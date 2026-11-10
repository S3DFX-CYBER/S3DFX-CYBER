#!/usr/bin/env python3
"""Render the S3DFX-CYBER profile cards as self-contained animated SVGs.

Two themes, one system. Every card is written twice — `<name>-dark.svg` and
`<name>-light.svg` — and the README picks between them with <picture> and
prefers-color-scheme. That is the only reliable way to theme an SVG that GitHub
serves as an image: the colours are baked into the file, so the file has to change.

Colour system: a duotone, pink and white, in both themes.
  · canvas + surface are the 60%; body copy and every number are the 30% ink
  · pink is the 10% — identity and state only, never used as fill
  · the heatmap is the one place a tint ramp is allowed, because there the
    colour *is* the data
Hierarchy comes from weight and space, not from extra hues.

Motion is CSS keyframes inside the SVG, so it plays on GitHub without JS.
Everything stops under prefers-reduced-motion, and every element's base style is
its final visible state, so a client that refuses to animate still shows the card.

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

# ---------------------------------------------------------------- palettes
PAL = {
    "dark": {
        "canvas": "#0B0910", "surface": "#120E17", "chip": "#171320",
        "border": "#251D30", "ink": "#F7F5F9", "muted": "#A79EB0",
        "accent": "#FF77B0", "accent_d": "#E23C86", "alt": "#FFFFFF",
        "faint": "#3D3448", "link": "#7A6F86",
        "glow": 0.16, "glow2": 0.03,
        "heat": ["#1A1420", "#4A1832", "#8E2055", "#C9327A", "#FF77B0"],
    },
    "light": {
        "canvas": "#FBF8FB", "surface": "#FFFFFF", "chip": "#F6F1F5",
        "border": "#E7DFE8", "ink": "#1A1520", "muted": "#6E6478",
        "accent": "#C42B74", "accent_d": "#E8639E", "alt": "#1A1520",
        "faint": "#C9BECE", "link": "#8A7F94",
        "glow": 0.10, "glow2": 0.02,
        "heat": ["#F2EAEF", "#FBD6E5", "#F5A6C7", "#E1559A", "#C42B74"],
    },
}

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

def card_bg(w, h, p, r=16, surface=False):
    fill = p["surface"] if surface else p["canvas"]
    return (f'<rect x="0.5" y="0.5" width="{w-1:g}" height="{h-1:g}" rx="{r}" '
            f'fill="{fill}" stroke="{p["border"]}" stroke-width="1"/>')

def dot(x, y, r, fill, opacity=None):
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="{fill}"{op}/>'

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

try:
    DATAJ = json.load(open(os.path.join(DATA, "contributions.json")))
except FileNotFoundError:
    DATAJ = None
    ISSUES.append("missing data/contributions.json — run scripts/fetch_contributions.py")

sizes = {}

# ================================================================ HERO
def build_hero(p):
    W, H, P = 880, 264, 46
    s = [svg_open(W, H, ["geist600", "geist400", "mono400"],
         "Savio Dsouza — AppSec engineer and AI security researcher in Mumbai. "
         "CVE-2026-40316. Co-lead of OWASP Top 10 for LLM Applications, LLM09:2026.")]
    s.append("<defs>"
             '<radialGradient id="glow" cx="0.12" cy="0.02" r="0.9">'
             f'<stop offset="0" stop-color="{p["accent"]}" stop-opacity="{p["glow"]}"/>'
             f'<stop offset="0.5" stop-color="{p["accent"]}" stop-opacity="{p["glow2"]}"/>'
             f'<stop offset="1" stop-color="{p["accent"]}" stop-opacity="0"/>'
             "</radialGradient>"
             '<clipPath id="pf"><circle cx="734" cy="132" r="100"/></clipPath></defs>')
    s.append(card_bg(W, H, p))
    s.append(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="16" '
             f'fill="url(#glow)" class="breathe"/>')

    kick = "SECURITY ENGINEERING / AI SAFETY"
    s.append(txt(P, 60, kick, "mono400", 11.5, p["accent"], 2.4, cls="r", delay=0.05))
    fit(kick, "mono400", 11.5, 380, 2.4, "hero kicker")
    s.append(f'<rect x="{P + measure("mono400", 11.5, kick, 2.4) + 9:.1f}" y="49" '
             f'width="7" height="13" rx="1" fill="{p["accent"]}" class="caret"/>')
    s.append(txt(610, 60, "MUMBAI, IN", "mono400", 11.5, p["muted"], 2.4, anchor="end",
                 cls="f", delay=0.5))

    s.append(txt(P - 2, 132, "Savio Dsouza", "geist600", 60, p["ink"], -1.2, cls="r", delay=0.15))
    fit("Savio Dsouza", "geist600", 60, 470, -1.2, "hero name")

    sub = "AppSec engineer and AI security researcher."
    s.append(txt(P, 168, sub, "geist400", 19, p["muted"], cls="r", delay=0.3))
    fit(sub, "geist400", 19, 470, 0, "hero sub")

    s.append(f'<g class="r" style="animation-delay:0.42s">'
             f'<rect x="{P}" y="190" width="120" height="3" rx="1.5" '
             f'fill="{p["accent"]}" fill-opacity="0.9"/>'
             f'<rect x="{P+74}" y="190" width="46" height="3" rx="1.5" '
             f'fill="{p["alt"]}" fill-opacity="0.85"/></g>')

    chips = [("CVE-2026-40316", p["accent"]), ("OWASP LLM09 CO-LEAD", p["alt"]),
             ("OWASP BLT", p["accent"])]
    cx = P
    for i, (label, col) in enumerate(chips):
        tw = fit(label, "mono400", 11, 260, 1.0, "hero chip")
        cw = tw + 34
        s.append(f'<g class="r" style="animation-delay:{0.54 + i*0.08}s">')
        s.append(f'<rect x="{cx:g}" y="214" width="{cw:g}" height="30" rx="6" '
                 f'fill="{p["chip"]}" stroke="{p["border"]}"/>')
        s.append(dot(cx + 13, 229, 3, col))
        s.append(txt(cx + 22, 233.5, label, "mono400", 11, p["ink"], 1.0))
        s.append("</g>")
        cx += cw + 10
    if cx > 600:
        ISSUES.append(f"hero chips overflow: {cx:.0f} > 600")

    PCX, PCY, PR = 734, 132, 100
    s.append(f'<circle cx="{PCX}" cy="{PCY}" r="{PR+9}" fill="none" stroke="{p["border"]}"/>')
    if P64:
        s.append(f'<image x="{PCX-PR}" y="{PCY-PR}" width="{2*PR}" height="{2*PR}" '
                 f'clip-path="url(#pf)" preserveAspectRatio="xMidYMid slice" '
                 f'xlink:href="data:image/jpeg;base64,{P64}" '
                 f'href="data:image/jpeg;base64,{P64}" class="f" '
                 f'style="animation-delay:0.2s"/>')
    s.append(f'<g class="spin"><path d="M {PCX} {PCY-PR-9} A {PR+9} {PR+9} 0 0 1 '
             f'{PCX+PR+9} {PCY}" fill="none" stroke="{p["accent"]}" stroke-width="2.5" '
             f'stroke-linecap="round"/></g>')
    s.append(arc(PCX, PCY, PR + 9, 90, 270, p["alt"], 2.5, 0.55))
    return "".join(s), W, H

# ================================================================ CONTRIBUTIONS
def build_contributions(p):
    d = DATAJ
    KW, KH = 880, 236
    s = [svg_open(KW, KH, ["geist600", "geist400", "mono400"],
         f"Contribution graph: {d['total']} contributions in the last 12 months, "
         f"current streak {d['current_streak']} days, longest streak "
         f"{d['longest_streak']} days.")]
    s.append(card_bg(KW, KH, p, r=14, surface=True))
    s.append(txt(30, 42, "CONTRIBUTIONS", "mono400", 10.5, p["accent"], 2.4, cls="f", delay=0.05))
    s.append(txt(KW - 30, 42, f"{d['total']:,} IN THE LAST 12 MONTHS", "mono400", 10.5,
                 p["muted"], 1.8, anchor="end", cls="f", delay=0.2))

    CELL, GAP = 11.0, 3.0
    grid_w = d["cols"] * (CELL + GAP) - GAP
    gx = (KW - grid_w) / 2
    gy = 62.0
    order = {}
    for i, day in enumerate(d["days"]):
        r_, c_ = divmod(i, d["cols"])
        order[(r_, c_)] = day
    # delay is per column, so the grid wipes in left to right as one movement
    for c_ in range(d["cols"]):
        delay = round(0.25 + c_ * 0.012, 3)
        cells = []
        for r_ in range(d["rows"]):
            day = order.get((r_, c_))
            if not day:
                continue
            x = gx + c_ * (CELL + GAP)
            y = gy + r_ * (CELL + GAP)
            cells.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{CELL:g}" height="{CELL:g}" '
                         f'rx="2.5" fill="{p["heat"][min(day["l"], 4)]}" class="p" '
                         f'style="animation-delay:{delay}s;transform-origin:'
                         f'{x+CELL/2:.1f}px {y+CELL/2:.1f}px"/>')
        s.extend(cells)

    lx = KW - 30 - (5 * (CELL + GAP) - GAP) - 46
    ly = gy + d["rows"] * (CELL + GAP) + 12
    s.append(txt(lx - 8, ly + 9, "LESS", "mono400", 9, p["muted"], 1.2, anchor="end"))
    for i, col in enumerate(p["heat"]):
        s.append(f'<rect x="{lx + i*(CELL+GAP):.1f}" y="{ly:.1f}" width="{CELL:g}" '
                 f'height="{CELL:g}" rx="2.5" fill="{col}" stroke="{p["border"]}" '
                 f'stroke-width="0.5"/>')
    s.append(txt(lx + 5 * (CELL + GAP) + 4, ly + 9, "MORE", "mono400", 9, p["muted"], 1.2))

    stats_row = [("CURRENT STREAK", f"{d['current_streak']} DAYS"),
                 ("LONGEST STREAK", f"{d['longest_streak']} DAYS"),
                 ("BUSIEST DAY", f"{d['busiest']['count']} ON {d['busiest']['date']}")]
    bx = 30
    for i, (lab, val) in enumerate(stats_row):
        s.append(txt(bx, KH - 30, lab, "mono400", 9, p["muted"], 1.6, cls="f",
                     delay=0.5 + i*0.1))
        s.append(txt(bx, KH - 12, val, "geist600", 14, p["ink"], -0.1, cls="f",
                     delay=0.55 + i*0.1))
        fit(val, "geist600", 14, 240, -0.1, f"contrib stat {lab}")
        bx += 250
    return "".join(s), KW, KH

# ================================================================ STATS
def build_stat(p, i, label, value, l1, l2):
    SW, SH = 293.333, 214
    s = [svg_open(SW, SH, ["geist600", "geist400", "mono400"],
                  f"{label}: {value}. {l1}, {l2}.")]
    s.append(card_bg(SW, SH, p, r=14, surface=True))
    s.append(f'<rect x="26" y="24" width="46" height="3" rx="1.5" fill="{p["accent"]}" '
             f'fill-opacity="0.9" class="f" style="animation-delay:0.1s"/>')
    s.append(txt(26, 56, label, "mono400", 10.5, p["muted"], 2.4, cls="f", delay=0.15))
    fit(label, "mono400", 10.5, SW - 52, 2.4, f"stat{i} label")
    s.append(txt(24, 116, value, "geist600", 44, p["ink"], -1.0, cls="r", delay=0.25))
    fit(value, "geist600", 44, SW - 48, -1.0, f"stat{i} value")
    if i == 3:
        s.append(star(24 + measure("geist600", 44, value, -1.0) + 22, 102, 15, p["accent"]))
    s.append(f'<line x1="26" y1="136" x2="{SW-26:.0f}" y2="136" stroke="{p["border"]}"/>')
    s.append(txt(26, 162, l1, "geist400", 13.5, p["ink"], cls="f", delay=0.35))
    fit(l1, "geist400", 13.5, SW - 52, 0, f"stat{i} l1")
    s.append(txt(26, 181, l2, "geist400", 12.5, p["muted"], cls="f", delay=0.42))
    fit(l2, "geist400", 12.5, SW - 52, 0, f"stat{i} l2")
    return "".join(s), SW, SH

# ================================================================ TITLE
def build_title(p):
    TW, TH = 880, 74
    s = [svg_open(TW, TH, ["geist600", "mono400"], "What I'm building")]
    s.append(txt(0, 44, "What I'm building", "geist600", 25, p["ink"], -0.4))
    tw = measure("geist600", 25, "What I'm building", -0.4)
    s.append(f'<line x1="{tw+18:.1f}" y1="36" x2="{TW}" y2="36" stroke="{p["border"]}"/>')
    s.append(txt(TW, 44, "03 PROJECTS", "mono400", 10.5, p["accent"], 2.4, anchor="end"))
    return "".join(s), TW, TH

# ================================================================ REPOS
def build_repo(p, idx, name, desc, foot, link):
    RW, RH = 293.333, 200
    s = [svg_open(RW, RH, ["geist600", "geist400", "mono400"],
                  f"{name}: {desc} {foot}")]
    s.append(card_bg(RW, RH, p, r=14, surface=True))
    s.append(txt(24, 40, idx, "mono400", 10.5, p["accent"], 2.0, cls="f", delay=0.1))
    s.append(txt(RW - 24, 40, "REPO", "mono400", 10.5, p["faint"], 2.0, anchor="end"))
    ns = 19 if measure("geist600", 19, name) <= RW - 48 else 16
    s.append(txt(24, 74, name, "geist600", ns, p["ink"], -0.3, cls="r", delay=0.2))
    fit(name, "geist600", ns, RW - 44, -0.3, f"repo {name} title")
    y = 100
    for ln in wrap(desc, "geist400", 13, RW - 48)[:3]:
        s.append(txt(24, y, ln, "geist400", 13, p["muted"], cls="f", delay=0.3))
        fit(ln, "geist400", 13, RW - 44, 0, f"repo {name} desc")
        y += 19
    s.append(f'<line x1="24" y1="{RH-40}" x2="{RW-24:.0f}" y2="{RH-40}" stroke="{p["border"]}"/>')
    s.append(txt(24, RH - 17, foot, "mono400", 10, p["accent"], 0.8))
    fit(foot, "mono400", 10, RW - 150, 0.8, f"repo {name} foot")
    s.append(txt(RW - 24, RH - 17, link, "mono400", 9.5, p["link"], 0.4, anchor="end"))
    fit(link, "mono400", 9.5, 140, 0.4, f"repo {name} link")
    return "".join(s), RW, RH

# ================================================================ STACK
def build_stack(p):
    KW, KH = 880, 214
    s = [svg_open(KW, KH, ["geist400", "mono400"],
                  "Stack. AI engineering: PyTorch, Transformers, LangChain, LlamaIndex, "
                  "ChromaDB, pgvector, FastAPI. AI security: OWASP LLM Top 10, Garak, "
                  "PyRIT, NeMo Guardrails, Semgrep, SARIF, Presidio. Platform: Python, "
                  "Docker, Cloudflare Workers, Redis, GitHub Actions, Vercel.")]
    s.append(card_bg(KW, KH, p, r=14, surface=True))
    s.append(txt(30, 40, "STACK", "mono400", 10.5, p["muted"], 2.4, cls="f", delay=0.05))
    rows_ = [("AI ENGINEERING",
              ["PyTorch", "Transformers", "LangChain", "LlamaIndex", "ChromaDB",
               "pgvector", "FastAPI"], 62),
             ("AI SECURITY",
              ["OWASP LLM Top 10", "Garak", "PyRIT", "NeMo Guardrails", "Semgrep",
               "SARIF", "Presidio"], 112),
             ("PLATFORM",
              ["Python", "Docker", "Cloudflare Workers", "Redis", "GitHub Actions",
               "Vercel"], 162)]
    for ri, (label, items, top) in enumerate(rows_):
        s.append(txt(30, top + 18, label, "mono400", 9.5, p["accent"], 1.6, cls="f",
                     delay=0.1 + ri*0.1))
        x = 150
        for ci, it in enumerate(items):
            tw = measure("mono400", 11, it, 0.6)
            w_ = tw + 26
            if x + w_ > KW - 30:
                ISSUES.append(f"stack row '{label}' overflow at '{it}' ({x+w_:.0f})")
            s.append(f'<g class="f" style="animation-delay:{0.16 + ri*0.1 + ci*0.03:.2f}s">')
            s.append(f'<rect x="{x:g}" y="{top:g}" width="{w_:g}" height="28" rx="6" '
                     f'fill="{p["chip"]}" stroke="{p["border"]}"/>')
            s.append(txt(x + 13, top + 18.5, it, "mono400", 11, p["ink"], 0.6))
            s.append("</g>")
            x += w_ + 8
    return "".join(s), KW, KH

# ================================================================ QUOTE
def build_quote(p):
    QW, QH = 880, 112
    s = [svg_open(QW, QH, ["serifit", "mono400"], "Engineer by choice.")]
    s.append(card_bg(QW, QH, p, r=14))
    s.append(txt(QW/2, 66, "Engineer by choice.", "serifit", 27, p["ink"], 0,
                 anchor="middle", cls="r", delay=0.1))
    s.append(txt(QW/2, 84, "OPEN TO SECURITY & AI ENGINEERING ROLES", "mono400", 10,
                 p["muted"], 2.6, anchor="middle", cls="f", delay=0.4))
    s.append(f'<rect x="{(QW-48)/2:.0f}" y="26" width="48" height="3" rx="1.5" '
             f'fill="{p["accent"]}" fill-opacity="0.9" class="f" '
             f'style="animation-delay:0.55s"/>')
    return "".join(s), QW, QH

# ================================================================ emit both themes
STATS = [(1, "DISCLOSED", "1", "CVE-2026-40316", "public vulnerability credit"),
         (2, "STANDARD", "LLM09", "OWASP Top 10 for LLMs", "co-lead, 2026 edition"),
         (3, "SHIPPED", "178", "FindMyGSoC", "stars, most-starred repo")]
REPOS = [("01", "FindMyGSoC",
          "Filter all 184 selected GSoC orgs by stack, language and domain. No install.",
          "HTML · 178 STARS", "findmygsoc.vercel.app"),
         ("02", "TENET-AI",
          "LLM firewall: blocks prompt injection, jailbreaks and data extraction under 10ms.",
          "Python · MIT", "tenet-aiorg.vercel.app"),
         ("03", "Claude-Skills-Security",
          "A production-grade security triage skill for AI agents.",
          "SKILL · 8 STARS", "github")]

for scheme, p in PAL.items():
    jobs = [("hero", lambda: build_hero(p))]
    if DATAJ:
        jobs.append(("contributions", lambda: build_contributions(p)))
    jobs += [(f"stat-{i}", (lambda i=i, l=l, v=v, a=a, b=b: build_stat(p, i, l, v, a, b)))
             for i, l, v, a, b in STATS]
    jobs.append(("title", lambda: build_title(p)))
    jobs += [(f"repo-{idx}", (lambda idx=idx, n=n, d=d, f=f, lk=lk: build_repo(p, idx, n, d, f, lk)))
             for idx, n, d, f, lk in REPOS]
    jobs.append(("stack", lambda: build_stack(p)))
    jobs.append(("quote", lambda: build_quote(p)))
    for name, fn in jobs:
        body, w_, h_ = fn()
        sizes[f"{name}-{scheme}.svg"] = write(f"{name}-{scheme}.svg", body, w_, h_)

# ---------------------------------------------------------------- report
print(json.dumps(sizes, indent=1))
print(f"\ntotal {sum(sizes.values())/1024:.0f} KB across {len(sizes)} cards")
for scheme, p in PAL.items():
    print(f"\ncontrast on {scheme} surface {p['surface']}")
    for nm, key, need in (("ink", "ink", 7.0), ("muted", "muted", 4.5),
                          ("accent", "accent", 4.5), ("accent_d", "accent_d", 3.0),
                          ("alt", "alt", 4.5), ("heat-4", None, 4.5), ("heat-3", None, 3.0)):
        col = p["heat"][4] if nm == "heat-4" else p["heat"][3] if nm == "heat-3" else p[key]
        r = contrast(col, p["surface"])
        ok = "ok" if r >= need else "LOW"
        print(f"  {nm:9s} {r:5.2f}:1  need {need}  {ok}")
        if r < need:
            ISSUES.append(f"{scheme} contrast {nm} {r:.2f} < {need}")
if ISSUES:
    print("\n!! ISSUES")
    for i in ISSUES: print("  ", i)
    sys.exit(1)
print("\nno overflow or contrast issues")
