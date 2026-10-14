# 发布检查工具

以下工具不连接真实设备。离线验证不能代替实物通信、运动或安全验收。

## 文件与接口检查

- `python3 tools/check_cpp_headers.py`：核对两份公共类型头、宏保护及独立/联合包含顺序。Linux 使用 C++17 编译器，Windows 在 MSVC 开发者命令行使用 `cl`；可用 `CXX` 指定编译器。
- `python3 tools/verify_release.py --static-only`：检查版本、平台架构、导出符号、动态依赖、包元数据、文档安装包路径、Conda 下载页及 SHA256SUMS。此模式跳过运行验收，不能用于正式归档。
- `python3 tools/test_release_checks.py` 与 `python3 tools/test_conda_html.py`：检查错误解释器、旧哈希、缺失执行记录、错误状态及下载页不一致的拒绝行为。

主臂和独立夹爪的 `onero_define.h` 必须内容一致并保留相同宏保护。Linux 共享库须导出全部公开 C 函数和必需 C++ 方法（含 const 方法）；Linux Python 扩展仅导出对应 PyInit 入口。

## 离线执行与归档

在 Linux x86_64 使用 CPython 3.12，安装 binutils、file、zstd、NumPy >=2,<2.3 和 loguru。完整门禁显式接收单独保存的验收证据：

```bash
python3.12 tools/verify_release.py --evidence <验收证据文件>
python3.12 tools/make_release_archive.py --evidence <验收证据文件>
```

完整门禁要求四个平台的实际执行记录与当前产物、公开头、模型及测试输入匹配，并运行本机 wheel 的独立导入、两个联合导入顺序和持续伺服仿真。缺失证据或门禁失败会阻止归档。归档仅包含 SHA256SUMS 审核文件及清单本身，不包含执行记录、缓存或 Git 历史。

`validate_platform.py` 在对应平台执行示例链接、Frame、无设备夹爪、ServoJ/ServoP 仿真、参数门禁及 Python 调用检查。使用 `--execution-mode native`（RISC-V 使用 `qemu`），通过 `--output-dir` 指定单独的记录目录，通过 `--log-id` 指定日志标识；三个原生平台还用 `--smoke-python 3.10=<解释器>`、`3.11=<解释器>`、`3.13=<解释器>` 提供已安装当前主臂 Conda 包的解释器。

`servo_regression.py` 覆盖目标应用、反馈、超时、冲突、停止及重启。suite 5 保留默认/自定义限制下的运动中前向、反向和多次覆盖目标，检查收敛、指令连续性、无超时/限位故障及相同目标续期；C++ 共享库也独立执行运动中换目标。运动中停止覆盖默认/自定义限制和单次/持续发令，按指令状态与动态限制检查制动上界、换向及零速 IDLE；活动 ServoJ 的通用取消须返回 -8，专用停止使用 `stop_servoj()`。这些容限是测试判定，不会改变 SDK 的运动限制。

CI 的日常检查运行本机回归；候选分支、手动触发或版本 tag 执行 Linux x86_64、ARM64、Windows 原生检查及 RISC-V QEMU 检查。最终作业校验实际日志哈希，在临时目录汇总证据并作为独立附件上传，SDK 目录不写入验收记录。仅最后的汇总/归档作业调整时可核对已执行工作流快照；追加作业、顶层配置或执行作业及其他测试输入变化仍须重新验收。RISC-V QEMU 通过不代表物理板卡验收。

历史证据若绑定了示例 Markdown 文档，纯文档修正须提供已执行原文和修正前后哈希，逐平台核对后才可复用；此规则不适用于测试代码、接口、模型或二进制。完整验收记录仍单独保存，不随 SDK 归档。

版本提档仅涉及包元数据时，外置证据可附原归档及其 SHA-256。`promote_package_version.py` 按固定规则生成新包；门禁逐包比对结果，并继续核对全部运行文件和实际测试输入。运行代码发生变化仍须重新验收，历史执行记录不得改写。

`numpy_import_regression.py` 在独立子进程覆盖 NumPy、主臂、独立夹爪的六种导入顺序，并执行模型加载、NumPy 数组 MIT 输入及反馈检查。`servo_regression.py --timeout-recovery-only` 覆盖默认/自定义限制下 BRAKING 中续发及 HOLDING 后改目标。`record_environment.py` 自动记录实际 OS、Python、NumPy、loguru 和 Conda/dpkg 依赖；原始记录与日志仍保存在 SDK 外。
