# D:\bctc\nganh-bat-dong-san — FILE NGÀNH BẤT ĐỘNG SẢN (tạo 21/09/2026)

Pipeline tương tự file ngành chứng khoán (`D:\bctc\nganh-chung-khoan`), nhưng:
- **Nguồn BCTC = Vietcap (VCI) toàn sàn** qua dump của `D:\bctc\fs-extractor\output` (không cần xuất FiinProX từng mã). VCI chỉ có từ **2018-Q1**.
  DNSE đã thử (api-bo.dnse.com.vn/senses-api/financial-report/details): công khai nhưng chỉ 10 quý gần nhất, ~40 chỉ tiêu rút gọn, khớp VCI → không dùng.
- **Không có workbook mẫu** → file dựng từ đầu bằng openpyxl theo khung sheet của file CK, rồi Excel COM tính lại + lưu + tự kiểm tra.
- **Chỉ file local**: `Nganh_BDS.xlsx` trong thư mục này, không chép OneDrive, không gắn Task Scheduler.

## Chạy
```
python run_nganh_bds.py              # dựng lại từ dump VCI + giá/market-data mới nhất (~1-2 phút)
python run_nganh_bds.py --refresh    # BCTC quý mới: kéo lại BCTC VCI cho mã BĐS (fsx.py bctc, gộp vào dump) rồi dựng (~15-20 phút)
python run_nganh_bds.py --no-com     # không mở Excel (file vẫn tự tính khi mở)
```

## Các bước / file
| Bước | Script | Ra |
|---|---|---|
| 1 | `build_nganh_bds.py` | `raw\*.parquet` (trích từ dump ~3 GB, chỉ trích lại khi CSV nguồn đổi), `data_fs.csv`, `dim_item.csv`, `dim_company.csv`, `nhom_bds.csv`, SQLite `nganh_bat_dong_san.sqlite` (fact_fs, dim_company, dim_item) |
| 2 | `build_valuation_bds.py` | `valuation_bds_stocks_daily.csv`, `valuation_bds_nhom_daily.csv`, `drivers_bds.csv`, `bond_maturity_bds.csv` (+ bảng SQLite) |
| 3 | `build_workbook_bds.py` (+ `metrics_bds.py`) | `Nganh_BDS.xlsx` |

## Phạm vi & nhóm (`nhom_bds.csv` — user sửa được)
- ICB cấp 2 "Bất động sản" của VCI (110 mã) + mọi mã thêm tay vào `nhom_bds.csv`.
- Nhóm: Phát triển nhà ở & khác / Khu công nghiệp / Vingroup / Dịch vụ BĐS (L4 "Tư vấn, định giá, môi giới"). Tổng hợp: ALL, EXVIN, NHA, KCN, VIN, DV.
- `cong_vao_nganh = 0`: **VIC** (hợp nhất VHM, VRE + VinFast) và **DXS** (con của DXG) — không cộng vào tổng để khỏi đếm đôi, vẫn xem riêng được.
- File tạo tự động lần đầu; lần sau chỉ THÊM mã mới, giữ nguyên chỉnh sửa của user.

## Khoá dữ liệu
VCI trả **cùng một thứ tự dòng** cho mọi mã/kỳ (đã kiểm: 1 chuỗi item_id duy nhất mỗi báo cáo) → `row_order` = vị trí dòng trong (mã, kỳ); khoá Data_FS = `mã|báo cáo|row_order`
(nhóm: `G:ALL|IS|3`). item_id VCI bị trùng (cost, accumulated_depreciation, short_term_investments, held_to_maturity...) nên KHÔNG dùng làm khoá; `dim_item.key_item` đánh số `#k`.
`check_layout()` cảnh báo nếu VCI đổi bố cục. Năm: dòng chảy (IS, CF, thuyết minh noc102–146, 155) = tổng 4 quý đủ; số dư = Q4. Dòng toàn 0 bị bỏ khỏi Data_FS (công thức dùng N() cho khoản cộng).

## Workbook `Nganh_BDS.xlsx`
| Sheet | Nội dung |
|---|---|
| Hướng dẫn | nguồn, phạm vi, định nghĩa, cách cập nhật |
| DASHBOARD | dropdown nhóm B4 → 7 biểu đồ quý (Chart_Data) + P/B, P/E ngày, TPDN, lãi suất, khối ngoại |
| FS Industry / (năm) | BCTC đầy đủ (KQKD, CĐKT 121 dòng, LCTT, thuyết minh chọn lọc) của nhóm chọn ở B4 — INDEX/MATCH Data_FS |
| FS Công ty / (năm) | như trên cho 1 mã chọn ở B4 |
| Key ratios / (năm) | CHỈ số tính toán + tỷ lệ, công thức tham chiếu thẳng dòng của FS Industry (khối trên) và FS Công ty (khối dưới) — sửa 22/09/2026 theo yêu cầu tách FS / ratios |
| So sánh mã / (năm) | 1 chỉ tiêu (C4) × 12 mã (B8:B19) + trung vị (AGGREGATE) + 1 nhóm (C21) + biểu đồ; đọc từ Calc_SoSanh(_Nam) = 13 khối giống Key ratios |
| Bảng mã | mọi mã tại 1 kỳ chọn (C3): vốn hoá, P/E, P/B (giá gần nhất) + DT/LNST TTM, biên gộp, ROE, nợ vay ròng/VCSH, tồn kho, người mua trả trước, CFO — công thức INDEX vào `fs_q` |
| Drivers | VN-Index, định giá ngành cuối quý, TPDN BĐS phát hành/đến hạn/lãi suất (bond-pivot), lãi suất & tín dụng (transmission-fetcher), khối ngoại (Vietcap IQ); lịch đáo hạn 12 quý tới |
| Data_FS / Data_DM / Data_DinhGia | dữ liệu giá trị; Names: dm_ma, dm_nhom, dm_ct, dm_ky, fs_q |

Thêm/sửa chỉ tiêu: sửa `BLOCK` trong `metrics_bds.py` (token `{x}`, `{x@ttm}`, `{x@ttm0}`, `{x@avg}`, `{x@lag}`) rồi chạy lại — mọi sheet (Key ratios, Calc, So sánh, Chart_Data) dùng chung.

## Định nghĩa
TTM = 4 quý liên tiếp. ROE = LNST CĐ mẹ TTM / VCSH CĐ mẹ bình quân (t, t−4). ROA = LNST TTM / TTS bình quân. Nợ vay = vay & nợ thuê TC ngắn + dài hạn.
Nợ vay ròng = nợ vay − tiền − ĐTTC ngắn hạn. Chi phí vốn vay = CP lãi vay TTM / nợ vay BQ. Người mua trả trước = ngắn + dài hạn.
Định giá: vốn hoá = giá TradingView (đã điều chỉnh) × số CP hiện hành; BCTC hiệu lực sau cuối quý + 45 ngày; P/E nhóm = Σ vốn hoá / Σ LNST TTM (gồm lỗ); P/B = Σ vốn hoá / Σ VCSH CĐ mẹ.
TPDN đến hạn = giá trị phát hành − đã mua lại (quý đang chạy và các quý tới: giá trị đang lưu hành).

## Kiểm định (21/09/2026)
Excel tính lại: 0 ô lỗi. Đối chiếu Python ở Q2-2026 khớp tuyệt đối: toàn ngành biên gộp TTM 43,4%, ROE 19,5%, nợ vay ròng/VCSH 0,34x, NMTTT/tồn kho 39,8%; NLG 42,3% / 5,6% / −0,07x / 33,9%.

## Lưu ý dữ liệu
- 7 mã chưa có giá TradingView: C21, DCH, ITA, MGR, PPI, SLD, XDH (không vào định giá ngày; BCTC vẫn có). TBR, DCH thiếu báo cáo KQKD trên VCI.
- Thuyết minh VCI (BĐS dở dang noc19, hàng hoá BĐS noc24, trái phiếu noc96) không phủ đủ mọi mã/kỳ.
- Nhóm Dịch vụ BĐS nhỏ (THD P/B ~9) → P/E nhóm nhiễu. KSF Q2-2026 LNST đột biến (ROE ~100%) — số nguồn.
