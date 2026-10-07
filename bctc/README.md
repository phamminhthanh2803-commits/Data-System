# D:\bctc — cụm BÁO CÁO TÀI CHÍNH DOANH NGHIỆP (gộp 14/09/2026)

5 tool cùng mục tiêu: biến BCTC từ nhiều nguồn thành facts long-format để tra cứu / SQL / gộp ngành.
Không tool nào chạy theo lịch (chạy tay theo đợt), nên phần gộp là **schema chung + chuỗi 1 lệnh**, không phải runner.

```
D:\bctc\
  bctc_normalize.py      đưa 4 nguồn về 1 schema: ticker|source|entity|statement|item_id|item|period|value(VND)|quality
                         python bctc_normalize.py HAH GMD --out bctc_HAH_GMD.csv      (--source fs,fiinprox,md,tcbs)
  pdf_to_bctc.py         chuỗi: tải PDF (pdf-detector) -> OCR Markdown (markitdown-tool) -> CSV (md2bctc)
                         python pdf_to_bctc.py --ticker SSI --url "<trang BCTC>" --include "hợp nhất"
  fs-extractor\          vnstock/VCI, full lịch sử BCTC theo mục (fsx.py bctc|cap|liq|nganh), output\ 3,5 GB
  fiinprox-unpivot\      Excel FiinProX (wide) -> facts long (run_pipeline.py theo config.csv), output\ 3,4 GB
  md2bctc\               Markdown OCR mẫu CTCK B0x -> bctc_master.csv + bctc_notes.csv (regex thuần)
  pdf-detector\          quét web phân trang, tải PDF theo từ khoá; markitdown-tool\pdf2md.py OCR tiếng Việt; downloads\ 2,7 GB
  tcbs-pbi\              dump Power BI TCBS (10 CSV, dump_pbi.py)
```

## Đơn vị và kỳ trong schema chung
- `value` luôn VND (FiinProX "Tỷ VND" × 1e9; ratio giữ nguyên). `period` = `YYYY-Qn` hoặc `YYYY-FY`.
- `entity`: HN = hợp nhất, RL = riêng lẻ, ? = nguồn không ghi (fs-extractor mặc định HN theo VCI).
- md2bctc chỉ lấy cột `current`; cột `prior` của BCTC quý không xác định được là quý trước hay đầu năm nên bỏ.
- fs-extractor đọc theo chunk 1 triệu dòng; không truyền mã = đọc cả 3,5 GB (chậm).

## Ai dùng dữ liệu này
`D:\market-data\transmission-fetcher` đọc `fs-extractor\output` (tỷ lệ ngân hàng niêm yết, funding gap) và gọi `pdf2md.py`;
`D:\market-data\market-valuation\adjust.py` đọc `fs-extractor\output_cap\market_cap_daily.csv`.
Chi tiết từng tool: HUONG-DAN.txt / README.md trong thư mục con.

Hướng dẫn tổng: [D:\HUONG-DAN-TOOLS.md](../HUONG-DAN-TOOLS.md)
