# Cảng vụ TP.HCM – kế hoạch điều động tàu thuyền (cvhcm)

Bản TP.HCM của tool Hải Phòng (`D:\shipping\cangvu-haiphong`), dùng chung thuật toán ghép chuyến + tổng hợp (import từ `cvhp_scrape.py`) và chung `vessel_master.csv` (làm giàu tàu bằng `vessel_enrich.py` bên HP, có tham số `--port`).
Vùng nước Cảng vụ TP.HCM gồm cả **Cái Mép – Thị Vải – Vũng Tàu** (BR-VT sáp nhập vào TP.HCM 07/2025) → dữ liệu có TCIT, TCTT, CMIT, SSIT, Gemalink, các mỏ dầu khí, Côn Đảo.

## Nguồn
`https://cangvuhanghaitphcm.gov.vn/index.aspx?page=shipschedule&cat=3107` – ASP.NET WebForms: chọn ngày bằng POST-back (`ctl22$txtDate`, `ctl22$btnSearch`, kèm `__VIEWSTATE`/`__EVENTVALIDATION` của trang trước). Lịch sử lùi được tới 2019. 3 bảng: **Tàu đến** (`GridView_TauDen`) / **Tàu rời** (`GridView_TauRoi`) / **Tàu di chuyển** (`GridView_TauDiChuyen`).
Trang `page=shipinport` ("Vị trí tàu tại cảng") là ảnh chụp tàu ĐANG ở cảng theo ngày, không có DWT, còn dính tàu cũ từ 2008 → không dùng.

Cột: Tên tàu (có dấu `*` đầu → cột `mark`), Quốc tịch, Hô hiệu, DWT, LOA, mớn, **Loại hàng + khối lượng** (`CONTAINER 1883`, `LPG 46822`, `NIL` = không hàng; đơn vị của số chưa xác định, để nguyên ở `cargo_qty`), Vị trí neo đậu (mã cầu), giờ, tàu lai, đại lý, tuyến luồng. Không có GT, không có cảng đi/đến ngoài HCM.

## Chạy
```
python cvhcm_scrape.py                       # kéo lại [hôm nay-3 .. ngày mai] rồi rebuild (bước cvhcm, Shipping AM 9:00)
python cvhcm_scrape.py --from 2019-01-01     # backfill (bỏ qua ngày đã có; --force để kéo lại)
python cvhcm_scrape.py --no-fetch            # rebuild + map lại mã cầu theo berths.csv mới
```

## Output (`data/`)
| File | Ý nghĩa |
|---|---|
| `cvhcm_events.csv` | 1 dòng = 1 sự kiện; `from`/`to` = mã cầu gốc, `terminal_from`/`terminal_to` = bến đã map qua `berths.csv` |
| `cvhcm_calls.csv` | 1 chuyến = Vào → Di chuyển* → Rời cùng tàu (DWT đếm 1 lần), `berths` theo tên bến đã map |
| `cvhcm_terminal_daily.csv` | ngày × bến (đã map, mã cầu chưa map giữ nguyên mã) |
| `cvhcm_daily.csv` | tổng theo ngày |
| `cvhcm_calls_enriched.csv`, `cvhcm_monthly_operator.csv`, `cvhcm_monthly_terminal.csv` | do `vessel_enrich.py --port hcm --apply` tạo: kèm loại tàu, hãng, TEU |

## Map mã cầu → bến (3 lớp)
1. `berth_area_map.csv` – bảng tra **chính thức** mã cầu/phao → khu vực cảng, dựng bởi `cvhcm_berthmap.py` từ trang "Vị trí tàu tại cảng" (`page=shipinport`, có 2 cột Khu vực cảng + Cầu/Phao). 452 mã, 162 khu vực, phủ 99,6% sự kiện. Cập nhật thứ Hai hằng tuần (bước `cvhcm-berthmap`).
2. `areas.csv` – gán tay khu vực → tên bến ngắn, chủ bến, mã CK, loại (`kind`), cụm địa lý (`node`: HO CHI MINH / CAI MEP / VUNG TAU / LONG SON / ngoài khơi...). Khu vực chưa gán tay: giữ tên khu vực, `kind` và `node` suy bằng từ khoá.
3. `berths.csv` – regex dự phòng, chỉ dùng cho mã cầu chưa từng thấy trong bảng chính thức.
Kết quả ghi ra `terminals_hcm.csv` (bến → group, ticker, kind, node, area), được app, vessel_enrich và vessel-itinerary dùng chung.
Những chỗ regex từng đoán sai và bảng chính thức đã sửa: `V1..V4` = VICT; `K1..K12` = Cảng Sài Gòn, `K15` = Bến Nghé, `K16` = Rau Quả, `K17-18` = Bông Sen; `BN_PH` thuộc cụm Cát Lái (Tân Cảng Phú Hữu); `P.HUU 1` = trạm nghiền xi măng; `PLxx` = bến phao Gemadept.

## Bẫy
- Mỗi request POST phải mang `__VIEWSTATE` của response trước; lỗi thì script tự GET lại trang gốc.
- Script kiểm tra ô ngày trong response đúng ngày yêu cầu (tránh server trả về hôm nay).
- Tên tàu đôi khi kèm hô hiệu `PACIFIC GRACE/3FQJ7` → cắt phần sau `/`.
- ~200 sự kiện/ngày (gấp 2,5 lần HP); backfill 2019→nay ≈ 1 giờ.
- **Gãy chuỗi 07–08/2025**: các bến Cái Mép – Thị Vải (TCIT, TCTT, CMIT, SSIT, Gemalink...) chỉ xuất hiện từ 07–08/2025 khi Cảng vụ Vũng Tàu nhập về; TCIT lên đủ từ 11/2025. Trước đó dữ liệu chỉ có khu TP.HCM cũ (Cát Lái, Hiệp Phước, Nhà Bè...) + tàu neo Vũng Tàu chờ vào sông. So sánh YoY toàn cảng vụ qua mốc này phải tách nhóm bến.
