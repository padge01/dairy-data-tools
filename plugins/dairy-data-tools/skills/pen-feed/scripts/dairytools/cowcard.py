"""The cow card: the medium milking-cow card's layout (her number and status, her milk and days in milk, her place in
the pen, her lactation as a line from calved to due, three tiles, her newest events), as a self-contained HTML page in
the kit's look. No remarks (free text typed on the farm), no DairyComp-calculated figures."""

from __future__ import annotations

from datetime import date, timedelta

from . import explorer
from .cards import CSS, esc, violin
from .herd import Herd
from .stats import ecm_lb

COW_CSS = """
.cow{max-width:440px;margin:24px auto;background:var(--surface);border:1px solid var(--border);border-radius:18px;
padding:18px 20px 14px}
.nameline{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.nameline h1{margin:0;font-size:26px;font-weight:700}
.pill{display:inline-flex;align-items:center;gap:6px;padding:2px 9px;border-radius:999px;background:var(--raised);
font-size:12.5px;font-weight:600}.pill i{width:8px;height:8px;border-radius:50%;background:var(--mark)}
.idsub{font-size:13.5px;color:var(--text2);margin-top:2px}
.figrow{display:flex;justify-content:space-between;align-items:baseline;margin-top:12px}
.big{font-size:48px;font-weight:700;line-height:1}.big small{font-size:16px;font-weight:400;color:var(--text2);margin-left:6px}
.dim{font-size:28px;font-weight:650}.dim small{font-size:14px;font-weight:600;margin-left:3px}
.rank{font-size:13.5px;color:var(--text2);margin:4px 0 10px}.rank b{color:var(--text)}
.cap{font-size:12.5px;color:var(--text2);margin:10px 0 2px}
.ctiles{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:10px 0}
.ctile{background:var(--raised);border-radius:9px;padding:5px 9px}.ctile .ck{display:block}.ctile .cv{font-size:15px}
.evs{min-height:112px}.ev{display:grid;grid-template-columns:56px 1fr;gap:8px;font-size:13.5px;padding:4px 0;
border-bottom:1px solid var(--subtle)}.ev b{font-weight:650}.ev span{color:var(--text2)}
.more{font-size:12.5px;color:var(--text3);text-align:right;margin-top:4px}
"""

BREEDS = {"H": "Holstein", "J": "Jersey", "X": "Crossbred", "B": "Brown Swiss", "G": "Guernsey", "A": "Ayrshire"}
EVENT_WORDS = {"calving": "Calved", "breeding": "Bred", "preg_positive": "Checked pregnant",
               "preg_negative": "Checked open", "dry_off": "Dried off", "pen_move": "Moved",
               "clinical_mastitis": "Clinical mastitis", "do_not_breed": "Do not breed", "to_close_up": "To close-up"}


def ordinal(n) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def strip(steps, today: date, width=400) -> str:
    """Her lactation as a line from calved to due, each step a labelled point; today the big dot."""
    if not steps:
        return ""
    first, last = steps[0][1], max(s[1] for s in steps)
    span = max((last - first).days, 1)

    def x(d):
        return 12 + (d - first).days / span * (width - 24)

    label = ", ".join(f"{w} {d:%b} {d.day}" for w, d, _ in steps)
    now = min(today, last)
    out = [f'<svg viewBox="0 0 {width} 70" width="100%" role="img" aria-label="her lactation: {esc(label)}">',
           f'<line x1="{x(first):.1f}" x2="{x(now):.1f}" y1="34" y2="34" stroke="var(--ink)" stroke-width="2.5"/>',
           f'<line x1="{x(now):.1f}" x2="{x(last):.1f}" y1="34" y2="34" stroke="var(--bar)" stroke-width="2.5"/>']
    placed = []
    for i, (what, d, kind) in enumerate(steps):
        cx = x(d)
        r = 8 if kind == "today" else 6
        fill = "var(--ink)" if kind == "today" else ("var(--mark)" if d <= today else "var(--surface)")
        out.append(f'<circle cx="{cx:.1f}" cy="34" r="{r}" fill="{fill}" stroke="var(--ink)" stroke-width="2"/>')
        anchor = "start" if i == 0 else "end" if i == len(steps) - 1 else "middle"
        crowded = any(abs(cx - p) < 46 for p in placed)
        placed.append(cx)
        weight = "650" if kind == "today" else "400"
        out.append(f'<text x="{cx:.1f}" y="{14 if not crowded else 66}" font-size="12.5" text-anchor="{anchor}" '
                   f'class="lab" font-weight="{weight}">{esc(what)}</text>')
        if not crowded:
            out.append(f'<text x="{cx:.1f}" y="60" font-size="12" text-anchor="{anchor}">{d:%b} {d.day}</text>')
    out.append("</svg>")
    return "".join(out)


def cow_card_html(herd: Herd, cow, gestation: int = 280) -> str:
    rec = explorer.cow_record(herd, cow)
    me = next(c for c in herd.cows if c["animal_id"] == rec["animal_id"])
    status = herd.status(me)
    today = herd.as_of
    fresh, conceived = me.get("fresh_date"), me.get("conception_date")
    repro = (me.get("repro_status") or "").upper()
    pregnant = repro in ("PREG", "DRY") and conceived is not None
    if status == "left":
        pill = "Left the herd"
    elif status == "dry":
        pill = "Dry"
    elif pregnant:
        pill = f"Pregnant {(today - conceived).days} d"
    else:
        pill = {"BRED": "Bred", "OPEN": "Open", "FRESH": "Fresh", "NO BRED": "Do not breed"}.get(repro,
                                                                                              repro.title() or "In milk")
    lact = me.get("lactation")
    parts = [f"Pen {me['pen']}" if me.get("pen") and me["pen"] != "No pen" else "",
             BREEDS.get((me.get("breed") or "").upper(), me.get("breed") or ""),
             f"{ordinal(lact)} lact" if lact else "heifer"]
    sub = " · ".join(p for p in parts if p)

    daily = me.get("daily_milk") or 0
    milk = daily if daily > 0 else me.get("test_milk")
    milk_what = "lb a day" if daily > 0 else f"lb, {herd.milk_words}"
    pen_milk = [c["test_milk"] for c in herd.in_herd() if c["pen"] == me.get("pen") and herd.status(c) == "milking"
                and (c.get("test_milk") or 0) > 0]
    rank = ""
    if me.get("test_milk") and len(pen_milk) >= 5:
        above = sum(1 for v in pen_milk if v > me["test_milk"])
        top = max(1, round(100 * (above + 1) / len(pen_milk)))
        below = sum(1 for v in pen_milk if v < me["test_milk"])
        place = f"Top {top}%" if top <= 50 else f"Bottom {max(1, round(100 * (below + 1) / len(pen_milk)))}%"
        rank = f"<b>{place}</b> of pen {esc(me['pen'])}, {herd.milk_words} ({len(pen_milk)} cows)"
    spread = ""
    if pen_milk and me.get("test_milk"):
        lo, hi = min(pen_milk), max(pen_milk)
        xm = 400 * (me["test_milk"] - lo) / ((hi - lo) or 1)
        spread = (f"<div class='cap'>Her milk against pen {esc(me['pen'])}, {herd.milk_words} (lb)</div>"
                  f"{violin(pen_milk, 'pen milk', ' lb', width=400, height=40)}"
                  f"<svg viewBox='0 0 400 16' width='100%' height='16' aria-hidden='true'>"
                  f"<polygon points='{xm - 6:.1f},14 {xm + 6:.1f},14 {xm:.1f},3' fill='var(--ink)'/></svg>"
                  f"<div class='sub'>Lowest {lo:.0f} · her {me['test_milk']:.0f} · highest {hi:.0f}</div>")

    steps = []
    if fresh:
        steps.append(("Calved", fresh, "past"))
        bred = sorted(e["event_date"] for e in herd.events if e["animal_id"] == me["animal_id"]
                      and e["std_event"] == "breeding" and e["event_date"] >= fresh)
        if bred:
            steps.append(("Bred" if len(bred) == 1 else f"Bred ×{len(bred)}", bred[-1], "past"))
        steps.append(("Today", today, "today"))
        if pregnant:
            due = conceived + timedelta(days=gestation)
            if status != "dry":
                steps.append(("Dry off", due - timedelta(days=60), "future"))
            steps.append(("Due", due, "future"))
        steps.sort(key=lambda s: s[1])

    tiles = []
    if me.get("prev_test_milk"):
        tiles.append(("Previous test", f"{me['prev_test_milk']:.0f} lb"))
    if me.get("test_fat_pct") and me.get("test_protein_pct"):
        tiles.append(("Fat · protein", f"{me['test_fat_pct']:.1f}% · {me['test_protein_pct']:.1f}%"))
    ecm = ecm_lb(me.get("test_milk"), me.get("test_fat_pct"), me.get("test_protein_pct"))
    if ecm:
        tiles.append(("ECM, last test", f"{ecm:.0f} lb"))
    if (me.get("test_scc") or 0) > 0 and len(tiles) < 3:
        tiles.append(("SCC", f"{me['test_scc']:.0f}k"))
    tiles_html = "".join(f"<div class='ctile'><span class='ck'>{esc(k)}</span><span class='cv'>{esc(v)}</span></div>"
                         for k, v in tiles[:3])

    events = list(reversed(rec["events_this_lactation"]))
    rows = []
    for e in events[:4]:
        d = date.fromisoformat(e["date"])
        words = EVENT_WORDS.get(e["meaning"]) or (e["meaning"] or e["event"] or "").replace("_", " ").capitalize()
        rows.append(f"<div class='ev'><span>{d:%b} {d.day}</span><div><b>{esc(words)}</b></div></div>")
    more = f"<div class='more'>+{len(events) - 4} earlier this lactation</div>" if len(events) > 4 else ""

    dim = me.get("days_in_milk")
    dim_html = f"<div class='dim'>{dim}<small>DIM</small></div>" if dim is not None and status == "milking" else ""
    big = f"{milk:.0f}<small>{milk_what}</small>" if milk else "<small>No milk recorded</small>"
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>Cow {esc(me['cow_id'])}</title>"
            f"<style>{CSS}{COW_CSS}</style></head><body><div class='cow'>"
            f"<div class='nameline'><h1>Cow {esc(me['cow_id'])}</h1><span class='pill'><i></i>{esc(pill)}</span></div>"
            f"<div class='idsub'>{esc(sub)}</div><div class='figrow'><div class='big'>{big}</div>{dim_html}</div>"
            f"<div class='rank'>{rank}</div>{spread}{strip(steps, today)}<div class='ctiles'>{tiles_html}</div>"
            f"<div class='evs'>{''.join(rows)}</div>{more}"
            f"<div class='foot'>From DairyComp's cow and event reports. Records end {today:%b %d, %Y}. Days in milk "
            "counted from her fresh date; ECM and her place in the pen worked out here.</div></div></body></html>")
