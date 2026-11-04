$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

$logPath = Join-Path $ScriptDir "run.log"
function Write-Log($msg) {
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Write-Host $line
    Add-Content -Path $logPath -Value $line -Encoding utf8
}

# 04/11/2026: moi duong dan qua Join-Path, khong viet "\" - GitHub Actions (Linux) chay file nay bang pwsh,
# o do "\" la ky tu trong ten file -> "Alibra-scraper\fetch.py" khong ton tai (alibra loi moi thu Hai 19/10-02/11).
# Find python: prefer venv, fall back to py launcher, then python on PATH.
$python = $null
$venvPython = Join-Path (Join-Path (Join-Path $ScriptDir ".venv") "Scripts") "python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
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
& $python (Join-Path $ScriptDir "fetch.py")
if ($LASTEXITCODE -ne 0) { Write-Log "fetch.py failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }

Write-Log "step 2/2: combine.py"
& $python (Join-Path $ScriptDir "combine.py")
if ($LASTEXITCODE -ne 0) { Write-Log "combine.py failed (exit $LASTEXITCODE)"; exit $LASTEXITCODE }

Write-Log "==== done ===="
