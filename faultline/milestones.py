"""Phase-2 entry criteria (proposal 3.2, review point 3).

"Enough failure cases to start the Watchdog/Judge lane" is machine-checkable
from the corpus index, not a vibe. A category qualifies when it has enough
DISTINCT checker fingerprints (diversity, not raw trajectory count -- template
spam adds trajectories but not fingerprints) observed across enough registry
tiers (so phase 2 doesn't just learn one model's quirks). UNCLASSIFIED never
qualifies.

Run: python -m faultline.milestones
"""
import json
import pathlib

PHASE2_THRESHOLDS = {
    "min_categories": 8,
    "min_fingerprints_per_category": 20,
    "min_tiers_per_category": 2,
}

def phase2_ready(signatures, thresholds=None):
    """signatures: corpus index mapping coarse signature -> v2 record.
    Returns a checklist dict with per-category detail and overall readiness."""
    th = dict(PHASE2_THRESHOLDS)
    if thresholds:
        th.update(thresholds)

    by_cat = {}
    for rec in signatures.values():
        if not isinstance(rec, dict):
            continue  # legacy v1 count; carries no coverage metadata
        cat = rec.get("category", "UNCLASSIFIED")
        if cat == "UNCLASSIFIED":
            continue
        agg = by_cat.setdefault(cat, {"fingerprints": set(), "tiers": set(), "cases": 0})
        agg["fingerprints"].update(rec.get("fingerprints", []))
        agg["tiers"].update(rec.get("tiers_failed", []))
        agg["cases"] += rec.get("count", 0)

    qualified = {
        cat for cat, a in by_cat.items()
        if len(a["fingerprints"]) >= th["min_fingerprints_per_category"]
        and len(a["tiers"]) >= th["min_tiers_per_category"]
    }
    return {
        "ready": len(qualified) >= th["min_categories"],
        "categories_qualified": len(qualified),
        "categories_seen": len(by_cat),
        "thresholds": th,
        "per_category": {
            cat: {"fingerprints": len(a["fingerprints"]),
                  "tiers": sorted(a["tiers"]),
                  "cases": a["cases"],
                  "qualified": cat in qualified}
            for cat, a in sorted(by_cat.items())
        },
    }

def _main():
    corpus_path = pathlib.Path(__file__).resolve().parent.parent / "corpus_index.json"
    doc = json.loads(corpus_path.read_text()) if corpus_path.exists() else {}
    signatures = doc.get("signatures", doc)  # v2 doc or legacy flat map
    print(json.dumps(phase2_ready(signatures), indent=2))

if __name__ == "__main__":
    _main()
