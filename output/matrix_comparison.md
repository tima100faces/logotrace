# Variant Comparison

**Samples:** 9
**Date:** 2026-07-22

## IoU aw

| Sample | vtracer+upscale | vtracer+upscale+fit |
|--------|--------|--------|
| `sample_01` | 0.9889 | 0.9867 |
| `sample_02` | 0.9780 | 0.9770 |
| `sample_03` | 0.9749 | 0.9740 |
| `sample_04` | 0.9666 | 0.9657 |
| `sample_05` | 0.9884 | 0.9879 |
| `sample_06` | 0.9927 | 0.9919 |
| `sample_07` | 0.9938 | 0.9932 |
| `sample_08` | 0.9742 | 0.9733 |
| `sample_09` | 0.9787 | 0.9758 |

## Chamfer (px)

| Sample | vtracer+upscale | vtracer+upscale+fit |
|--------|--------|--------|
| `sample_01` | 0.11 | 0.13 |
| `sample_02` | 0.16 | 0.17 |
| `sample_03` | 0.41 | 0.44 |
| `sample_04` | 0.15 | 0.16 |
| `sample_05` | 0.17 | 0.19 |
| `sample_06` | 0.42 | 0.50 |
| `sample_07` | 0.16 | 0.18 |
| `sample_08` | 0.36 | 0.37 |
| `sample_09` | 0.24 | 0.27 |

## Nodes

| Sample | vtracer+upscale | vtracer+upscale+fit |
|--------|--------|--------|
| `sample_01` | 4309 | 4309 |
| `sample_02` | 3234 | 3234 |
| `sample_03` | 3286 | 3286 |
| `sample_04` | 10404 | 10404 |
| `sample_05` | 1789 | 1789 |
| `sample_06` | 927 | 927 |
| `sample_07` | 1556 | 1556 |
| `sample_08` | 4763 | 4763 |
| `sample_09` | 718 | 718 |

## Time (s)

| Sample | vtracer+upscale | vtracer+upscale+fit |
|--------|--------|--------|
| `sample_01` | 5.6 | 7.3 |
| `sample_02` | 1.9 | 3.4 |
| `sample_03` | 2.5 | 4.3 |
| `sample_04` | 3.0 | 9.8 |
| `sample_05` | 6.3 | 6.4 |
| `sample_06` | 5.1 | 5.2 |
| `sample_07` | 4.5 | 5.2 |
| `sample_08` | 2.1 | 4.9 |
| `sample_09` | 0.6 | 0.8 |

## Aggregate (mean across samples)

| Metric | vtracer+upscale | vtracer+upscale+fit |
|--------|--------|--------|
| IoU mean | 0.8527 | 0.8488 |
| IoU aw | 0.9818 | 0.9806 |
| Chamfer | 0.24 | 0.27 |
| Nodes | 3443 | 3443 |
| SVG KB | 114.8 | 151.9 |
| Time (s) | 3.5 | 5.3 |
