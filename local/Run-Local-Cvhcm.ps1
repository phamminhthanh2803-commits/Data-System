# Run-Local-Cvhcm.ps1 — task laptop 8:30 hang ngay (~2 phut): Cang vu TP.HCM chan IP nuoc ngoai nen buoc cvhcm
# (+ cvhcm-berthmap thu Hai) chay o laptop, truoc cloud Shipping AM 9:00 (cloud doc cangvu-hcm/data de ghep tau + lo trinh).
# 09/10/2026: them buoc port-tracker (PT_AUTHS=HCM): keo lich HCM vao kho app Port Tracker -> store/events/HCM + store/days/HCM.csv
# (2 duong dan laptop_only trong data_manifest; cloud keo 11 cang vu con lai vao cung store/).
# Laptop la CHU thu muc shipping/cangvu-hcm tren Drive (tru 3 file *_enriched/monthly do cloud ghi).
# raw/ (HTML cache, 390 MB) chi o laptop D:\pipeline-data\shipping\cangvu-hcm\raw (seed_drive.ps1 chep tu D:\shipping).
# Chay tay: powershell -ExecutionPolicy Bypass -File D:\cloud-deploy\local\Run-Local-Cvhcm.ps1
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'common.ps1')
Start-LocalLog 'local-cvhcm'
Write-Log '===== BAT DAU Local Cvhcm ====='
try {
    Set-PipelineEnv
    Copy-Code 'market-data'; Copy-Code 'shipping'          # market-data: runlib.py cho run_slot shipping
    $ship = $env:SHIP_ROOT
    $steps = if ((Get-Date).DayOfWeek -eq 'Monday') { 'cvhcm-berthmap,cvhcm,port-tracker' } else { 'cvhcm,port-tracker' }
    $env:PT_AUTHS = 'HCM'                                   # pt_update.py: chi TP.HCM (cloud lam 11 cang vu kia)

    Write-Log "----- keo cangvu-hcm tu Drive -----"
    $rc = Invoke-Py $Repo @("$Repo\sync_data.py", 'down', '--hub', 'shipping', '--slot', 'AM', '--only', $steps, '--job', 'laptop')
    if ($rc -ne 0) { Write-Log "sync down exit $rc" 'WARN' }

    Write-Log "----- run_slot shipping AM --only $steps -----"
    $rc = Invoke-Py $ship @("$ship\run_slot.py", '--slot', 'AM', '--only', $steps)

    Write-Log '----- day cangvu-hcm len Drive (sync, tru 3 file enriched cua cloud) -----'
    $rc = Invoke-Py $Repo @("$Repo\sync_data.py", 'up', '--hub', 'shipping', '--slot', 'AM', '--only', $steps, '--job', 'laptop')
    if ($rc -ne 0) { Write-Log "sync up exit $rc" 'WARN' }

    $st = Get-Content "$ship\status-AM.txt" -ErrorAction SilentlyContinue
    Write-Log "===== KET THUC Local Cvhcm: $st ====="
} catch {
    Write-Log "NGOAI LE: $($_.Exception.Message)" 'ERROR'
}
exit 0
