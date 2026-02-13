@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo [1/3] Stopping running services...
call "%ROOT%\stop-prod.bat"

echo [2/3] Building frontend...
pushd "%ROOT%\frontend" || (
  echo [ERROR] Cannot enter frontend directory.
  exit /b 1
)

call npm install
if errorlevel 1 (
  echo [ERROR] npm install failed.
  popd
  exit /b 1
)

call npm run build
if errorlevel 1 (
  echo [ERROR] npm run build failed.
  popd
  exit /b 1
)
popd

echo [3/3] Starting production services...
call "%ROOT%\start-prod.bat"
if errorlevel 1 (
  echo [ERROR] start-prod failed.
  exit /b 1
)

echo.
echo Rebuild and restart completed.
exit /b 0
