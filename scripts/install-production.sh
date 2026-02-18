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

# Configure serial ports and disable getty conflicts
echo -e "\n${BLUE}🔧 Configuring serial port permissions...${NC}"
if [ -f "scripts/setup-serial-ports.sh" ]; then
    bash scripts/setup-serial-ports.sh
else
    echo -e "${YELLOW}⚠️  Serial port setup script not found (scripts/setup-serial-ports.sh)${NC}"
fi

echo -e "\n${BLUE}🔧 Optimizing system for 4G video streaming...${NC}"

# Create sysctl configuration for FPV streaming optimizations
cat > /etc/sysctl.d/99-fpv-streaming.conf << 'SYSCTL_EOF'
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
sed -i '/^vm.swappiness=100$/d; /^net.core.rmem_max=26214400$/d; /^net.core.rmem_default=26214400$/d; /^net.core.wmem_max=26214400$/d; /^net.core.wmem_default=26214400$/d' /etc/sysctl.conf 2>/dev/null || true

# Apply sysctl settings
sysctl --system > /dev/null 2>&1 || true
echo -e "${GREEN}✅ Network optimizations applied (BBR, buffers, 4G tuning)${NC}"

echo -e "\n${BLUE}🔧 Setting up project permissions...${NC}"

# Ensure frontend/client/dist directory exists and has correct permissions
mkdir -p /opt/FPVCopilotSky/frontend/client/dist
chown -R $ACTUAL_USER:$ACTUAL_USER /opt/FPVCopilotSky

echo -e "${GREEN}✅ Permissions configured${NC}"

# Configure sudo permissions for advanced networking (FASE 1-3)
echo -e "\n${BLUE}🔒 Configuring sudo permissions (iptables, ip route, policy routing)...${NC}"
if [ -f "/opt/FPVCopilotSky/scripts/setup-sudoers.sh" ]; then
    chmod +x /opt/FPVCopilotSky/scripts/setup-sudoers.sh
    bash /opt/FPVCopilotSky/scripts/setup-sudoers.sh
    echo -e "${GREEN}✅ Sudo permissions configured${NC}"
else
    echo -e "${YELLOW}⚠️  Sudoers setup script not found (run manually: bash scripts/setup-sudoers.sh)${NC}"
fi
echo -e "\n📋 Next steps:"
echo -e "   1. Build and deploy: ${BLUE}bash /opt/FPVCopilotSky/scripts/deploy.sh${NC}"
echo -e "   2. Check service status: ${BLUE}sudo systemctl status fpvcopilot-sky${NC}"
echo -e "   3. View logs: ${BLUE}sudo journalctl -u fpvcopilot-sky -f${NC}"
echo -e "\n🌐 After deployment, access the app at: ${GREEN}http://$(hostname -I | awk '{print $1}')${NC}"
