# Market Data App — xem toàn bộ dữ liệu thị trường + xuất Excel

App web chạy trên máy (Streamlit), đọc thẳng các master CSV trong `D:\market-data`.
**Không kéo mạng** khi xem — chỉ bấm nút "Cập nhật dữ liệu" mới gọi pipeline.

## Chạy

Nhấn đúp `Chay-app.bat` — hoặc `Chay-app-macro.bat` để mở thẳng vào trang **Vĩ mô & tiền tệ**
(cùng một app, chỉ khác URL `?trang=vimo`). Hoặc:

```bash
python -m streamlit run D:\market-data\app\app.py --server.port 8765
```

Trình duyệt mở `http://localhost:8765`. Đóng app = đóng cửa sổ đen.

Lần chạy đầu mất ~30 giây vì phải dựng cache parquet cho `tv-history.csv` (233 MB
→ `app\cache\tv-history.parquet`). Các lần sau vào ~2 giây; cache tự dựng lại khi
file CSV mới hơn.

## Các trang

| Trang | Có gì |
|---|---|
| 🏠 **Tổng quan** | 6 chỉ báo nhanh (VN-Index, GTGD, khối ngoại, % trên MA200, % mã tăng, P/E) + 4 biểu đồ + **bảng tình trạng 15 dataset** (dữ liệu đến ngày nào, trễ mấy ngày) |
| 📈 **Việt Nam** | 9 tab: Chỉ số & GTGD · Khối ngoại & tự doanh · Độ rộng · Dưới MA50/200/300 · Vốn hoá nhóm (VN30/Mid/Small) · Ngành · Định giá (thị trường, loại Vin, ngành ICB) · **Tăng trưởng EPS** · Tra cứu từng cổ phiếu |
| 🌏 **Khu vực & thế giới** | Chỉ số rebase · thanh khoản quy USD · khối ngoại 7 thị trường · định giá 12 thị trường |
| 🏦 **Vĩ mô & tiền tệ** | Dashboard 11 tab: **Bảng điều khiển** (8 KPI + 4 chart) · Lạm phát CPI (Cục Thống kê: CPI chung + lạm phát cơ bản + 11 nhóm hàng, so cùng kỳ/tháng trước/tháng 12/bình quân YTD; chỉ số mức 2024=100 IMF) · Tỷ giá & dự trữ (trung tâm, biên độ, VCB, chợ đen, swap point, dự trữ, tháng nhập khẩu) · Lãi suất & thanh khoản (LNH 6 kỳ hạn, lãi suất điều hành, OMO/tín phiếu bơm hút, huy động 1/6/12T, chênh cho vay - huy động) · Tín dụng & tiền tệ (tín dụng YTD, M2, LDR, vốn ngắn hạn cho vay TDH) · Thương mại, SX, bán lẻ & FDI (Cục Thống kê: XK/NK theo mặt hàng, IIP theo ngành, bán lẻ theo nhóm, FDI đăng ký luỹ kế; BOP NHNN) · Mỹ & khu vực (Fed, SOFR, UST, DXY + IMF 12 nước) · Toàn bộ 180 chuỗi · Niên giám NSO (333 bảng PX-Web: chọn lĩnh vực → bảng → chuỗi) · GDP & số quý (tăng trưởng GDP theo khu vực/ngành, quy mô GDP, PPI, XNK dịch vụ, vốn đầu tư toàn XH, thất nghiệp, lực lượng lao động — báo cáo quý NSO từ Q1/2023) |
| 🧾 **Trái phiếu & NĐT** | Số tài khoản VSDC · **TPDN toàn thị trường** 5 tab: *Quy mô & đối chiếu VBMA* (riêng lẻ + công chúng + TP USD theo năm, bảng chênh lệch) · *Cơ cấu theo ngành* (9 ngành kiểu VBMA, giá trị / tỷ trọng) · *Lãi suất phát hành* (BQ gia quyền theo quý/năm × ngành, từng lô dạng bong bóng, bảng năm × ngành) · *Đáo hạn & tổ chức* · *Chi tiết* — lọc năm/ngành/loại/CTCK bảo lãnh là tuỳ chọn |
| 📺 **Biểu đồ nhúng** | Chart VN (dchart VNDirect, nền TradingView) · **bản đồ nhiệt VN** dựng từ dữ liệu của mình · chart quốc tế + so sánh mã (widget TradingView) |
| 🔎 **Kho dữ liệu** | Mở **bất kỳ** dataset nào, lọc theo mã/chuỗi, vẽ cột bất kỳ, tải Excel |
| ⬇️ **Xuất Excel** | Tick các bảng cần → 1 file nhiều sheet; hoặc tải/cập nhật Chart Pack |

Mỗi bảng đều có nút **⬇️ Tải Excel** ngay bên dưới.

## Biểu đồ

- **Bảng màu** chọn ở thanh bên: *Báo cáo (nền trắng)* — đúng bộ màu các biểu đồ báo cáo
  đang dùng (cam `#ED7D31`, cam nhạt `#F4B183`, đen `#262626`, xám `#A6A6A6`/`#BFBFBF`,
  lưới `#D9D9D9`) — hoặc *Tối* cho hợp nền app.
- **Ảnh biểu đồ**: dưới mỗi biểu đồ có 2 nút nhỏ — **📋 Copy ảnh** (một cú bấm, ảnh vào
  clipboard, Ctrl+V dán thẳng vào slide/Word) và **⬇ PNG** (tải file). Không cần tải về
  rồi chèn nữa. Độ nét 1x–4x chọn ở thanh bên (mặc định 2x). Menu ⋮ góc biểu đồ vẫn có
  *Save as PNG/SVG* của trình duyệt.
  - Ảnh dựng **ngay trong trình duyệt**: Streamlit vẽ biểu đồ bằng SVG, nút copy đọc lại
    thẻ `<svg>` đó, vẽ vào canvas rồi ghi vào clipboard — không gọi server, không rerun,
    không cần thư viện ngoài.
  - Nếu báo *“Document is not focused”* thì bấm vào trang cho cửa sổ có focus rồi bấm lại;
    trình duyệt chỉ cho ghi clipboard khi cửa sổ đang được focus.
- Trục Y luôn có **đơn vị** (tỷ VND, điểm, %, số mã, lần…) và số chia theo kiểu Việt Nam
  (`1.234,5`); trục X đổi định dạng theo độ dài khung (ngày / tháng / năm).
- Khung hiển thị **cố định đúng khoảng thời gian đang chọn** — biểu đồ không tự phóng
  to/kéo lệch khi rê chuột.
- Giá trị giao dịch vẽ dạng **cột** (kèm MA20/MA50), có thêm kiểu *cột chồng 3 sàn* và
  *đường*; ngoài ra có biểu đồ GTGD bình quân mỗi phiên theo tháng.
- Bản đồ nhiệt VN là treemap ECharts: ô lớn = vốn hoá lớn, xanh/đỏ = tăng/giảm, chọn
  biến động 1 phiên / 1 tuần / 1 tháng / 3 tháng / 12 tháng.

## Thanh bên

- **Khoảng thời gian**: 1T / 3T / 6T / YTD / 12T / 2N / 3N / 5N / 10N / Tất cả, hoặc
  **Tuỳ chọn…** để nhập *từ ngày → đến ngày*. Áp cho **mọi** biểu đồ, bảng và file
  Excel xuất ra. Dòng chữ ngay dưới luôn ghi rõ khung đang dùng.
  - Chọn ngày kết thúc trong quá khứ thì cả app lùi về mốc đó: KPI, chỉ số ngành,
    bảng tổng kết ngành đều tính **đến ngày đó**, không phải đến hôm nay.
  - Chỉ số ngành và vốn hoá nhóm **rebase 100 tại ngày đầu khung** và dùng rổ cổ phiếu
    có giá trong chính khung đó.
- **⚙️ Dữ liệu → 🔄 Xoá cache**: nạp lại file sau khi pipeline chạy xong.
- **⚙️ Dữ liệu → ▶️ Cập nhật dữ liệu**: gọi `Run-Market.ps1 -Slot AM|PM [-Only ...]`,
  đúng runner mà Task Scheduler dùng. Có kết nối mạng, chạy vài phút.

## Xuất Excel data + chart (thanh bên → 📥 Xuất Excel)

- **Trang này**: mọi tab của trang đang xem. **Toàn app**: 5 trang dữ liệu (Tổng quan, Việt Nam,
  Khu vực, Vĩ mô, Trái phiếu), app tự chạy lần lượt từng trang (~40 giây) rồi quay lại trang đang xem.
- Nội dung = đúng những gì đang hiển thị: khoảng thời gian, phân ngành ICB, rổ/ngành/mã/chỉ tiêu đang chọn.
- File: sheet **Mục lục** (thiết lập đang dùng + link tới từng khối) + mỗi tab 1 sheet. Mỗi khối =
  tiêu đề, bảng data, bên phải là **biểu đồ Excel thật** (đường / cột / cột chồng / cột ngang /
  cột + đường / đường + ngưỡng nét đứt) vẽ từ chính vùng data → sửa, đổi màu, copy sang PPT được.
- **Định dạng giữ như app**: bảng màu đang chọn (Báo cáo / Tối), màu từng series đúng thứ tự Vega gán
  (domain sắp tăng dần), cột dương xanh / âm đỏ từng cột, cột xám / cam như app, nét 1,9px, ngưỡng nét đứt,
  lưới ngang nhạt, không lưới dọc, nền + không viền, chữ trục 11px màu ink2, số 2/1/0 chữ số lẻ theo độ lớn,
  trục ngày dd/mm · mm/yyyy · yyyy theo độ dài khung và cố định đúng khung đang xem, tiêu đề đậm căn trái.
  Bảng: header xám nhạt, màu chữ / đậm / nền lấy từ Styler của app, precision của Styler. KPI như st.metric.
- KPI đầu trang → bảng "Chỉ số nhanh"; bảng dữ liệu → bảng; bản đồ nhiệt → chỉ data;
  widget TradingView / chart nhúng (iframe) không xuất được. Bảng > 6.000 dòng chỉ giữ 6.000 dòng cuối.
- Code: `xuat_excel.py` (ghi lại + dựng file bằng openpyxl). Hàm vẽ trong app.py gọi `xuat.ghi(...)`,
  `st.dataframe`/`subheader`/`markdown` được bọc để ghi bảng + tiêu đề, tab dùng `xuat.tabs(...)`.
  Vẽ biểu đồ mới: dùng các hàm `line/bars/bars_stack/hbars/bars_lines/line_nguong` là tự có trong file
  xuất; chart Altair tự dựng gọi `show(ch)` thì được tách data theo encoding x/y/color.

## Ghi chú số liệu

- **GTGD** lấy từ `indices-master.value` (VCI `accumulatedValue`, triệu VND → tỷ).
  Phiên nào VCI chưa có thì bù bằng `close × KL` từng mã (TradingView) — cột `Nguồn`
  ghi rõ dòng nào là ước tính.
- Phiên **đang giao dịch** được tách riêng (cột `Phiên`): KPI ở trang Tổng quan luôn
  dùng phiên đã đóng cửa, số intraday chỉ hiện ở dòng thông báo.
- **Chỉ số ngành / vốn hoá nhóm** tính lại theo đúng kỳ đang xem (rổ cổ phiếu có giá
  ở cả đầu và cuối kỳ). Nếu cố định rổ từ một mốc xa thì các mã lên sàn sau (VHM, VPL…)
  bị loại khỏi cả chuỗi và hiệu suất ngành sai.
- **Nhóm quy mô** (top 30 / 31-100 / còn lại) là xấp xỉ theo thứ hạng vốn hoá HOSE
  cuối kỳ, không phải rổ chính thức VN30/VNMidcap/VNSmallcap (4 chỉ số đó vẽ riêng).
- Giá là **giá điều chỉnh** TradingView, nên MA và hiệu suất không gãy vì chia tách.
- **Tăng trưởng EPS** dùng `eps_index` (EPS quy về **điểm chỉ số**, đã chia divisor) nên so
  sánh được theo thời gian; `ln_ttm` là tổng lợi nhuận sau thuế 12 tháng của rổ, nhạy với
  thay đổi cấu phần rổ. Tăng trưởng tính **đúng ngày cùng kỳ năm trước**, không phải
  `shift(250)`. Nguồn valuation-wide có vài **điểm gai 1 ngày** (VN30 ln_ttm 03/11/2025 vọt
  gấp đôi rồi về ngay) → `datalib.despike()` bỏ điểm lệch >30% so với cả điểm trước lẫn sau;
  bước nhảy thật (đổi rổ) vẫn giữ vì nó kéo dài.
- **Trái phiếu — phạm vi dữ liệu**: HNX CBIS chỉ có **phát hành riêng lẻ trong nước**, khớp
  VBMA gần tuyệt đối (2023: 309.138 vs 309.229 tỷ · 2024: 435.704 vs 435.704 · 2025: 574.557 vs
  574.556). Con số VBMA hay được trích (2024: 468.618 tỷ, 2025: 629.910 tỷ) **cộng thêm ra công
  chúng** — app không có từng lô, lấy tổng năm từ báo cáo thường niên VBMA (`datalib.VBMA_NAM`).
- **Trái phiếu — 2 lỗi dữ liệu nguồn đã sửa trong `datalib.bonds_clean()`**: (1) 23 lô **USD**
  bị nhân mệnh giá USD như VND nên gần bằng 0 → quy đổi theo tỷ giá bình quân tháng phát
  hành (2025: 875 triệu USD ≈ 23.000 tỷ, khớp VBMA quốc tế); (2) 5 lô **VietBank 2020** nhập
  lãi suất dạng điểm cơ bản (520–800) → chia 100.
- **Ngành trái phiếu** gán theo tên tổ chức + hệ sinh thái (`datalib.phan_nganh_tp`), chia 9
  nhóm như VBMA. Đối chiếu riêng lẻ 2024: ngân hàng 64,4% (VBMA 64,4%), BĐS 22,0% (21,9%);
  2025: 64,1% (64,1%), 24,0% (25,6%). Lãi suất BQ riêng lẻ 2024 7,24% (VBMA 7,2%), 2025 7,40%
  (7,4%).
- **Trái phiếu**: nguồn là `bond-pivot\data\processed\market_issuance_timeline.csv`
  (toàn thị trường, HNX CBIS), không phải file riêng của từng CTCK. Cột `ctck_bao_lanh`
  đi kèm `do_tin_cay`: *cao/khá* lấy từ PDF công bố, *proxy* chỉ suy từ tổ chức lưu ký —
  nên bảng xếp hạng CTCK mặc định chỉ lấy *cao/khá*.
- **Vĩ mô** đọc từ `transmission-fetcher	ransmission-wide.csv` (180 chuỗi, đã gộp theo
  `series_id`) + `nso-fetcher\nso_monthly_master.csv` (CPI, XNK, IIP, bán lẻ, FDI của Cục Thống kê, 2023+) + `nso-fetcher\nso_master.csv` (niên giám PX-Web, tab Niên giám NSO) + `macro-fetcher\macro_vn_master.csv` (IMF: chỉ còn chỉ số CPI mức, dự trữ, lịch sử trước 2023). Phải dùng bản *wide* vì SBV đổi cách
  viết tên chuỗi giữa chừng (`LNH binh quan qua dem` → `LNH binh quan Qua đêm`) làm 1 chỉ tiêu
  bị tách thành 2 dòng trong file long; `series_id` thì không đổi. Tên hiển thị tiếng Việt lấy
  từ `datalib.TM_TEN`.
- **Widget TradingView miễn phí không nhúng được mã Việt Nam và phần lớn chỉ số**
  (SPX, DJI, N225…). Vì vậy chart VN dùng `dchart.vndirect.com.vn` — cùng nền TradingView,
  dữ liệu VN, cho nhúng. Nếu khung nhúng trống thì trình duyệt đang chặn iframe: bấm link
  *“Mở trong tab mới”* ngay dưới biểu đồ.

## Cấu trúc

```
app\
  app.py        giao diện (8 trang) + helper biểu đồ (line/bars/bars_lines/hbars/treemap)
  datalib.py    REGISTRY 15 dataset + cache + tính độ rộng / MA / ngành / GTGD / bản đồ nhiệt
  Chay-app.bat        launcher (mở trang Tổng quan)
  Chay-app-macro.bat  launcher mở thẳng trang Vĩ mô
  cache\              parquet cache, xoá được, tự dựng lại
```

Thêm pipeline mới: thêm 1 dòng vào `REGISTRY` trong `datalib.py` là trang
"Kho dữ liệu", "Xuất Excel" và bảng tình trạng tự có.

## Giao diện Bloomberg Terminal & hiển thị theo tháng (07/10/2026)
- Bảng màu mặc định **Bloomberg Terminal**: nền đen, chữ amber `#ffa028`/trắng, font IBM Plex Mono, ô KPI viền mỏng, tab dạng phím lệnh, thanh trạng thái trên cùng (trang · khung thời gian · tần suất · ICB · độ tươi dữ liệu · giờ). Theme Streamlit nền (`.streamlit/config.toml`) đặt base=dark + amber. CSS trong `CSS_BLOOMBERG`, bảng màu chart `MAU_BLOOMBERG`; vẫn chọn được 'Báo cáo (nền trắng)' / 'Tối' ở thanh bên.
- Toggle thanh bên **Hiển thị theo tháng** (mặc định bật): mọi chuỗi theo ngày đi qua `cut()` được gộp 1 điểm/tháng (`thang()`): giá, lãi suất, tỷ giá, số dư/đang lưu hành = giá trị cuối tháng; mua/bán ròng, GTGD, bơm/hút trong ngày, khối lượng, lượt = cộng dồn tháng. Mốc = ngày đầu tháng để khớp số NSO/IMF. Tắt để vẽ theo ngày.

## Khung phân tích & đồng bộ tab/bộ lọc (07/10/2026)
- `dl.KHUNG_VI_MO` là khung phân loại dùng chung toàn hệ thống: trang Vĩ mô có 9 tab theo khung (Bảng điều khiển · Tăng trưởng & đầu tư · Giá cả · Đối ngoại · Tiền tệ & thanh khoản · Hệ thống ngân hàng · Lao động · Thế giới · Dữ liệu gốc); mỗi khối nội dung gắn tab bằng `with T["..."]:` nên một tab nhận nhiều khối. Nhóm dataset trong REGISTRY đặt theo `Khối · Nhóm` (Vĩ mô / Cổ phiếu / Khu vực / Trái phiếu), Kho dữ liệu xếp theo đó; số liệu NSO lọc theo `dl.NHOM_NSO_TX`.
- `tabs_bb(names, key)`: tab là segmented control, tab đang mở được nhớ trong session (`_tab_<key>`) nên đổi trang/rerun vẫn giữ; tab không chọn chỉ ẩn bằng CSS (`st.container(key=)` + `.st-key-…{display:none}`) nên Xuất Excel toàn app vẫn đủ. Khi đang xuất dùng `st.tabs` gốc.
- `filt(kieu, label, options, default, key, col)`: multiselect/selectbox/radio có nhớ (`_f_<key>`), dùng cho mọi bộ lọc chính (CPI nhóm hàng, mặt hàng XK/NK, ngành IIP/GDP, niên giám, dataset Kho…) → chọn ở tab này, sang trang khác quay lại vẫn giữ.
