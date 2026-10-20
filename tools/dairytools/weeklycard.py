"""The pen-feed card and the weekly (visit) page, in the kit's card look: chips and labelled bars, record only, every
figure with its count; the farm against itself."""

from __future__ import annotations

from datetime import date

from . import feeding, weekly
from .cards import CSS, chip, esc
from .herd import Herd

PAGE_CSS = """
.page{max-width:1180px;margin:24px auto;background:var(--surface);border:1px solid var(--border);border-radius:22px;
padding:22px 30px 18px}
.sec{border-top:1px solid var(--subtle);padding:12px 0}.sec h2{font-size:17px;margin:0 0 8px;font-weight:650}
.sec .sub{margin-top:-4px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:22px}.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
.penrow{display:grid;grid-template-columns:120px 1fr;gap:12px;align-items:center;padding:8px 0;
border-bottom:1px solid var(--subtle)}.penrow:last-child{border:0}.penname{font-size:20px;font-weight:700}
.penname small{display:block;font-size:12.5px;font-weight:400;color:var(--text2)}
.delta{font-size:12px;color:var(--text2);margin-left:4px}
.act{display:grid;grid-template-columns:24px 1fr auto;gap:8px;align-items:start;padding:7px 0;
border-bottom:1px solid var(--subtle);font-size:14.5px}.box{width:16px;height:16px;border:1.5px solid var(--line);
border-radius:4px;margin-top:2px}.who{font-size:12.5px;color:var(--text2)}
@media (max-width:820px){.grid2,.grid3{grid-template-columns:1fr}.penrow{grid-template-columns:1fr}}
"""


def _page(title: str, head_sub: str, body: str, foot: str) -> str:
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{esc(title)}</title><style>{CSS}{PAGE_CSS}</style>"
            f"</head><body><div class='page'><div class='head'><h1>{esc(title)}</h1><span>{esc(head_sub)}</span></div>"
            f"{body}<div class='foot'>{esc(foot)}</div></div></body></html>")


def bars(rows, unit="", width=520, fmt="{:.2f}") -> str:
    """Horizontal bars, one per row (label, value), each with its value written at its end; no colour needed."""
    rows = [(l, v) for l, v in rows if v is not None]
    if not rows:
        return ""
    top = max(v for _, v in rows) or 1
    h = 26
    out = [f'<svg viewBox="0 0 {width} {h * len(rows) + 4}" width="{width}" style="max-width:100%" role="img" aria-label="'
           + esc("; ".join(f"{l} {fmt.format(v)}{unit}" for l, v in rows)) + '">']
    for i, (label, v) in enumerate(rows):
        y = i * h + 4
        w = (width - 190) * v / top
        out.append(f'<text x="0" y="{y + 15}" font-size="13" class="lab">{esc(label)}</text>'
                   f'<rect x="100" y="{y + 3}" width="{w:.1f}" height="16" rx="3" fill="var(--bar)"/>'
                   f'<text x="{106 + w:.1f}" y="{y + 15}" font-size="13" class="lab" font-weight="650">'
                   f'{fmt.format(v)}{esc(unit)}</text>')
    out.append("</svg>")
    return "".join(out)


def _money(v):
    return "n/a" if v is None else f"${v:,.2f}"


def _num(v, places=1, unit=""):
    return "n/a" if v is None else f"{v:,.{places}f}{unit}"


def pen_feed_html(herd: Herd, milk_price: float | None = None, days: int = 7) -> str:
    pf = feeding.pen_feed(herd, days=days, milk_price=milk_price)
    pens = [p for p in pf["pens"] if p.get("tested")]
    rows = []
    for p in pens:
        dmi, before = p.get("dmi_lb_per_cow"), p.get("dmi_before")
        change = f"<span class='delta'>{dmi - before:+.1f} on the week before</span>" if dmi and before else ""
        chips = [chip("ECM per cow", _num(p.get("ecm_mean_lb"), 1, " lb")),
                 chip("DM fed per cow", _num(dmi, 1, " lb")),
                 chip("ECM per lb DM", _num(p.get("ecm_per_lb_dm"), 2)),
                 chip("Feed per cow", _money(p.get("feed_cost_per_cow"))),
                 chip("Feed per cwt", _money(p.get("feed_cost_per_cwt")))]
        if "iofc_per_cow" in p:
            chips.append(chip(f"IOFC at ${milk_price:.2f}", _money(p["iofc_per_cow"])))
        if p.get("nasem_predicted_dmi"):
            chips.append(chip("NASEM predicts", _num(p["nasem_predicted_dmi"], 1, " lb")))
        rows.append(f"<div class='penrow'><div class='penname'>Pen {esc(p['pen'])}<small>{p['cows']} cows · "
                    f"{p['tested']} tested</small></div><div><div class='chips'>{''.join(chips)}</div>{change}</div></div>")
    eff = bars([(f"Pen {p['pen']}", p.get("ecm_per_lb_dm")) for p in pens], fmt="{:.2f}")
    cwt = bars([(f"Pen {p['pen']}", p.get("feed_cost_per_cwt")) for p in pens], unit="", fmt="${:.2f}")
    loading = ""
    try:
        la = feeding.loading_accuracy(herd, by="ingredient", days=14)["rows"][:6]
        loading = ("<div class='chips'>" + "".join(
            chip(r["ingredient"], f"{r['mean_deviation_pct']:+.1f}%" + (f" · {r['mean_deviation_lb']:+.2f} lb"
                                     if abs(r["mean_deviation_lb"]) >= .005 else "")) for r in la)
            + "</div><div class='sub'>Fed against called for, average a day over 14 days, largest first</div>")
    except SystemExit:
        loading = "<p class='sub'>No ingredient intake report in the folder.</p>"
    end = herd.as_of
    body = (f"<div class='sec'><h2>Each pen, last {days} days</h2>{''.join(rows)}</div>"
            f"<div class='sec grid2'><div><h2>ECM per lb of dry matter</h2>{eff}</div>"
            f"<div><h2>Feed cost per cwt of milk</h2>{cwt}</div></div>"
            f"<div class='sec'><h2>Loading</h2>{loading}</div>")
    foot = (f"From DairyComp's cow report and EZfeed's pen summary and intake reports. Records end {end:%b %d, %Y}. "
            "Per cow uses DairyComp's head count; dry matter is delivered, not eaten; ECM is each cow's last test; "
            "NASEM 2021 equation 2-1 for the predicted intake.")
    return _page("Pen feed", f"Milking pens · {days} days to {end:%b} {end.day}", body, foot)


def weekly_html(herd: Herd, milk_price: float | None = None, actions: list[tuple[str, str]] | None = None) -> str:
    w = weekly.weekly(herd, milk_price)
    h = w["herd"]
    end = herd.as_of
    sec = []
    t = h["test"]
    sec.append("<div class='sec'><h2>The herd</h2><div class='chips'>"
               + chip("Milking", h["milking"]) + chip("Dry", h["dry"]) + chip("Heifers", h["heifers"])
               + chip("Left, 12 months", h["left_last_12_months"])
               + chip("Median days in milk", _num(h["median_dim"], 0))
               + chip("ECM per cow, last test", _num(t["ecm_mean_lb"], 1, " lb"))
               + chip("SCC over 200k", f"{t['scc_over_200']} of {t['scc_tested']}") + "</div></div>")
    pens = [p for p in w["pens"] if p["kind"] == "milking" and p["tested"]]
    sec.append("<div class='sec'><h2>Pens, ECM per cow at the last test</h2>"
               + bars([(f"Pen {p['pen']}", p["ecm_mean"]) for p in pens], unit=" lb", fmt="{:.1f}") + "</div>")
    # Fresh cows.
    fc = w["fresh_cows"]
    dz = []
    for d in fc["diseases"]:
        if "by_parity" not in d:
            dz.append(chip(d["event"].capitalize(), "not recorded"))
            continue
        n = sum(r["lactations"] for r in d["by_parity"])
        k = sum(r["cases"] for r in d["by_parity"])
        dz.append(chip(d["event"].capitalize(), f"{k} of {n} · {100 * k / n:.1f}%" if n else "n/a"))
    ex = "".join(chip(f"Left by {e['within_dim']} DIM", f"{e['left']} of {e['lactations']}") for e in fc["exits"])
    fp = "".join(chip(f"Fat:protein > 1.4, parity {r['parity']}", f"{r['over_1_4']} of {r['cows']}") for r in fc["fat_protein_5_40_dim"])
    sec.append(f"<div class='sec'><h2>Fresh cows</h2><div class='chips'>{''.join(dz)}</div>"
               f"<div class='sub'>First case within 30 days in milk (ketosis 21), lactations observed from calving, as "
               f"the farm records them</div><div class='chips'>{ex}{fp}</div><div class='sub'>Fat:protein at 5-40 days in "
               f"milk, each cow's last test (after Oetzel)</div></div>")
    # Components and udder side by side.
    comp = w["components"]
    stage = "".join(chip(f"{r['dim']} DIM, parity {r['parity']}", f"{r['fat_pct']:.2f}% · {r['protein_pct']:.2f}%")
                    for r in comp["by_stage"])
    mid = comp["mid_lactation"]
    udder = w["udder_health"]
    pens_scc = "".join(chip(f"Pen {p['pen']}", f"{p['over_200']} of {p['tested']}") for p in udder["high_scc_by_pen"])
    bt = udder["between_tests"]
    names = {"new": "New high", "chronic": "Chronic", "cured": "Cured", "low both": "Low at both tests"}
    dyn = "".join(chip(names.get(k, k), v) for k, v in bt.items() if k != "cows") if isinstance(bt, dict) else ""
    cm = udder["clinical_mastitis_by_month"]
    cm_bars = bars([(r["month"], r["per_100_cows"]) for r in cm[-6:]], fmt="{:.1f}") if isinstance(cm, list) else \
        f"<p class='sub'>{esc(cm)}</p>"
    mid_chips = (chip("Inverted, 41-150 DIM", f"{mid['inverted']} of {mid['cows']}")
                 + chip("Fat under 3.0%, 41-150 DIM", f"{mid['fat_under_3']} of {mid['cows']}"))
    mun = comp["mun_by_pen"]
    mun_chips = "".join(chip(f"MUN, pen {m['pen']}", f"{m['mean']:.1f} mg/dL") for m in mun) if isinstance(mun, list) else ""
    sec.append(f"<div class='sec grid2'><div><h2>Components</h2><div class='chips'>{stage}</div><div class='sub'>Fat · "
               f"protein, each cow's last test</div><div class='chips'>{mid_chips}{mun_chips}"
               f"</div></div><div><h2>Udder health</h2><div class='chips'>{pens_scc}</div><div class='sub'>SCC over 200,000 "
               f"by pen</div><div class='chips'>{dyn}</div><div class='sub'>Between the last two tests</div>"
               f"<div class='sub'>Clinical mastitis per 100 cows in milk, by month</div>{cm_bars}</div></div>")
    # Reproduction and exits.
    rp = w["reproduction"]
    pr = "".join(chip(f"Parity {r['parity']}", f"PR {r['pregnancy_rate_pct']}% · CR {r['conception_rate_pct']}%")
                 for r in rp.get("pregnancy_rate", []))
    sv = "".join(chip(f"Service {r['service']}", f"{r['pct']}% of {r['services']}") for r in rp.get("conception_by_service", []))
    exits = w["exits"]["by_reason_and_stage"]
    ex2 = "".join(chip(f"{e['reason'].capitalize()}, {e['stage']}", e["animals"]) for e in exits)
    sec.append(f"<div class='sec grid2'><div><h2>Reproduction</h2><div class='chips'>{pr}</div><div class='sub'>21-day "
               f"pregnancy rate and conception rate</div><div class='chips'>{sv}</div><div class='sub'>Conception by "
               f"service</div></div><div><h2>Who left, 12 months</h2><div class='chips'>{ex2}</div></div></div>")
    if "pen_feed" in w and isinstance(w["pen_feed"], dict):
        feedchips = "".join(chip(f"Pen {p['pen']}", f"{_num(p.get('ecm_per_lb_dm'), 2)} ECM/lb DM · "
                                 f"{_money(p.get('feed_cost_per_cwt'))}/cwt") for p in w["pen_feed"]["pens"] if p.get("tested"))
        sec.append(f"<div class='sec'><h2>Feed, last 7 days</h2><div class='chips'>{feedchips}</div></div>")
    acts = "".join(f"<div class='act'><span class='box'></span><span>{esc(a)}</span><span class='who'>{esc(who)}</span>"
                   "</div>" for a, who in (actions or []))
    sec.append("<div class='sec'><h2>Actions for the next visit</h2>"
               + (acts or "<p class='sub'>None written yet.</p>") + "</div>")
    foot = (f"From DairyComp's cow, test and event reports and EZfeed's reports. Records end {end:%b %d, %Y}. Every "
            "figure is the farm's own, against itself; not recorded is not zero.")
    return _page("Visit review", f"{h['milking']} milking · records to {end:%b} {end.day}, {end.year}", "".join(sec), foot)
