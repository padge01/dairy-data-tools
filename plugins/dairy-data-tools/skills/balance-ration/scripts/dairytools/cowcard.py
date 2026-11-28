"""The cow card: the medium milking-cow card's layout (her number and status, her milk and days in milk, her place in
the pen, her lactation as a line from calved to due, three tiles, her newest events), as a self-contained HTML page in
the kit's look. No remarks (free text typed on the farm), no DairyComp-calculated figures."""

from __future__ import annotations

from datetime import date, timedelta

from . import explorer
from .cards import CSS, esc, violin
from .herd import Herd
from .stats import ecm_lb, quantile

COW_CSS = """
:root{--teal:#2f7f7a;--teal-t:rgba(47,127,122,.13);--rust:#b5532f;--rust-t:rgba(181,83,47,.12);--amber:#a7841f;
--amber-t:rgba(201,169,58,.18);--blue:#3f6fa3;--blue-t:rgba(63,111,163,.12);--slate-t:rgba(110,116,110,.14)}
@media (prefers-color-scheme:dark){:root{--teal:#6cc0b8;--teal-t:rgba(108,192,184,.16);--rust:#e5916f;
--rust-t:rgba(229,145,111,.16);--amber:#e6cf7a;--amber-t:rgba(230,207,122,.16);--blue:#8fb3dc;--blue-t:rgba(143,179,220,.16);
--slate-t:rgba(170,179,173,.14)}}
.pill.teal{background:var(--teal-t)}.pill.teal i{background:var(--teal)}.pill.amber{background:var(--amber-t)}
.pill.amber i{background:var(--amber)}.pill.blue{background:var(--blue-t)}.pill.blue i{background:var(--blue)}
.pill.rust{background:var(--rust-t)}.pill.rust i{background:var(--rust)}.pill.slate{background:var(--slate-t)}
.ctile.amber{background:var(--amber-t)}.ctile.blue{background:var(--blue-t)}.ctile.teal{background:var(--teal-t)}
.ev i{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:7px;background:var(--line)}
.ev i.repro{background:var(--teal)}.ev i.health{background:var(--rust)}
.curve{margin:8px 0 2px}
.curve-wrap{position:relative;padding-top:22px;margin-top:-18px}
.curve-wrap svg{display:block}
.violin-pad{padding:0 2%}
.spread-ptr{display:block;margin-top:-1px}
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
.strip-head{display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap;margin:10px 0 2px}
.strip-head .cap{margin:0}
.strip-key{display:inline-flex;align-items:center;gap:9px;flex-wrap:wrap;font-size:11px;color:var(--text3)}
.strip-key span{display:inline-flex;align-items:center;gap:4px}
.strip-key i{display:inline-block;width:7px;height:7px;border-radius:50%}
.strip-key i.health{background:var(--rust)}.strip-key i.repro{background:var(--teal)}.strip-key i.open{background:var(--amber)}
.strip-key i.care{background:var(--blue)}.strip-key i.plan{background:var(--surface);border:1.5px solid var(--teal);box-sizing:border-box}
.strip-key i.tick{width:2px;height:9px;border-radius:1px;background:var(--text3)}
.strip-scroll{overflow-x:auto;-webkit-overflow-scrolling:touch;padding:24px 0 2px;margin:-20px 0 0;scrollbar-width:thin}
.strip-inner{position:relative;min-width:100%}
.strip-inner svg{display:block;width:100%;height:76px}
.mark-hit,.pt-hit{position:absolute;transform:translate(-50%,-50%);cursor:pointer;outline:none;border-radius:999px;background:transparent}
.mark-hit{top:38px;width:18px;height:26px}
.pt-hit{width:18px;height:18px}
.mark-hit::after,.pt-hit::after{content:"";position:absolute;left:50%;top:50%;width:14px;height:14px;border-radius:50%;
transform:translate(-50%,-50%) scale(.7);border:2px solid var(--ink);opacity:0;transition:opacity .12s,transform .12s;pointer-events:none}
.mark-hit:hover::after,.mark-hit:focus::after,.pt-hit:hover::after,.pt-hit:focus::after{opacity:.35;transform:translate(-50%,-50%) scale(1)}
.mark-tip{position:absolute;bottom:calc(100% + 4px);left:50%;transform:translateX(-50%);background:var(--ink);color:var(--surface);
font-size:11px;font-weight:500;line-height:1.25;padding:3px 7px;border-radius:6px;white-space:nowrap;
box-shadow:0 2px 8px rgba(0,0,0,.18);opacity:0;pointer-events:none;transition:opacity .12s;z-index:20}
.mark-hit.left .mark-tip,.pt-hit.left .mark-tip{left:-4px;transform:none}
.mark-hit.right .mark-tip,.pt-hit.right .mark-tip{left:auto;right:-4px;transform:none}
.mark-hit:hover .mark-tip,.mark-hit:focus .mark-tip,.pt-hit:hover .mark-tip,.pt-hit:focus .mark-tip{opacity:1}
.strip-empty{font-size:12.5px;color:var(--text2);margin:10px 0 6px;padding:7px 10px;border-radius:9px;background:var(--raised)}
.ctiles{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin:10px 0}
.ctile{background:var(--raised);border-radius:9px;padding:5px 9px}.ctile .ck{display:block}.ctile .cv{font-size:15px}
.evs:not(:empty){min-height:112px}.ev{display:grid;grid-template-columns:56px 1fr auto;align-items:baseline;gap:8px;font-size:13.5px;padding:4px 0;
border-bottom:1px solid var(--subtle)}.ev b{font-weight:650}.ev span{color:var(--text2)}.ev .evdim{font-size:11.5px;color:var(--text3);font-variant-numeric:tabular-nums}
.more-evs{margin-top:4px}
.more-evs summary{list-style:none;cursor:pointer;font-size:12.5px;font-weight:500;color:var(--text2);text-align:right;padding:4px 0;user-select:none}
.more-evs summary::-webkit-details-marker{display:none}
.more-evs summary:hover{color:var(--text)}
.more-evs summary::after{content:" ▾";font-size:11px}
.more-evs[open] summary::after{content:" ▴"}
.more-evs .more-list{max-height:240px;overflow-y:auto;padding-right:2px}
"""

BREEDS = {"H": "Holstein", "J": "Jersey", "X": "Crossbred", "B": "Brown Swiss", "G": "Guernsey", "A": "Ayrshire"}
EVENT_WORDS = {
    "calving": "Calved", "breeding": "Bred", "preg_positive": "Checked pregnant",
    "preg_negative": "Checked open", "dry_off": "Dried off", "pen_move": "Moved",
    "clinical_mastitis": "Clinical mastitis", "do_not_breed": "Do not breed", "to_close_up": "To close-up",
    "ill_unspecified": "Sick", "lameness": "Lame", "metritis": "Metritis", "ketosis": "Ketosis",
    "retained_placenta": "Retained placenta", "displaced_abomasum": "Displaced abomasum",
    "milk_fever": "Milk fever", "abortion": "Aborted", "recovered": "Recovered",
    "hoof_trim": "Hoof trim", "milk_culture": "Milk culture", "vaccination": "Vaccinated",
    "treatment": "Treated", "note": "Note", "cleared": "Cleared",
}
SHORT_WORDS = {
    "calving": "Calved", "breeding": "Bred", "preg_positive": "Preg", "preg_negative": "Open",
    "dry_off": "Dry off", "pen_move": "Moved", "clinical_mastitis": "Mastitis", "do_not_breed": "DNB",
    "to_close_up": "Close-up", "ill_unspecified": "Sick", "lameness": "Lame", "metritis": "Metritis",
    "ketosis": "Ketosis", "retained_placenta": "RP", "displaced_abomasum": "DA", "milk_fever": "Milk fever",
    "abortion": "Aborted", "recovered": "Recovered", "hoof_trim": "Hoof trim", "milk_culture": "Culture",
    "vaccination": "Vax", "treatment": "Treated", "note": "Note", "cleared": "OK",
}


def ordinal(n) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _event_tone(meaning: str | None, category: str | None) -> tuple[str, int]:
    """Visual group and priority (lower = more important) for a lactation-timeline event mark."""
    if category == "health" or meaning in ("abortion", "do_not_breed"):
        return "health", 1
    if meaning == "preg_positive":
        return "repro", 2
    if meaning == "breeding":
        return "repro", 3
    if meaning == "preg_negative":
        return "open", 4
    if meaning == "dry_off":
        return "repro", 4
    if meaning in ("recovered", "treatment", "hoof_trim", "milk_culture") or category == "procedure":
        return "care", 5
    if meaning == "pen_move" or category == "movement":
        return "tick", 6
    return "tick", 7


def _event_short(e: dict) -> str:
    m = e.get("std_event") or e.get("meaning")
    raw = e.get("dc_event") or e.get("event") or ""
    return SHORT_WORDS.get(m) or (m or raw).replace("_", " ").capitalize() or "Event"


def _event_long(e: dict) -> str:
    m = e.get("std_event") or e.get("meaning")
    raw = e.get("dc_event") or e.get("event") or ""
    return EVENT_WORDS.get(m) or (m or raw).replace("_", " ").capitalize() or "Event"


def strip(steps, today: date, events=(), fresh: date | None = None, width: int = 400) -> str:
    """Her lactation as a line from calved to today (or due), marking every event in between."""
    if not steps:
        return ""
    # Group intermediate lactation events by date so same-day events share a single clean mark.
    by_day: dict[date, list[dict]] = {}
    bred_dates: list[date] = []
    for e in events:
        d = e.get("event_date")
        if d is None:
            continue
        m = e.get("std_event")
        if m == "calving" and fresh and d == fresh:
            continue
        if m == "breeding":
            bred_dates.append(d)
        by_day.setdefault(d, []).append(e)

    # A bare 2-point line (only Calved -> Today) with no events or future milestones adds no signal.
    has_future = any(kind == "future" for _, _, kind in steps)
    if not by_day and not has_future and len(steps) <= 2:
        if fresh:
            return f"<div class='strip-empty'>Calved {fresh:%b} {fresh.day} · no events recorded since calving</div>"
        return ""

    all_dates = [s[1] for s in steps] + list(by_day.keys())
    first, last = min(all_dates), max(all_dates)
    span = max((last - first).days, 1)
    now = min(max(today, first), last)

    # Expand horizontally into a scrollable strip when many events crowd into a compressed past segment.
    past_frac = (now - first).days / span
    svg_w = width
    if len(by_day) >= 5 and past_frac < 0.45:
        svg_w = max(560, min(720, round(width * 0.46 / max(past_frac, 0.22))))
    elif len(by_day) >= 12:
        svg_w = max(560, min(720, len(by_day) * 44))
    scrollable = svg_w > width

    def x(d: date) -> float:
        return 14 + (d - first).days / span * (svg_w - 28)

    anchor_dates = {d for _, d, _ in steps}
    last_bred = max(bred_dates) if bred_dates else None
    bred_count = len(bred_dates)

    # Build day marks sorted chronologically.
    marks = []
    seen_tones: set[str] = set()
    for d in sorted(by_day):
        day_evs = by_day[d]
        scored = sorted(day_evs, key=lambda ev: _event_tone(ev.get("std_event"), ev.get("category"))[1])
        lead = scored[0]
        tone, prio = _event_tone(lead.get("std_event"), lead.get("category"))
        seen_tones.add(tone)
        short = _event_short(lead)
        if lead.get("std_event") == "breeding" and d == last_bred and bred_count > 1:
            short = f"Bred ×{bred_count}"
        dim_txt = f" · {(d - fresh).days} DIM" if fresh else ""
        names = ", ".join(dict.fromkeys(_event_long(ev) for ev in scored))
        tip = f"{d:%b} {d.day}{dim_txt} · {names}"
        marks.append({"date": d, "x": x(d), "tone": tone, "prio": prio, "short": short, "tip": tip,
                      "is_anchor": d in anchor_dates})
    if has_future:
        seen_tones.add("plan")

    legend_bits = []
    for key, text in (("health", "Health"), ("repro", "Repro"), ("open", "Open"),
                      ("care", "Care"), ("tick", "Move / note"), ("plan", "Planned")):
        if key in seen_tones:
            legend_bits.append(f"<span><i class='{key}'></i>{text}</span>")
    if scrollable:
        legend_bits.append("<span>↔ Scroll</span>")
    head = (f"<div class='strip-head'><span class='cap'>This lactation</span>"
            f"{'<span class=\"strip-key\">' + ''.join(legend_bits) + '</span>' if legend_bits else ''}</div>")

    label_parts = [f"{w} {d:%b} {d.day}" for w, d, _ in steps]
    label_parts += [m["tip"] for m in marks[:6]]
    inner_style = f"width:{svg_w}px" if scrollable else "width:100%"
    out = [head,
           f"<div class='strip-scroll'><div class='strip-inner' style='{inner_style}'>",
           f'<svg viewBox="0 0 {svg_w} 76" width="{svg_w}" height="76" role="img" aria-label="her lactation: {esc("; ".join(label_parts))}">',
           f'<line x1="{x(first):.1f}" x2="{x(now):.1f}" y1="38" y2="38" stroke="var(--ink)" stroke-width="2.5" stroke-linecap="round"/>']
    if last > now:
        out.append(f'<line x1="{x(now):.1f}" x2="{x(last):.1f}" y1="38" y2="38" stroke="var(--bar)" '
                   f'stroke-width="2.5" stroke-dasharray="4 3" stroke-linecap="round"/>')

    # Draw intermediate event marks (ticks first, then colored dots so health/repro stay on top).
    tone_color = {"health": "var(--rust)", "repro": "var(--teal)", "open": "var(--amber)",
                  "care": "var(--blue)", "tick": "var(--text3)"}
    hits: list[tuple[float, str]] = []
    for m in sorted(marks, key=lambda item: -item["prio"]):
        if m["is_anchor"]:
            continue
        cx = m["x"]
        hits.append((cx, m["tip"]))
        if m["tone"] == "tick":
            out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="33.5" y2="42.5" stroke="var(--text3)" '
                       f'stroke-width="1.8" stroke-linecap="round"/>')
        else:
            r = 4.6 if m["tone"] in ("health", "repro", "open") else 3.8
            col = tone_color[m["tone"]]
            out.append(f'<circle cx="{cx:.1f}" cy="38" r="{r}" fill="{col}" stroke="var(--surface)" stroke-width="1.6"/>')

    # Draw milestone anchors and place their labels first.
    placed_top: list[float] = []
    placed_bot: list[float] = []
    for i, (what, d, kind) in enumerate(steps):
        cx = x(d)
        r = 7 if kind in ("today", "left") else 5.8
        if kind == "today":
            fill, stroke = "var(--ink)", "var(--ink)"
        elif kind == "left":
            fill, stroke = "var(--rust)", "var(--rust)"
        elif kind == "future":
            fill, stroke = "var(--surface)", "var(--teal)"
        else:
            fill, stroke = "var(--teal)", "var(--teal)"
        dim_txt = f" · {(d - fresh).days} DIM" if fresh and d >= fresh else ""
        extra_day = by_day.get(d, [])
        extra_txt = " · " + ", ".join(dict.fromkeys(_event_long(ev) for ev in extra_day)) if extra_day else ""
        hits.append((cx, f"{what} · {d:%b} {d.day}{dim_txt}{extra_txt}"))
        out.append(f'<circle cx="{cx:.1f}" cy="38" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        anchor = "start" if cx < 30 else "end" if cx > svg_w - 30 else "middle"
        crowded = any(abs(cx - p) < 46 for p in placed_top)
        weight = "650" if kind in ("today", "left") else "500"
        if not crowded:
            placed_top.append(cx)
            out.append(f'<text x="{cx:.1f}" y="15" font-size="11.5" text-anchor="{anchor}" '
                       f'class="lab" font-weight="{weight}">{esc(what)}</text>')
            if not any(abs(cx - p) < 44 for p in placed_bot):
                placed_bot.append(cx)
                out.append(f'<text x="{cx:.1f}" y="63" font-size="11" text-anchor="{anchor}">{d:%b} {d.day}</text>')
        elif not any(abs(cx - p) < 46 for p in placed_bot):
            placed_bot.append(cx)
            out.append(f'<text x="{cx:.1f}" y="68" font-size="11" text-anchor="{anchor}" '
                       f'class="lab" font-weight="{weight}">{esc(what)}</text>')

    # Place labels for highest-priority intermediate events wherever there is clean breathing room.
    for m in sorted(marks, key=lambda item: (item["prio"], item["date"])):
        if m["is_anchor"] or m["prio"] >= 7:
            continue
        cx = m["x"]
        if cx < 34 or cx > svg_w - 34:
            continue
        if any(abs(cx - p) < 52 for p in placed_top):
            continue
        placed_top.append(cx)
        col = tone_color[m["tone"]] if m["tone"] in ("health", "repro", "open") else "var(--text)"
        out.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="20" y2="31" stroke="var(--subtle)" stroke-width="1"/>')
        out.append(f'<text x="{cx:.1f}" y="15" font-size="11" text-anchor="middle" '
                   f'style="fill:{col}" font-weight="600">{esc(m["short"])}</text>')
        if not any(abs(cx - p) < 46 for p in placed_bot):
            placed_bot.append(cx)
            out.append(f'<text x="{cx:.1f}" y="63" font-size="10.5" text-anchor="middle">{m["date"]:%b} {m["date"].day}</text>')

    out.append("</svg>")
    # Pure-CSS hover & tap tooltips aligned directly over each dot/tick (zero JS).
    for cx, tip in hits:
        pct = cx / svg_w * 100
        edge = " left" if pct < 22 else " right" if pct > 78 else ""
        out.append(f"<span class='mark-hit{edge}' tabindex='0' style='left:{pct:.2f}%' aria-label='{esc(tip)}'>"
                   f"<span class='mark-tip'>{esc(tip)}</span></span>")
    out.append("</div></div>")
    return "".join(out)


def milk_curve(points, dim_now, kind: str, width=400, height=132) -> str:
    """Her milk this lactation by days in milk: daily weights as a line, tests as dots joined by a line."""
    pts = sorted((p["dim"], p["lb"]) for p in points if p["dim"] is not None and 0 <= p["dim"] <= (dim_now or 9999))
    if len(pts) < 2:
        return ""
    pad_l, pad_r, top, bottom = 30, 36, 10, 20
    xmax = max(100, max(d for d, _ in pts) + 5)
    ymax = max(50, -(-max(v for _, v in pts) * 1.1 // 25) * 25)
    x = lambda d: pad_l + d / xmax * (width - pad_l - pad_r)
    y = lambda v: top + (height - top - bottom) * (1 - v / ymax)
    line = " ".join(f"{x(d):.1f},{y(v):.1f}" for d, v in pts)
    out = [f"<div class='curve-wrap'><svg viewBox='0 0 {width} {height}' width='100%' role='img' aria-label='her milk this lactation'>"]
    v = 0
    while v <= ymax:
        out.append(f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{y(v):.1f}" y2="{y(v):.1f}" stroke="var(--subtle)"/>'
                   f'<text x="{pad_l - 5}" y="{y(v) + 4:.1f}" font-size="10.5" text-anchor="end">{v:.0f}</text>')
        v += 50 if ymax > 100 else 25
    out.append(f'<polygon points="{x(pts[0][0]):.1f},{y(0):.1f} {line} {x(pts[-1][0]):.1f},{y(0):.1f}" '
               f'fill="var(--blue-t)"/><polyline points="{line}" fill="none" stroke="var(--blue)" stroke-width="2.2" '
               f'stroke-linejoin="round"/>')
    if kind == "test":
        out += [f'<circle cx="{x(d):.1f}" cy="{y(v):.1f}" r="3.5" fill="var(--surface)" stroke="var(--blue)" '
                f'stroke-width="2"/>' for d, v in pts]
    d, v = pts[-1]
    out.append(f'<text x="{x(d) + 6:.1f}" y="{y(v) + 4:.1f}" font-size="12" class="lab"><tspan font-weight="650">'
               f'{v:.0f}</tspan> lb</text>')
    for t in range(0, int(xmax) + 1, 100):
        out.append(f'<text x="{x(t):.1f}" y="{height - 5}" font-size="10.5" text-anchor="middle">{t}</text>')
    out.append("</svg>")
    # Pure-CSS hover & tap tooltips on milk-curve points (sample up to ~20 points for daily weights).
    step = max(1, len(pts) // 20) if kind != "test" else 1
    shown = pts[::step]
    if pts[-1] not in shown:
        shown.append(pts[-1])
    for d, v in shown:
        xp = x(d) / width * 100
        yf = y(v) / height
        edge = " left" if xp < 22 else " right" if xp > 78 else ""
        tip = f"{d} DIM · {v:.0f} lb"
        out.append(f"<span class='pt-hit{edge}' tabindex='0' style='left:{xp:.2f}%;top:calc(22px + (100% - 22px) * {yf:.4f})' "
                   f"aria-label='{esc(tip)}'><span class='mark-tip'>{esc(tip)}</span></span>")
    out.append("</div>")
    return "".join(out)


def cow_card_html(herd: Herd, cow, gestation: int = 280) -> str:
    rec = explorer.cow_record(herd, cow)
    me = herd.cow_by_animal[rec["animal_id"]]
    status = herd.status(me)
    today = herd.as_of
    fresh, conceived = me.get("fresh_date"), me.get("conception_date")
    repro = (me.get("repro_status") or "").upper()
    pregnant = repro in ("PREG", "DRY") and conceived is not None
    if status == "left":
        pill, tone = "Left the herd", "rust"
    elif status == "dry":
        pill, tone = "Dry", "slate"
    elif pregnant:
        pill, tone = f"Pregnant {(today - conceived).days} d", "teal"
    else:
        pill = {"BRED": "Bred", "OPEN": "Open", "FRESH": "Fresh", "NO BRED": "Do not breed", "PREG": "Pregnant",
                "OK/OPEN": "Open"}.get(repro, repro.title() or "In milk")
        tone = {"BRED": "amber", "OPEN": "amber", "OK/OPEN": "amber", "FRESH": "blue", "NO BRED": "rust",
                "PREG": "teal"}.get(repro, "slate")
    lact = me.get("lactation")
    parts = [f"Pen {me['pen']}" if me.get("pen") and me["pen"] != "No pen" else "",
             BREEDS.get((me.get("breed") or "").upper(), me.get("breed") or ""),
             f"{ordinal(lact)} lact" if lact else "heifer"]
    sub = " · ".join(p for p in parts if p)

    daily = me.get("daily_milk") or 0
    milk = daily if daily > 0 else me.get("test_milk")
    milk_what = "lb a day" if daily > 0 else f"lb, {herd.milk_words}"
    pen_milk = [c["test_milk"] for c in herd.cows_by_pen.get(me.get("pen"), ()) if herd.status(c) == "milking"
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
        med = quantile(sorted(pen_milk), 0.5)
        pct = (me["test_milk"] - lo) / ((hi - lo) or 1)
        xm = 8 + pct * (400 - 16)
        anchor = "start" if xm < 56 else "end" if xm > 344 else "middle"
        lx = max(3, xm - 5.5) if anchor == "start" else min(397, xm + 5.5) if anchor == "end" else xm
        spread = (f"<div class='cap'>Her milk against pen {esc(me['pen'])}, {herd.milk_words} (lb)</div>"
                  f"<div class='violin-pad'>{violin(pen_milk, 'pen milk', ' lb', width=400, height=40)}</div>"
                  f"<svg class='spread-ptr' viewBox='0 0 400 26' width='100%' height='26' aria-hidden='true'>"
                  f"<polygon points='{xm - 5.5:.1f},10 {xm + 5.5:.1f},10 {xm:.1f},2' fill='var(--ink)'/>"
                  f"<text x='{lx:.1f}' y='23' font-size='11' font-weight='650' text-anchor='{anchor}' "
                  f"style='fill:var(--ink)'>Her {me['test_milk']:.0f} lb</text></svg>"
                  f"<div class='sub'>Lowest {lo:.0f} · pen median {med:.0f} · highest {hi:.0f}</div>")

    steps = []
    lact_events = []
    if fresh:
        lact_events = [e for e in herd.events_by_animal.get(me["animal_id"], ()) if e["event_date"] >= fresh]
        steps.append(("Calved", fresh, "past"))
        if me.get("left_date") and me["left_date"] >= fresh:
            steps.append(("Left", me["left_date"], "left"))
        else:
            steps.append(("Today", today, "today"))
            if pregnant:
                due = conceived + timedelta(days=gestation)
                if status != "dry":
                    steps.append(("Dry off", due - timedelta(days=60), "future"))
                steps.append(("Due", due, "future"))
        steps.sort(key=lambda s: s[1])

    tiles = []
    if me.get("prev_test_milk") and herd.milk_words == "last test":
        tiles.append(("Previous test", f"{me['prev_test_milk']:.0f} lb", "blue"))
    if me.get("test_fat_pct") and me.get("test_protein_pct"):
        tiles.append(("Fat · protein", f"{me['test_fat_pct']:.1f}% · {me['test_protein_pct']:.1f}%", "amber"))
    ecm = ecm_lb(me.get("test_milk"), me.get("test_fat_pct"), me.get("test_protein_pct"))
    if ecm:
        tiles.append(("ECM, last test", f"{ecm:.0f} lb", "blue"))
    if (me.get("test_scc") or 0) > 0 and len(tiles) < 3:
        tiles.append(("SCC", f"{me['test_scc']:.0f}k", "teal"))
    tiles_html = "".join(f"<div class='ctile {tone_}'><span class='ck'>{esc(k)}</span><span class='cv'>{esc(v)}</span>"
                         f"</div>" for k, v, tone_ in tiles[:3])

    # Her milk this lactation, from several snapshots: daily weights, or her tests.
    history = herd.milk_history.get(str(me["cow_id"]).strip(), [])
    dim_now = me.get("days_in_milk")
    for p in history:   # days in milk from her fresh date where the snapshot didn't carry them
        if p["dim"] is None and fresh:
            p["dim"] = (p["day"] - fresh).days
    this_lact = [p for p in history if (fresh is None or p["day"] >= fresh) and
                 (dim_now is None or p["dim"] is None or p["dim"] <= dim_now)]
    kind = "daily" if any(p["kind"] == "daily" for p in this_lact) else "test"
    curve = milk_curve([p for p in this_lact if p["kind"] == kind], dim_now, kind)
    curve_html = (f"<div class='cap'>Her milk this lactation, lb by days in milk "
                  f"({'each day' if kind == 'daily' else 'each test'})"
                  f"</div><div class='curve'>{curve}</div>" if curve else "")

    events = list(reversed(rec["events_this_lactation"]))
    def _ev_row(e: dict) -> str:
        d = date.fromisoformat(e["date"])
        words = EVENT_WORDS.get(e["meaning"]) or (e["meaning"] or e["event"] or "").replace("_", " ").capitalize()
        dot_cls = "health" if e.get("meaning") in ("abortion", "do_not_breed") else (e.get("category") or "")
        ev_dim = e.get("days_in_milk")
        if ev_dim is None and fresh:
            ev_dim = (d - fresh).days
        dim_cell = f"<span class='evdim'>{ev_dim} DIM</span>" if ev_dim is not None else "<span></span>"
        return (f"<div class='ev'><span>{d:%b} {d.day}</span><div><i class='{esc(dot_cls)}'>"
                f"</i><b>{esc(words)}</b></div>{dim_cell}</div>")

    rows = [_ev_row(e) for e in events[:4]]
    more = ""
    if len(events) > 4:
        rest = "".join(_ev_row(e) for e in events[4:])
        more = (f"<details class='more-evs'><summary>+{len(events) - 4} earlier this lactation</summary>"
                f"<div class='more-list'>{rest}</div></details>")

    dim = me.get("days_in_milk")
    dim_html = f"<div class='dim'>{dim}<small>DIM</small></div>" if dim is not None and status == "milking" else ""
    big = f"{milk:.0f}<small>{milk_what}</small>" if milk else "<small>No milk recorded</small>"
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>Cow {esc(me['cow_id'])}</title>"
            f"<style>{CSS}{COW_CSS}</style></head><body><div class='cow'>"
            f"<div class='nameline'><h1>Cow {esc(me['cow_id'])}</h1><span class='pill {tone}'><i></i>{esc(pill)}</span></div>"
            f"<div class='idsub'>{esc(sub)}</div><div class='figrow'><div class='big'>{big}</div>{dim_html}</div>"
            f"<div class='rank'>{rank}</div>{spread}{curve_html}{strip(steps, today, lact_events, fresh)}<div class='ctiles'>{tiles_html}</div>"
            f"<div class='evs'>{''.join(rows)}</div>{more}"
            f"<div class='foot'>From DairyComp's cow and event reports. Records end {today:%b %d, %Y}. "
            + ("Days in milk counted from her fresh date" if fresh else "Days in milk as DairyComp counts them (no fresh "
               "date in the export)")
            + ("; ECM and her place in the pen worked out here." if herd.milk_words == "last test" else
               "; her milk is her latest daily weight, her place in the pen worked out here.")
            + "</div></div></body></html>")
