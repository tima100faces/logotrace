# Architecture Decision Records — LogoTrace

## ADR-1: Product scope = flat logos only (1-3 colors)

**Status:** Accepted  
**Date:** 2026-07-21

**Context:** Vectorizer.AI-class full-color / photo tracing is expensive (ML, dataset, geometry engine). User does not need photos.

**Decision:** Scope MVP strictly to flat logos/icons with 1-3 solid colors and flat filled SVG output.

**Rejected:**
- Full-color photo vectorization — out of scope
- Gradient preservation — out of scope for MVP

---

## ADR-2: Primary tracer = VTracer; Potrace optional for mono

**Status:** Accepted  
**Date:** 2026-07-21

**Context:** Need color-capable, scriptable, local tracer with decent path quality.

**Decision:** Default engine: **VTracer** (CLI, spline mode, color). Potrace spike for per-color mono workflow deferred.

**Rejected:** CairoSVG, linedraw, imagetracerjs, custom DL tracer.

---

## ADR-3: Stack = Python FastAPI + static UI + VTracer binary

**Status:** Accepted  
**Date:** 2026-07-21

**Decision:**
- API: Python 3.11 + FastAPI + Typer
- Tracer: subprocess VTracer binary
- UI: static HTML/CSS/JS + pdf.js (cdnjs), served by FastAPI `/` mount
- Tests: pytest

---

## ADR-4: Interface = CLI + API + Web UI

**Status:** Accepted (updated 2026-07-21)  
**Date:** 2026-07-21

**Decision:**
1. CLI: `python -m src.cli input.jpg -o out.pdf`
2. API: `POST /vectorize` + `GET /health` + static `/` route
3. Web UI: light, English, paste/drop, canvas preview + zoom/pan, at idealabs.co/trace

---

## ADR-5: Quality bar = clean geometry for flat logos, not AI shape-fit

**Status:** Accepted  
**Date:** 2026-07-21

**Decision:** Optimize for correct palette, flat fills, stable parameters. Do not optimize for photo fidelity or AI shape recognition.

---

## ADR-6: License = GPL-3.0

**Status:** Accepted  

---

## ADR-7: No remote git until user asks

**Status:** Accepted  

---

## ADR-8: Palette = Auto (up_to) / Manual K (exact)

**Status:** Accepted (updated 2026-07-21)  
**Date:** 2026-07-21

**Decision:**
- Default: `palette=auto` → up_to 4 + gradient crush
- Manual: `palette=N` → exact N, **no crush** (dual gray survives)
- API contract: `resolve_palette_policy()` + response headers

---

## ADR-9: Preserve transparency (no white matte)

**Status:** Accepted  

---

## ADR-10: gradient crush for low-sat same-hue ramps

**Status:** Accepted  
**Date:** 2026-07-21

Gray ramps collapse to single darkest ink. Distinct hues kept. Active only in `up_to` mode; manual exact K bypasses crush.

---

## ADR-11: Primary output = RGB PDF; SVG is debug

**Status:** Accepted  

---

## ADR-12: JPEG-first color fidelity pipeline

**Status:** Accepted  

Palette measured from original → remap → VTracer → PDF.

---

## ADR-13: Mass-aware palette merge

**Status:** Accepted  

Major peers (≥3% ink) never merge unless ultra-close. Dust folds into nearest major.

---

## ADR-14: Geometry normalize post-pass — off by default

**Status:** Accepted (default off 2026-07-21)  

`geom=off` keeps raw VTracer splines. `basic`/`strict` experimental only — RDP ruined roundovers.

---

## ADR-15: Web UI — light, static, pdf.js canvas preview

**Status:** Accepted  
**Date:** 2026-07-21

- Single page HTML/CSS/JS, served by FastAPI mount
- pdf.js canvas preview (not browser PDF iframe)
- Zoom: −/+/Fit + Ctrl/⌘+wheel
- Pan: drag (hand tool)
- Paste/drop/file equally supported
- Colors: Auto|1|2|3|4 segmented
- Font: Inter

---

## ADR-16: Debug dumps — input/ui_* + output/ui_* + last.*

**Status:** Accepted  
**Date:** 2026-07-21

Every API/UI convert saves timestamped input + output + meta.json.
`last.*` symlink-like quick pointers for agent QA.
Soft cap 500 runs, no time-based prune. `.gitignore` excludes dumps.
Disabled via `LOGOTRACE_DEBUG_SAVE=0`.
