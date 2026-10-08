"""Inter-judge agreement (Cohen / Fleiss kappa) per evaluated model.

For each (scorer, field) combination — 2 scorers × 4 fields = 8 properties —
computes pairwise quadratic-weighted Cohen's kappa between the 3 judges
(gpt-5-nano, gemini-2.5-flash, grok-4-1-fast) plus Fleiss' kappa across all 3.

Adapted from the reference likert_kappa_analysis.py — same statistical
methodology, adapted for our schema:
  - item_key = (engine, experiment, sample_id)
  - properties = 8 (scorer × field)
  - scale = 0-4 (Likert)

Inputs:   eval_outputs/<model>/eval_results.jsonl
Outputs:  eval_outputs/<model>/kappa.csv
          eval_outputs/<model>/kappa_plots/kappa_<scorer>_<field>.png
          eval_outputs/<model>/kappa_plots/distributions_<scorer>_<field>.png
          eval_outputs/<model>/KAPPA_REPORT.md

Usage:
    python eval/compute_kappa.py <model>
"""
from __future__ import annotations
import argparse
import itertools
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.ticker import FormatStrFormatter, NullFormatter
from sklearn.metrics import cohen_kappa_score


# ─── Settings ────────────────────────────────────────────────────────────────
SCORERS = ["law_equivalence", "law_validity"]
FIELDS  = ["name", "statement", "formula", "overall"]
N_CATEGORIES = 5  # Likert 0-4 ⇒ 5 categories

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Times New Roman", "DejaVu Serif", "Palatino", "Georgia", "STIXGeneral"],
})


# ─── IO ──────────────────────────────────────────────────────────────────────

def load_eval_rows(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line: continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def build_judge_item_scores(rows: list[dict], scorer: str, field: str
                            ) -> dict[str, dict[tuple, int]]:
    """Returns {judge_model: {(engine, experiment, sample_id): score}}."""
    out: dict[str, dict[tuple, int]] = defaultdict(dict)
    for r in rows:
        if r.get("scorer") != scorer: continue
        if r.get("skipped"): continue
        if r.get("judge_error"): continue
        scores = r.get("scores") or {}
        v = scores.get(field)
        if v is None: continue
        try:
            v = int(v)
        except (TypeError, ValueError):
            continue
        if v < 0 or v >= N_CATEGORIES:
            continue
        item_key = (r["engine"], r["experiment"], r["sample_id"])
        judge = r["judge_model"]
        # First-seen wins (mirrors the reference)
        if item_key not in out[judge]:
            out[judge][item_key] = v
    return out


def align_judges(judge_item_scores: dict[str, dict[tuple, int]]
                 ) -> dict[str, list[int]]:
    """Intersect item keys across judges, return {judge: [scores in sorted-key order]}."""
    if not judge_item_scores: return {}
    judges = list(judge_item_scores.keys())
    common = set(judge_item_scores[judges[0]].keys())
    for j in judges[1:]:
        common &= set(judge_item_scores[j].keys())
    if not common:
        return {}
    keys_sorted = sorted(common)
    return {j: [judge_item_scores[j][k] for k in keys_sorted] for j in judges}


# ─── Kappa stats ─────────────────────────────────────────────────────────────

def pairwise_kappa(aligned: dict[str, list[int]]) -> dict[tuple[str, str], float]:
    judges = sorted(aligned.keys())
    out = {}
    for j1, j2 in itertools.combinations(judges, 2):
        y1, y2 = aligned[j1], aligned[j2]
        n = min(len(y1), len(y2))
        if n < 2: continue
        try:
            k = cohen_kappa_score(y1[:n], y2[:n], weights="quadratic")
            out[(j1, j2)] = float(k)
        except Exception as e:
            print(f"  WARNING kappa({j1},{j2}): {e}")
    return out


def fleiss_kappa(aligned: dict[str, list[int]]) -> float | None:
    """Fleiss kappa for a 0..N_CATEGORIES-1 Likert scale."""
    judges = sorted(aligned.keys())
    if len(judges) < 2: return None
    n_min = min(len(aligned[j]) for j in judges)
    if n_min < 2: return None
    matrix = np.array([aligned[j][:n_min] for j in judges]).T  # (n_items, n_raters)
    n_items, n_raters = matrix.shape

    cat_counts = np.zeros((n_items, N_CATEGORIES))
    for i in range(n_items):
        for r in matrix[i]:
            r = int(r)
            if 0 <= r < N_CATEGORIES:
                cat_counts[i, r] += 1

    if n_raters < 2:
        return None
    P_i  = (np.sum(cat_counts ** 2, axis=1) - n_raters) / (n_raters * (n_raters - 1))
    P_bar = np.mean(P_i)
    P_j  = np.sum(cat_counts, axis=0) / (n_items * n_raters)
    P_e  = np.sum(P_j ** 2)
    if P_e == 1: return None
    return float((P_bar - P_e) / (1 - P_e))


def interpret(k: float) -> str:
    if k < 0:        return "Poor"
    if k < 0.20:     return "Slight"
    if k < 0.40:     return "Fair"
    if k < 0.60:     return "Moderate"
    if k < 0.80:     return "Substantial"
    return "Almost Perfect"


def clean_judge_name(j: str) -> str:
    return j


# ─── Plots ───────────────────────────────────────────────────────────────────

def plot_kappa_heatmap(kappa_results: dict, judges: list[str],
                       title: str, save_path: Path) -> None:
    n = len(judges)
    if n < 2: return

    matrix = np.full((n, n), np.nan)
    for i, j in itertools.combinations(range(n), 2):
        m1, m2 = judges[i], judges[j]
        v = kappa_results.get((m1, m2), kappa_results.get((m2, m1), np.nan))
        matrix[j, i] = v

    fig, ax = plt.subplots(figsize=(max(10, n * 3.2), max(8, n * 3.0)))
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "muted_cols", ["#FFFDE7", "#FFF5CC", "#FFE0B2", "#FFCC80", "#FFAB91"])
    plotted = [matrix[i, j] for i in range(1, n) for j in range(i)
               if not np.isnan(matrix[i, j])]
    vmin = max(min(plotted) if plotted else -1.0, 1e-3)
    vmax = max(max(plotted) if plotted else 1.0, 1e-3)
    if vmin >= vmax: vmin, vmax = 1e-3, 1.0
    norm = mcolors.LogNorm(vmin=vmin, vmax=vmax)

    for i in range(1, n):
        for j in range(i):
            v = matrix[i, j]
            if np.isnan(v): continue
            color = cmap(norm(max(v, 1e-3)))
            rect = plt.Rectangle((j, i - 1), 1, 1, facecolor=color, edgecolor="gray")
            ax.add_patch(rect)
            ax.text(j + 0.5, i - 0.5, f"{v:.3f}",
                    ha="center", va="center",
                    color="black", fontsize=24, weight="bold")

    display = [clean_judge_name(j) for j in judges]
    ax.set_xlim(0, n - 1)
    ax.set_ylim(0, n - 1)
    ax.set_xticks(np.arange(n - 1) + 0.5)
    ax.set_yticks(np.arange(n - 1) + 0.5)
    ax.set_xticklabels(display[:-1], rotation=45, ha="right", fontsize=18)
    ax.set_yticklabels(display[1:], fontsize=18)
    ax.invert_yaxis()
    ax.set_aspect("equal")
    ax.set_title(title, fontsize=22, weight="bold", pad=20)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.tick_params(top=False, bottom=False, left=False, right=False)

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
    if vmin < vmax:
        cbar.set_ticks(np.logspace(math.log10(vmin), math.log10(vmax), 5))
    cbar.set_label("Weighted Cohen's Kappa", fontsize=18)
    cbar.ax.tick_params(labelsize=14)
    cbar.ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))
    cbar.ax.yaxis.set_minor_formatter(NullFormatter())
    cbar.ax.minorticks_off()

    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()


def plot_score_distributions(aligned: dict[str, list[int]],
                             title: str, save_path: Path) -> None:
    judges = sorted(aligned.keys())
    if not judges: return
    fig, axes = plt.subplots(1, 2, figsize=(20, 7))

    ax1 = axes[0]
    for j in judges:
        ax1.hist(aligned[j], alpha=0.55, label=clean_judge_name(j),
                 bins=N_CATEGORIES, range=(-0.5, N_CATEGORIES - 0.5))
    ax1.set_xlabel("Likert Score (0-4)", fontsize=14)
    ax1.set_ylabel("Frequency", fontsize=14)
    ax1.set_title(title, fontsize=15)
    ax1.legend(fontsize=11)
    ax1.set_xticks(list(range(N_CATEGORIES)))
    ax1.tick_params(axis="both", labelsize=12)
    ax1.grid(True, alpha=0.3, axis="y")

    ax2 = axes[1]
    data_for_box = [aligned[j] for j in judges]
    bp = ax2.boxplot(data_for_box,
                     tick_labels=[clean_judge_name(j) for j in judges],
                     patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor("lightblue")
    ax2.set_xlabel("Judge", fontsize=14)
    ax2.set_ylabel("Likert Score (0-4)", fontsize=14)
    ax2.set_title(title, fontsize=15)
    ax2.set_ylim(-0.5, N_CATEGORIES - 0.5)
    ax2.tick_params(axis="both", labelsize=12)
    ax2.grid(True, alpha=0.3, axis="y")
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=20, ha="right", fontsize=11)

    plt.tight_layout()
    plt.savefig(save_path, dpi=200, bbox_inches="tight")
    plt.close()


# ─── Markdown report ─────────────────────────────────────────────────────────

def md_table(rows, headers, aligns=None):
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--out_dir", default=None)
    args = ap.parse_args()

    eval_dir = Path("eval_outputs") / args.model
    eval_path = eval_dir / "eval_results.jsonl"
    if not eval_path.exists():
        raise SystemExit(f"missing {eval_path}")

    out_dir = Path(args.out_dir) if args.out_dir else eval_dir
    plots_dir = out_dir / "kappa_plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    rows = load_eval_rows(eval_path)
    print(f"[kappa] loaded {len(rows)} eval rows from {eval_path}")

    csv_rows = []
    md_lines: list[str] = []
    md_lines.append(f"# {args.model} — inter-judge agreement (Cohen / Fleiss kappa)")
    md_lines.append("")
    md_lines.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    md_lines.append("")
    md_lines.append("Pairwise quadratic-weighted Cohen's κ and Fleiss' κ on the 3-judge "
                    "Likert (0-4) scores per (scorer, field).")
    md_lines.append("")
    md_lines.append("Interpretation thresholds: <0.0 Poor · <0.20 Slight · <0.40 Fair · "
                    "<0.60 Moderate · <0.80 Substantial · ≥0.80 Almost Perfect.")
    md_lines.append("")

    # One section per (scorer, field)
    for scorer in SCORERS:
        md_lines.append(f"## {scorer}")
        md_lines.append("")
        for field in FIELDS:
            md_lines.append(f"### {scorer} → `{field}`")
            md_lines.append("")
            jis = build_judge_item_scores(rows, scorer, field)
            aligned = align_judges(jis)
            judges = sorted(aligned.keys())
            n_common = len(next(iter(aligned.values()))) if aligned else 0
            n_judges = len(judges)

            if n_judges < 2 or n_common < 2:
                md_lines.append(f"_Not enough data: {n_judges} judges, {n_common} aligned items._")
                md_lines.append("")
                continue

            md_lines.append(f"- Judges: {n_judges} ({', '.join(judges)})")
            md_lines.append(f"- Aligned items (intersection): **{n_common}**")
            md_lines.append("")

            # per-judge mean / std
            md_lines.append("**Per-judge distribution on aligned items:**")
            md_lines.append("")
            jrows = []
            for j in judges:
                vals = aligned[j]
                jrows.append([j, len(vals), f"{np.mean(vals):.3f}", f"{np.std(vals):.3f}",
                              min(vals), max(vals)])
            md_lines.append(md_table(jrows,
                ["judge", "N", "mean", "sd", "min", "max"],
                ["l", "r", "r", "r", "r", "r"]))
            md_lines.append("")

            # pairwise kappa
            kappa_results = pairwise_kappa(aligned)
            kpairs = sorted(kappa_results.items(), key=lambda x: -x[1])
            md_lines.append("**Pairwise weighted Cohen's κ:**")
            md_lines.append("")
            md_lines.append(md_table(
                [[j1, j2, f"{k:.4f}", interpret(k)] for (j1, j2), k in kpairs],
                ["judge_a", "judge_b", "weighted κ", "interpretation"],
                ["l", "l", "r", "l"]))
            md_lines.append("")

            avg = float(np.mean([k for _, k in kpairs])) if kpairs else float("nan")
            fk = fleiss_kappa(aligned)
            ovr_rows = [
                ["mean of pairwise κ", f"{avg:.4f}", interpret(avg) if not math.isnan(avg) else "-"],
                ["Fleiss' κ (all judges)", f"{fk:.4f}" if fk is not None else "-",
                 interpret(fk) if fk is not None else "-"],
            ]
            md_lines.append(md_table(ovr_rows,
                ["statistic", "value", "interpretation"],
                ["l", "r", "l"]))
            md_lines.append("")

            # Plots
            heatmap_path = plots_dir / f"kappa_{scorer}_{field}.png"
            dist_path = plots_dir / f"distributions_{scorer}_{field}.png"
            plot_kappa_heatmap(kappa_results, judges,
                f"{args.model} — {scorer} / {field}", heatmap_path)
            plot_score_distributions(aligned,
                f"{args.model} — {scorer} / {field} (N={n_common})", dist_path)

            md_lines.append(f"![]({heatmap_path.relative_to(out_dir)})")
            md_lines.append("")
            md_lines.append(f"![]({dist_path.relative_to(out_dir)})")
            md_lines.append("")

            # CSV rows
            for (j1, j2), k in kappa_results.items():
                csv_rows.append({
                    "model": args.model, "scorer": scorer, "field": field,
                    "judge_a": j1, "judge_b": j2,
                    "weighted_cohen_kappa": round(k, 6),
                    "interpretation": interpret(k),
                    "n_aligned_items": n_common,
                })
            if fk is not None:
                csv_rows.append({
                    "model": args.model, "scorer": scorer, "field": field,
                    "judge_a": "ALL", "judge_b": "OVERALL_FLEISS",
                    "weighted_cohen_kappa": round(fk, 6),
                    "interpretation": f"Fleiss: {interpret(fk)}",
                    "n_aligned_items": n_common,
                })

    # Save artifacts
    csv_path = out_dir / "kappa.csv"
    if csv_rows:
        pd.DataFrame(csv_rows).to_csv(csv_path, index=False)
        print(f"[kappa] wrote {csv_path} ({len(csv_rows)} rows)")
    md_path = out_dir / "KAPPA_REPORT.md"
    md_path.write_text("\n".join(md_lines))
    print(f"[kappa] wrote {md_path}")
    print(f"[kappa] heatmaps + distributions in {plots_dir}")


if __name__ == "__main__":
    main()
