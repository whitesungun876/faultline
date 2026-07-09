"""Run a case directory against one or more HFBackend targets and save traces."""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import time
from collections import Counter

from faultline.harness import HFBackend, run_agent, run_reference
from faultline.verify import (
    coarse_failure_signature,
    failure_category,
    fine_failure_signature,
    run_checker,
    validate_schema,
)


def parse_model(spec: str) -> tuple[str, str]:
    if "=" not in spec:
        label = spec.rsplit("/", 1)[-1].replace(".", "_")
        return label, spec
    label, model_id = spec.split("=", 1)
    return label, model_id


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--cases", default="generated_cases/day1_45")
    p.add_argument("--out", default=None)
    p.add_argument("--device", default="mps")
    p.add_argument(
        "--model",
        action="append",
        required=True,
        help="Model spec as label=model_id_or_path. May be repeated.",
    )
    return p.parse_args()


def load_cases(case_dir: pathlib.Path) -> list[dict]:
    cases = []
    for p in sorted(case_dir.glob("*.json")):
        if p.name == "manifest.json":
            continue
        case = json.loads(p.read_text())
        case["_path"] = str(p)
        cases.append(case)
    return cases


def evaluate_one(case: dict, backend: HFBackend, seen_signatures: dict[str, int]) -> dict:
    ok, msg = validate_schema(case)
    if not ok:
        return {"gate": "SCHEMA_FAIL", "score": 0.0, "detail": msg, "trace": []}

    ref_state, ref_answer = run_reference(case["reference"])
    ref_ok, ref_assert = run_checker(case, ref_state, ref_answer)
    if ref_ok is None:
        return {"gate": "CHECKER_ERROR", "score": 0.0, "detail": ref_assert, "trace": []}
    if not ref_ok:
        return {
            "gate": "UNSOLVABLE",
            "score": 0.0,
            "detail": f"reference failed: {ref_assert}",
            "trace": [],
        }

    started = time.time()
    state, answer, trace = run_agent(backend, case["task_prompt"])
    elapsed = round(time.time() - started, 3)
    agent_ok, assertion_id = run_checker(case, state, answer)
    actions = Counter(step["action"] for step in trace)

    if agent_ok is None:
        return {
            "gate": "CHECKER_ERROR",
            "score": 0.0,
            "detail": assertion_id,
            "answer": answer,
            "elapsed_s": elapsed,
            "actions": dict(actions),
            "trace": trace,
        }
    if agent_ok:
        return {
            "gate": "AGENT_PASSED",
            "score": 0.0,
            "detail": "no failure reproduced",
            "assertion_id": assertion_id,
            "answer": answer,
            "elapsed_s": elapsed,
            "actions": dict(actions),
            "trace": trace,
        }

    sig = coarse_failure_signature(case, assertion_id)
    fine_sig = fine_failure_signature(case, trace, assertion_id)
    n = seen_signatures.get(sig, 0)
    novelty = 1.0 / ((n + 1) ** 0.5)
    seen_signatures[sig] = n + 1
    score = round(0.4 + 0.6 * novelty, 4)
    return {
        "gate": "VALID",
        "score": score,
        "assertion_id": assertion_id,
        "signature": sig,
        "coarse_signature": sig,
        "fine_signature": fine_sig,
        "failure_category": failure_category(case, assertion_id),
        "novelty": round(novelty, 4),
        "answer": answer,
        "elapsed_s": elapsed,
        "actions": dict(actions),
        "trace": trace,
    }


def main() -> None:
    args = parse_args()
    case_dir = pathlib.Path(args.cases)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    out = pathlib.Path(args.out or f"evidence/generated_runs/{case_dir.name}_{run_id}")
    out.mkdir(parents=True, exist_ok=True)

    cases = load_cases(case_dir)
    summary_rows = []
    for label, model_id in [parse_model(spec) for spec in args.model]:
        print(f"MODEL_START {label} {model_id}", flush=True)
        backend = HFBackend(model_id, device=args.device)
        seen_signatures: dict[str, int] = {}
        trace_dir = out / "traces" / label
        trace_dir.mkdir(parents=True, exist_ok=True)
        for case in cases:
            case_id = case["case_id"]
            print(f"CASE_START {label} {case_id}", flush=True)
            result = evaluate_one(case, backend, seen_signatures)
            trace = result.pop("trace")
            (trace_dir / f"{case_id}.json").write_text(json.dumps(trace, indent=2) + "\n")
            row = {
                "model": label,
                "case_id": case_id,
                "template": case.get("generator", {}).get("template", "-"),
                "tags": ",".join(case.get("tags", [])),
                **result,
            }
            summary_rows.append(row)
            print(
                "CASE_RESULT",
                label,
                case_id,
                row["gate"],
                row.get("assertion_id", row.get("detail", "-")),
                "score=",
                row.get("score"),
                "elapsed=",
                row.get("elapsed_s"),
                flush=True,
            )

    jsonl = out / "summary.jsonl"
    jsonl.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in summary_rows))
    csv_path = out / "summary.csv"
    fieldnames = sorted({key for row in summary_rows for key in row})
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"SUMMARY_JSONL {jsonl}")
    print(f"SUMMARY_CSV {csv_path}")


if __name__ == "__main__":
    main()
