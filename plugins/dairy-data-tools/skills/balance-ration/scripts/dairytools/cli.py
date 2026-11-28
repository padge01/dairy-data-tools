"""Dairy Data Tools: one command for every question, on a folder of a farm's DairyComp and EZfeed exports.

  python dairy.py files              --folder "Farm Exports"            which file is which, and what's missing
  python dairy.py commands           [--folder F] [--years 3]           the DairyComp reports to save (SHOW, never LIST)
  python dairy.py check              "SHOW ID PEN FOR PEN=21" [--folder F]   what would go wrong typing it on this farm
  python dairy.py items              --folder F                         every DairyComp item on the farm, and what it is
  python dairy.py herd               --folder F                         the herd now
  python dairy.py pens               --folder F                         one line per pen
  python dairy.py pen                --folder F --pen 21 [--days 30]    one pen
  python dairy.py cow                --folder F --cow 1100              one cow
  python dairy.py pen-feed           --folder F [--milk-price 21.5] [--days 7] [--pen 21]
  python dairy.py ration-lab         --folder F --pen 21 [--days 7]     offline handoff for Dairy Ration Lab / MCP
  python dairy.py loading            --folder F [--by ingredient|pen|feeder] [--days 14]
  python dairy.py refusals           --folder F [--days 7]
  python dairy.py consistency        --folder F [--days 14]
  python dairy.py fresh              --folder F                         fresh cows: diseases, early exits, first tests
  python dairy.py components         --folder F                         fat, protein, fat:protein, MUN
  python dairy.py udder              --folder F                         high SCC, new and chronic, clinical mastitis
  python dairy.py scc-screen         --folder F [--by none|parity|pen] [--fresh-dim 40]
  python dairy.py scc-dynamics       --folder F [--by none|parity]      DHI-302 new, chronic, cured, dry-period dynamics
  python dairy.py mastitis           --folder F [--by month|none] [--first-only] [--months 12]
  python dairy.py repro              --folder F [--vwp 50]              21-day pregnancy rate, conception by service
  python dairy.py pregnancy-rate     --folder F [--vwp 50] [--by none|parity] [--cycles]
  python dairy.py first-service      --folder F [--vwp 50] [--by none|parity]
  python dairy.py pregnant-by        --folder F [--days 150] [--by parity|lactation_group|calving_year|none]
  python dairy.py time-to-pregnancy  --folder F [--by none|parity|COL]  Kaplan-Meier days open & log-rank test
  python dairy.py pregnancy-loss     --folder F [--by none|parity] [--followed-days 60]
  python dairy.py calving-interval   --folder F [--by none|parity]
  python dairy.py age-first-calving  --folder F [--by none|calving_year]
  python dairy.py conception         --folder F [--by service|month|dim_band|parity|breeding_code|technician|sire]
                                     [--max-service 3] [--include-untrusted]
  python dairy.py inter-service      --folder F                         inter-service interval distribution
  python dairy.py heifer-repro       --folder F                         heifer age at first breeding & conception risk
  python dairy.py dry-period         --folder F [--by none|parity]
  python dairy.py disease-effects    --folder F --event metritis [--within-dim 30] [--removal-dim 60]
  python dairy.py risk-ratio         --folder F --outcome metritis --exposure retained_placenta [--exposed VAL]
                                     [--within-dim 21]
  python dairy.py mh-rr              --folder F --outcome metritis --exposure retained_placenta [--strata parity]
  python dairy.py lactations         --folder F [--within-dim 21|lactation]
  python dairy.py left-reasons       --folder F [--from YYYY-MM-DD] [--to YYYY-MM-DD] [--by reason|parity|lactation_group|dim_band|remark]
  python dairy.py left-herd          --folder F [--within-dim 60] [--by parity|calving_year|lactation_group|calving_month|calving_season|none]
  python dairy.py event-months       --folder F --event metritis [--by calendar_month|year_month]
  python dairy.py survival           --folder F [--by none|parity]      Kaplan-Meier herd survival to 60/150/305 DIM
  python dairy.py calving            --folder F [--by none|parity]      calving ease, calf sex, twinning, gestation
  python dairy.py audit              --folder F                         record-quality audit (dates, DIM, lact jumps)
  python dairy.py exits              --folder F                         who left, and when
  python dairy.py weekly             --folder F [--milk-price 21.5]     all of it, for a visit
  python dairy.py card               --folder F --pen 21 | --cow 3004 | --feed | --weekly [--actions FILE] [--out FILE]
                                     [--slide: bigger and fewer items, for a projector; --pen and --feed]

Add --json FILE to any of them for every figure (cards are drawn from it). Read-only: the folder is never changed and
nothing is sent anywhere. Python 3.10 or later, standard library only.

As the dairy-data-tools package from PyPI, the same commands run as `dairy-data-tools herd --folder F`.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from . import cards, commands, cowcard, ecosystem, epi, explorer, feeding, io, repro, udder, weekly, weeklycard
from .errors import DairyToolsError
from .herd import load
from .models import _RecordMixin


def _r(v, places=1):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:,.{places}f}"
    return str(v)


def _pct(v, places=1):
    return "n/a" if v is None else f"{100 * v:.{places}f}%"


def _pct_num(v, places=1):
    return "n/a" if v is None else f"{v:.{places}f}%"


def _p_str(p):
    return "" if p is None else f" (p={p})"


def _spread(s, unit="lb"):
    return "n/a" if not s else f"low tenth {s['p10']:.0f}, middle {s['p50']:.0f}, high tenth {s['p90']:.0f} {unit} ({s['n']} cows)"


def _json_default(o):
    if isinstance(o, date):
        return o.isoformat()
    if isinstance(o, _RecordMixin):
        return o.to_dict()
    return str(o)


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
        if any(i in ("305ME", "305M", "305AA") for i in out.get("items", ())):
            L.append(f"Tip: For transparent 305-day / ME milk from raw tests, see BESTPRED ({ecosystem.ECOSYSTEM['bestpred']['mcp_url']}).")
    elif cmd == "items":
        for d in out:
            flag = " (DairyComp's own calculation: don't use)" if d["dairycomp_calculates"] else ""
            L.append(f"{d['item']}: {d['description']} [{d['kind']}]{flag}")
    elif cmd == "herd":
        t = out["test"]
        L.append(f"The herd on {out['as_of']}: {out['milking']} milking, {out['dry']} dry, {out['heifers']} heifers; "
                 f"{out['left_last_12_months']} left in the last 12 months. Median days in milk {_r(out['median_dim'], 0)}.")
        L.append(f"{t.get('milk_from', 'last test').capitalize()}: {t['tested']} of {t['of']} milking cows; milk {_spread(t['milk_lb'])}; "
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
        L.append(f"{t.get('milk_from', 'last test').capitalize()}, {t['tested']} of {t['of']} milking cows: milk {_r(t['milk_mean_lb'])} lb per cow "
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
            if p.get("ecm_mean_lb") or not p.get("milk_mean_lb"):
                milk = f"ECM {_r(p['ecm_mean_lb'])} lb"
                eff = f"ECM per lb DM {_r(p['ecm_per_lb_dm'], 2)}"
            else:
                milk = f"milk {_r(p['milk_mean_lb'])} lb ({p.get('milk_from', 'last test')})"
                eff = f"milk per lb DM {_r(p.get('milk_per_lb_dm'), 2)}"
            line = (f"Pen {p['pen']} ({p['days']}, {p['cows']} cows): {milk}, DM fed "
                    f"{_r(p['dmi_lb_per_cow'])} lb per cow (week before {_r(p['dmi_before'])}), {eff}, "
                    f"feed ${_r(p['feed_cost_per_cow'], 2)} per cow, ${_r(p['feed_cost_per_cwt'], 2)} per cwt")
            if "iofc_per_cow" in p:
                line += f", IOFC ${_r(p['iofc_per_cow'], 2)} per cow"
            if p["nasem_predicted_dmi"]:
                line += f"; NASEM predicts {_r(p['nasem_predicted_dmi'])} lb"
            L.append(line + ".")
            L += [f"  Note: {n}" for n in p["notes"]]
        if out["pens"]:
            rl = ecosystem.ECOSYSTEM["ration_lab"]
            L.append(f"To formulate or test ration changes, run `ration-lab --pen <PEN>` for {rl['name']} ({rl['web_url']} / MCP {rl['mcp_url']}).")
    elif cmd == "ration-lab":
        ag = out["animal_group"]
        rc = out["current_recipe"]
        L.append(f"Dairy Ration Lab handoff for Pen {out['pen']} ({ag['cows']} cows, {ag['milking']} milking, "
                 f"mean milk {_r(ag['milk_mean_lb'])} lb, ECM {_r(ag['ecm_mean_lb'])} lb, "
                 f"NASEM predicted DMI {_r(ag['nasem_predicted_dmi_lb'])} lb).")
        if rc["feeds"]:
            L.append(f"Current recipe ({len(rc['feeds'])} feeds, delivered DM {_r(rc['dmi_delivered_lb_per_cow'])} lb/cow, "
                     f"cost ${_r(rc['feed_cost_per_cow'], 2)}/cow):")
            for f in rc["feeds"]:
                price = f"${f['as_fed_cost_per_ton']:.2f}/ton AF" if f["as_fed_cost_per_ton"] is not None else "no price"
                L.append(f"  {f['ingredient']}: {_r(f['target_dm_lb_per_head'], 2)} lb DM target ({price})")
        if rc["unpriced_feeds"]:
            L.append("Unpriced feeds (confirm before formulating): " + ", ".join(rc["unpriced_feeds"]))
        L += [f"Next ({i}): {step}" for i, step in enumerate(out["mcp_steps"], 1)]
    elif cmd in ("loading", "refusals", "consistency"):
        for r in out.get("rows", []):
            L.append(", ".join(f"{k} {_r(v, 2) if isinstance(v, float) else v}" for k, v in r.items()))
        if out.get("note"):
            L.append(out["note"])
    elif cmd == "pregnancy-rate":
        for r in out["rows"]:
            prefix = f"{r['cycle_start']}..{r['cycle_end']} [{r['group']}]" if out["cycles"] else f"Group {r['group']} ({r['cycles']} cycles)"
            L.append(f"{prefix}: {r['eligible']} eligible, {r['bred']} bred ({_pct(r['service_rate'])}), "
                     f"{r['pregnant']} pregnant (CR {_pct(r['conception_rate'])}, PR {_pct(r['pregnancy_rate'])}).")
        L.append(out["definition"])
    elif cmd == "first-service":
        for r in out["rows"]:
            L.append(f"Group {r['group']}: {r['bred']} of {r['lactations']} bred, median {_r(r['median_dim'], 0)} DIM "
                     f"(mean {_r(r['mean_dim'])}), {_pct(r['share_by_vwp21'])} by VWP+20, {_pct(r['share_by_100'])} by 100 DIM.")
        L.append(out["definition"])
    elif cmd == "pregnant-by":
        for r in out["rows"]:
            L.append(f"Group {r['group']}: {r['pregnant']} of {r['n']} pregnant by {out['days']} DIM "
                     f"({_pct(r['share'])}, 95% CI {_pct(r['ci_low'])}-{_pct(r['ci_high'])}).")
        L.append(out["definition"])
    elif cmd == "time-to-pregnancy":
        for r in out["rows"]:
            L.append(f"Group {r['group']}: {r['pregnant']} of {r['lactations']} pregnant, KM median {_r(r['median_dim'], 0)} DIM; "
                     f"pregnant by 100/150/200 DIM: {_pct(r['pregnant_by_100'])} / {_pct(r['pregnant_by_150'])} / {_pct(r['pregnant_by_200'])}.")
        L.append(out["definition"])
    elif cmd == "pregnancy-loss":
        for r in out["rows"]:
            L.append(f"Group {r['group']}: {r['lost']} of {r['pregnant']} lost ({_pct(r['share'])}, "
                     f"95% CI {_pct(r['ci_low'])}-{_pct(r['ci_high'])}).")
        L.append(out["definition"])
    elif cmd == "calving-interval":
        for r in out["rows"]:
            L.append(f"Group {r['group']}: {r['intervals']} intervals, median {_r(r['median_days'], 0)} d "
                     f"(mean {_r(r['mean_days'])} d / {_r(r['mean_months'])} mo, {_pct(r['over_14_5_months'])} >14.5 mo); "
                     f"days open ({r['pregnant_lactations']} pregnant): median {_r(r['days_open_median'], 0)} d, mean {_r(r['days_open_mean'])} d.")
        L.append(out["definition"])
    elif cmd == "age-first-calving":
        for r in out["rows"]:
            L.append(f"Group {r['group']}: {r['heifers']} heifers, median {_r(r['median_months'])} mo "
                     f"(mean {_r(r['mean_months'])} mo), {_pct(r['over_24_months'])} over 24 mo.")
        L.append(out["definition"])
    elif cmd == "conception":
        grp = out["group"]
        for r in out["rows"]:
            note = f" [{r['note']}]" if r.get("note") else ""
            L.append(f"{r[grp]}: {r['pregnant']} of {r['services']} ({_pct(r['share'])}, "
                     f"95% CI {_pct(r['ci_low'])}-{_pct(r['ci_high'])}){note}")
        if out.get("safety_note"):
            L.append(f"Safety note: {out['safety_note']}")
        L.append(out["definition"])
    elif cmd == "inter-service":
        L.append(f"{out['intervals']} repeat intervals: median {_r(out['median_days'], 0)} d (mean {_r(out['mean_days'])} d), "
                 f"21:42 day ratio {_r(out['ratio_21_to_42'], 2)}.")
        for b in out["bands"]:
            L.append(f"  {b['band']} d: {b['intervals']} ({_pct(b['share'])})")
        L.append(out["definition"])
    elif cmd == "heifer-repro":
        c = out["conception"]
        L.append(f"Heifers bred: {out['heifers_bred']}; age at first breeding median {_r(out['age_first_breeding_median_months'])} mo "
                 f"(mean {_r(out['age_first_breeding_mean_months'])} mo, n={out['age_first_breeding_n']}).")
        L.append(f"Conception: {c['pregnant']} of {c['services']} ({_pct(c['share'])}, 95% CI {_pct(c['ci_low'])}-{_pct(c['ci_high'])}).")
        if out["pregnancy_loss"]:
            pl = out["pregnancy_loss"]
            L.append(f"Pregnancy loss: {pl['lost']} of {pl['pregnant']} ({_pct(pl['share'])}).")
        L.append(out["definition"])
    elif cmd == "dry-period":
        for r in out["rows"]:
            L.append(f"Group {r['group']}: {r['n']} dry periods, median {_r(r['median'], 0)} d (mean {_r(r['mean'])} d); "
                     f"<30 {_pct(r['share_under_30'])}, 30-39 {_pct(r['share_30_39'])}, 40-60 {_pct(r['share_40_60'])}, "
                     f"61-80 {_pct(r['share_61_80'])}, >80 {_pct(r['share_over_80'])}.")
        L.append(out["definition"])
    elif cmd == "disease-effects":
        L.append(f"Lactations with vs without {out['event']} by {out['within_dim']} DIM:")
        if out["milk"]:
            L.append(f"Milk ({out['milk_source']}):")
            for r in out["milk"]:
                L.append(f"  Parity {r['parity']}, {r['group']} (n={r['n']}): median {_r(r['median'])} lb, "
                         f"mean {_r(r['mean'])} lb{_p_str(r['p_value'])}.")
        if out["removal"]:
            rr = out["removal"]
            L.append(f"Removal by {out['removal_dim']} DIM: exposed {rr['exposed_cases']}/{rr['exposed_n']} "
                     f"({_pct(rr['exposed_risk'])}) vs ref {rr['reference_cases']}/{rr['reference_n']} "
                     f"({_pct(rr['reference_risk'])}); RR {_r(rr['rr'], 2)} "
                     f"(95% CI {_r(rr['rr_lower'], 2)}-{_r(rr['rr_upper'], 2)}){_p_str(rr['p_value'])} [{rr['test']}].")
        L.append("Days open:")
        for r in out["days_open"]:
            L.append(f"  {r['group']}: {r['conceived']}/{r['lactations']} conceived, median {_r(r['median_days_open'], 0)} d, "
                     f"KM median {_r(r['km_median_days_to_conception'], 0)} d{_p_str(r['p_value'])}.")
        L += [f"Note: {n}" for n in out["notes"]]
    elif cmd == "risk-ratio":
        L.append(f"{out['outcome']} by {out['exposure']}:")
        L.append(f"  {out['exposed_label']}: {out['exposed_cases']}/{out['exposed_n']} ({_pct(out['exposed_risk'])})")
        L.append(f"  {out['reference_label']}: {out['reference_cases']}/{out['reference_n']} ({_pct(out['reference_risk'])})")
        L.append(f"  RR {_r(out['rr'], 2)} (95% CI {_r(out['rr_lower'], 2)}-{_r(out['rr_upper'], 2)}); "
                 f"OR {_r(out['or'], 2)} (95% CI {_r(out['or_lower'], 2)}-{_r(out['or_upper'], 2)}){_p_str(out['p_value'])} [{out['test']}].")
    elif cmd == "mh-rr":
        L.append(f"{out['outcome']} by {out['exposure']} (stratified by {out['strata']}):")
        L.append(f"  Crude RR {_r(out['crude_rr'], 2)}; Mantel-Haenszel RR {_r(out['mh_rr'], 2)} "
                 f"(95% CI {_r(out['mh_rr_lower'], 2)}-{_r(out['mh_rr_upper'], 2)}){_p_str(out['p_value'])}.")
        for s in out["stratum_rows"]:
            L.append(f"  Stratum {s['stratum']}: exposed {s['exposed_cases']}/{s['exposed_n']} ({_pct(s['exposed_risk'])}) "
                     f"vs ref {s['reference_cases']}/{s['reference_n']} ({_pct(s['reference_risk'])}), RR {_r(s['rr'], 2)}.")
        L.append(out["definition"])
    elif cmd == "left-reasons":
        L.append(f"Exits {out['from']} to {out['to']}: {out['total_left']} cows (sold {out['sold']}, died {out['died']}), "
                 f"{_r(out['total_per_100_cow_years'])} per 100 cow-years (95% CI {_r(out['total_ci_low'])}-{_r(out['total_ci_high'])}; "
                 f"avg herd {_r(out['average_herd'])} cows).")
        for r in out["rows"]:
            label = r.get("group") or (f"{r['reason']} / {r['remark']}" if "remark" in r else r["reason"])
            L.append(f"  {label}: {r['n']} ({_pct(r['share'])}, {_r(r['per_100_cow_years'])} / 100 cow-yr)")
        if out.get("safety_note"):
            L.append(f"Safety note: {out['safety_note']}")
        L.append(out["definition"])
    elif cmd == "left-herd":
        for r in out["rows"]:
            L.append(f"Group {r['group']}: {r['left']} of {r['n']} left by {out['within_dim']} DIM "
                     f"({_pct(r['share'])}, 95% CI {_pct(r['ci_low'])}-{_pct(r['ci_high'])}).")
        L.append(out["definition"])
    elif cmd == "event-months":
        L.append(f"{out['event']} ({out['n_cases']} first cases){_p_str(round(out['p_value'], 4) if out['p_value'] is not None else None)}:")
        for r in out["rows"]:
            L.append(f"  {r['month']}: {r['cases']} ({_pct(r['share'])})")
        L.append(out["definition"])
    elif cmd == "survival":
        for r in out["rows"]:
            L.append(f"Group {r['group']}: {r['lactations']} lactations ({r['left']} left); survival 60/150/305 DIM: "
                     f"{_pct(r['survival_60'])} / {_pct(r['survival_150'])} / {_pct(r['survival_305'])}.")
        L.append(out["definition"])
    elif cmd == "calving":
        for r in out["rows"]:
            L.append(f"Group {r['group']}: ease>=3 {r['ease_score_ge_3']}/{r['ease_recorded']} ({_pct(r['share_ease_ge_3'])}), "
                     f"twins {r['twins']}/{r['observed_calvings']} ({_pct(r['twins_share'])}), "
                     f"gestation median {_r(r['gestation_median_days'], 0)} d (n={r['gestation_n']}).")
        L.append(out["definition"])
    elif cmd == "audit":
        L.append(f"Records audit: {out['total_flags']} total flags.")
        for c in out["checks"]:
            L.append(f"  {c['check']}: {c['count']} — {c['detail']}")
    elif cmd == "lactations":
        L.append(f"{len(out)} fully observed lactations exported (use --json FILE for the full table).")
    elif cmd == "scc-screen":
        for r in out["rows"]:
            L.append(f"{r['cows']} ({r['group']}): {r['tested']} tested, >200k {r['over_200k_cells_ml']} "
                     f"({_pct(r['share_over_200k_cells_ml'])}), SCS 5+ {r['scs_5_plus_283k_cells_ml']} "
                     f"({_pct(r['share_scs_5_plus_283k_cells_ml'])}), mean SCS {_r(r['mean_scs'], 2)}.")
        L.append(out["definition"])
    elif cmd == "scc-dynamics":
        for r in out["rows"]:
            L.append(f"[{r['group']}] {r['key']}: {r['cows']}/{r['of']} ({_pct_num(r['percent'])}) — {r['measure']}")
        L.append(out["definition"])
    elif cmd == "mastitis":
        if out["by"] == "month":
            for r in out["rows"]:
                L.append(f"{r['month']}: {r['cases']} cases, {_r(r['cows_in_milk'])} cows in milk, {_r(r['per_100_cows'])} per 100 cows.")
        else:
            s = out["summary"]
            L.append(f"{s['from']} to {s['to']} ({s['months']} months): {s['cases']} cases / {_r(s['cow_months'])} cow-months = "
                     f"{_r(s['per_100_cows_per_month'], 2)} per 100 cows/mo (95% CI {_r(s['ci_low'], 2)}-{_r(s['ci_high'], 2)}).")
        L.append(out["definition"])
    else:
        L.append(json.dumps(out, default=_json_default, indent=1))
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
    p.add_argument("--by", default=None, help="grouping (command-dependent)")
    p.add_argument("--vwp", type=int, default=50)
    p.add_argument("--years", type=int, default=3)
    p.add_argument("--as-of", help="YYYY-MM-DD: count to this day instead of the last event")
    p.add_argument("--from", dest="from_date", help="YYYY-MM-DD: period start (for left-reasons)")
    p.add_argument("--to", dest="to_date", help="YYYY-MM-DD: period end (for left-reasons)")
    p.add_argument("--cycles", action="store_true", help="for pregnancy-rate: one row per 21-day cycle")
    p.add_argument("--first-only", action="store_true", help="for mastitis: first case per lactation only")
    p.add_argument("--months", type=int, default=12, help="for mastitis: latest N complete months")
    p.add_argument("--max-service", type=int, default=3, help="for conception --by service")
    p.add_argument("--followed-days", type=int, default=60, help="for pregnancy-loss")
    p.add_argument("--fresh-dim", type=int, default=40, help="for scc-screen")
    p.add_argument("--within-dim", default=None, help="DIM window (or 'lactation' for lactations)")
    p.add_argument("--removal-dim", type=int, default=60, help="for disease-effects")
    p.add_argument("--event", nargs="+", help="for disease-effects / event-months: one or more std_event names")
    p.add_argument("--outcome", help="for risk-ratio / mh-rr: outcome column in lactation_data")
    p.add_argument("--exposure", help="for risk-ratio / mh-rr: exposure column in lactation_data")
    p.add_argument("--exposed", default=None, help="for risk-ratio / mh-rr: exposed group value")
    p.add_argument("--strata", default="parity", help="for mh-rr: stratification column (default parity)")
    p.add_argument("--include-untrusted", action="store_true",
                   help="opt in to raw technician names / farm remarks (explicitly flagged in output)")
    p.add_argument("--json")
    p.add_argument("--out", help="for card: the HTML file to write")
    p.add_argument("--feed", action="store_true", help="for card: the pen feed card")
    p.add_argument("--weekly", action="store_true", help="for card: the visit review page")
    p.add_argument("--slide", action="store_true", help="for card --pen or --feed: bigger, fewer items, for a projector")
    p.add_argument("--actions", help="for card --weekly: a text file, one action a line: what to check | who")
    a = p.parse_args(argv)
    cmd = a.command

    def parse_opt_date(val: str | None, flag: str) -> date | None:
        if not val:
            return None
        parsed = io.parse_dc_date(val)
        if parsed is None:
            raise DairyToolsError(f"Could not parse {flag} date {val!r} (use YYYY-MM-DD).")
        return parsed

    def herd():
        if not a.folder:
            raise DairyToolsError("Give --folder: the folder with the farm's exports.")
        return load(a.folder, parse_opt_date(a.as_of, "--as-of"))

    def item_list():
        if not a.folder:
            return None
        paths = [f["path"] for f in io.identify_folder(a.folder) if f["kind"] == "items"]
        return io.read_item_list(paths[0]) if paths else None

    def parse_within_dim(default):
        if a.within_dim is None:
            return default
        if str(a.within_dim).lower() == "lactation":
            return "lactation"
        try:
            return int(a.within_dim)
        except ValueError as exc:
            raise DairyToolsError(f"Invalid --within-dim {a.within_dim!r}: use an integer or 'lactation'.") from exc

    try:
        if cmd == "files":
            out = io.identify_folder(a.folder or ".")
        elif cmd == "commands":
            out = commands.export_commands(item_list(), events_days=365 * a.years)
        elif cmd == "check":
            out = commands.check(" ".join(a.text), item_list())
        elif cmd == "items":
            items = item_list()
            if not items:
                raise DairyToolsError("No item list in the folder: in DairyComp, ALTER\\2 > Tools > Export > CSV.")
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
        elif cmd == "ration-lab":
            if not a.pen:
                raise DairyToolsError("Give --pen for ration-lab (e.g. --pen 21).")
            out = ecosystem.ration_lab_handoff(herd(), a.pen, a.days or 7)
        elif cmd == "loading":
            out = feeding.loading_accuracy(herd(), a.by or "ingredient", a.days)
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
        elif cmd == "scc-screen":
            out = udder.scc_screen(herd(), by=a.by or "none", fresh_dim=a.fresh_dim)
        elif cmd == "scc-dynamics":
            out = udder.scc_dynamics(herd(), by=a.by or "none")
        elif cmd == "mastitis":
            out = udder.mastitis_incidence(herd(), by=a.by or "month", first_only=a.first_only, months=a.months)
        elif cmd == "repro":
            out = weekly.reproduction(herd(), a.vwp)
        elif cmd == "pregnancy-rate":
            out = repro.pregnancy_rate(herd(), vwp=a.vwp, by=a.by or "none", cycles=a.cycles)
        elif cmd == "first-service":
            out = repro.first_service(herd(), vwp=a.vwp, by=a.by or "none")
        elif cmd == "pregnant-by":
            out = repro.pregnant_by(herd(), days=a.days or 150, by=a.by or "parity")
        elif cmd == "time-to-pregnancy":
            out = repro.time_to_pregnancy(herd(), by=a.by or "none")
        elif cmd == "pregnancy-loss":
            out = repro.pregnancy_loss(herd(), by=a.by or "none", followed_days=a.followed_days)
        elif cmd == "calving-interval":
            out = repro.calving_interval(herd(), by=a.by or "none")
        elif cmd == "age-first-calving":
            out = repro.age_first_calving(herd(), by=a.by or "none")
        elif cmd == "conception":
            out = repro.conception_by(herd(), group=a.by or "service", max_service=a.max_service,
                                      allow_untrusted=a.include_untrusted)
        elif cmd == "inter-service":
            out = repro.inter_service_intervals(herd())
        elif cmd == "heifer-repro":
            out = repro.heifer_repro(herd())
        elif cmd == "dry-period":
            out = epi.dry_period_length(herd(), by=a.by or "none")
        elif cmd == "disease-effects":
            if not a.event:
                raise DairyToolsError("Give --event: one or more std_event names (e.g. --event metritis).")
            ev = a.event[0] if len(a.event) == 1 else a.event
            out = epi.fresh_disease_effects(herd(), ev, within_dim=parse_within_dim(30), removal_dim=a.removal_dim)
        elif cmd == "risk-ratio":
            if not a.outcome or not a.exposure:
                raise DairyToolsError("Give --outcome and --exposure (columns of lactation_data, e.g. --outcome metritis --exposure retained_placenta).")
            ld = epi.lactation_data(herd(), within_dim=parse_within_dim(21))
            out = epi.risk_ratio(ld, a.outcome, a.exposure, exposed=a.exposed)
        elif cmd == "mh-rr":
            if not a.outcome or not a.exposure:
                raise DairyToolsError("Give --outcome and --exposure for mh-rr.")
            ld = epi.lactation_data(herd(), within_dim=parse_within_dim(21))
            out = epi.mantel_haenszel_rr(ld, a.outcome, a.exposure, strata=a.strata, exposed=a.exposed)
        elif cmd == "left-reasons":
            out = epi.left_reasons(
                herd(),
                from_date=parse_opt_date(a.from_date, "--from"),
                to_date=parse_opt_date(a.to_date, "--to"),
                by=a.by or "reason",
                allow_untrusted=a.include_untrusted,
            )
        elif cmd == "left-herd":
            out = epi.left_herd(herd(), within_dim=parse_within_dim(60), by=a.by or "parity")
        elif cmd == "event-months":
            if not a.event:
                raise DairyToolsError("Give --event for event-months (e.g. --event metritis).")
            ev = a.event[0] if len(a.event) == 1 else a.event
            out = epi.event_months(herd(), ev, by=a.by or "calendar_month")
        elif cmd == "survival":
            out = epi.herd_survival(herd(), by=a.by or "parity")
        elif cmd == "calving":
            out = epi.calving_outcomes(herd(), by=a.by or "parity")
        elif cmd == "audit":
            out = epi.audit_records(herd())
        elif cmd == "lactations":
            out = epi.lactation_data(herd(), within_dim=parse_within_dim(21))
        elif cmd == "exits":
            out = weekly.exits(herd())
        elif cmd == "weekly":
            out = weekly.weekly(herd(), a.milk_price, a.vwp)
        elif cmd == "card":
            h = herd()
            if a.weekly:
                acts = []
                if a.actions:
                    act_path = Path(a.actions)
                    if not act_path.is_file():
                        raise DairyToolsError(f"Actions file '{a.actions}' not found.")
                    for line in act_path.read_text(encoding="utf-8").splitlines():
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
                raise DairyToolsError("Give --pen, --cow, --feed or --weekly for the card.")
            target.write_text(page, encoding="utf-8")
            print(f"Wrote {target} ({what}). Show it as an artifact, or open it in a browser.")
            return
        else:
            raise DairyToolsError(f"Unknown command '{cmd}'. Run with --help for the list.")
    except DairyToolsError as exc:
        raise SystemExit(str(exc)) from None

    if a.json:
        Path(a.json).write_text(json.dumps(out, default=_json_default, indent=1), encoding="utf-8")
    print(text(cmd, out))


if __name__ == "__main__":
    main()
