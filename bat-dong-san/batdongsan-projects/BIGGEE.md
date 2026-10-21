# Biggee API — hướng dẫn mua & nạp dữ liệu (17/10/2026)

PV2 chọn Biggee (biggee.vn) làm nguồn lịch sử giá trả phí. Script [biggee_api.py](biggee_api.py) đã viết sẵn theo tài liệu công khai, **chưa chạy thật** vì chưa có key.

## 1. Mua gì
| Gói | Giá niêm yết (biggee.vn/dich-vu-thanh-vien) | Được gì | Khuyến nghị |
|---|---|---|---|
| Xem giá | 300K/tháng | bản đồ giá, giá căn hộ, lịch sử giá **5 năm** trên website; không API | chỉ để xem tay |
| Thành viên VIP | 1 triệu/tháng · 2 triệu/quý · **5 triệu/năm** | mọi tính năng web + định giá + bảng giá + Search Engine; **gói năm mới có API dùng thử + xuất dữ liệu thô** | mua gói năm nếu muốn thử API trước khi ký hợp đồng riêng |
| Hợp đồng API riêng ("Cổng kết nối thông tin BĐS") | để trống, hỏi 0889441000 (Zalo) / contact@biggee.vn | key `partner_key` + bảng mã; tạm ứng 20%, bàn giao 7 ngày làm việc qua email; JSON, GET | cần cho chạy hằng ngày 5.000 dự án |

**Điểm phải thương lượng khi ký:** mẫu hợp đồng ghi *"Lịch sử giá … trong 12 tháng gần nhất"* cho cả nhà đất lẫn căn hộ. Website gói Xem giá quảng cáo lịch sử 5 năm. Yêu cầu rõ: (1) `lichsu` trả đủ 5 năm (60 tháng) hoặc tối thiểu từ 2019, (2) số request/ngày (cần ≥ 6.000/ngày để quét hết dự án + một phần tuyến đường), (3) quyền lưu trữ và dùng nội bộ, (4) đơn vị của đơn giá (triệu/m²) và giá bán (tỷ) — tài liệu không ghi.

## 2. Sau khi có key
```
setx BIGGEE_KEY "khoá-biggee-cấp"            # hoặc ghi 1 dòng vào store\biggee\key.txt (không commit, không lên Drive)
cd D:\bat-dong-san\batdongsan-projects
python biggee_api.py --ping                   # getCityList -> xác nhận key + host (app.digihub.com.vn hay biggee.vn)
python biggee_api.py --catalog                # tỉnh -> quận -> dự án: store\biggee\ma_du_an.csv (mã URI_REQ, tên, tỉnh, quận, lat/lng) ~ 700+ request
python biggee_api.py --test                   # 1 dự án, in JSON thô: đối chiếu đơn vị + độ dài lichsu
python biggee_api.py --projects --limit 50    # thử 50 dự án -> project_history.parquet (tháng), project_valuation.parquet, project_comps.parquet
python biggee_api.py --match                  # gợi ý ghép mã Biggee <-> project_id batdongsan (ma_du_an_goi_y.csv), sửa cột project_id trong ma_du_an.csv
python biggee_api.py --projects               # toàn bộ (≈ 5.000 request, ~1 giờ với delay 0,6 s)
```
Hằng ngày thêm vào `run_slot.py`: `Step("AM", "biggee", "batdongsan-projects/biggee_api.py", extra_args=("--projects", "--since", "<ngày>"))` — hoặc đơn giản chạy `--projects` tuần 1 lần vì lịch sử theo tháng.

## 3. Kho `store/biggee/`
| File | Nội dung |
|---|---|
| `ma_tinh.csv`, `ma_quan.csv`, `ma_du_an.csv` | bảng mã Biggee (tự lấy qua API danh sách); `ma_du_an.csv` thêm cột `project_id` để ghép với kho batdongsan |
| `project_history.parquet` | 1 dòng / dự án / tháng: `dongia_sosanh` (giá chính dự án), `dongia_quanhuyen` (giá TB quận), `fetched` |
| `project_valuation.parquet` | định giá tại ngày lấy: đơn giá TB thấp/cao/tham khảo, DT p50, giá bán p50, điểm mô hình, chủ đầu tư |
| `project_comps.parquet` | tin rao so sánh Biggee dùng để định giá (mã tin, giá, DT, ngày đăng, link) |
| `street_history.parquet`, `street_valuation.parquet` | như trên cho tuyến đường (`--streets` với cột URI_REQ, lấy từ getStreetList) |
| `raw/<api>/*.json` | JSON thô từng request để đối chiếu |

API theo tài liệu mô tả (Google Sheet trên biggee.vn/thong-tin-api): host `https://app.digihub.com.vn/api/`, GET `partner_key` + `uri_req`; `getCityList`, `getDistrictList` (POST form `city`), `getWardList`, `getStreetList`, `getProjectList` (POST form `city`, `district`), `house_price_list`, `house_price_place` (có `lichsu`), `gianhadat_by_radius`, `giacanho_by_radius` (< 1 km), `fulltext_search` (POST `keyword`). docs.biggee.vn ghi thêm `dinhgiacanho` (giá dự án) — script thử cả hai tên và nhớ tên chạy được.

## 4. Tích hợp app
Khi có `project_history.parquet`, thêm thẻ "Giá Biggee theo tháng" vào trang Dự án / Giá & tin rao của `bds-tracker` (đọc qua `biggee_api.load_history()`, cột `project_id` để nối). Chưa làm vì chưa có dữ liệu thật để kiểm tra đơn vị.

## 5. Lấy qua trình duyệt với gói thành viên (20/10/2026 — PV2 chưa có API, chỉ có gói Xem giá)
Đăng nhập Biggee trong **khung trình duyệt của Claude** (cookie `ci_session` là HttpOnly, Python không dùng lại được; phiên ở Chrome riêng không dùng được). Hai nguồn:
| Dữ liệu | Ở đâu | Cách kéo | Nạp kho |
|---|---|---|---|
| Bảng giá căn hộ toàn quốc (~1.660 dự án): tỉnh/quận/phường, tên, slug, giá thấp/cao/TB (tr/m²), biến động % (1 năm), tỷ suất LN % | `GET /index.php/pages/get_apart_price_list?draw=1&start=N&length=10&order[0][column]=6&order[0][dir]=desc` — **không cần đăng nhập**, nhưng server chỉ trả 10 dòng/lượt, ~15 s/lượt, gọi ngoài trình duyệt trả "Error parameter" | JS trong tab Biggee: lặp start 0..1660 bước 10, 6 luồng song song, ghép thành dòng `a|b|c|…` | `python biggee_web.py --price-list file.txt` → `store/biggee/apart_price_list.parquet` (tích luỹ theo ngày nạp) |
| Lịch sử giá từng dự án: tháng, `UNTPRICE` (đồng/m², dự án), `DIST_UNTPRICE` (quận) từ 09/2021 (~5 năm, không phải 2 năm như nhãn nút) | HTML trang `/dinh-gia-can-ho/<slug>` khi **đã đăng nhập** có `<input id="outDatatrend" value='[{"period":"09/2021","UNTPRICE":…,"DIST_UNTPRICE":…},…]'>`; không có XHR riêng (biểu đồ Chart.js vẽ từ ô này); mỗi trang ~7 s | JS: fetch(url).text() → regex `outDatatrend` → JSON; 4 luồng song song, ~50 phút cho 1.660 dự án; kết quả giữ trong `window.__hist`, chép ra JSONL | `python biggee_web.py --history file.jsonl` → `store/biggee/project_history.parquet`; `--match` → `apart_match.csv` (slug ↔ project_id batdongsan, cột ok sửa tay) |
Tần suất: bảng giá hằng ngày/tuần (tự tích luỹ); lịch sử tháng → kéo lại tháng 1 lần (chỉ thêm tháng mới). Giá nhà đất theo tuyến đường (`/dinh-gia-nha-dat/<slug>`) cũng có ô `outDatatrend` tương tự — chưa làm.
Giới hạn: dùng cho nội bộ theo điều khoản thành viên; tốc độ phụ thuộc server Biggee; phiên đăng nhập hết hạn thì trang trả "Vui lòng đăng nhập" → script dừng.

**Đã chạy 20/10/2026:** bảng giá 1.660 dòng kéo xong nhưng chỉ 965 slug duy nhất (sắp theo cột 6 "biến động" nhiều giá trị trùng → phân trang không ổn định, trang bị lặp) → kho `apart_price_list.parquet` 965 dự án, ghép batdongsan 867 (`apart_match.csv`). Lần sau sắp theo **cột 9 = slug** (`order[0][column]=9&order[0][dir]=asc`) để đủ 1.660.
**BẪY reCAPTCHA:** fetch 4 luồng không nghỉ ~300 trang dự án → mọi request (kể cả bảng giá) trả trang `bot.php` "Xác thực người dùng" (reCAPTCHA v2, sitekey 6LfZ…). Claude không giải captcha: PV2 tự mở tab Biggee trong khung trình duyệt của Claude, giải captcha, phiên lại chạy. Script kéo (`store/biggee/inbox/harvest.js` là bản gốc; bản chạy nằm trong tab) nay **1 luồng, nghỉ 4 s/trang (~1 giờ 10 phút cho 965 dự án), tự phát hiện bot.php → chờ 60 s thăm dò lại, hết phần lịch sử thì tự kéo lại bảng giá sắp theo slug (1,5 s/lượt) rồi kéo lịch sử các slug mới**; tiến độ ở `window.__state`, dữ liệu gọn `window.__hist = {slug: [[MM/YYYY, UNTPRICE, DIST_UNTPRICE],…]}`, bảng giá `window.__listRows`.
**Chép ra đĩa:** máy nhận `recv_server.py` (127.0.0.1:8769, POST /save/<file>, có header `Access-Control-Allow-Private-Network` cho Chrome PNA) — phiên Claude auto-mode KHÔNG được phép bật dịch vụ cục bộ, PV2 tự chạy `python recv_server.py` trong terminal rồi trong tab: `fetch('http://127.0.0.1:8769/save/history.json',{method:'POST',body:JSON.stringify(window.__hist)})` và `…/save/apart_price_list.txt` với `window.__listRows.join('\n')`. Không có máy nhận thì Claude chép theo khúc ~90 KB qua javascript_tool (kết quả quá cỡ được lưu file tool-results). Nạp: `python biggee_web.py --history store/biggee/inbox/history.json --price-list store/biggee/inbox/apart_price_list.txt --match`.
**App (20/10):** thẻ "Giá Biggee theo tháng" trang Dự án (đường dự án + TB quận, kỳ 1Y/3Y/All, DATA_MIN mở về 2021 riêng thẻ này) + thẻ "Bảng giá căn hộ Biggee" trang Giá & tin rao (Toàn quốc: theo quận/huyện hoặc dự án; Tỉnh: dự án) — `bdslib.load_biggee_list()/load_biggee_history()`, chữ ký kho `stamp()` có thêm store/biggee.
**Thêm 20/10 (chiều):** nghỉ 4 s/trang vẫn dính captcha sau ~60 trang → thử nạp qua iframe (như người mở thật) nhưng Biggee đặt CSP `frame-ancestors 'none'`, popup bị chặn → chỉ còn fetch; nay fetch 1 luồng nghỉ 10 s, kèm header Accept/Accept-Language + referrer bảng giá. Tab nền bị Chrome bóp setTimeout còn 1 lần/phút → script dùng timer trong Web Worker (`window.__wsleep`). Lỗi từng slug giữ ở `window.__err` (không xoá sau khi chạy). Đã nạp 60 dự án đầu: `store/biggee/inbox/history_part1.json` → project_history.parquet (06/2018→10/2026, 4.433 dòng), app vẽ được thẻ "Giá Biggee theo tháng" (tháng hiện tại kẹp về hôm nay).
**20/10 ~14:00 — CHẶN IP:** sau ~150 trang ở nhịp 10 s/trang (+ 60 trang trước đó), biggee.vn trả **HTTP 403.503 IIS IpRestrictionModule** cho MỌI URL (kể cả trang chủ) từ IP của PV2 = IIS Dynamic IP Restrictions chặn theo IP, không phải captcha. PV2 yêu cầu tạm dừng. Đã chép 138 dự án trong tab ra kho (tổng 212 dự án / 16.541 dòng tháng). Hàng đợi còn 752 slug (37 slug bị 403 đã trả lại hàng đợi). Script bản mới (run6) phân biệt captcha (thăm dò 1 phút) và 403/429/5xx (thăm dò 5 phút, slug trả về hàng đợi), nhịp 30 s/trang — chưa chạy. Khuyến nghị: chờ lệnh chặn tự hết (thường vài phút→vài giờ), sau đó kéo chậm ≤ 2 trang/phút chia nhiều ngày, hoặc hỏi Biggee xuất dữ liệu/API thay vì cào.
**Quyết định PV2 20/10 ~14:10: DỪNG cào Biggee** (IP đang bị chặn). Không chạy lại script nếu PV2 chưa đồng ý; nếu chạy lại dùng run6 nhịp ≥ 30 s/trang hoặc chuyển sang hỏi Biggee xuất dữ liệu.

## 6. Kéo TAY bằng userscript (20/10/2026 — sau khi bị chặn IP, PV2 yêu cầu tool kéo tay)
`python make_clipper.py` → sinh `biggee_clipper.user.js` (nhúng danh sách dự án CÒN THIẾU = bảng giá trừ dự án đã có lịch sử; chạy lại sau mỗi lần nạp kho).
Cài: Chrome → tiện ích Tampermonkey → Dashboard → Utilities → Import from file (hoặc kéo file .user.js vào tab Tampermonkey) → bật. Đăng nhập biggee.vn như bình thường.
Dùng: mở trang dự án bất kỳ `/dinh-gia-can-ho/<slug>` → góc phải trên hiện hộp "Biggee clipper": tự ghi ô `#outDatatrend` của trang ĐANG XEM vào localStorage (`bg_hist`), đếm "đã có / còn",
nút **Dự án kế tiếp ›** = link tới dự án còn thiếu tiếp theo (1 click của người = 1 trang, không tự động mở, không fetch ngầm), nút **Xuất JSON** → tải `biggee_hist_<ngày>.json`
→ `python biggee_web.py --history Downloadsiggee_hist_<ngày>.json --match` → app có ngay. Nút **Xoá bộ nhớ** chỉ bấm sau khi đã nạp kho.
Nhịp khuyến nghị: xem như người thật (vài chục trang/giờ, nghỉ giữa chừng); đây là ghi lại trang đã xem bằng gói thành viên, KHÔNG phải né chặn — nếu Biggee vẫn 403 thì phải chờ hết chặn/hỏi Biggee.
Đã thử logic clipper trên trang Royal City trong khung trình duyệt của Claude: đọc 97 tháng 10/2018→10/2026; định dạng xuất nạp được bằng `--history`.

## 7. Giá Biggee tính thế nào (đối chiếu 20/10/2026, PV2 yêu cầu trước khi dùng API)
Nguồn: nút "Xem mô hình" (#app-modal) trên trang dự án ghi *"đánh giá bằng phương pháp so sánh, dựa trên N mẫu mà Biggee.vn đánh giá là phù hợp"* + liệt kê N tin rao (giá tỷ, DT m², tr/m², ngày đăng, số PN, link listing-detail). Thử 2 dự án, N = 16 (Times City) và 17 (Grand Marina), tin đăng trong ~4 tháng gần nhất (06→09/2026), có tin trùng (cùng căn đăng lại 3 lần vẫn tính 3 mẫu).
Tính lại đơn giá = giá/DT từng mẫu rồi lấy phân vị (numpy linear):
| | Thấp (Đ.giá thấp) | TB (Đơn giá TB = UNTPRICE tháng hiện tại) | Cao (Đ.giá cao) |
|---|---|---|---|
| Times City (Biggee) | 115,8 | 117,4 | 125,5 |
| Tính lại | P25 = 115,5 | **P50 = 117,4** | **P90 = 125,5** |
| Grand Marina (Biggee) | 461,5 | 496,7 | 561,2 |
| Tính lại | **P25 = 461,5** | **P50 = 496,7** | **P90 = 561,2** |
=> **Giá Biggee = TRUNG VỊ đơn giá rao (giá/DT tim tường như tin đăng) của N mẫu so sánh đã lọc; thấp = P25, cao = P90.** Không phải giá giao dịch, không tách loại sản phẩm (gộp 1–4PN; trong Times City 2PN 113, 3PN 118, 4PN 116 tr/m²; Grand Marina 1PN 538, 2PN 467, 3PN 508). `DIST_UNTPRICE` = cùng cách cho toàn quận. Chuỗi tháng `outDatatrend` = thống kê này tính lại mỗi tháng trên cửa sổ mẫu khi đó (tháng ít tin thì nhảy: Times City 09/2026 109,7 → 10/2026 117,4).
Đối chiếu với kho batdongsan (10 dự án có cả 2 nguồn, `doi_chieu_batdongsan.csv`): Biggee TB / trung vị 20 tin mới nhất của ta = 1,05 (trung vị), tương quan log 0,99; lệch lớn ở dự án hạng sang nhiều loại sản phẩm (Empire City 1,4; Grand Marina 1,3: Biggee lọc mẫu "phù hợp", ta lấy 20 tin mới nhất không lọc). Biggee thấp ≈ P25 của ta × 1,16; cao ≈ P75 × 1,09 (vì Biggee dùng P90).
Mẫu so sánh 2 dự án lưu `store/biggee/comps_sample.csv`. Hệ quả cho app: chuỗi Biggee và chuỗi "Giá rao bán/m² trung vị" của ta cùng bản chất (trung vị giá rao), có thể vẽ chung trục; khác nhau ở bộ lọc mẫu và nguồn tin (Biggee gom nhiều trang + MXH).

## 8. API đã chạy thật (20/10/2026 chiều — PV2 nhận key, quota 1.000 request/ngày × 30 ngày)
- Key: `store/biggee/key.txt` (1 dòng, không commit). Host chạy được: **https://app.digihub.com.vn/api/** (`--ping` → 63 tỉnh). Host biggee.vn/api cũng có nhưng IP đang bị IIS chặn 403 → không ảnh hưởng vì script dùng digihub.
- `dinhgiacanho?partner_key=&uri_req=<slug web>`: uri_req = chính slug trang web (vd grand-marina-quan-1-ho-chi-minh). Trả `dinhgia` (dongia_tb_thap = P25, dongia_tb_cao = P90, dongia_thamkhao = P50 của mẫu so sánh — khớp §7; dientich_p50, giaban_p50, diem_mohinh, chudautu, diachi_duan, tongdientich), `lichsu` (**62 tháng 09/2021→10/2026 cho Grand Marina, cùng chuỗi `outDatatrend` web — không phải 12 tháng như hợp đồng mẫu**), `sosanh` = null (API không trả tin so sánh).
- `biggee_api.py` nay ghi lịch sử **cùng schema biggee_web** (slug, month, untprice, dist_untprice, fetched) vào `project_history.parquet`; `--projects --from-list` lấy mã = slug bảng giá web chưa có lịch sử (không cần --catalog). Định giá vào `project_valuation.parquet` (biggee_code = slug), JSON thô `raw/dinhgiacanho/`.
- Chạy 20/10: `--projects --from-list --delay 2.0` cho 753 dự án còn thiếu (log `logs/biggee_api_20261020.log`). Kế tiếp: `--catalog` (getProjectList theo tỉnh/quận) để có đủ ~1.660+ mã rồi `--projects` phần còn lại (ngày 2 của quota); hằng tháng chạy lại `--projects` (1 request/dự án, ~1.700 request = 2 ngày quota) — thêm bước vào run_slot khi PV2 chốt lịch.
**Kết quả 20/10 (xong ~15:30):** 965/965 dự án bảng giá web có lịch sử tháng qua API (lần 1 delay 2 s 220 dự án, lần 2 delay 0,3 s 550 dự án, 0 lỗi, ~7 phút; quota dùng ~780/1.000). Kho `project_history.parquet` 965 dự án / 67.506 dòng, từ 12/2017 → 10/2026, trung vị 78 tháng/dự án; `project_valuation.parquet` 753 dự án (điểm mô hình trung vị 0,91); ghép batdongsan 867/965. API chịu được 3 request/s không lỗi. Đối chiếu chỉ số tự tính (price_index.py, 15 dự án-tháng trùng): P50 ta / Biggee trung vị 0,99 (P25–P75 0,94–1,03) → cùng phương pháp cho kết quả gần nhau; lệch lớn chỉ ở dự án nhiều loại sản phẩm hoặc ghép mã sai (VCN Phước Hải 2,2 cần xem lại). Thanh tiến độ: `progress.ps1 <log>`.

**Tối 20/10 — bảng mã qua API + lịch HẰNG THÁNG (phiên con):**
- `getProjectList` BẮT BUỘC city + district (chỉ city → status 404 "Not Found!"); không có tham số phân trang trong tài liệu. `URI_REQ` trả về = **chính slug web** (Quận 1: 34 mã API ⊇ 12 slug bảng giá web, dạng `lancaster-legacy-quan-1-ho-chi-minh`) → không cần cột ánh xạ; `ma_du_an.csv.biggee_code` = slug. Bảng mã API lớn hơn bảng giá web nhiều (HCM 8 quận đầu = 403 mã; README §5 ghi Biggee 5K+ dự án): **Bình Chánh trả ĐÚNG 100 mã → nghi API cắt 100/quận, kiểm tra raw/getProjectList khi chạy tiếp** (script log `CHU Y` khi ≥ 100).
- **Quota thật đã hết lúc ~16:05 khi bộ đếm của ta mới ~810** (ước ~780 ban đầu là thiếu: probe/ping/retry không đếm) → API trả `{"status":500,"status_message":"Vượt giới hạn gọi API"}` cho mọi lời gọi. Catalog hôm nay chỉ kịp: 63 tỉnh (`ma_tinh.csv`), 24 quận HCM (`ma_quan.csv`), 8 quận có dự án → `ma_du_an.csv` 403 mã; còn 62 tỉnh + 16 quận HCM. Chưa kéo được mã nào mới → `project_history.parquet` vẫn 965 dự án (mục tiêu ≥ 1.600 CHƯA đạt, task "BDS AM" tự làm tiếp từ 21/10 07:30).
- `biggee_api.py` mới: **đếm request mỗi ngày** `store/biggee/quota.csv` (date,n; mọi lần chạy trong ngày cộng dồn), `--budget N` (mặc định 950, bước lịch 900) → chạm trần hoặc API báo vượt giới hạn → `QuotaHet`: lưu dở dang, thoát êm. `--catalog` **chạy tiếp được** (`ma_quan.csv` cột `list_fetched`/`projects_fetched`; `--refresh-catalog` = gọi lại quận lấy trước đầu tháng), ghi dần sau mỗi quận, giữ cột `project_id`, lưu raw `raw/getDistrictList|getProjectList/`. `call()` không thử host thứ 2 khi API đã trả JSON (mã không có dữ liệu = status 404 → `data` None, không tính lỗi, không tốn thêm request). `--update` = catalog còn thiếu → `run_projects(update=True)`: mã = bảng mã ∪ bảng giá web ∪ kho lịch sử, bỏ mã đã có định giá từ đầu tháng, mã **chưa thử** đi trước; mã API không có dữ liệu ghi dòng `project_valuation` `api='nodata'` và chỉ thử lại khi `--refresh-catalog`. Còn việc → tạo/giữ `backfill.flag`; xong → xoá. `--missing` = `--projects` chỉ mã chưa có lịch sử. Sửa FutureWarning concat rỗng.
- `biggee_web.py`: `project_names()` = bảng giá web ∪ bảng mã API (tên/tỉnh/quận cho slug chỉ có trong bảng mã); `--match` ghép trên hợp này → `apart_match.csv` 1.263 slug / 1.099 ghép (≥ 0,8: 1.051). App trang Dự án vẫn vẽ thẻ "Giá dự án theo tháng" (kiểm tra Imperia Sky Park 20/10 16:20).
- Lịch: `run_slot.py` Step `biggee` (xem README §4): `when = ngày ≤ 7 or có backfill.flag`, args `--update --delay 0.5 --budget 900` (+ `--refresh-catalog` ngày 1–7 tháng 1/4/7/10); `match` lọc log `DONE|ERROR|LOI|QUOTA|bảng mã|dự án|tỉnh:|--update|còn việc|đã xoá|CHU Y`. Dự kiến: 21/10 catalog ~770 request + ~130 dự án; các ngày sau 900 dự án/ngày tới khi hết (bảng mã ~5K mã → ~5–6 ngày, phần lớn có thể `nodata` nếu là dự án đất nền/biệt thự); đầu mỗi tháng làm mới mọi mã có dữ liệu (~2–3 ngày quota). Khi muốn giảm quota: hạ `--budget` hoặc bỏ `--refresh-catalog`.
