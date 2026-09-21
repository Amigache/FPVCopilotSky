#!/bin/bash
# =============================================================================
# Harden /opt/FPVCopilotSky ownership (audit finding C5)
#
# Production model: the source tree is owned by root and the service user gets
# read/execute only, so a compromised backend cannot rewrite its own code.
# Updates run as root through fpvcopilot-update.service (which preserves the
# ownership model).
#
# Usage:
#   sudo bash scripts/harden-ownership.sh            # apply production model
#   sudo bash scripts/harden-ownership.sh --revert   # restore for development
# =============================================================================
set -euo pipefail

PROJECT_DIR="/opt/FPVCopilotSky"
SERVICE_USER="fpvcopilotsky"

[ "$(id -u)" -eq 0 ] || {
    echo "must run as root: sudo bash $0" >&2
    exit 1
}
[ -d "$PROJECT_DIR" ] || {
    echo "not found: $PROJECT_DIR" >&2
    exit 1
}

MODE="${1:-apply}"

case "$MODE" in
    --revert | revert)
        echo "Reverting ownership to $SERVICE_USER (development mode)..."
        chown -R "$SERVICE_USER:$SERVICE_USER" "$PROJECT_DIR"
        # Keep nginx able to read the served build.
        if [ -d "$PROJECT_DIR/frontend/client/dist" ]; then
            chmod -R a+rX "$PROJECT_DIR/frontend/client/dist"
        fi
        echo "✓ Source is writable by $SERVICE_USER again"
        ;;
    apply | --apply | "")
        echo "Hardening ownership: root:$SERVICE_USER (service read-only)..."
        chown -R root:"$SERVICE_USER" "$PROJECT_DIR"
        # World read + traverse so nginx (www-data) can serve frontend/client/dist;
        # never world/group writable.
        chmod -R a+rX "$PROJECT_DIR"
        chmod -R go-w "$PROJECT_DIR"
        echo "✓ Source is root-owned and read-only for $SERVICE_USER"
        echo "  Back to development mode: sudo bash scripts/harden-ownership.sh --revert"
        ;;
    *)
        echo "unknown option: $MODE" >&2
        echo "usage: sudo bash $0 [apply|--revert]" >&2
        exit 1
        ;;
esac
