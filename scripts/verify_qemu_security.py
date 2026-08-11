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
QEMU_MACHINE = "qemu-edu-x86-64"
PLATFORM_MACHINE = "qemu-edu-platform-arm64"
PCI_PROFILE = "qemu-edu-pci-v1"
PLATFORM_PROFILE = "qemu-edu-platform-v1"
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
PLATFORM_PATCH_NAME = "0002-hw-misc-add-qemu-edu-platform-device.patch"
PLATFORM_PATCH_RELATIVE = (
    Path("meta-qemu-edu/recipes-devtools/qemu/files") / PLATFORM_PATCH_NAME
)
MACHINE_RELATIVE = Path(f"meta-qemu-edu/conf/machine/{QEMU_MACHINE}.conf")
PLATFORM_MACHINE_RELATIVE = Path(
    f"meta-qemu-edu/conf/machine/{PLATFORM_MACHINE}.conf"
)
EXPECTED_APPEND_TEXT = f"""# SPDX-License-Identifier: MIT

QEMU_EDU_BACKPORT_FILESPATH := "${{THISDIR}}/files:"

python __anonymous() {{
    patches = {{
        "{QEMU_MACHINE}": "{PATCH_NAME}",
        "{PLATFORM_MACHINE}": "{PLATFORM_PATCH_NAME}",
    }}
    patch = patches.get(d.getVar("MACHINE"))
    if patch is None:
        return
    d.prependVar("FILESEXTRAPATHS", d.getVar("QEMU_EDU_BACKPORT_FILESPATH"))
    d.appendVar("SRC_URI", " file://" + patch)
}}
"""
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
PLATFORM_PATCH_SHA256 = (
    "8082f4b58ff3bc2d3d13c995859557477365b0ec0bd6390ec3f538993d039c5f"
)
PLATFORM_CHANGED_PATHS = (
    "hw/arm/Kconfig",
    "hw/arm/virt.c",
    "hw/core/sysbus-fdt.c",
    "hw/misc/Kconfig",
    "hw/misc/meson.build",
    "hw/misc/qemu_edu_platform.c",
    "include/hw/misc/qemu_edu_platform.h",
)
PLATFORM_SOURCE_SHA256 = {
    "hw/arm/Kconfig": "1f68966366b6e9c64715272300f1127847b3d522b2b71a8d919372ae50efdd77",
    "hw/arm/virt.c": "8b9df7be3429429b6b859881f03e1f5a4b69497c96b7d37eb2bba29d55bb4c87",
    "hw/core/sysbus-fdt.c": "99624863fa6fad8e0c26937a112bf08483c7cad22adf9c5a5b46adf6b5a091c7",
    "hw/misc/Kconfig": "7eeb70b27381fdb69e8aebb96fc2c97ab0e82bfc5aea68084ea20a4453d5f880",
    "hw/misc/meson.build": "4ec1ba3bbb53cdc5a884b9b3caf564583c74cd05c69ca53960b11c637f49ee05",
    "hw/misc/qemu_edu_platform.c": "d71a6a00acd9cd86c4bdd50fc56a9694e277a035a3cdd720a92b6471e4d878a0",
    "include/hw/misc/qemu_edu_platform.h": "29cf6e3f8a7ef2de68d57f8c363ec505e17170a3d1ada02eca17fc828b4f5b1f",
}
PROFILE_RULES = {
    PCI_PROFILE: {
        "machine": QEMU_MACHINE,
        "patch": PATCH_NAME,
        "binary": QEMU_BINARY,
    },
    PLATFORM_PROFILE: {
        "machine": PLATFORM_MACHINE,
        "patch": PLATFORM_PATCH_NAME,
        "binary": "qemu-system-aarch64",
    },
}


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


def verify_platform_patch(path: Path) -> str:
    text = read_text(path)
    changed = re.findall(
        r"(?m)^diff --git a/([^\s]+) b/([^\s]+)$", text
    )
    expected = [(item, item) for item in PLATFORM_CHANGED_PATHS]
    if changed != expected:
        raise VerificationError(
            f"platform patch paths differ; actual={changed}, expected={expected}"
        )
    if "GIT binary patch" in text or re.search(r"(?m)^Binary files ", text):
        raise VerificationError("platform patch must not contain binary changes")
    for token, label in (
        (
            "Upstream-Status: Inappropriate [oe specific]",
            "OpenEmbedded-specific upstream status",
        ),
        ('+#define TYPE_QEMU_EDU_PLATFORM "qemu-edu-platform"', "QOM type"),
        ('+                            "qemu,edu-platform");', "FDT compatible"),
        ("+                           GIC_FDT_IRQ_FLAGS_LEVEL_HI);", "level IRQ"),
        ("+    .parent = TYPE_DYNAMIC_SYS_BUS_DEVICE,", "dynamic SysBus parent"),
        (
            "+    machine_class_allow_dynamic_sysbus_dev(mc, "
            "TYPE_QEMU_EDU_PLATFORM);",
            "virt allowlist",
        ),
    ):
        require_once(text, token, label)
    patch_sha256 = canonical_text_digest(text)
    if patch_sha256 != PLATFORM_PATCH_SHA256:
        raise VerificationError(
            "platform patch differs from the reviewed normalized patch: "
            + patch_sha256
        )
    return patch_sha256


def static_checks(root: Path) -> dict[str, Any]:
    append_path = root / APPEND_RELATIVE
    patch_path = root / PATCH_RELATIVE
    platform_patch_path = root / PLATFORM_PATCH_RELATIVE
    machine_path = root / MACHINE_RELATIVE
    platform_machine_path = root / PLATFORM_MACHINE_RELATIVE
    for path in (
        append_path,
        patch_path,
        platform_patch_path,
        machine_path,
        platform_machine_path,
    ):
        if not path.is_file():
            raise VerificationError(f"required A007 input is missing: {path}")

    qemu_dir = append_path.parent
    matching_appends = sorted(qemu_dir.glob("qemu-system-native*.bbappend"))
    if matching_appends != [append_path]:
        rendered = ", ".join(path.name for path in matching_appends) or "none"
        raise VerificationError(
            "qemu-system-native must have one exact 10.2.0 append; found " + rendered
        )

    append_text = read_text(append_path).replace("\r\n", "\n").replace("\r", "\n")
    if append_text != EXPECTED_APPEND_TEXT:
        raise VerificationError(
            "qemu-system-native append must exactly match the reviewed "
            "machine-scoped backport integration"
        )

    machine_text = read_text(machine_path)
    require_once(
        machine_text,
        f'REQUIRED_VERSION_{QEMU_RECIPE} = "{QEMU_VERSION}"',
        "required QEMU recipe version",
    )
    require_once(
        read_text(platform_machine_path),
        f'REQUIRED_VERSION_{QEMU_RECIPE} = "{QEMU_VERSION}"',
        "ARM64 required QEMU recipe version",
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
    platform_patch_sha256 = verify_platform_patch(platform_patch_path)

    return {
        "schema_version": 1,
        "kind": "qemu-edu-emulator-security-check",
        "check": "static",
        "qemu_recipe": QEMU_RECIPE,
        "qemu_version": QEMU_VERSION,
        "qemu_machine": QEMU_MACHINE,
        "upstream_commit": UPSTREAM_COMMIT,
        "patch_sha256": patch_sha256,
        "platform_patch_sha256": platform_patch_sha256,
        "machine_scope_verified": True,
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
    profile: str = PCI_PROFILE,
) -> dict[str, Any]:
    result = static_checks(root)
    rule = PROFILE_RULES.get(profile)
    if rule is None:
        raise VerificationError(f"unknown QEMU preflight profile: {profile}")
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
    patch_token = f"file://{rule['patch']}"
    if src_uri.split().count(patch_token) != 1:
        raise VerificationError("effective SRC_URI must contain the selected patch once")
    unexpected = {
        f"file://{profile_rule['patch']}"
        for profile_name, profile_rule in PROFILE_RULES.items()
        if profile_name != profile
    }
    selected_uri = set(src_uri.split())
    if selected_uri & unexpected:
        raise VerificationError("effective SRC_URI contains another lab's QEMU patch")
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
            "profile": profile,
            "qemu_machine": rule["machine"],
            "selected": True,
            "testimage_dependency_verified": True,
        }
    )
    return result


def platform_source_checks(source_tree: Path) -> dict[str, Any]:
    for relative, expected in PLATFORM_SOURCE_SHA256.items():
        path = source_tree / relative
        actual = canonical_text_digest(read_text(path))
        if actual != expected:
            raise VerificationError(
                f"patched platform source differs at {relative}: {actual}"
            )
    device = read_text(source_tree / "hw/misc/qemu_edu_platform.c")
    for token in (
        "TYPE_QEMU_EDU_PLATFORM",
        "QEMU_EDU_PLATFORM_MMIO_SIZE",
        "QEMU_EDU_PLATFORM_IRQ_RAISE_REG",
        "QEMU_EDU_PLATFORM_IRQ_ACK_REG",
        "TYPE_DYNAMIC_SYS_BUS_DEVICE",
    ):
        if token not in device and token not in read_text(
            source_tree / "include/hw/misc/qemu_edu_platform.h"
        ):
            raise VerificationError(f"patched platform source omits {token}")
    if re.search(r"\bdma\b", device, re.IGNORECASE):
        raise VerificationError("platform teaching device must not expose DMA")
    return {
        "schema_version": 1,
        "kind": "qemu-edu-emulator-security-check",
        "check": "source",
        "profile": PLATFORM_PROFILE,
        "qemu_recipe": QEMU_RECIPE,
        "qemu_version": QEMU_VERSION,
        "source_group_sha256": PLATFORM_SOURCE_SHA256,
        "source_guard_verified": True,
    }


def source_checks(
    source_tree: Path, profile: str = PCI_PROFILE
) -> dict[str, Any]:
    if profile == PLATFORM_PROFILE:
        return platform_source_checks(source_tree)
    if profile != PCI_PROFILE:
        raise VerificationError(f"unknown QEMU preflight profile: {profile}")
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
        "profile": PCI_PROFILE,
        "qemu_recipe": QEMU_RECIPE,
        "qemu_version": QEMU_VERSION,
        "upstream_commit": UPSTREAM_COMMIT,
        "source_sha256": source_sha256,
        "source_guard_verified": True,
    }


def consumer_checks(
    staging_bindir_native: Path, profile: str = PCI_PROFILE
) -> dict[str, Any]:
    rule = PROFILE_RULES.get(profile)
    if rule is None:
        raise VerificationError(f"unknown QEMU preflight profile: {profile}")
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

    candidate = staging / rule["binary"]
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
        "profile": profile,
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
    details: list[str] = []
    if result.get("patch_sha256"):
        details.append(f"patch_sha256={result['patch_sha256']}")
    if result.get("platform_patch_sha256"):
        details.append(
            f"platform_patch_sha256={result['platform_patch_sha256']}"
        )
    if result.get("source_sha256"):
        details.append(f"source_sha256={result['source_sha256']}")
    if result.get("source_group_sha256"):
        details.append(f"source_files={len(result['source_group_sha256'])}")
    if result.get("qemu_binary_sha256"):
        details.extend(
            (
                f"qemu_binary={result['qemu_binary']}",
                f"qemu_binary_sha256={result['qemu_binary_sha256']}",
            )
        )
    detail = " " + " ".join(details) if details else ""
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
    metadata.add_argument(
        "--profile", choices=tuple(PROFILE_RULES), default=PCI_PROFILE
    )

    source = subparsers.add_parser(
        "source", help="verify both guards in a patched QEMU source tree"
    )
    source.add_argument("--source-tree", required=True)
    source.add_argument(
        "--profile", choices=tuple(PROFILE_RULES), default=PCI_PROFILE
    )
    consumer = subparsers.add_parser(
        "consumer", help="reject runqemu host fallback and verify its native emulator"
    )
    consumer.add_argument("--staging-bindir-native", required=True)
    consumer.add_argument(
        "--profile", choices=tuple(PROFILE_RULES), default=PCI_PROFILE
    )
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
                profile=args.profile,
            )
        elif args.command == "source":
            result = source_checks(Path(args.source_tree), args.profile)
        else:
            result = consumer_checks(Path(args.staging_bindir_native), args.profile)
        emit(result, args.format)
        return 0
    except VerificationError as exc:
        print(f"qemu-security: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
