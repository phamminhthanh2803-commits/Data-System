# PDF Detector — Tóm tắt quá trình cập nhật

*Cập nhật: 2026-06-29*

Tài liệu tóm tắt những gì đã làm trong đợt nâng cấp. Chi tiết kỹ thuật xem [CONTEXT-HANDOFF.md](CONTEXT-HANDOFF.md).

---

## 1. Mở rộng từ 3 → 9 chế độ (thêm nhiều CTCK)

Ban đầu tool có 3 chế độ: `static` (haiants), `masvn`, `kafi`. Đã khảo sát và thêm hỗ trợ cho hàng loạt công ty chứng khoán:

| CTCK | Chế độ | Cơ chế phát hiện |
|------|--------|------------------|
| **SSI** | static | HTML tĩnh, `?page=N`, PDF inline |
| **VIX** | static | HTML tĩnh, `?page=N` |
| **TCSC** | static (path) | phân trang kiểu đường dẫn `/page-N/` → thêm placeholder `{page}` |
| **HSC** | static | HTML tĩnh, `?page=N`, PDF trên Google Cloud Storage |
| **VDSC** | vdsc | link tải endpoint id (không đuôi `.pdf`) → thêm `extra_pdf_patterns` |
| **SHS** | shs | Nuxt SPA → API Strapi same-origin `/api/shareholders/periodic-report` |
| **MBS** | mbs | WordPress **2 tầng** (list → trang chi tiết → PDF), path `/page/N/` |
| **BSC** | bsc | WordPress, list `data-id` → **POST admin-ajax** `get_content_qhcd` lấy PDF |
| **Pinetree** | pinetree | WordPress 2 tầng, bài `/post/<ngày>/<slug>/` → PDF |
| **BVSC** | bvsc | 2 tầng, list 1 trang → bài `/danhsachbaiviet/<slug>/` → PDF `/media/` |
| **GEL** (Gelex Infra) | gel | WordPress, PDF **inline** (`wp-content/uploads`), "phân trang" = **bộ lọc NĂM** `?y=<term_id>` đọc từ `ul.nav-year` → duyệt full lịch sử các năm |

**Cơ chế dùng chung:** thêm khả năng **2 tầng** (`follow_detail_re` + `find_detail_links()`) cho mbs/pinetree/bvsc; thêm **phân trang kiểu path** (placeholder `{page}`); thêm nhận diện **link tải không đuôi .pdf**.

**Bài học quan trọng (MBS):** đừng vội kết luận "cần Playwright". Cloudflare của MBS chỉ chặn POST admin-ajax, KHÔNG chặn GET — trang thật render SSR đầy đủ, chỉ cần `requests`. Playwright chỉ dùng để **khám phá** đúng URL + cấu trúc, không dùng lúc chạy.

---

## 2. Đổi tên file thống nhất (mặc định BẬT)

File lưu theo định dạng chuẩn:

```
<LOẠI> - <TICKER> - <KỲ>[ - HN/RIENG][ - KT][ - EN].pdf
```

- **LOẠI:** `BCTC` (báo cáo tài chính) · `BCTLATTC` (tỷ lệ an toàn tài chính) · `CBTT` (công bố thông tin) · `GiaiTrinh` (giải trình lợi nhuận)
- **KỲ:** `Q1.2026` · `H1.2026` (bán niên) · `2026` (cả năm)
- **Hậu tố:** `HN`/`RIENG` (hợp nhất/riêng) · `KT` (quý có kiểm toán/soát xét) · `EN` (bản tiếng Anh)

Ví dụ: `BCTC - SSI - Q1.2026 - HN.pdf`, `BCTLATTC - BSI - 2025.pdf`, `GiaiTrinh - TCSC - Q1.2026 - RIENG.pdf`

**Đặc điểm:**
- **Ticker tự detect theo host** — không phải chọn/gõ. Đè bằng `--ticker <MÃ>`.
- Nguồn phân loại theo thứ tự tin cậy: **Content-Disposition header** → tên URL (đã giải mã `%20`) → nhãn → **nội dung trang 1 PDF** (khi mọi thứ vô dụng, vd URL uuid).
- Không phân loại được loại/kỳ → **giữ tên gốc** (không mất file).
- Tắt bằng `--no-rename`.

---

## 3. Gom file theo thư mục ticker (mặc định BẬT)

Mỗi link tải tự gom vào thư mục con theo mã CK:

```
downloads/SSI/BCTC - SSI - Q1.2026 - HN.pdf
downloads/BVS/...
downloads/MBS/...
```

Tắt bằng `--no-subfolder`.

---

## 4. Công cụ đổi tên file ĐÃ tải sẵn

Đổi tên tại chỗ các PDF đã có (không tải lại):

- CLI: `python pdf_detector.py --rename-dir <thư mục> --ticker SSI`
- Hoặc cú đúp **`Doi-ten-file-da-tai.bat`** (hỏi thư mục + mã CK).
- Bỏ qua file đã đúng chuẩn; đọc nội dung PDF khi tên file vô dụng.

---

## 5. Các lỗi đã sửa

- **VDSC ra nhầm năm** (Q4.2026 → Q4.2025): nhãn mở đầu bằng ngày upload → đổi logic lấy năm (ưu tiên "năm YYYY"/cạnh quý/cuối cùng).
- **BSC nhầm loại** (CBTT viết liền "Congbothongtin" → nhận thành BCTLATTC): so khớp **không khoảng trắng**.
- **SSI tiền tố CBTT_BCTC_** làm mọi file thành CBTT → đổi thứ tự phân loại (CBTT để cuối).
- **Quý dính liền** "Quy1" không bắt được → regex `quy ?N`.
- **Mất hậu tố HN/RIENG khi chạy lại** rename-dir → bỏ qua file đã đúng chuẩn.
- **Tên `%20` loạn** → giải mã URL ở fallback.
- **Đặt tên trùng (2 tầng)** "Xem báo cáo" → tên = `{tiêu đề slug} - {tên file gốc}`.
- **GEL lỗi SSL** (server thiếu intermediate cert → "unable to verify the first certificate"): thêm `http_get()` tự fallback `verify=False` (nhớ host). Áp dụng chung mọi mode.
- **GEL nhầm `GiaiTrinh`**: file tên "BCTC … **và** Văn bản giải trình" (BCTC kèm giải trình trong 1 PDF) bị nhận thành `GiaiTrinh` → chỉ nhận GiaiTrinh khi KHÔNG kèm "báo cáo tài chính".
- **GEL sai NĂM** (bảng gộp nhiều cột quý vào 1 hàng → nhãn dính ngày/năm của báo cáo khác): **ưu tiên kỳ từ TÊN FILE**, chỉ fallback nhãn khi tên file rỗng kỳ; nếu tên file không có năm thì lấy **năm của trang nav** (`?y=`) thay vì nhãn nhiễu.
- **GEL trùng tên 2 bản annual** (bản công bố vs bản soát xét cùng năm `…2025-HN`): bản soát xét được thêm `KT` → `… 2025 - HN - KT` (không đè mất file).

---

## 6. Giới hạn còn lại

- **54 file SSI cũ (2007–2013)**, URL `/upload/file/<uuid>.pdf`: PDF scan/lỗi font (text méo/rỗng) + SSI giấu năm/quý trong bộ lọc JS → không tự đặt tên được. Đã để nguyên tên uuid trong `downloads/SSI/`. Muốn xử lý cần OCR hoặc map cấu trúc JS.
- **BVSC**: vài báo cáo gần đây trên web không đính kèm PDF công khai (modal trống) → tự bỏ qua.

---

## 7. Cách dùng nhanh

```bash
# Cú đúp Chay-PDF-Detector.bat  -> hỏi URL + tiêu chí, TỰ đổi tên + gom thư mục

# Hoặc dòng lệnh:
python pdf_detector.py --url "<URL>" --include "hợp nhất,kiểm toán"
python pdf_detector.py --url "<URL>" --no-rename        # giữ tên gốc
python pdf_detector.py --url "<URL>" --no-subfolder     # không gom thư mục
python pdf_detector.py --rename-dir downloads/SSI --ticker SSI   # đổi tên file đã tải
```

CTCK chạy tốt: SSI · VIX · TCSC · HSC · VDSC · SHS · MBS · BSC · Pinetree · BVSC · **GEL (Gelex Infra)** (+ haiants/masvn/kafi gốc).
