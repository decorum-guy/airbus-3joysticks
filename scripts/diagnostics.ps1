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
Write-Host 'Starting Airbus 3 Joysticks guided diagnostics...' -ForegroundColor Cyan
Write-Host 'Do not run scripts\run.ps1 at the same time.' -ForegroundColor DarkYellow
& $Python -m airbus3j.diagnostics
exit $LASTEXITCODE
