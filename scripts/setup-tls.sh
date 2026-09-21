#!/bin/bash
# =============================================================================
# Enable HTTPS for FPV Copilot Sky.
#
# Usage:
#   sudo bash scripts/setup-tls.sh                 # self-signed certificate (LAN)
#   sudo bash scripts/setup-tls.sh --tailscale     # Tailscale certificate
#
# Generates a certificate under /etc/ssl/fpvcopilot/, installs the TLS nginx
# config (systemd/fpvcopilot-sky.tls.nginx) and reloads nginx. deploy.sh will
# keep the TLS config as long as the certificate exists.
# =============================================================================
set -euo pipefail

PROJECT_DIR="/opt/FPVCopilotSky"
CERT_DIR="/etc/ssl/fpvcopilot"
CERT="$CERT_DIR/fpvcopilot.crt"
KEY="$CERT_DIR/fpvcopilot.key"
NGINX_SITE="/etc/nginx/sites-available/fpvcopilot-sky"
NGINX_ENABLED="/etc/nginx/sites-enabled/fpvcopilot-sky"

[ "$(id -u)" -eq 0 ] || {
    echo "must run as root: sudo bash $0" >&2
    exit 1
}

install -d -m 755 "$CERT_DIR"

MODE="${1:-self-signed}"
HOSTNAME_FQDN="$(hostname -f 2> /dev/null || hostname)"
IP="$(hostname -I 2> /dev/null | awk '{print $1}')"

if [ "$MODE" = "--tailscale" ] || [ "$MODE" = "tailscale" ]; then
    echo "🔐 Requesting Tailscale certificate for $HOSTNAME_FQDN ..."
    (cd "$CERT_DIR" && tailscale cert "$HOSTNAME_FQDN")
    mv "$CERT_DIR/$HOSTNAME_FQDN.crt" "$CERT"
    mv "$CERT_DIR/$HOSTNAME_FQDN.key" "$KEY"
else
    echo "🔐 Generating self-signed certificate for CN=$HOSTNAME_FQDN ..."
    openssl req -x509 -newkey rsa:4096 -nodes -days 825 \
        -keyout "$KEY" -out "$CERT" \
        -subj "/CN=$HOSTNAME_FQDN" \
        -addext "subjectAltName=DNS:$HOSTNAME_FQDN,DNS:fpvcopilot.local${IP:+,IP:$IP}"
fi
chmod 600 "$KEY"
chmod 644 "$CERT"

echo "🔧 Installing TLS nginx configuration..."
cp "$PROJECT_DIR/systemd/fpvcopilot-sky.tls.nginx" "$NGINX_SITE"
ln -sf "$NGINX_SITE" "$NGINX_ENABLED"
if [ -L /etc/nginx/sites-enabled/default ]; then
    rm -f /etc/nginx/sites-enabled/default
fi

if nginx -t; then
    systemctl reload nginx
    echo "✅ HTTPS enabled."
    echo "   https://$HOSTNAME_FQDN  (or https://$IP)"
    if [ "$MODE" = "--tailscale" ] || [ "$MODE" = "tailscale" ]; then
        echo "   Certificate issued by Tailscale."
    else
        echo "   Self-signed certificate: the browser will show a warning."
    fi
else
    echo "❌ nginx -t failed; nginx was NOT reloaded. Restore the previous config or fix it." >&2
    exit 1
fi
