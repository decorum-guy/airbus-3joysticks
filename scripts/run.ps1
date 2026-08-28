$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root '.venv\Scripts\python.exe'

if (-not (Test-Path $Python)) {
    Write-Host 'Virtual environment not found. Running setup...' -ForegroundColor Yellow
    & powershell -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'setup.ps1')
}

if (-not (Test-Path $Python)) {
    throw "Python virtual environment was not created at $Python"
}

Set-Location $Root
Write-Host 'Starting Airbus 3 Joysticks...' -ForegroundColor Cyan
Write-Host 'Press Ctrl+C to stop.' -ForegroundColor DarkGray
& $Python -m airbus3j
exit $LASTEXITCODE
