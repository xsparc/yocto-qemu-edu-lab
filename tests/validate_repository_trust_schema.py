#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Exercise repository-trust evidence v1 with the exact isolated oracle."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "tests") not in sys.path:
    sys.path.insert(0, str(ROOT / "tests"))

from test_repository_trust import MODULE, sample_evidence  # noqa: E402


def main() -> int:
    schema = json.loads(
        (ROOT / "schemas/qemu-edu-repository-trust-evidence-v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)

    positives = [sample_evidence()]
    unavailable = MODULE.build_evidence("b" * 64, None, MODULE.empty_facts())
    positives.append(unavailable)
    for document in positives:
        errors = list(validator.iter_errors(document))
        if errors:
            raise AssertionError(errors[0].message)
        MODULE.validate_evidence(document)

    negatives = []
    document = sample_evidence()
    document["future"] = True
    negatives.append(document)
    document = sample_evidence()
    document["schema_version"] = True
    negatives.append(document)
    document = sample_evidence()
    document["project"] = "another-project"
    negatives.append(document)
    document = sample_evidence()
    document["policy_sha256"] += "\n"
    negatives.append(document)
    document = sample_evidence()
    document["observed_at"] = "2026-08-30"
    negatives.append(document)
    document = sample_evidence()
    document["facts"]["repository"]["future"] = True
    negatives.append(document)
    document = sample_evidence()
    document["facts"]["ruleset"]["bypass_actor_count"] = True
    negatives.append(document)
    document = sample_evidence()
    document["checks"].pop()
    negatives.append(document)
    document = sample_evidence()
    document["checks"][0]["id"] = "ruleset.active"
    negatives.append(document)
    document = sample_evidence()
    document["checks"][0]["status"] = "passed"
    negatives.append(document)
    document = sample_evidence()
    document["facts"]["ruleset"]["name"] = "unsafe\u202ename"
    negatives.append(document)
    document = sample_evidence()
    document["facts"]["ruleset"]["name"] = "unsafe\nname"
    negatives.append(document)

    for index, document in enumerate(negatives):
        if not list(validator.iter_errors(document)):
            raise AssertionError(f"negative fixture {index} passed the JSON Schema")
        try:
            MODULE.validate_evidence(copy.deepcopy(document))
        except MODULE.RepositoryTrustError:
            pass
        else:
            raise AssertionError(f"negative fixture {index} passed semantic validation")

    print(
        "repository-trust-schema: PASS: "
        f"{len(positives)} positive and {len(negatives)} negative documents"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
