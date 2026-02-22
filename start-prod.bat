@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

set "FRONTEND_PORT=%~1"
if not defined FRONTEND_PORT set "FRONTEND_PORT=8080"
set "BACKEND_PORT=%~2"
if not defined BACKEND_PORT set "BACKEND_PORT=18011"
set "API_TARGET=http://127.0.0.1:%BACKEND_PORT%"

where node >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Node.js not found in PATH.
  exit /b 1
)

if not exist "%ROOT%\Backend\.venv\Scripts\python.exe" (
  echo [ERROR] Missing backend venv python: "%ROOT%\Backend\.venv\Scripts\python.exe"
  exit /b 1
)

if not exist "%ROOT%\tools\prod-server.mjs" (
  echo [ERROR] Missing prod server script: "%ROOT%\tools\prod-server.mjs"
  exit /b 1
)

if not exist "%ROOT%\frontend\dist\index.html" (
  echo [WARN] frontend\dist not found. Run rebuild-prod.bat first.
)

echo [1/2] Starting backend on %BACKEND_PORT%...
start "Enterprise Backend (%BACKEND_PORT%)" cmd /k "cd /d ""%ROOT%\Backend"" && set PYTHONUTF8=1 && set BACKEND_PORT=%BACKEND_PORT% && .venv\Scripts\python.exe -X utf8 main.py"

echo [2/2] Starting frontend prod server on %FRONTEND_PORT%...
start "Enterprise Frontend (%FRONTEND_PORT%)" cmd /k "cd /d ""%ROOT%"" && set PORT=%FRONTEND_PORT% && set API_TARGET=%API_TARGET% && node tools\prod-server.mjs"

echo.
echo Started.
echo Frontend URL: http://127.0.0.1:%FRONTEND_PORT%
echo Backend URL : http://127.0.0.1:%BACKEND_PORT%
echo.
exit /b 0
