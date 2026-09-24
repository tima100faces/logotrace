#!/usr/bin/env bash
# One-command deploy for the hosted service.
#
# Why the virtualenv step is part of the deploy: `hermes-site-ctl sync` mirrors the staged tree into
# the live directory **with deletion** — anything that is not in the repository goes, `venv/`
# included. So every deploy rebuilds the environment (fast, the packages come from the uv cache)
# before the unit is restarted.
#
# Usage: bash deploy/deploy.sh [site-slug] [port]      # defaults: trace 8302
set -euo pipefail

SITE="${1:-trace}"
PORT="${2:-8302}"
SITE_DIR="/srv/sites/$SITE"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CTL=/usr/local/sbin/hermes-site-ctl

sudo -n "$CTL" sync "$SITE"
bash "$REPO_DIR/deploy/live-venv.sh" "$SITE_DIR"
sudo -n "$CTL" restart "$SITE"

for _ in $(seq 1 20); do
  curl -sf --max-time 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && break
  sleep 1
done

echo "unit: $(systemctl is-active "site-$SITE")"
curl -sS --max-time 10 "http://127.0.0.1:$PORT/health" && echo
