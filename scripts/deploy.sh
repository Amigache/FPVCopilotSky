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

cd "$PROJECT_DIR"

# Step 1: Build Frontend
echo -e "\n${BLUE}📦 Building frontend...${NC}"
cd frontend/client
npm run build
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
    
    # Fix permissions for frontend build
    # dist/ is owned by hector (can rebuild) and www-data (can read)
    sudo chown -R hector:www-data "$PROJECT_DIR/frontend/client/dist"
    sudo chmod -R 755 "$PROJECT_DIR/frontend/client/dist"
    
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

# Wait for service to fully start (backend takes ~6s to init due to serial port scanning)
sleep 8

# Step 5: Health check
echo -e "\n${BLUE}🏥 Health check...${NC}"

# Check backend (use 127.0.0.1 to avoid IPv6 resolution issues with localhost)
if curl -s --connect-timeout 5 http://127.0.0.1:8000/api/status/health > /dev/null 2>&1; then
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
