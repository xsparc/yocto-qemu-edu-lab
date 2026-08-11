# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "platform_runtime_evidence_contract",
        ROOT / "scripts/platform_runtime_evidence.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_oeqa_case():
    oeqa = types.ModuleType("oeqa")
    core = types.ModuleType("oeqa.core")
    decorator = types.ModuleType("oeqa.core.decorator")
    depends = types.ModuleType("oeqa.core.decorator.depends")
    runtime = types.ModuleType("oeqa.runtime")
    runtime_case = types.ModuleType("oeqa.runtime.case")
    depends.OETestDepends = lambda _dependencies: lambda function: function
    runtime_case.OERuntimeTestCase = unittest.TestCase
    modules = {
        "oeqa": oeqa,
        "oeqa.core": core,
        "oeqa.core.decorator": decorator,
        "oeqa.core.decorator.depends": depends,
        "oeqa.runtime": runtime,
        "oeqa.runtime.case": runtime_case,
    }
    path = ROOT / "meta-qemu-edu/lib/oeqa/runtime/cases/qemu_edu_platform.py"
    spec = importlib.util.spec_from_file_location("qemu_edu_platform", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class PlatformRuntimeEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()

    def oeqa(self, failed_index: int | None = None) -> dict:
        results = {}
        for index, test_id in enumerate(self.module.EXPECTED_TESTS):
            results[test_id] = {
                "status": "FAILED" if index == failed_index else "PASSED",
                "duration": 0.25 + index,
            }
        return {
            "result-1": {
                "configuration": {
                    "MACHINE": "qemu-edu-platform-arm64",
                    "IMAGE_BASENAME": "qemu-edu-image",
                    "DISTRO": "poky",
                    "HOST_DISTRO": "ubuntu-24.04",
                    "STARTTIME": "20260811010101",
                    "TEST_TYPE": "runtime",
                },
                "result": results,
            }
        }

    def build(self, failed_index: int | None = None) -> dict:
        with patch.object(
            self.module,
            "git_state",
            return_value=("1" * 40, False),
        ):
            return self.module.build_evidence(
                oeqa=self.oeqa(failed_index),
                repo=ROOT,
                lab_id="platform-arm64",
                machine="qemu-edu-platform-arm64",
                image="qemu-edu-image",
                oeqa_sha256="2" * 64,
                testimage_exit_code=0,
            )

    def test_oeqa_case_order_matches_closed_evidence_contract(self) -> None:
        case = load_oeqa_case()
        methods = unittest.defaultTestLoader.getTestCaseNames(
            case.QemuEduPlatformRuntimeTests
        )
        actual = tuple(
            f"qemu_edu_platform.QemuEduPlatformRuntimeTests.{method}"
            for method in methods
        )
        self.assertEqual(actual, self.module.EXPECTED_TESTS)

    def test_passing_evidence_binds_lab_digests_and_validates(self) -> None:
        evidence = self.build()
        self.module.validate_evidence(evidence, require_pass=True)
        self.assertEqual(evidence["result"], "passed")
        self.assertEqual(evidence["build"]["lab"], "platform-arm64")
        for key in (
            "source_lock_sha256",
            "lab_index_sha256",
            "lab_manifest_sha256",
            "oeqa_result_sha256",
        ):
            self.assertRegex(evidence["inputs"][key], r"^[0-9a-f]{64}$")

    def test_failed_case_makes_claim_conservative_and_require_pass_rejects(self) -> None:
        evidence = self.build(failed_index=6)
        self.assertEqual(evidence["result"], "failed")
        self.assertFalse(evidence["contract"]["interrupts"]["exercised"])
        self.assertFalse(evidence["contract"]["interrupts"]["acknowledged"])
        self.module.validate_evidence(evidence)
        with self.assertRaisesRegex(self.module.EvidenceError, "passing suite"):
            self.module.validate_evidence(evidence, require_pass=True)

        lifecycle = self.build(failed_index=8)
        self.assertEqual(lifecycle["contract"]["lifecycle"]["mechanism"], "module-reload")
        self.assertFalse(lifecycle["contract"]["lifecycle"]["restored"])
        self.module.validate_evidence(lifecycle)

    def test_platform_build_identity_is_closed(self) -> None:
        base = self.build()
        for key, value in (
            ("lab", "other-lab"),
            ("machine", "other-machine"),
            ("image", "other-image"),
        ):
            evidence = copy.deepcopy(base)
            evidence["build"][key] = value
            with self.subTest(key=key):
                with self.assertRaisesRegex(self.module.EvidenceError, "not recognized"):
                    self.module.validate_evidence(evidence)

    def test_validator_rejects_bool_integer_aliases_and_unknown_fields(self) -> None:
        base = self.build()
        cases = []
        schema = copy.deepcopy(base)
        schema["schema_version"] = True
        cases.append(schema)
        guest = copy.deepcopy(base)
        guest["contract"]["guest_interface"]["version"] = True
        cases.append(guest)
        width = copy.deepcopy(base)
        width["contract"]["scratch_mmio"]["width_bits"] = True
        cases.append(width)
        summary = copy.deepcopy(base)
        summary["summary"]["failed"] = False
        cases.append(summary)
        unknown = copy.deepcopy(base)
        unknown["inputs"]["raw_log"] = "not allowed"
        cases.append(unknown)
        for evidence in cases:
            with self.subTest(evidence=evidence):
                with self.assertRaises(self.module.EvidenceError):
                    self.module.validate_evidence(evidence)

    def test_schema_is_closed_and_matches_parser_limits(self) -> None:
        schema = json.loads(
            (
                ROOT
                / "schemas/qemu-edu-platform-runtime-evidence-v1.schema.json"
            ).read_text(encoding="utf-8")
        )
        def objects(value):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    yield value
                for child in value.values():
                    yield from objects(child)
            elif isinstance(value, list):
                for child in value:
                    yield from objects(child)

        def strings(value):
            if isinstance(value, dict):
                if value.get("type") == "string":
                    yield value
                for child in value.values():
                    yield from strings(child)
            elif isinstance(value, list):
                for child in value:
                    yield from strings(child)

        for object_schema in objects(schema):
            self.assertFalse(object_schema["additionalProperties"])
            self.assertEqual(
                set(object_schema["required"]),
                set(object_schema["properties"]),
            )
        self.assertEqual(schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(schema["properties"]["tests"]["minItems"], 9)
        self.assertEqual(schema["properties"]["tests"]["maxItems"], 9)
        build = schema["properties"]["build"]["properties"]
        self.assertEqual(build["lab"]["const"], "platform-arm64")
        self.assertEqual(build["machine"]["const"], "qemu-edu-platform-arm64")
        self.assertEqual(build["image"]["const"], "qemu-edu-image")
        self.assertEqual(
            set(schema["properties"]["tests"]["items"]["properties"]["status"]["enum"]),
            self.module.OEQA_STATUSES,
        )
        for string_schema in strings(schema):
            self.assertIn("maxLength", string_schema)
            self.assertLessEqual(
                string_schema["maxLength"], self.module.MAX_STRING_LENGTH
            )


if __name__ == "__main__":
    unittest.main()
