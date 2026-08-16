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
/srv/nomiflix/                     (proposed root — confirm/adjust on VPS)
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

Open question: confirm actual mount point / disk layout once block storage decision is made (see CLAUDE.md deferred items).

## 3. Ingestion pipeline

### 3.1 Trigger
`inotifywait` watches `_Inbox/` for new/completed file writes (reuse Nomify's watcher pattern — same tool, new logic).

### 3.2 Processing steps

1. **Detect** new file in `_Inbox/`.
2. **Move** to `_Processing/<filename>` (prevents watcher from double-triggering, gives a clear "in progress" state).
3. **Probe** with `ffprobe`: read video codec, audio codec, resolution (height), container.
4. **Branch:**

   | Condition | Action |
   |---|---|
   | height > 1080p | Transcode: scale to 1080p, H.264 video (CRF ~20–23, `libx264`), AAC audio, MKV/MP4 container |
   | height ≤ 1080p, codec/audio NOT already H.264+AAC | Transcode: re-encode/re-mux to H.264+AAC, **no scaling** |
   | height ≤ 1080p, codec/audio already H.264+AAC | Skip transcoding — just rename/move |

5. **On transcode success** (or skip case): move final file into `Movies/` or `Shows/` using Jellyfin naming convention (see §4). Delete the original from `_Processing/`.
6. **On transcode failure**: move original (untouched) to `_Failed/<filename>`, write an error log (`ffprobe`/`ffmpeg` stderr, timestamp, filename) to `_Failed/<filename>.log`. Never delete on failure.
7. **Log outcome** (success/skip/fail) to `logs/watcher.log` regardless of branch.

### 3.3 Concurrency

Jobs run **strictly sequentially** — one transcode at a time. A simple lock file (e.g. `_Processing/.lock`) or a job queue directory is sufficient; no need for a full job queue system (e.g. Redis/Celery) at this scale. If a second file lands in `_Inbox/` while a job is running, it should wait in `_Inbox/` until the lock clears.

### 3.4 Movie vs. series detection

Not yet designed. Options to evaluate during implementation:
- Filename/pattern heuristics (e.g. `S01E01` pattern present → series)
- A `.txt` sidecar file (mirroring Nomify's metadata pairing) specifying type + target path explicitly
- Manual sorting into `_Inbox/Movies/` vs `_Inbox/Shows/` subfolders at upload time (simplest — likely starting point)

Recommend starting with the manual subfolder approach (simplest, matches how deliberate/curated Nomiflix's ingestion is expected to be) and revisiting if it becomes a bottleneck.

## 4. Naming conventions (for Jellyfin auto-scraping)

- **Movies:** `Movies/<Title> (<Year>)/<Title> (<Year>).<ext>`
- **Series:** `Shows/<Show Name>/Season <NN>/<Show Name> S<NN>E<NN>.<ext>`

These must be exact enough for Jellyfin's TMDb scraper to match. Given Nomiflix's focus on rare/obscure titles, expect a nontrivial rate of scraper mismatches — see §6.

## 5. DVD rip handling (not yet implemented)

DVD rips arrive as `VIDEO_TS/` folder structures or `.ISO` files, not single video files, and cannot go through the standard `_Inbox/` pipeline as-is.

Planned approach (to be refined):
1. Extract main title from `VIDEO_TS`/ISO into a single video file — likely via **HandBrake CLI** (`HandBrakeCLI`), which can go directly to H.264/AAC and may replace the ffmpeg transcode step for this source type specifically.
2. Drop the resulting single file into `_Inbox/` as normal, letting the standard pipeline handle it (probe will likely hit the "skip" or "codec-only" branch if HandBrake already output the right format).

Open question: does extraction happen on the VPS (upload the ISO, extract there) or locally on Nomikos's own machine (extract first, upload the clean file)? No decision yet — likely depends on VPS disk headroom, since ISOs/VIDEO_TS folders are large and would need to exist alongside their extracted output temporarily.

## 6. Metadata matching (fallback not yet designed)

Default: rely on Jellyfin's built-in TMDb scraper via naming convention (§4).

For titles the scraper gets wrong or can't find (expected to be common given Nomiflix's focus on rare/obscure content), a manual override will likely be needed eventually. Not designed yet. Candidate approaches to evaluate later:
- Jellyfin's native manual "identify" UI (may be sufficient on its own — check before building anything custom)
- A `.txt` sidecar file per item (mirroring Nomify's `.txt` metadata pattern) with explicit TMDb ID or title/year override, consumed by the pipeline before the file is moved into place

## 7. Explicitly out of scope for now

- Job status/progress visibility (manual `_Failed/` check is sufficient per current preference)
- Automated storage overflow handling
- Any credits/personnel/network-graph style feature (that's a Nomify-adjacent idea, not Nomiflix)
- Multi-job parallelism
- Docker/containerization

## 8. Open questions log

Keep this section current — move items here as they come up, remove once resolved.

- [ ] Confirm actual disk mount/path for `_Inbox` etc. on the VPS
- [ ] Movie vs. series detection mechanism at upload time
- [ ] DVD extraction: VPS or local?
- [ ] Metadata override mechanism for scraper mismatches
- [ ] When/how to revisit storage strategy (block storage vs. external) — revisit after a few months per CLAUDE.md
