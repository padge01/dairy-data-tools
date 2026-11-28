"""Udder health screen, DHI-302 SCC dynamics, and complete-month clinical mastitis incidence:
- `scc_screen`: latest-test SCC screen (>200k, SCS 5+ >=283k, NMC SCS bands, plus fresh cows' first test by parity)
- `scc_dynamics`: DHI-302 dynamics (new infections, chronic, cured, first-test infections, dry-period 4-way table,
  dry-period cure/new-infection rates, and infected at dry-off), overall or by parity
- `mastitis_incidence`: clinical mastitis per 100 cows in milk per complete calendar month (one case per cow per day,
  excluding dry cows, optional `first_only`, and exact Poisson 95% CI when `by="none"`)

100% Python standard library only.
"""

from __future__ import annotations

import math
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from .errors import DairyToolsError, MissingDataError
from .explorer import pen_order
from .herd import Herd
from .stats import linear_score, mean, pct, poisson_ci, share


def _clamped_ls(scc: float) -> float:
    return min(9.0, max(0.0, math.log2(max(scc, 1.0) / 100.0) + 3.0))


def _cow_scc(cow) -> float | None:
    scc = cow.get("test_scc")
    if scc is not None and scc > 0:
        return float(scc)
    # Only fall back to dc_linear_score when raw test_scc is absent (not 0 = untested).
    if scc is None:
        ls = cow.get("dc_linear_score")
        if ls is not None and ls > 0:
            return 100.0 * (2.0 ** (float(ls) - 3.0))
    return None


def _cow_ls(cow, ls_key: str, scc_key: str | None = None) -> float | None:
    """Linear score for DHI-302 dynamics: uses DairyComp's test-day card linear score when exported (matching
    the R version's `scc_dynamics()` and required for `DRYLG` which has no raw SCC counterpart), ignoring 0 when raw SCC is 0
    (untested), and falling back to `log2(SCC / 100) + 3` when linear score columns are absent."""
    if scc_key is not None and cow.get(scc_key) == 0:
        return None
    v = cow.get(ls_key)
    if v is not None:
        return float(v)
    if scc_key is not None:
        scc = cow.get(scc_key)
        if scc is not None and scc > 0:
            return linear_score(float(scc))
    return None


def _scc_row(sccs: list[float], cows_label: str, group: str) -> dict[str, Any]:
    n = len(sccs)
    scs_vals = [_clamped_ls(s) for s in sccs]
    over_200 = sum(1 for s in sccs if s > 200)
    scs5 = sum(1 for s in sccs if s >= 283)
    return {
        "cows": cows_label,
        "group": group,
        "tested": n,
        "over_200k_cells_ml": over_200,
        "share_over_200k_cells_ml": share(over_200, n),
        "scs_5_plus_283k_cells_ml": scs5,
        "share_scs_5_plus_283k_cells_ml": share(scs5, n),
        "mean_scs": round(mean(scs_vals), 2) if scs_vals else None,
        "scs_0_3_under_141k": share(sum(1 for s in sccs if s < 141), n),
        "scs_4_141_282k": share(sum(1 for s in sccs if 141 <= s < 283), n),
        "scs_5_283_565k": share(sum(1 for s in sccs if 283 <= s < 566), n),
        "scs_6_plus_566k_up": share(sum(1 for s in sccs if s >= 566), n),
    }


def scc_screen(herd: Herd, by: str = "none", fresh_dim: int = 40) -> dict[str, Any]:
    """Latest-test somatic cell count screen (overall, by parity, or by pen) plus fresh cows' first test by parity."""
    if by not in ("none", "parity", "pen"):
        raise DairyToolsError(f"by must be 'none', 'parity', or 'pen', got {by!r}")
    has_scc = any(c.get("test_scc") is not None or c.get("dc_linear_score") is not None for c in herd.cows)
    if not has_scc:
        raise MissingDataError("This herd has no SCC column. Re-export the cow report with the SCC item.")

    end = herd.data_end
    has_test_date = any(c.get("test_date") is not None for c in herd.cows)
    cutoff = end - timedelta(days=45)

    tested: list[tuple[Any, float]] = []
    for c in herd.in_herd():
        if herd.status(c) != "milking":
            continue
        if has_test_date and (c.get("test_date") is None or c["test_date"] < cutoff):
            continue
        scc = _cow_scc(c)
        if scc is not None:
            tested.append((c, scc))

    if not tested:
        raise MissingDataError("No milking cow has a test SCC.")

    grouped: dict[str, list[float]] = defaultdict(list)
    fresh_grouped: dict[str, list[float]] = defaultdict(list)
    for c, scc in tested:
        parity = "1" if c.get("lactation") == 1 else "2+"
        if by == "none":
            g = "all"
        elif by == "parity":
            g = parity
        else:
            g = c.get("pen") or "No pen"
        grouped[g].append(scc)
        if c.get("days_in_milk") is not None and c["days_in_milk"] <= fresh_dim:
            fresh_grouped[parity].append(scc)

    order = pen_order(grouped) if by == "pen" else sorted(grouped)
    rows = [_scc_row(grouped[g], "all tested", g) for g in order]
    fresh_label = f"fresh, first test ({fresh_dim} DIM or less)"
    for p in sorted(fresh_grouped):
        rows.append(_scc_row(fresh_grouped[p], fresh_label, p))

    definition = (
        f"Milking cows in the herd at {herd.as_of or end} (not dry) with a test this lactation (within 45 days of "
        f"{end} when test dates exist): each cow's latest test, SCC in x1000 cells/mL. Over 200k: SCC above 200 "
        f"(LS above 4). SCS 5+: SCC 283 or more (NMC's SCS classes: 0-3 under 141, 4 141-282, 5 283-565, 6+ 566 up). "
        f"Fresh: {fresh_dim} DIM or less now, so the latest test is the first of the lactation."
    )
    return {
        "by": by,
        "fresh_dim": fresh_dim,
        "rows": rows,
        "definition": definition,
        "source": herd.source_line(),
    }


def scc_dynamics(herd: Herd, by: str = "none") -> dict[str, Any]:
    """DHI-302 udder-health dynamics at the latest herd test, overall (`by="none"`) or by parity (`by="parity"`)."""
    if by not in ("none", "parity"):
        raise DairyToolsError(f"by must be 'none' or 'parity', got {by!r}")

    used_dc_ls = False
    eligible = []
    for c in herd.in_herd():
        td = c.get("test_date")
        now_ls = _cow_ls(c, "dc_linear_score", "test_scc")
        if td is not None and now_ls is not None and c.get("fresh_date") is not None and c.get("lactation") is not None:
            if c.get("dc_linear_score") is not None:
                used_dc_ls = True
            eligible.append((c, td, now_ls))

    if not eligible:
        raise MissingDataError(
            "No cow in the herd has a test date and SCC / linear score. Export the test-day summary card "
            "(TDAT, SCC/LGSCC, PSCC/PRVLG, SCC1/LOG1, DRYLG, FTDIM) for full udder dynamics."
        )

    latest = max(td for _, td, _ in eligible)
    window_start = latest - timedelta(days=3)
    cows_at_test = [(c, td, now_ls) for c, td, now_ls in eligible if td >= window_start]

    records = []
    for c, td, now_ls in cows_at_test:
        prev_ls = _cow_ls(c, "dc_prev_linear_score", "prev_test_scc")
        first_ls = _cow_ls(c, "dc_first_linear_score", "first_test_scc")
        dry_ls = _cow_ls(c, "dc_dry_off_linear_score", None)
        heifer = c["lactation"] == 1
        fresh = c["fresh_date"]
        dim_at_test = (td - fresh).days
        first_dim = c.get("first_test_dim")
        latest_is_first = (dim_at_test <= 35) if first_dim is None else (dim_at_test <= first_dim)
        both = (prev_ls is not None) and (not latest_is_first)
        recent = (latest - timedelta(days=120)) <= fresh <= latest
        dry_set = recent and (not heifer) and (dry_ls is not None) and (first_ls is not None)
        grp = ("1" if heifer else "2+") if by == "parity" else "all"
        records.append({
            "group": grp,
            "now": now_ls,
            "prev": prev_ls,
            "first": first_ls,
            "dry": dry_ls,
            "heifer": heifer,
            "both": both,
            "recent": recent,
            "dry_set": dry_set,
        })

    specs = (
        ("infected_now", "LS 4+ (200000+ cells/mL) at the latest test",
         lambda r: r["now"] >= 4, lambda r: True),
        ("scs5_now", "LS 5+ (about 283000+) at the latest test",
         lambda r: r["now"] >= 5, lambda r: True),
        ("new_infection", "New infections: LS 4+ now, of cows under 4 at the previous test",
         lambda r: r["now"] >= 4, lambda r: r["both"] and r["prev"] < 4),
        ("chronic", "Chronic: LS 4+ at both tests, of cows with both tests",
         lambda r: r["prev"] >= 4 and r["now"] >= 4, lambda r: r["both"]),
        ("cured", "Cured: under 4 now, of cows at 4+ at the previous test",
         lambda r: r["now"] < 4, lambda r: r["both"] and r["prev"] >= 4),
        ("first_test_heifers", "First test LS 4+, heifers calved in the last 120 days",
         lambda r: r["first"] >= 4, lambda r: r["recent"] and r["heifer"] and r["first"] is not None),
        ("first_test_cows", "First test LS 4+, cows (2+) calved in the last 120 days",
         lambda r: r["first"] >= 4, lambda r: r["recent"] and (not r["heifer"]) and r["first"] is not None),
        ("dry_healthy", "Dry period: stayed healthy (under 4 at dry-off and first test)",
         lambda r: r["dry"] < 4 and r["first"] < 4, lambda r: r["dry_set"]),
        ("dry_cured", "Dry period: cured (4+ at dry-off, under 4 at first test)",
         lambda r: r["dry"] >= 4 and r["first"] < 4, lambda r: r["dry_set"]),
        ("dry_new", "Dry period: new infection (under 4 at dry-off, 4+ at first test)",
         lambda r: r["dry"] < 4 and r["first"] >= 4, lambda r: r["dry_set"]),
        ("dry_chronic", "Dry period: chronic (4+ at dry-off and first test)",
         lambda r: r["dry"] >= 4 and r["first"] >= 4, lambda r: r["dry_set"]),
        ("dry_cure_rate", "Dry-period cure rate: under 4 at first test, of cows 4+ at dry-off",
         lambda r: r["first"] < 4, lambda r: r["dry_set"] and r["dry"] >= 4),
        ("dry_new_rate", "Dry-period new infection rate: 4+ at first test, of cows under 4 at dry-off",
         lambda r: r["first"] >= 4, lambda r: r["dry_set"] and r["dry"] < 4),
        ("infected_at_dry_off", "Infected at dry-off: LS 4+ at the last test before dry-off",
         lambda r: r["dry"] >= 4, lambda r: r["dry_set"]),
    )

    only_older = {
        "first_test_cows", "dry_healthy", "dry_cured", "dry_new", "dry_chronic",
        "dry_cure_rate", "dry_new_rate", "infected_at_dry_off",
    }

    groups = sorted({r["group"] for r in records})
    rows = []
    for g in groups:
        sub = [r for r in records if r["group"] == g]
        for key, measure, cond, denom in specs:
            if g == "1" and key in only_older:
                continue
            if g == "2+" and key == "first_test_heifers":
                continue
            in_denom = [r for r in sub if denom(r)]
            n_of = len(in_denom)
            n = sum(1 for r in in_denom if cond(r))
            rows.append({
                "key": key,
                "measure": measure,
                "group": g,
                "cows": n,
                "of": n_of,
                "share": share(n, n_of),
                "percent": pct(n, n_of, 1) if n_of else None,
            })

    ls_note = ("Linear scores from the test-day summary card (LGSCC/PRVLG/LOG1/DRYLG; LS >= 4 = 200,000+ cells/mL)."
               if used_dc_ls else "Linear scores computed from raw SCC (log2(SCC / 100) + 3; LS >= 4 = 200,000+ cells/mL).")
    definition = (
        f"Cows in the herd tested at the latest herd test ({latest}). {ls_note} New infections, chronic and cured "
        f"compare each cow's latest test with her previous test this lactation (fresh cows with one test so far are "
        f"left out). First-test and dry-period rows: cows that calved in the 120 days before the test."
    )
    return {
        "by": by,
        "latest_test": latest.isoformat(),
        "rows": rows,
        "definition": definition,
        "source": herd.source_line(),
    }


def mastitis_incidence(
    herd: Herd,
    by: str = "month",
    first_only: bool = False,
    months: int | None = 12,
) -> dict[str, Any]:
    """Clinical mastitis per 100 cows in milk per complete calendar month.

    Counts at most one case per cow per day (or first case per lactation when `first_only=True`), excludes cases on
    dry cows, uses exact interval overlap for cow-days in milk, and computes an exact Poisson 95% CI when `by="none"`.
    """
    if by not in ("month", "none"):
        raise DairyToolsError(f"by must be 'month' or 'none', got {by!r}")
    if not herd.events_from:
        raise MissingDataError("No events in these records.")
    end = herd.data_end
    start = herd.events_from

    # First and last complete calendar months covered by [start, end].
    first_y, first_m = start.year, start.month
    if start.day > 1:
        first_y, first_m = (first_y + 1, 1) if first_m == 12 else (first_y, first_m + 1)
    last_y, last_m = end.year, end.month
    if end.day < monthrange(last_y, last_m)[1]:
        last_y, last_m = (last_y - 1, 12) if last_m == 1 else (last_y, last_m - 1)
    if (last_y, last_m) < (first_y, first_m):
        raise MissingDataError("The records do not cover a complete month.")

    windows: list[tuple[str, date, date, int]] = []
    y, m = first_y, first_m
    while (y, m) <= (last_y, last_m):
        n_days = monthrange(y, m)[1]
        windows.append((f"{y}-{m:02d}", date(y, m, 1), date(y, m, n_days), n_days))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    if months is not None:
        windows = windows[-months:]

    lacts = [
        (l["animal_id"], l["lactation"], l["fresh_date"], l["end_date"] or end)
        for l in herd.lactations
        if (l["lactation"] or 0) >= 1 and l["fresh_date"] is not None
    ]
    lact_map = {(aid, lact): (fresh, stop) for aid, lact, fresh, stop in lacts}

    # Exact cow-days in milk per month via interval overlap.
    cow_months_by_m: list[float] = []
    for _, m_start, m_end, n_days in windows:
        cd = 0
        for _, _, fresh, stop in lacts:
            if stop < m_start or fresh > m_end:
                continue
            lo = fresh if fresh > m_start else m_start
            hi = stop if stop < m_end else m_end
            if hi >= lo:
                cd += (hi - lo).days + 1
        cow_months_by_m.append(cd / n_days)

    # Deduplicate clinical_mastitis on (animal_id, event_date), match to lactation, exclude dry-cow cases.
    first_win, last_win = windows[0][1], windows[-1][2]
    seen_day: set[tuple[str, date]] = set()
    in_milk_events: list[tuple[str, int, date]] = []
    dry_cases = 0
    for e in sorted(herd.events_by_std.get("clinical_mastitis", ()), key=lambda ev: ev["event_date"]):
        if e["event_date"] is None or e.get("lactation") is None:
            continue
        day_key = (e["animal_id"], e["event_date"])
        if day_key in seen_day:
            continue
        seen_day.add(day_key)
        span = lact_map.get((e["animal_id"], e["lactation"]))
        if span is None:
            continue
        fresh, stop = span
        if fresh <= e["event_date"] <= stop:
            in_milk_events.append((e["animal_id"], e["lactation"], e["event_date"]))
        elif first_win <= e["event_date"] <= last_win:
            dry_cases += 1

    if first_only:
        seen_lact: set[tuple[str, int]] = set()
        deduped = []
        for aid, lact, d in in_milk_events:
            if (aid, lact) not in seen_lact:
                seen_lact.add((aid, lact))
                deduped.append((aid, lact, d))
        in_milk_events = deduped

    cases_by_m = [sum(1 for _, _, d in in_milk_events if m_start <= d <= m_end) for _, m_start, m_end, _ in windows]

    label = "First clinical mastitis case of each lactation" if first_only else "Clinical mastitis cases"
    dry_note = f" {dry_cases} case(s) on dry cows left out." if dry_cases else ""
    definition = (
        f"{label} on cows in milk (one per cow per day) / average cows in milk that month (cow-days in milk / days "
        f"in the month) x 100. Complete months {windows[0][0]} to {windows[-1][0]}; the data end on {end}.{dry_note}"
    )

    if by == "month":
        rows = [
            {
                "month": m_key,
                "cases": k,
                "cows_in_milk": round(cm, 1),
                "per_100_cows": round(100 * k / cm, 1) if cm > 0 else None,
            }
            for (m_key, _, _, _), k, cm in zip(windows, cases_by_m, cow_months_by_m)
        ]
        return {"by": by, "first_only": first_only, "rows": rows, "definition": definition, "source": herd.source_line()}

    k_tot = sum(cases_by_m)
    cm_tot = sum(cow_months_by_m)
    lo, hi = poisson_ci(k_tot, cm_tot)
    summary = {
        "from": windows[0][0],
        "to": windows[-1][0],
        "months": len(windows),
        "cases": k_tot,
        "cow_months": round(cm_tot, 1),
        "per_100_cows_per_month": round(100 * k_tot / cm_tot, 2) if cm_tot > 0 else None,
        "ci_low": round(100 * lo, 2) if lo is not None else None,
        "ci_high": round(100 * hi, 2) if hi is not None else None,
    }
    return {"by": by, "first_only": first_only, "summary": summary, "definition": definition, "source": herd.source_line()}
