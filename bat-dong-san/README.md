# D:\bat-dong-san — hub BẤT ĐỘNG SẢN (tạo 17/10/2026)

Hệ thống data dự án BĐS từ batdongsan.com.vn, dựng theo đúng khuôn hub `D:\shipping` (scraper → kho `store/` parquet → app Streamlit mẫu Genea).

```
D:\bat-dong-san\
  run_slot.py             runner (lõi D:\market-data\runlib.py): python run_slot.py --slot AM  -> bước bds-projects; status-AM.txt, logs\
  batdongsan-projects\    SCRAPER bds_scrape.py + kho store\ (parquet) + logs\
  bds-tracker\            APP Streamlit "BĐS Tracker": Chay-app.bat -> http://localhost:8767 (Market 8765, Port Tracker 8766)
```

## 1. Nguồn & cách lấy (`batdongsan-projects\bds_scrape.py`)
Trang chặn bot bằng Cloudflare → dùng `curl_cffi` giả lập Chrome (`impersonate=chrome124`), 1 request/giây, 403/429 thì nghỉ 5/20/60 s và đổi fingerprint. Không cần đăng nhập, không có API chính thức.

| Lớp | Cờ | Nguồn trên web | Ra |
|---|---|---|---|
| 0. Danh bạ địa lý | `--geo` | JSON `GetDataForBoxSearch` (63 tỉnh cũ → 710 quận/huyện → 6.090 dự án) | `store/geo.json`, `store/geo_projects.parquet` (project_id → tỉnh, quận) |
| 1. Danh sách dự án | `--master` | `/du-an-bat-dong-san/p1..p609` (10 dự án/trang, thẻ `.js__card-project-web`) | `store/projects.parquet` (1 dòng/dự án: tên, trạng thái, loại hình từ URL, địa chỉ, diện tích, số căn, số tòa, tóm tắt, chủ đầu tư, số ảnh, first_seen/last_seen) + `store/project_changes.parquet` (ngày, dự án, trường, cũ → mới khi đổi trạng thái/số căn/tên/địa chỉ/chủ đầu tư; dự án mới = `new`) |
| 2. Chi tiết | `--details N` | trang dự án `/du-an-.../<slug>-pjNNNN` (bảng `.re__project-attr-box`, breadcrumb JSON-LD, Google Maps embed) | cột `d_*`, `city/district`, `lat/lng`, `investor_name/investor_id` (ep), `legal`, `price_text/price_lo/hi` (triệu/m²), `build_area_m2`, `floors`, `density`, `handover`, `attrs_json`, `sale_types`, `desc`, `detail_at` trong projects.parquet |
| 3. Tin rao | `--listings N` | `/nha-dat-ban-<slug>` và `/nha-dat-cho-thue-<slug>` (trang 1 = 20 tin + `#count-number` tổng số tin) | `store/listing_stats/<YYYY-MM>.parquet`: 1 dòng/ngày/dự án/loại: `n_total`, `n_sample`, trung vị + P25/P75 của giá (tỷ; thuê: triệu/tháng), giá/m² (triệu/m²), diện tích, `n_7d`/`n_30d` tin đăng mới, `posted_max` |

```
python bds_scrape.py                       # mặc định hằng ngày: --geo --master --details 300 --listings 800 (~45–60 phút)
python bds_scrape.py --master --pages 3    # thử nhanh
python bds_scrape.py --details 7000        # seed chi tiết toàn bộ (~2 giờ)
python bds_scrape.py --listings 1500 --kinds ban
```
Ưu tiên: chi tiết → dự án chưa có rồi cũ nhất (quay vòng hết kho ~20 ngày); tin rao → dự án **Đang mở bán / Sắp mở bán** chưa lấy hôm nay trước, rồi dự án cũ nhất. Env: `BDS_STORE`, `BDS_DELAY`. Mỗi lần chạy ghi 1 dòng `store/runs.csv`. Dòng cuối `DONE bds-projects: …` / `ERROR` cho runner.

Seed 17/10/2026: `--geo --master` → `--details 7000` → `--listings 1500` (log `batdongsan-projects\logs\seed_20261017.log`).

## 2. App `bds-tracker` (template Port & Vessel Tracker: `ui_genea.py` copy, `.streamlit\config.toml`, `Chay-app.bat`)
Cấp 1 (viên thuốc): **Tổng quan · Giá & tin rao · Chủ đầu tư · Bản đồ · Thay đổi · Dữ liệu**. Cấp 2 (mọi trang): **Toàn quốc · Tỉnh/thành · Dự án**.
Bộ lọc chung: Loại hình, Trạng thái. Deep-link `?trang=<trang>/<phạm vi>&tinh=<tỉnh>&da=<project_id>`.

| Trang | Toàn quốc | Tỉnh/thành | Dự án |
|---|---|---|---|
| Tổng quan | KPI (dự án, đang/sắp mở bán, đã bàn giao, số căn đang/sắp mở bán, tin rao bán, giá rao/m² trung vị); dự án theo tỉnh; số căn đang/sắp mở bán theo tỉnh; loại hình × trạng thái; bảng dự án có ô tìm | …theo quận/huyện | KPI dự án, giá rao/m² theo ngày (dải P25–P75), số tin bán/thuê, thông tin chi tiết, lịch sử thay đổi |
| Giá & tin rao | giá rao/m² trung vị theo tỉnh (chip Bán/Thuê); giá/m² và số tin theo tuần (6 khu vực lớn); bảng dự án theo tin rao | …theo quận/huyện | (= trang dự án) |
| Chủ đầu tư | top chủ đầu tư theo số dự án / số căn đang-sắp mở bán; bảng; dự án của 1 chủ đầu tư | trong tỉnh | |
| Bản đồ | scatter OSM theo toạ độ (màu trạng thái/loại, cỡ = số căn) | | |
| Thay đổi | số thay đổi theo ngày; đổi trạng thái; dự án mới; nhật ký | | |
| Dữ liệu | độ phủ theo tỉnh, lịch sử chạy, tải CSV | | |

`bdslib.py` chỉ đọc parquet (không gọi mạng); cache theo chữ ký size|mtime của kho (`bl.stamp()`), mở lại app là thấy dữ liệu mới.

## 3. Cách đọc số
- **Tỉnh/quận** theo danh bạ batdongsan (63 tỉnh cũ, trước sáp nhập 2025); thiếu thì lấy breadcrumb trang chi tiết, rồi đuôi địa chỉ.
- **Số căn / diện tích / giá niêm yết** là số ghi trên trang dự án (nhiều dự án trống) — không phải nguồn cung thực tế được cấp phép.
- **Giá/m²** là giá **rao** của 20 tin mới nhất trên trang dự án, không phải giá giao dịch; dự án < 3 tin thì nhiễu. Tin "Thỏa thuận" không có giá.
- **Trạng thái** 4 giá trị của batdongsan: Đang mở bán, Sắp mở bán, Đã bàn giao, Đang cập nhật. Chuỗi thay đổi chỉ có từ ngày seed (17/10/2026) trở đi.
- Tên chủ đầu tư chưa chuẩn hoá (cùng tập đoàn nhiều pháp nhân); `investor_id` (ep) của batdongsan dùng để gộp sau.

## 4. Lịch chạy (đăng ký 17/10/2026)
**Chạy ở LAPTOP** — task Task Scheduler **"BDS AM"** hằng ngày **07:30** (đã đăng ký 17/10/2026, user `User`, lần chạy kế 18/10 07:30):
```
schtasks /Create /F /TN "BDS AM" /SC DAILY /ST 07:30 /TR "C:\Users\User\AppData\Local\Programs\Python\Python312\python.exe D:\bat-dong-san\run_slot.py --slot AM"
```
(dùng đường dẫn python đầy đủ vì Task Scheduler không chắc có `python` trong PATH). Kiểm tra / chạy tay / tắt:
`schtasks /Query /TN "BDS AM" /V /FO LIST` · `schtasks /Run /TN "BDS AM"` · `schtasks /Change /TN "BDS AM" /DISABLE`.
Máy phải bật lúc 07:30 (Task Scheduler → Properties → Settings → "Run task as soon as possible after a scheduled start is missed" nếu hay lỡ).
Kết quả mỗi lần chạy: `status-AM.txt` (`OK | <giờ> | loi:` hoặc `WARN | ... | loi: bds-projects`), `logs\bds_AM_<stamp>.log`,
1 dòng mới trong `batdongsan-projects\store\runs.csv`. Thử nhanh bằng tay (2 trang danh sách, ~1 phút): `set BDS_ARGS=--master --pages 2` rồi `python run_slot.py --slot AM`
(env `BDS_ARGS` = tham số thêm cho `bds_scrape.py`, rỗng = mặc định hằng ngày).

**Vì sao không chạy trên cloud (GitHub Actions, repo Data-System)**: hub đã được đưa lên repo như 3 hub kia (`pack_code.py` chép code vào
`bat-dong-san/`, `data_manifest.py` khai `bat-dong-san/batdongsan-projects/store`, `sync_data.py --hub bat-dong-san`, workflow
`.github/workflows/bds-am.yml`, `requirements.txt` riêng) và chạy thử 17/10/2026 22:19 từ runner GitHub (IP Mỹ) với `--master --pages 2`
(run 39044473983): **8/8 request bị batdongsan.com.vn/Cloudflare chặn** (trả lời nhanh, không phải timeout; 2 lần thử × 171 s,
`runs.csv` ghi `requests=8, http_err=8`, status `WARN | loi: bds-projects`). Vì vậy:
- `bds-am.yml` **không có cron** (dòng `schedule` đã comment); giữ `workflow_dispatch` (Actions → BDS AM → Run workflow → `args` =
  `--master --pages 2`) và push sửa file workflow → tự chạy thử, để thử lại khi có đường đi IP VN (proxy/VPS VN).
- `data_manifest.py`: **laptop là chủ** `store/` (owner=laptop), cloud chỉ kéo Drive về, không đẩy đè; `store/` **không** nằm trong
  `APP_FOLDERS` (app `bds-tracker` đọc thẳng kho gốc `D:\bat-dong-san\batdongsan-projects\store`; kéo Drive về sẽ đè bản cũ lên bản mới).
- Google Drive `gdrive:pipeline-data/bat-dong-san/batdongsan-projects/store` chỉ có **bản seed 17/10/2026** (9,3 MB), không tự cập nhật.
  Sao lưu tay: `rclone copy D:\bat-dong-san\batdongsan-projects\store gdrive:pipeline-data/bat-dong-san/batdongsan-projects/store`.
- Khi cloud chạy được: bật lại cron trong `bds-am.yml`, đổi `owner="cloud"` + thêm lại `APP_FOLDERS` trong `data_manifest.py`,
  tắt task laptop (`schtasks /Change /TN "BDS AM" /DISABLE`), seed lại Drive từ kho laptop trước lần chạy cloud đầu tiên.

## 5. Dữ liệu LỊCH SỬ (khảo sát 17/10/2026)
Kho tự dựng chỉ có lịch sử từ ngày seed (17/10/2026); trên batdongsan.com.vn không có API lịch sử công khai. Những gì có:
| Nguồn | Có gì | Lịch sử | Cấp | Điều kiện |
|---|---|---|---|---|
| batdongsan.com.vn "Lịch sử giá" (widget trên trang tìm kiếm `/ban-can-ho-chung-cu-quan-7`…) | giá/m² theo quý, cao nhất/phổ biến/thấp nhất, % 1 năm, đỉnh | 1 / 2 / 5 năm | quận × loại hình × bán/thuê (không theo dự án) | miễn phí nhưng phải KYC (đăng nhập + OTP điện thoại); API `/Origins/CommonData/GetPricingHistory` bị Cloudflare chặn khi gọi ngoài trình duyệt. Dòng tóm tắt "Giá bán đã tăng x% trong 1 năm qua" và "thấp hơn đỉnh … vào Qx/yyyy" nằm sẵn trong HTML, không cần đăng nhập |
| research.batdongsan.com.vn | 45 báo cáo thị trường PDF (Q2/2018 → T10/2024, hàng tháng/quý), 21 báo cáo tỉnh, 25 phân tích VRES 2018–2024 | 2018–2024 | toàn quốc / HN / HCM / tỉnh, có chỉ số giá & mức độ quan tâm | miễn phí tải PDF (`/images/report/bds/*.pdf`) |
| Biggee.vn | giá đường/phường, giá dự án (5K+ dự án, 34 tỉnh), biến động theo THÁNG, Open API (API giá dự án theo mã, biến động giá theo tháng; thống kê tin đăng) | 5 năm (gói Xem giá) | đường / dự án / quận | Xem giá 300K/tháng; VIP 1 triệu/tháng, 2 triệu/quý, 5 triệu/năm (gói năm mới có API thử + xuất dữ liệu thô); liên hệ 0889441000 để mua API |
| BDS24H.vn | giá TB/m² theo phường, xu hướng, bản đồ nhiệt, Export | 3 năm (Pro) / 3 tháng (free) | tỉnh/quận/phường, 63 tỉnh | Pro 299K/tháng, 3 lượt tra miễn phí/ngày |
| OneHousing (One Mount) | công cụ phân tích thị trường ~1.000 dự án, lịch sử giá theo tháng từ giao dịch thực 10 năm (công bố 2022) | ~10 năm | dự án (HN là chính) | URL công cụ hiện chuyển về trang mua bán → cần hỏi OneHousing/đăng nhập |
| WiGroup (WiChart/WiData/WiFeed API) | số liệu Bộ Xây dựng theo quý: giao dịch thành công, dự án/căn cấp phép, đủ điều kiện bán, NOXH, nghỉ dưỡng | từ Q3/2019 | 3 miền / toàn quốc | trả phí, hỏi giá tuvan@wigroup.vn |
| Savills SPPI, CBRE, JLL, Cushman | chỉ số giá & giá sơ cấp/thứ cấp theo quý, nguồn cung, hấp thụ | SPPI từ 2012 | HN/HCM theo hạng, mẫu ~200 dự án | PDF quý miễn phí (đăng ký), bảng số liệu phải mua qua bộ phận nghiên cứu |
| Global Property Guide | house price index HCMC theo quý (gốc CBRE/JLL/batdongsan) | nhiều năm | thành phố | dataset trả phí (trang chặn bot, xem giá trực tiếp) |
| Mogi.vn giá nhà đất | giá TB theo quận/phường/đường/dự án + biểu đồ, từ 2 triệu tin Mogi + Muaban.net | không ghi rõ | đến dự án | có mục phí thành viên |
| Tổng cục Thống kê RPPI | chỉ số giá nhà ở chính thức, IMF hỗ trợ, mục tiêu mẫu thử 4/2026 | — | thành phố lớn | chưa công bố |
Không có nguồn nào bán lịch sử GIAO DỊCH theo từng dự án toàn quốc dạng dataset; gần nhất là Biggee (tin rao, theo tháng, có API) và OneHousing (giao dịch, ~1.000 dự án).
