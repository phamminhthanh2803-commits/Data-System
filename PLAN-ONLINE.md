# Chuyển toàn bộ cấu phần lên online – khảo sát 12/10/2026 (bản nháp, cập nhật theo kết quả probe)

## 1. Kiểm kê cấu phần và nơi chạy hiện tại
| # | Cấu phần | Đang chạy ở | Lịch | Online được chưa | Rào cản |
|---|---|---|---|---|---|
| 1 | Pipeline Market AM/PM, Shipping AM/PM (33 bước) | **GitHub Actions** (ubuntu, 4 workflow cron) + Google Drive (rclone) | 9:00 / 10:30 / 18:30 / 22:00 | **ĐÃ online** – 4 task Windows cũ đã TẮT 12/10 | Shipping AM 12/10 WARN bước `vhbs`, `alibra` (xem log) |
| 2 | Cảng vụ TP.HCM (`cvhcm`, `cvhcm-berthmap`) | Laptop, task "Pipeline Local Cvhcm" 8:30 | hằng ngày | Chưa | chặn IP ngoài VN (probe 07/10 timeout) → cần IP VN |
| 3 | IDX + Bursa (định giá khu vực) | Laptop, task "Pipeline Local Mini" 18:40 (BẬT 12/10) | hằng ngày | Chưa | Cloudflare chặn IP datacenter (403) |
| 4 | `nganh-ck` ghi Excel OneDrive (IB&Brokerage_Nganh.xlsx) | Laptop (Mini 18:40) | hằng ngày | Chưa | Excel COM (win32com) – cần Windows có Excel |
| 5 | `bonds` (bond-pivot, OCR PDF 3,5 GB) | Laptop (Mini thứ Hai) | tuần | Một phần | Drive hết chỗ cho PDF thô; processed 42 MB đã lên Drive; OCR Tesseract chạy được trên Linux |
| 6 | Bộ thu real-time DNSE (`dnse_stream.py`, 10 kết nối WS, 5 s) + SSI 60 s | **GitHub Actions** 2 job (`realtime-sang` 08:25–11:40, `realtime-chieu` 12:50–15:15) → Drive `realtime/<ngày>/` 60 s **+ 13/10: Cloudflare quick tunnel 5 s** (`--serve-port 8787`, `tunnel.json` trên Drive); laptop task "Realtime DNSE" đã TẮT 13/10 | T2–T6 | **ĐÃ online 13/10** (job SANG xanh, đẩy Drive 60 s); kênh 5 s code + test local xong 13/10, chạy thật từ job kế tiếp sau push | 10 kết nối/user → 2 bên không chạy cùng lúc (`local\Tat-realtime-laptop.ps1`); app "live 5 s (cloud)" qua tunnel, rơi về Drive "live 1 phút (cloud)" khi tunnel đứt; quick tunnel không SLA, URL đổi mỗi job |
| 7 | Lớp live-first `data_src.py` (Entrade, VNDirect, CafeF nội bộ) | Trong app (thread nền) | khi mở app + 30 phút | Theo app | nguồn phải mở từ IP nước ngoài (đang probe) |
| 8 | App Market Data (Streamlit, giao diện Genea, ● LIVE) | Laptop (shortcut Desktop, cổng 8765) | khi mở | Chưa | cần host 24/7 đọc được Drive + parquet live; HF Spaces thu phí; Streamlit Cloud ~1 GB RAM |
| 9 | App Port Tracker (Streamlit 8766) | Laptop | khi mở | Chưa | như 8, dữ liệu store/ parquet đã trên Drive |
| 10 | chart-pack, nganh-bds, fs-extractor, pdf-detector… (công cụ chạy tay) | Laptop | tay | Không cần | Excel COM / vnstock riêng |

## 2. Kết quả probe nguồn live từ runner GitHub (12/10/2026, IP Mỹ, 42 nguồn)
- **Vào được**: SSI iBoard snapshot toàn sàn + chart 1 phút, Entrade nến ngày/1 phút, VNDirect dchart + finfo, CafeF giao dịch nội bộ, cổng WebSocket DNSE (`wss://ws-openapi.dnse.com.vn`, trả 400 vì cần upgrade – bình thường), SBV/NSO/HNX/VSDC/Vietcap/cảng vụ còn lại.
- **Không vào được**: IDX + Bursa (Cloudflare 403), Cảng vụ TP.HCM (timeout) – như 07/10; Vietcap `symbols/getList` 404 (đường dẫn đổi, poll_realtime dùng – cần sửa); `openapi.dnse.com.vn/` gốc timeout (chỉ là trang gốc, endpoint REST thật chưa thử – bộ thu chủ yếu dùng WS).
- **Kết luận**: bộ thu DNSE + SSI 60 s và lớp live-first chạy được trên GitHub Actions; chỉ cvhcm, IDX/Bursa (và Excel COM) buộc phải có IP VN / Windows.
- Lỗi Shipping AM 12/10: `vhbs` = chứng chỉ SSL vhbs.de hết hạn (laptop cũng lỗi) → đã vá fallback không verify; `alibra` = tên thư mục `Alibra-scraper` viết hoa, Linux phân biệt → đã sửa run_slot.

## 3. Phương án đích
### A. Miễn phí hoàn toàn (ghép nhiều dịch vụ)
- Lịch & pipeline: GitHub Actions (như hiện nay). Bộ thu DNSE: 2 job/ngày (08:30–11:40, 12:50–15:15), ghi snapshot 5 s lên **Supabase** (Postgres free 500 MB, API không giới hạn) thay vì parquet trên runner; lịch sử nến ngày vẫn Entrade/VNDirect.
- App: **Streamlit Community Cloud** (free, 1 app private, ~1 GB RAM): đọc Drive qua rclone/gdown lúc khởi động + Supabase cho live. Rủi ro: RAM 1 GB với stock_daily 3,5 triệu dòng; app ngủ sau 12 giờ không ai mở.
- Còn lại trên laptop: cvhcm (IP VN), IDX/Bursa, nganh-ck Excel. Không có cách miễn phí cho IP VN.
### B. VPS Việt Nam (~150–250k VND/tháng, 2 vCPU / 2–4 GB)
- Chạy TẤT CẢ: pipeline (không cần GitHub Actions nữa, hoặc giữ song song), bộ thu DNSE liên tục, cvhcm + IDX/Bursa (IP VN – cần thử vì IP datacenter VN vẫn có thể bị Cloudflare chặn), 2 app Streamlit 24/7 sau Cloudflare Tunnel + mật khẩu, bonds OCR.
- Chỉ còn nganh-ck Excel COM ở Windows → thay bằng openpyxl/Graph API hoặc giữ task laptop 1 phút.
### C. Lai (khuyến nghị nếu không muốn chi phí)
- Giữ A cho pipeline + app; laptop giữ 3 việc nhỏ (cvhcm 1 phút sáng, IDX/Bursa + Excel tối, bộ thu DNSE trong giờ) = laptop chỉ bận ~10 phút/ngày + bộ thu nhẹ (1 tiến trình Python).

## 4. Thứ tự chuyển dần
1. (xong 12/10) Tắt 4 task Windows cũ, bật Mini → pipeline chạy hoàn toàn trên cloud.
2. Probe nguồn live từ runner → chốt bộ thu DNSE/SSI chạy được trên GitHub không.
3. (xong 12/10 — code + test local/app; 13/10 job SANG chạy thật, task laptop đã tắt) Bộ thu DNSE lên cloud (2 job) + Drive cho snapshot (parquet 60 s thay Supabase; app laptop kéo Drive, nhãn "live 1 phút (cloud)"). Tắt task laptop sau khi cloud xanh 13/10 (`local\Tat-realtime-laptop.ps1`).
   3b. (xong 13/10 — code + test local; chạy thật từ job kế tiếp) **Live 5 s**: `serve_live.py` HTTP + Cloudflare quick tunnel trong job, `tunnel.json` trên Drive, app kéo 5 s ("live 5 s (cloud)"), Drive 60 s dự phòng; README cloud-deploy mục *Live 5 s qua tunnel*. Secret `RT_TOKEN` tuỳ chọn. UI không mờ khi rerun (CSS `data-stale`).
4. App lên Streamlit Community Cloud (hoặc VPS) – đọc Drive + Supabase.
5. Port Tracker lên cùng host.
6. cvhcm / IDX-Bursa / nganh-ck: VPS VN hoặc giữ laptop.
