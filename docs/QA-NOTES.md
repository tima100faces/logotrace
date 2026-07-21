# Manual QA — LogoTrace

## Round 6 — UI + debug dumps (2026-07-21)

- Web UI at https://idealabs.co/trace/
- paste/drop, Auto|1–4, canvas preview + zoom/pan
- debug dumps: input/ui_*, output/ui_* + last.*
- systemd + nginx reverse proxy
- SVG stays API/CLI only (no UI button)

## Round 5 — auto vs exact palette contract (`v0.4`)

- auto / up_to: gradient crush OK
- exact / manual K: no crush — sample_05 exact 2 → black + mid-gray
- API: `palette=auto|N` + headers `X-LogoTrace-Colors*`
- pytest: 20 passed

## Round 4 (gradient crush + edge smooth) — `b12ad0a`

- Gray/same-hue ramps → one solid ink
- morph smooth later removed (staircases)

## Round 3 — spline quality restored

- NEAREST 2×, morph, disk-snap, bw mode all removed
- C/L ratio back to spline-dominant (sample_06: 711C/56L)

## Round 2 — mass-aware colors + exact/up_to

- Major peers protected; gradient crush added

## Round 1 — brand-color remap + PDF default

- User score ~4.0–4.5/5

## CLI reference

```bash
python -m src.cli IN.jpg -o OUT.pdf -c 4 --colors-mode up_to
python -m src.cli IN.jpg -o OUT.pdf -c 2 --colors-mode exact
```

## Follow-ups

- per-color potrace spike for organic inputs (08)
- remote git
- CMYK
