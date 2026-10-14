"""ServoJ：以 100 Hz 持续更新最新关节目标。"""

import math
import time

import oneroarm


DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_r"
CONTROL_PERIOD_S = 0.01
STREAM_DURATION_S = 2.0
TARGET_VALID_S = 0.10


def check_result(name: str, result: int) -> None:
    if result != oneroarm.ONERO_OK:
        raise RuntimeError(f"{name} failed: {result}")


def read_joint_positions(arm: oneroarm.OneroArm, dof: int) -> list[float]:
    positions = list(arm.get_joint_positions_from_motors())
    if len(positions) != dof or not all(math.isfinite(value) for value in positions):
        raise RuntimeError("invalid joint feedback")
    return positions


def main() -> None:
    config = oneroarm.OneroConfig()
    config.device = DEVICE
    config.robot_model = ROBOT_MODEL
    config.dof = 7
    config.version = "A1"
    config.mount_orientation = "vertical"

    arm = oneroarm.OneroArm(config)
    enable_attempted = False
    servo_started = False
    try:
        enable_attempted = True
        if not arm.enable_motors():
            raise RuntimeError("enable_motors failed")

        check_result("restore_arm", arm.restore_arm())
        target = read_joint_positions(arm, config.dof)
        target[3] += 0.10

        check_result("start_servoj", arm.start_servoj())
        servo_started = True

        deadline = time.monotonic() + STREAM_DURATION_S
        next_tick = time.monotonic()
        while time.monotonic() < deadline:
            check_result(
                "servoj",
                arm.servoj(target, valid_for_seconds=TARGET_VALID_S),
            )
            next_tick += CONTROL_PERIOD_S
            sleep_s = next_tick - time.monotonic()
            if sleep_s > 0.0:
                time.sleep(sleep_s)
            else:
                next_tick = time.monotonic()

        status = arm.get_servoj_status()
        print(
            f"state={status.state}, accepted={status.accepted_sequence}, "
            f"applied={status.applied_sequence}"
        )
        if status.state == oneroarm.ServoJState.FAULT:
            raise RuntimeError(f"ServoJ fault: {status.last_error}")
        check_result("stop_servoj", arm.stop_servoj())
        servo_started = False
        check_result("restore_arm", arm.restore_arm())
    finally:
        if servo_started:
            result = arm.stop_servoj()
            if result != oneroarm.ONERO_OK:
                print(f"warning: stop_servoj failed: {result}")
        if enable_attempted and not arm.disable_motors():
            print("warning: disable_motors failed")


if __name__ == "__main__":
    main()
