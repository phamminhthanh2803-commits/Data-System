# Build-Excel.ps1 - dung workbook Excel co Power Query tro thang vao 5 file CSV cua tool.
#
# Ket qua: transmission.xlsx - moi lan MO FILE la tu doc lai CSV moi nhat (RefreshOnFileOpen),
# khong can chay lai Python. Chi can chay script nay MOT LAN de tao file.
#
# Sheet Dashboard dung dung bo cuc 5 khoi cua ban HTML: bo cuc do make_dashboard.py xuat ra
# dashboard-layout.csv, script nay chi doc lai - sua BLOCKS trong Python la ca hai ban cung doi.
#
# Vi sao dung COM chu khong dung openpyxl: dinh nghia Power Query nam trong phan DataMashup
# (blob nhi phan trong xlsx), openpyxl khong ghi duoc.
#
# BAY QUAN TRONG: CSV cua pandas dung DAU CHAM lam thap phan, may dang locale Viet Nam
# (dau phay). Moi Table.TransformColumnTypes trong M deu phai chi dinh culture "en-US",
# neu khong Excel doc 4.62 thanh 462.

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition
$Out  = Join-Path $Root 'transmission.xlsx'

$fMaster = (Join-Path $Root 'transmission-master.csv')
$fWide   = (Join-Path $Root 'transmission-wide.csv')
$fNodes  = (Join-Path $Root 'transmission-nodes.csv')
$fNguon  = (Join-Path $Root 'nguon-chi-tieu.csv')
$fLayout = (Join-Path $Root 'dashboard-layout.csv')
foreach ($f in @($fMaster, $fWide, $fNodes, $fNguon, $fLayout)) {
    if (-not (Test-Path $f)) { throw "Khong thay $f - chay fetch_all.py roi make_dashboard.py truoc." }
}
if (Test-Path $Out) {
    try { [IO.File]::Open($Out, 'Open', 'ReadWrite', 'None').Close() }
    catch { throw "transmission.xlsx dang mo trong Excel - dong file roi chay lai." }
    # 10/09/2026: user da tu them sheet Bieu Do / Bo_Chi_Bao / BD_Calc vao workbook. Script nay
    # dung lai tu dau se XOA cac sheet do -> tu choi neu thay chung. Dung Upgrade-Excel.ps1 de cap nhat.
    $chk = New-Object -ComObject Excel.Application; $chk.Visible = $false; $chk.DisplayAlerts = $false
    $wbc = $chk.Workbooks.Open($Out, 0, $true); $has = $false
    foreach ($s in $wbc.Worksheets) { if ($s.Name -eq 'Bieu Do') { $has = $true } }
    $wbc.Close($false); $chk.Quit(); [Runtime.InteropServices.Marshal]::ReleaseComObject($chk) | Out-Null
    if ($has) { throw "transmission.xlsx da co sheet 'Bieu Do' do user tu lam - KHONG dung lai. Chay Upgrade-Excel.ps1." }
}

function M-Path([string]$p) { $p -replace '\\', '\\' }

# ---------- dinh nghia 4 truy van M ----------
$mNodes = @"
let
    Src = Csv.Document(File.Contents("$(M-Path $fNodes)"),[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Hdr = Table.PromoteHeaders(Src, [PromoteAllScalars=true]),
    Num = Table.TransformColumnTypes(Hdr,{{"n_obs", Int64.Type},{"last_value", type number},{"chg_1", type number},{"chg_5", type number},{"chg_20", type number},{"tre_ngay", Int64.Type}},"en-US"),
    Dt  = Table.TransformColumnTypes(Num,{{"last_date", type date}},"en-US")
in
    Dt
"@

$mWide = @"
let
    Src = Csv.Document(File.Contents("$(M-Path $fWide)"),[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Hdr = Table.PromoteHeaders(Src, [PromoteAllScalars=true]),
    Cols = List.RemoveFirstN(Table.ColumnNames(Hdr), 1),
    Num = Table.TransformColumnTypes(Hdr, List.Transform(Cols, each {_, type number}), "en-US"),
    Dt  = Table.TransformColumnTypes(Num, {{Table.ColumnNames(Hdr){0}, type date}}, "en-US"),
    Srt = Table.Sort(Dt, {{Table.ColumnNames(Hdr){0}, Order.Descending}})
in
    Srt
"@

$mMaster = @"
let
    Src = Csv.Document(File.Contents("$(M-Path $fMaster)"),[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Hdr = Table.PromoteHeaders(Src, [PromoteAllScalars=true]),
    Typ = Table.TransformColumnTypes(Hdr,{{"date", type date},{"value", type number}},"en-US"),
    Srt = Table.Sort(Typ, {{"series_id", Order.Ascending},{"date", Order.Ascending}})
in
    Srt
"@

# Nguon: giu nguyen kieu text - cot url la doi so cua HYPERLINK ben sheet Dashboard
$mNguon = @"
let
    Src = Csv.Document(File.Contents("$(M-Path $fNguon)"),[Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Hdr = Table.PromoteHeaders(Src, [PromoteAllScalars=true]),
    Typ = Table.TransformColumnTypes(Hdr,{{"series_id", type text},{"nguon", type text},{"url", type text},{"cong_thuc", type text}}),
    Fil = Table.ReplaceValue(Typ, null, "", Replacer.ReplaceValue, {"nguon","url","cong_thuc"})
in
    Fil
"@

$QUERIES = @(
    @{ Name = 'Node';   Sheet = 'Node';    M = $mNodes;  Note = 'Ban do node - moi chi tieu 1 dong, gia tri moi nhat' },
    @{ Name = 'Nguon';  Sheet = 'Nguon';   M = $mNguon;  Note = 'Nguon va duong dan kiem chung tung chi tieu' },
    @{ Name = 'Chuoi';  Sheet = 'Chuoi';   M = $mWide;   Note = 'Bang wide: ngay x chi tieu, moi nhat len dau' },
    @{ Name = 'DuLieu'; Sheet = 'Du lieu'; M = $mMaster; Note = 'Long-format day du de lam PivotTable' }
)

$layout = Import-Csv -Path $fLayout -Encoding UTF8

Write-Output "Mo Excel..."
$xl = New-Object -ComObject Excel.Application
$xl.Visible = $false
$xl.DisplayAlerts = $false
$ok = $false

try {
    if (Test-Path $Out) { Remove-Item $Out -Force }
    $wb = $xl.Workbooks.Add()
    while ($wb.Worksheets.Count -gt 1) { $wb.Worksheets.Item($wb.Worksheets.Count).Delete() }
    # BAY: Worksheets.Add() chen sheet moi len TRUOC sheet dang active, nen sau khi them
    # cac sheet truy van thi Item(1) KHONG con la sheet trong ban dau. Phai dat ten ngay tu
    # dau va tham chieu theo TEN, neu khong se ghi de dashboard len chinh bang du lieu.
    $wb.Worksheets.Item(1).Name = 'Dashboard'

    foreach ($q in $QUERIES) {
        Write-Output "  Tao truy van $($q.Name) ..."
        [void]$wb.Queries.Add($q.Name, $q.M)

        $ws = $wb.Worksheets.Add()
        $ws.Name = $q.Sheet

        $connStr = 'OLEDB;Provider=Microsoft.Mashup.OleDb.1;Data Source=$Workbook$;Location=' + $q.Name + ';Extended Properties=""'
        $conn = $wb.Connections.Add2("Query - $($q.Name)", $q.Note, $connStr, "SELECT * FROM [$($q.Name)]", 2)

        $lo = $ws.ListObjects.Add(0, $conn, $null, 1, $ws.Range("A1"))
        $lo.Name = $q.Name
        $lo.QueryTable.BackgroundQuery = $false
        $lo.QueryTable.Refresh($false) | Out-Null

        $conn.OLEDBConnection.BackgroundQuery = $false
        $conn.RefreshWithRefreshAll = $true
        $conn.OLEDBConnection.EnableRefresh = $true
        $conn.OLEDBConnection.RefreshOnFileOpen = $true

        $ws.Rows.Item(1).Font.Bold = $true
        [void]$ws.Range("A2").Select()
        $xl.ActiveWindow.FreezePanes = $true
        $ws.Columns.AutoFit() | Out-Null
        Write-Output "    -> $($lo.Range.Rows.Count) dong x $($lo.Range.Columns.Count) cot"
    }

    # ---------- sheet Dashboard: 5 khoi, moi dong mot chi tieu ----------
    $d = $wb.Worksheets.Item('Dashboard')
    $HEAD = @('CHI TIEU', 'MA CHUOI', 'GIA TRI', 'DON VI', 'NGAY', 'TRE (NGAY)', 'NGUON', 'NGUONG', 'DOC THE NAO')

    $d.Cells.Item(1, 1).Value2 = 'CHUOI TRUYEN DAN VND'
    $d.Cells.Item(2, 1).Value2 = 'Ty gia > chi phi von > can doi va cung tien > rang buoc ty le > du dia. ' +
        'So tu dong doc lai tu D:\market-data\transmission-fetcher moi lan mo file. Bam cot NGUON de mo trang goc kiem chung.'
    for ($j = 0; $j -lt $HEAD.Count; $j++) { $d.Cells.Item(4, $j + 1).Value2 = $HEAD[$j] }

    $r = 5
    $lastBlock = ''
    $n = 0
    foreach ($it in $layout) {
        if ($it.khoi -ne $lastBlock) {
            if ($lastBlock -ne '') { $r++ }
            $d.Cells.Item($r, 1).Value2 = $it.khoi.ToUpper()
            $hdr = $d.Range("A" + $r + ":I" + $r)
            $hdr.Interior.Color = 15921906
            $hdr.Font.Bold = $true
            $lastBlock = $it.khoi
            $r++
        }
        $d.Cells.Item($r, 2).Value2 = $it.series_id
        $d.Cells.Item($r, 1).Formula = "=IFERROR(XLOOKUP(B$r,Node[series_id],Node[series_name]),B$r)"
        # n_obs = 0 nghia la chuoi da khai bao nhung CHUA CO SO NAO. Neu lay thang last_value
        # thi Excel doi o rong thanh 0 va o do doc ra nhu mot gia tri that -> phai chan truoc.
        $co = "XLOOKUP(B$r,Node[series_id],Node[n_obs])>0"
        $d.Cells.Item($r, 3).Formula = "=IFERROR(IF($co,XLOOKUP(B$r,Node[series_id],Node[last_value]),""chua co""),""chua co"")"
        $d.Cells.Item($r, 4).Formula = "=IFERROR(XLOOKUP(B$r,Node[series_id],Node[unit]),"""")"
        $d.Cells.Item($r, 5).Formula = "=IFERROR(IF($co,XLOOKUP(B$r,Node[series_id],Node[last_date]),""""),"""")"
        $d.Cells.Item($r, 6).Formula = "=IFERROR(IF($co,XLOOKUP(B$r,Node[series_id],Node[tre_ngay]),""""),"""")"
        # url rong (chi tieu tinh ra / nhap tay) thi chi hien ten nguon kem cong thuc, khong bam duoc
        $d.Cells.Item($r, 7).Formula =
            "=IFERROR(IF(XLOOKUP(B$r,Nguon[series_id],Nguon[url])="""",XLOOKUP(B$r,Nguon[series_id],Nguon[nguon])&" +
            "IF(XLOOKUP(B$r,Nguon[series_id],Nguon[cong_thuc])="""","""","": ""&XLOOKUP(B$r,Nguon[series_id],Nguon[cong_thuc]))," +
            "HYPERLINK(XLOOKUP(B$r,Nguon[series_id],Nguon[url]),XLOOKUP(B$r,Nguon[series_id],Nguon[nguon]))),""-"")"
        if ($it.nguong) { $d.Cells.Item($r, 8).Value2 = $it.nguong }
        if ($it.doc_the_nao) { $d.Cells.Item($r, 9).Value2 = $it.doc_the_nao }
        $n++
        $r++
    }
    $last = $r - 1

    $d.Range("A1").Font.Size = 16
    $d.Range("A1").Font.Bold = $true
    $d.Range("A2").Font.Italic = $true
    $d.Range("A2").Font.ColorIndex = 16
    $d.Range("A4:I4").Font.Bold = $true
    $d.Range("A4:I4").Interior.Color = 14277081
    $d.Range("C5:C$last").NumberFormat = "#,##0.00"
    $d.Range("E5:E$last").NumberFormat = "dd/mm/yyyy"
    $d.Range("F5:F$last").NumberFormat = "0"
    $d.Range("F5:F$last").HorizontalAlignment = -4152
    $d.Range("G5:I$last").Font.Size = 10
    $d.Range("H5:I$last").Font.ColorIndex = 16
    $d.Columns.Item(1).ColumnWidth = 38
    $d.Columns.Item(2).ColumnWidth = 24
    $d.Columns.Item(3).ColumnWidth = 14
    $d.Columns.Item(4).ColumnWidth = 12
    $d.Columns.Item(5).ColumnWidth = 12
    $d.Columns.Item(6).ColumnWidth = 10
    $d.Columns.Item(7).ColumnWidth = 26
    $d.Columns.Item(8).ColumnWidth = 30
    $d.Columns.Item(9).ColumnWidth = 52
    $d.Rows.Item(3).RowHeight = 6

    # do so tre - chi tieu thang thuong tre 30 ngay nen chi bat den tu 40 ngay tro len
    $fc = $d.Range("F5:F$last").FormatConditions.Add(1, 5, "40")
    $fc.Font.Color = 255
    $fc.Font.Bold = $true

    $d.Activate()
    [void]$d.Range("A5").Select()
    $xl.ActiveWindow.FreezePanes = $true
    [void]$d.Range("A1").Select()

    # sap xep lai thu tu sheet
    $order = @('Dashboard','Node','Nguon','Chuoi','Du lieu')
    for ($i = 0; $i -lt $order.Count; $i++) {
        $wb.Worksheets.Item($order[$i]).Move($wb.Worksheets.Item($i + 1))
    }
    $wb.Worksheets.Item('Dashboard').Activate()

    $wb.SaveAs($Out, 51)
    $ok = $true
    Write-Output "Da luu: $Out  ($n chi tieu tren sheet Dashboard)"
}
finally {
    if ($wb) { $wb.Close($false) }
    $xl.Quit()
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($xl)
    [GC]::Collect()
}
if (-not $ok) { exit 1 }
