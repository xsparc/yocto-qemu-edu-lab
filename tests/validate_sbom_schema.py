#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Exercise the SPDX evidence schema with the exact isolated JSON Schema oracle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from test_sbom_evidence import MODULE, sample_evidence  # noqa: E402


def main() -> int:
    schema = json.loads(
        (ROOT / "schemas/qemu-edu-sbom-evidence-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    positives = [sample_evidence("pci-x86-64"), sample_evidence("platform-arm64")]
    for document in positives:
        errors = list(validator.iter_errors(document))
        if errors:
            raise AssertionError(errors[0].message)
        MODULE.validate_evidence(document, require_pass=True)

    negatives = []
    document = sample_evidence()
    document["future"] = True
    negatives.append(document)
    document = sample_evidence()
    document["task_exit_code"] = False
    negatives.append(document)
    document = sample_evidence()
    document["lab"]["machine"] = "qemu-edu-platform-arm64"
    negatives.append(document)
    document = sample_evidence()
    document["packages"].pop()
    negatives.append(document)
    document = sample_evidence()
    document["packages"][0]["declared_license"] = "MIT"
    negatives.append(document)
    document = sample_evidence()
    document["inputs"]["source_lock_sha256"] += "\n"
    negatives.append(document)
    document = sample_evidence()
    document["artifacts"][0]["basename"] = "image\u001b[31m"
    negatives.append(document)
    document = sample_evidence()
    document["generator"]["settings"]["SPDX_INCLUDE_TIMESTAMPS"] = "1"
    negatives.append(document)
    document = sample_evidence()
    document["checks"][0]["status"] = "failed"
    negatives.append(document)
    document = sample_evidence()
    document["source_sbom"]["size_bytes"] = 134217729
    negatives.append(document)

    for index, document in enumerate(negatives):
        if not list(validator.iter_errors(document)):
            raise AssertionError(f"negative fixture {index} passed the JSON Schema")
        try:
            MODULE.validate_evidence(document)
        except MODULE.SbomEvidenceError:
            pass
        else:
            raise AssertionError(f"negative fixture {index} passed semantic validation")

    print(
        "sbom-schema: PASS: "
        f"{len(positives)} positive and {len(negatives)} negative documents"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
