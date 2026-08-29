# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
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
SPEC = importlib.util.spec_from_file_location(
    "sdk_evidence_contract", ROOT / "scripts/sdk_evidence.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def sample_evidence(lab_id: str = "pci-x86-64") -> dict:
    lab_values = {
        "pci-x86-64": ("qemu-edu-x86-64", "build-sdk-pci-x86-64", "x86_64"),
        "platform-arm64": (
            "qemu-edu-platform-arm64",
            "build-sdk-platform-arm64",
            "aarch64",
        ),
    }
    machine, build_dir, architecture = lab_values[lab_id]
    return {
        "schema_version": 1,
        "kind": "qemu-edu-sdk-iteration-evidence",
        "project": {
            "name": "yocto-qemu-edu-lab",
            "version": "0.8.0-dev",
            "revision": "a" * 40,
            "dirty": False,
        },
        "inputs": {
            "source_lock_sha256": "b" * 64,
            "openembedded_core_commit": "c" * 40,
            "lab_index_sha256": "d" * 64,
            "lab_manifest_sha256": "e" * 64,
            "yocto_version": "6.0.2",
            "yocto_series": "wrynose",
        },
        "lab": {
            "id": lab_id,
            "machine": machine,
            "image": "qemu-edu-image",
            "development_build_dir": build_dir,
            "recipe": "qemu-edu-sdk-sample",
            "source_dir": "learner-source/qemu-edu-sdk-sample",
            "guest_binary": "/usr/bin/qemu-edu-sdk-sample",
        },
        "workflow": {
            "profile": "direct-esdk-devtool-v1",
            "sdk_mode": "direct-build",
            "ide": "none",
            "transport": "runqemu-slirp-loopback-ssh",
        },
        "source": {"sha256": "f" * 64, "preserved_after_reset": True},
        "execution": {
            "architecture": architecture,
            "expected_output": "qemu-edu-sdk-sample workspace",
            "artifact_sha256": "1" * 64,
            "base_absent": True,
            "undeployed_absent": True,
            "cold_boot_absent": True,
        },
        "checks": [
            {"id": check_id, "status": "passed"}
            for check_id in MODULE.CHECK_IDS
        ],
        "task_exit_code": 0,
        "result": "passed",
    }


class SdkEvidenceTests(unittest.TestCase):
    def test_project_state_uses_the_bounded_repository_adapter(self) -> None:
        executable = ROOT / "git"
        with (
            patch.object(MODULE, "resolve_native", return_value=executable),
            patch.object(
                MODULE,
                "repository_state",
                return_value=("a" * 40, False),
            ) as state,
        ):
            self.assertEqual(("a" * 40, False), MODULE.project_state(ROOT))
        state.assert_called_once_with(executable, ROOT)
        with (
            patch.object(MODULE, "resolve_native", return_value=executable),
            patch.object(
                MODULE,
                "repository_state",
                side_effect=MODULE.ToolContractError("unsafe repository"),
            ),
            self.assertRaisesRegex(MODULE.SdkEvidenceError, "unavailable"),
        ):
            MODULE.project_state(ROOT)

    def test_positive_dual_lab_documents_are_semantically_closed(self) -> None:
        for lab_id in ("pci-x86-64", "platform-arm64"):
            with self.subTest(lab=lab_id):
                MODULE.validate_evidence(sample_evidence(lab_id), require_pass=True)

    def test_semantic_validator_rejects_aliases_drift_and_failed_checks(self) -> None:
        mutations = []
        document = sample_evidence()
        document["schema_version"] = True
        mutations.append(document)
        document = sample_evidence()
        document["project"]["dirty"] = 0
        mutations.append(document)
        document = sample_evidence()
        document["lab"]["machine"] = "qemu-edu-platform-arm64"
        mutations.append(document)
        document = sample_evidence()
        document["lab"]["development_build_dir"] = "build-sdk-platform-arm64"
        mutations.append(document)
        document = sample_evidence()
        document["inputs"]["yocto_series"] = "/home/private"
        mutations.append(document)
        document = sample_evidence()
        document["execution"]["architecture"] = "aarch64"
        mutations.append(document)
        document = sample_evidence()
        document["execution"]["artifact_sha256"] = "0" * 63
        mutations.append(document)
        document = sample_evidence()
        document["checks"][4]["status"] = "failed"
        mutations.append(document)
        document = sample_evidence()
        document["checks"].reverse()
        mutations.append(document)
        document = sample_evidence()
        document["source"]["preserved_after_reset"] = 1
        mutations.append(document)
        document = sample_evidence()
        document["future"] = True
        mutations.append(document)
        for index, document in enumerate(mutations):
            with self.subTest(index=index):
                with self.assertRaises(MODULE.SdkEvidenceError):
                    MODULE.validate_evidence(document)

    def test_evidence_path_is_fixed_to_each_development_build_root(self) -> None:
        for lab_id, expected in (
            (
                "pci-x86-64",
                ROOT / "build-sdk-pci-x86-64/evidence/qemu-edu-sdk-evidence-v1.json",
            ),
            (
                "platform-arm64",
                ROOT / "build-sdk-platform-arm64/evidence/qemu-edu-sdk-evidence-v1.json",
            ),
        ):
            manifest, _, _, _, _ = MODULE.selected_contract(ROOT, lab_id)
            self.assertEqual(expected, MODULE.evidence_path(ROOT, manifest))

    def test_atomic_writer_round_trips_and_refuses_final_symlink(self) -> None:
        document = sample_evidence()
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence/document.json"
            MODULE.write_evidence(output, document)
            self.assertEqual(document, MODULE.read_evidence(output))
            protected = output.parent / "protected.json"
            protected.write_text("protected\n", encoding="utf-8")
            output.unlink()
            try:
                os.symlink(protected.name, output)
            except OSError as exc:
                self.skipTest(f"host cannot create a symbolic link: {exc}")
            with self.assertRaisesRegex(MODULE.SdkEvidenceError, "symbolic link"):
                MODULE.write_evidence(output, document)
            self.assertEqual("protected\n", protected.read_text(encoding="utf-8"))

    def test_evidence_path_rejects_relocation_and_symlinked_build_root(self) -> None:
        manifest, _, _, _, _ = MODULE.selected_contract(ROOT, "pci-x86-64")
        with tempfile.TemporaryDirectory() as temporary:
            relocated = Path(temporary) / "relocated"
            with self.assertRaisesRegex(MODULE.SdkEvidenceError, "differs"):
                MODULE.evidence_path(ROOT, manifest, relocated)

            root = Path(temporary) / "repository"
            root.mkdir()
            outside = Path(temporary) / "outside"
            outside.mkdir()
            expected = root / manifest["development"]["build_dir"]
            try:
                os.symlink(outside, expected, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"host cannot create a symbolic link: {exc}")
            with self.assertRaisesRegex(MODULE.SdkEvidenceError, "regular directory"):
                MODULE.evidence_path(root, manifest)

    def test_reader_rejects_duplicate_keys_and_oversized_integer_cleanly(self) -> None:
        for payload, expected in (
            (b'{"value":1,"value":2}', "duplicate JSON key"),
            (
                b'{"value":' + b"1" * (MODULE.MAX_JSON_INTEGER_DIGITS + 1) + b'}',
                "integer exceeds",
            ),
        ):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "bad.json"
                path.write_bytes(payload)
                with self.assertRaisesRegex(MODULE.SdkEvidenceError, expected):
                    MODULE.read_evidence(path)

    def test_cli_rejects_explicit_empty_lab_without_document(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/sdk_evidence.py"),
                "--repo",
                str(ROOT),
                "--lab",
                "",
                "path",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(2, result.returncode)
        self.assertEqual("", result.stdout)
        self.assertIn("unknown lab", result.stderr)

    def test_serialized_document_contains_no_host_or_transport_details(self) -> None:
        payload = json.dumps(sample_evidence(), sort_keys=True)
        for forbidden in (
            "ssh_port",
            "private_key",
            "known_hosts",
            "started_at",
            "duration",
            "C:\\",
            "/home/",
        ):
            self.assertNotIn(forbidden, payload)

    def test_current_input_validation_recomputes_retained_source_digest(self) -> None:
        document = sample_evidence()
        manifest = {
            "build": {
                "machine": "qemu-edu-x86-64",
                "targets": ["qemu-edu-image"],
            },
            "development": {
                "build_dir": "build-sdk-pci-x86-64",
                "recipe": "qemu-edu-sdk-sample",
                "source_dir": "learner-source/qemu-edu-sdk-sample",
                "guest_binary": "/usr/bin/qemu-edu-sdk-sample",
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "VERSION").write_text("0.8.0-dev\n", encoding="utf-8")
            source_path = (
                root
                / "build-sdk-pci-x86-64/learner-source/"
                "qemu-edu-sdk-sample/qemu-edu-sdk-sample.c"
            )
            source_path.parent.mkdir(parents=True)
            source_path.write_text("workspace\n", encoding="utf-8")
            document["source"]["sha256"] = MODULE.hashlib.sha256(
                source_path.read_bytes()
            ).hexdigest()
            lock = {"release": {"version": "6.0.2", "series": "wrynose"}}
            with (
                patch.object(
                    MODULE,
                    "selected_contract",
                    return_value=(manifest, "pci-x86-64", "d" * 64, "e" * 64, {}),
                ),
                patch.object(
                    MODULE,
                    "source_authority",
                    return_value=(lock, "b" * 64, "c" * 40),
                ),
                patch.object(
                    MODULE,
                    "project_state",
                    return_value=("a" * 40, False),
                ),
            ):
                MODULE.validate_evidence(document, current_repo=root)
                source_path.write_text("tampered\n", encoding="utf-8")
                with self.assertRaisesRegex(MODULE.SdkEvidenceError, "digest"):
                    MODULE.validate_evidence(document, current_repo=root)


if __name__ == "__main__":
    unittest.main()
