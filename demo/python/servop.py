"""ServoP：以 100 Hz 持续更新最新笛卡尔目标。"""

import math
import time

import oneroarm


DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_r"
CONTROL_PERIOD_S = 0.01
STREAM_DURATION_S = 2.0


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


def offset_x(source: oneroarm.Pose, dx: float) -> oneroarm.Pose:
    pose = oneroarm.Pose()
    pose.x = source.x + dx
    pose.y = source.y
    pose.z = source.z
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

    limits = oneroarm.CartesianServoLimits()
    limits.max_linear_velocity = 0.02
    limits.max_angular_velocity = 0.10
    limits.max_linear_acceleration = 0.05
    limits.max_angular_acceleration = 0.20

    arm = oneroarm.OneroArm(config)
    enable_attempted = False
    servo_started = False
    try:
        enable_attempted = True
        if not arm.enable_motors():
            raise RuntimeError("enable_motors failed")

        check_result("restore_arm", arm.restore_arm())
        current = require_valid_pose(arm.get_end_effector_pose())
        target = offset_x(current, dx=0.01)

        check_result("start_servop", arm.start_servop())
        servo_started = True

        deadline = time.monotonic() + STREAM_DURATION_S
        next_tick = time.monotonic()
        while time.monotonic() < deadline:
            check_result("servop", arm.servop(target, limits))
            next_tick += CONTROL_PERIOD_S
            sleep_s = next_tick - time.monotonic()
            if sleep_s > 0.0:
                time.sleep(sleep_s)
            else:
                next_tick = time.monotonic()

        status = arm.get_servop_status()
        print(
            f"state={status.state}, accepted={status.accepted_sequence}, "
            f"applied={status.applied_sequence}"
        )
        if status.state == oneroarm.ServoPState.FAULT:
            raise RuntimeError(f"ServoP fault: {status.last_error}")
        check_result("stop_servop", arm.stop_servop())
        servo_started = False
        check_result("restore_arm", arm.restore_arm())
    finally:
        if servo_started:
            result = arm.stop_servop()
            if result != oneroarm.ONERO_OK:
                print(f"warning: stop_servop failed: {result}")
        if enable_attempted and not arm.disable_motors():
            print("warning: disable_motors failed")


if __name__ == "__main__":
    main()
