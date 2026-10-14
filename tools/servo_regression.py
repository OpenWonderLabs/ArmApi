#!/usr/bin/env python3
"""Offline consumer regression; always uses simulation and a nonexistent device."""
import argparse
import importlib
import json
import math
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

PERIOD = 0.01
TIMEOUT = 20.0
JOINT_TOLERANCE = 1e-4
POSITION_TOLERANCE = 2e-4
SEED = [-0.158, 1.0, 1.2, -0.8, 0.1, 0.8, -1.0]
SDK_MAX_ACCELERATION = 0.2
SDK_MAX_JERK = 1.0 / 15.0


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def expect_rc(rc, message, expected=0):
    require(rc == expected, f"{message}: rc={rc}, expected={expected}")


def joint_error(a, b):
    require(len(a) == len(b) == 7 and all(math.isfinite(x) for x in [*a, *b]),
            f"invalid joint feedback: {a}, target: {b}")
    return max(abs(x - y) for x, y in zip(a, b))


def pose_values(pose):
    return [getattr(pose, name) for name in ("x", "y", "z", "qw", "qx", "qy", "qz")]


def pose_error(a, b):
    require(all(math.isfinite(x) for x in pose_values(a) + pose_values(b)), "nonfinite pose")
    distance = math.sqrt(sum((getattr(a, n) - getattr(b, n)) ** 2 for n in ("x", "y", "z")))
    qa, qb = pose_values(a)[3:], pose_values(b)[3:]
    norm = math.sqrt(sum(x*x for x in qa) * sum(x*x for x in qb))
    require(norm > 1e-9, "invalid quaternion")
    angle = 2 * math.acos(min(1.0, abs(sum(x*y for x, y in zip(qa, qb))) / norm))
    return distance, angle


def joint_applied(status, before, target, feedback, holding_state):
    return (status.applied_sequence > before.accepted_sequence
            and status.sent_frame_count >= before.sent_frame_count + 5
            and status.otg_update_count >= before.otg_update_count + 5
            and status.state == holding_state and status.last_error == 0
            and joint_error(status.commanded_q, target) < JOINT_TOLERANCE
            and joint_error(feedback, target) < JOINT_TOLERANCE)


def snapshot(arm, kind):
    status = getattr(arm, f"get_{kind}_status")()
    fields = ("state", "accepted_sequence", "applied_sequence", "sent_frame_count",
              "otg_update_count", "command_age_s", "limit_flags", "last_error",
              "commanded_q", "commanded_dq", "commanded_ddq")
    result = {name: getattr(status, name) for name in fields if hasattr(status, name)}
    result["state"] = int(result["state"])
    result["feedback"] = list(arm.get_arm_state_from_motor().positions)
    if kind == "servop":
        result["actual_pose"] = pose_values(status.actual_pose)
        result["target_pose"] = pose_values(status.target_pose)
    return result


def wait_for(label, arm, kind, check, update=None, timeout=TIMEOUT):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if update is not None:
            rc = update()
            require(rc == 0, f"{label}: update rc={rc}; {snapshot(arm, kind)}")
        status = getattr(arm, f"get_{kind}_status")()
        require(status.state.name != "FAULT", f"{label}: FAULT; {snapshot(arm, kind)}")
        if check(status):
            print(json.dumps({"check": label, "result": "passed", **snapshot(arm, kind)}), flush=True)
            return status
        time.sleep(PERIOD)
    raise AssertionError(f"{label}: timeout={timeout}s; {snapshot(arm, kind)}")


def moving_stop_case(oa, arm, custom=False, streaming=False):
    """ISSUE-01/02: stop while moving, before expiration or target arrival."""
    zero = [0.0] * 7
    expect_rc(arm.control_mit(zero, zero, SEED, zero, zero), "moving-stop seed")
    limits = oa.JointServoLimits()
    if custom:
        limits.max_velocity = [0.35] * 7
        limits.max_acceleration = [0.15] * 7
        limits.max_jerk = [0.04] * 7
    expect_rc(arm.start_servoj(limits), "moving-stop start")
    target = SEED.copy(); target[0] += -0.1 if custom else 0.1
    validity = 0.5 if streaming else 5.0
    expect_rc(arm.servoj(target, valid_for_seconds=validity), "moving-stop target")
    deadline = time.monotonic() + 1.3
    while time.monotonic() < deadline:
        if streaming:
            expect_rc(arm.servoj(target, valid_for_seconds=validity), "streaming update")
        time.sleep(PERIOD)
    before = arm.get_servoj_status()
    require(before.state == oa.ServoJState.RUNNING and abs(before.commanded_dq[0]) > 0.01,
            f"stop test did not enter obvious motion: {snapshot(arm, 'servoj')}")

    # Generic cancellation must refuse an active ServoJ session and leave it
    # tracking, instead of reporting success for an unsupported stop request.
    position_before = arm.get_joint_positions()[0]
    expect_rc(arm.cancel_trajectory(), "generic cancel during ServoJ", -8)
    time.sleep(0.1)
    after_cancel = arm.get_servoj_status()
    require(after_cancel.state == oa.ServoJState.RUNNING
            and after_cancel.last_error == 0
            and after_cancel.accepted_sequence == before.accepted_sequence
            and abs(arm.get_joint_positions()[0] - position_before) > 0.0005,
            f"cancel unexpectedly disturbed ServoJ: {snapshot(arm, 'servoj')}")
    if streaming:
        expect_rc(arm.servoj(target, valid_for_seconds=0.5), "fresh target after refused cancel")
    before = arm.get_servoj_status()
    acceleration_limit = min(limits.max_acceleration[0], SDK_MAX_ACCELERATION) if custom else SDK_MAX_ACCELERATION
    jerk_limit = min(limits.max_jerk[0], SDK_MAX_JERK) if custom else SDK_MAX_JERK
    # Conservative triangular/trapezoidal jerk-stop bound plus one second of
    # scheduling allowance. This is a test bound, not an extra SDK motion cap.
    bound = max(abs(a) / jerk_limit
                + 2 * math.sqrt(abs(v) / jerk_limit + a*a / (2 * jerk_limit**2))
                + abs(v) / acceleration_limit
                for v, a in zip(before.commanded_dq, before.commanded_ddq)) + 1.0
    result = {}
    started = time.monotonic()
    def stop():
        try:
            result["rc"] = arm.stop_servoj()
        except BaseException as exc:
            result["exception"] = repr(exc)
        finally:
            result["elapsed_s"] = time.monotonic() - started
    thread = threading.Thread(target=stop, daemon=True)
    thread.start()
    samples = []
    while thread.is_alive() and time.monotonic() - started < bound:
        s = arm.get_servoj_status()
        samples.append({"t": time.monotonic() - started, "state": s.state.name,
                        "q": list(s.commanded_q), "dq": list(s.commanded_dq),
                        "ddq": list(s.commanded_ddq), "frames": s.sent_frame_count})
        require(s.state != oa.ServoJState.FAULT, f"braking fault: {snapshot(arm, 'servoj')}")
        time.sleep(PERIOD / 2)
    require(not thread.is_alive(), f"moving stop exceeded {bound:.3f}s; {snapshot(arm, 'servoj')}")
    thread.join()
    expect_rc(result.get("rc"), f"moving stop failed: {result}")
    final = arm.get_servoj_status()
    require(final.state == oa.ServoJState.IDLE and final.last_error == 0
            and all(v == 0.0 for v in final.commanded_dq)
            and all(v == 0.0 for v in final.commanded_ddq), "moving stop did not reach IDLE/exact rest")
    samples.append({"t": result["elapsed_s"], "state": final.state.name,
                    "q": list(final.commanded_q), "dq": list(final.commanded_dq),
                    "ddq": list(final.commanded_ddq), "frames": final.sent_frame_count})
    require(any(s["state"] == "BRAKING" for s in samples), "controlled BRAKING was not observed")
    require(result["elapsed_s"] <= bound, f"stop elapsed exceeds bound: {result}")
    signs = [1 if s["dq"][0] > 1e-4 else -1 for s in samples if abs(s["dq"][0]) > 1e-4]
    reversals = sum(left != right for left, right in zip(signs, signs[1:]))
    require(reversals == 0, f"braking reversed velocity {reversals} times")
    previous = {"ddq": list(before.commanded_ddq), "dq": list(before.commanded_dq),
                "frames": before.sent_frame_count}
    for sample in samples:
        velocity_limit = limits.max_velocity[0] if custom else 1.0
        require(max(map(abs, sample["dq"])) <= velocity_limit + 1e-6,
                "braking velocity exceeded effective limit")
        ticks = sample["frames"] - previous["frames"]
        if ticks > 0:
            dt = ticks * PERIOD
            require(max(abs(a-b) for a,b in zip(sample["ddq"], previous["ddq"])) <= jerk_limit * dt + 1e-6,
                    "braking acceleration jump exceeded jerk limit")
            require(max(abs(a-b) for a,b in zip(sample["dq"], previous["dq"])) <= acceleration_limit * dt + 1e-6,
                    "braking velocity jump exceeded acceleration limit")
            previous = sample
    expect_rc(arm.servoj(target), "update after moving stop", -8)
    expect_rc(arm.cancel_trajectory(), "generic cancel without active ServoJ")
    arm.reset_stop_signal()
    expect_rc(arm.control_mit(zero, zero, SEED, zero, zero), "arm lease released after moving stop")
    expect_rc(arm.start_servoj(limits), "session restart after moving stop")
    expect_rc(arm.stop_servoj(), "resting session stop")
    print(json.dumps({"check": "ServoJ moving stop and refused generic cancel", "result": "passed",
                      "limits": "custom" if custom else "default", "streaming": streaming,
                      "elapsed_s": result["elapsed_s"], "time_bound_s": bound,
                      "final_state": final.state.name, "final_error": final.last_error,
                      "velocity_sign_reversals": reversals, "before_velocity": before.commanded_dq,
                      "before_acceleration": before.commanded_ddq, "samples": samples}), flush=True)


def moving_retarget_case(oa, arm, custom=False, mode="forward"):
    zero = [0.0] * 7
    expect_rc(arm.control_mit(zero, zero, SEED, zero, zero), "retarget seed")
    limits = oa.JointServoLimits()
    if custom:
        limits.max_velocity = [0.4] * 7
        limits.max_acceleration = [0.15] * 7
        limits.max_jerk = [0.04] * 7
    expect_rc(arm.start_servoj(limits), "retarget start")
    target = list(arm.get_joint_positions())
    target[0] += 0.1
    started = time.monotonic()
    while time.monotonic() - started < 1.3:
        expect_rc(arm.servoj(target, valid_for_seconds=0.5), "initial retarget stream")
        time.sleep(PERIOD)
    before = arm.get_servoj_status()
    require(before.state == oa.ServoJState.RUNNING and before.commanded_dq[0] > 0.01,
            "retarget must occur while moving")
    target[0] += 0.1 if mode != "reverse" else -0.15
    a_limit = 0.15 if custom else SDK_MAX_ACCELERATION
    j_limit = 0.04 if custom else SDK_MAX_JERK
    v_limit = 0.4 if custom else 1.0
    samples = []
    previous = before
    changed_at = time.monotonic()
    deadline = changed_at + 15.0
    peak = before.commanded_q[0]
    while time.monotonic() < deadline:
        if mode == "burst" and time.monotonic() - changed_at < 1.0:
            # Many admissible updates overwrite the same slot. The final one
            # is the desired target; no queue of intermediate points is built.
            for offset in (-0.02, 0.03, -0.01):
                interim = target.copy(); interim[0] += offset
                expect_rc(arm.servoj(interim, valid_for_seconds=0.5), "burst interim")
        expect_rc(arm.servoj(target, valid_for_seconds=0.5), "new target stream")
        accepted = arm.get_servoj_status().accepted_sequence
        invalid = target.copy(); invalid[0] = float("nan")
        expect_rc(arm.servoj(invalid), "invalid update during motion", -1)
        current = arm.get_servoj_status()
        require(current.accepted_sequence == accepted, "invalid update overwrote latest target")
        require(current.state != oa.ServoJState.FAULT and current.last_error == 0,
                f"retarget fault: {snapshot(arm, 'servoj')}")
        fatal = int(oa.ServoJLimitFlag.JOINT_POSITION) | int(oa.ServoJLimitFlag.OTG_INFEASIBLE) | int(oa.ServoJLimitFlag.COMMAND_TIMEOUT)
        require(not (current.limit_flags & fatal), "retarget limit/watchdog fault")
        ticks = current.sent_frame_count - previous.sent_frame_count
        if ticks > 0:
            dt = ticks * PERIOD
            require(max(map(abs, current.commanded_dq)) <= v_limit + 1e-6, "retarget velocity limit")
            require(max(map(abs, current.commanded_ddq)) <= a_limit + 1e-6, "retarget acceleration limit")
            require(max(abs(a-b) for a,b in zip(current.commanded_ddq, previous.commanded_ddq)) <= j_limit * dt + 1e-6,
                    "retarget acceleration discontinuity")
            require(max(abs(a-b) for a,b in zip(current.commanded_dq, previous.commanded_dq)) <= a_limit * dt + 1e-6,
                    "retarget velocity discontinuity")
            previous = current
        peak = max(peak, current.commanded_q[0])
        if mode == "forward":
            require(peak <= target[0] + JOINT_TOLERANCE, "feasible forward target overshot")
        samples.append({"t": time.monotonic() - changed_at, "q": current.commanded_q[0],
                        "dq": current.commanded_dq[0], "ddq": current.commanded_ddq[0],
                        "state": current.state.name, "frames": current.sent_frame_count})
        if (current.state == oa.ServoJState.HOLDING
                and joint_error(current.commanded_q, target) < JOINT_TOLERANCE
                and joint_error(arm.get_joint_positions(), target) < JOINT_TOLERANCE
                and max(map(abs, current.commanded_dq)) < 1e-8
                and max(map(abs, current.commanded_ddq)) < 1e-8):
            break
        time.sleep(PERIOD)
    else:
        raise AssertionError(f"new target did not converge: {snapshot(arm, 'servoj')}")
    # Refreshing identical data preserves the completed profile; sequence
    # increases, while replan count remains fixed and the arm stays at rest.
    replans = current.otg_replan_count
    for _ in range(20):
        expect_rc(arm.servoj(target, valid_for_seconds=0.5), "hold refresh")
        time.sleep(PERIOD)
    final = arm.get_servoj_status()
    require(final.otg_replan_count == replans, "same target refresh replanned")
    if mode != "burst":
        require(replans == before.otg_replan_count + 1, "identical streaming updates replanned")
    require(final.state == oa.ServoJState.HOLDING and joint_error(final.commanded_q, target) < JOINT_TOLERANCE,
            "latest target was not held")
    expect_rc(arm.stop_servoj(), "retarget stop")
    require(arm.get_servoj_status().state == oa.ServoJState.IDLE, "retarget cleanup IDLE")
    print(json.dumps({"check": "ServoJ moving retarget", "result": "passed",
                      "limits": "custom" if custom else "default", "mode": mode,
                      "target": target, "final_q": final.commanded_q,
                      "elapsed_s": time.monotonic() - changed_at, "time_bound_s": 15.0,
                      "position_error_rad": joint_error(final.commanded_q, target),
                      "peak_q0": peak, "replan_count": final.otg_replan_count,
                      "samples": samples}), flush=True)


def timeout_recovery_case(oa, arm, custom=False, phase="BRAKING"):
    samples = []
    limits = oa.JointServoLimits()
    v, a, j = (0.4, 0.15, 0.04) if custom else (1.0, 0.2, 1.0 / 15.0)
    if custom:
        limits.max_velocity, limits.max_acceleration, limits.max_jerk = [v]*7, [a]*7, [j]*7
    def observe():
        status = arm.get_servoj_status()
        s = {"state": status.state.name, "q": list(status.commanded_q),
             "dq": list(status.commanded_dq), "ddq": list(status.commanded_ddq),
             "frames": status.sent_frame_count, "limit_flags": status.limit_flags,
             "last_error": status.last_error, "accepted": status.accepted_sequence,
             "applied": status.applied_sequence, "replans": status.otg_replan_count,
             "age_s": status.command_age_s}
        s['t'] = time.monotonic() - started
        require(s['state'] != 'FAULT' and s['last_error'] == 0, f'fault: {s}')
        require(max(map(abs, s['dq'])) <= v+1e-6, f'velocity limit: {s}')
        require(max(map(abs, s['ddq'])) <= a+1e-6, f'acceleration limit: {s}')
        if samples and s['frames'] > samples[-1]['frames']:
            prev = samples[-1]
            dt = (s['frames']-prev['frames'])*PERIOD
            require(max(abs(x-y) for x,y in zip(s['ddq'],prev['ddq'])) <= j*dt+1e-6,
                    'acceleration continuity/jerk limit')
            require(max(abs(x-y) for x,y in zip(s['dq'],prev['dq'])) <= a*dt+1e-6,
                    'velocity continuity/acceleration limit')
            require(max(abs(x-y) for x,y in zip(s['q'],prev['q'])) <= v*dt+1e-6,
                    'position continuity/velocity limit')
        samples.append(s)
        return s
    require(not arm.is_hardware_connected(), 'unexpected hardware connection')
    z = [0.0]*7
    expect_rc(arm.control_mit(z,z,SEED,z,z), 'seed')
    expect_rc(arm.start_servoj(limits), 'start')
    target = SEED.copy(); target[0] += 0.1
    started = time.monotonic()
    while time.monotonic()-started < 1.3:
        expect_rc(arm.servoj(target, valid_for_seconds=0.15), 'initial stream')
        s = observe()
        time.sleep(PERIOD)
    require(s['state']=='RUNNING' and abs(s['dq'][0])>0.01, 'not moving before expiry')
    deadline = time.monotonic()+10
    saw_braking = False
    while time.monotonic()<deadline:
        s = observe()
        saw_braking |= s['state']=='BRAKING'
        expired = bool(s['limit_flags'] & int(oa.ServoJLimitFlag.COMMAND_TIMEOUT))
        ready = s['state']==phase and expired
        if ready and (phase=='HOLDING' or abs(s['dq'][0])>0.01):
            break
        time.sleep(PERIOD/2)
    else:
        raise AssertionError(f'expiry did not enter requested phase {phase}')
    require(saw_braking, 'no timeout BRAKING observed')
    before = s
    # Reuse the initial target in mid-brake; change it after fully holding.
    # Both must cause brake-to-tracking transition without restarting the session.
    if phase=='HOLDING': target[0] += 0.1
    recovery_started = time.monotonic()
    seen_running = False
    while time.monotonic()-recovery_started < 15:
        expect_rc(arm.servoj(target, valid_for_seconds=0.5), 'resume target')
        s = observe()
        seen_running |= s['state']=='RUNNING'
        fatal = int(oa.ServoJLimitFlag.JOINT_POSITION) | int(oa.ServoJLimitFlag.OTG_INFEASIBLE) | int(oa.ServoJLimitFlag.FEEDBACK_STALE)
        require(not s['limit_flags'] & fatal, f'recovery fatal flag: {s}')
        if s['state']=='HOLDING' and joint_error(s['q'],target)<1e-4 and joint_error(arm.get_joint_positions(),target)<1e-4 and max(map(abs,s['dq']))<1e-8 and max(map(abs,s['ddq']))<1e-8:
            break
        time.sleep(PERIOD)
    else:
        raise AssertionError(f'recovery did not converge: {s}')
    require(seen_running and s['applied']>before['accepted'], 'fresh target not applied')
    elapsed = time.monotonic()-recovery_started
    expect_rc(arm.stop_servoj(), 'stop')
    require(arm.get_servoj_status().state==oa.ServoJState.IDLE, 'cleanup IDLE')
    record = {'check':'ServoJ timeout recovery','result':'passed','limits':'custom' if custom else 'default',
              'resume_phase':phase,'resume_same_target':phase=='BRAKING','before':before,'final':s,
              'target':target,'elapsed_s':elapsed,'time_bound_s':15,'position_error_rad':joint_error(s['q'],target),
              'hardware_connected':False,'samples':samples}
    print(json.dumps(record), flush=True)
    return record


def run(order="arm-first", smoke_only=False, moving_stop_only=False, moving_retarget_only=False, arm_only=False, timeout_recovery_only=False):
    if order == "gripper-first" and not arm_only:
        gripper_module = importlib.import_module("onerogripper")
    oa = importlib.import_module("oneroarm")
    if not smoke_only and not arm_only and order == "arm-first":
        gripper_module = importlib.import_module("onerogripper")
    with tempfile.TemporaryDirectory(prefix="onero-offline-") as temp:
        device = Path(temp) / "nonexistent-device"
        require(not device.exists(), "test device must not exist")
        if not smoke_only and not arm_only:
            schemas = {
                "GripperStatus": ("position", "velocity", "force", "error", "valid"),
                "GripperTactileValue": ("point_id", "fx", "fy", "fz", "valid"),
                "GripperTactileSensorStatus": ("sensor_id", "total_force", "points", "valid"),
                "GripperTactileStatus": ("sensors", "valid"),
            }
            for name, fields in schemas.items():
                left, right = getattr(oa, name), getattr(gripper_module, name)
                require(left is not right, f"unisolated type {name}")
                require(all(hasattr(t, field) for t in (left, right) for field in fields), name)
            gripper = gripper_module.OneroGripper(str(device))
            require(not gripper.valid() and not gripper.status().valid, "unexpected gripper device")
            tactile = gripper.get_tactile()
            require(isinstance(tactile.sensors[0].total_force, gripper_module.GripperTactileValue),
                    "incorrect nested gripper type")
        config = oa.OneroConfig()
        config.device = str(device)
        config.robot_model, config.version, config.dof = "a1_l", "A1", 7
        config.mount_orientation = "vertical"
        config.simulation_mode = True
        arm = oa.OneroArm(config)
        try:
            require(not arm.is_hardware_connected(), "simulation must not connect hardware")
            require(arm.enable_motors(), "enable failed")
            zero = [0.0] * 7
            expect_rc(arm.control_mit(zero, zero, SEED, zero, zero), "simulation seed failed", 0)
            require(joint_error(arm.get_joint_positions(), SEED) < JOINT_TOLERANCE, "seed feedback")
            pose = arm.get_end_effector_pose()
            require(all(math.isfinite(v) for v in pose_values(pose)), "default model/FK")
            gravity = arm.compute_gravity_torque(SEED)
            require(len(gravity) == 7 and all(math.isfinite(v) for v in gravity), "gravity result")
            for api in ("movec", "start_servoj", "servoj", "get_servoj_status", "stop_servoj",
                        "start_servop", "servop", "get_servop_status", "stop_servop", "transform_pose"):
                require(hasattr(oa if api == "transform_pose" else arm, api), f"missing API {api}")
            if timeout_recovery_only:
                for custom in (False, True):
                    for phase in ("BRAKING", "HOLDING"):
                        timeout_recovery_case(oa, arm, custom, phase)
                return
            if moving_retarget_only:
                for custom in (False, True):
                    for mode in ("forward", "reverse", "burst"):
                        moving_retarget_case(oa, arm, custom, mode)
                return
            if moving_stop_only:
                for custom in (False, True):
                    for streaming in (False, True):
                        moving_stop_case(oa, arm, custom, streaming)
                return
            if smoke_only:
                print("Conda arm import/default model/key API smoke passed; full servo checks not run")
                return

            movej_target = SEED.copy(); movej_target[0] += 0.001
            rc = arm.movej(movej_target, 0.3)
            require(rc == 0 and joint_error(arm.get_joint_positions(), movej_target) < JOINT_TOLERANCE,
                    f"MoveJ execution/feedback failed rc={rc}")
            limits = oa.JointServoLimits()
            limits.max_velocity = [0.4] * 7
            limits.max_acceleration = [0.25] * 7
            limits.max_jerk = [0.1] * 7
            target = SEED.copy()
            target[0] += 0.02
            expect_rc(arm.start_servoj(limits), "start_servoj failed", 0)
            before = arm.get_servoj_status()
            expect_rc(arm.movej(target, 0.2), "MoveJ must be BUSY during ServoJ", -8)
            expect_rc(arm.start_servop(), "ServoP must be BUSY during ServoJ", -8)
            for bad in (float("nan"), float("inf"), -float("inf")):
                q = target.copy(); q[0] = bad
                expect_rc(arm.servoj(q), f"nonfinite target was accepted: {bad}", -1)
                dq = zero.copy(); dq[0] = bad
                expect_rc(arm.servoj(target, dq), f"nonfinite velocity was accepted: {bad}", -1)
            for q in (target[:-1], target + [0.0], []):
                expect_rc(arm.servoj(q), "wrong target length was accepted", -1)
            expect_rc(arm.servoj(target, zero[:-1]), "wrong velocity length was accepted", -1)
            for validity in (0, -0.1, 10.1, float("nan"), float("inf")):
                expect_rc(arm.servoj(target, valid_for_seconds=validity), f"invalid validity accepted: {validity}", -1)
            outside = target.copy(); outside[0] = 100.0
            expect_rc(arm.servoj(outside), "out-of-limit joint was accepted", -7)
            require(arm.get_servoj_status().accepted_sequence == before.accepted_sequence,
                    "rejected commands changed accepted sequence")
            def joint_arrived(s):
                return joint_applied(s, before, target, arm.get_joint_positions(), oa.ServoJState.HOLDING)
            wait_for("ServoJ different target applied and converged", arm, "servoj", joint_arrived,
                     lambda: arm.servoj(target, valid_for_seconds=0.5))

            # Start a second motion, then stop refreshing. Poll through timeout/braking.
            expiry_target = target.copy(); expiry_target[0] += 0.05
            wait_for("ServoJ moving before expiry", arm, "servoj",
                     lambda s: len(s.commanded_dq) == 7 and max(map(abs, s.commanded_dq)) > 1e-4,
                     lambda: arm.servoj(expiry_target, valid_for_seconds=0.15))
            expired = wait_for("ServoJ expiry -> controlled hold", arm, "servoj",
                              lambda s: s.state == oa.ServoJState.HOLDING
                              and bool(s.limit_flags & int(oa.ServoJLimitFlag.COMMAND_TIMEOUT))
                              and s.last_error == 0 and max(map(abs, s.commanded_dq)) < 1e-4)
            require(expired.command_age_s >= 0.15, "expired before command validity")
            require(not (expired.limit_flags & (int(oa.ServoJLimitFlag.OTG_INFEASIBLE)
                                               | int(oa.ServoJLimitFlag.FEEDBACK_STALE))),
                    f"uncontrolled expiry: {snapshot(arm, 'servoj')}")
            expect_rc(arm.stop_servoj(), "stop_servoj failed", 0)
            require(arm.get_servoj_status().state == oa.ServoJState.IDLE, "ServoJ stop state")
            expect_rc(arm.servoj(target), "ServoJ update after stop must be BUSY", -8)

            # Active ServoJ refuses generic cancellation with BUSY(-8).
            # The subprocess checks this while moving; use stop_servoj().
            expect_rc(arm.start_servoj(limits), "restart before disable", 0)
            current = arm.get_joint_positions()
            expect_rc(arm.servoj(current, valid_for_seconds=0.5), "restart update", 0)
            require(arm.disable_motors(), "disable_motors failed")
            wait_for("ServoJ disable_motors settled", arm, "servoj",
                     lambda s: s.state in (oa.ServoJState.IDLE, oa.ServoJState.HOLDING))
            expect_rc(arm.servoj(current), "update accepted after disable", -8)
            expect_rc(arm.stop_servoj(), "cleanup after disable", 0)
            require(arm.enable_motors(), "enable after disable")

            expect_rc(arm.control_mit(zero, zero, SEED, zero, zero), "reset simulation seed", 0)
            p_limits = oa.CartesianServoLimits()
            p_limits.max_linear_velocity, p_limits.max_angular_velocity = 0.02, 0.1
            p_limits.max_linear_acceleration, p_limits.max_angular_acceleration = 0.05, 0.2
            pose = arm.get_end_effector_pose()
            pose.x += 0.001  # Absolute base_T_link7; metres, wxyz, no implicit TCP offset.
            expect_rc(arm.start_servop(), "start_servop failed", 0)
            p_before = arm.get_servop_status().accepted_sequence
            for field in ("max_linear_velocity", "max_angular_velocity",
                          "max_linear_acceleration", "max_angular_acceleration"):
                saved = getattr(p_limits, field)
                for invalid in (0, -1, float("nan"), float("inf")):
                    setattr(p_limits, field, invalid)
                    expect_rc(arm.servop(pose, p_limits), f"ServoP accepted invalid {field}", -1)
                setattr(p_limits, field, saved)
            require(arm.get_servop_status().accepted_sequence == p_before,
                    "invalid ServoP limits advanced sequence")
            expect_rc(arm.movej(SEED, 0.2), "MoveJ must be BUSY during ServoP", -8)
            def pose_arrived(s):
                error, angle = pose_error(arm.get_end_effector_pose(), pose)
                return (s.applied_sequence > p_before and s.state == oa.ServoPState.HOLDING
                        and s.last_error == 0 and error < POSITION_TOLERANCE and angle < 0.005)
            wait_for("ServoP different absolute pose applied and converged", arm, "servop",
                     pose_arrived, lambda: arm.servop(pose, p_limits))
            expect_rc(arm.stop_servop(), "stop_servop failed", 0)
            require(arm.get_servop_status().state == oa.ServoPState.IDLE, "ServoP stop state")
            expect_rc(arm.servop(pose, p_limits), "ServoP update after stop must be BUSY", -8)
            expect_rc(arm.control_mit(zero, zero, SEED, zero, zero), "MoveC seed", 0)
            via, end = arm.get_end_effector_pose(), arm.get_end_effector_pose()
            via.x += 0.0005; via.z += 0.0002
            end.x += 0.001
            expect_rc(arm.movec(via, end, 0.2, 1), "MoveC accepted unsupported buffering", -1)
            rc = arm.movec(via, end, 0.2, 0)
            require(rc == 0, f"small MoveC execution failed rc={rc}")
            error, angle = pose_error(arm.get_end_effector_pose(), end)
            require(error < POSITION_TOLERANCE and angle < 0.005,
                    f"MoveC endpoint error={error}m orientation={angle}rad")
            print(json.dumps({"check": "MoveC arc and buffer rejection", "result": "passed",
                              "position_error_m": error, "orientation_error_rad": angle}), flush=True)

            expect_rc(arm.start_servop(), "ServoP restart failed", 0)
            pose = arm.get_end_effector_pose()
            pose.x += 0.001
            cancel_sequence = arm.get_servop_status().accepted_sequence
            wait_for("ServoP applied before cancel", arm, "servop",
                     lambda s: s.applied_sequence > cancel_sequence
                     and s.state in (oa.ServoPState.RUNNING, oa.ServoPState.LIMIT_TRANSITION),
                     lambda: arm.servop(pose, p_limits))
            expect_rc(arm.cancel_trajectory(), "ServoP cancel failed", 0)
            wait_for("ServoP cancel -> controlled hold", arm, "servop",
                     lambda s: s.state in (oa.ServoPState.HOLDING, oa.ServoPState.IDLE))
            expect_rc(arm.servop(pose, p_limits), "ServoP accepted update after cancel", -8)
            expect_rc(arm.stop_servop(), "ServoP cancel cleanup failed", 0)
            expect_rc(arm.start_servop(), "ServoP post-cancel restart")
            expect_rc(arm.stop_servop(), "ServoP post-cancel stop")

        except BaseException:
            for kind in ("servoj", "servop"):
                print(json.dumps({"failure_snapshot": kind, **snapshot(arm, kind)}), flush=True)
            raise
        finally:
            errors = []
            for name in ("stop_servoj", "stop_servop", "cancel_trajectory", "disable_motors"):
                try:
                    rc = getattr(arm, name)()
                    if not (rc is True if name == "disable_motors" else rc == 0):
                        errors.append(f"{name}: {rc}")
                except Exception as exc:
                    errors.append(f"{name}: {exc}")
            del arm
            require(not errors, f"cleanup failed: {errors}")
    print("Offline servo regression passed; physical tracking and safety performance NOT tested", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--import-order", choices=("arm-first", "gripper-first"), default="arm-first")
    parser.add_argument("--smoke-only", action="store_true", help="arm-only Conda ABI/API smoke, not full regression")
    parser.add_argument("--moving-stop-only", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--moving-retarget-only", action="store_true", help="moving latest-target convergence regression")
    parser.add_argument("--arm-only", action="store_true", help="skip standalone gripper module import")
    parser.add_argument("--timeout-recovery-only", action="store_true", help="resume after timeout braking and holding")
    args = parser.parse_args()
    run(args.import_order, args.smoke_only, args.moving_stop_only, args.moving_retarget_only, args.arm_only, args.timeout_recovery_only)
    if not args.smoke_only and not args.moving_stop_only and not args.moving_retarget_only and not args.timeout_recovery_only:
        # A faulty stop can block cleanup too. Bound the isolated simulation
        # process so a regression cannot hang the complete release validator.
        subprocess.run([sys.executable, "-X", "faulthandler", str(Path(__file__).resolve()),
                        "--import-order", args.import_order, "--moving-stop-only"],
                       check=True, timeout=60)

        subprocess.run([sys.executable, "-X", "faulthandler", str(Path(__file__).resolve()),
                        "--import-order", args.import_order, "--moving-retarget-only"],
                       check=True, timeout=150)

        subprocess.run([sys.executable, "-X", "faulthandler", str(Path(__file__).resolve()),
                        "--import-order", args.import_order, "--timeout-recovery-only"],
                       check=True, timeout=100)
