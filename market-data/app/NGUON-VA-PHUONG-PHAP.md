# Market Data App — Nguồn dữ liệu, phương pháp & cơ chế

*Cập nhật: 21/09/2026 · App: `D:\market-data\app\` · Chạy: `Chay-app.bat` → http://localhost:8765*

---

## 1. Kiến trúc tổng thể

```
Nguồn web/API ──► Pipeline Python (D:\market-data\*) ──► CSV/parquet trên ổ D ──► App Streamlit (datalib.py → app.py) ──► Trình duyệt / Excel / ảnh
                  Task Scheduler: Run-Market.ps1                                    localhost:8765
```

**App không gọi API khi xem.** App chỉ đọc file do các pipeline ghi sẵn. Có hai ngoại lệ:

- Nút **"▶️ Cập nhật dữ liệu"**: gọi `Run-Market.ps1 -Slot AM|PM -Only ...`, cùng runner với Task Scheduler.
- **Định giá một mã không có trong `stocks-wide.csv`**: app tự kéo VNDirect `v4/ratios`, lưu vào `app\cache\stock_val\<MA>.parquet`, mỗi ngày chỉ kéo phần mới.

### Lịch chạy (`D:\market-data\Run-Market.ps1`)

| Task | Giờ | Bước |
|---|---|---|
| **Market Data AM** | 10:30 | Mỗi ngày: `valuation-vn`. Thứ Hai: thêm `macro-vn`, `nso`, `nso-monthly`, `bonds`, `vsdc-accounts`. Thứ Bảy: thêm `indices` (full) |
| **Market Data PM** | 18:30 | Mỗi ngày: `transmission`, `flows`, `foreign-stocks`, `foreign-vci`, `prop-stocks`, `icb-vci`, `indices-vn`, `tvhistory`, `valuation-region`, `tradingview`, `nganh-ck`. Ngày 1–7: `msci`. Thứ Hai: `macro-region` |

Trạng thái: `status-AM.txt` / `status-PM.txt` và thư mục `logs\` trong `D:\market-data\`.

---

## 2. Nguồn & API theo nhóm dữ liệu

### 2.1 Giá & thanh khoản

| Dữ liệu (file) | Nguồn / endpoint | Ghi chú phương pháp |
|---|---|---|
| Chỉ số VN: OHLCV + GTGD (`index-fetcher\indices-master.csv`) | **Vietcap** `trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart` (POST) | GTGD lấy từ `accumulatedValue`, quy về triệu VND. Từ 12/08/2025 VCI đổi đơn vị, tool tự nhận ra bằng tỷ lệ value/volume. Mã HNX là `HNXIndex`, UPCoM là `HNXUpcomIndex` |
| Chỉ số Mỹ, Nhật, HK | **yfinance** (`^GSPC`, `^DJI`, `^IXIC`, `^N225`, `^HSI`...) | Không có GTGD |
| GTGD khu vực | Tencent `newfqkline` (TQ/HK), TWSE `FMTQIK` (Đài), Naver (Hàn), SET API (cần cookie Incapsula, dùng `curl_cffi`), IDX (Cloudflare), PDF Bursa / JPX | Cột `value` là triệu đồng tiền bản địa. `value_usd` quy theo tỷ giá ngày từ yfinance (`fx-master.csv`) |
| Giá từng cổ phiếu VN, ~1.233 mã (`tv-history.csv`, 233 MB) | **TradingView** qua `tvDatafeed` (websocket, không cần đăng nhập) | Giá đã điều chỉnh. `value_approx = close × KL` |
| VN-Index loại nhóm Vin (`VNINDEXADJ`) | Tự tính (`market-valuation\adjust.py`) | Phân rã lợi suất: R_exVin = (R_index − w_Vin·r_Vin) / (1 − w_Vin) |

### 2.2 Định giá

| Dữ liệu | Nguồn | Ghi chú |
|---|---|---|
| P/E, P/B, P/S, cổ tức, vốn hoá: VNINDEX/HNX/UPCOM/VN30 (`valuation-wide.csv`), 55 ngành ICB (`sectors-wide.csv`), từng mã (`stocks-wide.csv`) | **VNDirect** `api-finfo.vndirect.com.vn/v4/ratios` | Chỉ tiêu suy ra: LN TTM = mcap/PE, VCSH = mcap/PB, **ROE = PB/PE**, EPS chỉ số = close/PE. Lịch sử P/E–P/B từ 12/2017, vốn hoá từ 07/2019 |
| Định giá loại nhóm Vin (`valuation-adjusted.csv`) | VNDirect cấp mã; **FS Extractor (VCI)** khi mã lỗ | VNDirect ẩn P/E của mã lỗ TTM, nên lấy LNST từ BCTC VCI để trừ khỏi tử và mẫu |
| Số CP lưu hành (`shares-master.csv`) | VNDirect: MARKETCAP ÷ giá chưa điều chỉnh | Panel ngày × mã, ffill 15 phiên |
| Định giá 12 thị trường khu vực (`valuation-region-wide.csv`) | **TradingView screener** `scanner.tradingview.com/<market>/scan`, SET, SSE, Tencent, TWSE, JPX, IDX, Bursa, **MSCI factsheet** (P/E forward) | P/E = Σmcap / ΣLN (gồm cả mã lỗ), bỏ cổ phiếu ưu đãi. Hàn/HK chưa có P/E từ nguồn chính thức, dùng TradingView thay |

### 2.3 Dòng tiền

| Dữ liệu | Nguồn | Ghi chú |
|---|---|---|
| Khối ngoại & tự doanh cấp sàn VN (`flows-master.csv`) | VNDirect `v4/foreigns`, `v4/proprietary_trading` | Tự doanh sort theo `date`, không phải `tradingDate` (sai sẽ HTTP 500). Khối ngoại từ 08/2018, tự doanh từ 05/2022 |
| Khối ngoại theo mã (`raw\vn_foreign_stocks_vci.parquet`, ~4,9 triệu dòng, từ 2000) | **Vietcap IQ** `iq.vietcap.com.vn/api/iq-insight-service/v1/company/<MA>/price-history` | Có mua/bán khớp lệnh và thoả thuận, room, % sở hữu. VNDirect chỉ dùng để bù phiên mới nhất |
| Tự doanh theo mã (`raw\vn_prop_stocks.csv`, từ 05/2022) | VNDirect `v4/proprietary_trading` type STOCK | Tổng theo mã khớp số cấp sàn |
| Khối ngoại khu vực | Naver (Hàn), TWSE `BFI82U`, SET investor-type, IDX (số CP × VWAP), Bursa (PDF tháng + JSON ngày) | Có cột `freq` D/M. SET và Bursa chỉ có số theo tháng |
| Số tài khoản NĐT (`vsdc_tk_ndt.csv`) | **VSDC** `POST /thongke-tkgd_ndt/search` (cần header `__VPToken`) | Ngày báo cáo được quy về cuối tháng |
| Phân ngành (`raw\vn_icb_vci.csv`) | **Vietcap ICB** `iq.vietcap.com.vn/.../v2/company/search-bar` (~2.091 mã, cấp 1–4) | Dùng cho toàn app. TradingView (`vn_screener_meta.csv`) chỉ để dự phòng |

### 2.4 Vĩ mô & tiền tệ

| Dữ liệu | Nguồn | Ghi chú |
|---|---|---|
| CPI theo nhóm hàng (so cùng kỳ / tháng trước / tháng 12 / bình quân), XK-NK theo mặt hàng, IIP theo ngành, tổng mức bán lẻ, FDI đăng ký, vốn NSNN, khách quốc tế; theo QUÝ: GDP (hiện hành/so sánh/tăng trưởng theo ngành), PPI, XNK dịch vụ, vốn đầu tư toàn XH, lao động, thất nghiệp (`nso-fetcher\nso_monthly_master.csv`) | **Cục Thống kê (NSO)** — Biểu số liệu Báo cáo KT-XH tháng (`nso.gov.vn`), từ 01/2023 | Tháng gần nhất là ước tính, tháng trước sơ bộ (file tháng sau ghi đè). Bước `nso-monthly` thứ Hai |
| Niên giám 333 bảng: GDP, NSNN, M2/tín dụng/lãi suất, chứng khoán, CPI/PPI, XNK, bán lẻ, IIP, FDI, DN, lao động (`nso-fetcher\nso_master.csv`) | **NSO PX-Web** `pxweb.nso.gov.vn` (form ASP.NET → JSON-stat) | Theo năm đến 2025 (Sơ bộ/Ước tính), CPI tháng 2010–2025 nối với báo cáo tháng. Bước `nso` thứ Hai |
| CPI chỉ số mức 2024=100, tỷ giá, dự trữ ngoại hối, CAR FSI + lịch sử XNK/IIP trước 2023 (`macro_vn_master.csv`) | **IMF SDMX** `api.imf.org/external/sdmx/2.1` | Mỗi lần chạy kéo lại toàn bộ vì IMF sửa số cũ. Trễ khoảng 2–3 tháng || Cùng bộ chỉ tiêu cho 12 nước châu Á (`macro_region_master.csv`) | IMF SDMX | Đài Loan gần như trống trên IMF |
| Lãi suất LNH ON→9M + doanh số, tỷ giá trung tâm, OMO, tín phiếu, LDR/SFL/tổng tài sản | **sbv.gov.vn** (HTML render sẵn) | Trang chỉ có số **của ngày hôm nay**, nên phải chạy hằng ngày để tích luỹ chuỗi. WAF chặn theo số request, mỗi trang dùng một session riêng |
| Lịch sử dài của các chuỗi trên | **FiinProX** (Excel xuất tay, `import_fiinprox.py`) | Chuỗi tháng bị gắn nhãn theo ngày công bố, đã xoá những dòng lệch. Chuỗi ngày đúng nhãn |
| Tín dụng YTD, M2, BOP, FDI, đầu tư công, tỷ giá chợ đen | **dulieukinhte.com** | Có bước kiểm `temporalCoverage` vì một số bảng gắn sai ngày |
| Lãi suất huy động 28 NH | dulieu.nguoiquansat.vn | Dấu chấm là dấu thập phân (ngược với NHNN) |
| Lãi suất cho vay bình quân | Website BIDV, Eximbank, Agribank, VIB; VCB qua dulieukinhte | |
| CAR từng ngân hàng | PDF CBTT trên Vietstock static, OCR bằng `pdf2md.py` | 24 NH đọc được |
| LDR (TT22) & CASA nhóm NH niêm yết | BCTC từ FS Extractor (VCI), `D:\bctc\fs-extractor\output` | 27 NH niêm yết |
| Trần LDR / SFL | Bậc thang khai báo trong code (`src_caps.py`) | LDR 85% từ 2020. SFL 30% → 40% từ 07/2026 (TT 25/2026) |
| Dữ liệu Mỹ | FRED `fredgraph.csv` | Gọi không kèm User-Agent trình duyệt |

Pipeline: `transmission-fetcher\fetch_all.py` → `transmission-master.csv` (long) → `transmission-wide.csv` (wide, app đọc bản này).

### 2.5 Trái phiếu doanh nghiệp

| Dữ liệu | Nguồn | Ghi chú |
|---|---|---|
| Từng lô phát hành, dư nợ, lãi suất, mua lại, CTCK bảo lãnh (`bond-pivot\data\processed\market_issuance_timeline.csv`) | **HNX CBIS** `cbonds.hnx.vn` (header `CP-TOKEN`, CA bundle tự ghép) + PDF kết quả chào bán (OCR) | Chỉ có phát hành **riêng lẻ**, khớp VBMA. Độ tin cậy CTCK bảo lãnh: cao/khá (có PDF), proxy (suy từ tổ chức lưu ký). Phân ngành được ~88% số lô |

---

## 3. Các con số app tự tính (`datalib.py`)

| Chỉ tiêu | Cách tính |
|---|---|
| **GTGD thị trường** (`turnover`) | Lấy số VCI chính thức cho 3 sàn. Phiên VCI chưa có số thì ước tính Σ(close × KL) từ TradingView, cột `Nguồn` ghi rõ. KPI chỉ lấy phiên **đã đóng cửa**. Nếu file sửa trước 15:05 cùng ngày, phiên đó gắn nhãn "Dở phiên" |
| **Độ rộng thị trường** (`breadth`) | Tính trên ma trận giá toàn bộ mã VN: số mã tăng/giảm, đường A/D, % mã trên MA20/50/100/200/300, số mã dưới MA50/200/300 theo sàn, đỉnh/đáy 52 tuần (250 phiên) |
| **Nhóm quy mô** (`sector_caps`) | Xếp hạng vốn hoá HOSE ở phiên cuối (giá × số CP TradingView): Top 30 ≈ VN30, hạng 31–100 ≈ Midcap, còn lại ≈ Smallcap |
| **Chỉ số ngành** | Gia quyền vốn hoá, rebase về 100 **tại đầu khung thời gian đang xem**. Rổ chỉ gồm mã có giá ở cả đầu lẫn cuối kỳ, nên mã lên sàn giữa kỳ không làm méo chuỗi |
| **Hiệu suất ngành** (`sector_summary`) | Lợi suất gia quyền vốn hoá 1T/3T/6T/12T/YTD, % mã tăng, tỷ trọng vốn hoá |
| **Tăng trưởng EPS toàn TT** (`eps_market`, `eps_sector`) | EPS quy về **điểm chỉ số** (đã chia divisor). YoY so với **đúng ngày năm trước** (lùi 1 năm theo lịch, không lấy 250 phiên). `despike()` bỏ điểm lệch trên 30% so với cả điểm trước lẫn điểm sau |
| **Khối ngoại khu vực** (`flows_region`) | Quy ra triệu USD theo tỷ giá. Thị trường có số tháng thì dùng số tháng, còn lại cộng dồn số ngày |
| **Dòng tiền theo ngành** (`flows_sector`, `flows_nhom_ma`, `prop_*`, `dong_tien_nhom`) | Gắn ICB Vietcap (cấp 1–4, có thể tách Vingroup), gộp theo Ngày/Tuần/Tháng. "Soi dòng tiền" ghép khối ngoại với tự doanh, gắn nhãn cùng chiều / ngược chiều / một phía |
| **Trái phiếu** (`bonds_clean`, `lai_suat_bq`) | Sửa 2 lỗi nguồn: 23 lô USD bị ghi như VND (quy đổi theo tỷ giá tháng); VietBank 2020 ghi lãi suất bằng điểm cơ bản (chia 100). Lãi suất bình quân gia quyền theo giá trị phát hành. Đối chiếu tổng VBMA (`VBMA_NAM`) |
| **Vĩ mô** (`tm`, `mv`) | Đọc `transmission-wide.csv` (gộp theo `series_id`), không đọc bản long. NHNN đổi cách viết tên chuỗi giữa chừng, pivot theo tên sẽ làm gãy chuỗi. Tên tiếng Việt trong `TM_TEN` |

---

## 4. Cơ chế vận hành của app

1. **Cache theo mtime:** mỗi hàm đọc dữ liệu dùng `@st.cache_data`, có tham số `mt` là thời điểm sửa file. Pipeline ghi file mới thì cache tự hết hạn, không cần restart. Sửa `datalib.py` thì **phải** restart app.
   > Tham số bắt đầu bằng `_` không được băm vào khoá cache, nên tham số phụ thuộc file **không** được đặt tên có gạch dưới.
2. **Cache parquet:** `tv-history.csv` (233 MB) được đổi sang `cache\tv-history.parquet`. Lần đầu mất khoảng 30 giây, sau đó khoảng 2 giây.
3. **REGISTRY 14 dataset:** mỗi dataset khai báo một dòng trong `datalib.REGISTRY`. Khai báo xong là dataset tự hiện ở trang Kho dữ liệu, Xuất Excel và bảng "độ tươi" ở trang Tổng quan.
4. **Một khung thời gian chung:** thanh bên có preset 1T/3T/6T/YTD/12T/2N/3N/5N/10N/Tất cả hoặc Tuỳ chọn, cho ra `D_FROM`/`D_TO`. Hàm `cut()` áp khung này cho mọi bảng, chart và file Excel. Chuỗi tháng/quý mặc định giữ toàn bộ lịch sử (công tắc "Chuỗi tháng/quý: toàn bộ lịch sử").
5. **Phân ngành toàn cục:** chọn cấp ICB (1–4) và "Tách Vingroup" ở thanh bên (`dl.set_pn`), mọi hàm dùng theo.
6. **Biểu đồ:** Altair/Vega, định dạng số kiểu VN, trục X cố định theo khung đang chọn. Bảng màu "Báo cáo" (cam `#ED7D31`, nền trắng) hoặc "Tối". Bản đồ nhiệt dùng ECharts treemap. Chart kỹ thuật nhúng iframe `dchart.vndirect.com.vn`, vì widget TradingView miễn phí không có mã VN.
7. **Xuất:**
   - **📋 Copy ảnh / ⬇ PNG** dưới mỗi chart: làm hoàn toàn trên trình duyệt (SVG → canvas → clipboard), không gọi server.
   - **📥 Xuất Excel** (`xuat_excel.py`): ghi lại mọi chart/bảng/KPI đang hiển thị rồi dựng file xlsx bằng openpyxl, có chart Excel thật giữ đúng màu và định dạng. Chọn xuất trang này hoặc toàn app.
8. **Trang:** Tổng quan · Việt Nam · Khu vực & thế giới · Vĩ mô & tiền tệ · Trái phiếu & NĐT · Kho dữ liệu · Xuất Excel. Mở thẳng trang vĩ mô bằng `?trang=vimo` (`Chay-app-macro.bat`).

---

## 5. Giới hạn cần biết

- Nhiều nguồn là **API nội bộ không chính thức** (VNDirect, Vietcap, TradingView, SBV HTML), có thể đổi endpoint bất cứ lúc nào.
- Các chuỗi SBV và lãi suất ngân hàng **chỉ tích luỹ từ ngày tool bắt đầu chạy**. Ngày nào máy tắt là mất số ngày đó.
- Vẫn nhập tay: FDI giải ngân, kiều hối, tiền gửi KBNN, CAR hệ thống 2020–06/2024.
- Hàn Quốc và HK chưa có P/E cấp sàn từ nguồn chính thức.
- Trái phiếu chỉ có phát hành riêng lẻ, thiếu khoảng 7–13%/năm so với tổng VBMA (gồm cả ra công chúng).
- Có dữ liệu từ **FiinProX (có bản quyền)** trong các chuỗi vĩ mô. Nếu chia sẻ ra ngoài, cần xem điều khoản FiinProX cho phép đến đâu.
- App **không có mật khẩu**. Truy cập qua LAN (`http://<IP máy>:8765`) thì ai cũng xem được và bấm được nút "Cập nhật dữ liệu".

## Giá giao dịch TPDN riêng lẻ & đường cong lợi suất theo ngành (07/10/2026)

- **Giá**: sàn TPDN riêng lẻ HNX (`cbonds.hnx.vn/thong-tin-giao-dich`, bảng "Thống kê giao dịch theo mã"), từ 19/07/2023. Giá là **giá thanh toán = giá gộp** (đã gồm lãi dồn tích), đơn vị đồng/trái phiếu; app dùng giá bình quân ngày (GTGD/KL). Chỉ ~120–160 mã/ngày có khớp, giao dịch thỏa thuận nên nhiễu.
- **YTM**: lãi suất hiệu dụng năm (ACT/365) giải từ giá gộp với dòng tiền theo kỳ trả lãi trong bond master. Độ tin cậy: `cao` = lãi cố định + trả định kỳ; `kha` = thả nổi/kết hợp (HNX chỉ công bố lãi suất phát hành → coupon proxy); `thap` = trả lãi 1 lần khi đáo hạn (loại khỏi đường cong mặc định).
- **Đường cong**: mỗi mốc (as-of, −1M, −3M, −6M, −12M) lấy giao dịch trong `cửa sổ` ngày trước mốc, mỗi bond 1 giao dịch gần nhất, gom theo bucket kỳ hạn còn lại × ngành. **YTM bucket = bình quân gia quyền theo giá trị lô đang lưu hành**, sau khi cắt điểm ngoài 1,5·IQR trong bucket (từ 5 bond). Median/BQ theo GTGD chỉ để tham chiếu.
- **Benchmark**: spot rate TPCP theo ngày của HNX (`hnx.vn/trai-phieu/duong-cong-loi-suat`), spread = YTM − spot nội suy tại kỳ hạn còn lại.
- Chi tiết thuật toán: `D:\market-data\bond-pivot\README.md` mục "Giá giao dịch & đường cong lợi suất".
