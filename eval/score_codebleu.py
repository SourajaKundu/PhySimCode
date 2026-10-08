"""Compute CodeBLEU between the model's generated simulation code and the
ground-truth simulation code at the configured benchmarking_data root.

Uses the `codebleu` PyPI package with lang="python" and equal-weight defaults.
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval._common import (
    base_eval_record, load_gt_code, read_results, sample_filter, set_bench_root,
    write_jsonl,
)

from codebleu import calc_codebleu  # noqa: E402


CODEBLEU_WEIGHTS = (0.25, 0.25, 0.25, 0.25)  # ngram, weighted_ngram, syntax, dataflow


def score_one_record(rec: dict) -> dict:
    row = base_eval_record(rec, "codebleu", judge_model=None)
    if not rec.get("parse_ok_code", False):
        row["skipped"]     = True
        row["skip_reason"] = "parse_ok_code=False"
        return row

    cand = rec.get("parsed_code") or ""
    if not cand.strip():
        row["skipped"]     = True
        row["skip_reason"] = "empty_parsed_code"
        return row

    try:
        gt = load_gt_code(rec["engine"], rec["experiment"], rec["sample_id"])
    except FileNotFoundError as e:
        row["judge_error"] = f"missing_gt_code: {e}"
        return row

    t0 = time.time()
    try:
        result = calc_codebleu(
            [gt], [cand], lang="python",
            weights=CODEBLEU_WEIGHTS, tokenizer=None,
        )
        row["scores"] = {
            "codebleu":                    float(result["codebleu"]),
            "ngram_match_score":           float(result["ngram_match_score"]),
            "weighted_ngram_match_score":  float(result["weighted_ngram_match_score"]),
            "syntax_match_score":          float(result["syntax_match_score"]),
            "dataflow_match_score":        float(result["dataflow_match_score"]),
        }
    except Exception as e:
        row["judge_error"] = f"{type(e).__name__}: {e}"
    row["latency_s"]   = time.time() - t0
    row["tokens_in"]   = 0
    row["tokens_out"]  = 0
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results.jsonl")
    ap.add_argument("--out",     default="eval_results.jsonl")
    ap.add_argument("--bench_root", default=None)
    ap.add_argument("--limit",   type=int, default=None)
    ap.add_argument("--engines",     nargs="*", default=None)
    ap.add_argument("--experiments", nargs="*", default=None)
    args = ap.parse_args()
    if args.bench_root:
        set_bench_root(args.bench_root)

    recs = [r for r in read_results(args.results)
            if sample_filter(r, args.experiments, args.engines)]
    if args.limit:
        recs = recs[:args.limit]
    print(f"[codebleu] scoring {len(recs)} records")

    rows = [score_one_record(r) for r in recs]
    n = write_jsonl(rows, args.out, append=True)
    n_skip = sum(r["skipped"] for r in rows)
    n_err  = sum(bool(r["judge_error"]) for r in rows)
    print(f"[codebleu] wrote {n} rows to {args.out}  "
          f"({n_skip} skipped, {n_err} errored)")


if __name__ == "__main__":
    main()
