"""Scoring telemetry: an append-only JSONL ledger of every evaluation, plus a
per-category report used to decide WHEN the beta weights deserve revisiting.

Signals:
- avg difficulty / avg novelty per category (is one term dominating pricing?)
- submission volume vs DISTINCT fingerprints (volume up + fingerprints flat
  = the category is being farmed with re-skins -> over-mined flag)
- duplicate-fingerprint share

Any weight change this data motivates still ships through scoring_params.json
versioning + the 7-day timelock, citing this report as evidence.

Run: python -m faultline.telemetry [ledger.jsonl]
"""
import json
import pathlib
import sys
import time

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_LEDGER = _REPO_ROOT / "telemetry_ledger.jsonl"

OVERMINED_MIN_VALID = 10
OVERMINED_DUP_SHARE = 0.5

def log_evaluation(case, result, path=None, now=None):
    """Append one evaluation outcome to the ledger. Never raises."""
    path = pathlib.Path(path) if path else DEFAULT_LEDGER
    row = {
        "ts": now if now is not None else time.time(),
        "case_id": case.get("case_id"),
        "gate": result.get("gate"),
        "score": result.get("score"),
        "novelty": result.get("novelty"),
        "difficulty": result.get("difficulty"),
        "category": result.get("failure_category"),
        "signature": result.get("signature"),
        "fingerprint": result.get("fingerprint"),
        "duplicate_fingerprint": result.get("duplicate_fingerprint"),
        "target_results": result.get("target_results"),
    }
    try:
        with path.open("a") as f:
            f.write(json.dumps(row) + "\n")
    except OSError:
        pass

def load_ledger(path=None):
    path = pathlib.Path(path) if path else DEFAULT_LEDGER
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]

def report(rows):
    """Per-category aggregates + over-mining flags from ledger rows."""
    cats = {}
    total = {"submissions": 0, "valid": 0}
    for r in rows:
        total["submissions"] += 1
        if r.get("gate") != "VALID":
            continue
        total["valid"] += 1
        c = cats.setdefault(r.get("category") or "?", {
            "valid": 0, "novelty_sum": 0.0, "difficulty_sum": 0.0,
            "fingerprints": set(), "duplicates": 0})
        c["valid"] += 1
        c["novelty_sum"] += r.get("novelty") or 0.0
        c["difficulty_sum"] += r.get("difficulty") or 0.0
        if r.get("fingerprint"):
            c["fingerprints"].add(r["fingerprint"])
        if r.get("duplicate_fingerprint"):
            c["duplicates"] += 1
    out = {}
    for cat, c in sorted(cats.items()):
        dup_share = c["duplicates"] / c["valid"]
        out[cat] = {
            "valid_submissions": c["valid"],
            "avg_novelty": round(c["novelty_sum"] / c["valid"], 4),
            "avg_difficulty": round(c["difficulty_sum"] / c["valid"], 4),
            "distinct_fingerprints": len(c["fingerprints"]),
            "duplicate_share": round(dup_share, 4),
            "overmined": bool(c["valid"] >= OVERMINED_MIN_VALID
                              and dup_share >= OVERMINED_DUP_SHARE),
        }
    return {"totals": total, "per_category": out,
            "overmined_categories": [k for k, v in out.items() if v["overmined"]]}

def _main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    print(json.dumps(report(load_ledger(path)), indent=2))

if __name__ == "__main__":
    _main()
