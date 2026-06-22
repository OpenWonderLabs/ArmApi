"""buffered_traj_demo.py — OneroArm Python：trajectory_connect 缓冲轨迹示例

演示 movej / movep / movel 的最后一个参数 trajectory_connect：
  - trajectory_connect = 1 → 把当前段塞进内部 trajectory_buffer_，**不立即执行**；
  - 末尾调一次 execute_buffered_trajectory，把所有累积段串成一条
    平滑轨迹下发。

⚠ 注意：send_trajectory / send_trajectory_point 走的是另一条路径 ——
       直接给每个关节电机下发 MIT 力矩控制，**不做规划、不入此 buffer**。
       本 demo 不演示该接口。

序列：enable
     → restore_arm()                 # 显式归零；enable 不自动回零
     → movej(joint_target, 1.0, 1)   # 入 buffer：段 1
     → movep(pose_target,  1.0, 1)   # 入 buffer：段 2
     → movej(zero,         1.0, 1)   # 入 buffer：段 3
     → execute_buffered_trajectory   # 三段串成一条轨迹平滑执行
     → disable
"""
import time
import oneroarm

# === 关节空间目标（rad） ==================
JOINT_INDEX = 3        # 0-based: joint4
JOINT_VALUE_RAD = 0.3

# === 笛卡尔目标位姿（右臂可达） ===========
TARGET_X  =  -0.30
TARGET_Y  =  -0.30
TARGET_Z  =  0.30
TARGET_QW =  1.00
TARGET_QX =  0.00
TARGET_QY =  0.00
TARGET_QZ =  0.00
# =========================================


def build_config() -> oneroarm.OneroConfig:
    cfg = oneroarm.OneroConfig()
    cfg.device = "/dev/ttyACM0"
    cfg.robot_model = "a1_r"
    cfg.version = "A1"
    cfg.mount_orientation = "vertical"
    return cfg


def make_target() -> oneroarm.Pose:
    p = oneroarm.Pose()
    p.x, p.y, p.z = TARGET_X, TARGET_Y, TARGET_Z
    p.qw, p.qx, p.qy, p.qz = TARGET_QW, TARGET_QX, TARGET_QY, TARGET_QZ
    return p


def checked(name: str, ret: int) -> None:
    if ret != 0:
        raise RuntimeError(f"{name} failed, ret={ret}")
    print(f"[OK] {name}")


def main() -> None:
    cfg = build_config()
    arm = oneroarm.OneroArm(cfg)

    enabled = arm.enable_motors()
    if not enabled:
        print("[!] enable_motors failed (无硬件预期)")
    time.sleep(1.0)

    zero = [0.0] * cfg.dof
    joint_target = list(zero)
    joint_target[JOINT_INDEX] = JOINT_VALUE_RAD
    pose_target = make_target()

    try:
        # 显式归零；新版 enable_motors() 不再自动回零。
        checked("restore_arm() -> zero", arm.restore_arm())
        time.sleep(1.0)

        # 三段累积入 trajectory_buffer_，此时不会运动
        checked("movej(joint4=0.3, tc=1)",
                arm.movej(joint_target, speed_scale=1.0, trajectory_connect=1))
        checked("movep(target,    tc=1)",
                arm.movep(pose_target, speed_scale=1.0, trajectory_connect=1))
        checked("movej(zero,      tc=1)",
                arm.movej(zero, speed_scale=1.0, trajectory_connect=1))

        # 串成一条平滑轨迹一次性下发
        checked("execute_buffered_trajectory",
                arm.execute_buffered_trajectory())
    finally:
        if enabled:
            arm.disable_motors()


if __name__ == "__main__":
    main()
