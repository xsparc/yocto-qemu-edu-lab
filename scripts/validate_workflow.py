#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Validate the repository's small, dependency-free maintenance workflow."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path
from typing import Any


REQUIRED_FILES = (
    "MAINTAINERS.md",
    "docs/maintainers/README.md",
    "docs/maintainers/config.toml",
    "docs/maintainers/intake.md",
    "docs/maintainers/tasks.toml",
    "docs/maintainers/ledger.md",
    "docs/maintainers/context.md",
    "docs/maintainers/decisions.md",
    "docs/vision.md",
    "docs/architecture.md",
    "docs/roadmap.md",
    "docs/maintenance-workflow.md",
    "docs/licensing.md",
    "docs/source-lock.md",
    "docs/ci.md",
    "docs/versioning.md",
    "docs/guest-interface.md",
    "docs/runtime-testing.md",
    "docs/diagnostics.md",
    "config/sources.lock.json",
    "config/diagnostics-schema-validator.lock.json",
    "config/labs/index.json",
    "scripts/lab_config.py",
    "scripts/diagnostics.py",
    "scripts/diagnostics_git.py",
    "scripts/diagnostics_inputs.py",
    "scripts/verify_diagnostics_schema_lock.py",
    "qemu-edu-lab",
    "schemas/qemu-edu-diagnostics-v1.schema.json",
    "schemas/qemu-edu-runtime-evidence-v1.schema.json",
    "schemas/qemu-edu-platform-runtime-evidence-v1.schema.json",
    ".github/workflows/fast-checks.yml",
    ".github/workflows/yocto-metadata.yml",
)

REQUIRED_VALIDATION_COMMANDS = (
    "python3 scripts/source_lock.py validate",
    "python3 scripts/lab_config.py validate",
    "python3 scripts/validate_workflow.py",
    "python3 scripts/validate_ci.py",
    "python3 scripts/verify_qemu_security.py static",
    "python3 scripts/verify_diagnostics_schema_lock.py",
    "python3 -m unittest discover -s tests -p test_*.py",
    "python3 scripts/update_checksums.py --check",
    "git diff --check",
)

REQUIRED_PATH_LISTS = {
    "historical_runtime_evidence_schema_paths": (
        "schemas/qemu-edu-runtime-evidence-v1.schema.json",
        "schemas/qemu-edu-runtime-evidence-v2.schema.json",
    ),
}
MAX_TOML_BYTES = 256 * 1024
MAX_LEDGER_BYTES = 256 * 1024
EXPECTED_STATUSES = ["Proposed", "Ready", "In Progress", "Blocked", "Done"]
WORKFLOW_KEYS = {
    "statuses",
    "max_in_progress",
    "ready_requires_user_approval",
    "done_requires_validation_evidence",
    "done_requires_review_evidence",
    "one_pull_request_per_milestone",
    "public_actions_require_explicit_scope",
}
REQUIRED_TRUE_POLICIES = (
    "ready_requires_user_approval",
    "done_requires_validation_evidence",
    "done_requires_review_evidence",
    "one_pull_request_per_milestone",
    "public_actions_require_explicit_scope",
)


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def parse_toml_bytes(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > MAX_TOML_BYTES:
        raise ValueError(f"{label} exceeds {MAX_TOML_BYTES} bytes")
    try:
        value = tomllib.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ValueError(f"invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a TOML table")
    return value


def read_bounded(path: Path, maximum: int) -> bytes:
    with path.open("rb") as handle:
        raw = handle.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError(f"{path.name} exceeds {maximum} bytes")
    return raw


def validate_models(
    config: dict[str, Any],
    task_state: dict[str, Any],
    ledger: str | None,
) -> tuple[list[str], dict[str, str] | None]:
    errors: list[str] = []
    workflow_value = config.get("workflow", {})
    if not isinstance(workflow_value, dict):
        errors.append("workflow must be a TOML table")
        workflow: dict[str, Any] = {}
    else:
        workflow = workflow_value
    if set(workflow) != WORKFLOW_KEYS:
        errors.append("workflow fields differ from the closed policy contract")
    if workflow.get("statuses") != EXPECTED_STATUSES:
        errors.append("workflow.statuses differs from the closed status contract")
    statuses = EXPECTED_STATUSES
    if type(workflow.get("max_in_progress")) is not int or workflow.get(
        "max_in_progress"
    ) != 1:
        errors.append("workflow.max_in_progress must be exactly 1")
    for policy in REQUIRED_TRUE_POLICIES:
        if workflow.get(policy) is not True:
            errors.append(f"workflow.{policy} must be true")

    validation_commands = config.get("validation_commands", [])
    if not isinstance(validation_commands, list) or not all(
        isinstance(command, str) and command for command in validation_commands
    ):
        errors.append("validation_commands must be an array of non-empty strings")
        validation_commands = []
    if len(validation_commands) != len(set(validation_commands)):
        errors.append("validation_commands contains duplicates")
    for command in REQUIRED_VALIDATION_COMMANDS:
        if command not in validation_commands:
            errors.append(f"validation_commands is missing: {command}")

    prefix = config.get("task_id_prefix", "A")
    if not isinstance(prefix, str) or not prefix:
        errors.append("task_id_prefix must be a non-empty string")
        prefix = "A"
    if task_state.get("task_id_prefix") != prefix:
        errors.append("task_id_prefix differs between config.toml and tasks.toml")

    tasks = task_state.get("tasks", [])
    if not isinstance(tasks, list):
        errors.append("tasks must be an array of tables")
        return errors, None

    ids: set[str] = set()
    active_tasks: list[dict[str, str]] = []
    task_by_id: dict[str, dict[str, Any]] = {}
    dependencies_by_id: dict[str, list[str]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            errors.append("each task must be a TOML table")
            continue
        task_id_value = task.get("id", "")
        status_value = task.get("status", "")
        task_id = task_id_value if isinstance(task_id_value, str) else ""
        status = status_value if isinstance(status_value, str) else ""
        task_by_id[task_id] = task
        if not re.fullmatch(re.escape(str(prefix)) + r"\d{3,}", task_id):
            errors.append(f"invalid task id: {task_id or '<empty>'}")
        if task_id in ids:
            errors.append(f"duplicate task id: {task_id}")
        ids.add(task_id)
        if status not in statuses:
            errors.append(f"{task_id} has invalid status: {status}")
        if status == "In Progress":
            active_tasks.append({"id": task_id, "status": status})
        approval = task.get("approval", "")
        if status in {"Ready", "In Progress", "Done"} and (
            not isinstance(approval, str) or not approval.strip()
        ):
            errors.append(f"{task_id} is executable without approval evidence")
        for field in ("milestone", "title", "outcome", "scope", "acceptance_criteria", "validation"):
            value = task.get(field)
            if value in (None, "", []):
                errors.append(f"{task_id} has no {field}")
        if status == "Done":
            result = task.get("result", "")
            if not isinstance(result, str) or not result.strip():
                errors.append(f"{task_id} is Done without a result")
            if not task.get("validation_evidence"):
                errors.append(f"{task_id} is Done without validation evidence")
            if not task.get("review_evidence"):
                errors.append(f"{task_id} is Done without review evidence")
            required_value = task.get("reviews_required", [])
            completed_value = task.get("reviews_completed", [])
            if not isinstance(required_value, list) or not all(
                isinstance(item, str) and item for item in required_value
            ):
                errors.append(f"{task_id} reviews_required must be a string array")
                required_value = []
            if not isinstance(completed_value, list) or not all(
                isinstance(item, str) and item for item in completed_value
            ):
                errors.append(f"{task_id} reviews_completed must be a string array")
                completed_value = []
            required_reviews = set(required_value)
            completed_reviews = set(completed_value)
            missing_reviews = sorted(required_reviews - completed_reviews)
            if missing_reviews:
                errors.append(
                    f"{task_id} is Done without completed reviews: "
                    + ", ".join(missing_reviews)
                )
        dependency_value = task.get("dependencies", [])
        if not isinstance(dependency_value, list) or not all(
            isinstance(item, str) and item for item in dependency_value
        ):
            errors.append(f"{task_id} dependencies must be a string array")
            dependency_value = []
        dependencies_by_id[task_id] = dependency_value

    max_in_progress = 1
    if len(active_tasks) > max_in_progress:
        errors.append(f"{len(active_tasks)} tasks are In Progress")

    for task_id, task in task_by_id.items():
        for dependency in dependencies_by_id.get(task_id, []):
            if dependency == task_id:
                errors.append(f"{task_id} depends on itself")
            elif dependency not in task_by_id:
                errors.append(f"{task_id} has unknown dependency: {dependency}")
        if task.get("status") in {"Ready", "In Progress", "Done"}:
            for dependency in dependencies_by_id.get(task_id, []):
                if dependency not in task_by_id:
                    continue
                if task_by_id[dependency].get("status") != "Done":
                    errors.append(
                        f"{task_id} is executable before dependency {dependency} is Done"
                    )

    if ledger is not None:
        for task_id in ids:
            task = task_by_id[task_id]
            milestone = re.escape(str(task.get("milestone", "")))
            status = re.escape(str(task.get("status", "")))
            pattern = rf"(?m)^\| {re.escape(task_id)} \| {milestone} \| {status} \|"
            if not re.search(pattern, ledger):
                errors.append(f"ledger is missing {task_id}")

    active_task = active_tasks[0] if len(active_tasks) == 1 and not errors else None
    return errors, active_task


def validate(root: Path) -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            errors.append(f"missing required file: {relative}")

    config_path = root / "docs/maintainers/config.toml"
    tasks_path = root / "docs/maintainers/tasks.toml"
    ledger_path = root / "docs/maintainers/ledger.md"
    if not config_path.is_file() or not tasks_path.is_file():
        return errors

    try:
        config_raw = read_bounded(config_path, MAX_TOML_BYTES)
        tasks_raw = read_bounded(tasks_path, MAX_TOML_BYTES)
        ledger_raw = read_bounded(ledger_path, MAX_LEDGER_BYTES) if ledger_path.is_file() else None
        config = parse_toml_bytes(config_raw, "workflow configuration")
        task_state = parse_toml_bytes(tasks_raw, "task state")
        if ledger_raw is not None:
            ledger = ledger_raw.decode("utf-8")
        else:
            ledger = None
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        errors.append(f"invalid workflow input: {exc}")
        return errors

    model_errors, _ = validate_models(config, task_state, ledger)
    errors.extend(model_errors)

    for key in (
        "design_path",
        "vision_path",
        "roadmap_path",
        "maintenance_plan_path",
        "license_policy_path",
        "source_lock_path",
        "source_lock_policy_path",
        "lab_index_path",
        "ci_policy_path",
        "versioning_path",
        "guest_interface_path",
        "runtime_testing_path",
        "runtime_evidence_schema_path",
        "platform_runtime_evidence_schema_path",
        "diagnostics_schema_path",
        "diagnostics_schema_validator_lock_path",
        "diagnostics_documentation_path",
    ):
        relative = config.get(key)
        if not relative or not (root / str(relative)).is_file():
            errors.append(f"configured path is missing: {key}={relative!r}")

    for key, expected in REQUIRED_PATH_LISTS.items():
        configured = config.get(key)
        if configured != list(expected):
            errors.append(
                f"configured path list differs: {key}={configured!r}; "
                f"expected {list(expected)!r}"
            )
            continue
        for relative in configured:
            if not (root / relative).is_file():
                errors.append(f"configured path is missing: {key}={relative!r}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    args = parser.parse_args()
    errors = validate(Path(args.repo).resolve())
    if errors:
        for error in errors:
            print(f"workflow: FAIL: {error}", file=sys.stderr)
        return 1
    print("workflow: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
