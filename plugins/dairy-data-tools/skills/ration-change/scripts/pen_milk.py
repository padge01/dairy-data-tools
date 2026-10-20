"""Pen milk by day from several daily DairyComp cow-list exports, for ration_change.py --milk.

Read-only, no network, Python standard library only.

  python pen_milk.py EXPORT_2026-09-01.CSV EXPORT_2026-09-02.CSV ... --out pen_milk.csv [--item DMLK1]

Each export is one day: the date is read from the file name (2026-09-01, 20260901 or 09-01-2026), so name each saved
file by its day. Each export needs ID, PEN and the day's milk item (DMLK1 by default: each cow's milk for the day as
DairyComp holds it; export after the day's last milking). PCTF and PCTP are added when the export has them, weighted
by each cow's milk. A pen's milk is the mean of the cows in it that day with milk recorded. On Windows, a pattern
such as EXPORT_*.CSV works too.
"""

from __future__ import annotations

import argparse
import glob
import re
import sys
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True   # leave nothing behind in the skill folder
sys.path.insert(0, str(Path(__file__).resolve().parent))
from dairyread import mean, number, read_cow_list  # noqa: E402

PATTERNS = (
    (re.compile(r"(20\d\d)-(\d\d)-(\d\d)"), (1, 2, 3)),
    (re.compile(r"(20\d\d)(\d\d)(\d\d)"), (1, 2, 3)),
    (re.compile(r"(\d\d)-(\d\d)-(20\d\d)"), (3, 1, 2)),
)


def day_of(path: Path) -> date:
    for pattern, (y, m, d) in PATTERNS:
        found = pattern.search(path.stem)
        if found:
            return date(int(found.group(y)), int(found.group(m)), int(found.group(d)))
    raise SystemExit(f"{path.name}: no date in the file name (name it like cows_2026-09-01.csv)")


def weighted(group, item, milk_item):
    """The pen's percentage weighted by each cow's milk, over the cows that have both."""
    pairs = [(number(c.get(milk_item)), number(c.get(item))) for c in group]
    pairs = [(m, v) for m, v in pairs if m and v]
    total = sum(m for m, _ in pairs)
    return sum(m * v for m, v in pairs) / total if total else None


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("exports", nargs="+")
    p.add_argument("--out", required=True)
    p.add_argument("--item", default="DMLK1")
    a = p.parse_args(argv)
    # Windows shells hand patterns over unexpanded.
    names = [m for n in a.exports for m in (sorted(glob.glob(n)) if any(ch in n for ch in "*?[") else [n])]
    if not names:
        raise SystemExit("No export matches: " + " ".join(a.exports))
    rows = ["date,pen,milk_lb,fat_pct,protein_pct,cows"]
    for name in sorted(names, key=lambda n: day_of(Path(n))):
        when = day_of(Path(name))
        cows = [c for c in read_cow_list(name) if not c.get("ARDAT") and number(c.get(a.item.upper()))]
        if not cows:
            print(f"{Path(name).name}: no cow has {a.item}; left out", file=sys.stderr)
            continue
        for pen in sorted({c.get("PEN", "") for c in cows}, key=lambda x: (len(x), x)):
            group = [c for c in cows if c.get("PEN", "") == pen]
            fat, protein = weighted(group, "PCTF", a.item.upper()), weighted(group, "PCTP", a.item.upper())
            cell = lambda v, places: "" if v is None else f"{v:.{places}f}"
            rows.append(f"{when.isoformat()},{pen},{mean(number(c[a.item.upper()]) for c in group):.2f},"
                        f"{cell(fat, 2)},{cell(protein, 2)},{len(group)}")
    Path(a.out).write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"{len(rows) - 1} pen-days written to {a.out}")


if __name__ == "__main__":
    main()
