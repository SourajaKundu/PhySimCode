"""Generate a per-model markdown report under eval_outputs/<model>/REPORT.md.

Usage:
    python eval/make_model_report.py <model_name> [--out PATH]

Reads:
    inference_outputs/<model>/results.jsonl              (canonical inference)
    inference_outputs/<model>/results_recovered.jsonl    (optional, post-CoT-recovery)
    eval_outputs/<model>/eval_results.jsonl              (full eval rows)

Writes:
    eval_outputs/<model>/REPORT.md
"""
from __future__ import annotations
import argparse, json, os, statistics, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


# Pricing per 1M tokens (input, output) for cost attribution
PRICE = {
    "gpt-5-nano":       (0.05, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "grok-4-1-fast":    (0.20, 0.50),
    "grok-4-fast":      (0.20, 0.50),
}

LAW_FIELDS = ["name", "statement", "formula", "overall"]
LAW_FIELD_LABELS = {"name": "name", "statement": "statement",
                    "formula": "formula", "overall": "overall"}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists(): return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except json.JSONDecodeError: pass
    return out


def fmt(x, w=6, p=2):
    if x is None: return "-".rjust(w)
    if isinstance(x, float): return f"{x:.{p}f}".rjust(w)
    return str(x).rjust(w)


def section_law(rows, scorer_name):
    """Build per-judge mean table + cross-judge mean for a law scorer."""
    eligible = [r for r in rows if r.get("scorer") == scorer_name
                and not r.get("skipped") and not r.get("judge_error")
                and r.get("scores")]
    if not eligible:
        return None, []

    judges = sorted({r["judge_model"] for r in eligible})
    out_per = {}                          # judge -> {field: mean, "N": n}
    out_per_field_avg = {}                # field -> mean across all (sample, judge) pairs

    for judge in judges:
        sub = [r for r in eligible if r["judge_model"] == judge]
        per_field = {}
        for f in LAW_FIELDS:
            vals = [r["scores"].get(f) for r in sub if r["scores"].get(f) is not None]
            per_field[f] = statistics.fmean(vals) if vals else None
        out_per[judge] = {**per_field, "N": len(sub)}

    # Per-sample average across the 3 judges, then mean across samples
    by_sample_judge = defaultdict(dict)
    for r in eligible:
        key = (r["engine"], r["experiment"], r["sample_id"])
        by_sample_judge[key][r["judge_model"]] = r["scores"]
    for f in LAW_FIELDS:
        per_sample_means = []
        for sj in by_sample_judge.values():
            vs = [s.get(f) for s in sj.values() if s.get(f) is not None]
            if vs: per_sample_means.append(statistics.fmean(vs))
        out_per_field_avg[f] = statistics.fmean(per_sample_means) if per_sample_means else None

    return out_per, out_per_field_avg


def section_codebleu(rows):
    sub = [r for r in rows if r["scorer"] == "codebleu"
           and not r.get("skipped") and r.get("scores")]
    if not sub: return None
    fields = ["codebleu", "ngram_match_score", "weighted_ngram_match_score",
              "syntax_match_score", "dataflow_match_score"]
    out = {"N": len(sub)}
    for f in fields:
        vals = [r["scores"].get(f) for r in sub if r["scores"].get(f) is not None]
        out[f] = (statistics.fmean(vals), statistics.median(vals),
                  min(vals), max(vals)) if vals else None
    return out


def section_runnability(rows):
    sub = [r for r in rows if r["scorer"] == "runnability" and not r.get("skipped")]
    if not sub: return None
    n = len(sub)
    syn = sum(1 for r in sub if (r.get("scores") or {}).get("syntax_ok"))
    run = sum(1 for r in sub if (r.get("scores") or {}).get("runs_without_error"))
    vid = sum(1 for r in sub if (r.get("scores") or {}).get("produces_video_mp4"))
    to  = sum(1 for r in sub if (r.get("scores") or {}).get("timed_out"))
    times = [(r.get("scores") or {}).get("wall_time_s") for r in sub
             if (r.get("scores") or {}).get("wall_time_s") is not None]
    return {
        "N": n,
        "syntax_ok": syn,
        "runs_without_error": run,
        "produces_video_mp4": vid,
        "timed_out": to,
        "wall_median_s": statistics.median(times) if times else None,
        "wall_mean_s": statistics.fmean(times) if times else None,
        "wall_max_s": max(times) if times else None,
    }


def section_runnability_by_engine(rows):
    out = {}
    for eng in ("scipy", "kubric"):
        sub = [r for r in rows if r["scorer"] == "runnability"
               and r.get("engine") == eng and not r.get("skipped")]
        if not sub: continue
        n = len(sub)
        out[eng] = {
            "N": n,
            "syntax_ok": sum(1 for r in sub if (r.get("scores") or {}).get("syntax_ok")),
            "runs": sum(1 for r in sub if (r.get("scores") or {}).get("runs_without_error")),
            "video": sum(1 for r in sub if (r.get("scores") or {}).get("produces_video_mp4")),
            "timed_out": sum(1 for r in sub if (r.get("scores") or {}).get("timed_out")),
        }
    return out


def section_parse(inf_orig, inf_recov):
    """Inference parsability stats — original and post-recovery."""
    n = len(inf_orig)
    out = {"total": n}
    out["orig_cot_ok"] = sum(1 for r in inf_orig if r.get("parse_ok_cot"))
    out["orig_code_ok"] = sum(1 for r in inf_orig if r.get("parse_ok_code"))
    out["orig_both_ok"] = sum(1 for r in inf_orig if r.get("parse_ok_cot") and r.get("parse_ok_code"))
    out["orig_neither"] = sum(1 for r in inf_orig if not r.get("parse_ok_cot") and not r.get("parse_ok_code"))
    if inf_recov:
        out["recov_cot_ok"] = sum(1 for r in inf_recov if r.get("parse_ok_cot"))
        out["recov_code_ok"] = sum(1 for r in inf_recov if r.get("parse_ok_code"))
        out["rescued"] = out["recov_cot_ok"] - out["orig_cot_ok"]
    return out


def section_coverage(eval_rows):
    out = {}
    skip_matrix = Counter()
    for r in eval_rows:
        if r.get("skipped"):
            skip_matrix[(r.get("scorer"), r.get("skip_reason"))] += 1
    out["skip_matrix"] = skip_matrix

    err_matrix = Counter()
    for r in eval_rows:
        if r.get("judge_error"):
            err_matrix[(r.get("scorer"), r.get("judge_model"))] += 1
    out["err_matrix"] = err_matrix

    coverage = {}
    for sc in ("law_equivalence", "law_validity", "codebleu", "runnability"):
        sub = [r for r in eval_rows if r.get("scorer") == sc]
        unique = {(r["engine"], r["experiment"], r["sample_id"]) for r in sub
                  if not r.get("skipped")}
        skipped_unique = {(r["engine"], r["experiment"], r["sample_id"]) for r in sub
                          if r.get("skipped")}
        coverage[sc] = {
            "rows": len(sub),
            "unique_samples": len(unique),
            "skipped_samples": len(skipped_unique),
        }
    out["coverage"] = coverage
    return out


def section_judge_disagreement(rows, scorer_name):
    """Mean and median spread of overall across judges per sample."""
    eligible = [r for r in rows if r["scorer"] == scorer_name
                and not r.get("skipped") and not r.get("judge_error")
                and r.get("scores")]
    by_sample = defaultdict(list)
    for r in eligible:
        key = (r["engine"], r["experiment"], r["sample_id"])
        sc = r["scores"].get("overall")
        if sc is not None:
            by_sample[key].append(sc)
    spreads = [max(v) - min(v) for v in by_sample.values() if len(v) >= 2]
    if not spreads: return None
    return {
        "mean": statistics.fmean(spreads),
        "median": statistics.median(spreads),
        "max": max(spreads),
        "N": len(spreads),
    }


def section_cost(eval_rows):
    by_judge = defaultdict(lambda: {"N": 0, "tok_in": 0, "tok_out": 0, "cost": 0.0,
                                    "lat_total": 0.0})
    for r in eval_rows:
        j = r.get("judge_model")
        if not j or j not in PRICE: continue
        ti = int(r.get("tokens_in") or 0)
        to = int(r.get("tokens_out") or 0)
        ip, op = PRICE[j]
        by_judge[j]["N"] += 1
        by_judge[j]["tok_in"] += ti
        by_judge[j]["tok_out"] += to
        by_judge[j]["cost"] += (ti * ip + to * op) / 1e6
        by_judge[j]["lat_total"] += float(r.get("latency_s") or 0)
    return dict(by_judge)


def section_truncation_analysis(inf_orig, inf_recov):
    """Look at the still-failed rows post-recovery and characterize them."""
    if not inf_recov: return None
    failed_keys = {(r["engine"], r["experiment"], r["sample_id"])
                   for r in inf_recov if not r.get("parse_ok_cot")}
    orig_by_key = {(r["engine"], r["experiment"], r["sample_id"]): r for r in inf_orig}
    failed = [orig_by_key[k] for k in failed_keys if k in orig_by_key]
    if not failed: return None

    parse_errs = Counter(r.get("parse_error") or "(none)" for r in failed)
    api_err = sum(1 for r in failed if (r.get("parse_error") or "").startswith("no output"))
    parse_failed = len(failed) - api_err

    # Length stats for the parse_failed (truncation candidates)
    trunc = [r for r in failed if (r.get("parse_error") or "") and not (r.get("parse_error") or "").startswith("no output")]
    lens = [len(r.get("raw_output") or "") for r in trunc]

    # Endings
    endings = Counter()
    for r in trunc:
        raw = (r.get("raw_output") or "")[-80:].replace("\n", "\\n")
        endings[raw[:60]] += 1

    # Engine breakdown
    by_eng = Counter(r["engine"] for r in failed)
    by_exp = Counter(r["experiment"] for r in failed)

    # How many of CoT-failed nonetheless have a parseable code block
    code_ok = sum(1 for r in failed if r.get("parse_ok_code"))

    return {
        "n_failed": len(failed),
        "api_errors": api_err,
        "parse_errors": parse_failed,
        "len_stats": {
            "min": min(lens) if lens else None,
            "median": statistics.median(lens) if lens else None,
            "mean": statistics.fmean(lens) if lens else None,
            "max": max(lens) if lens else None,
        },
        "by_engine": dict(by_eng),
        "top_experiments": by_exp.most_common(10),
        "code_still_ok": code_ok,
        "common_endings": endings.most_common(5),
        "parse_error_kinds": parse_errs.most_common(5),
    }


# ---------- Markdown writers ----------

def md_table(rows, headers, aligns=None):
    """rows = list of lists, headers = list of strings.
    aligns = list of 'l'/'r'/'c' for each column."""
    aligns = aligns or ["l"] * len(headers)
    sep = ["---"] * len(headers)
    for i, a in enumerate(aligns):
        if a == "r": sep[i] = "---:"
        elif a == "c": sep[i] = ":---:"
    lines = ["| " + " | ".join(str(h) for h in headers) + " |"]
    lines.append("| " + " | ".join(sep) + " |")
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


def render_report(model: str, parse_stats, eq_per, eq_avg, val_per, val_avg,
                  cb, run, run_by_eng, cov, eq_dis, val_dis, cost, trunc) -> str:
    out = []
    out.append(f"# {model} — eval report")
    out.append("")
    out.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    out.append("")

    # ---------- Headline ----------
    out.append("## Headline")
    out.append("")
    eq_overall = eq_avg.get("overall") if eq_avg else None
    val_overall = val_avg.get("overall") if val_avg else None
    cb_total = cb["codebleu"][0] if cb else None
    run_pct = (100*run["runs_without_error"]/run["N"]) if run else None
    vid_pct = (100*run["produces_video_mp4"]/run["N"]) if run else None
    head_rows = [
        ["Equivalence (mean overall, all judges)", fmt(eq_overall)],
        ["Validity (mean overall, all judges)", fmt(val_overall)],
        ["CodeBLEU total (mean)", fmt(cb_total, p=3)],
        ["Runnability — runs_without_error", f"{run['runs_without_error']}/{run['N']} ({run_pct:.1f}%)" if run else "-"],
        ["Runnability — produces_video_mp4", f"{run['produces_video_mp4']}/{run['N']} ({vid_pct:.1f}%)" if run else "-"],
        ["Total cost (judge tokens)", f"${sum(c['cost'] for c in cost.values()):.2f}" if cost else "-"],
    ]
    out.append(md_table(head_rows, ["metric", "value"], ["l", "r"]))
    out.append("")

    # ---------- Law Equivalence ----------
    out.append("## Law Equivalence")
    out.append("")
    out.append("Likert 0–4 scoring of model-generated physics laws against ground truth (judge sees both).")
    out.append("")
    if eq_per:
        eq_rows = []
        for judge in sorted(eq_per.keys()):
            d = eq_per[judge]
            eq_rows.append([
                judge,
                fmt(d["name"]), fmt(d["statement"]),
                fmt(d["formula"]), fmt(d["overall"]),
                d["N"]
            ])
        eq_rows.append([
            "**average across judges**",
            f"**{fmt(eq_avg['name']).strip()}**",
            f"**{fmt(eq_avg['statement']).strip()}**",
            f"**{fmt(eq_avg['formula']).strip()}**",
            f"**{fmt(eq_avg['overall']).strip()}**",
            "—",
        ])
        out.append(md_table(eq_rows, ["judge", "name", "statement", "formula", "overall", "N"],
                            ["l", "r", "r", "r", "r", "r"]))
    else:
        out.append("_No law_equivalence rows scored._")
    out.append("")

    if eq_dis:
        out.append("**Judge disagreement on `overall`**: mean spread = "
                   f"{eq_dis['mean']:.2f}, median = {eq_dis['median']:.0f}, "
                   f"max = {eq_dis['max']}, N = {eq_dis['N']} samples")
        out.append("")

    # ---------- Law Validity ----------
    out.append("## Law Validity")
    out.append("")
    out.append("Likert 0–4 plausibility of the law on its own (judge does NOT see ground truth).")
    out.append("")
    if val_per:
        val_rows = []
        for judge in sorted(val_per.keys()):
            d = val_per[judge]
            val_rows.append([
                judge,
                fmt(d["name"]), fmt(d["statement"]),
                fmt(d["formula"]), fmt(d["overall"]),
                d["N"]
            ])
        val_rows.append([
            "**average across judges**",
            f"**{fmt(val_avg['name']).strip()}**",
            f"**{fmt(val_avg['statement']).strip()}**",
            f"**{fmt(val_avg['formula']).strip()}**",
            f"**{fmt(val_avg['overall']).strip()}**",
            "—",
        ])
        out.append(md_table(val_rows, ["judge", "name", "statement", "formula", "overall", "N"],
                            ["l", "r", "r", "r", "r", "r"]))
    else:
        out.append("_No law_validity rows scored._")
    out.append("")

    if val_dis:
        out.append("**Judge disagreement on `overall`**: mean spread = "
                   f"{val_dis['mean']:.2f}, median = {val_dis['median']:.0f}, "
                   f"max = {val_dis['max']}, N = {val_dis['N']} samples")
        out.append("")

    if eq_overall is not None and val_overall is not None:
        out.append(f"**Validity − Equivalence gap on overall**: {val_overall - eq_overall:.2f}  "
                   f"(higher gap means the model often produces *plausible* laws that aren't *correct* — "
                   "a signature of confident hallucination)")
        out.append("")

    # ---------- CodeBLEU ----------
    out.append("## CodeBLEU (4 sub-metrics)")
    out.append("")
    if cb:
        cb_rows = []
        for f, label in [("codebleu", "**total codebleu**"),
                         ("ngram_match_score", "ngram_match"),
                         ("weighted_ngram_match_score", "weighted_ngram"),
                         ("syntax_match_score", "syntax_match"),
                         ("dataflow_match_score", "dataflow_match")]:
            v = cb.get(f)
            if v is None: continue
            mean, med, mn, mx = v
            cb_rows.append([label,
                            f"{mean:.4f}", f"{med:.4f}",
                            f"{mn:.4f}", f"{mx:.4f}"])
        out.append(md_table(cb_rows, ["sub-metric", "mean", "median", "min", "max"],
                            ["l", "r", "r", "r", "r"]))
        out.append(f"\nN = {cb['N']} samples scored")
    else:
        out.append("_No codebleu rows scored._")
    out.append("")

    # ---------- Runnability ----------
    out.append("## Runnability")
    out.append("")
    if run:
        n = run["N"]
        run_rows = [
            ["syntax_ok",            f"{run['syntax_ok']}/{n}",            f"{100*run['syntax_ok']/n:.1f}%"],
            ["runs_without_error",   f"{run['runs_without_error']}/{n}",   f"{100*run['runs_without_error']/n:.1f}%"],
            ["produces_video_mp4",   f"{run['produces_video_mp4']}/{n}",   f"{100*run['produces_video_mp4']/n:.1f}%"],
            ["timed_out (60s)",      f"{run['timed_out']}/{n}",            f"{100*run['timed_out']/n:.1f}%"],
        ]
        out.append(md_table(run_rows, ["signal", "count", "rate"], ["l", "r", "r"]))
        out.append("")
        out.append(f"Wall time per run: median = {run['wall_median_s']:.2f}s, "
                   f"mean = {run['wall_mean_s']:.2f}s, max = {run['wall_max_s']:.2f}s")
        out.append("")

    if run_by_eng:
        out.append("### By engine")
        out.append("")
        rows = []
        for eng, d in run_by_eng.items():
            n = d["N"]
            rows.append([
                eng, n,
                f"{d['syntax_ok']}/{n} ({100*d['syntax_ok']/n:.1f}%)",
                f"{d['runs']}/{n} ({100*d['runs']/n:.1f}%)",
                f"{d['video']}/{n} ({100*d['video']/n:.1f}%)",
                f"{d['timed_out']}/{n}",
            ])
        out.append(md_table(rows, ["engine", "N", "syntax_ok", "runs", "video", "timeouts"],
                            ["l", "r", "r", "r", "r", "r"]))
        out.append("")

    # ---------- Parse stats ----------
    out.append("## Inference parsability")
    out.append("")
    out.append("Stats from the upstream `inference_outputs/<model>/` files (these gate which rows the eval can score).")
    out.append("")
    n = parse_stats["total"]
    rows = [
        ["Total inference rows", n, "100.0%"],
        ["parse_ok_cot=True (original)",
         parse_stats["orig_cot_ok"],
         f"{100*parse_stats['orig_cot_ok']/n:.1f}%"],
        ["parse_ok_code=True (original)",
         parse_stats["orig_code_ok"],
         f"{100*parse_stats['orig_code_ok']/n:.1f}%"],
        ["parse_ok_cot AND parse_ok_code (original)",
         parse_stats["orig_both_ok"],
         f"{100*parse_stats['orig_both_ok']/n:.1f}%"],
        ["parse_ok_cot=False AND parse_ok_code=False (original)",
         parse_stats["orig_neither"],
         f"{100*parse_stats['orig_neither']/n:.1f}%"],
    ]
    if "recov_cot_ok" in parse_stats:
        rows.append([
            "**parse_ok_cot=True (after recovery)**",
            f"**{parse_stats['recov_cot_ok']}**",
            f"**{100*parse_stats['recov_cot_ok']/n:.1f}%**",
        ])
        rows.append([
            "rows rescued by recovery script",
            parse_stats["rescued"],
            f"+{100*parse_stats['rescued']/n:.1f} pp",
        ])
    out.append(md_table(rows, ["metric", "count", "rate"], ["l", "r", "r"]))
    out.append("")

    # ---------- Coverage / skip analysis ----------
    out.append("## Coverage and skip analysis")
    out.append("")
    if cov.get("coverage"):
        cov_rows = []
        for sc, d in cov["coverage"].items():
            cov_rows.append([
                sc,
                d["rows"],
                d["unique_samples"],
                d["skipped_samples"],
            ])
        out.append(md_table(cov_rows,
                            ["scorer", "total rows", "unique samples scored", "skipped samples"],
                            ["l", "r", "r", "r"]))
        out.append("")

    if cov.get("skip_matrix"):
        out.append("### Skip reasons by scorer")
        out.append("")
        rows = []
        for (sc, rsn), n in sorted(cov["skip_matrix"].items(), key=lambda x: -x[1]):
            rows.append([sc, rsn, n])
        out.append(md_table(rows, ["scorer", "skip_reason", "count"], ["l", "l", "r"]))
        out.append("")

    if cov.get("err_matrix") and sum(cov["err_matrix"].values()) > 0:
        out.append("### Judge errors")
        out.append("")
        rows = []
        for (sc, judge), n in sorted(cov["err_matrix"].items(), key=lambda x: -x[1]):
            rows.append([sc, judge, n])
        out.append(md_table(rows, ["scorer", "judge", "count"], ["l", "l", "r"]))
        out.append("")

    # ---------- Truncation deep dive ----------
    if trunc and trunc["n_failed"] > 0:
        out.append("## Why CoT parsing failed (deep dive)")
        out.append("")
        out.append(f"After recovery, {trunc['n_failed']} input rows still have `parse_ok_cot=False`. Breakdown:")
        out.append("")
        bd = [
            ["API errors (no output at all)", trunc["api_errors"]],
            ["Parse failures (output present, malformed)", trunc["parse_errors"]],
            ["Of the failed, still have parseable code block", trunc["code_still_ok"]],
        ]
        out.append(md_table(bd, ["category", "count"], ["l", "r"]))
        out.append("")

        if trunc["len_stats"]["max"]:
            ls = trunc["len_stats"]
            out.append(f"**Output lengths of parse-failed rows**: "
                       f"min={ls['min']}, median={ls['median']:.0f}, "
                       f"mean={ls['mean']:.0f}, max={ls['max']}")
            out.append("")

        if trunc["common_endings"]:
            out.append("**Most common endings of failed responses** (top 5, last 60 chars):")
            out.append("")
            for end, n in trunc["common_endings"]:
                out.append(f"- `{n}` rows ending with: `...{end}`")
            out.append("")

        if trunc["by_engine"]:
            eng_rows = [[k, v] for k, v in trunc["by_engine"].items()]
            out.append("**By engine**:")
            out.append("")
            out.append(md_table(eng_rows, ["engine", "failed"], ["l", "r"]))
            out.append("")

        if trunc["top_experiments"]:
            out.append("**Top experiments with CoT failures**:")
            out.append("")
            ex_rows = [[k, v] for k, v in trunc["top_experiments"]]
            out.append(md_table(ex_rows, ["experiment", "failed"], ["l", "r"]))
            out.append("")

    # ---------- Cost ----------
    if cost:
        out.append("## Judge cost breakdown")
        out.append("")
        rows = []
        for j in sorted(cost.keys()):
            d = cost[j]
            rows.append([
                j, d["N"], d["tok_in"], d["tok_out"],
                f"${d['cost']:.4f}",
                f"{d['lat_total']/d['N']:.2f}s",
            ])
        rows.append([
            "**total**",
            sum(d["N"] for d in cost.values()),
            sum(d["tok_in"] for d in cost.values()),
            sum(d["tok_out"] for d in cost.values()),
            f"**${sum(d['cost'] for d in cost.values()):.4f}**",
            "—",
        ])
        out.append(md_table(rows, ["judge", "calls", "tok_in", "tok_out", "cost", "avg latency"],
                            ["l", "r", "r", "r", "r", "r"]))
        out.append("")

    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--root", default=".")
    ap.add_argument("--inference_root", default=None,
                    help="override root containing <model>/results*.jsonl")
    ap.add_argument("--eval_root", default=None,
                    help="override root containing <model>/eval_results.jsonl")
    ap.add_argument("--out", default=None,
                    help="output path; default eval_outputs/<model>/REPORT.md")
    args = ap.parse_args()

    root = Path(args.root)
    inf_dir = (Path(args.inference_root) / args.model) if args.inference_root else (root / "inference_outputs" / args.model)
    eval_dir = (Path(args.eval_root) / args.model) if args.eval_root else (root / "eval_outputs" / args.model)
    inf_path = inf_dir / "results.jsonl"
    inf_recov_path = inf_dir / "results_recovered.jsonl"
    eval_path = eval_dir / "eval_results.jsonl"

    if not inf_path.exists():
        sys.exit(f"missing {inf_path}")
    if not eval_path.exists():
        sys.exit(f"missing {eval_path}")

    inf_orig = load_jsonl(inf_path)
    inf_recov = load_jsonl(inf_recov_path) if inf_recov_path.exists() else []
    eval_rows = load_jsonl(eval_path)

    parse_stats = section_parse(inf_orig, inf_recov)
    eq_per, eq_avg = section_law(eval_rows, "law_equivalence")
    val_per, val_avg = section_law(eval_rows, "law_validity")
    cb = section_codebleu(eval_rows)
    run = section_runnability(eval_rows)
    run_by_eng = section_runnability_by_engine(eval_rows)
    cov = section_coverage(eval_rows)
    eq_dis = section_judge_disagreement(eval_rows, "law_equivalence")
    val_dis = section_judge_disagreement(eval_rows, "law_validity")
    cost = section_cost(eval_rows)
    trunc = section_truncation_analysis(inf_orig, inf_recov)

    md = render_report(args.model, parse_stats, eq_per, eq_avg, val_per, val_avg,
                       cb, run, run_by_eng, cov, eq_dis, val_dis, cost, trunc)

    out_path = Path(args.out) if args.out else (eval_dir / "REPORT.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(md)
    print(f"wrote {out_path} ({len(md):,} chars)")


if __name__ == "__main__":
    main()
