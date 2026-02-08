#!/bin/bash
# Quick Status Check - FPV Copilot Sky
# Verifica el estado de todos los componentes

echo "🔍 FPV Copilot Sky - Status Check"
echo "=================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

check_service() {
    local service=$1
    if systemctl is-active --quiet $service; then
        echo -e "${GREEN}✅${NC} $service is running"
        return 0
    else
        echo -e "${RED}❌${NC} $service is NOT running"
        return 1
    fi
}

check_port() {
    local port=$1
    local name=$2
    # Use ss (doesn't require sudo) instead of lsof
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
        echo -e "${GREEN}✅${NC} Port $port ($name) is listening"
        return 0
    else
        echo -e "${RED}❌${NC} Port $port ($name) is NOT listening"
        return 1
    fi
}

echo -e "\n${BLUE}📋 System Services${NC}"
check_service fpvcopilot-sky
BACKEND_RUNNING=$?
check_service nginx
NGINX_RUNNING=$?

echo -e "\n${BLUE}🌐 Network Services${NC}"
check_service NetworkManager
check_service ModemManager

echo -e "\n${BLUE}🔌 Network Ports${NC}"
check_port 80 "Nginx"
check_port 8000 "Backend API"

echo -e "\n${BLUE}📁 Files & Directories${NC}"
if [ -d "/opt/FPVCopilotSky/frontend/client/dist" ] && [ "$(ls -A /opt/FPVCopilotSky/frontend/client/dist 2>/dev/null)" ]; then
    echo -e "${GREEN}✅${NC} Frontend build exists"
else
    echo -e "${YELLOW}⚠️${NC}  Frontend build NOT found (run: npm run build)"
fi

if [ -f "/opt/FPVCopilotSky/venv/bin/python3" ]; then
    echo -e "${GREEN}✅${NC} Python virtual environment exists"
else
    echo -e "${RED}❌${NC} Python virtual environment NOT found"
fi

echo -e "\n${BLUE}🔧 Network Tools${NC}"
if command -v nmcli &> /dev/null; then
    if nmcli general status &> /dev/null; then
        echo -e "${GREEN}✅${NC} nmcli (NetworkManager CLI) working"
    else
        echo -e "${YELLOW}⚠️${NC}  nmcli available but not responding"
    fi
else
    echo -e "${RED}❌${NC} nmcli NOT found"
fi

if command -v mmcli &> /dev/null; then
    if mmcli -L &> /dev/null; then
        echo -e "${GREEN}✅${NC} mmcli (ModemManager CLI) working"
    else
        echo -e "${YELLOW}⚠️${NC}  mmcli available but not responding"
    fi
else
    echo -e "${RED}❌${NC} mmcli NOT found"
fi

if command -v hostapd &> /dev/null; then
    echo -e "${GREEN}✅${NC} hostapd (WiFi hotspot) available"
else
    echo -e "${RED}❌${NC} hostapd NOT found"
fi

if command -v iwconfig &> /dev/null; then
    echo -e "${GREEN}✅${NC} iwconfig (wireless tools) available"
else
    echo -e "${RED}❌${NC} iwconfig NOT found"
fi
if command -v usb_modeswitch &> /dev/null; then
    echo -e "${GREEN}✓${NC} usb_modeswitch (USB modem mode switching) available"
else
    echo -e "${RED}❌${NC} usb_modeswitch NOT found"
fi

echo -e "\n${BLUE}� Sudo Permissions${NC}"
# Check Tailscale sudo permissions
if [ -f "/etc/sudoers.d/tailscale" ]; then
    echo -e "${GREEN}✓${NC} Tailscale sudoers file exists"

    # Check if sudoers file contains correct user
    if sudo grep -q "^$USER ALL=" /etc/sudoers.d/tailscale 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Sudoers configured for user: $USER"

        # Test if tailscale commands work without password
        # We capture both stdout and stderr to check if command runs without password prompt
        TAILSCALE_TEST=$(sudo -n tailscale status 2>&1)
        TAILSCALE_EXIT=$?
        if [[ $TAILSCALE_EXIT -eq 0 ]] || [[ "$TAILSCALE_TEST" =~ "Logged out" ]]; then
            echo -e "${GREEN}✓${NC} Tailscale commands work without password"
        else
            echo -e "${YELLOW}⚠️${NC}  Tailscale commands may require password"
            echo -e "    ${BLUE}ℹ️${NC}  Test output: $(echo "$TAILSCALE_TEST" | head -1)"
        fi
    else
        echo -e "${YELLOW}⚠️${NC}  Sudoers not configured for current user ($USER)"
        # Check what user is configured
        SUDO_USER=$(sudo grep "ALL=" /etc/sudoers.d/tailscale 2>/dev/null | head -1 | cut -d' ' -f1)
        if [ ! -z "$SUDO_USER" ]; then
            echo -e "    ${BLUE}ℹ️${NC}  Configured for: $SUDO_USER"
        fi
    fi
else
    echo -e "${RED}❌${NC} Tailscale sudoers file missing"
    echo -e "    ${BLUE}ℹ️${NC}  VPN functionality may require password prompts"
fi

# Check system management sudo permissions
if [ -f "/etc/sudoers.d/fpvcopilot-system" ]; then
    echo -e "${GREEN}✓${NC} System management sudoers file exists"

    # Test if systemctl commands work without password
    SYSTEMCTL_TEST=$(sudo -n systemctl status fpvcopilot-sky 2>&1)
    SYSTEMCTL_EXIT=$?
    if [[ $SYSTEMCTL_EXIT -eq 0 ]] || [[ "$SYSTEMCTL_TEST" =~ "Active:" ]]; then
        echo -e "${GREEN}✓${NC} systemctl commands work without password"
    else
        echo -e "${YELLOW}⚠️${NC}  systemctl commands may require password"
    fi

    # Test if journalctl commands work without password
    JOURNALCTL_TEST=$(sudo -n journalctl -u fpvcopilot-sky -n 1 2>&1)
    JOURNALCTL_EXIT=$?
    if [[ $JOURNALCTL_EXIT -eq 0 ]]; then
        echo -e "${GREEN}✓${NC} journalctl commands work without password"
    else
        echo -e "${YELLOW}⚠️${NC}  journalctl commands may require password"
    fi
else
    echo -e "${RED}❌${NC} System management sudoers file missing"
    echo -e "    ${BLUE}ℹ️${NC}  System restart/logs functionality may require password prompts"
    echo -e "    ${BLUE}ℹ️${NC}  Run: sudo bash scripts/setup-system-sudoers.sh"
fi

# Check general sudo access
if sudo -n true 2>/dev/null; then
    echo -e "${GREEN}✓${NC} User has passwordless sudo access"
else
    echo -e "${BLUE}ℹ️${NC}  User requires password for sudo commands"
fi

echo -e "\n${BLUE}�📱 USB Modem Status${NC}"
# Check for Huawei modems
if lsusb | grep -q "12d1:1f01.*Mass storage"; then
    echo -e "${YELLOW}⚠️${NC}  Huawei modem in mass storage mode (needs switching)"
elif lsusb | grep -q "12d1:14dc.*HiLink Modem"; then
    echo -e "${GREEN}✓${NC} Huawei E3372 HiLink modem detected and ready"
    # Check if HiLink interface is active
    if ip addr show | grep -A5 "enx" | grep -q "192\.168\.8\."; then
        HILINK_IP=$(ip addr show | grep "inet.*192\.168\.8\." | awk '{print $2}' | head -1)
        echo -e "${GREEN}✓${NC} HiLink network interface active: $HILINK_IP"
        # Test gateway connectivity
        if ping -c 1 -W 2 192.168.8.1 &>/dev/null; then
            echo -e "${GREEN}✓${NC} HiLink gateway 192.168.8.1 responding"
        else
            echo -e "${YELLOW}⚠️${NC}  HiLink gateway not responding"
        fi
    else
        echo -e "${YELLOW}⚠️${NC}  HiLink interface not active"
    fi
elif lsusb | grep -q "12d1:"; then
    HUAWEI_MODEL=$(lsusb | grep "12d1:" | cut -d' ' -f7- | head -1)
    echo -e "${GREEN}✓${NC} Huawei modem detected: $HUAWEI_MODEL"
else
    echo -e "${BLUE}ℹ️${NC}  No Huawei USB modem detected"
fi

# Check ModemManager detection (only for traditional modems)
if command -v mmcli &> /dev/null; then
    MMCLI_OUTPUT=$(mmcli -L 2>/dev/null || echo "")
    if echo "$MMCLI_OUTPUT" | grep -q "^/org/freedesktop/ModemManager1/Modem/"; then
        MODEM_COUNT=$(echo "$MMCLI_OUTPUT" | grep -c "^/org/freedesktop/ModemManager1/Modem/" || echo "0")
        echo -e "${GREEN}✅${NC} ModemManager detected $MODEM_COUNT traditional modem(s)"
        # Show basic modem info
        echo "$MMCLI_OUTPUT" | grep "^/org/freedesktop/ModemManager1/Modem/" | head -3 | while read -r line; do
            echo "    $line"
        done
    else
        echo -e "${BLUE}ℹ️${NC}  No traditional modems detected by ModemManager"
        if lsusb | grep -q "12d1:14dc.*HiLink"; then
            echo -e "    ${BLUE}ℹ️${NC}  (This is normal - HiLink modems work as network interfaces)"
        fi
    fi
fi
echo -e "\n${BLUE}🌐 Network Priority & Routing${NC}"
# Show default routes with metrics
ROUTES=$(ip route show default 2>/dev/null)
if [ -n "$ROUTES" ]; then
    # Parse primary route (lowest metric)
    PRIMARY_IFACE=$(echo "$ROUTES" | sort -t' ' -k9 -n | head -1 | grep -oP 'dev \K\S+')
    PRIMARY_METRIC=$(echo "$ROUTES" | sort -t' ' -k9 -n | head -1 | grep -oP 'metric \K\d+')
    PRIMARY_GW=$(echo "$ROUTES" | sort -t' ' -k9 -n | head -1 | grep -oP 'via \K\S+')

    # Detect modem interface
    MODEM_IFACE=$(ip -o addr show 2>/dev/null | grep "192\.168\.8\." | awk '{print $2}' | head -1)

    # Check if primary is 4G modem
    if [ -n "$MODEM_IFACE" ] && [ "$PRIMARY_IFACE" = "$MODEM_IFACE" ]; then
        echo -e "${GREEN}✅${NC} Primary: 4G modem ($PRIMARY_IFACE) metric $PRIMARY_METRIC via $PRIMARY_GW"
    elif [ -n "$PRIMARY_IFACE" ]; then
        echo -e "${YELLOW}⚠️${NC}  Primary: $PRIMARY_IFACE metric $PRIMARY_METRIC via $PRIMARY_GW"
        if [ -n "$MODEM_IFACE" ]; then
            echo -e "    ${BLUE}ℹ️${NC}  4G modem detected ($MODEM_IFACE) but not primary"
        fi
    fi

    # Show all routes
    ROUTE_COUNT=$(echo "$ROUTES" | wc -l)
    if [ "$ROUTE_COUNT" -gt 1 ]; then
        BACKUP_LINES=$(echo "$ROUTES" | sort -t' ' -k9 -n | tail -n +2)
        while IFS= read -r line; do
            B_IFACE=$(echo "$line" | grep -oP 'dev \K\S+')
            B_METRIC=$(echo "$line" | grep -oP 'metric \K\d+')
            B_GW=$(echo "$line" | grep -oP 'via \K\S+')
            echo -e "${GREEN}✓${NC} Backup: $B_IFACE metric $B_METRIC via $B_GW"
        done <<< "$BACKUP_LINES"
    else
        echo -e "${YELLOW}⚠️${NC}  Only one default route (no failover)"
    fi
else
    echo -e "${RED}❌${NC} No default routes configured"
fi

# VPN-aware routing check
if ip link show 2>/dev/null | grep -q "tailscale.*UP"; then
    TS_IP=$(ip -o addr show tailscale0 2>/dev/null | grep -oP 'inet \K[\d.]+')
    echo -e "${GREEN}✅${NC} VPN active: tailscale0 ($TS_IP) - smooth transitions enabled"
else
    echo -e "${BLUE}ℹ️${NC}  VPN not active - standard route transitions"
fi

# Check route permissions
if sudo -n ip route show default &>/dev/null; then
    echo -e "${GREEN}✓${NC} Route management permissions OK"
else
    echo -e "${YELLOW}⚠️${NC}  Route management may require password"
    echo -e "    ${BLUE}ℹ️${NC}  Run: sudo bash scripts/setup-system-sudoers.sh"
fi

echo -e "\n${BLUE}🌐 Connectivity${NC}"
# Test backend port using /dev/tcp (built into bash)
if timeout 1 bash -c "echo >/dev/tcp/127.0.0.1/8000" 2>/dev/null; then
    echo -e "${GREEN}✅${NC} Backend API port is open"
elif ss -tuln | grep -q ":8000 "; then
    echo -e "${YELLOW}⚠️${NC}  Backend API port open but not responding"
else
    echo -e "${RED}❌${NC} Backend API port failed"
fi

if [ $NGINX_RUNNING -eq 0 ]; then
    # Test nginx port using /dev/tcp
    if timeout 1 bash -c "echo >/dev/tcp/127.0.0.1/80" 2>/dev/null; then
        echo -e "${GREEN}✅${NC} Nginx frontend port is accessible"
    elif ss -tuln | grep -q ":80 "; then
        echo -e "${YELLOW}⚠️${NC}  Nginx frontend port open but not responding"
    else
        echo -e "${RED}❌${NC} Nginx frontend port failed"
    fi
fi

echo -e "\n${BLUE}💾 Logs Location${NC}"
echo "   Backend: sudo journalctl -u fpvcopilot-sky -f"
echo "   Nginx:   sudo tail -f /var/log/nginx/fpvcopilot-sky-*.log"

echo -e "\n${BLUE}📊 Quick Stats${NC}"
if [ $BACKEND_RUNNING -eq 0 ]; then
    PID=$(systemctl show -p MainPID --value fpvcopilot-sky)
    if [ "$PID" != "0" ]; then
        MEM=$(ps -p $PID -o rss= | awk '{print int($1/1024)"MB"}')
        CPU=$(ps -p $PID -o %cpu= | awk '{print $1"%"}')
        echo "   Backend PID: $PID"
        echo "   Memory: $MEM"
        echo "   CPU: $CPU"
    fi
fi

echo -e "\n${BLUE}🌍 Access URLs${NC}"
IP=$(hostname -I | awk '{print $1}')
echo "   Local:      http://localhost"
echo "   Network:    http://$IP"
echo "   Backend:    http://$IP:8000"
echo "   API Docs:   http://$IP:8000/docs"

echo -e "\n${BLUE}⚡ Quick Actions${NC}"
echo "   Start:   sudo systemctl start fpvcopilot-sky"
echo "   Stop:    sudo systemctl stop fpvcopilot-sky"
echo "   Restart: sudo systemctl restart fpvcopilot-sky"
echo "   Logs:    sudo journalctl -u fpvcopilot-sky -f"
echo "   Deploy:  bash scripts/deploy.sh"

if [ $BACKEND_RUNNING -eq 0 ] && [ $NGINX_RUNNING -eq 0 ]; then
    echo -e "\n${GREEN}✅ System is operational!${NC}"
else
    echo -e "\n${YELLOW}⚠️  Some components are not running${NC}"
    echo "   Run: bash scripts/deploy.sh"
fi
