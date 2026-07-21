# Spec: LogoTrace

## Objective

Local tool: **flat logo rasters (mostly JPEG)** → **RGB vector PDF** for print/Illustrator workflow.

Not a Vectorizer.AI clone. Strength = brand-color fidelity + clean enough geometry for flat 1–N color marks.

**User:** Tim  
**Why:** Paid AI tracers overkill for flat logos; need controllable local pipeline + PDF out.

### User stories

1. Drop a JPEG logo scan → get RGB PDF with fills close to original brand colors.
2. `POST /vectorize` with `format=pdf` → PDF bytes.
3. Cap ink colors with `--colors N` (up to N; default 4).
4. If PNG has real alpha → keep transparency through SVG stage (PDF may flatten per renderer).

### Success criteria (current MVP — largely met 2026-07-21)

- [x] CLI: JPEG/PNG/WebP → **PDF** (default)
- [x] HTTP `GET /health` → 200
- [x] HTTP `POST /vectorize` → PDF by default (`format=svg` optional)
- [x] `--colors N` = max ink colors (default **4**)
- [x] Paper JPEG: bg handled; full-bleed brand field kept (`paper` / `fullbleed` modes)
- [x] Brand-color extract + remap before trace
- [x] pytest green
- [x] README + QA notes on real samples
- [x] User visual score on problem set ≈ **4.0–4.5 / 5** (2026-07-21)

### Post-MVP

- Web UI
- Tighter mono path (sample_08 gray banding)
- Optional CMYK (explicitly not required — Illustrator downstream)
- Auto-N palette size

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11 |
| API | FastAPI + uvicorn |
| CLI | Typer |
| Color | `src/colors.py` (numpy) — paper/fullbleed |
| Preprocess | Pillow + brand remap |
| Tracer | VTracer 0.6.4 (`bin/vtracer`) |
| PDF | rsvg-convert (preferred) / cairosvg |
| Tests | pytest |
| License | GPL-3.0 |

---

## Commands

```bash
cd /root/logotrace
source .venv/bin/activate
PYTHONPATH=/root/logotrace python -m src.cli samples/sample_06.jpg -o output/sample_06.pdf
PYTHONPATH=/root/logotrace python -m src.cli input.jpg -o out.svg --format svg   # debug
PYTHONPATH=/root/logotrace uvicorn src.api:app --host 127.0.0.1 --port 8095
curl -s -F file=@logo.jpg -F colors=4 -F format=pdf http://127.0.0.1:8095/vectorize -o out.pdf
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
  samples/
  output/          # gitignored PDFs/SVGs
  src/
    colors.py      # palette + remap
    preprocess.py
    tracer_vtracer.py
    pdf_export.py
    pipeline.py
    cli.py
    api.py
  tests/
```

---

## Decisions from Tim (locked)

1. Interfaces: CLI+API now; **web UI later**
2. Colors: **up to N**, default **4**
3. Alpha: preserve when present; JPEG is main input
4. Output: **PDF only as product deliverable**; SVG debug
5. PDF color space: **RGB** (Illustrator for further work)
6. Samples may live in repo

See `docs/DECISIONS.md` ADR-1…12 and `docs/QA-NOTES.md` round 2.

---

## Boundaries

**Always:** pytest before "done"; document tracer binary; JPEG-first assumptions in QA  
**Ask first:** public bind, systemd, CMYK, paid API fallback, remote git  
**Never:** treat CairoSVG as raster→vector tracer; ship web UI without quality OK  

---

## Status snapshot

| Item | State |
|------|--------|
| Repo | `/root/logotrace` local git `main` |
| Latest feature commit | brand-color remap + PDF default |
| API | `127.0.0.1:8095` |
| Quality (user) | ~4–4.5/5 after color fix |
