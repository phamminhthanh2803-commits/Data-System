# progress.ps1 - thanh tiến độ cho log biggee_api.py / bds_scrape.py (20/10/2026). Dùng: & .\progress.ps1 [đường dẫn log]
param([string]$Log = "D:\bat-dong-san\batdongsan-projects\logs\biggee_api_20261020.log")
$t0 = Get-Date
while ($true) {
    $lines = Get-Content $Log -ErrorAction SilentlyContinue
    $last = ($lines | Where-Object { $_ -match '(\d+)/(\d+) m' } | Select-Object -Last 1)
    if ($last -and $last -match '(\d+)/(\d+) m') {
        $i = [int]$Matches[1]; $n = [int]$Matches[2]; $pct = [int](100 * $i / [Math]::Max($n, 1))
        $el = (Get-Date) - $t0; $eta = if ($i -gt 0) { [TimeSpan]::FromSeconds($el.TotalSeconds * ($n - $i) / $i) } else { [TimeSpan]::Zero }
        Write-Progress -Activity "Biggee API: $i / $n du an" -Status ("{0}% | con ~{1:mm\:ss} | {2}" -f $pct, $eta, $last.Trim()) -PercentComplete $pct
    } else { Write-Progress -Activity "Biggee API" -Status "dang khoi dong..." -PercentComplete 0 }
    $end = $lines | Where-Object { $_ -match '^(DONE|ERROR) biggee' } | Select-Object -Last 1
    if ($end) { Write-Progress -Activity "Biggee API" -Completed; Write-Host $end; break }
    Start-Sleep -Seconds 5
}
