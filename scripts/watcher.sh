#!/usr/bin/env bash
# Watches _Inbox/ for a complete video+metadata-sidecar (.json) pair, moves
# it into _Processing/, and hands it off to process_item.py. See
# docs/SPEC.md §3.2-3.3.
set -euo pipefail

LIBRARY_ROOT="${LIBRARY_ROOT:-/opt/nomiflix}"
INBOX="$LIBRARY_ROOT/_Inbox"
PROCESSING="$LIBRARY_ROOT/_Processing"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_DIR="/tmp/nomiflix-locks"

mkdir -p "$INBOX" "$PROCESSING" "$LOCK_DIR"

find_video() {
    local base="$1"
    find "$INBOX" -maxdepth 1 -name "$base.*" ! -name "$base.json" -print -quit
}

find_poster() {
    local base="$1"
    find "$INBOX" -maxdepth 1 -name "$base-poster.*" -print -quit
}

process_if_ready() {
    local base="$1"
    local json="$INBOX/$base.json"
    local video poster

    [[ -f "$json" ]] || return 0
    video="$(find_video "$base")"
    [[ -n "$video" ]] || return 0

    (
        # Serialize per base name: the video and json close_write events
        # can both fire for the same upload in quick succession.
        flock -n 9 || exit 0
        # Re-check after acquiring the lock — another invocation may have
        # already claimed and moved this pair.
        [[ -f "$json" ]] || exit 0
        video="$(find_video "$base")"
        [[ -n "$video" ]] || exit 0

        mv "$video" "$PROCESSING/$(basename "$video")"
        mv "$json" "$PROCESSING/$base.json"
        # Poster is optional — the upload form may not always send one.
        poster="$(find_poster "$base")"
        [[ -n "$poster" ]] && mv "$poster" "$PROCESSING/$(basename "$poster")"

        echo "nomiflix: processing $base"
        if python3 "$SCRIPT_DIR/process_item.py" "$LIBRARY_ROOT" "$base"; then
            echo "nomiflix: finished $base"
        else
            echo "nomiflix: FAILED $base (see $LIBRARY_ROOT/_Failed/$base.log)" >&2
        fi
    ) 9>"$LOCK_DIR/$base.lock"
}

echo "nomiflix: starting inbox watcher on $INBOX"

# Catch any complete uploads that landed while the watcher wasn't running.
for json in "$INBOX"/*.json; do
    [[ -e "$json" ]] || continue
    process_if_ready "$(basename "$json" .json)"
done

inotifywait -m -e close_write -e moved_to --format '%f' "$INBOX" | while read -r fname; do
    case "$fname" in
        *.json)
            process_if_ready "${fname%.json}"
            ;;
        *)
            process_if_ready "${fname%.*}"
            ;;
    esac
done
