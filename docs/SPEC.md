# Spec: LogoTrace

## Objective

Local tool: **flat logo rasters (mostly JPEG)** → **RGB vector PDF** for print/Illustrator workflow.

Not a Vectorizer.AI clone. Strength = brand-color fidelity + clean enough geometry for flat 1–N color marks.

**User:** Tim  
**Why:** Paid AI tracers overkill for flat logos; need controllable local pipeline + PDF out.

### User stories

1. Drop/paste a JPEG logo scan → get RGB PDF with fills close to original brand colors.
2. `POST /vectorize` with `format=pdf` → PDF bytes.
3. Cap ink colors: Auto (up_to 4) or manual K (exact) via `palette` param.
4. Canvas preview with zoom/pan; Download PDF.
5. If PNG has real alpha → keep transparency through SVG stage (PDF may flatten per renderer).

### Success criteria (MVP — met 2026-07-21)

- [x] CLI: JPEG/PNG/WebP → **PDF** (default)
- [x] HTTP `GET /health` → 200
- [x] HTTP `POST /vectorize` → PDF by default
- [x] Palette: `palette=auto|N` (Auto=up_to 4, N=exact)
- [x] Paper JPEG: bg handled; full-bleed brand field kept
- [x] Brand-color extract + mass-aware remap + gradient crush (auto only)
- [x] pytest green (20)
- [x] Web UI: light, English, paste/drop, canvas preview + zoom/pan (idealabs.co/trace)
- [x] Debug dumps: `input/ui_*` + `output/ui_*` + `last.*` (cap 500, no time purge)
- [x] README + QA notes on real samples
- [x] User visual score on problem set ≈ **4.0–4.5 / 5** (2026-07-21)

### Post-MVP

- **Open problem #1 (top priority): palette loss on complex inputs** —
  sample_10 (green/gold label): large dark-green plate dropped, gold → olive.
  IoU aw 0.4989. **Diagnosed 2026-07-22** (`scripts/diag_sample_10.py`,
  `output/diag_sample_10/`): (a) border-median background = the dark-green
  plate itself (#002507); white_fraction 0.37 ≥ 0.22 → paper mode → 97.4%
  of the plate is replaced with white. Not a code bug — a semantics gap:
  "background = paper white" vs "background = brand field".
  (b) Olive cast = JPEG edge-mix colors (#cad4cc, #7bab84) on the
  gold/green boundary surviving as MAJOR ink clusters → green fringe
  around gold. Gradient crush is NOT at fault (gold anchor #f3e675 kept).
  Fix direction pending product decision (paper/fullbleed rules).
- **Open problem #2: thin-stroke wobble** (sample_05 line art, 2–4 px strokes) —
  both stroke edges traced independently → lumpy varying-width lines.
  First cheap lever: stronger upscale for thin-stroke inputs. Centerline
  tracing = separate large project, not approved.
- **Candidate experiment: per-color binary trace** — palette → one binary
  mask per ink → trace each mask separately (VTracer binary or potrace)
  → stack layers. Rationale: binary masks are memory-cheap, allowing 4x+
  upscale beyond the color pipeline's 2x/9.5M px cap — targets open
  problem #2; edge-mix colors cannot enter the trace (pixels are assigned
  to inks before tracing). Known risks: seams between independently traced
  masks (hairline gaps/overlaps — stacked VTracer avoids this by
  construction; would need trapping logic), and it does not fix palette
  selection itself (garbage palette in → perfectly traced garbage out).
  Sequencing: after open problem #1. Acceptance per ADR-17 rule:
  benchmark vs v4 on the canonical set — wins or it's gone.
- Optional CMYK (Illustrator downstream)
- Auto-N palette size

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11 |
| API | FastAPI + uvicorn |
| CLI | Typer |
| Color | `src/colors.py` (numpy) — mass-aware + gradient crush |
| Preprocess | Pillow + brand remap |
| Tracer | VTracer 0.6.4 (`bin/vtracer`) |
| PDF | rsvg-convert (preferred) / cairosvg |
| UI | Static HTML/CSS/JS + pdf.js (cdnjs) |
| Tests | pytest |
| License | GPL-3.0 |

---

## Commands

```bash
cd /root/logotrace
source .venv/bin/activate
PYTHONPATH=/root/logotrace python -m src.cli input/sample_06.jpg -o output/sample_06.pdf
PYTHONPATH=/root/logotrace python -m src.cli input.jpg -o out.svg --format svg   # debug
PYTHONPATH=/root/logotrace uvicorn src.api:app --host 127.0.0.1 --port 8095
curl -s -F file=@logo.jpg -F palette=auto -F format=pdf http://127.0.0.1:8095/vectorize -o out.pdf
python -m src.eval input/ --colors 4   # benchmark vs docs/EVAL-BASELINE.md
pytest -q
```

---

## Project Structure

```
/root/logotrace/
  README.md
  LICENSE, NOTICE
  bin/vtracer
  docs/   SPEC, RESEARCH, DECISIONS, EVAL-BASELINE, QA-NOTES, plans/
  input/          # sample_01..sample_10 + ui_* debug dumps
  output/          # gitignored PDFs/SVGs
  deploy/          # nginx snippet
  static/          # index.html, styles.css, app.js
  src/
    api.py         # FastAPI + / + /static mount
    cli.py
    colors.py      # palette + remap + crush + resolve_palette_policy
    config.py
    debug_save.py  # ui_* + last.* dumps
    disks.py       # experimental
    eval.py        # benchmark harness (IoU aw, Chamfer, tile-based binarize)
    geometry.py    # post-pass geom (off by default)
    pdf_export.py
    pipeline.py    # orchestrator + v4 upscale policy
    postprocess.py
    preprocess.py
    tracer_vtracer.py
    verify.py      # self-check PDF blankness
  tests/
```

---

## Decisions from Tim (locked)

1. Interfaces: CLI + API + **web UI**
2. Colors: **Auto (up_to) / Manual K (exact)**, default Auto
3. Alpha: preserve when present; JPEG is main input
4. Output: **PDF only as product deliverable**; SVG debug (API only, no UI button)
5. PDF color space: **RGB** (Illustrator for further work)
6. **Web UI:** https://idealabs.co/trace/ — systemd + nginx
7. Every pipeline change is benchmarked on the full canonical sample set
   (no exclusions); curve-quality changes additionally require owner visual
   review — metrics are blind to smoothness.

See `docs/DECISIONS.md` ADR-1…21 and `docs/QA-NOTES.md`.

---

## Status snapshot

| Item | State |
|------|--------|
| Repo | `/root/logotrace` git `main` + github.com/tima100faces/logotrace |
| Latest commit | `ed60ddc` (geometry_fit removed, 10-sample baseline) |
| API | `127.0.0.1:8095` (logotrace.service) |
| Web UI | https://idealabs.co/trace/ |
| Quality (user) | ~4–4.5/5 flat logos; complex labels — open problem #1 |
| Baseline | v4, 10 samples, IoU aw 0.9335 (see EVAL-BASELINE.md) |
| Tests | pytest green |
