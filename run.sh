#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# shellcheck source=environment.sh
source "$ROOT_DIR/environment.sh"
LOCK_TOOL="$ROOT_DIR/scripts/source_lock.py"
MACHINE=$(python3 "$LOCK_TOOL" --repo "$ROOT_DIR" get build.machine)
TARGET_TEXT=$(python3 "$LOCK_TOOL" --repo "$ROOT_DIR" get build.targets --lines)
mapfile -t TARGETS <<<"$TARGET_TEXT"
if [ "${#TARGETS[@]}" -ne 1 ]; then
    echo "run.sh requires exactly one locked image target" >&2
    exit 1
fi

# slirp requires no root privileges; snapshot avoids modifying the built image.
runqemu "$MACHINE" "${TARGETS[0]}" ext4.zst nographic slirp snapshot "$@"
