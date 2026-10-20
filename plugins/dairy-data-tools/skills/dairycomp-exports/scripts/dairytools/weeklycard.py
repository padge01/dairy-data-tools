"""The pen-feed card and the visit review page, in the kit's card look: big-figure tiles, plain HTML bars (their text
never scales), a small grid where a table is clearest. Record only: the farm against itself, every figure with its
count, nothing coloured that isn't also labelled."""

from __future__ import annotations

from datetime import date, timedelta

from . import feeding, weekly
from .cards import CSS, _recipe, esc, ration_bars
from .herd import Herd

PAGE_CSS = """
.page{max-width:1180px;margin:24px auto;background:var(--surface);border:1px solid var(--border);border-radius:22px;
padding:22px 30px 16px}
.sec{border-top:1px solid var(--subtle);padding:14px 0 16px}
.sec h2{font-size:18px;margin:0 0 2px;font-weight:650}.note{font-size:13px;color:var(--text3);margin:0 0 10px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:34px}
.trow{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:0 18px}
.t{padding:4px 0}.t .k{font-size:13.5px}.t .v{font-size:26px;margin:0}.t .v small{font-size:13.5px}
.t .n{font-size:12.5px}
.hb{display:grid;grid-template-columns:minmax(90px,max-content) 1fr;column-gap:12px;row-gap:7px;align-items:center}
.hb .l{font-size:14px;white-space:nowrap}.hb .track{display:flex;align-items:center;gap:8px;min-width:0}
.hb .bar{height:16px;border-radius:3px;background:var(--bar);flex:0 0 auto}
.hb .val{font-size:13.5px;font-weight:650;white-space:nowrap}.hb .val small{font-weight:400;color:var(--text2)}
.div{display:grid;grid-template-columns:170px minmax(0,260px) minmax(0,260px) max-content;column-gap:0;row-gap:7px;align-items:center}
.div .l{font-size:14px;padding-right:10px}.div .neg{display:flex;justify-content:flex-end;border-right:1.5px solid var(--line)}
.div .pos{display:flex;justify-content:flex-start}.div .bar{height:14px;background:var(--bar)}
.div .neg .bar{border-radius:3px 0 0 3px}.div .pos .bar{border-radius:0 3px 3px 0}
.div .val{font-size:13.5px;font-weight:650;padding-left:10px;white-space:nowrap}.div .axis{font-size:12px;color:var(--text3)}
.slide .rations{grid-template-columns:repeat(auto-fit,minmax(280px,1fr))}.slide .rations h3{font-size:24px}
.slide .rations .trow{grid-template-columns:repeat(3,1fr);margin:4px 0 6px}.slide .t .v{font-size:22px}
.pen{display:grid;grid-template-columns:150px 1fr 260px;gap:18px;align-items:start;padding:12px 0;
border-bottom:1px solid var(--subtle)}.pen:last-child{border:0}
.pen .who{font-size:26px;font-weight:700;line-height:1.1}.pen .who small{display:block;font-size:13px;font-weight:400;
color:var(--text2);margin-top:3px}
.facts{font-size:13.5px;line-height:1.75;color:var(--text2)}.facts b{color:var(--text);font-weight:650}
.grid{display:grid;border:1px solid var(--subtle);border-radius:10px;overflow:hidden;font-size:14px;align-self:start}
.grid div{padding:6px 10px;border-bottom:1px solid var(--subtle)}.grid .h{font-size:12.5px;color:var(--text2);
background:var(--raised)}.grid .r{font-weight:600}
.muted{font-size:13px;color:var(--text3);margin-top:8px}
.act{display:grid;grid-template-columns:24px 1fr auto;gap:8px;align-items:start;padding:8px 0;
border-bottom:1px solid var(--subtle);font-size:15px}.act:last-child{border:0}.box{width:16px;height:16px;
border:1.5px solid var(--line);border-radius:4px;margin-top:3px}.act .who{font-size:13px;color:var(--text2)}
@media (max-width:820px){.two{grid-template-columns:1fr}.pen{grid-template-columns:1fr}.div{grid-template-columns:110px 1fr 1fr 96px}}
"""


def _page(title: str, sub: str, body: str, foot: str, slide: bool = False) -> str:
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
            f"content='width=device-width,initial-scale=1'><title>{esc(title)}</title><style>{CSS}{PAGE_CSS}</style>"
            f"</head><body{' class=slide' if slide else ''}><div class='page'><div class='head'><h1>{esc(title)}</h1><span>{esc(sub)}</span></div>"
            f"{body}<div class='foot'>{esc(foot)}</div></div></body></html>")


def tile(label, value, unit="", note="") -> str:
    return (f"<div class='t'><div class='k'>{esc(label)}</div><div class='v'>{esc(value)}"
            + (f"<small>{esc(unit)}</small>" if unit else "") + "</div>"
            + (f"<div class='n'>{esc(note)}</div>" if note else "") + "</div>")


def hbars(rows, fmt="{:.1f}", unit="") -> str:
    """rows: (label, value, extra words). Bars scaled to the largest; every bar carries its value in words."""
    rows = [r for r in rows if r[1] is not None]
    if not rows:
        return "<p class='muted'>Nothing recorded.</p>"
    top = max(r[1] for r in rows) or 1
    room = 50 if any(r[2] for r in rows) else 78   # leave room for the words after the bar
    out = []
    for label, value, extra in rows:
        width = max(2.0, room * value / top)
        out.append(f"<div class='l'>{esc(label)}</div><div class='track'><div class='bar' style='width:{width:.1f}%'>"
                   f"</div><span class='val'>{esc(fmt.format(value))}{esc(unit)}"
                   + (f" <small>{esc(extra)}</small>" if extra else "") + "</span></div>")
    return f"<div class='hb'>{''.join(out)}</div>"


def _money(v):
    return "n/a" if v is None else f"${v:,.2f}"


def _num(v, places=1):
    return "n/a" if v is None else f"{v:,.{places}f}"


# --- pen feed --------------------------------------------------------------------------------------------------------

def pen_feed_html(herd: Herd, milk_price: float | None = None, days: int = 7, slide: bool = False) -> str:
    """Each pen's feed against its milk, each pen's ration as bars, loading. slide: for a projector, bigger and
    with fewer items (each pen's three figures and its ration)."""
    pf = feeding.pen_feed(herd, days=days, milk_price=milk_price)
    pens = [p for p in pf["pens"] if p.get("dmi_lb_per_cow") is not None]   # every pen fed, tested or not
    span = ""
    if pens:
        a, _, b = pens[0]["days"].partition(" to ")
        fa, fb = date.fromisoformat(a), date.fromisoformat(b)
        span = f"{fa:%b} {fa.day} – {fb:%b} {fb.day}"
    blocks = []
    for p in pens:
        dmi, before = p.get("dmi_lb_per_cow"), p.get("dmi_before")
        moved = f"{dmi - before:+.1f} lb on the week before" if dmi is not None and before is not None else ""
        facts = [f"ECM <b>{esc(_num(p.get('ecm_mean_lb')))} lb</b> per cow, last test" if p.get("ecm_mean_lb") else
                 f"Milk <b>{esc(_num(p.get('milk_mean_lb')))} lb</b> per cow, {esc(p.get('milk_from', 'last test'))}",
                 f"Feed <b>{esc(_money(p.get('feed_cost_per_cow')))}</b> per cow a day"]
        if "iofc_per_cow" in p:
            facts.append(f"IOFC <b>{esc(_money(p['iofc_per_cow']))}</b> per cow at ${milk_price:.2f} milk")
        if p.get("nasem_predicted_dmi"):
            facts.append(f"NASEM predicts <b>{esc(_num(p['nasem_predicted_dmi']))} lb</b> DM for these cows")
        efficiency = (tile("ECM per lb DM", _num(p.get("ecm_per_lb_dm"), 2))
                      if p.get("ecm_per_lb_dm") or not p.get("milk_per_lb_dm")
                      else tile("Milk per lb DM", _num(p.get("milk_per_lb_dm"), 2)))
        weighed = f"{p['tested']} tested" if p.get("milk_from", "last test") == "last test" else f"{p['tested']} weighed"
        blocks.append(
            f"<div class='pen'><div class='who'>Pen {esc(p['pen'])}<small>{p['cows']} cows · {weighed}</small>"
            f"</div><div class='trow'>{efficiency}"
            f"{tile('DM fed per cow', _num(dmi), ' lb', moved)}"
            f"{tile('Feed cost per cwt', _money(p.get('feed_cost_per_cwt')))}</div>"
            + ("" if slide else f"<div class='facts'>{'<br>'.join(facts)}</div>") + "</div>")
    ecm_eff = any(p.get("ecm_per_lb_dm") for p in pens)
    eff = hbars([(f"Pen {p['pen']}", p.get("ecm_per_lb_dm" if ecm_eff else "milk_per_lb_dm"), "") for p in pens],
                fmt="{:.2f}")
    cwt = hbars([(f"Pen {p['pen']}", p.get("feed_cost_per_cwt"), "") for p in pens], fmt="${:.2f}")
    loading = "<p class='muted'>No Ingredient Intake report in the folder.</p>"
    try:
        la = feeding.loading_accuracy(herd, by="ingredient", days=14)["rows"][:8]
        top = max(abs(r["mean_deviation_pct"]) for r in la) or 1
        rows = []
        for r in la:
            d = r["mean_deviation_pct"]
            w = max(1.5, 92 * abs(d) / top)
            neg = f"<div class='bar' style='width:{w:.1f}%'></div>" if d < 0 else ""
            pos = f"<div class='bar' style='width:{w:.1f}%'></div>" if d >= 0 else ""
            lb = f" · {r['mean_deviation_lb']:+.2f} lb" if abs(r["mean_deviation_lb"]) >= .005 else ""
            rows.append(f"<div class='l'>{esc(r['ingredient'])}</div><div class='neg'>{neg}</div><div class='pos'>{pos}"
                        f"</div><div class='val'>{d:+.1f}%{esc(lb)}</div>")
        loading = (f"<div class='div'><div></div><div class='axis' style='text-align:right;padding-right:6px'>under"
                   f"</div><div class='axis' style='padding-left:6px'>over</div><div></div>{''.join(rows)}</div>")
    except SystemExit:
        pass
    end = herd.as_of
    recipes = {p["pen"]: _recipe(herd, p["ezfeed_pen"], end - timedelta(days=days - 1), end) for p in pens}
    top = max((v for r in recipes.values() for v in r.values()), default=None)   # one scale for every pen
    rations = []
    for p in pens:
        if recipes[p["pen"]]:
            figs = ""
            if slide:   # each pen's three figures over its ration, one column a pen
                figs = (f"<div class='sub'>{p['cows']} cows</div><div class='trow'>"
                        + (tile('ECM per lb DM', _num(p.get('ecm_per_lb_dm'), 2)) if p.get('ecm_per_lb_dm')
                           or not p.get('milk_per_lb_dm') else tile('Milk per lb DM', _num(p.get('milk_per_lb_dm'), 2)))
                        + f"{tile('DM fed', _num(p.get('dmi_lb_per_cow')), ' lb')}"
                        f"{tile('Feed per cwt', _money(p.get('feed_cost_per_cwt')))}</div>")
            rations.append(f"<div><h3>Pen {esc(p['pen'])}</h3>{figs}{ration_bars(recipes[p['pen']], top=top)}</div>")
    ration_sec = (f"<div class='sec'><h2>Each pen's ration</h2><p class='note'>lb of dry matter per cow, called for, "
                  f"the last {days} days; grouped by feed type</p><div class='rations'>{''.join(rations)}</div></div>"
                  if rations else "")
    if slide:
        body = (f"<div class='sec'><p class='note'>{esc(span)}. Per cow uses DairyComp's head count. Rations: lb of dry "
                f"matter per cow, called for, grouped by feed type.</p><div class='rations'>{''.join(rations)}</div></div>")
        return _page("Pen feed", f"{len(pens)} milking pens · {days} days to {end:%b} {end.day}", body,
                     f"From DairyComp and EZfeed's reports. Records end {end:%b %d, %Y}.", slide=True)
    body = (f"<div class='sec'><h2>Each pen</h2><p class='note'>{esc(span)}. Per cow uses DairyComp's head count.</p>"
            f"{''.join(blocks)}</div>{ration_sec}"
            f"<div class='sec two'><div><h2>{'ECM' if ecm_eff else 'Milk'} per lb of dry matter</h2><p class='note'>Each pen's own figure; compare "
            f"it with its own past weeks</p>{eff}</div><div><h2>Feed cost per cwt of milk</h2><p class='note'>Feed cost "
            f"per cow over its milk at the last test</p>{cwt}</div></div>"
            f"<div class='sec'><h2>Loading, fed against called for</h2><p class='note'>Each feed's average miss a day "
            f"over 14 days, all pens; the largest first</p>{loading}</div>")
    foot = (f"From DairyComp's cow report and EZfeed's pen summary and ingredient intake reports. Records end "
            f"{end:%b %d, %Y}. Dry matter is delivered, not eaten. ECM is each cow's last test (0.327 × milk + "
            "12.95 × fat lb + 7.65 × protein lb). NASEM (2021) equation 2-1 with body weight 1,550 lb (1,350 first "
            "lactation) and body condition 3 where the farm doesn't record them.")
    return _page("Pen feed", f"{len(pens)} milking pens · {days} days to {end:%b} {end.day}", body, foot)


# --- visit review ----------------------------------------------------------------------------------------------------

def weekly_html(herd: Herd, milk_price: float | None = None, actions: list[tuple[str, str]] | None = None,
                vwp: int = 50) -> str:
    w = weekly.weekly(herd, milk_price, vwp)
    h = w["herd"]
    t = h["test"]
    end = herd.as_of
    sec = []

    sec.append("<div class='sec'><h2>The herd</h2><p class='note'>Animals in the herd on the day the records end</p>"
               "<div class='trow'>" + tile("Milking", h["milking"]) + tile("Dry", h["dry"]) + tile("Heifers", h["heifers"])
               + tile("Left, last 12 months", h["left_last_12_months"])
               + tile("Median days in milk", _num(h["median_dim"], 0))
               + tile("ECM per cow, last test", _num(t["ecm_mean_lb"]), " lb", f"{t['tested']} of {t['of']} tested")
               + "</div></div>")

    pens = [p for p in w["pens"] if p["kind"] == "milking" and p["tested"]]
    pen_bars = hbars([(f"Pen {p['pen']}", p["ecm_mean"], f"{p['tested']} cows · median {p['median_dim']:.0f} DIM"
                       if p["median_dim"] is not None else f"{p['tested']} cows") for p in pens], unit=" lb")
    feed = w.get("pen_feed")
    feed_bars = ""
    if isinstance(feed, dict):
        fp = [p for p in feed["pens"] if p.get("tested")]
        feed_bars = ("<div><h2>Feed efficiency, last 7 days</h2><p class='note'>ECM per lb of dry matter fed</p>"
                     + hbars([(f"Pen {p['pen']}", p.get("ecm_per_lb_dm"), f"{_money(p.get('feed_cost_per_cwt'))} per cwt")
                              for p in fp], fmt="{:.2f}") + "</div>")
    sec.append(f"<div class='sec two'><div><h2>Pens</h2><p class='note'>ECM per cow at the last test</p>{pen_bars}</div>"
               f"{feed_bars}</div>")

    fc = w["fresh_cows"]
    recorded, missing = [], []
    for d in fc["diseases"]:
        if "by_parity" not in d:
            missing.append(d["event"])
            continue
        n = sum(r["lactations"] for r in d["by_parity"])
        k = sum(r["cases"] for r in d["by_parity"])
        if n:
            recorded.append((d["event"].capitalize(), 100 * k / n, f"{k} of {n}"))
    recorded.sort(key=lambda r: -r[1])
    exits = "".join(tile(f"Left by {e['within_dim']} days in milk", f"{e['left']}", f" of {e['lactations']}",
                         f"{e['died']} died · {e['sold']} sold") for e in fc["exits"])
    fpq = "".join(tile(f"Fat:protein over 1.4, {'first lactation' if r['parity'] == '1' else 'older cows'}",
                       f"{r['over_1_4']}", f" of {r['cows']}", "too few to read" if r["note"] else "5-40 days in milk")
                  for r in fc["fat_protein_5_40_dim"])
    sec.append("<div class='sec'><h2>Fresh cows</h2><p class='note'>First case within 30 days in milk (ketosis 21), "
               "lactations followed from calving, as the farm records them</p><div class='two'><div>"
               + hbars(recorded, unit="%") + (f"<p class='muted'>Not recorded on this farm: {esc(', '.join(missing))}</p>"
                                               if missing else "")
               + f"</div><div class='trow'>{exits}{fpq}</div></div></div>")

    comp = w["components"]
    cells = ["<div class='h'>Days in milk</div><div class='h'>First lactation</div><div class='h'>Older cows</div>"]
    bands = []
    for r in comp["by_stage"]:
        if r["dim"] not in bands:
            bands.append(r["dim"])
    for b in bands:
        def cell(par):
            r = next((x for x in comp["by_stage"] if x["dim"] == b and x["parity"] == par), None)
            return "–" if not r else f"{r['fat_pct']:.2f}% · {r['protein_pct']:.2f}%  ({r['cows']})"
        cells.append(f"<div class='r'>{esc(b)}</div><div>{esc(cell('1'))}</div><div>{esc(cell('2+'))}</div>")
    grid = f"<div class='grid' style='grid-template-columns:1.1fr 1fr 1fr'>{''.join(cells)}</div>"
    mid = comp["mid_lactation"]
    mun = comp["mun_by_pen"]
    mun_tiles = "".join(tile(f"MUN, pen {m['pen']}", f"{m['mean']:.1f}", " mg/dL", f"{m['cows']} cows")
                        for m in mun) if isinstance(mun, list) else ""
    sec.append("<div class='sec'><h2>Components</h2><p class='note'>Fat · protein at each cow's last test (cows)</p>"
               f"<div class='two'>{grid}<div class='trow'>"
               + tile("Inverted, 41-150 DIM", f"{mid['inverted']}", f" of {mid['cows']}", "fat 0.2 points or more under protein")
               + tile("Fat under 3.0%, 41-150 DIM", f"{mid['fat_under_3']}", f" of {mid['cows']}") + mun_tiles
               + "</div></div>"
               + ("" if isinstance(mun, list) else "<p class='muted'>MUN isn't in the cow report.</p>") + "</div>")

    ud = w["udder_health"]
    scc = hbars([(f"Pen {p['pen']}", p["pct"], f"{p['over_200']} of {p['tested']}") for p in ud["high_scc_by_pen"]
                 if p["tested"]], unit="%")
    bt = ud["between_tests"]
    dyn = "".join(tile(n, bt.get(k, 0)) for k, n in (("new", "New high"), ("chronic", "Chronic"), ("cured", "Cured"),
                                                     ("low both", "Low at both tests"))) if isinstance(bt, dict) else ""
    cm = ud["clinical_mastitis_by_month"]
    cm_html = hbars([(r["month"], r["per_100_cows"], f"{r['cases']} cases") for r in cm[-6:]]) \
        if isinstance(cm, list) else f"<p class='muted'>{esc(cm)}</p>"
    sec.append("<div class='sec'><h2>Udder health</h2><div class='two'><div><p class='note'>SCC over 200,000, last test"
               f"</p>{scc}<p class='note' style='margin-top:12px'>Between the last two tests</p><div class='trow'>{dyn}"
               f"</div></div><div><p class='note'>Clinical mastitis per 100 cows in milk, whole months</p>{cm_html}"
               "</div></div></div>")

    rp = w["reproduction"]
    repro_tiles = "".join(
        tile(f"{'First lactation' if r['parity'] == '1' else 'Older cows'}", f"{r['pregnancy_rate_pct']}", "%",
             f"pregnancy rate · service {r['service_rate_pct']}% · conception {r['conception_rate_pct']}%")
        for r in rp.get("pregnancy_rate", []))
    serv = hbars([(f"Service {r['service']}", r["pct"], f"{r['pregnant']} of {r['services']}")
                  for r in rp.get("conception_by_service", [])], unit="%")
    left = w["exits"]["by_reason_and_stage"]
    left_bars = hbars([(f"{e['reason'].capitalize()}, {e['stage']}", e["animals"], "") for e in left], fmt="{:.0f}")
    sec.append("<div class='sec two'><div><h2>Reproduction</h2><p class='note'>21-day pregnancy rate, the way "
               f"DairyComp's BREDSUM counts</p><div class='trow'>{repro_tiles}</div><p class='note' style='margin-top:"
               f"12px'>Conception by service</p>{serv}</div><div><h2>Who left, last 12 months</h2><p class='note'>By "
               f"stage of lactation</p>{left_bars}</div></div>")

    acts = "".join(f"<div class='act'><span class='box'></span><span>{esc(a)}</span><span class='who'>{esc(who)}</span>"
                   "</div>" for a, who in (actions or []))
    sec.append("<div class='sec'><h2>Actions for the next visit</h2>"
               + (acts or "<p class='muted'>None written yet.</p>") + "</div>")
    foot = (f"From DairyComp's cow, test and event reports and EZfeed's reports. Records end {end:%b %d, %Y}. Every "
            "figure is the farm's own; not recorded is not zero; no published targets.")
    return _page("Visit review", f"Records to {end:%b} {end.day}, {end.year} · {h['milking']} cows milking",
                 "".join(sec), foot)
