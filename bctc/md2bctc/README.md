# md2bctc — BCTC Markdown (CTCK) → CSV

Chuyển báo cáo tài chính dạng **Markdown đã OCR** của **công ty chứng khoán** (mẫu `B0x-CTCK`)
thành **CSV long-format + metadata** để tra cứu / lookup / SQL.

Parse **thuần Python regex**, không cần API/internet.

## Cách dùng

**Dán đường dẫn (khuyến nghị):** chạy `Dan-duong-dan.bat`, dán đường dẫn **1 file `.md`** hoặc
**1 thư mục** (xử lý mọi `.md` trong đó) rồi Enter. Mẹo: Shift + chuột phải → "Copy as path".

**Kéo-thả:** kéo 1 hoặc nhiều file `.md` vào `KEO-THA_FILE_MD_VAO_DAY.bat` (vẫn dùng được).

**Dòng lệnh:**
```
python md2bctc.py "duong_dan" [-r] [--ticker SSI] [--year 2016] [--wide]
```
- `input`: **1+ file `.md` HOẶC thư mục**. Thư mục → tự quét `*.md`; thêm `-r` để quét cả thư mục con.
- Mỗi file lỗi không làm dừng batch (in `! LOI` rồi chạy tiếp); cuối in `# HOAN TAT: N OK, M loi`.
- `--ticker`: bỏ trống → đoán từ tên thư mục cha (`...\SSI\file.md` → `SSI`).
- `--year` : bỏ trống → tự đọc ("tại ngày..." ưu tiên, rồi "31 tháng 12...").
- `--master`/`--notes`: đường dẫn 2 file tổng (mặc định trong `D:\bctc\md2bctc\`).
- `--wide` : (tùy chọn) xuất thêm `output\<TICKER>_<YEAR>_bctc_wide.csv`.
- `--no-notes`: bỏ trích thuyết minh.

> Ví dụ batch cả thư mục: `python md2bctc.py "D:\bctc\pdf-detector\downloads\SSI"`
> → 150 file, 0 lỗi, dồn vào `bctc_master.csv` + `bctc_notes.csv` (upsert theo `source_file`).

## Đầu ra — 2 FILE TỔNG cộng dồn nhiều ticker

| File | Nội dung |
|---|---|
| `bctc_master.csv` | **4 báo cáo chính** (B01/B02/B03/B04), long-format |
| `bctc_notes.csv`  | **Thuyết minh** (B05/B06), long-format, theo `note_no` + `note_title` |

- Mỗi lần chạy 1 file `.md` sẽ **cộng dồn** dữ liệu vào cả 2 file tổng.
- **Upsert theo `source_file`** (mỗi file `.md` = 1 báo cáo): chạy lại **cùng file** sẽ thay thế
  dòng cũ của chính nó; các file khác **giữ nguyên** — kể cả cùng ticker/năm (vd annual vs quý,
  hợp nhất vs riêng lẻ) cũng **không đè mất nhau**.
- Kéo-thả nhiều file của nhiều mã → dồn hết về 2 bảng để query (lọc bằng `source_file` nếu cần
  tách từng báo cáo).

### Cột `bctc_master.csv`
`ticker, fiscal_year, period_label, consolidated, currency, statement, ma_so, chi_tieu, thuyet_minh, period, period_desc, value, flag, quality, raw, source_file`

### Cột `bctc_notes.csv`
`ticker, fiscal_year, period_label, consolidated, currency, note_no, note_no_raw, note_title, chi_tieu, period, value, flag, quality, raw, source_file`

### Kỳ báo cáo — cột `period_label` (năm / quý)
- `FY` = báo cáo **năm**; `Q1`..`Q4` = báo cáo **quý** (nhận từ "Quý N năm 20xx", hỗ trợ cả số La Mã).
- Phân biệt các quý cùng năm: `WHERE fiscal_year=2015 AND period_label='Q4'`.
- **KQKD báo cáo quý** có 4 cột → `period` được gán nghĩa:
  `quy_current` (quý này, năm nay) · `quy_prior` (quý này, năm trước) ·
  `ytd_current` (lũy kế, năm nay) · `ytd_prior` (lũy kế, năm trước).
  (CĐKT/LCTT quý vẫn 2 cột `current`/`prior`.)

### Cột `quality` — clean / dirty (để lọc dòng cần soi/sửa)
Có ở **cả 2 file**. `WHERE quality='dirty'` để ra danh sách cần kiểm tra tay.
- **dirty** khi có ≥1 dấu hiệu lỗi (lý do ghi trong `flag`):
  - `formula_mismatch` — **dòng tổng KHÔNG khớp công thức nhúng** (vd `100=110+130`) → gần như chắc chắn OCR sai 1 chữ số ở ô này
  - `huge_value` — số ≥ 10¹⁵ (nghi dính 2 cột)
  - `overflow` — nhiều số hơn số cột (lệch bảng)
  - `no_label` / `garbage_label` — nhãn rỗng hoặc lẫn rác OCR (`§ = — ñ`…, đuôi toàn chữ cái lẻ)
  - `check_n_amount` — số cột số bất thường
  - `b04_besteffort` — mọi dòng B04 (Biến động VCSH, cả bảng kém tin cậy)
- **clean** = còn lại. **Lưu ý:** bảng ma trận parse đúng (vd Note 7.1) vẫn là **clean** —
  `wide_check` (đánh dấu "bảng nhiều cột") KHÔNG tự động bị coi là dirty.

### Đối chiếu chéo bằng công thức nhúng (tăng độ chính xác)
Nhiều dòng tổng có công thức trong nhãn: `(100 = 110 + 130)`, `(270=100+200)`, `(440=300+400+430)`.
Tool tự kiểm tra `value(tổng) == Σ value(các mã con)` cùng kỳ. Lệch → gắn `formula_mismatch`
vào **đúng** dòng tổng đó (pinpoint ô OCR sai), in `Cong thuc nhung: khop X, LECH Y` ra console.
Trên bộ SSI: **~91% công thức khớp**; phần lệch đều là OCR đọc sai 1 chữ số (vd tổng 43.xxx vs 13.xxx).

- `period`: `current`/`prior` (bảng 2 cột) hoặc `col1..colN` (bảng ma trận nhiều cột — vd Note 7.x: Giá gốc/Giá trị ghi sổ/Giá trị hợp lý × 2 kỳ).
- Bảng ma trận gắn cờ `wide_check`; đoạn **text diễn giải thuần** (chính sách kế toán...) **không** trích.
- `note_no_raw` = số mục OCR gốc; `note_no` = sau khi chuẩn hóa (xem dưới).
- Tắt trích thuyết minh: thêm cờ `--no-notes`.

### Thuật toán parse Thuyết minh (position-based)
1. **Cắt mục** theo dòng tiêu đề; gộp các trang "(tiếp theo)" cùng mục thành 1 bảng.
2. **Chuẩn hóa `note_no`** (mục TM chỉ tới ~45): 3 chữ số `281`→`28.1`, `441`→`44.1`;
   2 chữ số > 50 `71`→`7.1`, `75`→`7.5`. Số ≤ 50 giữ nguyên.
   ⚠️ OCR sai kiểu `40`(=10), `47`(=17), `41`(=11) **không tự sửa được** → **tra theo `note_title`**.
3. **Gán cột theo TỌA ĐỘ**: tính mốc vị trí từ các dòng đầy đủ, gán mỗi số vào cột gần nhất
   (đơn điệu trái→phải) → **ô trống `-`/`=`/khoảng trắng được giữ đúng vị trí**, không bị dồn lệch.
4. Nhãn xuống nhiều dòng được gộp; bỏ dòng tiêu đề cột; bỏ phần footnote `(1)/(*)/[1]` cuối mục.

### Giới hạn đã biết (note)
- Bảng OCR quá nát vẫn sai (vd **28.2** vốn CSH 11 cột; **note 9** dòng tổng OCR `/` thay `.`;
  **note 35** "lãi thanh lý" mất 1 dấu chấm) — đều mang cờ `wide_check`/lệch, cần soi `raw`.
- Một số mục có 2 bảng con khác số cột (vd **note 12**: rollforward 5 cột + bảng phụ 2 cột) →
  trong cùng `note_no` sẽ thấy cả `colX` lẫn `current/prior`, đây là **bình thường**.
- Cột phi-tiền (số lượng CP ở 28.4, ngoại tệ 29.1, % ở note 11/20, lãi cơ bản 43) **vẫn được
  trích vào `value`** (chép trung thực) — dựa `note_title` để biết đơn vị thực.

- `statement`: `balance_sheet` | `income_statement` | `cash_flow` | `cash_flow_client` | `equity_changes`
- `period`: `current` (cuối kỳ/năm nay) | `prior` (đầu kỳ/năm trước) | `col1..colN` (riêng B04 bảng rộng)
- `value`: số nguyên VND (số âm để dấu trừ; rỗng nếu cột gốc là `-`)
- `flag`: rỗng nếu chắc chắn; `check_n_amount=k` nếu số cột số khác 2 (cần soi); `wide_check` cho mọi dòng B04
- `raw`: 1-2 dòng OCR gốc (chỉ ghi khi có `flag`) để đối chiếu nhanh

## Format hỗ trợ (tự nhận diện theo TIÊU ĐỀ)
Tool nhận format theo **tiêu đề báo cáo** (KHÔNG theo mã `B0x` ở góc — vì BCTC cũ cũng có mã B0x
và OCR hay ghi sai):

| Format | Tiêu đề nhận diện | Phạm vi |
|---|---|---|
| **TT210/2016** (mới) | "BÁO CÁO TÌNH HÌNH TÀI CHÍNH" | 4 BC chính **+ Thuyết minh** (đầy đủ) |
| **TT95-96/2008 (cũ) + DN thường (TT200, B09-DN)** | "BẢNG CÂN ĐỐI KẾ TOÁN" | 4 BC chính (BS/IS/CF/VCSH) **+ Thuyết minh** |
| **BC tỷ lệ ATTC** (TT226/2010) | "BÁO CÁO TỶ LỆ AN TOÀN TÀI CHÍNH" | bảng chính (`statement=safety_ratio`) **+ Thuyết minh** |

- New-format: gom trang theo tiêu đề; nếu **mã số ở ĐẦU dòng** (TT334) dùng parser chuẩn,
  nếu **mã số ở GIỮA dòng** (TT210 quý) tự chuyển sang parser position-based.

## Kiểm tra consistency (nhiều file)
Chạy `python test_all.py` để quét **mọi** file `.md`, in bảng (format/năm/kỳ/số dòng/cân đối/
clean-dirty) + tally. Dùng để soi nhanh file lỗi:
- **balance LECH** = Tổng tài sản ≠ Nợ + Vốn CSH → thường do **OCR đọc sai 1 chữ số** ở dòng tổng
  (vd Tổng TS 13.**3**97 tỷ vs Tổng NV 13.**5**97 tỷ) → file cần đối chiếu tay, không phải lỗi tool.
- **explosion / 0-rows** = file OCR text-layer quá kém (cũ 2009-2011) hoặc không phải BCTC.

- **BC tỷ lệ an toàn tài chính** (không phải BCTC): bảng chính 5 chỉ tiêu số (rủi ro thị trường/
  thanh toán/hoạt động, tổng rủi ro, vốn khả dụng) → `statement=safety_ratio`, 1 kỳ (`period=current`),
  có `ma_so`=STT + `thuyet_minh`. Thuyết minh đi vào `bctc_notes.csv`.
  Dòng **Tỷ lệ an toàn (%)** không trích (là %, tự tính = vốn khả dụng / tổng giá trị rủi ro).

- Format cũ dùng **position-based** nên chịu được số cột thay đổi: CĐKT/LCTT **2 cột**;
  KQKD **báo cáo quý 4 cột** (`col1`=quý nămnay, `col2`=quý nămtrước, `col3`=lũy kế nămnay, `col4`=lũy kế nămtrước).
- `ma_so` ở format cũ nằm GIỮA dòng (sau tên chỉ tiêu) → tool tự bóc.
- ⚠️ Nhiều BCTC cũ OCR **text-layer rất kém** (chữ/số lẫn lộn) → kết quả best-effort, nhiều dòng `dirty`.
- File **KHÔNG phải BCTC** (vd "Báo cáo tỷ lệ an toàn tài chính", "Báo cáo thu nhập toàn diện" lẻ)
  → ra **0 dòng** (không tạo data sai).

## Báo cáo nhận diện (TT334/2016)
- `B01-CTCK` → Bảng cân đối (balance_sheet) — vào `bctc_master.csv`
- `B02-CTCK` → Kết quả hoạt động (income_statement) — vào `bctc_master.csv`
- `B03/B03b-CTCK` → Lưu chuyển tiền tệ (cash_flow) + phần khách hàng (cash_flow_client) — `bctc_master.csv`
- `B04-CTCK` → Biến động vốn CSH (equity_changes) — **bảng rộng, best-effort, mọi dòng đều `wide_check`** — `bctc_master.csv`
- `B05/B06` (Thuyết minh) → trích số liệu vào `bctc_notes.csv` (best-effort, bỏ text thuần)

## Xử lý lỗi OCR đã cài
- Dấu `,` dùng nhầm cho dấu ngăn nghìn (`11.884,989.070.539` → `11884989070539`)
- Số bị chèn khoảng trắng / double-dot (`4.847 .340.451`, `9..598.969.134`)
- 1 space đơn được coi là dấu ngăn nghìn, nhưng **2 space liền = ranh giới cột**
  (vd `...818  214.303...` là 2 cột, không bị nối thành 1 số)
- Thừa chữ số ở đuôi nhóm (`134.075.3311` → `134.075.331`, regex chỉ ăn nhóm đúng 3 số)
- Ký tự OCR `§` → `5`
- Số âm trong ngoặc `(...)`
- Mã số con OCR dính liền 4 số (`1111` → `111.1`)
- Dòng "TỔNG CỘNG TÀI SẢN / NGUỒN VỐN" không có mã số
- Cột giá trị là `-` (rỗng): xác định số thuộc cột đầu/cuối kỳ theo vị trí (position-based)
- Bỏ qua header/footer/chữ ký lặp ở mỗi trang

## Tự kiểm tra (in ra console)
Sau khi chạy, tool kiểm tra **đẳng thức kế toán** cho cả 2 kỳ:
`Tổng tài sản = Nợ phải trả (300) + Vốn CSH (400)`.
Nếu báo `LECH` → có khả năng lỗi OCR ở số liệu, xem cột `flag`/`raw` và file `.md` gốc.

> Lưu ý: tool **chép trung thực** số từ OCR. Một vài ô có thể sai do bản OCR sai
> (vd dòng tổng "Nguồn vốn" của SSI 2016 bị OCR `43...` thay vì `13...`).
> Luôn đối chiếu các dòng có `flag` và các dòng tổng quan trọng.


## Cập nhật 14/09/2026 — gộp vào hub
Thư mục dời sang `D:\bctc\md2bctc` (cụm BCTC). Chuỗi 1 lệnh tải PDF → OCR → CSV: `python D:\bctc\pdf_to_bctc.py --ticker X --url U`; gộp nguồn: `D:\bctc\bctc_normalize.py`.
