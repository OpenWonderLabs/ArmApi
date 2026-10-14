# Python 示例

Ubuntu 24.04 riscv64 的 CPython 3.12 环境安装见 [RISC-V 安装说明](../../RISC_V_GUIDE.md)。

这些示例面向第一次使用 OneroArm SDK 的用户。每个文件都是自包含脚本，
只保留配置、核心 API 调用、返回值检查和资源释放，可以直接复制到自己的工程中。

运行前先修改脚本顶部的串口、机型、安装方向和运动目标，并确认机械臂
工作空间内没有人员或障碍物。示例中的 `cancel_trajectory()`、`stop_servop()` 和
`stop_servoj()` 都是软件停止，不是安全级急停。

## 基础运动

| 文件 | 覆盖接口 |
|---|---|
| `movej.py` | `estimate_movej_duration`、`movej` |
| `movel.py` | `movel` |
| `movep.py` | `movep` |
| `movec.py` | `movec` |
| `servoj.py` | `start_servoj`、`servoj`、状态查询、`stop_servoj` |
| `servop.py` | `start_servop`、`servop`、状态查询、`stop_servop` |
| `dual_arm_motion.py` | 两个独立机械臂实例的并发 `restore_arm` / `movej` |

普通双臂示例只是从两个宿主线程近同时启动两个阻塞调用，两臂仍各自规划、
各自走独立总线，不提供硬实时同步或共享轨迹时钟。

## 高级与可选功能

| 文件 | 覆盖接口 |
|---|---|
| `advanced/lifecycle.py` | 初始化、使能、状态读取、`restore_arm`、失能 |
| `advanced/buffered_motion.py` | `trajectory_connect=1`、执行/清空规划缓冲 |
| `advanced/joint_trajectory.py` | `send_trajectory_point`、`send_trajectory` |
| `advanced/mit_control.py` | `compute_gravity_torque`、`control_mit` |
| `advanced/cancel_motion.py` | `cancel_trajectory`、`reset_stop_signal` |
| `advanced/frame_transform.py` | Frame 四个纯坐标变换接口，不需要硬件 |
| `advanced/drag_teaching.py` | 单臂及夹爪回驱录制与回放 |
| `advanced/dual_arm_drag_teaching.py` | SDK 共享起始时间的双臂录制与回放 |
| `advanced/gripper.py` | 选配夹爪控制、状态与触觉读取 |
| `advanced/raw_can.py` | 非保留 ID 的原始 CAN 收发 |

`send_trajectory*` 和 `control_mit` 是直接控制接口，不属于
`trajectory_connect` 规划缓冲。调用方必须自行生成连续轨迹；
`send_trajectory_point` 和 `control_mit` 需要按至少 100 Hz 持续调用，
`send_trajectory` 则一次提交完整点列，由 SDK 按时间步执行。MoveC 不支持
`trajectory_connect=1`。

## 运行

在 Ubuntu 22.04+ 的 Linux x86_64 系统和 Python 3.12 环境中安装本仓 wheel。wheel 已包含主 SDK 所需的非系统动态库：

```bash
python3.12 -m pip install ./python/wheels/linux-x86_64/oneroarm-1.2.1-5-cp312-cp312-linux_x86_64.whl
```

然后从仓库根目录运行示例：

```bash
python demo/python/movej.py
python demo/python/servoj.py
python demo/python/advanced/frame_transform.py
```

运动示例会控制实机。运行前须按你的设备、机型和安装方向修改示例配置，并确认工作区与急停条件。坐标变换示例不连接机械臂。
