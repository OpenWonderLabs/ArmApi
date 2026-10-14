// SPDX-License-Identifier: MIT
// Copyright (c) 2026 OneRobotics (Shenzhen) Co., Ltd.

#ifndef ONERO_API_SHARED_DEFINE_H
#define ONERO_API_SHARED_DEFINE_H

#pragma once

#include <stdint.h>
#include <array>
#include <vector>
#include <functional>

namespace onero_api {

// Interrupt control: callback returns true when motion should stop (e.g. Ctrl+C).
typedef bool (*onero_interrupt_check_fn)(void* ctx);

// 用户自定义 CAN 帧回调签名：(can_id, payload, len)。
// payload 仅在回调期间有效；len ∈ [0, 8]。
// 该回调在所属 DeviceSession 的独立 callback worker 上执行，不占用
// BusExecutor。SDK 使用 64 项有界 FIFO；满时丢弃最旧的未开始用户帧。
// 回调内仍只支持 register/clear callback；其它 SDK 业务调用的重入语义不属于
// v1 契约。dispatcher 内部允许 callback 捕获的最后 owner 在回调返回路径释放。
using CanFrameCallback =
    std::function<void(uint16_t can_id, const uint8_t* payload, uint8_t len)>;

// Configuration structure for robot initialization
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
    bool simulation_mode = false;    // true 时进入仿真模式（无真实硬件）
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
struct onero_drag_teaching_handle;

enum class DragTeachingState : int {
    IDLE = 0,
    RECORDING = 1,
    REPLAYING = 2,
};

// Optional gripper channel used by drag teaching.  The gripper remains a
// separate percent-space actuator; it is never counted as an arm DOF.
enum class GripperTeachingMode : int {
    DISABLED = 0,
    POSITION = 1,
    BACKDRIVE = 2,
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

// Cartesian reference frames used by the frame-aware helpers.  BASE and
// WORLD are fixed frames. TOOL is the TCP frame captured at command start and
// therefore always requires an explicit/current base_T_tool anchor.
enum class CartesianFrame : uint8_t {
    BASE = 0,
    WORLD = 1,
    TOOL = 2,
};

// Rigid transform parent_T_child (metres, quaternion wxyz).
struct RigidTransform {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
    double qw = 1.0;
    double qx = 0.0;
    double qy = 0.0;
    double qz = 0.0;
};

// Six-DoF Cartesian increment.  Translation is expressed in the selected
// frame; rotation is left-composed for BASE/WORLD and right-composed for TOOL.
struct CartesianDelta {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
    double qw = 1.0;
    double qx = 0.0;
    double qy = 0.0;
    double qz = 0.0;
};

// Immutable-by-value frame parameters captured at a command boundary.  A
// missing world transform is represented explicitly and must fail closed.
struct FrameSnapshot {
    bool has_world_from_base = false;
    RigidTransform world_from_base{};  // ^W T_B
    RigidTransform flange_from_tool{}; // ^F T_TCP
};

// Runtime Cartesian soft limits for ServoP. Translation and rotation use
// separate scalar norm limits because their units are different. These values
// are requests from the caller; OneroCore always intersects them with its
// built-in model limits before generating a command.
struct CartesianServoLimits {
    double max_linear_velocity = 0.1;       // m/s
    double max_angular_velocity = 0.5;      // rad/s
    double max_linear_acceleration = 0.2;   // m/s^2
    double max_angular_acceleration = 1.0;  // rad/s^2
};

enum class ServoPState : int {
    IDLE = 0,
    RUNNING = 1,
    LIMIT_TRANSITION = 2,
    BRAKING = 3,
    HOLDING = 4,
    FAULT = 5,
};

enum ServoPLimitFlag : uint32_t {
    SERVOP_LIMIT_NONE = 0,
    SERVOP_LIMIT_CARTESIAN_VELOCITY = 1u << 0,
    SERVOP_LIMIT_CARTESIAN_ACCELERATION = 1u << 1,
    SERVOP_LIMIT_JOINT_POSITION = 1u << 2,
    SERVOP_LIMIT_JOINT_VELOCITY = 1u << 3,
    SERVOP_LIMIT_JOINT_ACCELERATION = 1u << 4,
    SERVOP_LIMIT_SINGULARITY = 1u << 5,
    SERVOP_LIMIT_COMMAND_TIMEOUT = 1u << 6,
    SERVOP_LIMIT_FEEDBACK_STALE = 1u << 7,
};

struct ServoPStatus {
    ServoPState state = ServoPState::IDLE;
    uint64_t accepted_sequence = 0;
    uint64_t applied_sequence = 0;
    double command_age_s = 0.0;
    CartesianServoLimits requested_limits;
    CartesianServoLimits effective_limits;
    double joint_feasibility_scale = 1.0;
    uint32_t limit_flags = SERVOP_LIMIT_NONE;
    int last_error = 0;
    Pose target_pose{0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0};
    Pose actual_pose{0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0};
};

// Per-joint ServoJ limits. max_velocity is a symmetric magnitude limit applied
// to both velocity directions. Empty vectors request the core's configured
// hard limits. Non-empty vectors must contain exactly dof finite positive
// values and are intersected with those hard limits.
struct JointServoLimits {
    JointArray max_velocity;
    JointArray max_acceleration;
    JointArray max_jerk;
};

enum class ServoJState : int {
    IDLE = 0,
    RUNNING = 1,
    BRAKING = 2,
    HOLDING = 3,
    FAULT = 4,
};

enum ServoJLimitFlag : uint32_t {
    SERVOJ_LIMIT_NONE = 0,
    SERVOJ_LIMIT_COMMAND_TIMEOUT = 1u << 0,
    SERVOJ_LIMIT_FEEDBACK_STALE = 1u << 1,
    SERVOJ_LIMIT_JOINT_POSITION = 1u << 2,
    SERVOJ_LIMIT_OTG_INFEASIBLE = 1u << 3,
    SERVOJ_LIMIT_DEADLINE_MISS = 1u << 4,
};

struct ServoJStatus {
    ServoJState state = ServoJState::IDLE;
    uint64_t accepted_sequence = 0;
    uint64_t applied_sequence = 0;
    uint64_t sent_frame_count = 0;
    uint64_t deadline_miss_count = 0;
    uint64_t otg_update_count = 0;
    uint64_t otg_replan_count = 0;
    double command_age_s = 0.0;
    uint32_t limit_flags = SERVOJ_LIMIT_NONE;
    int last_error = 0;
    JointArray target_q;
    JointArray commanded_q;
    JointArray commanded_dq;
    JointArray commanded_ddq;
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

// Arm-owned gripper tactile feedback. point_id 0x00 is total force;
// point_id 0x01..0x09 are the nine individual tactile points.
struct GripperTactileValue {
    uint8_t point_id = 0;
    double fx = 0.0;
    double fy = 0.0;
    double fz = 0.0;
    bool valid = false;
};

struct GripperTactileSensorStatus {
    uint8_t sensor_id = 0;
    GripperTactileValue total_force;
    std::vector<GripperTactileValue> points;
    bool valid = false;
};

struct GripperTactileStatus {
    std::array<GripperTactileSensorStatus, 2> sensors;
    bool valid = false;
};

// Trajectory point (for trajectory execution with dynamics)
struct TrajectoryPoint {
    JointArray position;      // Joint positions (radians)
    JointArray velocity;      // Joint velocities (rad/s)
    JointArray acceleration;  // Joint accelerations (rad/s²)
};
}  // namespace onero_api

#endif  // ONERO_API_SHARED_DEFINE_H
