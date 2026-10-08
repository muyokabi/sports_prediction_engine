$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot

$Executable = Join-Path $ProjectRoot ".venv\Scripts\sports-engine.exe"
if (-not (Test-Path -LiteralPath $Executable)) {
    Write-Error "sports-engine executable is missing. Run uv sync --all-groups first."
    exit 2
}

& $Executable daily
exit $LASTEXITCODE
