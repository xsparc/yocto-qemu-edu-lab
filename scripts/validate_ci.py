#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Enforce the public CI trust boundary without a YAML dependency."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ACTION = re.compile(r"\buses:\s*([^\s#]+)")
PINNED_ACTION = re.compile(r"(?:[^/@\s]+/[^/@\s]+)@[0-9a-f]{40}\Z")
JOB = re.compile(r"^  ([A-Za-z][A-Za-z0-9_-]*):\s*$")
WRITE_PERMISSION = re.compile(r"(?m)^\s+[A-Za-z_-]+:\s*write\s*$", re.IGNORECASE)
BANNED = {
    "pull_request_target:": "pull_request_target can expose privileged context to fork code",
    "workflow_run:": "workflow_run can cross an untrusted-to-privileged boundary",
    "self-hosted": "persistent self-hosted runners are outside the public PR trust boundary",
    "actions/cache": "M1 CI does not persist untrusted caches",
    "actions/upload-artifact": "M1 CI does not publish artifacts",
    "continue-on-error": "required evidence must not be silently weakened",
}
METADATA_REQUIRED_PATHS = {
    ".github/workflows/yocto-metadata.yml",
    "config/sources.lock.json",
    "scripts/source_lock.py",
    "scripts/configure_build.py",
    "setup.sh",
    "environment.sh",
    "build.sh",
    "inspect.sh",
    "Makefile",
    "meta-qemu-edu/**",
}


def has_exact_top_level_permissions(text: str) -> bool:
    lines = text.splitlines()
    indexes = [index for index, line in enumerate(lines) if line == "permissions:"]
    if len(indexes) != 1:
        return False
    children: list[str] = []
    for line in lines[indexes[0] + 1 :]:
        if line and not line.startswith(" "):
            break
        if line.strip() and not line.lstrip().startswith("#"):
            children.append(line.rstrip())
    return children == ["  contents: read"]


def job_blocks(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    try:
        start = lines.index("jobs:") + 1
    except ValueError:
        return []
    jobs: list[tuple[str, list[str]]] = []
    current_name: str | None = None
    current_lines: list[str] = []
    for line in lines[start:]:
        if line and not line.startswith(" "):
            break
        match = JOB.fullmatch(line)
        if match:
            if current_name is not None:
                jobs.append((current_name, current_lines))
            current_name = match.group(1)
            current_lines = [line]
        elif current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        jobs.append((current_name, current_lines))
    return [(name, "\n".join(lines_)) for name, lines_ in jobs]


def trigger_paths(text: str, trigger: str) -> set[str]:
    lines = text.splitlines()
    event_line = f"  {trigger}:"
    try:
        event_start = lines.index(event_line) + 1
    except ValueError:
        return set()
    event_end = len(lines)
    for index in range(event_start, len(lines)):
        if re.match(r"^  \S", lines[index]):
            event_end = index
            break
    try:
        paths_start = lines.index("    paths:", event_start, event_end) + 1
    except ValueError:
        return set()
    paths: set[str] = set()
    for line in lines[paths_start:event_end]:
        match = re.fullmatch(r'      - "([^"]+)"', line)
        if match:
            paths.add(match.group(1))
        elif line.strip():
            break
    return paths


def validate_metadata_paths(text: str) -> list[str]:
    errors: list[str] = []
    for trigger in ("pull_request", "push"):
        missing = sorted(METADATA_REQUIRED_PATHS - trigger_paths(text, trigger))
        if missing:
            errors.append(
                f"{trigger} paths omit metadata inputs: {', '.join(missing)}"
            )
    return errors


def validate_workflow(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()

    if not has_exact_top_level_permissions(text):
        errors.append("top-level permissions must contain only 'contents: read'")
    if WRITE_PERMISSION.search(text) or "write-all" in lowered:
        errors.append("write permissions are prohibited")
    if re.search(r"\bsecrets\s*(?:\.|\[)", lowered):
        errors.append("these workflows must not consume repository secrets")
    for token, reason in BANNED.items():
        if token in lowered:
            errors.append(reason)

    actions = ACTION.findall(text)
    for action in actions:
        if action.startswith("./"):
            continue
        if not PINNED_ACTION.fullmatch(action):
            errors.append(f"external action is not pinned to a full commit SHA: {action}")

    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "uses: actions/checkout@" not in line:
            continue
        block = "\n".join(lines[index + 1 : index + 9])
        if not re.search(r"(?m)^\s+persist-credentials:\s*false\s*$", block):
            errors.append("Checkout must set persist-credentials: false")
        if not re.search(r"(?m)^\s+fetch-depth:\s*0\s*$", block):
            errors.append("Checkout must set fetch-depth: 0")

    jobs = job_blocks(text)
    if not jobs:
        errors.append("workflow has no statically identifiable jobs")
    for name, block in jobs:
        if not re.search(r"(?m)^    timeout-minutes:\s*[1-9][0-9]*\s*$", block):
            errors.append(f"job {name} has no positive timeout-minutes")
        if re.search(r"(?m)^    permissions\s*:", block):
            errors.append(f"job {name} must not override permissions")

    if "fsfe/reuse" in lowered and not re.search(
        r"fsfe/reuse@sha256:[0-9a-f]{64}\b", lowered
    ):
        errors.append("REUSE container must be pinned to a sha256 digest")
    return errors


def validate(root: Path) -> list[str]:
    workflow_dir = root / ".github/workflows"
    workflows = sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml"))
    if not workflows:
        return ["no GitHub Actions workflows found"]
    errors: list[str] = []
    for workflow in workflows:
        for error in validate_workflow(workflow):
            errors.append(f"{workflow.relative_to(root).as_posix()}: {error}")
    metadata_workflow = workflow_dir / "yocto-metadata.yml"
    if not metadata_workflow.is_file():
        errors.append(".github/workflows/yocto-metadata.yml: required workflow is missing")
    else:
        for error in validate_metadata_paths(
            metadata_workflow.read_text(encoding="utf-8")
        ):
            errors.append(f".github/workflows/yocto-metadata.yml: {error}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    args = parser.parse_args()
    errors = validate(Path(args.repo).resolve())
    if errors:
        for error in errors:
            print(f"ci: FAIL: {error}", file=sys.stderr)
        return 1
    print("ci: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
