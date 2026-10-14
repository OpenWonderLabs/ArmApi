"""Check execution records, including changes confined to final CI aggregation."""
import copy
import hashlib
import re
import tarfile
from pathlib import Path

from validate_platform import check_evidence
from promote_package_version import promote_package


def promoted_evidence(root, evidence):
    promotion = evidence["package_version_promotion"]
    old, new = promotion["from_version"], promotion["to_version"]
    if (not all(isinstance(v, str) and re.fullmatch(r"\d+\.\d+\.\d+", v) for v in (old, new))
            or old == new or evidence.get("sdk_version") != new
            or (root / "VERSION").read_text().strip() != new):
        raise ValueError("package promotion versions differ")
    source = Path(promotion["source_archive"])
    if hashlib.sha256(source.read_bytes()).hexdigest() != promotion["source_archive_sha256"]:
        raise ValueError("source archive checksum differs")
    prefix = f"WoanArm_API_for_Users-{old}-multiplatform/"
    with tarfile.open(source) as archive:
        files = {}
        for member in archive:
            if not member.isfile() or not member.name.startswith(prefix):
                raise ValueError("invalid source archive member")
            relative = member.name[len(prefix):]
            if Path(relative).is_absolute() or ".." in Path(relative).parts or relative in files:
                raise ValueError("invalid source archive path")
            files[relative] = archive.extractfile(member).read()
    if files["VERSION"].decode().strip() != old:
        raise ValueError("source archive version differs")
    adjusted = copy.deepcopy(evidence)
    adjusted["sdk_version"] = new
    expected_packages = {}
    for group in ("native_platform_checks", "emulated_platform_checks"):
        for record in adjusted.get(group, {}).values():
            if record.get("sdk_version") != old:
                raise ValueError("executed platform version differs from source archive")
            hashes = {}
            for relative, checksum in record["artifact_sha256"].items():
                before = files[relative]
                if hashlib.sha256(before).hexdigest() != checksum:
                    raise ValueError("source archive does not match executed artifact")
                renamed = relative
                if Path(relative).suffix in (".whl", ".conda"):
                    renamed = relative.replace(f"-{old}-", f"-{new}-")
                    if relative not in expected_packages:
                        expected_packages[relative] = promote_package(before, old, new)
                    before = expected_packages[relative]
                current = root / renamed
                if (not current.resolve().is_relative_to(root.resolve()) or not current.is_file()
                        or current.read_bytes() != before):
                    raise ValueError("promotion changed runtime files or unexpected package metadata")
                hashes[renamed] = hashlib.sha256(before).hexdigest()
            record["artifact_sha256"] = hashes
            if record["inputs_sha256"].get("VERSION") != hashlib.sha256(files["VERSION"]).hexdigest():
                raise ValueError("source version does not match executed input")
            record["inputs_sha256"]["VERSION"] = hashlib.sha256((root / "VERSION").read_bytes()).hexdigest()
    return adjusted


def check_execution_evidence(root, evidence, complete=True):
    if isinstance(evidence, dict) and "package_version_promotion" in evidence:
        try:
            evidence = promoted_evidence(root, evidence)
        except (KeyError, TypeError, ValueError, OSError) as exc:
            return [f"invalid metadata-only package promotion: {exc}"]
    snapshot = evidence.get("aggregation_only_workflow_snapshot") if isinstance(evidence, dict) else None
    if not complete or snapshot is None:
        return check_evidence(root, evidence, complete=complete)
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("content"), str):
        return ["invalid executed workflow snapshot"]
    original = snapshot["content"]
    original_hash = hashlib.sha256(original.encode()).hexdigest()
    if original_hash != snapshot.get("sha256"):
        return ["executed workflow snapshot checksum differs"]
    workflow_relative = ".github/workflows/release-validation.yml"
    current = (root / workflow_relative).read_text()
    boundary = "\n  candidate-acceptance:\n"
    before, separator, original_tail = original.partition(boundary)
    now, current_separator, current_tail = current.partition(boundary)
    # The exception is limited to the final job, never additional jobs or root keys.
    extra_nodes = any(re.search(r"(?m)^[ \t]{0,3}[^ \t\r\n#]", tail)
                      for tail in (original_tail, current_tail))
    if not separator or not current_separator or before != now or extra_nodes:
        return ["executed platform workflow changed; rerun target acceptance"]
    updates = evidence.get("documentation_only_updates", {})
    if not isinstance(updates, dict):
        return ["invalid documentation-only update mapping"]
    for relative, update in updates.items():
        if not isinstance(relative, str) or not isinstance(update, dict):
            return ["invalid documentation-only update"]
        path = root / relative
        if (Path(relative).is_absolute() or ".." in Path(relative).parts
                or path.suffix.lower() != ".md" or not path.is_file()
                or not path.resolve().is_relative_to(root.resolve())):
            return ["documentation-only updates must be Markdown files inside the SDK"]
        content = update.get("executed_content")
        if (not isinstance(content, str)
                or hashlib.sha256(content.encode()).hexdigest() != update.get("executed_sha256")
                or hashlib.sha256(path.read_bytes()).hexdigest() != update.get("current_sha256")):
            return ["documentation update does not match original/current content hashes"]
    # Preserve historical records; only the non-executing aggregate job may differ.
    adjusted = copy.deepcopy(evidence)
    for group in ("native_platform_checks", "emulated_platform_checks"):
        records = adjusted.get(group, {})
        if not isinstance(records, dict):
            return ["invalid platform evidence structure"]
        for record in records.values():
            hashes = record.get("inputs_sha256", {}) if isinstance(record, dict) else {}
            if not isinstance(hashes, dict) or hashes.get(workflow_relative) != original_hash:
                return ["platform record does not match executed workflow snapshot"]
            hashes[workflow_relative] = hashlib.sha256(current.encode()).hexdigest()
            for document, update in updates.items():
                if hashes.get(document) != update["executed_sha256"]:
                    return ["document update does not match executed platform input"]
                hashes[document] = update["current_sha256"]
    return check_evidence(root, adjusted, complete=complete)
