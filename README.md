# LogoTrace

Flat logo raster-to-vector tracer (1-3 colors). Local MVP, not a Vectorizer.AI clone.

## Goal

Convert flat logos / icons (1-3 solid colors, no photos) into clean editable SVG with sensible geometry and low node count.

## Status

- Phase: **SPEC + PLAN** (awaiting human approval before implementation)
- Location: `/root/logotrace`
- License: GPL-3.0

## Docs

| File | What |
|------|------|
| [docs/SPEC.md](docs/SPEC.md) | Product/tech spec, success criteria, boundaries |
| [docs/RESEARCH.md](docs/RESEARCH.md) | Research: Vectorizer.AI, OSS landscape, rejected tools |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Architecture Decision Records (ADRs) |
| [docs/plans/2026-07-21-mvp-implementation.md](docs/plans/2026-07-21-mvp-implementation.md) | Bite-sized implementation plan |

## Scope (MVP)

**In:**
- PNG/JPG/WebP input
- Force 1-3 color palette
- Trace to flat filled SVG
- CLI + simple HTTP API
- Path simplify / SVGO cleanup

**Out (for now):**
- Photos / gradients / full-color art
- Vectorizer.AI-level shape fitting / symmetry AI
- Web UI
- Multi-tenant SaaS

## Quick start (after implementation)

```bash
# TBD after plan approval
cd /root/logotrace
# python -m src.cli input.png -o out.svg --colors 2
# curl -F file=@logo.png http://localhost:PORT/vectorize
```

## Samples

Put test logos in `samples/` (user will upload when ready).

## Related research session

Hermes research 2026-07-21: Vectorizer.AI vs VTracer / Potrace / linedraw / CairoSVG.
CairoSVG = wrong direction (SVG→raster). linedraw = plotter line-art only.
