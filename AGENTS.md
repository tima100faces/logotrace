# logotrace

- **What it is:** flat-logo raster (JPEG/PNG) → clean RGB vector PDF, ready for print and for
  Illustrator. Live at <https://trace.idealabs.co>.
- **Level:** Project
- **Stack:** Python 3 (FastAPI + uvicorn) behind nginx, static HTML/JS UI; VTracer 0.6.4 as a bundled
  binary (`bin/vtracer`); `rsvg-convert` (system package `librsvg2-bin`) for SVG→PDF and for the
  output self-check.
- **Where it runs:** mainframe. Code `/srv/hermes/projects/logotrace`; live tree `/srv/sites/logotrace`
  (owned by `site-logotrace`, never edited by hand); the virtualenv lives **in the live tree** and is
  built by `deploy/live-venv.sh`, because the site account cannot read `/srv/hermes`.
- **Start:** `PYTHONPATH=. .venv/bin/python -m src.cli input/logo.jpg -o output/logo.pdf` for the CLI ·
  `systemctl is-active site-logotrace` for the service (port 8301).
- **Deploy:** `bash deploy/deploy.sh` — mirrors the staged tree into the live one, rebuilds the
  virtualenv (`sync` deletes whatever the repository does not contain), restarts the unit and checks
  `/health`. `deploy/live-venv.sh` alone rebuilds just the environment.
- **Tests / checks:** `python -m pytest tests/test_pipeline.py tests/test_api.py -q` (safe subset —
  the eval tests load real images and can run out of memory) · `curl -s localhost:8301/health` ·
  `python -m src.eval input/ --matrix --colors 4` for the quality matrix.
- **Do not touch without asking:** `/srv/sites/logotrace` (deploy replaces the whole tree),
  `bin/vtracer`, the baseline numbers in `docs/EVAL-BASELINE.md`.
- **Licence:** GPL-3.0-or-later (`LICENSE`, `NOTICE`); VTracer keeps its own MIT licence.

---

## What this file is

This is the project's working agreement, and it is read by whichever agent works here — Claude Code,
Codex, Hermes/Rusty. `AGENTS.md` is the name agents look for; a `CLAUDE.md` beside it is only a
pointer for older tools.

The repo is the source of truth: not memory, not chat history, not a wiki page.

## Language

Talk to Tim in **Russian**. Everything else — code, comments, commits, file names,
UI strings, documentation in this repo — in **English**.

---

## Roles

- **Owner (Tim)** — decides product questions, approves anything significant, accepts the work.
- **Architect (Claude / Fable in chat)** — breaks down the idea, writes tasks, reviews results, writes the docs.
- **Executor (Claude Code, Codex, Hermes/Rusty — whichever works here)** — does one task, verifies it, reports back.

The agent makes technical decisions on its own. Product decisions it asks about.
Docs are written by the architect from the executor's report — not by the executor from memory.

---

## Complexity level — decided BEFORE any work starts

The level decides how much process applies. Default is Lightweight.

**Lightweight** — idea, prototype, small fix.
Docs: `docs/STATUS.md` + `docs/PITFALLS.md`. Git: commits straight to `main`.

**Project** — the thing is alive and in use.
Docs: `STATUS.md` + `PRODUCT.md` + `PLAN.md` + `DECISIONS.md` + `PITFALLS.md`.
Git: commits straight to `main`, one commit per finished step — the history must be revertable
step by step.

**Critical** — auth, payments, personal data, DB migrations, data deletion,
production release, anything irreversible.
Separate plan + branch + PR + explicit owner approval before merge.

A Project-level change that touches more than one component, or changes data, is treated as Critical
until the owner rules otherwise. Raising the level is the owner's call, not the agent's. Lowering it —
never.

---

## Where everything lives

Everything about the project lives **in this folder**: code, docs, scripts, fixtures, the rules above.
A project whose parts are scattered — half in a wiki, half in chat, half on someone's desktop — is a
project whose current state nobody can trust.

`docs/` is the operational part, and it is written for the next agent, not for a human reader:
`STATUS.md` (the only mandatory one), `PRODUCT.md`, `PLAN.md`, `DECISIONS.md`, `PITFALLS.md`.

An external wiki may keep the project's page — a map, links, the story behind it. It must not keep a
second copy of these files: two copies drift, and then nobody knows which one is true.

---

## Session start

1. Read this file and `docs/STATUS.md`.
2. Check the actual state of the repo (branch, uncommitted changes).
3. Report briefly: how you understand the project, what was done last, what you propose next.

Do not start significant changes before context is restored.
The repo is the source of truth — not memory, not chat history.

---

## Task format

**Goal.** What result is expected.

**Context.** Why this task exists.

**Scope.** What exactly to do.

**Out of scope.** What not to touch. This section matters more than Scope.

**Acceptance criteria.** Observable conditions for accepting the work.

**Verification.** Specific commands or scenarios + **expected output**.

**Report.** The executor returns:
- what changed, as a list of files;
- verification results (actual output, not a retelling);
- what is unfinished, and known limitations;
- branch name;
- recommended next step.

One task = one session. A task does not turn into a project-wide refactor.
Found an adjacent problem along the way? Do not fix it — put it in the report.

---

## Git and deploy

| Level | How | Who accepts |
|---|---|---|
| Lightweight | commit straight to `main` | owner, by eye |
| Project | commit straight to `main`, one commit per finished step → push → architect reviews the commits | architect + owner |
| Critical | branch + PR + explicit approval | owner only |

Rules:
- Commit message: one line, what was actually done. No "update", "fixes", "wip".
- Never commit: `.env`, keys, tokens, `venv/`, `node_modules/`, databases.
- DB migrations are always Critical, even for a single column.
- Deploy only on an explicit command. Never "while I'm at it".
- If something goes wrong: **STOP, show the output, do not fix it yourself**.

---

## Verification

Verification means a produced artifact, not the word "verified".

Counts as verification:
- a command plus its real output, matching what was expected;
- a previously failing test that now passes;
- comparison against a reference file, where one exists;
- a render or screenshot, where the result is visual.

Does not count: "should work", "looks right", "tested locally" with no output.

No automated tests? Write **and run** a manual scenario, and attach the result.
Never claim something is verified if verification did not actually happen.
An honest "I could not verify this" beats "done".

Before handing off: the main scenario works, nothing adjacent is broken,
no accidental changes were made.

---

## Session end

1. Update `docs/STATUS.md` (always, no exceptions).
2. For Project level: update `PLAN.md`, log significant decisions in `DECISIONS.md`.
3. Lost time on something that looked obvious? One line into `PITFALLS.md`: what broke, why, how not
   to step on it again. The next agent reads that file first when something smells familiar.
4. Report: what was done, what remains, what comes next.

---

## Constraints

- Do not add anything that was not asked for. No features, no dependencies, no "fixed this too".
- Between a complex and a simple working solution — take the simple one.
- Do not present assumptions as verified facts.
- Do not hide failing tests or unfinished work.
- Do not perform anything irreversible without approval.
- Do not leave documentation knowingly out of date.
