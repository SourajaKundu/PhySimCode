"""Evaluate predicted-vs-ground-truth parameter recovery across models.

Outputs
-------
1. A per-sample JSONL at <infer>/parameter_evaluation.jsonl. Each row contains
   the GT parameter dict (filtered) once at the start, plus a nested per-model
   section with predicted parameters, the matched (GT, pred) pairs, relative
   errors, fraction reported, fraction within 20 % tolerance, and the
   cumulative relative error across all matched parameters.
2. The paper's Table 9 summary (printed, and written next to the JSONL as
   parameter_evaluation_summary.csv).

Usage
-----
    python eval/eval_parameters.py                        # all models under inference_outputs/
    python eval/eval_parameters.py --models my_model
    python eval/eval_parameters.py --summarize-only       # re-print the table

Ground-truth CoTs are read from <bench>/<engine>/<experiment>/<sample>/cot.json.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).parent.parent.resolve()

# Populated by main(); module-level so the helpers below stay importable.
BENCH = ROOT / "benchmarking_data"
INFER = ROOT / "inference_outputs"
OUT   = INFER / "parameter_evaluation.jsonl"
MODELS: list[str] = []

# ─────────────────────────────────────────────────────────────────────────────
# 1) Filter — which GT parameter keys to skip
# ─────────────────────────────────────────────────────────────────────────────
SKIP_EXACT = {
    "g",                           # gravity (always 9.81 — freebie)
    "experiment", "category",      # metadata
    "camera_eye", "camera_target", "camera_pos",
    "colors", "color",
    "object_shapes", "shapes",
    "positions", "velocities",
    "duration", "fps", "n_frames", "seed",
    "n_objects", "n_pucks", "n_pit", "n_arch_blocks",  # object counts
    "floor_size",                  # arena scale, not physics
}
SKIP_SUBSTRING = (
    "_pos", "pos_", "color", "shape", "camera",
)


def is_physics_param(name: str, val: Any) -> bool:
    """True if this GT parameter should participate in evaluation."""
    n = name.lower()
    if n in SKIP_EXACT:
        return False
    if any(s in n for s in SKIP_SUBSTRING):
        return False
    # Skip non-scalar values (lists, dicts of pos/vel etc.)
    if isinstance(val, dict):
        v = val.get("value")
    else:
        v = val
    if isinstance(v, (list, tuple)):
        return False
    if v is None:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# 2) Name normalisation + alias generation (B2: lexical + deabbreviation)
# ─────────────────────────────────────────────────────────────────────────────
ABBREV = {
    "m": "mass", "mass": "mass",
    "v": "velocity", "vel": "velocity", "velocity": "velocity",
    "speed": "velocity",
    "u": "velocity",
    "r": "radius", "rad": "radius", "radius": "radius",
    "d": "diameter", "dia": "diameter", "diameter": "diameter",
    "h": "height", "ht": "height", "height": "height",
    "l": "length", "len": "length", "length": "length",
    "w": "width", "wid": "width", "width": "width",
    "k": "stiffness", "stiffness": "stiffness", "spring_constant": "stiffness",
    "i": "moment_inertia", "moi": "moment_inertia", "moment_of_inertia": "moment_inertia",
    "t": "period", "period": "period",
    "f": "frequency", "freq": "frequency", "frequency": "frequency",
    "theta": "angle", "phi": "angle", "alpha": "angle", "beta": "angle",
    "angle": "angle", "angle_deg": "angle", "angle_rad": "angle",
    "deg": "angle", "rad_angle": "angle",
    "omega": "angular_velocity", "ang_vel": "angular_velocity",
    "angular_velocity": "angular_velocity", "spin": "angular_velocity",
    "tau": "torque", "torque": "torque",
    "rho": "density", "density": "density",
    "mu": "friction", "friction": "friction",
    "friction_coefficient": "friction", "coefficient_of_friction": "friction",
    "e": "restitution", "restitution": "restitution",
    "coefficient_of_restitution": "restitution",
    "f_force": "force", "force": "force",
    "p": "pressure", "pressure": "pressure",
    "q": "charge", "charge": "charge",
    "energy": "energy", "ke": "kinetic_energy", "pe": "potential_energy",
    "amp": "amplitude", "amplitude": "amplitude",
    "wavelength": "wavelength", "lambda": "wavelength",
}


def normalize(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r"[\s\-\.]+", "_", n)
    n = re.sub(r"_+", "_", n).strip("_")
    return n


def alias_set(name: str) -> set[str]:
    """All aliases this name should match against."""
    out: set[str] = set()
    n = normalize(name)
    if not n:
        return out
    out.add(n)
    # base form (drop trailing digits)
    base = re.sub(r"\d+$", "", n)
    if base and base != n:
        out.add(base)
    # token decomposition
    tokens = n.split("_")
    deabbr = [ABBREV.get(t, t) for t in tokens]
    out.add("_".join(deabbr))
    for t in tokens:
        if not t:
            continue
        out.add(t)
        bt = re.sub(r"\d+$", "", t)
        if bt and bt != t:
            out.add(bt)
        if t in ABBREV:
            out.add(ABBREV[t])
        if bt and bt in ABBREV:
            out.add(ABBREV[bt])
    return out


def match_pairs(gt_names: list[str],
                pred_names: list[str]) -> list[tuple[str, str]]:
    """Greedy bipartite matching: prefer high-overlap pairs first.
    Each gt_name and pred_name participate in at most one match."""
    gt_alias = {n: alias_set(n) for n in gt_names}
    pred_alias = {n: alias_set(n) for n in pred_names}
    candidates = []
    for g in gt_names:
        for p in pred_names:
            inter = gt_alias[g] & pred_alias[p]
            if inter:
                union = gt_alias[g] | pred_alias[p]
                jaccard = len(inter) / len(union)
                candidates.append((-jaccard, -len(inter), g, p))
    candidates.sort()
    used_g, used_p = set(), set()
    pairs: list[tuple[str, str]] = []
    for _, _, g, p in candidates:
        if g in used_g or p in used_p:
            continue
        used_g.add(g); used_p.add(p)
        pairs.append((g, p))
    return pairs


# ─────────────────────────────────────────────────────────────────────────────
# 3) Value + unit handling
# ─────────────────────────────────────────────────────────────────────────────
NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def to_number(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = NUM_RE.search(v)
        if m:
            try:
                return float(m.group())
            except ValueError:
                return None
    return None


# Unit normalisation: convert (value, unit) to a canonical SI-ish unit
# Returns (canonical_value, canonical_unit) or original if unknown.
def normalize_unit(value: float, unit: str) -> tuple[float, str]:
    if unit is None:
        return value, ""
    u = unit.strip().lower()
    u = re.sub(r"\\\\?circ\b", "deg", u)        # ^\circ → deg
    u = u.replace("^\\circ", "deg").replace("°", "deg")
    u = re.sub(r"[\s\^]+", "", u)
    # Angle
    if u in ("deg", "degree", "degrees"):
        return value * math.pi / 180.0, "rad"
    if u in ("rad", "radian", "radians"):
        return value, "rad"
    # Length
    if u in ("mm", "millimeter", "millimetre"):
        return value / 1000.0, "m"
    if u in ("cm", "centimeter", "centimetre"):
        return value / 100.0, "m"
    if u in ("km",):
        return value * 1000.0, "m"
    if u in ("m", "meter", "metre"):
        return value, "m"
    # Mass
    if u in ("g", "gram", "grams"):
        return value / 1000.0, "kg"
    if u in ("kg", "kilogram"):
        return value, "kg"
    # Time
    if u in ("ms", "millisecond"):
        return value / 1000.0, "s"
    if u in ("s", "sec", "second", "seconds"):
        return value, "s"
    # Velocity
    if u in ("m/s", "ms-1", "ms^{-1}"):
        return value, "m/s"
    if u in ("km/h", "kph"):
        return value / 3.6, "m/s"
    # Force
    if u in ("kn",):
        return value * 1000.0, "n"
    if u in ("n", "newton"):
        return value, "n"
    # Pressure
    if u in ("kpa",):
        return value * 1000.0, "pa"
    if u in ("mpa",):
        return value * 1e6, "pa"
    return value, u


def relative_error(gt: float, pred: float) -> float:
    """Relative error with absolute fallback when gt ≈ 0."""
    if abs(gt) < 1e-12:
        return abs(pred - gt)               # fall back to abs error
    return abs(pred - gt) / abs(gt)


# ─────────────────────────────────────────────────────────────────────────────
# 4) Helpers to read GT and prediction
# ─────────────────────────────────────────────────────────────────────────────
def gt_filtered_params(cot: dict) -> dict[str, dict]:
    """Return GT.parameters filtered to keep only physics scalars."""
    raw = cot.get("parameters", {}) if isinstance(cot, dict) else {}
    out: dict[str, dict] = {}
    for name, entry in raw.items():
        if not is_physics_param(name, entry):
            continue
        if isinstance(entry, dict):
            v = entry.get("value")
            unit = entry.get("unit", "") or ""
        else:
            v = entry; unit = ""
        if isinstance(v, (list, tuple, dict)):
            continue
        n_v = to_number(v)
        if n_v is None:
            continue
        out[name] = {"value": n_v, "unit": str(unit)}
    return out


def pred_params(rec: dict) -> tuple[bool, dict[str, dict]]:
    """Return (parse_ok, predicted_parameters_dict)."""
    parse_ok = bool(rec.get("parse_ok_cot"))
    cot = rec.get("parsed_cot")
    if not parse_ok or not isinstance(cot, dict):
        return parse_ok, {}
    raw = cot.get("parameters", {})
    if not isinstance(raw, dict):
        return parse_ok, {}
    out: dict[str, dict] = {}
    for name, entry in raw.items():
        if isinstance(entry, dict):
            v = entry.get("value")
            unit = entry.get("unit", "") or ""
        else:
            v = entry; unit = ""
        if isinstance(v, (list, tuple, dict)):
            continue
        n_v = to_number(v)
        if n_v is None:
            continue
        out[str(name)] = {"value": n_v, "unit": str(unit)}
    return parse_ok, out


# ─────────────────────────────────────────────────────────────────────────────
# 5) Evaluation per (engine, exp, sample) pair
# ─────────────────────────────────────────────────────────────────────────────
def evaluate_pair(gt: dict[str, dict], pred: dict[str, dict]) -> dict:
    pairs = match_pairs(list(gt.keys()), list(pred.keys()))
    matched: list[dict] = []
    cum_err = 0.0
    n_in_tol = 0
    for g, p in pairs:
        gv, gu = gt[g]["value"], gt[g]["unit"]
        pv, pu = pred[p]["value"], pred[p]["unit"]
        gv_si, gu_si = normalize_unit(gv, gu)
        pv_si, pu_si = normalize_unit(pv, pu)
        # If units agree post-normalisation use the converted values; otherwise compare raw
        if gu_si == pu_si and gu_si != "":
            re_err = relative_error(gv_si, pv_si)
            used_unit = gu_si
        else:
            re_err = relative_error(gv, pv)
            used_unit = gu or pu or ""
        within = re_err <= 0.20
        cum_err += re_err
        if within:
            n_in_tol += 1
        matched.append({
            "gt_name": g, "pred_name": p,
            "gt_value": gv, "pred_value": pv,
            "gt_unit": gu,  "pred_unit": pu,
            "compared_unit": used_unit,
            "rel_err": re_err,
            "within_20pct": within,
        })
    n_gt, n_pred, n_match = len(gt), len(pred), len(pairs)
    return {
        "n_pred_params": n_pred,
        "predicted_parameters": pred,
        "matched": matched,
        "n_matched": n_match,
        "fraction_reported": (n_match / n_gt) if n_gt > 0 else 0.0,
        "n_within_tolerance": n_in_tol,
        "fraction_within_tolerance": (n_in_tol / n_match) if n_match > 0 else 0.0,
        "cumulative_error": cum_err,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6) Driver
# ─────────────────────────────────────────────────────────────────────────────
def load_predictions(model: str) -> dict[tuple[str, str, str], dict]:
    """Index a model's results.jsonl by (engine, experiment, sample_id)."""
    path = INFER / model / "results.jsonl"
    out: dict[tuple[str, str, str], dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (str(rec.get("engine")), str(rec.get("experiment")), str(rec.get("sample_id")))
            out[key] = rec
    return out


def discover_gt_samples() -> list[tuple[str, str, str, Path]]:
    """Return (engine, experiment, sample_id, cot_path) for every GT sample.

    Prefers cot.json sitting inside the benchmarking tree. Falls back to the
    manifest's `original_path` column for subsets that ship videos only.
    """
    found: dict[tuple[str, str, str], Path] = {}
    for cot_p in BENCH.glob("*/*/*/cot.json"):
        found[(cot_p.parts[-4], cot_p.parts[-3], cot_p.parts[-2])] = cot_p

    manifest = BENCH / "manifest.csv"
    n_from_manifest = 0
    if manifest.exists():
        with manifest.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (str(row["engine"]), str(row["experiment"]),
                       str(row["sample_id"]))
                if key in found:
                    continue
                cot_p = Path(row["original_path"]) / "cot.json"
                if cot_p.exists():
                    found[key] = cot_p
                    n_from_manifest += 1
    if n_from_manifest:
        print(f"resolved {n_from_manifest} GT CoTs via manifest original_path")
    return [(e, x, s, p) for (e, x, s), p in sorted(found.items())]


def main() -> None:
    print(f"ground truth  : {BENCH}")
    print(f"inference     : {INFER}")
    print(f"models discovered ({len(MODELS)}): {MODELS}")
    print("loading predictions per model...", flush=True)
    preds_by_model = {m: load_predictions(m) for m in MODELS}
    for m, d in preds_by_model.items():
        print(f"  {m}: {len(d)} records")

    gt_paths = discover_gt_samples()
    print(f"\nGT samples to evaluate: {len(gt_paths)}\n")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    n_written = 0
    n_missing_gt_params = 0
    with OUT.open("w", encoding="utf-8") as fout:
        for engine, experiment, sample_id, cot_p in gt_paths:
            try:
                gt_cot = json.loads(cot_p.read_text(encoding="utf-8"))
            except Exception:
                continue
            raw_keys = list(gt_cot.get("parameters", {}).keys())
            gt_filt = gt_filtered_params(gt_cot)
            skipped_keys = [k for k in raw_keys if k not in gt_filt]

            row: dict[str, Any] = {
                "engine": engine,
                "experiment": experiment,
                "sample_id": sample_id,
                "n_gt_params": len(gt_filt),
                "gt_parameters": gt_filt,
                "skipped_gt_keys": skipped_keys,
                "models": {},
            }
            if not gt_filt:
                n_missing_gt_params += 1

            for model in MODELS:
                rec = preds_by_model[model].get((engine, experiment, sample_id))
                if rec is None:
                    row["models"][model] = {
                        "parse_ok": False,
                        "no_record": True,
                        "n_pred_params": 0,
                        "predicted_parameters": {},
                        "matched": [],
                        "n_matched": 0,
                        "fraction_reported": 0.0,
                        "n_within_tolerance": 0,
                        "fraction_within_tolerance": 0.0,
                        "cumulative_error": 0.0,
                    }
                    continue
                ok, p_params = pred_params(rec)
                ev = evaluate_pair(gt_filt, p_params)
                ev["parse_ok"] = ok
                ev["no_record"] = False
                row["models"][model] = ev

            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            n_written += 1

    print(f"\nWrote {n_written} rows -> {OUT}")
    print(f"Samples with empty GT after filter: {n_missing_gt_params}")

    summarize(OUT)


# ─────────────────────────────────────────────────────────────────────────────
# 7) Table 9 summary
# ─────────────────────────────────────────────────────────────────────────────
SUMMARY_COLUMNS = [
    ("parse_fails",        "Parse fails"),
    ("avg_pred_params",    "Avg pred params"),
    ("avg_matched",        "Avg matched"),
    ("mean_frac_reported", "Mean frac reported"),
    ("mean_frac_within20", "Mean frac within 20%"),
    ("global_accuracy",    "Global accuracy"),
    ("end_to_end",         "End-to-end recovery"),
]


def summarize(jsonl_path: Path) -> list[dict[str, Any]]:
    """Compute the paper's Table 9 from a parameter_evaluation.jsonl.

    parse_fails         : #samples whose CoT could not be parsed
    avg_pred_params     : mean #parameters emitted per sample
    avg_matched         : mean #parameters aligned to a GT parameter
    mean_frac_reported  : mean over rows of n_matched / n_gt          (naming recall)
    mean_frac_within20  : mean over rows of n_within / n_matched      (value accuracy)
    global_accuracy     : sum(n_within) / sum(n_matched)   pooled over rows
    end_to_end          : sum(n_within) / sum(n_gt)        pooled over rows
    """
    rows = [json.loads(l) for l in jsonl_path.open(encoding="utf-8") if l.strip()]
    if not rows:
        print("no rows to summarize")
        return []
    models = list(rows[0]["models"].keys())
    n = len(rows)
    total_gt = sum(r["n_gt_params"] for r in rows)

    out: list[dict[str, Any]] = []
    for m in models:
        ev = [r["models"][m] for r in rows]
        n_within = sum(e["n_within_tolerance"] for e in ev)
        n_matched = sum(e["n_matched"] for e in ev)
        out.append({
            "model": m,
            "parse_fails": sum(1 for e in ev if not e.get("parse_ok")),
            "avg_pred_params": sum(e["n_pred_params"] for e in ev) / n,
            "avg_matched": n_matched / n,
            "mean_frac_reported": sum(e["fraction_reported"] for e in ev) / n,
            "mean_frac_within20": sum(e["fraction_within_tolerance"] for e in ev) / n,
            "global_accuracy": (n_within / n_matched) if n_matched else 0.0,
            "end_to_end": (n_within / total_gt) if total_gt else 0.0,
        })

    hdr = (f"\n{'Model':24s} {'Parse':>6} {'AvgPred':>8} {'AvgMatch':>9} "
           f"{'FracRep':>8} {'FracW20':>8} {'GlobAcc':>8} {'End2End':>8}")
    print(f"\nTable 9 — parameter estimation ({n} samples, "
          f"{total_gt} ground-truth parameters)")
    print(hdr)
    print("-" * len(hdr))
    for r in out:
        print(f"{r['model']:24s} {r['parse_fails']:6d} "
              f"{r['avg_pred_params']:8.1f} {r['avg_matched']:9.2f} "
              f"{r['mean_frac_reported']:8.3f} {r['mean_frac_within20']:8.3f} "
              f"{r['global_accuracy']:8.3f} {r['end_to_end']:8.4f}")

    csv_path = jsonl_path.with_name("parameter_evaluation_summary.csv")
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model"] + [label for _, label in SUMMARY_COLUMNS])
        for r in out:
            w.writerow([r["model"]] + [r[key] for key, _ in SUMMARY_COLUMNS])
    print(f"\nWrote summary -> {csv_path}")
    return out


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bench", default="benchmarking_data",
                    help="ground-truth dir (absolute, or relative to the repository root)")
    ap.add_argument("--infer", default="inference_outputs",
                    help="inference-outputs dir (absolute, or relative to the repository root)")
    ap.add_argument("--out", default=None,
                    help="output JSONL (default: <infer>/parameter_evaluation.jsonl)")
    ap.add_argument("--models", nargs="*", default=None,
                    help="restrict to these model subdirs (default: all)")
    ap.add_argument("--summarize-only", action="store_true",
                    help="re-print Table 9 from an existing JSONL without recomputing")
    return ap.parse_args()


def _resolve(p: str) -> Path:
    path = Path(p)
    return path if path.is_absolute() else (ROOT / path)


if __name__ == "__main__":
    args = parse_args()
    BENCH = _resolve(args.bench)
    INFER = _resolve(args.infer)
    OUT = _resolve(args.out) if args.out else INFER / "parameter_evaluation.jsonl"
    MODELS = args.models if args.models else [
        d.name for d in sorted(INFER.iterdir())
        if d.is_dir() and not d.name.startswith("_")
    ]
    if args.summarize_only:
        summarize(OUT)
    else:
        main()
