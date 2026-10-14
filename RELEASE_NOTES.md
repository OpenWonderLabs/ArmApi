# WoanArm SDK 1.2.1 发布说明

## 1.2.1 更新

修复 ServoJ 停止异常及运动中切换目标的异常超调，明确停止和取消接口的返回语义。

- **在线换目标修复**：移除逐拍追赶位置的回退规划，改为静态集成 Ruckig 0.15.3，从连续 q/dq/ddq 规划完整轨迹；同周期最新目标覆盖、相同目标续期、原动态限制及已有停止逻辑保留。新增完整路径和制动包络限位检查。
- **修复方式**：从连续指令位置、速度和加速度规划三阶段限加加速度制动，消除停止时反复重新追踪位置导致的速度换向；保留 SDK 原有动态限制。
- **返回约定**：`stop_servoj()` 成功返回 `0` 后进入 IDLE、速度和加速度归零并释放资源，故障返回负错误码；活动 ServoJ 的 `cancel_trajectory()` 返回 `-8 BUSY`，应使用专用停止。其他运动的取消返回 `0` 仅表示请求已记录。
- **验证结果**：四平台 suite 5 通过：60 次 NumPy 导入顺序检查、88 次超时恢复、132 次运动中换目标、88 次运动中停止；三个原生平台，RISC-V QEMU。真机与原生板卡验收不在本次范围。

## 接口与功能

- MoveJ、MoveL、MoveP、MoveC 运动接口。
- ServoJ 在线关节伺服和 ServoP 在线笛卡尔伺服，包含启动、更新、状态与停止。
- BASE/WORLD/TOOL 坐标变换、笛卡尔增量、flange/TCP 转换。
- 拖动示教及夹爪 POSITION/BACKDRIVE 录制和回放。
- 机械臂、夹爪、触觉共享受控设备会话及命令仲裁。
- 独立夹爪 C、C++、Python 接口。
- C/C++ 示例使用完整公开导出；Windows MSVC 示例使用 UTF-8。
- 主臂与独立夹爪的 `onero_define.h` 使用相同的完整宏保护，可在同一 C++ 编译单元中同时引入两个接口头。此修复仅涉及公共头文件，不改变类型布局或二进制接口；使用更新的头文件重新编译调用方即可。

## 平台与验证范围

| 平台 | C/C++ | Python | 离线验证环境 |
|---|---|---|---|
| Linux x86_64 | 主臂/夹爪 | 主臂 Conda 3.10–3.13，夹爪 Conda 3.12；配对 wheel 3.12 | Ubuntu 22.04，原生 |
| Linux arm64 | 主臂/夹爪 | 主臂 Conda 3.10–3.13，夹爪 Conda 3.12 | Ubuntu 22.04，原生 |
| Windows x86_64 | 主臂/夹爪 | 主臂 Conda 3.10–3.13，夹爪 Conda 3.12 | Windows Server 2022，原生 |
| Linux riscv64 | 主臂/夹爪 | 配对 wheel 3.12，无 Conda 包 | Ubuntu 24.04，QEMU 用户态 |


主臂 C/C++ 示例 Linux 每平台 22 个，Windows 21 个；Windows C 版拖动示教不在随包 CMake 构建范围。Python 完整联合调用检查使用 3.12；3.10/3.11/3.13 的主臂 Conda 构建/导入记录不等同于完整接口验收。

RISC-V 使用 Pinocchio 3.8、hpp-fcl 2.4.5 和 Ubuntu 系统库，不能混入其他平台的 Coal/Conda 运行库。QEMU 用户态测试不是开发板原生测试，安装见 [RISC-V 指南](RISC_V_GUIDE.md)。

## 版本与交付

VERSION、wheel/Conda 文件名和包内元数据保持 1.2.1。本次主臂运行库重新构建，Conda build 为 5，wheel 构建标签为 5；独立夹爪保持 Conda build 3、wheel 标签 3。运行包不携带构建 recipe、源目录链接或不必要的开发产物。

用户仓库使用独立发布历史；校验清单只列正式交付文件。发布门禁检查版本、全部公开 C 声明、必需 C++ 方法、导出白名单、依赖、包内容与 SHA-256。

升级时安装 1.2.1 对应平台的包并重启进程；配对 wheel 应同时更新主臂和夹爪。完整离线发布检查及归档使用 CPython 3.12；`--static-only` 不能放行正式归档。工具用法见 [tools/README.md](tools/README.md)。

## 使用限制

尚未验收实际串口/CAN、真实运动、夹爪开合、触觉硬件、工具补偿、急停及跟踪性能；完整 MoveL/MoveP/MoveC/ServoP 路径与实物 ServoJ 收敛仍需另行验证；本次通过的是已列出的仿真用例。WORLD 变换需要有效标定，实物工具必须提供正确模型。两个独立 Python 模块不得重复控制同一物理设备。

## 安装兼容与回归补充

- 修复 NumPy 先导入后创建机械臂时的 wheel 崩溃：统一 C++ 运行库的标准 SONAME 与依赖引用，主臂 wheel build 5、独立夹爪 build 3；Conda 主臂 build 5、夹爪 build 3 及 C/C++ 库内容保持不变。
- 将超时 BRAKING 中续发目标、超时 HOLDING 后更新目标加入默认/自定义限制回归；确认动态连续、最终收敛和零速清理。超时标志是会话历史，应联合状态、命令年龄及 last_error 判断。
- 修正 RISC-V wheel 标签和同版本强制重装命令；自动记录验收所用实际依赖并绑定原始日志。
