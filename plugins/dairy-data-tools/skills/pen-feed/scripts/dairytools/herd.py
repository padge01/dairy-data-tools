"""A farm's exports read into clean tables: cows, events, lactations and feed. The R version's intake() in Python.

  herd = load("Farm Exports")      # a folder of DairyComp and EZfeed reports, named however the farm likes

Rules (each taken from real exports):
- An animal is its ID and birth date (`animal_id`), because barn numbers are reused. Events without a birth date go to
  the animal with that number born most recently before the event.
- Exact duplicate events count once.
- Event codes get a standard meaning from the reference table, then from the farm's own `event_map.csv` in the folder
  (dc_code, remark_pattern, std_event, category), which wins. Codes nobody has mapped are listed, not guessed.
- Days in milk are counted to the herd's last event, not the computer's date (a restored backup overstates
  DairyComp's figure); DairyComp's own stays as `dc_days_in_milk`.
- A cow leaves the herd at her last SOLD or DIED event (or her archive date).
- Remarks are read only to map codes (a farm that records SICK with the disease in the remark). They are never put in
  any output: they are free text typed on the farm and can contain anything.
"""

from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from . import commands, io, reference


@dataclass
class Herd:
    folder: str
    cows: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    lactations: list[dict] = field(default_factory=list)
    feed: dict[str, list[dict]] = field(default_factory=dict)
    items: list[dict] = field(default_factory=list)
    files: list[dict] = field(default_factory=list)
    unmapped_codes: dict[str, int] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    as_of: date | None = None
    events_from: date | None = None

    def status(self, cow: dict) -> str:
        """milking, dry, heifer, left or unknown: one rule for every count."""
        if cow.get("left_date"):
            return "left"
        lact = cow.get("lactation")
        if lact is None or lact < 1:
            return "heifer"
        if (cow.get("repro_status") or "").upper() == "DRY" or cow.get("is_dry"):
            return "dry"
        return "milking" if cow.get("days_in_milk") is not None else "unknown"

    def in_herd(self) -> list[dict]:
        return [c for c in self.cows if not c.get("left_date")]

    def source_line(self) -> str:
        kinds = Counter(f["kind"] for f in self.files)
        span = f"events {self.events_from} to {self.as_of}" if self.events_from else f"to {self.as_of}"
        return (f"From {len(self.files)} files in {Path(self.folder).name} ({', '.join(f'{v} {k}' for k, v in kinds.items())}); "
                f"{span}; {len(self.in_herd())} animals in the herd.")


# --- loading ---------------------------------------------------------------------------------------------------------

def _convert(value, kind):
    if value is None:
        return None
    if kind == "date":
        return io.parse_dc_date(value)
    if kind == "integer":
        n = io.number(value)
        return int(n) if n is not None else None
    if kind == "number":
        return io.number(value)
    return value.strip()


def _guess(values) -> str:
    vals = [v for v in values if v is not None][:200]
    if not vals:
        return "text"
    if all(re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", v) for v in vals):
        return "date"
    if all(io.number(v) is not None for v in vals):
        return "number"
    return "text"


def pen_label(pen) -> str:
    """3 (not 3.0) and "No pen" for a blank, as the cards show it."""
    if pen is None or str(pen).strip() == "":
        return "No pen"
    s = str(pen).strip()
    n = io.number(s)
    return str(int(n)) if n is not None and n == int(n) else s


def _cow_rows(paths) -> list[dict]:
    """Several cow reports joined on ID and birth date (ID alone if one lacks BDAT); the first report with a column
    gives it."""
    parts = [io.read_dc_export(p) for p in paths]
    keys = ("ID", "BDAT") if all(part and "BDAT" in part[0] for part in parts) else ("ID",)
    joined: dict[tuple, dict] = {}
    order = []
    for part in parts:
        seen = Counter()   # without birth dates, the 2nd row with a number in one report is another animal
        for row in part:
            k = tuple(row.get(x) for x in keys)
            seen[k] += 1
            k = k + (seen[k],)
            if k not in joined:
                joined[k] = {}
                order.append(k)
            for col, v in row.items():
                if col not in joined[k] or joined[k][col] is None:
                    joined[k][col] = v
    return [joined[k] for k in order]


def _standardise(rows, table, item_list) -> tuple[list[dict], list[str]]:
    problems = []
    if not rows:
        return [], problems
    cols = list(dict.fromkeys(k for r in rows for k in r))   # every column any row has
    farm = commands.farm_record_items(item_list) if table == "cows" else {}
    names = {}
    for col in cols:
        if table == "events" and col in reference.EVENT_COLUMNS:
            names[col] = (reference.EVENT_COLUMNS[col],
                          {"birth_date": "date", "lactation": "integer", "dim_at_event": "integer",
                           "event_date": "date"}.get(reference.EVENT_COLUMNS[col], "text"))
        elif col in reference.ITEMS:
            name, kind, _, _ = reference.ITEMS[col]
            names[col] = (name, kind)
        elif col in farm:   # the farm's own MUN, body condition, body weight... under whatever name it uses
            names[col] = (farm[col], "number")
        else:
            safe = re.sub(r"[^a-z0-9]+", "_", col.lower()).strip("_") or "column"
            names[col] = (("item_" + safe) if safe[0].isdigit() else safe, _guess(r.get(col) for r in rows))
    out = []
    bad = Counter()
    for r in rows:
        new = {}
        for col, (name, kind) in names.items():
            v = _convert(r.get(col), kind)
            if r.get(col) is not None and v is None:
                bad[col] += 1
            new[name] = v
        if not new.get("cow_id"):
            bad["ID"] += 1
            continue
        out.append(new)
    for col, n in bad.items():
        problems.append(f"{n} values in {col} could not be read and were left blank")
    return out, problems


def animal_id(cow_id, birth: date | None) -> str:
    return f"{cow_id}-{birth:%Y%m%d}" if birth else str(cow_id)


def _read_event_map(folder: Path) -> list[dict]:
    path = folder / "event_map.csv"
    if not path.exists():
        return []
    rows = list(csv.DictReader(io.read_lines(path)))
    return [{k.strip().lower(): (v or "").strip() for k, v in r.items() if k} for r in rows]


def _map_events(events, farm_map):
    for e in events:
        code = (e.get("dc_event") or "").upper()
        e["dc_event"] = code
        std = reference.EVENTS.get(code)
        e["std_event"], e["category"] = (std[0], std[1]) if std else (None, None)
        e["mapped_by"] = "reference" if std else None
    plain = {m["dc_code"].upper(): m for m in farm_map if m.get("std_event") and not m.get("remark_pattern")}
    patterned = [m for m in farm_map if m.get("std_event") and m.get("remark_pattern")]
    for e in events:
        m = plain.get(e["dc_event"])
        if m:
            e["std_event"], e["category"], e["mapped_by"] = m["std_event"], m.get("category") or None, "farm map"
        remark = e.get("remark") or ""
        for m in patterned:
            if e["dc_event"] == m["dc_code"].upper() and re.search(m["remark_pattern"], remark, re.I):
                e["std_event"], e["category"], e["mapped_by"] = m["std_event"], m.get("category") or None, "farm map"
                break
    unmapped = Counter(e["dc_event"] for e in events if not e["std_event"])
    for e in events:
        if not e["std_event"]:
            e["category"] = "unmapped"
    return dict(unmapped.most_common())


def _assign(events, cows):
    by_id = defaultdict(list)
    for c in cows:
        by_id[c["cow_id"]].append(c)
    # Birth dates name an animal only when both reports carry them.
    have_birth = any(e.get("birth_date") for e in events) and any(c.get("birth_date") for c in cows)
    for e in events:
        if have_birth and e.get("birth_date"):
            e["animal_id"] = animal_id(e["cow_id"], e["birth_date"])
            continue
        cands = by_id.get(e["cow_id"], [])
        if not cands:
            e["animal_id"] = str(e["cow_id"])
        elif len(cands) == 1 or not e.get("event_date"):
            e["animal_id"] = cands[0]["animal_id"]
        else:
            born = [c for c in cands if c.get("birth_date") and c["birth_date"] <= e["event_date"]]
            if born:
                pick = max(born, key=lambda c: c["birth_date"])
            else:   # no birth dates: the animal that was still in the herd on the event's day
                still = [c for c in cands if not c.get("archive_date") or c["archive_date"] >= e["event_date"]]
                pick = min(still, key=lambda c: c.get("archive_date") or date.max) if still else cands[-1]
            e["animal_id"] = pick["animal_id"]


def load(folder, as_of: date | None = None) -> Herd:
    folder = Path(folder)
    files = io.identify_folder(folder)
    herd = Herd(folder=str(folder), files=files)
    cow_paths = [f["path"] for f in files if f["kind"] == "cows"]
    event_paths = [f["path"] for f in files if f["kind"] == "events"]
    item_paths = [f["path"] for f in files if f["kind"] == "items"]
    if item_paths:
        herd.items = io.read_item_list(item_paths[0])

    raw_cows = _cow_rows(cow_paths) if cow_paths else []
    raw_events = [r for p in event_paths for r in io.read_dc_export(p)]
    cows, probs = _standardise(raw_cows, "cows", herd.items)
    herd.problems += [f"cow report: {p}" for p in probs]
    events, probs = _standardise(raw_events, "events", herd.items)
    herd.problems += [f"events: {p}" for p in probs]

    taken = Counter()
    for c in cows:
        aid = animal_id(c["cow_id"], c.get("birth_date"))
        taken[aid] += 1
        # Without birth dates a reused number still names two animals: the later rows get #2, #3.
        c["animal_id"] = aid if taken[aid] == 1 else f"{aid}#{taken[aid]}"
        c["pen"] = pen_label(c.get("pen")) if "pen" in c else "No pen"
    reused = sum(1 for _, n in Counter(c["cow_id"] for c in cows).items() if n > 1)
    if reused:
        herd.problems.append(f"{reused} cow numbers belong to more than one animal (reused); ID and birth date tell them "
                             "apart")
    _assign(events, cows)
    seen, unique = set(), []
    for e in events:
        k = (e["animal_id"], e.get("dc_event"), e.get("event_date"), e.get("remark"))
        if k in seen:
            continue
        seen.add(k)
        unique.append(e)
    if len(unique) < len(events):
        herd.problems.append(f"{len(events) - len(unique)} exact duplicate events removed")
    events = [e for e in unique if e.get("event_date")]
    herd.unmapped_codes = _map_events(events, _read_event_map(folder))

    # "Today" is the last day the records reach. An event dated after the export was made is a typing slip: it stays
    # in the records but doesn't set the day. The export was made no earlier than the computer's date, or than the
    # newest milk test in it (a test is recorded after it happens), whichever is later.
    tests = [c["test_date"] for c in cows if c.get("test_date")]
    made = max([date.today()] + tests)
    future = [e for e in events if e["event_date"] > made]
    if future:
        herd.problems.append(f"{len(future)} events are dated after the export ({made}), e.g. "
                             f"{future[0]['dc_event']} on {future[0]['event_date']}: they don't set the records' last day")
    dates = [e["event_date"] for e in events if e["event_date"] <= made]
    cow_dates = [d for c in cows for d in (c.get("test_date"), c.get("fresh_date"), c.get("dry_date"))
                 if d and d <= made]
    herd.events_from = min(dates) if dates else None
    herd.as_of = as_of or max(dates + cow_dates, default=date.today())

    # Exits: the last SOLD or DIED, else the archive date.
    exits = {}
    for e in sorted(events, key=lambda e: e["event_date"]):
        if e["std_event"] in ("sold", "died"):
            exits[e["animal_id"]] = e
    for c in cows:
        x = exits.get(c["animal_id"])
        c["left_date"] = x["event_date"] if x else c.get("archive_date")
        c["left_reason"] = x["std_event"] if x else ("left" if c.get("archive_date") else None)

    # Days in milk to the herd's last event.
    for c in cows:
        fresh, dry = c.get("fresh_date"), c.get("dry_date")
        c["is_dry"] = bool(fresh and dry and dry >= fresh)
        if not fresh or c["left_date"]:
            c["days_in_milk"] = None
        elif c["is_dry"]:
            c["days_in_milk"] = (dry - fresh).days
        else:
            c["days_in_milk"] = max(0, (herd.as_of - fresh).days)
    no_fresh = [c for c in cows if not c.get("fresh_date") and not c["left_date"] and (c.get("lactation") or 0) >= 1]
    for c in no_fresh:   # no fresh date exported: DairyComp's own figure, when there is one, is all there is
        if c.get("dc_days_in_milk") is not None:
            c["days_in_milk"] = c["dc_days_in_milk"]
    if no_fresh:
        with_dim = sum(1 for c in no_fresh if c.get("days_in_milk") is not None)
        herd.problems.append(f"{len(no_fresh)} calved cows have no fresh date (FDAT) in the export: "
                             + (f"{with_dim} use DairyComp's own days in milk, " if with_dim else "")
                             + f"{len(no_fresh) - with_dim} can't be counted as milking or dry. Add FDAT to the cow report.")
    shifts = sorted(c["dc_days_in_milk"] - c["days_in_milk"] for c in cows
                    if c.get("dc_days_in_milk") is not None and c.get("days_in_milk") is not None and not c["is_dry"])
    if shifts and shifts[len(shifts) // 2] > 7:
        herd.problems.append(f"DairyComp's days in milk run {shifts[len(shifts) // 2]} days past the herd's last event "
                             f"({herd.as_of}): the export is from an older backup. Days in milk here count to "
                             f"{herd.as_of}.")

    herd.cows, herd.events = cows, events
    herd.lactations = build_lactations(cows, events, herd.events_from)
    orphans = {e["animal_id"] for e in events} - {c["animal_id"] for c in cows}
    if orphans and cows:
        herd.problems.append(f"events for {len(orphans)} animals not in the cow report (export the cow report with \\B "
                             "so sold and dead animals are in it)")
    _load_feed(herd, [f["path"] for f in files if f["kind"] == "feed"])
    return herd


# --- lactations ------------------------------------------------------------------------------------------------------

def build_lactations(cows, events, events_from) -> list[dict]:
    """One row per animal per lactation. A calving starts one (calvings within 30 days are one, entered twice); an
    abortion doesn't. A calving before the events export starts is worked out as event date minus DIM. Dry-off or
    leaving ends it, else the next calving. Conception is the last breeding on or before the first positive check.
    `fully_observed` is False when it started before the events begin: leave those out of rates from calving."""
    by_animal = defaultdict(list)
    for e in events:
        by_animal[e["animal_id"]].append(e)
    starts = defaultdict(list)  # animal -> [(date, priority, lactation, cow_id)]
    for e in events:
        if e["std_event"] == "calving":
            starts[e["animal_id"]].append((e["event_date"], 1, e.get("lactation"), e["cow_id"]))
        elif e.get("dim_at_event") is not None and e["dim_at_event"] >= 0 and e.get("lactation") not in (0, None):
            starts[e["animal_id"]].append((e["event_date"] - timedelta(days=e["dim_at_event"]), 3, e.get("lactation"),
                                           e["cow_id"]))
    for c in cows:
        if c.get("fresh_date") and (c.get("lactation") or 0) >= 1:
            starts[c["animal_id"]].append((c["fresh_date"], 2, c.get("lactation"), c["cow_id"]))
    out = []
    for aid, s in starts.items():
        s.sort()
        groups, current = [], [s[0]]
        for x in s[1:]:
            if (x[0] - current[-1][0]).days > 30:
                groups.append(current)
                current = [x]
            else:
                current.append(x)
        groups.append(current)
        picks = [min(g, key=lambda x: x[1]) for g in groups]
        ev = sorted(by_animal.get(aid, []), key=lambda e: e["event_date"])
        for i, (fresh, priority, lact, cow_id) in enumerate(picks):
            nxt = picks[i + 1][0] if i + 1 < len(picks) else None
            within = [e for e in ev if e["event_date"] >= fresh and (nxt is None or e["event_date"] < nxt)]
            first = lambda kinds: next((e for e in within if e["std_event"] in kinds), None)
            dry, left = first({"dry_off"}), first({"sold", "died"})
            if dry and (not left or dry["event_date"] <= left["event_date"]):
                end, reason = dry["event_date"], "dried off"
            elif left:
                end, reason = left["event_date"], left["std_event"]
            elif nxt:
                end, reason = nxt, "next calving (no dry-off recorded)"
            else:
                end, reason = None, "in milk at export"
            breed_end = min(d for d in (end, nxt) if d) if (end or nxt) else None
            services = [e["event_date"] for e in within if e["std_event"] == "breeding"
                        and (breed_end is None or e["event_date"] < breed_end)
                        and not _is_restated_breeding(e)]
            pregs = [e["event_date"] for e in within if e["std_event"] == "preg_positive" and not _is_restated_breeding(e)]
            conception = None
            if pregs:
                before = [d for d in services if d <= pregs[0]]
                conception = max(before) if before else None
            out.append({"animal_id": aid, "cow_id": cow_id, "lactation": lact, "fresh_date": fresh, "end_date": end,
                        "end_reason": reason, "first_service_date": services[0] if services else None,
                        "first_service_dim": (services[0] - fresh).days if services else None,
                        "services": len(services), "conception_date": conception,
                        "days_open": (conception - fresh).days if conception else None,
                        "health_events": sum(1 for e in within if e["category"] == "health"),
                        "fully_observed": bool(events_from and fresh >= events_from),
                        "start_source": {1: "event", 2: "cow list", 3: "implied by DIM"}[priority]})
    return out


SIRE_CODE = re.compile(r"^\d{1,3}[A-Z]{1,3}\d{2,6}$")


def _is_restated_breeding(e) -> bool:
    """DairyComp rewrites a breeding as PREG or OPEN on the breeding's own date once it is checked, with the sire code in
    the remark: that line is the breeding's result, not a pregnancy check of its own."""
    return e["std_event"] in ("preg_positive", "preg_negative") and bool(SIRE_CODE.match((e.get("remark") or "").strip()))


# --- feed ------------------------------------------------------------------------------------------------------------

def match_dc_pen(pen: str, dc_pens: set[str]) -> str | None:
    """'Pen 3', 'pen 3' and '3' are DairyComp pen 3; a pen only EZfeed has (hospital, beef) gets none."""
    s = re.sub(r"^pen\s*", "", (pen or "").strip().lower())
    if re.fullmatch(r"\d+", s) and str(int(s)) in dc_pens:
        return str(int(s))
    return None


def _load_feed(herd: Herd, paths):
    if not paths:
        return
    keys = {"feed_delivery": ("pen", "ingredient", "date"), "feed_ration_intake": ("ration", "ingredient", "date"),
            "feed_pen_days": ("life_stage", "pen", "date"), "feed_rations": ("ration", "ingredient"),
            "feed_loads": ("feeder", "load", "date"), "feed_refusals": ("pen", "date")}
    tables: dict[str, dict] = defaultdict(dict)
    for p in sorted(paths, key=lambda p: Path(p).stat().st_mtime):   # reports overlap: the latest file wins
        r = io.read_ezfeed(p)
        if not r["rows"]:
            herd.problems.append(f"{Path(p).name} has no rows: the farm may not feed this group through EZfeed")
        if r["skipped"]:
            herd.problems.append(f"{Path(p).name}: {r['skipped']} rows that were neither a heading nor a day were left out")
        for row in r["rows"]:
            tables[r["table"]][tuple(row.get(k) for k in keys[r["table"]])] = row
    herd.feed = {t: list(rows.values()) for t, rows in tables.items()}
    rations = {r["ration"] for t in ("feed_rations", "feed_ration_intake") for r in herd.feed.get(t, [])}
    for r in herd.feed.get("feed_delivery", []):
        r["premix"] = r["ingredient"] in rations   # a premix is listed as itself and as its parts: count it once
    dc_pens = {c["pen"] for c in herd.in_herd() if c.get("pen") != "No pen"}
    unmatched = set()
    for t in ("feed_delivery", "feed_pen_days", "feed_refusals"):
        for r in herd.feed.get(t, []):
            r["dc_pen"] = match_dc_pen(r["pen"], dc_pens)
            if r["dc_pen"] is None:
                unmatched.add(r["pen"])
    if unmatched:
        herd.problems.append("EZfeed pens with no DairyComp pen (kept, unmatched): " + ", ".join(sorted(unmatched)))
