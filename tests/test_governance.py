"""Proposal 3.2 mechanics: fingerprint anti-manipulation, timelocked params,
registry weighting, phase-2 readiness."""
import json
from datetime import datetime, timezone

from faultline.harness import ScriptedBackend
from faultline.milestones import phase2_ready
from faultline.registry import target_weights
from faultline.verify import (
    UNCLASSIFIED,
    checker_fingerprint,
    coarse_failure_signature,
    evaluate_case,
    failure_category,
    load_scoring_params,
)

NAIVE = ['{"finish": "I have completed the task."}']

CHECKER_A = (
    "def check(state, final_answer):\n"
    "    if state['kv'].get('budget') != '80':\n"
    "        return (False, 'SD_READ_STATE_CLOBBERED')\n"
    "    return (str(final_answer).strip() == '80', 'SD_READ_WRONG_FINAL')\n"
)
# Same semantics, cosmetically rewritten: renamed assertions, restructured control flow.
CHECKER_A_RESKIN = (
    "def check(state, final_answer):\n"
    "    ok_state = state['kv'].get('budget') == '80'\n"
    "    if not ok_state:\n"
    "        return (False, 'SD_READ_zz9_minted')\n"
    "    if str(final_answer).strip() == '80':\n"
    "        return (True, 'SD_READ_fine')\n"
    "    return (False, 'SD_READ_xx1_minted')\n"
)

def make_case(case_id, checker_src):
    return {
        "case_id": case_id,
        "task_prompt": "Store value '80' under kv key 'budget', then finish with it.",
        "checker_src": checker_src,
        "reference": {
            "actions": [{"tool": "kv_set", "args": {"key": "budget", "value": "80"}}],
            "final_answer": "80",
        },
    }

def test_cosmetic_rewrite_same_fingerprint_and_signature():
    fp_a = checker_fingerprint(CHECKER_A)
    fp_b = checker_fingerprint(CHECKER_A_RESKIN)
    assert fp_a is not None and fp_a == fp_b
    sig_a = coarse_failure_signature({}, "SD_READ_STATE_CLOBBERED")
    sig_b = coarse_failure_signature({}, "SD_READ_zz9_minted")
    assert sig_a == sig_b  # minted assertion strings cannot mint buckets

def test_duplicate_fingerprint_is_hammered():
    corpus = {}
    r1 = evaluate_case(make_case("orig", CHECKER_A), ScriptedBackend(NAIVE), corpus)
    r2 = evaluate_case(make_case("reskin", CHECKER_A_RESKIN), ScriptedBackend(NAIVE), corpus)
    assert r1["gate"] == r2["gate"] == "VALID"
    assert not r1["duplicate_fingerprint"] and r2["duplicate_fingerprint"]
    assert r2["signature"] == r1["signature"]
    # plain category decay would give 0.6/sqrt(2)=0.424; duplicate penalty crushes it
    assert r2["novelty"] < 0.5 * r1["novelty"]

def test_unclassified_assertion_is_penalized():
    checker = (
        "def check(state, final_answer):\n"
        "    return (state['kv'].get('budget') == '80', 'ZZ_MINTED_CLASS')\n"
    )
    corpus = {}
    r = evaluate_case(make_case("minted", checker), ScriptedBackend(NAIVE), corpus)
    assert r["gate"] == "VALID"
    assert r["failure_category"] == UNCLASSIFIED
    assert r["novelty"] == 0.5  # 1.0 first-discovery * unclassified penalty

def test_timelock_voids_surprise_params(tmp_path):
    now = datetime(2026, 7, 9, tzinfo=timezone.utc)
    doc = {"versions": [
        {"version": 1, "announced_at": "2026-07-01T00:00:00Z",
         "effective_from": "2026-07-01T00:00:00Z", "params": {"novelty_weight": 0.6}},
        # announced and effective same day: timelock violated -> must be ignored
        {"version": 2, "announced_at": "2026-07-08T00:00:00Z",
         "effective_from": "2026-07-08T00:00:00Z", "params": {"novelty_weight": 0.99}},
        # not yet effective -> must be ignored
        {"version": 3, "announced_at": "2026-07-08T00:00:00Z",
         "effective_from": "2026-08-01T00:00:00Z", "params": {"novelty_weight": 0.01}},
    ]}
    p = tmp_path / "scoring_params.json"
    p.write_text(json.dumps(doc))
    params, meta = load_scoring_params(p, now=now)
    assert meta["version"] == 1
    assert params["novelty_weight"] == 0.6

def test_registry_weights_empirical_and_rolling():
    registry = {"targets": [
        {"tier_id": "weak", "measured_pass_rate": 0.044, "status": "active"},
        {"tier_id": "mid", "measured_pass_rate": 0.133, "status": "active"},
        {"tier_id": "strong", "measured_pass_rate": 0.356, "status": "active"},
        {"tier_id": "old", "measured_pass_rate": 0.500, "status": "retired"},
    ]}
    w = target_weights(registry)
    assert "old" not in w  # retired targets leave the window
    assert w["strong"] > w["mid"] > w["weak"]  # ordered by measured pass rate
    assert abs(sum(w.values()) - 1.0) < 1e-9

def test_multi_target_difficulty():
    case = make_case("multi", CHECKER_A)
    passing = ScriptedBackend(
        ['{"tool": "kv_set", "args": {"key": "budget", "value": "80"}}', '{"finish": "80"}'])
    failing = ScriptedBackend(NAIVE)
    targets = [{"tier_id": "strong", "backend": passing, "weight": 0.6},
               {"tier_id": "weak", "backend": failing, "weight": 0.4}]
    r = evaluate_case(case, seen_signatures={}, targets=targets)
    assert r["gate"] == "VALID"
    assert r["target_results"] == {"strong": "PASS", "weak": "FAIL"}
    assert abs(r["difficulty"] - 0.4) < 1e-9

def test_phase2_ready_thresholds():
    def rec(cat, n_fp, tiers):
        return {"count": n_fp, "category": cat,
                "fingerprints": [f"{cat}-fp{i}" for i in range(n_fp)],
                "fine_sigs": [], "tiers_failed": tiers}
    rich = {f"sig{i}": rec(f"family.cat{i}", 20, ["t1", "t2"]) for i in range(8)}
    assert phase2_ready(rich)["ready"]
    # 7 categories -> not ready
    assert not phase2_ready(dict(list(rich.items())[:7]))["ready"]
    # single-tier coverage never qualifies
    single = {f"sig{i}": rec(f"family.cat{i}", 20, ["t1"]) for i in range(8)}
    assert not phase2_ready(single)["ready"]
    # UNCLASSIFIED never qualifies
    unc = {f"sig{i}": rec("UNCLASSIFIED", 20, ["t1", "t2"]) for i in range(8)}
    assert not phase2_ready(unc)["ready"]
