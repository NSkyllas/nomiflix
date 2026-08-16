#!/usr/bin/env python3
# Wraps ffprobe to read a video's codec/resolution info and decide which of
# the three ingest branches (scale / codec_only / skip) applies. See
# docs/SPEC.md §3.3 step 3-4 for the branch table this implements.

import json
import subprocess
import sys

BRANCH_SCALE = "scale"        # height > 1080p: scale down + re-encode
BRANCH_CODEC_ONLY = "codec_only"  # height <= 1080p, wrong codec/audio: re-encode, no scaling
BRANCH_SKIP = "skip"          # height <= 1080p, already H.264/AAC: just move

TARGET_VIDEO_CODEC = "h264"
TARGET_AUDIO_CODEC = "aac"
SCALE_THRESHOLD_HEIGHT = 1080


class ProbeError(Exception):
    """Expected, user-fixable failure (corrupt file, no video stream, ffprobe missing, ...)."""


def _run_ffprobe(video_path):
    cmd = [
        "ffprobe", "-v", "error",
        "-print_format", "json",
        "-show_format", "-show_streams",
        video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ProbeError(f"ffprobe failed: {result.stderr.strip()[-500:]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError(f"ffprobe returned unparseable output: {exc}")


def _first_video_stream(streams):
    for s in streams:
        # Cover art embedded as a "video" stream (disposition.attached_pic)
        # isn't the actual video track — skip it so it's never mistaken for one.
        if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic"):
            return s
    return None


def _first_audio_stream(streams):
    for s in streams:
        if s.get("codec_type") == "audio":
            return s
    return None


def decide_branch(height, video_codec, audio_codec):
    if height > SCALE_THRESHOLD_HEIGHT:
        return BRANCH_SCALE
    already_compliant = video_codec == TARGET_VIDEO_CODEC and audio_codec == TARGET_AUDIO_CODEC
    return BRANCH_SKIP if already_compliant else BRANCH_CODEC_ONLY


def probe(video_path):
    """Returns a dict: video_codec, audio_codec, height, container, branch.
    audio_codec is None if the file has no audio stream at all."""
    data = _run_ffprobe(video_path)

    streams = data.get("streams", [])
    video_stream = _first_video_stream(streams)
    if video_stream is None:
        raise ProbeError(f"no video stream found in {video_path!r}")

    height = video_stream.get("height")
    if not height:
        raise ProbeError(f"video stream has no height in {video_path!r}")

    video_codec = video_stream.get("codec_name")
    audio_stream = _first_audio_stream(streams)
    audio_codec = audio_stream.get("codec_name") if audio_stream else None
    container = data.get("format", {}).get("format_name")

    return {
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "height": height,
        "container": container,
        "branch": decide_branch(height, video_codec, audio_codec),
    }


def main():
    if len(sys.argv) != 2:
        print("usage: probe.py VIDEO_PATH", file=sys.stderr)
        return 1

    try:
        result = probe(sys.argv[1])
    except ProbeError as exc:
        print(f"probe error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
