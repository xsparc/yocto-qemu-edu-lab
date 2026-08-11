#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Validate and query the closed multi-lab build declarations."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from source_lock import LockError, locked_path, read_lock  # noqa: E402


INDEX_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
DEFAULT_INDEX = "config/labs/index.json"
DEFAULT_SOURCE_LOCK = "config/sources.lock.json"
MAX_JSON_BYTES = 64 * 1024
INDEX_KEYS = {"schema_version", "default_lab", "labs"}
INDEX_ENTRY_KEYS = {"id", "manifest", "sha256"}
MANIFEST_KEYS = {
    "schema_version",
    "id",
    "description",
    "build",
    "emulator",
    "runtime",
}
BUILD_KEYS = {"build_dir", "distro", "machine", "driver_target", "targets", "layers"}
EMULATOR_KEYS = {"preflight_profile", "system_binary"}
RUNTIME_KEYS = {
    "suite",
    "evidence_profile",
    "evidence_filename",
    "guest_contract_version",
    "evidence_schema_version",
}
LAB_ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")
BUILD_DIRECTORY = re.compile(r"build(?:-[a-z0-9][a-z0-9-]*)?\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
PROFILE_RULES = {
    "qemu-edu-pci-v1": {
        "system_binary": "qemu-system-x86_64",
        "driver_target": "qemu-edu-driver",
        "suite": "qemu_edu",
        "evidence_profile": "pci-v3",
        "evidence_filename": "qemu-edu-runtime-v3.json",
        "guest_contract_version": 3,
        "evidence_schema_version": 3,
    },
    "qemu-edu-platform-v1": {
        "system_binary": "qemu-system-aarch64",
        "driver_target": "qemu-edu-platform-driver",
        "suite": "qemu_edu_platform",
        "evidence_profile": "platform-v1",
        "evidence_filename": "qemu-edu-platform-runtime-v1.json",
        "guest_contract_version": 1,
        "evidence_schema_version": 1,
    },
}


class LabError(ValueError):
    """A lab index or manifest failed a closed validation rule."""


def exact_keys(value: dict[str, Any], expected: set[str], where: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing:
        raise LabError(f"{where} is missing fields: {', '.join(missing)}")
    if unknown:
        raise LabError(f"{where} has unknown fields: {', '.join(unknown)}")


def object_value(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LabError(f"{where} must be an object")
    return value


def string_value(value: Any, where: str, *, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value:
        raise LabError(f"{where} must be a non-empty string")
    if len(value) > max_length:
        raise LabError(f"{where} exceeds {max_length} characters")
    return value


def integer_value(value: Any, where: str) -> int:
    if type(value) is not int or value < 1:
        raise LabError(f"{where} must be a positive integer")
    return value


def string_list(value: Any, where: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise LabError(f"{where} must be a non-empty array")
    result = [string_value(item, f"{where}[{index}]") for index, item in enumerate(value)]
    if len(result) != len(set(result)):
        raise LabError(f"{where} contains duplicates")
    return result


def relative_path(value: Any, where: str, *, under: str | None = None) -> str:
    text = string_value(value, where)
    if "\\" in text or any(character.isspace() for character in text):
        raise LabError(f"{where} must be a normalized path without whitespace")
    path = PurePosixPath(text)
    if path.is_absolute() or text != path.as_posix() or any(
        part in {"", ".", ".."} for part in path.parts
    ):
        raise LabError(f"{where} must be a normalized repository-relative path")
    if any(not TOKEN.fullmatch(part) for part in path.parts):
        raise LabError(f"{where} contains unsupported path characters")
    if under is not None and (not path.parts or path.parts[0] != under):
        raise LabError(f"{where} must be under {under}/")
    return text


def duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LabError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path, where: str) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise LabError(f"cannot read {where}: {exc}") from exc
    if len(raw) > MAX_JSON_BYTES:
        raise LabError(f"{where} exceeds {MAX_JSON_BYTES} bytes")
    try:
        data = json.loads(raw, object_pairs_hook=duplicate_guard)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LabError(f"invalid JSON in {where}: {exc}") from exc
    if not isinstance(data, dict):
        raise LabError(f"{where} root must be an object")
    return data, hashlib.sha256(raw).hexdigest()


def validate_manifest(data: dict[str, Any], expected_id: str) -> None:
    exact_keys(data, MANIFEST_KEYS, f"lab {expected_id}")
    if type(data["schema_version"]) is not int or data["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise LabError(
            f"lab {expected_id} has unsupported schema_version "
            f"{data['schema_version']!r}"
        )
    lab_id = string_value(data["id"], f"lab {expected_id}.id")
    if lab_id != expected_id or not LAB_ID.fullmatch(lab_id):
        raise LabError(f"lab id {lab_id!r} does not match index id {expected_id!r}")
    description = string_value(data["description"], f"lab {expected_id}.description")
    if any(
        unicodedata.category(character) in {"Cc", "Cf", "Zl", "Zp"}
        for character in description
    ):
        raise LabError(
            f"lab {expected_id}.description contains unsafe rendering or control characters"
        )

    build = object_value(data["build"], f"lab {expected_id}.build")
    exact_keys(build, BUILD_KEYS, f"lab {expected_id}.build")
    build_dir = relative_path(build["build_dir"], f"lab {expected_id}.build.build_dir")
    if not BUILD_DIRECTORY.fullmatch(build_dir):
        raise LabError(
            f"lab {expected_id}.build.build_dir must be a top-level "
            "build or build-<lab> generated-output directory"
        )
    for field in ("distro", "machine", "driver_target"):
        value = string_value(build[field], f"lab {expected_id}.build.{field}")
        if not TOKEN.fullmatch(value):
            raise LabError(f"lab {expected_id}.build.{field} contains unsupported characters")
    targets = string_list(build["targets"], f"lab {expected_id}.build.targets")
    if len(targets) != 1:
        raise LabError(f"lab {expected_id}.build.targets must contain exactly one image")
    if not TOKEN.fullmatch(targets[0]):
        raise LabError(f"lab {expected_id}.build.targets[0] contains unsupported characters")
    for index, layer in enumerate(string_list(build["layers"], f"lab {expected_id}.build.layers")):
        relative_path(layer, f"lab {expected_id}.build.layers[{index}]")

    emulator = object_value(data["emulator"], f"lab {expected_id}.emulator")
    exact_keys(emulator, EMULATOR_KEYS, f"lab {expected_id}.emulator")
    profile = string_value(
        emulator["preflight_profile"],
        f"lab {expected_id}.emulator.preflight_profile",
    )
    rule = PROFILE_RULES.get(profile)
    if rule is None:
        raise LabError(f"lab {expected_id} uses unknown preflight profile {profile!r}")

    runtime = object_value(data["runtime"], f"lab {expected_id}.runtime")
    exact_keys(runtime, RUNTIME_KEYS, f"lab {expected_id}.runtime")
    actual = {
        "driver_target": build["driver_target"],
        "system_binary": string_value(
            emulator["system_binary"], f"lab {expected_id}.emulator.system_binary"
        ),
        "suite": string_value(runtime["suite"], f"lab {expected_id}.runtime.suite"),
        "evidence_profile": string_value(
            runtime["evidence_profile"], f"lab {expected_id}.runtime.evidence_profile"
        ),
        "evidence_filename": relative_path(
            runtime["evidence_filename"],
            f"lab {expected_id}.runtime.evidence_filename",
        ),
        "guest_contract_version": integer_value(
            runtime["guest_contract_version"],
            f"lab {expected_id}.runtime.guest_contract_version",
        ),
        "evidence_schema_version": integer_value(
            runtime["evidence_schema_version"],
            f"lab {expected_id}.runtime.evidence_schema_version",
        ),
    }
    if PurePosixPath(actual["evidence_filename"]).parent != PurePosixPath("."):
        raise LabError(f"lab {expected_id}.runtime.evidence_filename must be a basename")
    if not actual["evidence_filename"].endswith(".json"):
        raise LabError(f"lab {expected_id}.runtime.evidence_filename must end in .json")
    for field, expected in rule.items():
        if actual[field] != expected:
            raise LabError(
                f"lab {expected_id} {field} is {actual[field]!r}, expected {expected!r} "
                f"for {profile}"
            )


def default_build_parity(root: Path, default_manifest: dict[str, Any]) -> None:
    try:
        source_data, _ = read_lock(locked_path(root, DEFAULT_SOURCE_LOCK))
    except LockError as exc:
        raise LabError(f"source lock is invalid: {exc}") from exc
    legacy = source_data["build"]
    selected = default_manifest["build"]
    for field in ("build_dir", "distro", "machine", "targets", "layers"):
        if legacy[field] != selected[field]:
            raise LabError(
                f"default lab build.{field} differs from the source-lock compatibility value"
            )


def read_catalog(
    root: Path, index_relative: str = DEFAULT_INDEX
) -> tuple[dict[str, Any], str, dict[str, dict[str, Any]], dict[str, str]]:
    root = root.resolve()
    index_path = locked_path(root, relative_path(index_relative, "index path", under="config"))
    index, index_digest = read_json(index_path, index_relative)
    exact_keys(index, INDEX_KEYS, "lab index")
    if type(index["schema_version"]) is not int or index["schema_version"] != INDEX_SCHEMA_VERSION:
        raise LabError(f"unsupported lab-index schema_version {index['schema_version']!r}")
    default_lab = string_value(index["default_lab"], "lab index.default_lab")
    if not LAB_ID.fullmatch(default_lab):
        raise LabError("lab index.default_lab contains unsupported characters")
    entries = index["labs"]
    if not isinstance(entries, list) or not entries:
        raise LabError("lab index.labs must be a non-empty array")

    manifests: dict[str, dict[str, Any]] = {}
    digests: dict[str, str] = {}
    paths: set[str] = set()
    build_dirs: set[str] = set()
    machines: set[str] = set()
    for entry_index, raw_entry in enumerate(entries):
        where = f"lab index.labs[{entry_index}]"
        entry = object_value(raw_entry, where)
        exact_keys(entry, INDEX_ENTRY_KEYS, where)
        lab_id = string_value(entry["id"], f"{where}.id")
        if not LAB_ID.fullmatch(lab_id):
            raise LabError(f"{where}.id contains unsupported characters")
        if lab_id in manifests:
            raise LabError(f"duplicate lab id: {lab_id}")
        manifest_relative = relative_path(
            entry["manifest"], f"{where}.manifest", under="config"
        )
        if not manifest_relative.startswith("config/labs/"):
            raise LabError(f"{where}.manifest must be under config/labs/")
        if manifest_relative in paths:
            raise LabError(f"duplicate lab manifest path: {manifest_relative}")
        paths.add(manifest_relative)
        expected_digest = string_value(entry["sha256"], f"{where}.sha256")
        if not SHA256.fullmatch(expected_digest):
            raise LabError(f"{where}.sha256 must be a lowercase SHA-256")
        manifest, actual_digest = read_json(
            locked_path(root, manifest_relative), manifest_relative
        )
        if actual_digest != expected_digest:
            raise LabError(
                f"{manifest_relative} SHA-256 is {actual_digest}, expected {expected_digest}"
            )
        validate_manifest(manifest, lab_id)
        build_dir = manifest["build"]["build_dir"]
        machine = manifest["build"]["machine"]
        if build_dir in build_dirs:
            raise LabError(f"duplicate lab build directory: {build_dir}")
        if machine in machines:
            raise LabError(f"duplicate lab machine: {machine}")
        build_dirs.add(build_dir)
        machines.add(machine)
        manifests[lab_id] = manifest
        digests[lab_id] = actual_digest

    if default_lab not in manifests:
        raise LabError(f"default lab {default_lab!r} is not declared")
    default_build_parity(root, manifests[default_lab])
    return index, index_digest, manifests, digests


def select_lab(
    root: Path, lab_id: str | None, index_relative: str = DEFAULT_INDEX
) -> tuple[str, dict[str, Any], str, str]:
    index, index_digest, manifests, digests = read_catalog(root, index_relative)
    selected = lab_id or index["default_lab"]
    if selected not in manifests:
        raise LabError(f"unknown lab: {selected}")
    return selected, manifests[selected], index_digest, digests[selected]


def get_field(data: dict[str, Any], dotted: str) -> Any:
    value: Any = data
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise LabError(f"unknown lab field: {dotted}")
        value = value[part]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--index", default=DEFAULT_INDEX, help="lab index under repository")
    parser.add_argument("--lab", help="lab id; defaults to the index default")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate the index and every manifest")
    subparsers.add_parser("list", help="list declared labs")
    get_parser = subparsers.add_parser("get", help="print a selected manifest field")
    get_parser.add_argument("field", help="dot-separated manifest field")
    get_parser.add_argument("--lines", action="store_true", help="print list items one per line")
    subparsers.add_parser("digest", help="print selected index and manifest digests")
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    try:
        index, index_digest, manifests, digests = read_catalog(root, args.index)
        if args.command == "validate":
            result = {
                "schema_version": INDEX_SCHEMA_VERSION,
                "index_sha256": index_digest,
                "default_lab": index["default_lab"],
                "labs": sorted(manifests),
                "ok": True,
            }
            if args.format == "json":
                print(json.dumps(result, sort_keys=True, separators=(",", ":")))
            else:
                print(f"lab-config: PASS ({index_digest})")
            return 0
        if args.command == "list":
            if args.format == "json":
                print(
                    json.dumps(
                        {
                            "default_lab": index["default_lab"],
                            "labs": [
                                {
                                    "id": lab_id,
                                    "description": manifests[lab_id]["description"],
                                    "manifest_sha256": digests[lab_id],
                                }
                                for lab_id in sorted(manifests)
                            ],
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            else:
                for lab_id in sorted(manifests):
                    marker = "*" if lab_id == index["default_lab"] else " "
                    print(f"{marker} {lab_id}: {manifests[lab_id]['description']}")
            return 0

        selected, manifest, _, manifest_digest = select_lab(root, args.lab, args.index)
        if args.command == "digest":
            if args.format == "json":
                print(
                    json.dumps(
                        {
                            "lab": selected,
                            "index_sha256": index_digest,
                            "manifest_sha256": manifest_digest,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
            else:
                print(f"index_sha256={index_digest}")
                print(f"manifest_sha256={manifest_digest}")
            return 0

        value = get_field(manifest, args.field)
        if args.lines:
            if not isinstance(value, list):
                raise LabError(f"{args.field} is not an array")
            for item in value:
                if not isinstance(item, str):
                    raise LabError(f"{args.field} contains a non-string value")
                print(item)
            return 0
        if not isinstance(value, (str, int)) or isinstance(value, bool):
            raise LabError(f"{args.field} is not a scalar field")
        print(value)
        return 0
    except (LabError, LockError, OSError) as exc:
        if args.format == "json":
            print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        else:
            print(f"lab-config: FAIL: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
