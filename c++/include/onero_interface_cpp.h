// SPDX-License-Identifier: MIT
// Copyright (c) 2026 OneRobotics (Shenzhen) Co., Ltd.

#pragma once

#include "onero_define.h"

#include <chrono>
#include <initializer_list>
#include <memory>
#include <vector>
#include <string>

#if !defined(ONERO_CPP_API)
    #if defined(_WIN32)
        #if defined(ONERO_STATIC)
            #define ONERO_CPP_API
        #elif defined(ONERO_BUILDING_DLL) || defined(oneroarm_EXPORTS) || defined(oneroarm_core_EXPORTS) || defined(oneroarm_c_EXPORTS)
            #define ONERO_CPP_API __declspec(dllexport)
        #else
            #define ONERO_CPP_API __declspec(dllimport)
        #endif
    #else
        #define ONERO_CPP_API __attribute__((visibility("default")))
    #endif
#endif

namespace onero_api {

// ============================================================================
// 返回值约定（不同 API 沿用不同语义，调用方需对照表理解）：
//
//   * 强转自 MoveResult enum（0 = SUCCESS，负数 = 各类错误，详见
//     onero_define.h）：
//       - movej / movel / movep
//       - send_trajectory_point / send_trajectory
//       - cancel_trajectory
//       - execute_buffered_trajectory / clear_trajectory_buffer
//       - enable_motors / disable_motors
//
//   * bool（true = 成功）：
//       - OneroDragTeaching::initialize
//       - OneroDragTeaching::set_hardware
//       - OneroDragTeaching::is_initialized
//       - OneroArm::is_hardware_connected
//
//   * void:
//       - OneroArm::reset_stop_signal，用于用户层接受新命令时显式清旧 stop
//
//   * int（0 = 成功，非 0 = 错误）：
//       - OneroDragTeaching::enable_motors
//       - OneroDragTeaching::start_recording / stop_recording
//       - OneroDragTeaching::start_replay   / stop_replay
//       - OneroDragTeaching::handle_command
//       - OneroArm::send_can_frame / register_can_frame_callback /
//         clear_can_frame_callback / pump_can_bus（错误码定义见 onero_define.h
//         中的 ONERO_ERR_RAW_FRAME_*）
//
//   * 数据对象（空 vector / 全零 Pose / count==0 表示失败，调用方需自行
//     防御）：
//       - get_joint_positions / get_joint_positions_from_motors
//       - get_joint_velocities
//       - get_arm_state_from_motor / get_arm_state_cached
//       - get_end_effector_pose
//       - get_end_effector_pose_cached
//       - OneroDragTeaching::get_state（失败回退为 IDLE）
//       - OneroGripper::get_tactile（valid=false 表示未读到有效触觉帧）
//
// 现状沿用历史语义不做统一以保持 ABI 稳定；后续若引入 onero_status_t
// 单一返回码 enum，会在 SOVERSION major bump 时一并完成。
// ============================================================================

/**
 * @class OneroGripper
 * @brief Arm-owned optional gripper controller.
 *
 * Created only through OneroArm when config.with_gripper is true. It reuses the
 * arm's serial/CAN session; it is not a standalone gripper device entry point.
 */
class ONERO_CPP_API OneroGripper {
public:
    OneroGripper() = default;
    explicit OneroGripper(onero_robot_handle* handle);

    bool valid() const;
    int enable();
    int disable();
    GripperStatus status();
    int set_position(double percent);
    int move_position(double percent,
                      double max_vel = 100.0,
                      double max_acc = 250.0,
                      double max_jerk = 1000.0);
    int force_control(double torque);
    GripperTactileStatus get_tactile();

private:
    friend class OneroArm;
    void bind(onero_robot_handle* handle) { handle_ = handle; }
    onero_robot_handle* handle_ = nullptr;
};

/**
 * @class OneroArm
 * @brief OneroArm 主控实例（C++ 公开入口，与 Python 同名同形）
 *
 * 构造时按 config 创建底层 robot handle，析构时自动释放——RAII 取代
 * 历史的 `OneroAPI::create_robot/destroy_robot` 静态对子。
 * 拷贝禁用、可移动；移动后源对象 handle_ == nullptr，析构无副作用。
 */
class ONERO_CPP_API OneroArm {
public:
    explicit OneroArm(const onero_config_t& config);
    ~OneroArm();

    OneroArm(const OneroArm&) = delete;
    OneroArm& operator=(const OneroArm&) = delete;

    OneroArm(OneroArm&& other) noexcept;
    OneroArm& operator=(OneroArm&& other) noexcept;

    /**
     * @brief 构造是否成功（false 表示 robot handle 创建失败，所有方法将以错误码退出）
     */
    bool valid() const { return handle_ != nullptr; }
    bool has_gripper() const;
    OneroGripper* gripper();
    const OneroGripper* gripper() const;

    int enable_motors();
    int disable_motors();
    int restore_arm();
    int restore_arm(const JointArray& target);

    /**
     * @brief 并发 restore 多个机械臂(双臂/N 臂)
     *
     * 多个独立 OneroArm 实例同时调 restore_arm,内部用 barrier 让各线程在同一
     * wall-clock 时刻进入 SDK 调用,避免 std::async 调度抖动导致的起点错开。
     * 适合双臂启动 init_pos 同步、N 臂示教联动等场景。
     *
     * @param arms 待 restore 的 arm 列表,每个 arm 都回零位
     * @return 0 全部成功;非零=数组顺序中第一个失败的错误码(left 优先)
     * @note 任一侧失败时不主动中断对侧 restore — SDK 当前无 abort-restore 原语,
     *       caller 自行决定是否 disable_motors 收尾。
     */
    static int restore_arm_concurrent(std::initializer_list<OneroArm*> arms);

    struct RestoreTarget {
        OneroArm* arm;
        JointArray target;     // 空 vector 等价于零位 restore
    };
    /**
     * @brief 并发 restore,各臂可指定不同目标关节位置
     */
    static int restore_arm_concurrent(const std::vector<RestoreTarget>& tasks);

    int movej(const JointArray& target, double speed_scale = 1.0, uint8_t trajectory_connect = 0);
    int movel(const Pose& pose, double speed_scale = 1.0, uint8_t trajectory_connect = 0);
    int movep(const Pose& pose, double speed_scale = 1.0, uint8_t trajectory_connect = 0);
    double estimate_movej_duration(const JointArray& target, double speed_scale = 1.0);

    int execute_buffered_trajectory();
    int clear_trajectory_buffer();
    BufferedTrajectoryFailure get_last_buffered_trajectory_failure();
    void reset_stop_signal();

    JointArray get_joint_positions();
    JointArray get_joint_positions_from_motors();
    JointArray get_joint_velocities();
    // Real-time query: may perform CAN IO.
    ArmStateFromMotor get_arm_state_from_motor();
    // Cache-only query: returns empty state if cache is not valid yet; never performs CAN IO.
    ArmStateFromMotor get_arm_state_cached();
    // Real-time query: may perform CAN IO.
    Pose get_end_effector_pose();
    // Cache-only query: never performs CAN IO.
    Pose get_end_effector_pose_cached();

    int send_trajectory_point(const JointArray& positions, const JointArray& velocities);
    int send_trajectory(const std::vector<TrajectoryPoint>& trajectory);
    int cancel_trajectory();

    // ========== MIT 力位混合直接控制 ==========
    // 用于 teleop 数据采集、阻抗控制、模仿学习推断等需要低层力位混合接口的场景。
    // 与 movej/movel/movep 的高层规划路径**不要在重叠时间窗内混用**：内部共用同一根
    // SLCAN 链路，混用会让运动控制语义打架。

    /**
     * @brief 以 MIT 力位混合模式直接控制整臂关节（每帧一次发送）。
     *
     * 控制律由底层电机在 MIT 模式下闭环执行：
     *   tau_motor = kp * (q_des - q_actual) + kd * (dq_des - dq_actual) + tau
     *
     * 前提：调用前必须先 enable_motors()（默认会把电机置于 MIT_MODE）。本接口不再
     * 切模式、不规划轨迹、不做应用层裁剪——q/dq/tau 仅受电机 pack_mit 内
     * TAU_MAX/Q_MAX/DQ_MAX 饱和。q 走与 get_arm_state_from_motor() 一致的"SDK 关节
     * 空间"（内部按 robot_model 的 zero_bias 转换到电机电气角度）。
     *
     * 第一帧建议规则：q = 当前 get_arm_state_from_motor().positions、dq = 0、
     * tau = 0，避免 kp 较大时产生瞬间力矩冲击。
     *
     * 调用方负责以 ≥100Hz 的速率持续下发，低于 ~50Hz 电机端可能因超时停转或锁存。
     *
     * @param kp  各关节比例增益（长度 == dof，建议 [0, 500]，超出端值由电机端饱和）
     * @param kd  各关节微分增益（长度 == dof，建议 [0, 5]）
     * @param q   各关节目标位置 rad（长度 == dof）
     * @param dq  各关节目标速度 rad/s（长度 == dof）
     * @param tau 各关节前馈力矩 N·m（长度 == dof，传 compute_gravity_torque 返回
     *            的值可直接实现含重力补偿的零力/阻抗）
     * @return  0 成功；-1 参数长度错误；-2 硬件未初始化；
     *          -3 至少一关节 CAN 写入失败
     */
    int control_mit(const JointArray& kp,
                    const JointArray& kd,
                    const JointArray& q,
                    const JointArray& dq,
                    const JointArray& tau);

    /**
     * @brief 计算给定关节姿态下的重力补偿力矩
     * @param q       当前关节姿态 rad
     * @param out_tau 输出力矩 N·m
     * @return 0 成功；-1 q 长度错误；-2 动力学模型未就绪
     */
    int compute_gravity_torque(const JointArray& q, JointArray& out_tau);

    bool is_hardware_connected();

    // ========== 原始 CAN 帧 API ==========
    // 与电机/夹爪共用同一根 SLCAN 链路。受保留 ID 集（电机 / 夹爪 /
    // 触觉回包 / 操纵杆 / 0x7FF）保护：发送命中保留集会直接返回错误码，不下发到总线。
    //
    // 线程语义：注册的回调在 SDK 接收路径（即调用方运动控制线程）上
    // 同步执行；回调内禁止重入 SDK 任何发送/运动控制方法，否则可能
    // 与外层 receive() 自锁。

    /**
     * @brief 发送一帧自定义 CAN 报文（11-bit 标准帧）。
     * @param can_id 11-bit 标准帧 ID，范围 [0, 0x7FF]，且不能落在保留集
     * @param payload 数据载荷指针；len==0 时可为 nullptr
     * @param len 0..8
     * @return 0=成功；负数错误码见 onero_define.h（ONERO_ERR_RAW_FRAME_*）
     */
    int send_can_frame(uint16_t can_id, const uint8_t* payload, uint8_t len);

    /**
     * @brief 注册接收回调；所有非保留 ID 的入站帧都会派发到 cb。
     *        重复调用会替换前一个回调；nullptr 等价于清除。
     */
    int register_can_frame_callback(CanFrameCallback cb);

    /**
     * @brief 清除已注册的接收回调。
     */
    int clear_can_frame_callback();

    /**
     * @brief 在 timeout_ms 内主动从 SLCAN 拉帧并 dispatch 到已注册回调。
     *        电机/夹爪帧仍走原解析路径。timeout_ms == 0 等价于一次非阻塞 try-recv。
     *        典型用法：在 movej 等运动控制空闲期主动调用，避免 SLCAN
     *        rx 缓冲区累积。
     */
    int pump_can_bus(int timeout_ms);

    /**
     * @brief 暴露底层 handle 给 C ABI / 其他内部桥接代码
     * @internal 用户代码不应使用
     */
    onero_robot_handle* native_handle() const { return handle_; }

private:
    onero_robot_handle* handle_ = nullptr;
    std::unique_ptr<OneroGripper> gripper_;
};

/**
 * @class OneroDragTeaching
 * @brief 拖动示教实例（C++ 公开入口，与 Python 同名同形）
 *
 * 构造时分配 drag teaching handle，析构时释放。方法名与 Python 完全一致；
 * 不再带 `drag_teaching_` 前缀（类名已经表达了这个子空间）。
 */
class ONERO_CPP_API OneroDragTeaching {
public:
    OneroDragTeaching();
    ~OneroDragTeaching();

    OneroDragTeaching(const OneroDragTeaching&) = delete;
    OneroDragTeaching& operator=(const OneroDragTeaching&) = delete;

    OneroDragTeaching(OneroDragTeaching&& other) noexcept;
    OneroDragTeaching& operator=(OneroDragTeaching&& other) noexcept;

    bool valid() const { return handle_ != nullptr; }

    bool initialize(int dof, const std::string& record_file, double time_step = 0.01);
    bool set_hardware(const std::string& device,
                      const std::string& urdf_path,
                      const std::string& robot_model,
                      const std::string& mount_orientation = "horizontal");
    bool set_hardware(const std::string& device,
                      const std::string& urdf_path,
                      const std::string& robot_model,
                      const std::string& mount_orientation,
                      bool with_gripper);
    int  enable_motors();
    int  restore_arm();
    int  restore_arm(const JointArray& target);
    int  start_recording();
    int  stop_recording();
    void set_replay_file(const std::string& replay_file);
    int  start_replay();
    int  stop_replay();

    /**
     * @brief 准备轨迹回放(只做文件 IO,不运动)
     *
     * 是 start_replay 三阶段拆分的第 1 步。打开回放文件、校验文件头、
     * 读取首个轨迹点并缓存。对应单臂 start_replay 的"开文件 + 读首点"部分。
     */
    int  prepare_replay();

    /**
     * @brief 把机械臂运动到首个轨迹点(阻塞)
     *
     * 必须先 prepare_replay。供双臂/N 臂调用方用 barrier 同步触发,
     * 让两侧同时启动回首点运动。
     */
    int  move_to_replay_start();

    /**
     * @brief 设置共享时间基准并进入 REPLAYING 相
     *
     * 必须先 prepare_replay + move_to_replay_start。多个实例使用同一 t0
     * 即可获得对齐的轨迹回放时间基准 — 这是双臂同步回放的关键。
     * @param t0 共享时间基准(steady_clock 时间点)
     */
    int  begin_replay(std::chrono::steady_clock::time_point t0);

    int  handle_command(int cmd);

    /**
     * @brief 双臂便利封装:cmd=0/1/2/3 一次性下发到两臂
     *
     * cmd=0/1/2 等价于两侧顺序 handle_command;cmd=3 走 prepare → move(barrier
     * 同步) → begin(共享 t0) 的三阶段流程,先 stop_recording 兜底。
     * @return 0 双侧成功;非零 = left 优先聚合的错误码
     */
    static int handle_command_dual(OneroDragTeaching& l, OneroDragTeaching& r, int cmd);

    void timer_callback();
    DragTeachingState get_state();
    bool is_initialized();
    void update_joint_state(const JointArray& position,
                            const JointArray& velocity,
                            const JointArray& effort);

    /**
     * @brief 暴露底层 handle 给 C ABI / 其他内部桥接代码
     * @internal 用户代码不应使用
     */
    onero_drag_teaching_handle* native_handle() const { return handle_; }

private:
    onero_drag_teaching_handle* handle_ = nullptr;
};

}  // namespace onero_api
