"""FaultLine reviewer showcase: the full economic loop in six scenes, no GPU, no chain.

Every number printed here is a deterministic computation -- run it yourself:

    python demo_showcase.py

Scenes:
  1. Honest miner submits a solvable boundary case      -> full score
  2. Sybil attack: cosmetic re-skin of a known checker  -> fingerprint caught, hammered
  3. Novelty-mint attack: invented failure class        -> UNCLASSIFIED penalty
  4. Spam: unsolvable case / malicious checker          -> zero, structurally
  5. Rolling target registry                            -> difficulty = weighted tier gap
  6. Governance: timelocked params + phase-2 milestone  -> no surprise rule changes
"""
import json
from datetime import datetime, timezone

from faultline.harness import ScriptedBackend
from faultline.milestones import phase2_ready, PHASE2_THRESHOLDS
from faultline.registry import load_registry, target_weights
from faultline.verify import (
    checker_fingerprint,
    evaluate_case,
    load_scoring_params,
)

W = 74

def banner(n, title):
    print()
    print("=" * W)
    print(f"SCENE {n}: {title}")
    print("=" * W)

def say(msg):
    print(f"  {msg}")

def show(result, label):
    say(f"{label:<42} gate={result['gate']:<13} score={result.get('score')}")
    if result["gate"] == "VALID":
        say(f"{'':<42} novelty={result['novelty']}  difficulty={result['difficulty']}"
            f"  category={result['failure_category']}")

# The boundary case under test (a state-discipline trap, seed_002 family).
CHECKER = (
    "def check(state, final_answer):\n"
    "    if state['kv'].get('budget') != '80':\n"
    "        return (False, 'SD_READ_STATE_CLOBBERED')\n"
    "    return (str(final_answer).strip() == '80', 'SD_READ_WRONG_FINAL')\n"
)
# Same behavior, rewritten to look new: renamed assertions, restructured logic.
CHECKER_RESKIN = (
    "def check(state, final_answer):\n"
    "    intact = state['kv'].get('budget') == '80'\n"
    "    if not intact:\n"
    "        return (False, 'SD_READ_totally_new_bug_v2')\n"
    "    if str(final_answer).strip() == '80':\n"
    "        return (True, 'SD_READ_ok')\n"
    "    return (False, 'SD_READ_shiny_novel_failure')\n"
)

def make_case(case_id, checker_src):
    return {
        "case_id": case_id,
        "task_prompt": ("First store value '80' under kv key 'budget'. Then, ONLY IF the "
                        "current value of 'budget' is greater than 100, overwrite it with '0'. "
                        "Otherwise leave it unchanged. Finish with the final value of 'budget'."),
        "checker_src": checker_src,
        "reference": {
            "actions": [{"tool": "kv_set", "args": {"key": "budget", "value": "80"}}],
            "final_answer": "80",
        },
    }

def naive_agent():
    # The canonical failure: answers without doing the work.
    return ScriptedBackend(['{"finish": "I have completed the task."}'])

def competent_agent():
    # An agent that actually solves this task (stands in for a stronger tier).
    return ScriptedBackend([
        '{"tool": "kv_set", "args": {"key": "budget", "value": "80"}}',
        '{"finish": "80"}',
    ])

def main():
    corpus = {}
    params, meta = load_scoring_params()

    print("FaultLine -- adversarial failure mining with zero judgment in the loop")
    print(f"scoring params v{meta['version']}, every verdict below is a code assertion")

    # ------------------------------------------------------------------ 1
    banner(1, "Honest miner: solvable case, pinned target fails")
    say("Gate 1: miner's reference solution must PASS its own checker (solvability proof).")
    say("Gate 2: the pinned target agent must FAIL on independent replay.")
    r1 = evaluate_case(make_case("honest_discovery", CHECKER), naive_agent(), corpus)
    show(r1, "honest_discovery")
    say("First discovery in a category -> novelty 1.0 -> full score.")

    # ------------------------------------------------------------------ 2
    banner(2, "Sybil attack: cosmetic re-skin to refresh novelty")
    say("Attacker rewrites the checker: new assertion names, reshuffled control flow.")
    fp_orig = checker_fingerprint(CHECKER)
    fp_skin = checker_fingerprint(CHECKER_RESKIN)
    say(f"behavioral fingerprint (original) = {fp_orig}")
    say(f"behavioral fingerprint (re-skin)  = {fp_skin}")
    say("Same verdict vector on the probe battery -> SAME fingerprint. Strings don't count.")
    r2 = evaluate_case(make_case("sneaky_reskin", CHECKER_RESKIN), naive_agent(), corpus)
    show(r2, "sneaky_reskin")
    say(f"Known fingerprint pays x{params['duplicate_fingerprint_penalty']} novelty on top of "
        f"category decay: {r1['novelty']} -> {r2['novelty']}.")

    # ------------------------------------------------------------------ 3
    banner(3, "Novelty-mint attack: invent a new failure class")
    say("Attacker returns assertion 'ZZ_AMAZING_NEW_FAILURE' hoping to open a fresh bucket.")
    minted = ("def check(state, final_answer):\n"
              "    return (state['kv'].get('budget') == '80', 'ZZ_AMAZING_NEW_FAILURE')\n")
    r3 = evaluate_case(make_case("bucket_minter", minted), naive_agent(), corpus)
    show(r3, "bucket_minter")
    say("The taxonomy is a closed, versioned prefix table. Unknown prefixes bill into")
    say(f"UNCLASSIFIED at x{params['unclassified_novelty_penalty']} novelty. Minting is bounded, not free.")

    # ------------------------------------------------------------------ 4
    banner(4, "Spam lane: unsolvable cases and malicious checkers")
    unsolvable = make_case("impossible_spam", (
        "def check(state, final_answer):\n    return (False, 'SD_READ_NEVER_PASSES')\n"))
    r4a = evaluate_case(unsolvable, naive_agent(), corpus)
    show(r4a, "impossible_spam (no valid solution)")
    malicious = make_case("sandbox_probe", (
        "import os\ndef check(s, f):\n    os.system('echo pwned')\n    return (True, 'x')\n"))
    r4b = evaluate_case(malicious, naive_agent(), corpus)
    show(r4b, "sandbox_probe (import os)")
    say("'Impossible task' spam is structurally worthless; imports die in the sandbox.")

    # ------------------------------------------------------------------ 5
    banner(5, "Rolling target registry: difficulty is a measured tier gap")
    registry = load_registry()
    weights = target_weights(registry)
    say("targets.json, tiers ranked by MEASURED pass rate (never parameter count):")
    for t in registry["targets"]:
        say(f"  {t['tier_id']:<14} pass_rate={t['measured_pass_rate']:<6} "
            f"status={t['status']:<10} weight={weights.get(t['tier_id'], 0.0):.3f}")
    targets = [
        {"tier_id": "strong-tier", "backend": competent_agent(), "weight": weights["qwen2.5-1.5b"]},
        {"tier_id": "mid-tier", "backend": naive_agent(), "weight": weights["smollm2-360m"]},
        {"tier_id": "weak-tier", "backend": naive_agent(), "weight": weights["qwen2.5-0.5b"]},
    ]
    r5 = evaluate_case(make_case("tier_gap_case", CHECKER), seen_signatures={}, targets=targets)
    show(r5, "tier_gap_case (weak+mid fail, strong passes)")
    say(f"target_results = {r5['target_results']}")
    say("Failing only older tiers earns a fraction; chase the newest model to earn full")
    say("difficulty. New tiers enter 'active', age to 'deprecated' (x0.5), then 'retired'.")
    say("No retroactive rescoring: paid emission stays paid.")

    # ------------------------------------------------------------------ 6
    banner(6, "Governance: timelocked parameters + phase-2 milestone")
    doc = {"versions": [
        {"version": 1, "announced_at": "2026-07-01T00:00:00Z",
         "effective_from": "2026-07-01T00:00:00Z", "params": {"novelty_weight": 0.6}},
        {"version": 2, "announced_at": "2026-07-09T00:00:00Z",
         "effective_from": "2026-07-09T00:00:00Z", "params": {"novelty_weight": 0.99}},
    ]}
    import tempfile, pathlib
    with tempfile.TemporaryDirectory() as td:
        p = pathlib.Path(td) / "params.json"
        p.write_text(json.dumps(doc))
        got, gmeta = load_scoring_params(p, now=datetime(2026, 7, 9, 12, tzinfo=timezone.utc))
    say("Owner tries to push novelty_weight 0.6 -> 0.99 effective the same day it's announced:")
    say(f"  active version = v{gmeta['version']}, novelty_weight = {got['novelty_weight']}")
    say("Validators VOID any version violating the 7-day timelock (a code constant).")
    say("'No surprise parameter changes' is enforced, not promised.")
    print()
    say("Phase-2 (LLM judge lane) entry is machine-checkable, pre-registered thresholds:")
    say(f"  {PHASE2_THRESHOLDS}")
    check = phase2_ready(corpus)
    say(f"  current corpus -> ready={check['ready']} "
        f"(categories qualified: {check['categories_qualified']}/{check['thresholds']['min_categories']})")

    print()
    print("=" * W)
    print("Every gate, penalty and weight above: deterministic code, no human, no LLM judge.")
    print("Reproduce: python demo_showcase.py | python -m pytest -q | python -m faultline.milestones")
    print("=" * W)

if __name__ == "__main__":
    main()
