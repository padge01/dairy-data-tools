"""Write the sample herd: a made-up California dairy's DairyComp and EZfeed exports, in the layouts the kit reads.

Not a real farm. The base is the Rossow Data Lab's own simulator (tools/sample-herd-lab, written by its simulate.R
with vmtrc's simulate_herd: three years of events, cow and test-day reports, the item list, EZfeed's pen summaries,
feeder loads and refusals). On it goes the ARPAS talk's story: on 28 Sep 2026 pen 21 (older cows) went onto the new
corn silage pile and its recipe changed (half a pound more bypass fat, half a pound less rolled corn, more canola
meal) as the heat lifted. Pen 11 (first lactation) kept its recipe. Last fall, pen 21 had no change in the same weeks,
so the season check can be done both ways. Pen 21's test milk is scaled so the pen averages 89.8 lb ECM, the deck's
figure.

  python tools/make_sample_herd.py   (writes plugins/dairy-data-tools/sample-herd/; fixed seeds, same files every run)
"""

from __future__ import annotations

import csv
import io as _io
import math
import random
import shutil
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from dairytools import io as dio  # noqa: E402
from dairytools.herd import load  # noqa: E402
from dairytools.stats import ecm_lb, mean  # noqa: E402

LAB = ROOT / "tools" / "sample-herd-lab"
OUT = ROOT / "plugins" / "dairy-data-tools" / "sample-herd"
TODAY = date(2026, 10, 28)
CHANGE = date(2026, 9, 28)
BS = chr(92)

# --- feeds: dry matter % and price a ton as fed (examples, not market prices) ----------------------------------------
FEEDS = {
    "Corn silage, 2025 pile": (35.0, 62.0),
    "Corn silage, 2026 pile": (32.0, 60.0),
    "Alfalfa hay": (90.0, 285.0),
    "Wheat silage": (36.0, 55.0),
    "Almond hulls": (90.0, 210.0),
    "Rolled corn": (86.0, 310.0),
    "Whole cottonseed": (91.0, 395.0),
    "Canola meal": (90.0, 390.0),
    "Distillers grains": (90.0, 265.0),
    "Soybean meal": (89.0, 470.0),
    "Molasses": (75.0, 260.0),
    "Bypass fat": (98.0, 1450.0),
    "Lactation mineral": (98.0, 820.0),
    "Wheat straw": (91.0, 120.0),
    "Dry cow mineral": (98.0, 760.0),
}

# Recipes, lb of dry matter a cow a day, as formulated (the deck's high-cow recipe before and after the change).
HIGH_BEFORE = {"Corn silage, 2025 pile": 16.0, "Alfalfa hay": 8.5, "Wheat silage": 2.5, "Almond hulls": 3.5,
               "Rolled corn": 12.5, "Whole cottonseed": 4.0, "Canola meal": 6.0, "Distillers grains": 2.0,
               "Soybean meal": 2.5, "Molasses": 0.5, "Bypass fat": 0.5, "Lactation mineral": 1.5}
HIGH_AFTER = {"Corn silage, 2026 pile": 17.5, "Alfalfa hay": 9.0, "Wheat silage": 2.5, "Almond hulls": 3.5,
              "Rolled corn": 12.0, "Whole cottonseed": 4.0, "Canola meal": 7.0, "Distillers grains": 2.0,
              "Soybean meal": 2.5, "Molasses": 0.5, "Bypass fat": 1.0, "Lactation mineral": 1.5}
FRESH = {"Corn silage, 2025 pile": 14.0, "Alfalfa hay": 10.0, "Rolled corn": 9.0, "Canola meal": 5.0,
         "Soybean meal": 3.0, "Almond hulls": 1.5, "Lactation mineral": 1.2}
DRY = {"Wheat straw": 9.0, "Corn silage, 2025 pile": 9.0, "Alfalfa hay": 5.0, "Canola meal": 2.0,
       "Dry cow mineral": 1.2}


def ease(a, b, start, end, x):
    if x <= start:
        return a
    if x >= end:
        return b
    return a + (b - a) * (0.5 - math.cos((x - start) / (end - start) * math.pi) / 2)


def along(anchors, x):
    """Smooth path through (day, value) anchors; day 0 is 15 Aug."""
    for (d0, v0), (d1, v1) in zip(anchors, anchors[1:]):
        if x <= d1:
            return ease(v0, v1, d0, d1, x)
    return anchors[-1][1]


# Pen paths from 15 Aug (day 0) to 28 Oct (day 74): dry matter intake, milk, fat, protein. Pen 21 this fall is the
# deck's; last fall and pen 11 have the season only (no dip in early October, about half the rise from late September).
PEN21_2026 = {"dmi": [(0, 56.5), (17, 57.0), (43, 59.0), (51, 59.5), (58, 60.5), (66, 61.2), (74, 61.5)],
              "milk": [(0, 84.0), (17, 84.5), (43, 86.5), (51, 85.5), (58, 86.5), (66, 87.5), (74, 88.0)],
              "fat": [(0, 3.40), (17, 3.42), (43, 3.46), (51, 3.50), (58, 3.55), (66, 3.58), (74, 3.60)],
              "protein": [(0, 2.88), (17, 2.89), (43, 2.92), (51, 2.93), (58, 2.96), (66, 2.98), (74, 3.00)]}
SEASON = {"dmi": [(0, 56.0), (17, 56.4), (43, 58.0), (51, 58.4), (58, 58.8), (66, 59.2), (74, 59.5)],
          "milk": [(0, 83.0), (17, 83.3), (43, 85.0), (51, 85.3), (58, 85.6), (66, 85.9), (74, 86.1)],
          "fat": [(0, 3.40), (17, 3.41), (43, 3.44), (51, 3.46), (58, 3.47), (66, 3.48), (74, 3.49)],
          "protein": [(0, 2.88), (17, 2.88), (43, 2.91), (51, 2.92), (58, 2.93), (66, 2.94), (74, 2.95)]}


def shifted(path, dmi=0.0, milk=0.0):
    return {k: [(d, v + (dmi if k == "dmi" else milk if k == "milk" else 0)) for d, v in pts] for k, pts in path.items()}


def money(x: float) -> str:
    return f"${x:,.2f}" if x >= 0 else f"(${-x:,.2f})"


def quoted(x: str) -> str:
    return f'"{x}"' if "," in x else x


def called(path, d: date, year_start: date) -> float:
    """The pen's call follows appetite in half-pound steps, changed on Mondays."""
    monday = d - timedelta(days=d.weekday())
    return round(along(path["dmi"], max(0, (monday - year_start).days)) * 2) / 2


# --- EZfeed: each pen's feeds by day ---------------------------------------------------------------------------------

def feed_days(first: date, last: date, pens: dict, rnd: random.Random) -> dict:
    """pens: name -> function(day) -> (recipe, called lb DM). Returns {pen: {feed: [(day, target, fed, $t, $f)]}}."""
    out = {}
    for pen, plan in pens.items():
        rows: dict[str, list] = {}
        d = first
        while d <= last:
            recipe, call = plan(d)
            scale = call / sum(recipe.values())
            fed = 1 + rnd.uniform(-0.012, 0.012)
            for feed, lb in recipe.items():
                dm, price = FEEDS[feed]
                per_lb_dm = price / 2000 / (dm / 100)
                t = lb * scale
                a = t * fed * (1 + rnd.uniform(-0.01, 0.01))
                rows.setdefault(feed, []).append((d, round(t, 2), round(a, 2), t * per_lb_dm, a * per_lb_dm))
            d += timedelta(days=1)
        out[pen] = rows
    return out


def intake_lines(days_by_pen: dict, heads: dict) -> list[str]:
    lines = [",,,DMTgt,DMAct,$Tgt,$Act,$Tgt,$Act", "Pen,Ingredient,Date,IU(lbs/hd),IU(lbs/hd),IU($/hd),IU($/hd),IU($),IU"]
    for pen, rows in days_by_pen.items():
        head = heads[pen]
        every = [r for feed_rows in rows.values() for r in feed_rows]
        n = len({r[0] for r in every})
        lines.append(f"{pen},,,{sum(r[1] for r in every) / n:.2f},{sum(r[2] for r in every) / n:.2f},"
                     f"{money(sum(r[3] for r in every) / n)},{money(sum(r[4] for r in every) / n)},"
                     f"\"{money(sum(r[3] for r in every) * head)}\",\"{money(sum(r[4] for r in every) * head)}\"")
        for feed, feed_rows in rows.items():
            k = len(feed_rows)
            lines.append(f",{quoted(feed)},,{sum(r[1] for r in feed_rows) / k:.2f},{sum(r[2] for r in feed_rows) / k:.2f},"
                         f"{money(sum(r[3] for r in feed_rows) / k)},{money(sum(r[4] for r in feed_rows) / k)},"
                         f"\"{money(sum(r[3] for r in feed_rows) * head)}\",\"{money(sum(r[4] for r in feed_rows) * head)}\"")
            for d, t, a, ct, ca in feed_rows:
                lines.append(f",,{d.month}/{d.day}/{d.year},{t:.2f},{a:.2f},{money(ct)},{money(ca)},"
                             f"\"{money(ct * head)}\",\"{money(ca * head)}\"")
    return lines


def day_totals(days_by_pen: dict) -> dict:
    """{(pen, day): (lb DM fed per head, $ per head)}."""
    out = defaultdict(lambda: [0.0, 0.0])
    for pen, rows in days_by_pen.items():
        for feed_rows in rows.values():
            for d, _, a, _, ca in feed_rows:
                out[(pen, d)][0] += a
                out[(pen, d)][1] += ca
    return out


def rations_lines():
    lines = [",,AF,DM,$,DM,AF$", "Ration,Ingredient,AF(#/h/d),DM(#/h/d),($/h/d),DM %,AF($/ton)"]
    for name, recipe in (("Fresh", FRESH), ("Older cows (pen 21)", HIGH_AFTER), ("First lactation (pen 11)", HIGH_BEFORE),
                         ("Dry", DRY)):
        af = {f: lb / (FEEDS[f][0] / 100) for f, lb in recipe.items()}
        cost = {f: af[f] * FEEDS[f][1] / 2000 for f in recipe}
        total_af, total_dm = sum(af.values()), sum(recipe.values())
        lines.append(f"{quoted(name)},,{total_af:.2f},{total_dm:.2f},{money(sum(cost.values()))},"
                     f"{100 * total_dm / total_af:.2f}%,{money(2000 * sum(cost.values()) / total_af)}")
        for f, lb in recipe.items():
            lines.append(f",{quoted(f)},{af[f]:.2f},{lb:.2f},{money(cost[f])},{FEEDS[f][0]:.2f}%,{money(FEEDS[f][1])}")
    return lines


def pen_milk_lines(paths: dict, rnd: random.Random):
    """paths: {year: {pen: (path, cows)}}; one line per pen per day, 15 Aug to 28 Oct (31 Oct last year)."""
    rows = ["date,pen,milk_lb,fat_pct,protein_pct,cows"]
    for year, pens in paths.items():
        start = date(year, 8, 15)
        for i in range(75 if year == 2026 else 78):
            d = start + timedelta(days=i)
            for pen, (path, cows) in pens.items():
                milk = along(path["milk"], i) + rnd.uniform(-0.8, 0.8)
                fat = along(path["fat"], i) + rnd.uniform(-0.025, 0.025)
                protein = along(path["protein"], i) + rnd.uniform(-0.012, 0.012)
                rows.append(f"{d.isoformat()},{pen},{milk:.1f},{fat:.2f},{protein:.2f},{cows}")
    return rows


# --- the lab's files, adjusted ---------------------------------------------------------------------------------------

def read_rows(path):
    return list(csv.reader(_io.StringIO("\n".join(dio.read_lines(path)))))


def write_rows(path, rows):
    buf = _io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    path.write_text(buf.getvalue(), encoding="utf-8", newline="\n")


def scale_milk(rows, keys: set, factor: float):
    header = [h.strip().upper() for h in rows[0]]
    i_id, i_b, i_m = header.index("ID"), header.index("BDAT"), header.index("MILK")
    for r in rows[1:]:
        if len(r) > i_m and (r[i_id].strip(), r[i_b].strip()) in keys and dio.number(r[i_m]):
            r[i_m] = f"{dio.number(r[i_m]) * factor:.1f}"
    return rows


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    lab = load(LAB)
    milking = [c for c in lab.in_herd() if lab.status(c) == "milking"]

    # Pen 21's test milk scaled so the pen averages 89.8 lb ECM (the deck's figure).
    p21 = [c for c in milking if c["pen"] == "21" and (c.get("test_milk") or 0) > 0 and c.get("test_fat_pct")
           and c.get("test_protein_pct")]
    factor = 89.8 / mean(ecm_lb(c["test_milk"], c["test_fat_pct"], c["test_protein_pct"]) for c in p21)
    keys = {(c["cow_id"], f"{c['birth_date']:%m/%d/%y}") for c in p21}
    write_rows(OUT / "cows_2026-10-28.csv", scale_milk(read_rows(LAB / "herd report 1.csv"), keys, factor))
    write_rows(OUT / "tests_2026-10-28.csv", scale_milk(read_rows(LAB / "test day summary.csv"), keys, factor))
    shutil.copyfile(LAB / "item list.csv", OUT / "items.csv")
    for name in ("FeederLoad Summary.csv", "Pen Summary (Dry Cows).csv", "Refusal Summary.csv"):
        shutil.copyfile(LAB / name, OUT / name)

    # Three years of events in yearly files (each under the directory's size limit).
    rows = read_rows(LAB / "events 3 years.csv")
    i_date = [h.strip().upper() for h in rows[0]].index("DATE")
    for k in range(3):
        start = date(2023 + k, 10, 29)
        end = date(2024 + k, 10, 28)
        part = [r for r in rows[1:] if len(r) > i_date and (d := dio.parse_dc_date(r[i_date], TODAY)) and start <= d <= end]
        write_rows(OUT / f"events_{start}_{end}.csv", [rows[0]] + part)

    # The story's feeding: pen 11 kept at its own level, pen 21 the deck's path.
    heads = {f"Pen {p}": sum(1 for c in lab.in_herd() if c["pen"] == p) for p in ("1", "11", "21", "40", "41")}
    p11_milk = mean(c["test_milk"] for c in milking if c["pen"] == "11" and (c.get("test_milk") or 0) > 0)
    pen11 = shifted(SEASON, dmi=45.5 - SEASON["dmi"][-1][1], milk=p11_milk - SEASON["milk"][-1][1])
    s25, s26 = date(2025, 8, 15), date(2026, 8, 15)
    rnd = random.Random(2026)
    last_fall = feed_days(s25, date(2025, 10, 31), {
        "Pen 11": lambda d: (HIGH_BEFORE, called(pen11, d, s25)),
        "Pen 21": lambda d: (HIGH_BEFORE, called(SEASON, d, s25))}, rnd)
    this_fall = feed_days(s26, TODAY, {
        "Pen 1": lambda d: (FRESH, 43.0),
        "Pen 11": lambda d: (HIGH_BEFORE, called(pen11, d, s26)),
        "Pen 21": lambda d: (HIGH_AFTER if d >= CHANGE else HIGH_BEFORE, called(PEN21_2026, d, s26)),
        "Pen 40": lambda d: (DRY, 26.0),
        "Pen 41": lambda d: (DRY, 26.0)}, rnd)
    (OUT / "intake_2025-08-15_2025-10-31.csv").write_text("\n".join(intake_lines(last_fall, heads)) + "\n",
                                                          encoding="utf-8", newline="\n")
    (OUT / "intake_2026-08-15_2026-10-28.csv").write_text("\n".join(intake_lines(this_fall, heads)) + "\n",
                                                          encoding="utf-8", newline="\n")
    (OUT / "rations_2026-10-28.csv").write_text("\n".join(rations_lines()) + "\n", encoding="utf-8", newline="\n")

    # The lab's milking pen summary carries the same days for pens 11 and 21.
    totals = day_totals(this_fall)
    rows = read_rows(LAB / "Pen Summary (Milking Cows).csv")
    pen = None
    for r in rows[2:]:
        if len(r) > 2 and r[1].strip() and not r[2].strip():
            pen = r[1].strip()
        d = dio.ez_date(r[2]) if len(r) > 2 else None
        if d and pen in ("Pen 11", "Pen 21"):
            dm, cost = totals.get((pen, max(d, s26)), (None, None))
            if dm is not None:
                head = dio.number(r[10]) or heads[pen]
                r[3], r[4], r[5] = f"{dm:.2f}", money(cost), money(cost * head)
    write_rows(OUT / "Pen Summary (Milking Cows).csv", rows)

    (OUT / "pen_milk.csv").write_text("\n".join(pen_milk_lines({
        2025: {"11": (pen11, heads["Pen 11"]), "21": (SEASON, heads["Pen 21"])},
        2026: {"11": (pen11, heads["Pen 11"]), "21": (PEN21_2026, heads["Pen 21"])}}, random.Random(71))) + "\n",
        encoding="utf-8", newline="\n")
    (OUT / "event_map.csv").write_text("dc_code,remark_pattern,std_event,category\nKETONE,,ketosis,health\n"
                                       "BATH,,footbath,procedure\n", encoding="utf-8", newline="\n")
    (OUT / "README.md").write_text(README, encoding="utf-8", newline="\n")
    for path in sorted(OUT.iterdir()):
        print(f"{path.stat().st_size / 1024:7.1f} KiB  {path.name}")


README = f"""# Sample herd

A made-up California dairy's exports, for trying every skill. **Not a real farm**: it comes from the Rossow Data Lab's
herd simulator, with a ration-change story laid over it by `tools/make_sample_herd.py` in the repository.

| File | What it is | From |
| --- | --- | --- |
| `cows_2026-10-28.csv`, `tests_2026-10-28.csv` | Every animal on 28 Oct 2026 (in the herd, sold and dead), and each cow's tests | DairyComp SHOW reports, saved as CSV |
| `events_*.csv` | Three years of events, one file a year | DairyComp EVENTS |
| `items.csv` | The farm's item list | DairyComp ALTER{BS}2 export |
| `intake_2026-08-15_2026-10-28.csv`, `intake_2025-08-15_2025-10-31.csv` | Each pen's daily feed, this fall and last | EZfeed Ingredient Intake Tgt vs Act by Pen |
| `Pen Summary (Milking Cows).csv`, `Pen Summary (Dry Cows).csv` | Each pen's daily intake, cost and head count | EZfeed |
| `FeederLoad Summary.csv`, `Refusal Summary.csv` | Loading by feeder; refusals | EZfeed |
| `rations_2026-10-28.csv` | Today's recipes | EZfeed Rations |
| `pen_milk.csv` | Pens 11 and 21's milk, fat and protein by day, both falls | what `pen_milk.py` makes from daily cow reports |
| `event_map.csv` | What this farm's own event codes mean | written once for the farm |

The story: on 28 Sep 2026 pen 21 (older cows) went onto the new corn silage pile, with more canola meal, half a pound
more bypass fat and half a pound less rolled corn, as the heat lifted. Pen 11 (first lactation) kept its recipe. Try:

- "How is pen 21 doing?" and "What's pen 21's feed efficiency and IOFC at $21.50 milk?"
- "Did pen 21's ration change on 28 Sep work, or is it just the season?"
- "Get me ready for a visit: fresh cows, components, mastitis, pregnancy rate."
- "Write me a DairyComp command for the cows in pen 21 under 60 days in milk."
"""


if __name__ == "__main__":
    main()
