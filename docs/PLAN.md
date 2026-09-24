# PLAN — logotrace

**Updated:** 2026-09-24 · **Stage:** migration to mainframe (in progress)

## Now — the migration is not finished until

1. `librsvg2-bin` is installed on mainframe (owner) — without it SVG→PDF and the output self-check do
   not run, so the service cannot vectorize at all.
2. End-to-end check on a real sample through the public URL: PDF and SVG, colour headers present
   (`X-LogoTrace-Colors`, `X-LogoTrace-Colors-Mode`), the file opens in Illustrator.
3. `pytest tests/test_api.py tests/test_pipeline.py` green (12/12) inside the live virtualenv.
4. DNS: `trace.idealabs.co` → `188.245.227.6`, DNS-only at first, then
   `sudo hermes-site-ctl cert logotrace`, then a check from outside (`curl -4` and `curl -6`, plus the
   certificate subject and dates).
5. README and the wiki passport carry the new address.
6. Only afterwards, as a separate explicitly approved step: retire the old copy on OpenClaw — the
   systemd unit, the nginx `location /trace/` block and `/root/logotrace`. Keep the old tree until the
   new URL is verified from outside.

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
