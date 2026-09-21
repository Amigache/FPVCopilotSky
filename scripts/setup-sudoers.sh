#!/bin/bash
# FPV Copilot Sky - Legacy sudoers decommission
#
# The application no longer uses sudo: every privileged operation goes through
# the fpvcopilot-privd helper (root daemon + command whitelist). This script
# removes the previous NOPASSWD entries and grants cap_net_raw to ping so the
# latency monitor can work without privileges.
#
# Run with: sudo bash scripts/setup-sudoers.sh
#
# To go back to the old model, use the harden-ownership/--revert helpers and an
# older release; there is intentionally no way to recreate broad NOPASSWD rules.

set -e

echo "🔐 FPV Copilot Sky - Removing legacy sudoers (privileged helper model)"

LEGACY_FILES=(
    /etc/sudoers.d/fpvcopilot-sky
    /etc/sudoers.d/fpvcopilot-system
    /etc/sudoers.d/fpvcopilot-wifi
    /etc/sudoers.d/fpvcopilot-tailscale
    /etc/sudoers.d/tailscale
)

for file in "${LEGACY_FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "  🗑️  Removing legacy sudoers file: $file"
        rm -f "$file"
    fi
done

# ping needs cap_net_raw to create ICMP raw sockets without privileges.
# (When it is missing, the latency monitor falls back to the helper.)
PING_BIN="$(command -v ping 2>/dev/null || echo /usr/bin/ping)"
if [ -x "$PING_BIN" ]; then
    if setcap cap_net_raw+ep "$PING_BIN" 2>/dev/null; then
        echo "  ✅ cap_net_raw granted to $PING_BIN"
    else
        echo "  ⚠️  setcap failed — ping will go through the privileged helper"
    fi
fi

echo "  ✅ No NOPASSWD entries remain; privileged operations use fpvcopilot-privd"
