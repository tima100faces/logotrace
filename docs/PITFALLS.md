# PITFALLS — logotrace

## 2026-09-24 — `uv venv` produces a service that dies with 203/EXEC

- **Symptom:** the unit restarts in a loop, `Failed to execute /srv/sites/logotrace/venv/bin/uvicorn:
  Permission denied`.
- **Cause:** `uv venv` resolves to uv's managed CPython inside
  `/srv/hermes/.local/share/uv/python/...`. The service account cannot enter `/srv/hermes`
  (mode 770), so executing the interpreter fails with EACCES.
- **Fix:** build the virtualenv with the system interpreter — `/usr/bin/python3 -m venv`, which is what
  `deploy/live-venv.sh` does. Packages can still be installed with `uv pip install --python <venv>`.
- **Rule:** everything the unit executes has to live outside `/srv/hermes`.

## 2026-09-24 — a virtualenv staged in the repository arrives broken

- **Symptom:** right after `hermes-site-ctl create`, the live tree already contained a `venv/` whose
  shebangs pointed at `/srv/hermes/projects/logotrace/venv/bin/python3` — the same 203/EXEC.
- **Cause:** `sync` copies the staged tree as-is and preserves absolute shebangs, so a venv built in the
  repository carries paths the service account cannot read.
- **Fix:** keep `venv/` out of the repository (it is gitignored) and build it in the live tree.
- **Rule:** the deploy stage must contain only files whose absolute paths stay valid at the destination.

## 2026-09-24 — a rebuild inside the live tree fails: the ACL mask has no write bit

- **Symptom:** `uv venv --clear` emptied the directory and then failed with
  `failed to remove directory ... Permission denied`; the leftover empty directory made a plain
  `uv venv` refuse with "a directory already exists".
- **Cause:** `/srv/sites/logotrace` carries `user:hermes:rwx #effective:r-x` (mask `r-x`): the agent may
  write *inside* existing directories but cannot create or remove entries at the top level.
- **Fix:** create into the existing empty directory — `python3 -m venv <dir>` accepts one — or ask the
  operator for the missing write bit.
- **Rule:** in the live tree assume "write inside"; check before planning a delete.

## 2026-09-24 — the old path prefix survived in the page as a `<base>` tag

- **Symptom:** the site opened at `https://trace.idealabs.dev/` with no styling at all — plain HTML.
- **Cause:** `static/index.html` carried `<base href="/trace/" />` from the days when the service lived
  under `idealabs.co/trace/`. Every relative URL (`static/styles.css`, `static/app.js`) was therefore
  requested as `/trace/static/...` → 404. Server-side checks missed it: `curl` on `/static/styles.css`
  answers 200, because the file is served fine — the browser was asking for the wrong path.
- **Fix:** the `<base>` tag is gone; `API_BASE` in `static/app.js` defaults to `/` and still honours a
  base tag if a future deployment puts the service under a prefix.
- **Rule:** moving a service from a path to its own hostname means hunting for path knowledge in the
  front end — `<base>`, hard-coded prefixes, absolute asset URLs. And check pages the way a browser
  does, not only with `curl` on the endpoints you expect.

## 2026-09-24 — a service can be built for the wrong domain name

- **Symptom:** the site was created with `--domain trace.idealabs.co`, the owner pointed
  `trace.idealabs.dev` at the host instead, and the name could not simply be changed.
- **Cause:** `hermes-site-ctl` has no "change domain" subcommand — `--domain` is baked into the vhost
  and the `.domain` file at `create` time — and recreating the same slug fails because the `site-<slug>`
  account survives `remove`.
- **Fix:** create a second site under a new slug (`trace`) for the right domain; retire the first one
  later (soft delete, one root pass to clean the leftovers).
- **Rule:** confirm the exact domain with the owner *before* `create`, and prefer the domain the rest of
  the family already uses (`share.idealabs.dev` → `.dev`).

## 2026-09-24 — `sync` mirrors the staged tree with deletion, so the venv must exist in the repo

- **Symptom:** right after `hermes-site-ctl sync`, `venv/bin/python` was gone and the unit fell over;
  the directory could not simply be recreated (`Permission denied`) because the agent has no write bit
  on `/srv/sites/logotrace` itself.
- **Cause:** the hosting script mirrors the staged tree into the live directory with deletion —
  anything absent from the repository is removed, and `venv/` was absent.
- **Fix:** keep the directory in the staged tree (`venv/.gitkeep`, with `venv/*` still ignored) so the
  mirror keeps it, then build the environment inside it; `deploy/deploy.sh` does sync → venv →
  restart → health in one command.
- **Rule:** with a mirroring deploy, an empty directory that must survive belongs in the repository.
  And note that the agent can only write *inside* existing directories of the live tree, never create
  or remove entries at its top level.

## 2026-09-24 — Python cannot read a `pyvenv.cfg` owned by the agent

- **Symptom:** `PermissionError: [Errno 13] Permission denied: '/srv/sites/logotrace/venv/pyvenv.cfg'`,
  the unit exits 1 immediately after start.
- **Cause:** files created by the agent are `-rw-rw----` under the inherited default ACL, leaving
  `other` without read; the service runs as `site-logotrace`.
- **Fix:** `find <venv> -mindepth 1 -exec chmod a+rX {} +`. The recursive form starting at the
  directory itself reports `EPERM` (that directory belongs to the site account) — harmless, but it must
  not abort the script.
- **Rule:** after building anything in the live tree as the agent, make it world-readable.

## 2026-09-24 — a tracked artifact that is also gitignored

- **Symptom:** `git status` reports `output/matrix_comparison.md` as modified although `output/` is in
  `.gitignore`.
- **Cause:** the file was committed before the ignore rule appeared; ignoring does not untrack.
- **Rule:** to make a tracked artifact leave the repository, use `git rm --cached`, not `.gitignore`.

## 2026-07 (moved here with the code) — palette traps

- **Sample_10 palette loss:** border-median background detection picked the dark green plate itself and
  the paper/fullbleed split turned 97 % of it white. Fixed by removing the split — the background is
  always kept (`d3be21d`).
- **White panel rendering grey:** `collapse_gradient_ramps` used the darkest member as its grey anchor,
  so white plus edge-mix grey became grey. Fixed by choosing the anchor by mass (`4c58039`).
- **Bordeaux merging into brown:** the hue-bucketing guard used a lightness delta (0.094 ≤ 0.10) and
  merged them. Fixed by switching to the same weighted HSL-distance guard as step 2 (threshold 0.18,
  bordeaux/brown 0.210) — `f5fb537`.
- **Threshold window:** the merge threshold must stay below 0.210 (bordeaux vs brown) and above 0.017
  (adjacent brown ramp steps). 0.18 is the window.
