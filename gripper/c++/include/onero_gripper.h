// SPDX-License-Identifier: MIT
// Copyright (c) 2026 OneRobotics (Shenzhen) Co., Ltd.
#ifndef ONERO_GRIPPER_H
#define ONERO_GRIPPER_H

#include <memory>
#include <string>

// 复用 arm 仓的轻量数据类型（Eigen-free）
#include "onero_define.h"

#if defined(_WIN32)
#  if defined(ONERO_GRIPPER_BUILDING_DLL)
#    define ONERO_GRIPPER_API __declspec(dllexport)
#  else
#    define ONERO_GRIPPER_API __declspec(dllimport)
#  endif
#else
#  define ONERO_GRIPPER_API __attribute__((visibility("default")))
#endif

namespace onero_api { class GripperCore; }

namespace onero_gripper_api {

/**
 * @class OneroGripper
 * @brief 独立夹爪控制入口（gripper-only）。自己持有串口会话。
 *
 * 若夹爪与机械臂共用同一根 CAN-转串口线，请勿用本类与 OneroArm 同进程各开一次串口；
 * 那种形态请用 arm SDK 的 OneroArm(with_gripper=true)，由臂统一持有会话。
 */
class ONERO_GRIPPER_API OneroGripper {
public:
    // device 例如 "/dev/ttyACM0"（Linux）或 "COM3"（Windows）
    explicit OneroGripper(const std::string& device);
    ~OneroGripper();

    OneroGripper(const OneroGripper&) = delete;
    OneroGripper& operator=(const OneroGripper&) = delete;

    bool valid() const;
    int enable();
    int disable();
    onero_api::GripperStatus status();
    int set_position(double percent);
    int move_position(double percent,
                      double max_vel = 100.0,
                      double max_acc = 250.0,
                      double max_jerk = 1000.0);
    int force_control(double torque);
    onero_api::GripperTactileStatus get_tactile();
    void request_stop();
    void clear_stop();

private:
    std::unique_ptr<onero_api::GripperCore> core_;
};

}  // namespace onero_gripper_api

#endif  // ONERO_GRIPPER_H
