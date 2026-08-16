#!/usr/bin/env bash
# Creates the Nomiflix data-directory skeleton on the VPS and sets
# ownership. Run once (as root or via sudo) before starting the watcher /
# upload service. Movies/ and Shows/ are created automatically by the
# pipeline as items are processed — nothing to pre-create there. These
# live directly under NOMIFLIX_ROOT (the repo root itself, already
# gitignored) rather than a nested data subdirectory — see docs/SPEC.md §2.
set -euo pipefail

NOMIFLIX_USER="${NOMIFLIX_USER:-nomikos}"
NOMIFLIX_ROOT="${NOMIFLIX_ROOT:-/opt/nomiflix}"

dirs=(
    "$NOMIFLIX_ROOT/_Inbox"
    "$NOMIFLIX_ROOT/_Processing"
    "$NOMIFLIX_ROOT/_Failed"
    "$NOMIFLIX_ROOT/logs"
)

for d in "${dirs[@]}"; do
    mkdir -p "$d"
    echo "created $d"
done

chown -R "$NOMIFLIX_USER:$NOMIFLIX_USER" "${dirs[@]}"
echo "ownership set to $NOMIFLIX_USER:$NOMIFLIX_USER"
