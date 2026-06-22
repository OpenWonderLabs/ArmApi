"""enable_restore_demo.py — OneroArm Python：使能与 restore 解耦演示

★ 新行为（与旧版的关键区别）
  旧版：enable_motors() 内部会自动把机械臂 restore 到零位。
  新版：enable_motors() 只使能电机、不再自动运动——机械臂停在通电瞬间的位置；
        归零 / 去任意关节位姿，改由用户在使能后显式调用 restore_arm() 完成。

  好处：使能不再隐含一次"突然回零"运动；用户可以决定 restore 的目标和时机，
        甚至 restore 到非零的任意安全姿态。

序列：
  enable_motors()                # 仅使能，不自动归零
  → get_joint_positions()        # 证明使能后机械臂没有自动移动
  → restore_arm()                # 显式回零（内部安全速度 0.8 缩放）
  → restore_arm(custom_target)   # restore 到任意关节状态（新增重载）
  → restore_arm()                # 再回零
  → disable_motors()

依赖（注意：当前发布的 oneroarm 模块尚未暴露下列方法，需先更新 pybind 绑定
      并重编 oneroarm 模块后本 demo 才能实际运行）：
  - OneroArm.restore_arm()                    -> int  (0=成功)
  - OneroArm.restore_arm(target: list[float]) -> int  (0=成功)
"""
import time
import oneroarm

# === 自定义 restore 目标（rad，需在关节限位内；这里按 a1_r 取安全值） ===
#   index: 0=j1 1=j2 2=j3 3=j4 4=j5 5=j6 6=j7
CUSTOM_TARGET = {0: 0.3}   # 其余关节为 0
# ===================================================================


def build_config() -> oneroarm.OneroConfig:
    cfg = oneroarm.OneroConfig()
    cfg.device = "/dev/ttyACM0"
    cfg.robot_model = "a1_l"
    cfg.version = "A1"
    cfg.mount_orientation = "vertical"
    return cfg


def checked(name: str, ret: int) -> None:
    if ret != 0:
        raise RuntimeError(f"{name} failed, ret={ret}")
    print(f"[OK] {name}")


def fmt_joints(arm: "oneroarm.OneroArm") -> str:
    pos = arm.get_joint_positions()
    vals = [pos[i] for i in range(len(pos))]
    return "[" + ", ".join(f"{v:+.3f}" for v in vals) + "]"


def main() -> None:
    cfg = build_config()
    arm = oneroarm.OneroArm(cfg)

    enabled = arm.enable_motors()
    if not enabled:
        print("[!] enable_motors failed (无硬件预期)")
    time.sleep(1.0)

    # ★ 使能后机械臂应停在原地，而非自动归零——打印当前关节位置佐证。
    print(f"使能后当前关节位置（应为通电瞬间位置，非自动归零）: {fmt_joints(arm)}")

    zero = [0.0] * cfg.dof
    custom = list(zero)
    for idx, val in CUSTOM_TARGET.items():
        custom[idx] = val

    try:
        # 1) 显式回零
        checked("restore_arm() -> zero", arm.restore_arm())
        time.sleep(1.0)
        print(f"  回零后关节位置: {fmt_joints(arm)}")

        # 2) restore 到任意关节状态（新增重载）
        checked("restore_arm(custom)", arm.restore_arm(custom))
        time.sleep(1.0)
        print(f"  到自定义姿态后关节位置: {fmt_joints(arm)}")

        # 3) 再回零
        checked("restore_arm() -> zero", arm.restore_arm())
        time.sleep(1.0)
        print(f"  再次回零后关节位置: {fmt_joints(arm)}")
    finally:
        if enabled:
            arm.disable_motors()


if __name__ == "__main__":
    main()
