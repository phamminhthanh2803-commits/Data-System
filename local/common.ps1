# common.ps1 — ham dung chung cho Run-Local-Mini.ps1 / Run-Local-Cvhcm.ps1 / seed_drive.ps1 (dot-source).
# Khong chay truc tiep.

$script:Repo = Split-Path -Parent $PSScriptRoot          # D:\cloud-deploy
$script:Data = 'D:\pipeline-data'                        # cay du lieu laptop (code copy + data tu Drive)
$script:Remote = 'gdrive:pipeline-data'
$script:WingetRclone = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe\rclone-v1.75.1-windows-amd64\rclone.exe'

function Find-Rclone {
    # thu tu: env RCLONE -> PATH -> ban winget (chua co trong PATH cua shell cu)
    if ($env:RCLONE -and (Test-Path $env:RCLONE)) { return $env:RCLONE }
    $c = Get-Command rclone -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    if (Test-Path $script:WingetRclone) { return $script:WingetRclone }
    throw "Khong tim thay rclone. Cai: winget install Rclone.Rclone (roi mo lai PowerShell)."
}

function Write-Log([string]$msg, [string]$level = 'INFO') {
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $level, $msg
    Write-Host $line
    if ($script:LogFile) { Add-Content -Path $script:LogFile -Value $line -Encoding utf8 }
}

function Start-LocalLog([string]$name) {
    $dir = Join-Path $script:Data 'logs'
    New-Item -ItemType Directory -Force $dir | Out-Null
    $script:LogFile = Join-Path $dir ("{0}_{1}.log" -f $name, (Get-Date -Format 'yyyyMMdd_HHmmss'))
    # giu 60 log moi nhat
    Get-ChildItem $dir -Filter "$name*.log" | Sort-Object LastWriteTime -Descending | Select-Object -Skip 60 | Remove-Item -Force -ErrorAction SilentlyContinue
}

function Set-PipelineEnv {
    $env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'; $env:VNSTOCK_DISABLE_AGENT_SETUP = '1'
    $env:MD_ROOT = Join-Path $script:Data 'market-data'
    $env:SHIP_ROOT = Join-Path $script:Data 'shipping'
    $env:BCTC_ROOT = 'D:\bctc'                              # nganh-ck: code + sqlite + Excel OneDrive van o D:\bctc (laptop la chu)
    $env:HAH_DIR = Join-Path $script:Data 'hah'
    $env:RCLONE_REMOTE = $script:Remote
    $env:RCLONE = Find-Rclone
}

function Copy-Code([string]$hub) {
    # chep code tu repo vao cay du lieu (script ghi data canh script nen code va data phai cung thu muc).
    # KHONG /MIR (giu data), bo bond-pivot (junction -> D:\market-data\bond-pivot), bo port-tracker cache.
    $src = Join-Path $script:Repo $hub; $dst = Join-Path $script:Data $hub
    New-Item -ItemType Directory -Force $dst | Out-Null
    & robocopy $src $dst /E /XD .git __pycache__ logs cache bond-pivot /XF *.pyc /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
    if ($LASTEXITCODE -ge 8) { Write-Log "robocopy $hub loi $LASTEXITCODE" 'WARN' }
}

function Ensure-BondJunction {
    $j = Join-Path $script:Data 'market-data\bond-pivot'
    if (-not (Test-Path $j)) {
        cmd /c mklink /J "$j" "D:\market-data\bond-pivot" | Out-Null
        Write-Log "tao junction $j -> D:\market-data\bond-pivot"
    }
}

function Wait-CloudStatus([string]$relPath, [int]$maxMinutes = 150, [int]$everyMinutes = 5) {
    # doi file status-<slot>.txt tren Drive co ngay HOM NAY (cloud da chay xong slot) - tranh 2 ben ghi de nhau
    $rc = Find-Rclone; $today = Get-Date -Format 'yyyy-MM-dd'; $deadline = (Get-Date).AddMinutes($maxMinutes)
    while ($true) {
        $txt = & $rc cat "$($script:Remote)/$relPath" 2>$null
        if ($txt -and ($txt -join ' ') -match $today) { Write-Log "cloud da xong ($relPath): $($txt -join ' ')"; return $true }
        if ((Get-Date) -gt $deadline) { Write-Log "het $maxMinutes phut, cloud chua xong $relPath -> chay tiep voi du lieu hien co" 'WARN'; return $false }
        Write-Log "cloud chua xong $relPath ($(($txt -join ' ').Trim())) - doi $everyMinutes phut"
        Start-Sleep -Seconds ($everyMinutes * 60)
    }
}

function Invoke-Py([string]$workdir, [string[]]$argList) {
    # chay python, in output vao log; tra ve exit code (Start-Process + file redirect: tranh bay stderr PS 5.1)
    $so = [System.IO.Path]::GetTempFileName(); $se = [System.IO.Path]::GetTempFileName()
    $p = Start-Process -FilePath 'python' -ArgumentList $argList -WorkingDirectory $workdir -NoNewWindow -Wait -PassThru -RedirectStandardOutput $so -RedirectStandardError $se
    Get-Content $so -Encoding utf8 | ForEach-Object { if ($_ -match 'DONE|LOI|ERROR|->|Da luu|Tong|XONG|OK|FAIL|WARN|bo qua|keo ve|day len|\$ ') { Write-Log "  $_" } }
    if ($p.ExitCode -ne 0) { Get-Content $se -Encoding utf8 | Select-Object -Last 8 | ForEach-Object { Write-Log "  $_" 'WARN' } }
    Remove-Item $so, $se -Force -ErrorAction SilentlyContinue
    return $p.ExitCode
}
