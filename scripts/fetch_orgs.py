#!/usr/bin/env python3
"""Fetch the organisations S3DFX-CYBER has contributed to, and their logos.

Method, so the numbers are auditable rather than asserted:
  1. Search every pull request authored by the user (all pages, not just the
     first hundred — the first hundred alone misses older contributions).
  2. Group by repository owner.
  3. Keep only owners whose GitHub type is "Organization" — contributions to
     another person's repo are not organisations.
  4. Download each organisation's avatar and mask it to a circle at 60px.

Needs a token for a sane rate limit (60 requests/hour without one will not get
through this):

    GITHUB_TOKEN=ghp_xxx python scripts/fetch_orgs.py

Writes: data/orgs.json and assets/logos/<login>.png
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

from PIL import Image, ImageDraw

USER = os.environ.get("GH_USER", "S3DFX-CYBER")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "..", "data", "orgs.json")
LOGO_DIR = os.path.join(BASE, "..", "assets", "logos")
SIZE, SS = 60, 4          # 60px = 2x the 30px it renders at


def api(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "profile-readme-builder",
        "Accept": "application/vnd.github+json",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 403:
            sys.exit("rate limited — set GITHUB_TOKEN and retry")
        raise


def authored_prs():
    """Every PR the user authored, paged. Search caps at 100 per page."""
    owners, page, total = Counter(), 1, None
    while True:
        d = api(f"https://api.github.com/search/issues?q=author:{USER}+type:pr"
                f"&per_page=100&page={page}")
        total = d.get("total_count", total)
        items = d.get("items", [])
        if not items:
            break
        for it in items:
            repo = it["repository_url"].split("/repos/")[-1]
            owners[repo.split("/")[0]] += 1
        page += 1
        time.sleep(0.5)          # be polite to the search API
    return owners, total


def main():
    owners, total = authored_prs()
    print(f"{total} authored pull requests across {len(owners)} owners")

    orgs = []
    for login, count in owners.most_common():
        if login.lower() == USER.lower():
            continue                       # the user's own account is not an org
        try:
            who = api(f"https://api.github.com/users/{login}")
        except Exception as e:
            print(f"  skip {login}: {e}")
            continue
        if who.get("type") != "Organization":
            print(f"  skip {login}: type={who.get('type')}")
            continue
        orgs.append({"login": login, "prs": count, "file": f"logos/{login}.png"})

    os.makedirs(LOGO_DIR, exist_ok=True)
    for o in orgs:
        raw = os.path.join(LOGO_DIR, f"_{o['login']}.png")
        urllib.request.urlretrieve(f"https://github.com/{o['login']}.png?size=256", raw)
        im = Image.open(raw).convert("RGB")
        s = min(im.size)
        im = im.crop(((im.width-s)//2, (im.height-s)//2,
                      (im.width+s)//2, (im.height+s)//2)).resize((SIZE, SIZE), Image.LANCZOS)
        mask = Image.new("L", (SIZE*SS, SIZE*SS), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, SIZE*SS-1, SIZE*SS-1), fill=255)
        rgba = im.convert("RGBA")
        rgba.putalpha(mask.resize((SIZE, SIZE), Image.LANCZOS))
        rgba.save(os.path.join(LOGO_DIR, f"{o['login']}.png"), optimize=True)
        os.remove(raw)
        print(f"  {o['login']:28s} {o['prs']} PRs")

    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    json.dump({"generated": time.strftime("%Y-%m-%d"), "orgs": orgs,
               "org_prs": sum(o["prs"] for o in orgs),
               "total_authored_prs": total,
               "source": "all PRs authored by the user; owners filtered to "
                         "GitHub type=Organization"}, open(DATA, "w"), indent=1)
    print(f"\n{len(orgs)} organisations, {sum(o['prs'] for o in orgs)} PRs "
          f"-> {os.path.relpath(DATA)}")


if __name__ == "__main__":
    main()
