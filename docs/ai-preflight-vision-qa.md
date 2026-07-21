# AI Pre-Flight: vision QA for LogoTrace

Idea: before showing a vectorized PDF to Tim, an LLM (with vision) compares
input raster vs output render side-by-side and flags regressions.

This doc captures the hypothesis, implementation path, and practical limits.

**Date:** 2026-07-21  
**Status:** spec (not implemented)

---

## Problem

Current pipeline already self-checks for *blank* output (`verify.py`).  
But regressions like "circle became egg-shaped" or "text got jagged" only
surface when Tim opens the PDF — often mid-conversation with Hermes.

Tim's direct quote: *«все кривые стали с зазубринами. это для работы
использовать нельзя»* — was caught after several pipeline changes, not
during development.

## Hypothesis

An LLM vision pass can catch these regressions **before** human review:

1. Rasterize input (original JPEG/PNG)
2. Rasterize output (PDF → PNG via pdftoppm)
3. Send side-by-side to a vision model with a structured QA prompt
4. Model returns: PASS / WARN / FAIL + specific issue description
5. FAIL / WARN blocked from delivery; only clean PASS reaches UI

## Proposed pass/fail criteria

| Criterion | Check |
|-----------|--------|
| **Character/symbol loss** | Letter missing or deformed vs original |
| **Major shape distortion** | Circle → egg, ellipse → irregular blob |
| **Staircase curves** | Smooth bezier → visibly faceted polyline (count L vs C? or visual) |
| **Color shift > threshold** | ΔE > 12 in dominant colors |
| **Region collapse** | Two distinct fills merged into one |
| **Blank / degenerate** | Already caught by verify.py |

## Architecture sketch (post-MVP)

```
run() → PDF + SVG
  ├── verify.py (blank check, already done)
  ├── pdftoppm PDF → render.png
  ├── ✦ vision QA ✦ (input.jpg + render.png → PASS/WARN/FAIL)
  │     ├── PASS → return PDF
  │     ├── WARN → attach warning to download, still return
  │     └── FAIL → raise VectorizeError
  └── save debug dump (input/ui_*, output/ui_*)
```

## Model choice

- Default vision: **Gemini 2.5 Flash** (already in config, $0.15/$0.60 per 1M)
- Cost per check: ~400 input tokens image + ~80 output token → <$0.001
- 100 checks/day → <$0.10/day

## Prompt template (draft)

```
You are a QA checker for a logo vectorization pipeline.
Compare the source raster (left) and vector output render (right).

Report:
- Overall: PASS | WARN | FAIL
- Shape issues: circle/arc quality, faceted curves, missing parts
- Color: any hue shift or region loss
- Text: any symbol distortion or illegibility
- False positive check: do not flag organic shapes that match source intent

Respond with one line: STATUS:reason:details (max 2 sentences).
```

## Limitations (known)

1. **Vision models are not pixel-diff tools** — they see "gestalt", not per-pixel deviation
2. **False positives** on organic/artistic inputs (sample_08 shards)
3. **Latency**: +2–5s per convert (vision call + rasterization)
4. **Model jitter**: same input, slightly different verdict across calls
5. **Does not replace human QA** — only catches obvious regressions

## Experiment design

1. **Round 1**: 20 known pairs (10 good, 10 bad from git history)
   - Measure precision/recall of vision QA vs human verdict
2. **Round 2**: run in shadow mode for 1 week (log verdicts, don't block)
3. **Round 3**: enable blocking on FAIL only; WARN logs
4. **Gate**: if precision < 0.85 or false-positive rate > 5% — keep shadow-only

## Open questions

- Structural comparison (SVG path count, ellipse fit) vs pure vision?
- Multi-model: cheap model for first pass, expensive for edge cases?
- Should it run per-convert or only on sampled runs?

## Related

- `src/verify.py` — blank / degenerate check (complementary)
- ADR-14: geometry post-pass is off by default
- ADR-16: debug dumps provide baseline for experiment
