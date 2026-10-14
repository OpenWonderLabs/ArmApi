# WoanArm API for Users · 用户手册

本包是 A1 系列机械臂的 C、C++、Python 预编译 SDK，版本为 **1.2.1**。完整签名、安装与示例见 [C](c/README.md)、[C++](c++/README.md)、[Python](python/README.md)、[独立夹爪](gripper/README.md)及[示例](demo/README.md)。

## 1.2.1 更新

修复 ServoJ 停止异常及运动中切换目标的异常超调，明确停止和取消接口的返回语义。

- **在线换目标**：从连续指令 q/dq/ddq 重新规划完整限 jerk 轨迹；每拍采用最新目标，相同目标刷新只续期，提前检查路径及制动包络的关节限位。Ruckig 0.15.3 已静态集成，无额外运行依赖。
- **修复方式**：从连续指令位置、速度和加速度规划三阶段限加加速度制动，消除停止时反复重新追踪位置导致的速度换向；保留 SDK 原有动态限制。
- **返回约定**：`stop_servoj()` 成功返回 `0` 后进入 IDLE、速度和加速度归零并释放资源，故障返回负错误码；活动 ServoJ 的 `cancel_trajectory()` 返回 `-8 BUSY`，应使用专用停止。其他运动的取消返回 `0` 仅表示请求已记录。
- **验证结果**：四平台 suite 5 通过：60 次 NumPy 导入顺序检查、88 次超时恢复、132 次运动中换目标、88 次运动中停止；三个原生平台，RISC-V QEMU。真机与原生板卡验收不在本次范围。

## 一、交付范围

| 平台 | 机械臂 C/C++ | 独立夹爪 C/C++ | Python |
|---|---|---|---|
| Linux x86_64 / Ubuntu 22.04+ | 有 | 有 | 主 SDK Conda 3.10–3.13、wheel 3.12；夹爪 Conda/wheel 3.12 |
| Linux arm64 / Ubuntu 22.04+ | 有 | 有 | 主 SDK Conda 3.10–3.13；夹爪 Conda 3.12 |
| Windows x86_64 | 有 | 有 | 主 SDK Conda 3.10–3.13；夹爪 Conda 3.12 |
| Linux riscv64 / Ubuntu 24.04 | 有 | 有 | 主 SDK 和夹爪 wheel 3.12；无 Conda 包 |

c/include 是纯 C ABI，c++/include 是 C++17 API；同平台 C/C++ 库逐字节一致。python/ 和 gripper/python/ 提供运行包与类型存根。runtime/ 提供 x86_64、riscv64 的部分动态依赖，arm64 和 Windows 依赖匹配的 Conda 环境。

本包能够独立安装、编译调用方并运行，不需要 develop 或旧用户工程。交付树不含 SDK 核心实现源码；仍需公开头、二进制、模型及匹配的系统依赖。默认 A1 模型不含实物夹爪几何；自定义工具须配套正确的 URDF 和负载配置。

平台验证范围见 [发布说明](RELEASE_NOTES.md)与 [发布清单](RELEASE_MANIFEST.json)，校验值见 [SHA256SUMS](SHA256SUMS)。RISC-V 安装见 [专用指南](RISC_V_GUIDE.md)。离线调用验证不能代替实际硬件通信、运动及控制性能验收。


### 公共导出与运行库

Linux 主臂库导出公开 C 函数和 onero_api 的正式 C++ API；独立夹爪库使用以下名单，包含 const 方法：

~~~text
ONEROGRIPPER_1.2 {
    global:
        onerogripper_*;
        _ZN17onero_gripper_api12OneroGripper*;
        _ZNK17onero_gripper_api12OneroGripper*;
        _ZTIN17onero_gripper_api12OneroGripperE;
        _ZTSN17onero_gripper_api12OneroGripperE;
        _ZTVN17onero_gripper_api12OneroGripperE;
    local:
        *;
};
~~~

主臂公开 OneroArm、随臂 OneroGripper 的 const 方法同样包含对应 _ZNK9 前缀。每个 Linux 主臂库有 173 项动态导出，独立夹爪库有 24 项。Linux Python 扩展只导出对应 PyInit 入口；Windows 使用其平台公开包装类型与必要运行时导出。

同平台配对 wheel 使用一致的 C++ 运行库，四种共享夹爪状态类型采用模块隔离注册。升级时同时安装两个 wheel 并重启 Python 进程。x86_64 需要 Python 3.12、NumPy >=2,<2.3；RISC-V 的 NumPy 与系统依赖按专用指南配置。

Linux C++ 程序在链接期选择匹配的 libstdc++.so.6，并配置依赖搜索路径；仅设置 LD_LIBRARY_PATH 不够。命令见 [主臂 C++ 集成](c++/README.md)与[夹爪 C++ 集成](gripper/c++/README.md)。独立夹爪 C 创建函数返回非空句柄后仍须调用 onerogripper_valid 检查设备有效性。

## 二、语言入口、单位与配置

| 层 | 入口 | 用途 |
|---|---|---|
| C | onero_create_robot、onero_*，见 [纯 C 头](c/include/onero_interface_c.h) | C 工程与 Rust/Go/C# 等 FFI |
| C++ | onero_api::OneroArm、OneroDragTeaching，见 [C++ 头](c++/include/onero_interface_cpp.h) | C++17 工程，RAII 生命周期 |
| Python | import oneroarm，见 [类型存根](python/oneroarm.pyi) | 脚本、数据采集和上层应用 |

关节角、角速度、力矩单位依次为 rad、rad/s、N·m；笛卡尔位置为 m；姿态四元数顺序为 (qw, qx, qy, qz)。MoveC 与 ServoP 接收绝对 base_T_link7 位姿；ServoP v1 控制 Link7/flange 原点，**不自动叠加 TCP 偏移**。需要工具坐标时可先用 Frame 转换函数换算。

三个语言层的配置语义相近，C 与 C++ 结构体布局不能相互强制转换。C 侧先将 onero_config_t 清零。关键字段：

| 字段 | 约定 |
|---|---|
| device | 实际串口路径；Linux 可用 /dev/serial/by-id/...，Windows 使用 COM 端口 |
| robot_model、dof、version | A1 左/右臂用 a1_l / a1_r、7 轴、A1；按实物选择 |
| baud_rate | 0 使用 SDK 默认 921600；非默认值应与设备一致 |
| mount_orientation | vertical 或 horizontal；影响重力方向 |
| urdf_path | 显式 URDF 文件；留空时从模型资源目录寻找 |
| model_description_path | 显式资源根目录；留空时查 SDK 内置 share/oneroarm_description |
| mit_kp / mit_kd | 逐轴 MIT 增益；未提供时走 SDK 默认值 |
| with_gripper | 让随臂夹爪复用同一设备会话；夹爪不是第八轴 |
| simulation_mode | C++ 与 Python 的无硬件仿真配置；纯 C 配置结构没有此字段 |

资源查找依次考虑显式配置、ONERO_DESCRIPTION_PATH / ONERO_DESCRIPTION_DIR、库相对路径和历史回退路径。使用自定义 URDF 时，路径、模型名称、安装方向和夹爪负载必须互相匹配。内置左右臂模型结构图见 [图 1](doc/oneroarm_description1.png)与[图 2](doc/oneroarm_description2.png)。

## 三、返回值、生命周期与并发

MoveResult（C 中对应 ONERO_ERR_*）：

| 值 | 名称 | 常见含义 |
|---:|---|---|
| 0 | SUCCESS | 阻塞运动完成，或在线目标已被接受；具体看接口契约 |
| -1 | INVALID_PARAMS | 参数、数组长度、速度或模式非法 |
| -2 | IK_FAILED | 笛卡尔路径逆解失败 |
| -3 | COLLISION_DETECTED | 碰撞/路径安全预检拒绝 |
| -4 | EXECUTION_FAILED | 控制发送或执行失败 |
| -5 | TIMEOUT | 等待应答或执行超时 |
| -6 | INTERRUPTED | 被取消或中断 |
| -7 | JOINT_LIMIT_EXCEEDED | 关节目标越限 |
| -8 | BUSY | 同一设备会话已有冲突的命令所有者 |

原始 CAN 返回码：0 成功；-10 长度错误；-11 ID 越界；-12 使用保留 ID；-13 串口未打开；-14 发送失败。部分总线调用也可能返回 -8 BUSY。详细约束见各语言文档及头文件。

创建句柄/实例后先检查是否成功，再检查连接和反馈；使能电机与回零是分开的操作。使能、失能、销毁都不应被理解为自动回零或安全级急停。MoveJ/L/P/C 等阻塞调用返回后应读取实际反馈。ServoJ/P 的更新调用返回 0 **仅表示 SDK 接受了目标**，需检查 status 的状态、序号、错误码和 limit_flags。stop_servoj、stop_servop 与 cancel_trajectory 是软件控制停止，不是安全级急停。

同一会话的机械臂命令经过 SDK 仲裁，冲突返回 BUSY；机械臂与夹爪各有资源域，并共享唯一总线。查询缓存状态不会触发 CAN I/O，适合 UI/采集轮询；fresh 查询可能占用总线。销毁前应停止在线控制、清理回调，并避免再使用旧句柄。

## 四、机械臂接口速查

### 4.1 运动、缓冲与在线伺服

| C++ 方法（C/Python 有对应入口） | 输入 | 结果与动作 |
|---|---|---|
| enable_motors / disable_motors | 无 | 使能/失能机械臂关节；不自动回零 |
| restore_arm / restore_arm(target) | 默认位姿或关节角数组 | 阻塞回到指定关节位 |
| movej(target, speed_scale, trajectory_connect) | dof 个目标关节角 | 关节空间规划，不保证 TCP 直线 |
| movel(pose, speed_scale, trajectory_connect) | 绝对 Link7 位姿 | 规划末端直线，须通过逆解与路径预检 |
| movep(pose, speed_scale, trajectory_connect) | 绝对 Link7 位姿 | 末端点到点，不保证中间为直线 |
| movec(via, target, speed_scale, 0) | 经过点和终点的绝对 Link7 位姿 | 从新鲜反馈起点出发走圆弧；不支持整圆或轨迹缓冲 |
| estimate_movej_duration(target, speed_scale) | 目标关节角 | 估算时长，不下发运动 |
| execute_buffered_trajectory / clear_trajectory_buffer | 无 | 执行或清空 MoveJ/L/P 的 trajectory_connect 缓冲 |
| cancel_trajectory / reset_stop_signal | 无 | 请求取消 Move/轨迹或 ServoP；活动 ServoJ 返回 -8，使用 stop_servoj；按接口要求清除停止信号 |
| send_trajectory_point(q, dq) / send_trajectory(points) | 已生成的关节轨迹 | 直接轨迹控制；与 MoveJ/L/P 的规划缓冲不同 |
| control_mit(kp,kd,q,dq,tau) | 五个 dof 长度数组 | 底层 MIT 力位混合；调用方负责持续、连续地下发 |
| compute_gravity_torque(q) | 当前关节角 | 计算模型重力力矩；可作为 MIT 前馈，须核对实际负载 |

speed_scale 默认 1.0，具体有效范围由 SDK 校验与模型硬限制决定；它不是最终实测速度的保证。trajectory_connect=1 只适用于 MoveJ/L/P。调用 direct MIT、轨迹或在线伺服前需理解周期和命令所有权，不能与另一机械臂运动同时占用同一命令域。

| 在线接口 | 标准顺序 | 关键输入与状态 |
|---|---|---|
| ServoJ | start_servoj(limits) → 周期性 servoj(target_q, target_dq, valid_for_seconds) → get_servoj_status() → stop_servoj() | 关节目标；速度、加速度、加加速度请求与 SDK 硬限制取交集；状态含 accepted/applied sequence、帧数、超时和限制标志 |
| ServoP | start_servop() → 周期性 servop(pose, limits) → get_servop_status() → stop_servop() | 绝对 Link7 位姿；线/角速度与加速度请求；状态含目标、实际位姿、可行性比例和限制标志 |

在线更新不是阻塞到位指令。超时、反馈过期、关节界限或轨迹生成失败可触发减速/保持/故障；以状态结构和反馈判断，不以一次返回 0 判断到位。

### 4.2 Frame、状态与末端

Frame 提供 transform_pose、apply_cartesian_delta、flange_pose_to_tool、tool_pose_to_flange 四个纯计算入口，不连接设备。可在 BASE、WORLD、TOOL 间换算；WORLD 必须提供有效标定，TOOL 变换必须提供当前锚点。详细字段见各语言头文件/类型存根和 [Frame 示例](demo/python/advanced/frame_transform.py)。

状态入口包括 get_joint_positions、get_joint_positions_from_motors、get_joint_velocities、get_arm_state_from_motor、get_arm_state_cached、get_end_effector_pose、get_end_effector_pose_cached 与 is_hardware_connected。cached 方法不主动访问总线；数据还未建立时应检查数组长度或 valid 标志，不要把默认值当实时反馈。

随臂夹爪须用 with_gripper=true 创建，之后通过 arm.gripper()（C++）或 arm.gripper（Python）取得。支持独立 enable/disable、set_position、move_position、force_control、status 和 get_tactile；使能臂关节不会自动使能夹爪。独立夹爪包见 [gripper/](gripper/README.md)。夹爪不属于机械臂 dof，独立夹爪与随臂夹爪不应同时争用同一物理设备。

### 4.3 拖动示教

OneroDragTeaching 支持 initialize、set_hardware、enable_motors、restore_arm、start/stop_recording、set_replay_file、start/stop_replay、handle_command、timer_callback、get_state，以及双臂共享时间基准回放。带夹爪时 set_hardware(..., with_gripper=true) 选择匹配的会话与重力补偿参数，**不会自动开启夹爪录制**。录制前再选 DISABLED（臂单独 V1）、POSITION（记录夹爪目标）或 BACKDRIVE（零力矩手动开合），POSITION 可用 set_gripper_target(0..100) 指定目标；V2 文件保存臂与夹爪通道，回放时自动应用已录制通道。不能把带夹爪配置等同于已验证的重力补偿效果；须在实物上验证负载与反馈。

## 五、原始 CAN 帧行为

四个接口为 send_can_frame、register_can_frame_callback、clear_can_frame_callback、pump_can_bus。仅允许 11-bit 标准帧、0..8 字节、非 SDK 保留 ID；保留 ID 含电机、夹爪、触觉、操纵杆及 0x7FF。接收的用户帧进入每个 DeviceSession 的独立 callback worker；队列上限 64，满时丢弃最旧未开始帧。C/C++ 回调中的 payload 指针只在调用期间有效，Python 收到拥有内存的 bytes。回调内只把注册/清除回调作为受支持的重入调用，不在回调内调用运动、总线事务或销毁最后 owner。外部 clear/replace 返回前等待对应旧代正在执行的回调结束。pump_can_bus(0) 为非阻塞轮询。

## 六、安装、验收与许可

- Linux x86_64 C/C++ 运行前按 [runtime 文档](runtime/README.md)设置 LD_LIBRARY_PATH；Linux arm64、Windows 使用匹配 Conda 环境提供运行依赖。
- Python 安装命令、Windows channel 路径和版本矩阵见 [Python 文档](python/README.md)；三平台 Python 3.12 的 [精确环境与安装步骤](python/environments/README.md)可复现第三方依赖。
- Linux x86_64 的主臂与夹爪独立 wheel 已通过单独导入和两种顺序的联合导入；同平台 Conda 包联合导入也通过。验证范围见 [发布说明](RELEASE_NOTES.md)。
- 已完成的离线检查不等于真机运动验收。真机使用前核对设备、机型、安装方向、URDF、夹爪负载、工作空间和急停。
- 许可证见 [LICENSES/](LICENSES/)；版本和构建来源见 [VERSION](VERSION)、[RELEASE_MANIFEST.json](RELEASE_MANIFEST.json)。

仓库维护和交付核对流程见 [MAINTAINERS.md](MAINTAINERS.md)。


## ServoJ 运动中停止与通用取消

ServoJ 停止从当前连续指令位置、速度和加速度规划限加加速度制动，允许沿运动方向到达可制动的停止位置，不回到停止请求时的位置。`stop_servoj()` 阻塞等待受控制动及终拍完成；成功返回 `0` 后状态为 IDLE、命令速度和加速度为零、机械臂命令资源已释放；制动故障返回负错误码。停止时长取决于当时速度、加速度以及用户限制与 SDK 硬限制的交集，没有固定的通用毫秒承诺。

通用取消只请求取消 MoveJ/L/P/C、轨迹执行或 ServoP；返回 `0` 表示请求已记录，不表示运动已经停止，无活动运动时也返回 `0`。ServoJ 会话活动期间（含 RUNNING、BRAKING、HOLDING）返回 `-8 BUSY`，不设置取消信号、不改变该会话；必须调用专用 `stop_servoj()` / `onero_stop_servoj()`。

本次另修复 NumPy 先导入后构造机械臂时的 wheel 运行库冲突，统一标准 C++ SONAME；主臂 wheel build 5、独立夹爪 build 3，Conda 与 C/C++ 运行实现未变化。超时恢复与 NumPy 导入检查已纳入 suite 5，实际依赖记录自动生成。旧安装请按 Python 文档同时强制重装两个 wheel，并重启进程。
