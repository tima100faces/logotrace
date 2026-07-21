# LogoTrace Evaluation Baseline

**Engine:** VTracer (spline, hierarchical=stacked)
**Samples:** 8
**Date:** 2026-07-21

---

## v2 (fixed — canonical palette, binarized masks, Hungarian pairing)

Metric changes from v1:
- Palette: single source of truth from `vectorize_to_svg()` (no double-`prepare_for_trace` mismatch)
- Masks: binarize both reference and output by nearest-palette-color snap, THEN exact-match mask
- Pairing: Hungarian assignment by color distance (handles palette permutation)
- Edges: color-transition edges on binarized images (not Sobel on anti-aliased renders)

| # | Sample | Size | Colors | Palette | IoU mean | IoU worst | Unmatched | Chamfer (px) | Nodes | SVG KB |
|---|--------|------|--------|---------|----------|-----------|-----------|-------------|-------|--------|
| 1 | `sample_01.jpg` | 1340×1276 | 2 | #010101, #f5c753 | 0.9806 | 0.9800 | 0 | 0.20 | 3251 | 112.6 |
| 2 | `sample_02.jpg` | 904×946 | 2 | #95ac9b, #2b663c | 0.9559 | 0.9246 | 0 | 0.35 | 801 | 28.0 |
| 3 | `sample_03.jpg` | 1840×988 | 1 | #232122 | 1.0000 | 1.0000 | 0 | 0.00 | 2887 | 98.2 |
| 4 | `sample_04.jpg` | 902×1316 | 2 | #c0c2c2, #cb3c33 | 0.9874 | 0.9815 | 0 | 0.09 | 3454 | 108.1 |
| 5 | `sample_05.jpg` | 1640×2160 | 4 | #191919, #666666, #d7d7d7, #a7a7a7 | 0.6878 | 0.0463 | 0 | 0.55 | 2056 | 71.6 |
| 6 | `sample_06.jpg` | 1978×2046 | 2 | #1a1819, #c53837 | 0.9869 | 0.9752 | 0 | 0.44 | 733 | 27.8 |
| 7 | `sample_07.jpg` | 3456×1556 | 4 | #bbc1d8, #e17c3a, #0a1e7b, #594163 | 0.7775 | 0.1343 | 0 | 0.16 | 2190 | 79.2 |
| 8 | `sample_08.jpg` | 1506×790 | 1 | #1e1e1c | 1.0000 | 1.0000 | 0 | 0.00 | 3819 | 129.0 |

### v2 Aggregate

- **IoU mean:** 0.9220 (min: 0.6878, max: 1.0000)
- **Chamfer mean:** 0.22 px (min: 0.00, max: 0.55)
- **Nodes mean:** 2399 (min: 733, max: 3819)
- **SVG size mean:** 81.8 KB (min: 27.8, max: 129.0)

### v2 Worst Chamfer

- `sample_05.jpg` — Chamfer 0.55 px, IoU 0.69 (4-color gradient logo)
- `sample_06.jpg` — Chamfer 0.44 px, IoU 0.99 (tight coverage, edges drift slightly)
- `sample_02.jpg` — Chamfer 0.35 px, IoU 0.96

---

## v1 (invalid — mask matching bug, preserved for history)

Bug: (a) `_color_mask` with fuzzy radius=20 on anti-aliased renders inflated IoU;
(b) `prepare_for_trace()` called twice with different palettes for ref vs output.
Do not use v1 numbers for decisions.

| # | Sample | IoU mean | IoU worst | Chamfer (px) | Nodes |
|---|--------|----------|-----------|-------------|-------|
| 1 | `sample_01.jpg` | 0.975 | 0.964 | 2.34 | 3251 |
| 2 | `sample_02.jpg` | 0.439 | 0.031 | 2.70 | 801 |
| 3 | `sample_03.jpg` | 0.926 | 0.926 | 2.77 | 2887 |
| 4 | `sample_04.jpg` | 0.485 | 0.001 | 3.82 | 3454 |
| 5 | `sample_05.jpg` | 0.452 | 0.020 | 1.37 | 2056 |
| 6 | `sample_06.jpg` | 0.971 | 0.960 | 1.24 | 733 |
| 7 | `sample_07.jpg` | 0.519 | 0.014 | 2.91 | 2190 |
| 8 | `sample_08.jpg` | 0.970 | 0.970 | 2.33 | 3819 |
