#!/bin/bash
# FPV Copilot Sky - Production Environment Setup
# This script installs nginx and sets up the production environment

set -e

echo "🔧 FPV Copilot Sky - Production Setup"
echo "======================================"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if running with sudo
if [ "$EUID" -ne 0 ]; then 
    echo -e "${YELLOW}⚠️  This script needs sudo privileges${NC}"
    echo "Please run: sudo bash $0"
    exit 1
fi

# Get the actual user (not root if using sudo)
ACTUAL_USER=${SUDO_USER:-$USER}

echo -e "\n${BLUE}📦 Installing nginx...${NC}"
apt-get update
apt-get install -y nginx

echo -e "${GREEN}✅ Nginx installed${NC}"

# Enable nginx to start on boot
systemctl enable nginx

# Important: Disable default nginx site to avoid conflicts
if [ -L /etc/nginx/sites-enabled/default ]; then
    echo -e "\n${BLUE}🔧 Disabling default nginx site...${NC}"
    rm /etc/nginx/sites-enabled/default
    echo -e "${GREEN}✅ Default site disabled${NC}"
fi

# Create log directory if it doesn't exist
mkdir -p /var/log/nginx
chown www-data:www-data /var/log/nginx

echo -e "\n${BLUE}🔧 Disabling serial getty on ttyAML0...${NC}"
# The serial-getty service conflicts with MAVLink communication:
# - Changes port group from dialout to tty
# - Removes read permissions from group
# - Consumes all serial data as console input
if systemctl is-active --quiet serial-getty@ttyAML0.service 2>/dev/null; then
    systemctl stop serial-getty@ttyAML0.service
fi
systemctl disable serial-getty@ttyAML0.service 2>/dev/null || true
systemctl mask serial-getty@ttyAML0.service 2>/dev/null || true
echo -e "${GREEN}✅ Serial getty disabled on ttyAML0${NC}"

# Ensure udev rules are applied for serial port permissions
if [ -f /etc/udev/rules.d/99-radxa-serial.rules ]; then
    udevadm trigger --action=change --subsystem-match=tty
    udevadm settle
    echo -e "${GREEN}✅ Udev rules applied${NC}"
fi

echo -e "\n${BLUE}🔧 Setting up project permissions...${NC}"

# Ensure frontend/client/dist directory exists and has correct permissions
mkdir -p /opt/FPVCopilotSky/frontend/client/dist
chown -R $ACTUAL_USER:$ACTUAL_USER /opt/FPVCopilotSky

echo -e "${GREEN}✅ Permissions configured${NC}"

echo -e "\n${GREEN}✅ Production environment setup complete!${NC}"
echo -e "\n📋 Next steps:"
echo -e "   1. Build and deploy: ${BLUE}bash /opt/FPVCopilotSky/scripts/deploy.sh${NC}"
echo -e "   2. Check service status: ${BLUE}sudo systemctl status fpvcopilot-sky${NC}"
echo -e "   3. View logs: ${BLUE}sudo journalctl -u fpvcopilot-sky -f${NC}"
echo -e "\n🌐 After deployment, access the app at: ${GREEN}http://$(hostname -I | awk '{print $1}')${NC}"
