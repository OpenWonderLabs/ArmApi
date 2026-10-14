# OneroArm C++ SDK

Ubuntu 24.04 riscv64 的库位于 `linux/linux-riscv64/`，使用本包 RISC-V runtime；安装与示例命令见 [RISC-V 安装说明](../RISC_V_GUIDE.md)。

完整 C++ API（`namespace onero_api`）+ URDF/mesh 资源。三层公共面与返回值约定见仓库根 [`README.md`](../README.md)。

---

## 目录

- [OneroArm C++ SDK](#oneroarm-c-sdk)
  - [目录](#目录)
  - [一、目录结构](#一目录结构)
  - [二、集成方式](#二集成方式)
    - [2.1 CMake IMPORTED 目标](#21-cmake-imported-目标)
    - [2.2 Linux x86_64 命令行](#22-linux-x86_64-命令行)
  - [三、运行时依赖](#三运行时依赖)
  - [四、运行期资源定位](#四运行期资源定位)
  - [五、数据类型](#五数据类型)
    - [5.1 `onero_config_t`](#51-onero_config_t)
    - [5.2 数据结构](#52-数据结构)
    - [5.3 错误码常量](#53-错误码常量)
  - [六、`OneroArm` 详解](#六oneroarm-详解)
    - [6.1 生命周期](#61-生命周期)
    - [6.2 电机使能](#62-电机使能)
    - [6.3 运动控制](#63-运动控制)
    - [6.3.1 在线伺服与 Frame](#631-在线伺服与-frame)
    - [6.4 可选夹爪](#64-可选夹爪)
    - [6.5 缓冲与轨迹](#65-缓冲与轨迹)
    - [6.6 MIT 力位混合直接控制](#66-mit-力位混合直接控制)
    - [6.7 状态查询](#67-状态查询)
  - [七、`OneroDragTeaching` 详解](#七onerodragteaching-详解)
  - [八、完整示例](#八完整示例)
  - [九、CAN 帧示例](#九can-帧示例)
    - [9.1 方法签名](#91-方法签名)
    - [9.2 参数细节](#92-参数细节)
    - [9.3 完整示例](#93-完整示例)
  - [十、错误诊断](#十错误诊断)

---

## 一、目录结构

本 SDK 包提供 Linux x86_64、Linux arm64、Linux riscv64、Windows x86_64 四个平台的 C++ 库；RISC-V 当前仅完成 QEMU 离线验证。

| 目录 | 内容 |
|---|---|
| c++/include | onero_define.h、onero_interface_cpp.h，C++17 公共接口 |
| c++/linux/linux-x86_64 | liboneroarm.so |
| c++/linux/linux-arm64 | liboneroarm.so |
| c++/linux/linux-riscv64 | liboneroarm.so |
| c++/windows/windows-x86_64 | oneroarm.dll 与 oneroarm.lib |
| c++/share/oneroarm_description | URDF、mesh 等模型资源 |

同平台 c/ 与 c++/ 的动态库逐字节相同；区别是公开头。纯 C 工程请用同级的 [C 文档](../c/README.md)。

## 二、集成方式

### 2.1 CMake IMPORTED 目标

从本包根目录组织工程，以下示例为 Linux x86_64：

```cmake
cmake_minimum_required(VERSION 3.15)
project(my_cpp_app LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(ONERO_SDK /path/to/SDK/c++)
set(ONERO_DEPS /path/to/SDK/runtime/linux-x86_64/lib)
add_library(oneroarm SHARED IMPORTED)
set_target_properties(oneroarm PROPERTIES
  IMPORTED_LOCATION ${ONERO_SDK}/linux/linux-x86_64/liboneroarm.so
  INTERFACE_INCLUDE_DIRECTORIES ${ONERO_SDK}/include)
add_executable(my_cpp_app main.cpp)
target_link_libraries(my_cpp_app PRIVATE oneroarm "${ONERO_DEPS}/libstdc++.so.6")
target_link_directories(my_cpp_app BEFORE PRIVATE "${ONERO_DEPS}")
target_link_options(my_cpp_app PRIVATE "-Wl,-rpath-link,${ONERO_DEPS}")
set_property(TARGET my_cpp_app APPEND PROPERTY BUILD_RPATH "${ONERO_DEPS}")
```

Linux arm64 改为 linux/linux-arm64，并将 ONERO_DEPS 指向匹配 Conda 环境的 lib 目录。Linux C++ 消费者必须在链接期选用匹配的 libstdc++.so.6；仅设置运行时 LD_LIBRARY_PATH 不会改变编译器默认选用的系统旧 C++ 库。Windows 不使用上述 Linux libstdc++ 和链接选项；Windows x86_64 的 IMPORTED_LOCATION 指向 oneroarm.dll，并将 IMPORTED_IMPLIB 指向 oneroarm.lib；运行时还须让 Windows 能找到 DLL 及其传递依赖。完整可编译配置见 [demo/CMakeLists.txt](../demo/CMakeLists.txt)。

### 2.2 Linux x86_64 命令行

```bash
ONERO_DEPS="$PWD/runtime/linux-x86_64/lib"
g++ main.cpp -std=c++17 -I c++/include -L c++/linux/linux-x86_64 -loneroarm \
  "$ONERO_DEPS/libstdc++.so.6" -L"$ONERO_DEPS" -Wl,-rpath-link,"$ONERO_DEPS" \
  -Wl,-rpath,"$ONERO_DEPS" -Wl,-rpath,'$ORIGIN/c++/linux/linux-x86_64' -o my_cpp_app
```

本包的 Linux x86_64 传递库在 [runtime](../runtime/README.md) 中；运行前按该文档设置 LD_LIBRARY_PATH。arm64 和 Windows 应使用匹配的 Conda 环境或等价依赖集合。

## 三、运行时依赖

公共头不要求用户工程直接包含 Pinocchio 或 Coal 头；预编译动态库仍依赖相应运行库。本版本以 Pinocchio 3.8、Coal/hpp-fcl 3.0.1、urdfdom 4.0.1、Boost 1.88、OpenSSL 3 为依赖基线。详细清单以 [发布清单](../RELEASE_MANIFEST.json)、目标库依赖表及 [本地 Conda channel](../python/conda_channel/README.md) 为准。不能直接沿用旧版 Pinocchio 3.1、hpp-fcl 2.4 运行库说明。

---
## 四、运行期资源定位

`liboneroarm.so` 通过 `dladdr()` / `GetModuleFileNameW()` 取自身路径，
按以下三档候选探测 `share/oneroarm_description/`：

| 部署形态 | 探测路径 |
|---|---|
| Python wheel | `<libdir>/share/oneroarm_description/` |
| 系统 install | `<libdir>/../share/oneroarm_description/` |
| SDK 扁平形态 | `<libdir>/../../share/oneroarm_description/` |

第三档对应本包：`c++/linux/linux-x86_64/liboneroarm.so` →
`c++/share/oneroarm_description/`，无需任何环境变量。

也可通过环境变量 `ONERO_DESCRIPTION_PATH` / `ONERO_DESCRIPTION_DIR`
或 `onero_config_t::model_description_path` 显式覆盖；优先级由高到低：
`cfg` 字段 → 环境变量 → `dladdr` 自身路径推断 → CWD 相对回退 → ROS `AMENT_PREFIX_PATH`。

---

## 五、数据类型

`onero_interface_cpp.h` 自动 `#include "onero_define.h"`；用户代码只需 `#include "onero_interface_cpp.h"`。所有类型位于 `namespace onero_api`。

### 5.1 `onero_config_t`

```cpp
struct onero_config_t {
    char   device[256]              = "";          // 必填
    char   robot_model[64]          = "";          // 必填，"a1_l" / "a1_r"
    int    dof                      = 7;
    int    baud_rate                = 921600;
    char   urdf_path[512]           = "";          // 留空 -> 自动定位
    char   version[32]              = "";          // "A1"，留空时按 robot_model 推断
    char   mount_orientation[32]    = "vertical";  // "vertical" / "horizontal"
    double mit_kp[7]                = {0,0,0,0,0,0,0};   // == 0 视为未传入
    double mit_kd[7]                = {0,0,0,0,0,0,0};
    onero_interrupt_check_fn interrupt_check = nullptr;  // 运动循环回调；返回 true 中断
    void*  interrupt_ctx            = nullptr;
    char   model_description_path[512] = "";       // 留空 -> SDK 内置
    bool   with_gripper             = false;        // true 时复用同一总线注册可选夹爪
    bool   simulation_mode          = false;        // 无硬件仿真，不能替代真机验证
};
```

> 头文件给出默认值，`onero_api::onero_config_t cfg{};` 即安全。**字段顺序与 C ABI 不保证一致**（C ABI 由 `to_cpp_config` 按字段拷贝转换）。

**7-DOF 默认增益**（`mit_kp[i] == 0` 时自动注入）：

| 关节 | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| `kp` | 150 | 150 | 150 | 150 | 30 | 30 | 30 |
| `kd` | 4 | 4 | 4 | 4 | 1 | 1 | 1 |

### 5.2 数据结构

```cpp
namespace onero_api {

using JointArray = std::vector<double>;

struct Pose {
    double x, y, z;                 // 位置 (m)
    double qw, qx, qy, qz;          // 四元数（标量优先）
};

struct ArmStateFromMotor {
    JointArray positions;           // rad（含零位补偿）
    JointArray velocities;          // rad/s
    JointArray torques;             // N·m
};

struct GripperStatus {
    double position;                 // percent
    double velocity;                 // percent/s
    double force;                    // N, limited to +/-40
    uint8_t error;
    bool valid;
};

struct GripperTactileValue {
    uint8_t point_id;                 // 0x00 = total force, 0x01..0x09 = points
    double fx, fy, fz;                // N
    bool valid;
};

struct GripperTactileSensorStatus {
    uint8_t sensor_id;                // 0x01 / 0x02
    GripperTactileValue total_force;
    std::vector<GripperTactileValue> points; // 0x01..0x09
    bool valid;
};

struct GripperTactileStatus {
    std::array<GripperTactileSensorStatus, 2> sensors;
    bool valid;
};

struct TrajectoryPoint {
    JointArray position;
    JointArray velocity;
    JointArray acceleration;
};

enum class DragTeachingState : int { IDLE = 0, RECORDING = 1, REPLAYING = 2 };
enum class MoveResult        : int { SUCCESS = 0, INVALID_PARAMS = -1, IK_FAILED = -2,
                                     COLLISION_DETECTED = -3, EXECUTION_FAILED = -4, TIMEOUT = -5,
                                     INTERRUPTED = -6, JOINT_LIMIT_EXCEEDED = -7, BUSY = -8 };

using CanFrameCallback =
    std::function<void(uint16_t can_id, const uint8_t* payload, uint8_t len)>;

}  // namespace onero_api
```

### 5.3 错误码常量

```cpp
constexpr int ONERO_CAN_OK                       = 0;
constexpr int ONERO_ERR_RAW_FRAME_INVALID_LEN    = -10;  // payload > 8
constexpr int ONERO_ERR_RAW_FRAME_INVALID_ID     = -11;  // can_id 越过 11-bit
constexpr int ONERO_ERR_RAW_FRAME_RESERVED_ID    = -12;  // 命中保留集
constexpr int ONERO_ERR_RAW_FRAME_PORT_NOT_OPEN  = -13;
constexpr int ONERO_ERR_RAW_FRAME_SEND_FAILED    = -14;
```

---

## 六、`OneroArm` 详解

RAII 实例：构造时按 `onero_config_t` 创建底层 robot handle，析构时自动释放。
**禁拷贝**、可移动；moved-from 实例的 `valid()` 为 `false`，析构无副作用。

### 6.1 生命周期

```cpp
class OneroArm {
    explicit OneroArm(const onero_config_t& config);
    ~OneroArm();
    OneroArm(OneroArm&&) noexcept;
    bool valid() const;                      // false 表示底层 handle 创建失败
    bool has_gripper() const;
    OneroGripper* gripper();                 // nullptr when with_gripper=false
};
```

| 行为 | 说明 |
|---|---|
| 构造失败 | `valid() == false`；后续所有方法返回错误码。半构造的串口 / 电机 / URDF 资源在内部回滚 |
| 拷贝 | 禁用，避免双重释放 |
| 移动 | 源对象 handle 置 `nullptr`，析构 no-op |

### 6.2 电机使能

| 方法 | 返回 | 说明 |
|---|---|---|
| `enable_motors()` | `MoveResult` | 同步等待硬件应答；首次使能可能耗时秒级 |
| `disable_motors()` | `MoveResult` | 同步阻塞 |
| `restore_arm()` | `MoveResult` | 以安全速度恢复默认零位；与 `enable_motors()` 解耦，需调用方显式触发 |
| `restore_arm(target)` | `MoveResult` | 以安全速度恢复到指定关节目标；`target.size()` 应等于 `dof` |

restore_arm_concurrent 提供多臂并发恢复：传 OneroArm* 列表时各臂回默认零位，传 RestoreTarget 列表时可分别指定关节目标。返回 0 表示全部成功，失败按任务顺序聚合。它同步进入各臂 SDK 调用，不承诺多臂轨迹硬实时同步；任一侧失败不自动中断另一侧。

### 6.3 运动控制

| 方法 | 参数 | 语义 |
|---|---|---|
| `movej(target, speed_scale=1.0, trajectory_connect=0)` | `target`：rad，长度 = `dof` | 关节空间梯形/S 形规划，不保证 TCP 直线 |
| `movel(pose, …)` | `pose` | 笛卡尔直线（位置控制） |
| `movep(pose, …)` | `pose` | 笛卡尔点到点平滑过渡，**不**保证中间路径直线 |
| `movec(via_pose, target_pose, speed_scale=1.0, trajectory_connect=0)` | 两个绝对 base_T_link7 位姿 | 从新鲜反馈起点经 via 沿圆弧到 target；不支持整圆或缓冲模式 |
| `estimate_movej_duration(target, speed_scale=1.0)` | `target`：rad，长度 = `dof` | 只按 MoveJ 规划参数估算时长，不执行运动 |

通用参数：

- speed_scale 默认 1.0，实际运动受 SDK 参数校验、规划和模型硬限制约束。
- trajectory_connect：MoveJ/L/P 的 0 立即执行、1 入规划缓冲；MoveC 仅支持 0。

### 6.3.1 在线伺服与 Frame

| 方法 | 输入 | 返回与效果 |
|---|---|---|
| start_servoj(limits) | JointServoLimits 逐轴速度、加速度、加加速度上限；空数组使用 SDK 限制 | 启动 100 Hz 关节伺服 |
| servoj(target_q, target_dq={}, valid_for_seconds=0.10) | dof 维关节角、可选关节速度、有效期 | 0 表示接受最新目标，不表示到位；过期后受控减速 |
| get_servoj_status() / stop_servoj() | 无 | 查询序号、命令年龄、计数器、限制标志；受控停止 |
| start_servop() | 无 | 启动笛卡尔在线伺服 |
| servop(pose, limits) | 绝对 base_T_link7 位姿与四个正且有限的线/角速度、加速度上限 | 0 表示接受目标；SDK 与自身硬限制取交集 |
| get_servop_status() / stop_servop() | 无 | 查询请求/有效限制、实际/目标位姿、标志；受控停止 |

ServoP v1 控制 Link7/flange 原点，不自动施加 TCP 偏移。ServoJ 的 valid_for_seconds 必须是有限值且位于 (0,10]。ServoJ limit_flags 中 8 是 OTG_INFEASIBLE（轨迹生成不可行），不能仅据此认定加速度过大。accepted_sequence 与 applied_sequence 可用于辨别目标是否进入控制周期。

Frame 的 transform_pose、apply_cartesian_delta、flange_pose_to_tool、tool_pose_to_flange 是纯计算函数。FrameSnapshot 持有世界标定与 flange 到 TCP 的变换；WORLD 请求缺少标定时失败，TOOL 换算需要当前 base_from_tool 锚点。位置单位 m，四元数顺序 qw,qx,qy,qz。参见 [Frame 示例](../demo/cpp/frame_demo.cpp)。

状态的 limit_flags 为位掩码，可同时包含多种标志：

| ServoJ 数值 | 含义 | ServoP 数值 | 含义 |
|---:|---|---:|---|
| 1 | COMMAND_TIMEOUT | 1 | CARTESIAN_VELOCITY |
| 2 | FEEDBACK_STALE | 2 | CARTESIAN_ACCELERATION |
| 4 | JOINT_POSITION | 4 | JOINT_POSITION |
| 8 | OTG_INFEASIBLE | 8 | JOINT_VELOCITY |
| 16 | DEADLINE_MISS | 16 | JOINT_ACCELERATION |
| — | — | 32 | SINGULARITY |
| — | — | 64 | COMMAND_TIMEOUT |
| — | — | 128 | FEEDBACK_STALE |

状态不止表示到位情况，还包含命令过期、反馈、限制和控制周期信息。ServoJStatus 的 target_q 与 commanded_q/dq/ddq 分别为目标与下发值；ServoPStatus 的 target_pose 与 actual_pose 为目标与实际位姿。

### 6.4 可选夹爪

选配，默认关闭。`cfg.with_gripper = true` 时，`arm.gripper()` 返回 arm-owned 夹爪控制器；默认不开启时返回 `nullptr`。夹爪随臂初始化、复用 `OneroArm` 的同一串口 / CAN 会话（固定 CAN ID `0x08/0x18`），不单独打开设备；`enable_motors()` 只使能机械臂关节，夹爪需显式 `arm.gripper()->enable()`。

随臂初始化：

```cpp
onero_config_t cfg{};
cfg.with_gripper = true;          // 选配：开启 arm-owned 夹爪
OneroArm arm(cfg);
OneroGripper* g = arm.gripper();  // with_gripper=false 时为 nullptr
```

| 方法 | 参数 | 返回 | 语义 |
|---|---|---|---|
| `arm.has_gripper()` | – | `bool` | 是否随臂创建了夹爪控制器 |
| `arm.gripper()` | – | `OneroGripper*` | 夹爪控制器；`with_gripper=false` 时为 `nullptr` |
| `g->valid()` | – | `bool` | 控制器是否绑定到有效 handle |
| `g->enable()` / `g->disable()` | – | `MoveResult` | 使能 / 失能夹爪电机（固定 ID `0x08/0x18`，与 `enable_motors()` 解耦） |
| `g->set_position(percent)` | `percent`：`0..100%` | `MoveResult` | 单帧位置保持 |
| `g->move_position(percent, max_vel=100.0, max_acc=250.0, max_jerk=1000.0)` | `percent`：`0..100%`；速度 / 加速度 / 加加速度上限 | `MoveResult` | 100 Hz 点到点 S 曲线规划 |
| `g->force_control(torque)` | `torque`：N | `MoveResult` | 下发夹爪 MIT 力矩，内部钳位 ±40 N |
| `g->status()` | – | `GripperStatus` | 刷新并返回夹爪状态 |
| `g->get_tactile()` | – | `GripperTactileStatus` | 刷新并返回两个触摸传感器各自的合力与 9 个测点快照 |

`GripperStatus` 字段（定义见 §5.2）：`position`（百分比）、`velocity`（百分比/s）、`force`（N，±40）、`error`（故障码）、`valid`。夹爪状态与故障码只属于夹爪域，不改变机械臂 `dof` 或关节状态缓存。

`GripperTactileStatus` 当前读取传感器 `0x01` 和 `0x02` 的 `0x00..0x09`：`0x00` 写入 `total_force`，`0x01..0x09` 写入 `points`。`fx/fy` 按 `int8_t * 0.1N` 解析，`fz` 按 `uint8_t * 0.1N` 解析。

```cpp
onero_config_t cfg{};
cfg.with_gripper = true;
OneroArm arm(cfg);

if (auto* g = arm.gripper()) {
    g->enable();
    g->set_position(50.0);
    g->move_position(80.0, 100.0, 250.0, 1000.0);
    g->force_control(30.0); // gripper force/torque command is limited to +/-40 N
    GripperStatus st = g->status();
    GripperTactileStatus tactile = g->get_tactile();
}
```

### 6.5 缓冲与轨迹

| 方法 | 参数 |
|---|---|
| `send_trajectory_point(positions, velocities)` | 直接下发一个关节轨迹点，不进入 trajectory_connect 缓冲 |
| `send_trajectory(trajectory)` | 一次性下发完整轨迹（位置+速度+加速度） |
| `execute_buffered_trajectory()` | 触发缓冲队列执行 |
| `clear_trajectory_buffer()` | 丢弃缓冲队列 |
| `reset_stop_signal()` | 清除前一次 stop/cancel/interruption 信号；新一轮运动前由用户层显式调用 |
| `cancel_trajectory()` | 请求取消 Move/轨迹或 ServoP；`0` 仅表示已请求；活动 ServoJ 返回 `-8`，使用 `stop_servoj()` |

get_last_buffered_trajectory_failure() 返回最近的缓冲执行失败信息：valid、type、index、error_code，用于定位失败段。此方法是当前 C++ 公共入口，不能假设所有语言绑定都有对应方法。

### 6.6 MIT 力位混合直接控制

低层力位混合（阻抗）接口，用于 teleop 数据采集、阻抗控制、模仿学习推断等。控制律由电机在 MIT 模式下闭环执行：`tau_motor = kp*(q - q_act) + kd*(dq - dq_act) + tau`。

调用前必须先 `enable_motors()`；所有 `JointArray` 长度必须等于 `dof`。**不要**与 `movej/movel/movep/movec` 或 ServoJ/P 在重叠时间窗内混用（共用同一根 SLCAN 链路），并需以 ≥100 Hz 持续下发。

| 方法 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `control_mit(kp, kd, q, dq, tau)` | 五个 `JointArray`，长度 = `dof` | `int` | 整臂 MIT 力位混合控制（每帧一次）。`0` 成功 / `-1` 参数错误 / `-2` 硬件未初始化 / `-3` 至少一关节 CAN 写入失败 |
| `compute_gravity_torque(q, out_tau)` | `q`（输入 `JointArray`）/ `out_tau`（输出 `JointArray&`） | `int` | 计算重力补偿力矩（含 `robot_model` 校准缩放），喂给 `control_mit` 的 `tau`。`0` 成功 / `-1` `q` 长度错误 / `-2` 动力学模型未就绪 |

> `q` 走与 `get_arm_state_from_motor()` 一致的 SDK 关节空间。建议第一帧取 `q = 当前回读位置、dq = 0、tau = 0`，避免 `kp` 较大时产生瞬间力矩冲击。

### 6.7 状态查询

| 方法 | 数据源 | 是否触发 CAN I/O | 适用场景 |
|---|---|:---:|---|
| `get_joint_positions()` | 整臂实时状态查询 | 可能 | 需要刷新关节位置时使用 |
| `get_joint_positions_from_motors()` | 电机回读 | 可能 | 与外部传感器对齐 |
| `get_joint_velocities()` | 电机回读 | 可能 | 速度环 / 监督控制 |
| `get_arm_state_from_motor()` | 电机回读 | 可能 | 一次性获取位置 + 速度 + 力矩 |
| `get_arm_state_cached()` | 控制循环缓存 | 否 | **推荐**用于 GUI / 数据采集线程的高频轮询 |
| `get_end_effector_pose()` | 实时状态 / 内部正运动学 | 可能 | 末端位姿读取 |
| `get_end_effector_pose_cached()` | 控制循环缓存 | 否 | 高频只读位姿查询；缓存无效时返回默认位姿 |
| `is_hardware_connected()` | 总线心跳 | 否 | 启动 / 故障检测 |

> 失败时 `JointArray` 为空、位姿可能回退为零位置与单位四元数、`ArmStateFromMotor` 三个 vector 同时为空。调用方应通过 `vector::empty()` 防御。

---

## 七、`OneroDragTeaching` 详解

record_file 与 replay_file 使用不含 .. 的相对路径，例如 teach.bin；Linux 绝对路径会被 SDK 拒绝。录制文件是 SDK 二进制轨迹格式，不能按 CSV 文本解析。


```cpp
class OneroDragTeaching {
    OneroDragTeaching();
    ~OneroDragTeaching();
    OneroDragTeaching(OneroDragTeaching&&) noexcept;
    bool valid() const;
};
```

| 方法 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `initialize(dof, record_file, time_step=0.01)` | – | `bool` | 配置 dof / 输出文件 / 采样步长（100 Hz 默认） |
| `set_hardware(device, urdf_path, robot_model, mount_orientation="horizontal")` | – | `bool` | 绑定硬件；`mount_orientation` 必须与实际安装姿态一致 |
| `set_hardware(device, urdf_path, robot_model, mount_orientation, with_gripper)` | – | `bool` | 同上重载，额外用 `with_gripper` 选择匹配的重力补偿缩放与共享夹爪会话；不会自动开启夹爪录制（此重载下 `mount_orientation` 需显式给出） |
| `enable_motors()` | – | `MoveResult` | 使能电机，不带运动副作用 |
| `restore_arm()` | – | `MoveResult` | 以安全速度恢复默认零位 |
| `restore_arm(target)` | `target`：rad，长度 = `dof` | `MoveResult` | 以安全速度恢复到指定关节目标 |
| `start_recording()` / `stop_recording()` | – | `int` | 开始/停止录制并落盘 |
| `set_replay_file(replay_file)` | – | – | 选择回放文件 |
| `start_replay()` / `stop_replay()` | – | `int` | 开始/停止回放 |
| `handle_command(cmd)` | UI 命令码 | `int` | 转发到状态机 |
| `OneroDragTeaching::handle_command_dual(left, right, cmd)` | 两个实例引用 + UI 命令码 | `int` | 对两个拖动示教实例执行同步双臂命令 |
| `timer_callback()` | – | – | 周期 tick（推荐 100 Hz） |
| `get_state()` | – | `DragTeachingState` | 失败回退为 `IDLE` |
| `is_initialized()` | – | `bool` | – |
| `update_joint_state(position, velocity, effort)` | – | – | 喂入电机回读 |

带夹爪录制需先设置 with_gripper=true，再在录制前调用 set_gripper_teaching_mode。DISABLED 使用臂单独 V1 格式；POSITION 用 set_gripper_target(0..100) 记录目标；BACKDRIVE 以零力矩手动开合并记录反馈，V2 文件保存夹爪通道。回放 V2 自动处理该通道。get_gripper_status 的 valid=false 不可当作有效测量。夹爪不计入 arm dof。

**典型调用流程**：

1. `OneroDragTeaching drag;` → `drag.initialize(dof, record_file, dt)` → `drag.set_hardware(...)`。
2. `drag.enable_motors()`；如需先回零，再显式调用 `drag.restore_arm()`。
3. 录制：`drag.start_recording()` → 物理拖动 → `drag.stop_recording()`。
4. 回放：`drag.set_replay_file(path)` → `drag.start_replay()` → 必要时 `drag.stop_replay()`。
5. 周期循环：在固定频率（如 100 Hz）调用 `drag.timer_callback()`，并将电机回读 `drag.update_joint_state(...)` 喂入。
6. 退出：作用域结束时实例自动析构。

C++ 可分三阶段组织多臂回放：prepare_replay() 只读文件并准备首点；move_to_replay_start() 阻塞运动到首点；begin_replay(t0) 使用共享 steady_clock 时间点开始回放。各阶段失败时应停止后续步骤。单臂可继续使用 start_replay()，双臂可使用下述便利封装。

**双臂同步命令**：

`OneroDragTeaching::handle_command_dual(left, right, cmd)` 接受两个已初始化并完成 `set_hardware(...)` 的拖动示教实例。`cmd=1` 会在 SDK 内部对两臂执行并发 prepare，并用共享 `t0` 同步开始录制；`cmd=3` 走同步回放路径；`cmd=0/2` 分别用于双臂停止、停止录制。调用方不需要自己计算或传入 `steady_clock` 时间点。

---

## 八、完整示例

最小运动序列（参见 [`demo/cpp/movej_demo.cpp`](../demo/cpp/movej_demo.cpp) 同源）：

```cpp
#include "onero_interface_cpp.h"
#include <cstring>
#include <iostream>

using namespace onero_api;

int main() {
    onero_config_t cfg{};
    std::strcpy(cfg.device,      "/dev/ttyACM0");
    std::strcpy(cfg.robot_model, "a1_r");
    std::strcpy(cfg.version,     "A1");
    cfg.dof = 7;

    OneroArm arm(cfg);
    if (!arm.valid()) {
        std::cerr << "OneroArm construction failed\n";
        return 1;
    }

    if (arm.enable_motors() != 0) {
        return 2;                                   // 析构会自动释放底层 handle
    }

    JointArray home(7, 0.0);
    arm.movej(home, /*speed_scale=*/0.5);

    Pose target{0.30, 0.00, 0.40, /*qw=*/1.0, 0.0, 0.0, 0.0};
    arm.movel(target, 0.5);

    auto state = arm.get_arm_state_cached();
    if (!state.positions.empty()) {
        std::cout << "q[0]=" << state.positions[0] << '\n';
    }

    arm.disable_motors();
    return 0;                                       // OneroArm 析构自动释放
}
```

---

## 九、CAN 帧示例

与电机 / 夹爪共用同一根 SLCAN 串口；可用于向同总线上的自定义节点发送 11-bit 标准 CAN 帧并接收响应。用户帧回调由独立 dispatcher worker 派发；外部 replace/clear 等待旧代在执行的回调结束。共同语义（保留 ID 集、回调线程、payload 生命周期、异常处理）见根 [`README.md`](../README.md#五原始-can-帧行为)。

### 9.1 方法签名

```cpp
namespace onero_api {

using CanFrameCallback =
    std::function<void(uint16_t can_id, const uint8_t* payload, uint8_t len)>;

class OneroArm {
public:
    int send_can_frame             (uint16_t can_id,
                                    const uint8_t* payload, uint8_t len);
    int register_can_frame_callback(CanFrameCallback cb);
    int clear_can_frame_callback   ();
    int pump_can_bus               (int timeout_ms);
};

}  // namespace onero_api
```

### 9.2 参数细节

| 方法 | 参数约束 / 行为 |
|---|---|
| `send_can_frame` | `can_id` ∈ `[0x000, 0x7FF]`，**不能**落在保留集（含 arm 电机、夹爪 `0x08/0x18`、触觉回包 `0x418`、`0x7FF`）；`payload`（`len==0` 可为 `nullptr`）；`len ≤ 8`。同步发送，返回时 payload 已被拷贝 |
| `register_can_frame_callback` | 重复注册替换前一个；传入空 `std::function` 等价于 `clear_can_frame_callback()` |
| `pump_can_bus` | `timeout_ms == 0` = 一次非阻塞 try-recv；典型用法是在 `movej` 等运动控制空闲期主动调用，避免 SLCAN rx 缓冲累积 |

### 9.3 完整示例

```cpp
#include "onero_interface_cpp.h"
#include <cstdio>
#include <cstring>

using namespace onero_api;

int main() {
    onero_config_t cfg{};
    std::strcpy(cfg.device,      "/dev/ttyACM0");
    std::strcpy(cfg.robot_model, "a1_r");
    cfg.dof = 7;

    OneroArm arm(cfg);
    if (!arm.valid()) return 1;

    arm.register_can_frame_callback(
        [](uint16_t id, const uint8_t* d, uint8_t n) {
            std::printf("rx id=0x%X len=%u\n", id, n);
            for (uint8_t i = 0; i < n; ++i) std::printf(" %02X", d[i]);
            std::putchar('\n');
        });

    uint8_t payload[4] = {0x01, 0x02, 0x03, 0x04};
    int rc = arm.send_can_frame(0x100, payload, 4);    // 0 = 成功
    if (rc != 0) std::fprintf(stderr, "send failed: %d\n", rc);

    arm.pump_can_bus(50);                              // 50 ms 内派发到回调
    arm.clear_can_frame_callback();
    return 0;
}
```

---

## 十、错误诊断

| 现象 | 原因 / 处理 |
|---|---|
| 编译器找不到 `onero_interface_cpp.h` 或 `onero_define.h` | 把 `c++/include` 加入 include path |
| 编译时 Boost / Eigen / pinocchio / hpp-fcl 找不到 | 公共头**不需要**这些依赖；若用户工程别的代码也用了 pinocchio，确保在 conda env 内编译，避免与系统 ROS Boost / pinocchio 混链 |
| 链接时 `cannot find -loneroarm` | `-L c++/linux/<arch>` 路径不对；Windows 下需指 `IMPORTED_IMPLIB` 到 `oneroarm.lib` |
| 运行时 `cannot open shared object liboneroarm.so` | `LD_LIBRARY_PATH` 未包含库目录；推荐 `-Wl,-rpath,'$ORIGIN'/c++/linux/<arch>` |
| 运行时 `undefined symbol: ZN10pinocchio…` | 传递依赖未安装；按本文件运行时依赖说明配齐环境 |
| Windows 缺失 DLL | 把 `c++/windows/windows-x86_64/oneroarm.dll` 与依赖的 `.dll` 加入 `PATH`，或与可执行文件同目录 |
| `OneroArm::valid() == false` | 底层 handle 创建失败：检查串口设备路径、波特率、URDF 资源；可加日志确认 |
| `enable_motors()` 返回 `-5 TIMEOUT` | 检查串口设备路径、波特率（默认 921600）、急停按钮；`is_hardware_connected()` 验证总线心跳 |
| 运动接口返回 `-7 JOINT_LIMIT_EXCEEDED` | 目标关节越过 SDK 内置/URDF 对齐后的限位；先检查目标角度与 `robot_model` 是否匹配 |
| 运动接口返回 `-8 BUSY` | 同一只臂已有运动命令在执行；等待结束；ServoJ 先用专用 stop，其他运动先 cancel 并确认停止，再 `reset_stop_signal()` 后发新命令 |
| `send_can_frame` 返回 `-12 RESERVED_ID` | `can_id` 落在保留集（电机 / 夹爪 / 触觉回包 / 操纵杆 / `0x7FF`） |
| 回调收不到帧 | 对端发送的 CAN ID 是否在 SDK 保留集；运动控制空闲期主动 `pump_can_bus(timeout_ms)` |
| 启动报 `Pinocchio model load failed` / 找不到 URDF | 默认走 SDK 内置 `share/oneroarm_description/`；若被覆盖可设 `ONERO_DESCRIPTION_PATH` 或 `cfg.model_description_path` |

> 急停集成：可设置 `cfg.interrupt_check` + `cfg.interrupt_ctx`，运动循环会逐周期回调；上层 GUI / 按钮 / Ctrl+C 拉低标志位即可中断当前 `move*` 调用。


## ServoJ 运动中停止与通用取消

ServoJ 停止从当前连续指令位置、速度和加速度规划限加加速度制动，允许沿运动方向到达可制动的停止位置，不回到停止请求时的位置。`stop_servoj()` 阻塞等待受控制动及终拍完成；成功返回 `0` 后状态为 IDLE、命令速度和加速度为零、机械臂命令资源已释放；制动故障返回负错误码。停止时长取决于当时速度、加速度以及用户限制与 SDK 硬限制的交集，没有固定的通用毫秒承诺。

通用取消只请求取消 MoveJ/L/P/C、轨迹执行或 ServoP；返回 `0` 表示请求已记录，不表示运动已经停止，无活动运动时也返回 `0`。ServoJ 会话活动期间（含 RUNNING、BRAKING、HOLDING）返回 `-8 BUSY`，不设置取消信号、不改变该会话；必须调用专用 `stop_servoj()` / `onero_stop_servoj()`。

## ServoJ 运动中更新目标

每个 10 ms 控制周期读取最新有效目标；同周期多次更新覆盖旧目标，不排队逐点执行。运动中换目标时，从上一拍连续指令的 q/dq/ddq 重新规划到新目标，不要求先完成旧目标；刷新相同目标只续期，不重复规划。

当前跟踪使用静态集成的 Ruckig Community 0.15.3，保留 SDK 的速度、加速度、jerk 限制；使用前检查完整规划路径及制动包络的关节限位，每拍继续检查。无需额外安装 Ruckig 或联网。可行的前向换目标用例不再出现原先约 1 rad 的异常超调；换近目标或反向时，惯性和动态限制仍可能要求先制动一段距离。

`servoj()` 返回 `0` 表示接受目标。零目标速度的轨迹完成后进入 HOLDING；非零目标速度到达目标后仍处于 RUNNING，延续末速度，直至新目标、有效期到期或专用停止。规划路径或制动包络越界时，状态包含 JOINT_POSITION，`last_error=-7`，不会下发该候选路径；其他规划不可行仍报告 OTG_INFEASIBLE。请持续查询状态和反馈。

ServoJ 的 `limit_flags` 保留当前会话的累计事件。发生命令超时后，即使新目标已恢复跟踪，`COMMAND_TIMEOUT` 仍可能保留；应联合当前 `state`、`command_age_s`、序号和 `last_error` 判断。成功专用停止清除该标志；它不是新的停止请求。
