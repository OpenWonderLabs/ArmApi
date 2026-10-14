"""规划轨迹缓冲：入队 MoveJ、MoveP、MoveL 后一次执行。"""

import oneroarm


DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_r"


def check_result(name: str, result: int) -> None:
    if result != oneroarm.ONERO_OK:
        raise RuntimeError(f"{name} failed: {result}")


def make_pose(z: float) -> oneroarm.Pose:
    pose = oneroarm.Pose()
    pose.x, pose.y, pose.z = -0.30, -0.30, z
    pose.qw, pose.qx, pose.qy, pose.qz = 1.0, 0.0, 0.0, 0.0
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
        check_result("clear_trajectory_buffer", arm.clear_trajectory_buffer())

        first = [0.0] * config.dof
        first[3] = 0.30

        check_result(
            "queue movej",
            arm.movej(first, speed_scale=0.5, trajectory_connect=1),
        )
        check_result(
            "queue movep",
            arm.movep(make_pose(0.30), speed_scale=0.5, trajectory_connect=1),
        )
        check_result(
            "queue movel",
            arm.movel(make_pose(0.40), speed_scale=0.5, trajectory_connect=1),
        )
        check_result(
            "queue zero movej",
            arm.movej([0.0] * config.dof, speed_scale=0.5, trajectory_connect=1),
        )
        check_result(
            "execute_buffered_trajectory",
            arm.execute_buffered_trajectory(),
        )
    finally:
        if enable_attempted and not arm.disable_motors():
            print("warning: disable_motors failed")


if __name__ == "__main__":
    main()
