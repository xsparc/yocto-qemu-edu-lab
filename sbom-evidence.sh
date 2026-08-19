#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
set -eo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LAB_ID=${QEMU_EDU_LAB:-}

usage() {
    echo "Usage: ./sbom-evidence.sh [--lab LAB]" >&2
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --lab)
            [ "$#" -ge 2 ] || { echo "--lab requires a value" >&2; exit 2; }
            [ -n "$2" ] || { echo "--lab requires a non-empty value" >&2; exit 2; }
            LAB_ID=$2
            shift
            ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
    shift
done
if [ -n "$LAB_ID" ]; then
    QEMU_EDU_LAB=$LAB_ID
    export QEMU_EDU_LAB
fi

# shellcheck source=environment.sh
source "$ROOT_DIR/environment.sh"
LAB_TOOL="$ROOT_DIR/scripts/lab_config.py"
EVIDENCE_TOOL="$ROOT_DIR/scripts/sbom_evidence.py"
CONFIGURE_TOOL="$ROOT_DIR/scripts/configure_build.py"
TARGET_TEXT=$(python3 "$LAB_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" \
    get build.targets --lines)
mapfile -t TARGETS <<<"$TARGET_TEXT"
if [ "${#TARGETS[@]}" -ne 1 ]; then
    echo "sbom-evidence.sh requires exactly one locked image target" >&2
    exit 1
fi
TARGET=${TARGETS[0]}

ACTUAL_DISTRO=$(bitbake-getvar --value DISTRO)
ACTUAL_MACHINE=$(bitbake-getvar --value MACHINE)
ACTUAL_BBLAYERS=$(bitbake-getvar --value BBLAYERS)
python3 "$CONFIGURE_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" verify \
    --distro "$ACTUAL_DISTRO" \
    --machine "$ACTUAL_MACHINE" \
    --bblayers "$ACTUAL_BBLAYERS"

SETTING_NAMES=(
    SPDX_IMAGE_SUPPLIER_name
    SPDX_INCLUDE_BITBAKE_PARENT_BUILD
    SPDX_INCLUDE_BUILD_VARIABLES
    SPDX_INCLUDE_COMPILED_SOURCES
    SPDX_INCLUDE_KERNEL_CONFIG
    SPDX_INCLUDE_PACKAGECONFIG
    SPDX_INCLUDE_SOURCES
    SPDX_INCLUDE_TIMESTAMPS
    SPDX_INCLUDE_VEX
    SPDX_PACKAGE_SUPPLIER_name
    SPDX_PRETTY
    SPDX_PROFILES
    SPDX_VERSION
)
SETTING_ARGS=()
for setting_name in "${SETTING_NAMES[@]}"; do
    setting_value=$(bitbake-getvar --value --recipe "$TARGET" "$setting_name")
    SETTING_ARGS+=(--setting "$setting_name=$setting_value")
done

python3 "$EVIDENCE_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" \
    --build-dir "$BUILD_DIR" \
    preflight "${SETTING_ARGS[@]}"
EVIDENCE_OUTPUT=$(
    python3 "$EVIDENCE_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" \
        --build-dir "$BUILD_DIR" path
)
rm -f -- "$EVIDENCE_OUTPUT"

task_status=0
bitbake "$TARGET" -c create_image_sbom_spdx || task_status=$?
if [ "$task_status" -ne 0 ]; then
    echo "create_image_sbom_spdx failed with status $task_status" >&2
    exit "$task_status"
fi

DEPLOY_DIR_IMAGE=$(bitbake-getvar --value --recipe "$TARGET" DEPLOY_DIR_IMAGE)
IMAGE_LINK_NAME=$(bitbake-getvar --value --recipe "$TARGET" IMAGE_LINK_NAME)
if [ -z "$DEPLOY_DIR_IMAGE" ] || [ -z "$IMAGE_LINK_NAME" ]; then
    echo "BitBake did not resolve the image SPDX deployment identity" >&2
    exit 1
fi

python3 "$EVIDENCE_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" \
    --build-dir "$BUILD_DIR" collect \
    --deploy-dir "$DEPLOY_DIR_IMAGE" \
    --image-link-name "$IMAGE_LINK_NAME" \
    --task-exit-code "$task_status" \
    "${SETTING_ARGS[@]}"
REVISION=$(git -C "$ROOT_DIR" rev-parse --verify HEAD)
python3 "$EVIDENCE_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" validate \
    "$EVIDENCE_OUTPUT" \
    --require-pass \
    --require-revision "$REVISION" \
    --require-current-inputs
printf 'SPDX image evidence: %s\n' "$EVIDENCE_OUTPUT"
