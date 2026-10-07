# D:\market-data — cụm DỮ LIỆU THỊ TRƯỜNG & VĨ MÔ (gộp 14/09/2026)

Gộp 5 tool cùng bản chất (chuỗi thời gian long-format, merge/dedup incremental, chạy theo lịch) về một chỗ,
một thư viện chung, một runner, 2 task Task Scheduler thay cho 7 task cũ.

```
D:\market-data\
  mdlib.py               thư viện chung: log, cffi_session/new_session/get (giả Chrome, retry, WAF), vn_number/vn_date,
                         safe_to_csv (Excel đang mở -> .pending.csv), merge_long (gộp long-format), load_with_pending
  stale_check.py         kiểm tra độ tuổi master cho runner
  Run-Market.ps1         RUNNER DUY NHẤT: -Slot AM | PM  [-Only buoc1,buoc2]
  status-AM.txt / status-PM.txt, logs\market_<Slot>_*.log
  index-fetcher\         chỉ số + GTGD (VN vnstock/VCI, global yahoo, khu vực tencent/twse/naver/set/idx/bursa/jpx), khối ngoại (fetch_flows.py),
                         giá từng mã VN TradingView (tv_history.py -> tv-history.csv), reports\ (script phân tích), raw\
  market-valuation\      P/E, P/B, EPS thị trường VN (VNDirect) + ngành + từng mã + điều chỉnh (run_daily.py);
                         khu vực: region.py (sàn), tv_region.py (TradingView screener: định giá + cơ bản + forward), msci_region.py
  macro-fetcher\         IMF SDMX: VN theo tháng (fetch_macro.py), 12 nước (fetch_macro_region.py)
  nso-fetcher\           NSO PX-Web (pxweb.nso.gov.vn): niên giám 11 CSDL kinh tế + CPI tháng -> nso_master.csv / nso_timeseries.xlsx (fetch_nso.py);
                         Excel 'Biểu số liệu' báo cáo KT-XH tháng -> monthly-reports\ (fetch_monthly_reports.py)
  transmission-fetcher\  sơ đồ truyền dẫn tỷ giá -> lãi suất -> thanh khoản TTCK (SBV, FRED, VNDirect...), Build-Excel.ps1
  bond-pivot\            CSDL TPDN từ HNX CBIS (scripts\run_pipeline.py hằng tuần; run_backfill.ps1 đọc PDF, chạy tay khi có backlog)
  vsdc-accounts\         số tài khoản giao dịch NĐT theo tháng từ VSDC (pull_vsdc_accounts.py) -> vsdc_tk_ndt_table2.csv/.xlsx layout Table2 "Số TK mở mới"
```

## Lịch chạy (Task Scheduler)
| Task | Giờ | Bước (theo thứ tự, lỗi không chặn bước sau) |
|---|---|---|
| Market Data AM | 10:30 hằng ngày | valuation-vn (mỗi ngày); macro-vn, nso, nso-monthly, bonds, vsdc-accounts (thứ Hai); indices (thứ Bảy, retry 3, stale ≤ 6 ngày) |
| Market Data PM | 18:30 hằng ngày | transmission (retry 3, stale ≤ 4 ngày), flows, tvhistory (~12 phút), valuation-region, tradingview; msci (ngày 1–7); macro-region (thứ Hai) |
| Bond Pivot Backfill (dem) | 23:00, **đang tắt** | bật lại khi có đợt PDF kết quả chào bán mới |

Chạy tay một bước: `powershell -File D:\market-data\Run-Market.ps1 -Slot PM -Only flows,tradingview` (bỏ qua điều kiện lịch).
Popup cảnh báo chỉ khi bước Critical (valuation-vn, indices, transmission) lỗi hoặc dữ liệu cũ.

## Dùng mdlib trong script
```python
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # D:\market-data
from mdlib import log, cffi_session, safe_to_csv, merge_long
```
transmission-fetcher\common.py giờ chỉ còn phần riêng (ROOT, MASTER, COLS, row, merge_master) và re-export từ mdlib.

## Đường dẫn chéo (đã sửa khi dời)
market-valuation đọc `index-fetcher\indices-master.csv`, `index-fetcher\tv-history.csv`, `D:\bctc\fs-extractor\output_cap`;
transmission đọc `macro-fetcher\macro_vn_master.csv`, `D:\bctc\fs-extractor\output`, gọi `D:\bctc\pdf-detector\markitdown-tool\pdf2md.py`.

## 2 bẫy Windows (vẫn áp dụng)
1. PS 5.1: không dùng `& python ... 2>&1` (stderr bị bọc ErrorRecord, warning pandas thành lỗi) → Start-Process + redirect file, chỉ tin ExitCode.
2. Task phải có `-AllowStartIfOnBatteries` (laptop chạy pin thì task kẹt Queued).
Chi tiết từng tool: README.md trong thư mục con.

Hướng dẫn tổng: [D:\HUONG-DAN-TOOLS.md](../HUONG-DAN-TOOLS.md)
