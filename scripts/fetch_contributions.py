#!/usr/bin/env python3
"""Fetch the public contribution calendar and write data/contributions.json.

GitHub's profile page loads the calendar lazily, so this pulls the fragment the
page itself requests — no token, no GraphQL, no scraping of the profile body.

    python scripts/fetch_contributions.py

Writes: data/contributions.json  (then re-run build_cards.py to redraw the card)
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.request

USER = os.environ.get("GH_USER", "S3DFX-CYBER")
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "..", "data", "contributions.json")

URL = f"https://github.com/users/{USER}/contributions"
REQ = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0",
                                          "Accept": "text/html"})


def fetch() -> str:
    with urllib.request.urlopen(REQ, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def parse(html: str) -> dict:
    # cells carry id="contribution-day-component-{weekday}-{week}"
    cells = {}
    for m in re.finditer(
        r'<td[^>]*data-date="(\d{4}-\d{2}-\d{2})"[^>]*'
        r'id="contribution-day-component-(\d+)-(\d+)"[^>]*data-level="(\d)"', html):
        d, row, col, lvl = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        cells[(row, col)] = {"d": d, "l": lvl, "c": 0}

    # counts live only in the tooltips
    for m in re.finditer(r'<tool-tip[^>]*for="contribution-day-component-(\d+)-(\d+)"'
                         r'[^>]*>(.*?)</tool-tip>', html, re.S):
        txt = re.sub(r"\s+", " ", m.group(3)).strip()
        hit = re.match(r"(\d+|No) contribution", txt)
        cnt = 0 if (hit and hit.group(1) == "No") else int(hit.group(1)) if hit else 0
        key = (int(m.group(1)), int(m.group(2)))
        if key in cells:
            cells[key]["c"] = cnt

    if not cells:
        sys.exit("no contribution cells found — GitHub may have changed its markup")

    rows = max(r for r, _ in cells) + 1
    cols = max(c for _, c in cells) + 1
    days = [cells[(r, c)] for r in range(rows) for c in range(cols) if (r, c) in cells]

    # the grid is row-major (weekday rows), so sort before walking days in order
    chrono = sorted(days, key=lambda d: d["d"])
    best = cur = 0
    prev = None
    for d in chrono:
        if d["c"] > 0:
            gap = (dt.date.fromisoformat(d["d"]) -
                   dt.date.fromisoformat(prev)).days if prev else 0
            cur = cur + 1 if gap == 1 else 1
            best = max(best, cur)
            prev = d["d"]
        else:
            cur = 0
            prev = None

    streak = 0
    for d in reversed(chrono):
        if d["c"] > 0:
            streak += 1
        else:
            break

    busiest = max(days, key=lambda d: d["c"])
    return {"generated": dt.date.today().isoformat(), "rows": rows, "cols": cols,
            "total": sum(d["c"] for d in days), "longest_streak": best,
            "current_streak": streak,
            "busiest": {"date": busiest["d"], "count": busiest["c"]},
            "days": days}


if __name__ == "__main__":
    data = parse(fetch())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(data, open(OUT, "w"), indent=0)
    print(f"{data['total']} contributions · streak {data['current_streak']} "
          f"(best {data['longest_streak']}) · wrote {os.path.relpath(OUT)}")
