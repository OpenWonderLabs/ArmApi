"""MoveJ：关节空间运动的最小示例。"""

import oneroarm


DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_r"
JOINT_INDEX = 1  # joint2，索引从 0 开始
JOINT_VALUE_RAD = -0.3


def check_result(name: str, result: int) -> None:
    if result != oneroarm.ONERO_OK:
        raise RuntimeError(f"{name} failed: {result}")


def main() -> None:
    config = oneroarm.OneroConfig()
    config.device = DEVICE
    config.robot_model = ROBOT_MODEL
    config.dof = 7
    config.version = "A1"
    config.mount_orientation = "vertical"
    config.with_gripper = False

    arm = oneroarm.OneroArm(config)
    enable_attempted = False
    try:
        enable_attempted = True
        if not arm.enable_motors():
            raise RuntimeError("enable_motors failed")

        check_result("restore_arm", arm.restore_arm())

        target = [0.0] * config.dof
        target[JOINT_INDEX] = JOINT_VALUE_RAD
        duration = arm.estimate_movej_duration(target, speed_scale=0.5)
        print(f"estimated duration: {duration:.2f} s")
        check_result("movej", arm.movej(target, speed_scale=0.5))

        check_result("restore_arm", arm.restore_arm())
    finally:
        if enable_attempted and not arm.disable_motors():
            print("warning: disable_motors failed")


if __name__ == "__main__":
    main()
