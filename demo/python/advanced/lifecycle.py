"""机械臂初始化、使能、回零、指定姿态恢复和失能。"""

import oneroarm


DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_r"


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

    arm = oneroarm.OneroArm(config)
    print(f"hardware connected: {arm.is_hardware_connected()}")
    enable_attempted = False
    try:
        enable_attempted = True
        if not arm.enable_motors():
            raise RuntimeError("enable_motors failed")

        check_result("restore_arm", arm.restore_arm())
        print("joint positions:", list(arm.get_joint_positions_from_motors()))

        target = [0.0] * config.dof
        target[0] = 0.30
        check_result("restore_arm(target)", arm.restore_arm(target))
        check_result("restore_arm", arm.restore_arm())
    finally:
        if enable_attempted and not arm.disable_motors():
            print("warning: disable_motors failed")


if __name__ == "__main__":
    main()
