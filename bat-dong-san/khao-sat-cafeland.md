# Khảo sát cafeland.vn/du-an (17/10/2026) — có đáng thêm làm nguồn thứ 2?

Mục tiêu: xem cafeland có dữ liệu **lịch sử** mà batdongsan.com.vn không có. Kết luận: **không có chuỗi giá lịch sử**, nhưng có vài trường bổ sung đáng lấy để đối chiếu.

## Truy cập
- Không Cloudflare, curl_cffi (chrome124) 200 ngay; 1 request/giây thoải mái.
- Danh sách: `/du-an/<loại>-tai-<tỉnh>/page-N/` (vd `can-ho-chung-cu-tai-ha-noi`), ~15 dự án/trang; HN căn hộ 28 trang ≈ 420 dự án; toàn quốc căn hộ ≈ 100 trang ≈ 1.500–2.500. ID dự án tới ~6.155 → quy mô tương đương batdongsan (6.921).
- Loại: Căn hộ chung cư, Nhà ở xã hội, Khu đô thị, BĐS nghỉ dưỡng, Đất nền dự án, Nhà phố - biệt thự, Khu công nghiệp, Loại hình khác.

## Trang chi tiết (`/du-an/<slug>-<id>.html`)
| Có | Không |
|---|---|
| Mô tả, quy mô (tổng DT, DT xây dựng, DT sàn, mật độ, hệ số SDĐ, số tòa/tầng, số sản phẩm) — **văn bản tự do**, không bảng | Bảng "Số liệu" (19 trường: ngày khởi công, hoàn thành, vốn đầu tư, số căn, giá dự kiến thấp nhất/m², số block, tầng…) có khung nhưng **toàn dấu "-"** ở mọi dự án thử |
| Loại sản phẩm + khoảng diện tích từng loại | Biểu đồ lịch sử giá theo thời gian |
| Pháp lý: các quyết định có số + ngày (QĐ 2796/QĐ-UBND 17/6/2011…) → mốc pháp lý có ngày | AJAX `listurlduaninfodetail` trả 404 |
| Tiến độ có mốc tháng ("Cập nhật tháng 2/2026, đang triển khai hạ tầng") + "Giá bán tham khảo: Từ 100 triệu/m²" | |
| Chủ đầu tư (tên, năm hoạt động, trụ sở, người đại diện) | |
| Dấu thời gian "Cập nhật: 13/03/2026 2:21 PM" | |
| Biểu đồ cột "Giá dự án cùng khu vực": giá dự kiến thấp nhất (triệu/m²) của dự án + 4–5 dự án lân cận (số nằm trong JS Highcharts, lấy được) | |
| Điểm đánh giá 6 tiêu chí (radar) | |
| Toạ độ: map.cafeland.vn/tin-du-an/<slug>.html có lat/lng | |

## "Bảng giá dự án" (`/bang-gia-du-an/`)
- Bảng: Mã số (bản ghi), Loại: Tên dự án, Tình trạng, khoảng m², giá tr/m², link "Xem sản phẩm" (`/bang-gia-du-an/san-pham-<id dự án>/`), "Xem vị trí".
- Mã số bản ghi tới **15.472**, cùng dự án lặp nhiều lần (Vinhomes King Park 4 lần / 300 dòng) → đây là các lần cập nhật giá = lịch sử, **nhưng không có cột ngày** và phân trang chỉ mở ~33 trang × 50 = 1.650 bản ghi mới nhất (ID ≥ ~12.957). Bộ lọc `<loại>-<tỉnh>-<quận>-<tình trạng>-nokey` (loại 10 = căn hộ, tỉnh 1 = HN, 63 = HCM) cũng không lộ bản ghi cũ hơn.
- Trang `san-pham-<id>`: giá theo loại căn (thấp nhất / TB / cao nhất, tỷ) + tin rao đang giao dịch — hiện tại, không ngày.

## Kết luận
- Không có lịch sử giá nhiều năm; chuỗi thời gian vẫn phải **tự tích luỹ** như batdongsan (bảng giá có ID tăng dần → quét hằng ngày là ghép được lịch sử từ nay).
- Đáng thêm như lớp đối chiếu (ít request, ~1 request/dự án): giá tham khảo/m² + giá thấp nhất theo loại căn, mốc tiến độ có tháng, quyết định pháp lý có ngày, ngày cập nhật, chủ đầu tư, toạ độ. Ghép với batdongsan theo tên + tỉnh (như `biggee_api.py --match`).
- Nguồn lịch sử thật vẫn là Biggee (đã chọn) — xem `batdongsan-projects/BIGGEE.md`.
