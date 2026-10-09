# Đề xuất luồng dữ liệu real-time / gần real-time cho TTCK Việt Nam

Khảo sát 07/10/2026, 17:30–18:10 (ngoài giờ giao dịch). Thư mục: `D:\market-data\realtime-lab\`
(`poll_realtime.py` script mẫu, `samples\` mẫu JSON thô từng nguồn, `data\2026-10-07\` parquet do script sinh).
Không sửa pipeline hiện tại, không đăng ký tài khoản.

## 1. Hiện trạng và trường có ý nghĩa real-time

| Pipeline hiện tại | Lấy gì | Từ đâu | Tần suất |
|---|---|---|---|
| index-fetcher/fetch_indices.py | OHLCV + GTGD chỉ số VN | Vietcap `gap-chart` ONE_DAY | 1 lần/ngày |
| index-fetcher/fetch_flows.py | khối ngoại, tự doanh 4 rổ | VNDirect finfo `foreigns`, `proprietary_trading` | 1 lần/ngày (số cả phiên) |
| index-fetcher/tv_history.py | giá/KL daily ~1.600 mã | TradingView websocket (tvdatafeed) | 1 lần/ngày, 41 phút |
| market-valuation | P/E, P/B… thị trường | VNDirect finfo `ratios` | 1 lần/ngày |
| app Streamlit | đọc CSV/parquet offline | — | khi mở |

Trường chỉ có giá trị nếu lấy trong phiên: **giá/KL khớp và GTGD luỹ kế**, **khối ngoại mua/bán trong phiên** (từng mã và tổng sàn),
**độ rộng thị trường** (tăng/giảm/trần/sàn), **basis VN30F1M − VN30**, bid/ask bước 1. Định giá và tự doanh không cần real-time
(tự doanh chỉ có sau phiên).

## 2. Nguồn real-time đã khảo sát

Đã chạy thử trực tiếp từ laptop (IP VN) lúc 17:37–18:05; vì ngoài giờ nên chỉ kiểm chứng được: kết nối, cấu trúc dữ liệu,
dữ liệu phiên 07/10 có đủ đến 14:45/15:05, tốc độ phản hồi. **Độ trễ thật trong phiên chưa đo** (cần chạy lại 9:00–15:00).

| # | Nguồn | Dữ liệu | Cách lấy | Tài khoản | Kết quả thử | IP nước ngoài | Rủi ro |
|---|---|---|---|---|---|---|---|
| 1 | **VNDirect dchart** `dchart-api.vndirect.com.vn/dchart/history` | nến 1 phút chỉ số (VNINDEX, VN30, HNX, HNX30, UPCOM, VNMID, VNSML, VN100), phái sinh VN30F1M/F2M, từng mã | REST GET, JSON t/o/h/l/c/v | Không | 0,8 s/lần; 15 lần liên tiếp đều 200; đủ nến đến 15:05 | chưa probe host này (api-finfo cùng hãng OK từ GitHub Actions) | endpoint không chính thức, có thể đổi |
| 1b | VNDirect `dchart-socket.vndirect.com.vn` | stream nến theo mã | socket.io, emit `addsymbol` | Không | kết nối được, chưa thấy dữ liệu (ngoài giờ) | chưa test | như trên |
| 2 | **SSI iBoard** `iboard-query.ssi.com.vn/stock/exchange/{hose,hnx,upcom}` | **toàn sàn 1 request** (409+299+817 mã): giá khớp, thay đổi, KL/GTGD luỹ kế, **khối ngoại mua/bán trong phiên**, room, bid/ask 3 bước, phiên (PRE/LO/ATC) | REST GET, JSON | Không | 1–1,3 s/sàn, 5 lần liên tiếp OK | chưa test; trang web có Cloudflare challenge, API chưa rõ | Cloudflare có thể chặn IP datacenter |
| 2b | SSI `iboard-api.ssi.com.vn/statistics/charts/history` | nến 1 phút (VNINDEX, HNXINDEX, VN30F1M; UPCOM chưa có) | REST GET | Không | 1 s, 15 lần OK | chưa test | như trên |
| 2c | SSI MQTT `wss://price-streaming.ssi.com.vn/mqtt` | stream giá (protobuf) | MQTT over WSS, user/pass công khai của web `mqtt-ssi` | Không | **kết nối + đăng nhập OK**, nhưng subscribe wildcard `#` bị từ chối → phải biết đúng tên topic (bắt bằng DevTools tab WS khi mở iboard.ssi.com.vn trong phiên) | chưa test | phụ thuộc web SSI, protobuf chưa có .proto |
| 3 | **Vietcap trading** `trading.vietcap.com.vn/api/price/symbols/getList` | bảng giá theo danh sách mã: giá khớp, KL/GTGD luỹ kế, **khối ngoại mua/bán + room**, ATO/ATC, bid/ask 3 bước | REST POST (≤300 mã/lần) | Không | 0,7 s; đúng trường pipeline đang dùng (vnstock `price_board` bọc endpoint này) | **OK** (probe GitHub Actions 07/10) | gap-chart 1 phút chậm 7–20 s/lần, 1 lần timeout |
| 3b | Vietcap `api/market-watch/LEData/getAll` | **từng lệnh khớp** (tick) có KL, giá, luỹ kế | REST POST | Không | 0,8 s/50 tick | OK | — |
| 3c | Vietcap socket.io `wss://trading.vietcap.com.vn` path `/ws/market-watch/socket.io` | stream bảng giá/tick (protobuf, file `/protos/price.proto` công khai có IndexMessage: tăng/giảm/trần/sàn, MatchPriceMessage: khối ngoại, room…) | socket.io v4, không cần token khi chưa đăng nhập | Không | **kết nối OK không auth**; tên event subscribe chưa bắt được (ngoài giờ không có dữ liệu để quan sát) | OK (cùng host) | — |
| 4 | **Entrade (DNSE) công khai** `services.entrade.com.vn/chart-api/v2/ohlcs/{index,stock,derivative}` | nến 1 phút chỉ số (VNINDEX, VN30, HNX, UPCOM), từng mã, phái sinh | REST GET | Không | 0,7 s, 15 lần OK; không có VNMID/VNSML | chưa test | — |
| 5 | **DNSE Open API V2** (LightSpeed) `openapi.dnse.com.vn` + `wss://ws-openapi.dnse.com.vn/v1/stream` | tick khớp (`tick.G1.json`), bid/ask, nến `ohlc.1m.json`, giá dự kiến, trần/sàn; REST market/accounts/orders | WebSocket JSON/msgpack, auth HMAC-SHA256 bằng API key/secret; SDK chính thức `pip install dnse` (0.5.0) | **Cần TK DNSE**, đăng ký tại developers.dnse.com.vn (OTP, secret hiện 1 lần) | kết nối WS OK từ VN, server trả `welcome` rồi `NOT_AUTHENTICATED` khi subscribe không key → **bắt buộc có API key**, chưa test dữ liệu | **không thấy yêu cầu IP cố định** trong tài liệu → dùng được từ VPS/cloud | phí chưa ghi rõ trong tài liệu (hỏi DNSE); rate limit có header 429; chỉ số (MI) có ở LightSpeed V1 MQTT `datafeed-lts.dnse.com.vn` (JWT 8 giờ), V2 chưa rõ |
| 6 | **SSI FastConnect Data** `fc-data.ssi.com.vn/v2.0/Market` + streaming `fc-datahub.ssi.com.vn` (SignalR) | kênh X-QUOTE, X-TRADE, R (room ngoại), MI (chỉ số + tăng/giảm), B (OHLC), F, OL; REST DailyOhlc/IntradayOhlc/DailyIndex | SDK Python chính thức | **Cần TK SSI** + đăng ký API trên iBoard, **phải đăng ký IP cố định** | không test | **không dùng được trên GitHub Actions/Modal** (IP đổi); chỉ hợp VPS VN/laptop IP tĩnh | phí: tài liệu không ghi |
| 7 | vnstock 4.0.8 / vnai 2.6 | `Trading.price_board`, `Quote.intraday` | bọc REST Vietcap (3, 3b) | Không | như (3); **không có websocket, không realtime riêng** | như (3) | gói tự ghi file agent (đã tắt) |
| 8 | TradingView (tvdatafeed, scanner) | giá chỉ số/mã | websocket không login | Không | scanner trả `update_mode = delayed_streaming_900` → **dữ liệu VN trễ 15 phút** | OK | chỉ dùng cho chỉ số quốc tế |
| — | VNDirect `price-api.vndirect.com.vn/stocks/snapshot` | bảng giá | REST | Không | trả chuỗi mã hoá riêng, bỏ | — | — |

**Kết luận nguồn:** không cần tài khoản thì **tổ hợp (1) + (2) [dự phòng (3)+(4)]** đủ cho mức 1 phút: nến chỉ số/phái sinh từ VNDirect,
toàn thị trường + khối ngoại trong phiên từ SSI iBoard (3 request), Vietcap làm dự phòng vì đã chắc chạy được từ IP Mỹ.
Cần giây thì **DNSE Open API V2** sạch nhất (chính thức, có SDK, không ràng IP); SSI FastConnect chỉ khi có IP tĩnh.

### 2.1 Chưa kiểm chứng (phải làm trước khi chốt)
1. Chạy `python poll_realtime.py --force --interval 60` trong 1 phiên 9:00–15:00 để đo độ trễ thật (so `last_update_ms` của SSI
   và giờ nến cuối với đồng hồ) và xem có bị chặn sau vài trăm request không.
2. Probe IP Mỹ cho `dchart-api.vndirect.com.vn`, `iboard-query.ssi.com.vn`, `services.entrade.com.vn`: thêm 3 dòng vào
   `cloud-probe/probe_cloud.py` rồi chạy workflow probe trên GitHub Actions (chưa làm vì phải push lên repo).
3. Nếu muốn stream không tài khoản: bắt tên topic SSI MQTT / event Vietcap socket.io bằng DevTools trong phiên.
4. DNSE: phí dịch vụ Open API, V2 có kênh chỉ số không, rate limit cụ thể (hỏi DNSE / Discord cộng đồng).

## 3. Kiến trúc đề xuất 2 mức

### Mức A — gần real-time 1–5 phút (khuyến nghị bắt đầu)
Job chạy 8:55–15:05 ngày giao dịch, mỗi 60 s poll REST (script `poll_realtime.py` đã chạy được), ghi parquet theo ngày:
`index_1m` (nến), `stocks_latest` + `stocks_HHMM` (bảng giá), `market_summary` (độ rộng, GTGD, khối ngoại ròng từng sàn, basis).
Mỗi 5 phút `rclone copy` thư mục ngày lên Google Drive; laptop đã sync Drive nên app Streamlit đọc file như hiện nay
(thêm `st_autorefresh` 60 s). Dữ liệu cuối ngày (15:05) giữ lại làm lịch sử intraday.

| Nơi chạy | Phút/tháng (22 phiên × 370 phút) | Chi phí | Ghi chú |
|---|---|---|---|
| GitHub Actions, repo **private** | ≈ 8.100 phút | vượt hạn 2.000 phút | **không khả thi** nếu giữ private |
| GitHub Actions, repo **public** | không giới hạn | 0 đ | code public, dữ liệu ngoài repo (Drive); job tối đa 6 giờ → tách 2 job sáng 8:55–11:35 và chiều 12:55–15:05; cron có thể trễ 5–30 phút nên đặt sớm 15 phút; IP Mỹ cần probe mục 2.1 |
| GitHub Actions cron 5 phút, mỗi lần chạy ~1 phút (A-lite) | ≈ 1.600 phút | 0 đ, vừa hạn private | cron GitHub trễ thất thường 5–30 phút → không tin cậy cho dữ liệu phút |
| **Modal** (1 hàm chạy liên tục 6 giờ, 0,125 vCPU/0,5 GB) | ≈ 136 giờ container | ≈ 5–8 USD, trong 30 USD credit | 1 cron 8:55, timeout 6,2 giờ; Volume lưu parquet, rclone lên Drive cuối ngày; IP Mỹ |
| Laptop (Task Scheduler 8:55, như task Cvhcm) | — | 0 đ | phải bật máy trong phiên; đơn giản nhất để thử 1 tuần |

Nhược điểm mức A: độ trễ 1–2 phút (poll 60 s + sync Drive); không có tick/bid-ask thay đổi liên tục; phụ thuộc endpoint web
không chính thức (có thể đổi, ảnh hưởng ít vì có 3 nguồn thay thế); ~1.100 request/phiên lên SSI + 10 request/phút lên VNDirect.

### Mức B — real-time giây
Tiến trình chạy liên tục (VPS VN ~100–150k/tháng, hoặc laptop) nghe WebSocket, ghi DuckDB (`ticks`, `quotes`, `bars_1m`,
`market_state`), app Streamlit đọc DuckDB với auto-refresh 2–5 s (hoặc tách app nhỏ chỉ cho tab real-time).
Thứ tự ưu tiên nguồn:
1. **DNSE Open API V2** (cần TK DNSE): SDK `dnse`, `subscribe_trades/quotes/ohlc` cho danh sách mã VN30 + rổ theo dõi, JSON rõ ràng,
   reconnect sẵn. Thiếu: kênh chỉ số (dùng V1 MQTT `plaintext/quotes/index/MI/{marketID}` hoặc poll VNDirect 10 s).
2. Không tài khoản: Vietcap socket.io (protobuf đã có `.proto`, IndexMessage có cả tăng/giảm/trần/sàn) hoặc SSI MQTT (cần topic).
3. SSI FastConnect (cần TK SSI + IP tĩnh VPS): kênh đầy đủ nhất (MI, R, X-TRADE), chính thức, SDK Python.

Nhược điểm mức B: phải trực tiến trình 24/5 (reconnect, giám sát, Telegram cảnh báo); VPS mất phí; laptop phải bật và ổn định
mạng; nguồn không chính thức có thể đổi protobuf; cần thêm TK DNSE/SSI với mức chính thức; DuckDB ghi liên tục cần tách
writer/reader (app chỉ đọc bản sao hoặc dùng chế độ read-only).

### Lộ trình gợi ý
1. Tuần 1: chạy `poll_realtime.py` trên laptop (task 8:55) 3–5 phiên, đo độ trễ, thêm tab "Trong phiên" vào app đọc parquet.
2. Tuần 2: probe IP Mỹ; nếu OK chuyển job sang Modal (hoặc GitHub public); nếu SSI bị chặn thì dùng Vietcap getList làm nguồn chính
   (danh sách mã lấy từ `tv_symbols.txt`).
3. Chỉ khi thật sự cần giây: mở TK DNSE, lấy API key, thử SDK trên laptop 1 phiên rồi mới thuê VPS.

## 4. Ba câu hỏi PV2 cần chốt
1. **Dữ liệu nào** cần trong phiên: chỉ số + phái sinh + khối ngoại tổng sàn (đủ với mức A) hay cả tick/bid-ask từng mã (mức B)?
2. **Độ trễ chấp nhận**: 1–2 phút (A, miễn phí, chạy cloud) hay vài giây (B, VPS/laptop chạy liên tục + tài khoản DNSE)?
3. **Ngân sách và tài khoản**: 0 đ (GitHub public/Modal credit), hay ~150k/tháng VPS; có mở TK DNSE (và/hoặc SSI) để dùng API chính thức không?

## 5. Quyết định 08/10/2026: dùng tài khoản DNSE → bộ thu `dnse_stream.py`

PV2 chốt dùng DNSE. Đã viết sẵn bộ thu mức B (giây) `dnse_stream.py`; phần DNSE chỉ chạy khi có API key, phần còn lại đã test.

**PV2 tự làm (Claude không đăng ký, không nhập key thay):**
1. Có tài khoản chứng khoán DNSE (mở online tại entradex.dnse.com.vn nếu chưa có).
2. Vào developers.dnse.com.vn → Đăng ký OpenAPI → đăng nhập bằng tài khoản giao dịch → chọn xác thực SmartOTP (app DNSE)
   hoặc Email OTP → hệ thống hiện **API Key + API Secret (Secret chỉ hiện 1 lần, lưu ngay)**.
3. Copy `dnse.env.example` thành `dnse.env` cùng thư mục, điền 2 dòng `DNSE_API_KEY=`, `DNSE_API_SECRET=`. File này đã nằm trong
   `.gitignore`, không dán key vào chat.
4. Chạy `python dnse_stream.py --check` → in "XAC THUC OK" là xong. Hỏi DNSE (Discord/Zalo) về phí và rate limit Open API.

**08/10 tối, PV2 chốt "tất cả chuyển về DNSE"** → viết lại `dnse_stream.py` hoàn toàn bằng DNSE (bỏ VNDirect/SSI), client WebSocket
tự viết theo đúng giao thức (gói pip `dnse` 0.5.0 chỉ còn dùng để ký HMAC cho REST; SDK đúng là github `dnse-tech/openapi-sdk`).

| Dữ liệu PV2 cần | Kênh DNSE | Chu kỳ | Bảng DuckDB `data/realtime.duckdb` | Thử 08/10 17:17 (ngoài giờ) |
|---|---|---|---|---|
| Điểm 10 chỉ số (VNINDEX, VN30, HNX, HNX30, UPCOM, VN100, VNXALLSHARE, VNMITECH, VN50GROWTH, VNDIVIDEND) + **độ rộng** (tăng/giảm/đứng/trần/sàn, KL theo chiều) + GTGD khớp/thoả thuận | `market_index.{INDEX}.json` | 5 s | `market_index` (lịch sử) | đăng ký active |
| VN30 dự kiến (ATO/ATC) | `estimated_market_index.VN30.json` | khi đổi | `estimated_index` | active |
| **Toàn bộ mã trong rổ** VNINDEX/HNX/VN30/HNX30/VN100: giá, % đổi, GTGD, KL, tỷ trọng, điểm ảnh hưởng | `market_index_influence.{INDEX}.1.json` | khi đổi | `influence` (bản mới nhất theo mã) | active |
| Tick khớp lệnh (+ mua/bán chủ động, giá TB), bid/ask 3 bước, khối ngoại mua/bán + room, giá dự khớp ATO/ATC, nến 1 phút | `tick_extra.G1`, `top_price.G1`, `foreign.G1`, `expected_price.G1`, `ohlc.1`, `ohlc_closed.1` cho mã trong `dnse_symbols.txt` | liên tục | `ticks`, `quotes`, `foreign_flow`, `expected`, `bars_1m` | active, 3 kết nối |
| Nến 1 phút chỉ số + VN30F1M/F2M | `ohlc.1`, `ohlc_closed.1` + **backfill REST** `GET /price/ohlc` khi khởi động | liên tục | `bars_1m` | REST trả 9.049 nến (10 chỉ số, 2 phái sinh, 30 mã, phiên 08/10) |
| Phiên (ATO/LO/ATC) | `session.{STO,STX,UPX,FIO}.G1.json` | khi đổi | `sessions` | wildcard `*` bị cấm tier thường → dùng G1 |

Giới hạn server: 10 kết nối/user, 200 stream/kết nối (auth báo 100), 100 thông điệp/giây, kết nối tối đa 8 giờ (script tự nối lại sau 7,5 giờ).
Bộ thu chia 15 mã/kết nối (6 kênh × 15 = 90 stream): VN30 + F1M = 4 kết nối (market + 3 watch). Mở rộng: thêm mã vào
`dnse_symbols.txt` (tối đa ~9 kết nối × 15 = 135 mã) hoặc `--foreign-universe VN100` để lấy khối ngoại cả rổ VN100 (thêm 2 kết nối).
**Khối ngoại toàn sàn**: DNSE chỉ có theo mã, không có tổng sàn; tổng VN30/VN100 cộng từ `foreign_flow`. Nếu cần đúng tổng 3 sàn thì giữ
thêm poller SSI (`poll_realtime.py`) hoặc hỏi DNSE kênh tổng.

Xuất parquet mỗi 5 s vào `data/<ngày>/` cho app đọc (app **không** mở DuckDB đang ghi): `index_latest` (điểm + độ rộng + basis F1M),
`rt_latest` (giá/bid/ask/khối ngoại từng mã), `index_1m`, `rt_bars_1m`, `market_summary` (lịch sử 5 s của market_index),
`influence_latest` (toàn bộ mã trong rổ), `foreign_latest`. Chạy `python dnse_stream.py` tự giới hạn 08:45–15:10 T2–T6; `--force --duration N` thử ngoài giờ;
`--backfill` chỉ kéo lại nến hôm nay. Bảng `raw_log` giữ 300 thông điệp đầu để đối chiếu, `events` giữ ack/lỗi server.

**Đã làm với key thật (08/10, 17:00–17:06, ngoài giờ):** xác thực WebSocket OK, REST `/price/HPG/secdef` OK; server báo
`rate_limit: 100 thông điệp/giây, tối đa 100 subscription`. Hai lỗi của SDK 0.5.0 đã vá trong `dnse_stream.py` (không sửa gói):
(1) `nonce` phải là chuỗi, SDK gửi số → "nonce is required"; (2) gói đăng ký phải là
`{"action":"subscribe","channels":[{"name":"tick.G1.json","symbols":[...]}]}`, SDK gửi thiếu `action/channels`. Sau khi vá, server
trả `subscribed … status active` cho 31 mã ở 2 kênh tick.G1 và ohlc.1m. Task Scheduler **"Realtime DNSE"** chạy
`Chay-realtime.bat` 08:40 T2–T6 (log `logs\realtime_<ngày>.log`); xoá bằng `Unregister-ScheduledTask "Realtime DNSE"`.
200 thông điệp dữ liệu đầu tiên mỗi phiên được ghi thô vào bảng `raw_log` để đối chiếu trường.

**Chưa kiểm chứng (cần 1 phiên giao dịch, phiên đầu 09/10):** nội dung thật của thông điệp trong phiên (tên trường lấy theo SDK GitHub
và tài liệu, đã map đủ 12 loại T), độ trễ, tần suất thật của `market_index_influence`, kênh `ohlc.1` có đẩy khi không có giao dịch
không (nếu không thì dựng nến từ `ticks` bằng `time_bucket` trong DuckDB), và `--foreign-universe VN100` (endpoint instruments).
Sáng 09/10 sau 9:15: xem `events` (ack/lỗi), `raw_log`, rồi `index_latest.parquet` và `rt_latest.parquet`.

**Nơi chạy:** tuần đầu chạy trên laptop (Task Scheduler "Realtime DNSE" 08:40) để quan sát; ổn rồi mới thuê VPS VN
(~100–150k/tháng) vì tiến trình phải chạy liên tục trong phiên. Không hợp GitHub Actions/Modal (job 6 giờ, IP Mỹ chưa probe cho DNSE).
App Streamlit: thêm tab "Trong phiên" đọc các file parquet trên với `st_autorefresh` 3–5 giây.

## 6. File đi kèm
- `dnse_stream.py` — bộ thu mức B (mục 5); `dnse.env.example`, `dnse_symbols.txt`, `.gitignore`.
- `poll_realtime.py` — chạy được, `--once` thử bất kỳ lúc nào; mặc định lặp 60 s trong 8:55–15:05 rồi tự thoát.
  Chạy 07/10 17:55: 1.822 nến 10 mã (VNDirect), 1.525 mã 3 sàn (SSI), 12,6 s/vòng; HOSE tăng/giảm 150/151, khối ngoại ròng −900 tỷ,
  basis VN30F1M +0,2 (khớp số đóng cửa).
- `samples\*.json` — phản hồi thô: `vnd_dchart_*`, `ssi_iboard_*`, `vci_priceboard`, `vci_ticks_hpg`, `entrade_*`, `tv_scanner_vn`,
  `vnd_finfo_foreign_today` (khối ngoại cả phiên 07/10 đã có lúc 17:40).
- `data\2026-10-07\*.parquet` — output script.
- Thư viện đã cài thêm (không `--user`): `dnse` 0.5.0 (+httpx) cho `dnse_stream.py`; `paho-mqtt`, `python-socketio[client]`,
  `protobuf` chỉ để thử stream SSI/Vietcap, 2 script không cần.
