"""Dairy Data Tools: one command for every question, on a folder of a farm's DairyComp and EZfeed exports.

  python dairy.py files     --folder "Farm Exports"            which file is which, and what's missing
  python dairy.py commands  [--folder F] [--years 3]           the DairyComp reports to save (SHOW, never LIST)
  python dairy.py check     "SHOW ID PEN FOR PEN=21" [--folder F]   what would go wrong typing it on this farm
  python dairy.py items     --folder F                         every DairyComp item on the farm, and what it is
  python dairy.py herd      --folder F                         the herd now
  python dairy.py pens      --folder F                         one line per pen
  python dairy.py pen       --folder F --pen 21 [--days 30]    one pen
  python dairy.py cow       --folder F --cow 1100              one cow
  python dairy.py pen-feed  --folder F [--milk-price 21.5] [--days 7] [--pen 21]
  python dairy.py loading   --folder F [--by ingredient|pen|feeder] [--days 14]
  python dairy.py refusals  --folder F [--days 7]
  python dairy.py consistency --folder F [--days 14]
  python dairy.py fresh     --folder F                         fresh cows: diseases, early exits, first tests
  python dairy.py components --folder F                        fat, protein, fat:protein, MUN
  python dairy.py udder     --folder F                         high SCC, new and chronic, clinical mastitis
  python dairy.py repro     --folder F [--vwp 50]              21-day pregnancy rate, conception by service
  python dairy.py exits     --folder F                         who left, and when
  python dairy.py weekly    --folder F [--milk-price 21.5]     all of it, for a visit
  python dairy.py card      --folder F --pen 21 | --cow 3004 | --feed | --weekly [--actions FILE] [--out FILE]
                            [--slide: bigger and fewer items, for a projector; --pen and --feed]

Add --json FILE to any of them for every figure (cards are drawn from it). Read-only: the folder is never changed and
nothing is sent anywhere. Python 3.10 or later, standard library only.

Installed with pip (pip install dairy-data-tools), the same commands run as `dairy-data-tools herd --folder F`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import cards, commands, cowcard, explorer, feeding, io, weekly, weeklycard
from .herd import load


def _r(v, places=1):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:,.{places}f}"
    return str(v)


def _spread(s, unit="lb"):
    return "n/a" if not s else f"low tenth {s['p10']:.0f}, middle {s['p50']:.0f}, high tenth {s['p90']:.0f} {unit} ({s['n']} cows)"


def text(cmd: str, out) -> str:
    """A short plain summary; the full figures are in --json."""
    L = []
    if cmd == "files":
        for f in out:
            L.append(f"{Path(f['path']).name}: {f['kind']} ({f['detail'][:70]})")
        kinds = {f["kind"] for f in out}
        for need, how in (("cows", "a cow report (dairy.py commands)"), ("events", "an events report"),
                          ("items", "the item list (ALTER\\2 > Tools > Export > CSV)")):
            if need not in kinds:
                L.append(f"Missing: {how}.")
        if "feed" not in kinds:
            L.append("No EZfeed reports: the feed questions need the Ingredient Intake or Pen Summary reports.")
    elif cmd == "commands":
        for s in out:
            L.append(f"{s['step']}. {s['report']}: {s['command']}\n   {s['what']}")
    elif cmd == "check":
        L.append("OK to type." if out["ok"] else "Fix before typing:")
        L += [f"- {p}" for p in out["problems"]] + [f"Note: {n}" for n in out["notes"]]
    elif cmd == "items":
        for d in out:
            flag = " (DairyComp's own calculation: don't use)" if d["dairycomp_calculates"] else ""
            L.append(f"{d['item']}: {d['description']} [{d['kind']}]{flag}")
    elif cmd == "herd":
        t = out["test"]
        L.append(f"The herd on {out['as_of']}: {out['milking']} milking, {out['dry']} dry, {out['heifers']} heifers; "
                 f"{out['left_last_12_months']} left in the last 12 months. Median days in milk {_r(out['median_dim'], 0)}.")
        L.append(f"Last test: {t['tested']} of {t['of']} milking cows; milk {_spread(t['milk_lb'])}; "
                 f"ECM {_r(t['ecm_mean_lb'])} lb per cow.")
        if t["scc_tested"]:
            L.append(f"SCC over 200,000: {t['scc_over_200']} of {t['scc_tested']} cows tested.")
        h = out["holds"]
        if h["unmapped_codes"]:
            L.append("Event codes with no meaning yet: " + ", ".join(f"{k} ({v})" for k, v in h["unmapped_codes"].items())
                     + ". Add them to event_map.csv in the folder.")
        if h["not_recorded"]:
            L.append("No events recorded for: " + ", ".join(h["not_recorded"]) + " (not recorded is not zero).")
        L += [f"Note: {p}" for p in h["problems"]]
    elif cmd == "pens":
        for p in out:
            L.append(f"Pen {p['pen']} ({p['kind']}): {p['animals']} animals, median {_r(p['median_dim'], 0)} days in milk, "
                     f"{p['first_lactation']} first lactation, {p['pregnant']} pregnant; "
                     f"test milk median {_r(p['median_test_milk'], 0)} lb ({p['tested']} tested); ECM {_r(p['ecm_mean'])} lb per cow.")
    elif cmd == "pen":
        s, t = out["summary"], out["test"]
        L.append(f"Pen {out['pen']} on {out['as_of']}: {s['animals']} animals ({s['milking']} milking, {s['dry']} dry, "
                 f"{s['heifers']} heifers); days in milk {_spread(out['dim'], 'days')}.")
        L.append(f"Last test, {t['tested']} of {t['of']} milking cows: milk {_r(t['milk_mean_lb'])} lb per cow "
                 f"({_spread(t['milk_lb'])}); ECM {_r(t['ecm_mean_lb'])} lb per cow.")
        if out["health"]:
            L.append(f"Health events in the last {out['days']} days, cows in the pen now: "
                     + ", ".join(f"{h['event']} {h['events']} ({h['cows']} cows)" for h in out["health"]) + ".")
        L.append(f"Moved in: {out['moved_in']}; calved: {out['fresh_in']} (last {out['days']} days).")
    elif cmd == "cow":
        L.append(f"Cow {out['cow']}: {out['status']}, pen {out['pen']}, lactation {out['lactation']}, "
                 f"{_r(out['days_in_milk'], 0)} days in milk.")
        L += [f"  {x['date']}  {x['what']}" + (f" ({x['days_in_milk']} days in milk)" if x["days_in_milk"] is not None else "")
              for x in out["timeline"]]
        L += [f"  {x['measure']}: {x['value']} {x['unit']}" for x in out["tests"]]
        if out["number_also_used_by"]:
            L.append("Her number was also used by: " + ", ".join(out["number_also_used_by"]))
    elif cmd == "pen-feed":
        for p in out["pens"]:
            line = (f"Pen {p['pen']} ({p['days']}, {p['cows']} cows): ECM {_r(p['ecm_mean_lb'])} lb, DM fed "
                    f"{_r(p['dmi_lb_per_cow'])} lb per cow (week before {_r(p['dmi_before'])}), ECM per lb DM "
                    f"{_r(p['ecm_per_lb_dm'], 2)}, feed ${_r(p['feed_cost_per_cow'], 2)} per cow, "
                    f"${_r(p['feed_cost_per_cwt'], 2)} per cwt")
            if "iofc_per_cow" in p:
                line += f", IOFC ${_r(p['iofc_per_cow'], 2)} per cow"
            if p["nasem_predicted_dmi"]:
                line += f"; NASEM predicts {_r(p['nasem_predicted_dmi'])} lb"
            L.append(line + ".")
            L += [f"  Note: {n}" for n in p["notes"]]
    elif cmd in ("loading", "refusals", "consistency"):
        for r in out.get("rows", []):
            L.append(", ".join(f"{k} {_r(v, 2) if isinstance(v, float) else v}" for k, v in r.items()))
        if out.get("note"):
            L.append(out["note"])
    else:
        L.append(json.dumps(out, default=str, indent=1)[:6000])
    if isinstance(out, dict) and out.get("source"):
        L.append(out["source"])
    return "\n".join(L)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command")
    p.add_argument("text", nargs="*", help="the DairyComp command, for check (quotes optional)")
    p.add_argument("--folder", help="folder of the farm's exports")
    p.add_argument("--pen")
    p.add_argument("--cow")
    p.add_argument("--days", type=int)
    p.add_argument("--milk-price", type=float, help="$ per cwt")
    p.add_argument("--by", default="ingredient")
    p.add_argument("--vwp", type=int, default=50)
    p.add_argument("--years", type=int, default=3)
    p.add_argument("--as-of", help="YYYY-MM-DD: count to this day instead of the last event")
    p.add_argument("--json")
    p.add_argument("--out", help="for card: the HTML file to write")
    p.add_argument("--feed", action="store_true", help="for card: the pen feed card")
    p.add_argument("--weekly", action="store_true", help="for card: the visit review page")
    p.add_argument("--slide", action="store_true", help="for card --pen or --feed: bigger, fewer items, for a projector")
    p.add_argument("--actions", help="for card --weekly: a text file, one action a line: what to check | who")
    a = p.parse_args(argv)
    cmd = a.command

    def herd():
        if not a.folder:
            raise SystemExit("Give --folder: the folder with the farm's exports.")
        return load(a.folder, io.parse_dc_date(a.as_of) if a.as_of else None)

    def item_list():
        if not a.folder:
            return None
        paths = [f["path"] for f in io.identify_folder(a.folder) if f["kind"] == "items"]
        return io.read_item_list(paths[0]) if paths else None

    if cmd == "files":
        out = io.identify_folder(a.folder or ".")
    elif cmd == "commands":
        out = commands.export_commands(item_list(), events_days=365 * a.years)
    elif cmd == "check":
        out = commands.check(" ".join(a.text), item_list())
    elif cmd == "items":
        items = item_list()
        if not items:
            raise SystemExit("No item list in the folder: in DairyComp, ALTER\\2 > Tools > Export > CSV.")
        out = commands.describe_items(items)
    elif cmd == "herd":
        out = explorer.herd_summary(herd())
    elif cmd == "pens":
        out = explorer.pen_summary(herd())
    elif cmd == "pen":
        out = explorer.pen_card(herd(), a.pen, a.days or 30)
    elif cmd == "cow":
        out = explorer.cow_record(herd(), a.cow)
    elif cmd == "pen-feed":
        out = feeding.pen_feed(herd(), a.days or 7, a.milk_price, a.pen)
    elif cmd == "loading":
        out = feeding.loading_accuracy(herd(), a.by, a.days)
    elif cmd == "refusals":
        out = feeding.refusals(herd(), a.days or 7)
    elif cmd == "consistency":
        out = feeding.consistency(herd(), a.days or 14)
    elif cmd == "fresh":
        out = weekly.fresh_cows(herd())
    elif cmd == "components":
        out = weekly.components(herd())
    elif cmd == "udder":
        out = weekly.udder_health(herd())
    elif cmd == "repro":
        out = weekly.reproduction(herd(), a.vwp)
    elif cmd == "exits":
        out = weekly.exits(herd())
    elif cmd == "weekly":
        out = weekly.weekly(herd(), a.milk_price, a.vwp)
    elif cmd == "card":
        h = herd()
        if a.weekly:
            acts = []
            if a.actions:
                for line in Path(a.actions).read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        what, _, who = line.partition("|")
                        acts.append((what.strip(), who.strip()))
            page = weeklycard.weekly_html(h, a.milk_price, acts, a.vwp)
            target, what = Path(a.out or "visit-review.html"), "the visit review"
        elif a.feed:
            page = weeklycard.pen_feed_html(h, a.milk_price, a.days or 7, slide=a.slide)
            target, what = Path(a.out or "pen-feed.html"), "the pen feed card"
        elif a.cow:
            page = cowcard.cow_card_html(h, a.cow)
            target, what = Path(a.out or f"cow-{a.cow}-card.html"), f"cow {a.cow}'s card"
        elif a.pen:
            milk_files = [f["path"] for f in h.files if f["kind"] == "pen_milk"]
            page = cards.pen_card_html(h, a.pen, io.read_pen_milk(milk_files[0]) if milk_files else None, slide=a.slide)
            target, what = Path(a.out or f"pen-{a.pen}-card.html"), f"pen {a.pen}'s card"
        else:
            raise SystemExit("Give --pen, --cow, --feed or --weekly for the card.")
        target.write_text(page, encoding="utf-8")
        print(f"Wrote {target} ({what}). Show it as an artifact, or open it in a browser.")
        return
    else:
        raise SystemExit(f"Unknown command '{cmd}'. Run with --help for the list.")
    if a.json:
        Path(a.json).write_text(json.dumps(out, default=lambda o: o.isoformat() if isinstance(o, date) else str(o),
                                           indent=1), encoding="utf-8")
    print(text(cmd, out))


if __name__ == "__main__":
    main()
