---
license: other
base_model: Skywork/Skywork-o1-Open-PRM-Qwen-2.5-1.5B
tags:
  - onnx
  - int8
  - process-reward-model
  - math
pipeline_tag: text-classification
---

# Skywork PRM 1.5B — ONNX int8 (AMRE floor verifier)

Quantized ONNX export of **Skywork-o1-Open-PRM-Qwen-2.5-1.5B**, used as the
always-available process-reward-model (PRM) **floor** in the AMRE engine.

- **Base model:** `Skywork/Skywork-o1-Open-PRM-Qwen-2.5-1.5B`
- **Format:** ONNX, dynamic int8 quantization (`optimum` export + `quantize_dynamic`)
- **Size:** ~1.6 GB — fits the engine Space CPU (16 GB)
- **Role:** scores each reasoning step; failover target when the preferred
  Colab 7B PRM (`Qwen/Qwen2.5-Math-PRM-7B`) is unavailable.

## How it's produced
See `export_prm_onnx.py` in this folder: export → `quantize_dynamic` (int8) →
benchmark tokens/s before/after.

## How it's consumed
`prm_onnx.py` in the engine downloads this repo via `snapshot_download` and runs
**one batched ONNX call per chain** (never per token), intra-op threads = 4.
Step scores are turned into green/amber/red badges by percentile vs the cached
score distribution (p40 / p15), and the `argmin` step is flagged "weakest link".

## Notes / caveats
- Raw PRM scores saturate, so badges use **percentile** thresholds, not raw cutoffs.
- Correlation against the 7B PRM is reported by `prm_score_correlation.py`
  (Spearman ρ); ρ ≥ 0.8 → badges shown normally.
- License follows the base model's terms — review before redistribution.
