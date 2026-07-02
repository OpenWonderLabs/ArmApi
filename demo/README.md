# OneroArm Demo

按动作类型组织的 7 组示例，每组都覆盖 **C / C++ / Python** 三种调用方式：

```
demo/
├── CMakeLists.txt           # 一键编译所有 C / C++ demo
├── c/                       # 7 个纯 C ABI 示例   → ../c/   包
├── cpp/                     # 7 个 C++ RAII 示例  → ../c++/ 包
└── python/                  # 7 个 Python 示例   → import oneroarm
```

| 名字 | 演示内容 | 序列 |
|---|---|---|
| [`full_demo`](#full)                   | 综合：单关节 + movep + movel 全流程               | `enable → restore_arm()(zero) → movej(joint4=0.3) → movep(target) → restore_arm()(zero) → movel(target) → restore_arm()(zero) → disable` |
| [`movej_demo`](#movej)                 | 单一 `movej` 关节空间运动                          | `enable → restore_arm()(zero) → movej(target) → restore_arm()(zero) → disable` |
| [`movep_demo`](#movep)                 | 单一 `movep` 笛卡尔点到点（自动避碰）              | `enable → restore_arm()(zero) → movep(target) → restore_arm()(zero) → disable` |
| [`movel_demo`](#movel)                 | 单一 `movel` 笛卡尔直线                            | `enable → restore_arm()(zero) → movel(target) → restore_arm()(zero) → disable` |
| [`buffered_traj_demo`](#buffered_traj) | `trajectory_connect` 缓冲多段 move + `execute_buffered_trajectory` | `enable → restore_arm() → movej(joint4=0.3, tc=1) → movep(target, tc=1) → movej(zero, tc=1) → execute_buffered_trajectory → disable` |
| [`can_frame_demo`](#can_frame)         | 原始 CAN 帧收发最小示例（**不使能电机**） | `register_cb → send_can_frame(0x100, DEADBEEF) → pump×5 → clear_cb` |
| [`drag_teaching_demo`](#drag_teaching) | 拖动示教（零力录制 + 回放，纯 API、无 ROS）       | `initialize → set_hardware → tick(100Hz) ↔ stdin: 1=录制 / 2=停止 / 3=回放 / 4=选历史 / 5=退出` |

> **关节目标统一为 `joint4=0.3`**；**笛卡尔目标统一为左臂可达位** `(x=0.30, y=0.30, z=0.30 / 0.40)`，单位四元数 `(w=1, x=0, y=0, z=0)`。各 demo 文件**最顶部** `TARGET_*` / `JOINT_*` 常量集中可改。
>
> **`buffered_traj_demo` 演示的是"轨迹缓冲"——即 `movej/movel/movep` 最后一个参数 `trajectory_connect=1` 累积进内部 `trajectory_buffer_`，再由 `execute_buffered_trajectory` 串成一条平滑轨迹一次性下发**。它和 `send_trajectory` / `send_trajectory_point` 完全不是同一回事——后者是直接给关节电机下发 MIT 力矩控制（不规划、不入此 buffer），调用前必须自己规划好整段轨迹，本仓库 demo 不直接演示。详见外层 [`README.md` §四](../README.md#四接口速查表以-c-为例)。

CMakeLists 通过 `foreach()` 给每个名字声明 `<name>_demo_c` 与 `<name>_demo_cpp` 两个可执行；
两者分别链 `oneroarm_c` / `oneroarm_cpp` 这两个 IMPORTED target（同二进制 `liboneroarm.so`，
区别仅在公开头）。Python demo 由用户直接 `python demo/python/<name>_demo.py` 运行，无需 cmake。

---

## 编译 C / C++（Linux）

demo 编译本身只需要 C/C++ 编译器、CMake 和 Ninja。x86_64 / arm64 上如果想用
conda 统一提供工具链和运行时依赖，可以创建一个构建环境：

```bash
conda create -n oneroarm_cpp -c conda-forge \
    cmake ninja compilers eigen boost pinocchio hpp-fcl urdfdom pkg-config -y
conda activate oneroarm_cpp
```

RISC-V 上不需要 conda，也不需要源码编译 pinocchio / hpp-fcl；这些 runtime 已随包放在
`third_party/linux-riscv64/lib/riscv64-linux-gnu/`，并由 SDK 内置 RPATH 自动解析。
RISC-V 只需补齐构建工具：

```bash
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build
```

随后编译 demo：

```bash
cd demo
mkdir -p build && cd build
cmake .. -G Ninja
cmake --build .
```

CMake 自动按 `CMAKE_SYSTEM_PROCESSOR` 选 `linux-x86_64` / `linux-arm64` / `linux-riscv64`。`BUILD_RPATH` 已写进可执行文件，
**无需 `LD_LIBRARY_PATH`** 即可定位 `liboneroarm.so`：

```bash
./full_demo_c            ./full_demo_cpp
./movej_demo_c           ./movej_demo_cpp
./movep_demo_c           ./movep_demo_cpp
./movel_demo_c           ./movel_demo_cpp
./buffered_traj_demo_c   ./buffered_traj_demo_cpp
./can_frame_demo_c       ./can_frame_demo_cpp
./drag_teaching_demo_c   ./drag_teaching_demo_cpp
```

> 头文件**不需要**额外 `find_package(Eigen3 / pinocchio / hpp-fcl / Boost / OpenSSL)`——
> SDK 已用 `-fvisibility=hidden` 把这些类型吸收进 `liboneroarm.so` 的导出表。
> x86_64 / arm64 运行时通过 conda env 提供传递依赖；RISC-V 运行时通过仓库
> `third_party/linux-riscv64/` 与 SDK 内置 RPATH 提供传递依赖。正常情况下无需
> `LD_LIBRARY_PATH`。

### 在已有 conda env 上加构建工具链

如果想在 x86_64 / arm64 上复用现有 conda env（例如已经装了 `oneroarm` 的 Python 消费环境），只需补齐 build-only 依赖；运行时 `pinocchio` / `hpp-fcl` / `urdfdom` 已随 `oneroarm` 包拉进同一个 env，**不要重装**：

```bash
conda activate oneroarm                  # 已有的目标 env
conda install -c conda-forge cmake ninja compilers eigen boost pkg-config -y
```

随后回到 `demo/build` 重新 `cmake .. -G Ninja`。如果同一个 `build/` 之前用过别的 generator，`CMakeCache.txt` 会把 generator 锁死，再次 `cmake ..` 会报 `CMake was unable to find a build program corresponding to "Ninja"`——清掉整个 `build/` 重新来：

```bash
rm -rf build && mkdir build && cd build
cmake .. -G Ninja
cmake --build .
```

> 报错"找不到 Ninja"通常有两种成因：① 当前 env 里**根本没装** `ninja`（多见于直接 `conda activate oneroarm` 的 Python 消费环境，没有 build 工具链）；② env 已装 `ninja` 但 `build/CMakeCache.txt` 锁的是上一次的 generator。先确认 `which ninja` 指向当前 env，再决定是补装工具链还是清 build 目录。

### 版本冲突怎么办

`liboneroarm.so` 期望的 SONAME 在 [c/README.md §三](../c/README.md#三运行时依赖) 列出。x86_64 / arm64 常见症状与处理：

| 症状 | 原因 | 处理 |
|---|---|---|
| `cannot open shared object file: libpinocchio_*.so.3.1` | env 里 pinocchio 大版本对不上 SDK 期望的 SONAME | `conda install -c conda-forge "pinocchio=3.1.*" "hpp-fcl=2.4.*" "urdfdom=4.0.*" -y` |
| `undefined symbol: _ZN10pinocchio*` 等 mangled 名字 | 主版本对得上、但 conda-forge 不同 build 串号之间 ABI 漂移 | 先 `conda update --all -c conda-forge` 把 env 拉到当前快照，再按上一行 pin 死小版本 |
| `GLIBCXX_3.4.30 not found` / `GOMP_*` not found | 进程链到了系统 gcc 的旧 `libstdc++` / `libgomp`，没用 env 内的 | 重新 `conda activate <env>`；仍报错则 `conda install -c conda-forge libstdcxx-ng libgomp` 把运行库强制拉进 env |
| `UnsatisfiableError` 装 `compilers` 时 | 既存 env 跨 channel 锁住了 toolchain | `conda install -c conda-forge --strict-channel-priority compilers cmake ninja eigen boost pkg-config`；仍解不开就回到上面流程开一个干净的 `oneroarm_cpp` |

> 不要把 `liboneroarm.so` 同时丢进多个 env、再用 `LD_LIBRARY_PATH` 跨 env 拉。SDK 的 BUILD_RPATH 已锁死自身目录，跨 env 极易引入第二份 `libpinocchio_*` / `libhpp-fcl` 与 SONAME 不一致而段错误。

## 编译 C / C++（Windows）

`CMakeLists.txt` 同样自动检出 `windows/windows-x86_64`：

```cmd
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release

:: 把 oneroarm.dll 与 conda env 里的传递依赖加入 PATH 后运行
set PATH=%cd%\..\..\c++\windows\windows-x86_64;%CONDA_PREFIX%\Library\bin;%PATH%
.\Release\full_demo_cpp.exe
```

## 跑 Python demo

```bash
conda create -n oneroarm python=3.12 -y
conda activate oneroarm
conda install -c conda-forge -c ./python/conda_channel/linux oneroarm -y

python demo/python/full_demo.py
python demo/python/movej_demo.py
python demo/python/movep_demo.py
python demo/python/movel_demo.py
python demo/python/buffered_traj_demo.py
python demo/python/can_frame_demo.py
python demo/python/drag_teaching_demo.py
```

## 无硬件下的预期行为

所有 demo 都会先打印 `OneroCore Hardware Initialization` 横幅，然后报：

```
Error opening serial port (/dev/ttyACM0): open: No such file or directory ...
[X] 串口未连接: /dev/ttyACM0 (设备不存在)
```

`onero_create_robot` / `OneroArm` 构造仍返回非空句柄（设计如此）；`enable_motors` 进入跳过分支
返回失败码，`movej` 打印 `[MoveJ] target_joints: [...]` 后阻塞等响应——这是预期的"无硬件"路径，
按 `Ctrl-C` 终止即可。

## 路径覆盖示例

零配置（推荐）：留 `cfg.model_description_path = ""`，SDK 通过 `dladdr` 解析到内置
`oneroarm_description`（`<libdir>/../share/oneroarm_description/`）。

显式覆盖（按优先级递减）：

```cpp
// 1. 进程内
std::strcpy(cfg.model_description_path, "/custom/oneroarm_description");
```

```bash
# 2. 环境变量（同时被 SDK 与外部工具读取）
export ONERO_DESCRIPTION_PATH=/custom/oneroarm_description
```

需要把内置 URDF 喂给外部工具（RViz / MuJoCo / 自研 viewer）时：

```python
import os, oneroarm
desc = os.path.join(os.path.dirname(oneroarm.__file__),
                    "share", "oneroarm_description")
```
