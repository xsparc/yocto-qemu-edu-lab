#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LAB_ID=${QEMU_EDU_LAB:-}

usage() {
    echo "Usage: ./run.sh [--lab LAB] [--] [runqemu arguments...]" >&2
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --lab)
            [ "$#" -ge 2 ] || { echo "--lab requires a value" >&2; exit 2; }
            LAB_ID=$2
            shift 2
            ;;
        --) shift; break ;;
        --help|-h) usage; exit 0 ;;
        *) break ;;
    esac
done
if [ -n "$LAB_ID" ]; then
    QEMU_EDU_LAB=$LAB_ID
    export QEMU_EDU_LAB
fi

# shellcheck source=environment.sh
source "$ROOT_DIR/environment.sh"
LAB_TOOL="$ROOT_DIR/scripts/lab_config.py"
QEMU_PREFLIGHT="$ROOT_DIR/scripts/qemu_security_preflight.sh"
MACHINE=$(python3 "$LAB_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" \
    get build.machine)
TARGET_TEXT=$(python3 "$LAB_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" \
    get build.targets --lines)
mapfile -t TARGETS <<<"$TARGET_TEXT"
if [ "${#TARGETS[@]}" -ne 1 ]; then
    echo "run.sh requires exactly one locked image target" >&2
    exit 1
fi

# Refuse stale or host-fallback QEMU before the public manual boot path.
bash "$QEMU_PREFLIGHT" "$ROOT_DIR" "$QEMU_EDU_LAB" "${TARGETS[0]}"

# slirp requires no root privileges; snapshot avoids modifying the built image.
runqemu "$MACHINE" "${TARGETS[0]}" ext4.zst nographic slirp snapshot "$@"
