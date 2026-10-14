"""取消正在执行的规划运动。

cancel_trajectory() 请求取消 Move/轨迹或 ServoP；返回 0 仅表示请求已记录。
活动 ServoJ 返回 -8 且继续运行，必须使用 stop_servoj()；这是软件接口，不是安全级急停。
"""

import threading
import time

import oneroarm


DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_r"
CANCEL_AFTER_S = 1.0


def check_result(name: str, result: int) -> None:
    if result != oneroarm.ONERO_OK:
        raise RuntimeError(f"{name} failed: {result}")


def main() -> None:
    config = oneroarm.OneroConfig()
    config.device = DEVICE
    config.robot_model = ROBOT_MODEL
    config.dof = 7
    config.version = "A1"
    config.mount_orientation = "vertical"

    arm = oneroarm.OneroArm(config)
    enable_attempted = False
    move_result: list[int] = []
    try:
        enable_attempted = True
        if not arm.enable_motors():
            raise RuntimeError("enable_motors failed")

        check_result("restore_arm", arm.restore_arm())
        target = [0.0] * config.dof
        target[3] = 1.0

        worker = threading.Thread(
            target=lambda: move_result.append(
                arm.movej(target, speed_scale=0.2)
            )
        )
        worker.start()
        try:
            time.sleep(CANCEL_AFTER_S)
            check_result("cancel_trajectory", arm.cancel_trajectory())
        except BaseException:
            arm.cancel_trajectory()
            raise
        finally:
            worker.join()

        if len(move_result) != 1:
            raise RuntimeError(f"unexpected movej result: {move_result}")
        if move_result[0] == oneroarm.ONERO_ERR_INTERRUPTED:
            print("movej was cancelled")
        elif move_result[0] == oneroarm.ONERO_OK:
            print("movej completed before cancellation")
        else:
            raise RuntimeError(f"movej failed: {move_result[0]}")

        arm.reset_stop_signal()
        check_result("restore_arm", arm.restore_arm())
    finally:
        if enable_attempted and not arm.disable_motors():
            print("warning: disable_motors failed")


if __name__ == "__main__":
    main()
