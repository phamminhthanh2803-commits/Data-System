# Vessel Itinerary – lộ trình di chuyển từng tàu từ dữ liệu cảng vụ

Sinh chuỗi điểm dừng + chặng + bản đồ cho từng tàu, **không cần AIS**: ghép chuyến thật ở Cảng vụ Hải Phòng (`cvhp_calls.csv`, có cột cảng đi `origin` và cảng đến kế `destination`) với chuyến thật ở Cảng vụ TP.HCM (`cvhcm_calls.csv`, gồm Cái Mép – Vũng Tàu). Lớp tàu / hãng / TEU lấy từ `vessel_master.csv`. Chỉ đọc, không ghi vào dữ liệu nguồn.
Vẽ bản đồ bằng engine `D:\shipping\vessel-route-app\route.py` (searoute + PNG 300 DPI); app Streamlit cũ vẫn dùng được cho bảng "tháng – vùng biển" nhập tay.

## Chạy
```
python vessel_itinerary.py --ship "HAIAN BELL" --from 2026-08-01          # 1 tàu: out\<TAU>_stops.csv, _legs.csv, _route.png
python vessel_itinerary.py --ship "PACIFIC GRACE,WAN HAI 105" --last 12   # nhiều tàu, 12 điểm dừng gần nhất
python vessel_itinerary.py --all --since 2025-01-01 --no-png              # mọi tàu container -> data\ (bước itinerary, Shipping AM)
python vessel_itinerary.py --all --since 2025-01-01 --classes container,general,bulk
```

## Output `--all` (`data/`)
| File | Ý nghĩa |
|---|---|
| `itinerary_stops.csv` | 1 dòng = 1 điểm dừng: tàu, seq, cảng, bến, giờ vào/rời, `inferred`, `source`, toạ độ |
| `itinerary_legs.csv` | 1 dòng = 1 chặng from → to: ngày rời/đến, số ngày, hải lý (searoute), hãng, TEU |
| `vessel_route_pattern.csv` | 1 dòng/tàu: **vòng tuyến hay chạy nhất** (proxy tuyến dịch vụ), các cảng ghé + số lần, tổng hải lý |
| `lane_monthly.csv` | tháng × chặng × hãng: số chặng, số tàu, tổng TEU danh nghĩa → luồng hàng theo tuyến |
| `port_pairs_nm.csv` | cache khoảng cách cặp cảng |

## Cách ghép
- Mỗi chuyến HP sinh 3 điểm: `[origin]` (suy ra) → `HAI PHONG` (thật, có giờ + bến) → `[destination]` (suy ra). Mỗi chuyến HCM sinh điểm thật theo nút `HO CHI MINH` / `CAI MEP` / `VUNG TAU` / `LONG SON` (một chuyến ghé Cái Mép rồi vào Cát Lái thành 2 điểm).
- Điểm **suy ra** (`inferred=1`, dấu `~` trên bản đồ) không có giờ. Nếu nó thuộc vùng HCM và liền kề có chuyến thật ở HCM/Cái Mép (≤ 10 ngày) thì bị bỏ, giữ chuyến thật. Hai điểm liên tiếp cùng cảng thì gộp.
- Hai chuyến **thật** cùng cảng cách nhau > 2 ngày → chèn điểm giả `(ngoai vung du lieu)`: tàu đã đi cảng khác mà hai cảng vụ không thấy (tàu chỉ ghé HCM chạy tuyến quốc tế sẽ có dạng này).
- `source`: `CVHP`, `CVHCM`, `CVHP-origin`, `CVHP-dest`, `gap`; ghép nhiều nguồn nối bằng `+`.

## Giới hạn phải nhớ khi đọc
- Tên cảng nước ngoài ở HP đa số chỉ ở **mức quốc gia** (`CHINA`, `KOREA`, `TAIWAN`...) → đặt ở cảng đại diện (`precision=country`, dấu `*` trên bản đồ): CHINA = Shekou/Hoa Nam, KOREA = Busan, TAIWAN = Kaohsiung, JAPAN = Yokohama... Hải lý và đường vẽ của các chặng này là gần đúng.
- HP chỉ ghi cảng **liền trước / liền sau**, nên vòng tuyến nhiều cảng (HP → Hong Kong → Shekou → Nansha → HP) chỉ hiện 2 đầu.
- Cảng vụ TP.HCM không ghi cảng đi/đến → tàu chỉ ghé HCM/Cái Mép không biết đi đâu (điểm `(ngoai vung du lieu)`).
- Không phải vị trí AIS: không có toạ độ thực, tốc độ, thời gian neo chờ ngoài khơi.

## `ports_geo.csv`
Regex → `port, country, lon, lat, precision` (port / country / inland). Dòng trên ưu tiên hơn; không để dấu phẩy trong `pattern`. Log cuối mỗi lần chạy liệt kê tên chưa có toạ độ.
