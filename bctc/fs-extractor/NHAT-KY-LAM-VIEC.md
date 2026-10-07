# Nhật ký làm việc — FS Extractor (bộ tool kéo data tài chính VN)

> File này ghi lại **toàn bộ quá trình + quyết định + lý do** để tiếp tục ở phiên/context khác.
> Đọc file này trước khi sửa code. Hướng dẫn dùng cho người dùng cuối ở `HUONG-DAN.txt`.
> Cập nhật lần cuối: 2026-07-14 (thêm chọn mã theo NGÀNH `--nganh` + lệnh `nganh` + cache listing).
> LƯU Ý: code đã GỘP về 2 file `fsx.py` + `common.py` (từ 2026-06). Các tên
> `fs_pull.py / cap_pull.py / liq_pull.py / _pacer.py` trong phần dưới là TÊN CŨ —
> logic vẫn đúng nguyên, chỉ đổi chỗ: fs_pull→`cmd_bctc`, cap_pull→`cmd_cap`,
> liq_pull→`cmd_liq`, _pacer→`common.Pacer`.

---

## 0. Mục đích & bối cảnh

- **Người dùng**: làm đầu tư (PV2 / CKT Capital), cần **data ngành** cổ phiếu VN: BCTC theo mục, thanh khoản, vốn hóa, P/E, P/B — kéo theo lô nhiều mã, theo thời gian.
- **Vị trí tool**: `D:\bctc\fs-extractor\` (đã dời ra ngoài thư mục VS Code để update VS Code không xoá).
- **Nguồn dữ liệu**: thư viện `vnstock` 4.x, nguồn **VCI** (`iq.vietcap.com.vn/api/iq-insight-service`).
  - Dữ liệu BCTC theo quý: từ **2018**. Giá/khối lượng theo ngày: từ **~2015**.
  - Trước 2018 không có (giới hạn nguồn) — muốn có phải scrape CafeF/Vietstock hoặc FiinPro trả phí.
- **Lưu ý Windows bắt buộc**: set `PYTHONIOENCODING=utf-8` trước khi chạy, nếu không banner tiếng Việt của vnstock crash console cp1252. Các file .bat đã set sẵn.

---

## 1. Cấu trúc thư mục

```
D:\bctc\fs-extractor\
├── fsx.py                Entry point duy nhất, 4 lệnh con: bctc / cap / liq / nganh
├── common.py             Dùng chung: Pacer, retry, listing+ngành, chọn theo ngành, CSV
├── run.bat               Menu: 1=BCTC, 2=Vốn hóa, 3=Thanh khoản, 4=Tra cứu ngành
├── tickers.txt           Danh sách mã (chỉ cần khi KHÔNG dùng --nganh)
├── nganh_cache.csv       Cache mã+sàn+ngành ICB (tự tạo, hạn 7 ngày, xóa được)
├── HUONG-DAN.txt         Hướng dẫn người dùng cuối
├── NHAT-KY-LAM-VIEC.md   File này
├── output\               CSV BCTC
├── output_liq\           CSV thanh khoản
└── output_cap\           CSV vốn hóa/P-E/P-B
```

### 1b. Chọn mã theo NGÀNH (thêm 2026-07-14, thay cho nhập tickers thủ công)

- **Vấn đề**: mỗi lần chạy phải sửa `tickers.txt` / gõ mã rất mệt → giờ chọn cả nhóm ngành.
- **Cách hoạt động** (`common.py`):
  - `get_listing(refresh)`: ghép `Listing().symbols_by_exchange()` (lọc `type=STOCK`,
    sàn HSX/HNX/UPCOM, map HSX→HOSE, ~1.525 mã) với bảng ICB 4 cấp → cache
    `nganh_cache.csv` 7 ngày (`NGANH_CACHE_DAYS`) để tra ngành **không tốn API**.
  - `strip_accents()`: bỏ dấu + thường hóa → gõ `"ngan hang"` khớp `"Ngân hàng"`.
  - `resolve_nganh(patterns, listing, san)`: khớp **substring cả 4 cấp ICB**, nhiều
    ngành cách nhau dấu phẩy; trả (tickers, tên ngành khớp). Khớp substring nên từ
    khóa ngắn có thể trúng nhiều ngành (vd "van tai" = 133 mã L3+L4) — tool luôn
    IN RA tên ngành khớp + số mã + ước lượng phút trước khi chạy để user tự thấy.
  - `load_industry(listing)`: khi đã có listing (do dùng `--nganh`) thì tái sử dụng làm
    bảng phân ngành merge vào output, khỏi gọi API thêm lần nữa.
- **CLI** (cả 3 pipeline): `--nganh "tên ngành"` (lặp lại được) + `--san HOSE,HNX`
  + `--refresh-nganh`. Ba nguồn mã CỘNG DỒN: positional + `--file` + `--nganh`, khử
  trùng lặp giữ thứ tự (`_gather_tickers` trong fsx.py).
- **Lệnh tra cứu**: `python fsx.py nganh [từ khóa]` — liệt kê ngành 4 cấp + số mã,
  có từ khóa thì in luôn danh sách mã + gợi ý lệnh kéo. run.bat menu 4.
- Đã test end-to-end: `liq --nganh "van tai thuy" --san HOSE` → 9 mã, cột ngành đầy đủ.

---

## 2. Ba pipeline

### 2.1 fs_pull.py — BCTC
- Kéo 5 báo cáo, xuất 5 CSV long-format (ticker | ten_cong_ty | nganh_L1..L4 | item | item_en | item_id | period | value):
  `income_statement, balance_sheet, cash_flow, ratio, note`.
- **Bypass giới hạn 4 kỳ** của bản community: gọi hàm nội bộ `Finance._get_report(report_type=..., limit=500)` (limit ở phía thư viện trong `vnstock/explorer/vci/financial.py`, API thực trả full).
- **note.csv (thuyết minh)**: API VCI có section `NOTE` ẩn mà vnstock không expose → gọi thẳng endpoint `financial-statement?section=NOTE`, map field code qua `_get_ratio_dict(format='dataframe')`. Field prefix tùy loại hình: `noc`=DN thường (157 chỉ tiêu), `nob`=ngân hàng (219), `nos`=chứng khoán (678), `noi`=bảo hiểm (307). **Lọc theo membership trong mapping, KHÔNG lọc cứng prefix** (đã từng bug: lọc cứng `noc` làm CK/NH/BH rỗng).
- Phân ngành ICB 4 cấp merge từ `Listing().symbols_by_industries()` (~7.7k mã).
- Date range `--from 2020-Q1 --to 2024-Q4` (hoặc chỉ năm). Ratio VCI trộn kỳ năm vào data quý → tool tự lọc đúng loại kỳ theo `--period`.

### 2.2 liq_pull.py — Thanh khoản INDEX
- Mặc định CHỈ kéo **7 index**: VNINDEX, VN30, VNMID, VNSML, HNXINDEX, HNX30, UPCOMINDEX → `indices.csv` (index|date|OHLC|volume). (VNXALL không tồn tại trên VCI.)
- Truyền mã vào dòng lệnh vẫn kéo được từng cổ phiếu (kèm ngành + gtgd_ty = close×volume xấp xỉ).
- API trả dư ngày trước `--from` → script có bước clip date range.

### 2.3 cap_pull.py — Vốn hóa + P/E + P/B  ★
Xuất 3 file vào `output_cap\`:
- **market_cap_daily.csv**: `ticker | ten_cong_ty | nganh_L1..L4 | date | close | shares_outstanding | market_cap_ty | lnst_ttm_ty | equity_ty | pe_daily | pe_vci | pb_daily | pb_vci`
- **industry_valuation.csv**: P/E, P/B cả ngành (gộp): `cap | nganh | date | so_ma | mcap_ty | so_ma_pe | lnst_ttm_ty | pe_nganh | so_ma_pb | equity_ty | pb_nganh`
- **snapshot.csv**: ảnh chụp hiện tại (giá, vốn hóa, số CP, room ngoại, % nhà nước, P/E, P/B, ROE).

---

## 3. CÔNG THỨC cap_pull (đã CHỐT, KHÓA — user xác nhận, đừng tự đổi)

```
vốn hóa(t)   = giá_điều_chỉnh(t) × SỐ CP HIỆN TẠI (issue_share, cố định mọi ngày)
P/E (pe_daily) = vốn hóa / NPATMI
                 NPATMI = attributable_to_parent_company (LN sau thuế cổ đông cty mẹ), TTM 4 quý
P/B (pb_daily) = vốn hóa / (owners_equity − minority_interests − minority_interests_before_2015)
```

### Các "viên gạch" theo quý (mốc hiệu lực = ngày cuối quý, asof backward ghép ra ngày):
- **Số CP**: dùng `issue_share` từ overview (HIỆN TẠI, cố định). (Có bảng số CP lịch sử `number_of_shares_mkt_cap` nhưng chỉ dùng fallback.)
- **LNST TTM**: dòng `attributable_to_parent_company`, reindex theo lưới quý liên tục (`qidx = year*4+q-1`) rồi `rolling(4).sum()`. **Thiếu quý → TTM = NaN** (không cộng nhầm 4 quý rời). **Quý ÂM vẫn cộng với dấu** (làm giảm tổng). **TTM ≤ 0 (lỗ) → pe_daily TRỐNG**.
- **VCSH công ty mẹ**: `owners_equity − minority_interests − minority_interests_before_2015`. **VCSH ≤ 0 → pb_daily trống**. (P/B vẫn tính khi LỖ vì VCSH dương.)
- **pe_vci/pb_vci**: lấy nguyên pe/pb VietcapIQ công bố (ratio_summary, quarter 1-4), forward-fill — **chỉ để đối chiếu**.

### Gộp cấp ngành (phương pháp AGGREGATE, KHÔNG phải bình quân tỷ số):
```
pe_nganh = Σ vốn_hóa(các mã có LNST hợp lệ) / Σ LNST    ← tử & mẫu CÙNG TẬP MÃ
pb_nganh = Σ vốn_hóa(các mã có VCSH hợp lệ) / Σ VCSH
```
Gộp ở cả 4 cấp ICB (cột `cap` = L1..L4). Cột `so_ma_pe`/`so_ma_pb` cho biết ngành gộp từ mấy mã hợp lệ. **Chỉ gộp các mã trong tickers.txt**, không phải toàn sàn.

---

## 4. CÁC QUYẾT ĐỊNH PHƯƠNG PHÁP (và lý do) — quan trọng để không làm lại

1. **P/E dùng LNST kế toán CÔNG TY MẸ** (không phải tổng, không phải "lợi nhuận đã thực hiện"):
   - Lý do: đồng nhất so sánh chéo các ngành. User chọn cái này thay vì khớp VCI.
   - Hệ quả: **P/E ngành chứng khoán cao hơn VCI ~15-20%** vì VCI dùng "lợi nhuận đã thực hiện" cho CTCK (loại lãi/lỗ đánh giá lại danh mục tự doanh chưa bán). **KHÔNG phải bug** — đã verify: SSI earn VCI ≈ TTM realized, ≠ TTM parent. Phát hiện CTCK qua dòng `realized_profit` (chỉ CTCK có).

2. **P/B dùng VCSH công ty mẹ** (trừ lợi ích cổ đông thiểu số) — khớp cách VCI tính, khớp pb_vci tại hiện tại.

3. **Vốn hóa = giá điều chỉnh × số CP HIỆN TẠI** (công thức user chốt):
   - VCI history CHỈ có giá đã điều chỉnh (endpoint `chart/OHLCChart/gap-chart`, không có param raw).
   - Đúng cho các sự kiện LÀM LOÃNG (cổ tức CP, chia tách, quyền mua chiết khấu) vì giá đc tự bù.
   - `close` = giá điều chỉnh; `shares_outstanding` = số CP hiện tại (cố định).

4. **Giá điều chỉnh** (không phải giá thô) cho định giá — vì VCI không cấp giá thô.

---

## 5. LỊCH SỬ DEBUG vốn hóa (để không lặp lại các ngõ cụt)

Vốn hóa từng bị tính sai, đã thử nhiều cách trước khi chốt:
1. **Cũ (bug gốc)**: `giá_đc × số CP LỊCH SỬ` → vốn hóa/P-E/P-B QUÁ KHỨ TỤT SAI (P/B < 1 giả tạo) với mã chia cổ tức CP (double-deflation: giá đc thấp + số CP lịch sử thấp). HPG 2019 lệch -65%, 2020 -82%.
2. **Thử neo theo `market_cap` quý của VCI** → SAI. Vì cột `market_cap` trong ratio_summary **không gắn ngày cuối quý** (lúc cao lúc thấp ±35-50%, không khớp giá×CP nào). ĐỪNG dùng cột này làm chuẩn.
3. **Thử hệ số factor từng quý** (factor = mcap_vci/CP/giá_đc) → SAI cùng lý do #2, lại vỡ khi pull khoảng ngắn (thiếu giá cuối quý).
4. **Thử overview-anchor** (mcap hôm nay × tỷ lệ giá) → ổn nhưng phức tạp, today lệch nhẹ.
5. **CHỐT**: `giá_đc × số CP hiện tại` (công thức đơn giản của user). Đúng về toán cho sự kiện làm loãng.

---

## 6. GIỚI HẠN VALID đã biết (user CHẤP NHẬN)

### Vấn đề chính còn lại — diễn đạt CHÍNH XÁC:
- Giá điều chỉnh ĐÃ xử lý sự kiện **làm loãng** (cổ tức CP, chia tách, quyền mua chiết khấu) → "giá đc × CP hiện tại" **ĐÚNG kể cả lịch sử**.
- **CHỈ SAI** (thổi phồng vốn hóa/P-E/P-B quá khứ xa) với phát hành **KHÔNG làm loãng** = bán CP bằng/sát **GIÁ THỊ TRƯỜNG** (chào bán riêng lẻ, ESOP). Giá không được adjust nhưng số CP vẫn tăng → dùng CP hiện tại cho quá khứ là dư. **Chủ yếu CK & NGÂN HÀNG.**
- **Dấu hiệu nhận diện**: VCSH tăng mạnh CÙNG LÚC số CP tăng mạnh (cổ tức CP KHÔNG làm tăng VCSH). Vd SSI: số CP 655tr→2.501tr & VCSH 11,4k→39,7k tỷ = đã thu tiền thật.
- **ĐỘ LỚN sai số KHÔNG xác định được** nếu thiếu giá thô. (Lần trước từng nói "SSI P/B 5,5 vs 3,5" — đó là ước lượng thô, ĐÃ ĐÍNH CHÍNH, đừng khẳng định con số cụ thể.)

### Các giới hạn nhỏ khác:
- **Cổ tức tiền mặt**: vốn hóa quá khứ thấp nhẹ (~vài %/năm cumulative) ở mã trả cổ tức tiền cao. Không khử được khi chỉ có giá đc.
- **Hôm nay lệch overview ~0,7%**: giá đóng cửa history trễ giá hiện tại overview. Cosmetic.
- **Độ trễ công bố BCTC (~30-45 ngày)**: LNST/VCSH gán theo ngày CUỐI QUÝ, nhưng DN công bố trễ → ~1-1,5 tháng đầu mỗi quý P/E dùng số thị trường chưa biết (look-ahead nhẹ). Khử được bằng `publicDate` — CHƯA làm.
- **pe_vci/pb_vci** quá khứ kém tin cậy (market_cap nền của VCI không nhất quán).

### Đánh giá tổng:
- ✅ ĐÁNG TIN: hiện tại + 1-2 năm gần (số CP ổn định), mọi mã; và mã tăng CP bằng cổ tức CP (sản xuất/tiêu dùng) cả lịch sử.
- ⚠️ DÈ CHỪNG: P/E, P/B **lịch sử xa của CK & ngân hàng**.

### 6b. RÀ SOÁT NHƯỢC ĐIỂM vs các bên cung cấp (vì sao quá khứ lệch) — đầy đủ:

**A. VỐN HÓA (tử số chung)** — lệch lớn nhất ở quá khứ (VCI chỉ có giá đã đc → tool dùng giá đc × CP hiện tại):
- A1. Phát hành KHÔNG làm loãng (chào bán/ESOP giá thị trường): giá không adjust mà CP tăng → vốn hóa quá khứ tool CAO hơn thực. (CK, NH)
- A2. Cổ tức tiền mặt: giá đc quá khứ bị hạ → vốn hóa quá khứ tool THẤP nhẹ.

**B. P/E (mẫu số lợi nhuận):**
- B1. Tool dùng LNST kế toán công ty mẹ; VCI/CafeF dùng "lợi nhuận đã thực hiện" cho CTCK → tool CAO ~15-20%, MỌI kỳ (CK & NH).
- B2. Mã có cổ đông thiểu số: tool dùng NPATMI (mẹ); vài bên dùng tổng LNST.
- B3. Gán LNST theo ngày cuối quý, công bố trễ ~30-45 ngày → ~1 tháng đầu quý lệch (look-ahead).

**C. P/B (mẫu số VCSH):**
- C1. Tool dùng VCSH công ty mẹ (trừ thiểu số); vài bên dùng tổng.
- C2. Lệch kỳ vốn-CP: số CP hiện tại + VCSH quý cũ (chưa có vốn vừa raise) → P/B sai khoảng giữa đợt raise và quý kế.

**Bản chất:** Tool TỰ NHẤT QUÁN (cùng cơ sở) → tốt để SO SÁNH NỘI BỘ (giữa mã, theo thời gian trong data của mình). KHÔNG khớp bên ngoài vì (1) mỗi bên quy ước khác, (2) dựng lại vốn hóa quá khứ từ giá đc là LOSSY (mất thông tin). Khử triệt để chỉ khi có GIÁ THÔ từng ngày × số CP từng kỳ.

**Lưu ý cho dev:** đừng "sửa" để khớp 1 bên cụ thể — sẽ phá tính nhất quán nội bộ và phá khớp với bên khác. Mỗi bên (VCI/CafeF/Vietstock) ra số khác nhau. HCM là ca SẠCH (CP ổn định từ 2025-Q1) → tool khớp VCI tuyệt đối (mcap 30.617, P/B 2.13); dùng HCM làm ca kiểm thử "đúng".

---

## 7. RATE LIMIT & kỹ thuật

- vnstock community giới hạn **20 request/phút** (lớp `vnai`, file `vnai/beam/quota.py`, tier default min=20/hour=1200/day=28800). Khi chạm trần, `CleanErrorContext.__exit__` gọi `sys.exit()` → raise **SystemExit** (KHÔNG phải Exception) nên try/except Exception thường không bắt được, chết cả batch.
- **Fix**: `_pacer.py` (dùng chung): class `Pacer` giữ nhịp < 18 req/phút (rolling 60s, gọi `pacer.wait(weight)` trước mỗi mã) + `call_with_retry` bắt cả SystemExit lẫn Exception có "rate limit", chờ 62s thử lại. Weight: cap_pull=5, fs_pull=7, liq=1.
- **Tốc độ thực**: cap ~4-5 mã/phút (100 mã ~22 phút), fs ~2-3 mã/phút (~40 phút), liq nhanh.
- **BỎ RATE LIMIT hoàn toàn (nếu cần sau này)**: giới hạn là của lớp vnai, KHÔNG phải server. Gọi THẲNG REST API VCI bằng `requests` thuần = không bị chặn (đã test 30 req/26s/0 lỗi). base_url=`https://iq.vietcap.com.vn/api/iq-insight-service`, headers lấy từ `Finance(...).headers`. Endpoint: `/v1/company/{T}/financial-statement?section=INCOME_STATEMENT|BALANCE_SHEET|CASH_FLOW|NOTE`, `/v1/company/{T}/statistics-financial` (vốn hóa/PE), mapping `/v1/company/financialratio`. Đổi lại phải tự parse field code thô. **User 6/2026 CHỌN GIỮ pacer** (ổn định) — đừng tự rewrite.
- **Rủi ro bảo trì**: tool gọi hàm NỘI BỘ vnstock (`_get_report`, `_get_ratio_dict`, `ratio_summary`...). `pip install vnstock -U` lên bản mới có thể đổi tên/cấu trúc → phải sửa.

---

## 8. CÁCH CHẠY (tóm tắt)

```powershell
$env:PYTHONIOENCODING='utf-8'
cd D:\bctc\fs-extractor

# Tra cứu ngành
python fsx.py nganh "van tai"
# BCTC — theo mã hoặc theo ngành
python fsx.py bctc HAH GMD VSC --period quarter --from 2020-Q1 --out output
python fsx.py bctc --nganh "Ngân hàng" --period quarter --from 2020-Q1
# Thanh khoản index
python fsx.py liq --from 2020-01-01 --out output_liq
# Vốn hóa + P/E + P/B
python fsx.py cap --nganh "van tai thuy" --san HOSE --from 2020-01-01 --out output_cap
```
Hoặc double-click run.bat (menu 1/2/3/4; hỏi ngành trước, Enter = dùng tickers.txt).
Mỗi lần chạy GHI ĐÈ output\. Muốn giữ bản cũ thì đổi tên thư mục trước khi chạy (tool luôn kéo full mới nhất, xử lý đúng số hồi tố/restate).

---

## 9. TRẠNG THÁI HIỆN TẠI & VIỆC CÒN LẠI

### Đã xong & verify:
- 3 pipeline chạy ổn, có phân ngành, date range, chống rate-limit.
- Logic P/E, P/B audit khớp tính tay tuyệt đối (HAH/GMD/SSI), nhất quán nội bộ (pe/pb = VCSH/LNST), xử lý lỗ đúng, chọn đúng quý theo ngày, gộp ngành đúng (aggregate).

### Việc lớn nhất còn lại (nếu user yêu cầu):
- **Bổ sung nguồn GIÁ THÔ từng ngày** (vd scrape CafeF) để nhân với số CP TỪNG KỲ → khử triệt để cả lỗi #6 (CK/NH phát hành thị giá) lẫn cổ tức tiền → P/E/P/B lịch sử chuẩn mọi ngành mọi thời kỳ. Đây là việc lớn nhất; các thứ khác nhỏ hoặc đã chấp nhận.
- (Tùy chọn) Khử look-ahead bằng `publicDate` thay vì ngày cuối quý.

---

## 10. Tham chiếu memory liên quan
- `fs-extractor-tool.md` (memory chính của tool này — chứa toàn bộ chi tiết kỹ thuật).
- Các tool cùng workflow của user: `md2bctc` (BCTC Markdown OCR → CSV), `pdf-detector`, `markitdown-tool`, `vhbs-contex-pipeline`, `haian-schedule-pipeline`.
