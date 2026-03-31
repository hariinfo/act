#!/bin/bash
# Start both backend and frontend for the ACT Practice Test App
# Works on macOS and Linux (and Windows Git Bash)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Detect OS for platform-specific commands
kill_port() {
  local port=$1
  if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" || "$OSTYPE" == "win32" ]]; then
    # Windows (Git Bash / MSYS2)
    pid=$(netstat -ano 2>/dev/null | grep ":$port " | grep LISTENING | awk '{print $5}' | head -1)
    if [ -n "$pid" ] && [ "$pid" != "0" ]; then
      echo "Killing existing process on port $port (PID: $pid)"
      taskkill //F //PID "$pid" 2>/dev/null
    fi
  else
    # macOS / Linux
    pid=$(lsof -ti :"$port" 2>/dev/null)
    if [ -n "$pid" ]; then
      echo "Killing existing process on port $port (PID: $pid)"
      kill -9 "$pid" 2>/dev/null
    fi
  fi
}

echo "Checking for existing processes..."
kill_port 8000
kill_port 5173

# Start backend
echo "Starting backend (FastAPI)..."
cd "$SCRIPT_DIR/backend"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend
echo "Starting frontend (Vite)..."
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Backend running at http://localhost:8000"
echo "Frontend running at http://localhost:5173"
echo ""
echo "Press Ctrl+C to stop both servers."

# Trap Ctrl+C to kill both processes
trap "echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

# Wait for both
wait
