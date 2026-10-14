"""双臂并发 MoveJ 示例。

两个阻塞调用会从两个宿主线程近同时启动，但不提供共享轨迹时钟或
硬实时同步。
"""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
import threading

import oneroarm


LEFT_DEVICE = "/dev/ttyACM0"
RIGHT_DEVICE = "/dev/ttyACM1"
LEFT_MODEL = "a1_l"
RIGHT_MODEL = "a1_r"


def create_arm(device: str, robot_model: str) -> oneroarm.OneroArm:
    config = oneroarm.OneroConfig()
    config.device = device
    config.robot_model = robot_model
    config.dof = 7
    config.version = "A1"
    config.mount_orientation = "vertical"
    return oneroarm.OneroArm(config)


def check_result(name: str, result: int) -> None:
    if result != oneroarm.ONERO_OK:
        raise RuntimeError(f"{name} failed: {result}")


def run_parallel(
    label: str,
    left_call: Callable[[], int],
    right_call: Callable[[], int],
    cancel_both: Callable[[], None],
) -> None:
    start = threading.Barrier(2)

    def invoke(call: Callable[[], int]) -> int:
        start.wait(timeout=1.0)
        return call()

    pool = ThreadPoolExecutor(max_workers=2)
    futures = []
    try:
        left_future = pool.submit(invoke, left_call)
        right_future = pool.submit(invoke, right_call)
        futures = [left_future, right_future]
        left_result = left_future.result()
        right_result = right_future.result()
    except BaseException:
        cancel_both()
        for future in futures:
            try:
                future.result()
            except BaseException:
                pass
        raise
    finally:
        pool.shutdown(wait=True)

    check_result(f"left {label}", left_result)
    check_result(f"right {label}", right_result)


def main() -> None:
    if LEFT_DEVICE == RIGHT_DEVICE:
        raise ValueError("left and right arms must use different devices")

    left = create_arm(LEFT_DEVICE, LEFT_MODEL)
    right = create_arm(RIGHT_DEVICE, RIGHT_MODEL)
    left_enable_attempted = False
    right_enable_attempted = False

    def cancel_both() -> None:
        left.cancel_trajectory()
        right.cancel_trajectory()

    try:
        left_enable_attempted = True
        if not left.enable_motors():
            raise RuntimeError("left enable_motors failed")
        right_enable_attempted = True
        if not right.enable_motors():
            raise RuntimeError("right enable_motors failed")

        left_target = [0.0] * 7
        right_target = [0.0] * 7
        left_target[1] = 0.30
        right_target[1] = -0.30

        run_parallel(
            "restore_arm",
            left.restore_arm,
            right.restore_arm,
            cancel_both,
        )
        run_parallel(
            "movej",
            lambda: left.movej(left_target, speed_scale=0.5),
            lambda: right.movej(right_target, speed_scale=0.5),
            cancel_both,
        )
        run_parallel(
            "restore_arm",
            left.restore_arm,
            right.restore_arm,
            cancel_both,
        )
    finally:
        if left_enable_attempted and not left.disable_motors():
            print("warning: left disable_motors failed")
        if right_enable_attempted and not right.disable_motors():
            print("warning: right disable_motors failed")


if __name__ == "__main__":
    main()
