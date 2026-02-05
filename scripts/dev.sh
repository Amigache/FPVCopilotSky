#!/bin/bash
# FPV Copilot Sky - Development Mode
# Run backend and frontend in development mode with hot reload

set -e

echo "🛠️  FPV Copilot Sky - Development Mode"
echo "======================================"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Check if production service is running on port 8000
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo -e "${YELLOW}⚠️  Port 8000 is already in use (production service running?)${NC}"
    echo -e "   Using alternative port 8001 for development backend"
    BACKEND_PORT=8001
else
    BACKEND_PORT=8000
fi

# Function to cleanup background processes on exit
cleanup() {
    echo -e "\n${YELLOW}🛑 Stopping development servers...${NC}"
    jobs -p | xargs -r kill 2>/dev/null || true
    exit 0
}

trap cleanup EXIT INT TERM

echo -e "\n${BLUE}🐍 Starting backend (port $BACKEND_PORT) with hot reload...${NC}"
cd "$PROJECT_DIR"
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port $BACKEND_PORT --reload &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

echo -e "${GREEN}✅ Backend running on http://localhost:$BACKEND_PORT${NC}"
echo -e "   API docs: ${BLUE}http://localhost:$BACKEND_PORT/docs${NC}"

echo -e "\n${BLUE}⚛️  Starting frontend (port 5173) with hot reload...${NC}"
cd "$PROJECT_DIR/frontend/client"

# Update API base URL for development if needed
if [ $BACKEND_PORT -ne 8000 ]; then
    echo -e "${YELLOW}   Note: Backend is on port $BACKEND_PORT${NC}"
    echo -e "   Make sure frontend connects to the right port"
fi

npm run dev &
FRONTEND_PID=$!

echo -e "\n${GREEN}✅ Development servers started!${NC}"
echo -e "\n📋 Access points:"
echo -e "   Frontend: ${GREEN}http://localhost:5173${NC}"
echo -e "   Backend:  ${GREEN}http://localhost:$BACKEND_PORT${NC}"
echo -e "   API Docs: ${BLUE}http://localhost:$BACKEND_PORT/docs${NC}"

echo -e "\n💡 Tips:"
echo -e "   - Both servers have hot reload enabled"
echo -e "   - Frontend will auto-open in browser"
echo -e "   - Press Ctrl+C to stop both servers"
echo -e "   - Backend logs will appear in this terminal"

echo -e "\n${YELLOW}📝 Watching for changes...${NC}\n"

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
