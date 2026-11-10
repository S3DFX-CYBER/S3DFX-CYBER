#!/usr/bin/env python3
"""Render the S3DFX-CYBER profile cards as self-contained animated SVGs.

Every card carries its own background and its own base64-embedded fonts, so it
looks identical on GitHub's light theme, dark theme, and in any RSS/mirror.
Numbers are a snapshot (taken 2026-11-11); nothing here needs a cron job.

Run from the repo root:  pip install fonttools pillow  &&  python scripts/build_cards.py
Layout is measured with PIL against the real fonts, so the script fails loudly
rather than shipping a card with clipped or overflowing text.
"""
import base64, json, os, shutil, sys
from fontTools.ttLib import TTFont
from PIL import ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("CARDS_OUT") or os.path.join(BASE, "..", "cards")
FONT_DIR = os.environ.get("FONTS_DIR") or os.path.join(BASE, "..", "fonts")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- palette
BG      = "#0A0D0F"
PANEL   = "#0E1316"
CHIP    = "#121A1E"
BORDER  = "#1E282E"
INK     = "#EDF2F3"
MUTED   = "#7B8B92"
ACCENT  = "#3EDC8B"
ACC_DIM = "#1D5740"
WARN    = "#E9B44C"

# ---------------------------------------------------------------- fonts
WOFFS = {
    "geist400": "geist-400.woff",
    "geist600": "geist-600.woff",
    "mono400":  "geistmono-400.woff",
    "serif400": "serif-400.woff",
    "serifit":  "serif-italic.woff",
}

def woff_to_ttf(key, fn):
    ttf = os.path.join(FONT_DIR, f"{key}.ttf")
    f = TTFont(os.path.join(FONT_DIR, fn))
    fam = f["name"].getDebugName(1)
    sub = f["name"].getDebugName(2)
    f.flavor = None
    f.save(ttf)
    return ttf, fam, sub

FONTS = {}          # key -> (ttf_path, family, subfamily, base64woff)
for k, fn in WOFFS.items():
    ttf, fam, sub = woff_to_ttf(k, fn)
    b64 = base64.b64encode(open(os.path.join(FONT_DIR, fn), "rb").read()).decode()
    FONTS[k] = (ttf, fam, sub, b64)

print("fonts:", {k: (v[1], v[2]) for k, v in FONTS.items()})

_measure_cache = {}
def measure(key, size, text, tracking=0.0):
    ck = (key, size, text)
    if ck not in _measure_cache:
        f = ImageFont.truetype(FONTS[key][0], size)
        _measure_cache[ck] = f.getlength(text)
    return _measure_cache[ck] + tracking * max(0, len(text) - 1)

ISSUES = []
def fit(text, key, size, maxw, tracking=0.0, where=""):
    w = measure(key, size, text, tracking)
    if w > maxw + 0.5:
        ISSUES.append(f"OVERFLOW {where}: '{text}' {w:.1f} > {maxw:.1f}")
    return w

def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))

def wrap(text, key, size, maxw):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if measure(key, size, t) <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = wd
    if cur:
        lines.append(cur)
    return lines

def font_face(key):
    _, fam, sub, b64 = FONTS[key]
    style = "italic" if "italic" in sub.lower() else "normal"
    weight = "600" if "600" in sub else "400"
    return (f"@font-face{{font-family:'{fam}';font-style:{style};font-weight:{weight};"
            f"src:url(data:font/woff;base64,{b64}) format('woff');}}")

def svg_open(w, h, keys, title):
    faces = "".join(font_face(k) for k in dict.fromkeys(keys))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}" height="{h:g}" '
            f'viewBox="0 0 {w:g} {h:g}" role="img" aria-label="{esc(title)}">'
            f"<title>{esc(title)}</title><style>{faces}</style>")

def txt(x, y, s, key, size, fill, tracking=0.0, weight=None, anchor=None, opacity=None):
    _, fam, sub, _ = FONTS[key]
    w = weight or ("600" if "600" in sub else "400")
    st = "italic" if "italic" in sub.lower() else "normal"
    a = f' text-anchor="{anchor}"' if anchor else ""
    ls = f' letter-spacing="{tracking}"' if tracking else ""
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return (f'<text x="{x:g}" y="{y:g}" font-family="{fam}" font-size="{size:g}" '
            f'font-weight="{w}" font-style="{st}" fill="{fill}"{ls}{a}{op}>{esc(s)}</text>')

def card_bg(w, h, r=16, fill=BG, stroke=BORDER):
    return (f'<rect x="0.5" y="0.5" width="{w-1:g}" height="{h-1:g}" rx="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>')

def dot(x, y, r, fill, opacity=None, cls=""):
    op = f' opacity="{opacity}"' if opacity is not None else ""
    c = f' class="{cls}"' if cls else ""
    return f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="{fill}"{op}{c}/>'

def star(cx, cy, r, fill):
    import math
    pts = []
    for i in range(10):
        ang = math.radians(-90 + i * 36)
        rad = r if i % 2 == 0 else r * 0.42
        pts.append(f"{cx + rad*math.cos(ang):.1f},{cy + rad*math.sin(ang):.1f}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill}"/>'

def write(name, body, w, h):
    open(os.path.join(OUT, name), "w").write(body + "</svg>\n")
    return os.path.getsize(os.path.join(OUT, name))

# ================================================================ 1. HERO
W, H = 880, 264
P = 46
fams = ["geist600", "geist400", "mono400"]
s = [svg_open(W, H, fams,
     "Savio Dsouza — AppSec engineer and AI security researcher in Mumbai. "
     "CVE-2026-40316. Co-lead of OWASP Top 10 for LLM Applications, LLM09:2026.")]
s.append("<defs>"
         '<radialGradient id="glow" cx="0.12" cy="0.05" r="0.9">'
         f'<stop offset="0" stop-color="{ACCENT}" stop-opacity="0.16"/>'
         f'<stop offset="0.55" stop-color="{ACCENT}" stop-opacity="0.02"/>'
         f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/>'
         "</radialGradient>"
         '<linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">'
         f'<stop offset="0" stop-color="{ACCENT}" stop-opacity="0.55"/>'
         f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/>'
         "</linearGradient>"
         "</defs>")
s.append(card_bg(W, H))
s.append(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="16" fill="url(#glow)"/>')
# faint concentric arcs, right edge
for r_, o in ((150, 0.30), (108, 0.45), (66, 0.60)):
    s.append(f'<circle cx="{W+16}" cy="132" r="{r_}" fill="none" stroke="{BORDER}" '
             f'stroke-opacity="{o}" stroke-width="1"/>')
s.append(dot(W + 16 - 66, 132, 3, ACCENT, 0.9))
s.append(dot(W + 16 - 108, 132, 2, ACCENT, 0.45))

s.append(txt(P, 56, "SECURITY ENGINEERING / AI SAFETY", "mono400", 11.5, ACCENT, 2.4))
fit("SECURITY ENGINEERING / AI SAFETY", "mono400", 11.5, 420, 2.4, "hero kicker")

s.append(txt(W - P, 56, "MUMBAI, IN", "mono400", 11.5, MUTED, 2.4, anchor="end"))
fit("MUMBAI, IN", "mono400", 11.5, 160, 2.4, "hero loc")

name = "Savio Dsouza"
s.append(txt(P - 2, 132, name, "geist600", 60, INK, -1.2))
fit(name, "geist600", 60, W - 2 * P - 150, -1.2, "hero name")

sub = "AppSec engineer and AI security researcher."
s.append(txt(P, 168, sub, "geist400", 19, MUTED))
fit(sub, "geist400", 19, W - 2 * P - 120, 0, "hero sub")

s.append(f'<rect x="{P}" y="196" width="88" height="1.5" fill="url(#rule)"/>')

# chips
chips = [("CVE-2026-40316", WARN), ("OWASP TOP 10 LLM · LLM09 CO-LEAD", ACCENT),
         ("OWASP BLT", MUTED)]
cx = P
for label, col in chips:
    tw = fit(label, "mono400", 11, 300, 1.0, "hero chip")
    cw = tw + 34
    s.append(f'<rect x="{cx:g}" y="214" width="{cw:g}" height="30" rx="6" '
             f'fill="{CHIP}" stroke="{BORDER}"/>')
    s.append(dot(cx + 13, 229, 3, col))
    s.append(txt(cx + 22, 233.5, label, "mono400", 11, INK, 1.0))
    cx += cw + 10
if cx > W - P:
    ISSUES.append(f"hero chips overflow: {cx:.0f} > {W-P}")
sizes = {"hero.svg": write("hero.svg", "".join(s), W, H)}

# ================================================================ 2. STATS
SW, SH = 293.333, 214
stats = [
    ("DISCLOSED", "1", "CVE-2026-40316", "public vulnerability credit", WARN),
    ("STANDARD", "LLM09", "OWASP Top 10 for LLMs", "co-lead, 2026 edition", ACCENT),
    ("SHIPPED", "178", "FindMyGSoC", "stars, most-starred repo", ACCENT),
]
for i, (label, value, line1, line2, col) in enumerate(stats, 1):
    s = [svg_open(SW, SH, ["geist600", "geist400", "mono400"],
                  f"{label}: {value}. {line1}, {line2}.")]
    s.append(card_bg(SW, SH, r=14, fill=PANEL))
    s.append(f'<rect x="26" y="30" width="22" height="2" fill="{col}" fill-opacity="0.85"/>')
    s.append(txt(26, 54, label, "mono400", 10.5, MUTED, 2.4))
    fit(label, "mono400", 10.5, SW - 52, 2.4, f"stat{i} label")
    s.append(txt(24, 112, value, "geist600", 44, INK, -1.0))
    fit(value, "geist600", 44, SW - 48, -1.0, f"stat{i} value")
    if i == 3:
        s.append(star(24 + measure("geist600", 44, value, -1.0) + 22, 98, 15, ACCENT))
    s.append(f'<line x1="26" y1="132" x2="{SW-26}" y2="132" stroke="{BORDER}"/>')
    s.append(txt(26, 158, line1, "geist400", 13.5, INK))
    fit(line1, "geist400", 13.5, SW - 52, 0, f"stat{i} l1")
    s.append(txt(26, 177, line2, "geist400", 12.5, MUTED))
    fit(line2, "geist400", 12.5, SW - 52, 0, f"stat{i} l2")
    sizes[f"stat-{i}.svg"] = write(f"stat-{i}.svg", "".join(s), SW, SH)

# ================================================================ 3. TITLE (light + dark)
TW, TH = 880, 74
for scheme in ("dark", "light"):
    ink = INK if scheme == "dark" else "#0A0D0F"
    rule = BORDER if scheme == "dark" else "#DCE2E5"
    muted = MUTED if scheme == "dark" else "#5C6B72"
    s = [svg_open(TW, TH, ["geist600", "mono400"], "What I'm building")]
    s.append(txt(0, 44, "What I'm building", "geist600", 25, ink, -0.4))
    tw = measure("geist600", 25, "What I'm building", -0.4)
    s.append(f'<line x1="{tw+18:.1f}" y1="36" x2="{TW}" y2="36" stroke="{rule}" stroke-width="1"/>')
    s.append(txt(TW, 44, "03 PROJECTS", "mono400", 10.5, muted, 2.4, anchor="end"))
    sizes[f"title-{scheme}.svg"] = write(f"title-{scheme}.svg", "".join(s), TW, TH)

# ================================================================ 4. REPO CARDS
RW, RH = 293.333, 200
repos = [
    ("01", "FindMyGSoC",
     "Filter all 184 selected GSoC orgs by stack, language and domain. No install.",
     "HTML · 178 STARS", "findmygsoc.vercel.app"),
    ("02", "TENET-AI",
     "LLM firewall: blocks prompt injection, jailbreaks and data extraction under 10ms.",
     "Python · MIT", "tenet-aiorg.vercel.app"),
    ("03", "Claude-Skills-Security",
     "A production-grade security triage skill for AI agents.",
     "SKILL · 8 STARS", "github"),
]
for idx, name, desc, foot, link in repos:
    s = [svg_open(RW, RH, ["geist600", "geist400", "mono400"],
                  f"{name}: {desc} {foot}")]
    s.append(card_bg(RW, RH, r=14, fill=PANEL))
    s.append(txt(24, 40, idx, "mono400", 10.5, ACC_DIM, 2.0))
    s.append(txt(RW - 24, 40, "REPO", "mono400", 10.5, "#33424A", 2.0, anchor="end"))
    ns = 19 if measure("geist600", 19, name) <= RW - 48 else 16
    s.append(txt(24, 74, name, "geist600", ns, INK, -0.3))
    fit(name, "geist600", ns, RW - 44, -0.3, f"repo {name} title")
    y = 100
    for ln in wrap(desc, "geist400", 13, RW - 48)[:3]:
        s.append(txt(24, y, ln, "geist400", 13, MUTED))
        fit(ln, "geist400", 13, RW - 44, 0, f"repo {name} desc")
        y += 19
    s.append(f'<line x1="24" y1="{RH-40}" x2="{RW-24}" y2="{RH-40}" stroke="{BORDER}"/>')
    s.append(txt(24, RH - 17, foot, "mono400", 10, ACCENT, 0.8))
    fit(foot, "mono400", 10, RW - 150, 0.8, f"repo {name} foot")
    s.append(txt(RW - 24, RH - 17, link, "mono400", 9.5, "#6C7D85", 0.4, anchor="end"))
    fit(link, "mono400", 9.5, 140, 0.4, f"repo {name} link")
    sizes[f"repo-{idx}.svg"] = write(f"repo-{idx}.svg", "".join(s), RW, RH)

# ================================================================ 5. STACK
KW, KH = 880, 152
s = [svg_open(KW, KH, ["geist400", "mono400"],
              "Stack: Semgrep, SARIF, SonarCloud, Nettacker, GitHub Actions, FastAPI, "
              "Cloudflare Workers, D1, Redis, ChromaDB, sentence-transformers.")]
s.append(card_bg(KW, KH, r=14, fill=PANEL))
s.append(txt(30, 40, "STACK", "mono400", 10.5, MUTED, 2.4))
rows = [("SECURITY", ["Semgrep", "SARIF", "SonarCloud", "Nettacker", "GitHub Actions"], 60),
        ("AI / INFRA", ["FastAPI", "Cloudflare Workers", "D1", "Redis", "ChromaDB",
                        "sentence-transformers"], 106)]
for label, items, top in rows:
    s.append(txt(30, top + 18, label, "mono400", 10, ACC_DIM, 1.8))
    x = 150
    for it in items:
        tw = measure("mono400", 11, it, 0.6)
        w_ = tw + 26
        if x + w_ > KW - 30:
            ISSUES.append(f"stack row overflow at '{it}'")
        s.append(f'<rect x="{x:g}" y="{top:g}" width="{w_:g}" height="28" rx="6" '
                 f'fill="{CHIP}" stroke="{BORDER}"/>')
        s.append(txt(x + 13, top + 18.5, it, "mono400", 11, INK, 0.6))
        x += w_ + 8
sizes["stack.svg"] = write("stack.svg", "".join(s), KW, KH)

# ================================================================ 6. QUOTE
QW, QH = 880, 108
s = [svg_open(QW, QH, ["serifit"], "Engineer by choice.")]
s.append(card_bg(QW, QH, r=14))
s.append(f'<rect x="0.5" y="0.5" width="{QW-1}" height="{QH-1}" rx="14" fill="url(#q)"/>')
s.insert(1, f'<defs><radialGradient id="q" cx="0.5" cy="0.5" r="0.75">'
            f'<stop offset="0" stop-color="{ACCENT}" stop-opacity="0.06"/>'
            f'<stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></radialGradient></defs>')
s.append(txt(QW/2, 62, "Engineer by choice.", "serifit", 27, INK, 0, anchor="middle"))
s.append(txt(QW/2, 84, "OPEN TO SECURITY & AI ENGINEERING ROLES", "mono400", 10, MUTED,
             2.6, anchor="middle"))
# mono font needed for the small line
s[0] = s[0].replace("</style>", font_face("mono400") + "</style>")
sizes["quote.svg"] = write("quote.svg", "".join(s), QW, QH)

print(json.dumps(sizes, indent=1))
if ISSUES:
    print("\n!! LAYOUT ISSUES")
    for i in ISSUES:
        print("  ", i)
    sys.exit(1)
print("\nno overflow issues")
