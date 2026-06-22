"""dual_arm_drag_teaching_demo.py — OneroArm Python：双臂拖动示教（无 ROS）

左右臂各创建一个 OneroDragTeaching 实例，分别绑定不同串口。录制和回放命令
通过 OneroDragTeaching.handle_command_dual() 下发到 SDK 侧双臂同步路径。

命令：
  0 = 停止当前录制/回放
  1 = 开始双臂零力拖动录制
  2 = 停止录制并写入双臂轨迹清单
  3 = 回放当前轨迹对
  4 = 选择历史轨迹对回放
  5 = 退出

录制文件落在 ./trajectory_log/dual_arm/：
  drag_record_dual_<YYYYmmdd_HHMMSS>_left.dat
  drag_record_dual_<YYYYmmdd_HHMMSS>_right.dat
  drag_record_dual_<YYYYmmdd_HHMMSS>_index.dat

注意：
  - OneroDragTeaching.set_hardware() 自行打开串口，不需要再实例化 OneroArm。
  - 当前 demo 与单臂 drag_teaching_demo.py 一样，用后台线程按 100Hz 调用
    timer_callback，主线程读 stdin 调 handle_command_dual，未额外加锁。
  - 每次启动脚本生成一组新的录制文件；如需录多组轨迹，建议退出后重启脚本。
"""
from __future__ import annotations

from dataclasses import dataclass
import datetime
from pathlib import Path
import threading
import time

import oneroarm

# === 配置 ================================================================
LEFT_DEVICE = "/dev/ttyACM0"
RIGHT_DEVICE = "/dev/ttyACM1"
LEFT_MODEL = "a1_l"
RIGHT_MODEL = "a1_r"
MOUNT_ORIENTATION = "vertical"
LEFT_URDF_PATH = ""
RIGHT_URDF_PATH = ""
DOF = 7
TIME_STEP_S = 0.01          # 100 Hz
LOG_DIR = Path("./trajectory_log/dual_arm")
# =======================================================================

MANIFEST_HEADER = "ONERO_DUAL_TRAJ 1"


@dataclass
class ArmCtx:
    side: str
    device: str
    robot_model: str
    urdf_path: str
    record_file: Path
    dt: "oneroarm.OneroDragTeaching"


@dataclass(frozen=True)
class TrajectoryPair:
    timestamp: str
    left: Path
    right: Path


def make_timestamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def dual_data_path(timestamp: str, side: str) -> Path:
    return LOG_DIR / f"drag_record_dual_{timestamp}_{side}.dat"


def dual_manifest_path(timestamp: str) -> Path:
    return LOG_DIR / f"drag_record_dual_{timestamp}_index.dat"


def make_arm(
    side: str,
    device: str,
    robot_model: str,
    urdf_path: str,
    record_file: Path,
) -> ArmCtx:
    dt = oneroarm.OneroDragTeaching()
    return ArmCtx(
        side=side,
        device=device,
        robot_model=robot_model,
        urdf_path=urdf_path,
        record_file=record_file,
        dt=dt,
    )


def init_arm(arm: ArmCtx) -> bool:
    if not arm.dt.initialize(DOF, str(arm.record_file), TIME_STEP_S):
        print(f"[X] {arm.side}: OneroDragTeaching.initialize failed")
        return False
    if not arm.dt.set_hardware(
        arm.device,
        arm.urdf_path,
        arm.robot_model,
        MOUNT_ORIENTATION,
    ):
        print(
            f"[X] {arm.side}: set_hardware failed "
            f"(device={arm.device}, model={arm.robot_model})"
        )
        return False
    print(
        f"[OK] {arm.side}: ready "
        f"(device={arm.device}, model={arm.robot_model}, "
        f"record={arm.record_file.name})"
    )
    return True


def handle_command_dual(left: ArmCtx, right: ArmCtx, cmd: int) -> int:
    handler = getattr(oneroarm.OneroDragTeaching, "handle_command_dual", None)
    if handler is None:
        raise RuntimeError(
            "当前 oneroarm 包未暴露 OneroDragTeaching.handle_command_dual(); "
            "请安装包含双臂拖动示教接口的新版本 Python 包。"
        )
    return handler(left.dt, right.dt, cmd)


def write_dual_manifest(timestamp: str, left: ArmCtx, right: ArmCtx) -> bool:
    if not left.record_file.is_file() or not right.record_file.is_file():
        return False

    manifest_path = dual_manifest_path(timestamp)
    with manifest_path.open("w", encoding="utf-8") as out:
        out.write(f"{MANIFEST_HEADER}\n")
        out.write(f"timestamp={timestamp}\n")
        out.write(f"left={left.record_file.name}\n")
        out.write(f"right={right.record_file.name}\n")
    return True


def read_dual_manifest(manifest_path: Path) -> TrajectoryPair | None:
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    if not lines or lines[0] != MANIFEST_HEADER:
        return None

    values: dict[str, str] = {}
    for line in lines[1:]:
        key, sep, value = line.partition("=")
        if sep:
            values[key] = value

    timestamp = values.get("timestamp", "")
    if not timestamp:
        stem = manifest_path.stem
        prefix = "drag_record_dual_"
        suffix = "_index"
        if stem.startswith(prefix) and stem.endswith(suffix):
            timestamp = stem[len(prefix):-len(suffix)]

    left_name = values.get("left", "")
    right_name = values.get("right", "")
    if not timestamp or not left_name or not right_name:
        return None

    left_path = manifest_path.parent / left_name
    right_path = manifest_path.parent / right_name
    if not left_path.is_file() or not right_path.is_file():
        return None
    return TrajectoryPair(timestamp=timestamp, left=left_path, right=right_path)


def list_trajectory_pairs() -> list[TrajectoryPair]:
    if not LOG_DIR.is_dir():
        return []

    pairs: list[TrajectoryPair] = []
    for path in LOG_DIR.iterdir():
        if not path.is_file():
            continue
        if path.suffix != ".dat":
            continue
        if not path.stem.startswith("drag_record_dual_"):
            continue
        if not path.stem.endswith("_index"):
            continue
        pair = read_dual_manifest(path)
        if pair is not None:
            pairs.append(pair)

    pairs.sort(key=lambda pair: pair.timestamp, reverse=True)
    return pairs


def print_menu() -> None:
    print("\n>>> 命令: 0=停止 1=开始录制 2=停止录制 3=回放当前 4=回放历史 5=退出")
    print(">>> ", end="", flush=True)


def select_and_replay(left: ArmCtx, right: ArmCtx) -> str | None:
    pairs = list_trajectory_pairs()
    if not pairs:
        print(f"[X] 未找到双臂轨迹对 ({LOG_DIR})，先用命令 1/2 录一段再回放。")
        return None

    print(f"找到 {len(pairs)} 组双臂轨迹:")
    for i, pair in enumerate(pairs, 1):
        print(f"  [{i}] {pair.timestamp}")

    line = input(f"输入编号 (1-{len(pairs)})，0 取消: ").strip()
    try:
        idx = int(line)
    except ValueError:
        print("已取消")
        return None
    if idx < 1 or idx > len(pairs):
        print("已取消")
        return None

    pair = pairs[idx - 1]
    left.dt.set_replay_file(str(pair.left))
    right.dt.set_replay_file(str(pair.right))

    rc = handle_command_dual(left, right, 3)
    tag = "[OK]" if rc == 0 else "[X]"
    print(f"{tag} 回放历史轨迹对: {pair.timestamp} ret={rc}")
    return pair.timestamp if rc == 0 else None


def start_tick_thread(left: ArmCtx, right: ArmCtx) -> tuple[threading.Event, threading.Thread]:
    running = threading.Event()
    running.set()

    def tick_loop() -> None:
        next_t = time.monotonic()
        while running.is_set():
            left.dt.timer_callback()
            right.dt.timer_callback()
            next_t += TIME_STEP_S
            sleep = next_t - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_t = time.monotonic()

    thread = threading.Thread(target=tick_loop, name="dual-drag-tick", daemon=True)
    thread.start()
    return running, thread


def main() -> None:
    if LEFT_DEVICE == RIGHT_DEVICE:
        raise ValueError("LEFT_DEVICE and RIGHT_DEVICE must be different serial ports")

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = make_timestamp()
    manifest_path = dual_manifest_path(timestamp)

    left = make_arm(
        side="left",
        device=LEFT_DEVICE,
        robot_model=LEFT_MODEL,
        urdf_path=LEFT_URDF_PATH,
        record_file=dual_data_path(timestamp, "left"),
    )
    right = make_arm(
        side="right",
        device=RIGHT_DEVICE,
        robot_model=RIGHT_MODEL,
        urdf_path=RIGHT_URDF_PATH,
        record_file=dual_data_path(timestamp, "right"),
    )

    if not init_arm(left) or not init_arm(right):
        print("[X] 双臂拖动示教初始化失败")
        return

    print(f"[OK] 双臂拖动示教 ready. pair={timestamp}")
    print(f"[OK] left_record ={left.record_file}")
    print(f"[OK] right_record={right.record_file}")

    running, tick_thread = start_tick_thread(left, right)
    active_replay_label = timestamp

    try:
        print_menu()
        for line in iter(input, ""):
            line = line.strip()
            try:
                cmd = int(line)
            except ValueError:
                print(f"[X] 无效命令: {line!r}")
                print_menu()
                continue

            if cmd == 5:
                break
            if cmd == 4:
                selected = select_and_replay(left, right)
                if selected is not None:
                    active_replay_label = selected
                print_menu()
                continue
            if cmd < 0 or cmd > 3:
                print(f"[X] 无效命令: {cmd}")
                print_menu()
                continue

            rc = handle_command_dual(left, right, cmd)
            tag = "[OK]" if rc == 0 else "[X]"
            print(f"{tag} handle_command_dual({cmd}) ret={rc}")

            if cmd == 1 and rc == 0:
                print("[OK] 双臂零力拖动录制已开始，拖动两只机械臂完成示教。")
            elif cmd == 2 and rc == 0:
                manifest_ok = write_dual_manifest(timestamp, left, right)
                if manifest_ok:
                    print(f"[OK] 双臂轨迹清单已写入: {manifest_path}")
                    active_replay_label = timestamp
                else:
                    print("[!] 未写入清单：左右轨迹文件尚未同时生成。")
            elif cmd == 3 and rc == 0:
                print(f"[OK] 回放当前轨迹对: {active_replay_label}")

            print_menu()
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        try:
            handle_command_dual(left, right, 0)
        except Exception as exc:
            print(f"[!] 退出时停止双臂失败: {exc}")
        running.clear()
        tick_thread.join()
        print("[OK] 退出")


if __name__ == "__main__":
    main()
