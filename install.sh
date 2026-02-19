#!/bin/bash
# FPV Copilot Sky - Installation Script
# Installs all dependencies needed to run the project
# Compatible with Linux systems (Radxa, Raspberry Pi, x86, etc.)
#
# System Configuration Changes:
# =============================
# This script modifies the following system files and settings:
#
# Network Configuration:
#   - /etc/NetworkManager/NetworkManager.conf → managed=false → managed=true
#   - /etc/netplan/30-wifis-dhcp.yaml → renderer: networkd → renderer: NetworkManager
#   - wlan0 interface set to managed mode via nmcli
#
# Sudo Permissions (no-password):
#   - /etc/sudoers.d/tailscale → Tailscale VPN management
#   - /etc/sudoers.d/fpvcopilot-wifi → WiFi scan, connect, disconnect
#
# System Services:
#   - NetworkManager service enabled and started
#   - ModemManager service enabled and started
#
# Kernel Parameters:
#   - /etc/sysctl.d/99-fpv-streaming.conf → Network optimizations for 4G/LTE video streaming
#   - TCP buffer sizes, UDP optimizations, BBR congestion control
#   - Network backlog and memory management tuning
#
# USB Modem Configuration:
#   - Huawei E3372h modem mode switching (mass storage → modem mode)
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to create fpvcopilotsky user if it doesn't exist
setup_fpvcopilotsky_user() {
    local USERNAME="fpvcopilotsky"

    if id "$USERNAME" &>/dev/null; then
        echo -e "${GREEN}✓${NC} User '$USERNAME' already exists"
        return 0
    fi

    echo ""
    echo -e "${BLUE}👤 Setting up FPVCopilotSky system user...${NC}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "The FPVCopilotSky service runs as a dedicated system user for security."
    echo "This user needs access to hardware (serial ports, cameras, network)."
    echo ""

    # Create user with home directory
    echo -e "${BLUE}Creating user '$USERNAME'...${NC}"
    sudo useradd -m -s /bin/bash "$USERNAME" || {
        echo -e "${RED}✗ Failed to create user '$USERNAME'${NC}"
        return 1
    }

    # Set password
    echo ""
    echo -e "${YELLOW}Please set a password for user '$USERNAME':${NC}"
    sudo passwd "$USERNAME"

    # Add user to required groups
    echo ""
    echo -e "${BLUE}Adding '$USERNAME' to system groups...${NC}"
    sudo usermod -a -G dialout "$USERNAME"     # Serial port access
    sudo usermod -a -G video "$USERNAME"       # Camera access
    sudo usermod -a -G netdev "$USERNAME"      # Network device access
    sudo usermod -a -G sudo "$USERNAME"        # Sudo access for system management

    echo -e "${GREEN}✓${NC} User '$USERNAME' created and configured"
    echo -e "${GREEN}✓${NC} Groups: dialout, video, netdev, sudo"
    echo ""

    # Set ownership of project directory
    if [ -d "/opt/FPVCopilotSky" ]; then
        echo -e "${BLUE}Setting ownership of /opt/FPVCopilotSky...${NC}"
        sudo chown -R "$USERNAME:$USERNAME" /opt/FPVCopilotSky
        echo -e "${GREEN}✓${NC} Directory ownership updated"
    fi

    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}✓ User setup completed successfully${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
}

echo "🚀 Installing FPV Copilot Sky dependencies..."

# Setup fpvcopilotsky user first
setup_fpvcopilotsky_user

# Detect system
echo "📋 System information:"
uname -a

# Update system
echo "📦 Updating system packages..."
sudo apt-get update

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
sudo apt-get install -y python3 python3-pip python3-venv python3-dev

# Install GStreamer for video streaming
echo "📹 Installing GStreamer for video streaming..."
sudo apt-get install -y \
    gstreamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-plugins-ugly \
    gstreamer1.0-libav \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    python3-gi \
    python3-gi-cairo \
    libcairo2-dev \
    libgirepository1.0-dev \
    pkg-config \
    v4l-utils

# Install FFmpeg libraries for WebRTC (aiortc + av/PyAV)
echo "🌐 Installing FFmpeg libraries for WebRTC support..."
sudo apt-get install -y \
    ffmpeg \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
    libopus-dev \
    libvpx-dev \
    libsrtp2-dev

# Install network management tools
echo "🌐 Installing network management tools..."
sudo apt-get install -y \
    network-manager \
    modemmanager \
    hostapd \
    wireless-tools \
    usb-modeswitch \
    usb-modeswitch-data \
    iproute2 \
    ethtool \
    curl \
    iptables

# Install CAKE qdisc and tc for bufferbloat control (Flight Mode)
echo "⚙️  Installing traffic control tools for CAKE bufferbloat mitigation..."
# Note: iproute2 already installed in network management tools section
# CAKE is built into kernel 6.x+ (sch_cake module)
if modinfo sch_cake &>/dev/null 2>&1; then
    echo "  ✓ CAKE qdisc kernel module available"
else
    echo "  ⚠️  CAKE qdisc module not found (kernel may not support it)"
fi
if command -v tc &>/dev/null; then
    echo "  ✓ tc (traffic control) available"
else
    echo "  ⚠️  tc not found"
fi

# Check MPTCP kernel support
echo "🔀 Checking MPTCP (Multi-Path TCP) support..."
if sysctl net.mptcp.enabled &>/dev/null 2>&1; then
    echo "  ✓ MPTCP supported by kernel"
else
    echo "  ℹ️  MPTCP not supported by this kernel (requires 5.6+)"
fi

# Enable and start network services
echo "🔧 Configuring network services..."

# Configure NetworkManager to manage all interfaces
echo "  📝 Configuring NetworkManager..."
sudo sed -i 's/managed=false/managed=true/' /etc/NetworkManager/NetworkManager.conf 2>/dev/null || true

sudo systemctl enable NetworkManager
sudo systemctl start NetworkManager
echo "  ✓ NetworkManager enabled and started"

sudo systemctl enable ModemManager
sudo systemctl start ModemManager
echo "  ✓ ModemManager enabled and started"

# Ensure WiFi interface is managed by NetworkManager
echo "  📡 Configuring WiFi management..."

# Configure netplan to use NetworkManager for WiFi (if netplan is present)
if [ -d "/etc/netplan" ]; then
    NETPLAN_WIFI_FILE="/etc/netplan/30-wifis-dhcp.yaml"
    if [ -f "$NETPLAN_WIFI_FILE" ]; then
        # Check if it uses networkd renderer
        if grep -q "renderer: networkd" "$NETPLAN_WIFI_FILE" 2>/dev/null; then
            echo "  📝 Updating netplan to use NetworkManager renderer..."
            sudo sed -i 's/renderer: networkd/renderer: NetworkManager/' "$NETPLAN_WIFI_FILE" 2>/dev/null || true
            echo "  ✓ Netplan WiFi renderer updated to NetworkManager"
            # Apply netplan changes
            sudo netplan apply 2>/dev/null && sleep 2 || true
        fi
    fi
fi

if nmcli dev show wlan0 &>/dev/null; then
    sudo nmcli dev set wlan0 managed yes 2>/dev/null || true
    sleep 1
    WLAN_STATE=$(nmcli dev status 2>/dev/null | grep wlan0 | awk '{print $3}')
    if [ "$WLAN_STATE" = "unmanaged" ]; then
        echo "  ⚠️  wlan0 still unmanaged (may need reboot)"
    else
        echo "  ✓ wlan0 set to managed (state: $WLAN_STATE)"
    fi
fi

# Verify network tools work
echo "🔍 Verifying network tools..."
if command -v nmcli &> /dev/null; then
    echo "  ✓ nmcli (NetworkManager CLI) available"
    nmcli general status || true
else
    echo "  ⚠ nmcli not found"
fi

if command -v mmcli &> /dev/null; then
    echo "  ✓ mmcli (ModemManager CLI) available"
    mmcli -L 2>/dev/null || echo "    (No modems detected - OK)"
else
    echo "  ⚠ mmcli not found"
fi

if command -v hostapd &> /dev/null; then
    echo "  ✓ hostapd (WiFi hotspot) available"
else
    echo "  ⚠ hostapd not found"
fi

if command -v iwconfig &> /dev/null; then
    echo "  ✓ iwconfig (wireless tools) available"
else
    echo "  ⚠ iwconfig not found"
fi

if command -v usb_modeswitch &> /dev/null; then
    echo "  ✓ usb_modeswitch (USB modem mode switching) available"
else
    echo "  ⚠ usb_modeswitch not found"
fi

# Configure USB modems automatically
echo "📱 Configuring USB modems..."
configure_usb_modems() {
    # Look for Huawei modems in mass storage mode
    if lsusb | grep -q "12d1:1f01.*Mass storage"; then
        echo "  🔄 Huawei modem found in mass storage mode, switching to modem mode..."
        sudo usb_modeswitch -v 12d1 -p 1f01 -M "55534243123456780000000000000a11062000000000000100000000000000" 2>/dev/null || true
        sleep 3
        if lsusb | grep -q "12d1:14dc.*HiLink Modem"; then
            echo "  ✓ Huawei modem successfully switched to modem mode"
        elif lsusb | grep -q "12d1:"; then
            echo "  ✓ Huawei modem detected (may already be in correct mode)"
        else
            echo "  ⚠ Huawei modem mode switch may have failed"
        fi
    elif lsusb | grep -q "12d1:"; then
        echo "  ✓ Huawei modem already in correct mode"
    else
        echo "  ℹ️ No Huawei modem detected"
    fi

    # Wait a moment for ModemManager to detect the modem
    sleep 2
    MMCLI_OUTPUT=$(mmcli -L 2>/dev/null || echo "")
    if echo "$MMCLI_OUTPUT" | grep -q "^/org/freedesktop/ModemManager1/Modem/"; then
        echo "  ✓ Traditional modem detected by ModemManager"
    else
        if lsusb | grep -q "12d1:14dc.*HiLink"; then
            echo "  ℹ️ HiLink modem detected - works as network interface (this is normal)"
            echo "    HiLink modems don't appear in ModemManager - they work as USB network adapters"
        else
            echo "  ℹ️ No traditional modem detected by ModemManager (this is normal if no modem is connected)"
        fi
    fi
}
configure_usb_modems

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "🔧 Creating Python virtual environment..."
    python3 -m venv venv --system-site-packages  # Include system packages (GStreamer)
fi

# Activate virtual environment
source venv/bin/activate

# Install Python packages
echo "📚 Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Install Node.js if not installed
if ! command -v node &> /dev/null; then
    echo "📦 Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

# Install frontend dependencies
echo "⚛️ Installing frontend dependencies..."
cd frontend/client
npm install
cd ../..

# Install Tailscale for VPN support
echo ""
echo "🔐 Installing Tailscale VPN..."
if command -v tailscale &> /dev/null; then
    echo "  ✓ Tailscale already installed"
else
    if curl -fsSL https://tailscale.com/install.sh | sh; then
        echo "  ✓ Tailscale installed successfully"
        echo "  ℹ️  To connect: sudo tailscale up"
    else
        echo "  ⚠ Tailscale installation failed (optional)"
    fi
fi

# Configure sudo permissions (unified file: /etc/sudoers.d/fpvcopilot-sky)
echo "🔐 Configuring sudo permissions..."
if [ -f "scripts/setup-sudoers.sh" ]; then
    chmod +x scripts/setup-sudoers.sh
    sudo bash scripts/setup-sudoers.sh
else
    echo "  ⚠ Sudoers setup script not found (scripts/setup-sudoers.sh)"
fi

# Configure network priority management (VPN-aware routing)
echo "🌐 Configuring network priority management..."

# Verify iproute2 available (needed for route management)
if command -v ip &> /dev/null; then
    IP_BIN=$(which ip)
    echo "  ✓ iproute2 available: $IP_BIN"
else
    echo "  ⚠ iproute2 not found, installing..."
    sudo apt-get install -y iproute2
fi

# Verify ip route sudoers are in place
if [ -f "/etc/sudoers.d/fpvcopilot-system" ]; then
    if sudo grep -q "ip route" /etc/sudoers.d/fpvcopilot-system 2>/dev/null; then
        echo "  ✓ Network route management sudo permissions configured"
    else
        echo "  ⚠ Route permissions missing, re-running sudoers setup..."
        sudo bash scripts/setup-system-sudoers.sh
    fi
fi

# Detect and configure default network priority
# 4G modem is always primary when available, WiFi is backup
echo "  🔍 Detecting network interfaces..."
MODEM_IFACE=""
WIFI_IFACE=""

# Detect USB 4G modem (HiLink mode uses 192.168.8.x)
if ip -o addr show 2>/dev/null | grep -q "192\.168\.8\."; then
    MODEM_IFACE=$(ip -o addr show 2>/dev/null | grep "192\.168\.8\." | awk '{print $2}' | head -1)
    echo "  ✓ USB 4G modem detected: $MODEM_IFACE"
else
    echo "  ℹ️ No USB 4G modem detected"
fi

# Detect WiFi
WIFI_IFACE=$(nmcli -t -f DEVICE,TYPE device 2>/dev/null | grep ':wifi$' | cut -d: -f1 | head -1)
if [ -n "$WIFI_IFACE" ]; then
    echo "  ✓ WiFi interface detected: $WIFI_IFACE"
else
    echo "  ℹ️ No WiFi interface detected"
fi

# Set initial network priority: 4G primary (metric 100), WiFi backup (metric 200)
if [ -n "$MODEM_IFACE" ]; then
    MODEM_GW=$(ip route show default dev "$MODEM_IFACE" 2>/dev/null | awk '/via/{print $3}' | head -1)
    if [ -n "$MODEM_GW" ]; then
        CURRENT_METRIC=$(ip route show default dev "$MODEM_IFACE" 2>/dev/null | grep -oP 'metric \K\d+')
        if [ "$CURRENT_METRIC" != "100" ]; then
            sudo ip route del default via "$MODEM_GW" dev "$MODEM_IFACE" 2>/dev/null || true
            sudo ip route add default via "$MODEM_GW" dev "$MODEM_IFACE" metric 100 2>/dev/null || true
            echo "  ✓ 4G modem set as primary (metric 100)"
        else
            echo "  ✓ 4G modem already primary (metric 100)"
        fi
    fi
fi

if [ -n "$WIFI_IFACE" ]; then
    WIFI_GW=$(ip route show default dev "$WIFI_IFACE" 2>/dev/null | awk '/via/{print $3}' | head -1)
    if [ -n "$WIFI_GW" ]; then
        CURRENT_METRIC=$(ip route show default dev "$WIFI_IFACE" 2>/dev/null | grep -oP 'metric \K\d+')
        if [ "$CURRENT_METRIC" != "200" ]; then
            sudo ip route del default via "$WIFI_GW" dev "$WIFI_IFACE" 2>/dev/null || true
            sudo ip route add default via "$WIFI_GW" dev "$WIFI_IFACE" metric 200 2>/dev/null || true
            echo "  ✓ WiFi set as backup (metric 200)"
        else
            echo "  ✓ WiFi already backup (metric 200)"
        fi
    fi
fi

# Persist metrics in NetworkManager connections
if [ -n "$MODEM_IFACE" ]; then
    NM_CONN=$(nmcli -t -f NAME,DEVICE connection show --active 2>/dev/null | grep ":${MODEM_IFACE}$" | cut -d: -f1)
    if [ -n "$NM_CONN" ]; then
        nmcli connection modify "$NM_CONN" ipv4.route-metric 100 2>/dev/null || true
        echo "  ✓ NetworkManager metric persisted for 4G"
    fi
fi

if [ -n "$WIFI_IFACE" ]; then
    NM_CONN=$(nmcli -t -f NAME,DEVICE connection show --active 2>/dev/null | grep ":${WIFI_IFACE}$" | cut -d: -f1)
    if [ -n "$NM_CONN" ]; then
        nmcli connection modify "$NM_CONN" ipv4.route-metric 200 2>/dev/null || true
        echo "  ✓ NetworkManager metric persisted for WiFi"
    fi
fi

echo "  ✓ Network priority management configured"
echo "    Priority: 4G (metric 100) > WiFi (metric 200)"
echo "    Auto-adjust: Enabled (every 30s via backend)"
echo "    VPN-aware: Smooth transitions when Tailscale active"

# Set permissions for serial ports
echo "🔐 Setting up serial port permissions..."
sudo usermod -a -G dialout $USER
sudo usermod -a -G video $USER

# Also add fpvcopilotsky user if different from current user
if [ "$USER" != "fpvcopilotsky" ] && id "fpvcopilotsky" &>/dev/null; then
    sudo usermod -a -G dialout fpvcopilotsky
    sudo usermod -a -G video fpvcopilotsky
    echo "  ✓ Permissions also set for fpvcopilotsky user"
fi

# Configure serial ports and disable getty conflicts
if [ -f "scripts/setup-serial-ports.sh" ]; then
    chmod +x scripts/setup-serial-ports.sh
    sudo bash scripts/setup-serial-ports.sh
else
    echo "  ⚠ Serial port setup script not found (scripts/setup-serial-ports.sh)"
fi

# Install nginx for production reverse proxy
echo ""
echo "🌐 Installing nginx for production..."
if command -v nginx &> /dev/null; then
    echo "  ✓ Nginx already installed"
else
    sudo apt-get install -y nginx
    echo "  ✓ Nginx installed"
fi
sudo systemctl enable nginx 2>/dev/null || true
# Disable default nginx site to avoid conflicts
if [ -L /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
    echo "  ✓ Default nginx site disabled"
fi
# Create log directory
sudo mkdir -p /var/log/nginx
sudo chown www-data:www-data /var/log/nginx 2>/dev/null || true

# Check GStreamer plugins
echo ""
echo "🔍 Checking GStreamer plugins..."
if gst-inspect-1.0 jpegenc > /dev/null 2>&1; then
    echo "  ✓ MJPEG encoder (jpegenc) found"
else
    echo "  ⚠ MJPEG encoder not found"
fi
if gst-inspect-1.0 x264enc > /dev/null 2>&1; then
    echo "  ✓ H.264 encoder (x264enc) found"
else
    echo "  ⚠ H.264 encoder not found (install gstreamer1.0-plugins-ugly)"
fi
if gst-inspect-1.0 v4l2src > /dev/null 2>&1; then
    echo "  ✓ V4L2 video source found"
else
    echo "  ⚠ V4L2 plugin not found"
fi
if gst-inspect-1.0 rtpjpegpay > /dev/null 2>&1; then
    echo "  ✓ RTP JPEG payloader found"
else
    echo "  ⚠ RTP JPEG payloader not found"
fi
if gst-inspect-1.0 rtph264pay > /dev/null 2>&1; then
    echo "  ✓ RTP H.264 payloader found"
else
    echo "  ⚠ RTP H.264 payloader not found"
fi

# Check for camera
echo ""
echo "📷 Checking for cameras..."
if ls /dev/video* > /dev/null 2>&1; then
    v4l2-ctl --list-devices 2>/dev/null || ls /dev/video*
else
    echo "  ⚠ No cameras found"
fi

# Optimize system for video streaming and 4G/LTE
echo ""
echo "⚡ Optimizing system for video streaming and 4G..."

# Create sysctl configuration for FPV streaming
sudo tee /etc/sysctl.d/99-fpv-streaming.conf > /dev/null << 'SYSCTL_EOF'
# FPV Streaming Optimizations for 4G/LTE
# Optimized for video and telemetry over cellular networks

# ===== TCP Buffer Sizes (for MAVLink, WebSocket) =====
net.core.rmem_max=134217728
net.core.wmem_max=134217728
net.core.rmem_default=1048576
net.core.wmem_default=1048576
net.ipv4.tcp_rmem=4096 1048576 134217728
net.ipv4.tcp_wmem=4096 1048576 134217728

# ===== UDP Optimizations (for video streaming) =====
net.ipv4.udp_rmem_min=65536
net.ipv4.udp_wmem_min=65536

# ===== BBR Congestion Control (best for 4G variable bandwidth) =====
net.core.default_qdisc=fq
net.ipv4.tcp_congestion_control=bbr
net.ipv4.tcp_slow_start_after_idle=0
net.ipv4.tcp_mtu_probing=1
net.ipv4.tcp_no_metrics_save=1
net.ipv4.tcp_fastopen=3

# ===== Network Backlog (handle bursts better) =====
net.core.netdev_max_backlog=5000
net.core.somaxconn=4096

# ===== IPv6 Disable (reduce overhead for embedded) =====
net.ipv6.conf.all.disable_ipv6=1
net.ipv6.conf.default.disable_ipv6=1

# ===== MPTCP (Multi-Path TCP for WiFi+4G bonding) =====
net.mptcp.enabled=1
net.mptcp.allow_join_initial_addr_port=1
net.mptcp.checksum_enabled=0

# ===== Memory Management =====
vm.swappiness=10

# ===== Kernel Logging (reduce spam) =====
kernel.printk=3 3 3 3
SYSCTL_EOF

# Remove old conflicting entries from sysctl.conf
sudo sed -i '/^vm.swappiness=100$/d; /^net.core.rmem_max=26214400$/d; /^net.core.rmem_default=26214400$/d; /^net.core.wmem_max=26214400$/d; /^net.core.wmem_default=26214400$/d' /etc/sysctl.conf 2>/dev/null || true

# Apply sysctl settings
sudo sysctl --system > /dev/null 2>&1 || true
echo "  ✓ Network buffers optimized for 4G streaming"
echo "  ✓ BBR congestion control enabled"
echo "  ✓ UDP/TCP tuning applied"

# Setup local data directory
echo ""
echo "📁 Setting up local data directory..."
DATA_DIR="/var/lib/fpvcopilot-sky"
sudo mkdir -p "$DATA_DIR"
sudo chown fpvcopilotsky:fpvcopilotsky "$DATA_DIR"
sudo chmod 755 "$DATA_DIR"

# Initialize version file if it doesn't exist
if [ ! -f "$DATA_DIR/version" ]; then
    # Try to get version from git tag, fallback to 1.0.0
    if cd /opt/FPVCopilotSky && git describe --tags --exact-match HEAD 2>/dev/null; then
        INITIAL_VERSION=$(git describe --tags --exact-match HEAD 2>/dev/null | sed 's/^v//')
    else
        INITIAL_VERSION="1.0.0"
    fi
    echo "$INITIAL_VERSION" | sudo tee "$DATA_DIR/version" > /dev/null
    sudo chown fpvcopilotsky:fpvcopilotsky "$DATA_DIR/version"
    echo "  ✓ Version file initialized: $INITIAL_VERSION"
else
    echo "  ✓ Version file already exists"
fi
echo "  ✓ Data directory configured: $DATA_DIR"

# Deploy to production (build frontend, install systemd service, start)
echo ""
echo "🚀 Deploying to production..."
if [ -f "scripts/deploy.sh" ]; then
    chmod +x scripts/deploy.sh
    sudo bash scripts/deploy.sh
else
    echo "  ⚠ Deploy script not found (scripts/deploy.sh)"
    echo "  Skipping production deployment — run manually later"
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "=========================================="
echo "System is ready!"
echo "=========================================="
echo ""
IP=$(hostname -I | awk '{print $1}')
echo "🌐 Application: http://$IP"
echo "📡 API:         http://$IP:8000/docs"
echo ""
echo -e "${GREEN}${BOLD}🎯 FPVCopilotSky Management Console${NC}"
echo -e "${BLUE}For easy system management, use the CLI:${NC}"
echo ""
echo -e "  ${CYAN}cd /opt/FPVCopilotSky${NC}"
echo -e "  ${CYAN}./fpv${NC}"
echo ""
echo "Quick manual commands:"
echo "  Status:   bash scripts/status.sh"
echo "  Restart:  sudo systemctl restart fpvcopilot-sky"
echo "  Logs:     sudo journalctl -u fpvcopilot-sky -f"
echo "  Deploy:   sudo bash scripts/deploy.sh"
echo ""
echo "⚠️ You may need to log out and log back in for group permissions to take effect."
