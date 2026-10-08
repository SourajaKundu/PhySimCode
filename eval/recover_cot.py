"""Tolerant recovery of CoT JSON from a model's raw_output.

Handles five cases observed in real model outputs:

  1. Properly delimited (`@@COT_BEGIN@@...@@COT_END@@`) but JSON-malformed
     (Python arithmetic in `"value"` fields, single quotes, trailing commas,
     unicode π, unescaped LaTeX backslashes, comments, …).
  2. Markdown-fenced JSON (` ```json ... ``` `) with no @@COT_BEGIN@@ at all.
  3. Truncated mid-emission — `@@COT_BEGIN@@` is open but never closes.
  4. Both delimiters missing entirely (rare).
  5. Already-valid JSON.

A single public entry point `recover_cot(raw)` returns a `RecoveryResult`
describing what was salvaged.
"""
from __future__ import annotations
import json, re, ast, math
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


# ── Safe arithmetic evaluator (whitelist of constants and pure-math functions) ──

_ALLOWED_NAMES = {
    "pi": math.pi, "PI": math.pi,
    "e":  math.e,  "E":  math.e,
    "inf": float("inf"),
}
_ALLOWED_FUNCS = {
    "sqrt": math.sqrt, "cbrt": (lambda x: x ** (1/3)),
    "cos":  math.cos,  "sin":  math.sin,  "tan":  math.tan,
    "acos": math.acos, "asin": math.asin, "atan": math.atan,
    "log":  math.log,  "log10": math.log10, "log2": math.log2,
    "exp":  math.exp,
    "abs":  abs, "min": min, "max": max,
    "pow":  pow, "round": round,
    "ceil": math.ceil, "floor": math.floor,
}


def _safe_eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_NAMES:
            return _ALLOWED_NAMES[node.id]
        raise ValueError(f"unknown name {node.id}")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _safe_eval(node.operand)
        return -v if isinstance(node.op, ast.USub) else +v
    if isinstance(node, ast.BinOp) and isinstance(
        node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.FloorDiv)
    ):
        l, r = _safe_eval(node.left), _safe_eval(node.right)
        return {
            ast.Add: l + r, ast.Sub: l - r, ast.Mult: l * r, ast.Div: l / r,
            ast.Pow: l ** r, ast.Mod: l % r, ast.FloorDiv: l // r,
        }[type(node.op)]
    if isinstance(node, ast.Attribute):
        # math.pi, np.pi, Math.PI, numpy.e, etc.
        if isinstance(node.value, ast.Name) and node.value.id in ("math", "np", "numpy", "Math"):
            attr = node.attr
            if attr in _ALLOWED_NAMES:
                return _ALLOWED_NAMES[attr]
            if attr.lower() == "pi":
                return math.pi
            if attr.lower() == "e":
                return math.e
        raise ValueError("attribute access not allowed")
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS:
            return _ALLOWED_FUNCS[node.func.id](*[_safe_eval(a) for a in node.args])
        if isinstance(node.func, ast.Attribute):
            f = node.func
            if isinstance(f.value, ast.Name) and f.value.id in ("math", "np", "numpy") \
                    and f.attr in _ALLOWED_FUNCS:
                return _ALLOWED_FUNCS[f.attr](*[_safe_eval(a) for a in node.args])
    raise ValueError(f"node type {type(node).__name__} not allowed")


def _arith_to_number(expr: str) -> Optional[float]:
    try:
        return _safe_eval(ast.parse(expr.strip(), mode="eval").body)
    except Exception:
        return None


# ── Block extraction ─────────────────────────────────────────────────────────

_RE_COT_BLOCK = re.compile(
    r"@@COT_BEGIN@@\s*(.*?)\s*(?:@@COT_END@@|@@CODE_BEGIN@@|\Z)",
    re.DOTALL,
)
_RE_MD_JSON  = re.compile(r"```json\s*\n(.*?)\n```", re.DOTALL)
_RE_MD_PLAIN = re.compile(r"```\s*\n(\{.*?\})\s*\n```", re.DOTALL)


def _find_cot_text(raw: str) -> Optional[str]:
    """Find the JSON-shaped CoT region in raw model output."""
    m = _RE_COT_BLOCK.search(raw)
    if m and m.group(1).strip().startswith("{"):
        return m.group(1).strip()
    m = _RE_MD_JSON.search(raw)
    if m:
        return m.group(1).strip()
    m = _RE_MD_PLAIN.search(raw)
    if m:
        return m.group(1).strip()
    # last-ditch: look for the first `{` that begins a top-level object
    idx = raw.find('{')
    if idx >= 0 and '"physical_law"' in raw[idx: idx + 5000]:
        # try to balance braces
        depth = 0; end = None
        for i, ch in enumerate(raw[idx:], idx):
            if ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0: end = i + 1; break
        if end:
            return raw[idx:end].strip()
    return None


# ── Progressive JSON recovery ────────────────────────────────────────────────

def _basic_fixups(s: str) -> str:
    s = s.replace("π", "3.141592653589793")
    s = re.sub(r",(\s*[}\]])", r"\1", s)              # trailing commas
    s = re.sub(r"//[^\n]*", "", s)                    # // comments
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)  # /* */ comments
    return s


def _escape_latex_backslashes(s: str) -> str:
    r"""Inside every JSON string, escape `\X` where X is not a valid JSON escape."""
    return re.sub(
        r'"((?:[^"\\]|\\.)*)"',
        lambda m: '"' + re.sub(r"\\(?![\\\"/bfnrtu])", r"\\\\", m.group(1)) + '"',
        s, flags=re.DOTALL,
    )


_RE_VALUE_EXPR = re.compile(r'("value"\s*:\s*)([^",\{\[\}\]]+?)(\s*[,\}\]])')
_RE_VALUE_LIST = re.compile(r'("value"\s*:\s*)\[([^\]]+)\]')


def _evaluate_value_arithmetic(s: str) -> str:
    def rv(m: re.Match) -> str:
        v = _arith_to_number(m.group(2))
        if v is None:
            return m.group(0)
        return f"{m.group(1)}{json.dumps(v)}{m.group(3)}"
    return _RE_VALUE_EXPR.sub(rv, s)


def _evaluate_value_lists(s: str) -> str:
    def rl(m: re.Match) -> str:
        new = []
        for it in m.group(2).split(","):
            v = _arith_to_number(it.strip())
            new.append(json.dumps(v) if v is not None else it)
        return f"{m.group(1)}[{', '.join(new)}]"
    return _RE_VALUE_LIST.sub(rl, s)


def _try_progressive(s: str):
    """Run the full fix-up cascade. Yield (label, new_s) at each stage."""
    yield "raw", s
    s1 = _basic_fixups(s);                                yield "basic_fixups", s1
    s2 = _escape_latex_backslashes(s1);                   yield "latex_escape", s2
    s3 = _evaluate_value_arithmetic(s2);                  yield "evaluate_arith", s3
    s4 = _evaluate_value_lists(s3);                       yield "evaluate_lists", s4


# ── Public entry point ──────────────────────────────────────────────────────

@dataclass
class RecoveryResult:
    parsed_cot:   Optional[Dict[str, Any]] = None     # the full recovered dict
    physical_law: Optional[Dict[str, str]] = None     # convenience: name/statement/formula
    method:       str = "none"                        # which fix-up succeeded
    partial:      bool = False                        # True if only physical_law (not full JSON)
    error:        Optional[str] = None


_RE_LAW_BLOCK = re.compile(r'"physical_law"\s*:\s*\{([^{}]*)\}', re.DOTALL)


def _regex_extract_physical_law(text: str) -> Optional[Dict[str, str]]:
    m = _RE_LAW_BLOCK.search(text)
    if not m:
        return None
    block = m.group(1)
    def grab(field):
        x = re.search(rf'"{field}"\s*:\s*"((?:[^"\\]|\\.)*)"', block)
        return x.group(1) if x else ""
    out = {"name": grab("name"), "statement": grab("statement"), "formula": grab("formula")}
    return out if out["name"] else None


def recover_cot(raw_output: str, *, original_parsed_cot: Any = None) -> RecoveryResult:
    """Try to salvage a parsed CoT dict from raw_output.

    If `original_parsed_cot` is already a dict with a non-empty `physical_law`,
    return it as-is (the row was already fine; nothing to recover).
    """
    if isinstance(original_parsed_cot, dict):
        pl = original_parsed_cot.get("physical_law")
        if isinstance(pl, dict) and pl.get("name"):
            return RecoveryResult(
                parsed_cot=original_parsed_cot,
                physical_law={k: str(pl.get(k, "") or "") for k in ("name","statement","formula")},
                method="already_valid",
            )

    text = _find_cot_text(raw_output or "")
    if text is None:
        return RecoveryResult(method="no_cot_block", error="no JSON-shaped block found")

    # Stage 1 — full JSON recovery via progressive fix-ups
    last_err = None
    for label, candidate in _try_progressive(text):
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict) and isinstance(obj.get("physical_law"), dict):
                pl = obj["physical_law"]
                law = {k: str(pl.get(k, "") or "") for k in ("name","statement","formula")}
                return RecoveryResult(parsed_cot=obj, physical_law=law, method=label)
            return RecoveryResult(parsed_cot=obj, physical_law=None, method=label,
                                   partial=True, error="parsed but no physical_law block")
        except json.JSONDecodeError as e:
            last_err = e
            continue

    # Stage 2 — json5 fallback
    try:
        import json5  # type: ignore
        obj = json5.loads(text)
        if isinstance(obj, dict) and isinstance(obj.get("physical_law"), dict):
            pl = obj["physical_law"]
            law = {k: str(pl.get(k, "") or "") for k in ("name","statement","formula")}
            return RecoveryResult(parsed_cot=obj, physical_law=law, method="json5")
    except Exception:
        pass

    # Stage 3 — regex-only physical_law extraction (handles truncated mid-stream)
    law = _regex_extract_physical_law(text) or _regex_extract_physical_law(raw_output)
    if law:
        return RecoveryResult(
            parsed_cot={"physical_law": law},
            physical_law=law,
            method="regex_law_only",
            partial=True,
        )

    return RecoveryResult(method="unrecoverable",
                          error=str(last_err) if last_err else "no physical_law extractable")
