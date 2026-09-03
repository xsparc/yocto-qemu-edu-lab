#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Enforce the public CI trust boundary without a YAML dependency."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


ACTION = re.compile(r"(?m)^\s+(?:-\s+)?uses:\s*([^\s#]+)")
PINNED_ACTION = re.compile(r"(?:[^/@\s]+/[^/@\s]+)@[0-9a-f]{40}\Z")
JOB = re.compile(r"^  ([A-Za-z_][A-Za-z0-9_-]*):\s*$")
MAPPING_ENTRY = re.compile(
    r"^(?P<indent> *)(?P<sequence>-\s+)?"
    r"(?P<key>[A-Za-z_][A-Za-z0-9_-]*):(?P<rest>.*)$"
)
WRITE_PERMISSION = re.compile(
    r"(?m)^\s+[A-Za-z_-]+:\s*['\"]?write['\"]?\s*(?:#.*)?$",
    re.IGNORECASE,
)
BLOCK_SCALAR = re.compile(
    r"^(?P<indent> *)(?P<sequence>-\s+)?"
    r"[A-Za-z_][A-Za-z0-9_-]*:\s*[|>][+-]?\s*(?:#.*)?$"
)
QUOTED_KEY = re.compile(r"^\s*(?:-\s+)?(?:'[^']*'|\"[^\"]*\")\s*:")
SPACED_KEY = re.compile(
    r"^\s*(?:-\s+)?[A-Za-z_][A-Za-z0-9_-]*[ \t]+:"
)
CANONICAL_MAPPING = re.compile(
    r"^\s*(?:-\s+)?[A-Za-z_][A-Za-z0-9_-]*:"
)
YAML_REFERENCE = re.compile(r"(?:^|[\s:\-\[,])(?:&|\*)[A-Za-z_][A-Za-z0-9_-]*")
YAML_TAG = re.compile(r"(?:^|[\s:\-\[,])![^\s=]")
GITHUB_OWNED_ACTION_OWNERS = {"actions", "github"}
FAST_JOB_IDS = {"repository", "static", "diagnostics-schema", "licensing"}
FAST_TRIGGER_BLOCK = (
    "on:",
    "  pull_request:",
    "  push:",
    "    branches: [main]",
    "  workflow_dispatch:",
)
DEFAULTS_BLOCK = (
    "defaults:",
    "  run:",
    "    shell: bash",
)
WORKFLOW_TOP_LEVEL_KEYS = {
    "name",
    "on",
    "permissions",
    "concurrency",
    "defaults",
    "jobs",
}
# This binds the trigger and execution envelope outside the job blocks too.
FAST_WORKFLOW_SHA256 = "cbc9a8ea4d5d7113575c7d2081c96e79c399bccc52d84cd9b9eaed0b6a4d0b29"
# Review-maintained fingerprints of the exact required job blocks.
FAST_JOB_SHA256 = {
    "repository": "0f9fbf8d7350f7d3361aa4af8d5b61db7d738e09c0059a684b0a9a8acf72fb63",
    "static": "f786d0044245e4bec20e0075534980c26f5965148ec2049cd855877944bfca58",
    "diagnostics-schema": "5dfb80baf0660693d14f9436ceb13d2b5d729ac86bd446c04e8182cd353c5c33",
    "licensing": "90f639835253b88f06380049148504d98af725dbedcac53a0f9f6ae6bb107b5f",
}
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


def structural_lines(text: str) -> list[tuple[int, str]]:
    """Return YAML structure while excluding block-scalar payloads."""
    result: list[tuple[int, str]] = []
    block_indent: int | None = None
    for number, line in enumerate(text.splitlines(), start=1):
        indent = len(line) - len(line.lstrip(" "))
        if block_indent is not None:
            if not line.strip() or indent > block_indent:
                continue
            block_indent = None
        result.append((number, line))
        match = BLOCK_SCALAR.fullmatch(line)
        if match:
            block_indent = len(match.group("indent")) + (
                2 if match.group("sequence") else 0
            )
    return result


def validate_canonical_yaml(text: str) -> list[str]:
    """Reject YAML forms that could obscure security-relevant mappings."""
    errors: list[str] = []
    for number, line in structural_lines(text):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        reason: str | None = None
        if "\t" in line:
            reason = "tabs"
        elif QUOTED_KEY.match(line):
            reason = "quoted mapping keys"
        elif SPACED_KEY.match(line):
            reason = "whitespace before mapping colons"
        elif re.match(r"^\s*(?:-\s+)?\?(?:\s|$)", line):
            reason = "explicit mapping keys"
        elif re.match(r"^\s*(?:-\s+)?<<:", line):
            reason = "mapping merges"
        elif YAML_REFERENCE.search(line):
            reason = "anchors or aliases"
        elif YAML_TAG.search(line):
            reason = "explicit YAML tags"
        else:
            without_expressions = re.sub(r"\$\{\{.*?\}\}", "", line)
            if "{" in without_expressions or "}" in without_expressions:
                reason = "flow mappings"
            elif not CANONICAL_MAPPING.match(line) and not re.match(
                r"^\s*-\s+\S", line
            ):
                reason = "unsupported structural form"
        if reason is not None:
            errors.append(
                f"line {number} uses unsupported noncanonical YAML: {reason}"
            )
    return errors


def validate_duplicate_mappings(text: str) -> list[str]:
    """Reject duplicate keys within each canonical mapping scope."""
    errors: list[str] = []
    stack: list[tuple[int, tuple[str, str]]] = []
    sequence_counts: dict[tuple[tuple[tuple[str, str], ...], int], int] = {}
    seen: set[tuple[tuple[tuple[str, str], ...], str]] = set()
    for number, line in structural_lines(text):
        match = MAPPING_ENTRY.fullmatch(line)
        if match is None:
            continue
        base_indent = len(match.group("indent"))
        if match.group("sequence"):
            while stack and stack[-1][0] >= base_indent:
                stack.pop()
            sequence_key = (tuple(item[1] for item in stack), base_indent)
            sequence_counts[sequence_key] = sequence_counts.get(sequence_key, 0) + 1
            stack.append(
                (
                    base_indent,
                    ("item", f"{base_indent}:{sequence_counts[sequence_key]}"),
                )
            )
            effective_indent = base_indent + 2
        else:
            effective_indent = base_indent
            while stack and stack[-1][0] >= effective_indent:
                stack.pop()

        scope = tuple(item[1] for item in stack)
        key = match.group("key")
        identity = (scope, key)
        if identity in seen:
            errors.append(
                f"line {number} repeats mapping key {key!r} in the same scope"
            )
        else:
            seen.add(identity)

        value = match.group("rest").strip()
        if not value or value.startswith("#"):
            stack.append((effective_indent, ("mapping", key)))
    return errors


def top_level_keys(text: str) -> list[str]:
    keys: list[str] = []
    for _, line in structural_lines(text):
        match = MAPPING_ENTRY.fullmatch(line)
        if (
            match is not None
            and not match.group("indent")
            and match.group("sequence") is None
        ):
            keys.append(match.group("key"))
    return keys


def top_level_block(text: str, key: str) -> tuple[str, ...]:
    lines = text.splitlines()
    indexes = [index for index, line in enumerate(lines) if line == f"{key}:"]
    if len(indexes) != 1:
        return ()
    start = indexes[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index] and not lines[index].startswith(" "):
            end = index
            break
    block = lines[start:end]
    while block and not block[-1].strip():
        block.pop()
    return tuple(block)


def validate_github_context(text: str) -> list[str]:
    """Permit only the non-credential GitHub context roots used by this project."""
    for expression in re.findall(r"\$\{\{(.*?)\}\}", text, flags=re.DOTALL):
        for reference in re.finditer(r"\bgithub\b", expression, flags=re.IGNORECASE):
            suffix = expression[reference.end() :]
            if re.match(
                r"\s*\.\s*(?:event|ref|workflow)\b",
                suffix,
                flags=re.IGNORECASE,
            ) is None:
                return [
                    "GitHub expressions may use only github.event, github.ref, "
                    "or github.workflow"
                ]
    return []


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

    errors.extend(validate_canonical_yaml(text))
    errors.extend(validate_duplicate_mappings(text))
    if set(top_level_keys(text)) != WORKFLOW_TOP_LEVEL_KEYS:
        errors.append("workflow top-level keys differ from the closed CI envelope")
    if top_level_block(text, "defaults") != DEFAULTS_BLOCK:
        errors.append("workflow defaults must contain only 'run.shell: bash'")
    if not has_exact_top_level_permissions(text):
        errors.append("top-level permissions must contain only 'contents: read'")
    if WRITE_PERMISSION.search(text) or "write-all" in lowered:
        errors.append("write permissions are prohibited")
    if re.search(r"\bsecrets\b", lowered):
        errors.append("these workflows must not consume repository secrets")
    errors.extend(validate_github_context(text))
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
        if path.name != "fast-checks.yml":
            if name in FAST_JOB_IDS:
                errors.append(
                    f"job {name} uses a context reserved for fast-checks.yml"
                )
            if re.search(r"(?m)^    name:\s*", block):
                errors.append(
                    f"job {name} must not override its context name outside "
                    "fast-checks.yml"
                )
        if len(re.findall(r"(?m)^    timeout-minutes:", block)) != 1 or not re.search(
            r"(?m)^    timeout-minutes:\s*[1-9][0-9]*\s*$", block
        ):
            errors.append(f"job {name} has no positive timeout-minutes")
        if len(re.findall(r"(?m)^    runs-on:", block)) != 1 or len(
            re.findall(r"(?m)^    runs-on:\s*ubuntu-24\.04\s*$", block)
        ) != 1:
            errors.append(f"job {name} must use exactly one ubuntu-24.04 hosted runner")
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
        if not all(
            isinstance(item, dict)
            for item in (policy, actions, selected, required)
        ):
            raise TypeError("policy sections must be objects")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError, KeyError, TypeError, ValueError) as exc:
        return [f"{TRUST_POLICY}: cannot bind CI policy: {exc}"]

    if top_level_block(fast_text, "on") != FAST_TRIGGER_BLOCK:
        errors.append(
            ".github/workflows/fast-checks.yml: triggers must be exactly "
            "unfiltered pull_request, main push, and workflow_dispatch"
        )
    if hashlib.sha256(fast_text.encode("utf-8")).hexdigest() != FAST_WORKFLOW_SHA256:
        errors.append(
            ".github/workflows/fast-checks.yml: complete workflow differs from "
            "its reviewed execution surface"
        )

    parsed_jobs = job_blocks(fast_text)
    fast_jobs = [name for name, _ in parsed_jobs]
    if len(fast_jobs) != len(FAST_JOB_IDS) or set(fast_jobs) != FAST_JOB_IDS:
        errors.append(
            ".github/workflows/fast-checks.yml: job IDs must be exactly "
            + ", ".join(sorted(FAST_JOB_IDS))
        )
    for name, block in parsed_jobs:
        if name not in FAST_JOB_IDS:
            continue
        for key in ("name", "if", "needs", "strategy"):
            if re.search(rf"(?m)^    {key}:\s*", block):
                errors.append(
                    f".github/workflows/fast-checks.yml: required job {name} "
                    f"must not set job-level {key}"
                )
        digest = hashlib.sha256(block.encode("utf-8")).hexdigest()
        if digest != FAST_JOB_SHA256[name]:
            errors.append(
                f".github/workflows/fast-checks.yml: required job {name} "
                "differs from its reviewed command surface"
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
            if not isinstance(item["context"], str) or not isinstance(
                item["source"], str
            ):
                errors.append(f"{TRUST_POLICY}: required check values must be strings")
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
