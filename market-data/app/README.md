# Market Data App — xem toàn bộ dữ liệu thị trường + xuất Excel

App web chạy trên máy (Streamlit), đọc thẳng các master CSV của hub market-data (thư mục `MD_ROOT`,
mặc định `D:\market-data`; bản pipeline mới ở `D:\pipeline-data\market-data`). **Không kéo mạng** khi xem.

**09/10/2026 — giao diện mới theo mẫu "Genea"** (nền be sáng `#faf8f6`, điều hướng 3 cấp trên đầu trang, thẻ biểu đồ
trắng bo góc 12px, cam `#ed7d31`, font Inter, biểu đồ Plotly). Khảo sát + design tokens + kiểm kê thẻ:
`design\genea-ui-spec.md`; ảnh chụp từng trang: `design\screens\`. Giao diện cũ (Bloomberg/Altair) giữ nguyên ở
`app_legacy.py`, vẫn chạy được: `python -m streamlit run app_legacy.py --server.port 8769`.

## Chạy

Nhấn đúp `Chay-app.bat` (cổng 8765) hoặc:

```bat
set MD_ROOT=D:\pipeline-data\market-data
set SHIP_ROOT=D:\pipeline-data\shipping
set BCTC_ROOT=D:\bctc
cd /d D:\market-data\app
python -m streamlit run app.py --server.port 8765
```

Trình duyệt mở `http://localhost:8765`. Lần đầu mất ~1 phút vì dựng cache parquet (`cache\tv-history.parquet`,
`cache\tv-ohlc-vn.parquet` cho nến). Cần `plotly` (đã cài 09/10/2026, không dùng `--user`); `kaleido` tuỳ chọn —
có thì mỗi thẻ thêm nút **⧉ Ảnh**.

**Deep-link** `?trang=<section>/<sub>/<nav>`: `ttck/vn/dong-tien`, `vi-mo/viet-nam/gia-ca`, `ttck/trai-phieu/gia-loi-suat`,
`tong-quan/kho`, `tong-quan/excel`… Slug cũ (`vimo`, `vn`, `trai-phieu`, `kho`, `excel`, `khu-vuc`) vẫn mở đúng trang; `?trang=live` (trang Live đã bỏ) về Tổng quan.

## Điều hướng & nội dung

| Cấp 1 (viên thuốc) | Cấp 2 (tab gạch chân) | Cấp 3 (segment) → các mục / thẻ |
|---|---|---|
| **Tổng quan** | Tổng quan | 6 KPI (có điểm hôm nay LIVE khi công tắc bật) + VN-Index · GTGD · Độ rộng · Khối ngoại · bảng độ tươi 21 bộ dữ liệu · nút xoá cache / chạy pipeline |
| | Kho dữ liệu | mở bất kỳ dataset trong REGISTRY, lọc, vẽ cột, tải · khối **Bộ thu real-time DNSE** (PID, 3 dòng log, Bật/Tắt) |
| | Xuất Excel | tick bảng → 1 file nhiều sheet; Chart Pack |
| **Thị trường chứng khoán** | Chứng khoán Việt Nam | **Hiệu suất**: nến/đường 6 chỉ số + KL · rebase 100 · độ rộng dưới MA · hiệu suất ngành rebase · thay đổi vốn hoá ngành 1D…5Y · bảng hiệu suất cổ phiếu trong ngành · nến từng mã |
| | | **Dòng tiền**: GTGD + MA20/50 · GTGD theo nhà đầu tư (giá trị/tỷ trọng, phiên/tuần/tháng) · bình quân tháng · tự doanh ròng + luỹ kế · khối ngoại ròng + luỹ kế · treemap tự doanh / khối ngoại · KN & TD theo ngành · theo mã · *(chưa có: dòng tiền chủ động, giao dịch nội bộ, ETF)* |
| | | **Định giá**: P/E, P/B theo rổ · có/không Vingroup · ngũ phân vị P/E, P/B (theo ngành ICB cấp 3) · P/E ngành ICB · P/E-P/B từng mã |
| | | **Nhà đầu tư**: TK mở mới ròng VSDC · số dư TK · *(chưa có: margin ×3)* |
| | Chứng khoán thế giới | Chỉ số (rebase + bảng 1D…5Y) · Thanh khoản USD · Khối ngoại 7 thị trường · Định giá 12 thị trường |
| | Trái phiếu | Phát hành (app vs VBMA, theo quý, đáo hạn, top hệ sinh thái/CTCK, chi tiết) · Cơ cấu & lãi suất · Giá & đường cong lợi suất (bond-pivot `yield_curve.py`) |
| **Vĩ mô** | Vĩ mô Việt Nam | 9 navtab: Tăng trưởng & sản xuất · Giá cả · Lãi suất & tiền tệ · Hệ thống tài chính · Tài khoá · Tỷ giá · Dự trữ ngoại hối · Thương mại & CCTT · Đầu tư nước ngoài |
| | Vĩ mô thế giới | Tỷ giá (DXY + 12 nước) · Lãi suất (Mỹ) · Chỉ số giá · Tăng trưởng & lao động |
| **Tin tức** | — | placeholder + bảng dữ liệu vừa cập nhật |

Thẻ nào spec yêu cầu mà hệ thống chưa có nguồn (PMI, giá dầu/vàng, margin, ETF, giao dịch nội bộ, đóng góp CPI,
GDP phía chi tiêu, dự toán NSNN, lãi suất điều hành châu Á, thất nghiệp quốc tế) vẫn hiện khung **"Chưa có dữ liệu"**
nhạt kèm ghi chú nguồn dự kiến — không bỏ trống.

## Real-time DNSE — chỉ còn lớp overlay ● LIVE (trang Live đã bỏ 09/10/2026)

PV2 (09/10/2026 chiều): *"bỏ cả phần live đi"* → **không còn trang Live** (pill cấp 1, `?trang=live` về Tổng quan) và không còn các thẻ
riêng trong phiên (KPI strip, Diễn biến/Độ rộng trong phiên, GTGD luỹ kế vs BQ, Toàn sàn, Khối ngoại trong phiên, Ảnh hưởng lên chỉ số,
Bảng giá toàn sàn, Nến 1 phút). `pages_live.py` đã xoá, `data_live.py` chỉ giữ phần overlay + trạng thái bộ thu (code cũ xem git
trước commit "app: bo han trang Live"). Phần **giữ lại** = cách "tích hợp live vào các trang khác":

- **Công tắc ● LIVE + overlay hàng hôm nay** trên mọi biểu đồ lịch sử (mục *Live TOÀN APP* dưới) — nguồn là bộ thu
  `D:\market-dataealtime-lab\dnse_stream.py` (task "Realtime DNSE", 08:45–15:10 T2–T6, `Chay-realtime.bat`) xuất **mỗi 5 giây** vào
  `realtime-lab\data\<YYYY-MM-DD>\`; app đọc `index_latest`, `index_1m`, `stocks_latest` (toàn sàn ~1.500 mã), **không mở** `realtime.duckdb`.
  Đổi thư mục bằng env `RT_ROOT`.
- **Khối "Bộ thu real-time DNSE"** cuối trang **Kho dữ liệu** (tình trạng nguồn, không phải thẻ live): tiến trình có chạy không (psutil),
  3 dòng log cuối `realtime-lab\logsealtime_<yyyymmdd>.log`, nút **▶ Bật** (`Start-Process Chay-realtime.bat`) / **■ Tắt** (terminate PID),
  thư mục dữ liệu phiên gần nhất. `pages_khac._bo_thu_realtime`.
- Đơn vị dữ liệu bộ thu: điểm chỉ số; `total_val` chỉ số đã là **tỷ**; `stocks_latest` giá **đồng**, `total_val`/`fr_*` **tỷ**; khối lượng là
  **số cổ phiếu** (DNSE phát /10, bộ thu nhân 10 lúc parse từ 09/10/2026 13:12 — docstring "DON VI KHOI LUONG" trong `dnse_stream.py`).
- Ảnh kiểm chứng sau khi bỏ: `design\screens-bo-live-{tong-quan,hieu-suat,kho}.png` (server 8773, trong phiên 09/10 13:56, LIVE bật,
  render fragment Tổng quan 0,7 s · Hiệu suất 0,9 s · Dòng tiền 1,4 s). Ảnh trang Live cũ (`10-live.png`, `11-live-toan-app-live.png`,
  `12-live-toan-san.png`) chỉ còn giá trị lịch sử.

### Live TOÀN APP (09/10/2026 chiều) — "chart nào live được thì live hết, tải về dùng lịch sử"

- **Công tắc ● LIVE + tần suất 5/15/60 s** ngay dưới header (`ui_genea.live_bar`), nhớ trong `session_state` + query param
  `?live=1|0&tan=5|15|60`. Mặc định **BẬT trong 08:45–15:10 T2–T6, ngoài giờ tự TẮT** (trừ khi người dùng tự bấm). Bật thì trang đang xem
  render trong `st.fragment(run_every=…)` → mọi thẻ tự làm mới; tắt thì như trước.
  `live_state()` chỉ coi là *active* khi có thư mục dữ liệu hôm nay và bộ thu còn phát (trễ < 300 s trong giờ).
- **Lớp overlay hôm nay** (`data_live.with_live(df, kind, **kw)`): lịch sử (cache dài như cũ) + **1 hàng hôm nay** tính từ parquet của bộ thu
  (`stocks_latest` toàn sàn ~1.500 mã, `index_latest`, `index_1m`), thay thế hàng cùng ngày nếu có, gắn `df.attrs["live"] = {ts, hist_end}`.
  Cache ttl 4 s theo mtime file, overlay < 300 ms (độ rộng ~55 ms, hiệu suất ngành ~120 ms), không mở `realtime.duckdb`.

  | `kind` | Hàng hôm nay lấy từ | Dùng ở thẻ |
  |---|---|---|
  | `index_ohlc`, `index_close`, `world_close` | `index_latest` (điểm, cao/thấp, KL, GTGD tỷ) + nến 1 phút đầu (open) | Chỉ số nến, rebase, CK thế giới rebase + bảng 1D…5Y (chỉ VN-Index), Tổng quan VN-Index |
  | `turnover` | GTGD 3 sàn = `total_val` VNINDEX/HNX/UPCOM, MA20/50 tính lại, Nguồn = "LIVE DNSE" | GTGD, Tổng quan GTGD + KPI |
  | `breadth` | giá khớp toàn sàn + 299 phiên trước → % trên/dưới MA20…300, số mã tăng/giảm theo `change` | Độ rộng dưới MA, Tổng quan độ rộng + KPI |
  | `flows_vn`, `net_flows`, `flows_investor` | Σ `fr_net_val` theo sàn (khối ngoại); **tự doanh = NaN (không live)** | Khối ngoại ròng, GTGD theo NĐT, Tổng quan KN |
  | `stock_ohlc`, `stock_flows` | 1 mã trong `stocks_latest` | Giá cổ phiếu, KN theo mã |
  | `valuation` | giá trị cuối × **hệ số vốn hoá** = Σ(giá×CP)/Σ(tham chiếu×CP) của rổ (HOSE/VN30/HNX/UPCoM, loại Vin, ngành, mã) | P/E, P/B theo rổ, có/không Vin, theo ngành ICB, từng mã, KPI P/E |
  | `sector_caps` | chỉ số ngành cuối × hệ số vốn hoá ngành (HOSE) | Hiệu suất ngành rebase |
  | `sector_returns_live`, `stock_returns_live` | `px_with_today()` = ma trận giá + hàng hôm nay → tính lại 1D…5Y | Thay đổi vốn hoá ngành, bảng hiệu suất cổ phiếu |
  | `treemap_add_today`, `sector_flows_add_today` | cộng KN ròng hôm nay theo mã / theo ngành vào kỳ | Bản đồ khối ngoại, KN theo ngành (Cả kỳ) |

- **Trên thẻ**: điểm hôm nay = **dấu tròn rỗng** trên mỗi đường/cột/nến + nhãn **LIVE hh:mm:ss** góc trên phải (`ui_genea.add_live_marker`);
  chân thẻ "● LIVE hh:mm:ss · lịch sử tới dd/mm · tải về không gồm live". Thẻ không live được (vĩ mô, VSDC, trái phiếu, tự doanh, ngũ phân vị,
  thanh khoản USD…) khi LIVE bật ghi **"Lịch sử tới dd/mm"**. `Card.cut` luôn giữ hàng hôm nay dù ô "đến ngày" còn là phiên trước.
- **⤓ CSV / ⤓ Excel**: luôn xuất **lịch sử** (bỏ hàng hôm nay; thẻ tính lại với giá live truyền `df_export=` bản lịch sử), tooltip ghi
  "tới dd/mm, không gồm live". Hàm `rt.mark_live(df, src)` chép attrs sau các phép `diff/rolling/resample` làm mất attrs.
- **Bộ thu phủ toàn sàn** (`dnse_stream.py`, cùng ngày): server DNSE báo `subscriptions_max = 100 stream/kết nối` (không phải 200) và
  **10 kết nối/user** → 1.000 stream. Dùng: market (100: chỉ số + influence + ohlc + session + 56 mã), watch-1/2 (VN30 + F1M × 6 kênh = 96 + 4 mã),
  uni-1…7 (tick_extra 100 mã/kết nối) = **10/10 kết nối, 1.000/1.000 stream** → tick DNSE 5 s cho **toàn bộ HOSE (406) + HNX (299) + ~60 mã UPCOM
  thanh khoản nhất**; ~720 mã UPCOM còn lại + khối ngoại ngoài VN30 + giá tham chiếu/trần/sàn lấy từ **SSI iBoard** (1 request/sàn, 60 s,
  không cần key; REST `/price/instruments` của DNSE không tồn tại nên không lấy được rổ qua API). Xuất thêm
  `data\<ngày>\stocks_latest.parquet` mỗi 5 s (giá **đồng**, `total_val`/`fr_*` **tỷ**, `src` = dnse|ssi, ghi file tạm rồi `os.replace`).
  Test song song bộ thu thật: `--db data/test.duckdb --out data/test` (nhưng 10 kết nối là chung cho cả user → test chỉ nối được phần còn trống).
- Ảnh: `design\screens\11-live-toan-app-*.png`. Lịch sử `indices-master` có thể thiếu phiên gần nhất (pipeline kéo PM) → KPI ±% VN-Index khi live
  dùng `change_pct` của feed, còn đường chỉ số sẽ nối từ phiên lịch sử cuối sang điểm hôm nay.

## Nguồn live-first (09/10/2026 chiều) — "data nào live được thì kéo live, không đợi pipeline"

PV2: *"mấy data thiếu thì fill live luôn không đợi pull tại pipeline nữa"* và *"các data mà live được không cần historical của
pipeline thì kéo live"*. Module **`data_src.py`** là lớp nguồn live-first: với dữ liệu mà nguồn REST công khai cung cấp được
**cả lịch sử**, app kéo thẳng từ nguồn đó về cache parquet `cache\src\` (cập nhật **tăng dần** trong **thread nền** mỗi lần mở app
và mỗi 30 phút, không chặn render), hôm nay trong phiên vẫn do `data_live.with_live` overlay. Pipeline chỉ còn cho thứ không live
được (vĩ mô, VSDC, trái phiếu, tự doanh theo mã, định giá loại Vin, khu vực…).

| Dataset (REGISTRY) | Nguồn live-first | Lịch sử từ | Pipeline còn dùng cho |
|---|---|---|---|
| `indices` (VNINDEX, VN30, HNXINDEX, UPCOM, + HNX30) | Entrade `chart-api/v2/ohlcs/index` (OHLCV) + VNDirect `vnmarket_prices` (GTGD `accumulatedVal` → triệu VND, value_usd theo fx-master) | VNINDEX 2000 (Entrade), 4 rổ kia 05/2020; GTGD 08/2017 | giai đoạn trước nguồn; chỉ số thế giới/khu vực; VNMidcap/VNSmallcap (tv-history, không có nguồn live) |
| `tv_history` (giá ~1.500 mã) | Entrade `ohlcs/stock` kéo nền (ThreadPool 8, **112 s cho 1.525 mã, 3,5 triệu dòng**) + VNDirect `stock_prices` theo NGÀY cả sàn (3 request/ngày: ngày thiếu + 14 ngày gần nhất để có `ref` giá tham chiếu và GTGD thật) → fallback EOD `stocks_latest` bộ thu | 2012 | mã trước 2012 / sàn nước ngoài; **hệ số điều chỉnh giá** (xem dưới) |
| `flows` (VN) | VNDirect `foreigns` + `proprietary_trading` theo chỉ số | 08/2018, tự doanh 05/2022 (T+1) | khu vực (KOSPI, TAIEX, SET…) |
| khối ngoại theo mã (`foreign_stocks`) | VNDirect `foreigns type:STOCK` theo ngày — **chỉ các ngày sau pipeline** (Vietcap theo mã) | — | toàn bộ lịch sử Vietcap |
| `valuation_wide` | VNDirect `ratios` 4 rổ × 5 chỉ tiêu (cột suy ra + `close/eps_index` tính lại từ indices) | 12/2017 | — (`valuation_adjusted` loại Vin vẫn pipeline) |
| `sectors_wide` | VNDirect `ratios` batch 55 mã ICB — chỉ các ngày sau pipeline | — | lịch sử 55 ngành |

- **Gộp** (`datalib.load`, `datalib.tv`): nguồn live-first là **chính** — thay hàng cùng ngày của pipeline (pipeline hay dính hàng
  *dở phiên*: VN-Index 07/10 pipeline 1.753,88 / GTGD 505 tỷ vs VNDirect 1.753,39 / 15.226 tỷ; khối ngoại 07/10 pipeline = 0);
  giai đoạn nguồn thiếu nối lịch sử pipeline phía trước; nguồn lỗi/offline → pipeline + lỗi ghi `cache\src\status.json`.
  **Chữ ký hàm / cột trả về không đổi** nên pages_* và `with_live` chạy nguyên; khoá cache `_mtime()` = mtime file pipeline +
  mtime parquet nguồn (cần giờ sửa thật dùng `_raw_mt`).
- **Giá Entrade CHƯA điều chỉnh** (kiểm chứng VNM/FPT/HPG/MWG: tỷ lệ tv-history/Entrade bước thang đúng ngày GDKHQ, = 1 sau sự kiện
  cuối). `datalib.adjust_stock_src`: trong giai đoạn trùng tv-history, hệ số = close_tv/close (làm tròn 4 số, ffill theo mã); bỏ hàng
  tv ở ngày cuối (có thể dở phiên); **sau ngày cuối tv-history** phát hiện sự kiện quyền bằng giá tham chiếu VNDirect (`ref` ≠ close
  hôm trước > 0,4%, chỉ HOSE/HNX — UPCOM tham chiếu là giá bình quân nên không xét) và nhân ngược về quá khứ như TradingView.
  Đối chiếu 2,49 triệu dòng trùng: 99,74% lệch ≤ 0,1%; lệch > 1% tập trung 3 mã SHS/PPS/ANT (TradingView điều chỉnh khác — chưa rõ).
  KL Entrade = **khớp lệnh**; hàng VNDirect cũng lấy `nmVolume` cho nhất quán, GTGD = khớp + thoả thuận. Cache gộp `cache\tv-live.parquet`.
- **Trạng thái**: chip "Nguồn dữ liệu" (header) có dòng `● Live-first: n/6 bộ · đang kéo nền x/1.525 mã · cập nhật hh:mm` + bảng
  `data_src.source_status()`; bảng độ tươi (Tổng quan) và Kho dữ liệu có cột/ghi chú **Nguồn: live-first / pipeline**.
- Chạy tay: `python data_src.py [--full] [--only index_daily,flows_daily,...]`. Phiên hôm nay chỉ được nhận vào lịch sử sau **15:15**
  (trước đó hàng hôm nay là của overlay live). Ảnh: `design\screens\13-live-first-*.png` (server test 8772, MD_ROOT pipeline-data:
  Tổng quan/Hiệu suất/Dòng tiền/Định giá có 08/10 + LIVE 09/10, render ấm 0,5–2 s/trang; lần đầu sau khi nguồn đổi ~10 s để ghép giá).
- Chưa làm: rổ VNMidcap/VNSmallcap (không có rổ trong pipeline → vẫn tv-history, thiếu ngày pipeline chưa kéo); `valuation_adjusted`
  (loại Vin) và `stocks_wide`/`shares` vẫn pipeline; tự doanh theo mã (VNDirect T+1) vẫn pipeline.

## Giải phẫu 1 thẻ (`ui_genea.card`)

```
Tiêu đề (H3)  đơn vị nhạt  (?)                       [chip đối tượng · pills góc phải]
[1M 3M 6M YTD 1Y 3Y 5Y All]  [từ ngày] [đến ngày]     [toggle Nến|Đường …]  [⤓ CSV] [⤓ Excel] [⧉ Ảnh*]
(legend) ──── biểu đồ Plotly cao 380 ────
Cập nhật lần cuối: dd/mm/yyyy · ghi chú kỳ
```

- Period + 2 ô ngày nhớ theo `key` của thẻ trong `st.session_state` (`per_<key>`, `d0_<key>`, `d1_<key>`); bấm period
  đặt lại 2 ô ngày, sửa ngày thì period về trống.
- Chart: template Plotly `genea` (nền trong suốt, lưới `#ece8e4`, chữ trục 11px `#8c8c8c`, bảng màu cam/nâu/xám,
  nến xanh `#12965a` / đỏ `#e23b3b`, KL soft, legend trên, số kiểu VN `1.234,5`).
- Bảng %: `html_pct_table` (Mã đậm + tên nhỏ, % canh phải xanh/đỏ, "—" khi thiếu) hoặc `st.dataframe`.

## Cấu trúc module

```
app  app.py          khung trang: header ◆ Market Data + chip "Nguồn dữ liệu: N bộ", cây NAV 3 cấp, ?trang=, gọi module trang
  ui_genea.py     tokens + CSS, nav(), card() / Card (chart, table, empty, export), template Plotly, fig_line/bars/stack/
                  hbar/candle/treemap/group_bars/band/bubble, fmt_vn, html_pct_table, kpi_strip
  data_ext.py     dữ liệu bổ sung trên datalib: OHLC VN (cache parquet), hiệu suất ngành/mã 1D…5Y, GTGD theo nhà đầu tư,
                  treemap, ngũ phân vị, TPCP spot/snapshot, CAR, NSNN niên giám, VSDC
  data_live.py    đọc parquet realtime-lab\data\<ngày>\ (retry + fallback) → overlay hàng hôm nay (with_live, ov_*), live_state,
                  trạng thái/bật/tắt bộ thu (trang Live + pages_live.py đã bỏ 09/10/2026)
  data_src.py     lớp nguồn LIVE-FIRST: Entrade/VNDirect/EOD bộ thu → cache\src\*.parquet, thread nền cập nhật tăng dần,
                  source_status(); datalib.load/tv gộp (xem mục "Nguồn live-first")
  pages_ck.py     TTCK Việt Nam: hieu_suat · dong_tien · dinh_gia · nha_dau_tu
  pages_vimo.py   Vĩ mô VN (9 navtab) + thế giới (4)
  pages_khac.py   Tổng quan · Kho dữ liệu (+ khối Bộ thu real-time) · Xuất Excel · CK thế giới · Trái phiếu (3 navtab) · Tin tức
  datalib.py      LỚP DỮ LIỆU: REGISTRY 21 dataset (+ gộp nguồn live-first), cache, độ rộng, MA, ngành, GTGD, flows, bonds, NSO, tm()
  app_legacy.py   giao diện cũ (Bloomberg, Altair, xuat_excel.py) — không sửa
  xuat_excel.py   chỉ app_legacy dùng (xuất data + chart Excel kiểu Altair)
  design\         genea-ui-spec.md (spec), screens\*.png (ảnh chụp), screens\chup.sh (chụp lại bằng headless Chrome)
  cache\          parquet cache, xoá được, tự dựng lại
```

## Thêm 1 thẻ mới

```python
with ui.card("Tên thẻ", "đơn vị", help="giải thích ?", key="ten_the",
             chips=["A", "B"], chip_default="A",            # tuỳ chọn, pills góc phải (chip_multi=True cho đa chọn)
             toggles={"Kiểu": ["Nến", "Đường"]},            # tuỳ chọn, segment bên phải hàng điều khiển
             periods=ui.PERIODS, default="1Y") as c:        # PERIODS_MACRO cho chuỗi tháng/quý
    d = c.cut(dl.ham_nao_do())                              # cắt theo c.d0 / c.d1; c.chip, c.toggle["Kiểu"]
    c.chart(ui.fig_line(d, "đơn vị"), d, ten="ten file")    # tự thêm nút CSV/Excel + "Cập nhật lần cuối"
```
Không có dữ liệu: `ui.card_empty("Tên", "đơn vị", "ghi chú nguồn dự kiến", key=...)`. Thêm dataset mới: 1 dòng trong
`REGISTRY` (datalib.py) → Kho dữ liệu, chip nguồn, bảng độ tươi tự có.

## Ghi chú số liệu

- **GTGD** lấy từ `indices-master.value` (VCI `accumulatedValue`, triệu VND → tỷ).
  Phiên nào VCI chưa có thì bù bằng `close × KL` từng mã (TradingView) — cột `Nguồn`
  ghi rõ dòng nào là ước tính.
- Phiên **đang giao dịch** được tách riêng (cột `Phiên`): KPI ở trang Tổng quan luôn
  dùng phiên đã đóng cửa, số intraday chỉ hiện ở dòng thông báo.
- **Chỉ số ngành / vốn hoá nhóm** tính lại theo đúng kỳ đang xem (rổ cổ phiếu có giá
  ở cả đầu và cuối kỳ). Nếu cố định rổ từ một mốc xa thì các mã lên sàn sau (VHM, VPL…)
  bị loại khỏi cả chuỗi và hiệu suất ngành sai.
- **Nhóm quy mô** (top 30 / 31-100 / còn lại) là xấp xỉ theo thứ hạng vốn hoá HOSE
  cuối kỳ, không phải rổ chính thức VN30/VNMidcap/VNSmallcap (4 chỉ số đó vẽ riêng).
- Giá là **giá điều chỉnh** TradingView, nên MA và hiệu suất không gãy vì chia tách.
- **Tăng trưởng EPS** dùng `eps_index` (EPS quy về **điểm chỉ số**, đã chia divisor) nên so
  sánh được theo thời gian; `ln_ttm` là tổng lợi nhuận sau thuế 12 tháng của rổ, nhạy với
  thay đổi cấu phần rổ. Tăng trưởng tính **đúng ngày cùng kỳ năm trước**, không phải
  `shift(250)`. Nguồn valuation-wide có vài **điểm gai 1 ngày** (VN30 ln_ttm 03/11/2025 vọt
  gấp đôi rồi về ngay) → `datalib.despike()` bỏ điểm lệch >30% so với cả điểm trước lẫn sau;
  bước nhảy thật (đổi rổ) vẫn giữ vì nó kéo dài.
- **Trái phiếu — phạm vi dữ liệu**: HNX CBIS chỉ có **phát hành riêng lẻ trong nước**, khớp
  VBMA gần tuyệt đối (2023: 309.138 vs 309.229 tỷ · 2024: 435.704 vs 435.704 · 2025: 574.557 vs
  574.556). Con số VBMA hay được trích (2024: 468.618 tỷ, 2025: 629.910 tỷ) **cộng thêm ra công
  chúng** — app không có từng lô, lấy tổng năm từ báo cáo thường niên VBMA (`datalib.VBMA_NAM`).
- **Trái phiếu — 2 lỗi dữ liệu nguồn đã sửa trong `datalib.bonds_clean()`**: (1) 23 lô **USD**
  bị nhân mệnh giá USD như VND nên gần bằng 0 → quy đổi theo tỷ giá bình quân tháng phát
  hành (2025: 875 triệu USD ≈ 23.000 tỷ, khớp VBMA quốc tế); (2) 5 lô **VietBank 2020** nhập
  lãi suất dạng điểm cơ bản (520–800) → chia 100.
- **Ngành trái phiếu** gán theo tên tổ chức + hệ sinh thái (`datalib.phan_nganh_tp`), chia 9
  nhóm như VBMA. Đối chiếu riêng lẻ 2024: ngân hàng 64,4% (VBMA 64,4%), BĐS 22,0% (21,9%);
  2025: 64,1% (64,1%), 24,0% (25,6%). Lãi suất BQ riêng lẻ 2024 7,24% (VBMA 7,2%), 2025 7,40%
  (7,4%).
- **Trái phiếu**: nguồn là `bond-pivot\data\processed\market_issuance_timeline.csv`
  (toàn thị trường, HNX CBIS), không phải file riêng của từng CTCK. Cột `ctck_bao_lanh`
  đi kèm `do_tin_cay`: *cao/khá* lấy từ PDF công bố, *proxy* chỉ suy từ tổ chức lưu ký —
  nên bảng xếp hạng CTCK mặc định chỉ lấy *cao/khá*.
- **Vĩ mô** đọc từ `transmission-fetcher\transmission-wide.csv` (180 chuỗi, đã gộp theo
  `series_id`) + `nso-fetcher\nso_monthly_master.csv` (CPI, XNK, IIP, bán lẻ, FDI của Cục Thống kê, 2023+) + `nso-fetcher\nso_master.csv` (niên giám PX-Web, tab Niên giám NSO) + `macro-fetcher\macro_vn_master.csv` (IMF: chỉ còn chỉ số CPI mức, dự trữ, lịch sử trước 2023). Phải dùng bản *wide* vì SBV đổi cách
  viết tên chuỗi giữa chừng (`LNH binh quan qua dem` → `LNH binh quan Qua đêm`) làm 1 chỉ tiêu
  bị tách thành 2 dòng trong file long; `series_id` thì không đổi. Tên hiển thị tiếng Việt lấy
  từ `datalib.TM_TEN`.
- **Widget TradingView miễn phí không nhúng được mã Việt Nam và phần lớn chỉ số**
  (SPX, DJI, N225…). Vì vậy chart VN dùng `dchart.vndirect.com.vn` — cùng nền TradingView,
  dữ liệu VN, cho nhúng. Nếu khung nhúng trống thì trình duyệt đang chặn iframe: bấm link
  *“Mở trong tab mới”* ngay dưới biểu đồ.

