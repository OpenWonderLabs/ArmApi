# OneroArm 纯 C ABI 包

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

---

## 一、目录结构

```
c/
├── include/                                  # 跨 OS 共用，公开头扁平到顶层
│   └── onero_interface_c.h                   # 纯 C 接口声明 + 内联导出宏（extern "C"）
├── share/oneroarm_description/               # 跨 OS 共用 URDF / mesh
├── linux/
│   ├── linux-x86_64/liboneroarm.so
│   ├── linux-arm64/liboneroarm.so
│   └── linux-riscv64/liboneroarm.so
└── windows/
    └── windows-x86_64/{oneroarm.dll, oneroarm.lib}
```

本包**不含** rbdl 头/静态库，也**不含** `onero_define.h` 与
`onero_interface_cpp.h`（C++ API）。如需 C++ 接口请改用同级
[`c++/`](../c++/) 包；两包的 `liboneroarm.so` / `oneroarm.dll` 二进制完全相同。

---

## 二、集成方式

### 2.1 选项 A：CMake 直接 IMPORTED

```cmake
cmake_minimum_required(VERSION 3.15)
project(my_c_app LANGUAGES C)              # 注意：纯 C 项目无需 CXX

set(ONERO_SDK ${CMAKE_CURRENT_SOURCE_DIR}/c)
add_library(oneroarm SHARED IMPORTED)
set_target_properties(oneroarm PROPERTIES
    IMPORTED_LOCATION             ${ONERO_SDK}/linux/linux-x86_64/liboneroarm.so
    INTERFACE_INCLUDE_DIRECTORIES ${ONERO_SDK}/include
)

add_executable(my_c_app main.c)
target_link_libraries(my_c_app PRIVATE oneroarm)
```

Windows 把 `IMPORTED_LOCATION` 指向 `oneroarm.dll`，再加 `IMPORTED_IMPLIB`
指向 `oneroarm.lib`；Linux 按实际架构把子目录改成 `linux-x86_64`、`linux-arm64`
或 `linux-riscv64` 即可。RISC-V 示例：

```cmake
set(ONERO_SDK ${CMAKE_CURRENT_SOURCE_DIR}/c)
add_library(oneroarm SHARED IMPORTED)
set_target_properties(oneroarm PROPERTIES
    IMPORTED_LOCATION             ${ONERO_SDK}/linux/linux-riscv64/liboneroarm.so
    INTERFACE_INCLUDE_DIRECTORIES ${ONERO_SDK}/include
)
```

### 2.2 选项 B：纯命令行编译

```bash
gcc main.c -I c/include -L c/linux/linux-x86_64 -loneroarm \
    -Wl,-rpath,'$ORIGIN'/c/linux/linux-x86_64 -o my_c_app
```

RISC-V 上把库目录替换为 `linux-riscv64`，并确保第三方运行时库在
`LD_LIBRARY_PATH` 中：

```bash
export ONERO_DEPS_PREFIX=/opt/onero-deps
export LD_LIBRARY_PATH="$ONERO_DEPS_PREFIX/lib:$PWD/c/linux/linux-riscv64:$LD_LIBRARY_PATH"

gcc main.c -I c/include -L c/linux/linux-riscv64 -loneroarm \
    -Wl,-rpath,'$ORIGIN'/c/linux/linux-riscv64 \
    -Wl,-rpath-link,"$ONERO_DEPS_PREFIX/lib" \
    -o my_c_app

./my_c_app
```

---

## 三、运行时依赖

`liboneroarm.so` / `oneroarm.dll` 的 C++ 传递依赖通过 ELF `DT_NEEDED` /
Windows IAT 在运行时由动态加载器自动拉起；只需保证下表 SONAME 在
`LD_LIBRARY_PATH` / `PATH` 上即可：

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
`-Wl,-rpath,'$ORIGIN'/c/linux/linux-riscv64`）：

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
ldd c/linux/linux-riscv64/liboneroarm.so | grep 'not found' || true
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

**`robot_model` 子串包含规则**（大小写敏感）：

| 子串 | 含义 | 配套 `dof` |
|---|---|:---:|
| `a1_l` | A1 系列左臂 | 7 |
| `a1_r` | A1 系列右臂 | 7 |

例如 `"a1_r_demo01"` 会被识别为 A1 右臂。

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
| `onero_create_robot` | `const onero_config_t* config` | `onero_handle`（`NULL`=失败） | 按配置创建底层 handle；半构造资源（串口 / 电机 / URDF）失败时由内部回滚。**没有连接机械臂时本调用仍可能返回非空 handle**，后续 `onero_enable_motors` 才会进入跳过分支返回错误码 |
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

通用参数：

- `speed_scale`：建议 `(0, 2.0]`，默认 `1.0`，超过 `1.0` 仅在低惯量场景使用。
- `trajectory_connect`：`0` 立即执行；`1` 入缓冲队列，由 `onero_execute_buffered_trajectory` 触发。

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
| `onero_send_trajectory_point` | `positions` + `velocities` | `MoveResult` | 单点（位置 + 速度）入缓冲队列，配合 `execute_buffered_trajectory` 使用 |
| `onero_send_trajectory` | `points`（数组）+ `num_points` | `MoveResult` | 一次性下发完整轨迹（位置+速度+加速度），SDK 内部按周期插补 |
| `onero_execute_buffered_trajectory` | – | `MoveResult` | 触发缓冲队列执行 |
| `onero_clear_trajectory_buffer` | – | `MoveResult` | 丢弃缓冲队列 |
| `onero_cancel_trajectory` | – | `MoveResult` | 异步终止当前运动指令 |

### 6.6 MIT 力位混合直接控制

低层力位混合（阻抗）接口，用于 teleop 数据采集、阻抗控制、模仿学习推断等。控制律由电机在 MIT 模式下闭环执行：`tau_motor = kp*(q - q_act) + kd*(dq - dq_act) + tau`。

调用前必须先 `onero_enable_motors`；所有数组的 `count` 必须等于 `dof`。**不要**与 `onero_movej/movel/movep` 在重叠时间窗内混用（共用同一根 SLCAN 链路），并需以 ≥100 Hz 持续下发。

| 函数 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `onero_control_mit` | `kp` / `kd` / `q` / `dq` / `tau`（均为 `const onero_joint_array_t*`，长度 = `dof`） | `int` | 整臂 MIT 力位混合控制（每帧一次）。`0` 成功 / `-1` 参数错误 / `-2` 硬件未初始化 / `-3` 至少一关节 CAN 写入失败 |
| `onero_compute_gravity_torque` | `q`（输入）/ `out_tau`（输出 `onero_joint_array_t*`） | `int` | 计算重力补偿力矩（含 `robot_model` 校准缩放），可直接塞进 `onero_control_mit` 的 `tau`。`0` 成功 / `-1` `q` 长度错误 / `-2` 动力学模型未就绪 |

> `q` 走与 `onero_get_arm_state_from_motor` 一致的 SDK 关节空间。建议第一帧取 `q = 当前回读位置、dq = 0、tau = 0`，避免 `kp` 较大时产生瞬间力矩冲击。

### 6.7 状态查询

| 函数 | 数据源 | 是否触发 CAN I/O | 适用场景 |
|---|---|:---:|---|
| `onero_get_joint_positions` | 上位机内部缓存 | 否 | 通用查询，最低开销 |
| `onero_get_joint_positions_from_motors` | 电机回读 |  | 与外部传感器对齐 / 校准 |
| `onero_get_joint_velocities` | 电机回读 |  | 速度环 / 监督控制 |
| `onero_get_arm_state_from_motor` | 电机回读 |  | 一次性获取位置 + 速度 + 力矩 |
| `onero_get_arm_state_cached` | 控制循环写入的缓存 | 否 | **推荐**用于 GUI / 数据采集线程的高频轮询 |
| `onero_get_end_effector_pose` | 实时状态 / 内部正运动学 | 可能 | 末端位姿读取 |
| `onero_get_end_effector_pose_cached` | 控制循环写入的缓存 | 否 | 高频只读位姿查询；缓存无效时返回默认位姿 |
| `onero_is_hardware_connected` | 总线心跳 | 否 | 启动 / 故障检测 |

> **失败回退**：`onero_joint_array_t::count == 0` 表示数组失败；`onero_arm_state_t` 三个数组同时 `count==0`；`onero_pose_t` 全零。

### 6.8 拖动示教

| 函数 | 返回 | 说明 |
|---|---|---|
| `onero_drag_teaching_create()` | 句柄（`NULL`=失败） | 分配实例 |
| `onero_drag_teaching_destroy(h)` | – | 释放实例 |
| `onero_drag_teaching_initialize(h, dof, record_file, time_step)` | `bool` | 配置 dof / 输出文件 / 采样步长（默认 `0.01s`） |
| `onero_drag_teaching_set_hardware(h, device, urdf_path, robot_model, mount_orientation)` | `bool` | 绑定硬件设备；`mount_orientation` 必须与实际安装姿态一致 |
| `onero_drag_teaching_set_hardware_ex(h, device, urdf_path, robot_model, mount_orientation, with_gripper)` | `bool` | 同上，额外用 `with_gripper` 选择带夹爪的重力补偿缩放占位参数；`false` 时等价于不带 `_ex` 的版本 |
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

**双臂同步命令**：

`onero_drag_teaching_handle_command_dual(left, right, cmd)` 接受两个已初始化并完成 `onero_drag_teaching_set_hardware(...)` 的拖动示教句柄。`cmd=1` 会在 SDK 内部对两臂执行并发 prepare，并用共享 `t0` 同步开始录制；`cmd=3` 走同步回放路径；`cmd=0/2` 分别用于双臂停止、停止录制。调用方不需要自己计算或传入 `steady_clock` 时间点。

---

## 七、完整示例

最小可编译的 C 程序（与 [`demo/arm_control_demo.c`](../demo/arm_control_demo.c) 同源，省略错误处理）：

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

与电机 / 夹爪共用同一根 SLCAN 串口；可用于向同总线上的自定义节点（MCU、传感器、IO 板等）发送 11-bit 标准 CAN 帧并接收响应。共同语义（保留 ID 集、回调线程、payload 生命周期）见根 [`README.md`](../README.md) §7。

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

回调中 `data` 仅在调用期间有效，需保留请自行 `memcpy`。

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
| 运行时 `undefined symbol: ZN10pinocchio…` | `libpinocchio_*` / `libhpp-fcl` 等传递依赖没装；激活 `oneroarm_cpp` conda 环境即可 |
| `onero_enable_motors` 返回 `-5 TIMEOUT` | 检查 `cfg.device` / `baud_rate` / 急停按钮；先调用 `onero_is_hardware_connected` 验证总线心跳 |
| 运动接口返回 `-7 JOINT_LIMIT_EXCEEDED` | 目标关节越过 SDK 内置/URDF 对齐后的限位；先检查目标角度与 `robot_model` 是否匹配 |
| 运动接口返回 `-8 BUSY` | 同一只臂已有运动命令在执行；等待结束或先 cancel，再 `onero_reset_stop_signal` 后发新命令 |
| `onero_send_can_frame` 返回 `-12 RESERVED_ID` | `can_id` 落在保留集（电机 / 夹爪 / 触觉回包 / 操纵杆 / `0x7FF`） |
| `onero_send_can_frame` 返回 `-13 PORT_NOT_OPEN` | 串口未打开或 handle 已被 `onero_destroy_robot` 释放 |
| 回调收不到帧 | 确认对端发送的 CAN ID **不在** SDK 保留集；运动控制空闲期调用 `onero_pump_can_bus` 主动拉帧 |
| `Pinocchio model load failed` / 找不到 URDF | 默认走 SDK 内置 `share/oneroarm_description/`；若被覆盖可设 `ONERO_DESCRIPTION_PATH` 或 `cfg.model_description_path` |
