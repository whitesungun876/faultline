"""Generate a deterministic FaultLine case bundle and self-check references."""
from __future__ import annotations

import argparse
import json
import pathlib
from collections import Counter

from faultline.casegen import generate_cases
from faultline.harness import run_reference
from faultline.verify import run_checker, validate_schema


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="generated_cases/day1_45")
    p.add_argument("--count", type=int, default=45)
    p.add_argument("--seed", type=int, default=20260709)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    cases = generate_cases(total=args.count, seed=args.seed)
    template_counts = Counter()
    for case in cases:
        obj = case.to_json_obj()
        ok, msg = validate_schema(obj)
        if not ok:
            raise RuntimeError(f"{case.case_id} schema failed: {msg}")
        state, answer = run_reference(obj["reference"])
        ref_ok, assertion_id = run_checker(obj, state, answer)
        if not ref_ok:
            raise RuntimeError(f"{case.case_id} reference failed: {assertion_id}")
        template_counts[obj["generator"]["template"]] += 1
        (out / f"{case.case_id}.json").write_text(
            json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
        )

    manifest = {
        "count": len(cases),
        "seed": args.seed,
        "templates": dict(sorted(template_counts.items())),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
