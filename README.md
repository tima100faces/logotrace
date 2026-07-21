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
PYTHONPATH=/root/logotrace python -m src.cli input.jpg -o out.pdf --colors 4 --colors-mode up_to --geom basic
PYTHONPATH=/root/logotrace python -m src.cli input.jpg -o out.pdf -c 2 --colors-mode exact -g strict
# debug SVG:
PYTHONPATH=/root/logotrace python -m src.cli input.jpg -o out.svg --format svg
```

- `--colors N` — palette size (default **4**)
- `--colors-mode up_to|exact` — at most N vs collapse to N by mass
- `--geom off|basic|strict` — path normalize (default **basic**)
- JPEG first-class. Transparent PNG alpha preserved when present.

## API (localhost)

```bash
PYTHONPATH=/root/logotrace uvicorn src.api:app --host 127.0.0.1 --port 8095

curl -s http://127.0.0.1:8095/health
curl -s -F "file=@logo.jpg" -F "colors=4" -F "format=pdf" \
  http://127.0.0.1:8095/vectorize -o out.pdf
```

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
