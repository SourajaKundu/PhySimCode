# PhySimCode: A Benchmark and Evaluation Method for Physics Video to Code Generation

[**Website**](https://sourajakundu.github.io/PhySimCode/) · **Paper** (arXiv, coming soon) · [**Dataset**](https://huggingface.co/datasets/SourajaKundu123/PhySimCode)

Can a multimodal LLM watch a 2D or 3D physics simulation, work out the involved physics laws and parameter values, and write code from scratch that regenerates it?

This repository contains the evaluation code for PhySimCode. Given only a video (and the engine name), a model must output (i) a chain-of-thought JSON with the governing physical law and parameter values and (ii) a runnable Python script. We score the law, the code, and the video the code renders.

## Benchmark data

The evaluation set has **2,430 videos**: 162 physics phenomena × 15 samples, drawn from the full 160,614-sample PhySimCode corpus.

| Engine | Folder | Samples | Video |
|---|---|---|---|
| SciPy (2D) | `scipy/` | 1,305 | 360×180, 10 FPS |
| PyBullet (3D) | `kubric/` | 1,125 | 240×240, 10 FPS |

Each sample is `<engine>/<experiment>/<sample_id>/` with `video.mp4`, `simulation_code.py`, `cot.json` and `params.json`.

```bash
pip install -U huggingface_hub
hf download SourajaKundu123/PhySimCode --repo-type dataset --local-dir benchmarking_data
```

## Setup

```bash
conda create -n physimcode python=3.10 -y && conda activate physimcode
pip install -r eval/requirements_eval.txt
pip install PyOpenGL==3.1.7 --no-deps     # pyrender pins an older version that fails on headless EGL
export PYOPENGL_PLATFORM=egl              # headless rendering of the 3D scenes (needs a GPU with EGL)
```

The three LLM judges read their API keys from the environment or from a `.env` file in the repository root:

```bash
OPENAI_API_KEY=...    # GPT-5-Nano
GEMINI_API_KEY=...    # Gemini-2.5-Flash
XAI_API_KEY=...       # Grok-4.1-Fast
```

## 1. Run your model

For every sample, give the model the video frames (10 FPS) and the engine-conditioned prompt from Appendix A.4 of the paper (the engine is the folder name: `scipy` or `kubric`). Write one JSON line per sample to `inference_outputs/<model>/results.jsonl`:

```json
{"model": "my_model", "engine": "scipy", "experiment": "balls_in_basin", "sample_id": "918",
 "raw_output": "<full model response>",
 "parsed_cot": {"simulation": "...", "physical_observation": "...", "physical_law": {"name": "...", "statement": "...", "formula": "..."}, "parameters": {"g": {"value": 9.81, "unit": "m/s^2", "description": "..."}}},
 "parsed_code": "<python source>",
 "parse_ok_cot": true, "parse_ok_code": true}
```

`parsed_cot` and `parsed_code` are the contents of the `@@COT_BEGIN@@ … @@COT_END@@` and `@@CODE_BEGIN@@ … @@CODE_END@@` blocks.

## 2. Score

Run all commands from the repository root.

```bash
# Re-parse chain-of-thought blocks that failed strict JSON parsing
python eval/recover_inference_outputs.py --models my_model

# Law correctness + law equivalence (3 judges), CodeBLEU, and runnability.
# Runnability executes each script and keeps its video in eval_outputs/my_model/runs/
python eval/run_dataset.py --models my_model

# DINOv2 and VideoCLIP similarity between regenerated and input videos
python eval/score_video_similarity.py --models my_model
```

All scores are written to `eval_outputs/my_model/`. Re-running any command resumes where it stopped.

## 3. Reproduce the paper's tables

| Paper | Command |
|---|---|
| Table 3 (law correctness, law equivalence), Table 5 (CodeBLEU, compile / run / video rates) | `python eval/aggregate.py` |
| Table 5 split by engine | `python eval/aggregate_per_engine.py` (add your model to `OPEN` or `CLOSED` at the top) |
| Table 9, Table 5 parameter accuracy (±20%) | `python eval/eval_parameters.py` (Table 5 reports the end-to-end recovery) |
| Table 4 (DINOv2, VideoCLIP) | `python eval/make_video_sim_report.py my_model` |
| Fig. 4 (inter-judge Cohen's κ) | `python eval/compute_kappa.py my_model` |
| Appendix A.9 (judge agreement) | `python eval/judge_stats.py --in eval_outputs/my_model/eval_results.jsonl --model my_model` |
| Per-model summary | `python eval/make_model_report.py my_model` |

The judges score each field on a 0–4 scale; the paper reports these as a 1–5 Likert scale (score + 1).

## Citation

```bibtex
@misc{kundu2026physimcode,
  title  = {PhySimCode: A Benchmark and Evaluation Method for
            Physics Video to Code Generation},
  author = {Kundu, Souraja and Gupta, Aditya and Julin, Joel and
            Zhao, Yizhou and Xie, Liuyue and Jeni, Laszlo A.},
  year   = {2026},
  note   = {arXiv preprint (coming soon)}
}
```

Contact: [sourajak@cs.cmu.edu](mailto:sourajak@cs.cmu.edu). The project website is served from this repository (`index.html`, `assets/`, `data/`, `videos/`).
