#!/bin/bash
# Setup serial port permissions and disable getty conflicts
# This script must be run with: sudo bash setup-serial-ports.sh

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'
REBOOT_REQUIRED=0

echo -e "${BLUE}🔧 Configuring serial port permissions...${NC}"

is_radxa_zero3w() {
    if [ -f "/proc/device-tree/model" ]; then
        tr -d '\000' < /proc/device-tree/model 2>/dev/null | grep -qi "Radxa ZERO 3"
        return $?
    fi
    return 1
}

enable_uart4_m1_overlay() {
    local ARMBIAN_ENV="/boot/armbianEnv.txt"
    local OVERLAY_NAME="rk3568-uart4-m1"
    local LEGACY_OVERLAY="rk3568-uart2-m0"

    [ -f "$ARMBIAN_ENV" ] || return 0

    # Verify overlay exists in current kernel dtb set.
    if ! find /boot/dtb* -maxdepth 4 -type f -name "${OVERLAY_NAME}.dtbo" 2>/dev/null | grep -q .; then
        echo -e "${YELLOW}⚠ Overlay ${OVERLAY_NAME}.dtbo not found — skipping UART4_M1 auto-enable${NC}"
        return 0
    fi

    # Remove legacy UART2 overlay to avoid console/debug conflicts.
    if grep -Eq "^overlays=.*\b${LEGACY_OVERLAY}\b" "$ARMBIAN_ENV"; then
        cp "$ARMBIAN_ENV" "${ARMBIAN_ENV}.bak.fpvcopilot" 2>/dev/null || true
        sed -i "/^overlays=/ s/\b${LEGACY_OVERLAY}\b//g" "$ARMBIAN_ENV"
        sed -i '/^overlays=/ s/  */ /g; /^overlays=/ s/ $//; /^overlays= $/s//overlays=/' "$ARMBIAN_ENV"
        echo -e "${GREEN}✓ Removed legacy overlay ${LEGACY_OVERLAY} from armbianEnv.txt${NC}"
        REBOOT_REQUIRED=1
    fi

    if grep -Eq "^overlays=.*\b${OVERLAY_NAME}\b" "$ARMBIAN_ENV"; then
        echo -e "${GREEN}✓ UART4_M1 overlay already enabled in armbianEnv.txt${NC}"
        return 0
    fi

    cp "$ARMBIAN_ENV" "${ARMBIAN_ENV}.bak.fpvcopilot" 2>/dev/null || true

    if grep -q '^overlays=' "$ARMBIAN_ENV"; then
        sed -i "/^overlays=/ s/$/ ${OVERLAY_NAME}/" "$ARMBIAN_ENV"
    else
        echo "overlays=${OVERLAY_NAME}" >> "$ARMBIAN_ENV"
    fi

    echo -e "${GREEN}✓ Enabled ${OVERLAY_NAME} overlay in armbianEnv.txt${NC}"
    REBOOT_REQUIRED=1
}

set_default_serial_preferences() {
    local PREFS_FILE="/var/lib/fpvcopilot-sky/preferences.json"

    # Preferences may not exist yet on early install stages.
    [ -f "$PREFS_FILE" ] || return 0

    local chosen
    chosen=$(python3 - "$PREFS_FILE" <<'PY'
import json
import os
import sys

path = sys.argv[1]
try:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
except Exception:
    print("")
    raise SystemExit(0)

serial_cfg = data.setdefault("serial", {})
if serial_cfg.get("port"):
    print("")
    raise SystemExit(0)

candidates = ["/dev/ttyS4", "/dev/ttyS0", "/dev/ttyAML0", "/dev/ttyS1"]
selected = ""

kernel_console_ports = set()
try:
    with open("/proc/cmdline", "r", encoding="utf-8") as f:
        for token in f.read().strip().split():
            if token.startswith("console="):
                dev = token.split("=", 1)[1].split(",", 1)[0]
                if dev.startswith("tty"):
                    kernel_console_ports.add(f"/dev/{dev}")
except Exception:
    pass

for dev in candidates:
    if dev in kernel_console_ports:
        continue
    if os.path.exists(dev):
        selected = dev
        break

if selected:
    serial_cfg["port"] = selected
    serial_cfg["baudrate"] = int(serial_cfg.get("baudrate", 115200) or 115200)
    serial_cfg["auto_connect"] = bool(serial_cfg.get("auto_connect", False))
    serial_cfg["last_successful"] = bool(serial_cfg.get("last_successful", False))

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

print(selected)
PY
)

    if [ -n "$chosen" ]; then
        echo -e "${GREEN}✓ Serial default configured in preferences: ${chosen}${NC}"
    fi
}

# Create udev rule for serial ports
UDEV_RULE="/etc/udev/rules.d/99-radxa-serial.rules"
cat > "$UDEV_RULE" <<'UDEV_EOF'
KERNEL=="ttyAML*", MODE="0660", GROUP="dialout"
KERNEL=="ttyS*", MODE="0660", GROUP="dialout"
KERNEL=="ttyAMA*", MODE="0660", GROUP="dialout"
KERNEL=="ttyUSB*", MODE="0660", GROUP="dialout"
KERNEL=="ttyACM*", MODE="0660", GROUP="dialout"
UDEV_EOF
echo -e "${GREEN}✓ Udev rules for serial ports updated${NC}"

# Disable serial-getty on ttyAML0 to prevent conflicts with MAVLink
# The serial-getty service conflicts with MAVLink communication:
# - Changes port group from dialout to tty
# - Removes read permissions from group
# - Consumes all serial data as console input
for GETTY_PORT in ttyAML0 ttyS4; do
    echo -e "${BLUE}🔧 Disabling serial getty on ${GETTY_PORT}...${NC}"
    if systemctl is-active --quiet "serial-getty@${GETTY_PORT}.service" 2>/dev/null; then
        systemctl stop "serial-getty@${GETTY_PORT}.service"
        echo -e "${GREEN}✓ Serial getty stopped on ${GETTY_PORT}${NC}"
    fi
    systemctl disable "serial-getty@${GETTY_PORT}.service" 2>/dev/null || true
    systemctl mask "serial-getty@${GETTY_PORT}.service" 2>/dev/null || true
    echo -e "${GREEN}✓ Serial getty disabled and masked on ${GETTY_PORT}${NC}"
done

# Trigger udev to apply serial port rules
udevadm trigger --action=change --subsystem-match=tty 2>/dev/null || true
udevadm settle 2>/dev/null || true
echo -e "${GREEN}✓ Udev rules applied${NC}"

# Set permissions for serial ports if they exist
if ls /dev/ttyAML* > /dev/null 2>&1; then
    chmod 666 /dev/ttyAML* || true
    echo -e "${GREEN}✓ Permissions set for /dev/ttyAML*${NC}"
fi
if ls /dev/ttyS* > /dev/null 2>&1; then
    chmod 666 /dev/ttyS* || true
    echo -e "${GREEN}✓ Permissions set for /dev/ttyS*${NC}"
fi
if ls /dev/ttyUSB* > /dev/null 2>&1; then
    chmod 666 /dev/ttyUSB* || true
    echo -e "${GREEN}✓ Permissions set for /dev/ttyUSB*${NC}"
fi
if ls /dev/ttyACM* > /dev/null 2>&1; then
    chmod 666 /dev/ttyACM* || true
    echo -e "${GREEN}✓ Permissions set for /dev/ttyACM*${NC}"
fi

if is_radxa_zero3w; then
    echo -e "${BLUE}🎯 Radxa Zero 3W detected — applying default serial preferences...${NC}"
    echo -e "${BLUE}🔧 Enabling UART4_M1 overlay (Armbian)...${NC}"
    enable_uart4_m1_overlay
    set_default_serial_preferences
fi

echo -e "${GREEN}✅ Serial port configuration complete${NC}"
if [ "$REBOOT_REQUIRED" -eq 1 ]; then
    echo -e "${YELLOW}⚠ Reboot required to apply UART overlay changes${NC}"
fi
