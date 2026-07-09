"""Compare coarse and fine signature clustering against generator template labels."""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
from collections import Counter, defaultdict

from faultline.verify import coarse_failure_signature, fine_failure_signature, failure_category


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="generated_cases/day1_45")
    p.add_argument(
        "--run",
        action="append",
        default=[
            "evidence/generated_runs/day1_45_e7c08c5_qwen_0p5_1p5",
            "evidence/generated_runs/day1_45_e7c08c5_smollm360",
        ],
        help="Run directory containing summary.csv and traces/<model>/*.json.",
    )
    p.add_argument("--out", default="evidence/signature_clustering/day1_45_e7c08c5")
    return p.parse_args()


def load_cases(case_dir: pathlib.Path) -> dict[str, dict]:
    cases = {}
    for path in sorted(case_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        case = json.loads(path.read_text())
        cases[case["case_id"]] = case
    return cases


def simple_cluster_metrics(rows: list[dict], signature_key: str) -> dict:
    valid = [r for r in rows if r.get(signature_key)]
    if not valid:
        return {"n": 0, "homogeneity": 1.0, "completeness": 1.0}

    by_signature: dict[str, Counter] = defaultdict(Counter)
    by_template: dict[str, Counter] = defaultdict(Counter)
    for row in valid:
        sig = row[signature_key]
        template = row["template"]
        by_signature[sig][template] += 1
        by_template[template][sig] += 1

    # Purity-style homogeneity: one signature should not mix templates.
    homogeneous = sum(max(counts.values()) for counts in by_signature.values()) / len(valid)
    # Template completeness: one template should not split across many signatures.
    complete = sum(max(counts.values()) for counts in by_template.values()) / len(valid)
    mixed = {
        sig: dict(counts)
        for sig, counts in by_signature.items()
        if len(counts) > 1
    }
    split_templates = {
        template: dict(counts)
        for template, counts in by_template.items()
        if len(counts) > 1
    }
    return {
        "n": len(valid),
        "homogeneity": round(homogeneous, 4),
        "completeness": round(complete, 4),
        "clusters": len(by_signature),
        "mixed_signature_count": len(mixed),
        "split_template_count": len(split_templates),
        "mixed_signatures": mixed,
        "split_templates": split_templates,
    }


def load_rows(cases: dict[str, dict], run_dirs: list[pathlib.Path]) -> list[dict]:
    rows = []
    for run_dir in run_dirs:
        with (run_dir / "summary.csv").open() as f:
            for row in csv.DictReader(f):
                if row["gate"] != "VALID":
                    continue
                case = cases[row["case_id"]]
                trace_path = run_dir / "traces" / row["model"] / f"{row['case_id']}.json"
                trace = json.loads(trace_path.read_text())
                assertion_id = row["assertion_id"]
                rows.append({
                    "model": row["model"],
                    "case_id": row["case_id"],
                    "template": case.get("generator", {}).get("template", "-"),
                    "assertion_id": assertion_id,
                    "failure_category": failure_category(case, assertion_id),
                    "coarse_signature": coarse_failure_signature(case, assertion_id),
                    "fine_signature": fine_failure_signature(case, trace, assertion_id),
                    "old_summary_signature": row.get("signature", ""),
                })
    return rows


def write_report(out: pathlib.Path, metrics: dict, rows: list[dict]) -> None:
    lines = [
        "# Signature Clustering Report",
        "",
        "Ground truth label: generator template.",
        "",
        "| model | mode | n | clusters | homogeneity | completeness | split templates | mixed signatures |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for model in sorted(metrics):
        for mode in ["fine_signature", "coarse_signature"]:
            m = metrics[model][mode]
            lines.append(
                f"| {model} | {mode.replace('_signature', '')} | {m['n']} | {m['clusters']} | "
                f"{m['homogeneity']} | {m['completeness']} | "
                f"{m['split_template_count']} | {m['mixed_signature_count']} |"
            )

    lines.extend([
        "",
        "Key observed repair:",
        "",
        "- `qwen1p5` `state_read_before_write` had four VALID examples split across four fine signatures in the old path-sensitive scheme.",
        "- The coarse signature maps those same examples to one billing cluster, so natural path variance no longer resets novelty.",
        "",
        "Note: fine signatures remain useful for exact dedupe and trace diagnostics; coarse signatures are used for novelty billing.",
        "",
    ])
    out.joinpath("report.md").write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = load_cases(pathlib.Path(args.cases))
    rows = load_rows(cases, [pathlib.Path(p) for p in args.run])

    metrics = {}
    for model in sorted({r["model"] for r in rows}):
        model_rows = [r for r in rows if r["model"] == model]
        metrics[model] = {
            "fine_signature": simple_cluster_metrics(model_rows, "fine_signature"),
            "coarse_signature": simple_cluster_metrics(model_rows, "coarse_signature"),
        }

    out.joinpath("metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    out.joinpath("rows.jsonl").write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    with out.joinpath("rows.csv").open("w", newline="") as f:
        fieldnames = [
            "model", "case_id", "template", "assertion_id", "failure_category",
            "coarse_signature", "fine_signature", "old_summary_signature",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    write_report(out, metrics, rows)
    print(json.dumps(metrics, indent=2, sort_keys=True))
    print(f"REPORT {out / 'report.md'}")


if __name__ == "__main__":
    main()
