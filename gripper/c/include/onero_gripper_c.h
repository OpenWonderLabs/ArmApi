// SPDX-License-Identifier: MIT
// Copyright (c) 2026 OneRobotics (Shenzhen) Co., Ltd.
#ifndef ONERO_GRIPPER_C_H
#define ONERO_GRIPPER_C_H

#include <stdint.h>
#include <stdbool.h>

#if defined(_WIN32)
#  if defined(ONERO_GRIPPER_BUILDING_DLL)
#    define ONERO_GRIPPER_API __declspec(dllexport)
#  else
#    define ONERO_GRIPPER_API __declspec(dllimport)
#  endif
#else
#  define ONERO_GRIPPER_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef void* onero_gripper_handle;

typedef struct {
    double position;  // percent
    double velocity;  // percent/s
    double force;     // N, limited to +/-40
    uint8_t error;
    bool valid;
} onerogripper_status_t;

// 创建独立夹爪句柄；参数无效或构造异常返回 NULL。
// 非空句柄仍须检查 onerogripper_valid(h)；设备不可用时可返回非空的无效句柄。
// device 例如 "/dev/ttyACM0"。
ONERO_GRIPPER_API onero_gripper_handle onerogripper_create(const char* device);
ONERO_GRIPPER_API void onerogripper_destroy(onero_gripper_handle h);

ONERO_GRIPPER_API bool onerogripper_valid(onero_gripper_handle h);
ONERO_GRIPPER_API int  onerogripper_enable(onero_gripper_handle h);
ONERO_GRIPPER_API int  onerogripper_disable(onero_gripper_handle h);
ONERO_GRIPPER_API onerogripper_status_t onerogripper_status(onero_gripper_handle h);
ONERO_GRIPPER_API int  onerogripper_set_position(onero_gripper_handle h, double percent);
ONERO_GRIPPER_API int  onerogripper_move_position(onero_gripper_handle h,
                                                  double percent,
                                                  double max_vel,
                                                  double max_acc,
                                                  double max_jerk);
ONERO_GRIPPER_API int  onerogripper_force_control(onero_gripper_handle h, double torque);

#ifdef __cplusplus
}
#endif

#endif  // ONERO_GRIPPER_C_H
