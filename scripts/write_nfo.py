#!/usr/bin/env python3
# Builds a local Kodi/Jellyfin-style NFO file from the upload form's
# metadata (see docs/SPEC.md §3.1 for the field list, §6 for why this
# exists instead of TMDb scraping). Movies get a <movie> NFO; show
# episodes get an <episodedetails> NFO — Jellyfin's local-NFO reader picks
# either up automatically when named to match the video file.

import json
import os
import sys
import xml.etree.ElementTree as ET

TYPE_MOVIE = "movie"
TYPE_SHOW = "show"


class NfoError(Exception):
    """Expected, user-fixable failure (missing/invalid metadata field)."""


def nfo_path_for(video_path):
    return os.path.splitext(video_path)[0] + ".nfo"


def _require(metadata, key):
    value = metadata.get(key)
    if not value:
        raise NfoError(f"missing required metadata field: {key!r}")
    return value


def _to_xml_bytes(root):
    ET.indent(root)
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + ET.tostring(root, encoding="UTF-8")


def build_movie_nfo(metadata):
    title = _require(metadata, "title")
    year = _require(metadata, "year")
    genre = _require(metadata, "genre")

    root = ET.Element("movie")
    ET.SubElement(root, "title").text = title
    ET.SubElement(root, "year").text = str(year)
    ET.SubElement(root, "genre").text = genre

    return _to_xml_bytes(root)


def build_episode_nfo(metadata):
    title = _require(metadata, "title")
    season = _require(metadata, "season")
    episode = _require(metadata, "episode")
    genre = _require(metadata, "genre")

    root = ET.Element("episodedetails")
    ET.SubElement(root, "title").text = title
    ET.SubElement(root, "season").text = str(season)
    ET.SubElement(root, "episode").text = str(episode)
    ET.SubElement(root, "genre").text = genre

    return _to_xml_bytes(root)


def write_nfo(video_path, metadata):
    """Writes the NFO next to video_path (same basename, .nfo extension).
    Returns the path written."""
    item_type = metadata.get("type")
    if item_type == TYPE_MOVIE:
        content = build_movie_nfo(metadata)
    elif item_type == TYPE_SHOW:
        content = build_episode_nfo(metadata)
    else:
        raise NfoError(f"metadata 'type' must be {TYPE_MOVIE!r} or {TYPE_SHOW!r}, got {item_type!r}")

    path = nfo_path_for(video_path)
    with open(path, "wb") as f:
        f.write(content)
    return path


def main():
    if len(sys.argv) != 3:
        print("usage: write_nfo.py VIDEO_PATH METADATA_JSON_PATH", file=sys.stderr)
        return 1

    video_path, metadata_json_path = sys.argv[1], sys.argv[2]

    with open(metadata_json_path, encoding="utf-8") as f:
        metadata = json.load(f)

    try:
        path = write_nfo(video_path, metadata)
    except NfoError as exc:
        print(f"nfo error: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {path}")
    with open(path, encoding="utf-8") as f:
        print(f.read())
    return 0


if __name__ == "__main__":
    sys.exit(main())
