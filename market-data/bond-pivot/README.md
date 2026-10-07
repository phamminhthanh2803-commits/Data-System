# Bond Pivot — CSDL trái phiếu doanh nghiệp VN (scrape HNX CBIS → pivot)

**Mục tiêu:** scrape dữ liệu trái phiếu doanh nghiệp riêng lẻ từ HNX CBIS, dựng
fact table để **pivot/trình bày dữ liệu PHÁT HÀNH và ĐANG LƯU HÀNH** theo các
chiều: doanh nghiệp phát hành, hệ sinh thái (tập đoàn mẹ), CTCK bảo lãnh/thu xếp,
thời gian phát hành & đáo hạn — kèm **mức độ tin cậy** của việc xác định CTCK
bảo lãnh (cao = PDF ghi đích danh / kha = vai trò gián tiếp / proxy = suy từ
lưu ký / khong_xd).

**File chính để dùng:** `data/processed/market_issuance_timeline.csv` — 1 dòng =
1 lô, mở Excel → PivotTable. Phân tích sâu 1 CTCK: `output/<firm>/`.

## Fact table chính: market_issuance_timeline.csv

| Nhóm cột | Cột | Ghi chú |
|---|---|---|
| Doanh nghiệp / hệ sinh thái | `to_chuc_phat_hanh`, `parent_group`, `nganh_nhom`, `mapped` | map qua `data/spv_parent_map.csv` |
| Thời gian | `ngay_phat_hanh` + `nam_ph`/`quy_ph`/`thang_ph`; `ngay_dao_han` + `nam_dh`/`quy_dh` | `quy_*` dạng `2024Q3`, pivot thẳng |
| Giá trị | `gia_tri_ty` (phát hành), `gia_tri_luu_hanh_ty` (đang lưu hành), `tinh_trang` | tỷ VND, mệnh giá × KL |
| Mua lại trước hạn | `gt_mua_lai_luy_ke_ty`, `so_dot_mua_lai`, `ngay_mua_lai_gan_nhat` | từ bảng mua lại HNX (6.2k đợt, chi tiết: `mua_lai.csv`) |
| Sự kiện tín dụng | `su_kien_tin_dung` (theo mã), `issuer_su_kien_tin_dung` (theo DN) | chậm thanh toán / gia hạn kỳ hạn / vi phạm / hội nghị trái chủ — từ tiêu đề CBTT (chi tiết: `credit_events.csv`) |
| Chi tiết bond | `dam_bao`, `hinh_thuc_dam_bao`, `ma_isin`, `trang_thai_dkgd`, `ngay_gd_dau_tien` | enrich từng bond (`bond_detail.csv`) |
| CTCK bảo lãnh | `ctck_bao_lanh`, `nguon_bao_lanh`, **`do_tin_cay`** | cao = PDF bảo lãnh/tư vấn; kha = PDF vai trò khác hoặc `bao_chi` (press_arranger.csv); proxy = suy từ lưu ký; **thap** = không tìm được → gán chính tổ chức phát hành (`tu_phat_hanh(lý_do)` — chủ yếu bond ngân hàng tự bán) |
| Audit | `pdf_bao_lanh/tu_van/dai_ly_phat_hanh/dai_dien_nshtp`, `to_chuc_luu_ky`, `lai_suat`, `ky_han` | đối chiếu nguồn |

`do_tin_cay` cao/kha dày lên mỗi đêm khi backfill OCR chạy (hiện ~95 lô, backlog ~2.5k doc).

## Kiến trúc

```
run_daily.ps1 / run_backfill.ps1   # 2 entry point cho Task Scheduler ("Bond Pivot Weekly" thu Hai 10:30, "Bond Pivot Backfill (dem)" 23:00)
config/firms.json                  # khai báo CTCK: regex, canonical, nhóm nội bộ
data/spv_parent_map.csv            # DÙNG CHUNG: map SPV → tập đoàn
data/press_arranger.csv            # bảng tay: CTCK thu xếp theo báo chí (hỗ trợ prefix "VJCH21*")
data/processed/                    # DỮ LIỆU CHUNG (mọi công ty)
  bond_master.csv                  #   6.7k+ bond, cột to_chuc_luu_ky = proxy chính
  feed.csv / ttph.csv              #   tin CBTT + registry đợt phát hành
  arranger_evidence.csv            #   bảng arranger toàn thị trường từ PDF
  market_issuance_timeline.csv     #   fact table cấp lô (pivot theo quý)
  market_issuance_by_group.csv     #   tổng hợp theo nhóm
  mua_lai.csv                      #   6.2k đợt mua lại trước hạn (bảng 1 registry)
  credit_events.csv                #   tin chậm trả/gia hạn/vi phạm từ feed
  bond_detail.csv                  #   ISIN, đảm bảo, ĐKGD, đại diện NSHTP/bond
data/raw/                          # ca_bundle.pem + cache pdfs/ + pdf_text/
output/<firm>/                     # KẾT QUẢ RIÊNG: bonds_raw, issuer_frequency
                                   #   (+_raw), feed_hits, report.md, history/
scripts/                           # 6 file:
  hnx_common.py                    #   session HNX + ghi file an toàn + firm config
  pull_hnx.py                      #   master | update | feed-full | ttph-full
  analyze_firm.py <key>            #   flag → evidence check → SPV map → report
  extract_arrangers.py [--limit]   #   OCR PDF → bảng arranger + canonicalize
  enrich_bond_detail.py [--limit]  #   chi tiết từng bond (resume, ~0.8s/bond)
  build_timeline.py                #   fact table timeline + credit events
  run_pipeline.py                  #   orchestrator
```

## Thêm công ty mới (2 bước)

1. Thêm entry vào `config/firms.json`: key, `name`, `patterns` (regex nhận diện
   tên trong text — nhớ cả tên pháp lý lẫn viết tắt), `internal_groups` (parent
   group cần tách khỏi danh sách "khách hàng", thường là ngân hàng mẹ),
   `enabled: true` nếu muốn chạy hằng tuần.
2. Chạy thử ngay (không cần enable): `python scripts/analyze_firm.py <key>`
   → có ngay `output/<key>/`. (Level 2: `python scripts/level2_update.py <key>`.)

## Cập nhật tự động hằng tuần

- **Task Scheduler**: `Bond Pivot Weekly` — **thứ Hai 10:30** → `run_daily.ps1`
  → `scripts/run_pipeline.py`. Chạy tay: double-click `run_daily.bat`.
- Mỗi lần chạy: re-pull bond master (68 trang, vì trường lưu ký/tình trạng mutate)
  → incremental feed + registry (dừng khi hết tin mới) → với từng firm enabled:
  analyze + level2 (cap 50 PDF OCR/lần, backlog tự cạn) → snapshot + summary.
- File output bị khoá (đang mở Excel) → tự retry rồi giữ bản cũ, ghi warning,
  không crash. Log: `logs/pipeline_YYYY-MM-DD.log`; tổng hợp: `logs/summary.csv`
  (`date, firm, bonds_flagged_ext, value_ty_ext, failed_steps`).
- **Khi có issuer lạ trong top**: tra nhóm mẹ, thêm keyword (thường, không dấu)
  vào `data/spv_parent_map.csv` — dùng chung cho mọi công ty, lần chạy sau tự gộp.

## Kỹ thuật cào cbonds.hnx.vn (khám phá 07/2026)

Site jQuery trả **HTML fragment**. Mọi POST cần header `CP-TOKEN` = meta
`__RequestVerificationToken` cùng session. TLS: server thiếu intermediate cert
GlobalSign → dùng `data/raw/ca_bundle.pem` (certifi + cert tải từ AIA URL chính
thức), KHÔNG tắt verify.

| Endpoint | Payload | Trả về |
|---|---|---|
| POST `/to-chuc-phat-hanh/danh-sach-trai-phieu` | JSON `{SearchKeys:[8x""], CurrentPage, NumberRecordOnPage}` | bond master 23 cột |
| POST `/to-chuc-phat-hanh/tin-cong-bo-x` | form `keysSearch[]×7, currentPages[]×4, numberRecord[]×4` | feed 4 tab |
| POST `/to-chuc-phat-hanh/thong-tin-phat-hanh/tim-kiem` | form `searchKeys[]×4, arrCurrentPage[]×12, arrNumberRecord[]×12` | 12 bảng; bảng 0 = đợt PH trong nước |
| GET `/view-file?refId=&tableType=` | — | popup chứa link PDF `owa.hnx.vn/ftp/...` |
| GET `/thong-tin-chi-tiet-trai-phieu?bond_code=` | — | chi tiết 1 bond |

OCR: tesseract + `tessdata/vie.traineddata` (script tự set TESSDATA_PREFIX).

## Xác định tổ chức bảo lãnh/tư vấn — thang tin cậy

1. **`arranger_evidence.csv`** (mạnh nhất): bóc trực tiếp từ PDF kết quả chào bán —
   ghi đích danh *"Tổ chức bảo lãnh phát hành: ..."* per lô. Backfill chạy đêm
   (task `Bond Pivot Backfill (dem)` 23:00, 400 doc/đêm, hết backlog tự no-op;
   log `logs/backfill.log`). Chỉ mẫu 2021–2023 có bảng này; mẫu 2024+ đã bỏ.
2. Cột `evidence_check` trong `bonds_raw.csv`: `confirmed` (PDF xác nhận) /
   `other_firm:X` (PDF chỉ ra công ty khác → loại khỏi đếm origination) /
   `doc_no_table` / `no_doc` (chỉ còn proxy lưu ký).
3. Proxy lưu ký (Signal A) — dùng khi không có evidence; đã biết có ngoại lệ.

Lưu ý: kể cả PDF ghi "bảo lãnh phát hành" cũng không phân biệt firm-commitment
vs best-effort, và **không bao giờ** cho biết ai đang "ôm" bond (trái chủ không
công bố; chỉ suy được cơ cấu NĐT sơ cấp nếu doc có mục đó).

## Caveat phương pháp (áp dụng mọi công ty)

1. **Lưu ký ≠ thu xếp**: Signal A là đại lý đăng ký lưu ký — đa số trùng bên thu
   xếp nhưng có ngoại lệ (vd bond VTP do TVSI tư vấn nhưng TCBS lưu ký). Đối
   chiếu `vai_tro` + `level2_evidence.csv`.
2. **Under-count**: bond chuyển đăng ký về VSDC (sàn TPDN riêng lẻ 2023+) mất dấu
   CTCK lưu ký gốc.
3. Mapping SPV theo báo chí, có cột confidence — không phải quan hệ sở hữu pháp lý.
4. CBIS dày dữ liệu từ 2023, đầy đủ từ 2025 (TT 76/2024/TT-BTC).
5. Mẫu CBTT kết quả chào bán 2024+ không còn bảng tổ chức liên quan → Level 2 chỉ
   hiệu quả với doc 2021–2023.


## Cập nhật 14/09/2026 — gộp vào hub
Task cũ `Bond Pivot Weekly` (T2 10:30, `run_daily.ps1`) → nay là bước `bonds` (thứ Hai) trong **Market Data AM** (`D:\market-data\Run-Market.ps1`). `run_backfill.ps1` giữ nguyên cho task `Bond Pivot Backfill (dem)` (đang tắt).

## Phân ngành tổ chức phát hành (16/09/2026)

**Vấn đề cũ:** cột `nganh_nhom` chỉ lấy từ `data/spv_parent_map.csv` (62 SPV khai tay) → chỉ
14,8% số lô / 22,6% giá trị có ngành; **toàn bộ ngân hàng bỏ trống** (52% giá trị phần trống).

**Mới:** `scripts/classify_issuers.py` (được `build_timeline.py` gọi tự động) gán ngành cho
mọi tổ chức → thêm 4 cột vào `market_issuance_timeline.csv` (cột cũ giữ nguyên, kể cả
`nganh_nhom`) và ghi `data/processed/issuer_industry.csv` (1 dòng/tổ chức, để soát):

| Cột | Ý nghĩa |
|---|---|
| `nganh` | 9 nhóm như VBMA: Ngân hàng, Bất động sản, Xây dựng, Tài chính, Chứng khoán, Tiêu dùng, Công nghiệp, Năng lượng, Lĩnh vực khác — hoặc `Chưa phân loại` |
| `ma_ck` | mã CK nếu khớp được công ty niêm yết |
| `nganh_chi_tiet` | ICB cấp 2/4, hoặc hệ sinh thái + ghi chú |
| `nguon_nganh` | cách gán — để biết dòng nào chắc, dòng nào cần soát |

Thứ tự gán (dừng ở bước đầu tiên khớp):
1. `override` — `config/nganh_overrides.csv` (từ khoá, ngành, mã CK, ghi chú). **Sửa sai / bổ sung ở đây.**
2. `dac_biet` — CTCK, công ty tài chính, AMC, bảo hiểm (tên có chữ "Ngân hàng" nhưng không phải ngân hàng: FE Credit, CK Vietinbank…)
3. `niem_yet` — khớp tên chuẩn hoá với 1.526 công ty niêm yết (`D:ctcs-extractor
ganh_cache.csv`, ICB VietcapIQ). Tên ngân hàng **chỉ** được khớp với ngân hàng niêm yết.
4. `ngan_hang` — ngân hàng chưa niêm yết (Agribank, Shinhan, HSBC, BaoViet Bank…)
5. `he_sinh_thai` — SPV trong `spv_parent_map.csv`
6. `tu_khoa` — luật từ khoá, **khớp trọn từ** (``)
7. `Chưa phân loại`

Kết quả: **88,1% số lô / 90,3% giá trị** có ngành; 1.983/1.983 lô tên ngân hàng → Ngân hàng.
Đối chiếu VBMA riêng lẻ 2024: ngân hàng 64,4% (VBMA 64,4%), BĐS 20,5% + chưa phân loại 4,0%
(VBMA BĐS 21,9% — phần chưa phân loại chủ yếu là SPV BĐS chưa rõ chủ).

Lỗi đã bắt khi soát: "Ngân hàng TMCP Bảo Việt" khớp nhầm Tập đoàn Bảo Việt (BVH, bảo hiểm);
"Công ty Cổ phần Bông Sen" rơi vào Công nghiệp vì chuỗi "co **phan bon**g sen" chứa "phan bon";
"Tiếp vận và BĐS Tân Liên Phát Tân Cảng" → Công nghiệp vì chữ "cảng"; VinFast → BĐS theo hệ sinh
thái Vingroup; BCG Land → Xây dựng theo ICB.

## Giá giao dịch & đường cong lợi suất theo ngành (07/10/2026)

**Nguồn giá:** sàn TPDN riêng lẻ HNX (mở 19/07/2023), endpoint
`POST /thong-ke-thi-truong/danh-sach` bảng "Thống kê giao dịch theo mã trái phiếu":
mỗi ngày trả **toàn bộ ~2.300 mã đăng ký giao dịch** (KL, GT, giá cuối ngày); chỉ
~120–160 mã/ngày có khớp → chỉ lưu dòng KL > 0. Giao diện web chặn 15 ngày nhưng
**server không chặn** → backfill được toàn bộ lịch sử (đã backfill 07/2023 → nay).
Giá là **giá thanh toán = giá gộp (dirty, gồm lãi dồn tích)**, đồng/trái phiếu
(hướng dẫn CTCK: "Giá đặt: Giá thanh toán"; bond trả lãi 1 lần khi đáo hạn giao
dịch 150–175% mệnh giá xác nhận điều này). `gia_bq = GT/KL` (VWAP ngày) dùng làm
giá chính, ổn định hơn giá cuối.

**Benchmark TPCP:** `www.hnx.vn/ModuleReportBonds/Bond_YieldCurve/SearchAndNextPageYieldCurveData`
(form `pDate`) → spot rate 11 kỳ hạn 3T–20N theo ngày, có lịch sử. TLS hnx.vn
thiếu intermediate GlobalSign → script tự ghép `data/raw/ca_bundle_hnx.pem` từ AIA.

| Script | Lệnh | Output |
|---|---|---|
| `pull_prices.py` | `update` (20 ngày) / `backfill --from 2023-07-19` | `bond_prices.csv`: ngay, ma_gd, kl, gt, gia_cuoi, gia_bq |
| `pull_tpcp_curve.py` | `update` (30 ngày) / `backfill` | `tpcp_curve.csv`: ngay, ky_han, ky_han_nam, spot_lien_tuc, par_yield, spot_nam |
| `bond_yields.py` | — | `bond_yields.csv`: 1 dòng = 1 mã × 1 ngày có GD: YTM, spread vs TPCP, ngành, độ tin cậy |
| `yield_curve.py` | `[--as-of D] [--window 30] [--tin-cay cao\|kha\|thap] [--min-bond 3]` | `yield_curve.csv` (long), `yield_curve_wide.csv` (ngành × bucket, cột 0M/1M/3M/6M/12M + thay đổi bps), `yield_curve_fit.csv` (nội suy tại 0.5/1/2/3/5/7/10N), `output/yield_curves/<as_of>_*.png` |

**Nối mã:** `ma_gd` (mã giao dịch, vd VHM12503) → `ma_tp` qua `bond_detail.csv`
(`ma_tp_giao_dich`), fallback mã trùng; bond mới chưa enrich → `nganh = "Chưa nối mã"`
(tự hết khi `enrich_bond_detail` chạy tuần).

**Mô hình YTM** (lãi suất hiệu dụng năm, ACT/365, giải bisection trên giá gộp):
- Trả lãi định kỳ: coupon = mệnh giá × lãi suất × kỳ/12 tại các mốc lùi từ đáo hạn → `mo_hinh_cf = dinh_ky_<k>m`.
- Trả lãi 1 lần khi đáo hạn (hoặc kỳ trả lãi ≥ kỳ hạn): 1 dòng tiền = mệnh giá × (1 + lãi × số năm từ phát hành), lãi đơn → `lai_don_den_han`.
- Lãi suất 0 → `zero_coupon`.
- **`do_tin_cay_ytm`**: `cao` = lãi cố định + trả định kỳ; `kha` = thả nổi/kết hợp (HNX chỉ công bố **lãi suất phát hành**, không có lãi kỳ hiện tại → coupon proxy, ghi chú `coupon_proxy_ky_dau`) hoặc trả đầu kỳ/"Khác"; `thap` = trả 1 lần khi đáo hạn (không rõ lãi đơn/kép, nhiều mã đã trả lãi một phần → YTM sai lệch mạnh ở kỳ hạn ngắn).
- Outlier (YTM < 0 hoặc > 40%, giá < 50% hoặc > 250%) giữ dòng, `ghi_chu = outlier`, không dùng dựng đường cong.

**Đường cong:** mỗi mốc (as-of, −1M, −3M, −6M, −12M theo lịch) lấy giao dịch trong
`window` ngày trước mốc, mỗi bond giữ giao dịch gần nhất, gom theo bucket kỳ hạn còn
lại (0.1–0.5 / 0.5–1 / 1–2 / 2–3 / 3–5 / 5–7 / 7–10 / >10 năm) × ngành (9 nhóm VBMA
+ "Toàn thị trường" + "Toàn TT trừ Ngân hàng"); mỗi bucket ≥ `min-bond` bond.
Số chính **`ytm` = bình quân gia quyền theo GIÁ TRỊ LÔ đang lưu hành** (fallback giá
trị phát hành, rồi GTGD), tính **sau khi cắt điểm phân tán** ngoài [Q1−1,5·IQR,
Q3+1,5·IQR] trong bucket (chỉ khi ≥ 5 bond; `n_bond` vs `n_bond_truoc_cat` cho biết
đã cắt bao nhiêu). Cột tham chiếu: `ytm_wavg_raw` (chưa cắt), `ytm_wavg_gtgd` (trọng
số GTGD), `ytm_median`, `ytm_min/max`; `spread_bps` gia quyền cùng trọng số,
`tpcp_spot` nội suy tại kỳ hạn bình quân gia quyền. Mặc định dùng `cao + kha`;
`--tin-cay cao` để chỉ lấy bond lãi cố định (sạch hơn nhưng thưa).

**Caveat:** (1) thanh khoản mỏng, giá thỏa thuận → nhiễu lớn, bucket ít bond đổi
median mạnh; đọc kèm `n_bond`. (2) Bond thả nổi dùng lãi phát hành → YTM lệch khi
lãi tham chiếu đã đổi (chủ yếu ngân hàng/BĐS lớn). (3) Nhiều mã ngân hàng kỳ hạn
5–10N là bond vốn cấp 2 có quyền mua lại → YTM-to-maturity cao hơn yield-to-call.
(4) Ngành theo `classify_issuers.py`, "Chưa phân loại" là SPV chưa rõ chủ.
