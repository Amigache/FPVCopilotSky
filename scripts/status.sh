#!/bin/bash
# Quick Status Check - FPV Copilot Sky
# Verifica el estado de todos los componentes

echo "🔍 FPV Copilot Sky - Status Check"
echo "=================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

check_service() {
    local service=$1
    if systemctl is-active --quiet $service; then
        echo -e "${GREEN}✅${NC} $service is running"
        return 0
    else
        echo -e "${RED}❌${NC} $service is NOT running"
        return 1
    fi
}

check_port() {
    local port=$1
    local name=$2
    # Use ss (doesn't require sudo) instead of lsof
    if ss -tlnp 2>/dev/null | grep -q ":$port "; then
        echo -e "${GREEN}✅${NC} Port $port ($name) is listening"
        return 0
    else
        echo -e "${RED}❌${NC} Port $port ($name) is NOT listening"
        return 1
    fi
}

echo -e "\n${BLUE}📋 System Services${NC}"
check_service fpvcopilot-sky
BACKEND_RUNNING=$?
check_service nginx
NGINX_RUNNING=$?

echo -e "\n${BLUE}🔌 Network Ports${NC}"
check_port 80 "Nginx"
check_port 8000 "Backend API"

echo -e "\n${BLUE}📁 Files & Directories${NC}"
if [ -d "/opt/FPVCopilotSky/frontend/client/dist" ] && [ "$(ls -A /opt/FPVCopilotSky/frontend/client/dist 2>/dev/null)" ]; then
    echo -e "${GREEN}✅${NC} Frontend build exists"
else
    echo -e "${YELLOW}⚠️${NC}  Frontend build NOT found (run: npm run build)"
fi

if [ -f "/opt/FPVCopilotSky/venv/bin/python3" ]; then
    echo -e "${GREEN}✅${NC} Python virtual environment exists"
else
    echo -e "${RED}❌${NC} Python virtual environment NOT found"
fi

echo -e "\n${BLUE}🌐 Connectivity${NC}"
# Use 127.0.0.1 to avoid IPv6 resolution issues with localhost
BACKEND_URL="http://127.0.0.1:8000/api/status/health"
if curl -s -f --connect-timeout 5 "$BACKEND_URL" > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} Backend API responding"
else
    echo -e "${RED}❌${NC} Backend API NOT responding"
fi

if [ $NGINX_RUNNING -eq 0 ]; then
    NGINX_URL="http://127.0.0.1/"
    if curl -s -f --connect-timeout 5 "$NGINX_URL" > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC} Nginx serving frontend"
    else
        echo -e "${YELLOW}⚠️${NC}  Nginx running but not serving correctly"
    fi
fi

echo -e "\n${BLUE}💾 Logs Location${NC}"
echo "   Backend: sudo journalctl -u fpvcopilot-sky -f"
echo "   Nginx:   sudo tail -f /var/log/nginx/fpvcopilot-sky-*.log"

echo -e "\n${BLUE}📊 Quick Stats${NC}"
if [ $BACKEND_RUNNING -eq 0 ]; then
    PID=$(systemctl show -p MainPID --value fpvcopilot-sky)
    if [ "$PID" != "0" ]; then
        MEM=$(ps -p $PID -o rss= | awk '{print int($1/1024)"MB"}')
        CPU=$(ps -p $PID -o %cpu= | awk '{print $1"%"}')
        echo "   Backend PID: $PID"
        echo "   Memory: $MEM"
        echo "   CPU: $CPU"
    fi
fi

echo -e "\n${BLUE}🌍 Access URLs${NC}"
IP=$(hostname -I | awk '{print $1}')
echo "   Local:      http://localhost"
echo "   Network:    http://$IP"
echo "   Backend:    http://$IP:8000"
echo "   API Docs:   http://$IP:8000/docs"

echo -e "\n${BLUE}⚡ Quick Actions${NC}"
echo "   Start:   sudo systemctl start fpvcopilot-sky"
echo "   Stop:    sudo systemctl stop fpvcopilot-sky"
echo "   Restart: sudo systemctl restart fpvcopilot-sky"
echo "   Logs:    sudo journalctl -u fpvcopilot-sky -f"
echo "   Deploy:  bash scripts/deploy.sh"

if [ $BACKEND_RUNNING -eq 0 ] && [ $NGINX_RUNNING -eq 0 ]; then
    echo -e "\n${GREEN}✅ System is operational!${NC}"
else
    echo -e "\n${YELLOW}⚠️  Some components are not running${NC}"
    echo "   Run: bash scripts/deploy.sh"
fi
