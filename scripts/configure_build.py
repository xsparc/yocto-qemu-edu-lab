#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Reconcile and verify the generated OpenEmbedded build configuration."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lab_config import DEFAULT_INDEX, LabError, select_lab  # noqa: E402
from source_lock import LockError, locked_path  # noqa: E402


START = "# BEGIN yocto-qemu-edu-lab"
END = "# END yocto-qemu-edu-lab"
AUTOMATIC_BUILD_CONFIGURATION = (
    "site.conf",
    "auto.conf",
    "toolcfg.conf",
    "bblock.conf",
)
SDK_CONFIGURATION_ROOT = ".qemu-edu-config"
MAX_SDK_CONFIGURATION_BYTES = 64 * 1024


class ConfigurationError(ValueError):
    """The generated build configuration is unsafe or inconsistent."""


def ensure_supported_path(path: Path, label: str) -> None:
    if any(character.isspace() for character in str(path)):
        raise ConfigurationError(f"{label} must not contain whitespace: {path}")


def expected_layers(root: Path, data: dict[str, Any]) -> list[str]:
    return [str(locked_path(root, relative)) for relative in data["build"]["layers"]]


def sdk_configuration_root(root: Path, data: dict[str, Any]) -> Path:
    return root / data["development"]["build_dir"] / SDK_CONFIGURATION_ROOT


def render_bblayers(
    root: Path,
    data: dict[str, Any],
    *,
    include_build_root: bool = True,
) -> str:
    lines = [
        "# Managed by yocto-qemu-edu-lab; edit the selected lab manifest instead.",
        'POKY_BBLAYERS_CONF_VERSION = "2"',
        (
            'BBPATH = "${TOPDIR}"'
            if include_build_root
            else f'BBPATH = "{sdk_configuration_root(root, data)}"'
        ),
        'BBFILES ?= ""',
        'BBLAYERS = " \\',
    ]
    lines.extend(f"  {layer} \\" for layer in expected_layers(root, data))
    lines.append('"')
    return "\n".join(lines) + "\n"


def render_local_conf(text: str, data: dict[str, Any]) -> str:
    start_count = text.count(START)
    end_count = text.count(END)
    markers_absent = start_count == 0 and end_count == 0
    markers_ordered = (
        start_count == 1
        and end_count == 1
        and text.index(START) < text.index(END)
    )
    if not (markers_absent or markers_ordered):
        raise ConfigurationError(
            "local.conf has an invalid managed block; use a fresh BUILD_DIR"
        )
    block = f'''{START}
DISTRO = "{data["build"]["distro"]}"
MACHINE = "{data["build"]["machine"]}"

# Keep reusable downloads and shared-state output outside tmp/.
DL_DIR ?= "${{TOPDIR}}/../downloads"
SSTATE_DIR ?= "${{TOPDIR}}/../sstate-cache"

# Development convenience only; remove this from a production image.
EXTRA_IMAGE_FEATURES += "allow-empty-password allow-root-login empty-root-password post-install-logging"
{END}'''
    if START in text:
        before = text.split(START, 1)[0].rstrip()
        after = text.split(END, 1)[1].strip()
        text = before
        if after:
            text += "\n\n" + after
        return text + "\n\n" + block + "\n"
    return text.rstrip() + "\n\n" + block + "\n"


def render_sdk_local_conf(data: dict[str, Any]) -> str:
    """Return the complete local.conf used by the closed SDK profile."""
    return render_local_conf('CONF_VERSION = "2"\n', data)


def render_sdk_bblayers(
    root: Path,
    data: dict[str, Any],
    *,
    workspace: Path | None = None,
) -> str:
    """Return the complete SDK layer list, optionally with its exact workspace."""
    text = render_bblayers(root, data, include_build_root=False)
    if workspace is None:
        return text
    marker = '"\n'
    if not text.endswith(marker):
        raise ConfigurationError("generated layer configuration is inconsistent")
    return text[: -len(marker)] + f"  {workspace} \\\n" + marker


def _write_atomic(path: Path, text: str) -> None:
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{path.name}-",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _prepare_sdk_configuration_root(path: Path, *, create: bool = False) -> None:
    """Create or accept only the closed directory shape used on SDK BBPATH."""
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ConfigurationError("SDK configuration root is unsafe")
    if not path.exists():
        if not create:
            raise ConfigurationError("SDK configuration root is unavailable")
        path.mkdir()
    if path.resolve(strict=True) != path:
        raise ConfigurationError("SDK configuration root escapes the build root")
    entries = list(path.iterdir())
    conf_dir = path / "conf"
    if any(entry.name != "conf" or entry.is_symlink() for entry in entries):
        raise ConfigurationError("SDK configuration root contains unexpected state")
    if conf_dir.exists():
        if conf_dir.is_symlink() or not conf_dir.is_dir():
            raise ConfigurationError("SDK configuration root is unsafe")
    else:
        if not create:
            raise ConfigurationError("SDK configuration root is unavailable")
        conf_dir.mkdir()
    if conf_dir.resolve(strict=True) != conf_dir:
        raise ConfigurationError("SDK configuration root escapes the build root")
    local_path = conf_dir / "local.conf"
    conf_entries = list(conf_dir.iterdir())
    if any(entry != local_path or entry.is_symlink() for entry in conf_entries):
        raise ConfigurationError("SDK configuration root contains unexpected state")
    if local_path.exists() and not local_path.is_file():
        raise ConfigurationError("SDK configuration root is unsafe")


def verify_sdk_configuration_root(path: Path, local_text: str) -> None:
    """Authenticate the only SDK BBPATH entry before a parser can consume it."""
    _prepare_sdk_configuration_root(path)
    local_path = path / "conf/local.conf"
    try:
        with local_path.open("rb") as handle:
            raw = handle.read(MAX_SDK_CONFIGURATION_BYTES + 1)
    except OSError as exc:
        raise ConfigurationError("SDK configuration root is unavailable") from exc
    if len(raw) > MAX_SDK_CONFIGURATION_BYTES:
        raise ConfigurationError("SDK configuration root exceeds its byte bound")
    try:
        actual = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ConfigurationError("SDK configuration root is invalid") from exc
    if actual != local_text:
        raise ConfigurationError("SDK configuration root is not authoritative")


def configure_sdk(
    root: Path,
    build_dir: Path,
    data: dict[str, Any],
    *,
    workspace: Path | None = None,
) -> None:
    """Replace all automatically parsed SDK configuration with a closed form."""
    root = root.resolve()
    build_dir = build_dir.resolve()
    ensure_supported_path(root, "repository path")
    ensure_supported_path(build_dir, "build path")
    expected_build = root / data["development"]["build_dir"]
    if build_dir != expected_build:
        raise ConfigurationError("SDK build directory differs from the lab contract")
    conf_dir = build_dir / "conf"
    if conf_dir.is_symlink() or not conf_dir.is_dir():
        raise ConfigurationError("SDK configuration directory is unavailable")
    if conf_dir.resolve(strict=True) != conf_dir:
        raise ConfigurationError("SDK configuration directory escapes the build root")
    for name in AUTOMATIC_BUILD_CONFIGURATION:
        forbidden = conf_dir / name
        if forbidden.exists() or forbidden.is_symlink():
            raise ConfigurationError(
                f"SDK configuration contains automatically parsed {forbidden.name}"
            )
    for path in (conf_dir / "local.conf", conf_dir / "bblayers.conf"):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ConfigurationError("SDK configuration path is unsafe")
        if path.exists() and path.resolve(strict=True) != path:
            raise ConfigurationError("SDK configuration escapes the build root")
    if workspace is not None:
        workspace = workspace.resolve()
        if workspace.parent != build_dir:
            raise ConfigurationError("SDK workspace differs from the closed build root")
    local_text = render_sdk_local_conf(data)
    configuration_root = sdk_configuration_root(root, data)
    _prepare_sdk_configuration_root(configuration_root, create=True)
    _write_atomic(configuration_root / "conf/local.conf", local_text)
    verify_sdk_configuration_root(configuration_root, local_text)
    _write_atomic(conf_dir / "local.conf", local_text)
    _write_atomic(
        conf_dir / "bblayers.conf",
        render_sdk_bblayers(root, data, workspace=workspace),
    )


def configure(root: Path, build_dir: Path, data: dict[str, Any]) -> None:
    root = root.resolve()
    build_dir = build_dir.resolve()
    ensure_supported_path(root, "repository path")
    ensure_supported_path(build_dir, "build path")
    conf_dir = build_dir / "conf"
    local_path = conf_dir / "local.conf"
    bblayers_path = conf_dir / "bblayers.conf"
    if not local_path.is_file():
        raise ConfigurationError(f"OpenEmbedded did not create {local_path}")

    local_text = render_local_conf(local_path.read_text(encoding="utf-8"), data)
    bblayers_text = render_bblayers(root, data)
    bblayers_path.write_text(bblayers_text, encoding="utf-8", newline="\n")
    local_path.write_text(local_text, encoding="utf-8", newline="\n")


def effective_errors(
    root: Path,
    data: dict[str, Any],
    *,
    distro: str,
    machine: str,
    bblayers: str,
) -> list[str]:
    errors: list[str] = []
    if distro != data["build"]["distro"]:
        errors.append(
            f"DISTRO resolved to {distro!r}, expected {data['build']['distro']!r}"
        )
    if machine != data["build"]["machine"]:
        errors.append(
            f"MACHINE resolved to {machine!r}, expected {data['build']['machine']!r}"
        )
    actual_layers = bblayers.split()
    locked_layers = expected_layers(root.resolve(), data)
    if actual_layers != locked_layers:
        errors.append(
            "BBLAYERS differs from the locked order:\n"
            f"  actual:   {actual_layers}\n"
            f"  expected: {locked_layers}"
        )
    return errors


def sdk_effective_errors(
    root: Path,
    data: dict[str, Any],
    *,
    build_dir: Path,
    distro: str,
    machine: str,
    bblayers: str,
    bbpath: str,
) -> list[str]:
    errors = effective_errors(
        root,
        data,
        distro=distro,
        machine=machine,
        bblayers=bblayers,
    )
    expected_build = root / data["development"]["build_dir"]
    if build_dir != expected_build:
        errors.append("SDK build directory differs from the lab contract")
    entries = bbpath.split(os.pathsep)
    configuration_root = str(sdk_configuration_root(root, data))
    allowed = {configuration_root, *expected_layers(root, data)}
    if entries.count(configuration_root) != 1:
        errors.append("SDK BBPATH must contain the closed configuration root exactly once")
    if any(not entry for entry in entries):
        errors.append("SDK BBPATH contains an empty search component")
    if any(entry == str(expected_build) for entry in entries):
        errors.append("SDK BBPATH exposes the disposable build root")
    if any(entry not in allowed for entry in entries):
        errors.append("SDK BBPATH contains an undeclared search component")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--index", default=DEFAULT_INDEX, help="lab index under repository")
    parser.add_argument("--lab", help="lab id; defaults to the index default")
    subparsers = parser.add_subparsers(dest="command", required=True)
    configure_parser = subparsers.add_parser("configure", help="write locked build configuration")
    configure_parser.add_argument("--build-dir", required=True)
    configure_sdk_parser = subparsers.add_parser(
        "configure-sdk",
        help="write the closed direct-eSDK build configuration",
    )
    configure_sdk_parser.add_argument("--build-dir", required=True)
    verify_parser = subparsers.add_parser("verify", help="compare effective BitBake values")
    verify_parser.add_argument("--distro", required=True)
    verify_parser.add_argument("--machine", required=True)
    verify_parser.add_argument("--bblayers", required=True)
    verify_sdk_parser = subparsers.add_parser(
        "verify-sdk",
        help="compare effective direct-eSDK BitBake values",
    )
    verify_sdk_parser.add_argument("--build-dir", required=True)
    verify_sdk_parser.add_argument("--distro", required=True)
    verify_sdk_parser.add_argument("--machine", required=True)
    verify_sdk_parser.add_argument("--bblayers", required=True)
    verify_sdk_parser.add_argument("--bbpath", required=True)
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    try:
        selected, data, _, _ = select_lab(root, args.lab, args.index)
        if args.command == "configure":
            configure(root, Path(args.build_dir), data)
            print(f"build-config: reconciled ({selected})")
            return 0
        if args.command == "configure-sdk":
            configure_sdk(root, Path(args.build_dir), data)
            print(f"build-config: SDK reconciled ({selected})")
            return 0
        if args.command == "verify-sdk":
            errors = sdk_effective_errors(
                root,
                data,
                build_dir=Path(args.build_dir).resolve(),
                distro=args.distro,
                machine=args.machine,
                bblayers=args.bblayers,
                bbpath=args.bbpath,
            )
            if errors:
                raise ConfigurationError("\n".join(errors))
            print(f"build-config: SDK PASS ({selected})")
            return 0
        errors = effective_errors(
            root,
            data,
            distro=args.distro,
            machine=args.machine,
            bblayers=args.bblayers,
        )
        if errors:
            raise ConfigurationError(
                "\n".join(errors) + "\nUse a fresh BUILD_DIR for custom configuration."
            )
        print(f"build-config: PASS ({selected})")
        return 0
    except (ConfigurationError, LabError, LockError, OSError) as exc:
        print(f"build-config: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
