"""Deterministic case generator for state-discipline and character-level traps."""
from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class GeneratedCase:
    case_id: str
    task_prompt: str
    checker_src: str
    reference: dict
    claimed_failure: str
    tags: list[str]
    generator: dict

    def to_json_obj(self) -> dict:
        return {
            "case_id": self.case_id,
            "task_prompt": self.task_prompt,
            "checker_src": self.checker_src,
            "reference": self.reference,
            "claimed_failure": self.claimed_failure,
            "tags": self.tags,
            "generator": self.generator,
        }


WORDS = [
    "amber", "brisk", "cedar", "delta", "ember", "fjord", "glint", "harbor",
    "ivory", "juno", "kepler", "lumen", "mango", "nyx", "orbit", "prism",
    "quartz", "rivet", "solace", "tango", "umbra", "vesta", "willow", "xenon",
]


def _checker_kv_exact(key: str, expected: str, missing_id: str, wrong_final_id: str) -> str:
    return (
        "def check(state, final_answer):\n"
        f"    v = state['kv'].get({key!r})\n"
        f"    if v != {expected!r}: return (False, {missing_id!r})\n"
        f"    return (str(final_answer).strip() == {expected!r}, {wrong_final_id!r})\n"
    )


def _checker_file_exact(name: str, expected: str, assertion_id: str) -> str:
    return (
        "def check(state, final_answer):\n"
        f"    return (state['files'].get({name!r}) == {expected!r}, {assertion_id!r})\n"
    )


def _overlap_count(text: str, needle: str) -> int:
    if not needle:
        return 0
    return sum(1 for i in range(0, len(text) - len(needle) + 1) if text[i:i + len(needle)] == needle)


def _first_diff(a: str, b: str) -> int:
    for i, (left, right) in enumerate(zip(a, b), start=1):
        if left != right:
            return i
    return 0 if len(a) == len(b) else min(len(a), len(b)) + 1


def _case_id(template: str, idx: int) -> str:
    return f"gen_{template}_{idx:03d}"


def read_before_write(idx: int, rng: random.Random) -> GeneratedCase:
    key = f"{rng.choice(WORDS)}_budget"
    value = str(rng.randrange(18, 96, 7))
    threshold = int(value) + rng.randrange(8, 35)
    replacement = str(threshold + rng.randrange(10, 60))
    prompt = (
        f"First store value '{value}' under kv key '{key}'. Then read the current value. "
        f"Only if the current value is greater than {threshold}, overwrite it with "
        f"'{replacement}'. Otherwise leave it unchanged. Finish with the final value of '{key}'."
    )
    return GeneratedCase(
        case_id=_case_id("state_read_before_write", idx),
        task_prompt=prompt,
        checker_src=_checker_kv_exact(
            key, value, "SD_READ_STATE_CLOBBERED", "SD_READ_WRONG_FINAL"
        ),
        reference={
            "actions": [
                {"tool": "kv_set", "args": {"key": key, "value": value}},
                {"tool": "kv_get", "args": {"key": key}},
            ],
            "final_answer": value,
        },
        claimed_failure="read_before_write_skipped",
        tags=["state_discipline", "read_before_write"],
        generator={"template": "state_read_before_write", "variant": idx},
    )


def conditional_write(idx: int, rng: random.Random) -> GeneratedCase:
    key = f"{rng.choice(WORDS)}_score"
    value = str(rng.randrange(10, 50))
    threshold = int(value) + rng.randrange(3, 18)
    replacement = str(threshold * 2 + rng.randrange(1, 9))
    prompt = (
        f"Store '{value}' under kv key '{key}'. Read it back. If the current value is less "
        f"than {threshold}, replace it with '{replacement}'; otherwise keep it. Finish with "
        f"the final value."
    )
    return GeneratedCase(
        case_id=_case_id("state_conditional_write", idx),
        task_prompt=prompt,
        checker_src=_checker_kv_exact(
            key, replacement, "SD_COND_WRONG_VALUE", "SD_COND_WRONG_FINAL"
        ),
        reference={
            "actions": [
                {"tool": "kv_set", "args": {"key": key, "value": value}},
                {"tool": "kv_get", "args": {"key": key}},
                {"tool": "kv_set", "args": {"key": key, "value": replacement}},
            ],
            "final_answer": replacement,
        },
        claimed_failure="conditional_write_missed",
        tags=["state_discipline", "conditional_write"],
        generator={"template": "state_conditional_write", "variant": idx},
    )


def overwrite_protection(idx: int, rng: random.Random) -> GeneratedCase:
    key = f"{rng.choice(WORDS)}_lock"
    original = f"keep-{rng.randrange(20, 99)}"
    proposed = f"swap-{rng.randrange(100, 999)}"
    code = rng.choice(["deny", "hold", "red", "closed"])
    prompt = (
        f"Set kv key '{key}' to '{original}'. A proposed update wants to change it to "
        f"'{proposed}', but protected keys may be overwritten only when the guard code is "
        f"'allow'. The guard code here is '{code}', so preserve the original value. Finish "
        f"with the final value of '{key}'."
    )
    return GeneratedCase(
        case_id=_case_id("state_overwrite_protection", idx),
        task_prompt=prompt,
        checker_src=_checker_kv_exact(
            key, original, "SD_PROTECT_OVERWRITTEN", "SD_PROTECT_WRONG_FINAL"
        ),
        reference={
            "actions": [
                {"tool": "kv_set", "args": {"key": key, "value": original}},
                {"tool": "kv_get", "args": {"key": key}},
            ],
            "final_answer": original,
        },
        claimed_failure="overwrite_guard_ignored",
        tags=["state_discipline", "overwrite_protection"],
        generator={"template": "state_overwrite_protection", "variant": idx},
    )


def sequence_dependency(idx: int, rng: random.Random) -> GeneratedCase:
    name = f"{rng.choice(WORDS)}_log.txt"
    lines = rng.sample(WORDS, 4)
    alphabetical = ", ".join(sorted(lines))
    expected = "".join(f"{line}\n" for line in lines)
    prompt = (
        f"Create file '{name}' by appending exactly these lines in this order: "
        + " then ".join(f"'{line}\\n'" for line in lines)
        + f". Do not sort them; alphabetical order would be {alphabetical}. Finish with 'done'."
    )
    return GeneratedCase(
        case_id=_case_id("state_sequence_dependency", idx),
        task_prompt=prompt,
        checker_src=_checker_file_exact(name, expected, "SD_SEQUENCE_WRONG_ORDER"),
        reference={
            "actions": [
                {"tool": "file_append", "args": {"name": name, "content": f"{line}\n"}}
                for line in lines
            ],
            "final_answer": "done",
        },
        claimed_failure="sequence_reordered",
        tags=["state_discipline", "sequence_dependency"],
        generator={"template": "state_sequence_dependency", "variant": idx},
    )


def state_rollback(idx: int, rng: random.Random) -> GeneratedCase:
    key = f"{rng.choice(WORDS)}_quota"
    original = rng.randrange(30, 80)
    delta = rng.randrange(20, 50)
    cap = original + delta - rng.randrange(1, 12)
    prompt = (
        f"Store '{original}' under kv key '{key}'. Compute a trial value by adding {delta}. "
        f"If the trial value is greater than cap {cap}, roll back and keep '{original}'; "
        f"otherwise store the trial value. Finish with the final value of '{key}'."
    )
    return GeneratedCase(
        case_id=_case_id("state_rollback", idx),
        task_prompt=prompt,
        checker_src=_checker_kv_exact(
            key, str(original), "SD_ROLLBACK_NOT_RESTORED", "SD_ROLLBACK_WRONG_FINAL"
        ),
        reference={
            "actions": [
                {"tool": "kv_set", "args": {"key": key, "value": str(original)}},
                {"tool": "calc", "args": {"expression": f"{original} + {delta}"}},
                {"tool": "kv_set", "args": {"key": key, "value": str(original)}},
            ],
            "final_answer": str(original),
        },
        claimed_failure="rollback_state_lost",
        tags=["state_discipline", "state_rollback"],
        generator={"template": "state_rollback", "variant": idx},
    )


def letter_count(idx: int, rng: random.Random) -> GeneratedCase:
    target = rng.choice(["r", "t", "e", "a"])
    pieces = rng.sample(WORDS, 5)
    text = " ".join(pieces)
    expected = str(text.count(target))
    key = f"count_{target}_{idx}"
    prompt = (
        f"Count how many times the letter '{target}' appears in the exact string "
        f"'{text}'. Store the count under kv key '{key}' and finish with the number."
    )
    return GeneratedCase(
        case_id=_case_id("char_letter_count", idx),
        task_prompt=prompt,
        checker_src=_checker_kv_exact(
            key, expected, "CH_LETTER_WRONG_COUNT", "CH_LETTER_WRONG_FINAL"
        ),
        reference={"actions": [{"tool": "kv_set", "args": {"key": key, "value": expected}}],
                   "final_answer": expected},
        claimed_failure="character_count_wrong",
        tags=["character_level", "letter_count"],
        generator={"template": "char_letter_count", "variant": idx},
    )


def substring_count(idx: int, rng: random.Random) -> GeneratedCase:
    bases = [
        ("bananana", "ana"),
        ("aaaaa", "aa"),
        ("civicivic", "ivic"),
        ("levellevel", "level"),
        ("mississippi", "issi"),
    ]
    text, needle = bases[(idx - 1) % len(bases)]
    key = f"substr_{idx}"
    expected = str(_overlap_count(text, needle))
    prompt = (
        f"In the string '{text}', count overlapping occurrences of substring '{needle}'. "
        f"Store the count under kv key '{key}' and finish with the number."
    )
    return GeneratedCase(
        case_id=_case_id("char_substring_overlap", idx),
        task_prompt=prompt,
        checker_src=_checker_kv_exact(
            key, expected, "CH_SUBSTR_WRONG_COUNT", "CH_SUBSTR_WRONG_FINAL"
        ),
        reference={"actions": [{"tool": "kv_set", "args": {"key": key, "value": expected}}],
                   "final_answer": expected},
        claimed_failure="overlapping_substring_missed",
        tags=["character_level", "substring"],
        generator={"template": "char_substring_overlap", "variant": idx},
    )


def format_extraction(idx: int, rng: random.Random) -> GeneratedCase:
    code = f"{rng.choice(['AZ', 'BK', 'CX', 'DN'])}-{rng.randrange(100, 999)}"
    owner = rng.choice(WORDS)
    checksum = f"{rng.choice('qrstuvwxyz')}{rng.randrange(10, 99)}{rng.choice('abcdef')}"
    status = rng.choice(["hold", "open", "cold", "ready"])
    record = f"ticket={code};owner={owner};checksum={checksum};status={status}"
    key = f"checksum_{idx}"
    prompt = (
        f"From this compact record, extract exactly the checksum field value and nothing else: "
        f"'{record}'. Store it under kv key '{key}' and finish with the checksum."
    )
    return GeneratedCase(
        case_id=_case_id("char_format_extract", idx),
        task_prompt=prompt,
        checker_src=_checker_kv_exact(
            key, checksum, "CH_FORMAT_WRONG_FIELD", "CH_FORMAT_WRONG_FINAL"
        ),
        reference={"actions": [{"tool": "kv_set", "args": {"key": key, "value": checksum}}],
                   "final_answer": checksum},
        claimed_failure="format_field_extraction_wrong",
        tags=["character_level", "format_extraction"],
        generator={"template": "char_format_extract", "variant": idx},
    )


def fine_compare(idx: int, rng: random.Random) -> GeneratedCase:
    stem = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(10))
    pos = rng.randrange(2, 9)
    replacement = rng.choice([c for c in "ABCDEFGHJKLMNPQRSTUVWXYZ23456789" if c != stem[pos]])
    left = stem
    right = stem[:pos] + replacement + stem[pos + 1:]
    expected = str(_first_diff(left, right))
    key = f"diff_{idx}"
    prompt = (
        f"Compare token A '{left}' with token B '{right}'. Store the 1-based index of the "
        f"first differing character under kv key '{key}'. If they are identical, store 0. "
        f"Finish with the index."
    )
    return GeneratedCase(
        case_id=_case_id("char_fine_compare", idx),
        task_prompt=prompt,
        checker_src=_checker_kv_exact(
            key, expected, "CH_COMPARE_WRONG_INDEX", "CH_COMPARE_WRONG_FINAL"
        ),
        reference={"actions": [{"tool": "kv_set", "args": {"key": key, "value": expected}}],
                   "final_answer": expected},
        claimed_failure="fine_grained_comparison_wrong",
        tags=["character_level", "fine_grained_compare"],
        generator={"template": "char_fine_compare", "variant": idx},
    )


TEMPLATES = [
    read_before_write,
    conditional_write,
    overwrite_protection,
    sequence_dependency,
    state_rollback,
    letter_count,
    substring_count,
    format_extraction,
    fine_compare,
]


def generate_cases(total: int = 45, seed: int = 20260709) -> list[GeneratedCase]:
    """Generate a deterministic, template-balanced bundle."""
    if total < len(TEMPLATES):
        raise ValueError(f"total must be at least {len(TEMPLATES)}")
    rng = random.Random(seed)
    cases: list[GeneratedCase] = []
    counts = {fn.__name__: 0 for fn in TEMPLATES}
    while len(cases) < total:
        for fn in TEMPLATES:
            if len(cases) >= total:
                break
            counts[fn.__name__] += 1
            cases.append(fn(counts[fn.__name__], rng))
    return cases
