# seed_drive.ps1 — LAN DAU: dua du lieu pipeline tu D:\ len Google Drive (gdrive:pipeline-data) theo data_manifest.py
# va dung cay du lieu laptop D:\pipeline-data (cangvu-hcm raw + junction bond-pivot).
#   powershell -ExecutionPolicy Bypass -File D:\cloud-deploy\seed_drive.ps1 [-DryRun] [-SkipLocal]
# Uoc ~1,9 GB (xem: python data_manifest.py --size). bond-pivot (3,5 GB) KHONG len Drive (drive=False trong manifest,
# Drive chi con 6,8 GB) - co -SkipBond cho tuong thich, mac dinh luon bo. Chay lai an toan (rclone copy chi chep file moi/doi).
param([switch]$DryRun, [switch]$SkipLocal, [switch]$SkipBond = $true)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'local\common.ps1')
$rc = Find-Rclone
Write-Host "rclone: $rc"
$remotes = & $rc listremotes
if (-not ($remotes -match '^gdrive:')) {
    throw "Chua co remote 'gdrive'. Chay: rclone config create gdrive drive scope=drive  (dang nhap Google tren trinh duyet)"
}
$env:RCLONE = $rc; $env:RCLONE_REMOTE = $Remote; $env:PYTHONUTF8 = '1'

Write-Host "`n== Uoc dung luong se len Drive"
python (Join-Path $Repo 'data_manifest.py') --size

Write-Host "`n== rclone copy D:\ -> $Remote (bo bond-pivot)"
$pyArgs = @((Join-Path $Repo 'sync_data.py'), 'seed', '--skip-bond')
if ($DryRun) { $pyArgs += '--dry-run' }
& python @pyArgs
if ($LASTEXITCODE -ne 0) { Write-Host "! co loi rclone (xem tren), chay lai seed_drive.ps1 sau" -ForegroundColor Yellow }

if (-not $SkipLocal -and -not $DryRun) {
    Write-Host "`n== Cay du lieu laptop $Data"
    New-Item -ItemType Directory -Force (Join-Path $Data 'market-data') | Out-Null
    New-Item -ItemType Directory -Force (Join-Path $Data 'shipping') | Out-Null
    Ensure-BondJunction
    # cangvu-hcm: laptop la chu -> chep ca raw/ (390 MB, khong len Drive) tu D:\shipping
    Write-Host "robocopy D:\shipping\cangvu-hcm -> $Data\shipping\cangvu-hcm (ca raw/)"
    & robocopy 'D:\shipping\cangvu-hcm' (Join-Path $Data 'shipping\cangvu-hcm') /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
    Copy-Code 'market-data'; Copy-Code 'shipping'
    Write-Host "code da chep vao $Data (Run-Local-*.ps1 se chep lai moi lan chay)"
}

Write-Host "`n== Dung luong tren Drive"
& $rc size $Remote
Write-Host "`nXONG. Buoc tiep: push repo + them secret RCLONE_CONF (xem README.md)."
