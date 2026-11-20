#!/usr/bin/env python3
"""Fetch live star counts and languages for the repos the cards feature.

The stat cards and repo footers read these numbers from data/stats.json, so
nothing on the page is a hand-typed snapshot that quietly goes stale.

    GITHUB_TOKEN=ghp_xxx python scripts/fetch_stats.py

Writes: data/stats.json
"""
import json
import os
import sys
import urllib.error
import urllib.request

# (owner, repo) — the three that appear as cards
REPOS = [
    ("S3DFX-CYBER", "FindMyGSoC"),
    ("TENET-DEV-AI", "TENET-AI"),
    ("S3DFX-CYBER", "Claude-Skills-Security"),
]

TOKEN = os.environ.get("GITHUB_TOKEN", "")
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "..", "data", "stats.json")


def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "profile-readme-builder",
        "Accept": "application/vnd.github+json",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def main():
    rows = []
    for owner, repo in REPOS:
        try:
            d = get(f"https://api.github.com/repos/{owner}/{repo}")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                sys.exit("rate limited — set GITHUB_TOKEN and retry")
            print(f"  skip {owner}/{repo}: HTTP {e.code}")
            continue
        rows.append({
            "owner": owner,
            "repo": repo,
            "stars": d.get("stargazers_count", 0),
            "forks": d.get("forks_count", 0),
            "language": d.get("language"),
        })
        print(f"  {owner}/{repo:26s} {d.get('stargazers_count'):>4} stars  {d.get('language')}")

    if not rows:
        sys.exit("no repos fetched — refusing to overwrite stats.json")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({"repos": rows}, open(OUT, "w"), indent=1)
    print(f"\n{len(rows)} repos -> {os.path.relpath(OUT)}")


if __name__ == "__main__":
    main()
