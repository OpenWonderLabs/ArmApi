# OneroGripper Python SDK

Ubuntu 24.04 riscv64 使用 `wheels/linux-riscv64/` 下的 CPython 3.12 wheel；联合安装见 [RISC-V 安装说明](../../RISC_V_GUIDE.md)。

当前 wheel 支持 Ubuntu 22.04+、Linux x86_64 和 CPython 3.12。在本包根目录执行：

```bash
python3.12 -m pip install ./gripper/python/wheels/linux-x86_64/onerogripper-1.2.1-3-cp312-cp312-linux_x86_64.whl
python3.12 -c 'import onerogripper; print(onerogripper.__file__)'
```

## 与主臂模块联合使用

共享状态类型各自在所属模块内注册，两个导入顺序均通过离线检查：

```bash
python3.12 -m pip install --force-reinstall --no-deps ./python/wheels/linux-x86_64/oneroarm-1.2.1-5-cp312-cp312-linux_x86_64.whl ./gripper/python/wheels/linux-x86_64/onerogripper-1.2.1-3-cp312-cp312-linux_x86_64.whl
python3.12 -c 'import oneroarm, onerogripper; print("arm -> gripper: OK")'
python3.12 -c 'import onerogripper, oneroarm; print("gripper -> arm: OK")'
```

主臂 wheel 的构建标签为 5，独立夹爪 wheel 为 3，版本均为 1.2.1。已有环境必须重新安装两个文件并重启 Python 进程。四种状态/触觉类型各自属于对应模块；请使用接口所属模块返回的对象。联合导入允许在一个进程使用两个模块，但同一物理设备仍应由一个控制所有者占用。随臂夹爪请通过 oneroarm 的 arm.gripper 访问；独立模块用于独立设备。

主臂及夹爪 wheel 使用一致的随包 C++ 运行库；两种导入顺序下的默认 URDF 加载、机械臂构造和代表性仿真调用已在 Python 3.12.14/3.12.15 下通过。本 wheel 使用 linux_x86_64 标签；Ubuntu 22.04+ 为支持基线，未声明 manylinux 标签。详见 [发布说明](../../RELEASE_NOTES.md)。

完整签名见 [onerogripper.pyi](onerogripper.pyi)，构建来源与验证范围见 [发布说明](../../RELEASE_NOTES.md)。
