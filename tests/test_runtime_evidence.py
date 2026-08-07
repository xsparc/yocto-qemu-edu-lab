# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT

from __future__ import annotations

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "runtime_evidence", ROOT / "scripts/runtime_evidence.py"
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def oeqa_record(started_at: str = "20260808010203") -> dict[str, object]:
    results = {
        test_id: {"status": "PASSED", "duration": index / 10}
        for index, test_id in enumerate(MODULE.EXPECTED_TESTS, start=1)
    }
    result_id = f"runtime_qemu-edu-image_qemu-edu-x86-64_{started_at}"
    return {
        result_id: {
            "configuration": {
                "MACHINE": "qemu-edu-x86-64",
                "IMAGE_BASENAME": "qemu-edu-image",
                "DISTRO": "poky",
                "HOST_DISTRO": "ubuntu-24.04",
                "STARTTIME": started_at,
                "TEST_TYPE": "runtime",
            },
            "result": results,
        }
    }


class RuntimeEvidenceTests(unittest.TestCase):
    def build(self, oeqa: dict[str, object] | None = None) -> dict[str, object]:
        return MODULE.build_evidence(
            oeqa=oeqa or oeqa_record(),
            repo=ROOT,
            machine="qemu-edu-x86-64",
            image="qemu-edu-image",
            oeqa_sha256="a" * 64,
            testimage_exit_code=0,
        )

    def test_passing_oeqa_result_builds_closed_evidence(self) -> None:
        evidence = self.build()
        evidence["project"]["dirty"] = False
        MODULE.validate_evidence(evidence, require_pass=True)
        self.assertEqual(evidence["result"], "passed")
        self.assertEqual(evidence["summary"]["passed"], len(MODULE.EXPECTED_TESTS))
        self.assertNotIn("log", str(evidence).lower())
        self.assertTrue(
            evidence["contract"]["negative_paths"]["factorial_timeout"]["exercised"]
        )

    def test_latest_matching_oeqa_result_is_selected(self) -> None:
        older = oeqa_record("20260808010203")
        newer = oeqa_record("20260808020304")
        merged = {**newer, **older}
        evidence = self.build(merged)
        self.assertEqual(evidence["build"]["started_at"], "20260808020304")

    def test_missing_required_case_is_rejected(self) -> None:
        oeqa = oeqa_record()
        record = next(iter(oeqa.values()))
        del record["result"][MODULE.EXPECTED_TESTS[-1]]
        with self.assertRaisesRegex(MODULE.EvidenceError, "missing required test"):
            self.build(oeqa)

    def test_failed_case_produces_failure_evidence(self) -> None:
        oeqa = oeqa_record()
        record = next(iter(oeqa.values()))
        record["result"][MODULE.EXPECTED_TESTS[4]]["status"] = "FAILED"
        evidence = self.build(oeqa)
        MODULE.validate_evidence(evidence)
        self.assertEqual(evidence["result"], "failed")
        with self.assertRaisesRegex(MODULE.EvidenceError, "does not record a passing"):
            MODULE.validate_evidence(evidence, require_pass=True)

    def test_nonzero_testimage_exit_cannot_produce_a_pass(self) -> None:
        evidence = MODULE.build_evidence(
            oeqa=oeqa_record(),
            repo=ROOT,
            machine="qemu-edu-x86-64",
            image="qemu-edu-image",
            oeqa_sha256="b" * 64,
            testimage_exit_code=1,
        )
        self.assertEqual(evidence["result"], "failed")
        self.assertEqual(evidence["build"]["testimage_exit_code"], 1)

    def test_skipped_negative_path_is_explicit_and_cannot_pass(self) -> None:
        oeqa = oeqa_record()
        record = next(iter(oeqa.values()))
        record["result"][MODULE.EXPECTED_TESTS[9]]["status"] = "SKIPPED"
        evidence = self.build(oeqa)
        timeout = evidence["contract"]["negative_paths"]["factorial_timeout"]
        self.assertFalse(timeout["exercised"])
        self.assertEqual(evidence["result"], "failed")

    def test_failed_negative_paths_do_not_claim_completed_mechanisms(self) -> None:
        oeqa = oeqa_record()
        record = next(iter(oeqa.values()))
        record["result"][MODULE.EXPECTED_TESTS[9]]["status"] = "ERROR"
        record["result"][MODULE.EXPECTED_TESTS[10]]["status"] = "FAILED"
        evidence = self.build(oeqa)
        timeout = evidence["contract"]["negative_paths"]["factorial_timeout"]
        absence = evidence["contract"]["negative_paths"]["device_absence"]
        self.assertFalse(timeout["exercised"])
        self.assertFalse(timeout["fault_injected"])
        self.assertFalse(absence["exercised"])
        MODULE.validate_evidence(evidence)

    def test_boolean_integer_aliases_are_rejected(self) -> None:
        mutations = (
            (("schema_version",), True),
            (("contract", "guest_interface", "version"), True),
            (("contract", "suite", "version"), True),
            (("contract", "negative_paths", "factorial_timeout", "exercised"), 1),
            (("contract", "negative_paths", "factorial_timeout", "fault_injected"), 1),
            (("contract", "negative_paths", "device_absence", "exercised"), 1),
            (
                (
                    "contract",
                    "negative_paths",
                    "device_absence",
                    "cold_boot_without_device",
                ),
                0,
            ),
            (("summary", "failed"), False),
        )
        for path, replacement in mutations:
            with self.subTest(path=path):
                evidence = self.build()
                target = evidence
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = replacement
                with self.assertRaises(MODULE.EvidenceError):
                    MODULE.validate_evidence(evidence)

    def test_strings_over_contract_limit_are_rejected(self) -> None:
        evidence = self.build()
        evidence["project"]["version"] = "x" * (MODULE.MAX_STRING_LENGTH + 1)
        with self.assertRaisesRegex(MODULE.EvidenceError, "exceeds"):
            MODULE.validate_evidence(evidence)

    def test_dirty_tree_cannot_qualify_as_passing_evidence(self) -> None:
        evidence = self.build()
        evidence["project"]["dirty"] = True
        with self.assertRaisesRegex(MODULE.EvidenceError, "clean project tree"):
            MODULE.validate_evidence(evidence, require_pass=True)

    def test_invalid_native_digest_is_rejected(self) -> None:
        with self.assertRaisesRegex(MODULE.EvidenceError, "digest"):
            MODULE.build_evidence(
                oeqa=oeqa_record(),
                repo=ROOT,
                machine="qemu-edu-x86-64",
                image="qemu-edu-image",
                oeqa_sha256="not-a-digest",
                testimage_exit_code=0,
            )

    def test_unknown_fields_and_inconsistent_summary_are_rejected(self) -> None:
        evidence = self.build()
        unknown = copy.deepcopy(evidence)
        unknown["private_log"] = "must not be accepted"
        with self.assertRaisesRegex(MODULE.EvidenceError, "keys differ"):
            MODULE.validate_evidence(unknown)
        evidence["summary"]["passed"] -= 1
        with self.assertRaisesRegex(MODULE.EvidenceError, "summary"):
            MODULE.validate_evidence(evidence)

    def test_written_evidence_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            evidence = self.build()
            evidence["project"]["dirty"] = False
            MODULE.write_evidence(path, evidence)
            MODULE.validate_evidence(MODULE.read_object(path), require_pass=True)

    def test_duplicate_json_keys_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema_version": 1, "schema_version": 2}', encoding="utf-8")
            with self.assertRaisesRegex(MODULE.EvidenceError, "duplicate JSON key"):
                MODULE.read_object(path)

    def test_oversized_json_is_rejected_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "oversized.json"
            path.write_bytes(b"{" + b" " * MODULE.MAX_JSON_BYTES + b"}")
            with self.assertRaisesRegex(MODULE.EvidenceError, "safety limit"):
                MODULE.read_object(path)


if __name__ == "__main__":
    unittest.main()
