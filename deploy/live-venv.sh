#!/usr/bin/env bash
# Build (or rebuild) the site's virtualenv inside the live tree.
#
# Why the virtualenv lives in the live directory and not in the repository:
#   * `hermes-site-ctl sync` copies the staged tree over the live one; a venv
#     staged in the repository arrives with shebangs pointing into /srv/hermes,
#     which the site account cannot enter — the unit then dies with 203/EXEC.
#   * a venv built here is self-contained: its shebangs point at a path the site
#     account can read.
#
# Why the system interpreter and not uv's managed one: same reason. `uv venv`
# resolves to ~/.local/share/uv/python/... (inside /srv/hermes) and the service
# account cannot execute it (203/EXEC, "Permission denied"). So the environment
# is created with /usr/bin/python3 and only the packages come from uv.
#
# Usage: bash deploy/live-venv.sh [/srv/sites/logotrace]
set -euo pipefail

SITE_DIR="${1:-/srv/sites/trace}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_SYSTEM="${PY_SYSTEM:-/usr/bin/python3}"
UV="${UV:-$HOME/.hermes/bin/uv}"

if [ ! -d "$SITE_DIR" ]; then
  echo "no live directory at $SITE_DIR — run 'hermes-site-ctl create trace --domain trace.idealabs.dev' first" >&2
  exit 1
fi

if [ ! -x "$SITE_DIR/venv/bin/python3" ]; then
  "$PY_SYSTEM" -m venv "$SITE_DIR/venv"
fi

"$UV" pip install --python "$SITE_DIR/venv" -r "$REPO_DIR/requirements.txt"

# The service account belongs to site-logotrace, while everything here belongs to the agent:
# without readable permissions Python cannot even load pyvenv.cfg, and the unit dies at startup.
# The venv directory itself is owned by the site account, so the recursive form reports EPERM on it —
# that must not abort the script.
chmod a+rX "$SITE_DIR/venv" 2>/dev/null || true
find "$SITE_DIR/venv" -mindepth 1 -exec chmod a+rX {} + 2>/dev/null || true

echo "venv ready: $SITE_DIR/venv $("$SITE_DIR/venv/bin/python3" -V)"
echo "next: sudo /usr/local/sbin/hermes-site-ctl restart logotrace"
