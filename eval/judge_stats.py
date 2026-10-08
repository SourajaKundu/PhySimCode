"""Inter-judge statistics for an eval_results.jsonl: pairwise agreement,
correlation, bias, outlier rates."""
from __future__ import annotations
import argparse, json, statistics, sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _mean(xs):   return statistics.fmean(xs) if xs else float("nan")
def _median(xs): return statistics.median(xs) if xs else float("nan")


def _pearson(xs: List[float], ys: List[float]) -> float:
    n = len(xs)
    if n < 2: return float("nan")
    mx, my = _mean(xs), _mean(ys)
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    if sx == 0 or sy == 0: return float("nan")
    return sxy / ((sx * sy) ** 0.5)


def collect(path: Path, model: str, scorer: str) -> Dict[Tuple, Dict[str, dict]]:
    """Return { (engine, exp, sid): { judge: scores_dict } } for given model+scorer."""
    by_sample: Dict[Tuple, Dict[str, dict]] = defaultdict(dict)
    for line in open(path):
        if not line.strip(): continue
        r = json.loads(line)
        if r.get("model") != model:        continue
        if r.get("scorer") != scorer:      continue
        if r.get("skipped"):               continue
        if r.get("judge_error"):           continue
        if not r.get("scores"):            continue
        key = (r["engine"], r["experiment"], r["sample_id"])
        by_sample[key][r["judge_model"]] = r["scores"]
    # keep only samples where all 3 judges scored
    return {k: v for k, v in by_sample.items() if len(v) >= 2}


def report(by_sample: Dict[Tuple, Dict[str, dict]], scorer_label: str):
    judges = sorted({j for v in by_sample.values() for j in v.keys()})
    n_full = sum(1 for v in by_sample.values() if len(v) == len(judges))
    print(f"\n=== {scorer_label}  judges={judges}  samples_with_all_judges={n_full} / {len(by_sample)} ===")

    # 1) Per-judge means on overall
    print("\n  per-judge mean (averaged over samples where the judge scored)")
    print(f"  {'judge':<25s}  name  stmt  form  over   N")
    for j in judges:
        ns = [v[j]["name"] for v in by_sample.values() if j in v and v[j].get("name") is not None]
        ss = [v[j]["statement"] for v in by_sample.values() if j in v and v[j].get("statement") is not None]
        fs = [v[j]["formula"] for v in by_sample.values() if j in v and v[j].get("formula") is not None]
        os_ = [v[j]["overall"]   for v in by_sample.values() if j in v and v[j].get("overall")   is not None]
        print(f"  {j:<25s}  {_mean(ns):.2f}  {_mean(ss):.2f}  {_mean(fs):.2f}  {_mean(os_):.2f}   {len(os_)}")

    # 2) Pairwise Pearson on overall_score, only over samples where both judges scored
    print("\n  pairwise Pearson r on overall_score")
    for i in range(len(judges)):
        for k in range(i + 1, len(judges)):
            a, b = judges[i], judges[k]
            xs, ys = [], []
            for v in by_sample.values():
                if a in v and b in v and v[a].get("overall") is not None and v[b].get("overall") is not None:
                    xs.append(v[a]["overall"]); ys.append(v[b]["overall"])
            r = _pearson(xs, ys)
            mad = _mean([abs(x - y) for x, y in zip(xs, ys)])
            exact = sum(1 for x, y in zip(xs, ys) if x == y) / max(len(xs), 1)
            within1 = sum(1 for x, y in zip(xs, ys) if abs(x - y) <= 1) / max(len(xs), 1)
            print(f"  {a:<25s} ↔ {b:<25s}  r={r:+.3f}  |Δ|={mad:.2f}  exact={exact:.0%}  ≤1={within1:.0%}  N={len(xs)}")

    # 3) Per-judge bias vs the (other-two) consensus median
    print("\n  per-judge bias vs median-of-other-judges (overall_score)")
    print(f"  {'judge':<25s}  bias    |bias|   N")
    for j in judges:
        diffs = []
        for v in by_sample.values():
            if j not in v or v[j].get("overall") is None: continue
            others = [v[o]["overall"] for o in v if o != j and v[o].get("overall") is not None]
            if not others: continue
            consensus = _median(others)
            diffs.append(v[j]["overall"] - consensus)
        if diffs:
            print(f"  {j:<25s}  {_mean(diffs):+.2f}    {_mean([abs(d) for d in diffs]):.2f}    {len(diffs)}")

    # 4) Outlier rate: judge differs from the median-of-other-two by ≥ 2
    print("\n  outlier rate (this judge ≥2 points away from median of the other two)")
    print(f"  {'judge':<25s}  ≥2-away rate   ≥3-away rate   N")
    for j in judges:
        n2 = n3 = total = 0
        for v in by_sample.values():
            if j not in v or v[j].get("overall") is None: continue
            others = [v[o]["overall"] for o in v if o != j and v[o].get("overall") is not None]
            if len(others) < 2: continue          # only count when both other judges scored
            consensus = _median(others)
            d = abs(v[j]["overall"] - consensus)
            total += 1
            if d >= 2: n2 += 1
            if d >= 3: n3 += 1
        if total:
            print(f"  {j:<25s}  {n2/total:>5.1%}         {n3/total:>5.1%}         {total}")

    # 5) Spread distribution: max−min across all 3 judges per sample
    print("\n  spread (max−min across judges) on overall_score")
    spreads = []
    for v in by_sample.values():
        if len(v) < 2: continue
        xs = [s["overall"] for s in v.values() if s.get("overall") is not None]
        if len(xs) >= 2:
            spreads.append(max(xs) - min(xs))
    from collections import Counter
    hist = Counter(spreads)
    print(f"  N={len(spreads)}  mean={_mean(spreads):.2f}  median={_median(spreads):.0f}  max={max(spreads) if spreads else 0}")
    for s in sorted(hist):
        bar = "#" * min(50, int(60 * hist[s] / len(spreads)))
        print(f"    spread={s}: {hist[s]:>4d} ({hist[s]/len(spreads):>5.1%})  {bar}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in",     dest="inp", required=True)
    ap.add_argument("--model",  required=True)
    args = ap.parse_args()

    p = Path(args.inp)
    print(f"Loading {p} for model={args.model}")
    for scorer in ("law_equivalence", "law_validity"):
        bys = collect(p, args.model, scorer)
        if bys:
            report(bys, scorer)


if __name__ == "__main__":
    main()
