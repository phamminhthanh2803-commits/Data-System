# Khảo sát nguồn "tuyến đường quy hoạch dự kiến" & cổng quy hoạch tỉnh (18/10/2026)

Vấn đề: OSM chỉ có tuyến quy hoạch khi cộng đồng tự vẽ (`highway=proposed`): cả nước 669 đoạn / 198 tên sau khi lọc biên giới (Cầu Giẽ – Ninh Bình GĐ2, Chơn Thành – Đức Hoà, Hoà Bình – Mộc Châu, HCM – Long Thành GĐ2, vành đai…), metro quy hoạch HCM tuyến 3/6/7 có, Hà Nội hầu như không. Đường đang xây (`construction`) 7.263 đoạn / ~900 tên khá đủ (Vành đai 3 HCM, Vành đai 4 HN, Châu Đốc – Cần Thơ – Sóc Trăng, Đồng Đăng – Trà Lĩnh…).

## Nguồn chính thức có tuyến dự kiến
| Nguồn | Có gì | Lấy được không |
|---|---|---|
| Tile QH sử dụng đất TP.HCM (Sở QHKT `sqhkt-qlqh.tphcm.gov.vn/api/tiles/bandoso`) | vẽ cả lộ giới đường quy hoạch 1/2000 (ô đất giao thông) | **đã có trong app** (lớp tile + tra cứu thửa trả `LoGioi`) |
| Tile QH phân khu / QH chung Hà Nội (VietPalm) | đường quy hoạch theo đồ án phân khu | **đã có trong app** |
| **Hải Phòng** `quyhoach.haiphong.gov.vn` (eKGIS) | vector tile PBF chính thức: polygon ô quy hoạch (QHC/QHPK/QHCT) với `phanLoai` (Đất giao thông, Đất ở đô thị, cây xanh…), mật độ, tầng cao, hệ số SDĐ, mã hồ sơ; URL `mapserverquyhoach.haiphong.gov.vn/ekmapserver/rest/services/293/VectorTileServer/tile/{z}/{y}/{x}.pbf?apikey=…` (apikey nằm trong `assets/styles/haiphong_qhxd.json`) | giải mã được bằng `mapbox-vector-tile` (đã cài, cần vá parse_value); chưa đưa vào app — làm được ở cấp Dự án (ô 4 km ≈ 9–16 tile z14) |
| Bắc Ninh `quyhoach.bacninh.gov.vn` | cùng nền tảng eKGIS nhưng cấu hình đang trỏ style "Bắc Giang" (404) | bỏ |
| Cổng GIS xây dựng TP.HCM mới `gisxaydung.tphcm.gov.vn` | ArcGIS REST `api-gisxaydung.tphcm.gov.vn/arcm/rest/services/HCM/*` (thửa đất, ranh đồ án QHPK) | directory trả rỗng/401 khi gọi ngoài trình duyệt → chưa khai thác |
| Hệ thống CSDL quốc gia về quy hoạch (Bộ KH&ĐT/Bộ TC, `vplan.mpi.gov.vn`) | theo đề án có WebGIS quy hoạch tỉnh 2021–2030 gồm mạng lưới giao thông | không truy cập được từ mạng này (timeout/DNS) |
| Quy hoạch mạng lưới đường bộ 2021–2030 (QĐ 1454/QĐ-TTg 2021, điều chỉnh QĐ 1088/QĐ-BXD 6/2026, 41–43 tuyến cao tốc ~9.000 km) | danh mục tuyến + điểm đầu/cuối, bản đồ PDF | **không có shapefile công khai**; muốn có lớp vector phải tự số hoá hoặc mua |
| Bình Dương, Đồng Nai, Đà Nẵng, Khánh Hoà, BR-VT, Long An | các tên miền cổng quy hoạch cũ không phân giải DNS (sau sáp nhập tỉnh 2025 nhiều cổng đã gộp/đổi) | cần dò lại theo tỉnh mới |
| Guland / Meey Map / VietPalm (thương mại) | đã số hoá quy hoạch tỉnh + giao thông dự kiến toàn quốc | mua/thoả thuận API (Meey Map chặn tile, VietPalm chỉ HN) |

## Hướng đi
1. Hải Phòng: thêm lớp vector eKGIS ở cấp Dự án (polygon chức năng SDĐ, tô màu, hover mật độ/tầng cao) — việc kỹ thuật rõ, ~1 phiên.
2. Tuyến cao tốc quy hoạch toàn quốc: số hoá "sơ đồ" 41–43 tuyến theo danh mục QĐ 1454/1088 (nối qua huyện/nút giao nêu trong quyết định) → lớp "Cao tốc quy hoạch (sơ đồ, không phải tuyến chính xác)"; hoặc mua lớp số hoá từ nhà cung cấp GIS.
3. Dò lại cổng quy hoạch của các tỉnh mới sáp nhập khi cần tỉnh cụ thể.
