"""Top-level orchestrator: walk inference_outputs/, run every scorer over every
model's results.jsonl (sharded files concatenated), append to per-model
eval_outputs/<model>/eval_results.jsonl with resume + live flushing.

Usage:
    python eval/run_dataset.py                                 # all models, all scorers, default concurrency
    python eval/run_dataset.py --models qwen3vl_30b_a3b        # only one model
    python eval/run_dataset.py --scorers codebleu              # cheap leg only
    python eval/run_dataset.py --limit 50                      # first 50 samples per model
    python eval/run_dataset.py --concurrency 8                 # tune fan-out
    python eval/run_dataset.py --no-resume                     # ignore existing eval_results.jsonl

For LLM scorers, runs every (sample × judge) call in a thread-pool with
`--concurrency` workers (each worker drives one sample-judge pair). Default 4.
"""
from __future__ import annotations
import argparse, csv, sys, time, traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, List, Optional, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval._common import (
    INFER_ROOT, EVAL_OUT_ROOT, append_row, base_eval_record, existing_keys,
    discover_results, read_results, sample_filter, physical_law_block,
    load_gt_cot, load_gt_code, load_prompt, LIKERT_SCHEMA, set_bench_root,
)


EQUIV_SYS, EQUIV_USR = load_prompt("law_equivalence.md")
VALID_SYS, VALID_USR = load_prompt("law_validity.md")

SampleKey = Tuple[str, str, str]


def load_sample_keys(path: Optional[Path]) -> Optional[Set[SampleKey]]:
    """Read a benchmark manifest and return allowed (engine, experiment, sample_id)."""
    if path is None:
        return None
    keys: Set[SampleKey] = set()
    with path.open(newline="") as f:
        for row in csv.DictReader(f):
            engine = row.get("engine")
            experiment = row.get("experiment")
            sample_id = row.get("sample_id")
            if engine and experiment and sample_id:
                keys.add((str(engine), str(experiment), str(sample_id)))
    return keys


def load_judge_factory() -> dict[str, Any]:
    from eval.judges import GeminiJudge, GrokJudge, OpenAIJudge
    return {"openai": OpenAIJudge, "gemini": GeminiJudge, "grok": GrokJudge}


# ── Per (sample, judge, scorer) work item ────────────────────────────────────

def _equiv_user(gt_law, cd_law) -> str:
    return EQUIV_USR.format(
        gt_name      = gt_law["name"]      or "(empty)",
        gt_statement = gt_law["statement"] or "(empty)",
        gt_formula   = gt_law["formula"]   or "(empty)",
        cand_name      = cd_law["name"]      or "(empty)",
        cand_statement = cd_law["statement"] or "(empty)",
        cand_formula   = cd_law["formula"]   or "(empty)",
    )


def _valid_user(cd_law) -> str:
    return VALID_USR.format(
        cand_name      = cd_law["name"]      or "(empty)",
        cand_statement = cd_law["statement"] or "(empty)",
        cand_formula   = cd_law["formula"]   or "(empty)",
    )


def _llm_call(judge: Any, scorer: str, rec: dict,
              gt_law=None, cd_law=None) -> dict:
    """Run one scorer (equivalence|validity) for one (sample, judge) and
    return the eval-row dict ready for append."""
    row = base_eval_record(rec, scorer, judge.name)
    if scorer == "law_equivalence":
        sys_p, usr_p = EQUIV_SYS, _equiv_user(gt_law, cd_law)
    elif scorer == "law_validity":
        sys_p, usr_p = VALID_SYS, _valid_user(cd_law)
    else:
        raise ValueError(scorer)
    resp = judge.call(sys_p, usr_p, LIKERT_SCHEMA)
    row["raw_response"] = resp.raw_text
    row["latency_s"]    = resp.latency_s
    row["tokens_in"]    = resp.tokens_in
    row["tokens_out"]   = resp.tokens_out
    row["judge_error"]  = resp.error
    if resp.parsed:
        row["scores"] = {
            "name":      resp.parsed.get("name_score"),
            "statement": resp.parsed.get("statement_score"),
            "formula":   resp.parsed.get("formula_score"),
            "overall":   resp.parsed.get("overall_score"),
        }
        row["justification"] = resp.parsed.get("justification")
    return row


def _skip_row(rec: dict, scorer: str, judge_name: Optional[str], reason: str) -> dict:
    row = base_eval_record(rec, scorer, judge_name)
    row["skipped"]     = True
    row["skip_reason"] = reason
    return row


# ── Per-model run ────────────────────────────────────────────────────────────

def run_model(
    model_dir: Path,
    *,
    scorers: List[str],
    judges: List[Any],
    out_path: Path,
    concurrency: int,
    resume: bool,
    limit: Optional[int],
    engines_filter: Optional[List[str]],
    experiments_filter: Optional[List[str]],
    videos_root: Optional[Path] = None,
    runnability_timeout_s: float = 60.0,
    allowed_sample_keys: Optional[Set[SampleKey]] = None,
) -> None:
    files = discover_results(model_dir)
    if not files:
        print(f"  ! no results*.jsonl found in {model_dir}")
        return

    rows_in = []
    for f in files:
        rows_in.extend(read_results(str(f)))
    rows_in = [r for r in rows_in if sample_filter(r, experiments_filter, engines_filter)]
    if allowed_sample_keys is not None:
        rows_in = [
            r for r in rows_in
            if (str(r.get("engine")), str(r.get("experiment")), str(r.get("sample_id")))
            in allowed_sample_keys
        ]
    if limit:
        rows_in = rows_in[:limit]

    done: dict[str, set] = {}
    if resume:
        for s in scorers:
            done[s] = existing_keys(out_path, scorers=[s])

    print(f"  {len(rows_in)} input rows, output → {out_path}")
    if resume:
        for s in scorers:
            print(f"    [{s}] resuming: {len(done.get(s, set()))} previously-scored rows in output")

    # ── Build the work queue ────────────────────────────────────────────────
    work = []
    for rec in rows_in:
        eng, exp, sid, model = rec["engine"], rec["experiment"], rec["sample_id"], rec["model"]
        for scorer in scorers:
            if scorer == "codebleu":
                key = (eng, exp, sid, model, "codebleu", None)
                if resume and key in done.get("codebleu", set()):
                    continue
                work.append(("codebleu", rec, None))
                continue
            if scorer == "runnability":
                key = (eng, exp, sid, model, "runnability", None)
                if resume and key in done.get("runnability", set()):
                    continue
                work.append(("runnability", rec, None))
                continue
            # LLM scorers: parse_ok_cot gate
            if not rec.get("parse_ok_cot", False):
                # write skip rows once per judge for accounting
                for j in judges:
                    key = (eng, exp, sid, model, scorer, j.name)
                    if resume and key in done.get(scorer, set()):
                        continue
                    work.append((scorer, rec, ("skip", "parse_ok_cot=False", j)))
                continue
            for j in judges:
                key = (eng, exp, sid, model, scorer, j.name)
                if resume and key in done.get(scorer, set()):
                    continue
                work.append((scorer, rec, ("call", None, j)))

    print(f"    total work items: {len(work)}")
    if not work:
        return

    # Pre-fetch ground-truth physical-law blocks per sample (cheap, local I/O)
    gt_law_cache: dict[Tuple[str, str, str], dict] = {}
    def _gt_law(rec):
        key = (rec["engine"], rec["experiment"], rec["sample_id"])
        if key not in gt_law_cache:
            try:
                gt_law_cache[key] = physical_law_block(load_gt_cot(*key))
            except Exception:
                gt_law_cache[key] = {"name": "", "statement": "", "formula": ""}
        return gt_law_cache[key]

    codebleu_one = None
    runnability_one = None
    if "codebleu" in scorers:
        from eval.score_codebleu import score_one_record as codebleu_one
    if "runnability" in scorers:
        from eval.score_runnability import score_one_record as runnability_one

    def _exec(item):
        scorer, rec, payload = item
        if scorer == "codebleu":
            return codebleu_one(rec)
        if scorer == "runnability":
            return runnability_one(rec, videos_root=videos_root,
                                    timeout_s=runnability_timeout_s)
        # LLM scorer
        kind, reason, judge = payload
        if kind == "skip":
            return _skip_row(rec, scorer, judge.name, reason)
        cd_law = physical_law_block(rec.get("parsed_cot") or {})
        gt_law = _gt_law(rec) if scorer == "law_equivalence" else None
        try:
            return _llm_call(judge, scorer, rec, gt_law=gt_law, cd_law=cd_law)
        except Exception as e:
            row = base_eval_record(rec, scorer, judge.name)
            row["judge_error"] = f"{type(e).__name__}: {e}"
            return row

    # ── Run with thread pool, append rows live ──────────────────────────────
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    n_done = n_err = n_skip = 0
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futs = {ex.submit(_exec, item): item for item in work}
        for fut in as_completed(futs):
            try:
                row = fut.result()
            except Exception as e:
                tb = traceback.format_exc()
                print(f"    !! exec failure: {e}\n{tb}", file=sys.stderr)
                continue
            append_row(out_path, row)
            n_done += 1
            if row.get("skipped"):    n_skip += 1
            if row.get("judge_error"): n_err += 1
            if n_done % 50 == 0 or n_done == len(work):
                rate = n_done / max(time.time() - t0, 1e-3)
                print(f"    [{n_done}/{len(work)}]  ok={n_done-n_skip-n_err}  "
                      f"skipped={n_skip}  errored={n_err}  ({rate:.1f}/s)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inference_root", default=str(INFER_ROOT))
    ap.add_argument("--out_root",       default=str(EVAL_OUT_ROOT))
    ap.add_argument("--bench_root",     default=None,
                    help="benchmarking_data-shaped GT root; defaults to PHYSIM_BENCH_ROOT or repo benchmarking_data")
    ap.add_argument("--sample_manifest", default=None,
                    help="optional manifest.csv limiting evaluation to listed samples")
    ap.add_argument("--models",         nargs="*", default=None,
                    help="If omitted, every subdir of inference_outputs/ except _logs is processed.")
    ap.add_argument("--scorers",        nargs="*",
                    default=["equivalence", "validity", "codebleu", "runnability"])
    ap.add_argument("--judges",         nargs="*", default=["openai", "gemini", "grok"])
    ap.add_argument("--concurrency",    type=int, default=4)
    ap.add_argument("--limit",          type=int, default=None)
    ap.add_argument("--engines",        nargs="*", default=None)
    ap.add_argument("--experiments",    nargs="*", default=None)
    ap.add_argument("--no-resume",      dest="resume", action="store_false")
    ap.add_argument("--no-keep-videos", dest="keep_videos", action="store_false",
                    help="Discard generated video.mp4 files instead of saving them.")
    ap.add_argument("--runnability_timeout", type=float, default=60.0,
                    help="Per-candidate wall-clock cap for the runnability scorer (seconds).")
    args = ap.parse_args()

    infer_root = Path(args.inference_root)
    out_root   = Path(args.out_root)
    bench_root = set_bench_root(args.bench_root) if args.bench_root else None
    sample_keys = load_sample_keys(Path(args.sample_manifest)) if args.sample_manifest else None
    scorer_map = {"equivalence": "law_equivalence",
                  "validity":    "law_validity",
                  "codebleu":    "codebleu",
                  "runnability": "runnability"}
    scorers = [scorer_map[s] for s in args.scorers]
    needs_llm = any(s in ("law_equivalence", "law_validity") for s in scorers)
    judge_factory = load_judge_factory() if needs_llm else {}
    judges = [judge_factory[n]() for n in args.judges] if needs_llm else []

    if args.models:
        model_dirs = [infer_root / m for m in args.models]
    else:
        model_dirs = sorted(p for p in infer_root.iterdir()
                             if p.is_dir() and not p.name.startswith("_"))

    print(f"[run_dataset] models = {[d.name for d in model_dirs]}")
    print(f"[run_dataset] scorers = {scorers}")
    print(f"[run_dataset] judges = {[j.name for j in judges]}")
    print(f"[run_dataset] concurrency = {args.concurrency}    resume = {args.resume}")
    if bench_root is not None:
        print(f"[run_dataset] bench_root = {bench_root}")
    if sample_keys is not None:
        print(f"[run_dataset] sample_manifest = {args.sample_manifest} ({len(sample_keys)} samples)")

    for md in model_dirs:
        if not md.exists():
            print(f"\n!! model dir missing: {md}")
            continue
        out_path    = out_root / md.name / "eval_results.jsonl"
        videos_root = (out_root / md.name / "runs") if args.keep_videos else None
        print(f"\n=== {md.name} ===   videos_root={videos_root}")
        run_model(
            md,
            scorers=scorers,
            judges=judges,
            out_path=out_path,
            concurrency=args.concurrency,
            resume=args.resume,
            limit=args.limit,
            engines_filter=args.engines,
            experiments_filter=args.experiments,
            videos_root=videos_root,
            runnability_timeout_s=args.runnability_timeout,
            allowed_sample_keys=sample_keys,
        )


if __name__ == "__main__":
    main()
