"""Case schema, sandboxed checker execution, ValidityGate and novelty scoring.

A case is a JSON dict:
{
  "case_id": str,
  "task_prompt": str,
  "checker_src": str,        # python source defining: def check(state, final_answer) -> (bool, assertion_id)
  "reference": {"actions": [{"tool":..., "args":{...}}, ...], "final_answer": str},
  "claimed_failure": str     # miner's self-labelled failure class (informational in MVP)
}

Day-1 sandbox debt (documented, acceptable on testnet only):
the checker runs in a subprocess with resource limits and a bare namespace,
NOT a container. Harden before mainnet.
"""
import hashlib
import json
import subprocess
import sys
import tempfile

REQUIRED = ["case_id", "task_prompt", "checker_src", "reference"]

_ASSERTION_TAXONOMY = [
    ("SD_READ_", "state.read_before_write"),
    ("SD_COND_", "state.conditional_write"),
    ("SD_PROTECT_", "state.overwrite_protection"),
    ("SD_SEQUENCE_", "state.sequence_dependency"),
    ("SD_ROLLBACK_", "state.rollback"),
    ("CH_LETTER_", "character.letter_count"),
    ("CH_SUBSTR_", "character.substring"),
    ("CH_FORMAT_", "character.format_extraction"),
    ("CH_COMPARE_", "character.fine_compare"),
]

_CHECKER_RUNNER = r"""
import json, sys, resource
resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
try:
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,) * 2)
except (ValueError, OSError):
    # Some macOS/Python builds expose RLIMIT_AS but reject changing it.
    # Keep the CPU timeout and isolated subprocess instead of failing every checker.
    pass
payload = json.load(sys.stdin)
ns = {"__builtins__": {"len": len, "str": str, "int": int, "float": float, "abs": abs,
                        "round": round, "sorted": sorted, "isinstance": isinstance,
                        "Exception": Exception, "ValueError": ValueError}}
exec(payload["checker_src"], ns)
ok, assertion_id = ns["check"](payload["state"], payload["final_answer"])
print(json.dumps({"ok": bool(ok), "assertion_id": str(assertion_id)}))
"""

def validate_schema(case):
    missing = [k for k in REQUIRED if k not in case]
    if missing:
        return False, f"missing fields: {missing}"
    if len(case["checker_src"]) > 8000 or len(case["task_prompt"]) > 4000:
        return False, "size limits exceeded"
    return True, "ok"

def run_checker(case, state, final_answer, timeout=10):
    """Execute miner checker in a subprocess sandbox. Returns (ok, assertion_id) or (None, error)."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(_CHECKER_RUNNER)
        runner = f.name
    payload = json.dumps({"checker_src": case["checker_src"],
                          "state": state, "final_answer": final_answer})
    try:
        p = subprocess.run([sys.executable, "-I", runner], input=payload,
                           capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            return None, f"checker error: {p.stderr[-300:]}"
        out = json.loads(p.stdout.strip().splitlines()[-1])
        return out["ok"], out["assertion_id"]
    except subprocess.TimeoutExpired:
        return None, "checker timeout"

def _hash_signature(raw):
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def failure_category(case, assertion_id):
    """Stable failure taxonomy bucket used by the coarse novelty signature."""
    assertion_id = str(assertion_id)
    for prefix, category in _ASSERTION_TAXONOMY:
        if assertion_id.startswith(prefix):
            return category
    tags = case.get("tags") or []
    if len(tags) >= 2:
        return ".".join(str(t) for t in tags[:2])
    if case.get("claimed_failure"):
        return str(case["claimed_failure"])
    return assertion_id.split("_", 1)[0]

def coarse_failure_signature(case, assertion_id):
    """Novelty billing signature: assertion plus semantic failure category.

    This intentionally ignores path-sensitive trace features so natural agent
    path variance cannot reset novelty for the same semantic failure.
    """
    category = failure_category(case, assertion_id)
    raw = f"{category}|{assertion_id}"
    return _hash_signature(raw)

def fine_failure_signature(case, trace, assertion_id):
    """Path-sensitive signature retained for exact dedupe and diagnostics."""
    actions = [t["action"] for t in trace]
    step_bucket = min(len(actions) // 4, 3)
    sketch = ",".join(actions[-3:])
    raw = f"{assertion_id}|{step_bucket}|{sketch}"
    return _hash_signature(raw)

def failure_signature(case, trace, assertion_id):
    """Backward-compatible alias for the novelty billing signature."""
    return coarse_failure_signature(case, assertion_id)

def evaluate_case(case, backend, seen_signatures):
    """Full validity gate + score. Returns dict with score in [0,1] and diagnostics.
    seen_signatures: dict signature -> count (the corpus index; persist as JSON)."""
    from .harness import run_agent, run_reference

    ok, msg = validate_schema(case)
    if not ok:
        return {"score": 0.0, "gate": "SCHEMA_FAIL", "detail": msg}

    # Gate 1: solvability — reference solution must PASS the checker.
    ref_state, ref_answer = run_reference(case["reference"])
    ref_ok, ref_assert = run_checker(case, ref_state, ref_answer)
    if ref_ok is None:
        return {"score": 0.0, "gate": "CHECKER_ERROR", "detail": ref_assert}
    if not ref_ok:
        return {"score": 0.0, "gate": "UNSOLVABLE", "detail": f"reference failed: {ref_assert}"}

    # Gate 2: target agent must FAIL (independent replay, deterministic backend).
    state, answer, trace = run_agent(backend, case["task_prompt"])
    agent_ok, assertion_id = run_checker(case, state, answer)
    if agent_ok is None:
        return {"score": 0.0, "gate": "CHECKER_ERROR", "detail": assertion_id}
    if agent_ok:
        return {"score": 0.0, "gate": "AGENT_PASSED", "detail": "no failure reproduced"}

    # Novelty: coarse cluster-count decay, 1/sqrt(n+1); first discovery gets full weight.
    sig = coarse_failure_signature(case, assertion_id)
    fine_sig = fine_failure_signature(case, trace, assertion_id)
    n = seen_signatures.get(sig, 0)
    novelty = 1.0 / ((n + 1) ** 0.5)
    seen_signatures[sig] = n + 1

    difficulty = 1.0  # single-target MVP; becomes tier-gap once registry has >1 target
    score = 0.4 * difficulty + 0.6 * novelty
    return {"score": round(score, 4), "gate": "VALID", "signature": sig,
            "coarse_signature": sig, "fine_signature": fine_sig,
            "failure_category": failure_category(case, assertion_id),
            "assertion_id": assertion_id, "novelty": round(novelty, 4),
            "trace_len": len(trace)}
