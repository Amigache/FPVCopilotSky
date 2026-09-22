#!/bin/bash
# Enable API authentication (bearer token) for FPV Copilot Sky.
#
# Generates a random token into /etc/fpvcopilot-sky/env (0600, root) and
# installs a systemd drop-in that loads it, so the secret never lives in the
# repository or the main unit file. Idempotent: keeps the existing token unless
# --rotate is passed.
#
# Usage: sudo bash scripts/setup-auth.sh [--rotate]

set -euo pipefail

ENV_DIR="/etc/fpvcopilot-sky"
ENV_FILE="$ENV_DIR/env"
DROPIN_DIR="/etc/systemd/system/fpvcopilot-sky.service.d"
DROPIN_FILE="$DROPIN_DIR/auth.conf"

ROTATE=0
if [ "${1:-}" = "--rotate" ]; then
    ROTATE=1
fi

if [ "$(id -u)" -ne 0 ]; then
    echo "This script must run as root (use sudo)." >&2
    exit 1
fi

mkdir -p "$ENV_DIR"
chmod 700 "$ENV_DIR"

if [ -f "$ENV_FILE" ] && grep -q '^FPV_API_TOKEN=' "$ENV_FILE" && [ "$ROTATE" -eq 0 ]; then
    echo "✓ API token already configured ($ENV_FILE) — keeping it (use --rotate to regenerate)."
else
    TOKEN="$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    umask 077
    printf 'FPV_API_TOKEN=%s\n' "$TOKEN" > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    chown root:root "$ENV_FILE" 2>/dev/null || true
    echo "✓ Generated a new API token in $ENV_FILE"
    echo ""
    echo "  API token: $TOKEN"
    echo "  (guárdalo; la WebUI lo pedirá y lo recordará en este navegador)"
    echo ""
fi

mkdir -p "$DROPIN_DIR"
cat > "$DROPIN_FILE" <<'EOF'
# Enables API authentication when /etc/fpvcopilot-sky/env defines FPV_API_TOKEN.
[Service]
EnvironmentFile=-/etc/fpvcopilot-sky/env
EOF
chmod 644 "$DROPIN_FILE"

systemctl daemon-reload
systemctl restart fpvcopilot-sky 2>/dev/null || true

echo "✓ API authentication enabled (drop-in: $DROPIN_FILE)"
