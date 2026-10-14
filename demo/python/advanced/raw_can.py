"""原始 CAN 帧收发示例；不需要使能机械臂电机。"""

import threading
import time

import oneroarm


DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_l"
TEST_CAN_ID = 0x100  # 必须避开 SDK 保留 ID
TEST_PAYLOAD = bytes.fromhex("DE AD BE EF")
RECEIVE_TIMEOUT_S = 5.0


def check_result(name: str, result: int) -> None:
    if result != oneroarm.ONERO_CAN_OK:
        raise RuntimeError(f"{name} failed: {result}")


def main() -> None:
    config = oneroarm.OneroConfig()
    config.device = DEVICE
    config.robot_model = ROBOT_MODEL
    config.dof = 7
    config.version = "A1"
    config.mount_orientation = "vertical"

    arm = oneroarm.OneroArm(config)
    received = threading.Event()

    def on_frame(can_id: int, payload: bytes) -> None:
        print(f"rx id=0x{can_id:03X}, data={payload.hex(' ')}")
        received.set()

    check_result("register_can_frame_callback", arm.register_can_frame_callback(on_frame))
    try:
        check_result("send_can_frame", arm.send_can_frame(TEST_CAN_ID, TEST_PAYLOAD))
        deadline = time.monotonic() + RECEIVE_TIMEOUT_S
        while not received.is_set() and time.monotonic() < deadline:
            check_result("pump_can_bus", arm.pump_can_bus(50))
        if not received.is_set():
            print("no response received; this is expected when no node replies")
    finally:
        result = arm.clear_can_frame_callback()
        if result != oneroarm.ONERO_CAN_OK:
            print(f"warning: clear_can_frame_callback failed: {result}")


if __name__ == "__main__":
    main()
