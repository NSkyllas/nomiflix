#!/usr/bin/env python3
# Upload form: a video file plus Title/Year/Type/Season+Episode/Overview
# and an optional poster. Writes everything into _Inbox/ under a random
# base name, so there is no filename-matching step left for a human (or
# the watcher) to get wrong. See docs/SPEC.md §3.1.

import hmac
import json
import os
import re
import uuid

from flask import Flask, Response, render_template, request

app = Flask(__name__)

LIBRARY_ROOT = os.environ.get("LIBRARY_ROOT", "/opt/nomiflix")
INBOX = os.path.join(LIBRARY_ROOT, "_Inbox")
UPLOAD_PASSWORD = os.environ["UPLOAD_PASSWORD"]

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".wmv", ".flv", ".ts", ".m2ts", ".webm"}
COVER_EXTENSIONS = {".jpg": ".jpg", ".jpeg": ".jpg", ".png": ".png", ".webp": ".webp"}
YEAR_RE = re.compile(r"^\d{4}$")

TYPE_MOVIE = "movie"
TYPE_SHOW = "show"


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
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    video_file = request.files.get("video")
    poster_file = request.files.get("poster")
    title = request.form.get("title", "").strip()
    year = request.form.get("year", "").strip()
    item_type = request.form.get("type", "").strip()
    season = request.form.get("season", "").strip()
    episode = request.form.get("episode", "").strip()
    overview = request.form.get("overview", "").strip()

    def error(message):
        return render_template("index.html", error=message), 400

    if not video_file or not video_file.filename:
        return error("Please choose a video file.")
    video_ext = os.path.splitext(video_file.filename)[1].lower()
    if video_ext not in VIDEO_EXTENSIONS:
        return error(f"Unsupported video file type {video_ext!r}.")
    if not title:
        return error("Title is required.")
    if not YEAR_RE.match(year):
        return error("Year is required and must be a 4-digit number.")
    if item_type not in (TYPE_MOVIE, TYPE_SHOW):
        return error("Type must be Movie or Show.")
    if item_type == TYPE_SHOW:
        if not season.isdigit() or int(season) < 1:
            return error("Season is required for a Show and must be a positive number.")
        if not episode.isdigit() or int(episode) < 1:
            return error("Episode is required for a Show and must be a positive number.")

    poster_ext = None
    if poster_file and poster_file.filename:
        poster_ext = COVER_EXTENSIONS.get(os.path.splitext(poster_file.filename)[1].lower())
        if not poster_ext:
            return error("Poster must be a jpg, png, or webp file.")

    os.makedirs(INBOX, exist_ok=True)
    base = uuid.uuid4().hex[:12]

    # Poster, then video, then json last — the watcher triggers off
    # whichever of the video/json is written last, so everything else must
    # already be on disk by then or watcher.sh could grab an incomplete set.
    if poster_ext:
        poster_file.save(os.path.join(INBOX, base + "-poster" + poster_ext))

    video_file.save(os.path.join(INBOX, base + video_ext))

    metadata = {"title": title, "year": year, "type": item_type}
    if item_type == TYPE_SHOW:
        metadata["season"] = season
        metadata["episode"] = episode
    if overview:
        metadata["overview"] = overview

    with open(os.path.join(INBOX, base + ".json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return render_template("index.html", success=f'Uploaded — nomiflix will process "{title}" shortly.')


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 8081)))
