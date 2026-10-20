"""Read DairyComp and EZfeed export files. Python standard library only, read-only, no network.

The one source for the copies in each skill's scripts/ folder (tools/sync_scripts.py copies it there, because in
Claude's chat only a skill's own folder reaches the code sandbox). Edit this file, then run the sync.

Farm notes are untrusted text: event remarks, protocols and technician names are left out unless asked for, because a
remark can carry words that read like instructions to an AI agent.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")


def read_text(path: str | Path) -> str:
    raw = Path(path).read_bytes()
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def rows_of(path: str | Path) -> list[list[str]]:
    text = read_text(path)
    return [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(text))]


def number(value: str | None) -> float | None:
    """'1,234.5', '$6.84', '57.94%', ' 77.1 ', '(1.20)' -> float (EZfeed shows negatives in brackets);
    blank or text -> None."""
    if value is None:
        return None
    text = value.strip().replace("$", "").replace(",", "").replace("%", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    if text in ("", "-", "."):
        return None
    try:
        return -float(text) if negative else float(text)
    except ValueError:
        return None


def day(value: str | None) -> date | None:
    """DairyComp and EZfeed dates: 11/20/25, 11/20/2025, 2025-11-20. Blank -> None."""
    if not value:
        return None
    text = value.strip()
    for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


# --- DairyComp -------------------------------------------------------------------------------------------------------

def read_cow_list(path: str | Path) -> list[dict[str, str]]:
    """A DairyComp SHOW (saved as CSV) or FILEOUT export with a header row: one dict per cow, keyed by item name (ID, PEN, LACT...).

    Handles the padded values a saved report has and the empty last column it often ends with."""
    rows = [row for row in rows_of(path) if any(row)]
    if not rows:
        raise ValueError(f"{path}: the file is empty")
    header = [name.upper() for name in rows[0]]
    while header and header[-1] == "":
        header.pop()
    if "ID" not in header:
        raise ValueError(f"{path}: no ID column in the first row; export the list with its header row")
    cows = []
    for row in rows[1:]:
        cow = {name: (row[i] if i < len(row) else "") for i, name in enumerate(header) if name}
        if cow.get("ID", "") == "" or cow["ID"].lower().startswith("total"):
            continue  # blank rows and DairyComp's "Total: 474" footer
        cows.append(cow)
    return cows


EVENT_COLUMNS = ("ID", "LACT", "EVENT", "DIM", "DATE")
OPTIONAL_EVENT_COLUMNS = ("BDAT",)  # cow numbers are reused: ID and birth date together name a cow
UNTRUSTED_EVENT_COLUMNS = ("REMARK", "PROTOCOLS", "TECHNICIAN")


def read_events(path: str | Path, include_remarks: bool = False) -> list[dict]:
    """A DairyComp EVENTS export (ID, BDAT, LACT, Event, DIM, Date, Remark, ...): one dict per event with a real date.

    Remarks, protocols and technicians stay out unless include_remarks is True (they are free text typed on the farm,
    and technicians are people's names)."""
    rows = [row for row in rows_of(path) if any(row)]
    header = [name.upper() for name in rows[0]]
    missing = [name for name in EVENT_COLUMNS if name not in header]
    if missing:
        raise ValueError(f"{path}: not an EVENTS export (missing {', '.join(missing)})")
    keep = list(EVENT_COLUMNS) + list(OPTIONAL_EVENT_COLUMNS) +         (list(UNTRUSTED_EVENT_COLUMNS) if include_remarks else [])
    events = []
    for row in rows[1:]:
        raw = {name: (row[i] if i < len(row) else "") for i, name in enumerate(header)}
        when = day(raw.get("DATE"))
        if not raw.get("ID") or raw["ID"].lower().startswith("total") or when is None:
            continue
        event = {name: raw.get(name, "") for name in keep if name in raw}
        event["DATE"] = when
        event["EVENT"] = event["EVENT"].upper()
        events.append(event)
    # The same event exported twice (overlapping windows) counts once.
    seen, unique = set(), []
    for e in events:
        key = tuple(str(e.get(k)) for k in keep)
        if key not in seen:
            seen.add(key)
            unique.append(e)
    return unique


def cow_key(row: dict) -> tuple[str, str]:
    """ID and birth date: a cow number can be reused by a later animal."""
    return row.get("ID", "").strip(), (row.get("BDAT") or "").strip()


DAIRYCOMP_FIGURE = re.compile(
    r"305|\bME\b|MATURE|AGE[- ]?ADJ|\bAA|AA\b|PROJ|PREDICT|RELV|RELATIVE|\bREL\b|INDEX|VALUE|PTA|MERIT|GENOMIC")


@dataclass
class Item:
    name: str
    description: str
    type_code: str
    op1: str
    op2: str

    @property
    def dairycomp_figure(self) -> bool:
        """True when the name or description marks one of DairyComp's own calculations: 305-day and age-adjusted or
        mature-equivalent yields, projections, relative values, indexes and dollar values. Work those out from the raw
        records with public methods instead. False is not a promise the item is raw: when in doubt, ask."""
        text = f"{self.name} {self.description}".upper()
        return bool(DAIRYCOMP_FIGURE.search(text)) or "$" in self.name


def read_items(path: str | Path) -> list[Item]:
    """DairyComp's item list as ALTER\\2 > Tools > Export > CSV writes it (Name, Index, Loc/Op1, Len/Op2, Type,
    Description)."""
    rows = [row for row in rows_of(path) if any(row)]
    header = [name.upper() for name in rows[0]]
    need = {"NAME": None, "LOC/OP1": None, "LEN/OP2": None, "TYPE": None, "DESCRIPTION": None}
    for key in need:
        if key not in header:
            raise ValueError(f"{path}: not an ALTER item export (no {key} column)")
        need[key] = header.index(key)
    return [
        Item(
            name=row[need["NAME"]],
            description=row[need["DESCRIPTION"]] if need["DESCRIPTION"] < len(row) else "",
            type_code=row[need["TYPE"]],
            op1=row[need["LOC/OP1"]],
            op2=row[need["LEN/OP2"]],
        )
        for row in rows[1:]
        if row and row[need["NAME"]]
    ]


# --- EZfeed ----------------------------------------------------------------------------------------------------------

@dataclass
class IngredientDay:
    pen: str
    ingredient: str
    date: date
    dm_target_lb: float | None
    dm_actual_lb: float | None
    cost_target_hd: float | None
    cost_actual_hd: float | None


@dataclass
class IntakeReport:
    """EZfeed's ingredient usage report: each pen, each ingredient, each day, in lb of dry matter a head."""

    days: list[IngredientDay] = field(default_factory=list)

    def pens(self) -> list[str]:
        return sorted({d.pen for d in self.days}, key=_natural)

    def pen_days(self, pen: str) -> dict[date, dict[str, float | None]]:
        """Day -> the pen's total DM target and actual (lb a head) and cost a head, summed over its ingredients."""
        out: dict[date, dict[str, float | None]] = {}
        for d in self.days:
            if d.pen != pen:
                continue
            total = out.setdefault(d.date, {"dm_target_lb": 0.0, "dm_actual_lb": 0.0, "cost_actual_hd": 0.0})
            for key in total:
                value = getattr(d, key)
                total[key] = None if (total[key] is None or value is None) else total[key] + value
        return dict(sorted(out.items()))

    def recipe(self, pen: str, on: date) -> dict[str, float]:
        """The pen's recipe on a day: ingredient -> target lb DM a head."""
        return {d.ingredient: d.dm_target_lb for d in self.days
                if d.pen == pen and d.date == on and d.dm_target_lb is not None}


def _natural(text: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def read_intakes(paths) -> IntakeReport:
    """Several ingredient intake exports (e.g. last fall's and this fall's) read as one; a day in two files counts once."""
    merged, seen = IntakeReport(), set()
    for path in ([paths] if isinstance(paths, (str, Path)) else paths):
        for d in read_intake(path).days:
            key = (d.pen, d.ingredient, d.date)
            if key not in seen:
                seen.add(key)
                merged.days.append(d)
    return merged


def read_intake(path: str | Path) -> IntakeReport:
    """EZfeed's ingredient usage export. Two header rows (DMTgt, DMAct, $Tgt, $Act... over IU(lbs/hd), IU($/hd)...),
    then a row per pen, a row per ingredient under it, and a row per day under each ingredient."""
    rows = rows_of(path)
    head = next((i for i, row in enumerate(rows) if row and row[0].lower() == "pen"), None)
    if head is None or head == 0:
        raise ValueError(f"{path}: not EZfeed's ingredient usage report (no 'Pen, Ingredient, Date' header row)")
    top, units = rows[head - 1], rows[head]
    labels = [f"{(top[i] if i < len(top) else '').strip()} {u}".strip() for i, u in enumerate(units)]

    def column(kind: str, unit: str) -> int:
        for i, label in enumerate(labels):
            if label.startswith(kind) and unit in label:
                return i
        raise ValueError(f"{path}: no '{kind}' column in {unit}")

    dm_t, dm_a = column("DMTgt", "lbs/hd"), column("DMAct", "lbs/hd")
    c_t, c_a = column("$Tgt", "$/hd"), column("$Act", "$/hd")
    report = IntakeReport()
    pen = ingredient = None
    for row in rows[head + 1:]:
        if not any(row):
            continue
        cell = lambda i: row[i] if i < len(row) else ""
        if cell(0):
            pen, ingredient = cell(0), None
            continue
        if cell(1):
            ingredient = cell(1)
            continue
        when = day(cell(2))
        if pen is None or ingredient is None or when is None:
            continue
        report.days.append(IngredientDay(pen, ingredient, when, number(cell(dm_t)), number(cell(dm_a)),
                                         number(cell(c_t)), number(cell(c_a))))
    if not report.days:
        raise ValueError(f"{path}: no daily rows found under the pens and ingredients")
    return report


@dataclass
class RationLine:
    ration: str
    ingredient: str
    as_fed_lb: float | None
    dm_lb: float | None
    cost_hd: float | None
    dm_pct: float | None
    price_ton_as_fed: float | None


def read_rations(path: str | Path) -> list[RationLine]:
    """EZfeed's ration (recipe) export: a row per ration with its totals, then its ingredients
    (AF lb, DM lb, $ a head a day, DM %, $ a ton as fed)."""
    rows = rows_of(path)
    head = next((i for i, row in enumerate(rows) if row and row[0].lower() == "ration"), None)
    if head is None:
        raise ValueError(f"{path}: not EZfeed's ration report (no 'Ration, Ingredient' header row)")
    lines, ration = [], None
    for row in rows[head + 1:]:
        if not any(row):
            continue
        cell = lambda i: row[i] if i < len(row) else ""
        if cell(0):
            ration = cell(0)
            continue
        if ration and cell(1):
            lines.append(RationLine(ration, cell(1), number(cell(2)), number(cell(3)), number(cell(4)),
                                    number(cell(5)), number(cell(6))))
    return lines


# --- Figures worked out here, from raw records -----------------------------------------------------------------------

def ecm_lb(milk_lb: float, fat_pct: float, protein_pct: float) -> float:
    """Energy-corrected milk, lb (Tyrrell and Reid, 1965, as DHIA uses it)."""
    return 0.327 * milk_lb + 12.95 * milk_lb * fat_pct / 100 + 7.65 * milk_lb * protein_pct / 100


def mean(values) -> float | None:
    values = [v for v in values if v is not None]
    return math.fsum(values) / len(values) if values else None   # the same answer on every Python


def percentiles(values, qs=(0.1, 0.5, 0.9)) -> tuple[float, ...] | None:
    """Linear-interpolated percentiles (the spread a pen card shows: low tenth, middle cow, high tenth)."""
    values = sorted(v for v in values if v is not None)
    if not values:
        return None

    def at(q: float) -> float:
        position = (len(values) - 1) * q
        low = int(position)
        high = min(low + 1, len(values) - 1)
        return values[low] + (values[high] - values[low]) * (position - low)

    return tuple(at(q) for q in qs)


def quartiles(values) -> tuple[float, float, float] | None:
    return percentiles(values, (0.25, 0.5, 0.75))
