"""movej_demo.py — OneroArm Python：单一 movej 关节空间运动示例

序列：enable → restore_arm()(zero) → movej(target) → restore_arm()(zero) → disable
"""
import time
import oneroarm

# === 关节空间目标（rad） ==================
JOINT_INDEX = 3        # 0-based: joint4
JOINT_VALUE_RAD = 0.6
# =========================================


def build_config() -> oneroarm.OneroConfig:
    cfg = oneroarm.OneroConfig()
    cfg.device = "/dev/ttyACM1"
    cfg.robot_model = "a1_r"
    cfg.version = "A1"
    cfg.mount_orientation = "vertical"
    return cfg


def checked(name: str, ret: int) -> None:
    if ret != 0:
        raise RuntimeError(f"{name} failed, ret={ret}")
    print(f"[OK] {name}")


def main() -> None:
    cfg = build_config()
    arm = oneroarm.OneroArm(cfg)

    enabled = arm.enable_motors()
    if not enabled:
        print("[!] enable_motors failed (无硬件预期)")
    time.sleep(1.0)

    zero = [0.0] * cfg.dof
    target = list(zero)
    target[JOINT_INDEX] = JOINT_VALUE_RAD

    try:
        checked("restore_arm() -> zero", arm.restore_arm())
        time.sleep(1.0)
        checked("movej(target)", arm.movej(target, speed_scale=1.5, trajectory_connect=0))
        time.sleep(1.0)
        checked("restore_arm() -> zero", arm.restore_arm())
    finally:
        if enabled:
            arm.disable_motors()


if __name__ == "__main__":
    main()
