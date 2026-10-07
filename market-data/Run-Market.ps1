# Run-Market.ps1 - RUNNER DUY NHAT cho cum DU LIEU THI TRUONG & VI MO (D:\market-data), gop 14/09/2026.
# Thay cho 5 runner cu: index-fetcher\Run-Pipeline.ps1 (T7), Run-Region-Daily.ps1 (18:30), market-valuation\Chay-hang-ngay.bat (10:30),
# macro-fetcher\run_daily.bat (T2), transmission-fetcher\Run-Pipeline.ps1 (16:00), bond-pivot\run_daily.ps1 (T2).
#
# 2 task Task Scheduler:
#   "Market Data AM"  10:30 hang ngay  -> Run-Market.ps1 -Slot AM   (dinh gia VN; T2: vi mo VN + NSO PX-Web + trai phieu + so TK VSDC; T7: chi so tuan)
#   "Market Data PM"  18:30 hang ngay  -> Run-Market.ps1 -Slot PM   (truyen dan SBV, khoi ngoai, gia co phieu TradingView,
#                                                                    dinh gia khu vuc + TradingView, file nganh CK; ngay 1-7: MSCI; T2: vi mo khu vuc)
# Chay tay 1 buoc:  powershell -File Run-Market.ps1 -Slot PM -Only flows,tradingview
# Buoc loi KHONG chan buoc sau. Buoc Critical loi/stale -> popup canh bao. Trang thai: status-<Slot>.txt, log: logs\market_<Slot>_*.log
# 2 bay Windows: PS 5.1 khong dung "& python 2>&1" (stderr bi boc ErrorRecord) -> Start-Process + file redirect, chi tin ExitCode;
#                task phai co -AllowStartIfOnBatteries.
param(
    [ValidateSet('AM', 'PM')][string]$Slot = 'PM',
    [string[]]$Only = @()
)
$ErrorActionPreference = 'Continue'
$Only = @($Only | ForEach-Object { $_ -split ',' } | Where-Object { $_ })   # -File truyen 'a,b,c' thanh 1 chuoi -> tu tach
$Root    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$LogDir  = Join-Path $Root 'logs'
$Stamp   = Get-Date -Format 'yyyyMMdd_HHmmss'
$LogFile = Join-Path $LogDir "market_$Slot`_$Stamp.log"
$Status  = Join-Path $Root "status-$Slot.txt"
$today   = Get-Date
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$env:PYTHONUTF8 = '1'; $env:PYTHONIOENCODING = 'utf-8'
$env:VNSTOCK_DISABLE_AGENT_SETUP = '1'   # vnai >= 2.6 tu ghi ~/.claude/CLAUDE.md + AGENTS.md khi import vnstock -> tat

function Write-Log { param([string]$Msg, [string]$Level = 'INFO')
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Level, $Msg
    Write-Host $line; Add-Content -Path $LogFile -Value $line -Encoding utf8 }   # Write-Host, KHONG Write-Output: trong ham se lan vao gia tri return

function Show-Alert { param([string]$Title, [string]$Body)
    $safe = $Body -replace "'", "''"
    $cmd  = "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.MessageBox]::Show('$safe','$Title','OK','Error') | Out-Null"
    Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile', '-Command', $cmd }

function Run-Python { param([string]$Name, [string]$Script, [string]$WorkDir, $ExtraArgs, [string]$Match)
    $so = Join-Path $LogDir "out_$Stamp`_$Name.txt"; $se = Join-Path $LogDir "err_$Stamp`_$Name.txt"
    $argList = @($Script)
    if ($ExtraArgs) { $argList += @($ExtraArgs) }     # khong duoc them $null vao ArgumentList
    try {
        $p = Start-Process -FilePath 'python' -ArgumentList $argList -WorkingDirectory $WorkDir -NoNewWindow -Wait -PassThru `
                           -RedirectStandardOutput $so -RedirectStandardError $se
        $code = $p.ExitCode
        if (Test-Path $so) { foreach ($t in (Get-Content $so -Encoding utf8)) { if ($t -match $Match) { Write-Log "  $t" } } }
        if ($code -ne 0 -and (Test-Path $se)) {
            foreach ($t in (Get-Content $se -Encoding utf8 | Select-Object -Last 8)) { if ($t.Trim()) { Write-Log "  $t" 'WARN' } } }
        Remove-Item $so, $se -Force -ErrorAction SilentlyContinue
        return $code
    } catch { Write-Log "$Name ngoai le: $($_.Exception.Message)" 'ERROR'; return 999 } }

function Run-Step { param([hashtable]$S)
    $name = $S.Name
    Write-Log "----- $name -----"
    $retry = if ($S.Retry) { $S.Retry } else { 1 }
    $wait  = if ($S.RetryWait) { $S.RetryWait } else { 60 }
    $match = if ($S.Match) { $S.Match } else { 'Che do|LOI|Tong|Da luu|->|Master|XONG|Bao cao|! |X ' }
    $work  = if ([IO.Path]::IsPathRooted($S.WorkDir)) { $S.WorkDir } else { Join-Path $Root $S.WorkDir }   # cho phep buoc ngoai hub (D:\bctc)
    $t0 = Get-Date
    for ($i = 1; $i -le $retry; $i++) {
        $script = if ([IO.Path]::IsPathRooted($S.Script)) { $S.Script } else { Join-Path $Root $S.Script }
        $code = Run-Python -Name $name -Script $script -WorkDir $work -ExtraArgs $S.ExtraArgs -Match $match
        if ($code -eq 0) { break }
        Write-Log "$name exit $code (lan $i/$retry)" 'WARN'
        if ($i -lt $retry) { Start-Sleep -Seconds $wait }
    }
    Write-Log ("$name : {0} [{1:n0}s]" -f $(if ($code -eq 0) { 'OK' } else { "FAIL exit $code" }), ((Get-Date) - $t0).TotalSeconds)
    return ($code -eq 0) }

function Check-Stale { param([hashtable]$S)
    # S.Stale = @{ File='...'; Days=N; Groups=@('VN=source:vnstock', ...) }
    $st = $S.Stale
    $file = Join-Path $Root $st.File
    if (-not (Test-Path $file)) { return "STALE|khong thay $($st.File)" }
    $so = Join-Path $LogDir "probe_$Stamp`_$($S.Name).txt"
    $argList = @((Join-Path $Root 'stale_check.py'), $file, $st.Days) + @($st.Groups)
    Start-Process -FilePath 'python' -ArgumentList $argList -NoNewWindow -Wait -RedirectStandardOutput $so -RedirectStandardError "$so.err" | Out-Null
    $out = ''
    if (Test-Path $so) { $out = (Get-Content $so | Select-Object -Last 1) }
    Remove-Item $so, "$so.err" -Force -ErrorAction SilentlyContinue
    if (-not $out) { $out = 'STALE|probe khong chay duoc' }
    return $out }

# ------------------------------------------------------------------ BANG BUOC
$isMon = ($today.DayOfWeek -eq 'Monday'); $isSat = ($today.DayOfWeek -eq 'Saturday'); $isEarly = ($today.Day -le 7)
$Steps = @(
    # ---- AM 10:30
    @{ Slot='AM'; Name='valuation-vn';  Script='market-valuation\run_daily.py';          WorkDir='market-valuation';   When=$true;   Critical=$true
       Note='P/E, P/B, EPS thi truong VN (VNDirect) + nganh + tung ma + dieu chinh' }
    @{ Slot='AM'; Name='macro-vn';      Script='macro-fetcher\fetch_macro.py';           WorkDir='macro-fetcher';      When=$isMon;  Match='.' }
    # 07/10/2026: PX-Web NSO song lai o pxweb.nso.gov.vn (form ASP.NET -> JSON-stat): nien giam (nam) + CPI thang;
    # keo lai het moi tuan vi NSO sua so cu (So bo -> chinh thuc). nso-monthly chi tai Excel "Bieu so lieu" bao cao KT-XH thang.
    @{ Slot='AM'; Name='nso';           Script='nso-fetcher\fetch_nso.py';               WorkDir='nso-fetcher';        When=$isMon;  Match='Da luu|Tong|LOI|XONG|X '
       Note='NSO PX-Web 11 CSDL kinh te -> nso_master.csv + nso_catalog.csv + nso_timeseries.xlsx' }
    @{ Slot='AM'; Name='nso-monthly';   Script='nso-fetcher\fetch_monthly_reports.py';   WorkDir='nso-fetcher';        When=$isMon;  Match='Da luu|Tong|LOI|X ' }
    @{ Slot='AM'; Name='bonds';         Script='bond-pivot\scripts\run_pipeline.py';     WorkDir='bond-pivot';         When=$isMon;  Match='\] ' }
    @{ Slot='AM'; Name='vsdc-accounts'; Script='vsdc-accounts\pull_vsdc_accounts.py';    WorkDir='vsdc-accounts';      When=$isMon;  Match='Da luu|LOI|! |X ' }
    @{ Slot='AM'; Name='indices';       Script='index-fetcher\fetch_indices.py';         WorkDir='index-fetcher';      When=$isSat;  Retry=3; Critical=$true
       Stale=@{ File='index-fetcher\indices-master.csv'; Days=6; Groups=@('VN=source:vnstock', 'Global=source:yahoo', 'KhuVuc=source:!vnstock,yahoo') } }
    # ---- PM 18:30 (sau khi TQ/HK/Han/Dai/Thai/Indo/Malaysia/Nhat dong cua; SBV da dang so trong ngay)
    @{ Slot='PM'; Name='transmission';  Script='transmission-fetcher\fetch_all.py';      WorkDir='transmission-fetcher'; When=$true; Retry=3; RetryWait=90; Critical=$true
       Match='Che do|Master:|Bao cao|Tong|X |! '; Stale=@{ File='transmission-fetcher\transmission-master.csv'; Days=4; Groups=@() } }
    @{ Slot='PM'; Name='flows';         Script='index-fetcher\fetch_flows.py';           WorkDir='index-fetcher';      When=$true }
    @{ Slot='PM'; Name='foreign-stocks'; Script='index-fetcher\fetch_foreign_stocks.py'; WorkDir='index-fetcher';     When=$true;  Match='Che do|-> |Da luu|Khong'
       Note='khoi ngoai mua/ban theo tung ma (VNDirect, du phong) -> app tab Khoi ngoai chia theo nhom nganh' }
    # 18/09/2026: nguon CHINH khoi ngoai theo ma = Vietcap IQ (lich su tu 2000, tach thoa thuan);
    # hang ngay chi keo 10 phien gan nhat moi ma (~1600 request, 8 luong). Backfill: --full.
    @{ Slot='PM'; Name='foreign-vci';   Script='index-fetcher\fetch_foreign_vci.py';     WorkDir='index-fetcher';      When=$true
       ExtraArgs=@('--recent', '10'); Match='Che do|Da luu|-> |! ' }
    @{ Slot='PM'; Name='prop-stocks';   Script='index-fetcher\fetch_prop_stocks.py';    WorkDir='index-fetcher';      When=$true;  Match='Che do|-> |Da luu|Khong'
       Note='tu doanh CTCK theo tung ma (VNDirect, tu 05/2022) -> app Soi dong tien' }
    @{ Slot='PM'; Name='icb-vci';       Script='index-fetcher\fetch_icb_vci.py';        WorkDir='index-fetcher';      When=$true;  Match='Che do|-> |Da luu|LOI'
       Note='phan nganh ICB 4 cap (Vietcap, 1 request) -> app chia dong tien KN/TD theo nganh' }
    # 17/09/2026: GTGD chinh thuc (VCI) cua 4 chi so VN phai cap nhat MOI NGAY sau dong cua -
    # buoc 'indices' chi chay T7 nen ca tuan app phai dung GTGD uoc tinh, va neu ai keo giua
    # phien (nut Cap nhat du lieu / chay tay) thi dong do phien nam lai toi T7. Chay 18:30
    # ghi de dung phien day du (incremental keo lai 7 ngay gan nhat).
    @{ Slot='PM'; Name='indices-vn';    Script='index-fetcher\fetch_indices.py';         WorkDir='index-fetcher';      When=$true
       ExtraArgs=@('--only', 'VNINDEX,VN30,HNXINDEX,UPCOM'); Match='Che do|Tong|Da luu|LOI' }
    @{ Slot='PM'; Name='tvhistory';     Script='index-fetcher\tv_history.py';            WorkDir='index-fetcher';      When=$true;  Match='-> |da luu|KHONG' }
    @{ Slot='PM'; Name='valuation-region'; Script='market-valuation\region.py';          WorkDir='market-valuation';   When=$true }
    @{ Slot='PM'; Name='tradingview';   Script='market-valuation\tv_region.py';          WorkDir='market-valuation';   When=$true;  Match='TV_|LOI|->' }
    @{ Slot='PM'; Name='nganh-ck';      Script='D:\bctc\nganh-chung-khoan\update_nganh_daily.py'; WorkDir='D:\bctc\nganh-chung-khoan'; When=$true;  Match='-> |! |LOI|tbl_|Table2'
       Note='file nganh CK IB&Brokerage_Nganh.xlsx: dinh gia + LNST TTM tu gia TradingView, so TK VSDC (sau tvhistory)' }
    @{ Slot='PM'; Name='msci';          Script='market-valuation\msci_region.py';        WorkDir='market-valuation';   When=$isEarly }
    @{ Slot='PM'; Name='macro-region';  Script='macro-fetcher\fetch_macro_region.py';    WorkDir='macro-fetcher';      When=$isMon;  Match='.' }
)

Write-Log "===== BAT DAU Market Data [$Slot] ====="
$fails = @(); $stales = @(); $critFail = $false
foreach ($s in $Steps) {
    if ($s.Slot -ne $Slot) { continue }
    if ($Only.Count -gt 0 -and $Only -notcontains $s.Name) { continue }
    if (-not $s.When -and $Only.Count -eq 0) { Write-Log "$($s.Name): bo qua (khong dung lich)"; continue }
    $ok = Run-Step $s
    if (-not $ok) { $fails += $s.Name; if ($s.Critical) { $critFail = $true } }
    if ($s.Stale) {
        $probe = Check-Stale $s
        Write-Log "  do tuoi: $probe"
        if ($probe -like 'STALE|*') { $stales += "$($s.Name): $($probe.Split('|')[1])" }
    }
}
$state = if ($critFail) { 'FAIL' } elseif ($stales.Count) { 'STALE' } elseif ($fails.Count) { 'WARN' } else { 'OK' }
"$state | $(Get-Date -Format 'yyyy-MM-dd HH:mm') | loi: $($fails -join ',') | cu: $($stales -join '; ')" | Set-Content -Path $Status -Encoding utf8
Write-Log "===== KET THUC [$Slot]: $state | loi: $($fails -join ',') | cu: $($stales -join '; ') ====="
if ($critFail -or $stales.Count) {
    Show-Alert -Title "Market Data $Slot - $state" -Body "Loi: $($fails -join ', ')`nDu lieu cu: $($stales -join '; ')`n`nLog: $LogFile"
}
# don log: giu 60 file moi nhat
Get-ChildItem $LogDir -Filter 'market_*.log' | Sort-Object LastWriteTime -Descending | Select-Object -Skip 60 | Remove-Item -Force -ErrorAction SilentlyContinue
Get-ChildItem $LogDir -Filter '*_*.txt' | Where-Object { $_.LastWriteTime -lt $today.AddDays(-2) } | Remove-Item -Force -ErrorAction SilentlyContinue
exit 0
