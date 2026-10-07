# PDF Detector — Context Handoff

Tài liệu chuyển ngữ cảnh sang phiên/cửa sổ chat khác. Đọc file này là nắm đủ tiến độ & cách hoạt động.

## 1. Tool là gì
Tool Python quét trang web, **phát hiện link PDF, lọc theo tiêu chí (loại văn bản: báo cáo tài chính, hợp nhất, công ty mẹ, kiểm toán, quý, năm...) rồi tải về**. Hỗ trợ phân trang và nhiều kiểu site khác nhau.

## 2. Vị trí & cách chạy
- **Thư mục:** `D:\bctc\pdf-detector\`
  - `pdf_detector.py` — script chính (1 file, ~550 dòng)
  - `Chay-PDF-Detector.bat` — cú đúp để chạy (hỏi tiêu chí tương tác)
  - `downloads\` — nơi lưu PDF mặc định
- **Đặt ở GỐC ổ D** (không để trong `D:\Microsoft VS Code\` vì update VS Code xoá sạch thư mục cài → đã từng mất tool 1 lần).
- **Deps:** `requests`, `beautifulsoup4` (lúc chạy). `playwright`+chromium đã cài nhưng CHỈ dùng để khám phá site mới, không cần lúc chạy.
- **CLI:**
  ```
  python pdf_detector.py --url "<URL>" --include "hợp nhất,kiểm toán" --exclude "soát xét" --pages 1-14
  python pdf_detector.py --url "<URL>"          # không lọc = tải tất cả; bỏ --pages = tự dừng
  --mode static|masvn|kafi|shs|vdsc|mbs|bsc|pinetree|bvsc   # ép chế độ (mặc định tự nhận diện theo URL)
  --include-mode any|all                         # any=khớp 1 từ khoá đủ (mặc định), all=phải khớp hết
  --overwrite                                     # tải lại file đã có
  --no-rename                                     # TẮT đổi tên (mặc định BẬT)
  --no-subfolder                                  # KHÔNG gom theo ticker (mặc định BẬT)
  --ticker SSI                                    # đè ticker tự detect (host lạ / ép mã)
  ```
  **Gom theo ticker (BẬT MẶC ĐỊNH)**: file của mỗi link tự vào `<out>/<TICKER>/`
  (vd `downloads/SSI/`). Ticker tự detect theo host. Tắt: `--no-subfolder`.
  **Đổi tên thống nhất BẬT MẶC ĐỊNH** (ticker tự detect theo host): file lưu
  `"<LOẠI> - <TICKER> - <KỲ>[ - HN/RIENG][ - KT][ - EN].pdf"`. Tắt: `--no-rename`. Xem mục 4b.

## 3. Chín chế độ (tự nhận diện qua URL)

| Chế độ | Site mẫu đã test | Cơ chế |
|--------|------------------|--------|
| `static` | haiants.vn/bao-cao-tai-chinh-q8.html | HTML tĩnh, PDF nằm sẵn trong HTML, phân trang `?page=N` (hoặc path `{page}`) |
| `masvn` | masvn.com/cate/bao-cao-tai-chinh-11 | Nuxt SPA → API JSON (không cần token) |
| `kafi` | kafi.vn/investors | Phoenix LiveView SSR + PDF trên Google Drive |
| `shs` | shs.com.vn/quan-he-co-dong/bao-cao-dinh-ky/TAICHINH | Nuxt SPA → API Strapi same-origin `/api/shareholders/periodic-report` |
| `vdsc` | vdsc.com.vn/quan-he-co-dong/thong-tin-tai-chinh/bao-cao-tai-chinh | static + link tải endpoint id (không đuôi .pdf) |
| `mbs` | www.mbs.com.vn/bao-cao-tai-chinh/ | static **2 TẦNG** (list SSR → trang chi tiết → PDF), phân trang path `/page/N/` |
| `bsc` | www.bsc.com.vn/bao-cao-tai-chinh/ | WordPress: list SSR (data-id) → **POST admin-ajax modal** `get_content_qhcd` lấy PDF |
| `pinetree` | pinetree.vn/post/category/quan-he-nha-dau-tu/bao-cao-tai-chinh/ | WordPress **2 TẦNG** (list SSR → bài `/post/<ngày>/<slug>/` → PDF), phân trang path `/page/N/` |
| `bvsc` | www.bvsc.com.vn/danhmuc/quan-he-nha-dau-tu/bao-cao-tai-chinh/ | static **2 TẦNG** (cả list 1 trang → bài `/danhsachbaiviet/<slug>/` → PDF /media/) |

> Cơ chế **2 TẦNG dùng chung** (mbs + pinetree + bvsc): `run_static` + cfg `follow_detail_re`. Mỗi trang list, ngoài PDF trực tiếp còn `find_detail_links()` lấy link bài chi tiết (dedup `seen_details`), GET từng bài, `find_pdfs_on_page` lấy PDF. **Đặt tên file = `{tiêu đề} - {tên file gốc}.pdf`** để DUY NHẤT (tránh trùng khi nhiều bài cùng có "Cong-bo-thong-tin.pdf" hay link chỉ ghi "Xem báo cáo"/icon). Tiêu đề lấy từ text link list; nếu là nút chung chung/icon/quá ngắn → lấy từ SLUG URL bài chi tiết.

### 3a. static (haiants.vn)
- Cào HTML mỗi trang `?page=N`, tìm `<a href$=.pdf>`.
- Test: **130/130 PDF**, phân trang 1→14.

**Phân trang kiểu ĐƯỜNG DẪN (path-based)** — site nhét số trang vào path chứ không phải query (`/page-2/` thay vì `?page=2`):
- Nhét placeholder `{page}` vào `--url`, vd `--url "https://tcsc.vn/vi/download/Bao-cao-tai-chinh/page-{page}/"`.
- `build_page_url()` thấy `{page}` → thay bằng số trang; không thấy → gắn `?page=N` như cũ.
- Auto-stop vẫn chạy: khi vượt trang cuối, site lặp lại trang 1 → toàn PDF đã thấy (dedup theo URL trong `seen_files`) → "không có PDF mới" 2 trang liên tiếp → dừng.

**Các CTCK đã khảo sát & test OK (đều là chế độ `static`):**

| CTCK | URL | Phân trang | Ghi chú |
|------|-----|-----------|---------|
| **SSI** | `ssi.com.vn/quan-he-nha-dau-tu/bao-cao-tai-chinh` | `?page=N` (1→19) | HTML tĩnh, PDF inline, có hợp nhất/riêng. Test OK. |
| **VIX** | `vixs.vn/qhcd/bao-cao-tai-chinh` | `?page=N` (1→12) | HTML tĩnh. CTCK đơn lẻ → KHÔNG có "hợp nhất". Test OK. |
| **TCSC** | `tcsc.vn/vi/download/Bao-cao-tai-chinh/page-{page}/` | **path** `/page-N/` (1→20) | Cần placeholder `{page}`. 171 PDF, auto-stop OK. |
| **HSC** | `hsc.com.vn/vi/quan-he-nha-dau-tu/thong-tin-tai-chinh/bao-cao-tai-chinh` | `?page=N` (1→14) | HTML tĩnh, PDF trên Google Cloud Storage. Đơn lẻ → KHÔNG có "hợp nhất" (lọc kiểm toán/quý/năm). Test tải OK. |

**Site đã khảo sát NHƯNG chưa chạy được:** (hiện không còn — tất cả CTCK khảo sát đều đã có chế độ)

> VDSC, SHS, MBS, BSC trước đây nằm ở mục này — nay ĐÃ làm xong (xem 3d, 3e, 3f, 3g).

**⚠️ Bài học MBS (đừng lặp lại):** ban đầu tưởng MBS phải dùng Playwright vì admin-ajax bị Cloudflare chặn 403. NHƯNG đó là ngõ cụt — Cloudflare chỉ chặn **POST** admin-ajax, KHÔNG chặn **GET**. Trang BCTC đúng là `www.mbs.com.vn/bao-cao-tai-chinh/` (URL cũ `/vi/quan-he-co-dong/bao-cao-tai-chinh/` đã 404 nên mới tưởng bí). Trang này render SSR đầy đủ, phân trang path `/page/N/`, mỗi báo cáo link sang trang chi tiết chứa PDF → chỉ cần `requests` + adapter 2 tầng, KHÔNG cần browser. Playwright chỉ dùng để KHÁM PHÁ ra đúng URL + cấu trúc, không dùng lúc chạy. (Bài học: luôn thử lại bằng GET trang list trước khi kết luận "cần browser".)


### 3b. masvn (masvn.com)
- URL `/cate/<slug>-<id>` → id = số cuối slug (vd `bao-cao-tai-chinh-11` → id **11**).
- Gọi API: `GET https://masvn.com/api/categories/fe/<id>/article?page=N&limit=20&sort=published_at&direction=desc&active=1` — **không cần token**.
- JSON trả `data[]` (mỗi item có `title` dạng `{"vi":"..."}` + `file_path`), kèm `total`/`last_page`/`per_page` để phân trang.
- URL PDF = `https://masvn.com/api` + `file_path` (phải `quote()` ký tự Unicode).
- Khi match: BỎ tiền tố timestamp-ngày-upload khỏi tên file + truyền url rỗng vào match_criteria (để năm-upload không gây dương tính giả khi lọc theo năm).
- Tên file lưu: `{title} [{id}].pdf` (id chống trùng).
- Test: cate 11 = **100 báo cáo / 5 trang**, tải OK.
- ⚠️ MAS là CTCK đơn lẻ → KHÔNG có loại "hợp nhất/công ty mẹ". Lọc theo `quý`, `năm`, `kiểm toán`, `bán niên`.

### 3c. kafi (kafi.vn/investors)
- Phoenix LiveView, danh sách báo cáo nằm SẴN trong HTML tĩnh (SSR).
- Mỗi tài liệu là div `phx-click navigate -> /investors-details?tab=tntttc&id=<GoogleDriveID>`.
- PDF lưu trên **Google Drive** → tải qua `https://drive.usercontent.google.com/download?id=<id>&export=download`.
  - Xử lý trang xác nhận file lớn của Drive: nếu trả `text/html` thì parse các hidden input `name=value` rồi gọi lại.
- Parse bộ ba (drive id, tiêu đề, ngày) bằng regex; tên file lưu `{tiêu đề} ({DD-MM-YYYY}).pdf`.
- Test: **218 tài liệu** (tab "Thông tin tài chính"), tải **116 PDF** hợp lệ.
- ⚠️ HẠN CHẾ: chỉ lấy tab `tntttc` (mặc định). Các tab khác (Báo cáo thường niên, Quản trị DN, Lịch sự kiện, CBTT khác) nạp qua websocket `phx-click="switch_tab"` → cần chế độ browser, **CHƯA làm**.

### 3d. vdsc (vdsc.com.vn — Rồng Việt)
- Bản chất là `static` (HTML tĩnh, phân trang `?page=N`, ~17 trang) NHƯNG link tải KHÔNG có đuôi `.pdf` mà là endpoint id: `/data/api/app/file-storage/<uuid>?downloadFrom=ManagementDocument-<n>` (response `Content-Type: application/pdf`, magic `%PDF`, không có Content-Disposition).
- Cơ chế dùng chung với static: `run()` khi mode=`vdsc` chỉ set `cfg["extra_pdf_patterns"]=[r"/file-storage/"]` rồi chạy `run_static` như thường.
- `find_pdfs_on_page(html, url, extra_pdf_patterns)`: link khớp pattern phụ cũng coi là PDF; vì URL không có tên file → đặt tên từ NHÃN (text cả hàng), bỏ số đếm lượt tải ở cuối, kèm `[id]` (số trong URL) cho duy nhất → trả thêm khoá `dest`. Vòng static truyền `dest_name=p.get("dest")` vào `download()`.
- Nhãn VDSC giàu từ khoá ("…Hợp nhất…/…Riêng…/…Đã kiểm toán…") → lọc `hợp nhất`/`riêng`/`kiểm toán`/`soát xét` chạy tốt.
- Test: lọc "hợp nhất" trang 1-2 → 8/16 khớp, tải OK.

### 3e. shs (shs.com.vn — Sài Gòn Hà Nội)
- Nuxt SPA: SSR HTML CHỈ có 10 báo cáo mới nhất + phân trang là client-side → phải gọi API. API Strapi same-origin (KHÔNG cần token):
  `GET /api/shareholders/periodic-report?category=<CODE>&page=N&pageSize=100` → `{data:[{Title, Summary(HTML có link .pdf), PublishedDate,...}], meta:{pagination:{page,pageCount,total}}}`.
- `<CODE>` = đoạn cuối URL người dùng dán: `TAICHINH` (BCTC), `ANTOANTAICHINH` (tỷ lệ ATTC), `THUONGNIEN` (thường niên)... Lấy danh sách mã ở `/api/shareholders/periodic-report/categories`.
- PDF (bản **VI** + **EN**) host trên `s3-storage.shs.com.vn`, nằm trong field `Summary` (HTML) → regex `https?://...\.pdf`. Lọc trên `Title + tên file` (tên file có `VI_`/`EN_`, `Quy`, `Nam`, `KiemToan`... rất giàu từ khoá). Muốn chỉ bản tiếng Việt: `--include "VI_" --exclude "EN_"`.
- ⚠️ Cùng group "báo cáo định kỳ" còn các loại khác (corporate-report, info-disclosure, share-report, stock-report, research-report, market-outlook-reports) ở các path `/api/shareholders/*` và `/api/*` — hiện tool chỉ map `/bao-cao-dinh-ky/` → `periodic-report`. Loại khác chưa map.
- Test: `category=TAICHINH` = **120 báo cáo / 2 trang**, 76 PDF; tải bản VI OK.

### 3f. mbs (www.mbs.com.vn — Chứng khoán MB)
- Static **2 TẦNG**: trang list (SSR, `requests` lấy được — Cloudflare KHÔNG chặn GET) → mỗi báo cáo link sang TRANG CHI TIẾT → PDF thật trên `mbs.com.vn/files/uploads/.../*.pdf`. Trang cũ đôi khi link thẳng .pdf (đã bắt luôn ở tầng list).
- URL người dùng dán: `www.mbs.com.vn/bao-cao-tai-chinh/` (hoặc loại khác: `/bao-cao-thuong-nien/`...). `run()` mode=mbs: lấy `slug` = đoạn cuối URL → `follow_detail_re = /<slug>-[^/]+/?$`, và đổi base thành `…/<slug>/page/{page}/` (phân trang path, page 1 = `/page/1/`).
- Cơ chế 2 tầng (dùng chung trong `run_static`): cfg `follow_detail_re` set → mỗi trang list, ngoài PDF trực tiếp còn `find_detail_links()` lấy link chi tiết (dedup `seen_details`), GET từng trang, `find_pdfs_on_page` lấy PDF; nhãn = tiêu đề chi tiết + tên file (giàu từ khoá để lọc), đặt tên file theo tiêu đề (nhiều PDF/trang → thêm `(1)(2)(3)`).
- Auto-stop: `/page/13/`+ trả 404 → resp None → empty_streak → dừng sau 2 trang. Phân trang test được 1→12.
- Test: lọc "kiểm toán" trang 1-2 → tải các BCTC kiểm toán + ATTC + giải trình OK.

### 3g. bsc (www.bsc.com.vn — Chứng khoán BIDV)
- WordPress. Trang list (vd `/bao-cao-tai-chinh/`) render SSR, mỗi báo cáo là `<div data-id="<post id>" data-newstype="0">` + tiêu đề/ngày, **KHÔNG có link PDF** (mở modal khi click). `requests` lấy list bình thường (Cloudflare KHÔNG chặn).
- Lấy PDF: với mỗi `data-id`, **POST** `…/wp-admin/admin-ajax.php` body `action=get_content_qhcd&id_post=<id>&newstype=<nt>&security=<nonce>` → HTML modal chứa link PDF trên `files.bsc.com.vn/news/...`. ⚠️ BẮT BUỘC header `X-Requested-With: XMLHttpRequest` + `Referer` (thiếu → trả rỗng). `nonce` lấy từ HTML trang list (`security: '<10hex>'`).
- Phân trang query `?post_page=N` (1→6), auto-dừng khi trang không còn `data-id`. Lọc trên tiêu đề (giàu từ khoá: "đã được kiểm toán", "soát xét", "Quý...") + tên file. Đặt tên theo tên file gốc (đã mô tả tốt: `BSCBaocaotaichinhakiemtoan...`).
- ⚠️ HẠN CHẾ DỮ LIỆU BSC (không sửa được): nhiều post (nhất là BCTC quý 2024-2025) modal chỉ ghi "Chi tiết tại tập tin đính kèm!" mà KHÔNG có link PDF công khai (kể cả khi click thật trên browser; vài post có recaptcha) → tool tự bỏ qua ("không có PDF"). Các báo cáo kiểm toán năm + bán niên soát xét thì có đủ PDF, tải OK.
- Test: page 1 không lọc → 6 PDF (kiểm toán 2025 + bán niên soát xét 2025); lọc "kiểm toán" 2 trang → 5 file.

### 3h. pinetree (pinetree.vn — Pinetree Securities)
- WordPress, **2 TẦNG y như mbs**: list `/post/category/.../bao-cao-tai-chinh/` (SSR) → bài chi tiết `/post/<YYYYMMDD>/<slug>/` → PDF trên `pinetree.vn/wp-content/uploads/.../*.pdf`. `requests` lấy được, không bị chặn.
- `run()` mode=pinetree: set `follow_detail_re = /post/\d{8}/[a-z0-9\-]+/?$` + đổi base thành `…/page/{page}/` (path pagination, page 1→~5 có nội dung, page ≥6 trống/404 → auto-stop).
- ⚠️ Link báo cáo trên trang list chỉ ghi "Xem báo cáo"/"Tải PDF" (nút) → tiêu đề lấy từ SLUG URL bài (vd `pinetree-bao-cao-tai-chinh-quy-1-nam-2026` → "bao cao tai chinh quy 1 nam 2026"). Mỗi bài có NHIỀU PDF (BCTC + ATTC + CBTT + giải trình) → tên file `{tiêu đề} - {tên file gốc}.pdf`.
- Test: lọc "kiểm toán" 2 trang → 27 PDF tải duy nhất (không trùng tên).

### 3i. bvsc (www.bvsc.com.vn — Chứng khoán Bảo Việt)
- KHÔNG phải WP/Nuxt (site .NET, jQuery). **2 TẦNG nhưng list nằm GỌN trong 1 trang**: tất cả báo cáo là `<div class="news__nhadautu--detail" quy nam newsid>` (ẩn `display:none`, hiện theo nút quý — nhưng nội dung SẴN trong HTML), mỗi cái có `<a href="/danhsachbaiviet/<slug>/">` (chỉ bọc icon pdf, KHÔNG có text). Trang chi tiết → 5 PDF trên `/media/...pdf` (VI + EN BCTC + giải trình + CBTT, link tương đối → urljoin).
- `run()` mode=bvsc: `follow_detail_re = /danhsachbaiviet/[a-z0-9\-]+/?$`; list không phân trang nên set `page_end=1` (nếu user không yêu cầu khác). `?page=N` bị site bỏ qua nên kể cả không set cũng auto-stop.
- Vì link list chỉ là icon (text rỗng) → tiêu đề LẤY TỪ SLUG URL bài (vd `bvsc-cong-bo-bao-cao-tai-chinh-quy-i-nam-2026`). Lọc bản Việt: `--exclude "en_"`.
- Test: 1 trang list → 96 link chi tiết, **253 PDF** (lịch sử tới 2006!); lọc "kiểm toán" loại EN → 14 file tải duy nhất.

## 4. Logic lọc (dùng chung mọi chế độ)
- `strip_accents()`: bỏ dấu tiếng Việt + biến mọi dấu phân tách (`-`, `_`, `.`...) thành khoảng trắng + lowercase.
- So khớp **space-insensitive**: "hợp nhất" khớp cả `hop-nhat` lẫn dạng liền `HOPNHAT`.
- Bộ **SYNONYMS**: công ty mẹ↔ctyme↔riêng, hợp nhất↔hopnhat↔consolidated, kiểm toán↔audited, soát xét↔reviewed, bctc↔báo cáo tài chính.
- `include_mode`: `any` (mặc định) / `all`. `exclude` luôn thắng.

## 4b. Đổi tên file thống nhất (BẬT MẶC ĐỊNH — tự detect ticker)
**MẶC ĐỊNH BẬT** mọi lúc (kể cả luồng BAT/tương tác); KHÔNG hỏi gì. Lưu file thành **`<LOẠI> - <TICKER> - <KỲ>[ - HN/RIENG][ - KT][ - EN].pdf`**. Tắt bằng `--no-rename`.
- **TICKER tự detect** theo host từ `TICKER_BY_HOST` (ssi→SSI, vixs→VIX, tcsc→TCSC, hsc→HCM, vdsc→VDS, shs→SHS, mbs→MBS, bsc→BSI, bvsc→BVS, pinetree→PINETREE, masvn→MAS, kafi→KAFI, haiants→HAH). `--ticker <MÃ>` để đè (cho host lạ hoặc ép mã). Host lạ + không `--ticker` → giữ tên gốc (in 1 dòng nhắc).
- **Nguồn tên file để phân loại**: `download()` GET (stream, chưa tải body) đọc **`Content-Disposition`** trước → tên header đáng tin hơn URL (URL hay uuid/%20/dính số). Có header → `unified_filename(..., header_name=...)` dùng nó; không có → dùng tên URL (đã `unquote` %20). Helper `_filename_from_cd()` (ưu tiên RFC5987 `filename*`). ⚠️ Thực tế hầu hết site CK VN (SSI/BSC/VDSC...) KHÔNG gửi Content-Disposition → vẫn rơi về URL/nhãn; header chỉ là lớp ưu tiên khi site nào đó có gửi.
- **LOẠI** (`_detect_type`, ưu tiên TÊN FILE rồi tiêu đề, so khớp **không khoảng trắng** để bắt tên viết liền như `Congbothongtin`): `GiaiTrinh` → `BCTLATTC` → `BCTC` → `CBTT` (CBTT CUỐI vì SSI thêm tiền tố `CBTT_BCTC_`). Không khớp loại nào (vd báo cáo thường niên/quản trị) → **giữ tên gốc**.
- **KỲ** (`_detect_period`): `Q1.2026`/`H1.2026` (bán niên: "bán niên"/"6 tháng"/"30/06")/`2026` (cả năm). ⚠️ Năm: KHÔNG lấy năm đầu (nhãn hay mở đầu bằng ngày upload, vd VDSC "30 tháng 1 2026 ... Quý IV/2025"); ưu tiên "nam YYYY" → năm cạnh token quý → ngày cuối kỳ → năm CUỐI cùng.
- **Hậu tố**: `HN`/`RIENG` (hợp nhất/riêng — firm đơn lẻ thì không có); `KT` (chỉ khi QUÝ + kiểm toán/soát xét, tránh trùng quý thường); `EN` (tên file bắt đầu `en_` / "english" / "financial statement" → tránh đè bản Việt cùng kỳ).
- Áp dụng trong `download()` (param `ticker`) → mọi chế độ (kể cả kafi qua `drive_download`). `cfg["rename_ticker"]` set 1 lần trong `run()`.
- **GOM THƯ MỤC theo ticker** (BẬT MẶC ĐỊNH): trong `run()`, detect `tk` 1 lần (dùng chung cho đổi tên & gom); nếu có `tk` và không `--no-subfolder` → `cfg["out_dir"] = out_dir/<tk>` rồi mới `makedirs`. Hoạt động độc lập với đổi tên (kể cả `--no-rename` vẫn gom). CONFIG `no_subfolder`.
- ⚠️ Trùng tên (cùng loại+ticker+kỳ+hậu tố) hiếm → vẫn skip-if-exists (idempotent); dùng `--overwrite` nếu cần.
- Test OK: SSI (HN/RIENG/BCTLATTC/quý/bán niên/năm), VDSC (năm sửa từ nhãn), TCSC (GiaiTrinh), Pinetree/MBS/BSC (4 loại), SHS (VI/EN), HSC (phân loại theo tiêu đề vì tên file là hash GCS).
- ⚠️ THỨ TỰ phân loại: GiaiTrinh → BCTLATTC → BCTC → **CBTT cuối cùng**. Vì SSI thêm tiền tố `CBTT_BCTC_`/`CBTT_..._ATTC_` vào MỌI file (CBTT chỉ là nhãn công bố, không phải loại). CBTT thật = bản công bố KHÔNG kèm từ khoá báo cáo (vd BSC `Congbothongtin.pdf`).
- Quý nhận cả dạng DÍNH LIỀN: `quy ?N`/`quy ?<roman>` bắt "Quy1", "QuyI", "quy 1"...

### Hỏi tương tác (luồng BAT) + đổi tên file đã tải
- **`Chay-PDF-Detector.bat`** chạy `python pdf_detector.py` (không tham số) → `interactive_setup()` hỏi: URL, từ khoá chọn/loại, trang, và **đổi tên** (Enter=không | gõ mã CK | gõ `auto`=tự tra host). → set cfg ticker/rename. (Trước đây BAT KHÔNG hỏi nên luôn ra tên gốc — đã thêm.)
- **`--rename-dir <thư mục> --ticker <MÃ>`**: đổi tên TẠI CHỖ các PDF ĐÃ tải (không tải lại), suy loại/kỳ từ tên file → nếu fail thì đọc **nội dung trang 1** (pdfplumber). File không phân loại được → giữ nguyên; trùng đích → `(2)`; **BỎ QUA file đã đúng chuẩn** (regex `^(BCTC|BCTLATTC|CBTT|GiaiTrinh) - ` — tránh chạy lại làm mất hậu tố HN/RIENG). Hàm `rename_existing_dir()`. ⚠️ 1 thư mục = 1 ticker.
- **Fallback NỘI DUNG** (`_pdf_first_text`, pdfplumber, ~1000 ký tự đầu trang 1): dùng khi tên/nhãn/header đều vô dụng (vd URL uuid). Áp dụng cả trong `download()` (sau khi lưu, nếu rename fail → đọc content → đổi tên) lẫn `rename_existing_dir()`.
- ⚠️ GIỚI HẠN (gặp với SSI báo cáo cũ 2007-2013, URL `/upload/file/<uuid>.pdf`): PDF **scan/lỗi font** → text trích ra méo/rỗng → không phân loại được; SSI lại giấu năm/quý trong **bộ lọc JS** (`select-year`), không có trong link/label tĩnh (chỉ có loại ở `div.chart__content__item__desc`). → các file này GIỮ NGUYÊN tên uuid (cần OCR hoặc map cấu trúc JS nếu muốn).
- **`Doi-ten-file-da-tai.bat`**: BAT bọc `--rename-dir` (hỏi thư mục + mã CK).

## 5. Các bug "sót file" đã sửa (chế độ static)
1. **normalize_url**: vá URL dị dạng `http:/host` (thiếu 1 gạch) — trước gây rớt file im lặng. (haiants có 1 file như vậy → giờ đủ 130/130.)
2. **So khớp space-insensitive + synonyms**: trước bỏ sót file đặt tên viết tắt/liền (`HOPNHAT`).
3. Báo cáo danh sách **FILE TẢI LỖI** cuối run (không sót im lặng).
4. **Retry 3 lần/trang** (lỗi 1 trang không giết cả crawl).
5. **Auto-stop khi 2 trang trống liên tiếp** (không dừng nhầm sớm).

## 6. Bài học khám phá site mới (nếu thêm site)
- **WAF chặn request không phải browser** (vd masvn 403/trắng): dùng Playwright với **user-agent + viewport thật** (BẮT BUỘC, thiếu là bị chặn).
- Tìm API: render bằng Playwright → bắt network/XHR khi tương tác (gõ Search, click tab) → lộ endpoint thật. Có thể đọc `window.__NUXT__` / bundle `/_nuxt/*.js` để tìm `baseURL`/`apiBase`.
- Sau khi biết endpoint, thường gọi được bằng `requests` thường (kèm header Referer/Origin/UA) → không cần browser lúc chạy.
- ⚠️ Đừng cố trích `CLIENT_SECRET`/tự xin OAuth token — bị bộ lọc an toàn chặn và vượt phạm vi. Ưu tiên API public không cần token, hoặc để browser tự xin token.

## 7. Việc còn dang dở / mở rộng khả dĩ
- [ ] kafi: lấy các tab khác (cần chế độ browser/Playwright drive `switch_tab`).
- [ ] (Tùy chọn) gom mỗi loại văn bản vào thư mục con riêng.
- [ ] (Tùy chọn) thêm chế độ `render` tổng quát bằng Playwright cho site JS bất kỳ chưa có API sạch.

## 8. Memory liên quan (đã lưu)
- `pdf-detector-tool.md` — chi tiết tool này (đã cập nhật đủ 3 chế độ).
- `markitdown-pdf2md-tool.md` — tool convert PDF→Markdown (`D:\markitdown-tool\`), dùng sau khi tải PDF.
- `fs-extractor-tool.md` — kéo BCTC theo mục (`D:\bctc\fs-extractor\`).
