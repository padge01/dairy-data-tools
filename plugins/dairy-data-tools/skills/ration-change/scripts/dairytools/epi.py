"""Transition-cow, culling, and epidemiology analyses plus record-only extensions:
- `lactation_data`: analysis-ready cow-lactation table
- `risk_ratio`: 2x2 RR/OR with 95% Taylor-series CIs and chi-square / Fisher's exact p-value
- `mantel_haenszel_rr`: parity-stratified Mantel-Haenszel pooled RR with 95% CI and MH p-value (beyond R)
- `dry_periods`, `dry_band`, `dry_period_length`: completed dry period lengths and distribution bands
- `fresh_disease_effects`: milk at first test (within parity), early removal RR, and days open / KM median to conception
- `left_reasons`: annual cull & death rates per 100 cow-years using exact day-by-day cow spells
- `left_herd`: share of lactations ending sold or died within X DIM with Wilson 95% CI
- `event_months`: first cases per lactation by calendar month or year-month with chi-square seasonality test
- `herd_survival`: Kaplan-Meier herd survival (not sold/died) to 60, 150, 305 DIM by parity (beyond R)
- `calving_outcomes`: calving ease, calf sex, twinning, and gestation length from raw records (beyond R)
- `audit_records`: data-quality audit (breedings before calving, preg without breeding, DIM mismatches, lact jumps)

100% Python standard library only.
"""

from __future__ import annotations

import math
import re
from calendar import month_abbr
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from .errors import DairyToolsError, MissingDataError, NotFoundError
from .herd import Herd, _is_restated_breeding
from .stats import (
    Z_95,
    chisq_contingency,
    chisq_goodness_of_fit,
    fisher_exact_2x2,
    kaplan_meier,
    km_median,
    kruskal_wallis,
    logrank_test,
    mantel_haenszel_rr as _mh_rr,
    mean,
    median,
    poisson_ci,
    quantile,
    share,
    signif,
    wilcoxon_ranksum,
    wilson,
)

MONTH_ABBR = [month_abbr[i] for i in range(1, 13)]
SEASONS = ("winter", "spring", "summer", "fall")
_MONTH_TO_SEASON = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "fall", 10: "fall", 11: "fall",
}
SAFE_EXIT_CODE = re.compile(r"^[A-Za-z0-9_-]{1,12}$")


def calving_period(d: date, by: str) -> str:
    """Calendar month abbreviation (Jan..Dec) or northern-hemisphere season (winter/spring/summer/fall)."""
    if by == "calving_month":
        return MONTH_ABBR[d.month - 1]
    if by == "calving_season":
        return _MONTH_TO_SEASON[d.month]
    raise DairyToolsError(f"by must be 'calving_month' or 'calving_season', got {by!r}")


# --- dry period length -----------------------------------------------------------------------------------------------

def dry_band(days: int | float | None) -> str | None:
    """Group a dry period length (days) into the standard bands: under 30, 30-39, 40-60, 61-80, over 80."""
    if days is None or not math.isfinite(days):
        return None
    if days <= 29:
        return "under 30"
    if days <= 39:
        return "30-39"
    if days <= 60:
        return "40-60"
    if days <= 80:
        return "61-80"
    return "over 80"


def dry_periods(herd: Herd) -> list[dict[str, Any]]:
    """One row per completed dry period: the dry-off in lactation n-1 and the calving starting lactation n."""
    dried: dict[tuple[str, int], date] = {}
    for l in herd.lactations:
        if l["end_reason"] == "dried off" and l["end_date"] is not None and l["lactation"] is not None:
            dried[(l["animal_id"], l["lactation"])] = l["end_date"]
    latest_ev: dict[tuple[str, int], date] = {}
    for e in herd.events_by_std.get("dry_off", ()):
        lact = e.get("lactation")
        if lact is None:
            continue
        k = (e["animal_id"], lact)
        if k not in latest_ev or e["event_date"] > latest_ev[k]:
            latest_ev[k] = e["event_date"]
    for k, d in latest_ev.items():
        dried.setdefault(k, d)

    out: list[dict[str, Any]] = []
    for l in herd.lactations:
        lact = l.get("lactation")
        if lact is None or lact < 2 or l["fresh_date"] is None:
            continue
        dry_date = dried.get((l["animal_id"], lact - 1))
        if dry_date is None:
            continue
        days = (l["fresh_date"] - dry_date).days
        if days < 0:
            continue
        out.append({
            "animal_id": l["animal_id"],
            "lactation": lact,
            "dry_date": dry_date,
            "fresh_date": l["fresh_date"],
            "dry_days": days,
            "band": dry_band(days),
        })
    out.sort(key=lambda r: (r["fresh_date"], r["animal_id"]))
    return out


def dry_period_length(herd: Herd, by: str = "none") -> dict[str, Any]:
    """Completed dry period lengths, overall (`by="none"`) or by lactation calved into (`by="parity"`: `"2"` vs `"3+"`)."""
    if by not in ("none", "parity"):
        raise DairyToolsError(f"by must be 'none' or 'parity', got {by!r}")
    dp = dry_periods(herd)
    if not dp:
        raise MissingDataError("No completed dry periods (a dry-off and then the next calving) in these records.")
    grouped: dict[str, list[int]] = defaultdict(list)
    for r in dp:
        g = ("3+" if r["lactation"] >= 3 else "2") if by == "parity" else "all"
        grouped[g].append(r["dry_days"])
    rows = []
    for lv in sorted(grouped):
        ds = grouped[lv]
        n = len(ds)
        rows.append({
            "group": lv,
            "n": n,
            "median": median(ds),
            "mean": round(mean(ds), 1),
            "share_under_30": share(sum(1 for d in ds if d < 30), n),
            "share_30_39": share(sum(1 for d in ds if 30 <= d <= 39), n),
            "share_40_60": share(sum(1 for d in ds if 40 <= d <= 60), n),
            "share_61_80": share(sum(1 for d in ds if 61 <= d <= 80), n),
            "share_over_80": share(sum(1 for d in ds if d > 80), n),
        })
    first_fresh = min(r["fresh_date"] for r in dp)
    last_fresh = max(r["fresh_date"] for r in dp)
    definition = (
        f"Dry period: days from dry-off (end of the previous lactation) to the next calving, for cows that calved "
        f"between {first_fresh} and {last_fresh}. "
        + ('Group = the lactation the cow calved into ("2" is her first dry period). ' if by == "parity" else "")
        + "Cows still dry at the end of the records are not counted."
    )
    return {
        "by": by,
        "rows": rows,
        "detail": dp,
        "definition": definition,
        "source": herd.source_line(),
    }


# --- analysis-ready lactation table ----------------------------------------------------------------------------------

def lactation_data(herd: Herd, events: list[str] | tuple[str, ...] | None = None,
                   within_dim: int | float | str = 21) -> list[dict[str, Any]]:
    """Build an analysis-ready cow-lactation table (one dict per fully observed lactation)."""
    if within_dim == "lactation":
        win = math.inf
    else:
        if not isinstance(within_dim, (int, float)) or isinstance(within_dim, bool) or math.isnan(within_dim) or within_dim < 0:
            raise DairyToolsError('within_dim must be days in milk (>= 0), math.inf, or "lactation".')
        win = float(within_dim)

    end = herd.data_end
    if events is None:
        ev_names = sorted({e["std_event"] for e in herd.events if e["category"] == "health" and e["std_event"]})
    else:
        ev_names = [events] if isinstance(events, str) else list(events)

    followed = int(win) if math.isfinite(win) else 0
    cutoff = end - timedelta(days=followed)
    lacts = [l for l in herd.lactations if l["fully_observed"] and (l["lactation"] or 0) >= 1
             and l["fresh_date"] <= cutoff]

    lacts_by_animal: dict[str, list[Any]] = defaultdict(list)
    for l in lacts:
        lacts_by_animal[l["animal_id"]].append(l)

    hits_by_event: dict[str, set[tuple[str, int]]] = {}
    for name in ev_names:
        hit_keys: set[tuple[str, int]] = set()
        for e in herd.events_by_std.get(name, ()):
            dim = e.get("dim_at_event")
            lact = e.get("lactation")
            if dim is not None and lact is not None:
                if 0 <= dim <= win:
                    hit_keys.add((e["animal_id"], lact))
            elif e.get("event_date") is not None:
                # Fallback when DIM or LACT is absent from the events export: match by date within lactation.
                for l in lacts_by_animal.get(e["animal_id"], ()):
                    d_calc = (e["event_date"] - l["fresh_date"]).days
                    if 0 <= d_calc <= win:
                        hit_keys.add((l["animal_id"], l["lactation"]))
        hits_by_event[name] = hit_keys

    dry_by_key = {(r["animal_id"], r["lactation"]): r["dry_days"] for r in dry_periods(herd)}

    last_neg: dict[tuple[str, int], date] = {}
    for e in herd.events_by_std.get("preg_negative", ()):
        if _is_restated_breeding(e):
            continue
        lact = e.get("lactation")
        if lact is None:
            continue
        k = (e["animal_id"], lact)
        if k not in last_neg or e["event_date"] > last_neg[k]:
            last_neg[k] = e["event_date"]

    rows: list[dict[str, Any]] = []
    for l in lacts:
        aid = l["animal_id"]
        lact_num = l["lactation"]
        key = (aid, lact_num)
        pregnant = l["conception_date"] is not None
        fsd = l["first_service_date"]
        if fsd is None:
            fs_outcome = None
        elif pregnant and l["conception_date"] == fsd:
            fs_outcome = "pregnant"
        elif (l["services"] >= 2) or pregnant or (key in last_neg and last_neg[key] > fsd):
            fs_outcome = "open"
        else:
            fs_outcome = "unknown"

        stop = l["end_date"]
        if stop is None or stop > end:
            stop = end
        follow_days = (stop - l["fresh_date"]).days
        days_to_event = l["days_open"] if pregnant else follow_days

        row: dict[str, Any] = {
            "animal_id": aid,
            "cow_id": l["cow_id"],
            "lactation": lact_num,
            "fresh_date": l["fresh_date"],
            "end_date": l["end_date"],
            "end_reason": l["end_reason"],
            "first_service_date": fsd,
            "first_service_dim": l["first_service_dim"],
            "services": l["services"],
            "conception_date": l["conception_date"],
            "days_open": l["days_open"],
            "health_events": l["health_events"],
            "fully_observed": l["fully_observed"],
            "start_source": l["start_source"],
        }
        for name in ev_names:
            row[name] = key in hits_by_event[name]
        row["dry_days"] = dry_by_key.get(key)
        row["parity"] = "1" if lact_num == 1 else "2+"
        row["lactation_group"] = "3+" if lact_num >= 3 else str(lact_num)
        row["pregnant"] = pregnant
        row["first_service_outcome"] = fs_outcome
        row["follow_days"] = follow_days
        row["days_to_event"] = days_to_event
        row["event"] = pregnant
        rows.append(row)
    return rows


# --- 2x2 risk ratio, Mantel-Haenszel stratified RR & group comparison ------------------------------------------------

def _coerce_exposed(xs: list[Any], exposure: str, exposed: Any) -> tuple[Any, bool]:
    non_null_x = [v for v in xs if v is not None]
    x_is_bool = bool(non_null_x) and all(isinstance(v, bool) for v in non_null_x)
    if exposed is None:
        if not x_is_bool:
            choices = sorted({str(v) for v in non_null_x})
            raise DairyToolsError(f"Say which group is exposed: exposed = one of {', '.join(repr(c) for c in choices)}.")
        return True, True
    if x_is_bool and not isinstance(exposed, bool):
        u = str(exposed).strip().upper()
        if u in ("1", "TRUE", "T", "YES"):
            return True, True
        if u in ("0", "FALSE", "F", "NO"):
            return False, True
    return exposed, x_is_bool


def risk_ratio(data: list[dict[str, Any]], outcome: str, exposure: str, exposed: Any = None) -> dict[str, Any]:
    """2x2 risk ratio and odds ratio with 95% Taylor-series CIs and chi-square / Fisher's exact p-value."""
    if not data:
        raise MissingDataError("No rows in data for risk_ratio().")
    for col in (outcome, exposure):
        if col not in data[0]:
            raise NotFoundError(f"No column '{col}' in the data.")
    ys = [r.get(outcome) for r in data]
    non_null_y = [v for v in ys if v is not None]
    if not non_null_y or not all(isinstance(v, bool) for v in non_null_y):
        raise DairyToolsError(f"'{outcome}' must be True/False (a case or not).")
    xs = [r.get(exposure) for r in data]
    exposed, x_is_bool = _coerce_exposed(xs, exposure, exposed)

    kept = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    exp_str = str(exposed)
    if not any((x == exposed if x_is_bool else str(x) == exp_str) for x, _ in kept):
        raise MissingDataError(f"No rows have {exposure} = {exposed}.")

    a = b = c = d = 0
    others: set[str] = set()
    for x, y in kept:
        is_exp = (x == exposed) if x_is_bool else (str(x) == exp_str)
        if is_exp:
            a += int(y)
            b += int(not y)
        else:
            others.add(str(x))
            c += int(y)
            d += int(not y)
    n1 = a + b
    n0 = c + d
    if n0 == 0:
        raise MissingDataError("Everyone is in the exposed group: there is no reference group.")

    def _log_ci(est: float | None, se: float | None) -> tuple[float | None, float | None]:
        if est is None or se is None or est <= 0 or not math.isfinite(se):
            return None, None
        return round(est * math.exp(-Z_95 * se), 2), round(est * math.exp(Z_95 * se), 2)

    r1 = a / n1
    r0 = c / n0
    rr_val = (r1 / r0) if r0 > 0 else None
    rr_se = math.sqrt(1 / a - 1 / n1 + 1 / c - 1 / n0) if (a > 0 and c > 0) else None
    rr_lo, rr_hi = _log_ci(rr_val, rr_se)

    or_val = ((a * d) / (b * c)) if (b > 0 and c > 0) else None
    or_se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d) if (a > 0 and b > 0 and c > 0 and d > 0) else None
    or_lo, or_hi = _log_ci(or_val, or_se)

    total = n1 + n0
    c1 = a + c
    c0 = b + d
    expected = (n1 * c1 / total, n1 * c0 / total, n0 * c1 / total, n0 * c0 / total)
    use_fisher = any(e < 5.0 for e in expected)
    if use_fisher:
        p = fisher_exact_2x2(a, b, c, d)
        test_name = "Fisher's exact"
    else:
        _, p = chisq_contingency([(a, b), (c, d)], correct=False)
        test_name = "chi-square"

    exp_label = f"{exposure} = TRUE" if x_is_bool else f"{exposure} {exposed}"
    if x_is_bool:
        ref_label = f"{exposure} = FALSE"
    elif len(others) == 1:
        ref_label = f"{exposure} {next(iter(others))}"
    else:
        ref_label = f"{exposure} not {exposed}"

    return {
        "outcome": outcome,
        "exposure": exposure,
        "exposed_label": exp_label,
        "reference_label": ref_label,
        "exposed_cases": a,
        "exposed_n": n1,
        "exposed_risk": share(a, n1),
        "reference_cases": c,
        "reference_n": n0,
        "reference_risk": share(c, n0),
        "rr": round(rr_val, 2) if rr_val is not None else None,
        "rr_lower": rr_lo,
        "rr_upper": rr_hi,
        "or": round(or_val, 2) if or_val is not None else None,
        "or_lower": or_lo,
        "or_upper": or_hi,
        "p_value": signif(p, 2),
        "test": test_name,
    }


def mantel_haenszel_rr(
    data: list[dict[str, Any]],
    outcome: str,
    exposure: str,
    strata: str = "parity",
    exposed: Any = None,
) -> dict[str, Any]:
    """Parity- or group-stratified Mantel-Haenszel pooled Risk Ratio with Greenland-Robins 95% CI and MH p-value."""
    if not data:
        raise MissingDataError("No rows in data for mantel_haenszel_rr().")
    for col in (outcome, exposure, strata):
        if col not in data[0]:
            raise NotFoundError(f"No column '{col}' in the data.")
    xs = [r.get(exposure) for r in data]
    exposed, x_is_bool = _coerce_exposed(xs, exposure, exposed)
    exp_str = str(exposed)

    by_stratum: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for r in data:
        s, x, y = r.get(strata), r.get(exposure), r.get(outcome)
        if s is None or x is None or y is None:
            continue
        is_exp = (x == exposed) if x_is_bool else (str(x) == exp_str)
        cell = by_stratum[str(s)]
        if is_exp:
            cell[0 if y else 1] += 1
        else:
            cell[2 if y else 3] += 1

    if not by_stratum:
        raise MissingDataError("No complete strata for mantel_haenszel_rr().")

    stratum_rows = []
    tuples: list[tuple[int, int, int, int]] = []
    for s in sorted(by_stratum):
        a, b, c, d = by_stratum[s]
        tuples.append((a, b, c, d))
        n1, n0 = a + b, c + d
        rr_s = ((a / n1) / (c / n0)) if (n1 > 0 and n0 > 0 and c > 0) else None
        stratum_rows.append({
            "stratum": s,
            "exposed_cases": a,
            "exposed_n": n1,
            "exposed_risk": share(a, n1),
            "reference_cases": c,
            "reference_n": n0,
            "reference_risk": share(c, n0),
            "rr": round(rr_s, 2) if rr_s is not None else None,
        })

    pooled = _mh_rr(tuples)
    crude = risk_ratio(data, outcome, exposure, exposed=exposed)
    return {
        "outcome": outcome,
        "exposure": exposure,
        "strata": strata,
        "crude_rr": crude["rr"],
        "mh_rr": pooled["rr"],
        "mh_rr_lower": pooled["rr_lower"],
        "mh_rr_upper": pooled["rr_upper"],
        "p_value": pooled["p_value"],
        "stratum_rows": stratum_rows,
        "definition": (
            f"Mantel-Haenszel pooled risk ratio for {outcome} by {exposure}, stratified by {strata}, with "
            f"Greenland-Robins 95% confidence interval and Mantel-Haenszel chi-square test."
        ),
    }


def compare_groups(data: list[dict[str, Any]], value: str, group: str) -> list[dict[str, Any]]:
    """Compare a numeric column across groups (Wilcoxon rank-sum for 2 groups, Kruskal-Wallis for 3+)."""
    grouped: dict[str, list[float]] = defaultdict(list)
    for r in data:
        v = r.get(value)
        g = r.get(group)
        if v is not None and g is not None and math.isfinite(v):
            grouped[str(g)].append(float(v))
    levels = sorted(grouped)
    if len(levels) == 2:
        p = wilcoxon_ranksum(grouped[levels[0]], grouped[levels[1]], correct=True)
        test_name = "Wilcoxon rank-sum"
    elif len(levels) > 2:
        p = kruskal_wallis([grouped[lv] for lv in levels])
        test_name = "Kruskal-Wallis"
    else:
        p = None
        test_name = ""
    return [
        {
            "group": lv,
            "n": len(grouped[lv]),
            "median": median(grouped[lv]),
            "q1": quantile(grouped[lv], 0.25),
            "q3": quantile(grouped[lv], 0.75),
            "mean": round(mean(grouped[lv]), 1),
            "p_value": signif(p, 2),
            "test": test_name,
        }
        for lv in levels
    ]


# --- fresh disease effects -------------------------------------------------------------------------------------------

def fresh_disease_effects(herd: Herd, event: str | list[str] | tuple[str, ...],
                          within_dim: int = 30, removal_dim: int = 60) -> dict[str, Any]:
    """Compare lactations with vs without fresh-cow disease `event` within `within_dim` DIM on:
    1. Milk at first test (within parity 1 vs 2+, Wilcoxon rank-sum)
    2. Removal (sold or died) by `removal_dim` DIM (`risk_ratio`)
    3. Days open (median among conceived + Kaplan-Meier median days to conception)
    """
    ev_list = [event] if isinstance(event, str) else list(event)
    recorded = set(herd.events_by_std)
    unknown = [e for e in ev_list if e not in recorded]
    if unknown:
        raise NotFoundError(f"No events called {', '.join(unknown)} in this herd.")

    end = herd.data_end
    label = " or ".join(ev_list)
    sick_col = f"{label.replace(' ', '_')}_by_{within_dim}_dim"
    ld = lactation_data(herd, events=ev_list, within_dim=within_dim)
    groups = [f"with {label}", f"without {label}"]
    for r in ld:
        sick = any(r[e] for e in ev_list)
        r[sick_col] = sick
        r["group"] = groups[0] if sick else groups[1]

    notes: list[str] = []

    # 1. Milk at first test (prefer first_test_milk, then multi-snapshot milk_history tests, else <=60 DIM current cows)
    has_ftm = any(c.get("first_test_milk") is not None for c in herd.cows)
    tested_by_key: dict[tuple[str, int], float] = {}
    if has_ftm:
        for c in herd.cows:
            if c.get("first_test_milk") is not None and c.get("lactation") is not None:
                tested_by_key[(c["animal_id"], c["lactation"])] = c["first_test_milk"]
        milk_source = "first_test_milk column (the first test of each cow's current or last lactation)"
    elif herd.milk_history and any(
        p["kind"] == "test" for pts in herd.milk_history.values() for p in pts
    ):
        # Match earliest test snapshot in each lactation (within 60 DIM) across multi-snapshot exports.
        for r in ld:
            pts = herd.milk_history.get(str(r["cow_id"]).strip(), ())
            end_cap = r["end_date"] or end
            early = [
                p["lb"] for p in pts
                if p["kind"] == "test" and r["fresh_date"] <= p["day"] <= end_cap
                and (p["day"] - r["fresh_date"]).days <= 60 and p["lb"] > 0
            ]
            if early:
                tested_by_key[(r["animal_id"], r["lactation"])] = early[0]
        milk_source = "earliest milk test within 60 DIM from the monthly test snapshots"
    else:
        for c in herd.cows:
            if (c.get("left_date") is None and (c.get("test_milk") or 0) > 0
                    and c.get("days_in_milk") is not None and c["days_in_milk"] <= 60
                    and c.get("lactation") is not None):
                tested_by_key[(c["animal_id"], c["lactation"])] = c["test_milk"]
        what = "latest daily weight" if herd.milk_words == "latest daily weight" else "latest test (test_milk)"
        milk_source = (f"{what} of cows still in the herd at 60 DIM or less at the end of the records; "
                       "earlier tests are not in the records")
        notes.append(
            f"Milk: the records hold only each cow's {herd.milk_words}, not every test day, so first-test milk is "
            f"from cows now 60 DIM or less ({within_dim}-60 DIM). It is a small, recent group; "
            f"a test-day export would give first-test milk for every lactation."
        )

    milk_d = []
    for r in ld:
        m = tested_by_key.get((r["animal_id"], r["lactation"]))
        if m is not None:
            milk_d.append({"parity": r["parity"], "group": r["group"], "milk": m})

    milk_rows: list[dict[str, Any]] | None = None
    if milk_d:
        milk_rows = []
        for p in sorted({r["parity"] for r in milk_d}):
            sub = [r for r in milk_d if r["parity"] == p]
            cg = compare_groups(sub, "milk", "group")
            by_g = {row["group"]: row for row in cg}
            for g in groups:
                if g in by_g:
                    row = {"parity": p, **by_g[g]}
                    if len(cg) < 2:
                        row["p_value"] = None
                        row["test"] = ""
                    milk_rows.append(row)
        notes.append("Milk is compared within parity (first-lactation cows give less milk); nothing else is adjusted for.")
    else:
        notes.append("Milk: no tested cows in these lactations, so no milk comparison.")

    # 2. Removal by removal_dim
    rem_cutoff = end - timedelta(days=max(removal_dim, within_dim))
    out_col = f"removed_by_{removal_dim}_dim"
    rem = []
    for r in ld:
        if r["fresh_date"] <= rem_cutoff:
            removed = (r["end_reason"] in ("sold", "died") and r["end_date"] is not None
                       and (r["end_date"] - r["fresh_date"]).days <= removal_dim)
            rem.append({**r, out_col: removed})
    removal = None
    if any(r[sick_col] for r in rem) and any(not r[sick_col] for r in rem):
        removal = risk_ratio(rem, out_col, sick_col)
        notes.append(
            f"Removal: lactations calving on or before {rem_cutoff}. "
            f"A cow that left before she could get sick counts as not sick, which can make the disease look less harmful."
        )
    else:
        notes.append("Removal: not enough lactations in both groups to compare.")

    # 3. Days open
    conceived_by_g = {g: [r["days_open"] for r in ld if r["group"] == g and r["days_open"] is not None] for g in groups}
    do_p = (signif(wilcoxon_ranksum(conceived_by_g[groups[0]], conceived_by_g[groups[1]], correct=True), 2)
            if conceived_by_g[groups[0]] and conceived_by_g[groups[1]] else None)
    days_open_rows = []
    for g in groups:
        sub = [r for r in ld if r["group"] == g]
        conc = conceived_by_g[g]
        days_open_rows.append({
            "group": g,
            "lactations": len(sub),
            "conceived": len(conc),
            "median_days_open": median(conc) if conc else None,
            "km_median_days_to_conception": km_median(
                [r["days_to_event"] for r in sub], [r["event"] for r in sub], interpolate_half=True
            ),
            "p_value": do_p,
        })
    notes.append("Days open: the median among cows that conceived leaves out cows that never did; the Kaplan-Meier "
                 "median counts them until they left or the records ended.")
    notes.append("These are associations: sick cows may differ in parity, season or other diseases.")

    return {
        "event": label,
        "within_dim": within_dim,
        "removal_dim": removal_dim,
        "milk": milk_rows,
        "milk_source": milk_source,
        "removal": removal,
        "days_open": days_open_rows,
        "notes": notes,
        "source": herd.source_line(),
    }


# --- left_reasons (cow-years cull & death rates), left_herd, event_months (R parity) ---------------------------------

def _cow_spells(herd: Herd) -> list[tuple[str, date, date | None]]:
    """Earliest date each calved cow entered the records -> her left_date (or None)."""
    earliest: dict[str, date] = {}
    for l in herd.lactations:
        if (l["lactation"] or 0) >= 1 and l["fresh_date"] is not None:
            aid = l["animal_id"]
            if aid not in earliest or l["fresh_date"] < earliest[aid]:
                earliest[aid] = l["fresh_date"]
    for e in herd.events:
        if (e.get("lactation") or 0) >= 1 and e["event_date"] is not None:
            aid = e["animal_id"]
            if aid not in earliest or e["event_date"] < earliest[aid]:
                earliest[aid] = e["event_date"]
    for c in herd.cows:
        if (c.get("lactation") or 0) >= 1 and c.get("fresh_date") is not None:
            aid = c["animal_id"]
            if aid not in earliest or c["fresh_date"] < earliest[aid]:
                earliest[aid] = c["fresh_date"]
    return [
        (aid, entry, herd.cow_by_animal[aid].get("left_date") if aid in herd.cow_by_animal else None)
        for aid, entry in earliest.items()
    ]


def _left_remark_by_animal(herd: Herd) -> dict[str, str]:
    """Last SOLD/DIED event remark per animal (used only when `allow_untrusted=True`)."""
    out: dict[str, tuple[date, str]] = {}
    for std in ("sold", "died"):
        for e in herd.events_by_std.get(std, ()):
            aid = e["animal_id"]
            d = e["event_date"]
            rem = (e.get("remark") or "").strip()
            if aid not in out or d >= out[aid][0]:
                out[aid] = (d, rem)
    return {aid: rem for aid, (_, rem) in out.items()}


def left_reasons(
    herd: Herd,
    from_date: date | None = None,
    to_date: date | None = None,
    by: str = "reason",
    allow_untrusted: bool = False,
) -> dict[str, Any]:
    """Annual cull and death rates per 100 cow-years using exact day-by-day cow spells.

    `by`: `"reason"` (sold/died), `"parity"` (1 vs 2+), `"lactation_group"` (1, 2, 3+), `"dim_band"` (0-30, 31-60,
    61-200, over 200, dry, unknown), or `"remark"` (farm exit remarks; gated by `allow_untrusted` safety boundary).
    """
    choices = ("reason", "remark", "parity", "lactation_group", "dim_band")
    if by not in choices:
        raise DairyToolsError(f"by must be one of {', '.join(choices)}; got {by!r}")
    end = herd.data_end
    start = herd.events_from or end
    to_d = to_date or end
    from_d = from_date or (to_d - timedelta(days=364))
    if from_d > end:
        raise MissingDataError(f"The period starts after the records end ({end}).")
    if to_d < start:
        raise MissingDataError(f"The period ends before the records start ({start}).")
    notes: list[str] = []
    if to_d > end:
        notes.append(f"The records end on {end}; counting to then.")
        to_d = end
    if from_d < start:
        notes.append(f"The records start on {start}; counting from then.")
        from_d = start
    if from_d > to_d:
        raise DairyToolsError("'from_date' is after 'to_date'.")

    days = (to_d - from_d).days + 1
    in_period = [c for c in herd.cows if c.get("left_date") is not None and from_d <= c["left_date"] <= to_d]
    heifers = sum(1 for c in in_period if (c.get("lactation") or 0) < 1)
    gone = [c for c in in_period if (c.get("lactation") or 0) >= 1]
    if not gone:
        raise MissingDataError(f"No cows left the herd between {from_d} and {to_d}.")

    spells = _cow_spells(herd)
    cow_days = 0
    end_excl = to_d + timedelta(days=1)
    for _, entry, exit_d in spells:
        e_lo = entry if entry > from_d else from_d
        e_hi = end_excl if (exit_d is None or exit_d > to_d) else exit_d
        if e_hi > e_lo:
            cow_days += (e_hi - e_lo).days
    cow_years = cow_days / 365.25
    rate = lambda n: round(100 * n / cow_years, 1) if cow_years > 0 else None

    safety_note = None
    total_gone = len(gone)
    if by in ("reason", "remark"):
        remarks_map = _left_remark_by_animal(herd) if by == "remark" else {}
        counts: Counter = Counter()
        redacted = 0
        for c in gone:
            reason = c.get("left_reason") or "left"
            if by == "reason":
                counts[(reason,)] += 1
            else:
                rem = remarks_map.get(c["animal_id"], "") or "(no remark)"
                if rem != "(no remark)" and not allow_untrusted and not SAFE_EXIT_CODE.match(rem):
                    rem = "redacted (free text)"
                    redacted += 1
                counts[(reason, rem)] += 1
        if by == "remark" and allow_untrusted:
            safety_note = "Includes raw farm exit remarks because allow_untrusted=True (--include-untrusted) was passed."
        elif redacted:
            safety_note = f"{redacted} free-text exit remarks were redacted; pass allow_untrusted=True to show raw text."
        rows = []
        for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
            row = {"reason": key[0]}
            if by == "remark":
                row["remark"] = key[1]
            row.update({"n": n, "share": share(n, total_gone), "per_100_cow_years": rate(n)})
            rows.append(row)
    else:
        order_map = {
            "parity": ["1", "2+"],
            "lactation_group": ["1", "2", "3+"],
            "dim_band": ["0-30", "31-60", "61-200", "over 200", "dry", "unknown"],
        }
        g_tot: Counter[str] = Counter()
        g_sold: Counter[str] = Counter()
        g_died: Counter[str] = Counter()
        for c in gone:
            if by == "parity":
                g = "1" if c["lactation"] == 1 else "2+"
            elif by == "lactation_group":
                g = "3+" if c["lactation"] >= 3 else str(c["lactation"])
            else:
                last = herd.lactations_by_key.get((c["animal_id"], c["lactation"]))
                is_dry = bool(last and last["end_reason"] == "dried off" and last["end_date"] is not None
                              and last["end_date"] <= c["left_date"])
                dim = (c["left_date"] - c["fresh_date"]).days if c.get("fresh_date") else None
                if is_dry:
                    g = "dry"
                elif dim is None or dim < 0:
                    g = "unknown"
                elif dim <= 30:
                    g = "0-30"
                elif dim <= 60:
                    g = "31-60"
                elif dim <= 200:
                    g = "61-200"
                else:
                    g = "over 200"
            g_tot[g] += 1
            if c.get("left_reason") == "sold":
                g_sold[g] += 1
            elif c.get("left_reason") == "died":
                g_died[g] += 1
        rows = [
            {
                "group": lv,
                "n": g_tot[lv],
                "sold": g_sold[lv],
                "died": g_died[lv],
                "share": share(g_tot[lv], total_gone),
                "per_100_cow_years": rate(g_tot[lv]),
            }
            for lv in order_map[by] if g_tot[lv]
        ]

    sold_n = sum(1 for c in gone if c.get("left_reason") == "sold")
    died_n = sum(1 for c in gone if c.get("left_reason") == "died")
    ci_lo, ci_hi = poisson_ci(total_gone, cow_years)
    return {
        "by": by,
        "from": from_d.isoformat(),
        "to": to_d.isoformat(),
        "days": days,
        "average_herd": round(cow_days / days, 1),
        "cow_years": round(cow_years, 1),
        "total_left": total_gone,
        "sold": sold_n,
        "died": died_n,
        "total_per_100_cow_years": rate(total_gone),
        "total_ci_low": round(100 * ci_lo, 1) if ci_lo is not None else None,
        "total_ci_high": round(100 * ci_hi, 1) if ci_hi is not None else None,
        "heifers_excluded": heifers,
        "rows": rows,
        "safety_note": safety_note,
        "notes": notes,
        "definition": (
            f"Cows (calved at least once) with a left date from {from_d} to {to_d} ({days} days). Rates are per 100 "
            f"cow-years of the whole herd (average herd {round(cow_days / days, 1)} cows, exact cow-days)."
            + (f" {heifers} heifers that left are not counted." if heifers else "")
        ),
        "source": herd.source_line(),
    }


def left_herd(herd: Herd, within_dim: int = 60, by: str = "parity") -> dict[str, Any]:
    """Share of lactations ending sold or died within `within_dim` DIM with 95% Wilson CI."""
    choices = ("calving_year", "parity", "lactation_group", "calving_month", "calving_season", "none")
    if by not in choices:
        raise DairyToolsError(f"by must be one of {', '.join(choices)}; got {by!r}")
    end = herd.data_end
    cutoff = end - timedelta(days=within_dim)
    ld = [r for r in lactation_data(herd) if r["fresh_date"] <= cutoff]
    if not ld:
        raise MissingDataError(f"No lactations calved on or before {cutoff}.")

    grouped: dict[str, list[bool]] = defaultdict(list)
    for r in ld:
        if by == "parity":
            g = r["parity"]
        elif by == "lactation_group":
            g = r["lactation_group"]
        elif by == "calving_year":
            g = str(r["fresh_date"].year)
        elif by in ("calving_month", "calving_season"):
            g = calving_period(r["fresh_date"], by)
        else:
            g = "all"
        left = bool(r["end_reason"] in ("sold", "died") and r["end_date"] is not None
                    and (r["end_date"] - r["fresh_date"]).days <= within_dim)
        grouped[g].append(left)

    if by == "calving_month":
        levels = [m for m in MONTH_ABBR if m in grouped]
    elif by == "calving_season":
        levels = [s for s in SEASONS if s in grouped]
    else:
        levels = sorted(grouped)

    rows = []
    for lv in levels:
        ys = grouped[lv]
        n, k = len(ys), sum(ys)
        lo, hi = wilson(k, n)
        rows.append({
            "group": lv,
            "n": n,
            "left": k,
            "share": share(k, n),
            "ci_low": round(lo, 3) if lo is not None else None,
            "ci_high": round(hi, 3) if hi is not None else None,
        })
    return {
        "within_dim": within_dim,
        "by": by,
        "rows": rows,
        "definition": f"Lactations calving on or before {cutoff}; left = sold or died within {within_dim} DIM.",
        "source": herd.source_line(),
    }


def event_months(herd: Herd, event: str | list[str] | tuple[str, ...], by: str = "calendar_month") -> dict[str, Any]:
    """First cases of `event` per lactation by calendar month or year-month, with chi-square seasonality test against
    the exact number of calendar days each month was observed."""
    if by not in ("calendar_month", "year_month"):
        raise DairyToolsError(f"by must be 'calendar_month' or 'year_month', got {by!r}")
    ev_list = [event] if isinstance(event, str) else list(event)
    if not herd.events_from:
        raise MissingDataError("No events in these records.")
    end = herd.data_end
    start = herd.events_from

    # First occurrence per (animal_id, lactation) across the requested events.
    earliest: dict[tuple[str, Any], date] = {}
    for name in ev_list:
        for e in herd.events_by_std.get(name, ()):
            if e["event_date"] is None or e["event_date"] > end:
                continue
            k = (e["animal_id"], e.get("lactation"))
            if k not in earliest or e["event_date"] < earliest[k]:
                earliest[k] = e["event_date"]

    # Build ordered month list and exact observed calendar days per month (interval math, no day loop!).
    from calendar import monthrange
    ym_labels: list[str] = []
    days_by_key: Counter[str] = Counter()
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        lo = max(date(y, m, 1), start)
        hi = min(date(y, m, monthrange(y, m)[1]), end)
        n_days = (hi - lo).days + 1
        ym = f"{y}-{m:02d}"
        ym_labels.append(ym)
        key = MONTH_ABBR[m - 1] if by == "calendar_month" else ym
        days_by_key[key] += n_days
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    labels = list(MONTH_ABBR) if by == "calendar_month" else ym_labels
    case_counts: Counter[str] = Counter()
    for d in earliest.values():
        key = MONTH_ABBR[d.month - 1] if by == "calendar_month" else f"{d.year}-{d.month:02d}"
        case_counts[key] += 1

    total = sum(case_counts.values())
    obs = [case_counts[lab] for lab in labels]
    exp_w = [float(days_by_key[lab]) for lab in labels]
    _, p_val = chisq_goodness_of_fit(obs, exp_w) if total >= 1 else (0.0, math.nan)
    p_out = None if math.isnan(p_val) else p_val

    rows = [
        {"month": lab, "cases": case_counts[lab], "share": share(case_counts[lab], max(1, total))}
        for lab in labels
    ]
    return {
        "event": " or ".join(ev_list),
        "by": by,
        "n_cases": total,
        "p_value": p_out,
        "rows": rows,
        "definition": (
            f"First case per lactation of {' or '.join(ev_list)} from {start} to {end}. Chi-square goodness-of-fit "
            f"compares observed cases to the exact number of calendar days each month was observed."
        ),
        "source": herd.source_line(),
    }


# --- Beyond R: Kaplan-Meier herd survival, calving outcomes, records quality audit -----------------------------------

def herd_survival(herd: Herd, by: str = "parity") -> dict[str, Any]:
    """Kaplan-Meier herd survival (not sold or died) from calving through 60, 150, and 305 DIM, with Greenwood 95% CIs."""
    if by not in ("none", "parity"):
        raise DairyToolsError(f"by must be 'none' or 'parity', got {by!r}")
    end = herd.data_end
    lacts = [l for l in herd.lactations if l["fully_observed"] and (l["lactation"] or 0) >= 1]
    if not lacts:
        raise MissingDataError("No lactations observed from calving in these records.")

    by_group: dict[str, tuple[list[float], list[bool]]] = defaultdict(lambda: ([], []))
    all_t: list[float] = []
    all_e: list[bool] = []
    all_g: list[str] = []
    for l in lacts:
        g = ("1" if l["lactation"] == 1 else "2+") if by == "parity" else "all"
        ev = l["end_reason"] in ("sold", "died") and l["end_date"] is not None and l["end_date"] <= end
        stop = l["end_date"] if (l["end_date"] is not None and l["end_date"] <= end) else end
        t = float(max(0, (stop - l["fresh_date"]).days))
        by_group[g][0].append(t)
        by_group[g][1].append(ev)
        all_t.append(t)
        all_e.append(ev)
        all_g.append(g)

    rows = []
    for lv in sorted(by_group):
        ts, evs = by_group[lv]
        curve = kaplan_meier(ts, evs)
        max_t = max(ts)

        def surv_at(day: int) -> tuple[float | None, float | None, float | None]:
            if day > max_t:
                return None, None, None
            s, se = 1.0, 0.0
            for u, sv, _, _, gw in curve:
                if u <= day:
                    s, se = sv, gw
                else:
                    break
            return round(s, 3), round(max(0.0, s - Z_95 * se), 3), round(min(1.0, s + Z_95 * se), 3)

        s60, lo60, hi60 = surv_at(60)
        s150, lo150, hi150 = surv_at(150)
        s305, lo305, hi305 = surv_at(305)
        rows.append({
            "group": lv,
            "lactations": len(ts),
            "left": sum(evs),
            "survival_60": s60,
            "survival_60_ci": [lo60, hi60] if s60 is not None else None,
            "survival_150": s150,
            "survival_150_ci": [lo150, hi150] if s150 is not None else None,
            "survival_305": s305,
            "survival_305_ci": [lo305, hi305] if s305 is not None else None,
        })

    p_val = logrank_test(all_t, all_e, all_g) if len(by_group) > 1 else None
    return {
        "by": by,
        "rows": rows,
        "p_value": p_val,
        "definition": (
            f"Kaplan-Meier survival (not sold or died) from calving through 60, 150, and 305 DIM, with Greenwood "
            f"95% confidence intervals. Lactations ending in dry-off, next calving, or still in milk on {end} are censored."
        ),
        "source": herd.source_line(),
    }


def calving_outcomes(herd: Herd, by: str = "parity") -> dict[str, Any]:
    """Calving ease (`EASE`), calf sex (`CSEX`), twinning (`TWINS`), and observed gestation length from raw records."""
    if by not in ("none", "parity"):
        raise DairyToolsError(f"by must be 'none' or 'parity', got {by!r}")

    calved = [c for c in herd.cows if (c.get("lactation") or 0) >= 1]
    if not calved:
        raise MissingDataError("No calved cows in these records.")

    # Gestation length: previous lactation conception_date -> next lactation fresh_date (250-310 d plausible window).
    gest_by_g: dict[str, list[int]] = defaultdict(list)
    gest_odd = 0
    for l in herd.lactations:
        if (l["lactation"] or 0) < 2 or l["fresh_date"] is None:
            continue
        prev = herd.lactations_by_key.get((l["animal_id"], l["lactation"] - 1))
        if prev is None or prev["conception_date"] is None:
            continue
        days = (l["fresh_date"] - prev["conception_date"]).days
        if 250 <= days <= 310:
            g = ("1" if l["lactation"] == 1 else "2+") if by == "parity" else "all"
            gest_by_g[g].append(days)
        else:
            gest_odd += 1

    # Twinning: TWINS events matched to fully observed lactations.
    twin_keys = {(e["animal_id"], e.get("lactation")) for e in herd.events_by_std.get("twins", ())
                 if e.get("lactation") is not None}
    obs_lacts = [l for l in herd.lactations if l["fully_observed"] and (l["lactation"] or 0) >= 1]

    groups = sorted({("1" if c["lactation"] == 1 else "2+") if by == "parity" else "all" for c in calved})
    rows = []
    for g in groups:
        sub_c = [c for c in calved if (("1" if c["lactation"] == 1 else "2+") if by == "parity" else "all") == g]
        eases = [c["calving_ease"] for c in sub_c if c.get("calving_ease") is not None and c["calving_ease"] > 0]
        sexes = Counter((c.get("calf_sex") or "").strip().upper() for c in sub_c if (c.get("calf_sex") or "").strip())
        sub_l = [l for l in obs_lacts if (("1" if l["lactation"] == 1 else "2+") if by == "parity" else "all") == g]
        twins = sum(1 for l in sub_l if (l["animal_id"], l["lactation"]) in twin_keys)
        gs = gest_by_g.get(g, [])
        rows.append({
            "group": g,
            "ease_recorded": len(eases),
            "ease_score_ge_3": sum(1 for v in eases if v >= 3),
            "share_ease_ge_3": share(sum(1 for v in eases if v >= 3), len(eases)),
            "calf_sex_recorded": sum(sexes.values()),
            "calf_sex_counts": dict(sorted(sexes.items())),
            "observed_calvings": len(sub_l),
            "twins": twins,
            "twins_share": share(twins, len(sub_l)) if twin_keys else None,
            "gestation_n": len(gs),
            "gestation_median_days": median(gs) if gs else None,
            "gestation_mean_days": round(mean(gs), 1) if gs else None,
        })

    return {
        "by": by,
        "rows": rows,
        "gestation_excluded_outside_250_310": gest_odd,
        "definition": (
            "Calving ease (EASE) and calf sex (CSEX) from each cow's latest calving; twinning from TWINS events in "
            "fully observed lactations; gestation length from previous conception date to next calving (250-310 d)."
        ),
        "source": herd.source_line(),
    }


def audit_records(herd: Herd) -> dict[str, Any]:
    """Record-quality audit catching recording inconsistencies before analysis:
    - Breedings dated before the lactation's calving date
    - Positive pregnancy checks with no prior breeding in that lactation
    - Event DIM disagreeing with `(event_date - fresh_date).days` by > 2 days
    - Lactation number jumps (e.g. lactation 1 -> lactation 3 with no lactation 2)
    - Negative dry periods (dry-off dated after next calving)
    """
    breeding_before_calving = 0
    preg_without_breeding = 0
    dim_mismatches = 0
    lactation_jumps = 0
    negative_dry_periods = 0

    for aid, lacts in herd.lactations_by_animal.items():
        nums = sorted({l["lactation"] for l in lacts if (l["lactation"] or 0) >= 1})
        for a, b in zip(nums, nums[1:]):
            if b - a > 1:
                lactation_jumps += 1
        for l in lacts:
            if l["end_reason"] == "dried off" and l["end_date"] is not None and l["lactation"] is not None:
                nxt = herd.lactations_by_key.get((aid, l["lactation"] + 1))
                if nxt is not None and (nxt["fresh_date"] - l["end_date"]).days < 0:
                    negative_dry_periods += 1

    # Check events against matched lactation.
    for e in herd.events:
        lact_num = e.get("lactation")
        if lact_num is None or lact_num < 1:
            continue
        lac = herd.lactations_by_key.get((e["animal_id"], lact_num))
        if lac is None:
            continue
        diff = (e["event_date"] - lac["fresh_date"]).days
        if e["std_event"] == "breeding" and diff < 0:
            breeding_before_calving += 1
        if e.get("dim_at_event") is not None and abs(e["dim_at_event"] - diff) > 2 and diff >= 0:
            dim_mismatches += 1

    # Positive pregnancy checks with no prior breeding in the same lactation.
    bred_min: dict[tuple[str, int], date] = {}
    for e in herd.events_by_std.get("breeding", ()):
        if e.get("lactation") is not None and e["lactation"] >= 1:
            k = (e["animal_id"], e["lactation"])
            if k not in bred_min or e["event_date"] < bred_min[k]:
                bred_min[k] = e["event_date"]
    seen_preg: set[tuple[str, int]] = set()
    for e in herd.events_by_std.get("preg_positive", ()):
        if _is_restated_breeding(e) or e.get("lactation") is None or e["lactation"] < 1:
            continue
        k = (e["animal_id"], e["lactation"])
        if k in seen_preg:
            continue
        lac = herd.lactations_by_key.get(k)
        if lac is not None and lac["fully_observed"]:
            seen_preg.add(k)
            if k not in bred_min or bred_min[k] > e["event_date"]:
                preg_without_breeding += 1

    checks = [
        {"check": "breeding_before_calving", "count": breeding_before_calving,
         "detail": "Breeding events dated earlier than the lactation's calving date"},
        {"check": "preg_without_breeding", "count": preg_without_breeding,
         "detail": "Fully observed lactations with a positive pregnancy check and no prior breeding"},
        {"check": "dim_date_mismatch", "count": dim_mismatches,
         "detail": "Events where recorded DIM disagrees with (event_date - fresh_date) by more than 2 days"},
        {"check": "lactation_number_jump", "count": lactation_jumps,
         "detail": "Animals whose lactation numbers skip a number (e.g. 1 to 3)"},
        {"check": "negative_dry_period", "count": negative_dry_periods,
         "detail": "Dry-off dates recorded after the next calving date"},
    ]
    return {
        "total_flags": sum(c["count"] for c in checks),
        "checks": checks,
        "load_problems": list(herd.problems),
        "unmapped_codes": dict(herd.unmapped_codes),
        "source": herd.source_line(),
    }
