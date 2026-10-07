# vimawa-sanluong — Sản lượng hàng hóa thông qua cảng biển (Cục Hàng hải và Đường thủy VN)

Kéo toàn bộ biểu **"Thống kê khối lượng hàng hóa thông qua cảng biển"** (Biểu 28-T / 07-T) đăng ở
<https://vimawa.gov.vn/vi/thong-ke>, parse và gộp thành **1 CSV tổng** `data\vimawa_sanluong.csv`.

## Chạy

```
python vimawa_sanluong.py              # dò bài mới, tải, parse lại toàn bộ, ghi CSV (~40s, OCR đã cache)
python vimawa_sanluong.py --full       # duyệt hết 8 trang danh sách
python vimawa_sanluong.py --force      # tải lại mọi file + OCR lại (~10 phút)
python vimawa_sanluong.py --no-fetch   # không vào mạng, chỉ parse lại raw\
python vimawa_sanluong.py --ocr off    # bỏ qua PDF scan
```

Cần: `requests lxml python-docx openpyxl pdfplumber pymupdf pytesseract pillow numpy` + Tesseract
(`C:\Program Files\Tesseract-OCR`, tessdata vie/eng lấy ở `D:\bctc\pdf-detector\markitdown-tool\tessdata`).

## Nguồn: cùng 1 mẫu biểu, 5 kiểu file

| Thời kỳ | Định dạng | Cách đọc |
|---|---|---|
| 2024 → nay | `.docx` 1 bảng | python-docx |
| 1–6/2026, 6–12/2025 | `.xlsx` "Biểu 28-20xx BC Bộ" nhiều sheet T1..T12 + Năm | openpyxl, kỳ lấy từ tiêu đề trong sheet (`nguon_loai = xlsx-bieu28`) |
| 7–12/2021, 2022, 1–3/2023 | `.pdf` có lớp text | bảng pdfplumber; T2, T3/2022 pdfplumber không dựng được bảng → lấy chữ lớp text xếp theo biên cột dò từ đường kẻ |
| 1–5/2021, 4–11/2023 | `.pdf` ảnh scan / ảnh chụp màn hình | OCR Tesseract **từng ô** (`pdf-ocr`) |
| 2018, 2020 | `.xlsx` 1 sheet | openpyxl |
| 2015 (T2, T3), 11/2016 – 6/2018 | bảng HTML trong bài | lxml, lưu `raw\<slug>__inline.html` |

Không có trên web: 4/2015–10/2016 (bài rỗng), 7/2018–12/2019, 9/2021, 1/2022, 5/2024.
T6/2021: PDF chỉ có công văn + Phụ lục II (biểu theo khu vực), **không có Biểu 28-T** → không parse.
Bài "Tàu thuyền ra, vào cảng biển", "Năng lực thông qua cảng" là biểu khác → bỏ qua (`kind = bieu-khac/empty`).

## Cột của `vimawa_sanluong.csv`

1 dòng = **kỳ × chỉ tiêu × đơn vị** (22 dòng/kỳ). Đơn vị gốc: **1000 tấn / 1000 TEU**.

| Cột | Ý nghĩa |
|---|---|
| `period`, `ky_loai`, `nam`, `thang` | `2026-08` (tháng) hoặc `2025` (biểu năm, `ky_loai = nam`) |
| `ngay_bao_cao` | "Ngày báo cáo" ghi trong biểu (thường ngày 15 của tháng) |
| `nhom` | `tong`, `container`, `hang_long`, `hang_kho`, `qua_canh` |
| `chieu` | `tong`, `xuat_khau`, `nhap_khau`, `noi_dia`, `qua_canh_boc_do` |
| `chi_tieu`, `nhan_goc` | tên chuẩn hoá / nhãn gốc trong văn bản |
| `ke_hoach_nam` | cột 1 |
| `luy_ke_thang_truoc` | cột 2 — lũy kế từ đầu năm đến hết tháng trước (**số thực hiện**) |
| `thang_bao_cao` | cột 3 — **ƯỚC** thực hiện tháng báo cáo |
| `luy_ke` | cột 4 — lũy kế đến hết tháng báo cáo (= cột 2 + cột 3); biểu năm: thực hiện năm |
| `luy_ke_cung_ky` | cột 5 — lũy kế cùng kỳ năm trước; biểu năm: thực hiện năm trước |
| `yoy_pct`, `pct_ke_hoach` | cột 6, 7 (đơn vị %, 118 = 118%) |
| `thang_thuc_te` | **suy ra**: cột 2 của kỳ sau − cột 2 của kỳ này (T12: số năm − cột 2 T12). Trống nếu thiếu kỳ sau |
| `nguon_loai`, `nguon_file`, `sheet`, `url` | truy vết |
| `ghi_chu` | dòng "Ghi chú" của biểu (có/không gồm hàng quá cảnh không bốc dỡ — **đổi theo từng kỳ**) |
| `canh_bao` | lệch số học trong biểu, ô đã sửa theo số học, tháng suy ra lệch ước >35% |

### Lưu ý khi dùng số

- **Cột 3 chỉ là ước** lập ngày 15, nhiều kỳ = cột 2 / số tháng đã qua. Muốn sản lượng tháng thực → dùng `thang_thuc_te`.
- **Phạm vi thống kê đổi giữa chừng**: từ T4/2025 kế hoạch năm nhảy 925.705 → 1.064.879 (gộp cảng thủy nội địa sau sáp nhập
  Cục HH & ĐTNĐ); 2026 là 1.300.382. `thang_thuc_te` vắt qua điểm đổi phạm vi sẽ sai (T3/2025 = 122.509) → có `canh_bao`.
  Tương tự T7→T8/2026 (cột 2 T8 = 735.656 trong khi cột 4 T7 = 797.469).
- Bản thân nguồn có ô lệch (copy công thức cũ): vd T1/2024 Hàng lỏng/khô, T11/2024 Hàng lỏng, cột cùng kỳ T12 các năm.
  Tool **giữ nguyên số nguồn** với docx/xlsx/pdf text, chỉ ghi `canh_bao`.
- `ke_hoach_nam` trong nguồn có kỳ ghi số năm cũ (7–11/2024 ghi 725.367) → lấy mode theo năm nếu cần.

## Chọn phiên bản khi 1 kỳ có nhiều nguồn

`vimawa_sanluong_all.csv` giữ mọi phiên bản (cột `chon` = 1 là bản vào master). Thứ tự ưu tiên: file riêng của kỳ
(docx/pdf/xlsx/html) > sheet trong Biểu 28 gộp; rồi ít cảnh báo hơn; rồi bài đăng mới hơn.
Sheet Biểu 28 của các tháng *sau* kỳ bài đăng là số ước chạy công thức (vd sheet T7-2026 trong file "đến tháng 6/2026").

## OCR PDF scan

1. Ảnh trang: scan 300dpi render bằng pymupdf; ảnh chụp màn hình 2023 (chỉ ~600px) dùng **ảnh gốc**, không phóng trước.
2. `deskew` theo đường kẻ ngang → dò đường kẻ dọc/ngang (chuỗi điểm tối dài) = biên cột/dòng → xoá đường kẻ + gạch chân.
3. Cột nhãn = cột rộng nhất trong 2 cột đầu; 7 cột số kế tiếp; cột thừa bên phải (T7/2023) bỏ.
   Dòng "Tổng số" neo theo nhãn / dòng "A B C"; 23 dòng sau theo `TEMPLATE` (thứ tự dòng cố định của biểu).
4. Mỗi ô số OCR 5 biến thể (phóng cho chữ cao 28/36px, lanczos/bicubic, có/không sharpen), whitelist `0-9 . , %`,
   bỏ phiếu + chọn bộ (cột 2, 3, 4) thoả `cột 2 + cột 3 = cột 4`; cột 5 chọn theo `tổng nhóm = xuất + nhập + nội địa`.
   **Phóng quá tay làm Tesseract nhầm 5↔3, 8↔3** — đừng tăng scale.
5. `repair_ocr`: ô còn lệch mà 2 ràng buộc độc lập (dòng + cột) cùng chỉ ra thì sửa, ghi `canh_bao = sua theo so hoc ...`.
6. Cache `raw\ocr\<file>.json` (xoá file cache hoặc `--force` để OCR lại).

Đã kiểm: T4/2023 và T2/2021 khớp 100% khi soi ảnh; 238 ô `luy_ke` OCR đối chiếu với `luy_ke_cung_ky` năm sau (nguồn text)
chỉ 7 ô lệch >15%, đều là dòng quá cảnh nhỏ do nguồn điều chỉnh.

## File phụ

- `period_overrides.csv` — `slug,period`: ép kỳ cho bài không ghi năm. Hiện có 2 bài cũ nhất "T2", "- T 3" gán **2015**
  (suy từ kế hoạch năm 407.349 và vị trí trong danh sách — nếu sai sửa ở đây).
- `data\vimawa_index.csv` — danh sách 112 bài + file đã tải; bài đã có trong index không tải lại (trừ `--force`).

## Thêm vào lịch (chưa gắn)

Biểu ra 1 lần/tháng (sau ngày 15). Nếu muốn chạy tự động, thêm vào `$Steps` của `D:\shipping\Run-Shipping.ps1`:

```
@{ Slot='AM'; Name='vimawa'; Kind='py'; Script=(Join-Path $Root 'vimawa-sanluong\vimawa_sanluong.py'); When=$isMon }
```
