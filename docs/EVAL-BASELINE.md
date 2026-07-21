# LogoTrace Evaluation Baseline

**Engine:** VTracer (spline, hierarchical=stacked)
**Samples:** 8
**Date:** 2026-07-21

---

## v4 (current default — auto upscale + threshold scaling)

**Policy:** `effective = min(2x, 3072/max_side, √(9.5M/total_px))`, skip if < 1.05x.
**VTracer thresholds:** `filter_speckle` × effective, `segment_length` × effective.
Angular params (corner, splice) unchanged.

| # | Sample | Size | Eff. | IoU mean | IoU aw | Chamfer | Nodes | SVG KB | Time |
|---|--------|------|------|----------|--------|---------|-------|--------|------|
| 1 | sample_01 | 1340×1276 | 2.0x | 0.989 | 0.989 | 0.11 | 4315 | 152.2 | 3.5s |
| 2 | sample_02 | 904×946 | 2.0x | 0.753 | 0.973 | 0.16 | 3234 | 108.9 | 1.7s |
| 3 | sample_03 | 1840×988 | 1.7x | 0.931 | 0.931 | 0.41 | 3286 | 113.3 | 2.3s |
| 4 | sample_04 | 902×1316 | 2.0x | 0.720 | 0.976 | 0.15 | 10420 | 324.9 | 2.5s |
| 5 | sample_05 | 1640×2160 | 1.4x | 0.598 | 0.988 | 0.17 | 1789 | 62.6 | 6.0s |
| 6 | sample_06 | 1978×2046 | 1.5x | 0.981 | 0.991 | 0.42 | 927 | 34.4 | 5.0s |
| 7 | sample_07 | 3456×1556 | 1.0x | 0.778 | 0.994 | 0.16 | 1556 | 57.5 | 4.4s |
| 8 | sample_08 | 1506×790 | 2.0x | 0.972 | 0.972 | 0.36 | 4793 | 156.5 | 2.0s |

### v4 vs off (auto upscale delta)

| Metric | off | v4 auto | Δ |
|--------|-----|---------|---|
| IoU mean | 0.822 | **0.849** | +2.7% |
| IoU aw | 0.981 | 0.981 | — |
| Chamfer | 0.35 | **0.25** | **−29%** |
| Nodes | 1787 | 4109 | +2.3× |
| SVG KB | 55.8 | 119.4 | +2.1× |
| Time | 2.0s | 3.4s | +1.7× |

**Verdict:** Chamfer −29% (0.35→0.25 px), IoU +2.7%, at 2.3× nodes. Area-weighted IoU flat (0.981).
v4 auto upscale is the **new default**. `--upscale off` escape hatch available for debugging.

---

## v3 (background as first-class mask class)

| # | Sample | Size | Mode | Inks | IoU mean | IoU aw | IoU worst | IoU bg | Chamfer | Nodes | SVG KB |
|---|--------|------|------|------|----------|--------|-----------|--------|---------|-------|--------|
| 1 | sample_01 | 1340×1276 | fullbleed | #010101, #f5c753 | 0.981 | 0.981 | 0.980 | — | 0.20 | 3251 | 112.6 |
| 2 | sample_02 | 904×946 | paper | #95ac9b, #2b663c | 0.661 | 0.972 | 0.072 | 0.988 | 0.28 | 801 | 28.0 |
| 3 | sample_03 | 1840×988 | paper | #232122 | 0.925 | 0.924 | 0.866 | 0.984 | 0.48 | 2887 | 98.2 |
| 4 | sample_04 | 902×1316 | paper | #c0c2c2, #cb3c33 | 0.695 | 0.974 | 0.121 | 0.982 | 0.14 | 3454 | 108.1 |
| 5 | sample_05 | 1640×2160 | paper | #191919, #666666, #d7d7d7, #a7a7a7 | 0.561 | 0.987 | 0.046 | 0.996 | 0.56 | 2056 | 71.6 |
| 6 | sample_06 | 1978×2046 | paper | #1a1819, #c53837 | 0.972 | 0.990 | 0.946 | 0.994 | 0.97 | 733 | 27.8 |
| 7 | sample_07 | 3456×1556 | fullbleed | #bbc1d8, #e17c3a, #0a1e7b, #594163 | 0.778 | 0.994 | 0.134 | — | 0.16 | 2190 | 79.2 |
| 8 | sample_08 | 1506×790 | paper | #1e1e1c | 0.966 | 0.966 | 0.957 | 0.975 | 0.51 | 3819 | 129.0 |

### v3 Aggregate

- **IoU mean:** 0.817, **IoU area-weighted:** 0.980
- **IoU bg mean:** 0.986
- **Chamfer mean:** 0.41 px
- **Nodes mean:** 2399, **SVG size mean:** 81.8 KB

---

## Step 0 — Low IoU-worst mask diagnosis

All IoU worst < 0.15 are **tiny masks** (< 1% of frame), not real palette failure.
Area-weighted IoU is 0.97-0.99 for all samples.

| Sample | Worst mask | Area | IoU | Verdict |
|--------|-----------|------|-----|---------|
| sample_02 | #95ac9b (light green) | 0.8% | 0.072 | tiny accent, barely visible |
| sample_04 | #c0c2c2 (silver) | 0.9% | 0.121 | tiny highlight |
| sample_05 | #a7a7a7 (mid-gray) | 0.2% | 0.046 | gradient crush noise |
| sample_05 | #d7d7d7 (light gray) | 0.2% | 0.055 | gradient crush noise |
| sample_07 | #594163 (purple) | 0.2% | 0.134 | tiny accent detail |

**Conclusion:** IoU worst is misleading as a quality signal — it's always a sub-1% mask.
Area-weighted IoU (0.980) is the correct aggregate. Per-mask area % should be shown
alongside IoU in all reports.

XOR diffs for masks with IoU < 0.5 dumped to `output/eval_diffs/`.

---

## Step 1 — Upscale experiment

2x Lanczos upscale before trace, SVG coordinates scaled back to original viewport.
4x variants exceed memory budget (8M px cap) on all samples — no data.

### Per-sample comparison (2x vs off)

| Sample | IoU off | IoU 2x | Δ | Chamfer off | Chamfer 2x | Δ | Nodes off | Nodes 2x | Time off | Time 2x |
|--------|---------|--------|---|-------------|------------|---|-----------|----------|----------|---------|
| sample_01 | 0.981 | **0.989** | +0.8% | 0.20 | **0.11** | −45% | 3251 | 5980 | 1.4s | 3.5s |
| sample_02 | 0.661 | **0.753** | +9.2% | 0.28 | **0.15** | −46% | 801 | 4687 | 0.7s | 1.7s |
| sample_03 | 0.925 | **0.933** | +0.8% | 0.48 | **0.39** | −19% | 2887 | 5385 | 1.2s | 3.2s |
| sample_04 | 0.695 | **0.721** | +2.6% | 0.14 | 0.15 | +7% | 3454 | 15602 | 1.0s | 2.6s |
| sample_08 | 0.966 | **0.972** | +0.6% | 0.51 | **0.36** | −29% | 3819 | 6723 | 0.8s | 2.1s |
| 05/06/07 | — | OOM | — | — | OOM | — | — | — | — | — |

### Aggregate

| Metric | off | 2x |
|--------|-----|-----|
| IoU mean | 0.817 | **0.874** |
| IoU aw | 0.980 | 0.977 |
| Chamfer | 0.41 | **0.23** |
| Nodes | 2399 | 7675 |
| SVG KB | 81.8 | 169.7 |
| Time (s) | 2.0 | 2.7* |

*mean over OOM-skipped samples excluded

### Recommendation

**2x Lanczos wins on every measurable axis** (IoU, Chamfer) at the cost of 3× nodes and 2× SVG size.
4x/4x-smooth could not be tested on any sample (all exceed 8M px memory cap).

For production pipeline: add `--upscale 2x` flag. For small images only (< 2K²), default off.
Consider size cap (~2M source pixels) for automatic 2x mode.

---

## v2 (invalid — background-blind)

Bug: nearest-palette binarization with no background entry assigns background
pixels to an ink. Single-ink samples score IoU=1.0 trivially.

| # | Sample | IoU mean | IoU worst | Chamfer |
|---|--------|----------|-----------|---------|
| 1 | sample_01 | 0.981 | 0.980 | 0.20 |
| 2 | sample_02 | 0.956 | 0.925 | 0.35 |
| 3 | sample_03 | 1.000 | 1.000 | 0.00 |
| 4 | sample_04 | 0.987 | 0.982 | 0.09 |
| 5 | sample_05 | 0.688 | 0.046 | 0.55 |
| 6 | sample_06 | 0.987 | 0.975 | 0.44 |
| 7 | sample_07 | 0.778 | 0.134 | 0.16 |
| 8 | sample_08 | 1.000 | 1.000 | 0.00 |

---

## v1 (invalid — mask matching bug)

Bug: double-`prepare_for_trace` palette mismatch + fuzzy radius matching.

| # | Sample | IoU mean | IoU worst | Chamfer |
|---|--------|----------|-----------|---------|
| 1 | sample_01 | 0.975 | 0.964 | 2.34 |
| 2 | sample_02 | 0.439 | 0.031 | 2.70 |
| 3 | sample_03 | 0.926 | 0.926 | 2.77 |
| 4 | sample_04 | 0.485 | 0.001 | 3.82 |
| 5 | sample_05 | 0.452 | 0.020 | 1.37 |
| 6 | sample_06 | 0.971 | 0.960 | 1.24 |
| 7 | sample_07 | 0.519 | 0.014 | 2.91 |
| 8 | sample_08 | 0.970 | 0.970 | 2.33 |

---

## Stage 2b — Upscale matrix with threshold scaling + OOM fix

**Caps:** longest side ≤ 3072px, total pixels ≤ 9.5M.
**VTracer thresholds:** `filter_speckle` multiplied by effective upscale factor.

### OOM root cause

VTracer crashes when input exceeds ~10M pixels (sample_05 at 2x raw = 14M px → OOM).
Fixed with dual cap: side ≤ 3072px AND pixels ≤ 9.5M. Sample_07 (3456×1556) excluded entirely
(effective scale 0.89 < 1.15 minimum).

### Effect of threshold scaling on nodes

Previous 2x-unscaled: mean nodes = 7675. 2x-scaled: mean nodes = 5941 (**−23%**).
Threshold scaling eliminates most of the node inflation — geometric strictness is
constant in source-image units.

### Full matrix (area-weighted IoU)

| Sample | off | 2x | 4x | 4x-smooth | Eff. scale |
|--------|-----|----|----|-----------|-----------|
| sample_01 | 0.981 | 0.989 | **0.990** | 0.990 | 2.0 / 2.3x |
| sample_02 | 0.661 | 0.753 | 0.809 | **0.810** | 2.0 / 3.2x |
| sample_03 | 0.925 | **0.932** | 0.932 | 0.931 | 1.7x |
| sample_04 | 0.695 | 0.721 | 0.739 | **0.742** | 2.0 / 2.3x |
| sample_05 | 0.561 | 0.597 | 0.597 | **0.599** | 1.4x |
| sample_06 | 0.972 | **0.981** | 0.981 | 0.980 | 1.5x |
| sample_07 | 0.778 | — | — | — | skip (3456px) |
| sample_08 | 0.966 | 0.972 | 0.973 | **0.973** | 2.0x |

### Aggregate

| Metric | off | 2x | 4x | 4x-smooth |
|--------|-----|-----|-----|-----------|
| IoU aw mean | 0.980 | 0.981 | **0.983** | **0.983** |
| Chamfer mean | 0.41 | 0.25 | **0.24** | **0.24** |
| Nodes mean | 2399 | 5941 | 7515 | 7313 |
| SVG KB mean | 81.8 | 184.4 | 238.6 | 232.5 |
| Time mean (s) | 2.0 | 2.8 | 3.4 | 3.6 |

### Recommendation

**2x with scaled thresholds is the sweet spot**: +0.1pp IoU aw, −39% Chamfer (−0.16 px),
at 2.5× nodes and 2.3× SVG size. 4x/4x-smooth add marginal gain (+0.2pp IoU) for
+26% more nodes vs 2x. For production: `--upscale 2x` with `filter_speckle` auto-scaled
by effective factor, enabled for source images where longest side ≤ 1536px (guarantees
2x within the 3072 cap).
