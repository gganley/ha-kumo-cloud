#!/usr/bin/env bash
# Copy the integration into the Home Assistant config directory and restart HA.
# HA runs in a rootless podman container with ~/.config/homeassistant bind-mounted
# at /config, so the files have to live physically inside that tree -- a symlink
# out to this repo would dangle inside the container.
set -euo pipefail

HA_CONFIG="${HA_CONFIG:-$HOME/.config/homeassistant}"
DEST="$HA_CONFIG/custom_components/kumo_cloud"
SRC="$(cd "$(dirname "$0")" && pwd)/custom_components/kumo_cloud"

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -r "$SRC" "$DEST"
find "$DEST" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
echo "deployed -> $DEST"

if [[ "${1:-}" == "--restart" ]]; then
  podman restart homeassistant >/dev/null
  echo "restarted homeassistant"
fi
