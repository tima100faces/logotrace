# Engine Comparison: VTracer vs Subpixel (Stage 3)

**Samples:** 8
**Date:** 2026-07-21

## IoU aw

| Sample | vtracer+upscale | subpixel | subpix+upscale |
|--------|----------------|----------|---------------|
| `sample_01` | 0.9889 | 0.0133 | 0.0068 |
| `sample_02` | 0.9780 | 0.9595 | 0.9761 |
| `sample_03` | 0.9749 | 0.0959 | 0.0959 |
| `sample_04` | 0.9666 | 0.9342 | 0.9640 |
| `sample_05` | 0.9884 | 0.9353 | 0.0608 |
| `sample_06` | 0.9927 | 0.7695 | 0.7697 |
| `sample_07` | 0.9938 | 0.0024 | 0.0024 |
| `sample_08` | 0.9742 | 0.3616 | 0.3616 |

## Chamfer (px)

| Sample | vtracer+upscale | subpixel | subpix+upscale |
|--------|----------------|----------|---------------|
| `sample_01` | 0.11 | 0.77 | 0.26 |
| `sample_02` | 0.16 | 0.59 | 0.30 |
| `sample_03` | 0.41 | 0.00 | 0.00 |
| `sample_04` | 0.15 | 0.58 | 0.21 |
| `sample_05` | 0.17 | 0.50 | 0.35 |
| `sample_06` | 0.42 | 93.85 | 93.92 |
| `sample_07` | 0.16 | 0.52 | 0.52 |
| `sample_08` | 0.36 | 0.00 | 0.00 |

## Nodes

| Sample | vtracer+upscale | subpixel | subpix+upscale |
|--------|----------------|----------|---------------|
| `sample_01` | 4309 | 6025 | 9245 |
| `sample_02` | 3234 | 1353 | 1789 |
| `sample_03` | 3286 | 0 | 0 |
| `sample_04` | 10404 | 5237 | 6879 |
| `sample_05` | 1789 | 3308 | 3887 |
| `sample_06` | 927 | 650 | 818 |
| `sample_07` | 1556 | 2237 | 2237 |
| `sample_08` | 4763 | 0 | 0 |

## Time (s)

| Sample | vtracer+upscale | subpixel | subpix+upscale |
|--------|----------------|----------|---------------|
| `sample_01` | 3.9 | 3.6 | 8.1 |
| `sample_02` | 1.7 | 1.2 | 2.6 |
| `sample_03` | 2.5 | 0.9 | 1.9 |
| `sample_04` | 2.7 | 2.5 | 5.3 |
| `sample_05` | 4.7 | 4.6 | 6.7 |
| `sample_06` | 4.6 | 3.1 | 6.2 |
| `sample_07` | 4.5 | 5.9 | 7.2 |
| `sample_08` | 2.0 | 0.6 | 1.8 |

## Aggregate (mean across samples)

| Metric | vtracer+upscale | subpixel | subpix+upscale |
|--------|----------------|----------|---------------|
| IoU mean | 0.8403 | 0.2805 | 0.2801 |
| IoU aw | 0.9822 | 0.5090 | 0.4047 |
| Chamfer | 0.24 | 12.10 | 11.94 |
| Nodes | 3784 | 2351 | 3107 |
| SVG KB | 126.1 | 110.1 | 152.3 |
| Time (s) | 3.3 | 2.8 | 5.0 |
