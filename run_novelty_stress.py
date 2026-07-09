"""Stress-test novelty clustering with many same-template reskins."""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
from collections import Counter, defaultdict

from faultline.harness import ScriptedBackend
from faultline.verify import evaluate_case


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="generated_cases/day1_45")
    p.add_argument("--out", default="evidence/novelty_stress")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    case_dir = pathlib.Path(args.cases)
    out = pathlib.Path(args.out) / case_dir.name
    out.mkdir(parents=True, exist_ok=True)
    cases = [
        json.loads(p.read_text())
        for p in sorted(case_dir.glob("*.json"))
        if p.name != "manifest.json"
    ]

    corpus_index: dict[str, int] = {}
    rows = []
    cluster_templates: dict[str, set[str]] = defaultdict(set)
    for case in cases:
        result = evaluate_case(case, ScriptedBackend(['{"finish": "done"}']), corpus_index)
        row = {
            "case_id": case["case_id"],
            "template": case.get("generator", {}).get("template", "-"),
            "gate": result["gate"],
            "score": result.get("score"),
            "novelty": result.get("novelty"),
            "assertion_id": result.get("assertion_id"),
            "signature": result.get("signature"),
            "coarse_signature": result.get("coarse_signature"),
            "fine_signature": result.get("fine_signature"),
            "failure_category": result.get("failure_category"),
        }
        rows.append(row)
        if row["signature"]:
            cluster_templates[row["signature"]].add(row["template"])

    by_template = Counter(row["template"] for row in rows)
    by_signature = Counter(row["signature"] for row in rows if row["signature"])
    cluster_summary = {
        "cases": len(rows),
        "templates": dict(sorted(by_template.items())),
        "signatures": dict(sorted(by_signature.items())),
        "mixed_template_signatures": {
            sig: sorted(templates)
            for sig, templates in cluster_templates.items()
            if len(templates) > 1
        },
    }

    (out / "summary.json").write_text(json.dumps(cluster_summary, indent=2) + "\n")
    (out / "rows.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    with (out / "rows.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps(cluster_summary, indent=2))
    print(f"ROWS {out / 'rows.csv'}")


if __name__ == "__main__":
    main()
