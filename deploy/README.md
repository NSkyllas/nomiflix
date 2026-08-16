# deploy/

Deployment/setup notes and scripts for the VPS side.

## Done (written and locally syntax-checked; not yet applied to the VPS)

- `setup-dirs.sh` — creates `_Inbox/`, `_Processing/`, `_Failed/`, `logs/` under `NOMIFLIX_ROOT` (default `/opt/nomiflix`) and chowns them to `NOMIFLIX_USER` (default `nomikos`). Mirrors Nomify's `setup-dirs.sh`. `Movies/`/`Shows/` aren't pre-created — the pipeline makes them on first use.
- `nomiflix-inbox-watcher.service` — systemd unit for `scripts/watcher.sh`, mirrors Nomify's `nomify-inbox-watcher.service`.
- `nomiflix-upload.service` — systemd unit for `upload/app.py`, mirrors Nomify's `nomify-upload.service`. Needs an `/opt/nomiflix/upload/.env` with `UPLOAD_PASSWORD=...` created on the VPS (untracked, not in git — same as Nomify's).

## Not done yet

- Nothing installed/enabled on the actual VPS — repo sync + applying these is manual (git push here, git pull + `sudo systemctl enable --now ...` on the VPS), same as Nomify. Not something done from Claude Code.
- `ffmpeg`, `inotify-tools`, `python3-flask` not confirmed installed on the VPS (all are on this local dev machine now).
- Jellyfin: not installed. Once it is, the Nomiflix libraries need internet metadata providers (TMDb) turned off/deprioritized in favor of the local "Nfo" provider — see `docs/SPEC.md` §6. This is a one-time manual step in Jellyfin's web UI, not something a script can drive.
- `ufw allow <upload port>/tcp` for the upload form's port (`8081` by default — chosen to not collide with Nomify's `8080`).
- `handbrake_extract.py` (local DVD extraction, see SPEC §5) has no deploy story since it deliberately never runs on the VPS.
