# Spec: LogoTrace

## Objective

Local tool: **flat logo rasters (mostly JPEG)** → **RGB vector PDF** for print/Illustrator workflow.

Not a Vectorizer.AI clone. Strength = brand-color fidelity + clean enough geometry for flat 1–N color marks.

**User:** Tim  
**Why:** Paid AI tracers overkill for flat logos; need controllable local pipeline + PDF out.

### User stories

1. Drop/paste a JPEG logo scan → get RGB PDF with fills close to original brand colors.
2. `POST /vectorize` with `format=pdf` → PDF bytes.
3. Ink colors: Auto (auto-N, 1..8) or manual K (exact, 1..16) via `palette` param; background always kept as bottom layer.
4. Canvas preview with zoom/pan; Download PDF.
5. If PNG has real alpha → keep transparency through SVG stage (PDF may flatten per renderer).

### Success criteria (MVP — met 2026-07-21)

- [x] CLI: JPEG/PNG/WebP → **PDF** (default)
- [x] HTTP `GET /health` → 200
- [x] HTTP `POST /vectorize` → PDF by default
- [x] Palette: `palette=auto|N`
- [x] Brand-color extract + mass-aware remap + gradient crush (auto only)
- [x] pytest green (20)
- [x] Web UI: light, English, paste/drop, canvas preview + zoom/pan (idealabs.co/trace)
- [x] Debug dumps: `input/ui_*` + `output/ui_*` + `last.*` (cap 500, no time purge)
- [x] README + QA notes on real samples
- [x] User visual score on problem set ≈ **4.0–4.5 / 5** (2026-07-21)

### Closed problems

- **Palette loss on complex inputs (ex-problem #1)** — CLOSED 2026-07-22.
  sample_10 aw 0.4989 → 0.9834. Fixed by ADR-22 (background always kept,
  paper/fullbleed removed, mass-based crush anchor) + ADR-23 (unified
  auto palette: weighted-HSL merge, mass colors undroppable). Owner
  verdict on real labels: "colors are an order of magnitude better".

### Post-MVP

- **Open problem #2 (now top priority): thin-stroke wobble / edge burrs** —
  sample_05 line art (2–4 px strokes): both stroke edges traced
  independently → lumpy varying-width lines; micro-ripple on letter
  edges of dense labels. Levers by cost: (a) stronger upscale for
  thin-stroke inputs (limited by VTracer memory on full color);
  (b) per-color binary trace experiment (below); (c) differentiable
  rasterizer (large project, postponed — ADR-18). Centerline tracing =
  separate large project, not approved.
- **Candidate experiment: per-color binary trace** — palette → one binary
  mask per ink → trace each mask separately → stack layers. Rationale:
  binary masks are memory-cheap, allowing 4x+ upscale beyond the color
  pipeline's 2x/9.5M px cap — targets problem #2; edge-mix colors cannot
  enter the trace. Known risks: seams between independently traced masks
  (would need trapping logic; stacked VTracer avoids this by
  construction). Acceptance per ADR-17 rule: benchmark vs baseline on
  the canonical set — wins or it's gone.
- Auto-N refinements only via ADR-23 acceptance set re-run
- Optional CMYK (Illustrator downstream)

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11 |
| API | FastAPI + uvicorn |
| CLI | Typer |
| Color | `src/colors.py` (numpy) — unified auto palette (ADR-22/23) |
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
systemctl restart logotrace   # MANDATORY after every merge to main
```

---

## Project Structure

```
/root/logotrace/
  README.md
  LICENSE, NOTICE
  bin/vtracer
  docs/   SPEC, RESEARCH, DECISIONS, EVAL-BASELINE, QA-NOTES, plans/
  input/          # sample_01..sample_11 + ui_* debug dumps
  output/          # gitignored PDFs/SVGs
  deploy/          # nginx snippet
  static/          # index.html, styles.css, app.js (Auto|1-8 control)
  src/
    api.py         # FastAPI + / + /static mount
    cli.py
    colors.py      # unified auto palette (ADR-22/23)
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
2. Colors: **Auto (auto-N, ADR-23) / Manual K (exact)**, default Auto; background always kept (ADR-22)
3. Alpha: preserve when present; JPEG is main input
4. Output: **PDF only as product deliverable**; SVG debug (API only, no UI button)
5. PDF color space: **RGB** (Illustrator for further work)
6. **Web UI:** https://idealabs.co/trace/ — systemd + nginx; restart service after every merge
7. Every pipeline change is benchmarked on the full canonical sample set
   (no exclusions); palette and curve-quality changes additionally require
   owner visual review — metrics are blind to smoothness and palette
   semantics.
8. Roles: Claude = architect (tasks contain final design decisions, no
   open choices for the agent), DeepSeek V4 Pro agent = implementation,
   Tim = product decisions. Every agent report includes a "Regressions"
   section (each metric worse than baseline, explained — or explicit
   "none").

See `docs/DECISIONS.md` ADR-1…23 and `docs/QA-NOTES.md`.

---

## Status snapshot

| Item | State |
|------|--------|
| Repo | `/root/logotrace` git `main` + github.com/tima100faces/logotrace |
| Latest commit | `f5fb537` (unified auto palette) + docs sync |
| API | `127.0.0.1:8095` (logotrace.service) |
| Web UI | https://idealabs.co/trace/ (Auto|1–8) |
| Quality (user) | "colors an order of magnitude better"; remaining: edge burrs (problem #2) |
| Baseline | f5fb537, 11 samples, IoU aw 0.9830 (see EVAL-BASELINE.md) |
| Tests | pytest green (20) |
