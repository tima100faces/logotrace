# LogoTrace

Flat logo raster → **RGB vector PDF** tracer.  
Drop a JPEG/PNG, get a clean PDF ready for print and Illustrator.

**Pipeline:** upscale (auto) → background detection (always kept) → unified auto palette → remap → VTracer spline → PDF

---

## Quick start

```bash
cd /root/logotrace
source .venv/bin/activate
pip install -r requirements.txt

# CLI
PYTHONPATH=. python -m src.cli input/logo.jpg -o output/logo.pdf

# CLI with upscale off (escape hatch)
PYTHONPATH=. LOGOTRACE_UPSCALE=off python -m src.cli input/logo.jpg -o output/logo.pdf

# API
uvicorn src.api:app --host 127.0.0.1 --port 8095
curl -s -F file=@logo.jpg -F palette=auto http://127.0.0.1:8095/vectorize -o out.pdf
```

**Web UI:** https://idealabs.co/trace/ — paste/drop, Auto|1–8 colors, canvas preview + zoom/pan.

**Deploy note:** the API runs as `logotrace.service`. After every merge to
main: `systemctl restart logotrace` — otherwise the web UI serves stale code.

---

## Architecture

```
Raster (JPEG/PNG)
  │
  ├─ [src/pipeline.py]     upscale preprocess (default: auto toward 3072px cap)
  │   └─ Lanczos resize, effective factor ≤ 2x, skip if < 1.05x,
  │      pixel-unit VTracer thresholds scaled by effective factor
  │
  ├─ [src/colors.py]      unified auto palette (ADR-22/23)
  │   ├─ estimate_background()    bg detected, ALWAYS kept as bottom layer
  │   ├─ mass filter              clusters ≥ 3% of dominant
  │   ├─ weighted-HSL merge       w_L=2 w_S=1 w_H=1, thr 0.18 — never hue-only
  │   ├─ N = survivors, 1..8      (auto mode)
  │   └─ gradient crush           mass anchor; cannot drop mass colors;
  │                               bimodal guard kept as safety net
  │
  ├─ [src/preprocess.py]   brand-color remap
  │   └─ remap_to_palette()   snap pixels to measured colors (bg incl.)
  │
  ├─ [src/tracer_vtracer.py]  subprocess → VTracer 0.6.4
  │   └─ spline mode, color, mild speckle
  │
  ├─ [src/postprocess.py]  svgo optimize
  │
  ├─ [src/geometry.py]     path simplify (off by default, experimental — ADR-14)
  │
  ├─ [src/pdf_export.py]   SVG → PDF (rsvg-convert / cairosvg)
  │
  ├─ [src/verify.py]       self-check: raster output, assert non-blank
  │
  ├─ [src/pipeline.py]     orchestrator: vectorize_file / vectorize_bytes
  │
  ├─ [src/debug_save.py]   persist input/ui_* + output/ui_* + last.*
  │
  ├─ [src/api.py]          FastAPI: POST /vectorize, GET /health, static UI
  ├─ [src/cli.py]          Typer: --colors, --colors-mode, --geom, --format
  └─ [src/config.py]       VTracer binary path, thresholds
```

### Palette = Auto / Manual K

| `palette` | Mode | Behavior |
|-----------|------|----------|
| `auto`    | auto-N | bg + N inks, N = mass/HSL survivors, 1..8 (ADR-23) |
| `1`–`16`  | exact K | bg + exactly K inks by mass, **no crush** |

Background occupies a reserved slot outside the ink limit (ADR-22).
Response headers: `X-LogoTrace-Colors`, `X-LogoTrace-Colors-Mode`.

### Geometry post-pass

`--geom off` (default) keeps raw VTracer splines. `basic`/`strict` are
experimental and may facet curves. A separate geometry_fit refinement pass
was built, benchmarked and **removed** (no visible benefit — ADR-21).

---

## Evaluation

```bash
python -m src.eval input/ --colors 4
```

Canonical sample set: `input/sample_01..sample_11`. Metrics: area-weighted
IoU (background is a first-class mask class), Chamfer on color-transition
edges, nodes, SVG size. The log prints both `iou_mean` and `iou_aw`;
**`iou_aw` is the quality aggregate** — see
[`docs/EVAL-BASELINE.md`](docs/EVAL-BASELINE.md). Pixel metrics are blind
to smoothness and palette semantics — owner visual review is part of
acceptance for palette/curve changes.

---

## Project structure

```
logotrace/
  bin/vtracer                  # bundled 0.6.4 Linux x86_64
  src/
    api.py, cli.py, config.py
    colors.py                  # unified auto palette (ADR-22/23)
    preprocess.py, tracer_vtracer.py, pipeline.py
    pdf_export.py, postprocess.py, geometry.py
    verify.py, debug_save.py, disks.py
    eval.py                    # benchmark harness
  static/                      # Web UI (html/css/js + pdf.js)
  tests/                       # pytest
  docs/                        # SPEC, DECISIONS, EVAL-BASELINE, QA-NOTES
  deploy/                      # nginx snippet for idealabs.co/trace
  input/                       # sample_01..sample_11 + ui_* debug dumps
  output/                      # gitignored PDFs/SVGs
```

---

## CLI reference

```bash
# auto (default): auto-N palette (ADR-23)
python -m src.cli input.jpg -o out.pdf

# manual exact K: no crush — dual gray survives
python -m src.cli input/sample_05.jpg -o out.pdf -c 2 --colors-mode exact

# debug SVG path geometry
python -m src.cli input.jpg -o out.svg --format svg
```

---

## API

```
POST /vectorize
  file=@logo.jpg    (multipart, required)
  palette=auto|1-16 (default auto; UI exposes 1-8)
  format=pdf|svg    (default pdf)

GET  /health
GET  /              (Web UI)
```

---

## Documentation

- [`docs/SPEC.md`](docs/SPEC.md) — product spec, user stories, success criteria
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — architecture decision records (ADR-1…23)
- [`docs/EVAL-BASELINE.md`](docs/EVAL-BASELINE.md) — benchmark baselines and metric history
- [`docs/QA-NOTES.md`](docs/QA-NOTES.md) — manual QA rounds, sample results
- [`docs/RESEARCH.md`](docs/RESEARCH.md) — tracer selection research
- [`docs/ai-preflight-vision-qa.md`](docs/ai-preflight-vision-qa.md) — AI vision QA proposal

---

## License

GPL-3.0-or-later. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
