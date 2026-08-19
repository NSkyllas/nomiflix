# Nomiflix — Technical Spec

Companion to `CLAUDE.md`. That file has the "why"; this file has the "what," in enough detail to implement against. Update this doc as design decisions firm up during implementation — it should stay accurate, not aspirational.

## 1. Environment

| Item | Value |
|---|---|
| Host | Same Contabo VPS as Nomify |
| OS | Ubuntu Noble |
| User | `nomikos` |
| Resources | 4 vCPU / 8GB RAM / 100GB disk (shared with Nomify) |
| Install method | Native (no Docker) |
| Firewall | ufw already configured for SSH/80/443 (Nomify) — add Jellyfin's port when installed |
| Streaming server | Jellyfin |

## 2. Directory layout

```
/opt/nomiflix/                     (root — matches Nomify's /opt/nomify convention)
├── _Inbox/                        # raw uploads land here
├── _Processing/                   # in-flight jobs (watcher moves file here while working)
├── _Failed/                       # failed transcodes; original preserved
│   └── <job>.log                  # error log per failed item
├── Movies/                        # Jellyfin library root — movies
│   └── <Title> (<Year>)/
│       └── <Title> (<Year>).mkv
├── Shows/                         # Jellyfin library root — series
│   └── <Show Name>/
│       └── Season 01/
│           └── <Show Name> S01E01.mkv
└── logs/
    └── watcher.log                # general pipeline activity log
```

Root path confirmed as `/opt/nomiflix`. Open question: disk layout may still need to change if/when the block storage decision is made (see CLAUDE.md deferred items).

## 3. Ingestion pipeline

### 3.1 Upload

**Decided**: a small Flask upload form, directly mirroring Nomify's `upload/app.py`, is the sole entry point into `_Inbox/` — no direct file drops. Fields:

- **Video file** (required)
- **Title** (required)
- **Year** (required)
- **Type**: Movie or Show (required) — the single source of truth for routing. No `_Inbox/Movies/` vs `_Inbox/Shows/` subfoldering — the upload form is the only way a file enters `_Inbox/`, so there's no manual filesystem step left to make redundant with this field
- **Season / Episode** (required if Type = Show)
- **Genre** (required) — fixed dropdown, currently `Samurai` / `Science Fiction` / `Greek` / `Western`. Extend the list the same way if more categories come up.
- **Poster image** (optional)
- **Credits** (optional) — a raw paste of IMDB's "Full Cast & Crew" page, uploaded as `<base>-credits.txt` and **parsed** by `scripts/parse_credits.py` during processing (§3.3 step 5) into department-grouped Name/role/alias/uncredited/voice records — see §6 for what happens to the result. A bad/unrecognized paste fails the **whole item** (routed to `_Failed/`, same as a transcode failure) rather than degrading gracefully — credits parsing is fail-loud like Nomify's tracklist/credits parsing, not best-effort. There is no Overview/plot field — Credits replaces that role entirely.

Like Nomify's uploader, the video is saved under a random base name (e.g. `uuid4().hex[:12]`) alongside a metadata sidecar written from the form fields, so there's no filename-collision or matching step left for a human (or the watcher) to get wrong. Poster and credits are separate sidecar files (`<base>-poster.<ext>`, `<base>-credits.txt`), not folded into the JSON — named with a `-suffix` (not `<base>.<ext>`) specifically so they don't collide with `process_item.py`'s video-detection glob.

**Sidecar format decided as JSON** (`<base>.json`), not Nomify's key:value `.txt` — the fields here are flat (title/year/type/season/episode/genre) with no tracklist-style nested structure to parse, so JSON needs no custom parser and is what `process_item.py`/`write_nfo.py`/`move_into_library.py` already consume.

### 3.2 Trigger
`inotifywait` watches `_Inbox/` for new/completed file writes (reuse Nomify's watcher pattern — same tool, new logic). Triggers once both the video and its metadata sidecar are present, mirroring how Nomify's watcher waits for the mp3+txt pair.

### 3.3 Processing steps

1. **Detect** new video+sidecar pair in `_Inbox/`.
2. **Move** to `_Processing/<filename>` (prevents watcher from double-triggering, gives a clear "in progress" state).
3. **Probe** with `ffprobe`: read video codec, audio codec, resolution (height), container.
4. **Branch:**

   | Condition | Action |
   |---|---|
   | height > 1080p | Transcode: scale to 1080p, H.264 video (CRF ~20–23, `libx264`), AAC audio, MKV/MP4 container |
   | height ≤ 1080p, codec/audio NOT already H.264+AAC | Transcode: re-encode/re-mux to H.264+AAC, **no scaling** |
   | height ≤ 1080p, codec/audio already H.264+AAC | Skip transcoding — just rename/move |

5. **On transcode success** (or skip case): move final file into `Movies/` or `Shows/` using Jellyfin naming convention (see §4), and write a local NFO file from the sidecar's metadata (+ parsed credits, if any) alongside it (see §6). Delete the original from `_Processing/`. Credits are parsed **before** probe/transcode even starts, not after — a bad paste should fail fast, not burn a potentially long transcode first.
6. **On transcode failure**: move original (untouched) to `_Failed/<filename>`, write an error log (`ffprobe`/`ffmpeg` stderr, timestamp, filename) to `_Failed/<filename>.log`. Never delete on failure.
7. **Log outcome** (success/skip/fail) to `logs/watcher.log` regardless of branch.

### 3.4 Concurrency

Jobs run **strictly sequentially** — one transcode at a time. A simple lock file (e.g. `_Processing/.lock`) or a job queue directory is sufficient; no need for a full job queue system (e.g. Redis/Celery) at this scale. If a second file lands in `_Inbox/` while a job is running, it should wait in `_Inbox/` until the lock clears.

## 4. Naming conventions (for local NFO matching, not scraper matching)

- **Movies:** `Movies/<Title> (<Year>)/<Title> (<Year>).<ext>`
- **Series:** `Shows/<Show Name>/Season <NN>/<Show Name> S<NN>E<NN>.<ext>`

The pipeline constructs these paths itself directly from the upload form's Title/Year/Type/Season/Episode fields — it does not depend on Jellyfin successfully guessing anything from the name. See §6.

## 5. DVD rip handling (not yet implemented)

DVD rips arrive as `VIDEO_TS/` folder structures or `.ISO` files, not single video files, and cannot go through the standard `_Inbox/` pipeline as-is.

Planned approach (to be refined):
1. Extract main title from `VIDEO_TS`/ISO into a single video file — likely via **HandBrake CLI** (`HandBrakeCLI`), which can go directly to H.264/AAC and may replace the ffmpeg transcode step for this source type specifically.
2. Drop the resulting single file into `_Inbox/` as normal, letting the standard pipeline handle it (probe will likely hit the "skip" or "codec-only" branch if HandBrake already output the right format).

**Decided**: extraction happens locally on Nomikos's own machine, not on the VPS — avoids ISOs/VIDEO_TS folders (large) needing to coexist with their extracted output on the VPS's limited disk. Only the final clean H.264/AAC file gets uploaded.

## 6. Metadata matching

**Decided**: no TMDb auto-scraping. Metadata comes entirely from the upload form (§3.1) — same philosophy as Nomify writing ID3 tags directly from its upload form rather than inferring them.

- The pipeline generates a local **NFO file** from the sidecar's Title/Year/Genre/Season+Episode, written as `<video basename>.nfo` alongside the final video file when it's moved into `Movies/`/`Shows/` (§3.3 step 5) — Jellyfin/Kodi both recognize this basename-matching convention, not just `movie.nfo`.
- Jellyfin's library is configured to use the **"Nfo" local metadata provider** as its source, with internet metadata providers (TMDb) disabled or deprioritized for the Nomiflix libraries specifically — so nothing is auto-matched or guessed; Jellyfin just reads what was explicitly typed in at upload time.
- Poster image, if uploaded, is saved alongside as `<video basename>-poster.<ext>` (Jellyfin/Kodi's basename-matching local-artwork convention) rather than fetched from TMDb.

This removes the scraper-mismatch problem (§7 old note) entirely rather than working around it — there's no automated matching step to get wrong.

### 6.1 Credits: parsed, split between the NFO and a separate structured file

`scripts/parse_credits.py` parses the raw IMDB paste into `{director: [names], writer: [names], cast: [{name, character, alias, uncredited, voice}], crew: {department: [{name, role, alias, uncredited, voice}]}}`. Two different destinations for the result:

- **Director / Writer / Cast → the NFO.** Kodi/Jellyfin's NFO schema only has person-slots for `<director>`, `<credits>` (writer), and `<actor>` (name + character) — there is no `<producer>` or other department element in the schema, so those three are the *only* categories that can ever show up inside Jellyfin itself, no matter how thoroughly the rest gets parsed. `alias`/`uncredited`/`voice` flags aren't written into the NFO either — Jellyfin has nowhere to display them, they're only in the JSON below.
- **Everything (all departments, full detail) → `<video basename>-credits.json`.** A durable structured record — same spirit as Nomify's `credits.json` (`write_credits_file` in `process-pair.py`) — written next to the video, meant for future analysis/visualization (e.g. a crew collaboration graph), not for Jellyfin to read. The raw pasted `.txt` is deleted once successfully parsed — the JSON is the durable artifact, the same "success renders the original disposable" pattern used for the pre-transcode video (§3.3 step 5/hard constraint #3 in `CLAUDE.md`).

**IMDB paste quirks the parser specifically handles** (found by testing against a real "Full Cast & Crew" paste, not synthesized): a cast member's photo-caption line ("`Name in Other Film (Year)`") that can reference a completely different title than the one being catalogued; a cast member with *no* photo still getting a caption line, just as their bare name repeated with no "in ... (Year)" suffix (distinguished from a real Name line only by being an exact duplicate of the line before it — a character description being byte-identical to the actor's own name is treated as implausible); and departments where a lone person has no role/alias text at all, so the line right after their name is directly the next department header, not a detail line for them.

**Known unresolvable ambiguity**: if a department ever has two people back-to-back with *neither* having role text, the parser cannot tell that apart from one person's Name+detail pair — there is no syntactic signal left after IMDB's HTML is flattened to plain text. Not seen in the one real example tested against; would surface as either a wrong pairing or (more likely) a "line N: expected a department header" fail-loud error if the department-whitelist lookahead doesn't line up.

## 7. Explicitly out of scope for now

- Job status/progress visibility (manual `_Failed/` check is sufficient per current preference)
- Automated storage overflow handling
- Automated TMDb scraping/matching (deliberately not used at all — see §6)
- Any credits/personnel/network-graph style feature (that's a Nomify-adjacent idea, not Nomiflix)
- Multi-job parallelism
- Docker/containerization

## 8. Open questions log

Keep this section current — move items here as they come up, remove once resolved.

- [x] Confirm actual disk mount/path for `_Inbox` etc. on the VPS — `/opt/nomiflix`, matches Nomify's `/opt` convention
- [x] Movie vs. series detection mechanism at upload time — a Type field (Movie/Show) on the upload form (§3.1); no `_Inbox/` subfoldering, since the form is the only entry point
- [x] DVD extraction: VPS or local? — local, upload only the extracted output
- [x] Metadata override mechanism for scraper mismatches — resolved by not using a scraper at all; metadata is typed in at upload and written to local NFO files (§6)
- [x] Jellyfin install/config — installed natively via official apt repo, reachable at `https://nomiflix-jellyfin.duckdns.org` via Caddy (port 8096 not opened in `ufw`, same never-expose-app-port pattern as the upload form). Movies/Shows libraries added, TMDb fetchers disabled, Nfo reader enabled, confirmed reading real local metadata/artwork/credits correctly. Trickplay/chapter-image scheduled tasks disabled to avoid CPU contention with transcode jobs. See `deploy/README.md`.
- [ ] When/how to revisit storage strategy (block storage vs. external) — revisit after a few months per CLAUDE.md
