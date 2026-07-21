# LogoTrace Evaluation Baseline

**Engine:** VTracer (spline, hierarchical=stacked)
**Samples:** 8
**Date:** 2026-07-21

## Per-Sample Metrics

| # | Sample | Size | Colors | Palette | IoU mean | IoU worst | Chamfer (px) | Nodes | SVG KB |
|---|--------|------|--------|---------|----------|-----------|-------------|-------|--------|
| 1 | `sample_01.jpg` | 1340×1276 | 4 | #010101, #f5c753 | 0.9750 | 0.9642 | 2.34 | 3251 | 112.6 |
| 2 | `sample_02.jpg` | 904×946 | 4 | #95ac9b, #2b663c | 0.4389 | 0.0307 | 2.70 | 801 | 28.0 |
| 3 | `sample_03.jpg` | 1840×988 | 4 | #232122 | 0.9256 | 0.9256 | 2.77 | 2887 | 98.2 |
| 4 | `sample_04.jpg` | 902×1316 | 4 | #c0c2c2, #cb3c33 | 0.4848 | 0.0010 | 3.82 | 3454 | 108.1 |
| 5 | `sample_05.jpg` | 1640×2160 | 4 | #191919, #666666, #d7d7d7, #a7a7a7 | 0.4515 | 0.0201 | 1.37 | 2056 | 71.6 |
| 6 | `sample_06.jpg` | 1978×2046 | 4 | #1a1819, #c53837 | 0.9706 | 0.9603 | 1.24 | 733 | 27.8 |
| 7 | `sample_07.jpg` | 3456×1556 | 4 | #bbc1d8, #e17c3a, #0a1e7b, #594163 | 0.5186 | 0.0143 | 2.91 | 2190 | 79.2 |
| 8 | `sample_08.jpg` | 1506×790 | 4 | #1e1e1c | 0.9701 | 0.9701 | 2.33 | 3819 | 129.0 |

## Aggregate

- **IoU mean:**  0.7169  (min: 0.4389, max: 0.9750)
- **Chamfer mean:** 2.44 px  (min: 1.24, max: 3.82)
- **Nodes mean:**  2399  (min: 733, max: 3819)
- **SVG size mean:** 81.8 KB  (min: 27.8, max: 129.0)

## Worst Chamfer (curve-quality problem cases)

- `sample_04.jpg` — Chamfer 3.82 px, IoU mean 0.4848
- `sample_07.jpg` — Chamfer 2.91 px, IoU mean 0.5186
- `sample_03.jpg` — Chamfer 2.77 px, IoU mean 0.9256
