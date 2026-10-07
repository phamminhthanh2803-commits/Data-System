# Run-Local-Mini.ps1 — task laptop 18:40 hang ngay (~3-5 phut), phan KHONG chay duoc tren GitHub Actions:
#   1. valuation-region chi 2 san IDX (JCI, LQ45) + Bursa (FBMKLCI)  — Cloudflare chan IP My
#   2. nganh-ck: ghi Excel OneDrive IB&Brokerage_Nganh.xlsx (win32com)   — can Excel Windows
#   3. thu Hai: bonds (bond-pivot 3,5 GB o lai laptop, D:\market-data\bond-pivot qua junction)
#   4. keo du lieu cloud ve D:\pipeline-data cho 2 app Streamlit (local\Chay-app-*.bat)
# Truoc khi chay: doi cloud Market PM hom nay xong (status-PM.txt tren Drive co ngay hom nay, toi da 150 phut)
# de khong ghi de valuation-region-master.csv va de nganh-ck doc tv-history moi.
# Dang ky: xem local\schtasks-mau.txt. Chay tay: powershell -ExecutionPolicy Bypass -File D:\cloud-deploy\local\Run-Local-Mini.ps1 [-NoWait] [-NoApp]
param([switch]$NoWait, [switch]$NoApp, [switch]$NoBond)
$ErrorActionPreference = 'Continue'
. (Join-Path $PSScriptRoot 'common.ps1')
Start-LocalLog 'local-mini'
Write-Log '===== BAT DAU Local Mini ====='
try {
    Set-PipelineEnv
    Copy-Code 'market-data'; Copy-Code 'shipping'; Ensure-BondJunction
    $md = $env:MD_ROOT; $isMon = (Get-Date).DayOfWeek -eq 'Monday'

    if (-not $NoWait) { Wait-CloudStatus 'market-data/status-PM.txt' 150 5 | Out-Null }

    # --- keo ve thu muc 2 buoc can (market-valuation, index-fetcher 1 phan, vsdc, transmission)
    $steps = 'valuation-region,nganh-ck'
    Write-Log "----- keo du lieu tu Drive ($steps) -----"
    $rc = Invoke-Py $Repo @("$Repo\sync_data.py", 'down', '--hub', 'market-data', '--slot', 'PM', '--only', $steps, '--job', 'laptop')
    if ($rc -ne 0) { Write-Log "sync down exit $rc" 'WARN' }

    # --- 1. IDX + Bursa (region.py --only; merge vao valuation-region-master.csv da keo ve)
    Write-Log '----- valuation-region: JCI, LQ45, FBMKLCI -----'
    $rc = Invoke-Py "$md\market-valuation" @("$md\market-valuation\region.py", '--only', 'JCI,LQ45,FBMKLCI')
    Write-Log ("valuation-region (IDX/Bursa): " + $(if ($rc -eq 0) { 'OK' } else { "FAIL exit $rc" }))

    # --- 2. nganh-ck (Excel COM, D:\bctc) - runner ghi log/status vao D:\pipeline-data\market-data
    Write-Log '----- nganh-ck -----'
    $rc = Invoke-Py $md @("$md\run_slot.py", '--slot', 'PM', '--only', 'nganh-ck')

    # --- 3. thu Hai: bonds (chay tren D:\market-data\bond-pivot qua junction, khong len Drive)
    if ($isMon -and -not $NoBond) {
        Write-Log '----- bonds (thu Hai, local) -----'
        $rc = Invoke-Py $md @("$md\run_slot.py", '--slot', 'AM', '--only', 'bonds')
    }

    # --- day len Drive: chi 2 file valuation-region-*.csv (laptop_up_include trong data_manifest)
    Write-Log '----- day len Drive (valuation-region) -----'
    $rc = Invoke-Py $Repo @("$Repo\sync_data.py", 'up', '--hub', 'market-data', '--slot', 'PM', '--only', 'valuation-region,bonds', '--job', 'laptop')   # bonds: data/processed bond-pivot (laptop chu) len Drive
    if ($rc -ne 0) { Write-Log "sync up exit $rc" 'WARN' }

    # --- 4. du lieu cho app Streamlit + port-tracker
    if (-not $NoApp) {
        Write-Log '----- keo du lieu cho app (APP_FOLDERS) -----'
        $rc = Invoke-Py $Repo @("$Repo\sync_data.py", 'app')
        if ($rc -ne 0) { Write-Log "sync app exit $rc" 'WARN' }
    }
    $st = Get-Content "$md\status-PM.txt" -ErrorAction SilentlyContinue
    Write-Log "===== KET THUC Local Mini: $st ====="
} catch {
    Write-Log "NGOAI LE: $($_.Exception.Message)" 'ERROR'
}
exit 0
