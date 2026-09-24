# STATUS — logotrace

**Updated:** 2026-09-24 · **Level:** Project · branch `main`

## Where it is

Moved from the old VPS (`OpenClaw`, `/root/logotrace`) to mainframe on 2026-09-24. The service runs as
`site-logotrace` on port 8301 behind nginx for `trace.idealabs.co` and answers `/health` with
`{"status":"ok","version":"0.4.0"}`.

| Piece | State |
|---|---|
| Code | `/srv/hermes/projects/logotrace` (was `/root/logotrace` on the old host) |
| Site | `trace` → live tree `/srv/sites/trace`, `systemctl is-active site-trace` → `active`, port 8302 |
| Address | <https://trace.idealabs.dev> — live, Let's Encrypt certificate valid until 2026-12-23, checked from outside over IPv4 |
| Virtualenv | `/srv/sites/trace/venv`, rebuilt by `deploy/deploy.sh` on the **system** interpreter (3.14.4); the empty directory is kept in the repository so it survives the mirroring deploy |
| Deploy | `bash deploy/deploy.sh` — sync → virtualenv → restart → health (the venv must be rebuilt because `sync` deletes what the repository does not contain) |
| SVG output | **works** — `format=svg` returns 200 with a 386 KB VTracer file |
| PDF output | **blocked on one more system package** — see below |

## What works

- HTTPS from the outside: `curl -4 https://trace.idealabs.dev/health` → `{"status":"ok","version":"0.4.0"}`;
  certificate subject `CN=trace.idealabs.dev`, issuer Let's Encrypt, valid until 2026-12-23.
- The web UI is served (200) and so is `/static/*`.
- `format=svg` vectorization end to end, self-check included: 200, 386 308 bytes.
- `PYTHONPATH=. /srv/sites/trace/venv/bin/python3 -m pytest tests/test_pipeline.py tests/test_api.py -q`
  → **16 passed, 4 failed**; every failure is a PDF path that waits for `pdftoppm`
  (`test_vectorize_file_pdf`, `test_vectorize_bytes_pdf`, `test_vectorize_endpoint_pdf`,
  `test_vectorize_palette_auto_header`).

## What is broken

- **`format=pdf` answers 422** — `output failed self-check: need pdftoppm or ImageMagick convert to
  rasterize PDF`. `rsvg-convert` now turns SVG into PDF (installed 24.09), but the self-check of a PDF
  output rasterizes the first page and for that `src/verify.py` looks for `pdftoppm` (package
  `poppler-utils`) or ImageMagick — neither is installed on mainframe. The old host had `pdftocairo`,
  so this is a missing piece of the same set. One command by the owner fixes it.
- The old site is still running on the old host and still answers `idealabs.co/trace/` — to be retired
  only after the owner agrees (the new address is already verified from outside).
- No AAAA record for the domain, so IPv6 clients cannot reach it at all (which is at least safe: the
  hosting template writes IPv4-only vhosts, and an AAAA record would send them to the board's default
  vhost).

## Next

1. Owner: `apt install -y poppler-utils` on mainframe (gives `pdftoppm`), then PDF output works.
2. Then: verify PDF end to end through the public URL, run the test suite (12/12), open the result in
   Illustrator once.
3. Then, as a separate explicitly approved step: retire the old copy — `remove logotrace` on mainframe
   (the `.co` site created by mistake), and on OpenClaw the unit, the nginx `location /trace/` block
   and `/root/logotrace`.
4. Parked: a redirect from `idealabs.co/trace/` once `idealabs.co` itself moves to mainframe.
