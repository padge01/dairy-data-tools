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

from . import explorer, feeding
from .herd import Herd
from .stats import ecm_lb, mean, quantile

CSS = """
:root{--canvas:#fafaf9;--surface:#fff;--raised:#f0f2ef;--text:#0a0a0a;--text2:#626762;--text3:#6b726c;--border:#dedfdc;--subtle:#efefec;
--line:#bfc3be;--bar:#cfd3ce;--ink:#0a0a0a;--l1:#c9a93a;--l2:#e08a2c;--l3:#9a6a43;--mark:#2b302c;
--forage:#6f9a52;--grain:#c9a93a;--protein:#5a80aa;--fat:#e08a2c;--byproduct:#a47b55;--mineral:#8f948f;--other:#b5b9b4;
--sans:'Inter Variable','Inter','Segoe UI',system-ui,sans-serif}
@media (prefers-color-scheme:dark){:root{--canvas:#0d110f;--surface:#151a17;--raised:#1d241f;--text:#f1f4f2;--text2:#aab3ad;
--text3:#7d8a82;--border:#323b35;--subtle:#232b26;--line:#4a564e;--bar:#3a463f;--ink:#f1f4f2;--l1:#e6cf7a;--l2:#f0a24a;
--l3:#c08a5c;--mark:#c9d1cb;--forage:#8cb56c;--grain:#e6cf7a;--protein:#86a9cf;--fat:#f0a24a;--byproduct:#c49a74;--mineral:#8f9a93;--other:#5d6660}}
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
.below .side{display:flex;flex-direction:column;justify-content:center}.below .side:last-child{flex:1}
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
.rg{font-size:11.5px;letter-spacing:.04em;text-transform:uppercase;color:var(--text3);margin:9px 0 2px}
.rb{display:grid;grid-template-columns:minmax(0,10.5em) minmax(40px,1fr) auto;gap:10px;align-items:center;font-size:13.5px;padding:2px 0}
.rb .nm{line-height:1.2}.rb .tr{position:relative;height:13px}
.rb .fl{position:absolute;left:0;top:0;bottom:0;border-radius:3px}.rb .off{border:1.5px dashed var(--line);background:transparent}
.rb .tk{position:absolute;top:-3px;bottom:-3px;width:2px;background:var(--ink)}
.rb .lb{font-weight:650;white-space:nowrap;text-align:right}.rb .lb small{font-weight:400;color:var(--text2)}
.rations{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px 30px}
.rations h3{font-size:16px;margin:0 0 2px;font-weight:650}
body.slide .card,body.slide .page{zoom:1.5;max-width:1060px;margin:14px auto}
.grp{break-inside:avoid}.slide .body{grid-template-columns:1fr 1.15fr}.slide .rbars{columns:2;column-gap:26px}
.slide .rbars .grp:first-child .rg{margin-top:0}
.slide .rbars .rb{grid-template-columns:minmax(0,9.4em) minmax(40px,1fr) auto;gap:8px}
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


def lact_bar(groups) -> str:
    total = sum(n for _, n in groups) or 1
    colours = ["var(--l1)", "var(--l2)", "var(--l3)", "var(--bar)"]
    x, parts = 0.0, []
    for (label, n), col in zip(groups, colours):
        w = 260 * n / total
        parts.append(f'<rect x="{x:.1f}" y="10" width="{max(w - 2, 0):.1f}" height="20" rx="3" fill="{col}">'
                     f'<title>{esc(label)}: {n}</title></rect>')
        x += w
    return f'<svg viewBox="0 0 260 40" width="100%" height="40" role="img" aria-label="lactations">{"".join(parts)}</svg>'


def spark(series, width=260, height=40) -> str:
    vals = [v for _, v in series if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    hi = hi if hi > lo else lo + 1
    n = len(series)
    pts = " ".join(f"{i / (n - 1) * width:.1f},{height - 4 - (v - lo) / (hi - lo) * (height - 8):.1f}"
                   for i, (_, v) in enumerate(series) if v is not None)
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" preserveAspectRatio="none" role="img" '
            f'aria-label="daily, {lo:.1f} to {hi:.1f}"><polyline points="{pts}" fill="none" stroke="var(--mark)" '
            f'stroke-width="1.6"/></svg>')


def _week_avg(series):
    out = []
    for i in range(len(series)):
        span = [v for _, v in series[max(0, i - 6):i + 1] if v is not None]
        out.append((series[i][0], sum(span) / len(span) if span else None))
    return out


def time_chart(rows, change: date | None, start: date, end: date, width=760) -> str:
    """rows: [(title, unit, [(label, style, series)])] stacked panels on one date axis; series [(date, value)]."""
    pad_l, pad_r, panel_h, gap = 46, 120, 120, 34
    height = len(rows) * (panel_h + gap) + 28
    span = max((end - start).days, 1)
    x = lambda d: pad_l + (d - start).days / span * (width - pad_l - pad_r)
    out = [f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" aria-label="by day, {start} to {end}">']
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
    return "".join(out)


FEED_TYPES = (   # (type, words in the feed's name); the first match wins, so silage counts as forage
    ("Forages", "forage", r"silage|haylage|\bhay\b|straw|alfalfa|lucerne|pasture|grass|baleage|green ?chop|forage"),
    ("Minerals and additives", "mineral", r"mineral|premix|vitamin|\bsalt\b|buffer|bicarb|limestone|rumensin|"
     r"monensin|yeast|additive|binder|magnesium|mag ox|selenium|\bvit\b|\bmix\b"),
    ("Fats", "fat", r"\bfat\b|tallow|bypass|megalac|\boil\b|calcium salts|energizer"),
    ("By-products", "byproduct", r"hull|cottonseed|pulp|\bbran\b|middlings|midds|by-?product|screenings|cannery|peel"),
    ("Proteins", "protein", r"canola|\bsoy|distillers|ddgs|gluten|\bmeal\b|blood|fish|urea|amino|protein"),
    ("Grains and energy", "grain", r"corn|maize|barley|wheat|sorghum|milo|\boats?\b|hominy|bakery|molasses|grain|"
     r"starch|flake"),
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
            out.append(f"<div class='rb'><span class='nm' title='{esc(k)}'>{esc(k)}</span><div class='tr'>{bar}</div>"
                       f"<span class='lb'>{label} <small>lb</small></span></div>")
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
    cows = [c for c in herd.in_herd() if c["pen"] == pen]
    milking = [c for c in cows if herd.status(c) == "milking"]
    end = herd.as_of
    start = end - timedelta(days=days - 1)
    feed = None
    if herd.feed:
        try:
            rows = feeding.pen_feed(herd, days=7, pen=pen)["pens"]
            feed = rows[0] if rows else None
        except SystemExit:
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
    tiles = [
        ("Milk per cow, last test", f"{t['milk_mean_lb']:.1f} lb" if t["milk_mean_lb"] else "n/a",
         f"ECM {t['ecm_mean_lb']:.1f} lb" if t["ecm_mean_lb"] else "",
         violin(milk_vals, "milk at the last test", " lb"),
         f"Middle 80%: {quantile(milk_vals, .1):.0f}–{quantile(milk_vals, .9):.0f} lb · {t['tested']} of {t['of']} cows"
         if milk_vals else "No tests"),
        ("Days in milk", f"{quantile(dim_vals, .5):.0f}" if dim_vals else "n/a", "median",
         violin(dim_vals, "days in milk"),
         f"Middle 80%: {quantile(dim_vals, .1):.0f}–{quantile(dim_vals, .9):.0f} days" if dim_vals else ""),
        ("Lactation", f"{median_lact:.0f}" if median_lact else "n/a", "median", lact_bar(lact),
         " · ".join(f"{l} {n}" for l, n in lact)),
        ("Intake, last 7 days", f"{feed['dmi_lb_per_cow']:.1f} lb" if feed and feed.get("dmi_lb_per_cow") else "n/a",
         "DM per cow", spark(intake_series[-30:]), "Daily, the last 30 days" if intake_series else "No EZfeed records"),
    ]
    tile_html = "".join(f'<div class="tile"><div class="k">{esc(k)}</div><div class="v">{esc(v)}<small>{esc(s)}</small>'
                        f'</div>{chart}<div class="n">{esc(n)}</div></div>' for k, v, s, chart, n in tiles)
    # Charts: ECM per cow by day (this fall, and the same days last fall), intake per cow by day.
    changes = _recipe_changes(herd, feed["ezfeed_pen"]) if feed else []
    change = changes[-1][0] if changes else None
    rows = []
    if pen_milk:
        def ecm_series(year_shift):
            out = []
            d = start
            while d <= end:
                src = _shift_years(d, year_shift)
                v = pen_milk.get((pen, src))
                e = ecm_lb(v["milk_lb"], v["fat_pct"], v["protein_pct"]) if v and v.get("fat_pct") else None
                out.append((d, e))
                d += timedelta(days=1)
            return out
        this, last = ecm_series(0), ecm_series(-1)
        rows.append(("ECM, lb per cow", "lb", [("this fall", "thin", this), ("this fall", "bold", _week_avg(this)),
                                              ("last fall", "dashed", _week_avg(last))]))
    if intake_series and not slide:
        rows.append(("Intake, lb of dry matter per cow", "lb", [("fed", "bold", intake_series)]))
    # A slide draws the chart narrower, so its words come out bigger.
    chart = (time_chart(rows, change, start, end, width=560 if slide else 760) if rows
             else "<p>No daily records for this pen.</p>")
    # Side: the current ration as bars, and the season beside the last change.
    side = []
    ecm_since = ""
    if feed:   # the pen's current ration; the chart marks when it last changed
        recipe = _recipe(herd, feed["ezfeed_pen"], end - timedelta(days=6), end)
        if recipe:
            side.append(f"<h2>Ration, last 7 days</h2><div class='sub'>lb of dry matter per cow, called for</div>"
                        f"<div class='rbars'>{ration_bars(recipe)}</div>")
    if pen_milk and change:
        def wk(year_shift, a, b):
            vals = []
            dd = a
            while dd <= b:
                v = pen_milk.get((pen, _shift_years(dd, year_shift)))
                if v and v.get("fat_pct"):
                    vals.append(ecm_lb(v["milk_lb"], v["fat_pct"], v["protein_pct"]))
                dd += timedelta(days=1)
            return mean(vals)
        before = (change - timedelta(days=7), change - timedelta(days=1))
        after = (end - timedelta(days=6), end)
        now = wk(0, *after) - wk(0, *before) if wk(0, *after) and wk(0, *before) else None
        then = wk(-1, *after) - wk(-1, *before) if wk(-1, *after) and wk(-1, *before) else None
        if now is not None and then is not None:
            note = f"The week before against the week to {_fmt_date(end)}, per cow"
            if slide:   # the slide's point, as big figures under the chart
                ecm_since = (f"<h2>ECM since {_fmt_date(change)}</h2><div class='figs'>"
                             f"<div><div class='k'>This fall</div><div class='v'>{now:+.1f} lb</div></div>"
                             f"<div><div class='k'>Last fall, no change</div><div class='v'>{then:+.1f} lb</div></div>"
                             f"<div><div class='k'>Left for the ration</div><div class='v'>{now - then:+.1f} lb</div>"
                             f"</div></div><div class='sub'>{note}</div>")
            else:
                side.append(f"<h2>ECM since {_fmt_date(change)}</h2><div class='chips'>"
                            f"{chip('This fall', f'{now:+.1f} lb')}{chip('Last fall, no change', f'{then:+.1f} lb')}"
                            f"</div><div class='sub'>{note}</div>")
    # Feed and health go under the charts, so both columns end together; a slide has only the ECM figures there.
    below = [ecm_since] if ecm_since else []
    if pc["health"] and not slide:
        below.append(f"<h2>Health, last {pc['days']} days</h2><div class='chips'>" + "".join(
            chip(h["event"].capitalize(), f"{h['cows']} cow{'s' if h['cows'] != 1 else ''}") for h in pc["health"])
            + "</div><div class='sub'>Cows in the pen now</div>")
    if feed and feed.get("ecm_per_lb_dm") and not slide:
        efficiency = format(feed["ecm_per_lb_dm"], ".2f")
        per_cow = "$" + format(feed["feed_cost_per_cow"], ".2f") if feed.get("feed_cost_per_cow") is not None else "n/a"
        per_cwt = "$" + format(feed["feed_cost_per_cwt"], ".2f") if feed.get("feed_cost_per_cwt") else "n/a"
        figures = (("ECM per lb DM", efficiency), ("Feed per cow", per_cow), ("Feed per cwt", per_cwt))
        below.insert(0, "<h2>Feed, last 7 days</h2><div class='figs'>" + "".join(
            f"<div><div class='k'>{esc(k)}</div><div class='v'>{esc(v)}</div></div>" for k, v in figures)
            + "</div><div class='sub'>Delivered feed, per cow in the pen</div>")
    below_html = ("<div class='below'>" + "".join(f"<div class='side'>{b}</div>" for b in below) + "</div>") if below else ""
    kinds = {f["kind"] for f in herd.files}
    sources = ["DairyComp's cow, test and event reports" if "events" in kinds else "DairyComp's cow report"]
    if "feed" in kinds:
        sources.append("EZfeed's intake and pen summary reports")
    if "pen_milk" in kinds:
        sources.append("pen milk by day")
    files = ", ".join(sources)
    kind = {"milking": "Milking cows", "dry": "Dry cows", "heifer": "Heifers"}.get(pc["summary"]["kind"], "Mixed")
    return (f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>Pen {esc(pen)}</title><style>{CSS}</style></head>"
            f"<body{' class=slide' if slide else ''}><div class='card'><div class='head'><h1>Pen {esc(pen)}</h1><span>{len(cows)} cows · {kind} · "
            f"{_fmt_date(start)} to {_fmt_date(end)}</span></div><div class='tiles'>{tile_html}</div>"
            f"<div class='body'><div class='left'>{chart}{below_html}</div><div class='side'>{''.join(side) or '<p>No changes recorded.</p>'}"
            f"</div></div><div class='foot'>From {esc(files) if not slide else 'DairyComp and EZfeed'}. Records end {end:%b %d, %Y}. ECM = 0.327 × milk + "
            f"12.95 × fat lb + 7.65 × protein lb, worked out here. Intake is delivered, per DairyComp head.</div></div>"
            f"</body></html>")
