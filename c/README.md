# OneroArm 纯 C ABI 包

Ubuntu 24.04 riscv64 的库位于 `linux/linux-riscv64/`，安装与依赖见 [RISC-V 安装说明](../RISC_V_GUIDE.md)。

预编译 `liboneroarm.so` / `oneroarm.dll` + 纯 C 接口头文件 + URDF/mesh 资源。
适用于 C 工程或其他语言的 FFI 绑定（Rust / Go / C# 等）。三层公共面与返回值约定见仓库根 [`README.md`](../README.md)。

---

## 目录

- [一、目录结构](#一目录结构)
- [二、集成方式](#二集成方式)
- [三、运行时依赖](#三运行时依赖)
- [四、运行期资源定位](#四运行期资源定位)
- [五、数据类型](#五数据类型)
- [六、API 详解](#六api-详解)
- [七、完整示例](#七完整示例)
- [八、CAN 帧示例](#八can-帧示例)
- [九、错误诊断](#九错误诊断)
- [十、新增运动与坐标接口](#十新增运动与坐标接口)

---

## 一、目录结构

~~~text
c/
├── include/onero_interface_c.h               自含的纯 C ABI 头文件
├── share/oneroarm_description/                A1 左右臂 URDF、SRDF、xacro、mesh
├── linux/linux-x86_64/liboneroarm.so
├── linux/linux-arm64/liboneroarm.so
├── linux/linux-riscv64/liboneroarm.so
└── windows/windows-x86_64/{oneroarm.dll,oneroarm.lib}
~~~

同平台的 c/ 与 c++/ 动态库逐字节相同；C 包不含 C++ 的 onero_define.h、onero_interface_cpp.h。独立夹爪包在 [gripper/c/](../gripper/c/README.md)。

## 二、集成方式

### 2.1 CMake IMPORTED 目标

在仓库根目录建立纯 C 工程时，可直接指向交付库和头文件：

~~~cmake
cmake_minimum_required(VERSION 3.15)
project(my_c_app LANGUAGES C)
set(ONERO_SDK /path/to/SDK/c)
set(ONERO_DEPS /path/to/SDK/runtime/linux-x86_64/lib)
add_library(oneroarm SHARED IMPORTED)
set_target_properties(oneroarm PROPERTIES
  IMPORTED_LOCATION "${ONERO_SDK}/linux/linux-x86_64/liboneroarm.so"
  INTERFACE_INCLUDE_DIRECTORIES "${ONERO_SDK}/include")
add_executable(my_c_app main.c)
target_link_libraries(my_c_app PRIVATE oneroarm)
target_link_options(my_c_app PRIVATE "-Wl,-rpath-link,${ONERO_DEPS}")
set_property(TARGET my_c_app APPEND PROPERTY BUILD_RPATH "${ONERO_DEPS}")
~~~

Linux arm64 把库子目录换成 linux-arm64，ONERO_DEPS 指向匹配 Conda 环境的 lib 目录；Windows 不使用上述 Linux 链接选项。Windows x86_64 把 IMPORTED_LOCATION 指向 oneroarm.dll，并设置 IMPORTED_IMPLIB 为 oneroarm.lib。完整的平台选择见 [demo/CMakeLists.txt](../demo/CMakeLists.txt)。

### 2.2 Linux x86_64 命令行

~~~bash
ONERO_DEPS="$PWD/runtime/linux-x86_64/lib"
cc -std=c11 main.c -Ic/include -Lc/linux/linux-x86_64 -loneroarm \
  -Wl,-rpath-link,"$ONERO_DEPS" -Wl,-rpath,"$ONERO_DEPS" \
  -Wl,-rpath,"$PWD/c/linux/linux-x86_64" -o my_c_app
export LD_LIBRARY_PATH="$PWD/runtime/linux-x86_64/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
./my_c_app
~~~

上面的 LD_LIBRARY_PATH 用于解析 Pinocchio 等传递依赖；只在可执行文件里设置 liboneroarm.so 的 RPATH 不够。运行程序前仍需配好真实设备和模型。Linux arm64 推荐在匹配的 Conda 环境内提供运行依赖。Windows 用 MSVC 链接 .lib，并把 DLL 与 Conda 环境的 Library/bin 加入 DLL 搜索路径。

## 三、运行时依赖

本版本采用 Pinocchio 3.8、Coal/hpp-fcl 3.0.1、urdfdom 4.0.1、Boost 1.88、OpenSSL 3 等运行库；完整清单以 [发布清单](../RELEASE_MANIFEST.json)和所用平台动态库的依赖表为准。Linux x86_64 提供 [runtime/](../runtime/README.md)；Linux arm64、Windows 使用对应本地 Conda channel 与 conda-forge/robostack-staging 的依赖。不能把早期 Pinocchio 3.1、hpp-fcl 2.4 安装说明直接用于本版本。

## 四、运行期资源定位

`liboneroarm.so` 通过 `dladdr()` / `GetModuleFileNameW()` 取自身路径，
按以下三档候选探测 `share/oneroarm_description/`：

| 部署形态 | 探测路径 |
|---|---|
| Python wheel | `<libdir>/share/oneroarm_description/` |
| 系统 install | `<libdir>/../share/oneroarm_description/` |
| SDK 扁平形态 | `<libdir>/../../share/oneroarm_description/` |

第三档对应本包：`c/linux/linux-x86_64/liboneroarm.so` →
`c/share/oneroarm_description/`，无需任何环境变量。

URDF/mesh 资源根目录解析优先级（命中即停）：

1. `cfg.model_description_path`（非空时直接使用）
2. 环境变量 `ONERO_DESCRIPTION_PATH` / `ONERO_DESCRIPTION_DIR`
3. `dladdr` / `GetModuleFileNameW` 自身路径推断（上表）
4. CWD 相对回退（兼容历史脚本）
5. ROS / `AMENT_PREFIX_PATH` 各 `share/oneroarm_description/urdf/<version>/`

命中后会进一步定位 `urdf/<version>/`。**默认情形**（留空 + 不设环境变量）即可命中第 3 步的 SDK 内置资源；仅在切换到自定义 / 调试用 URDF 时才显式覆盖。

---

## 五、数据类型

定义在 [`include/onero_interface_c.h`](include/onero_interface_c.h)，所有结构体均为 POD。

### 5.1 `onero_config_t`

```c
typedef struct {
    char   device[256];                 // 必填，串口路径
    char   robot_model[64];             // 必填，"a1_l" / "a1_r"
    int    dof;                         // 7
    int    baud_rate;                   // 默认 921600
    char   urdf_path[512];              // 留空 -> 由 model_description_path + version 自动定位
    char   version[32];                 // "A1"，留空时按 robot_model 推断
    char   mount_orientation[32];       // "vertical"（默认）或 "horizontal"
    char   model_description_path[512]; // 留空 -> SDK 内置 share/oneroarm_description
    double mit_kp[7];                   // == 0 视为该关节未传入，按 dof 注入默认增益
    double mit_kd[7];                   // 同上
    bool   with_gripper;                // true 时复用同一总线注册可选夹爪
} onero_config_t;
```

> **务必零初始化**：`onero_config_t cfg = {0};` 或 `memset(&cfg, 0, sizeof cfg);`，否则栈上随机数据会被误判为「用户传入的非 0 PD 增益」。

**7-DOF 默认增益**（`mit_kp[i] == 0` 时自动注入）：

| 关节 | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| `kp` | 150 | 150 | 150 | 150 | 30 | 30 | 30 |
| `kd` | 4 | 4 | 4 | 4 | 1 | 1 | 1 |

**robot_model 路由：** 当前包提供 A1 左臂 a1_l 与右臂 a1_r；新版在模型与重力参数选择前会统一规范为小写。

| 子串 | 含义 | 配套 `dof` |
|---|---|:---:|
| `a1_l` | A1 系列左臂 | 7 |
| `a1_r` | A1 系列右臂 | 7 |

推荐直接使用 a1_l 或 a1_r，避免模型名称与共享会话 identity 不一致。

### 5.2 数据结构

```c
#define ONERO_MAX_JOINT_COUNT 16

typedef struct {
    double data[ONERO_MAX_JOINT_COUNT];
    int    count;                       // 实际关节数；count == 0 表示失败回退
} onero_joint_array_t;

typedef struct {
    double x, y, z;                     // 位置 (m)
    double qw, qx, qy, qz;              // 四元数（标量优先）
} onero_pose_t;

typedef struct {
    onero_joint_array_t positions;      // rad
    onero_joint_array_t velocities;     // rad/s
    onero_joint_array_t torques;        // N·m
} onero_arm_state_t;

typedef struct {
    double position;                     // percent
    double velocity;                     // percent/s
    double force;                        // N, limited to +/-40
    uint8_t error;
    bool valid;
} onero_gripper_status_t;

typedef struct {
    uint8_t point_id;                     // 0x00 = total force, 0x01..0x09 = points
    double fx, fy, fz;                    // N
    bool valid;
} onero_gripper_tactile_value_t;

typedef struct {
    uint8_t sensor_id;                    // 0x01 / 0x02
    onero_gripper_tactile_value_t total_force;
    onero_gripper_tactile_value_t points[9];
    uint8_t point_count;                  // 0..9
    bool valid;
} onero_gripper_tactile_sensor_status_t;

typedef struct {
    onero_gripper_tactile_sensor_status_t sensors[2];
    bool valid;
} onero_gripper_tactile_status_t;

typedef struct {
    onero_joint_array_t position;
    onero_joint_array_t velocity;
    onero_joint_array_t acceleration;
} onero_traj_point_t;

typedef enum {
    ONERO_DRAG_TEACHING_IDLE      = 0,
    ONERO_DRAG_TEACHING_RECORDING = 1,
    ONERO_DRAG_TEACHING_REPLAYING = 2,
} onero_drag_teaching_state_t;

typedef void* onero_handle;
typedef void* onero_drag_teaching_handle;
```

### 5.3 错误码

```c
// MoveResult（int 返回族）
0  SUCCESS
-1 INVALID_PARAMS
-2 IK_FAILED
-3 COLLISION_DETECTED
-4 EXECUTION_FAILED
-5 TIMEOUT
-6 INTERRUPTED
-7 JOINT_LIMIT_EXCEEDED
-8 BUSY

// 原始 CAN 帧族
0   ONERO_CAN_OK
-10 ONERO_ERR_RAW_FRAME_INVALID_LEN     // payload > 8 字节
-11 ONERO_ERR_RAW_FRAME_INVALID_ID      // can_id 越过 11-bit
-12 ONERO_ERR_RAW_FRAME_RESERVED_ID     // 命中保留集
-13 ONERO_ERR_RAW_FRAME_PORT_NOT_OPEN   // 串口未连接
-14 ONERO_ERR_RAW_FRAME_SEND_FAILED     // SLCAN 写串口失败
```

---

## 六、API 详解

下表按功能分组列出每个函数的参数与返回值。完整声明见头文件。

### 6.1 生命周期

| 函数 | 参数 | 返回 | 说明 |
|---|---|---|---|
| onero_create_robot | 配置指针 | onero_handle；NULL 表示失败 | 初始化串口、模型和会话；非仿真纯 C 配置下设备路径不存在或打开失败时初始化失败，不回退到默认串口 |
| `onero_destroy_robot` | `onero_handle` | – | 释放句柄；释放后调用方应将其重置为 `NULL`，禁止重用 |

### 6.2 电机使能

| 函数 | 返回 | 说明 |
|---|---|---|
| `onero_enable_motors(h)` | `MoveResult` | 同步等待硬件应答；首次使能可能耗时秒级 |
| `onero_disable_motors(h)` | `MoveResult` | 同步阻塞 |
| `onero_restore_arm(h)` | `MoveResult` | 以安全速度恢复默认零位；与 `onero_enable_motors` 解耦，需调用方显式触发 |
| `onero_restore_arm_to(h, target, n)` | `MoveResult` | 以安全速度恢复到指定关节目标；`n` 应等于配置的 `dof` |
| `onero_reset_stop_signal(h)` | `0/-1` | 清除前一次 stop/cancel/interruption 信号；新一轮运动前由用户层显式调用 |

### 6.3 运动控制

| 函数 | 参数 | 返回 | 语义 |
|---|---|---|---|
| `onero_movej` | `target`（rad，长度 = `dof`）/ `speed_scale` / `trajectory_connect` | `MoveResult` | 关节空间梯形/S 形规划；不保证 TCP 直线 |
| `onero_movel` | `pose` / `speed_scale` / `trajectory_connect` | `MoveResult` | 笛卡尔直线（位置控制） |
| `onero_movep` | `pose` / `speed_scale` / `trajectory_connect` | `MoveResult` | 笛卡尔点到点平滑过渡，不保证中间路径直线 |

| onero_movec | via_pose + target_pose + speed_scale + trajectory_connect=0 | MoveResult | 从新鲜反馈起点经过 via 到 target 的圆弧；不支持整圆或缓冲 |
| onero_start_servoj / onero_servoj / onero_stop_servoj | 关节限额、关节目标、有效时间 | MoveResult | SDK 100 Hz 在线关节伺服；更新返回 0 仅表示接受 |
| onero_start_servop / onero_servop / onero_stop_servop | 绝对 Link7 位姿、笛卡尔软限制 | MoveResult | 在线笛卡尔伺服；更新返回 0 仅表示接受 |
| onero_get_servoj_status / onero_get_servop_status | 句柄 | 状态结构 | 读取序号、运行状态、限制标志与最后错误 |

通用参数：

- speed_scale：无量纲速度比例，默认 1.0；必须满足 SDK 参数校验并与模型硬限制取交集，不能把 50% 理解为固定的末端速度。
- trajectory_connect=0 立即执行；MoveJ/L/P 的 trajectory_connect=1 入规划缓冲，由 onero_execute_buffered_trajectory 触发；MoveC 仅支持 0。

### 6.4 可选夹爪

`cfg.with_gripper = true` 时，SDK 在 `OneroArm` 同一串口 / CAN 会话内注册可选夹爪；默认不开启。`onero_enable_motors()` 只作用于机械臂关节，夹爪需显式调用 `onero_gripper_enable()` / `onero_gripper_disable()`。

| 函数 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `onero_has_gripper` | `onero_handle` | `bool` | 是否创建了 arm-owned 夹爪控制域 |
| `onero_gripper_enable` / `onero_gripper_disable` | `onero_handle` | `MoveResult` | 只作用于固定夹爪电机 ID `0x08` |
| `onero_gripper_status` | `onero_handle` | `onero_gripper_status_t` | 刷新并返回 position / velocity / force / error / valid |
| `onero_gripper_set_position` | `percent` | `MoveResult` | `0..100%` 单帧位置保持 |
| `onero_gripper_move_position` | `percent, max_vel, max_acc, max_jerk` | `MoveResult` | 100 Hz 点到点规划 |
| `onero_gripper_force_control` | `torque` | `MoveResult` | 下发夹爪 MIT torque，内部限制为 ±40 N |
| `onero_gripper_get_tactile` | `out` | `MoveResult` | 刷新并写出两个触摸传感器各自的合力与 9 个测点快照 |

```c
cfg.with_gripper = true;
onero_handle arm = onero_create_robot(&cfg);

if (onero_has_gripper(arm)) {
    onero_gripper_enable(arm);
    onero_gripper_set_position(arm, 50.0);
    onero_gripper_move_position(arm, 80.0, 100.0, 250.0, 1000.0);
    onero_gripper_force_control(arm, 30.0);
    onero_gripper_status_t gs = onero_gripper_status(arm);
    onero_gripper_tactile_status_t tactile;
    if (onero_gripper_get_tactile(arm, &tactile) == ONERO_OK && tactile.valid) {
        for (int i = 0; i < 2; ++i) {
            onero_gripper_tactile_sensor_status_t* s = &tactile.sensors[i];
            if (s->valid) {
                printf("%u %.3f %.3f %.3f\n",
                       s->sensor_id,
                       s->total_force.fx,
                       s->total_force.fy,
                       s->total_force.fz);
                for (uint8_t j = 0; j < s->point_count; ++j) {
                    onero_gripper_tactile_value_t* p = &s->points[j];
                    printf("  point %u %.3f %.3f %.3f\n",
                           p->point_id, p->fx, p->fy, p->fz);
                }
            }
        }
    }
}
```

`onero_gripper_get_tactile()` 当前读取传感器 `0x01` 和 `0x02` 的 `0x00..0x09`：`0x00` 写入 `total_force`，`0x01..0x09` 写入 `points`，`point_count` 最多为 9。`fx/fy` 按 `int8_t * 0.1N` 解析，`fz` 按 `uint8_t * 0.1N` 解析。

### 6.5 缓冲与轨迹

| 函数 | 参数 | 返回 | 说明 |
|---|---|---|---|
| onero_send_trajectory_point | positions + velocities | MoveResult | 单个直接关节轨迹点；调用方负责连续下发，不属于 trajectory_connect 规划缓冲 |
| `onero_send_trajectory` | `points`（数组）+ `num_points` | `MoveResult` | 一次性下发完整轨迹（位置+速度+加速度），SDK 内部按周期插补 |
| `onero_execute_buffered_trajectory` | – | `MoveResult` | 触发缓冲队列执行 |
| `onero_clear_trajectory_buffer` | – | `MoveResult` | 丢弃缓冲队列 |
| `onero_cancel_trajectory` | – | `MoveResult` | 请求取消 Move/轨迹或 ServoP；`0` 仅表示已请求；活动 ServoJ 返回 `-8`，使用 `onero_stop_servoj` |

### 6.6 MIT 力位混合直接控制

低层力位混合（阻抗）接口，用于 teleop 数据采集、阻抗控制、模仿学习推断等。控制律由电机在 MIT 模式下闭环执行：`tau_motor = kp*(q - q_act) + kd*(dq - dq_act) + tau`。

调用前先使能电机，所有数组的 count 必须等于 dof。直接 MIT 命令与 MoveJ/L/P/C、ServoJ/P 等共用机械臂命令资源，冲突返回 BUSY；调用方需按至少 100 Hz 保持连续命令。

| 函数 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `onero_control_mit` | `kp` / `kd` / `q` / `dq` / `tau`（均为 `const onero_joint_array_t*`，长度 = `dof`） | `int` | 整臂 MIT 力位混合控制（每帧一次）。`0` 成功 / `-1` 参数错误 / `-2` 硬件未初始化 / `-3` 至少一关节 CAN 写入失败 |
| `onero_compute_gravity_torque` | `q`（输入）/ `out_tau`（输出 `onero_joint_array_t*`） | `int` | 计算重力补偿力矩（含 `robot_model` 校准缩放），可直接塞进 `onero_control_mit` 的 `tau`。`0` 成功 / `-1` `q` 长度错误 / `-2` 动力学模型未就绪 |

> `q` 走与 `onero_get_arm_state_from_motor` 一致的 SDK 关节空间。建议第一帧取 `q = 当前回读位置、dq = 0、tau = 0`，避免 `kp` 较大时产生瞬间力矩冲击。

### 6.7 状态查询

| 函数 | 数据源 | 是否触发 CAN I/O | 适用场景 |
|---|---|:---:|---|
| `onero_get_joint_positions` | 整臂实时状态查询 | 可能 | 需要刷新关节位置时使用 |
| `onero_get_joint_positions_from_motors` | 电机回读 | 可能 | 与外部传感器对齐 / 校准 |
| `onero_get_joint_velocities` | 电机回读 | 可能 | 速度环 / 监督控制 |
| `onero_get_arm_state_from_motor` | 电机回读 | 可能 | 一次性获取位置 + 速度 + 力矩 |
| `onero_get_arm_state_cached` | 控制循环写入的缓存 | 否 | **推荐**用于 GUI / 数据采集线程的高频轮询 |
| `onero_get_end_effector_pose` | 实时状态 / 内部正运动学 | 可能 | 末端位姿读取 |
| `onero_get_end_effector_pose_cached` | 控制循环写入的缓存 | 否 | 高频只读位姿查询；缓存无效时返回默认位姿 |
| `onero_is_hardware_connected` | 总线心跳 | 否 | 启动 / 故障检测 |

> **失败回退**：`onero_joint_array_t::count == 0` 表示数组失败；`onero_arm_state_t` 三个数组同时 `count==0`；位姿可能回退为零位置与单位四元数；C 无效句柄或异常还可能返回全零。位姿值本身没有有效性标志，应结合连接与关节反馈判断。

### 6.8 拖动示教

record_file 与 replay_file 使用不含 .. 的相对路径，例如 teach.bin；Linux 绝对路径会被 SDK 拒绝。录制文件是 SDK 二进制轨迹格式，不能按 CSV 文本解析。


带夹爪的录制需先用 set_hardware_ex(..., true) 绑定同一设备，再选 DISABLED、POSITION 或 BACKDRIVE。POSITION 通过 set_gripper_target(0..100) 提交开度；BACKDRIVE 以零力矩允许手动开合。DISABLED 生成臂单独 V1 文件；另两种模式录制 V2 臂夹爪通道。V2 回放自动重放夹爪，不要求再次设置录制模式。


| 函数 | 返回 | 说明 |
|---|---|---|
| `onero_drag_teaching_create()` | 句柄（`NULL`=失败） | 分配实例 |
| `onero_drag_teaching_destroy(h)` | – | 释放实例 |
| `onero_drag_teaching_initialize(h, dof, record_file, time_step)` | `bool` | 配置 dof / 输出文件 / 采样步长（默认 `0.01s`） |
| `onero_drag_teaching_set_hardware(h, device, urdf_path, robot_model, mount_orientation)` | `bool` | 绑定硬件设备；`mount_orientation` 必须与实际安装姿态一致 |
| onero_drag_teaching_set_hardware_ex(h, device, urdf_path, robot_model, mount_orientation, with_gripper) | bool | 带夹爪时挂载共享总线并选择匹配的重力补偿缩放；不会自动运动夹爪或开启夹爪录制 |
| `onero_drag_teaching_enable_motors(h)` | `MoveResult` | 使能电机，不带运动副作用 |
| `onero_drag_teaching_restore_arm(h)` | `MoveResult` | 以安全速度恢复默认零位 |
| `onero_drag_teaching_restore_arm_to(h, target, n)` | `MoveResult` | 以安全速度恢复到指定关节目标 |
| `onero_drag_teaching_start_recording(h)` / `_stop_recording(h)` | `int` | 开始/停止录制并落盘 |
| `onero_drag_teaching_set_replay_file(h, replay_file)` | – | 选择回放文件 |
| `onero_drag_teaching_start_replay(h)` / `_stop_replay(h)` | `int` | 开始/停止回放 |
| `onero_drag_teaching_handle_command(h, cmd)` | `int` | 转发 UI 命令码到状态机 |
| `onero_drag_teaching_handle_command_dual(left, right, cmd)` | `int` | 对两个拖动示教实例执行同步双臂命令 |
| `onero_drag_teaching_timer_callback(h)` | – | 周期 tick（推荐 100 Hz） |
| `onero_drag_teaching_get_state(h)` | `onero_drag_teaching_state_t` | 失败回退为 `IDLE` |
| `onero_drag_teaching_is_initialized(h)` | `bool` | – |
| `onero_drag_teaching_update_joint_state(h, position, velocity, effort)` | – | 喂入电机回读 |

新增的 onero_drag_teaching_set_gripper_teaching_mode、onero_drag_teaching_set_gripper_target 返回 0 表示配置成功；onero_drag_teaching_gripper_status 返回的 valid=false 表示无有效夹爪反馈。带夹爪参数只选择对应重力缩放与共享总线，不自动证明负载补偿正确。

**双臂同步命令**：

`onero_drag_teaching_handle_command_dual(left, right, cmd)` 接受两个已初始化并完成 `onero_drag_teaching_set_hardware(...)` 的拖动示教句柄。`cmd=1` 会在 SDK 内部对两臂执行并发 prepare，并用共享 `t0` 同步开始录制；`cmd=3` 走同步回放路径；`cmd=0/2` 分别用于双臂停止、停止录制。调用方不需要自己计算或传入 `steady_clock` 时间点。

---

## 七、完整示例

最小 C 调用结构示例（运动目标必须按实物重新评估；对应完整工程见 [full_demo.c](../demo/c/full_demo.c)）：

```c
#include "onero_interface_c.h"
#include <stdio.h>
#include <string.h>

int main(void) {
    onero_config_t cfg = {0};                       /* 必须零初始化 */
    strcpy(cfg.device,      "/dev/ttyACM0");
    strcpy(cfg.robot_model, "a1_r");
    strcpy(cfg.version,     "A1");
    cfg.dof       = 7;
    cfg.baud_rate = 921600;

    onero_handle arm = onero_create_robot(&cfg);
    if (!arm) return 1;

    if (onero_enable_motors(arm) != 0) {
        onero_destroy_robot(arm);
        return 2;
    }

    /* 1) 关节空间回零 */
    onero_joint_array_t home = {0};
    home.count = 7;                                 /* data[*] 已全 0 */
    onero_movej(arm, &home, 0.5, 0);

    /* 2) 笛卡尔直线 */
    onero_pose_t target = {0};
    target.x = 0.30; target.y = 0.0; target.z = 0.40;
    target.qw = 1.0;
    onero_movel(arm, &target, 0.5, 0);

    /* 3) 状态查询（不触发 CAN I/O） */
    onero_arm_state_t st = onero_get_arm_state_cached(arm);
    if (st.positions.count > 0) {
        printf("q[0]=%f\n", st.positions.data[0]);
    }

    onero_disable_motors(arm);
    onero_destroy_robot(arm);
    return 0;
}
```

---

## 八、CAN 帧示例

与电机 / 夹爪共用同一根 SLCAN 串口；可用于向同总线上的自定义节点（MCU、传感器、IO 板等）发送 11-bit 标准 CAN 帧并接收响应。共同语义（保留 ID 集、回调线程、payload 生命周期）见根 [`README.md`](../README.md#五原始-can-帧行为)。

### 8.1 函数签名

```c
typedef void (*onero_can_frame_callback_t)(uint16_t can_id,
                                           const uint8_t* data,
                                           uint8_t        len,
                                           void*          user_data);

int onero_send_can_frame             (onero_handle h, uint16_t can_id,
                                      const uint8_t* data, uint8_t len);
int onero_register_can_frame_callback(onero_handle h,
                                      onero_can_frame_callback_t cb,
                                      void* user_data);
int onero_clear_can_frame_callback   (onero_handle h);
int onero_pump_can_bus               (onero_handle h, int timeout_ms);
```

### 8.2 参数细节

| 函数 | 参数 | 约束 / 行为 |
|---|---|---|
| `onero_send_can_frame` | `can_id` ∈ `[0x000, 0x7FF]`，**不能**落在保留集（含 arm 电机、夹爪 `0x08/0x18`、触觉回包 `0x418`、`0x7FF`）；`data`（`len==0` 可为 `NULL`）；`len ≤ 8` | 同步发送，返回时 `data` 已被拷贝，调用方可立即释放 |
| `onero_register_can_frame_callback` | `cb`（`NULL` 等价于 clear）；`user_data` 由 SDK 透传，不解释 | 重复注册替换前一个 |
| `onero_pump_can_bus` | `timeout_ms == 0` = 一次非阻塞 try-recv | 在 `move*` 空闲期主动调用，避免 SLCAN rx 缓冲累积 |

回调在独立的 DeviceSession callback worker 上执行，不占用总线 worker。SDK 使用 64 项有界 FIFO，满时丢弃最旧的未开始用户帧。回调中 data 仅在调用期间有效；只支持在回调内 register/clear callback，其它总线或运动方法的重入不属于 v1 契约。外部 clear/replace 会等待调用开始时已在执行的旧代回调。


### 8.3 完整示例

```c
#include "onero_interface_c.h"
#include <stdio.h>

static void on_frame(uint16_t id, const uint8_t* d, uint8_t n, void* ud) {
    (void)ud;
    printf("rx id=0x%X len=%u: ", id, n);
    for (uint8_t i = 0; i < n; ++i) printf("%02X ", d[i]);
    putchar('\n');
}

int main(void) {
    onero_config_t cfg = {0};
    strcpy(cfg.device,      "/dev/ttyACM0");
    strcpy(cfg.robot_model, "a1_r");
    cfg.dof = 7;

    onero_handle arm = onero_create_robot(&cfg);
    if (!arm) return 1;

    onero_register_can_frame_callback(arm, on_frame, NULL);

    uint8_t payload[4] = {0x01, 0x02, 0x03, 0x04};
    int rc = onero_send_can_frame(arm, 0x100, payload, 4);
    if (rc != 0) fprintf(stderr, "send failed: %d\n", rc);

    onero_pump_can_bus(arm, 50);                     /* 50 ms 内派发到回调 */

    onero_clear_can_frame_callback(arm);
    onero_destroy_robot(arm);
    return 0;
}
```

---

## 九、错误诊断

| 现象 | 原因 / 处理 |
|---|---|
| 编译器找不到 `onero_interface_c.h` | 把 `c/include` 加入 include path（CMake 的 `INTERFACE_INCLUDE_DIRECTORIES` 或 `gcc -I`） |
| 链接报 `cannot find -loneroarm` | `-L c/linux/<arch>` 路径不对；或 Windows 下没指 `IMPORTED_IMPLIB` |
| 运行时 `cannot open shared object liboneroarm.so` | `LD_LIBRARY_PATH` 未包含库目录；推荐用 `-Wl,-rpath,'$ORIGIN'/c/linux/<arch>` 把 rpath 写进可执行文件 |
| 运行时 `undefined symbol: ZN10pinocchio…` | `libpinocchio_*` / `libhpp-fcl` 等传递依赖没装；按本文件运行时依赖说明配齐环境 |
| `onero_enable_motors` 返回 `-5 TIMEOUT` | 检查 `cfg.device` / `baud_rate` / 急停按钮；先调用 `onero_is_hardware_connected` 验证总线心跳 |
| 运动接口返回 `-7 JOINT_LIMIT_EXCEEDED` | 目标关节越过 SDK 内置/URDF 对齐后的限位；先检查目标角度与 `robot_model` 是否匹配 |
| 运动接口返回 `-8 BUSY` | 同一只臂已有运动命令在执行；等待结束；ServoJ 先用专用 stop，其他运动先 cancel 并确认停止，再 `onero_reset_stop_signal` 后发新命令 |
| `onero_send_can_frame` 返回 `-12 RESERVED_ID` | `can_id` 落在保留集（电机 / 夹爪 / 触觉回包 / 操纵杆 / `0x7FF`） |
| `onero_send_can_frame` 返回 `-13 PORT_NOT_OPEN` | 串口未打开或 handle 已被 `onero_destroy_robot` 释放 |
| 回调收不到帧 | 确认对端发送的 CAN ID **不在** SDK 保留集；运动控制空闲期调用 `onero_pump_can_bus` 主动拉帧 |
| `Pinocchio model load failed` / 找不到 URDF | 默认走 SDK 内置 `share/oneroarm_description/`；若被覆盖可设 `ONERO_DESCRIPTION_PATH` 或 `cfg.model_description_path` |


## 十、新增运动与坐标接口

以下均为 [公开 C 头](include/onero_interface_c.h) 中已交付的函数。机械臂参数为 onero_handle；创建句柄前应将 onero_config_t 清零，再按实际设备设置机型、轴数、安装方向和夹爪选项。

| 接口 | 主要输入 | 返回及行为 |
|---|---|---|
| onero_movec | via_pose、target_pose、speed_scale、trajectory_connect=0 | 从新鲜反馈起点经 via 沿圆弧到 target；两 Pose 为绝对 base_T_link7；不支持整圆或缓冲模式 |
| onero_start_servoj | 可选逐轴速度/加速度/加加速度软限制 | 启动 SDK 自有 100 Hz 在线关节控制 |
| onero_servoj | dof 个 target_q、可空的 target_dq、valid_for_seconds | 替换最新目标；0 表示接受而非到位；有效期须有限且在 (0,10] 秒 |
| onero_get_servoj_status / onero_stop_servoj | 句柄 | 查询状态/受控停止，stop 非安全级急停 |
| onero_start_servop | 句柄 | 启动笛卡尔在线控制 |
| onero_servop | 绝对 base_T_link7 位姿及四个正且有限的线/角速度和加速度软限制 | 替换最新目标；0 表示接受而非到位；SDK 与硬限制取交集 |
| onero_get_servop_status / onero_stop_servop | 句柄 | 查询状态/受控停止，stop 非安全级急停 |

ServoP v1 控制 Link7/flange 原点，不自动施加 TCP 偏移。ServoJ/ServoP status 都包括 accepted_sequence、applied_sequence、limit_flags 和 last_error；检查这些字段并读取实际反馈，不能只看更新返回 0。ServoJ limit_flags 中数值 8 为 OTG_INFEASIBLE（轨迹生成不可行），不能仅据此认定加速度过大。

Frame 的 onero_transform_pose、onero_apply_cartesian_delta、onero_flange_pose_to_tool、onero_tool_pose_to_flange 为纯坐标运算。WORLD 换算须有 world_from_base 标定；TOOL 换算须有当前 base_from_tool 锚点。位置单位 m，四元数按 qw/qx/qy/qz 传递，输出参数和完整结构见 [公开 C 头](include/onero_interface_c.h)及 [C Frame 示例](../demo/c/frame_demo.c)。

拖动示教夹爪接口包括 onero_drag_teaching_set_gripper_teaching_mode、onero_drag_teaching_set_gripper_target、onero_drag_teaching_gripper_status。DISABLED 使用臂单独 V1 轨迹；POSITION 记录夹爪目标；BACKDRIVE 以零力矩手动开合并记录夹爪反馈，V2 回放自动处理夹爪通道。设置 with_gripper 只是选择共享会话与相应补偿参数，不自动启动夹爪录制。

C 多臂回放可使用 onero_drag_teaching_prepare_replay → onero_drag_teaching_move_to_replay_start → onero_drag_teaching_begin_replay；前一阶段全部成功后才进入后一阶段。共享 t0_ns 必须用 onero_steady_clock_now_ns() 的同源时钟生成，不能使用系统日历时间。单臂通常直接使用 onero_drag_teaching_start_replay，双臂可用 onero_drag_teaching_handle_command_dual。


## ServoJ 运动中停止与通用取消

ServoJ 停止从当前连续指令位置、速度和加速度规划限加加速度制动，允许沿运动方向到达可制动的停止位置，不回到停止请求时的位置。`stop_servoj()` 阻塞等待受控制动及终拍完成；成功返回 `0` 后状态为 IDLE、命令速度和加速度为零、机械臂命令资源已释放；制动故障返回负错误码。停止时长取决于当时速度、加速度以及用户限制与 SDK 硬限制的交集，没有固定的通用毫秒承诺。

通用取消只请求取消 MoveJ/L/P/C、轨迹执行或 ServoP；返回 `0` 表示请求已记录，不表示运动已经停止，无活动运动时也返回 `0`。ServoJ 会话活动期间（含 RUNNING、BRAKING、HOLDING）返回 `-8 BUSY`，不设置取消信号、不改变该会话；必须调用专用 `stop_servoj()` / `onero_stop_servoj()`。

## ServoJ 运动中更新目标

每个 10 ms 控制周期读取最新有效目标；同周期多次更新覆盖旧目标，不排队逐点执行。运动中换目标时，从上一拍连续指令的 q/dq/ddq 重新规划到新目标，不要求先完成旧目标；刷新相同目标只续期，不重复规划。

当前跟踪使用静态集成的 Ruckig Community 0.15.3，保留 SDK 的速度、加速度、jerk 限制；使用前检查完整规划路径及制动包络的关节限位，每拍继续检查。无需额外安装 Ruckig 或联网。可行的前向换目标用例不再出现原先约 1 rad 的异常超调；换近目标或反向时，惯性和动态限制仍可能要求先制动一段距离。

`servoj()` 返回 `0` 表示接受目标。零目标速度的轨迹完成后进入 HOLDING；非零目标速度到达目标后仍处于 RUNNING，延续末速度，直至新目标、有效期到期或专用停止。规划路径或制动包络越界时，状态包含 JOINT_POSITION，`last_error=-7`，不会下发该候选路径；其他规划不可行仍报告 OTG_INFEASIBLE。请持续查询状态和反馈。

ServoJ 的 `limit_flags` 保留当前会话的累计事件。发生命令超时后，即使新目标已恢复跟踪，`COMMAND_TIMEOUT` 仍可能保留；应联合当前 `state`、`command_age_s`、序号和 `last_error` 判断。成功专用停止清除该标志；它不是新的停止请求。
