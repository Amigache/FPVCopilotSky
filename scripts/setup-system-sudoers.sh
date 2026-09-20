#!/bin/bash
# FPV Copilot Sky - DEPRECATED sudoers setup (compatibility shim)
#
# This script used to write /etc/sudoers.d/fpvcopilot-system with dangerous
# NOPASSWD wildcards that allowed trivial root escalation, e.g.:
#   - /usr/bin/tee *      → write any file as root (/etc/sudoers.d/*, SSH keys)
#   - /usr/sbin/sysctl -w *
#   - /usr/bin/mkdir -p *
#   - /usr/sbin/ethtool -s *
#
# It now delegates to the hardened, unified scripts/setup-sudoers.sh, which
# removes these legacy files and installs a single least-privilege policy at
# /etc/sudoers.d/fpvcopilot-sky.
#
# Run with: sudo bash scripts/setup-system-sudoers.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "⚠️  setup-system-sudoers.sh is deprecated."
echo "    Delegating to the hardened scripts/setup-sudoers.sh ..."
echo ""

exec bash "$SCRIPT_DIR/setup-sudoers.sh"
