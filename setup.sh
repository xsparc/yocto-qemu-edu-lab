#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
POKY_DIR=${POKY_DIR:-"$ROOT_DIR/poky"}
BUILD_DIR=${BUILD_DIR:-"$ROOT_DIR/build"}
YOCTO_BRANCH=${YOCTO_BRANCH:-wrynose}

command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

if [ ! -d "$POKY_DIR/.git" ]; then
    echo "Cloning Poky branch '$YOCTO_BRANCH'..."
    git clone --branch "$YOCTO_BRANCH" --single-branch \
        https://git.yoctoproject.org/poky "$POKY_DIR"
else
    echo "Using existing Poky checkout: $POKY_DIR"
fi

# Yocto's setup script is not written for nounset shells.
set +u
source "$POKY_DIR/oe-init-build-env" "$BUILD_DIR" >/dev/null
set -u

if ! bitbake-layers show-layers 2>/dev/null | grep -Fq "$ROOT_DIR/meta-qemu-edu"; then
    bitbake-layers add-layer "$ROOT_DIR/meta-qemu-edu"
fi

LOCAL_CONF="$BUILD_DIR/conf/local.conf"
export LOCAL_CONF
python3 <<'PY'
import os
from pathlib import Path

path = Path(os.environ["LOCAL_CONF"])
text = path.read_text()
start = "# BEGIN yocto-qemu-edu-lab"
end = "# END yocto-qemu-edu-lab"
block = f'''{start}
MACHINE = "qemu-edu-x86-64"

# Keep reusable downloads and shared-state output outside tmp/.
DL_DIR ?= "${{TOPDIR}}/../downloads"
SSTATE_DIR ?= "${{TOPDIR}}/../sstate-cache"

# Development convenience only; remove this from a production image.
EXTRA_IMAGE_FEATURES += "debug-tweaks"
{end}'''

if start in text and end in text:
    before = text.split(start, 1)[0].rstrip()
    after = text.split(end, 1)[1].lstrip("\n")
    text = before + "\n\n" + block + "\n"
    if after:
        text += "\n" + after
else:
    text = text.rstrip() + "\n\n" + block + "\n"
path.write_text(text)
PY

echo
echo "Configuration complete."
echo "  Build: $ROOT_DIR/build.sh"
echo "  Inspect metadata: $ROOT_DIR/inspect.sh"
echo "  Run after building: $ROOT_DIR/run.sh"
