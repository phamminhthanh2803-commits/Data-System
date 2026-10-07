# Index Fetcher — kéo dữ liệu giao dịch DAILY của các chỉ số thị trường

Kéo OHLCV **theo ngày** + **giá trị giao dịch (thanh khoản)** của các chỉ số thị trường VN, khu vực châu Á và toàn cầu, merge vào **một file master CSV** (long-format, SQL-friendly).

## Nguồn dữ liệu (cột `source` trong `indices.csv`)
| source | Thị trường / mã | Có `value`? | Lịch sử | Ghi chú kỹ thuật |
|---|---|---|---|---|
| `vnstock` | VN: VNINDEX, VN30, HNXINDEX, UPCOM | ✅ | 2004 | Hit thẳng VCI `gap-chart`, `accumulatedValue` → triệu VND (tự vá đổi đơn vị 2025-08-12). |
| `yahoo` | Mỹ: SP500, DJI, NASDAQ, RUT, VIX | ❌ | 1990 | yfinance. Không có turnover; **volume = 0 với hầu hết chỉ số châu Á** → tool ghi trống. |
| `tencent` | TQ: SSEC (sh000001), SZSEC (sz399001), CSI300 (sh000300) · HK: HSI, HSCEI, HSTECH | ✅ | SH 1990, HSI 1997, HSCEI 2006, HSTECH 2020 | `proxy.finance.qq.com/.../newfqkline/get`, `param=<sym>,day,<from>,<to>,640,qfq`; phần tử `[date,open,close,high,low,volume,{},turnover%,amount(万),...]` → amount/100 = triệu CNY/HKD. Tối đa 640 dòng/lần → chia cửa sổ 2 năm. Volume TQ = 手 ×100; HK không có volume. |
| `twse` | Đài Loan: TAIEX | ✅ | 1999 | `twse.com.tw/rwd/zh/afterTrading/FMTQIK?date=YYYYMM01&response=json`, 1 request = 1 tháng, ngày ROC (+1911). Nghỉ 3s/request kẻo bị chặn. Chỉ có close. |
| `naver` | Hàn Quốc: KOSPI, KOSDAQ | ✅ | 1990 | `finance.naver.com/sise/sise_index_day.naver?code=KOSPI&page=N`, 6 dòng/trang, euc-kr, cột 거래대금(백만) = triệu KRW, 거래량(천주) ×1000. Full ≈ 1.600 trang. Chỉ có close. |
| `set` | Thái Lan: SET, MAI | ✅ | **5 năm** | `set.or.th/api/set/index/<SET|mai>/chart-quotation?period=5Y` (10Y/MAX → 400). WAF Incapsula chặn gọi API trực tiếp: phải **GET trang HTML overview trước để nhận cookie `incap_ses_*`** rồi gọi API cùng session, bằng `curl_cffi` impersonate chrome (requests thường vẫn bị chặn). Chỉ có close. |
| `idx` | Indonesia: JCI (COMPOSITE), LQ45 | ✅ | 2020 | `idx.co.id/primary/TradingSummary/GetIndexSummary?date=YYYYMMDD` — **1 request/ngày**, Cloudflare → `curl_cffi`; đôi lúc trả "Just a moment" → đổi session + retry. Value IDR → triệu. Có H/L/C, không có open. |
| `bursa` | Malaysia: FBMKLCI | ✅ | ~2024-06 | Giá từ yahoo `^KLSE`; KL/GTGD **toàn thị trường** từ PDF `bursamalaysia.com/misc/missftp/securities/securities_equities_daily_scoreboard_YYYYMMDD.pdf` (pypdf): tổng Main + ACE + LEAP, cả khớp lệnh lẫn Direct Business; RM '000 → triệu RM. Ngày nghỉ = 404 (bỏ qua). |
| `jpx` | Nhật: N225 | ✅ | ~3 tháng gần nhất | Giá từ yahoo `^N225`; GTGD **toàn TSE** (Prime + Standard + Growth, cả ToSTNeT) từ PDF `est-set_YYYYMMDD.pdf` trên `jpx.co.jp/markets/statistics-equities/daily/` (index + `00-archives-NN.html`). JPX chỉ giữ ~3 tháng → **phải chạy đều để bồi chuỗi**. pypdf tách số thành mảnh (`2,831,128,1 00`) → `_jpx_numbers()` ghép lại đến khi đúng dạng `1,234,567`. |

**Đã thử và KHÔNG dùng được** (đừng mất thời gian lại): Eastmoney `push2his`, Sina, 163 money → máy này bị reset kết nối sau vài request (Tencent thì ổn); KRX data.krx.co.kr nay bắt đăng nhập (pykrx chết); SET/settrade gọi API thẳng → 403 Incapsula; PSE (Philippines) edge/pse.com.ph không lộ API turnover; SGX không tìm được endpoint thống kê ngày; NSE India 403 Akamai kể cả có cookie; stooq đòi JS challenge.

## Cấu trúc thư mục (dọn 14/09/2026)
- Gốc: chỉ còn script chạy theo lịch (`fetch_indices.py`, `fetch_flows.py`, `tv_history.py`), 2 runner PS1, config (`indices.csv`, `tv_symbols.txt`) và 4 master CSV (`indices-master`, `flows-master`, `fx-master`, `tv-history`).
- `reports\` — script phân tích một lần + ảnh kết quả (xem `reports\README.md`). `raw\` — CSV trung gian và dữ liệu kéo tay (khối ngoại khu vực bản tháng, ICI/JPX/FRED, screener meta...). `logs\` — giữ 15 log gần nhất.
- **Lịch `Run-Region-Daily.ps1` 18:30**: hằng ngày 4 bước (flows → tvhistory → region.py → tv_region.py); `msci_region.py` chỉ ngày 1–7 hằng tháng; `fetch_macro_region.py` chỉ thứ 2. Tổng ~15–20 phút, phần lớn là tv_history.

## File
- `indices.csv` — **danh sách chỉ số cần kéo**. Cột: `index_code,index_name,source,symbol,currency`.
- `fetch_indices.py` — script chính.
- `indices-master.csv` — **file kết quả** (long-format). Sinh tự động.
- `fx-master.csv` — cache tỷ giá `XXX=X` (số đơn vị bản địa / 1 USD) từ yfinance, long `date,currency,rate`. Sinh tự động.
- `fetch_flows.py` / `flows-master.csv` — dòng tiền khối ngoại + tự doanh VN (xem dưới).
- `Run-Pipeline.ps1` — runner cho Task Scheduler (log/retry/stale check). `Chay-hang-ngay.bat` — runner cũ.

## Cách chạy
```bat
python fetch_indices.py                    :: INCREMENTAL — mỗi mã kéo từ (ngày mới nhất của mã đó − 7) đến nay, merge + dedup
python fetch_indices.py --full             :: FULL — kéo lại toàn bộ lịch sử, dựng lại master (giữ chỉ số phái sinh derived-*)
python fetch_indices.py --only SET,MAI     :: chỉ kéo các mã liệt kê; mã chưa có trong master tự kéo full
python fetch_indices.py --full --only HSI  :: backfill lại lịch sử 1 mã (vd đổi source)
```
- Incremental tính **theo từng mã** → thêm mã mới vào `indices.csv` rồi chạy bình thường là tự backfill mã đó.
- Dedup theo `(date, index_code)` giữ bản mới nhất → chạy nhiều lần/ngày vẫn an toàn, tự vá gap.
- Backfill full lần đầu mất thời gian: IDX ~1.700 request (≈30 phút), TWSE ~330 tháng × 3s (≈17 phút), Naver ~2.800 trang (≈10 phút), Bursa ~600 PDF. Nên chạy `--only` theo nhóm.
- Excel đang mở master → ghi tạm `indices-master.pending.csv`, lần chạy sau tự nuốt lại.

## Định dạng output — `indices-master.csv`
Long-format, 1 dòng = 1 `(date, index_code)`, sắp xếp theo `(index_code, date)`:

| Cột | Ý nghĩa |
|-----|---------|
| `date` | YYYY-MM-DD |
| `index_code` | mã nội bộ (VNINDEX, SSEC, KOSPI...) |
| `index_name` | tên hiển thị |
| `source` | nguồn (bảng trên) |
| `open, high, low, close` | OHLC — nhiều nguồn khu vực chỉ có `close` (TWSE, Naver, SET), IDX không có open |
| `adj_close` | giá điều chỉnh (= close trừ yahoo) |
| `volume` | **số cổ phiếu** (đã quy về cổ phiếu: TQ 手×100, Hàn 천주×1000, Malaysia '000×1000). HK trống. |
| `value` | **giá trị giao dịch, đơn vị TRIỆU đồng tiền bản địa** (cột `currency`): triệu VND, triệu CNY, triệu HKD, triệu TWD, triệu KRW, triệu THB, triệu IDR, triệu MYR, triệu JPY. Chia 1.000 ra tỷ. |
| `currency` | VND / USD / CNY / HKD / TWD / KRW / THB / IDR / MYR / JPY |
| `value_usd` | `value` quy về **triệu USD** theo tỷ giá ngày (`fx-master.csv`, ffill cho ngày nghỉ) — dùng so thanh khoản giữa các thị trường. Tính lại toàn bộ mỗi lần chạy. |

**Phạm vi của `value`** (quan trọng khi so sánh): VN = giá trị khớp + thỏa thuận của sàn tương ứng; SSEC/SZSEC = toàn sàn SH / SZ; CSI300 = riêng rổ 300 mã; HSI/HSCEI/HSTECH = riêng rổ; TAIEX = toàn TWSE; KOSPI/KOSDAQ = toàn sàn; SET/MAI = toàn bảng; JCI = toàn IDX, LQ45 = riêng rổ; FBMKLCI = **toàn Bursa** (không phải 30 mã KLCI); N225 = **toàn TSE** (không phải 225 mã).

Encoding `utf-8-sig` (mở Excel không lỗi font).

## Dòng tiền khối ngoại + tự doanh — `fetch_flows.py` → `flows-master.csv`

Kéo **dòng tiền cấp thị trường** (không phải giá) từ VNDirect finfo:
- **Khối ngoại**: `v4/foreigns` (từ 08/2018) — có `total_room`/`current_room`
- **Tự doanh**: `v4/proprietary_trading` (từ 05/2022; VN30 chỉ từ 03/2026) — có `buy_val_pct`/`sell_val_pct`

4 rổ: VNINDEX, VN30, HNXINDEX (VNDirect gọi `HNX`), UPCOM. Chạy tự động cùng runner (bước 1b, non-fatal). Chạy tay: `python fetch_flows.py [--full]`.

`flows-master.csv` long-format, 1 dòng = `(date, index_code, flow_type)`, `flow_type` = `foreign`/`prop`. Đơn vị `*_val` = VND. Prop thường trễ 1 phiên so với foreign.

## Thêm chỉ số mới
Mở `indices.csv`, thêm 1 dòng với `source` phù hợp và `currency`:
- Yahoo: symbol trên finance.yahoo.com (`^FTSE`, `^GDAXI`...), chỉ có giá.
- VN qua VCI: `VNINDEX`, `VN30`, `HNXIndex`, `HNXUpcomIndex`, `VN100`...
- Tencent: `sh000xxx` / `sz399xxx` / `hkXXXX` (vd `sh000905` CSI500, `hkHSCI`).
- IDX: `IndexCode` trong GetIndexSummary (COMPOSITE, LQ45, IDX30, JII...).
- SET: `SET` / `mai` / `SET50` / `SET100`.

Rồi chạy `python fetch_indices.py --only <MÃ>` để backfill.

## Tự động — pipeline hằng tuần

**Task: `Index Fetcher Weekly` — Thứ 7, 09:00.** Gọi **`Run-Pipeline.ps1`**: log `logs\run_*.log` (giữ 30), retry 3 lần/60s, stale check (>6 ngày) cho 3 nhóm VN / Global / Khu vực, popup khi FAIL/STALE, `status.txt`.

Lưu ý JPX chỉ giữ ~3 tháng PDF → chạy tuần là đủ, nhưng nghỉ >3 tháng là mất chuỗi GTGD Nhật.

Chạy tay: `powershell -ExecutionPolicy Bypass -File .\Run-Pipeline.ps1`

### ⚠️ Hai cái bẫy đã gặp (đừng lặp lại)

1. **PowerShell 5.1 + `2>&1` trên native command** → mỗi dòng stderr bị bọc thành ErrorRecord; kèm `$ErrorActionPreference='Stop'` thì một `FutureWarning` vô hại của pandas cũng làm pipeline **báo fail oan và retry**. Runner dùng `Start-Process` + file redirect, chỉ tin `ExitCode`.

2. **`New-ScheduledTaskSettingsSet` mặc định bật `DisallowStartIfOnBatteries`** → trên laptop chạy pin, task kẹt **Queued vĩnh viễn, không chạy mà vẫn báo result 0**. Bắt buộc thêm `-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries`.

Đăng ký lại task:
```powershell
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -ExecutionPolicy Bypass -File "D:\market-data\index-fetcher\Run-Pipeline.ps1"' -WorkingDirectory 'D:\market-data\index-fetcher'
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At 9:00am
$set     = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName "Index Fetcher Weekly" -Action $action -Trigger $trigger -Settings $set -Force
```

## Phụ thuộc
`yfinance vnstock pandas requests` (có sẵn) + **`curl_cffi`** (SET/IDX/Bursa/JPX — impersonate Chrome qua WAF), **`pypdf`** (PDF Bursa/JPX), **`lxml`** (pandas.read_html cho Naver).
Trên máy này `pip.exe` bị Permission denied → cài bằng `python -m pip install --user curl_cffi pypdf lxml`.

## Liên quan
- `D:\market-data\market-valuation\adjust.py` ghi chỉ số phái sinh `VNINDEXADJ` (source `derived-mktval`) vào master này; từ 09/2026 đã sửa để **giữ nguyên mọi cột** (currency, value_usd) khi ghi lại.

## Dòng tiền KHU VỰC trong `fetch_flows.py` (thêm 09/2026)

`flows-master.csv` thêm 2 cột `currency`, `freq` (D/M) và 2 flow_type mới `institution`, `individual`. Đơn vị `*_val` = tiền bản địa tuyệt đối.

| index_code | Nguồn | Có gì | Lịch sử |
|---|---|---|---|
| KOSPI, KOSDAQ | Naver `investorDealTrendDay.naver?sosok=01/02` (억원 ×1e8) | net foreign/institution/individual | đầy đủ, ~1 trang/6 phiên |
| TAIEX | TWSE `fund/BFI82U?type=day` | buy/sell/net foreign (外資 + 外資自營商), prop (自營商), institution (投信) | 1 request/ngày, nghỉ 2s |
| SET, MAI | `set.or.th /api/set/market/{x}/investor-type` (ngày hiện tại, buy/sell/net 4 nhóm) + `investor-type-chart?period=1Y` (net THÁNG, freq M) | foreign/institution/prop/individual | ngày: bồi từ 09/2026; tháng: 12 tháng |
| JCI | IDX `GetStockSummary` cộng ForeignBuy/ForeignSell (số CP) từng mã × VWAP | foreign buy/sell/net val (xấp xỉ) + vol (chính xác) | từ 2020, 1 request ~1MB/ngày |
| FBMKLCI | PDF `trading_participation_investor_YYYYMMDD.pdf` (thống kê THÁNG, PDF tháng M mô tả tháng M−1) | foreign (inst+retail), institution, individual buy/sell/net, freq M | từ 10/2025 |

Chạy: `python fetch_flows.py` (VN + khu vực) · `--region-only` · `--vn-only` · `--only JCI,SET` · `--full`.
SET/Tencent chỉ có số NGÀY HIỆN TẠI → task **"Region Daily" 18:30** (`Run-Region-Daily.ps1`) chạy cả flows + `market-valuation
egion.py` + `macro-fetcheretch_macro_region.py`; task tuần T7 vẫn chạy index. Chưa có: Philippines, Ấn Độ (NSE/NSDL chặn), Singapore.

## Lịch sử giá từng cổ phiếu từ TradingView — `tv_history.py` (thêm 14/09/2026)
TradingView không có REST cho nến; dùng websocket qua thư viện `tvDatafeed` (cài `python -m pip install --user git+https://github.com/rongardF/tvdatafeed.git`), **không cần login**, trả TOÀN BỘ lịch sử daily khi `n_bars=10000` (VNINDEX từ 07/2000, VIC từ 2007, HKEX:5 từ 2002, Samsung/TSMC/PTT/BBCA từ 2005–06). Chỉ có OHLC + volume, KHÔNG có giá trị giao dịch → `value_approx = close × volume`. Giá đã điều chỉnh chia tách/quyền (khớp VCI trong ±0,5%). Ký hiệu: `HOSE:VIC`, `HNX:SHS`, `UPCOM:ACV`, `KRX:005930`, `TWSE:2330`, `SET:PTT`, `IDX:BBCA`, `HKEX:5` (không phải 0005), `MYX:MAYBANK`, `TSE:7203`, `SSE:600519`. Websocket đôi khi rớt → script tự thử lại 3 lần. Danh sách mã trong `tv_symbols.txt`; output `tv-history.csv` (long, dedup theo date + tv_symbol, incremental 60 nến cho mã đã có).
**Từ 14/09/2026: `tv_symbols.txt` = TOÀN BỘ cổ phiếu VN (1.233 mã: HOSE 402, HNX 263, UPCoM 568, lấy từ TradingView screener `type=stock`) và `tv-history.csv` là nguồn giá cổ phiếu chính thay cho VCI gap-chart.** `market-valuationdjust.py::fetch_prices()` đọc file này trước (fallback VCI nếu thiếu mã hoặc file cũ >7 ngày). Chạy hằng ngày trong `Run-Region-Daily.ps1` (bước tvhistory, incremental 60 nến/mã ≈ 15 phút); script tự lưu mỗi 100 mã nên bị ngắt giữa chừng không mất dữ liệu. Chỉ số VN (VNINDEX/HNX/UPCOM) VẪN dùng VCI vì TradingView không có giá trị giao dịch.


## Cập nhật 14/09/2026 — gộp vào hub
Task cũ `Index Fetcher Weekly` (T7 9:00, `Run-Pipeline.ps1`) và `Region Daily` (18:30, `Run-Region-Daily.ps1`) đã bỏ → bước `indices` (T7) trong **Market Data AM 10:30** và `flows, tvhistory` trong **Market Data PM 18:30** của `D:\market-data\Run-Market.ps1`. `log/_cffi_session/safe_to_csv` import từ `..\mdlib.py`.
