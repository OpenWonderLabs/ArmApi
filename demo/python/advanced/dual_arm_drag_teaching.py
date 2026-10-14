"""双臂拖动示教：使用 SDK 共享起始时间录制和回放。

共享起始时间用于协调两条轨迹，不代表电机帧具备硬实时同步。
"""

from pathlib import Path
import time

import oneroarm


LEFT_DEVICE = "/dev/ttyACM0"
RIGHT_DEVICE = "/dev/ttyACM1"
CONTROL_PERIOD_S = 0.01
RECORD_DURATION_S = 10.0
REPLAY_TIMEOUT_S = 60.0
LOG_DIR = Path("trajectory_log/dual_arm")


def create_teaching(
    device: str,
    robot_model: str,
    record_file: Path,
) -> oneroarm.OneroDragTeaching:
    teaching = oneroarm.OneroDragTeaching()
    if not teaching.initialize(7, str(record_file), CONTROL_PERIOD_S):
        raise RuntimeError(f"initialize failed: {device}")
    if not teaching.set_hardware(device, "", robot_model, "vertical"):
        raise RuntimeError(f"set_hardware failed: {device}")
    teaching.set_replay_file(str(record_file))
    return teaching


def check_result(name: str, result: int) -> None:
    if result != oneroarm.ONERO_OK:
        raise RuntimeError(f"{name} failed: {result}")


def wait_for_next_tick(next_tick: float) -> float:
    next_tick += CONTROL_PERIOD_S
    sleep_s = next_tick - time.monotonic()
    if sleep_s > 0.0:
        time.sleep(sleep_s)
        return next_tick
    return time.monotonic()


def tick_both(
    left: oneroarm.OneroDragTeaching,
    right: oneroarm.OneroDragTeaching,
    deadline: float,
) -> None:
    next_tick = time.monotonic()
    while time.monotonic() < deadline:
        left.timer_callback()
        right.timer_callback()
        if (
            left.get_state() != oneroarm.DragTeachingState.RECORDING
            or right.get_state() != oneroarm.DragTeachingState.RECORDING
        ):
            raise RuntimeError("one arm stopped recording unexpectedly")
        next_tick = wait_for_next_tick(next_tick)


def main() -> None:
    if LEFT_DEVICE == RIGHT_DEVICE:
        raise ValueError("left and right arms must use different devices")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    left = create_teaching(LEFT_DEVICE, "a1_l", LOG_DIR / "left.dat")
    right = create_teaching(RIGHT_DEVICE, "a1_r", LOG_DIR / "right.dat")

    try:
        print(f"move both arms now; recording for {RECORD_DURATION_S:.0f} seconds")
        check_result(
            "start dual recording",
            oneroarm.OneroDragTeaching.handle_command_dual(left, right, 1),
        )
        recording_failed = False
        try:
            tick_both(left, right, time.monotonic() + RECORD_DURATION_S)
        except BaseException:
            recording_failed = True
            raise
        finally:
            result = oneroarm.OneroDragTeaching.handle_command_dual(
                left,
                right,
                2,
            )
            if result != oneroarm.ONERO_OK:
                if recording_failed:
                    print(f"warning: stop dual recording failed: {result}")
                else:
                    raise RuntimeError(
                        f"stop dual recording failed: {result}"
                    )

        input("press Enter to replay both trajectories...")
        check_result(
            "start dual replay",
            oneroarm.OneroDragTeaching.handle_command_dual(left, right, 3),
        )
        replay_deadline = time.monotonic() + REPLAY_TIMEOUT_S
        next_tick = time.monotonic()
        while time.monotonic() < replay_deadline:
            left_replaying = (
                left.get_state() == oneroarm.DragTeachingState.REPLAYING
            )
            right_replaying = (
                right.get_state() == oneroarm.DragTeachingState.REPLAYING
            )
            if not left_replaying and not right_replaying:
                break
            if left_replaying != right_replaying:
                raise RuntimeError("dual replay states diverged")
            left.timer_callback()
            right.timer_callback()
            next_tick = wait_for_next_tick(next_tick)
        if (
            left.get_state() == oneroarm.DragTeachingState.REPLAYING
            or right.get_state() == oneroarm.DragTeachingState.REPLAYING
        ):
            raise TimeoutError("dual replay timed out")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        result = oneroarm.OneroDragTeaching.handle_command_dual(left, right, 0)
        if result != oneroarm.ONERO_OK:
            print(f"warning: stop dual teaching failed: {result}")


if __name__ == "__main__":
    main()
