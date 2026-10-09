# Data-System — chạy 3 hub pipeline trên GitHub Actions (miễn phí), dữ liệu ở Google Drive

Repo này là **code** của 3 hub `D:\market-data`, `D:\shipping`, `D:\bctc` (+ `hah/haian_pull.py`) đóng gói bởi `pack_code.py`.
**Dữ liệu** (CSV master, parquet…) KHÔNG nằm trong repo mà ở Google Drive `gdrive:pipeline-data/<hub>/<thư mục>` (lặp y cấu trúc `D:\`),
đồng bộ bằng `rclone` trước/sau mỗi lần chạy (`sync_data.py` + `data_manifest.py`).

```
GitHub Actions (Linux, Mỹ)                     Laptop Windows
┌───────────────────────────┐                  ┌─────────────────────────────────────────┐
│ 4 slot/ngày:              │  rclone          │ 8:30  Run-Local-Cvhcm.ps1  (cvhcm, IP VN)│
│  Shipping AM 9:00         │◄────────────────►│ 18:40 Run-Local-Mini.ps1   (IDX/Bursa,   │
│  Market AM 10:30          │  Google Drive    │        nganh-ck Excel, bonds thứ Hai,    │
│  Market PM 18:30          │  pipeline-data   │        kéo data cho app)                 │
│  Shipping PM 22:00        │  (~1,9 GB)       │ App Streamlit: local\Chay-app-*.bat      │
└───────────────────────────┘                  └─────────────────────────────────────────┘
```

Bước **bỏ qua trên cloud** (env `CLOUD_SKIP`): `cvhcm`, `cvhcm-berthmap` (Cảng vụ TP.HCM chặn IP nước ngoài), `nganh-ck` (Excel COM),
`bonds` (bond-pivot 3,5 GB không lên Drive). `valuation-region` trên cloud bỏ IDX + Bursa (env `REGION_SKIP=idx,bursa`, Cloudflare 403);
laptop chạy `region.py --only JCI,LQ45,FBMKLCI`. Chi tiết ai ghi thư mục nào: `python data_manifest.py`.

**4 task Task Scheduler cũ (Run-Market.ps1 / Run-Shipping.ps1) vẫn chạy, chưa đụng.** Chỉ tắt khi cloud ổn định ≥ 1 tuần (mục 7).

---

## Các file trong repo

| File | Việc |
|---|---|
| `pack_code.py` | chép code 3 hub từ `D:\` vào repo (whitelist .py/.md/cấu hình nhỏ; bỏ data/log/cache), quét secret. Chạy lại mỗi khi sửa code ở `D:\`. |
| `data_manifest.py` | bản đồ dữ liệu: thư mục nào mỗi bước đọc/ghi, chủ (cloud/laptop), lên Drive hay không. `--size` = ước dung lượng. |
| `sync_data.py` | `down`/`up` theo bước sẽ chạy hôm nay (cùng luật `--only`, `CLOUD_SKIP` với runner), `app` (kéo data cho app), `seed` (lần đầu). |
| `seed_drive.ps1` | lần đầu: `D:\` → Drive (~1,9 GB, bỏ bond-pivot) + dựng `D:\pipeline-data` (cangvu-hcm raw + junction bond-pivot). |
| `.github/workflows/*.yml` | 4 slot cron + `keepalive.yml` (commit rỗng ngày 1 và 16 hằng tháng để GitHub không tắt cron sau 60 ngày không commit). |
| `local\Run-Local-Mini.ps1` | 18:40: IDX/Bursa → nganh-ck → (thứ Hai) bonds → đẩy 2 file region lên Drive → kéo data cho app. Đợi cloud Market PM xong trước (tối đa 150'). |
| `local\Run-Local-Cvhcm.ps1` | 8:30: cvhcm (+ cvhcm-berthmap thứ Hai) → đẩy `shipping/cangvu-hcm` lên Drive (trước cloud Shipping AM 9:00). |
| `local\Chay-app-market.bat`, `local\Chay-app-port-tracker.bat` | bản copy 2 launcher app với `MD_ROOT`/`SHIP_ROOT` = `D:\pipeline-data\...` (file gốc không sửa). |
| `local\schtasks-mau.txt` | lệnh `schtasks /create` mẫu (CHƯA đăng ký). |
| `market-data/requirements.txt` | thư viện Python dùng chung (cloud `pip install -r`). |
| `cloud-probe/` | probe nguồn từ GitHub Actions 07/10/2026 (31/34 OK). |

Secret cần đặt trên GitHub (Settings → Secrets and variables → Actions → New repository secret):

| Secret | Bắt buộc | Nội dung |
|---|---|---|
| `RCLONE_CONF` | có | file `rclone.conf` (remote `gdrive`) mã hoá base64 — mục 2 |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | không | runner gửi cảnh báo FAIL/STALE qua Telegram; không có thì chỉ ghi log + Summary của job |

Quét secret (`pack_code.py`): **không** thấy token/api_key/password/cookie gắn cứng trong code — các "token" trong bond-pivot/VSDC là token CSRF lấy lúc chạy.

---

## Làm từng bước (lần đầu)

### 1. Cài rclone trên Windows và nối Google Drive
Mở PowerShell (không cần admin):
```powershell
winget install Rclone.Rclone
```
Đóng PowerShell, mở lại để có `rclone` trong PATH (nếu vẫn không có, file nằm ở
`C:\Users\User\AppData\Local\Microsoft\WinGet\Packages\Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe\rclone-v1.75.1-windows-amd64\rclone.exe`
— các script `.ps1` tự tìm theo thứ tự PATH → đường dẫn này).
```powershell
rclone config create gdrive drive scope=drive
```
Trình duyệt mở ra → đăng nhập Google của PV2 → Allow. Kiểm tra: `rclone lsd gdrive:` (liệt kê thư mục Drive). Tạo thư mục gốc:
```powershell
rclone mkdir gdrive:pipeline-data
```

### 2. Đưa cấu hình rclone lên GitHub Secrets
```powershell
rclone config file                       # in đường dẫn rclone.conf (thường C:\Users\User\AppData\Roaming\rclone\rclone.conf)
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$env:APPDATA\rclone\rclone.conf")) | Set-Clipboard
```
Chuỗi base64 đã nằm trong clipboard → GitHub repo → Settings → Secrets and variables → Actions → New repository secret →
Name `RCLONE_CONF`, Secret: dán (Ctrl+V) → Add secret. (Tuỳ chọn: thêm `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.)
Không bao giờ commit file rclone.conf vào repo (`.gitignore` đã chặn).

### 3. Đưa dữ liệu lên Drive lần đầu (~1,9 GB, 10–30 phút tuỳ mạng)
```powershell
cd D:\cloud-deploy
python data_manifest.py --size             # xem ước lượng từng thư mục, tổng phải < 4 GB
powershell -ExecutionPolicy Bypass -File .\seed_drive.ps1
```
Script copy `D:\market-data\{market-valuation,index-fetcher,transmission-fetcher,nso-fetcher,macro-fetcher,vsdc-accounts}`,
`D:\shipping\{VHBS-ConTex,cangvu-haiphong,cangvu-hcm,cangvu-toanquoc,vessel-itinerary,Alibra-scraper,BCTI-scraper}`,
`D:\Database\Logistics\HAH\haian-*.csv` lên `gdrive:pipeline-data/...` (bỏ code, log, `raw/` HTML cache, `cbtt/`, bond-pivot),
rồi dựng `D:\pipeline-data`: chép `D:\shipping\cangvu-hcm` (cả `raw/`) + tạo junction `D:\pipeline-data\market-data\bond-pivot → D:\market-data\bond-pivot`.
Chạy lại an toàn (chỉ chép file mới/đổi). Kiểm tra: `rclone size gdrive:pipeline-data`.

### 4. Push repo lên GitHub
Repo `github.com/phamminhthanh2803-commits/Data-System` hiện chỉ có `cloud-probe/`; bản này đã gom `cloud-probe/` thành thư mục con, nên thay toàn bộ:
```powershell
cd D:\cloud-deploy
git remote add origin https://github.com/phamminhthanh2803-commits/Data-System.git
git push --force -u origin main          # thay lịch sử cũ (chỉ có cloud-probe, đã nằm trong repo này)
```
Lần đầu Git hỏi đăng nhập GitHub → chọn "Sign in with your browser". Sau này mỗi khi sửa code ở `D:\`:
```powershell
cd D:\cloud-deploy; python pack_code.py; git add -A; git commit -m "cap nhat code"; git push
```
Repo nên để **Private** lúc đầu (2.000 phút Actions/tháng); xem mục 7.

### 5. Chạy tay 1 bước để kiểm tra
GitHub → tab **Actions** → chọn **Market PM** (cột trái) → nút **Run workflow** → ô `only` gõ `icb-vci` → Run workflow.
Job mất ~4–6 phút (cài thư viện lần đầu lâu hơn). Xem: bấm vào job → "Chay pipeline market-data PM" → log; phần **Summary** có dòng status.
Kết quả mong đợi: `OK | <giờ> | loi:  | cu:` và trên Drive `gdrive:pipeline-data/market-data/index-fetcher/raw/vn_icb_vci.csv` có giờ mới
(`rclone lsl gdrive:pipeline-data/market-data/index-fetcher/raw/vn_icb_vci.csv`). Artifact `market-PM-<id>` chứa log + status (giữ 30 ngày).
Nếu lỗi `Thieu secret RCLONE_CONF` → mục 2; lỗi `rclone lsd` → base64 sai (dán lại); lỗi pip → xem log bước "Cai thu vien Python".

Sau đó thử cả slot: Run workflow với `only` để trống (Market PM ~60–90 phút vì tvhistory). Trong thời gian đầu, cloud và 4 task laptop
cùng chạy song song (laptop ghi `D:\`, cloud ghi Drive) — không ảnh hưởng nhau.

### 6. Đăng ký 2 task laptop (khi cloud đã chạy đúng)
Chạy thử tay trước:
```powershell
powershell -ExecutionPolicy Bypass -File D:\cloud-deploy\local\Run-Local-Cvhcm.ps1
powershell -ExecutionPolicy Bypass -File D:\cloud-deploy\local\Run-Local-Mini.ps1 -NoWait
```
Log ở `D:\pipeline-data\logs\`. Rồi dán 2 lệnh trong `local\schtasks-mau.txt` để đăng ký "Pipeline Local Cvhcm" 8:30 và "Pipeline Local Mini" 18:40.
Mở app bằng `local\Chay-app-market.bat` và `local\Chay-app-port-tracker.bat` (đọc `D:\pipeline-data`).

### 7. Sau 1 tuần: xem phút Actions và quyết định
GitHub → ảnh đại diện → Settings → **Billing and plans** → Plans and usage → Actions: xem "minutes used". Ước ~2.500–3.200 phút/tháng
(laptop ~1h45/ngày; runner 4 vCPU có thể nhanh hơn). Repo private chỉ có 2.000 phút/tháng:
- vượt → đổi repo sang **Public** (Settings → General → Danger Zone → Change visibility; phút không giới hạn; code đã quét secret, dữ liệu không nằm trong repo), hoặc
- chuyển slot nặng (Market PM) sang Modal.com (30 USD credit/tháng, xem `cloud-probe/README.md`).
Khi ổn: tắt 4 task cũ `schtasks /Change /TN "<tên task>" /DISABLE` (không xoá); app chuyển sang `local\Chay-app-*.bat`.

---

## Port Tracker: ghép dữ liệu liên tục (09/10/2026)
App Port & Vessel Tracker không còn tự gọi trang nguồn khi mở. Bước `port-tracker` (Shipping AM) và `port-tracker-pm` (Shipping PM) chạy
`shipping/port-tracker/pt_update.py`: nạp kho chia sẻ `store/` → gọi nguồn các ngày thiếu/chưa chốt (cửa sổ 14 ngày) → xuất lại
`store/events/<cảng vụ>/<YYYY-MM>.parquet` + `store/days/<cảng vụ>.csv` (1 file = 1 cảng vụ 1 tháng, cả lịch sử ≈ 50 MB).
- Cloud kéo 11 cảng vụ (`CLOUD=1` → bỏ HCM) và là **chủ** thư mục `shipping/port-tracker` trên Drive (sync, bỏ `cache/` + sqlite).
- Cảng vụ TP.HCM chặn IP nước ngoài → laptop kéo (`PT_AUTHS=HCM`) trong `Run-Local-Cvhcm.ps1` 8:30 và `Run-Local-Mini.ps1` 18:40, chỉ đẩy
  2 đường dẫn `store/events/HCM/**`, `store/days/HCM.csv` (`laptop_only` trong `data_manifest.py`; cloud không sync 2 đường dẫn này).
- App (`local\Chay-app-port-tracker.bat`) kéo `store/` về qua `sync_data.py app` rồi `livedata.import_store()` chỉ nạp file đổi vào sqlite riêng.
- Seed lần đầu 09/10/2026: `pt_update.py --export-all --no-pull` ở `D:\shipping\port-tracker` → `rclone copy store/ gdrive:pipeline-data/shipping/port-tracker/store`.

## Vận hành hằng ngày
- Lịch (UTC = VN − 7): Shipping AM `0 2 * * *` (9:00), Market AM `30 3 * * *` (10:30), Market PM `30 11 * * *` (18:30), Shipping PM `0 15 * * *` (22:00).
  GitHub có thể trễ 5–30 phút; `concurrency: pipeline` → job sau đợi job trước, không chạy đè.
- Mỗi job: checkout → pip (cache) → tesseract + rclone → `sync_data.py down` (chỉ thư mục các bước hôm nay cần) → `run_slot.py --slot` →
  `sync_data.py up` (**luôn chạy**, kể cả bước lỗi; chủ thư mục dùng `rclone sync --max-delete 50`, bên không phải chủ chỉ `copy` vài file) → artifact log.
- Xem trạng thái nhanh: `rclone cat gdrive:pipeline-data/market-data/status-PM.txt` (hoặc Actions → job → Summary).
- Chạy tay 1 bước: Actions → workflow → Run workflow → `only=a,b`. Chạy tay ở laptop (code repo, data D:\pipeline-data):
  `$env:MD_ROOT='D:\pipeline-data\market-data'; python D:\pipeline-data\market-data\run_slot.py --slot PM --only icb-vci`.
- Thêm bước mới: sửa `run_slot.py` của hub ở `D:\` **và** thêm dòng trong `STEP_FOLDERS` (`data_manifest.py`) để job biết thư mục cần đồng bộ
  (bước không có trong `STEP_FOLDERS` → không kéo/đẩy gì → chạy trên thư mục rỗng!). Rồi `pack_code.py` + push.
- Khi code hub (`D:\...`) đổi: `python pack_code.py` rồi commit/push. Cloud luôn chạy code trên GitHub, laptop chạy code copy từ repo vào `D:\pipeline-data`.

## Cách hoạt động (để sửa khi cần)
- Script của hub ghi dữ liệu **cạnh script** (`os.path.dirname(__file__)`), nên trên cloud code và data cùng cây: `MD_ROOT=$GITHUB_WORKSPACE/market-data`
  (checkout) + rclone copy data vào đúng thư mục đó; rclone lọc `*.py *.md logs/ ...` nên code không bao giờ lên Drive, data không bao giờ vào git.
  Laptop cũng vậy: `Run-Local-*.ps1` robocopy code từ `D:\cloud-deploy` vào `D:\pipeline-data\<hub>` rồi chạy.
- `runlib.py` thêm `--skip a,b` / env `CLOUD_SKIP` và `select_steps()` (cùng luật chọn bước cho runner và `sync_data.py`).
  `market-valuation/region.py` thêm env `REGION_SKIP`. `bctc/nganh-chung-khoan/{build_presentation,build_workbook_logic,drivers_extra,backfill_drivers}.py`
  đọc `D:\market-data` qua `MD_ROOT` (mặc định không đổi). Các thay đổi này đã áp vào bản gốc ở `D:\` (không ảnh hưởng 4 task cũ vì chúng gọi ps1).
- Chủ thư mục (tránh ghi đè): cloud là chủ mọi thư mục trừ `shipping/cangvu-hcm` (laptop; cloud chỉ ghi 3 file `*_enriched/monthly*` của `vessel_enrich.py`)
  và `market-data/bond-pivot` (laptop, không lên Drive). Laptop được ghi thêm 2 file `valuation-region-master/wide.csv`.
  `Run-Local-Mini` đợi `status-PM.txt` trên Drive có ngày hôm nay rồi mới chạy để không đụng cloud Market PM.
- Không lên Drive: `index-fetcher/raw/vci_foreign` **có** lên (1.600 file nhỏ, cloud ghi hằng ngày); `cangvu-haiphong/raw`, `cangvu-hcm/raw` (HTML cache),
  `transmission-fetcher/cbtt` (811 MB PDF công cụ riêng), `sbv_cache`, bond-pivot: không. Tổng ~1,9 GB (Drive còn 6,8 GB).
- Keepalive: `keepalive.yml` commit rỗng ngày 1 và 16 hằng tháng (GitHub tắt cron nếu repo không có commit 60 ngày).
