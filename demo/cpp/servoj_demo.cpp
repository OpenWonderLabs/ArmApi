#include "onero_interface_cpp.h"
#include <algorithm>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <cstring>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <thread>

using namespace onero_api;
static volatile std::sig_atomic_t interrupted = 0;
static void on_signal(int) { interrupted = 1; }
static void check(int rc, const char* step) {
    if (rc != 0) throw std::runtime_error(std::string(step) + " rc=" + std::to_string(rc));
}
static void feedback(const JointArray& q) {
    if (q.size() != 7 || !std::all_of(q.begin(), q.end(), [](double x) { return std::isfinite(x); }))
        throw std::runtime_error("Missing/nonfinite seven-axis feedback");
}

int main(int argc, char** argv) {
    const bool simulation = argc == 2 && std::strcmp(argv[1], "--simulate") == 0;
    const bool hardware = argc == 4 && std::strcmp(argv[1], "--device") == 0
        && argv[2][0] != '\0' && std::strlen(argv[2]) < 256 && std::strcmp(argv[3], "--run") == 0;
    if (!simulation && !hardware) {
        std::cerr << "Usage: " << argv[0] << " --simulate\n       " << argv[0]
                  << " --device DEVICE --run\nA1 left, vertical, no gripper; review configuration before hardware use.\n";
        return 2; // No SDK object or device access before this gate.
    }
    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);
    std::unique_ptr<OneroArm> arm;
    bool enable_attempted = false, start_attempted = false;
    int result = 1;
    try {
        onero_config_t cfg{};
        std::snprintf(cfg.device, sizeof cfg.device, "%s", simulation ? "servo-demo-simulation-only" : argv[2]);
        std::snprintf(cfg.robot_model, sizeof cfg.robot_model, "a1_l");
        std::snprintf(cfg.version, sizeof cfg.version, "A1");
        std::snprintf(cfg.mount_orientation, sizeof cfg.mount_orientation, "vertical");
        cfg.dof = 7; cfg.with_gripper = false; cfg.simulation_mode = simulation;
        arm = std::make_unique<OneroArm>(cfg);
        if (arm->is_hardware_connected() != hardware) throw std::runtime_error("Unexpected connection mode");
        feedback(arm->get_arm_state_from_motor().positions);
        enable_attempted = true;
        check(arm->enable_motors(), "enable_motors");
        if (simulation) {
            // This seed is ONLY injected into the no-I/O simulation backend.
            const JointArray zero(7, 0.0), seed{-0.158, 1.0, 1.2, -0.8, 0.1, 0.8, -1.0};
            check(arm->control_mit(zero, zero, seed, zero, zero), "simulation seed");
        }
        auto target = arm->get_arm_state_from_motor().positions;
        feedback(target);
        target[0] += 0.01; // 0.01 rad relative to validated feedback, checked again by SDK limits.
        JointServoLimits limits{};
        limits.max_velocity = JointArray(7, 0.1);
        limits.max_acceleration = JointArray(7, 0.2);
        limits.max_jerk = JointArray(7, 0.05);
        constexpr double validity_s = 0.5; // Refreshed every 10 ms; expiry triggers braking.
        start_attempted = true;
        check(arm->start_servoj(limits), "start_servoj");
        const auto initial = arm->get_servoj_status();
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(20);
        auto tick = std::chrono::steady_clock::now();
        unsigned settled = 0, cycles = 0;
        while (!interrupted && std::chrono::steady_clock::now() < deadline) {
            const int rc = arm->servoj(target, {}, validity_s);
            const auto status = arm->get_servoj_status();
            const auto q = arm->get_arm_state_from_motor().positions;
            feedback(q);
            double error = 0.0;
            for (size_t i = 0; i < q.size(); ++i) error = std::max(error, std::abs(q[i] - target[i]));
            if (cycles++ % 100 == 0 || rc || status.last_error || status.state == ServoJState::FAULT) {
                std::cout << "rc=" << rc << " state=" << static_cast<int>(status.state)
                          << " accepted=" << status.accepted_sequence << " applied=" << status.applied_sequence
                          << " flags=" << status.limit_flags << " last_error=" << status.last_error
                          << " error=" << error  << " sent=" << status.sent_frame_count << " age_s=" << status.command_age_s << " feedback=";
                for (double value : q) std::cout << value << ',';
                std::cout << '\n';
            }
            check(rc, "servoj update");
            check(status.last_error, "servoj status");
            if (status.state == ServoJState::FAULT) throw std::runtime_error("servoj FAULT");
            const bool applied = status.applied_sequence > initial.accepted_sequence;
            settled = applied && status.sent_frame_count >= 5 && status.state == ServoJState::HOLDING && error < 1e-3 ? settled + 1 : 0;
            if (settled >= 3) { result = 0; break; }
            tick += std::chrono::milliseconds(10);
            if (tick < std::chrono::steady_clock::now()) tick = std::chrono::steady_clock::now();
            std::this_thread::sleep_until(tick);
        }
        if (interrupted) result = 130;
        else if (result) throw std::runtime_error("servoj timeout: target not confirmed applied and settled");
        if (simulation && result == 0) {
            // Exercise the delivered shared library while moving, not only its
            // HOLDING cleanup. Python packages contain a separate core build.
            result = 1;
            check(arm->stop_servoj(), "settled session stop");
            // Validate replacement while genuinely moving against this shared
            // library; Python extensions embed a separately linked core.
            const JointArray zero(7, 0.0), seed{-0.158, 1.0, 1.2, -0.8, 0.1, 0.8, -1.0};
            check(arm->control_mit(zero, zero, seed, zero, zero), "retarget seed");
            auto replacement = arm->get_arm_state_from_motor().positions;
            replacement[0] += 0.1;
            check(arm->start_servoj(), "retarget start");
            const auto moving_until = std::chrono::steady_clock::now() + std::chrono::milliseconds(1300);
            while (std::chrono::steady_clock::now() < moving_until) {
                check(arm->servoj(replacement, {}, 0.5), "old target stream");
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
            auto previous = arm->get_servoj_status();
            if (previous.state != ServoJState::RUNNING || previous.commanded_dq[0] < 0.01)
                throw std::runtime_error("retarget requires nonzero forward velocity");
            const auto expected_replans = previous.otg_replan_count + 1;
            replacement[0] += 0.1;
            const auto changed_at = std::chrono::steady_clock::now();
            const auto retarget_deadline = changed_at + std::chrono::seconds(15);
            double peak = previous.commanded_q[0], target_error = 1.0;
            bool arrived = false;
            while (std::chrono::steady_clock::now() < retarget_deadline) {
                check(arm->servoj(replacement, {}, 0.5), "new target stream");
                const auto status = arm->get_servoj_status();
                check(status.last_error, "retarget status");
                if (status.state == ServoJState::FAULT || (status.limit_flags & (1u | 4u | 8u)))
                    throw std::runtime_error("retarget fault/timeout/limit");
                peak = std::max(peak, status.commanded_q[0]);
                if (peak > replacement[0] + 1e-4)
                    throw std::runtime_error("feasible forward replacement overshot");
                const auto frames = status.sent_frame_count - previous.sent_frame_count;
                if (frames) {
                    for (size_t j = 0; j < replacement.size(); ++j) {
                        if (std::abs(status.commanded_dq[j]) > 1.0 + 1e-6 ||
                            std::abs(status.commanded_ddq[j]) > 0.2 + 1e-6 ||
                            std::abs(status.commanded_ddq[j] - previous.commanded_ddq[j]) > frames * 0.01 / 15.0 + 1e-6)
                            throw std::runtime_error("retarget dynamic discontinuity");
                    }
                    previous = status;
                }
                target_error = std::abs(status.commanded_q[0] - replacement[0]);
                if (status.state == ServoJState::HOLDING && target_error < 1e-8 &&
                    std::abs(arm->get_arm_state_from_motor().positions[0] - replacement[0]) < 1e-4) {
                    if (status.otg_replan_count != expected_replans) throw std::runtime_error("unchanged target replanned");
                    arrived = true;
                    break;
                }
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
            }
            if (!arrived) throw std::runtime_error("retarget did not settle");
            const double retarget_elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - changed_at).count();
            std::cout << "shared-library moving retarget elapsed_s=" << retarget_elapsed
                      << " error_rad=" << target_error << " peak_q0=" << peak
                      << " target_q0=" << replacement[0] << " state=HOLDING replans=" << previous.otg_replan_count
                      << " expected_replans=" << expected_replans << "\n";
            check(arm->stop_servoj(), "retarget settled stop");
            auto moving_target = arm->get_arm_state_from_motor().positions;
            moving_target[0] += 0.1;
            check(arm->start_servoj(), "default moving session");
            check(arm->servoj(moving_target, {}, 5.0), "moving target");
            std::this_thread::sleep_for(std::chrono::milliseconds(1300));
            auto moving = arm->get_servoj_status();
            if (moving.state != ServoJState::RUNNING || std::abs(moving.commanded_dq[0]) < 0.01)
                throw std::runtime_error("moving stop requires visibly nonzero commanded velocity");
            if (arm->cancel_trajectory() != -8)
                throw std::runtime_error("generic cancel must reject an active ServoJ session");
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            moving = arm->get_servoj_status();
            if (moving.state != ServoJState::RUNNING || moving.last_error)
                throw std::runtime_error("refused cancel changed the active ServoJ session");
            double bound = 0.0;
            constexpr double acceleration = 0.2, jerk = 1.0 / 15.0;
            for (size_t i = 0; i < moving.commanded_dq.size(); ++i) {
                const double v = std::abs(moving.commanded_dq[i]);
                const double a = std::abs(moving.commanded_ddq[i]);
                bound = std::max(bound, a / jerk + 2 * std::sqrt(v / jerk + a * a / (2 * jerk * jerk)) + v / acceleration);
            }
            bound += 1.0; // Regression scheduling allowance, not an SDK limit.
            const auto started = std::chrono::steady_clock::now();
            check(arm->stop_servoj(), "moving stop");
            const double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - started).count();
            const auto stopped = arm->get_servoj_status();
            if (elapsed > bound || stopped.state != ServoJState::IDLE || stopped.last_error
                || !std::all_of(stopped.commanded_dq.begin(), stopped.commanded_dq.end(), [](double v) { return v == 0.0; })
                || !std::all_of(stopped.commanded_ddq.begin(), stopped.commanded_ddq.end(), [](double a) { return a == 0.0; }))
                throw std::runtime_error("moving stop did not reach zero-velocity/acceleration IDLE within its bound");
            check(arm->start_servoj(), "restart after moving stop");
            check(arm->stop_servoj(), "restarted session stop");
            std::cout << "shared-library moving stop elapsed_s=" << elapsed << " bound_s=" << bound << " generic_cancel=-8 state=IDLE\n";
            result = 0;
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
    }
    // Each cleanup step runs even if a preceding step failed or an exception was raised.
    if (arm && start_attempted) {
        try {
            const int rc = arm->stop_servoj();
            std::cout << "stop_servoj rc=" << rc << " state=" << static_cast<int>(arm->get_servoj_status().state) << '\n';
            if (rc) result = 1;
        } catch (const std::exception& error) { std::cerr << "stop: " << error.what() << '\n'; result = 1; }
    }
    if (arm && enable_attempted) {
        try {
            const int rc = arm->disable_motors();
            std::cout << "disable_motors rc=" << rc << '\n';
            if (rc) result = 1;
        } catch (const std::exception& error) { std::cerr << "disable: " << error.what() << '\n'; result = 1; }
    }
    arm.reset();
    if (result == 0) std::cout << "servoj: applied target and feedback checked; "
                              << (simulation ? "simulation only, not physical tracking validation" : "example tolerance only") << '\n';
    return result;
}
