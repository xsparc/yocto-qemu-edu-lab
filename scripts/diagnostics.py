#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Deterministic, read-only diagnostics for the selected QEMU EDU lab."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import diagnostics_git
import lab_config
import platform_runtime_evidence
import runtime_evidence
import source_lock
import validate_workflow
from diagnostics_inputs import (
    InputContractError,
    InputUnavailable,
    read_regular,
    require_directory,
    require_entry,
)


PROJECT_NAME = "yocto-qemu-edu-lab"
SCHEMA_VERSION = 1
SOURCE_ORDER = ("bitbake", "openembedded-core", "meta-yocto")
MAX_VERSION_BYTES = 128
MAX_WORKFLOW_BYTES = 256 * 1024
MAX_EVIDENCE_BYTES = 1024 * 1024
MAX_TASK_ID_LENGTH = 64
TASK_ID = re.compile(r"A[0-9]{3,}\Z")
PROJECT_VERSION = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:-(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
)

CHECKS = {
    "project.version": (True, "Project version is valid.", "Project version is invalid.", "Project version is unavailable."),
    "repository.git": (True, "Repository identity is valid.", "Repository identity is invalid.", "Repository identity is unavailable."),
    "workflow.task": (True, "Maintenance task state is valid.", "Maintenance task state is invalid.", "Maintenance task state is unavailable."),
    "inputs.source-lock": (True, "Source lock is valid.", "Source lock is invalid.", "Source lock is unavailable."),
    "inputs.lab-catalog": (True, "Lab catalog is valid.", "Lab catalog is invalid.", "Lab catalog could not be evaluated."),
    "lab.selection": (True, "Selected lab is valid.", "Selected lab is inconsistent.", "Selected lab could not be evaluated."),
    "repository.clean": (False, "Repository worktree is clean.", "Repository worktree has uncommitted changes.", "Repository cleanliness could not be evaluated."),
    "tool.git": (True, "Required Git executable is available.", "Git executable does not meet the diagnostic contract.", "Required Git executable is unavailable."),
    "tool.ssh": (True, "Required SSH executable is available.", "SSH executable does not meet the diagnostic contract.", "Required SSH executable is unavailable."),
    "source.bitbake": (True, "BitBake checkout matches the source lock.", "BitBake checkout differs from the source lock.", "BitBake checkout is unavailable."),
    "source.openembedded-core": (True, "OpenEmbedded Core checkout matches the source lock.", "OpenEmbedded Core checkout differs from the source lock.", "OpenEmbedded Core checkout is unavailable."),
    "source.meta-yocto": (True, "Meta-Yocto checkout matches the source lock.", "Meta-Yocto checkout differs from the source lock.", "Meta-Yocto checkout is unavailable."),
    "build.local-conf": (True, "Declared local configuration file is present.", "Declared local configuration path is invalid.", "Declared local configuration file is unavailable."),
    "build.bblayers-conf": (True, "Declared layer configuration file is present.", "Declared layer configuration path is invalid.", "Declared layer configuration file is unavailable."),
    "evidence.file": (True, "Selected evidence file is readable and bounded.", "Selected evidence path violates the file contract.", "Selected evidence file is unavailable."),
    "evidence.document": (True, "Evidence document is valid.", "Evidence document is invalid.", "Evidence document could not be evaluated."),
    "evidence.result": (True, "Evidence records a clean passing suite.", "Evidence does not record a clean passing suite.", "Evidence result could not be evaluated."),
    "evidence.inputs": (True, "Evidence inputs match the selected project inputs.", "Evidence inputs differ from the selected project inputs.", "Evidence inputs could not be evaluated."),
    "evidence.subject": (False, "Evidence subject matches the current revision.", "Evidence describes a different clean revision.", "Evidence subject match could not be evaluated."),
}

SEQUENCES = {
    "status": ("project.version", "repository.git", "workflow.task", "inputs.source-lock", "inputs.lab-catalog", "lab.selection", "repository.clean"),
    "doctor": ("project.version", "repository.git", "workflow.task", "inputs.source-lock", "inputs.lab-catalog", "lab.selection", "tool.git", "tool.ssh", "source.bitbake", "source.openembedded-core", "source.meta-yocto", "build.local-conf", "build.bblayers-conf", "evidence.file", "evidence.document", "evidence.result", "evidence.inputs", "evidence.subject"),
    "inspect": ("project.version", "repository.git", "inputs.source-lock", "inputs.lab-catalog", "lab.selection"),
    "evidence": ("project.version", "repository.git", "inputs.source-lock", "inputs.lab-catalog", "lab.selection", "evidence.file", "evidence.document", "evidence.result", "evidence.inputs", "evidence.subject"),
}


@dataclass(frozen=True)
class Check:
    id: str
    status: str
    required: bool
    summary: str

    def object(self) -> dict[str, Any]:
        return {"id": self.id, "status": self.status, "required": self.required, "summary": self.summary}


class DiagnosticArgumentError(ValueError):
    """A caller supplied a selector outside the closed catalog contract."""


def valid_project_version(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.isascii()
        and 0 < len(value) <= MAX_VERSION_BYTES
        and PROJECT_VERSION.fullmatch(value) is not None
    )


def valid_lab_id(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= lab_config.MAX_STRING_LENGTH
        and lab_config.LAB_ID.fullmatch(value) is not None
    )


def valid_active_task(value: Any) -> bool:
    if value is None:
        return True
    return (
        isinstance(value, dict)
        and set(value) == {"id", "status"}
        and isinstance(value.get("id"), str)
        and len(value["id"]) <= MAX_TASK_ID_LENGTH
        and TASK_ID.fullmatch(value["id"]) is not None
        and value.get("status") == "In Progress"
    )


def exact_object(value: Any, fields: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == fields


def valid_sha(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None
    )


def valid_token(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= lab_config.MAX_STRING_LENGTH
        and lab_config.TOKEN.fullmatch(value) is not None
    )


def valid_relative_path(value: Any) -> bool:
    try:
        lab_config.relative_path(value, "diagnostics projection")
    except lab_config.LabError:
        return False
    return True


def valid_build_directory(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= lab_config.MAX_STRING_LENGTH
        and lab_config.BUILD_DIRECTORY.fullmatch(value) is not None
    )


def valid_git_ref(value: Any, prefix: str) -> bool:
    try:
        source_lock.git_ref(value, "diagnostics projection", prefix)
    except source_lock.LockError:
        return False
    return True


def valid_https_url(value: Any) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= source_lock.MAX_STRING_LENGTH
        and value.startswith("https://")
        and not any(character.isspace() for character in value)
        and "\\" not in value
    )


def valid_selected_lab(value: Any) -> bool:
    fields = {"build_dir", "machine", "image", "driver", "evidence_profile"}
    return (
        exact_object(value, fields)
        and isinstance(value, dict)
        and valid_build_directory(value["build_dir"])
        and all(valid_token(value[field]) for field in fields - {"build_dir"})
    )


def valid_source_lock_projection(value: Any) -> bool:
    return (
        exact_object(value, {"sha256", "yocto_version", "yocto_series"})
        and isinstance(value, dict)
        and valid_sha(value["sha256"], 64)
        and valid_token(value["yocto_version"])
        and valid_token(value["yocto_series"])
    )


def valid_evidence_summary(value: Any) -> bool:
    fields = {
        "kind", "schema_version", "project", "build", "result", "summary",
        "native_input_sha256", "source_lock_sha256", "file_sha256",
    }
    if not exact_object(value, fields) or not isinstance(value, dict):
        return False
    kind = value["kind"]
    version = value["schema_version"]
    if not (
        (kind == runtime_evidence.KIND and type(version) is int and version in {1, 2, 3})
        or (
            kind == platform_runtime_evidence.KIND
            and type(version) is int
            and version == 1
        )
    ):
        return False
    expected_total = (
        len(runtime_evidence.SUPPORTED_TESTS[version])
        if kind == runtime_evidence.KIND
        else len(platform_runtime_evidence.EXPECTED_TESTS)
    )
    project = value["project"]
    build = value["build"]
    summary = value["summary"]
    summary_fields = {
        "total",
        "passed",
        "failed",
        "skipped",
        "errors",
        "expected_failures",
        "unknown",
    }
    shape_valid = (
        exact_object(project, {"version", "revision", "dirty"})
        and isinstance(project, dict)
        and valid_project_version(project["version"])
        and valid_sha(project["revision"], 40)
        and type(project["dirty"]) is bool
        and exact_object(build, {"machine", "image", "testimage_exit_code"})
        and isinstance(build, dict)
        and valid_token(build["machine"])
        and valid_token(build["image"])
        and type(build["testimage_exit_code"]) is int
        and 0 <= build["testimage_exit_code"] <= 255
        and value["result"] in {"passed", "failed"}
        and exact_object(summary, summary_fields)
        and isinstance(summary, dict)
        and all(type(summary[field]) is int and summary[field] >= 0 for field in summary)
        and valid_sha(value["native_input_sha256"], 64)
        and valid_sha(value["source_lock_sha256"], 64)
        and valid_sha(value["file_sha256"], 64)
    )
    if not shape_valid:
        return False
    categories = (
        "passed", "failed", "skipped", "errors", "expected_failures", "unknown"
    )
    if summary["total"] != expected_total or summary["total"] != sum(
        summary[field] for field in categories
    ):
        return False
    expected_result = (
        "passed"
        if summary["passed"] == expected_total
        and build["testimage_exit_code"] == 0
        else "failed"
    )
    return value["result"] == expected_result


def valid_evidence_inputs(value: Any) -> bool:
    if not exact_object(
        value, {"lab_binding", "lab_index_sha256", "lab_manifest_sha256"}
    ) or not isinstance(value, dict):
        return False
    if value["lab_binding"] == "bound":
        return valid_sha(value["lab_index_sha256"], 64) and valid_sha(
            value["lab_manifest_sha256"], 64
        )
    return (
        value["lab_binding"] == "not-recorded"
        and value["lab_index_sha256"] is None
        and value["lab_manifest_sha256"] is None
    )


def valid_source_projection(value: Any, expected_id: str) -> bool:
    return (
        exact_object(value, {"id", "url", "branch_ref", "release_ref", "commit"})
        and isinstance(value, dict)
        and value["id"] == expected_id
        and valid_https_url(value["url"])
        and value["url"] == source_lock.SOURCE_URLS[expected_id]
        and valid_git_ref(value["branch_ref"], "refs/heads/")
        and valid_git_ref(value["release_ref"], "refs/tags/")
        and valid_sha(value["commit"], 40)
    )


def valid_status_data(value: Any) -> bool:
    return (
        exact_object(value, {"active_task", "source_lock", "selected_lab"})
        and isinstance(value, dict)
        and valid_active_task(value["active_task"])
        and (
            value["source_lock"] is None
            or valid_source_lock_projection(value["source_lock"])
        )
        and (
            value["selected_lab"] is None
            or valid_selected_lab(value["selected_lab"])
        )
    )


def valid_doctor_data(value: Any) -> bool:
    return (
        exact_object(value, {"active_task", "evidence"})
        and isinstance(value, dict)
        and valid_active_task(value["active_task"])
        and (
            value["evidence"] is None
            or valid_evidence_summary(value["evidence"])
        )
    )


def valid_inspect_data(value: Any) -> bool:
    fields = {"release", "sources", "build", "emulator", "runtime", "source_lock_sha256"}
    if not exact_object(value, fields) or not isinstance(value, dict):
        return False
    release = value["release"]
    sources = value["sources"]
    build = value["build"]
    emulator = value["emulator"]
    runtime = value["runtime"]
    release_valid = release is None or (
        exact_object(release, {"project_version", "yocto_version", "yocto_series"})
        and isinstance(release, dict)
        and valid_project_version(release["project_version"])
        and valid_token(release["yocto_version"])
        and valid_token(release["yocto_series"])
    )
    sources_valid = sources is None or (
        isinstance(sources, list)
        and len(sources) == len(SOURCE_ORDER)
        and all(
            valid_source_projection(item, source_id)
            for item, source_id in zip(sources, SOURCE_ORDER, strict=True)
        )
    )
    build_valid = build is None or (
        exact_object(build, {"build_dir", "machine", "image", "driver", "layers"})
        and isinstance(build, dict)
        and valid_build_directory(build["build_dir"])
        and all(valid_token(build[field]) for field in ("machine", "image", "driver"))
        and isinstance(build["layers"], list)
        and 1 <= len(build["layers"]) <= 16
        and len(build["layers"]) == len(set(build["layers"]))
        and all(valid_relative_path(layer) for layer in build["layers"])
    )
    emulator_valid = emulator is None or (
        exact_object(emulator, {"profile", "system_binary"})
        and isinstance(emulator, dict)
        and valid_token(emulator["profile"])
        and valid_token(emulator["system_binary"])
    )
    runtime_valid = runtime is None or (
        exact_object(
            runtime,
            {"suite", "evidence_profile", "guest_contract_version", "evidence_schema_version"},
        )
        and isinstance(runtime, dict)
        and valid_token(runtime["suite"])
        and valid_token(runtime["evidence_profile"])
        and type(runtime["guest_contract_version"]) is int
        and 1 <= runtime["guest_contract_version"] <= 3
        and type(runtime["evidence_schema_version"]) is int
        and 1 <= runtime["evidence_schema_version"] <= 3
    )
    return (
        release_valid
        and sources_valid
        and build_valid
        and emulator_valid
        and runtime_valid
        and (
            value["source_lock_sha256"] is None
            or valid_sha(value["source_lock_sha256"], 64)
        )
    )


def valid_evidence_data(value: Any) -> bool:
    return (
        exact_object(value, {"evidence", "inputs", "subject_matches_head"})
        and isinstance(value, dict)
        and (value["evidence"] is None or valid_evidence_summary(value["evidence"]))
        and (value["inputs"] is None or valid_evidence_inputs(value["inputs"]))
        and (
            value["subject_matches_head"] is None
            or type(value["subject_matches_head"]) is bool
        )
    )


def check(check_id: str, status: str) -> Check:
    required, passed, failed, unavailable = CHECKS[check_id]
    if status == "pass":
        summary = passed
    elif status == "fail":
        summary = failed
    elif status == "unavailable":
        summary = unavailable
    elif status == "warning" and check_id in {"repository.clean", "evidence.subject"}:
        summary = failed
    elif status == "warning" and check_id == "evidence.inputs":
        summary = "Historical PCI evidence does not record lab catalog bindings."
    else:
        raise ValueError("unsupported check status")
    return Check(check_id, status, required, summary)


class Context:
    def __init__(self, root: Path, lab_id: str | None):
        self.root = root.resolve(strict=True)
        if lab_id is not None and not valid_lab_id(lab_id):
            raise DiagnosticArgumentError("invalid lab selector")
        self.lab_id = lab_id
        self.version: str | None = None
        self.revision: str | None = None
        self.dirty: bool | None = None
        self.active_task: dict[str, str] | None = None
        self.git_executable: Path | None = None
        self.git_state: str | None = None
        self.lock: dict[str, Any] | None = None
        self.lock_digest: str | None = None
        self.catalog: dict[str, Any] | None = None
        self.index_digest: str | None = None
        self.manifests: dict[str, dict[str, Any]] | None = None
        self.manifest_digests: dict[str, str] | None = None
        self.manifest: dict[str, Any] | None = None
        self.manifest_digest: str | None = None
        self.evidence_raw: bytes | None = None
        self.evidence_document: dict[str, Any] | None = None
        self.evidence_digest: str | None = None
        self.evidence_summary: dict[str, Any] | None = None
        self.lab_binding: str | None = None
        self.subject_matches: bool | None = None
        self.statuses: dict[str, str] = {}

    def record(self, item: Check) -> Check:
        self.statuses[item.id] = item.status
        return item

    def blocked(self, *ids: str) -> bool:
        return any(self.statuses.get(item) not in {"pass", "warning"} for item in ids)

    def project_version(self) -> Check:
        try:
            raw = read_regular(self.root, "VERSION", MAX_VERSION_BYTES)
        except InputUnavailable:
            return self.record(check("project.version", "unavailable"))
        except InputContractError:
            return self.record(check("project.version", "fail"))
        try:
            value = raw.decode("utf-8").strip()
        except UnicodeDecodeError:
            return self.record(check("project.version", "fail"))
        if raw != (value + "\n").encode("utf-8") or not valid_project_version(value):
            return self.record(check("project.version", "fail"))
        self.version = value
        return self.record(check("project.version", "pass"))

    def _git(self) -> tuple[Path | None, str]:
        if self.git_state is not None:
            return self.git_executable, self.git_state
        try:
            executable = diagnostics_git.resolve_native("git")
            diagnostics_git.git_version(executable, self.root)
        except diagnostics_git.ToolUnavailable:
            self.git_state = "unavailable"
            return None, "unavailable"
        except diagnostics_git.ToolContractError:
            self.git_state = "fail"
            return None, "fail"
        self.git_executable = executable
        self.git_state = "pass"
        return executable, "pass"

    def repository(self) -> Check:
        executable, state = self._git()
        if executable is None:
            return self.record(check("repository.git", state))
        try:
            self.revision, self.dirty = diagnostics_git.repository_state(executable, self.root)
        except (diagnostics_git.ToolContractError, OSError, UnicodeError):
            return self.record(check("repository.git", "fail"))
        return self.record(check("repository.git", "pass"))

    def workflow(self) -> Check:
        self.active_task = None
        try:
            config_raw = read_regular(self.root, "docs/maintainers/config.toml", MAX_WORKFLOW_BYTES)
            tasks_raw = read_regular(self.root, "docs/maintainers/tasks.toml", MAX_WORKFLOW_BYTES)
            ledger_raw = read_regular(self.root, "docs/maintainers/ledger.md", MAX_WORKFLOW_BYTES)
        except InputUnavailable:
            return self.record(check("workflow.task", "unavailable"))
        except InputContractError:
            return self.record(check("workflow.task", "fail"))
        try:
            config = validate_workflow.parse_toml_bytes(config_raw, "workflow configuration")
            tasks = validate_workflow.parse_toml_bytes(tasks_raw, "task state")
            errors, active = validate_workflow.validate_models(config, tasks, ledger_raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return self.record(check("workflow.task", "fail"))
        if errors:
            return self.record(check("workflow.task", "fail"))
        self.active_task = active
        return self.record(check("workflow.task", "pass"))

    def source_lock(self) -> Check:
        try:
            raw = read_regular(self.root, "config/sources.lock.json", source_lock.MAX_JSON_BYTES)
        except InputUnavailable:
            return self.record(check("inputs.source-lock", "unavailable"))
        except InputContractError:
            return self.record(check("inputs.source-lock", "fail"))
        try:
            self.lock, self.lock_digest = source_lock.parse_lock_bytes(raw)
        except source_lock.LockError:
            return self.record(check("inputs.source-lock", "fail"))
        return self.record(check("inputs.source-lock", "pass"))

    def lab_catalog(self) -> Check:
        if self.blocked("inputs.source-lock") or self.lock is None:
            return self.record(check("inputs.lab-catalog", "unavailable"))
        try:
            index_raw = read_regular(self.root, lab_config.DEFAULT_INDEX, lab_config.MAX_JSON_BYTES)
        except InputUnavailable:
            return self.record(check("inputs.lab-catalog", "unavailable"))
        except InputContractError:
            return self.record(check("inputs.lab-catalog", "fail"))
        try:
            index, _ = lab_config.parse_index_bytes(index_raw)
        except lab_config.LabError:
            return self.record(check("inputs.lab-catalog", "fail"))
        if self.lab_id is None:
            self.lab_id = index["default_lab"]
        manifest_bytes: dict[str, bytes] = {}
        try:
            for entry in index["labs"]:
                manifest_bytes[entry["manifest"]] = read_regular(
                    self.root, entry["manifest"], lab_config.MAX_JSON_BYTES
                )
        except InputUnavailable:
            return self.record(check("inputs.lab-catalog", "unavailable"))
        except InputContractError:
            return self.record(check("inputs.lab-catalog", "fail"))
        try:
            self.catalog, self.index_digest, self.manifests, self.manifest_digests = lab_config.read_catalog_bytes(
                index_raw, manifest_bytes, self.lock
            )
        except lab_config.LabError:
            return self.record(check("inputs.lab-catalog", "fail"))
        return self.record(check("inputs.lab-catalog", "pass"))

    def selection(self) -> Check:
        if self.blocked("inputs.lab-catalog") or self.manifests is None or self.manifest_digests is None:
            return self.record(check("lab.selection", "unavailable"))
        self.manifest = self.manifests.get(self.lab_id)
        self.manifest_digest = self.manifest_digests.get(self.lab_id)
        if self.manifest is None or self.manifest_digest is None:
            raise DiagnosticArgumentError("unknown lab selector")
        return self.record(check("lab.selection", "pass"))

    def cleanliness(self) -> Check:
        if self.blocked("repository.git") or self.dirty is None:
            return self.record(check("repository.clean", "unavailable"))
        return self.record(check("repository.clean", "warning" if self.dirty else "pass"))

    def tool_git(self) -> Check:
        _, state = self._git()
        return self.record(check("tool.git", state))

    def tool_ssh(self) -> Check:
        try:
            diagnostics_git.resolve_native("ssh")
        except diagnostics_git.ToolUnavailable:
            return self.record(check("tool.ssh", "unavailable"))
        except diagnostics_git.ToolContractError:
            return self.record(check("tool.ssh", "fail"))
        return self.record(check("tool.ssh", "pass"))

    def source_checkout(self, source_id: str) -> Check:
        check_id = f"source.{source_id}"
        if self.blocked("tool.git", "inputs.source-lock") or self.lock is None or self.git_executable is None:
            return self.record(check(check_id, "unavailable"))
        source = next(item for item in self.lock["sources"] if item["id"] == source_id)
        try:
            path = require_directory(self.root, source["path"])
        except InputUnavailable:
            return self.record(check(check_id, "unavailable"))
        except InputContractError:
            return self.record(check(check_id, "fail"))
        try:
            matches = diagnostics_git.checkout_matches(self.git_executable, path, source)
            for required in source["required_paths"]:
                try:
                    require_entry(self.root, f"{source['path']}/{required}")
                except (InputUnavailable, InputContractError):
                    matches = False
        except (diagnostics_git.ToolContractError, OSError, UnicodeError):
            return self.record(check(check_id, "fail"))
        return self.record(check(check_id, "pass" if matches else "fail"))

    def build_file(self, name: str) -> Check:
        check_id = f"build.{name.replace('.', '-')}"
        if self.blocked("lab.selection") or self.manifest is None:
            return self.record(check(check_id, "unavailable"))
        relative = f"{self.manifest['build']['build_dir']}/conf/{name}"
        try:
            read_regular(self.root, relative, 4 * 1024 * 1024)
        except InputUnavailable:
            return self.record(check(check_id, "unavailable"))
        except InputContractError:
            return self.record(check(check_id, "fail"))
        return self.record(check(check_id, "pass"))

    def evidence_file(self) -> Check:
        if self.blocked("lab.selection") or self.manifest is None:
            return self.record(check("evidence.file", "unavailable"))
        relative = f"{self.manifest['build']['build_dir']}/{self.manifest['runtime']['evidence_filename']}"
        try:
            self.evidence_raw = read_regular(self.root, relative, MAX_EVIDENCE_BYTES)
        except InputUnavailable:
            return self.record(check("evidence.file", "unavailable"))
        except InputContractError:
            return self.record(check("evidence.file", "fail"))
        self.evidence_digest = hashlib.sha256(self.evidence_raw).hexdigest()
        return self.record(check("evidence.file", "pass"))

    def evidence_document_check(self) -> Check:
        if self.blocked("evidence.file", "lab.selection") or self.evidence_raw is None:
            return self.record(check("evidence.document", "unavailable"))
        try:
            document = runtime_evidence.parse_object_bytes(
                self.evidence_raw, "selected evidence", max_bytes=MAX_EVIDENCE_BYTES
            )
            if document.get("kind") == runtime_evidence.KIND:
                runtime_evidence.validate_evidence(document)
                if document.get("schema_version") not in {1, 2, 3}:
                    raise runtime_evidence.EvidenceError("unsupported PCI evidence")
                binding = "not-recorded"
            elif document.get("kind") == platform_runtime_evidence.KIND:
                platform_runtime_evidence.validate_evidence(document)
                binding = "bound"
            else:
                raise runtime_evidence.EvidenceError("unsupported evidence kind")
            if not valid_project_version(document["project"]["version"]):
                raise runtime_evidence.EvidenceError("unsafe evidence project version")
            if not lab_config.TOKEN.fullmatch(document["build"]["machine"]):
                raise runtime_evidence.EvidenceError("unsafe evidence machine")
            if not lab_config.TOKEN.fullmatch(document["build"]["image"]):
                raise runtime_evidence.EvidenceError("unsafe evidence image")
        except (runtime_evidence.EvidenceError, KeyError, TypeError, ValueError):
            return self.record(check("evidence.document", "fail"))
        self.evidence_document = document
        self.lab_binding = binding
        if (
            self.version is not None
            and self.manifest is not None
            and document["project"]["version"] == self.version
            and document["build"]["machine"] == self.manifest["build"]["machine"]
            and document["build"]["image"] == self.manifest["build"]["targets"][0]
        ):
            self.evidence_summary = evidence_projection(document, self.evidence_digest)
        return self.record(check("evidence.document", "pass"))

    def evidence_result_check(self) -> Check:
        if self.blocked("evidence.document") or self.evidence_document is None:
            return self.record(check("evidence.result", "unavailable"))
        document = self.evidence_document
        try:
            if document["kind"] == runtime_evidence.KIND:
                runtime_evidence.validate_evidence(document, require_pass=True)
            else:
                platform_runtime_evidence.validate_evidence(document, require_pass=True)
        except runtime_evidence.EvidenceError:
            return self.record(check("evidence.result", "fail"))
        return self.record(check("evidence.result", "pass"))

    def evidence_inputs_check(self) -> Check:
        if self.blocked(
            "project.version", "evidence.document", "inputs.source-lock", "lab.selection"
        ) or self.evidence_document is None or self.manifest is None:
            return self.record(check("evidence.inputs", "unavailable"))
        evidence = self.evidence_document
        inputs = evidence["inputs"]
        build = evidence["build"]
        matches = (
            inputs["source_lock_sha256"] == self.lock_digest
            and evidence["project"]["version"] == self.version
            and build["machine"] == self.manifest["build"]["machine"]
            and build["image"] == self.manifest["build"]["targets"][0]
            and evidence["schema_version"] == self.manifest["runtime"]["evidence_schema_version"]
        )
        if self.lab_binding == "bound":
            matches = matches and (
                evidence["kind"] == platform_runtime_evidence.KIND
                and build["lab"] == self.lab_id
                and inputs["lab_index_sha256"] == self.index_digest
                and inputs["lab_manifest_sha256"] == self.manifest_digest
            )
            return self.record(check("evidence.inputs", "pass" if matches else "fail"))
        matches = matches and evidence["kind"] == runtime_evidence.KIND
        return self.record(check("evidence.inputs", "warning" if matches else "fail"))

    def evidence_subject_check(self) -> Check:
        if self.blocked("evidence.document", "evidence.result", "repository.git") or self.evidence_document is None or self.revision is None:
            return self.record(check("evidence.subject", "unavailable"))
        self.subject_matches = self.evidence_document["project"]["revision"] == self.revision
        return self.record(check("evidence.subject", "pass" if self.subject_matches else "warning"))


def evidence_projection(evidence: dict[str, Any], digest: str | None) -> dict[str, Any]:
    summary_keys = (
        "total",
        "passed",
        "failed",
        "skipped",
        "errors",
        "expected_failures",
        "unknown",
    )
    return {
        "kind": evidence["kind"],
        "schema_version": evidence["schema_version"],
        "project": {
            "version": evidence["project"]["version"],
            "revision": evidence["project"]["revision"],
            "dirty": evidence["project"]["dirty"],
        },
        "build": {
            "machine": evidence["build"]["machine"],
            "image": evidence["build"]["image"],
            "testimage_exit_code": evidence["build"]["testimage_exit_code"],
        },
        "result": evidence["result"],
        "summary": {key: evidence["summary"][key] for key in summary_keys},
        "native_input_sha256": evidence["inputs"]["oeqa_result_sha256"],
        "source_lock_sha256": evidence["inputs"]["source_lock_sha256"],
        "file_sha256": digest,
    }


def aggregate(checks: list[Check]) -> tuple[str, int]:
    if any(item.status == "fail" for item in checks):
        return "fail", 1
    if any(item.required and item.status == "unavailable" for item in checks):
        return "unavailable", 3
    if any(item.status in {"warning", "unavailable"} for item in checks):
        return "warning", 0
    return "pass", 0


def validate_state_transitions(statuses: dict[str, str]) -> None:
    dependencies = {
        "inputs.lab-catalog": ("inputs.source-lock",),
        "lab.selection": ("inputs.lab-catalog",),
        "repository.clean": ("repository.git",),
        "source.bitbake": ("tool.git", "inputs.source-lock"),
        "source.openembedded-core": ("tool.git", "inputs.source-lock"),
        "source.meta-yocto": ("tool.git", "inputs.source-lock"),
        "build.local-conf": ("lab.selection",),
        "build.bblayers-conf": ("lab.selection",),
        "evidence.file": ("lab.selection",),
        "evidence.document": ("evidence.file", "lab.selection"),
        "evidence.result": ("evidence.document",),
        "evidence.inputs": (
            "project.version",
            "evidence.document",
            "inputs.source-lock",
            "lab.selection",
        ),
        "evidence.subject": (
            "evidence.document",
            "evidence.result",
            "repository.git",
        ),
    }
    for downstream, upstreams in dependencies.items():
        if downstream not in statuses:
            continue
        present = tuple(item for item in upstreams if item in statuses)
        if any(statuses[item] not in {"pass", "warning"} for item in present):
            if statuses[downstream] != "unavailable":
                raise ValueError("diagnostics check dependency state is invalid")

    derived_states = {
        "lab.selection": (("inputs.lab-catalog",), {"pass", "fail"}),
        "repository.clean": (("repository.git",), {"pass", "warning"}),
        "evidence.document": (("evidence.file",), {"pass", "fail"}),
        "evidence.result": (("evidence.document",), {"pass", "fail"}),
        "evidence.inputs": (
            (
                "project.version",
                "evidence.document",
                "inputs.source-lock",
                "lab.selection",
            ),
            {"pass", "warning", "fail"},
        ),
        "evidence.subject": (
            ("evidence.document", "evidence.result", "repository.git"),
            {"pass", "warning"},
        ),
    }
    for downstream, (upstreams, allowed) in derived_states.items():
        if downstream not in statuses or any(
            item not in statuses for item in upstreams
        ):
            continue
        if all(statuses[item] == "pass" for item in upstreams):
            if statuses[downstream] not in allowed:
                raise ValueError("diagnostics derived check state is invalid")
    if "repository.git" in statuses and "tool.git" in statuses:
        tool_states = {
            "pass": {"pass"},
            "fail": {"pass", "fail"},
            "unavailable": {"unavailable"},
        }
        if statuses["tool.git"] not in tool_states[statuses["repository.git"]]:
            raise ValueError("diagnostics cached git state is invalid")


def validate_document(document: dict[str, Any]) -> None:
    expected_root = {"kind", "schema_version", "command", "result", "project", "lab", "checks", "data"}
    if not isinstance(document, dict) or set(document) != expected_root:
        raise ValueError("diagnostics document fields differ from the contract")
    if (
        document["kind"] != "qemu-edu-diagnostics"
        or type(document["schema_version"]) is not int
        or document["schema_version"] != 1
    ):
        raise ValueError("diagnostics document identity is invalid")
    command = document["command"]
    if command not in SEQUENCES or not isinstance(document["checks"], list):
        raise ValueError("diagnostics command is invalid")
    if len(document["checks"]) != len(SEQUENCES[command]):
        raise ValueError("diagnostics check count differs from the contract")
    checked: list[Check] = []
    for expected_id, raw in zip(SEQUENCES[command], document["checks"], strict=True):
        if not isinstance(raw, dict) or set(raw) != {"id", "status", "required", "summary"}:
            raise ValueError("diagnostics check fields differ from the contract")
        if (
            raw["id"] != expected_id
            or raw["status"] not in {"pass", "warning", "fail", "unavailable"}
            or type(raw["required"]) is not bool
        ):
            raise ValueError("diagnostics check identity or status is invalid")
        expected = check(expected_id, raw["status"])
        if raw != expected.object():
            raise ValueError("diagnostics check semantics differ from the contract")
        checked.append(expected)
    result, _ = aggregate(checked)
    if document["result"] != result:
        raise ValueError("diagnostics aggregate result differs from its checks")
    statuses = {item.id: item.status for item in checked}
    validate_state_transitions(statuses)
    project = document["project"]
    if not isinstance(project, dict) or set(project) != {"name", "version", "revision", "dirty"}:
        raise ValueError("diagnostics project fields differ from the contract")
    if project["name"] != PROJECT_NAME:
        raise ValueError("diagnostics project name is invalid")
    version_present = valid_project_version(project["version"])
    revision_present = isinstance(project["revision"], str) and re.fullmatch(r"[0-9a-f]{40}", project["revision"]) is not None
    dirty_present = type(project["dirty"]) is bool
    if version_present != (statuses["project.version"] == "pass"):
        raise ValueError("diagnostics project version differs from its check")
    if revision_present != (statuses["repository.git"] == "pass") or dirty_present != revision_present:
        raise ValueError("diagnostics repository identity differs from its check")
    lab = document["lab"]
    if not isinstance(lab, dict) or set(lab) != {"id", "index_sha256", "manifest_sha256"}:
        raise ValueError("diagnostics lab fields differ from the contract")
    lab_id_present = valid_lab_id(lab["id"])
    index_present = isinstance(lab["index_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", lab["index_sha256"]) is not None
    manifest_present = isinstance(lab["manifest_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", lab["manifest_sha256"]) is not None
    if lab["id"] is not None and not lab_id_present:
        raise ValueError("diagnostics lab id is invalid")
    if index_present != (statuses["inputs.lab-catalog"] == "pass"):
        raise ValueError("diagnostics catalog identity differs from its check")
    if manifest_present != (statuses["lab.selection"] == "pass"):
        raise ValueError("diagnostics lab manifest differs from its check")
    if statuses["lab.selection"] == "pass" and not lab_id_present:
        raise ValueError("diagnostics selected lab identity is unavailable")
    data = document["data"]
    data_validators = {
        "status": valid_status_data,
        "doctor": valid_doctor_data,
        "inspect": valid_inspect_data,
        "evidence": valid_evidence_data,
    }
    if not data_validators[command](data):
        raise ValueError("diagnostics command data differs from the contract")
    if command in {"status", "doctor"}:
        if statuses["workflow.task"] != "pass" and data.get("active_task") is not None:
            raise ValueError("diagnostics active task differs from its check")
    if command == "status":
        clean_status = statuses["repository.clean"]
        if clean_status not in {"pass", "warning", "unavailable"}:
            raise ValueError("diagnostics cleanliness status is invalid")
        expected_dirty = {"pass": False, "warning": True, "unavailable": None}[
            clean_status
        ]
        if project["dirty"] is not expected_dirty:
            raise ValueError("diagnostics cleanliness differs from its check")
        if (data["source_lock"] is not None) != (
            statuses["inputs.source-lock"] == "pass"
        ):
            raise ValueError("diagnostics source-lock data differs from its check")
        if (data["selected_lab"] is not None) != (
            statuses["lab.selection"] == "pass"
        ):
            raise ValueError("diagnostics selected-lab data differs from its check")
    if command == "inspect":
        projection_available = all(
            statuses[check_id] == "pass"
            for check_id in (
                "project.version",
                "inputs.source-lock",
                "inputs.lab-catalog",
                "lab.selection",
            )
        )
        projection_fields = (
            "release", "sources", "build", "emulator", "runtime", "source_lock_sha256"
        )
        if any(data[field] is not None for field in projection_fields) != projection_available:
            raise ValueError("diagnostics inspect data differs from its checks")
        if projection_available and any(
            data[field] is None for field in projection_fields
        ):
            raise ValueError("diagnostics inspect data is incomplete")
        if data["release"] is not None and (
            data["release"]["project_version"] != project["version"]
        ):
            raise ValueError("diagnostics inspect project identity differs")
    if command in {"doctor", "evidence"}:
        if statuses["evidence.document"] != "pass" and data["evidence"] is not None:
            raise ValueError("diagnostics evidence data differs from its check")
        if statuses["evidence.inputs"] in {"pass", "warning"} and data["evidence"] is None:
            raise ValueError("diagnostics evidence projection is incomplete")
        evidence = data["evidence"]
        if evidence is not None:
            if evidence["project"]["version"] != project["version"]:
                raise ValueError("diagnostics evidence project identity differs")
            clean_evidence = (
                evidence["result"] == "passed"
                and evidence["project"]["dirty"] is False
            )
            result_status = statuses["evidence.result"]
            if result_status not in {"pass", "fail"} or (
                result_status == "pass"
            ) != clean_evidence:
                raise ValueError("diagnostics evidence result differs from its facts")
            subject_status = statuses["evidence.subject"]
            if subject_status not in {"pass", "warning", "unavailable"}:
                raise ValueError("diagnostics evidence subject status is invalid")
            if subject_status in {"pass", "warning"}:
                identity_matches = (
                    evidence["project"]["revision"] == project["revision"]
                )
                if identity_matches != (subject_status == "pass"):
                    raise ValueError("diagnostics evidence revision differs from its subject")
            input_status = statuses["evidence.inputs"]
            expected_kind = {
                "pass": platform_runtime_evidence.KIND,
                "warning": runtime_evidence.KIND,
            }.get(input_status)
            if expected_kind is not None and evidence["kind"] != expected_kind:
                raise ValueError("diagnostics evidence binding kind differs")
    if command == "evidence":
        if (data["inputs"] is not None) != (
            statuses["evidence.document"] == "pass"
        ):
            raise ValueError("diagnostics evidence inputs differ from their check")
        subject_status = statuses["evidence.subject"]
        if subject_status not in {"pass", "warning", "unavailable"}:
            raise ValueError("diagnostics evidence subject status is invalid")
        expected_subject = {
            "pass": True,
            "warning": False,
            "unavailable": None,
        }[subject_status]
        if data["subject_matches_head"] is not expected_subject:
            raise ValueError("diagnostics evidence subject differs from its check")
        input_status = statuses["evidence.inputs"]
        if input_status == "pass":
            if not (
                data["inputs"]["lab_binding"] == "bound"
                and data["inputs"]["lab_index_sha256"] == lab["index_sha256"]
                and data["inputs"]["lab_manifest_sha256"] == lab["manifest_sha256"]
            ):
                raise ValueError("diagnostics bound evidence inputs differ")
        elif input_status == "warning" and data["inputs"]["lab_binding"] != "not-recorded":
            raise ValueError("diagnostics historical evidence binding differs")
    if result == "pass":
        validate_pass_data(command, data)


def validate_pass_data(command: str, data: Any) -> None:
    validators = {
        "status": valid_status_data,
        "doctor": valid_doctor_data,
        "inspect": valid_inspect_data,
        "evidence": valid_evidence_data,
    }
    if command not in validators or not validators[command](data):
        raise ValueError("passing diagnostics data is invalid")
    if command == "status":
        valid = data["source_lock"] is not None and data["selected_lab"] is not None
    elif command == "doctor":
        valid = data["evidence"] is not None
    elif command == "inspect":
        valid = all(
            data[field] is not None
            for field in (
                "release", "sources", "build", "emulator", "runtime", "source_lock_sha256"
            )
        )
    else:
        valid = (
            data["evidence"] is not None
            and data["inputs"] is not None
            and data["subject_matches_head"] is True
        )
    if not valid:
        raise ValueError("passing diagnostics data is incomplete")


def base(ctx: Context, command: str) -> list[Check]:
    items = [ctx.project_version(), ctx.repository()]
    if command in {"status", "doctor"}:
        items.append(ctx.workflow())
    items.extend((ctx.source_lock(), ctx.lab_catalog(), ctx.selection()))
    return items


def evidence_checks(ctx: Context) -> list[Check]:
    return [
        ctx.evidence_file(),
        ctx.evidence_document_check(),
        ctx.evidence_result_check(),
        ctx.evidence_inputs_check(),
        ctx.evidence_subject_check(),
    ]


def command_document(root: Path, command: str, lab_id: str | None = None) -> tuple[dict[str, Any], int]:
    if command not in SEQUENCES:
        raise ValueError("unknown diagnostics command")
    ctx = Context(root, lab_id)
    items = base(ctx, command)
    if command == "status":
        items.append(ctx.cleanliness())
        data = {
            "active_task": ctx.active_task,
            "source_lock": None if ctx.lock is None else {
                "sha256": ctx.lock_digest,
                "yocto_version": ctx.lock["release"]["version"],
                "yocto_series": ctx.lock["release"]["series"],
            },
            "selected_lab": selected_lab_projection(ctx),
        }
    elif command == "doctor":
        items.extend((ctx.tool_git(), ctx.tool_ssh()))
        items.extend(ctx.source_checkout(source_id) for source_id in SOURCE_ORDER)
        items.extend((ctx.build_file("local.conf"), ctx.build_file("bblayers.conf")))
        items.extend(evidence_checks(ctx))
        data = {"active_task": ctx.active_task, "evidence": ctx.evidence_summary}
    elif command == "inspect":
        data = inspect_projection(ctx)
    else:
        items.extend(evidence_checks(ctx))
        data = {
            "evidence": ctx.evidence_summary,
            "inputs": None if ctx.evidence_document is None else {
                "lab_binding": ctx.lab_binding,
                "lab_index_sha256": ctx.evidence_document["inputs"].get("lab_index_sha256"),
                "lab_manifest_sha256": ctx.evidence_document["inputs"].get("lab_manifest_sha256"),
            },
            "subject_matches_head": ctx.subject_matches,
        }
    if tuple(item.id for item in items) != SEQUENCES[command]:
        raise RuntimeError("internal diagnostics check order differs from the contract")
    result, exit_code = aggregate(items)
    document = {
        "kind": "qemu-edu-diagnostics",
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "result": result,
        "project": {"name": PROJECT_NAME, "version": ctx.version, "revision": ctx.revision, "dirty": ctx.dirty},
        "lab": {"id": ctx.lab_id, "index_sha256": ctx.index_digest, "manifest_sha256": ctx.manifest_digest},
        "checks": [item.object() for item in items],
        "data": data,
    }
    validate_document(document)
    return document, exit_code


def selected_lab_projection(ctx: Context) -> dict[str, Any] | None:
    if ctx.manifest is None:
        return None
    build = ctx.manifest["build"]
    return {
        "build_dir": build["build_dir"],
        "machine": build["machine"],
        "image": build["targets"][0],
        "driver": build["driver_target"],
        "evidence_profile": ctx.manifest["runtime"]["evidence_profile"],
    }


def inspect_projection(ctx: Context) -> dict[str, Any]:
    if ctx.version is None or ctx.lock is None or ctx.manifest is None:
        return {"release": None, "sources": None, "build": None, "emulator": None, "runtime": None, "source_lock_sha256": None}
    build = ctx.manifest["build"]
    runtime = ctx.manifest["runtime"]
    sources_by_id = {item["id"]: item for item in ctx.lock["sources"]}
    return {
        "release": {"project_version": ctx.version, "yocto_version": ctx.lock["release"]["version"], "yocto_series": ctx.lock["release"]["series"]},
        "sources": [
            {
                "id": item["id"],
                "url": item["url"],
                "branch_ref": item["branch_ref"],
                "release_ref": item["release_ref"],
                "commit": item["commit"],
            }
            for item in (sources_by_id[source_id] for source_id in SOURCE_ORDER)
        ],
        "build": {"build_dir": build["build_dir"], "machine": build["machine"], "image": build["targets"][0], "driver": build["driver_target"], "layers": build["layers"]},
        "emulator": {"profile": ctx.manifest["emulator"]["preflight_profile"], "system_binary": ctx.manifest["emulator"]["system_binary"]},
        "runtime": {"suite": runtime["suite"], "evidence_profile": runtime["evidence_profile"], "guest_contract_version": runtime["guest_contract_version"], "evidence_schema_version": runtime["evidence_schema_version"]},
        "source_lock_sha256": ctx.lock_digest,
    }


def json_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def text_bytes(document: dict[str, Any]) -> bytes:
    lines = [f"qemu-edu-lab {document['command']}: {document['result']}"]
    for item in document["checks"]:
        lines.append(f"[{item['status'].upper()}] {item['id']}: {item['summary']}")
    lines.append("data: " + json.dumps(document["data"], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
    return ("\n".join(lines) + "\n").encode("utf-8")
