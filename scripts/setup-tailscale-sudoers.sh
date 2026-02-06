#!/bin/bash
# Setup Tailscale sudo permissions for VPN management
# Run this script with: sudo bash setup-tailscale-sudoers.sh

SUDOERS_FILE="/etc/sudoers.d/fpvcopilot-tailscale"
FPVCOPILOT_USER="fpvcopilotsky"

# Get actual user if run with sudo, otherwise use fpvcopilotsky
CURRENT_USER="${SUDO_USER:-$FPVCOPILOT_USER}"

echo "Setting up Tailscale sudo permissions for user: $CURRENT_USER"

# Create sudoers file with proper permissions
cat > "$SUDOERS_FILE" << EOF
# Allow $CURRENT_USER to manage Tailscale without password
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/tailscale up
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/tailscale up *
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/tailscale down
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/tailscale logout
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/tailscale status
$CURRENT_USER ALL=(ALL) NOPASSWD: /usr/bin/tailscale status *
EOF

# Set proper permissions
chmod 440 "$SUDOERS_FILE"

# Verify syntax
if visudo -c -f "$SUDOERS_FILE" > /dev/null 2>&1; then
    echo "✅ Tailscale sudo permissions configured successfully!"
    echo ""
    echo "You can now use these commands without password:"
    echo "  - sudo tailscale up"
    echo "  - sudo tailscale down"
    echo "  - sudo tailscale logout"
    echo "  - sudo tailscale status"
else
    echo "❌ Error: Invalid sudoers syntax"
    rm -f "$SUDOERS_FILE"
    exit 1
fi
