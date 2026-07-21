# LogoTrace Evaluation Baseline

**Engine:** VTracer (spline, hierarchical=stacked)
**Samples:** 8
**Date:** 2026-07-21

---

## v3 (fixed — background as first-class mask class)

Metric changes from v2:
- Evaluation palette = pipeline inks + `estimate_background()` color
- Background is a first-class mask → ink↔bg silhouette edges are measured
- Fullbleed samples (bg ≈ ink, or <22% near-white pixels): no background class
- Sanity check: if binarized masks are identical and output has nodes → degenerate error
- IoU worst always includes background if present

| # | Sample | Size | Mode | Inks | IoU mean | IoU worst | IoU bg | Chamfer (px) | Nodes | SVG KB |
|---|--------|------|------|------|----------|-----------|--------|-------------|-------|--------|
| 1 | `sample_01.jpg` | 1340×1276 | fullbleed | #010101, #f5c753 | 0.9806 | 0.9800 | — | 0.20 | 3251 | 112.6 |
| 2 | `sample_02.jpg` | 904×946 | paper | #95ac9b, #2b663c | 0.6614 | 0.0718 | 0.9876 | 0.28 | 801 | 28.0 |
| 3 | `sample_03.jpg` | 1840×988 | paper | #232122 | 0.9251 | 0.8663 | 0.9839 | 0.48 | 2887 | 98.2 |
| 4 | `sample_04.jpg` | 902×1316 | paper | #c0c2c2, #cb3c33 | 0.6946 | 0.1207 | 0.9816 | 0.14 | 3454 | 108.1 |
| 5 | `sample_05.jpg` | 1640×2160 | paper | #191919, #666666, #d7d7d7, #a7a7a7 | 0.5610 | 0.0463 | 0.9956 | 0.56 | 2056 | 71.6 |
| 6 | `sample_06.jpg` | 1978×2046 | paper | #1a1819, #c53837 | 0.9717 | 0.9464 | 0.9935 | 0.97 | 733 | 27.8 |
| 7 | `sample_07.jpg` | 3456×1556 | fullbleed | #bbc1d8, #e17c3a, #0a1e7b, #594163 | 0.7775 | 0.1343 | — | 0.16 | 2190 | 79.2 |
| 8 | `sample_08.jpg` | 1506×790 | paper | #1e1e1c | 0.9657 | 0.9567 | 0.9747 | 0.51 | 3819 | 129.0 |

### v3 Aggregate

- **IoU mean:** 0.817 (min: 0.56, max: 0.98)
- **IoU bg mean:** 0.986 (min: 0.975, max: 0.996)
- **Chamfer mean:** 0.41 px (min: 0.14, max: 0.97)
- **Nodes mean:** 2399
- **Fullbleed:** 2 samples
- **Degenerate:** 0 samples (sanity check passed)

### v3 Worst Chamfer

- `sample_06.jpg` — Chamfer 0.97 px, IoU 0.97 (ink edges drift despite tight fill coverage)
- `sample_05.jpg` — Chamfer 0.56 px, IoU 0.56 (4-color gradient logo, crush mismatch)
- `sample_08.jpg` — Chamfer 0.51 px, IoU 0.97 (single-ink, silhouette edge drift)

### Per-sample delta vs v2

| Sample | v2 IoU | v3 IoU | Δ | Why |
|--------|--------|--------|---|-----|
| sample_01 | 0.981 | 0.981 | — | fullbleed, same palette |
| sample_02 | 0.956 | **0.661** | −0.30 | bg mask reveals green/white boundary mismatch |
| sample_03 | 1.000 | **0.925** | −0.08 | was degenerate (1-color, no bg → trivial 1.0) |
| sample_04 | 0.987 | **0.695** | −0.29 | bg mask reveals logo silhouette mismatch |
| sample_05 | 0.688 | **0.561** | −0.13 | bg + 4-color crush amplifies differences |
| sample_06 | 0.987 | **0.972** | −0.02 | bg well-preserved, ink edges main issue |
| sample_07 | 0.778 | 0.778 | — | fullbleed, same palette |
| sample_08 | 1.000 | **0.966** | −0.03 | was degenerate (1-color, no bg → trivial 1.0) |

---

## v2 (invalid — background-blind, preserved for history)

Bug: nearest-palette binarization with no background entry assigns background
pixels to an ink. Single-ink samples score IoU=1.0 trivially. Silhouette invisible.

| # | Sample | IoU mean | IoU worst | Chamfer (px) |
|---|--------|----------|-----------|-------------|
| 1 | sample_01 | 0.981 | 0.980 | 0.20 |
| 2 | sample_02 | 0.956 | 0.925 | 0.35 |
| 3 | sample_03 | 1.000 | 1.000 | 0.00 |
| 4 | sample_04 | 0.987 | 0.982 | 0.09 |
| 5 | sample_05 | 0.688 | 0.046 | 0.55 |
| 6 | sample_06 | 0.987 | 0.975 | 0.44 |
| 7 | sample_07 | 0.778 | 0.134 | 0.16 |
| 8 | sample_08 | 1.000 | 1.000 | 0.00 |

---

## v1 (invalid — mask matching bug, preserved for history)

Bug: double-`prepare_for_trace` palette mismatch + fuzzy radius matching.

| # | Sample | IoU mean | IoU worst | Chamfer (px) |
|---|--------|----------|-----------|-------------|
| 1 | sample_01 | 0.975 | 0.964 | 2.34 |
| 2 | sample_02 | 0.439 | 0.031 | 2.70 |
| 3 | sample_03 | 0.926 | 0.926 | 2.77 |
| 4 | sample_04 | 0.485 | 0.001 | 3.82 |
| 5 | sample_05 | 0.452 | 0.020 | 1.37 |
| 6 | sample_06 | 0.971 | 0.960 | 1.24 |
| 7 | sample_07 | 0.519 | 0.014 | 2.91 |
| 8 | sample_08 | 0.970 | 0.970 | 2.33 |
