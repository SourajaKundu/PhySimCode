"""Score law equivalence: candidate physical_law vs ground-truth physical_law.

For each results.jsonl row, calls each judge once with the equivalence prompt
and writes one eval_results.jsonl row per (sample × judge).
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval._common import (
    LIKERT_SCHEMA, base_eval_record, fan_out, load_gt_cot, load_prompt,
    physical_law_block, read_results, sample_filter, set_bench_root, write_jsonl,
)
from eval.judges import OpenAIJudge, GeminiJudge, GrokJudge, JudgeClient

SYSTEM_PROMPT, USER_TEMPLATE = load_prompt("law_equivalence.md")


def _format_user_prompt(gt_law: dict, cand_law: dict) -> str:
    return USER_TEMPLATE.format(
        gt_name      = gt_law["name"]      or "(empty)",
        gt_statement = gt_law["statement"] or "(empty)",
        gt_formula   = gt_law["formula"]   or "(empty)",
        cand_name      = cand_law["name"]      or "(empty)",
        cand_statement = cand_law["statement"] or "(empty)",
        cand_formula   = cand_law["formula"]   or "(empty)",
    )


def _judge_one(judge: JudgeClient, *, system: str, user: str) -> dict:
    resp = judge.call(system, user, LIKERT_SCHEMA)
    return {
        "judge_model": judge.name,
        "parsed":      resp.parsed,
        "raw_text":    resp.raw_text,
        "latency_s":   resp.latency_s,
        "tokens_in":   resp.tokens_in,
        "tokens_out":  resp.tokens_out,
        "error":       resp.error,
    }


def score_one_record(rec: dict, judges: List[JudgeClient]) -> List[dict]:
    """Returns one eval-record per judge for this sample."""
    if not rec.get("parse_ok_cot", False):
        return [
            {**base_eval_record(rec, "law_equivalence", j.name),
             "skipped": True, "skip_reason": "parse_ok_cot=False"}
            for j in judges
        ]
    gt_law   = physical_law_block(load_gt_cot(rec["engine"], rec["experiment"], rec["sample_id"]))
    cand_law = physical_law_block(rec.get("parsed_cot") or {})
    user = _format_user_prompt(gt_law, cand_law)

    judge_results = fan_out(judges, _judge_one, system=SYSTEM_PROMPT, user=user)

    rows = []
    for jr in judge_results:
        row = base_eval_record(rec, "law_equivalence", jr["judge_model"])
        row["raw_response"] = jr["raw_text"]
        row["latency_s"]    = jr["latency_s"]
        row["tokens_in"]    = jr["tokens_in"]
        row["tokens_out"]   = jr["tokens_out"]
        row["judge_error"]  = jr["error"]
        if jr["parsed"]:
            row["scores"] = {
                "name":      jr["parsed"].get("name_score"),
                "statement": jr["parsed"].get("statement_score"),
                "formula":   jr["parsed"].get("formula_score"),
                "overall":   jr["parsed"].get("overall_score"),
            }
            row["justification"] = jr["parsed"].get("justification")
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results",       default="results.jsonl",
                    help="Input results.jsonl from the model under test.")
    ap.add_argument("--out",           default="eval_results.jsonl",
                    help="Output jsonl (appended).")
    ap.add_argument("--limit",         type=int, default=None)
    ap.add_argument("--engines",       nargs="*", default=None)
    ap.add_argument("--experiments",   nargs="*", default=None)
    ap.add_argument("--judges",        nargs="*", default=["openai", "gemini", "grok"])
    ap.add_argument("--bench_root",    default=None)
    args = ap.parse_args()
    if args.bench_root:
        set_bench_root(args.bench_root)

    judge_factory = {"openai": OpenAIJudge, "gemini": GeminiJudge, "grok": GrokJudge}
    judges: List[JudgeClient] = [judge_factory[name]() for name in args.judges]
    print(f"[equivalence] judges = {[j.name for j in judges]}")

    recs = [r for r in read_results(args.results)
            if sample_filter(r, args.experiments, args.engines)]
    if args.limit:
        recs = recs[:args.limit]
    print(f"[equivalence] scoring {len(recs)} records")

    all_rows = []
    for i, rec in enumerate(recs, 1):
        rows = score_one_record(rec, judges)
        all_rows.extend(rows)
        skipped = sum(r["skipped"] for r in rows)
        errors  = sum(bool(r["judge_error"]) for r in rows)
        print(f"  [{i}/{len(recs)}] {rec['engine']}/{rec['experiment']}/{rec['sample_id']} "
              f"-> {len(rows)} rows, {skipped} skipped, {errors} judge errors")

    n = write_jsonl(all_rows, args.out, append=True)
    print(f"[equivalence] wrote {n} rows to {args.out}")


if __name__ == "__main__":
    main()
