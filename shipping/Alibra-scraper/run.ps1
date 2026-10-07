$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

$logPath = Join-Path $ScriptDir "run.log"
function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $logPath -Value $line -Encoding utf8
}

# Find python: prefer venv, fall back to py launcher, then python on PATH.
$python = $null
if (Test-Path (Join-Path $ScriptDir ".venv\Scripts\python.exe")) {
    $python = Join-Path $ScriptDir ".venv\Scripts\python.exe"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
} else {
    Write-Log "ERROR: no Python interpreter found (need venv, py launcher, or python on PATH)"
    exit 2
}

Write-Log "==== alibra scraper run ===="
Write-Log "python: $python"

Write-Log "step 1/2: fetch.py"
& $python "$ScriptDir\fetch.py"
if ($LASTEXITCODE -ne 0) { Write-Log "fetch.py failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }

Write-Log "step 2/2: combine.py"
& $python "$ScriptDir\combine.py"
if ($LASTEXITCODE -ne 0) { Write-Log "combine.py failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }

Write-Log "==== done ===="
