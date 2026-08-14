#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LOCK_TOOL="$ROOT_DIR/scripts/source_lock.py"
LAB_TOOL="$ROOT_DIR/scripts/lab_config.py"
CONFIGURE_TOOL="$ROOT_DIR/scripts/configure_build.py"
OFFLINE=false
CHECK_ONLY=false
LAB_ID=${QEMU_EDU_LAB:-}

usage() {
    cat <<'EOF'
Usage: ./setup.sh [--lab LAB] [--check] [--offline]

  --lab LAB  select a declared lab; default: pci-x86-64
  --check    verify existing source checkouts without fetching or configuring
  --offline  configure using already-cached locked Git objects; never fetch
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --check) CHECK_ONLY=true ;;
        --offline) OFFLINE=true ;;
        --lab)
            [ "$#" -ge 2 ] || { echo "--lab requires a value" >&2; exit 2; }
            [ -n "$2" ] || { echo "--lab requires a non-empty value" >&2; exit 2; }
            LAB_ID=$2
            shift
            ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

if [ -n "$LAB_ID" ]; then
    QEMU_EDU_LAB=$(python3 "$LAB_TOOL" --repo "$ROOT_DIR" --lab "$LAB_ID" get id)
else
    QEMU_EDU_LAB=$(python3 "$LAB_TOOL" --repo "$ROOT_DIR" get id)
fi
export QEMU_EDU_LAB

if $CHECK_ONLY; then
    python3 "$LOCK_TOOL" --repo "$ROOT_DIR" status
    exit $?
fi

if $OFFLINE; then
    python3 "$LOCK_TOOL" --repo "$ROOT_DIR" sync --offline
else
    python3 "$LOCK_TOOL" --repo "$ROOT_DIR" sync
fi

# shellcheck source=environment.sh
source "$ROOT_DIR/environment.sh"

python3 "$CONFIGURE_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" \
    configure --build-dir "$BUILD_DIR"

ACTUAL_DISTRO=$(bitbake-getvar --value DISTRO)
ACTUAL_MACHINE=$(bitbake-getvar --value MACHINE)
ACTUAL_BBLAYERS=$(bitbake-getvar --value BBLAYERS)
python3 "$CONFIGURE_TOOL" --repo "$ROOT_DIR" --lab "$QEMU_EDU_LAB" verify \
    --distro "$ACTUAL_DISTRO" \
    --machine "$ACTUAL_MACHINE" \
    --bblayers "$ACTUAL_BBLAYERS"

bitbake-layers show-layers

echo
echo "Configuration complete."
echo "  Locked sources: $ROOT_DIR/config/sources.lock.json"
echo "  Lab: $QEMU_EDU_LAB"
printf '  Inspect metadata: BUILD_DIR=%q %q --lab %q\n' \
    "$BUILD_DIR" "$ROOT_DIR/inspect.sh" "$QEMU_EDU_LAB"
printf '  Build: BUILD_DIR=%q %q --lab %q\n' \
    "$BUILD_DIR" "$ROOT_DIR/build.sh" "$QEMU_EDU_LAB"
printf '  Run after building: BUILD_DIR=%q %q --lab %q\n' \
    "$BUILD_DIR" "$ROOT_DIR/run.sh" "$QEMU_EDU_LAB"
printf '  Runtime test: BUILD_DIR=%q %q --lab %q\n' \
    "$BUILD_DIR" "$ROOT_DIR/runtime-test.sh" "$QEMU_EDU_LAB"
