# VPA container – sản lượng container theo cảng (Hiệp hội Cảng biển VN)

Gom báo cáo tháng của VPA (file Excel, mỗi sheet `T<m>-<yyyy>`) thành 1 bảng dài cảng × tháng, rồi nạp làm **số công bố** cho
mô hình ước/dự báo của app Port Tracker (`port-tracker/nowcast_targets.csv`).

```
python vpa_container.py                    # đọc mọi input/VPA-container*.xlsx
python vpa_container.py --targets          # + cập nhật nowcast_targets.csv
```

**Đầu ra** (`data/`): `vpa_container_long.csv` (region, port, month cuối tháng, teu, nguồn, nhập/xuất ngoại, nhập/xuất nội,
trung chuyển, 20', rỗng, lạnh, sà lan, cảnh báo) · `vpa_container_wide.xlsx` (cảng × tháng + cả năm trước + cảnh báo).

**Quy tắc**
- Tháng năm nay = cột CỘNG của sheet; trống/0 mà lũy kế tăng → lấy chênh lệch lũy kế (VPA đôi khi chỉ điền lũy kế).
- Tháng năm trước (T1–T7/2025 từ file 2026) suy từ chênh lệch cột lũy kế cùng kỳ giữa 2 sheet liền nhau.
- Khi nạp `--targets`: số tháng ghi đè số cũ; số suy từ lũy kế cùng kỳ CHỈ điền ô trống — cột lũy kế VPA có khi chép nhầm năm
  (Chùa Vẽ + Tân Vũ 1T2025 = 108.077 = số T1/2024; HICT 6T2025 suy ra 128.061 vs báo cáo tháng 123.596).
- Cảng trùng tên trong 1 sheet (Nam Hải Đình Vũ 2 dòng, 1 dòng viết "Dình") → giữ dòng số lớn nhất.
- Cảnh báo khi số tháng ≠ chênh lũy kế > 2% (16/10/2026: chỉ 3 dòng tổng vùng Miền Bắc T1–T2, Bắc Trung Bộ T4).
- Ánh xạ cảng VPA → bến app: `PORT_MAP` (29 bến: HP 17, HCM 11 gồm Cái Mép, Đà Nẵng → Tiên Sa, Phước An). Chưa map: Bình Dương,
  Đồng Nai, Quy Nhơn, Nghệ Tĩnh, Cửa Lò, Lào-Việt, Lotus, Phước Long ICD, ĐBSCL (cảng vụ không có trong app / chưa ghép bến).

16/10/2026: file `VPA-container-2025-2026-T7-2026.xlsx` (7 sheet T1–T7/2026) → 48 cảng/vùng, 632 dòng 01/2025–07/2026.
Chưa gắn lịch: VPA gửi file theo tháng, PV2 chép vào `input/` rồi chạy lại.
