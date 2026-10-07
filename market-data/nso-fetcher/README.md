# nso-fetcher — số liệu kinh tế Cục Thống kê (NSO) cho phân tích chuỗi thời gian

Kéo **toàn bộ bảng số liệu** trên PX-Web của NSO (`https://pxweb.nso.gov.vn/pxweb/vi/`) về 1 file long-format
+ 1 file Excel dạng rộng (mỗi bảng 1 sheet, cột = series, dòng = kỳ), và tải kèm file Excel "Biểu số liệu"
của Báo cáo tình hình KT-XH hằng tháng (nguồn số liệu **tháng**). Chạy tự động thứ Hai trong **Market Data AM**
(bước `nso`, `nso-monthly` trong `..\Run-Market.ps1`).

## Nguồn & cách lấy (khảo sát 07/10/2026)
| Nguồn | Nội dung | Cách lấy |
|---|---|---|
| PX-Web NSO (16 CSDL, ~330 bảng, mã `Vxx.yy`) | **Niên giám**: GDP, thu chi NSNN, M2/tín dụng/lãi suất (V03.18–21), chứng khoán (V03.26), CPI/PPI/giá XNK (V11), XNK theo mặt hàng/nước (V09), bán lẻ (V08), IIP + sản phẩm CN (V07), vốn đầu tư + FDI (V04), DN (V05), du lịch (V10), vận tải (V12), nông nghiệp (V06), lao động (V02). Hầu hết **theo năm** (từ 1986–1995), riêng **CPI theo tháng** (V11.01–V11.07, từ 1995/2010). Số mới nhất = năm 2025 ("Sơ bộ"/"Ước tính"). | API REST `/api/v1/vi/` chỉ mở 4 CSDL và POST bị 404 → **không dùng API**. Dùng form ASP.NET: GET trang chọn biến → POST chọn hết giá trị + `OutputFormat=FileTypeJsonStat` → JSON-stat (có 1 byte NUL cuối file). Danh sách bảng chỉ hiện khi `?tablelist=true`. |
| Báo cáo KT-XH tháng (`nso.gov.vn/bao-cao-tinh-hinh-kinh-te-xa-hoi-hang-thang/`) | File **Biểu số liệu** (.xlsx, ~20 sheet): nông nghiệp, IIP tháng + theo địa phương, sản phẩm CN, lao động DN, DN đăng ký/quay lại/ngừng/giải thể, vốn NSNN, FDI, tổng mức bán lẻ, XK/NK theo mặt hàng, CPI + lạm phát cơ bản, vận tải, khách quốc tế, xã hội | Quét trang danh sách → bài → link `wp-content/uploads/*.xlsx`. Danh sách lùi tới 01/2000 (bài 2000–2019 được đăng lại 2019–2020 với slug `bc-tinh-hinh...`/`tinh-hinh-kinh-te-xa-hoi...`, thư mục /YYYY/MM/ trong URL KHÔNG phải kỳ báo cáo). 317 file 2000-01 → 2026-09; file 2000–2018 là .xls (74 file xlrd không đọc được đã chuyển sang .xlsx bằng Excel COM, bản gốc trong `monthly-reports\xls-goc\`). `parse_monthly_reports.py` nhận sheet theo tiêu đề A1 (tên sheet đổi lung tung) và phân loại tiêu đề cột bằng máy trạng thái (khối 'Sơ bộ/Ước tính' → mức, 'So với cùng kỳ' → YoY, 'Cơ cấu/kế hoạch' → bỏ, kéo dài sang các cột gộp ô) ("Tháng N năm Y so với cùng kỳ", "Sơ bộ/Ước tính tháng N", "K tháng"...), tên mục chuẩn hoá (hoá/hóa, đổi tên nhóm CPI) → `nso_monthly_master.csv`. Metric: CPI = IDX_BASE/YOY/VS_DEC/MOM/AVG_YTD_YOY (chỉ số, 104,9 = +4,9%); XK/NK/RETAIL/SVC/INVEST/NSNN/TOURIST = LEVEL, YOY (+_Q quý, _YTD luỹ kế, _YEAR năm); IIP = YOY/MOM/YOY_Q/YOY_YTD; FDI = PROJECTS_YTD/REG_NEW_YTD/REG_ADJ_YTD (luỹ kế); GDP = LEVEL_HH_Q/_YTD/_YEAR (giá hiện hành), LEVEL_SS_* (giá so sánh), YOY_Q/_YTD/_YEAR (tăng trưởng); PPI = YOY_Q/QOQ/YOY_YTD/YOY_YEAR; LABOR = LEVEL_Q/_YTD/_YEAR; UNEMP = RATE_Q/_YTD/_YEAR (bảng dòng = kỳ). Báo cáo quý (T3/6/9/12) có thêm GDP, PPI, XNK dịch vụ, vốn đầu tư toàn XH, lao động; số quý mới nhất = Q3/2026. File tháng sau ghi đè tháng trước (Sơ bộ thay Ước tính). |

Không có trên PX-Web: số **tháng** của IIP/bán lẻ/XNK/FDI (chỉ trong Biểu số liệu tháng hoặc IMF — xem `..\macro-fetcher`),
GDP quý (chỉ có năm; GDP quý lấy từ báo cáo quý/IMF QNEA).

## Files
```
fetch_nso.py              script chính: liệt kê bảng → tải JSON-stat → parse → merge master → catalog → gọi build_timeseries
pxweb.py                  thư viện: list_databases / list_tables / fetch_table / parse_table (JSON-stat → long)
build_timeseries.py       nso_master.csv → nso_timeseries.xlsx (sheet DANH MUC + mỗi bảng 1 sheet dạng rộng)
fetch_monthly_reports.py  tải Excel Biểu số liệu báo cáo KT-XH tháng → monthly-reports\YYYY-MM_<tên gốc>.xlsx + monthly_reports_index.csv, rồi gọi parse
parse_monthly_reports.py  đọc mọi sheet nhận dạng được theo TIÊU ĐỀ (14 nhóm: CPI, PPI, XK, NK, SVC, IIP, RETAIL, FDI, GDP, INVEST, NSNN, TOURIST, LABOR, UNEMP)
                          của file tháng VÀ file quý → nso_monthly_master.csv (long: date,series_id,group,metric,item,section,unit,status,value,src)
nso_master.csv            long: date,freq,table_id,series_id,pos,dim1,dim2,dim3,unit,status,value,updated,source
nso_catalog.csv           1 dòng/bảng: db,table_id,title,dims,time_dim,freq,n_series,n_rows,first,last,updated,fetched_at
nso_timeseries.xlsx       file phân tích chuỗi thời gian (dựng lại mỗi lần chạy)
raw\<table>.json          JSON-stat gốc của lần kéo gần nhất
```

## Quy ước dữ liệu
- `date`: `YYYY` (freq **A**), `YYYY-MM` (**M**), `YYYY-Qn` (**Q**), hoặc chuỗi gốc như `Tổng số`, `1988-1990` (**X** — không phải mốc thời gian, vẫn giữ để tra).
- `status`: `Sơ bộ` / `Ước tính` theo nhãn năm của NSO; năm sau NSO chốt số thì dòng cùng khóa `(table_id, series_id, date)` được **ghi đè**, status về rỗng.
- `series_id` = `table_id|dim1|dim2|dim3` (nhãn gốc tiếng Việt, bỏ khoảng trắng thừa; dim thứ 4 trở đi gộp vào dim3). `pos` = thứ tự xuất hiện trong bảng NSO (giữ "Tổng số" trước nhóm con khi dựng sheet rộng).
- `unit`: tách từ ngoặc cuối nhãn series hoặc tiêu đề bảng (`Tỷ đồng`, `%`, `Năm trước = 100`…); rỗng nếu không tách được.
- Bảng có nhiều tần suất (V11.01: tháng + các dòng "Năm 2010 = 100") tách thành sheet `V11.01_M`, `V11.01_A`.

## Chạy tay
```
python fetch_nso.py                                   # 11 CSDL kinh tế (~330 bảng, ~10 phút), dựng Excel
python fetch_nso.py --tables V11.06,V03.01 --no-excel # vài bảng
python fetch_nso.py --db "Chỉ số giá;Thương mại"      # vài CSDL;  --db all = cả 16 CSDL kể cả nhóm PLV* (phân theo vùng)
python fetch_nso.py --list                            # chỉ liệt kê
python build_timeseries.py --db "Chỉ số giá" --freq M --out cpi_thang.xlsx
python fetch_monthly_reports.py --since 2023
```
Dùng trong pandas: `df = pd.read_csv("nso_master.csv", dtype={"date": str}); cpi = df[df.table_id=="V11.06"].pivot(index="date", columns="dim1", values="value")`.

## Bẫy đã gặp
- Header `Referer` có dấu tiếng Việt → curl_cffi lỗi latin-1 → luôn `urllib.parse.quote` đường dẫn trước khi dùng.
- PX-Web không cho biết ngày cập nhật từng bảng (API `updated` chỉ có ở 4 CSDL) → kéo lại hết mỗi tuần; `updated` trong JSON-stat đôi khi là `9999-12-31` (bỏ trống).
- Nhãn dim có thụt đầu dòng thể hiện cấp bậc (`"     Lương thực"`) → đã strip, giữ thứ tự bằng `pos`.

## Dùng trong app Streamlit (07/10/2026)
`D:\market-data\app\datalib.py`: `nm()/nm_last()` (số tháng), `cpi_nso()` (PX-Web V11.06/02/05 nối báo cáo tháng), `trade_nso()`, `iip_nso()`, `fdi_nso()` (NSO ghi đè IMF, IMF bù lịch sử trước 2023), `nso_table()/nso_catalog()` (tab Niên giám NSO). REGISTRY: `nso_monthly`, `nso`.

## File cũ 2000–2019 (07/10/2026)
- Chữ Việt trong file 2000–2010 theo bảng mã TCVN3 (`S¶n xuÊt c«ng nghiÖp`) → `tcvn3()` đổi sang Unicode; chuỗi trộn ("XuÊt khÈu th¸ng 7 đầu năm 2008") chỉ đổi ký tự đặc trưng + chữ hoa Latin-1 đứng sau chữ thường.
- File 2008–2019 bị NSO đổi mã sai trên chữ đã là Unicode (á→ỏ, â→õ, ê→ờ: "Thỏng 7", "Khai khoỏng", "so sỏnh") → sửa theo danh sách `_MOJIBAKE` cho tiêu đề cột; tên mục sửa bằng cách đọc file MỚI trước rồi với mục lạ thử đảo ngược mã (`moji_rev`) xem có trùng khoá đã biết không.
- Kỳ ghi "6 tháng/2000", "tháng 7/2001"; số lưu dạng chuỗi; dòng "A | 1 | 2 | 3" đánh số cột → `fix_grid`.
- Trước 2011 không có IIP (chỉ có Giá trị sản xuất công nghiệp giá 1994 — chưa parse); CPI theo nhóm cũ (Lương thực, thực phẩm; Phương tiện đi lại, bưu điện…) giữ tên gốc; FDI 2001–2019 chỉ có `REG_TOTAL_YTD` (vốn đăng ký, nghìn USD đã quy về triệu USD); bán lẻ 2004–2011 nhiều tháng chỉ có luỹ kế.
