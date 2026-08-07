#!/usr/bin/env bash
# SPDX-License-Identifier: MIT
set -eo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
LOCK_TOOL="$ROOT_DIR/scripts/source_lock.py"
CONFIGURE_TOOL="$ROOT_DIR/scripts/configure_build.py"
OFFLINE=false
CHECK_ONLY=false

usage() {
    cat <<'EOF'
Usage: ./setup.sh [--check] [--offline]

  --check    verify existing source checkouts without fetching or configuring
  --offline  configure using already-cached locked Git objects; never fetch
EOF
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --check) CHECK_ONLY=true ;;
        --offline) OFFLINE=true ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

command -v git >/dev/null || { echo "git is required" >&2; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

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

python3 "$CONFIGURE_TOOL" --repo "$ROOT_DIR" configure --build-dir "$BUILD_DIR"

ACTUAL_DISTRO=$(bitbake-getvar --value DISTRO)
ACTUAL_MACHINE=$(bitbake-getvar --value MACHINE)
ACTUAL_BBLAYERS=$(bitbake-getvar --value BBLAYERS)
python3 "$CONFIGURE_TOOL" --repo "$ROOT_DIR" verify \
    --distro "$ACTUAL_DISTRO" \
    --machine "$ACTUAL_MACHINE" \
    --bblayers "$ACTUAL_BBLAYERS"

bitbake-layers show-layers

echo
echo "Configuration complete."
echo "  Locked sources: $ROOT_DIR/config/sources.lock.json"
echo "  Build: $ROOT_DIR/build.sh"
echo "  Inspect metadata: $ROOT_DIR/inspect.sh"
echo "  Run after building: $ROOT_DIR/run.sh"
