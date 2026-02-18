#!/bin/bash
# Setup serial port permissions and disable getty conflicts
# This script must be run with: sudo bash setup-serial-ports.sh

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}🔧 Configuring serial port permissions...${NC}"

# Create udev rule for serial ports
UDEV_RULE="/etc/udev/rules.d/99-radxa-serial.rules"
if [ ! -f "$UDEV_RULE" ]; then
    echo 'KERNEL=="ttyAML*", MODE="0660", GROUP="dialout"' > "$UDEV_RULE"
    echo -e "${GREEN}✓ Udev rules for serial ports created${NC}"
else
    echo -e "${GREEN}✓ Udev rules already exist${NC}"
fi

# Disable serial-getty on ttyAML0 to prevent conflicts with MAVLink
# The serial-getty service conflicts with MAVLink communication:
# - Changes port group from dialout to tty
# - Removes read permissions from group
# - Consumes all serial data as console input
echo -e "${BLUE}🔧 Disabling serial getty on ttyAML0...${NC}"
if systemctl is-active --quiet serial-getty@ttyAML0.service 2>/dev/null; then
    systemctl stop serial-getty@ttyAML0.service
    echo -e "${GREEN}✓ Serial getty stopped${NC}"
fi
systemctl disable serial-getty@ttyAML0.service 2>/dev/null || true
systemctl mask serial-getty@ttyAML0.service 2>/dev/null || true
echo -e "${GREEN}✓ Serial getty disabled and masked on ttyAML0${NC}"

# Trigger udev to apply serial port rules
udevadm trigger --action=change --subsystem-match=tty 2>/dev/null || true
udevadm settle 2>/dev/null || true
echo -e "${GREEN}✓ Udev rules applied${NC}"

# Set permissions for serial ports if they exist
if ls /dev/ttyAML* > /dev/null 2>&1; then
    chmod 666 /dev/ttyAML* || true
    echo -e "${GREEN}✓ Permissions set for /dev/ttyAML*${NC}"
fi
if ls /dev/ttyUSB* > /dev/null 2>&1; then
    chmod 666 /dev/ttyUSB* || true
    echo -e "${GREEN}✓ Permissions set for /dev/ttyUSB*${NC}"
fi

echo -e "${GREEN}✅ Serial port configuration complete${NC}"
