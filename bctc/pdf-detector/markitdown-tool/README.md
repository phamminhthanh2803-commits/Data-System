# PDF → Markdown tool (markitdown + OCR Tesseract)

Convert hàng loạt PDF sang Markdown. Tự OCR trang scan (tiếng Việt + Anh), dựng bảng thẳng cột, chạy song song theo trang.

**Vị trí:** `D:\bctc\pdf-detector\markitdown-tool\`

---

## 1. DÙNG NHANH

Double-click **`Dan-duong-dan.bat`** → dán đường dẫn 1 **file** `.pdf` hoặc 1 **thư mục** → Enter.
- Dán kèm dấu `"..."` cũng được (Shift + chuột phải → *Copy as path*).
- Xong nó hỏi tiếp → dán cái khác để làm nữa, hoặc để trống + Enter để thoát.
- Dán thư mục → tự convert hết (đệ quy). File `.md` xuất **cạnh** file PDF gốc.

## 2. DÙNG NÂNG CAO (PowerShell — khi cần đổi tùy chọn)

```powershell
python "D:\bctc\pdf-detector\markitdown-tool\pdf2md.py" "<đường dẫn>" [tùy chọn]
```

| Tùy chọn | Ý nghĩa |
|---|---|
| `-r` | quét cả thư mục con |
| `-o "DIR"` | thư mục xuất .md (mặc định: cạnh file PDF) |
| `-f` | ghi đè .md đã có (mặc định: bỏ qua) |
| `-j N` | số trang OCR song song (mặc định ~3/4 luồng CPU) |
| `--ocr auto` | (mặc định) trang có chữ lấy thẳng, trang scan mới OCR |
| `--ocr force` | OCR mọi trang (scan thuần ra rỗng thì dùng cái này) |
| `--ocr off` | chỉ markitdown, không OCR (nhanh nhất, PDF có sẵn chữ) |
| `-l vie+eng` | ngôn ngữ OCR |
| `--dpi 300` | độ nét OCR — `250` nhanh hơn ~30%, `350-400` nét hơn |
| `--psm 6` | chế độ phân vùng trang Tesseract |
| `--layout on` | (mặc định) dựng bảng thẳng cột + bọc code-block; `off` = OCR thường |

**Ví dụ:**
```powershell
python "...\pdf2md.py" "D:\Scan" -r --dpi 250        # khối lượng lớn, ưu tiên tốc độ
python "...\pdf2md.py" "D:\file.pdf" --ocr force      # 1 file scan thuần
python "...\pdf2md.py" "D:\TaiLieu" -r --ocr off      # PDF có sẵn chữ, bỏ OCR
```

## 3. MẸO KHỐI LƯỢNG LỚN
- **Đứt giữa chừng cứ chạy lại**: file `.md` đã có tự bỏ qua, làm tiếp phần thiếu (đừng thêm `-f`).
- Tốc độ tham khảo: scan ~40 trang/phút → 1.000 trang ≈ 25 phút.
- Trỏ vào thư mục cha + `-r` là quét hết mọi thư mục con.

---

## 4. CONTEXT KỸ THUẬT (để bảo trì / nhờ Claude sau này)

**Tool gồm 3 phần:**
- `pdf2md.py` — script chính (Python 3.12).
- `Dan-duong-dan.bat` — entry dán-đường-dẫn; gọi `pdf2md.py` qua `%~dp0` nên **di chuyển cả thư mục đi đâu cũng chạy**.
- `tessdata\` — `vie` + `eng` + `osd` traineddata kèm theo tool.

**Phụ thuộc (cài mức hệ thống, không nằm trong thư mục):**
- `pip`: `markitdown[pdf]`, `pytesseract`, `pypdfium2`
- Tesseract OCR v5.5 ở `C:\Program Files\Tesseract-OCR\` (cài bằng winget `UB-Mannheim.TesseractOCR`).

**Quyết định thiết kế quan trọng:**
- markitdown thuần **KHÔNG OCR** → PDF scan (không có lớp text) sẽ ra rỗng. Vì vậy mới tự thêm OCR bằng pypdfium2 (render trang) + Tesseract.
- Trỏ tessdata qua biến môi trường **`TESSDATA_PREFIX`**, KHÔNG dùng `--tessdata-dir` (pytesseract cắt config theo dấu cách → path có khoảng trắng bị hỏng).
- **Tốc độ:** song song theo TRANG bằng 1 pool OCR dùng chung (`OcrEngine`) + semaphore chặn tràn RAM; vài luồng render đẩy việc vào pool → nhanh cả khi 1 file lớn lẫn nhiều file nhỏ. Tắt đa luồng nội bộ Tesseract (`OMP_THREAD_LIMIT=1`) để tự song song ngoài. Benchmark: HAH 58 trang scan từ 578s (tuần tự) → 84s (~6.9x).
- **Bảng:** `--layout on` dựng lại dòng theo toạ độ x của chữ (`image_to_data`/TSV) rồi bọc ` ```text ` → số trong bảng tài chính thẳng cột, Markdown giữ căn lề.
- Console Windows ép UTF-8 để in tiếng Việt (tránh lỗi cp1252).

**Hạn chế:** Tesseract miễn phí nên chữ nhỏ/mờ còn sai vặt. Muốn chính xác cao hơn phải dùng backend trả phí của markitdown (Azure Document Intelligence `-d -e endpoint`, Azure Content Understanding, hoặc LLM Vision) — cần credentials, chưa tích hợp.

**Lưu ý môi trường:** sandbox của Claude Code overlay thư mục project (`D:\Microsoft VS Code`) nên file tạo trong đó không persist ra đĩa thật; vì vậy tool đặt NGOÀI project (giờ ở `D:\bctc\pdf-detector\`). Khi nhờ Claude sửa file đĩa thật, dùng PowerShell với `dangerouslyDisableSandbox`.
