#!/usr/bin/env python3
# Orchestrates one _Processing/ video+metadata-sidecar pair end to end:
# probe, transcode (if needed), move into the library, write its NFO. On
# any expected failure, moves the original untouched to _Failed/ and logs
# why — never silently loses a source file (CLAUDE.md hard constraint #3).
# See docs/SPEC.md §3.3. Invoked by watcher.py once it has moved a
# complete pair from _Inbox/ into _Processing/.

import glob
import json
import os
import shutil
import sys
import tempfile
import traceback
from datetime import datetime

from move_into_library import MoveError, move_into_library
from parse_credits import CreditsParseError, parse_credits
from probe import BRANCH_SKIP, ProbeError, probe
from transcode import TranscodeError, transcode
from write_nfo import NfoError, write_nfo

ExpectedError = (ProbeError, TranscodeError, MoveError, NfoError, CreditsParseError)


def find_video_file(processing, base):
    candidates = [
        p for p in glob.glob(os.path.join(processing, base + ".*"))
        if not p.endswith(".json")
    ]
    return candidates[0] if len(candidates) == 1 else None


def find_poster_file(processing, base):
    # Named "{base}-poster.<ext>", not "{base}.<ext>" — the latter would
    # make find_video_file() see two non-json candidates and give up.
    candidates = glob.glob(os.path.join(processing, base + "-poster.*"))
    return candidates[0] if candidates else None


def find_credits_file(processing, base):
    path = os.path.join(processing, base + "-credits.txt")
    return path if os.path.isfile(path) else None


def log_outcome(library_root, message):
    logs_dir = os.path.join(library_root, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    timestamp = datetime.now().isoformat(timespec="seconds")
    with open(os.path.join(logs_dir, "watcher.log"), "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def move_to_failed(library_root, paths, base, reason):
    failed_dir = os.path.join(library_root, "_Failed")
    os.makedirs(failed_dir, exist_ok=True)
    for src in paths:
        if not src or not os.path.exists(src):
            continue
        shutil.move(src, os.path.join(failed_dir, os.path.basename(src)))
    with open(os.path.join(failed_dir, f"{base}.log"), "w", encoding="utf-8") as f:
        f.write(reason + "\n")
    log_outcome(library_root, f"{base}: FAILED — {reason.splitlines()[0]}")


def process_item(video_path, metadata_path, poster_path, credits_path, library_root):
    """Returns (dest_path, branch). Raises ExpectedError on any
    user-fixable failure; never touches video_path/metadata_path/
    poster_path/credits_path on failure — the caller is responsible for
    routing them to _Failed/."""
    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)

    # Parsed first, before any transcode/move work — a bad credits paste
    # should fail fast and leave nothing half-done, not burn a long
    # transcode only to fail afterward.
    credits = None
    if credits_path:
        with open(credits_path, encoding="utf-8") as f:
            credits = parse_credits(f.read())

    probe_result = probe(video_path)

    if probe_result["branch"] == BRANCH_SKIP:
        final_source = video_path
    else:
        fd, staged_path = tempfile.mkstemp(
            suffix=os.path.splitext(video_path)[1], dir=os.path.dirname(video_path)
        )
        os.close(fd)
        os.remove(staged_path)  # transcode() creates it fresh; this just reserves a unique name
        transcode(video_path, staged_path, probe_result)
        final_source = staged_path

    dest = move_into_library(final_source, metadata, library_root)

    if final_source != video_path:
        # Transcode succeeded and its output is now in the library — the
        # pre-transcode original is redundant, delete per hard constraint #3.
        os.remove(video_path)

    if poster_path:
        # Same basename-suffix convention as the NFO — Jellyfin/Kodi both
        # recognize "<video basename>-poster.<ext>" as local artwork.
        poster_dest = os.path.splitext(dest)[0] + "-poster" + os.path.splitext(poster_path)[1]
        shutil.move(poster_path, poster_dest)

    if credits_path:
        # The structured JSON is the durable artifact — the raw paste is
        # redundant once successfully parsed (same "success renders the
        # original disposable" pattern as the pre-transcode video above).
        credits_dest = os.path.splitext(dest)[0] + "-credits.json"
        with open(credits_dest, "w", encoding="utf-8") as f:
            json.dump(credits, f, indent=2, ensure_ascii=False)
        os.remove(credits_path)

    write_nfo(dest, metadata, credits)
    return dest, probe_result["branch"]


def main():
    if len(sys.argv) != 3:
        print("usage: process_item.py LIBRARY_ROOT BASE", file=sys.stderr)
        return 1

    library_root, base = sys.argv[1], sys.argv[2]
    processing = os.path.join(library_root, "_Processing")
    video_path = find_video_file(processing, base)
    metadata_path = os.path.join(processing, base + ".json")
    poster_path = find_poster_file(processing, base)
    credits_path = find_credits_file(processing, base)

    if not video_path or not os.path.isfile(metadata_path):
        return 0  # not a complete pair (yet) — already handled or not ready

    try:
        dest, branch = process_item(video_path, metadata_path, poster_path, credits_path, library_root)
    except ExpectedError as exc:
        move_to_failed(library_root, [video_path, metadata_path, poster_path, credits_path], base, str(exc))
        return 1
    except Exception:
        move_to_failed(
            library_root, [video_path, metadata_path, poster_path, credits_path], base,
            f"unexpected error:\n{traceback.format_exc()}",
        )
        return 1

    os.remove(metadata_path)
    log_outcome(library_root, f"{base}: OK ({branch}) -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
