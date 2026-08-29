#!/bin/bash -p
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
set -eo pipefail

LAB_ID=${QEMU_EDU_LAB:-}

usage() {
    echo "Usage: ./sdk-test.sh [--lab LAB]" >&2
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --lab)
            [ "$#" -ge 2 ] || { echo "--lab requires a value" >&2; exit 2; }
            [ -n "$2" ] || { echo "--lab requires a non-empty value" >&2; exit 2; }
            LAB_ID=$2
            shift
            ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
    shift
done

# The direct-eSDK entrypoint owns environment initialization. Do not let a
# caller redirect OE internals, Python imports, Git object/config state, or
# BitBake passthrough before the locked environment and controller can verify
# their authority.
unset \
    BASH_ENV BDIR BBEXTRA BBPATH BBPATH_EXTRA BITBAKEDIR BUILDDIR CDPATH ENV \
    GIT_ALTERNATE_OBJECT_DIRECTORIES GIT_COMMON_DIR GIT_CONFIG \
    GIT_CONFIG_COUNT GIT_CONFIG_GLOBAL GIT_CONFIG_PARAMETERS GIT_CONFIG_SYSTEM \
    GIT_DIR GIT_INDEX_FILE GIT_NAMESPACE GIT_OBJECT_DIRECTORY \
    GIT_REPLACE_REF_BASE GIT_WORK_TREE OE_ADDED_PATHS OEROOT TEMPLATECONF \
    BB_ENV_EXTRAWHITE BB_ENV_PASSTHROUGH_ADDITIONS \
    PYTHONBREAKPOINT PYTHONCASEOK PYTHONHOME PYTHONINSPECT PYTHONPATH \
    PYTHONSAFEPATH PYTHONSTARTUP PYTHONUSERBASE PYTHONWARNINGS
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1

SCRIPT_DIR=${BASH_SOURCE[0]%/*}
if [ "$SCRIPT_DIR" = "${BASH_SOURCE[0]}" ]; then
    SCRIPT_DIR=.
fi
ROOT_DIR=$(CDPATH='' builtin cd -- "$SCRIPT_DIR" && builtin pwd -P)
unset SCRIPT_DIR
LAB_TOOL="$ROOT_DIR/scripts/lab_config.py"
ITERATION_TOOL="$ROOT_DIR/scripts/sdk_iteration.py"

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
NATIVE_GIT=$(type -P git) || { echo "sdk-test.sh requires native Git" >&2; exit 1; }
case "$NATIVE_GIT" in
    /*) ;;
    *) echo "sdk-test.sh requires native Git at an absolute path" >&2; exit 1 ;;
esac
NATIVE_GIT_DIR=${NATIVE_GIT%/*}
case "$NATIVE_GIT_DIR" in
    ""|*:) echo "sdk-test.sh resolved an unsafe native Git path" >&2; exit 1 ;;
esac
command -v ssh >/dev/null || { echo "sdk-test.sh requires an OpenSSH client" >&2; exit 1; }
command -v scp >/dev/null || { echo "sdk-test.sh requires OpenSSH scp" >&2; exit 1; }

if [ -n "$LAB_ID" ]; then
    QEMU_EDU_LAB=$(python3 "$LAB_TOOL" --repo "$ROOT_DIR" --lab "$LAB_ID" get id)
else
    QEMU_EDU_LAB=$(python3 "$LAB_TOOL" --repo "$ROOT_DIR" get id)
fi
export QEMU_EDU_LAB
SDK_BUILD_DIR=$(
    python3 "$LAB_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" \
        get development.build_dir
)
BUILD_DIR="$ROOT_DIR/$SDK_BUILD_DIR"
export BUILD_DIR

python3 "$ITERATION_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" \
    --build-dir "$BUILD_DIR" preflight-path

# shellcheck source=environment.sh
source "$ROOT_DIR/environment.sh"

# OE-Core prepends a scripts/git helper. Preserve the already resolved host Git
# directory ahead of that helper; the controller revalidates the selected file.
PATH="$NATIVE_GIT_DIR:$PATH"
export PATH
unset NATIVE_GIT NATIVE_GIT_DIR

# OE prepends its locked BitBake library to the inherited value. The Python
# controller reconstructs the one verified path for every build-facing child.
unset PYTHONPATH

python3 "$ITERATION_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" \
    --build-dir "$BUILD_DIR" run
