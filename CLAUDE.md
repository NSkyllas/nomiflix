# Nomiflix — Project Context

Read this file first. It's the anchor for how this project works and what decisions have already been made. Full technical detail lives in `docs/SPEC.md` — this file is the "why" and the guardrails.

## What this is

A self-hosted movie/series library and streaming setup, sibling project to **Nomify** (music). Same philosophy: own the library, own the infrastructure, no dependency on third-party streaming availability.

**Purpose, specifically:** old/rare movies and shows that aren't on Netflix/mainstream streaming — things Nomikos already loves but can only find as lower-resolution web rips, or has to rip from his own DVD collection. This is NOT a general Plex/Jellyfin replacement for new releases — that context shapes a lot of the pipeline decisions below (assume messy, inconsistent, low-res sources as the *normal* case, not the exception).

## Infrastructure

- Runs on the **same Contabo VPS as Nomify** (Ubuntu Noble, user `nomikos`, 4 vCPU / 8GB RAM / 100GB disk, EU region), at least for now — explicitly a "start here, see how storage goes" decision, not a permanent commitment.
- **Fully separate service** from Nomify: own directory tree, own port, own process. Do not couple Nomiflix code/config to Nomify's.
- Streaming server: **Jellyfin** (chosen over Plex/Emby — no cloud account layer, fully self-hosted, matches the ownership philosophy).
- Native install preferred, consistent with Nomify (no Docker), unless a strong reason emerges to deviate.

## Hard constraints (don't relitigate these without a good reason)

1. **Disk is the tightest resource.** 100GB total on the VPS, shared with Nomify's music library. Movie/series files are an order of magnitude bigger than music. Storage growth needs to be watched — this is why transcoding to a smaller universal format matters so much.
2. **CPU is limited (4 vCPUs) and shared with Nomify.** Transcoding is CPU-bound and slow (a 2hr movie can take hours on this hardware). Transcode jobs must run **sequentially, one at a time**, never in parallel, and should not starve Navidrome/Nomify or Jellyfin direct-play traffic.
3. **Never silently lose source files.**
   - Transcode **succeeds** → delete the original (avoid doubling storage).
   - Transcode **fails** → keep the original, move to `_Failed/`, log the error. Never delete on failure.

## Universal format (the core design decision)

Goal: everything in the library should be able to **direct play** in Jellyfin on any client (phone, TV, browser) — i.e. never transcode at watch time. All the ingest-time work exists to guarantee this.

Target: **H.264 video + AAC audio, MKV or MP4 container.**

Resolution rule — conditional, not blanket:
- Source height **> 1080p** → transcode down to 1080p (CRF ~20–23, x264).
- Source height **≤ 1080p** but codec/audio isn't already H.264/AAC (e.g. HEVC, VP9, AV1, AC3, DTS) → transcode container/codec only, do **not** upscale.
- Source height **≤ 1080p** and already H.264/AAC → skip transcoding entirely, just move + rename into place.

Given the actual source mix (old web rips, DVD rips), the skip/codec-only branches will likely be the common case, not the "shrink from 4K" branch — don't over-optimize for the expensive path.

## Pipeline shape (mirrors Nomify's `_Inbox` pattern)

```
_Inbox/        → raw upload, any resolution/codec/container
_Processing/   → watcher picked it up, job in progress
_Failed/       → transcode failed; original preserved + error logged
Movies/        → Jellyfin structure: Movies/Title (Year)/Title (Year).mkv
Shows/         → Jellyfin structure: Shows/Show Name/Season 01/Show Name S01E01.mkv
```

Watcher (inotifywait-based, same tool as Nomify) → probe with `ffprobe` → three-way branch above → move into Jellyfin folder convention → delete original on success only → log outcome.

**DVD sources are a special case**: a rip is a `VIDEO_TS/` folder or `.ISO`, not a single video file — it can't just drop into `_Inbox/` like a downloaded file. Needs a separate extraction step (HandBrake CLI is the likely tool) to pull the main title into a single file first. Not yet decided whether extraction happens on the VPS or locally before upload — flag this as open when it comes up.

## Metadata

Jellyfin's built-in TMDb scraping works from folder/file naming convention alone — no manual tagging step required, unlike Nomify's mutagen/ID3 approach. **But**: because Nomiflix's whole purpose is rare/obscure titles, auto-matching will be unreliable more often than for mainstream content (wrong year, foreign remake, no match at all). Expect to eventually need a manual override/fallback for matching, similar in spirit to Nomify's `.txt` sidecar approach — not designed yet, just anticipated.

## Explicitly deferred / not yet decided

- Long-term storage location if VPS disk fills up (block storage add-on vs. external storage) — revisit after a few months of real usage data.
- DVD extraction step location (VPS vs. local).
- Manual metadata override mechanism for unmatched/misidentified titles.
- Progress/status visibility into long-running transcode jobs — not needed yet; manual check of `_Failed/` is sufficient for now.

## Working style

- Architecture/design discussions happen in the Claude.ai project (high-level, "why" decisions). Implementation happens here, in Claude Code.
- Prefer small, verifiable steps over big-bang implementation, given how slow/expensive transcode testing can be on this hardware.
- Don't reintroduce Docker, don't couple to Nomify's codebase, don't default to Plex — these were explicit decisions above.
