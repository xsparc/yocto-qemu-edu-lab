#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
"""Verify the QEMU EDU host-emulator security backport and its build selection."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


QEMU_RECIPE = "qemu-system-native"
QEMU_VERSION = "10.2.0"
UPSTREAM_COMMIT = "42f599172ae023924f288e20af0ceed681674747"
UPSTREAM_URL = (
    "https://gitlab.com/qemu-project/qemu/-/commit/"
    f"{UPSTREAM_COMMIT}"
)
APPEND_RELATIVE = Path(
    "meta-qemu-edu/recipes-devtools/qemu/qemu-system-native_10.2.0.bbappend"
)
PATCH_NAME = "0001-hw-misc-edu-restrict-dma-access-to-dma-buffer.patch"
PATCH_RELATIVE = Path("meta-qemu-edu/recipes-devtools/qemu/files") / PATCH_NAME
MACHINE_RELATIVE = Path("meta-qemu-edu/conf/machine/qemu-edu-x86-64.conf")
EXPECTED_RECIPE_SUFFIX = (
    "/layers/openembedded-core/meta/recipes-devtools/qemu/"
    "qemu-system-native_10.2.0.bb"
)
TESTIMAGE_HELPER_TASKS = {
    "qemu-helper-native:do_populate_sysroot",
    "qemu-helper-native:do_addto_recipe_sysroot",
}
EXPECTED_PATCH_SHA256 = (
    "73689608fcf9d8826ca95a105562c9962c79f207fb11a65e1a7451ab6085a72c"
)
EXPECTED_EDU_SOURCE_SHA256 = (
    "32e2a035df36c25410d843e902cb4057aa43e83c047f682589d6f8539036ca2a"
)
QEMU_BINARY = "qemu-system-x86_64"


class VerificationError(ValueError):
    """Raised when an expected security invariant is absent or ambiguous."""


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise VerificationError(f"cannot read {path}: {exc}") from exc


def require_once(text: str, token: str, label: str) -> None:
    count = text.count(token)
    if count != 1:
        raise VerificationError(f"{label} must occur exactly once, found {count}")


def digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise VerificationError(f"cannot hash {path}: {exc}") from exc


def canonical_text_digest(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def require_guarded_copy(source: str, endpoint: str, function: str) -> None:
    guard = re.compile(
        rf"if\s*\(\s*edu_check_range\(\s*{endpoint}\s*,\s*edu->dma\.cnt\s*,"
        rf"\s*DMA_START\s*,\s*DMA_SIZE\s*\)\s*\)\s*\{{(?P<body>[^{{}}]*)\}}",
        re.DOTALL,
    )
    matches = list(guard.finditer(source))
    if len(matches) != 1:
        raise VerificationError(
            f"patched EDU {endpoint} guard must occur exactly once, found {len(matches)}"
        )
    body = matches[0].group("body")
    if not re.search(rf"\b{function}\s*\(", body):
        raise VerificationError(
            f"{function} must remain inside the validated {endpoint} guard"
        )


def static_checks(root: Path) -> dict[str, Any]:
    append_path = root / APPEND_RELATIVE
    patch_path = root / PATCH_RELATIVE
    machine_path = root / MACHINE_RELATIVE
    for path in (append_path, patch_path, machine_path):
        if not path.is_file():
            raise VerificationError(f"required A007 input is missing: {path}")

    qemu_dir = append_path.parent
    matching_appends = sorted(qemu_dir.glob("qemu-system-native*.bbappend"))
    if matching_appends != [append_path]:
        rendered = ", ".join(path.name for path in matching_appends) or "none"
        raise VerificationError(
            "qemu-system-native must have one exact 10.2.0 append; found " + rendered
        )

    append_text = read_text(append_path)
    require_once(
        append_text,
        'FILESEXTRAPATHS:prepend := "${THISDIR}/files:"',
        "exact file search path",
    )
    require_once(
        append_text,
        f'SRC_URI:append = " file://{PATCH_NAME}"',
        "backport SRC_URI entry",
    )

    machine_text = read_text(machine_path)
    require_once(
        machine_text,
        f'REQUIRED_VERSION_{QEMU_RECIPE} = "{QEMU_VERSION}"',
        "required QEMU recipe version",
    )

    patch_text = read_text(patch_path)
    for token, label in (
        (f"From {UPSTREAM_COMMIT} ", "upstream commit header"),
        ("From: Torin Carey <torin@tcarey.uk>", "upstream author"),
        (
            f"Upstream-Status: Backport [{UPSTREAM_URL}]",
            "Yocto upstream status",
        ),
        (
            "+static bool edu_check_range(uint64_t xfer_start, uint64_t xfer_size,",
            "boolean range helper",
        ),
        (
            "+        if (edu_check_range(dst, edu->dma.cnt, DMA_START, DMA_SIZE)) {",
            "guest-to-device-buffer guard",
        ),
        (
            "+        if (edu_check_range(src, edu->dma.cnt, DMA_START, DMA_SIZE)) {",
            "device-buffer-to-guest guard",
        ),
    ):
        require_once(patch_text, token, label)
    require_once(
        patch_text,
        "diff --git a/hw/misc/edu.c b/hw/misc/edu.c",
        "EDU source diff",
    )
    if patch_text.count("diff --git ") != 1:
        raise VerificationError("backport must change exactly one file")
    if "GIT binary patch" in patch_text or re.search(r"(?m)^Binary files ", patch_text):
        raise VerificationError("backport must not contain binary changes")
    patch_sha256 = canonical_text_digest(patch_text)
    if patch_sha256 != EXPECTED_PATCH_SHA256:
        raise VerificationError(
            "backport differs from the reviewed normalized patch: " + patch_sha256
        )

    return {
        "schema_version": 1,
        "kind": "qemu-edu-emulator-security-check",
        "check": "static",
        "qemu_recipe": QEMU_RECIPE,
        "qemu_version": QEMU_VERSION,
        "upstream_commit": UPSTREAM_COMMIT,
        "patch_sha256": patch_sha256,
        "selected": False,
        "source_guard_verified": False,
    }


def metadata_checks(
    *,
    root: Path,
    show_appends: str,
    pn: str,
    pv: str,
    recipe_file: str,
    src_uri: str,
    testimage_depends: str,
    helper_depends: str,
) -> dict[str, Any]:
    result = static_checks(root)
    normalized_appends = show_appends.replace("\\", "/")
    append_suffix = "/" + APPEND_RELATIVE.as_posix()
    if normalized_appends.count(append_suffix) != 1:
        raise VerificationError(
            "show-appends must select the project qemu-system-native append once"
        )
    selected_appends = [
        line.strip()
        for line in normalized_appends.splitlines()
        if line.strip().endswith(".bbappend")
    ]
    if len(selected_appends) != 1 or not selected_appends[0].endswith(append_suffix):
        raise VerificationError(
            "qemu-system-native has an unexpected additional bbappend"
        )
    if pn.strip() != QEMU_RECIPE:
        raise VerificationError(f"unexpected QEMU PN: {pn.strip()!r}")
    if pv.strip() != QEMU_VERSION:
        raise VerificationError(f"unexpected QEMU PV: {pv.strip()!r}")
    normalized_recipe = recipe_file.strip().replace("\\", "/")
    if not normalized_recipe.endswith(EXPECTED_RECIPE_SUFFIX):
        raise VerificationError(
            "qemu-system-native FILE is not the exact locked OE-Core 10.2.0 recipe"
        )
    patch_token = f"file://{PATCH_NAME}"
    if src_uri.split().count(patch_token) != 1:
        raise VerificationError("effective SRC_URI must contain the backport once")
    missing_helper_tasks = TESTIMAGE_HELPER_TASKS - set(testimage_depends.split())
    if missing_helper_tasks:
        raise VerificationError(
            "testimage dependency chain omits: " + ", ".join(sorted(missing_helper_tasks))
        )
    if QEMU_RECIPE not in helper_depends.split():
        raise VerificationError(
            "qemu-helper-native does not depend on qemu-system-native"
        )

    result.update(
        {
            "check": "metadata",
            "selected": True,
            "testimage_dependency_verified": True,
        }
    )
    return result


def source_checks(source_tree: Path) -> dict[str, Any]:
    source_path = source_tree / "hw/misc/edu.c"
    source = read_text(source_path)
    if not re.search(r"static\s+bool\s+edu_check_range\s*\(", source):
        raise VerificationError("patched EDU range helper is not boolean")
    require_guarded_copy(source, "dst", "pci_dma_read")
    require_guarded_copy(source, "src", "pci_dma_write")
    if "return true;" not in source or "return false;" not in source:
        raise VerificationError("patched EDU range helper does not fail closed")
    source_sha256 = canonical_text_digest(source)
    if source_sha256 != EXPECTED_EDU_SOURCE_SHA256:
        raise VerificationError(
            "patched EDU source differs from the reviewed QEMU 10.2.0 result: "
            + source_sha256
        )

    return {
        "schema_version": 1,
        "kind": "qemu-edu-emulator-security-check",
        "check": "source",
        "qemu_recipe": QEMU_RECIPE,
        "qemu_version": QEMU_VERSION,
        "upstream_commit": UPSTREAM_COMMIT,
        "source_sha256": source_sha256,
        "source_guard_verified": True,
    }


def consumer_checks(staging_bindir_native: Path) -> dict[str, Any]:
    if not staging_bindir_native.is_absolute():
        raise VerificationError("STAGING_BINDIR_NATIVE must be an absolute path")
    try:
        staging = staging_bindir_native.resolve(strict=True)
    except OSError as exc:
        raise VerificationError(
            f"native staging directory is unavailable: {staging_bindir_native}: {exc}"
        ) from exc
    if not staging.is_dir():
        raise VerificationError(f"native staging path is not a directory: {staging}")

    candidate = staging / QEMU_BINARY
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise VerificationError(
            f"patched native emulator is unavailable (host fallback prohibited): {candidate}"
        ) from exc
    try:
        resolved.relative_to(staging)
    except ValueError as exc:
        raise VerificationError(
            f"native emulator resolves outside STAGING_BINDIR_NATIVE: {resolved}"
        ) from exc
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise VerificationError(f"native emulator is not an executable file: {resolved}")

    return {
        "schema_version": 1,
        "kind": "qemu-edu-emulator-security-check",
        "check": "consumer",
        "qemu_recipe": QEMU_RECIPE,
        "qemu_version": QEMU_VERSION,
        "upstream_commit": UPSTREAM_COMMIT,
        "qemu_binary": str(resolved),
        "qemu_binary_sha256": digest(resolved),
        "runqemu_consumer_verified": True,
    }


def emit(result: dict[str, Any], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps(result, sort_keys=True))
        return
    detail = ""
    if result.get("patch_sha256"):
        detail = f" patch_sha256={result['patch_sha256']}"
    if result.get("source_sha256"):
        detail = f" source_sha256={result['source_sha256']}"
    if result.get("qemu_binary_sha256"):
        detail = (
            f" qemu_binary={result['qemu_binary']}"
            f" qemu_binary_sha256={result['qemu_binary_sha256']}"
        )
    print(f"qemu-security: PASS: {result['check']}{detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository root")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("static", help="verify committed recipe and patch inputs")

    metadata = subparsers.add_parser(
        "metadata", help="verify effective BitBake recipe and dependency selection"
    )
    metadata.add_argument("--show-appends", required=True)
    metadata.add_argument("--pn", required=True)
    metadata.add_argument("--pv", required=True)
    metadata.add_argument("--recipe-file", required=True)
    metadata.add_argument("--src-uri", required=True)
    metadata.add_argument("--testimage-depends", required=True)
    metadata.add_argument("--helper-depends", required=True)

    source = subparsers.add_parser(
        "source", help="verify both guards in a patched QEMU source tree"
    )
    source.add_argument("--source-tree", required=True)
    consumer = subparsers.add_parser(
        "consumer", help="reject runqemu host fallback and verify its native emulator"
    )
    consumer.add_argument("--staging-bindir-native", required=True)
    args = parser.parse_args()

    try:
        if args.command == "static":
            result = static_checks(Path(args.repo).resolve())
        elif args.command == "metadata":
            result = metadata_checks(
                root=Path(args.repo).resolve(),
                show_appends=read_text(Path(args.show_appends)),
                pn=args.pn,
                pv=args.pv,
                recipe_file=args.recipe_file,
                src_uri=args.src_uri,
                testimage_depends=args.testimage_depends,
                helper_depends=args.helper_depends,
            )
        elif args.command == "source":
            result = source_checks(Path(args.source_tree))
        else:
            result = consumer_checks(Path(args.staging_bindir_native))
        emit(result, args.format)
        return 0
    except VerificationError as exc:
        print(f"qemu-security: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
