"""What a ration holds: each feed's composition from the farm's own analyses where it has them, NASEM (2021) book values
otherwise, matched by the feed's name; and each pen's dry matter fed by day split into aNDF, starch, CP, fat and the
rest. Every match is reported, so a card can say where its numbers came from."""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from . import io

LIBRARY = Path(__file__).with_name("data") / "nasem_feeds.csv"
LAYERS = (("ndf", "aNDF"), ("starch", "Starch"), ("cp", "CP"), ("fat", "Fat"), ("other", "Sugar, ash, other"))

# A farm's name for a feed -> NASEM's. The first match wins, so the more particular names come first.
MATCH = (
    (r"corn\s*silage", "Corn silage, typical"),
    (r"earlage|snaplage|high\s*moist|\bhmc\b|\bhm\s*corn", "Corn grain HM, coarse grind"),
    (r"steam(ed)?[\s-]*flak", "Corn grain, steam-flaked"),
    (r"(alfalfa|lucerne|legume).*(silage|haylage)|haylage", "Legume silage, mid-maturity"),
    (r"alfalfa|lucerne|legume", "Legume hay, mid-maturity"),
    (r"wheat.*silage|small grain.*silage|triticale.*silage|oat.*silage", "Wheat silage, HEADED"),
    (r"wheat\s*hay|oat\s*hay|small grain\s*hay", "Wheat hay, headed"),
    (r"straw", "Wheat straw"),
    (r"grass\s*hay|\bhay\b", "Cool season grass hay, mid-mtr"),
    (r"canola\s*oil", "Fat, canola oil"),
    (r"canola", "Canola meal"),
    (r"soy.*hull", "Soybean hulls"),
    (r"soy", "Soybean meal, solvent 48CP"),
    (r"\bddgs?\b|distillers?\s*(dried\s*)?grain|dried distillers", "DDGS, low fat"),
    (r"cottonseed\s*meal", "Cottonseed meal"),
    (r"cottonseed\s*hull", "Cottonseed hulls"),
    (r"cottonseed|\bcotton\b", "Cottonseed, whole"),
    (r"almond", "Almond hulls"),
    (r"beet\s*pulp", "Beet pulp, dry"),
    (r"citrus", "Citrus pulp, dry"),
    (r"molasses", "Molasses"),
    (r"whey", "Whey, wet"),
    (r"bypass|calcium soap|megalac|energy booster|\bfat\b", "Calcium soaps"),
    (r"barley", "Barley grain, steam rolled"),
    (r"corn|maize", "Corn grain dry, coarse grind"),
)
# Minerals, premixes and additives: no NDF, starch, protein or fat to speak of; all of it counts as "the rest".
MINERAL = re.compile(r"mineral|premix|vitamin|\bsalt\b|buffer|bicarb|limestone|rumensin|monensin|yeast|additive|"
                     r"binder|magnesium|mag ox|selenium|\bmix\b", re.I)


def library() -> dict[str, dict]:
    with open(LIBRARY, encoding="utf-8") as f:
        return {r["name"]: {k: (float(v) if k not in ("name", "category") and v else v) for k, v in r.items()}
                for r in csv.DictReader(f)}


def read_analyses(path) -> dict[str, dict]:
    """The farm's own feed analyses: a CSV with a feed name and, as % of DM, NDF, starch, CP and fat (any of these
    headers: feed/ingredient/name, ndf/andf, starch, cp/protein, fat/fa/ee, sugar/wsc, ash)."""
    rows = list(csv.DictReader(io.read_lines(path)))
    if not rows:
        return {}
    keys = {k: k.strip().lower() for k in rows[0]}
    pick = lambda *names: next((k for k, low in keys.items() if low in names), None)
    name = pick("feed", "ingredient", "name", "feed name")
    cols = {"ndf": pick("ndf", "andf", "andfom"), "starch": pick("starch", "st"), "cp": pick("cp", "protein", "crude protein"),
            "fat": pick("fat", "fa", "ee", "fatty acids"), "wsc": pick("sugar", "wsc", "esc"), "ash": pick("ash")}
    out = {}
    for r in rows:
        if name and (r.get(name) or "").strip():
            out[r[name].strip().lower()] = {k: io.number(r.get(c)) if c else None for k, c in cols.items()}
    return out


def is_analyses(header: list[str]) -> bool:
    low = {h.strip().lower() for h in header}
    return bool(low & {"feed", "ingredient", "feed name"}) and bool(low & {"ndf", "andf"}) and bool(low & {"cp", "protein"})


def composition(feed: str, analyses: dict, lib: dict) -> tuple[dict, str, str]:
    """(% of DM by layer, where it came from: "farm" | "book" | "mineral" | "none", the book feed's name or "")."""
    own = analyses.get(feed.strip().lower())
    if own and own.get("ndf") is not None:
        c = {"ndf": own["ndf"] or 0, "starch": own.get("starch") or 0, "cp": own.get("cp") or 0, "fat": own.get("fat") or 0}
        return _with_rest(c), "farm", ""
    if MINERAL.search(feed):
        return {"ndf": 0, "starch": 0, "cp": 0, "fat": 0, "other": 100}, "mineral", ""
    for pattern, book in MATCH:
        if re.search(pattern, feed, re.I) and book in lib:
            b = lib[book]
            return _with_rest({"ndf": b["ndf"] or 0, "starch": b["starch"] or 0, "cp": b["cp"] or 0,
                               "fat": b["fa"] or 0}), "book", book
    return {"ndf": 0, "starch": 0, "cp": 0, "fat": 0, "other": 100}, "none", ""


def _with_rest(c: dict) -> dict:
    named = sum(c.values())
    if named > 100:   # analyses that overlap: scale the named parts to the whole
        c = {k: v * 100 / named for k, v in c.items()}
        named = 100
    return {**c, "other": 100 - named}


def pen_layers_by_day(herd, ezfeed_pen: str, analyses: dict | None = None) -> tuple[dict, dict]:
    """Each day's share of the pen's delivered dry matter in each layer, {day: {layer: share}}, from EZfeed's feeds by
    day (premix lines once; Pushout and water left out), and how each feed was valued: {feed: (source, book name)}."""
    from .feeding import NOT_FEED
    lib = library()
    analyses = analyses or {}
    by_day = defaultdict(lambda: defaultdict(float))
    totals = defaultdict(float)
    how = {}
    for r in herd.feed.get("feed_delivery", []):
        if r["pen"] != ezfeed_pen or r.get("premix") or NOT_FEED.match(r["ingredient"] or ""):
            continue
        dm = r.get("actual_dm_lb_per_head") or 0
        if dm <= 0:
            continue
        comp, source, book = composition(r["ingredient"], analyses, lib)
        how[r["ingredient"]] = (source, book)
        for layer, _ in LAYERS:
            by_day[r["date"]][layer] += dm * comp[layer] / 100
        totals[r["date"]] += dm
    shares = {d: {layer: v / totals[d] for layer, v in layers.items()} for d, layers in by_day.items() if totals[d] > 0}
    return shares, how


def source_words(how: dict) -> str:
    """One line for a card: how many feeds were valued from what."""
    count = defaultdict(list)
    for feed, (source, _) in how.items():
        count[source].append(feed)
    parts = []
    if count["farm"]:
        parts.append(f"the farm's analyses for {len(count['farm'])} feed{'s' if len(count['farm']) != 1 else ''}")
    if count["book"]:
        parts.append(f"NASEM (2021) book values for {len(count['book'])}")
    if count["mineral"]:
        parts.append(f"{len(count['mineral'])} mineral or premix counted as the rest")
    if count["none"]:
        parts.append(f"not matched, counted as the rest: {', '.join(sorted(count['none']))}")
    return "What's in it: " + "; ".join(parts) + "." if parts else ""
