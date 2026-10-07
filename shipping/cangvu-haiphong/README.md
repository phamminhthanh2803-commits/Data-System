# Cảng vụ Hải Phòng – lịch điều động tàu (cvhp)

Kéo **Kế hoạch điều động tàu** hằng ngày của Cảng vụ Hàng hải Hải Phòng để đếm tàu, DWT/GT ra vào, bến nào xếp dỡ.

Nguồn: `https://csdltau.cangvuhaiphong.gov.vn/pages/ship_plan.aspx?d=<offset>`
`d` = số ngày lệch so với hôm nay của server (0 hôm nay, -1 hôm qua, 1 ngày mai). Lịch sử lùi được tới 2016.
Mỗi trang = 1 ngày, 4 bảng: **Rời cảng / Di chuyển / Vào cảng / Qua luồng**. HTML lỗi thẻ `</td>` thừa → parse bằng lxml (không dùng html.parser).

## Chạy
```
python cvhp_scrape.py                          # mặc định: kéo lại [hôm nay-3 .. ngày mai] rồi rebuild bảng dẫn xuất
python cvhp_scrape.py --from 2019-01-01        # backfill (bỏ qua ngày đã có; --force để kéo lại)
python cvhp_scrape.py --no-fetch               # chỉ rebuild calls/summary từ events
```
Chạy theo lịch: bước `cvhp` trong `D:\shipping\Run-Shipping.ps1` slot AM (task "Shipping AM" 9:00).
Trang của một ngày được **bổ sung dần trong ngày** (ngày mai chỉ có vài dòng) → cửa sổ 5 ngày gần nhất luôn kéo lại và **thay toàn bộ** dòng của ngày đó.

## Output (`data/`)
| File | Ý nghĩa |
|---|---|
| `cvhp_events.csv` | Master long: 1 dòng = 1 sự kiện. `section` = Vao / Roi / DiChuyen / QuaLuong. `from`/`to` là cột Từ/Đến gốc. Số đã đổi định dạng VN (18.360 → 18360; 8,6 → 8.6). `is_sb` = tàu sông biển "(SB)". |
| `cvhp_calls.csv` | 1 dòng = **1 chuyến tàu cập cảng**: ghép Vào → Di chuyển* → Rời của cùng tàu (khoá `ship_key` = tên bỏ hậu tố SB). DWT/GT đếm 1 lần/chuyến. `berths` = các bến đã ghé theo thứ tự (`|`), `first_berth`, `last_berth`, `hours_in_port`, `origin`, `destination`. |
| `cvhp_terminal_daily.csv` | Ngày × bến: `n_arrive`/`dwt_arrive` (tàu Vào đến bến), `n_shift_in` (Di chuyển đến bến), `n_berth_in` = tổng cập bến, `n_depart`/`dwt_depart` (Rời từ bến), `n_shift_out`. Có `group/ticker/kind` từ `terminals.csv`. |
| `cvhp_daily.csv` | Tổng theo ngày: số tàu + DWT + GT vào / rời, số di chuyển, qua luồng. |
| `raw/YYYY-MM-DD.html` | Cache HTML gốc từng ngày. |

### Trạng thái chuyến (`status` trong cvhp_calls)
- `complete`: có Vào và Rời.
- `no_departure`: có Vào nhưng chưa thấy Rời (tàu đang làm hàng, hoặc cuối cửa sổ dữ liệu).
- `no_arrival`: có Rời (hoặc Di chuyển) mà không thấy Vào trước đó (tàu vào trước ngày bắt đầu dữ liệu, tàu đóng mới ở nhà máy đóng tàu DAMEN/Phà Rừng...).
- `shift_only`: chỉ có Di chuyển.

### Khử trùng lặp (tàu vắt qua nhiều ngày)
- Cùng tàu, cùng ngày/bảng/giờ/từ/đến → 1 sự kiện.
- 2 lần **Vào** liên tiếp (chưa Rời) cùng nơi đi/bến đến trong ≤ 3 ngày → lịch bị dời, giữ lần sau (`n_revisions`).
- Vào quá 45 ngày không thấy Rời → coi như thiếu dữ liệu rời, sự kiện sau mở chuyến mới.
- Tàu **Vào** ngày D, **Di chuyển** ngày D+1, **Rời** ngày D+2 → đúng 1 chuyến, không đếm 3 lần.

## Đếm cho đúng
- Số tàu cập cảng HP trong kỳ = số dòng `cvhp_calls` có `arr_date` trong kỳ (không tính `no_arrival`).
- DWT vào cảng theo kỳ = sum `dwt` của các chuyến đó. Theo bến = `cvhp_terminal_daily` cột `n_arrive`/`dwt_arrive` (chỉ tàu vào từ ngoài) hoặc `n_berth_in` (kể cả tàu chuyển bến tới).
- Bảng **Qua luồng** là tàu quá cảnh (sông pha biển đi Quảng Ninh/Thái Bình...), không phải tàu cập cảng HP → không đưa vào `calls`, chỉ có trong `daily`.
- Cột Từ/Đến: ở bảng Vào, `to` là bến HP; ở bảng Rời, `from` là bến HP; vì thế danh sách bến tự sinh từ dữ liệu, `terminals.csv` chỉ để gán nhóm/mã CK (sửa tay, tên bến phải viết đúng như trên trang).

## Bẫy
- `d` tính theo ngày của **server**; script kiểm tra dòng "KẾ HOẠCH ĐIỀU ĐỘNG TÀU NGÀY dd/mm/yyyy" trong trang, lệch thì chỉnh lại `d` một lần.
- Bảng Qua luồng chỉ 10 cột (không GT, tàu lai, đại lý).
- Tên bến có dấu tiếng Việt lẫn lộn ("KHU NEO VẬT CÁCH" vs "VAT CACH"), Hateco xuất hiện cả HHIT lẫn HTIT.

## Bổ sung thông tin tàu (vessel_enrich.py) — hãng khai thác, TEU, tuyến dịch vụ
DWT không đủ để phân tích container → 3 tầng làm giàu, kết quả ở `data/vessel_master.csv` (1 dòng/tàu):
1. **BalticShipping** (API JSON miễn phí, `--particulars`, mặc định 300 tàu/ngày trong bước `cvhp-vessels` của Shipping AM): IMO, MMSI, loại tàu (mã `bs_type` → `vessel_class`: 12 container, 14 general, 9 bulk, 26/29/82 tanker, 32 gas, 83 roro), năm đóng, chủ tàu. Khớp tên + DWT/GT ±10%. Không có TEU; chủ tàu là chủ cho thuê, không phải hãng khai thác.
   - Dự phòng **VesselFinder** tìm theo tên (HTML tĩnh) cho tàu mới BalticShipping chưa có (đóng 2022+). Số "IMO" 7 chữ số bắt đầu bằng 1 là id nội bộ VesselFinder của tàu không có IMO.
   - **Flexport Atlas** (`--teu`, `https://atlas.flexport.com/vessel/imo:<imo>[/mmsi:<mmsi>]`, JSON-LD trong HTML): **TEU danh nghĩa**, loại tàu, năm đóng, LOA. Chỉ có tàu container → trang rỗng (`teu_src = flexport:none`) là tín hiệu tàu không phải container. Trang chỉ IMO nặng 5MB, có MMSI thì 90KB → luôn ưu tiên có MMSI.
2. **Luật** `carriers.csv`: tiền tố tên tàu (WAN HAI, SITC, HAIAN, EVER/UNI, XIN=COSCO, KOTA=PIL...), từ khoá chủ tàu, đại lý độc quyền (Cát Tường=Wan Hai, SITC VN, Hải An, GLS, VSICO, Vinafco, VTB Tân Cảng) → `operator`.
3. **Agent** (skill `/cvhp-vessels` trong Claude Code): `--todo --limit N` xuất `data/vessel_todo.csv` (tàu container thiếu service/operator, và TEU nếu Flexport không có, ưu tiên hay ghé 12 tháng gần nhất) → agent tra web → `data/vessel_lookup.csv` → `--merge`. Lookup ghi đè luật và BalticShipping (`*_src = lookup`), tra lại sau 1 năm.

`vessel_master.csv` dùng chung cho cả Cảng vụ TP.HCM (`--port hp|hcm|all`, mặc định all: đọc events cả 2 cảng, apply ghi enriched cho từng cảng; loại hàng CONTAINER của HCM cũng dùng để phân loại tàu). `--apply` (chạy cuối mỗi lần): `cvhp_calls_enriched.csv` (calls + imo/vessel_class/operator/teu/service), `cvhp_monthly_operator.csv` (tháng × hãng × lớp tàu: chuyến, TEU danh nghĩa, DWT), `cvhp_monthly_terminal.csv` (tháng × bến × lớp tàu: lượt cập bến không tính khu neo, TEU, DWT). Cột `teu_known` cho biết bao nhiêu chuyến đã có TEU để đánh giá độ phủ.

Không có API key / `claude` CLI trên máy nên tầng 3 chạy trong phiên Claude Code (desktop). Nếu sau này có `ANTHROPIC_API_KEY`, có thể thay bằng script gọi API web_search theo lô.
