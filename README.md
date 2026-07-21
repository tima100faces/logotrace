# LogoTrace

Flat logo raster-to-vector tracer (up to N colors, default **4**). Local MVP.

Not a Vectorizer.AI clone — classic pipeline: preprocess → **VTracer** → SVG.

## Status

MVP CLI + API implemented. Web UI and PDF are post-MVP.

## Setup

```bash
cd /root/logotrace
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# binary ships in bin/vtracer (linux x86_64 musl)
./bin/vtracer --version
```

## CLI

```bash
source .venv/bin/activate
PYTHONPATH=/root/logotrace python -m src.cli samples/sample_01.jpg -o output/sample_01.svg
PYTHONPATH=/root/logotrace python -m src.cli input.png -o out.svg --colors 4
```

- `--colors N` / `-c N` = **maximum** palette size (default 4)
- Transparency in PNG is preserved (no white matte)

## API (localhost)

```bash
source .venv/bin/activate
PYTHONPATH=/root/logotrace uvicorn src.api:app --host 127.0.0.1 --port 8095

curl -s http://127.0.0.1:8095/health
curl -s -F "file=@logo.png" -F "colors=4" http://127.0.0.1:8095/vectorize -o out.svg
```

## Tests

```bash
source .venv/bin/activate
PYTHONPATH=/root/logotrace pytest -q
```

## Docs

| File | What |
|------|------|
| [docs/SPEC.md](docs/SPEC.md) | Spec + success criteria |
| [docs/RESEARCH.md](docs/RESEARCH.md) | Research notes |
| [docs/DECISIONS.md](docs/DECISIONS.md) | ADRs |
| [docs/plans/2026-07-21-mvp-implementation.md](docs/plans/2026-07-21-mvp-implementation.md) | Implementation plan |
| [docs/QA-NOTES.md](docs/QA-NOTES.md) | Sample run results |

## Layout

```
bin/vtracer     # bundled tracer binary
src/            # Python package
samples/        # input logos
output/         # generated SVG (gitignored)
tests/
```

## License

GPL-3.0-or-later. See `LICENSE` and `NOTICE` (VTracer MIT binary).
