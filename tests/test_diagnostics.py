# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))
import diagnostics  # noqa: E402
import diagnostics_git  # noqa: E402
import diagnostics_inputs  # noqa: E402
import lab_config  # noqa: E402
import runtime_evidence  # noqa: E402
import platform_runtime_evidence  # noqa: E402
import source_lock  # noqa: E402


class DiagnosticsTests(unittest.TestCase):
    def passing_platform_diagnostic(self) -> dict[str, object]:
        document, _ = diagnostics.command_document(
            ROOT, "evidence", "platform-arm64"
        )
        document["checks"] = [
            diagnostics.check(check_id, "pass").object()
            for check_id in diagnostics.SEQUENCES["evidence"]
        ]
        document["result"] = "pass"
        document["data"] = {
            "evidence": {
                "kind": platform_runtime_evidence.KIND,
                "schema_version": 1,
                "project": {
                    "version": document["project"]["version"],
                    "revision": document["project"]["revision"],
                    "dirty": False,
                },
                "build": {
                    "machine": "qemu-edu-platform-arm64",
                    "image": "qemu-edu-image",
                    "testimage_exit_code": 0,
                },
                "result": "passed",
                "summary": {
                    "total": 9,
                    "passed": 9,
                    "failed": 0,
                    "skipped": 0,
                    "errors": 0,
                    "expected_failures": 0,
                    "unknown": 0,
                },
                "native_input_sha256": "1" * 64,
                "source_lock_sha256": "2" * 64,
                "file_sha256": "3" * 64,
            },
            "inputs": {
                "lab_binding": "bound",
                "lab_index_sha256": document["lab"]["index_sha256"],
                "lab_manifest_sha256": document["lab"]["manifest_sha256"],
            },
            "subject_matches_head": True,
        }
        diagnostics.validate_document(document)
        return document

    def test_aggregate_precedence_is_total(self) -> None:
        passed = diagnostics.check("project.version", "pass")
        warning = diagnostics.check("repository.clean", "warning")
        optional_unavailable = diagnostics.check("repository.clean", "unavailable")
        required_unavailable = diagnostics.check("project.version", "unavailable")
        failed = diagnostics.check("project.version", "fail")
        self.assertEqual(("pass", 0), diagnostics.aggregate([passed]))
        self.assertEqual(("warning", 0), diagnostics.aggregate([passed, warning]))
        self.assertEqual(("warning", 0), diagnostics.aggregate([passed, optional_unavailable]))
        self.assertEqual(("unavailable", 3), diagnostics.aggregate([warning, required_unavailable]))
        self.assertEqual(("fail", 1), diagnostics.aggregate([required_unavailable, failed]))

    def test_project_version_contract_is_general_ascii_semver(self) -> None:
        for value in ("0.5.0-dev", "0.6.1", "0.6.12-rc.1+build.2", "0.7.0"):
            self.assertIsNotNone(diagnostics.PROJECT_VERSION.fullmatch(value))
        for value in (
            "0.6.01",
            "0.6.1-01",
            "0.6.1\u0661",
            "0.6.1-\u0661",
            "0.6.1\n",
        ):
            self.assertIsNone(diagnostics.PROJECT_VERSION.fullmatch(value))

    def test_semantic_validator_rejects_summary_and_aggregate_drift(self) -> None:
        document, _ = diagnostics.command_document(ROOT, "inspect", "pci-x86-64")
        diagnostics.validate_document(document)
        changed = copy.deepcopy(document)
        changed["checks"][0]["summary"] = "Project version is unavailable."
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)
        changed = copy.deepcopy(document)
        changed["result"] = "fail"
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)
        changed = copy.deepcopy(document)
        changed["schema_version"] = True
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)
        changed = copy.deepcopy(document)
        changed["checks"][0]["required"] = 1
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

    def test_passing_data_validator_is_closed_and_typed(self) -> None:
        document, _ = diagnostics.command_document(ROOT, "inspect", None)
        self.assertEqual("pass", document["result"])
        data = document["data"]
        diagnostics.validate_pass_data("inspect", data)
        for mutation in (
            {**data, "source_lock_sha256": "wrong"},
            {**data, "sources": []},
            {**data, "extra": True},
        ):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                diagnostics.validate_pass_data("inspect", mutation)

    def test_semantic_validator_rejects_passing_null_identity_and_data(self) -> None:
        document, _ = diagnostics.command_document(ROOT, "status", None)
        document["checks"][-1] = diagnostics.check("repository.clean", "pass").object()
        document["result"] = "pass"
        document["project"]["dirty"] = False
        diagnostics.validate_document(document)
        changed = copy.deepcopy(document)
        changed["project"]["dirty"] = True
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)
        changed = copy.deepcopy(document)
        changed["project"] = {
            "name": diagnostics.PROJECT_NAME,
            "version": None,
            "revision": None,
            "dirty": None,
        }
        changed["lab"]["index_sha256"] = None
        changed["lab"]["manifest_sha256"] = None
        changed["data"] = {
            "active_task": None,
            "source_lock": None,
            "selected_lab": None,
        }
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

    def test_semantic_validator_rejects_malformed_nested_command_data(self) -> None:
        inspect, _ = diagnostics.command_document(ROOT, "inspect", None)
        mutations = []
        changed = copy.deepcopy(inspect)
        changed["data"]["release"] = {"secret": "/home/alice/token=supersecret"}
        mutations.append(changed)
        changed = copy.deepcopy(inspect)
        changed["data"]["build"]["build_dir"] = "/home/alice/token=supersecret"
        mutations.append(changed)
        changed = copy.deepcopy(inspect)
        changed["data"]["sources"] = []
        mutations.append(changed)
        changed = copy.deepcopy(inspect)
        changed["data"]["source_lock_sha256"] = "wrong"
        mutations.append(changed)

        status, _ = diagnostics.command_document(ROOT, "status", None)
        changed = copy.deepcopy(status)
        changed["data"]["source_lock"] = "arbitrary"
        mutations.append(changed)
        changed = copy.deepcopy(status)
        changed["data"]["extra"] = True
        mutations.append(changed)

        for mutation in mutations:
            with self.subTest(command=mutation["command"]), self.assertRaises(ValueError):
                diagnostics.validate_document(mutation)

    def test_projection_string_bounds_and_path_grammar_match_inputs(self) -> None:
        self.assertTrue(
            diagnostics.valid_build_directory("build-" + "a" * 4090)
        )
        self.assertFalse(
            diagnostics.valid_build_directory("build-" + "a" * 4091)
        )
        inspect, _ = diagnostics.command_document(ROOT, "inspect", None)
        for layer in (
            "layers/\x1bprivate-token",
            "layers/\x00private-token",
            "layers/priváte",
            "layers/private\ud800",
            "a" * 4097,
        ):
            with self.subTest(layer=ascii(layer)):
                changed = copy.deepcopy(inspect)
                changed["data"]["build"]["layers"][0] = layer
                with self.assertRaises(ValueError):
                    diagnostics.validate_document(changed)

    def test_semantic_validator_rejects_identity_and_evidence_drift(self) -> None:
        inspect, _ = diagnostics.command_document(ROOT, "inspect", None)
        changed = copy.deepcopy(inspect)
        changed["data"]["release"]["project_version"] = "9.9.9"
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

        baseline = self.passing_platform_diagnostic()
        mutations = []
        changed = copy.deepcopy(baseline)
        changed["data"]["evidence"]["result"] = "failed"
        mutations.append(changed)
        changed = copy.deepcopy(baseline)
        changed["data"]["evidence"]["summary"]["failed"] = 1
        mutations.append(changed)
        changed = copy.deepcopy(baseline)
        changed["data"]["evidence"]["summary"]["total"] = 1
        changed["data"]["evidence"]["summary"]["passed"] = 1
        mutations.append(changed)
        changed = copy.deepcopy(baseline)
        changed["data"]["evidence"]["result"] = "failed"
        changed["data"]["evidence"]["summary"]["passed"] = 8
        mutations.append(changed)
        changed = copy.deepcopy(baseline)
        changed["data"]["evidence"]["project"]["revision"] = "f" * 40
        mutations.append(changed)
        changed = copy.deepcopy(baseline)
        changed["data"]["inputs"]["lab_index_sha256"] = "f" * 64
        mutations.append(changed)
        changed = copy.deepcopy(baseline)
        changed["data"]["inputs"] = {
            "lab_binding": "not-recorded",
            "lab_index_sha256": None,
            "lab_manifest_sha256": None,
        }
        mutations.append(changed)
        for mutation in mutations:
            with self.assertRaises(ValueError):
                diagnostics.validate_document(mutation)

        changed = copy.deepcopy(baseline)
        changed["checks"][7] = diagnostics.check(
            "evidence.result", "fail"
        ).object()
        changed["checks"][9] = diagnostics.check(
            "evidence.subject", "unavailable"
        ).object()
        changed["result"] = "fail"
        changed["data"]["subject_matches_head"] = None
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

        changed["data"]["evidence"]["result"] = "failed"
        changed["data"]["evidence"]["summary"]["passed"] = 8
        changed["data"]["evidence"]["summary"]["failed"] = 1
        diagnostics.validate_document(changed)

    def test_doctor_binds_evidence_revision_to_subject_check(self) -> None:
        source = self.passing_platform_diagnostic()
        doctor, _ = diagnostics.command_document(ROOT, "doctor", "platform-arm64")
        doctor["checks"] = [
            diagnostics.check(check_id, "pass").object()
            for check_id in diagnostics.SEQUENCES["doctor"]
        ]
        doctor["result"] = "pass"
        doctor["data"] = {
            "active_task": doctor["data"]["active_task"],
            "evidence": copy.deepcopy(source["data"]["evidence"]),
        }
        diagnostics.validate_document(doctor)

        changed = copy.deepcopy(doctor)
        changed["data"]["evidence"]["project"]["revision"] = "f" * 40
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

        changed["checks"][17] = diagnostics.check(
            "evidence.subject", "warning"
        ).object()
        changed["result"] = "warning"
        diagnostics.validate_document(changed)
        changed["data"]["evidence"]["project"]["revision"] = doctor["project"]["revision"]
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

    def test_semantic_validator_rejects_impossible_dependency_states(self) -> None:
        inspect, _ = diagnostics.command_document(ROOT, "inspect", None)
        changed = copy.deepcopy(inspect)
        changed["checks"][2] = diagnostics.check(
            "inputs.source-lock", "fail"
        ).object()
        changed["result"] = "fail"
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

        changed = copy.deepcopy(inspect)
        changed["checks"][4] = diagnostics.check(
            "lab.selection", "unavailable"
        ).object()
        changed["result"] = "unavailable"
        changed["lab"]["manifest_sha256"] = None
        changed["data"] = {
            "release": None,
            "sources": None,
            "build": None,
            "emulator": None,
            "runtime": None,
            "source_lock_sha256": None,
        }
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

        baseline = self.passing_platform_diagnostic()
        changed = copy.deepcopy(baseline)
        for index, check_id in enumerate(
            ("evidence.file", "evidence.document", "evidence.result", "evidence.inputs"),
            start=5,
        ):
            changed["checks"][index] = diagnostics.check(
                check_id, "unavailable"
            ).object()
        changed["result"] = "unavailable"
        changed["data"] = {
            "evidence": None,
            "inputs": None,
            "subject_matches_head": True,
        }
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

        changed = copy.deepcopy(baseline)
        for index, check_id in enumerate(
            ("evidence.document", "evidence.result", "evidence.inputs"),
            start=6,
        ):
            changed["checks"][index] = diagnostics.check(
                check_id, "unavailable"
            ).object()
        changed["checks"][9] = diagnostics.check(
            "evidence.subject", "unavailable"
        ).object()
        changed["result"] = "unavailable"
        changed["data"] = {
            "evidence": None,
            "inputs": None,
            "subject_matches_head": None,
        }
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

        changed = copy.deepcopy(baseline)
        changed["checks"][7] = diagnostics.check(
            "evidence.result", "unavailable"
        ).object()
        changed["checks"][9] = diagnostics.check(
            "evidence.subject", "unavailable"
        ).object()
        changed["result"] = "unavailable"
        changed["data"]["subject_matches_head"] = None
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

        changed = copy.deepcopy(baseline)
        changed["checks"][8] = diagnostics.check(
            "evidence.inputs", "unavailable"
        ).object()
        changed["result"] = "unavailable"
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

        changed = copy.deepcopy(baseline)
        changed["checks"][9] = diagnostics.check(
            "evidence.subject", "unavailable"
        ).object()
        changed["result"] = "warning"
        changed["data"]["subject_matches_head"] = None
        with self.assertRaises(ValueError):
            diagnostics.validate_document(changed)

    def test_semantic_validator_binds_cached_git_states(self) -> None:
        statuses = {
            "repository.git": "pass",
            "tool.git": "unavailable",
        }
        with self.assertRaises(ValueError):
            diagnostics.validate_state_transitions(statuses)
        statuses = {
            "repository.git": "unavailable",
            "tool.git": "pass",
        }
        with self.assertRaises(ValueError):
            diagnostics.validate_state_transitions(statuses)
        statuses = {
            "repository.git": "fail",
            "tool.git": "unavailable",
        }
        with self.assertRaises(ValueError):
            diagnostics.validate_state_transitions(statuses)
        for repository_state, tool_state in (
            ("pass", "pass"),
            ("unavailable", "unavailable"),
            ("fail", "pass"),
            ("fail", "fail"),
        ):
            diagnostics.validate_state_transitions(
                {
                    "repository.git": repository_state,
                    "tool.git": tool_state,
                }
            )

    def test_catalog_default_and_safe_future_ids_are_core_authority(self) -> None:
        document, _ = diagnostics.command_document(ROOT, "inspect", None)
        self.assertEqual("pci-x86-64", document["lab"]["id"])
        changed = copy.deepcopy(document)
        changed["lab"]["id"] = "future-riscv"
        diagnostics.validate_document(changed)
        with self.assertRaises(diagnostics.DiagnosticArgumentError):
            diagnostics.command_document(ROOT, "inspect", "future-riscv")
        with self.assertRaises(diagnostics.DiagnosticArgumentError):
            diagnostics.command_document(ROOT, "inspect", "../../private")
        with self.assertRaises(diagnostics.DiagnosticArgumentError):
            diagnostics.command_document(ROOT, "inspect", "future-riscv\n")
        with self.assertRaises(diagnostics.DiagnosticArgumentError):
            diagnostics.Context(ROOT, 7)  # type: ignore[arg-type]
        oversized = "a" * (lab_config.MAX_STRING_LENGTH + 1)
        with patch.object(diagnostics, "read_regular") as read:
            with self.assertRaises(diagnostics.DiagnosticArgumentError):
                diagnostics.command_document(ROOT, "inspect", oversized)
        read.assert_not_called()

    def test_core_selects_a_synthetic_third_catalog_lab(self) -> None:
        source_raw = (ROOT / "config/sources.lock.json").read_bytes()
        source_data, _ = source_lock.parse_lock_bytes(source_raw)
        index = json.loads((ROOT / "config/labs/index.json").read_bytes())
        manifest_paths = [entry["manifest"] for entry in index["labs"]]
        manifest_bytes = {
            relative: (ROOT / relative).read_bytes() for relative in manifest_paths
        }
        future = json.loads(manifest_bytes[index["labs"][0]["manifest"]])
        future["id"] = "future-riscv"
        future["description"] = "Synthetic future catalog fixture."
        future["build"]["build_dir"] = "build-future"
        future["build"]["machine"] = "qemu-edu-future"
        future_relative = "config/labs/future-riscv.json"
        future_raw = (
            json.dumps(future, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        index["labs"].append(
            {
                "id": "future-riscv",
                "manifest": future_relative,
                "sha256": hashlib.sha256(future_raw).hexdigest(),
            }
        )
        index_raw = (
            json.dumps(index, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        manifest_bytes[future_relative] = future_raw
        catalog, _, manifests, _ = lab_config.read_catalog_bytes(
            index_raw, manifest_bytes, source_data
        )
        self.assertEqual("pci-x86-64", catalog["default_lab"])
        self.assertIn("future-riscv", manifests)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "config/labs").mkdir(parents=True)
            (root / "config/sources.lock.json").write_bytes(source_raw)
            (root / "config/labs/index.json").write_bytes(index_raw)
            for relative, raw in manifest_bytes.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            ctx = diagnostics.Context(root, "future-riscv")
            self.assertEqual("pass", ctx.source_lock().status)
            self.assertEqual("pass", ctx.lab_catalog().status)
            self.assertEqual("pass", ctx.selection().status)
            self.assertEqual("future-riscv", ctx.manifest["id"])

    def test_json_bytes_are_stable_utf8_lf(self) -> None:
        document, _ = diagnostics.command_document(ROOT, "inspect", "platform-arm64")
        first = diagnostics.json_bytes(document)
        second = diagnostics.json_bytes(document)
        self.assertEqual(first, second)
        self.assertTrue(first.endswith(b"\n"))
        self.assertNotIn(b"\r\n", first)
        self.assertEqual(document, json.loads(first))

    def test_inspect_source_order_is_canonical_not_lock_array_order(self) -> None:
        ctx = diagnostics.Context(ROOT, "pci-x86-64")
        self.assertEqual("pass", ctx.project_version().status)
        self.assertEqual("pass", ctx.source_lock().status)
        self.assertEqual("pass", ctx.lab_catalog().status)
        self.assertEqual("pass", ctx.selection().status)
        assert ctx.lock is not None
        ctx.lock["sources"].reverse()
        projection = diagnostics.inspect_projection(ctx)
        self.assertEqual(
            list(diagnostics.SOURCE_ORDER),
            [source["id"] for source in projection["sources"]],
        )

    def test_byte_parsers_reject_duplicate_nonfinite_and_surrogate_json(self) -> None:
        bad = (
            b'{"schema_version":1,"schema_version":1}',
            b'{"value":NaN}',
            b'{"value":"\\uDEAD"}',
        )
        for raw in bad:
            with self.subTest(raw=raw):
                with self.assertRaises((source_lock.LockError, runtime_evidence.EvidenceError, lab_config.LabError)):
                    if b"schema_version" in raw:
                        source_lock.parse_lock_bytes(raw)
                    elif b"NaN" in raw:
                        runtime_evidence.parse_object_bytes(raw)
                    else:
                        lab_config.parse_json_bytes(raw, "fixture")

    def test_json_shape_limits_apply_before_semantic_validation(self) -> None:
        nested: object = "value"
        for _ in range(65):
            nested = [nested]
        with self.assertRaisesRegex(lab_config.LabError, "depth"):
            lab_config.parse_json_bytes(json.dumps({"nested": nested}).encode(), "fixture")
        with self.assertRaisesRegex(source_lock.LockError, "string exceeds"):
            source_lock.parse_lock_bytes(
                json.dumps({"unexpected": "x" * 4097}).encode()
            )

    def test_bounded_reader_rejects_large_and_traversing_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "small").write_bytes(b"abc")
            self.assertEqual(b"abc", diagnostics_inputs.read_regular(root, "small", 3))
            with self.assertRaises(diagnostics_inputs.InputContractError):
                diagnostics_inputs.read_regular(root, "small", 2)
            with self.assertRaises(diagnostics_inputs.InputContractError):
                diagnostics_inputs.read_regular(root, "../small", 3)

    def test_bounded_reader_rejects_links_when_the_host_can_create_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "target").write_bytes(b"abc")
            link = root / "link"
            try:
                link.symlink_to(root / "target")
            except (OSError, NotImplementedError):
                self.skipTest("host cannot create a symbolic link")
            with self.assertRaises(diagnostics_inputs.InputContractError):
                diagnostics_inputs.read_regular(root, "link", 3)

    def test_failed_git_probe_is_cached_for_one_diagnostic_snapshot(self) -> None:
        ctx = diagnostics.Context(ROOT, "pci-x86-64")
        with patch.object(
            diagnostics_git,
            "resolve_native",
            side_effect=diagnostics_git.ToolUnavailable("missing"),
        ) as resolve:
            self.assertEqual((None, "unavailable"), ctx._git())
            self.assertEqual((None, "unavailable"), ctx._git())
        resolve.assert_called_once_with("git")

    def test_reused_context_clears_active_task_after_workflow_errors(self) -> None:
        ctx = diagnostics.Context(ROOT, "pci-x86-64")
        self.assertEqual("pass", ctx.workflow().status)
        self.assertIsNotNone(ctx.active_task)

        with patch.object(
            diagnostics.validate_workflow,
            "validate_models",
            return_value=(["invalid workflow"], None),
        ):
            self.assertEqual("fail", ctx.workflow().status)
        self.assertIsNone(ctx.active_task)

        self.assertEqual("pass", ctx.workflow().status)
        self.assertIsNotNone(ctx.active_task)
        with patch.object(
            diagnostics,
            "read_regular",
            side_effect=diagnostics.InputUnavailable("missing workflow"),
        ):
            self.assertEqual("unavailable", ctx.workflow().status)
        self.assertIsNone(ctx.active_task)

    def test_git_invocation_bounds_output_and_time(self) -> None:
        executable = Path(sys.executable)
        with patch.object(diagnostics_git, "OUTPUT_LIMIT", 32):
            with self.assertRaises(diagnostics_git.ToolContractError):
                diagnostics_git.invoke(executable, ROOT, ["-B", "-c", "print('x' * 1000)"])
        with patch.object(diagnostics_git, "TIMEOUT_SECONDS", 0.05):
            with self.assertRaises(diagnostics_git.ToolContractError):
                diagnostics_git.invoke(executable, ROOT, ["-B", "-c", "import time; time.sleep(2)"])

    def test_git_contract_hardens_environment_and_rejects_old_versions(self) -> None:
        executable = Path(sys.executable)
        with patch.object(diagnostics_git, "invoke", return_value=(0, b"git version 2.35.8\n")):
            with self.assertRaisesRegex(diagnostics_git.ToolContractError, "2.36.0"):
                diagnostics_git.git_version(executable, ROOT)
        with patch.object(diagnostics_git, "invoke", return_value=(0, b"git version 2.36.0\n")):
            self.assertEqual((2, 36, 0), diagnostics_git.git_version(executable, ROOT))
        environment = diagnostics_git._environment(executable)
        self.assertEqual("1", environment["GIT_NO_LAZY_FETCH"])
        self.assertEqual("1", environment["GIT_NO_REPLACE_OBJECTS"])

    def _git_fixture(self) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        executable = diagnostics_git.resolve_native("git")
        try:
            diagnostics_git.git_version(executable, root)
        except diagnostics_git.ToolContractError as exc:
            self.skipTest(str(exc))
        subprocess.run([str(executable), "init", "--quiet", "--object-format=sha1", str(root)], check=True)
        subprocess.run([str(executable), "-C", str(root), "config", "user.email", "tests@example.invalid"], check=True)
        subprocess.run([str(executable), "-C", str(root), "config", "user.name", "Diagnostics Tests"], check=True)
        return temporary, root, executable

    def test_url_rewrite_cannot_disguise_a_wrong_checkout_origin(self) -> None:
        _, root, executable = self._git_fixture()
        (root / "fixture").write_text("locked\n", encoding="utf-8")
        subprocess.run([str(executable), "-C", str(root), "add", "fixture"], check=True)
        subprocess.run([str(executable), "-C", str(root), "commit", "--quiet", "-m", "locked"], check=True)
        commit = subprocess.check_output([str(executable), "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        expected = "https://expected.example/repo"
        wrong = "https://wrong.example/repo"
        subprocess.run([str(executable), "-C", str(root), "remote", "add", "origin", wrong], check=True)
        subprocess.run([str(executable), "-C", str(root), "config", "url.https://expected.example/.insteadOf", "https://wrong.example/"], check=True)
        for suffix in ("branch", "release"):
            subprocess.run([str(executable), "-C", str(root), "update-ref", f"refs/yocto-qemu-edu-lab/bitbake/{suffix}", commit], check=True)
        subprocess.run([str(executable), "-C", str(root), "checkout", "--quiet", "--detach", commit], check=True)
        expanded = subprocess.check_output([str(executable), "-C", str(root), "remote", "get-url", "origin"], text=True).strip()
        self.assertEqual(expected, expanded)
        source = {"id": "bitbake", "url": expected, "commit": commit}
        self.assertFalse(diagnostics_git.checkout_matches(executable, root, source))

    def test_replacement_ref_cannot_disguise_a_different_clean_tree(self) -> None:
        _, root, executable = self._git_fixture()
        fixture = root / "fixture"
        fixture.write_text("locked\n", encoding="utf-8")
        subprocess.run([str(executable), "-C", str(root), "add", "fixture"], check=True)
        subprocess.run([str(executable), "-C", str(root), "commit", "--quiet", "-m", "locked"], check=True)
        locked = subprocess.check_output([str(executable), "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        fixture.write_text("replacement\n", encoding="utf-8")
        subprocess.run([str(executable), "-C", str(root), "commit", "--quiet", "-am", "replacement"], check=True)
        replacement = subprocess.check_output([str(executable), "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
        subprocess.run([str(executable), "-C", str(root), "replace", locked, replacement], check=True)
        subprocess.run([str(executable), "-C", str(root), "checkout", "--quiet", "--detach", locked], check=True)
        self.assertEqual("replacement\n", fixture.read_text(encoding="utf-8"))
        self.assertEqual("", subprocess.check_output([str(executable), "-C", str(root), "status", "--porcelain=v1"], text=True))
        revision, dirty = diagnostics_git.repository_state(executable, root)
        self.assertEqual(locked, revision)
        self.assertTrue(dirty)

    def test_promisor_configuration_is_rejected_before_object_queries(self) -> None:
        _, root, executable = self._git_fixture()
        subprocess.run(
            [str(executable), "-C", str(root), "config", "remote.origin.promisor", "true"],
            check=True,
        )
        with self.assertRaisesRegex(
            diagnostics_git.ToolContractError, "partial, or promisor"
        ):
            diagnostics_git.repository_state(executable, root)

    def test_included_and_worktree_configuration_are_rejected(self) -> None:
        for setting in ("include.path", "extensions.worktreeConfig"):
            with self.subTest(setting=setting):
                _, root, executable = self._git_fixture()
                subprocess.run(
                    [str(executable), "-C", str(root), "config", setting, "true"],
                    check=True,
                )
                with self.assertRaisesRegex(
                    diagnostics_git.ToolContractError, "included, worktree-scoped"
                ):
                    diagnostics_git.repository_state(executable, root)

    def test_document_contains_no_host_or_private_identity(self) -> None:
        document, _ = diagnostics.command_document(ROOT, "inspect", "pci-x86-64")
        payload = diagnostics.json_bytes(document).decode("utf-8")
        forbidden = (
            str(ROOT),
            str(Path.home()),
            os.environ.get("USERNAME", "__missing__"),
            ".age" + "nts",
            ".co" + "dex",
        )
        for value in forbidden:
            if value and value != "__missing__":
                self.assertNotIn(value, payload)

    def test_unsafe_workflow_prefix_is_not_projected(self) -> None:
        original = diagnostics.read_regular
        secret = "/home/alice/token=supersecret-"

        def supplied(root: Path, relative: str, maximum: int) -> bytes:
            raw = original(root, relative, maximum)
            if relative in {
                "docs/maintainers/config.toml",
                "docs/maintainers/tasks.toml",
            }:
                return raw.replace(b'task_id_prefix = "A"', f'task_id_prefix = "{secret}"'.encode())
            return raw

        with patch.object(diagnostics, "read_regular", side_effect=supplied):
            document, exit_code = diagnostics.command_document(
                ROOT, "status", "pci-x86-64"
            )
        payload = diagnostics.json_bytes(document)
        self.assertEqual(1, exit_code)
        self.assertEqual("fail", document["result"])
        self.assertIsNone(document["data"]["active_task"])
        self.assertNotIn(secret.encode(), payload)

    def test_semantic_validator_rejects_unsafe_active_task(self) -> None:
        document, _ = diagnostics.command_document(ROOT, "status", None)
        for task_id in (
            "/home/alice/token=supersecret-006",
            "A\u0660\u0660\u0666",
            "A006\n",
            "A" + "0" * diagnostics.MAX_TASK_ID_LENGTH,
        ):
            with self.subTest(task_id=task_id):
                changed = copy.deepcopy(document)
                changed["data"]["active_task"] = {
                    "id": task_id,
                    "status": "In Progress",
                }
                with self.assertRaises(ValueError):
                    diagnostics.validate_document(changed)

    def test_semantic_validator_suppresses_active_task_when_workflow_fails(self) -> None:
        document, _ = diagnostics.command_document(ROOT, "status", None)
        self.assertIsNotNone(document["data"]["active_task"])
        for status in ("fail", "unavailable"):
            with self.subTest(status=status):
                changed = copy.deepcopy(document)
                changed["checks"][2] = diagnostics.check(
                    "workflow.task", status
                ).object()
                changed["result"] = status
                with self.assertRaises(ValueError):
                    diagnostics.validate_document(changed)
                changed["data"]["active_task"] = None
                diagnostics.validate_document(changed)

    def test_status_reads_each_repository_input_once(self) -> None:
        original = diagnostics.read_regular
        reads: dict[str, int] = {}

        def counted(root: Path, relative: str, maximum: int) -> bytes:
            reads[relative] = reads.get(relative, 0) + 1
            return original(root, relative, maximum)

        with patch.object(diagnostics, "read_regular", side_effect=counted):
            diagnostics.command_document(ROOT, "status", "pci-x86-64")
        self.assertTrue(reads)
        self.assertTrue(all(count == 1 for count in reads.values()), reads)

    def test_missing_git_is_unavailable_without_path_details(self) -> None:
        with patch.object(
            diagnostics_git,
            "resolve_native",
            side_effect=diagnostics_git.ToolUnavailable("fixture path must stay private"),
        ):
            document, exit_code = diagnostics.command_document(ROOT, "status", "pci-x86-64")
        self.assertEqual(3, exit_code)
        self.assertEqual("unavailable", document["result"])
        payload = diagnostics.json_bytes(document)
        self.assertNotIn(b"fixture path", payload)
        self.assertIsNone(document["project"]["revision"])
        self.assertIsNone(document["project"]["dirty"])

    def test_present_invalid_evidence_fails_instead_of_becoming_unavailable(self) -> None:
        original = diagnostics.read_regular
        selected = "build/qemu-edu-runtime-v3.json"

        def supplied(root: Path, relative: str, maximum: int) -> bytes:
            if relative == selected:
                return b"{}\n"
            return original(root, relative, maximum)

        with patch.object(diagnostics, "read_regular", side_effect=supplied):
            document, exit_code = diagnostics.command_document(ROOT, "evidence", "pci-x86-64")
        self.assertEqual(1, exit_code)
        self.assertEqual("fail", document["result"])
        statuses = {item["id"]: item["status"] for item in document["checks"]}
        self.assertEqual("pass", statuses["evidence.file"])
        self.assertEqual("fail", statuses["evidence.document"])
        self.assertEqual("unavailable", statuses["evidence.result"])

    def test_untrusted_evidence_identity_is_not_projected(self) -> None:
        pci_results = {
            test_id: {"status": "PASSED", "duration": 0.1}
            for test_id in runtime_evidence.EXPECTED_TESTS
        }
        pci_oeqa = {
            "result": {
                "configuration": {
                    "MACHINE": "qemu-edu-x86-64",
                    "IMAGE_BASENAME": "qemu-edu-image",
                    "DISTRO": "poky",
                    "HOST_DISTRO": "ubuntu-24.04",
                    "STARTTIME": "20260814010101",
                    "TEST_TYPE": "runtime",
                },
                "result": pci_results,
            }
        }
        with patch.object(runtime_evidence, "git_state", return_value=("1" * 40, False)):
            pci = runtime_evidence.build_evidence(
                oeqa=pci_oeqa,
                repo=ROOT,
                machine="qemu-edu-x86-64",
                image="qemu-edu-image",
                oeqa_sha256="2" * 64,
                testimage_exit_code=0,
            )
        platform_results = {
            test_id: {"status": "PASSED", "duration": 0.1}
            for test_id in platform_runtime_evidence.EXPECTED_TESTS
        }
        platform_oeqa = {
            "result": {
                "configuration": {
                    "MACHINE": "qemu-edu-platform-arm64",
                    "IMAGE_BASENAME": "qemu-edu-image",
                    "DISTRO": "poky",
                    "HOST_DISTRO": "ubuntu-24.04",
                    "STARTTIME": "20260814010101",
                    "TEST_TYPE": "runtime",
                },
                "result": platform_results,
            }
        }
        with patch.object(platform_runtime_evidence, "git_state", return_value=("1" * 40, False)):
            platform = platform_runtime_evidence.build_evidence(
                oeqa=platform_oeqa,
                repo=ROOT,
                lab_id="platform-arm64",
                machine="qemu-edu-platform-arm64",
                image="qemu-edu-image",
                oeqa_sha256="3" * 64,
                testimage_exit_code=0,
            )
        secrets = (
            "/home/alice/token=supersecret",
            "user:password@host.invalid",
            "builder.example.invalid",
            "0.6.0-dev\nprivate",
            "0.6.0+builder.example.invalid",
        )
        original = diagnostics.read_regular
        fixtures = (
            ("pci-x86-64", "build/qemu-edu-runtime-v3.json", pci),
            (
                "platform-arm64",
                "build-platform-arm64/qemu-edu-platform-runtime-v1.json",
                platform,
            ),
        )
        for lab_id, selected, evidence in fixtures:
            for secret in secrets:
                with self.subTest(lab=lab_id, value=secret):
                    changed = copy.deepcopy(evidence)
                    changed["project"]["version"] = secret
                    supplied_bytes = (json.dumps(changed) + "\n").encode()

                    def supplied(root: Path, relative: str, maximum: int) -> bytes:
                        if relative == selected:
                            return supplied_bytes
                        return original(root, relative, maximum)

                    with patch.object(diagnostics, "read_regular", side_effect=supplied):
                        document, exit_code = diagnostics.command_document(
                            ROOT, "evidence", lab_id
                        )
                    payload = diagnostics.json_bytes(document)
                    self.assertEqual(1, exit_code)
                    self.assertEqual("fail", document["result"])
                    self.assertIsNone(document["data"]["evidence"])
                    self.assertNotIn(secret.encode(), payload)

        for field, secret in (
            ("machine", "builder.example.invalid"),
            ("image", "qemu-edu-other"),
        ):
            changed = copy.deepcopy(pci)
            changed["build"][field] = secret
            supplied_bytes = (json.dumps(changed) + "\n").encode()

            def supplied_identity(root: Path, relative: str, maximum: int) -> bytes:
                if relative == "build/qemu-edu-runtime-v3.json":
                    return supplied_bytes
                return original(root, relative, maximum)

            with patch.object(
                diagnostics, "read_regular", side_effect=supplied_identity
            ):
                document, exit_code = diagnostics.command_document(
                    ROOT, "evidence", "pci-x86-64"
                )
            payload = diagnostics.json_bytes(document)
            self.assertEqual(1, exit_code)
            self.assertIsNone(document["data"]["evidence"])
            self.assertNotIn(secret.encode(), payload)

    def test_evidence_file_bytes_are_parsed_without_reopening(self) -> None:
        results = {
            test_id: {"status": "PASSED", "duration": 0.1}
            for test_id in runtime_evidence.EXPECTED_TESTS
        }
        oeqa = {
            "result": {
                "configuration": {
                    "MACHINE": "qemu-edu-x86-64", "IMAGE_BASENAME": "qemu-edu-image",
                    "DISTRO": "poky", "HOST_DISTRO": "ubuntu-24.04",
                    "STARTTIME": "20260814010101", "TEST_TYPE": "runtime",
                },
                "result": results,
            }
        }
        with patch.object(runtime_evidence, "git_state", return_value=("1" * 40, False)):
            evidence = runtime_evidence.build_evidence(
                oeqa=oeqa, repo=ROOT, machine="qemu-edu-x86-64",
                image="qemu-edu-image", oeqa_sha256="2" * 64,
                testimage_exit_code=0,
            )
        evidence_bytes = (json.dumps(evidence, separators=(",", ":")) + "\n").encode()
        original = diagnostics.read_regular
        selected = "build/qemu-edu-runtime-v3.json"
        reads = 0

        def supplied(root: Path, relative: str, maximum: int) -> bytes:
            nonlocal reads
            if relative == selected:
                reads += 1
                return evidence_bytes
            return original(root, relative, maximum)

        with patch.object(diagnostics, "read_regular", side_effect=supplied):
            document, exit_code = diagnostics.command_document(ROOT, "evidence", "pci-x86-64")
        self.assertEqual(1, reads)
        self.assertEqual(0, exit_code)
        self.assertEqual("warning", document["result"])
        self.assertEqual("not-recorded", document["data"]["inputs"]["lab_binding"])

    def test_pci_evidence_honestly_reports_unrecorded_lab_binding(self) -> None:
        results = {
            test_id: {"status": "PASSED", "duration": 0.1}
            for test_id in runtime_evidence.EXPECTED_TESTS
        }
        oeqa = {
            "result": {
                "configuration": {
                    "MACHINE": "qemu-edu-x86-64",
                    "IMAGE_BASENAME": "qemu-edu-image",
                    "DISTRO": "poky",
                    "HOST_DISTRO": "ubuntu-24.04",
                    "STARTTIME": "20260814010101",
                    "TEST_TYPE": "runtime",
                },
                "result": results,
            }
        }
        with patch.object(runtime_evidence, "git_state", return_value=("1" * 40, False)):
            evidence = runtime_evidence.build_evidence(
                oeqa=oeqa,
                repo=ROOT,
                machine="qemu-edu-x86-64",
                image="qemu-edu-image",
                oeqa_sha256="2" * 64,
                testimage_exit_code=0,
            )
        ctx = diagnostics.Context(ROOT, "pci-x86-64")
        self.assertEqual("pass", ctx.project_version().status)
        self.assertEqual("pass", ctx.source_lock().status)
        self.assertEqual("pass", ctx.lab_catalog().status)
        self.assertEqual("pass", ctx.selection().status)
        ctx.evidence_document = evidence
        ctx.lab_binding = "not-recorded"
        ctx.statuses["evidence.document"] = "pass"
        item = ctx.evidence_inputs_check()
        self.assertEqual("warning", item.status)
        self.assertEqual("Historical PCI evidence does not record lab catalog bindings.", item.summary)

    def test_platform_evidence_requires_current_lab_digests(self) -> None:
        results = {
            test_id: {"status": "PASSED", "duration": 0.1}
            for test_id in platform_runtime_evidence.EXPECTED_TESTS
        }
        oeqa = {
            "result": {
                "configuration": {
                    "MACHINE": "qemu-edu-platform-arm64",
                    "IMAGE_BASENAME": "qemu-edu-image",
                    "DISTRO": "poky",
                    "HOST_DISTRO": "ubuntu-24.04",
                    "STARTTIME": "20260814010101",
                    "TEST_TYPE": "runtime",
                },
                "result": results,
            }
        }
        with patch.object(platform_runtime_evidence, "git_state", return_value=("1" * 40, False)):
            evidence = platform_runtime_evidence.build_evidence(
                oeqa=oeqa,
                repo=ROOT,
                lab_id="platform-arm64",
                machine="qemu-edu-platform-arm64",
                image="qemu-edu-image",
                oeqa_sha256="3" * 64,
                testimage_exit_code=0,
            )
        ctx = diagnostics.Context(ROOT, "platform-arm64")
        self.assertEqual("pass", ctx.project_version().status)
        self.assertEqual("pass", ctx.source_lock().status)
        self.assertEqual("pass", ctx.lab_catalog().status)
        self.assertEqual("pass", ctx.selection().status)
        ctx.evidence_document = evidence
        ctx.lab_binding = "bound"
        ctx.statuses["evidence.document"] = "pass"
        self.assertEqual("pass", ctx.evidence_inputs_check().status)
        ctx.evidence_document = copy.deepcopy(evidence)
        ctx.evidence_document["inputs"]["lab_manifest_sha256"] = "0" * 64
        self.assertEqual("fail", ctx.evidence_inputs_check().status)
        ctx.evidence_document = copy.deepcopy(evidence)
        ctx.evidence_document["project"]["version"] = "0.5.0-dev"
        self.assertEqual("fail", ctx.evidence_inputs_check().status)


if __name__ == "__main__":
    unittest.main()
