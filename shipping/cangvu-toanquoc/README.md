# Cảng vụ toàn quốc – khảo sát nguồn và bộ thu thập

Mục tiêu: gộp kế hoạch điều động tàu của mọi cảng vụ hàng hải thành một bộ dữ liệu chuyến tàu cả nước.
Khảo sát ngày 29/09/2026. Danh sách nguồn: `authorities.csv`. Script dò lại: `khao-sat\probe*.py`.

## Kết quả khảo sát: 4 kiểu nền tảng

| Kiểu | Cảng vụ | Cách lấy | Trạng thái |
|---|---|---|---|
| **public-kh** (hệ thống thủ tục điện tử của Bộ, mỗi cảng vụ 1 máy chủ) | Quảng Ninh (đến đầu 2025), Hải Phòng, Thái Bình, Thanh Hoá, Hà Tĩnh, Đà Nẵng + Quảng Nam, Bình Thuận, Đồng Nai, Kiên Giang | API JSON không cần đăng nhập | **Đã làm** – `pkh_scrape.py` |
| **ASP.NET riêng** | Hải Phòng (csdltau, `d=`), TP.HCM + Vũng Tàu (POST ngày), Quảng Ninh kht1 (POST ngày, từ 2025), Nha Trang (như TP.HCM), Cần Thơ (`d=`, 4 khu vực) | HTML bảng | **Đã làm** – `cangvu-haiphong`, `cangvu-hcm`, `aspx_scrape.py` |
| **Đăng file hằng ngày** | Nghệ An (PDF), Quy Nhơn (ảnh JPG), Quảng Trị + Quảng Bình, Thừa Thiên Huế | cần tách bảng PDF / OCR | **Chưa làm** |
| **Không truy cập được** | Quảng Ngãi, An Giang, Đồng Tháp (trang Plesk mặc định); Nam Định, Mỹ Tho, Cà Mau (không phân giải tên miền) | – | **Không có nguồn** |

Vũng Tàu đã hợp nhất vào TP.HCM và Quảng Nam vào Đà Nẵng từ 01/08/2025 (Quyết định 1086/QĐ-BXD), nên nằm trong dữ liệu hai cảng vụ đó.
Cổng trung ương `hanghai.moc.gov.vn/public-kh` chạy cùng phần mềm nhưng không có dữ liệu; mỗi máy chủ cảng vụ chỉ trả dữ liệu của chính mình.

## Nền tảng public-kh
Trang công khai: `<base>#/tra-cuu/ke_hoach/0/0/KeHoachDieuDongTau2`. API là các request chính trang đó gọi (portlet `vma_WAR_TichHopGiaoThongportlet`):
`vma_itinerary_schedule_come` (tàu đến, `timeOfArrival=dd/mm/yyyy`), `vma_itinerary_schedule_leave`, `vma_schedule_shifting`, và `findVmaItineraryScheduleByItineraryNo` (chi tiết 1 chuyến).
- Có sẵn **IMO, hô hiệu, GT, DWT, NT, LOA, quốc tịch, mã chuyến `itineraryNo`** → nối lượt đến – di chuyển – rời chính xác theo mã chuyến, không cần đoán theo tên.
- Chi tiết chuyến có **cảng trước / cảng kế theo UN/LOCODE, loại hàng, hàng còn trên tàu, chủ tàu**.
- Bỏ tham số ngày thì API trả toàn bộ lịch sử. Máy chủ lớn (Hải Phòng, Quảng Ninh, Đồng Nai) báo 504 nếu lấy một lần → `--full` kéo theo trang 1.500 bản ghi.
- Lịch sử thực tế bắt đầu khoảng 2020 (vài bản ghi lẻ trước đó). Có bản ghi ngày lỗi (năm 0003, 3023) và kế hoạch đặt trước nhiều tháng → đã lọc.
- **Chỉ lấy trường vận hành của tàu và chuyến.** Không lấy tên thuyền trưởng, số thuyền viên, điện thoại/email đại lý. Không dùng endpoint nội bộ `findVmaItineraryScheduleURL` dù nó mở, vì không thuộc trang công khai và chứa dữ liệu cá nhân.

## Chạy
```
python pkh_scrape.py                 # hằng ngày: [hôm nay-3 .. +1] cho 9 cảng vụ, cập nhật theo id bản ghi
python pkh_scrape.py --full          # lần đầu: toàn bộ lịch sử
python pkh_scrape.py --details 400   # tra cảng trước / cảng kế cho 400 chuyến tàu >= 3.000 DWT gần nhất mỗi cảng vụ
python aspx_scrape.py                # Quảng Ninh kht1, Nha Trang, Cần Thơ
python aspx_scrape.py --from 2019-01-01
python national_build.py             # gộp toàn quốc
```
Task Shipping AM 9:00: bước `cv-pkh` (kèm 150 chi tiết/ngày), `cv-aspx`, `cv-national`, rồi `cvhp-vessels`, `itinerary`.

## Output
| File | Nội dung |
|---|---|
| `data\<MÃ>\events.csv`, `calls.csv`, `terminals.csv` | từng cảng vụ (QNH, HPH, TBH, THA, HTH, DNG, BTN, DNI, KGG, QNK, NTG, CTO) |
| `data\<MÃ>\details.csv` | cảng trước / cảng kế / hàng của từng chuyến (public-kh) |
| `data\imo_map.csv` | tên tàu → IMO, hô hiệu từ mọi máy chủ public-kh; `vessel_enrich.py` dùng để điền IMO cho tàu ở HP/HCM |
| `data\national_calls.csv` | 1 dòng = 1 chuyến, mọi cảng vụ, cột chung + `auth`, `source` |
| `data\national_terminals.csv` | cảng vụ, bến, nhóm, mã CK, loại |
| `data\national_monthly.csv` | tháng × cảng vụ: số chuyến, số tàu, tổng DWT, tổng GT, số chuyến tàu ≥ 5.000 DWT |
| `data\coverage.csv` | mỗi cảng vụ: nguồn, khoảng ngày, số chuyến, tỷ lệ có IMO, tỷ lệ có cảng đi/đến |

Mã cảng vụ trong bộ toàn quốc (bắc → nam): QN, HP, TBH, THA, HTH, DNG, NTG, BTN, DNI, HCM, CTO, KGG.
Quảng Ninh nối 2 nguồn: public-kh đến ngày đầu tiên kht1 có dữ liệu, sau đó kht1.

## Giới hạn
- **Không so sánh trực tiếp số chuyến giữa các cảng vụ**: Kiên Giang phần lớn là tàu khách/phà, Bình Thuận nhiều tàu dịch vụ ngoài khơi. Lọc theo DWT hoặc loại tàu trước khi so.
- Hải Phòng, TP.HCM, Nha Trang, Cần Thơ, Quảng Ninh kht1 ghép chuyến theo **tên tàu**; các cảng vụ public-kh ghép theo **mã chuyến**.
- Cảng đi/đến: HP, Nha Trang có sẵn (tên chữ); public-kh phải tra chi tiết từng chuyến (mã UN/LOCODE), phủ dần mỗi ngày; TP.HCM không có.
- Bến của các cảng vụ public-kh lấy nguyên tên ("BẾN CẢNG TIÊN SA"), `kind` suy bằng từ khoá, chưa gán chủ bến / mã CK.
- Miền Trung còn thiếu Nghệ An, Quảng Trị, Huế, Quy Nhơn, Quảng Ngãi (Dung Quất).
