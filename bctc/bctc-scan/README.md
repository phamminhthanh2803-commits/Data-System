# bctc-scan — theo dõi BCTC mới công bố toàn thị trường (13/10/2026)

Quét **báo cáo tài chính vừa đăng** (quý / soát xét bán niên / kiểm toán năm; hợp nhất / riêng / công ty mẹ) của toàn bộ mã
HOSE + HNX + UPCOM, ghi 1 file long-format cho app Market Data (tab **Tin tức › Báo cáo tài chính mới**).
Nguồn chính **CafeF** `FileBCTC.ashx` (theo từng mã, ~1 phút toàn thị trường), dự phòng **Vietstock** `data/GetDocument`.
Khảo sát 6 nguồn + endpoint chi tiết: [`NGUON.md`](NGUON.md).

## Chạy

```bat
cd /d D:\bctc\bctc-scan
python bctc_scan.py                 :: tăng dần: từ (ngày cuối trong CSV − 7) tới nay, tối đa --days 30   (~1 phút)
python bctc_scan.py --full          :: lần đầu / dựng lại: 400 ngày (CafeF Year=2025 + 2026 cho 1.559 mã, ~2 phút, 3.118 request)
python bctc_scan.py --days 60 --symbols FPT,VNM
python bctc_scan.py --source vietstock   :: dự phòng (cần token + cookie, tự lấy); --source both để đối chiếu
python bctc_scan.py --download      :: tải PDF các dòng MỚI về pdf\<mã>\ (mặc định KHÔNG tải; pdf/ không lên Drive)
```
Danh sách mã: `MD_ROOT\index-fetcher\raw\vn_screener_meta.csv` (sàn) + tên DN từ `raw\vn_icb_vci.csv`; không có → `realtime-lab\symbols.txt`.
6 luồng, nghỉ 0,05 s/request, 429/5xx chờ 3·i giây, thử lại 4 lần; >50 % mã lỗi → exit 2 (nguồn chặn). Log `logs\bctc_scan.log`.

## Kết quả

`data\bctc_congbo.csv` (UTF-8 BOM, append theo khoá `id`, sắp theo ngày giảm dần) + `data\bctc_congbo_latest.parquet` (bản đầy đủ):

| cột | ý nghĩa |
|---|---|
| `id` | `cafef:<ObjectId>` hoặc `vietstock:<FileInfoID>` (khoá dedup) |
| `symbol`, `exchange`, `ten_dn` | mã, sàn (HOSE/HNX/UPCOM), tên ngắn (ICB Vietcap) |
| `ky` | `2026Q3` quý · `2026H1` soát xét bán niên · `2025FY` kiểm toán năm |
| `loai` | `quy` / `soat_xet` / `kiem_toan` / `khac` |
| `pham_vi` | `hop_nhat` / `rieng` / `cong_ty_me` / `khong_ro` (không ghi = DN không có công ty con) |
| `ngay_cong_bo`, `gio_dang` | thời điểm CafeF đăng file (4 byte đầu ObjectId; khớp hậu tố ddmmyyyyHHMMSS tên file); Vietstock: `LastUpdate` |
| `nam`, `quy` | Year / Quarter gốc (Quarter 5 = cả năm) |
| `tieu_de`, `url_pdf`, `url_nguon`, `nguon`, `ngay_quet` | tên chuẩn CafeF, link PDF gốc, trang mã, nguồn, ngày quét |

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
