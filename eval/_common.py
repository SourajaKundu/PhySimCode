"""Shared helpers used by every score_*.py and the orchestrator."""
from __future__ import annotations
import os, json, re, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False
load_dotenv()

REPO_ROOT     = Path(__file__).resolve().parent.parent
EVAL_DIR      = Path(__file__).resolve().parent
PROMPTS_DIR   = EVAL_DIR / "prompts"


def _root_from_env(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser().resolve() if raw else default


BENCH_ROOT    = _root_from_env("PHYSIM_BENCH_ROOT", REPO_ROOT / "benchmarking_data")
INFER_ROOT    = _root_from_env("PHYSIM_INFER_ROOT", REPO_ROOT / "inference_outputs")
EVAL_OUT_ROOT = _root_from_env("PHYSIM_EVAL_OUT_ROOT", REPO_ROOT / "eval_outputs")


def set_bench_root(path: str | Path) -> Path:
    """Point GT loaders at a different benchmarking_data-shaped root."""
    global BENCH_ROOT
    BENCH_ROOT = Path(path).expanduser().resolve()
    return BENCH_ROOT


# ── Likert-scoring JSON schema (re-used by both equivalence and validity) ───
LIKERT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "name_score":      {"type": "integer", "minimum": 0, "maximum": 4},
        "statement_score": {"type": "integer", "minimum": 0, "maximum": 4},
        "formula_score":   {"type": "integer", "minimum": 0, "maximum": 4},
        "overall_score":   {"type": "integer", "minimum": 0, "maximum": 4},
        "justification":   {"type": "string"},
    },
    "required": ["name_score", "statement_score", "formula_score",
                 "overall_score", "justification"],
    "additionalProperties": False,
}


def load_prompt(filename: str) -> Tuple[str, str]:
    """Read prompts/<filename> and split into (system, user) sections.
    The file format is:
        SYSTEM:
        <system content>
        USER:
        <user content with {placeholders}>
    """
    text = (PROMPTS_DIR / filename).read_text()
    m = re.match(r"SYSTEM:\s*\n(.*?)\nUSER:\s*\n(.*)", text, flags=re.DOTALL)
    if not m:
        raise ValueError(f"prompt file {filename} missing SYSTEM/USER sections")
    return m.group(1).strip(), m.group(2).strip()


def read_results(path: str) -> List[dict]:
    out = []
    n_bad = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                n_bad += 1
    if n_bad:
        print(f"  [read_results] {n_bad} unparseable line(s) skipped in {path}",
              file=sys.stderr)
    return out


def write_jsonl(rows: Iterable[dict], path: str, append: bool = False) -> int:
    mode = "a" if append else "w"
    n = 0
    with open(path, mode) as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
            n += 1
    return n


def gt_path(engine: str, experiment: str, sample_id: str) -> Path:
    return BENCH_ROOT / engine / experiment / sample_id


def load_gt_cot(engine: str, experiment: str, sample_id: str) -> dict:
    return json.loads((gt_path(engine, experiment, sample_id) / "cot.json").read_text())


def load_gt_code(engine: str, experiment: str, sample_id: str) -> str:
    return (gt_path(engine, experiment, sample_id) / "simulation_code.py").read_text()


def physical_law_block(cot: dict) -> Dict[str, str]:
    """Pull (name, statement, formula) out of any cot.json, defaulting to
    empty strings if a field is missing or non-string."""
    pl = cot.get("physical_law") or {}
    if not isinstance(pl, dict):
        return {"name": "", "statement": "", "formula": ""}
    return {
        "name":      str(pl.get("name", "") or ""),
        "statement": str(pl.get("statement", "") or ""),
        "formula":   str(pl.get("formula", "") or ""),
    }


def base_eval_record(rec: dict, scorer: str, judge_model: Optional[str]) -> dict:
    """The fields every eval_results.jsonl row carries, regardless of scorer."""
    return {
        "engine":      rec["engine"],
        "experiment":  rec["experiment"],
        "sample_id":   rec["sample_id"],
        "model":       rec["model"],
        "scorer":      scorer,
        "judge_model": judge_model,
        "scores":      None,
        "justification": None,
        "raw_response":  None,
        "latency_s":   None,
        "tokens_in":   None,
        "tokens_out":  None,
        "judge_error": None,
        "skipped":     False,
        "skip_reason": None,
    }


def fan_out(judges, fn, **kwargs) -> List[Any]:
    """Run `fn(judge, **kwargs)` over every judge concurrently. Returns results
    in the same order as the input judge list."""
    out: List[Any] = [None] * len(judges)
    with ThreadPoolExecutor(max_workers=len(judges)) as ex:
        futs = {ex.submit(fn, j, **kwargs): i for i, j in enumerate(judges)}
        for fut in as_completed(futs):
            i = futs[fut]
            out[i] = fut.result()
    return out


def sample_filter(rec: dict,
                  experiments: Optional[List[str]] = None,
                  engines: Optional[List[str]] = None) -> bool:
    if experiments is not None and rec.get("experiment") not in experiments:
        return False
    if engines is not None and rec.get("engine") not in engines:
        return False
    return True


# ── Resume / dedupe helpers ──────────────────────────────────────────────────

def existing_keys(eval_path: str | Path,
                  scorers: Optional[List[str]] = None) -> set[Tuple]:
    """Read an eval_results.jsonl (if any) and return the set of
    (engine, experiment, sample_id, model, scorer, judge_model) tuples
    already present. Rows with `skipped=True` or `judge_error` are NOT
    counted as done — we'd want to retry those on a resume."""
    keys: set[Tuple] = set()
    p = Path(eval_path)
    if not p.exists():
        return keys
    for line in p.open():
        if not line.strip(): continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if scorers and r.get("scorer") not in scorers:
            continue
        # Treat valid scored rows as done; skipped or errored rows we may
        # want to retry, so don't dedupe against them.
        if r.get("skipped"): continue
        if r.get("judge_error"): continue
        if not r.get("scores"): continue
        keys.add((
            r.get("engine"), r.get("experiment"), r.get("sample_id"),
            r.get("model"), r.get("scorer"), r.get("judge_model"),
        ))
    return keys


# ── Sharded results.jsonl helpers ────────────────────────────────────────────

def discover_results(model_dir: Path, prefer_recovered: bool = True) -> List[Path]:
    """Return the input results JSONL files for a model directory.

    Precedence:
        1. results_recovered.jsonl (if it exists and prefer_recovered=True).
           That file already contains every input row with parse_ok_cot patched.
        2. results.jsonl (the merged/canonical file).
        3. results.shard_*.jsonl (intermediate shards, only when no merged
           results.jsonl is present — otherwise we'd double-count).
    """
    if prefer_recovered:
        rec = model_dir / "results_recovered.jsonl"
        if rec.is_file():
            return [rec]
    merged = model_dir / "results.jsonl"
    if merged.is_file():
        return [merged]
    shards = sorted(p for p in model_dir.glob("results.shard_*.jsonl") if p.is_file())
    return shards


def read_results_dir(model_dir: Path) -> List[dict]:
    """Concatenate every results*.jsonl in a model directory."""
    out: List[dict] = []
    for p in discover_results(model_dir):
        out.extend(read_results(str(p)))
    return out


# ── Append-line writer ───────────────────────────────────────────────────────

def append_row(path: str | Path, row: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")
        f.flush()
