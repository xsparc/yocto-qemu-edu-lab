#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
set -eo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LAB_ID=${QEMU_EDU_LAB:-}

usage() {
    echo "Usage: ./runtime-test.sh [--lab LAB]" >&2
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --lab)
            [ "$#" -ge 2 ] || { echo "--lab requires a value" >&2; exit 2; }
            LAB_ID=$2
            shift
            ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    esac
    shift
done
if [ -n "$LAB_ID" ]; then
    QEMU_EDU_LAB=$LAB_ID
    export QEMU_EDU_LAB
fi

if ! command -v ssh >/dev/null 2>&1; then
    echo "runtime-test.sh requires an OpenSSH client (ssh) on the build host" >&2
    exit 1
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
    echo "runtime-test.sh requires exactly one locked image target" >&2
    exit 1
fi
TARGET=${TARGETS[0]}

bash "$QEMU_PREFLIGHT" "$ROOT_DIR" "$QEMU_EDU_LAB" "$TARGET"

EVIDENCE_FILENAME=$(
    python3 "$LAB_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" \
        get runtime.evidence_filename
)
EVIDENCE_PROFILE=$(
    python3 "$LAB_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" \
        get runtime.evidence_profile
)
case "$EVIDENCE_PROFILE" in
    pci-v3)
        EVIDENCE_TOOL="$ROOT_DIR/scripts/runtime_evidence.py"
        EVIDENCE_EXTRA_ARGS=()
        ;;
    platform-v1)
        EVIDENCE_TOOL="$ROOT_DIR/scripts/platform_runtime_evidence.py"
        EVIDENCE_EXTRA_ARGS=(--lab "$QEMU_EDU_LAB")
        ;;
    *)
        echo "Unsupported runtime evidence profile: $EVIDENCE_PROFILE" >&2
        exit 1
        ;;
esac
EVIDENCE_OUTPUT=${EVIDENCE_OUTPUT:-"$BUILD_DIR/evidence/$EVIDENCE_FILENAME"}
install -d "$BUILD_DIR/evidence"
OEQA_JSON_RESULT_DIR=$(mktemp -d "$BUILD_DIR/evidence/oeqa.XXXXXXXX")
export OEQA_JSON_RESULT_DIR
export BB_ENV_PASSTHROUGH_ADDITIONS="${BB_ENV_PASSTHROUGH_ADDITIONS:-} OEQA_JSON_RESULT_DIR"

bitbake "$TARGET"

test_status=0
bitbake "$TARGET" -c testimage || test_status=$?

evidence_status=0
python3 "$EVIDENCE_TOOL" --repo "$ROOT_DIR" collect \
    --oeqa "$OEQA_JSON_RESULT_DIR/testresults.json" \
    --output "$EVIDENCE_OUTPUT" \
    --machine "$MACHINE" \
    --image "$TARGET" \
    --testimage-exit-code "$test_status" \
    "${EVIDENCE_EXTRA_ARGS[@]}" || evidence_status=$?

if [ "$test_status" -ne 0 ]; then
    echo "testimage failed with status $test_status" >&2
    exit "$test_status"
fi
if [ "$evidence_status" -ne 0 ]; then
    exit "$evidence_status"
fi
python3 "$EVIDENCE_TOOL" validate "$EVIDENCE_OUTPUT" --require-pass
printf 'runtime evidence: %s\n' "$EVIDENCE_OUTPUT"
