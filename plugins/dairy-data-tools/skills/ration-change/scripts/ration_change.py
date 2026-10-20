"""A pen's ration change, before and after, and whether the season alone could explain the difference.

Read-only, no network, Python standard library only.

  python ration_change.py --intake INTAKE.CSV [MORE.CSV ...] --pen 21 [--change 2026-09-28] [--to 2026-10-28]
                          [--weeks 1] [--milk PEN_MILK.CSV] [--compare-pen 22] [--json out.json]

--intake   EZfeed's ingredient intake export(s): the recipe (target lb of dry matter a cow) and what was fed, by day.
           Give last year's export too, for the season check.
--change   the day the new recipe started. Left out, the latest recipe change in the export is used.
--to       the last day to look at (default: the latest day in the files).
--weeks    the weeks compared: the N weeks before the change against the N weeks up to --to (default 1).
--milk     optional pen milk by day: a CSV with date, pen, milk_lb and, if known, fat_pct and protein_pct (pen_milk.py
           builds it from daily DairyComp cow lists).
--compare-pen  a pen whose recipe did not change in the same weeks: its change over the same days is the season's.

A recipe change is a change in what goes in (a feed added or taken off, or a feed's share of the dry matter moving by
half a point or more). A change in how much the pen is called for, with the same recipe, is listed separately.

The season check: the same weeks a year earlier (when the files reach back that far), or a pen with no change over the
same days. Without either, the script says the change and the season cannot be told apart.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.dont_write_bytecode = True   # leave nothing behind in the skill folder
try:   # inside the installed package
    from .dairyread import day, ecm_lb, mean, number, read_intakes, read_text
except ImportError:   # run as a script from the skill's folder
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from dairyread import day, ecm_lb, mean, number, read_intakes, read_text  # noqa: E402

SHARE_POINTS = 0.5  # a feed's share of the DM must move this many points to count as a recipe change
CALL_LB = 0.5       # the pen's total call must move this many lb to count as a call change


def shares(recipe: dict[str, float]) -> dict[str, float]:
    total = sum(recipe.values())
    return {k: 100 * v / total for k, v in recipe.items()} if total else {}


def changes(intake, pen: str) -> tuple[list[date], list[date]]:
    """(recipe change days, call change days) for a pen."""
    days = sorted({d.date for d in intake.days if d.pen == pen})
    recipe_days, call_days = [], []
    for before, after in zip(days, days[1:]):
        if (after - before).days > 1:
            continue  # a gap between exports, not a change
        a, b = intake.recipe(pen, before), intake.recipe(pen, after)
        sa, sb = shares(a), shares(b)
        if set(a) != set(b) or any(abs(sa[k] - sb[k]) >= SHARE_POINTS for k in sa):
            recipe_days.append(after)
        elif abs(sum(a.values()) - sum(b.values())) >= CALL_LB:
            call_days.append(after)
    return recipe_days, call_days


def recipe_mean(intake, pen: str, start: date, end: date) -> dict[str, float]:
    days = [d for d in intake.days if d.pen == pen and start <= d.date <= end and d.dm_target_lb is not None]
    dates = {d.date for d in days}
    totals: dict[str, float] = {}
    for d in days:
        totals[d.ingredient] = totals.get(d.ingredient, 0.0) + d.dm_target_lb
    return {k: round(v / len(dates), 2) for k, v in totals.items()} if dates else {}


def read_pen_milk(path: str) -> dict[tuple[str, date], dict[str, float | None]]:
    out = {}
    for row in csv.DictReader(read_text(path).splitlines()):
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        when = day(row.get("date"))
        if when is None:
            continue
        milk, fat, protein = number(row.get("milk_lb")), number(row.get("fat_pct")), number(row.get("protein_pct"))
        out[(row.get("pen", ""), when)] = {
            "milk_lb": milk,
            "ecm_lb": ecm_lb(milk, fat, protein) if None not in (milk, fat, protein) else None,
        }
    return out


def window_mean(series: dict[date, float | None], start: date, end: date) -> tuple[float | None, int]:
    values = [v for d, v in series.items() if start <= d <= end and v is not None]
    return mean(values), len(values)


def shift(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year + years, day=28)


def compare(series: dict[date, float | None], change: date, to: date, weeks: int) -> dict:
    """The N weeks before the change against the N weeks up to `to`; and the same days a year earlier."""
    span = timedelta(days=7 * weeks)
    after_start = max(change, to - span + timedelta(days=1))

    def one(c: date, t: date, s: date) -> dict:
        before, nb = window_mean(series, c - span, c - timedelta(days=1))
        after, na = window_mean(series, s, t)
        return {"before": before, "after": after, "days_before": nb, "days_after": na,
                "difference": None if None in (before, after) or nb < 3 or na < 3 else after - before,
                "before_days": f"{(c - span).isoformat()} to {(c - timedelta(days=1)).isoformat()}",
                "after_days": f"{s.isoformat()} to {t.isoformat()}"}

    out = one(change, to, after_start)
    last = one(shift(change, -1), shift(to, -1), shift(after_start, -1))
    if last["difference"] is not None:
        out["last_year"] = last
    return out


def season_check(own: dict, other: dict | None, label: str) -> dict:
    if own.get("difference") is None:
        return {"measure": label, "verdict": "not enough days on one side of the change"}
    base = None
    if "last_year" in own:
        base = ("the same weeks last year", own["last_year"]["difference"])
    elif other and other.get("difference") is not None:
        base = ("the comparison pen, same days", other["difference"])
    if base is None:
        return {"measure": label, "change": own["difference"],
                "verdict": "no season check: the files don't reach back a year and there is no comparison pen, so "
                           "the change and the season cannot be told apart"}
    return {"measure": label, "change": own["difference"], "season_from": base[0], "season": base[1],
            "left_for_the_ration": own["difference"] - base[1]}


def find_pen(names, pen: str) -> str | None:
    digits = lambda s: "".join(c for c in s if c.isdigit()).lstrip("0")
    return next((n for n in names if n == pen), None) or \
        next((n for n in names if digits(pen) and digits(n) == digits(pen)), None)


def analyse(intake_paths, pen, change=None, to=None, weeks=1, milk_path=None, compare_pen=None) -> dict:
    intake = read_intakes(intake_paths)
    names = intake.pens()
    name = find_pen(names, pen)
    if name is None:
        raise SystemExit(f"No EZfeed pen {pen}. Pens: {', '.join(names)}")
    pen = name
    recipe_days, call_days = changes(intake, pen)
    last_day = max(d.date for d in intake.days if d.pen == pen)
    to = to or last_day
    if change is None:
        candidates = [d for d in recipe_days if d <= to]
        if not candidates:
            raise SystemExit(f"{pen}'s recipe did not change in these files"
                             + (f" (its call changed on {', '.join(d.isoformat() for d in call_days)})" if call_days
                                else "") + ". Give --change to look at a day anyway.")
        change = candidates[-1]
    span = timedelta(days=7 * weeks)
    out = {
        "pen": pen,
        "change": change.isoformat(),
        "to": to.isoformat(),
        "weeks": weeks,
        "recipe_changes_found": [d.isoformat() for d in recipe_days],
        "call_changes_found": [d.isoformat() for d in call_days],
        "recipe_before": recipe_mean(intake, pen, change - span, change - timedelta(days=1)),
        "recipe_after": recipe_mean(intake, pen, max(change, to - span + timedelta(days=1)), to),
        "results": {},
        "season_checks": [],
        "notes": [],
    }
    later = [d for d in recipe_days if change < d <= to]
    if later:
        out["notes"].append(f"The recipe changed again on {', '.join(d.isoformat() for d in later)}, before {to}.")

    other_pen = None
    if compare_pen:
        other_pen = find_pen(names, compare_pen)
        if other_pen is None:
            out["notes"].append(f"No EZfeed pen {compare_pen} to compare with.")
        elif any(change - span <= d <= to for d in changes(intake, other_pen)[0]):
            out["notes"].append(f"{other_pen}'s recipe also changed in these weeks, so it is a weak comparison.")

    def pen_series(p: str, key: str) -> dict[date, float | None]:
        return {d: v[key] for d, v in intake.pen_days(p).items()}

    for key, label in (("dm_actual_lb", "intake, lb DM a cow a day"), ("cost_actual_hd", "feed cost, $ a cow a day")):
        own = compare(pen_series(pen, key), change, to, weeks)
        other = compare(pen_series(other_pen, key), change, to, weeks) if other_pen else None
        out["results"][label] = own
        out["season_checks"].append(season_check(own, other, label))

    if milk_path:
        milk = read_pen_milk(milk_path)
        in_file = sorted({p for p, _ in milk})
        mine = find_pen(in_file, pen)
        if mine is None:
            out["notes"].append(f"The milk file has no pen {pen} (it has {', '.join(in_file)}).")
        else:
            theirs = find_pen(in_file, compare_pen) if compare_pen else None
            for key, label in (("milk_lb", "milk, lb a cow a day"), ("ecm_lb", "ECM, lb a cow a day")):
                series = {d: v[key] for (p, d), v in milk.items() if p == mine}
                if not any(v is not None for v in series.values()):
                    continue
                own = compare(series, change, to, weeks)
                other = None
                if theirs:
                    other = compare({d: v[key] for (p, d), v in milk.items() if p == theirs}, change, to, weeks)
                out["results"][label] = own
                out["season_checks"].append(season_check(own, other, label))
    return out


def signed(v, places=1):
    return "n/a" if v is None else f"{v:+,.{places}f}"


def summary(r: dict) -> str:
    lines = [f"{r['pen']}: recipe change on {r['change']}; the {r['weeks']} week(s) before it against the "
             f"{r['weeks']} week(s) to {r['to']}."]
    before, after = r["recipe_before"], r["recipe_after"]
    moved = []
    for name in sorted(set(before) | set(after)):
        b, a = before.get(name, 0.0), after.get(name, 0.0)
        if abs(a - b) >= 0.25:
            moved.append(f"{name} {b:.1f} -> {a:.1f}")
    lines.append("Recipe, lb DM a cow: " + ("; ".join(moved) if moved else "no feed moved by a quarter pound") +
                 f" (total {sum(before.values()):.1f} -> {sum(after.values()):.1f}).")
    for check in r["season_checks"]:
        if "left_for_the_ration" in check:
            lines.append(f"{check['measure']}: {signed(check['change'])} since the change; {check['season_from']} "
                         f"{signed(check['season'])}; left for the ration {signed(check['left_for_the_ration'])}.")
        else:
            lines.append(f"{check['measure']}: {signed(check.get('change'))} ({check['verdict']}).")
    lines += r["notes"]
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--intake", required=True, nargs="+")
    p.add_argument("--pen", required=True)
    p.add_argument("--change", help="YYYY-MM-DD; default: the latest recipe change in the export")
    p.add_argument("--to", help="YYYY-MM-DD; default: the latest day in the files")
    p.add_argument("--weeks", type=int, default=1)
    p.add_argument("--milk")
    p.add_argument("--compare-pen")
    p.add_argument("--json")
    a = p.parse_args(argv)
    r = analyse(a.intake, a.pen, day(a.change) if a.change else None, day(a.to) if a.to else None, a.weeks,
                a.milk, a.compare_pen)
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1), encoding="utf-8")
    print(summary(r))


if __name__ == "__main__":
    main()
