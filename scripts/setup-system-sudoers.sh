#!/bin/bash
# Setup system management sudo permissions
# Run this script with: sudo bash setup-system-sudoers.sh

SUDOERS_FILE="/etc/sudoers.d/fpvcopilot-system"
FPVCOPILOT_USER="fpvcopilotsky"

# Get actual user if run with sudo, otherwise use fpvcopilotsky
CURRENT_USER="${SUDO_USER:-$FPVCOPILOT_USER}"

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

# Allow $CURRENT_USER to scan WiFi networks without password
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/iw dev * scan
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/sbin/iw dev * link
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
else
    echo "❌ Error: Invalid sudoers syntax"
    rm -f "$SUDOERS_FILE"
    exit 1
fi
