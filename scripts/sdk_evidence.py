#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Validate and publish closed direct-eSDK iteration evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lab_config import LabError, select_lab  # noqa: E402
from diagnostics_git import (  # noqa: E402
    ToolContractError,
    ToolUnavailable,
    repository_state,
    resolve_native,
)
from source_lock import LockError, read_lock, status_result  # noqa: E402


SCHEMA_VERSION = 1
KIND = "qemu-edu-sdk-iteration-evidence"
PROJECT_NAME = "yocto-qemu-edu-lab"
PROFILE = "direct-esdk-devtool-v1"
MAX_EVIDENCE_BYTES = 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024
MAX_STRING_LENGTH = 4096
MAX_JSON_DEPTH = 24
MAX_JSON_ITEMS = 4096
MAX_JSON_INTEGER_DIGITS = 16
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")
SEMVER = re.compile(
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-((?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z"
)
CHECK_IDS = (
    "preflight.sources",
    "preflight.tooling",
    "preflight.composition",
    "preflight.emulator",
    "workspace.created",
    "source.prepared",
    "recipe.modified",
    "recipe.built",
    "artifact.bound",
    "sdk.generated",
    "base.absent",
    "target.architecture",
    "target.deployed",
    "target.executed",
    "target.undeployed",
    "target.absent",
    "workspace.reset",
    "source.retained",
    "cold_boot.absent",
    "cleanup.complete",
)
LAB_IDENTITIES = {
    "pci-x86-64": {
        "machine": "qemu-edu-x86-64",
        "architecture": "x86_64",
        "development_build_dir": "build-sdk-pci-x86-64",
    },
    "platform-arm64": {
        "machine": "qemu-edu-platform-arm64",
        "architecture": "aarch64",
        "development_build_dir": "build-sdk-platform-arm64",
    },
}


class SdkEvidenceError(ValueError):
    """An SDK evidence document or its authority failed validation."""


def exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise SdkEvidenceError(f"{where} has " + "; ".join(details))


def string_value(value: Any, where: str, *, maximum: int = MAX_STRING_LENGTH) -> str:
    if not isinstance(value, str) or not value:
        raise SdkEvidenceError(f"{where} must be a non-empty string")
    if len(value) > maximum:
        raise SdkEvidenceError(f"{where} exceeds {maximum} characters")
    if any(
        ord(character) < 0x20
        or ord(character) == 0x7F
        or 0xD800 <= ord(character) <= 0xDFFF
        for character in value
    ):
        raise SdkEvidenceError(f"{where} contains an unsupported character")
    return value


def sha1_value(value: Any, where: str) -> str:
    text = string_value(value, where)
    if not SHA1.fullmatch(text):
        raise SdkEvidenceError(f"{where} must be a lowercase SHA-1")
    return text


def sha256_value(value: Any, where: str) -> str:
    text = string_value(value, where)
    if not SHA256.fullmatch(text):
        raise SdkEvidenceError(f"{where} must be a lowercase SHA-256")
    return text


def object_value(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SdkEvidenceError(f"{where} must be an object")
    return value


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SdkEvidenceError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_value: str) -> Any:
    raise SdkEvidenceError("unsupported JSON constant")


def parse_bounded_integer(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise SdkEvidenceError("JSON integer exceeds its digit bound")
    return int(value)


def validate_json_shape(value: Any, *, depth: int = 0) -> int:
    if depth > MAX_JSON_DEPTH:
        raise SdkEvidenceError("evidence JSON exceeds its depth bound")
    if value is None or type(value) in (bool, int):
        return 1
    if isinstance(value, str):
        string_value(value, "evidence JSON string")
        return 1
    if isinstance(value, list):
        count = 1
        for item in value:
            count += validate_json_shape(item, depth=depth + 1)
            if count > MAX_JSON_ITEMS:
                raise SdkEvidenceError("evidence JSON exceeds its value bound")
        return count
    if isinstance(value, dict):
        count = 1
        for key, item in value.items():
            string_value(key, "evidence JSON key")
            count += validate_json_shape(item, depth=depth + 1)
            if count > MAX_JSON_ITEMS:
                raise SdkEvidenceError("evidence JSON exceeds its value bound")
        return count
    raise SdkEvidenceError("evidence JSON contains an unsupported value type")


def source_authority(repo: Path) -> tuple[dict[str, Any], str, str]:
    data, digest = read_lock(repo / "config/sources.lock.json")
    status = status_result(repo, data, digest)
    if not status["ok"]:
        raise SdkEvidenceError("locked sources are not ready")
    matches = [source for source in data["sources"] if source["id"] == "openembedded-core"]
    if len(matches) != 1:
        raise SdkEvidenceError("source lock must contain exactly one openembedded-core")
    return data, digest, matches[0]["commit"]


def project_state(repo: Path) -> tuple[str, bool]:
    try:
        revision, dirty = repository_state(resolve_native("git"), repo)
    except (ToolUnavailable, ToolContractError, OSError, UnicodeError) as exc:
        raise SdkEvidenceError("repository state is unavailable") from exc
    return sha1_value(revision, "project revision"), dirty


def selected_contract(
    repo: Path, lab_id: str | None
) -> tuple[dict[str, Any], str, str, str, dict[str, str]]:
    selected, manifest, index_digest, manifest_digest = select_lab(repo, lab_id)
    development = manifest["development"]
    identity = LAB_IDENTITIES.get(selected)
    if identity is None or development["profile"] != PROFILE:
        raise SdkEvidenceError("selected lab does not use the SDK evidence v1 profile")
    if manifest["build"]["machine"] != identity["machine"]:
        raise SdkEvidenceError("selected lab machine is not recognized")
    if manifest["build"]["targets"] != ["qemu-edu-image"]:
        raise SdkEvidenceError("selected lab image is not recognized")
    return manifest, selected, index_digest, manifest_digest, identity


def evidence_path(repo: Path, manifest: dict[str, Any], build_dir: Path | None = None) -> Path:
    expected_build = repo / manifest["development"]["build_dir"]
    if expected_build.is_symlink() or (
        expected_build.exists() and not expected_build.is_dir()
    ):
        raise SdkEvidenceError("development build root is not a regular directory")
    build_root = expected_build.resolve()
    if build_dir is not None and build_dir.resolve() != build_root:
        raise SdkEvidenceError("development build root differs from the lab contract")
    evidence_dir = build_root / "evidence"
    if evidence_dir.exists():
        if evidence_dir.is_symlink() or not evidence_dir.is_dir():
            raise SdkEvidenceError("evidence directory is not a regular directory")
        if evidence_dir.resolve(strict=True) != evidence_dir:
            raise SdkEvidenceError("evidence directory escapes the selected build directory")
    path = evidence_dir / manifest["development"]["evidence_filename"]
    if path.is_symlink():
        raise SdkEvidenceError("evidence output must not be a symbolic link")
    if path.exists() and not path.is_file():
        raise SdkEvidenceError("evidence output is not a regular file")
    return path


def verify_output(path: Path, *, create_parent: bool = False) -> None:
    if create_parent:
        path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise SdkEvidenceError("evidence directory is not a regular directory")
    if path.parent.resolve(strict=True) != path.parent:
        raise SdkEvidenceError("evidence directory escapes the selected build directory")
    if path.is_symlink():
        raise SdkEvidenceError("evidence output must not be a symbolic link")
    if path.exists() and not path.is_file():
        raise SdkEvidenceError("evidence output is not a regular file")


def clear_evidence(path: Path) -> None:
    verify_output(path, create_parent=True)
    path.unlink(missing_ok=True)


def build_evidence(
    repo: Path,
    lab_id: str,
    source_sha256: str,
    artifact_sha256: str,
) -> dict[str, Any]:
    repo = repo.resolve()
    manifest, selected, index_digest, manifest_digest, identity = selected_contract(
        repo, lab_id
    )
    lock, lock_digest, oe_core_commit = source_authority(repo)
    release = object_value(lock.get("release"), "source-lock release")
    revision, dirty = project_state(repo)
    if dirty:
        raise SdkEvidenceError("passing SDK evidence requires a clean repository")
    version = string_value(
        (repo / "VERSION").read_text(encoding="utf-8").strip(), "project version", maximum=128
    )
    if not SEMVER.fullmatch(version):
        raise SdkEvidenceError("project version is not SemVer")
    development = manifest["development"]
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "project": {
            "name": PROJECT_NAME,
            "version": version,
            "revision": revision,
            "dirty": False,
        },
        "inputs": {
            "source_lock_sha256": lock_digest,
            "openembedded_core_commit": oe_core_commit,
            "lab_index_sha256": index_digest,
            "lab_manifest_sha256": manifest_digest,
            "yocto_version": string_value(release.get("version"), "release.version"),
            "yocto_series": string_value(release.get("series"), "release.series"),
        },
        "lab": {
            "id": selected,
            "machine": manifest["build"]["machine"],
            "image": manifest["build"]["targets"][0],
            "development_build_dir": development["build_dir"],
            "recipe": development["recipe"],
            "source_dir": development["source_dir"],
            "guest_binary": development["guest_binary"],
        },
        "workflow": {
            "profile": PROFILE,
            "sdk_mode": "direct-build",
            "ide": development["ide"],
            "transport": "runqemu-slirp-loopback-ssh",
        },
        "source": {
            "sha256": sha256_value(source_sha256, "retained source digest"),
            "preserved_after_reset": True,
        },
        "execution": {
            "architecture": identity["architecture"],
            "expected_output": "qemu-edu-sdk-sample workspace",
            "artifact_sha256": sha256_value(
                artifact_sha256, "deployed artifact digest"
            ),
            "base_absent": True,
            "undeployed_absent": True,
            "cold_boot_absent": True,
        },
        "checks": [{"id": check_id, "status": "passed"} for check_id in CHECK_IDS],
        "task_exit_code": 0,
        "result": "passed",
    }
    validate_evidence(evidence, require_pass=True)
    return evidence


def validate_evidence(
    evidence: dict[str, Any],
    *,
    require_pass: bool = False,
    expected_revision: str | None = None,
    current_repo: Path | None = None,
) -> None:
    exact_keys(
        evidence,
        {
            "schema_version", "kind", "project", "inputs", "lab", "workflow",
            "source", "execution", "checks", "task_exit_code", "result",
        },
        "evidence",
    )
    if type(evidence["schema_version"]) is not int or evidence["schema_version"] != 1:
        raise SdkEvidenceError("unsupported evidence schema version")
    if evidence["kind"] != KIND:
        raise SdkEvidenceError("unsupported evidence kind")

    project = object_value(evidence["project"], "project")
    exact_keys(project, {"name", "version", "revision", "dirty"}, "project")
    if project["name"] != PROJECT_NAME:
        raise SdkEvidenceError("project.name is not recognized")
    version = string_value(project["version"], "project.version", maximum=128)
    if not SEMVER.fullmatch(version):
        raise SdkEvidenceError("project.version is not SemVer")
    revision = sha1_value(project["revision"], "project.revision")
    if project["dirty"] is not False:
        raise SdkEvidenceError("passing SDK evidence must record a clean repository")
    if expected_revision is not None and revision != sha1_value(
        expected_revision, "required revision"
    ):
        raise SdkEvidenceError("project revision does not match the required revision")

    inputs = object_value(evidence["inputs"], "inputs")
    exact_keys(
        inputs,
        {
            "source_lock_sha256", "openembedded_core_commit", "lab_index_sha256",
            "lab_manifest_sha256", "yocto_version", "yocto_series",
        },
        "inputs",
    )
    for key in ("source_lock_sha256", "lab_index_sha256", "lab_manifest_sha256"):
        sha256_value(inputs[key], f"inputs.{key}")
    sha1_value(inputs["openembedded_core_commit"], "inputs.openembedded_core_commit")
    for key in ("yocto_version", "yocto_series"):
        value = string_value(inputs[key], f"inputs.{key}")
        if not TOKEN.fullmatch(value):
            raise SdkEvidenceError(f"inputs.{key} is not a supported token")

    lab = object_value(evidence["lab"], "lab")
    exact_keys(
        lab,
        {"id", "machine", "image", "development_build_dir", "recipe", "source_dir", "guest_binary"},
        "lab",
    )
    lab_id = string_value(lab.get("id"), "lab.id")
    identity = LAB_IDENTITIES.get(lab_id)
    if identity is None or lab.get("machine") != identity["machine"]:
        raise SdkEvidenceError("lab identity is not recognized")
    manifest_fields = ("image", "development_build_dir", "recipe", "source_dir", "guest_binary")
    for key in manifest_fields:
        string_value(lab[key], f"lab.{key}")
    if lab["image"] != "qemu-edu-image":
        raise SdkEvidenceError("lab image is not recognized")
    if lab != {
        "id": lab_id,
        "machine": identity["machine"],
        "image": "qemu-edu-image",
        "development_build_dir": identity["development_build_dir"],
        "recipe": "qemu-edu-sdk-sample",
        "source_dir": "learner-source/qemu-edu-sdk-sample",
        "guest_binary": "/usr/bin/qemu-edu-sdk-sample",
    }:
        raise SdkEvidenceError("lab development identity is not recognized")

    workflow = object_value(evidence["workflow"], "workflow")
    exact_keys(workflow, {"profile", "sdk_mode", "ide", "transport"}, "workflow")
    if workflow != {
        "profile": PROFILE,
        "sdk_mode": "direct-build",
        "ide": "none",
        "transport": "runqemu-slirp-loopback-ssh",
    }:
        raise SdkEvidenceError("workflow is not the closed SDK profile")

    source = object_value(evidence["source"], "source")
    exact_keys(source, {"sha256", "preserved_after_reset"}, "source")
    sha256_value(source["sha256"], "source.sha256")
    if source["preserved_after_reset"] is not True:
        raise SdkEvidenceError("retained source was not preserved")

    execution = object_value(evidence["execution"], "execution")
    exact_keys(
        execution,
        {
            "architecture", "expected_output", "artifact_sha256", "base_absent",
            "undeployed_absent", "cold_boot_absent",
        },
        "execution",
    )
    if execution["architecture"] != identity["architecture"]:
        raise SdkEvidenceError("execution architecture does not match the lab")
    if execution["expected_output"] != "qemu-edu-sdk-sample workspace":
        raise SdkEvidenceError("execution output is not recognized")
    sha256_value(execution["artifact_sha256"], "execution.artifact_sha256")
    for key in ("base_absent", "undeployed_absent", "cold_boot_absent"):
        if execution[key] is not True:
            raise SdkEvidenceError(f"execution.{key} must be true")

    checks = evidence["checks"]
    if not isinstance(checks, list) or len(checks) != len(CHECK_IDS):
        raise SdkEvidenceError("checks must contain the complete ordered lifecycle")
    for expected_id, check in zip(CHECK_IDS, checks, strict=True):
        check = object_value(check, "check")
        exact_keys(check, {"id", "status"}, "check")
        if check != {"id": expected_id, "status": "passed"}:
            raise SdkEvidenceError("checks contain a failed, unknown, or out-of-order entry")
    if type(evidence["task_exit_code"]) is not int or evidence["task_exit_code"] != 0:
        raise SdkEvidenceError("task_exit_code must be zero")
    if evidence["result"] != "passed":
        raise SdkEvidenceError("result must be passed")
    if require_pass and (project["dirty"] or evidence["result"] != "passed"):
        raise SdkEvidenceError("evidence does not describe a clean passing run")

    if current_repo is not None:
        repo = current_repo.resolve()
        manifest, selected, index_digest, manifest_digest, _ = selected_contract(
            repo, lab["id"]
        )
        lock, lock_digest, oe_core_commit = source_authority(repo)
        release = object_value(lock.get("release"), "source-lock release")
        current_revision, dirty = project_state(repo)
        if dirty or current_revision != revision:
            raise SdkEvidenceError("evidence project state is not current and clean")
        if version != (repo / "VERSION").read_text(encoding="utf-8").strip():
            raise SdkEvidenceError("evidence project version is not current")
        expected_inputs = {
            "source_lock_sha256": lock_digest,
            "openembedded_core_commit": oe_core_commit,
            "lab_index_sha256": index_digest,
            "lab_manifest_sha256": manifest_digest,
            "yocto_version": release["version"],
            "yocto_series": release["series"],
        }
        if inputs != expected_inputs:
            raise SdkEvidenceError("evidence inputs are not current")
        development = manifest["development"]
        expected_lab = {
            "id": selected,
            "machine": manifest["build"]["machine"],
            "image": manifest["build"]["targets"][0],
            "development_build_dir": development["build_dir"],
            "recipe": development["recipe"],
            "source_dir": development["source_dir"],
            "guest_binary": development["guest_binary"],
        }
        if lab != expected_lab:
            raise SdkEvidenceError("evidence lab contract is not current")
        build_root = repo / development["build_dir"]
        if build_root.is_symlink() or not build_root.is_dir():
            raise SdkEvidenceError("development build root is not current")
        if build_root.resolve(strict=True) != build_root:
            raise SdkEvidenceError("development build root escapes its selected path")
        source_path = (
            build_root
            / development["source_dir"]
            / "qemu-edu-sdk-sample.c"
        )
        if source_path.is_symlink() or not source_path.is_file():
            raise SdkEvidenceError("retained learner source is not current")
        if source_path.resolve(strict=True) != source_path:
            raise SdkEvidenceError("retained learner source escapes its selected path")
        with source_path.open("rb") as handle:
            source_bytes = handle.read(MAX_SOURCE_BYTES + 1)
        if len(source_bytes) > MAX_SOURCE_BYTES:
            raise SdkEvidenceError("retained learner source exceeds its byte bound")
        if hashlib.sha256(source_bytes).hexdigest() != source["sha256"]:
            raise SdkEvidenceError("retained learner source digest is not current")


def read_evidence(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_EVIDENCE_BYTES + 1)
    except OSError as exc:
        raise SdkEvidenceError("cannot read evidence") from exc
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise SdkEvidenceError("evidence exceeds its byte bound")
    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_constant,
            parse_int=parse_bounded_integer,
        )
    except SdkEvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise SdkEvidenceError("invalid evidence JSON") from exc
    if not isinstance(data, dict):
        raise SdkEvidenceError("evidence root must be an object")
    validate_json_shape(data)
    return data


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    validate_evidence(evidence, require_pass=True)
    verify_output(path, create_parent=True)
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if len(payload.encode("utf-8")) > MAX_EVIDENCE_BYTES:
        raise SdkEvidenceError("generated evidence exceeds its byte bound")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=".sdk-evidence-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        verify_output(path)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--lab", help="lab id; defaults to the catalog default")
    parser.add_argument("--build-dir", help="selected development build directory")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("path", help="print the selected evidence path")
    subparsers.add_parser("clear", help="remove only the selected evidence file")
    validate = subparsers.add_parser("validate", help="validate an SDK evidence document")
    validate.add_argument("evidence")
    validate.add_argument("--require-pass", action="store_true")
    validate.add_argument("--require-revision")
    validate.add_argument("--require-current-inputs", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    try:
        if args.command == "validate":
            validate_evidence(
                read_evidence(Path(args.evidence)),
                require_pass=args.require_pass,
                expected_revision=args.require_revision,
                current_repo=repo if args.require_current_inputs else None,
            )
            print(f"sdk-evidence: PASS: {args.evidence}")
            return 0
        manifest, _, _, _, _ = selected_contract(repo, args.lab)
        build_dir = None
        if args.build_dir is not None:
            if not args.build_dir:
                raise SdkEvidenceError("build directory must be non-empty")
            build_dir = Path(args.build_dir)
            if not build_dir.is_absolute():
                build_dir = repo / build_dir
        output = evidence_path(repo, manifest, build_dir)
        if args.command == "path":
            print(output)
        else:
            clear_evidence(output)
            print(f"sdk-evidence: cleared: {output}")
        return 0
    except LabError as exc:
        print(f"sdk-evidence: FAIL: {exc}", file=sys.stderr)
        return 2
    except (SdkEvidenceError, LockError, OSError) as exc:
        print(f"sdk-evidence: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
