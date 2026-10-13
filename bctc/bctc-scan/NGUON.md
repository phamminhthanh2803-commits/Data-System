# Khảo sát nguồn "BCTC mới công bố" toàn thị trường (13/10/2026)

Mục tiêu: theo dõi báo cáo tài chính (quý / soát xét bán niên / kiểm toán năm; hợp nhất / riêng / công ty mẹ) **mới công bố**
của toàn bộ mã HOSE + HNX + UPCOM, có link PDF gốc và ngày công bố, gọi được từ GitHub Actions (IP Mỹ).
Cách thử: `curl_cffi` impersonate Chrome từ laptop (IP VN) + trình duyệt tích hợp bắt API thật qua network log.
Chưa thử trực tiếp từ IP Mỹ trong phiên này; probe 12/10 cho biết cafef.vn / hnx.vn / vietcap OK từ runner GitHub.

## Kết luận: CafeF là nguồn chính, Vietstock dự phòng, HOSE/HNX ghi nhận để bổ sung sau

| Nguồn | Phủ sàn | Toàn TT 1 call? | PDF gốc | Ngày công bố | Kỳ / loại / phạm vi | IP Mỹ | Tốc độ | Kết luận |
|---|---|---|---|---|---|---|---|---|
| **CafeF FileBCTC.ashx** | HOSE+HNX+UPCOM | Không (bắt buộc `Symbol`) | Có (cafefnew.mediacdn.vn) | Suy từ Mongo ObjectId `id` (thời điểm CafeF đăng, khớp hậu tố ddmmyyyyHHMMSS trong tên file) | `Quarter`/`Year` + tên chuẩn hoá "BCTC hợp nhất quý 2 năm 2026 (đã soát xét)" | OK (probe 12/10) | 0,2–0,3 s/mã, 24 mã/6 luồng = 1,0 s → toàn TT ~1 phút | **CHÍNH** |
| **Vietstock data/GetDocument** | HOSE+HNX+UPCOM | Không (theo `code`) | Có (static2.vietstock.vn, đôi khi .zip) | `LastUpdate` (ms) | Tiêu đề "BCTC Hợp nhất Soát xét 6 tháng đầu năm 2026" (parse regex) | Chưa thử; nginx, không thấy Cloudflare | ~0,5 s/mã; cần token + cookie từ 1 lần GET trang | **DỰ PHÒNG** (`--source vietstock`) |
| HOSE api.hsx.vn | HOSE | Có (news/cate) nhưng BCTC trộn với mọi CBTT; file BCTC theo mã qua `mediafiles/5/{secOrgId}` | Có (staticfile.hsx.vn/Uploads/…) | `createdDate` chính xác tới giây (`publishDate` không tin được) | `type` Quý/Bán niên/Năm + `time` "02.2026"; phạm vi từ tên file | Chưa thử | 0,2 s | Ghi nhận, chưa dùng (cần map mã → secOrgId) |
| HNX ModuleArticles | HNX + UPCOM (+ TPDN) | Có (POST tìm theo tiêu đề + khoảng ngày, 50 dòng/trang) | File qua `funcShowFileAttach(id,1)` (cần thêm 1 bước) | "dd/MM/yyyy HH:mm" chính xác | Chỉ có tiêu đề tự do | OK (probe 12/10) | 1,8 s/50 dòng | Ghi nhận, chưa dùng (HTML, lẫn mã trái phiếu) |
| VNDirect finfo v4 | — | `events` lỗi ES 500, `news` rỗng, không có endpoint tài liệu | Không | — | — | api-finfo OK, finfo-api timeout | — | Loại |
| Vietcap IQ | — | Không đoán được endpoint tài liệu (404) | — | — | — | — | — | Loại (chưa bắt được API) |

### 1. CafeF (nguồn chính)

Trang mã: `https://cafef.vn/du-lieu/hose/fpt-cong-ty-co-phan-fpt.chn` → tab **Tài liệu** `…/hose/fpt-tai-lieu.chn` gọi:

```
GET https://cafef.vn/du-lieu/Ajax/PageNew/FileBCTC.ashx?Symbol=fpt&Type=1&Year=0
    Header: Referer https://cafef.vn/du-lieu/hose/fpt-tai-lieu.chn, X-Requested-With XMLHttpRequest  (curl_cffi impersonate chrome)
    Type=1 BCTC (FPT: 205 file từ 2008) · Type=3 điều lệ + BCTN · Type=4 nghị quyết (Time = dd-MM-yyyy) · Type=0 tất cả · Type=2 lỗi
    Year=0 tất cả năm, Year=2026 chỉ BCTC năm tài chính 2026 (Q1, Q2, soát xét 6T)   → tăng dần chỉ gọi 1–2 năm/mã
    Không có Symbol → "symbol is empty" (KHÔNG có bản toàn thị trường)
{"Data":[{"id":"6a681930015b429ee29cd168","Type":0,"Quarter":2,"Year":2026,"Time":"Q2/2026",
          "Name":"Báo cáo tài chính công ty mẹ quý 2 năm 2026","Link":"https://cafefnew.mediacdn.vn/Images/Uploaded/DuLieuDownload/BCTC/FPT_…_28072026095127.pdf?v=…"}]}
```
- `id` = Mongo ObjectId → 4 byte đầu = Unix time lúc CafeF đăng (0x6a681930 = 28/07/2026 09:51 VN, khớp tên file). Dùng làm **ngày công bố**
  (có thể trễ 0–2 ngày so với ngày DN gửi UBCK; so với VNDirect `createdDate` FPT Q3/2025: CafeF 24/10 vs VND 24/10 – khớp).
- `Quarter` 1–4 = quý, 5 = cả năm (`Time` "CN/2025"); soát xét bán niên ghi Quarter=2 + "(đã soát xét)".
- Tên chuẩn hoá → phạm vi: "hợp nhất" / "công ty mẹ" / "riêng"; không ghi = công ty không có công ty con (`khong_ro`).
- Các endpoint khác trên trang mã (để tham khảo): `News.ashx?Symbol=fpt&NewsType=1..5` (tin CBTT dạng bài viết, có DeployDate,
  không link PDF), `LichSuKien.ashx`, `FinanceReport.ashx` (số liệu BCTC đã nhập), `GDCoDong.ashx` (giao dịch nội bộ – đã dùng ở data_src).

### 2. Vietstock (dự phòng)

```
GET  https://finance.vietstock.vn/FPT/tai-lieu.htm   → cookie ASP.NET_SessionId + __RequestVerificationToken
                                                        + input hidden __RequestVerificationToken (108 ký tự, HTML minify: name=… không có dấu nháy)
POST https://finance.vietstock.vn/data/GetDocument    code=FPT&type=1&page=1&pageSize=50&__RequestVerificationToken=<tok>
     Header X-Requested-With: XMLHttpRequest, Referer trang mã
     type: 1 BCTC · 2 BCTN · 3 bản cáo bạch · 4 NQ ĐHCĐ · 5 tài liệu ĐHCĐ · 6 khác (điều lệ)
[{"FileInfoID":559276,"Url":"https://static2.vietstock.vn/data/HOSE/2026/BCTC/VN/QUY%202/FPT_Baocaotaichinh_6T_2026_Soatxet_Congtyme.pdf?ver=…",
  "Title":"BCTC Công ty mẹ Soát xét 6 tháng đầu năm 2026 ","FullName":"Báo cáo tài chính …","LastUpdate":"/Date(1787371890290)/","TotalRow":225}]
```
- Token dùng chung cho mọi mã trong cùng phiên (đã thử FPT → AAH). Không cần đăng nhập cho type=1.
- Đường dẫn Url có sàn (HOSE/HNX/UPCOM) tại thời điểm nộp; UPCOM đôi khi .zip.
- Chưa thử từ IP Mỹ; nếu bị chặn → chạy `--source vietstock` ở laptop (Run-Local-Mini).

### 3. HOSE (api.hsx.vn – site React mới, bundle main.d430e296.js)

```
GET https://api.hsx.vn/n/api/v1/1/news/cate?pageIndex=1&pageSize=100&startDate=2026-10-01&endDate=2026-10-13&aliasCate=tin-tuc/tin-to-chuc-niem-yet
    → mọi CBTT của TCNY (8.160 tin từ 01/08; postedDate Unix), tiêu đề "FPT: …"; aliasCate=tin-tuc/thong-tin-tai-chinh rỗng
GET https://api.hsx.vn/n/api/v1/1/news/{id}            → chi tiết, có code + relatedId (= secOrgId)
GET https://api.hsx.vn/m/api/v1/1/mediafiles/5/{secOrgId}?pageIndex=1&pageSize=50&year=0
    → file BCTC của 1 DN: fileName, filePath "~/Uploads/UploadDocuments/…" (→ https://staticfile.hsx.vn/Uploads/…), type "Quý|Bán niên|Năm",
      time "02.2026", createdDate (đúng), publishDate (SAI – = ngày kết thúc kỳ)
Header: Origin/Referer https://www.hsx.vn ; "1" sau v1 = langId (vi). Tìm toàn văn: https://api.hsx.vn/q/api/v1/search (basic auth internet_user/internet_user, chưa thử)
```
Thiếu map mã → secOrgId (`/l/api/v1/1/securities/` trả rỗng, `/s/api/v1/1/secorgs/FPT` 400) → lấy qua news detail. Để sau.

### 4. HNX (www.hnx.vn, ASP.NET MVC)

```
GET  https://www.hnx.vn/thong-tin-cong-bo-ny-tcph.html   (cookie; curl_cffi cần verify=False – chuỗi CA HNX thiếu intermediate)
POST https://www.hnx.vn/ModuleArticles/ArticlesCPEtfs/NextPageTinCPNY_CBTCPH
     pNumPage=1&pAction=1&pNhomTin=&pTieuDeTin=báo cáo tài chính&pMaChungKhoan=&pFromDate=01/07/2026&pToDate=13/10/2026&pOrderBy=&pNumRecord=50
     → HTML bảng: STT | Ngày đăng tin (dd/MM/yyyy HH:mm) | Mã CK | Tên TCPH | Tiêu đề | File (onclick funcShowFileAttach(<id>,1)); "Tổng số 1198 bản ghi"
```
Lẫn mã trái phiếu (BID126009, SBT426026…) → lọc mã 3 ký tự. File đính kèm cần thêm 1 request theo id (chưa làm).
(`ModuleReportDisclosure` cũ không còn; bond-pivot/pull_hnx.py dùng cbonds.hnx.vn – site khác.)

### 5. Loại

- VNDirect `finfo-api.vndirect.com.vn` timeout từ laptop; `api-finfo.vndirect.com.vn/v4/events` lỗi Elasticsearch 500, `v4/news` rỗng,
  `company_documents`/`documents` 404. `financial_statements` chỉ có số liệu (createdDate = ngày nhập, FPT Q2/2026 = 28/07) – không phải tài liệu.
- Vietcap IQ: các đường dẫn `iq-insight-service/v1/company/{sym}/documents|financial-reports` 404 – chưa bắt được API tài liệu.

## Điểm chưa chắc / cần theo dõi

1. Ngày công bố CafeF = giờ CafeF đăng file, không phải giờ DN gửi UBCK/HOSE; lệch có thể 0–2 ngày (cuối tuần).
2. CafeF có thể đăng cùng 1 báo cáo 2 lần (FPT Q3/2025 có 3 dòng: 1 "Báo cáo tài chính quý 3" + "công ty mẹ" + "hợp nhất") → app đếm DN theo (mã, kỳ) distinct.
3. Chưa xác nhận Vietstock/HSX từ IP Mỹ. CafeF OK theo probe 12/10.
4. Danh sách mã lấy từ `index-fetcher/raw/vn_screener_meta.csv` (1.233 mã có sàn); mã mới niêm yết chưa có trong file sẽ bị bỏ sót tới khi screener cập nhật.
