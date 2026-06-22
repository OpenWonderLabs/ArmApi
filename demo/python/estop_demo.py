"""estop_demo.py — OneroArm Python：运动中急停（emergency stop）最小演示

演示"急停接口"：运动执行中从另一线程触发 cancel_trajectory()，让正在跑的
movej 立刻中断返回；之后必须 reset_stop_signal() 重新解除急停，后续命令才会执行。

  cancel_trajectory()   触发急停：置内部 stop 标志，使在跑的 movej/movel/
                        send_trajectory 在下一拍检测到后立刻返回 INTERRUPTED(-6)。
  reset_stop_signal()   解除急停：清掉 stop 标志。★ 新版不会在每条命令入口自动清，
                        所以急停后若不调用本接口，下一条 movej 会立刻又返回 -6。

序列：
  enable → restore_arm()(基线归零)
  [完整]  movej(target, 慢速) 跑完 → movej(zero)            # 先演示一遍完整运动
  [急停]  线程跑 movej(target, 慢速)；主线程 1s 后 cancel_trajectory()
          → movej 返回 -6(INTERRUPTED)
          → reset_stop_signal() 解除
          → movej(zero) 证明已恢复
  → disable

────────────────────────────────────────────────────────────────────────
★★ 运行前置条件（当前发布的 oneroarm 模块尚不满足，需先更新 pybind 绑定再重编）：
  1. 暴露 OneroArm.reset_stop_signal() -> None。
  2. movej 绑定必须在执行期间释放 GIL（py::gil_scoped_release）。否则跑 movej
     的工作线程会一直占着 GIL，主线程的 cancel_trajectory() 根本拿不到 GIL 去执行，
     急停不会生效。cancel_trajectory() 本身已暴露，无需新增。
────────────────────────────────────────────────────────────────────────
"""
import threading
import time
import oneroarm

# === 运动参数 ============================
JOINT_INDEX  = 3        # 0-based: joint4
TARGET_RAD   = 1.0      # joint4 目标角（在 a1_r 限位内）
ESTOP_SPEED  = 0.6      # 慢速，留出中途急停的时间窗（越小越慢）
STOP_AFTER_S = 2.0      # movej 启动后多久触发急停
# =========================================

# 与 onero_define.h::MoveResult 对齐（模块未导出枚举，这里按值解释）
MOVE_OK          = 0
MOVE_INTERRUPTED = -6


def build_config() -> oneroarm.OneroConfig:
    cfg = oneroarm.OneroConfig()
    cfg.device = "/dev/ttyACM0"
    cfg.robot_model = "a1_l"
    cfg.version = "A1"
    cfg.mount_orientation = "vertical"
    return cfg


def checked(name: str, ret: int) -> None:
    if ret != 0:
        raise RuntimeError(f"{name} failed, ret={ret}")
    print(f"[OK] {name}")


def main() -> None:
    cfg = build_config()
    arm = oneroarm.OneroArm(cfg)

    enabled = arm.enable_motors()
    if not enabled:
        print("[!] enable_motors failed (无硬件预期；急停逻辑需真机才能完整演示)")
    time.sleep(1.0)

    zero = [0.0] * cfg.dof
    target = list(zero)
    target[JOINT_INDEX] = TARGET_RAD

    try:
        # 基线：先显式归零（新版 enable 不再自动归零）
        checked("restore_arm() -> zero", arm.restore_arm())
        time.sleep(1.0)

        # ───── 第一遍：完整跑完，不急停 ─────
        print("\n=== [1/2] 完整运动（不急停）===")
        checked(f"movej(joint4={TARGET_RAD}) 完整", arm.movej(target, speed_scale=ESTOP_SPEED))
        time.sleep(0.5)
        checked("movej(zero) 回零", arm.movej(zero, speed_scale=ESTOP_SPEED))
        time.sleep(0.5)

        # ───── 第二遍：运动中途急停 ─────
        print("\n=== [2/2] 运动中途急停 ===")
        result = {"ret": None}

        def _run_movej() -> None:
            # 在工作线程里跑阻塞的 movej；主线程稍后急停。
            result["ret"] = arm.movej(target, speed_scale=ESTOP_SPEED)

        worker = threading.Thread(target=_run_movej, name="movej-worker")
        worker.start()

        time.sleep(STOP_AFTER_S)
        print(f"[!] 急停：cancel_trajectory()  (movej 启动 {STOP_AFTER_S}s 后触发)")
        arm.cancel_trajectory()
        worker.join()

        ret = result["ret"]
        if ret == MOVE_INTERRUPTED:
            print(f"[OK] movej 被急停中断，返回 {ret} (INTERRUPTED) —— 符合预期")
        else:
            print(f"[!] movej 返回 {ret}（预期 {MOVE_INTERRUPTED} INTERRUPTED；"
                  f"无硬件或 movej 未释放 GIL 时会看到其他值）")

        # ★ 急停后必须解除，否则下一条 movej 会立刻又返回 -6
        arm.reset_stop_signal()
        print("[OK] reset_stop_signal() 已解除急停")

        # 证明恢复：再次 movej 回零应能正常执行
        checked("movej(zero) 急停恢复后回零", arm.movej(zero, speed_scale=ESTOP_SPEED))
    finally:
        if enabled:
            arm.disable_motors()


if __name__ == "__main__":
    main()
