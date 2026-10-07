# Transmission Fetcher — auto kéo data cho sơ đồ truyền dẫn tỷ giá → thanh khoản TTCK

Bộ tool kéo tự động các chỉ tiêu để **fill số vào từng node** của sơ đồ
"Truyền dẫn áp lực tỷ giá và lãi suất xuống thanh khoản thị trường chứng khoán".

Mỗi node trong sơ đồ = 1 `node_id` (N01…N16) trong `nodes.csv`. Mỗi node có 1–7 series.

```
python fetch_all.py            # incremental (mặc định) — chạy hằng ngày
python fetch_all.py --full     # kéo lại full lịch sử từ 2018-01-01
python fetch_all.py --only sbv # chỉ 1 nguồn: sbv | us | fx | market | bctc
python fetch_all.py --build    # không gọi mạng, chỉ tính lại phái sinh + báo cáo
```

Một lượt chạy hằng ngày ~25 giây (NHNN 15s + phần còn lại). Bước BCTC quý chỉ chạy lại
mỗi 7 ngày (`BCTC_EVERY_DAYS`), khi chạy thì tốn thêm ~6 phút vì phải giãn nhịp vnstock.

## File

| File | Nội dung |
|---|---|
| `nodes.csv` | **Registry** — bản đồ node ↔ series ↔ nguồn ↔ trạng thái. Sửa file này khi thêm chỉ tiêu. |
| `transmission-master.csv` | Data long-format: `date, node_id, node_name, series_id, series_name, freq, unit, value, source, fetched_at`. Dedup theo `(date, series_id)` keep last → idempotent. |
| `transmission-wide.csv` | Pivot `date × series_id` — đổ thẳng vào Excel/SQL. |
| `transmission-nodes.csv` | **Bảng để fill vào sơ đồ**: mỗi series 1 dòng, giá trị mới nhất + thay đổi 1/5/20 quan sát + cảnh báo dữ liệu cũ. |
| `common.py` | Session HTTP giả lập Chrome, parser số kiểu VN, merge/dedup. |
| `src_sbv.py` / `src_us.py` / `src_fx.py` / `src_market.py` / `src_bctc.py` / `src_rates.py` / `src_dlkt.py` / `src_local.py` | 8 fetcher theo nguồn. |
| `brokers.txt` / `banks.txt` | Danh sách mã CTCK / ngân hàng dùng để tổng hợp margin, tiền gửi NĐT, LDR. Sửa tự do. |
| `import_fiinprox.py` | Nạp file Excel xuất từ FiinProX ("Biểu đồ phân tích tài chính") để **backfill lịch sử** cho các chỉ tiêu NHNN chỉ đăng số của ngày hiện tại. |
| `Build-Excel.ps1` | Dựng `transmission.xlsx` (Power Query → CSV, tự refresh khi mở). |
| `powerbi-queries.pq` / `powerbi-nguon.pbids` | Query M + file mở nhanh cho Power BI Desktop. |
| `Run-Pipeline.ps1` | Runner cho Task Scheduler: log + retry + stale check + popup. |

## Nguồn theo node

| Node | Tên trong sơ đồ | Nguồn | Tần suất |
|---|---|---|---|
| N01 | Lãi suất USD | FRED (`fredgraph.csv`, không cần key, gộp 8 mã trong 1 request): SOFR, EFFR, DFEDTARU, DTB4WK, DTB3, DGS2, DGS10, DTWEXBGS | ngày, full lịch sử |
| N02 | Dòng vốn ngoại sinh | VNDirect (khối ngoại) + `src_local.py` gộp từ `D:\market-data\macro-fetcher` (cán cân TM, XNK). FDI/kiều hối: **nhập tay** | ngày / tháng |
| N03 | Nới ràng buộc & nguồn | NHNN — lãi suất tái cấp vốn, tái chiết khấu (ngày) + tỷ lệ vốn ngắn hạn cho vay trung dài hạn thực tế (quý) | ngày / quý |
| N04 | Tỷ giá USD/VND | NHNN (tỷ giá trung tâm) + Vietcombank (mua/bán thực tế) + biên độ ±5% (phái sinh) | ngày |
| N05 | NHNN hút/bơm | NHNN — kết quả đấu thầu OMO theo kỳ hạn + tín phiếu | ngày |
| N06 | NHNN bán forward | NHNN — giá mua/bán USD tham chiếu Sở GD (mức chặn thực tế) + dự trữ ngoại hối từ `D:\market-data\macro-fetcher` | ngày / tháng |
| N07 | Swap point | Phái sinh: `ib_* − us_*` theo kỳ hạn tương ứng | ngày |
| N08 | Lãi suất TT2 | NHNN — lãi suất BQ liên ngân hàng ON/1W/2W/1M/3M/6M/9M | ngày |
| N09 | Nguồn TT2 | NHNN — doanh số liên ngân hàng. Tiền gửi KBNN: **nhập tay** (thuyết minh BCTC quý) | ngày / quý |
| N10 | Room & chi phí vốn NH | NHNN: LDR toàn hệ thống + theo nhóm, tổng tài sản, vốn điều lệ. VCI/BCTC: LDR nhóm niêm yết, CASA. CAR: **nhập tay** | quý |
| N11 | Lãi suất TT1 | `dulieu.nguoiquansat.vn/lai-suat` — 28 NH × 3 kỳ hạn, lấy Big4 / bình quân / cao nhất. Lãi suất cho vay: **nhập tay** | ngày |
| N12 | Tín dụng giải ngân | Cho vay KH nhóm NH niêm yết (VCI/BCTC). Tăng trưởng tín dụng toàn hệ thống: **nhập tay** | quý / tháng |

Cột `status` trong `nodes.csv`: `auto` (tool kéo) · `derived` (tính ra) · `link` (lấy từ tool khác trên máy) · `manual` (phải nhập tay).

## Chỉ tiêu phái sinh (đọc thẳng ra cơ chế trong sơ đồ)

| Series | Ý nghĩa trong sơ đồ |
|---|---|
| `fx_band_ceiling` / `fx_vcb_sell_vs_ceiling` | Mũi tên ③④ "chạm trần → hút / bán forward". Càng gần 0% là càng sát trần. |
| `swap_on` / `swap_1m` / `swap_3m` | Node ⑥ Swap point = r_VND − r_USD. Âm sâu → áp lực carry trade, khối ngoại rút. |
| `ib_spread_policy` | LNH qua đêm − lãi suất tái cấp vốn. > 0 = hệ thống thiếu VND, NHNN phải bơm. |
| `ib_curve_1m_on` | Độ dốc TT2. Dốc lên mạnh = căng thanh khoản kỳ hạn → đẩy giá vốn huy động (⑫). |
| `omo_net` | Bơm ròng = OMO trúng thầu − tín phiếu phát hành. Mũi tên ⑤ "hút → tăng". |
| `ib_vol_total` | Doanh số TT2 — node ⑨ "lệch nguồn". |
| `turnover_all3` / `turnover_ma20` | Node ⑳ "tốc độ tiền đổi chủ". |

## Backfill bằng file FiinProX

Đặt file `.xlsx` xuất từ FiinProX vào thư mục tool (hoặc `fiinprox\`) rồi:

```
python import_fiinprox.py
python fetch_all.py --build
```

Hai bản xuất 08/09/2026 đã nạp:

- **File (2)** — `policy_refinance` + `policy_rediscount` (2005-01, 5.266 dòng), `ib_on` (2006-11, 4.982), `ib_vol_on` (2011-10, 3.698)
- **File (3)** — `fx_central` (2004-12, 3.735 dòng) · lãi suất LNH **1W/2W/1M/3M/6M/9M** (2006-11, ~4.980 mỗi kỳ hạn)
  + `ib_1y` (2006-2012, nguồn đã ngừng) · doanh số LNH 6 kỳ hạn (2011-10, ~3.700)
- **File (4)** — `omo_outstanding` (2010-10, 2.989) · `bill_outstanding` (2012-10, 1.440) · lãi suất trúng thầu
  reverse repo & tín phiếu theo 8 kỳ hạn · `credit_outstanding` (2001-12, 180 tháng) · `m2`,
  `deposits_corporate`, `deposits_household` (2012-04, 166 tháng)
**Đối chiếu chéo ngày 04/09/2026: FiinProX và NHNN khớp tuyệt đối** (4,62% · 892.137 tỷ · 4,50% · 3,00%)
— xác nhận parser SBV đọc đúng.

Thêm chỉ tiêu chỉ cần thêm 1 dòng regex vào `REG` trong `import_fiinprox.py`. Đã khai báo sẵn
(chờ file xuất): lãi suất LNH 1 tuần / 2 tuần / 1 tháng / 3 tháng / 6 tháng / 9 tháng,
doanh số 1 tuần / 1 tháng, tỷ giá trung tâm.

**Bẫy tên cột kỳ hạn:** FiinProX đặt tên cột doanh số các kỳ hạn khác là
"Doanh số 1 tuần (Doanh số giao dịch **qua đêm** 1 tuần)" — chữ "qua đêm" nằm trong TẤT CẢ các cột.
Pattern `doanh so.*qua dem` vì thế nuốt hết mọi kỳ hạn vào `ib_vol_on`. Các pattern doanh số phải
**neo đầu dòng** (`^doanh so 1 tuan`…).

**Bẫy dấu:** FiinProX ghi **tín phiếu lưu hành là SỐ ÂM** (hút tiền), reverse repo dương (bơm tiền)
→ `omo_net_outstanding` là phép **cộng**, không phải trừ.

**Bẫy tháng thiếu:** chuỗi tháng của FiinProX có lỗ (bản xuất này thiếu 12/2025, 04/2026, và 10/2025–04/2026
với M2/tiền gửi). Nếu lấy "quan sát cuối cùng của năm trước" làm gốc YTD thì khi thiếu tháng 12 nó âm thầm
đo với tháng 11 hoặc tháng 9 → ra số YTD sai mà không báo lỗi (đã dính: tín dụng ra 13,3% thay vì để trống).
`build_derived()` giờ chỉ tính YTD khi gốc **thực sự là tháng 12**, thiếu thì để trống, và tính thêm YoY
(so cùng kỳ, dung sai ±25 ngày) để bù cho khoảng trống.

**Bẫy đơn vị:** FiinProX lưu % dưới dạng **thập phân** (`0,045` = 4,5%) và tiền theo **VND tuyệt đối**
(`892137000000000`). Hệ số quy đổi đọc từ dòng "Đơn vị :" — dòng này **có dấu tiếng Việt**, phải
`_norm()` trước khi dò, nếu so khớp chuỗi thô sẽ không nhận ra và nạp nhầm 0,0462 thay vì 4,62.

> `rebuild_derived()` **xoá sạch mọi dòng `source='derived'` rồi tính lại** mỗi lần build — nếu chỉ merge
> thì dòng phái sinh cũ (tính theo công thức sai) vẫn nằm lại trong master vì dedup chỉ đè lên dòng
> cùng `(date, series_id)`.

## Excel và Power BI

`transmission.xlsx` — workbook Excel có **Power Query trỏ thẳng vào 3 file CSV**, đặt
`RefreshOnFileOpen` nên **mỗi lần mở file là tự đọc lại số mới nhất**, không cần chạy lại Python.

| Sheet | Nội dung |
|---|---|
| `Bang dieu khien` | 15 chỉ tiêu chính của 6 mắt xích, lấy bằng `XLOOKUP` từ bảng `Node` |
| `Node` | Bản đồ node (106 dòng × 17 cột) |
| `Chuoi` | Bảng wide ngày × chỉ tiêu (6.683 × 116), mới nhất lên đầu — dùng vẽ biểu đồ |
| `Du lieu` | Long-format đầy đủ (161.700 dòng) — dùng làm PivotTable |

Dựng lại workbook (chỉ cần khi muốn đổi cấu trúc, không cần để cập nhật số):

```powershell
powershell -ExecutionPolicy Bypass -File "D:\market-data\transmission-fetcher\Build-Excel.ps1"
```

Mở file mất vài giây vì Power Query đọc lại 161.700 dòng. Nếu thấy chậm, xoá sheet
`Du lieu` — hai sheet còn lại đủ cho hầu hết việc, và `Chuoi` vẫn pivot được.

**Power BI**: máy chưa cài Power BI Desktop. Khi cài xong, double-click `powerbi-nguon.pbids`
để mở sẵn kết nối, rồi dán các query trong `powerbi-queries.pq` (có sẵn bảng Master, Node,
Lịch ngày, kèm measure DAX và bố cục báo cáo gợi ý). Muốn refresh tự động theo lịch thì phải
publish lên Power BI Service và cài On-premises Data Gateway ở chế độ personal, vì nguồn là
file trên máy.

**BẪY LOCALE — quan trọng:** CSV do pandas ghi dùng **dấu chấm** làm thập phân, máy đang
locale Việt Nam (dấu phẩy). Mọi `Table.TransformColumnTypes` trong M **bắt buộc** có culture
`"en-US"` ở tham số cuối, nếu không Excel/Power BI đọc `4.62` thành `462`.

## Gỡ phụ thuộc FiinProX (08/09/2026)

FiinProX phải export tay nên không dùng làm nguồn thường xuyên được. Sau vòng thay nguồn,
FiinProX chỉ còn giữ vai trò **lịch sử một lần** — mọi chuỗi vẫn chạy hằng ngày đều đã có
nguồn tự động:

| Nhóm | Nguồn tự động thay thế |
|---|---|
| Lãi suất LNH 7 kỳ hạn + **doanh số cả 7 kỳ hạn** | NHNN `/lãi-suất1` (trước đây chỉ lấy ON/1W/1M nên phải backfill; nay lấy hết) |
| Tỷ giá trung tâm, lãi suất điều hành | NHNN `/tỷ-giá`, `/lãi-suất1` |
| **OMO & tín phiếu đang lưu hành**, trúng thầu, đáo hạn, bơm/hút ròng ngày | dulieukinhte `sbv-bomhut-tien-334` |
| **M2, tiền gửi dân cư, tiền gửi TCKT**, tỷ trọng tiền mặt/M2 | dulieukinhte `cung-tien-m2-huy-dong-385` |
| Lãi suất trúng thầu các kỳ hạn lẻ (8/21/28/56/91/140 ngày), lãi suất tín phiếu | NHNN — parser bắt mọi dòng "Kỳ hạn N ngày" nên tự có lại khi NHNN mở đợt tương ứng |

**Còn đúng một chỗ chưa thay được:** `credit_outstanding` (mức dư nợ tín dụng tuyệt đối).
Không có nguồn mở nào công bố *mức*; chỉ có *tốc độ tăng* (`credit_growth_ytd`, dulieukinhte,
số NHNN công bố — đã tự động). Thay thế thực dụng cho việc theo dõi mức: `bank_loans`
(tổng cho vay khách hàng của 18 ngân hàng niêm yết, VCI/BCTC, theo quý, tự động).

### Lỗi dữ liệu FiinProX đã phát hiện và xử lý

Chuỗi **theo tháng** của FiinProX gán nhãn theo **ngày công bố**, không phải tháng tham chiếu —
và độ trễ công bố của NHNN ngày càng dài nên sai số lớn dần:

| FiinProX ghi | Thực tế là tháng | Lệch |
|---|---|---|
| 2026-05-29 | 01/2026 | 4 tháng |
| 2026-06-30 | 03/2026 | 3 tháng |
| 2026-07-31 | 05/2026 | 2 tháng |
| 2026-08-28 | 06/2026 | 2 tháng |

Phát hiện bằng cách đối chiếu M2 với dulieukinhte: **giá trị trùng khít nhau đến từng đồng**,
chỉ khác nhãn ngày. Trước 2025-09-30 hai nguồn khớp cả ngày lẫn giá trị, từ 2025-10 trở đi mới lệch.
Đây cũng là lời giải cho chuyện "M2 chỉ tăng 2% trong 11 tháng trong khi tín dụng tăng 14%" —
không phải gãy chuỗi, mà là do nhãn ngày sai.

Đã **xoá 21 dòng** FiinProX sai nhãn (`m2`, `deposits_household`, `deposits_corporate`,
`credit_outstanding` sau 2025-09-30) và để dulieukinhte cấp số từ đó về sau.
Chuỗi **theo ngày** của FiinProX thì đúng nhãn — đã kiểm chéo cả 7 kỳ hạn với NHNN ngày 04/09,
khớp tuyệt đối. Chỉ chuỗi theo tháng bị lỗi này.

`omo_outstanding` ngày 07/09: FiinProX 250.778,26 vs dulieukinhte 250.223,28 — lệch 0,2%,
khác nhau ở cách suy đáo hạn. Dùng dulieukinhte vì khớp với bảng chi tiết theo kỳ hạn của NHNN.

## Các tỷ lệ cấp hệ thống — đọc cho đúng

Ba lỗi đã sửa ngày 08/09/2026 sau khi rà lại nhóm tỷ lệ:

**1. `ldr_listed_banks` 115% không phải LDR.** Nó là cho vay khách hàng chia tiền gửi khách hàng —
mẫu số thiếu toàn bộ nguồn vốn huy động khác, nên luôn cao hơn nhiều so với con số NHNN công bố.
Đặt cạnh `ldr_system` 77% thì đọc thành mâu thuẫn. Đã tách làm hai:

| Series | Ý nghĩa | 2026-Q2 |
|---|---|---|
| `ldr_system` | LDR toàn hệ thống theo NHNN (trần quy định 85%) | **77,06%** |
| `ldr_broad_listed` | Cho vay ÷ nguồn vốn huy động **mở rộng** của 18 NH niêm yết (tiền gửi KH + liên NH + giấy tờ có giá + nợ CP/NHNN) | **77,26%** |
| `loan_deposit_listed` | Cho vay KH ÷ tiền gửi KH — chỉ báo khe hở huy động, **không phải LDR** | 115,07% |

`ldr_broad_listed` lệch `ldr_system` đúng **0,2 điểm %** — đây mới là kiểm chứng chéo thật:
một bên tính từ bảng cân đối của 18 ngân hàng, một bên là số NHNN công bố cho cả hệ thống.

**2. VCI dùng lại `item_id` cho cả dòng tổng lẫn dòng thuyết minh.**
`deposits_and_loans_from_other_credit_institutions` xuất hiện 2 lần trong cùng một báo cáo với
2 giá trị khác nhau (405.184 và 389.128 tỷ ở VCB) → `groupby.sum()` sẽ cộng đôi.
`_balance_sheet()` giờ `drop_duplicates(["item_id","period"], keep="first")` để lấy dòng tổng.

**3. CASA có nguy cơ lệch tử/mẫu.** Tử số lấy từ thuyết minh (`nob66`), mẫu số lấy từ bảng cân đối
của *tất cả* mã — ngân hàng nào thiếu thuyết minh sẽ kéo tỷ lệ xuống. Đã ràng mẫu số về đúng nhóm mã
có thuyết minh cùng kỳ. Thực tế cả 18 mã đều có `nob66` nên số không đổi, nhưng đây là bẫy chờ sẵn
khi đổi danh sách trong `banks.txt`.

### Gãy chuỗi thống kê tháng 10/2025 — không phải lỗi tool

Số của NHNN có một lần **phân loại lại** tại 10/2025, nhìn rõ trong `deposits_*`:

| | 09/2025 | 10/2025 | Thay đổi |
|---|---|---|---|
| Tiền gửi dân cư | 7.832.400 | **10.194.762** | +30,2% |
| Tiền gửi TCKT | 8.350.231 | **5.714.809** | −31,6% |
| Tổng hai nhóm | 16.182.631 | 15.909.571 | −1,7% |
| M2 | 19.980.717 | 18.728.084 | −6,3% |

Khoảng 2,4 triệu tỷ chuyển từ nhóm TCKT sang nhóm dân cư trong một tháng — đó là thay đổi cách phân
loại, không phải dòng tiền thật. M2 đồng thời giảm 6,3% nên nhiều khả năng phạm vi thống kê M2 cũng
bị thu hẹp. Hệ quả: `m2_growth` và `deposit_growth_ytd` của **năm 2025** bắc qua chỗ gãy này nên
không đọc được như tăng trưởng thật; số **2026 trở đi sạch** vì cả gốc lẫn ngọn đều nằm sau mốc gãy.
`credit_growth_ytd` không ảnh hưởng vì lấy thẳng số tăng trưởng NHNN công bố.

## Phạm vi: đã bỏ khối thị trường (08/09/2026)

Bốn node cuối chuỗi — **N13 khối ngoại, N14 margin, N15 tiền gửi NĐT tại CTCK,
N16 thanh khoản TTCK** — đã bị gỡ khỏi tool theo yêu cầu, vì được theo dõi bằng file riêng.
Xoá 9 chuỗi và 16.802 dòng khỏi master; `brokers.txt` và phần kéo BCTC công ty chứng khoán
cũng bỏ luôn.

Tool giờ dừng ở **N12 — tín dụng giải ngân**, tức phủ đoạn từ lãi suất USD → tỷ giá → can thiệp
của NHNN → liên ngân hàng → room và giá vốn ngân hàng → tín dụng. Phần truyền dẫn xuống giá
cổ phiếu nằm ở file riêng của PV2.

**Giữ lại `fii_net_val`** (khối ngoại mua ròng) ở node N02 — đây là *input* của sơ đồ
(dòng vốn ngoại sinh), không phải kết quả ở cuối chuỗi, nên không nằm trong nhóm bị xoá.

## SFL — cái tính được và cái không

**Tỷ lệ vốn ngắn hạn cho vay trung dài hạn đầy đủ theo Thông tư 22 thì KHÔNG dựng lại được**
từ báo cáo tài chính. Công thức cần nguồn vốn tách theo **kỳ hạn còn lại**, mà thuyết minh chỉ
tách tiền gửi thành "không kỳ hạn" và "có kỳ hạn" — gộp chung kỳ hạn 1 tháng với 36 tháng.
Đúng mảnh quyết định mẫu số là mảnh không có. Mọi cách ước lượng đều phải giả định tỷ trọng
tiền gửi trên 12 tháng, mà đó chính là ẩn số cần tìm.

Ba thứ có thật:

| Chỉ tiêu | Nội dung | Chuỗi |
|---|---|---|
| `sfl_system` | **Số chính thức** của NHNN — 29,16% (Q2/2026) | Trang NHNN chỉ đăng kỳ hiện tại, pipeline bồi 1 điểm mỗi quý |
| `mlt_loan_share` | Tỷ trọng cho vay trung dài hạn của 27 NH niêm yết — **tử số** của SFL | Đủ từ Q1/2018 |
| `mlt_loans` | Dư nợ trung dài hạn tuyệt đối | Đủ từ Q1/2018 |

`mlt_loan_share` đi từ 49,7% (2018) xuống đáy 43,0% (Q1/2025) rồi lên **47,3%** (Q2/2026) —
tăng 4,3 điểm trong năm quý, tức áp lực chuyển hoá kỳ hạn đang quay lại. Tổng ba kỳ hạn khớp
chính xác `bank_loans` nên số liệu tự kiểm chứng được.

## Cạm bẫy đã xử lý (đừng lặp lại)

1. **WAF của NHNN (Incapsula).** `sbv.gov.vn` chặn User-Agent kiểu curl/python, và khi
   chặn vẫn trả **HTTP 200** kèm trang `Request Rejected` ~246 byte → `common.get()`
   coi đó là lỗi chứ không phải thành công. Phải gửi đủ bộ header Chrome
   (`sec-ch-ua`, `Sec-Fetch-*`, `Accept-Language`…). Gọi dồn dập cũng bị chặn tạm thời
   → giữa 4 trang có `sleep(3)`, và retry backoff 6/12/18s.
2. **Số kiểu NHNN dùng dấu phẩy cho CẢ hàng nghìn lẫn thập phân:** `892,137,0` = 892137.0;
   `4,62` = 4.62; `3,000%` = 3.0. `common.vn_number()` xử lý bằng quy tắc "bỏ hết dấu chấm,
   dấu phẩy **cuối cùng** là thập phân".
3. **4 trang NHNN chỉ công bố số của ngày hiện tại**, không có lịch sử → chuỗi thời gian
   được bồi dần mỗi ngày. Chạy sót ngày nào là mất ngày đó (không backfill được).
   Ngày lãi suất liên ngân hàng thường **trễ 2–4 ngày** so với hôm nay, đó là bình thường.
4. **Đơn vị `accumulatedValue` của VCI đổi giữa chừng** (trước 12/08/2025 là VND tuyệt đối,
   sau đó là triệu VND). `src_market._norm_value()` chuẩn hoá bằng tỷ lệ `value/volume`
   nên không hard-code mốc ngày.
5. **Chạy giữa phiên thì số thanh khoản / khối ngoại là số LUỸ KẾ DỞ DANG của ngày đó.**
   Không sai — lần chạy sau kéo lại 10 ngày gần nhất và dedup keep last nên tự đè lại số cuối ngày.
   Đó là lý do đặt task lúc 16h00 (sau khi đóng cửa và sau khi NHNN cập nhật OMO buổi chiều).
6. **vnstock bản community giới hạn ~20 request/phút và chỉ trả 4 kỳ BCTC.**
   `src_bctc.py` gọi thẳng `Finance._get_report(..., limit=40)` để vượt giới hạn 4 kỳ (giống
   `D:\bctc\fs-extractor`), và giãn 6 giây/mã vì mỗi mã tốn 2 request. Bước BCTC chỉ chạy lại khi
   quý gần nhất đã cũ hơn 45 ngày. vnstock in banner quảng cáo có emoji → phải nuốt stdout,
   nếu không sẽ vỡ cp1252 trên Windows.
7. **WAF của NHNN giới hạn số request trên MỘT PHIÊN, không phải theo nhịp.** 4 trang đầu qua
   được, đến trang thứ 5 (thống kê TCTD) bị chặn kể cả khi đã giãn 10s và retry 15/30/45s —
   nhưng gọi lại bằng **session mới** thì thành công ngay. `src_sbv.fetch_all()` vì thế tạo
   **một session riêng cho mỗi trang**.
8. **`dulieu.nguoiquansat.vn` dùng DẤU CHẤM làm thập phân** (`3.60` = 3,6%) — ngược với NHNN.
   Không được dùng `common.vn_number()` ở đây (hàm đó coi dấu chấm là hàng nghìn → 360);
   `src_rates._num()` parse riêng. Cùng lý do, `_norm()` phải **bỏ dấu tiếng Việt trước** khi
   `re.sub(r"[^a-z0-9]")`, nếu không "Ngân hàng" thành "nnhng" và mọi phép so khớp đều trượt.
9. **Mở `transmission-master.csv` bằng Excel là Windows khoá file** → `to_csv` ném
   `PermissionError` và mất trắng cả lượt kéo. `common.safe_to_csv()` thử lại 3 lần,
   vẫn khoá thì đổ ra `transmission-master.csv.pending.csv`; lần chạy sau `merge_master`
   tự nuốt lại file pending rồi xoá — **không mất dữ liệu**, nhưng đóng Excel rồi chạy
   lại cho gọn.
10. **PS 5.1 + `2>&1` trên native command** → `FutureWarning` vô hại của pandas bị hiểu là lỗi.
   `Run-Pipeline.ps1` dùng `Start-Process` + redirect ra file, chỉ tin `ExitCode`.
11. **`New-ScheduledTaskSettingsSet` mặc định `DisallowStartIfOnBatteries=True`** → laptop chạy
   pin thì task kẹt Queued vĩnh viễn nhưng vẫn báo `LastTaskResult=0`. Bắt buộc
   `-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries`.

## Nguồn đã thử và loại

- **`dttktt.sbv.gov.vn`** (trang thống kê cũ của NHNN, menu vẫn trỏ tới): DNS phân giải được
  `202.58.245.101` nhưng **không kết nối được** — bỏ, dùng trang mới trên `sbv.gov.vn`.
- **Vietstock `finance.vietstock.vn/Macro/GetReportDataByIDs`**: có đủ VNIBOR / OMO / tỷ giá
  trung tâm / tín dụng / huy động / FDI theo chuỗi dài, nhưng anonymous bị chặn hoàn toàn
  (`RequestUpgradeAccount_Permission`) ở **mọi khoảng ngày**. Chỉ dùng được nếu có tài khoản trả phí.
  Payload nếu sau này có tài khoản:
  `POST /Macro/GetReportDataByIDs {termTypeID, subTermTypeID, fromDate, toDate, type:"CATEGORY", listID:[categoryID], __RequestVerificationToken}`
  — CategoryID: 66 VNIBOR · 54 thị trường mở · 55 tỷ giá trung tâm · 52 tín dụng · 53 huy động
  · 56 lãi suất điều hành · 69 lãi suất tiền gửi · 50 dự trữ ngoại hối · 62 FDI · 37 BOP.
- **FRED gọi từng mã một mất ~45 giây/mã** (8 mã ≈ 6 phút). `fredgraph.csv?id=A,B,C…` nhận
  nhiều mã trong 1 request → còn ~2 giây. Từ **4 mã trở lên** FRED trả về **file ZIP**
  (1 CSV cho mỗi tần suất: `daily.csv`, `daily,_7-day.csv`) chứ không phải CSV thuần — `src_us._frames()`
  dò 2 byte đầu `PK` để xử lý cả hai dạng.
- **World Bank API** (`api.worldbank.org`) — kiều hối `BX.TRF.PWKR.CD.DT`, FDI `BX.KLT.DINV.CD.WD`:
  **không kết nối được từ máy này** (http=000 nhiều lần, cả qua curl lẫn WebFetch).
- **FDI giải ngân theo tháng** — chỉ có trong thông cáo của Cục Thống kê (NSO), không có API.
- **Trang "Tỷ lệ nợ xấu" của NHNN đang RỖNG** (không có bảng số) → không lấy được NPL, và
  không tìm thấy trang nào của NHNN công bố CAR toàn hệ thống.
- **`dulieukinhte.com`** — 96 bảng vĩ mô VN miễn phí, HTML render sẵn, curl lấy được, mỗi bảng
  ~30 kỳ gần nhất. Đang dùng cho: lãi suất cho vay bình quân, tăng trưởng tín dụng (số NHNN
  công bố), FDI đăng ký, tỷ giá chợ đen. **CẢNH BÁO — một số bảng đặt NHẦM nhãn ngày:** bảng
  "Lãi suất điều hành + liên ngân hàng" (slug 391) gắn nhãn 08-09-2026 cho số thực tế của
  28-08-2026 (lệch 11 ngày); bảng "Đường cong lợi suất TPCP" (417) và "Kiều hối" (426) cũng
  lệch. Giá trị thì ĐÚNG (đối chiếu 7 kỳ hạn với NHNN + FiinProX khớp tuyệt đối), chỉ sai ngày.
  JSON-LD trong trang có `temporalCoverage` ghi đúng mốc cuối → `src_dlkt._check_dates()` so
  cột mới nhất với nó, lệch thì **bỏ qua cả bảng**. Bảng OMO (334), tỷ giá chợ đen (719),
  tăng trưởng tín dụng (353), FDI (405) đều qua được guard này.
  Site có REST API (`api.dulieukinhte.com`, cần đăng ký lấy key; gói free 100 request/tháng,
  10/phút, lịch sử 5 năm) — chưa dùng vì 100 request/tháng không đủ cho pipeline chạy hằng ngày.
- **VNDirect finfo** không có dataset lãi suất/vĩ mô (`v4/interest_rates`, `v4/macro*` đều 404).
- **Endpoint XML cũ của VCB** (`portal.vietcombank.com.vn/.../pXML.aspx`) bỏ qua tham số ngày,
  luôn trả hôm nay → dùng `vietcombank.com.vn/api/exchangerates?date=YYYY-MM-DD` (có lịch sử).

## Task Scheduler

Chạy **hằng ngày 16h00** (sau khi NHNN cập nhật OMO buổi chiều và thị trường CK đóng cửa):

```powershell
$A = New-ScheduledTaskAction -Execute 'powershell.exe' `
     -Argument '-NoProfile -ExecutionPolicy Bypass -File "D:\market-data\transmission-fetcher\Run-Pipeline.ps1"'
$T = New-ScheduledTaskTrigger -Daily -At 16:00
$S = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
     -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'Transmission Fetcher Daily' -Action $A -Trigger $T -Settings $S
```

Sau mỗi lần chạy: `status.txt` một dòng `OK|STALE|FAIL <thời gian>`, log tại `logs\run_*.log`.


## Cập nhật 14/09/2026 — gộp vào hub
Task cũ `Transmission Fetcher Daily` 16:00 (`Run-Pipeline.ps1`) → nay là bước `transmission` (retry 3, stale ≤ 4 ngày, Critical) chạy ĐẦU TIÊN trong **Market Data PM 18:30** (`D:\market-data\Run-Market.ps1`). `common.py` chỉ còn ROOT/MASTER/COLS/row/merge_master; session/get/vn_number/vn_date/safe_to_csv/log nằm ở `..\mdlib.py` (re-export, `from common import ...` vẫn chạy).
