"""movel_demo.py — OneroArm Python：单一 movel 笛卡尔直线运动示例

序列：enable → restore_arm()(zero) → movel(target) → restore_arm()(zero) → disable
"""
import time
import oneroarm

# === 笛卡尔目标位姿（右臂可达） ===========
TARGET_X  =  -0.30
TARGET_Y  =  -0.30
TARGET_Z  =  0.40
TARGET_QW =  1.00
TARGET_QX =  0.00
TARGET_QY =  0.00
TARGET_QZ =  0.00
# =========================================


def build_config() -> oneroarm.OneroConfig:
    cfg = oneroarm.OneroConfig()
    cfg.device = "/dev/ttyACM1"
    cfg.robot_model = "a1_r"
    cfg.version = "A1"
    cfg.mount_orientation = "vertical"
    return cfg


def make_target() -> oneroarm.Pose:
    p = oneroarm.Pose()
    p.x, p.y, p.z = TARGET_X, TARGET_Y, TARGET_Z
    p.qw, p.qx, p.qy, p.qz = TARGET_QW, TARGET_QX, TARGET_QY, TARGET_QZ
    return p


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

    target = make_target()

    try:
        checked("restore_arm() -> zero", arm.restore_arm())
        time.sleep(1.0)
        checked("movel(target)", arm.movel(target, speed_scale=1.0, trajectory_connect=0))
        time.sleep(1.0)
        checked("restore_arm() -> zero", arm.restore_arm())
    finally:
        if enabled:
            arm.disable_motors()


if __name__ == "__main__":
    main()
