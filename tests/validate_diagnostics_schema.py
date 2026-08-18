# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Independent Draft 2020-12 positive and adversarial diagnostics validation."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from referencing import Registry


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import diagnostics  # noqa: E402
import platform_runtime_evidence  # noqa: E402
import runtime_evidence  # noqa: E402


def rejected(validator: Draft202012Validator, document: dict) -> None:
    if validator.is_valid(document):
        raise AssertionError("adversarial diagnostics document was accepted")


def passing_oeqa(machine: str, tests: tuple[str, ...]) -> dict:
    return {
        "result": {
            "configuration": {
                "MACHINE": machine,
                "IMAGE_BASENAME": "qemu-edu-image",
                "DISTRO": "poky",
                "HOST_DISTRO": "ubuntu-24.04",
                "STARTTIME": "20260815010101",
                "TEST_TYPE": "runtime",
            },
            "result": {
                test_id: {"status": "PASSED", "duration": 0.1}
                for test_id in tests
            },
        }
    }


def populated_evidence_bytes(revision: str) -> dict[str, bytes]:
    with patch.object(runtime_evidence, "git_state", return_value=(revision, False)):
        pci = runtime_evidence.build_evidence(
            oeqa=passing_oeqa(
                "qemu-edu-x86-64", runtime_evidence.EXPECTED_TESTS
            ),
            repo=ROOT,
            machine="qemu-edu-x86-64",
            image="qemu-edu-image",
            oeqa_sha256="1" * 64,
            testimage_exit_code=0,
        )
    with patch.object(
        platform_runtime_evidence, "git_state", return_value=(revision, False)
    ):
        platform = platform_runtime_evidence.build_evidence(
            oeqa=passing_oeqa(
                "qemu-edu-platform-arm64",
                platform_runtime_evidence.EXPECTED_TESTS,
            ),
            repo=ROOT,
            lab_id="platform-arm64",
            machine="qemu-edu-platform-arm64",
            image="qemu-edu-image",
            oeqa_sha256="2" * 64,
            testimage_exit_code=0,
        )
    return {
        "build/qemu-edu-runtime-v3.json": (
            json.dumps(pci, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode(),
        "build-platform-arm64/qemu-edu-platform-runtime-v1.json": (
            json.dumps(platform, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode(),
    }


def main() -> int:
    schema = json.loads((ROOT / "schemas/qemu-edu-diagnostics-v1.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    retrievals: list[str] = []

    def deny_retrieval(uri: str):
        retrievals.append(uri)
        raise RuntimeError("external schema retrieval is forbidden")

    validator = Draft202012Validator(schema, registry=Registry(retrieve=deny_retrieval))
    documents = []
    for lab in ("pci-x86-64", "platform-arm64"):
        for command in ("status", "doctor", "inspect", "evidence"):
            document, _ = diagnostics.command_document(ROOT, command, lab)
            validator.validate(document)
            documents.append(document)

    revision = documents[0]["project"]["revision"]
    if not isinstance(revision, str):
        raise AssertionError("repository revision is unavailable for schema fixtures")
    evidence_files = populated_evidence_bytes(revision)
    original_read = diagnostics.read_regular

    def supplied(root: Path, relative: str, maximum: int) -> bytes:
        if relative in evidence_files:
            raw = evidence_files[relative]
            if len(raw) > maximum:
                raise AssertionError("generated evidence exceeds its diagnostic bound")
            return raw
        return original_read(root, relative, maximum)

    with patch.object(diagnostics, "read_regular", side_effect=supplied):
        for lab in ("pci-x86-64", "platform-arm64"):
            for command in ("doctor", "evidence"):
                document, _ = diagnostics.command_document(ROOT, command, lab)
                validator.validate(document)
                if document["data"]["evidence"] is None:
                    raise AssertionError("populated evidence projection is missing")
                documents.append(document)

    baseline = next(item for item in documents if item["command"] == "status")
    changed = copy.deepcopy(baseline)
    changed["extra"] = True
    rejected(validator, changed)
    changed = copy.deepcopy(baseline)
    changed["schema_version"] = True
    rejected(validator, changed)
    changed = copy.deepcopy(baseline)
    changed["project"]["version"] = "0.7.0-dev"
    validator.validate(changed)
    for invalid_version in ("0.6.0\n", "0.6.0\u0661", "0.6.0-\u0661"):
        changed = copy.deepcopy(baseline)
        changed["project"]["version"] = invalid_version
        rejected(validator, changed)
    changed = copy.deepcopy(baseline)
    changed["lab"]["id"] = "future-riscv"
    validator.validate(changed)
    changed = copy.deepcopy(baseline)
    changed["lab"]["id"] = "a" * 4097
    rejected(validator, changed)
    changed = copy.deepcopy(baseline)
    changed["lab"]["id"] = "future-riscv\n"
    rejected(validator, changed)
    changed = copy.deepcopy(baseline)
    changed["project"]["revision"] = "a" * 40 + "\n"
    rejected(validator, changed)
    changed = copy.deepcopy(baseline)
    changed["lab"]["index_sha256"] = "a" * 64 + "\n"
    rejected(validator, changed)
    changed = copy.deepcopy(baseline)
    changed["data"]["active_task"] = {
        "id": "A006\n",
        "status": "In Progress",
    }
    rejected(validator, changed)
    for task_id in (
        "A\u0660\u0660\u0666",
        "/home/alice/token=supersecret-006",
        "A" + "0" * 64,
    ):
        changed = copy.deepcopy(baseline)
        changed["data"]["active_task"] = {
            "id": task_id,
            "status": "In Progress",
        }
        rejected(validator, changed)
    for status in ("fail", "unavailable"):
        changed = copy.deepcopy(baseline)
        changed["checks"][2] = diagnostics.check(
            "workflow.task", status
        ).object()
        changed["result"] = status
        rejected(validator, changed)
        changed["data"]["active_task"] = None
        validator.validate(changed)
    passing_status = copy.deepcopy(baseline)
    passing_status["checks"][-1] = diagnostics.check(
        "repository.clean", "pass"
    ).object()
    passing_status["result"] = "pass"
    validator.validate(passing_status)
    changed = copy.deepcopy(passing_status)
    changed["checks"][0], changed["checks"][1] = changed["checks"][1], changed["checks"][0]
    rejected(validator, changed)
    changed = copy.deepcopy(baseline)
    changed["checks"][0]["summary"] = "Project version is unavailable."
    rejected(validator, changed)
    changed = copy.deepcopy(baseline)
    changed["result"] = "fail"
    rejected(validator, changed)
    changed = copy.deepcopy(baseline)
    changed["data"]["extra"] = True
    rejected(validator, changed)
    changed = copy.deepcopy(passing_status)
    changed["project"] = {
        "name": "yocto-qemu-edu-lab",
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
    rejected(validator, changed)
    inspect = next(item for item in documents if item["command"] == "inspect")
    changed = copy.deepcopy(inspect)
    changed["data"]["sources"][0], changed["data"]["sources"][1] = changed["data"]["sources"][1], changed["data"]["sources"][0]
    rejected(validator, changed)
    evidence = next(
        item
        for item in documents
        if item["command"] == "evidence"
        and item["result"] == "pass"
        and item["data"]["evidence"] is not None
    )
    changed = copy.deepcopy(evidence)
    changed["data"]["inputs"] = {"lab_binding": "bound", "lab_index_sha256": None, "lab_manifest_sha256": None}
    rejected(validator, changed)
    changed = copy.deepcopy(evidence)
    changed["data"]["evidence"]["summary"]["passed"] = True
    rejected(validator, changed)
    changed = copy.deepcopy(evidence)
    changed["data"]["evidence"] = None
    changed["data"]["inputs"] = None
    changed["data"]["subject_matches_head"] = None
    rejected(validator, changed)
    changed = copy.deepcopy(evidence)
    changed["data"]["subject_matches_head"] = False
    rejected(validator, changed)
    changed = copy.deepcopy(evidence)
    changed["data"]["inputs"] = "wrong"
    rejected(validator, changed)
    changed = copy.deepcopy(evidence)
    changed["data"]["extra"] = True
    rejected(validator, changed)
    if retrievals:
        raise AssertionError("schema validation attempted external retrieval")
    print("diagnostics-schema: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
