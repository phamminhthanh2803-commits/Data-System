# Run-Shipping.ps1 - RUNNER DUY NHAT cho cum VAN TAI BIEN (D:\shipping), gop 14/09/2026.
# Thay cho 4 task cu: "VHBS ConTex Daily Pull" 9:00, "HaiAn Schedule Daily" 10:00, "AlibraScraper" T2 8:00, "BCTI-Scraper" 22:00.
#
# 2 task Task Scheduler:
#   "Shipping AM"  09:00 hang ngay -> -Slot AM : VHBS ConTex (gia thue tau container), HaiAn (lich tau HAH), CVHP (lich dieu dong tau Cang vu HP); T2: Alibra
#   "Shipping PM"  22:00 hang ngay -> -Slot PM : BCTI/BDI... (chi so cuoc, stockq.org cap nhat sau gio London)
# Chay tay: powershell -File Run-Shipping.ps1 -Slot AM -Only vhbs
# HaiAn van nam o D:\Database\Logistics\HAH (script ghi data canh no; dung $PSScriptRoot). Buoc loi khong chan buoc sau.
param(
    [ValidateSet('AM', 'PM')][string]$Slot = 'AM',
    [string[]]$Only = @()
)
$ErrorActionPreference = 'Continue'
$Only = @($Only | ForEach-Object { $_ -split ',' } | Where-Object { $_ })   # -File truyen 'a,b,c' thanh 1 chuoi -> tu tach
$Root    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$LogDir  = Join-Path $Root 'logs'
$Stamp   = Get-Date -Format 'yyyyMMdd_HHmmss'
$LogFile = Join-Path $LogDir "shipping_$Slot`_$Stamp.log"
$Status  = Join-Path $Root "status-$Slot.txt"
$today   = Get-Date
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'
$env:VNSTOCK_DISABLE_AGENT_SETUP = '1'   # vnai >= 2.6 tu ghi ~/.claude/CLAUDE.md + AGENTS.md khi import vnstock -> tat

function Write-Log { param([string]$Msg, [string]$Level = 'INFO')
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Msg
    Write-Host $line; Add-Content -Path $LogFile -Value $line -Encoding utf8 }   # Write-Host, KHONG Write-Output: trong ham se lan vao gia tri return

function Run-Step { param([hashtable]$S)
    $name = $S.Name; Write-Log "----- $name -----"
    $so = Join-Path $LogDir "out_$Stamp`_$name.txt"; $se = Join-Path $LogDir "err_$Stamp`_$name.txt"
    $t0 = Get-Date
    try {
        if ($S.Kind -eq 'ps1') {
            $exe = 'powershell.exe'; $argList = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $S.Script)
        } else {
            $exe = 'python'; $argList = @($S.Script)
        }
        if ($S.ExtraArgs) { $argList += @($S.ExtraArgs) }     # khong duoc them $null vao ArgumentList
        $p = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory (Split-Path -Parent $S.Script) -NoNewWindow -Wait -PassThru `
                           -RedirectStandardOutput $so -RedirectStandardError $se
        $code = $p.ExitCode
        $match = if ($S.Match) { $S.Match } else { 'DONE|ERROR|LOI|XONG|Master|Da ghi|done|failed|saved|rows' }
        if (Test-Path $so) { foreach ($t in (Get-Content $so -Encoding utf8)) { if ($t -match $match) { Write-Log "  $t" } } }
        if ($code -ne 0 -and (Test-Path $se)) {
            foreach ($t in (Get-Content $se -Encoding utf8 | Select-Object -Last 8)) { if ($t.Trim()) { Write-Log "  $t" 'WARN' } } }
        Remove-Item $so, $se -Force -ErrorAction SilentlyContinue
    } catch { Write-Log "$name ngoai le: $($_.Exception.Message)" 'ERROR'; $code = 999 }
    Write-Log ("$name : {0} [{1:n0}s]" -f $(if ($code -eq 0) { 'OK' } else { "FAIL exit $code" }), ((Get-Date) - $t0).TotalSeconds)
    return ($code -eq 0) }

$isMon = ($today.DayOfWeek -eq 'Monday')
$Steps = @(
    @{ Slot='AM'; Name='vhbs';   Kind='ps1'; Script=(Join-Path $Root 'VHBS-ConTex\Update-VhbsContex.ps1');          When=$true }
    @{ Slot='AM'; Name='haian';  Kind='ps1'; Script='D:\Database\Logistics\HAH\haian-schedule-daily.ps1';           When=$true }
    @{ Slot='AM'; Name='cvhp';   Kind='py';  Script=(Join-Path $Root 'cangvu-haiphong\cvhp_scrape.py');            When=$true }   # lich dieu dong tau Cang vu HP (keo lai hom nay-3..+1)
    @{ Slot='AM'; Name='cvhcm-berthmap'; Kind='py'; Script=(Join-Path $Root 'cangvu-hcm\cvhcm_berthmap.py'); ExtraArgs=@('--months','2'); When=$isMon }   # thu Hai: cap nhat bang tra ma cau -> khu vuc cang chinh thuc
    @{ Slot='AM'; Name='cvhcm';  Kind='py';  Script=(Join-Path $Root 'cangvu-hcm\cvhcm_scrape.py');                When=$true }   # ke hoach dieu dong tau Cang vu TP.HCM (gom Cai Mep - Vung Tau), keo lai hom nay-3..+1
    @{ Slot='AM'; Name='cv-pkh';  Kind='py';  Script=(Join-Path $Root 'cangvu-toanquoc\pkh_scrape.py'); ExtraArgs=@('--details','150'); When=$true }   # 9 cang vu nen tang public-kh (QNH,HPH,TBH,THA,HTH,DNG,BTN,DNI,KGG)
    @{ Slot='AM'; Name='cv-aspx'; Kind='py';  Script=(Join-Path $Root 'cangvu-toanquoc\aspx_scrape.py');           When=$true }   # Quang Ninh kht1, Nha Trang, Can Tho
    @{ Slot='AM'; Name='cv-national'; Kind='py'; Script=(Join-Path $Root 'cangvu-toanquoc\national_build.py');     When=$true }   # gop chuyen tau toan quoc
    @{ Slot='AM'; Name='cvhp-vessels'; Kind='py'; Script=(Join-Path $Root 'cangvu-haiphong\vessel_enrich.py');     When=$true }   # tra IMO/loai tau/TEU/hang cho tau ca HP + HCM (BalticShipping/Flexport, toi da 300 tau/ngay) + ghep vao calls
    @{ Slot='AM'; Name='itinerary'; Kind='py'; Script=(Join-Path $Root 'vessel-itinerary\vessel_itinerary.py'); ExtraArgs=@('--all','--since','2025-01-01','--no-png'); When=$true }   # lo trinh tung tau + chang + vong tuyen tu calls HP+HCM
    @{ Slot='AM'; Name='alibra'; Kind='ps1'; Script=(Join-Path $Root 'alibra-scraper\run.ps1');                    When=$isMon }
    @{ Slot='PM'; Name='bcti';   Kind='py';  Script=(Join-Path $Root 'BCTI-scraper\scrape_bcti.py'); ExtraArgs=@('ALL'); When=$true }
)

Write-Log "===== BAT DAU Shipping [$Slot] ====="
$fails = @()
foreach ($s in $Steps) {
    if ($s.Slot -ne $Slot) { continue }
    if ($Only.Count -gt 0 -and $Only -notcontains $s.Name) { continue }
    if (-not $s.When -and $Only.Count -eq 0) { Write-Log "$($s.Name): bo qua (khong dung lich)"; continue }
    if (-not (Run-Step $s)) { $fails += $s.Name }
}
$state = if ($fails.Count) { 'WARN' } else { 'OK' }
"$state | $(Get-Date -Format 'yyyy-MM-dd HH:mm') | loi: $($fails -join ',')" | Set-Content -Path $Status -Encoding utf8
Write-Log "===== KET THUC [$Slot]: $state $($fails -join ',') ====="
Get-ChildItem $LogDir -Filter 'shipping_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 60 | Remove-Item -Force -ErrorAction SilentlyContinue
exit 0
