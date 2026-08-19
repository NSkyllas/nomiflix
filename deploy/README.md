# deploy/

Deployment/setup notes and scripts for the VPS side.

## Upload form exposure: Caddy + DuckDNS, not a raw open port

**Correction from an earlier version of this doc**: the upload form is **not** exposed via a raw `ufw allow 8081/tcp` rule. Nomify's actual production setup (not its README's older aspirational notes) uses Caddy as a reverse proxy with DuckDNS + automatic HTTPS, and never opens its app port directly — `ufw` only allows 22/80/443. Nomiflix follows the same pattern, for the same reason: the upload form's password travels in Basic Auth, which must not go out in cleartext over plain HTTP.

`upload/app.py` already binds to `127.0.0.1` (matches Nomify's `app.py` — no code change needed), so it's only reachable via the Caddy reverse proxy, never directly from the internet.

If you already ran `sudo ufw allow 8081/tcp`, undo it: `sudo ufw delete allow 8081/tcp`.

## Runs as root — this VPS has no separate `nomikos` service account for Nomiflix

**Correction**: earlier versions of these deploy files assumed a `nomikos` user, copied over from how Nomify's own deploy files are set up. That was never actually confirmed for Nomiflix's VPS — asked and confirmed: everything here runs as **root** (`setup-dirs.sh`'s `NOMIFLIX_USER` defaults to `root`, both systemd units use `User=root`). Don't assume a service account exists; ask if it's ever unclear which user something should run as.

## Known issue, fixed: `setup-dirs.sh` must chown the whole root, not just the subdirs

Hit on the real VPS: the first real upload failed with `PermissionError: /opt/nomiflix/Movies` — `setup-dirs.sh` originally only chowned `_Inbox/`/`_Processing/`/`_Failed/`/`logs/` individually, not `NOMIFLIX_ROOT` itself. Since `Movies/`/`Shows/` are created lazily by `move_into_library.py` the first time an item is filed, directly as children of the repo root, this bites regardless of which user owns/runs things if that user isn't also the root directory's owner. Fixed by chowning the whole `NOMIFLIX_ROOT`. (This was surfaced while ownership was still assumed to be `nomikos`, before that assumption was corrected to `root` above — with everything running as root, `chown` is close to moot since root can write anywhere, but the script still sets it explicitly for clarity/consistency.)

## Done (applied on the real VPS — upload form and watcher are live)

- `setup-dirs.sh` — creates `_Inbox/`, `_Processing/`, `_Failed/`, `logs/` under `NOMIFLIX_ROOT` (default `/opt/nomiflix`) and chowns the whole root to `NOMIFLIX_USER` (default `root`) — see fix above.
- `nomiflix-inbox-watcher.service` — systemd unit for `scripts/watcher.sh`, structurally mirrors Nomify's `nomify-inbox-watcher.service` but runs as `root`, not `nomikos` (Nomify's actual VPS user — not assumed to exist here).
- `nomiflix-upload.service` — systemd unit for `upload/app.py`, same structural mirror, same root-vs-nomikos distinction. Needs an `/opt/nomiflix/upload/.env` with `UPLOAD_PASSWORD=...` created on the VPS (untracked, not in git — same as Nomify's).
- `duckdns-update.sh` + `nomiflix-duckdns-update.service` + `nomiflix-duckdns-update.timer` — Nomiflix's own copies (not shared with/coupled to Nomify's), point at `/opt/nomiflix/deploy/duckdns.env`. Same DuckDNS account/token as Nomify can be reused (DuckDNS tokens are account-wide, not per-subdomain) — just register a new subdomain (e.g. `nomiflix`) under that account first.
- `Caddyfile-snippet` — the site block to manually append to the VPS's existing system Caddyfile (`/etc/caddy/Caddyfile`, which already has Nomify's blocks). Not a full Caddyfile — Caddy is a single VPS-wide service, so this doesn't get its own file the way the systemd units do.

## Done on the VPS (confirmed by real usage)

- `ffmpeg`, `inotify-tools`, `python3-flask` installed — `nomiflix-inbox-watcher` and `nomiflix-upload` are running and have processed a real upload (probe/transcode succeeded; it only failed at the `Movies/` mkdir step, see fix above).
- DuckDNS subdomain + Caddy reverse proxy working — upload form is reachable and accepting real uploads.

## Jellyfin — installed and reachable (2026-08-19)

- Installed natively via Jellyfin's official apt repo (`curl -fsSL https://repo.jellyfin.org/install-debuntu.sh | sudo bash`) — matches the no-Docker constraint, runs as its own `jellyfin.service` (not coupled to Nomiflix's own systemd units).
- Listens on `127.0.0.1:8096`/`0.0.0.0:8096` by default, but `ufw` only allows 22/80/443 — same "never open the app port directly" pattern as the upload form, reachable only through Caddy.
- New DuckDNS subdomain `nomiflix-jellyfin` added under the same account/token as `nomiflix` — `duckdns.env`'s `DUCKDNS_SUBDOMAIN` updated to `nomiflix,nomiflix-jellyfin` (DuckDNS's update endpoint accepts a comma-separated list in one call, same as Nomify's `nomify,nomify-navidrome`).
- Caddy block added to `/etc/caddy/Caddyfile` (see `Caddyfile-snippet`) and reloaded — `https://nomiflix-jellyfin.duckdns.org` confirmed serving (200 from `/health`).
- Web UI setup done: admin account created; Movies/Shows libraries added pointed at `/opt/nomiflix/Movies` and `/opt/nomiflix/Shows`; both libraries' metadata fetchers (TheMovieDb/TheTVDB) disabled, Nfo reader enabled — confirmed against a real library item (title/year/genre/poster/credits all coming from the local NFO/poster, not fetched).
- Dashboard > Scheduled Tasks: **Generate Trickplay Images** and **Extract Chapter Images** disabled — both are CPU-bound background jobs that would otherwise compete with sequential ffmpeg transcodes on the same 4 vCPUs (hard constraint #2 in `CLAUDE.md`).

## Not done yet

- `handbrake_extract.py` (local DVD extraction, see SPEC §5) has no deploy story since it deliberately never runs on the VPS.
