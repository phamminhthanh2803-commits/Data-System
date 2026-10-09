# Market Data App — xem toàn bộ dữ liệu thị trường + xuất Excel

App web chạy trên máy (Streamlit), đọc thẳng các master CSV của hub market-data (thư mục `MD_ROOT`,
mặc định `D:\market-data`; bản pipeline mới ở `D:\pipeline-data\market-data`). **Không kéo mạng** khi xem.

**09/10/2026 — giao diện mới theo mẫu "Genea"** (nền be sáng `#faf8f6`, điều hướng 3 cấp trên đầu trang, thẻ biểu đồ
trắng bo góc 12px, cam `#ed7d31`, font Inter, biểu đồ Plotly). Khảo sát + design tokens + kiểm kê thẻ:
`design\genea-ui-spec.md`; ảnh chụp từng trang: `design\screens\`. Giao diện cũ (Bloomberg/Altair) giữ nguyên ở
`app_legacy.py`, vẫn chạy được: `python -m streamlit run app_legacy.py --server.port 8769`.

## Chạy

Nhấn đúp `Chay-app.bat` (cổng 8765) hoặc:

```bat
set MD_ROOT=D:\pipeline-data\market-data
set SHIP_ROOT=D:\pipeline-data\shipping
set BCTC_ROOT=D:ctc
cd /d D:\market-datapp
python -m streamlit run app.py --server.port 8765
```

Trình duyệt mở `http://localhost:8765`. Lần đầu mất ~1 phút vì dựng cache parquet (`cache	v-history.parquet`,
`cache	v-ohlc-vn.parquet` cho nến). Cần `plotly` (đã cài 09/10/2026, không dùng `--user`); `kaleido` tuỳ chọn —
có thì mỗi thẻ thêm nút **⧉ Ảnh**.

**Deep-link** `?trang=<section>/<sub>/<nav>`: `ttck/vn/dong-tien`, `vi-mo/viet-nam/gia-ca`, `ttck/trai-phieu/gia-loi-suat`,
`tong-quan/kho`, `tong-quan/excel`… Slug cũ (`vimo`, `vn`, `trai-phieu`, `kho`, `excel`, `khu-vuc`) vẫn mở đúng trang.

## Điều hướng & nội dung

| Cấp 1 (viên thuốc) | Cấp 2 (tab gạch chân) | Cấp 3 (segment) → các mục / thẻ |
|---|---|---|
| **Tổng quan** | Tổng quan | 6 KPI + VN-Index · GTGD · Độ rộng · Khối ngoại · bảng độ tươi 21 bộ dữ liệu · nút xoá cache / chạy pipeline |
| | Kho dữ liệu | mở bất kỳ dataset trong REGISTRY, lọc, vẽ cột, tải |
| | Xuất Excel | tick bảng → 1 file nhiều sheet; Chart Pack |
| **Thị trường chứng khoán** | Chứng khoán Việt Nam | **Hiệu suất**: nến/đường 6 chỉ số + KL · rebase 100 · độ rộng dưới MA · hiệu suất ngành rebase · thay đổi vốn hoá ngành 1D…5Y · bảng hiệu suất cổ phiếu trong ngành · nến từng mã |
| | | **Dòng tiền**: GTGD + MA20/50 · GTGD theo nhà đầu tư (giá trị/tỷ trọng, phiên/tuần/tháng) · bình quân tháng · tự doanh ròng + luỹ kế · khối ngoại ròng + luỹ kế · treemap tự doanh / khối ngoại · KN & TD theo ngành · theo mã · *(chưa có: dòng tiền chủ động, giao dịch nội bộ, ETF)* |
| | | **Định giá**: P/E, P/B theo rổ · có/không Vingroup · ngũ phân vị P/E, P/B (theo ngành ICB cấp 3) · P/E ngành ICB · P/E-P/B từng mã |
| | | **Nhà đầu tư**: TK mở mới ròng VSDC · số dư TK · *(chưa có: margin ×3)* |
| | Chứng khoán thế giới | Chỉ số (rebase + bảng 1D…5Y) · Thanh khoản USD · Khối ngoại 7 thị trường · Định giá 12 thị trường |
| | Trái phiếu | Phát hành (app vs VBMA, theo quý, đáo hạn, top hệ sinh thái/CTCK, chi tiết) · Cơ cấu & lãi suất · Giá & đường cong lợi suất (bond-pivot `yield_curve.py`) |
| **Vĩ mô** | Vĩ mô Việt Nam | 9 navtab: Tăng trưởng & sản xuất · Giá cả · Lãi suất & tiền tệ · Hệ thống tài chính · Tài khoá · Tỷ giá · Dự trữ ngoại hối · Thương mại & CCTT · Đầu tư nước ngoài |
| | Vĩ mô thế giới | Tỷ giá (DXY + 12 nước) · Lãi suất (Mỹ) · Chỉ số giá · Tăng trưởng & lao động |
| **Tin tức** | — | placeholder + bảng dữ liệu vừa cập nhật |

Thẻ nào spec yêu cầu mà hệ thống chưa có nguồn (PMI, giá dầu/vàng, margin, ETF, giao dịch nội bộ, đóng góp CPI,
GDP phía chi tiêu, dự toán NSNN, lãi suất điều hành châu Á, thất nghiệp quốc tế) vẫn hiện khung **"Chưa có dữ liệu"**
nhạt kèm ghi chú nguồn dự kiến — không bỏ trống.

## Giải phẫu 1 thẻ (`ui_genea.card`)

```
Tiêu đề (H3)  đơn vị nhạt  (?)                       [chip đối tượng · pills góc phải]
[1M 3M 6M YTD 1Y 3Y 5Y All]  [từ ngày] [đến ngày]     [toggle Nến|Đường …]  [⤓ CSV] [⤓ Excel] [⧉ Ảnh*]
(legend) ──── biểu đồ Plotly cao 380 ────
Cập nhật lần cuối: dd/mm/yyyy · ghi chú kỳ
```

- Period + 2 ô ngày nhớ theo `key` của thẻ trong `st.session_state` (`per_<key>`, `d0_<key>`, `d1_<key>`); bấm period
  đặt lại 2 ô ngày, sửa ngày thì period về trống.
- Chart: template Plotly `genea` (nền trong suốt, lưới `#ece8e4`, chữ trục 11px `#8c8c8c`, bảng màu cam/nâu/xám,
  nến xanh `#12965a` / đỏ `#e23b3b`, KL soft, legend trên, số kiểu VN `1.234,5`).
- Bảng %: `html_pct_table` (Mã đậm + tên nhỏ, % canh phải xanh/đỏ, "—" khi thiếu) hoặc `st.dataframe`.

## Cấu trúc module

```
app  app.py          khung trang: header ◆ Market Data + chip "Nguồn dữ liệu: N bộ", cây NAV 3 cấp, ?trang=, gọi module trang
  ui_genea.py     tokens + CSS, nav(), card() / Card (chart, table, empty, export), template Plotly, fig_line/bars/stack/
                  hbar/candle/treemap/group_bars/band/bubble, fmt_vn, html_pct_table, kpi_strip
  data_ext.py     dữ liệu bổ sung trên datalib: OHLC VN (cache parquet), hiệu suất ngành/mã 1D…5Y, GTGD theo nhà đầu tư,
                  treemap, ngũ phân vị, TPCP spot/snapshot, CAR, NSNN niên giám, VSDC
  pages_ck.py     TTCK Việt Nam: hieu_suat · dong_tien · dinh_gia · nha_dau_tu
  pages_vimo.py   Vĩ mô VN (9 navtab) + thế giới (4)
  pages_khac.py   Tổng quan · Kho dữ liệu · Xuất Excel · CK thế giới · Trái phiếu (3 navtab) · Tin tức
  datalib.py      LỚP DỮ LIỆU (giữ nguyên): REGISTRY 21 dataset, cache, độ rộng, MA, ngành, GTGD, flows, bonds, NSO, tm()
  app_legacy.py   giao diện cũ (Bloomberg, Altair, xuat_excel.py) — không sửa
  xuat_excel.py   chỉ app_legacy dùng (xuất data + chart Excel kiểu Altair)
  design\         genea-ui-spec.md (spec), screens\*.png (ảnh chụp), screens\chup.sh (chụp lại bằng headless Chrome)
  cache\          parquet cache, xoá được, tự dựng lại
```

## Thêm 1 thẻ mới

```python
with ui.card("Tên thẻ", "đơn vị", help="giải thích ?", key="ten_the",
             chips=["A", "B"], chip_default="A",            # tuỳ chọn, pills góc phải (chip_multi=True cho đa chọn)
             toggles={"Kiểu": ["Nến", "Đường"]},            # tuỳ chọn, segment bên phải hàng điều khiển
             periods=ui.PERIODS, default="1Y") as c:        # PERIODS_MACRO cho chuỗi tháng/quý
    d = c.cut(dl.ham_nao_do())                              # cắt theo c.d0 / c.d1; c.chip, c.toggle["Kiểu"]
    c.chart(ui.fig_line(d, "đơn vị"), d, ten="ten file")    # tự thêm nút CSV/Excel + "Cập nhật lần cuối"
```
Không có dữ liệu: `ui.card_empty("Tên", "đơn vị", "ghi chú nguồn dự kiến", key=...)`. Thêm dataset mới: 1 dòng trong
`REGISTRY` (datalib.py) → Kho dữ liệu, chip nguồn, bảng độ tươi tự có.

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

