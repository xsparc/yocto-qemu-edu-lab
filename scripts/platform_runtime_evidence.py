#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Collect and validate closed ARM64 platform-lab runtime evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lab_config import LabError, select_lab  # noqa: E402
from runtime_evidence import (  # noqa: E402
    EvidenceError,
    MAX_STRING_LENGTH,
    OEQA_STATUSES,
    PROJECT_NAME,
    SHA1,
    SHA256,
    SUMMARY_KEYS,
    git_state,
    read_object,
    require_boolean,
    require_exact_keys,
    require_integer,
    require_string,
    select_oeqa_result,
    write_evidence,
)


SCHEMA_VERSION = 1
KIND = "qemu-edu-platform-runtime"
GUEST_CONTRACT_NAME = "qemu-edu-platform-sysfs"
SUITE_NAME = "qemu-edu-platform-baseline"
EVIDENCE_PROFILE = "platform-v1"
EXPECTED_TESTS = (
    "qemu_edu_platform.QemuEduPlatformRuntimeTests.test_00_driver_registered",
    "qemu_edu_platform.QemuEduPlatformRuntimeTests.test_01_generated_device_tree_contract",
    "qemu_edu_platform.QemuEduPlatformRuntimeTests.test_02_platform_binding_and_resources",
    "qemu_edu_platform.QemuEduPlatformRuntimeTests.test_03_identification_and_initial_state",
    "qemu_edu_platform.QemuEduPlatformRuntimeTests.test_04_bounded_scratch_roundtrip",
    "qemu_edu_platform.QemuEduPlatformRuntimeTests.test_05_invalid_scratch_preserves_value",
    "qemu_edu_platform.QemuEduPlatformRuntimeTests.test_06_distinct_interrupt_acknowledgement_cycles",
    "qemu_edu_platform.QemuEduPlatformRuntimeTests.test_07_zero_interrupt_is_rejected",
    "qemu_edu_platform.QemuEduPlatformRuntimeTests.test_08_unload_cleanup_and_rebind_recovery",
)


def exact_object(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    require_exact_keys(value, keys, label)
    return value


def passing(statuses: dict[str, str], case_id: str) -> bool:
    return statuses[case_id] == "PASSED"


def build_evidence(
    *,
    oeqa: dict[str, Any],
    repo: Path,
    lab_id: str,
    machine: str,
    image: str,
    oeqa_sha256: str,
    testimage_exit_code: int,
) -> dict[str, Any]:
    repo = repo.resolve()
    selected, manifest, index_digest, manifest_digest = select_lab(repo, lab_id)
    if manifest["runtime"]["evidence_profile"] != EVIDENCE_PROFILE:
        raise EvidenceError(f"lab {selected} is not a platform-v1 evidence source")
    if machine != manifest["build"]["machine"]:
        raise EvidenceError("requested machine differs from the selected lab manifest")
    if manifest["build"]["targets"] != [image]:
        raise EvidenceError("requested image differs from the selected lab manifest")
    if not SHA256.fullmatch(oeqa_sha256):
        raise EvidenceError("OEQA input digest must be a lowercase SHA-256")
    if (
        isinstance(testimage_exit_code, bool)
        or not isinstance(testimage_exit_code, int)
        or not 0 <= testimage_exit_code <= 255
    ):
        raise EvidenceError("testimage exit code must be an integer from 0 to 255")

    result_id, configuration, results = select_oeqa_result(
        oeqa, machine, image, EXPECTED_TESTS
    )
    tests: list[dict[str, Any]] = []
    for test_id in EXPECTED_TESTS:
        report = results.get(test_id)
        if not isinstance(report, dict):
            raise EvidenceError(f"OEQA result is missing required test {test_id}")
        status = require_string(report.get("status"), f"{test_id}.status")
        if status not in OEQA_STATUSES:
            raise EvidenceError(f"{test_id} has unknown OEQA status {status!r}")
        duration = report.get("duration", 0.0)
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(float(duration))
            or duration < 0
        ):
            raise EvidenceError(f"{test_id}.duration must be finite and non-negative")
        tests.append(
            {
                "id": test_id,
                "status": status,
                "duration_seconds": round(float(duration), 6),
            }
        )

    status_by_id = {test["id"]: test["status"] for test in tests}
    counts = Counter(status_by_id.values())
    summary = {"total": len(tests)}
    summary.update({target: counts[source] for source, target in SUMMARY_KEYS.items()})
    revision, dirty = git_state(repo)
    lock_path = repo / "config/sources.lock.json"
    lock = read_object(lock_path)
    release = exact_object(lock.get("release"), {"project", "version", "series"}, "release")
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "contract": {
            "guest_interface": {
                "name": GUEST_CONTRACT_NAME,
                "version": SCHEMA_VERSION,
            },
            "suite": {
                "name": SUITE_NAME,
                "version": SCHEMA_VERSION,
                "test_type": require_string(configuration.get("TEST_TYPE"), "TEST_TYPE"),
            },
            "device_tree": {
                "case_id": EXPECTED_TESTS[1],
                "exercised": passing(status_by_id, EXPECTED_TESTS[1]),
                "compatible": "qemu,edu-platform",
                "mmio_size_bytes": 4096,
                "interrupt_trigger": "level-high",
            },
            "scratch_mmio": {
                "case_id": EXPECTED_TESTS[4],
                "negative_case_id": EXPECTED_TESTS[5],
                "exercised": passing(status_by_id, EXPECTED_TESTS[4]),
                "invalid_input_rejected": passing(status_by_id, EXPECTED_TESTS[5]),
                "width_bits": 32,
            },
            "interrupts": {
                "case_id": EXPECTED_TESTS[6],
                "zero_rejection_case_id": EXPECTED_TESTS[7],
                "exercised": passing(status_by_id, EXPECTED_TESTS[6]),
                "zero_rejected": passing(status_by_id, EXPECTED_TESTS[7]),
                "masks": ["0x00000400", "0x00000800"],
                "acknowledged": passing(status_by_id, EXPECTED_TESTS[6]),
            },
            "lifecycle": {
                "case_id": EXPECTED_TESTS[8],
                "exercised": passing(status_by_id, EXPECTED_TESTS[8]),
                "mechanism": "module-reload",
                "restored": passing(status_by_id, EXPECTED_TESTS[8]),
            },
        },
        "project": {
            "name": PROJECT_NAME,
            "version": (repo / "VERSION").read_text(encoding="utf-8").strip(),
            "revision": revision,
            "dirty": dirty,
        },
        "inputs": {
            "source_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
            "lab_index_sha256": index_digest,
            "lab_manifest_sha256": manifest_digest,
            "oeqa_result_sha256": oeqa_sha256,
            "yocto_version": require_string(release.get("version"), "release.version"),
            "yocto_series": require_string(release.get("series"), "release.series"),
        },
        "build": {
            "lab": selected,
            "machine": machine,
            "image": image,
            "distro": require_string(configuration.get("DISTRO"), "DISTRO"),
            "host_distro": require_string(configuration.get("HOST_DISTRO"), "HOST_DISTRO"),
            "started_at": require_string(configuration.get("STARTTIME"), "STARTTIME"),
            "oeqa_result_id": result_id,
            "testimage_exit_code": testimage_exit_code,
        },
        "result": (
            "passed"
            if counts["PASSED"] == len(tests) and testimage_exit_code == 0
            else "failed"
        ),
        "summary": summary,
        "tests": tests,
    }
    validate_evidence(evidence)
    return evidence


def validate_evidence(evidence: dict[str, Any], *, require_pass: bool = False) -> None:
    require_exact_keys(
        evidence,
        {"schema_version", "kind", "contract", "project", "inputs", "build", "result", "summary", "tests"},
        "evidence",
    )
    if require_integer(evidence["schema_version"], "schema_version", minimum=1) != 1 or evidence["kind"] != KIND:
        raise EvidenceError("unsupported platform evidence schema or kind")

    project = exact_object(evidence["project"], {"name", "version", "revision", "dirty"}, "project")
    if project["name"] != PROJECT_NAME:
        raise EvidenceError("project.name is not recognized")
    require_string(project["version"], "project.version")
    if not SHA1.fullmatch(require_string(project["revision"], "project.revision")):
        raise EvidenceError("project.revision must be a lowercase SHA-1")
    require_boolean(project["dirty"], "project.dirty")

    inputs = exact_object(
        evidence["inputs"],
        {"source_lock_sha256", "lab_index_sha256", "lab_manifest_sha256", "oeqa_result_sha256", "yocto_version", "yocto_series"},
        "inputs",
    )
    for key in ("source_lock_sha256", "lab_index_sha256", "lab_manifest_sha256", "oeqa_result_sha256"):
        if not SHA256.fullmatch(require_string(inputs[key], f"inputs.{key}")):
            raise EvidenceError(f"inputs.{key} must be lowercase SHA-256")
    require_string(inputs["yocto_version"], "inputs.yocto_version")
    require_string(inputs["yocto_series"], "inputs.yocto_series")

    build = exact_object(
        evidence["build"],
        {"lab", "machine", "image", "distro", "host_distro", "started_at", "oeqa_result_id", "testimage_exit_code"},
        "build",
    )
    for key in set(build) - {"testimage_exit_code"}:
        require_string(build[key], f"build.{key}")
    expected_build_identity = {
        "lab": "platform-arm64",
        "machine": "qemu-edu-platform-arm64",
        "image": "qemu-edu-image",
    }
    for key, expected in expected_build_identity.items():
        if build[key] != expected:
            raise EvidenceError(f"build.{key} is not recognized for platform evidence")
    exit_code = require_integer(build["testimage_exit_code"], "build.testimage_exit_code")
    if exit_code > 255:
        raise EvidenceError("build.testimage_exit_code must not exceed 255")

    tests = evidence["tests"]
    if not isinstance(tests, list) or len(tests) != len(EXPECTED_TESTS):
        raise EvidenceError("tests must contain every platform case")
    statuses: list[str] = []
    for expected_id, test in zip(EXPECTED_TESTS, tests, strict=True):
        test = exact_object(test, {"id", "status", "duration_seconds"}, "test")
        if test["id"] != expected_id:
            raise EvidenceError(f"unexpected or out-of-order test id: {test['id']!r}")
        status = require_string(test["status"], f"{expected_id}.status")
        if status not in OEQA_STATUSES:
            raise EvidenceError(f"unsupported test status {status!r}")
        duration = test["duration_seconds"]
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(float(duration)) or duration < 0:
            raise EvidenceError("duration_seconds must be finite and non-negative")
        statuses.append(status)

    contract = exact_object(
        evidence["contract"],
        {"guest_interface", "suite", "device_tree", "scratch_mmio", "interrupts", "lifecycle"},
        "contract",
    )
    guest = exact_object(contract["guest_interface"], {"name", "version"}, "guest_interface")
    suite = exact_object(contract["suite"], {"name", "version", "test_type"}, "suite")
    require_string(guest["name"], "guest_interface.name")
    require_integer(guest["version"], "guest_interface.version")
    require_string(suite["name"], "suite.name")
    require_integer(suite["version"], "suite.version")
    require_string(suite["test_type"], "suite.test_type")
    if guest != {"name": GUEST_CONTRACT_NAME, "version": 1}:
        raise EvidenceError("unsupported platform guest-interface contract")
    if suite != {"name": SUITE_NAME, "version": 1, "test_type": "runtime"}:
        raise EvidenceError("unsupported platform suite contract")
    expected_exercised = [status == "PASSED" for status in statuses]
    expected_contract = {
        "device_tree": {"case_id": EXPECTED_TESTS[1], "exercised": expected_exercised[1], "compatible": "qemu,edu-platform", "mmio_size_bytes": 4096, "interrupt_trigger": "level-high"},
        "scratch_mmio": {"case_id": EXPECTED_TESTS[4], "negative_case_id": EXPECTED_TESTS[5], "exercised": expected_exercised[4], "invalid_input_rejected": expected_exercised[5], "width_bits": 32},
        "interrupts": {"case_id": EXPECTED_TESTS[6], "zero_rejection_case_id": EXPECTED_TESTS[7], "exercised": expected_exercised[6], "zero_rejected": expected_exercised[7], "masks": ["0x00000400", "0x00000800"], "acknowledged": expected_exercised[6]},
        "lifecycle": {"case_id": EXPECTED_TESTS[8], "exercised": expected_exercised[8], "mechanism": "module-reload", "restored": expected_exercised[8]},
    }
    for name, expected in expected_contract.items():
        actual = contract[name]
        if not isinstance(actual, dict):
            raise EvidenceError(f"contract.{name} must be an object")
        require_exact_keys(actual, set(expected), f"contract.{name}")
        for key, expected_value in expected.items():
            value = actual[key]
            if type(expected_value) is bool:
                require_boolean(value, f"contract.{name}.{key}")
            elif type(expected_value) is int:
                require_integer(value, f"contract.{name}.{key}")
            elif isinstance(expected_value, str):
                require_string(value, f"contract.{name}.{key}")
            elif isinstance(expected_value, list):
                if not isinstance(value, list) or not all(
                    isinstance(item, str) for item in value
                ):
                    raise EvidenceError(f"contract.{name}.{key} must be a string array")
        if actual != expected:
            raise EvidenceError(f"contract.{name} semantics do not match the suite")

    summary = exact_object(evidence["summary"], {"total", *SUMMARY_KEYS.values()}, "summary")
    for key in summary:
        require_integer(summary[key], f"summary.{key}")
    counts = Counter(statuses)
    expected_summary = {"total": len(statuses)}
    expected_summary.update({target: counts[source] for source, target in SUMMARY_KEYS.items()})
    if summary != expected_summary:
        raise EvidenceError("summary does not match test statuses")
    expected_result = "passed" if counts["PASSED"] == len(statuses) and exit_code == 0 else "failed"
    if evidence["result"] != expected_result:
        raise EvidenceError("result does not match test statuses")
    if require_pass and evidence["result"] != "passed":
        raise EvidenceError("platform evidence does not record a passing suite")
    if require_pass and project["dirty"]:
        raise EvidenceError("passing platform evidence requires a clean project tree")
    if require_pass and not all(
        (
            expected_contract["device_tree"]["exercised"],
            expected_contract["scratch_mmio"]["exercised"],
            expected_contract["scratch_mmio"]["invalid_input_rejected"],
            expected_contract["interrupts"]["exercised"],
            expected_contract["interrupts"]["zero_rejected"],
            expected_contract["lifecycle"]["exercised"],
        )
    ):
        raise EvidenceError("passing platform evidence requires every bounded path")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect", help="convert the current platform OEQA run")
    collect.add_argument("--oeqa", required=True)
    collect.add_argument("--output", required=True)
    collect.add_argument("--lab", required=True)
    collect.add_argument("--machine", required=True)
    collect.add_argument("--image", required=True)
    collect.add_argument("--testimage-exit-code", required=True, type=int)
    validate = subparsers.add_parser("validate", help="validate platform evidence")
    validate.add_argument("path")
    validate.add_argument("--require-pass", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "collect":
            oeqa_path = Path(args.oeqa)
            evidence = build_evidence(
                oeqa=read_object(oeqa_path),
                repo=Path(args.repo),
                lab_id=args.lab,
                machine=args.machine,
                image=args.image,
                oeqa_sha256=hashlib.sha256(oeqa_path.read_bytes()).hexdigest(),
                testimage_exit_code=args.testimage_exit_code,
            )
            write_evidence(Path(args.output), evidence)
            print(f"platform-runtime-evidence: {evidence['result']}: {args.output}")
            return 0
        evidence = read_object(Path(args.path))
        validate_evidence(evidence, require_pass=args.require_pass)
        print(f"platform-runtime-evidence: PASS: {args.path}")
        return 0
    except (EvidenceError, LabError, OSError, subprocess.CalledProcessError) as exc:
        print(f"platform-runtime-evidence: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
