#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Enforce the public CI trust boundary without a YAML dependency."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ACTION = re.compile(r"\buses:\s*([^\s#]+)")
PINNED_ACTION = re.compile(r"(?:[^/@\s]+/[^/@\s]+)@[0-9a-f]{40}\Z")
JOB = re.compile(r"^  ([A-Za-z][A-Za-z0-9_-]*):\s*$")
WRITE_PERMISSION = re.compile(r"(?m)^\s+[A-Za-z_-]+:\s*write\s*$", re.IGNORECASE)
GITHUB_OWNED_ACTION_OWNERS = {"actions", "github"}
FAST_JOB_IDS = {"repository", "static", "diagnostics-schema", "licensing"}
TRUST_POLICY = "config/repository-trust-policy.json"
MAX_TRUST_POLICY_BYTES = 32 * 1024
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
    "config/labs/**",
    "scripts/source_lock.py",
    "scripts/lab_config.py",
    "scripts/configure_build.py",
    "scripts/qemu_security_preflight.sh",
    "scripts/verify_qemu_security.py",
    "scripts/sbom_evidence.py",
    "scripts/sdk_evidence.py",
    "scripts/sdk_iteration.py",
    "scripts/sdk_tooling.py",
    "setup.sh",
    "environment.sh",
    "build.sh",
    "inspect.sh",
    "run.sh",
    "runtime-test.sh",
    "sbom-evidence.sh",
    "sdk-test.sh",
    "schemas/qemu-edu-sdk-evidence-v1.schema.json",
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
            continue
        owner = action.split("/", 1)[0].lower()
        if owner not in GITHUB_OWNED_ACTION_OWNERS:
            errors.append(f"external action owner is not GitHub-owned: {owner}")

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


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate key: {key}")
        value[key] = item
    return value


def validate_trust_policy_binding(root: Path, fast_text: str) -> list[str]:
    errors: list[str] = []
    policy_path = root / TRUST_POLICY
    try:
        raw = policy_path.read_bytes()
        if len(raw) > MAX_TRUST_POLICY_BYTES:
            raise ValueError("policy exceeds its byte limit")
        policy = json.loads(raw.decode("utf-8"), object_pairs_hook=reject_duplicate_pairs)
        actions = policy["actions"]
        selected = actions["selected_actions"]
        required = policy["ruleset"]["required_status_checks"]
        checks = required["checks"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError, KeyError, TypeError, ValueError) as exc:
        return [f"{TRUST_POLICY}: cannot bind CI policy: {exc}"]

    fast_jobs = [name for name, _ in job_blocks(fast_text)]
    if len(fast_jobs) != len(FAST_JOB_IDS) or set(fast_jobs) != FAST_JOB_IDS:
        errors.append(
            ".github/workflows/fast-checks.yml: job IDs must be exactly "
            + ", ".join(sorted(FAST_JOB_IDS))
        )

    if not isinstance(checks, list):
        errors.append(f"{TRUST_POLICY}: required checks must be an array")
    else:
        contexts: list[str] = []
        sources: list[str] = []
        for item in checks:
            if not isinstance(item, dict) or set(item) != {"context", "source"}:
                errors.append(f"{TRUST_POLICY}: required check fields differ")
                continue
            contexts.append(item["context"])
            sources.append(item["source"])
        if len(contexts) != len(FAST_JOB_IDS) or set(contexts) != FAST_JOB_IDS:
            errors.append(f"{TRUST_POLICY}: required contexts must match the exact Fast job IDs")
        if any(source != "github-actions" for source in sources):
            errors.append(f"{TRUST_POLICY}: every required context must bind to github-actions")
        if "yocto-metadata" in contexts:
            errors.append(f"{TRUST_POLICY}: path-scoped metadata must remain advisory")

    expected_actions = {
        "enabled": True,
        "allowed_actions": "selected",
        "sha_pinning_required": True,
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
    }
    if any(actions.get(name) != value for name, value in expected_actions.items()):
        errors.append(f"{TRUST_POLICY}: Actions policy differs from the local CI boundary")
    if selected != {
        "github_owned_allowed": True,
        "verified_allowed": False,
        "patterns_allowed": [],
    }:
        errors.append(f"{TRUST_POLICY}: selected actions must remain GitHub-owned only")
    if required.get("strict_required_status_checks_policy") is not True:
        errors.append(f"{TRUST_POLICY}: required status checks must remain strict")
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
    fast_workflow = workflow_dir / "fast-checks.yml"
    if not fast_workflow.is_file():
        errors.append(".github/workflows/fast-checks.yml: required workflow is missing")
    else:
        errors.extend(
            validate_trust_policy_binding(
                root, fast_workflow.read_text(encoding="utf-8")
            )
        )
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
