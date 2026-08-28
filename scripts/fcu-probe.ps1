$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    Write-Host 'Virtual environment not found. Running setup first...' -ForegroundColor Yellow
    & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'setup.ps1')
}

if (-not (Test-Path $Python)) {
    throw "Python virtual environment was not created at $Python"
}

Set-Location $Root
Write-Host 'Starting focused A320 FCU SimConnect probe...' -ForegroundColor Cyan
Write-Host 'MSFS 2020 must already be loaded into the A320 cockpit.' -ForegroundColor DarkYellow
& $Python -m airbus3j.fcu_probe
exit $LASTEXITCODE
