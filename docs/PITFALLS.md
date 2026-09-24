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
