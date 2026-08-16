# scripts/

Pipeline implementation goes here. Expected pieces (see `docs/SPEC.md` §3 for full logic):

- `probe.py` — done. Wraps `ffprobe`, returns codec/resolution info + branch decision (`scale`/`codec_only`/`skip`)
- `transcode.py` — done. Wraps `ffmpeg` for the `scale`/`codec_only` branches; copies (not re-encodes) whichever of video/audio is already compliant, since CPU is the tight resource
- `write_nfo.py` — done. Builds a local Kodi/Jellyfin NFO (`<movie>` or `<episodedetails>`) from the upload sidecar's metadata, see SPEC §6. Known gap: the upload form has one Title field, which doubles as show name AND per-episode title for shows — no separate episode-title field yet
- `move_into_library.py` — done. Applies Jellyfin naming convention, moves into `Movies/` or `Shows/`. Refuses to overwrite an existing destination (raises rather than silently clobbering)
- `process_item.py` — done. Orchestrates one `_Processing/<base>.*` pair: probe → transcode (if needed) → move into library → place poster (if any) → write NFO, or route to `_Failed/` on any expected error. Verified end-to-end against synthetic files (transcode branch, skip branch, corrupt-input failure)
- `watcher.sh` — done. inotifywait dispatcher, mirrors Nomify's `inbox-watcher.sh` (per-base `flock`, catch-up scan of pairs already waiting at startup) plus the `_Inbox/` → `_Processing/` move Nomiflix's design calls for. Also moves the optional poster file. Verified live: background-started, pairs dropped into `_Inbox/` while running get picked up automatically (both upload orderings), plus a catch-up run against a pair dropped while no watcher was running
- `../upload/app.py` + `../upload/templates/index.html` — done. Flask upload form mirroring Nomify's (video + Title/Year/Type/Season+Episode/Overview/poster, all server-side validated), writes the random-base-name video+JSON(+poster) set into `_Inbox/`. Verified live end-to-end: real `curl` upload with a poster → `_Inbox/` → `watcher.sh` → landed correctly in `Movies/` with matching video/NFO/poster basenames; all validation error paths (missing title, bad year, show without season/episode, unsupported video extension, no file) confirmed to reject cleanly with no partial files left in `_Inbox/`
- `handbrake_extract.py` (later) — DVD `VIDEO_TS`/ISO extraction step, see SPEC §5

The full pipeline (upload → watch → probe → transcode → file → NFO/poster) is now built and verified locally end-to-end. Remaining: real-world testing against actual movie files (not synthetic `ffmpeg testsrc` clips), and eventual VPS deployment (systemd units, Jellyfin config — see `deploy/`).

Keep the queue/lock mechanism simple (single lock file is enough per SPEC §3.3) — no need for a job queue framework at this scale.

Local dev note: this repo has no venv/requirements.txt, matching Nomify's convention of using the system's `python3-flask` package rather than pip. `python3-flask` was installed via `sudo apt install python3-flask` for local testing.
