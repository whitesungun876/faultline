"""Case schema, sandboxed checker execution, ValidityGate and novelty scoring.

A case is a JSON dict:
{
  "case_id": str,
  "task_prompt": str,
  "checker_src": str,        # python source defining: def check(state, final_answer) -> (bool, assertion_id)
  "reference": {"actions": [{"tool":..., "args":{...}}, ...], "final_answer": str},
  "claimed_failure": str     # miner's self-label (informational ONLY; never enters scoring)
}

Anti-manipulation design (proposal 3.2):
  Every input to the billing signature is validator-derived. The coarse signature
  is the taxonomy category, matched by fixed assertion prefixes -- a closed set,
  so miners cannot mint new novelty buckets with free-text strings (the old
  tags/claimed_failure fallbacks are gone). Cosmetic checker rewrites are caught
  by a behavioral fingerprint: the checker is executed against a fixed probe
  battery and the canonicalized verdict vector is hashed. Two checkers that
  "look different but behave the same" share a fingerprint, and resubmitting a
  known fingerprint takes a hard novelty penalty.

Known limitation: the probe battery is public, so a checker can Goodhart it by
special-casing probe states. Mitigation path: battery versioning plus private
probes derived from the corpus (see README, Known Limitations).

Day-1 sandbox debt (documented, acceptable on testnet only):
the checker runs in a subprocess with resource limits and a bare namespace,
NOT a container. Harden before mainnet.
"""
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

REQUIRED = ["case_id", "task_prompt", "checker_src", "reference"]

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Scoring parameters + governance (proposal 3.2, review point 4)
# ---------------------------------------------------------------------------
# Parameters live in scoring_params.json, versioned. A parameter version only
# activates if it was announced at least GOVERNANCE_TIMELOCK_SECONDS before its
# effective_from (version 1 = genesis, exempt). Versions violating the timelock
# are IGNORED by every validator: surprise parameter changes cannot take effect.
# The timelock length itself is a code constant, so shortening it requires a
# public repo diff, not a config edit.

GOVERNANCE_TIMELOCK_SECONDS = 7 * 24 * 3600
SCORING_PARAMS_PATH = _REPO_ROOT / "scoring_params.json"

DEFAULT_PARAMS = {
    "difficulty_weight": 0.4,
    "novelty_weight": 0.6,
    "novelty_decay": "inv_sqrt",            # novelty base = 1 / sqrt(n + 1)
    "unclassified_novelty_penalty": 0.5,    # assertion prefix outside taxonomy
    "duplicate_fingerprint_penalty": 0.25,  # known checker behavior resubmitted
    "ema_alpha": 0.2,
}

def _parse_ts(s):
    return datetime.fromisoformat(str(s).replace("Z", "+00:00"))

def load_scoring_params(path=None, now=None):
    """Return (params, meta). Falls back to DEFAULT_PARAMS if no file.
    Picks the highest version that is effective now AND respected the timelock."""
    path = pathlib.Path(path) if path else SCORING_PARAMS_PATH
    if not path.exists():
        return dict(DEFAULT_PARAMS), {"version": 0, "source": "defaults"}
    doc = json.loads(path.read_text())
    now = now or datetime.now(timezone.utc)
    active = None
    for v in sorted(doc.get("versions", []), key=lambda v: v["version"]):
        eff = _parse_ts(v["effective_from"])
        if eff > now:
            continue
        if v["version"] > 1:
            ann = _parse_ts(v["announced_at"])
            if (eff - ann).total_seconds() < GOVERNANCE_TIMELOCK_SECONDS:
                continue  # timelock violated -> version void
        active = v
    params = dict(DEFAULT_PARAMS)
    if active:
        params.update(active["params"])
    meta = {"version": active["version"] if active else 0,
            "evidence": (active or {}).get("evidence", ""),
            "source": str(path) if active else "defaults"}
    return params, meta

# ---------------------------------------------------------------------------
# Failure taxonomy (closed set; extending it is a governed change)
# ---------------------------------------------------------------------------

TAXONOMY_VERSION = 2

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
    ("KN_PRIOR_", "knowledge.memorized_prior"),
    ("TM_ARGS_", "tool.bad_arguments"),
    ("TM_CHOICE_", "tool.wrong_tool"),
    ("TM_NOOP_", "tool.missing_call"),
    ("PL_ORDER_", "planning.step_order"),
    ("PL_GOAL_", "planning.goal_drift"),
    ("PL_LOOP_", "planning.redundant_loop"),
    ("CX_FORGET_", "context.instruction_loss"),
    ("CX_OBS_", "context.observation_ignored"),
]

UNCLASSIFIED = "UNCLASSIFIED"

# ---------------------------------------------------------------------------
# Checker sandbox (batch: one subprocess evaluates many probes)
# ---------------------------------------------------------------------------

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
results = []
for probe in payload["probes"]:
    try:
        ok, assertion_id = ns["check"](probe["state"], probe["final_answer"])
        results.append({"ok": bool(ok), "assertion_id": str(assertion_id)})
    except Exception as e:
        results.append({"error": str(e)[:200]})
print(json.dumps(results))
"""

def validate_schema(case):
    missing = [k for k in REQUIRED if k not in case]
    if missing:
        return False, f"missing fields: {missing}"
    if len(case["checker_src"]) > 8000 or len(case["task_prompt"]) > 4000:
        return False, "size limits exceeded"
    return True, "ok"

def _run_checker_probes(checker_src, probes, timeout=15):
    """Run the checker against a list of {'state','final_answer'} probes in ONE
    sandboxed subprocess. Returns list of {'ok','assertion_id'}|{'error'} or None."""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(_CHECKER_RUNNER)
        runner = f.name
    payload = json.dumps({"checker_src": checker_src, "probes": probes})
    try:
        p = subprocess.run([sys.executable, "-I", runner], input=payload,
                           capture_output=True, text=True, timeout=timeout)
        if p.returncode != 0:
            return None
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (subprocess.TimeoutExpired, json.JSONDecodeError, IndexError):
        return None

def run_checker(case, state, final_answer, timeout=10):
    """Execute miner checker on one state. Returns (ok, assertion_id) or (None, error)."""
    results = _run_checker_probes(case["checker_src"],
                                  [{"state": state, "final_answer": final_answer}],
                                  timeout=timeout)
    if results is None:
        return None, "checker error: exec failed or timeout"
    out = results[0]
    if "error" in out:
        return None, f"checker error: {out['error']}"
    return out["ok"], out["assertion_id"]

# ---------------------------------------------------------------------------
# Behavioral fingerprint (proposal 3.2, review point 1)
# ---------------------------------------------------------------------------

PROBE_BATTERY_VERSION = 1

def probe_battery():
    """Fixed, versioned probe set. Deterministic and shared across cases so
    fingerprints are comparable. Extend only with a version bump."""
    return [
        {"state": {"kv": {}, "files": {}}, "final_answer": ""},
        {"state": {"kv": {}, "files": {}}, "final_answer": "done"},
        {"state": {"kv": {}, "files": {}}, "final_answer": "I have completed the task."},
        {"state": {"kv": {"budget": "80"}, "files": {}}, "final_answer": "80"},
        {"state": {"kv": {"budget": "0"}, "files": {}}, "final_answer": "0"},
        {"state": {"kv": {"budget": "100"}, "files": {}}, "final_answer": "100"},
        {"state": {"kv": {"budget": "80", "count": "7"}, "files": {}}, "final_answer": "7"},
        {"state": {"kv": {"a": "1", "b": "2"}, "files": {}}, "final_answer": "3"},
        {"state": {"kv": {}, "files": {"log.txt": "alpha\nbeta\n"}}, "final_answer": "alpha"},
        {"state": {"kv": {}, "files": {"log.txt": "gamma\nalpha\nbeta\n"}}, "final_answer": "2"},
        {"state": {"kv": {"final_amount": "1389.15", "gain": "189.15"}, "files": {}}, "final_answer": "1389.15"},
        {"state": {"kv": {"zeds": "15.54"}, "files": {"notes.txt": "x"}}, "final_answer": "15.54"},
    ]

_FINGERPRINT_CACHE = {}

def checker_fingerprint(checker_src, timeout=15):
    """Validator-derived behavioral identity of a checker.

    The checker runs against the probe battery; the verdict vector is
    canonicalized (PASS -> 'P', error -> 'E', each distinct assertion string
    -> 'A0','A1',... by first appearance) and hashed. Assertion STRINGS are
    erased by the canonicalization, so renaming them cannot mint a new
    fingerprint -- only behaviorally different checkers differ. Returns a hex
    digest, or None if the checker source fails to execute.
    """
    key = hashlib.sha256(checker_src.encode()).hexdigest()
    if key in _FINGERPRINT_CACHE:
        return _FINGERPRINT_CACHE[key]
    verdicts = _run_checker_probes(checker_src, probe_battery(), timeout=timeout)
    if verdicts is None:
        return None
    labels, tokens = {}, []
    for v in verdicts:
        if "error" in v:
            tokens.append("E")
        elif v["ok"]:
            tokens.append("P")
        else:
            aid = v["assertion_id"]
            labels.setdefault(aid, f"A{len(labels)}")
            tokens.append(labels[aid])
    fp = _hash_signature(f"probes_v{PROBE_BATTERY_VERSION}|" + ",".join(tokens))
    _FINGERPRINT_CACHE[key] = fp
    return fp

# ---------------------------------------------------------------------------
# Signatures
# ---------------------------------------------------------------------------

def _hash_signature(raw):
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def failure_category(case, assertion_id):
    """Taxonomy bucket from the fixed prefix table ONLY.

    No fallback to miner-supplied tags/claimed_failure: those were free-text
    novelty mints. Unrecognized prefixes go to UNCLASSIFIED (novelty-penalized),
    so the set of billable categories is closed and governed."""
    assertion_id = str(assertion_id)
    for prefix, category in _ASSERTION_TAXONOMY:
        if assertion_id.startswith(prefix):
            return category
    return UNCLASSIFIED

def coarse_failure_signature(case, assertion_id):
    """Novelty billing signature: the taxonomy category, nothing else.

    Path-sensitive features are excluded so agent path variance cannot reset
    novelty; the raw assertion string is excluded so miners cannot mint
    buckets. Re-skins of the same failure class decay together."""
    return _hash_signature(f"tax_v{TAXONOMY_VERSION}|{failure_category(case, assertion_id)}")

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

# ---------------------------------------------------------------------------
# Corpus records
# ---------------------------------------------------------------------------

def _corpus_record(existing, category):
    """Normalize a corpus entry to the v2 record shape (legacy ints upgraded)."""
    if isinstance(existing, dict):
        return existing
    rec = {"count": 0, "category": category, "fingerprints": [],
           "fine_sigs": [], "tiers_failed": []}
    if isinstance(existing, int):
        rec["count"] = existing
    return rec

# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_case(case, backend=None, seen_signatures=None, targets=None, params=None):
    """Full validity gate + score. Returns dict with score in [0,1] and diagnostics.

    seen_signatures: dict signature -> record (the corpus index; persist as JSON).
    targets: optional rolling registry, list of {"tier_id", "backend", "weight"}
             (see faultline.registry). If omitted, `backend` is used as a single
             target with weight 1.0 -- the single-target MVP behavior.
    params: scoring parameters; defaults to load_scoring_params().
    """
    from .harness import run_agent

    if seen_signatures is None:
        seen_signatures = {}
    if params is None:
        params, _ = load_scoring_params()
    if targets is None:
        targets = [{"tier_id": "default", "backend": backend, "weight": 1.0}]

    ok, msg = validate_schema(case)
    if not ok:
        return {"score": 0.0, "gate": "SCHEMA_FAIL", "detail": msg}

    # Gate 1: solvability -- reference solution must PASS the checker.
    from .harness import run_reference
    ref_state, ref_answer = run_reference(case["reference"])
    ref_ok, ref_assert = run_checker(case, ref_state, ref_answer)
    if ref_ok is None:
        return {"score": 0.0, "gate": "CHECKER_ERROR", "detail": ref_assert}
    if not ref_ok:
        return {"score": 0.0, "gate": "UNSOLVABLE", "detail": f"reference failed: {ref_assert}"}

    # Behavioral fingerprint (validator-derived; cosmetic rewrites collapse here).
    fingerprint = checker_fingerprint(case["checker_src"])
    if fingerprint is None:
        return {"score": 0.0, "gate": "CHECKER_ERROR", "detail": "fingerprint probes failed"}

    # Gate 2: pinned target(s) must FAIL (independent replay, deterministic backend).
    total_weight = sum(t["weight"] for t in targets) or 1.0
    failed, target_results = [], {}
    assertion_id, best_trace = None, []
    for t in sorted(targets, key=lambda t: -t["weight"]):
        state, answer, trace = run_agent(t["backend"], case["task_prompt"])
        agent_ok, aid = run_checker(case, state, answer)
        if agent_ok is None:
            return {"score": 0.0, "gate": "CHECKER_ERROR", "detail": aid}
        target_results[t["tier_id"]] = "PASS" if agent_ok else "FAIL"
        if not agent_ok:
            if not failed:  # highest-weight failing target defines the diagnosis
                assertion_id, best_trace = aid, trace
            failed.append(t)
    if not failed:
        return {"score": 0.0, "gate": "AGENT_PASSED",
                "detail": "no failure reproduced on any registry target",
                "target_results": target_results}

    # Difficulty: weighted fraction of registry targets that fail (rolling window).
    difficulty = sum(t["weight"] for t in failed) / total_weight

    # Novelty: category-count decay 1/sqrt(n+1); duplicate-fingerprint and
    # unclassified penalties are multiplicative.
    category = failure_category(case, assertion_id)
    sig = coarse_failure_signature(case, assertion_id)
    fine_sig = fine_failure_signature(case, best_trace, assertion_id)

    rec = _corpus_record(seen_signatures.get(sig), category)
    novelty = 1.0 / ((rec["count"] + 1) ** 0.5)
    duplicate = fingerprint in rec["fingerprints"]
    if duplicate:
        novelty *= params["duplicate_fingerprint_penalty"]
    if category == UNCLASSIFIED:
        novelty *= params["unclassified_novelty_penalty"]

    rec["count"] += 1
    rec["category"] = category
    if fingerprint not in rec["fingerprints"]:
        rec["fingerprints"].append(fingerprint)
    if fine_sig not in rec["fine_sigs"]:
        rec["fine_sigs"].append(fine_sig)
    for t in failed:
        if t["tier_id"] not in rec["tiers_failed"]:
            rec["tiers_failed"].append(t["tier_id"])
    seen_signatures[sig] = rec

    score = params["difficulty_weight"] * difficulty + params["novelty_weight"] * novelty
    return {"score": round(score, 4), "gate": "VALID", "signature": sig,
            "coarse_signature": sig, "fine_signature": fine_sig,
            "fingerprint": fingerprint, "duplicate_fingerprint": duplicate,
            "failure_category": category, "assertion_id": assertion_id,
            "novelty": round(novelty, 4), "difficulty": round(difficulty, 4),
            "target_results": target_results, "trace_len": len(best_trace)}
