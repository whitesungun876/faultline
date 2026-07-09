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
