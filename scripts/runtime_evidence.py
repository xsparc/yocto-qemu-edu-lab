#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Collect and validate closed version-1 QEMU EDU runtime evidence."""

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


SCHEMA_VERSION = 1
KIND = "qemu-edu-runtime"
PROJECT_NAME = "yocto-qemu-edu-lab"
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_STRING_LENGTH = 4096
GUEST_CONTRACT_NAME = "qemu-edu-sysfs"
SUITE_NAME = "qemu-edu-baseline"
EXPECTED_TESTS = (
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


def read_object(path: Path) -> dict[str, Any]:
    try:
        if path.stat().st_size > MAX_JSON_BYTES:
            raise EvidenceError(
                f"JSON input exceeds the {MAX_JSON_BYTES}-byte safety limit: {path}"
            )
        text = path.read_text(encoding="utf-8")

        def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            value: dict[str, Any] = {}
            for key, item in pairs:
                if key in value:
                    raise EvidenceError(f"duplicate JSON key: {key!r}")
                value[key] = item
            return value

        value = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"could not read JSON object {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{path} must contain a JSON object")
    return value


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
    data: dict[str, Any], machine: str, image: str
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
        if not any(test_id in results for test_id in EXPECTED_TESTS):
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
                "version": 1,
            },
            "suite": {
                "name": SUITE_NAME,
                "version": 1,
                "test_type": require_string(
                    configuration.get("TEST_TYPE"), "TEST_TYPE"
                ),
            },
            "negative_paths": {
                "factorial_timeout": {
                    "case_id": EXPECTED_TESTS[9],
                    "exercised": status_by_id[EXPECTED_TESTS[9]] == "PASSED",
                    "fault_injected": status_by_id[EXPECTED_TESTS[9]] == "PASSED",
                    "mechanism": "module-parameter:force_factorial_timeout",
                },
                "device_absence": {
                    "case_id": EXPECTED_TESTS[10],
                    "exercised": status_by_id[EXPECTED_TESTS[10]] == "PASSED",
                    "mechanism": "linux-pci-hot-remove",
                    "cold_boot_without_device": False,
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


def validate_evidence(evidence: dict[str, Any], *, require_pass: bool = False) -> None:
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
    if (
        require_integer(evidence["schema_version"], "schema_version")
        != SCHEMA_VERSION
        or evidence["kind"] != KIND
    ):
        raise EvidenceError("unsupported evidence schema or kind")

    contract = evidence["contract"]
    if not isinstance(contract, dict):
        raise EvidenceError("contract must be an object")
    require_exact_keys(
        contract, {"guest_interface", "suite", "negative_paths"}, "contract"
    )
    guest = contract["guest_interface"]
    if not isinstance(guest, dict):
        raise EvidenceError("contract.guest_interface must be an object")
    require_exact_keys(guest, {"name", "version"}, "contract.guest_interface")
    if (
        guest.get("name") != GUEST_CONTRACT_NAME
        or require_integer(guest.get("version"), "contract.guest_interface.version")
        != 1
    ):
        raise EvidenceError("unsupported guest-interface contract")
    suite = contract["suite"]
    if not isinstance(suite, dict):
        raise EvidenceError("contract.suite must be an object")
    require_exact_keys(suite, {"name", "version", "test_type"}, "contract.suite")
    if (
        suite.get("name") != SUITE_NAME
        or require_integer(suite.get("version"), "contract.suite.version") != 1
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
    if not SHA1.fullmatch(require_string(project["revision"], "project.revision")):
        raise EvidenceError("project.revision must be a lowercase SHA-1")

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
    if not isinstance(tests, list) or len(tests) != len(EXPECTED_TESTS):
        raise EvidenceError("tests must contain every required QEMU EDU case")
    statuses: list[str] = []
    for expected_id, test in zip(EXPECTED_TESTS, tests, strict=True):
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
    expected_timeout_exercised = statuses[9] == "PASSED"
    expected_absence_exercised = statuses[10] == "PASSED"
    if timeout != {
        "case_id": EXPECTED_TESTS[9],
        "exercised": expected_timeout_exercised,
        "fault_injected": expected_timeout_exercised,
        "mechanism": "module-parameter:force_factorial_timeout",
    }:
        raise EvidenceError("factorial-timeout semantics do not match the suite")
    if absence != {
        "case_id": EXPECTED_TESTS[10],
        "exercised": expected_absence_exercised,
        "mechanism": "linux-pci-hot-remove",
        "cold_boot_without_device": False,
    }:
        raise EvidenceError("device-absence semantics do not match the suite")

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
        validate_evidence(evidence, require_pass=args.require_pass)
        print(f"runtime-evidence: PASS: {args.path}")
        return 0
    except (EvidenceError, OSError, subprocess.CalledProcessError) as exc:
        print(f"runtime-evidence: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
