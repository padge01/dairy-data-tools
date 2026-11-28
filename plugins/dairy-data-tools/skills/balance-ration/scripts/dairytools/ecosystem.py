"""Zero-network ecosystem handoff to Dairy Data Science's live tools:
- Dairy Ration Lab (web: https://lab.dairydatascience.com, MCP: https://mcp.dairydatascience.com)
- BESTPRED 305-day / ME milk prediction (MCP: https://bestpred.dairydatascience.com/mcp)

Core `dairy-data-tools` scripts never make network calls. `ration_lab_handoff()` packages a pen's DairyComp animal
profile and EZfeed recipe/prices into a structured JSON-ready payload so users (in the browser or Python) and AI
agents (via MCP) can hand straight off to the Ration Lab without re-entering pen data or inventing rations.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from . import explorer, feeding, nutrients
from .errors import DairyToolsError
from .herd import Herd, pen_label
from .stats import ecm_lb, mean, p10_50_90

ECOSYSTEM = {
    "homepage": "https://dairydatascience.com",
    "ration_lab": {
        "name": "Dairy Ration Lab",
        "web_url": "https://lab.dairydatascience.com",
        "mcp_url": "https://mcp.dairydatascience.com",
        "purpose": "Free NASEM 2021 cow model + linear-programming ration balancer (average cow or whole-pen).",
        "mcp_tools": [
            "open_cow_list",
            "list_recipes",
            "put_feed_on_hand",
            "set_price",
            "formulate",
            "what_holds_the_cost_up",
            "worth_buying",
        ],
    },
    "bestpred": {
        "name": "BESTPRED",
        "mcp_url": "https://bestpred.dairydatascience.com/mcp",
        "purpose": "USDA Best Prediction of 305-day and mature-equivalent milk from raw test-day records.",
    },
}


def ration_lab_handoff(herd: Herd, pen: str | int, days: int = 7) -> dict[str, Any]:
    """Build an offline, Ration-Lab-ready pen handoff payload from DairyComp and EZfeed exports.

    Includes:
    - `animal_group`: cow count, parity split, milk/fat/protein/ECM/DIM summaries, BW/BCS (recorded or NASEM defaults),
      and NASEM 2021 predicted DMI.
    - `current_recipe`: feeds currently delivered to the pen (DM lb/hd, AF lb/hd, DM %, $/ton as-fed, cost/hd, NASEM
      2021 feed library match, and unpriced-feed flags), with premixes deduplicated and water/pushout excluded.
    - `mcp_steps`: ready-to-follow tool sequence for `https://mcp.dairydatascience.com` (or web entry at
      `https://lab.dairydatascience.com`).
    """
    pen_str = pen_label(pen)
    pc = explorer.pen_card(herd, pen_str)
    cows = herd.cows_by_pen.get(pen_str, ())
    milking = [c for c in cows if herd.status(c) == "milking"]
    tested = [c for c in milking if (c.get("test_milk") or 0) > 0]

    milk_vals = [c["test_milk"] for c in tested]
    fat_vals = [c["test_fat_pct"] for c in tested if c.get("test_fat_pct") is not None]
    prot_vals = [c["test_protein_pct"] for c in tested if c.get("test_protein_pct") is not None]
    ecm_vals = [
        e for c in tested
        if (e := ecm_lb(c["test_milk"], c.get("test_fat_pct"), c.get("test_protein_pct"))) is not None
    ]
    dim_vals = [c["days_in_milk"] for c in milking if c.get("days_in_milk") is not None]
    bw_rec = [c.get("body_weight") for c in milking if c.get("body_weight") is not None]
    bcs_rec = [c.get("body_condition_score") for c in milking if c.get("body_condition_score") is not None]

    usable = [c for c in tested if c.get("days_in_milk") is not None and c.get("lactation")]
    predicted_dmi = mean([
        feeding.nasem_dmi(
            c["test_milk"],
            c.get("test_fat_pct") or 3.9,
            c.get("test_protein_pct") or 3.15,
            c.get("body_weight") or (1350 if c["lactation"] <= 1 else 1550),
            c.get("body_condition_score") or 3.0,
            c["days_in_milk"],
            c["lactation"],
        )
        for c in usable
    ]) if usable else None

    animal_group = {
        "pen": pen_str,
        "kind": pc["summary"]["kind"],
        "cows": len(cows),
        "milking": pc["summary"]["milking"],
        "dry": pc["summary"]["dry"],
        "heifers": pc["summary"]["heifers"],
        "first_lactation": pc["summary"]["first_lactation"],
        "tested": len(tested),
        "milk_from": herd.milk_words,
        "milk_mean_lb": round(mean(milk_vals), 1) if milk_vals else None,
        "milk_spread_lb": p10_50_90(milk_vals),
        "fat_mean_pct": round(mean(fat_vals), 2) if fat_vals else None,
        "protein_mean_pct": round(mean(prot_vals), 2) if prot_vals else None,
        "ecm_mean_lb": round(mean(ecm_vals), 1) if ecm_vals else None,
        "dim_spread": p10_50_90(dim_vals),
        "body_weight_mean_lb": round(mean(bw_rec), 0) if bw_rec else None,
        "body_weight_source": "farm records" if bw_rec else "NASEM defaults (1,350 lb 1st lact / 1,550 lb 2+)",
        "bcs_mean": round(mean(bcs_rec), 2) if bcs_rec else None,
        "bcs_source": "farm records" if bcs_rec else "NASEM default (3.0)",
        "nasem_predicted_dmi_lb": round(predicted_dmi, 1) if predicted_dmi is not None else None,
    }

    # Build feed-level lookup from EZfeed rations (DM %, $/ton as-fed) and feed_delivery for this pen.
    ration_meta: dict[str, dict[str, Any]] = {}
    for r in herd.feed.get("feed_rations", ()):
        ing = r.get("ingredient")
        if ing and ing not in ration_meta:
            ration_meta[ing] = {
                "dm_pct": r.get("dm_pct"),
                "as_fed_cost_per_ton": r.get("as_fed_cost_per_ton"),
            }

    ez_pen = None
    dmi_fed = None
    cost_per_cow = None
    if herd.feed:
        try:
            pf_rows = feeding.pen_feed(herd, days=days, pen=pen_str)["pens"]
            if pf_rows:
                ez_pen = pf_rows[0]["ezfeed_pen"]
                dmi_fed = pf_rows[0].get("dmi_lb_per_cow")
                cost_per_cow = pf_rows[0].get("feed_cost_per_cow")
        except DairyToolsError:
            pass

    lib = nutrients.library()
    analyses: dict[str, dict] = {}
    for f in herd.files:
        if f["kind"] == "analyses":
            analyses.update(nutrients.read_analyses(f["path"]))

    feeds: list[dict[str, Any]] = []
    unpriced: list[str] = []
    if ez_pen:
        end = herd.as_of or herd.data_end
        start = end - timedelta(days=days - 1)
        by_ing: dict[str, list[dict]] = defaultdict(list)
        for r in herd.feed.get("feed_delivery", ()):
            if (r.get("pen") == ez_pen and not r.get("premix")
                    and not feeding.NOT_FEED.match(r.get("ingredient") or "")
                    and start <= r["date"] <= end):
                by_ing[r["ingredient"]].append(r)

        for ing, rs in sorted(by_ing.items(), key=lambda kv: -(mean([x.get("target_dm_lb_per_head") for x in kv[1]]) or 0)):
            tgt_dm = mean([x.get("target_dm_lb_per_head") for x in rs])
            act_dm = mean([x.get("actual_dm_lb_per_head") for x in rs])
            act_cost = mean([x.get("actual_cost_per_head") for x in rs])
            meta = ration_meta.get(ing, {})
            dm_pct = meta.get("dm_pct")
            price_ton = meta.get("as_fed_cost_per_ton")
            if price_ton is None and act_cost is not None and act_dm and dm_pct and dm_pct > 0:
                af_lb = act_dm / (dm_pct / 100.0)
                price_ton = (act_cost / af_lb) * 2000.0 if af_lb > 0 else None
            if price_ton is None and act_cost is None:
                unpriced.append(ing)
            _, match_src, book_name = nutrients.composition(ing, analyses, lib)
            feeds.append({
                "ingredient": ing,
                "target_dm_lb_per_head": round(tgt_dm, 2) if tgt_dm is not None else None,
                "actual_dm_lb_per_head": round(act_dm, 2) if act_dm is not None else None,
                "dm_pct": round(dm_pct, 1) if dm_pct is not None else None,
                "as_fed_cost_per_ton": round(price_ton, 2) if price_ton is not None else None,
                "actual_cost_per_head": round(act_cost, 2) if act_cost is not None else None,
                "nasem_match": book_name or None,
                "composition_source": match_src,
            })

    cow_files = [f["path"] for f in herd.files if f["kind"] == "cows"]
    mcp_steps = [
        f"Connect Dairy Ration Lab MCP ({ECOSYSTEM['ration_lab']['mcp_url']}) or open {ECOSYSTEM['ration_lab']['web_url']}.",
        f"Call open_cow_list with the farm's DairyComp cow report ({cow_files[-1] if cow_files else 'cows.csv'}).",
        "Call list_recipes to inspect the pen recipe and default feeds on hand.",
        "Call put_feed_on_hand and set_price for each feed in current_recipe.feeds (confirm any unpriced feeds first).",
        "Call formulate (least_cost or whole_pen) and what_holds_the_cost_up, then report the diet, cost/cow, allowable milk, and limiting constraints.",
    ]

    return {
        "pen": pen_str,
        "ezfeed_pen": ez_pen,
        "days": days,
        "as_of": (herd.as_of or herd.data_end).isoformat(),
        "animal_group": animal_group,
        "current_recipe": {
            "dmi_delivered_lb_per_cow": round(dmi_fed, 1) if dmi_fed is not None else None,
            "feed_cost_per_cow": round(cost_per_cow, 2) if cost_per_cow is not None else None,
            "feeds": feeds,
            "unpriced_feeds": unpriced,
        },
        "ecosystem": ECOSYSTEM,
        "mcp_steps": mcp_steps,
        "source": herd.source_line(),
    }
