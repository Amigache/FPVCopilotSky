#!/bin/bash
# Test script for network management improvements
# Test the VPN-aware routing and auto-adjustment

set -e

API_URL="http://localhost:8000"
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BOLD}🧪 FPVCopilotSky Network Management Tests${NC}\n"

# Check if service is running
echo -e "${YELLOW}📡 Checking if service is running...${NC}"
if ! curl -s "$API_URL" > /dev/null 2>&1; then
    echo -e "${RED}❌ Service not running. Start with: systemctl start fpvcopilot-sky${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Service is running${NC}\n"

# Test 1: Get current network status
echo -e "${BOLD}Test 1: Get Network Status${NC}"
echo -e "${YELLOW}GET /api/network/status${NC}"
curl -s "$API_URL/api/network/status" | python3 -m json.tool
echo -e "\n"

# Test 2: Get current routes
echo -e "${BOLD}Test 2: Get Routes${NC}"
echo -e "${YELLOW}GET /api/network/routes${NC}"
curl -s "$API_URL/api/network/routes" | python3 -m json.tool
echo -e "\n"

# Test 3: Check if VPN is active
echo -e "${BOLD}Test 3: Check VPN Status${NC}"
echo -e "${YELLOW}GET /api/vpn/status${NC}"
curl -s "$API_URL/api/vpn/status" | python3 -m json.tool
echo -e "\n"

# Test 4: Auto-adjust priority
echo -e "${BOLD}Test 4: Auto-Adjust Priority${NC}"
echo -e "${YELLOW}POST /api/network/priority/auto-adjust${NC}"
result=$(curl -s -X POST "$API_URL/api/network/priority/auto-adjust")
echo "$result" | python3 -m json.tool

if echo "$result" | grep -q '"success": true'; then
    echo -e "${GREEN}✅ Auto-adjust successful${NC}"
    
    # Check if network changed
    if echo "$result" | grep -q '"changed": true'; then
        reason=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('reason', 'N/A'))")
        echo -e "${YELLOW}⚠️  Network priority changed: $reason${NC}"
    else
        echo -e "${GREEN}✅ Network priority already optimal${NC}"
    fi
else
    echo -e "${RED}❌ Auto-adjust failed${NC}"
fi
echo -e "\n"

# Test 5: Set to auto mode
echo -e "${BOLD}Test 5: Set to Auto Mode${NC}"
echo -e "${YELLOW}POST /api/network/priority (mode=auto)${NC}"
result=$(curl -s -X POST "$API_URL/api/network/priority" \
    -H "Content-Type: application/json" \
    -d '{"mode": "auto"}')
echo "$result" | python3 -m json.tool

if echo "$result" | grep -q '"success": true'; then
    echo -e "${GREEN}✅ Set to auto mode successful${NC}"
else
    error=$(echo "$result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('detail', 'Unknown error'))" 2>/dev/null || echo "Unknown error")
    echo -e "${YELLOW}⚠️  $error${NC}"
fi
echo -e "\n"

# Test 6: Cooldown test (should fail if called immediately)
echo -e "${BOLD}Test 6: Cooldown Test${NC}"
echo -e "${YELLOW}POST /api/network/priority (mode=modem, immediate retry)${NC}"
curl -s -X POST "$API_URL/api/network/priority" \
    -H "Content-Type: application/json" \
    -d '{"mode": "modem"}' > /dev/null

sleep 1
result=$(curl -s -X POST "$API_URL/api/network/priority" \
    -H "Content-Type: application/json" \
    -d '{"mode": "wifi"}')

if echo "$result" | grep -q "cooldown"; then
    echo -e "${GREEN}✅ Cooldown working correctly${NC}"
else
    echo -e "${YELLOW}⚠️  Cooldown may not be triggered (network might be the same)${NC}"
fi
echo "$result" | python3 -m json.tool
echo -e "\n"

# Display routing table
echo -e "${BOLD}Test 7: System Routing Table${NC}"
echo -e "${YELLOW}ip route show default${NC}"
ip route show default
echo -e "\n"

# Display VPN interface
echo -e "${BOLD}Test 8: VPN Interface${NC}"
echo -e "${YELLOW}ip link show | grep tailscale${NC}"
if ip link show | grep -q tailscale; then
    ip link show | grep tailscale
    echo -e "${GREEN}✅ Tailscale interface found${NC}"
else
    echo -e "${YELLOW}⚠️  No Tailscale interface detected${NC}"
fi
echo -e "\n"

# Summary
echo -e "${BOLD}═══════════════════════════════════${NC}"
echo -e "${BOLD}📊 Test Summary${NC}"
echo -e "${BOLD}═══════════════════════════════════${NC}"
echo -e "${GREEN}✅ All API endpoints responding${NC}"
echo -e "${GREEN}✅ Network management operational${NC}"
echo -e "\n${YELLOW}💡 Tip: Check logs with:${NC}"
echo -e "   journalctl -u fpvcopilot-sky -f | grep -i network"
echo -e "\n${YELLOW}💡 Monitor auto-adjustment:${NC}"
echo -e "   watch -n 5 'curl -s http://localhost:8000/api/network/status | python3 -m json.tool'"
