#!/usr/bin/env python3
"""Compile temporary SDK copies separately and together with distinct timestamps."""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARM = ROOT / "c++/include"
GRIPPER = ROOT / "gripper/c++/include"

if (ARM / "onero_define.h").read_bytes() != (GRIPPER / "onero_define.h").read_bytes():
    raise SystemExit("arm and gripper onero_define.h must be identical")

compiler = os.environ.get("CXX", "cl" if os.name == "nt" else "c++")
arm_checks = """
static_assert(sizeof(onero_api::OneroArm) > 0);
static_assert(sizeof(onero_api::onero_config_t) > 0);
"""
gripper_checks = """
#include <type_traits>
#include <utility>
static_assert(std::is_same_v<
    decltype(std::declval<onero_gripper_api::OneroGripper>().status()),
    onero_api::GripperStatus>);
static_assert(std::is_same_v<
    decltype(std::declval<onero_gripper_api::OneroGripper>().get_tactile()),
    onero_api::GripperTactileStatus>);
"""
with tempfile.TemporaryDirectory(prefix="onero-header-review-") as tmp:
    stage = Path(tmp)
    arm = stage / "arm"
    gripper = stage / "gripper"
    shutil.copytree(ARM, arm)
    shutil.copytree(GRIPPER, gripper)
    stamp = (arm / "onero_define.h").stat().st_mtime
    os.utime(gripper / "onero_define.h", (stamp + 2, stamp + 2))
    assert (arm / "onero_define.h").stat().st_mtime != (gripper / "onero_define.h").stat().st_mtime
    arm_header, gripper_header = "onero_interface_cpp.h", "onero_gripper.h"
    cases = (
        ("arm-only", (arm_header,), (arm,), arm_checks),
        ("gripper-only", (gripper_header,), (gripper,), gripper_checks),
        ("arm-first", (arm_header, gripper_header), (arm, gripper), arm_checks + gripper_checks),
        ("gripper-first", (gripper_header, arm_header), (arm, gripper), arm_checks + gripper_checks),
    )
    failed = False
    for label, headers, includes, checks in cases:
        source = stage / f"{label}.cpp"
        source.write_text("".join(f'#include "{name}"\n' for name in headers * 2)
                          + checks + "int main() { return 0; }\n", encoding="utf-8")
        if os.name == "nt":
            command = [compiler, "/nologo", "/std:c++17", "/EHsc", "/utf-8", "/Zs",
                       *("/I" + str(path) for path in includes), str(source)]
        else:
            command = [compiler, "-std=c++17", "-fsyntax-only",
                       *("-I" + str(path) for path in includes), str(source)]
        result = subprocess.run(command, cwd=stage)
        print(f"{label}: compile_exit = {result.returncode}", flush=True)
        failed |= result.returncode != 0
    if failed:
        raise SystemExit(1)
