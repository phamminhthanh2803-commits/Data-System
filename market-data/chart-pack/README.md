# chart-pack — bộ data 12 tháng để vẽ chart TTCK

Gom sẵn dữ liệu từ các pipeline đã có trong `D:\market-data` thành **1 file Excel**
(`Chart_Pack_TTCK.xlsx`), mỗi sheet là một bảng wide (cột đầu = ngày/tháng, các cột sau =
từng series) — chọn vùng rồi Insert > Chart là ra luôn, không phải xử lý gì thêm.

## Chạy

> ⚠️ **File đang có 31 biểu đồ tự vẽ (16/09/2026).** `build_chart_pack.py` **ghi đè**
> toàn bộ file → sẽ mất chart. Muốn thêm/cập nhật dữ liệu vào file đang dùng thì chạy
> `add_sheet.py`: dùng Excel COM, chỉ đụng sheet dữ liệu, tự backup `_backup.xlsx`.

```
python D:\market-data\chart-pack\add_sheet.py           # cập nhật 06_GTGD_* vào file hiện tại
python D:\market-data\chart-pack\build_chart_pack.py    # DỰNG LẠI TỪ ĐẦU (mất chart đã vẽ)
python D:\market-data\chart-pack\build_chart_pack.py --months 24
```

Chạy lại sau khi task **Market Data PM 18:30** xong (bước `flows`, `tvhistory`) để có
phiên mới nhất. Xem nhanh + xuất Excel linh hoạt hơn: app `D:\market-data\app\`.

## Sheet

| Sheet | Nội dung | Đơn vị |
|---|---|---|
| `00_Huong_dan` | mục lục, đơn vị, nguồn, kỳ dữ liệu | |
| `01_KhoiNgoai_ChauA` | khối ngoại mua/bán ròng theo tháng: VN, KOSPI, KOSDAQ, Đài Loan, Indonesia, Thái Lan, Malaysia + tổng EM châu Á + luỹ kế | triệu USD |
| `01b_KhoiNgoai_VN_Ngay` | khối ngoại + tự doanh VN theo ngày, 3 sàn, luỹ kế, kèm VN-Index | tỷ VND |
| `02_VonHoa_Nhom` | VN-Index / VN30 / VNMidcap / VNSmallcap: chỉ số, rebase 100, vốn hoá nhóm quy mô | điểm · nghìn tỷ |
| `03_DoRong_TT` | độ rộng: tăng/giảm/đứng giá, % mã tăng, A/D line, % mã trên MA20/50/100/200, đỉnh–đáy 52 tuần | số mã · % |
| `04_Sector_12M` | chỉ số ngành gia quyền vốn hoá, rebase 100 | rebase 100 |
| `04b_Sector_TongKet` | hiệu suất 1T/3T/6T/12T/YTD, % mã tăng, vốn hoá, đóng góp | % · nghìn tỷ |
| `05_Duoi_MA` | số cổ phiếu **nằm dưới** MA50 / MA200 / MA300 theo ngày, tách HOSE/HNX/UPCoM + toàn TT | số mã · % |
| `06_GTGD_ThiTruong` | giá trị + khối lượng giao dịch 3 sàn theo ngày, MA20/MA50, kèm VN-Index | tỷ VND · triệu CP |
| `06b_GTGD_KhuVuc` | GTGD bình quân phiên theo tháng, 10 thị trường châu Á | triệu USD |

## Nguồn (không kéo mạng, chỉ đọc file đã có)

- `index-fetcher\tv-history.csv` — giá daily TradingView, 1.233 mã VN + chỉ số HOSE
- `index-fetcher\flows-master.csv` — khối ngoại/tự doanh VN (VNDirect) + khu vực
  (Naver/KRX, TWSE, IDX, SET, Bursa)
- `index-fetcher\fx-master.csv` — tỷ giá để quy USD (bình quân tháng)
- `index-fetcher\raw\vn_screener_meta.csv` — số CP lưu hành + ngành (screener TradingView)

## Lưu ý khi đọc số

- **Vốn hoá nhóm quy mô** trong `02` là **ước tính** = số CP lưu hành hiện tại × giá điều chỉnh,
  nhóm chia theo thứ hạng vốn hoá HOSE cuối kỳ (top 30 / 31–100 / còn lại) chứ không phải rổ
  chính thức của HOSE. Muốn đúng rổ thì dùng 4 cột chỉ số VN30 / VNMidcap / VNSmallcap ở cùng sheet.
- **Thái Lan, Malaysia** chỉ công bố khối ngoại theo **tháng**; tháng nào chưa có bản tháng thì
  script cộng dồn các ngày đã bồi (không đếm hai lần).
- **Chỉ số ngành** dùng rổ cố định (mã có giá cả đầu kỳ lẫn cuối kỳ) để không nhảy bậc khi có mã
  mới lên sàn / huỷ niêm yết. Phân nhóm ngành giống `index-fetcher\reports\three_month.py`.
- Giá là **giá điều chỉnh**, nên MA và hiệu suất không bị gãy vì chia tách/cổ tức; đổi lại mức
  vốn hoá của quá khứ là vốn hoá theo giá điều chỉnh, không phải vốn hoá danh nghĩa ngày đó.
