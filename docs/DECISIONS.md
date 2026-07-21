# ADR: SPSA / black-box control-point optimization — dead end

**Date:** 2026-07-21  
**Status:** Accepted  
**Stage:** 5

## Context

Stage 5 aimed to test whether gradient-guided vertex optimization (DiffVG-style)
against the original image could improve curve fidelity beyond v4
(VTracer + upscale, IoU aw 0.982, Chamfer 0.24px).

An SPSA optimizer with edge-distance (Chamfer-like) loss was implemented over
the full set of VTracer control points (~24K params).

## Decision

### What was tried

1. **SPSA with edge-distance loss** — 2 function evaluations per iteration
   regardless of dimension. Conservative hyperparameters: a=0.15, c=0.15,
   trust_radius=±1.5px, max_iter=10.
2. **SPSA with edge-weighted MSE** — edge-proximity weighting of pixel MSE.
3. **Rebuild-based SVG injection** — parse→optimize→rebuild SVG paths with
   control-point precision preservation.

### What went wrong

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

## Consequences

- **Black-box numeric optimization of SVG control points is banned.**
  Any future refinement must use a true differentiable rasterizer
  (e.g. `diffvg` with PyTorch autograd) that provides real analytic
  gradients through the rendering pipeline.
- The SPSA implementation is not committed (dead code removed).
- `run_matrix` in `eval.py` remains the generic variant comparison entry
  point. New variants can be added via the `variants_config` list.

## Alternatives considered

- **Per-path optimization** — smaller parameter space, but same loss
  misalignment problem.
- **Coordinate descent** — still black-box, slower, same issue.
- **Nelder-Mead / CMA-ES** — O(n²) function evals, intractable for 24K params.
- **True differentiable rasterizer (diffvg)** — the only viable path forward.
  Requires torch+CUDA, returns analytic gradients ∂loss/∂control_points
  through the full SVG→raster pipeline.
