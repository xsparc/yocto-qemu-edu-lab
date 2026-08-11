#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LAB_ID=${QEMU_EDU_LAB:-}

usage() {
    echo "Usage: ./build.sh [--lab LAB]" >&2
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --lab)
            [ "$#" -ge 2 ] || { echo "--lab requires a value" >&2; exit 2; }
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
TARGET_TEXT=$(python3 "$ROOT_DIR/scripts/lab_config.py" --repo "$ROOT_DIR" \
    --lab "$QEMU_EDU_LAB" get build.targets --lines)
mapfile -t TARGETS <<<"$TARGET_TEXT"
bitbake "${TARGETS[@]}"
