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

bitbake qemu-edu-image
