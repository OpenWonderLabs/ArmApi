#!/usr/bin/env python3
"""Execute offline consumer checks on one target; keep raw logs outside the SDK."""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {
    "linux-x86_64": ("native_platform_checks", "native", "linux/linux-x86_64", "linux/linux-64"),
    "linux-arm64": ("native_platform_checks", "native", "linux/linux-arm64", "linux/linux-aarch64"),
    "windows-x86_64": ("native_platform_checks", "native", "windows/windows-x86_64", "windows/win-64"),
    "linux-riscv64": ("emulated_platform_checks", "QEMU user mode", "linux/linux-riscv64", None),
}
CHECKS = ("examples_link", "frame_c", "frame_cpp", "gripper_no_device", "motion_argument_gates",
          "servoj_cpp_simulation", "servop_cpp_simulation", "python_frame", "python_arm-first",
          "python_gripper-first", "servoj_moving_stop", "servoj_moving_retarget",
          "servoj_shared_library_moving_retarget", "servoj_timeout_recovery",
          "numpy_import_orders", "environment_inventory")
SUITE_VERSION = 5


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifacts(root, key):
    _, _, directory, channel = PLATFORMS[key]
    paths = set()
    for base in ("c", "c++", "gripper/c", "gripper/c++"):
        paths.update(p for p in (root / base / directory).glob("*") if p.is_file())
    for base in ("python/wheels", "gripper/python/wheels"):
        paths.update((root / base / key).glob("*.whl"))
    paths.update(p for p in (root / "runtime" / key / "lib").glob("*") if p.is_file())
    if channel:
        paths.update((root / "python/conda_channel" / channel).glob("*.conda"))
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(paths)}


def inputs(root, key):
    # Bind evidence to consumers, public contracts and models as well as binaries.
    paths = set()
    for base in ("demo", "gripper/demo", "c/include", "c++/include", "gripper/c/include",
                 "gripper/c++/include", "c/share", "c++/share"):
        paths.update(p for p in (root / base).rglob("*") if p.is_file()
                     and not any(part in ("build", "__pycache__") for part in p.relative_to(root).parts))
    paths.update(root / p for p in ("tools/servo_regression.py", "tools/validate_platform.py",
                                   "tools/numpy_import_regression.py", "tools/record_environment.py",
                                   "python/oneroarm.pyi", "gripper/python/onerogripper.pyi", "VERSION",
                                   ".github/workflows/release-validation.yml"))
    lock = root / "python/environments" / f"{key}-py312-explicit.txt"
    if lock.exists():
        paths.add(lock)
    if key == "linux-riscv64":
        paths.add(root / "python/environments/linux-riscv64-ubuntu24.04-packages.tsv")
    return {p.relative_to(root).as_posix(): digest(p) for p in sorted(paths)}


def check_evidence(root, evidence, complete=True):
    errors = []
    if not isinstance(evidence, dict):
        return ["execution evidence must be a JSON object"]
    if evidence.get("sdk_version") != (root / "VERSION").read_text().strip():
        errors.append("execution evidence SDK version differs from VERSION")
    for key, (group, mode, _, channel) in PLATFORMS.items():
        records = evidence.get(group, {})
        record = records.get(key, {}) if isinstance(records, dict) else {}
        if not isinstance(record, dict):
            errors.append(f"{key}: invalid platform evidence structure")
            continue
        recorded = record.get("artifact_sha256", {})
        if not isinstance(recorded, dict):
            errors.append(f"{key}: invalid artifact hash mapping")
            continue
        expected = artifacts(root, key)
        if not expected or not set(expected).issubset(recorded):
            errors.append(f"{key}: missing required delivered artifact hashes")
        for relative, checksum in recorded.items():
            if not isinstance(relative, str) or not isinstance(checksum, str):
                errors.append(f"{key}: invalid artifact path/checksum")
                continue
            path = root / relative
            if (Path(relative).is_absolute() or ".." in Path(relative).parts
                    or not path.is_file() or not path.resolve().is_relative_to(root.resolve())
                    or digest(path) != checksum):
                errors.append(f"{key}: artifact differs from executed snapshot: {relative}")
        if not complete:
            continue
        if (record.get("status") != "passed" or record.get("suite_version") != SUITE_VERSION
                or record.get("execution_mode") != mode or record.get("hardware_connected") is not False):
            errors.append(f"{key}: pending target execution for suite {SUITE_VERSION} ({mode})")
        if record.get("inputs_sha256") != inputs(root, key):
            errors.append(f"{key}: public headers/models/test inputs differ from executed snapshot")
        checks = record.get("checks", {})
        required_checks = (*CHECKS, "conda_joint_arm-first", "conda_joint_gripper-first") if key == "linux-x86_64" else CHECKS
        if not isinstance(checks, dict) or any(checks.get(name) != "passed" for name in required_checks):
            errors.append(f"{key}: required target consumer/servo checks are incomplete")
        environment = record.get("environment", {})
        packages = environment.get('packages') if isinstance(environment, dict) else None
        if (not isinstance(environment, dict)
                or not all(isinstance(environment.get(k), str) and environment[k] for k in ('os','python','numpy'))
                or not isinstance(packages, list) or not packages
                or any(not isinstance(p, dict) or not all(isinstance(p.get(k), str) and p[k] for k in ('name','version'))
                       for p in packages)):
            errors.append(f"{key}: actual execution dependency inventory is missing")
        if key == "linux-riscv64" and (not isinstance(environment, dict) or environment.get("inventory_source") != "dpkg"):
            errors.append("RISC-V execution must retain its actual apt/dpkg inventory")
        log = record.get("execution_log", {})
        if (not isinstance(log, dict) or not isinstance(log.get("id"), str)
                or not isinstance(log.get("sha256"), str)
                or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", log["id"])
                or not re.fullmatch(r"[a-f0-9]{64}", log["sha256"])):
            errors.append(f"{key}: missing private execution log identifier/SHA-256")
        required_python = {"3.10", "3.11", "3.12", "3.13"} if channel else {"3.12"}
        python_checks = record.get("python_checks", [])
        passed_python = {p.get("python_minor") for p in python_checks
                         if isinstance(p, dict) and p.get("status") == "passed"
                         and isinstance(p.get("python_minor"), str)} if isinstance(python_checks, list) else set()
        if not required_python.issubset(passed_python):
            errors.append(f"{key}: missing Conda/Python ABI smoke records")
        if key == "linux-riscv64" and record.get("native_board_validation") is not False:
            errors.append("RISC-V QEMU evidence must not claim native-board validation")
    return errors


def current_platform():
    machine = platform.machine().lower()
    architecture = {"amd64": "x86_64", "x86_64": "x86_64", "aarch64": "arm64",
                    "arm64": "arm64", "riscv64": "riscv64"}.get(machine)
    key = f"{'windows' if os.name == 'nt' else 'linux'}-{architecture}"
    if key not in PLATFORMS:
        raise ValueError(f"unsupported execution platform: {platform.system()}/{machine}")
    return key


def execute(args):
    if platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 12):
        raise ValueError("target suite requires CPython 3.12; other ABIs are separate smoke interpreters")
    key = current_platform()
    group, mode, directory, channel = PLATFORMS[key]
    if args.execution_mode != ("qemu" if key == "linux-riscv64" else "native"):
        raise ValueError("execution mode must explicitly match the target; QEMU is not native execution")
    output = args.output_dir.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("raw logs/build outputs must be outside the public SDK directory")
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,160}", args.log_id):
        raise ValueError("use an opaque private log ID, not a private URL or machine path")
    output.mkdir(parents=True, exist_ok=True)
    log_path = output / "execution.log"
    if log_path.exists():
        raise ValueError("use a fresh output directory; do not overwrite prior execution logs")
    record = {"suite_version": SUITE_VERSION, "sdk_version": (ROOT / "VERSION").read_text().strip(),
              "date": datetime.now(timezone.utc).isoformat(), "status": "failed",
              "hardware_connected": False, "execution_mode": mode,
              "target": platform.system() + " " + platform.machine(),
              "artifact_sha256": artifacts(ROOT, key), "inputs_sha256": inputs(ROOT, key),
              "checks": {}, "python_checks": []}
    if platform.system() == "Linux":
        release = platform.freedesktop_os_release()
        record["environment"] = {"os": release.get("PRETTY_NAME", "Linux"),
                                 "python": platform.python_version()}
    else:
        record["environment"] = {"os": platform.system() + " " + platform.release(),
                                 "python": platform.python_version()}
    if key == "linux-riscv64":
        record["native_board_validation"] = False
    env = os.environ.copy()
    for name in ("PYTHONPATH", "LD_LIBRARY_PATH", "ONERO_DESCRIPTION_PATH", "ONERO_DESCRIPTION_DIR"):
        env.pop(name, None)
    env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1")
    deps = ROOT / "runtime" / key / "lib"
    if not deps.is_dir():
        deps = Path(sys.prefix) / ("Library/bin" if os.name == "nt" else "lib")
    if os.name == "nt":
        env["PATH"] = os.pathsep.join(map(str, (ROOT / "c" / directory,
                                    ROOT / "gripper/c" / directory, deps))) + os.pathsep + env["PATH"]
    else:
        env["LD_LIBRARY_PATH"] = str(deps)

    def command(label, argv, expected=0, environment=None):
        with log_path.open("a", encoding="utf-8") as log:
            offset = log.tell()
            log.write(f"\n[{label}] {list(map(str, argv))!r}\n"); log.flush()
            result = subprocess.run(list(map(str, argv)), cwd=ROOT, env=environment or env,
                                    stdout=log, stderr=subprocess.STDOUT,
                                    timeout=60 if label.startswith("conda_servoj_moving_stop") else 300)
            log.write(f"returncode={result.returncode}; expected={expected}\n")
        if result.returncode != expected:
            raise RuntimeError(f"{label}: rc={result.returncode}; see private execution log")
        record["checks"][label] = "passed"
        if label == "environment_inventory" or label.startswith("numpy_"):
            with log_path.open("rb") as log:
                log.seek(offset)
                values = [json.loads(line) for line in log.read().decode("utf-8").splitlines()
                          if line.startswith('{')]
            if label == "environment_inventory":
                environment = next(v for v in values if v.get("check") == "SDK execution environment")
                record["environment"] = {k:v for k,v in environment.items() if k != "check"}
            else:
                orders = [v for v in values if v.get("check") == "NumPy SDK import order" and v.get("result") == "passed"]
                expected_orders = 2 if label.startswith("numpy_conda_") and not label.endswith("3.12") else 6
                if len(orders) != expected_orders or len({tuple(v["order"]) for v in orders}) != expected_orders:
                    raise RuntimeError(f"{label}: incomplete NumPy import-order execution")
                record.setdefault("numpy_import_measurements", {})[label] = orders
                record["checks"]["numpy_import_orders"] = "passed"
        if label.startswith(("python_arm-first", "python_gripper-first", "conda_joint_", "conda_servoj_moving_stop", "conda_servoj_moving_retarget", "conda_servoj_timeout_recovery")):
            with log_path.open("rb") as log:
                log.seek(offset)
                lines = log.read().decode("utf-8", errors="replace").splitlines()
            measurements = []
            retargets = []
            recoveries = []
            for line in lines:
                if not line.startswith('{'):
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if value.get("check") == "ServoJ timeout recovery":
                    recoveries.append({k:value[k] for k in ("limits", "resume_phase", "resume_same_target", "elapsed_s", "time_bound_s", "position_error_rad")})
                if value.get("check") == "ServoJ moving retarget":
                    retargets.append({k: value[k] for k in ("limits", "mode", "elapsed_s", "time_bound_s",
                                      "position_error_rad", "peak_q0", "target", "replan_count")})
                if value.get("check") == "ServoJ moving stop and refused generic cancel":
                    measurements.append({k: value[k] for k in ("limits", "streaming", "elapsed_s",
                                         "time_bound_s", "velocity_sign_reversals", "final_state", "final_error")})
            if not label.startswith(("conda_servoj_moving_stop", "conda_servoj_timeout_recovery")):
                if {(m["limits"], m["mode"]) for m in retargets} != {
                        (limits, mode) for limits in ("default", "custom") for mode in ("forward", "reverse", "burst")}:
                    raise RuntimeError(f"{label}: missing moving-retarget scenarios")
                record.setdefault("servoj_moving_retarget_measurements", {})[label] = retargets
                record["checks"]["servoj_moving_retarget"] = "passed"
            if not label.startswith(("conda_servoj_moving_retarget", "conda_servoj_timeout_recovery")) and {(m["limits"], m["streaming"]) for m in measurements} != {
                    (limits, streaming) for limits in ("default", "custom") for streaming in (False, True)}:
                raise RuntimeError(f"{label}: missing moving-stop scenarios in execution log")
            if measurements:
                record.setdefault("servoj_moving_stop_measurements", {})[label] = measurements
                record["checks"]["servoj_moving_stop"] = "passed"
            if not label.startswith(("conda_servoj_moving_stop", "conda_servoj_moving_retarget")):
                if {(v["limits"], v["resume_phase"]) for v in recoveries} != {(limits, phase) for limits in ("default", "custom") for phase in ("BRAKING", "HOLDING")}:
                    raise RuntimeError(f"{label}: missing timeout-recovery scenarios")
                record.setdefault("servoj_timeout_recovery_measurements", {})[label] = recoveries
                record["checks"]["servoj_timeout_recovery"] = "passed"
        if label == "servoj_cpp_simulation":
            with log_path.open("rb") as log:
                log.seek(offset)
                output = log.read().decode("utf-8", errors="replace")
            match = re.search(r"shared-library moving retarget elapsed_s=([\d.e+-]+) error_rad=([\d.e+-]+) peak_q0=([\d.e+-]+) target_q0=([\d.e+-]+) state=HOLDING replans=(\d+) expected_replans=(\d+)", output)
            if not match or match[5] != match[6]:
                raise RuntimeError("shared-library moving-retarget measurement missing/inconsistent")
            record["servoj_shared_library_moving_retarget"] = {
                "elapsed_s": float(match[1]), "position_error_rad": float(match[2]),
                "peak_q0": float(match[3]), "target_q0": float(match[4]), "state": "HOLDING", "replan_count": int(match[5])}
            record["checks"]["servoj_shared_library_moving_retarget"] = "passed"
            with log_path.open("rb") as log:
                log.seek(offset)
                output = log.read().decode("utf-8", errors="replace")
            match = re.search(r"shared-library moving stop elapsed_s=([\d.e+-]+) bound_s=([\d.e+-]+) generic_cancel=-8 state=IDLE", output)
            if not match:
                raise RuntimeError("shared library moving-stop measurement is missing")
            record["servoj_shared_library_moving_stop"] = {
                "elapsed_s": float(match[1]), "time_bound_s": float(match[2]),
                "generic_cancel": -8, "final_state": "IDLE"}
        print(label, "passed", flush=True)

    try:
        command("environment_inventory", [sys.executable, ROOT / "tools/record_environment.py"])
        build = output / "build"
        options = [f"-DONERO_DEPENDENCY_DIR={deps}"] if os.name != "nt" else ["-A", "x64"]
        command("configure", ["cmake", "-S", ROOT / "demo", "-B", build, "-DCMAKE_BUILD_TYPE=Release", *options])
        command("examples_link", ["cmake", "--build", build, "--config", "Release", "--parallel", "2"])
        binary_dir = build / "Release" if os.name == "nt" else build
        suffix = ".exe" if os.name == "nt" else ""
        binary = lambda name: binary_dir / (name + suffix)
        for lang in ("c", "cpp"):
            command(f"frame_{lang}", [binary(f"frame_demo_{lang}")])
        missing = output / "nonexistent-gripper-device"
        if missing.exists():
            raise ValueError("test device unexpectedly exists")
        command("gripper_no_device", [binary("gripper_offline_check_cpp"), missing])
        for kind in ("servoj", "servop"):
            for lang in ("c", "cpp"):
                for index, arguments in enumerate(([], ["--run"], ["--device", str(missing)])):
                    command(f"gate_{kind}_{lang}_{index}", [binary(f"{kind}_demo_{lang}"), *arguments], expected=2)
            command(f"{kind}_cpp_simulation", [binary(f"{kind}_demo_cpp"), "--simulate"])
        record["checks"]["motion_argument_gates"] = "passed"
        interpreters = {"3.12": Path(sys.executable)}
        for argument in args.smoke_python:
            version, executable = argument.split("=", 1)
            if version not in ("3.10", "3.11", "3.13"):
                raise ValueError("--smoke-python expects 3.10, 3.11 or 3.13=interpreter")
            interpreters[version] = Path(executable)
        if channel:
            for version, executable in sorted(interpreters.items()):
                # Verify actual installed package identity, not just a successful import from elsewhere.
                code = """
import hashlib, importlib, json, sys
from pathlib import Path
root, minor, subdir = sys.argv[1:]
assert '.'.join(map(str, sys.version_info[:2])) == minor
for name in (('oneroarm','onerogripper') if minor == '3.12' else ('oneroarm',)):
    module=importlib.import_module(name)
    assert Path(module.__file__).resolve().is_relative_to(Path(sys.prefix).resolve()), module.__file__
    matches=list((Path(sys.prefix)/'conda-meta').glob(name+'-*.json'))
    assert len(matches)==1, matches
    meta=json.loads(matches[0].read_text())
    package=Path(root)/'python/conda_channel'/subdir/meta['fn']
    assert meta['sha256']==hashlib.sha256(package.read_bytes()).hexdigest(), meta['fn']
    assert meta['version']==(Path(root)/'VERSION').read_text().strip()
print('exact delivered Conda package identity passed')
print('Private environment:', sys.version, sys.prefix)
for metadata in sorted((Path(sys.prefix)/'conda-meta').glob('*.json')):
    package=json.loads(metadata.read_text())
    print(package.get('name'), package.get('version'), package.get('build'), package.get('sha256'))
"""
                py_env = env.copy()
                if os.name == "nt":
                    py_env["PATH"] = str(executable.parent / "Library/bin") + os.pathsep + env["PATH"]
                else:
                    py_env["LD_LIBRARY_PATH"] = str(executable.parent.parent / "lib")
                command(f"conda_identity_{version}", [executable, "-c", code, ROOT, version, channel], environment=py_env)
                command(f"conda_smoke_{version}", [executable, ROOT / "tools/servo_regression.py", "--smoke-only"], environment=py_env)
                command(f"conda_servoj_moving_stop_{version}",
                        [executable, ROOT / "tools/servo_regression.py", "--smoke-only", "--moving-stop-only"],
                        environment=py_env)
                command(f"conda_servoj_moving_retarget_{version}",
                        [executable, ROOT / "tools/servo_regression.py", "--smoke-only", "--moving-retarget-only"],
                        environment=py_env)
                command(f"conda_servoj_timeout_recovery_{version}",
                        [executable, ROOT / "tools/servo_regression.py", "--smoke-only", "--timeout-recovery-only"], environment=py_env)
                command(f"numpy_conda_{version}", [executable, ROOT / "tools/numpy_import_regression.py", *([] if version == "3.12" else ["--arm-only"])], environment=py_env)
                record["python_checks"].append({"python_minor": version, "package": "Conda", "status": "passed",
                                                "scope": "install/import/default model/key API smoke, ServoJ moving-stop/retarget/timeout-recovery and NumPy import-order regression"})
        runtime_env = env.copy()
        if key in ("linux-x86_64", "linux-riscv64"):
            target = output / "wheel-target"
            wheels = sorted((ROOT / "python/wheels" / key).glob("*.whl")) + sorted((ROOT / "gripper/python/wheels" / key).glob("*.whl"))
            command("wheel_install", [sys.executable, "-m", "pip", "install", "--no-index", "--no-deps", "--target", target, *wheels])
            runtime_env.pop("LD_LIBRARY_PATH", None)
            runtime_env["PYTHONPATH"] = str(target)
        command("numpy_python", [sys.executable, ROOT / "tools/numpy_import_regression.py"], environment=runtime_env)
        command("python_frame", [sys.executable, ROOT / "demo/python/advanced/frame_transform.py"], environment=runtime_env)
        for order in ("arm-first", "gripper-first"):
            if key == "linux-x86_64":
                command(f"conda_joint_{order}", [sys.executable, "-X", "faulthandler", ROOT / "tools/servo_regression.py",
                                               "--import-order", order])
            command(f"python_{order}", [sys.executable, "-X", "faulthandler", ROOT / "tools/servo_regression.py",
                                       "--import-order", order], environment=runtime_env)
        if not channel:
            record["python_checks"].append({"python_minor": "3.12", "package": "wheel", "status": "passed",
                                            "scope": "both import orders and offline servo regression"})
        if artifacts(ROOT, key) != record["artifact_sha256"] or inputs(ROOT, key) != record["inputs_sha256"]:
            raise RuntimeError("SDK/test files changed during execution; evidence discarded")
        record["status"] = "passed" if not channel or len(interpreters) == 4 else "pending"
        if record["status"] == "pending":
            record["pending_reason"] = "Conda 3.10/3.11/3.13 smoke interpreters are missing"
    finally:
        if log_path.exists():
            record["execution_log"] = {"id": args.log_id, "sha256": digest(log_path)}
        payload = {"sdk_version": record["sdk_version"], group: {key: record}}
        (output / f"{key}.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if record["status"] != "passed":
        raise RuntimeError(record.get("pending_reason", "incomplete platform execution"))
    print(f"{key}: target offline suite passed; hardware NOT tested")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execution-mode", choices=("native", "qemu"), required=True)
    parser.add_argument("--log-id", required=True, help="opaque locator for retained PRIVATE execution.log")
    parser.add_argument("--smoke-python", action="append", default=[], metavar="MINOR=PYTHON")
    args = parser.parse_args()
    try:
        execute(args)
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Target validation failed: {exc}\n")


if __name__ == "__main__":
    main()
