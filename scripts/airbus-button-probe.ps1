$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "Virtual environment not found; running setup first..." -ForegroundColor Yellow
    & (Join-Path $PSScriptRoot "setup.ps1")
}

if (-not (Test-Path $VenvPython)) {
    throw "Virtual environment was not created successfully."
}

Write-Host "The original H-event probe is retired. Running stock A320 button probe v2 instead..." -ForegroundColor Yellow

Push-Location $RepoRoot
try {
    & $VenvPython -m airbus3j.stock_airbus_probe
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Pop-Location
}
