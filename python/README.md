# OneroArm Python 包

预编译 Python 扩展模块（pybind11）+ URDF/mesh 资源。三层公共面与返回值约定见仓库根 [`README.md`](../README.md)。

> **模块名**：`import oneroarm`（pybind11 原生扩展，包名 `oneroarm-1.0.0`）。

---

## 目录

- [一、目录结构](#一目录结构)
- [二、安装](#二安装)
- [三、运行期资源定位](#三运行期资源定位)
- [四、数据类](#四数据类)
- [五、`OneroArm` 详解](#五oneroarm-详解)
- [六、`OneroDragTeaching` 详解](#六onerodragteaching-详解)
- [七、完整示例](#七完整示例)
- [八、CAN 帧示例](#八can-帧示例)
- [九、错误诊断](#九错误诊断)

---

## 一、目录结构

```
python/
├── conda_channel/                          # 离线 conda 渠道（x86_64 / arm64 / Windows）
│   ├── linux/{linux-64, linux-aarch64, noarch}/
│   └── windows/{win-64, noarch}/
└── wheels/
    └── linux-riscv64/oneroarm-*.whl
```

类型存根 `oneroarm.pyi` 由 conda 包 / wheel 自带，安装后位于
`<env>/lib/python3.12/site-packages/oneroarm.pyi`；预编译扩展位于同目录的
`oneroarm.cpython-312-*.so`（Linux）或 `oneroarm.cp312-*.pyd`（Windows）。

`oneroarm_description`（URDF / mesh）也一并打包到
`<env>/lib/python3.12/site-packages/share/oneroarm_description/`。

---

## 二、安装

```bash
conda create -n oneroarm python=3.12 -y
conda activate oneroarm

# Linux
conda install -c conda-forge -c ./python/conda_channel/linux oneroarm -y

# Windows (PowerShell / cmd)
conda install -c conda-forge -c .\python\conda_channel\windows oneroarm -y
```

> 也可用 `micromamba install ...` 替代 `conda install`。
>
> 安装时**必须保留** `-c conda-forge`，本地 channel 仅提供 `oneroarm` 自身，依赖（pinocchio / hpp-fcl / boost / 等）从 conda-forge 拉取。

### 2.1 安装自检

```bash
python -c "import oneroarm; print('OK,', oneroarm.__file__)"
```

无机械臂连接时 `OneroArm(cfg)` 构造可能不抛异常，但后续 `enable_motors()` 会返回 `False`——这是预期行为，可仅用于环境自检。

### 2.2 RISC-V (linux-riscv64)：用 wheel 安装

conda-forge **没有** riscv64 的 `oneroarm` 及其依赖包，所以 riscv 上**不走 conda**，
改用随包提供的 **linux-riscv64 瘦 wheel**：

```bash
# 1. 进入仓库根目录，一键准备 RISC-V 第三方依赖
cd /path/to/OneroArm_API_for_Users
sudo ./scripts/install_riscv_dependencies.sh
export LD_LIBRARY_PATH=/opt/onero-deps/lib:$LD_LIBRARY_PATH

# 2. 使用 Python 3.12；wheel 标签是 cp312
python3.12 -m venv .venv_oneroarm
. .venv_oneroarm/bin/activate
python -m pip install --upgrade pip

# 3. 装瘦 wheel（仅含 oneroarm.so + .pyi，不打包第三方动态库）
#    --no-deps 用于避免 pip 在 riscv64 上源码编 numpy。
python -m pip install --no-deps ./python/wheels/linux-riscv64/oneroarm-*.whl

# 4. 自检
python -c "import oneroarm; print('OK,', oneroarm.__file__)"
```

> ⚠ wheel 是「瘦」的：`import oneroarm` 时由动态加载器从你的 `LD_LIBRARY_PATH`
> 解析 `libpinocchio_default.so.3.1.0` 等。版本须严格匹配（pinocchio 必须 `v3.1.0`），
> 否则报 `ImportError: ... undefined symbol` 或 `cannot open shared object`。
> 排错见第九节同款条目。
>
> wheel 文件名中的 `cp312` / `linux_riscv64` 是 pip 识别兼容性的标准标签，请不要手动改名；
> 安装时使用上面的 `oneroarm-*.whl` 通配符即可。
>
> 若业务代码确实需要 `numpy` / `loguru`，建议优先使用系统包或本地预编 wheel；
> 直接 `pip install numpy` 可能在 riscv64 上触发源码编译，耗时较长且容易缺 `meson-python`。

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
ja  = oneroarm.JointArray()          # 类 list 容器（也可以直接传 list[float]）
p   = oneroarm.Pose()                # x, y, z, qw, qx, qy, qz
fp  = oneroarm.ForcePosition()       # force_position_flag / direction / force
st  = oneroarm.ArmStateFromMotor()   # positions / velocities / torques
tp  = oneroarm.TrajectoryPoint()     # position / velocity / acceleration

oneroarm.DragTeachingState.IDLE       # 0
oneroarm.DragTeachingState.RECORDING  # 1
oneroarm.DragTeachingState.REPLAYING  # 2
```

### 4.1 `OneroConfig` 字段

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|:---:|---|---|
| `device` | `str` | ✅ | `""` | 串口设备路径。Linux `/dev/ttyACM0`，Windows `COM3` |
| `robot_model` | `str` | ✅ | `""` | `"a1_l"` / `"a1_r"`，子串包含、大小写敏感 |
| `dof` | `int` | – | `7` | 自由度，仅支持 `7` |
| `baud_rate` | `int` | – | `921600` | 串口波特率 |
| `urdf_path` | `str` | – | `""` | 留空 → 由 `model_description_path` + `version` 自动定位 |
| `version` | `str` | – | `""` | URDF 子目录名（`"A1"`），留空时按 `robot_model` 推断 |
| `mount_orientation` | `str` | – | `"vertical"` | `"vertical"` 立装 / `"horizontal"` 卧装。**装错将导致重力补偿方向错误** |
| `mit_kp` | `list[float]` | – | 全 `0` | MIT 比例增益。`==0` 视为该关节未传入 |
| `mit_kd` | `list[float]` | – | 全 `0` | MIT 微分增益。同上 |
| `model_description_path` | `str` | – | `""` | `oneroarm_description` 根目录。留空 → SDK 内置 |

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
    def __init__(self, config: OneroConfig) -> None: ...
```

构造时按 `OneroConfig` 创建底层 robot handle；Python 层无 `valid()`，构造失败会抛异常。运动 / 状态方法既接受 `JointArray`，也接受 `list[float]`（自动转换）。

### 5.1 电机使能

| 方法 | 返回 | 说明 |
|---|---|---|
| `enable_motors() -> bool` | `True` 成功 | 同步等待硬件应答；首次使能可能耗时秒级 |
| `disable_motors() -> bool` | `True` 成功 | 同步阻塞 |
| `restore_arm() -> int` | `MoveResult` | 以安全速度回默认零位 |
| `restore_arm(target) -> int` | `MoveResult` | 以安全速度回指定关节目标 |

> Python 的 `enable_motors()` / `disable_motors()` 仍返回 `bool`：`True` 即成功，`False` 即任何非 0 错误码。

### 5.2 运动控制

```python
def movej(self, target: list[float] | JointArray,
          speed_scale: float = 1.0, trajectory_connect: int = 0) -> int: ...
def movel(self, pose: Pose,
          speed_scale: float = 1.0, trajectory_connect: int = 0) -> int: ...
def movep(self, pose: Pose,
          speed_scale: float = 1.0, trajectory_connect: int = 0) -> int: ...
def estimate_movej_duration(self, target: list[float] | JointArray,
                            speed_scale: float = 1.0) -> float: ...
def force_position_movel(self, pose: Pose,
                         speed_scale: float = 1.0, trajectory_connect: int = 0) -> int: ...
```

返回 `MoveResult`（`0=成功`，负数错误码见 §4.2）。语义、参数约束（`speed_scale` 建议 `(0, 2.0]`，`trajectory_connect` `0` 立即/`1` 缓冲）与 C++ 一致。

### 5.3 力-位混合控制

```python
def set_force_position_control (self, force_position: ForcePosition) -> int: ...
def stop_force_position_control(self) -> int: ...
```

调用顺序：`set_force_position_control(fp)` → `force_position_movel(pose, ...)` 或 `movel(...)` → 工序结束 `stop_force_position_control()`。

### 5.4 缓冲与轨迹

```python
def send_trajectory_point      (self, q: JointArray, dq: JointArray) -> int: ...
def send_trajectory            (self, trajectory: list[TrajectoryPoint]) -> int: ...
def execute_buffered_trajectory(self) -> int: ...
def clear_trajectory_buffer    (self) -> int: ...
def reset_stop_signal          (self) -> None: ...
def cancel_trajectory          (self) -> int: ...
```

### 5.5 状态查询

| 方法 | 数据源 | 是否触发 CAN I/O | 适用场景 |
|---|---|:---:|---|
| `get_joint_positions() -> JointArray` | 上位机内部缓存 | 否 | 通用查询，最低开销 |
| `get_joint_positions_from_motors() -> JointArray` | 电机回读 |  | 与外部传感器对齐 |
| `get_joint_velocities() -> JointArray` | 电机回读 |  | 速度环 / 监督控制 |
| `get_arm_state_from_motor() -> ArmStateFromMotor` | 电机回读 |  | 一次性获取位置 + 速度 + 力矩 |
| `get_arm_state_cached() -> ArmStateFromMotor` | 控制循环缓存 | 否 | **推荐**用于 GUI / 数据采集线程的高频轮询 |
| `get_end_effector_pose() -> Pose` | 实时状态 / 内部正运动学 | 可能 | 末端位姿读取 |
| `get_end_effector_pose_cached() -> Pose` | 控制循环缓存 | 否 | 高频只读位姿查询 |
| `is_hardware_connected() -> bool` | 总线心跳 | 否 | 启动 / 故障检测 |

> 失败时 `JointArray` 长度为 0、`Pose` 全零、`ArmStateFromMotor` 三个 `JointArray` 同时为 0；调用方应用 `len(...)` 防御。

---

## 六、`OneroDragTeaching` 详解

```python
class OneroDragTeaching:
    def __init__(self) -> None: ...

    def initialize  (self, dof: int, record_file: str, time_step: float = 0.01) -> bool: ...
    def set_hardware(self, device: str, urdf_path: str, robot_model: str,
                     mount_orientation: str = "horizontal") -> bool: ...

    def enable_motors  (self) -> int: ...
    def restore_arm    (self) -> int: ...
    def restore_arm    (self, target: list[float] | JointArray) -> int: ...
    def start_recording(self) -> int: ...
    def stop_recording (self) -> int: ...

    def set_replay_file(self, replay_file: str) -> None: ...
    def start_replay   (self) -> int: ...
    def stop_replay    (self) -> int: ...

    def handle_command (self, cmd: int) -> int: ...
    def timer_callback (self) -> None: ...

    def get_state      (self) -> DragTeachingState: ...
    def is_initialized (self) -> bool: ...

    def update_joint_state(self, position: JointArray,
                           velocity: JointArray, effort: JointArray) -> None: ...
```

**典型流程**：

1. `drag = oneroarm.OneroDragTeaching()` → `drag.initialize(7, "/tmp/teach.csv", 0.01)` → `drag.set_hardware(...)`。
2. `drag.enable_motors()`；如需先回零，再显式调用 `drag.restore_arm()`。
3. 录制：`drag.start_recording()` → 物理拖动 → `drag.stop_recording()`。
4. 回放：`drag.set_replay_file(path)` → `drag.start_replay()` → 必要时 `drag.stop_replay()`。
5. 周期循环：100 Hz 调用 `drag.timer_callback()`，并把电机回读 `drag.update_joint_state(...)` 喂入。

---

## 七、完整示例

最小运动序列（与 [`demo/arm_control_demo.py`](../demo/arm_control_demo.py) 同源）：

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

# 力-位混合
fp = oneroarm.ForcePosition()
fp.force_position_flag = True
fp.direction           = 2            # z 轴
fp.force               = 5.0          # 5 N
arm.set_force_position_control(fp)
arm.force_position_movel(p, speed_scale=0.3)
arm.stop_force_position_control()

# 状态查询
st = arm.get_arm_state_cached()
if len(st.positions) > 0:
    print("q[0] =", st.positions[0])

arm.disable_motors()
```

---

## 八、CAN 帧示例

与电机 / 夹爪共用同一根 SLCAN 串口；可用于向同总线上的自定义节点（MCU、传感器、IO 板等）发送 11-bit 标准 CAN 帧并接收响应。共同语义（保留 ID 集、回调线程、payload 生命周期、异常处理）见根 [`README.md`](../README.md) §7。

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
| `send_can_frame(can_id, payload)` | `can_id ∈ [0, 0x7FF]`，**不能**落在保留集；`payload` 接受 `bytes` / `bytearray` / `memoryview` 等任何 buffer-like 对象，长度 ≤ 8。同步发送，返回时 SDK 已拷贝 payload，调用方可立即释放底层缓冲 |
| `register_can_frame_callback(callback)` | 重复注册替换前一个；传 `None` 等价 `clear_can_frame_callback()`。SDK 在派发前会拷贝 payload 为 `bytes`，因此回调结束后 `payload` 仍然有效；**回调内禁止重入** `arm` 任何发送 / 运动控制方法。回调中抛出的异常会被 SDK 静默吞掉，业务侧应自行 `try/except` |
| `clear_can_frame_callback()` | 清除已注册的回调（user_data 不再被引用） |
| `pump_can_bus(timeout_ms)` | `timeout_ms == 0` = 一次非阻塞 try-recv；`pump_can_bus` 内部会释放 GIL，让其他 Python 线程在等待期间继续工作。回调本身在重新获取 GIL 后执行 |

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
| `OSError: cannot find liboneroarm` 或 `Symbol not found` | 没安装传递依赖；conda env 内 `conda install -c conda-forge pinocchio hpp-fcl boost` 重装 |
| RISC-V `pip install` 卡在编 numpy / 报 `Cannot import 'mesonpy'` | RISC-V wheel 安装用 `python -m pip install --no-deps ...linux_riscv64.whl`；`numpy`/`loguru` 如确实需要再单独用系统包或本地 wheel 安装 |
| RISC-V `ImportError: libpinocchio_default.so.3.1.0: cannot open shared object file` | 未加载 `/opt/onero-deps/lib`；先执行 `export LD_LIBRARY_PATH=/opt/onero-deps/lib:$LD_LIBRARY_PATH`，并确认 `install_riscv_dependencies.sh` 已完成 |
| RISC-V wheel 报 `not a supported wheel on this platform` | Python 版本或平台不匹配；当前 wheel 是 `cp312` + `linux_riscv64`，请用 `python3.12` 且在 `riscv64` 系统安装 |
| `Serial device not found` | Linux：`ls /dev/ttyACM*`，必要时 `sudo chmod 666 /dev/ttyACM0` 或加入 `dialout` 组。Windows：设备管理器查 COM 端口号，更新 `cfg.device` |
| `enable_motors()` 返回 `False` | 检查串口设备路径、波特率、急停按钮；先 `arm.is_hardware_connected()` 验证 |
| `send_can_frame` 返回 `-12` | `can_id` 落在保留集（电机 / 夹爪 / 操纵杆 / `0x7FF`） |
| 回调收不到帧 | 对端发送的 CAN ID 不能在 SDK 保留集；运动控制空闲期主动 `arm.pump_can_bus(timeout_ms)` |
| 回调中的异常被吞掉、看不到 traceback | 在回调内自己 `try/except` 并打印 / 写日志 |
| 启动报 `Pinocchio model load failed` / 找不到 URDF | 默认走 SDK 内置；若被覆盖可设 `ONERO_DESCRIPTION_PATH` 或 `cfg.model_description_path` |
