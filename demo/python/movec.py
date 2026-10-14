"""MoveC：经过 via_pose 到 target_pose 的圆弧运动。"""

import math

import oneroarm


DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_r"
SAFE_START = [-0.158, -1.0, 1.2, -0.8, 0.1, 0.8, -1.0]


def check_result(name: str, result: int) -> None:
    if result != oneroarm.ONERO_OK:
        raise RuntimeError(f"{name} failed: {result}")


def require_valid_pose(pose: oneroarm.Pose) -> oneroarm.Pose:
    values = (pose.x, pose.y, pose.z, pose.qw, pose.qx, pose.qy, pose.qz)
    quaternion_norm = pose.qw**2 + pose.qx**2 + pose.qy**2 + pose.qz**2
    if not all(math.isfinite(value) for value in values) or not math.isclose(
        quaternion_norm,
        1.0,
        rel_tol=1e-3,
        abs_tol=1e-3,
    ):
        raise RuntimeError("invalid end-effector pose feedback")
    return pose


def offset_pose(source: oneroarm.Pose, dx: float, dz: float) -> oneroarm.Pose:
    pose = oneroarm.Pose()
    pose.x = source.x + dx
    pose.y = source.y
    pose.z = source.z + dz
    pose.qw = source.qw
    pose.qx = source.qx
    pose.qy = source.qy
    pose.qz = source.qz
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

        check_result("restore_arm(SAFE_START)", arm.restore_arm(SAFE_START))
        start = require_valid_pose(arm.get_end_effector_pose())
        via_pose = offset_pose(start, dx=0.005, dz=0.002)
        target_pose = offset_pose(start, dx=0.010, dz=0.0)
        check_result("movec", arm.movec(via_pose, target_pose, speed_scale=0.3))
        check_result("restore_arm", arm.restore_arm())
    finally:
        if enable_attempted and not arm.disable_motors():
            print("warning: disable_motors failed")


if __name__ == "__main__":
    main()
