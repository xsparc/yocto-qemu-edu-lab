#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Collect version-3 and validate supported QEMU EDU runtime evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 3
KIND = "qemu-edu-runtime"
PROJECT_NAME = "yocto-qemu-edu-lab"
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_STRING_LENGTH = 4096
MAX_JSON_DEPTH = 64
MAX_JSON_ITEMS = 100_000
GUEST_CONTRACT_NAME = "qemu-edu-sysfs"
SUITE_NAME = "qemu-edu-baseline"
V1_EXPECTED_TESTS = (
    "qemu_edu.QemuEduRuntimeTests.test_00_driver_registered",
    "qemu_edu.QemuEduRuntimeTests.test_01_pci_device_bound",
    "qemu_edu.QemuEduRuntimeTests.test_02_identification_register",
    "qemu_edu.QemuEduRuntimeTests.test_03_initial_operation_state",
    "qemu_edu.QemuEduRuntimeTests.test_04_liveness_inversion",
    "qemu_edu.QemuEduRuntimeTests.test_05_factorial_boundaries",
    "qemu_edu.QemuEduRuntimeTests.test_06_invalid_factorial_inputs",
    "qemu_edu.QemuEduRuntimeTests.test_07_legacy_interrupt",
    "qemu_edu.QemuEduRuntimeTests.test_08_zero_interrupt_rejected",
    "qemu_edu.QemuEduRuntimeTests.test_09_factorial_timeout",
    "qemu_edu.QemuEduRuntimeTests.test_10_removed_device_diagnostic",
)
V2_EXPECTED_TESTS = (
    "qemu_edu.QemuEduRuntimeTests.test_00_driver_registered",
    "qemu_edu.QemuEduRuntimeTests.test_01_pci_device_bound",
    "qemu_edu.QemuEduRuntimeTests.test_02_identification_register",
    "qemu_edu.QemuEduRuntimeTests.test_03_initial_operation_state",
    "qemu_edu.QemuEduRuntimeTests.test_04_liveness_inversion",
    "qemu_edu.QemuEduRuntimeTests.test_05_factorial_boundaries",
    "qemu_edu.QemuEduRuntimeTests.test_06_invalid_factorial_inputs",
    "qemu_edu.QemuEduRuntimeTests.test_07_default_and_required_msi",
    "qemu_edu.QemuEduRuntimeTests.test_08_explicit_intx_comparison",
    "qemu_edu.QemuEduRuntimeTests.test_09_automatic_intx_fallback",
    "qemu_edu.QemuEduRuntimeTests.test_10_required_msi_failure_and_cleanup",
    "qemu_edu.QemuEduRuntimeTests.test_11_zero_interrupt_rejected",
    "qemu_edu.QemuEduRuntimeTests.test_12_factorial_timeout",
    "qemu_edu.QemuEduRuntimeTests.test_13_removed_device_diagnostic",
)
EXPECTED_TESTS = V2_EXPECTED_TESTS + (
    "qemu_edu.QemuEduRuntimeTests.test_14_dma_contract",
    "qemu_edu.QemuEduRuntimeTests.test_15_dma_roundtrip_boundaries",
    "qemu_edu.QemuEduRuntimeTests.test_16_invalid_dma_inputs",
    "qemu_edu.QemuEduRuntimeTests.test_17_dma_timeout_and_recovery",
    "qemu_edu.QemuEduRuntimeTests.test_18_dma_teardown_and_rebind",
)
SUPPORTED_TESTS = {
    1: V1_EXPECTED_TESTS,
    2: V2_EXPECTED_TESTS,
    3: EXPECTED_TESTS,
}
OEQA_STATUSES = {
    "PASSED",
    "FAILED",
    "ERROR",
    "SKIPPED",
    "EXPECTEDFAIL",
    "UNKNOWN",
}
SUMMARY_KEYS = {
    "PASSED": "passed",
    "FAILED": "failed",
    "ERROR": "errors",
    "SKIPPED": "skipped",
    "EXPECTEDFAIL": "expected_failures",
    "UNKNOWN": "unknown",
}
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


class EvidenceError(ValueError):
    """The input or evidence violates the closed runtime contract."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise EvidenceError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _reject_constant(value: str) -> Any:
    raise EvidenceError(f"unsupported JSON constant: {value}")


def _validate_json_shape(value: Any) -> None:
    pending: list[tuple[Any, int]] = [(value, 1)]
    items = 0
    while pending:
        current, depth = pending.pop()
        items += 1
        if items > MAX_JSON_ITEMS:
            raise EvidenceError(f"JSON input exceeds {MAX_JSON_ITEMS} values")
        if depth > MAX_JSON_DEPTH:
            raise EvidenceError(f"JSON input exceeds depth {MAX_JSON_DEPTH}")
        if isinstance(current, str):
            if len(current) > MAX_STRING_LENGTH:
                raise EvidenceError(
                    f"JSON string exceeds {MAX_STRING_LENGTH} characters"
                )
            if any(0xD800 <= ord(character) <= 0xDFFF for character in current):
                raise EvidenceError("JSON contains an invalid Unicode surrogate")
        elif isinstance(current, dict):
            pending.extend((key, depth + 1) for key in current)
            pending.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            pending.extend((item, depth + 1) for item in current)
        elif isinstance(current, float) and not math.isfinite(current):
            raise EvidenceError("JSON contains a non-finite number")


def parse_object_bytes(
    raw: bytes,
    label: str = "JSON input",
    *,
    max_bytes: int = MAX_JSON_BYTES,
) -> dict[str, Any]:
    """Parse one bounded evidence object without reopening its source path."""
    if len(raw) > max_bytes:
        raise EvidenceError(f"{label} exceeds the {max_bytes}-byte safety limit")
    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EvidenceError(f"could not parse {label}: {exc}") from exc
    _validate_json_shape(value)
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must contain a JSON object")
    return value


def read_object(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_JSON_BYTES + 1)
    except OSError as exc:
        raise EvidenceError(f"could not read JSON object {path}: {exc}") from exc
    return parse_object_bytes(raw, str(path))


def require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise EvidenceError(f"{label} keys differ; missing={missing}, extra={extra}")


def require_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{label} must be a non-empty string")
    if len(value) > MAX_STRING_LENGTH:
        raise EvidenceError(f"{label} exceeds {MAX_STRING_LENGTH} characters")
    return value


def require_integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvidenceError(f"{label} must be an integer of at least {minimum}")
    return value


def require_boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise EvidenceError(f"{label} must be boolean")
    return value


def git_state(repo: Path) -> tuple[str, bool]:
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    if not SHA1.fullmatch(revision):
        raise EvidenceError(f"repository revision is not a SHA-1 commit: {revision!r}")
    return revision, dirty


def select_oeqa_result(
    data: dict[str, Any], machine: str, image: str,
    expected_tests: tuple[str, ...] = EXPECTED_TESTS,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    candidates: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
    for result_id, record in data.items():
        if not isinstance(result_id, str) or not isinstance(record, dict):
            continue
        configuration = record.get("configuration")
        results = record.get("result")
        if not isinstance(configuration, dict) or not isinstance(results, dict):
            continue
        if configuration.get("MACHINE") != machine:
            continue
        if configuration.get("IMAGE_BASENAME") != image:
            continue
        if not any(test_id in results for test_id in expected_tests):
            continue
        started_at = require_string(configuration.get("STARTTIME"), "STARTTIME")
        candidates.append((started_at, result_id, configuration, results))
    if not candidates:
        raise EvidenceError(
            f"no OEQA result contains the {image}/{machine} QEMU EDU suite"
        )
    _, result_id, configuration, results = max(candidates, key=lambda item: item[:2])
    return result_id, configuration, results


def build_evidence(
    *,
    oeqa: dict[str, Any],
    repo: Path,
    machine: str,
    image: str,
    oeqa_sha256: str,
    testimage_exit_code: int,
) -> dict[str, Any]:
    repo = repo.resolve()
    result_id, configuration, results = select_oeqa_result(oeqa, machine, image)
    if not SHA256.fullmatch(oeqa_sha256):
        raise EvidenceError("OEQA input digest must be a lowercase SHA-256")
    if isinstance(testimage_exit_code, bool) or not isinstance(testimage_exit_code, int):
        raise EvidenceError("testimage exit code must be an integer")
    if testimage_exit_code < 0 or testimage_exit_code > 255:
        raise EvidenceError("testimage exit code must be between 0 and 255")
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

    counts = Counter(test["status"] for test in tests)
    status_by_id = {test["id"]: test["status"] for test in tests}
    summary = {"total": len(tests)}
    summary.update({target: counts[source] for source, target in SUMMARY_KEYS.items()})
    revision, dirty = git_state(repo)
    lock_path = repo / "config/sources.lock.json"
    lock = read_object(lock_path)
    release = lock.get("release")
    if not isinstance(release, dict):
        raise EvidenceError("source lock has no release object")
    lock_digest = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
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
                "test_type": require_string(
                    configuration.get("TEST_TYPE"), "TEST_TYPE"
                ),
            },
            "interrupt_paths": {
                "default_msi": {
                    "case_id": EXPECTED_TESTS[7],
                    "exercised": status_by_id[EXPECTED_TESTS[7]] == "PASSED",
                    "requested": "auto",
                    "selected": "msi",
                },
                "explicit_intx": {
                    "case_id": EXPECTED_TESTS[8],
                    "exercised": status_by_id[EXPECTED_TESTS[8]] == "PASSED",
                    "requested": "intx",
                    "selected": "intx",
                },
                "automatic_fallback": {
                    "case_id": EXPECTED_TESTS[9],
                    "exercised": status_by_id[EXPECTED_TESTS[9]] == "PASSED",
                    "requested": "auto",
                    "selected": "intx",
                    "mechanism": "pci-device-msi_bus",
                },
                "required_msi_failure": {
                    "case_id": EXPECTED_TESTS[10],
                    "exercised": status_by_id[EXPECTED_TESTS[10]] == "PASSED",
                    "requested": "msi",
                    "device_unbound": status_by_id[EXPECTED_TESTS[10]] == "PASSED",
                    "mechanism": "pci-device-msi_bus",
                },
                "cleanup_recovery": {
                    "case_id": EXPECTED_TESTS[10],
                    "exercised": status_by_id[EXPECTED_TESTS[10]] == "PASSED",
                    "restored": "auto-msi",
                },
            },
            "negative_paths": {
                "factorial_timeout": {
                    "case_id": EXPECTED_TESTS[12],
                    "exercised": status_by_id[EXPECTED_TESTS[12]] == "PASSED",
                    "fault_injected": status_by_id[EXPECTED_TESTS[12]] == "PASSED",
                    "mechanism": "module-parameter:force_factorial_timeout",
                },
                "device_absence": {
                    "case_id": EXPECTED_TESTS[13],
                    "exercised": status_by_id[EXPECTED_TESTS[13]] == "PASSED",
                    "mechanism": "linux-pci-hot-remove",
                    "cold_boot_without_device": False,
                },
            },
            "dma_paths": {
                "bounded_interface": {
                    "case_id": EXPECTED_TESTS[14],
                    "exercised": status_by_id[EXPECTED_TESTS[14]] == "PASSED",
                    "mask_bits": 28,
                    "buffer_size_bytes": 4096,
                    "length_only": True,
                    "address_exposed": False,
                },
                "roundtrip_boundaries": {
                    "case_id": EXPECTED_TESTS[15],
                    "exercised": status_by_id[EXPECTED_TESTS[15]] == "PASSED",
                    "minimum_length": 1,
                    "maximum_length": 4096,
                    "directions": ["ram-to-edu", "edu-to-ram"],
                    "completion_irq_status": "0x00000100",
                    "interrupts_per_roundtrip": 2,
                },
                "input_rejection": {
                    "case_id": EXPECTED_TESTS[16],
                    "exercised": status_by_id[EXPECTED_TESTS[16]] == "PASSED",
                    "classes": ["zero", "over-limit", "negative", "malformed"],
                    "preserves_last_result": True,
                },
                "timeout_recovery": {
                    "case_id": EXPECTED_TESTS[17],
                    "exercised": status_by_id[EXPECTED_TESTS[17]] == "PASSED",
                    "fault_injected": status_by_id[EXPECTED_TESTS[17]] == "PASSED",
                    "mechanism": "module-parameter:force_dma_timeout",
                    "restored": "default-auto-msi-and-dma",
                },
                "teardown_rebind": {
                    "case_id": EXPECTED_TESTS[18],
                    "exercised": status_by_id[EXPECTED_TESTS[18]] == "PASSED",
                    "restored": "default-auto-msi-and-dma",
                },
            },
        },
        "project": {
            "name": PROJECT_NAME,
            "version": version,
            "revision": revision,
            "dirty": dirty,
        },
        "inputs": {
            "source_lock_sha256": lock_digest,
            "oeqa_result_sha256": oeqa_sha256,
            "yocto_version": require_string(release.get("version"), "release.version"),
            "yocto_series": require_string(release.get("series"), "release.series"),
        },
        "build": {
            "machine": machine,
            "image": image,
            "distro": require_string(configuration.get("DISTRO"), "DISTRO"),
            "host_distro": require_string(
                configuration.get("HOST_DISTRO"), "HOST_DISTRO"
            ),
            "started_at": require_string(
                configuration.get("STARTTIME"), "STARTTIME"
            ),
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


def validate_evidence(
    evidence: dict[str, Any],
    *,
    require_pass: bool = False,
    expected_revision: str | None = None,
) -> None:
    require_exact_keys(
        evidence,
        {
            "schema_version",
            "kind",
            "contract",
            "project",
            "inputs",
            "build",
            "result",
            "summary",
            "tests",
        },
        "evidence",
    )
    schema_version = require_integer(evidence["schema_version"], "schema_version")
    expected_tests = SUPPORTED_TESTS.get(schema_version)
    if expected_tests is None or evidence["kind"] != KIND:
        raise EvidenceError("unsupported evidence schema or kind")

    contract = evidence["contract"]
    if not isinstance(contract, dict):
        raise EvidenceError("contract must be an object")
    contract_keys = {"guest_interface", "suite", "negative_paths"}
    if schema_version >= 2:
        contract_keys.add("interrupt_paths")
    if schema_version == 3:
        contract_keys.add("dma_paths")
    require_exact_keys(contract, contract_keys, "contract")
    guest = contract["guest_interface"]
    if not isinstance(guest, dict):
        raise EvidenceError("contract.guest_interface must be an object")
    require_exact_keys(guest, {"name", "version"}, "contract.guest_interface")
    if (
        guest.get("name") != GUEST_CONTRACT_NAME
        or require_integer(guest.get("version"), "contract.guest_interface.version")
        != schema_version
    ):
        raise EvidenceError("unsupported guest-interface contract")
    suite = contract["suite"]
    if not isinstance(suite, dict):
        raise EvidenceError("contract.suite must be an object")
    require_exact_keys(suite, {"name", "version", "test_type"}, "contract.suite")
    if (
        suite.get("name") != SUITE_NAME
        or require_integer(suite.get("version"), "contract.suite.version")
        != schema_version
        or suite.get("test_type") != "runtime"
    ):
        raise EvidenceError("unsupported runtime suite contract")

    project = evidence["project"]
    if not isinstance(project, dict):
        raise EvidenceError("project must be an object")
    require_exact_keys(project, {"name", "version", "revision", "dirty"}, "project")
    if project["name"] != PROJECT_NAME:
        raise EvidenceError("project.name is not recognized")
    require_string(project["version"], "project.version")
    if not isinstance(project["dirty"], bool):
        raise EvidenceError("project.dirty must be boolean")
    project_revision = require_string(project["revision"], "project.revision")
    if not SHA1.fullmatch(project_revision):
        raise EvidenceError("project.revision must be a lowercase SHA-1")
    if expected_revision is not None:
        expected_revision = require_string(expected_revision, "required revision")
        if not SHA1.fullmatch(expected_revision):
            raise EvidenceError("required revision must be a lowercase SHA-1")
        if project_revision != expected_revision:
            raise EvidenceError(
                f"project.revision is {project_revision}, required {expected_revision}"
            )

    inputs = evidence["inputs"]
    if not isinstance(inputs, dict):
        raise EvidenceError("inputs must be an object")
    require_exact_keys(
        inputs,
        {"source_lock_sha256", "oeqa_result_sha256", "yocto_version", "yocto_series"},
        "inputs",
    )
    if not SHA256.fullmatch(
        require_string(inputs["source_lock_sha256"], "inputs.source_lock_sha256")
    ):
        raise EvidenceError("inputs.source_lock_sha256 must be lowercase SHA-256")
    if not SHA256.fullmatch(
        require_string(inputs["oeqa_result_sha256"], "inputs.oeqa_result_sha256")
    ):
        raise EvidenceError("inputs.oeqa_result_sha256 must be lowercase SHA-256")
    require_string(inputs["yocto_version"], "inputs.yocto_version")
    require_string(inputs["yocto_series"], "inputs.yocto_series")

    build = evidence["build"]
    if not isinstance(build, dict):
        raise EvidenceError("build must be an object")
    require_exact_keys(
        build,
        {
            "machine",
            "image",
            "distro",
            "host_distro",
            "started_at",
            "oeqa_result_id",
            "testimage_exit_code",
        },
        "build",
    )
    for key in set(build) - {"testimage_exit_code"}:
        require_string(build[key], f"build.{key}")
    exit_code = build["testimage_exit_code"]
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise EvidenceError("build.testimage_exit_code must be an integer")
    if exit_code < 0 or exit_code > 255:
        raise EvidenceError("build.testimage_exit_code must be between 0 and 255")

    tests = evidence["tests"]
    if not isinstance(tests, list) or len(tests) != len(expected_tests):
        raise EvidenceError("tests must contain every required QEMU EDU case")
    statuses: list[str] = []
    for expected_id, test in zip(expected_tests, tests, strict=True):
        if not isinstance(test, dict):
            raise EvidenceError("every test must be an object")
        require_exact_keys(test, {"id", "status", "duration_seconds"}, "test")
        if test["id"] != expected_id:
            raise EvidenceError(f"unexpected or out-of-order test id: {test['id']!r}")
        status = require_string(test["status"], f"{expected_id}.status")
        if status not in OEQA_STATUSES:
            raise EvidenceError(f"unsupported test status {status!r}")
        duration = test["duration_seconds"]
        if (
            isinstance(duration, bool)
            or not isinstance(duration, (int, float))
            or not math.isfinite(float(duration))
            or duration < 0
        ):
            raise EvidenceError("duration_seconds must be finite and non-negative")
        statuses.append(status)

    negative_paths = contract["negative_paths"]
    if not isinstance(negative_paths, dict):
        raise EvidenceError("contract.negative_paths must be an object")
    require_exact_keys(
        negative_paths, {"factorial_timeout", "device_absence"}, "negative_paths"
    )
    timeout = negative_paths["factorial_timeout"]
    absence = negative_paths["device_absence"]
    if not isinstance(timeout, dict) or not isinstance(absence, dict):
        raise EvidenceError("negative-path declarations must be objects")
    require_exact_keys(
        timeout,
        {"case_id", "exercised", "fault_injected", "mechanism"},
        "factorial_timeout",
    )
    require_exact_keys(
        absence,
        {"case_id", "exercised", "mechanism", "cold_boot_without_device"},
        "device_absence",
    )
    require_boolean(timeout["exercised"], "factorial_timeout.exercised")
    require_boolean(timeout["fault_injected"], "factorial_timeout.fault_injected")
    require_boolean(absence["exercised"], "device_absence.exercised")
    require_boolean(
        absence["cold_boot_without_device"],
        "device_absence.cold_boot_without_device",
    )
    timeout_index = 9 if schema_version == 1 else 12
    absence_index = 10 if schema_version == 1 else 13
    expected_timeout_exercised = statuses[timeout_index] == "PASSED"
    expected_absence_exercised = statuses[absence_index] == "PASSED"
    if timeout != {
        "case_id": expected_tests[timeout_index],
        "exercised": expected_timeout_exercised,
        "fault_injected": expected_timeout_exercised,
        "mechanism": "module-parameter:force_factorial_timeout",
    }:
        raise EvidenceError("factorial-timeout semantics do not match the suite")
    if absence != {
        "case_id": expected_tests[absence_index],
        "exercised": expected_absence_exercised,
        "mechanism": "linux-pci-hot-remove",
        "cold_boot_without_device": False,
    }:
        raise EvidenceError("device-absence semantics do not match the suite")

    interrupt_paths = None
    if schema_version >= 2:
        interrupt_paths = contract["interrupt_paths"]
        if not isinstance(interrupt_paths, dict):
            raise EvidenceError("contract.interrupt_paths must be an object")
        require_exact_keys(
            interrupt_paths,
            {
                "default_msi",
                "explicit_intx",
                "automatic_fallback",
                "required_msi_failure",
                "cleanup_recovery",
            },
            "interrupt_paths",
        )
        for name, expected_keys in {
            "default_msi": {"case_id", "exercised", "requested", "selected"},
            "explicit_intx": {"case_id", "exercised", "requested", "selected"},
            "automatic_fallback": {
                "case_id",
                "exercised",
                "requested",
                "selected",
                "mechanism",
            },
            "required_msi_failure": {
                "case_id",
                "exercised",
                "requested",
                "device_unbound",
                "mechanism",
            },
            "cleanup_recovery": {"case_id", "exercised", "restored"},
        }.items():
            path = interrupt_paths[name]
            if not isinstance(path, dict):
                raise EvidenceError(f"interrupt_paths.{name} must be an object")
            require_exact_keys(path, expected_keys, f"interrupt_paths.{name}")
            require_boolean(path["exercised"], f"interrupt_paths.{name}.exercised")
        require_boolean(
            interrupt_paths["required_msi_failure"]["device_unbound"],
            "interrupt_paths.required_msi_failure.device_unbound",
        )
        expected_interrupt_paths = {
            "default_msi": {
                "case_id": expected_tests[7],
                "exercised": statuses[7] == "PASSED",
                "requested": "auto",
                "selected": "msi",
            },
            "explicit_intx": {
                "case_id": expected_tests[8],
                "exercised": statuses[8] == "PASSED",
                "requested": "intx",
                "selected": "intx",
            },
            "automatic_fallback": {
                "case_id": expected_tests[9],
                "exercised": statuses[9] == "PASSED",
                "requested": "auto",
                "selected": "intx",
                "mechanism": "pci-device-msi_bus",
            },
            "required_msi_failure": {
                "case_id": expected_tests[10],
                "exercised": statuses[10] == "PASSED",
                "requested": "msi",
                "device_unbound": statuses[10] == "PASSED",
                "mechanism": "pci-device-msi_bus",
            },
            "cleanup_recovery": {
                "case_id": expected_tests[10],
                "exercised": statuses[10] == "PASSED",
                "restored": "auto-msi",
            },
        }
        if interrupt_paths != expected_interrupt_paths:
            raise EvidenceError("interrupt-path semantics do not match the suite")

    dma_paths = None
    if schema_version == 3:
        dma_paths = contract["dma_paths"]
        if not isinstance(dma_paths, dict):
            raise EvidenceError("contract.dma_paths must be an object")
        require_exact_keys(
            dma_paths,
            {
                "bounded_interface",
                "roundtrip_boundaries",
                "input_rejection",
                "timeout_recovery",
                "teardown_rebind",
            },
            "dma_paths",
        )
        for name, expected_keys in {
            "bounded_interface": {
                "case_id", "exercised", "mask_bits", "buffer_size_bytes",
                "length_only", "address_exposed",
            },
            "roundtrip_boundaries": {
                "case_id", "exercised", "minimum_length", "maximum_length",
                "directions", "completion_irq_status", "interrupts_per_roundtrip",
            },
            "input_rejection": {
                "case_id", "exercised", "classes", "preserves_last_result",
            },
            "timeout_recovery": {
                "case_id", "exercised", "fault_injected", "mechanism", "restored",
            },
            "teardown_rebind": {"case_id", "exercised", "restored"},
        }.items():
            path = dma_paths[name]
            if not isinstance(path, dict):
                raise EvidenceError(f"dma_paths.{name} must be an object")
            require_exact_keys(path, expected_keys, f"dma_paths.{name}")
            require_boolean(path["exercised"], f"dma_paths.{name}.exercised")
        require_boolean(
            dma_paths["bounded_interface"]["length_only"],
            "dma_paths.bounded_interface.length_only",
        )
        require_boolean(
            dma_paths["bounded_interface"]["address_exposed"],
            "dma_paths.bounded_interface.address_exposed",
        )
        require_boolean(
            dma_paths["input_rejection"]["preserves_last_result"],
            "dma_paths.input_rejection.preserves_last_result",
        )
        require_boolean(
            dma_paths["timeout_recovery"]["fault_injected"],
            "dma_paths.timeout_recovery.fault_injected",
        )
        for path_name, key in (
            ("bounded_interface", "mask_bits"),
            ("bounded_interface", "buffer_size_bytes"),
            ("roundtrip_boundaries", "minimum_length"),
            ("roundtrip_boundaries", "maximum_length"),
            ("roundtrip_boundaries", "interrupts_per_roundtrip"),
        ):
            require_integer(
                dma_paths[path_name][key], f"dma_paths.{path_name}.{key}"
            )
        expected_dma_paths = {
            "bounded_interface": {
                "case_id": expected_tests[14],
                "exercised": statuses[14] == "PASSED",
                "mask_bits": 28,
                "buffer_size_bytes": 4096,
                "length_only": True,
                "address_exposed": False,
            },
            "roundtrip_boundaries": {
                "case_id": expected_tests[15],
                "exercised": statuses[15] == "PASSED",
                "minimum_length": 1,
                "maximum_length": 4096,
                "directions": ["ram-to-edu", "edu-to-ram"],
                "completion_irq_status": "0x00000100",
                "interrupts_per_roundtrip": 2,
            },
            "input_rejection": {
                "case_id": expected_tests[16],
                "exercised": statuses[16] == "PASSED",
                "classes": ["zero", "over-limit", "negative", "malformed"],
                "preserves_last_result": True,
            },
            "timeout_recovery": {
                "case_id": expected_tests[17],
                "exercised": statuses[17] == "PASSED",
                "fault_injected": statuses[17] == "PASSED",
                "mechanism": "module-parameter:force_dma_timeout",
                "restored": "default-auto-msi-and-dma",
            },
            "teardown_rebind": {
                "case_id": expected_tests[18],
                "exercised": statuses[18] == "PASSED",
                "restored": "default-auto-msi-and-dma",
            },
        }
        if dma_paths != expected_dma_paths:
            raise EvidenceError("DMA-path semantics do not match the suite")

    summary = evidence["summary"]
    if not isinstance(summary, dict):
        raise EvidenceError("summary must be an object")
    expected_summary_keys = {"total", *SUMMARY_KEYS.values()}
    require_exact_keys(summary, expected_summary_keys, "summary")
    for key in expected_summary_keys:
        require_integer(summary[key], f"summary.{key}")
    counts = Counter(statuses)
    expected_summary = {"total": len(statuses)}
    expected_summary.update(
        {target: counts[source] for source, target in SUMMARY_KEYS.items()}
    )
    if summary != expected_summary:
        raise EvidenceError("summary does not match test statuses")
    expected_result = (
        "passed"
        if counts["PASSED"] == len(statuses) and exit_code == 0
        else "failed"
    )
    if evidence["result"] != expected_result:
        raise EvidenceError("result does not match test statuses")
    if require_pass and evidence["result"] != "passed":
        raise EvidenceError("runtime evidence does not record a passing suite")
    if require_pass and project["dirty"]:
        raise EvidenceError("passing runtime evidence requires a clean project tree")
    if require_pass and (not timeout["exercised"] or not absence["exercised"]):
        raise EvidenceError("passing runtime evidence requires both negative paths")
    if require_pass and interrupt_paths is not None and not all(
        path["exercised"] for path in interrupt_paths.values()
    ):
        raise EvidenceError("passing runtime evidence requires every interrupt path")
    if require_pass and dma_paths is not None and not all(
        path["exercised"] for path in dma_paths.values()
    ):
        raise EvidenceError("passing runtime evidence requires every DMA path")


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    collect = subparsers.add_parser("collect", help="convert the latest OEQA run")
    collect.add_argument("--oeqa", required=True, help="OEQA testresults.json")
    collect.add_argument("--output", required=True, help="project evidence JSON")
    collect.add_argument("--machine", required=True)
    collect.add_argument("--image", required=True)
    collect.add_argument("--testimage-exit-code", required=True, type=int)
    validate = subparsers.add_parser("validate", help="validate project evidence")
    validate.add_argument("path")
    validate.add_argument("--require-pass", action="store_true")
    validate.add_argument(
        "--require-revision",
        help="require evidence from this exact 40-character project revision",
    )
    args = parser.parse_args()

    try:
        if args.command == "collect":
            oeqa_path = Path(args.oeqa)
            evidence = build_evidence(
                oeqa=read_object(oeqa_path),
                repo=Path(args.repo),
                machine=args.machine,
                image=args.image,
                oeqa_sha256=hashlib.sha256(oeqa_path.read_bytes()).hexdigest(),
                testimage_exit_code=args.testimage_exit_code,
            )
            write_evidence(Path(args.output), evidence)
            print(f"runtime-evidence: {evidence['result']}: {args.output}")
            return 0
        evidence = read_object(Path(args.path))
        validate_evidence(
            evidence,
            require_pass=args.require_pass,
            expected_revision=args.require_revision,
        )
        print(f"runtime-evidence: PASS: {args.path}")
        return 0
    except (EvidenceError, OSError, subprocess.CalledProcessError) as exc:
        print(f"runtime-evidence: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
