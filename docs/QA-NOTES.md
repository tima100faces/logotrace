# Manual QA — round 2 (2026-07-21)

## Changes since round 1

1. **JPEG-first color pipeline**
   - Extract dominant brand colors from original
   - Remap pixels to those colors before VTracer
   - Modes: `paper` (logo on light scan) vs `fullbleed` (brand field fills frame)
2. **Default deliverable = RGB PDF** (SVG kept for debug via `--format svg`)
3. Lower VTracer speckle filter so thin second strokes survive

## Problem cases (user feedback)

| File | Before | After (engine) | Notes |
|------|--------|----------------|-------|
| sample_02 | hue shift, green washed | paper mode; ink ≈ `#2c673d` (closer to original dark green) | Still effectively 1 brand green + paper |
| sample_06 | 2 colors → 1 | paper; **red + black** kept | Fixed |
| sample_07 | 2 colors → 1 | fullbleed; **navy field + orange** | Fixed (blue is brand field, not paper) |
| sample_08 | hue/gray soup | paper; dark grays dominant | Better blacks; VTracer still splits gray steps — optional later mono path |

## Outputs

- PDF: `/root/logotrace/output/sample_0X.pdf`
- SVG debug: `/root/logotrace/output/sample_0X.svg`

## Automated

- `pytest -q` → 12 passed
- API default `format=pdf` → `%PDF`

## User score (2026-07-21)

After brand-color remap + PDF default: user reports **radical improvement**, estimate in the **4.0–4.5 / 5** band (exact score not pinned).

Problem-set recheck: sample_06/07 multi-color restored; sample_02/08 hue better.