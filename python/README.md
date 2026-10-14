# OneroArm Python 包

Ubuntu 24.04 riscv64 的 CPython 3.12 wheel 位于 `wheels/linux-riscv64/`；系统依赖及双模块安装见 [RISC-V 安装说明](../RISC_V_GUIDE.md)。本平台不提供 Conda 包。

预编译 Python 扩展模块（pybind11）+ URDF/mesh 资源。三层公共面与返回值约定见仓库根 [`README.md`](../README.md)。

> **模块名**：`import oneroarm`（pybind11 原生扩展，包名 `oneroarm`）。

---

## 目录

- [OneroArm Python 包](#oneroarm-python-包)
  - [目录](#目录)
  - [一、目录结构](#一目录结构)
  - [二、安装](#二安装)
    - [2.1 Linux x86_64 wheel](#21-linux-x86_64-wheel)
    - [2.2 本地 Conda channel](#22-本地-conda-channel)
  - [三、运行期资源定位](#三运行期资源定位)
  - [四、数据类](#四数据类)
    - [4.1 `OneroConfig` 字段](#41-oneroconfig-字段)
    - [4.2 错误码](#42-错误码)
  - [五、`OneroArm` 详解](#五oneroarm-详解)
    - [5.1 电机使能](#51-电机使能)
    - [5.2 可选夹爪](#52-可选夹爪)
    - [5.3 运动控制、在线伺服与 Frame](#53-运动控制在线伺服与-frame)
    - [5.4 缓冲与轨迹](#54-缓冲与轨迹)
    - [5.5 MIT 力位混合直接控制](#55-mit-力位混合直接控制)
    - [5.6 状态查询](#56-状态查询)
  - [六、`OneroDragTeaching` 详解](#六onerodragteaching-详解)
  - [七、完整示例](#七完整示例)
  - [八、CAN 帧示例](#八can-帧示例)
    - [8.1 方法签名](#81-方法签名)
    - [8.2 参数细节](#82-参数细节)
    - [8.3 完整示例](#83-完整示例)
  - [九、错误诊断](#九错误诊断)

---

## 一、目录结构

| 路径 | 内容 |
|---|---|
| python/wheels/linux-x86_64 | 主机械臂 CPython 3.12 wheel |
| python/wheels/linux-riscv64 | Ubuntu 24.04 RISC-V 主机械臂 CPython 3.12 wheel |
| python/conda_channel/linux | Linux x86_64 / arm64 Conda 包及索引 |
| python/conda_channel/windows | Windows x86_64 Conda 包及索引 |
| python/oneroarm.pyi | Python 类型存根及完整接口签名 |

主 SDK 的 Conda 包覆盖 CPython 3.10–3.13，独立夹爪 Conda 包当前为 CPython 3.12。详见 [channel 文档](conda_channel/README.md)。安装包包含扩展模块和模型资源。

## 二、安装

### 2.1 Linux x86_64 wheel

在 Ubuntu 22.04+、CPython 3.12 环境中，从本包根目录执行：

```bash
python3.12 -m pip install --force-reinstall ./python/wheels/linux-x86_64/oneroarm-1.2.1-5-cp312-cp312-linux_x86_64.whl
python3.12 -c "import oneroarm; print(oneroarm.__file__)"
```

主臂与独立夹爪 wheel 的共享状态类型采用 module_local 注册，Python 扩展使用导出白名单，两个模块使用相同的随包 C++ 运行库。主臂 wheel 构建标签为 5，独立夹爪 wheel 为 3，版本均为 1.2.1。本次 SDK 版本号保持 1.2.1，已有同版本安装需强制重装 wheel 或升级至主臂 Conda build 5，并重启 Python 进程。wheel 仅适用于 CPython 3.12，NumPy 要求为 >=2,<2.3。

两种导入顺序下的模型加载、机械臂构造及代表性仿真调用已通过本机 Python 3.12.14/3.12.15 检查。联合安装和重新安装命令见 [独立夹爪 Python 文档](../gripper/python/README.md)，完整范围见 [发布说明](../RELEASE_NOTES.md)。本 wheel 使用 linux_x86_64 标签，不承诺 manylinux 兼容范围；当前支持基线为 Ubuntu 22.04+。

### 2.2 本地 Conda channel

以下命令用于 Linux x86_64 / arm64，须在本包根目录执行：

```bash
micromamba create -n woanarm-sdk-120 -c "file://$PWD/python/conda_channel/linux" -c robostack-staging -c conda-forge python=3.12 oneroarm=1.2.1 "numpy>=2,<2.3"
micromamba run -n woanarm-sdk-120 python -c "import oneroarm; print(oneroarm.__file__)"
```

Windows x86_64 在 Windows 本机将 channel URL 改为 file:///<SDK绝对路径>/python/conda_channel/windows。需要独立夹爪包时，在 Python 3.12 环境加入 onerogripper=1.2.1。本地 channel 提供 SDK 包，依赖从 robostack-staging / conda-forge 解算。导入自检不连接机械臂。精确复现三平台 Python 3.12 环境见 [依赖锁与安装步骤](environments/README.md)。

---
## 三、运行期资源定位

`oneroarm` 扩展底层即 `liboneroarm.so`，URDF/mesh 资源解析优先级（命中即停）：

1. `cfg.model_description_path`（非空时直接使用）
2. 环境变量 `ONERO_DESCRIPTION_PATH` / `ONERO_DESCRIPTION_DIR`
3. 自身 `dladdr` 推断 → `<site-packages>/share/oneroarm_description/`（默认零配置）
4. CWD 相对回退（兼容历史脚本）
5. ROS / `AMENT_PREFIX_PATH`

**喂给外部工具**（RViz / MuJoCo / 自研 viewer）需要绝对路径时：

```python
import os, oneroarm
desc = os.path.join(os.path.dirname(oneroarm.__file__),
                    "share", "oneroarm_description")
```

或显式 `export ONERO_DESCRIPTION_PATH=/path/to/oneroarm_description` 由调用方与 SDK 共享同一份资源。

---

## 四、数据类

```python
import oneroarm

cfg = oneroarm.OneroConfig()         # device / robot_model / dof / version / mit_kp ...
ja  = oneroarm.JointArray()          # 运行时为原生 list，也可直接传 list[float]
p   = oneroarm.Pose()                # x, y, z, qw, qx, qy, qz
st  = oneroarm.ArmStateFromMotor()   # positions / velocities / torques
gs  = oneroarm.GripperStatus()       # position / velocity / force / error / valid
ts  = oneroarm.GripperTactileStatus()# sensors[2] / valid
tp  = oneroarm.TrajectoryPoint()     # position / velocity / acceleration

oneroarm.DragTeachingState.IDLE       # 0
oneroarm.DragTeachingState.RECORDING  # 1
oneroarm.DragTeachingState.REPLAYING  # 2
```

### 4.1 `OneroConfig` 字段

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|:---:|---|---|
| `device` | `str` | ✅ | `""` | 串口设备路径。Linux `/dev/ttyACM0`，Windows `COM3` |
| `robot_model` | `str` | ✅ | `""` | `"a1_l"` / `"a1_r"`，会规范化为小写；按实际机型选择 |
| `dof` | `int` | – | `7` | API 配置支持 6 或 7；随包 A1 左右臂使用 7 |
| `baud_rate` | `int` | – | `921600` | 串口波特率 |
| `urdf_path` | `str` | – | `""` | 留空 → 由 `model_description_path` + `version` 自动定位 |
| `version` | `str` | – | `""` | URDF 子目录名（`"A1"`），留空时按 `robot_model` 推断 |
| `mount_orientation` | `str` | – | `"vertical"` | `"vertical"` 立装 / `"horizontal"` 卧装。**装错将导致重力补偿方向错误** |
| `mit_kp` | `list[float]` | – | 全 `0` | MIT 比例增益。`==0` 视为该关节未传入 |
| `mit_kd` | `list[float]` | – | 全 `0` | MIT 微分增益。同上 |
| `model_description_path` | `str` | – | `""` | `oneroarm_description` 根目录。留空 → SDK 内置 |
| `with_gripper` | `bool` | – | `False` | 在同一串口 / CAN 会话内注册可选夹爪；也可构造 `OneroArm(cfg, with_gripper=True)` |
| `simulation_mode` | `bool` | – | `False` | 无硬件仿真，仅用于离线接口与算法检查 |

> Python 端**不暴露** `interrupt_check` / `interrupt_ctx`（C++ 独有）。

**7-DOF 默认增益**（`mit_kp[i] == 0` 时自动注入）：

| 关节 | 0 | 1 | 2 | 3 | 4 | 5 | 6 |
|---|---|---|---|---|---|---|---|
| `kp` | 150 | 150 | 150 | 150 | 30 | 30 | 30 |
| `kd` | 4 | 4 | 4 | 4 | 1 | 1 | 1 |

### 4.2 错误码

```python
# MoveResult
0   # SUCCESS
-1  # INVALID_PARAMS
-2  # IK_FAILED
-3  # COLLISION_DETECTED
-4  # EXECUTION_FAILED
-5  # TIMEOUT
-6  # INTERRUPTED
-7  # JOINT_LIMIT_EXCEEDED
-8  # BUSY

# 原始 CAN 帧
0    # ONERO_CAN_OK
-10  # ONERO_ERR_RAW_FRAME_INVALID_LEN
-11  # ONERO_ERR_RAW_FRAME_INVALID_ID
-12  # ONERO_ERR_RAW_FRAME_RESERVED_ID
-13  # ONERO_ERR_RAW_FRAME_PORT_NOT_OPEN
-14  # ONERO_ERR_RAW_FRAME_SEND_FAILED
```

---

## 五、`OneroArm` 详解

```python
class OneroArm:
    def __init__(self, config: OneroConfig, with_gripper: bool = False) -> None: ...
```

构造时按 `OneroConfig` 创建底层 robot handle；Python 层无 valid()；真实串口缺失或打不开时初始化失败，不会自动回退另一设备。运动 / 状态方法既接受 `JointArray`，也接受 `list[float]`（自动转换）。

### 5.1 电机使能

| 方法 | 返回 | 说明 |
|---|---|---|
| `enable_motors() -> bool` | `True` 成功 | 同步等待硬件应答；首次使能可能耗时秒级 |
| `disable_motors() -> bool` | `True` 成功 | 同步阻塞 |
| `restore_arm() -> int` | `MoveResult` | 以安全速度回默认零位 |
| `restore_arm(target) -> int` | `MoveResult` | 以安全速度回指定关节目标 |

> Python 的 `enable_motors()` / `disable_motors()` 仍返回 `bool`：`True` 即成功，`False` 即任何非 0 错误码。

### 5.2 可选夹爪

选配，默认关闭。`with_gripper=True` 时，`arm.gripper` 是 arm-owned 控制器；默认 `False` 时为 `None`。夹爪随臂初始化、复用 `OneroArm` 的同一串口 / CAN 会话（固定 CAN ID `0x08/0x18`），不会单独打开设备；`arm.enable_motors()` 只使能机械臂关节，夹爪需显式 `arm.gripper.enable()`。

| 成员 / 方法 | 参数 | 返回 | 语义 |
|---|---|---|---|
| `OneroArm(cfg, with_gripper=True)` / `cfg.with_gripper=True` | – | `OneroArm` | 随臂创建可选夹爪 |
| `arm.has_gripper()` | – | `bool` | 是否随臂创建了夹爪 |
| `arm.gripper` | 属性 | `Optional[OneroGripper]` | 夹爪控制器；未开启时为 `None` |
| `gripper.enable()` / `gripper.disable()` | – | `bool` | 使能 / 失能夹爪电机（固定 ID `0x08/0x18`，与 `enable_motors()` 解耦） |
| `gripper.set_position(percent)` | `percent`：`0..100` | `int`（`MoveResult`） | 单帧位置保持 |
| `gripper.move_position(percent, max_vel=100.0, max_acc=250.0, max_jerk=1000.0)` | `percent`：`0..100`；速度 / 加速度 / 加加速度上限 | `int` | 100 Hz 点到点规划 |
| `gripper.force_control(torque)` | `torque`：N | `int` | 下发 MIT 力矩，内部钳位 ±40 N |
| `gripper.status()` | – | `GripperStatus` | 刷新并返回 `position` / `velocity` / `force` / `error` / `valid` |
| `gripper.get_tactile()` | – | `GripperTactileStatus` | 刷新并返回两个触摸传感器各自的合力与 9 个测点快照 |

```python
arm = oneroarm.OneroArm(cfg, with_gripper=True)
arm.gripper.enable()

arm.gripper.set_position(50.0)                       # percent, 单帧保持
arm.gripper.move_position(80.0, 100.0, 250.0, 1000.0) # 100 Hz 点到点规划
arm.gripper.force_control(30.0)                       # limited to +/-40 N

status = arm.gripper.status()
print(status.position, status.velocity, status.force, status.error)

tactile = arm.gripper.get_tactile()
if tactile.valid:
    for sensor in tactile.sensors:
        if sensor.valid:
            f = sensor.total_force
            print(sensor.sensor_id, f.fx, f.fy, f.fz)
            for p in sensor.points:
                print("point", p.point_id, p.fx, p.fy, p.fz)
```

`status.position` / `status.velocity` 使用用户侧百分比单位；内部会映射到夹爪工作范围。`force_control()` 和 `status.force` 使用 N，夹爪力矩命令限制为 ±40 N。夹爪状态和故障码只属于夹爪域，不会改变机械臂 `dof` 或关节状态缓存。

`get_tactile()` 当前读取传感器 `0x01` 和 `0x02` 的 `0x00..0x09`：`0x00` 写入 `sensor.total_force`，`0x01..0x09` 写入 `sensor.points`。`fx/fy` 按 `int8_t * 0.1N` 解析，`fz` 按 `uint8_t * 0.1N` 解析。

### 5.3 运动控制、在线伺服与 Frame

```python
arm.movej(target_q, speed_scale=1.0, trajectory_connect=0)
arm.movel(target_pose, speed_scale=1.0, trajectory_connect=0)
arm.movep(target_pose, speed_scale=1.0, trajectory_connect=0)
arm.movec(via_pose, target_pose, speed_scale=1.0, trajectory_connect=0)
duration = arm.estimate_movej_duration(target_q, speed_scale=1.0)
```

MoveJ 输入 dof 维关节角（rad），不保证末端直线；MoveL 为笛卡尔直线；MoveP 为笛卡尔点到点。MoveC 从新鲜反馈起点经 via 沿圆弧到 target。MoveC 的两个 Pose 均为绝对 base_T_link7 位姿（m、四元数 qw/qx/qy/qz），不支持整圆或 trajectory_connect=1。阻塞运动返回 MoveResult；0 表示 SDK 执行结束，仍应读取实际反馈。speed_scale 受规划参数与模型硬限制约束。

```python
limits_j = oneroarm.JointServoLimits()  # 空数组表示使用 SDK 限制
arm.start_servoj(limits_j)
arm.servoj(target_q, target_dq=[], valid_for_seconds=0.10)
status_j = arm.get_servoj_status()
arm.stop_servoj()

limits_p = oneroarm.CartesianServoLimits()
arm.start_servop()
arm.servop(target_pose, limits_p)
status_p = arm.get_servop_status()
arm.stop_servop()
```

ServoJ 以 100 Hz 运行，可请求逐轴 max_velocity、max_acceleration、max_jerk 软限制；有效期须为有限值且位于 (0,10] 秒。ServoP 的四个线/角速度、加速度软限制须有限且大于 0，并与 SDK 硬限制取交集；它控制 Link7/flange 原点，不自动施加 TCP 偏移。两种在线更新返回 0 都只表示 SDK 接受了目标；应查询状态的 accepted_sequence、applied_sequence、last_error、limit_flags 及实际反馈。ServoJ 的 limit_flags 值 8 为 OTG_INFEASIBLE，单凭该标志无法断言加速度过大。stop 是受控软件停止，并非急停。

```python
frames = oneroarm.FrameSnapshot()
base_pose = oneroarm.transform_pose(pose, oneroarm.CartesianFrame.BASE,
                                   oneroarm.CartesianFrame.TOOL, frames,
                                   current_base_from_tool)
new_pose = oneroarm.apply_cartesian_delta(current_base_from_tool, delta,
                                          oneroarm.CartesianFrame.TOOL, frames)
tool_pose = oneroarm.flange_pose_to_tool(flange_pose, frames.flange_from_tool)
flange_pose = oneroarm.tool_pose_to_flange(tool_pose, frames.flange_from_tool)
```

Frame 四个函数只做坐标运算，不连接设备。WORLD 换算须有 world_from_base 标定；TOOL 换算须提供当前 base_from_tool 锚点。详细结构与返回签名见 [类型存根](oneroarm.pyi)和 [Frame 示例](../demo/python/advanced/frame_transform.py)。

### 5.4 缓冲与轨迹

```python
def send_trajectory_point      (self, q: JointArray, dq: JointArray) -> int: ...
def send_trajectory            (self, trajectory: list[TrajectoryPoint]) -> int: ...
def execute_buffered_trajectory(self) -> int: ...
def clear_trajectory_buffer    (self) -> int: ...
def reset_stop_signal          (self) -> None: ...
def cancel_trajectory          (self) -> int: ...
```

### 5.5 MIT 力位混合直接控制

```python
def control_mit(self, kp: JointArray, kd: JointArray, q: JointArray,
                dq: JointArray, tau: JointArray) -> int: ...
def compute_gravity_torque(self, q: JointArray) -> JointArray: ...
```

低层力位混合（阻抗）接口，用于 teleop 数据采集、阻抗控制、模仿学习推断等。控制律 `tau_motor = kp*(q - q_act) + kd*(dq - dq_act) + tau` 由电机在 MIT 模式下闭环执行。调用前先 `enable_motors()`；所有数组长度 = `dof`，需以 ≥100 Hz 持续下发，**不要**与 `movej/movel/movep/movec` 或 ServoJ/P 在重叠时间窗内混用。

- `control_mit(...)`：返回 `int`（`0` 成功 / `-1` 参数错误 / `-2` 硬件未初始化 / `-3` 至少一关节 CAN 写入失败）；调用期间释放 GIL。`q` 走与 `get_arm_state_from_motor()` 一致的 SDK 关节空间，建议第一帧 `q=当前回读位置、dq=0、tau=0`。
- `compute_gravity_torque(q)`：**返回值即重力补偿力矩 `JointArray`**（含 `robot_model` 校准缩放），可直接作为 `control_mit` 的 `tau`；`len(q) != dof` 或动力学模型未就绪时抛 `ValueError`。注意此处返回 tau，与 C / C++ 的「`int` 返回 + 出参」风格不同。

### 5.6 状态查询

| 方法 | 数据源 | 是否触发 CAN I/O | 适用场景 |
|---|---|:---:|---|
| `get_joint_positions() -> JointArray` | 整臂实时状态查询 | 可能 | 需要刷新关节位置时使用 |
| `get_joint_positions_from_motors() -> JointArray` | 电机回读 | 可能 | 与外部传感器对齐 |
| `get_joint_velocities() -> JointArray` | 电机回读 | 可能 | 速度环 / 监督控制 |
| `get_arm_state_from_motor() -> ArmStateFromMotor` | 电机回读 | 可能 | 一次性获取位置 + 速度 + 力矩 |
| `get_arm_state_cached() -> ArmStateFromMotor` | 控制循环缓存 | 否 | **推荐**用于 GUI / 数据采集线程的高频轮询 |
| `get_end_effector_pose() -> Pose` | 实时状态 / 内部正运动学 | 可能 | 末端位姿读取 |
| `get_end_effector_pose_cached() -> Pose` | 控制循环缓存 | 否 | 高频只读位姿查询 |
| `is_hardware_connected() -> bool` | 总线心跳 | 否 | 启动 / 故障检测 |

> 失败时 `JointArray` 长度为 0、位姿可能回退为零位置与单位四元数、`ArmStateFromMotor` 三个 `JointArray` 同时为 0；调用方应用 `len(...)` 防御。

---

## 六、`OneroDragTeaching` 详解

record_file 与 replay_file 使用不含 .. 的相对路径，例如 teach.bin；Linux 绝对路径会被 SDK 拒绝。录制文件是 SDK 二进制轨迹格式，不能按 CSV 文本解析。


```python
class OneroDragTeaching:
    def __init__(self) -> None: ...

    def initialize  (self, dof: int, record_file: str, time_step: float = 0.01) -> bool: ...
    def set_hardware(self, device: str, urdf_path: str, robot_model: str,
                     mount_orientation: str = "horizontal",
                     with_gripper: bool = False) -> bool: ...

    def set_gripper_teaching_mode(self, mode: GripperTeachingMode) -> int: ...
    def set_gripper_target(self, percent: float) -> int: ...
    def get_gripper_status(self) -> GripperStatus: ...

    def enable_motors  (self) -> int: ...
    def restore_arm    (self) -> int: ...
    def restore_arm    (self, target: list[float] | JointArray) -> int: ...
    def start_recording(self) -> int: ...
    def stop_recording (self) -> int: ...

    def set_replay_file(self, replay_file: str) -> None: ...
    def start_replay   (self) -> int: ...
    def stop_replay    (self) -> int: ...

    def handle_command (self, cmd: int) -> int: ...
    @staticmethod
    def handle_command_dual(left: "OneroDragTeaching",
                            right: "OneroDragTeaching",
                            cmd: int) -> int: ...
    def timer_callback (self) -> None: ...

    def get_state      (self) -> DragTeachingState: ...
    def is_initialized (self) -> bool: ...

    def update_joint_state(self, position: JointArray,
                           velocity: JointArray, effort: JointArray) -> None: ...
```

带夹爪示教：set_hardware(..., with_gripper=True) 选择同一设备会话及匹配的重力补偿缩放，但不自动录制夹爪。录制前可选 GripperTeachingMode.DISABLED（臂单独 V1）、POSITION（set_gripper_target 记录百分比目标）或 BACKDRIVE（零力矩手动开合）；后两者写 V2 轨迹并保存夹爪通道，V2 回放自动重放该通道。get_gripper_status().valid=False 时不可将数值视为有效反馈。

**典型流程**：

1. `drag = oneroarm.OneroDragTeaching()` → `drag.initialize(7, "teach.bin", 0.01)` → `drag.set_hardware(...)`。
2. `drag.enable_motors()`；如需先回零，再显式调用 `drag.restore_arm()`。
3. 录制：`drag.start_recording()` → 物理拖动 → `drag.stop_recording()`。
4. 回放：`drag.set_replay_file(path)` → `drag.start_replay()` → 必要时 `drag.stop_replay()`。
5. 周期循环：100 Hz 调用 `drag.timer_callback()`，并把电机回读 `drag.update_joint_state(...)` 喂入。

**双臂同步命令**：

`OneroDragTeaching.handle_command_dual(left, right, cmd)` 接受两个已初始化并完成 `set_hardware(...)` 的拖动示教实例。`cmd=1` 会在 SDK 内部对两臂执行并发 prepare，并用共享 `t0` 同步开始录制；`cmd=3` 走同步回放路径；`cmd=0/2` 分别用于双臂停止、停止录制。Python 侧不需要自己计算或传入 `steady_clock` 时间点。

---

## 七、完整示例

最小运动序列（参见 [`demo/python/movej.py`](../demo/python/movej.py) 同源）：

```python
import oneroarm

cfg = oneroarm.OneroConfig()
cfg.device      = "/dev/ttyACM0"      # Windows: "COM3"
cfg.robot_model = "a1_r"
cfg.version     = "A1"
cfg.dof         = 7
# model_description_path 留空 → 走 SDK 内置；如需切换可显式赋值

arm = oneroarm.OneroArm(cfg)
assert arm.enable_motors(), "enable_motors failed"

# 关节空间
arm.movej([0.0] * 7, speed_scale=0.5)

# 笛卡尔直线
p = oneroarm.Pose()
p.x, p.y, p.z = 0.30, 0.00, 0.40
p.qw           = 1.0
arm.movel(p, speed_scale=0.5)

# 状态查询
st = arm.get_arm_state_cached()
if len(st.positions) > 0:
    print("q[0] =", st.positions[0])

arm.disable_motors()
```

---

## 八、CAN 帧示例

与电机 / 夹爪共用同一根 SLCAN 串口；可用于向同总线上的自定义节点（MCU、传感器、IO 板等）发送 11-bit 标准 CAN 帧并接收响应。共同语义（保留 ID 集、回调线程、payload 生命周期、异常处理）见根 [`README.md`](../README.md#五原始-can-帧行为)。

### 8.1 方法签名

```python
class OneroArm:
    def send_can_frame(self, can_id: int,
                       payload: bytes | bytearray | memoryview) -> int: ...
    def register_can_frame_callback(
            self,
            callback: Callable[[int, bytes], None]) -> int: ...
    def clear_can_frame_callback(self) -> int: ...
    def pump_can_bus(self, timeout_ms: int) -> int: ...
```

### 8.2 参数细节

| 方法 | 参数 / 行为 |
|---|---|
| `send_can_frame(can_id, payload)` | `can_id ∈ [0, 0x7FF]`，**不能**落在保留集（含 arm 电机、夹爪 `0x08/0x18`、触觉回包 `0x418`、`0x7FF`）；`payload` 接受 `bytes` / `bytearray` / `memoryview` 等任何 buffer-like 对象，长度 ≤ 8。同步发送，返回时 SDK 已拷贝 payload，调用方可立即释放底层缓冲 |
| `register_can_frame_callback(callback)` | 重复注册替换前一个；传 `None` 等价 `clear_can_frame_callback()`。SDK 在派发前会拷贝 payload 为 `bytes`，因此回调结束后 `payload` 仍然有效；**回调内只支持注册/清除回调重入；禁止** `arm` 任何发送 / 运动控制方法。回调中抛出的异常会被 SDK 静默吞掉，业务侧应自行 `try/except` |
| `clear_can_frame_callback()` | 清除已注册的回调（user_data 不再被引用） |
| `pump_can_bus(timeout_ms)` | `timeout_ms == 0` = 一次非阻塞 try-recv；`pump_can_bus` 内部会释放 GIL，让其他 Python 线程在等待期间继续工作。回调由独立 dispatcher worker 取得 GIL 后执行 |

### 8.3 完整示例

```python
import oneroarm

cfg = oneroarm.OneroConfig()
cfg.device      = "/dev/ttyACM0"
cfg.robot_model = "a1_r"
cfg.dof         = 7
arm = oneroarm.OneroArm(cfg)

def on_frame(can_id: int, data: bytes) -> None:
    try:
        print(f"rx 0x{can_id:X} len={len(data)} {data.hex()}")
    except Exception as e:
        print("user callback error:", e)        # SDK 会吞掉未捕获异常

arm.register_can_frame_callback(on_frame)

rc = arm.send_can_frame(0x100, b"\x01\x02\x03\x04")     # 0 = 成功
if rc != 0:
    print(f"send failed: {rc}")

arm.pump_can_bus(50)        # 50 ms 内派发到回调
arm.clear_can_frame_callback()
```

---

## 九、错误诊断

| 现象 | 原因 / 处理 |
|---|---|
| `PackagesNotFoundError: oneroarm` | 用**实际**相对/绝对路径作为 `-c` channel；`python/conda_channel/linux/` 下应有 `linux-64/` + `noarch/` 子目录及 `repodata.json` |
| `UnsatisfiableError` / `LibMambaUnsatisfiableError` | 创建全新环境：`conda create -n oneroarm python=3.12 -y`；安装命令必须保留 `-c conda-forge` |
| `ImportError: DLL load failed`（Windows） | 确认已 `conda activate oneroarm`，IDE 解释器是该环境的 Python |
| `OSError: cannot find liboneroarm` 或 `Symbol not found` | 核对已激活的环境与安装渠道，按 §2 的本地 channel 命令重新解算匹配依赖 |
| 主臂和独立夹爪 wheel 同进程导入报 GripperStatus already registered | 检查是否仍安装旧夹爪 wheel；从本包重新安装当前 wheel，并在新进程验证两个导入顺序；参见 [发布说明](../RELEASE_NOTES.md) |
| `Serial device not found` | Linux：`ls /dev/ttyACM*`，必要时 `sudo chmod 666 /dev/ttyACM0` 或加入 `dialout` 组。Windows：设备管理器查 COM 端口号，更新 `cfg.device` |
| `enable_motors()` 返回 `False` | 检查串口设备路径、波特率、急停按钮；先 `arm.is_hardware_connected()` 验证 |
| `send_can_frame` 返回 `-12` | `can_id` 落在保留集（电机 / 夹爪 / 触觉回包 / 操纵杆 / `0x7FF`） |
| 回调收不到帧 | 对端发送的 CAN ID 不能在 SDK 保留集；运动控制空闲期主动 `arm.pump_can_bus(timeout_ms)` |
| 回调中的异常被吞掉、看不到 traceback | 在回调内自己 `try/except` 并打印 / 写日志 |
| 启动报 `Pinocchio model load failed` / 找不到 URDF | 默认走 SDK 内置；若被覆盖可设 `ONERO_DESCRIPTION_PATH` 或 `cfg.model_description_path` |


## ServoJ 运动中停止与通用取消

ServoJ 停止从当前连续指令位置、速度和加速度规划限加加速度制动，允许沿运动方向到达可制动的停止位置，不回到停止请求时的位置。`stop_servoj()` 阻塞等待受控制动及终拍完成；成功返回 `0` 后状态为 IDLE、命令速度和加速度为零、机械臂命令资源已释放；制动故障返回负错误码。停止时长取决于当时速度、加速度以及用户限制与 SDK 硬限制的交集，没有固定的通用毫秒承诺。

通用取消只请求取消 MoveJ/L/P/C、轨迹执行或 ServoP；返回 `0` 表示请求已记录，不表示运动已经停止，无活动运动时也返回 `0`。ServoJ 会话活动期间（含 RUNNING、BRAKING、HOLDING）返回 `-8 BUSY`，不设置取消信号、不改变该会话；必须调用专用 `stop_servoj()` / `onero_stop_servoj()`。

## ServoJ 运动中更新目标

每个 10 ms 控制周期读取最新有效目标；同周期多次更新覆盖旧目标，不排队逐点执行。运动中换目标时，从上一拍连续指令的 q/dq/ddq 重新规划到新目标，不要求先完成旧目标；刷新相同目标只续期，不重复规划。

当前跟踪使用静态集成的 Ruckig Community 0.15.3，保留 SDK 的速度、加速度、jerk 限制；使用前检查完整规划路径及制动包络的关节限位，每拍继续检查。无需额外安装 Ruckig 或联网。可行的前向换目标用例不再出现原先约 1 rad 的异常超调；换近目标或反向时，惯性和动态限制仍可能要求先制动一段距离。

`servoj()` 返回 `0` 表示接受目标。零目标速度的轨迹完成后进入 HOLDING；非零目标速度到达目标后仍处于 RUNNING，延续末速度，直至新目标、有效期到期或专用停止。规划路径或制动包络越界时，状态包含 JOINT_POSITION，`last_error=-7`，不会下发该候选路径；其他规划不可行仍报告 OTG_INFEASIBLE。请持续查询状态和反馈。

### NumPy 与 wheel 的 C++ 运行库

主臂 wheel build 5、独立夹爪 wheel build 3 保留标准 `libstdc++.so.6` / `libgcc_s.so.1` SONAME；两模块随包运行库保持相同内容，NumPy 已加载兼容运行库时复用该提供者，避免哈希别名加载第二套运行库。无需调整 NumPy/SDK 导入顺序。已有安装须同时强制重装两个 wheel 并重启进程。Linux x86_64 扩展至少需要 GLIBCXX_3.4.32。若环境预载的运行库缺少 GLIBCXX/CXXABI 所需符号，应使用匹配 Conda 包或更新该环境运行库；不要混用不兼容的旧 C++ 运行库。

ServoJ 的 `limit_flags` 保留当前会话的累计事件。发生命令超时后，即使新目标已恢复跟踪，`COMMAND_TIMEOUT` 仍可能保留；应联合当前 `state`、`command_age_s`、序号和 `last_error` 判断。成功专用停止清除该标志；它不是新的停止请求。
