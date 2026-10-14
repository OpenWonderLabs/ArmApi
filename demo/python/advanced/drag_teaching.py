"""单臂拖动示教：机械臂与夹爪回驱录制 10 秒，然后回放。"""

from pathlib import Path
import time

import oneroarm


DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_r"
CONTROL_PERIOD_S = 0.01
RECORD_DURATION_S = 10.0
REPLAY_TIMEOUT_S = 60.0
RECORD_FILE = Path("trajectory_log/drag_teaching.dat")


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


def main() -> None:
    RECORD_FILE.parent.mkdir(parents=True, exist_ok=True)
    teaching = oneroarm.OneroDragTeaching()
    if not teaching.initialize(7, str(RECORD_FILE), CONTROL_PERIOD_S):
        raise RuntimeError("initialize failed")
    if not teaching.set_hardware(
        DEVICE,
        "",
        ROBOT_MODEL,
        "vertical",
        with_gripper=True,
    ):
        raise RuntimeError("set_hardware failed")
    check_result(
        "set_gripper_teaching_mode",
        teaching.set_gripper_teaching_mode(
            oneroarm.GripperTeachingMode.BACKDRIVE,
        ),
    )

    try:
        print(f"move the arm now; recording for {RECORD_DURATION_S:.0f} seconds")
        check_result("start_recording", teaching.start_recording())
        record_deadline = time.monotonic() + RECORD_DURATION_S
        next_tick = time.monotonic()
        try:
            while time.monotonic() < record_deadline:
                teaching.timer_callback()
                next_tick = wait_for_next_tick(next_tick)
        finally:
            result = teaching.stop_recording()
            if result != oneroarm.ONERO_OK:
                print(f"warning: stop_recording failed: {result}")

        input("press Enter to replay the recorded trajectory...")
        teaching.set_replay_file(str(RECORD_FILE))
        check_result("start_replay", teaching.start_replay())
        replay_deadline = time.monotonic() + REPLAY_TIMEOUT_S
        next_tick = time.monotonic()
        while (
            teaching.get_state() == oneroarm.DragTeachingState.REPLAYING
            and time.monotonic() < replay_deadline
        ):
            teaching.timer_callback()
            next_tick = wait_for_next_tick(next_tick)
        if teaching.get_state() == oneroarm.DragTeachingState.REPLAYING:
            raise TimeoutError("replay timed out")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        result = teaching.handle_command(0)
        if result != oneroarm.ONERO_OK:
            print(f"warning: stop failed: {result}")


if __name__ == "__main__":
    main()
