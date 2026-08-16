# deploy/

Deployment/setup notes and scripts for the VPS side.

## Upload form exposure: Caddy + DuckDNS, not a raw open port

**Correction from an earlier version of this doc**: the upload form is **not** exposed via a raw `ufw allow 8081/tcp` rule. Nomify's actual production setup (not its README's older aspirational notes) uses Caddy as a reverse proxy with DuckDNS + automatic HTTPS, and never opens its app port directly — `ufw` only allows 22/80/443. Nomiflix follows the same pattern, for the same reason: the upload form's password travels in Basic Auth, which must not go out in cleartext over plain HTTP.

`upload/app.py` already binds to `127.0.0.1` (matches Nomify's `app.py` — no code change needed), so it's only reachable via the Caddy reverse proxy, never directly from the internet.

If you already ran `sudo ufw allow 8081/tcp`, undo it: `sudo ufw delete allow 8081/tcp`.

## Done (written and locally syntax-checked; not yet applied to the VPS)

- `setup-dirs.sh` — creates `_Inbox/`, `_Processing/`, `_Failed/`, `logs/` under `NOMIFLIX_ROOT` (default `/opt/nomiflix`) and chowns them to `NOMIFLIX_USER` (default `nomikos`). Mirrors Nomify's `setup-dirs.sh`. `Movies/`/`Shows/` aren't pre-created — the pipeline makes them on first use.
- `nomiflix-inbox-watcher.service` — systemd unit for `scripts/watcher.sh`, mirrors Nomify's `nomify-inbox-watcher.service`.
- `nomiflix-upload.service` — systemd unit for `upload/app.py`, mirrors Nomify's `nomify-upload.service`. Needs an `/opt/nomiflix/upload/.env` with `UPLOAD_PASSWORD=...` created on the VPS (untracked, not in git — same as Nomify's).
- `duckdns-update.sh` + `nomiflix-duckdns-update.service` + `nomiflix-duckdns-update.timer` — Nomiflix's own copies (not shared with/coupled to Nomify's), point at `/opt/nomiflix/deploy/duckdns.env`. Same DuckDNS account/token as Nomify can be reused (DuckDNS tokens are account-wide, not per-subdomain) — just register a new subdomain (e.g. `nomiflix`) under that account first.
- `Caddyfile-snippet` — the site block to manually append to the VPS's existing system Caddyfile (`/etc/caddy/Caddyfile`, which already has Nomify's blocks). Not a full Caddyfile — Caddy is a single VPS-wide service, so this doesn't get its own file the way the systemd units do.

## Not done yet

- Nothing installed/enabled on the actual VPS — repo sync + applying these is manual (git push here, git pull + `sudo systemctl enable --now ...` on the VPS), same as Nomify. Not something done from Claude Code.
- `ffmpeg`, `inotify-tools`, `python3-flask` not confirmed installed on the VPS (all are on this local dev machine now).
- DuckDNS subdomain `nomiflix.duckdns.org` not yet registered, `deploy/duckdns.env` not yet created on the VPS.
- Caddy site block not yet appended to `/etc/caddy/Caddyfile` on the VPS.
- Jellyfin: not installed. Once it is, the Nomiflix libraries need internet metadata providers (TMDb) turned off/deprioritized in favor of the local "Nfo" provider — see `docs/SPEC.md` §6. This is a one-time manual step in Jellyfin's web UI, not something a script can drive.
- `handbrake_extract.py` (local DVD extraction, see SPEC §5) has no deploy story since it deliberately never runs on the VPS.
