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

- Per-color binary trace (potrace) for organic/08-class inputs
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
pytest -q
```

---

## Project Structure

```
/root/logotrace/
  README.md
  LICENSE, NOTICE
  bin/vtracer
  docs/   SPEC, RESEARCH, DECISIONS, QA-NOTES, plans/
  input/          # sample_*.jpg + ui_* debug dumps
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
    geometry.py    # post-pass geom (off by default)
    pdf_export.py
    pipeline.py
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

See `docs/DECISIONS.md` ADR-1…16 and `docs/QA-NOTES.md`.

---

## Status snapshot

| Item | State |
|------|--------|
| Repo | `/root/logotrace` local git `main` |
| Latest commit | `e88ad20` (full-width UI) |
| API | `127.0.0.1:8095` (logotrace.service) |
| Web UI | https://idealabs.co/trace/ |
| Quality (user) | ~4–4.5/5 |
| Tests | 20 passed |
