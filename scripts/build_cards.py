#!/usr/bin/env python3
"""Render the S3DFX-CYBER profile cards as self-contained animated SVGs.

Colour system: a tricolour, used semantically rather than decoratively.
  · canvas + surface are the 60% (near-black, tinted navy)
  · white/near-white is the 30% (all body text)
  · saffron and green are the 10% (identity + positive state only)
  · one accent per component, never two; navy only as surface tint
Each of the three stat cards owns one tricolour band, and a 3-segment strip
repeats as the signature device across the set.

Every card carries its own background and its own base64-embedded fonts, so it
looks identical on GitHub's light theme, dark theme, and in any mirror.

Run from the repo root:  pip install fonttools pillow  &&  python scripts/build_cards.py
Layout is measured with PIL against the real fonts, so the script fails loudly
rather than shipping a card with clipped or overflowing text.
"""
import base64, json, os, sys
from fontTools.ttLib import TTFont
from PIL import Image, ImageFilter
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("CARDS_OUT") or os.path.join(BASE, "..", "cards")
FONT_DIR = os.environ.get("FONTS_DIR") or os.path.join(BASE, "..", "fonts")
ASSETS = os.environ.get("ASSETS_DIR") or os.path.join(BASE, "..", "assets")
os.makedirs(OUT, exist_ok=True)

# ---------------------------------------------------------------- palette
CANVAS  = "#0A0D12"   # near-black, navy tint
SURFACE = "#0F151C"
CHIP    = "#141C24"
BORDER  = "#1D2733"
INK     = "#F5F8F9"   # white role — all primary text
MUTED   = "#93A1AD"   # cool grey — secondary text
SAFFRON = "#FF9933"   # identity / attention
GREEN   = "#3FAE58"   # flag green lifted for contrast on dark (see check below)
GREEN_D = "#138808"   # true flag green, graphic use only
WHITE_A = "#FFFFFF"   # the white band of the tricolour

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
        from PIL import ImageFont
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
            f'width="{w:g}" height="{h:g}" '
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

def card_bg(w, h, r=16, fill=CANVAS, stroke=BORDER):
    return (f'<rect x="0.5" y="0.5" width="{w-1:g}" height="{h-1:g}" rx="{r}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="1"/>')

def dot(x, y, r, fill, opacity=None):
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="{fill}"{op}/>'

def tricolour(x, y, w, h=3, gap=0, op=1.0):
    """The signature device: saffron / white / green, one band, three segments."""
    seg = (w - 2 * gap) / 3.0
    out = []
    for i, col in enumerate((SAFFRON, WHITE_A, GREEN)):
        out.append(f'<rect x="{x + i*(seg+gap):.1f}" y="{y:g}" width="{seg:.1f}" '
                   f'height="{h:g}" fill="{col}" fill-opacity="{op}"/>')
    return "".join(out)

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

# ---------------------------------------------------------------- ascii portrait
RAMP = " .:-=+*#%@"
ASCII_COLS = 100

def ascii_rows(zoom=0.58, yoff=-0.05, blur=5, gamma=1.2, clamp=0.05):
    src = Image.open(os.path.join(ASSETS, "portrait.png")).convert("RGB")
    W, H = src.size
    cx, cy, r = W / 2, H / 2, W / 2
    s = r * 2 * zoom
    cy += yoff * r
    c = src.crop((int(cx - s/2), int(cy - s/2), int(cx + s/2), int(cy + s/2)))
    c = c.filter(ImageFilter.GaussianBlur(blur))
    rows = int(round(ASCII_COLS * 8 / 9.6))
    g = c.convert("L").resize((ASCII_COLS, rows), Image.LANCZOS)
    v = 255.0 - np.asarray(g).astype(float)
    lo, hi = np.percentile(v, 2), np.percentile(v, 98)
    v = np.clip((v - lo) / (hi - lo + 1e-6), 0, 1) ** (1 / gamma)
    v[v < clamp] = 0.0
    idx = (v * (len(RAMP) - 1)).round().astype(int)
    return ["".join(RAMP[i] for i in row) for row in idx]

# ================================================================ 1. HERO
def arc(cx, cy, r, a1, a2, stroke, width, op=1.0):
    import math
    x1, y1 = cx + r*math.cos(math.radians(a1)), cy + r*math.sin(math.radians(a1))
    x2, y2 = cx + r*math.cos(math.radians(a2)), cy + r*math.sin(math.radians(a2))
    return (f'<path d="M {x1:.2f} {y1:.2f} A {r:g} {r:g} 0 0 1 {x2:.2f} {y2:.2f}" '
            f'fill="none" stroke="{stroke}" stroke-width="{width:g}" stroke-opacity="{op}"/>')

def hero_svg(mode):
    W, P = 880, 46
    H = 308 if mode == "ascii" else 264
    s = [svg_open(W, H, ["geist600", "geist400", "mono400"],
         "Savio Dsouza — AppSec engineer and AI security researcher in Mumbai. "
         "CVE-2026-40316. Co-lead of OWASP Top 10 for LLM Applications, LLM09:2026.")]
    s.append("<defs>"
             '<radialGradient id="glow" cx="0.1" cy="0.04" r="0.85">'
             f'<stop offset="0" stop-color="{SAFFRON}" stop-opacity="0.10"/>'
             f'<stop offset="0.55" stop-color="{SAFFRON}" stop-opacity="0.015"/>'
             f'<stop offset="1" stop-color="{SAFFRON}" stop-opacity="0"/>'
             "</radialGradient>"
             '<clipPath id="pf"><circle cx="734" cy="132" r="100"/></clipPath></defs>')
    s.append(card_bg(W, H))
    s.append(f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="16" fill="url(#glow)"/>')

    s.append(txt(P, 64, "SECURITY ENGINEERING / AI SAFETY", "mono400", 11.5, SAFFRON, 2.4))
    fit("SECURITY ENGINEERING / AI SAFETY", "mono400", 11.5, 380, 2.4, "hero kicker")
    s.append(txt(610, 64, "MUMBAI, IN", "mono400", 11.5, MUTED, 2.4, anchor="end"))

    name = "Savio Dsouza"
    s.append(txt(P - 2, 152 if mode == "ascii" else 132, name, "geist600", 60, INK, -1.2))
    fit(name, "geist600", 60, 470, -1.2, "hero name")

    sub = "AppSec engineer and AI security researcher."
    sy = 188 if mode == "ascii" else 168
    s.append(txt(P, sy, sub, "geist400", 19, MUTED))
    fit(sub, "geist400", 19, 470, 0, "hero sub")
    s.append(tricolour(P, sy + 18, 120, 3, 2, 0.9))

    chips = [("CVE-2026-40316", SAFFRON), ("OWASP LLM09 CO-LEAD", WHITE_A),
             ("OWASP BLT", GREEN)]
    cy0 = 230 if mode == "ascii" else 210
    cx = P
    for label, col in chips:
        tw = fit(label, "mono400", 11, 260, 1.0, "hero chip")
        cw = tw + 34
        s.append(f'<rect x="{cx:g}" y="{cy0:g}" width="{cw:g}" height="30" rx="6" '
                 f'fill="{CHIP}" stroke="{BORDER}"/>')
        s.append(dot(cx + 13, cy0 + 15, 3, col))
        s.append(txt(cx + 22, cy0 + 19.5, label, "mono400", 11, INK, 1.0))
        cx += cw + 10
    if cx > 600:
        ISSUES.append(f"hero chips overflow: {cx:.0f} > 600")

    if mode == "ascii":
        rows = ascii_rows()
        PW, PH = 272, 271
        PX, PY = W - P - PW, (H - PH) / 2
        sx = PW / (ASCII_COLS * 8.0)
        s.append(f'<g transform="translate({PX:.1f} {PY:.1f}) scale({sx:.4f})" '
                 f'font-family="{FONTS["mono400"][1]}" font-size="8" '
                 f'fill="{SAFFRON}" fill-opacity="0.92" xml:space="preserve">')
        for i, row in enumerate(rows):
            if row.strip():
                s.append(f'<text x="0" y="{8 + i*9.6:.1f}" textLength="{ASCII_COLS*8:g}" '
                         f'lengthAdjust="spacing">{esc(row)}</text>')
        s.append("</g>")
        s.append(f'<rect x="{PX-1:.1f}" y="{PY-1:.1f}" width="{PW+2:.1f}" height="{PH+2:.1f}" '
                 f'rx="4" fill="none" stroke="{BORDER}" stroke-opacity="0.8"/>')
    else:
        PCX, PCY, PR = 734, 132, 100
        if P64:
            s.append(f'<image x="{PCX-PR}" y="{PCY-PR}" width="{2*PR}" height="{2*PR}" '
                     f'clip-path="url(#pf)" preserveAspectRatio="xMidYMid slice" '
                     f'xlink:href="data:image/jpeg;base64,{P64}" '
                     f'href="data:image/jpeg;base64,{P64}"/>')
        # the tricolour as a ring, one band per third
        for a1, a2, col in ((-90, 30, SAFFRON), (30, 150, WHITE_A), (150, 270, GREEN)):
            s.append(arc(PCX, PCY, PR + 9, a1, a2, col, 2.5, 0.85))
    return "".join(s) + "</svg>\n", W, H

PORTRAIT = os.path.join(ASSETS, "portrait.jpg")
P64 = base64.b64encode(open(PORTRAIT, "rb").read()).decode() if os.path.exists(PORTRAIT) else None
if not P64:
    ISSUES.append(f"missing portrait at {PORTRAIT}")

sizes = {}
for mode, fname in (("photo", "hero.svg"), ("ascii", "hero-ascii.svg")):
    body, w_, h_ = hero_svg(mode)
    open(os.path.join(OUT, fname), "w").write(body)
    sizes[fname] = os.path.getsize(os.path.join(OUT, fname))

# ================================================================ 2. STATS
SW, SH = 293.333, 214
stats = [("DISCLOSED", "1", "CVE-2026-40316", "public vulnerability credit", SAFFRON),
         ("STANDARD", "LLM09", "OWASP Top 10 for LLMs", "co-lead, 2026 edition", WHITE_A),
         ("SHIPPED", "178", "FindMyGSoC", "stars, most-starred repo", GREEN)]
for i, (label, value, l1, l2, col) in enumerate(stats, 1):
    s = [svg_open(SW, SH, ["geist600", "geist400", "mono400"],
                  f"{label}: {value}. {l1}, {l2}.")]
    s.append(card_bg(SW, SH, r=14, fill=SURFACE))
    s.append(f'<rect x="26" y="24" width="{SW-52:.0f}" height="3" fill="{col}" fill-opacity="0.9"/>')
    s.append(txt(26, 56, label, "mono400", 10.5, MUTED, 2.4))
    fit(label, "mono400", 10.5, SW - 52, 2.4, f"stat{i} label")
    s.append(txt(24, 116, value, "geist600", 44, INK, -1.0))
    fit(value, "geist600", 44, SW - 48, -1.0, f"stat{i} value")
    if i == 3:
        s.append(star(24 + measure("geist600", 44, value, -1.0) + 22, 102, 15, col))
    s.append(f'<line x1="26" y1="136" x2="{SW-26:.0f}" y2="136" stroke="{BORDER}"/>')
    s.append(txt(26, 162, l1, "geist400", 13.5, INK))
    fit(l1, "geist400", 13.5, SW - 52, 0, f"stat{i} l1")
    s.append(txt(26, 181, l2, "geist400", 12.5, MUTED))
    fit(l2, "geist400", 12.5, SW - 52, 0, f"stat{i} l2")
    sizes[f"stat-{i}.svg"] = write(f"stat-{i}.svg", "".join(s), SW, SH)

# ================================================================ 3. TITLE
TW, TH = 880, 74
for scheme in ("dark", "light"):
    ink = INK if scheme == "dark" else "#0A0D12"
    rule = BORDER if scheme == "dark" else "#DCE2E5"
    muted = MUTED if scheme == "dark" else "#5C6B72"
    s = [svg_open(TW, TH, ["geist600", "mono400"], "What I'm building")]
    s.append(txt(0, 44, "What I'm building", "geist600", 25, ink, -0.4))
    tw = measure("geist600", 25, "What I'm building", -0.4)
    s.append(f'<line x1="{tw+18:.1f}" y1="36" x2="{TW}" y2="36" stroke="{rule}"/>')
    s.append(txt(TW, 44, "03 PROJECTS", "mono400", 10.5, muted, 2.4, anchor="end"))
    sizes[f"title-{scheme}.svg"] = write(f"title-{scheme}.svg", "".join(s), TW, TH)

# ================================================================ 4. REPOS
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
    s.append(txt(24, 40, idx, "mono400", 10.5, SAFFRON, 2.0))
    s.append(txt(RW - 24, 40, "REPO", "mono400", 10.5, "#3A4750", 2.0, anchor="end"))
    ns = 19 if measure("geist600", 19, name) <= RW - 48 else 16
    s.append(txt(24, 74, name, "geist600", ns, INK, -0.3))
    fit(name, "geist600", ns, RW - 44, -0.3, f"repo {name} title")
    y = 100
    for ln in wrap(desc, "geist400", 13, RW - 48)[:3]:
        s.append(txt(24, y, ln, "geist400", 13, MUTED))
        fit(ln, "geist400", 13, RW - 44, 0, f"repo {name} desc")
        y += 19
    s.append(f'<line x1="24" y1="{RH-40}" x2="{RW-24:.0f}" y2="{RH-40}" stroke="{BORDER}"/>')
    s.append(txt(24, RH - 17, foot, "mono400", 10, GREEN, 0.8))
    fit(foot, "mono400", 10, RW - 150, 0.8, f"repo {name} foot")
    s.append(txt(RW - 24, RH - 17, link, "mono400", 9.5, "#6C7D85", 0.4, anchor="end"))
    fit(link, "mono400", 9.5, 140, 0.4, f"repo {name} link")
    sizes[f"repo-{idx}.svg"] = write(f"repo-{idx}.svg", "".join(s), RW, RH)

# ================================================================ 5. STACK
KW, KH = 880, 214
s = [svg_open(KW, KH, ["geist400", "mono400"],
              "Stack. AI engineering: PyTorch, Transformers, LangChain, LlamaIndex, RAG, "
              "ChromaDB, pgvector, FastAPI. AI security: OWASP LLM Top 10, Garak, PyRIT, "
              "NeMo Guardrails, Semgrep, SARIF, Presidio. Platform: Python, Docker, "
              "Cloudflare Workers, Redis, GitHub Actions, Vercel.")]
s.append(card_bg(KW, KH, r=14, fill=SURFACE))
s.append(txt(30, 40, "STACK", "mono400", 10.5, MUTED, 2.4))
rows_ = [("AI ENGINEERING",
          ["PyTorch", "Transformers", "LangChain", "LlamaIndex", "ChromaDB",
           "pgvector", "FastAPI"], 62, SAFFRON),
         ("AI SECURITY",
          ["OWASP LLM Top 10", "Garak", "PyRIT", "NeMo Guardrails", "Semgrep", "SARIF",
           "Presidio"], 112, WHITE_A),
         ("PLATFORM",
          ["Python", "Docker", "Cloudflare Workers", "Redis", "GitHub Actions", "Vercel"],
          162, GREEN)]
for label, items, top, col in rows_:
    s.append(txt(30, top + 18, label, "mono400", 9.5, col, 1.6))
    x = 150
    for it in items:
        tw = measure("mono400", 11, it, 0.6)
        w_ = tw + 26
        if x + w_ > KW - 30:
            ISSUES.append(f"stack row '{label}' overflow at '{it}' ({x+w_:.0f})")
        s.append(f'<rect x="{x:g}" y="{top:g}" width="{w_:g}" height="28" rx="6" '
                 f'fill="{CHIP}" stroke="{BORDER}"/>')
        s.append(txt(x + 13, top + 18.5, it, "mono400", 11, INK, 0.6))
        x += w_ + 8
sizes["stack.svg"] = write("stack.svg", "".join(s), KW, KH)

# ================================================================ 6. QUOTE
QW, QH = 880, 112
s = [svg_open(QW, QH, ["serifit", "mono400"], "Engineer by choice.")]
s.append(card_bg(QW, QH, r=14))
s.append(tricolour((QW - 96) / 2, QH - 26, 96, 3, 2, 0.9))
s.append(txt(QW/2, 66, "Engineer by choice.", "serifit", 27, INK, 0, anchor="middle"))
s.append(txt(QW/2, 88, "OPEN TO SECURITY & AI ENGINEERING ROLES", "mono400", 10, MUTED,
             2.6, anchor="middle"))
sizes["quote.svg"] = write("quote.svg", "".join(s), QW, QH)

# ---------------------------------------------------------------- report
print(json.dumps(sizes, indent=1))
print("\ncontrast on surface", SURFACE)
for nm, col, need in (("INK", INK, 7.0), ("MUTED", MUTED, 4.5), ("SAFFRON", SAFFRON, 4.5),
                      ("GREEN", GREEN, 4.5), ("GREEN_D", GREEN_D, 3.0),
                      ("WHITE_A", WHITE_A, 7.0)):
    r = contrast(col, SURFACE)
    flag = "ok" if r >= need else "LOW"
    print(f"  {nm:8s} {r:5.2f}:1  need {need}  {flag}")
    if r < need:
        ISSUES.append(f"contrast {nm} {r:.2f} < {need}")
if ISSUES:
    print("\n!! ISSUES")
    for i in ISSUES: print("  ", i)
    sys.exit(1)
print("\nno overflow or contrast issues")
