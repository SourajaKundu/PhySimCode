"""Replicate the paper's per-model code-generation table, split by engine
(scipy vs kubric).

Columns replicated (parameter-estimation accuracy is computed separately):
  CoT %       parse_ok_cot=True (after recovery) / total inference rows
  Code %      parse_ok_code=True (original)      / total inference rows
  Compile %   runnability.syntax_ok=True         / total inference rows
  No Err %    runnability.runs_without_error     / total inference rows
  Video %     runnability.produces_video_mp4     / total inference rows
  CodeBLEU    mean of codebleu.total_codebleu across non-skipped rows

Skipped scorer rows count as failures for Compile/No Err/Video (denominator =
inference-total, matching the paper table's 2430-based numbers).
"""
import json
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent.parent

OPEN = ["qwen3vl_30b_a3b", "internvl3_5_30b_a3b", "gemma_3_12b_it",
        "glm_4_1v_9b_thinking", "pixtral_12b"]
CLOSED = ["gpt_5_mini", "gemini_2_5_pro", "claude_sonnet_4_6",
          "grok_4_fast_reasoning", "nova_2_lite"]
PRETTY = {
    "qwen3vl_30b_a3b": r"\textsc{Qwen3-VL-30B-A3B-Instruct}",
    "internvl3_5_30b_a3b": r"\textsc{InternVL3.5-30B-A3B}",
    "gemma_3_12b_it": r"\textsc{Gemma-3-12B-IT}",
    "glm_4_1v_9b_thinking": r"\textsc{GLM-4.1V-9B-Thinking}",
    "pixtral_12b": r"\textsc{Pixtral-12B-2409}",
    "gpt_5_mini": r"\textsc{GPT-5 Mini}",
    "gemini_2_5_pro": r"\textsc{Gemini 2.5 Pro}",
    "claude_sonnet_4_6": r"\textsc{Claude Sonnet 4.6}",
    "grok_4_fast_reasoning": r"\textsc{Grok 4 Fast Reasoning}",
    "nova_2_lite": r"\textsc{Nova 2 Lite}",
}

# Add your own model's folder name (under inference_outputs/) to OPEN or CLOSED.
# Models without inference_outputs/<model>/results.jsonl are skipped.
OPEN = [m for m in OPEN if (ROOT / "inference_outputs" / m / "results.jsonl").exists()]
CLOSED = [m for m in CLOSED if (ROOT / "inference_outputs" / m / "results.jsonl").exists()]


def load_inference(model):
    """Returns list of dicts, one per inference row; recovered supersedes orig
    for parse_ok_cot (matches make_model_report.py behavior)."""
    orig_path = ROOT / "inference_outputs" / model / "results.jsonl"
    rec_path = ROOT / "inference_outputs" / model / "results_recovered.jsonl"
    orig = [json.loads(l) for l in open(orig_path)]
    if rec_path.exists():
        rec_by_key = {}
        for l in open(rec_path):
            d = json.loads(l)
            k = (d["engine"], d["experiment"], d["sample_id"])
            rec_by_key[k] = d
        merged = []
        for d in orig:
            k = (d["engine"], d["experiment"], d["sample_id"])
            r = rec_by_key.get(k)
            if r is not None:
                d = dict(d)
                d["parse_ok_cot"] = r.get("parse_ok_cot", d.get("parse_ok_cot"))
            merged.append(d)
        return orig, merged
    return orig, orig


def load_eval(model):
    path = ROOT / "eval_outputs" / model / "eval_results.jsonl"
    rows = [json.loads(l) for l in open(path)]
    return rows


def per_engine_stats(model):
    inf_orig, inf_recov = load_inference(model)
    ev = load_eval(model)

    out = {}
    for eng in ("scipy", "kubric"):
        inf_e_o = [r for r in inf_orig if r.get("engine") == eng]
        inf_e_r = [r for r in inf_recov if r.get("engine") == eng]
        n_inf = len(inf_e_o)

        cot = sum(1 for r in inf_e_r if r.get("parse_ok_cot"))
        code = sum(1 for r in inf_e_o if r.get("parse_ok_code"))

        run_rows = [r for r in ev if r.get("scorer") == "runnability"
                    and r.get("engine") == eng and not r.get("skipped")]
        comp = sum(1 for r in run_rows if (r.get("scores") or {}).get("syntax_ok"))
        noerr = sum(1 for r in run_rows if (r.get("scores") or {}).get("runs_without_error"))
        video = sum(1 for r in run_rows if (r.get("scores") or {}).get("produces_video_mp4"))

        cb_rows = [r for r in ev if r.get("scorer") == "codebleu"
                   and r.get("engine") == eng and not r.get("skipped")]
        cb_vals = [(r.get("scores") or {}).get("codebleu") for r in cb_rows]
        cb_vals = [v for v in cb_vals if v is not None]
        cb_mean = mean(cb_vals) if cb_vals else float("nan")

        out[eng] = dict(N=n_inf, cot=cot, code=code,
                        compile=comp, noerr=noerr, video=video,
                        codebleu=cb_mean)
    return out


def fmt_pct(num, den):
    return f"{100.0 * num / den:.1f}\\%" if den else "--"


def fmt_bleu(v):
    return f"{v:.3f}" if v == v else "--"  # NaN check


def build_row(model, stats, best_by_metric, engine):
    s = stats[engine]
    parts = [PRETTY.get(model, model.replace("_", r"\_"))]
    for key, den in [("cot", s["N"]), ("code", s["N"]),
                     ("compile", s["N"]), ("noerr", s["N"]),
                     ("video", s["N"])]:
        pct = 100.0 * s[key] / s["N"] if s["N"] else 0.0
        val = fmt_pct(s[key], s["N"])
        # bold if this is the best pct in its group for this metric
        if best_by_metric and best_by_metric.get(key) == (model, engine):
            val = r"\textbf{" + val + "}"
        parts.append(val)
    bleu = s["codebleu"]
    val = fmt_bleu(bleu)
    if best_by_metric and best_by_metric.get("codebleu") == (model, engine):
        val = r"\textbf{" + val + "}"
    parts.append(val)
    return " & ".join(parts) + r" \\"


def find_best_within_group(all_stats, models, engine):
    """Return {metric: (model, engine)} for best within a (group, engine)."""
    best = {}
    for key in ("cot", "code", "compile", "noerr", "video"):
        rated = [(100.0 * all_stats[m][engine][key] / all_stats[m][engine]["N"], m)
                 for m in models if all_stats[m][engine]["N"]]
        if rated:
            _, m = max(rated)
            best[key] = (m, engine)
    rated = [(all_stats[m][engine]["codebleu"], m) for m in models
             if all_stats[m][engine]["codebleu"] == all_stats[m][engine]["codebleu"]]
    if rated:
        _, m = max(rated)
        best["codebleu"] = (m, engine)
    return best


HEADER = (r"""
\begin{table*}[t]
\centering
\footnotesize
\setlength{\tabcolsep}{0.35em}
\caption{Code-generation quality split by simulation engine (Scipy vs.\ Kubric). Percentages
computed against total inference attempts (skipped-scorer rows counted as failures);
CodeBLEU is the mean over non-skipped rows. Best within (group, engine) in bold.
`Param.\ Estimation Acc.' from the original table is not derivable from the checked-in
scoring pipeline and is omitted here.}
\label{tab:codegen_per_engine}
\begin{adjustbox}{width=\linewidth}
\begin{tabular}{l|cccccc|cccccc}
\toprule
& \multicolumn{6}{c|}{\textbf{Scipy}} & \multicolumn{6}{c}{\textbf{Kubric}} \\
\textbf{Model}
 & CoT & Code & Compile & No Err. & Video & CodeBLEU
 & CoT & Code & Compile & No Err. & Video & CodeBLEU \\
\midrule
""".rstrip())

FOOTER = r"""
\bottomrule
\end{tabular}
\end{adjustbox}
\end{table*}
"""


def build_row_pair(model, stats, best_scipy, best_kubric):
    s_sc = stats["scipy"]; s_ku = stats["kubric"]
    cells = [PRETTY.get(model, model.replace("_", r"\_"))]
    def val(key, s, best, m):
        if key == "codebleu":
            v = fmt_bleu(s["codebleu"])
        else:
            v = fmt_pct(s[key], s["N"])
        if best.get(key, (None, None))[0] == m:
            v = r"\textbf{" + v + "}"
        return v
    for key in ("cot", "code", "compile", "noerr", "video", "codebleu"):
        cells.append(val(key, s_sc, best_scipy, model))
    for key in ("cot", "code", "compile", "noerr", "video", "codebleu"):
        cells.append(val(key, s_ku, best_kubric, model))
    return " & ".join(cells) + r" \\"


def main():
    all_stats = {m: per_engine_stats(m) for m in OPEN + CLOSED}

    # Best per (group, engine) — restricted to models in the group
    best = {}
    for group in ("open", "closed"):
        models = OPEN if group == "open" else CLOSED
        best[(group, "scipy")] = find_best_within_group(all_stats, models, "scipy")
        best[(group, "kubric")] = find_best_within_group(all_stats, models, "kubric")

    lines = [HEADER]
    lines.append(r"\rowcolor{Gray} \multicolumn{13}{l}{\textit{Open-source models}} \\")
    for m in OPEN:
        lines.append(build_row_pair(m, all_stats[m],
                                     best[("open", "scipy")],
                                     best[("open", "kubric")]))
    lines.append(r"\midrule")
    lines.append(r"\rowcolor{Gray} \multicolumn{13}{l}{\textit{Closed-source models}} \\")
    for m in CLOSED:
        lines.append(build_row_pair(m, all_stats[m],
                                     best[("closed", "scipy")],
                                     best[("closed", "kubric")]))
    lines.append(FOOTER)

    tex = "\n".join(lines)
    out = ROOT / "eval_outputs" / "_tables" / "codegen_per_engine.tex"
    out.parent.mkdir(exist_ok=True)
    out.write_text(tex)

    # Also print human-readable + save CSV
    print(tex)
    print()

    import csv
    csv_path = out.with_suffix(".csv")
    with open(csv_path, "w") as f:
        w = csv.writer(f)
        w.writerow(["model", "engine", "N",
                    "cot%", "code%", "compile%", "no_err%", "video%", "codebleu"])
        for m in OPEN + CLOSED:
            for eng in ("scipy", "kubric"):
                s = all_stats[m][eng]
                N = s["N"] or 1
                w.writerow([m, eng, s["N"],
                            f"{100*s['cot']/N:.2f}",
                            f"{100*s['code']/N:.2f}",
                            f"{100*s['compile']/N:.2f}",
                            f"{100*s['noerr']/N:.2f}",
                            f"{100*s['video']/N:.2f}",
                            f"{s['codebleu']:.4f}" if s['codebleu'] == s['codebleu'] else ""])
    print(f"Wrote {out}\nWrote {csv_path}")


if __name__ == "__main__":
    main()
