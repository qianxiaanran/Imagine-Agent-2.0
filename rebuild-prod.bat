@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "STOP_ARGS=--keep-supabase"
if /i "%~1"=="--full" set "STOP_ARGS="
set "NEED_NPM_INSTALL=1"

echo [1/3] Stopping running services...
call "%ROOT%\stop-prod.bat" %STOP_ARGS%

echo [2/3] Building frontend...
pushd "%ROOT%\frontend" || (
  echo [ERROR] Cannot enter frontend directory.
  exit /b 1
)

set "NEED_NPM_INSTALL=1"
if exist "node_modules" (
  call :check_lock_match
)

if "%NEED_NPM_INSTALL%"=="1" (
  echo [INFO] Installing frontend dependencies ^(lock changed or node_modules missing^)...
  call npm install --no-audit --no-fund --prefer-offline
  if errorlevel 1 (
    echo [ERROR] npm install failed.
    popd
    exit /b 1
  )
  call :write_lock_stamp
) else (
  echo [INFO] package-lock unchanged, skip npm install.
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
if defined STOP_ARGS (
  echo Rebuild and restart completed. ^(fast mode, Supabase kept running^)
) else (
  echo Rebuild and restart completed. ^(full mode^)
)
exit /b 0

:check_lock_match
powershell -NoProfile -ExecutionPolicy Bypass -Command "$lock='package-lock.json'; $stamp='node_modules/.deps-lock.sha256'; if ((Test-Path $lock) -and (Test-Path $stamp)) { $a=(Get-FileHash -Algorithm SHA256 $lock).Hash.Trim(); $b=(Get-Content $stamp -Raw).Trim(); if ($a -eq $b) { exit 0 } }; exit 1"
if not errorlevel 1 set "NEED_NPM_INSTALL=0"
goto :eof

:write_lock_stamp
powershell -NoProfile -ExecutionPolicy Bypass -Command "$lock='package-lock.json'; $stamp='node_modules/.deps-lock.sha256'; if (Test-Path $lock) { (Get-FileHash -Algorithm SHA256 $lock).Hash | Set-Content -Path $stamp -NoNewline }"
goto :eof
