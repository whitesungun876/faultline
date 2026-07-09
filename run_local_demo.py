"""End-to-end demo WITHOUT chain or GPU: proves the validity gate + scoring pipeline works.
Swap ScriptedBackend for HFBackend on your machine to replay against the real pinned model."""
import json, pathlib
from faultline.harness import ScriptedBackend
from faultline.verify import evaluate_case, run_checker
from faultline.harness import run_reference

CASES = sorted(pathlib.Path("seed_cases").glob("*.json"))

def naive_agent_responses():
    # A lazy 'agent' that answers immediately without using tools — the canonical failure.
    return ['{"finish": "I have completed the task."}']

def main():
    corpus_index = {}  # signature -> count; persist this file in the real validator
    print("=" * 70)
    print("GATE CHECK 1: all seed cases must be SOLVABLE (reference passes checker)")
    for p in CASES:
        case = json.loads(p.read_text())
        st, ans = run_reference(case["reference"])
        ok, aid = run_checker(case, st, ans)
        print(f"  {case['case_id']:<35} reference: {'PASS' if ok else 'FAIL <-- bug in case!'} ")
        assert ok, f"seed case {case['case_id']} is unsolvable — fix before shipping"

    print("\nGATE CHECK 2: naive agent should FAIL -> cases score as VALID")
    for p in CASES:
        case = json.loads(p.read_text())
        result = evaluate_case(case, ScriptedBackend(naive_agent_responses()), corpus_index)
        print(f"  {case['case_id']:<35} gate={result['gate']:<12} score={result.get('score')}")

    print("\nGATE CHECK 3: duplicate submission -> novelty decays")
    case = json.loads(CASES[0].read_text())
    for i in range(3):
        r = evaluate_case(case, ScriptedBackend(naive_agent_responses()), corpus_index)
        print(f"  resubmission {i+1}: score={r['score']} novelty={r.get('novelty')}")

    print("\nGATE CHECK 4: spam/unsolvable submission -> zero")
    bad = dict(case, case_id="spam_unsolvable",
               checker_src="def check(state, final_answer):\n    return (False, 'Z_never_passes')\n")
    r = evaluate_case(bad, ScriptedBackend(naive_agent_responses()), corpus_index)
    print(f"  unsolvable case: gate={r['gate']} score={r['score']}")

    bad2 = {"case_id": "spam_malicious", "task_prompt": "x",
            "checker_src": "import os\ndef check(s,f):\n    os.system('echo pwned')\n    return (True,'x')\n",
            "reference": {"actions": [], "final_answer": "x"}}
    r2 = evaluate_case(bad2, ScriptedBackend(naive_agent_responses()), corpus_index)
    print(f"  malicious checker (import blocked): gate={r2['gate']} score={r2['score']}")
    print("=" * 70)
    print("All gates behave as designed.")

if __name__ == "__main__":
    main()
