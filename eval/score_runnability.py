"""Code-runnability eval: 3 independent boolean signals per candidate.

  syntax_ok          — `ast.parse(code)` succeeds
  runs_without_error — `python simulation_code.py` exits 0 within timeout
  produces_video_mp4 — a `video.mp4` of nonzero size exists in the run dir

Each candidate is run in its own freshly-created temp directory so the
subprocess can write `video.mp4` (or anything else) without leaking onto the
host filesystem; the temp dir is removed when scoring is complete.
"""
from __future__ import annotations
import argparse, ast, json, os, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from typing import Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval._common import base_eval_record, read_results, sample_filter, write_jsonl


# ── tunables ─────────────────────────────────────────────────────────────────
DEFAULT_TIMEOUT_S    = 60.0      # per-candidate wall-clock cap
# Prefer the dedicated phys_eval env if it exists; this is the env the
# runnability scorer is meant to be run against (see eval/requirements_eval.txt).
_PHYS_EVAL_PY = "path/to/python"
DEFAULT_INTERPRETER  = _PHYS_EVAL_PY if os.path.isfile(_PHYS_EVAL_PY) else sys.executable
STDERR_TAIL_BYTES    = 1500      # how much stderr to keep for audit
STDOUT_TAIL_BYTES    = 600


def _check_syntax(code: str) -> Optional[str]:
    """Return None if the code is parseable, else the SyntaxError message."""
    try:
        ast.parse(code)
        return None
    except SyntaxError as e:
        return f"{e.__class__.__name__}: {e.msg} (line {e.lineno})"
    except Exception as e:
        return f"{e.__class__.__name__}: {e}"


def _run_in_tempdir(
    code: str,
    timeout_s: float,
    interpreter: str,
    keep_video_to: Optional[Path] = None,
) -> Dict:
    """Write `code` to <tmp>/simulation_code.py and run it under `interpreter`
    with cwd=<tmp>. If a non-empty `video.mp4` is produced and `keep_video_to`
    is given, copy it there before the tempdir is wiped. Returns a dict with
    exit_code, wall_time_s, stdout_tail, stderr_tail, timed_out, video_bytes
    (-1 if no video produced), and video_path (str | None) if kept."""
    tmp = tempfile.mkdtemp(prefix="runeval_")
    script = Path(tmp) / "simulation_code.py"
    script.write_text(code)
    out: Dict = {
        "exit_code": None, "wall_time_s": None,
        "stdout_tail": "", "stderr_tail": "",
        "timed_out": False, "video_bytes": -1,
        "spawn_error": None, "video_path": None,
    }
    t0 = time.time()
    try:
        cp = subprocess.run(
            [interpreter, "simulation_code.py"],
            cwd=tmp, timeout=timeout_s,
            capture_output=True,
        )
        out["exit_code"]   = cp.returncode
        out["stdout_tail"] = cp.stdout[-STDOUT_TAIL_BYTES:].decode(errors="replace")
        out["stderr_tail"] = cp.stderr[-STDERR_TAIL_BYTES:].decode(errors="replace")
    except subprocess.TimeoutExpired as e:
        out["timed_out"]   = True
        out["exit_code"]   = -1
        if e.stdout: out["stdout_tail"] = e.stdout[-STDOUT_TAIL_BYTES:].decode(errors="replace")
        if e.stderr: out["stderr_tail"] = e.stderr[-STDERR_TAIL_BYTES:].decode(errors="replace")
    except Exception as e:
        out["spawn_error"] = f"{type(e).__name__}: {e}"
        out["exit_code"]   = -2
    out["wall_time_s"] = time.time() - t0

    vid = Path(tmp) / "video.mp4"
    if vid.exists():
        out["video_bytes"] = vid.stat().st_size
        if keep_video_to is not None and out["video_bytes"] > 0:
            try:
                keep_video_to.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(vid, keep_video_to)
                out["video_path"] = str(keep_video_to)
            except Exception as e:
                out["spawn_error"] = (out["spawn_error"] or "") + f" (video_copy_err: {e})"
    else:
        out["video_bytes"] = -1

    shutil.rmtree(tmp, ignore_errors=True)
    return out


def score_one_record(
    rec: dict,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    interpreter: str = DEFAULT_INTERPRETER,
    videos_root: Optional[Path] = None,
) -> dict:
    """Returns one eval-record for the runnability scorer.

    If `videos_root` is given, any non-empty video.mp4 produced by the candidate
    is copied to:
        <videos_root>/<engine>/<experiment>/<sample_id>/video.mp4
    and the relative path is stored in `scores.video_path`."""
    row = base_eval_record(rec, "runnability", judge_model=None)

    if not rec.get("parse_ok_code", False):
        row["skipped"]     = True
        row["skip_reason"] = "parse_ok_code=False"
        return row

    code = rec.get("parsed_code") or ""
    if not code.strip():
        row["skipped"]     = True
        row["skip_reason"] = "empty_parsed_code"
        return row

    syntax_err = _check_syntax(code)
    syntax_ok  = syntax_err is None

    runs_ok            = False
    produces_video     = False
    sub: Dict = {"skipped": "syntax_failed"}

    keep_path: Optional[Path] = None
    if videos_root is not None and syntax_ok:
        keep_path = (videos_root / rec["engine"] / rec["experiment"]
                     / rec["sample_id"] / "video.mp4")

    if syntax_ok:
        sub = _run_in_tempdir(code, timeout_s=timeout_s, interpreter=interpreter,
                              keep_video_to=keep_path)
        runs_ok        = (sub["exit_code"] == 0) and not sub["timed_out"]
        produces_video = sub["video_bytes"] > 0

    row["scores"] = {
        "syntax_ok":          syntax_ok,
        "runs_without_error": runs_ok,
        "produces_video_mp4": produces_video,
        "exit_code":          sub.get("exit_code"),
        "wall_time_s":        sub.get("wall_time_s"),
        "timed_out":          sub.get("timed_out", False),
        "video_bytes":        sub.get("video_bytes", -1),
        "video_path":         sub.get("video_path"),
    }
    if syntax_err:
        row["judge_error"] = syntax_err
    elif sub.get("spawn_error"):
        row["judge_error"] = sub["spawn_error"]

    # Save stderr/stdout tails for audit (capped lengths).
    row["raw_response"] = json.dumps({
        "syntax_err":  syntax_err,
        "stdout_tail": sub.get("stdout_tail", ""),
        "stderr_tail": sub.get("stderr_tail", ""),
    }, default=str)
    row["latency_s"]    = sub.get("wall_time_s")
    row["tokens_in"]    = 0
    row["tokens_out"]   = 0
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results",        default="results.jsonl")
    ap.add_argument("--out",            default="eval_results.jsonl")
    ap.add_argument("--limit",          type=int, default=None)
    ap.add_argument("--engines",        nargs="*", default=None)
    ap.add_argument("--experiments",    nargs="*", default=None)
    ap.add_argument("--timeout",        type=float, default=DEFAULT_TIMEOUT_S)
    ap.add_argument("--interpreter",    default=DEFAULT_INTERPRETER)
    ap.add_argument("--videos_root",    default=None,
                    help="If set, copy successful video.mp4 files under "
                         "<videos_root>/<engine>/<exp>/<sid>/video.mp4. "
                         "If unset, generated videos are discarded.")
    args = ap.parse_args()

    recs = [r for r in read_results(args.results)
            if sample_filter(r, args.experiments, args.engines)]
    if args.limit:
        recs = recs[:args.limit]
    videos_root = Path(args.videos_root) if args.videos_root else None
    print(f"[runnability] scoring {len(recs)} records  "
          f"timeout={args.timeout}s  interp={args.interpreter}  "
          f"videos_root={videos_root}")

    rows = [score_one_record(r, timeout_s=args.timeout,
                              interpreter=args.interpreter,
                              videos_root=videos_root)
            for r in recs]
    n = write_jsonl(rows, args.out, append=True)

    n_skip   = sum(r["skipped"] for r in rows)
    n_synok  = sum(1 for r in rows if not r["skipped"] and r.get("scores", {}).get("syntax_ok"))
    n_runok  = sum(1 for r in rows if not r["skipped"] and r.get("scores", {}).get("runs_without_error"))
    n_video  = sum(1 for r in rows if not r["skipped"] and r.get("scores", {}).get("produces_video_mp4"))
    print(f"[runnability] wrote {n} rows to {args.out}  "
          f"skipped={n_skip}  syntax_ok={n_synok}  runs={n_runok}  video={n_video}")


if __name__ == "__main__":
    main()
