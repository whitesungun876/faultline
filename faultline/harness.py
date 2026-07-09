"""Minimal deterministic tool-agent loop.
Backends: HFBackend (pinned open-weight model, greedy) for real runs; ScriptedBackend for tests.
Every step's model output must be a single JSON object:
  {"tool": "<name>", "args": {...}}   or   {"finish": "<final answer string>"}
Malformed output is itself a recorded failure mode (action "MALFORMED")."""
import json
import re
from .toolbox import TOOLS, tool_docs, new_state

MAX_STEPS = 12

SYSTEM = (
    "You are an agent that completes tasks using tools. Available tools:\n{docs}\n"
    "At each step reply with EXACTLY one JSON object and nothing else, either\n"
    '{{"tool": "<tool_name>", "args": {{...}}}} to call a tool, or\n'
    '{{"finish": "<final answer>"}} when done.\n'
    'The "args" value must always be a JSON object, never a list or string.\n'
    "Example:\n"
    "User: Store value 'hello' under kv key 'demo'.\n"
    'Assistant: {{"tool": "kv_set", "args": {{"key": "demo", "value": "hello"}}}}\n'
    "User: Observation: OK\n"
    'Assistant: {{"finish": "hello"}}'
)

class ScriptedBackend:
    """Deterministic scripted 'model' for tests and offline demos."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.i = 0
    def generate(self, messages):
        r = self.responses[min(self.i, len(self.responses) - 1)]
        self.i += 1
        return r

class HFBackend:
    """Pinned open-weight model, greedy decoding. Requires GPU/CPU + transformers.
    NOTE: not runnable inside this sandbox (no HF network access); run on your machine."""
    def __init__(self, model_id="Qwen/Qwen2.5-1.5B-Instruct", device="auto"):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        self.tok = AutoTokenizer.from_pretrained(model_id)
        self.model = AutoModelForCausalLM.from_pretrained(
            model_id, torch_dtype=torch.bfloat16, device_map=device)
    def generate(self, messages):
        text = self.tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        ids = self.tok(text, return_tensors="pt").to(self.model.device)
        out = self.model.generate(**ids, max_new_tokens=256, do_sample=False,
                                  temperature=None, top_p=None, top_k=None)
        return self.tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)

def _parse_action(text):
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict) and ("finish" in obj or ("tool" in obj and isinstance(obj.get("args", {}), dict))):
        return obj
    return None

def execute_action(state, action):
    """Shared executor used by both the agent loop and reference-solution replay."""
    name = action["tool"]
    if name not in TOOLS:
        return f"ERROR: unknown tool {name}"
    try:
        return TOOLS[name](state, **action.get("args", {}))
    except TypeError as e:
        return f"ERROR: bad args: {e}"

def run_agent(backend, task_prompt, max_steps=MAX_STEPS):
    """Returns (state, final_answer_or_None, trace). Trace is a list of step dicts."""
    state = new_state()
    messages = [{"role": "system", "content": SYSTEM.format(docs=tool_docs())},
                {"role": "user", "content": task_prompt}]
    trace = []
    for step in range(max_steps):
        raw = backend.generate(messages)
        action = _parse_action(raw)
        if action is None:
            trace.append({"step": step, "action": "MALFORMED", "raw": raw[:500]})
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": "Invalid format. Reply with exactly one JSON object."})
            continue
        if "finish" in action:
            trace.append({"step": step, "action": "FINISH", "answer": str(action["finish"])})
            return state, str(action["finish"]), trace
        obs = execute_action(state, action)
        trace.append({"step": step, "action": action["tool"], "args": action.get("args", {}), "obs": str(obs)[:500]})
        messages.append({"role": "assistant", "content": json.dumps(action)})
        messages.append({"role": "user", "content": f"Observation: {obs}"})
    trace.append({"step": max_steps, "action": "MAX_STEPS"})
    return state, None, trace

def run_reference(reference):
    """Replay a miner-supplied reference solution: {'actions': [...], 'final_answer': str}."""
    state = new_state()
    for a in reference.get("actions", []):
        execute_action(state, a)
    return state, reference.get("final_answer")
