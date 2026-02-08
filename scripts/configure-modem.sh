#!/bin/bash
# FPV Copilot Sky - USB Modem Configuration Script
# Detects and configures USB modems to switch from storage mode to modem mode

set -e

echo "📱 FPV Copilot Sky - USB Modem Configuration"
echo "============================================"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Check if usb_modeswitch is available
if ! command -v usb_modeswitch &> /dev/null; then
    echo -e "${RED}❌${NC} usb_modeswitch not found. Please install it first:"
    echo "   sudo apt install -y usb-modeswitch usb-modeswitch-data"
    exit 1
fi

echo -e "${BLUE}🔍${NC} Checking for USB modems..."

# Function to configure Huawei modems
configure_huawei_modem() {
    echo -e "${YELLOW}🔄${NC} Huawei modem found in mass storage mode, switching to modem mode..."

    if sudo usb_modeswitch -v 12d1 -p 1f01 -M "55534243123456780000000000000a11062000000000000100000000000000" 2>/dev/null; then
        echo -e "${GREEN}✅${NC} Mode switch command executed successfully"

        echo "   Waiting 5 seconds for modem to switch modes..."
        sleep 5

        if lsusb | grep -q "12d1:14dc.*HiLink Modem"; then
            echo -e "${GREEN}✅${NC} Huawei modem successfully switched to HiLink modem mode"
        elif lsusb | grep -q "12d1:"; then
            HUAWEI_MODEL=$(lsusb | grep "12d1:" | cut -d' ' -f7- | head -1)
            echo -e "${GREEN}✅${NC} Huawei modem detected: $HUAWEI_MODEL"
        else
            echo -e "${YELLOW}⚠️${NC}  Modem mode switch may have failed - modem not detected"
            return 1
        fi
    else
        echo -e "${RED}❌${NC} Failed to execute mode switch command"
        return 1
    fi
}

# Check current USB devices
echo -e "${BLUE}📱${NC} Current USB modems:"
if lsusb | grep -q "12d1:1f01.*Mass storage"; then
    echo "   🔴 Huawei modem in mass storage mode (ID: 12d1:1f01)"
    configure_huawei_modem
elif lsusb | grep -q "12d1:14dc.*HiLink Modem"; then
    echo -e "   ${GREEN}✅${NC} Huawei HiLink modem already in correct mode"
elif lsusb | grep -q "12d1:"; then
    HUAWEI_MODEL=$(lsusb | grep "12d1:" | cut -d' ' -f7- | head -1)
    echo -e "   ${GREEN}✅${NC} Huawei modem detected: $HUAWEI_MODEL"
else
    echo -e "   ${BLUE}ℹ️${NC}  No Huawei USB modems detected"
fi

# Check with ModemManager
echo -e "\n${BLUE}🔍${NC} Checking ModemManager detection..."
if command -v mmcli &> /dev/null; then
    sleep 2  # Wait for ModemManager to detect

    MMCLI_OUTPUT=$(mmcli -L 2>/dev/null || echo "")
    if echo "$MMCLI_OUTPUT" | grep -q "^/org/freedesktop/ModemManager1/Modem/"; then
        MODEM_COUNT=$(echo "$MMCLI_OUTPUT" | grep -c "^/org/freedesktop/ModemManager1/Modem/" || echo "0")
        echo -e "${GREEN}✅${NC} ModemManager detected $MODEM_COUNT traditional modem(s):"
        echo "$MMCLI_OUTPUT" | grep "^/org/freedesktop/ModemManager1/Modem/" | while read -r line; do
            echo "   $line"
        done
    else
        echo -e "${BLUE}ℹ️${NC}  No traditional modems detected by ModemManager"
        if lsusb | grep -q "12d1:14dc.*HiLink"; then
            echo -e "${BLUE}ℹ️${NC}  Note: HiLink modems (like E3372) work as network interfaces, not traditional modems"
            echo "   This is NORMAL behavior - your modem is working correctly!"

            # Check HiLink network status
            if ip addr show | grep -A5 "enx" | grep -q "192\.168\.8\."; then
                HILINK_IP=$(ip addr show | grep "inet.*192\.168\.8\." | awk '{print $2}' | head -1)
                echo -e "${GREEN}✅${NC} HiLink network interface active: $HILINK_IP"

                if ping -c 1 -W 2 192.168.8.1 &>/dev/null; then
                    echo -e "${GREEN}✅${NC} HiLink gateway 192.168.8.1 responding - modem is fully functional!"
                else
                    echo -e "${YELLOW}⚠️${NC}  HiLink gateway not responding"
                fi
            else
                echo -e "${YELLOW}⚠️${NC}  HiLink network interface not found"
            fi
        else
            echo "   This could mean:"
            echo "   - No modem is connected"
            echo "   - Modem is still switching modes (wait a moment and try again)"
            echo "   - ModemManager service is not running"
        fi
    fi
else
    echo -e "${RED}❌${NC} mmcli (ModemManager) not found"
fi

echo -e "\n${BLUE}💡${NC} Tips:"
echo "   - If modem is not detected, try unplugging and reconnecting it"
echo "   - Some modems may take up to 30 seconds to be recognized"
echo "   - Check system logs with: sudo journalctl -u ModemManager -f"
echo "   - Run: bash scripts/status.sh to see overall system status"

echo -e "\n${GREEN}✅${NC} Modem configuration check complete!"
