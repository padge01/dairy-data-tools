"""Reading the files: DairyComp reports, the item list, and EZfeed's reports. Files are recognised by what is in
them, so people can name them however they like."""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from pathlib import Path


# --- text ------------------------------------------------------------------------------------------------------------

def read_lines(path) -> list[str]:
    """A file's lines, UTF-8 (with or without a byte-order mark) or Windows-1252, as DairyComp and EZfeed write."""
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    return text.splitlines()


def split_csv(line: str) -> list[str]:
    return next(csv.reader(io.StringIO(line)), [])


def parse_dc_date(text, today: date | None = None) -> date | None:
    """DairyComp's MM/DD/YY (a two-digit year in the future is last century), MM/DD/YYYY, or YYYY-MM-DD."""
    if text is None:
        return None
    if isinstance(text, date):
        return text
    s = str(text).strip()
    if not s:
        return None
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
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
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().replace("$", "").replace(",", "").replace("%", "")
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if not re.fullmatch(r"-?\d+(\.\d+)?|-?\.\d+", s):
        return None
    return -float(s) if negative else float(s)


# --- DairyComp -------------------------------------------------------------------------------------------------------

def read_dc_export(path) -> list[dict[str, str | None]]:
    """A DairyComp report saved as CSV (SHOW, EVENTS, FILEOUT or the item list): one dict per row, keyed by the
    upper-cased column name. Handles Windows-1252 text, the trailing comma's empty column, padded values, '-' for a
    missing value and the 'Total:' footer."""
    lines = [l for l in read_lines(path) if l.strip() and not re.match(r"^\s*Total:", l)]
    if not lines:
        raise ValueError(f"{Path(path).name} is empty")
    header = [h.strip().upper() for h in split_csv(lines[0])]
    rows = [[c.strip() for c in split_csv(l)] for l in lines[1:]]
    width = max([len(header)] + [len(r) for r in rows])
    header += [""] * (width - len(header))
    names, seen = [], {}
    for h in header:
        if h and h in seen:
            seen[h] += 1
            names.append(f"{h}.{seen[h]}")
        else:
            seen[h] = 0
            names.append(h)
    out = []
    for r in rows:
        r = r + [""] * (width - len(r))
        out.append({n: (None if v in ("", "-", "NA") else v) for n, v in zip(names, r)})
    # The trailing comma leaves an unnamed column with nothing in it.
    empty = [n for n in names if n == "" and all(row.get(n) is None for row in out)]
    for row in out:
        for n in empty:
            row.pop(n, None)
    if "" in names:
        spilled = [row for row in out if row.get("") is not None]
        # Many rows past the last name is DairyComp's 33-column limit; a few is a stray comma in a remark.
        if len(spilled) > max(5, len(out) // 100):
            raise ValueError(f"{Path(path).name}: more values than column names. DairyComp prints at most 33 column "
                             "names; split the items over two reports, each starting ID BDAT.")
        for row in out:
            extra = row.pop("", None)
            if extra is not None:
                row["_spilled"] = extra   # counted and reported by the reader of the herd, never used
    return out


def read_item_list(path) -> list[dict]:
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


def ez_rows(path) -> list[list[str]]:
    return [[c.strip() for c in split_csv(l)] for l in read_lines(path) if l.replace(",", "").strip()]


def ezfeed_kind(rows) -> tuple[str, int] | None:
    for i, row in enumerate(rows[:3]):
        r = list(row)
        while r and not r[-1]:
            r.pop()
        for kind, (_, _, labels) in EZFEED_REPORTS.items():
            if r == labels:
                return kind, i
    return None


def ez_date(text) -> date | None:
    s = (text or "").strip()
    if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}", s):
        try:
            return datetime.strptime(s, "%m/%d/%Y").date()
        except ValueError:
            return None
    return None


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


def read_ezfeed(path) -> dict | None:
    """One EZfeed report: {'kind', 'title', 'table', 'rows' (list of dicts), 'skipped'}; None if it isn't one of the
    reports read here."""
    rows = ez_rows(path)
    found = ezfeed_kind(rows)
    if found is None:
        return None
    kind, at = found
    title, table, _ = EZFEED_REPORTS[kind]
    body = rows[at + 1:]
    if kind in ("intake_by_pen", "intake_by_ration"):
        banner = rows[0] if at > 0 else []
        t = banner.index("DMTgt") if "DMTgt" in banner else None
        a = banner.index("DMAct") if "DMAct" in banner else None
        target_first = t is None or a is None or t < a
        got, skipped = _walk(body, [0, 1], lambda r, c: ez_date(_cell(r, 2)) is not None and c[0] and c[1])

        def pair(i, j, f, r):
            x, y = f(_cell(r, i)), f(_cell(r, j))
            return (x, y) if target_first else (y, x)

        group = "pen" if kind == "intake_by_pen" else "ration"
        data = []
        for r, (g, ing) in got:
            dm = pair(3, 4, number, r)
            hd = pair(5, 6, number, r)
            tot = pair(7, 8, number, r)
            data.append({group: g, "ingredient": ing, "date": ez_date(_cell(r, 2)),
                         "target_dm_lb_per_head": dm[0], "actual_dm_lb_per_head": dm[1],
                         "target_cost_per_head": hd[0], "actual_cost_per_head": hd[1],
                         "target_cost": tot[0], "actual_cost": tot[1]})
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


def read_pen_milk(path) -> dict:
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

def identify(path) -> dict:
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
    elif {"DATE", "PEN", "MILK_LB"} <= {h.lower().upper() for h in header} or header[:3] == ["DATE", "PEN", "MILK_LB"]:
        kind = "pen_milk"
    else:
        kind = "unknown"
    return {"path": str(p), "kind": kind, "detail": " ".join(h for h in header if h)}


def identify_folder(folder) -> list[dict]:
    folder = Path(folder)
    if not folder.is_dir():
        raise SystemExit(f"Folder '{folder}' not found. Put the DairyComp and EZfeed reports in it.")
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".csv", ".txt", ".prn"))
    return [identify(p) for p in files]
