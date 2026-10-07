# Port & Vessel Tracker

App Streamlit theo dõi cảng và tàu của 12 cảng vụ hàng hải. **App gọi thẳng trang nguồn của từng cảng vụ** (từ 29/09/2026), phân tích trong bộ nhớ và lưu vào kho riêng `cache\live.sqlite`. App không còn đọc các file `*_events.csv` / `*_calls.csv` do pipeline parse sẵn.

## Cơ chế dữ liệu trực tiếp (`livedata.py`)
| Việc | Cách làm |
|---|---|
| Gọi nguồn | Dùng lại đúng hàm scrape của các tool (`cvhp_scrape`, `cvhcm_scrape`, `pkh_scrape`, `aspx_scrape`) nhưng không qua file: HP `ship_plan.aspx?d=N`, TP.HCM POST ngày, 8 cảng vụ API `public-kh`, Quảng Ninh kht1, Nha Trang, Cần Thơ |
| Kho của app | SQLite `cache\live.sqlite`: bảng `events` (sự kiện), `days` (ngày nào đã kéo, lúc nào), `details` (cảng trước/kế), `vessel_live` (thông số tàu tra trong app) |
| Khi nào kéo lại | Ngày đã qua hơn 2 ngày và đã kéo sau mốc đó = **chốt**, không kéo lại. Ngày gần đây (hôm nay−2 … ngày mai) kéo lại khi bản trong kho cũ hơn TTL (thanh bên, mặc định 30 phút) |
| Khi mở app | Tự làm mới ngày gần đây và lấp khoảng trống nhỏ (≤ 12 ngày mỗi cảng vụ). Khoảng trống lớn hơn chỉ báo, kéo chủ động ở trang **Dữ liệu** |
| Bảng điều độ | Gọi thẳng trang cảng vụ cho đúng ngày đang xem (TTL tối đa 10 phút) |
| Trang Tàu | Nút **Tra thông số tàu trực tuyến** (IMO: BalticShipping/VesselFinder, TEU: Flexport) và **Tra cảng trước / cảng kế** (trang chi tiết chuyến public-kh) |
| Ghép chuyến | Tính trong bộ nhớ. Phần lịch sử (trước đầu tháng trước) tính 1 lần và lưu đĩa; phần đuôi gần đây tính lại mỗi lần kho có dữ liệu mới |
| Chặng, vòng tuyến | Tính trong app từ chuyến vừa ghép, mỗi ngày 1 lần |
| Khởi tạo | Lần chạy đầu, kho được nạp **một lần** từ lịch sử đã có để khỏi kéo lại ~8 năm (khoảng 1 phút). Sau đó mọi cập nhật đi thẳng từ nguồn. Muốn thuần trực tiếp: xoá `cache\live.sqlite`, tắt nạp, rồi kéo theo khoảng ngày ở trang Dữ liệu |

Còn đọc từ file (là bảng tham chiếu/cấu hình, không phải dữ liệu lịch tàu): `vessel_master.csv` (hãng, TEU, tuyến đã tra), `terminals.csv`, `terminals_hcm.csv`, `berth_area_map.csv`, `areas.csv`, `ports_geo.csv`.

## Chạy
Double-click `Chay-app.bat` → http://localhost:8766 (Market Data App ở 8765, không đụng nhau).
Mở thẳng một trang: `http://localhost:8766/?trang=<slug>` với slug = `tong-quan`, `ben-cang`, `hang-tau`, `tau`, `dieu-do`, `canh-bao`, `tuyen`, `du-lieu`.

## Thanh bên (áp dụng cho mọi trang)
Cảng vụ (trống = cả nước) · Chỉ tàu container · Khoảng thời gian · Độ phân giải Tháng/Tuần · Đo lường (Lượt tàu / TEU danh nghĩa / DWT) · Tự kéo từ trang nguồn khi mở · TTL làm mới · nút Kéo lại từ nguồn ngay.
Kỳ cuối chưa trọn (tháng/tuần đang chạy) bị bỏ khỏi biểu đồ để đường không gãy giả.

## Các trang
| Trang | Dùng để |
|---|---|
| Tổng quan | 4 chỉ số 30 ngày (so kỳ trước, cùng kỳ năm trước), chuỗi theo cảng vụ, cột chồng theo bến |
| Bến cảng | Chuỗi + thị phần theo Bến / Nhóm chủ bến / Mã CK (PHP, GMD, VSC, HAH, SNP...); chi tiết 1 bến: hãng ghé nhiều nhất, cỡ tàu bình quân, giờ nằm cảng |
| Hãng tàu | Ma trận hãng × bến 12 tháng; chi tiết 1 hãng: phân bổ theo bến, đội tàu đang khai thác + vòng tuyến |
| Tàu | Thông số tàu, thời gian nằm cảng từng chuyến, lộ trình (điểm dừng) và nút vẽ bản đồ PNG |
| Bảng điều độ | Kế hoạch vào / rời / di chuyển theo ngày, tàu đang ở cảng |
| Cảnh báo | Biến động theo bến, tàu mới xuất hiện, tàu ngừng ghé, tàu đổi bến chính |
| Tuyến | Chặng lớn nhất, chuỗi theo chặng, hãng trên từng chặng, vòng tuyến từng tàu |
| Dữ liệu | Kho của app theo cảng vụ (khoảng ngày, lần kéo gần nhất), kéo bù/kéo lại từ nguồn theo khoảng ngày, độ phủ TEU/hãng, tải dữ liệu |

Mọi bảng có nút tải Excel và CSV.

## Cấu trúc
- `app.py` – giao diện. `livedata.py` – gọi nguồn + kho SQLite + ghép chuyến. `trackerlib.py` – ghép thông tin tàu, lượt cập bến, chặng.
- Lộ trình trang Tàu dùng `D:\shipping\vessel-itinerary\vessel_itinerary.py` (hàm ghép điểm dừng và vẽ bản đồ).
- Task Shipping AM vẫn chạy để phục vụ các tool dòng lệnh (file CSV, vessel_enrich), nhưng app không phụ thuộc vào nó.

## Cách đọc số
- **TEU danh nghĩa** = sức chở của tàu × số lượt ghé. Đây là công suất tàu đưa vào bến, KHÔNG phải sản lượng container xếp dỡ.
- **Lượt cập bến** tách từ cột `berths` của chuyến: một chuyến ghé 2 bến tính 1 lượt cho mỗi bến. Khu neo, bến phao neo chờ không tính.
- **Thị phần** = phần của bến trong tổng lượt cập bến cùng cảng vụ, cùng bộ lọc loại tàu.
- TP.HCM: các bến Cái Mép – Thị Vải chỉ có từ 07–08/2025 → chuỗi tăng bậc do mở rộng phạm vi.
- Hãng khai thác chưa phủ hết; trang Hãng tàu ghi tỷ lệ phủ. Bổ sung bằng skill `/cvhp-vessels`.

## Biểu đồ
Altair, bảng màu 8 sắc cố định đã kiểm định cho người mù màu; màu đi theo thực thể (xếp theo tổng 24 tháng), quá 7 nhóm thì gộp "Khác". Không dùng trục kép. Số theo kiểu Việt Nam.
