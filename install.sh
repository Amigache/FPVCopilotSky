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

# Optimize system for video streaming
echo ""
echo "⚡ Optimizing system for video streaming..."

# Increase UDP buffer sizes
sudo sysctl -w net.core.rmem_max=26214400 2>/dev/null || true
sudo sysctl -w net.core.wmem_max=26214400 2>/dev/null || true
sudo sysctl -w net.core.rmem_default=26214400 2>/dev/null || true
sudo sysctl -w net.core.wmem_default=26214400 2>/dev/null || true

# Make permanent
if ! grep -q "net.core.rmem_max=26214400" /etc/sysctl.conf 2>/dev/null; then
    echo "net.core.rmem_max=26214400" | sudo tee -a /etc/sysctl.conf > /dev/null
    echo "net.core.wmem_max=26214400" | sudo tee -a /etc/sysctl.conf > /dev/null
    echo "net.core.rmem_default=26214400" | sudo tee -a /etc/sysctl.conf > /dev/null
    echo "net.core.wmem_default=26214400" | sudo tee -a /etc/sysctl.conf > /dev/null
    echo "  ✓ UDP buffer sizes increased"
fi

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
