# bctc-scan — theo dõi BCTC mới công bố toàn thị trường (13/10/2026)

Quét **báo cáo tài chính vừa đăng** (quý / soát xét bán niên / kiểm toán năm; hợp nhất / riêng / công ty mẹ) của toàn bộ mã
HOSE + HNX + UPCOM, ghi 1 file long-format cho app Market Data (tab **Tin tức › Báo cáo tài chính mới**).
3 nguồn chạy song song rồi **gộp lấy ngày công bố sớm nhất** (13/10/2026): **CafeF** `FileBCTC.ashx` (phủ rộng nhất, ngày = giờ CafeF đăng,
thường muộn / đăng gộp) + **Vietstock** `data/GetDocument` (`LastUpdate` đúng ngày) + **HOSE** `api.hsx.vn/m/api/v1/1/mediafiles/5/{secOrgId}`
(chỉ mã HOSE, `createdDate` chính xác, map mã → secOrgId tự xây vào `data/hose_secorg.csv`). Khảo sát 6 nguồn + endpoint + cách gộp: [`NGUON.md`](NGUON.md).

## Chạy

```bat
cd /d D:\bctc\bctc-scan
python bctc_scan.py                 :: tăng dần, --source all (CafeF + Vietstock + HOSE): từ (ngày cuối trong CSV − 7) tới nay, tối đa --days 30 (~2 phút)
python bctc_scan.py --full          :: lần đầu / dựng lại: 400 ngày, 3 nguồn (~6 phút; lần đầu thêm 1–3 phút xây map HOSE secOrgId)
python bctc_scan.py --days 60 --symbols FPT,VNM
python bctc_scan.py --source cafef  :: 1 nguồn: cafef | vietstock | hose; both = CafeF + Vietstock; all = cả 3 (mặc định)
python bctc_scan.py --download      :: tải PDF các dòng MỚI về pdf\<mã>\ (mặc định KHÔNG tải; pdf/ không lên Drive)
```
Danh sách mã: `MD_ROOT\index-fetcher\raw\vn_screener_meta.csv` (sàn) + tên DN từ `raw\vn_icb_vci.csv`; không có → `realtime-lab\symbols.txt`.
6 luồng, nghỉ 0,05 s/request, 429/5xx chờ 3·i giây, thử lại 4 lần. Nguồn lỗi ≥12 mã liên tiếp mà chưa mã nào OK (chặn IP / timeout)
→ **tắt nguồn đó**, các nguồn khác vẫn chạy (log `! nguon … TAT`); chỉ exit 2 khi không nguồn nào chạy được. Log `logs\bctc_scan.log`.

**Gộp**: khoá `(symbol, ky, loai, pham_vi)` (`rieng` ≡ `cong_ty_me`), giữ dòng có `ngay_cong_bo` + `gio_dang` sớm nhất (`nguon`, `id`, `url_pdf`,
`tieu_de` của nguồn đó); nguồn còn lại ghi `nguon_khac` (dấu phẩy) + `url_pdf_khac` (dấu `|`). Dữ liệu cũ trong CSV gộp theo cùng quy tắc,
nên chạy tăng dần vẫn sửa được ngày sớm hơn cho BCTC đã có.

## Kết quả

`data\bctc_congbo.csv` (UTF-8 BOM, 1 dòng = 1 BCTC đã gộp 3 nguồn, sắp theo ngày giảm dần) + `data\bctc_congbo_latest.parquet` (bản đầy đủ)
+ `data\hose_secorg.csv` (map mã HOSE → secOrgId, tự bổ sung):

| cột | ý nghĩa |
|---|---|
| `id` | `cafef:<ObjectId>` / `vietstock:<FileInfoID>` / `hose:<thư mục UploadDocuments>:<tên file>` của nguồn sớm nhất |
| `nguon`, `nguon_khac`, `url_pdf_khac` | nguồn sớm nhất (`cafef` / `vietstock` / `hose`); các nguồn khác cũng có file này + link PDF tương ứng |
| `symbol`, `exchange`, `ten_dn` | mã, sàn (HOSE/HNX/UPCOM), tên ngắn (ICB Vietcap) |
| `ky` | `2026Q3` quý · `2026H1` soát xét bán niên · `2025FY` kiểm toán năm |
| `loai` | `quy` / `soat_xet` / `kiem_toan` / `khac` |
| `pham_vi` | `hop_nhat` / `rieng` / `cong_ty_me` / `khong_ro` (không ghi = DN không có công ty con) |
| `ngay_cong_bo`, `gio_dang` | sớm nhất trong 3 nguồn: HOSE `createdDate` · Vietstock `LastUpdate` · CafeF thời điểm đăng (4 byte đầu ObjectId) |
| `nam`, `quy` | Year / Quarter gốc (Quarter 5 = cả năm) |
| `tieu_de`, `url_pdf`, `url_nguon`, `ngay_quet` | tiêu đề (CafeF/Vietstock: tên chuẩn; HOSE: `type time · fileName`), link PDF gốc, trang nguồn, ngày quét gần nhất |

Lần chạy `--full` 13/10/2026: 10.381 dòng / 1.463 DN trong 400 ngày; số DN có BCTC quý: 2025Q4 1.103 · 2026Q1 1.110 · 2026Q2 1.102 ·
soát xét 2026H1 854 · kiểm toán 2025FY 1.3xx; 2026Q3 mới 4 DN (mùa công bố bắt đầu ~15/10).

## Pipeline

- Bước `bctc-scan` trong `D:\market-data\run_slot.py` **AM 10:30 và PM 18:30** (WorkDir `BCTC_ROOT\bctc-scan`, retry 2), chạy trên cloud
  (GitHub Actions – cafef.vn OK từ IP Mỹ theo probe 12/10); `data_manifest.py`: `Folder("bctc","bctc-scan", exclude pdf/**)` cloud là chủ,
  `STEP_FOLDERS["bctc-scan"]` đọc thêm `index-fetcher` (IDX_SMALL), có trong `APP_FOLDERS` → Run-Local-Mini kéo về `D:\bctc\bctc-scan\data`.
- App: `datalib.REGISTRY["bctc_congbo"]` (đường dẫn `BCTC_ROOT\bctc-scan\data\bctc_congbo.csv`), trang `pages_khac.tin_tuc`;
  Streamlit Cloud: `cloud_boot.APP_DATA` có `("bctc/bctc-scan", ["/data/bctc_congbo.csv"])` (kéo về `<base>/bctc/bctc-scan`).
- Nếu CafeF chặn IP Mỹ: thêm `bctc-scan` vào `CLOUD_SKIP` của 2 workflow market-*.yml và gọi
  `python D:\market-data\run_slot.py --slot PM --only bctc-scan` trong `Run-Local-Mini.ps1` (+ `sync_data.py up --only bctc-scan --job laptop`,
  đổi `owner="laptop"` trong data_manifest).

## Điểm chưa chắc

- Ngày công bố = giờ CafeF đăng, có thể trễ 0–2 ngày so với ngày DN gửi UBCK; muốn giờ chính xác dùng HOSE `mediafiles/5/{secOrgId}.createdDate`
  hoặc HNX `NextPageTinCPNY_CBTCPH` (xem NGUON.md, chưa triển khai).
- CafeF đôi khi gắn nhầm kỳ (vd "quý 4 năm 2026" đăng 22/09/2026) hoặc đăng 2 bản cùng kỳ; app bỏ trùng theo (mã, kỳ, loại, phạm vi).
- Vietstock chưa thử từ IP Mỹ.
