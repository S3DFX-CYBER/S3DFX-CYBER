#!/usr/bin/env python3
"""Render the S3DFX-CYBER profile cards as self-contained animated SVGs.

THEME ROTATION
Each card carries both palettes and flips between them on a 60s loop — 30s dark,
30s light — driven by CSS keyframes on colour roles. One file per card, no
JavaScript, and it works on GitHub because the file is served as an image.

How the two animations coexist: colour lives on a leaf element (a role class),
motion lives on a <g> wrapping it. An element can only have one `animation`
shorthand, so a leaf never carries both — that is why the emitters below wrap.

Colour system: a duotone, pink and white, in both themes.
  · canvas + surface are the 60%; body copy and every number are the 30% ink
  · pink is the 10% — identity and state only, never used as fill
  · the heatmap is the one place a tint ramp is allowed, because there the
    colour *is* the data
Hierarchy comes from weight and space, not from extra hues.

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

CYCLE = 60          # seconds for a full dark -> light -> dark rotation
SWITCH = 49.9       # % into the cycle where it flips; 49.9 gives a 60ms dissolve

# role -> (dark value, light value, css property)
ROLES = {
    "canvas":  ("#0B0910", "#FBF8FB", "fill"),
    "surface": ("#120E17", "#FFFFFF", "fill"),
    "chip":    ("#171320", "#F6F1F5", "fill"),
    "border":  ("#251D30", "#E7DFE8", "stroke"),
    "ink":     ("#F7F5F9", "#1A1520", "fill"),
    "muted":   ("#A79EB0", "#6E6478", "fill"),
    "accent":  ("#FF77B0", "#C42B74", "fill"),
    "alt":     ("#FFFFFF", "#1A1520", "fill"),
    "faint":   ("#3D3448", "#C9BECE", "fill"),
    "link":    ("#7A6F86", "#8A7F94", "fill"),
    "h0":      ("#1A1420", "#F2EAEF", "fill"),
    "h1":      ("#4A1832", "#FBD6E5", "fill"),
    "h2":      ("#8E2055", "#F5A6C7", "fill"),
    "h3":      ("#C9327A", "#E1559A", "fill"),
    "h4":      ("#FF77B0", "#C42B74", "fill"),
    "glow":    ("#FF77B0", "#C42B74", "stop-color"),
    "glow2":   ("#FF77B0", "#C42B74", "stop-color"),
}
GLOW_OP = {"glow": (0.16, 0.10), "glow2": (0.03, 0.02)}

def _lum(hexs):
    c = [int(hexs[i:i+2], 16) / 255 for i in (1, 3, 5)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

def contrast(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)

def dark(role):
    return ROLES[role][0]

def role_css():
    """One keyframe pair per role; both palettes live in every card."""
    out = []
    for role, (d, l, prop) in ROLES.items():
        frames = f"0%,{SWITCH}%{{{prop}:{d}}}50%,100%{{{prop}:{l}}}"
        if role in GLOW_OP:
            o0, o1 = GLOW_OP[role]
            frames = (f"0%,{SWITCH}%{{{prop}:{d};stop-opacity:{o0}}}"
                      f"50%,100%{{{prop}:{l};stop-opacity:{o1}}}")
        out.append(f"@keyframes k-{role}{{{frames}}}"
                   f".c-{role}{{animation:k-{role} {CYCLE}s linear infinite}}")
    return "".join(out)

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
            f"<title>{esc(title)}</title><style>{faces}{role_css()}{MOTION}</style>")

def wrap_motion(inner, motion=None, delay=None, extra=""):
    if not motion:
        return inner
    d = f"animation-delay:{delay}s;" if delay is not None else ""
    return f'<g class="{motion}" style="{d}{extra}">{inner}</g>'

def txt(x, y, s, key, size, role, tracking=0.0, weight=None, anchor=None,
        motion=None, delay=None, opacity=None):
    _, fam, sub, _ = FONTS[key]
    w = weight or ("600" if "600" in sub else "400")
    st = "italic" if "italic" in sub.lower() else "normal"
    a = f' text-anchor="{anchor}"' if anchor else ""
    ls = f' letter-spacing="{tracking}"' if tracking else ""
    op = f' opacity="{opacity}"' if opacity is not None else ""
    el = (f'<text x="{x:g}" y="{y:g}" font-family="{fam}" font-size="{size:g}" '
          f'font-weight="{w}" font-style="{st}" fill="{dark(role)}"{ls}{a}{op} '
          f'class="c-{role}">{esc(s)}</text>')
    return wrap_motion(el, motion, delay)

def rect(x, y, w, h, role, rx=None, fill_opacity=None, stroke=None, stroke_width=None,
         motion=None, delay=None, extra_style=""):
    r = f' rx="{rx:g}"' if rx is not None else ""
    fo = f' fill-opacity="{fill_opacity}"' if fill_opacity is not None else ""
    st = f' stroke="{dark(stroke)}" stroke-width="{stroke_width:g}"' if stroke else ""
    cls = f"c-{role}" + (f" c-{stroke}" if stroke else "")
    el = (f'<rect x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}"{r} '
          f'fill="{dark(role)}"{fo}{st} class="{cls}"/>')
    return wrap_motion(el, motion, delay, extra_style)

def dot(x, y, r, role, opacity=None, motion=None, delay=None):
    op = f' opacity="{opacity}"' if opacity is not None else ""
    el = (f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="{dark(role)}"{op} '
          f'class="c-{role}"/>')
    return wrap_motion(el, motion, delay)

def star(cx, cy, r, role):
    import math
    pts = []
    for i in range(10):
        ang = math.radians(-90 + i * 36)
        rad = r if i % 2 == 0 else r * 0.42
        pts.append(f"{cx + rad*math.cos(ang):.1f},{cy + rad*math.sin(ang):.1f}")
    return f'<polygon points="{" ".join(pts)}" fill="{dark(role)}" class="c-{role}"/>'

def arc(cx, cy, r, a1, a2, role, width, op=1.0):
    import math
    x1, y1 = cx + r*math.cos(math.radians(a1)), cy + r*math.sin(math.radians(a1))
    x2, y2 = cx + r*math.cos(math.radians(a2)), cy + r*math.sin(math.radians(a2))
    return (f'<path d="M {x1:.2f} {y1:.2f} A {r:g} {r:g} 0 0 1 {x2:.2f} {y2:.2f}" '
            f'fill="none" stroke="{dark(role)}" stroke-width="{width:g}" '
            f'stroke-opacity="{op}" stroke-linecap="round" class="c-{role}"/>')

def card_bg(w, h, r=16, surface=False):
    role = "surface" if surface else "canvas"
    return (f'<rect x="0.5" y="0.5" width="{w-1:g}" height="{h-1:g}" rx="{r}" '
            f'fill="{dark(role)}" stroke="{dark("border")}" stroke-width="1" '
            f'class="c-{role} c-border"/>')

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
def build_hero():
    W, H, P = 880, 264, 46
    s = [svg_open(W, H, ["geist600", "geist400", "mono400"],
         "Savio Dsouza — AppSec engineer and AI security researcher in Mumbai. "
         "CVE-2026-40316. Co-lead of OWASP Top 10 for LLM Applications, LLM09:2026.")]
    s.append("<defs>"
             '<radialGradient id="glow" cx="0.12" cy="0.02" r="0.9">'
             f'<stop offset="0" stop-color="{dark("glow")}" stop-opacity="0.16" class="c-glow"/>'
             f'<stop offset="0.5" stop-color="{dark("glow2")}" stop-opacity="0.03" class="c-glow2"/>'
             f'<stop offset="1" stop-color="{dark("glow2")}" stop-opacity="0"/>'
             "</radialGradient>"
             '<clipPath id="pf"><circle cx="734" cy="132" r="100"/></clipPath></defs>')
    s.append(card_bg(W, H))
    s.append(wrap_motion(
        f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="16" fill="url(#glow)"/>',
        "breathe"))

    kick = "SECURITY ENGINEERING / AI SAFETY"
    s.append(txt(P, 60, kick, "mono400", 11.5, "accent", 2.4, motion="r", delay=0.05))
    fit(kick, "mono400", 11.5, 380, 2.4, "hero kicker")
    s.append(rect(P + measure("mono400", 11.5, kick, 2.4) + 9, 49, 7, 13, "accent",
                  rx=1, motion="caret"))
    s.append(txt(610, 60, "MUMBAI, IN", "mono400", 11.5, "muted", 2.4, anchor="end",
                 motion="f", delay=0.5))

    s.append(txt(P - 2, 132, "Savio Dsouza", "geist600", 60, "ink", -1.2,
                 motion="r", delay=0.15))
    fit("Savio Dsouza", "geist600", 60, 470, -1.2, "hero name")

    sub = "AppSec engineer and AI security researcher."
    s.append(txt(P, 168, sub, "geist400", 19, "muted", motion="r", delay=0.3))
    fit(sub, "geist400", 19, 470, 0, "hero sub")

    s.append(wrap_motion(
        rect(P, 190, 120, 3, "accent", rx=1.5, fill_opacity=0.9) +
        rect(P + 74, 190, 46, 3, "alt", rx=1.5, fill_opacity=0.85),
        "r", 0.42))

    chips = [("CVE-2026-40316", "accent"), ("OWASP LLM09 CO-LEAD", "alt"),
             ("OWASP BLT", "accent")]
    cx = P
    for i, (label, col) in enumerate(chips):
        tw = fit(label, "mono400", 11, 260, 1.0, "hero chip")
        cw = tw + 34
        inner = (rect(cx, 214, cw, 30, "chip", rx=6, stroke="border", stroke_width=1) +
                 dot(cx + 13, 229, 3, col) +
                 txt(cx + 22, 233.5, label, "mono400", 11, "ink", 1.0))
        s.append(wrap_motion(inner, "r", round(0.54 + i*0.08, 2)))
        cx += cw + 10
    if cx > 600:
        ISSUES.append(f"hero chips overflow: {cx:.0f} > 600")

    PCX, PCY, PR = 734, 132, 100
    s.append(f'<circle cx="{PCX}" cy="{PCY}" r="{PR+9}" fill="none" '
             f'stroke="{dark("border")}" class="c-border"/>')
    if P64:
        s.append(wrap_motion(
            f'<image x="{PCX-PR}" y="{PCY-PR}" width="{2*PR}" height="{2*PR}" '
            f'clip-path="url(#pf)" preserveAspectRatio="xMidYMid slice" '
            f'xlink:href="data:image/jpeg;base64,{P64}" '
            f'href="data:image/jpeg;base64,{P64}"/>', "f", 0.2))
    s.append(wrap_motion(
        f'<path d="M {PCX} {PCY-PR-9} A {PR+9} {PR+9} 0 0 1 {PCX+PR+9} {PCY}" '
        f'fill="none" stroke="{dark("accent")}" stroke-width="2.5" '
        f'stroke-linecap="round" class="c-accent"/>', "spin"))
    s.append(arc(PCX, PCY, PR + 9, 90, 270, "alt", 2.5, 0.55))
    return "".join(s), W, H

# ================================================================ CONTRIBUTIONS
def build_contributions():
    d = DATAJ
    KW, KH = 880, 236
    s = [svg_open(KW, KH, ["geist600", "geist400", "mono400"],
         f"Contribution graph: {d['total']} contributions in the last 12 months, "
         f"current streak {d['current_streak']} days, longest streak "
         f"{d['longest_streak']} days.")]
    s.append(card_bg(KW, KH, r=14, surface=True))
    s.append(txt(30, 42, "CONTRIBUTIONS", "mono400", 10.5, "accent", 2.4,
                 motion="f", delay=0.05))
    s.append(txt(KW - 30, 42, f"{d['total']:,} IN THE LAST 12 MONTHS", "mono400", 10.5,
                 "muted", 1.8, anchor="end", motion="f", delay=0.2))

    CELL, GAP = 11.0, 3.0
    grid_w = d["cols"] * (CELL + GAP) - GAP
    gx = (KW - grid_w) / 2
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
            s.append(rect(x, y, CELL, CELL, f"h{min(day['l'], 4)}", rx=2.5,
                          motion="p", delay=delay,
                          extra_style=f"transform-origin:{x+CELL/2:.1f}px {y+CELL/2:.1f}px;"))

    lx = KW - 30 - (5 * (CELL + GAP) - GAP) - 46
    ly = gy + d["rows"] * (CELL + GAP) + 12
    s.append(txt(lx - 8, ly + 9, "LESS", "mono400", 9, "muted", 1.2, anchor="end"))
    for i in range(5):
        s.append(rect(lx + i*(CELL+GAP), ly, CELL, CELL, f"h{i}", rx=2.5,
                      stroke="border", stroke_width=0.5))
    s.append(txt(lx + 5 * (CELL + GAP) + 4, ly + 9, "MORE", "mono400", 9, "muted", 1.2))

    stats_row = [("CURRENT STREAK", f"{d['current_streak']} DAYS"),
                 ("LONGEST STREAK", f"{d['longest_streak']} DAYS"),
                 ("BUSIEST DAY", f"{d['busiest']['count']} ON {d['busiest']['date']}")]
    bx = 30
    for i, (lab, val) in enumerate(stats_row):
        s.append(txt(bx, KH - 30, lab, "mono400", 9, "muted", 1.6, motion="f",
                     delay=round(0.5 + i*0.1, 2)))
        s.append(txt(bx, KH - 12, val, "geist600", 14, "ink", -0.1, motion="f",
                     delay=round(0.55 + i*0.1, 2)))
        fit(val, "geist600", 14, 240, -0.1, f"contrib stat {lab}")
        bx += 250
    return "".join(s), KW, KH

# ================================================================ STATS
def build_stat(i, label, value, l1, l2):
    SW, SH = 293.333, 214
    s = [svg_open(SW, SH, ["geist600", "geist400", "mono400"],
                  f"{label}: {value}. {l1}, {l2}.")]
    s.append(card_bg(SW, SH, r=14, surface=True))
    s.append(rect(26, 24, 46, 3, "accent", rx=1.5, fill_opacity=0.9, motion="f", delay=0.1))
    s.append(txt(26, 56, label, "mono400", 10.5, "muted", 2.4, motion="f", delay=0.15))
    fit(label, "mono400", 10.5, SW - 52, 2.4, f"stat{i} label")
    s.append(txt(24, 116, value, "geist600", 44, "ink", -1.0, motion="r", delay=0.25))
    fit(value, "geist600", 44, SW - 48, -1.0, f"stat{i} value")
    if i == 3:
        s.append(star(24 + measure("geist600", 44, value, -1.0) + 22, 102, 15, "accent"))
    s.append(f'<line x1="26" y1="136" x2="{SW-26:.0f}" y2="136" '
             f'stroke="{dark("border")}" class="c-border"/>')
    s.append(txt(26, 162, l1, "geist400", 13.5, "ink", motion="f", delay=0.35))
    fit(l1, "geist400", 13.5, SW - 52, 0, f"stat{i} l1")
    s.append(txt(26, 181, l2, "geist400", 12.5, "muted", motion="f", delay=0.42))
    fit(l2, "geist400", 12.5, SW - 52, 0, f"stat{i} l2")
    return "".join(s), SW, SH

# ================================================================ TITLE
def build_title():
    TW, TH = 880, 74
    s = [svg_open(TW, TH, ["geist600", "mono400"], "What I'm building")]
    s.append(txt(0, 44, "What I'm building", "geist600", 25, "ink", -0.4,
                 motion="r", delay=0.05))
    tw = measure("geist600", 25, "What I'm building", -0.4)
    s.append(wrap_motion(
        f'<line x1="{tw+18:.1f}" y1="36" x2="{TW}" y2="36" '
        f'stroke="{dark("border")}" class="c-border"/>', "f", 0.3))
    s.append(txt(TW, 44, "03 PROJECTS", "mono400", 10.5, "accent", 2.4, anchor="end",
                 motion="f", delay=0.45))
    return "".join(s), TW, TH

# ================================================================ REPOS
def build_repo(idx, name, desc, foot, link):
    RW, RH = 293.333, 200
    s = [svg_open(RW, RH, ["geist600", "geist400", "mono400"],
                  f"{name}: {desc} {foot}")]
    s.append(card_bg(RW, RH, r=14, surface=True))
    s.append(txt(24, 40, idx, "mono400", 10.5, "accent", 2.0, motion="f", delay=0.1))
    s.append(txt(RW - 24, 40, "REPO", "mono400", 10.5, "faint", 2.0, anchor="end"))
    ns = 19 if measure("geist600", 19, name) <= RW - 48 else 16
    s.append(txt(24, 74, name, "geist600", ns, "ink", -0.3, motion="r", delay=0.2))
    fit(name, "geist600", ns, RW - 44, -0.3, f"repo {name} title")
    y = 100
    for ln in wrap(desc, "geist400", 13, RW - 48)[:3]:
        s.append(txt(24, y, ln, "geist400", 13, "muted", motion="f", delay=0.3))
        fit(ln, "geist400", 13, RW - 44, 0, f"repo {name} desc")
        y += 19
    s.append(f'<line x1="24" y1="{RH-40}" x2="{RW-24:.0f}" y2="{RH-40}" '
             f'stroke="{dark("border")}" class="c-border"/>')
    s.append(txt(24, RH - 17, foot, "mono400", 10, "accent", 0.8))
    fit(foot, "mono400", 10, RW - 150, 0.8, f"repo {name} foot")
    s.append(txt(RW - 24, RH - 17, link, "mono400", 9.5, "link", 0.4, anchor="end"))
    fit(link, "mono400", 9.5, 140, 0.4, f"repo {name} link")
    return "".join(s), RW, RH

# ================================================================ STACK
def build_stack():
    KW, KH = 880, 214
    s = [svg_open(KW, KH, ["geist400", "mono400"],
                  "Stack. AI engineering: PyTorch, Transformers, LangChain, LlamaIndex, "
                  "ChromaDB, pgvector, FastAPI. AI security: OWASP LLM Top 10, Garak, "
                  "PyRIT, NeMo Guardrails, Semgrep, SARIF, Presidio. Platform: Python, "
                  "Docker, Cloudflare Workers, Redis, GitHub Actions, Vercel.")]
    s.append(card_bg(KW, KH, r=14, surface=True))
    s.append(txt(30, 40, "STACK", "mono400", 10.5, "muted", 2.4, motion="f", delay=0.05))
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
        s.append(txt(30, top + 18, label, "mono400", 9.5, "accent", 1.6, motion="f",
                     delay=round(0.1 + ri*0.1, 2)))
        x = 150
        for ci, it in enumerate(items):
            tw = measure("mono400", 11, it, 0.6)
            w_ = tw + 26
            if x + w_ > KW - 30:
                ISSUES.append(f"stack row '{label}' overflow at '{it}' ({x+w_:.0f})")
            inner = (rect(x, top, w_, 28, "chip", rx=6, stroke="border", stroke_width=1) +
                     txt(x + 13, top + 18.5, it, "mono400", 11, "ink", 0.6))
            s.append(wrap_motion(inner, "f", round(0.16 + ri*0.1 + ci*0.03, 2)))
            x += w_ + 8
    return "".join(s), KW, KH

# ================================================================ QUOTE
def build_quote():
    QW, QH = 880, 112
    s = [svg_open(QW, QH, ["serifit", "mono400"], "Engineer by choice.")]
    s.append(card_bg(QW, QH, r=14))
    s.append(txt(QW/2, 66, "Engineer by choice.", "serifit", 27, "ink", 0,
                 anchor="middle", motion="r", delay=0.1))
    s.append(txt(QW/2, 84, "OPEN TO SECURITY & AI ENGINEERING ROLES", "mono400", 10,
                 "muted", 2.6, anchor="middle", motion="f", delay=0.4))
    s.append(rect((QW-48)/2, 26, 48, 3, "accent", rx=1.5, fill_opacity=0.9,
                  motion="f", delay=0.55))
    return "".join(s), QW, QH

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

jobs = [("hero", build_hero)]
if DATAJ:
    jobs.append(("contributions", build_contributions))
jobs += [(f"stat-{i}", (lambda i=i, l=l, v=v, a=a, b=b: build_stat(i, l, v, a, b)))
         for i, l, v, a, b in STATS]
jobs.append(("title", build_title))
jobs += [(f"repo-{idx}", (lambda idx=idx, n=n, d=d, f=f, lk=lk: build_repo(idx, n, d, f, lk)))
         for idx, n, d, f, lk in REPOS]
jobs += [("stack", build_stack), ("quote", build_quote)]

for name, fn in jobs:
    body, w_, h_ = fn()
    sizes[f"{name}.svg"] = write(f"{name}.svg", body, w_, h_)

# ---------------------------------------------------------------- report
print(json.dumps(sizes, indent=1))
print(f"\ntotal {sum(sizes.values())/1024:.0f} KB across {len(sizes)} cards, "
      f"{CYCLE}s rotation")
for theme, idx in (("dark", 0), ("light", 1)):
    print(f"\ncontrast on {theme} surface")
    checks = [("ink", "ink", 7.0), ("muted", "muted", 4.5), ("accent", "accent", 4.5),
              ("alt", "alt", 4.5), ("h4", "h4", 4.5), ("h3", "h3", 3.0)]
    surf = ROLES["surface"][idx]
    for nm, role, need in checks:
        col = ROLES[role][idx]
        r = contrast(col, surf)
        ok = "ok" if r >= need else "LOW"
        print(f"  {nm:7s} {r:5.2f}:1  need {need}  {ok}")
        if r < need:
            ISSUES.append(f"{theme} contrast {nm} {r:.2f} < {need}")
if ISSUES:
    print("\n!! ISSUES")
    for i in ISSUES: print("  ", i)
    sys.exit(1)
print("\nno overflow or contrast issues")
