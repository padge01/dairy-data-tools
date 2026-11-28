"""Cards: one self-contained HTML page per answer, in the ARPAS deck's look (inline SVG, no outside libraries, nothing
fetched), so it shows the same as a Claude artifact, in a browser, or in any agent's preview.

Rules: record only (no targets, no verdicts); every figure names its count and files; pounds first, "per cow"; colour
is never the only cue (every line and band is labelled in words); light and dark themes.
"""

from __future__ import annotations

import html
import math
import re
from collections import defaultdict
from datetime import date, timedelta

from . import explorer, feeding, nutrients
from .errors import DairyToolsError
from .herd import Herd
from .stats import ecm_lb, mean, quantile

CSS = """
:root{--canvas:#fafaf9;--surface:#fff;--raised:#f0f2ef;--text:#0a0a0a;--text2:#626762;--text3:#6b726c;--border:#dedfdc;--subtle:#efefec;
--line:#bfc3be;--bar:#cfd3ce;--ink:#0a0a0a;--l1:#c9a93a;--l2:#e08a2c;--l3:#9a6a43;--mark:#2b302c;
--forage:#6f9a52;--grain:#c9a93a;--protein:#5a80aa;--fat:#e08a2c;--byproduct:#a47b55;--mineral:#8f948f;--other:#b5b9b4;--feed:#b8962a;--feedwash:rgba(201,169,58,.20);
--n-ndf:#3987e5;--n-starch:#d95926;--n-cp:#199e70;--n-fat:#c98500;--n-other:#cfd3ce;
--sans:'Inter Variable','Inter','Segoe UI',system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root{--canvas:#0d110f;--surface:#151a17;--raised:#1d241f;--text:#f1f4f2;--text2:#aab3ad;
--text3:#7d8a82;--border:#323b35;--subtle:#232b26;--line:#4a564e;--bar:#3a463f;--ink:#f1f4f2;--l1:#e6cf7a;--l2:#f0a24a;
--l3:#c08a5c;--mark:#c9d1cb;--forage:#8cb56c;--grain:#e6cf7a;--protein:#86a9cf;--fat:#f0a24a;--byproduct:#c49a74;--mineral:#8f9a93;--other:#5d6660;--feed:#e6cf7a;--feedwash:rgba(230,207,122,.16);--n-ndf:#2a78d6;--n-starch:#eb6834;--n-cp:#1baf7a;--n-fat:#eda100;--n-other:#3a463f}}
*{box-sizing:border-box}body{margin:0;background:var(--canvas);color:var(--text);font-family:var(--sans)}
.card{max-width:1180px;margin:24px auto;background:var(--surface);border:1px solid var(--border);border-radius:22px;
padding:22px 30px 18px}
.head{display:flex;align-items:baseline;gap:16px;flex-wrap:wrap;border-bottom:1px solid var(--subtle);padding-bottom:10px}
.head h1{margin:0;font-size:46px;font-weight:700;letter-spacing:-.5px}.head span{font-size:20px;color:var(--text2)}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);border-bottom:1px solid var(--subtle)}
.tile{padding:12px 18px 14px 0;border-right:1px solid var(--subtle);margin-right:18px}.tile:last-child{border:0;margin:0}
.k{font-size:15px;color:var(--text2)}.v{font-size:28px;font-weight:650;margin:2px 0}.v small{font-size:15px;
font-weight:400;color:var(--text2);margin-left:6px}.n{font-size:14px;color:var(--text3)}
.body{display:grid;grid-template-columns:1fr 390px;gap:26px;padding-top:12px}
.side{border:1px solid var(--border);border-radius:16px;padding:16px 18px;align-self:stretch}
.side h2{font-size:16px;margin:0 0 8px;font-weight:650}.side p,.side li{font-size:15px;line-height:1.45;margin:0 0 8px}
.side ul{padding-left:18px;margin:0 0 8px}
.left{display:flex;flex-direction:column}.below{margin-top:18px;flex:1;display:flex;flex-direction:column;gap:16px}
.below .side{display:flex;flex-direction:column;justify-content:flex-start}.below .side:last-child{flex:1}
.figs{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:6px 0 4px}.figs .v{font-size:32px}
.side h2{margin-top:14px}.side h2:first-child{margin-top:0}.sub{font-size:12.5px;color:var(--text3);margin:2px 0 6px}
.chips{display:flex;flex-wrap:wrap;gap:6px}.chip2{display:inline-grid;padding:5px 10px;border-radius:10px;
background:var(--raised)}.ck{font-size:12px;color:var(--text2)}.cv{font-size:16px;font-weight:650}
.feedrow{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:4px 0;font-size:14px;
border-bottom:1px solid var(--subtle)}.feedrow:last-child{border:0}.chip{padding:2px 9px;border-radius:999px;
background:var(--raised);font-size:13px;font-weight:600;white-space:nowrap}.chip.new{outline:1.5px solid var(--line)}
.chip.gone{text-decoration:line-through;color:var(--text2)}
.foot{font-size:12.5px;color:var(--text3);border-top:1px solid var(--subtle);margin-top:12px;padding-top:8px}
svg text{font-family:var(--sans);fill:var(--text2)}svg .lab{fill:var(--text)}
.body>*,.tiles>*,.figs>*{min-width:0}
.body.one{grid-template-columns:1fr}.body.one .below{flex-direction:row;flex-wrap:wrap}.body.one .below .side{flex:1 1 320px}
.rg{font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;color:var(--text3);margin:9px 0 2px}
.rb{display:grid;grid-template-columns:minmax(0,10.5em) minmax(40px,1fr) auto;gap:10px;align-items:center;font-size:13.5px;padding:2px 0}
.rb .nm{line-height:1.2}.rb .tr{position:relative;height:13px}
.rb .fl{position:absolute;left:0;top:0;bottom:0;border-radius:3px}.rb .off{border:1.5px dashed var(--line);background:transparent}
.rb .tk{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--ink)}
.hr{display:grid;grid-template-columns:minmax(0,10em) minmax(40px,1fr) auto;gap:10px;align-items:center;font-size:14px;padding:3px 0}.hr .tr{position:relative;height:12px}.hr .fl{position:absolute;left:0;top:0;bottom:0;border-radius:3px;background:var(--mark)}.hr .lb{font-weight:650;white-space:nowrap}.hr .lb small{font-weight:400;color:var(--text2)}
.rb .lb{font-weight:650;white-space:nowrap;text-align:right}.rb .lb small{font-weight:400;color:var(--text2)}
.rations{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px 30px}
.rations h3{font-size:16px;margin:0 0 2px;font-weight:650}
body.slide .card,body.slide .page{zoom:1.5;max-width:1060px;margin:14px auto}
.grp{break-inside:avoid}.slide .body{grid-template-columns:1fr 1.15fr}.slide .rbars{columns:2;column-gap:26px}
.slide .rbars .grp:first-child .rg{margin-top:0}
.slide .rbars .rb{grid-template-columns:minmax(0,9.4em) minmax(40px,1fr) auto;gap:8px}
.tip-box,.tip-own{position:relative}.tip-own{outline:none;cursor:pointer}
.hits{position:absolute;top:0;bottom:0;left:0;right:0;display:flex}
.hit{flex:1 1 0;min-width:0;cursor:pointer;outline:none;-webkit-tap-highlight-color:transparent}
.hit:hover,.hit:focus{background:linear-gradient(var(--text2),var(--text2)) var(--gx,50%) 0/1.5px 100% no-repeat}
.hits.seg{top:10px;bottom:auto;height:20px}
.hits.seg .hit:hover,.hits.seg .hit:focus{background:none;border-radius:3px;box-shadow:inset 0 0 0 2px var(--ink)}
.mark-tip{position:absolute;bottom:calc(100% + 4px);left:50%;transform:translateX(-50%);background:var(--ink);color:var(--surface);
font-size:11px;font-weight:500;line-height:1.3;padding:3px 7px;border-radius:6px;white-space:nowrap;text-align:left;
box-shadow:0 2px 8px rgba(0,0,0,.18);opacity:0;pointer-events:none;transition:opacity .12s;z-index:20}
.mark-tip b{font-weight:700}.mark-tip.l{transform:none}.mark-tip.r{left:auto;transform:none}
.mark-tip.box{left:0;right:0;margin:0 auto;width:max-content;max-width:100%;white-space:normal;transform:none}
.tip-row{position:relative;outline:none;border-radius:4px;-webkit-tap-highlight-color:transparent}
.tip-row>.mark-tip{left:auto;right:0;width:max-content;max-width:100%;white-space:normal;transform:none}
.hit:hover>.mark-tip,.hit:focus>.mark-tip,.tip-own:hover>.mark-tip,.tip-own:focus>.mark-tip,
.tip-row:hover>.mark-tip,.tip-row:focus>.mark-tip{opacity:1}
.rb:hover,.rb:focus,.hr:hover,.hr:focus,.tip-row:hover,.tip-row:focus{background:var(--raised);
box-shadow:-5px 0 0 var(--raised),5px 0 0 var(--raised)}
.chart-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:thin;padding:58px 0 2px;margin-top:-54px}
.chart-inner{position:relative;min-width:620px}.chart-inner>svg{display:block}.slide .chart-inner{min-width:0}
.table-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;scrollbar-width:thin;padding:22px 0 2px;margin-top:-20px}
.more-rows{margin-top:4px}
.more-rows summary{list-style:none;cursor:pointer;font-size:12.5px;font-weight:500;color:var(--text2);padding:4px 0;user-select:none}
.more-rows summary::-webkit-details-marker{display:none}.more-rows summary:hover{color:var(--text)}
.more-rows summary::after{content:" ▾";font-size:11px}.more-rows[open] summary::after{content:" ▴"}
@media (max-width:1060px){.body{grid-template-columns:1fr}}
@media (max-width:820px){.tiles{grid-template-columns:repeat(2,1fr)}.head h1{font-size:34px}
.card{margin:8px;padding:16px}.figs .v{font-size:24px}}
"""


def esc(x) -> str:
    return html.escape(str(x))


def chip(label, value) -> str:
    """A small rounded tile: the label above, the figure below (words carry it; no colour needed)."""
    return f"<span class='chip2'><span class='ck'>{esc(label)}</span><span class='cv'>{esc(value)}</span></span>"


def _fmt_date(d: date) -> str:
    return f"{d:%b} {d.day}"


def tip(words: str, where: str = "", style: str = "") -> str:
    """The pill a hover, a tap or the Tab key shows (CSS only). `words` is HTML, already escaped. where: "" centred on
    its target, "l" / "r" running right / left from it (near an edge), "box" centred on the whole chart and wrapping."""
    return (f"<span class='mark-tip{' ' + where if where else ''}'" + (f" style='{style}'" if style else "")
            + f">{words}</span>")


def _spread(n: int, k: int) -> list[int]:
    """Up to k places in 0..n-1, evenly spaced, the first and the last among them."""
    if n <= k:
        return list(range(n))
    return sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})


def _day_hits(tips: dict, start: date, end: date, pad_l: float, pad_r: float, width: float, always=(), k: int = 14) -> str:
    """Strips over a chart's time axis, one for each of about k evenly spaced days (and the last day, and each day in
    `always`): hovering, tapping or tabbing to a strip draws a line at its day and shows that day's pill above the
    chart. tips: {day: HTML}. The strips together cover the plot, so there is no dead space between them."""
    days = sorted(d for d in tips if start <= d <= end)
    if not days:
        return ""
    span = max((end - start).days, 1)
    keep = {days[-1]} | {d for d in always if d in tips and start <= d <= end}
    near = span / (2.5 * k)     # an evenly spaced day this close to one that is always shown gives way to it
    chosen = sorted(keep | {days[i] for i in _spread(len(days), k) if all(abs((days[i] - f).days) > near for f in keep)})
    at = [(d - start).days / span for d in chosen]
    edges = [0.0] + [(a + b) / 2 for a, b in zip(at, at[1:])] + [1.0]
    out = []
    for i, d in enumerate(chosen):
        w = max(edges[i + 1] - edges[i], 1e-6)
        f = at[i]
        where, style = ("l", f"left:{100 * f:.2f}%") if f < .35 else ("r", f"right:{100 * (1 - f):.2f}%") if f > .65 \
            else ("", f"left:{100 * f:.2f}%")
        out.append(f"<span class='hit' tabindex='0' style='flex:0 0 {100 * w:.3f}%;--gx:{100 * (f - edges[i]) / w:.1f}%'>"
                   f"{tip(tips[d], where, style)}</span>")
    return (f"<div class='hits' style='left:{100 * pad_l / width:.2f}%;right:{100 * pad_r / width:.2f}%'>"
            f"{''.join(out)}</div>")


def _scroll_chart(svg: str, hits: str) -> str:
    """A wide chart in a strip a phone can swipe sideways, with room above it for the pills."""
    return f"<div class='chart-scroll'><div class='chart-inner'>{svg}{hits}</div></div>"


def _kde(values, lo, hi, points=41):
    v = [x for x in values if x is not None]
    n = len(v)
    if n < 2:
        return [0.0] * points
    m = sum(v) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in v) / (n - 1)) or 1.0
    h = 1.06 * sd * n ** -0.2
    xs = [lo + (hi - lo) * i / (points - 1) for i in range(points)]
    ys = [sum(math.exp(-0.5 * ((x - y) / h) ** 2) for y in v) for x in xs]
    top = max(ys) or 1
    return [y / top for y in ys]


def violin(values, label, unit="", width=260, height=46) -> str:
    """The spread from the lowest to the highest cow, the middle 80% darker, the median a line; labelled in words."""
    v = sorted(x for x in values if x is not None)
    if len(v) < 3:
        return ""
    lo, hi = v[0], v[-1]
    if hi == lo:
        hi = lo + 1
    shape = _kde(v, lo, hi)
    mid = height / 2
    x = lambda val: (val - lo) / (hi - lo) * width
    pts = [(lo + (hi - lo) * i / (len(shape) - 1), s) for i, s in enumerate(shape)]
    top = " L".join(f"{x(a):.1f},{mid - s * (mid - 3):.1f}" for a, s in pts)
    bottom = " L".join(f"{x(a):.1f},{mid + s * (mid - 3):.1f}" for a, s in reversed(pts))
    p10, p50, p90 = quantile(v, .1), quantile(v, .5), quantile(v, .9)
    cid = f"c{abs(hash(label)) % 100000}"
    at = lambda val: shape[min(len(shape) - 1, max(0, round((val - lo) / (hi - lo) * (len(shape) - 1))))]
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" preserveAspectRatio="none" role="img" '
            f'aria-label="{esc(label)}: lowest {lo:.0f}, middle 80% {p10:.0f} to {p90:.0f}, middle cow {p50:.0f}{unit}">'
            f'<defs><clipPath id="{cid}"><rect x="{x(p10):.1f}" y="0" width="{x(p90) - x(p10):.1f}" height="{height}"/>'
            f'</clipPath></defs><path d="M{top} L{bottom} Z" fill="var(--subtle)"/>'
            f'<path d="M{top} L{bottom} Z" fill="var(--bar)" clip-path="url(#{cid})"/>'
            f'<line x1="{x(p50):.1f}" x2="{x(p50):.1f}" y1="{mid - (mid - 3) * at(p50):.1f}" '
            f'y2="{mid + (mid - 3) * at(p50):.1f}" stroke="var(--ink)" stroke-width="2"/></svg>')


def violin_tip(values, label, unit="", width=260, height=46) -> str:
    """violin(), and on hover, tap or Tab a pill with its lowest, 10th to 90th percentile, median and highest. The
    drawing is violin()'s own, untouched, so a page that lines marks up against it (the cow card) still can."""
    svg = violin(values, label, unit, width, height)
    if not svg:
        return ""
    v = sorted(x for x in values if x is not None)
    words = (f"Lowest {v[0]:.0f} · P10–P90 {quantile(v, .1):.0f}–{quantile(v, .9):.0f} · Median "
             f"{quantile(v, .5):.0f} · Highest {v[-1]:.0f}{esc(unit)}")
    return f"<div class='tip-own' tabindex='0'>{svg}{tip(words, 'box')}</div>"


def lact_bar(groups) -> str:
    """One segment per lactation group, as wide as its cows; each segment answers a hover, tap or Tab with its count
    and share."""
    total = sum(n for _, n in groups) or 1
    colours = ["var(--l1)", "var(--l2)", "var(--l3)", "var(--bar)"]
    x, parts, hits = 0.0, [], []
    for (label, n), col in zip(groups, colours):
        w = 260 * n / total
        words = f"{esc(label)} lact: {n} cow{'s' if n != 1 else ''} ({100 * n / total:.0f}%)"
        parts.append(f'<rect x="{x:.1f}" y="10" width="{max(w - 2, 0):.1f}" height="20" rx="3" fill="{col}">'
                     f'<title>{words}</title></rect>')
        hits.append(f"<span class='hit' tabindex='0' style='flex:{n} 1 0'>{tip(words, 'box')}</span>")
        x += w
    # Stretched to the tile's width (as the violins are), so each segment's hit area sits exactly on it.
    return (f'<div class="tip-box"><svg viewBox="0 0 260 40" width="100%" height="40" preserveAspectRatio="none" '
            f'role="img" aria-label="lactations">{"".join(parts)}</svg><div class="hits seg">{"".join(hits)}</div></div>')


def spark(series, width=260, height=40, unit="") -> str:
    """A small daily line. About a dozen of its days (the first and the last among them) answer a hover, tap or Tab
    with the day and its figure."""
    vals = [v for _, v in series if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    hi = hi if hi > lo else lo + 1
    n = len(series)
    pts = " ".join(f"{i / (n - 1) * width:.1f},{height - 4 - (v - lo) / (hi - lo) * (height - 8):.1f}"
                   for i, (_, v) in enumerate(series) if v is not None)
    svg = (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" preserveAspectRatio="none" role="img" '
           f'aria-label="daily, {lo:.1f} to {hi:.1f}"><polyline points="{pts}" fill="none" stroke="var(--mark)" '
           f'stroke-width="1.6"/></svg>')
    picked = _spread(n, 12)
    hits = []
    for j, i in enumerate(picked):   # equal strips; the line each draws sits on its own day
        d, v = series[i]
        if v is None:
            hits.append("<span class='hit'></span>")
            continue
        gx = min(100.0, max(0.0, (i / (n - 1) * len(picked) - j) * 100))
        when = f"{_fmt_date(d)} · " if isinstance(d, date) else ""
        hits.append(f"<span class='hit' tabindex='0' style='--gx:{gx:.1f}%'>"
                    f"{tip(f'{when}{v:.1f}{esc(unit)}', 'box')}</span>")
    return f'<div class="tip-box">{svg}<div class="hits">{"".join(hits)}</div></div>'


def _week_avg(series):
    out = []
    for i in range(len(series)):
        span = [v for _, v in series[max(0, i - 6):i + 1] if v is not None]
        out.append((series[i][0], sum(span) / len(span) if span else None))
    return out


def _runs(points):
    """Unbroken stretches of (date, ...) points whose values are all present."""
    out, run = [], []
    for p in points:
        if all(v is not None for v in p[1:]):
            run.append(p)
        else:
            if len(run) > 1:
                out.append(run)
            run = []
    if len(run) > 1:
        out.append(run)
    return out


def ordinal_word(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def pen_panels(start: date, end: date, change: date | None = None, band=(), lines=(), fed=(), shares=None,
               milk_words="Milk, lb a cow", width=760) -> str:
    """Two panels on one time axis: milk above on its own close scale (`band` [(day, low, mid, high)] or `lines`
    [(label, style, [(day, lb)])]); below, the dry matter fed a cow by day, as a stack of what's in it when `shares`
    {day: {layer: share}} is known, else one area. The last ration change is marked across both."""
    from .nutrients import LAYERS
    pad_l, pad_r, gap = 40, 150, 40
    top_h = 150 if (band or any(len([v for _, v in s if v is not None]) > 1 for _, _, s in lines)) else 0
    low_h = 190 if fed else 0
    if not (top_h or low_h):
        return ""
    height = 24 + (top_h + gap if top_h else 0) + low_h + 26
    span = max((end - start).days, 1)
    x = lambda d: pad_l + (d - start).days / span * (width - pad_l - pad_r)
    out = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="milk and intake by day">']
    say = defaultdict(list)     # each day's pill: a line for its milk, a line for what was fed
    if top_h:
        milk = esc(milk_words.split(",")[0].split(":")[0])
        for d, l, m, h in band:
            if None not in (l, m, h) and start <= d <= end:
                say[d].append(f"{milk} {m:.0f} lb · middle 80% {l:.0f}–{h:.0f}")
        by_day = defaultdict(list)
        for label, _, s in lines:
            for d, v in s:
                if v is not None and start <= d <= end:
                    by_day[d].append(f"{esc(label)} {v:.1f}")
        for d, parts in by_day.items():
            say[d].append(f"{milk}: {' · '.join(parts)} lb")
    if low_h:
        share = None
        for d, v in sorted((d, v) for d, v in fed if start <= d <= end and v is not None):
            share = (shares or {}).get(d, share)
            say[d].append(f"Fed {v:.1f} lb DM" + "".join(
                f" · {esc(label)} {100 * share.get(key, 0):.0f}%" for key, label in LAYERS[:4] if share))

    def ends_text(ends):
        ends.sort()
        for i in range(1, len(ends)):
            ends[i][0] = max(ends[i][0], ends[i - 1][0] + 15)
        return "".join(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="12.5" class="lab">{t}</text>' for ly, lx, t in ends)

    y0 = 24
    if top_h:
        vals = [v for b in band for v in (b[1], b[3])] + [v for _, _, s in lines for _, v in s if v is not None]
        lo, hi = min(vals), max(vals)
        padv = (hi - lo) * .12 or 1
        lo, hi = lo - padv, hi + padv
        y = lambda v: y0 + top_h - (v - lo) / (hi - lo) * top_h
        out.append(f'<text x="{pad_l - 34}" y="{y0 - 8}" class="lab" font-size="13">{esc(milk_words)}</text>')
        for k in range(4):
            v = lo + (hi - lo) * (k + .5) / 4
            out.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--subtle)"/>'
                       f'<text x="{pad_l - 6}" y="{y(v) + 4:.1f}" font-size="11" text-anchor="end">{v:.0f}</text>')
        ends = []
        for run in _runs(band):
            up = " ".join(f"{x(d):.1f},{y(h):.1f}" for d, l, m, h in run)
            dn = " ".join(f"{x(d):.1f},{y(l):.1f}" for d, l, m, h in reversed(run))
            out.append(f'<polygon points="{up} {dn}" fill="var(--bar)" opacity=".75"/><polyline points="'
                       + " ".join(f"{x(d):.1f},{y(m):.1f}" for d, l, m, h in run)
                       + '" fill="none" stroke="var(--ink)" stroke-width="2.2"/>')
        if band:
            ends.append([y(band[-1][2]) + 4, x(band[-1][0]) + 6, f'<tspan font-weight="650">{band[-1][2]:.0f}</tspan> lb'])
        for label, style, s in lines:
            s = [(d, v) for d, v in s if v is not None and start <= d <= end]
            if len(s) < 2:
                continue
            w, colour = ("2.4", "var(--ink)") if style == "bold" else ("1", "var(--line)")
            out.append(f'<polyline points="{" ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in s)}" fill="none" '
                       f'stroke="{colour}" stroke-width="{w}"/>')
            if style == "bold":
                ends.append([y(s[-1][1]) + 4, x(s[-1][0]) + 6, f'<tspan font-weight="650">{s[-1][1]:.1f}</tspan> lb'])
        out.append(ends_text(ends))
        y0 += top_h + gap
    if low_h:
        fed = [(d, v) for d, v in fed if start <= d <= end and v is not None]
        # three-day average, so the stack reads as a level rather than noise
        smooth = [(d, mean([v for _, v in fed[max(0, i - 2):i + 1]])) for i, (d, _) in enumerate(fed)]
        ymax = max(v for _, v in smooth) * 1.1
        step = 10 if ymax <= 60 else 20
        y = lambda v: y0 + low_h - v / ymax * low_h
        out.append(f'<text x="{pad_l - 34}" y="{y0 - 8}" class="lab" font-size="13">Intake, lb of dry matter a cow'
                   + (", and what's in it" if shares else "") + "</text>")
        v = 0
        while v <= ymax:
            out.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--subtle)"/>'
                       f'<text x="{pad_l - 6}" y="{y(v) + 4:.1f}" font-size="11" text-anchor="end">{v}</text>')
            v += step
        if shares:
            last_share = None
            stack = []
            for d, total in smooth:
                last_share = shares.get(d, last_share)
                stack.append((d, total, last_share))
            stack = [(d, tot, sh) for d, tot, sh in stack if sh]
            base = {d: 0.0 for d, _, _ in stack}
            ends = []
            for key, label in LAYERS:
                upper = [(d, base[d] + tot * sh.get(key, 0)) for d, tot, sh in stack]
                pts_up = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in upper)
                pts_dn = " ".join(f"{x(d):.1f},{y(base[d]):.1f}" for d, _, _ in reversed(stack))
                out.append(f'<polygon points="{pts_up} {pts_dn}" fill="var(--n-{key})"/>')
                d_last, tot_last, sh_last = stack[-1]
                mid = base[d_last] + tot_last * sh_last.get(key, 0) / 2
                ends.append([y(mid) + 4, x(d_last) + 6, f'{esc(label)} <tspan font-weight="650">'
                             f'{tot_last * sh_last.get(key, 0):.1f}</tspan>'])
                for d, tot, sh in stack:
                    base[d] += tot * sh.get(key, 0)
            out.append(ends_text(ends))
        else:
            pts = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in smooth)
            out.append(f'<polygon points="{x(smooth[0][0]):.1f},{y(0):.1f} {pts} {x(smooth[-1][0]):.1f},{y(0):.1f}" '
                       f'fill="var(--feedwash)"/><polyline points="{pts}" fill="none" stroke="var(--feed)" stroke-width="1.6"/>'
                       f'<text x="{x(smooth[-1][0]) + 6:.1f}" y="{y(smooth[-1][1]) + 4:.1f}" font-size="12.5" class="lab">'
                       f'<tspan font-weight="650">{smooth[-1][1]:.1f}</tspan> fed</text>')
        y_bottom = y(0)
    else:
        y_bottom = y0 - gap
    if change and start <= change <= end:
        cx = x(change)
        out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="14" y2="{y_bottom:.1f}" stroke="var(--ink)" '
                   f'stroke-dasharray="3 3"/><text x="{cx + 5:.1f}" y="12" font-size="12.5" class="lab">'
                   f'Ration change, {_fmt_date(change)}</text>')
    d = start
    while d <= end:
        if d.day in (1, 15):
            out.append(f'<text x="{x(d):.1f}" y="{height - 6}" font-size="11.5" text-anchor="middle">{_fmt_date(d)}</text>')
        d += timedelta(days=1)
    tips = {d: f"<b>{_fmt_date(d)}</b>" + (" · ration change" if d == change else "") + "".join(f"<br>{w}" for w in ws)
            for d, ws in say.items()}
    return _scroll_chart("".join(out) + "</svg>", _day_hits(tips, start, end, pad_l, pad_r, width, always=(change,)))


def more_rows(rows: list[str], limit: int, what: str, wrap=("", "")) -> str:
    """The first `limit` rows, and the rest behind a line to click ("+3 more events", what="more event"): nothing is dropped. With
    limit None every row shows. wrap: (opening, closing) HTML put round the rows that are behind the click."""
    if limit is None or len(rows) <= limit:
        return "".join(rows)
    n = len(rows) - limit
    return ("".join(rows[:limit]) + f"<details class='more-rows'><summary>+{n} {esc(what)}{'s' if n != 1 else ''}"
            f"</summary>{wrap[0]}{''.join(rows[limit:])}{wrap[1]}</details>")


def health_rows(health, cows: int, limit: int | None = 8) -> str:
    """One bar per health event: the cows with it in the last days, and how many that is in 100 cows of the pen.
    Past `limit` events the rest sit behind "+N more events" (limit None: all of them shown)."""
    top = max(h["cows"] for h in health) or 1
    rows = []
    for h in health:
        name, n = esc(h["event"].capitalize()), h["cows"]
        words = f"{name}: {n} cow{'s' if n != 1 else ''}"
        if h.get("events"):
            words += f" · {h['events']} event{'s' if h['events'] != 1 else ''}"
        if cows:
            words += f" · {100 * n / cows:.1f} in 100 cows"
        rows.append(
            f"<div class='hr tip-row' tabindex='0'><span>{name}</span><div class='tr'><div class='fl' "
            f"style='width:{max(3, 100 * n / top):.0f}%'></div></div><span class='lb'>{n} "
            f"cow{'s' if n != 1 else ''}" + (f" <small>· {100 * n / cows:.0f} in 100</small>" if cows else "")
            + f"</span>{tip(words)}</div>")
    return more_rows(rows, limit, "more event")


def time_chart(rows, change: date | None, start: date, end: date, width=760) -> str:
    """rows: [(title, unit, [(label, style, series)])] stacked panels on one date axis; series [(date, value)]."""
    pad_l, pad_r, panel_h, gap = 46, 120, 120, 34
    height = len(rows) * (panel_h + gap) + 28
    span = max((end - start).days, 1)
    x = lambda d: pad_l + (d - start).days / span * (width - pad_l - pad_r)
    out = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="by day, {start} to {end}">']
    say = defaultdict(list)     # each day's pill: a line for each panel
    for title, unit, lines in rows:
        by_day = defaultdict(list)
        for label, _, s in lines:
            for d, v in s:
                if v is not None and start <= d <= end:
                    by_day[d].append(f"{esc(label)} {v:.1f}")
        for d, parts in by_day.items():
            say[d].append(f"{esc(title)}: {' · '.join(parts)}" + (f" {esc(unit)}" if unit else ""))
    for k, (title, unit, lines) in enumerate(rows):
        top = k * (panel_h + gap) + 18
        vals = [v for _, _, s in lines for _, v in s if v is not None]
        if not vals:
            continue
        lo, hi = min(vals), max(vals)
        padv = (hi - lo) * .12 or 1
        lo, hi = lo - padv, hi + padv
        y = lambda v: top + panel_h - (v - lo) / (hi - lo) * panel_h
        out.append(f'<text x="{pad_l - 40}" y="{top - 6}" class="lab" font-size="13">{esc(title)}</text>')
        for t in range(4):
            v = lo + (hi - lo) * (t + .5) / 4
            out.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--subtle)"/>'
                       f'<text x="{pad_l - 6}" y="{y(v) + 4:.1f}" font-size="11" text-anchor="end">{v:.0f}</text>')
        ends = []
        for label, style, s in lines:
            s = [(d, v) for d, v in s if v is not None and start <= d <= end]
            if len(s) < 2:
                continue
            pts = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in s)
            dash = ' stroke-dasharray="5 4"' if style == "dashed" else ""
            w = "2.4" if style == "bold" else "1.6" if style == "dashed" else "1"
            colour = "var(--line)" if style == "thin" else "var(--ink)" if style == "bold" else "var(--text2)"
            out.append(f'<polyline points="{pts}" fill="none" stroke="{colour}" stroke-width="{w}"{dash}/>')
            if style != "thin":
                d, v = s[-1]
                ends.append([y(v) + 4, x(d) + 6, f'<tspan font-weight="650">{v:.1f}</tspan> {esc(label)}'])
        # End labels never overlap: each sits at least 15 px below the one above it.
        ends.sort()
        for i in range(1, len(ends)):
            ends[i][0] = max(ends[i][0], ends[i - 1][0] + 15)
        for ly, lx, text in ends:
            out.append(f'<text x="{lx:.1f}" y="{ly:.1f}" font-size="12.5" class="lab">{text}</text>')
    if change and start <= change <= end:
        cx = x(change)
        out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="10" y2="{height - 26}" stroke="var(--ink)" '
                   f'stroke-dasharray="3 3"/><text x="{cx + 5:.1f}" y="12" font-size="12.5" class="lab">'
                   f'Ration change, {_fmt_date(change)}</text>')
    d = start
    while d <= end:
        if d.day in (1, 15):
            out.append(f'<text x="{x(d):.1f}" y="{height - 6}" font-size="11.5" text-anchor="middle">{_fmt_date(d)}</text>')
        d += timedelta(days=1)
    out.append("</svg>")
    tips = {}
    for d, ws in say.items():   # at most three lines, so the pill fits in the room above the chart
        ws = ws if len(ws) <= 2 else [" · ".join(ws[:(len(ws) + 1) // 2]), " · ".join(ws[(len(ws) + 1) // 2:])]
        tips[d] = f"<b>{_fmt_date(d)}</b>" + (" · ration change" if d == change else "") + "".join(f"<br>{w}" for w in ws)
    return _scroll_chart("".join(out), _day_hits(tips, start, end, pad_l, pad_r, width, always=(change,)))


FEED_TYPES = (   # (type, words in the feed's name); the first match wins, so silage counts as forage
    ("Forages", "forage", r"silage|haylage|\bhay\b|straw|alfalfa|lucerne|pasture|grass|baleage|green ?chop|forage"),
    ("Minerals and additives", "mineral", r"mineral|premix|vitamin|\bsalt\b|buffer|bicarb|limestone|rumensin|"
     r"monensin|yeast|additive|binder|magnesium|mag ox|selenium|\bvit\b|\bmix\b"),
    ("Fats", "fat", r"\bfat\b|tallow|bypass|megalac|\boil\b|calcium salts|energizer"),
    ("By-products", "byproduct", r"hull|cottonseed|pulp|\bbran\b|middlings|midds|by-?product|screenings|cannery|peel|whey|bakery|candy"),
    ("Proteins", "protein", r"canola|\bsoy|distillers|\bddgs?\b|gluten|\bmeal\b|blood|fish|urea|amino|protein"),
    ("Grains and energy", "grain", r"corn|maize|barley|wheat|sorghum|milo|\boats?\b|hominy|bakery|molasses|grain|"
     r"starch|flake|earlage|snaplage|high moisture|\bhmc\b"),
)


def feed_type(name: str) -> tuple[str, str]:
    """(type in words, colour name) for a feed, from its name; "Other feeds" when nothing matches."""
    for words, colour, pattern in FEED_TYPES:
        if re.search(pattern, name, re.I):
            return words, colour
    return "Other feeds", "other"


def ration_bars(after: dict, before: dict | None = None, only_moved: bool = False, top: float | None = None) -> str:
    """One bar per feed, lb of dry matter per cow, grouped and coloured by feed type. Every bar carries its feed's
    name and pounds, and its group is named, so colour is never the only cue. With `before`, a tick marks each feed's
    amount before and the label reads before -> after; feeds that came off show as an empty dashed bar. `top`: the
    pounds a full bar stands for, so several pens' bars share one scale."""
    not_feed = re.compile(r"^\s*(water|push ?out)\s*$", re.I)   # in some recipes, but not feeds
    after = {k: v for k, v in after.items() if not not_feed.match(k)}
    before = {k: v for k, v in (before or {}).items() if not not_feed.match(k)}
    feeds = sorted(set(after) | set(before))
    moved = [k for k in feeds if abs(after.get(k, 0.0) - before.get(k, 0.0)) >= .25] if before else feeds
    show = moved if only_moved else feeds
    if not show:
        return "<p class='sub'>No feeds recorded.</p>"
    top = top or max(max(after.get(k, 0.0), before.get(k, 0.0)) for k in show) or 1
    all_after, all_before = sum(after.values()), sum(before.values())   # the whole ration, for each feed's share
    share = lambda lb, of: f" · {100 * lb / of:.1f}% of DM" if of else ""
    groups = defaultdict(list)
    for k in show:
        groups[feed_type(k)].append(k)
    order = [(w, c) for w, c, _ in FEED_TYPES] + [("Other feeds", "other")]
    out = []
    for words, colour in order:
        ks = sorted(groups.get((words, colour), []), key=lambda k: -max(after.get(k, 0.0), before.get(k, 0.0)))
        if not ks:
            continue
        out.append(f"<div class='grp'><div class='rg'>{esc(words)}</div>")
        for k in ks:
            a, b = before.get(k, 0.0), after.get(k, 0.0)
            changed = bool(before) and k in moved
            if changed and b < .05:
                bar = f"<div class='fl off' style='width:{100 * a / top:.1f}%'></div>"
                label = f"<small>off · was</small> {a:.1f}"
            else:
                bar = f"<div class='fl' style='width:{max(1.5, 100 * b / top):.1f}%;background:var(--{colour})'></div>"
                if changed and a >= .05:
                    bar += f"<div class='tk' style='left:{100 * a / top:.1f}%'></div>"
                label = (f"<small>new ·</small> {b:.1f}" if changed and a < .05 else
                         f"<small>{a:.1f} →</small> {b:.1f}" if changed else f"{b:.1f}")
            now = f"{b:.1f} lb DM{share(b, all_after)}"
            words = (f"{esc(k)}: off · was {a:.1f} lb DM{share(a, all_before)}" if changed and b < .05 else
                     f"{esc(k)}: new · {now}" if changed and a < .05 else
                     f"{esc(k)}: {now} · was {a:.1f} lb{share(a, all_before)}" if changed else f"{esc(k)}: {now}")
            out.append(f"<div class='rb tip-row' tabindex='0'><span class='nm' title='{esc(k)}'>{esc(k)}</span>"
                       f"<div class='tr'>{bar}</div><span class='lb'>{label} <small>lb</small></span>{tip(words)}</div>")
        out.append("</div>")
    if only_moved and len(feeds) > len(show):
        n = len(feeds) - len(show)
        out.append(f"<div class='sub'>{n} other feed{'s' if n != 1 else ''} unchanged</div>")
    return "".join(out)


def _recipe(herd: Herd, ezfeed_pen: str, first: date, last: date) -> dict:
    """The pen's recipe, lb of dry matter per head called for, averaged over the days from first to last."""
    by_day = defaultdict(dict)
    for r in herd.feed.get("feed_delivery", []):
        if r["pen"] == ezfeed_pen and not r.get("premix") and r.get("target_dm_lb_per_head") \
                and first <= r["date"] <= last:
            by_day[r["date"]][r["ingredient"]] = r["target_dm_lb_per_head"]
    feeds = {k for d in by_day for k in by_day[d]}
    return {k: sum(by_day[d].get(k, 0.0) for d in by_day) / len(by_day) for k in feeds} if by_day else {}


def _recipe_changes(herd: Herd, ezfeed_pen: str):
    """Days the pen's recipe changed (a feed in or out, or a share moving half a point): (day, the feeds that moved,
    the recipe the week before, the recipe the week after)."""
    by_day = defaultdict(dict)
    for r in herd.feed.get("feed_delivery", []):
        if r["pen"] == ezfeed_pen and not r.get("premix") and r.get("target_dm_lb_per_head"):
            by_day[r["date"]][r["ingredient"]] = r["target_dm_lb_per_head"]
    days = sorted(by_day)
    out = []
    for a, b in zip(days, days[1:]):
        if (b - a).days > 1:
            continue
        ra, rb = by_day[a], by_day[b]
        ta, tb = sum(ra.values()), sum(rb.values())
        sa = {k: 100 * v / ta for k, v in ra.items()}
        sb = {k: 100 * v / tb for k, v in rb.items()}
        if set(ra) != set(rb) or any(abs(sa[k] - sb[k]) >= .5 for k in sa):
            # The recipe the week before against the week after, averaged (a single day carries the pen's call too).
            def week(first, last):
                ds = [d for d in days if first <= d <= last]
                feeds = {k for d in ds for k in by_day[d]}
                return {k: sum(by_day[d].get(k, 0.0) for d in ds) / len(ds) for k in feeds} if ds else {}
            wa = week(b - timedelta(days=7), b - timedelta(days=1))
            wb = week(b, b + timedelta(days=6))
            moved = [(k, wa.get(k, 0.0), wb.get(k, 0.0)) for k in sorted(set(wa) | set(wb))
                     if abs(wa.get(k, 0.0) - wb.get(k, 0.0)) >= .25]
            out.append((b, moved, wa, wb))
    return out



def _shift_years(d, years):
    """The same day another year; 29 February becomes the 28th in a year without it."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)

def pen_card_html(herd: Herd, pen, pen_milk: dict | None = None, days: int = 75, slide: bool = False) -> str:
    """Pen 21's card: who is in it, their milk, their stage, intake; ECM and intake by day with a ration change
    marked and last fall's same weeks beside this fall's; the ration as bars. pen_milk: {(pen, date): {milk, fat,
    protein}}. slide: for a projector, bigger and with fewer items (ECM only, the feeds that moved, no health or feed)."""
    pc = explorer.pen_card(herd, pen)
    t = pc["test"]
    pen = pc["pen"]
    cows = herd.cows_by_pen.get(pen, [])
    milking = [c for c in cows if herd.status(c) == "milking"]
    end = herd.as_of
    start = end - timedelta(days=days - 1)
    feed = None
    if herd.feed:
        try:
            rows = feeding.pen_feed(herd, days=7, pen=pen)["pens"]
            feed = rows[0] if rows else None
        except DairyToolsError:
            feed = None
    # Tiles.
    milk_vals = [c["test_milk"] for c in milking if (c.get("test_milk") or 0) > 0]
    dim_vals = [c["days_in_milk"] for c in milking if c.get("days_in_milk") is not None]
    groups = {g["lactation"]: g["cows"] for g in pc["lactation"]}
    lact = [(l, n) for l, n in (("1st", groups.get("1", 0)), ("2nd", groups.get("2", 0)), ("3rd+", groups.get("3+", 0)))
            if n]
    median_lact = quantile([c["lactation"] for c in milking if c.get("lactation")], .5)
    pen_days = feeding._pen_feed_days(herd)
    intake_series = sorted((r["date"], r["dm_lb_per_head"] * (r["head_count"] or 0) / max(len(cows), 1)
                            if r.get("head_count") else r["dm_lb_per_head"])
                           for r in pen_days if r.get("dc_pen") == pen and start <= r["date"] <= end)
    changes = _recipe_changes(herd, feed["ezfeed_pen"]) if feed else []
    change = changes[-1][0] if changes else None
    # The pen's place among the milking pens, by ECM (or milk where the herd doesn't test).
    by_pen = defaultdict(list)
    for c in herd.in_herd():
        if herd.status(c) == "milking" and (c.get("test_milk") or 0) > 0:
            e = ecm_lb(c["test_milk"], c.get("test_fat_pct"), c.get("test_protein_pct"))
            by_pen[c["pen"]].append(e if e is not None else c["test_milk"])
    means = sorted(((mean(v), k) for k, v in by_pen.items() if len(v) >= 5), reverse=True)
    place = next((i for i, (_, k) in enumerate(means, 1) if k == pen), None)
    rank = ("Highest" if place == 1 else ordinal_word(place)) + f" of {len(means)} pens" if place and len(means) > 1 else ""
    # Called for: EZfeed's target, on the same per-cow footing as the intake.
    called = None
    if feed and feed.get("dmi_lb_per_cow"):
        week = [r for r in herd.feed.get("feed_delivery", []) if r["pen"] == feed["ezfeed_pen"] and not r.get("premix")
                and end - timedelta(days=6) <= r["date"] <= end]
        tgt = sum(r.get("target_dm_lb_per_head") or 0 for r in week)
        act = sum(r.get("actual_dm_lb_per_head") or 0 for r in week)
        if tgt and act:
            called = feed["dmi_lb_per_cow"] * tgt / act
    tiles = [
        (f"Milk per cow, {herd.milk_words}", f"{t['milk_mean_lb']:.1f} lb" if t["milk_mean_lb"] else "n/a",
         f"ECM {t['ecm_mean_lb']:.1f} lb" if t["ecm_mean_lb"] else "",
         violin_tip(milk_vals, f"milk, {herd.milk_words}", " lb"),
         " · ".join(x for x in (rank, f"middle 80%: {quantile(milk_vals, .1):.0f}–{quantile(milk_vals, .9):.0f} lb"
                                if milk_vals else "no milk recorded") if x)),
        ("Days in milk", f"{quantile(dim_vals, .5):.0f}" if dim_vals else "n/a", "median",
         violin_tip(dim_vals, "days in milk", " days"),
         f"Middle 80%: {quantile(dim_vals, .1):.0f}–{quantile(dim_vals, .9):.0f} days" if dim_vals else ""),
        ("Lactation", f"{median_lact:.0f}" if median_lact else "n/a", "median", lact_bar(lact),
         " · ".join(f"{l} {n}" for l, n in lact)),
        ("Intake, last 7 days", f"{feed['dmi_lb_per_cow']:.1f} lb" if feed and feed.get("dmi_lb_per_cow") else "n/a",
         "DM per cow", spark(intake_series[-30:], unit=" lb DM"),
         (f"Called for {called:.1f} lb · daily, last 30 days" if called else "Daily, the last 30 days")
         if intake_series else "No EZfeed records"),
    ]
    tile_html = "".join(f'<div class="tile"><div class="k">{esc(k)}</div><div class="v">{esc(v)}<small>{esc(s)}</small>'
                        f'</div>{chart}<div class="n">{esc(n)}</div></div>' for k, v, s, chart, n in tiles)
    # Milk above: each day's middle cow and middle 80% (daily weights), or the pen's ECM by day; intake below as a stack.
    band = sorted((d, v["low"], v["mid"], v["high"]) for (p, d), v in herd.pen_milk_days.items()
                  if p == pen and start <= d <= end)
    band = band if len(band) >= 2 else []
    lines = []
    if pen_milk and not band:
        ecm = []
        d = start
        while d <= end:
            v = pen_milk.get((pen, d))
            ecm.append((d, ecm_lb(v["milk_lb"], v["fat_pct"], v["protein_pct"]) if v and v.get("fat_pct") else None))
            d += timedelta(days=1)
        lines = [("daily", "thin", ecm), ("7-day", "bold", _week_avg(ecm))]
    shares, how = ({}, {})
    if feed:
        analyses = {}
        for f in herd.files:
            if f["kind"] == "analyses":
                analyses.update(nutrients.read_analyses(f["path"]))
        shares, how = nutrients.pen_layers_by_day(herd, feed["ezfeed_pen"], analyses)
    # A slide draws the chart narrower, so its words come out bigger.
    chart = pen_panels(start, end, change, band=band, lines=lines, fed=intake_series, shares=shares,
                       milk_words=("ECM, lb a cow" if lines else "Milk, lb a cow: the middle cow (shading: the middle 80%)"),
                       width=560 if slide else 760)
    what_in = nutrients.source_words(how) if shares else ""
    if chart and what_in:
        chart += f"<div class='sub'>{esc(what_in)}</div>"
    # Side: the current ration as bars.
    side = []
    if feed:   # the pen's current ration; the chart marks when it last changed
        recipe = _recipe(herd, feed["ezfeed_pen"], end - timedelta(days=6), end)
        if recipe:
            side.append(f"<h2>Ration, last 7 days</h2><div class='sub'>lb of dry matter per cow, called for</div>"
                        f"<div class='rbars'>{ration_bars(recipe)}</div>")
    # Feed goes under the charts; a slide leaves it out.
    below = []
    if pc["health"] and not slide:   # under the ration, so the two columns end together
        side.append(f"<h2>Health, last {pc['days']} days</h2><div class='sub'>Cows in the pen now with each "
                    f"event</div>{health_rows(pc['health'], len(cows))}")
    if feed and feed.get("dmi_lb_per_cow") and not slide:
        eff_key = "ecm_per_lb_dm" if feed.get("ecm_per_lb_dm") else "milk_per_lb_dm"
        efficiency = format(feed[eff_key], ".2f") if feed.get(eff_key) else "n/a"
        per_cow = "$" + format(feed["feed_cost_per_cow"], ".2f") if feed.get("feed_cost_per_cow") is not None else "n/a"
        per_cwt = "$" + format(feed["feed_cost_per_cwt"], ".2f") if feed.get("feed_cost_per_cwt") else "n/a"
        figures = (("ECM per lb DM" if eff_key == "ecm_per_lb_dm" else "Milk per lb DM", efficiency),
                   ("Feed per cow", per_cow), ("Feed per cwt", per_cwt))
        below.insert(0, "<h2>Feed, last 7 days</h2><div class='figs'>" + "".join(
            f"<div><div class='k'>{esc(k)}</div><div class='v'>{esc(v)}</div></div>" for k, v in figures)
            + "</div><div class='sub'>Delivered feed, per cow in the pen</div>")
    below_html = ("<div class='below'>" + "".join(f"<div class='side'>{b}</div>" for b in below) + "</div>") if below else ""
    kinds = {f["kind"] for f in herd.files}
    cow_words = "cow, test and event reports" if herd.milk_words == "last test" else "cow and event reports"
    sources = [f"DairyComp's {cow_words}" if "events" in kinds else "DairyComp's cow report"]
    if "feed" in kinds:
        sources.append("EZfeed's intake and pen summary reports")
    if "pen_milk" in kinds:
        sources.append("pen milk by day")
    files = ", ".join(sources)
    kind = {"milking": "Milking cows", "dry": "Dry cows", "heifer": "Heifers"}.get(pc["summary"]["kind"], "Mixed")
    left_html = chart + below_html
    side_html = f"<div class='side'>{''.join(side)}</div>" if side else ""
    if left_html and side_html:
        body_html = f"<div class='body'><div class='left'>{left_html}</div>{side_html}</div>"
    elif left_html or side_html:   # one column: what there is, full width
        body_html = f"<div class='body one'><div class='left'>{left_html or side_html}</div></div>"
    else:
        body_html = ""
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>Pen {esc(pen)}</title><style>{CSS}</style></head>"
            f"<body{' class=slide' if slide else ''}><div class='card'><div class='head'><h1>Pen {esc(pen)}</h1><span>{len(cows)} cows · {kind} · "
            f"{_fmt_date(start)} to {_fmt_date(end)}</span></div><div class='tiles'>{tile_html}</div>"
            f"{body_html}<div class='foot'>From {esc(files) if not slide else 'DairyComp and EZfeed'}. Records end {end:%b %d, %Y}. "
            + ("ECM = 0.327 × milk + 12.95 × fat lb + 7.65 × protein lb, worked out here. " if herd.milk_words == "last test"
               else "Milk is each cow's latest daily weight: no tests, so no ECM. ")
            + "Intake is delivered, per DairyComp head.</div></div>"
            f"</body></html>")
