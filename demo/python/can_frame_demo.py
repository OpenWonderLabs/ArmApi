"""can_frame_demo.py — OneroArm Python：原始 CAN 帧收发最小示例

演示原始 CAN 帧四个接口：
  - register_can_frame_callback：注册接收回调（仅非保留 ID 派发）
  - send_can_frame              ：向**非保留** ID 发送一帧
  - pump_can_bus                ：主动驱动一次串口 rx，把帧从 SLCAN 缓冲取出
  - clear_can_frame_callback    ：清回调

注意：
  - 本 demo **不调用 enable_motors** —— 串口在 OneroArm 构造时已打开，
    收发原始帧不需要电机使能。
  - 选用 CAN ID = 0x100，不在 SDK 保留集 (0x01-0x08, 0x11-0x17, 0x7FF) 内，
    不会被 ONERO_ERR_RAW_FRAME_RESERVED_ID 拦截。
  - 总线上若**没有**接听该 ID 的节点，回调可能不会触发；这是预期行为。
"""
import threading
import time

import oneroarm

# === 测试帧 ===============================
TEST_CAN_ID  = 0x100              # 非保留
TEST_PAYLOAD = bytes([0xDE, 0xAD, 0xBE, 0xEF])
PUMP_STEP_MS         = 50         # 单次 pump 步长；越小越能及时跳出阻塞
RECV_OVERALL_TIMEOUT = 5.0        # 秒：等待回帧的硬超时上限（无节点时必触发）
# =========================================

# 回调内禁止重入 arm 的 send_* / 运动控制方法，所以仅置位一个 Event，
# 让外层 pump 循环据此判断是否退出阻塞。
_recv_event = threading.Event()


def build_config() -> oneroarm.OneroConfig:
    cfg = oneroarm.OneroConfig()
    cfg.device = "/dev/ttyACM0"
    cfg.robot_model = "a1_l"
    cfg.version = "A1"
    cfg.mount_orientation = "vertical"
    return cfg


def on_can_frame(can_id: int, data: bytes) -> None:
    print(f"[RX] id=0x{can_id:03X} len={len(data)} data={data.hex(' ').upper()}")
    _recv_event.set()


def main() -> None:
    cfg = build_config()
    arm = oneroarm.OneroArm(cfg)

    rc = arm.register_can_frame_callback(on_can_frame)
    if rc != 0:
        print(f"register_can_frame_callback failed, ret={rc}")
    else:
        print("[OK] register_can_frame_callback")

    print(f"[TX] id=0x{TEST_CAN_ID:03X} len={len(TEST_PAYLOAD)} "
          f"data={TEST_PAYLOAD.hex(' ').upper()}")
    rc = arm.send_can_frame(TEST_CAN_ID, TEST_PAYLOAD)
    if rc != 0:
        print(f"[X] send_can_frame failed, ret={rc} (无硬件预期 -13)")
    else:
        print("[OK] send_can_frame")

    # 阻塞至收到任意非保留 ID 的 CAN 帧，或 RECV_OVERALL_TIMEOUT 到期
    deadline = time.monotonic() + RECV_OVERALL_TIMEOUT
    while not _recv_event.is_set() and time.monotonic() < deadline:
        arm.pump_can_bus(PUMP_STEP_MS)

    if _recv_event.is_set():
        print("[OK] 收到回帧")
    else:
        print(f"[X] {RECV_OVERALL_TIMEOUT:.1f}s 内未收到任何 CAN 帧")

    arm.clear_can_frame_callback()


if __name__ == "__main__":
    main()
