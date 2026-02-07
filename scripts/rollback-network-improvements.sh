#!/bin/bash
# Network Improvements Rollback - EMERGENCY USE ONLY
# 
# This script restores the network service to a previous state.
# Use ONLY if network connectivity is completely broken after deployment.
#
# Quick alternatives (try these first):
#   systemctl restart fpvcopilot-sky           # Restart service
#   bash scripts/status.sh                      # Check what's wrong
#   git log --oneline app/services/network*.py # See recent changes

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_DIR="/opt/FPVCopilotSky"

echo -e "${BOLD}⚠️  NETWORK ROLLBACK - EMERGENCY RECOVERY${NC}\n"

if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Run with sudo${NC}"
    exit 1
fi

cd "$PROJECT_DIR"

# Check if git is available
if [ ! -d .git ]; then
    echo -e "${RED}❌ Git repository not found${NC}"
    echo ""
    echo "Without git, rollback is manual:"
    echo "  1. Find a backup in backups/ directory"
    echo "  2. cp backups/*/app/services/network_service.py app/services/"
    echo "  3. systemctl restart fpvcopilot-sky"
    exit 1
fi

echo -e "${YELLOW}📋 Git repository found. Checking modified files:${NC}"
git status --short app/services/ app/api/routes/network.py 2>/dev/null || echo "No changes detected"
echo ""

read -p "Restore network_service.py and network.py from git? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Cancelled"
    exit 0
fi

echo -e "${YELLOW}🔄 Rolling back...${NC}"
git checkout -- app/services/network_service.py 2>/dev/null || echo "No network_service.py changes"
git checkout -- app/api/routes/network.py 2>/dev/null || echo "No network.py changes"

echo -e "${YELLOW}⏹️  Restarting service...${NC}"
systemctl restart fpvcopilot-sky

sleep 2
if systemctl is-active --quiet fpvcopilot-sky; then
    echo -e "${GREEN}✅ Service restarted${NC}"
    echo ""
    echo "Verify connectivity:"
    echo "  curl http://localhost:8000/api/system/info"
    echo "  ip route show"
else
    echo -e "${RED}❌ Service failed. Check logs:${NC}"
    journalctl -u fpvcopilot-sky -n 30 -e
    exit 1
fi

