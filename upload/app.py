#!/usr/bin/env python3
# Upload form: a video file plus Title/Year/Type/Season+Episode/Genre, and
# optional poster + credits. Writes everything into _Inbox/ under a random
# base name, so there is no filename-matching step left for a human (or
# the watcher) to get wrong. See docs/SPEC.md §3.1.

import hmac
import json
import os
import re
import uuid
import xml.etree.ElementTree as ET

from flask import Flask, Response, render_template, request

app = Flask(__name__)

LIBRARY_ROOT = os.environ.get("LIBRARY_ROOT", "/opt/nomiflix")
INBOX = os.path.join(LIBRARY_ROOT, "_Inbox")
SHOWS_ROOT = os.path.join(LIBRARY_ROOT, "Shows")
UPLOAD_PASSWORD = os.environ["UPLOAD_PASSWORD"]

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".ts", ".m2ts", ".webm"}
COVER_EXTENSIONS = {".jpg": ".jpg", ".jpeg": ".jpg", ".png": ".png", ".webp": ".webp"}
YEAR_RE = re.compile(r"^\d{4}$")
BAD_CHARS_RE = re.compile(r'[\/\\:*?"<>|]')

TYPE_MOVIE = "movie"
TYPE_SHOW = "show"

GENRES = [
    "Samurai",
    "Science Fiction",
    "Greek",
    "Western",
    "Film Noir",
    "Horror",
    "Comedy",
    "Drama",
    "Crime",
    "War",
    "Musical",
    "Animation",
    "Documentary",
    "Adventure",
    "Mystery",
    "Fantasy",
    "Thriller",
    "Romance",
]


def sanitize_title(title):
    # Must match scripts/move_into_library.py's sanitize() exactly — kept
    # as a separate copy since upload/ and scripts/ run as independent
    # systemd services (see deploy/README.md), not a shared package.
    return BAD_CHARS_RE.sub("-", title).strip()


def show_dir_for(title):
    path = os.path.join(SHOWS_ROOT, sanitize_title(title))
    return path if os.path.isdir(path) else None


def existing_genre_for(show_dir):
    # Every episode NFO carries the show's genre (write_nfo.py writes one
    # <genre> per episode) — reuse whichever is found first so a follow-up
    # batch doesn't need Genre retyped.
    for root, _, files in os.walk(show_dir):
        for name in sorted(files):
            if not name.endswith(".nfo"):
                continue
            try:
                tree = ET.parse(os.path.join(root, name))
            except ET.ParseError:
                continue
            genre_el = tree.getroot().find("genre")
            if genre_el is not None and genre_el.text:
                return genre_el.text
    return None


@app.before_request
def require_auth():
    auth = request.authorization
    if not auth or not hmac.compare_digest(auth.password or "", UPLOAD_PASSWORD):
        return Response(
            "Authentication required",
            401,
            {"WWW-Authenticate": 'Basic realm="Nomiflix Upload"'},
        )


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", genres=GENRES)


@app.route("/show-lookup", methods=["GET"])
def show_lookup():
    # Pure UX sugar for the page's JS (relax Year/Genre requirements when a
    # show already has episodes on disk) — /upload never trusts this and
    # re-checks the same thing itself before deciding what's required.
    title = request.args.get("title", "").strip()
    if not title:
        return {"exists": False}
    show_dir = show_dir_for(title)
    if not show_dir:
        return {"exists": False}
    return {"exists": True, "genre": existing_genre_for(show_dir)}


@app.route("/upload", methods=["POST"])
def upload():
    # A Show upload may carry several episode video files in one submission
    # (see docs/SPEC.md §3.1) — Title/Year/Genre/Poster/Credits are entered
    # once and reused for every episode; Season is one value for the whole
    # batch; each file gets its own episode number, positionally paired
    # with the "episode" field list built by the page's JS. A Movie upload
    # is just the batch-size-1 case of the same code path.
    video_files = [f for f in request.files.getlist("video") if f and f.filename]
    poster_file = request.files.get("poster")
    title = request.form.get("title", "").strip()
    year = request.form.get("year", "").strip()
    item_type = request.form.get("type", "").strip()
    season = request.form.get("season", "").strip()
    episodes = [e.strip() for e in request.form.getlist("episode")]
    genre = request.form.get("genre", "").strip()
    credits_text = request.form.get("credits", "").strip()

    # Carried forward into the re-rendered form (on both success and
    # error) so a second batch for the same show — e.g. episodes 6-10
    # after 1-5 — doesn't require retyping Title/Year/Genre/Season/Credits.
    # File inputs (video, poster) can't be prefilled by browsers, so those
    # always need reselecting; that's an unavoidable platform limit, not a
    # gap in this carryover.
    sticky = {
        "genres": GENRES,
        "sticky_title": title,
        "sticky_year": year,
        "sticky_type": item_type,
        "sticky_season": season,
        "sticky_genre": genre,
        "sticky_credits": credits_text,
    }

    def error(message):
        return render_template("index.html", error=message, **sticky), 400

    if not video_files:
        return error("Please choose at least one video file.")
    video_exts = []
    for f in video_files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in VIDEO_EXTENSIONS:
            return error(f"Unsupported video file type {ext!r} ({f.filename}).")
        video_exts.append(ext)
    if not title:
        return error("Title is required.")
    if item_type not in (TYPE_MOVIE, TYPE_SHOW):
        return error("Type must be Movie or Show.")
    if item_type == TYPE_MOVIE and len(video_files) != 1:
        return error("A Movie upload supports a single video file only.")

    # A follow-up batch for a show that already has episodes on disk only
    # needs its episode-numbering fields — Year isn't persisted for shows
    # at all (unused by move_into_library.py/write_nfo.py), and Genre is
    # read back from an already-uploaded episode's NFO instead of being
    # retyped every time. /show-lookup is the same check, for the page's
    # live-updating JS; this is the authoritative copy the server enforces.
    is_existing_show = False
    if item_type == TYPE_SHOW:
        show_dir = show_dir_for(title)
        is_existing_show = show_dir is not None
        if is_existing_show and not genre:
            genre = existing_genre_for(show_dir) or genre
            sticky["sticky_genre"] = genre

    if not (item_type == TYPE_SHOW and is_existing_show) and not YEAR_RE.match(year):
        return error("Year is required and must be a 4-digit number.")

    episode_numbers = None
    if item_type == TYPE_SHOW:
        if not season.isdigit() or int(season) < 1:
            return error("Season is required for a Show and must be a positive number.")
        if len(episodes) != len(video_files):
            return error("Each video file needs an episode number.")
        episode_numbers = []
        for e in episodes:
            if not e.isdigit() or int(e) < 1:
                return error(f"Episode numbers must be positive numbers (got {e!r}).")
            episode_numbers.append(int(e))
        if len(set(episode_numbers)) != len(episode_numbers):
            return error("Episode numbers in this batch must be unique.")
    if genre not in GENRES:
        return error("Genre is required.")

    poster_ext = None
    if poster_file and poster_file.filename:
        poster_ext = COVER_EXTENSIONS.get(os.path.splitext(poster_file.filename)[1].lower())
        if not poster_ext:
            return error("Poster must be a jpg, png, or webp file.")

    os.makedirs(INBOX, exist_ok=True)

    for i, video_file in enumerate(video_files):
        base = uuid.uuid4().hex[:12]

        # Poster/credits, then video, then json last — the watcher triggers
        # off whichever of the video/json is written last, so everything
        # else must already be on disk by then or watcher.sh could grab an
        # incomplete set. Poster/credits are re-saved per item since each
        # item is an independent _Inbox/ entry the watcher processes on its
        # own — same poster/credits text applied to every episode.
        if poster_ext:
            poster_file.stream.seek(0)
            poster_file.save(os.path.join(INBOX, base + "-poster" + poster_ext))

        if credits_text:
            # Stored raw, not parsed — unlike Nomify's structured Discogs
            # credits, IMDB's format varies too much to usefully parse; it's
            # just kept as a plain sidecar text file next to the video.
            with open(os.path.join(INBOX, base + "-credits.txt"), "w", encoding="utf-8") as f:
                f.write(credits_text + "\n")

        video_file.save(os.path.join(INBOX, base + video_exts[i]))

        metadata = {"title": title, "year": year, "type": item_type, "genre": genre}
        if item_type == TYPE_SHOW:
            metadata["season"] = season
            metadata["episode"] = str(episode_numbers[i])

        with open(os.path.join(INBOX, base + ".json"), "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    if item_type == TYPE_SHOW and len(video_files) > 1:
        success = f'Uploaded {len(video_files)} episodes of "{title}" — nomiflix will process them shortly.'
    else:
        success = f'Uploaded — nomiflix will process "{title}" shortly.'

    next_episode = max(episode_numbers) + 1 if episode_numbers else None
    return render_template(
        "index.html", success=success, sticky_starting_episode=next_episode, **sticky
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 8081)))
