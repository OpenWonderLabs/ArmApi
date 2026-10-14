"""MoveL：末端沿直线运动到绝对 base_T_link7 位姿。"""

import oneroarm


DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_r"
TARGET = (-0.30, -0.30, 0.40, 1.0, 0.0, 0.0, 0.0)


def check_result(name: str, result: int) -> None:
    if result != oneroarm.ONERO_OK:
        raise RuntimeError(f"{name} failed: {result}")


def make_pose(values: tuple[float, ...]) -> oneroarm.Pose:
    pose = oneroarm.Pose()
    pose.x, pose.y, pose.z, pose.qw, pose.qx, pose.qy, pose.qz = values
    return pose


def main() -> None:
    config = oneroarm.OneroConfig()
    config.device = DEVICE
    config.robot_model = ROBOT_MODEL
    config.dof = 7
    config.version = "A1"
    config.mount_orientation = "vertical"

    arm = oneroarm.OneroArm(config)
    enable_attempted = False
    try:
        enable_attempted = True
        if not arm.enable_motors():
            raise RuntimeError("enable_motors failed")

        check_result("restore_arm", arm.restore_arm())
        check_result("movel", arm.movel(make_pose(TARGET), speed_scale=0.3))
        check_result("restore_arm", arm.restore_arm())
    finally:
        if enable_attempted and not arm.disable_motors():
            print("warning: disable_motors failed")


if __name__ == "__main__":
    main()
