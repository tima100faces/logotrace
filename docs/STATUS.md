# STATUS — logotrace

**Updated:** 2026-09-24 · **Level:** Project · branch `main`

## Where it is

Moved from the old VPS (`OpenClaw`, `/root/logotrace`) to mainframe on 2026-09-24. The service runs as
`site-logotrace` on port 8301 behind nginx for `trace.idealabs.co` and answers `/health` with
`{"status":"ok","version":"0.4.0"}`.

| Piece | State |
|---|---|
| Code | `/srv/hermes/projects/logotrace` (was `/root/logotrace` on the old host) |
| Live tree | `/srv/sites/logotrace` · `systemctl is-active site-logotrace` → `active` |
| Virtualenv | `/srv/sites/logotrace/venv`, rebuilt by `deploy/deploy.sh` on the **system** interpreter (3.14.4); the empty directory is kept in the repository so it survives the mirroring deploy |
| Deploy | `bash deploy/deploy.sh` — sync → virtualenv → restart → health (the venv must be rebuilt because `sync` deletes what the repository does not contain) |
| Domain | `trace.idealabs.co` — vhost created, **TLS pending** (DNS still points at the old host) |
| Vectorization | **blocked on a system package** — see below |

## What works

- Service starts and stays up; `/health` and the web UI answer through nginx — checked with
  `curl -k --resolve trace.idealabs.co:443:127.0.0.1 https://trace.idealabs.co/` (200, 3 744 bytes).
- `PYTHONPATH=. venv/bin/python -m pytest tests/test_pipeline.py tests/test_api.py -q` →
  `11 passed, 1 failed` (the failure is the missing system library, see below).

## What is broken

- **`/vectorize` answers 422** — `output failed self-check: rsvg-convert required for verify`.
  `pipeline.vectorize_bytes` always verifies its output by rasterizing it, and the rasterizer needs
  `rsvg-convert`; the same binary is what converts SVG into PDF. `librsvg2-bin` is not installed on
  mainframe. Fix is one command by the owner: `apt install -y librsvg2-bin`. Until then the service is
  up but produces nothing.
- `tests/test_pipeline.py::test_vectorize_file_pdf` fails for the same reason (`OSError: no library`).
- No TLS certificate yet: DNS for `trace.idealabs.co` has not been switched to the new host.

## Also true, not broken

- `output/` and `input/` are copied into the live tree with the rest of the repository (they are not
  excluded from `sync`). Harmless but noisy: ~43 MB of samples and past runs travel on every deploy.

## Next

1. Owner: `apt install -y librsvg2-bin` on mainframe.
2. Owner: point `trace.idealabs.co` (A record) at `188.245.227.6`, DNS-only (grey cloud) so the
   certbot HTTP-01 challenge reaches nginx; then `sudo hermes-site-ctl cert logotrace`.
3. Then: end-to-end check through the public URL — PDF and SVG for a real sample, both check out, and
   the test suite green (12/12).
4. Later, and only on an explicit command: retire the old copy (`/root/logotrace`, `logotrace.service`
   and the nginx `location /trace/` block on OpenClaw) after the new URL is verified from outside.
