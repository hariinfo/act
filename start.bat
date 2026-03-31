@echo off
REM Start both backend and frontend for the ACT Practice Test App
REM Works on native Windows (no Git Bash required)

set SCRIPT_DIR=%~dp0

echo Checking for existing processes...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Killing existing process on port 8000 (PID: %%a)
    taskkill /F /PID %%a >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173" ^| findstr "LISTENING"') do (
    echo Killing existing process on port 5173 (PID: %%a)
    taskkill /F /PID %%a >nul 2>&1
)

echo Starting backend (FastAPI)...
start "ACT Backend" cmd /c "cd /d %SCRIPT_DIR%backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

echo Starting frontend (Vite)...
start "ACT Frontend" cmd /c "cd /d %SCRIPT_DIR%frontend && npm run dev"

echo.
echo Backend running at http://localhost:8000
echo Frontend running at http://localhost:5173
echo.
echo Close the "ACT Backend" and "ACT Frontend" windows to stop the servers.
pause
