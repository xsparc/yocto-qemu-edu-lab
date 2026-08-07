#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Reconcile and verify the generated OpenEmbedded build configuration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from source_lock import DEFAULT_LOCK, LockError, locked_path, read_lock  # noqa: E402


START = "# BEGIN yocto-qemu-edu-lab"
END = "# END yocto-qemu-edu-lab"


class ConfigurationError(ValueError):
    """The generated build configuration is unsafe or inconsistent."""


def ensure_supported_path(path: Path, label: str) -> None:
    if any(character.isspace() for character in str(path)):
        raise ConfigurationError(f"{label} must not contain whitespace: {path}")


def expected_layers(root: Path, data: dict[str, Any]) -> list[str]:
    return [str(locked_path(root, relative)) for relative in data["build"]["layers"]]


def render_bblayers(root: Path, data: dict[str, Any]) -> str:
    lines = [
        "# Managed by yocto-qemu-edu-lab; edit config/sources.lock.json instead.",
        'POKY_BBLAYERS_CONF_VERSION = "2"',
        'BBPATH = "${TOPDIR}"',
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--lock", default=DEFAULT_LOCK, help="lock path under repository")
    subparsers = parser.add_subparsers(dest="command", required=True)
    configure_parser = subparsers.add_parser("configure", help="write locked build configuration")
    configure_parser.add_argument("--build-dir", required=True)
    verify_parser = subparsers.add_parser("verify", help="compare effective BitBake values")
    verify_parser.add_argument("--distro", required=True)
    verify_parser.add_argument("--machine", required=True)
    verify_parser.add_argument("--bblayers", required=True)
    args = parser.parse_args()

    root = Path(args.repo).resolve()
    try:
        data, _ = read_lock(locked_path(root, args.lock))
        if args.command == "configure":
            configure(root, Path(args.build_dir), data)
            print("build-config: reconciled")
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
        print("build-config: PASS")
        return 0
    except (ConfigurationError, LockError, OSError) as exc:
        print(f"build-config: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
