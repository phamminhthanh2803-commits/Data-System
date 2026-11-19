# news-alert — cảnh báo TIN TỨC theo watchlist cổ phiếu (18/11/2026)

Chạy **online 24/7**, không cần mở laptop hay app:

| Thành phần | Ở đâu | Làm gì |
|---|---|---|
| **GitHub Actions `News Alert`** (repo Data-System, `.github/workflows/news-alert.yml`) | cloud, 15 phút/lần 07:00–22:45 | kéo 57 feed RSS → lọc tin có mã trong watchlist → **email tin mới**; sau `tom_tat_email_gio` (17h) gửi **1 email tóm tắt cả ngày** do Claude Sonnet viết |
| **App Market Data › Tin tức › Watchlist** | laptop + Streamlit Cloud | sửa watchlist, cấu hình email, **🤖 Tóm tắt** (Sonnet) theo khung Trong ngày / 24 giờ / 3 ngày / 7 ngày / Tuỳ chọn, 2 hạng mục **Vĩ mô** + **Tin doanh nghiệp**; ô **🔎 Tìm theo mã** = xem tin / tóm tắt riêng mã (cả mã ngoài watchlist); xem tin khớp + lịch sử email |
| Task Windows **News Alert** | laptop, khi máy bật | thêm **thông báo góc màn hình** (toast, bấm = mở bài) |

Dữ liệu dùng chung ở Google Drive `gdrive:pipeline-data/market-data/news-alert/` (KHÔNG vào repo public):
`watchlist.csv`, `config.json` (app / CLI sửa, Actions chỉ đọc) · `da_gui.json`, `lich_su.csv`, `trang_thai_email.json`, `kho/`,
`tom_tat/<ngày>.md|json` (Actions + app ghi). Laptop giữ riêng trạng thái toast: `da_gui_may.json`, `lich_su_may.csv`.

## Cài đặt một lần (PV2 tự làm — không ai khác nhập được mật khẩu / key)
1. **Mật khẩu ứng dụng Gmail**: bật xác minh 2 bước cho Gmail gửi → myaccount.google.com/apppasswords → tạo mật khẩu.
2. **API key Anthropic** (tóm tắt Sonnet): platform.claude.com → API keys → tạo key.
3. **GitHub** repo Data-System → Settings → Secrets and variables → Actions → New repository secret:
   `NEWS_ALERT_SMTP_PASS` = mật khẩu ứng dụng Gmail · `ANTHROPIC_API_KEY` = API key.
4. **Streamlit Cloud** (share.streamlit.io → app → Settings → Secrets) thêm 2 dòng (nút Tóm tắt / Gửi thử trên app online):
   `ANTHROPIC_API_KEY = "..."` và `NEWS_ALERT_SMTP_PASS = "..."`.
5. **Laptop** (nút Tóm tắt khi chạy app local), PowerShell:
   `[Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY','<key>','User')` rồi mở lại app.
6. App › Tin tức › Watchlist › **Email thông báo**: điền Gmail gửi + email nhận → 💾 Lưu.
7. Thử: GitHub → Actions → News Alert → Run workflow → tick `thu`.

## Thêm / bớt mã
App › Tin tức › **Watchlist** → bảng *Danh sách theo dõi* → 💾 Lưu (đẩy lên Drive, lần quét kế tiếp dùng).
Cột `ma` (mã CK; bộ phân loại news-rss tự nhận cả tên DN theo `news-rss\config\alias_ma.csv`), `ten_goi_them` (tên khác, cách `;`).
Dòng lệnh: `python news_alert.py them VCB MWG` · `xoa HPG` · `ds`.

## config.json
`email_bat`, `email_gui_den`, `smtp_user` (Gmail SMTP 465) · `gio_bat_dau`/`gio_ket_thuc` (ngoài khung → giữ tin, báo lần sau) ·
`chi_bao_tin_moi_trong_gio` (12) · `tom_tat_email_gio` (17; bỏ trống = không gửi email tóm tắt) · `toast_bat`, `toi_da_toast_le` (laptop).

## File code
`news_alert.py` (lõi + đồng bộ Drive bằng rclone) · `tom_tat.py` (Claude Sonnet `claude-sonnet-5-5`, effort medium,
fallbacks "default"; chỉ dựa trên tiêu đề + tóm tắt RSS) · `toast.ps1` (WinRT) · `requirements.txt` (Actions) · `Sua-watchlist.bat`.
Chi phí tóm tắt ~ vài nghìn token/ngày (Sonnet 5.5: $2 vào / $10 ra mỗi 1M token).
Không thấy toast trên laptop → Settings › System › Notifications: bật cho **Windows PowerShell**, tắt Do not disturb.
