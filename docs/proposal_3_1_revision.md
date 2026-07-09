# Proposal 3.1 Revision Notes

## Target Registry Ordering Must Be Empirical

The generated 45-case matrix shows that model size is not a reliable proxy for
target difficulty across model families:

| model | parameters | pass rate |
| --- | ---: | ---: |
| Qwen2.5-0.5B-Instruct | 0.5B | 4.4% |
| SmolLM2-360M-Instruct | 0.36B | 13.3% |
| Qwen2.5-1.5B-Instruct | 1.5B | 35.6% |

SmolLM2-360M is smaller than Qwen2.5-0.5B but passed roughly three times as many
cases. Therefore registry tiers must be ordered by measured pass rate on the
current benchmark bundle, not by parameter count or model family. Otherwise a
tier-gap difficulty formula can produce inverted or negative difficulty when
cross-family models violate the size-performance assumption.

Revision: define target tiers as empirical performance ranks over a pinned case
bundle and harness commit. Parameter count may be recorded as metadata, but it
must not drive tier ordering.

## Novelty Signature Split

The first path-sensitive signature used `(assertion_id, step bucket, last-3
actions)` for both billing and duplicate diagnostics. Real model traces showed
that semantically identical failures can split across multiple signatures due to
natural path variance. This creates accidental novelty inflation.

Revision: use two signatures:

- Coarse billing signature: `failure_category + assertion_id`
- Fine diagnostic signature: `assertion_id + step bucket + last-3 actions`

The coarse signature drives novelty decay. The fine signature remains available
for exact duplicate detection and trace-level debugging.
