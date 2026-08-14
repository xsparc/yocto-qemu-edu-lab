# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Independent Draft 2020-12 positive and adversarial diagnostics validation."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import diagnostics  # noqa: E402


def rejected(validator: Draft202012Validator, document: dict) -> None:
    if validator.is_valid(document):
        raise AssertionError("adversarial diagnostics document was accepted")


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

    baseline = next(item for item in documents if item["command"] == "status")
    changed = copy.deepcopy(baseline)
    changed["extra"] = True
    rejected(validator, changed)
    changed = copy.deepcopy(baseline)
    changed["schema_version"] = True
    rejected(validator, changed)
    changed = copy.deepcopy(baseline)
    changed["project"]["version"] = "0.7.0-dev"
    rejected(validator, changed)
    changed = copy.deepcopy(baseline)
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
    inspect = next(item for item in documents if item["command"] == "inspect")
    changed = copy.deepcopy(inspect)
    changed["data"]["sources"][0], changed["data"]["sources"][1] = changed["data"]["sources"][1], changed["data"]["sources"][0]
    rejected(validator, changed)
    evidence = next(item for item in documents if item["command"] == "evidence")
    changed = copy.deepcopy(evidence)
    changed["data"]["inputs"] = {"lab_binding": "bound", "lab_index_sha256": None, "lab_manifest_sha256": None}
    rejected(validator, changed)
    if retrievals:
        raise AssertionError("schema validation attempted external retrieval")
    print("diagnostics-schema: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
