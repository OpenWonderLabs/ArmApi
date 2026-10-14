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
static void valid_pose(const Pose& p) {
    const double values[] = {p.x,p.y,p.z,p.qw,p.qx,p.qy,p.qz};
    if (!std::all_of(std::begin(values), std::end(values), [](double x) { return std::isfinite(x); })
        || std::abs(p.qw*p.qw+p.qx*p.qx+p.qy*p.qy+p.qz*p.qz-1.0) > 1e-3)
        throw std::runtime_error("Invalid pose feedback");
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
        auto target = arm->get_end_effector_pose();
        valid_pose(target);
        target.x += 0.001; // Absolute base_T_link7, metres/wxyz; no implicit tool/TCP offset.
        CartesianServoLimits limits{};
        limits.max_linear_velocity = 0.02;       // m/s
        limits.max_angular_velocity = 0.10;      // rad/s
        limits.max_linear_acceleration = 0.05;  // m/s^2
        limits.max_angular_acceleration = 0.20; // rad/s^2
        start_attempted = true;
        check(arm->start_servop(), "start_servop");
        const auto initial = arm->get_servop_status();
        const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(20);
        auto tick = std::chrono::steady_clock::now();
        unsigned settled = 0, cycles = 0;
        while (!interrupted && std::chrono::steady_clock::now() < deadline) {
            const int rc = arm->servop(target, limits);
            const auto status = arm->get_servop_status();
            const auto q = arm->get_arm_state_from_motor().positions;
            feedback(q);
            const auto actual = arm->get_end_effector_pose();
            valid_pose(actual);
            const double error = std::hypot(std::hypot(actual.x-target.x, actual.y-target.y), actual.z-target.z);
            const double dot = actual.qw*target.qw + actual.qx*target.qx + actual.qy*target.qy + actual.qz*target.qz;
            const double norm = std::sqrt((actual.qw*actual.qw+actual.qx*actual.qx+actual.qy*actual.qy+actual.qz*actual.qz)
                                       * (target.qw*target.qw+target.qx*target.qx+target.qy*target.qy+target.qz*target.qz));
            const double angle = 2.0 * std::acos(std::min(1.0, std::abs(dot)/norm));
            if (cycles++ % 100 == 0 || rc || status.last_error || status.state == ServoPState::FAULT) {
                std::cout << "rc=" << rc << " state=" << static_cast<int>(status.state)
                          << " accepted=" << status.accepted_sequence << " applied=" << status.applied_sequence
                          << " flags=" << status.limit_flags << " last_error=" << status.last_error
                          << " error=" << error  << " angle_rad=" << angle << " feedback=";
                for (double value : q) std::cout << value << ',';
                std::cout << '\n';
            }
            check(rc, "servop update");
            check(status.last_error, "servop status");
            if (status.state == ServoPState::FAULT) throw std::runtime_error("servop FAULT");
            const bool applied = status.applied_sequence > initial.accepted_sequence;
            settled = applied && status.state == ServoPState::HOLDING && error < 2e-4 && angle < 0.005 ? settled + 1 : 0;
            if (settled >= 3) { result = 0; break; }
            tick += std::chrono::milliseconds(10);
            if (tick < std::chrono::steady_clock::now()) tick = std::chrono::steady_clock::now();
            std::this_thread::sleep_until(tick);
        }
        if (interrupted) result = 130;
        else if (result) throw std::runtime_error("servop timeout: target not confirmed applied and settled");
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
    }
    // Each cleanup step runs even if a preceding step failed or an exception was raised.
    if (arm && start_attempted) {
        try {
            const int rc = arm->stop_servop();
            std::cout << "stop_servop rc=" << rc << " state=" << static_cast<int>(arm->get_servop_status().state) << '\n';
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
    if (result == 0) std::cout << "servop: applied target and feedback checked; "
                              << (simulation ? "simulation only, not physical tracking validation" : "example tolerance only") << '\n';
    return result;
}
