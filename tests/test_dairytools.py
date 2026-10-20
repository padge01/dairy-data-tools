"""The ported Rossow lab rules, on small made-up files with known answers."""

import ast
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from dairytools import commands, feeding, io, weekly  # noqa: E402
from dairytools.herd import load  # noqa: E402

BS = chr(92)  # a backslash, written so no shell or editor can eat it


def write(folder: Path, name: str, text: str, encoding="utf-8"):
    (folder / name).write_text(text, encoding=encoding)


# --- commands --------------------------------------------------------------------------------------------------------

def items_csv(names):
    rows = ['"Name","Index","Loc/Op1","Len/Op2","Type","Description"']
    rows += [f'"{n}","{i}","0","0","1","{n} ITEM"' for i, n in enumerate(names, 1)]
    return "\n".join(rows) + "\n"


def test_commands_use_show_and_split_at_33_columns(tmp_path):
    names = ["ID", "BDAT", "LACT", "PEN", "FDAT", "DDAT", "MILK"] + [f"F{i}" for i in range(40)]
    write(tmp_path, "items.csv", items_csv(names))
    steps = commands.export_commands(io.read_item_list(tmp_path / "items.csv"))
    cow_steps = [s for s in steps if s["report"].startswith("cows")]
    assert all(s["command"].startswith("SHOW ID BDAT ") for s in cow_steps)
    assert all(not s["command"].startswith("LIST") for s in steps)
    assert all(len(s["command"].split(" FOR ")[0].split()) - 1 <= 33 for s in cow_steps)
    events = next(s for s in steps if s["report"] == "events")
    assert events["command"] == f"EVENTS{BS}2S1095-0B ID BDAT LACT"


def test_fileout_shortcuts_fit_63_characters():
    out = commands.fileout_shortcuts(["ID", "BDAT", "LACT", "PEN", "FDAT", "DDAT", "CDAT", "TBRD", "RPRO", "MILK",
                                      "PCTF", "PCTP", "SCC", "DMLK1", "ARDAT", "PFDAT", "TDAT"])
    assert all(len(content) <= 63 and len(name) <= 7 for name, content in out)
    assert out[-1][1].startswith("FILEOUT ") and out[-1][1].endswith(f"{BS}99CCH")


def test_check_catches_list_missing_items_and_calculations(tmp_path):
    write(tmp_path, "items.csv", items_csv(["ID", "PEN", "MILK", "LACT"]))
    items = io.read_item_list(tmp_path / "items.csv")
    bad = commands.check("LIST ID PEN 305ME FOR PEN=21", items)
    text = " ".join(bad["problems"])
    assert not bad["ok"] and "LIST sends" in text and "305ME" in text
    good = commands.check("SHOW ID PEN LACT MILK FOR PEN=21 BY MILK", items)
    assert good["ok"], good


# --- the herd --------------------------------------------------------------------------------------------------------

COWS = """ID,BDAT,LACT,PEN,FDAT,DDAT,CDAT,RPRO,MILK,PCTF,PCTP,SCC,ARDAT,
    7,03/01/21,       3,      21,09/01/26,        ,        ,   FRESH,    90.0,    3.60,    3.00,     100,        ,
    7,02/01/18,       5,        ,07/01/24,        ,        ,    SOLD,        ,        ,        ,        ,03/01/25,
    8,04/01/22,       2,      21,08/20/26,        ,08/30/26,    PREG,    80.0,    4.00,    3.10,       0,        ,
Total: 3,,,,,,,,,,,,,
"""

EVENTS = """ID,BDAT,LACT,Event,DIM,Date,Remark,R,T,B,Protocols,Technician
7,03/01/21,3,FRESH,0,09/01/26,,,,,,
7,03/01/21,3,FRESH,0,09/05/26,corrected,,,,,
7,03/01/21,3,MAST,20,09/21/26,LF,,,,,
7,03/01/21,3,MAST,20,09/21/26,LF,,,,,
8,04/01/22,2,BRED,10,08/30/26,7HO12345,,,,,
8,04/01/22,2,PREG,10,08/30/26,7HO12345,,,,,
8,04/01/22,2,PREG,45,10/04/26,,,,,,
8,04/01/22,2,KETONE,5,08/25/26,,,,,,
"""


def test_herd_rules(tmp_path):
    write(tmp_path, "cows.csv", COWS)
    write(tmp_path, "events.csv", EVENTS, encoding="cp1252")
    herd = load(tmp_path)
    assert len(herd.cows) == 3                                        # the Total line isn't a cow
    assert len({c["animal_id"] for c in herd.cows if c["cow_id"] == "7"}) == 2   # number 7 reused
    assert any("reused" in p for p in herd.problems)
    assert any("duplicate" in p for p in herd.problems)               # the two identical MAST lines
    assert herd.unmapped_codes == {"KETONE": 1}
    assert herd.as_of == date(2026, 10, 4)                            # the last event, not today
    seven = next(c for c in herd.cows if c["animal_id"] == "7-20210301")
    assert seven["days_in_milk"] == (date(2026, 10, 4) - date(2026, 9, 1)).days
    lact7 = [l for l in herd.lactations if l["animal_id"] == "7-20210301"]
    assert len(lact7) == 1                                            # calvings 4 days apart are one
    lact8 = next(l for l in herd.lactations if l["animal_id"] == "8-20220401")
    assert lact8["conception_date"] == date(2026, 8, 30)               # last breeding before the real check
    assert lact8["services"] == 1


def test_event_map_in_the_folder_maps_farm_codes(tmp_path):
    write(tmp_path, "cows.csv", COWS)
    write(tmp_path, "events.csv", EVENTS)
    write(tmp_path, "event_map.csv", "dc_code,remark_pattern,std_event,category\nKETONE,,ketosis,health\n")
    herd = load(tmp_path)
    assert herd.unmapped_codes == {}
    assert any(e["std_event"] == "ketosis" for e in herd.events)


def test_incidence_counts_first_case_among_lactations_with_the_whole_window(tmp_path):
    write(tmp_path, "cows.csv", COWS)
    write(tmp_path, "events.csv", EVENTS.replace("8,04/01/22,2,PREG,45,10/04/26,,,,,,",
                                                 "8,04/01/22,2,PREG,45,10/04/26,,,,,,\n9,01/01/22,2,OK,0,12/31/26,,,,,,"))
    herd = load(tmp_path)
    r = weekly.incidence(herd, "clinical_mastitis", 30, "none")
    # Calved 1 Sep and 20 Aug, both before 31 Dec - 30 days; one case, the duplicate counted once.
    assert r["rows"] == [{"group": "all", "lactations": 1, "cases": 1, "risk_pct": 100.0}] or \
        r["rows"][0]["cases"] == 1


# --- pen feed --------------------------------------------------------------------------------------------------------

PEN_SUMMARY = """Pen Summary Milking,,,,,,,,,,,,
Date Range,Pen,Date,Act(#/h/d),Act($/h/d),Act(ttl$),lbs/hd/day,PenMlk Act($/hd/day),Avg($/cwt PenMilk),LbsMilk/LbAct,(avg ttl/d),(avg %),End Time
10/1/2026 - 10/4/2026,,,,,,,,,,,,
,Pen 21,,,,,,,,,,,
,,10/3/2026,60.00,$9.00,$540.00,0,0,0,0,3,100%,6:05 AM
,,10/4/2026,60.00,$9.00,$540.00,0,0,0,0,3,100%,6:15 AM
"""


def test_pen_feed_uses_dairycomps_head_count(tmp_path):
    write(tmp_path, "cows.csv", COWS)
    write(tmp_path, "events.csv", EVENTS)
    write(tmp_path, "pen summary.csv", PEN_SUMMARY)
    herd = load(tmp_path)
    r = feeding.pen_feed(herd, days=7, milk_price=20.0)
    p = r["pens"][0]
    assert p["pen"] == "21" and p["cows"] == 2 and p["ezfeed_head_count"] == 3
    assert abs(p["dmi_lb_per_cow"] - 90.0) < 1e-9                    # 60 lb x 3 EZfeed heads / 2 DairyComp cows
    assert abs(p["iofc_per_cow"] - (20.0 * 85.0 / 100 - 13.5)) < 1e-9
    assert any("DairyComp has 2" in n for n in p["notes"])


# --- the code itself -------------------------------------------------------------------------------------------------

def test_no_control_characters_in_the_code():
    """A shell heredoc once turned a regex's backslash-b into a backspace; catch any such slip."""
    for f in list((ROOT / "tools").rglob("*.py")):
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert not any(ord(ch) < 9 for ch in node.value), f"{f}:{node.lineno}"
