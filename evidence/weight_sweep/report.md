# Weight Sweep Report

45 valid cases x 20 seeded submission orders. Strategy = generator template; revenue = mean total score across orders.

| combo (diff/nov) | Kendall tau vs 0.4/0.6 | novelty-carried | difficulty-farmed | top strategy |
| --- | ---: | ---: | ---: | --- |
| 0.3/0.7 | 0.7222 | 0 | 0 | char_fine_compare |
| 0.4/0.6 | 1.0 | 0 | 0 | state_conditional_write |
| 0.5/0.5 | 0.7778 | 0 | 0 | char_fine_compare |
| 0.6/0.4 | 0.8333 | 0 | 0 | state_read_before_write |

## Strategy revenue by combo

### 0.3/0.7

- char_fine_compare: 3.612
- state_read_before_write: 3.612
- state_conditional_write: 3.612
- char_letter_count: 3.612
- state_sequence_dependency: 3.612
- char_substring_overlap: 3.462
- state_rollback: 3.362
- state_overwrite_protection: 3.062
- char_format_extract: 2.812

### 0.4/0.6

- state_conditional_write: 3.739
- state_read_before_write: 3.739
- state_sequence_dependency: 3.739
- char_fine_compare: 3.739
- char_letter_count: 3.739
- char_substring_overlap: 3.539
- state_rollback: 3.406
- state_overwrite_protection: 3.006
- char_format_extract: 2.672

### 0.5/0.5

- char_fine_compare: 3.866
- state_read_before_write: 3.866
- state_conditional_write: 3.866
- state_sequence_dependency: 3.866
- char_letter_count: 3.866
- char_substring_overlap: 3.616
- state_rollback: 3.449
- state_overwrite_protection: 2.949
- char_format_extract: 2.533

### 0.6/0.4

- state_read_before_write: 3.993
- char_fine_compare: 3.993
- state_conditional_write: 3.993
- state_sequence_dependency: 3.993
- char_letter_count: 3.993
- char_substring_overlap: 3.693
- state_rollback: 3.493
- state_overwrite_protection: 2.893
- char_format_extract: 2.393
