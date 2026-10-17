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

## 4. Lịch chạy
Chưa đăng ký Task Scheduler. Đăng ký (PowerShell, 1 lần): `schtasks /create /tn "BDS AM" /sc daily /st 07:30 /tr "python D:\bat-dong-san\run_slot.py --slot AM" /f`.
Đưa lên cloud như 3 hub kia: thêm hub `bat-dong-san` vào `D:\cloud-deploy\pack_code.py` + `data_manifest.py` (chỉ `batdongsan-projects/store` lên Drive, cloud là chủ) + 1 workflow cron.
