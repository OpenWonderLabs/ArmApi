"""低层关节轨迹：流式下发单点和一次提交完整点列。"""

import math
import time

import oneroarm


DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_r"
DT_S = 0.01
DURATION_S = 1.0
POINT_STREAM_DURATION_S = 0.20


def check_result(name: str, result: int) -> None:
    if result != oneroarm.ONERO_OK:
        raise RuntimeError(f"{name} failed: {result}")


def read_joint_positions(arm: oneroarm.OneroArm, dof: int) -> list[float]:
    positions = list(arm.get_joint_positions_from_motors())
    if len(positions) != dof or not all(math.isfinite(value) for value in positions):
        raise RuntimeError("invalid joint feedback")
    return positions


def make_trajectory(start: list[float]) -> list[oneroarm.TrajectoryPoint]:
    delta = [0.0] * len(start)
    delta[3] = 0.10
    points: list[oneroarm.TrajectoryPoint] = []

    steps = round(DURATION_S / DT_S)
    for index in range(steps + 1):
        u = index / steps
        position_scale = 10 * u**3 - 15 * u**4 + 6 * u**5
        velocity_scale = (30 * u**2 - 60 * u**3 + 30 * u**4) / DURATION_S
        acceleration_scale = (60 * u - 180 * u**2 + 120 * u**3) / DURATION_S**2

        point = oneroarm.TrajectoryPoint()
        point.position = [
            position + change * position_scale
            for position, change in zip(start, delta)
        ]
        point.velocity = [change * velocity_scale for change in delta]
        point.acceleration = [change * acceleration_scale for change in delta]
        points.append(point)

    return points


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
        start = read_joint_positions(arm, config.dof)
        zeros = [0.0] * config.dof

        stream_deadline = time.monotonic() + POINT_STREAM_DURATION_S
        next_tick = time.monotonic()
        while time.monotonic() < stream_deadline:
            check_result(
                "send_trajectory_point",
                arm.send_trajectory_point(start, zeros),
            )
            next_tick += DT_S
            sleep_s = next_tick - time.monotonic()
            if sleep_s > 0.0:
                time.sleep(sleep_s)
            else:
                next_tick = time.monotonic()

        check_result("send_trajectory", arm.send_trajectory(make_trajectory(start)))
        check_result("restore_arm", arm.restore_arm())
    finally:
        if enable_attempted and not arm.disable_motors():
            print("warning: disable_motors failed")


if __name__ == "__main__":
    main()
