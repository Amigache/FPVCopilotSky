#!/bin/bash
# FPV Copilot Sky - Production Deployment Script
# This script builds the frontend and deploys the application for production

set -e

echo "🚀 FPV Copilot Sky - Production Deployment"
echo "==========================================="

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Resolve the actual invoking user (handles: sudo bash deploy.sh, bash deploy.sh, root)
ACTUAL_USER="${SUDO_USER:-$USER}"

cd "$PROJECT_DIR"

# Ensure local data directory exists
echo -e "\n${BLUE}📁 Ensuring data directory...${NC}"
DATA_DIR="/var/lib/fpvcopilot-sky"
sudo mkdir -p "$DATA_DIR"

# Set proper ownership if fpvcopilotsky user exists
if id "fpvcopilotsky" &>/dev/null; then
    sudo chown fpvcopilotsky:fpvcopilotsky "$DATA_DIR"
else
    # Fallback: use current user or www-data
    if [ -n "$SUDO_USER" ]; then
        sudo chown "$SUDO_USER:$SUDO_USER" "$DATA_DIR"
    else
        sudo chown www-data:www-data "$DATA_DIR"
    fi
fi
sudo chmod 755 "$DATA_DIR"

# Initialize version file if it doesn't exist
if [ ! -f "$DATA_DIR/version" ]; then
    # Get version from git tag on current HEAD
    if INITIAL_VERSION=$(git describe --tags --exact-match HEAD 2>/dev/null | sed 's/^v//'); then
        echo -e "${GREEN}✅ Version detected from git tag: $INITIAL_VERSION${NC}"
    else
        INITIAL_VERSION="unknown"
        echo -e "${YELLOW}⚠️  No git tag on HEAD, version set to 'unknown'${NC}"
    fi
    echo "$INITIAL_VERSION" > "$DATA_DIR/version.tmp"
    sudo mv "$DATA_DIR/version.tmp" "$DATA_DIR/version"

    # Set proper ownership
    if id "fpvcopilotsky" &>/dev/null; then
        sudo chown fpvcopilotsky:fpvcopilotsky "$DATA_DIR/version"
    else
        if [ -n "$SUDO_USER" ]; then
            sudo chown "$SUDO_USER:$SUDO_USER" "$DATA_DIR/version"
        else
            sudo chown www-data:www-data "$DATA_DIR/version"
        fi
    fi
    echo -e "${GREEN}✅ Version file initialized: $INITIAL_VERSION${NC}"
else
    echo -e "${GREEN}✅ Version file already exists${NC}"
fi

# Step 1: Build Frontend
echo -e "\n${BLUE}📦 Building frontend...${NC}"
cd frontend/client
npm run build
# Fix ownership so the service user (fpvcopilotsky) can overwrite dist on future updates
if id "fpvcopilotsky" &>/dev/null; then
    chown -R fpvcopilotsky:fpvcopilotsky dist
elif [ -n "$SUDO_USER" ]; then
    chown -R "$SUDO_USER:$SUDO_USER" dist
fi
echo -e "${GREEN}✅ Frontend built successfully${NC}"

# Step 2: Install systemd service
echo -e "\n${BLUE}🔧 Installing systemd service...${NC}"
sudo cp "$PROJECT_DIR/systemd/fpvcopilot-sky.service" /etc/systemd/system/
sudo systemctl daemon-reload
echo -e "${GREEN}✅ Systemd service installed${NC}"

# Step 3: Setup nginx if installed
if command -v nginx &> /dev/null; then
    echo -e "\n${BLUE}🌐 Configuring nginx...${NC}"

    # Backup existing config if it exists
    if [ -f /etc/nginx/sites-available/fpvcopilot-sky ]; then
        sudo cp /etc/nginx/sites-available/fpvcopilot-sky /etc/nginx/sites-available/fpvcopilot-sky.backup
    fi

    # Copy nginx config with production optimizations:
    # - Uses 127.0.0.1 instead of localhost (avoids IPv6 resolution issues)
    # - Optimized timeouts for API (10s) and WebSocket (7d)
    sudo cp "$PROJECT_DIR/systemd/fpvcopilot-sky.nginx" /etc/nginx/sites-available/fpvcopilot-sky

    # Enable FPV site
    sudo ln -sf /etc/nginx/sites-available/fpvcopilot-sky /etc/nginx/sites-enabled/

    # IMPORTANT: Disable default nginx site to prevent it from interfering
    if [ -L /etc/nginx/sites-enabled/default ]; then
        echo -e "${YELLOW}Disabling default nginx site...${NC}"
        sudo rm /etc/nginx/sites-enabled/default
    fi

    # Fix permissions for frontend build:
    # - Owner: ACTUAL_USER so the dev user can rebuild without sudo
    # - Group: fpvcopilotsky (if it exists) so the service can overwrite files during git-based updates
    # - Mode: 775/664 so group members can write; other (nginx/www-data) gets read-only
    if id "fpvcopilotsky" &>/dev/null; then
        sudo chown -R "$ACTUAL_USER:fpvcopilotsky" "$PROJECT_DIR/frontend/client/dist"
    else
        sudo chown -R "$ACTUAL_USER:$ACTUAL_USER" "$PROJECT_DIR/frontend/client/dist"
    fi
    sudo chmod -R 775 "$PROJECT_DIR/frontend/client/dist"
    sudo find "$PROJECT_DIR/frontend/client/dist" -type f -exec chmod 664 {} \;

    # Test nginx config
    if sudo nginx -t; then
        echo -e "${GREEN}✅ Nginx configuration is valid${NC}"
        sudo systemctl reload nginx
        echo -e "${GREEN}✅ Nginx reloaded${NC}"
    else
        echo -e "${YELLOW}⚠️  Nginx config test failed, please check manually${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  Nginx not installed, skipping web server configuration${NC}"
    echo -e "   Install nginx: sudo apt-get install nginx"
fi

# Step 4: Enable and start service
echo -e "\n${BLUE}🚀 Starting service...${NC}"
sudo systemctl enable fpvcopilot-sky.service
sudo systemctl restart fpvcopilot-sky.service

# Wait for service to fully start (backend typically ready in ~25s)
echo -e "\n${BLUE}🏥 Health check...${NC}"

HEALTH_OK=false
MAX_WAIT=60
INTERVAL=2
ELAPSED=0
while [ "$ELAPSED" -lt "$MAX_WAIT" ]; do
    if curl -s --connect-timeout 2 http://127.0.0.1:8000/api/status/health > /dev/null 2>&1; then
        HEALTH_OK=true
        echo -e "   Backend ready in ${ELAPSED}s"
        break
    fi
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
    echo -e "   Waiting for backend... (${ELAPSED}s / ${MAX_WAIT}s max)"
done

# Step 5: Health check results
if $HEALTH_OK; then
    echo -e "${GREEN}✅${NC} Backend API is responding"
else
    echo -e "${RED}❌${NC} Backend API is NOT responding"
    echo -e "   Check logs: ${BLUE}sudo journalctl -u fpvcopilot-sky -f${NC}"
fi

# Check nginx/frontend (use 127.0.0.1 to avoid IPv6 resolution issues)
if curl -s --connect-timeout 5 http://127.0.0.1/ > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} Frontend is being served"
else
    echo -e "${RED}❌${NC} Frontend is NOT being served"
fi

# Step 6: Show status
echo -e "\n${BLUE}📊 Service status:${NC}"
sudo systemctl status fpvcopilot-sky.service --no-pager -l

echo -e "\n${GREEN}✅ Deployment complete!${NC}"
echo -e "\n📋 Service commands:"
echo -e "   Status:  ${BLUE}sudo systemctl status fpvcopilot-sky${NC}"
echo -e "   Logs:    ${BLUE}sudo journalctl -u fpvcopilot-sky -f${NC}"
echo -e "   Restart: ${BLUE}sudo systemctl restart fpvcopilot-sky${NC}"
echo -e "   Stop:    ${BLUE}sudo systemctl stop fpvcopilot-sky${NC}"

if command -v nginx &> /dev/null; then
    echo -e "\n🌐 Application is available at:"
    echo -e "   ${GREEN}http://$(hostname -I | awk '{print $1}')${NC}"
else
    echo -e "\n🌐 Backend is running on port 8000"
    echo -e "   ${GREEN}http://$(hostname -I | awk '{print $1}'):8000${NC}"
fi

echo -e "\n💡 Development mode:"
echo -e "   You can still develop in parallel using different ports:"
echo -e "   - Backend dev: python3 app/main.py (uses port 8000 - will conflict)"
echo -e "   - Or use: uvicorn app.main:app --port 8001 --reload"
echo -e "   - Frontend dev: cd frontend/client && npm run dev (port 5173)"
