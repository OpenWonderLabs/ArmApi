"""MIT 力位混合控制：以 100 Hz 保持当前关节位置。"""

from collections.abc import Iterable
import math
import time

import oneroarm


DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_r"
CONTROL_PERIOD_S = 0.01
CONTROL_DURATION_S = 1.0
KP = [150.0, 150.0, 150.0, 150.0, 30.0, 30.0, 30.0]
KD = [4.0, 4.0, 4.0, 4.0, 1.0, 1.0, 1.0]


def check_result(name: str, result: int) -> None:
    if result != oneroarm.ONERO_OK:
        raise RuntimeError(f"{name} failed: {result}")


def require_joint_array(
    name: str,
    values: Iterable[float],
    dof: int,
) -> list[float]:
    result = list(values)
    if len(result) != dof or not all(math.isfinite(value) for value in result):
        raise RuntimeError(f"invalid {name}")
    return result


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
        target = require_joint_array(
            "joint feedback",
            arm.get_joint_positions_from_motors(),
            config.dof,
        )
        zeros = [0.0] * config.dof
        gravity = require_joint_array(
            "gravity torque",
            arm.compute_gravity_torque(target),
            config.dof,
        )

        deadline = time.monotonic() + CONTROL_DURATION_S
        next_tick = time.monotonic()
        while time.monotonic() < deadline:
            check_result(
                "control_mit",
                arm.control_mit(KP, KD, target, zeros, gravity),
            )
            next_tick += CONTROL_PERIOD_S
            sleep_s = next_tick - time.monotonic()
            if sleep_s > 0.0:
                time.sleep(sleep_s)
            else:
                next_tick = time.monotonic()

        check_result("restore_arm", arm.restore_arm())
    finally:
        if enable_attempted and not arm.disable_motors():
            print("warning: disable_motors failed")


if __name__ == "__main__":
    main()
