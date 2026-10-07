# Bond Pivot - dem: doc PDF ket qua chao ban, boc bang to chuc lien quan
# Het backlog thi thoat ngay (vai giay) - khong can tat task
Set-Location "D:\market-data\bond-pivot"
$env:PYTHONIOENCODING = "utf-8"
python scripts\extract_arrangers.py --limit 400 2>&1 | Out-File -Append -Encoding utf8 logs\backfill.log
exit $LASTEXITCODE
