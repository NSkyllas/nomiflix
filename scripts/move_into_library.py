#!/usr/bin/env python3
# Builds the Jellyfin-convention destination path from upload metadata and
# moves the (already transcoded, or already-compliant) video into place.
# See docs/SPEC.md §4 for the naming convention this implements.

import json
import os
import re
import shutil
import sys

from write_nfo import TYPE_MOVIE, TYPE_SHOW

BAD_CHARS_RE = re.compile(r'[\/\\:*?"<>|]')


class MoveError(Exception):
    """Expected, user-fixable failure (bad metadata, destination already exists, ...)."""


def sanitize(name):
    return BAD_CHARS_RE.sub("-", name).strip()


def build_movie_path(library_root, metadata, ext):
    title = sanitize(metadata["title"])
    year = metadata["year"]
    folder = f"{title} ({year})"
    return os.path.join(library_root, "Movies", folder, f"{folder}{ext}")


def build_episode_path(library_root, metadata, ext):
    show = sanitize(metadata["title"])
    season_num = int(metadata["season"])
    episode_num = int(metadata["episode"])
    filename = f"{show} S{season_num:02d}E{episode_num:02d}{ext}"
    return os.path.join(library_root, "Shows", show, f"Season {season_num:02d}", filename)


def build_destination_path(library_root, metadata, ext):
    item_type = metadata.get("type")
    if item_type == TYPE_MOVIE:
        return build_movie_path(library_root, metadata, ext)
    elif item_type == TYPE_SHOW:
        return build_episode_path(library_root, metadata, ext)
    raise MoveError(f"metadata 'type' must be {TYPE_MOVIE!r} or {TYPE_SHOW!r}, got {item_type!r}")


def move_into_library(video_path, metadata, library_root):
    """Moves video_path into its Jellyfin-convention destination under
    library_root. Raises MoveError (without moving anything) if the
    destination already exists — never silently overwrite an existing
    library item (see CLAUDE.md hard constraint #3)."""
    ext = os.path.splitext(video_path)[1]
    dest = build_destination_path(library_root, metadata, ext)

    if os.path.exists(dest):
        raise MoveError(f"destination already exists, refusing to overwrite: {dest!r}")

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.move(video_path, dest)
    return dest


def main():
    if len(sys.argv) != 4:
        print("usage: move_into_library.py VIDEO_PATH METADATA_JSON_PATH LIBRARY_ROOT", file=sys.stderr)
        return 1

    video_path, metadata_json_path, library_root = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(metadata_json_path, encoding="utf-8") as f:
        metadata = json.load(f)

    try:
        dest = move_into_library(video_path, metadata, library_root)
    except MoveError as exc:
        print(f"move error: {exc}", file=sys.stderr)
        return 1

    print(f"moved to {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
