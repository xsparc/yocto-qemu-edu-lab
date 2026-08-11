#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
set -eo pipefail

if [ "$#" -ne 3 ]; then
    echo "usage: qemu_security_preflight.sh REPOSITORY_ROOT LAB IMAGE_TARGET" >&2
    exit 2
fi

ROOT_DIR=$1
LAB_ID=$2
TARGET=$3
CONFIGURE_TOOL="$ROOT_DIR/scripts/configure_build.py"
QEMU_SECURITY_TOOL="$ROOT_DIR/scripts/verify_qemu_security.py"
LAB_TOOL="$ROOT_DIR/scripts/lab_config.py"
PROFILE=$(python3 "$LAB_TOOL" --repo "$ROOT_DIR" --lab "$LAB_ID" \
    get emulator.preflight_profile)

ACTUAL_DISTRO=$(bitbake-getvar --value DISTRO)
ACTUAL_MACHINE=$(bitbake-getvar --value MACHINE)
ACTUAL_BBLAYERS=$(bitbake-getvar --value BBLAYERS)
python3 "$CONFIGURE_TOOL" --repo "$ROOT_DIR" --lab "$LAB_ID" verify \
    --distro "$ACTUAL_DISTRO" \
    --machine "$ACTUAL_MACHINE" \
    --bblayers "$ACTUAL_BBLAYERS"

QEMU_SHOW_APPENDS=$(mktemp)
trap 'rm -f "$QEMU_SHOW_APPENDS"' EXIT
bitbake-layers show-appends qemu-system-native >"$QEMU_SHOW_APPENDS"
QEMU_PN=$(bitbake-getvar --value --recipe qemu-system-native PN)
QEMU_PV=$(bitbake-getvar --value --recipe qemu-system-native PV)
QEMU_FILE=$(bitbake-getvar --value --recipe qemu-system-native FILE)
QEMU_SRC_URI=$(bitbake-getvar --value --recipe qemu-system-native SRC_URI)
TESTIMAGE_DEPENDS=$(bitbake-getvar --value --recipe "$TARGET" TESTIMAGEDEPENDS)
HELPER_DEPENDS=$(bitbake-getvar --value --recipe qemu-helper-native DEPENDS)
python3 "$QEMU_SECURITY_TOOL" --repo "$ROOT_DIR" metadata \
    --show-appends "$QEMU_SHOW_APPENDS" \
    --pn "$QEMU_PN" \
    --pv "$QEMU_PV" \
    --recipe-file "$QEMU_FILE" \
    --src-uri "$QEMU_SRC_URI" \
    --testimage-depends "$TESTIMAGE_DEPENDS" \
    --helper-depends "$HELPER_DEPENDS" \
    --profile "$PROFILE"

bitbake qemu-system-native -c patch
QEMU_SOURCE=$(bitbake-getvar --value --recipe qemu-system-native S)
python3 "$QEMU_SECURITY_TOOL" source --source-tree "$QEMU_SOURCE" \
    --profile "$PROFILE"
bitbake qemu-system-native -c populate_sysroot

# This is runqemu's exact native consumer sysroot. Populating and checking it
# prevents runqemu from silently falling back to a host QEMU on PATH.
bitbake qemu-helper-native -c addto_recipe_sysroot
STAGING_BINDIR_NATIVE=$(
    bitbake-getvar --value --recipe qemu-helper-native STAGING_BINDIR_NATIVE
)
python3 "$QEMU_SECURITY_TOOL" consumer \
    --staging-bindir-native "$STAGING_BINDIR_NATIVE" \
    --profile "$PROFILE"
