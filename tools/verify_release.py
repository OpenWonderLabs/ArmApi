#!/usr/bin/env python3
import argparse
import hashlib
import io
import json
import os
import platform
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from verify_conda_html import check_conda_html
from check_execution_evidence import check_execution_evidence

parser = argparse.ArgumentParser(description="Validate release files and offline execution evidence.")
parser.add_argument("--static-only", action="store_true",
                    help="inspect files/evidence only; skip wheel installation and execution")
parser.add_argument("--evidence", type=Path, help="separately retained execution evidence JSON")
args = parser.parse_args()
if not args.static_only and (platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 12)):
    parser.error("Full release checks require CPython 3.12. Use --static-only for file checks only; "
                 "static success is NOT full release acceptance.")
if platform.system() != "Linux" or platform.machine() not in ("x86_64", "AMD64"):
    parser.error("Run the release aggregate on Linux x86_64; use validate_platform.py on target runners.")
if not args.static_only and args.evidence is None:
    parser.error("Full release acceptance requires --evidence; execution records are not part of the SDK.")

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []

def fail(message: str) -> None:
    ERRORS.append(message)

def run(*args: str, env=None):
    process_env = dict(os.environ if env is None else env)
    process_env["LC_ALL"] = "C"
    process_env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        return subprocess.run(args, cwd=ROOT, text=True, capture_output=True, env=process_env, timeout=300)
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        fail(f"command exceeded 300s: {args[0]}")
        return subprocess.CompletedProcess(args, 124, stdout, stderr + "\ncommand timed out after 300s")

def check_elf(path: Path) -> None:
    rel = path.relative_to(ROOT)
    output = run("file", str(path)).stdout
    if "stripped" not in output or "not stripped" in output:
        fail(f"not stripped: {rel}")
    strings = run("strings", str(path)).stdout
    if any(token in strings for token in ("/home/", "SDK_movec", "test_7k7k")):
        fail(f"absolute or internal path in {rel}")
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(ROOT / "runtime/linux-x86_64/lib")
    ldd = run("ldd", str(path), env=env)
    if ldd.returncode or "not found" in ldd.stdout:
        fail(f"unresolved dependency in {rel}: {ldd.stdout}{ldd.stderr}")

def check_cross_platform_binary(path: Path, architecture: str) -> None:
    rel = path.relative_to(ROOT)
    output = run("file", str(path)).stdout
    if architecture not in output:
        fail(f"wrong architecture for {rel}: {output.strip()}")
    if architecture in ("ARM aarch64", "RISC-V") and ("not stripped" in output or "stripped" not in output):
        fail(f"not stripped: {rel}")
    strings = run("strings", str(path)).stdout
    if any(token in strings for token in ("/home/", "\\Users\\", "SDK_movec", "test_7k7k")):
        fail(f"absolute or internal path in {rel}")

def check_exports(path: Path, version_node: str, c_prefix: str, cpp_prefixes) -> None:
    unexpected = []
    output = run("nm", "-D", "--defined-only", str(path))
    if output.returncode:
        fail(f"cannot inspect exports: {path.relative_to(ROOT)}")
        return
    names = []
    for line in output.stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        name = fields[-1].split("@@")[0]
        names.append(name)
        if name == version_node or name.startswith(c_prefix):
            continue
        demangled = run("c++filt", name).stdout.strip()
        if not demangled.startswith(cpp_prefixes):
            unexpected.append(demangled)
    if unexpected:
        fail(f"unexpected exports in {path.relative_to(ROOT)}: {unexpected[:8]}")
    if c_prefix == "onero_":
        demangled = run("c++filt", *names).stdout
        for method in ("onero_api::OneroArm::has_gripper() const",
                       "onero_api::OneroArm::gripper() const",
                       "onero_api::OneroGripper::valid() const"):
            if method not in demangled:
                fail(f"missing public const method {method}: {path.relative_to(ROOT)}")
    if c_prefix == "onerogripper_":
        demangled = run("c++filt", *names).stdout
        for method in ("OneroGripper", "~OneroGripper", "valid", "enable", "disable",
                       "status", "set_position", "move_position", "force_control",
                       "get_tactile", "request_stop", "clear_stop"):
            if f"onero_gripper_api::OneroGripper::{method}(" not in demangled:
                fail(f"missing gripper C++ method {method}: {path.relative_to(ROOT)}")
        if "onero_gripper_api::OneroGripper::valid() const" not in demangled:
            fail(f"missing const valid(): {path.relative_to(ROOT)}")

def check_c_header_exports(header: Path, binary: Path, macro: str, prefix: str) -> None:
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", header.read_text(), flags=re.S)
    declarations = set(re.findall(rf"\b{macro}\s+[^;{{}}]*?\b({prefix}\w+)\s*\(", source))
    if not declarations:
        fail(f"no C declarations found: {header.relative_to(ROOT)}")
        return
    if binary.suffix == ".dll":
        output = run("objdump", "-p", str(binary))
        section = output.stdout.partition("[Ordinal/Name Pointer] Table")[2]
        names = set(re.findall(r"^\s*\[\s*\d+\]\s+(\S+)\s*$", section, flags=re.M))
    else:
        output = run("nm", "-D", "--defined-only", str(binary))
        names = {line.split()[-1].split("@@")[0] for line in output.stdout.splitlines() if line.split()}
    if output.returncode:
        fail(f"cannot inspect C exports: {binary.relative_to(ROOT)}")
        return
    missing = sorted(declarations - names)
    if missing:
        fail(f"C header declarations missing in {binary.relative_to(ROOT)}: {missing}")

def check_conda_info(path: Path, expected_metadata=None) -> None:
    # Inspect package metadata without extracting files or installing the package.
    try:
        with zipfile.ZipFile(path) as package:
            names = [name for name in package.namelist() if name.startswith("info-") and name.endswith(".tar.zst")]
            if len(names) != 1:
                raise ValueError("expected one info component")
            unpacked = subprocess.run(["zstd", "-dq"], input=package.read(names[0]), capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(unpacked)) as metadata:
            for member in metadata:
                if member.name == "info/recipe" or member.name.startswith("info/recipe/"):
                    fail(f"build recipe included in {path.name}: {member.name}")
                if member.isfile():
                    content = metadata.extractfile(member).read()
                    if member.name == "info/index.json" and expected_metadata is not None:
                        index = json.loads(content)
                        for key in ("name", "version", "build", "build_number", "subdir", "depends"):
                            if index.get(key) != expected_metadata.get(key):
                                fail(f"Conda info/repodata mismatch for {key}: {path.name}")
                    if re.search(rb"/home/|/Users/|/runner/|[A-Za-z]:[\\/]a[\\/]|[\\/]Users[\\/]|SDK_movec|test_7k7k|OneroArm_for_develop_multiplatform_build", content):
                        fail(f"internal build path in {path.name}: {member.name}")
    except Exception as exc:
        fail(f"cannot inspect Conda metadata in {path.name}: {exc}")

version = (ROOT / "VERSION").read_text().strip()
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    fail(f"unexpected VERSION: {version}")

try:
    manifest = json.loads((ROOT / "RELEASE_MANIFEST.json").read_text())
    if manifest.get("sdk_version") != version:
        fail("RELEASE_MANIFEST.json version does not match VERSION")
    if manifest.get("release_status") != "release":
        fail("release must be marked release")
except Exception as exc:
    fail(f"invalid RELEASE_MANIFEST.json: {exc}")

required = [
    "c/include/onero_interface_c.h",
    "c++/include/onero_interface_cpp.h",
    "c++/include/onero_define.h",
    "c/linux/linux-x86_64/liboneroarm.so",
    "c++/linux/linux-x86_64/liboneroarm.so",
    "c/linux/linux-arm64/liboneroarm.so",
    "c++/linux/linux-arm64/liboneroarm.so",
    "c/windows/windows-x86_64/oneroarm.dll",
    "c/windows/windows-x86_64/oneroarm.lib",
    "c++/windows/windows-x86_64/oneroarm.dll",
    "c++/windows/windows-x86_64/oneroarm.lib",
    "gripper/c/linux/linux-x86_64/libonerogripper.so",
    "gripper/c++/linux/linux-x86_64/libonerogripper.so",
    "gripper/c/linux/linux-arm64/libonerogripper.so",
    "gripper/c++/linux/linux-arm64/libonerogripper.so",
    "gripper/c/windows/windows-x86_64/onerogripper.dll",
    "gripper/c/windows/windows-x86_64/onerogripper.lib",
    "gripper/c++/windows/windows-x86_64/onerogripper.dll",
    "gripper/c++/windows/windows-x86_64/onerogripper.lib",
    "runtime/linux-x86_64/lib",
    "c/linux/linux-riscv64/liboneroarm.so",
    "c++/linux/linux-riscv64/liboneroarm.so",
    "gripper/c/linux/linux-riscv64/libonerogripper.so",
    "gripper/c++/linux/linux-riscv64/libonerogripper.so",
    "runtime/linux-riscv64/lib",
    "RISC_V_GUIDE.md",
    "python/oneroarm.pyi",
    "gripper/python/onerogripper.pyi",
    "python/conda_channel/linux/linux-64/repodata.json",
    "python/conda_channel/linux/linux-aarch64/repodata.json",
    "python/conda_channel/linux/noarch/repodata.json",
    "python/conda_channel/windows/win-64/repodata.json",
    "python/conda_channel/windows/noarch/repodata.json",
    "RELEASE_MANIFEST.json",
    "SHA256SUMS",
]
for rel in required:
    if not (ROOT / rel).exists():
        fail(f"missing {rel}")

for doc in [*ROOT.rglob("*.md"), *ROOT.glob("*.json")]:
    text = doc.read_text(errors="replace")
    for token in ("/home/woan", "SDK_movec", "test_7k7k", "feat/add-gripper", "pre_binary_release"):
        if token in text:
            fail(f"sensitive/internal token {token!r} in {doc.relative_to(ROOT)}")
    if doc.suffix == ".md":
        for relative in re.findall(
                r"(?:\./)?(?:python|gripper/python)/(?:wheels|conda_channel)/[^\s`\"\\<>]+\.(?:whl|conda)", text):
            if not any(path.is_file() for path in ROOT.glob(relative)):
                fail(f"missing package referenced in {doc.relative_to(ROOT)}: {relative}")

for arch in ("linux-x86_64", "linux-arm64", "windows-x86_64"):
    lock = ROOT / "python/environments" / f"{arch}-py312-explicit.txt"
    if not lock.is_file():
        fail(f"missing tested dependency lock: {lock.relative_to(ROOT)}")
        continue
    lines = lock.read_text().splitlines()
    if not lines or lines[0] != "@EXPLICIT" or len(lines) < 2:
        fail(f"invalid explicit dependency lock: {lock.relative_to(ROOT)}")
    for url in lines[1:]:
        if not url.startswith(("https://conda.anaconda.org/conda-forge/", "https://conda.anaconda.org/robostack-staging/")):
            fail(f"non-public dependency URL in {lock.relative_to(ROOT)}")
        if "/oneroarm-" in url or "/onerogripper-" in url:
            fail(f"SDK package must be installed from the local channel, not the third-party lock: {lock.relative_to(ROOT)}")

ERRORS.extend(check_conda_html(ROOT / "python/conda_channel"))

for conda_dir, expected_arch in (
    (ROOT / "python/conda_channel/linux/linux-64", "linux-64"),
    (ROOT / "python/conda_channel/linux/linux-aarch64", "linux-aarch64"),
    (ROOT / "python/conda_channel/windows/win-64", "win-64"),
):
    try:
        repodata = json.loads((conda_dir / "repodata.json").read_text())
        packages = repodata.get("packages.conda", {})
        names = set(packages)
        arm_names = {
            name for name in names if name.startswith(f"oneroarm-{version}-")
        }
        expected_python_tags = {"py310", "py311", "py312", "py313"}
        actual_python_tags = {
            tag
            for name in arm_names
            for tag in expected_python_tags
            if f"-{tag}" in name
        }
        if actual_python_tags != expected_python_tags or len(arm_names) != 4:
            fail(
                f"incomplete oneroarm Python matrix in {expected_arch}: "
                f"found {sorted(actual_python_tags)}"
            )
        gripper_names = {
            name for name in names
            if name.startswith(f"onerogripper-{version}-py312")
        }
        if len(gripper_names) != 1:
            fail(f"expected one CPython 3.12 onerogripper package in {expected_arch} channel, found {len(gripper_names)}")
        for filename, metadata in packages.items():
            path = conda_dir / filename
            if not path.exists():
                fail(f"Conda repodata references missing file: {path.relative_to(ROOT)}")
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != metadata.get("sha256"):
                fail(f"Conda repodata checksum mismatch: {filename}")
            if path.stat().st_size != metadata.get("size") or hashlib.md5(path.read_bytes()).hexdigest() != metadata.get("md5"):
                fail(f"Conda repodata size/MD5 mismatch: {filename}")
            if metadata.get("version") != version:
                fail(f"wrong Conda package version: {filename}")
            check_conda_info(path, metadata)
            if filename.startswith(f"oneroarm-{version}-"):
                dependencies = set(metadata.get("depends", []))
                if "numpy >=2,<2.3" not in dependencies:
                    fail(f"Conda arm package has wrong NumPy constraint: {filename}")
                if "eigen >=3.4,<3.5" not in dependencies:
                    fail(f"Conda arm package has wrong Eigen constraint: {filename}")
    except Exception as exc:
        fail(f"invalid {expected_arch} Conda channel metadata: {exc}")

arm_c = ROOT / "c/linux/linux-x86_64/liboneroarm.so"
arm_cpp = ROOT / "c++/linux/linux-x86_64/liboneroarm.so"
gripper_c = ROOT / "gripper/c/linux/linux-x86_64/libonerogripper.so"
gripper_cpp = ROOT / "gripper/c++/linux/linux-x86_64/libonerogripper.so"
for binary in (arm_c, arm_cpp, gripper_c, gripper_cpp):
    check_elf(binary)
if arm_c.read_bytes() != arm_cpp.read_bytes():
    fail("C and C++ liboneroarm.so files differ")
if gripper_c.read_bytes() != gripper_cpp.read_bytes():
    fail("C and C++ libonerogripper.so files differ")

cross_platform_pairs = [
    ("c/linux/linux-riscv64/liboneroarm.so", "c++/linux/linux-riscv64/liboneroarm.so", "RISC-V"),
    ("gripper/c/linux/linux-riscv64/libonerogripper.so", "gripper/c++/linux/linux-riscv64/libonerogripper.so", "RISC-V"),
    ("c/linux/linux-arm64/liboneroarm.so", "c++/linux/linux-arm64/liboneroarm.so", "ARM aarch64"),
    ("gripper/c/linux/linux-arm64/libonerogripper.so", "gripper/c++/linux/linux-arm64/libonerogripper.so", "ARM aarch64"),
    ("c/windows/windows-x86_64/oneroarm.dll", "c++/windows/windows-x86_64/oneroarm.dll", "PE32+"),
    ("c/windows/windows-x86_64/oneroarm.lib", "c++/windows/windows-x86_64/oneroarm.lib", "current ar archive"),
    ("gripper/c/windows/windows-x86_64/onerogripper.dll", "gripper/c++/windows/windows-x86_64/onerogripper.dll", "PE32+"),
    ("gripper/c/windows/windows-x86_64/onerogripper.lib", "gripper/c++/windows/windows-x86_64/onerogripper.lib", "current ar archive"),
]
for c_rel, cpp_rel, architecture in cross_platform_pairs:
    c_path, cpp_path = ROOT / c_rel, ROOT / cpp_rel
    if c_path.exists() and cpp_path.exists():
        check_cross_platform_binary(c_path, architecture)
        check_cross_platform_binary(cpp_path, architecture)
        if c_path.read_bytes() != cpp_path.read_bytes():
            fail(f"C and C++ binaries differ: {c_rel} / {cpp_rel}")

for platform in ("linux/linux-x86_64", "linux/linux-arm64", "linux/linux-riscv64", "windows/windows-x86_64"):
    suffix = "oneroarm.dll" if platform.startswith("windows") else "liboneroarm.so"
    check_c_header_exports(ROOT / "c/include/onero_interface_c.h", ROOT / "c" / platform / suffix,
                           "ONERO_API", "onero_")
    suffix = "onerogripper.dll" if platform.startswith("windows") else "libonerogripper.so"
    check_c_header_exports(ROOT / "gripper/c/include/onero_gripper_c.h",
                           ROOT / "gripper/c" / platform / suffix,
                           "ONERO_GRIPPER_API", "onerogripper_")

arm_cpp_prefixes = (
    "onero_api::OneroArm", "onero_api::OneroGripper", "onero_api::OneroDragTeaching",
    "onero_api::transform_pose", "onero_api::apply_cartesian_delta",
    "onero_api::flange_pose_to_tool", "onero_api::tool_pose_to_flange",
    "typeinfo for onero_api::Onero", "typeinfo name for onero_api::Onero",
    "vtable for onero_api::Onero",
)
for architecture in ("linux-x86_64", "linux-arm64", "linux-riscv64"):
    check_exports(
        ROOT / f"c/linux/{architecture}/liboneroarm.so", "ONEROARM_1.2", "onero_",
        arm_cpp_prefixes,
    )
    check_exports(
        ROOT / f"gripper/c/linux/{architecture}/libonerogripper.so",
        "ONEROGRIPPER_1.2", "onerogripper_", ("onero_gripper_api::OneroGripper",),
    )

arm_wheels = list((ROOT / "python/wheels/linux-x86_64").glob("*.whl"))
gripper_wheels = list((ROOT / "gripper/python/wheels/linux-x86_64").glob("*.whl"))
if len(arm_wheels) != 1:
    fail(f"expected one arm wheel, found {len(arm_wheels)}")
if len(gripper_wheels) != 1:
    fail(f"expected one gripper wheel, found {len(gripper_wheels)}")

riscv_wheels = []
for directory in ("python/wheels/linux-riscv64", "gripper/python/wheels/linux-riscv64"):
    wheels = list((ROOT / directory).glob("*.whl"))
    if len(wheels) != 1:
        fail(f"expected one RISC-V wheel in {directory}, found {len(wheels)}")
    riscv_wheels.extend(wheels)
for binary in (ROOT / "runtime/linux-riscv64/lib").glob("*.so*"):
    if binary.is_file():
        check_cross_platform_binary(binary, "RISC-V")

wheel_providers = {}
for wheel in arm_wheels + gripper_wheels + riscv_wheels:
    with zipfile.ZipFile(wheel) as archive, tempfile.TemporaryDirectory() as temp:
        names = archive.namelist()
        metadata_name = next((name for name in names if name.endswith(".dist-info/METADATA")), None)
        if metadata_name is None or not metadata_name.endswith(f"-{version}.dist-info/METADATA"):
            fail(f"wrong wheel metadata directory: {wheel.name}")
        elif f"Version: {version}\n" not in archive.read(metadata_name).decode():
            fail(f"wrong wheel package version: {wheel.name}")
        forbidden = [
            name for name in names
            if name.endswith((".a", ".h", ".hpp", ".cmake", ".pc"))
            or "rbdl_urdfreader_util" in name
            or name.startswith(("bin/", "include/", "lib/"))
        ]
        if forbidden:
            fail(f"development files in {wheel.name}: {forbidden[:5]}")
        archive.extractall(temp)
        extension = next(Path(temp).glob("*.so"), None)
        if extension is None:
            fail(f"missing Python extension in {wheel.name}")
            continue
        output = run("file", str(extension)).stdout
        if "stripped" not in output or "not stripped" in output:
            fail(f"wheel extension is not stripped: {wheel.name}")
        module = "onerogripper" if wheel.name.startswith("onerogripper-") else "oneroarm"
        expected_build = manifest['package_builds']['gripper_wheel' if module == 'onerogripper' else 'arm_wheel']
        wheel_metadata = archive.read(next(n for n in names if n.endswith('.dist-info/WHEEL'))).decode()
        if f'Build: {expected_build}\n' not in wheel_metadata or wheel.name.split('-')[2] != str(expected_build):
            fail(f"wheel build label differs from manifest: {wheel.name}")
        providers = {}
        for canonical in ('libstdc++.so.6', 'libgcc_s.so.1'):
            provider = Path(temp) / (module+'.libs') / canonical
            if not provider.is_file():
                fail(f"wheel missing canonical C++ runtime {canonical}: {wheel.name}")
                continue
            dynamic = run('readelf', '-d', str(provider)).stdout
            if f'[{canonical}]' not in dynamic or '(SONAME)' not in dynamic:
                fail(f"wheel runtime SONAME is not canonical: {wheel.name}/{canonical}")
            providers[canonical] = hashlib.sha256(provider.read_bytes()).hexdigest()
        for binary in Path(temp).rglob('*'):
            if binary.is_file() and binary.read_bytes()[:4] == b'\x7fELF':
                dynamic = run('readelf', '-d', str(binary)).stdout
                if re.search(r'\[lib(?:stdc\+\+|gcc_s)-', dynamic):
                    fail(f"wheel contains C++ runtime aliases: {wheel.name}/{binary.name}")
        architecture = 'linux-riscv64' if wheel in riscv_wheels else 'linux-x86_64'
        wheel_providers.setdefault(architecture, {})[module] = providers
        exports = run("nm", "-D", "--defined-only", str(extension))
        names_exported = {line.split()[-1] for line in exports.stdout.splitlines() if line.split()}
        if exports.returncode or names_exported != {f"PyInit_{module}"}:
            fail(f"wheel extension must only export PyInit_{module}: {wheel.name}")
        strings = run("strings", str(extension)).stdout
        if any(token in strings for token in ("/home/", "SDK_movec", "test_7k7k")):
            fail(f"internal path in wheel extension: {wheel.name}")
        if wheel in riscv_wheels:
            if "RISC-V" not in output or not wheel.name.endswith("-cp312-cp312-linux_riscv64.whl"):
                fail(f"wrong RISC-V wheel architecture or ABI: {wheel.name}")
            metadata = archive.read(next(name for name in names if name.endswith(".dist-info/METADATA"))).decode()
            if "Requires-Python: >=3.12,<3.13" not in metadata:
                fail(f"wrong RISC-V Python constraint: {wheel.name}")
            # Foreign ELF files are inspected here; execution is recorded by QEMU validation.
            for dependency in (Path(temp) / (module + ".libs")).glob("*.so*"):
                details = run("file", str(dependency)).stdout
                if "RISC-V" not in details or "not stripped" in details:
                    fail(f"wrong or unstripped wheel dependency: {wheel.name}/{dependency.name}")
            continue
        env = os.environ.copy()
        env.pop("LD_LIBRARY_PATH", None)
        ldd = run("ldd", str(extension), env=env)
        if ldd.returncode or "not found" in ldd.stdout:
            fail(f"wheel dependency is unresolved in {wheel.name}: {ldd.stdout}{ldd.stderr}")

for architecture, pair in wheel_providers.items():
    if pair.get('oneroarm') != pair.get('onerogripper'):
        fail(f"arm/gripper wheel C++ providers differ: {architecture}")
for relative in ('RISC_V_GUIDE.md', 'python/README.md', 'gripper/python/README.md'):
    text = (ROOT / relative).read_text()
    for module, field in (('主臂', 'arm_wheel'), ('独立夹爪', 'gripper_wheel')):
        for build in re.findall(module+r' wheel(?: 的)?(?:构建标签为| 构建标签为| 为) (\d+)', text):
            if int(build) != manifest['package_builds'][field]:
                fail(f"stale wheel build description: {relative}")

if not args.static_only:
    wheel_checks = [
        (arm_wheels[0] if arm_wheels else None, "oneroarm", ("OneroArm", "transform_pose")),
        (gripper_wheels[0] if gripper_wheels else None, "onerogripper", ("OneroGripper",)),
    ]
    for wheel, module, names in wheel_checks:
        if wheel is None:
            continue
        with tempfile.TemporaryDirectory() as temp:
            install = run(
                sys.executable, "-m", "pip", "install", "--no-index",
                "--no-deps", "--target", temp, str(wheel),
            )
            if install.returncode:
                fail(f"cannot install {wheel.name}: {install.stdout}{install.stderr}")
                continue
            code = f"import {module}; assert all(hasattr({module}, n) for n in {names!r})"
            env = os.environ.copy()
            env.pop("LD_LIBRARY_PATH", None)
            env["PYTHONPATH"] = temp
            imported = run(sys.executable, "-c", code, env=env)
            if imported.returncode:
                fail(f"cannot import {wheel.name}: {imported.stdout}{imported.stderr}")

    if len(arm_wheels) == 1 and len(gripper_wheels) == 1:
        with tempfile.TemporaryDirectory() as temp:
            install = run(
                sys.executable, "-m", "pip", "install", "--no-index",
                "--no-deps", "--target", temp,
                str(arm_wheels[0]), str(gripper_wheels[0]),
            )
            if install.returncode:
                fail(f"cannot install wheel pair: {install.stdout}{install.stderr}")
            else:
                env = os.environ.copy()
                env.pop("LD_LIBRARY_PATH", None)
                env["PYTHONPATH"] = temp
                env["PYTHONNOUSERSITE"] = "1"
                for order in ("arm-first", "gripper-first"):
                    imported = run(sys.executable, "-X", "faulthandler",
                                   str(ROOT / "tools/servo_regression.py"), "--import-order", order, env=env)
                    if imported.returncode:
                        fail(f"wheel offline regression failed ({order}): {imported.stdout}{imported.stderr}")
                    else:
                        print(f"PASS: wheel joint import and sustained simulation ({order})")

sums = ROOT / "SHA256SUMS"
if sums.exists():
    checked = run("sha256sum", "-c", str(sums))
    if checked.returncode:
        fail(f"SHA256SUMS verification failed: {checked.stdout}{checked.stderr}")

if args.evidence is not None:
    try:
        evidence = json.loads(args.evidence.read_text())
        ERRORS.extend(check_execution_evidence(ROOT, evidence, complete=not args.static_only))
    except (KeyError, ValueError, OSError, TypeError) as exc:
        fail(f"platform execution evidence unavailable: {exc}")

if ERRORS:
    for error in ERRORS:
        print("ERROR:", error, file=sys.stderr)
    raise SystemExit(1)
print("PASS: package metadata, public exports, dependencies and file inventory hashes")
if args.static_only:
    print("SKIPPED: wheel installation, single-module imports, both joint-import orders and sustained servo simulation")
    print("SKIPPED: complete target execution/evidence acceptance (file hashes alone do not prove execution)")
    print("Static checks passed; FULL RELEASE CHECKS: NOT RUN")
else:
    print("PASS: CPython 3.12 single-module imports, both joint-import orders and sustained servo simulation")
    print("PASS: all required native/QEMU execution evidence matches this package and test suite")
    print("FULL OFFLINE RELEASE CHECKS: PASSED (real hardware NOT tested)")
