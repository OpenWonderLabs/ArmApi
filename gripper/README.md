# WoanArm 独立夹爪 SDK

Ubuntu 24.04 riscv64 的独立夹爪 C/C++ 库与 CPython 3.12 wheel 见 [RISC-V 安装说明](../RISC_V_GUIDE.md)。

当前提供 Linux x86_64、Linux arm64、Linux riscv64、Windows x86_64 的纯 C/C++ 动态库。Conda 包覆盖 Linux x86_64、Linux arm64 和 Windows x86_64；独立 CPython 3.12 wheel 覆盖 Linux x86_64/riscv64。RISC-V 安装以专用指南为准。以下命令用于 x86_64：

- [`c/`](c/README.md)：`onero_gripper_c.h` + `libonerogripper.so`；
- [`c++/`](c++/README.md)：`onero_gripper.h`、`onero_define.h` + `libonerogripper.so`；
- [`python/`](python/README.md)：`onerogripper` wheel。

独立夹爪对象自行占有设备会话。夹爪与机械臂共用同一物理总线时，应使用 `oneroarm` 中的随臂夹爪接口，避免两个根会话同时打开同一设备。
