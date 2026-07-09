"""Weight sweep + telemetry mechanics."""
from faultline.sweep import kendall_tau, run_sweep, score_order
from faultline.telemetry import log_evaluation, load_ledger, report
from faultline.verify import DEFAULT_PARAMS

TIERS = {"weak": 0.2, "strong": 0.8}

def rec(cid, template, cat, fp, tiers):
    return {"case_id": cid, "template": template, "category": cat,
            "fingerprint": fp, "failed_tiers": set(tiers)}

RECORDS = [
    rec("a1", "alpha", "state.rollback", "fpA", ["weak", "strong"]),
    rec("a2", "alpha", "state.rollback", "fpA", ["weak", "strong"]),  # re-skin of a1
    rec("b1", "beta", "character.substring", "fpB", ["weak"]),
    rec("b2", "beta", "character.substring", "fpB2", ["weak"]),
]

def test_score_order_deterministic_and_penalizes_duplicates():
    s1 = score_order(RECORDS, [0, 1, 2, 3], (0.4, 0.6), TIERS, DEFAULT_PARAMS)
    s2 = score_order(RECORDS, [0, 1, 2, 3], (0.4, 0.6), TIERS, DEFAULT_PARAMS)
    assert s1 == s2
    assert s1["a1"]["score"] == 1.0          # full difficulty, first discovery
    assert s1["a2"]["duplicate"]             # same fingerprint, same category
    assert s1["a2"]["novelty"] < 0.25 * s1["a1"]["novelty"] + 1e-9
    assert not s1["b2"]["duplicate"]         # new fingerprint, no duplicate penalty

def test_kendall_tau_bounds():
    r = {"x": 0, "y": 1, "z": 2}
    assert kendall_tau(r, r) == 1.0
    assert kendall_tau(r, {"x": 2, "y": 1, "z": 0}) == -1.0

def test_run_sweep_shapes_and_flags():
    # n_orders=20: seeds are fixed, so the flag outcome below is deterministic
    res = run_sweep(records=RECORDS, combos=[(0.4, 0.6), (0.6, 0.4)],
                    n_orders=20, params=DEFAULT_PARAMS, tier_weights=TIERS)
    assert res["n_cases"] == 4
    for combo in ["0.4/0.6", "0.6/0.4"]:
        r = res["combos"][combo]
        assert set(r["strategy_revenue"]) == {"alpha", "beta"}
        assert -1.0 <= r["kendall_tau_vs_baseline"] <= 1.0
    # the re-skin a2 always duplicates regardless of order
    assert "a2" in res["combos"]["0.4/0.6"]["flags"]["difficulty_farmed"]

def test_telemetry_report_and_overmined_flag(tmp_path):
    ledger = tmp_path / "ledger.jsonl"
    valid = {"gate": "VALID", "score": 0.8, "novelty": 0.5, "difficulty": 0.5,
             "failure_category": "state.rollback", "fingerprint": "fpX",
             "duplicate_fingerprint": True}
    for i in range(12):
        log_evaluation({"case_id": f"c{i}"}, dict(valid, duplicate_fingerprint=i >= 4),
                       path=ledger)
    log_evaluation({"case_id": "junk"}, {"gate": "UNSOLVABLE", "score": 0.0}, path=ledger)
    rep = report(load_ledger(ledger))
    assert rep["totals"] == {"submissions": 13, "valid": 12}
    cat = rep["per_category"]["state.rollback"]
    assert cat["valid_submissions"] == 12
    assert cat["distinct_fingerprints"] == 1
    assert cat["duplicate_share"] > 0.5 and cat["overmined"]
    assert rep["overmined_categories"] == ["state.rollback"]
