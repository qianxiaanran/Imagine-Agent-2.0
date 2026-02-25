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

echo Stopping listeners on ports 8080, 18001 and 18011...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ports=@(8080,18001,18011); foreach($port in $ports){$conns=Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue; if($conns){$procIds=$conns | Select-Object -ExpandProperty OwningProcess -Unique; foreach($procId in $procIds){try{Stop-Process -Id $procId -Force -ErrorAction Stop; Write-Host ('Stopped PID '+$procId+' on port '+$port)}catch{Write-Host ('Failed to stop PID '+$procId+': '+$_.Exception.Message)}}}else{Write-Host ('No listener on port '+$port)}}"

echo Cleaning possible extra launcher processes...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$targets=Get-CimInstance Win32_Process | Where-Object {($_.Name -eq 'python.exe' -and $_.CommandLine -like '*main.py*') -or ($_.Name -eq 'node.exe' -and $_.CommandLine -like '*tools\prod-server.mjs*')}; foreach($p in $targets){try{Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop; Write-Host ('Stopped extra PID '+$p.ProcessId)}catch{}}"

if exist "%ROOT%\supabase\config.toml" (
  echo Stopping local Supabase...
  pushd "%ROOT%" >nul
  call npx supabase stop >nul 2>&1
  popd >nul
)

echo Done.
exit /b 0
