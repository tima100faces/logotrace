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

**Status:** Accepted (auto-mode selection superseded by ADR-23, 2026-07-22)  
**Date:** 2026-07-21

**Decision:**
- Default: `palette=auto` → up_to 4 + gradient crush *(auto mode now: unified auto-N per ADR-23)*
- Manual: `palette=N` → exact N, **no crush** (dual gray survives) — unchanged
- API contract: `resolve_palette_policy()` + response headers

---

## ADR-9: Preserve transparency (no white matte)

**Status:** Accepted  

---

## ADR-10: gradient crush for low-sat same-hue ramps

**Status:** Accepted (anchor rule updated by ADR-22; drop rules constrained by ADR-23)  
**Date:** 2026-07-21

Gray ramps collapse to single ink. Distinct hues kept. Active only in auto mode; manual exact K bypasses crush. Anchor = dominant cluster by MASS (ADR-22), not darkest. Crush may never drop a color whose mass exceeds the candidate threshold (ADR-23).

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

**Status:** Accepted (palette control extended to Auto|1–8, 2026-07-22)  
**Date:** 2026-07-21

- Single page HTML/CSS/JS, served by FastAPI mount
- pdf.js canvas preview (not browser PDF iframe)
- Zoom: −/+/Fit + Ctrl/⌘+wheel
- Pan: drag (hand tool)
- Paste/drop/file equally supported
- Colors: Auto|1–8 segmented (API accepts up to 16)
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
- Chain-based rule implemented in commit `ba5af9b` (rebased as `f775180`);
  result: 0 false merges across the sample set (vs 2168 conversions with
  the per-cubic approach).
- Any future geometry transform must include per-shape safety guards
  with revert logging.

---

## ADR-21: geometry_fit post-pass — removed (no visible benefit)

**Status:** Accepted  
**Date:** 2026-07-22

**Context:** geometry_fit was a three-pass post-VTracer geometry cleanup:
pass 1 — chain-based line detection (per ADR-20), pass 2 — line snapping,
pass 3 — G1 smoothing at cubic joints. Findings on the canonical sample set:

- **Pass 1: 0 merges.** VTracer chains never satisfied the chord/deviation
  rule — nothing to convert.
- **Pass 2: dead by construction.** VTracer emits cubic Béziers only;
  there are no line segments to snap.
- **Pass 3: no visible benefit.** Thousands of joints smoothed per sample,
  0 safety-guard reverts — but owner review of 400% before/after crops
  found the visual difference negligible, while metrics were slightly
  worse: Chamfer +0.02 px, SVG size +34%, runtime +50%.

**Decision:** Removed entirely (commit `ed60ddc`, −809 lines: module,
tests, visual-crop script, pipeline/eval wiring). The tile-based
`_binarize` fix in `src/eval.py` is retained (independent, prevents OOM
on high-node samples). Per the no-dormant-code rule: no off-by-default
shelving.

**Consequences:**
- Curve refinement beyond VTracer + upscale requires a true
  differentiable rasterizer (see ADR-18); no further heuristic
  geometry passes.
- Legacy `geometry.py` (`--geom`) remains as-is per ADR-14: off by
  default, experimental only.

---

## ADR-22: Background is always kept — paper/fullbleed split removed

**Status:** Accepted  
**Date:** 2026-07-22

**Context:** The pipeline classified inputs as "paper" (white_fraction ≥
0.22 → background erased to white) or "fullbleed". On sample_10 (green/gold
label) the border-median background was the dark-green brand plate itself;
paper mode erased 97.4% of it (52% of the image), and JPEG edge-mix colors
on the gold/green boundary then survived as MAJOR ink clusters, producing
an olive fringe. Root cause: a semantics gap ("background = paper white"
vs "background = brand field"), not a code bug. Owner does not need
background removal — deleting a background rectangle in Illustrator is
trivial, while auto-erasure destroys labels.

**Decision:**
1. The paper/fullbleed classification and the erase-to-white path are
   removed (commit `d3be21d`, −45 lines net). Background is ALWAYS kept
   as a regular bottom palette layer.
2. `estimate_background()` detection and BG_DIST2 snapping stay — JPEG
   noise cleanup now snaps to the detected bg color, not to white.
3. Background occupies a reserved slot OUTSIDE the ink limit:
   auto = bg + N inks; manual K = bg + K inks.
4. Follow-up fix (commit `4c58039`): gradient-crush anchor for the
   low-saturation group is chosen by MASS (dominant cluster), not by
   darkness — the darkest-anchor heuristic assumed white was always
   background and turned a 34.6% white panel gray.

**Results:** 11-sample IoU aw 0.9335 → 0.9853; sample_10 0.4989 → 0.97+.
Bimodal guard no longer fires on any sample but is kept as a safety net.
Open problem #1 (palette loss on complex labels) closed by this ADR
together with ADR-23.

**Operational note:** the API runs as `logotrace.service`; after every
merge to main the service must be restarted (`systemctl restart
logotrace`) or the web UI serves stale code.

---

## ADR-23: Unified auto palette selection (auto-N)

**Status:** Accepted  
**Date:** 2026-07-22

**Context:** Auto mode hard-capped the palette at 4 inks; multi-ink
labels (sample_11 bread label: brown, orange, yellow, bordeaux, white)
lost colors. A first auto-N attempt (commit `6cc2163`) layered new
heuristics (hue-only bucketing, add-back cap, GRAY_SAT_MAX 0.14→0.16,
bounds 1..6) on top of the old 4-color-era code and produced three
failures: bordeaux merged into orange (hue-only merge ignores lightness),
sample_10 Chamfer 0.4→3.7px (auto-N=2 forced crush to drop the 34.6%
white panel), and sample_09's two grays collapsed into one (SAT shift,
metric improved while visual quality dropped — owner rejected on review).

**Decision** (commit `f5fb537`) — palette selection is ONE coherent
procedure:
1. Candidates by mass: clusters ≥ 3% of the dominant cluster.
2. Merging ONLY by full color distance: weighted HSL with w_L=2, w_S=1,
   w_H=1, merge threshold 0.18. Never merge by hue alone. Distant-lightness
   pairs (bordeaux vs orange: 0.332; dark vs light gray) stay separate.
3. N = number of survivors, bounds 1..8. The add-back heuristic is
   deleted (it patched the hue-only merging bug).
4. Gradient crush runs on survivors but may NEVER drop a color whose
   mass exceeds the candidate threshold — crush merges ramps, it does
   not enforce N.
5. GRAY_SAT_MAX = 0.14 (the 0.16 shift is rejected: on sample_09 it
   merged #5d646e into light gray — metrics up, visual quality down).
6. Manual K (exact) contract unchanged. UI: Auto|1–8.

**Known trade-offs (accepted by owner):** sample_02 −0.014 IoU aw (one
extra intermediate green in the palette), sample_04 −0.028 (pink hue
shift). The 0.18 threshold is a deliberate compromise between
bordeaux-vs-brown separation and ramp collapse — do not tune it
casually; any change must re-pass the ADR-23 acceptance set
(sample_05, 08, 09, 10, 11).

**Lesson recorded:** three times in one day metrics improved while
visual quality regressed (gray panel, sample_09 grays, pass-3
smoothing). Pixel metrics are necessary but not sufficient — owner
visual review is a mandatory part of acceptance for palette and curve
changes.

## ADR-24: The service moves to mainframe under its own subdomain

**Context:** the service ran on the old VPS as `https://idealabs.co/trace/` — a path inside a vhost
that also serves the rest of `idealabs.co`. mainframe hosts sites as `server_name` + certificate per
site (`hermes-site-ctl`), and `idealabs.co` itself has not moved yet.

**Decision:** the new address is `https://trace.idealabs.co`, with an A record straight to mainframe
(`188.245.227.6`), DNS-only at first so the ACME challenge reaches nginx.

**Consequences:**
- Old links into `idealabs.co/trace/` need a redirect; it can only be written once `idealabs.co`
  itself moves (parked in `docs/PLAN.md`).
- The old host stays the address users reach until DNS is switched, so the two copies must not drift:
  no code changes on the old side.
- TLS is issued with `hermes-site-ctl cert logotrace` after the switch, from the hosting template.

## ADR-25: The virtualenv is built on the system interpreter, inside the live tree

**Context:** the hosting template starts `<site>/venv/bin/uvicorn app:app`. A virtualenv staged in the
repository arrives with absolute shebangs into `/srv/hermes`, which the service account cannot enter
(the unit dies with `203/EXEC`); the same happens with a venv created by `uv venv`, which points at
uv's managed interpreter inside `/srv/hermes`.

**Decision:** `deploy/live-venv.sh` creates the environment in the live tree with
`/usr/bin/python3 -m venv` and installs `requirements.txt` with `uv pip install --python <venv>`.

**Consequences:**
- The interpreter is the distribution one (3.14.4 today), not the 3.11 the project used on the old
  host; a distro upgrade means rebuilding the venv and re-running the tests.
- `sync` mirrors the staged tree **with deletion**, so the environment is rebuilt on every deploy —
  `deploy/deploy.sh` chains sync → venv → restart → health. The `venv/` directory itself is kept in
  the repository (`venv/.gitkeep`) so the mirror does not remove it; its contents are ignored.
- The virtualenv is not in git — it is a build artifact of the deployment, not part of the source.
- The repository copy stays useful for development: `python3 -m venv .venv` plus the same
  `requirements.txt`.

## ADR-26: Project documentation lives in the repository

**Context:** decisions, specs and QA notes had grown inside the repository, while status and history
also lived on a wiki page; two copies drift and it becomes unclear which one is true.

**Decision:** `AGENTS.md` plus `docs/{STATUS,PRODUCT,PLAN,DECISIONS,PITFALLS}.md` are the operational
documentation and live with the code. The wiki keeps a passport: what the project is, where it runs,
the address, versions, and the links back here.

**Consequences:**
- An agent working in the code (Claude Code on the Mac, Codex, Hermes on the server) reads the
  repository; nothing important may exist only in the wiki.
- The pre-existing `docs/` files (`SPEC.md`, `EVAL-BASELINE.md`, `QA-NOTES.md`, `RESEARCH.md`,
  `ai-preflight-vision-qa.md`, `plans/`) stay where they are — they are the project's own material.
