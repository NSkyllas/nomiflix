#!/usr/bin/env python3
# Parses a raw paste of IMDB's "Full Cast & Crew" page into structured
# data: repeating Name/detail-line pairs grouped under department headers
# (Director, Writers, Cast, Composer, ...), with the Cast section handling
# two extra IMDB quirks: photo-caption noise lines ("X in Y (1999)") and
# status lines ("(in credits order) ...", "Rest of cast listed
# alphabetically", "Crew verified as complete"). Every detail line gets a
# light, uniform tag extraction — "(as ALIAS)" / "(uncredited)" / "(voice)"
# — with whatever's left over kept as the role/character text; nothing
# deeper than that is inferred, since IMDB's phrasing is too varied to
# model precisely and the goal here is archival/analysis data, not a
# strict schema. Fails loudly (CreditsParseError) on any line that doesn't
# fit a known department header or a Name/detail pair — per-project
# philosophy: never silently drop or misfile credit data.

import json
import re
import sys

# Not exhaustive — IMDB's exact department vocabulary varies by title/era.
# If a real paste hits an "unrecognized line" error on a genuine department
# header, add it here; the error message names the exact line so it's a
# quick fix.
KNOWN_DEPARTMENTS = {
    "Director", "Directors", "Writer", "Writers", "Producer", "Producers",
    "Cast", "Composer", "Cinematographer", "Cinematographers", "Editor",
    "Editors", "Casting", "Casting Department", "Casting By",
    "Production Designer", "Production Designers", "Art Direction",
    "Art Direction by", "Set Decoration", "Set Decoration by",
    "Set Decorators", "Costume Design", "Costume Design by",
    "Costume Designer", "Costume Designers", "Makeup Department",
    "Production Management", "Second Unit Director or Assistant Director",
    "Second Unit Directors or Assistant Directors", "Art Department",
    "Sound Department", "Special Effects", "Special Effects by",
    "Visual Effects", "Visual Effects by", "Stunts",
    "Camera and Electrical Department", "Costume and Wardrobe Department",
    "Editorial Department", "Music Department", "Transportation Department",
    "Script and Continuity Department", "Color Department",
    "Animation Department", "Location Management", "Additional Crew",
    "Thanks", "Special Thanks",
}

DIRECTOR_HEADERS = {"Director", "Directors"}
WRITER_HEADERS = {"Writer", "Writers"}
CAST_HEADER = "Cast"

# Noise lines that carry no data, wherever they appear — checked before
# department-header/pair parsing so "Crew verified as complete" (which
# trails the very last department, not just Cast) is still caught.
STATUS_LINE_RE = re.compile(
    r"^(?:\(in credits order\).*|Rest of cast listed alphabetically|Crew verified as complete)$"
)
# IMDB's photo-caption line under a cast member's thumbnail, e.g.
# "Donatas Banionis and Natalya Bondarchuk in Solaris (1972)" — may name a
# completely different film than the one being catalogued. Always
# immediately followed by the real Name line.
CAST_CAPTION_RE = re.compile(r"^.+ in .+\(\d{4}\)$")

UNCREDITED_RE = re.compile(r"\(uncredited\)")
VOICE_RE = re.compile(r"\(voice\)")
ALIAS_RE = re.compile(r"\(as ([^)]+)\)")
WHITESPACE_RE = re.compile(r"\s+")


class CreditsParseError(Exception):
    """Expected, user-fixable failure (unrecognized line/department, truncated pair)."""


def extract_tags(text):
    """Strips (as ALIAS)/(uncredited)/(voice) out of a detail line; returns
    (leftover_or_None, alias_or_None, uncredited_bool, voice_bool)."""
    alias_match = ALIAS_RE.search(text)
    alias = alias_match.group(1) if alias_match else None
    uncredited = bool(UNCREDITED_RE.search(text))
    voice = bool(VOICE_RE.search(text))

    leftover = ALIAS_RE.sub("", text)
    leftover = UNCREDITED_RE.sub("", leftover)
    leftover = VOICE_RE.sub("", leftover)
    leftover = WHITESPACE_RE.sub(" ", leftover).strip()

    return (leftover or None, alias, uncredited, voice)


def parse_credits(text):
    """Returns {"director": [names], "writer": [names], "cast": [entries],
    "crew": {department: [entries]}}. Raises CreditsParseError on anything
    that doesn't fit."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    director = []
    writer = []
    cast = []
    crew = {}
    department = None

    i = 0
    while i < len(lines):
        line = lines[i]

        if STATUS_LINE_RE.match(line):
            i += 1
            continue

        if line in KNOWN_DEPARTMENTS:
            department = line
            i += 1
            continue

        if department is None:
            raise CreditsParseError(f"line {i + 1}: expected a department header, got {line!r}")

        if department == CAST_HEADER and CAST_CAPTION_RE.match(line):
            i += 1
            continue

        # A cast member with no representative photo still gets a caption
        # line, just with no " in Title (Year)" to distinguish it — IMDB
        # simply repeats their bare name once more before the real Name
        # line (e.g. "Vladislav Dvorzhetskiy\nVladislav Dvorzhetskiy\nAnri
        # Berton, pilot"). A character description being byte-identical to
        # the actor's own name is implausible, so treat exact consecutive
        # duplicates in Cast as this same caption artifact.
        if department == CAST_HEADER and i + 1 < len(lines) and lines[i + 1] == line:
            i += 1
            continue

        # Some single-person departments (e.g. a lone Cinematographer with
        # no alias to show) have a bare name and NO detail line at all —
        # the very next line is directly the next department header. Only
        # treat the next line as this entry's detail if it isn't itself the
        # start of a new department/status/cast-caption line.
        name = line
        next_line = lines[i + 1] if i + 1 < len(lines) else None
        next_is_new_unit = next_line is not None and (
            next_line in KNOWN_DEPARTMENTS
            or STATUS_LINE_RE.match(next_line)
            or (department == CAST_HEADER and CAST_CAPTION_RE.match(next_line))
        )

        if next_line is not None and not next_is_new_unit:
            leftover, alias, uncredited, voice = extract_tags(next_line)
            i += 2
        else:
            leftover, alias, uncredited, voice = None, None, False, False
            i += 1

        if department == CAST_HEADER:
            cast.append({
                "name": name, "character": leftover, "alias": alias,
                "uncredited": uncredited, "voice": voice,
            })
        else:
            entry = {
                "name": name, "role": leftover, "alias": alias,
                "uncredited": uncredited, "voice": voice,
            }
            if department in DIRECTOR_HEADERS:
                director.append(name)
            elif department in WRITER_HEADERS:
                writer.append(name)
            crew.setdefault(department, []).append(entry)

    return {"director": director, "writer": writer, "cast": cast, "crew": crew}


def main():
    if len(sys.argv) != 2:
        print("usage: parse_credits.py CREDITS_TXT_PATH", file=sys.stderr)
        return 1

    with open(sys.argv[1], encoding="utf-8") as f:
        text = f.read()

    try:
        result = parse_credits(text)
    except CreditsParseError as exc:
        print(f"credits parse error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
