# Linux 运行时依赖

`linux-riscv64/lib/` 对应 Ubuntu 24.04 riscv64，使用 Pinocchio 3.8.0、hpp-fcl 2.4.5 及匹配的 C++ 运行库；与 x86_64 的运行库不能混用。系统依赖和集成命令见 [RISC-V 安装说明](../RISC_V_GUIDE.md)。

`linux-x86_64/lib/` 包含本版本本在 Linux x86_64 上运行所需的非系统动态库。使用 C/C++ 动态库前，将该目录加入 `LD_LIBRARY_PATH`。Python wheel 内包含独立的运行时副本。

这些文件来自与 SDK ABI 匹配的发布依赖集合。许可证见仓库 `LICENSES/`；系统提供的 glibc、动态加载器、pthread、libm 等不在本目录重复分发。

## 编译调用方程序

x86_64 库由 GCC/G++ 15.3 构建，依赖 GLIBCXX_3.4.32 / CXXABI_1.3.15。较旧系统编译器可编译公开 C++17 头，但链接时须显式选择本目录的 libstdc++.so.6，并设置 -rpath-link；仅设置 LD_LIBRARY_PATH 不够。完整命令见 [主臂 C++](../c++/README.md)与[夹爪 C++](../gripper/c++/README.md)。demo/CMakeLists.txt 已加入这些配置，且不允许忽略共享库未解析符号。

Linux arm64 的同类依赖来自匹配 Conda 环境的 lib 目录，可用 -DONERO_DEPENDENCY_DIR="$CONDA_PREFIX/lib" 传给 demo CMake。
