# Kích hoạt workflow đúng giờ bằng cron-job.org (18/11/2026)

**Vì sao:** từ 10/11/2026 GitHub chạy lịch `cron` trễ **6–8 tiếng** (Realtime SÁNG hẹn 07:55 chạy lúc 14:17–15:36, CHIỀU hẹn
12:05 chạy 19:31–21:12 → quá giờ kết thúc nên thoát ngay, Live không có dữ liệu từ 10/11; Market EOD 15:20 chạy 23:20–01:40).
Lượt chạy bằng **workflow_dispatch** (nút Run workflow / gọi API) thì GitHub khởi động trong vài giây → cron-job.org (miễn phí,
chính xác tới phút) gọi API GitHub đúng giờ.

Lịch `cron` cũ trong các workflow vẫn giữ làm **dự phòng**: job `guard` bỏ qua lượt cron tới trễ nếu trong 10–12 giờ qua
(News Alert: 1 giờ) đã có lượt chạy tay → không chạy trùng. cron-job.org hỏng / token hết hạn → lịch cũ tự chạy lại (trễ).

## 1. Tạo token GitHub (chỉ quyền chạy Actions của repo Data-System)
1. https://github.com/settings/personal-access-tokens/new (Fine-grained token)
2. **Token name:** `cron-job-org` · **Expiration:** 366 days (ghi lịch nhắc gia hạn trước ngày hết hạn)
3. **Repository access:** *Only select repositories* → `Data-System`
4. **Permissions → Repository permissions → Actions:** `Read and write` (Metadata: Read tự bật)
5. **Generate token** → copy chuỗi `github_pat_...` (chỉ hiện 1 lần). KHÔNG dán vào chat / file / repo.

Token này chỉ chạy / huỷ / chạy lại workflow của Data-System — không đọc được secret, không sửa được code.

## 2. Tạo tài khoản cron-job.org
https://console.cron-job.org → Sign up (miễn phí) → **Settings → Timezone: `Asia/Ho_Chi_Minh`**.

## 3. Tạo cron job đầu tiên (Realtime SANG) rồi Clone cho các job khác
**Create cronjob**:
- **Title:** `Realtime SANG`
- **URL:** `https://api.github.com/repos/phamminhthanh2803-commits/Data-System/actions/workflows/realtime-sang.yml/dispatches`
- **Execution schedule → Custom:** Days of week = Mon–Fri · Hours = 8 · Minutes = 30
- Tab **ADVANCED**:
  - **Request method:** `POST`
  - **Headers** (Add header, 5 dòng):

    | Key | Value |
    |---|---|
    | `Accept` | `application/vnd.github+json` |
    | `Authorization` | `Bearer github_pat_...` (token ở bước 1) |
    | `X-GitHub-Api-Version` | `2022-11-28` |
    | `Content-Type` | `application/json` |
    | `User-Agent` | `cron-job-org-data-system` |
  - **Request body:** `{"ref":"main"}`
  - **Time zone:** `Asia/Ho_Chi_Minh` (nếu ô này có)
- Tab **NOTIFICATIONS:** bật *execution of the cronjob fails*.
- **TEST RUN** → phải ra **HTTP 204 No Content** (GitHub → Actions → Realtime SANG hiện lượt mới `workflow_dispatch`).
  401 = token sai/hết hạn · 403 = token thiếu quyền Actions write · 404 = sai tên file/repo hoặc token không chọn Data-System ·
  422 = body sai (phải đúng `{"ref":"main"}`).
- **Create**.

Các job còn lại: ở danh sách bấm **⋮ → Clone** job trên, đổi **Title**, đổi **tên file .yml cuối URL** và **lịch**:

| Title | Tên file trong URL | Lịch (giờ VN) |
|---|---|---|
| Realtime SANG | `realtime-sang.yml` | Mon–Fri · 8:30 |
| Realtime CHIEU | `realtime-chieu.yml` | Mon–Fri · 12:50 |
| Market EOD | `market-eod.yml` | Mon–Fri · 15:20 |
| Shipping AM | `shipping-am.yml` | Every day · 9:00 |
| Market AM | `market-am.yml` | Every day · 10:30 |
| Market PM | `market-pm.yml` | Every day · 18:30 |
| Shipping PM | `shipping-pm.yml` | Every day · 22:00 |
| News Alert | `news-alert.yml` | Every day · Hours 7–22 · Minutes 0, 15, 30, 45 |

Không cần: App keepalive (2 giờ/lần, trễ vẫn đủ), Keepalive, Probe, BDS AM.

## 4. Kiểm tra
- cron-job.org → mỗi job → **History**: các lần chạy 204.
- GitHub → Actions: lượt chạy có nhãn `workflow_dispatch` đúng giờ; lượt `schedule` tới trễ hiện job `guard` xanh + `run` bị skip.
- App: Live có dữ liệu từ ~08:35 (sáng) / ~12:55 (chiều).

## Gia hạn token (sau 366 ngày)
Tạo token mới như bước 1 → cron-job.org sửa header `Authorization` của cả 8 job (hoặc xoá 7 job, sửa 1 job rồi Clone lại).
Trong lúc token hết hạn, lịch cron cũ của GitHub vẫn chạy (trễ) nên dữ liệu không mất, chỉ chậm.
