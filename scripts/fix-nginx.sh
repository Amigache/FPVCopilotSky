#!/bin/bash
# Quick Fix - Disable nginx default site
# Run this if you see "Welcome to nginx" instead of FPV Copilot Sky

echo "🔧 Fixing nginx configuration..."

# Disable default site
if [ -L /etc/nginx/sites-enabled/default ]; then
    sudo rm /etc/nginx/sites-enabled/default
    echo "✅ Default nginx site disabled"
else
    echo "ℹ️  Default site is already disabled"
fi

# Reload nginx
sudo systemctl reload nginx
echo "✅ Nginx reloaded"

# Verify
if curl -s http://localhost/ | grep -q "root"; then
    echo "✅ Frontend is now being served"
else
    echo "⚠️  Frontend may not be loading correctly"
    echo "   Check that frontend build exists:"
    echo "   ls -la /opt/FPVCopilotSky/frontend/client/dist/"
fi
