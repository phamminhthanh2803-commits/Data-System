# Giao diện mẫu "Genea" – khảo sát 09/10/2026 (để dựng lại giao diện Market Data App)

Nguồn: https://genea.xn--ng-k9s.vn/ (app nội bộ, React + CSS thuần, biểu đồ SVG tự vẽ; nến dùng TradingView lightweight-charts).
Mục tiêu: dựng lại BỐ CỤC, MÀU, ĐIỀU HƯỚNG và GIẢI PHẪU THẺ BIỂU ĐỒ trên Streamlit cho D:\market-data\app (code riêng, không chép mã/logo/ảnh của họ).

## 1. Design tokens (lấy từ :root của trang)
| Token | Giá trị | Dùng cho |
|---|---|---|
| --bg | #faf8f6 | nền trang (be ấm, KHÔNG phải trắng) |
| --surface | #fff | nền thẻ (card), nút chip tắt |
| --surface-2 | #f5f2ef | nền nhóm nút (segment/period) |
| --ink | #262626 | chữ chính |
| --ink-2 | #595959 | chữ phụ |
| --ink-3 | #8c8c8c | chữ mờ (đơn vị, "Cập nhật lần cuối") |
| --rule | #d9d9d9 | viền nút chip |
| --rule-soft | #ece8e4 | viền thẻ |
| --brand-orange / --accent | #ed7d31 | nút đang chọn (nền), chuỗi chính trên chart |
| --brand-orange-light | #f4b183 | chuỗi phụ |
| --accent-text | #b3551c | chữ nút active kiểu "trắng-chữ cam" (period, navtab, subtab) |
| --accent-strong | #c75f1e | hover |
| --accent-wash | #fdf3ec | nền nhấn nhẹ |
| --up-market / --down-market | #12965a / #e23b3b | tăng/giảm thị trường (giá, nến) |
| --up-market-soft / --down-market-soft | #b7e4cd / #f4c4c4 | cột khối lượng |
| --up / --down (chart thường) | #ed7d31 / #a6a6a6 | mua ròng cam, bán ròng xám |
| --brand-gray / light | #a6a6a6 / #bfbfbf | chuỗi xám |
| --shadow-sm / md / lg | 0 1px 2px #2626260f / 0 1px 2px #2626261a / 0 6px 20px #26262629 | |
| --danger / --warn | #b42318 / #9c4a15 | |

Bảng màu chuỗi trên chart (quan sát): cam #ed7d31, nâu đậm #7a4a2a / #8b5a3c (MA, luỹ kế), nâu nhạt #c9956a, cam nhạt #f4b183, xám #a6a6a6, xám nhạt #d9d9d9. Đường tham chiếu/giá hiện tại: nét đứt đỏ với nhãn giá nền đỏ.

Chữ: `Inter, system-ui, Avenir, Arial, sans-serif`; body 16px; H1 (logo) 22px/700; H2 mục 18px/700 CHỮ HOA; H3 tiêu đề thẻ 16px/700 + phần đơn vị 13px màu --ink-3 ngay sau tiêu đề; nút 13px/600.

## 2. Khung trang
- Nền --bg, `main` padding 22px, nội dung rộng ~1410px (full-width, không sidebar).
- Dòng 1 (header): trái = logo hình thoi cam ◆ + tên app (22px/700); phải = chip mờ "Nguồn dữ liệu: 15 đơn vị · 23 nhóm ▾" (dropdown liệt kê nguồn).
- Dòng 2 (điều hướng cấp 1 – `section-tab`): 4 nút dạng VIÊN THUỐC (radius 999px, padding 9px 16px, 13px/600, viền 0.8px #d9d9d9, nền trắng; active: nền #ed7d31 chữ trắng): **Tổng quan · Thị trường chứng khoán · Vĩ mô · Tin tức**.
- Khối nội dung: 1 thẻ lớn nền trắng, radius 12px, viền 0.8px #ece8e4, padding 16–22px, chứa:
  - Điều hướng cấp 2 (`subtab`): tab chữ gạch chân (14px/600, padding 10px 4px; active chữ #b3551c + gạch dưới cam 2px; tắt chữ #262626). Vd: Chứng khoán Việt Nam · Chứng khoán thế giới · Trái phiếu.
  - Điều hướng cấp 3 (`navtab`): nhóm nút SEGMENT trong khay nền #f5f2ef radius 9px; nút 13px/600 padding 7px 14px radius 7px; active nền trắng + chữ #b3551c + shadow-md. Vd: Hiệu suất · Dòng tiền · Định giá · Nhà đầu tư.
  - Các MỤC: H2 chữ hoa (CHỈ SỐ / NGÀNH / CỔ PHIẾU / QUỸ ETF), dưới là các thẻ biểu đồ xếp dọc (1 cột, full width), cách nhau 18px.

## 3. Giải phẫu 1 thẻ biểu đồ (card)
Khung: nền trắng, radius 12px, viền 0.8px #ece8e4, padding 16px, không shadow.
1. Hàng tiêu đề: trái = H3 16px/700 "Tên thẻ" + đơn vị 13px --ink-3 ("(tỷ đồng)", "· 09/10/2026", "1,730.02 điểm −8.95 (−0.51%)" với số tăng/giảm tô màu up/down-market) + dấu "?" tròn nhỏ (explainer, tooltip giải thích); phải = dãy **chip** chọn đối tượng (VN-Index · VN30 · VNMidcap · VNSmallcap · HNX-Index · UPCoM, hoặc Toàn thị trường…): nút radius 8px, viền #d9d9d9, 13px/600, padding 7px 14px, active nền cam chữ trắng.
2. Hàng điều khiển: trái = nhóm **period-btn** trong khay #f5f2ef (1M 3M 6M YTD 1Y 3Y 5Y All; vĩ mô: Quý/Năm + 3Y 5Y 10Y All; active nền trắng chữ #b3551c shadow) + 2 ô ngày `01/01/2026 → 09/10/2026` (input date, viền nhạt, radius 8px); phải = toggle kiểu chart (Nến | Đường; Phiên | Tuần | Tháng; Giá trị | Tỷ trọng; Cấp 1 | Cấp 2) + 3 nút xuất **⧉ Ảnh · ⤓ CSV · ⤓ Excel** (nút trắng viền, 13px).
3. Dòng chú thích: "Cập nhật lần cuối: dd/mm/yyyy" 12–13px --ink-3; legend chuỗi dạng chấm/gạch màu + tên; đôi khi 1 câu giải thích có thanh dọc cam bên trái (callout) và 1 dòng tóm tắt kỳ ("Cả kỳ: khối ngoại 12.8%, tự doanh 3.7%…").
4. Vùng chart: cao ~360–420px, lưới ngang mảnh #ece8e4, không viền trục, trục phải cho khối lượng/luỹ kế, nhãn trục 11–12px #8c8c8c, tooltip nền trắng viền nhạt. Góc dưới phải có "chart-grip" (kéo đổi chiều cao).
5. Một số thẻ có nút "Bảng số liệu" (mở bảng dưới chart) và "☰ Danh sách đầy đủ".

Bảng dữ liệu (vd Hiệu suất cổ phiếu trong ngành): cột Mã (đậm) + tên công ty (nhỏ, --ink-2) rồi 1D 1W 1M 3M 6M YTD 1Y 3Y 5Y; số % canh phải, dương xanh #12965a, âm đỏ #e23b3b, "—" khi thiếu; header mờ; hàng kẻ mảnh.

## 4. Kiểm kê trang (nội dung từng tab – để ánh xạ sang dữ liệu của ta)
### Tổng quan / Chứng khoán thế giới / Trái phiếu / Tin tức
Chỉ có tiêu đề ("Chuyên mục đang được xây dựng") → ta TỰ THIẾT KẾ: Tổng quan = KPI strip + 4 chart nhỏ (như app hiện tại); CK thế giới = chỉ số khu vực/thế giới + định giá khu vực (region); Trái phiếu = bond-pivot (giá, YTM, đường cong, phát hành).

### Thị trường chứng khoán › Chứng khoán Việt Nam
**Hiệu suất** — CHỈ SỐ: (1) VN-Index nến+KL, chip 6 chỉ số, Nến|Đường; (2) Hiệu suất rebase 100 (đa chỉ số, chip nhiều chọn + VINDEX); (3) Độ rộng % cổ phiếu dưới MA20/50/100/200 (sàn HOSE, chip sàn). NGÀNH: (4) Hiệu suất ngành rebase 100 (ICB cấp 1/2, dropdown chọn ngành); (5) Thay đổi vốn hoá theo ngành (%) – cột ngang xếp hạng, 1D…5Y, "Toàn thị trường" cuối; (6) Hiệu suất cổ phiếu trong ngành – bảng Mã/1D…5Y, dropdown ngành. CỔ PHIẾU: (7) ô nhập mã → nến/đường + OHLC + KL.
**Dòng tiền** — CHỈ SỐ: GTGD (tỷ) cột + MA20/MA50; GTGD theo nhà đầu tư (stack Khối ngoại/Tự doanh/Trong nước khác; Phiên|Tuần|Tháng; Giá trị|Tỷ trọng); Giá trị bình quân theo tháng (cột, tháng chưa kết thúc tô nhạt); GTGD tự doanh (mua ròng cam / bán ròng xám + luỹ kế trục phải); GTGD khối ngoại (tương tự); Treemap tự doanh; Treemap khối ngoại. NGÀNH: dòng tiền chủ động/khối ngoại/tự doanh theo ngành (ròng). CỔ PHIẾU: mã + GTGD tự doanh/khối ngoại theo mã; Giao dịch nội bộ. QUỸ ETF: dòng tiền ETF ròng (29 quỹ).
**Định giá** — CHỈ SỐ: P/E TTM, P/B TTM (chip chỉ số); P/E & P/B toàn thị trường có/không Vingroup; Ngũ phân vị P/E, P/B (% số cổ phiếu theo lịch sử chính mã). CỔ PHIẾU: P/E,P/B của 1 mã.
**Nhà đầu tư** — TÀI KHOẢN GIAO DỊCH: số TK mở mới ròng theo tháng (VSDC). DƯ NỢ MARGIN: dư nợ margin toàn TT theo quý; dư địa cho vay; CTCK theo dư nợ (bảng).

### Vĩ mô › Vĩ mô Việt Nam (9 navtab)
- Tăng trưởng & sản xuất: GDP yoy (Quý|Năm; thực/danh nghĩa); GDP theo khu vực SX (stack 100%); GDP phía chi tiêu (năm); IIP (yoy/mom); PMI; Bán lẻ theo nhóm.
- Giá cả: CPI & lạm phát yoy; Đóng góp vào lạm phát (điểm %); Lạm phát theo nhóm hàng (cột ngang tháng gần nhất); Giá dầu Brent/WTI; Vàng thế giới; Vàng SJC mua/bán.
- Lãi suất & Tiền tệ: LS điều hành; Số dư OMO; Bơm hút ròng theo phiên; LS liên ngân hàng; LS huy động theo kỳ hạn (dải cao–thấp); Lợi suất TPCP; TPCP theo kỳ hạn; Yield curve slope 10Y−1Y.
- Hệ thống tài chính: LDR theo nhóm sở hữu; Vốn ngắn hạn cho vay trung dài hạn; CAR; Quy mô TCTD; Nhóm NH niêm yết.
- Tài khoá: Thu chi bội chi NSNN; Dự toán.
- Tỷ giá: USD/VND trung tâm · VCB · tự do; Chênh lệch so với trung tâm.
- Dự trữ ngoại hối: Dự trữ (gồm vàng); Tháng nhập khẩu (mốc 3 tháng); XNK & cán cân (IMF); Cán cân thanh toán quý.
- Thương mại & CCTT: XNK theo tháng (từng tháng/luỹ kế); Phần FDI; BoP theo quý (NHNN).
- Đầu tư nước ngoài: FDI đăng ký/thực hiện; Số dự án; FDI theo ngành (6 ngành).
### Vĩ mô › Vĩ mô thế giới: Tỷ giá (DXY) · Lãi suất · Chỉ số giá · Tăng trưởng & lao động.

## 5. Ánh xạ sang dữ liệu hiện có của ta (D:\pipeline-data\market-data, REGISTRY trong datalib.py)
indices-master (chỉ số, GTGD) · tv-history (giá từng mã → độ rộng, hiệu suất ngành, bảng mã) · flows-master + raw/vn_foreign_stocks_vci.parquet + vn_prop_stocks (khối ngoại/tự doanh, treemap, theo ngành qua vn_icb_vci) · valuation-wide/adjusted/sectors-wide/stocks-wide (P/E P/B, có/không Vin, ngũ phân vị) · vsdc_tk_ndt (TK mở mới) · nso_monthly_master + nso_master (GDP, IIP, bán lẻ, CPI, XNK, FDI) · macro_vn_master (IMF: CPI, tỷ giá, dự trữ) · transmission-master (SBV: LS điều hành, OMO, liên NH, tỷ giá, LS huy động, TPCP) · bond-pivot/processed (TPDN) · valuation-region-wide + region indices (CK thế giới) · macro_region_master (vĩ mô thế giới). Chưa có: margin, PMI, giá dầu/vàng, giao dịch nội bộ, ETF → thẻ hiện "Chưa có dữ liệu" nhạt, không bỏ trống.

## 6. Quy tắc dựng trên Streamlit
- `.streamlit/config.toml`: base light, primaryColor #ed7d31, backgroundColor #faf8f6, secondaryBackgroundColor #ffffff, textColor #262626, font Inter (nhúng Google Fonts qua CSS).
- Ẩn sidebar mặc định; điều hướng 3 cấp bằng `st.pills`/`st.segmented_control` (Streamlit ≥1.40) được CSS hoá theo token trên; giữ `?trang=` query param để deep-link (trang = section/sub/nav slug).
- Mỗi thẻ = `st.container(border=True)` + CSS: radius 12px, viền #ece8e4, nền trắng, padding 16px; tiêu đề H3 + đơn vị nhạt + "?" dùng `help`; chip đối tượng = `st.pills` góc phải (dùng `st.columns([3,2])`).
- Hàng điều khiển: period = `st.segmented_control`, ngày = 2 `st.date_input` cạnh nhau, toggle = `st.segmented_control`, nút xuất = 3 `st.download_button` nhỏ (Ảnh = PNG plotly `to_image` nếu có kaleido, nếu không ẩn).
- Chart: Plotly với template riêng: nền trong suốt, lưới #ece8e4, không viền trục, chữ trục 11px #8c8c8c, bảng màu chuỗi theo mục 1, nến xanh #12965a / đỏ #e23b3b, KL soft; chiều cao 380.
- Bảng: `st.dataframe` với `column_config` số % + tô màu bằng pandas Styler (xanh/đỏ), hoặc HTML table tự render cho đúng kiểu.
- Toàn bộ chữ tiếng Việt có dấu, dấu phẩy thập phân giữ như app hiện tại.
