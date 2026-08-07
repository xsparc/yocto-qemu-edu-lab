#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# shellcheck source=environment.sh
source "$ROOT_DIR/environment.sh"
TARGET_TEXT=$(python3 "$ROOT_DIR/scripts/source_lock.py" --repo "$ROOT_DIR" \
    get build.targets --lines)
mapfile -t TARGETS <<<"$TARGET_TEXT"

echo "== Layers =="
bitbake-layers show-layers

echo
echo "== Recipes supplied by this lab =="
bitbake-layers show-recipes 'qemu-edu-*'

echo
echo "== Key expanded values =="
bitbake -e "${TARGETS[0]}" | \
    grep -E '^(MACHINE|MACHINEOVERRIDES|QB_CPU|QB_OPT_APPEND|MACHINE_ESSENTIAL_EXTRA_RDEPENDS|IMAGE_INSTALL)='
