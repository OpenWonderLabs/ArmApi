"""dual_arm_coordination_demo.py — OneroArm Python：左右臂协同 movej + 急停示例

左右臂各创建一个 OneroArm 实例，分别绑定不同串口。先并发下发一组小幅镜像
movej，再并发下发一组慢速 movej，并由主线程同时触发 cancel_trajectory()
测试急停。

运行前按实际接线修改 LEFT_DEVICE / RIGHT_DEVICE。

序列：
  enable both
  → parallel restore_arm()(zero)
  → parallel movej(mirrored target)
  → parallel restore_arm()(zero)
  → parallel slow movej(mirrored estop target), cancel both after 1s
  → reset_stop_signal() on both
  → parallel restore_arm()(zero)
  → disable both

注意：
  急停部分与 estop_demo.py 有同样的 pybind 前置要求：阻塞的 movej 需要释放 GIL，
  否则主线程无法在运动中途执行 cancel_trajectory()。
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time

import oneroarm

# === Serial / model configuration ==========================================
LEFT_DEVICE = "/dev/ttyACM0"
RIGHT_DEVICE = "/dev/ttyACM1"
LEFT_MODEL = "a1_l"
RIGHT_MODEL = "a1_r"
# ===========================================================================

# === Motion parameters =======================================================
JOINT_INDEX = 1          # 0-based: joint4, symmetric limits on a1_l/a1_r
MOVE_TARGET_RAD = -0.3    # small movej smoke test
ESTOP_TARGET_RAD = -0.4   # larger target to leave time for emergency stop
MOVE_SPEED = 0.8
ESTOP_SPEED = 0.2
STOP_AFTER_S = 1.0
# ===========================================================================

MOVE_OK = 0
MOVE_INTERRUPTED = -6


@dataclass
class ArmEntry:
    name: str
    cfg: "oneroarm.OneroConfig"
    arm: "oneroarm.OneroArm"
    enabled: bool = False


def build_config(device: str, robot_model: str) -> oneroarm.OneroConfig:
    cfg = oneroarm.OneroConfig()
    cfg.device = device
    cfg.robot_model = robot_model
    cfg.version = "A1"
    cfg.mount_orientation = "vertical"
    return cfg


def make_arm(name: str, device: str, robot_model: str) -> ArmEntry:
    cfg = build_config(device, robot_model)
    return ArmEntry(name=name, cfg=cfg, arm=oneroarm.OneroArm(cfg))


def make_joint_target(cfg: oneroarm.OneroConfig, joint_value: float) -> list[float]:
    target = [0.0] * cfg.dof
    target[JOINT_INDEX] = joint_value
    return target


def checked(name: str, ret: int) -> None:
    if ret != MOVE_OK:
        raise RuntimeError(f"{name} failed, ret={ret}")
    print(f"[OK] {name}")


def _movej_worker(
    entry: ArmEntry,
    target: list[float],
    speed_scale: float,
    result: dict[str, object],
) -> None:
    try:
        result[entry.name] = entry.arm.movej(
            target,
            speed_scale=speed_scale,
            trajectory_connect=0,
        )
    except BaseException as exc:
        result[entry.name] = exc


def _restore_worker(entry: ArmEntry, result: dict[str, object]) -> None:
    try:
        result[entry.name] = entry.arm.restore_arm()
    except BaseException as exc:
        result[entry.name] = exc


def run_parallel_movej(
    label: str,
    entries: list[ArmEntry],
    targets: dict[str, list[float]],
    speed_scale: float,
) -> dict[str, int]:
    print(f"\n=== {label} ===")

    result: dict[str, object] = {}
    threads = [
        threading.Thread(
            target=_movej_worker,
            name=f"{entry.name}-movej",
            args=(entry, targets[entry.name], speed_scale, result),
        )
        for entry in entries
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    typed_result: dict[str, int] = {}
    for entry in entries:
        ret = result.get(entry.name)
        if isinstance(ret, BaseException):
            raise RuntimeError(f"{entry.name} {label} raised: {ret!r}") from ret
        if not isinstance(ret, int):
            raise RuntimeError(f"{entry.name} {label} returned invalid result: {ret!r}")
        typed_result[entry.name] = ret
        checked(f"{entry.name} {label}", ret)

    return typed_result


def run_parallel_restore(label: str, entries: list[ArmEntry]) -> dict[str, int]:
    print(f"\n=== {label} ===")

    result: dict[str, object] = {}
    threads = [
        threading.Thread(
            target=_restore_worker,
            name=f"{entry.name}-restore",
            args=(entry, result),
        )
        for entry in entries
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    typed_result: dict[str, int] = {}
    for entry in entries:
        ret = result.get(entry.name)
        if isinstance(ret, BaseException):
            raise RuntimeError(f"{entry.name} {label} raised: {ret!r}") from ret
        if not isinstance(ret, int):
            raise RuntimeError(f"{entry.name} {label} returned invalid result: {ret!r}")
        typed_result[entry.name] = ret
        checked(f"{entry.name} {label}", ret)

    return typed_result


def reset_stop_signal(entry: ArmEntry) -> bool:
    reset = getattr(entry.arm, "reset_stop_signal", None)
    if reset is None:
        print(f"[!] {entry.name}: reset_stop_signal() not available; skip recovery move")
        return False

    reset()
    print(f"[OK] {entry.name}: reset_stop_signal()")
    return True


def main() -> None:
    if LEFT_DEVICE == RIGHT_DEVICE:
        raise ValueError("LEFT_DEVICE and RIGHT_DEVICE must be different serial ports")

    entries: list[ArmEntry] = []

    try:
        entries.append(make_arm("left", LEFT_DEVICE, LEFT_MODEL))
        entries.append(make_arm("right", RIGHT_DEVICE, RIGHT_MODEL))

        for entry in entries:
            entry.enabled = entry.arm.enable_motors()
            if entry.enabled:
                print(f"[OK] {entry.name}: enable_motors() ({entry.cfg.device}, {entry.cfg.robot_model})")
            else:
                print(f"[!] {entry.name}: enable_motors() failed ({entry.cfg.device}, {entry.cfg.robot_model})")

        if not all(entry.enabled for entry in entries):
            print("[!] At least one arm failed to enable; skip movej/estop test.")
            return

        time.sleep(2.0)

        move_targets = {
            "left": make_joint_target(entries[0].cfg, -MOVE_TARGET_RAD),
            "right": make_joint_target(entries[1].cfg, MOVE_TARGET_RAD),
        }
        estop_targets = {
            "left": make_joint_target(entries[0].cfg, -ESTOP_TARGET_RAD),
            "right": make_joint_target(entries[1].cfg, ESTOP_TARGET_RAD),
        }

        run_parallel_restore("restore_arm() -> zero", entries)
        time.sleep(0.5)
        run_parallel_movej("movej(mirrored target)", entries, move_targets, MOVE_SPEED)
        time.sleep(0.5)
        run_parallel_restore("restore_arm() -> zero", entries)
        time.sleep(0.5)

        print("\n=== parallel movej + emergency stop ===")
        estop_result: dict[str, object] = {}
        workers = [
            threading.Thread(
                target=_movej_worker,
                name=f"{entry.name}-estop-movej",
                args=(entry, estop_targets[entry.name], ESTOP_SPEED, estop_result),
            )
            for entry in entries
        ]

        for worker in workers:
            worker.start()

        time.sleep(STOP_AFTER_S)
        for entry in entries:
            ret = entry.arm.cancel_trajectory()
            print(f"[!] {entry.name}: cancel_trajectory() after {STOP_AFTER_S}s, ret={ret}")

        for worker in workers:
            worker.join()

        for entry in entries:
            ret = estop_result.get(entry.name)
            if ret == MOVE_INTERRUPTED:
                print(f"[OK] {entry.name}: movej interrupted, ret={ret}")
            elif isinstance(ret, BaseException):
                print(f"[!] {entry.name}: movej raised {ret!r}")
            else:
                print(f"[!] {entry.name}: movej returned {ret}, expected {MOVE_INTERRUPTED} (INTERRUPTED)")

        reset_ok = [reset_stop_signal(entry) for entry in entries]
        if all(reset_ok):
            run_parallel_restore("restore_arm() -> zero after estop reset", entries)
    finally:
        for entry in entries:
            if entry.enabled:
                entry.arm.disable_motors()
                print(f"[OK] {entry.name}: disable_motors()")


if __name__ == "__main__":
    main()
