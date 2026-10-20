"""Pen cows to pen feed, and the feeding checks. The Rossow lab's pen_dmi, feed_efficiency, iofc, refusals,
feeding_consistency and loading_accuracy in Python.

Every figure is compared with the same pen's own previous weeks; published ranges appear only as a cited line, never
as a verdict. DairyComp's head count is the denominator for the pen (EZfeed's own counts can be well off). "Fed" is
what was delivered, not what was eaten, unless refusals are weighed.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import timedelta

from .herd import Herd
from .stats import ecm_lb, mean, median, p10_50_90

KG = 0.45359237


def _window(rows, days, end=None):
    dates = [r["date"] for r in rows if r.get("date")]
    if not dates:
        return [], None, None
    end = end or max(dates)
    start = end - timedelta(days=days - 1)
    return [r for r in rows if r.get("date") and start <= r["date"] <= end], start, end


def nasem_dmi(milk, fat_pct, protein_pct, body_weight, bcs, dim, lactation, lactose_pct=4.85):
    """NASEM (2021) equation 2-1, predicted dry matter intake of a lactating cow, lb a day."""
    ne_milk = 9.29 * fat_pct / 100 + 5.85 * protein_pct / 100 + 3.95 * lactose_pct / 100
    p = 0 if lactation <= 1 else 1
    kg = (3.7 + 5.7 * p + 0.305 * ne_milk * milk * KG + 0.022 * body_weight * KG + (-0.689 - 1.87 * p) * bcs) * \
        (1 - (0.212 + 0.136 * p) * math.exp(-0.053 * max(dim, 1)))
    return kg / KG


def _milking_tested(herd: Herd, pen=None):
    out = []
    for c in herd.in_herd():
        if herd.status(c) != "milking" or not (c.get("test_milk") or 0) > 0:
            continue
        if pen is not None and c["pen"] != pen:
            continue
        out.append(c)
    return out


def _pen_feed_days(herd: Herd):
    """Each EZfeed pen's days: DM and cost per head and EZfeed's head count, from the Pen Summary when the farm sent
    it, else the ingredient intake report summed over its feeds (premix lines once)."""
    if herd.feed.get("feed_pen_days"):
        rows = [dict(r, source="Pen Summary") for r in herd.feed["feed_pen_days"]
                if (r.get("dm_lb_per_head") or 0) > 0 and (r.get("head_count") or 0) > 0]
        return rows
    days = defaultdict(lambda: {"dm_lb_per_head": 0.0, "cost_per_head": 0.0, "target_dm": 0.0})
    meta = {}
    for r in herd.feed.get("feed_delivery", []):
        if r.get("premix"):
            continue
        k = (r["pen"], r["date"])
        meta[k] = r.get("dc_pen")
        d = days[k]
        d["dm_lb_per_head"] += r.get("actual_dm_lb_per_head") or 0
        d["cost_per_head"] += r.get("actual_cost_per_head") or 0
        d["target_dm"] += r.get("target_dm_lb_per_head") or 0
    return [{"pen": p, "date": dt, "dc_pen": meta[(p, dt)], "life_stage": None, "head_count": None,
             "source": "Ingredient Intake", **v} for (p, dt), v in days.items() if v["dm_lb_per_head"] > 0]


def pen_feed(herd: Herd, days: int = 7, milk_price: float | None = None, pen=None) -> dict:
    """Each DairyComp pen joined to its EZfeed pen: cows, milk and ECM spread at the last test, dry matter fed and
    feed cost per cow, ECM per lb DM, feed cost per cwt, IOFC at the milk price given, NASEM's predicted intake for
    the cows in it, and the same figures for the days before, to compare the pen with itself."""
    feed_days = _pen_feed_days(herd)
    if not feed_days:
        raise SystemExit("No EZfeed Pen Summary or Ingredient Intake report in the folder: pen feed needs one.")
    rows_by_pen = defaultdict(list)
    for r in feed_days:
        if r.get("dc_pen"):
            rows_by_pen[r["dc_pen"]].append(r)
    live = herd.in_herd()
    out = []
    for dc_pen, rows in sorted(rows_by_pen.items(), key=lambda x: (len(x[0]), x[0])):
        if pen is not None and dc_pen != str(pen):
            continue
        heads = sum(1 for c in live if c["pen"] == dc_pen)
        if not heads:
            continue
        now, start, end = _window(rows, days)
        before, b_start, b_end = _window(rows, days, start - timedelta(days=1)) if start else ([], None, None)

        def per_cow(rs, key):
            if not rs:
                return None
            if rs[0].get("head_count"):   # Pen Summary: EZfeed's total over DairyComp's count
                return mean([r[key] * r["head_count"] for r in rs]) / heads
            return mean([r[key] for r in rs])   # Ingredient Intake: per EZfeed head only

        cows = _milking_tested(herd, dc_pen)
        milk = [c["test_milk"] for c in cows]
        ecm = [e for e in (ecm_lb(c["test_milk"], c.get("test_fat_pct"), c.get("test_protein_pct")) for c in cows)
               if e is not None]
        dmi, cost = per_cow(now, "dm_lb_per_head"), per_cow(now, "cost_per_head")
        dmi_b, cost_b = per_cow(before, "dm_lb_per_head"), per_cow(before, "cost_per_head")
        mean_milk, mean_ecm = mean(milk), mean(ecm)
        predicted = None
        usable = [c for c in cows if c.get("days_in_milk") is not None and c.get("lactation")]
        if usable:
            predicted = mean([nasem_dmi(c["test_milk"], c.get("test_fat_pct") or 3.9, c.get("test_protein_pct") or 3.15,
                                        c.get("body_weight") or (1350 if c["lactation"] <= 1 else 1550),
                                        c.get("body_condition_score") or 3, c["days_in_milk"], c["lactation"])
                              for c in usable])
        ez_heads = mean([r["head_count"] for r in now if r.get("head_count")])
        row = {"pen": dc_pen, "ezfeed_pen": rows[0]["pen"], "source": rows[0]["source"],
               "days": f"{start} to {end}", "cows": heads, "tested": len(cows),
               "ezfeed_head_count": round(ez_heads) if ez_heads else None,
               "milk_lb": p10_50_90(milk), "milk_mean_lb": mean_milk, "ecm_mean_lb": mean_ecm,
               "dmi_lb_per_cow": dmi, "dmi_before": dmi_b,
               "feed_cost_per_cow": cost, "feed_cost_before": cost_b,
               "ecm_per_lb_dm": mean_ecm / dmi if mean_ecm and dmi else None,
               "feed_cost_per_cwt": 100 * cost / mean_milk if cost and mean_milk else None,
               "nasem_predicted_dmi": predicted,
               "fed_vs_predicted_pct": 100 * (dmi - predicted) / predicted if dmi and predicted else None,
               "notes": []}
        if milk_price is not None and mean_milk and cost is not None:
            row["milk_income_per_cow"] = milk_price * mean_milk / 100
            row["iofc_per_cow"] = row["milk_income_per_cow"] - cost
        if ez_heads and abs(ez_heads / heads - 1) > 0.05:
            row["notes"].append(f"EZfeed counts {round(ez_heads)} head; DairyComp has {heads}. Per cow uses "
                                "DairyComp's count.")
        if rows[0]["source"] == "Ingredient Intake":
            row["notes"].append("From the Ingredient Intake report: per EZfeed head (the Pen Summary would give the "
                                "head count to correct it).")
        if not cows:
            row["notes"].append("No milking cow in the pen has a test: no milk, ECM or efficiency.")
        out.append(row)
    return {"pens": out, "days": days, "milk_price": milk_price, "source": herd.source_line(),
            "definitions": [
                "ECM from each cow's last test (0.327 x milk + 12.95 x fat lb + 7.65 x protein lb); one test day "
                "against a window of feeding.",
                "Dry matter fed is delivered, not eaten, unless refusals are weighed.",
                "Predicted intake: NASEM (2021) equation 2-1 for the cows in the pen now; body weight 1,550 lb "
                "(1,350 first lactation) and body condition 3 where the farm doesn't record them.",
                "Feed cost per cwt = feed cost per cow / milk lb x 100. IOFC = milk price x milk lb / 100 - feed "
                "cost per cow."],
            "reference_lines": ["Penn State and Cornell suggest sampling the TMR when ECM per lb DM falls below "
                                "about 1.45 (cited for context, not a target)."]}


def loading_accuracy(herd: Herd, by: str = "ingredient", days: int | None = None) -> dict:
    """Fed against called for: each feed's (or pen's) mean deviation (a steady over- or under-load) and its day-to-day
    spread, in lb and %; by feeder from the FeederLoad Summary. Premix lines once."""
    if by == "feeder":
        loads = [l for l in herd.feed.get("feed_loads", []) if l.get("deviation_pct") is not None and l.get("feeder")]
        if not loads:
            raise SystemExit("No FeederLoad Summary in the folder.")
        groups = defaultdict(list)
        for l in loads:
            groups[l["feeder"]].append(l)
        rows = []
        for f, ls in groups.items():
            w = [l.get("loads") or 1 for l in ls]
            dev = sum(abs(l["deviation_pct"]) * x for l, x in zip(ls, w)) / sum(w)
            rows.append({"feeder": f, "days": len({l["date"] for l in ls}), "loads": sum(w),
                         "mean_abs_deviation_pct": dev})
        rows.sort(key=lambda r: -r["mean_abs_deviation_pct"])
        return {"by": "feeder", "rows": rows, "reference_lines": ["1-2% is achievable (Kluth), cited for context."]}
    d = [r for r in herd.feed.get("feed_delivery", []) if not r.get("premix") and (r.get("target_dm_lb_per_head") or 0) > 0
         and r.get("actual_dm_lb_per_head") is not None]
    if not d:
        raise SystemExit("No Ingredient Intake Tgt vs Act by Pen report in the folder.")
    if days:
        d, _, _ = _window(d, days)
    if by == "pen":
        agg = defaultdict(lambda: [0.0, 0.0])
        for r in d:
            agg[(r["pen"], r["date"])][0] += r["target_dm_lb_per_head"]
            agg[(r["pen"], r["date"])][1] += r["actual_dm_lb_per_head"]
        d = [{"pen": p, "date": dt, "target_dm_lb_per_head": t, "actual_dm_lb_per_head": a} for (p, dt), (t, a) in agg.items()]
    groups = defaultdict(list)
    for r in d:
        groups[r[by]].append(r)
    rows = []
    for g, rs in groups.items():
        dev = [100 * (r["actual_dm_lb_per_head"] - r["target_dm_lb_per_head"]) / r["target_dm_lb_per_head"] for r in rs]
        lb = [r["actual_dm_lb_per_head"] - r["target_dm_lb_per_head"] for r in rs]
        m = sum(dev) / len(dev)
        sd = math.sqrt(sum((x - m) ** 2 for x in dev) / (len(dev) - 1)) if len(dev) > 1 else None
        rows.append({by: g, "days": len({r["date"] for r in rs}), "target_lb": mean(r["target_dm_lb_per_head"] for r in rs),
                     "fed_lb": mean(r["actual_dm_lb_per_head"] for r in rs), "mean_deviation_pct": m,
                     "mean_deviation_lb": sum(lb) / len(lb), "sd_deviation_pct": sd,
                     "mean_abs_deviation_pct": sum(abs(x) for x in dev) / len(dev)})
    rows.sort(key=lambda r: -abs(r["mean_deviation_pct"]))
    return {"by": by, "rows": rows,
            "definitions": ["Deviation = (fed - called for) / called for, each day; mean = a steady miss, spread = "
                            "how much it wanders day to day. Dry matter, lb per EZfeed head."],
            "reference_lines": ["UC Davis, 26 California dairies: 46% of loads missed by more than 2%; hay, corn "
                                "silage and canola were loaded worst (cited for context)."]}


def refusals(herd: Herd, days: int = 7) -> dict:
    """Refused as a share of delivered (both as fed), pounds over pounds, for the last days and the days before.
    All-zero refusals mean the farm doesn't weigh them, never zero."""
    r = [x for x in herd.feed.get("feed_refusals", []) if x.get("refusal_pct") is not None
         and x.get("refusal_as_fed_lb") is not None]
    if not r:
        raise SystemExit("No Refusal Summary in the folder.")
    if all((x["refusal_as_fed_lb"] or 0) == 0 for x in r):
        return {"rows": [], "note": "Every refusal in the report is zero: the farm doesn't weigh refusals here, so "
                                    "'fed' is delivered, not eaten."}
    by_pen = defaultdict(list)
    for x in r:
        by_pen[x["pen"]].append(x)
    rows = []
    for pen, xs in by_pen.items():
        usual = mean([x["refusal_as_fed_lb"] * 100 / x["refusal_pct"] for x in xs if x["refusal_pct"] > 0])

        def share(sub):
            if not sub:
                return None
            refused = sum(x["refusal_as_fed_lb"] for x in sub)
            delivered = sum(x["refusal_as_fed_lb"] * 100 / x["refusal_pct"] if x["refusal_pct"] > 0 else (usual or 0)
                            for x in sub)
            return 100 * refused / delivered if delivered else None

        now, start, end = _window(xs, days)
        before, _, _ = _window(xs, days, start - timedelta(days=1))
        rows.append({"pen": pen, "dc_pen": xs[0].get("dc_pen"), "days": f"{start} to {end}",
                     "refusal_pct": share(now), "refusal_pct_before": share(before)})
    return {"rows": rows, "definitions": ["lb refused / lb delivered, as fed, over the days (not an average of daily "
                                          "percentages); delivered worked back from each day's lb and %."],
            "reference_lines": ["Penn State and Minnesota give about 1-3% for high cows, 0.5-3% for low and dry, "
                                "near 5% for transition (cited for context)."]}


def consistency(herd: Herd, days: int = 14) -> dict:
    """Day to day: how much DM per head changed between consecutive days, and how regular the first feeding was."""
    pd = [r for r in herd.feed.get("feed_pen_days", []) if (r.get("dm_lb_per_head") or 0) > 0
          and (r.get("head_count") or 0) > 0]
    if not pd:
        raise SystemExit("No Pen Summary in the folder.")
    by_pen = defaultdict(list)
    for r in pd:
        by_pen[r["pen"]].append(r)
    rows = []
    for pen, rs in by_pen.items():
        rs, start, end = _window(rs, days)
        rs.sort(key=lambda r: r["date"])
        changes = [abs(b["dm_lb_per_head"] - a["dm_lb_per_head"]) for a, b in zip(rs, rs[1:])
                   if (b["date"] - a["date"]).days == 1]
        times = [int(t[:2]) * 60 + int(t[3:]) for t in (r.get("last_unload_time") for r in rs) if t]
        usual = round(median(times)) if times else None
        rows.append({"pen": pen, "dc_pen": rs[0].get("dc_pen") if rs else None, "days": f"{start} to {end}",
                     "mean_change_lb": mean(changes), "max_change_lb": max(changes) if changes else None,
                     "changes_over_2_lb": sum(1 for c in changes if c > 2),
                     "usual_feed_time": f"{usual // 60:02d}:{usual % 60:02d}" if usual is not None else None,
                     "share_within_10_min": (sum(1 for t in times if abs(t - usual) <= 10) / len(times)) if times else None})
    return {"rows": rows, "definitions": ["|DM per head today - yesterday|, consecutive days only; feeding time is "
                                          "EZfeed's earliest unload end."],
            "reference_lines": ["Advisers aim for changes within 1-2 lb DM per head a day (Kluth; Silva-del-Rio), "
                                "cited for context."]}
