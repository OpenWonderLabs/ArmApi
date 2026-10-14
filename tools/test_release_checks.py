#!/usr/bin/env python3
"""Regression tests for false-positive acceptance; no SDK or hardware required."""
import copy
import hashlib
import io
from enum import IntEnum
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import tarfile
from types import SimpleNamespace
import unittest
import zipfile
from unittest.mock import patch

import servo_regression as servo
import validate_platform as validation
from check_execution_evidence import check_execution_evidence
from promote_package_version import promote_package


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sdk-gate-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "VERSION").write_text("1.2.0\n")
        (self.root / "consumer.py").write_text("test suite\n")
        for key in validation.PLATFORMS:
            (self.root / f"{key}.bin").write_bytes(key.encode())
        self.addCleanup(patch.stopall)
        patch.object(validation, "artifacts", lambda root, key: {
            f"{key}.bin": validation.digest(root / f"{key}.bin")}).start()
        patch.object(validation, "inputs", lambda root, key: {
            "consumer.py": validation.digest(root / "consumer.py")}).start()
        self.evidence = {"sdk_version": "1.2.0"}
        for key, (group, mode, _, channel) in validation.PLATFORMS.items():
            record = {
                "status": "passed", "suite_version": validation.SUITE_VERSION,
                "execution_mode": mode, "hardware_connected": False,
                "artifact_sha256": validation.artifacts(self.root, key),
                "inputs_sha256": validation.inputs(self.root, key),
                "checks": {check: "passed" for check in (*validation.CHECKS,
                           "conda_joint_arm-first", "conda_joint_gripper-first")},
                "execution_log": {"id": "private-test-run", "sha256": "a" * 64},
                "python_checks": [{"python_minor": v, "status": "passed"} for v in
                                  (("3.10", "3.11", "3.12", "3.13") if channel else ("3.12",))],
                "native_board_validation": False,
                "environment": {"os":"test", "python":"3.12", "numpy":"2.2.6", "packages":[{"name":"numpy","version":"2.2.6"}], "inventory_source":"dpkg"},
            }
            self.evidence.setdefault(group, {})[key] = record

    def test_complete_record(self):
        self.assertEqual(validation.check_evidence(self.root, self.evidence), [])

    def test_missing_actual_dependencies_is_rejected(self):
        self.evidence['emulated_platform_checks']['linux-riscv64']['environment'] = None
        self.assertTrue(validation.check_evidence(self.root, self.evidence))

    def test_missing_recovery_and_numpy_execution_is_rejected(self):
        for name in ('servoj_timeout_recovery', 'numpy_import_orders'):
            value = self.evidence['native_platform_checks']['linux-x86_64']['checks'].pop(name)
            self.assertTrue(validation.check_evidence(self.root, self.evidence))
            self.evidence['native_platform_checks']['linux-x86_64']['checks'][name] = value

    def test_metadata_promotion_checks_all_runtime_files_and_preserves_history(self):
        self.workflow_snapshot()
        previous_inputs, previous_artifacts = validation.inputs, validation.artifacts
        patch.object(validation, "inputs", lambda root, key: {
            **previous_inputs(root, key), "VERSION": validation.digest(root / "VERSION")}).start()
        old_name = "oneroarm-1.2.0-3-cp312-cp312-linux_x86_64.whl"
        new_name = old_name.replace("1.2.0", "1.2.1")
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as archive:
            archive.writestr("oneroarm.so", b"unchanged runtime")
            archive.writestr("oneroarm-1.2.0.dist-info/METADATA", "Name: oneroarm\nVersion: 1.2.0\n")
        (self.root / old_name).write_bytes(payload.getvalue())
        patch.object(validation, "artifacts", lambda root, key: {
            **previous_artifacts(root, key), **({p.name: validation.digest(p)
                for p in root.glob("*.whl")} if key == "linux-x86_64" else {})}).start()
        for key, (group, *_) in validation.PLATFORMS.items():
            self.evidence[group][key].update(inputs_sha256=validation.inputs(self.root, key),
                                            artifact_sha256=validation.artifacts(self.root, key), sdk_version="1.2.0")
        source = self.root / "source.tar.gz"
        files = [p for p in self.root.rglob("*") if p.is_file()]
        with tarfile.open(source, "w:gz") as archive:
            for p in files:
                archive.add(p, arcname="WoanArm_API_for_Users-1.2.0-multiplatform/" + p.relative_to(self.root).as_posix())
        (self.root / old_name).unlink()
        converted = promote_package(payload.getvalue(), "1.2.0", "1.2.1")
        (self.root / new_name).write_bytes(converted)
        (self.root / "VERSION").write_text("1.2.1\n")
        self.evidence["sdk_version"] = "1.2.1"
        self.evidence["package_version_promotion"] = {
            "from_version": "1.2.0", "to_version": "1.2.1", "source_archive": str(source),
            "source_archive_sha256": validation.digest(source)}
        before = copy.deepcopy(self.evidence)
        self.assertEqual(check_execution_evidence(self.root, self.evidence), [])
        self.assertEqual(self.evidence, before)
        with zipfile.ZipFile(io.BytesIO(converted)) as archive:
            self.assertEqual(archive.read("oneroarm.so"), b"unchanged runtime")
            self.assertIn(b"Version: 1.2.1\n", archive.read("oneroarm-1.2.1.dist-info/METADATA"))
        (self.root / "consumer.py").write_text("changed executed code\n")
        self.assertTrue(check_execution_evidence(self.root, self.evidence))
        (self.root / "consumer.py").write_text("test suite\n")
        (self.root / new_name).write_bytes(converted + b"unexpected bytes")
        self.assertTrue(check_execution_evidence(self.root, self.evidence))
        (self.root / new_name).write_bytes(converted)
        (self.root / "linux-arm64.bin").write_bytes(b"changed runtime")
        self.assertTrue(check_execution_evidence(self.root, self.evidence))
        (self.root / "linux-arm64.bin").write_bytes(b"linux-arm64")
        self.evidence["package_version_promotion"]["source_archive_sha256"] = "0" * 64
        self.assertTrue(check_execution_evidence(self.root, self.evidence))

    def workflow_snapshot(self):
        relative = ".github/workflows/release-validation.yml"
        workflow = self.root / relative
        workflow.parent.mkdir(parents=True)
        original = "jobs:\n  target:\n    run: actual-tests\n\n  candidate-acceptance:\n    run: old-aggregation\n"
        workflow.write_text(original)
        patch.object(validation, "inputs", lambda root, key: {
            "consumer.py": validation.digest(root / "consumer.py"),
            relative: validation.digest(root / relative)}).start()
        for key, (group, *_) in validation.PLATFORMS.items():
            self.evidence[group][key]["inputs_sha256"] = validation.inputs(self.root, key)
        self.evidence["aggregation_only_workflow_snapshot"] = {
            "content": original, "sha256": validation.digest(workflow)}
        return workflow, original

    def test_aggregation_only_change_preserves_original_evidence(self):
        workflow, original = self.workflow_snapshot()
        workflow.write_text(original.replace("old-aggregation", "external-evidence"))
        before = copy.deepcopy(self.evidence)
        self.assertEqual(check_execution_evidence(self.root, self.evidence), [])
        self.assertEqual(self.evidence, before)
        (self.root / "consumer.py").write_text("changed consumer\n")
        self.assertTrue(check_execution_evidence(self.root, self.evidence))

    def test_workflow_snapshot_cannot_hide_platform_job_change_or_tampering(self):
        workflow, original = self.workflow_snapshot()
        workflow.write_text(original.replace("actual-tests", "changed-tests"))
        self.assertTrue(check_execution_evidence(self.root, self.evidence))
        workflow.write_text(original)
        self.evidence["aggregation_only_workflow_snapshot"]["sha256"] = "0" * 64
        self.assertTrue(check_execution_evidence(self.root, self.evidence))

    def test_workflow_snapshot_must_match_recorded_input(self):
        self.workflow_snapshot()
        record = self.evidence["native_platform_checks"]["linux-arm64"]
        record["inputs_sha256"][".github/workflows/release-validation.yml"] = "0" * 64
        self.assertTrue(check_execution_evidence(self.root, self.evidence))

    def test_workflow_snapshot_rejects_appended_jobs_and_root_keys(self):
        workflow, original = self.workflow_snapshot()
        appended = (
            "\n  added-execution-job:\n    run: changed-platform-execution\n",
            "\n  candidate-acceptance:\n    run: duplicate-job\n",
            "\npermissions:\n  contents: write\n",
            "\n---\njobs: {}\n",
        )
        for tail in appended:
            with self.subTest(tail=tail):
                workflow.write_text(original + tail)
                self.assertTrue(check_execution_evidence(self.root, self.evidence))
        workflow.write_text(original + "\n# harmless comment\n")
        self.assertEqual(check_execution_evidence(self.root, self.evidence), [])

    def test_documentation_update_requires_both_snapshots_and_cannot_change_code(self):
        self.workflow_snapshot()
        document = self.root / "consumer.md"
        original = "install old-package.whl\n"
        document.write_text(original)
        previous_inputs = validation.inputs
        patch.object(validation, "inputs", lambda root, key: {
            **previous_inputs(root, key), "consumer.md": validation.digest(root / "consumer.md")}).start()
        for key, (group, *_) in validation.PLATFORMS.items():
            self.evidence[group][key]["inputs_sha256"] = validation.inputs(self.root, key)
        document.write_text("install current-package.whl\n")
        update = {"executed_content": original,
                  "executed_sha256": hashlib.sha256(original.encode()).hexdigest(),
                  "current_sha256": validation.digest(document)}
        self.evidence["documentation_only_updates"] = {"consumer.md": update}
        before = copy.deepcopy(self.evidence)
        self.assertEqual(check_execution_evidence(self.root, self.evidence), [])
        self.assertEqual(self.evidence, before)
        for field in ("executed_content", "executed_sha256", "current_sha256"):
            broken = copy.deepcopy(self.evidence)
            broken["documentation_only_updates"]["consumer.md"][field] = "tampered"
            self.assertTrue(check_execution_evidence(self.root, broken))
        self.evidence["documentation_only_updates"] = {"consumer.py": update}
        self.assertTrue(check_execution_evidence(self.root, self.evidence))

    def test_each_platform_rejects_changed_artifact_and_missing_hash(self):
        for key, (group, *_) in validation.PLATFORMS.items():
            with self.subTest(platform=key):
                artifact = self.root / f"{key}.bin"
                previous = artifact.read_bytes()
                artifact.write_bytes(previous + b"changed")
                self.assertTrue(validation.check_evidence(self.root, self.evidence, complete=False))
                artifact.write_bytes(previous)
                missing = copy.deepcopy(self.evidence)
                missing[group][key]["artifact_sha256"] = {}
                self.assertTrue(validation.check_evidence(self.root, missing))

    def test_changed_consumer_requires_new_execution(self):
        (self.root / "consumer.py").write_text("changed checks\n")
        self.assertTrue(validation.check_evidence(self.root, self.evidence))
        self.assertEqual(validation.check_evidence(self.root, self.evidence, complete=False), [])

    def test_incomplete_or_malformed_records_fail_closed(self):
        mutations = (
            ("status", "pending"), ("suite_version", 1), ("hardware_connected", True),
            ("execution_mode", "QEMU user mode"), ("checks", {}), ("checks", []),
            ("artifact_sha256", []), ("execution_log", {}), ("execution_log", None),
            ("execution_log", {"id": "https://private/log", "sha256": "a" * 64}),
            ("python_checks", [{"python_minor": "3.12", "status": "passed"}]),
            ("python_checks", None),
        )
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                broken = copy.deepcopy(self.evidence)
                broken["native_platform_checks"]["linux-x86_64"][field] = value
                self.assertTrue(validation.check_evidence(self.root, broken))

    def test_no_qemu_to_native_promotion(self):
        self.evidence["emulated_platform_checks"]["linux-riscv64"]["native_board_validation"] = True
        self.assertTrue(validation.check_evidence(self.root, self.evidence))


class InterpreterTests(unittest.TestCase):
    def test_archive_requires_successful_full_gate(self):
        tools = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix="sdk-archive-failure-") as temp:
            output = Path(temp) / "must-not-exist.tar.gz"
            evidence = Path(temp) / "execution.json"
            results = [subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 1)]
            with patch.object(sys, "version_info", (3, 12, 0, "final", 0)), \
                    patch.object(sys, "argv", ["make_release_archive.py", "--output", str(output),
                                               "--evidence", str(evidence)]), \
                    patch("platform.python_implementation", return_value="CPython"), \
                    patch("subprocess.run", side_effect=results) as calls, \
                    self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(tools / "make_release_archive.py"), run_name="__main__")
            self.assertEqual(stopped.exception.code, 1)
            self.assertFalse(output.exists())
            self.assertEqual(calls.call_args_list[-1].args[0],
                             [sys.executable, str(tools / "verify_release.py"), "--evidence", str(evidence)])

    def test_missing_separate_evidence_rejected_before_checks(self):
        tools = Path(__file__).resolve().parent
        for script in ("verify_release.py", "make_release_archive.py"):
            with self.subTest(script=script), \
                    patch.object(sys, "version_info", (3, 12, 0, "final", 0)), \
                    patch.object(sys, "argv", [script]), \
                    patch("platform.python_implementation", return_value="CPython"), \
                    patch("subprocess.run") as calls, \
                    self.assertRaises(SystemExit) as stopped:
                runpy.run_path(str(tools / script), run_name="__main__")
            self.assertEqual(stopped.exception.code, 2)
            calls.assert_not_called()

    def test_non_target_interpreter_rejected_before_checks_or_archive(self):
        tools = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(prefix="sdk-archive-gate-") as temp:
            output = Path(temp) / "must-not-exist.tar.gz"
            for script in ("verify_release.py", "make_release_archive.py"):
                arguments = [str(tools / script)]
                if script == "make_release_archive.py":
                    arguments += ["--output", str(output)]
                code = ("import runpy, sys; "
                        f"sys.path.insert(0, {str(tools)!r}); sys.argv={arguments!r}; "
                        "sys.version_info=(3,10,12,'final',0); "
                        f"runpy.run_path({str(tools / script)!r}, run_name='__main__')")
                result = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("CPython 3.12", result.stderr)
                self.assertNotIn("PASSED", result.stdout)
            self.assertFalse(output.exists())


class State(IntEnum):
    HOLDING = 1
    FAULT = 2


class ServoOracleTests(unittest.TestCase):
    def setUp(self):
        self.target = [0.01] + [0.0] * 6
        self.before = SimpleNamespace(accepted_sequence=0, sent_frame_count=0, otg_update_count=0)
        self.status = SimpleNamespace(state=State.HOLDING, accepted_sequence=20, applied_sequence=10,
                                      sent_frame_count=20, otg_update_count=20, last_error=0,
                                      limit_flags=0, commanded_q=self.target)
        self.arm = SimpleNamespace(get_servoj_status=lambda: self.status,
                                   get_arm_state_from_motor=lambda: SimpleNamespace(positions=self.target))

    def arrived(self, status):
        return servo.joint_applied(status, self.before, self.target, self.target, State.HOLDING)

    def test_accepted_and_even_matching_feedback_are_insufficient(self):
        self.assertTrue(self.arrived(self.status))
        for field, value in (("applied_sequence", 0), ("sent_frame_count", 0), ("otg_update_count", 0),
                             ("last_error", -1), ("state", State.FAULT), ("commanded_q", [0.0] * 7)):
            with self.subTest(field=field), patch.object(self.status, field, value):
                self.assertFalse(self.arrived(self.status))
        self.status.applied_sequence = 0
        with self.assertRaisesRegex(AssertionError, "timeout=.*applied_sequence.*feedback"):
            servo.wait_for("accepted but unapplied", self.arm, "servoj", self.arrived, timeout=0.02)

    def test_update_failure_and_fault_include_diagnostics(self):
        with self.assertRaisesRegex(AssertionError, "rc=-8.*accepted_sequence.*limit_flags.*feedback"):
            servo.wait_for("update failure", self.arm, "servoj", self.arrived, update=lambda: -8)
        self.status.state = State.FAULT
        with self.assertRaisesRegex(AssertionError, "FAULT.*applied_sequence.*feedback"):
            servo.wait_for("fault", self.arm, "servoj", self.arrived)


if __name__ == "__main__":
    unittest.main()
