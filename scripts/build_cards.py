#!/usr/bin/env python3
"""Render the S3DFX-CYBER profile cards as self-contained animated SVGs.

Colour system: a duotone. Pink and white only.
  · canvas + surface are the 60% (near-black, tinted plum)
  · white is the 30% — every piece of body copy and every number
  · pink is the 10% — one accent, used for identity and state, never as fill
Hierarchy comes from weight and space, not from extra hues. The heatmap is the
one place a tint ramp is allowed, because there the colour *is* the data.

Motion is CSS keyframes inside the SVG, so it plays on GitHub without JS:
staggered rise on the hero, a slow ring rotation, a blinking caret, and the
contribution cells popping in left to right. Everything stops dead under
prefers-reduced-motion.

Run from the repo root:  pip install fonttools pillow  &&  python scripts/build_cards.py
Refresh the graph first with:  python scripts/fetch_contributions.py
Layout is measured with PIL against the real fonts, so the script fails loudly
rather than shipping a card with clipped or overflowing text.
"""
import base64, json, os, sys
from fontTools.ttLib import TTFont
from PIL import ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("CARDS_OUT") or os.path.join(BASE, "..", "cards")
FONT_DIR = os.environ.get("FONTS_DIR") or os.path.join(BASE, "..", "fonts")
ASSETS = os.environ.get("ASSETS_DIR") or os.path.join(BASE, "..", "assets")
DATA = os.environ.get("DATA_DIR") or os.path.join(BASE, "..", "data")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- palette
CANVAS  = "#0B0910"
SURFACE = "#120E17"
CHIP    = "#171320"
BORDER  = "#251D30"
INK     = "#F7F5F9"
MUTED   = "#A79EB0"
PINK    = "#FF77B0"   # the single accent
PINK_D  = "#E23C86"   # graphic fills, where 3:1 is enough
WHITE   = "#FFFFFF"
HEAT    = ["#1A1420", "#4A1832", "#8E2055", "#C9327A", "#FF77B0"]

def _lum(hexs):
    c = [int(hexs[i:i+2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

# ---------------------------------------------------------------- fonts
WOFFS = {"geist400": "geist-400.woff", "geist600": "geist-600.woff",
         "mono400": "geistmono-400.woff", "serif400": "serif-400.woff",
         "serifit": "serif-italic.woff"}
FONTS = {}
for k, fn in WOFFS.items():
    ttf = os.path.join(FONT_DIR, f"{k}.ttf")
    f = TTFont(os.path.join(FONT_DIR, fn))
    fam, sub = f["name"].getDebugName(1), f["name"].getDebugName(2)
    f.flavor = None
    f.save(ttf)
    b64 = base64.b64encode(open(os.path.join(FONT_DIR, fn), "rb").read()).decode()
    FONTS[k] = (ttf, fam, sub, b64)

_mc = {}
def measure(key, size, text, tracking=0.0):
    ck = (key, size, text)
    if ck not in _mc:
        _mc[ck] = ImageFont.truetype(FONTS[key][0], size).getlength(text)
    return _mc[ck] + tracking * max(0, len(text) - 1)

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
    if cur: lines.append(cur)
    return lines

def font_face(key):
    _, fam, sub, b64 = FONTS[key]
    style = "italic" if "italic" in sub.lower() else "normal"
    weight = "600" if "600" in sub else "400"
    return (f"@font-face{{font-family:'{fam}';font-style:{style};font-weight:{weight};"
            f"src:url(data:font/woff;base64,{b64}) format('woff');}}")

MOTION = """
@keyframes rise{from{opacity:0;transform:translateY(9px)}to{opacity:1;transform:translateY(0)}}
@keyframes fade{from{opacity:0}to{opacity:1}}
@keyframes pop{0%{opacity:0;transform:scale(.35)}70%{transform:scale(1.06)}100%{opacity:1;transform:scale(1)}}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes blink{0%,45%{opacity:1}55%,100%{opacity:0}}
@keyframes breathe{0%,100%{opacity:.45}50%{opacity:.95}}
@keyframes sweep{from{opacity:0}to{opacity:1}}
.r{animation:rise .75s cubic-bezier(.22,.7,.3,1) both}
.f{animation:fade .9s ease-out both}
.p{animation:pop .5s cubic-bezier(.22,.7,.3,1) both}
.spin{animation:spin 44s linear infinite;transform-origin:734px 132px}
.caret{animation:blink 1.15s steps(1,end) infinite}
.breathe{animation:breathe 5.5s ease-in-out infinite}
@media (prefers-reduced-motion:reduce){*{animation:none!important}}
"""

def svg_open(w, h, keys, title):
    faces = "".join(font_face(k) for k in dict.fromkeys(keys))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w:g}" height="{h:g}" viewBox="0 0 {w:g} {h:g}" '
            f'role="img" aria-label="{esc(title)}">'
            f"<title>{esc(title)}</title><style>{faces}{MOTION}</style>")

def txt(x, y, s, key, size, fill, tracking=0.0, weight=None, anchor=None,
        opacity=None, cls=None, delay=None):
    _, fam, sub, _ = FONTS[key]
    w = weight or ("600" if "600" in sub else "400")
    st = "italic" if "italic" in sub.lower() else "normal"
    a = f' text-anchor="{anchor}"' if anchor else ""
    ls = f' letter-spacing="{tracking}"' if tracking else ""
    op = f' opacity="{opacity}"' if opacity is not None else ""
    c = f' class="{cls}"' if cls else ""
    d = f' style="animation-delay:{delay}s"' if delay is not None else ""
    return (f'<text x="{x:g}" y="{y:g}" font-family="{fam}" font-size="{size:g}" '
            f'font-weight="{w}" font-style="{st}" fill="{fill}"{ls}{a}{op}{c}{d}>{esc(s)}</text>')

def card_bg(w, h, r=16, fill=CANVAS, stroke=BORDER):
    return (f'<rect x="0.5" y="0.5" width="{w-1:g}" height="{h-1:g}" rx="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>')

def dot(x, y, r, fill, opacity=None, cls=None):
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

def arc(cx, cy, r, a1, a2, stroke, width, op=1.0):
    import math
    x1, y1 = cx + r*math.cos(math.radians(a1)), cy + r*math.sin(math.radians(a1))
    x2, y2 = cx + r*math.cos(math.radians(a2)), cy + r*math.sin(math.radians(a2))
    return (f'<path d="M {x1:.2f} {y1:.2f} A {r:g} {r:g} 0 0 1 {x2:.2f} {y2:.2f}" '
            f'fill="none" stroke="{stroke}" stroke-width="{width:g}" stroke-opacity="{op}" '
            f'stroke-linecap="round"/>')

def write(name, body, w, h):
    open(os.path.join(OUT, name), "w").write(body + "</svg>\n")
    return os.path.getsize(os.path.join(OUT, name))

PORTRAIT = os.path.join(ASSETS, "portrait.jpg")
P64 = base64.b64encode(open(PORTRAIT, "rb").read()).decode() if os.path.exists(PORTRAIT) else None
if not P64:
    ISSUES.append(f"missing portrait at {PORTRAIT}")

sizes = {}

# ================================================================ 1. HERO
W, H, P = 880, 264, 46
s = [svg_open(W, H, ["geist600", "geist400", "mono400"],
     "Savio Dsouza — AppSec engineer and AI security researcher in Mumbai. "
     "CVE-2026-40316. Co-lead of OWASP Top 10 for LLM Applications, LLM09:2026.")]
s.append("<defs>"
         '<radialGradient id="glow" cx="0.12" cy="0.02" r="0.9">'
         f'<stop offset="0" stop-color="{PINK}" stop-opacity="0.16"/>'
         f'<stop offset="0.5" stop-color="{PINK}" stop-opacity="0.03"/>'
         f'<stop offset="1" stop-color="{PINK}" stop-opacity="0"/>'
         "</radialGradient>"
         '<clipPath id="pf"><circle cx="734" cy="132" r="100"/></clipPath></defs>')
s.append(card_bg(W, H))
s.append(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="16" fill="url(#glow)" class="breathe"/>')

s.append(txt(P, 60, "SECURITY ENGINEERING / AI SAFETY", "mono400", 11.5, PINK, 2.4,
             cls="r", delay=0.05))
fit("SECURITY ENGINEERING / AI SAFETY", "mono400", 11.5, 380, 2.4, "hero kicker")
_kw = measure("mono400", 11.5, "SECURITY ENGINEERING / AI SAFETY", 2.4)
s.append(f'<rect x="{P + _kw + 9:.1f}" y="49" width="7" height="13" rx="1" '
         f'fill="{PINK}" class="caret"/>')
s.append(txt(610, 60, "MUMBAI, IN", "mono400", 11.5, MUTED, 2.4, anchor="end",
             cls="f", delay=0.5))

s.append(txt(P - 2, 132, "Savio Dsouza", "geist600", 60, INK, -1.2, cls="r", delay=0.15))
fit("Savio Dsouza", "geist600", 60, 470, -1.2, "hero name")

s.append(txt(P, 168, "AppSec engineer and AI security researcher.", "geist400", 19, MUTED,
             cls="r", delay=0.3))
fit("AppSec engineer and AI security researcher.", "geist400", 19, 470, 0, "hero sub")

s.append(f'<g class="r" style="animation-delay:0.42s">'
         f'<rect x="{P}" y="190" width="120" height="3" rx="1.5" fill="{PINK}" fill-opacity="0.9"/>'
         f'<rect x="{P+74}" y="190" width="46" height="3" rx="1.5" fill="{WHITE}" fill-opacity="0.85"/></g>')

chips = [("CVE-2026-40316", PINK), ("OWASP LLM09 CO-LEAD", WHITE), ("OWASP BLT", PINK)]
cx = P
for i, (label, col) in enumerate(chips):
    tw = fit(label, "mono400", 11, 260, 1.0, "hero chip")
    cw = tw + 34
    s.append(f'<g class="r" style="animation-delay:{0.54 + i*0.08}s">')
    s.append(f'<rect x="{cx:g}" y="214" width="{cw:g}" height="30" rx="6" '
             f'fill="{CHIP}" stroke="{BORDER}"/>')
    s.append(dot(cx + 13, 229, 3, col))
    s.append(txt(cx + 22, 233.5, label, "mono400", 11, INK, 1.0))
    s.append("</g>")
    cx += cw + 10
if cx > 600:
    ISSUES.append(f"hero chips overflow: {cx:.0f} > 600")

PCX, PCY, PR = 734, 132, 100
s.append(f'<circle cx="{PCX}" cy="{PCY}" r="{PR+9}" fill="none" stroke="{BORDER}"/>')
if P64:
    s.append(f'<image x="{PCX-PR}" y="{PCY-PR}" width="{2*PR}" height="{2*PR}" '
             f'clip-path="url(#pf)" preserveAspectRatio="xMidYMid slice" '
             f'xlink:href="data:image/jpeg;base64,{P64}" '
             f'href="data:image/jpeg;base64,{P64}" class="f" '
             f'style="animation-delay:0.2s"/>')
# one rotating accent arc, and a fixed white one — the ring turns, the portrait does not
s.append(f'<g class="spin"><path d="M {PCX} {PCY-PR-9} A {PR+9} {PR+9} 0 0 1 {PCX+PR+9} {PCY}" '
         f'fill="none" stroke="{PINK}" stroke-width="2.5" stroke-linecap="round"/></g>')
s.append(arc(PCX, PCY, PR + 9, 90, 270, WHITE, 2.5, 0.55))
sizes["hero.svg"] = write("hero.svg", "".join(s), W, H)

# ================================================================ 2. CONTRIBUTIONS
KW, KH = 880, 236
try:
    data = json.load(open(os.path.join(DATA, "contributions.json")))
except FileNotFoundError:
    data = None
    ISSUES.append("missing data/contributions.json — run scripts/fetch_contributions.py")

if data:
    s = [svg_open(KW, KH, ["geist600", "geist400", "mono400"],
         f"Contribution graph: {data['total']} contributions in the last 12 months, "
         f"current streak {data['current_streak']} days, longest streak "
         f"{data['longest_streak']} days.")]
    s.append(card_bg(KW, KH, r=14, fill=SURFACE))
    s.append(txt(30, 42, "CONTRIBUTIONS", "mono400", 10.5, PINK, 2.4, cls="f", delay=0.05))
    s.append(txt(KW - 30, 42, f"{data['total']:,} IN THE LAST 12 MONTHS", "mono400", 10.5,
                 MUTED, 1.8, anchor="end", cls="f", delay=0.2))

    CELL, GAP = 11.0, 3.0
    grid_w = data["cols"] * (CELL + GAP) - GAP
    gx = (KW - grid_w) / 2
    gy = 62.0
    by_col = {}
    for d in data["days"]:
        pass
    # cells come row-major (weekday rows, week columns); delay runs left to right
    order = {}
    for i, d in enumerate(data["days"]):
        r_, c_ = divmod(i, data["cols"])
        order[(r_, c_)] = d
    for r_ in range(data["rows"]):
        for c_ in range(data["cols"]):
            d = order.get((r_, c_))
            if not d:
                continue
            x = gx + c_ * (CELL + GAP)
            y = gy + r_ * (CELL + GAP)
            delay = round(0.25 + c_ * 0.011 + r_ * 0.004, 3)
            s.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{CELL:g}" height="{CELL:g}" rx="2.5" '
                     f'fill="{HEAT[min(d["l"], 4)]}" class="p" '
                     f'style="animation-delay:{delay}s;transform-origin:{x+CELL/2:.1f}px {y+CELL/2:.1f}px"/>')
    # legend
    lx = KW - 30 - (5 * (CELL + GAP) - GAP) - 46
    ly = gy + data["rows"] * (CELL + GAP) + 12
    s.append(txt(lx - 8, ly + 9, "LESS", "mono400", 9, MUTED, 1.2, anchor="end"))
    for i, col in enumerate(HEAT):
        s.append(f'<rect x="{lx + i*(CELL+GAP):.1f}" y="{ly:.1f}" width="{CELL:g}" height="{CELL:g}" '
                 f'rx="2.5" fill="{col}"/>')
    s.append(txt(lx + 5 * (CELL + GAP) + 4, ly + 9, "MORE", "mono400", 9, MUTED, 1.2))

    # three stats along the bottom
    stats_row = [("CURRENT STREAK", f"{data['current_streak']} DAYS"),
                 ("LONGEST STREAK", f"{data['longest_streak']} DAYS"),
                 ("BUSIEST DAY", f"{data['busiest']['count']} ON {data['busiest']['date']}")]
    bx = 30
    for i, (lab, val) in enumerate(stats_row):
        s.append(txt(bx, KH - 30, lab, "mono400", 9, MUTED, 1.6, cls="f", delay=0.5 + i*0.1))
        s.append(txt(bx, KH - 12, val, "geist600", 14, INK, -0.1, cls="f", delay=0.55 + i*0.1))
        fit(val, "geist600", 14, 240, -0.1, f"contrib stat {lab}")
        bx += 250
    sizes["contributions.svg"] = write("contributions.svg", "".join(s), KW, KH)

# ================================================================ 3. STATS
SW, SH = 293.333, 214
stats = [("DISCLOSED", "1", "CVE-2026-40316", "public vulnerability credit"),
         ("STANDARD", "LLM09", "OWASP Top 10 for LLMs", "co-lead, 2026 edition"),
         ("SHIPPED", "178", "FindMyGSoC", "stars, most-starred repo")]
for i, (label, value, l1, l2) in enumerate(stats, 1):
    s = [svg_open(SW, SH, ["geist600", "geist400", "mono400"],
                  f"{label}: {value}. {l1}, {l2}.")]
    s.append(card_bg(SW, SH, r=14, fill=SURFACE))
    s.append(f'<rect x="26" y="24" width="46" height="3" rx="1.5" fill="{PINK}" '
             f'fill-opacity="0.9" class="f" style="animation-delay:0.1s"/>')
    s.append(txt(26, 56, label, "mono400", 10.5, MUTED, 2.4, cls="f", delay=0.15))
    fit(label, "mono400", 10.5, SW - 52, 2.4, f"stat{i} label")
    s.append(txt(24, 116, value, "geist600", 44, INK, -1.0, cls="r", delay=0.25))
    fit(value, "geist600", 44, SW - 48, -1.0, f"stat{i} value")
    if i == 3:
        s.append(star(24 + measure("geist600", 44, value, -1.0) + 22, 102, 15, PINK))
    s.append(f'<line x1="26" y1="136" x2="{SW-26:.0f}" y2="136" stroke="{BORDER}"/>')
    s.append(txt(26, 162, l1, "geist400", 13.5, INK, cls="f", delay=0.35))
    fit(l1, "geist400", 13.5, SW - 52, 0, f"stat{i} l1")
    s.append(txt(26, 181, l2, "geist400", 12.5, MUTED, cls="f", delay=0.42))
    fit(l2, "geist400", 12.5, SW - 52, 0, f"stat{i} l2")
    sizes[f"stat-{i}.svg"] = write(f"stat-{i}.svg", "".join(s), SW, SH)

# ================================================================ 4. TITLE
TW, TH = 880, 74
for scheme in ("dark", "light"):
    ink = INK if scheme == "dark" else "#0B0910"
    rule = BORDER if scheme == "dark" else "#E2DCE6"
    muted = MUTED if scheme == "dark" else "#6B6274"
    accent = PINK if scheme == "dark" else "#C42B74"
    s = [svg_open(TW, TH, ["geist600", "mono400"], "What I'm building")]
    s.append(txt(0, 44, "What I'm building", "geist600", 25, ink, -0.4))
    tw = measure("geist600", 25, "What I'm building", -0.4)
    s.append(f'<line x1="{tw+18:.1f}" y1="36" x2="{TW}" y2="36" stroke="{rule}"/>')
    s.append(txt(TW, 44, "03 PROJECTS", "mono400", 10.5, accent, 2.4, anchor="end"))
    sizes[f"title-{scheme}.svg"] = write(f"title-{scheme}.svg", "".join(s), TW, TH)

# ================================================================ 5. REPOS
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
    s.append(card_bg(RW, RH, r=14, fill=SURFACE))
    s.append(txt(24, 40, idx, "mono400", 10.5, PINK, 2.0, cls="f", delay=0.1))
    s.append(txt(RW - 24, 40, "REPO", "mono400", 10.5, "#3D3448", 2.0, anchor="end"))
    ns = 19 if measure("geist600", 19, name) <= RW - 48 else 16
    s.append(txt(24, 74, name, "geist600", ns, INK, -0.3, cls="r", delay=0.2))
    fit(name, "geist600", ns, RW - 44, -0.3, f"repo {name} title")
    y = 100
    for ln in wrap(desc, "geist400", 13, RW - 48)[:3]:
        s.append(txt(24, y, ln, "geist400", 13, MUTED, cls="f", delay=0.3))
        fit(ln, "geist400", 13, RW - 44, 0, f"repo {name} desc")
        y += 19
    s.append(f'<line x1="24" y1="{RH-40}" x2="{RW-24:.0f}" y2="{RH-40}" stroke="{BORDER}"/>')
    s.append(txt(24, RH - 17, foot, "mono400", 10, PINK, 0.8))
    fit(foot, "mono400", 10, RW - 150, 0.8, f"repo {name} foot")
    s.append(txt(RW - 24, RH - 17, link, "mono400", 9.5, "#7A6F86", 0.4, anchor="end"))
    fit(link, "mono400", 9.5, 140, 0.4, f"repo {name} link")
    sizes[f"repo-{idx}.svg"] = write(f"repo-{idx}.svg", "".join(s), RW, RH)

# ================================================================ 6. STACK
KW2, KH2 = 880, 214
s = [svg_open(KW2, KH2, ["geist400", "mono400"],
              "Stack. AI engineering: PyTorch, Transformers, LangChain, LlamaIndex, "
              "ChromaDB, pgvector, FastAPI. AI security: OWASP LLM Top 10, Garak, PyRIT, "
              "NeMo Guardrails, Semgrep, SARIF, Presidio. Platform: Python, Docker, "
              "Cloudflare Workers, Redis, GitHub Actions, Vercel.")]
s.append(card_bg(KW2, KH2, r=14, fill=SURFACE))
s.append(txt(30, 40, "STACK", "mono400", 10.5, MUTED, 2.4, cls="f", delay=0.05))
rows_ = [("AI ENGINEERING",
          ["PyTorch", "Transformers", "LangChain", "LlamaIndex", "ChromaDB",
           "pgvector", "FastAPI"], 62),
         ("AI SECURITY",
          ["OWASP LLM Top 10", "Garak", "PyRIT", "NeMo Guardrails", "Semgrep", "SARIF",
           "Presidio"], 112),
         ("PLATFORM",
          ["Python", "Docker", "Cloudflare Workers", "Redis", "GitHub Actions", "Vercel"],
          162)]
for ri, (label, items, top) in enumerate(rows_):
    s.append(txt(30, top + 18, label, "mono400", 9.5, PINK, 1.6, cls="f", delay=0.1 + ri*0.1))
    x = 150
    for ci, it in enumerate(items):
        tw = measure("mono400", 11, it, 0.6)
        w_ = tw + 26
        if x + w_ > KW2 - 30:
            ISSUES.append(f"stack row '{label}' overflow at '{it}' ({x+w_:.0f})")
        s.append(f'<g class="f" style="animation-delay:{0.16 + ri*0.1 + ci*0.03:.2f}s">')
        s.append(f'<rect x="{x:g}" y="{top:g}" width="{w_:g}" height="28" rx="6" '
                 f'fill="{CHIP}" stroke="{BORDER}"/>')
        s.append(txt(x + 13, top + 18.5, it, "mono400", 11, INK, 0.6))
        s.append("</g>")
        x += w_ + 8
sizes["stack.svg"] = write("stack.svg", "".join(s), KW2, KH2)

# ================================================================ 7. QUOTE
QW, QH = 880, 112
s = [svg_open(QW, QH, ["serifit", "mono400"], "Engineer by choice.")]
s.append(card_bg(QW, QH, r=14))
s.append(txt(QW/2, 66, "Engineer by choice.", "serifit", 27, INK, 0, anchor="middle",
             cls="r", delay=0.1))
s.append(txt(QW/2, 84, "OPEN TO SECURITY & AI ENGINEERING ROLES", "mono400", 10, MUTED,
             2.6, anchor="middle", cls="f", delay=0.4))
s.append(f'<rect x="{(QW-48)/2:.0f}" y="26" width="48" height="3" rx="1.5" '
         f'fill="{PINK}" fill-opacity="0.9" class="f" style="animation-delay:0.55s"/>')
sizes["quote.svg"] = write("quote.svg", "".join(s), QW, QH)

# ---------------------------------------------------------------- report
print(json.dumps(sizes, indent=1))
print("\ncontrast on surface", SURFACE)
for nm, col, need in (("INK", INK, 7.0), ("MUTED", MUTED, 4.5), ("PINK", PINK, 4.5),
                      ("PINK_D", PINK_D, 3.0), ("WHITE", WHITE, 7.0),
                      ("HEAT-4", HEAT[4], 4.5), ("HEAT-3", HEAT[3], 3.0)):
    r = contrast(col, SURFACE)
    ok = "ok" if r >= need else "LOW"
    print(f"  {nm:8s} {r:5.2f}:1  need {need}  {ok}")
    if r < need:
        ISSUES.append(f"contrast {nm} {r:.2f} < {need}")
if ISSUES:
    print("\n!! ISSUES")
    for i in ISSUES: print("  ", i)
    sys.exit(1)
print("\nno overflow or contrast issues")
