# news-alert — cảnh báo TIN TỨC theo watchlist cổ phiếu (18/11/2026)

Task Windows **News Alert** chạy **15 phút/lần, 07:00–22:00** (pythonw, không hiện cửa sổ):
kéo 57 feed RSS của news-rss (kho riêng `kho\`, không đụng kho của app) → lọc bài nhắc mã trong `watchlist.csv`
→ bài **chưa báo** (gộp tin trùng nhiều báo, nhớ 14 ngày ở `da_gui.json`) → **toast Windows** (bấm = mở bài) + **email** tổng hợp.

## Thêm / bớt mã
- `Sua-watchlist.bat` → sửa `watchlist.csv`, lưu là xong. Cột:
  - `ma`: mã CK (bộ phân loại news-rss tự nhận mã 3 ký tự + tên DN trong `news-rss\config\alias_ma.csv`, VD "Hòa Phát" → HPG)
  - `ten_goi_them`: tên gọi khác tự khai, cách nhau `;` (VD `Nhựa Bình Minh;BMP`) — khớp nguyên từ trong tiêu đề/tóm tắt
  - `ghi_chu`: tuỳ ý
- Hoặc dòng lệnh: `python news_alert.py them VCB MWG` · `python news_alert.py xoa HPG` · `python news_alert.py ds`

## Cấu hình — `config.json`
| khoá | ý nghĩa |
|---|---|
| `toast_bat` | thông báo góc màn hình Windows |
| `email_bat`, `email_gui_den`, `smtp_user` | email tổng hợp mỗi lần có tin mới (Gmail SMTP 465) |
| `gio_bat_dau`, `gio_ket_thuc` | ngoài khung giờ thì giữ tin, báo vào lần chạy sau |
| `chi_bao_tin_moi_trong_gio` | chỉ báo bài đăng trong N giờ gần nhất (mặc định 12) |
| `toi_da_toast_le` | > N tin một lượt → gộp 1 toast tóm tắt (chi tiết ở email / `lich_su.csv`) |

### Bật email (Gmail)
1. Bật xác minh 2 bước cho tài khoản Gmail gửi → tạo **Mật khẩu ứng dụng** tại myaccount.google.com/apppasswords.
2. Lưu mật khẩu vào biến môi trường User (không ghi vào file), trong PowerShell:
   `[Environment]::SetEnvironmentVariable('NEWS_ALERT_SMTP_PASS','<mật khẩu ứng dụng>','User')`
3. `config.json`: `"email_bat": true`, `"smtp_user": "<gmail gửi>"`, `"email_gui_den": "<email nhận, nhiều địa chỉ cách dấu phẩy>"`.
4. Thử: `python news_alert.py --thu` (gửi 2 bài mới nhất khớp watchlist, không ghi `da_gui.json`).

## File
`news_alert.py` (lõi) · `toast.ps1` (hiện toast qua WinRT, không cần cài gói) · `lich_su.csv` (mọi tin đã báo) ·
`logs\alert.log` · `kho\` (tin RSS 14 ngày).
Windows: nếu không thấy toast → Settings › System › Notifications: bật cho **Windows PowerShell**, tắt Do not disturb.
