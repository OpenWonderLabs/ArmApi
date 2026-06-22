"""drag_teaching_demo.py — OneroArm Python：拖动示教（零力录制 + 回放）

演示 OneroDragTeaching 的核心 API：
  - initialize / set_hardware
  - timer_callback   ：控制循环 tick（demo 用后台线程按 100Hz 调用）
  - handle_command   ：0=Stop  1=StartRec  2=StopRec  3=Replay
  - set_replay_file  ：切换回放数据源

不含 ROS / 话题 / 参数；纯 stdin 命令循环 + 后台线程驱动控制循环。
录制文件落在 ./trajectory_log/drag_record_<YYYYmmdd_HHMMSS>.dat，
命令 4 会列出该目录下所有 .dat 供选择回放。

注意：
  - OneroDragTeaching.set_hardware() 自行打开串口，不需要再实例化 OneroArm。
  - 同一实例的方法不是线程安全的；demo 与 ROS 节点行为一致：tick 线程跑
    timer_callback，主线程读 stdin 调 handle_command，未额外加锁。
"""
import datetime
import os
import threading
import time

import oneroarm

# === 配置 ================================
DEVICE             = "/dev/ttyACM1"
ROBOT_MODEL        = "a1_r"
MOUNT_ORIENTATION  = "vertical"
DOF                = 7
TIME_STEP_S        = 0.01           # 100 Hz
LOG_DIR            = "./trajectory_log"
# =========================================


def make_record_file_path() -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(LOG_DIR, f"drag_record_{ts}.dat")


def list_trajectory_files() -> list[str]:
    if not os.path.isdir(LOG_DIR):
        return []
    files = [os.path.join(LOG_DIR, f)
             for f in os.listdir(LOG_DIR) if f.endswith(".dat")]
    files.sort(key=os.path.basename, reverse=True)
    return files


def print_menu() -> None:
    print("\n>>> 命令: 0=停止 1=开始录制 2=停止录制 3=回放当前 4=回放历史 5=退出")
    print(">>> ", end="", flush=True)


def select_and_replay(dt: "oneroarm.OneroDragTeaching") -> None:
    files = list_trajectory_files()
    if not files:
        print(f"[X] 未找到轨迹文件 ({LOG_DIR})，先用命令 1/2 录一段再回放。")
        return
    print(f"找到 {len(files)} 个轨迹文件:")
    for i, p in enumerate(files, 1):
        print(f"  [{i}] {os.path.basename(p)}")

    line = input(f"输入编号 (1-{len(files)})，0 取消: ").strip()
    try:
        idx = int(line)
    except ValueError:
        print("已取消")
        return
    if idx < 1 or idx > len(files):
        print("已取消")
        return
    dt.set_replay_file(files[idx - 1])
    rc = dt.handle_command(3)
    tag = "[OK]" if rc == 0 else "[X]"
    print(f"{tag} 回放: {os.path.basename(files[idx - 1])} ret={rc}")


def main() -> None:
    os.makedirs(LOG_DIR, exist_ok=True)
    record_file = make_record_file_path()

    dt = oneroarm.OneroDragTeaching()
    if not dt.initialize(DOF, record_file, TIME_STEP_S):
        print("[X] OneroDragTeaching.initialize failed")
        return
    if not dt.set_hardware(DEVICE, "", ROBOT_MODEL, MOUNT_ORIENTATION):
        print(f"[X] set_hardware failed (device={DEVICE}, model={ROBOT_MODEL})")
        return
    print(f"[OK] DragTeaching ready. record_file={record_file}")

    running = threading.Event()
    running.set()

    def tick_loop() -> None:
        next_t = time.monotonic()
        while running.is_set():
            dt.timer_callback()
            next_t += TIME_STEP_S
            sleep = next_t - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_t = time.monotonic()

    tick_thread = threading.Thread(target=tick_loop, daemon=True)
    tick_thread.start()

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
                select_and_replay(dt)
                print_menu()
                continue
            if cmd < 0 or cmd > 3:
                print(f"[X] 无效命令: {cmd}")
                print_menu()
                continue
            rc = dt.handle_command(cmd)
            tag = "[OK]" if rc == 0 else "[X]"
            print(f"{tag} handle_command({cmd}) ret={rc}")
            print_menu()
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        running.clear()
        tick_thread.join()
        print("[OK] 退出")


if __name__ == "__main__":
    main()
