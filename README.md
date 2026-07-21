# LogoTrace

Flat logo tracer for **JPEG/PNG** → **RGB vector PDF** (SVG optional debug).

Pipeline: measure brand colors → remap → VTracer → PDF.

## Setup

```bash
cd /root/logotrace
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./bin/vtracer --version   # bundled linux x86_64
```

Also uses `rsvg-convert` (librsvg2-bin) for SVG→PDF when available.

## CLI

```bash
source .venv/bin/activate
PYTHONPATH=/root/logotrace python -m src.cli samples/sample_06.jpg -o output/sample_06.pdf
# auto (default): up_to 4 + gradient crush
PYTHONPATH=/root/logotrace python -m src.cli input.jpg -o out.pdf -c 4 --colors-mode up_to
# manual exact K (UI slider): no crush — dual gray survives (sample_05)
PYTHONPATH=/root/logotrace python -m src.cli samples/sample_05.jpg -o out.pdf -c 2 --colors-mode exact
# debug SVG:
PYTHONPATH=/root/logotrace python -m src.cli input.jpg -o out.svg --format svg
```

- `--colors N` — palette size (default **4**)
- `--colors-mode up_to|exact`
  - **up_to** = auto smart (≤N, may crush gray ramps)
  - **exact** = manual K solids by mass (no crush)
- `--geom off|basic|strict` — path normalize (**default off**; basic/strict experimental)
- JPEG first-class. Transparent PNG alpha preserved when present.

## API + UI (localhost)

```bash
PYTHONPATH=/root/logotrace uvicorn src.api:app --host 127.0.0.1 --port 8095

# UI
open http://127.0.0.1:8095/

curl -s http://127.0.0.1:8095/health
# UI contract:
curl -s -F "file=@logo.jpg" -F "palette=auto" -F "format=pdf" \
  http://127.0.0.1:8095/vectorize -o out.pdf
curl -s -F "file=@logo.jpg" -F "palette=2" -F "format=pdf" \
  http://127.0.0.1:8095/vectorize -o out.pdf
# Response headers: X-LogoTrace-Colors, X-LogoTrace-Colors-Mode
```

Web UI (English, light): drop / click / **paste** · Colors Auto|1–4 · PDF preview + download.

| `palette` | Meaning |
|-----------|---------|
| `auto` | up_to DEFAULT_COLORS(4) + crush |
| `1`..`16` | **exact** N (manual override) |

Legacy: `colors` + `colors_mode=up_to|exact|auto`.

Default format: **pdf**.

## Tests

```bash
PYTHONPATH=/root/logotrace pytest -q
```

## Docs

- `docs/SPEC.md` — product spec
- `docs/RESEARCH.md` — research
- `docs/DECISIONS.md` — ADRs
- `docs/QA-NOTES.md` — sample results
- `docs/plans/2026-07-21-mvp-implementation.md` — original plan

## License

GPL-3.0-or-later. See `LICENSE`, `NOTICE`.
