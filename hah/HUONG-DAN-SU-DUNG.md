# Hướng dẫn sử dụng — Bộ công cụ lịch tàu HAIAN

Tất cả file nằm trong **`D:\Database\HAH\`** (vị trí ổn định — KHÔNG để trong thư mục cài VS Code vì sẽ bị xoá khi VS Code tự cập nhật).

> `eservice.haiants.vn` là ứng dụng **Flutter Web** (vẽ canvas) nên KHÔNG cào được DOM.
> Mọi công cụ ở đây gọi thẳng API backend `kethop.haiants.vn` mà chính trang web đang dùng.

---

## A. PIPELINE TỰ ĐỘNG (chạy hằng ngày, KHÔNG cần thao tác)

### Đang chạy gì
- **Script:** `D:\Database\HAH\haian-schedule-daily.ps1`
- **Task Scheduler:** "HaiAn Schedule Daily" — chạy **10:00 mỗi ngày**, có **chạy bù** (`StartWhenAvailable`) nếu lỡ giờ.
- Mỗi lần: tự lấy hôm nay → +120 ngày × tất cả tàu → merge vào master → dựng lại file theo voyage.

### File kết quả (ghi đè mỗi lần chạy)
| File | Nội dung |
|---|---|
| `haian-schedule-master.csv` | Tích luỹ tất cả chặng (history) |
| `haian-voyages.csv` | 1 dòng / voyage (Rotation A > B > C, ETD đầu, ETA cuối) |
| `haian-portcalls.csv` | 1 dòng / cảng (Seq, Port, ETA, ETD) |
| `haian-daily.log` | Log mỗi lần chạy |

### Lệnh quản trị (PowerShell)
```powershell
# Chạy thử ngay
powershell -NoProfile -ExecutionPolicy Bypass -File "D:\Database\HAH\haian-schedule-daily.ps1"

# Kích hoạt qua Task Scheduler
Start-ScheduledTask -TaskName 'HaiAn Schedule Daily'

# Xem trạng thái / kết quả lần cuối (LastTaskResult = 0 là thành công)
Get-ScheduledTask -TaskName 'HaiAn Schedule Daily' | Get-ScheduledTaskInfo

# Đổi giờ chạy (vd 7h sáng)
Set-ScheduledTask -TaskName 'HaiAn Schedule Daily' -Trigger (New-ScheduledTaskTrigger -Daily -At 7:00am)

# Gỡ task
Unregister-ScheduledTask -TaskName 'HaiAn Schedule Daily'
```

### Tinh chỉnh (sửa đầu file .ps1)
- `$LookAheadDays` (mặc định 120): quét bao nhiêu ngày tới.
- `$StepDays` (7): bước nhảy ETD.
- `$OutDir`: thư mục lưu data.

> ⚠️ Pipeline chỉ quét TỪ hôm nay trở đi (không backfill quá khứ). History dựa vào lần seed
> ban đầu + tích luỹ mỗi ngày. Máy phải bật để task chạy (có chạy bù khi bật lại).

---

## B. CÔNG CỤ THỦ CÔNG (browser Console — để backfill nhiều năm)

Chạy trên tab **https://eservice.haiants.vn/#/Schedule** → F12 → Console
(lần đầu Chrome chặn dán: gõ `allow pasting` rồi Enter).

### B1. `scrape-haian-api.js` — cào nhiều năm
- Mở file, copy toàn bộ, dán vào Console → Enter.
- Sửa `CONFIG` đầu file: `START`, `END`, `STEP_DAYS`, `CONCURRENCY`.
- Chạy song song có kiểm soát (back-off khi bị giới hạn, jitter, checkpoint mỗi 1000 request).
- Kết thúc tải `haian-schedule.csv` + `haian-schedule.json`.
- Điều khiển: `__STOP__=true` (dừng), `__EXPORT__()` (xuất lại), `__RAW__` (dữ liệu).

### B2. `parse-by-voyage.js` — gộp theo voyage
- Chạy sau B1 (cùng tab) → tự dùng dữ liệu trong bộ nhớ.
- Nếu đã F5/đóng tab: gõ `__LOADJSON__()` → chọn file `haian-schedule.json`.
- Xuất `haian-portcalls.csv` + `haian-voyages.csv`.

---

## C. DỮ LIỆU & DEDUPE

- **Khoá khử trùng = `VoyDetail + PolId + PodId`** (1 chặng của 1 chuyến cụ thể).
- ETD KHÔNG nằm trong khoá → tàu delay đổi ngày, ETD trùng không sinh bản ghi giả.
- Gặp lại chặng cũ → ghi đè bằng số liệu mới nhất.
- API trả **mọi cặp cảng đi–đến (O-D)**; file `voyages`/`portcalls` đã dựng lại thành
  hành trình tuần tự (mỗi cảng có giờ đến ETA + giờ đi ETD).

### Lọc tàu HAH vận hành
Lọc theo cột **`Service`** (mã tuyến HAH, gồm cả tàu liên doanh) — KHÔNG lọc theo tên "HAIAN"
(sẽ sót tàu liên doanh tên khác). Có thể lọc trực tiếp trong Excel.

---

## D. API tham khảo
| API | Method | Trả về |
|---|---|---|
| `GET  https://kethop.haiants.vn/Booking/GetAllVessel` | GET | `[{shipId, shipName}]` |
| `POST https://kethop.haiants.vn/Booking/ShipSchedule?ShipId=<GUID>&ETD=<MM/DD/YYYY>` | POST (body rỗng) | Mảng chặng (leg) |

Header bắt buộc: `Referer: https://eservice.haiants.vn/`. ETD định dạng **MM/DD/YYYY**.
Không cần token đăng nhập (`credentials: omit`).


## Cập nhật 14/09/2026 — gộp vào hub
Task cũ `HaiAn Schedule Daily` 10:00 đã gỡ → nay là bước `haian` trong **Shipping AM 09:00** (`D:\shipping\Run-Shipping.ps1`, gọi sang `haian-schedule-daily.ps1` tại đây; data vẫn ghi cạnh script).
