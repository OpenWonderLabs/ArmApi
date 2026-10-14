# 本地 Conda channel

RISC-V 本次只提供 CPython 3.12 wheel，不提供 Conda channel；见 [RISC-V 安装说明](../../RISC_V_GUIDE.md)。

当前 channel 包含 Linux x86_64、Linux arm64 和 Windows x86_64 的 `oneroarm` 与 `onerogripper` 1.2.1 包。主臂 build 为 `4`，独立夹爪 build 为 `3`。`oneroarm` 覆盖 CPython 3.10–3.13；`onerogripper` 当前为 CPython 3.12。

从 SDK 根目录执行：

```bash
micromamba create -n woanarm-sdk-120 \
  -c "file://$PWD/python/conda_channel/linux" \
  -c robostack-staging -c conda-forge \
  oneroarm=1.2.1 onerogripper=1.2.1 "numpy>=2,<2.3"
```

Linux x86_64 已在全新 Python 3.12 环境中完成 `oneroarm` 与 `onerogripper` 联合安装和导入，并检查运动接口。主 SDK 的其他 Python 版本和平台在各自原生构建任务中完成安装与导入；夹爪包也分别完成导入检查。

Windows 把 channel 地址改为 `file:///<SDK路径>/python/conda_channel/windows`。Linux x86_64 与 arm64 共用 `linux` channel，Conda 会按当前架构选择 `linux-64` 或 `linux-aarch64` 子目录。

复现本次三平台 Python 3.12 离线验收时，使用 [精确环境文件与安装步骤](../environments/README.md)。常规 channel 命令会重新解算依赖，不等同于精确复现已验证环境。

本 channel 的 15 个包版本均为 1.2.1；12 个主臂包的 build 号为 4，3 个独立夹爪包为 3。包内不含构建 recipe 或源目录链接。索引、安装文件清单和哈希与当前包一致。安装时使用当前 channel；升级后核对 SHA-256 并重启 Python 进程。
