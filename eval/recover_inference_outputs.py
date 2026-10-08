"""Walk inference_outputs/, run the tolerant CoT recovery on every parse-failed
row, and write a sidecar `results_recovered.jsonl` per model dir.

Each output row carries audit metadata so we can tell what was original vs.
what was rescued:
    parse_ok_cot              : True iff parsed_cot has a usable physical_law
                                (whether it was originally OK or rescued)
    parse_ok_cot_orig         : the original flag, untouched
    parsed_cot                : full dict if recovered, else None
    parsed_cot_partial        : True if we only got physical_law, not full JSON
    cot_recovery_method       : "already_valid" | "basic_fixups" | "evaluate_arith"
                                | "evaluate_lists" | "latex_escape" | "json5"
                                | "regex_law_only" | "no_cot_block" | "unrecoverable"
    cot_recovery_error        : str | None
"""
from __future__ import annotations
import argparse, json, sys
from collections import Counter
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from eval._common import INFER_ROOT, discover_results, read_results
from eval.recover_cot import recover_cot


def process_row(rec: dict) -> dict:
    """Return a copy of `rec` with recovery audit fields added."""
    out = dict(rec)
    out["parse_ok_cot_orig"] = bool(rec.get("parse_ok_cot", False))

    res = recover_cot(rec.get("raw_output", "") or "",
                      original_parsed_cot=rec.get("parsed_cot"))
    out["cot_recovery_method"] = res.method
    out["cot_recovery_error"]  = res.error
    out["parsed_cot_partial"]  = res.partial

    if res.parsed_cot is not None and res.physical_law:
        # treat "have physical_law" as parse-ok for downstream judging
        out["parsed_cot"]   = res.parsed_cot
        out["parse_ok_cot"] = True
    elif res.parsed_cot is not None and not res.physical_law:
        # full JSON parsed but no physical_law block — keep the parse but mark not-OK
        out["parsed_cot"]   = res.parsed_cot
        out["parse_ok_cot"] = False
    else:
        out["parsed_cot"]   = rec.get("parsed_cot")
        out["parse_ok_cot"] = False
    return out


def process_model(model_dir: Path, out_path: Path) -> dict:
    # Always read the ORIGINAL inference outputs, never our own sidecar.
    files = discover_results(model_dir, prefer_recovered=False)
    if not files:
        return {"model": model_dir.name, "files": 0, "rows": 0, "skipped": "no results.jsonl"}

    method_counter   = Counter()
    n_orig_ok        = 0
    n_now_ok         = 0
    n_rescued        = 0
    n_lost           = 0
    rows_in: List[dict] = []
    for f in files:
        rows_in.extend(read_results(str(f)))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as fh:
        for r in rows_in:
            patched = process_row(r)
            fh.write(json.dumps(patched, default=str) + "\n")
            method_counter[patched["cot_recovery_method"]] += 1
            if patched["parse_ok_cot_orig"]:
                n_orig_ok += 1
            if patched["parse_ok_cot"]:
                n_now_ok += 1
            if patched["parse_ok_cot"] and not patched["parse_ok_cot_orig"]:
                n_rescued += 1
            if not patched["parse_ok_cot"] and not patched["parse_ok_cot_orig"]:
                n_lost += 1

    return {
        "model":            model_dir.name,
        "files":            len(files),
        "rows":             len(rows_in),
        "originally_ok":    n_orig_ok,
        "now_ok":           n_now_ok,
        "rescued":          n_rescued,
        "still_lost":       n_lost,
        "ok_gain":          n_now_ok - n_orig_ok,
        "ok_pct_before":    round(100 * n_orig_ok / max(len(rows_in), 1), 1),
        "ok_pct_after":     round(100 * n_now_ok  / max(len(rows_in), 1), 1),
        "method_breakdown": dict(method_counter),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inference_root", default=str(INFER_ROOT))
    ap.add_argument("--models", nargs="*", default=None,
                    help="If omitted, every subdir of inference_outputs/ except _logs is processed.")
    ap.add_argument("--out_filename", default="results_recovered.jsonl",
                    help="Filename for the recovered output, written into each model dir.")
    args = ap.parse_args()

    infer_root = Path(args.inference_root)
    if args.models:
        model_dirs = [infer_root / m for m in args.models]
    else:
        model_dirs = sorted(p for p in infer_root.iterdir()
                            if p.is_dir() and not p.name.startswith("_"))

    print(f"[recover] root={infer_root}")
    print(f"[recover] {len(model_dirs)} models: {[d.name for d in model_dirs]}\n")

    summaries = []
    for d in model_dirs:
        if not d.exists():
            print(f"!! missing: {d}"); continue
        out_path = d / args.out_filename
        print(f"=== {d.name} ===  → {out_path}")
        info = process_model(d, out_path)
        summaries.append(info)
        print(json.dumps(info, indent=2)); print()

    # Cross-model comparison
    print("\n" + "=" * 78)
    print(f"{'model':<25s} {'rows':>5s} {'orig_OK':>8s} {'now_OK':>8s} {'rescued':>8s} {'still_lost':>11s}")
    print("-" * 78)
    for s in summaries:
        print(f"{s['model']:<25s} {s['rows']:>5d} "
              f"{s['originally_ok']:>5d}/{s['ok_pct_before']:>4.1f}% "
              f"{s['now_ok']:>5d}/{s['ok_pct_after']:>4.1f}% "
              f"{s['rescued']:>8d} {s['still_lost']:>11d}")


if __name__ == "__main__":
    main()
