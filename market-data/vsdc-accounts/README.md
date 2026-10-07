# vsdc-accounts — số tài khoản giao dịch nhà đầu tư (VSDC) tự động

Thay cho việc copy tay bảng trên https://vsdc.vn/vi/tra-cuu-thong-ke/TK_SL_TKGD_NDT?tab=7 vào sheet "Số TK mở mới" (Table2) của file IB&Brokerage.

## Chạy
```
python pull_vsdc_accounts.py                 # tất cả năm 2015..nay (~2 giây)
python pull_vsdc_accounts.py --years 2026    # chỉ năm cần cập nhật
```
Tự động: bước `vsdc-accounts` trong task **Market Data AM** (thứ Hai). Chạy tay: `powershell -File D:\market-data\Run-Market.ps1 -Slot AM -Only vsdc-accounts`.

## Đầu ra
| File | Nội dung |
|---|---|
| `vsdc_tk_ndt.csv` | master long: `date` (cuối tháng số liệu), `ngay_bao_cao` (ngày VSDC ghi), `ca_nhan`, `to_chuc`, `ca_nhan_nn`, `to_chuc_nn`, `tong` (tích luỹ) |
| `vsdc_tk_ndt_table2.csv` | đúng layout Table2 sheet "Số TK mở mới": Date, Cá nhân, Tổ chức, Cá nhân NN, Tổ chức NN, Tổng, Cá nhân mở thêm, Tổ chức mở thêm, Tăng trưởng, Năm, Quý, Time (+ Ngày báo cáo) |
| `vsdc_tk_ndt.xlsx` | bản Excel của table2 (bảng Excel tên `Table2`) |
Không copy sang OneDrive: file ngành CK `IB&Brokerage_Nganh.xlsx` (build_presentation.py) tự đọc `vsdc_tk_ndt_table2.csv` để ghi đè Table2 sheet "Số TK mở mới" và tạo sheet Data_TK.

`build_workbook_logic.py` (D:\bctc\nganh-chung-khoan) tự nối các tháng mới hơn workbook từ `vsdc_tk_ndt_table2.csv` vào Table2 khi tính Drivers.

## Cơ chế web (để sửa khi VSDC đổi)
- Trang gắn header anti-forgery `__VPToken` (giá trị = `<meta name="__VPToken">` trong HTML) vào mọi `$.ajax` (js/site.js). Thiếu header → HTTP 400 rỗng. Cookie `__VPToken` phải cùng phiên GET.
- `POST /thongke-tkgd_ndt/search`, body JSON `{SearchKey:"<năm>|VI", CurrentPage:n, RecordOnPage:50, OrderBy:"", OrderType:""}` → HTML `<table>`; server cố định **10 dòng/trang** (bỏ qua RecordOnPage) → lật `CurrentPage` tới khi đủ "x / N bản ghi".
- Ngày VSDC ghi là **ngày báo cáo**, không phải cuối tháng (vd 07/05/2026 = số liệu cuối tháng 4). Quy tắc: ngày ≤ 15 → cuối tháng trước; ngày > 15 → cuối tháng đó. Khớp cách file IB&Brokerage đã nhập.
- Đối chiếu 15/09/2026: 125/126 tháng trùng khớp tuyệt đối với Table2 trong workbook; 1 sai lệch là lỗi gõ tay trong workbook (Cá nhân NN 30/06/2024: 4.198 thay vì 41.980, tổng VSDC xác nhận 41.980).
