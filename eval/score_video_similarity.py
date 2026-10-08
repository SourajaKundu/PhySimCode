"""Compute video similarity between rendered model outputs and reference videos.

Two metrics per pair:
  - DINOv2: per-frame embedding, mean-pooled, cosine similarity
  - X-CLIP: video-level embedding (whole-clip), cosine similarity

Reference videos:  benchmarking_data/<engine>/<experiment>/<sample_id>/video.mp4
Rendered videos:   eval_outputs/<model>/runs/<engine>/<experiment>/<sample_id>/video.mp4

Output:           eval_outputs/<model>/video_similarity.jsonl  (one row per sample)

Usage:
  python eval/score_video_similarity.py \\
      --models gpt_5_mini gemma_3_12b_it grok_4_fast_reasoning \\
      --device cuda:0 --batch 8

  # smoke-test 10 samples
  python eval/score_video_similarity.py \\
      --models gpt_5_mini --limit 10
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image

REF_ROOT = Path(os.environ.get("PHYSIM_BENCH_ROOT", "benchmarking_data"))
EVAL_ROOT = Path(os.environ.get("PHYSIM_EVAL_ROOT", "eval_outputs"))

# Frame-sampling targets — DINOv2 is per-frame, X-CLIP wants exactly 8 frames.
DINO_FRAMES = 16            # uniform sample, mean-pooled
XCLIP_FRAMES = 8            # X-CLIP base expects 8
TARGET_RES = 224            # both models accept 224x224


# ──────────────────────────────────────────────────────────────────────────
# Video reading
# ──────────────────────────────────────────────────────────────────────────

def read_video_uniform(path: Path, num_frames: int, resolution: int = TARGET_RES) -> Optional[np.ndarray]:
    """Read a video and return `num_frames` frames sampled uniformly,
    each resized to (resolution, resolution) RGB. Returns None on failure.

    Aspect handling: letterbox to square (preserves all content)."""
    import imageio.v3 as iio
    try:
        frames = list(iio.imiter(str(path), plugin="pyav"))
    except Exception as e:
        return None
    if not frames:
        return None
    n = len(frames)
    # uniform sampling
    if n >= num_frames:
        idxs = np.linspace(0, n - 1, num_frames).astype(int)
    else:
        # repeat last frame to pad
        idxs = list(range(n)) + [n - 1] * (num_frames - n)
    sampled = []
    for i in idxs:
        f = frames[i]
        if f.dtype != np.uint8:
            f = (f * 255).clip(0, 255).astype(np.uint8) if f.max() <= 1.0 else f.astype(np.uint8)
        # Letterbox to square then resize
        h, w = f.shape[:2]
        if h != w:
            side = max(h, w)
            pad_h = (side - h) // 2
            pad_w = (side - w) // 2
            sq = np.zeros((side, side, 3), dtype=np.uint8)
            sq[pad_h:pad_h + h, pad_w:pad_w + w] = f if f.ndim == 3 else np.stack([f] * 3, axis=-1)
            f = sq
        elif f.ndim == 2:
            f = np.stack([f] * 3, axis=-1)
        elif f.shape[-1] == 4:
            f = f[..., :3]
        # Resize
        img = Image.fromarray(f).resize((resolution, resolution), Image.BILINEAR)
        sampled.append(np.array(img))
    return np.stack(sampled, axis=0)


# ──────────────────────────────────────────────────────────────────────────
# DINOv2 encoder
# ──────────────────────────────────────────────────────────────────────────

class DinoEncoder:
    def __init__(self, device: torch.device, model_id: str = "facebook/dinov2-base"):
        from transformers import AutoModel, AutoImageProcessor
        self.proc = AutoImageProcessor.from_pretrained(model_id)
        self.model = AutoModel.from_pretrained(model_id).to(device).eval()
        self.device = device

    @torch.no_grad()
    def encode(self, frames: np.ndarray) -> np.ndarray:
        """frames: (T, H, W, 3) uint8 → (D,) embedding (mean over frames, L2-normed)."""
        pil = [Image.fromarray(f) for f in frames]
        inp = self.proc(images=pil, return_tensors="pt").to(self.device)
        out = self.model(**inp)
        feats = out.pooler_output if hasattr(out, "pooler_output") and out.pooler_output is not None \
                else out.last_hidden_state[:, 0]
        emb = F.normalize(feats, dim=-1).mean(0)
        emb = F.normalize(emb, dim=-1)
        return emb.cpu().numpy()


# ──────────────────────────────────────────────────────────────────────────
# X-CLIP encoder (video-level)
# ──────────────────────────────────────────────────────────────────────────

class XClipEncoder:
    """X-CLIP video encoder.

    transformers 4.57 has a bug in `get_video_features` (returns tuple instead of
    object with .pooler_output). We work around it by calling the full forward
    with a dummy text token and reading `video_embeds`.
    """
    def __init__(self, device: torch.device, model_id: str = "microsoft/xclip-base-patch16"):
        from transformers import XCLIPModel, XCLIPProcessor
        self.proc = XCLIPProcessor.from_pretrained(model_id)
        self.model = XCLIPModel.from_pretrained(model_id).to(device).eval()
        self.device = device

    @torch.no_grad()
    def encode(self, frames: np.ndarray) -> np.ndarray:
        """frames: (T, H, W, 3) uint8, T MUST be 8 → (D,) video embedding."""
        # image_processor expects list[list[frames]] (one inner list per video)
        sampled = [list(frames)]
        inp = self.proc(text=["a video"], images=sampled,
                        return_tensors="pt", padding=True)
        inp = {k: v.to(self.device) for k, v in inp.items()}
        out = self.model(**inp)
        emb = F.normalize(out.video_embeds[0], dim=-1)
        return emb.cpu().numpy()


# ──────────────────────────────────────────────────────────────────────────
# Pair iteration
# ──────────────────────────────────────────────────────────────────────────

def find_pairs(model: str, engines: Optional[list[str]] = None,
               experiments: Optional[list[str]] = None) -> list[dict]:
    pairs = []
    runs_root = EVAL_ROOT / model / "runs"
    if not runs_root.exists():
        return pairs
    for vid in sorted(runs_root.rglob("video.mp4")):
        rel = vid.relative_to(runs_root)
        parts = rel.parts  # (engine, experiment, sample_id, "video.mp4")
        if len(parts) < 4:
            continue
        eng, exp, sid = parts[0], parts[1], parts[2]
        if engines and eng not in engines: continue
        if experiments and exp not in experiments: continue
        ref = REF_ROOT / eng / exp / sid / "video.mp4"
        if not ref.exists():
            # not all rendered videos have a paired reference
            continue
        pairs.append({"model": model, "engine": eng, "experiment": exp,
                      "sample_id": sid, "rendered": vid, "reference": ref})
    return pairs


def cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--engines", nargs="*", default=None,
                    help="restrict to engines (default: all)")
    ap.add_argument("--experiments", nargs="*", default=None,
                    help="restrict to experiments (default: all)")
    ap.add_argument("--device", default="cuda:0" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--limit", type=int, default=None,
                    help="for testing — only score the first N pairs per model")
    ap.add_argument("--shard", type=int, default=0,
                    help="shard index (0-indexed); used with --num-shards for parallel runs")
    ap.add_argument("--num-shards", type=int, default=1,
                    help="total number of shards to split the work across")
    ap.add_argument("--no-resume", dest="resume", action="store_false",
                    help="recompute even if rows already exist")
    ap.add_argument("--dino-model", default="facebook/dinov2-base")
    ap.add_argument("--xclip-model", default="microsoft/xclip-base-patch16")
    ap.add_argument("--no-xclip", action="store_true",
                    help="skip X-CLIP (DINOv2 only)")
    ap.add_argument("--no-dino", action="store_true",
                    help="skip DINOv2 (X-CLIP only)")
    args = ap.parse_args()

    device = torch.device(args.device)
    print(f"[video_sim] device={device}", flush=True)

    print(f"[video_sim] loading DINOv2 ({args.dino_model})", flush=True)
    dino = None if args.no_dino else DinoEncoder(device, args.dino_model)
    print(f"[video_sim] loading X-CLIP   ({args.xclip_model})", flush=True)
    xclip = None if args.no_xclip else XClipEncoder(device, args.xclip_model)

    for model in args.models:
        out_path = EVAL_ROOT / model / "video_similarity.jsonl"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Resume support
        done_keys = set()
        if args.resume and out_path.exists():
            for line in out_path.read_text().splitlines():
                line = line.strip()
                if not line: continue
                try:
                    r = json.loads(line)
                    done_keys.add((r["engine"], r["experiment"], r["sample_id"]))
                except Exception:
                    pass

        pairs = find_pairs(model, args.engines, args.experiments)
        # Apply shard filter — deterministic by sorted order, take every Nth
        if args.num_shards > 1:
            pairs = [p for i, p in enumerate(pairs) if i % args.num_shards == args.shard]
        pending = [p for p in pairs if (p["engine"], p["experiment"], p["sample_id"]) not in done_keys]
        if args.limit is not None:
            pending = pending[:args.limit]

        print(f"\n=== {model} ===  pairs={len(pairs)}  done={len(done_keys)}  pending={len(pending)}", flush=True)
        if not pending:
            continue

        f_out = out_path.open("a", buffering=1)
        n_done = n_err = 0
        t0 = time.time()
        for i, p in enumerate(pending):
            row = {"scorer": "video_similarity",
                   "model": model,
                   "engine": p["engine"],
                   "experiment": p["experiment"],
                   "sample_id": p["sample_id"],
                   "rendered_path": str(p["rendered"]),
                   "reference_path": str(p["reference"])}
            try:
                # DINOv2: 16 frames, mean-pooled
                if dino is not None:
                    R = read_video_uniform(p["rendered"], DINO_FRAMES)
                    T = read_video_uniform(p["reference"], DINO_FRAMES)
                    if R is None or T is None:
                        raise RuntimeError("frame read failed")
                    dr = dino.encode(R); dt = dino.encode(T)
                    row["dino_cosine"] = cos(dr, dt)
                # X-CLIP: 8 frames, video-level
                if xclip is not None:
                    R8 = read_video_uniform(p["rendered"], XCLIP_FRAMES)
                    T8 = read_video_uniform(p["reference"], XCLIP_FRAMES)
                    if R8 is None or T8 is None:
                        raise RuntimeError("frame read failed (xclip)")
                    xr = xclip.encode(R8); xt = xclip.encode(T8)
                    row["xclip_cosine"] = cos(xr, xt)
                row["status"] = "ok"
                n_done += 1
            except Exception as e:
                row["status"] = "error"
                row["error"] = f"{type(e).__name__}: {e}"
                n_err += 1
            f_out.write(json.dumps(row) + "\n")

            if (i + 1) % 50 == 0 or (i + 1) == len(pending):
                rate = (i + 1) / (time.time() - t0)
                print(f"  [{i+1}/{len(pending)}]  ok={n_done}  err={n_err}  {rate:.2f}/s", flush=True)

        f_out.close()
        print(f"  → wrote {out_path}", flush=True)


if __name__ == "__main__":
    main()
