"""Reading the files: DairyComp reports, the item list, and EZfeed's reports. Files are recognised by what is in
them, so people can name them however they like.

Single canonical reader for both `dairytools` and the standalone `dairyread` facade (`ration_change.py`,
`pen_milk.py`). Python standard library only.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from pathlib import Path

from .errors import FolderNotFoundError

ENCODINGS = ("utf-8-sig", "cp1252")

_NUMBER_RE = re.compile(r"^-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?$|^-?\.\d+$")
_POST_REMARK_COLS = ("R", "T", "B", "PROTOCOLS", "TECHNICIAN")


# --- text ------------------------------------------------------------------------------------------------------------

def read_text(path: str | Path) -> str:
    """A file's text, UTF-8 (with or without a byte-order mark) or Windows-1252, as DairyComp and EZfeed write."""
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def read_lines(path: str | Path) -> list[str]:
    """A file's lines, decoded with `read_text`."""
    return read_text(path).splitlines()


def split_csv(line: str) -> list[str]:
    return next(csv.reader(io.StringIO(line)), [])


def rows_of(path: str | Path) -> list[list[str]]:
    """All CSV rows from a file, with every cell stripped of surrounding whitespace."""
    return [[cell.strip() for cell in row] for row in csv.reader(io.StringIO(read_text(path)))]


def parse_dc_date(text, today: date | None = None) -> date | None:
    """DairyComp's MM/DD/YY (a two-digit year in the future is last century), MM/DD/YYYY, YYYY-MM-DD, or ISO timestamp."""
    if text is None:
        return None
    if isinstance(text, datetime):
        return text.date()
    if isinstance(text, date):
        return text
    s = str(text).strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:$|[\sT]\d{2}:\d{2})", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})", s)
    if not m:
        return None
    year = int(m[3])
    if year < 100:
        year += 2000
        if year > (today or date.today()).year + 1:
            year -= 100
    try:
        return date(year, int(m[1]), int(m[2]))
    except ValueError:
        return None


def number(text) -> float | None:
    """'1,234.5', '$6.84', '57.94%', '(1.20)' (EZfeed's negatives), ' 77.1 ' -> float; blank or text -> None."""
    if text is None:
        return None
    if isinstance(text, (int, float)) and not isinstance(text, bool):
        return float(text)
    s = str(text).strip().replace("$", "").replace("%", "")
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1].strip()
        if s.startswith("-"):  # reject double-negated '(-1.2)'
            return None
    if not _NUMBER_RE.fullmatch(s):
        return None
    val = float(s.replace(",", ""))
    return -val if negative else val


# --- DairyComp -------------------------------------------------------------------------------------------------------

def read_dc_export(path: str | Path) -> list[dict[str, str | None]]:
    """A DairyComp report saved as CSV (SHOW, EVENTS, FILEOUT or the item list): one dict per row, keyed by the
    upper-cased column name. Handles Windows-1252 text, the trailing comma's empty column, padded values, '-' for a
    missing value, the 'Total:' footer, and stray unquoted commas inside a remark (which otherwise shift columns right)."""
    lines = [l for l in read_lines(path) if l.strip() and not re.match(r"^\s*Total:", l, re.I)]
    if not lines:
        raise ValueError(f"{Path(path).name} is empty")
    raw_header = [h.strip().upper() for h in split_csv(lines[0])]
    rows = [[c.strip() for c in split_csv(l)] for l in lines[1:]]
    width = max([len(raw_header)] + [len(r) for r in rows])
    padded_header = raw_header + [""] * (width - len(raw_header))

    # Give every blank header cell a unique synthetic name so a trailing comma never overwrites spilled cells.
    names: list[str] = []
    seen: dict[str, int] = {}
    blank_names: list[str] = []
    for idx, h in enumerate(padded_header):
        if not h:
            bname = f"_extra_{idx}"
            names.append(bname)
            blank_names.append(bname)
        elif h in seen:
            seen[h] += 1
            names.append(f"{h}.{seen[h]}")
        else:
            seen[h] = 0
            names.append(h)

    # Number of named columns (excluding DairyComp's trailing blank column).
    named_count = len(raw_header)
    while named_count > 0 and not raw_header[named_count - 1]:
        named_count -= 1
    is_events = {"EVENT", "DATE", "REMARK"} <= set(raw_header)

    out: list[dict[str, str | None]] = []
    spilled_rows: list[int] = []
    for row_idx, r in enumerate(rows):
        # Detect a row wider than the header (e.g. an unquoted comma inside a remark shifted cells right).
        has_overflow = len(r) > len(raw_header) and any(v not in ("", "-", "NA") for v in r[named_count:])
        if not has_overflow:
            # Also catch an unquoted comma inside a remark when there is a trailing comma in header:
            # len(r) > len(raw_header) even if the very last cell is blank because the trailing comma shifted right.
            has_overflow = len(r) > len(raw_header)
        r_pad = r + [""] * (width - len(r))
        rec = {n: (None if v in ("", "-", "NA") else v) for n, v in zip(names, r_pad)}
        extra_vals = [rec.pop(bn, None) for bn in blank_names]
        non_empty_extra = [v for v in extra_vals if v is not None]
        if has_overflow or non_empty_extra:
            spilled_rows.append(row_idx)
            if is_events:
                # A stray comma inside REMARK shifts R, T, B, PROTOCOLS, TECHNICIAN right: blank them so
                # remark text can never leak into structured columns like result_code or technician_code.
                for col in _POST_REMARK_COLS:
                    if col in rec:
                        rec[col] = None
            rec["_spilled"] = ", ".join(non_empty_extra) if non_empty_extra else "shifted"
        out.append(rec)

    # Many rows past the last name is DairyComp's 33-column limit; a few is a stray comma in a remark.
    if len(spilled_rows) > max(5, len(out) // 100):
        raise ValueError(f"{Path(path).name}: more values than column names. DairyComp prints at most 33 column "
                         "names; split the items over two reports, each starting ID BDAT.")
    return out


def read_item_list(path: str | Path) -> list[dict]:
    """The farm's item list: ALTER\\2 > Tools > Export > CSV (Name, Index, Loc/Op1, Len/Op2, Type, Description), or the
    ALTER\\2 report saved as text (columns under a ===== ruler). `computed` is True when the first operand names
    another item, as DIM's names DDAT and FDAT; plain numbers there don't prove an item is raw (305M)."""
    lines = read_lines(path)
    ruler = next((i for i, l in enumerate(lines) if re.fullmatch(r"=+( +=+)+\s*", l)), None)
    if ruler is not None:
        spans = [(m.start(), m.end()) for m in re.finditer(r"=+", lines[ruler])]
        rows = []
        for l in lines[ruler + 1:]:
            if re.match(r"^\s*-", l) or re.fullmatch(r"=+( +=+)+.*", l) or re.match(r"^Name\s+#", l):
                continue
            name = l[spans[0][0]:spans[0][1]].strip()
            if not name:
                continue
            field = lambda i, to_end=False: l[spans[i][0]:(None if to_end else spans[i][1])].strip()
            n = len(spans)
            rows.append({"NAME": name, "INDEX": field(1), "LOC/OP1": field(2), "LEN/OP2": field(3),
                         "TYPE": field(4), "%USED": field(6) if n >= 8 else None,
                         "DESCRIPTION": field(n - 1, True)})
    else:
        rows = read_dc_export(path)
        if not rows or not ({"NAME", "ITEM"} & set(rows[0])):
            raise ValueError(f"{Path(path).name} has no Name column: is it a DairyComp item list?")
    out = []
    for r in rows:
        name = (r.get("NAME") or r.get("ITEM") or "").upper()
        if not name:
            continue
        op1 = (r.get("LOC/OP1") or "").strip()
        used = re.sub(r"^\.*", "", r.get("%USED") or "")
        out.append({"dc_item": name, "item_number": r.get("INDEX"), "op1": op1, "op2": (r.get("LEN/OP2") or ""),
                    "type_code": r.get("TYPE"), "percent_used": int(used) if used.isdigit() else None,
                    "computed": bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9#$%_-]*", op1)),
                    "description": (r.get("DESCRIPTION") or "").strip()})
    return out


# --- EZfeed ----------------------------------------------------------------------------------------------------------

# The exact column labels (the row under EZfeed's banner row) of each report read here.
EZFEED_REPORTS = {
    "intake_by_pen": ("Ingredient Intake Tgt vs Act by Pen", "feed_delivery",
                      ["Pen", "Ingredient", "Date", "IU(lbs/hd)", "IU(lbs/hd)", "IU($/hd)", "IU($/hd)", "IU($)", "IU"]),
    "intake_by_ration": ("Ingredient Intake by Ration", "feed_ration_intake",
                         ["Ration", "Ingredient", "Date", "IU(lbs/hd)", "IU(lbs/hd)", "IU($/hd)", "IU($/hd)", "IU($)",
                          "IU"]),
    "pen_summary_milking": ("Pen Summary (Milking Cows)", "feed_pen_days",
                            ["Date Range", "Pen", "Date", "Act(#/h/d)", "Act($/h/d)", "Act(ttl$)", "lbs/hd/day",
                             "PenMlk Act($/hd/day)", "Avg($/cwt PenMilk)", "LbsMilk/LbAct", "(avg ttl/d)", "(avg %)",
                             "End Time"]),
    "pen_summary_dry": ("Pen Summary (Dry Cows)", "feed_pen_days",
                        ["Date Range", "Pen Group", "Pen", "Date", "Act(#/h/d)", "Act($/h/d)", "Act(ttl$)",
                         "(avg ttl/d)", "(avg %)", "End Time"]),
    "pen_summary_heifers": ("Pen Summary (Heifers)", "feed_pen_days",
                            ["Date Range", "Pen", "Date", "Act(#/h/d)", "Act($/h/d)", "(avg ttl/d)", "(avg %)",
                             "End Time"]),
    "rations": ("Rations (current breakdown)", "feed_rations",
                ["Ration", "Ingredient", "AF(#/h/d)", "DM(#/h/d)", "($/h/d)", "DM %", "AF($/ton)"]),
    "feeder_loads": ("FeederLoad Summary", "feed_loads",
                     ["Date Range", "User", "Load", "Date", "(ttlCount)", "(avg#/min)", "(avg time/ld)",
                      "DmFed(avg#/actn)", "Overall(%)", "(avg %/actn)", "Start Time", "End Time", "(ttlTime)"]),
    "refusals": ("Refusal Summary", "feed_refusals",
                 ["Date Range", "Pen", "Date", "Act(#/h/d)", "Act%of D/ttl", "Act(#/d)"]),
}


def ez_rows(path: str | Path) -> list[list[str]]:
    return [[c.strip() for c in split_csv(l)] for l in read_lines(path) if l.replace(",", "").strip()]


def ezfeed_kind(rows, max_scan: int = 3) -> tuple[str, int] | None:
    for i, row in enumerate(rows[:max_scan]):
        r = list(row)
        while r and not r[-1]:
            r.pop()
        for kind, (_, _, labels) in EZFEED_REPORTS.items():
            if r == labels:
                return kind, i
    return None


def ez_date(text) -> date | None:
    """EZfeed date (MM/DD/YYYY, MM/DD/YY, or YYYY-MM-DD)."""
    return parse_dc_date(text)


def ez_time(text) -> str | None:
    s = (text or "").strip().upper()
    if re.fullmatch(r"\d{1,2}:\d{2} *(AM|PM)", s):
        return datetime.strptime(s.replace(" ", ""), "%I:%M%p").strftime("%H:%M")
    return None


def ez_seconds(text) -> float | None:
    s = text or ""
    if not re.search(r"\d+ *(Hour|Min|Sec)", s, re.I):
        return None
    part = lambda unit: float(m[1]) if (m := re.search(rf"(\d+) *{unit}", s, re.I)) else 0.0
    return 3600 * part("Hour") + 60 * part("Min") + part("Sec")


def _cell(row, i):
    return row[i] if i < len(row) else ""


def _walk(body, levels, keep):
    """EZfeed's nested rows: a group row (pen, ration, feeder...), then the rows under it; a blank cell means "same as
    above". `levels` are the 0-based columns that carry down; `keep(row, current)` picks the fact rows."""
    current = [None] * len(levels)
    out, skipped = [], 0
    for row in body:
        if keep(row, current):
            out.append((row, list(current)))
            continue
        set_at = [j for j, col in enumerate(levels) if _cell(row, col)]
        if set_at:
            j = set_at[0]
            current[j] = _cell(row, levels[j])
            for k in range(j + 1, len(current)):
                current[k] = None
        else:
            skipped += 1
    return out, skipped


def _find_banner_cols(banner: list[str], units: list[str]) -> tuple[int, int, int, int, int, int]:
    """Locate (dm_t, dm_a, hd_t, hd_a, tot_t, tot_a) columns from banner + unit labels, defaulting to EZfeed order."""
    labels = [f"{(banner[i] if i < len(banner) else '').strip()} {u}".strip() for i, u in enumerate(units)]

    def col(prefix: str, unit: str, fallback: int) -> int:
        for i, lab in enumerate(labels):
            if lab.startswith(prefix) and unit in lab:
                return i
        return fallback

    dm_t = col("DMTgt", "lbs/hd", 3)
    dm_a = col("DMAct", "lbs/hd", 4)
    hd_t = col("$Tgt", "$/hd", 5)
    hd_a = col("$Act", "$/hd", 6)
    tot_t = col("$Tgt", "($)", 7)
    tot_a = col("$Act", "IU", 8)
    # If banner puts $Act before $Tgt for total columns, respect the last two columns cleanly.
    if tot_a == tot_t:
        tot_t, tot_a = 7, 8
    return dm_t, dm_a, hd_t, hd_a, tot_t, tot_a


def read_ezfeed(path: str | Path, *, flexible: bool = False) -> dict | None:
    """One EZfeed report: {'kind', 'title', 'table', 'rows' (list of dicts), 'skipped'}; None if it isn't one of the
    reports read here. With `flexible=True`, also recognises intake/ration reports with extra title rows or subset columns."""
    rows = ez_rows(path)
    found = ezfeed_kind(rows, max_scan=len(rows) if flexible else 3)
    if found is None and flexible:
        # Fallback for custom/trimmed intake or ration exports (preserves legacy dairyread behavior).
        for i, r in enumerate(rows):
            low = [c.lower() for c in r]
            if i > 0 and len(low) >= 3 and low[0] == "pen" and low[1] == "ingredient" and low[2] == "date":
                found = ("intake_by_pen", i)
                break
            if len(low) >= 2 and low[0] == "ration" and low[1] == "ingredient":
                found = ("rations", i)
                break
    if found is None:
        return None
    kind, at = found
    title, table, _ = EZFEED_REPORTS[kind]
    body = rows[at + 1:]
    if kind in ("intake_by_pen", "intake_by_ration"):
        banner = rows[at - 1] if at > 0 else []
        units = rows[at]
        dm_t, dm_a, hd_t, hd_a, tot_t, tot_a = _find_banner_cols(banner, units)
        got, skipped = _walk(body, [0, 1], lambda r, c: ez_date(_cell(r, 2)) is not None and c[0] and c[1])
        group = "pen" if kind == "intake_by_pen" else "ration"
        data = [
            {
                group: g,
                "ingredient": ing,
                "date": ez_date(_cell(r, 2)),
                "target_dm_lb_per_head": number(_cell(r, dm_t)),
                "actual_dm_lb_per_head": number(_cell(r, dm_a)),
                "target_cost_per_head": number(_cell(r, hd_t)),
                "actual_cost_per_head": number(_cell(r, hd_a)),
                "target_cost": number(_cell(r, tot_t)) if tot_t < len(r) else None,
                "actual_cost": number(_cell(r, tot_a)) if tot_a < len(r) else None,
            }
            for r, (g, ing) in got
        ]
    elif kind.startswith("pen_summary"):
        stage = {"pen_summary_milking": "milking", "pen_summary_dry": "dry", "pen_summary_heifers": "heifer"}[kind]
        grouped = stage == "dry"
        pen_col = 2 if grouped else 1
        date_col = pen_col + 1
        levels = [0, 1, 2] if grouped else [0, 1]
        got, skipped = _walk(body, levels, lambda r, c: ez_date(_cell(r, date_col)) is not None and c[-1])
        m = date_col + 1
        head_col = m + {"milking": 7, "dry": 3, "heifer": 2}[stage]
        data = [{"life_stage": stage, "pen_group": c[1] if grouped else None, "pen": c[-1],
                 "date": ez_date(_cell(r, date_col)), "dm_lb_per_head": number(_cell(r, m)),
                 "cost_per_head": number(_cell(r, m + 1)),
                 "cost_total": None if stage == "heifer" else number(_cell(r, m + 2)),
                 "head_count": number(_cell(r, head_col)), "capacity_pct": number(_cell(r, head_col + 1)),
                 "last_unload_time": ez_time(_cell(r, head_col + 2))} for r, c in got]
    elif kind == "rations":
        got, skipped = _walk(body, [0], lambda r, c: not _cell(r, 0) and _cell(r, 1) and c[0])
        data = [{"ration": c[0], "ingredient": _cell(r, 1), "as_fed_lb_per_head": number(_cell(r, 2)),
                 "dm_lb_per_head": number(_cell(r, 3)), "cost_per_head": number(_cell(r, 4)),
                 "dm_pct": number(_cell(r, 5)), "as_fed_cost_per_ton": number(_cell(r, 6))} for r, c in got]
    elif kind == "feeder_loads":
        got, skipped = _walk(body, [0, 1], lambda r, c: ez_date(_cell(r, 3)) is not None and _cell(r, 2) and c[1])
        data = [{"feeder": c[1], "load": _cell(r, 2), "date": ez_date(_cell(r, 3)), "loads": number(_cell(r, 4)),
                 "as_fed_lb_per_minute": number(_cell(r, 5)), "average_load_seconds": ez_seconds(_cell(r, 6)),
                 "dm_lb_per_action": number(_cell(r, 7)), "deviation_pct": number(_cell(r, 8)),
                 "deviation_pct_per_action": number(_cell(r, 9)), "first_load_time": ez_time(_cell(r, 10)),
                 "last_load_time": ez_time(_cell(r, 11)), "total_seconds": ez_seconds(_cell(r, 12))}
                for r, c in got]
    else:  # refusals: EZfeed prints them as negatives (feed taken back out); kept as amounts
        got, skipped = _walk(body, [0, 1], lambda r, c: ez_date(_cell(r, 2)) is not None and c[1])
        absval = lambda v: None if v is None else abs(v)
        data = [{"pen": c[1], "date": ez_date(_cell(r, 2)),
                 "refusal_as_fed_lb_per_head": absval(number(_cell(r, 3))),
                 "refusal_pct": absval(number(_cell(r, 4))), "refusal_as_fed_lb": absval(number(_cell(r, 5)))}
                for r, c in got]
    return {"kind": kind, "title": title, "table": table, "rows": data, "skipped": skipped}


def read_pen_milk(path: str | Path) -> dict:
    """Pen milk by day (date, pen, milk_lb, fat_pct, protein_pct): {(pen, date): {milk_lb, fat_pct, protein_pct}}."""
    rows = list(csv.DictReader(read_lines(path)))
    out = {}
    for r in rows:
        r = {k.strip().lower(): (v or "").strip() for k, v in r.items() if k}
        d = parse_dc_date(r.get("date"))
        if d and r.get("pen"):
            out[(r["pen"], d)] = {"milk_lb": number(r.get("milk_lb")), "fat_pct": number(r.get("fat_pct")),
                                  "protein_pct": number(r.get("protein_pct"))}
    return out


# --- which file is which ---------------------------------------------------------------------------------------------

def identify(path: str | Path) -> dict:
    """{'path', 'kind': cows | events | items | feed | unknown, 'detail'}."""
    p = Path(path)
    try:
        lines = [l for l in read_lines(p) if l.strip()]
    except OSError as e:
        return {"path": str(p), "kind": "unknown", "detail": str(e)}
    if any(re.fullmatch(r"=+( +=+)+\s*", l) for l in lines[:40]):
        return {"path": str(p), "kind": "items", "detail": "ALTER\\2 report"}
    found = ezfeed_kind([[c.strip() for c in split_csv(l)] for l in lines[:3]])
    if found:
        return {"path": str(p), "kind": "feed", "detail": EZFEED_REPORTS[found[0]][0]}
    header = [h.strip().upper() for h in split_csv(lines[0])] if lines else []
    if {"DC_CODE", "STD_EVENT"} <= set(header):
        kind = "event_map"
    elif {"EVENT", "DATE"} <= set(header):
        kind = "events"
    elif {"NAME", "DESCRIPTION"} <= set(header):
        kind = "items"
    elif "ID" in header:
        kind = "cows"
    elif {"DATE", "PEN", "MILK_LB"} <= set(header) or header[:3] == ["DATE", "PEN", "MILK_LB"]:
        kind = "pen_milk"
    elif set(header) & {"FEED", "INGREDIENT", "FEED NAME"} and set(header) & {"NDF", "ANDF"} and \
            set(header) & {"CP", "PROTEIN"}:
        kind = "analyses"   # the farm's own feed analyses
    else:
        kind = "unknown"
    return {"path": str(p), "kind": kind, "detail": " ".join(h for h in header if h)}


def identify_folder(folder: str | Path) -> list[dict]:
    folder = Path(folder)
    if not folder.is_dir():
        raise FolderNotFoundError(f"Folder '{folder}' not found. Put the DairyComp and EZfeed reports in it.")
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".csv", ".txt", ".prn"))
    return [identify(p) for p in files]
