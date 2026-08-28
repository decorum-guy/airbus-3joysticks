$ErrorActionPreference = "Stop"

Write-Host "Airbus 3 Joysticks - setup" -ForegroundColor Cyan

$python = $null
try {
    & py -3.12 --version *> $null
    if ($LASTEXITCODE -eq 0) { $python = @("py", "-3.12") }
} catch {}

if (-not $python) {
    try {
        & python --version *> $null
        if ($LASTEXITCODE -eq 0) { $python = @("python") }
    } catch {}
}

if (-not $python) {
    throw "Python was not found. Install 64-bit Python 3.12, then run this script again."
}

if (-not (Test-Path ".venv")) {
    if ($python.Count -eq 2) {
        & $python[0] $python[1] -m venv .venv
    } else {
        & $python[0] -m venv .venv
    }
}

$venvPython = Join-Path $PWD ".venv\Scripts\python.exe"
& $venvPython -m pip install --upgrade pip setuptools wheel
& $venvPython -m pip install -e ".[dev]"

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Run: .\scripts\run.ps1"
