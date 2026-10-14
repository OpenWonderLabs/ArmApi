# Onero Gripper C++ SDK

Ubuntu 24.04 riscv64 使用 `linux/linux-riscv64/libonerogripper.so`，依赖与安装见 [RISC-V 安装说明](../../RISC_V_GUIDE.md)。

预编译 `libonerogripper.so` / `onerogripper.dll` + C++ 公开头（`namespace onero_gripper_api`）。
整个 SDK 只控制夹爪，独立交付、开箱即用。

---

## 目录

- [一、目录结构](#一目录结构)
- [二、集成方式](#二集成方式)
- [三、运行时依赖](#三运行时依赖)
- [四、数据类型](#四数据类型)
- [五、`OneroGripper` 详解](#五onerogripper-详解)
- [六、完整示例](#六完整示例)
- [七、错误诊断](#七错误诊断)

---

## 一、目录结构

```
c++/
├── include/
│   ├── onero_gripper.h                       # namespace onero_gripper_api 接口（含内联导出宏）
│   └── onero_define.h                        # 夹爪数据类型 / 状态结构 / 返回码
├── linux/
│   ├── linux-x86_64/libonerogripper.so
│   ├── linux-arm64/libonerogripper.so
│   └── linux-riscv64/libonerogripper.so
└── windows/
    └── windows-x86_64/{onerogripper.dll, onerogripper.lib}
```

如只需要纯 C ABI（`extern "C"`）头，请改用同级 [`c/`](../c/) 包，纯 C 工程可
`project(LANGUAGES C)` 集成。两包的 `libonerogripper.so` / `onerogripper.dll` 二进制完全相同。

---

## 二、集成方式

### 2.1 选项 A：CMake 直接 IMPORTED

```cmake
cmake_minimum_required(VERSION 3.15)
project(my_cpp_app LANGUAGES CXX)

set(GRIPPER_SDK /path/to/SDK/gripper/c++)
set(ONERO_DEPS /path/to/SDK/runtime/linux-x86_64/lib)
add_library(onerogripper SHARED IMPORTED)
set_target_properties(onerogripper PROPERTIES
    IMPORTED_LOCATION             ${GRIPPER_SDK}/linux/linux-x86_64/libonerogripper.so
    INTERFACE_INCLUDE_DIRECTORIES ${GRIPPER_SDK}/include
)

add_executable(my_cpp_app main.cpp)
target_link_libraries(my_cpp_app PRIVATE onerogripper "${ONERO_DEPS}/libstdc++.so.6")
target_link_directories(my_cpp_app BEFORE PRIVATE "${ONERO_DEPS}")
target_link_options(my_cpp_app PRIVATE "-Wl,-rpath-link,${ONERO_DEPS}")
set_property(TARGET my_cpp_app APPEND PROPERTY BUILD_RPATH "${ONERO_DEPS}")
```

Windows 把 `IMPORTED_LOCATION` 指向 `onerogripper.dll`，再加 `IMPORTED_IMPLIB`
指向 `onerogripper.lib`，Windows 不使用上述 Linux libstdc++ 和链接选项；Linux 按实际架构把子目录改成 `linux-x86_64` 或 `linux-arm64`。arm64 的 ONERO_DEPS 指向匹配 Conda 环境的 lib 目录。

### 2.2 选项 B：纯命令行编译

```bash
# 从整个 SDK 根目录执行
ONERO_DEPS="$PWD/runtime/linux-x86_64/lib"
g++ main.cpp -std=c++17 -I gripper/c++/include -L gripper/c++/linux/linux-x86_64 -lonerogripper \
    "$ONERO_DEPS/libstdc++.so.6" -L"$ONERO_DEPS" -Wl,-rpath-link,"$ONERO_DEPS" \
    -Wl,-rpath,"$ONERO_DEPS" -Wl,-rpath,'$ORIGIN/gripper/c++/linux/linux-x86_64' -o my_cpp_app
```

---

## 三、运行时依赖

公开头仅引用标准库类型。运行库仍有动态依赖：

- **编译期**：加入公开头目录，并按上述示例链接匹配的 C++ 运行库。仅设置 LD_LIBRARY_PATH 不会改变编译器选用的系统旧 libstdc++。
- **运行期**：Linux x86_64/arm64 版依赖 Boost 1.88 和 C++ 运行库。Linux x86_64 可使用仓库 `runtime/linux-x86_64/lib`；Linux arm64 可使用与 SDK 匹配的 Conda 环境。RISC-V 使用 Ubuntu 24.04 系统依赖及对应 runtime，按 [RISC-V 指南](../../RISC_V_GUIDE.md)安装。

| 运行时库 | 来源 |
|---|---|
| `libboost_system.so.1.88.0` | 随包 runtime 或匹配的 Conda 环境 |
| `libstdc++.so.6` / `libgcc_s.so.1` | 随包 runtime 或匹配的编译器运行库 |
| `libm.so.6` / `libc.so.6` | 系统 glibc |

```bash
export LD_LIBRARY_PATH="$PWD/runtime/linux-x86_64/lib:$PWD/gripper/c++/linux/linux-x86_64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
ldd gripper/c++/linux/linux-x86_64/libonerogripper.so | grep 'not found' || echo "OK"
```

> 串口设备独占：打开会话时对串口加独占锁，同一设备同一时刻只能被一个进程打开。

---

## 四、数据类型

定义在 [`include/onero_define.h`](include/onero_define.h)，位于 `namespace onero_api`；
`onero_gripper.h` 已自动包含，用户代码只需 `#include "onero_gripper.h"`。

```cpp
namespace onero_api {

struct GripperStatus {
    double  position;   // 开合位置，百分比 0..100
    double  velocity;   // 速度，百分比/s
    double  force;      // 力，N，限幅 ±40
    uint8_t error;      // 故障码，0 = 正常
    bool    valid;      // 该帧状态是否有效
};

// 触觉反馈（0x00 = 合力，0x01..0x09 = 9 个测点）
struct GripperTactileValue {
    uint8_t point_id;                 // 0x00 = 合力，0x01..0x09 = 测点
    double  fx, fy, fz;               // N
    bool    valid;
};
struct GripperTactileSensorStatus {
    uint8_t sensor_id;                // 0x01 / 0x02
    GripperTactileValue total_force;
    std::vector<GripperTactileValue> points;   // 0x01..0x09
    bool valid;
};
struct GripperTactileStatus {
    std::array<GripperTactileSensorStatus, 2> sensors;
    bool valid;
};

}  // namespace onero_api
```

### 返回码（`int`，强转自 `onero_api::MoveResult`）

```cpp
 0   SUCCESS            // 成功
-1   INVALID_PARAMS     // 会话未就绪 / 参数非法（如 max_* <= 0）
-4   EXECUTION_FAILED   // 串口/总线写失败或状态刷新失败
-6   INTERRUPTED        // move_position 被 request_stop() 取消
```

---

## 五、`OneroGripper` 详解

RAII 实例：构造时打开独立串口会话并注册夹爪，析构时自动释放。**禁拷贝、禁移动**。

```cpp
namespace onero_gripper_api {

class OneroGripper {
    explicit OneroGripper(const std::string& device);   // 波特率固定 921600
    ~OneroGripper();

    bool valid() const;                                  // 会话是否就绪
    int  enable();
    int  disable();
    onero_api::GripperStatus status();
    int  set_position(double percent);
    int  move_position(double percent,
                       double max_vel  = 100.0,
                       double max_acc  = 250.0,
                       double max_jerk = 1000.0);
    int  force_control(double torque);
    onero_api::GripperTactileStatus get_tactile();
    void request_stop();
    void clear_stop();
};

}  // namespace onero_gripper_api
```

| 方法 | 参数 | 返回 | 语义 |
|---|---|---|---|
| `OneroGripper(device)` | `device`：Linux `"/dev/ttyACM0"` / Windows `"COM3"` | – | 打开独立串口会话；失败时 `valid()==false` |
| `valid()` | – | `bool` | 会话是否就绪（串口已打开且夹爪已注册） |
| `enable()` / `disable()` | – | `int` | 使能 / 失能夹爪电机；运动前先 `enable()` |
| `set_position(percent)` | `0..100` | `int` | 单帧位置保持（下发一帧 MIT 位置命令，非阻塞） |
| `move_position(percent, max_vel, max_acc, max_jerk)` | `percent`：`0..100`；`max_*` 速度/加速度/加加速度上限（默认 `100/250/1000`，须 `>0`） | `int` | 100 Hz 点到点 S 曲线规划，**阻塞**直到到位 |
| `force_control(torque)` | `torque`：N | `int` | 单帧力保持，内部钳位 ±40 N |
| `status()` | – | `GripperStatus` | 刷新并返回夹爪状态；失败时 `valid=false` |
| `get_tactile()` | – | `GripperTactileStatus` | 刷新并返回两个触觉传感器各自的合力与 9 个测点快照 |
| `request_stop()` / `clear_stop()` | – | `void` | 置位 / 复位中断标志：`request_stop()` 使正在进行的 `move_position()` 尽快返回 `INTERRUPTED(-6)`，通常从另一线程调用；新一轮运动前 `clear_stop()` 复位 |

`status().position` / `velocity` 使用用户侧百分比单位；`force` 使用 N，命令与读数均限幅 ±40 N。

`get_tactile()` 读数前先判 `valid`（顶层、每个 `sensor`、每个 `point`），通常需先 `enable()` 并施加一定夹持力才会读到非零数据。

---

## 六、完整示例

```cpp
#include "onero_gripper.h"
#include <iostream>

using onero_gripper_api::OneroGripper;

int main() {
    OneroGripper grip("/dev/ttyACM0");           // Windows: "COM3"
    if (!grip.valid()) {
        std::cerr << "failed to open gripper\n";
        return 1;
    }

    grip.enable();
    grip.move_position(80.0);                    // 闭合到 80%（默认速度/加速度上限）

    auto s = grip.status();
    std::cout << "pos=" << s.position << "% force=" << s.force << "N\n";

    grip.force_control(20.0);                    // 20 N 力保持（±40 N 上限）

    auto t = grip.get_tactile();
    if (t.valid) {
        for (const auto& sensor : t.sensors) {
            if (sensor.valid) {
                const auto& f = sensor.total_force;
                std::cout << int(sensor.sensor_id) << ": "
                          << f.fx << " " << f.fy << " " << f.fz << " N\n";
            }
        }
    }

    grip.disable();
    return 0;                                    // 析构自动释放会话
}
```

---

## 七、错误诊断

| 现象 | 原因 / 处理 |
|---|---|
| 编译器找不到 `onero_gripper.h` / `onero_define.h` | 把 `c++/include` 加入 include path |
| 链接报 `cannot find -lonerogripper` | `-L c++/linux/<arch>` 路径不对；Windows 下需指 `IMPORTED_IMPLIB` 到 `onerogripper.lib` |
| 运行时 `cannot open shared object libonerogripper.so` | 库目录不在搜索路径；推荐 `-Wl,-rpath,'$ORIGIN'/c++/linux/<arch>`，或运行时设 `LD_LIBRARY_PATH` |
| `OneroGripper::valid() == false` | 串口路径 / 权限：Linux `ls /dev/ttyACM*`，必要时 `sudo chmod 666` 或加入 `dialout` 组；Windows 在设备管理器查 COM 号 |
| 同一设备第二次打开失败 | 串口被独占：确认没有其他进程正占用该设备 |
| 方法返回 `-1 INVALID_PARAMS` | 会话未就绪；或 `move_position` 的 `max_vel/acc/jerk <= 0` |
| 方法返回 `-4 EXECUTION_FAILED` | 串口 / 总线写失败或状态刷新失败：检查连线、供电、设备是否被拔出 |
| `move_position` 返回 `-6 INTERRUPTED` | 运动期间被 `request_stop()` 取消；下次运动前 `clear_stop()` 复位 |
