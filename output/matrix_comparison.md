# Variant Comparison

**Samples:** 11
**Date:** 2026-07-21

## IoU aw

| Sample | vtracer+upscale |
|--------|--------|
| `sample_01` | 0.9863 |
| `sample_02` | 0.9888 |
| `sample_03` | 0.9871 |
| `sample_04` | 0.9709 |
| `sample_05` | 0.9883 |
| `sample_06` | 0.9957 |
| `sample_07` | 0.9931 |
| `sample_08` | 0.9896 |
| `sample_09` | 0.9927 |
| `sample_10` | 0.9874 |
| `sample_11` | 0.9713 |

## Chamfer (px)

| Sample | vtracer+upscale |
|--------|--------|
| `sample_01` | 0.14 |
| `sample_02` | 0.08 |
| `sample_03` | 0.20 |
| `sample_04` | 0.13 |
| `sample_05` | 0.15 |
| `sample_06` | 0.27 |
| `sample_07` | 0.16 |
| `sample_08` | 0.14 |
| `sample_09` | 0.10 |
| `sample_10` | 3.71 |
| `sample_11` | 0.17 |

## Nodes

| Sample | vtracer+upscale |
|--------|--------|
| `sample_01` | 4072 |
| `sample_02` | 1616 |
| `sample_03` | 2817 |
| `sample_04` | 9055 |
| `sample_05` | 3405 |
| `sample_06` | 714 |
| `sample_07` | 1649 |
| `sample_08` | 4586 |
| `sample_09` | 432 |
| `sample_10` | 2652 |
| `sample_11` | 5944 |

## Time (s)

| Sample | vtracer+upscale |
|--------|--------|
| `sample_01` | 3.5 |
| `sample_02` | 1.6 |
| `sample_03` | 2.5 |
| `sample_04` | 2.7 |
| `sample_05` | 6.9 |
| `sample_06` | 4.7 |
| `sample_07` | 4.8 |
| `sample_08` | 2.1 |
| `sample_09` | 0.6 |
| `sample_10` | 1.6 |
| `sample_11` | 6.6 |

## Aggregate (mean across samples)

| Metric | vtracer+upscale |
|--------|--------|
| IoU mean | 0.8438 |
| IoU aw | 0.9865 |
| Chamfer | 0.48 |
| Nodes | 3358 |
| SVG KB | 110.8 |
| Time (s) | 3.4 |
