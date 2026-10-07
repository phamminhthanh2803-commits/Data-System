# D:\bctc\nganh-chung-khoan — folder NGÀNH CHỨNG KHOÁN (tạo 14/09/2026)

Lấy facts FiinProX của 87 công ty chứng khoán (ngành "Dịch vụ tài chính" trong `fiinprox-unpivot\output\fiinprox_facts_all.csv`),
ánh xạ về ~55 chỉ tiêu chuẩn, tính sẵn TTM, tỷ lệ, tăng trưởng, và xếp theo **star schema** (fact + dim) để tra bằng SQL hoặc PivotTable.
`build_nganh_ck.py` tự chạy ở cuối `fiinprox-unpivot\run_pipeline.py`; chạy tay: `python build_nganh_ck.py`.

## KIẾN TRÚC FILE NGÀNH HIỆN HÀNH (16/09/2026 tối) — 2 sheet DATA trung gian + 2 sheet CALC + sheet trình bày toàn công thức ngắn
`IB&Brokerage_Nganh.xlsx` (21–22 MB) gồm:
| Nhóm | Sheet | Nội dung / vai trò |
|---|---|---|
| Trình bày | DASHBOARD, **Key ratios**, **So sánh mã**, Key ratios (năm), So sánh mã (năm), FS Industry, Drivers, Market Share, Số TK mở mới | giữ format/biểu đồ workbook gốc; Key ratios: khối ngành = công thức → FS Industry; khối công ty dòng 91–145 = `INDEX/MATCH` vào Data_FS (cột C = báo cáo, D = row_order, H ẩn = vị trí dòng) + dòng tổng `SUM`; dòng 38–64 = tỷ lệ theo định nghĩa PV2 (`kr_formulas.py`). So sánh mã: 1 chỉ tiêu × 12 mã × kỳ, ô = `INDEX(Calc_SoSanh!cột kỳ, dòng chỉ tiêu + 110·b)` (≈70 ký tự) |
| Calc trung gian | **Calc_SoSanh**, **Calc_SoSanh_Nam** | 12 khối công ty giống hệt khối công ty của Key ratios (khối b: dòng 36+110b..145+110b, mã = F8+b của So sánh mã) → cùng một logic, không lặp công thức dài |
| Data trung gian (lookup/dropdown) | **Data_FS** (`tbl_FS`) | TOÀN BỘ item BS/IS/CF/NOTE của 87 CTCK + dòng `ALL` (tổng ngành) theo QUÝ từ Q1-2012 (58 cột), key `ticker|stmt|row_order`, 38.906 dòng (bỏ 42k dòng toàn 0). Tra bất kỳ dòng nào của bất kỳ mã nào; PivotTable dạng dài không khả thi (3,4 triệu fact > 1 triệu dòng) → dùng Power Query unpivot / Data Model nếu cần pivot |
| | **Data_DM** | `tbl_Ma` (A:E, 87 mã + tên + nhóm quy mô + VCSH; Name `dm_ma_list`) và `tbl_ChiTieu` (H:O: 76 chỉ tiêu tra cứu = dòng Key ratios, nhãn quý/năm, loại, báo cáo, row_order, định dạng, dòng ngành; Names `dm_ct_q`, `dm_ct_y`, `dm_ct_row`, `dm_ct_fmt`, `dm_ct_ind`) |
| Thị trường theo ngày | Data_DinhGia, Data_DinhGia_Ma, Data_NPAT, Data_TK | định giá ngành/mã, LNST quý, số TK VSDC — `update_nganh_daily.py` chỉ nối thêm dòng mới hàng ngày (bước `nganh-ck` Market Data PM) |

Pipeline khi có BCTC quý mới (`fiinprox-unpivot\run_pipeline.py`): build_nganh_ck → build_valuation_ck → build_excel_feed (fs_all_wide cho FS Industry)
→ **`build_data_fs.py`** (data_fs.csv + data_dm_ma.csv từ SQLite fact_fs, ~35 s) → `build_workbook_logic.py --no-loop` (chỉ tính FS Industry/Drivers/
khối ngành bằng pycel, ~2 phút; **bỏ vòng lặp 87 mã**) → `build_presentation.py` (Excel COM, ~13 phút) → OneDrive.
Đã BỎ khỏi file: Data_FS 10 mã, Data_FS_Nganh, Data_KR, Data_TyLe, Data_TyLe_Nam, Data_ChiTieu, KR_wide_Q/Y, dm_ma; script `ratio_table.py` và
`key_ratios_by_ticker*.csv` không còn dùng (giữ file để tham khảo). Các mục "Data_TyLe / KR_wide / vòng lặp G36" bên dưới là LỊCH SỬ.
Kiểm định 16/09/2026 (7 mã × 42 quý + 10 năm): dòng tra trực tiếp 91–120 khớp 100% bản cũ; tỷ lệ/dòng tổng khớp 100% (1.176/1.176 quý, 280/280 năm)
trừ các dòng phụ thuộc 103–105 (trái phiếu đầu tư) và 132–143 (thuyết minh CP/CCQ/tiền gửi): **bản cũ sai** (vòng lặp pycel không thay được
15 dòng này theo mã: 103–105 giữ số VCBS cho mọi mã, 132–143 = 0) → Fixed income/IEA, Equity/IEA, Trái phiếu/VCSH cũ sai; bản mới đúng theo Data_FS.
Bẫy đã gặp: `IF(OR(H="",INDEX(..)=""))` → Excel không short-circuit OR → #VALUE! khi H trống (dùng IF lồng); sheet tham chiếu chéo (So sánh ↔ Calc)
phải TẠO RỖNG cả hai trước rồi mới ghi công thức, nếu không `='<sheet chưa có>'!F8` thành link ngoài.

### Drivers có công thức + dropdown, ô dropdown không merge (17/09/2026)
- Sheet **Drivers** trước đây bị đóng băng toàn bộ thành giá trị nên 3 dropdown (F12:F22 công ty, G12 sàn, G55 mã) không còn tác dụng. `restore_drivers()`
  (build_presentation.py, chạy sau Table2 + Data_FS + Data_DM) trả lại công thức: thị phần 12–22 = `XLOOKUP` vào `tbl_MarketShare` (công ty|sàn|kỳ);
  tài khoản 39–51 = `SUMIFS/MAXIFS` vào `Table2` (structured reference → VSDC cập nhật hằng tháng tự chảy vào; cột đầu Q1-2018 của dòng "mở mới NN"
  và "tăng vốn" = "" vì không có kỳ trước); nguồn vốn 54–62: G55 trống = ngành (FS Industry dòng 43/53/54), G55 = mã → `Data_FS` BS 8 / 142 / 145.
  Thanh khoản 28–35 vẫn là giá trị (nguồn link SharePoint của workbook gốc). Drivers có 34 kỳ (I..AP, Q1-2018 → Q2-2026).
- Dropdown lấy danh sách DUY NHẤT: `dm_ms_company` (34 công ty trong Market Share), `dm_ms_market` (HNX/HOSE/UPCOM/Phái sinh/Trái phiếu) ở Data_DM cột Q/R;
  G55 dùng `dm_ma_list` (87 mã, vì tra Data_FS). Quy tắc user 17/09: **ô dropdown không được là merged cell** → G4 của 2 sheet So sánh bỏ merge
  (chữ tràn sang H..R), `unmerge_dropdowns()`. Vá file đang có: `python build_presentation.py --patch-drivers [--no-copy]` (~15 s).

### CIR chuẩn bank – định nghĩa mới (17/09/2026, PV2 chốt sau khi soát sanity)
- Vấn đề: CIR cũ = −(CP bán hàng + quản lý)/TOI cho dải 1–46% giữa các mã lớn vì (1) tử số chỉ có SG&A (8,5k tỷ) trong khi chi phí vận hành thật của
  ngành ~28k tỷ: "Chi phí hoạt động" IS 41 (53k) gồm lỗ tự doanh gộp 27k + dự phòng/CP đi vay 6k + **chi phí nghiệp vụ 19,8k (môi giới 16,5k)**;
  (2) mỗi công ty xếp lương môi giới khác nhau (SSI để ở nghiệp vụ, chỉ 250 tỷ quản lý; VCK 620 tỷ quản lý) → không so sánh được.
- Đối chiếu với bank: DTHĐ của CTCK là số GỘP nên phải trừ lỗ tự doanh gộp (IS 23/27/29/31) mới bằng "lãi thuần mua bán CK"; chi phí nghiệp vụ (IS 32–39)
  = lương/hoa hồng môi giới, phí sàn, hệ thống = "chi phí hoạt động" của bank; dự phòng (phần trong IS 30) để ngoài CIR; lãi vay trừ khỏi TOI.
- Định nghĩa mới: **CIR = (CP nghiệp vụ + CP bán hàng + CP quản lý) / (DTHĐ − lỗ tự doanh − CP lãi vay + cổ tức/lãi tiền gửi)**; lãi vay = IS 51, hoặc IS 30
  khi công ty không có IS 51 (9 công ty, HCM 1.894 tỷ); TOI ≤ 0 → trống. Kết quả TTM Q2/2026: ngành 31%, SSI 29%, VND 31%, HCM 49%, MBS 44%, VCBS 47%,
  TCX 17%, VPX 15%, VIX 4% (thuần tự doanh); 28 mã > 1.000 tỷ DTHĐ: trung vị 38%, p10–p90 17–55%.
- Hiện thực: `build_data_fs.py` thêm dòng dẫn xuất `DER|1` (Σ IS 32–39) và `DER|2` (IS 30 khi IS 51 = 0) cho từng mã + ALL; Key ratios dòng 79–84
  (khối peer cũ) = số liệu bổ sung (80 DER1, 81 DER2, 82 IS 31, 83 = CP hoạt động chuẩn bank, 84 = TOI chuẩn bank), dòng 175–177 = ngành;
  công thức dòng 47 (công ty) và 15 (ngành) trong `kr_formulas.py`. Lỗi dấu FiinProX ở công ty nhỏ (ART CP hoạt động dương; APS, Tân Việt CP quản lý dương) chưa sửa.

### Lãi vay ghi ở IS 30 (HCM, ACBS, MASC, FTS, DSE, KISVN…) – lãi vay hiệu lực (17/09/2026)
- Câu hỏi: IS 51 "Chi phí lãi vay" (chi phí tài chính) và IS 30 "CP dự phòng TSTC… và CP đi vay" (chi phí hoạt động) có trùng nhau không?
  Trọng tài = lưu chuyển tiền tệ: CF 9 "Chi phí lãi vay" (điều chỉnh gián tiếp, số quý rời) và CF 54 "Tiền lãi vay đã trả". Kết quả: **không trùng**
  – CF 9 = IS 51 (SSI, VPX, TCX, MBS, VND…), = IS 30 (HCM 1.894, ACBS 1.459), ≈ IS 51 + IS 30 (KISVN, TCI; DSE qua CF 54 524 ≈ 582). Nhưng IS 30 còn chứa
  dự phòng (VDS 294 mà tiền lãi trả 51; MASC 843 vs CF 606; Kafi 104, VND +420 hoàn nhập) nên cộng thô cả dòng thổi ngành lên 28,2k vs CF 25,5–26,0k.
- Quy tắc (`build_data_fs._interest_in_row30`, dòng `DER|2` từng mã + ALL): tỷ lệ lãi vay trong IS 30 = (max(|CF9|,|CF54|) − |IS51|) / |IS30| trên
  4 quý trượt, kẹp [0,1]; không có CF → ngưỡng lãi suất (IS51×4/nợ < 2% và IS30×4/nợ ∈ [2%,15%] → cả dòng 30). **Lãi vay hiệu lực = IS 51 + DER|2**,
  dùng thống nhất cho CIR (dòng 84), COF (58), NIM (59), Spread và khối ngành (26, 28 = FS Industry 27 + dòng 176).
- Tác động (TTM Q2/2026): HCM COF 0% → 7,9%, NIM 10,0% → 4,6%; ACBS NIM 8,5% → 3,4%; COF ngành 5,3% → 5,7%; phân phối lãi vay/nợ (nợ > 500 tỷ)
  p10 3,1% → 5,1%. Còn bất thường dữ liệu: HD Securities 1,9% và VDS 1,2% (CF xác nhận lãi thấp → nợ có phần không chịu lãi), National Securities IS 51
  = 251 nhưng CF 53–126 (IS 51 nghi sai). FS Industry dòng 27/35 của workbook gốc giữ nguyên (chỉ IS 51).
- **Sửa khối ngành 17/09/2026:** FS Industry dòng 35 "Net Interest income" = thu nhập IEA gộp (IS 2+6+7+8+23+27+28+29) **đã trừ IS 51** (kiểm chứng
  Q2/2026: 14.270 = 20.755 − 6.485). Trước đó Earning yield ngành (dòng 25) dùng số ròng và NIM ngành (28) trừ IS 51 hai lần → NIM ngành 2,9%, Spread 0,1%.
  Nay EY ngành = (FS35 − FS27)/IEA, NIM ngành = (FS35 + dòng 176)/IEA, COF ngành = −(FS27 + dòng 176)/nợ có lãi. Khối công ty không bị lỗi này.

### DASHBOARD 16 biểu đồ + khối dữ liệu biểu đồ (17/09/2026, `dashboard_data.py`)
- **Dữ liệu**: FS Industry dòng 144–246, toàn công thức, cùng cột kỳ của sheet (năm H..R 2015–2025, quý U..BN Q1-2015..Q2-2026). Nguồn: dòng FS Industry,
  tỷ lệ đã chốt ở Key ratios / Key ratios (năm) (tra theo nhãn kỳ, không tính lại), GTGD/ADTV ở Drivers 28–35, dòng ALL của Data_FS. Ô thiếu số = #N/A (xám, biểu đồ bỏ qua).
  Bản năm: dòng chảy = tổng 4 quý (đủ 4 quý), số dư = Q4, ADTV = bình quân 4 quý, %YoY = so với năm trước.
- **Biểu đồ**: DASHBOARD dòng 37–128, 4 phần theo spec PV2, 4 biểu đồ/hàng (cột B, J, R, Z), tên `DB_C01`..`DB_C16`, trục quý Q1-2018..Q2-2026;
  6 biểu đồ gốc A1:AA34 giữ nguyên. Chart 7 = khung trống "trao đổi sau". Chạy lại xoá `DB_*` và dựng mới (idempotent).
- Quy ước: Chart 1–2 "Khác" = tổng − 4 mảng chính (dòng "Others" gốc không phủ hết doanh thu, lệch tới 1.368 tỷ năm 2015) → cột chồng luôn bằng tổng;
  Chart 4 biên theo QUÝ (không TTM); Chart 6 cột = CP nghiệp vụ + SG&A (tử số CIR), đường "Dự phòng TSTC & phải thu khó đòi" = IS 30 − phần lãi vay (ngoài CIR);
  Chart 9 GTGD ≤ 0 coi là thiếu (Drivers Q4-2018 = 0); Chart 10 IEA = Margin + Fixed-income + Equity + Đầu tư khác (FVTPL+HTM+AFS − FI − Equity);
  Chart 14–15 nợ không chịu lãi = Tổng TS − nợ vay − VCSH.
- Kiểm định: tổng = Σ thành phần (57 kỳ), cơ cấu % = 100%, 8 tỷ lệ khớp Key ratios 34/34 quý + 10/10 năm, GTGD khớp Drivers 31/31.
- Lưu ý dữ liệu: Q2-2026 "Đầu tư khác" vọt lên vì LPS, VCBS, DSC, MASC thiếu thuyết minh (file FiinProX xuất sớm 21/07, `_can_xuat_lai.csv`);
  %YoY LNTT Q1-2021 ~950% do nền thấp. Vá file có sẵn: `python dashboard_data.py [--no-copy]` (~15 s); dựng full tự gọi sau Drivers.

### Vay qua đêm & Drivers bổ sung (17/09/2026)
- **Phải trả ngắn hạn khác (BS 116) = vay qua đêm của CTCK** (PV2): cộng vào NỢ CÓ LÃI ở mọi nơi. Khối công ty: dòng 85 (tra Data_FS) → dòng 122
  = SUM(97:102) + 85 → Nợ/VCSH (40), COF (58). Khối ngành: dòng 178 (ALL|BS|116, số dư: năm = Q4) → dòng 8 và 26. Dashboard: `bs_on` trong nợ vay
  (Chart 14–16). Ngành Q2/2026 BS 116 = 4.500 tỷ (~0,9% nợ vay; 18,8k năm 2023) → Nợ/VCSH 1,103 → 1,113x, COF 6,69% → 6,62%.
  Lưu ý: HD Securities (2.106 tỷ) và Tân Việt (510 tỷ) có BS 116 lớn nhưng lãi vay rất thấp (COF 2,5% / 1,2%) → khoản này ở 2 công ty có thể không chịu lãi.
- **Drivers dòng 64–85** (`drivers_extra.py`, cả build full lẫn cập nhật hằng ngày): A. mua/bán ròng khối ngoại HOSE theo quý + lũy kế 4 quý, dư nợ margin,
  Δ margin, tương quan 8 quý (Q2/2026: −0,77); B. LS huy động BQ (VCB công bố, chỉ có từ 2024), LNH 3 tháng/qua đêm, tái cấp vốn, CoF CTCK, chênh lệch
  (LS tiền gửi 2026 = 3,7% so với LNH 3T 7,6% và CoF 6,6% → đúng nhận định PV2); C. vốn hoá HOSE cuối quý (từ Q3-2019), Margin/Vốn hoá (5,2%), Vốn hoá/Margin.
  Số thị trường = giá trị từ flows-master / transmission-master / valuation-master; dẫn xuất = công thức. Lịch sử LS tiền gửi trước 2024 chưa có nguồn.

### GTGD từ pipeline, DASHBOARD gộp 21 biểu đồ, định dạng App (17/09/2026 chiều)
- **Drivers dòng 28–30 (GTGD quý) / 33–35 (ADTV)**: giá trị tính từ `D:\market-data\index-fetcher\indices-master.csv` (VNINDEX/HNXINDEX/UPCOM, cột `value`
  triệu đồng/phiên, vnstock): GTGD = tổng phiên trong quý / 1.000, ADTV = GTGD / số phiên (`drivers_extra.write_gtgd`, chạy cả build full lẫn cập nhật hằng
  ngày). Đối chiếu với số link SharePoint cũ: lệch 0% ở 3 sàn mọi quý 2019–Q2/2026; lấp thêm Q1–Q4/2018 (trước đây trống/0).
- **DASHBOARD** (`dashboard_charts.py`): xoá sạch và dựng lại 21 biểu đồ trong 5 phần; 5 biểu đồ gốc gộp vào khối mới thành Chart 17 cơ cấu thu nhập %,
  18 thị phần môi giới HOSE, 19 room margin đã dùng (donut, quý gần nhất), 20 chu kỳ tăng vốn, 21 P/B ngành ± 1σ/2σ (Name mảng trên `tbl_DinhGia`, tự
  giãn khi cập nhật hằng ngày). Biểu đồ gốc "Dư nợ margin" trùng Chart 8 → bỏ. Biểu đồ P/B cũ trỏ file `Downloads\Định giá` (#REF) → link ngoài của file
  đã hết; xoá 598 Name `#REF!` thừa kế (`____tk*`). DASHBOARD phải dựng SAU Data_DinhGia (build_presentation gọi sau vòng DATA_SHEETS).
- **Định dạng = bảng màu "Báo cáo" của Market Data App** (`app.py` MAU_BAOCAO): nền trắng không viền; chữ trục #595959 8pt, trục & lưới ngang #D9D9D9,
  không lưới dọc/tick; chú thích dưới; thứ tự màu #262626, #ED7D31, #A6A6A6, #F4B183, #C00000, #00B050, #4472C4…; 1 cột + đường → cột #BFBFBF, đường
  đen/cam; đường 1,5pt không marker; nhãn kỳ ở đáy (không đè vùng âm). Font App Source Sans Pro không cài → Segoe UI.
- Drivers thị phần (12–22) trả #N/A (chữ trắng) thay "" để biểu đồ không vẽ 0 ở kỳ thiếu số. Vá file có sẵn: `python drivers_extra.py` rồi `python dashboard_data.py`.
- Bẫy COM: `Chart.Axes(1,2)` vẫn trả đối tượng khi trục phụ không hiện nhưng `.Format` lỗi → kiểm `HasAxis(t,g)` trước.

### Chart 7 – Yield các loại tài sản sinh lời (17/09/2026)
- Thay khung trống "Fixed-income / Equity / Margin yield". BCTC CTCK KHÔNG tách thu nhập trái phiếu với cổ phiếu → yield theo nhóm kế toán:
  Margin (Key ratios 24), HTM (23; gần như thuần fixed-income: tiền gửi, CD, TP giữ đến đáo hạn), AFS (22), FVTPL tổng (21: lãi bán + đánh giá lại +
  cổ tức, lãi − lỗ), **FVTPL carry** = 4 × IS 5 "Cổ tức, tiền lãi phát sinh từ FVTPL" / FVTPL bình quân (t, t−1) (năm: số năm), CoF (nét đứt) làm mốc.
- Dòng khối dữ liệu: `y_margin`, `y_htm`, `y_afs`, `y_fvtpl`, `is5`, `y_fvtpl_carry` (kiểu `yield` trong dashboard_data). Kiểm định: 4 yield khớp
  Key ratios 34/34 quý + 10/10 năm; carry khớp tính tay (Q2/2026 5,1%, năm 2025 3,9%). Q2/2026: margin 11,1%, HTM 8,3%, AFS 6,4%, FVTPL tổng 9,3%, CoF 6,6%.

## File
| File | Dùng cho | Nội dung |
|---|---|---|
| `nganh_chung_khoan.sqlite` | SQL (DBeaver, Python, Power BI) | `dim_company`, `dim_period`, `dim_metric`, `fact_items`, `fact_ratios`, `fact_fs` (toàn bộ 4,7 triệu facts ngành, có index), `industry_summary`; view `v_ratios` (đã join tên công ty + tên chỉ tiêu), `v_latest_q` (quý mới nhất) |
| `nganh_chung_khoan_pivot.xlsx` | PivotTable | sheet `fact_ratios` dạng long (550k dòng): ticker, tên, nhóm quy mô, freq, period, year, quarter, nhóm chỉ tiêu, metric, tên Việt, đơn vị, value. Kéo `metric` vào Filter, `period` vào Columns, `ticker` vào Rows, `value` vào Values (Sum hoặc Average) |
| `fact_ratios.csv` | Python/pandas | như sheet trên, không có tên công ty (join `dim_company.csv`) |
| `ratios_wide_Q.csv`, `ratios_wide_Y.csv` | xem nhanh | 1 dòng = công ty × kỳ, cột = mọi chỉ tiêu |
| `fact_items.csv` | | chỉ tiêu gốc đã ánh xạ (Tỷ VND), chưa tính tỷ lệ |
| `industry_summary.csv` | | theo kỳ: tổng TTS, VCSH, margin, LNST… toàn ngành, ROE ngành, trung vị các tỷ lệ, số công ty |
| `dim_company.csv` | | ticker, tên, ngành ICB L1–L4, VCSH kỳ gần nhất, nhóm quy mô Lớn/Vừa/Nhỏ (tam phân vị VCSH), năm đầu/cuối có số |
| `dim_metric.csv` | | metric → tên Việt, nhóm (Quy mô / Kết quả / TTM / Sinh lời / Đòn bẩy / Cơ cấu / Hiệu quả / Tăng trưởng / Định giá), đơn vị, công thức |
| `dim_period.csv` | | period → freq, year, quarter, ngày cuối kỳ |
| `metric_map.csv` | chỉnh sửa | ánh xạ key ↔ (statement_code, row_order) FiinProX; sửa/thêm dòng rồi chạy lại. Thuyết minh có nhãn lặp nên khoá là row_order |

## Quy ước
- Giá trị Tỷ VND như FiinProX; **chi phí và thuế đã đổi về số dương** (FiinProX ghi âm). EPS/BVPS VND.
- Kỳ quý: TTM = tổng 4 quý liên tiếp (thiếu quý thì NaN); bình quân = (kỳ này + cùng kỳ năm trước)/2. Kỳ năm: dùng số năm, bình quân với năm trước.
- `margin_book` = thuyết minh "Cho vay ký quỹ" (NOTE 159), thiếu thì "Các khoản cho vay" (BS 8, gồm cả ứng trước).
- `interest_cost` = chi phí lãi vay (IS 51); công ty ghi lãi vay trong "CP dự phòng TSTC và CP đi vay" (IS 30, ví dụ HCM) thì lấy dòng đó.
- `brokerage_fee_rate` = DT môi giới / GTGD cổ phiếu của NĐT qua CTCK (thuyết minh 109), cùng kỳ, không TTM.
- Nhóm quy mô tính theo VCSH quý gần nhất, thay đổi mỗi lần chạy.

## SQL mẫu
```sql
-- ROE TTM và margin/VCSH quý mới nhất, công ty lớn
SELECT ticker, period, metric, value FROM v_latest_q WHERE nhom_quy_mo='Lớn' AND metric IN ('roe','margin_to_equity') ORDER BY metric, value DESC;
-- Chuỗi dư nợ margin toàn ngành theo quý
SELECT period, sum_margin_book, ind_margin_to_equity, n_cong_ty FROM industry_summary WHERE freq='Q' ORDER BY ngay_cuoi_ky;
-- Một dòng bất kỳ trong BCTC gốc (thuyết minh dòng 159 = cho vay ký quỹ)
SELECT ticker, period, value FROM fact_fs WHERE statement_code='NOTE' AND row_order=159 AND freq='Q' AND ticker='SSI' ORDER BY year, quarter;
```
Python: `import sqlite3, pandas as pd; con = sqlite3.connect(r"D:\bctc\nganh-chung-khoan\nganh_chung_khoan.sqlite"); pd.read_sql("SELECT * FROM v_ratios WHERE metric='roe' AND freq='Q'", con)`.

## Kiểm tra dữ liệu nguồn
Trước khi tin số quý mới nhất, xem `fiinprox-unpivot\output\_can_xuat_lai.csv`: công ty có mặt ở đó là file FiinProX xuất sớm, thiếu thuyết minh (margin_book rơi về BS 8) hoặc thiếu CF.

## [LỊCH SỬ] Feed cho workbook Excel `IB&Brokerage_Genea_2Q26.xlsx` (14/09/2026)
`build_excel_feed.py` sinh CSV dạng rộng thay PivotTable 4,67 triệu dòng + 95k GETPIVOTDATA, theo đặc tả trong workbook:
- `excel_feed\fs_all_wide.csv` — key `ALL|metric|row_order` (row_order = ALL cho tầng metric), cột kỳ `YYYYQn` (Q0 = quý null) và `YYYYFY` (= tổng Q0..Q4 như subtotal năm của pivot).
- `excel_feed\fs_ticker_wide.csv` — key `ticker|metric|row_order`, phạm vi `--scope list` (`excel_feed\tickers.txt`, lấy từ Key ratios!G36 + F60:F71) hoặc `--scope all`.
- `market_cap_daily.csv` (bỏ 5 cột text), `industry_valuation.csv`, `manifest.json` (chỉ nằm trong `excel_feed\` cục bộ; không chép CSV sang OneDrive nữa).
- Ô không có dòng nguồn ghi **0** (`--fill zero`), vì GETPIVOTDATA trả 0 khi item dòng/cột tồn tại mà giao điểm trống (mẫu NOTE!X8 2009Q1); `--fill blank` nếu muốn để trống.
- Kiểm định: đặt `excel_feed\validation_samples.csv` (xuất từ sheet `_Validation_Samples`, workbook phải LƯU trước) → `validation_report.csv`. Chưa có thì dùng 15 mẫu trong đặc tả.
- `render_workbook_feed.py --wb <xlsx>` — dựng `excel_feed\IB&Brokerage_values.xlsx` **cùng cấu trúc** workbook (sheet BS, IS, NOTE, Peer Data, Key ratios, Drivers, đúng toạ độ ô): ô thuần GETPIVOTDATA trên pivot DATA được thay bằng giá trị pipeline, ô khác giữ giá trị đã tính trong workbook. Đồng thời đối chiếu từng ô với giá trị pivot đang lưu → `validation_full.csv` (95 nghìn ô); xuất `_Validation_Samples` → `validation_samples.csv`. Ngữ nghĩa GETPIVOTDATA đã tái tạo: subtotal metric (mọi row_order, mọi báo cáo), subtotal metric×row_order, ô ticker; quý null → Q0; FY = subtotal năm; giao điểm trống → 0; item/cột không tồn tại → "".

### Quyết định 15/09/2026: KHÔNG bắt chước lỗi gộp nhãn của pivot
Pivot Excel gộp item không phân biệt hoa/thường và subtotal theo `metric` cộng mọi dòng cùng nhãn ở mọi báo cáo. Hệ quả: 2.022 ô sheet BS
(17 chỉ tiêu: Tiền và tương đương tiền, Vay dài hạn, GD mua bán lại TPCP, Phải trả cổ tức..., các dòng tài sản lưu ký VSD) đang cộng nhầm
tiêu đề/dòng thuyết minh cùng tên, thậm chí cộng dòng tài sản với dòng nợ (`bs_corrections.csv`: giá trị workbook vs giá trị đúng).
- `build_excel_feed.py`: nhãn phân biệt hoa/thường (`--casefold` chỉ để đối chiếu). Sheet BS phải tra theo **dòng**: key `="ALL|"&TRIM($A8)&"|"&$B8`
  (cột B của BS là row_order), không dùng tầng `ALL` cho BS. IS đã dùng row_order, NOTE dùng ROW()-7.
- `render_workbook_feed.py --mode correct` (mặc định): BS tra theo cột B; `--mode faithful` bắt chước pivot 100% chỉ để kiểm định.

## Tái tạo LOGIC tính toán của workbook (`build_workbook_logic.py`, 15/09/2026) — nay chạy `--no-loop`, vòng lặp 87 mã là LỊCH SỬ
Không viết lại tay ~9.400 công thức của Key ratios / FS Industry / Drivers: dựng workbook "lite" (`excel_feed\_wb_lite.xlsx`) trong đó
BS/IS/NOTE/Peer Data là GIÁ TRỊ từ pipeline, 3 sheet logic GIỮ CÔNG THỨC (GETPIVOTDATA → số pipeline, link ngoài `[1]Processed Data`
→ giá trị đã lưu, GETPIVOTDATA trên pivot "Số TK mở mới" → tính lại từ Table2), rồi cho **pycel** tính toàn bộ và đối chiếu từng ô
với giá trị workbook (`excel_feed\logic\validation_logic.csv`). pycel thiếu MEDIAN/SEARCH → vá trong script.
- `--faithful`: bắt chước pivot (gộp hoa/thường, BS theo nhãn) — dùng để chứng minh engine khớp 100%.
- Mặc định (correct): BS tra theo dòng, nhãn phân biệt hoa/thường → ô khác workbook chính là các ô workbook đang sai lan sang FS Industry/Key ratios.
- Vòng lặp G36 qua 87 mã (thay 55 dòng dữ liệu gốc của công ty bằng số pipeline) → `logic\key_ratios_by_ticker.csv` (long: ticker, chỉ tiêu, kỳ, giá trị);
  `--peer` mới sinh `peer_compare.csv` (mặc định bỏ: PivotTable trên `key_ratios_by_ticker.csv` chọn mã tuỳ ý).
- Xuất: `logic\fs_industry.csv`, `key_ratios_industry.csv`, `drivers.csv`, `key_ratios_by_ticker.csv`, `IB&Brokerage_logic.xlsx`.
- Drivers: thị phần (Market Share), tài khoản mở mới (Table2 sheet "Số TK mở mới") — các tháng mới hơn workbook tự nối từ `D:\market-data\vsdc-accounts\vsdc_tk_ndt_table2.csv` (kéo tự động từ VSDC), thanh khoản (giá trị đã lưu từ link SharePoint `Thanh khoản.xlsx`
  — pipeline `D:\market-data\index-fetcher` có GTGD HOSE/HNX/UPCOM, có thể thay link này khi cần).

### Kỳ NĂM (15/09/2026)
- Tầng chỉ tiêu chuẩn: `fact_ratios.csv` / SQLite / pivot xlsx có cả `freq = Y` (181k dòng, 2005–2025) tính từ file FiinProX Yearly (số năm kiểm toán,
  bình quân với năm trước). Trước đó bị mất do pivot_table bỏ dòng có quarter NaN — đã sửa.
- Tầng logic workbook: Key ratios chỉ định nghĩa theo quý (TTM = 4 quý). Bản năm = giá trị tại Q4 (dòng chảy TTM = cả năm, số dư = cuối năm):
  `logic\key_ratios_by_ticker_yearly.csv`, `logic\key_ratios_industry_yearly.csv`, hai sheet "(nam)" trong `IB&Brokerage_logic.xlsx`.
  Lưu ý: bản này là tổng 4 quý, có thể lệch nhẹ so với số năm kiểm toán trong tầng chỉ tiêu chuẩn.
- `build_presentation.py` (Excel COM, gọi cuối build_workbook_logic.py): **`logic\IB&Brokerage_Nganh.xlsx`** → chép sang **`OneDrive\excel_feed\IB&Brokerage_Nganh.xlsx` = FILE NGÀNH DUY NHẤT giao** (15/09/2026: gộp mọi đầu ra vào 1 file; sheet Data_FS/Data_FS_Nganh/Data_KR/Data_DinhGia/Data_DinhGia_Ma/Data_NPAT/Data_TK là bảng Excel tbl_* để PivotTable; Table2 "Số TK mở mới" ghi đè bằng VSDC tự động). Bản sao 4 sheet DASHBOARD, FS Industry,
  Key ratios, Drivers của workbook gốc (Sheets.Copy trong Excel → giữ 100% format, biểu đồ, cond. format). FS Industry & Drivers = giá trị pipeline
  (`cells_values.csv`); Key ratios: khối ngành giá trị tĩnh, khối công ty công thức nhẹ (cột H ẩn `=MATCH($G$36&"|"&ROW(),KR_wide_Q!$A:$A,0)`,
  ô kỳ `=INDEX(KR_wide_Q!I:I,$H38)` cùng chữ cột), G36 dropdown 87 mã (Name `dm_ma_list`); thêm "Key ratios (năm)". Sheet ẩn KR_wide_Q/KR_wide_Y/dm_ma.
  Chart DASHBOARD trỏ về sheet nội bộ. Không dùng openpyxl để ghi file này (sẽ mất chart). Chạy ~10 phút vì Excel mở file gốc 68 MB.

### Nhãn quý/năm khác nhau cùng dòng (15/09/2026 — vụ Finance income = 0)
FS Industry dòng "Finance income/expense" lấy từ IS dòng 55/63 (row_order 48/56). Sheet IS ghi nhãn của mẫu NĂM ("Doanh thu hoạt động tài chính",
"Chi phí tài chính") trong khi phần lớn file QUÝ ghi "Cộng doanh thu hoạt động tài chính" / "Cộng chi phí tài chính" → GETPIVOTDATA của workbook gốc
chỉ khớp vài công ty, ra 0. `build_excel_feed.load_source()` nay gộp nhãn theo (báo cáo, row_order) về nhãn phổ biến nhất và giữ `ALIAS`
(nhãn biến thể → chuẩn) cho mọi tra cứu; fs_all_wide/fs_ticker_wide có thêm dòng theo nhãn biến thể để MATCH bằng nhãn nào cũng khớp.
Hiện có 3 dòng: IS 48, IS 56, IS 79.
- **Công thức mảng** (15/09/2026): 1.276 ô năm của FS Industry là `{=SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=I$4)*$U24:$BM24)}` (và biến thể chỉ Q4
  cho số dư); openpyxl trả về object ArrayFormula chứ không phải chuỗi nên trước đây bị bỏ qua, file trình bày giữ số cũ của workbook
  (Finance income 2016 = 2,48 thay vì 319,8). Nay `build_workbook_logic.py` tính trực tiếp bằng Python (tổng các ô quý cùng dòng theo năm / Q4).
  Ô Drivers dùng XLOOKUP vào bảng `tbl_MarketShare` (structured reference, pycel không hỗ trợ) giữ nguyên giá trị workbook (dữ liệu thị phần tĩnh).

## Định giá ngành theo ngày + LNST toàn ngành (`build_valuation_ck.py`, 15/09/2026; tự chạy cuối pipeline)
- `valuation_nganh_ck_daily.csv` (+ bảng `valuation_daily` SQLite): từ 2015, mỗi ngày: số mã, Σ vốn hoá, Σ LNST TTM, Σ VCSH, P/E (gồm lỗ), P/E ex-loss, P/B, coverage.
- `valuation_ck_stocks_daily.csv` (+ `valuation_stocks_daily`): từng mã niêm yết × ngày (39 mã có giá TradingView) — cho PivotTable.
- `npat_nganh_ck_quarterly.csv` (+ `npat_quarterly`): LNST quý và TTM của 87 công ty (cả chưa niêm yết) và của nhóm niêm yết, YoY.
- `dinh-gia-nganh-ck.png`: 4 panel P/E, P/B, vốn hoá, LNST.
- Phương pháp: vốn hoá = giá đóng cửa TradingView (đã điều chỉnh chia tách/quyền) × số CP HIỆN HÀNH (giống VCI/fs-extractor) — nhân với vốn góp
  từng quý sẽ chiết khấu 2 lần; BCTC quý có hiệu lực sau cuối quý + 30 ngày; LNST TTM = 4 quý liên tiếp; P/E ngành = Σ mcap / Σ LNST TTM.
- Chưa có giá: ART, FSC, HBS, HFT, PHS (không có trên TradingView). LNST ngành lấy từ `industry_summary.csv` nên vẫn đủ 87 công ty.

## OCI / lãi lỗ AFS chưa thực hiện (16/09/2026) — phần Data_TyLe/ratio_table là LỊCH SỬ (đã bỏ khỏi file)
- Số dư luỹ kế nằm ở **BS dòng 152 "Chênh lệch đánh giá lại tài sản theo giá trị hợp lý"** (VCSH) → metric `afs_reval_reserve`; phát sinh trong kỳ ở
  **IS dòng 77** → `oci_afs` (tổng OCI dòng 75 → `oci`, tổng thu nhập toàn diện dòng 84 → `total_comprehensive`); dẫn xuất `npat_incl_oci` = LNST + OCI AFS (có TTM).
- Đối chiếu 2020+: Δ số dư 152 ≈ OCI 77 ở 306/369 quý. ABW, TVB, VCK ghi OCI theo luỹ kế (không cộng dồn được); thuyết minh NOTE 529 "Loại AFS" gần như trống.
- **Lỗi nguồn TCX Q1/2026**: FiinProX ghi OCI AFS = LNST (1.147,6 tỷ) → tổng thu nhập toàn diện nhân đôi. Đã ghi `fiinprox-unpivot\fixes.csv` (IS 75/77 → −12,09 tỷ; 84/86 → 1.135,5 tỷ, theo VCI API `fs-extractor` + Δ BS152). Detector `_loi_don_vi.csv` đã gắn cờ review.
- Các metric này xuất hiện trong `ratios_wide_Q/Y.csv`, SQLite, và sheet **Data_TyLe / Data_TyLe_Nam** (bảng `tbl_TyLe`, `tbl_TyLe_Nam`) của `IB&Brokerage_Nganh.xlsx`. **Trong file Excel các tỷ lệ là CÔNG THỨC** (`ratio_table.py`, 16/09/2026): chỉ tiêu gốc (59 cột theo metric_map) là giá trị; cột `ok_ttm/ok_lag4/ok_lag1` kiểm tra cùng mã + đủ kỳ liên tiếp; dẫn xuất, `*_ttm` (SUM 4 dòng liền trước cùng mã) và 28 tỷ lệ là công thức O(1)/ô tham chiếu 1–4 dòng trước; sheet **Data_ChiTieu** (`tbl_ChiTieu`) diễn giải tên cột. Đối chiếu với Python: khớp 100% trừ sai số làm tròn CSV 4 chữ số ở công ty rất nhỏ; Excel tính thêm ở kỳ Python trả NaN (ô trống = 0). Bẫy COM: ghi công thức vào ListObject đang tồn tại → Excel trải công thức dòng đầu xuống cả cột (calculated column) → phải `Unlist()` rồi ghi rồi tạo lại bảng cùng tên.
  — đủ 87 CTCK (Data_FS chỉ có 10 mã trong scope list), nên xem OCI của TCX tại đây.
- **NGUYÊN TẮC CHỈ THÊM (24/09/2026, PV2):** mỗi lần chạy chỉ được THÊM dữ liệu mới vào đúng file OneDrive đang giao — không dựng lại rồi chép file mới đè lên, không sửa/xoá dòng hay ô đã có (giữ mọi chỉnh sửa tay, vd. sheet `Calc_DinhGia_comps` user tự thêm).
- Cập nhật hàng ngày: `update_nganh_daily.py` (bước `nganh-ck`, Market Data PM sau tvhistory) chạy build_valuation_ck → sao lưu file OneDrive vào `excel_feed\_backup\daily\` (giữ 10 bản) → mở THẲNG file OneDrive: tbl_DinhGia (khoá date), tbl_DinhGia_Ma (ticker+date), tbl_NPAT (period), tbl_TK (date) nối dòng có khoá chưa có; Table2 VSDC nối tháng mới + kéo công thức dòng cuối; Drivers (GTGD 28–35, khối 64–85) điền ô trống (`drivers_extra.build(wb, append_only=True, recent=2)`). **Ghi đè `RECENT_Q` = 2 quý gần nhất** (quý mới nhất + quý liền trước theo ngày/qend của dòng; Drivers = 2 cột kỳ cuối): số khác → ghi đè đúng ô cột pipeline (điều chỉnh BCTC, giá chốt phiên, VSDC sửa số). Quý cũ hơn đóng băng. Không bao giờ xoá dòng; dòng user thêm trong bảng (khoá không có trong CSV), cột user thêm trong bảng, ô công thức/chữ user gõ trong Drivers, sheet user thêm: giữ nguyên. Không có gì mới → không lưu. File đang mở trong Excel → không đụng, exit 3, lần sau thêm bù. Sau khi lưu, chép ngược OneDrive → `logic\` làm bản làm việc.
- Dựng lại full (`build_presentation.py`; `run_pipeline.py` gọi khi có BCTC quý mới, `BCTC_NO_WORKBOOK=1` để bỏ qua): chỉ ra `logic\IB&Brokerage_Nganh.xlsx`; `copy_final` **KHÔNG ghi đè** file OneDrive đã có. Muốn thay thật: `--replace-final` (tự sao lưu `_backup\Nganh_OneDrive_truoc-replace_*.xlsx` trước).
- Sửa 16/09/2026: tăng trưởng YoY kỳ NĂM trong build_nganh_ck trước đây lùi 4 năm (dùng chung lag4 với quý) → nay lùi 1 năm; bản Excel đúng từ đầu.

## Key ratios = CÔNG THỨC theo định nghĩa PV2 chốt 16/09/2026 (`kr_formulas.py`)
- Khối ngành (dòng 6–33) tham chiếu 'FS Industry' (giá trị tổng ngành) + dòng 167–174 (IS ngành: lãi/lỗ FVTPL/AFS/HTM/cho vay, giá trị từ fs_all_wide); khối công ty (38–64) tham chiếu dòng 91–145 (INDEX từ KR_wide_Q/Y).
- ROE/ROA = TTM / bình quân (t, t−4 quý | t, t−1 năm); yield, earning yield, COF, NIM = quý×4 / bình quân (t, t−1), năm = số năm; NIM = (thu nhập IEA − CP lãi vay)/IEA BQ; Spread = EY − COF; CIR (TTM) chuẩn bank −(CP bán hàng + quản lý)/TOI cho cả 2 khối; Nợ/VCSH chỉ nợ có lãi (6 dòng vay + TP phát hành).
- Bản năm: KR_wide_Y dòng chảy (106–120, 124–131) = tổng 4 quý (đủ 4 quý), số dư = Q4. Đối chiếu Q2/2026 VCBS: 9/9 tỷ lệ khớp tính tay.
- `audit_logic.py` → `AUDIT-Logic-Sheet-TrinhBay.md`: liệt kê logic gốc của workbook (409 dòng) để đối chiếu.
- Lưu ý: FS Industry năm 2015 thiếu nhiều mã (FiinProX) → tỷ lệ bình quân ở cột 2016 (t−4 = 2015) của khối ngành bị lệch; dùng từ 2017.

## [LỊCH SỬ – bản 1, công thức CHOOSE dài] Sheet SO SÁNH NHIỀU MÃ (`compare_sheet.py`, 16/09/2026 chiều) — bản 2 dùng Calc_SoSanh, xem mục KIẾN TRÚC ở đầu
- 2 sheet trình bày mới trong `IB&Brokerage_Nganh.xlsx`: **So sánh mã** (42 quý) và **So sánh mã (năm)** (10 năm), đặt ngay sau "Key ratios (năm)".
  Chọn 1 chỉ tiêu ở **G4** (dropdown: 21 tỷ lệ khối công ty của Key ratios + 55 số liệu gốc dòng 91–145), tối đa **12 mã ở F8:F19** (dropdown `dm_ma_list`),
  cột I.. = kỳ (cùng cột với Key ratios), cột G = giá trị mới nhất; dòng 20 = TRUNG VỊ các mã đã chọn, dòng 21 = NGÀNH (tra Key ratios, trống nếu chỉ tiêu gốc);
  biểu đồ đường 14 series (12 mã + trung vị nét đứt + ngành nét đậm) dưới bảng, tiêu đề = chỉ tiêu đang chọn.
- Mọi ô là CÔNG THỨC, định nghĩa y hệt `kr_formulas.F.company` (ROE/ROA TTM/bình quân, yield ×4, CIR chuẩn bank, nợ có lãi): cột helper ẩn BH..CC
  = MATCH(mã|dòng gốc) 1 lần/mã, ô giá trị = `CHOOSE($D$4, 21 biểu thức tỷ lệ, số liệu gốc)` với INDEX O(1) vào KR_wide_Q/KR_wide_Y; TTM = `SUM(INDEX(4 cột, idx, 0))`.
  Định dạng số đổi theo loại chỉ tiêu bằng conditional formatting (E4 = pct / x / num). Danh mục chỉ tiêu ở sheet ẩn `dm_ma` cột C:F (quý), H:K (năm); Name `dm_ct_q`, `dm_ct_y`.
- Đối chiếu 16/09/2026: 26 chỉ tiêu × 3 mã (VCBS, SSI, TCX) × 2 sheet = 4.056 ô khớp 100% với khối 1 mã của Key ratios.
- Dựng full: `build_presentation.py` gọi `compare_sheet.build(wb, per_q, per_y)` sau Key ratios. Thêm vào file đang có: `python compare_sheet.py [--file <xlsx>] [--no-copy]`
  (xoá sheet cũ cùng tên rồi dựng lại; `update_nganh_daily.py` không đụng 2 sheet này). Thêm tỷ lệ mới: sửa `RATIOS` + `CF.exprs()` (và `kr_formulas.py` cho đồng bộ).

## BẪY MÔI TRƯỜNG: pip --user từ Claude Code không thấy được từ Task Scheduler (16/09/2026)
App Claude là MSIX package → `pip install --user` chạy trong phiên Claude bị chuyển hướng vào
`%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Python\...`; chạy tay từ Claude thì import OK, nhưng task theo lịch
báo `ModuleNotFoundError` (tvDatafeed, win32com, lxml, pypdf). Đã robocopy overlay ra `%APPDATA%\Roaming\Python` thật bằng task tạm.
Từ nay cài gói cho pipeline KHÔNG dùng `--user` (site-packages hệ thống `Programs\Python\Python312` không bị ảo hoá), hoặc cài từ terminal ngoài Claude.
