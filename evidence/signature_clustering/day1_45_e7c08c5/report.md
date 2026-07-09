# Signature Clustering Report

Ground truth label: generator template.

| model | mode | n | clusters | homogeneity | completeness | split templates | mixed signatures |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| qwen0p5 | fine | 43 | 14 | 1.0 | 0.8605 | 4 | 0 |
| qwen0p5 | coarse | 43 | 9 | 1.0 | 1.0 | 0 | 0 |
| qwen1p5 | fine | 29 | 14 | 1.0 | 0.7931 | 3 | 0 |
| qwen1p5 | coarse | 29 | 8 | 1.0 | 1.0 | 0 | 0 |
| smollm360 | fine | 39 | 10 | 1.0 | 0.9487 | 1 | 0 |
| smollm360 | coarse | 39 | 9 | 1.0 | 1.0 | 0 | 0 |

Key observed repair:

- `qwen1p5` `state_read_before_write` had four VALID examples split across four fine signatures in the old path-sensitive scheme.
- The coarse signature maps those same examples to one billing cluster, so natural path variance no longer resets novelty.

Note: fine signatures remain useful for exact dedupe and trace diagnostics; coarse signatures are used for novelty billing.
