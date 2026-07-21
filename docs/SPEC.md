# Spec: LogoTrace MVP

## Objective

Build a local tool that converts **flat logo rasters** (1-3 solid colors) into **clean flat SVG** suitable for edit/print/cut workflows.

**User:** Tim (operator / product). Later maybe API consumers.  
**Why:** Vectorizer.AI is strong but paid/heavy; for flat logos OSS pipeline is enough and controllable.

### User stories

1. As an operator, I drop a 2-color PNG logo and get an SVG with two flat fills and editable paths.
2. As a developer, I `POST` an image to `/vectorize` and receive `image/svg+xml`.
3. As an operator, I can set `--colors N` as **max palette size** (up to N, not always exactly N).
4. As an operator, if the source has transparency, the SVG keeps transparent background (no forced white matte).

### Success criteria (MVP done when)

- [ ] CLI converts PNG/JPG/WebP → SVG for samples in `samples/`
- [ ] HTTP `GET /health` → 200
- [ ] HTTP `POST /vectorize` accepts image, returns SVG
- [ ] `--colors N` means **at most N** colors (default TBD; start with default 3)
- [ ] Transparent source → transparent SVG background (do not flatten onto white)
- [ ] Output is flat fills (no intentional gradients)
- [ ] At least one automated test with a tiny fixture image
- [ ] README documents install + usage
- [ ] Side-by-side notes on 3+ real logos after user uploads samples (manual QA)

### Post-MVP (not blocking MVP)

- Web UI (after tracer quality is validated on real samples)
- PDF export (vector PDF from SVG)
- Tune exact default N and auto-detect heuristics

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

## Decisions from Tim (2026-07-21)

1. **Interfaces:** MVP — CLI + API both fine for tests. **Web UI after** quality tests. Not in MVP.
2. **Colors:** **up to N**, not forced exact N. Exact default N and auto-detect still open (decision forks later on samples).
3. **Transparency:** if alpha present → **keep transparent**, do not paste on white.
4. **PDF:** wanted eventually; **not required in MVP** (SVG first).

## Still open (minor — can resolve on samples)

1. Default `N` for `--colors` when user omits flag (proposal: **3**)
2. Auto-detect palette size vs always use default N
3. Manual QA bar: "usable without edits" vs "ok with 2 min cleanup"
4. Public bind vs localhost-only for API during tests (proposal: **127.0.0.1**)

---

## Assumptions (correct me if wrong)

1. Runtime is this VPS (Linux), local process OK
2. English code/docs filenames; Russian OK in chat only
3. No remote GitHub until you say push
4. Samples you upload may be used as test fixtures inside this repo unless you say private-only
5. Primary deliverable of MVP is **SVG**; PDF is post-MVP conversion from SVG
