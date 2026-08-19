#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Collect and validate bounded SPDX 3 image-composition evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lab_config import LabError, select_lab  # noqa: E402
from source_lock import LockError, read_lock, status_result  # noqa: E402


SCHEMA_VERSION = 1
KIND = "qemu-edu-spdx-image-evidence"
PROJECT_NAME = "yocto-qemu-edu-lab"
EVIDENCE_PROFILE = "spdx3-image-v1"
SPDX_VERSION = "3.0.1"
PROFILES = ("build", "core", "security", "simpleLicensing", "software")
MAX_SBOM_BYTES = 128 * 1024 * 1024
MAX_EVIDENCE_BYTES = 1024 * 1024
MAX_ARTIFACTS = 128
MAX_INSTALLED_PACKAGES = 8192
MAX_STRING_LENGTH = 4096
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024 * 1024
MAX_TOTAL_ARTIFACT_BYTES = 16 * 1024 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_ITEMS = 20000
MAX_RAW_JSON_DEPTH = 64
MAX_RAW_JSON_ITEMS = 250000
MAX_RAW_STRING_LENGTH = 65536
MAX_SPDX_OBJECTS = 50000
MAX_JSON_INTEGER_DIGITS = 64
ROOTFS_BUILD_TYPE = "http://openembedded.org/bitbake/do_create_rootfs_spdx/rootfs"
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
EXPECTED_SETTINGS = {
    "SPDX_IMAGE_SUPPLIER_name": "",
    "SPDX_INCLUDE_BITBAKE_PARENT_BUILD": "0",
    "SPDX_INCLUDE_BUILD_VARIABLES": "0",
    "SPDX_INCLUDE_COMPILED_SOURCES": "0",
    "SPDX_INCLUDE_KERNEL_CONFIG": "0",
    "SPDX_INCLUDE_PACKAGECONFIG": "0",
    "SPDX_INCLUDE_SOURCES": "0",
    "SPDX_INCLUDE_TIMESTAMPS": "0",
    "SPDX_INCLUDE_VEX": "current",
    "SPDX_PACKAGE_SUPPLIER_name": "",
    "SPDX_PRETTY": "0",
    "SPDX_PROFILES": "core build software simpleLicensing security",
    "SPDX_VERSION": SPDX_VERSION,
}
CHECK_IDS = (
    "source-lock",
    "lab-contract",
    "generator-settings",
    "spdx-model",
    "spdx-graph",
    "package-set",
    "declared-licenses",
    "artifact-hashes",
)
LAB_IDENTITIES = {
    "pci-x86-64": {
        "machine": "qemu-edu-x86-64",
        "image": "qemu-edu-image",
        "packages": {
            "kernel-module-qemu-edu-6.18.24-yocto-standard": "GPL-2.0-only",
            "qemu-edu-driver": "GPL-2.0-only",
            "qemu-edu-tools": "MIT",
        },
    },
    "platform-arm64": {
        "machine": "qemu-edu-platform-arm64",
        "image": "qemu-edu-image",
        "packages": {
            "kernel-module-qemu-edu-platform-6.18.24-yocto-standard": (
                "GPL-2.0-only"
            ),
            "qemu-edu-platform-driver": "GPL-2.0-only",
            "qemu-edu-platform-tools": "MIT",
        },
    },
}


class SbomEvidenceError(ValueError):
    """An SPDX input or evidence document failed a closed validation rule."""


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
        raise SbomEvidenceError(f"{where} has " + "; ".join(details))


def reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SbomEvidenceError("duplicate JSON key")
        result[key] = value
    return result


def bounded_json_string(
    value: Any,
    where: str,
    *,
    max_length: int,
    allow_json_whitespace_controls: bool,
) -> str:
    if not isinstance(value, str):
        raise SbomEvidenceError(f"{where} must be a string")
    if len(value) > max_length:
        raise SbomEvidenceError(f"{where} exceeds {max_length} characters")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise SbomEvidenceError(f"{where} contains an invalid Unicode surrogate")
    permitted_controls = {0x09, 0x0A, 0x0D} if allow_json_whitespace_controls else set()
    if any(
        (ord(character) < 0x20 and ord(character) not in permitted_controls)
        or ord(character) == 0x7F
        for character in value
    ):
        raise SbomEvidenceError(f"{where} contains a control character")
    return value


def validate_json_shape(
    value: Any,
    *,
    depth: int = 0,
    max_depth: int = MAX_JSON_DEPTH,
    max_items: int = MAX_JSON_ITEMS,
    max_string_length: int = MAX_STRING_LENGTH,
    allow_json_whitespace_controls: bool = False,
    where: str = "evidence JSON",
) -> int:
    if depth > max_depth:
        raise SbomEvidenceError(f"{where} exceeds depth {max_depth}")
    if value is None or type(value) in (bool, int):
        return 1
    if isinstance(value, str):
        bounded_json_string(
            value,
            f"{where} string",
            max_length=max_string_length,
            allow_json_whitespace_controls=allow_json_whitespace_controls,
        )
        return 1
    if isinstance(value, list):
        count = 1
        for item in value:
            count += validate_json_shape(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_string_length=max_string_length,
                allow_json_whitespace_controls=allow_json_whitespace_controls,
                where=where,
            )
            if count > max_items:
                raise SbomEvidenceError(f"{where} exceeds {max_items} values")
        return count
    if isinstance(value, dict):
        count = 1
        for key, item in value.items():
            string_value(key, f"{where} key", max_length=max_string_length)
            count += validate_json_shape(
                item,
                depth=depth + 1,
                max_depth=max_depth,
                max_items=max_items,
                max_string_length=max_string_length,
                allow_json_whitespace_controls=allow_json_whitespace_controls,
                where=where,
            )
            if count > max_items:
                raise SbomEvidenceError(f"{where} exceeds {max_items} values")
        return count
    raise SbomEvidenceError("evidence JSON contains an unsupported value type")


def object_value(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SbomEvidenceError(f"{where} must be an object")
    return value


def string_value(
    value: Any,
    where: str,
    *,
    allow_empty: bool = False,
    max_length: int = MAX_STRING_LENGTH,
) -> str:
    if not isinstance(value, str) or (not value and not allow_empty):
        qualifier = "a string" if allow_empty else "a non-empty string"
        raise SbomEvidenceError(f"{where} must be {qualifier}")
    if len(value) > max_length:
        raise SbomEvidenceError(f"{where} exceeds {max_length} characters")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise SbomEvidenceError(f"{where} contains an invalid Unicode surrogate")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise SbomEvidenceError(f"{where} contains a control character")
    return value


def integer_value(
    value: Any, where: str, *, minimum: int = 0, maximum: int | None = None
) -> int:
    if type(value) is not int or value < minimum:
        raise SbomEvidenceError(f"{where} must be an integer of at least {minimum}")
    if maximum is not None and value > maximum:
        raise SbomEvidenceError(f"{where} must not exceed {maximum}")
    return value


def boolean_value(value: Any, where: str) -> bool:
    if type(value) is not bool:
        raise SbomEvidenceError(f"{where} must be boolean")
    return value


def safe_token(value: Any, where: str) -> str:
    text = string_value(value, where)
    if not TOKEN.fullmatch(text):
        raise SbomEvidenceError(f"{where} contains unsupported characters")
    return text


def sha1_value(value: Any, where: str) -> str:
    text = string_value(value, where)
    if not SHA1.fullmatch(text):
        raise SbomEvidenceError(f"{where} must be a lowercase SHA-1")
    return text


def sha256_value(value: Any, where: str) -> str:
    text = string_value(value, where)
    if not SHA256.fullmatch(text):
        raise SbomEvidenceError(f"{where} must be a lowercase SHA-256")
    return text


def parse_settings(values: list[str]) -> dict[str, str]:
    settings: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise SbomEvidenceError("--setting must be NAME=VALUE")
        name, value = item.split("=", 1)
        if name in settings:
            raise SbomEvidenceError(f"duplicate setting: {name}")
        settings[name] = value
    if set(settings) != set(EXPECTED_SETTINGS):
        missing = sorted(set(EXPECTED_SETTINGS) - set(settings))
        unknown = sorted(set(settings) - set(EXPECTED_SETTINGS))
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise SbomEvidenceError("SPDX settings are incomplete: " + "; ".join(details))
    for name, expected in EXPECTED_SETTINGS.items():
        actual = settings[name]
        if name == "SPDX_PROFILES":
            if actual.split() != expected.split():
                raise SbomEvidenceError(
                    f"{name} is {actual!r}, expected exact ordered value {expected!r}"
                )
        elif actual != expected:
            raise SbomEvidenceError(f"{name} is {actual!r}, expected {expected!r}")
    return settings


def source_authority(repo: Path) -> tuple[dict[str, Any], str, dict[str, Any]]:
    lock_path = repo / "config/sources.lock.json"
    data, digest = read_lock(lock_path)
    status = status_result(repo, data, digest)
    if not status["ok"]:
        failures = [
            f"{source['id']}: {', '.join(source['errors'])}"
            for source in status["sources"]
            if source["state"] != "ready"
        ]
        raise SbomEvidenceError("locked sources are not ready: " + "; ".join(failures))
    matches = [source for source in data["sources"] if source["id"] == "openembedded-core"]
    if len(matches) != 1:
        raise SbomEvidenceError("source lock must contain exactly one openembedded-core")
    return data, digest, matches[0]


def project_state(repo: Path) -> tuple[str, bool]:
    revision = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    sha1_value(revision, "project revision")
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=normal"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return revision, dirty


def selected_contract(
    repo: Path, lab_id: str | None
) -> tuple[dict[str, Any], str, str, str, dict[str, str], list[str]]:
    selected, manifest, index_digest, manifest_digest = select_lab(repo, lab_id)
    supply_chain = manifest["supply_chain"]
    if supply_chain["evidence_profile"] != EVIDENCE_PROFILE:
        raise SbomEvidenceError(f"lab {selected} does not use {EVIDENCE_PROFILE}")
    required = {
        package["name"]: package["declared_license"]
        for package in supply_chain["required_packages"]
    }
    forbidden = list(supply_chain["forbidden_packages"])
    identity = LAB_IDENTITIES.get(selected)
    if identity is None:
        raise SbomEvidenceError(f"evidence schema 1 does not recognize lab {selected}")
    if manifest["build"]["machine"] != identity["machine"]:
        raise SbomEvidenceError(f"lab {selected} machine is not recognized")
    if manifest["build"]["targets"] != [identity["image"]]:
        raise SbomEvidenceError(f"lab {selected} image is not recognized")
    if required != identity["packages"]:
        raise SbomEvidenceError(f"lab {selected} package rules are not recognized")
    return manifest, selected, index_digest, manifest_digest, required, forbidden


def evidence_path(
    repo: Path, manifest: dict[str, Any], build_dir: Path | None = None
) -> Path:
    build_root = (
        build_dir.resolve()
        if build_dir is not None
        else (repo / manifest["build"]["build_dir"]).resolve()
    )
    evidence_dir = build_root / "evidence"
    if evidence_dir.exists():
        if evidence_dir.is_symlink() or not evidence_dir.is_dir():
            raise SbomEvidenceError("evidence directory is not a regular directory")
        if evidence_dir.resolve(strict=True) != evidence_dir:
            raise SbomEvidenceError("evidence directory escapes the selected build directory")
    path = evidence_dir / manifest["supply_chain"]["evidence_filename"]
    if path.is_symlink():
        raise SbomEvidenceError("evidence output must not be a symbolic link")
    if path.exists() and not path.is_file():
        raise SbomEvidenceError("evidence output is not a regular file")
    return path


def verify_evidence_output(path: Path, *, create_parent: bool = False) -> None:
    parent = path.parent
    if create_parent:
        parent.mkdir(parents=True, exist_ok=True)
    if parent.is_symlink() or not parent.is_dir():
        raise SbomEvidenceError("evidence directory is not a regular directory")
    if parent.resolve(strict=True) != parent:
        raise SbomEvidenceError("evidence directory escapes the selected build directory")
    if path.is_symlink():
        raise SbomEvidenceError("evidence output must not be a symbolic link")
    if path.exists() and not path.is_file():
        raise SbomEvidenceError("evidence output is not a regular file")


def clear_evidence(path: Path) -> None:
    verify_evidence_output(path, create_parent=True)
    path.unlink(missing_ok=True)


def active_build_dir(
    repo: Path, manifest: dict[str, Any], requested: str | None
) -> Path:
    if requested is None:
        return (repo / manifest["build"]["build_dir"]).resolve()
    text = string_value(requested, "build directory")
    path = Path(text)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def load_spdx_model(repo: Path, openembedded_core: dict[str, Any]) -> Any:
    source_root = (repo / openembedded_core["path"]).resolve()
    model_root = source_root / "meta/lib"
    expected = model_root / "oe/spdx30/__init__.py"
    if not expected.is_file():
        raise SbomEvidenceError("locked OE-Core SPDX model is missing")
    model_root_text = str(model_root)
    if model_root_text not in sys.path:
        sys.path.insert(0, model_root_text)
    try:
        spdx = importlib.import_module("oe.spdx30")
    except Exception as exc:  # the generated model may report several safe errors
        raise SbomEvidenceError(
            f"locked OE-Core SPDX model could not be imported: {type(exc).__name__}"
        ) from exc
    module_path = Path(spdx.__file__).resolve()
    if module_path != expected.resolve():
        raise SbomEvidenceError("imported SPDX model is outside the locked OE-Core source")
    return spdx


def read_sbom(path: Path) -> tuple[bytes, str]:
    try:
        size = path.stat().st_size
        if size < 1 or size > MAX_SBOM_BYTES:
            raise SbomEvidenceError(
                f"SPDX document size must be from 1 through {MAX_SBOM_BYTES} bytes"
            )
        with path.open("rb") as handle:
            raw = handle.read(MAX_SBOM_BYTES + 1)
    except OSError as exc:
        raise SbomEvidenceError(f"cannot read SPDX document: {exc}") from exc
    if len(raw) != size or len(raw) > MAX_SBOM_BYTES:
        raise SbomEvidenceError("SPDX document changed or exceeded its read bound")
    return raw, hashlib.sha256(raw).hexdigest()


def reject_json_constant(value: str) -> None:
    raise SbomEvidenceError(f"JSON contains unsupported constant {value}")


def parse_bounded_integer(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise SbomEvidenceError(
            f"JSON integer exceeds {MAX_JSON_INTEGER_DIGITS} digits"
        )
    return int(value)


def deserialize_spdx(spdx: Any, raw: bytes) -> Any:
    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_json_constant,
            parse_int=parse_bounded_integer,
        )
    except SbomEvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SbomEvidenceError(f"invalid SPDX JSON: {exc}") from exc
    validate_json_shape(
        data,
        max_depth=MAX_RAW_JSON_DEPTH,
        max_items=MAX_RAW_JSON_ITEMS,
        max_string_length=MAX_RAW_STRING_LENGTH,
        allow_json_whitespace_controls=True,
        where="SPDX JSON",
    )
    objset = spdx.SHACLObjectSet()
    try:
        spdx.JSONLDDeserializer().deserialize_data(data, objset)
    except Exception as exc:
        raise SbomEvidenceError(
            f"SPDX 3 model validation failed: {type(exc).__name__}"
        ) from exc
    objects = getattr(objset, "objects", None)
    if objects is None or not hasattr(objects, "__len__"):
        raise SbomEvidenceError("SPDX model did not expose a bounded object set")
    if len(objects) > MAX_SPDX_OBJECTS:
        raise SbomEvidenceError(
            f"SPDX graph exceeds {MAX_SPDX_OBJECTS} model objects"
        )
    return objset


def only_sha256(spdx: Any, element: Any, where: str) -> str:
    values = [
        verified.hashValue
        for verified in element.verifiedUsing
        if isinstance(verified, spdx.Hash)
        and verified.algorithm == spdx.HashAlgorithm.sha256
    ]
    if len(values) != 1:
        raise SbomEvidenceError(f"{where} must declare exactly one lowercase SHA-256")
    return sha256_value(values[0], f"{where} SHA-256")


def hash_file(path: Path) -> tuple[str, int]:
    size = path.stat().st_size
    if size < 1 or size > MAX_ARTIFACT_BYTES:
        raise SbomEvidenceError(
            f"artifact size must be from 1 through {MAX_ARTIFACT_BYTES} bytes"
        )
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    if path.stat().st_size != size:
        raise SbomEvidenceError("artifact changed while it was hashed")
    return digest.hexdigest(), size


def analyze_graph(
    *,
    spdx: Any,
    objset: Any,
    deploy_dir: Path,
    image: str,
    required_packages: dict[str, str],
    forbidden_packages: list[str],
) -> dict[str, Any]:
    documents = list(objset.foreach_type(spdx.SpdxDocument))
    sboms = list(objset.foreach_type(spdx.software_Sbom))
    if len(documents) != 1 or len(sboms) != 1:
        raise SbomEvidenceError("SPDX graph must contain one document and one SBOM")
    document = documents[0]
    sbom = sboms[0]
    imported = {item.externalSpdxId for item in document.import_}
    unresolved = sorted(set(objset.missing_ids) - imported)
    if unresolved:
        raise SbomEvidenceError("SPDX graph contains unresolved internal identifiers")
    if list(document.rootElement) != [sbom]:
        raise SbomEvidenceError("SPDX document root must contain only the image SBOM")
    if document.creationInfo.specVersion != SPDX_VERSION:
        raise SbomEvidenceError("SPDX document version is not 3.0.1")
    expected_profiles = {
        getattr(spdx.ProfileIdentifierType, profile) for profile in PROFILES
    }
    if (
        len(document.profileConformance) != len(expected_profiles)
        or set(document.profileConformance) != expected_profiles
    ):
        raise SbomEvidenceError("SPDX document profiles do not match the locked profile")
    if list(sbom.software_sbomType) != [spdx.software_SbomType.build]:
        raise SbomEvidenceError("SPDX image SBOM must use the build SBOM type")

    root_packages = [
        element
        for element in sbom.rootElement
        if isinstance(element, spdx.software_Package)
    ]
    root_files = [
        element
        for element in sbom.rootElement
        if isinstance(element, spdx.software_File)
    ]
    if len(root_packages) != 1 or root_packages[0].name != image:
        raise SbomEvidenceError("SPDX SBOM must contain the selected image rootfs package")
    if (
        root_packages[0].software_primaryPurpose
        != spdx.software_SoftwarePurpose.archive
    ):
        raise SbomEvidenceError("SPDX rootfs package must use the archive purpose")
    if len(root_files) < 1 or len(root_files) > MAX_ARTIFACTS:
        raise SbomEvidenceError(
            f"SPDX SBOM must contain from 1 through {MAX_ARTIFACTS} image artifacts"
        )
    if len(sbom.rootElement) != len(root_packages) + len(root_files):
        raise SbomEvidenceError("SPDX SBOM contains an unsupported root element type")

    expected_build_name = f"{image}:do_create_rootfs_spdx:rootfs"
    rootfs_builds = [
        build
        for build in objset.foreach_type(spdx.build_Build)
        if build.name == expected_build_name
    ]
    if len(rootfs_builds) != 1:
        raise SbomEvidenceError("SPDX graph must contain one selected-image rootfs build")
    rootfs_build = rootfs_builds[0]
    if rootfs_build.build_buildType != ROOTFS_BUILD_TYPE:
        raise SbomEvidenceError("SPDX rootfs build type is not the locked task type")
    relationships = list(objset.foreach_type(spdx.Relationship))
    output_relationships = [
        relation
        for relation in relationships
        if relation.from_ is rootfs_build
        and relation.relationshipType == spdx.RelationshipType.hasOutput
    ]
    if len(output_relationships) != 1 or list(output_relationships[0].to) != root_packages:
        raise SbomEvidenceError("SPDX rootfs build output is not the rootfs package")
    if (
        not isinstance(output_relationships[0], spdx.LifecycleScopedRelationship)
        or output_relationships[0].scope != spdx.LifecycleScopeType.build
    ):
        raise SbomEvidenceError("SPDX rootfs output does not use build lifecycle scope")

    input_relationships = [
        relation
        for relation in relationships
        if relation.from_ is rootfs_build
        and relation.relationshipType == spdx.RelationshipType.hasInput
    ]
    if len(input_relationships) != 1:
        raise SbomEvidenceError("SPDX rootfs build must have one installed-package input set")
    if (
        not isinstance(input_relationships[0], spdx.LifecycleScopedRelationship)
        or input_relationships[0].scope != spdx.LifecycleScopeType.build
    ):
        raise SbomEvidenceError("SPDX rootfs inputs do not use build lifecycle scope")
    package_inputs: list[Any] = []
    for relation in input_relationships:
        package_inputs.extend(list(relation.to))
    if not package_inputs or len(package_inputs) > MAX_INSTALLED_PACKAGES:
        raise SbomEvidenceError(
            "SPDX rootfs installed-package input set is absent or exceeds its bound"
        )
    if any(not isinstance(item, spdx.software_Package) for item in package_inputs):
        raise SbomEvidenceError("SPDX rootfs input set contains a non-package element")
    if any(
        item.software_primaryPurpose != spdx.software_SoftwarePurpose.install
        for item in package_inputs
    ):
        raise SbomEvidenceError("SPDX rootfs input packages must use the install purpose")
    names = [
        safe_token(package.name, "installed package name")
        for package in package_inputs
    ]
    if len(names) != len(set(names)):
        raise SbomEvidenceError("SPDX rootfs installed-package names are not unique")
    missing = sorted(set(required_packages) - set(names))
    forbidden = sorted(set(forbidden_packages) & set(names))
    if missing:
        raise SbomEvidenceError("required installed packages are missing: " + ", ".join(missing))
    if forbidden:
        raise SbomEvidenceError("forbidden installed packages are present: " + ", ".join(forbidden))

    installed_by_name = {package.name: package for package in package_inputs}
    package_records: list[dict[str, Any]] = []
    for name, expected_license in sorted(required_packages.items()):
        package = installed_by_name[name]
        expressions: list[str] = []
        for relation in relationships:
            if relation.from_ is not package:
                continue
            if relation.relationshipType != spdx.RelationshipType.hasDeclaredLicense:
                continue
            for target in relation.to:
                if not isinstance(target, spdx.simplelicensing_LicenseExpression):
                    raise SbomEvidenceError(
                        f"declared license for {name} is not a LicenseExpression"
                    )
                expressions.append(target.simplelicensing_licenseExpression)
        if expressions != [expected_license]:
            raise SbomEvidenceError(
                f"declared license for {name} is {expressions!r}, "
                f"expected [{expected_license!r}]"
            )
        version = safe_token(package.software_packageVersion, f"package {name} version")
        package_records.append(
            {"name": name, "version": version, "declared_license": expected_license}
        )

    deploy_root = deploy_dir.resolve(strict=True)
    artifact_records: list[dict[str, Any]] = []
    seen_artifacts: set[str] = set()
    total_artifact_bytes = 0
    for artifact in sorted(root_files, key=lambda item: item.name):
        basename = safe_token(artifact.name, "artifact basename")
        if basename in seen_artifacts:
            raise SbomEvidenceError(f"duplicate artifact basename: {basename}")
        seen_artifacts.add(basename)
        path = deploy_root / basename
        if path.is_symlink() or not path.is_file():
            raise SbomEvidenceError(f"artifact is not a regular deployed file: {basename}")
        resolved = path.resolve(strict=True)
        if resolved.parent != deploy_root:
            raise SbomEvidenceError(f"artifact escapes the deploy directory: {basename}")
        declared_digest = only_sha256(spdx, artifact, f"artifact {basename}")
        actual_digest, size = hash_file(resolved)
        total_artifact_bytes += size
        if total_artifact_bytes > MAX_TOTAL_ARTIFACT_BYTES:
            raise SbomEvidenceError(
                "image artifacts exceed the aggregate byte bound"
            )
        if actual_digest != declared_digest:
            raise SbomEvidenceError(f"artifact SHA-256 mismatch: {basename}")
        artifact_records.append(
            {"basename": basename, "sha256": actual_digest, "size_bytes": size}
        )

    return {
        "document_count": len(documents),
        "sbom_count": len(sboms),
        "root_element_count": len(sbom.rootElement),
        "unresolved_id_count": len(unresolved),
        "installed_package_count": len(package_inputs),
        "packages": package_records,
        "artifacts": artifact_records,
    }


def resolve_sbom_path(deploy_dir: Path, image_link_name: str) -> tuple[Path, str]:
    link_name = safe_token(image_link_name, "IMAGE_LINK_NAME")
    deploy_root = deploy_dir.resolve(strict=True)
    link = deploy_root / f"{link_name}.spdx.json"
    if not link.exists():
        raise SbomEvidenceError("stable image SPDX document is missing")
    resolved = link.resolve(strict=True)
    if resolved.parent != deploy_root:
        raise SbomEvidenceError("stable image SPDX link escapes DEPLOY_DIR_IMAGE")
    if not resolved.is_file():
        raise SbomEvidenceError("stable image SPDX target is not a regular file")
    return resolved, resolved.name


def build_evidence(
    *,
    repo: Path,
    lab_id: str,
    build_dir: Path,
    deploy_dir: Path,
    image_link_name: str,
    settings: dict[str, str],
    task_exit_code: int,
) -> dict[str, Any]:
    repo = repo.resolve()
    if type(task_exit_code) is not int or not 0 <= task_exit_code <= 255:
        raise SbomEvidenceError("task exit code must be an integer from 0 through 255")
    if task_exit_code != 0:
        raise SbomEvidenceError("SPDX task did not complete successfully")
    if settings != EXPECTED_SETTINGS:
        raise SbomEvidenceError("SPDX settings were not validated")
    manifest, selected, index_digest, manifest_digest, required, forbidden = (
        selected_contract(repo, lab_id)
    )
    lock, lock_digest, oe_core = source_authority(repo)
    deploy_root = deploy_dir.resolve(strict=True)
    build_root = build_dir.resolve()
    try:
        deploy_root.relative_to(build_root)
    except ValueError as exc:
        raise SbomEvidenceError(
            "DEPLOY_DIR_IMAGE must be inside the selected build directory"
        ) from exc
    sbom_path, sbom_basename = resolve_sbom_path(deploy_root, image_link_name)
    raw, sbom_digest = read_sbom(sbom_path)
    spdx = load_spdx_model(repo, oe_core)
    objset = deserialize_spdx(spdx, raw)
    image = manifest["build"]["targets"][0]
    graph = analyze_graph(
        spdx=spdx,
        objset=objset,
        deploy_dir=deploy_root,
        image=image,
        required_packages=required,
        forbidden_packages=forbidden,
    )
    revision, dirty = project_state(repo)
    version = (repo / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(version):
        raise SbomEvidenceError("project version is not ASCII Semantic Versioning")
    release = object_value(lock["release"], "source lock release")
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "project": {
            "name": PROJECT_NAME,
            "version": version,
            "revision": revision,
            "dirty": dirty,
        },
        "inputs": {
            "source_lock_sha256": lock_digest,
            "openembedded_core_commit": oe_core["commit"],
            "lab_index_sha256": index_digest,
            "lab_manifest_sha256": manifest_digest,
            "yocto_version": release["version"],
            "yocto_series": release["series"],
        },
        "lab": {
            "id": selected,
            "machine": manifest["build"]["machine"],
            "image": image,
            "evidence_profile": EVIDENCE_PROFILE,
        },
        "generator": {
            "name": "openembedded-create-spdx",
            "spdx_version": SPDX_VERSION,
            "profiles": list(PROFILES),
            "settings": dict(sorted(settings.items())),
        },
        "source_sbom": {
            "basename": sbom_basename,
            "sha256": sbom_digest,
            "size_bytes": len(raw),
            "document_count": graph["document_count"],
            "sbom_count": graph["sbom_count"],
            "root_element_count": graph["root_element_count"],
            "unresolved_id_count": graph["unresolved_id_count"],
            "installed_package_count": graph["installed_package_count"],
            "artifact_count": len(graph["artifacts"]),
        },
        "packages": graph["packages"],
        "artifacts": graph["artifacts"],
        "checks": [{"id": check_id, "status": "passed"} for check_id in CHECK_IDS],
        "task_exit_code": task_exit_code,
        "result": "passed",
    }
    validate_evidence(evidence)
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
            "schema_version",
            "kind",
            "project",
            "inputs",
            "lab",
            "generator",
            "source_sbom",
            "packages",
            "artifacts",
            "checks",
            "task_exit_code",
            "result",
        },
        "evidence",
    )
    if type(evidence["schema_version"]) is not int or evidence["schema_version"] != 1:
        raise SbomEvidenceError("unsupported evidence schema_version")
    if evidence["kind"] != KIND:
        raise SbomEvidenceError("unsupported evidence kind")

    project = object_value(evidence["project"], "project")
    exact_keys(project, {"name", "version", "revision", "dirty"}, "project")
    if project["name"] != PROJECT_NAME:
        raise SbomEvidenceError("project.name is not recognized")
    version = string_value(project["version"], "project.version", max_length=128)
    if not SEMVER.fullmatch(version):
        raise SbomEvidenceError("project.version is not ASCII Semantic Versioning")
    revision = sha1_value(project["revision"], "project.revision")
    dirty = boolean_value(project["dirty"], "project.dirty")
    if expected_revision is not None:
        if revision != sha1_value(expected_revision, "required revision"):
            raise SbomEvidenceError(
                f"project.revision is {revision}, required {expected_revision}"
            )

    inputs = object_value(evidence["inputs"], "inputs")
    exact_keys(
        inputs,
        {
            "source_lock_sha256",
            "openembedded_core_commit",
            "lab_index_sha256",
            "lab_manifest_sha256",
            "yocto_version",
            "yocto_series",
        },
        "inputs",
    )
    for key in ("source_lock_sha256", "lab_index_sha256", "lab_manifest_sha256"):
        sha256_value(inputs[key], f"inputs.{key}")
    sha1_value(inputs["openembedded_core_commit"], "inputs.openembedded_core_commit")
    safe_token(inputs["yocto_version"], "inputs.yocto_version")
    safe_token(inputs["yocto_series"], "inputs.yocto_series")

    lab = object_value(evidence["lab"], "lab")
    exact_keys(lab, {"id", "machine", "image", "evidence_profile"}, "lab")
    lab_id = safe_token(lab["id"], "lab.id")
    identity = LAB_IDENTITIES.get(lab_id)
    if identity is None:
        raise SbomEvidenceError("lab.id is not recognized by evidence schema 1")
    if lab["machine"] != identity["machine"] or lab["image"] != identity["image"]:
        raise SbomEvidenceError("lab machine or image is not recognized")
    if lab["evidence_profile"] != EVIDENCE_PROFILE:
        raise SbomEvidenceError("lab evidence profile is not recognized")

    generator = object_value(evidence["generator"], "generator")
    exact_keys(generator, {"name", "spdx_version", "profiles", "settings"}, "generator")
    if generator["name"] != "openembedded-create-spdx":
        raise SbomEvidenceError("generator.name is not recognized")
    if generator["spdx_version"] != SPDX_VERSION:
        raise SbomEvidenceError("generator.spdx_version is not recognized")
    if generator["profiles"] != list(PROFILES):
        raise SbomEvidenceError("generator.profiles do not match the evidence profile")
    settings = object_value(generator["settings"], "generator.settings")
    if settings != EXPECTED_SETTINGS:
        raise SbomEvidenceError("generator.settings do not match the evidence profile")
    for name, value in settings.items():
        string_value(value, f"generator.settings.{name}", allow_empty=True)

    source_sbom = object_value(evidence["source_sbom"], "source_sbom")
    exact_keys(
        source_sbom,
        {
            "basename",
            "sha256",
            "size_bytes",
            "document_count",
            "sbom_count",
            "root_element_count",
            "unresolved_id_count",
            "installed_package_count",
            "artifact_count",
        },
        "source_sbom",
    )
    basename = safe_token(source_sbom["basename"], "source_sbom.basename")
    if not basename.endswith(".spdx.json"):
        raise SbomEvidenceError("source_sbom.basename must end in .spdx.json")
    sha256_value(source_sbom["sha256"], "source_sbom.sha256")
    integer_value(
        source_sbom["size_bytes"],
        "source_sbom.size_bytes",
        minimum=1,
        maximum=MAX_SBOM_BYTES,
    )
    if source_sbom["document_count"] != 1 or type(source_sbom["document_count"]) is not int:
        raise SbomEvidenceError("source_sbom.document_count must be 1")
    if source_sbom["sbom_count"] != 1 or type(source_sbom["sbom_count"]) is not int:
        raise SbomEvidenceError("source_sbom.sbom_count must be 1")
    if source_sbom["unresolved_id_count"] != 0 or type(source_sbom["unresolved_id_count"]) is not int:
        raise SbomEvidenceError("source_sbom.unresolved_id_count must be 0")
    installed_count = integer_value(
        source_sbom["installed_package_count"],
        "source_sbom.installed_package_count",
        minimum=1,
        maximum=MAX_INSTALLED_PACKAGES,
    )
    artifact_count = integer_value(
        source_sbom["artifact_count"],
        "source_sbom.artifact_count",
        minimum=1,
        maximum=MAX_ARTIFACTS,
    )
    root_count = integer_value(
        source_sbom["root_element_count"],
        "source_sbom.root_element_count",
        minimum=2,
        maximum=MAX_ARTIFACTS + 1,
    )
    if root_count != artifact_count + 1:
        raise SbomEvidenceError("source_sbom root and artifact counts are inconsistent")

    packages = evidence["packages"]
    expected_packages = identity["packages"]
    if not isinstance(packages, list) or len(packages) != len(expected_packages):
        raise SbomEvidenceError("packages must contain the exact project package set")
    package_names: list[str] = []
    for index, raw_package in enumerate(packages):
        package = object_value(raw_package, f"packages[{index}]")
        exact_keys(package, {"name", "version", "declared_license"}, f"packages[{index}]")
        name = safe_token(package["name"], f"packages[{index}].name")
        safe_token(package["version"], f"packages[{index}].version")
        declared = string_value(
            package["declared_license"], f"packages[{index}].declared_license"
        )
        if expected_packages.get(name) != declared:
            raise SbomEvidenceError(f"package {name} has an unexpected declared license")
        package_names.append(name)
    if package_names != sorted(expected_packages):
        raise SbomEvidenceError("packages are incomplete, duplicated, or out of order")
    if installed_count < len(packages):
        raise SbomEvidenceError("installed package count is smaller than project package set")

    artifacts = evidence["artifacts"]
    if not isinstance(artifacts, list) or len(artifacts) != artifact_count:
        raise SbomEvidenceError("artifacts do not match source_sbom.artifact_count")
    artifact_names: list[str] = []
    total_artifact_bytes = 0
    for index, raw_artifact in enumerate(artifacts):
        artifact = object_value(raw_artifact, f"artifacts[{index}]")
        exact_keys(artifact, {"basename", "sha256", "size_bytes"}, f"artifacts[{index}]")
        artifact_names.append(safe_token(artifact["basename"], f"artifacts[{index}].basename"))
        sha256_value(artifact["sha256"], f"artifacts[{index}].sha256")
        total_artifact_bytes += integer_value(
            artifact["size_bytes"],
            f"artifacts[{index}].size_bytes",
            minimum=1,
            maximum=MAX_ARTIFACT_BYTES,
        )
        if total_artifact_bytes > MAX_TOTAL_ARTIFACT_BYTES:
            raise SbomEvidenceError(
                "image artifacts exceed the aggregate byte bound"
            )
    if artifact_names != sorted(artifact_names) or len(artifact_names) != len(set(artifact_names)):
        raise SbomEvidenceError("artifacts must be unique and sorted by basename")

    checks = evidence["checks"]
    if not isinstance(checks, list) or len(checks) != len(CHECK_IDS):
        raise SbomEvidenceError("checks must contain the complete evidence check set")
    for expected_id, raw_check in zip(CHECK_IDS, checks, strict=True):
        check = object_value(raw_check, f"check {expected_id}")
        exact_keys(check, {"id", "status"}, f"check {expected_id}")
        if check != {"id": expected_id, "status": "passed"}:
            raise SbomEvidenceError(f"check {expected_id} did not pass exactly")
    if evidence["task_exit_code"] != 0 or type(evidence["task_exit_code"]) is not int:
        raise SbomEvidenceError("task_exit_code must be 0")
    if evidence["result"] != "passed":
        raise SbomEvidenceError("result must be passed")
    if require_pass and dirty:
        raise SbomEvidenceError("passing SPDX evidence requires a clean project tree")

    if current_repo is not None:
        repo = current_repo.resolve()
        manifest, selected, index_digest, manifest_digest, required, _ = selected_contract(
            repo, lab_id
        )
        lock, lock_digest, oe_core = source_authority(repo)
        current_version = (repo / "VERSION").read_text(encoding="utf-8").strip()
        current_identity = {
            "source_lock_sha256": lock_digest,
            "openembedded_core_commit": oe_core["commit"],
            "lab_index_sha256": index_digest,
            "lab_manifest_sha256": manifest_digest,
            "yocto_version": lock["release"]["version"],
            "yocto_series": lock["release"]["series"],
        }
        if inputs != current_identity:
            raise SbomEvidenceError("evidence inputs do not match current project inputs")
        if version != current_version or selected != lab_id:
            raise SbomEvidenceError("evidence project or lab identity is not current")
        if manifest["build"]["machine"] != lab["machine"]:
            raise SbomEvidenceError("evidence machine is not current")
        if manifest["build"]["targets"] != [lab["image"]]:
            raise SbomEvidenceError("evidence image is not current")
        if required != expected_packages:
            raise SbomEvidenceError("evidence package contract is not current")


def read_evidence(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_EVIDENCE_BYTES + 1)
    except OSError as exc:
        raise SbomEvidenceError(f"cannot read evidence: {exc}") from exc
    if len(raw) > MAX_EVIDENCE_BYTES:
        raise SbomEvidenceError(f"evidence exceeds {MAX_EVIDENCE_BYTES} bytes")
    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicate_pairs,
            parse_constant=reject_json_constant,
            parse_int=parse_bounded_integer,
        )
    except SbomEvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise SbomEvidenceError(f"invalid evidence JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise SbomEvidenceError("evidence root must be an object")
    validate_json_shape(data)
    return data


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    verify_evidence_output(path, create_parent=True)
    payload = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    if len(payload.encode("utf-8")) > MAX_EVIDENCE_BYTES:
        raise SbomEvidenceError("generated evidence exceeds its byte bound")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=".sbom-evidence-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        verify_evidence_output(path)
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--lab", help="lab id; defaults to the catalog default")
    parser.add_argument(
        "--build-dir",
        help="active build directory; defaults to the selected manifest path",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    preflight = subparsers.add_parser("preflight", help="verify current SPDX inputs")
    preflight.add_argument("--setting", action="append", default=[])
    subparsers.add_parser("path", help="print the selected generated evidence path")
    subparsers.add_parser("clear", help="remove only the selected stale evidence file")
    collect = subparsers.add_parser("collect", help="collect the selected image SPDX evidence")
    collect.add_argument("--deploy-dir", required=True)
    collect.add_argument("--image-link-name", required=True)
    collect.add_argument("--task-exit-code", required=True, type=int)
    collect.add_argument("--setting", action="append", default=[])
    validate = subparsers.add_parser("validate", help="validate an evidence document")
    validate.add_argument("evidence")
    validate.add_argument("--require-pass", action="store_true")
    validate.add_argument("--require-revision")
    validate.add_argument("--require-current-inputs", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    try:
        lab_id = args.lab
        if args.command == "validate":
            validate_evidence(
                read_evidence(Path(args.evidence)),
                require_pass=args.require_pass,
                expected_revision=args.require_revision,
                current_repo=repo if args.require_current_inputs else None,
            )
            print(f"sbom-evidence: PASS: {args.evidence}")
            return 0
        manifest, selected, _, _, _, _ = selected_contract(repo, lab_id)
        build_dir = active_build_dir(repo, manifest, args.build_dir)
        if args.command in ("path", "clear"):
            output = evidence_path(repo, manifest, build_dir)
            if args.command == "path":
                print(output)
            else:
                clear_evidence(output)
                print(f"sbom-evidence: cleared: {output}")
            return 0
        settings = parse_settings(args.setting)
        source_authority(repo)
        if args.command == "preflight":
            print(f"sbom-evidence: PASS: preflight {selected}")
            return 0
        evidence = build_evidence(
            repo=repo,
            lab_id=selected,
            build_dir=build_dir,
            deploy_dir=Path(args.deploy_dir),
            image_link_name=args.image_link_name,
            settings=settings,
            task_exit_code=args.task_exit_code,
        )
        output = evidence_path(repo, manifest, build_dir)
        write_evidence(output, evidence)
        print(f"sbom-evidence: {evidence['result']}: {output}")
        return 0
    except LabError as exc:
        print(f"sbom-evidence: FAIL: {exc}", file=sys.stderr)
        return 2
    except (
        SbomEvidenceError,
        LockError,
        OSError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"sbom-evidence: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
