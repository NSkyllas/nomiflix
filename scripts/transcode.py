#!/usr/bin/env python3
# Wraps ffmpeg for the "scale" and "codec_only" branches from probe.py.
# Never called for the "skip" branch — that's just a move, no ffmpeg
# involved. Per-stream copy-vs-encode is decided independently (not just
# per branch) so a codec_only file with already-compliant video but wrong
# audio doesn't pay to re-encode video it didn't need to touch — CPU is a
# hard constraint (see CLAUDE.md), so avoiding unnecessary re-encodes matters.

import os
import subprocess
import sys

from probe import TARGET_AUDIO_CODEC, TARGET_VIDEO_CODEC, BRANCH_SCALE, BRANCH_SKIP, probe, ProbeError

CRF = "22"
SCALE_HEIGHT = 1080


class TranscodeError(Exception):
    """Expected, user-fixable failure (ffmpeg error, no output produced, ...)."""


def build_ffmpeg_cmd(input_path, output_path, probe_result):
    video_needs_encode = (
        probe_result["branch"] == BRANCH_SCALE
        or probe_result["video_codec"] != TARGET_VIDEO_CODEC
    )
    audio_needs_encode = probe_result["audio_codec"] != TARGET_AUDIO_CODEC

    cmd = ["ffmpeg", "-y", "-nostdin", "-i", input_path, "-map_metadata", "-1"]

    if probe_result["branch"] == BRANCH_SCALE:
        cmd += ["-vf", f"scale=-2:{SCALE_HEIGHT}"]

    if video_needs_encode:
        cmd += ["-c:v", "libx264", "-crf", CRF]
    else:
        cmd += ["-c:v", "copy"]

    if audio_needs_encode:
        cmd += ["-c:a", "aac"]
    else:
        cmd += ["-c:a", "copy"]

    cmd.append(output_path)
    return cmd


def transcode(input_path, output_path, probe_result):
    """Runs ffmpeg per probe_result's branch/codecs. Raises TranscodeError
    on failure; caller is responsible for moving the original to _Failed/
    (this function never touches input_path)."""
    if probe_result["branch"] == BRANCH_SKIP:
        raise TranscodeError("transcode() called on a 'skip' branch file — should just be moved, not transcoded")

    cmd = build_ffmpeg_cmd(input_path, output_path, probe_result)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise TranscodeError(f"ffmpeg failed: {result.stderr.strip()[-500:]}")


def main():
    if len(sys.argv) != 3:
        print("usage: transcode.py INPUT_PATH OUTPUT_PATH", file=sys.stderr)
        return 1

    input_path, output_path = sys.argv[1], sys.argv[2]

    try:
        probe_result = probe(input_path)
    except ProbeError as exc:
        print(f"probe error: {exc}", file=sys.stderr)
        return 1

    if probe_result["branch"] == BRANCH_SKIP:
        print(f"already compliant ({probe_result}) — no transcode needed, just move it")
        return 0

    print(f"branch={probe_result['branch']} video={probe_result['video_codec']} "
          f"audio={probe_result['audio_codec']} height={probe_result['height']}")

    try:
        transcode(input_path, output_path, probe_result)
    except TranscodeError as exc:
        print(f"transcode error: {exc}", file=sys.stderr)
        return 1

    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
