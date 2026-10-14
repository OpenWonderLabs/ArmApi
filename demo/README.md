# SDK 示例使用说明

Ubuntu 24.04 riscv64 可由本目录 CMake 自动选择对应库；环境配置见 [RISC-V 安装说明](../RISC_V_GUIDE.md)。

本目录提供三种语言的接口示例。C 和 C++ 使用同一组 11 个主题，Python 按基础运动与高级功能分目录；详细清单见 [Python 示例](python/README.md)。示例中的位姿和设备名只是演示输入，运行运动程序前须按实际机械臂、安装方向、工具和工作区核对。

## 一、示例索引

| C/C++ 名称 | 演示接口 | 运行效果 |
|---|---|---|
| full_demo | restore_arm、MoveJ、MoveP、MoveL | 顺序执行多个阻塞运动 |
| movej_demo | MoveJ | 关节空间到目标，末端路径不保证直线 |
| movep_demo | MoveP | 笛卡尔点到点 |
| movel_demo | MoveL | 笛卡尔直线 |
| buffered_traj_demo | trajectory_connect、execute_buffered_trajectory | 将 MoveJ/L/P 路点放入规划缓冲后执行 |
| can_frame_demo | send_can_frame、callback、pump | 发送非保留 ID 帧，不使能臂电机 |
| drag_teaching_demo | 拖动示教录制、回放 | 依示例命令进入录制或回放 |
| frame_demo | BASE/WORLD/TOOL 坐标变换 | 纯计算，无硬件控制 |
| new_motion_demo | MoveC | 用当前反馈位姿、via、target 规划圆弧 |
| servoj_demo | ServoJ | 周期性关节目标跟踪与状态查询 |
| servop_demo | ServoP | 周期性笛卡尔目标跟踪与状态查询 |

每个主题有 demo/c/<name>_demo.c 和 demo/cpp/<name>_demo.cpp 两份源码。CMake 会在受支持平台生成同名的 _demo_c / _demo_cpp 可执行文件；Windows 跳过 C 版 drag_teaching_demo。new_motion、servoj、servop 是在线/新增接口示例；其结果须结合状态和真实反馈判断。软件 stop/cancel 不是安全级急停。

Python 的 movej.py、movel.py、movep.py、movec.py、servoj.py、servop.py 对应基本运动；advanced/ 包含缓冲轨迹、MIT、Frame、夹爪、拖动示教与原始 CAN。直接轨迹 send_trajectory_point / send_trajectory 不进入 trajectory_connect 的 MoveJ/L/P 规划缓冲。MoveC 不支持缓冲模式。接口参数与返回值见 [C](../c/README.md)、[C++](../c++/README.md)、[Python](../python/README.md) 文档。

## 二、编译 C/C++

C/C++ 示例的头文件已在包内；预编译动态库的传递依赖须由对应平台环境提供。Linux x86_64 可按 [runtime 说明](../runtime/README.md)设置 LD_LIBRARY_PATH。Linux arm64、Windows x86_64 使用匹配的 Conda 环境或等价的依赖集合。

从本目录执行：

```bash
cmake -S . -B build -G Ninja
cmake --build build
```

Linux arm64 配置时提供匹配 Conda 环境：cmake -S . -B build -G Ninja -DONERO_DEPENDENCY_DIR="$CONDA_PREFIX/lib"。Linux 的 C++ 链接会显式使用匹配的 libstdc++.so.6，并检查共享库的未解析符号。

CMake 按系统架构选择 c/ 与 c++/ 中的目标库；缺少对应二进制的平台会在配置阶段失败。Linux x86_64 如使用包内 runtime，可从 SDK 根目录执行：

```bash
export LD_LIBRARY_PATH="$PWD/runtime/linux-x86_64/lib"
./demo/build/frame_demo_cpp
```

frame_demo 为纯坐标计算。要运行运动示例，先检查相应源码的设备路径、机型、目标和 WOANARM_RUN_MOTION 门禁；例如 new_motion_demo 要传实际串口设备路径。确认目标对实机可达且工作区安全后再运行。

ServoJ/ServoP 的四份 C/C++ 示例使用独立命令行门禁，默认只输出用法并返回 2，不构造 SDK 对象。真机必须同时传 `--device DEVICE --run`，例如 `./demo/build/servoj_demo_c --device /dev/ttyACM0 --run`；机型固定为 A1 左臂、竖直安装、无夹爪，运行前核对源码配置。C 配置没有 `simulation_mode`，因此 CI 只编译链接 C 版实际调用并检查缺参退出，C 版运行验收须使用专用测试设备或测试设施。

C++ 支持显式无硬件仿真：

```bash
./demo/build/servoj_demo_cpp --simulate
./demo/build/servop_demo_cpp --simulate
```

四份示例均执行配置、有限值反馈检查、使能、启动、10 ms 周期更新、状态/反馈判定、停止、失能和销毁。ServoJ 在初始反馈基础上让首轴增加 0.01 rad，逐轴速度/加速度/加加速度限制分别为 0.1 rad/s、0.2 rad/s²、0.05 rad/s³，每次目标有效期 0.5 s；打印状态、已接受/已应用序号、下发计数、限制标志、错误码、命令年龄和反馈。ServoP 将初始末端 x 增加 0.001 m，输入是绝对 `base_T_link7` 位姿（米、wxyz 四元数，没有隐含 TCP 偏移）；四个软限制为 0.02 m/s、0.1 rad/s、0.05 m/s²、0.2 rad/s²。

示例最多等待 20 s，必须观察到新目标已应用、HOLDING 状态及连续 3 次反馈达标：ServoJ 误差 <0.001 rad 且下发计数 ≥5；ServoP 平移误差 <0.0002 m、旋转误差 <0.005 rad。更新返回 0 不代表到位。失败、FAULT、超时及 Ctrl-C 均走停止与清理路径；正常返回 0，失败返回 1，参数错误返回 2，正常处理的中断返回 130。仿真通过只说明这些离线用例通过，不表示实物跟踪性能通过。自动验收命令见 [发布检查](../tools/README.md)。

Windows x86_64 在 Visual Studio 2022 开发者终端可配置：

```cmd
cmake -S demo -B demo\build -G "Visual Studio 17 2022" -A x64
cmake --build demo\build --config Release
```

运行前将 SDK DLL 目录及 Conda 环境的 Library/bin 加入 PATH。实际生成目标与平台特例以 [CMakeLists.txt](CMakeLists.txt) 为准。

## 三、运行 Python 示例

先按 [Python 安装说明](../python/README.md)安装匹配的 wheel 或 Conda 包。无硬件接口检查可运行：

```bash
python demo/python/advanced/frame_transform.py
```

运行机械臂示例前，请在各脚本内按实物配置设备、机型、安装方向和位姿目标。然后在 SDK 根目录选择一个脚本单独运行，例如：

```bash
python demo/python/movej.py
```

这些脚本会调用真实运动接口；MoveJ/L/P/C 的返回码须与反馈一起解释，ServoJ/P 更新返回 0 只表示 SDK 接受目标。安装成功、纯计算 Frame 通过，都不等于机械臂真机运动通过。

## 四、常见问题

| 现象 | 检查 |
|---|---|
| 配置时报 no SDK binary | 当前平台没有匹配的 c/ 或 c++/ 动态库；见根目录平台表 |
| 运行时报 liboneroarm.so 或传递依赖找不到 | 配好库搜索路径与本版本匹配的 Pinocchio 3.8、Coal 3.0.1、urdfdom 4.0.1 等运行库 |
| Windows 找不到 DLL | 把 SDK DLL 与环境 Library/bin 放入进程 DLL 搜索路径 |
| 串口不存在或无法打开 | 非仿真配置下创建应失败；检查设备路径、权限、占用和波特率，不会自动回退默认串口 |
| 运动返回负数 | 查看错误码、状态标志与实际反馈；目标位姿、路径预检和限位都可能导致拒绝 |
| 同一会话第二个命令返回 BUSY | 等待当前命令结束，或按接口生命周期受控停止后再发送 |

资源默认按动态库或 Python 扩展所在路径定位 share/oneroarm_description；如使用自定义模型，请用 model_description_path 或 ONERO_DESCRIPTION_PATH 显式配置，并核对实际负载与安装方向。
