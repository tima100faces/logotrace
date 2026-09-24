# LogoTrace

Flat logo raster → **RGB vector PDF** tracer.  
Drop a JPEG/PNG, get a clean PDF ready for print and Illustrator.

**Pipeline:** upscale (auto) → brand-color detection → palette remap → VTracer spline → PDF

---

## Quick start

Deployed on **mainframe**: code `/srv/hermes/projects/logotrace`, live tree `/srv/sites/logotrace`,
virtualenv inside the live tree (built by `deploy/live-venv.sh`).

```bash
cd /srv/hermes/projects/logotrace

# Development environment (the deployed one is built by deploy/live-venv.sh)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# CLI
PYTHONPATH=. .venv/bin/python -m src.cli input/logo.jpg -o output/logo.pdf

# CLI with upscale off (escape hatch)
PYTHONPATH=. LOGOTRACE_UPSCALE=off .venv/bin/python -m src.cli input/logo.jpg -o output/logo.pdf

# API — the deployed instance listens on 127.0.0.1:8301 behind nginx
curl -s -F file=@input/logo.jpg -F palette=auto http://127.0.0.1:8301/vectorize -o out.pdf
```

**Deploy:** `sudo /usr/local/sbin/hermes-site-ctl sync logotrace` — copies the staged tree into the
live one and restarts the unit. After a fresh `create`, or after a distro upgrade, run
`bash deploy/live-venv.sh` first.

**Web UI:** https://trace.idealabs.co/ — paste/drop, Auto|1–4 colors, canvas preview + zoom/pan.

---

## Architecture

```
Raster (JPEG/PNG)
  │
  ├─ [src/pipeline.py]     upscale preprocess (default: auto toward 3072px cap)
  │   └─ Lanczos resize, effective factor ≤ 2x, skip if < 1.05x,
  │      pixel-unit VTracer thresholds scaled by effective factor
  │
  ├─ [src/colors.py]      palette analysis
  │   ├─ estimate_background()       paper vs fullbleed
  │   ├─ _mass_aware_select()        dust → nearest major
  │   ├─ collapse_gradient_ramps()   gray ramp → one ink
  │   └─ bimodal guard               undo crush if two mass peaks
  │
  ├─ [src/preprocess.py]   brand-color remap
  │   └─ remap_to_palette()   snap pixels to measured colors
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
  │                        cap 500 runs, no time purge
  │
  ├─ [src/api.py]          FastAPI: POST /vectorize, GET /health, static UI
  ├─ [src/cli.py]          Typer: --colors, --colors-mode, --geom, --format
  └─ [src/config.py]       VTracer binary path, thresholds
```

### Palette = Auto / Manual K

| `palette` | Internal mode | Gradient crush |
|-----------|---------------|----------------|
| `auto`    | up_to ≤ 4     | yes (bimodal guard overrides) |
| `1`–`16`  | exact K       | **no** — exact N inks by mass |

Response headers: `X-LogoTrace-Colors`, `X-LogoTrace-Colors-Mode`.

### Colors: gradient crush + bimodal guard

Gray/same-hue lightness ramps collapse to one solid ink (sample_08 banding → solid circle).  
**Bimodal guard:** if crush produces 1 fill but histogram shows two mass peaks >10% separated by ≥60 lightness units → auto-correct to mass-aware palette without crush. Prevents dark-background logos with light text from becoming solid rectangles.

### Geometry post-pass

`--geom off` (default) keeps raw VTracer splines. `basic`/`strict` are experimental and may facet curves — use only for testing.
A separate geometry_fit refinement pass was built, benchmarked and **removed** (no visible benefit — see ADR-21).

---

## Evaluation

```bash
python -m src.eval input/ --colors 4
```

Canonical sample set: `input/sample_01..sample_10`. Metrics: area-weighted IoU
(background is a first-class mask class), Chamfer on color-transition edges,
nodes, SVG size. The log prints both `iou_mean` and `iou_aw`; **`iou_aw` is
the quality aggregate** — see [`docs/EVAL-BASELINE.md`](docs/EVAL-BASELINE.md).

---

## Project structure

```
logotrace/
  bin/vtracer                  # bundled 0.6.4 Linux x86_64
  src/
    api.py, cli.py, config.py
    colors.py                  # palette, crush, bimodal guard
    preprocess.py, tracer_vtracer.py, pipeline.py
    pdf_export.py, postprocess.py, geometry.py
    verify.py, debug_save.py, disks.py
    eval.py                    # benchmark harness
  static/                      # Web UI (html/css/js + pdf.js)
  tests/                       # pytest
  docs/                        # STATUS, PRODUCT, PLAN, DECISIONS, PITFALLS + SPEC, EVAL-BASELINE, QA-NOTES
  deploy/                      # live-venv.sh (builds the service venv in the live tree)
  input/                       # sample_01..sample_11 + ui_* debug dumps
  output/                      # gitignored PDFs/SVGs
```

The live copy lives at `/srv/sites/logotrace` and is owned by `site-logotrace`; it is only ever
written by `hermes-site-ctl sync`. The service virtualenv is built there by `deploy/live-venv.sh`,
because the service account cannot read `/srv/hermes` — see `docs/PITFALLS.md`.

---

## CLI reference

```bash
# auto (default): up_to 4 + gradient crush (bimodal guard)
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
  palette=auto|1-4  (default auto)
  format=pdf|svg    (default pdf)

GET  /health
GET  /              (Web UI)
```

---

## Documentation

- [`AGENTS.md`](AGENTS.md) — working agreement: roles, levels, git, verification
- [`docs/STATUS.md`](docs/STATUS.md) — current state, what is broken, next action
- [`docs/PRODUCT.md`](docs/PRODUCT.md) — why it exists, who it is for, what it must do
- [`docs/PLAN.md`](docs/PLAN.md) — the migration to mainframe, parked items, risks
- [`docs/DECISIONS.md`](docs/DECISIONS.md) — architecture decision records (ADR-1…24)
- [`docs/PITFALLS.md`](docs/PITFALLS.md) — what already broke and how not to repeat it
- [`docs/SPEC.md`](docs/SPEC.md) — product spec, user stories, success criteria
- [`docs/EVAL-BASELINE.md`](docs/EVAL-BASELINE.md) — benchmark baselines and metric history
- [`docs/QA-NOTES.md`](docs/QA-NOTES.md) — manual QA rounds, sample results
- [`docs/RESEARCH.md`](docs/RESEARCH.md) — tracer selection research
- [`docs/ai-preflight-vision-qa.md`](docs/ai-preflight-vision-qa.md) — AI vision QA proposal

---

## License

GPL-3.0-or-later. See [`LICENSE`](LICENSE) and [`NOTICE`](NOTICE).
