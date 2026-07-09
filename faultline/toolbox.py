"""Fixed deterministic toolbox. Cases may NOT define their own tools (day-1 security cut:
miner-supplied code surface is limited to the checker, which runs sandboxed)."""
import ast
import operator as op

_OPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
        ast.Pow: op.pow, ast.USub: op.neg, ast.Mod: op.mod, ast.FloorDiv: op.floordiv}

def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")

def new_state():
    return {"kv": {}, "files": {}}

def calc(state, expression: str):
    """Evaluate an arithmetic expression, e.g. '(1200 * 1.05) ** 3'."""
    try:
        return str(_safe_eval(ast.parse(str(expression), mode="eval")))
    except Exception as e:
        return f"ERROR: {e}"

def kv_set(state, key: str, value: str):
    """Store a string value under a key."""
    state["kv"][str(key)] = str(value)
    return "OK"

def kv_get(state, key: str):
    """Read the value stored under a key."""
    return state["kv"].get(str(key), "ERROR: key not found")

def file_write(state, name: str, content: str):
    """Create/overwrite a file with content."""
    state["files"][str(name)] = str(content)
    return "OK"

def file_append(state, name: str, content: str):
    """Append content to a file (creates it if missing)."""
    state["files"][str(name)] = state["files"].get(str(name), "") + str(content)
    return "OK"

def file_read(state, name: str):
    """Read a file's content."""
    return state["files"].get(str(name), "ERROR: file not found")

TOOLS = {f.__name__: f for f in [calc, kv_set, kv_get, file_write, file_append, file_read]}

def tool_docs():
    lines = []
    for name, f in TOOLS.items():
        args = ", ".join(f.__code__.co_varnames[1:f.__code__.co_argcount])
        lines.append(f"- {name}({args}): {f.__doc__}")
    return "\n".join(lines)
