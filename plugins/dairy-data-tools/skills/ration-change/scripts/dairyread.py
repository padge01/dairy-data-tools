"""Read DairyComp and EZfeed export files. Python standard library only, read-only, no network.

Thin compatibility facade delegating DairyComp and EZfeed parsing to `dairytools.io` and statistics to
`dairytools.stats`, so export parsing lives in one place while `ration_change.py`, `pen_milk.py`,
`tools/sync_scripts.py`, and PyPI CLI entrypoints keep working identically.

Farm notes are untrusted text: event remarks, protocols and technician names are left out unless asked for, because a
remark can carry words that read like instructions to an AI agent.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

try:   # inside the installed package (dairytools.dairyread)
    from . import io as _io
    from . import stats as _stats
except ImportError:   # run from tools/ or a skill's scripts/ folder
    _here = str(Path(__file__).resolve().parent)
    if _here not in sys.path:
        sys.path.insert(0, _here)
    from dairytools import io as _io  # noqa: E402
    from dairytools import stats as _stats  # noqa: E402

ENCODINGS = _io.ENCODINGS
read_text = _io.read_text
rows_of = _io.rows_of
number = _io.number
day = _io.parse_dc_date


# --- DairyComp -------------------------------------------------------------------------------------------------------

def read_cow_list(path: str | Path) -> list[dict[str, str]]:
    """A DairyComp SHOW (saved as CSV) or FILEOUT export with a header row: one dict per cow, keyed by item name (ID, PEN, LACT...).

    Handles the padded values a saved report has and the empty last column it often ends with."""
    raw_rows = _io.read_dc_export(path)
    if not raw_rows or "ID" not in raw_rows[0]:
        raise ValueError(f"{path}: no ID column in the first row; export the list with its header row")
    cows = []
    for row in raw_rows:
        cow = {k: ("" if v is None else v) for k, v in row.items() if k and k != "_spilled"}
        if not cow.get("ID") or cow["ID"].lower().startswith("total"):
            continue
        cows.append(cow)
    return cows


EVENT_COLUMNS = ("ID", "LACT", "EVENT", "DIM", "DATE")
OPTIONAL_EVENT_COLUMNS = ("BDAT",)  # cow numbers are reused: ID and birth date together name a cow
UNTRUSTED_EVENT_COLUMNS = ("REMARK", "PROTOCOLS", "TECHNICIAN")


def read_events(path: str | Path, include_remarks: bool = False) -> list[dict]:
    """A DairyComp EVENTS export (ID, BDAT, LACT, Event, DIM, Date, Remark, ...): one dict per event with a real date.

    Remarks, protocols and technicians stay out unless include_remarks is True (they are free text typed on the farm,
    and technicians are people's names). Deduplication runs on the full row before dropping untrusted columns so
    event counts do not depend on `include_remarks`."""
    raw_rows = _io.read_dc_export(path)
    header = set(raw_rows[0]) if raw_rows else set()
    missing = [name for name in EVENT_COLUMNS if name not in header]
    if missing:
        raise ValueError(f"{path}: not an EVENTS export (missing {', '.join(missing)})")
    all_cols = list(EVENT_COLUMNS) + list(OPTIONAL_EVENT_COLUMNS) + list(UNTRUSTED_EVENT_COLUMNS)
    keep = list(EVENT_COLUMNS) + list(OPTIONAL_EVENT_COLUMNS) + (
        list(UNTRUSTED_EVENT_COLUMNS) if include_remarks else []
    )
    seen, unique = set(), []
    for raw in raw_rows:
        cid = raw.get("ID") or ""
        when = day(raw.get("DATE"))
        if not cid or cid.lower().startswith("total") or when is None:
            continue
        full_key = tuple(
            when.isoformat() if k == "DATE" else (raw.get(k) or "").upper() if k == "EVENT" else (raw.get(k) or "")
            for k in all_cols
        )
        if full_key in seen:
            continue
        seen.add(full_key)
        event = {name: (raw.get(name) or "") for name in keep if name in raw}
        event["DATE"] = when
        event["EVENT"] = event["EVENT"].upper()
        unique.append(event)
    return unique


def cow_key(row: dict) -> tuple[str, str]:
    """ID and birth date: a cow number can be reused by a later animal."""
    return row.get("ID", "").strip(), (row.get("BDAT") or "").strip()


DAIRYCOMP_FIGURE = re.compile(
    r"305|\bME\b|MATURE|AGE[- ]?ADJ|\bAA|AA\b|PROJ|PREDICT|RELV|RELATIVE|\bREL\b|INDEX|VALUE|PTA|MERIT|GENOMIC")


@dataclass(slots=True)
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
    return [
        Item(
            name=r["dc_item"],
            description=r.get("description") or "",
            type_code=r.get("type_code") or "",
            op1=r.get("op1") or "",
            op2=r.get("op2") or "",
        )
        for r in _io.read_item_list(path)
    ]


# --- EZfeed ----------------------------------------------------------------------------------------------------------

@dataclass(slots=True)
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
    rep = _io.read_ezfeed(path, flexible=True)
    if rep is None or rep["kind"] != "intake_by_pen":
        raise ValueError(f"{path}: not EZfeed's ingredient usage report (no 'Pen, Ingredient, Date' header row)")
    report = IntakeReport(days=[
        IngredientDay(
            pen=r["pen"],
            ingredient=r["ingredient"],
            date=r["date"],
            dm_target_lb=r["target_dm_lb_per_head"],
            dm_actual_lb=r["actual_dm_lb_per_head"],
            cost_target_hd=r["target_cost_per_head"],
            cost_actual_hd=r["actual_cost_per_head"],
        )
        for r in rep["rows"]
    ])
    if not report.days:
        raise ValueError(f"{path}: no daily rows found under the pens and ingredients")
    return report


@dataclass(slots=True)
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
    rep = _io.read_ezfeed(path, flexible=True)
    if rep is None or rep["kind"] != "rations":
        raise ValueError(f"{path}: not EZfeed's ration report (no 'Ration, Ingredient' header row)")
    return [
        RationLine(
            ration=r["ration"],
            ingredient=r["ingredient"],
            as_fed_lb=r["as_fed_lb_per_head"],
            dm_lb=r["dm_lb_per_head"],
            cost_hd=r["cost_per_head"],
            dm_pct=r["dm_pct"],
            price_ton_as_fed=r["as_fed_cost_per_ton"],
        )
        for r in rep["rows"]
    ]


# --- Figures worked out here, from raw records -----------------------------------------------------------------------

def ecm_lb(milk_lb: float, fat_pct: float, protein_pct: float) -> float:
    """Energy-corrected milk, lb (Tyrrell and Reid, 1965, as DHIA uses it)."""
    return _stats.ecm_lb(milk_lb, fat_pct, protein_pct)


mean = _stats.mean


def percentiles(values, qs=(0.1, 0.5, 0.9)) -> tuple[float, ...] | None:
    """Linear-interpolated percentiles (the spread a pen card shows: low tenth, middle cow, high tenth)."""
    vals = _stats.clean(values)
    if not vals:
        return None
    return tuple(_stats.quantile(vals, q) for q in qs)


def quartiles(values) -> tuple[float, float, float] | None:
    return percentiles(values, (0.25, 0.5, 0.75))
