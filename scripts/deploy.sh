#!/usr/bin/env bash
# Sync local pyscript/ tree to Home Assistant /config/pyscript/
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env
fi

HA_HOST="${HA_HOST:-homeassistant.local}"
HA_USER="${HA_USER:-root}"
HA_CONFIG_PATH="${HA_CONFIG_PATH:-/config}"
DEST="${HA_USER}@${HA_HOST}:${HA_CONFIG_PATH}/pyscript/"

echo "Deploying ${ROOT}/pyscript/ -> ${DEST}"
# Do not preserve owner/group/perms — HA rejects chgrp/chown from rsync -a
rsync -rltvz \
  --no-owner --no-group --no-perms \
  --exclude='config.yaml.example' \
  --exclude='*.example' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  "${ROOT}/pyscript/" \
  "${DEST}"

echo "Done. Pyscript reloads changed files automatically."
