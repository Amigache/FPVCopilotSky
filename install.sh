#!/bin/bash
# FPV Copilot Sky - Installation Script
# Installs all dependencies needed to run the project
# Compatible with Linux systems (Radxa, Raspberry Pi, x86, etc.)

set -e

echo "🚀 Installing FPV Copilot Sky dependencies..."

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
    gstreamer1.0-alsa \
    gir1.2-gstreamer-1.0 \
    gir1.2-gst-plugins-base-1.0 \
    python3-gi \
    python3-gi-cairo \
    libcairo2-dev \
    libgirepository1.0-dev \
    pkg-config \
    v4l-utils

# Install additional tools for video
echo "🎥 Installing video tools..."
sudo apt-get install -y ffmpeg v4l-utils || true

# Install network management tools
echo "🌐 Installing network management tools..."
sudo apt-get install -y \
    network-manager \
    modemmanager \
    hostapd \
    wireless-tools \
    usb-modeswitch \
    usb-modeswitch-data

# Enable and start network services
echo "🔧 Configuring network services..."
sudo systemctl enable NetworkManager
sudo systemctl start NetworkManager
echo "  ✓ NetworkManager enabled and started"

sudo systemctl enable ModemManager
sudo systemctl start ModemManager
echo "  ✓ ModemManager enabled and started"

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

# Configure sudo permissions for Tailscale
echo "🔐 Configuring Tailscale sudo permissions..."
SUDOERS_FILE="/etc/sudoers.d/tailscale"
if [ ! -f "$SUDOERS_FILE" ]; then
    sudo tee "$SUDOERS_FILE" > /dev/null << EOF
# Allow user to manage Tailscale without password
$USER ALL=(ALL) NOPASSWD: /usr/bin/tailscale up
$USER ALL=(ALL) NOPASSWD: /usr/bin/tailscale up *
$USER ALL=(ALL) NOPASSWD: /usr/bin/tailscale down
$USER ALL=(ALL) NOPASSWD: /usr/bin/tailscale logout
$USER ALL=(ALL) NOPASSWD: /usr/bin/tailscale status
$USER ALL=(ALL) NOPASSWD: /usr/bin/tailscale status *
EOF
    sudo chmod 440 "$SUDOERS_FILE"
    echo "  ✓ Tailscale sudo permissions configured"
else
    echo "  ✓ Tailscale sudo permissions already configured"
fi

# Set permissions for serial ports
echo "🔐 Setting up serial port permissions..."
sudo usermod -a -G dialout $USER
sudo usermod -a -G video $USER

# Create udev rule for serial ports
if [ ! -f /etc/udev/rules.d/99-radxa-serial.rules ]; then
    echo 'KERNEL=="ttyAML*", MODE="0660", GROUP="dialout"' | sudo tee /etc/udev/rules.d/99-radxa-serial.rules > /dev/null
    echo "  ✓ Udev rules for serial ports created"
fi

# Disable serial-getty on ttyAML0 to prevent conflicts with MAVLink
# The serial-getty service conflicts with MAVLink:
# - Changes port group from dialout to tty
# - Removes read permissions from group
# - Consumes all serial data as console input
if systemctl is-active --quiet serial-getty@ttyAML0.service 2>/dev/null; then
    sudo systemctl stop serial-getty@ttyAML0.service
fi
sudo systemctl disable serial-getty@ttyAML0.service 2>/dev/null || true
sudo systemctl mask serial-getty@ttyAML0.service 2>/dev/null || true
echo "  ✓ Serial getty disabled on ttyAML0"

# Trigger udev to apply serial port rules
sudo udevadm trigger --action=change --subsystem-match=tty 2>/dev/null || true
sudo udevadm settle 2>/dev/null || true

# Set permissions for serial ports if they exist
if ls /dev/ttyAML* > /dev/null 2>&1; then
    sudo chmod 666 /dev/ttyAML* || true
    echo "✓ Permissions set for /dev/ttyAML*"
fi
if ls /dev/ttyUSB* > /dev/null 2>&1; then
    sudo chmod 666 /dev/ttyUSB* || true
    echo "✓ Permissions set for /dev/ttyUSB*"
fi

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

echo ""
echo "✅ Installation complete!"
echo ""
echo "=========================================="
echo "Quick Start:"
echo "=========================================="
echo ""
echo "To run the backend:"
echo "  source venv/bin/activate"
echo "  python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
echo ""
echo "To run the frontend:"
echo "  cd frontend/client && npm run dev -- --host"
echo ""
echo "API Endpoints:"
echo "  • MAVLink:  http://localhost:8000/api/mavlink"
echo "  • Router:   http://localhost:8000/api/mavlink-router"
echo "  • Video:    http://localhost:8000/api/video"
echo "  • System:   http://localhost:8000/api/system"
echo "  • WebSocket: ws://localhost:8000/ws"
echo ""
echo "Mission Planner Video:"
echo "  • Configure GStreamer source with UDP port 5600"
echo "  • Use /api/video/pipeline-string for the pipeline"
echo ""
echo "⚠️ You may need to log out and log back in for permissions to take effect."
