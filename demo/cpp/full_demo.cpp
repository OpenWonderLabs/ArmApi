// full_demo.cpp — OneroArm C++ RAII：综合运动序列示例
//
// 序列：enable
//      → restore_arm()(zero) → movej(joint4=0.3)
//      → movep(target) → restore_arm()(zero) → movel(target)
//      → restore_arm()(zero) → disable
#include "onero_interface_cpp.h"

#include <chrono>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>

namespace {

// === 关节空间目标（rad） =================
constexpr int    JOINT_INDEX     = 3;        // 0-based: joint4
constexpr double JOINT_VALUE_RAD = 0.3;

// === 笛卡尔目标位姿（右臂可达） ==========
constexpr double TARGET_X  =  0.30;
constexpr double TARGET_Y  =  0.30;
constexpr double TARGET_Z  =  0.40;
constexpr double TARGET_QW =  1.00;
constexpr double TARGET_QX =  0.00;
constexpr double TARGET_QY =  0.00;
constexpr double TARGET_QZ =  0.00;
// =========================================

onero_api::onero_config_t build_config() {
    onero_api::onero_config_t cfg{};
    std::strncpy(cfg.device,      "/dev/ttyACM0", sizeof(cfg.device)      - 1);
    std::strncpy(cfg.robot_model, "a1_l",         sizeof(cfg.robot_model) - 1);
    std::strncpy(cfg.version,     "A1",           sizeof(cfg.version)     - 1);
    std::strncpy(cfg.mount_orientation, "vertical", sizeof(cfg.mount_orientation) - 1);
    return cfg;
}

onero_api::Pose make_target() {
    onero_api::Pose p{};
    p.x  = TARGET_X;  p.y  = TARGET_Y;  p.z  = TARGET_Z;
    p.qw = TARGET_QW; p.qx = TARGET_QX; p.qy = TARGET_QY; p.qz = TARGET_QZ;
    return p;
}

void checked(const std::string& name, int ret) {
    if (ret != 0) {
        throw std::runtime_error(name + " failed, ret=" + std::to_string(ret));
    }
    std::cout << "[OK] " << name << std::endl;
}

}  // namespace

int main() {
    const auto cfg = build_config();
    onero_api::OneroArm arm(cfg);

    bool enabled = (arm.enable_motors() == 0);
    if (!enabled) std::cerr << "[!] enable_motors failed (无硬件预期)\n";
    std::this_thread::sleep_for(std::chrono::seconds(1));

    onero_api::JointArray zero(static_cast<size_t>(cfg.dof), 0.0);
    onero_api::JointArray joint_target = zero;
    joint_target[JOINT_INDEX] = JOINT_VALUE_RAD;
    const auto pose_target = make_target();

    try {
        checked("restore_arm() -> zero", arm.restore_arm());
        std::this_thread::sleep_for(std::chrono::seconds(1));
        checked("movej(joint4=0.3)",   arm.movej(joint_target, 1.0, static_cast<uint8_t>(0)));
        std::this_thread::sleep_for(std::chrono::seconds(1));
        checked("movep(target)",       arm.movep(pose_target,  1.0, static_cast<uint8_t>(0)));
        std::this_thread::sleep_for(std::chrono::seconds(1));
        checked("restore_arm() -> zero", arm.restore_arm());
        std::this_thread::sleep_for(std::chrono::seconds(1));
        checked("movel(target)",       arm.movel(pose_target,  1.0, static_cast<uint8_t>(0)));
        std::this_thread::sleep_for(std::chrono::seconds(1));
        checked("restore_arm() -> zero", arm.restore_arm());
    } catch (...) {
        if (enabled) arm.disable_motors();
        throw;
    }

    if (enabled) arm.disable_motors();
    return 0;
}
