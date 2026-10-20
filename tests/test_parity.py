"""The Python port against the author's earlier R version, number for number, on the same simulated farm.

tests/parity/herd is the R version's simulate_herd(n_cows = 400, seed = 11, farm = "c", feed = TRUE, layout = "commercial")
(tests/parity/simulate.R); tests/parity/lab_results.json is what the R version's intake and analyses give on it
(tests/parity/run_lab.R). Differences allowed: the R version rounds some figures before subtracting (a cent, a tenth).
"""

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from dairytools import explorer, feeding, weekly  # noqa: E402
from dairytools.herd import load  # noqa: E402

PARITY = ROOT / "tests" / "parity"
pytestmark = pytest.mark.skipif(not (PARITY / "lab_results.json").exists(), reason="no lab results")


@pytest.fixture(scope="module")
def lab():
    return json.loads((PARITY / "lab_results.json").read_text())


@pytest.fixture(scope="module")
def herd():
    return load(PARITY / "herd")


def close(a, b, tol):
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) <= tol)


def test_herd_and_lactations(lab, herd):
    assert str(herd.as_of) == lab["as_of"]
    status = Counter(herd.status(c) for c in herd.cows)
    assert {k: v for k, v in lab["status"].items() if v} == dict(status)
    assert len(herd.lactations) == lab["lactations"]
    assert dict(Counter(l["end_reason"] for l in herd.lactations)) == lab["end_reasons"]
    s = explorer.herd_summary(herd)
    t = s["test"]
    assert s["median_dim"] == lab["herd"]["median_dim"]
    assert t["tested"] == lab["herd"]["tested"] and t["scc_over_200"] == lab["herd"]["scc_over_200"]
    for q in ("p10", "p50", "p90"):
        assert close(t["milk_lb"][q], lab["herd"][q], 1e-6)
    assert s["lactation"] == lab["herd"]["lactation"]
    assert s["repro"] == lab["herd"]["repro"]


def test_pens(lab, herd):
    py = {p["pen"]: p for p in explorer.pen_summary(herd)}
    assert len(py) == len(lab["pens"])
    for r in lab["pens"]:
        p = py[str(r["pen"])]
        assert p["animals"] == r["cows"]
        for k in ("milking", "dry", "heifers", "first_lactation", "pregnant", "tested", "scc_tested", "scc_over_200"):
            assert p[k] == r[k], (r["pen"], k)
        assert close(p["median_dim"], r["median_dim"], 1e-6) and close(p["median_test_milk"], r["median_test_milk"], 1e-6)


def test_pen_card(lab, herd):
    pc = explorer.pen_card(herd, 21)
    for q in ("p10", "p50", "p90"):
        assert close(pc["test"]["milk_lb"][q], lab["pen21"]["milk"][q], 1e-6)
    assert [(h["event"], h["events"], h["cows"]) for h in pc["health"]] == \
        [(h["event"].replace("_", " "), h["events"], h["cows"]) for h in lab["pen21"]["health"]]


def test_disease_risk(lab, herd):
    for event, rows in lab["incidence"].items():
        if rows is None:
            continue
        py = weekly.incidence(herd, event, 30, "parity")["rows"]
        assert [(r["group"], r["lactations"], r["cases"]) for r in rows] == \
            [(r["group"], r["lactations"], r["cases"]) for r in py], event


def test_pregnancy_rate(lab, herd):
    py = {r["parity"]: r for r in weekly.reproduction(herd, 50)["pregnancy_rate"]}
    for r in lab["pregnancy_rate"]:
        p = py[r["group"]]
        assert (p["eligible"], p["bred"], p["pregnant"]) == (r["eligible"], r["bred"], r["pregnant"])


def test_feed_efficiency_and_iofc(lab, herd):
    py = {p["pen"]: p for p in feeding.pen_feed(herd, days=7, milk_price=21)["pens"]}
    for r in lab["feed_efficiency"]:
        p = py[str(r["dc_pen"])]
        assert p["cows"] == r["cows"]
        assert close(p["milk_mean_lb"], r["milk"], 0.051) and close(p["ecm_mean_lb"], r["ecm"], 0.051)
        assert close(p["dmi_lb_per_cow"], r["dmi_per_cow"], 0.051)
        assert close(p["ecm_per_lb_dm"], r["feed_efficiency"], 0.006)
    for r in lab["iofc"]:
        p = py[str(r["dc_pen"])]
        assert close(p["feed_cost_per_cow"], r["feed_cost_per_cow"], 0.0051)
        assert close(p["iofc_per_cow"], r["iofc"], 0.011)


def test_loading_refusals_consistency(lab, herd):
    li = {x["ingredient"]: x for x in feeding.loading_accuracy(herd)["rows"]}
    assert len(li) == len(lab["loading_ingredient"])
    for r in lab["loading_ingredient"]:
        assert close(li[r["ingredient"]]["mean_deviation_pct"], r["mean_deviation_pct"], 0.051)
        assert close(li[r["ingredient"]]["sd_deviation_pct"], r["sd_deviation_pct"], 0.051)
    lf = {x["feeder"]: x for x in feeding.loading_accuracy(herd, by="feeder")["rows"]}
    for r in lab["loading_feeder"]:
        assert lf[r["feeder"]]["loads"] == r["loads"]
        assert close(lf[r["feeder"]]["mean_abs_deviation_pct"], r["mean_abs_deviation_pct"], 0.0051)
    rf = {x["pen"]: x for x in feeding.refusals(herd, 7)["rows"]}
    for r in lab["refusals"]:
        assert close(rf[r["pen"]]["refusal_pct"], r["refusal_pct"], 0.0051)
    cs = {x["pen"]: x for x in feeding.consistency(herd, 14)["rows"]}
    for r in lab["consistency"]:
        c = cs[r["pen"]]
        assert close(c["mean_change_lb"], r["mean_abs_change_lb"], 0.0051)
        assert c["changes_over_2_lb"] == r["changes_over_2_lb"]
        assert c["usual_feed_time"] == r["usual_feed_time"]
        assert close(c["share_within_10_min"], r["share_within_10_min"], 0.0006)
