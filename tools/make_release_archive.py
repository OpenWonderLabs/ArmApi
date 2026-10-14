#!/usr/bin/env python3
import argparse
import gzip
import platform
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = (ROOT / "VERSION").read_text().strip()
NAME = f"WoanArm_API_for_Users-{VERSION}-multiplatform"


def normalized(info: tarfile.TarInfo) -> tarfile.TarInfo:
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    return info


parser = argparse.ArgumentParser(description="Create the public SDK archive without Git history.")
parser.add_argument(
    "--output",
    type=Path,
    default=ROOT.parent / f"{NAME}.tar.gz",
)
parser.add_argument("--evidence", type=Path, help="separately retained execution evidence JSON")
args = parser.parse_args()
if platform.python_implementation() != "CPython" or sys.version_info[:2] != (3, 12):
    parser.error("Official archive creation requires CPython 3.12 and full offline release checks; "
                 "static-only acceptance is not allowed.")
if args.evidence is None:
    parser.error("Archive creation requires --evidence; execution records are not bundled with the SDK.")

# Only the reviewed checksum inventory is deliverable, as in source-package staging.
# Local builds and ignored working files must never enter a public archive.
paths = [ROOT / "SHA256SUMS"]
for line in (ROOT / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
    _, relative = line.split(maxsplit=1)
    rel = Path(relative)
    path = ROOT / rel
    if (rel.is_absolute() or ".." in rel.parts or ".git" in rel.parts
            or not path.resolve().is_relative_to(ROOT.resolve()) or not path.is_file()):
        raise SystemExit(f"Invalid release inventory path: {relative}")
    paths.append(path)
if len(set(paths)) != len(paths):
    raise SystemExit("Duplicate release inventory path")

for script in ("check_cpp_headers.py", "verify_release.py"):
    command = [sys.executable, str(ROOT / "tools" / script)]
    if script == "verify_release.py":
        command += ["--evidence", str(args.evidence.resolve())]
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode:
        parser.exit(1, f"Archive not created: {script} failed; complete offline acceptance is required.\n")
with args.output.open("wb") as raw:
    with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w", dereference=True) as archive:
            for path in sorted(paths):
                relative = path.relative_to(ROOT)
                archive.add(path, arcname=Path(NAME) / relative, recursive=False, filter=normalized)
print(args.output)
