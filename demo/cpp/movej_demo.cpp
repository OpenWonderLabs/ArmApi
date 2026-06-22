// movej_demo.cpp — OneroArm C++ RAII：单一 movej 关节空间运动示例
//
// 序列：enable → restore_arm()(zero) → movej(target) → restore_arm()(zero) → disable
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
// =========================================

onero_api::onero_config_t build_config() {
    onero_api::onero_config_t cfg{};
    std::strncpy(cfg.device,      "/dev/ttyACM0", sizeof(cfg.device)      - 1);
    std::strncpy(cfg.robot_model, "a1_l",         sizeof(cfg.robot_model) - 1);
    std::strncpy(cfg.version,     "A1",           sizeof(cfg.version)     - 1);
    std::strncpy(cfg.mount_orientation, "vertical", sizeof(cfg.mount_orientation) - 1);
    return cfg;
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
    onero_api::JointArray target = zero;
    target[JOINT_INDEX] = JOINT_VALUE_RAD;

    try {
        checked("restore_arm() -> zero", arm.restore_arm());
        std::this_thread::sleep_for(std::chrono::seconds(1));
        checked("movej(target)", arm.movej(target, 1.5, static_cast<uint8_t>(0)));
        std::this_thread::sleep_for(std::chrono::seconds(1));
        checked("restore_arm() -> zero", arm.restore_arm());
    } catch (...) {
        if (enabled) arm.disable_motors();
        throw;
    }

    if (enabled) arm.disable_motors();
    return 0;
}
