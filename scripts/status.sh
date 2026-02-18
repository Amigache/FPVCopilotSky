#!/bin/bash
# Quick Status Check - FPV Copilot Sky
# Verifica el estado de todos los componentes
#
# Checks performed:
# =================
# - System Services: fpvcopilot-sky, nginx, NetworkManager, ModemManager
# - Network Ports: 80 (nginx), 8000 (backend API)
# - Video: Cameras, GStreamer installation, video streaming status
# - Network Configuration:
#   * wlan0 interface state (managed/unmanaged)
#   * WiFi scanning capability
#   * NetworkManager configuration (managed interfaces)
#   * Netplan WiFi renderer (NetworkManager vs networkd)
# - Sudo Permissions:
#   * Tailscale VPN management (no-password)
#   * WiFi management (scan, connect, disconnect)
#   * System management (service control, journalctl access)
# - Files & Directories: Frontend build, Python venv
# - Network Tools: nmcli, mmcli, hostapd, iwconfig, usb_modeswitch

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

echo -e "\n${BLUE}⚡ CPU & Performance${NC}"
# CPU governor check
GOV_FILE="/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
if [ -f "$GOV_FILE" ]; then
    GOV=$(cat "$GOV_FILE")
    NUM_CORES=$(ls -d /sys/devices/system/cpu/cpu[0-9]*/cpufreq 2>/dev/null | wc -l)
    ALL_PERF=true
    for g in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
        if [ "$(cat "$g" 2>/dev/null)" != "performance" ]; then
            ALL_PERF=false
            break
        fi
    done
    if $ALL_PERF; then
        echo -e "${GREEN}✅${NC} CPU governor: performance (all $NUM_CORES cores)"
    else
        if [ $BACKEND_RUNNING -eq 0 ]; then
            echo -e "${RED}❌${NC} CPU governor: $GOV (should be 'performance' while streaming)"
            echo -e "    ${BLUE}ℹ️${NC}  Systemd ExecStartPre should set this automatically"
            echo -e "    ${BLUE}ℹ️${NC}  Check: grep ExecStartPre /etc/systemd/system/fpvcopilot-sky.service"
        else
            echo -e "${GREEN}✓${NC} CPU governor: $GOV (service not running — normal)"
        fi
    fi
else
    echo -e "${YELLOW}⚠️${NC}  CPU governor: cpufreq not available"
fi

# CPU frequency
if [ -f "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq" ]; then
    FREQ=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq)
    FREQ_MHZ=$((FREQ / 1000))
    MAX_FREQ=$(cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq 2>/dev/null)
    MAX_MHZ=$((MAX_FREQ / 1000))
    if [ "$FREQ" -ge "$((MAX_FREQ - 10000))" ] 2>/dev/null; then
        echo -e "${GREEN}✓${NC} CPU frequency: ${FREQ_MHZ} MHz / ${MAX_MHZ} MHz (max)"
    else
        echo -e "${YELLOW}⚠️${NC}  CPU frequency: ${FREQ_MHZ} MHz / ${MAX_MHZ} MHz (not at max)"
    fi
fi

# Systemd service configuration checks
SYSTEMD_FILE="/etc/systemd/system/fpvcopilot-sky.service"
if [ -f "$SYSTEMD_FILE" ]; then
    # CPUQuota should NOT be active (it throttles multi-threaded x264enc)
    if grep -q "^CPUQuota=" "$SYSTEMD_FILE" 2>/dev/null; then
        QUOTA=$(grep "^CPUQuota=" "$SYSTEMD_FILE" | head -1)
        echo -e "${RED}❌${NC} Systemd $QUOTA (throttles x264enc — should be removed)"
        echo -e "    ${BLUE}ℹ️${NC}  Fix: redeploy with: sudo bash scripts/deploy.sh"
    else
        echo -e "${GREEN}✓${NC} Systemd CPUQuota: not set (correct — x264enc uses all cores)"
    fi

    # ExecStartPre governor check
    if grep -q "ExecStartPre=.*performance" "$SYSTEMD_FILE" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Systemd ExecStartPre: CPU governor → performance"
    else
        echo -e "${RED}❌${NC} Systemd ExecStartPre: CPU governor not configured"
        echo -e "    ${BLUE}ℹ️${NC}  Fix: redeploy with: sudo bash scripts/deploy.sh"
    fi

    # ExecStopPost governor restore check
    if grep -q "ExecStopPost=.*ondemand" "$SYSTEMD_FILE" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Systemd ExecStopPost: CPU governor → ondemand (restore)"
    else
        echo -e "${YELLOW}⚠️${NC}  Systemd ExecStopPost: CPU governor restore not configured"
    fi

    # MemoryMax check
    if grep -q "^MemoryMax=" "$SYSTEMD_FILE" 2>/dev/null; then
        MEMMAX=$(grep "^MemoryMax=" "$SYSTEMD_FILE" | cut -d= -f2)
        echo -e "${GREEN}✓${NC} Systemd MemoryMax: $MEMMAX"
    fi

    # Source vs deployed sync check
    SOURCE_FILE="/opt/FPVCopilotSky/systemd/fpvcopilot-sky.service"
    if [ -f "$SOURCE_FILE" ]; then
        if diff -q "$SOURCE_FILE" "$SYSTEMD_FILE" > /dev/null 2>&1; then
            echo -e "${GREEN}✓${NC} Systemd service: source and deployed are in sync"
        else
            echo -e "${YELLOW}⚠️${NC}  Systemd service: source differs from deployed!"
            echo -e "    ${BLUE}ℹ️${NC}  Fix: sudo bash scripts/deploy.sh"
        fi
    fi
else
    echo -e "${RED}❌${NC} Systemd service file not found at $SYSTEMD_FILE"
fi

# Sysctl streaming optimizations
echo -e "\n${BLUE}🔧 Kernel Tuning${NC}"
BBR=$(sysctl -n net.ipv4.tcp_congestion_control 2>/dev/null)
if [ "$BBR" = "bbr" ]; then
    echo -e "${GREEN}✓${NC} TCP congestion: BBR (optimal for 4G)"
else
    echo -e "${YELLOW}⚠️${NC}  TCP congestion: $BBR (should be bbr)"
fi

QDISC=$(sysctl -n net.core.default_qdisc 2>/dev/null)
if [ "$QDISC" = "fq" ]; then
    echo -e "${GREEN}✓${NC} Default qdisc: fq"
else
    echo -e "${YELLOW}⚠️${NC}  Default qdisc: $QDISC (should be fq)"
fi

RMEM=$(sysctl -n net.core.rmem_max 2>/dev/null)
if [ "$RMEM" -ge 134217728 ] 2>/dev/null; then
    echo -e "${GREEN}✓${NC} net.core.rmem_max: $(echo "$RMEM" | awk '{printf "%.0fMB", $1/1048576}')"
else
    echo -e "${YELLOW}⚠️${NC}  net.core.rmem_max: $RMEM (should be ≥128MB)"
fi

SWAP=$(sysctl -n vm.swappiness 2>/dev/null)
if [ "$SWAP" -le 10 ] 2>/dev/null; then
    echo -e "${GREEN}✓${NC} vm.swappiness: $SWAP"
else
    echo -e "${YELLOW}⚠️${NC}  vm.swappiness: $SWAP (should be ≤10 for embedded)"
fi

if [ -f "/etc/sysctl.d/99-fpv-streaming.conf" ]; then
    echo -e "${GREEN}✓${NC} FPV streaming sysctl config present"
else
    echo -e "${RED}❌${NC} /etc/sysctl.d/99-fpv-streaming.conf missing"
    echo -e "    ${BLUE}ℹ️${NC}  Fix: bash install.sh (creates sysctl config)"
fi
check_service NetworkManager
check_service ModemManager

echo -e "\n${BLUE}🔌 Network Ports${NC}"
check_port 80 "Nginx"
check_port 8000 "Backend API"

echo -e "\n${BLUE}🎥 Video / Cameras${NC}"
# Cameras
if ls /dev/video* > /dev/null 2>&1; then
    CAM_COUNT=$(ls /dev/video* 2>/dev/null | wc -l)
    echo -e "${GREEN}✅${NC} $CAM_COUNT video device(s) found"
    v4l2-ctl --list-devices 2>/dev/null | head -8 || ls /dev/video*
else
    echo -e "${YELLOW}⚠️${NC}  No video devices found (/dev/video*)"
fi
# GStreamer
if command -v gst-inspect-1.0 > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} GStreamer installed ($(gst-inspect-1.0 --version 2>/dev/null | head -1))"
else
    echo -e "${RED}❌${NC} GStreamer NOT installed"
fi

# WebRTC dependencies
echo -e "\n${BLUE}🌐 WebRTC Support${NC}"
# Check Python packages (aiortc, av)
if [ -f "/opt/FPVCopilotSky/venv/bin/python3" ]; then
    VENV_PYTHON="/opt/FPVCopilotSky/venv/bin/python3"

    if $VENV_PYTHON -c "import aiortc" 2>/dev/null; then
        AIORTC_VERSION=$($VENV_PYTHON -c "import aiortc; print(aiortc.__version__)" 2>/dev/null)
        echo -e "${GREEN}✅${NC} aiortc installed (${AIORTC_VERSION:-unknown})"
    else
        echo -e "${RED}❌${NC} aiortc NOT installed (pip install aiortc>=1.5.0)"
    fi

    if $VENV_PYTHON -c "import av" 2>/dev/null; then
        AV_VERSION=$($VENV_PYTHON -c "import av; print(av.__version__)" 2>/dev/null)
        echo -e "${GREEN}✅${NC} PyAV (av) installed (${AV_VERSION:-unknown})"
    else
        echo -e "${RED}❌${NC} PyAV (av) NOT installed (pip install av>=10.0.0)"
    fi
fi

# Check FFmpeg libraries
if pkg-config --exists libavcodec 2>/dev/null; then
    AVCODEC_VER=$(pkg-config --modversion libavcodec 2>/dev/null)
    echo -e "${GREEN}✅${NC} libavcodec installed (${AVCODEC_VER})"
else
    echo -e "${RED}❌${NC} libavcodec NOT found (apt install libavcodec-dev)"
fi

if pkg-config --exists libavformat 2>/dev/null; then
    AVFORMAT_VER=$(pkg-config --modversion libavformat 2>/dev/null)
    echo -e "${GREEN}✅${NC} libavformat installed (${AVFORMAT_VER})"
else
    echo -e "${RED}❌${NC} libavformat NOT found (apt install libavformat-dev)"
fi

if pkg-config --exists libsrtp2 2>/dev/null; then
    SRTP_VER=$(pkg-config --modversion libsrtp2 2>/dev/null)
    echo -e "${GREEN}✅${NC} libsrtp2 installed (${SRTP_VER})"
else
    echo -e "${YELLOW}⚠️${NC}  libsrtp2 NOT found (apt install libsrtp2-dev) - required for WebRTC"
fi

if pkg-config --exists opus 2>/dev/null; then
    OPUS_VER=$(pkg-config --modversion opus 2>/dev/null)
    echo -e "${GREEN}✓${NC} libopus installed (${OPUS_VER})"
else
    echo -e "${YELLOW}⚠️${NC}  libopus NOT found (apt install libopus-dev) - needed for audio"
fi

if pkg-config --exists vpx 2>/dev/null; then
    VPX_VER=$(pkg-config --modversion vpx 2>/dev/null)
    echo -e "${GREEN}✓${NC} libvpx installed (${VPX_VER})"
else
    echo -e "${YELLOW}⚠️${NC}  libvpx NOT found (apt install libvpx-dev) - needed for VP8/VP9"
fi

# Check v4l-utils
if command -v v4l2-ctl &> /dev/null; then
    echo -e "${GREEN}✓${NC} v4l2-ctl (video device control) available"
else
    echo -e "${RED}❌${NC} v4l2-ctl NOT found (apt install v4l-utils)"
fi

# Video streaming status via API
if [ $BACKEND_RUNNING -eq 0 ]; then
    VIDEO_STATUS=$(curl -s --max-time 3 http://localhost:8000/api/video/status 2>/dev/null)
    if [ -n "$VIDEO_STATUS" ]; then
        STREAMING=$(echo "$VIDEO_STATUS" | grep -o '"streaming":\s*true' | head -1)
        if [ -n "$STREAMING" ]; then
            echo -e "${GREEN}✅${NC} Video streaming is ACTIVE"
        else
            echo -e "${YELLOW}⚠️${NC}  Video streaming is stopped"
        fi
    fi
fi

echo -e "\n${BLUE}📊 Network Quality & Self-Healing${NC}"
# Check CAKE qdisc
if modinfo sch_cake &>/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} CAKE qdisc kernel module available"
else
    echo -e "${YELLOW}⚠️${NC}  CAKE qdisc module not available (bufferbloat control unavailable)"
fi

# Check tc (traffic control)
if command -v tc &>/dev/null; then
    # Check if CAKE is active on any interface
    CAKE_ACTIVE=$(tc qdisc show 2>/dev/null | grep -c "cake" 2>/dev/null)
    CAKE_ACTIVE=${CAKE_ACTIVE:-0}
    if [ "$CAKE_ACTIVE" -gt 0 ] 2>/dev/null; then
        echo -e "${GREEN}✅${NC} CAKE qdisc active on $CAKE_ACTIVE interface(s)"
    else
        echo -e "${GREEN}✓${NC} tc (traffic control) available"
    fi
else
    echo -e "${YELLOW}⚠️${NC}  tc (traffic control) not found"
fi

# Check iptables
if command -v iptables &>/dev/null; then
    echo -e "${GREEN}✓${NC} iptables available (VPN policy routing)"
else
    echo -e "${YELLOW}⚠️${NC}  iptables not found (VPN policy routing unavailable)"
fi

# Check MPTCP
if sysctl net.mptcp.enabled &>/dev/null 2>&1; then
    MPTCP_ENABLED=$(sysctl -n net.mptcp.enabled 2>/dev/null)
    if [ "$MPTCP_ENABLED" = "1" ]; then
        echo -e "${GREEN}✅${NC} MPTCP enabled (multi-path TCP for WiFi+4G bonding)"
    else
        echo -e "${YELLOW}⚠️${NC}  MPTCP available but disabled (enable via API or sysctl)"
    fi
else
    echo -e "${BLUE}ℹ️${NC}  MPTCP not supported by kernel (requires 5.6+)"
fi

# Network Event Bridge status via API
if [ $BACKEND_RUNNING -eq 0 ]; then
    BRIDGE_STATUS=$(curl -s --max-time 3 http://localhost:8000/api/network/bridge/status 2>/dev/null)
    if [ -n "$BRIDGE_STATUS" ]; then
        BRIDGE_ACTIVE=$(echo "$BRIDGE_STATUS" | grep -o '"active":\s*true' | head -1)
        if [ -n "$BRIDGE_ACTIVE" ]; then
            QUALITY_SCORE=$(echo "$BRIDGE_STATUS" | grep -oP '"score":\s*\K[\d.]+' | head -1)
            QUALITY_LABEL=$(echo "$BRIDGE_STATUS" | grep -oP '"label":\s*"\K[^"]+' | head -1)
            echo -e "${GREEN}✅${NC} Network Event Bridge ACTIVE (Score: ${QUALITY_SCORE:-?}/100 - ${QUALITY_LABEL:-?})"
        else
            echo -e "${YELLOW}⚠️${NC}  Network Event Bridge stopped (start via /api/network/bridge/start)"
        fi
    fi
fi

# ── FASE 1: Multi-Modem Pool ─────────────────────────────────────────────────
echo -e "\n${BLUE}🔀 Multi-Modem & Policy Routing (FASE 1-3)${NC}"

# ModemPool API
if [ $BACKEND_RUNNING -eq 0 ]; then
    POOL_STATUS=$(curl -s --max-time 3 http://localhost:8000/api/network/modems/status 2>/dev/null)
    if [ -n "$POOL_STATUS" ]; then
        POOL_ENABLED=$(echo "$POOL_STATUS" | grep -oP '"enabled":\s*\K(true|false)' | head -1)
        POOL_TOTAL=$(echo   "$POOL_STATUS" | grep -oP '"total_modems":\s*\K\d+' | head -1)
        POOL_CONN=$(echo    "$POOL_STATUS" | grep -oP '"connected_modems":\s*\K\d+' | head -1)
        POOL_ACTIVE=$(echo  "$POOL_STATUS" | grep -oP '"active_modem":\s*"\K[^"]+' | head -1)
        if [ "$POOL_ENABLED" = "true" ]; then
            echo -e "${GREEN}✅${NC} ModemPool ENABLED — total=$POOL_TOTAL connected=$POOL_CONN active=${POOL_ACTIVE:-none}"
        else
            echo -e "${YELLOW}⚠️${NC}  ModemPool present but disabled (enable in Preferences → Network)"
        fi
    else
        echo -e "${YELLOW}⚠️${NC}  ModemPool API unreachable (service may be starting up)"
    fi
else
    echo -e "${YELLOW}⚠️${NC}  Backend not running — skipping ModemPool check"
fi

# ── FASE 2: Policy Routing ────────────────────────────────────────────────────

# Check iptables mangle marks (fpv_ chains or MARK targets)
if command -v iptables &>/dev/null; then
    FPV_MARKS=$(sudo iptables -t mangle -L OUTPUT -n 2>/dev/null | grep -c 'MARK\|0x[0-9]' 2>/dev/null)
    FPV_MARKS=${FPV_MARKS:-0}
    if [ "$FPV_MARKS" -gt 0 ] 2>/dev/null; then
        echo -e "${GREEN}✅${NC} iptables mangle MARK rules active ($FPV_MARKS rules — VPN/Video/MAVLink isolation)"
    else
        echo -e "${YELLOW}⚠️${NC}  No iptables mangle marks found (policy routing not initialized or disabled)"
    fi
else
    echo -e "${YELLOW}⚠️${NC}  iptables not available"
fi

# Check ip rules for fwmark → table routing
if command -v ip &>/dev/null; then
    FWMARK_RULES=$(ip rule show 2>/dev/null | grep -c 'fwmark' 2>/dev/null)
    FWMARK_RULES=${FWMARK_RULES:-0}
    if [ "$FWMARK_RULES" -gt 0 ] 2>/dev/null; then
        echo -e "${GREEN}✅${NC} Policy routing rules active ($FWMARK_RULES fwmark rules — tables 100/200 configured)"
    else
        echo -e "${YELLOW}⚠️${NC}  No fwmark ip rules found (set via /api/network/policy-routing/apply)"
    fi
fi

# Policy Routing API status
if [ $BACKEND_RUNNING -eq 0 ]; then
    PR_STATUS=$(curl -s --max-time 3 http://localhost:8000/api/network/policy-routing/status 2>/dev/null)
    if [ -n "$PR_STATUS" ]; then
        PR_INIT=$(echo "$PR_STATUS" | grep -oP '"initialized":\s*\K(true|false)' | head -1)
        if [ "$PR_INIT" = "true" ]; then
            PR_IFACE=$(echo "$PR_STATUS" | grep -oP '"interface":\s*"\K[^"]+' | head -1)
            echo -e "${GREEN}✅${NC} PolicyRoutingManager initialized — active modem: ${PR_IFACE:-none}"
        else
            echo -e "${YELLOW}⚠️${NC}  PolicyRoutingManager not initialized (enable in Preferences → Network → Policy Routing)"
        fi
    fi
fi

# ── FASE 3: VPN Health Checker ────────────────────────────────────────────────

if [ $BACKEND_RUNNING -eq 0 ]; then
    VH_STATUS=$(curl -s --max-time 3 http://localhost:8000/api/network/vpn-health/status 2>/dev/null)
    if [ -n "$VH_STATUS" ]; then
        VH_INIT=$(echo   "$VH_STATUS" | grep -oP '"initialized":\s*\K(true|false)' | head -1)
        VH_TYPE=$(echo   "$VH_STATUS" | grep -oP '"vpn_type":\s*"\K[^"]+' | head -1)
        VH_HEALTHY=$(echo "$VH_STATUS" | grep -oP '"healthy":\s*\K(true|false)' | head -1 2>/dev/null || true)
        VH_RTT=$(echo    "$VH_STATUS" | grep -oP '"rtt_ms":\s*\K[\d.]+' | head -1)
        if [ "$VH_TYPE" = "none" ] || [ -z "$VH_TYPE" ]; then
            echo -e "${BLUE}ℹ️${NC}  VPNHealthChecker: no VPN detected (checks disabled — normal if no VPN installed)"
        elif [ "$VH_HEALTHY" = "true" ]; then
            echo -e "${GREEN}✅${NC} VPN health OK — type=${VH_TYPE} RTT=${VH_RTT:-?}ms"
        elif [ "$VH_INIT" = "true" ]; then
            echo -e "${YELLOW}⚠️${NC}  VPN health DEGRADED — type=${VH_TYPE} (peer unreachable or interface down)"
        else
            echo -e "${YELLOW}⚠️${NC}  VPNHealthChecker not initialized"
        fi
    else
        echo -e "${YELLOW}⚠️${NC}  VPN Health API unreachable"
    fi
fi

echo -e "\n${BLUE}💻 Python Environment${NC}"
if [ -f "/opt/FPVCopilotSky/venv/bin/python3" ]; then
    VENV_PYTHON="/opt/FPVCopilotSky/venv/bin/python3"
    PYTHON_VER=$($VENV_PYTHON --version 2>&1)
    echo -e "${GREEN}✓${NC} Python venv exists: $PYTHON_VER"

    # Check critical Python packages
    MISSING_PACKAGES=""

    if ! $VENV_PYTHON -c "import fastapi" 2>/dev/null; then
        MISSING_PACKAGES="${MISSING_PACKAGES}fastapi "
    fi
    if ! $VENV_PYTHON -c "import pymavlink" 2>/dev/null; then
        MISSING_PACKAGES="${MISSING_PACKAGES}pymavlink "
    fi
    if ! $VENV_PYTHON -c "import serial" 2>/dev/null; then
        MISSING_PACKAGES="${MISSING_PACKAGES}pyserial "
    fi
    if ! $VENV_PYTHON -c "import gi" 2>/dev/null; then
        MISSING_PACKAGES="${MISSING_PACKAGES}PyGObject "
    fi

    if [ -z "$MISSING_PACKAGES" ]; then
        echo -e "${GREEN}✓${NC} All critical Python packages installed"
    else
        echo -e "${RED}❌${NC} Missing Python packages: $MISSING_PACKAGES"
        echo -e "    ${BLUE}ℹ️${NC}  Fix: source venv/bin/activate && pip install -r requirements.txt"
    fi
else
    echo -e "${RED}❌${NC} Python venv NOT found at /opt/FPVCopilotSky/venv"
    echo -e "    ${BLUE}ℹ️${NC}  Run: bash install.sh"
fi

echo -e "\n${BLUE}📁 Frontend Build${NC}"
if [ -d "/opt/FPVCopilotSky/frontend/client/dist" ] && [ "$(ls -A /opt/FPVCopilotSky/frontend/client/dist 2>/dev/null)" ]; then
    echo -e "${GREEN}✓${NC} Frontend build exists"
    # Check if Node.js is available for rebuilding
    if command -v node &> /dev/null; then
        NODE_VER=$(node --version)
        echo -e "${GREEN}✓${NC} Node.js installed: $NODE_VER"
    else
        echo -e "${YELLOW}⚠️${NC}  Node.js not found (needed for frontend rebuild)"
    fi
else
    echo -e "${YELLOW}⚠️${NC}  Frontend build NOT found"
    echo -e "    ${BLUE}ℹ️${NC}  Fix: cd frontend/client && npm install && npm run build"
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

if command -v ethtool &> /dev/null; then
    echo -e "${GREEN}✓${NC} ethtool (network interface tuning) available"
else
    echo -e "${YELLOW}⚠️${NC}  ethtool NOT found (install: apt-get install ethtool)"
fi

if command -v pkg-config &> /dev/null; then
    echo -e "${GREEN}✓${NC} pkg-config available"
else
    echo -e "${RED}❌${NC} pkg-config NOT found (needed for build)"
fi

if command -v curl &> /dev/null; then
    echo -e "${GREEN}✓${NC} curl available"
else
    echo -e "${RED}❌${NC} curl NOT found (install: apt-get install curl)"
fi

echo -e "\n${BLUE}👥 User Groups & Permissions${NC}"
# Check if user is in required groups
if groups $USER | grep -q "\bdialout\b"; then
    echo -e "${GREEN}✓${NC} User in 'dialout' group (serial port access)"
else
    echo -e "${RED}❌${NC} User NOT in 'dialout' group"
    echo -e "    ${BLUE}ℹ️${NC}  MAVLink serial communication will fail"
    echo -e "    ${BLUE}ℹ️${NC}  Fix: sudo usermod -a -G dialout $USER && reboot"
fi

if groups $USER | grep -q "\bvideo\b"; then
    echo -e "${GREEN}✓${NC} User in 'video' group (camera/video device access)"
else
    echo -e "${RED}❌${NC} User NOT in 'video' group"
    echo -e "    ${BLUE}ℹ️${NC}  Video streaming may fail"
    echo -e "    ${BLUE}ℹ️${NC}  Fix: sudo usermod -a -G video $USER && reboot"
fi

# Check serial port permissions
if ls /dev/ttyAML* > /dev/null 2>&1; then
    SERIAL_PERMS=$(stat -c "%a %G" /dev/ttyAML0 2>/dev/null || echo "unknown")
    if [[ "$SERIAL_PERMS" =~ "dialout" ]]; then
        echo -e "${GREEN}✓${NC} Serial port /dev/ttyAML0 group: dialout"
    else
        echo -e "${YELLOW}⚠️${NC}  Serial port /dev/ttyAML0 group: $SERIAL_PERMS (should be dialout)"
    fi
fi

# Check if serial-getty is masked (prevents MAVLink conflicts)
if systemctl is-masked serial-getty@ttyAML0.service &>/dev/null; then
    echo -e "${GREEN}✓${NC} serial-getty@ttyAML0 is masked (no conflict with MAVLink)"
elif systemctl is-active serial-getty@ttyAML0.service &>/dev/null; then
    echo -e "${RED}❌${NC} serial-getty@ttyAML0 is ACTIVE - will conflict with MAVLink!"
    echo -e "    ${BLUE}ℹ️${NC}  Fix: sudo systemctl stop serial-getty@ttyAML0 && sudo systemctl mask serial-getty@ttyAML0"
else
    echo -e "${GREEN}✓${NC} serial-getty@ttyAML0 is disabled"
fi

echo -e "\n${BLUE}📡 WiFi Configuration${NC}"
# Check wlan0 state
if command -v nmcli &> /dev/null && nmcli dev show wlan0 &>/dev/null; then
    WLAN_STATE=$(nmcli dev status 2>/dev/null | grep wlan0 | awk '{print $3}')
    WLAN_CONNECTION=$(nmcli dev status 2>/dev/null | grep wlan0 | awk '{print $4}')

    if [ "$WLAN_STATE" = "connected" ]; then
        echo -e "${GREEN}✅${NC} wlan0 is $WLAN_STATE ($WLAN_CONNECTION)"
    elif [ "$WLAN_STATE" = "unmanaged" ]; then
        echo -e "${RED}❌${NC} wlan0 is UNMANAGED (WiFi scanning won't work)"
        echo -e "    ${BLUE}ℹ️${NC}  Fix: sudo nmcli dev set wlan0 managed yes"
    else
        echo -e "${YELLOW}⚠️${NC}  wlan0 state: $WLAN_STATE"
    fi

    # Check if WiFi scanning works
    if sudo -n iw dev wlan0 scan &>/dev/null 2>&1; then
        WIFI_COUNT=$(sudo iw dev wlan0 scan 2>/dev/null | grep -c "^BSS " || echo "0")
        if [ "$WIFI_COUNT" -gt 0 ]; then
            echo -e "${GREEN}✅${NC} WiFi scanning works ($WIFI_COUNT networks detected)"
        else
            echo -e "${YELLOW}⚠️${NC}  WiFi scan returned 0 networks"
        fi
    else
        echo -e "${YELLOW}⚠️${NC}  WiFi scanning requires sudo permissions"
    fi
else
    echo -e "${RED}❌${NC} wlan0 interface not found"
fi

# Check NetworkManager configuration
if [ -f "/etc/NetworkManager/NetworkManager.conf" ]; then
    if grep -q "managed=true" /etc/NetworkManager/NetworkManager.conf 2>/dev/null; then
        echo -e "${GREEN}✅${NC} NetworkManager configured to manage interfaces"
    elif grep -q "managed=false" /etc/NetworkManager/NetworkManager.conf 2>/dev/null; then
        echo -e "${RED}❌${NC} NetworkManager set to managed=false"
        echo -e "    ${BLUE}ℹ️${NC}  Fix: sudo sed -i 's/managed=false/managed=true/' /etc/NetworkManager/NetworkManager.conf"
    fi
fi

# Check netplan WiFi configuration (if exists)
if [ -f "/etc/netplan/30-wifis-dhcp.yaml" ]; then
    if grep -q "renderer: NetworkManager" /etc/netplan/30-wifis-dhcp.yaml 2>/dev/null; then
        echo -e "${GREEN}✅${NC} Netplan WiFi using NetworkManager renderer"
    elif grep -q "renderer: networkd" /etc/netplan/30-wifis-dhcp.yaml 2>/dev/null; then
        echo -e "${YELLOW}⚠️${NC}  Netplan WiFi using networkd (should use NetworkManager)"
        echo -e "    ${BLUE}ℹ️${NC}  Fix: Change renderer to NetworkManager in netplan"
    fi
fi

echo -e "\n${BLUE}🔑 Sudo Permissions${NC}"

# Determine which sudoers file is in use
SUDOERS_UNIFIED="/etc/sudoers.d/fpvcopilot-sky"
if [ -f "$SUDOERS_UNIFIED" ]; then
    echo -e "${GREEN}✅${NC} Unified sudoers file: $SUDOERS_UNIFIED"

    # Functional tests
    if sudo -n iw dev wlan0 scan &>/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} WiFi scan commands work without password"
    else
        echo -e "${YELLOW}⚠️${NC}  WiFi scan commands require password"
    fi

    TAILSCALE_TEST=$(sudo -n tailscale status 2>&1)
    TAILSCALE_EXIT=$?
    if [[ $TAILSCALE_EXIT -eq 0 ]] || [[ "$TAILSCALE_TEST" =~ "Logged out" ]]; then
        echo -e "${GREEN}✓${NC} Tailscale commands work without password"
    else
        echo -e "${YELLOW}⚠️${NC}  Tailscale commands may require password"
    fi

    echo -e "${BLUE}─${NC} Network management:"
    if sudo -n nmcli connection show --active > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} nmcli commands work without password"
    else
        echo -e "${YELLOW}⚠️${NC}  nmcli commands may require password"
    fi
    if sudo -n ip route show > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} ip route commands work without password"
    else
        echo -e "${YELLOW}⚠️${NC}  ip route commands may require password"
    fi
    if sudo -n ip link show > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} ip link commands work without password"
    else
        echo -e "${YELLOW}⚠️${NC}  ip link commands may require password"
    fi

    SYSTEMCTL_TEST=$(sudo -n systemctl status fpvcopilot-sky 2>&1)
    if [[ $? -eq 0 ]] || [[ "$SYSTEMCTL_TEST" =~ "Active:" ]]; then
        echo -e "${GREEN}✓${NC} systemctl commands work without password"
    else
        echo -e "${YELLOW}⚠️${NC}  systemctl commands may require password"
    fi

    JOURNALCTL_TEST=$(sudo -n journalctl -u fpvcopilot-sky -n 1 2>&1)
    if [[ $? -eq 0 ]]; then
        echo -e "${GREEN}✓${NC} journalctl commands work without password"
    else
        echo -e "${YELLOW}⚠️${NC}  journalctl commands may require password"
    fi

    # Check restricted permissions are present (not dangerous wildcards)
    if sudo grep -q "sysctl -w net\." "$SUDOERS_UNIFIED" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} sysctl (restricted network tuning) configured"
    else
        echo -e "${YELLOW}⚠️${NC}  sysctl permission missing"
    fi

    if sudo grep -q "ethtool" "$SUDOERS_UNIFIED" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} ethtool (restricted WoL disable) configured"
    else
        echo -e "${YELLOW}⚠️${NC}  ethtool permission missing"
    fi

    # Warn about dangerous legacy entries
    if sudo grep -q "tee \*" "$SUDOERS_UNIFIED" 2>/dev/null; then
        echo -e "${RED}❌${NC} DANGEROUS: 'tee *' wildcard found — re-run: sudo bash scripts/setup-sudoers.sh"
    fi
    if sudo grep -qP "sysctl -w \*$" "$SUDOERS_UNIFIED" 2>/dev/null; then
        echo -e "${RED}❌${NC} DANGEROUS: 'sysctl -w *' wildcard found — re-run: sudo bash scripts/setup-sudoers.sh"
    fi
else
    # Legacy file detection
    LEGACY_FILES=""
    [ -f "/etc/sudoers.d/fpvcopilot-wifi" ] && LEGACY_FILES="$LEGACY_FILES fpvcopilot-wifi"
    [ -f "/etc/sudoers.d/fpvcopilot-system" ] && LEGACY_FILES="$LEGACY_FILES fpvcopilot-system"
    [ -f "/etc/sudoers.d/tailscale" ] && LEGACY_FILES="$LEGACY_FILES tailscale"
    [ -f "/etc/sudoers.d/fpvcopilot-tailscale" ] && LEGACY_FILES="$LEGACY_FILES fpvcopilot-tailscale"

    if [ -n "$LEGACY_FILES" ]; then
        echo -e "${YELLOW}⚠️${NC}  Legacy sudoers files found:$LEGACY_FILES"
        echo -e "    ${BLUE}ℹ️${NC}  Migrate to unified file: sudo bash scripts/setup-sudoers.sh"
    else
        echo -e "${RED}❌${NC} No sudoers files found"
        echo -e "    ${BLUE}ℹ️${NC}  Run: sudo bash scripts/setup-sudoers.sh"
    fi
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
        THREADS=$(ps -eLf 2>/dev/null | grep -c "^.*$PID" || echo "?")
        echo "   Backend PID: $PID"
        echo "   Memory: $MEM"
        echo "   CPU: $CPU"
        echo "   Threads: $THREADS"
    fi

    # Video streaming performance
    VIDEO_JSON=$(curl -s --max-time 3 http://localhost:8000/api/video/status 2>/dev/null)
    if [ -n "$VIDEO_JSON" ]; then
        IS_STREAMING=$(echo "$VIDEO_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('streaming', False))" 2>/dev/null)
        if [ "$IS_STREAMING" = "True" ]; then
            STATS=$(echo "$VIDEO_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
s = d.get('stats', {})
fps = s.get('current_fps', 0)
bitrate = s.get('current_bitrate', 0)
health = s.get('health', '?')
uptime = s.get('uptime_formatted', '?')
frames = s.get('frames_sent', 0)
print(f'FPS:{fps} BR:{bitrate} HP:{health} UP:{uptime} FR:{frames}')
" 2>/dev/null)
            if [ -n "$STATS" ]; then
                FPS=$(echo "$STATS" | grep -oP 'FPS:\K[0-9]+')
                BR=$(echo "$STATS" | grep -oP 'BR:\K[0-9]+')
                HP=$(echo "$STATS" | grep -oP 'HP:\K[a-z]+')
                UP=$(echo "$STATS" | grep -oP 'UP:\K[0-9:]+')
                FR=$(echo "$STATS" | grep -oP 'FR:\K[0-9]+')

                echo -e "\n${BLUE}📹 Video Streaming${NC}"
                # FPS check
                if [ "$FPS" -ge 25 ] 2>/dev/null; then
                    echo -e "   ${GREEN}✅${NC} FPS: $FPS (target: 30)"
                elif [ "$FPS" -ge 15 ] 2>/dev/null; then
                    echo -e "   ${YELLOW}⚠️${NC}  FPS: $FPS (below target 30)"
                elif [ "$FPS" -gt 0 ] 2>/dev/null; then
                    echo -e "   ${RED}❌${NC} FPS: $FPS (critically low)"
                else
                    echo -e "   ${YELLOW}⚠️${NC}  FPS: $FPS (starting up...)"
                fi

                # Health
                if [ "$HP" = "good" ]; then
                    echo -e "   ${GREEN}✅${NC} Health: $HP"
                elif [ "$HP" = "fair" ]; then
                    echo -e "   ${YELLOW}⚠️${NC}  Health: $HP"
                else
                    echo -e "   ${RED}❌${NC} Health: $HP"
                fi

                echo "   Bitrate: ${BR} kbps"
                echo "   Uptime: $UP"
                echo "   Frames: $FR"
            fi
        else
            echo -e "\n${BLUE}📹 Video Streaming${NC}"
            echo -e "   ${YELLOW}⚠️${NC}  Not streaming (start via web UI or API)"
        fi
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
