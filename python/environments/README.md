# 已验证的 Python 3.12 环境

RISC-V 使用 Ubuntu 24.04 apt 环境，不使用这些三平台 Conda 锁文件。安装入口见 [RISC-V 安装说明](../../RISC_V_GUIDE.md)。

三个 explicit 文件记录已验证环境的第三方依赖、精确构建版本和下载校验值。各平台文件与对应的 Python 3.12 原生验证环境一致。按实际平台选择文件，不能跨平台使用。Linux x86_64 的精确环境包含要求 x86_64-v3 指令集的 BLASFEO 构建；常规 channel 安装由包管理器选择与主机匹配的构建。文件不含 SDK 包或内部仓库地址；SDK 包来自本交付树，SHA-256 见根目录 SHA256SUMS。

从 SDK 根目录执行。Linux x86_64：

```bash
micromamba create -y -n woanarm-validated -f python/environments/linux-x86_64-py312-explicit.txt
micromamba install -y -n woanarm-validated --no-deps \
  ./python/conda_channel/linux/linux-64/oneroarm-1.2.1-py312ha1a5271_5.conda \
  ./python/conda_channel/linux/linux-64/onerogripper-1.2.1-py312h2bc3f7f_3.conda
```

Linux arm64：

```bash
micromamba create -y -n woanarm-validated -f python/environments/linux-arm64-py312-explicit.txt
micromamba install -y -n woanarm-validated --no-deps \
  ./python/conda_channel/linux/linux-aarch64/oneroarm-1.2.1-py312hdb8e320_5.conda \
  ./python/conda_channel/linux/linux-aarch64/onerogripper-1.2.1-py312h3f4af3b_3.conda
```

Windows x86_64，在 PowerShell 中执行：

```powershell
micromamba create -y -n woanarm-validated -f python/environments/windows-x86_64-py312-explicit.txt
micromamba install -y -n woanarm-validated --no-deps ./python/conda_channel/windows/win-64/oneroarm-1.2.1-py312ha41a7fa_5.conda ./python/conda_channel/windows/win-64/onerogripper-1.2.1-py312h659f713_3.conda
```

这里的 --no-deps 仅用于已经由对应 explicit 文件完整创建的环境，避免重新解算已验证的依赖。不要将第二步用于其他环境。

安装后用两个独立进程检查导入顺序：

```bash
micromamba run -n woanarm-validated python -c "import oneroarm, onerogripper; print('OK')"
micromamba run -n woanarm-validated python -c "import onerogripper, oneroarm; print('OK')"
```

此处仅检查导入；实际构造和代表性离线调用的结果见 [发布说明](../../RELEASE_NOTES.md)。精确环境当前只覆盖 Python 3.12。Python 3.10、3.11、3.13 的主臂包仍可按 [channel 说明](../conda_channel/README.md)安装，但不属于当前精确环境及联合功能验证范围。

RISC-V 的 `linux-riscv64-ubuntu24.04-packages.tsv` 是依赖参考，不作为当前容器的精确锁定环境。suite 5 自动将本次实际 dpkg 包名和版本、OS、Python、NumPy、loguru 写入原始执行日志及平台证据，并同时绑定参考文件哈希。验收环境以本次生成的记录为准。
