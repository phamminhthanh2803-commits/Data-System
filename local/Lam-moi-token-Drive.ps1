# Lam-moi-token-Drive.ps1 — lam moi quyen Google Drive cua rclone (remote gdrive) khi bi loi invalid_grant.
#
# Khi nao can: app online bao "Quyen Google Drive cua rclone da het han", hoac log Actions co
# "couldn't fetch token: invalid_grant". Nguyen nhan: ung dung OAuth 'rclone-pipeline' o trang thai Testing
# -> Google thu hoi refresh token sau 7 ngay. Publish app (In production) thi het bi.
#
# Cach chay (PV2 tu chay, KHONG chay qua Claude): chuot phai -> Run with PowerShell, hoac
#   powershell -ExecutionPolicy Bypass -File D:\cloud-deploy\local\Lam-moi-token-Drive.ps1
# Script se:
#   1. mo trinh duyet de PV2 dang nhap Google + bam Allow (rclone config reconnect gdrive:)
#   2. kiem tra Drive doc duoc
#   3. chep chuoi base64 cua rclone.conf vao CLIPBOARD (khong in ra man hinh)
#   4. mo 2 trang secret: GitHub Actions (RCLONE_CONF) + Streamlit Cloud -> PV2 dan vao
$ErrorActionPreference = 'Stop'
$rc = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe\rclone-v1.75.1-windows-amd64\rclone.exe'
if (-not (Test-Path $rc)) { $c = Get-Command rclone -ErrorAction SilentlyContinue; if ($c) { $rc = $c.Source } else { throw 'Khong tim thay rclone' } }
$conf = Join-Path $env:APPDATA 'rclone\rclone.conf'

Write-Host ''
Write-Host '== 1/4 Lam moi quyen Drive: trinh duyet se mo, dang nhap Google (phamminhthanh2803) roi bam Allow / Cho phep ==' -ForegroundColor Cyan
Write-Host '   (Neu hoi "Refresh token?" -> go y roi Enter. Neu hien "Google hasn''t verified this app" -> Advanced -> Go to rclone)'
& $rc config reconnect gdrive:
if ($LASTEXITCODE -ne 0) { throw "rclone config reconnect loi (exit $LASTEXITCODE)" }

Write-Host ''
Write-Host '== 2/4 Kiem tra Drive ==' -ForegroundColor Cyan
& $rc lsd gdrive:pipeline-data
if ($LASTEXITCODE -ne 0) { throw 'Van chua doc duoc Drive - chay lai script' }
Write-Host '   Drive OK' -ForegroundColor Green

Write-Host ''
Write-Host '== 3/4 Chep chuoi RCLONE_CONF (base64) vao clipboard ==' -ForegroundColor Cyan
[Convert]::ToBase64String([IO.File]::ReadAllBytes($conf)) | Set-Clipboard
Write-Host '   Da chep vao clipboard (khong hien ra man hinh).' -ForegroundColor Green

Write-Host ''
Write-Host '== 4/4 Dan vao 2 noi ==' -ForegroundColor Cyan
Write-Host '   a) GitHub: trang vua mo -> RCLONE_CONF -> bieu tuong but chi (Update) -> Ctrl+V -> Update secret'
Start-Process 'https://github.com/phamminhthanh2803-commits/Data-System/settings/secrets/actions/RCLONE_CONF'
Write-Host '   b) Streamlit: share.streamlit.io -> dau ... canh app -> Settings -> Secrets -> thay gia tri trong'
Write-Host '      RCLONE_CONF = "...." bang chuoi moi (Ctrl+V giua 2 dau nhay) -> Save changes -> sau do Reboot app'
Start-Process 'https://share.streamlit.io/'
Write-Host ''
Write-Host 'Xong buoc 4 thi bao Claude: "da cap nhat token" de kiem tra cac job va app.' -ForegroundColor Yellow
Read-Host 'Enter de dong'
