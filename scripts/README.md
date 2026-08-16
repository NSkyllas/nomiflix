# scripts/

Pipeline implementation goes here. Expected pieces (see `docs/SPEC.md` §3 for full logic):

- `watcher.py` (or `.sh`) — inotifywait-triggered entry point, watches `_Inbox/`
- `probe.py` — wraps `ffprobe`, returns codec/resolution info for the branch decision
- `transcode.py` — wraps `ffmpeg`, handles the three branches (scale+encode / codec-only / skip)
- `move_into_library.py` — applies Jellyfin naming convention, moves into `Movies/` or `Shows/`
- `handbrake_extract.py` (later) — DVD `VIDEO_TS`/ISO extraction step, see SPEC §5

Keep the queue/lock mechanism simple (single lock file is enough per SPEC §3.3) — no need for a job queue framework at this scale.
