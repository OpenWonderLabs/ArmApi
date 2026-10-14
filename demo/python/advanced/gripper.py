"""选配夹爪的最小控制与状态读取示例。"""

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
    config.with_gripper = True

    arm = oneroarm.OneroArm(config)
    gripper = arm.gripper
    if gripper is None:
        raise RuntimeError("gripper is not available")

    arm_enable_attempted = False
    gripper_enable_attempted = False
    try:
        arm_enable_attempted = True
        if not arm.enable_motors():
            raise RuntimeError("enable_motors failed")
        gripper_enable_attempted = True
        if not gripper.enable():
            raise RuntimeError("gripper.enable failed")

        check_result("restore_arm", arm.restore_arm())
        check_result("set_position", gripper.set_position(0.0))
        check_result("move_position", gripper.move_position(50.0))
        check_result("force_control", gripper.force_control(0.0))

        status = gripper.status()
        print(
            f"position={status.position:.1f}%, force={status.force:.1f} N, "
            f"valid={status.valid}"
        )
        tactile = gripper.get_tactile()
        print(f"tactile valid={tactile.valid}, sensors={len(tactile.sensors)}")
    finally:
        if gripper_enable_attempted and not gripper.disable():
            print("warning: gripper.disable failed")
        if arm_enable_attempted and not arm.disable_motors():
            print("warning: disable_motors failed")


if __name__ == "__main__":
    main()
