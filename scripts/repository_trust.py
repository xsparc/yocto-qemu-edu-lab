#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Validate the fixed repository-trust policy and sanitized observation."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = Path("config/repository-trust-policy.json")
OBSERVATION_PATH = Path("build/repository-trust/observation-v1.json")
SECURITY_PATH = Path("SECURITY.md")
KIND = "qemu-edu-repository-trust-evidence"
PROJECT = "yocto-qemu-edu-lab"
SCHEMA_VERSION = 1
MAX_POLICY_BYTES = 32 * 1024
MAX_OBSERVATION_BYTES = 64 * 1024
MAX_SECURITY_BYTES = 64 * 1024
MAX_JSON_DEPTH = 16
MAX_JSON_ITEMS = 512
MAX_STRING_LENGTH = 256
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}\Z")
CONTACT = re.compile(r"@[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\Z")
UTC_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
MERGE_METHODS = {"merge", "rebase", "squash"}


EXPECTED_CHECKS = [
    {"context": "diagnostics-schema", "source": "github-actions"},
    {"context": "licensing", "source": "github-actions"},
    {"context": "repository", "source": "github-actions"},
    {"context": "static", "source": "github-actions"},
]

APPROVED_POLICY: dict[str, Any] = {
    "schema_version": 1,
    "project": PROJECT,
    "repository": {
        "visibility": "public",
        "default_branch": "main",
        "merge_methods": ["squash"],
        "delete_branch_on_merge": True,
    },
    "actions": {
        "enabled": True,
        "allowed_actions": "selected",
        "sha_pinning_required": True,
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
        "selected_actions": {
            "github_owned_allowed": True,
            "verified_allowed": False,
            "patterns_allowed": [],
        },
    },
    "ruleset": {
        "name": "Protect main",
        "enforcement": "active",
        "target": "default_branch",
        "bypass_actor_count": 0,
        "deletion": True,
        "non_fast_forward": True,
        "linear_history": True,
        "do_not_enforce_on_create": False,
        "pull_request": {
            "required": True,
            "required_approving_review_count": 0,
            "allowed_merge_methods": ["squash"],
        },
        "required_status_checks": {
            "strict_required_status_checks_policy": True,
            "checks": EXPECTED_CHECKS,
        },
    },
    "security": {
        "dependabot_alerts": True,
        "dependabot_security_updates": True,
        "secret_scanning": True,
        "secret_scanning_push_protection": True,
        "private_vulnerability_reporting": True,
        "contact": "@xsparc",
    },
}

CHECK_IDS = (
    "repository.public",
    "repository.default_branch",
    "repository.squash_only",
    "repository.delete_branch",
    "actions.enabled",
    "actions.selected",
    "actions.sha_pinning",
    "actions.default_permissions",
    "actions.pr_approval_permission",
    "actions.github_owned_only",
    "ruleset.active",
    "ruleset.name",
    "ruleset.default_branch",
    "ruleset.no_bypass",
    "ruleset.deletion",
    "ruleset.non_fast_forward",
    "ruleset.linear_history",
    "ruleset.enforce_on_create",
    "ruleset.pull_request",
    "ruleset.squash_only",
    "ruleset.strict_checks",
    "ruleset.exact_checks",
    "ruleset.check_source",
    "ruleset.metadata_advisory",
    "security.dependabot_alerts",
    "security.dependabot_updates",
    "security.secret_scanning",
    "security.push_protection",
    "security.private_reporting",
    "security.contact",
)


class RepositoryTrustError(ValueError):
    """A policy, observation, or evidence contract violation."""


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RepositoryTrustError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise RepositoryTrustError(f"unsupported JSON constant: {value}")


def reject_float(value: str) -> None:
    raise RepositoryTrustError(f"floating-point JSON value is not allowed: {value}")


def parse_integer(value: str) -> int:
    digits = value.removeprefix("-")
    if len(digits) > 10:
        raise RepositoryTrustError("JSON integer exceeds the decimal digit bound")
    return int(value)


def read_regular(path: Path, maximum: int, label: str) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise RepositoryTrustError(f"cannot inspect {label}: {exc}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RepositoryTrustError(f"{label} must be a direct regular file")
    if before.st_size > maximum:
        raise RepositoryTrustError(f"{label} exceeds {maximum} bytes")
    descriptor: int | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (
            before.st_dev,
            before.st_ino,
        ) != (
            opened.st_dev,
            opened.st_ino,
        ):
            raise RepositoryTrustError(f"{label} changed before it could be read")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = None
            raw = handle.read(maximum + 1)
    except RepositoryTrustError:
        raise
    except OSError as exc:
        raise RepositoryTrustError(f"cannot read {label}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if len(raw) > maximum:
        raise RepositoryTrustError(f"{label} exceeds {maximum} bytes")
    return raw


def validate_json_shape(value: Any) -> None:
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > MAX_JSON_ITEMS:
            raise RepositoryTrustError("JSON input exceeds the value-count bound")
        if depth > MAX_JSON_DEPTH:
            raise RepositoryTrustError("JSON input exceeds the nesting-depth bound")
        if isinstance(item, str):
            if len(item) > MAX_STRING_LENGTH:
                raise RepositoryTrustError("JSON string exceeds the character bound")
            if any(ord(character) < 0x20 or 0xD800 <= ord(character) <= 0xDFFF for character in item):
                raise RepositoryTrustError("JSON string contains an unsafe character")
        elif isinstance(item, dict):
            stack.extend((key, depth + 1) for key in item)
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
        elif item is not None and type(item) not in {bool, int}:
            raise RepositoryTrustError("JSON input contains an unsupported value type")


def parse_json(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_constant,
            parse_float=reject_float,
            parse_int=parse_integer,
        )
    except RepositoryTrustError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise RepositoryTrustError(f"{label} is invalid JSON") from exc
    validate_json_shape(value)
    if not isinstance(value, dict):
        raise RepositoryTrustError(f"{label} root must be an object")
    return value


def exact_object(
    value: Any,
    allowed: set[str],
    required: set[str],
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RepositoryTrustError(f"{label} must be an object")
    unknown = sorted(set(value) - allowed)
    missing = sorted(required - set(value))
    if unknown:
        raise RepositoryTrustError(f"{label} has unknown fields: {', '.join(unknown)}")
    if missing:
        raise RepositoryTrustError(f"{label} is missing fields: {', '.join(missing)}")
    return value


def boolean(value: Any, label: str, *, optional: bool = False) -> bool | None:
    if optional and value is None:
        return None
    if type(value) is not bool:
        raise RepositoryTrustError(f"{label} must be a boolean")
    return value


def integer(
    value: Any,
    label: str,
    *,
    minimum: int = 0,
    maximum: int = 1024,
    optional: bool = False,
) -> int | None:
    if optional and value is None:
        return None
    if type(value) is not int or not minimum <= value <= maximum:
        raise RepositoryTrustError(f"{label} must be an integer from {minimum} to {maximum}")
    return value


def enum_string(
    value: Any,
    allowed: set[str],
    label: str,
    *,
    optional: bool = False,
) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or value not in allowed:
        raise RepositoryTrustError(f"{label} has an unsupported value")
    return value


def token(value: Any, label: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or TOKEN.fullmatch(value) is None:
        raise RepositoryTrustError(f"{label} must be a bounded token")
    return value


def timestamp(value: Any, label: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or UTC_TIMESTAMP.fullmatch(value) is None:
        raise RepositoryTrustError(f"{label} must be a whole-second UTC timestamp")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise RepositoryTrustError(f"{label} is not a calendar-valid timestamp") from exc
    return value


def merge_methods(value: Any, label: str, *, optional: bool = False) -> list[str] | None:
    if optional and value is None:
        return None
    if not isinstance(value, list) or len(value) > len(MERGE_METHODS):
        raise RepositoryTrustError(f"{label} must be a bounded merge-method array")
    if any(not isinstance(item, str) or item not in MERGE_METHODS for item in value):
        raise RepositoryTrustError(f"{label} contains an unsupported merge method")
    if len(value) != len(set(value)):
        raise RepositoryTrustError(f"{label} contains duplicate merge methods")
    return sorted(value)


def patterns(value: Any, label: str, *, optional: bool = False) -> list[str] | None:
    if optional and value is None:
        return None
    if not isinstance(value, list) or len(value) > 16:
        raise RepositoryTrustError(f"{label} must be a bounded array")
    checked: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item or len(item) > 128:
            raise RepositoryTrustError(f"{label} contains an invalid pattern")
        if any(ord(character) < 0x21 or ord(character) > 0x7E for character in item):
            raise RepositoryTrustError(f"{label} contains an unsafe pattern")
        checked.append(item)
    if len(checked) != len(set(checked)):
        raise RepositoryTrustError(f"{label} contains duplicate patterns")
    return sorted(checked)


def status_checks(value: Any, label: str, *, optional: bool = False) -> list[dict[str, str]] | None:
    if optional and value is None:
        return None
    if not isinstance(value, list) or len(value) > 16:
        raise RepositoryTrustError(f"{label} must be a bounded array")
    checked: list[dict[str, str]] = []
    for index, item in enumerate(value):
        entry = exact_object(item, {"context", "source"}, {"context", "source"}, f"{label}[{index}]")
        checked.append(
            {
                "context": token(entry["context"], f"{label}[{index}].context"),
                "source": token(entry["source"], f"{label}[{index}].source"),
            }
        )
    contexts = [item["context"] for item in checked]
    if len(contexts) != len(set(contexts)):
        raise RepositoryTrustError(f"{label} contains duplicate contexts")
    return sorted(checked, key=lambda item: item["context"])


def validate_policy(value: Any) -> dict[str, Any]:
    if value != APPROVED_POLICY:
        raise RepositoryTrustError("repository trust policy differs from the approved exact contract")
    return value


def load_policy(root: Path = ROOT) -> tuple[dict[str, Any], str]:
    raw = read_regular(root / POLICY_PATH, MAX_POLICY_BYTES, "repository trust policy")
    value = validate_policy(parse_json(raw, "repository trust policy"))
    return value, hashlib.sha256(raw).hexdigest()


def validate_observation(value: Any) -> dict[str, Any]:
    validate_json_shape(value)
    root = exact_object(
        value,
        {"schema_version", "observed_at", "repository", "actions", "ruleset", "security"},
        {"schema_version", "observed_at"},
        "observation",
    )
    if type(root["schema_version"]) is not int or root["schema_version"] != 1:
        raise RepositoryTrustError("observation schema_version must be integer 1")
    timestamp(root["observed_at"], "observation.observed_at")

    if "repository" in root:
        repository = exact_object(
            root["repository"],
            {"visibility", "default_branch", "merge_methods", "delete_branch_on_merge"},
            set(),
            "observation.repository",
        )
        if "visibility" in repository:
            enum_string(repository["visibility"], {"public", "private", "internal"}, "observation.repository.visibility")
        if "default_branch" in repository:
            token(repository["default_branch"], "observation.repository.default_branch")
        if "merge_methods" in repository:
            repository["merge_methods"] = merge_methods(repository["merge_methods"], "observation.repository.merge_methods")
        if "delete_branch_on_merge" in repository:
            boolean(repository["delete_branch_on_merge"], "observation.repository.delete_branch_on_merge")

    if "actions" in root:
        actions = exact_object(
            root["actions"],
            {"enabled", "allowed_actions", "sha_pinning_required", "default_workflow_permissions", "can_approve_pull_request_reviews", "selected_actions"},
            set(),
            "observation.actions",
        )
        for name in ("enabled", "sha_pinning_required", "can_approve_pull_request_reviews"):
            if name in actions:
                boolean(actions[name], f"observation.actions.{name}")
        if "allowed_actions" in actions:
            enum_string(actions["allowed_actions"], {"all", "local_only", "selected"}, "observation.actions.allowed_actions")
        if "default_workflow_permissions" in actions:
            enum_string(actions["default_workflow_permissions"], {"read", "write"}, "observation.actions.default_workflow_permissions")
        if "selected_actions" in actions:
            selected = exact_object(
                actions["selected_actions"],
                {"github_owned_allowed", "verified_allowed", "patterns_allowed"},
                set(),
                "observation.actions.selected_actions",
            )
            for name in ("github_owned_allowed", "verified_allowed"):
                if name in selected:
                    boolean(selected[name], f"observation.actions.selected_actions.{name}")
            if "patterns_allowed" in selected:
                selected["patterns_allowed"] = patterns(selected["patterns_allowed"], "observation.actions.selected_actions.patterns_allowed")

    if "ruleset" in root:
        ruleset = exact_object(
            root["ruleset"],
            {"name", "enforcement", "target", "bypass_actor_count", "deletion", "non_fast_forward", "linear_history", "do_not_enforce_on_create", "pull_request", "required_status_checks"},
            set(),
            "observation.ruleset",
        )
        if "name" in ruleset:
            if not isinstance(ruleset["name"], str) or not ruleset["name"] or len(ruleset["name"]) > 128:
                raise RepositoryTrustError("observation.ruleset.name must be a bounded string")
        if "enforcement" in ruleset:
            enum_string(ruleset["enforcement"], {"active", "disabled", "evaluate"}, "observation.ruleset.enforcement")
        if "target" in ruleset:
            enum_string(ruleset["target"], {"default_branch", "other"}, "observation.ruleset.target")
        if "bypass_actor_count" in ruleset:
            integer(ruleset["bypass_actor_count"], "observation.ruleset.bypass_actor_count")
        for name in ("deletion", "non_fast_forward", "linear_history", "do_not_enforce_on_create"):
            if name in ruleset:
                boolean(ruleset[name], f"observation.ruleset.{name}")
        if "pull_request" in ruleset:
            pull_request = exact_object(
                ruleset["pull_request"],
                {"required", "required_approving_review_count", "allowed_merge_methods"},
                set(),
                "observation.ruleset.pull_request",
            )
            if "required" in pull_request:
                boolean(pull_request["required"], "observation.ruleset.pull_request.required")
            if "required_approving_review_count" in pull_request:
                integer(pull_request["required_approving_review_count"], "observation.ruleset.pull_request.required_approving_review_count", maximum=10)
            if "allowed_merge_methods" in pull_request:
                pull_request["allowed_merge_methods"] = merge_methods(pull_request["allowed_merge_methods"], "observation.ruleset.pull_request.allowed_merge_methods")
        if "required_status_checks" in ruleset:
            required = exact_object(
                ruleset["required_status_checks"],
                {"strict_required_status_checks_policy", "checks"},
                set(),
                "observation.ruleset.required_status_checks",
            )
            if "strict_required_status_checks_policy" in required:
                boolean(required["strict_required_status_checks_policy"], "observation.ruleset.required_status_checks.strict_required_status_checks_policy")
            if "checks" in required:
                required["checks"] = status_checks(required["checks"], "observation.ruleset.required_status_checks.checks")

    if "security" in root:
        security = exact_object(
            root["security"],
            {"dependabot_alerts", "dependabot_security_updates", "secret_scanning", "secret_scanning_push_protection", "private_vulnerability_reporting", "contact"},
            set(),
            "observation.security",
        )
        for name in ("dependabot_alerts", "dependabot_security_updates", "secret_scanning", "secret_scanning_push_protection", "private_vulnerability_reporting"):
            if name in security:
                boolean(security[name], f"observation.security.{name}")
        if "contact" in security and (
            not isinstance(security["contact"], str) or CONTACT.fullmatch(security["contact"]) is None
        ):
            raise RepositoryTrustError("observation.security.contact must be a bounded GitHub handle")
    return root


def empty_facts() -> dict[str, Any]:
    return {
        "repository": {
            "visibility": None,
            "default_branch": None,
            "merge_methods": None,
            "delete_branch_on_merge": None,
        },
        "actions": {
            "enabled": None,
            "allowed_actions": None,
            "sha_pinning_required": None,
            "default_workflow_permissions": None,
            "can_approve_pull_request_reviews": None,
            "github_owned_allowed": None,
            "verified_allowed": None,
            "patterns_allowed": None,
        },
        "ruleset": {
            "name": None,
            "enforcement": None,
            "target": None,
            "bypass_actor_count": None,
            "deletion": None,
            "non_fast_forward": None,
            "linear_history": None,
            "do_not_enforce_on_create": None,
            "pull_request_required": None,
            "required_approving_review_count": None,
            "allowed_merge_methods": None,
            "strict_required_status_checks_policy": None,
            "required_status_checks": None,
        },
        "security": {
            "dependabot_alerts": None,
            "dependabot_security_updates": None,
            "secret_scanning": None,
            "secret_scanning_push_protection": None,
            "private_vulnerability_reporting": None,
            "contact": None,
        },
    }


def facts_from_observation(observation: dict[str, Any]) -> dict[str, Any]:
    facts = empty_facts()
    for section in ("repository", "security"):
        for key, value in observation.get(section, {}).items():
            facts[section][key] = copy.deepcopy(value)
    actions = observation.get("actions", {})
    for key in ("enabled", "allowed_actions", "sha_pinning_required", "default_workflow_permissions", "can_approve_pull_request_reviews"):
        if key in actions:
            facts["actions"][key] = copy.deepcopy(actions[key])
    for key, value in actions.get("selected_actions", {}).items():
        facts["actions"][key] = copy.deepcopy(value)
    ruleset = observation.get("ruleset", {})
    for key in ("name", "enforcement", "target", "bypass_actor_count", "deletion", "non_fast_forward", "linear_history", "do_not_enforce_on_create"):
        if key in ruleset:
            facts["ruleset"][key] = copy.deepcopy(ruleset[key])
    pull_request = ruleset.get("pull_request", {})
    mapping = {
        "required": "pull_request_required",
        "required_approving_review_count": "required_approving_review_count",
        "allowed_merge_methods": "allowed_merge_methods",
    }
    for source, target in mapping.items():
        if source in pull_request:
            facts["ruleset"][target] = copy.deepcopy(pull_request[source])
    required = ruleset.get("required_status_checks", {})
    if "strict_required_status_checks_policy" in required:
        facts["ruleset"]["strict_required_status_checks_policy"] = required["strict_required_status_checks_policy"]
    if "checks" in required:
        facts["ruleset"]["required_status_checks"] = copy.deepcopy(required["checks"])
    return facts


def scalar_status(value: Any, expected: Any) -> str:
    if value is None:
        return "unavailable"
    return "pass" if value == expected else "fail"


def combined_status(values: tuple[Any, ...], predicate: Callable[[], bool]) -> str:
    if any(value is None for value in values):
        return "unavailable"
    return "pass" if predicate() else "fail"


def check_statuses(facts: dict[str, Any]) -> list[dict[str, str]]:
    repository = facts["repository"]
    actions = facts["actions"]
    ruleset = facts["ruleset"]
    security = facts["security"]
    checks = ruleset["required_status_checks"]
    statuses = {
        "repository.public": scalar_status(repository["visibility"], "public"),
        "repository.default_branch": scalar_status(repository["default_branch"], "main"),
        "repository.squash_only": scalar_status(repository["merge_methods"], ["squash"]),
        "repository.delete_branch": scalar_status(repository["delete_branch_on_merge"], True),
        "actions.enabled": scalar_status(actions["enabled"], True),
        "actions.selected": scalar_status(actions["allowed_actions"], "selected"),
        "actions.sha_pinning": scalar_status(actions["sha_pinning_required"], True),
        "actions.default_permissions": scalar_status(actions["default_workflow_permissions"], "read"),
        "actions.pr_approval_permission": scalar_status(actions["can_approve_pull_request_reviews"], False),
        "actions.github_owned_only": combined_status(
            (actions["github_owned_allowed"], actions["verified_allowed"], actions["patterns_allowed"]),
            lambda: actions["github_owned_allowed"] is True and actions["verified_allowed"] is False and actions["patterns_allowed"] == [],
        ),
        "ruleset.active": scalar_status(ruleset["enforcement"], "active"),
        "ruleset.name": scalar_status(ruleset["name"], "Protect main"),
        "ruleset.default_branch": scalar_status(ruleset["target"], "default_branch"),
        "ruleset.no_bypass": scalar_status(ruleset["bypass_actor_count"], 0),
        "ruleset.deletion": scalar_status(ruleset["deletion"], True),
        "ruleset.non_fast_forward": scalar_status(ruleset["non_fast_forward"], True),
        "ruleset.linear_history": scalar_status(ruleset["linear_history"], True),
        "ruleset.enforce_on_create": scalar_status(ruleset["do_not_enforce_on_create"], False),
        "ruleset.pull_request": combined_status(
            (ruleset["pull_request_required"], ruleset["required_approving_review_count"]),
            lambda: ruleset["pull_request_required"] is True and ruleset["required_approving_review_count"] == 0,
        ),
        "ruleset.squash_only": scalar_status(ruleset["allowed_merge_methods"], ["squash"]),
        "ruleset.strict_checks": scalar_status(ruleset["strict_required_status_checks_policy"], True),
        "ruleset.exact_checks": scalar_status(checks, EXPECTED_CHECKS),
        "ruleset.check_source": "unavailable" if checks is None else ("pass" if all(item["source"] == "github-actions" for item in checks) else "fail"),
        "ruleset.metadata_advisory": "unavailable" if checks is None else ("pass" if all(item["context"] != "yocto-metadata" for item in checks) else "fail"),
        "security.dependabot_alerts": scalar_status(security["dependabot_alerts"], True),
        "security.dependabot_updates": scalar_status(security["dependabot_security_updates"], True),
        "security.secret_scanning": scalar_status(security["secret_scanning"], True),
        "security.push_protection": scalar_status(security["secret_scanning_push_protection"], True),
        "security.private_reporting": scalar_status(security["private_vulnerability_reporting"], True),
        "security.contact": scalar_status(security["contact"], "@xsparc"),
    }
    return [{"id": check_id, "status": statuses[check_id]} for check_id in CHECK_IDS]


def aggregate(checks: list[dict[str, str]]) -> str:
    states = {item["status"] for item in checks}
    if "fail" in states:
        return "fail"
    if "unavailable" in states:
        return "unavailable"
    return "pass"


def build_evidence(policy_sha256: str, observed_at: str | None, facts: dict[str, Any]) -> dict[str, Any]:
    checks = check_statuses(facts)
    evidence = {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "project": PROJECT,
        "policy_sha256": policy_sha256,
        "observed_at": observed_at,
        "result": aggregate(checks),
        "facts": copy.deepcopy(facts),
        "checks": checks,
    }
    validate_evidence(evidence)
    return evidence


def validate_facts(facts: Any) -> dict[str, Any]:
    root = exact_object(facts, {"repository", "actions", "ruleset", "security"}, {"repository", "actions", "ruleset", "security"}, "evidence.facts")
    repository = exact_object(root["repository"], {"visibility", "default_branch", "merge_methods", "delete_branch_on_merge"}, {"visibility", "default_branch", "merge_methods", "delete_branch_on_merge"}, "evidence.facts.repository")
    enum_string(repository["visibility"], {"public", "private", "internal"}, "evidence.facts.repository.visibility", optional=True)
    token(repository["default_branch"], "evidence.facts.repository.default_branch", optional=True)
    normalized = merge_methods(repository["merge_methods"], "evidence.facts.repository.merge_methods", optional=True)
    if normalized != repository["merge_methods"]:
        raise RepositoryTrustError("evidence.facts.repository.merge_methods must be sorted")
    boolean(repository["delete_branch_on_merge"], "evidence.facts.repository.delete_branch_on_merge", optional=True)

    actions = exact_object(root["actions"], {"enabled", "allowed_actions", "sha_pinning_required", "default_workflow_permissions", "can_approve_pull_request_reviews", "github_owned_allowed", "verified_allowed", "patterns_allowed"}, {"enabled", "allowed_actions", "sha_pinning_required", "default_workflow_permissions", "can_approve_pull_request_reviews", "github_owned_allowed", "verified_allowed", "patterns_allowed"}, "evidence.facts.actions")
    for name in ("enabled", "sha_pinning_required", "can_approve_pull_request_reviews", "github_owned_allowed", "verified_allowed"):
        boolean(actions[name], f"evidence.facts.actions.{name}", optional=True)
    enum_string(actions["allowed_actions"], {"all", "local_only", "selected"}, "evidence.facts.actions.allowed_actions", optional=True)
    enum_string(actions["default_workflow_permissions"], {"read", "write"}, "evidence.facts.actions.default_workflow_permissions", optional=True)
    normalized_patterns = patterns(actions["patterns_allowed"], "evidence.facts.actions.patterns_allowed", optional=True)
    if normalized_patterns != actions["patterns_allowed"]:
        raise RepositoryTrustError("evidence.facts.actions.patterns_allowed must be sorted")

    ruleset = exact_object(root["ruleset"], {"name", "enforcement", "target", "bypass_actor_count", "deletion", "non_fast_forward", "linear_history", "do_not_enforce_on_create", "pull_request_required", "required_approving_review_count", "allowed_merge_methods", "strict_required_status_checks_policy", "required_status_checks"}, {"name", "enforcement", "target", "bypass_actor_count", "deletion", "non_fast_forward", "linear_history", "do_not_enforce_on_create", "pull_request_required", "required_approving_review_count", "allowed_merge_methods", "strict_required_status_checks_policy", "required_status_checks"}, "evidence.facts.ruleset")
    if ruleset["name"] is not None and (
        not isinstance(ruleset["name"], str)
        or not ruleset["name"]
        or len(ruleset["name"]) > 128
    ):
        raise RepositoryTrustError("evidence.facts.ruleset.name must be a bounded string or null")
    enum_string(ruleset["enforcement"], {"active", "disabled", "evaluate"}, "evidence.facts.ruleset.enforcement", optional=True)
    enum_string(ruleset["target"], {"default_branch", "other"}, "evidence.facts.ruleset.target", optional=True)
    integer(ruleset["bypass_actor_count"], "evidence.facts.ruleset.bypass_actor_count", optional=True)
    for name in ("deletion", "non_fast_forward", "linear_history", "do_not_enforce_on_create", "pull_request_required", "strict_required_status_checks_policy"):
        boolean(ruleset[name], f"evidence.facts.ruleset.{name}", optional=True)
    integer(ruleset["required_approving_review_count"], "evidence.facts.ruleset.required_approving_review_count", maximum=10, optional=True)
    normalized_methods = merge_methods(ruleset["allowed_merge_methods"], "evidence.facts.ruleset.allowed_merge_methods", optional=True)
    if normalized_methods != ruleset["allowed_merge_methods"]:
        raise RepositoryTrustError("evidence.facts.ruleset.allowed_merge_methods must be sorted")
    normalized_checks = status_checks(ruleset["required_status_checks"], "evidence.facts.ruleset.required_status_checks", optional=True)
    if normalized_checks != ruleset["required_status_checks"]:
        raise RepositoryTrustError("evidence.facts.ruleset.required_status_checks must be sorted")

    security = exact_object(root["security"], {"dependabot_alerts", "dependabot_security_updates", "secret_scanning", "secret_scanning_push_protection", "private_vulnerability_reporting", "contact"}, {"dependabot_alerts", "dependabot_security_updates", "secret_scanning", "secret_scanning_push_protection", "private_vulnerability_reporting", "contact"}, "evidence.facts.security")
    for name in ("dependabot_alerts", "dependabot_security_updates", "secret_scanning", "secret_scanning_push_protection", "private_vulnerability_reporting"):
        boolean(security[name], f"evidence.facts.security.{name}", optional=True)
    if security["contact"] is not None and (
        not isinstance(security["contact"], str) or CONTACT.fullmatch(security["contact"]) is None
    ):
        raise RepositoryTrustError("evidence.facts.security.contact must be a bounded GitHub handle or null")
    return root


def validate_evidence(evidence: Any) -> dict[str, Any]:
    validate_json_shape(evidence)
    root = exact_object(evidence, {"kind", "schema_version", "project", "policy_sha256", "observed_at", "result", "facts", "checks"}, {"kind", "schema_version", "project", "policy_sha256", "observed_at", "result", "facts", "checks"}, "evidence")
    if root["kind"] != KIND or root["project"] != PROJECT:
        raise RepositoryTrustError("evidence identity is invalid")
    if type(root["schema_version"]) is not int or root["schema_version"] != 1:
        raise RepositoryTrustError("evidence schema_version must be integer 1")
    if not isinstance(root["policy_sha256"], str) or SHA256.fullmatch(root["policy_sha256"]) is None:
        raise RepositoryTrustError("evidence policy_sha256 is invalid")
    timestamp(root["observed_at"], "evidence.observed_at", optional=True)
    if root["result"] not in {"pass", "fail", "unavailable"}:
        raise RepositoryTrustError("evidence result is invalid")
    facts = validate_facts(root["facts"])
    checks = root["checks"]
    if not isinstance(checks, list) or len(checks) != len(CHECK_IDS):
        raise RepositoryTrustError("evidence checks differ from the complete ordered set")
    for expected_id, item in zip(CHECK_IDS, checks, strict=True):
        checked = exact_object(item, {"id", "status"}, {"id", "status"}, f"evidence check {expected_id}")
        if checked["id"] != expected_id or checked["status"] not in {"pass", "fail", "unavailable"}:
            raise RepositoryTrustError(f"evidence check {expected_id} is invalid")
    expected_checks = check_statuses(facts)
    if checks != expected_checks or root["result"] != aggregate(expected_checks):
        raise RepositoryTrustError("evidence result or checks differ from their facts")
    if root["observed_at"] is None and facts != empty_facts():
        raise RepositoryTrustError("evidence without an observation time must not contain observed facts")
    return root


def json_bytes(document: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def validate_local_contract(root: Path, policy: dict[str, Any]) -> None:
    raw = read_regular(root / SECURITY_PATH, MAX_SECURITY_BYTES, "security policy")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RepositoryTrustError("security policy is not UTF-8") from exc
    contact = policy["security"]["contact"]
    expected = f"Security contact: [{contact}](https://github.com/{contact.removeprefix('@')})"
    if text.count(expected) != 1:
        raise RepositoryTrustError("security policy must name the approved contact exactly once")


def evaluate_repository(root: Path = ROOT) -> tuple[dict[str, Any], int]:
    policy, policy_digest = load_policy(root)
    validate_local_contract(root, policy)
    observation_path = root / OBSERVATION_PATH
    try:
        observation_path.lstat()
    except FileNotFoundError:
        evidence = build_evidence(policy_digest, None, empty_facts())
        return evidence, 3
    except OSError as exc:
        raise RepositoryTrustError(f"cannot inspect repository trust observation: {exc}") from exc
    raw = read_regular(observation_path, MAX_OBSERVATION_BYTES, "repository trust observation")
    observation = validate_observation(parse_json(raw, "repository trust observation"))
    facts = facts_from_observation(observation)
    evidence = build_evidence(policy_digest, observation["observed_at"], facts)
    return evidence, {"pass": 0, "fail": 1, "unavailable": 3}[evidence["result"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "evaluate"))
    args = parser.parse_args()
    try:
        if args.command == "validate":
            policy, _ = load_policy(ROOT)
            validate_local_contract(ROOT, policy)
            print("repository-trust: PASS")
            return 0
        evidence, exit_code = evaluate_repository(ROOT)
        sys.stdout.buffer.write(json_bytes(evidence))
        return exit_code
    except RepositoryTrustError as exc:
        print(f"repository-trust: INVALID: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"repository-trust: INVALID: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
