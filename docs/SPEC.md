# Spec: LogoTrace MVP

## Objective

Build a local tool that converts **flat logo rasters** (1-3 solid colors) into **clean flat SVG** suitable for edit/print/cut workflows.

**User:** Tim (operator / product). Later maybe API consumers.  
**Why:** Vectorizer.AI is strong but paid/heavy; for flat logos OSS pipeline is enough and controllable.

### User stories

1. As an operator, I drop a 2-color PNG logo and get an SVG with two flat fills and editable paths.
2. As a developer, I `POST` an image to `/vectorize` and receive `image/svg+xml`.
3. As an operator, I can force `--colors 1|2|3` when auto palette is wrong.

### Success criteria (MVP done when)

- [ ] CLI converts PNG/JPG/WebP → SVG for samples in `samples/`
- [ ] HTTP `GET /health` → 200
- [ ] HTTP `POST /vectorize` accepts image, returns SVG
- [ ] `--colors N` forces palette size N ∈ {1,2,3}
- [ ] Output is flat fills (no intentional gradients)
- [ ] At least one automated test with a tiny fixture image
- [ ] README documents install + usage
- [ ] Side-by-side notes on 3+ real logos after user uploads samples (manual QA)

---

## Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11 |
| API | FastAPI + uvicorn |
| CLI | Typer (or argparse if lighter) |
| Preprocess | Pillow |
| Tracer | VTracer CLI (primary) |
| Optional tracer | Potrace (mono path, spike-dependent) |
| SVG optimize | svgo and/or Python simplify |
| Tests | pytest |
| License | GPL-3.0 |

---

## Commands (target)

```bash
# setup
cd /root/logotrace
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# ensure vtracer on PATH (cargo install vtracer / package)

# CLI
python -m src.cli samples/logo.png -o output/logo.svg --colors 2

# API
uvicorn src.api:app --host 127.0.0.1 --port 8095
curl -s http://127.0.0.1:8095/health
curl -s -F "file=@samples/logo.png" -F "colors=2" http://127.0.0.1:8095/vectorize -o out.svg

# tests
pytest -q
```

---

## Project Structure

```
/root/logotrace/
  README.md
  LICENSE
  NOTICE                  # third-party licenses
  .gitignore
  requirements.txt
  pyproject.toml          # optional
  docs/
    SPEC.md               # this file
    RESEARCH.md
    DECISIONS.md
    plans/
      2026-07-21-mvp-implementation.md
  samples/                # user logos (gitkeep; binaries optional)
  src/
    __init__.py
    cli.py                # CLI entry
    api.py                # FastAPI app
    pipeline.py           # preprocess → trace → post
    preprocess.py
    tracer_vtracer.py
    postprocess.py
    config.py
  tests/
    test_pipeline.py
    fixtures/
      tiny_logo.png
  output/                 # gitignored runtime outs
```

---

## Code Style

- Python 3.11, type hints on public functions
- snake_case modules/functions, PascalCase only if classes needed
- No silent failures: raise clear errors (unsupported format, tracer missing)
- Subprocess timeouts on tracer calls
- Example:

```python
def vectorize(image_bytes: bytes, colors: int = 2) -> str:
    """Return SVG string. colors must be 1..3."""
    ...
```

---

## Testing Strategy

- **Unit:** preprocess palette count; CLI arg validation
- **Integration:** fixture PNG → SVG contains `<svg` and non-empty paths
- **Manual:** user samples after upload — visual check + node-count note
- Framework: pytest
- Do not require GPU

---

## Boundaries

**Always:**
- Run pytest before claiming done
- Keep scope to flat 1-3 color logos
- Document tracer binary dependency
- GPL-3.0 headers / LICENSE present

**Ask first:**
- Adding Potrace as hard dependency
- Exposing API publicly (auth, rate limit)
- Calling external paid vectorizer API
- systemd unit / nginx vhost
- Changing license

**Never:**
- Commit secrets or large binary dumps of client logos without ask
- Implement photo/gradient ML pipeline in MVP
- Build web UI in MVP
- Use CairoSVG as tracer

---

## Non-goals (MVP)

- Match Vectorizer.AI on complex art
- DXF/EPS export (SVG only first)
- Auth, multi-user, billing
- Auto circle/rect shape snapping (nice-to-have later)

---

## Open Questions (for Tim before or during spike)

1. Default port / only CLI for first week?
2. Prefer **strict** palette (exactly N colors) vs "up to N"?
3. Background transparency: preserve alpha hole vs force opaque?
4. When samples arrive: pass/fail threshold — "usable in Inkscape without edits" vs "ok with 2 min cleanup"?

---

## Assumptions (correct me if wrong)

1. Runtime is this VPS (Linux), local process OK
2. English code/docs filenames; Russian OK in chat only
3. No remote GitHub until you say push
4. Samples you upload may be used as test fixtures inside this repo unless you say private-only
