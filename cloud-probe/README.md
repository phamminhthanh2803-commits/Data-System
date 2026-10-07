# Đưa pipeline lên cloud miễn phí – khảo sát & kế hoạch (07/10/2026)

## Hiện trạng đo được
| Mục | Số liệu |
|---|---|
| Lịch chạy | 4 task/ngày: Market AM 10:30, Market PM 18:30, Shipping AM 9:00, Shipping PM 22:00 |
| Thời gian máy chạy | ≈ 1h45/ngày (~55 giờ/tháng). Nặng nhất: tvhistory 41', cvhp-vessels 24', foreign-vci 9', valuation-region 4,5' |
| Dữ liệu | market-data 5,6 GB · shipping 1,9 GB · bctc 11,3 GB (phần lớn là công cụ chạy 1 lần: fs-extractor, fiinprox, pdf-detector) |
| Dữ liệu pipeline hằng ngày thực sự cần | ≈ 3–4 GB (index-fetcher, transmission, nso, shipping, bond-pivot) |
| RAM cần | pandas đọc tv-history.csv 229 MB + sqlite 343 MB → tối thiểu 4 GB, thoải mái 8 GB |
| Phụ thuộc Windows | `win32com` Excel (bước nganh-ck ghi file OneDrive, chart-pack, nganh-bds); popup MessageBox; 2 bước PowerShell (vhbs, haian); Tesseract đường dẫn `C:\Program Files`; 41 dòng đường dẫn `D:\` cứng trong 29 file |
| Thư viện | pandas, pyarrow, duckdb, curl_cffi (giả Chrome qua WAF), vnstock, yfinance, streamlit, pdfplumber, pymupdf, pytesseract – đều có bản Linux/ARM |
| Nguồn có WAF / nhạy IP | sbv.gov.vn, SET (Incapsula), IDX & Bursa (Cloudflare), các cảng vụ *.gov.vn, vsdc.vn, hnx.vn |

## Lựa chọn miễn phí – xếp hạng (cập nhật 07/10/2026 chiều)
**Oracle Cloud Free Tier KHÔNG cho đăng ký từ Việt Nam** (VN không nằm trong danh sách quốc gia được hỗ trợ) → loại. Các VPS "free forever" khác không còn: AWS/Azure/Fly.io chỉ còn credit thời hạn; GCP e2-micro 1 GB RAM quá yếu. Vì vậy chuyển sang mô hình **không cần máy ảo**: máy chạy theo lịch (cloud) + kho dữ liệu (Drive/OneDrive) + app đọc dữ liệu đã đồng bộ ở local.

1. **GitHub Actions (cron)** – khuyến nghị thử trước. Đăng ký tự do từ VN, không cần thẻ. Runner Linux 4 vCPU / 16 GB RAM / 14 GB đĩa, mỗi job tối đa 6 giờ. Hạn mức: 2.000 phút/tháng repo private (ta cần ~3.300 phút/tháng trên laptop, runner 4 vCPU có thể nhanh hơn); repo **public** thì không giới hạn phút → code public, dữ liệu để ngoài repo. Nhược: runner ở Mỹ (nguy cơ gov.vn chặn – phải probe), không có đĩa bền nên mỗi job phải tải master CSV về (rclone từ Google Drive/OneDrive) rồi đẩy lên lại; cron có thể trễ 5–30 phút; repo không có commit 60 ngày thì cron tự tắt.
2. **Modal.com** – 30 USD credit/tháng vĩnh viễn trên gói Starter, 5 cron, Volume lưu dữ liệu bền (không phải tải lên/xuống mỗi lần), chọn được CPU/RAM, Python thuần (bọc `subprocess.run(run_slot.py)` trong 1 hàm). 55 giờ CPU/tháng ≈ 8–10 USD → nằm trong credit. Nhược: cũng là IP Mỹ; chính sách credit có thể đổi.
3. **Kaggle Notebooks (Google)** – có lịch chạy notebook hằng ngày, 4 CPU / 29 GB RAM, internet bật được sau xác minh SĐT; lưu dữ liệu bằng Dataset version. Nhược: giờ chạy chỉ xấp xỉ, mỗi lần chạy phải nạp dataset đầu vào, ghi output rồi tạo version mới qua Kaggle API – vụng, dễ gãy. Chỉ xem là phương án dự phòng.
4. **Nơi lưu dữ liệu**: Google Drive 15 GB hoặc OneDrive (đã dùng cho excel_feed) qua `rclone`; Backblaze B2 10 GB nếu muốn S3 API.
5. **App Streamlit** giữ ở local (chỉ chạy khi mở, đọc dữ liệu đã đồng bộ về, không tốn tài nguyên khi không dùng). Hugging Face Spaces từ 2026 yêu cầu gói trả phí cho Space chạy code → không tính.
6. Nếu probe cho thấy gov.vn chặn IP Mỹ và không muốn giữ bước đó ở local: VPS Việt Nam rẻ (~100–150k VND/tháng) là cách sạch nhất vì có IP VN; không miễn phí nhưng giải quyết tận gốc.

**Kết quả probe từ GitHub Actions (07/10/2026, repo phamminhthanh2803-commits/Data-System, IP Mỹ)**: 31/34 nguồn OK (`probe_github_20261007.txt`). Bị chặn: IDX + Bursa (Cloudflare 403 với IP datacenter) và Cảng vụ TP.HCM (timeout, chặn IP ngoài VN). → **Chốt: GitHub Actions chạy 4 slot; laptop giữ 1 task nhỏ ~3 phút/ngày** gồm cvhcm (+ cvhcm-berthmap thứ Hai), IDX/Bursa trong valuation-region, nganh-ck (Excel COM). Dữ liệu qua Google Drive/OneDrive bằng rclone; cloud là bên ghi duy nhất cho thư mục của nó, laptop là bên ghi duy nhất cho cvhcm + file Excel.

Giờ cron (UTC = VN − 7): Shipping AM 9:00 → `0 2 * * *`; Market AM 10:30 → `30 3 * * *`; Market PM 18:30 → `30 11 * * *`; Shipping PM 22:00 → `0 15 * * *`. Phút/tháng ước ~3.200 trên laptop; repo private chỉ 2.000 → đo thực tế tuần đầu, nếu vượt thì chuyển repo public (sau khi quét secret trong code) hoặc đưa slot nặng (Market PM) sang Modal.

## Đã làm (07/10/2026) – phần chuẩn bị không phụ thuộc nền tảng (mục 2, 3, 4, 6 dưới)
| Mục | Kết quả |
|---|---|
| Đường dẫn cứng | 29 chỗ / 24 file `.py` đã chuyển sang biến môi trường, mặc định giữ nguyên Windows: `MD_ROOT` (D:\market-data), `SHIP_ROOT` (D:\shipping), `BCTC_ROOT` (D:\bctc), `HAH_DIR` (D:\Database\Logistics\HAH), `TESSERACT_CMD` (mặc định `C:\Program Files\Tesseract-OCR\tesseract.exe` nếu có, không thì `tesseract`). Đường dẫn OneDrive `C:\Users\User\...` → `os.path.expanduser("~")`. Chỉ còn `D:\` trong docstring/comment/chuỗi hiển thị. |
| Runner Python | `D:\market-data\runlib.py` (lõi chung) + `D:\market-data\run_slot.py` + `D:\shipping\run_slot.py`: cùng bảng bước, cùng logic When/Retry/Critical/Stale/Match, cùng định dạng `status-<Slot>.txt` và `logs\<hub>_<Slot>_<stamp>.log` (UTF-8 BOM), dọn log giữ 60 file. `--slot AM\|PM --only a,b --dry-run`. Cảnh báo: `notify()` gửi Telegram khi có env `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`, không có env thì Windows popup như cũ, Linux chỉ ghi log WARN. Bước `nganh-ck` đánh dấu `windows_only=True` → Linux bỏ qua + ghi log. 2 file `.ps1` gốc và 4 task Task Scheduler **giữ nguyên**, vẫn chạy hằng ngày. |
| 2 bước PowerShell | `D:\shipping\VHBS-ConTex\vhbs_pull.py` và `D:\Database\Logistics\HAH\haian_pull.py` (đặt cạnh ps1 gốc, ps1 giữ nguyên) – cùng cách merge/dedup, cùng nơi ghi, cùng định dạng CSV (BOM + CRLF; HaiAn quote mọi ô như Export-Csv). Khác ps1: haian_pull exit 1 khi lỗi nghiêm trọng (ps1 exit 0). Bước `alibra` vẫn gọi `run.ps1` trên Windows, trên Linux chạy `fetch.py` rồi `combine.py`. |
| requirements.txt | `D:\market-data\requirements.txt` dùng chung 3 hub, ghim phiên bản từ `_pip-backup\py312-freeze-2026-09-17.txt`, chỉ các gói code thực sự import; `pywin32` để riêng mục Windows; `vnai` ghim 2.4.8. |
| Kiểm chứng | `python run_slot.py --slot PM --only icb-vci,prop-stocks` (market) và `--slot AM --only vhbs,cvhp` (shipping): log/status khớp từng dòng với log ps1 cùng ngày. VHBS: chạy py rồi chạy lại ps1 → CSV **giống nhau từng byte**. HaiAn: chạy ps1 rồi py trên cùng master → master **giống từng byte**; portcalls/voyages cùng số dòng, cùng tập cảng/giờ, chỉ khác thứ tự các cảng trùng mốc giờ (ps1 duyệt Hashtable .NET, py duyệt theo thứ tự chèn) → Seq/Rotation xoay ở 177 dòng portcalls, 66 voyage; chấp nhận. |

Còn lại khi có máy cloud: cron gọi `python run_slot.py --slot AM/PM` với env `MD_ROOT=/home/ubuntu/market-data` (SHIP_ROOT, BCTC_ROOT, HAH_DIR tương tự); `apt install tesseract-ocr tesseract-ocr-vie`; đặt `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`; mục 1, 5, 7 dưới.

## Việc phải làm trước khi chuyển (bất kể nền tảng)
1. Chạy `probe_cloud.py` trên máy cloud, so với `probe_local_baseline.json` → biết nguồn nào bị chặn IP nước ngoài. Nếu gov.vn chặn: dùng Oracle vùng Singapore thường qua; còn chặn thì giữ bước đó chạy local hoặc tunnel qua máy nhà.
2. Bỏ đường dẫn `D:\` cứng → biến môi trường `MD_ROOT` / `SHIP_ROOT` (29 file, 41 dòng).
3. Chuyển Run-Market.ps1 / Run-Shipping.ps1 sang `run_slot.py` (bảng bước giữ nguyên) + cron; popup MessageBox → Telegram bot.
4. vhbs / haian: viết lại bằng Python (chỉ Invoke-WebRequest/RestMethod, ~100 dòng) hoặc cài `pwsh` trên Linux.
5. Bước **nganh-ck** (Excel COM ghi IB&Brokerage_Nganh.xlsx trên OneDrive, 37 s) **giữ ở Windows**: task local nhỏ 18:40 đọc output từ cloud (rclone/OneDrive sync) rồi ghi Excel. chart-pack, nganh-bds cũng vậy (chạy tay).
6. requirements.txt từ `_pip-backup\py312-freeze-2026-09-17.txt`; `apt install tesseract-ocr-vie`.
7. Đồng bộ dữ liệu 2 chiều: cloud → OneDrive/Google Drive bằng `rclone` sau mỗi slot (để máy local và đồng nghiệp vẫn đọc được).
