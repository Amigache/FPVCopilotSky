#!/bin/bash
# =============================================================================
# FPV Copilot Sky - Privileged updater (runs as root via systemd)
#
# Invoked by fpvcopilot-update.service. The request is passed through
# /var/lib/fpvcopilot-sky/update-request.env:
#     FPV_UPDATE_ACTION=update|rollback
#     FPV_UPDATE_TARGET=<semver>          (e.g. 1.2.3, leading 'v' allowed)
#
# Running the update as root lets /opt/FPVCopilotSky be read-only for the
# service user (audit finding C5). The target is validated before use and the
# existing ownership model is preserved after the update.
# =============================================================================
set -euo pipefail

PROJECT_DIR="/opt/FPVCopilotSky"
DATA_DIR="/var/lib/fpvcopilot-sky"
VERSION_FILE="$DATA_DIR/version"
PREVIOUS_VERSION_FILE="$DATA_DIR/previous_version"
SERVICE_USER="fpvcopilotsky"

ACTION="${FPV_UPDATE_ACTION:-}"
TARGET="${FPV_UPDATE_TARGET:-}"
TARGET="${TARGET#v}"

log() { echo "[privileged-update] $*"; }
die() {
    echo "[privileged-update] ERROR: $*" >&2
    exit 1
}

[ "$(id -u)" -eq 0 ] || die "must run as root"

case "$ACTION" in
    update | rollback) ;;
    *) die "invalid action '$ACTION'" ;;
esac

if ! [[ "$TARGET" =~ ^[0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9.-]+)?$ ]]; then
    die "invalid target version '$TARGET'"
fi

[ -d "$PROJECT_DIR/.git" ] || die "not a git repository: $PROJECT_DIR"

cd "$PROJECT_DIR"
GIT="git -c safe.directory=$PROJECT_DIR"
TAG="v$TARGET"

# Remember the ownership model of this install (root-owned in hardened
# deployments, service/dev-owned otherwise) and restore it afterwards.
PROJECT_OWNER="$(stat -c '%U:%G' "$PROJECT_DIR" 2>/dev/null || echo "$SERVICE_USER:$SERVICE_USER")"

CURRENT_VERSION=""
if [ -f "$VERSION_FILE" ]; then
    CURRENT_VERSION="$(cat "$VERSION_FILE" 2>/dev/null || true)"
fi

log "action=$ACTION tag=$TAG current=$CURRENT_VERSION"

$GIT reset --hard
$GIT fetch origin --tags

if ! $GIT rev-parse -q --verify "refs/tags/$TAG" > /dev/null; then
    die "tag $TAG not found in repository"
fi

if [ "$ACTION" = "update" ] && [ -n "$CURRENT_VERSION" ]; then
    echo "$CURRENT_VERSION" > "$PREVIOUS_VERSION_FILE"
fi

$GIT checkout --force "$TAG"
echo "$TARGET" > "$VERSION_FILE"

# Python dependencies
VENV_PY="$PROJECT_DIR/venv/bin/python3"
if [ -x "$VENV_PY" ]; then
    REQ_FILE="$PROJECT_DIR/requirements.lock"
    [ -f "$REQ_FILE" ] || REQ_FILE="$PROJECT_DIR/requirements.txt"
    log "installing python dependencies ($(basename "$REQ_FILE"))"
    "$VENV_PY" -m pip install -r "$REQ_FILE"
fi

# Frontend build
if [ -d "$PROJECT_DIR/frontend/client" ]; then
    log "building frontend"
    (cd "$PROJECT_DIR/frontend/client" && npm install && npm run build)
fi

# Preserve the ownership model of the install so both hardened (root-owned) and
# development (service-owned) setups keep working.
log "restoring ownership ($PROJECT_OWNER)"
chown -R "$PROJECT_OWNER" "$PROJECT_DIR" 2> /dev/null || true

log "restarting fpvcopilot-sky"
systemctl restart fpvcopilot-sky
log "done"
