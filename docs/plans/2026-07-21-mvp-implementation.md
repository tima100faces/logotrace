# LogoTrace MVP Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task after human approval.  
> **Gate:** Do not start Task 1 until Tim says «делай» / «погнали» / approves this plan.

**Goal:** Ship a local flat-logo tracer (up to N colors, default ~3) with CLI + minimal FastAPI, backed by VTracer. Preserve alpha. SVG first; PDF/web UI later.

**Architecture:** Thin Python orchestration: preprocess (Pillow) → subprocess VTracer → SVG postprocess → CLI/API facades. No custom ML.

**Tech Stack:** Python 3.11, FastAPI, Pillow, pytest, VTracer CLI, optional svgo, GPL-3.0

---

## Phase 0 — Prerequisites (before code)

### Task 0.1: Confirm plan with Tim

**Objective:** Human approves SPEC + ADRs + this plan.

**Verify:** Explicit approval message.

### Task 0.2: Install VTracer on host

**Objective:** `vtracer --help` works.

```bash
# preferred if rust/cargo available:
cargo install vtracer
# or download release binary to /usr/local/bin/vtracer
which vtracer && vtracer --help
```

**Verify:** exit 0 on help.

### Task 0.3: Collect samples (Tim)

**Objective:** 3-15 flat logos in `/root/logotrace/samples/`.

**Verify:** `ls samples/*.{png,jpg,webp}`.

---

## Phase 1 — Skeleton & config

### Task 1: Python package layout + dependencies

**Objective:** Importable `src` package and pinned deps.

**Files:**
- Create: `requirements.txt`
- Create: `src/__init__.py`
- Create: `src/config.py`
- Create: `LICENSE` (GPL-3.0 text)
- Create: `NOTICE`

**requirements.txt (initial):**
```
fastapi>=0.110
uvicorn>=0.27
python-multipart>=0.0.9
pillow>=10.0
typer>=0.12
pytest>=8.0
httpx>=0.27
```

**Step:** `python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt`

**Verify:** `python -c "import src; import fastapi, PIL"`

**Commit:** `chore: bootstrap package and dependencies`

---

### Task 2: Config module

**Objective:** Central defaults for colors, timeouts, paths.

**Files:**
- Create: `src/config.py`

```python
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLORS = 2
MIN_COLORS = 1
MAX_COLORS = 3
VTRACER_BIN = "vtracer"
TRACE_TIMEOUT_SEC = 60
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
```

**Verify:** `python -c "from src.config import MAX_COLORS; assert MAX_COLORS == 3"`

**Commit:** `feat: add config defaults`

---

## Phase 2 — Pipeline core (TDD)

### Task 3: Failing test for vectorize contract

**Objective:** Lock API of core function before implementation.

**Files:**
- Create: `tests/test_pipeline.py`
- Create: `tests/fixtures/tiny_logo.png` (generate in test setup if needed)

**Test sketch:**
```python
from src.pipeline import vectorize_file

def test_vectorize_returns_svg_string(tmp_path):
    # tiny 2-color PNG fixture
    out = vectorize_file(fixture_path, colors=2)
    assert out.lstrip().startswith("<svg")
    assert "</svg>" in out
```

**Run:** `pytest tests/test_pipeline.py -v`  
**Expected:** FAIL — module/function missing

**Commit:** `test: add failing vectorize contract test`

---

### Task 4: Preprocess — load + quantize colors

**Objective:** Reduce image to N colors before trace.

**Files:**
- Create: `src/preprocess.py`
- Test: `tests/test_preprocess.py`

**Behavior:**
- Accept path or bytes
- Convert RGBA→RGB or keep alpha if we decide preserve (default MVP: flatten on white **or** keep alpha — follow SPEC open question; default **preserve alpha if present**, else RGB)
- Quantize to `colors` using Pillow adaptive/octree
- Write temp PNG for tracer

**Verify:** pytest preprocess tests pass

**Commit:** `feat: preprocess palette quantize`

---

### Task 5: VTracer wrapper

**Objective:** Call vtracer CLI and return SVG text.

**Files:**
- Create: `src/tracer_vtracer.py`

**Behavior:**
- `run_vtracer(input_path, output_path, colors: int) -> None`
- Check binary exists → clear error if not
- Timeout `TRACE_TIMEOUT_SEC`
- Pass flags appropriate for flat color (document chosen flags after `vtracer --help` on install; e.g. filter-speckle, color precision)

**Verify:** unit test with mock subprocess **or** integration if binary present (skip if missing)

**Commit:** `feat: vtracer subprocess wrapper`

---

### Task 6: Postprocess SVG

**Objective:** Light cleanup for flatter/editable output.

**Files:**
- Create: `src/postprocess.py`

**MVP behavior:**
- Ensure XML/SVG well-formed enough to return
- Optional: strip metadata, collapse useless groups
- If `svgo` on PATH, run it; else no-op with log

**Verify:** test leaves `<svg` intact

**Commit:** `feat: svg postprocess hook`

---

### Task 7: pipeline.vectorize_file / vectorize_bytes

**Objective:** Wire preprocess → trace → postprocess.

**Files:**
- Create: `src/pipeline.py`
- Modify: tests to PASS

**Verify:** `pytest -q` all green (with vtracer installed)

**Commit:** `feat: end-to-end vectorize pipeline`

---

## Phase 3 — Interfaces

### Task 8: CLI

**Objective:** Usable command-line entry.

**Files:**
- Create: `src/cli.py`

```bash
python -m src.cli INPUT -o OUTPUT --colors 2
```

**Verify:** run on fixture, file exists, starts with `<svg`

**Commit:** `feat: CLI entrypoint`

---

### Task 9: FastAPI

**Objective:** Health + vectorize endpoints.

**Files:**
- Create: `src/api.py`

Endpoints:
- `GET /health` → `{"status":"ok"}`
- `POST /vectorize` multipart: `file`, optional `colors` (default 2) → SVG response

**Verify:**
```bash
uvicorn src.api:app --port 8095 &
curl -s localhost:8095/health
curl -s -F file=@tests/fixtures/tiny_logo.png -F colors=2 localhost:8095/vectorize | head
```

**Commit:** `feat: FastAPI vectorize endpoint`

---

## Phase 4 — Docs & freeze

### Task 10: README usage + NOTICE licenses

**Objective:** Operator can run without chat history.

**Files:**
- Modify: `README.md`
- Create/update: `NOTICE`

**Commit:** `docs: usage and third-party notices`

---

### Task 11: Manual QA on Tim samples

**Objective:** Score real logos; record in `docs/QA-NOTES.md`

**Files:**
- Create: `docs/QA-NOTES.md`

Table: file | colors | usable? | notes | node soup?

**Commit:** `docs: sample QA notes`

---

## Verification checklist (release MVP)

- [ ] `pytest -q` green
- [ ] CLI works on ≥3 samples
- [ ] `/health` 200
- [ ] `/vectorize` returns SVG
- [ ] No secrets in git
- [ ] LICENSE + NOTICE present
- [ ] Report to Tim in tima-office format

---

## Risks

| Risk | Mitigation |
|------|------------|
| VTracer geometry still messy | Parameter grid + Potrace mono fallback |
| Potrace GPL-2 coupling | Optional extra; document; keep default VTracer-only |
| Bad antialiased logos | Stronger preprocess / threshold mode |
| Large uploads | `MAX_UPLOAD_BYTES` + reject |

---

## Out of scope (do not implement in this plan)

- Web UI
- Vectorizer.AI API hybrid
- DXF/EPS
- systemd/nginx (ask first)
- ML shape fitting

---

## Execution order summary

0. Approve + install vtracer + samples  
1. Bootstrap  
2. Config  
3. Failing test  
4. Preprocess  
5. VTracer wrapper  
6. Postprocess  
7. Pipeline green  
8. CLI  
9. API  
10. Docs  
11. Real-sample QA  

**Stop after plan approval gate. No implementation without Tim command.**
