#!/usr/bin/env bash
# SPDX-License-Identifier: MIT

# Source this file to enter the exact OpenEmbedded environment from the lock.
QEMU_EDU_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
QEMU_EDU_LOCK_TOOL="$QEMU_EDU_ROOT/scripts/source_lock.py"
QEMU_EDU_LAB_TOOL="$QEMU_EDU_ROOT/scripts/lab_config.py"

if ! command -v python3 >/dev/null; then
    echo "python3 is required" >&2
    return 1 2>/dev/null || exit 1
fi
if ! python3 "$QEMU_EDU_LOCK_TOOL" --repo "$QEMU_EDU_ROOT" status >/dev/null; then
    echo "Run ./setup.sh to materialize the locked Yocto sources." >&2
    return 1 2>/dev/null || exit 1
fi

if [ -n "${QEMU_EDU_LAB:-}" ]; then
    if QEMU_EDU_SELECTED_LAB=$(
        python3 "$QEMU_EDU_LAB_TOOL" --repo "$QEMU_EDU_ROOT" \
            --lab "$QEMU_EDU_LAB" get id
    ); then
        :
    else
        echo "The requested lab is not declared by config/labs/index.json." >&2
        unset QEMU_EDU_SELECTED_LAB
        return 1 2>/dev/null || exit 1
    fi
else
    if QEMU_EDU_SELECTED_LAB=$(
        python3 "$QEMU_EDU_LAB_TOOL" --repo "$QEMU_EDU_ROOT" get id
    ); then
        :
    else
        echo "The lab catalog is invalid." >&2
        unset QEMU_EDU_SELECTED_LAB
        return 1 2>/dev/null || exit 1
    fi
fi
QEMU_EDU_LAB=$QEMU_EDU_SELECTED_LAB
export QEMU_EDU_LAB
unset QEMU_EDU_SELECTED_LAB

QEMU_EDU_ENVIRONMENT=$(
    python3 "$QEMU_EDU_LOCK_TOOL" --repo "$QEMU_EDU_ROOT" \
        get build.environment_script
)
QEMU_EDU_BITBAKE_BIN=$(
    python3 "$QEMU_EDU_LOCK_TOOL" --repo "$QEMU_EDU_ROOT" get build.bitbake_bin
)
QEMU_EDU_DEFAULT_BUILD=$(
    python3 "$QEMU_EDU_LAB_TOOL" --repo "$QEMU_EDU_ROOT" \
        --lab "$QEMU_EDU_LAB" get build.build_dir
)
BUILD_DIR=${BUILD_DIR:-"$QEMU_EDU_ROOT/$QEMU_EDU_DEFAULT_BUILD"}
case ":$PATH:" in
    *":$QEMU_EDU_ROOT/$QEMU_EDU_BITBAKE_BIN:"*) ;;
    *) export PATH="$QEMU_EDU_ROOT/$QEMU_EDU_BITBAKE_BIN:$PATH" ;;
esac

# Yocto's setup script is not written for nounset shells.
if [[ $- == *u* ]]; then
    QEMU_EDU_RESTORE_NOUNSET=true
else
    QEMU_EDU_RESTORE_NOUNSET=false
fi
set +u
# The validated lock owns this dynamic source path.
# shellcheck disable=SC1090
if source "$QEMU_EDU_ROOT/$QEMU_EDU_ENVIRONMENT" "$BUILD_DIR" >/dev/null; then
    QEMU_EDU_ENV_STATUS=0
else
    QEMU_EDU_ENV_STATUS=$?
fi
if $QEMU_EDU_RESTORE_NOUNSET; then
    set -u
fi
unset QEMU_EDU_RESTORE_NOUNSET
if [ "$QEMU_EDU_ENV_STATUS" -ne 0 ]; then
    echo "Failed to initialize the locked OpenEmbedded environment." >&2
    return "$QEMU_EDU_ENV_STATUS" 2>/dev/null || exit "$QEMU_EDU_ENV_STATUS"
fi
unset QEMU_EDU_ENV_STATUS

# oe-init-build-env resolves the requested directory before changing cwd.
# Keep the public override stable for callers that supplied a relative path.
if [ -z "${BUILDDIR:-}" ]; then
    echo "The locked OpenEmbedded environment did not set BUILDDIR." >&2
    return 1 2>/dev/null || exit 1
fi
BUILD_DIR=$BUILDDIR
export BUILD_DIR
