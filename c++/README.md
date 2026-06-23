# OneroArm C++ SDK

完整 C++ API（`namespace onero_api`）+ URDF/mesh 资源。三层公共面与返回值约定见仓库根 [`README.md`](../README.md)。

---

## 目录

- [OneroArm C++ SDK](#oneroarm-c-sdk)
  - [目录](#目录)
  - [一、目录结构](#一目录结构)
  - [二、集成方式](#二集成方式)
    - [2.1 选项 A：CMake 直接 IMPORTED](#21-选项-acmake-直接-imported)
    - [2.2 选项 B：纯命令行编译](#22-选项-b纯命令行编译)
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
    - [6.4 可选夹爪](#64-可选夹爪)
    - [6.5 缓冲与轨迹](#65-缓冲与轨迹)
    - [6.6 状态查询](#66-状态查询)
  - [七、`OneroDragTeaching` 详解](#七onerodragteaching-详解)
  - [八、完整示例](#八完整示例)
  - [九、CAN 帧示例](#九can-帧示例)
    - [9.1 方法签名](#91-方法签名)
    - [9.2 参数细节](#92-参数细节)
    - [9.3 完整示例](#93-完整示例)
  - [十、错误诊断](#十错误诊断)

---

## 一、目录结构

```
c++/
├── include/                                  # 跨 OS 共用，公开头扁平到顶层
│   ├── onero_define.h                        # 数据类型 / 常量 / 错误码
│   └── onero_interface_cpp.h                 # namespace onero_api 接口（含内联导出宏）
├── share/oneroarm_description/               # 跨 OS 共用 URDF / mesh
├── linux/
│   ├── linux-x86_64/liboneroarm.so
│   ├── linux-arm64/liboneroarm.so
│   └── linux-riscv64/liboneroarm.so
└── windows/
    └── windows-x86_64/{oneroarm.dll, oneroarm.lib}
```

如只需要纯 C ABI（`extern "C"`）头文件，请改用同级 [`c/`](../c/) 包；它去掉了
`onero_define.h` / `onero_interface_cpp.h`，仅保留 `onero_interface_c.h`，纯 C 工程可
`project(LANGUAGES C)` 集成。两包的 `liboneroarm.so` / `oneroarm.dll` 二进制完全相同。

---

## 二、集成方式


### 2.1 选项 A：CMake 直接 IMPORTED

```cmake
cmake_minimum_required(VERSION 3.15)
project(my_cpp_app LANGUAGES CXX)

set(ONERO_SDK ${CMAKE_CURRENT_SOURCE_DIR}/c++)
add_library(oneroarm SHARED IMPORTED)
set_target_properties(oneroarm PROPERTIES
    IMPORTED_LOCATION             ${ONERO_SDK}/linux/linux-x86_64/liboneroarm.so
    INTERFACE_INCLUDE_DIRECTORIES ${ONERO_SDK}/include
)

add_executable(my_cpp_app main.cpp)
target_link_libraries(my_cpp_app PRIVATE oneroarm)
```

Windows 把 `IMPORTED_LOCATION` 指向 `oneroarm.dll`，再加 `IMPORTED_IMPLIB`
指向 `oneroarm.lib`；Linux 按实际架构把子目录改成 `linux-x86_64`、`linux-arm64`
或 `linux-riscv64` 即可。RISC-V 示例：

```cmake
set(ONERO_SDK ${CMAKE_CURRENT_SOURCE_DIR}/c++)
add_library(oneroarm SHARED IMPORTED)
set_target_properties(oneroarm PROPERTIES
    IMPORTED_LOCATION             ${ONERO_SDK}/linux/linux-riscv64/liboneroarm.so
    INTERFACE_INCLUDE_DIRECTORIES ${ONERO_SDK}/include
)
```

### 2.2 选项 B：纯命令行编译

```bash
g++ main.cpp -std=c++17 -I c++/include -L c++/linux/linux-x86_64 -loneroarm \
    -Wl,-rpath,'$ORIGIN'/c++/linux/linux-x86_64 -o my_cpp_app
```

RISC-V 上把库目录替换为 `linux-riscv64`，并确保第三方运行时库在
`LD_LIBRARY_PATH` 中：

```bash
export ONERO_DEPS_PREFIX=/opt/onero-deps
export LD_LIBRARY_PATH="$ONERO_DEPS_PREFIX/lib:$PWD/c++/linux/linux-riscv64:$LD_LIBRARY_PATH"

g++ main.cpp -std=c++17 -I c++/include -L c++/linux/linux-riscv64 -loneroarm \
    -Wl,-rpath,'$ORIGIN'/c++/linux/linux-riscv64 \
    -Wl,-rpath-link,"$ONERO_DEPS_PREFIX/lib" \
    -o my_cpp_app

./my_cpp_app
```

---

## 三、运行时依赖

C++ 头声明引用 Eigen / pinocchio 等类型，但**最终二进制 `liboneroarm.so`**
已用 `-fvisibility=hidden` + `ONERO_CPP_API` 显式标注，外部链接表只暴露
`onero_api::*` 与纯 C ABI 符号。所以你只需要：

- **编译期**：把 `c++/include/` 加入 include path 即可；用户工程**不需要**
  `find_package(Eigen3 / pinocchio / hpp-fcl / Boost / OpenSSL)`。
- **运行期**：通过 ELF `DT_NEEDED` 拉起以下传递依赖：

| 运行时库 | 版本 |
|---|---|
| `libpinocchio_*` | `3.1.x` |
| `libhpp-fcl` | `2.4.x` |
| `liburdfdom_world` | `4.0.x` |
| `libboost_*` / `libcrypto` / `libstdc++` / `libgomp` | conda-forge 默认 |

最简便的方式是创建一个 `oneroarm_cpp` conda 环境一键拉齐：

```bash
conda create -n oneroarm_cpp -c conda-forge \
    cmake ninja compilers eigen boost pinocchio hpp-fcl urdfdom pkg-config -y
conda activate oneroarm_cpp
```

### RISC-V (linux-riscv64)：依赖须自行从源码准备

conda-forge **没有任何** riscv64 的 `pinocchio` / `hpp-fcl` / `urdfdom` 包，因此
riscv 上不能用上面的 conda 一键方案。你需要在 riscv64 机器上**自行从源码编译**这些
运行时依赖，并保证下表的**精确 SONAME** 出现在 `LD_LIBRARY_PATH`（或用
`-Wl,-rpath,'$ORIGIN'/c++/linux/linux-riscv64`）：

| 运行时库（SONAME） | 版本 | 获取方式（riscv64） |
|---|---|---|
| `libpinocchio_default.so.3.1.0` / `libpinocchio_parsers.so.3.1.0` | **3.1.0** | 源码编，`-DBUILD_WITH_COLLISION_SUPPORT=ON` |
| `libhpp-fcl.so` | **2.4.x** | 源码编 |
| `liburdfdom_world.so.4.0` | `4.0.x` | 发行版包 `liburdfdom-dev` 或源码 |
| `libcrypto.so.3` | openssl 3 | 发行版包 `libssl-dev` |
| `libgomp.so.1` / `libstdc++.so.6` | 系统默认 | 发行版自带 |

> ⚠ **版本须严格匹配**：`liboneroarm.so` 的 `DT_NEEDED` 写死了 `…so.3.1.0` 这样的
> 版本化 SONAME；pinocchio 必须恰好编 `v3.1.0`，否则动态加载器找不到而报
> `cannot open shared object` 或 `undefined symbol`。pinocchio 务必开启 collision
> 支持（对应 SDK 内部的 `PINOCCHIO_WITH_HPP_FCL`）。
>
> 随包提供的一次性安装脚本见仓库根目录 `scripts/install_riscv_dependencies.sh`
> （按序源码编 hpp-fcl 2.4.4 + pinocchio 3.1.0 到 `/opt/onero-deps`）。

RISC-V 用户侧最小安装 / 自检流程：

```bash
# 1. 准备第三方依赖。在 RISC-V 目标板进入仓库根目录执行：
cd /path/to/OneroArm_API_for_Users
sudo ./scripts/install_riscv_dependencies.sh

# 2. 加载依赖路径：
export LD_LIBRARY_PATH=/opt/onero-deps/lib:$LD_LIBRARY_PATH

# 3. 确认 liboneroarm.so 的传递依赖都能解析；正常情况下不应有 not found：
ldd c++/linux/linux-riscv64/liboneroarm.so | grep 'not found' || true
```

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
    uint8_t point_id;                 // 0x00 = total force
    double fx, fy, fz;                // N
    bool valid;
};

struct GripperTactileSensorStatus {
    uint8_t sensor_id;                // 0x01 / 0x02
    GripperTactileValue total_force;
    std::vector<GripperTactileValue> points; // empty until per-point feedback is enabled
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

### 6.3 运动控制

| 方法 | 参数 | 语义 |
|---|---|---|
| `movej(target, speed_scale=1.0, trajectory_connect=0)` | `target`：rad，长度 = `dof` | 关节空间梯形/S 形规划，不保证 TCP 直线 |
| `movel(pose, …)` | `pose` | 笛卡尔直线（位置控制） |
| `movep(pose, …)` | `pose` | 笛卡尔点到点平滑过渡，**不**保证中间路径直线 |
| `estimate_movej_duration(target, speed_scale=1.0)` | `target`：rad，长度 = `dof` | 只按 MoveJ 规划参数估算时长，不执行运动 |

通用参数：

- `speed_scale`：建议 `(0, 2.0]`，默认 `1.0`。
- `trajectory_connect`：`0` 立即执行；`1` 入缓冲队列。

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
| `g->get_tactile()` | – | `GripperTactileStatus` | 刷新并返回两个触摸传感器各自的合力快照 |

`GripperStatus` 字段（定义见 §5.2）：`position`（百分比）、`velocity`（百分比/s）、`force`（N，±40）、`error`（故障码）、`valid`。夹爪状态与故障码只属于夹爪域，不改变机械臂 `dof` 或关节状态缓存。

`GripperTactileStatus` 当前读取传感器 `0x01` 和 `0x02` 的合力点 `0x00`。`fx/fy` 按 `int8_t * 0.1N` 解析，`fz` 按 `uint8_t * 0.1N` 解析；`points` 当前为空，后续支持单点分力后填入测点数据。

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
| `send_trajectory_point(positions, velocities)` | 单点入缓冲 |
| `send_trajectory(trajectory)` | 一次性下发完整轨迹（位置+速度+加速度） |
| `execute_buffered_trajectory()` | 触发缓冲队列执行 |
| `clear_trajectory_buffer()` | 丢弃缓冲队列 |
| `reset_stop_signal()` | 清除前一次 stop/cancel/interruption 信号；新一轮运动前由用户层显式调用 |
| `cancel_trajectory()` | 异步终止当前运动 |

### 6.6 状态查询

| 方法 | 数据源 | 是否触发 CAN I/O | 适用场景 |
|---|---|:---:|---|
| `get_joint_positions()` | 上位机内部缓存 | 否 | 通用查询，最低开销 |
| `get_joint_positions_from_motors()` | 电机回读 |  | 与外部传感器对齐 |
| `get_joint_velocities()` | 电机回读 |  | 速度环 / 监督控制 |
| `get_arm_state_from_motor()` | 电机回读 |  | 一次性获取位置 + 速度 + 力矩 |
| `get_arm_state_cached()` | 控制循环缓存 | 否 | **推荐**用于 GUI / 数据采集线程的高频轮询 |
| `get_end_effector_pose()` | 实时状态 / 内部正运动学 | 可能 | 末端位姿读取 |
| `get_end_effector_pose_cached()` | 控制循环缓存 | 否 | 高频只读位姿查询；缓存无效时返回默认位姿 |
| `is_hardware_connected()` | 总线心跳 | 否 | 启动 / 故障检测 |

> 失败时 `JointArray` 为空、`Pose` 全零、`ArmStateFromMotor` 三个 vector 同时为空。调用方应通过 `vector::empty()` 防御。

---

## 七、`OneroDragTeaching` 详解

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

**典型调用流程**：

1. `OneroDragTeaching drag;` → `drag.initialize(dof, record_file, dt)` → `drag.set_hardware(...)`。
2. `drag.enable_motors()`；如需先回零，再显式调用 `drag.restore_arm()`。
3. 录制：`drag.start_recording()` → 物理拖动 → `drag.stop_recording()`。
4. 回放：`drag.set_replay_file(path)` → `drag.start_replay()` → 必要时 `drag.stop_replay()`。
5. 周期循环：在固定频率（如 100 Hz）调用 `drag.timer_callback()`，并将电机回读 `drag.update_joint_state(...)` 喂入。
6. 退出：作用域结束时实例自动析构。

**双臂同步命令**：

`OneroDragTeaching::handle_command_dual(left, right, cmd)` 接受两个已初始化并完成 `set_hardware(...)` 的拖动示教实例。`cmd=1` 会在 SDK 内部对两臂执行并发 prepare，并用共享 `t0` 同步开始录制；`cmd=3` 走同步回放路径；`cmd=0/2` 分别用于双臂停止、停止录制。调用方不需要自己计算或传入 `steady_clock` 时间点。

---

## 八、完整示例

最小运动序列（与 [`demo/arm_control_demo.cpp`](../demo/arm_control_demo.cpp) 同源）：

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

与电机 / 夹爪共用同一根 SLCAN 串口；可用于向同总线上的自定义节点发送 11-bit 标准 CAN 帧并接收响应。共同语义（保留 ID 集、回调线程、payload 生命周期、异常处理）见根 [`README.md`](../README.md) §7。

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
| 运行时 `undefined symbol: ZN10pinocchio…` | 传递依赖未安装；激活 `oneroarm_cpp` conda 环境 |
| Windows 缺失 DLL | 把 `c++/windows/windows-x86_64/oneroarm.dll` 与依赖的 `.dll` 加入 `PATH`，或与可执行文件同目录 |
| `OneroArm::valid() == false` | 底层 handle 创建失败：检查串口设备路径、波特率、URDF 资源；可加日志确认 |
| `enable_motors()` 返回 `-5 TIMEOUT` | 检查串口设备路径、波特率（默认 921600）、急停按钮；`is_hardware_connected()` 验证总线心跳 |
| 运动接口返回 `-7 JOINT_LIMIT_EXCEEDED` | 目标关节越过 SDK 内置/URDF 对齐后的限位；先检查目标角度与 `robot_model` 是否匹配 |
| 运动接口返回 `-8 BUSY` | 同一只臂已有运动命令在执行；等待结束或先 cancel，再 `reset_stop_signal()` 后发新命令 |
| `send_can_frame` 返回 `-12 RESERVED_ID` | `can_id` 落在保留集（电机 / 夹爪 / 触觉回包 / 操纵杆 / `0x7FF`） |
| 回调收不到帧 | 对端发送的 CAN ID 是否在 SDK 保留集；运动控制空闲期主动 `pump_can_bus(timeout_ms)` |
| 启动报 `Pinocchio model load failed` / 找不到 URDF | 默认走 SDK 内置 `share/oneroarm_description/`；若被覆盖可设 `ONERO_DESCRIPTION_PATH` 或 `cfg.model_description_path` |

> 急停集成：可设置 `cfg.interrupt_check` + `cfg.interrupt_ctx`，运动循环会逐周期回调；上层 GUI / 按钮 / Ctrl+C 拉低标志位即可中断当前 `move*` 调用。
