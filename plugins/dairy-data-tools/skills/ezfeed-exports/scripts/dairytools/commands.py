"""DairyComp commands: the export set for a farm, and a check of any command before someone types it.

The agent writes commands from plain English using the skill's notes on DairyComp's syntax; `check` then catches what
would go wrong on this farm: LIST (it prints: use SHOW), items the farm doesn't have (DairyComp stops at a "Please
Select Item" box), DairyComp's own calculated items, and shortcuts over 63 characters.
"""

from __future__ import annotations

import re

from . import reference

MAX_COLUMNS = 33        # DairyComp prints at most 33 column names in a report
MAX_SHORTCUT = 63       # characters in a shortcut's content (ALTER\3)
FILEOUT_FILE = 99       # one-off pulls; file 1 is EZfeed's pen import, never use it
LOOKS_CALCULATED = re.compile(r"305|\bME\b|MATURE|AGE[- ]?ADJ|PROJ|PREDICT|RELV|RELATIVE|\bREL\b|INDEX|VALUE|PTA|"
                              r"MERIT|GENOMIC")
VERBS = {"SHOW", "LIST", "SUM", "COUNT", "PCT", "GRAPH", "EGRAPH", "PLOT", "EVENTS", "BREDSUM", "ECON", "MONITOR",
         "FILEOUT", "ALTER", "MILK"}

# Farms' own items (90 and up) the kit recognises under any name: (column name, name pattern, description pattern).
FARM_RECORDS = [
    ("body_condition_score", r"^BCS|^CONDSC$|^BODYC", r"BODY COND|CONDITION SC"),
    ("body_weight", r"^BW$|^BODYWT|^WEIGHT|^WT$|^LBS$", r"BODY WEIGHT|^WEIGHT"),
    ("mun", r"^MUN|^UREA|^MILKUN", r"UREA|\bMUN\b"),
    ("locomotion_score", r"^LOCO|^MOBIL|^LSCOR", r"LOCOMOTION|MOBILITY"),
    ("hoof_score", r"^HOOFS|^HFSC", r"HOOF SC"),
    ("hygiene_score", r"^HYG", r"HYGIENE|CLEANLINESS"),
    ("calving_ease_score", r"^CEASE|^CALVE|^DIFF$", r"CALVING EASE|DIFFICULTY"),
]


def farm_record_items(item_list) -> dict[str, str]:
    """The farm's own items the kit recognises: {dc_item: column name}; one item per column, a description match
    first."""
    found: dict[str, tuple[int, str]] = {}
    for it in item_list or []:
        if it["dc_item"] in reference.ITEMS or it.get("computed"):
            continue
        for name, by_name, by_desc in FARM_RECORDS:
            score = 2 * bool(re.search(by_desc, it.get("description") or "", re.I)) + \
                bool(re.search(by_name, it["dc_item"], re.I))
            if score and (name not in found or score > found[name][0]):
                found[name] = (score, it["dc_item"])
    return {item: name for name, (_, item) in found.items()}


def export_commands(item_list=None, events_days: int = 1095) -> list[dict]:
    """The reports to save for this farm, in order: [{step, report, command, what}]. Without the item list, the
    first step is to save it, and the cow report uses only DairyComp's standard items."""
    steps = []
    if not item_list:
        steps.append({"report": "item list", "command": "ALTER\\2",
                      "what": "Tools > Export > CSV, saved as items.csv. Then ask again: the commands will use only "
                              "items this farm has."})
        have = set(reference.STANDARD_COW_ITEMS) - {"PN", "EASE", "CSEX", "TDAT", "TPEN", "PMILK", "PSCC", "MUN",
                                                    "SCC1", "FTDIM", "FSTBF", "FSTPR"}
        farm = {}
    else:
        names = {it["dc_item"] for it in item_list}
        have = {i for i in reference.STANDARD_COW_ITEMS if i in names}
        farm = farm_record_items(item_list)
    if "ID" not in have:
        have.add("ID")
    keys = [k for k in ("ID", "BDAT") if k in have or not item_list]
    others = [i for i in reference.STANDARD_COW_ITEMS if i in have and i not in keys] + sorted(farm)
    per = MAX_COLUMNS - len(keys)
    chunks = [others[i:i + per] for i in range(0, len(others), per)] or [[]]
    for n, chunk in enumerate(chunks, 1):
        cols = keys + chunk
        steps.append({"report": "cows" if len(chunks) == 1 else f"cows (part {n} of {len(chunks)})",
                      "command": f"SHOW {' '.join(cols)} FOR ID>0 \\B",
                      "what": f"One row per animal, in the herd, sold and dead (\\B), {len(cols)} items. "
                              "Export > Save as CSV."})
    ev_items = [i for i in ("ID", "BDAT", "LACT") if i in have or not item_list]
    steps.append({"report": "events", "command": f"EVENTS\\2S{events_days}-0B {' '.join(ev_items)}",
                  "what": f"Every event of the last {events_days} days, one per line, with each animal's "
                          f"{', '.join(ev_items)} (birth date because cow numbers are reused). Export > Save as CSV."})
    for i, s in enumerate(steps, 1):
        s["step"] = i
    return steps


def fileout_shortcuts(items: list[str], prefix: str = "KIT", file_number: int = FILEOUT_FILE) -> list[tuple[str, str]]:
    """Shortcuts for a daily file (ALTER\\3, then the last one in ALTER\\6's scheduler): item lists of at most 63
    characters, then FILEOUT naming them. Returns [(name, content)]."""
    lists, current = [], []
    for item in items:
        if len(" ".join(current + [item])) > MAX_SHORTCUT:
            lists.append(current)
            current = []
        current.append(item)
    if current:
        lists.append(current)
    names = [f"{prefix}{chr(ord('I') + i)}" for i in range(len(lists))]
    out = [(n, " ".join(l)) for n, l in zip(names, lists)]
    run = f"FILEOUT {' '.join(names)} \\{file_number}CCH"
    if len(run) > MAX_SHORTCUT:
        raise ValueError("too many items for one file: split them over two files")
    out.append((f"{prefix}COWS"[:7], run))
    return out


def check(command: str, item_list=None) -> dict:
    """What would go wrong typing this command on this farm. {'ok', 'problems', 'notes', 'items'}."""
    cmd = command.strip()
    problems, notes = [], []
    verb = re.split(r"[\s\\]", cmd, maxsplit=1)[0].upper()
    if verb == "LIST":
        problems.append("LIST sends the report to the printer: use SHOW, then Export > Save as CSV.")
    elif verb not in VERBS:
        notes.append(f"'{verb}' isn't one of DairyComp's report commands the kit knows; it may be one of the farm's "
                     "own shortcuts (check ALTER\\3).")
    words = re.findall(r"[A-Za-z0-9$#%]+", re.sub(r"\\\S*", " ", cmd))
    body = words[1:]
    stop = {"FOR", "BY", "DOWNBY", "TODAY", "AND", "OR"}
    items = []
    for w in body:
        u = w.upper()
        if u in stop or re.fullmatch(r"-?\d+(\.\d+)?", u):
            continue
        items.append(u)
    names = {it["dc_item"]: it for it in item_list or []}
    for u in dict.fromkeys(items):
        if u in reference.ITEMS and reference.ITEMS[u][3]:
            problems.append(f"{u} is DairyComp's own calculation ({reference.ITEMS[u][2]}): work it out from the raw "
                            "records instead.")
        if names and u not in names:
            problems.append(f"{u} isn't an item on this farm. If it's one of the farm's own shortcuts that's fine; "
                            "otherwise DairyComp stops at 'Please Select Item'.")
        elif names and names[u].get("computed"):
            notes.append(f"{u} is worked out by DairyComp from {names[u]['op1']} (a calculation, not a record).")
    if verb == "FILEOUT":
        m = re.search(r"\\(\d+)", cmd)
        if m and m.group(1) == "1":
            problems.append("FILEOUT file 1 is usually EZfeed's pen import: use 99.")
        if "SETUP" in cmd.upper():
            problems.append("Never route reports through SETUP (the printer setup): it has hung DairyComp for hours.")
    if len(cmd) > MAX_SHORTCUT:
        notes.append(f"{len(cmd)} characters: fine to type, but a shortcut holds at most {MAX_SHORTCUT}.")
    if not item_list:
        notes.append("Without the farm's item list (ALTER\\2 > Tools > Export > CSV), items can't be checked.")
    return {"ok": not problems, "problems": problems, "notes": notes, "items": list(dict.fromkeys(items))}


def describe_items(item_list) -> list[dict]:
    """Every item on the farm with what the kit makes of it: kind (standard, farm record, from events, other),
    whether DairyComp works it out, and the column name it gets."""
    farm = farm_record_items(item_list)
    out = []
    for it in item_list:
        name = it["dc_item"]
        if name in reference.ITEMS:
            col, _, desc, calc = reference.ITEMS[name]
            kind = "DairyComp's own calculation" if calc else "standard record"
        elif name in farm:
            col, desc, calc, kind = farm[name], it["description"], False, "farm record"
        else:
            col, desc = None, it["description"]
            calc = bool(it.get("computed")) or bool(LOOKS_CALCULATED.search(f"{name} {desc}".upper())) or "$" in name
            from_events = (it.get("op1") or "").upper() in reference.EVENTS
            kind = "worked out from events" if from_events else ("calculated" if calc else "farm item")
        if name not in reference.ITEMS:
            calc = bool(calc or it.get("computed"))
        out.append({"item": name, "kind": kind, "column": col, "dairycomp_calculates": bool(calc),
                    "description": desc, "percent_used": it.get("percent_used")})
    return out
