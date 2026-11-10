#!/usr/bin/env python3
"""Render the S3DFX-CYBER profile cards as self-contained animated SVGs.

THEME ROTATION — two layers, one crossfade
Each card contains the whole design twice: a dark layer and a light layer,
stacked. Only their opacity animates, on a 60s loop — 24s dark, 6s crossfade,
24s light, 6s crossfade back.

Why layers instead of animating the palette per element: an element-by-element
colour animation can drift out of phase in a browser, and a card that is half
switched is unreadable (dark text on a dark surface). Two complete layers cannot
do that — any single frame is a blend of two readable cards. It also makes the
transition genuinely smooth rather than a 60ms cut.

Every element appears once per layer with identical geometry; only colour values
differ, which build_cards asserts before writing.

Motion (rise / fade / pop / spin / caret / breathe) is CSS keyframes, so it plays
on GitHub without JavaScript. Everything stops under prefers-reduced-motion, and
the static attributes are the dark layer, so a frozen card is still correct.

Run from the repo root:  pip install fonttools pillow  &&  python scripts/build_cards.py
Refresh the graph first with:  python scripts/fetch_contributions.py
"""
import base64, json, os, re, sys
from fontTools.ttLib import TTFont
from PIL import ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("CARDS_OUT") or os.path.join(BASE, "..", "cards")
FONT_DIR = os.environ.get("FONTS_DIR") or os.path.join(BASE, "..", "fonts")
ASSETS = os.environ.get("ASSETS_DIR") or os.path.join(BASE, "..", "assets")
DATA = os.environ.get("DATA_DIR") or os.path.join(BASE, "..", "data")
os.makedirs(OUT, exist_ok=True)

CYCLE = 60          # seconds for a full dark -> light -> dark rotation
HOLD = 40           # % the dark layer holds before it starts to fade
MID = 50            # % the light layer is fully in
BACK = 90           # % the light layer starts to fade back

# ---------------------------------------------------------------- palettes
PAL = {
    "dark": {
        "canvas": "#0B0910", "surface": "#120E17", "chip": "#171320",
        "border": "#251D30", "ink": "#F7F5F9", "muted": "#A79EB0",
        "accent": "#FF77B0", "alt": "#FFFFFF", "faint": "#3D3448",
        "link": "#7A6F86",
        "heat": ["#1A1420", "#4A1832", "#8E2055", "#C9327A", "#FF77B0"],
        "glow": "#FF77B0", "glow_op": 0.16, "glow_op2": 0.03,
    },
    "light": {
        "canvas": "#FBF8FB", "surface": "#FFFFFF", "chip": "#F6F1F5",
        "border": "#E7DFE8", "ink": "#1A1520", "muted": "#6E6478",
        "accent": "#C42B74", "alt": "#1A1520", "faint": "#C9BECE",
        "link": "#8A7F94",
        "heat": ["#F2EAEF", "#FBD6E5", "#F5A6C7", "#E1559A", "#C42B74"],
        "glow": "#C42B74", "glow_op": 0.10, "glow_op2": 0.02,
    },
}

def _lum(hexs):
    c = [int(hexs[i:i+2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

MOTION = f"""
@keyframes d-swap{{0%,{HOLD}%{{opacity:1}}{MID}%,{BACK}%{{opacity:0}}100%{{opacity:1}}}}
@keyframes l-swap{{0%,{HOLD}%{{opacity:0}}{MID}%,{BACK}%{{opacity:1}}100%{{opacity:0}}}}
.lay-d{{animation:d-swap {CYCLE}s linear infinite}}
.lay-l{{animation:l-swap {CYCLE}s linear infinite}}
@keyframes rise{{from{{opacity:0;transform:translateY(9px)}}to{{opacity:1;transform:translateY(0)}}}}
@keyframes fade{{from{{opacity:0}}to{{opacity:1}}}}
@keyframes pop{{0%{{opacity:0;transform:scale(.35)}}70%{{transform:scale(1.06)}}100%{{opacity:1;transform:scale(1)}}}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
@keyframes blink{{0%,45%{{opacity:1}}55%,100%{{opacity:0}}}}
@keyframes breathe{{0%,100%{{opacity:.45}}50%{{opacity:.95}}}}
.r{{animation:rise .75s cubic-bezier(.22,.7,.3,1) both}}
.f{{animation:fade .9s ease-out both}}
.p{{animation:pop .5s cubic-bezier(.22,.7,.3,1) both}}
.spin{{animation:spin 44s linear infinite;transform-origin:734px 132px}}
.caret{{animation:blink 1.15s steps(1,end) infinite}}
.breathe{{animation:breathe 5.5s ease-in-out infinite}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
"""

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

def svg_open(w, h, keys, title):
    faces = "".join(font_face(k) for k in dict.fromkeys(keys))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w:g}" height="{h:g}" viewBox="0 0 {w:g} {h:g}" '
            f'role="img" aria-label="{esc(title)}">'
            f"<title>{esc(title)}</title><style>{faces}{MOTION}</style>")

def wrap_motion(inner, motion=None, delay=None, extra=""):
    if not motion:
        return inner
    d = f"animation-delay:{delay}s;" if delay is not None else ""
    return f'<g class="{motion}" style="{d}{extra}">{inner}</g>'

def txt(x, y, s, key, size, fill, tracking=0.0, weight=None, anchor=None,
        motion=None, delay=None, opacity=None):
    _, fam, sub, _ = FONTS[key]
    w = weight or ("600" if "600" in sub else "400")
    st = "italic" if "italic" in sub.lower() else "normal"
    a = f' text-anchor="{anchor}"' if anchor else ""
    ls = f' letter-spacing="{tracking}"' if tracking else ""
    op = f' opacity="{opacity}"' if opacity is not None else ""
    el = (f'<text x="{x:g}" y="{y:g}" font-family="{fam}" font-size="{size:g}" '
          f'font-weight="{w}" font-style="{st}" fill="{fill}"{ls}{a}{op}>{esc(s)}</text>')
    return wrap_motion(el, motion, delay)

def rect(x, y, w, h, fill, rx=None, fill_opacity=None, stroke=None, stroke_width=None,
         motion=None, delay=None, extra_style=""):
    r = f' rx="{rx:g}"' if rx is not None else ""
    fo = f' fill-opacity="{fill_opacity}"' if fill_opacity is not None else ""
    st = f' stroke="{stroke}" stroke-width="{stroke_width:g}"' if stroke else ""
    el = (f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}"{r} '
          f'fill="{fill}"{fo}{st}/>')
    return wrap_motion(el, motion, delay, extra_style)

def dot(x, y, r, fill, opacity=None, motion=None, delay=None):
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return wrap_motion(f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="{fill}"{op}/>',
                       motion, delay)

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
            f'fill="none" stroke="{stroke}" stroke-width="{width:g}" '
            f'stroke-opacity="{op}" stroke-linecap="round"/>')

def card_bg(w, h, p, r=16, surface=False):
    return (f'<rect x="0.5" y="0.5" width="{w-1:g}" height="{h-1:g}" rx="{r}" '
            f'fill="{p["surface"] if surface else p["canvas"]}" '
            f'stroke="{p["border"]}" stroke-width="1"/>')

COLOUR_ATTRS = re.compile(r'(?:fill|stroke|stop-color|stop-opacity|fill-opacity)="[^"]*"')
def strip_colour(s):
    s = COLOUR_ATTRS.sub("", s)
    s = re.sub(r'url\(#[^)]*\)', "url()", s)
    return s

def write(name, dark_body, light_body, w, h, body):
    """The two layers must differ in colour only — anything else is a bug."""
    if strip_colour(dark_body) != strip_colour(light_body):
        ISSUES.append(f"{name}: dark and light layers differ by more than colour")
    if 'fill="none"' in dark_body and "stroke=" not in dark_body:
        ISSUES.append(f"{name}: unfilled element with no stroke")
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
HERO_W, HERO_H = 880, 264
def hero_content(p):
    W, H, P = HERO_W, HERO_H, 46
    s = [f'<defs><radialGradient id="glow" cx="0.12" cy="0.02" r="0.9">'
         f'<stop offset="0" stop-color="{p["glow"]}" stop-opacity="{p["glow_op"]}"/>'
         f'<stop offset="0.5" stop-color="{p["glow"]}" stop-opacity="{p["glow_op2"]}"/>'
         f'<stop offset="1" stop-color="{p["glow"]}" stop-opacity="0"/>'
         f'</radialGradient></defs>']
    s.append(card_bg(W, H, p))
    s.append(wrap_motion(
        f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="16" fill="url(#glow)"/>',
        "breathe"))

    kick = "SECURITY ENGINEERING / AI SAFETY"
    s.append(txt(P, 60, kick, "mono400", 11.5, p["accent"], 2.4, motion="r", delay=0.05))
    fit(kick, "mono400", 11.5, 380, 2.4, "hero kicker")
    s.append(rect(P + measure("mono400", 11.5, kick, 2.4) + 9, 49, 7, 13, p["accent"],
                  rx=1, motion="caret"))
    s.append(txt(610, 60, "MUMBAI, IN", "mono400", 11.5, p["muted"], 2.4, anchor="end",
                 motion="f", delay=0.5))

    s.append(txt(P - 2, 132, "Savio Dsouza", "geist600", 60, p["ink"], -1.2,
                 motion="r", delay=0.15))
    fit("Savio Dsouza", "geist600", 60, 470, -1.2, "hero name")
    sub = "AppSec engineer and AI security researcher."
    s.append(txt(P, 168, sub, "geist400", 19, p["muted"], motion="r", delay=0.3))
    fit(sub, "geist400", 19, 470, 0, "hero sub")

    s.append(wrap_motion(
        rect(P, 190, 120, 3, p["accent"], rx=1.5, fill_opacity=0.9) +
        rect(P + 74, 190, 46, 3, p["alt"], rx=1.5, fill_opacity=0.85), "r", 0.42))

    chips = [("CVE-2026-40316", p["accent"]), ("OWASP LLM09 CO-LEAD", p["alt"]),
             ("OWASP BLT", p["accent"])]
    cx = P
    for i, (label, col) in enumerate(chips):
        tw = fit(label, "mono400", 11, 260, 1.0, "hero chip")
        cw = tw + 34
        inner = (rect(cx, 214, cw, 30, p["chip"], rx=6, stroke=p["border"], stroke_width=1) +
                 dot(cx + 13, 229, 3, col) +
                 txt(cx + 22, 233.5, label, "mono400", 11, p["ink"], 1.0))
        s.append(wrap_motion(inner, "r", round(0.54 + i*0.08, 2)))
        cx += cw + 10
    if cx > 600:
        ISSUES.append(f"hero chips overflow: {cx:.0f} > 600")

    PCX, PCY, PR = 734, 132, 100
    s.append(f'<circle cx="{PCX}" cy="{PCY}" r="{PR+9}" fill="none" '
             f'stroke="{p["border"]}"/>')
    s.append(wrap_motion('<use xlink:href="#pic" href="#pic"/>', "f", 0.2))
    s.append(wrap_motion(
        f'<path d="M {PCX} {PCY-PR-9} A {PR+9} {PR+9} 0 0 1 {PCX+PR+9} {PCY}" '
        f'fill="none" stroke="{p["accent"]}" stroke-width="2.5" '
        f'stroke-linecap="round"/>', "spin"))
    s.append(arc(PCX, PCY, PR + 9, 90, 270, p["alt"], 2.5, 0.55))
    return "".join(s)

HERO_SHARED = (f'<defs><clipPath id="pf"><circle cx="734" cy="132" r="100"/></clipPath>'
               f'<image id="pic" x="634" y="32" width="200" height="200" clip-path="url(#pf)" '
               f'preserveAspectRatio="xMidYMid slice" '
               f'xlink:href="data:image/jpeg;base64,{P64}" '
               f'href="data:image/jpeg;base64,{P64}"/></defs>') if P64 else ""

# ================================================================ CONTRIBUTIONS
CON_W, CON_H = 880, 236
def contributions_content(p):
    d = DATAJ
    KW, KH = CON_W, CON_H
    s = [card_bg(KW, KH, p, r=14, surface=True)]
    s.append(txt(30, 42, "CONTRIBUTIONS", "mono400", 10.5, p["accent"], 2.4,
                 motion="f", delay=0.05))
    s.append(txt(KW - 30, 42, f"{d['total']:,} IN THE LAST 12 MONTHS", "mono400", 10.5,
                 p["muted"], 1.8, anchor="end", motion="f", delay=0.2))

    CELL, GAP = 11.0, 3.0
    gx = (KW - (d["cols"] * (CELL + GAP) - GAP)) / 2
    gy = 62.0
    order = {}
    for i, day in enumerate(d["days"]):
        r_, c_ = divmod(i, d["cols"])
        order[(r_, c_)] = day
    for c_ in range(d["cols"]):
        delay = round(0.25 + c_ * 0.012, 3)
        for r_ in range(d["rows"]):
            day = order.get((r_, c_))
            if not day:
                continue
            x = gx + c_ * (CELL + GAP)
            y = gy + r_ * (CELL + GAP)
            s.append(rect(x, y, CELL, CELL, p["heat"][min(day["l"], 4)], rx=2.5,
                          motion="p", delay=delay,
                          extra_style=f"transform-origin:{x+CELL/2:.1f}px {y+CELL/2:.1f}px;"))

    lx = KW - 30 - (5 * (CELL + GAP) - GAP) - 46
    ly = gy + d["rows"] * (CELL + GAP) + 12
    s.append(txt(lx - 8, ly + 9, "LESS", "mono400", 9, p["muted"], 1.2, anchor="end"))
    for i in range(5):
        s.append(rect(lx + i*(CELL+GAP), ly, CELL, CELL, p["heat"][i], rx=2.5,
                      stroke=p["border"], stroke_width=0.5))
    s.append(txt(lx + 5 * (CELL + GAP) + 4, ly + 9, "MORE", "mono400", 9, p["muted"], 1.2))

    row = [("CURRENT STREAK", f"{d['current_streak']} DAYS"),
           ("LONGEST STREAK", f"{d['longest_streak']} DAYS"),
           ("BUSIEST DAY", f"{d['busiest']['count']} ON {d['busiest']['date']}")]
    bx = 30
    for i, (lab, val) in enumerate(row):
        s.append(txt(bx, KH - 30, lab, "mono400", 9, p["muted"], 1.6, motion="f",
                     delay=round(0.5 + i*0.1, 2)))
        s.append(txt(bx, KH - 12, val, "geist600", 14, p["ink"], -0.1, motion="f",
                     delay=round(0.55 + i*0.1, 2)))
        fit(val, "geist600", 14, 240, -0.1, f"contrib stat {lab}")
        bx += 250
    return "".join(s)

# ================================================================ STATS
STAT_W, STAT_H = 293.333, 214
def stat_content(p, i, label, value, l1, l2):
    SW, SH = STAT_W, STAT_H
    s = [card_bg(SW, SH, p, r=14, surface=True)]
    s.append(rect(26, 24, 46, 3, p["accent"], rx=1.5, fill_opacity=0.9, motion="f", delay=0.1))
    s.append(txt(26, 56, label, "mono400", 10.5, p["muted"], 2.4, motion="f", delay=0.15))
    fit(label, "mono400", 10.5, SW - 52, 2.4, f"stat{i} label")
    s.append(txt(24, 116, value, "geist600", 44, p["ink"], -1.0, motion="r", delay=0.25))
    fit(value, "geist600", 44, SW - 48, -1.0, f"stat{i} value")
    if i == 3:
        s.append(star(24 + measure("geist600", 44, value, -1.0) + 22, 102, 15, p["accent"]))
    s.append(f'<line x1="26" y1="136" x2="{SW-26:.0f}" y2="136" stroke="{p["border"]}"/>')
    s.append(txt(26, 162, l1, "geist400", 13.5, p["ink"], motion="f", delay=0.35))
    fit(l1, "geist400", 13.5, SW - 52, 0, f"stat{i} l1")
    s.append(txt(26, 181, l2, "geist400", 12.5, p["muted"], motion="f", delay=0.42))
    fit(l2, "geist400", 12.5, SW - 52, 0, f"stat{i} l2")
    return "".join(s)

# ================================================================ TITLE
TIT_W, TIT_H = 880, 74
def title_content(p):
    TW, TH = TIT_W, TIT_H
    s = [txt(0, 44, "What I'm building", "geist600", 25, p["ink"], -0.4,
             motion="r", delay=0.05)]
    tw = measure("geist600", 25, "What I'm building", -0.4)
    s.append(wrap_motion(
        f'<line x1="{tw+18:.1f}" y1="36" x2="{TW}" y2="36" stroke="{p["border"]}"/>', "f", 0.3))
    s.append(txt(TW, 44, "03 PROJECTS", "mono400", 10.5, p["accent"], 2.4, anchor="end",
                 motion="f", delay=0.45))
    return "".join(s)

# ================================================================ REPOS
REPO_W, REPO_H = 293.333, 200
def repo_content(p, idx, name, desc, foot, link):
    RW, RH = REPO_W, REPO_H
    s = [card_bg(RW, RH, p, r=14, surface=True)]
    s.append(txt(24, 40, idx, "mono400", 10.5, p["accent"], 2.0, motion="f", delay=0.1))
    s.append(txt(RW - 24, 40, "REPO", "mono400", 10.5, p["faint"], 2.0, anchor="end"))
    ns = 19 if measure("geist600", 19, name) <= RW - 48 else 16
    s.append(txt(24, 74, name, "geist600", ns, p["ink"], -0.3, motion="r", delay=0.2))
    fit(name, "geist600", ns, RW - 44, -0.3, f"repo {name} title")
    y = 100
    for ln in wrap(desc, "geist400", 13, RW - 48)[:3]:
        s.append(txt(24, y, ln, "geist400", 13, p["muted"], motion="f", delay=0.3))
        fit(ln, "geist400", 13, RW - 44, 0, f"repo {name} desc")
        y += 19
    s.append(f'<line x1="24" y1="{RH-40}" x2="{RW-24:.0f}" y2="{RH-40}" stroke="{p["border"]}"/>')
    s.append(txt(24, RH - 17, foot, "mono400", 10, p["accent"], 0.8))
    fit(foot, "mono400", 10, RW - 150, 0.8, f"repo {name} foot")
    s.append(txt(RW - 24, RH - 17, link, "mono400", 9.5, p["link"], 0.4, anchor="end"))
    fit(link, "mono400", 9.5, 140, 0.4, f"repo {name} link")
    return "".join(s)

# ================================================================ STACK
STK_W, STK_H = 880, 214
def stack_content(p):
    KW, KH = STK_W, STK_H
    s = [card_bg(KW, KH, p, r=14, surface=True)]
    s.append(txt(30, 40, "STACK", "mono400", 10.5, p["muted"], 2.4, motion="f", delay=0.05))
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
        s.append(txt(30, top + 18, label, "mono400", 9.5, p["accent"], 1.6, motion="f",
                     delay=round(0.1 + ri*0.1, 2)))
        x = 150
        for ci, it in enumerate(items):
            tw = measure("mono400", 11, it, 0.6)
            w_ = tw + 26
            if x + w_ > KW - 30:
                ISSUES.append(f"stack row '{label}' overflow at '{it}' ({x+w_:.0f})")
            inner = (rect(x, top, w_, 28, p["chip"], rx=6, stroke=p["border"], stroke_width=1) +
                     txt(x + 13, top + 18.5, it, "mono400", 11, p["ink"], 0.6))
            s.append(wrap_motion(inner, "f", round(0.16 + ri*0.1 + ci*0.03, 2)))
            x += w_ + 8
    return "".join(s)

# ================================================================ QUOTE
QUO_W, QUO_H = 880, 112
def quote_content(p):
    QW, QH = QUO_W, QUO_H
    s = [card_bg(QW, QH, p, r=14)]
    s.append(txt(QW/2, 66, "Engineer by choice.", "serifit", 27, p["ink"], 0,
                 anchor="middle", motion="r", delay=0.1))
    s.append(txt(QW/2, 84, "OPEN TO SECURITY & AI ENGINEERING ROLES", "mono400", 10,
                 p["muted"], 2.6, anchor="middle", motion="f", delay=0.4))
    s.append(rect((QW-48)/2, 26, 48, 3, p["accent"], rx=1.5, fill_opacity=0.9,
                  motion="f", delay=0.55))
    return "".join(s)

# ================================================================ emit
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

def build(name, keys, title, fn, w, h, shared=""):
    d, l = fn(PAL["dark"]), fn(PAL["light"])
    body = (svg_open(w, h, keys, title) + shared +
            f'<g class="lay-d">{d}</g><g class="lay-l">{l}</g>')
    sizes[name] = write(name, d, l, w, h, body)

build("hero.svg", ["geist600", "geist400", "mono400"],
      "Savio Dsouza — AppSec engineer and AI security researcher in Mumbai. "
      "CVE-2026-40316. Co-lead of OWASP Top 10 for LLM Applications, LLM09:2026.",
      hero_content, HERO_W, HERO_H, HERO_SHARED)

if DATAJ:
    build("contributions.svg", ["geist600", "geist400", "mono400"],
          f"Contribution graph: {DATAJ['total']} contributions in the last 12 months, "
          f"current streak {DATAJ['current_streak']} days, longest streak "
          f"{DATAJ['longest_streak']} days.",
          contributions_content, CON_W, CON_H)

for i, l, v, a, b in STATS:
    build(f"stat-{i}.svg", ["geist600", "geist400", "mono400"],
          f"{l}: {v}. {a}, {b}.",
          (lambda i=i, l=l, v=v, a=a, b=b: lambda p: stat_content(p, i, l, v, a, b))(),
          STAT_W, STAT_H)

build("title.svg", ["geist600", "mono400"], "What I'm building",
      title_content, TIT_W, TIT_H)

for idx, n, d_, f_, lk in REPOS:
    build(f"repo-{idx}.svg", ["geist600", "geist400", "mono400"], f"{n}: {d_} {f_}",
          (lambda idx=idx, n=n, d_=d_, f_=f_, lk=lk: lambda p: repo_content(p, idx, n, d_, f_, lk))(),
          REPO_W, REPO_H)

build("stack.svg", ["geist400", "mono400"],
      "Stack. AI engineering: PyTorch, Transformers, LangChain, LlamaIndex, ChromaDB, "
      "pgvector, FastAPI. AI security: OWASP LLM Top 10, Garak, PyRIT, NeMo Guardrails, "
      "Semgrep, SARIF, Presidio. Platform: Python, Docker, Cloudflare Workers, Redis, "
      "GitHub Actions, Vercel.", stack_content, STK_W, STK_H)

build("quote.svg", ["serifit", "mono400"], "Engineer by choice.",
      quote_content, QUO_W, QUO_H)

# ---------------------------------------------------------------- report
print(json.dumps(sizes, indent=1))
print(f"\ntotal {sum(sizes.values())/1024:.0f} KB across {len(sizes)} cards, "
      f"{CYCLE}s loop: {HOLD}% dark, {MID-HOLD}% fade, {BACK-MID}% light, {100-BACK}% fade")
for theme, p in PAL.items():
    print(f"\ncontrast on {theme} surface")
    for nm, key, need in (("ink", "ink", 7.0), ("muted", "muted", 4.5),
                          ("accent", "accent", 4.5), ("alt", "alt", 4.5)):
        r = contrast(p[key], p["surface"])
        ok = "ok" if r >= need else "LOW"
        print(f"  {nm:7s} {r:5.2f}:1  need {need}  {ok}")
        if r < need:
            ISSUES.append(f"{theme} contrast {nm} {r:.2f} < {need}")
    for i, need in ((4, 4.5), (3, 3.0)):
        r = contrast(p["heat"][i], p["surface"])
        ok = "ok" if r >= need else "LOW"
        print(f"  heat-{i}  {r:5.2f}:1  need {need}  {ok}")
        if r < need:
            ISSUES.append(f"{theme} contrast heat-{i} {r:.2f} < {need}")
if ISSUES:
    print("\n!! ISSUES")
    for i in ISSUES: print("  ", i)
    sys.exit(1)
print("\nno overflow, contrast or layer-parity issues")
