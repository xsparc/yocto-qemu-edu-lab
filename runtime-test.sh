#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Yocto QEMU EDU learning project contributors
# SPDX-License-Identifier: MIT
set -eo pipefail
ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

if ! command -v ssh >/dev/null 2>&1; then
    echo "runtime-test.sh requires an OpenSSH client (ssh) on the build host" >&2
    exit 1
fi

# shellcheck source=environment.sh
source "$ROOT_DIR/environment.sh"
LOCK_TOOL="$ROOT_DIR/scripts/source_lock.py"
CONFIGURE_TOOL="$ROOT_DIR/scripts/configure_build.py"
EVIDENCE_TOOL="$ROOT_DIR/scripts/runtime_evidence.py"
MACHINE=$(python3 "$LOCK_TOOL" --repo "$ROOT_DIR" get build.machine)
TARGET_TEXT=$(python3 "$LOCK_TOOL" --repo "$ROOT_DIR" get build.targets --lines)
mapfile -t TARGETS <<<"$TARGET_TEXT"
if [ "${#TARGETS[@]}" -ne 1 ]; then
    echo "runtime-test.sh requires exactly one locked image target" >&2
    exit 1
fi
TARGET=${TARGETS[0]}

ACTUAL_DISTRO=$(bitbake-getvar --value DISTRO)
ACTUAL_MACHINE=$(bitbake-getvar --value MACHINE)
ACTUAL_BBLAYERS=$(bitbake-getvar --value BBLAYERS)
python3 "$CONFIGURE_TOOL" --repo "$ROOT_DIR" verify \
    --distro "$ACTUAL_DISTRO" \
    --machine "$ACTUAL_MACHINE" \
    --bblayers "$ACTUAL_BBLAYERS"

EVIDENCE_OUTPUT=${EVIDENCE_OUTPUT:-"$BUILD_DIR/evidence/qemu-edu-runtime-v2.json"}
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
    --testimage-exit-code "$test_status" || evidence_status=$?

if [ "$test_status" -ne 0 ]; then
    echo "testimage failed with status $test_status" >&2
    exit "$test_status"
fi
if [ "$evidence_status" -ne 0 ]; then
    exit "$evidence_status"
fi
python3 "$EVIDENCE_TOOL" validate "$EVIDENCE_OUTPUT" --require-pass
printf 'runtime evidence: %s\n' "$EVIDENCE_OUTPUT"
