# Research: Raster-to-Vector for Flat Logos

**Date:** 2026-07-21  
**Goal of research:** Can we build a useful local alternative to Vectorizer.AI for **flat logos (1-3 colors)**, without cloning their full AI stack?

---

## Benchmark product: Vectorizer.AI

- URL: https://vectorizer.ai
- Full-color AI tracer with proprietary Deep Vector Engine
- Own DL models + classical geometry (Vector Graph, full shape fitting: circles/ellipses/stars, clean corners, symmetry, sub-pixel precision)
- Outputs: SVG, EPS, DXF, PDF
- Has developer API (test mode free; paid plans for real volume)
- Industry quality benchmark for fidelity
- **Overkill for flat 1-3 color logos**, but good quality ceiling reference

---

## Tools evaluated

### Not applicable (wrong problem)

| Tool | Why rejected |
|------|----------------|
| **CairoSVG** (Kozea) | SVG → raster. Opposite direction. |
| **linedraw** (LingDong-) | Line drawings for plotters (polylines, sketchy). Not filled flat logo shapes. |

### Relevant open source / free

| Tool | Color | Notes | Fit for flat logos |
|------|-------|-------|--------------------|
| **VTracer** (visioncortex) | Yes | Rust, CLI + web demo, color clustering + stacking, compact-ish SVG | **Primary candidate** |
| **Potrace** (+ Inkscape Trace Bitmap) | Mainly mono / multi-pass | Classic, often clean on 1-color logos; GPL-2 | Strong for mono/2-color |
| **imagetracerjs** | Yes | JS, easy to embed in web | Backup / browser path |
| **Autotrace** | Limited color | Older | Legacy only |
| **primitive / Geometrize** | Stylized | Artistic primitives, not fidelity | No |

### Commercial peers (context only)

- Vector Magic — strong full-color veteran
- Adobe Illustrator Image Trace — manual control if already in Adobe
- Various 2026 web AI tools (VectoSolve, PerfectVector, etc.) — blog comparisons often self-serving

---

## Consensus (Reddit / SoftRecs / 2026 writeups)

- No free OSS equals Vectorizer.AI on complex full-color art
- For free: Inkscape/Potrace or VTracer
- Preprocess (clean edges, optional upscale) often matters more than tracer brand
- Node soup is the main UX pain after auto-trace

---

## Fit to our product decision

User constraints (confirmed):
- Photos: **out of scope**
- Logos **1-3 colors**
- Flat output
- Prefer **correct geometry** (clean paths, low node count)
- Do **not** build Vectorizer.AI-scale monster

**Conclusion:** MVP is realistic and justified. Classic pipeline + VTracer (and/or Potrace) is enough for a useful spike and productizable CLI/API.

Suggested quality band for flat logos:
- ~70-90% cases usable immediately
- Rest need light cleanup or parameter tweak

---

## Proposed technical pipeline (research-backed)

```
raster (PNG/JPG/WebP)
  → preprocess (despeckle / contrast / optional threshold)
  → palette quantize to N∈{1,2,3}
  → tracer (VTracer primary; Potrace optional mono path)
  → post (svgo + path simplify)
  → SVG (flat fills)
```

Hybrid later (not MVP): hard cases → paid API fallback.

---

## Open items before coding

1. User sample set (3-15 flat logos) for side-by-side scoring
2. Confirm preferred primary engine: VTracer vs Potrace-first for 1-color
3. License interaction: Potrace is GPLv2 — if linked, product license implications (project already GPL-3.0 oriented)
4. Deploy shape: local CLI only vs FastAPI on this VPS

---

## Sources (non-exhaustive)

- https://vectorizer.ai (product claims / feature list)
- https://github.com/visioncortex/vtracer
- https://github.com/LingDong-/linedraw
- https://github.com/Kozea/CairoSVG
- https://github.com/fromtheexchange/image2svg-awesome
- PerfectVector / VectoSolve 2026 comparison posts (bias flagged)
- Softwarerecs / Reddit threads on free alternatives to Vectorizer.AI
