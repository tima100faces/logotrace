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
| SVG output | **works** — `format=svg` returns 200 with a VTracer file (190 KB for sample_11) |
| PDF output | **works** — `format=pdf` returns 200, `application/pdf`, `%PDF-1.7` (34 893 bytes for sample_02) |

## What works

- HTTPS from the outside: `curl -4 https://trace.idealabs.dev/health` → `{"status":"ok","version":"0.4.0"}`;
  certificate subject `CN=trace.idealabs.dev`, issuer Let's Encrypt, valid until 2026-12-23.
- Web UI (200), local CSS and JS (200, `text/css` and `text/javascript`) — the old `<base href="/trace/">`
  that broke styling after the move is gone.
- Both output formats end to end through the public address, self-checks included.
- `PYTHONPATH=. /srv/sites/trace/venv/bin/python3 -m pytest tests/test_pipeline.py tests/test_api.py -q`
  → **20 passed**.

## What is broken

- The `logotrace` site created earlier for the `.co` name still exists on mainframe (port 8301, no
  traffic — nothing resolves to it). Waiting for the owner's go-ahead to `remove` it.
- The old copy on the old host still serves `idealabs.co/trace/` — retired separately, once the owner
  confirms the new address is the one to keep.
- No AAAA record for the domain, so IPv6 clients cannot reach it at all (which is at least safe: the
  hosting template writes IPv4-only vhosts, and an AAAA record would send them to the board's default
  vhost).

## Next

1. Owner: approve removal of the stray `logotrace` site (and later of the old copy on OpenClaw).
2. Open one real result in Illustrator and confirm the colours and curves before the old host is
   switched off.
3. Parked: a redirect from `idealabs.co/trace/` once `idealabs.co` itself moves to mainframe.
