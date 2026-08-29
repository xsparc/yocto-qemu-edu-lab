#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Verify the locked tool and metadata interface used by SDK iteration."""

from __future__ import annotations

import argparse
import ast
import os
import shutil
import sys
from pathlib import Path
from typing import Callable


sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from source_lock import (  # noqa: E402
    LockError,
    locked_path,
    read_lock,
    status_result,
)


MAX_TOOL_SOURCE_BYTES = 256 * 1024
MAX_PROJECT_LAYER_ENTRIES = 4096
SOURCE_INTERFACES = {
    "openembedded-core": {
        "scripts/devtool": {"create-workspace", "General", "workspace_path", "-q"},
        "scripts/runqemu": {"snapshot", "slirp", "nographic"},
        "scripts/lib/devtool/build.py": {"build"},
        "scripts/lib/devtool/standard.py": {
            "modify",
            "--no-extract",
            "-n",
            "reset",
            "--no-clean",
        },
        "scripts/lib/devtool/deploy.py": {
            "deploy-target",
            "undeploy-target",
            "--no-host-check",
            "-c",
            "--port",
            "-P",
            "--ssh-exec",
            "-e",
            "--no-strip",
        },
        "scripts/lib/devtool/ide_sdk.py": {
            "ide-sdk",
            "--mode",
            "modified",
            "--ide",
        },
        "scripts/lib/devtool/ide_plugins/ide_none.py": {"none"},
    },
}
EXECUTABLE_INTERFACES = {
    "bitbake": ("bitbake", "bin/bitbake"),
    "bitbake-getvar": ("bitbake", "bin/bitbake-getvar"),
    "bitbake-layers": ("bitbake", "bin/bitbake-layers"),
    "devtool": ("openembedded-core", "scripts/devtool"),
    "runqemu": ("openembedded-core", "scripts/runqemu"),
}
SDK_RECIPE = "qemu-edu-sdk-sample"
SDK_RECIPE_VERSION = "1.0"
SDK_RECIPE_LICENSE = "MIT"
SDK_COMPATIBLE_MACHINE = "^(qemu-edu-x86-64|qemu-edu-platform-arm64)$"
SDK_SOURCE_URI = "file://qemu-edu-sdk-sample.c"
SDK_LABS = {
    "pci-x86-64": "qemu-edu-x86-64",
    "platform-arm64": "qemu-edu-platform-arm64",
}


class SdkToolingError(RuntimeError):
    """The locked SDK tooling contract could not be verified."""


def locked_sources(repo: Path) -> dict[str, Path]:
    """Return verified source roots by closed source-lock identifier."""
    root = repo.resolve()
    data, digest = read_lock(root / "config/sources.lock.json")
    if not status_result(root, data, digest)["ok"]:
        raise SdkToolingError("locked SDK tooling sources are not ready")
    return {
        source["id"]: locked_path(root, source["path"])
        for source in data["sources"]
    }


def _read_tool_source(source_root: Path, relative: str) -> str:
    path = source_root / relative
    try:
        if path.is_symlink() or not path.is_file():
            raise SdkToolingError("a locked SDK tool source is not a regular file")
        path.resolve(strict=True).relative_to(source_root.resolve(strict=True))
        with path.open("rb") as handle:
            raw = handle.read(MAX_TOOL_SOURCE_BYTES + 1)
    except (OSError, ValueError) as exc:
        raise SdkToolingError("a locked SDK tool source is unavailable") from exc
    if len(raw) > MAX_TOOL_SOURCE_BYTES:
        raise SdkToolingError("a locked SDK tool source exceeds its byte bound")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SdkToolingError("a locked SDK tool source is not UTF-8") from exc


def verify_source_interfaces(sources: dict[str, Path]) -> None:
    """Require the exact command and option literals used by the closed loop."""
    for source_id, files in SOURCE_INTERFACES.items():
        source_root = sources.get(source_id)
        if source_root is None:
            raise SdkToolingError("a required locked SDK source is missing")
        for relative, required_literals in files.items():
            text = _read_tool_source(source_root, relative)
            try:
                tree = ast.parse(text, filename=relative)
            except (SyntaxError, RecursionError, MemoryError) as exc:
                raise SdkToolingError("a locked SDK tool source could not be parsed") from exc
            literals = {
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)
            }
            if not required_literals.issubset(literals):
                raise SdkToolingError("the locked SDK command interface is incompatible")


def verify_executable_interfaces(
    sources: dict[str, Path],
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> None:
    """Require build-facing executables to resolve inside their locked checkout."""
    for command, (source_id, relative) in EXECUTABLE_INTERFACES.items():
        source_root = sources.get(source_id)
        if source_root is None:
            raise SdkToolingError("a required locked SDK source is missing")
        expected = source_root / relative
        found = which(command)
        try:
            if (
                found is None
                or expected.is_symlink()
                or not expected.is_file()
                or not os.access(expected, os.X_OK)
                or Path(found).is_symlink()
                or Path(found).resolve(strict=True) != expected.resolve(strict=True)
            ):
                raise SdkToolingError(
                    f"{command} does not resolve to the locked source checkout"
                )
        except (OSError, RuntimeError) as exc:
            raise SdkToolingError(
                f"{command} does not resolve to the locked source checkout"
            ) from exc


def verify_python_interface(sources: dict[str, Path]) -> Path:
    """Return the exact BitBake library path required by locked Python tools."""
    source_root = sources.get("bitbake")
    if source_root is None:
        raise SdkToolingError("a required locked SDK source is missing")
    path = source_root / "lib"
    try:
        if path.is_symlink() or not path.is_dir():
            raise SdkToolingError("the locked BitBake Python library is unavailable")
        resolved = path.resolve(strict=True)
        resolved.relative_to(source_root.resolve(strict=True))
    except (OSError, RuntimeError, ValueError) as exc:
        raise SdkToolingError("the locked BitBake Python library is unavailable") from exc
    return resolved


def verify_project_layer_authority(repo: Path) -> None:
    """Reject project-layer hooks that can replace the locked devtool/sample path."""
    layer = repo.resolve() / "meta-qemu-edu"
    if layer.is_symlink() or not layer.is_dir():
        raise SdkToolingError("the project layer is unavailable")
    plugin_root = layer / "lib/devtool"
    if plugin_root.exists() or plugin_root.is_symlink():
        raise SdkToolingError("the project layer must not provide devtool plugins")
    entries = 0
    appends: list[Path] = []
    try:
        for directory, names, files in os.walk(layer, followlinks=False):
            root = Path(directory)
            entries += len(names) + len(files)
            if entries > MAX_PROJECT_LAYER_ENTRIES:
                raise SdkToolingError("the project layer exceeds its entry bound")
            for name in names:
                if (root / name).is_symlink():
                    raise SdkToolingError("the project layer contains a symbolic link")
            for name in files:
                path = root / name
                if path.is_symlink():
                    raise SdkToolingError("the project layer contains a symbolic link")
                if name.startswith(SDK_RECIPE) and name.endswith(".bbappend"):
                    appends.append(path)
    except OSError as exc:
        raise SdkToolingError("project SDK metadata authority is unavailable") from exc
    if appends:
        raise SdkToolingError("the project layer must not append the SDK sample")


def verify_tooling(repo: Path, *, require_executables: bool = True) -> Path:
    sources = locked_sources(repo)
    verify_source_interfaces(sources)
    python_path = verify_python_interface(sources)
    verify_project_layer_authority(repo)
    if require_executables:
        verify_executable_interfaces(sources)
    return python_path


def verify_recipe_metadata(
    repo: Path,
    lab_id: str,
    *,
    pn: str,
    pv: str,
    license_expression: str,
    compatible_machine: str,
    source_uri: str,
    recipe_file: str,
) -> None:
    machine = SDK_LABS.get(lab_id)
    if machine is None:
        raise SdkToolingError("unknown SDK metadata lab")
    expected_file = (
        repo.resolve()
        / "meta-qemu-edu/recipes-support/qemu-edu-sdk-sample/"
        "qemu-edu-sdk-sample_1.0.bb"
    )
    try:
        selected_file = Path(recipe_file)
        exact_file = (
            not expected_file.is_symlink()
            and expected_file.is_file()
            and not selected_file.is_symlink()
            and selected_file.resolve(strict=True) == expected_file.resolve(strict=True)
        )
    except (OSError, RuntimeError):
        exact_file = False
    if (
        pn != SDK_RECIPE
        or pv != SDK_RECIPE_VERSION
        or license_expression != SDK_RECIPE_LICENSE
        or compatible_machine != SDK_COMPATIBLE_MACHINE
        or source_uri.split() != [SDK_SOURCE_URI]
        or not exact_file
        or machine not in compatible_machine
    ):
        raise SdkToolingError("effective SDK sample metadata is incompatible")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("source", help="verify locked source command interfaces")
    subparsers.add_parser("verify", help="verify source and executable interfaces")
    metadata = subparsers.add_parser("metadata", help="verify effective sample metadata")
    metadata.add_argument("--lab", required=True)
    metadata.add_argument("--pn", required=True)
    metadata.add_argument("--pv", required=True)
    metadata.add_argument("--license", required=True, dest="license_expression")
    metadata.add_argument("--compatible-machine", required=True)
    metadata.add_argument("--source-uri", required=True)
    metadata.add_argument("--recipe-file", required=True)
    args = parser.parse_args()
    try:
        if args.command == "source":
            verify_tooling(Path(args.repo), require_executables=False)
        elif args.command == "verify":
            verify_tooling(Path(args.repo))
        else:
            verify_recipe_metadata(
                Path(args.repo),
                args.lab,
                pn=args.pn,
                pv=args.pv,
                license_expression=args.license_expression,
                compatible_machine=args.compatible_machine,
                source_uri=args.source_uri,
                recipe_file=args.recipe_file,
            )
        print("sdk-tooling: PASS")
        return 0
    except (SdkToolingError, LockError, OSError) as exc:
        print(f"sdk-tooling: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
