"""Local bundle scoring helpers shared by tests and validator dry-runs."""
from __future__ import annotations

import json
import pathlib
from collections.abc import Callable

from .harness import ScriptedBackend
from .verify import evaluate_case


def load_case_bundle(case_dir: str | pathlib.Path) -> list[dict]:
    root = pathlib.Path(case_dir)
    cases = []
    for path in sorted(root.glob("*.json")):
        if path.name == "manifest.json":
            continue
        case = json.loads(path.read_text())
        case["_path"] = str(path)
        cases.append(case)
    return cases


def score_bundle(
    case_dir: str | pathlib.Path,
    corpus: dict[str, int] | None = None,
    backend_factory: Callable[[], object] | None = None,
) -> list[dict]:
    """Score every case in a directory, mutating the supplied corpus index."""
    if corpus is None:
        corpus = {}
    if backend_factory is None:
        backend_factory = lambda: ScriptedBackend(['{"finish": "done"}'])

    rows = []
    for case in load_case_bundle(case_dir):
        result = evaluate_case(case, backend_factory(), corpus)
        rows.append({
            "case_id": case["case_id"],
            "template": case.get("generator", {}).get("template", "-"),
            **result,
        })
    return rows
