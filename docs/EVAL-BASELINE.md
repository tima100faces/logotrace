# LogoTrace Evaluation Baseline

**Engine:** VTracer (spline, hierarchical=stacked)
**Canonical sample set:** sample_01..sample_11 (11 files)
**Baseline commit:** `f5fb537` (unified auto palette, ADR-22/23)
**Date:** 2026-07-22

---

## Reading the metrics: `iou_mean` vs `iou_aw`

The eval log prints both per sample. `iou_mean` is a plain average over all
color masks — tiny accent masks (< 1% of frame) with low IoU drag it down
hard (see Step 0 in History). `iou_aw` is area-weighted and is **the correct
aggregate** for quality tracking. Do not compare `iou_mean` from logs
against `iou_aw` from matrices — they are different metrics by design.

Pixel metrics are necessary but not sufficient: three regressions in this
project improved metrics while degrading visual quality. Owner visual
review is part of acceptance for palette and curve changes (SPEC locked
decision #7, ADR-23).

---

## Canonical baseline — `f5fb537`, 11 samples (2026-07-22)

**Pipeline:** preprocess → auto upscale (≤ 2x, caps: side 3072 / 9.5M px,
thresholds scaled) → background detection (always kept as bottom layer,
ADR-22) → unified auto palette (mass ≥ 3% dominant → weighted-HSL merge
w_L=2/w_S=1/w_H=1 thr 0.18 → N survivors 1..8 → crush, mass colors
undroppable; ADR-23) → VTracer spline stacked → svgo → PDF.
Run: `python -m src.eval input/ --colors 4` (auto path ignores the cap).

| # | Sample | IoU aw | Chamfer | Auto N | Auto palette |
|---|--------|--------|---------|--------|--------------|
| 1 | sample_01 | 0.9889 | 0.1 | 1 | #010101 |
| 2 | sample_02 | 0.9745 | 0.2 | 3 | #b5c9bb #678a71 #2b663c |
| 3 | sample_03 | 0.9871 | 0.2 | 1 | #232122 |
| 4 | sample_04 | 0.9520 | 0.2 | 3 | #e29d9a #cb3c33 #e9c8c5 |
| 5 | sample_05 | 0.9885 | 0.2 | 4 | #191919 #666666 #d7d7d7 #a7a7a7 |
| 6 | sample_06 | 0.9957 | 0.3 | 2 | #1a1819 #c53837 |
| 7 | sample_07 | 0.9940 | 0.1 | 3 | #fefefe #e17c3a #7682b4 |
| 8 | sample_08 | 0.9896 | 0.1 | 1 | #272725 |
| 9 | sample_09 | 0.9866 | 0.1 | 3 | #a6aeb3 #ff9900 #5d646e |
| 10 | sample_10 | 0.9834 | 0.1 | 2 | #fefefe #f3e675 |
| 11 | sample_11 | 0.9732 | 0.1 | 5 | #fdfefd #ab3b2e #6d3c23 #e27339 #f9d048 |

**Aggregate (computed from the table):** IoU aw **0.9830** | Chamfer 0.15 px.
(Nodes/SVG aggregates were not recorded for this run — capture them on the
next benchmark.)

**Notes:**
- sample_11 = multi-ink bread label, added 2026-07-22 (was briefly named
  sample_12). Represents the "complex label" class.
- Open problem #1 (palette loss, ex-sample_10 aw 0.4989) is CLOSED by
  ADR-22 + ADR-23: 0.4989 → 0.9834.
- Accepted trade-offs vs pre-refactor: sample_02 −0.014 (extra
  intermediate green), sample_04 −0.028 (pink hue shift) — see ADR-23.
- History aggregates below were computed on 8–10 sample sets and are not
  directly comparable.

---

# History (superseded)

## 10-sample canonical baseline, 2026-07-22 (pre-ADR-22, superseded)

v4 pipeline with paper/fullbleed split still in place; geometry_fit removed.

| # | Sample | IoU mean | IoU aw | Chamfer | Nodes | Time |
|---|--------|----------|--------|---------|-------|------|
| 1 | sample_01 | 0.9889 | 0.9889 | 0.11 | 4309 | 3.5s |
| 2 | sample_02 | 0.7527 | 0.9780 | 0.16 | 3234 | 1.6s |
| 3 | sample_03 | 0.9313 | 0.9749 | 0.41 | 3286 | 2.2s |
| 4 | sample_04 | 0.7204 | 0.9666 | 0.15 | 10404 | 2.6s |
| 5 | sample_05 | 0.5981 | 0.9884 | 0.17 | 1789 | 5.1s |
| 6 | sample_06 | 0.9810 | 0.9927 | 0.42 | 927 | 4.6s |
| 7 | sample_07 | 0.7781 | 0.9938 | 0.16 | 1556 | 4.4s |
| 8 | sample_08 | 0.9722 | 0.9742 | 0.36 | 4763 | 2.0s |
| 9 | sample_09 | 0.9515 | 0.9787 | 0.24 | 718 | 0.6s |
| 10 | sample_10 | 0.4965 | 0.4989 | 0.16 | 6531 | 2.0s |

Aggregate: IoU mean 0.8171 | IoU aw 0.9335 | Chamfer 0.23 px | Nodes 3752.
sample_10 failure here motivated ADR-22. Intermediate states between this
table and the canonical baseline: `d3be21d` (bg kept, aw 0.9850),
`4c58039` (mass anchor, aw 0.9853), `6cc2163` (first auto-N, rejected —
see ADR-23).

sample_11 (old numbering) was removed 2026-07-22 as a byte-duplicate of
sample_05; the name was later reused for the bread label.

---

## v4 (8-sample run, 2026-07-21 — superseded)

**Policy:** `effective = min(2x, 3072/max_side, √(9.5M/total_px))`, skip if < 1.05x.
**VTracer thresholds:** `filter_speckle` × effective, `segment_length` × effective.

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
| Time | 2.0s | 3.4s | +1.7× |

**Verdict:** v4 auto upscale is the default. `--upscale off` escape hatch available.

---

## Step 0 — Low IoU-worst mask diagnosis (2026-07-21)

All IoU worst < 0.15 are **tiny masks** (< 1% of frame), not real palette failure.
Area-weighted IoU is the correct aggregate; per-mask area % should be shown
alongside IoU in reports. (Details of v1–v3 metric evolution and the upscale
matrix are preserved in git history of this file, commits `2b0e5ad`..`8823675`.)
