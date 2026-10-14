# Onero Gripper 纯 C ABI 包

Ubuntu 24.04 riscv64 使用 `linux/linux-riscv64/libonerogripper.so`，依赖与安装见 [RISC-V 安装说明](../../RISC_V_GUIDE.md)。

预编译 `libonerogripper.so` / `onerogripper.dll` + 纯 C 接口头文件。
适用于 C 工程或其他语言的 FFI 绑定（Rust / Go / C# 等）。整个 SDK 只控制夹爪，
独立于任何上位设备，开箱即用。

---

## 目录

- [一、目录结构](#一目录结构)
- [二、集成方式](#二集成方式)
- [三、运行时依赖](#三运行时依赖)
- [四、数据类型](#四数据类型)
- [五、API 详解](#五api-详解)
- [六、完整示例](#六完整示例)
- [七、错误诊断](#七错误诊断)

---

## 一、目录结构

```
c/
├── include/
│   └── onero_gripper_c.h                     # 纯 C 接口声明 + 内联导出宏（extern "C"）
├── linux/
│   ├── linux-x86_64/libonerogripper.so
│   ├── linux-arm64/libonerogripper.so
│   └── linux-riscv64/libonerogripper.so
└── windows/
    └── windows-x86_64/{onerogripper.dll, onerogripper.lib}
```

本包仅含纯 C ABI 头 `onero_gripper_c.h`（自带 `onerogripper_status_t` 定义，无需其他头）。
如需 C++ 接口（类 + 触觉反馈）请改用同级 [`c++/`](../c++/) 包；两包的二进制完全相同。

---

## 二、集成方式

### 2.1 选项 A：CMake 直接 IMPORTED

```cmake
cmake_minimum_required(VERSION 3.15)
project(my_gripper_app LANGUAGES C)            # 纯 C 项目无需 CXX

set(GRIPPER_SDK /path/to/SDK/gripper/c)
set(ONERO_DEPS /path/to/SDK/runtime/linux-x86_64/lib)
add_library(onerogripper SHARED IMPORTED)
set_target_properties(onerogripper PROPERTIES
    IMPORTED_LOCATION             ${GRIPPER_SDK}/linux/linux-x86_64/libonerogripper.so
    INTERFACE_INCLUDE_DIRECTORIES ${GRIPPER_SDK}/include
)

add_executable(my_gripper_app main.c)
target_link_libraries(my_gripper_app PRIVATE onerogripper)
target_link_options(my_gripper_app PRIVATE "-Wl,-rpath-link,${ONERO_DEPS}")
set_property(TARGET my_gripper_app APPEND PROPERTY BUILD_RPATH "${ONERO_DEPS}")
```

Windows 把 `IMPORTED_LOCATION` 指向 `onerogripper.dll`，再加 `IMPORTED_IMPLIB`
指向 `onerogripper.lib`，Windows 不使用上述 Linux 链接选项；Linux arm64 的 ONERO_DEPS 指向匹配 Conda 环境的 lib 目录。Linux 按实际架构把子目录改成 `linux-x86_64` 或 `linux-arm64`。

### 2.2 选项 B：纯命令行编译

```bash
# 从整个 SDK 根目录执行
ONERO_DEPS="$PWD/runtime/linux-x86_64/lib"
gcc main.c -I gripper/c/include -L gripper/c/linux/linux-x86_64 -lonerogripper \
    -Wl,-rpath-link,"$ONERO_DEPS" -Wl,-rpath,"$ONERO_DEPS" \
    -Wl,-rpath,'$ORIGIN/gripper/c/linux/linux-x86_64' -o my_gripper_app
```

`-Wl,-rpath,'$ORIGIN'/...` 让程序找到夹爪动态库；运行时依赖还需要以下配置。

---

## 三、运行时依赖

Linux x86_64/arm64 版 `libonerogripper.so` 依赖 Boost 1.88 和 C++ 运行库。本包在 `runtime/linux-x86_64/lib` 提供 Linux x86_64 对应文件；Linux arm64 可通过与 SDK 匹配的 Conda 环境提供依赖。RISC-V 使用 Ubuntu 24.04 系统依赖及对应 runtime，按 [RISC-V 指南](../../RISC_V_GUIDE.md)安装。

| 运行时库 | 来源 |
|---|---|
| `libboost_system.so.1.88.0` | 随包 runtime 或匹配的 Conda 环境 |
| `libstdc++.so.6` / `libgcc_s.so.1` | 随包 runtime 或匹配的编译器运行库 |
| `libm.so.6` / `libc.so.6` | 系统 glibc |

Linux x86_64 从仓库根目录运行时，先设置运行库搜索路径，再确认无 `not found`：

```bash
export LD_LIBRARY_PATH="$PWD/runtime/linux-x86_64/lib:$PWD/gripper/c/linux/linux-x86_64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
ldd gripper/c/linux/linux-x86_64/libonerogripper.so | grep 'not found' || echo "OK"
```

> 串口设备独占：打开会话时对串口加独占锁，同一设备同一时刻只能被一个进程打开；
> 第二个进程打开同一设备会失败（见第七节）。

---

## 四、数据类型

定义在 [`include/onero_gripper_c.h`](include/onero_gripper_c.h)，均为 POD。

```c
typedef void* onero_gripper_handle;

typedef struct {
    double  position;   // 开合位置，百分比 0..100
    double  velocity;   // 速度，百分比/s
    double  force;      // 力，N，限幅 ±40
    uint8_t error;      // 故障码，0 = 正常
    bool    valid;      // 该帧状态是否有效
} onerogripper_status_t;
```

### 错误码（`int` 返回族）

```c
 0   SUCCESS            // 成功
-1   INVALID_PARAMS     // 句柄无效 / 会话未就绪 / 参数非法（如 max_* <= 0）
-4   EXECUTION_FAILED   // 串口/总线写失败或状态刷新失败
-6   INTERRUPTED        // 运动被取消（仅 C++/Python 的中断接口会触发；纯 C 用不到）
```

---

## 五、API 详解

所有函数均带内部 `try/catch` 兜底，异常绝不跨越 C ABI 边界；非法句柄一律返回错误码 / `false` / 零值结构体。

### 5.1 生命周期

| 函数 | 参数 | 返回 | 说明 |
|---|---|---|---|
| `onerogripper_create` | `const char* device` | `onero_gripper_handle` | 创建独立夹爪句柄；NULL 表示参数无效或构造异常；非空句柄还须检查 onerogripper_valid(h)。设备不可用时可返回非空的无效句柄。打开串口会话（波特率固定 921600）。`device`：Linux `"/dev/ttyACM0"`，Windows `"COM3"` |
| `onerogripper_destroy` | `onero_gripper_handle` | – | 释放句柄；释放后置 `NULL`，禁止重用。传 `NULL` 安全 |
| `onerogripper_valid` | `onero_gripper_handle` | `bool` | 会话是否就绪（串口已打开且夹爪已注册） |

### 5.2 使能

| 函数 | 返回 | 说明 |
|---|---|---|
| `onerogripper_enable(h)` | `int` | 使能夹爪电机；运动前必须先使能 |
| `onerogripper_disable(h)` | `int` | 失能夹爪电机 |

### 5.3 运动与力控

| 函数 | 参数 | 返回 | 语义 |
|---|---|---|---|
| `onerogripper_set_position` | `percent`（`0..100`） | `int` | 单帧位置保持（下发一帧 MIT 位置命令，非阻塞） |
| `onerogripper_move_position` | `percent, max_vel, max_acc, max_jerk` | `int` | 100 Hz 点到点 S 曲线规划，**阻塞**直到到位；`max_*` 为速度/加速度/加加速度上限（典型 `100 / 250 / 1000`，须 `> 0`） |
| `onerogripper_force_control` | `torque`（N） | `int` | 单帧力保持，内部钳位 ±40 N |

### 5.4 状态查询

| 函数 | 返回 | 说明 |
|---|---|---|
| `onerogripper_status(h)` | `onerogripper_status_t` | 刷新并返回 `position` / `velocity` / `force` / `error` / `valid`；失败时返回全零（`valid=false`） |

---

## 六、完整示例

最小可编译的 C 程序（省略部分错误处理）：

```c
#include "onero_gripper_c.h"
#include <stdio.h>

int main(void) {
    onero_gripper_handle g = onerogripper_create("/dev/ttyACM0");
    if (!onerogripper_valid(g)) {
        fprintf(stderr, "failed to open gripper\n");
        onerogripper_destroy(g);
        return 1;
    }

    onerogripper_enable(g);

    /* 点到点闭合到 80% */
    onerogripper_move_position(g, 80.0, 100.0, 250.0, 1000.0);

    /* 读取状态 */
    onerogripper_status_t s = onerogripper_status(g);
    printf("pos=%.1f%% vel=%.1f force=%.2fN valid=%d\n",
           s.position, s.velocity, s.force, s.valid);

    /* 20 N 力保持（上限 ±40 N） */
    onerogripper_force_control(g, 20.0);

    onerogripper_disable(g);
    onerogripper_destroy(g);
    return 0;
}
```

---

## 七、错误诊断

| 现象 | 原因 / 处理 |
|---|---|
| 编译器找不到 `onero_gripper_c.h` | 把 `c/include` 加入 include path（CMake 的 `INTERFACE_INCLUDE_DIRECTORIES` 或 `gcc -I`） |
| 链接报 `cannot find -lonerogripper` | `-L c/linux/<arch>` 路径不对；Windows 下没指 `IMPORTED_IMPLIB` 到 `onerogripper.lib` |
| 运行时 `cannot open shared object libonerogripper.so` | 库目录不在搜索路径；推荐编译时加 `-Wl,-rpath,'$ORIGIN'/c/linux/<arch>`，或运行时设 `LD_LIBRARY_PATH` |
| `onerogripper_create` 返回 `NULL` 或 `valid()==false` | 串口路径 / 权限：Linux `ls /dev/ttyACM*`，必要时 `sudo chmod 666 /dev/ttyACM0` 或把用户加入 `dialout` 组；Windows 在设备管理器查 COM 号 |
| 同一设备第二次打开失败 | 串口被独占：确认没有其他进程正占用该设备，先退出占用方再打开 |
| 方法返回 `-1 INVALID_PARAMS` | 句柄无效 / 会话未就绪；或 `move_position` 的 `max_vel/acc/jerk <= 0` |
| 方法返回 `-4 EXECUTION_FAILED` | 串口 / 总线写失败或状态刷新失败：检查连线、供电、设备是否被拔出 |
