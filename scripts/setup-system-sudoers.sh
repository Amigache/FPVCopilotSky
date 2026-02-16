#!/bin/bash
# Setup system management sudo permissions
# Run this script with: sudo bash setup-system-sudoers.sh

SUDOERS_FILE="/etc/sudoers.d/fpvcopilot-system"
FPVCOPILOT_USER="fpvcopilotsky"

# Always use fpvcopilotsky user (not root even when run with sudo)
CURRENT_USER="$FPVCOPILOT_USER"

echo "Setting up system management sudo permissions for user: $CURRENT_USER"

# Create sudoers file with proper permissions
cat > "$SUDOERS_FILE" << EOF
# Allow $CURRENT_USER to manage fpvcopilot-sky service without password
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart fpvcopilot-sky
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl status fpvcopilot-sky
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start fpvcopilot-sky
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop fpvcopilot-sky
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/journalctl -u fpvcopilot-sky *

# Allow $CURRENT_USER to manage nginx service without password
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nginx
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl status nginx
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl reload nginx

# Allow $CURRENT_USER to manage network routes without password (VPN-aware routing)
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/ip route add *
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/ip route del *
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/ip route change *
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/ip route replace *
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/ip link set *
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/ip -o addr show
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/ip -o -4 addr show
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/ip addr show

# Allow $CURRENT_USER to scan WiFi networks without password
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/iw dev * scan
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/iw dev * link

# Allow $CURRENT_USER to manage system network parameters (sysctl)
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/sysctl -w *

# Allow $CURRENT_USER to manage network interfaces (ethtool)
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/ethtool -s *

# Allow $CURRENT_USER to manage DNS cache (dnsmasq)
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/apt-get update
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/apt-get install -y dnsmasq
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/mkdir -p *
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl start dnsmasq
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop dnsmasq
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl status dnsmasq
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart dnsmasq
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable dnsmasq
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/killall -USR1 dnsmasq
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/killall -HUP dnsmasq
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/tee *

# Allow $CURRENT_USER to manage traffic control (CAKE bufferbloat)
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/tc qdisc *
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/tc class *
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/tc filter *

# Allow $CURRENT_USER to manage iptables (VPN policy routing marks)
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/iptables -t mangle *

# Allow $CURRENT_USER to manage policy routing rules
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/ip rule *

# Allow $CURRENT_USER to manage MPTCP (multi-path TCP)
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/ip mptcp *
EOF

# Set proper permissions
chmod 440 "$SUDOERS_FILE"

# Verify syntax
if visudo -c -f "$SUDOERS_FILE" > /dev/null 2>&1; then
    echo "✅ System management sudo permissions configured successfully!"
    echo ""
    echo "You can now use these commands without password:"
    echo "  - sudo systemctl restart fpvcopilot-sky"
    echo "  - sudo systemctl restart nginx"
    echo "  - sudo systemctl status fpvcopilot-sky"
    echo "  - sudo journalctl -u fpvcopilot-sky"
    echo "  - sudo ip route add/del/change (for network priority management)"
    echo "  - sudo tc qdisc/class/filter (for CAKE bufferbloat control)"
    echo "  - sudo iptables -t mangle (for VPN policy routing)"
    echo "  - sudo ip rule (for policy routing rules)"
    echo "  - sudo ip mptcp (for multi-path TCP management)"
else
    echo "❌ Error: Invalid sudoers syntax"
    rm -f "$SUDOERS_FILE"
    exit 1
fi
