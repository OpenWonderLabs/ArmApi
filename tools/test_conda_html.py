"""Run with python3 tools/test_conda_html.py; no packages are installed."""
import hashlib
import json
import tempfile
from pathlib import Path

from verify_conda_html import check_conda_html


with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    name = "oneroarm-1.2.0-py312_3.conda"
    payload = b"test package"
    (root / name).write_bytes(payload)
    sha, md5 = hashlib.sha256(payload).hexdigest(), hashlib.md5(payload).hexdigest()
    metadata = {"size": len(payload), "sha256": sha, "md5": md5}
    (root / "repodata.json").write_text(json.dumps({"packages.conda": {name: metadata}}))
    page = root / "index.html"
    valid = (f'<table><tr><td><a href="{name}">{name}</a></td>'
             f'<td>{len(payload)}</td><td>{sha}</td><td>{md5}</td></tr></table>')
    page.write_text(valid)
    assert check_conda_html(root) == []
    page.write_text(valid.replace(f'href="{name}"', 'href="oneroarm-1.1.0-py312_2.conda"'))
    assert any("broken" in error for error in check_conda_html(root))
    page.write_text(valid.replace(sha, "0" * 64))
    assert any("checksums" in error for error in check_conda_html(root))
    page.unlink()
    assert any("cannot verify" in error for error in check_conda_html(root))

print("Conda HTML regression checks passed")
