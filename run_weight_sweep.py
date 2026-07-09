"""Offline weight sweep over the archived 45-case x 3-model matrix.
Writes evidence/weight_sweep/{results.json, report.md}. See faultline/sweep.py."""
import json
import pathlib

from faultline.sweep import run_sweep

OUT = pathlib.Path("evidence/weight_sweep")

def main():
    res = run_sweep()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(res, indent=2) + "\n")

    lines = ["# Weight Sweep Report", "",
             f"{res['n_cases']} valid cases x {res['n_orders']} seeded submission orders. "
             "Strategy = generator template; revenue = mean total score across orders.", "",
             "| combo (diff/nov) | Kendall tau vs 0.4/0.6 | novelty-carried | difficulty-farmed | top strategy |",
             "| --- | ---: | ---: | ---: | --- |"]
    for combo, r in res["combos"].items():
        top = next(iter(r["strategy_revenue"]))
        lines.append(f"| {combo} | {r['kendall_tau_vs_baseline']} | "
                     f"{len(r['flags']['novelty_carried'])} | "
                     f"{len(r['flags']['difficulty_farmed'])} | {top} |")
    lines += ["", "## Strategy revenue by combo", ""]
    for combo, r in res["combos"].items():
        lines.append(f"### {combo}")
        lines.append("")
        for k, v in r["strategy_revenue"].items():
            lines.append(f"- {k}: {v}")
        if r["flags"]["novelty_carried"] or r["flags"]["difficulty_farmed"]:
            lines.append(f"- flagged: novelty_carried={r['flags']['novelty_carried']}, "
                         f"difficulty_farmed={r['flags']['difficulty_farmed']}")
        lines.append("")
    (OUT / "report.md").write_text("\n".join(lines))
    print("\n".join(lines))
    print(f"\nWROTE {OUT}/results.json {OUT}/report.md")

if __name__ == "__main__":
    main()
