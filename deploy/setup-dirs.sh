#!/usr/bin/env bash
# Creates the Nomiflix data-directory skeleton on the VPS and sets
# ownership. Run once (as root or via sudo) before starting the watcher /
# upload service. Movies/ and Shows/ are NOT pre-created here — the
# pipeline creates them lazily (move_into_library.py) the first time an
# item is filed, directly as children of NOMIFLIX_ROOT (the repo root
# itself, already gitignored — see docs/SPEC.md §2). NOMIFLIX_ROOT itself,
# not just the subdirs below, gets chowned too: if the repo root ends up
# owned by someone other than NOMIFLIX_USER, that user's services can't
# create new top-level folders (Movies/, Shows/) in it at all. Everything
# here runs as root by default — this repo runs on a single-user VPS with
# no separate service account.
set -euo pipefail

NOMIFLIX_USER="${NOMIFLIX_USER:-root}"
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

chown -R "$NOMIFLIX_USER:$NOMIFLIX_USER" "$NOMIFLIX_ROOT"
echo "ownership set to $NOMIFLIX_USER:$NOMIFLIX_USER"
