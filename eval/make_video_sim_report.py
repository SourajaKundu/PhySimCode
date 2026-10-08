"""Generate a per-model video-similarity report.

Reads:   eval_outputs/<model>/video_similarity.jsonl
Writes:  eval_outputs/<model>/VIDEO_SIM_REPORT.md

Usage:
    python eval/make_video_sim_report.py <model>
"""
from __future__ import annotations
import argparse, json, statistics, sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def load_jsonl(p: Path) -> list[dict]:
    if not p.exists(): return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line: continue
        try: out.append(json.loads(line))
        except: pass
    return out


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


def hist(vals, edges, bar_w=30):
    counts = [0] * (len(edges) + 1)
    for v in vals:
        placed = False
        for i, e in enumerate(edges):
            if v < e:
                counts[i] += 1; placed = True; break
        if not placed: counts[-1] += 1
    total = sum(counts) or 1
    mx = max(counts) or 1
    out = []
    prev = -float("inf")
    for i, e in enumerate(edges):
        bar = "█" * int(counts[i] / mx * bar_w)
        label = f"<{e:.2f}"
        out.append(f"  {label:<8s} {counts[i]:>5d} ({100*counts[i]/total:>4.1f}%) {bar}")
    label = f">={edges[-1]:.2f}"
    bar = "█" * int(counts[-1] / mx * bar_w)
    out.append(f"  {label:<8s} {counts[-1]:>5d} ({100*counts[-1]/total:>4.1f}%) {bar}")
    return out


def stats_block(vals: list[float]) -> dict:
    if not vals: return {}
    s = sorted(vals)
    n = len(s)
    def pct(p): return s[int(round((p/100)*(n-1)))]
    return {
        "N": n,
        "mean":   statistics.fmean(vals),
        "median": statistics.median(vals),
        "P5":     pct(5),  "P10": pct(10), "P25": pct(25),
        "P75":    pct(75), "P90": pct(90), "P95": pct(95),
        "min":    min(vals), "max": max(vals),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    p = Path("eval_outputs") / args.model / "video_similarity.jsonl"
    rows = load_jsonl(p)
    if not rows:
        sys.exit(f"no rows at {p}")

    ok = [r for r in rows if r.get("status") == "ok"]
    err = [r for r in rows if r.get("status") != "ok"]

    out: list[str] = []
    out.append(f"# {args.model} — video similarity report")
    out.append("")
    out.append(f"_Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}_")
    out.append("")
    out.append("Per-sample cosine similarity between **rendered model output** and the "
               "**reference benchmark video** (`benchmarking_data/<engine>/<exp>/<sid>/video.mp4`).")
    out.append("")
    out.append("- **DINOv2** (`facebook/dinov2-base`): per-frame ViT embeddings, mean-pooled across 16 uniform frames, L2-normalized.")
    out.append("- **X-CLIP** (`microsoft/xclip-base-patch16`): single video-level embedding from 8 uniform frames, L2-normalized.")
    out.append("")

    # ─── Headline ─────────────────────────────────────────
    dino = [r["dino_cosine"] for r in ok if "dino_cosine" in r]
    xclip = [r["xclip_cosine"] for r in ok if "xclip_cosine" in r]
    out.append("## Headline")
    out.append("")
    out.append(md_table(
        [
            ["pairs total", len(rows)],
            ["scored OK", len(ok)],
            ["errors / unreadable", len(err)],
            ["**DINOv2 cosine — mean**", f"**{statistics.fmean(dino):.4f}**" if dino else "-"],
            ["DINOv2 cosine — median", f"{statistics.median(dino):.4f}" if dino else "-"],
            ["**X-CLIP cosine — mean**", f"**{statistics.fmean(xclip):.4f}**" if xclip else "-"],
            ["X-CLIP cosine — median", f"{statistics.median(xclip):.4f}" if xclip else "-"],
        ],
        ["metric", "value"], ["l", "r"],
    ))
    out.append("")

    # ─── Distribution by encoder ─────────────────────────
    out.append("## Distribution")
    out.append("")
    for label, vals in [("DINOv2", dino), ("X-CLIP", xclip)]:
        if not vals: continue
        s = stats_block(vals)
        out.append(f"### {label}")
        out.append("")
        out.append(md_table(
            [[label, s["N"], f"{s['mean']:.4f}", f"{s['median']:.4f}",
              f"{s['P5']:.4f}", f"{s['P25']:.4f}", f"{s['P75']:.4f}",
              f"{s['P95']:.4f}", f"{s['min']:.4f}", f"{s['max']:.4f}"]],
            ["encoder", "N", "mean", "median", "P5", "P25", "P75", "P95", "min", "max"],
            ["l"] + ["r"]*9,
        ))
        out.append("")
        out.append("```")
        for line in hist(vals, [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]):
            out.append(line)
        out.append("```")
        out.append("")

    # ─── Per-engine ──────────────────────────────────────
    out.append("## Per engine")
    out.append("")
    rows_by_eng = defaultdict(list)
    for r in ok:
        rows_by_eng[r["engine"]].append(r)
    eng_rows = []
    for eng in sorted(rows_by_eng.keys()):
        sub = rows_by_eng[eng]
        d = [r["dino_cosine"] for r in sub if "dino_cosine" in r]
        x = [r["xclip_cosine"] for r in sub if "xclip_cosine" in r]
        eng_rows.append([
            eng, len(sub),
            f"{statistics.fmean(d):.4f}" if d else "-",
            f"{statistics.median(d):.4f}" if d else "-",
            f"{statistics.fmean(x):.4f}" if x else "-",
            f"{statistics.median(x):.4f}" if x else "-",
        ])
    out.append(md_table(eng_rows,
                        ["engine", "N", "DINO mean", "DINO median",
                         "XCLIP mean", "XCLIP median"],
                        ["l"] + ["r"]*5))
    out.append("")

    # ─── Top / bottom samples (DINOv2) ───────────────────
    if dino:
        ok_sorted = sorted(ok, key=lambda r: r.get("dino_cosine", 0))
        out.append("## Sample tails (DINOv2 cosine)")
        out.append("")
        out.append("### Lowest 5 (model render least matches reference)")
        out.append("")
        rows_t = []
        for r in ok_sorted[:5]:
            rows_t.append([r["engine"], r["experiment"], r["sample_id"],
                           f"{r.get('dino_cosine',0):.3f}",
                           f"{r.get('xclip_cosine',0):.3f}"])
        out.append(md_table(rows_t,
                            ["engine", "experiment", "sample_id", "DINO", "XCLIP"],
                            ["l", "l", "l", "r", "r"]))
        out.append("")
        out.append("### Highest 5 (model render most matches reference)")
        out.append("")
        rows_t = []
        for r in ok_sorted[-5:][::-1]:
            rows_t.append([r["engine"], r["experiment"], r["sample_id"],
                           f"{r.get('dino_cosine',0):.3f}",
                           f"{r.get('xclip_cosine',0):.3f}"])
        out.append(md_table(rows_t,
                            ["engine", "experiment", "sample_id", "DINO", "XCLIP"],
                            ["l", "l", "l", "r", "r"]))
        out.append("")

    # ─── Per-experiment (best/worst) ─────────────────────
    if ok:
        by_exp = defaultdict(list)
        for r in ok:
            by_exp[(r["engine"], r["experiment"])].append(r["dino_cosine"])
        exp_rows = []
        for (eng, exp), vals in by_exp.items():
            exp_rows.append((eng, exp, len(vals), statistics.fmean(vals)))
        # Top 5 best mean
        out.append("## Top / bottom experiments by DINOv2 mean")
        out.append("")
        sorted_best = sorted(exp_rows, key=lambda r: -r[3])
        out.append("### Best 5")
        out.append("")
        out.append(md_table(
            [[r[0], r[1], r[2], f"{r[3]:.3f}"] for r in sorted_best[:5]],
            ["engine", "experiment", "N", "DINO mean"], ["l", "l", "r", "r"]))
        out.append("")
        out.append("### Worst 5")
        out.append("")
        out.append(md_table(
            [[r[0], r[1], r[2], f"{r[3]:.3f}"] for r in sorted_best[-5:][::-1]],
            ["engine", "experiment", "N", "DINO mean"], ["l", "l", "r", "r"]))
        out.append("")

    # ─── Unreadable / errored videos ─────────────────────
    if err:
        out.append("## Unreadable videos (errors)")
        out.append("")
        n_total = len(rows)

        # 1) overall count + rate
        out.append(f"**{len(err)} of {n_total} pairs ({100*len(err)/n_total:.1f}%) failed to score.** "
                   "These are cases where the rendered video file exists but cannot be decoded "
                   "into frames (most commonly: a 262-byte empty MP4 stub left behind when the "
                   "model's animation script crashed mid-write).")
        out.append("")

        # 2) by error type
        out.append("### By error type")
        out.append("")
        cnt = Counter(r.get("error", "(no message)") for r in err)
        out.append(md_table(
            [[k, v, f"{100*v/len(err):.1f}%"] for k, v in cnt.most_common(10)],
            ["error", "count", "% of errors"], ["l", "r", "r"]))
        out.append("")

        # 3) by engine
        eng_total = Counter(r["engine"] for r in rows)
        eng_err = Counter(r["engine"] for r in err)
        out.append("### By engine (broken-rendered-video rate)")
        out.append("")
        eng_rows = []
        for eng in sorted(eng_total.keys()):
            n_eng_total = eng_total[eng]
            n_eng_err = eng_err.get(eng, 0)
            eng_rows.append([eng, n_eng_total, n_eng_err,
                             f"{100*n_eng_err/n_eng_total:.1f}%"])
        out.append(md_table(eng_rows,
                            ["engine", "pairs", "errors", "rate"],
                            ["l", "r", "r", "r"]))
        out.append("")

        # 4) Rendered file size distribution (the broken-stub signature)
        sizes = []
        ref_sizes = []
        ref_missing = 0
        rend_missing = 0
        for r in err:
            rp = Path(r.get("rendered_path", ""))
            ref = Path(r.get("reference_path", ""))
            if rp.exists():
                sizes.append(rp.stat().st_size)
            else:
                rend_missing += 1
            if ref.exists():
                ref_sizes.append(ref.stat().st_size)
            else:
                ref_missing += 1

        out.append("### Side analysis (which video failed to read)")
        out.append("")
        side_rows = [
            [f"rendered file present ({args.model}'s output)", len(sizes)],
            ["rendered file MISSING", rend_missing],
            ["reference file present", len(ref_sizes)],
            ["reference file MISSING", ref_missing],
        ]
        out.append(md_table(side_rows, ["check", "count"], ["l", "r"]))
        out.append("")

        if sizes:
            sb = stats_block(sizes)
            tiny = sum(1 for s in sizes if s < 1024)
            small = sum(1 for s in sizes if s < 10 * 1024)
            out.append("### Rendered video file size (errored only)")
            out.append("")
            out.append(md_table(
                [[
                    "errored renders",
                    sb["N"], f"{sb['min']}", f"{sb['median']:.0f}",
                    f"{sb['mean']:.0f}", f"{sb['max']}",
                    tiny, small,
                ]],
                ["category", "N", "min B", "median B", "mean B", "max B",
                 "<1 KB", "<10 KB"],
                ["l"] + ["r"] * 7,
            ))
            out.append("")
            out.append(f"_For context: a healthy rendered MP4 is ~150-300 KB. "
                       f"{tiny} files (<1 KB) and {small} files (<10 KB) of the {len(sizes)} "
                       f"errored rows are obviously broken stubs from crashed animations._")
            out.append("")

        # 5) top experiments with errors
        if err:
            err_by_exp = Counter((r["engine"], r["experiment"]) for r in err)
            tot_by_exp = Counter((r["engine"], r["experiment"]) for r in rows)
            ranked = []
            for key, n_err in err_by_exp.most_common():
                n_tot = tot_by_exp[key]
                ranked.append((key, n_err, n_tot, n_err / n_tot))
            top5 = sorted(ranked, key=lambda r: (-r[3], -r[1]))[:10]
            out.append("### Top 10 experiments with most unreadable rendered videos")
            out.append("")
            out.append(md_table(
                [[k[0], k[1], n_err, n_tot, f"{100*rate:.1f}%"]
                 for (k, n_err, n_tot, rate) in top5],
                ["engine", "experiment", "errors", "total", "rate"],
                ["l", "l", "r", "r", "r"]))
            out.append("")

    out_path = Path(args.out) if args.out else (Path("eval_outputs") / args.model / "VIDEO_SIM_REPORT.md")
    out_path.write_text("\n".join(out))
    print(f"wrote {out_path} ({len(out_path.read_text()):,} chars)")


if __name__ == "__main__":
    main()
