# D:\shipping — cụm VẬN TẢI BIỂN / LOGISTICS (gộp 14/09/2026)

```
D:\shipping\
  Run-Shipping.ps1       RUNNER DUY NHẤT: -Slot AM | PM  [-Only vhbs,haian,cvhp,cvhcm,cvhp-vessels,itinerary,alibra,bcti]; status-<Slot>.txt, logs\
  VHBS-ConTex\           giá thuê tàu container New ConTex (vhbs.de) -> vhbs_contex.csv (Update-VhbsContex.ps1)
  BCTI-scraper\          8 chỉ số cước BDI/BCI/BPI/BSI/BHI/BCTI/BDTI/SCFI từ stockq.org (scrape_bcti.py ALL, cần header Referer)
  alibra-scraper\        fetch.py + combine.py (tên cũ "D:\Alibra scraper")
  cangvu-haiphong\       lịch điều động tàu Cảng vụ HP (cvhp_scrape.py) -> data\cvhp_events/calls/terminal_daily/daily.csv, lịch sử từ 2019
                         + vessel_enrich.py: IMO/loại tàu/TEU/hãng cho tàu cả HP & HCM (vessel_master.csv), skill /cvhp-vessels tra tuyến
  cangvu-hcm\            kế hoạch điều động tàu Cảng vụ TP.HCM gồm Cái Mép-Vũng Tàu (cvhcm_scrape.py, berths.csv map mã cầu), lịch sử từ 2019
  cangvu-toanquoc/       các cảng vụ còn lại: pkh_scrape.py (9 nơi, API public-kh), aspx_scrape.py (Quảng Ninh kht1, Nha Trang, Cần Thơ), national_build.py -> national_calls.csv
  port-tracker/          APP Streamlit theo dõi cảng & tàu (Chay-app.bat -> localhost:8766), chỉ đọc dữ liệu cangvu-* + vessel-itinerary
  vessel-itinerary/      lộ trình từng tàu từ calls HP+HCM (vessel_itinerary.py --ship / --all) -> stops, legs, route_pattern, lane_monthly, PNG
  vessel-route-app\      app tra tuyến/khoảng cách (không có lịch)
  (HaiAn)                lịch tàu HAH vẫn ở D:\Database\Logistics\HAH\haian-schedule-daily.ps1 (script ghi data cạnh nó), runner gọi sang
```

| Task | Giờ | Bước |
|---|---|---|
| Shipping AM | 09:00 hằng ngày | vhbs, haian, cvhp, cvhcm, cv-pkh, cv-aspx, cv-national, cvhp-vessels, itinerary; alibra (thứ Hai) |
| Shipping PM | 22:00 hằng ngày | bcti (stockq cập nhật sau giờ London) |

Thay cho 4 task cũ: "VHBS ConTex Daily Pull" 9:00, "HaiAn Schedule Daily" 10:00, "AlibraScraper" T2 8:00, "BCTI-Scraper" 22:00.
Bước lỗi không chặn bước sau; HaiAn tự bắt lỗi trong script nên luôn exit 0 — xem `haian-daily.log` nếu nghi ngờ.

Hướng dẫn tổng: [D:\HUONG-DAN-TOOLS.md](../HUONG-DAN-TOOLS.md)
