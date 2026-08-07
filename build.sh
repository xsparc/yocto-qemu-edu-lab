#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# shellcheck source=environment.sh
source "$ROOT_DIR/environment.sh"
TARGET_TEXT=$(python3 "$ROOT_DIR/scripts/source_lock.py" --repo "$ROOT_DIR" \
    get build.targets --lines)
mapfile -t TARGETS <<<"$TARGET_TEXT"
bitbake "${TARGETS[@]}"
