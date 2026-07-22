# Variant Comparison

**Samples:** 11
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
| `sample_10` | 0.4989 | 0.4986 |
| `sample_11` | 0.9884 | 0.9879 |

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
| `sample_10` | 0.16 | 0.16 |
| `sample_11` | 0.17 | 0.19 |

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
| `sample_10` | 6531 | 6531 |
| `sample_11` | 1789 | 1789 |

## Time (s)

| Sample | vtracer+upscale | vtracer+upscale+fit |
|--------|--------|--------|
| `sample_01` | 3.5 | 6.9 |
| `sample_02` | 1.7 | 3.4 |
| `sample_03` | 2.4 | 4.3 |
| `sample_04` | 2.7 | 9.2 |
| `sample_05` | 4.8 | 6.6 |
| `sample_06` | 4.7 | 5.8 |
| `sample_07` | 4.6 | 5.4 |
| `sample_08` | 2.0 | 4.9 |
| `sample_09` | 0.6 | 0.7 |
| `sample_10` | 2.0 | 6.9 |
| `sample_11` | 4.9 | 6.9 |

## Aggregate (mean across samples)

| Metric | vtracer+upscale | vtracer+upscale+fit |
|--------|--------|--------|
| IoU mean | 0.7972 | 0.7934 |
| IoU aw | 0.9385 | 0.9375 |
| Chamfer | 0.23 | 0.25 |
| Nodes | 3573 | 3573 |
| SVG KB | 116.7 | 156.0 |
| Time (s) | 3.1 | 5.5 |
