<#
.SYNOPSIS
    Keo du lieu gia cuoc VHSS ConTex (charter rates) va MERGE cac date moi
    vao file CSV cu. Idempotent: chay nhieu lan chi them ngay chua co.

.NOTES
    Du lieu nam inline trong HTML duoi dang  var json = '{...}'.
    Gia tri = USD/ngay. Gia tri 0 trong nguon = khong cong bo -> de trong.
    Dung cho Windows PowerShell 5.1+ (khong can thu vien ngoai).
#>
[CmdletBinding()]
param(
    [string]$CsvPath,
    [string]$LogPath,
    [string]$Url = 'https://www.vhbs.de/index.php?id=79&L=1'
)

$ErrorActionPreference = 'Stop'

# Resolve thu muc script (PS 5.1: $PSScriptRoot co the rong trong param default khi chay -File)
$ScriptDir = if ($PSScriptRoot) { $PSScriptRoot }
             elseif ($MyInvocation.MyCommand.Path) { Split-Path -Parent $MyInvocation.MyCommand.Path }
             else { (Get-Location).Path }
if (-not $CsvPath) { $CsvPath = Join-Path $ScriptDir 'vhbs_contex.csv' }
if (-not $LogPath) { $LogPath = Join-Path $ScriptDir 'vhbs_contex.log' }

function Write-Log {
    param([string]$Message)
    $line = ('{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message)
    try { Add-Content -Path $LogPath -Value $line -Encoding UTF8 } catch {}
    Write-Host $line
}

# key trong JSON -> nhan cot (giu thu tu nay)
$TypeLabels = [ordered]@{
    c1100teu = '1100 TEU'; c1700teu = '1700 TEU'; c1800teu = '1800 TEU'
    c2500teu = '2500 TEU'; c2700teu = '2700 TEU'; c3000teu = '3000 TEU'
    c3500teu = '3500 TEU'; c4250teu = '4250 TEU'; c5700teu = '5700 TEU'
    c6500teu = '6500 TEU'; overall  = 'New ConTex'
}
$LabelToKey = @{}
foreach ($k in $TypeLabels.Keys) { $LabelToKey[$TypeLabels[$k]] = $k }

try {
    Write-Log "START  tai $Url"

    # ---- 1. Tai HTML ----
    $headers = @{
        'Accept'          = 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        'Accept-Language' = 'en-US,en;q=0.9'
        'Referer'         = 'https://www.vhbs.de/index.php?id=28&L=1'
    }
    $ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36'
    $resp = Invoke-WebRequest -Uri $Url -Headers $headers -UserAgent $ua -UseBasicParsing -TimeoutSec 30
    $html = $resp.Content

    # ---- 2. Trich cac block JSON ----
    $mset = [regex]::Matches($html, "var\s+json\s*=\s*'(\{.*?\})'\s*;", [System.Text.RegularExpressions.RegexOptions]::Singleline)
    if ($mset.Count -eq 0) { throw 'Khong tim thay du lieu JSON trong trang (cau truc co the da thay doi).' }

    # ---- 3. Gop series, uu tien series dai nhat ----
    $merged = @{}   # key -> hashtable(date -> value)
    foreach ($m in $mset) {
        $obj = $m.Groups[1].Value | ConvertFrom-Json
        foreach ($prop in $obj.PSObject.Properties) {
            $key = $prop.Name
            if ($key -eq 'maximum') { continue }
            $series = @{}
            foreach ($p in $prop.Value.PSObject.Properties) { $series[$p.Name] = $p.Value }
            if ($series.Count -eq 0) { continue }
            if (-not $merged.ContainsKey($key) -or $series.Count -gt $merged[$key].Count) {
                $merged[$key] = $series
            }
        }
    }

    # ---- 4. Xac dinh thu tu cot ----
    $orderedKeys = @($TypeLabels.Keys | Where-Object { $merged.ContainsKey($_) })
    $orderedKeys += @($merged.Keys | Where-Object { -not $TypeLabels.Contains($_) } | Sort-Object)
    $labels = @($orderedKeys | ForEach-Object { if ($TypeLabels.Contains($_)) { $TypeLabels[$_] } else { $_ } })
    $header = @('Date') + $labels

    # ---- 5. Doc file cu (neu co), giu nguyen header/thu tu cot cua file ----
    $existing = [ordered]@{}   # date -> string[] (cac o, theo header file)
    if (Test-Path $CsvPath) {
        $lines = Get-Content -Path $CsvPath -Encoding UTF8
        if ($lines.Count -gt 0) {
            $fileHeader = ($lines[0] -replace "^﻿", '') -split ','
            $header = $fileHeader
            $labels = $header[1..($header.Count - 1)]
            for ($i = 1; $i -lt $lines.Count; $i++) {
                if ([string]::IsNullOrWhiteSpace($lines[$i])) { continue }
                $cells = $lines[$i] -split ','
                $existing[$cells[0]] = $cells
            }
        }
    }

    # ---- 6. Them cac date MOI (chua co trong file) ----
    $allDates = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($k in $merged.Keys) { foreach ($d in $merged[$k].Keys) { [void]$allDates.Add($d) } }

    $added = 0
    foreach ($d in $allDates) {
        if ($existing.Contains($d)) { continue }
        $row = New-Object System.Collections.Generic.List[string]
        $row.Add($d)
        foreach ($label in $labels) {
            $key = $LabelToKey[$label]
            $val = $null
            if ($key -and $merged.ContainsKey($key)) { $val = $merged[$key][$d] }
            if ($null -eq $val -or $val -eq 0) { $row.Add('') } else { $row.Add([string]$val) }
        }
        $existing[$d] = $row.ToArray()
        $added++
    }

    # ---- 7. Ghi lai (sap xep theo ngay), UTF-8 BOM cho Excel ----
    $sortedDates = $existing.Keys | Sort-Object
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine(($header -join ','))
    foreach ($d in $sortedDates) { [void]$sb.AppendLine(($existing[$d] -join ',')) }
    $enc = New-Object System.Text.UTF8Encoding($true)
    [System.IO.File]::WriteAllText($CsvPath, $sb.ToString(), $enc)

    $latest = if ($sortedDates) { $sortedDates[-1] } else { '(rong)' }
    Write-Log ("DONE   them {0} ngay moi | tong {1} ngay | moi nhat {2} -> {3}" -f $added, $sortedDates.Count, $latest, $CsvPath)
}
catch {
    Write-Log ("ERROR  {0}" -f $_.Exception.Message)
    exit 1
}
