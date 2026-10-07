# Upgrade-Excel.ps1 - nang cap transmission.xlsx DA CO (giu nguyen sheet user tu them) cho khop
# voi so chuoi moi. KHONG dung Build-Excel.ps1 nua vi no dung lai tu dau va xoa sheet Bieu Do.
#
# Lam gi:
#  1. Sao luu vao _archive\transmission.before-upgrade-<ngay>.xlsx
#  2. RefreshAll de bang Node/Chuoi/DuLieu doc CSV moi (them ~30 chuoi)
#  3. BD_Calc: doi moi cong thuc tu khoang CO DINH ('Chuoi'!B1:EW1, 2:6685, Node 2:113) sang
#     THAM CHIEU BANG + mang dong (Chuoi[#Headers], Chuoi[date], Node[series_id]...) -> chuoi moi,
#     ngay moi tu vao, khong phai keo cong thuc. Chart tro qua ten X1..X5 / Y1..Y5 = vung spill.
#  4. Bieu Do: cung thay tham chieu; danh sach chon = BD_Calc!$B$2#
#  5. Bo_Chi_Bao: sua tham chieu + them 6 bo chi bao moi
#  6. Dashboard: thay ldr_broad_listed -> ldr_tt22_listed, chen dong cho chuoi moi theo dung khoi
#
#     powershell -File Upgrade-Excel.ps1     (dong Excel truoc)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Xlsx = Join-Path $Root 'transmission.xlsx'
$Bak  = Join-Path $Root ('_archive\transmission.before-upgrade-' + (Get-Date -Format 'yyyyMMdd-HHmm') + '.xlsx')

try { [IO.File]::Open($Xlsx, 'Open', 'ReadWrite', 'None').Close() }
catch { throw "transmission.xlsx dang mo trong Excel - dong file roi chay lai." }
New-Item -ItemType Directory -Force (Split-Path $Bak) | Out-Null
Copy-Item $Xlsx $Bak -Force
Write-Host "Sao luu: $Bak"

$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false; $xl.DisplayAlerts = $false
$wb = $xl.Workbooks.Open($Xlsx)

function Sheet($n) { $wb.Worksheets.Item($n) }

# ---------------------------------------------------------------- 2. refresh
Write-Host "RefreshAll..."
$wb.RefreshAll(); $xl.CalculateUntilAsyncQueriesDone()
Start-Sleep -Seconds 5
$node = Sheet('Node'); $chuoi = Sheet('Chuoi')
Write-Host ("Node rows: " + $node.ListObjects.Item(1).ListRows.Count + " | Chuoi cols: " + $chuoi.ListObjects.Item(1).ListColumns.Count)

# ---------------------------------------------------------------- 3. BD_Calc
$c = Sheet('BD_Calc')
$c.Range('A2:AH6685').ClearContents() | Out-Null
$c.Range('A2').Formula2 = '=TRANSPOSE(INDEX(Chuoi[#Headers],1,SEQUENCE(1,COLUMNS(Chuoi[#Headers])-1,2)))'
$c.Range('B2').Formula2 = '=IFERROR(XLOOKUP($A$2#,Node[series_id],Node[series_name]),$A$2#)&" ["&$A$2#&"]"'
$c.Range('D2').Formula2 = '=INDEX(Chuoi[date],ROWS(Chuoi[date])+1-SEQUENCE(ROWS(Chuoi[date])))'
$raw = @('E','F','G','H','I'); $fcell = @('$F$5','$F$6','$F$7','$F$8','$F$9')
for ($i = 0; $i -lt 5; $i++) {
    $f = "=IF('Bieu Do'!" + $fcell[$i] + "=0,NA(),LET(v,INDEX(Chuoi[#Data],ROWS(Chuoi[date])+1-SEQUENCE(ROWS(Chuoi[date])),'Bieu Do'!" + $fcell[$i] + "),IF(v="""",NA(),v)))"
    $c.Range($raw[$i] + '2').Formula2 = $f
}
# loc theo khung: V/W, X/Y, Z/AA, AB/AC, AD/AE
$locD = @('V','X','Z','AB','AD'); $locV = @('W','Y','AA','AC','AE')
for ($i = 0; $i -lt 5; $i++) {
    $r = '$' + $raw[$i] + '$2#'
    $cond = "ISNUMBER($r)*(`$D`$2#>='Bieu Do'!`$B`$17)*(`$D`$2#<='Bieu Do'!`$B`$18)"
    $c.Range($locD[$i] + '2').Formula2 = "=IFERROR(FILTER(`$D`$2#,$cond),"""")"
    $c.Range($locV[$i] + '2').Formula2 = "=IFERROR(FILTER($r,$cond),"""")"
}
# base index 100: AH2..AH6
for ($i = 0; $i -lt 5; $i++) {
    $v = '$' + $locV[$i] + '$2#'
    $c.Range('AH' + (2 + $i)).Formula2 = "=IF(COUNT($v)=0,1,IF(INDEX($v,1)=0,1,INDEX($v,1)))"
}
# du lieu ve chart: K/L, M/N, O/P, Q/R, S/T
$cx = @('K','M','O','Q','S'); $cy = @('L','N','P','R','T')
for ($i = 0; $i -lt 5; $i++) {
    $d = '$' + $locD[$i] + '$2#'; $v = '$' + $locV[$i] + '$2#'; $b = '$AH$' + (2 + $i)
    $c.Range($cx[$i] + '2').Formula2 = "=$d"
    $c.Range($cy[$i] + '2').Formula2 = "=IF('Bieu Do'!`$B`$15=""Index 100 tai dau ky"",$v/$b*100,$v)"
    $c.Range($cy[$i] + '1').Formula = "='Bieu Do'!`$G`$" + (5 + $i)
}
$c.Range('AJ1').Value2 = "Sheet tinh toan cho 'Bieu Do'. Khong sua tay. Mang dong tu bang Chuoi/Node: chuoi moi va ngay moi tu vao. E:I raw, V:AE loc theo khung, K:T du lieu ve chart (ten chart_x1..5/chart_y1..5), AH base Index."

# ten cho chart
for ($i = 1; $i -le 5; $i++) {
    foreach ($nm in @("chart_x$i", "chart_y$i")) { try { $wb.Names.Item($nm).Delete() } catch {} }
    # thu dau # truoc (Formula2 hieu), khong duoc thi ANCHORARRAY (ten noi bo cua #)
    foreach ($pair in @(@("chart_x$i", $cx[$i - 1]), @("chart_y$i", $cy[$i - 1]))) {
        $ok = $false
        foreach ($ref in @(('=BD_Calc!$' + $pair[1] + '$2#'), ('=ANCHORARRAY(BD_Calc!$' + $pair[1] + '$2)'), ('=BD_Calc!$' + $pair[1] + '$2:$' + $pair[1] + '$20000'))) {
            try { $wb.Names.Add($pair[0], $ref) | Out-Null; $ok = $true; Write-Host ("  name " + $pair[0] + " = " + $ref); break } catch {}
        }
        if (-not $ok) { throw ("khong tao duoc ten " + $pair[0]) }
    }
}

# ---------------------------------------------------------------- 4. Bieu Do
$b = Sheet('Bieu Do')
$rep = @(
    @('BD_Calc!$A$2:$A$154', 'BD_Calc!$A$2#'), @('BD_Calc!$B$2:$B$154', 'BD_Calc!$B$2#'),
    @('Node!$C$2:$C$113', 'Node[series_id]'), @('Node!$D$2:$D$113', 'Node[series_name]'),
    @('Node!$E$2:$E$113', 'Node[unit]'), @('Node!$I$2:$I$113', 'Node[n_obs]'),
    @("'Chuoi'!`$A`$2:`$A`$6685", 'Chuoi[date]'), @("'Chuoi'!`$B`$1:`$EW`$1", 'Chuoi[#Headers]')
)
foreach ($p in $rep) { $b.Cells.Replace($p[0], $p[1], 2, 1, $false, $false, $false, $false) | Out-Null }
# thong ke trong khung: cot L,N,P,R,T -> spill
$stat = @('L','N','P','R','T')
for ($i = 0; $i -lt 5; $i++) {
    $r = 53 + $i; $col = 'BD_Calc!$' + $stat[$i] + '$2#'
    $b.Range("B$r").Formula2 = "=IF(COUNT($col)=0,"""",INDEX($col,1))"
    $b.Range("C$r").Formula2 = "=IF(COUNT($col)=0,"""",INDEX($col,COUNT($col)))"
    $b.Range("F$r").Formula2 = "=IF(COUNT($col)=0,"""",AGGREGATE(5,6,$col))"
    $b.Range("G$r").Formula2 = "=IF(COUNT($col)=0,"""",AGGREGATE(4,6,$col))"
    $b.Range("H$r").Formula2 = "=IF(COUNT($col)=0,"""",AGGREGATE(1,6,$col))"
}
$b.Range('B17').Formula2 = '=IF($B$12="Tuy chon",$B$13,IFERROR(SWITCH($B$12,"1 thang",EDATE($B$18,-1),"3 thang",EDATE($B$18,-3),"6 thang",EDATE($B$18,-6),"1 nam",EDATE($B$18,-12),"2 nam",EDATE($B$18,-24),"3 nam",EDATE($B$18,-36),"5 nam",EDATE($B$18,-60),"10 nam",EDATE($B$18,-120),"YTD",DATE(YEAR($B$18),1,1),MIN(Chuoi[date])),MIN(Chuoi[date])))'
$b.Range('B18').Formula2 = '=IF($B$12="Tuy chon",$B$14,MAX(Chuoi[date]))'
$b.Range('B13').Formula2 = '=EDATE(MAX(Chuoi[date]),-12)'
$b.Range('B14').Formula2 = '=MAX(Chuoi[date])'
$dv = $b.Range('B5:B9').Validation; $dv.Delete()
$okv = $false
foreach ($ref in @('=BD_Calc!$B$2#', '=ANCHORARRAY(BD_Calc!$B$2)', '=BD_Calc!$B$2:$B$1000')) { try { $dv.Add(3, 1, 1, $ref) | Out-Null; $okv = $true; Write-Host "  validation = $ref"; break } catch { $dv.Delete() } }
$b.Range('A2').Value2 = 'Chon toi da 5 chi tieu va khung thoi gian. Danh sach chuoi tu bang Chuoi (moi lan refresh la co chuoi moi).'

# chart -> ten
$ch = $b.ChartObjects('TimeSeries').Chart
$wbn = $wb.Name
for ($i = 1; $i -le 5; $i++) {
    $ch.SeriesCollection($i).Formula = "=SERIES(""Chi tieu $i"",'$wbn'!chart_x$i,'$wbn'!chart_y$i,$i)"
}

# ---------------------------------------------------------------- 5. Bo_Chi_Bao
$bo = Sheet('Bo_Chi_Bao')
$bo.Cells.Replace('Node!$C$2:$C$113', 'Node[series_id]', 2, 1, $false, $false, $false, $false) | Out-Null
$bo.Cells.Replace('Node!$D$2:$D$113', 'Node[series_name]', 2, 1, $false, $false, $false, $false) | Out-Null
# bo "Du tru ngoai hoi" dung fdi_disbursed (rong) -> FDI theo BOP
for ($r = 2; $r -le 40; $r++) { for ($k = 2; $k -le 6; $k++) { if ($bo.Cells.Item($r, $k).Value2 -eq 'fdi_disbursed') { $bo.Cells.Item($r, $k).Value2 = 'fdi_inflow_bop' } } }
$sets = @(
    @('Can can thanh toan (BOP, quy)', 'current_account_bop', 'fdi_net_bop', 'fii_net_bop', 'bop_errors', 'bop_overall', 'trieu USD - loi va sai sot am = von chay ra khong ghi nhan'),
    @('Lai suat cho vay tung NH cong bo', 'lending_rate_big4', 'lending_rate_jsc', 'lend_avg_bid', 'lend_avg_eib', 'lend_avg_vib', '%/nam - TB don gian, tu 10/2025'),
    @('Gia von Vietcombank', 'lending_rate_avg', 'deposit_rate_avg_vcb', 'lending_deposit_spread', 'lending_spread_net_vcb', '', '%/nam - huy dong BQ = cho vay - chenh lech'),
    @('Dau tu cong (Kho bac) vs NHNN bom', 'public_inv_month', 'public_inv_ytd', 'omo_net_outstanding', '', '', 'ty VND - tien ngoai sinh vao he thong'),
    @('LDR Thong tu 22 vs NHNN', 'ldr_system', 'ldr_tt22_listed', 'loan_deposit_listed', 'ldr_cap', '', '% - tran 85%'),
    @('CAR tung NH lon (CBTT TT41)', 'car_vcb', 'car_bid', 'car_ctg', 'car_tcb', 'car_vpb', '% - hop nhat, nua nam')
)
$r0 = 2; while ($r0 -le 40 -and $bo.Cells.Item($r0, 1).Value2) { $r0++ }
foreach ($s in $sets) {
    if ($r0 -gt 40) { break }
    if ($bo.Cells.Item($r0, 1).Value2 -like 'Huong dan*') { $bo.Rows($r0).Insert() | Out-Null }
    for ($k = 0; $k -lt 7; $k++) { $bo.Cells.Item($r0, 1 + $k).Value2 = $s[$k] }
    $bo.Range("I2:M2").Copy() | Out-Null; $bo.Range("I$r0").PasteSpecial(-4123) | Out-Null
    $r0++
}
try { $xl.CutCopyMode = 0 } catch {}

# ---------------------------------------------------------------- 6. Dashboard
$d = Sheet('Dashboard')
function Find-Row($sheet, $sid) { for ($r = 5; $r -le 200; $r++) { if ($sheet.Cells.Item($r, 2).Value2 -eq $sid) { return $r } }; return 0 }
function Insert-After($sheet, $afterSid, $newSids) {
    $r = Find-Row $sheet $afterSid; if ($r -eq 0) { Write-Host "  ! khong thay $afterSid"; return }
    foreach ($sid in $newSids) {
        if ((Find-Row $sheet $sid) -gt 0) { continue }
        $sheet.Rows($r + 1).Insert() | Out-Null
        $sheet.Rows($r).Copy() | Out-Null; $sheet.Rows($r + 1).PasteSpecial(-4123) | Out-Null   # cong thuc + format
        $sheet.Cells.Item($r + 1, 2).Value2 = $sid
        $sheet.Cells.Item($r + 1, 8).Value2 = ''; $sheet.Cells.Item($r + 1, 9).Value2 = ''
        $r++
    }
}
# chen tu duoi len de khong lech
Insert-After $d 'ldr_system'          @('ldr_tt22_listed')          # khoi 05 (dong ldr_system thu hai - xu ly duoi)
$r = Find-Row $d 'ldr_broad_listed'; if ($r -gt 0) { $d.Cells.Item($r, 2).Value2 = 'ldr_tt22_listed' }
Insert-After $d 'bank_deposits'       @('public_inv_month', 'public_inv_ytd')
Insert-After $d 'lending_deposit_spread' @('lending_rate_big4', 'lending_rate_jsc', 'deposit_rate_avg_vcb', 'lending_spread_net_vcb', 'lend_avg_bid', 'lend_avg_agr', 'lend_avg_eib', 'lend_avg_vib')
Insert-After $d 'fii_net_val'         @('fdi_inflow_bop', 'fdi_realized_vnd', 'current_account_bop', 'bop_errors', 'bop_overall')
# khoi 05: dong ldr_tt22_listed vua chen sau ldr_system CUA KHOI 04 (Find-Row tra ve dong dau) -> chuyen sang khoi 05
$rA = Find-Row $d 'ldr_tt22_listed'                      # dong o khoi 04 (da co, tu ldr_broad)
$rows = @(); for ($r = 5; $r -le 250; $r++) { if ($d.Cells.Item($r, 2).Value2 -eq 'ldr_tt22_listed') { $rows += $r } }
if ($rows.Count -ge 2) {
    # dong thu 2 la dong vua chen (nam trong khoi 04) -> xoa; roi chen lai sau ldr_system cua khoi 05
    $d.Rows($rows[1]).Delete() | Out-Null
    $r5 = 0; for ($r = 5; $r -le 250; $r++) { if ($d.Cells.Item($r, 2).Value2 -eq 'ldr_system') { $r5 = $r } }   # lan cuoi = khoi 05
    $d.Rows($r5 + 1).Insert() | Out-Null; $d.Rows($r5).Copy() | Out-Null; $d.Rows($r5 + 1).PasteSpecial(-4123) | Out-Null
    $d.Cells.Item($r5 + 1, 2).Value2 = 'ldr_tt22_listed'
    $d.Cells.Item($r5 + 1, 8).Value2 = 'Tran 85%, so hop nhat chua loai Kho bac'
    $d.Cells.Item($r5 + 1, 9).Value2 = 'Cao hon so NHNN vi khong co QTDND va NH nuoc ngoai keo xuong; sat 85% la nhom niem yet het room.'
}
try { $xl.CutCopyMode = 0 } catch {}
$xl.Calculate()

$wb.Save(); $wb.Close($false); $xl.Quit()
[Runtime.InteropServices.Marshal]::ReleaseComObject($xl) | Out-Null
Write-Host "Xong: $Xlsx"
