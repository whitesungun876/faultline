"""Generate 5 handcrafted seed cases into seed_cases/*.json.
Each targets a known small-model weakness; every case ships a passing reference solution."""
import json, pathlib

OUT = pathlib.Path(__file__).parent / "seed_cases"
OUT.mkdir(exist_ok=True)

cases = []

# 1. Non-standard constant trap: prompt overrides a memorized conversion factor.
cases.append({
    "case_id": "seed_001_nonstandard_factor",
    "task_prompt": ("Convert 42 km to 'zeds'. In this company's internal unit system, "
                    "1 km = 0.37 zeds (do NOT use miles or any standard factor). "
                    "Compute it with the calc tool, then store the numeric result "
                    "under kv key 'zeds' and finish."),
    "checker_src": (
        "def check(state, final_answer):\n"
        "    v = state['kv'].get('zeds')\n"
        "    if v is None: return (False, 'A1_missing_key')\n"
        "    try: x = float(v)\n"
        "    except Exception: return (False, 'A2_not_numeric')\n"
        "    return (abs(x - 15.54) < 0.01, 'A3_wrong_value')\n"),
    "reference": {"actions": [
        {"tool": "calc", "args": {"expression": "42 * 0.37"}},
        {"tool": "kv_set", "args": {"key": "zeds", "value": "15.54"}}],
        "final_answer": "15.54"},
    "claimed_failure": "premise_override_ignored"})

# 2. Conditional update trap: must READ before writing.
cases.append({
    "case_id": "seed_002_read_before_write",
    "task_prompt": ("First store value '80' under kv key 'budget'. Then, ONLY IF the current "
                    "value of 'budget' is greater than 100, overwrite it with '0'. Otherwise "
                    "leave it unchanged. Finish with the final value of 'budget'."),
    "checker_src": (
        "def check(state, final_answer):\n"
        "    if state['kv'].get('budget') != '80': return (False, 'B1_state_clobbered')\n"
        "    return (str(final_answer).strip() == '80', 'B2_wrong_final')\n"),
    "reference": {"actions": [
        {"tool": "kv_set", "args": {"key": "budget", "value": "80"}},
        {"tool": "kv_get", "args": {"key": "budget"}}],
        "final_answer": "80"},
    "claimed_failure": "conditional_ignored"})

# 3. Order-sensitive file assembly with a distractor instruction.
cases.append({
    "case_id": "seed_003_append_order",
    "task_prompt": ("Create file 'log.txt' by appending exactly three lines in this order: "
                    "'gamma\\n' then 'alpha\\n' then 'beta\\n'. Note: even though alphabetical "
                    "order would be alpha, beta, gamma, you must use the order given. Finish "
                    "with 'done'."),
    "checker_src": (
        "def check(state, final_answer):\n"
        "    return (state['files'].get('log.txt') == 'gamma\\nalpha\\nbeta\\n', 'C1_wrong_order')\n"),
    "reference": {"actions": [
        {"tool": "file_append", "args": {"name": "log.txt", "content": "gamma\n"}},
        {"tool": "file_append", "args": {"name": "log.txt", "content": "alpha\n"}},
        {"tool": "file_append", "args": {"name": "log.txt", "content": "beta\n"}}],
        "final_answer": "done"},
    "claimed_failure": "distractor_followed"})

# 4. Multi-step arithmetic requiring intermediate persistence.
cases.append({
    "case_id": "seed_004_compound_pipeline",
    "task_prompt": ("Compute 1200 * (1.05 ** 3) with the calc tool, round to 2 decimals, "
                    "store it under kv key 'final_amount', then compute the gain "
                    "(that amount minus 1200), round to 2 decimals, store under kv key 'gain'. "
                    "Finish with the gain."),
    "checker_src": (
        "def check(state, final_answer):\n"
        "    try:\n"
        "        a = float(state['kv'].get('final_amount', 'x'))\n"
        "        g = float(state['kv'].get('gain', 'x'))\n"
        "    except Exception: return (False, 'D1_missing_or_nan')\n"
        "    if abs(a - 1389.15) > 0.01: return (False, 'D2_amount_wrong')\n"
        "    return (abs(g - 189.15) < 0.01, 'D3_gain_wrong')\n"),
    "reference": {"actions": [
        {"tool": "calc", "args": {"expression": "1200 * 1.05 ** 3"}},
        {"tool": "kv_set", "args": {"key": "final_amount", "value": "1389.15"}},
        {"tool": "calc", "args": {"expression": "1389.15 - 1200"}},
        {"tool": "kv_set", "args": {"key": "gain", "value": "189.15"}}],
        "final_answer": "189.15"},
    "claimed_failure": "intermediate_state_lost"})

# 5. Exact-string discipline: tokenizer-hostile counting, no helpful tool exists.
cases.append({
    "case_id": "seed_005_letter_count",
    "task_prompt": ("Count how many times the letter 'r' appears in the string "
                    "'strawberry barrier terror'. Store the count under kv key 'count' "
                    "and finish with the number."),
    "checker_src": (
        "def check(state, final_answer):\n"
        "    return (state['kv'].get('count') == '7', 'E1_wrong_count')\n"),
    "reference": {"actions": [
        {"tool": "kv_set", "args": {"key": "count", "value": "7"}}],
        "final_answer": "7"},
    "claimed_failure": "perception_limit"})

for c in cases:
    (OUT / f"{c['case_id']}.json").write_text(json.dumps(c, indent=2, ensure_ascii=False))
print(f"wrote {len(cases)} cases to {OUT}")
