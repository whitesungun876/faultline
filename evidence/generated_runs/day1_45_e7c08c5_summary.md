# Day-1 Generated Case Matrix

Harness baseline commit: `e7c08c5`

Case bundle: `generated_cases/day1_45`

- 45 generated cases
- 9 templates, 5 reskins per template
- Coverage: state discipline and character-level perception

Novelty stress:

- Output: `evidence/novelty_stress/day1_45`
- Scripted repeated-failure backend produced 9 signatures for 45 cases.
- Each template clustered into exactly 1 signature of size 5.
- No mixed-template signatures were observed.
- Score decay per cluster matched `1/sqrt(n)`: 1.0, 0.8243, 0.7464, 0.7, 0.6683.

Model matrix:

| model | VALID | AGENT_PASSED | pass rate |
| --- | ---: | ---: | ---: |
| qwen0p5 | 43 | 2 | 0.044 |
| qwen1p5 | 29 | 16 | 0.356 |
| smollm360 | 39 | 6 | 0.133 |

Design implications:

- SmolLM2-360M passed 13.3% while Qwen2.5-0.5B passed 4.4%. A smaller non-Qwen model beat a larger Qwen model by roughly 3x, so target registry tiers must be ordered by measured pass rate, not parameter count.
- Path-sensitive novelty signatures are too brittle for billing. Real traces split semantic repeats: `qwen1p5` had `state_read_before_write` split into 4 fine signatures for 4 VALID examples.
- The revised two-level signature uses a coarse billing signature (`failure_category + assertion_id`) and retains the old path-sensitive signature as `fine_signature` for exact dedupe/diagnostics.

Signature clustering against generator template labels:

| model | mode | homogeneity | completeness |
| --- | --- | ---: | ---: |
| qwen0p5 | fine | 1.0 | 0.8605 |
| qwen0p5 | coarse | 1.0 | 1.0 |
| qwen1p5 | fine | 1.0 | 0.7931 |
| qwen1p5 | coarse | 1.0 | 1.0 |
| smollm360 | fine | 1.0 | 0.9487 |
| smollm360 | coarse | 1.0 | 1.0 |

Template pass counts:

| template | qwen0p5 | qwen1p5 | smollm360 |
| --- | ---: | ---: | ---: |
| char_fine_compare | 0/5 | 1/5 | 0/5 |
| char_format_extract | 0/5 | 5/5 | 2/5 |
| char_letter_count | 0/5 | 1/5 | 0/5 |
| char_substring_overlap | 0/5 | 2/5 | 0/5 |
| state_conditional_write | 0/5 | 1/5 | 0/5 |
| state_overwrite_protection | 2/5 | 4/5 | 0/5 |
| state_read_before_write | 0/5 | 1/5 | 0/5 |
| state_rollback | 0/5 | 0/5 | 4/5 |
| state_sequence_dependency | 0/5 | 1/5 | 0/5 |

Evidence paths:

- Qwen traces and summaries: `evidence/generated_runs/day1_45_e7c08c5_qwen_0p5_1p5`
- SmolLM2 traces and summaries: `evidence/generated_runs/day1_45_e7c08c5_smollm360`
- Signature clustering: `evidence/signature_clustering/day1_45_e7c08c5`
