# Architecture Decision Records — LogoTrace

## ADR-1: Product scope = flat logos only (1-3 colors)

**Status:** Accepted  
**Date:** 2026-07-21

**Context:** Vectorizer.AI-class full-color / photo tracing is expensive (ML, dataset, geometry engine). User does not need photos.

**Decision:** Scope MVP strictly to flat logos/icons with 1-3 solid colors and flat filled SVG output.

**Reasons:**
- Open-source tracers are strongest exactly here
- Clear success criteria and small test matrix
- Avoids AI-monster R&D

**Rejected:**
- Full-color photo vectorization — out of scope
- Gradient preservation — out of scope for MVP

---

## ADR-2: Primary tracer = VTracer; Potrace optional for mono

**Status:** Accepted (pending spike confirmation on real samples)  
**Date:** 2026-07-21

**Context:** Need color-capable, scriptable, local tracer with decent path quality.

**Decision:**
- Default engine: **VTracer** (CLI)
- Optional path: **Potrace** for pure 1-color / high-contrast mono logos if spike shows cleaner geometry
- Final choice locked after sample benchmark

**Reasons:**
- VTracer handles 2-3 color logos without multi-pass hacks
- CLI-friendly for API wrapping
- Active OSS, compact stacking strategy

**Rejected:**
- CairoSVG — wrong direction
- linedraw — line-art/plotter only
- Building custom DL tracer for MVP — YAGNI
- imagetracerjs as primary — weaker ops story on server than Rust CLI

---

## ADR-3: Stack = Python FastAPI + external tracer binary + Pillow/svgo

**Status:** Accepted  
**Date:** 2026-07-21

**Context:** Tim's server stack is Python-heavy (FastAPI services). Want thin orchestration, not rewrite tracer in Python.

**Decision:**
- Orchestration / API / CLI: **Python 3.11 + FastAPI + Typer (or argparse)**
- Image preprocess: **Pillow** (+ optional opencv only if spike needs it)
- Trace: subprocess to **vtracer** binary
- SVG cleanup: **svgo** (Node) and/or Python SVG path simplify library
- Package: local git repo under `/root/logotrace`, GPL-3.0

**Reasons:**
- Matches existing ops (daber-dict etc.)
- Tracer stays best-of-breed binary
- Easy to test with pytest + sample fixtures

**Rejected:**
- Pure JS service — unnecessary rewrite of server habits
- Embedding full Inkscape — heavy dependency
- Calling Vectorizer.AI API as core — fine as later fallback, not MVP core

---

## ADR-4: Interface = CLI first, HTTP API second, no UI in MVP

**Status:** Accepted  
**Date:** 2026-07-21

**Context:** Need something usable for batch and integration; web designer UI not requested.

**Decision:**
1. CLI: `logotrace input.png -o out.svg --colors 2`
2. HTTP: `POST /vectorize` multipart → SVG bytes + `GET /health`
3. No frontend in MVP

**Rejected:**
- Full web app / drag-drop UI — later
- Desktop GUI — out of scope

---

## ADR-5: Quality bar = editable flat SVG, not pixel-perfect photo match

**Status:** Accepted  
**Date:** 2026-07-21

**Context:** "Правильная геометрия" means clean paths, not Vectorizer.AI shape-fitting AI.

**Decision:** Optimize for:
- Correct palette count (1-3)
- Flat fills (no gradients unless unavoidable)
- Lower node count via simplify
- Stable CLI parameters

Do **not** optimize for photo fidelity or automatic circle/star recognition in MVP.

**Rejected:**
- Full shape-fitting engine in v1
- Symmetry modelling AI

---

## ADR-6: License = GPL-3.0 for project code

**Status:** Accepted  
**Date:** 2026-07-21

**Context:** User standard: GPL-3.0 only (rejected MIT for projects).

**Decision:** Project code under GPL-3.0. Document third-party licenses (VTracer, Potrace GPLv2 if used) in NOTICE or README.

**Note:** If Potrace is linked/distributed, ensure license compatibility is explicit in docs.

---

## ADR-7: No remote git until user asks

**Status:** Accepted  
**Date:** 2026-07-21

**Context:** User asked for local repo init. Other repos sometimes restricted on remote.

**Decision:** Local `git init` on main only. Push/remote only on explicit request.

---

## ADR-8: Palette = up to N colors (not exactly N)

**Status:** Accepted  
**Date:** 2026-07-21

**Context:** User cannot yet lock exact color counts; logos vary. Forced exact-N can invent junk colors or crush real ones.

**Decision:** `--colors N` / API `colors=N` means **maximum** palette size. Engine may use fewer. Default N left slightly open (proposal: 3) until samples.

**Rejected:** Always exactly N colors in output.

---

## ADR-9: Preserve transparency (no white matte)

**Status:** Accepted  
**Date:** 2026-07-21

**Context:** Logos often sit on transparent PNG. Flattening to white destroys reuse on dark backgrounds.

**Decision:** If source has alpha/transparency, keep transparent background in SVG. Do not composite onto white.

**Rejected:** Always flatten on white for "simpler" trace.

---

## ADR-10: Web UI after quality validation; PDF post-MVP

**Status:** Accepted  
**Date:** 2026-07-21

**Context:** Need to prove tracer quality before investing UI. PDF is useful export but not core geometry problem.

**Decision:**
- MVP: CLI + API, SVG out
- After tests: web UI
- PDF: post-MVP (vector PDF via SVG→PDF, e.g. cairosvg/resvg/inkscape — note: CairoSVG here is OK as **SVG→PDF**, not as tracer)

**Rejected:** Web UI or PDF as MVP blockers.
