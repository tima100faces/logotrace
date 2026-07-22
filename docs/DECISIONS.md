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

---

## ADR-17: Potrace — benchmark against VTracer baseline, remove if not better

**Status:** Accepted  
**Date:** 2026-07-21

**Context:** Potrace was kept as optional mono tracer since ADR-2 (July 21).
No integration work has been done yet. Before building code paths,
we must prove Potrace earns its place.

**Decision:** Potrace will be benchmarked against the VTracer baseline using
the evaluation harness (`src/eval.py`). If Potrace does **not** outperform
VTracer on flat-logo samples (better IoU or Chamfer on at least some),
it must be removed from the system entirely:

- Binary (`bin/potrace` or system `potrace`)
- Any Python wrappers, imports, or config references
- `requirements.txt` / NOTICE / README references

No dormant fallback code. Either it ships because it wins, or it's gone.

**Reasons:**
- Dead code paths create maintenance burden
- "Optional fallback" without benchmark data is speculative complexity
- The eval harness now provides objective comparison data

**Rejected:**
- Keeping Potrace "just in case" without proving value
- Shipping both engines unconditionally

---

## ADR-18: SPSA / black-box control-point optimization — dead end

**Status:** Accepted  
**Date:** 2026-07-21  
**Stage:** 5

### Context

Stage 5 aimed to test whether gradient-guided vertex optimization (DiffVG-style)
against the original image could improve curve fidelity beyond v4
(VTracer + upscale, IoU aw 0.982, Chamfer 0.24px).

An SPSA optimizer with edge-distance (Chamfer-like) loss was implemented over
the full set of VTracer control points (~24K params).

### Decision

#### What was tried

1. **SPSA with edge-distance loss** — 2 function evaluations per iteration
   regardless of dimension. Conservative hyperparameters: a=0.15, c=0.15,
   trust_radius=±1.5px, max_iter=10.
2. **SPSA with edge-weighted MSE** — edge-proximity weighting of pixel MSE.
3. **Rebuild-based SVG injection** — parse→optimize→rebuild SVG paths with
   control-point precision preservation.

#### What went wrong

- **Loss decreased while geometry collapsed.** Edge-distance loss improved
  from 163.5 → 161.5 on sample_03, but IoU aw dropped from 0.98 → 0.75
  (and to 0.38 with slightly larger step sizes).
- **Edge-distance loss is not aligned with visual quality.** SPSA found
  minima in the loss landscape that produced visually broken SVGs.
- **Gradients are uninformative at 24K params.** Each SPSA gradient estimate
  is stochastic noise in a 24K-dimensional space. Two function evaluations
  per iteration cannot recover a meaningful descent direction.
- **Rebuild SVG roundtrip is fragile.** Parsing and rebuilding SVG paths
  introduced formatting discrepancies that changed rendering behaviour.

### Consequences

- **Black-box numeric optimization of SVG control points is banned.**
  Any future refinement must use a true differentiable rasterizer
  (e.g. `diffvg` with PyTorch autograd) that provides real analytic
  gradients through the rendering pipeline.
- The SPSA implementation is not committed (dead code removed).
- `run_matrix` in `eval.py` remains the generic variant comparison entry
  point. New variants can be added via the `variants_config` list.

### Alternatives considered

- **Per-path optimization** — smaller parameter space, but same loss
  misalignment problem.
- **Coordinate descent** — still black-box, slower, same issue.
- **Nelder-Mead / CMA-ES** — O(n²) function evals, intractable for 24K params.
- **True differentiable rasterizer (diffvg)** — the only viable path forward.
  Requires torch+CUDA, returns analytic gradients ∂loss/∂control_points
  through the full SVG→raster pipeline.

---

## ADR-19: Subpixel contour tracer — removed (lost to VTracer + upscale)

**Status:** Accepted  
**Date:** 2026-07-21 (recorded 2026-07-22)  
**Stage:** 3

**Context:** A custom subpixel tracer (soft per-color masks →
`skimage.find_contours` → Schneider cubic fitting) was built as a
potential replacement for VTracer, aiming at smoother curves from
subpixel-accurate contours.

**Decision:** Removed entirely (`src/tracer_subpixel.py`, commit `873b977`).
Benchmarked against VTracer + upscale on the full sample set: it lost on
every sample (IoU aw ≈ 0.51 vs ≈ 0.98). Per the no-dormant-code rule the
implementation was deleted, not shelved.

**Consequences:**
- VTracer remains the only tracing engine (see ADR-2, ADR-17).
- Curve-quality work continues via upscale policy and post-VTracer passes,
  not via replacement tracers.

---

## ADR-20: Per-cubic line conversion banned — line detection must be chain-based

**Status:** Accepted  
**Date:** 2026-07-22

**Context:** In the geometry_fit post-pass (pass 1), converting every
near-flat short cubic into a line segment turned smooth curves —
which VTracer emits as chains of short cubics — into polygons
(polygon-ized circles). The same defect existed in the legacy
`geometry.py` simplify pass (see ADR-14: RDP ruined roundovers).

**Decision:** Per-cubic line conversion is banned. Line detection must be
chain-based: a chain of ≥2 consecutive cubics may be converted to a line
only if chord length ≥ 5 source-px AND max deviation < 0.35 px.
Single cubics are never converted.

**Consequences:**
- Chain-based rule implemented in commit `ba5af9b`; result: 0 false
  merges across the sample set (vs 2168 conversions with the per-cubic
  approach).
- Any future geometry transform must include per-shape safety guards
  with revert logging.
