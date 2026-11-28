"""Reproduction analyses plus record-only extensions:
- `pregnancy_rate`: 21-day pregnancy, service, and conception rates (pooled or cycle-by-cycle `cycles=True`)
- `conception_by`: conception risk by service, month, DIM band, parity, breeding code, technician, or sire
- `first_service`: days to first service and shares bred by VWP + 20 DIM and 100 DIM
- `pregnant_by`: share of lactations conceived by X DIM (default 150) with Wilson 95% CI
- `pregnancy_loss`: diagnosed pregnancies later found open or aborted
- `time_to_pregnancy`: Kaplan-Meier median days open, Greenwood 95% CIs, and log-rank test
- `calving_interval`: consecutive calving intervals and days open
- `age_first_calving`: months from birth to first calving
- `inter_service_intervals`: descriptive distribution of days between consecutive services (beyond R)
- `heifer_repro`: heifer age at first breeding, heifer conception risk, and heifer pregnancy loss (beyond R)

Safety boundary on untrusted farm text:
- Event remarks and technician names are free text typed on the farm and could contain untrusted text or personal names.
- In `conception_by(..., allow_untrusted=False)` (the safe default):
  * `group="sire"` accepts structured NAAB sire codes (`SIRE_CODE`) and replaces non-code free text with
    `"redacted (free text)"`.
  * `group="technician"` validates `technician_code` (`T`) as a short structured code (`^[A-Za-z0-9_-]{1,8}$`) and
    anonymizes free-text technician names as `"Technician 1"`, `"Technician 2"`, ...
  * `group="breeding_code"` validates `breeding_code` (`B`) as a short structured code (`^[A-Za-z0-9_-]{1,8}$`).
- Pass `allow_untrusted=True` (`--include-untrusted` on CLI) to opt into raw farm text (explicitly flagged in `safety_note`).
"""

from __future__ import annotations

import re
from bisect import bisect_left
from calendar import month_abbr
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from . import epi
from .errors import DairyToolsError, MissingDataError, NotFoundError
from .herd import SIRE_CODE, Herd, _is_restated_breeding
from .stats import (
    Z_95,
    chisq_contingency,
    kaplan_meier,
    km_median,
    logrank_test,
    mean,
    median,
    share,
    signif,
    wilson,
)

MONTH_ABBR = [month_abbr[i] for i in range(1, 13)]
MONTH_DAYS = 30.4375
SAFE_CODE = re.compile(r"^[A-Za-z0-9_-]{1,8}$")


def _parity(lactation: int) -> str:
    if lactation == 0:
        return "heifers"
    return "1" if lactation == 1 else "2+"


def _sort_levels(levels) -> list[str]:
    lv = sorted(set(levels))
    head = [x for x in ("heifers", "1", "2+") if x in lv]
    tail = [x for x in lv if x not in ("heifers", "1", "2+")]
    return head + tail


# --- 21-day pregnancy_rate (pooled or cycle-by-cycle) ----------------------------------------------------------------

def pregnancy_rate(herd: Herd, vwp: int = 50, by: str = "none", cycles: bool = False) -> dict[str, Any]:
    """21-day pregnancy, service, and conception rates (BREDSUM's way), pooled or per 21-day cycle (`cycles=True`).

    Matches the R version's `pregnancy_rate()`: breedings and do-not-breed events are matched by `(animal_id, lactation)`
    (falling back to date-within-lactation if an event lacks a lactation number).
    """
    if by not in ("none", "parity"):
        raise DairyToolsError(f"by must be 'none' or 'parity', got {by!r}")
    end = herd.data_end
    lacts = [l for l in herd.lactations if l["fully_observed"] and (l["lactation"] or 0) >= 1]
    if not lacts or not herd.events_from:
        raise MissingDataError("No lactations observed from calving in these records.")

    last_start = end - timedelta(days=62)
    first_start = herd.events_from
    if last_start < first_start:
        raise MissingDataError("The records are too short for 21-day cycles.")
    starts: list[date] = []
    s = last_start
    while s >= first_start:
        starts.append(s)
        s -= timedelta(days=21)
    starts.reverse()

    breed_by_key: dict[tuple[str, int], list[date]] = defaultdict(list)
    breed_by_aid: dict[str, list[date]] = defaultdict(list)
    for e in herd.events_by_std.get("breeding", ()):
        if e["event_date"] is None:
            continue
        if e.get("lactation") is not None:
            breed_by_key[(e["animal_id"], e["lactation"])].append(e["event_date"])
        else:
            breed_by_aid[e["animal_id"]].append(e["event_date"])
    for ds in breed_by_key.values():
        ds.sort()
    for ds in breed_by_aid.values():
        ds.sort()

    dnb_by_key: dict[tuple[str, int], date] = {}
    dnb_by_aid: dict[str, date] = {}
    for e in herd.events_by_std.get("do_not_breed", ()):
        if e["event_date"] is None:
            continue
        if e.get("lactation") is not None:
            k = (e["animal_id"], e["lactation"])
            if k not in dnb_by_key or e["event_date"] < dnb_by_key[k]:
                dnb_by_key[k] = e["event_date"]
        else:
            aid = e["animal_id"]
            if aid not in dnb_by_aid or e["event_date"] < dnb_by_aid[aid]:
                dnb_by_aid[aid] = e["event_date"]

    lact_info = []
    levels_set: set[str] = set()
    for l in lacts:
        g = _parity(l["lactation"]) if by == "parity" else "all"
        levels_set.add(g)
        k = (l["animal_id"], l["lactation"])
        bdates = breed_by_key.get(k)
        if bdates is None and l["animal_id"] in breed_by_aid:
            bdates = [d for d in breed_by_aid[l["animal_id"]] if d >= l["fresh_date"]]
        dnb_day = dnb_by_key.get(k)
        if dnb_day is None:
            fallback_dnb = dnb_by_aid.get(l["animal_id"])
            if fallback_dnb is not None and fallback_dnb >= l["fresh_date"]:
                dnb_day = fallback_dnb
        lact_info.append((
            g,
            l["fresh_date"],
            l["fresh_date"] + timedelta(days=vwp),
            l["end_date"],
            l["conception_date"],
            dnb_day,
            bdates or (),
        ))

    levels = _sort_levels(levels_set)
    cycle_rows: list[dict[str, Any]] = []
    for s in starts:
        e_ = s + timedelta(days=20)
        counts = {lv: [0, 0, 0] for lv in levels}
        for g, fresh, vwp_day, stop, conc, dnb_day, bdates in lact_info:
            if s < vwp_day:
                continue
            if conc is not None and conc < s:
                continue
            if dnb_day is not None and dnb_day <= s:
                continue
            if stop is not None and stop <= e_:
                continue
            lo_day = s if s >= fresh else fresh
            idx = bisect_left(bdates, lo_day)
            bred = idx < len(bdates) and bdates[idx] <= e_
            preg = conc is not None and conc <= e_
            c = counts[g]
            c[0] += 1
            c[1] += bred
            c[2] += preg
        for lv in levels:
            el, br, pr = counts[lv]
            if el > 0:
                cycle_rows.append({
                    "cycle_start": s.isoformat(),
                    "cycle_end": e_.isoformat(),
                    "group": lv,
                    "eligible": el,
                    "bred": br,
                    "pregnant": pr,
                    "service_rate": share(br, el),
                    "conception_rate": share(pr, br),
                    "pregnancy_rate": share(pr, el),
                })

    if not cycle_rows:
        raise MissingDataError("No eligible cows in any 21-day cycle in these records.")

    first_c = cycle_rows[0]["cycle_start"]
    last_c = cycle_rows[-1]["cycle_end"]
    definition = (
        f"21-day cycles from {first_c} to {last_c} (later cycles are left out: pregnancies in them are not confirmed "
        f"42 days before the data end, {end}). Eligible: lactations observed from calving, past the {vwp}-day VWP at "
        f"the cycle start, not pregnant, not marked do-not-breed, and in the lactation for all 21 days. Bred: a "
        f"breeding in the cycle. Pregnant: conceived in the cycle. Service rate = bred / eligible; conception rate = "
        f"pregnant / bred; pregnancy rate = pregnant / eligible."
    )

    if cycles:
        rows = cycle_rows
    else:
        rows = []
        for lv in levels:
            sub = [r for r in cycle_rows if r["group"] == lv]
            if not sub:
                continue
            el = sum(r["eligible"] for r in sub)
            br = sum(r["bred"] for r in sub)
            pr = sum(r["pregnant"] for r in sub)
            rows.append({
                "group": lv,
                "cycles": len(sub),
                "eligible": el,
                "bred": br,
                "pregnant": pr,
                "service_rate": share(br, el),
                "conception_rate": share(pr, br),
                "pregnancy_rate": share(pr, el),
            })

    return {
        "vwp": vwp,
        "by": by,
        "cycles": cycles,
        "rows": rows,
        "definition": definition,
        "source": herd.source_line(),
    }


# --- conception_by ---------------------------------------------------------------------------------------------------

def conception_by(herd: Herd, group: str = "service", max_service: int = 3,
                  allow_untrusted: bool = False) -> dict[str, Any]:
    """Conception risk by `service`, `technician`, `sire`, `month`, `dim_band`, `breeding_code`, or `parity`.

    Matches the R version's `conception_by()` denominators, same-day deduplication, 45-day waiting window, Wilson 95% CIs,
    and chi-square test across groups with >= 20 services. Restated PREG/OPEN lines (breeding results rewritten by
    DairyComp with a sire code in the remark) are excluded from `preg_negative` checks.
    """
    choices = ("service", "technician", "sire", "month", "dim_band", "breeding_code", "parity")
    if group not in choices:
        raise DairyToolsError(f"group must be one of {', '.join(choices)}; got {group!r}")
    end = herd.data_end
    wait = 45
    lacts_by_key = {
        (l["animal_id"], l["lactation"]): l
        for l in herd.lactations
        if (l["lactation"] or 0) >= 1
    }

    cow_breedings: dict[tuple[str, int], dict[date, Any]] = defaultdict(dict)
    heifer_count = 0
    for e in herd.events_by_std.get("breeding", ()):
        if e["event_date"] is None:
            continue
        lact = e.get("lactation")
        k = (e["animal_id"], lact) if lact is not None else None
        if k is None or k not in lacts_by_key:
            heifer_count += 1
            continue
        cow_breedings[k].setdefault(e["event_date"], e)

    last_neg: dict[tuple[str, int], date] = {}
    for e in herd.events_by_std.get("preg_negative", ()):
        if _is_restated_breeding(e) or e.get("lactation") is None:
            continue
        k = (e["animal_id"], e["lactation"])
        if k not in last_neg or e["event_date"] > last_neg[k]:
            last_neg[k] = e["event_date"]

    def _dim_band(dim: int) -> str:
        if dim < 60:
            return "under 60"
        if dim < 100:
            return "60-99"
        if dim < 150:
            return "100-149"
        if dim < 200:
            return "150-199"
        return "200+"

    unknown_count = 0
    after_count = 0
    redacted_count = 0
    anonymized_techs = False
    raw_known: list[tuple[str, bool, bool]] = []

    for k, by_date in cow_breedings.items():
        lac = lacts_by_key[k]
        in_group = lac["fully_observed"] if group == "service" else True
        conc = lac["conception_date"]
        stop_date = lac["end_date"]
        neg_date = last_neg.get(k)
        ordered = sorted(by_date.items())
        n_serv = len(ordered)
        for idx, (d, e) in enumerate(ordered, 1):
            later_breeding = idx < n_serv
            checked_open = neg_date is not None and neg_date > d
            is_preg = conc is not None and d == conc
            is_after = conc is not None and d > conc
            stayed = d <= end - timedelta(days=wait) and (stop_date is None or stop_date > d + timedelta(days=wait))
            is_open = (not is_preg) and (not is_after) and (later_breeding or checked_open or stayed)
            if not in_group:
                continue
            if is_after:
                after_count += 1
                continue
            if not (is_preg or is_open):
                unknown_count += 1
                continue

            is_free_tech = False
            if group == "service":
                g = f"{max_service}+" if idx >= max_service else str(idx)
            elif group == "technician":
                tech = (e.get("technician") or "").strip()
                tcode = (e.get("technician_code") or "").strip()
                if tech:
                    g = tech
                    is_free_tech = True
                elif tcode:
                    if allow_untrusted or SAFE_CODE.match(tcode):
                        g = tcode
                    else:
                        g = "redacted (free text)"
                        redacted_count += 1
                else:
                    g = "not recorded"
            elif group == "sire":
                rem = (e.get("remark") or "").strip()
                if not rem:
                    g = "not recorded"
                elif allow_untrusted or SIRE_CODE.match(rem):
                    g = rem
                else:
                    g = "redacted (free text)"
                    redacted_count += 1
            elif group == "month":
                g = MONTH_ABBR[d.month - 1]
            elif group == "dim_band":
                g = _dim_band((d - lac["fresh_date"]).days)
            elif group == "breeding_code":
                bcode = (e.get("breeding_code") or "").strip()
                if not bcode:
                    g = "not recorded"
                elif allow_untrusted or SAFE_CODE.match(bcode):
                    g = bcode
                else:
                    g = "redacted (free text)"
                    redacted_count += 1
            else:  # parity
                g = _parity(lac["lactation"])
            raw_known.append((g, is_preg, is_free_tech))

    if group == "technician" and not allow_untrusted and any(ft for _, _, ft in raw_known):
        anonymized_techs = True
        tech_counts = Counter(g for g, _, ft in raw_known if ft)
        rank_map = {
            name: f"Technician {i}"
            for i, (name, _) in enumerate(sorted(tech_counts.items(), key=lambda kv: (-kv[1], kv[0])), 1)
        }
        known_records = [(rank_map[g] if ft else g, p) for g, p, ft in raw_known]
    else:
        known_records = [(g, p) for g, p, _ in raw_known]

    counts = Counter(g for g, _ in known_records)
    preg_counts = Counter(g for g, p in known_records if p)

    dim_levels = ["under 60", "60-99", "100-149", "150-199", "200+"]
    if group == "service":
        order = [str(i) for i in range(1, max_service)] + [f"{max_service}+"]
        lv = [x for x in order if x in counts]
    elif group == "month":
        lv = [m for m in MONTH_ABBR if m in counts]
    elif group == "dim_band":
        lv = [x for x in dim_levels if x in counts]
    elif group == "parity":
        lv = _sort_levels(counts)
    else:
        lv = sorted(counts, key=lambda x: (-counts[x], x))

    rows = []
    for g in lv:
        n = counts[g]
        p = preg_counts[g]
        lo, hi = wilson(p, n)
        rows.append({
            group: g,
            "services": n,
            "pregnant": p,
            "share": share(p, n),
            "ci_low": round(lo, 3) if lo is not None else None,
            "ci_high": round(hi, 3) if hi is not None else None,
            "note": "under 20 services: too few to compare" if n < 20 else "",
        })

    big = [g for g in lv if counts[g] >= 20]
    p_val: float | None = None
    if len(big) >= 2:
        table = [(counts[g] - preg_counts[g], preg_counts[g]) for g in big]
        if sum(p for _, p in table) > 0 and sum(o for o, _ in table) > 0:
            _, p_val = chisq_contingency(table)

    test_str = (
        "No test: fewer than two groups have 20 or more services (or no variation)."
        if p_val is None else
        f"Chi-square test across the groups with 20 or more services: p = {signif(p_val, 2)}."
    )
    safety_note = None
    if allow_untrusted and group in ("technician", "sire", "breeding_code"):
        safety_note = ("Includes raw untrusted farm text (technician names / remarks / codes) because "
                       "allow_untrusted=True (--include-untrusted) was passed.")
    elif anonymized_techs:
        safety_note = ("Technician names are anonymized (Technician 1, 2, ...) to avoid outputting personal names or "
                       "untrusted farm text; pass allow_untrusted=True (--include-untrusted) to show raw names.")
    elif redacted_count:
        safety_note = (f"{redacted_count} free-text values did not match a structured code and were redacted; "
                       "pass allow_untrusted=True (--include-untrusted) to show raw text.")

    in_obs = " in lactations observed from calving" if group == "service" else ""
    definition = (
        f"{len(known_records)} services to cows with a known outcome{in_obs}. Pregnant: the lactation's conception "
        f"service. Open: followed by another breeding or an open check, or more than {wait} days old with the cow "
        f"still in the lactation {wait} days later and never confirmed pregnant. Left out: {unknown_count} services "
        f"with no outcome yet (bred in the last {wait} days, or the cow left or was dried off within {wait} days with "
        f"no check), {after_count} services after the lactation's first conception (rebred after a pregnancy loss) and "
        f"{heifer_count} heifer / unmatched services. {test_str}"
    )
    return {
        "group": group,
        "rows": rows,
        "p_value": p_val,
        "safety_note": safety_note,
        "definition": definition,
        "source": herd.source_line(),
    }


# --- first_service & pregnant_by -------------------------------------------------------------------------------------

def first_service(herd: Herd, vwp: int = 50, by: str = "none") -> dict[str, Any]:
    """Days to first service and shares bred by VWP + 20 DIM and 100 DIM, for lactations followed to >= max(vwp+50, 100) DIM."""
    if by not in ("none", "parity"):
        raise DairyToolsError(f"by must be 'none' or 'parity', got {by!r}")
    end = herd.data_end
    follow = max(vwp + 50, 100)
    lacts = []
    for l in herd.lactations:
        if not l["fully_observed"] or (l["lactation"] or 0) < 1:
            continue
        stop_at = l["end_date"]
        if stop_at is None or stop_at > end:
            stop_at = end
        if (stop_at - l["fresh_date"]).days >= follow:
            lacts.append(l)
    if not lacts:
        raise MissingDataError(f"No lactations followed to {follow} DIM in these records.")

    grouped: dict[str, list[int | None]] = defaultdict(list)
    all_dims: list[int | None] = []
    for l in lacts:
        g = _parity(l["lactation"]) if by == "parity" else "all"
        d = l["first_service_dim"]
        grouped[g].append(d)
        all_dims.append(d)

    rows = []
    for lv in _sort_levels(grouped):
        ds = grouped[lv]
        bred = [d for d in ds if d is not None]
        n = len(ds)
        rows.append({
            "group": lv,
            "lactations": n,
            "bred": len(bred),
            "median_dim": median(bred) if bred else None,
            "mean_dim": round(mean(bred), 1) if bred else None,
            "share_by_vwp21": share(sum(1 for d in bred if d <= vwp + 20), n),
            "share_by_100": share(sum(1 for d in bred if d <= 100), n),
        })

    cuts = sorted({vwp, vwp + 21, 101})
    labs = [f"under {cuts[0]}"] + [f"{a}-{b - 1}" for a, b in zip(cuts, cuts[1:])] + [f"{cuts[-1]}+"]
    band_counts = Counter()
    for d in all_dims:
        if d is None:
            band_counts["not bred"] += 1
            continue
        placed = False
        for i, c in enumerate(cuts):
            if d < c:
                band_counts[labs[i]] += 1
                placed = True
                break
        if not placed:
            band_counts[labs[-1]] += 1
    n_all = len(all_dims)
    bands = [{"band": lab, "lactations": band_counts[lab], "share": share(band_counts[lab], n_all)}
             for lab in labs + ["not bred"]]

    definition = (
        f"Lactations observed from calving and followed to at least {follow} DIM (in the herd until then, calving on "
        f"or before {end - timedelta(days=follow)}). Median and mean DIM at first service are for cows bred; "
        f"share_by_vwp21 = first service by {vwp + 20} DIM (within 21 days after a {vwp}-day VWP); share_by_100 = "
        f"by 100 DIM; cows never bred count as not bred."
    )
    return {
        "vwp": vwp,
        "by": by,
        "rows": rows,
        "bands": bands,
        "definition": definition,
        "source": herd.source_line(),
    }


def pregnant_by(herd: Herd, days: int = 150, by: str = "parity") -> dict[str, Any]:
    """Share of lactations conceived by `days` DIM (default 150), with 95% Wilson CI.

    Matches the R version's `pregnant_by()`: only lactations calving at least `days + 35` days before `data_end` count;
    cows that left open stay in the denominator as not pregnant.
    """
    choices = ("parity", "lactation_group", "calving_year", "none")
    if by not in choices:
        raise DairyToolsError(f"by must be one of {', '.join(choices)}; got {by!r}")
    end = herd.data_end
    cutoff = end - timedelta(days=days + 35)
    ld = epi.lactation_data(herd)
    due = [r for r in ld if r["fresh_date"] <= cutoff]
    if not due:
        raise MissingDataError(f"No lactations calved on or before {cutoff} (for pregnant by {days} DIM).")

    grouped: dict[str, list[bool]] = defaultdict(list)
    for r in due:
        if by == "parity":
            g = r["parity"]
        elif by == "lactation_group":
            g = r["lactation_group"]
        elif by == "calving_year":
            g = str(r["fresh_date"].year)
        else:
            g = "all"
        yes = bool(r["pregnant"] and r["days_open"] is not None and r["days_open"] <= days)
        grouped[g].append(yes)

    rows = []
    for lv in _sort_levels(grouped):
        ys = grouped[lv]
        n = len(ys)
        k = sum(ys)
        lo, hi = wilson(k, n)
        rows.append({
            "group": lv,
            "n": n,
            "pregnant": k,
            "share": share(k, n),
            "ci_low": round(lo, 3) if lo is not None else None,
            "ci_high": round(hi, 3) if hi is not None else None,
        })
    return {
        "days": days,
        "by": by,
        "rows": rows,
        "definition": f"Lactations calving on or before {cutoff}; pregnant = conceived by {days} DIM.",
        "source": herd.source_line(),
    }


# --- pregnancy_loss --------------------------------------------------------------------------------------------------

def pregnancy_loss(herd: Herd, by: str = "none", followed_days: int = 60) -> dict[str, Any]:
    """Share of diagnosed pregnancies later found open or aborted before the next calving."""
    if by not in ("none", "parity"):
        raise DairyToolsError(f"by must be 'none' or 'parity', got {by!r}")
    end = herd.data_end
    cutoff = end - timedelta(days=followed_days)

    first_pos: dict[tuple[str, int], date] = {}
    for e in herd.events_by_std.get("preg_positive", ()):
        if _is_restated_breeding(e) or e["event_date"] is None or e.get("lactation") is None:
            continue
        k = (e["animal_id"], e["lactation"])
        if k not in first_pos or e["event_date"] < first_pos[k]:
            first_pos[k] = e["event_date"]

    dx = {k: d for k, d in first_pos.items() if d <= cutoff}

    losses: dict[tuple[str, int], tuple[date, str]] = {}
    for std in ("preg_negative", "abortion"):
        for e in herd.events_by_std.get(std, ()):
            if _is_restated_breeding(e) or e["event_date"] is None or e.get("lactation") is None:
                continue
            k = (e["animal_id"], e["lactation"])
            diag = dx.get(k)
            if diag is None or e["event_date"] <= diag:
                continue
            prev = losses.get(k)
            if prev is None or e["event_date"] < prev[0]:
                losses[k] = (e["event_date"], std)

    grouped_n: Counter[str] = Counter()
    grouped_lost: Counter[str] = Counter()
    for (aid, lact) in dx:
        g = _parity(lact) if by == "parity" else "all"
        grouped_n[g] += 1
        if (aid, lact) in losses:
            grouped_lost[g] += 1

    rows = []
    for lv in _sort_levels(grouped_n):
        n = grouped_n[lv]
        k = grouped_lost[lv]
        lo, hi = wilson(k, n)
        rows.append({
            "group": lv,
            "pregnant": n,
            "lost": k,
            "share": share(k, n),
            "ci_low": round(lo, 3) if lo is not None else None,
            "ci_high": round(hi, 3) if hi is not None else None,
        })

    cases = sorted(
        [
            {
                "animal_id": aid,
                "lactation": lact,
                "diagnosed": dx[(aid, lact)].isoformat(),
                "lost_on": lost_on.isoformat(),
                "how": how,
            }
            for (aid, lact), (lost_on, how) in losses.items()
        ],
        key=lambda r: (r["lost_on"], r["animal_id"]),
    )
    heifers = sum(1 for _, lact in dx if lact == 0)
    heifer_note = f", or as a heifer: {heifers}" if heifers else ""
    definition = (
        f"Pregnancies diagnosed (first positive check in a lactation{heifer_note}) on or before {cutoff}, "
        f"{followed_days} days before the data end. Lost: an open check or an abortion after that positive check and "
        f"before the next calving, once per lactation."
    )
    return {
        "by": by,
        "followed_days": followed_days,
        "rows": rows,
        "cases": cases,
        "definition": definition,
        "source": herd.source_line(),
    }


# --- time_to_pregnancy (Kaplan-Meier + Greenwood CI + log-rank) ------------------------------------------------------

def time_to_pregnancy(herd: Herd, by: str = "none", data: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Kaplan-Meier time from calving to conception (days in milk), handling right-censored cows cleanly.

    Includes Greenwood 95% confidence bands on each survival curve point and Mantel-Haenszel log-rank p-value across
    groups (`"none"`, `"parity"`, or any column name in `lactation_data(herd)`).
    """
    end = herd.data_end
    known = end - timedelta(days=42)
    rows_in = epi.lactation_data(herd) if data is None else data
    if not rows_in:
        raise MissingDataError("No lactations calved early enough to follow.")
    need = {"fresh_date", "conception_date", "end_date"} - set(rows_in[0])
    if need:
        raise NotFoundError(f"data needs the columns of lactation_data(): missing {', '.join(sorted(need))}")
    if by != "none" and by not in rows_in[0]:
        raise NotFoundError(f"No column '{by}' in the data.")

    by_group: dict[str, tuple[list[float], list[bool]]] = defaultdict(lambda: ([], []))
    all_times: list[float] = []
    all_events: list[bool] = []
    all_groups: list[str] = []

    for r in rows_in:
        fresh = r.get("fresh_date")
        if fresh is None or fresh > known:
            continue
        if by == "none":
            g = "all"
        else:
            raw_g = r.get(by)
            if raw_g is None:
                continue
            g = ("TRUE" if raw_g else "FALSE") if isinstance(raw_g, bool) else str(raw_g)
        conc = r.get("conception_date")
        ev = conc is not None and conc <= known
        stop_at = r.get("end_date")
        if stop_at is None or stop_at > known:
            stop_at = known
        t = float((conc - fresh).days if ev else (stop_at - fresh).days)
        by_group[g][0].append(t)
        by_group[g][1].append(ev)
        all_times.append(t)
        all_events.append(ev)
        all_groups.append(g)

    if not by_group:
        raise MissingDataError("No lactations calved early enough to follow.")

    levels = _sort_levels(by_group)
    rows = []
    curves: dict[str, list[dict[str, Any]]] = {}
    for lv in levels:
        ts, evs = by_group[lv]
        curve = kaplan_meier(ts, evs)
        max_t = max(ts)

        def at(day: int) -> float | None:
            if day > max_t:
                return None
            surv = 1.0
            for u, s, _, _, _ in curve:
                if u <= day:
                    surv = s
                else:
                    break
            return round(1.0 - surv, 3)

        rows.append({
            "group": lv,
            "lactations": len(ts),
            "pregnant": sum(evs),
            "median_dim": km_median(ts, evs, interpolate_half=False),
            "pregnant_by_100": at(100),
            "pregnant_by_150": at(150),
            "pregnant_by_200": at(200),
        })
        curves[lv] = [
            {
                "dim": u,
                "surv": round(s, 6),
                "pregnant_share": round(1.0 - s, 6),
                "ci_low": round(max(0.0, (1.0 - s) - Z_95 * se), 4),
                "ci_high": round(min(1.0, (1.0 - s) + Z_95 * se), 4),
                "at_risk": n_r,
                "events": d_e,
            }
            for u, s, n_r, d_e, se in curve
        ]

    p_val = logrank_test(all_times, all_events, all_groups) if len(levels) > 1 else None
    p_text = f" Log-rank test between the groups: p = {signif(p_val, 2)}." if p_val is not None else ""
    definition = (
        f"Kaplan-Meier time from calving to conception (days in milk), lactations observed from calving. "
        f"Pregnancies count up to {known} (42 days before the data end, so they are confirmed); lactations not yet "
        f"pregnant are censored at their end (sold, died, dried off) or that date.{p_text}"
    )
    return {
        "by": by,
        "rows": rows,
        "p_value": p_val,
        "curves": curves,
        "definition": definition,
        "source": herd.source_line(),
    }


# --- calving_interval & age_first_calving ----------------------------------------------------------------------------

def calving_interval(herd: Herd, by: str = "none") -> dict[str, Any]:
    """Consecutive calving intervals (cows that calved again) and days open (fully observed conceived lactations)."""
    if by not in ("none", "parity"):
        raise DairyToolsError(f"by must be 'none' or 'parity', got {by!r}")
    lacts = [l for l in herd.lactations if (l["lactation"] or 0) >= 1 and l["fresh_date"] is not None]
    by_key = {(l["animal_id"], l["lactation"]): l for l in lacts}

    iv_by_group: dict[str, list[int]] = defaultdict(list)
    do_by_group: dict[str, list[int]] = defaultdict(list)

    for l in lacts:
        g = _parity(l["lactation"]) if by == "parity" else "all"
        nxt = by_key.get((l["animal_id"], l["lactation"] + 1))
        if nxt is not None:
            iv_by_group[g].append((nxt["fresh_date"] - l["fresh_date"]).days)
        if l["fully_observed"] and l["conception_date"] is not None and l["days_open"] is not None:
            do_by_group[g].append(l["days_open"])

    levels = _sort_levels(set(iv_by_group) | set(do_by_group))
    if not levels:
        raise MissingDataError("No calving intervals or conceptions in these records.")

    rows = []
    for lv in levels:
        xs = iv_by_group.get(lv, [])
        os = do_by_group.get(lv, [])
        rows.append({
            "group": lv,
            "intervals": len(xs),
            "median_days": median(xs) if xs else None,
            "mean_days": round(mean(xs), 1) if xs else None,
            "mean_months": round(mean(xs) / MONTH_DAYS, 1) if xs else None,
            "over_14_5_months": share(sum(1 for x in xs if x > 14.5 * MONTH_DAYS), len(xs)) if xs else None,
            "pregnant_lactations": len(os),
            "days_open_median": median(os) if os else None,
            "days_open_mean": round(mean(os), 1) if os else None,
        })

    definition = (
        "Calving interval: days from one calving to the next (consecutive lactations), cows that calved again only; "
        "a month is 30.4 days. Days open: calving to conception for lactations observed from calving that conceived "
        "(cows still open are not in it)."
    )
    return {
        "by": by,
        "rows": rows,
        "definition": definition,
        "source": herd.source_line(),
    }


def age_first_calving(herd: Herd, by: str = "none") -> dict[str, Any]:
    """Months from birth to first calving, excluding ages under 15 or over 48 months as likely entry errors."""
    if by not in ("none", "calving_year"):
        raise DairyToolsError(f"by must be 'none' or 'calving_year', got {by!r}")
    grouped: dict[str, list[float]] = defaultdict(list)
    no_birth = 0
    odd = 0
    kept = 0

    for l in herd.lactations:
        if l["lactation"] != 1 or l["fresh_date"] is None:
            continue
        cow = herd.cow_by_animal.get(l["animal_id"])
        birth = cow.get("birth_date") if cow is not None else None
        if birth is None:
            no_birth += 1
            continue
        months = (l["fresh_date"] - birth).days / MONTH_DAYS
        if months < 15 or months > 48:
            odd += 1
            continue
        kept += 1
        g = str(l["fresh_date"].year) if by == "calving_year" else "all"
        grouped[g].append(months)

    if not grouped:
        raise MissingDataError("No first calvings with a birth date in these records.")

    rows = []
    for lv in _sort_levels(grouped):
        xs = grouped[lv]
        rows.append({
            "group": lv,
            "heifers": len(xs),
            "median_months": round(median(xs), 1),
            "mean_months": round(mean(xs), 1),
            "over_24_months": share(sum(1 for x in xs if x > 24), len(xs)),
        })

    plural = lambda n: f"{n} first calving{'' if n == 1 else 's'}"
    definition = (
        f"Months (30.4 days) from birth date to first calving, for {plural(kept)} in the records."
        + (f" Left out: {plural(odd)} with an age under 15 or over 48 months (likely entry errors)." if odd else "")
        + (f" {plural(no_birth)} had no birth date." if no_birth else "")
    )
    return {
        "by": by,
        "rows": rows,
        "excluded_odd": odd,
        "excluded_no_birth": no_birth,
        "definition": definition,
        "source": herd.source_line(),
    }


# --- Beyond R: inter-service intervals & heifer reproduction (record-only, pure stdlib) ------------------------------

def inter_service_intervals(herd: Herd) -> dict[str, Any]:
    """Descriptive distribution of days between consecutive breedings within a lactation (record-only heat-detection
    pattern: short <18 d, single cycle 18-24 d, mid 25-35 d, double cycle 36-48 d, long 49+ d, and 21:42 day ratio)."""
    lacts_by_key = {(l["animal_id"], l["lactation"]): l for l in herd.lactations if (l["lactation"] or 0) >= 1}
    by_key: dict[tuple[str, int], set[date]] = defaultdict(set)
    for e in herd.events_by_std.get("breeding", ()):
        if e["event_date"] is None or e.get("lactation") is None:
            continue
        k = (e["animal_id"], e["lactation"])
        if k in lacts_by_key:
            by_key[k].add(e["event_date"])

    gaps: list[int] = []
    for ds in by_key.values():
        ordered = sorted(ds)
        for a, b in zip(ordered, ordered[1:]):
            diff = (b - a).days
            if diff > 0:
                gaps.append(diff)

    if not gaps:
        raise MissingDataError("No repeat breedings within a lactation in these records.")

    bands_spec = (
        ("under 18", lambda d: d < 18),
        ("18-24", lambda d: 18 <= d <= 24),
        ("25-35", lambda d: 25 <= d <= 35),
        ("36-48", lambda d: 36 <= d <= 48),
        ("49+", lambda d: d >= 49),
    )
    n = len(gaps)
    bands = []
    counts: dict[str, int] = {}
    for label, pred in bands_spec:
        k = sum(1 for d in gaps if pred(d))
        counts[label] = k
        bands.append({"band": label, "intervals": k, "share": share(k, n)})

    c21, c42 = counts["18-24"], counts["36-48"]
    return {
        "intervals": n,
        "median_days": median(gaps),
        "mean_days": round(mean(gaps), 1),
        "ratio_21_to_42": round(c21 / c42, 2) if c42 else None,
        "bands": bands,
        "definition": (
            "Days between consecutive distinct-day breedings within the same cow lactation (same-day repeats counted "
            "once). 18-24 d represents one estrous cycle; 36-48 d represents two cycles."
        ),
        "source": herd.source_line(),
    }


def heifer_repro(herd: Herd) -> dict[str, Any]:
    """Heifer (lactation 0) reproduction summary: age at first breeding, heifer conception risk, and pregnancy loss.

    Counts lactation-0 breeding and pregnancy-check events that cow-only reproduction measures exclude.
    """
    end = herd.data_end
    wait = 45

    heifer_bred: dict[str, list[date]] = defaultdict(list)
    for e in herd.events_by_std.get("breeding", ()):
        if e["event_date"] is not None and e.get("lactation") == 0:
            heifer_bred[e["animal_id"]].append(e["event_date"])
    for aid in heifer_bred:
        heifer_bred[aid] = sorted(set(heifer_bred[aid]))

    first_pos: dict[str, date] = {}
    for e in herd.events_by_std.get("preg_positive", ()):
        if not _is_restated_breeding(e) and e["event_date"] is not None and e.get("lactation") == 0:
            aid = e["animal_id"]
            if aid not in first_pos or e["event_date"] < first_pos[aid]:
                first_pos[aid] = e["event_date"]

    last_neg: dict[str, date] = {}
    for e in herd.events_by_std.get("preg_negative", ()):
        if not _is_restated_breeding(e) and e["event_date"] is not None and e.get("lactation") == 0:
            aid = e["animal_id"]
            if aid not in last_neg or e["event_date"] > last_neg[aid]:
                last_neg[aid] = e["event_date"]

    if not heifer_bred and not first_pos:
        raise MissingDataError("No heifer (lactation 0) breeding or pregnancy-check events in these records.")

    # Age at first breeding (months), excluding implausible <8 or >36 months.
    ages: list[float] = []
    for aid, ds in heifer_bred.items():
        cow = herd.cow_by_animal.get(aid)
        birth = cow.get("birth_date") if cow is not None else None
        if birth is None:
            continue
        mo = (ds[0] - birth).days / MONTH_DAYS
        if 8 <= mo <= 36:
            ages.append(mo)

    # Heifer conception risk.
    known_n = 0
    known_preg = 0
    unknown_n = 0
    for aid, ds in heifer_bred.items():
        pos = first_pos.get(aid)
        conc = max((d for d in ds if pos is not None and d <= pos), default=None)
        cow = herd.cow_by_animal.get(aid)
        stop = cow.get("left_date") if cow is not None else None
        neg = last_neg.get(aid)
        for idx, d in enumerate(ds, 1):
            if conc is not None and d > conc:
                break
            if conc is not None and d == conc:
                known_n += 1
                known_preg += 1
            elif idx < len(ds) or (neg is not None and neg > d) or (
                d <= end - timedelta(days=wait) and (stop is None or stop > d + timedelta(days=wait))
            ):
                known_n += 1
            else:
                unknown_n += 1

    lo, hi = wilson(known_preg, known_n) if known_n else (None, None)
    pl = pregnancy_loss(herd, by="parity")
    heifer_loss = next((r for r in pl["rows"] if r["group"] == "heifers"), None)

    return {
        "heifers_bred": len(heifer_bred),
        "age_first_breeding_n": len(ages),
        "age_first_breeding_median_months": round(median(ages), 1) if ages else None,
        "age_first_breeding_mean_months": round(mean(ages), 1) if ages else None,
        "conception": {
            "services": known_n,
            "pregnant": known_preg,
            "unknown_excluded": unknown_n,
            "share": share(known_preg, known_n),
            "ci_low": round(lo, 3) if lo is not None else None,
            "ci_high": round(hi, 3) if hi is not None else None,
        },
        "pregnancy_loss": heifer_loss,
        "definition": (
            "Heifer (lactation 0) breeding and pregnancy-check events. Age at first breeding excludes ages under 8 or "
            "over 36 months. Conception risk follows the 45-day outcome rule."
        ),
        "source": herd.source_line(),
    }
