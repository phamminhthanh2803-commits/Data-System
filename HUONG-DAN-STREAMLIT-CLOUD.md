# Đưa app Market Data lên Streamlit Community Cloud (miễn phí) — hướng dẫn từng bước

*12/10/2026. Dành cho người không phải dev: chỉ cần bấm chuột và dán 1 dòng secret. Không sửa code.*

App chạy trên máy chủ của Streamlit (miễn phí), đọc dữ liệu pipeline trên **Google Drive** (`gdrive:pipeline-data/market-data/…`,
chính là dữ liệu GitHub Actions đẩy lên hằng ngày). Lúc mở lần đầu app tự tải `rclone`, tự kéo ~560 MB dữ liệu về máy chủ
(≈ 60–90 giây, có thanh tiến độ), sau đó cứ 30 phút kéo lại phần mới. Mã nguồn lấy từ repo GitHub **Data-System**
(`phamminhthanh2803-commits/Data-System`, nhánh `main`, file chính `market-data/app/app.py`).

## 0. Cần có sẵn

- Tài khoản GitHub đã có quyền vào repo `Data-System` (repo **private** – Streamlit Cloud miễn phí cho phép **1 app private**).
- Laptop có `rclone` đã kết nối Google Drive (remote tên `gdrive`, file `%APPDATA%\rclone\rclone.conf`) — đã có từ 07/10/2026.
- **Không cần** 2 secret DNSE (`DNSE_*`) cho app này: app chỉ đọc parquet real-time trên Drive do bộ thu ghi, không gọi DNSE.

## 1. Tạo secret `RCLONE_CONF` (1 dòng, làm trên laptop)

Mở **PowerShell** (Start → gõ `powershell` → Enter), dán lệnh sau rồi Enter. Lệnh mã hoá file `rclone.conf` thành base64
và **copy vào clipboard** (không hiện ra màn hình):

```powershell
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:APPDATA\rclone\rclone.conf")) | Set-Clipboard
```

Clipboard giờ chứa 1 chuỗi dài (~900 ký tự). **Không dán chuỗi này vào chat, email, GitHub hay file nào trong repo** — nó
tương đương mật khẩu vào Google Drive. Chỉ dán vào ô Secrets ở bước 3.

## 2. Tạo app trên share.streamlit.io

1. Vào <https://share.streamlit.io> → **Continue with GitHub** → đăng nhập GitHub → cho phép Streamlit truy cập repo
   (chọn *All repositories* hoặc ít nhất repo `Data-System`).
2. Bấm **Create app** (góc phải trên) → chọn **Deploy a public app from GitHub** (với repo private, Streamlit vẫn cho deploy
   nhưng app sẽ là **private**: chỉ người được mời xem được).
3. Điền:
   - **Repository**: `phamminhthanh2803-commits/Data-System`
   - **Branch**: `main`
   - **Main file path**: `market-data/app/app.py`
   - **App URL**: đặt tên tuỳ ý, ví dụ `pv2-market-data` → app sẽ ở `https://pv2-market-data.streamlit.app`

## 3. Advanced settings: Python 3.12 + Secrets

Bấm **Advanced settings…** (ngay dưới App URL) trước khi Deploy:

- **Python version**: chọn **3.12**.
- **Secrets**: dán đúng **1 dòng** (Ctrl+V chuỗi ở bước 1 vào giữa 2 dấu nháy):

  ```toml
  RCLONE_CONF = "<dán chuỗi base64 ở đây>"
  ```

- **Save** → **Deploy!**

Streamlit sẽ cài thư viện theo `market-data/app/requirements.txt` (2–4 phút lần đầu), rồi chạy app. Lần mở đầu thấy hộp
**“Lần đầu mở trên cloud: đang kéo dữ liệu từ Google Drive (≈ 1–2 phút)…”** liệt kê từng thư mục đang kéo; xong thì hiện
*“Đã kéo 556 MB (64 file) trong ~60 s · làm mới mỗi 30 phút”* và trang Tổng quan hiện ra. Chân trang có dòng
**Cloud: dữ liệu kéo từ Google Drive lúc …** để biết app đang chạy chế độ cloud.

## 4. Mời người xem (app private)

Trên trang quản lý app (share.streamlit.io → app của bạn) → **⋮** (3 chấm) → **Settings** → tab **Sharing**:
nhập email (Google/GitHub) của người được xem → **Save**. Người đó vào link app, đăng nhập bằng email đó là xem được.
Gói miễn phí: **1 app private**, số người xem không giới hạn (nhưng cùng dùng chung 1 máy chủ nhỏ).

## 5. Xem log khi có lỗi

Trang app → góc dưới phải **Manage app** → bảng log hiện ra (đây là `stdout` của app). Các dòng `[cloud_boot] …` cho biết
từng bước kéo dữ liệu; `rclone exit …` kèm 400 ký tự cuối lỗi rclone. Lỗi hay gặp:

| Thấy trong log | Nguyên nhân | Cách xử lý |
|---|---|---|
| `Kéo dữ liệu lỗi: … rclone copy index-fetcher loi` / `couldn't find remote gdrive` | secret `RCLONE_CONF` sai / thiếu / dán thừa dấu | Làm lại bước 1 + 3 (Settings → Secrets), rồi **Reboot app** |
| `token expired` / `invalid_grant` | token Drive trong `rclone.conf` hết hạn (laptop cũng sẽ lỗi) | Trên laptop chạy `rclone config reconnect gdrive:` rồi tạo lại secret (bước 1 + 3) |
| `ModuleNotFoundError` | thư viện chưa có trong `market-data/app/requirements.txt` | báo lại để thêm; Streamlit tự cài lại khi push repo |
| `Oh no. Error running app` + app tắt | **hết RAM** (máy chủ miễn phí ~1 GB; app đo trên laptop đỉnh ~1,1 GB lúc khởi động) | **Reboot app**; nếu lặp lại → xem mục 7 |

## 6. Giới hạn của gói miễn phí & cách đánh thức

- **Ngủ sau 12 giờ** không ai mở: link app hiện nút **“Yes, get this app back up!”** → bấm là máy chủ bật lại (≈ 1–3 phút:
  cài lại thư viện nếu cần + kéo lại dữ liệu từ Drive vì `/tmp` bị xoá khi ngủ).
- **RAM ≈ 1 GB** (Streamlit công bố 690 MB – 2,7 GB tuỳ lúc), CPU chia sẻ → trang đầu chậm hơn laptop (6–11 s/trang sau khi
  đã kéo dữ liệu), nhiều người cùng xem sẽ chậm thêm.
- **Không có đĩa bền**: mọi thứ app kéo về nằm ở `/tmp` của máy chủ, mất khi app ngủ/reboot — nên app luôn kéo lại từ Drive,
  không cần làm gì.
- **Dữ liệu tới đâu?** = Drive tới đâu: pipeline cloud (GitHub Actions) đẩy lên 10:30 / 18:30; app làm mới mỗi 30 phút
  (chỉ kéo file đã đổi) — bảng **Độ tươi** ở trang Tổng quan cho biết ngày cuối từng bộ.
- Lớp **live-first** (Entrade/VNDirect/CafeF) vẫn chạy trong app trên cloud (thread nền, 30 phút/lần). Lần đầu app kéo sẵn
  cache nguồn (`app-cache/src`, ~60 MB) mà app laptop đã đẩy lên Drive, nên **không** phải kéo nền 1.525 mã Entrade trên máy chủ.
  Muốn cache này mới: mở app trên laptop (thread nền tự đẩy lên Drive sau mỗi lần cập nhật).
- **Real-time (● LIVE)** trong phiên: app cloud đọc `gdrive:pipeline-data/realtime/<ngày>/` do bộ thu DNSE ghi (xem README app,
  mục data_live chế độ cloud).

## 7. Nếu app bị tắt vì hết RAM (chỉ khi xảy ra)

1. **Reboot app** (Manage app → ⋮ → Reboot). Thường đủ vì lúc khởi động app dựng cache giá là lúc tốn RAM nhất.
2. Nếu vẫn lặp lại: vào Settings → Secrets, thêm dòng `CLOUD_REFRESH_SEC = "3600"` (làm mới 60 phút thay vì 30) và/hoặc
   báo lại để tắt bớt lớp live-first trên cloud (`SRC_CACHE_PUSH`, `APP_NO_BG=1` trong secrets → app chỉ dùng dữ liệu pipeline).

## 8. Cập nhật app sau này

Sửa code trên laptop (`D:\market-data\app`) → `python D:\cloud-deploy\pack_code.py` → `git add/commit/push` trong `D:\cloud-deploy`
(như quy trình pipeline). Streamlit Cloud **tự deploy lại** mỗi khi nhánh `main` có commit mới (không cần vào web).
Thay đổi secret: Settings → Secrets → Save → app tự khởi động lại.

## 9. Những file liên quan (để biết, không cần sửa)

| File | Vai trò |
|---|---|
| `market-data/app/cloud_boot.py` | nhận biết cloud, tải rclone, ghi `rclone.conf` từ secret, kéo dữ liệu về `/tmp/pipeline-data/market-data`, thread làm mới 30 phút, `rclone_cmd()` dùng chung cho real-time |
| `market-data/app/requirements.txt` | thư viện Python app cần (Streamlit Cloud đọc file này) |
| `.streamlit/config.toml` (gốc repo và trong `market-data/app`) | theme sáng Genea + `headless` |
| `.gitignore` | chặn `secrets.toml`, `rclone.conf`, `cache/`, `app-cache/`, `.data/` — **không bao giờ** có secret trong git |
| `data_manifest.py` | bản đồ thư mục dữ liệu trên Drive (cloud_boot chỉ kéo các file app đọc) |

Kiểm chứng 12/10/2026 (giả lập cloud trên laptop: `STREAMLIT_CLOUD=1`, `MD_ROOT` = thư mục trống, secret trong
`secrets.toml`): kéo lần đầu 556 MB / 64 file trong 62 s (index-fetcher 12,5 s; market-valuation 4,9; transmission 4,6;
nso 6,3; macro 4,1; vsdc 3,6; bond-pivot 6,0; app-cache/src 5,6) + dựng 3 parquet giá ~20 s → trang Tổng quan sẵn sàng sau 81 s;
5 trang chính mở 6–11 s, không traceback. Ảnh: `market-data/app/design/screens/17-cloud-boot.png`.
