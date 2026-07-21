# Manual QA — real samples (2026-07-21)

Engine: VTracer 0.6.4 via LogoTrace pipeline (`--colors 4`, default flags).
Command: `python -m src.cli samples/X.jpg -o output/X.svg -c 4`

| File | Size in | SVG out | Notes |
|------|---------|---------|--------|
| sample_01.jpg | 190 KB / 1340x1276 | ~121 KB | Traced OK |
| sample_02.jpg | 57 KB / 904x946 | ~27 KB | Traced OK |
| sample_03.jpg | 136 KB / 1840x988 | ~98 KB | Traced OK |
| sample_04.jpg | 121 KB / 902x1316 | ~100 KB | Traced OK |
| sample_05.jpg | 133 KB / 1640x2160 | ~66 KB | Traced OK |
| sample_06.jpg | 117 KB / 1978x2046 | ~27 KB | Traced OK |
| sample_07.jpg | 212 KB / 3456x1556 | ~90 KB | Traced OK |
| sample_08.jpg | 97 KB / 1506x790 | ~141 KB | Traced OK |

## Automated

- `pytest -q` → **13 passed**
- `GET /health` → 200 `{"status":"ok"}`
- `POST /vectorize` on sample_02 → SVG

## Visual / geometry (operator)

Samples are **JPEG photos/scans of logos** (not clean transparent PNG masters). Expect:

- Background paper/noise may become extra shapes
- JPEG compression edges add path complexity
- True alpha not present in these inputs (JPEG)

**Recommendation for next QA round:** if possible, also drop clean PNG masters with transparent background for fairer geometry check.

## Pass bar for MVP engineering

- Pipeline stable on all 8 files: **YES**
- Editable flat SVG produced: **YES** (paths + fills)
- Product-quality vs Vectorizer.AI: **not scored visually yet** — Tim to open `output/*.svg` in browser/Inkscape

## Follow-ups (not done)

- Tune filter_speckle / color_precision per logo type
- Optional bg removal preprocess for photo-on-paper samples
- Web UI after Tim visual OK
- PDF export post-MVP
