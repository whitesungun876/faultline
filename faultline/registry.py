"""Rolling target registry (proposal 3.2, review point 2).

The registry pins measurement instruments (model checkpoint x harness commit x
toolbox) and gives each a scoring weight. Principles:

- Tier ordering is EMPIRICAL (measured pass rate on the pinned bundle), never
  parameter count -- see docs/proposal_3_1_revision.md (SmolLM2-360M beats
  Qwen2.5-0.5B 3x).
- Rolling window: new targets enter `active`, age to `deprecated` (weight
  halved), then `retired` (weight 0, kept as historical metadata). Failing a
  stronger target is worth more, so miners naturally chase the newest tier.
- No retroactive rescoring: emission already paid under an old registry stays
  paid; registry updates only shape FUTURE scores.
"""
import json
import pathlib

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY_PATH = _REPO_ROOT / "targets.json"

STATUS_MULTIPLIER = {"active": 1.0, "deprecated": 0.5, "retired": 0.0}

def load_registry(path=None):
    path = pathlib.Path(path) if path else REGISTRY_PATH
    return json.loads(path.read_text())

def target_weights(registry):
    """tier_id -> normalized weight.

    Live targets are ranked by measured pass rate ascending (harder-to-fail =
    higher rank = higher weight), then scaled by the status multiplier."""
    live = [t for t in registry["targets"]
            if STATUS_MULTIPLIER.get(t.get("status", "retired"), 0.0) > 0.0]
    ranked = sorted(live, key=lambda t: t["measured_pass_rate"])
    raw = {t["tier_id"]: (i + 1) * STATUS_MULTIPLIER[t["status"]]
           for i, t in enumerate(ranked)}
    total = sum(raw.values()) or 1.0
    return {tier: w / total for tier, w in raw.items()}

def build_targets(registry, backend_factory):
    """Materialize evaluate_case targets: [{"tier_id", "backend", "weight"}].
    backend_factory(target_entry) -> backend instance."""
    weights = target_weights(registry)
    return [{"tier_id": t["tier_id"], "backend": backend_factory(t),
             "weight": weights[t["tier_id"]]}
            for t in registry["targets"] if t["tier_id"] in weights]
