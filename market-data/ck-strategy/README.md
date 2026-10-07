# D:\market-data\ck-strategy — CHIẾN LƯỢC NGÀNH CHỨNG KHOÁN (chốt 23/09/2026, đổi luật bán 28/09/2026)

Mua cả rổ CTCK vốn hoá lớn ở đáy chu kỳ, bán khi lợi nhuận ngành bắt đầu chững lại. Một file duy nhất: `ck_strategy.py`.

```bash
python ck_strategy.py              # trạng thái hôm nay + ck_signals.csv
python ck_strategy.py --backtest   # thêm nhật ký lệnh + biểu đồ PNG
python ck_strategy.py --top 3      # đổi số mã (mặc định 5)
python ck_strategy.py --fixed SSI,VND,HCM,VCI,MBS   # rổ cố định
python ck_strategy.py --ban dinhgia                 # luật bán cũ (P/B ngành +2,5σ) để so sánh; file ra thêm hậu tố _dinhgia
```

## Quy tắc

**Danh mục:** N mã CTCK vốn hoá lớn nhất tại ngày mua (mặc định 5), bỏ mã niêm yết dưới 1 năm, chia đều tiền. Không đảo mã giữa chừng.

**MUA — cần đủ 3 điều kiện**

| # | Điều kiện | Nguồn |
|---|---|---|
| 1 | z của **P/E VN-Index loại Vin** ≤ −1,7σ → bậc 1 (50% vốn); ≤ −1,9σ → bậc 2 (50% còn lại). z tính theo cửa sổ trượt **3 năm HOẶC 5 năm** (chạm ở cửa sổ nào cũng được) | Vietcap IQ 2009–07/2019 (×hệ số loại Vin) + VNDirect `valuation-adjusted.csv` |
| 2 | **GTGD 3 sàn quý gần nhất giảm** so với quý trước (dòng tiền đã rút) | `indices-master.csv` |
| 3 | **LNST ngành CK tăng**, ưu tiên QoQ: tăng QoQ → mở đủ 2 bậc; chỉ tăng YoY → chỉ mở bậc 1 (mua nốt khi QoQ chuyển tăng); cả hai giảm → đóng | `fact_items.csv` (FiinProX), hiệu lực sau cuối quý + 45 ngày |

**BÁN — chạm bất kỳ điều kiện nào thì bán hết**
- **LNST ngành CK bắt đầu không tăng:** BCTC quý công bố *sau ngày mua* (hiệu lực cuối quý + 45 ngày) cho thấy LNST ngành **giảm QoQ**, với điều kiện trong lệnh **đã có ≥ 3 quý LNST tăng QoQ liên tiếp** (`G_MIN`). Bán ngay ở quý giảm đầu tiên sau khi mua chỉ còn 5,7x; ≥ 2 quý thì bán sớm 11/2017 giữa chu kỳ 2016–18.
- **Chốt chặn:** danh mục **giảm 30%** so với đỉnh của lệnh; **khi đỉnh lãi của lệnh đã ≥ +20% thì siết còn giảm 20%** từ đỉnh (chốt lời) — `LAI_KICH`, `DD_CHAT`.
- Nắm quá 5 năm.

**Vào lại:** sau chốt chặn −30% nghỉ 10 phiên; sau khi bán vì LNST phải chờ BCTC quý kế tiếp; rồi mua lại khi tín hiệu mua bật lại. **Sau chốt lời: mua lại cùng rổ, 100% vốn, khi rổ vượt lại đỉnh cũ của lệnh** (`MUA_LAI`); huỷ chờ nếu LNST ngành chững. Tiền chờ tính lãi 5%/năm. Chốt lời mà không có luật mua lại → 8,5x (bán sớm rồi định giá hết rẻ, không vào lại được).

*Luật bán cũ (đến 28/09/2026):* z của P/B ngành CK (3 năm) vượt +2,5σ rồi cắt xuống. Bán quá sớm trong sóng mạnh: 06/2021 bán ở +341%, rổ còn tăng thêm 96% tới 11/2021.

## Cách chọn tham số: tối ưu cho CHU KỲ BÌNH THƯỜNG

2020–2021 (Covid → bong bóng) và 2022 (vỡ bong bóng) là bất thường — **không dùng để chọn tham số**. Chấm điểm bằng NAV gộp của 2012–19, 2023–24, 2025–nay (dò 290 tổ hợp: luật bán LNST g1/g2/g3 / định giá / không có; chốt chặn −20/25/30%; kích hoạt siết 10–50%; mức siết 7–20%).

- Trong chu kỳ bình thường **luật bán LNST gần như không kích hoạt** — kết quả 2023–24 và 2025 giống hệt nhau giữa bán LNST, bán định giá hay không có luật bán; **chỉ mức chốt lời quyết định**.
- Mức siết **−10% quá chặt** cho chu kỳ 2016–18 (bán 07/2017 ở +50%, rổ còn lên tới 04/2018); −15%/−20% giữ được tới gần đỉnh.
- Vùng ổn định: kích hoạt 20–30%, siết 15–20%, g3 → +19,3–19,4%/năm trong chu kỳ bình thường. Chọn **−20%** vì toàn kỳ tốt hơn (53,7x vs 46,5x) và ít lệnh hơn.
- Không có mức nào tốt nhất ở mọi chu kỳ: 2025 thích −10% (+49%) hơn −20% (+37%); 2016–18 ngược lại (+104% vs +191%). Chỉ có 3 chu kỳ bình thường → vẫn là chọn trên mẫu nhỏ.

| Theo giai đoạn (top 5) | 2012–19 | 2023–24 | 2025–nay | **CAGR chu kỳ bình thường** | 2020–21 (BT) | 2022 (BT) | Toàn kỳ | Sụt toàn kỳ |
|---|---|---|---|---|---|---|---|---|
| **Luật hiện hành** (g3, lãi ≥20% → −20%, mua lại) | **+191%** | **+89%** | +37% | **+19,3%** | +400% | +41% | **53,7x** | −25% |
| Sáng 28/09 (g2, lãi ≥20% → −10%, mua lại) | +104% | +84% | +49% | +16,3% | +343% | +69% | 42,1x | −22% |
| LNST g2 + chỉ −30% | +122% | +67% | +26% | +14,4% | +694% | +13% | 42,3x | −31% |
| Định giá cũ + −30% | +170% | +67% | +26% | +16,4% | +360% | +13% | 29,7x | −31% |
| *Mua-giữ top 5 (cuối kỳ / cao nhất)* | +26% / +187% | +71% / +130% | +12% / +95% | | +417% | −62% | | |

Rổ cố định SSI, VND, HCM, VCI, MBS với luật hiện hành: 50,1x, CAGR +31,2%, sụt −25%.

Nhật ký lệnh (top 5, luật hiện hành): 01/2016 → 04/2018 **+122%** · 03/2020 → 07/2020 +23% → *mua lại* 09/2020 → 01/2021 **+71%** → *mua lại* 04/2021 → 15/11/2021 **+130%** (LNST Q3/2021 giảm sau 3 quý tăng) · 05/2022 → 06/2022 −6% · 06/2022 → 09/2022 +29% · 11/2022 → 10/2023 **+120%** · 04/2025 → 10/2025 **+72%** · đang giữ từ 03/2026.

(Từ 28/09/2026 giá mua dùng giá đóng cửa gần nhất khi một mã không khớp lệnh ngày mua; trước đó mã đó bị loại khỏi bậc mua nên lệnh 2016 bị tính thấp.)

## Dữ liệu vào (đọc trực tiếp, không kéo mạng)
- `D:\market-data\market-valuation\history\vnindex_val_vietcap.csv` — P/E, P/B VN-Index theo ngày từ 04/2009 (Vietcap IQ, endpoint `iq.vietcap.com.vn/.../index-valuation`).
- `D:\market-data\market-valuation\valuation-adjusted.csv` — P/E loại VIC/VHM/VRE/VPL (từ 07/2019).
- `D:\bctc\nganh-chung-khoan\fact_items.csv` — VCSH và LNST quý của 87 CTCK (FiinProX).
- `D:\market-data\index-fetcher\tv-history.csv` + `raw\vn_screener_meta.csv` — giá và số CP.
- `D:\market-data\index-fetcher\indices-master.csv` — VN-Index và GTGD 3 sàn.

## File ra
`ck_signals.csv` (mọi chuỗi tín hiệu theo ngày) · `ck_trades_top{N}.csv` · `ck_nav_top{N}.csv` · `ck_strategy_top{N}.png` (chỉ khi `--backtest`)

**Theo dõi PnL (xuất mỗi lần chạy):** `ck_pnl_top{N}.png` / `ck_pnl_fixed{N}.png` — (1) lệnh đang mở: PnL cả rổ + từng mã (giá vốn bình quân các bậc), đỉnh PnL lệnh, đường chốt chặn −30%; (2) PnL mọi lệnh theo số phiên từ ngày vào; (3) kết quả từng lệnh + đỉnh PnL đạt được; (4) NAV + sụt từ đỉnh. `ck_pnl_lenh_top{N}.png` / `ck_pnl_lenh_fixed{N}.png` — mỗi lệnh 1 ô, thang riêng, vạch chia dày theo độ dài lệnh (lệnh ngắn: nhãn tuần + vạch ngày; lệnh dài: nhãn 2 tháng/quý + vạch tháng; trục % vạch chính ~8 nấc, vạch phụ 1/5), có điểm mua từng bậc, đỉnh PnL, điểm bán, mức chốt chặn và PnL từng mã. PnL lệnh đang mở dừng ở ngày cuối rổ có giá thật (không kéo phẳng ngày thiếu giá). `ck_pnl_*.csv` = PnL theo ngày mọi lệnh + cột `lai_<mã>` và `muc_cat` của lệnh đang mở. Terminal in cảnh báo khi rổ đã giảm ≥ 24% từ đỉnh lệnh (80% ngưỡng chốt chặn).

## Lưu ý khi dùng
- **Chỉ 6 lệnh đã đóng trong 14 năm**, và lệnh 2020–2021 chiếm phần lớn kết quả. Luật bán LNST mới chỉ thực sự kích hoạt 2 lần (11/2017, 11/2021); phần vượt trội so với luật cũ gần như đến từ riêng lần 11/2021. Các tham số (−1,7σ/−1,9σ, ≥ 2 quý tăng, −30%) được chọn sau khi nhìn dữ liệu nên có rủi ro khớp quá khít quá khứ.
- Rổ CTCK lấy từ TradingView nên **thiếu các công ty đã huỷ niêm yết** → kết quả giai đoạn 2012–2015 có thiên lệch sống sót.
- Chưa tính phí giao dịch, thuế, cổ tức.
- Chuỗi P/B ngành CK dựng lại tại chỗ từ 08/2009 (pipeline `build_valuation_ck.py` đang cắt ở 2015 — nên sửa cho đồng bộ).
- Đã thử và LOẠI: chốt lỗ 15–20% (quét sạch sóng, CAGR còn 6–8%), cổng thanh khoản TĂNG (bỏ lỡ 2022/2023/2025), lọc mã theo LNST tăng QoQ (đẩy vào mã nhỏ, CAGR 14,7%), bán khi chạm +2σ trên đường lên (bán sớm ở nhịp rung lắc 01/2021), bán ở quý LNST giảm đầu tiên sau khi mua (5,7x), bán khi LNST giảm YoY / TTM giảm (4,2–4,4x), dùng LNST của chính rổ thay vì ngành (kết quả như nhau).
