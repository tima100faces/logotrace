# PLAN — logotrace

**Updated:** 2026-09-24 · **Stage:** migration to mainframe (in progress)

## Now — the migration is almost done

Done on 24.09.2026: the code moved, the service runs as `site-trace` on port 8302, HTTPS
<https://trace.idealabs.dev> is live with a Let's Encrypt certificate (valid until 2026-12-23), and SVG
output was verified end to end from outside.

What is left:

1. `poppler-utils` installed on mainframe (owner) — it provides `pdftoppm`, which the self-check of a
   PDF output needs. Until then `format=pdf` answers 422 while `format=svg` works.
2. PDF verified end to end through the public URL, the suite green (12/12), and one result opened in
   Illustrator.
3. The stray `logotrace` site on mainframe removed — it was created for the `trace.idealabs.co` name
   before the owner pointed the domain at `trace.idealabs.dev`. Separate, explicitly approved step
   (`hermes-site-ctl remove` is soft: the account, the live directory and the vhost file stay behind
   and need one root pass).
4. The old copy on OpenClaw retired — the systemd unit, the nginx `location /trace/` block and
   `/root/logotrace` — after the owner confirms the new address is the one to keep.

## Parked (deliberately not now)

- **Back-compat for the old URL:** a redirect from `idealabs.co/trace/` to the new address needs the
  `idealabs.co` vhost, which still lives on OpenClaw — it waits for that site's migration.
- Cloudflare in front of `trace.idealabs.co` (orange cloud) — after direct TLS works.
- UI polish from Tim's list: the interface moved as-is.
- Trim the live tree: `input/` and `output/` travel with every `sync` (~43 MB). Moving the samples out
  of the staged tree needs a look at how `eval.py` resolves paths.
- `sample_11.jpg` and `scripts/` are still untracked in git; the sample is referenced by the palette
  work and should be committed.

## Risks

- **Interpreter drift.** The live virtualenv is built on `/usr/bin/python3` (3.14.4) because the site
  account cannot execute uv's managed interpreter inside `/srv/hermes`. A distro upgrade can move that
  interpreter: rebuild with `deploy/live-venv.sh` and re-run the tests afterwards.
- **The venv must never be staged.** `sync` copies the staged tree over the live one; a virtualenv that
  comes from the repository arrives with shebangs into `/srv/hermes` and the unit dies with `203/EXEC`.
  That is exactly how it broke the first time.
- **Old host still serves the domain** until DNS is switched: two copies of the service exist for a
  while, and the old one is the one users reach.
