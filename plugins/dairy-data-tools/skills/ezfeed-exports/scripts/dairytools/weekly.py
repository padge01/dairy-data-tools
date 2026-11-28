"""The weekly (or visit) analyses a consultant pulls: fresh cows, components and MUN, udder health, reproduction and
exits. Ported from the R version (epi.R, transition.R, nutrition.R, udder.R, repro.R) with its denominators: who is
counted, and what the records can't know yet, is stated every time.

The farm is compared with itself (month by month, pen by pen); a published cut-point appears only as the cited
definition of a case (fat:protein above 1.4 at 5-40 days in milk, after Oetzel), never as an alarm.
"""

from __future__ import annotations

from calendar import monthrange
from collections import Counter, defaultdict
from datetime import date, timedelta

from .errors import MissingDataError
from .herd import Herd
from .stats import mean, p10_50_90, pct

DISEASES = {"retained_placenta": 30, "milk_fever": 30, "metritis": 30, "ketosis": 21, "displaced_abomasum": 30,
            "clinical_mastitis": 30, "lameness": 30}


def _month(d: date) -> str:
    return f"{d.year}-{d.month:02d}"


def _month_intervals(start: date, end: date) -> list[tuple[str, date, date]]:
    """Every calendar month overlapping `[start, end]`, clipped to `[start, end]`."""
    out: list[tuple[str, date, date]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        first = date(y, m, 1)
        last = date(y, m, monthrange(y, m)[1])
        lo = max(first, start)
        hi = min(last, end)
        out.append((f"{y}-{m:02d}", lo, hi))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def incidence(herd: Herd, event: str, within_dim: int, by: str = "parity") -> dict:
    """First case per lactation from calving to `within_dim` days in milk, among lactations observed from calving
    that calved at least `within_dim` days before the records end."""
    end = herd.as_of
    cutoff = end - timedelta(days=within_dim)
    at_risk = [l for l in herd.lactations if l["fully_observed"] and (l["lactation"] or 0) >= 1
               and l["fresh_date"] <= cutoff]
    cases = set()
    lacts_by_animal = defaultdict(list)
    for l in at_risk:
        lacts_by_animal[l["animal_id"]].append(l)
    for e in herd.events_by_std.get(event, ()):
        for l in lacts_by_animal.get(e["animal_id"], ()):
            dim = (e["event_date"] - l["fresh_date"]).days
            if 0 <= dim <= within_dim:
                cases.add((l["animal_id"], l["fresh_date"]))
    groups = defaultdict(lambda: [0, 0])
    for l in at_risk:
        g = {"parity": "1" if l["lactation"] == 1 else "2+", "calving_month": _month(l["fresh_date"]),
             "none": "all"}[by]
        groups[g][0] += 1
        groups[g][1] += (l["animal_id"], l["fresh_date"]) in cases
    rows = [{"group": g, "lactations": n, "cases": k, "risk_pct": pct(k, n)} for g, (n, k) in sorted(groups.items())]
    return {"event": event, "within_dim": within_dim, "rows": rows,
            "definition": f"First {event.replace('_', ' ')} from 0 to {within_dim} days in milk, once per lactation; "
                          f"lactations observed from calving that calved on or before {cutoff}."}


def fresh_cows(herd: Herd) -> dict:
    """Transition health, early exits and the first-test fat:protein screen, by calving month (the farm against its
    own months) and by parity."""
    recorded = set(herd.events_by_std)
    diseases = []
    for event, window in DISEASES.items():
        if event not in recorded:
            diseases.append({"event": event.replace("_", " "), "note": "not recorded in these events (not zero)"})
            continue
        diseases.append({"event": event.replace("_", " "),
                         "by_parity": incidence(herd, event, window, "parity")["rows"],
                         "by_calving_month": incidence(herd, event, window, "calving_month")["rows"],
                         "within_dim": window})
    exits = []
    for d in (30, 60):
        cutoff = herd.as_of - timedelta(days=d)
        at_risk = [l for l in herd.lactations if l["fully_observed"] and (l["lactation"] or 0) >= 1
                   and l["fresh_date"] <= cutoff]
        left = [l for l in at_risk if l["end_reason"] in ("sold", "died") and (l["end_date"] - l["fresh_date"]).days <= d]
        exits.append({"within_dim": d, "lactations": len(at_risk), "left": len(left), "pct": pct(len(left), len(at_risk)),
                      "sold": sum(1 for l in left if l["end_reason"] == "sold"),
                      "died": sum(1 for l in left if l["end_reason"] == "died")})
    fresh_milking = [c for c in herd.in_herd() if herd.status(c) == "milking" and c.get("days_in_milk") is not None
                     and 5 <= c["days_in_milk"] <= 40]
    fp = []
    first = {}
    for parity in ("1", "2+"):
        in_par = [c for c in fresh_milking if ("1" if c.get("lactation") == 1 else "2+") == parity]
        tested = [c for c in in_par if c.get("test_fat_pct") and c.get("test_protein_pct")]
        k = sum(1 for c in tested if c["test_fat_pct"] / c["test_protein_pct"] > 1.4)
        fp.append({"parity": parity, "cows": len(tested), "over_1_4": k, "pct": pct(k, len(tested)),
                   "note": "fewer than 12 cows: too few to read" if len(tested) < 12 else None})
        milk = [c["test_milk"] for c in in_par if (c.get("test_milk") or 0) > 0]
        first[parity] = p10_50_90(milk)
    return {"as_of": herd.as_of.isoformat(), "diseases": diseases, "exits": exits, "fat_protein_5_40_dim": fp,
            "test_milk_5_40_dim": first, "source": herd.source_line(),
            "definitions": ["Disease: first case per lactation within the window (ketosis 21 days, others 30), "
                            "lactations observed from calving with the whole window behind them. As the farm "
                            "records it: farms define and detect ketosis and metritis differently.",
                            "Fat:protein above 1.4 at 5-40 days in milk, each cow's last test (after Oetzel), as a "
                            "herd screen, not a diagnosis of a cow."]}


def components(herd: Herd) -> dict:
    """Fat, protein and fat:protein at the last test by stage of lactation and parity; inverted and low-fat shares at
    41-150 days in milk; MUN by pen when the farm records it."""
    cows = [c for c in herd.in_herd() if herd.status(c) == "milking" and c.get("days_in_milk") is not None
            and (c.get("test_milk") or 0) > 0 and c.get("test_fat_pct") and c.get("test_protein_pct")]
    bands = [(5, 40), (41, 100), (101, 200), (201, 999)]
    rows = []
    for lo, hi in bands:
        for parity in ("1", "2+"):
            g = [c for c in cows if lo <= c["days_in_milk"] <= hi and ("1" if c.get("lactation") == 1 else "2+") == parity]
            if not g:
                continue
            rows.append({"dim": f"{lo}-{hi}" if hi < 999 else f"over {lo - 1}", "parity": parity, "cows": len(g),
                         "milk_lb": mean(c["test_milk"] for c in g), "fat_pct": mean(c["test_fat_pct"] for c in g),
                         "protein_pct": mean(c["test_protein_pct"] for c in g),
                         "fat_protein": mean(c["test_fat_pct"] / c["test_protein_pct"] for c in g)})
    mid = [c for c in cows if 41 <= c["days_in_milk"] <= 150]
    inverted = sum(1 for c in mid if c["test_fat_pct"] <= c["test_protein_pct"] - 0.2)
    low = sum(1 for c in mid if c["test_fat_pct"] < 3.0)
    mun_key = "test_mun" if any(c.get("test_mun") for c in cows) else ("mun" if any(c.get("mun") for c in cows) else None)
    mun = []
    if mun_key:
        by_pen = defaultdict(list)
        for c in cows:
            if c.get(mun_key):
                by_pen[c["pen"]].append(c[mun_key])
        mun = [{"pen": p, "cows": len(v), "mean": mean(v), "spread": p10_50_90(v),
                "under_8_pct": pct(sum(1 for x in v if x < 8), len(v)),
                "over_12_pct": pct(sum(1 for x in v if x > 12), len(v))} for p, v in sorted(by_pen.items())]
    return {"by_stage": rows, "mid_lactation": {"cows": len(mid), "inverted": inverted, "inverted_pct": pct(inverted, len(mid)),
                                                "fat_under_3": low, "fat_under_3_pct": pct(low, len(mid))},
            "mun_by_pen": mun or "MUN isn't in the cow report (add the farm's MUN item to the export)",
            "source": herd.source_line(),
            "definitions": ["Each milking cow's last test. Inverted: fat at least 0.2 points below protein. MUN: build "
                            "the herd's own baseline on the current ration; a move of 2-3 points means look for what "
                            "changed (Penn State)."]}


def udder_health(herd: Herd) -> dict:
    """High SCC by pen; new, chronic and cured high counts between the last two tests (200,000 cells/mL, linear score
    4); clinical mastitis cases per 100 cows in milk per month."""
    cows = [c for c in herd.in_herd() if herd.status(c) == "milking" and (c.get("test_scc") or 0) > 0]
    by_pen = defaultdict(lambda: [0, 0])
    for c in cows:
        by_pen[c["pen"]][0] += 1
        by_pen[c["pen"]][1] += c["test_scc"] > 200
    pens = [{"pen": p, "tested": n, "over_200": k, "pct": pct(k, n)} for p, (n, k) in sorted(by_pen.items())]
    both = [c for c in cows if (c.get("prev_test_scc") or 0) > 0]
    dyn = Counter()
    for c in both:
        was, now = c["prev_test_scc"] > 200, c["test_scc"] > 200
        dyn["chronic" if was and now else "new" if now else "cured" if was else "low both"] += 1

    # Exact interval overlap per month across the trailing 365 days (replaces day-by-day iteration).
    win_start = herd.as_of - timedelta(days=365)
    month_windows = _month_intervals(win_start, herd.as_of)
    months: dict[str, list[float]] = {m: [0, 0.0] for m, _, _ in month_windows}
    for l in herd.lactations:
        start = max(l["fresh_date"], win_start)
        stop = min(l["end_date"] or herd.as_of, herd.as_of)
        if stop < start:
            continue
        for m, m_lo, m_hi in month_windows:
            if m_hi < start:
                continue
            if m_lo > stop:
                break
            lo = start if start > m_lo else m_lo
            hi = stop if stop < m_hi else m_hi
            if hi >= lo:
                months[m][1] += (hi - lo).days + 1
    mast_events = herd.events_by_std.get("clinical_mastitis", ())
    for e in mast_events:
        if e["event_date"] > win_start and e["event_date"] <= herd.as_of:
            m = _month(e["event_date"])
            if m in months:
                months[m][0] += 1
    # A month counts only once every cow in milk then calved inside the events (305 days after they begin).
    full_from = _month(herd.events_from + timedelta(days=305)) if herd.events_from else None
    rate = [{"month": m, "cases": int(k), "cows_in_milk": round(cd / 30.4), "per_100_cows": round(100 * k / (cd / 30.4), 1)
             if cd else None} for m, (k, cd) in sorted(months.items()) if full_from and m >= full_from and (k or cd)]
    return {"high_scc_by_pen": pens,
            "between_tests": {"cows": len(both), **dyn} if both else "No previous-test SCC (add PSCC to the export)",
            "clinical_mastitis_by_month": rate if rate and any(r["cases"] for r in rate) else
            ("No clinical mastitis events recorded" if not mast_events
             else "The events don't reach back far enough for whole months (export 3 years: EVENTS\\2S1095-0B)"),
            "source": herd.source_line(),
            "definitions": ["SCC in thousands of cells per mL; 0 means not tested and is left out. High: over 200,000 "
                            "(linear score 4). Clinical mastitis per 100 cows in milk per month: cases over cow-days "
                            "in milk / 30.4; a part month at either end has fewer days."]}


def reproduction(herd: Herd, vwp: int = 50) -> dict:
    """21-day pregnancy, service and conception rates (BREDSUM's way), and conception by service number.

    Delegates directly to `repro.pregnancy_rate` and `repro.conception_by` so `weekly` / `repro` and `conception`
    always report identical counts and rates.
    """
    from . import repro
    note = None
    try:
        pr = repro.pregnancy_rate(herd, vwp=vwp, by="parity", cycles=False)
        rates = [
            {
                "parity": r["group"],
                "eligible": r["eligible"],
                "bred": r["bred"],
                "pregnant": r["pregnant"],
                "service_rate_pct": pct(r["bred"], r["eligible"]),
                "conception_rate_pct": pct(r["pregnant"], r["bred"]),
                "pregnancy_rate_pct": pct(r["pregnant"], r["eligible"]),
            }
            for r in pr["rows"]
        ]
        pr_def = pr["definition"]
    except MissingDataError as exc:
        rates = []
        note = str(exc)
        pr_def = note
    cb = repro.conception_by(herd, group="service")
    cr = [
        {
            "service": r["service"],
            "services": r["services"],
            "pregnant": r["pregnant"],
            "pct": pct(r["pregnant"], r["services"]),
            "interval_pct": [round(100 * r["ci_low"], 1), round(100 * r["ci_high"], 1)] if r["ci_low"] is not None else None,
            "note": "fewer than 20 services: too few to compare" if r["services"] < 20 else None,
        }
        for r in cb["rows"]
    ]
    out = {"pregnancy_rate": rates, "conception_by_service": cr, "vwp": vwp, "source": herd.source_line(),
           "definitions": [pr_def, cb["definition"]]}
    if note:
        out["note"] = note
    return out


def exits(herd: Herd) -> dict:
    """Who left in the last 12 months: sold or died, and at what stage of lactation."""
    since = herd.as_of - timedelta(days=365)
    left = [c for c in herd.cows if c.get("left_date") and since < c["left_date"] <= herd.as_of]
    bands = Counter()
    for c in left:
        l = max((x for x in herd.lactations_by_animal.get(c["animal_id"], ()) if x["fresh_date"] <= c["left_date"]),
                key=lambda x: x["fresh_date"], default=None)
        dim = (c["left_date"] - l["fresh_date"]).days if l else None
        band = "not calved / unknown" if dim is None else "0-60 days in milk" if dim <= 60 else \
            "61-200" if dim <= 200 else "over 200"
        bands[(c.get("left_reason") or "left", band)] += 1
    return {"left_last_12_months": len(left), "by_reason_and_stage": [{"reason": r, "stage": b, "animals": n}
                                                                      for (r, b), n in sorted(bands.items())],
            "source": herd.source_line(),
            "definitions": ["Left: the last SOLD or DIED event, else the archive date. Sale and death reasons are "
                            "the farm's own codes in remarks, left out here as untrusted text."]}


def weekly(herd: Herd, milk_price=None, vwp: int = 50) -> dict:
    """Everything for a visit or a week, in one place."""
    from . import explorer, feeding
    out = {"herd": explorer.herd_summary(herd), "pens": explorer.pen_summary(herd), "fresh_cows": fresh_cows(herd),
           "components": components(herd), "udder_health": udder_health(herd),
           "reproduction": reproduction(herd, vwp=vwp), "exits": exits(herd)}
    if herd.feed:
        # Separately: a farm can send the Pen Summary without the loading report, or the other way round.
        try:
            out["pen_feed"] = feeding.pen_feed(herd, milk_price=milk_price)
        except MissingDataError as e:
            out["pen_feed"] = str(e)
        try:
            out["loading"] = feeding.loading_accuracy(herd, by="pen", days=14)
        except MissingDataError as e:
            out["loading"] = str(e)
    return out
