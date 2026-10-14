# Linux RISC-V 用户包安装

本目录交付 Ubuntu 24.04 riscv64 的主机械臂、独立夹爪 C/C++ 共享库和 CPython 3.12 wheel。SDK 版本为 1.2.1，主臂 wheel 构建标签为 5，独立夹爪 wheel 为 3。没有 riscv64 Conda 包；不能将 x86_64、arm64 的 Conda 包用于本平台。

目标系统必须是 riscv64 Linux。Ubuntu 22.04、Bianbu、其他 Python ABI 和具体开发板的兼容性未由本次检查证明。开发电脑上的 QEMU 仅用于构建/离线验证，不是机械臂物理仿真器。实际硬件通信和控制性能另行验收，验证范围见 [发布说明](RELEASE_NOTES.md)。

## 文件位置

| 路径 | 内容 |
|---|---|
| c/linux/linux-riscv64/liboneroarm.so | 主臂 C 库 |
| c++/linux/linux-riscv64/liboneroarm.so | 主臂 C++ 库，与 C 库逐字节相同 |
| gripper/c/linux/linux-riscv64/libonerogripper.so | 独立夹爪 C 库 |
| gripper/c++/linux/linux-riscv64/libonerogripper.so | 独立夹爪 C++ 库，与 C 库逐字节相同 |
| python/wheels/linux-riscv64/ | 主臂 CPython 3.12 wheel |
| gripper/python/wheels/linux-riscv64/ | 独立夹爪 CPython 3.12 wheel |
| runtime/linux-riscv64/lib/ | Pinocchio、hpp-fcl 和匹配的 C++ 运行库 |

公开头文件、C/C++ 模型资源及示例与其余平台共用。运行不需要 SDK 实现源码或旧用户工程。以下命令在 Ubuntu 24.04 riscv64 机器的本包根目录执行。

## 安装系统依赖

以下依赖集合用于已验证的干净容器验收；其中 `-dev` 包同时支持用户程序编译：

```bash
sudo apt-get update
sudo apt-get install -y \
  build-essential cmake ninja-build \
  python3.12 python3.12-venv python3-numpy python3-loguru \
  libboost-all-dev liburdfdom-dev libssl-dev zlib1g-dev \
  liboctomap-dev libassimp-dev libqhull-dev libconsole-bridge-dev
```

本平台使用 Pinocchio 3.8.0、hpp-fcl 2.4.5 和 Ubuntu 24.04 的系统依赖。其他平台的 Coal 3.0.1/Conda 运行库不可混入本平台。系统 glibc、动态加载器及相应 Ubuntu 库由 apt 提供；随包 runtime 不是完整操作系统。

## C/C++ 示例

```bash
export LD_LIBRARY_PATH="$PWD/runtime/linux-riscv64/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
cmake -S demo -B build-riscv64 -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build-riscv64 --parallel 2
./build-riscv64/frame_demo_c
./build-riscv64/frame_demo_cpp
```

示例 CMake 根据 `riscv64` 自动选择库，并在链接阶段选择随包 `libstdc++.so.6`。Frame 是不连接硬件的计算示例；其余运动例程需按各自说明配置设备和安全工作空间，不能作为自动安装检查运行。

自行集成时使用公开头、对应共享库及 `runtime/linux-riscv64/lib`。C++ 要求 C++17；为依赖库配置链接期 `-Wl,-rpath-link,<runtime目录>` 和运行期路径。主臂与夹爪共享库包含指向本包 runtime 的相对 RPATH/RUNPATH，移动文件时应保持目录关系。

## Python 联合安装

在目标系统新建环境，使用 apt 提供的 NumPy/loguru，避免在目标上临时编译 NumPy：

```bash
python3.12 -m venv --system-site-packages .venv-riscv64
. .venv-riscv64/bin/activate
python -m pip install --force-reinstall --no-index --no-deps \
  ./python/wheels/linux-riscv64/oneroarm-1.2.1-5-cp312-cp312-linux_riscv64.whl \
  ./gripper/python/wheels/linux-riscv64/onerogripper-1.2.1-3-cp312-cp312-linux_riscv64.whl
env -u LD_LIBRARY_PATH python -c "import oneroarm, onerogripper; print('arm-first OK')"
env -u LD_LIBRARY_PATH python -c "import onerogripper, oneroarm; print('gripper-first OK')"
env -u LD_LIBRARY_PATH python demo/python/advanced/frame_transform.py
```

wheel 标签为 `cp312-cp312-linux_riscv64`，不声明 manylinux 兼容。主臂 wheel 声明 `numpy>=1.26,<3` 和 `loguru`；验证使用 Ubuntu 24.04 的 apt 版本。主臂扩展及模型资源随 wheel 安装；每个模块有自己的依赖目录，两个模块的 C++ 运行库名称和内容保持一致。导入时仍需要前述 Ubuntu 系统依赖。升级已有环境时应同时重装两个 wheel，并重启 Python 进程。

## 校验

本包根目录执行 `sha256sum -c SHA256SUMS`。在 x86_64 主机执行发布检查时，RISC-V 文件仅作架构、导出、内容和哈希检查；外架构的实际执行结果见 [发布说明](RELEASE_NOTES.md)，不能用 x86_64 的 `ldd`/Python 代替目标架构运行检查。
