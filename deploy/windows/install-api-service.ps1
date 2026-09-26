<#
  Install the FastAPI backend as a Windows service (run as Administrator on the server).

  Uses NSSM (https://nssm.cc) to run uvicorn as a service that starts with Windows and restarts if it stops.
  Before running: backend\.venv exists (python -m venv backend\.venv; backend\.venv\Scripts\pip install -r
  backend\requirements.txt) and backend\.env holds DATABASE_URL (see deploy\README.md).

  .\install-api-service.ps1 -Nssm C:\tools\nssm\win64\nssm.exe
#>
param(
    [Parameter(Mandatory = $true)] [string] $Nssm,
    [string] $ServiceName = 'SchoolPlanningAPI',
    [string] $Backend = (Resolve-Path "$PSScriptRoot\..\..\backend").Path,
    [int] $Port = 8000
)
$ErrorActionPreference = 'Stop'
$python = Join-Path $Backend '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "Missing $python - create the virtual environment first." }
if (-not (Test-Path (Join-Path $Backend '.env'))) { throw "Missing $Backend\.env with DATABASE_URL." }

# Database tables up to date before the service starts
Push-Location $Backend
& $python -m alembic upgrade head
Pop-Location

$logs = Join-Path $Backend 'logs'
New-Item -ItemType Directory -Force $logs | Out-Null
& $Nssm install $ServiceName $python "-m uvicorn app.main:app --host 127.0.0.1 --port $Port --proxy-headers"
& $Nssm set $ServiceName AppDirectory $Backend
& $Nssm set $ServiceName DisplayName 'School planning API (FastAPI)'
& $Nssm set $ServiceName Start SERVICE_AUTO_START
& $Nssm set $ServiceName AppStdout (Join-Path $logs 'api.log')
& $Nssm set $ServiceName AppStderr (Join-Path $logs 'api.log')
& $Nssm set $ServiceName AppRotateFiles 1
& $Nssm set $ServiceName AppRotateBytes 10485760
& $Nssm start $ServiceName
Write-Host "Service $ServiceName started. Check: http://127.0.0.1:$Port/api/health"
