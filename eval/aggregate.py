"""Aggregate eval_results.jsonl files into per-model / per-judge / per-experiment
summaries. Reads either a single file (--in) or every model dir under
eval_outputs/ (--root)."""
from __future__ import annotations
import argparse, json, statistics, sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval._common import EVAL_OUT_ROOT


def _mean(xs):   return statistics.fmean(xs) if xs else None
def _median(xs): return statistics.median(xs) if xs else None
def _spread(xs): return (max(xs) - min(xs)) if xs else None


def discover_eval_files(root: Path) -> List[Path]:
    return sorted(root.glob("*/eval_results.jsonl"))


def read_jsonl(path: Path) -> List[dict]:
    return [json.loads(l) for l in open(path) if l.strip()]


def collect(rows: List[dict]) -> List[dict]:
    return rows


# ── Per-model overall report ────────────────────────────────────────────────

def per_model_overall(rows: List[dict], scorer: str) -> str:
    """Mean overall_score per (model, judge) for an LLM scorer."""
    fields = ["name", "statement", "formula", "overall"]
    by: Dict[Tuple[str, str], Dict[str, List[int]]] = defaultdict(lambda: defaultdict(list))
    skip = err = 0
    for r in rows:
        if r["scorer"] != scorer: continue
        if r["skipped"]:    skip += 1; continue
        if r["judge_error"]: err += 1; continue
        if not r.get("scores"): continue
        key = (r["model"], r["judge_model"] or "(none)")
        for f in fields:
            v = r["scores"].get(f)
            if v is not None: by[key][f].append(int(v))

    out = [f"\n=== {scorer} per (model, judge) — skipped={skip}, judge-error={err} ==="]
    out.append(f"  {'model':<25s} {'judge':<22s} {'name':>5s} {'stmt':>5s} {'form':>5s} {'over':>5s}   N")
    for (model, judge), d in sorted(by.items()):
        means = [_mean(d[f]) for f in fields]
        n = len(d.get("overall", []))
        cells = "  ".join(f"{(m if m is not None else float('nan')):5.2f}" for m in means)
        out.append(f"  {model:<25s} {judge:<22s}  {cells}   {n:>4d}")
    return "\n".join(out)


def per_model_runnability(rows: List[dict]) -> str:
    """Per-model runnability rates: syntax_ok, runs_without_error, produces_video_mp4."""
    by: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        if r["scorer"] != "runnability": continue
        if r["skipped"]: continue
        by[r["model"]].append(r.get("scores") or {})
    if not by:
        return "\n=== runnability: no scored rows"
    out = ["\n=== runnability per model ==="]
    out.append(f"  {'model':<25s} {'N':>4s}  {'syntax':>8s} {'runs':>8s} {'video':>8s} "
               f"{'mean_t':>7s} {'timeouts':>9s}")
    for model, ss in sorted(by.items()):
        n = len(ss)
        syn = sum(1 for s in ss if s.get("syntax_ok"))
        run = sum(1 for s in ss if s.get("runs_without_error"))
        vid = sum(1 for s in ss if s.get("produces_video_mp4"))
        ts  = [s.get("wall_time_s") or 0 for s in ss]
        to  = sum(1 for s in ss if s.get("timed_out"))
        mt  = _mean(ts) if ts else 0
        out.append(f"  {model:<25s} {n:>4d}  "
                   f"{syn:>4d}/{n} ({100*syn/n:>4.1f}%)  "
                   f"{run:>4d}/{n} ({100*run/n:>4.1f}%)  "
                   f"{vid:>4d}/{n} ({100*vid/n:>4.1f}%)  "
                   f"{mt:>7.2f}  {to:>9d}")
    return "\n".join(out)


def per_model_codebleu(rows: List[dict]) -> str:
    by: Dict[str, List[float]] = defaultdict(list)
    sub: Dict[str, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r["scorer"] != "codebleu": continue
        if r["skipped"] or r["judge_error"]: continue
        s = r.get("scores") or {}
        if "codebleu" not in s: continue
        by[r["model"]].append(s["codebleu"])
        for k in ("ngram_match_score", "weighted_ngram_match_score",
                  "syntax_match_score", "dataflow_match_score"):
            if k in s: sub[r["model"]][k].append(s[k])
    out = ["\n=== codebleu per model ==="]
    out.append(f"  {'model':<25s} {'mean':>7s} {'median':>7s} {'min':>7s} {'max':>7s}   N    "
               f"({'ngram':>6s} {'wngram':>6s} {'syntax':>6s} {'dflow':>6s})")
    for model, xs in sorted(by.items()):
        sub_means = [_mean(sub[model].get(k, [])) for k in
                     ("ngram_match_score","weighted_ngram_match_score",
                      "syntax_match_score","dataflow_match_score")]
        sub_str = "  ".join(f"{(m if m is not None else 0):5.3f}" for m in sub_means)
        out.append(f"  {model:<25s} {_mean(xs):>7.4f} {_median(xs):>7.4f} {min(xs):>7.4f} "
                   f"{max(xs):>7.4f}   {len(xs):>4d}   ({sub_str})")
    return "\n".join(out)


def disagreement(rows: List[dict], scorer: str) -> str:
    """Spread of overall_score across judges, per (model, sample)."""
    by_key: Dict[Tuple, List[int]] = defaultdict(list)
    for r in rows:
        if r["scorer"] != scorer or r["skipped"] or r["judge_error"]: continue
        v = (r.get("scores") or {}).get("overall")
        if v is None: continue
        key = (r["model"], r["engine"], r["experiment"], r["sample_id"])
        by_key[key].append(int(v))
    spreads: Dict[str, List[int]] = defaultdict(list)
    for key, vs in by_key.items():
        if len(vs) > 1:
            spreads[key[0]].append(_spread(vs))
    out = [f"\n=== {scorer} judge disagreement on overall_score per model ==="]
    out.append(f"  {'model':<25s} {'mean':>5s} {'median':>5s} {'max':>5s}    N")
    for model, vs in sorted(spreads.items()):
        out.append(f"  {model:<25s} {_mean(vs):>5.2f} {_median(vs):>5.2f} {max(vs):>5d}    {len(vs):>4d}")
    return "\n".join(out)


def coverage_table(rows: List[dict]) -> str:
    """Number of distinct samples seen per (model, scorer)."""
    seen: Dict[Tuple[str, str], set] = defaultdict(set)
    skipped: Dict[Tuple[str, str], int] = defaultdict(int)
    for r in rows:
        key = (r["model"], r["scorer"])
        if r["skipped"]:
            skipped[key] += 1
            continue
        if r.get("judge_error"): continue
        seen[key].add((r["engine"], r["experiment"], r["sample_id"]))
    out = ["\n=== coverage (unique samples per scorer) ==="]
    out.append(f"  {'model':<25s} {'scorer':<20s} unique_samples  skipped_rows")
    keys = sorted(set(seen) | set(skipped))
    for k in keys:
        out.append(f"  {k[0]:<25s} {k[1]:<20s} {len(seen.get(k, set())):>14d}  {skipped.get(k, 0):>13d}")
    return "\n".join(out)


def per_experiment(rows: List[dict], scorer: str, model: str | None = None) -> str:
    """Mean overall_score per experiment for one model (or all models)."""
    by: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for r in rows:
        if r["scorer"] != scorer or r["skipped"] or r["judge_error"]: continue
        if model and r["model"] != model: continue
        v = (r.get("scores") or {}).get("overall")
        if v is None: continue
        by[(r["engine"], r["experiment"])].append(int(v))
    if not by: return ""
    out = [f"\n=== {scorer} per experiment" + (f"  (model={model})" if model else "") + " ==="]
    out.append(f"  {'engine':<8s} {'experiment':<45s}  mean   N")
    for (eng, exp), vs in sorted(by.items(), key=lambda kv: _mean(kv[1]) or 0):
        out.append(f"  {eng:<8s} {exp:<45s}  {_mean(vs):>4.2f}   {len(vs):>3d}")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=None,
                    help="Path to a single eval_results.jsonl. Mutually exclusive with --root.")
    ap.add_argument("--root", default=str(EVAL_OUT_ROOT),
                    help="Root dir whose subdirs each contain eval_results.jsonl.")
    ap.add_argument("--per_experiment_for", default=None,
                    help="If set, print a per-experiment breakdown for this model.")
    args = ap.parse_args()

    rows: List[dict] = []
    if args.inp:
        rows = read_jsonl(Path(args.inp))
        print(f"loaded {len(rows)} rows from {args.inp}")
    else:
        files = discover_eval_files(Path(args.root))
        for f in files:
            rs = read_jsonl(f)
            print(f"  + {f}  ({len(rs)} rows)")
            rows.extend(rs)
        print(f"loaded {len(rows)} rows total from {len(files)} files under {args.root}")

    if not rows:
        print("no rows; nothing to aggregate.")
        return

    print(coverage_table(rows))
    print(per_model_overall(rows, "law_equivalence"))
    print(per_model_overall(rows, "law_validity"))
    print(disagreement(rows, "law_equivalence"))
    print(disagreement(rows, "law_validity"))
    print(per_model_codebleu(rows))
    print(per_model_runnability(rows))
    if args.per_experiment_for:
        print(per_experiment(rows, "law_equivalence", model=args.per_experiment_for))


if __name__ == "__main__":
    main()
