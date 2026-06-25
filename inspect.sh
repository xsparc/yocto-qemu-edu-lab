#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if [ ! -f "$ROOT_DIR/poky/oe-init-build-env" ]; then
    echo "Run ./setup.sh first." >&2
    exit 1
fi

set +u
source "$ROOT_DIR/poky/oe-init-build-env" "$ROOT_DIR/build" >/dev/null
set -u

echo "== Layers =="
bitbake-layers show-layers

echo
echo "== Recipes supplied by this lab =="
bitbake-layers show-recipes 'qemu-edu-*'

echo
echo "== Key expanded values =="
bitbake -e qemu-edu-image | \
    grep -E '^(MACHINE|MACHINEOVERRIDES|QB_CPU|QB_OPT_APPEND|MACHINE_ESSENTIAL_EXTRA_RDEPENDS|IMAGE_INSTALL)='
