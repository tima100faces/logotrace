# Manual QA — round 3 (2026-07-21)

## Changes

### Colors (`efd31c1`)
- **Mass-aware merge:** dust → nearest major; two **major peers** never merged (even if close hues)
- **`--colors-mode up_to|exact`**
  - `up_to` (default): at most N ink colors
  - `exact`: collapse to N by mass (won't invent colors if fewer majors exist)

### Geometry (`5e7804b`)
- **`--geom off|basic|strict`** (default **basic**)
  - `basic`: RDP + collinear collapse on path polylines
  - `strict`: + circle fit when residual OK
- Wired through CLI, API, pipeline; PDF still default deliverable

## User prior score
Round 2: ~4.0–4.5/5 after brand remap.

## Commands

```bash
python -m src.cli IN.jpg -o OUT.pdf -c 4 --colors-mode up_to -g basic
python -m src.cli IN.jpg -o OUT.pdf -c 2 --colors-mode exact -g strict
```

## Round 4 (gradient crush + edge smooth) — `b12ad0a`

- Gray/same-hue ramps → one solid ink; distinct hues kept
- sample_08: single ink fill (no gray band stack in SVG)
- Light morph smooth per label before trace
- geom remains **off** by default
- Agent verified all 8 PDFs non-blank

## Sample re-run (all 8, geom=basic) — agent-verified
All `output/sample_0X.pdf` non-blank via pdftoppm.

## Follow-ups
- sample_08 gray banding: try `-c 2 --colors-mode exact`
- corner fillet rebuild if strict arcs insufficient
- web UI later
