"""Offline weight sweep: replay the archived case x model matrix under candidate
(difficulty_weight, novelty_weight) combos BEFORE changing them on-chain.

Questions it answers, per the beta-parameter discipline:
- How do mining-strategy revenue rankings shift across weight combos?
  (strategy = generator template; each is a distinct way to farm the subnet)
- Do degenerate incentives appear at some combo?
    * novelty-carried: low-difficulty cases scoring in the top quartile
    * difficulty-farmed: duplicate-fingerprint (re-skin) cases still scoring high

Novelty depends on submission ORDER, so every combo is evaluated over many
seeded shuffles and reported as a mean -- single-order conclusions are noise.

Run: python run_weight_sweep.py
"""
import json
import pathlib
import random
from collections import defaultdict

from .registry import load_registry, target_weights
from .verify import (UNCLASSIFIED, checker_fingerprint, failure_category,
                     load_scoring_params)

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

DEFAULT_RUNS = [
    ("evidence/generated_runs/day1_45_e7c08c5_qwen_0p5_1p5/summary.jsonl",
     {"qwen0p5": "qwen2.5-0.5b", "qwen1p5": "qwen2.5-1.5b"}),
    ("evidence/generated_runs/day1_45_e7c08c5_smollm360/summary.jsonl",
     {"smollm360": "smollm2-360m"}),
]
DEFAULT_COMBOS = [(0.3, 0.7), (0.4, 0.6), (0.5, 0.5), (0.6, 0.4)]
BASELINE = (0.4, 0.6)

def load_matrix(case_dir="generated_cases/day1_45", runs=None, root=None):
    """Fold archived per-model runs into one record per case:
    {case_id, template, category, fingerprint, failed_tiers}."""
    root = pathlib.Path(root) if root else _REPO_ROOT
    runs = runs if runs is not None else DEFAULT_RUNS
    cases = {}
    for path in sorted((root / case_dir).glob("*.json")):
        if path.name == "manifest.json":
            continue
        case = json.loads(path.read_text())
        cases[case["case_id"]] = {
            "case_id": case["case_id"],
            "template": case.get("generator", {}).get("template", "-"),
            "fingerprint": checker_fingerprint(case["checker_src"], case),
            "category": None,
            "failed_tiers": set(),
        }
    for rel, tier_map in runs:
        for line in (root / rel).read_text().splitlines():
            row = json.loads(line)
            rec = cases.get(row["case_id"])
            if rec is None:
                continue
            if row["gate"] == "VALID":
                rec["failed_tiers"].add(tier_map[row["model"]])
                rec["category"] = rec["category"] or failure_category({}, row["assertion_id"])
    return [rec for rec in cases.values() if rec["failed_tiers"]]

def score_order(records, order, weights, tier_weights, params):
    """Deterministically score one submission order under one weight combo.
    Mirrors evaluate_case pricing: category-count decay, duplicate-fingerprint
    and unclassified penalties, difficulty = failed tier weight share."""
    dw, nw = weights
    seen_count, seen_fp = defaultdict(int), defaultdict(set)
    out = {}
    for i in order:
        rec = records[i]
        cat = rec["category"] or UNCLASSIFIED
        novelty = 1.0 / ((seen_count[cat] + 1) ** 0.5)
        duplicate = rec["fingerprint"] in seen_fp[cat]
        if duplicate:
            novelty *= params["duplicate_fingerprint_penalty"]
        if cat == UNCLASSIFIED:
            novelty *= params["unclassified_novelty_penalty"]
        seen_count[cat] += 1
        seen_fp[cat].add(rec["fingerprint"])
        difficulty = sum(tier_weights.get(t, 0.0) for t in rec["failed_tiers"])
        out[rec["case_id"]] = {"score": dw * difficulty + nw * novelty,
                               "difficulty": difficulty, "novelty": novelty,
                               "duplicate": duplicate}
    return out

def kendall_tau(rank_a, rank_b):
    """Kendall rank correlation between two orderings of the same keys."""
    keys = list(rank_a)
    conc = disc = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a = rank_a[keys[i]] - rank_a[keys[j]]
            b = rank_b[keys[i]] - rank_b[keys[j]]
            if a * b > 0:
                conc += 1
            elif a * b < 0:
                disc += 1
    pairs = len(keys) * (len(keys) - 1) / 2
    return (conc - disc) / pairs if pairs else 1.0

def _strategy_ranking(revenue):
    ordered = sorted(revenue, key=lambda k: -revenue[k])
    return {k: i for i, k in enumerate(ordered)}

def run_sweep(records=None, combos=None, n_orders=20, params=None, tier_weights=None):
    records = records if records is not None else load_matrix()
    combos = combos or DEFAULT_COMBOS
    if params is None:
        params, _ = load_scoring_params()
    if tier_weights is None:
        tier_weights = target_weights(load_registry())

    idx = list(range(len(records)))
    results = {}
    for combo in combos:
        revenue = defaultdict(float)
        case_scores = defaultdict(list)
        for seed in range(n_orders):
            order = idx[:]
            random.Random(seed).shuffle(order)
            scored = score_order(records, order, combo, tier_weights, params)
            for rec in records:
                s = scored[rec["case_id"]]
                revenue[rec["template"]] += s["score"] / n_orders
                case_scores[rec["case_id"]].append(s)
        # per-case means for degeneracy flags
        case_stats = {}
        for cid, rows in case_scores.items():
            case_stats[cid] = {
                "mean_score": sum(r["score"] for r in rows) / len(rows),
                "difficulty": rows[0]["difficulty"],  # order-independent
                "duplicate_share": sum(r["duplicate"] for r in rows) / len(rows),
            }
        scores_sorted = sorted(s["mean_score"] for s in case_stats.values())
        q3 = scores_sorted[int(0.75 * (len(scores_sorted) - 1))]
        median = scores_sorted[len(scores_sorted) // 2]
        flags = {"novelty_carried": [], "difficulty_farmed": []}
        for cid, s in sorted(case_stats.items()):
            if s["difficulty"] <= 0.2 and s["mean_score"] >= q3:
                flags["novelty_carried"].append(cid)
            if s["duplicate_share"] >= 0.5 and s["mean_score"] >= median:
                flags["difficulty_farmed"].append(cid)
        results[combo] = {"strategy_revenue": dict(revenue),
                          "ranking": _strategy_ranking(revenue),
                          "flags": flags}

    base = results[BASELINE]["ranking"] if BASELINE in results else results[combos[0]]["ranking"]
    for combo, r in results.items():
        r["kendall_tau_vs_baseline"] = round(kendall_tau(base, r["ranking"]), 4)
    return {"n_cases": len(records), "n_orders": n_orders,
            "combos": {f"{d}/{n}": {
                "strategy_revenue": {k: round(v, 3) for k, v in
                                     sorted(r["strategy_revenue"].items(), key=lambda kv: -kv[1])},
                "kendall_tau_vs_baseline": r["kendall_tau_vs_baseline"],
                "flags": r["flags"],
            } for (d, n), r in results.items()}}
