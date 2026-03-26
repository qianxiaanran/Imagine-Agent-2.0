@echo off
setlocal

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

if not defined NPM_CONFIG_CACHE (
  if exist "F:\" (
    set "NPM_CONFIG_CACHE=F:\codex-npm-cache"
    if not exist "%NPM_CONFIG_CACHE%" mkdir "%NPM_CONFIG_CACHE%" >nul 2>&1
  )
)

set "FRONTEND_PORT=%~1"
if not defined FRONTEND_PORT set "FRONTEND_PORT=8080"
if not defined FRONTEND_HOST set "FRONTEND_HOST=127.0.0.1"
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

set "OLLAMA_BASE_URL="
set "OLLAMA_NUM_PARALLEL="
set "OLLAMA_MAX_QUEUE="
if exist "%ROOT%\Backend\.env.local" (
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /i "OLLAMA_BASE_URL=" "%ROOT%\Backend\.env.local"`) do set "OLLAMA_BASE_URL=%%B"
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /i "OLLAMA_NUM_PARALLEL=" "%ROOT%\Backend\.env.local"`) do set "OLLAMA_NUM_PARALLEL=%%B"
  for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b /i "OLLAMA_MAX_QUEUE=" "%ROOT%\Backend\.env.local"`) do set "OLLAMA_MAX_QUEUE=%%B"
)
if not defined OLLAMA_BASE_URL set "OLLAMA_BASE_URL=http://127.0.0.1:11434"
if not defined OLLAMA_NUM_PARALLEL set "OLLAMA_NUM_PARALLEL=2"
if not defined OLLAMA_MAX_QUEUE set "OLLAMA_MAX_QUEUE=128"

call :refresh_ollama_hostport
set "OLLAMA_LOG=%ROOT%\.runtime\ollama-start.log"
if not exist "%ROOT%\.runtime" mkdir "%ROOT%\.runtime" >nul 2>&1

echo [0/4] Ensuring local Ollama is running...
echo [INFO] Ollama concurrency: parallel=%OLLAMA_NUM_PARALLEL%, max_queue=%OLLAMA_MAX_QUEUE%
curl.exe -fsS --max-time 2 "%OLLAMA_BASE_URL%/api/tags" >nul 2>&1
if errorlevel 1 (
  where ollama >nul 2>&1
  if errorlevel 1 (
    echo [WARN] Ollama not found in PATH. Local model may be unavailable.
  ) else (
    del "%OLLAMA_LOG%" >nul 2>&1
    start "Enterprise Ollama (%OLLAMA_HOSTPORT%)" /min cmd /c "set OLLAMA_HOST=%OLLAMA_HOSTPORT%&& set OLLAMA_NUM_PARALLEL=%OLLAMA_NUM_PARALLEL%&& set OLLAMA_MAX_QUEUE=%OLLAMA_MAX_QUEUE%&& ollama serve >> ""%OLLAMA_LOG%"" 2>&1"
    echo [INFO] Waiting for Ollama to become ready at %OLLAMA_BASE_URL%...
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$ok=$false; for($i=0;$i -lt 20;$i++){ try { Invoke-RestMethod -Method Get -Uri '%OLLAMA_BASE_URL%/api/tags' -TimeoutSec 2 | Out-Null; $ok=$true; break } catch { Start-Sleep -Seconds 1 } }; if(-not $ok){ exit 1 }"
    if errorlevel 1 (
      echo [WARN] Ollama did not become ready at %OLLAMA_BASE_URL%.
      if exist "%OLLAMA_LOG%" (
        echo [WARN] Recent Ollama log:
        powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-Content -Path '%OLLAMA_LOG%' -Tail 20"
      )
    ) else (
      echo [INFO] Ollama is ready at %OLLAMA_BASE_URL%.
    )
  )
) else (
  echo [INFO] Ollama already running at %OLLAMA_BASE_URL%.
  echo [INFO] If this instance was started without parallel settings, restart Ollama to apply new concurrency values.
)

if exist "%ROOT%\supabase\config.toml" (
  docker info >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Docker daemon is not running. Start Docker Desktop and retry.
    exit /b 1
  )
  where npx >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] npx not found in PATH.
    exit /b 1
  )

  echo [0/3] Ensuring local Supabase is running...
  pushd "%ROOT%" >nul
  curl.exe -sS --max-time 2 "http://127.0.0.1:54321/rest/v1/" >nul 2>&1
  if errorlevel 1 (
    call npx --yes supabase --version >nul 2>&1
    call npx --yes supabase start
    if errorlevel 1 (
      echo [WARN] supabase start failed. Retrying after cleanup...
      call npx --yes supabase stop
      timeout /t 1 /nobreak >nul
      call npx --yes supabase start
      if errorlevel 1 (
        echo [ERROR] Failed to start local Supabase.
        popd >nul
        exit /b 1
      )
    )
  ) else (
    echo [INFO] Supabase already running.
  )
  curl.exe -sS --max-time 2 "http://127.0.0.1:54321/rest/v1/" >nul 2>&1
  if errorlevel 1 (
    echo [ERROR] Supabase API is not reachable on 127.0.0.1:54321.
    popd >nul
    exit /b 1
  )
  popd >nul
) else (
  echo [WARN] supabase\config.toml not found. Skipping local Supabase startup.
)

echo [1/2] Checking backend on %BACKEND_PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "if (Get-NetTCPConnection -State Listen -LocalPort %BACKEND_PORT% -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo [1/2] Starting backend on %BACKEND_PORT%...
  start "Enterprise Backend (%BACKEND_PORT%)" cmd /k "cd /d ""%ROOT%\Backend"" && set PYTHONUTF8=1 && set BACKEND_PORT=%BACKEND_PORT% && set OLLAMA_BASE_URL=%OLLAMA_BASE_URL% && set OLLAMA_API_BASE=%OLLAMA_BASE_URL% && .venv\Scripts\python.exe -X utf8 main.py"
) else (
  echo [INFO] Backend already listening on %BACKEND_PORT%, skip start.
)

echo [2/2] Checking frontend on %FRONTEND_PORT%...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "if (Get-NetTCPConnection -State Listen -LocalPort %FRONTEND_PORT% -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo [2/2] Starting frontend prod server on %FRONTEND_PORT%...
  start "Enterprise Frontend (%FRONTEND_PORT%)" cmd /k "cd /d ""%ROOT%"" && set PORT=%FRONTEND_PORT% && set FRONTEND_HOST=%FRONTEND_HOST% && set API_TARGET=%API_TARGET% && node tools\prod-server.mjs"
) else (
  echo [INFO] Frontend already listening on %FRONTEND_PORT%, skip start.
)

echo.
echo Started.
echo Frontend URL: http://%FRONTEND_HOST%:%FRONTEND_PORT%
echo Backend URL : http://127.0.0.1:%BACKEND_PORT%
echo Ollama URL  : %OLLAMA_BASE_URL%
echo Supabase API: http://127.0.0.1:54321
echo Supabase Studio: http://127.0.0.1:54323
echo.
exit /b 0

:refresh_ollama_hostport
set "OLLAMA_HOSTPORT=127.0.0.1:11434"
for /f "usebackq delims=" %%A in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$u=[uri]'%OLLAMA_BASE_URL%'; Write-Output ($u.Host + ':' + $u.Port)"`) do set "OLLAMA_HOSTPORT=%%A"
goto :eof
