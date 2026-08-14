#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Validate the exact test-only diagnostics JSON Schema dependency set."""

from __future__ import annotations

import argparse
import email
import hashlib
import importlib
import importlib.metadata
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any


LOCK_PATH = "config/diagnostics-schema-validator.lock.json"
MAX_LOCK_BYTES = 64 * 1024
SHA256 = re.compile(r"[0-9a-f]{64}")
EXPECTED_CANONICAL_SHA256 = "5e19001d5e2fa0405c963123ca09f2c14c66a02d21264a7fac9e951c284b967e"
ROOT_KEYS = {"schema_version", "purpose", "runtime_dependency", "environment", "installation", "packages", "license_summary", "verification"}
PACKAGE_KEYS = {"name", "version", "license_expression", "requires_python", "dependencies", "filename", "url", "sha256", "license_file", "license_sha256"}
EXPECTED = (
    ("attrs", "26.1.0", "attrs-26.1.0-py3-none-any.whl", "MIT", "c647aa4a12dfbad9333ca4e71fe62ddc36f4e63b2d260a37a8b83d2f043ac309", "attrs-26.1.0.dist-info/licenses/LICENSE", "882115c95dfc2af1eeb6714f8ec6d5cbcabf667caff8729f42420da63f714e9f", ()),
    ("jsonschema", "4.26.0", "jsonschema-4.26.0-py3-none-any.whl", "MIT", "d489f15263b8d200f8387e64b4c3a75f06629559fb73deb8fdfb525f2dab50ce", "jsonschema-4.26.0.dist-info/licenses/COPYING", "4f92a015a13c4d1a040bef018aa13430b4f1bc73b41b16bb846c346766de7439", ("attrs>=22.2.0", "jsonschema-specifications>=2023.03.6", "referencing>=0.28.4", "rpds-py>=0.25.0")),
    ("jsonschema-specifications", "2025.9.1", "jsonschema_specifications-2025.9.1-py3-none-any.whl", "MIT", "98802fee3a11ee76ecaca44429fda8a41bff98b00a0f2838151b113f210cc6fe", "jsonschema_specifications-2025.9.1.dist-info/licenses/COPYING", "42dcd63495f87b4eb7c7757afa379bb55a53f94afd7a5f657d9adf57236e515c", ("referencing>=0.31.0",)),
    ("referencing", "0.37.0", "referencing-0.37.0-py3-none-any.whl", "MIT", "381329a9f99628c9069361716891d34ad94af76e461dcb0335825aecc7692231", "referencing-0.37.0.dist-info/licenses/COPYING", "42dcd63495f87b4eb7c7757afa379bb55a53f94afd7a5f657d9adf57236e515c", ("attrs>=22.2.0", "rpds-py>=0.7.0", "typing-extensions>=4.4.0; python_version < '3.13'")),
    ("rpds-py", "2026.6.3", "rpds_py-2026.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl", "MIT", "ecabd69db66de867690f9797f2f8fa27ba501bbc24540cbdbdc649cd15888ba6", "rpds_py-2026.6.3.dist-info/licenses/LICENSE", "314e4e91be3baa93c0fb4bccc9e4e97cd643eb839b065af921782c2175fe9909", ()),
    ("typing-extensions", "4.16.0", "typing_extensions-4.16.0-py3-none-any.whl", "PSF-2.0", "481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8", "typing_extensions-4.16.0.dist-info/licenses/LICENSE", "3b2f81fe21d181c499c59a256c8e1968455d6689d269aa85373bfb6af41da3bf", ()),
)
EXPECTED_URLS = {
    "attrs": "https://files.pythonhosted.org/packages/64/b4/17d4b0b2a2dc85a6df63d1157e028ed19f90d4cd97c36717afef2bc2f395/attrs-26.1.0-py3-none-any.whl",
    "jsonschema": "https://files.pythonhosted.org/packages/69/90/f63fb5873511e014207a475e2bb4e8b2e570d655b00ac19a9a0ca0a385ee/jsonschema-4.26.0-py3-none-any.whl",
    "jsonschema-specifications": "https://files.pythonhosted.org/packages/41/45/1a4ed80516f02155c51f51e8cedb3c1902296743db0bbc66608a0db2814f/jsonschema_specifications-2025.9.1-py3-none-any.whl",
    "referencing": "https://files.pythonhosted.org/packages/2c/58/ca301544e1fa93ed4f80d724bf5b194f6e4b945841c5bfd555878eea9fcb/referencing-0.37.0-py3-none-any.whl",
    "rpds-py": "https://files.pythonhosted.org/packages/04/8f/d2f3f532616be4d06c316ef119683e832bd3d41e112bf3a88f4151c95b17/rpds_py-2026.6.3-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
    "typing-extensions": "https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl",
}


class LockError(ValueError):
    pass


def duplicate_guard(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise LockError(f"duplicate key: {key}")
        value[key] = item
    return value


def exact(value: Any, keys: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise LockError(f"{label} fields differ from the closed contract")
    return value


def load(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        raw = handle.read(MAX_LOCK_BYTES + 1)
    if len(raw) > MAX_LOCK_BYTES:
        raise LockError("dependency lock exceeds its byte limit")
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=duplicate_guard)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise LockError("dependency lock is invalid JSON") from exc
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != EXPECTED_CANONICAL_SHA256:
        raise LockError("dependency lock differs from the approved exact record")
    exact(value, ROOT_KEYS, "lock")
    if value["schema_version"] != 1 or type(value["schema_version"]) is not int:
        raise LockError("unsupported dependency-lock schema")
    if value["runtime_dependency"] is not False:
        raise LockError("schema validator must remain test-only")
    environment = exact(value["environment"], {"operating_system", "architecture", "python_implementation", "python_version", "python_abi", "runner_label"}, "environment")
    if environment != {"operating_system": "linux", "architecture": "x86_64", "python_implementation": "cpython", "python_version": "3.12", "python_abi": "cp312", "runner_label": "ubuntu-24.04"}:
        raise LockError("dependency environment differs from the approved platform")
    installation = exact(value["installation"], {"network_scope", "verify_before_install", "source_distributions", "package_index_resolution", "dependency_resolution", "required_options"}, "installation")
    if installation["network_scope"] != "six exact HTTPS wheel URLs" or installation["verify_before_install"] != "sha256":
        raise LockError("installation network or integrity policy differs")
    if any(installation[key] != "forbidden" for key in ("source_distributions", "package_index_resolution", "dependency_resolution")):
        raise LockError("installation policy permits dependency expansion")
    if installation["required_options"] != ["--no-index", "--no-deps", "--only-binary=:all:", "--disable-pip-version-check", "--no-input"]:
        raise LockError("installation options differ from the approved set")
    packages = value["packages"]
    if not isinstance(packages, list) or len(packages) != len(EXPECTED):
        raise LockError("dependency package set differs")
    for package, expected in zip(packages, EXPECTED, strict=True):
        exact(package, PACKAGE_KEYS, f"package {expected[0]}")
        identity = (package["name"], package["version"], package["filename"], package["license_expression"])
        if identity != expected[:4]:
            raise LockError(f"package identity differs for {expected[0]}")
        if package["url"] != EXPECTED_URLS[expected[0]]:
            raise LockError(f"package URL is not an exact PyPI file URL for {expected[0]}")
        if not SHA256.fullmatch(package["sha256"]) or not SHA256.fullmatch(package["license_sha256"]):
            raise LockError(f"package digest is invalid for {expected[0]}")
        if not isinstance(package["dependencies"], list) or not all(isinstance(item, str) and item for item in package["dependencies"]):
            raise LockError(f"package dependencies are invalid for {expected[0]}")
        if (package["sha256"], package["license_file"], package["license_sha256"], tuple(package["dependencies"])) != expected[4:]:
            raise LockError(f"package integrity or dependency record differs for {expected[0]}")
    if value["license_summary"] != {"MIT": 5, "PSF-2.0": 1, "redistributed_in_source_tree": False}:
        raise LockError("license summary differs from the package records")
    return value


def verify_files(lock: dict[str, Any], directory: Path) -> None:
    expected_names = {package["filename"] for package in lock["packages"]}
    actual_names = {path.name for path in directory.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise LockError("wheel directory differs from the locked six-file set")
    for package in lock["packages"]:
        path = directory / package["filename"]
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != package["sha256"]:
            raise LockError(f"wheel digest differs for {package['name']}")
        with zipfile.ZipFile(path) as archive:
            try:
                license_bytes = archive.read(package["license_file"])
                metadata_name = next(
                    name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
                )
                metadata = email.message_from_bytes(archive.read(metadata_name))
            except KeyError as exc:
                raise LockError(f"wheel license file is missing for {package['name']}") from exc
            except StopIteration as exc:
                raise LockError(f"wheel metadata is missing for {package['name']}") from exc
        if hashlib.sha256(license_bytes).hexdigest() != package["license_sha256"]:
            raise LockError(f"wheel license digest differs for {package['name']}")
        identity = (
            str(metadata.get("Name", "")).replace("_", "-").lower(),
            metadata.get("Version"),
            metadata.get("Requires-Python"),
            metadata.get("License-Expression"),
        )
        if identity != (
            package["name"],
            package["version"],
            package["requires_python"],
            package["license_expression"],
        ):
            raise LockError(f"wheel metadata differs for {package['name']}")
        dependencies = tuple(
            item
            for item in metadata.get_all("Requires-Dist", [])
            if "extra ==" not in item
        )
        if dependencies != tuple(package["dependencies"]):
            raise LockError(f"wheel dependency metadata differs for {package['name']}")


def verify_installed(lock: dict[str, Any]) -> None:
    modules = {
        "attrs": "attrs",
        "jsonschema": "jsonschema",
        "jsonschema-specifications": "jsonschema_specifications",
        "referencing": "referencing",
        "rpds-py": "rpds",
        "typing-extensions": "typing_extensions",
    }
    for package in lock["packages"]:
        if importlib.metadata.version(package["name"]) != package["version"]:
            raise LockError(f"installed version differs for {package['name']}")
        importlib.import_module(modules[package["name"]])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--wheel-directory")
    parser.add_argument("--installed", action="store_true")
    args = parser.parse_args()
    try:
        lock = load(Path(args.repo).resolve() / LOCK_PATH)
        if args.wheel_directory:
            verify_files(lock, Path(args.wheel_directory).resolve())
        if args.installed:
            verify_installed(lock)
    except (OSError, LockError, zipfile.BadZipFile, importlib.metadata.PackageNotFoundError) as exc:
        print(f"diagnostics-schema-lock: FAIL: {exc}", file=sys.stderr)
        return 1
    print("diagnostics-schema-lock: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
