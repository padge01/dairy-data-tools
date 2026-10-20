"""The herd explorer: the herd, its pens, one pen, one cow. The R version's herd_summary, pen_summary, pen_card and
cow_record in Python, with the same rules: every count says what it is out of; milk as a spread, not an average
alone; a pen's events are for the cows in it now (DairyComp holds only the current pen); remarks never shown."""

from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta

from .herd import Herd, pen_label
from .stats import ecm_lb, median, p10_50_90

REPRO_LABELS = {"FRESH": "Fresh", "OPEN": "Open", "BRED": "Bred", "PREG": "Pregnant", "DRY": "Dry",
                "NO BRED": "Do not breed"}
TRANSITION = {"retained_placenta": "retained placenta", "metritis": "metritis", "ketosis": "ketosis",
              "displaced_abomasum": "displaced abomasum", "milk_fever": "milk fever",
              "clinical_mastitis": "clinical mastitis"}


def _lact_group(cow):
    lact = cow.get("lactation")
    return "3+" if lact and lact >= 3 else str(lact) if lact else "Heifer"


def repro_split(cows):
    counts = Counter()
    for c in cows:
        s = (c.get("repro_status") or "").strip().upper() or "Not recorded"
        counts[REPRO_LABELS.get(s, s)] += 1
    order = list(REPRO_LABELS.values())
    return [{"status": k, "cows": counts[k]} for k in order + sorted(set(counts) - set(order)) if counts[k]]


def _test(cows, milk_from="last test"):
    milk = [c.get("test_milk") for c in cows if (c.get("test_milk") or 0) > 0]
    scc = [c.get("test_scc") for c in cows if (c.get("test_scc") or 0) > 0]   # SCC 0 means not tested
    ecm = [ecm_lb(c.get("test_milk"), c.get("test_fat_pct"), c.get("test_protein_pct")) for c in cows
           if (c.get("test_milk") or 0) > 0]
    ecm = [e for e in ecm if e is not None]
    dates = [c["test_date"] for c in cows if c.get("test_date")]
    return {"date": max(dates).isoformat() if dates else None, "of": len(cows), "tested": len(milk),
            "milk_from": milk_from,
            "milk_lb": p10_50_90(milk), "ecm_lb": p10_50_90(ecm),
            "ecm_mean_lb": sum(ecm) / len(ecm) if ecm else None, "milk_mean_lb": sum(milk) / len(milk) if milk else None,
            "scc_tested": len(scc), "scc_over_200": sum(1 for s in scc if s > 200)}


def herd_summary(herd: Herd) -> dict:
    status = {c["animal_id"]: herd.status(c) for c in herd.cows}
    n = Counter(status.values())
    left_12 = sum(1 for c in herd.cows if c.get("left_date") and herd.as_of - timedelta(days=365) < c["left_date"]
                  <= herd.as_of)
    calved = [c for c in herd.cows if status[c["animal_id"]] in ("milking", "dry")]
    milking = [c for c in calved if status[c["animal_id"]] == "milking"]
    lact = []
    for g in ("1", "2", "3+"):
        lact.append({"lactation": g, "milking": sum(1 for c in milking if _lact_group(c) == g),
                     "dry": sum(1 for c in calved if status[c["animal_id"]] == "dry" and _lact_group(c) == g)})
    std_events = {e["std_event"] for e in herd.events}
    return {"as_of": herd.as_of.isoformat(), "milking": n["milking"], "dry": n["dry"], "heifers": n["heifer"],
            "left_last_12_months": left_12,
            "median_dim": median(c["days_in_milk"] for c in milking),
            "lactation": lact, "repro": repro_split(calved), "test": _test(milking, herd.milk_words),
            "holds": {"events_from": herd.events_from.isoformat() if herd.events_from else None,
                      "events": len(herd.events), "unmapped_codes": herd.unmapped_codes,
                      "not_recorded": [v for k, v in TRANSITION.items() if k not in std_events],
                      "problems": herd.problems},
            "source": herd.source_line()}


def _pen_row(herd, cows, pen):
    st = Counter(herd.status(c) for c in cows)
    milking = [c for c in cows if herd.status(c) == "milking"]
    kind = max(st, key=st.get) if cows and max(st.values()) > len(cows) / 2 else "mixed"
    t = _test(milking, herd.milk_words)
    return {"pen": pen, "kind": kind, "animals": len(cows), "milking": st["milking"], "dry": st["dry"],
            "heifers": st["heifer"], "median_dim": median(c["days_in_milk"] for c in milking),
            "first_lactation": sum(1 for c in cows if c.get("lactation") == 1),
            "pregnant": sum(1 for c in cows if (c.get("repro_status") or "").upper() == "PREG"),
            "tested": t["tested"], "median_test_milk": t["milk_lb"]["p50"] if t["milk_lb"] else None,
            "ecm_mean": t["ecm_mean_lb"], "scc_tested": t["scc_tested"], "scc_over_200": t["scc_over_200"]}


def pen_order(labels):
    def key(p):
        n = re.fullmatch(r"\d+(\.\d+)?", p)
        return (p == "No pen", n is None, float(p) if n else 0, p)
    return sorted(set(labels), key=key)


def pen_summary(herd: Herd) -> list[dict]:
    now = herd.in_herd()
    return [_pen_row(herd, [c for c in now if c["pen"] == p], p) for p in pen_order(c["pen"] for c in now)]


def pen_card(herd: Herd, pen, days: int = 30) -> dict:
    pen = pen_label(pen)
    now = herd.in_herd()
    cows = [c for c in now if c["pen"] == pen]
    if not cows:
        raise SystemExit(f"No animals in pen {pen}. The herd's pens: {', '.join(pen_order(c['pen'] for c in now))}.")
    milking = [c for c in cows if herd.status(c) == "milking"]
    ids = {c["animal_id"] for c in cows}
    since = herd.as_of - timedelta(days=days)
    recent = [e for e in herd.events if e["animal_id"] in ids and since < e["event_date"] <= herd.as_of]
    health = Counter(e["std_event"] for e in recent if e["category"] == "health")
    health_cows = {k: len({e["animal_id"] for e in recent if e["std_event"] == k}) for k in health}
    groups = Counter("Heifer" if herd.status(c) == "heifer" else _lact_group(c) for c in cows)
    return {"pen": pen, "as_of": herd.as_of.isoformat(), "days": days, "summary": _pen_row(herd, cows, pen),
            "test": _test(milking, herd.milk_words),
            "lactation": [{"lactation": g, "cows": groups[g]} for g in ("Heifer", "1", "2", "3+") if groups[g]],
            "repro": repro_split([c for c in cows if herd.status(c) != "heifer"]),
            "dim": p10_50_90([c["days_in_milk"] for c in milking]),
            "health": [{"event": k.replace("_", " "), "events": v, "cows": health_cows[k]} for k, v in health.most_common()],
            "moved_in": len({e["animal_id"] for e in recent if e["std_event"] == "pen_move"}),
            "fresh_in": len({e["animal_id"] for e in recent if e["std_event"] == "calving"}),
            "source": herd.source_line()}


def cow_record(herd: Herd, cow, gestation: int = 280) -> dict:
    cow = str(cow).strip()
    hits = [c for c in herd.cows if c["animal_id"] == cow] or [c for c in herd.cows if c["cow_id"] == cow]
    if not hits:
        raise SystemExit(f"No cow {cow} in this herd.")
    hits.sort(key=lambda c: (bool(c.get("left_date")), -(c["left_date"].toordinal() if c.get("left_date") else 0)))
    me, others = hits[0], [c["animal_id"] for c in hits[1:]]
    status = herd.status(me)
    fresh = me.get("fresh_date")
    ev = sorted((e for e in herd.events if e["animal_id"] == me["animal_id"]), key=lambda e: e["event_date"])
    current = [e for e in ev if fresh and e["event_date"] >= fresh]
    timeline = []
    if fresh:
        timeline.append(("Calved", fresh))
    for i, e in enumerate([e for e in current if e["std_event"] == "breeding"], 1):
        timeline.append((f"Bred {i}", e["event_date"]))
    conceived = me.get("conception_date")
    pregnant = (me.get("repro_status") or "").upper() in ("PREG", "DRY") and conceived
    if pregnant:
        timeline.append(("Conceived", conceived))
    if status == "dry" and me.get("dry_date"):
        timeline.append(("Dried off", me["dry_date"]))
    if me.get("left_date"):
        timeline.append((f"Left the herd ({me.get('left_reason') or 'left'})", me["left_date"]))
    else:
        timeline.append(("Records end", herd.as_of))
        if pregnant:
            timeline.append(("Due", conceived + timedelta(days=gestation)))
    timeline.sort(key=lambda x: x[1])
    tests = []
    for key, label, unit in (("test_date", "Last test", ""), ("test_milk", "Milk", "lb"),
                             ("prev_test_milk", "Milk, previous test", "lb"), ("test_fat_pct", "Fat", "%"),
                             ("test_protein_pct", "Protein", "%"), ("test_mun", "MUN", "mg/dL"),
                             ("mun", "MUN", "mg/dL"), ("test_scc", "SCC", "x1000 cells/mL"),
                             ("prev_test_scc", "SCC, previous test", "x1000 cells/mL"),
                             ("daily_milk", "The day's milk", "lb"), ("body_condition_score", "Body condition", "")):
        v = me.get(key)
        if v is not None and not (key == "test_scc" and v == 0):
            tests.append({"measure": label, "value": v.isoformat() if hasattr(v, "isoformat") else v, "unit": unit})
    ecm = ecm_lb(me.get("test_milk"), me.get("test_fat_pct"), me.get("test_protein_pct"))
    if ecm:
        tests.append({"measure": "ECM (worked out here)", "value": round(ecm, 1), "unit": "lb"})
    return {"cow": me["cow_id"], "animal_id": me["animal_id"], "status": status, "pen": me.get("pen"),
            "lactation": me.get("lactation"), "days_in_milk": me.get("days_in_milk"), "as_of": herd.as_of.isoformat(),
            "timeline": [{"what": w, "date": d.isoformat(), "days_in_milk": (d - fresh).days if fresh else None}
                         for w, d in timeline],
            "tests": tests,
            "events_this_lactation": [{"date": e["event_date"].isoformat(), "days_in_milk": e.get("dim_at_event"),
                                       "event": e["dc_event"], "meaning": e["std_event"], "category": e["category"]}
                                      for e in current],
            "lactations": [{"lactation": l["lactation"], "fresh": l["fresh_date"].isoformat(),
                            "ended": l["end_date"].isoformat() if l["end_date"] else None, "how": l["end_reason"],
                            "services": l["services"], "days_open": l["days_open"]}
                           for l in herd.lactations if l["animal_id"] == me["animal_id"]],
            "number_also_used_by": others}
