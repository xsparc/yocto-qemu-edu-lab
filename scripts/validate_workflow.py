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
    "config/sources.lock.json",
    "config/labs/index.json",
    "scripts/lab_config.py",
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


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


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
        config = load_toml(config_path)
        task_state = load_toml(tasks_path)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        errors.append(f"invalid workflow TOML: {exc}")
        return errors

    workflow = config.get("workflow", {})
    statuses = workflow.get("statuses", [])
    if not isinstance(statuses, list) or not statuses:
        errors.append("workflow.statuses must be a non-empty list")
        statuses = []

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
    if task_state.get("task_id_prefix") != prefix:
        errors.append("task_id_prefix differs between config.toml and tasks.toml")

    tasks = task_state.get("tasks", [])
    if not isinstance(tasks, list):
        errors.append("tasks must be an array of tables")
        return errors

    ids: set[str] = set()
    active = 0
    task_by_id: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if not isinstance(task, dict):
            errors.append("each task must be a TOML table")
            continue
        task_id = str(task.get("id", ""))
        status = str(task.get("status", ""))
        task_by_id[task_id] = task
        if not re.fullmatch(re.escape(str(prefix)) + r"\d{3,}", task_id):
            errors.append(f"invalid task id: {task_id or '<empty>'}")
        if task_id in ids:
            errors.append(f"duplicate task id: {task_id}")
        ids.add(task_id)
        if status not in statuses:
            errors.append(f"{task_id} has invalid status: {status}")
        if status == "In Progress":
            active += 1
        if status in {"Ready", "In Progress", "Done"} and workflow.get(
            "ready_requires_user_approval", True
        ) and not str(task.get("approval", "")).strip():
            errors.append(f"{task_id} is executable without approval evidence")
        for field in ("milestone", "title", "outcome", "scope", "acceptance_criteria", "validation"):
            value = task.get(field)
            if value in (None, "", []):
                errors.append(f"{task_id} has no {field}")
        if status == "Done":
            if not str(task.get("result", "")).strip():
                errors.append(f"{task_id} is Done without a result")
            if workflow.get("done_requires_validation_evidence", True) and not task.get(
                "validation_evidence"
            ):
                errors.append(f"{task_id} is Done without validation evidence")
            if workflow.get("done_requires_review_evidence", True) and not task.get(
                "review_evidence"
            ):
                errors.append(f"{task_id} is Done without review evidence")
            required_reviews = set(task.get("reviews_required", []))
            completed_reviews = set(task.get("reviews_completed", []))
            missing_reviews = sorted(required_reviews - completed_reviews)
            if missing_reviews:
                errors.append(
                    f"{task_id} is Done without completed reviews: "
                    + ", ".join(missing_reviews)
                )

    if active > int(workflow.get("max_in_progress", 1)):
        errors.append(f"{active} tasks are In Progress")

    for task_id, task in task_by_id.items():
        for dependency in task.get("dependencies", []):
            if dependency == task_id:
                errors.append(f"{task_id} depends on itself")
            elif dependency not in task_by_id:
                errors.append(f"{task_id} has unknown dependency: {dependency}")
        if task.get("status") in {"Ready", "In Progress", "Done"}:
            for dependency in task.get("dependencies", []):
                if dependency not in task_by_id:
                    continue
                if task_by_id[dependency].get("status") != "Done":
                    errors.append(
                        f"{task_id} is executable before dependency {dependency} is Done"
                    )

    if ledger_path.is_file():
        ledger = ledger_path.read_text(encoding="utf-8")
        for task_id in ids:
            task = task_by_id[task_id]
            milestone = re.escape(str(task.get("milestone", "")))
            status = re.escape(str(task.get("status", "")))
            pattern = rf"(?m)^\| {re.escape(task_id)} \| {milestone} \| {status} \|"
            if not re.search(pattern, ledger):
                errors.append(f"ledger is missing {task_id}")

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
