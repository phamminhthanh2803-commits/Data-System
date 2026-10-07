# MARKET VALUATION FETCHER — Định giá toàn thị trường (VNDirect tính sẵn)

## Tool làm gì

Kéo chỉ số định giá **toàn thị trường** theo NGÀY từ API công khai của VNDirect
(`api-finfo.vndirect.com.vn/v4/ratios`) — số liệu **bên thứ 3 đã tính sẵn**,
KHÔNG phải tự gộp từng mã như FS Extractor. Không cần API key, kéo full lịch sử ~1 phút.

- **4 rổ**: VNINDEX, HNX, UPCOM, VN30
- **5 chỉ tiêu gốc** (VNDirect tính): P/E, P/B, P/S, Tỷ suất cổ tức, Vốn hóa
- **Lịch sử**: P/E, P/B, P/S, cổ tức từ **12/2017**; Vốn hóa từ **07/2019**

## Output

| File | Nội dung |
|---|---|
| `valuation-master.csv` | Long-format gốc: `code, date, ratio, value` — merge/dedup incremental |
| `valuation-wide.csv` | Wide theo (code, date), gồm cột gốc + cấu phần suy ra |

Cột trong `valuation-wide.csv`:

- Gốc: `pe, pb, ps, div_yield, marketcap` (marketcap đơn vị VND)
- Suy ra từ số VNDirect (đơn vị VND, TTM):
  - `ln_ttm` = marketcap / pe → **tổng LNST TTM toàn thị trường**
  - `gtss` = marketcap / pb → **tổng giá trị sổ sách (VCSH)**
  - `doanh_thu_ttm` = marketcap / ps
  - `co_tuc_ttm` = div_yield × marketcap → **tổng cổ tức tiền TTM**
  - `earnings_yield` = 1/pe
  - `roe_ttm` = **pb / pe** → **ROE TTM toàn thị trường** (= LN_TTM/VCSH = EPS/BVPS). Đơn vị thập phân (0.15 = 15%). Dùng pb/pe thay vì ln_ttm/gtss để có lịch sử từ **12/2017** (marketcap chỉ từ 07/2019); marketcap tự triệt tiêu nên 2 cách cho kết quả y hệt.
- Join với `D:\market-data\index-fetcher\indices-master.csv` (nếu có):
  - `close` = điểm đóng cửa chỉ số
  - `eps_index` = close / pe → **EPS thị trường theo điểm chỉ số**
  - `bvps_index` = close / pb → **BVPS thị trường theo điểm chỉ số**

## Cách chạy

**Auto**: Task Scheduler "Market Valuation Daily" chạy **10h30 hằng ngày** (sau
Index Fetcher 10h) → `Chay-hang-ngay.bat` → `run_daily.py`: 4 bước tuần tự
(thị trường → ngành → từng mã → điều chỉnh loại trừ), log tại `logs\YYYY-MM-DD.log`.
1 bước lỗi không chặn bước sau; cuối log có dòng `KET THUC: OK het / LOI: ...`.

Config người dùng tự sửa (không cần đụng code):
- `tickers.txt`   — danh sách mã cho stocks.py (mỗi dòng 1 mã; trống = bỏ qua bước 3)
- `nhom-loai.txt` — nhóm mã loại trừ cho adjust.py (1 dòng; trống = bỏ qua bước 4)

Chạy tay từng phần:
```
Chay-hang-ngay.bat                 # chạy cả pipeline ngay (incremental, ~1 phút)
python fetch_valuation.py --full   # kéo lại toàn bộ lịch sử 1 phần (khi nghi hỏng)
```

## Định giá theo ngành — `sectors.py`

```
python sectors.py           # incremental (chỉ ~5 request)
python sectors.py --full    # kéo lại toàn bộ lịch sử (~550k dòng, vài phút)
```

VNDirect tính sẵn **55 mã ngành ICB** (group INDUSTRY, trộn cấp 2 + cấp 3) với đủ
5 chỉ tiêu như cấp thị trường: P/E, P/B, P/S, tỷ suất cổ tức, vốn hóa — theo ngày,
từ 12/2017 (vốn hóa từ ~07/2019). Output:

- `sectors-master.csv` — long-format gốc
- `sectors-wide.csv` — wide theo (code, date), kèm `ten_nganh`, `cap_icb` (2/3)
  + cấu phần suy ra: `ln_ttm`, `gtss`, `doanh_thu_ttm`, `co_tuc_ttm`, `roe_ttm` (= pb/pe, ROE TTM ngành)

Lưu ý: ngành chỉ có 1 nhánh con thì số cấp 2 = cấp 3 (vd 8300 = 8350 Ngân hàng).
Ngoài ra group INDEX của VNDirect còn có VN100, VNFIN, VNDIAMOND, HNXCON... nếu
cần rổ nào thì thêm code vào CODES trong fetch_valuation.py.

Nguồn thay thế bottom-up: FS Extractor `fsx.py cap` tự gộp `industry_valuation.csv`
theo 4 cấp ICB từ các mã đã kéo — dùng khi cần ngành hẹp hơn cấp 3 hoặc tự chọn rổ mã.

## Định giá từng mã riêng lẻ — `stocks.py`

```
python stocks.py VNM FPT MWG HPG      # kéo các mã chỉ định
python stocks.py --file tickers.txt   # đọc danh sách từ file
python stocks.py VNM --full           # kéo lại full lịch sử
```

Cùng nguồn VNDirect (group STOCK), theo ngày: **P/E, P/B, P/S, tỷ suất cổ tức,
vốn hóa** (từ 12/2017) + **BVPS** (VNDirect chỉ có từ 12/2022). Suy ra: `ln_ttm`
(LNST TTM), `vcsh`, `doanh_thu_ttm`, `co_tuc_ttm`, `roe_ttm` (= pb/pe, ROE TTM mã),
`gia` (= bvps×pb, khớp giá đóng cửa), `eps` (= gia/pe), `roe_src` (nguồn của roe_ttm).
Output: `stocks-master.csv` (cache incremental — mã mới tự kéo full, mã cũ chỉ kéo ngày
mới) + `stocks-wide.csv`.

**ROE mã lỗ (fallback FS/VCI):** mã thua lỗ TTM bị VNDirect ẩn P/E → `roe_ttm=pb/pe`
trống. Tool tự lấp: lấy **LNST TTM từ FS Extractor** (VCI, `output_cap*\market_cap_daily.csv`,
cột `lnst_ttm_ty`) làm tử số, **VCSH = marketcap/pb của VNDirect** làm mẫu số → `roe_ttm`
**âm** đúng bản chất. Cột `roe_src` đánh dấu: `vndirect` (pb/pe) · `fs_vci` (fallback mã lỗ)
· trống (không lấp được). Chỉ lấp cho mã đã có trong FS Extractor; mã lỗ chưa kéo FS thì
`roe_ttm` vẫn trống — kéo bằng `python fsx.py cap <mã> --out output_cap` bên `D:\bctc\fs-extractor`.
`ln_ttm`/`eps` vẫn trống ngày mã lỗ (chỉ `roe_ttm` được lấp). EPS/giá chỉ từ 12/2022
theo BVPS. Muốn EPS forward hoặc theo quý chuẩn BCTC thì dùng FS Extractor bctc.

## EPS thị trường TUYỆT ĐỐI (VND/CP) — `market_eps.py`

```
python market_eps.py           # incremental (nằm trong pipeline hằng ngày, bước 5/5)
python market_eps.py --full    # tính lại từ 2019-07-19 (~45 phút, nên chạy nền)
```

**EPS tuyệt đối = NPATMI TTM toàn thị trường ÷ Σ số CP lưu hành** (khác `eps_index`
theo điểm chỉ số trong valuation-wide):
- Số CP từng mã = vốn hóa ÷ giá đóng cửa **chưa điều chỉnh** (`v4/stock_prices`,
  cột `close`) — đã kiểm chứng ra đúng số CP thực (VNM 2,09 tỷ)
- Rổ = mã HOSE theo cột `floor` **từng ngày lịch sử** → mã chuyển sàn/hủy niêm yết
  tự đúng, không survivorship bias
- NPATMI = `ln_ttm` VNINDEX (P/E VNDirect tính trên LN cổ đông công ty mẹ)

**Kỹ thuật panel + ffill**: VNDirect KHÔNG công bố vốn hóa đủ mọi mã mỗi ngày
(ngày thiếu nhóm này ngày thiếu nhóm kia, lệch cả nghìn tỷ nếu cộng thô) → tool
xây panel (ngày × mã), ffill số CP tối đa 15 phiên rồi mới Σ. QC bằng cột
`qc_mcap` = Σ vốn hóa HOSE tự tính / vốn hóa VNINDEX — dao động 0,98–1,00 là chuẩn.

Output: `market-eps.csv` (eps_abs, bvps_abs, tong_cp_luu_hanh, so_ma, qc_mcap)
+ cache `shares-master.csv` (panel gốc theo mã, incremental lùi 30 ngày mỗi lần).

## P/E, P/B điều chỉnh loại trừ mã — `adjust.py`

```
python adjust.py VIC VHM VRE                  # loại nhóm Vin khỏi VNINDEX
python adjust.py VCB BID CTG --index VNINDEX  # loại nhóm bank
python adjust.py VIC VHM --full               # kéo lại full lịch sử các mã
```

Công thức: `pe_adj = (Σvốn hóa − vốn hóa nhóm) / (ΣLN TTM − LN TTM nhóm)`,
tương tự cho P/B, và **`roe_adj = (ΣLN TTM − LN nhóm) / (ΣVCSH − VCSH nhóm)` = pb_adj/pe_adj**
→ ROE TTM của rổ đã loại nhóm mã. Số từng mã kéo từ **cùng API VNDirect** (group STOCK):
LN mã = mcap/PE, VCSH mã = mcap/PB — nhất quán phương pháp với số toàn thị trường.

Output: `valuation-adjusted.csv` (date, pe, pe_adj, pb, pb_adj, **roe, roe_adj,
diem, diem_adj**, ty_trong_mcap, các cấu phần tử/mẫu, n_thieu_ln) + cache
`tickers-master.csv` (incremental, chạy lại chỉ kéo ngày mới). Cột `roe` = ROE gốc
của chỉ số (pb/pe), `roe_adj` = ROE đã loại nhóm; đơn vị thập phân (0.15 = 15%).

**Chỉ số điểm điều chỉnh loại nhóm** (`diem`, `diem_adj`): `diem` = điểm chỉ số gốc
(VN-Index...), `diem_adj` = "VN-Index nếu bỏ nhóm mã" theo **RETURN-DECOMPOSITION**:
`R_exVin,t = (R_index,t − w_Vin,t₋₁ × r_Vin,t) / (1 − w_Vin,t₋₁)`, nối chuỗi từ return
rồi neo bằng chính chỉ số tại ngày gốc. Trong đó `R_index` = return VN-Index, `w_Vin` =
tỷ trọng vốn hóa nhóm, `r_Vin` = return giá nhóm (cap-weighted, giá VIC/VHM/VRE/VPL kéo
tươi từ VCI qua `fetch_prices`, trọng số theo mcap từng mã của VNDirect).

✅ Ưu điểm so với cách vốn-hóa cũ: xây từ **return của chính VN-Index** (đã điều chỉnh
divisor) nên **KHÔNG bị nhiễu bởi mã mới niêm yết ngoài nhóm**. ⚠️ Hạn chế còn lại:
(1) `w_Vin` dùng vốn hóa ĐẦY ĐỦ của VNDirect, không phải free-float → trọng số nhóm hơi
cao hơn thực tế trong VN-Index; (2) giá VCI điều chỉnh cả cổ tức nên `r_Vin` hơi cao hơn
"price return" thuần (chênh nhỏ ~ lợi tức cổ tức). Kết quả 29/07/2026: VN-Index 1704.7 →
ex-Vin 1394.2 (Vin đang outperform mạnh nên bỏ ra thì index thấp hơn).

**Mã mới niêm yết trong nhóm loại trừ** (vd VPL lên sàn 05/2025): mỗi mã chỉ được
tính từ ngày có P/B đầu tiên (proxy ngày niêm yết); trước đó mã chưa nằm trong rổ
nên trừ 0 — KHÔNG làm trống các ngày lịch sử. VNDirect có snapshot MARKETCAP cuối
quý trước cả ngày niêm yết (data rác) — tool tự cắt bỏ.

**Ngày không tính được pe_adj** (cột `n_thieu_ln`):
- Trước 07/2019: vốn hóa cấp chỉ số chưa có (giới hạn nguồn) → không có ΣLN.
- **Mã thua lỗ TTM**: VNDirect ngừng công bố PE của mã đó (vd VIC cả năm 2022)
  → tool tự fallback sang LNST TTM của FS Extractor, đọc từ cả 2 file:
  `output_cap\market_cap_daily.csv` và `output_cap_adjust\market_cap_daily.csv`.
  Muốn lấp mã mới: `cd D:\bctc\fs-extractor` rồi
  `python fsx.py cap <mã...> --out output_cap_adjust` (KHÔNG ghi vào output_cap
  — fsx ghi đè cả file, sẽ mất data cũ), xong chạy lại adjust.py.
  Nhóm VIC/VHM/VRE đã kéo sẵn (2015→nay), giai đoạn VIC lỗ 2022 đã lấp.
- P/B hầu như không bị: VNDirect vẫn công bố P/B khi mã lỗ (miễn VCSH dương).

Nên chạy **sau 10h30** (sau khi Task "Index Fetcher" chạy xong lúc 10h) để cột
`close/eps_index/bvps_index` có đủ ngày mới nhất. Chạy trước cũng không sao —
ngày thiếu close sẽ tự được lấp ở lần chạy sau (wide dựng lại toàn bộ từ master).

## Lưu ý

- Vài dòng có `close` NaN vào **31/12, 30/9...**: VNDirect chốt snapshot cuối quý
  vào ngày nghỉ, không có phiên giao dịch — không phải lỗi.
- API không chính thức (VNDirect có thể đổi) — nếu lỗi 404/403 hàng loạt, kiểm tra
  lại endpoint bằng DevTools trên trang dstock.vndirect.com.vn.
- P/E, P/B do VNDirect tính theo phương pháp của họ (gộp vốn hóa/LN toàn rổ);
  có thể lệch nhẹ so với số Vietstock/FiinTrade nhưng nhất quán theo thời gian.
- Cần: `pip install pandas` (không cần vnstock).

## Cấu trúc

```
fetch_valuation.py       Script chính (incremental merge + dựng wide + derived)
adjust.py                P/E, P/B điều chỉnh loại trừ nhóm mã (dùng chung API + cache riêng)
Chay-hang-ngay.bat       Chạy nhanh / gắn Task Scheduler
valuation-master.csv     Data gốc long-format (cấp chỉ số)
valuation-wide.csv       Data phân tích wide + cấu phần định giá
tickers-master.csv       Cache data từng mã loại trừ (mcap, PE, PB)
valuation-adjusted.csv   Kết quả P/E, P/B điều chỉnh
```

## Định giá THỊ TRƯỜNG KHU VỰC — `region.py` (thêm 09/2026)

Cùng "form" với VN nhưng cho các sàn châu Á: `valuation-region-master.csv` (long: `code,date,ratio,value,currency,freq,source`)
+ `valuation-region-wide.csv` (wide + suy ra `ln_ttm, gtss, earnings_yield, roe_ttm`, join `close` từ indices-master → `eps_index, bvps_index`).
Ratio dùng tên VNDirect: `PRICE_TO_EARNINGS, PRICE_TO_BOOK, DIVIDEND_YIELD (%), MARKETCAP (tiền bản địa tuyệt đối)`; thêm `MARKETCAP_FLOAT`, `EPS`, `PE_COVERAGE`.
`freq` = D (ngày) / M (tháng, date = ngày giao dịch cuối tháng).

| code | Nguồn | Có gì | Lịch sử |
|---|---|---|---|
| SET, MAI, SET50, SET100 | `set.or.th /api/set/index/{x}/performance` (cookie Incapsula, curl_cffi) | pe, pbv, dividendYield, marketCap, eps | **chỉ snapshot ngày** → bồi dần |
| SSE_A | `query.sse.com.cn commonQuery MRGK` PRODUCT_CODE=01 (A shares sàn chính SH) | AVG_PE_RATE, tổng/lưu hành vốn hoá | có lịch sử, 1 request/ngày, từ 2020 |
| SSEC, SZSEC, CSI300 | `qt.gtimg.cn/q=` trường 39 (P/E chỉ số), 44/45 (vốn hoá lưu hành/tổng, tỷ CNY) | pe, marketcap | snapshot ngày (phải chạy sau 15h TQ) |
| JCI, LQ45 | `idx.co.id GetIndexSummary` MarketCapital | marketcap | lịch sử từ 2020, 1 request/ngày |
| FBMKLCI | PDF `securities_equities_keyindicators_YYYYMMDD.pdf` (bảng ~1 tháng gần nhất) | marketcap toàn Bursa (RM tỷ ×1e9) | PDF cũ 403/404 → bồi dần |
| TAIEX | **gộp từ từng mã**: `BWIBBU_d` (P/E, yield, P/B, giá) × `MI_QFIIS` (發行股數) | pe, pb, div_yield, marketcap toàn TWSE, pe_coverage | 2 request + 6s/ngày → mặc định từ 2024 (`SOURCE_FLOOR`), `--full` để xa hơn |
| TSE_PRIME/STD/GROWTH, TSE_ALL | JPX `perpbrYYYYMM.xlsx` (PER/PBR gia quyền, dòng 総合) + `historical-jika.xlsx` (vốn hoá cuối tháng, triệu JPY) | pe, pb, ln_ttm, gtss, marketcap | **tháng**, từ 04/2022 (JPX chỉ list ~12 file perpbr) |

**Chưa có**: KOSPI/KOSDAQ (KRX data.krx.co.kr bắt đăng nhập từ 2026 → pykrx chết; Naver bỏ PER khỏi trang index), HSI (hsi.com.hk chỉ có PDF "Historical PE", AAStocks bảng JS). Nếu user có tài khoản KRX (miễn phí) thì đặt env `KRX_ID/KRX_PW` cho pykrx `get_index_fundamental`.

Bẫy: JPX ghi `＊` cho PER>1000 và `－` cho âm → `_num()` trả NaN; jika ghi ngày giao dịch cuối tháng (2026-05-29) nên PER/PBR tháng đó cũng gắn ngày ấy để khớp dòng. Tencent snapshot trong phiên là số intraday → task chạy 18:30.

Chạy: `python region.py` (incremental; snapshot chỉ lấy hôm nay) · `--full` · `--only SET,SSE_A`. Tự động bởi task **"Region Daily" 18:30** (`D:\market-data\index-fetcher\Run-Region-Daily.ps1`).

### `tv_region.py` — định giá toàn sàn từ TradingView (thêm 12/09/2026)
`scanner.tradingview.com/<market>/scan` (POST, công khai, không login) trả từng cổ phiếu: `market_cap_basic, price_earnings_ttm, price_book_fq, return_on_equity, dividends_yield, net_income_ttm, exchange, subtype` cho 12 thị trường (vietnam, korea, taiwan, hongkong, thailand, indonesia, malaysia, japan, china, singapore, philippines, india; range tối đa 5000/lần, India phải phân trang). Gộp theo vốn hoá → mã `TV_<MARKET>` + `TV_<EXCHANGE>` (TV_HOSE, TV_TWSE, TV_SSE, TV_NSE...), source `tradingview`, freq D, **snapshot ngày chạy** (bồi dần).
- **P/E dùng `net_income_ttm`** (Σmcap/ΣLN, gồm mã lỗ) để cùng định nghĩa với VNDirect: HOSE 12,45 vs VNDirect 12,64. `price_earnings_ttm` của TV bị NaN khi lỗ hoặc P/E rất cao (VIC) → `PE_EX_LOSS` thấp hơn nhiều (HOSE 9,9), chỉ để tham khảo.
- **Bỏ `subtype=preferred`**: TV gán vốn hoá cổ phiếu thường cho cả cổ phiếu ưu đãi (Samsung 005935 = 005930) → đếm đôi (Hàn 8,5e15 → 6,0e15 KRW).
- `ROE_W` = bình quân ROE công ty gia quyền vốn hoá (Hàn 36% vì Hynix 92%) — **không dùng để so sánh**; ROE so sánh = P/B ÷ P/E trong wide (Hàn 15,3%).
- Kiểm chéo: TWSE 25,7 vs tự gộp `region.py` 24,7 (ex-loss); Thái 16,6 vs SET performance 16,0; Nhật TSE 16,6 vs JPX Prime 20,8 (JPX dùng số năm tài chính cố định, cũ hơn TTM).
Chạy trong `Run-Region-Daily.ps1` (bước tradingview, sau region.py).

### Cơ bản + P/E forward từ TradingView (14/09/2026: đã GỘP vào `tv_region.py`, file `tv_fundamentals.py` đã xoá)
Screener còn có **lịch sử theo quý từng mã**: `net_income_fq_h`, `total_revenue_fq_h`, `total_assets_fq_h`, `ebitda_fq_h`, `free_cash_flow_fq_h`, `earnings_per_share_diluted_fq_h` (32 quý, mới nhất trước; **không có** `total_equity_fq_h`), `net_income_fy_h`/`total_revenue_fy_h`/`fiscal_period_fy_h` (11 năm), `fiscal_period_end_fq` (epoch quý cuối → suy nhãn quý), `earnings_per_share_forecast_next_fy` (EPS consensus FY tới), `price_target_average`, `recommendation_mark`. Không có: `price_earnings_forward*`, `return_on_equity_fq_h`, `fiscal_period_fq_h`.
Gộp trên **panel cố định** (mã có ≥20 quý) → `EARNINGS_TTM_Q`, `REVENUE_TTM_Q` (freq Q, date = cuối quý lịch), `ROE_TTM_PANEL` (ΣLN ttm/ΣVCSH fq), `ROE_FY` (ΣLN fy/ΣVCSH fy), `PE_FORWARD` (Σmcap/Σ(EPS fwd × số CP)), `PE_FWD_COVERAGE`. Bẫy: HK/SG báo cáo nửa năm → panel quý nhỏ (HK 221, SG 55 mã, SG YoY vô nghĩa); VN quý mới nhất TV có trễ 1 quý (Q1/2026 khi VN đã ra Q2).

### `msci_region.py` — MSCI country index factsheet (tháng, có P/E FORWARD)
`https://www.msci.com/documents/10199/255599/msci-<country>-index.pdf` (India: `msci-india-index-net.pdf`), bảng "FUNDAMENTALS (MMM DD, YYYY): Div Yld | P/E | P/E Fwd | P/BV" — 4 số đầu là chỉ số nước, 8 số sau là chỉ số tham chiếu. Code `MSCI_<CC>`, freq M, currency USD. MSCI = large+mid cap (~85% vốn hoá) nên P/E khác toàn sàn. Vietnam P/E Fwd = na. 31/08/2026: Hàn fwd 5,1 · Indo 9,4 · PH 9,9 · TQ 10,8 · MY 14,0 · HK 14,5 · JP 16,4 · Thái 16,9 · SG 17,8 · Đài 19,1 · Ấn 19,9.
`tv_region.py` chạy hằng ngày (bước tradingview); `msci_region.py` chỉ chạy ngày 1–7 hằng tháng trong `Run-Region-Daily.ps1`. Ảnh phân tích để trong `reports\`.


## Cập nhật 14/09/2026 — gộp vào hub
Task cũ `Market Valuation Daily` 10:30 (`Chay-hang-ngay.bat` → `run_daily.py`) → nay là bước `valuation-vn` trong **Market Data AM** 10:30; `region.py / tv_region.py / msci_region.py` là các bước `valuation-region, tradingview, msci` trong **Market Data PM** 18:30 (`D:\market-data\Run-Market.ps1`). `log/_cffi_session` import từ `..\mdlib.py`.
