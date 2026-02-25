param(
    [string]$RemoteDbUrl = "",
    [string]$RemoteSupabaseUrl = "",
    [string]$RemoteServiceRoleKey = "",
    [string]$NpmCache = "F:\codex-npm-cache",
    [switch]$SkipStorage,
    [switch]$SkipApiFallback
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ProjectRoot

function Run-Step {
    param(
        [string]$Description,
        [scriptblock]$Action
    )

    Write-Host "  - $Description"
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed (exit code $LASTEXITCODE)"
    }
}

$env:NPM_CONFIG_CACHE = $NpmCache

Write-Host "[1/6] Starting local Supabase in $ProjectRoot ..."
Run-Step "supabase start" { npx supabase start }

Write-Host "[2/6] Reading local Supabase env and writing project env files ..."
$statusLines = & npx supabase status -o env
if ($LASTEXITCODE -ne 0) {
    throw "supabase status failed (exit code $LASTEXITCODE)"
}

$local = @{}
foreach ($line in $statusLines) {
    if ($line -match '^([A-Z0-9_]+)="(.*)"$') {
        $local[$matches[1]] = $matches[2]
    }
}

if (-not $local["API_URL"] -or -not $local["ANON_KEY"] -or -not $local["SERVICE_ROLE_KEY"]) {
    throw "Cannot parse local supabase status output."
}

$backendEnvPath = Join-Path $ProjectRoot "Backend/.env.local"
$frontendEnvPath = Join-Path $ProjectRoot "frontend/.env.local"

$backendLines = @(
    "SUPABASE_URL=$($local['API_URL'])",
    "SUPABASE_ANON_KEY=$($local['ANON_KEY'])",
    "SUPABASE_SERVICE_ROLE_KEY=$($local['SERVICE_ROLE_KEY'])",
    "SUPABASE_DB_HOST=127.0.0.1",
    "SUPABASE_DB_PORT=54322",
    "SUPABASE_DB_USER=postgres",
    "SUPABASE_DB_PASSWORD=postgres",
    "SUPABASE_DB_NAME=postgres",
    "SUPABASE_DB_SSLMODE=disable"
)

$frontendLines = @(
    "VITE_SUPABASE_URL=$($local['API_URL'])",
    "VITE_SUPABASE_ANON_KEY=$($local['ANON_KEY'])"
)

Set-Content -Path $backendEnvPath -Value ($backendLines -join "`r`n") -Encoding UTF8
Set-Content -Path $frontendEnvPath -Value ($frontendLines -join "`r`n") -Encoding UTF8
Write-Host "  - wrote Backend/.env.local and frontend/.env.local"

$dbMigrated = $false

if (-not [string]::IsNullOrWhiteSpace($RemoteDbUrl)) {
    Write-Host "[3/6] Dumping/importing remote database by direct DB URL ..."

    try {
        $tempDir = Join-Path $ProjectRoot "supabase/.temp"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

        $schemaDump = Join-Path $tempDir "remote_public_schema.sql"
        $dataDump = Join-Path $tempDir "remote_data.sql"

        Run-Step "dump remote public schema" {
            npx supabase db dump --db-url "$RemoteDbUrl" --schema public --file "$schemaDump"
        }
        Run-Step "dump remote data (public/auth/storage)" {
            npx supabase db dump --db-url "$RemoteDbUrl" --data-only --schema public --schema auth --schema storage --use-copy --file "$dataDump"
        }

        Write-Host "[4/6] Applying DB dump into local Supabase ..."
        $configPath = Join-Path $ProjectRoot "supabase/config.toml"
        $projectMatch = Select-String -Path $configPath -Pattern '^project_id\s*=\s*"([^"]+)"'
        if (-not $projectMatch) {
            throw "Cannot parse project_id from supabase/config.toml"
        }
        $projectId = $projectMatch.Matches[0].Groups[1].Value
        $dbContainer = "supabase_db_$projectId"

        Run-Step "drop and recreate local public schema" {
            docker exec $dbContainer psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c "drop schema if exists public cascade; create schema public;"
        }
        Run-Step "copy schema dump into db container" {
            docker cp $schemaDump "${dbContainer}:/tmp/remote_public_schema.sql"
        }
        Run-Step "copy data dump into db container" {
            docker cp $dataDump "${dbContainer}:/tmp/remote_data.sql"
        }
        Run-Step "apply schema dump" {
            docker exec $dbContainer psql -U postgres -d postgres -v ON_ERROR_STOP=1 -f /tmp/remote_public_schema.sql
        }

        $truncateSql = @"
DO `$$
DECLARE
  r RECORD;
BEGIN
  FOR r IN
    SELECT schemaname, tablename
    FROM pg_tables
    WHERE schemaname IN ('public', 'auth', 'storage')
  LOOP
    EXECUTE format('TRUNCATE TABLE %I.%I CASCADE', r.schemaname, r.tablename);
  END LOOP;
END `$$;
"@

        Write-Host "  - truncate local data tables in public/auth/storage"
        $truncateSql | docker exec -i $dbContainer psql -U postgres -d postgres -v ON_ERROR_STOP=1
        if ($LASTEXITCODE -ne 0) {
            throw "truncate local data tables failed (exit code $LASTEXITCODE)"
        }

        Run-Step "apply data dump" {
            docker exec $dbContainer psql -U postgres -d postgres -v ON_ERROR_STOP=1 -f /tmp/remote_data.sql
        }

        $dbMigrated = $true
    }
    catch {
        Write-Warning "Direct DB migration failed: $($_.Exception.Message)"
    }
}
else {
    Write-Host "[3/6] RemoteDbUrl not provided, skipping direct DB dump/import."
}

if (-not $dbMigrated -and -not $SkipApiFallback) {
    if (-not [string]::IsNullOrWhiteSpace($RemoteSupabaseUrl) -and -not [string]::IsNullOrWhiteSpace($RemoteServiceRoleKey)) {
        Write-Host "[5/6] Running API fallback migration (public schema/data + auth users) ..."
        $pythonExe = Join-Path $ProjectRoot "Backend/.venv/Scripts/python.exe"
        if (Test-Path $pythonExe) {
            Run-Step "run API fallback migration" {
                & $pythonExe "tools/migrate_supabase_api_fallback.py" `
                    --remote-url "$RemoteSupabaseUrl" `
                    --remote-service-role-key "$RemoteServiceRoleKey" `
                    --local-url "$($local['API_URL'])" `
                    --local-service-role-key "$($local['SERVICE_ROLE_KEY'])" `
                    --local-db-url "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
            }
        }
        else {
            Run-Step "run API fallback migration" {
                python "tools/migrate_supabase_api_fallback.py" `
                    --remote-url "$RemoteSupabaseUrl" `
                    --remote-service-role-key "$RemoteServiceRoleKey" `
                    --local-url "$($local['API_URL'])" `
                    --local-service-role-key "$($local['SERVICE_ROLE_KEY'])" `
                    --local-db-url "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
            }
        }
    }
    else {
        Write-Warning "DB direct migration failed/skipped, and API fallback is unavailable because remote URL/key is missing."
    }
}
elseif (-not $dbMigrated -and $SkipApiFallback) {
    Write-Warning "DB direct migration failed/skipped, and API fallback is explicitly skipped."
}

if (-not $SkipStorage -and -not [string]::IsNullOrWhiteSpace($RemoteSupabaseUrl) -and -not [string]::IsNullOrWhiteSpace($RemoteServiceRoleKey)) {
    Write-Host "[6/6] Migrating Storage objects ..."
    $pythonExe = Join-Path $ProjectRoot "Backend/.venv/Scripts/python.exe"

    if (Test-Path $pythonExe) {
        Run-Step "run storage migration script" {
            & $pythonExe "tools/migrate_supabase_storage.py" `
                --remote-url "$RemoteSupabaseUrl" `
                --remote-service-role-key "$RemoteServiceRoleKey" `
                --local-url "$($local['API_URL'])" `
                --local-service-role-key "$($local['SERVICE_ROLE_KEY'])"
        }
    }
    else {
        Run-Step "run storage migration script" {
            python "tools/migrate_supabase_storage.py" `
                --remote-url "$RemoteSupabaseUrl" `
                --remote-service-role-key "$RemoteServiceRoleKey" `
                --local-url "$($local['API_URL'])" `
                --local-service-role-key "$($local['SERVICE_ROLE_KEY'])"
        }
    }
}
else {
    Write-Warning "Storage migration skipped (missing remote URL/key or SkipStorage=true)."
}

Write-Host "Completed."
