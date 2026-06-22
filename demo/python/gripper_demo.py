"""gripper_demo.py — OneroArm Python：movej 同时控制夹爪开合

序列：
  OneroArm(cfg, with_gripper=True)
  → enable_motors()                         # 只使能机械臂关节
  → arm.gripper.enable()                    # 显式使能夹爪
  → restore_arm()(zero)
  → parallel: movej(target) + gripper open
  → parallel: movej(zero)   + gripper close
  → gripper.disable()
  → disable_motors()

注意：
  1. 当前夹爪百分比沿用夹爪 SDK 的“闭合百分比”语义：0% 偏张开，100% 偏闭合。
     如果实物方向与预期相反，只需要交换 GRIPPER_OPEN_PERCENT / GRIPPER_CLOSED_PERCENT。
  2. 并发依赖 Python binding 对阻塞的 movej / gripper.move_position 释放 GIL。
"""
from __future__ import annotations

import threading
import time
from typing import Callable

import oneroarm

# === Serial / model configuration ==========================================
DEVICE = "/dev/ttyACM0"
ROBOT_MODEL = "a1_r"
# ===========================================================================

# === Arm movej target ========================================================
JOINT_INDEX = 1        # 0-based: joint2
JOINT_VALUE_RAD = -0.3
MOVE_SPEED = 1.0
# ===========================================================================

# === Gripper target ==========================================================
GRIPPER_OPEN_PERCENT = 0.0
GRIPPER_CLOSED_PERCENT = 100.0
GRIPPER_MAX_VEL = 100.0
GRIPPER_MAX_ACC = 250.0
GRIPPER_MAX_JERK = 1000.0
# ===========================================================================

# === Tactile feedback ========================================================
TACTILE_PRINT_HZ = 10.0
# ===========================================================================


def build_config() -> oneroarm.OneroConfig:
    cfg = oneroarm.OneroConfig()
    cfg.device = DEVICE
    cfg.robot_model = ROBOT_MODEL
    cfg.version = "A1"
    cfg.mount_orientation = "vertical"

    if not hasattr(cfg, "with_gripper"):
        raise RuntimeError("当前 oneroarm 模块不包含 with_gripper，请先安装/同步带夹爪支持的版本。")

    cfg.with_gripper = True
    return cfg


def create_arm_with_gripper(cfg: oneroarm.OneroConfig) -> oneroarm.OneroArm:
    try:
        arm = oneroarm.OneroArm(cfg, with_gripper=True)
    except TypeError:
        # 兼容只通过 cfg.with_gripper 传参的构造形式。
        arm = oneroarm.OneroArm(cfg)

    has_gripper = getattr(arm, "has_gripper", lambda: False)
    if not has_gripper() or getattr(arm, "gripper", None) is None:
        raise RuntimeError("arm.gripper 未创建，请确认 cfg.with_gripper=True 且运行库已更新。")

    return arm


def checked(name: str, ret: int) -> None:
    if ret != 0:
        raise RuntimeError(f"{name} failed, ret={ret}")
    print(f"[OK] {name}")


def checked_bool(name: str, ok: bool) -> None:
    if not ok:
        raise RuntimeError(f"{name} failed")
    print(f"[OK] {name}")


def make_joint_target(cfg: oneroarm.OneroConfig, joint_value: float) -> list[float]:
    target = [0.0] * cfg.dof
    target[JOINT_INDEX] = joint_value
    return target


def gripper_status_text(gripper: oneroarm.OneroGripper) -> str:
    st = gripper.status()
    return (
        f"valid={st.valid}, position={st.position:.1f}%, "
        f"velocity={st.velocity:.1f}%/s, force={st.force:.1f}, error={st.error}"
    )


def tactile_status_text(gripper: oneroarm.OneroGripper) -> str:
    tactile = gripper.get_tactile()
    parts = []

    for sensor in tactile.sensors:
        total = sensor.total_force
        if sensor.valid and total.valid:
            parts.append(
                f"sensor=0x{sensor.sensor_id:02X} "
                f"fx={total.fx:.2f}N fy={total.fy:.2f}N fz={total.fz:.2f}N"
            )
        else:
            parts.append(f"sensor=0x{sensor.sensor_id:02X} invalid")

    return f"valid={tactile.valid}, " + "; ".join(parts)


def start_tactile_printer(
    gripper: oneroarm.OneroGripper,
) -> tuple[threading.Event, threading.Thread]:
    if not hasattr(gripper, "get_tactile"):
        raise RuntimeError("当前 oneroarm 模块不包含 gripper.get_tactile，请先安装/同步带触觉支持的版本。")

    stop_event = threading.Event()
    period = 1.0 / TACTILE_PRINT_HZ

    def worker() -> None:
        next_tick = time.monotonic()
        while not stop_event.is_set():
            try:
                print(f"[TACTILE] {tactile_status_text(gripper)}")
            except BaseException as exc:
                print(f"[TACTILE] read failed: {exc!r}")

            next_tick += period
            wait_s = max(0.0, next_tick - time.monotonic())
            stop_event.wait(wait_s)

    thread = threading.Thread(target=worker, name="tactile-printer", daemon=True)
    thread.start()
    return stop_event, thread


def run_parallel(label: str, jobs: dict[str, Callable[[], int]]) -> None:
    print(f"\n=== {label} ===")
    results: dict[str, object] = {}

    def worker(name: str, fn: Callable[[], int]) -> None:
        try:
            results[name] = fn()
        except BaseException as exc:
            results[name] = exc

    threads = [
        threading.Thread(target=worker, name=f"{label}-{name}", args=(name, fn))
        for name, fn in jobs.items()
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    for name in jobs:
        ret = results.get(name)
        if isinstance(ret, BaseException):
            raise RuntimeError(f"{label}: {name} raised {ret!r}") from ret
        if not isinstance(ret, int):
            raise RuntimeError(f"{label}: {name} returned invalid result {ret!r}")
        checked(f"{label}: {name}", ret)


def gripper_move(gripper: oneroarm.OneroGripper, percent: float) -> int:
    return gripper.move_position(
        percent,
        max_vel=GRIPPER_MAX_VEL,
        max_acc=GRIPPER_MAX_ACC,
        max_jerk=GRIPPER_MAX_JERK,
    )
    # gripper.set_position(percent)
    # return 0


def gripper_close(gripper: oneroarm.OneroGripper) -> int:
    return gripper.force_control(20.0)


def main() -> None:
    cfg = build_config()
    arm = create_arm_with_gripper(cfg)
    gripper = arm.gripper

    arm_enabled = False
    gripper_enabled = False
    tactile_stop: threading.Event | None = None
    tactile_thread: threading.Thread | None = None

    zero = [0.0] * cfg.dof
    target = make_joint_target(cfg, JOINT_VALUE_RAD)

    try:
        arm_enabled = arm.enable_motors()
        if not arm_enabled:
            print("[!] enable_motors failed (无硬件预期)，跳过运动 demo")
            return
        print("[OK] enable_motors()")

        checked_bool("gripper.enable()", gripper.enable())
        gripper_enabled = True
        print(f"  gripper status after enable: {gripper_status_text(gripper)}")

        # tactile_stop, tactile_thread = start_tactile_printer(gripper)

        checked("restore_arm() -> zero", arm.restore_arm())
        time.sleep(2.0)

        # # 建立一个明确的起始夹爪状态，避免上一轮实验留下未知开合度。
        checked("gripper.move_position(closed)", gripper_move(gripper, GRIPPER_CLOSED_PERCENT))
        time.sleep(0.5)

        run_parallel(
            "movej(target) + gripper open",
            {
                "arm.movej(target)": lambda: arm.movej(target, speed_scale=MOVE_SPEED, trajectory_connect=0),
                "gripper.open": lambda: gripper_move(gripper, GRIPPER_OPEN_PERCENT),
            },
        )
        time.sleep(2.0)

        run_parallel(
            "movej(zero) + gripper close",
            {
                "arm.movej(zero)": lambda: arm.movej(zero, speed_scale=MOVE_SPEED, trajectory_connect=0),
                "gripper.close": lambda: gripper_close(gripper),
            },
        )

        time.sleep(2.0)

        print(f"  final gripper status: {gripper_status_text(gripper)}")
    finally:
        if tactile_stop is not None:
            tactile_stop.set()
        if tactile_thread is not None:
            tactile_thread.join(timeout=1.0)
        if gripper_enabled:
            gripper.disable()
            print("[OK] gripper.disable()")
        if arm_enabled:
            arm.disable_motors()
            print("[OK] disable_motors()")


if __name__ == "__main__":
    main()