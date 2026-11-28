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
from dairytools import epi, explorer, feeding, repro, udder, weekly  # noqa: E402
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
    # Cycle-by-cycle pregnancy_rate parity
    cyc = repro.pregnancy_rate(herd, vwp=50, by="none", cycles=True)["rows"]
    assert len(cyc) == len(lab["pregnancy_rate_cycles"])
    for p, r in zip(cyc, lab["pregnancy_rate_cycles"]):
        assert p["cycle_start"] == r["cycle_start"]
        assert (p["eligible"], p["bred"], p["pregnant"]) == (r["eligible"], r["bred"], r["pregnant"])
        assert close(p["pregnancy_rate"], r["pregnancy_rate"], 0.0011)


def test_pregnant_by_left_reasons_left_herd_event_months_and_mastitis(lab, herd):
    pb = {r["group"]: r for r in repro.pregnant_by(herd, days=150, by="parity")["rows"]}
    for r in lab["pregnant_by_150"]:
        p = pb[str(r["group"])]
        assert (p["n"], p["pregnant"]) == (r["n"], r["pregnant"])
        assert close(p["share"], r["share"], 0.0011)
        assert close(p["ci_low"], r["ci_low"], 0.0011) and close(p["ci_high"], r["ci_high"], 0.0011)

    lr = epi.left_reasons(herd, by="reason")
    ref_lr = lab["left_reasons_reason"]
    assert lr["total_left"] == ref_lr["total_left"]
    assert close(lr["average_herd"], ref_lr["average_herd"], 0.11)
    assert close(lr["cow_years"], ref_lr["cow_years"], 0.11)
    assert close(lr["total_per_100_cow_years"], ref_lr["total_per_100_cow_years"], 0.11)
    py_lr = {r["reason"]: r for r in lr["rows"]}
    for r in ref_lr["rows"]:
        p = py_lr[r["reason"]]
        assert p["n"] == r["n"] and close(p["per_100_cow_years"], r["per_100_cow_years"], 0.11)

    lr_dim = {r["group"]: r for r in epi.left_reasons(herd, by="dim_band")["rows"]}
    for r in lab["left_reasons_dim"]:
        p = lr_dim[r["group"]]
        assert (p["n"], p["sold"], p["died"]) == (r["n"], r["sold"], r["died"])

    lh = {r["group"]: r for r in epi.left_herd(herd, within_dim=60, by="parity")["rows"]}
    for r in lab["left_herd_60"]:
        p = lh[str(r["group"])]
        assert (p["n"], p["left"]) == (r["n"], r["left"])
        assert close(p["share"], r["share"], 0.0011)

    em = epi.event_months(herd, "metritis", by="calendar_month")
    py_em = {r["month"]: r for r in em["rows"]}
    for r in lab["event_months_metritis"]["rows"]:
        assert py_em[r["month"]]["cases"] == r["cases"]
    assert close(em["p_value"], lab["event_months_metritis"]["p_value"], 1e-4)

    mm = {r["month"]: r for r in udder.mastitis_incidence(herd, by="month", months=12)["rows"]}
    assert len(mm) == len(lab["mastitis_month"])
    for r in lab["mastitis_month"]:
        p = mm[r["month"]]
        assert p["cases"] == r["cases"]
        assert close(p["cows_in_milk"], r["cows_in_milk"], 0.11)
        assert close(p["per_100_cows"], r["per_100_cows"], 0.11)

    mp = udder.mastitis_incidence(herd, by="none", first_only=True, months=12)["summary"]
    rmp = lab["mastitis_pooled"]
    assert (mp["from"], mp["to"], mp["months"], mp["cases"]) == (rmp["from"], rmp["to"], rmp["months"], rmp["cases"])
    assert close(mp["cow_months"], rmp["cow_months"], 0.11)
    assert close(mp["per_100_cows_per_month"], rmp["per_100_cows_per_month"], 0.02)
    assert close(mp["ci_low"], rmp["ci_low"], 0.02) and close(mp["ci_high"], rmp["ci_high"], 0.02)


def test_first_service(lab, herd):
    fs = repro.first_service(herd, vwp=50, by="parity")
    py = {r["group"]: r for r in fs["rows"]}
    for r in lab["first_service"]["rows"]:
        p = py[r["group"]]
        assert (p["lactations"], p["bred"]) == (r["lactations"], r["bred"])
        assert close(p["median_dim"], r["median_dim"], 1e-6)
        assert close(p["mean_dim"], r["mean_dim"], 0.11)
        assert close(p["share_by_vwp21"], r["share_by_vwp21"], 0.0011)
        assert close(p["share_by_100"], r["share_by_100"], 0.0011)
    assert [(b["band"], b["lactations"]) for b in fs["bands"]] == \
        [(b["band"], b["lactations"]) for b in lab["first_service"]["bands"]]


def test_time_to_pregnancy(lab, herd):
    ttp = repro.time_to_pregnancy(herd, by="parity")
    py = {r["group"]: r for r in ttp["rows"]}
    for r in lab["time_to_pregnancy"]["rows"]:
        p = py[r["group"]]
        assert (p["lactations"], p["pregnant"]) == (r["lactations"], r["pregnant"])
        assert close(p["median_dim"], r["median_dim"], 1e-6)
        for col in ("pregnant_by_100", "pregnant_by_150", "pregnant_by_200"):
            assert close(p[col], r[col], 0.0011), (r["group"], col, p[col], r[col])
    assert close(ttp["p_value"], lab["time_to_pregnancy"]["p_value"], 1e-5)


def test_pregnancy_loss(lab, herd):
    pl = repro.pregnancy_loss(herd, by="parity")
    py = {r["group"]: r for r in pl["rows"]}
    for r in lab["pregnancy_loss"]["rows"]:
        p = py[r["group"]]
        assert (p["pregnant"], p["lost"]) == (r["pregnant"], r["lost"])
        assert close(p["share"], r["share"], 0.0011)
        assert close(p["ci_low"], r["ci_low"], 0.0011)
        assert close(p["ci_high"], r["ci_high"], 0.0011)
    assert len(pl["cases"]) == lab["pregnancy_loss"]["cases"]


def test_calving_interval(lab, herd):
    ci = repro.calving_interval(herd, by="parity")
    py = {r["group"]: r for r in ci["rows"]}
    for r in lab["calving_interval"]:
        p = py[r["group"]]
        assert (p["intervals"], p["pregnant_lactations"]) == (r["intervals"], r["pregnant_lactations"])
        assert close(p["median_days"], r["median_days"], 1e-6)
        assert close(p["mean_days"], r["mean_days"], 0.11)
        assert close(p["mean_months"], r["mean_months"], 0.11)
        assert close(p["over_14_5_months"], r["over_14_5_months"], 0.0011)
        assert close(p["days_open_median"], r["days_open_median"], 1e-6)
        assert close(p["days_open_mean"], r["days_open_mean"], 0.11)


def test_age_first_calving(lab, herd):
    afc = repro.age_first_calving(herd, by="calving_year")
    py = {r["group"]: r for r in afc["rows"]}
    for r in lab["age_first_calving"]:
        p = py[str(r["group"])]
        assert p["heifers"] == r["heifers"]
        assert close(p["median_months"], r["median_months"], 0.11)
        assert close(p["mean_months"], r["mean_months"], 0.11)
        assert close(p["over_24_months"], r["over_24_months"], 0.0011)


def test_conception_by_all_groups(lab, herd):
    for grp, expected in lab["conception_by"].items():
        # allow_untrusted=True for technician so exact names match R; also test safe default separately.
        res = repro.conception_by(herd, group=grp, allow_untrusted=(grp == "technician"))
        py = {str(r[grp]): r for r in res["rows"]}
        assert len(py) == len(expected["rows"]), grp
        for r in expected["rows"]:
            p = py[str(r[grp])]
            assert (p["services"], p["pregnant"]) == (r["services"], r["pregnant"]), (grp, r[grp])
            assert close(p["share"], r["share"], 0.0011), (grp, r[grp])
            assert close(p["ci_low"], r["ci_low"], 0.0011), (grp, r[grp])
            assert close(p["ci_high"], r["ci_high"], 0.0011), (grp, r[grp])
        assert close(res["p_value"], expected["p_value"], 1e-4), (grp, res["p_value"], expected["p_value"])
    # Verify safe default for technician anonymizes names while keeping identical counts and p-value.
    safe_tech = repro.conception_by(herd, group="technician", allow_untrusted=False)
    assert safe_tech["safety_note"] is not None
    assert [r["technician"] for r in safe_tech["rows"]] == ["Technician 1", "Technician 2", "Technician 3"]
    assert [(r["services"], r["pregnant"]) for r in safe_tech["rows"]] == \
        [(r["services"], r["pregnant"]) for r in lab["conception_by"]["technician"]["rows"]]
    assert close(safe_tech["p_value"], lab["conception_by"]["technician"]["p_value"], 1e-4)


def test_dry_period_length(lab, herd):
    dp = epi.dry_period_length(herd, by="parity")
    assert len(dp["detail"]) == lab["dry_period_length"]["n_detail"]
    py = {r["group"]: r for r in dp["rows"]}
    for r in lab["dry_period_length"]["rows"]:
        p = py[str(r["group"])]
        assert p["n"] == r["n"]
        assert close(p["median"], r["median"], 1e-6)
        assert close(p["mean"], r["mean"], 0.11)
        for col in ("share_under_30", "share_30_39", "share_40_60", "share_61_80", "share_over_80"):
            assert close(p[col], r[col], 0.0011), (r["group"], col)


def test_lactation_data_and_risk_ratio(lab, herd):
    ld = epi.lactation_data(herd)
    ref = lab["lactation_data"]
    assert len(ld) == ref["rows"]
    assert set(ld[0]) == set(ref["columns"])
    assert sum(1 for r in ld if r["pregnant"]) == ref["pregnant"]
    assert sum(1 for r in ld if r["dry_days"] is not None) == ref["dry_days_non_na"]
    for col in ("metritis", "retained_placenta", "displaced_abomasum", "clinical_mastitis", "milk_fever"):
        assert sum(1 for r in ld if r[col]) == ref[col], col

    for (outcome, exposure, exposed, key) in (
        ("metritis", "retained_placenta", None, "metritis_by_rp"),
        ("metritis", "parity", "1", "metritis_by_parity"),
    ):
        py = epi.risk_ratio(ld, outcome, exposure, exposed=exposed)
        r = lab["risk_ratio"][key]
        for k in ("exposed_cases", "exposed_n", "reference_cases", "reference_n", "test"):
            assert py[k] == r[k], (key, k)
        for k in ("exposed_risk", "reference_risk"):
            assert close(py[k], r[k], 0.0011), (key, k)
        for k in ("rr", "rr_lower", "rr_upper", "or", "or_lower", "or_upper"):
            assert close(py[k], r[k], 0.011), (key, k, py[k], r[k])
        assert close(py["p_value"], r["p_value"], max(1e-12, 0.05 * (r["p_value"] or 0))), (key, py["p_value"], r["p_value"])


def test_fresh_disease_effects(lab, herd):
    for ev in ("metritis", "retained_placenta"):
        py = epi.fresh_disease_effects(herd, ev)
        ref = lab["fresh_disease_effects"][ev]
        # Milk comparison
        py_milk = {(r["parity"], r["group"]): r for r in py["milk"]}
        for r in ref["milk"]:
            p = py_milk[(str(r["parity"]), r["group"])]
            assert p["n"] == r["n"]
            assert close(p["median"], r["median"], 1e-6)
            assert close(p["q1"], r["q1"], 1e-6)
            assert close(p["q3"], r["q3"], 1e-6)
            assert close(p["mean"], r["mean"], 0.11)
            assert close(p["p_value"], r["p_value"], 0.011)
        # Removal RR
        rem_r = ref["removal"]
        rem_p = py["removal"]
        for k in ("exposed_cases", "exposed_n", "reference_cases", "reference_n", "test"):
            assert rem_p[k] == rem_r[k], (ev, k)
        for k in ("rr", "rr_lower", "rr_upper", "or", "or_lower", "or_upper"):
            assert close(rem_p[k], rem_r[k], 0.011), (ev, k)
        assert close(rem_p["p_value"], rem_r["p_value"], 0.011)
        # Days open
        py_do = {r["group"]: r for r in py["days_open"]}
        for r in ref["days_open"]:
            p = py_do[r["group"]]
            assert (p["lactations"], p["conceived"]) == (r["lactations"], r["conceived"])
            assert close(p["median_days_open"], r["median_days_open"], 1e-6)
            assert close(p["km_median_days_to_conception"], r["km_median_days_to_conception"], 1e-6)
            assert close(p["p_value"], r["p_value"], 0.011)


def test_scc_screen_and_dynamics(lab, herd):
    for by, key in (("parity", "scc_screen_parity"), ("pen", "scc_screen_pen")):
        py = {(r["cows"], str(r["group"])): r for r in udder.scc_screen(herd, by=by)["rows"]}
        assert len(py) == len(lab[key])
        for r in lab[key]:
            p = py[(r["cows"], str(r["group"]))]
            for col in ("tested", "over_200k_cells_ml", "scs_5_plus_283k_cells_ml"):
                assert p[col] == r[col], (key, r["group"], col)
            for col in ("share_over_200k_cells_ml", "share_scs_5_plus_283k_cells_ml",
                        "scs_0_3_under_141k", "scs_4_141_282k", "scs_5_283_565k", "scs_6_plus_566k_up"):
                assert close(p[col], r[col], 0.0011), (key, r["group"], col)
            assert close(p["mean_scs"], r["mean_scs"], 0.011)

    for by, key in (("parity", "scc_dynamics_parity"), ("none", "scc_dynamics_all")):
        py = {(r["key"], str(r["group"])): r for r in udder.scc_dynamics(herd, by=by)["rows"]}
        assert len(py) == len(lab[key])
        for r in lab[key]:
            p = py[(r["key"], str(r["group"]))]
            assert (p["cows"], p["of"]) == (r["cows"], r["of"]), (key, r["key"], r["group"])
            assert close(p["percent"], r["percent"], 0.11), (key, r["key"], r["group"])


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
