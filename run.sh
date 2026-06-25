#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if [ ! -f "$ROOT_DIR/poky/oe-init-build-env" ]; then
    echo "Run ./setup.sh and ./build.sh first." >&2
    exit 1
fi

set +u
source "$ROOT_DIR/poky/oe-init-build-env" "$ROOT_DIR/build" >/dev/null
set -u

# slirp requires no root privileges; snapshot avoids modifying the built image.
runqemu qemu-edu-x86-64 qemu-edu-image ext4.zst nographic slirp snapshot "$@"
