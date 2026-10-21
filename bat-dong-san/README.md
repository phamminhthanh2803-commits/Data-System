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
| 4. Báo cáo PDF (lịch sử 2018–2025) | `--reports` | `research.batdongsan.com.vn/ListingReport/Index?type=0|1|2&currentPage=N` (thẻ `.card-content`: tiêu đề, ngày, link PDF) | `store/reports/<thi-truong|tinh|phan-tich>/<tên>.pdf` (chỉ tải file chưa có) + `store/reports/index.csv` (type, tiêu đề, ngày đăng, url, file, size, pages, text_chars, n_images, n_hits) + `store/reports/extracted.csv` (file, trang, kind text/table, dòng có số liệu % / tr/m² / điểm, trích bằng pymupdf) |
| 5. Lịch sử giá khu vực (1 năm, cấp quận) | `--area-history N` (mặc định 400 trang/lần) | trang tìm kiếm cấp quận `/ban-<loại>-<slug-quận>`, `/cho-thue-<loại>-<slug-quận>`; loại = can-ho-chung-cu, nha-rieng, nha-mat-pho, nha-biet-thu-lien-ke, dat-nen-du-an, dat (cho thuê chỉ 4 loại đầu) | `store/area_history/<YYYY-MM>.parquet`: 1 dòng/ngày/quận/loại/bán-thuê: `pct_1y` (% thay đổi giá rao 1 năm, âm = giảm, từ dòng "Giá bán đã tăng x% trong 1 năm qua"), `price_lo/hi` + `price_unit` (khoảng giá tham khảo tr/m² hoặc tr/tháng), `area_lo/hi` (diện tích phổ biến), `n_total` (#count-number), `last_posted`, `raw_text`; `rent_pct/peak_*` chỉ điền khi widget hiện số thật (hiện là text mẫu → trống). Danh bạ slug: `store/area_slugs.csv` (516/710 quận có slug; `--area-slugs` dựng lại) |

```
python bds_scrape.py                       # mặc định hằng ngày: --geo --master --details 300 --listings 800 (~45–60 phút)
python bds_scrape.py --master --pages 3    # thử nhanh
python bds_scrape.py --details 7000        # seed chi tiết toàn bộ (~2 giờ)
python bds_scrape.py --listings 1500 --kinds ban
python bds_scrape.py --reports                  # tải PDF mới ở research.batdongsan + trích số liệu (seed 17/10: ~5 phút)
python bds_scrape.py --area-history 400         # 400 trang quận × loại × bán/thuê (~8–10 phút); --area-history 10000 = quét hết ~5.200 trang
python bds_scrape.py --area-slugs               # dựng lại danh bạ slug quận (sidebar trang toàn quốc → trang tỉnh, ~130 request)
```
Ưu tiên: chi tiết → dự án chưa có rồi cũ nhất (quay vòng hết kho ~20 ngày); tin rao → dự án **Đang mở bán / Sắp mở bán** chưa lấy hôm nay trước, rồi dự án cũ nhất; lịch sử giá khu vực → trang chưa lấy bao giờ (tỉnh lớn trước: HN, HCM, BD, ĐN…) rồi trang cũ nhất, quay vòng hết ~5.200 trang (516 quận × 10 loại/kiểu) trong ~13 ngày với 400 trang/ngày. Mặc định hằng ngày (không cờ) = `--geo --master --details 300 --listings 800 --reports --area-history 400`. Env: `BDS_STORE`, `BDS_DELAY`. Mỗi lần chạy ghi 1 dòng `store/runs.csv`. Dòng cuối `DONE bds-projects: …` / `ERROR` cho runner.

Seed 17/10/2026: `--geo --master` → `--details 7000` → `--listings 1500` (log `batdongsan-projects\logs\seed_20261017.log`).
Seed lịch sử 17/10/2026: `--reports` (91 PDF trong danh mục, 91 tải được, log `logs\reports_20261017.log`) + `--area-history 400 --delay 1.5` (400 dòng, log `logs\area_20261017.log`).

## 2. App `bds-tracker` (template Port & Vessel Tracker: `ui_genea.py` copy, `.streamlit\config.toml`, `Chay-app.bat`)
Cấp 1 (viên thuốc): **Tổng quan · Giá & tin rao · Chủ đầu tư · Bản đồ · Thay đổi · Dữ liệu**. Cấp 2 (mọi trang): **Toàn quốc · Tỉnh/thành · Dự án**.
Bộ lọc chung: Loại hình, Trạng thái. Deep-link `?trang=<trang>/<phạm vi>&tinh=<tỉnh>&da=<project_id>`.

| Trang | Toàn quốc | Tỉnh/thành | Dự án |
|---|---|---|---|
| Tổng quan | KPI (dự án, đang/sắp mở bán, đã bàn giao, số căn đang/sắp mở bán, tin rao bán, giá rao/m² trung vị); dự án theo tỉnh; số căn đang/sắp mở bán theo tỉnh; loại hình × trạng thái; bảng dự án có ô tìm | …theo quận/huyện | KPI dự án, giá rao/m² theo ngày (dải P25–P75), số tin bán/thuê, thông tin chi tiết, lịch sử thay đổi |
| Giá & tin rao | giá rao/m² trung vị theo tỉnh (chip Bán/Thuê); giá/m² và số tin theo tuần (6 khu vực lớn); bảng dự án theo tin rao; **Lịch sử giá khu vực (batdongsan)**: bảng quận × % 1 năm (chip loại hình, toggle Bán/Cho thuê, khoảng giá, số tin, link trang nguồn) | …theo quận/huyện; Lịch sử giá khu vực = cột ngang % 1 năm theo quận + bảng | (= trang dự án) |
| Chủ đầu tư | top chủ đầu tư theo số dự án / số căn đang-sắp mở bán; bảng; dự án của 1 chủ đầu tư | trong tỉnh | |
| Bản đồ | scatter OSM theo toạ độ (màu trạng thái/loại, cỡ = số căn) | | |
| Thay đổi | số thay đổi theo ngày; đổi trạng thái; dự án mới; nhật ký | | |
| Dữ liệu | độ phủ theo tỉnh; **Báo cáo thị trường PDF** (index.csv: ngày, loại, tiêu đề, link mở PDF, số trang, số dòng số liệu trích); lịch sử chạy; tải CSV (gồm lịch sử giá khu vực, danh mục PDF) | | |

`bdslib.py` chỉ đọc parquet (không gọi mạng); cache theo chữ ký size|mtime của kho (`bl.stamp()`), mở lại app là thấy dữ liệu mới.

## 3. Cách đọc số
- **Tỉnh/quận** theo danh bạ batdongsan (63 tỉnh cũ, trước sáp nhập 2025); thiếu thì lấy breadcrumb trang chi tiết, rồi đuôi địa chỉ.
- **Số căn / diện tích / giá niêm yết** là số ghi trên trang dự án (nhiều dự án trống) — không phải nguồn cung thực tế được cấp phép.
- **Giá/m²** là giá **rao** của 20 tin mới nhất trên trang dự án, không phải giá giao dịch; dự án < 3 tin thì nhiễu. Tin "Thỏa thuận" không có giá.
- **Trạng thái** 4 giá trị của batdongsan: Đang mở bán, Sắp mở bán, Đã bàn giao, Đang cập nhật. Chuỗi thay đổi chỉ có từ ngày seed (17/10/2026) trở đi.
- Tên chủ đầu tư chưa chuẩn hoá (cùng tập đoàn nhiều pháp nhân); `investor_id` (ep) của batdongsan dùng để gộp sau.

## 4. Lịch chạy (đăng ký 17/10/2026) — QUYẾT ĐỊNH 18/10/2026: hub này chạy LOCAL, không đưa lên cloud
**20/10/2026:** task "BDS AM" không chạy thật 18–20/10 (Last Result 0x800710E0 = từ chối vì laptop đang dùng PIN + không bù lượt lỡ). Đã sửa: AllowStartIfOnBatteries, DontStopIfGoingOnBatteries, StartWhenAvailable (bù lượt lỡ khi mở máy). PV2 chốt giữ task này (chỉ crawl batdongsan, KHÔNG đụng Biggee).
**20/10/2026 (tối) — bước `biggee` HẰNG THÁNG qua API** (không cào web biggee.vn; thêm theo yêu cầu phiên chính sau khi có key API, quota 1.000 request/ngày):
`Step("AM", "biggee", "batdongsan-projects/biggee_api.py", when=ngày 1–7 hoặc còn file store/biggee/backfill.flag, extra_args=--update --delay 0.5 --budget 900 [+ --refresh-catalog ngày 1–7 tháng 1/4/7/10])`.
Mỗi lần chạy: (1) bảng mã dự án còn thiếu (getCityList → getDistrictList → getProjectList, ghi dần `ma_tinh/ma_quan/ma_du_an.csv`), (2) lịch sử tháng + định giá mọi mã
(bảng mã ∪ bảng giá web ∪ kho) chưa lấy trong tháng, mã chưa thử bao giờ đi trước, 1 request/mã. Chạm 900 request/ngày (đếm ở `store/biggee/quota.csv`, hoặc API trả
"Vượt giới hạn gọi API") → dừng êm exit 0, ngày sau chạy tiếp (flag giữ bước chạy cả ngoài ngày 1–7); hết việc → tự xoá flag. Mã API không có dữ liệu giá ghi
`project_valuation.parquet` api=`nodata`, chỉ thử lại đầu quý. Chạy tay bất kỳ lúc nào: `python run_slot.py --slot AM --only biggee`. Chi tiết: `batdongsan-projects/BIGGEE.md` §8.
Ước lượng quota: bảng mã ~770 request (1 lần + làm mới mỗi quý); lịch sử ~1 request/dự án → ~2–6 ngày đầu tháng tuỳ số mã có dữ liệu (bảng mã API lớn hơn bảng giá web nhiều).
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
- **18/10/2026 PV2 chốt: scraper + app giữ ở laptop (task "BDS AM" 07:30 + `Chay-app.bat` → localhost:8767), không bật cron cloud, không chuyển kho lên Drive làm chủ.**
  Phần đã đưa vào repo Data-System (`bds-am.yml` không cron, `data_manifest.py` owner=laptop) chỉ để đó, không phát triển thêm.

## 5. Dữ liệu LỊCH SỬ (khảo sát 17/10/2026, 2 nguồn miễn phí ĐÃ LẤY tối 17/10)
Kho tự dựng chỉ có lịch sử từ ngày seed (17/10/2026); trên batdongsan.com.vn không có API lịch sử công khai. Đã nối 2 nguồn miễn phí của chính batdongsan vào `bds_scrape.py` (mục 1, lớp 4–5):

**(a) `--reports` – PDF research.batdongsan.com.vn.** 91 PDF trong danh mục (type 0 báo cáo thị trường tháng/quý Q2/2018→T10/2024 + 1 báo cáo BIM 04/2025; type 1 báo cáo tỉnh/vùng 2023–2024; type 2 phân tích chuyên sâu / VRES 2018–2024), 91 tải được về `store/reports/`.
Trích được gì: pymupdf lấy text + bảng (`find_tables`) → `extracted.csv` 16315 dòng có số liệu (%, tr/m², điểm) kèm file + trang. Phần lớn PDF là slide xuất từ PowerPoint nên **tiêu đề slide, nhận định và số liệu ghi dạng text (vd "giá rao bán chung cư HN tăng 12% so với cùng kỳ", "mức độ quan tâm giảm 8%")** trích được; **biểu đồ chỉ số giá / mức độ quan tâm theo tháng là ẢNH** (canvas xuất ra bitmap) nên **không trích được chuỗi số theo tháng**, chỉ còn số in trên slide. 0 file gần như không có text (toàn ảnh / scan). Muốn chuỗi tháng từ biểu đồ phải OCR + digitize ảnh (chưa làm). Thẻ "Báo cáo thị trường PDF" ở trang Dữ liệu của app liệt kê index.csv với link mở PDF.

**(b) `--area-history` – dòng tóm tắt widget "Lịch sử giá" cấp quận.** 400 dòng ngày 17/10 (400 trang đầu, tỉnh lớn trước). Lấy được không cần đăng nhập: `% thay đổi giá rao 1 năm` (có dấu tăng/giảm, class `re__up-trend`/`re__down-trend`), khoảng giá tham khảo thấp–cao (tr/m² bán, tr/tháng thuê), diện tích phổ biến, tổng số tin, ngày cập nhật tin mới nhất. **Không lấy được**: biểu đồ giá theo quý (cao nhất / phổ biến / thấp nhất, 1–2–5 năm) và các dòng "% thuê (Qx–Qy)", "thấp hơn đỉnh … vào Qx/yyyy" — 2 dòng này trong HTML là **text mẫu giống nhau ở mọi trang** ("23% … Q2/2022 - Q2/2023", "6% … đỉnh 8,5 tr/tháng vào Q1/2022"), số thật chỉ đổ về qua API `GetPricingHistory` sau KYC → scraper so với text mẫu, chỉ ghi khi khác (hiện luôn trống). Tích luỹ hằng ngày sẽ thành chuỗi % 1 năm × khoảng giá theo quận (quay vòng ~13 ngày/lượt), đủ để theo dõi xu hướng cấp quận dù không có lịch sử 5 năm.

Các nguồn khác đã khảo sát:
| Nguồn | Có gì | Lịch sử | Cấp | Điều kiện |
|---|---|---|---|---|
| batdongsan.com.vn "Lịch sử giá" (widget trên trang tìm kiếm `/ban-can-ho-chung-cu-quan-7`…) — **đã lấy phần miễn phí (`--area-history`)** | giá/m² theo quý, cao nhất/phổ biến/thấp nhất, % 1 năm, đỉnh | 1 / 2 / 5 năm | quận × loại hình × bán/thuê (không theo dự án) | miễn phí nhưng phải KYC (đăng nhập + OTP điện thoại); API `/Origins/CommonData/GetPricingHistory` bị Cloudflare chặn khi gọi ngoài trình duyệt. Chỉ dòng "Giá bán đã tăng x% trong 1 năm qua" + bảng Thông tin (khoảng giá, diện tích, số tin) là số thật trong HTML; dòng "thấp hơn đỉnh … vào Qx/yyyy" là text mẫu |
| research.batdongsan.com.vn — **đã tải (`--reports`)** | 45 báo cáo thị trường PDF (Q2/2018 → T10/2024, hàng tháng/quý), 21 báo cáo tỉnh, 25 phân tích VRES 2018–2024 | 2018–2024 | toàn quốc / HN / HCM / tỉnh, có chỉ số giá & mức độ quan tâm | miễn phí tải PDF (`/images/report/bds/*.pdf`); biểu đồ là ảnh, chỉ trích được số in dạng text |
| Biggee.vn | giá đường/phường, giá dự án (5K+ dự án, 34 tỉnh), biến động theo THÁNG, Open API (API giá dự án theo mã, biến động giá theo tháng; thống kê tin đăng) | 5 năm (gói Xem giá) | đường / dự án / quận | Xem giá 300K/tháng; VIP 1 triệu/tháng, 2 triệu/quý, 5 triệu/năm (gói năm mới có API thử + xuất dữ liệu thô); liên hệ 0889441000 để mua API |
| BDS24H.vn | giá TB/m² theo phường, xu hướng, bản đồ nhiệt, Export | 3 năm (Pro) / 3 tháng (free) | tỉnh/quận/phường, 63 tỉnh | Pro 299K/tháng, 3 lượt tra miễn phí/ngày |
| OneHousing (One Mount) | công cụ phân tích thị trường ~1.000 dự án, lịch sử giá theo tháng từ giao dịch thực 10 năm (công bố 2022) | ~10 năm | dự án (HN là chính) | URL công cụ hiện chuyển về trang mua bán → cần hỏi OneHousing/đăng nhập |
| WiGroup (WiChart/WiData/WiFeed API) | số liệu Bộ Xây dựng theo quý: giao dịch thành công, dự án/căn cấp phép, đủ điều kiện bán, NOXH, nghỉ dưỡng | từ Q3/2019 | 3 miền / toàn quốc | trả phí, hỏi giá tuvan@wigroup.vn |
| Savills SPPI, CBRE, JLL, Cushman | chỉ số giá & giá sơ cấp/thứ cấp theo quý, nguồn cung, hấp thụ | SPPI từ 2012 | HN/HCM theo hạng, mẫu ~200 dự án | PDF quý miễn phí (đăng ký), bảng số liệu phải mua qua bộ phận nghiên cứu |
| Global Property Guide | house price index HCMC theo quý (gốc CBRE/JLL/batdongsan) | nhiều năm | thành phố | dataset trả phí (trang chặn bot, xem giá trực tiếp) |
| Mogi.vn giá nhà đất | giá TB theo quận/phường/đường/dự án + biểu đồ, từ 2 triệu tin Mogi + Muaban.net | không ghi rõ | đến dự án | có mục phí thành viên |
| Tổng cục Thống kê RPPI | chỉ số giá nhà ở chính thức, IMF hỗ trợ, mục tiêu mẫu thử 4/2026 | — | thành phố lớn | chưa công bố |
Không có nguồn nào bán lịch sử GIAO DỊCH theo từng dự án toàn quốc dạng dataset; gần nhất là Biggee (tin rao, theo tháng, có API) và OneHousing (giao dịch, ~1.000 dự án).
**20/10/2026 — Biggee qua gói thành viên (chưa mua API):** lấy qua tab Biggee đã đăng nhập trong khung trình duyệt của Claude (xem `batdongsan-projects/BIGGEE.md` §5): bảng giá căn hộ toàn quốc (965/1.660 dự án đã nạp) + lịch sử giá tháng từng dự án (`#outDatatrend`, ~09/2021→nay, đồng/m² dự án + quận) → `store/biggee/` (`biggee_web.py --price-list/--history/--match`). Bẫy: kéo nhanh bị reCAPTCHA `bot.php` → chạy 1 luồng nghỉ 4 s; máy nhận `recv_server.py` phải do PV2 tự bật. App: thẻ "Giá Biggee theo tháng" (trang Dự án) + "Bảng giá căn hộ Biggee" (Giá & tin rao). 20/10 chiều: Biggee chặn IP (403.503) sau ~210 trang → DỪNG cào; kho có 212/965 dự án lịch sử. Kéo tiếp bằng TAY: `make_clipper.py` → `biggee_clipper.user.js` (Tampermonkey, ghi trang đang xem + nút Dự án kế tiếp + Xuất JSON, BIGGEE.md §6).

## 6. Lớp đối chiếu cafeland.vn (18/10/2026, `batdongsan-projects/cafeland.py`, gọi qua cờ `--cf-*` của bds_scrape.py)
Khảo sát: `khao-sat-cafeland.md`. Không Cloudflare, dùng chung Client 1 request/giây. Kho `store/cafeland/`:
| Cờ | Nguồn | Ra |
|---|---|---|
| `--cf-list [--cf-types a,b]` | `/du-an/<loại>/page-N/` 8 loại (~14 dự án/trang, ~800 trang) | `projects.parquet`: cf_id, name (tên ngắn) + title, type, status (Đang/Sắp mở bán/Đã bàn giao từ thẻ), investor, address, province, lat/lng (link map trong thẻ); `project_changes.parquet` khi đổi status/tên/CĐT/địa chỉ |
| `--cf-details N` | trang `/du-an/<slug>-<id>.html` (ưu tiên chưa có, rồi cũ nhất) | cột chi tiết: `price_ref_text/lo/hi` (giá tham khảo, triệu/m²; chỉ phần bán, trước "giá thuê"), `progress_text/progress_month`, `legal_json` (câu có số QĐ + ngày) + `legal_last_date`, `scale_json` (bảng Quy mô: tổng DT, DT xây dựng, mật độ, hệ số SDĐ, số tòa/tầng, số sản phẩm) → `area_m2`, `build_area_m2`, `units_text`, `product_json` (loại căn + DT), `comps_json` + `cf_price_min` (biểu đồ "Giá dự án cùng khu vực": giá dự kiến thấp nhất của dự án + lân cận), `rating_json`, `updated_at`, `d_lat/d_lng` |
| `--cf-prices` | `/bang-gia-du-an/page-N/` (50 bản ghi/trang, chỉ mở ~33 trang) | `price_table/<YYYY-MM>.parquet`: record_id (tăng dần theo thời gian), cf_id, name, type_label, status, area_lo/hi, price_lo/hi (triệu/m²), date quét. Chỉ lấy bản ghi mới hơn record_id đã có → chuỗi lịch sử tích luỹ từ #12.957 (18/10/2026) |
| `--cf-match` | kho batdongsan (`projects.parquet` + `geo_projects.parquet`) | `match.csv`: cf_id ↔ project_id theo Jaccard token tên (bỏ từ chung: dự án, khu, nhà ở xã hội, chung cư…) trong cùng tỉnh; tự nhận khi điểm ≥ 0,6 và trùng ≥ 2 từ; cột `ok` sửa tay (1 đúng / 0 sai, giữ qua các lần chạy). `cafeland.load_match()` trả cặp đã nhận |
Mặc định hằng ngày (không cờ) đã gồm `--cf-list --cf-details 200 --cf-prices --cf-match`. Seed 18/10: `--cf-list` rồi `--cf-details 7000`.
Thử 18/10 trên loại Nhà ở xã hội: 303 dự án / 22 trang, 76/303 ghép được với batdongsan (53 điểm ≥ 0,8); bảng giá 1.614 bản ghi (#12.957 → #15.472).
Bẫy: tiêu đề thẻ là "Tên: Dự án … tại Tỉnh" → `short_name()`; giá tham khảo có cả "đồng/m2" (chia 10⁶) và "giá thuê" phía sau; bảng "Số liệu" trên trang chi tiết luôn trống ("-"), không dùng.

## 7. Hạ tầng & quy hoạch trên bản đồ (18/10/2026)
Trang **Bản đồ** (cấp Tỉnh/thành và cấp Dự án) chồng được các lớp sau lên nền CARTO; code: `bds-tracker/infra_layers.py` (vẽ), `bds-tracker/tile_proxy.py` (proxy tile), `batdongsan-projects/infra_fetch.py` (kéo dữ liệu).
| Lớp | Nguồn | Kho | Cách lấy |
|---|---|---|---|
| Hạ tầng OSM: metro/đường sắt đô thị (khai thác, đang xây, quy hoạch), đường sắt chính, cao tốc, quốc lộ, **đường đang xây**, **đường quy hoạch**, sân bay, cầu lớn | OpenStreetMap qua Overpass API (tag railway/highway/aeroway, `construction=*`, `proposed=*`, `opening_date`) | `store/infra/osm_infra.parquet` (62.412 đoạn 18/10/2026, mỗi đoạn toạ độ JSON + khung bao) | `python infra_fetch.py` (chia 7 dải vĩ độ × 2 nhóm, ~10 phút; dải lỗi 504 chạy lại bằng `--bbox nam,tây,bắc,đông`). Tuần 1 lần là đủ |
| QH sử dụng đất TP.HCM (bản đồ số), ranh QH phân khu TP.HCM | Sở Quy hoạch – Kiến trúc TP.HCM, tile `sqhkt-qlqh.tphcm.gov.vn/api/tiles/{bandoso, ranh_qhpk_tphcm_v2}` (cổng thongtinquyhoach.hochiminhcity.gov.vn) | tile cache `store/infra/tile_cache/` | tự tải khi bật lớp |
| QH phân khu / QH chung 2030 / Kế hoạch SDĐ / Đô thị vệ tinh Hà Nội | tile do VietPalm dựng từ bản đồ công bố, dùng trên quyhoach.hanoi.vn (`land.vietpalm.group`, S3) — **nguồn thứ ba**, không phải cổng chính thức | tile cache | tự tải khi bật lớp |
| Ranh 45 phân khu + QH chung + 15 đô thị vệ tinh Hà Nội (tên, diện tích, dân số, số QĐ) | GeoJSON của quyhoach.hanoi.vn | `store/infra/hn_zones.parquet` (WKT) | 1 lần (đã có) |
| **Tra cứu quy hoạch tại điểm TP.HCM**: thửa đất chứa toạ độ dự án → đồ án QHPK 1/2000 (số QĐ, ngày), chức năng SDĐ + % diện tích, lộ giới đường tiếp giáp, điều chỉnh cục bộ | API `a-z/all` của Sở QHKT (POST Lat/Lon, cùng API cổng dùng khi bấm lên bản đồ) | `store/infra/hcm_qh_lookup.parquet` + JSON thô `hcm_raw/` | `python infra_fetch.py --hcm-lookup N` (1,2 s/request; ~1.490 dự án HCM có toạ độ) |
Kỹ thuật: tile của Sở QHKT và VietPalm không có header CORS nên Plotly không tải trực tiếp → `tile_proxy.py` chạy trong tiến trình app (cổng 8768, cache đĩa, gửi Referer phù hợp); đổi cổng bằng env `TILE_PROXY_PORT`. Tile ngoài vùng → PNG trong suốt. OSM chỉ vẽ các đoạn giao với khung phạm vi (toàn quốc: không bật tile, chỉ hạ tầng).
Hạn chế: toạ độ dự án batdongsan lệch vài chục mét → tra cứu thửa có thể rơi vào thửa cạnh; trạng thái OSM phụ thuộc cộng đồng cập nhật; Hà Nội chưa có API tra cứu tại điểm (cổng dùng tile ảnh).

### 7b. Sơ đồ cao tốc quy hoạch (18/10/2026, `batdongsan-projects/expressway_plan.py`)
Không có shapefile công khai cho Quy hoạch mạng lưới đường bộ, nên vẽ **SƠ ĐỒ**: 47 mã tuyến / 87 đoạn (41 tuyến QĐ 1454/QĐ-TTg 2021 + Cà Mau – Đất Mũi, Quảng Ngãi – Kon Tum theo QĐ 12/QĐ-TTg 2025 + 5 tuyến mới theo QĐ 1088/QĐ-BXD 30/6/2026: Vành đai miền núi phía Bắc CT.12, Vành đai trung du phía Bắc CT.43, Hà Tĩnh – Cầu Treo CT.44, Huế – A Lưới CT.45, Phan Thiết – Bảo Lộc – Gia Nghĩa – Bu Prăng CT.46; CT.12 cũ Mậu A – Việt Quang giữ mã "CT.12 (2021)"). Mỗi đoạn = chuỗi waypoint địa danh trong `ROUTES` (toạ độ thị trấn, snap về OSM `places.parquet` khi cách < 25 km với `--refine`). Tình trạng đoạn (đang khai thác / đang xây / quy hoạch) và `horizon` (trước/sau 2030) là tham khảo tại 10/2026, sửa trong `ROUTES` rồi chạy `python expressway_plan.py`.
**20/10/2026 — tuyến NỐI QUA TỪNG NÚT GIAO** (yêu cầu PV2), 2 cách dựng hình, cột `geom_src` ghi cách nào:
- `osm` / `mixed`: đoạn có đường thật trong `osm_infra.parquet` (way motorway / construction / proposed / trunk có `ref` = mã tuyến, hoặc tên tuyến trong `OSM_NAMES`, hoặc ref phụ `opts['refs']` — vd đường Hồ Chí Minh `HCM` cho các đoạn CT.02 nâng cấp từ đường HCM). Dựng đồ thị các way (nối khe hở < 500 m giữa đầu way, gộp mảng liên thông), snap từng waypoint vào nút gần nhất (< 20 km; waypoint giữa tuyến xa hơn thì bỏ qua, vd Cần Thơ với CT.34 đi phía tây thành phố), Dijkstra giữa 2 waypoint kế tiếp → tuyến bám hình OSM, tự đi qua đúng nút giao; làm thưa `simplify 0,0003°` (~30 m, ~1 điểm/km trên đường thẳng). Cặp waypoint không nối được (không có way, hoặc đường OSM dài > 2,2 × chim bay + 15 km = đi vòng tuyến khác) → nối thẳng, `osm_pairs` ghi "số cặp bám OSM / tổng". Kết quả 20/10: 33 đoạn `osm`, 11 `mixed`, 43 `schematic` (CT.01 toàn tuyến Hữu Nghị → Cần Thơ bám OSM trừ 1 chặng Tuy Hòa – Vân Phong). Lưu ý: osm_infra kéo 18/10 **thiếu dải vĩ độ 13,5–16° cho đường bộ** (Overpass lỗi) → 20/10 đã kéo bù `python infra_fetch.py --bbox 13.5,102,16.0,110` (road OK 8.111 phần tử, rail dải này bỏ qua vì 3 endpoint lỗi; osm_infra nay 41.808 đoạn); sau mỗi lần kéo OSM mới nên chạy lại `python expressway_plan.py`.
- `schematic`: đoạn chỉ có trên quy hoạch giữ đường nối địa danh; để nắn qua đúng vị trí nút giao theo QĐ 1454 / điều chỉnh 2025–2026, thêm waypoint dạng tuple `('Nút giao Tân Vạn', lat, lng)` vào danh sách waypoint (tên bắt đầu "Nút giao" → thành nút `kind=manual`).
- **Nút giao** (cột `nodes`, JSON `[{name, cross, lat, lng, pos_km, kind}]`): điểm cắt (shapely STRtree) giữa tuyến và quốc lộ (trunk) / cao tốc / đường đang xây-quy hoạch có `ref` (hoặc tên "Đường cao tốc…/Đường vành đai…") trong OSM, cộng giao cắt giữa 2 tuyến sơ đồ khác mã. Tên nút = ref đường bị cắt ("Nút giao QL.1", "Nút giao CT.40", `HCM` → đường Hồ Chí Minh). Lọc: bỏ way của chính tuyến (carriageway kép), đoạn **đang khai thác bám OSM** chỉ giữ giao cắt có nhánh nối (motorway_link/trunk_link) trong 600 m (cầu vượt không nối ≠ nút giao; đoạn đang xây không đòi vì OSM chưa vẽ nhánh); gộp nút cùng tên trong 3 km (bám OSM) / 8 km (sơ đồ nối thẳng cắt qua lại 1 quốc lộ), nút khác tên trong 400 m gộp tên "QL.1 / ĐT.830". 20/10: 552 nút / 87 đoạn, 6.965 điểm.
Trên app (`infra_layers.add_osm_traces` + `add_node_traces`): lớp "Cao tốc quy hoạch (sơ đồ QĐ 1454/1088)" bật mặc định, texture theo tình trạng, **chấm nhỏ tại mỗi nút giao** (viền trắng + chấm xám đậm, gộp chấm trùng vị trí giữa 2 tuyến), hover chấm = "Nút giao QL.yy · CT.xx × QL.yy · vị trí theo OSM / sơ đồ / nhập tay"; hover đường ghi cách dựng ("hướng tuyến theo OSM" / "một phần theo OSM (k/n chặng)" / "SƠ ĐỒ"), km, làn, địa danh và 10 nút giao đầu. Không legend (quy ước §7c). Đoạn `exp_plan` được làm thưa nhẹ hơn lớp OSM thường (max_pts × 12) để không mất hình. Kiểm tra 1 tuyến: `python expressway_plan.py --only CT.40 --verbose` (in cặp bám OSM, số điểm, km, danh sách nút; không ghi parquet).
Kho: `store/infra/expressway_plan.parquet` (cùng cấu trúc osm_infra, layer `exp_plan`, thêm `geom_src`, `osm_pairs`, `length_km`, `nodes`, `n_nodes`), gazetteer `store/infra/places.parquet` (6.143 điểm OSM place=city/town + ranh hành chính; dải 21,6–23,5° thiếu do Overpass lỗi).

### 7c. Vẽ đường "có texture", không legend (18/10/2026, `infra_layers.STYLES`)
Scattermap chỉ có độ rộng + màu nên mỗi loại đường = vài lớp vẽ chồng: cao tốc = viền nâu 7px + lòng vàng 5px + vạch trắng giữa (nét đứt sinh theo mét); quốc lộ = viền xám + lòng trắng ngà + vạch mảnh; đường sắt/metro = nền đen (metro xanh tím, đang xây cam) + "tà vẹt" trắng xen kẽ; đang xây = nét đứt cam; quy hoạch (OSM proposed và sơ đồ cao tốc) = nét đứt đỏ trên nền mờ; sân bay xanh, cầu xám. Nét đứt sinh bằng `_dash_segments` (on/off theo mét × `scale`: toàn quốc 10, tỉnh ~1, dự án ~0,05 — app tính từ bề rộng khung). Legend tắt (`showlegend=False`); chỉ lớp lòng đường nhận hover (tên, loại, tình trạng; với sơ đồ: "SƠ ĐỒ" + làn + địa danh). Đổi màu/độ rộng/độ dài vạch: sửa `STYLES`.
Chi phí: khung HCM cấp tỉnh ~60k điểm / 18 trace, toàn quốc (sơ đồ + metro + đang xây, max_pts 25) ~117k điểm / 15 trace, cấp dự án ~85k điểm / 31 trace — trình duyệt vẽ 2–5 giây.

## 8. Chỉ số giá dự án TỰ TÍNH — thay Biggee dần (20/10/2026, `batdongsan-projects/price_index.py`)
Quyết định PV2: sau khi kéo xong lịch sử Biggee (và có API) thì chuyển từ thu thập Biggee sang tự làm cùng phương pháp. Phương pháp Biggee đã kiểm chứng (BIGGEE.md §7):
giá dự án tháng = **trung vị (P50) đơn giá rao** của ~16–17 tin so sánh đăng trong ~4 tháng, thấp = P25, cao = P90, không tách loại sản phẩm.
- `bds_scrape.py --listings` nay lưu thêm **tin rao từng dòng** `store/listings/<YYYY-MM>.parquet` (1 dòng/prid/kind: giá, đơn vị, DT, tr/m², số PN, ngày đăng, first_seen, date) ngoài `listing_stats` tổng hợp.
- `price_index.py [--window 120] [--compare-biggee]` → `store/price_index.parquet` (project_id × tháng: n, p25, p50, p90, mean, area_med, p50_b1..b4 theo số PN) + `price_index_district.parquet` (gộp tin mọi dự án trong quận).
  Mẫu = tin BÁN có đơn giá, posted (thiếu thì first_seen) trong 120 ngày trước cuối tháng, mỗi prid 1 lần; lọc ngoài [0,5×; 2×] trung vị thô rồi |x−med| > 3,5 MAD; ≥ 5 mẫu.
- App trang Dự án: thẻ "Giá dự án theo tháng" vẽ chung Biggee (từ 2018) + Tự tính P50 (từ 10/2026, toggle dải P25–P90). Giai đoạn chuyển tiếp: 2 chuỗi chạy song song để đối chiếu (`--compare-biggee` → `store/biggee/doi_chieu_price_index.csv`), khi khớp ổn định thì chuỗi tự tính là chính, Biggee chỉ còn lịch sử.
- Hằng ngày: thêm bước `price-index` sau `bds-projects` trong run_slot.py (xem mục 4). Tin rao của ta mới có từ 17/10/2026 nên tháng 10–11/2026 còn ít mẫu (n nhỏ) — chỉ số ổn định sau ~4 tháng tích luỹ.

**20/10 (tối) — giá tham chiếu cho MỌI dự án + lịch sử bắt buộc (PV2):** `bdslib.add_price_ref` thêm cột *Giá tham chiếu / Thấp / Cao / Nguồn giá* (tr/m²) vào mọi bảng dự án theo thứ tự ưu tiên: Biggee dự án (TB, P25, P90) → tin rao batdongsan (trung vị, P25, P75) → TB quận (trung vị giá TB các dự án căn hộ Biggee cùng tỉnh+quận; thấp/cao = P25/P90) → TB tỉnh → TB toàn quốc; cột Nguồn giá ghi rõ bậc nào (dự án không phải căn hộ vẫn nhận TB quận căn hộ). Thẻ "Giá dự án theo tháng" ở trang Dự án luôn có chuỗi: không có chuỗi riêng thì vẽ chuỗi quận (`bdslib.area_history`: TB quận = chuỗi quận của Biggee, Thấp/Cao = P25/P90 các dự án trong quận theo tháng), thiếu quận thì tỉnh, rồi toàn quốc; nhãn ghi rõ khu vực và số dự án.

**20/10 (tối) — quy ước biểu đồ + trang Chủ đầu tư (PV2):** mọi biểu đồ TRUNG BÌNH phải có DẢI CAO–THẤP MỜ đi kèm → helper `app.fig_mid_band(items)` (đường TB + band fill mờ cùng màu, legend 1 mục "Thấp–Cao …"): dùng ở thẻ "Giá dự án theo tháng" (dải = tự tính P25–P90 khi có, nếu không là P25–P90 các dự án trong quận/tỉnh theo tháng; bỏ toggle Dải), "Giá rao bán/m² theo tuần" (dải = trung vị P25/P75 các dự án trong khu vực), "Giá rao/m² trung vị theo tỉnh/quận" (fig_range_dots: chấm trung vị + thanh P25–P75 mờ), và trang Chủ đầu tư. Trang Chủ đầu tư bố trí lại: chọn CĐT lên đầu → KPI (dự án, số căn, giá TC trung vị + thấp/cao, số dự án có giá riêng) → "Giá từng dự án của CĐT" (`fig_range_dots`: chấm = giá tham chiếu, thanh mờ = thấp–cao, hover ghi nguồn) + loại hình×trạng thái → "Lịch sử giá các dự án của CĐT" (đường mảnh 8 dự án nhiều căn nhất + trung vị CĐT đậm với dải P25–P90 các dự án; không có chuỗi riêng → chuỗi tỉnh/quận nơi CĐT nhiều dự án) → bảng dự án; tổng quan CĐT (2 hbar + bảng có thêm giá TC trung vị, thấp nhất, cao nhất) xuống dưới.

**20/10 (tối) — hạ tầng tông tối + bản đồ trong trang Dự án (PV2):** `infra_layers.STYLES` đổi toàn bộ sang tông tối (cao tốc lòng nâu sẫm viền đen vạch xám; quốc lộ xám xanh đậm; đang xây nét đứt nâu viền đen; quy hoạch nét đứt tím than; metro/đường sắt nền đen–tà vẹt xám; nút giao chấm đen viền xám nhạt) để chấm dự án (màu) nổi trên nền hạ tầng. Trang Dự án (cấp dự án ở mọi tab trừ Bản đồ) nay gọi `page_project_map` ở cuối: bản đồ 4 km quanh dự án + lớp hạ tầng/quy hoạch + tra cứu QH TP.HCM. Cỡ bubble dự án theo số căn như cũ (sqrt(số căn)+3, size_max 18) ở cả bản đồ chính (mọi mức Thưa/Vừa/Đủ) và bản đồ dự án (dự án đang xem to nhất, màu đỏ).

**21/10/2026:** sửa lỗi chọn kỳ 1Y/3Y ở thẻ lịch sử giá (StreamlitValueBelowMinError): `ui.DATA_MIN` toàn app nay = 01/01/2018 (trước là 01/10/2026 và chỉ nới tạm trong thẻ, nhưng callback kỳ chạy trước khi nới). Biggee API: quota ngày chưa reset lúc 09:55 (vẫn "Vượt giới hạn") → vòng thăm dò `--ping` mỗi 20 phút rồi tự chạy `--update --budget 900` (log `logs/biggee_update_20261021.log`); bước `biggee` trong task BDS AM cũng tự chạy khi còn `backfill.flag`.
