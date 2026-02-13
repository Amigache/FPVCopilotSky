#!/bin/bash
# FPV Copilot Sky - Pre-flight Check
# Verificación exhaustiva antes de ejecutar la aplicación
# Este script verifica TODAS las dependencias, permisos y configuraciones

set -e

echo "🚁 FPV Copilot Sky - Pre-Flight Check"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Track failures
CRITICAL_FAILURES=0
WARNINGS=0

check_critical() {
    local name=$1
    local command=$2

    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ $name${NC}"
        return 0
    else
        echo -e "${RED}❌ $name - CRITICAL${NC}"
        ((CRITICAL_FAILURES++))
        return 1
    fi
}

check_warning() {
    local name=$1
    local command=$2

    if eval "$command" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ $name${NC}"
        return 0
    else
        echo -e "${YELLOW}⚠️  $name - WARNING${NC}"
        ((WARNINGS++))
        return 1
    fi
}

# ============================================
# SYSTEM DEPENDENCIES
# ============================================
echo -e "${BLUE}📦 System Dependencies${NC}"

check_critical "Python 3" "command -v python3"
check_critical "pip" "command -v pip3"
check_critical "pkg-config" "command -v pkg-config"
check_critical "curl" "command -v curl"

echo ""

# ============================================
# GSTREAMER
# ============================================
echo -e "${BLUE}📹 GStreamer${NC}"

check_critical "GStreamer tools" "command -v gst-inspect-1.0"
check_critical "jpegenc plugin (MJPEG)" "gst-inspect-1.0 jpegenc"
check_critical "x264enc plugin (H.264)" "gst-inspect-1.0 x264enc"
check_critical "v4l2src plugin (V4L2)" "gst-inspect-1.0 v4l2src"
check_critical "rtpjpegpay plugin (RTP)" "gst-inspect-1.0 rtpjpegpay"
check_critical "rtph264pay plugin (RTP)" "gst-inspect-1.0 rtph264pay"

echo ""

# ============================================
# FFMPEG & WEBRTC LIBRARIES
# ============================================
echo -e "${BLUE}🌐 FFmpeg & WebRTC Libraries${NC}"

check_critical "libavcodec" "pkg-config --exists libavcodec"
check_critical "libavformat" "pkg-config --exists libavformat"
check_critical "libavutil" "pkg-config --exists libavutil"
check_critical "libswscale" "pkg-config --exists libswscale"
check_warning "libsrtp2 (WebRTC)" "pkg-config --exists libsrtp2"
check_warning "libopus (Audio)" "pkg-config --exists opus"
check_warning "libvpx (VP8/VP9)" "pkg-config --exists vpx"

echo ""

# ============================================
# NETWORK TOOLS
# ============================================
echo -e "${BLUE}🌐 Network Tools${NC}"

check_critical "NetworkManager (nmcli)" "command -v nmcli && nmcli general status"
check_critical "ModemManager (mmcli)" "command -v mmcli"
check_critical "iw (wireless)" "command -v iw"
check_critical "ip (iproute2)" "command -v ip"
check_warning "ethtool" "command -v ethtool"
check_warning "hostapd (hotspot)" "command -v hostapd"
check_warning "usb_modeswitch" "command -v usb_modeswitch"

echo ""

# ============================================
# VIDEO TOOLS
# ============================================
echo -e "${BLUE}🎥 Video Tools${NC}"

check_critical "v4l2-ctl" "command -v v4l2-ctl"
check_warning "ffmpeg" "command -v ffmpeg"

echo ""

# ============================================
# PYTHON VIRTUAL ENVIRONMENT
# ============================================
echo -e "${BLUE}🐍 Python Virtual Environment${NC}"

if [ -f "/opt/FPVCopilotSky/venv/bin/python3" ]; then
    echo -e "${GREEN}✅ venv exists${NC}"

    VENV_PYTHON="/opt/FPVCopilotSky/venv/bin/python3"

    # Check critical packages
    check_critical "fastapi" "$VENV_PYTHON -c 'import fastapi'"
    check_critical "uvicorn" "$VENV_PYTHON -c 'import uvicorn'"
    check_critical "pymavlink" "$VENV_PYTHON -c 'import pymavlink'"
    check_critical "pyserial" "$VENV_PYTHON -c 'import serial'"
    check_critical "PyGObject" "$VENV_PYTHON -c 'import gi'"
    check_warning "aiortc (WebRTC)" "$VENV_PYTHON -c 'import aiortc'"
    check_warning "av (PyAV)" "$VENV_PYTHON -c 'import av'"
else
    echo -e "${RED}❌ venv NOT FOUND - CRITICAL${NC}"
    ((CRITICAL_FAILURES++))
fi

echo ""

# ============================================
# USER GROUPS
# ============================================
echo -e "${BLUE}👥 User Groups${NC}"

if groups $USER | grep -q "\bdialout\b"; then
    echo -e "${GREEN}✅ dialout group (serial ports)${NC}"
else
    echo -e "${RED}❌ dialout group - CRITICAL${NC}"
    echo -e "   Fix: sudo usermod -a -G dialout $USER && reboot"
    ((CRITICAL_FAILURES++))
fi

if groups $USER | grep -q "\bvideo\b"; then
    echo -e "${GREEN}✅ video group (cameras)${NC}"
else
    echo -e "${RED}❌ video group - CRITICAL${NC}"
    echo -e "   Fix: sudo usermod -a -G video $USER && reboot"
    ((CRITICAL_FAILURES++))
fi

echo ""

# ============================================
# SUDO PERMISSIONS
# ============================================
echo -e "${BLUE}🔐 Sudo Permissions (no-password)${NC}"

check_warning "nmcli" "sudo -n nmcli connection show"
check_warning "ip route" "sudo -n ip route show"
check_warning "ip link" "sudo -n ip link show"
check_warning "iw scan" "sudo -n iw dev 2>&1 | head -1"
check_warning "systemctl (fpvcopilot-sky)" "sudo -n systemctl status fpvcopilot-sky"
check_warning "journalctl" "sudo -n journalctl -u fpvcopilot-sky -n 1"

echo ""

# ============================================
# SUDOERS FILES
# ============================================
echo -e "${BLUE}📝 Sudoers Files${NC}"

if [ -f "/etc/sudoers.d/fpvcopilot-wifi" ]; then
    echo -e "${GREEN}✓ /etc/sudoers.d/fpvcopilot-wifi${NC}"
else
    echo -e "${YELLOW}⚠️  /etc/sudoers.d/fpvcopilot-wifi missing${NC}"
    ((WARNINGS++))
fi

if [ -f "/etc/sudoers.d/fpvcopilot-system" ]; then
    echo -e "${GREEN}✓ /etc/sudoers.d/fpvcopilot-system${NC}"
else
    echo -e "${YELLOW}⚠️  /etc/sudoers.d/fpvcopilot-system missing${NC}"
    ((WARNINGS++))
fi

if [ -f "/etc/sudoers.d/tailscale" ]; then
    echo -e "${GREEN}✓ /etc/sudoers.d/tailscale${NC}"
else
    echo -e "${YELLOW}⚠️  /etc/sudoers.d/tailscale missing (VPN optional)${NC}"
fi

echo ""

# ============================================
# NETWORK CONFIGURATION
# ============================================
echo -e "${BLUE}🌐 Network Configuration${NC}"

# NetworkManager
if [ -f "/etc/NetworkManager/NetworkManager.conf" ]; then
    if grep -q "managed=true" /etc/NetworkManager/NetworkManager.conf 2>/dev/null; then
        echo -e "${GREEN}✅ NetworkManager: managed=true${NC}"
    else
        echo -e "${RED}❌ NetworkManager: managed=false - CRITICAL${NC}"
        echo -e "   Fix: sudo sed -i 's/managed=false/managed=true/' /etc/NetworkManager/NetworkManager.conf"
        ((CRITICAL_FAILURES++))
    fi
else
    echo -e "${YELLOW}⚠️  NetworkManager.conf not found${NC}"
    ((WARNINGS++))
fi

# Netplan (optional)
if [ -f "/etc/netplan/30-wifis-dhcp.yaml" ]; then
    if grep -q "renderer: NetworkManager" /etc/netplan/30-wifis-dhcp.yaml 2>/dev/null; then
        echo -e "${GREEN}✓ Netplan: renderer=NetworkManager${NC}"
    elif grep -q "renderer: networkd" /etc/netplan/30-wifis-dhcp.yaml 2>/dev/null; then
        echo -e "${YELLOW}⚠️  Netplan: renderer=networkd (should be NetworkManager)${NC}"
        ((WARNINGS++))
    fi
fi

# WiFi interface
if nmcli dev show wlan0 &>/dev/null; then
    WLAN_STATE=$(nmcli dev status 2>/dev/null | grep wlan0 | awk '{print $3}')
    if [ "$WLAN_STATE" = "unmanaged" ]; then
        echo -e "${RED}❌ wlan0: UNMANAGED - WiFi won't work${NC}"
        echo -e "   Fix: sudo nmcli dev set wlan0 managed yes"
        ((CRITICAL_FAILURES++))
    else
        echo -e "${GREEN}✅ wlan0: $WLAN_STATE${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  wlan0 interface not found${NC}"
fi

echo ""

# ============================================
# SERIAL PORTS
# ============================================
echo -e "${BLUE}🔌 Serial Ports${NC}"

if ls /dev/ttyAML* > /dev/null 2>&1; then
    echo -e "${GREEN}✓ /dev/ttyAML* exists${NC}"

    # Check permissions
    SERIAL_GROUP=$(stat -c "%G" /dev/ttyAML0 2>/dev/null || echo "unknown")
    if [ "$SERIAL_GROUP" = "dialout" ]; then
        echo -e "${GREEN}✓ Serial port group: dialout${NC}"
    else
        echo -e "${YELLOW}⚠️  Serial port group: $SERIAL_GROUP (should be dialout)${NC}"
        ((WARNINGS++))
    fi

    # Check serial-getty
    if systemctl is-masked serial-getty@ttyAML0.service &>/dev/null; then
        echo -e "${GREEN}✓ serial-getty@ttyAML0: masked${NC}"
    elif systemctl is-active serial-getty@ttyAML0.service &>/dev/null; then
        echo -e "${RED}❌ serial-getty@ttyAML0: ACTIVE - will conflict with MAVLink!${NC}"
        echo -e "   Fix: sudo systemctl mask serial-getty@ttyAML0"
        ((CRITICAL_FAILURES++))
    else
        echo -e "${GREEN}✓ serial-getty@ttyAML0: disabled${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  /dev/ttyAML* not found (check if board has serial)${NC}"
fi

echo ""

# ============================================
# VIDEO DEVICES
# ============================================
echo -e "${BLUE}📷 Video Devices${NC}"

if ls /dev/video* > /dev/null 2>&1; then
    VIDEO_COUNT=$(ls /dev/video* 2>/dev/null | wc -l)
    echo -e "${GREEN}✅ $VIDEO_COUNT video device(s) found${NC}"
    v4l2-ctl --list-devices 2>/dev/null | head -10 || ls /dev/video*
else
    echo -e "${YELLOW}⚠️  No video devices found${NC}"
    ((WARNINGS++))
fi

echo ""

# ============================================
# FRONTEND BUILD
# ============================================
echo -e "${BLUE}⚛️  Frontend Build${NC}"

if [ -d "/opt/FPVCopilotSky/frontend/client/dist" ] && [ "$(ls -A /opt/FPVCopilotSky/frontend/client/dist 2>/dev/null)" ]; then
    echo -e "${GREEN}✅ Frontend build exists${NC}"
else
    echo -e "${YELLOW}⚠️  Frontend build NOT found${NC}"
    echo -e "   Fix: cd frontend/client && npm install && npm run build"
    ((WARNINGS++))
fi

if command -v node &> /dev/null; then
    NODE_VER=$(node --version)
    echo -e "${GREEN}✓ Node.js: $NODE_VER${NC}"
else
    echo -e "${YELLOW}⚠️  Node.js not found (needed for frontend rebuild)${NC}"
    ((WARNINGS++))
fi

echo ""

# ============================================
# SYSTEMD SERVICES
# ============================================
echo -e "${BLUE}🔧 Systemd Services${NC}"

if systemctl list-unit-files | grep -q "fpvcopilot-sky.service"; then
    echo -e "${GREEN}✓ fpvcopilot-sky.service installed${NC}"

    if systemctl is-enabled fpvcopilot-sky &>/dev/null; then
        echo -e "${GREEN}✓ fpvcopilot-sky: enabled${NC}"
    else
        echo -e "${YELLOW}⚠️  fpvcopilot-sky: not enabled${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  fpvcopilot-sky.service not installed${NC}"
    ((WARNINGS++))
fi

if systemctl is-active NetworkManager &>/dev/null; then
    echo -e "${GREEN}✓ NetworkManager: active${NC}"
else
    echo -e "${RED}❌ NetworkManager: NOT active - CRITICAL${NC}"
    ((CRITICAL_FAILURES++))
fi

if systemctl is-active ModemManager &>/dev/null; then
    echo -e "${GREEN}✓ ModemManager: active${NC}"
else
    echo -e "${YELLOW}⚠️  ModemManager: not active${NC}"
fi

echo ""

# ============================================
# SYSTEM OPTIMIZATIONS
# ============================================
echo -e "${BLUE}⚡ System Optimizations${NC}"

if [ -f "/etc/sysctl.d/99-fpv-streaming.conf" ]; then
    echo -e "${GREEN}✓ /etc/sysctl.d/99-fpv-streaming.conf exists${NC}"

    # Check BBR
    if grep -q "net.ipv4.tcp_congestion_control=bbr" /etc/sysctl.d/99-fpv-streaming.conf 2>/dev/null; then
        echo -e "${GREEN}✓ BBR congestion control configured${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  System optimizations not configured${NC}"
    ((WARNINGS++))
fi

echo ""

# ============================================
# SUMMARY
# ============================================
echo "======================================"
echo -e "${BLUE}📊 Pre-Flight Check Summary${NC}"
echo "======================================"
echo ""

if [ $CRITICAL_FAILURES -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✅ ALL CHECKS PASSED${NC}"
    echo ""
    echo "System is ready for flight! 🚀"
    echo ""
    echo "To start the services:"
    echo "  sudo systemctl start fpvcopilot-sky"
    echo "  sudo systemctl start nginx"
    echo ""
    echo "Or use production deployment:"
    echo "  bash scripts/deploy.sh"
    exit 0
elif [ $CRITICAL_FAILURES -eq 0 ]; then
    echo -e "${YELLOW}⚠️  $WARNINGS WARNING(S)${NC}"
    echo ""
    echo "System should work but some features may be unavailable."
    echo "Review warnings above and fix if needed."
    echo ""
    echo "To start anyway:"
    echo "  bash scripts/deploy.sh"
    exit 0
else
    echo -e "${RED}❌ $CRITICAL_FAILURES CRITICAL FAILURE(S)${NC}"
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}⚠️  $WARNINGS WARNING(S)${NC}"
    fi
    echo ""
    echo "System is NOT ready. Fix critical issues above."
    echo ""
    echo "Re-run installation:"
    echo "  bash install.sh"
    echo ""
    echo "Or fix issues manually and run this check again:"
    echo "  bash scripts/preflight-check.sh"
    exit 1
fi
