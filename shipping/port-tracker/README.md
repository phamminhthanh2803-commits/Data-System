# Port & Vessel Tracker

App Streamlit theo dõi cảng và tàu của 12 cảng vụ hàng hải. Dữ liệu được **pipeline ghép liên tục** (từ 09/10/2026) vào kho chia sẻ `store/`; khi mở, app chỉ nạp các file store mới vào sqlite riêng `cache\live.sqlite` rồi phân tích trong bộ nhớ. App không đọc các file `*_events.csv` / `*_calls.csv` do pipeline parse sẵn; vẫn gọi thẳng được trang nguồn (nút ở thanh bên / trang Dữ liệu).

## Ghép dữ liệu liên tục (`pt_update.py`, 09/10/2026)
| Việc | Cách làm |
|---|---|
| Bước pipeline | `port-tracker` (Shipping AM 9:00) và `port-tracker-pm` (Shipping PM 22:00) trong `D:\shipping\run_slot.py` gọi `pt_update.py`: nạp store → gọi nguồn các ngày thiếu/chưa chốt trong cửa sổ 14 ngày (`--days`) → xuất lại các cảng vụ-tháng vừa ghi |
| Ai kéo cảng vụ nào | Cloud (GitHub Actions, repo Data-System) kéo 11 cảng vụ (`CLOUD=1` → bỏ HCM). Cảng vụ TP.HCM chặn IP nước ngoài → laptop kéo (`PT_AUTHS=HCM`) trong `Run-Local-Cvhcm.ps1` 8:30 và `Run-Local-Mini.ps1` 18:40 |
| Kho chia sẻ `store/` | `events/<cảng vụ>/<YYYY-MM>.parquet` (1 file = 1 cảng vụ 1 tháng, ~0,5 MB; cả lịch sử 2019+ ≈ 50 MB, 987 file) + `days/<cảng vụ>.csv` (ngày nào đã kéo, lúc nào). rclone đồng bộ `gdrive:pipeline-data/shipping/port-tracker/store`; cloud là chủ, 2 đường dẫn HCM chỉ laptop ghi (`laptop_only` trong `data_manifest.py`) |
| App nạp | `livedata.import_store()` khi mở: so chữ ký size|mtime từng file với bảng `meta` → chỉ nạp file đổi (mỗi file thay trọn 1 cảng vụ-tháng trong sqlite). Lần đầu nạp cả kho ~1–2 phút, sau đó < 1 giây |
| Seed lần đầu | `python pt_update.py --export-all --no-pull` xuất sqlite hiện có ra `store/` (37 giây) rồi `rclone copy` lên Drive |
| Chạy tay | `python pt_update.py` (tất cả), `--auths HCM --days 3`, `--months 2` (chỉ nạp 2 tháng store vào sqlite, cloud mặc định 4), `--ttl 30`, `--max-pages 60` |
| Env | `PORT_TRACKER_DB` (sqlite), `PORT_TRACKER_STORE` (store/), `PT_AUTHS`, `PT_DAYS`, `CLOUD=1` |

Mô hình cloud: app chạy từ bản copy `D:\pipeline-data\shipping\port-tracker` bằng `D:\cloud-deploy\local\Chay-app-port-tracker.bat` (tự `sync_data.py app` kéo store mới từ Drive trước khi mở). Bản gốc `D:\shipping\port-tracker` vẫn chạy được với `Chay-app.bat` (đọc `store/` tại chỗ).

## EconDB (`econdb.py`, 14/10/2026) – nguồn của trang "Sản lượng"
| Việc | Cách làm |
|---|---|
| Nguồn | EconDB API v1 `https://api.econdb.com/v1/` (docs https://developers.econdb.com/docs/), header `Authorization: Token <key>`. Key ở biến môi trường `ECONDB_TOKEN` (laptop: `setx`, cloud: GitHub secret cùng tên). Thiếu key → bước tự bỏ qua |
| Bước pipeline | `econdb` (Shipping AM) trong `run_slot.py` / `Run-Shipping.ps1`: ~120 request, ~3 phút |
| Kho `store/econdb/` | `series.parquet` (long: scope, metric, series, date, value – container full tuần, nằm bãi, theo hãng, theo đối tác, VN↔17 nước, 13 cảng khu vực, toàn cầu; `term_throughput`/`term_full` = throughput / container full TỪNG terminal), `calls.parquet` (lượt ghé, TÍCH LUỸ vì API chỉ giữ ~4 tháng), `schedule.parquet` (lịch ~3 tuần tới), `ports.parquet`, `terminals.parquet` (mã, terminal_id, tên, nhà khai thác) |
| Theo terminal | API v1 không có → trang terminal công khai econdb.com (không cần key): `/maritime/ports/async/<locode>/` (mã terminal) → `/maritime/get_terminal_detail/<locode>/<mã>/` (terminal_id) → `/widgets/port-time-series/data/?unit=throughput&by=teu_class&freq=month&terminal_id=` (cộng các cỡ tàu) + `/widgets/sea-trade-by-week/data/?freq=month&terminal_id=`. ~32 terminal, từ 2022; tổng HP T9/2026 367k ≈ container-traffic 357k. Mã → bến cảng vụ ở `econdb.TERMINAL_MAP` (VNCHL = HICT, HTIT riêng). MAIN/SPCT/SITV: EconDB trả 500 |
| Cảng | 6 cảng VN trong top 400 EconDB: `VN HPH`, `VN SGN`, `VN VUT`, `VN DAD`, `VN DNA`, `VN UIH` (locode CÓ dấu cách). Map cảng vụ: HP→HPH, HCM→SGN+VUT, DNG→DAD, DNI→DNA; cảng vụ khác không có |
| Chạy tay | `python econdb.py`, `--only traffic,calls,schedule` |
| Cách đọc | TEU ở trang này là container **có hàng (full) xếp dỡ** do EconDB ước từ AIS – khác TEU danh nghĩa (sức chở tàu) ở các trang khác |

## Ước/dự báo sản lượng (`nowcast.py`, 14/10/2026) – cùng trang "Sản lượng"
Trang "Sản lượng" (`?trang=san-luong/<phạm vi>`, slug cũ econdb/du-bao tự chuyển): dải KPI (thực tế tháng gần nhất, ước tháng này, dự báo tháng tới, MAPE, nằm bãi) + 1 thẻ "Sản lượng container" (chip: Thực tế & dự báo / Theo chiều / Theo cảng|terminal / Theo hãng / XK, NK theo nước|đối tác / So khu vực; bến: Tỷ trọng trong cảng vụ) + 1 thẻ "Chi tiết" (toàn quốc: bảng ước/dự báo theo cảng vụ, bến; cảng vụ/bến: Bảng tháng / So sánh mô hình / Nằm bãi / Lịch tàu / Lượt ghé).

Tổng quát hoá `hict_nowcast.py` của PV2 cho mọi cảng/bến:
| Việc | Cách làm |
|---|---|
| Biến | Lượt cập bến tàu container (cảng vụ): số lượt, sức chở TEU danh nghĩa (thiếu TEU → DWT / trung vị DWT/TEU), tổng giờ nằm bến chặn 80 h/lượt. Bỏ 2 ngày cuối (tàu chưa rời) |
| Mục tiêu (thực tế = EconDB) | Cảng vụ: container full EconDB (HP, HCM = SGN+VUT, DNG, DNI). Bến: throughput terminal EconDB qua `TERMINAL_MAP` |
| Từng cảng một | `fit_ports`: cảng vụ nhiều cảng EconDB (HCM) chạy hồi quy RIÊNG cho từng cảng (biến = bến thuộc cảng theo `econdb.terminal_port` ← cột node của cangvu-hcm/areas.csv: HO CHI MINH → VN SGN, CAI MEP/VUNG TAU/LONG SON → VN VUT; thực tế = container full cảng đó) rồi `combine` cộng lại; MAPE của tổng tính trên tháng mọi cảng đều có backtest. Toàn quốc = combine các cảng vụ. HCM: gộp 14,4% → SGN 9,8% + VUT 2,7% |
| Mô hình | Hồi quy không hệ số chặn, 6 biến thể (A–F: giờ + sức chở / chỉ sức chở / chỉ giờ, toàn bộ quá khứ hoặc 12 tháng); backtest ngoài mẫu từ tháng thứ 13, chọn MAPE thấp nhất; so với naive "tháng trước" |
| Kết quả | Nowcast tháng trọn có biến chưa có số thực tế; tháng đang chạy = w × (biến đã có quy ra cả tháng) + (1 − w) × dự báo thuần, w = số ngày đã có / số ngày tháng (0 nếu < 5 ngày), khoảng ± MAPE × (1,5 − 0,5 w); tháng tới: biến = TB 3 tháng trọn × mùa vụ của chuỗi thực tế năm trước (chặn 0,7–1,35). |
| Số công bố (ưu tiên) | `nowcast_targets.csv` (auth, terminal, month, actual_teu) nhập ở chip "Số công bố" (Chi tiết, phạm vi Từng cảng). Bến có ≥ 9 tháng công bố thì mô hình dùng số này thay EconDB: EconDB terminal chỉ đếm container có hàng và lệch dần (HICT: công bố/EconDB 1,43 → 1,56 → 1,77 cho 2024 → 2026, nghi lẫn HTIT/HHIT cùng Lạch Huyện; EconDB×hệ số sai 13,8% so công bố). Đã nhập (PV2 gửi 14/10/2026, 3 ảnh bảng "Cảng Sông Miền Bắc / Cảng nước sâu"): HICT 01/2024–03/2026, HTIT 05/2025–03/2026, HHIT 02/2025–03/2026; Green port, VIP Green, Chùa Vẽ+Tân Vũ, Đình Vũ, Nam Hải Đình Vũ, Nam Đình Vũ, PTSC Đình Vũ, VIMC 01/2024–09/2025 (nguồn trống T10–12/2024; số đỏ T11–12/2025, T3/2026 là ước của nguồn; VIMC T9/2024 = 0 bỏ); backtest ngoài mẫu 6,2% (mô hình G: giờ bến 6 tháng) so 8,1% mô hình A của script. Biểu đồ vẽ thêm đường EconDB full để đối chiếu |
| Hệ số chung THEO NHÓM | Bến KHÔNG có số công bố (hoặc < 9 tháng): xếp nhóm bằng chính dữ liệu bến (`terminal_class`: nước sâu = tàu TB ≥ 4.000 TEU; sông lớn = sức chở ≥ 50.000 TEU/tháng; sông nhỏ = còn lại), rồi `pooled_by_class` = OLS gộp không chặn (thử giờ+sức chở / giờ / sức chở, hệ số ≥ 0, chọn MAPE trong mẫu thấp nhất) trên 12 tháng cuối có số của các bến công bố CÙNG NHÓM cùng cảng vụ (nhóm < 2 bến → hệ số "chung" mọi bến; cảng vụ không có bến công bố → toàn quốc) → `apply_pooled`. PV2 14/10: "cảng nhỏ hơn cũng khác, nước sâu hơn cũng khác" — HP: nước sâu 135–155 TEU/giờ & 0,4–0,5 TEU/sức chở; sông lớn 64–79 & 0,8–1,1; sông nhỏ 50–77 & 1,2–2,0. Sai số hiện là TRONG MẪU gộp, không phải backtest riêng; app ghi rõ. Thứ tự nguồn thực tế của bến: số công bố riêng → hệ số chung → EconDB terminal → phân bổ. Số công bố gộp nhiều bến ghi `A+B` trong cột terminal (Chùa Vẽ + Tân Vũ) → biến gộp, hiện 1 dòng |
| Đối chiếu fit & chọn tay | Biểu đồ chính vẽ "Mô hình fit" (hệ số cuối, suốt lịch sử, như biểu đồ Model Fit của PV2) + chấm "Backtest ngoài mẫu". Chip "So sánh mô hình" (bến): bảng 11 mô hình (MAPE backtest / 6 tháng gần / fit trong mẫu), biểu đồ fit của mô hình đang dùng + 2 mô hình kế tiếp, selectbox "Mô hình dùng cho bến này" (Tự động / A–K) → `run(force=)`; lựa chọn giữ trong session (`nc_force_<auth>_<bến>`), không lưu file |
| Mô hình & chọn | 11 biến thể: giờ / sức chở / cả hai × cửa sổ toàn bộ, 12, 6, 3 tháng; chọn theo điểm = TB(MAPE cả lịch sử, MAPE 6 tháng backtest gần nhất) → bám khi năng suất TEU/giờ đổi. Mùa vụ dự báo của bến lấy từ chuỗi cảng (`seasonal_ref`) |
| Từng bến tự hồi quy | Mỗi bến có mã terminal EconDB tự hồi quy trên lượt cập bến của chính nó, thực tế = throughput terminal; `MIN_TRAIN_TERM = 6` (backtest từ tháng 7, cần ≥ 9 tháng) vì chuỗi Cái Mép mới từ 08/2025 → 27 bến có mô hình riêng (kể cả TCTT). Chip "Theo bến" ở Chi tiết cảng vụ = bảng ước/dự báo mọi bến + tổng các bến so với mô hình cảng vụ. Nowcast chỉ cho tháng SAU thực tế cuối |
| Bến không có mã terminal / chưa đủ 9 tháng | Thực tế = container full cảng × tỷ trọng container xếp dỡ của bến trong lượt tàu EconDB ghép được với bến cảng vụ (tên tàu + giờ đến ±2 ngày, ghép ~85–92%); ước/dự báo = ước/dự báo cảng vụ × tỷ trọng TB 3 tháng (không backtest) |
| Bẫy | Tên bến cảng vụ Đà Nẵng lưu Unicode NFD → so sánh qua `nowcast.nfc()` |
| Lưu ý | Huấn luyện theo bộ lọc "Dữ liệu nạp" (mặc định 2 năm). TP.HCM: dữ liệu cảng vụ thêm Cái Mép từ 07–08/2025 → mô hình đang kém naive, app cảnh báo |

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
Deep-link: `http://localhost:8766/?trang=<trang>/<phạm vi>&cv=<mã cảng vụ>&ben=<bến>`, ví dụ `?trang=dieu-do/cang-vu&cv=HCM`,
`?trang=tong-quan/cang&cv=HP&ben=HICT`. Trang = `tong-quan`, `hang-tau`, `dieu-do`, `tuyen`, `du-lieu`; phạm vi = `toan-quoc`, `cang-vu`, `cang`
(slug cũ `ben-cang`, `tau`, `canh-bao` vẫn mở đúng trang).

## Giao diện (09/10/2026: theo mẫu Market Data App, `ui_genea.py`)
Nền be sáng, không sidebar, thẻ biểu đồ Plotly (xem `D:\market-data\app\design\genea-ui-spec.md`). `ui_genea.py` là bản copy từ
`D:\market-data\app` để app tự chạy; `.streamlit\config.toml` đặt theme sáng.
- **Header**: logo ◆ + chip **Kho dữ liệu: 12 cảng vụ ▾** (popover: độ phủ từng cảng vụ, công tắc "Kéo thêm từ trang nguồn khi mở", TTL, nút Kéo lại ngay).
- **Bộ lọc chung** (áp dụng cho mọi trang): Loại tàu (Container / Mọi loại) · Đo lường (Lượt tàu / TEU danh nghĩa / DWT) · Độ phân giải (Tháng / Tuần) · Dữ liệu nạp (2 năm / 3 năm / Từ 2019).
- **Điều hướng cấp 1** (viên thuốc cam): 5 trang. **Cấp 2** (tab gạch chân, có trên MỌI trang): **Toàn quốc · Từng cảng vụ · Từng cảng** — cấp cảng vụ chọn 1 cảng vụ, cấp cảng chọn cảng vụ + bến (bến xếp theo tổng 24 tháng của đo lường đang chọn; lựa chọn nhớ qua các trang).
- **Thẻ biểu đồ**: tiêu đề + đơn vị + "?" · chip (vd Gộp theo Bến / Nhóm chủ bến / Mã CK) · kỳ 3M 6M 1Y 2Y 3Y All + 2 ô ngày · toggle (Giá trị / Thị phần) · nút ⤓ CSV ⤓ Excel · dòng "Cập nhật lần cuối". Kỳ cuối chưa trọn bị bỏ khỏi chuỗi.

| Trang | Toàn quốc | Từng cảng vụ | Từng cảng |
|---|---|---|---|
| Tổng quan | KPI 30 ngày cả nước; chuỗi theo cảng vụ; tỷ trọng cảng vụ (%); bảng cảng vụ × kỳ | KPI cảng vụ; cột chồng theo Bến / Nhóm chủ bến / Mã CK; thị phần trong cảng vụ; bảng bến × kỳ | KPI bến; chuỗi bến (giá trị / thị phần trong cảng vụ); hãng ghé nhiều nhất; cỡ tàu bình quân; danh sách lượt cập bến |
| Hãng tàu & tàu | Ma trận hãng × cảng vụ 12 tháng; chi tiết 1 hãng theo cảng vụ + đội tàu; tra cứu tàu đã ghé cả nước | Ma trận hãng × bến; chi tiết 1 hãng theo bến + đội tàu; tra cứu tàu đã ghé cảng vụ | Hãng ghé nhiều nhất + hãng theo kỳ tại bến; chi tiết 1 hãng; tra cứu tàu đã ghé bến |
| Điều độ & cảnh báo | Kế hoạch ngày 12 cảng vụ (vào/rời/di chuyển), tàu đang ở cảng; 4 cảnh báo cả nước | Kế hoạch + cảnh báo trong 1 cảng vụ | Kế hoạch có bến này ở cột từ/đến; tàu đang ở bến; tàu mới / ngừng ghé bến; tàu đổi bến đến/đi khỏi bến |
| Tuyến | Chặng lớn nhất, chặng theo tháng, hãng trên chặng, vòng tuyến từng tàu (mọi tàu container) | …của các tàu đã ghé cảng vụ | …của các tàu đã ghé bến |
| Dữ liệu | Độ phủ kho theo cảng vụ, kéo bù từ nguồn, độ phủ TEU/hãng, tải chuyến | Độ phủ 1 cảng vụ, kéo bù 1 cảng vụ, tải chuyến | Tải lượt cập bến |

Trang **Tàu** (chi tiết 1 tàu: thông số, nằm cảng từng chuyến theo bến, lộ trình + nút vẽ bản đồ PNG, toàn bộ chuyến) nằm cuối trang Hãng tàu & tàu, chọn tàu trong ô "Chọn tàu đã ghé…" (danh sách theo phạm vi đang xem). Giao diện cũ (Altair + sidebar) không còn giữ.

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
