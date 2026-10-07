# macro-fetcher — CPI & vĩ mô Việt Nam theo tháng (IMF SDMX)

Kéo dữ liệu vĩ mô VN theo tháng từ **IMF SDMX API** (`api.imf.org`, không cần API key)
về 1 file CSV long-format, merge/dedup incremental. Chạy tự động hằng ngày 9h30
qua Task Scheduler (task **"VN Macro Daily"**).

## Vì sao IMF mà không phải GSO/NSO?
pxweb API của GSO đã chết sau khi GSO sáp nhập về Bộ Tài chính (thành NSO);
nso.gov.vn chỉ còn bài công bố dạng HTML, không có API. IMF nhận số liệu gốc
từ NSO/SBV, độ trễ chỉ ~1 tháng (T7/2026 đã có CPI T6/2026), API ổn định.

## Output: `macro_vn_master.csv`
Long format: `date (YYYY-MM), series_id, series_name, group, unit, value, source`

| Group | Series | Ghi chú |
|---|---|---|
| CPI | `CPI_ALL` + `CPI_CP01`..`CP12` (index 2024=100) + `_YOY`/`_MOM` (%) | CPI tổng + 12 nhóm COICOP, từ 2001. YoY/MoM tự tính từ index. CP11 (nhà hàng KS) IMF không có số |
| FX | `VND_USD_EOP`, `VND_USD_AVG` | Tỷ giá cuối kỳ / bình quân, từ 1995 |
| TRADE | `EXPORT_USD`, `IMPORT_USD`, `EXPORT_YOY`, `IMPORT_YOY`, `TRADE_BAL_USD` | XK FOB / NK CIF, từ 2006 |
| RESERVES | `FX_RESERVES_USD` | Dự trữ ngoại hối gồm vàng, từ 1996 |
| IIP | `IIP_IX`, `IIP_YOY` | Sản xuất công nghiệp — IMF trễ (đến ~2025-03) |

**Không có trên IMF cho VN:** M2/tín dụng, lãi suất (MFS), PPI → vẫn lấy từ SBV/NSO
thủ công (xem ViMo_Tracker). GDP quý có ở flow `IMF.STA,QNEA` nếu cần mở rộng.

## Files
- `fetch_macro.py` — script chính (chỉ dùng stdlib, không cần pandas)
- `run_daily.bat` — wrapper cho Task Scheduler, log ra `task_run.log`
- `fetch_log.txt` — log chi tiết từng lần chạy
- `macro_vn_master.csv` — file master

## Chạy tay
```
cd /d D:\market-data\macro-fetcher
python fetch_macro.py
```

## Cơ chế merge
Mỗi lần chạy fetch **toàn bộ lịch sử** từ 1995 (IMF hay revise số cũ), giá trị mới
ghi đè theo khóa `(date, series_id)`; dòng cũ không còn trong API vẫn được giữ.
Ghi file qua `.tmp` rồi replace để không hỏng master nếu đứt giữa chừng.

## Thêm series mới
Thêm entry vào `JOBS` trong `fetch_macro.py` (flow, key SDMX, mapping series).
Dò key bằng: `https://api.imf.org/external/sdmx/2.1/data/IMF.STA,{FLOW}/VNM...M?lastNObservations=2`
(số dấu chấm = số dimension - 1; xem `DIM_ORDER`).

## Vĩ mô KHU VỰC — `fetch_macro_region.py` (thêm 09/2026)

Cùng series như VN nhưng cho 12 nước (`VNM THA IDN MYS PHL SGP KOR CHN HKG JPN IND TWN`), 1 request/flow cho tất cả nước
(key `THA+IDN+....CPI._T+CP01..CP12.IX.M`), ra `macro_region_master.csv` long-format có thêm cột `country`.
Series id giống VN trừ tỷ giá đổi tên chung `FX_USD_EOP`/`FX_USD_AVG` (unit `XXX/USD` theo nước). YoY/MoM/cán cân tự tính bằng `add_derived` của `fetch_macro.py`.
TWN: IMF gần như không có (không phải thành viên) — chỉ vài series lẻ. HKG dự trữ dừng 2024-02, IIP chỉ IND/JPN/KOR.
Kéo full mỗi lần (~5 phút), chạy bởi task **"Region Daily" 18:30** (`D:\market-data\index-fetcher\Run-Region-Daily.ps1`). Chạy tay: `python fetch_macro_region.py`.


## Cập nhật 14/09/2026 — gộp vào hub
Task cũ `VN Macro Daily` (`run_daily.bat`) → nay `fetch_macro.py` = bước `macro-vn` (thứ Hai) trong **Market Data AM**, `fetch_macro_region.py` = bước `macro-region` (thứ Hai) trong **Market Data PM** (`D:\market-data\Run-Market.ps1`).
