// SPDX-License-Identifier: MIT
// Copyright (c) 2026 OneRobotics (Shenzhen) Co., Ltd.

#pragma once

#include <stdint.h>
#include <vector>
#include <functional>

namespace onero_api {

// Interrupt control: callback returns true when motion should stop (e.g. Ctrl+C).
typedef bool (*onero_interrupt_check_fn)(void* ctx);

// 用户自定义 CAN 帧回调签名：(can_id, payload, len)。
// payload 仅在回调期间有效；len ∈ [0, 8]。
// 该回调将在 SDK 接收路径（即调用方运动控制线程）上同步执行；
// 回调内禁止重入任何 SDK 发送/运动控制方法，否则可能造成自锁。
using CanFrameCallback =
    std::function<void(uint16_t can_id, const uint8_t* payload, uint8_t len)>;

// Configuration structure for robot initialization
//
// 所有字段都给出默认值，使得 `onero_config_t cfg;`（非聚合零初始化）也是安全的：
// 未由调用方显式赋值的字段不会保留栈/堆垃圾。
// 对必须由调用方提供的字段（device / robot_model），默认空串配合下游
// 检查会给出可读错误，而不是访问未初始化内存。
struct onero_config_t {
    char device[256] = "";        // Serial device path (e.g., "/dev/ttyACM0"); 必填
    char robot_model[64] = "";    // Robot model name (e.g., "a1_l", "a1_r"); 必填
    int dof = 7;                  // Degrees of freedom (6 or 7)
    int baud_rate = 921600;       // Serial baud rate (default: 921600)
    char urdf_path[512] = "";     // URDF file path (optional, empty = auto-find via model_description_path)
    char version[32] = "";        // Robot version (e.g., "A1")
    char mount_orientation[32] = "vertical"; // Installation orientation: "horizontal" or "vertical"
    // PD控制参数（MIT 模式）—— 逐关节回退：mit_kp[i]/mit_kd[i] == 0 表示该关节未传入，
    // OneroCore 会按 dof 自动填入内置默认增益：
    //   7DOF (GetPDGains7DOF): kp=[150,150,150,150,30,30,30]  kd=[4,4,4,4,1,1,1]
    // 部分覆盖是安全的：例如只设 mit_kp[0]=200，其余关节仍使用对应 dof 的默认值。
    double mit_kp[7] = {0, 0, 0, 0, 0, 0, 0};   // MIT模式PD参数-比例系数（最多7个关节）
    double mit_kd[7] = {0, 0, 0, 0, 0, 0, 0};   // MIT模式PD参数-微分系数（最多7个关节）
    // 中断控制：运动循环中检查，nullptr 表示不检查
    onero_interrupt_check_fn interrupt_check = nullptr;
    void* interrupt_ctx = nullptr;
    char model_description_path[512] = ""; // 留空 → SDK 内置 share/oneroarm_description；可被 ONERO_DESCRIPTION_PATH/DIR 或显式赋值覆盖
    bool with_gripper = false;       // true 时在同一 OneroCore 总线会话内注册可选夹爪
};

// ===== 运动控制默认参数 =====
constexpr double DEFAULT_MAX_VEL = 1.0;       // rad/s
constexpr double DEFAULT_MAX_ACC = DEFAULT_MAX_VEL / 3;       // rad/s²
constexpr double DEFAULT_MAX_JERK = DEFAULT_MAX_ACC / 3;     // rad/s³
constexpr double DEFAULT_TIME_STEP = 0.01;    // s

// ===== PD 参数预设 =====
struct PDGains {
    std::vector<double> kps;
    std::vector<double> kds;
};

// DOF=7 默认增益
inline PDGains GetPDGains7DOF() {
    return {
        {150.0, 150.0, 150.0, 150.0, 30.0, 30.0, 30.0},
        {4.0, 4.0, 4.0, 4.0, 1.0, 1.0, 1.0}
    };
}

// Robot handle (opaque pointer)
typedef struct onero_robot_handle onero_robot_handle;
typedef struct onero_drag_teaching_handle onero_drag_teaching_handle;

enum class DragTeachingState : int {
    IDLE = 0,
    RECORDING = 1,
    REPLAYING = 2,
};

// Move API result codes
enum class MoveResult : int {
    SUCCESS = 0,
    INVALID_PARAMS = -1,
    IK_FAILED = -2,
    COLLISION_DETECTED = -3,
    EXECUTION_FAILED = -4,
    TIMEOUT = -5,
    INTERRUPTED = -6,
    JOINT_LIMIT_EXCEEDED = -7,
    BUSY = -8,                  // 同一只臂已有运动命令在执行
};

// 原始 CAN 帧 API 错误码（与 MoveResult 共用整型空间，沿用负数错误约定）。
// 0 表示成功；与 MoveResult::SUCCESS 等价。
constexpr int ONERO_CAN_OK                       = 0;
constexpr int ONERO_ERR_RAW_FRAME_INVALID_LEN    = -10;  // payload 超过 8 字节
constexpr int ONERO_ERR_RAW_FRAME_INVALID_ID     = -11;  // can_id 越过 11-bit 标准帧范围
constexpr int ONERO_ERR_RAW_FRAME_RESERVED_ID    = -12;  // 命中保留 ID（电机 / 夹爪 / 操纵杆 / 0x7FF）
constexpr int ONERO_ERR_RAW_FRAME_PORT_NOT_OPEN  = -13;  // 串口未连接 / handle 失效
constexpr int ONERO_ERR_RAW_FRAME_SEND_FAILED    = -14;  // SLCAN 写串口失败

// Motion modes
enum class MotionMode : uint8_t {
    MOVEJ = 0,              // Joint space motion
    MOVEL_STANDARD = 1,     // Cartesian linear (standard PD control)
    MOVEL_MIT = 2,          // Cartesian linear (MIT force control)
    MOVEP = 3,              // Pose transmission
};

// Trajectory connection flag
enum class TrajectoryConnect : uint8_t {
    EXECUTE_NOW = 0,        // Execute immediately
    BUFFER = 1,             // Buffer waypoint, don't execute
};

enum class BufferedTrajectoryType : uint8_t {
    NONE = 0,
    MOVEJ = 1,
    MOVEL = 2,
    MOVEP = 3,
};

struct BufferedTrajectoryFailure {
    bool valid = false;
    BufferedTrajectoryType type = BufferedTrajectoryType::NONE;
    int index = -1;
    int error_code = 0;
};

// Joint target (array)
using JointArray = std::vector<double>;

// Cartesian pose
struct Pose {
    double x, y, z;         // Position (meters)
    double qw, qx, qy, qz;  // Quaternion orientation
};

// Arm state from motors (position with zero bias, velocity and torque without)
struct ArmStateFromMotor {
    JointArray positions;   // Joint positions (rad) with zero bias applied
    JointArray velocities;  // Joint velocities (rad/s)
    JointArray torques;     // Joint torques (N·m)
};

// Arm-owned optional gripper state. position / velocity are user-space percent
// units mapped from the internal gripper working range; force is limited to +/-40 N.
struct GripperStatus {
    double position = 0.0;
    double velocity = 0.0;
    double force = 0.0;
    uint8_t error = 0;
    bool valid = false;
};

// Trajectory point (for trajectory execution with dynamics)
struct TrajectoryPoint {
    JointArray position;      // Joint positions (radians)
    JointArray velocity;      // Joint velocities (rad/s)
    JointArray acceleration;  // Joint accelerations (rad/s²)
};
struct ForcePosition {
    bool force_position_flag;
    int direction;
     double force;
};
}  // namespace onero_api
