# -*- coding: utf-8 -*-
"""Ban do series_id -> (ten nguon, duong dan kiem chung).

Dung chung cho dashboard HTML (link tren tung o) va Excel (cot HYPERLINK).
Chi mot noi khai bao de khong lech nhau.
"""

SBV_RATES = "https://sbv.gov.vn/l%C3%A3i-su%E1%BA%A5t1"
SBV_FX = "https://sbv.gov.vn/t%E1%BB%B7-gi%C3%A1"
SBV_OMO = "https://sbv.gov.vn/vi/nghi%E1%BB%87p-v%E1%BB%A5-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng-m%E1%BB%9F"
SBV_STAT = "https://sbv.gov.vn/vi/thong-ke-mot-so-chi-tieu-co-ban"
VCB_FX = "https://www.vietcombank.com.vn/vi-VN/KHCN/Cong-cu-Tien-ich/Ty-gia"
NQS = "https://dulieu.nguoiquansat.vn/lai-suat"
DLKT = "https://dulieukinhte.com/du-lieu/"
IMF = "https://data.imf.org/"
VND_FOREIGN = ("https://api-finfo.vndirect.com.vn/v4/foreigns"
               "?q=code:VNINDEX~tradingDate:gte:2026-01-01&size=20&sort=tradingDate")
FSX = "https://fs.vietcap.com.vn/"          # nguon goc cua D:/bctc/fs-extractor
# van ban goc cua hai tran quy dinh - xem lo trinh day du trong src_caps.py
TT22 = "https://congbao.chinhphu.vn/van-ban/thong-tu-so-22-2019-tt-nhnn-30003.htm"
TT25 = "https://vanban.chinhphu.vn/?docid=218533&pageid=27160"

# FRED: moi chuoi mot trang rieng
FRED = {
    "us_sofr": "SOFR", "us_effr": "EFFR", "us_fed_target_upper": "DFEDTARU",
    "us_tbill_4w": "DTB4WK", "us_tbill_3m": "DTB3", "us_ust_2y": "DGS2",
    "us_ust_10y": "DGS10", "us_dxy_broad": "DTWEXBGS",
}

# dulieukinhte: moi bang mot slug
DLKT_SLUG = {
    "omo_outstanding": "sbv-bomhut-tien-334", "bill_outstanding": "sbv-bomhut-tien-334",
    "omo_maturity_total": "sbv-bomhut-tien-334", "omo_net_daily": "sbv-bomhut-tien-334",
    "m2": "cung-tien-m2-huy-dong-385", "cash_ratio_m2": "cung-tien-m2-huy-dong-385",
    "deposits_household": "cung-tien-m2-huy-dong-385",
    "deposits_corporate": "cung-tien-m2-huy-dong-385",
    "lending_rate_avg": "lai-suat-cho-vay-binh-quan-ngan-hang-700",
    "lending_deposit_spread": "lai-suat-cho-vay-binh-quan-ngan-hang-700",
    "lending_spread_net_vcb": "lai-suat-cho-vay-binh-quan-ngan-hang-700",
    "credit_growth_ytd": "tang-truong-tin-dung-toc-do-353",
    "fdi_registered": "von-fdi-dang-ky-cap-moi-405",
    **{k: "can-can-thanh-toan-361" for k in "current_account_bop fdi_inflow_bop fdi_net_bop fii_net_bop other_inv_net_bop financial_account_bop bop_errors bop_overall".split()},
    "fdi_realized_vnd": "von-dau-tu-phat-trien-xa-hoi-275",
    "public_inv_month": "von-dau-tu-tu-nsnn-317",
    "fx_free_buy": "ty-gia-cho-den-719", "fx_free_sell": "ty-gia-cho-den-719",
    "fx_free_vs_vcb": "ty-gia-cho-den-719",
}

# con lai: khai bao thang
DIRECT = {
    # NHNN - trang lai suat
    "policy_refinance": ("NHNN · Lãi suất", SBV_RATES),
    "policy_rediscount": ("NHNN · Lãi suất", SBV_RATES),
    **{k: ("NHNN · Lãi suất", SBV_RATES) for k in
       ("ib_on ib_1w ib_2w ib_1m ib_3m ib_6m ib_9m "
        "ib_vol_on ib_vol_1w ib_vol_2w ib_vol_1m ib_vol_3m ib_vol_6m ib_vol_9m").split()},
    # NHNN - trang ty gia
    "fx_central": ("NHNN · Tỷ giá", SBV_FX),
    "fx_sbv_sell_ref": ("NHNN · Tỷ giá", SBV_FX),
    "fx_sbv_buy_ref": ("NHNN · Tỷ giá", SBV_FX),
    # NHNN - nghiep vu thi truong mo
    **{k: ("NHNN · Thị trường mở", SBV_OMO) for k in
       ("omo_win_total omo_win_7d_vol omo_win_7d_rate omo_win_14d_vol omo_win_14d_rate "
        "omo_win_91d_vol bill_issue_vol").split()},
    # NHNN - thong ke he thong TCTD
    **{k: ("NHNN · Thống kê TCTD", SBV_STAT) for k in
       ("ldr_system ldr_soe ldr_jsc sfl_system sfl_soe sfl_jsc car_tt41 car_tt41_soe "
        "car_tt41_jsc own_capital_tt41 bank_total_assets bank_charter_capital").split()},
    # Vietcombank
    **{k: ("Vietcombank", VCB_FX) for k in
       "fx_vcb_sell fx_vcb_transfer fx_vcb_buy_cash".split()},
    # Nguoiquansat
    **{k: ("Người Quan Sát", NQS) for k in
       ("deposit_1m_big4 deposit_1m_avg deposit_1m_max deposit_6m_big4 deposit_6m_avg "
        "deposit_6m_max deposit_12m_big4 deposit_12m_avg deposit_12m_max").split()},
    # IMF qua macro-fetcher
    **{k: ("IMF · macro-fetcher", IMF) for k in
       "trade_balance exports imports fx_reserves fx_imf_eop".split()},
    # VNDirect
    "fii_net_val": ("VNDirect finfo", VND_FOREIGN),
    # BCTC qua FS Extractor (file local, link toi nguon goc VCI)
    **{k: ("BCTC · FS Extractor", FSX) for k in
       ("bank_loans bank_deposits ldr_tt22_listed loan_deposit_listed casa_ratio "
        "mlt_loan_share mlt_loans").split()},
    # tran quy dinh - link toi van ban dang co hieu luc cho tung chi tieu
    # lai suat cho vay binh quan tung ngan hang cong bo (src_lending.py)
    **{k: ("BIDV · công bố lãi suất", "https://bidv.com.vn/bidv/tin-tuc/congbothongtinlaisuat_vi/congbolaisuatchovay_vi") for k in "lend_avg_bid lend_spread_bid".split()},
    **{k: ("Eximbank · lãi suất bình quân", "https://eximbank.com.vn/tin-tuc/lai-suat-binh-quan-thang-trong-nam-2026") for k in "lend_avg_eib lend_avg_eib_khcn lend_avg_eib_khdn lend_spread_eib".split()},
    **{k: ("Agribank · lãi suất cho vay", "https://www.agribank.com.vn/vn/lai-suat-cho-vay-agribank") for k in "lend_avg_agr lend_spread_agr".split()},
    **{k: ("VIB · lãi suất vay bình quân", "https://www.vib.com.vn/vn/lai-suat-vay-binh-quan/") for k in "lend_avg_vib lend_avg_vib_khcn lend_avg_vib_khdn lend_spread_vib".split()},
    "ldr_cap": ("Thông tư 22/2019/TT-NHNN", TT22),
    "sfl_cap": ("Thông tư 25/2026/TT-NHNN", TT25),
}

# chi tieu tinh ra - ghi cong thuc thay vi link
DERIVED_FORMULA = {
    "fx_band_ceiling": "fx_central × 1,05",
    "fx_band_floor": "fx_central × 0,95",
    "fx_vcb_sell_vs_ceiling": "fx_vcb_sell ÷ trần − 1",
    "swap_on": "ib_on − us_sofr",
    "swap_1m": "ib_1m − us_tbill_4w",
    "swap_3m": "ib_3m − us_tbill_3m",
    "ib_curve_1m_on": "ib_1m − ib_on",
    "ib_spread_policy": "ib_on − policy_refinance",
    "ib_vol_total": "tổng doanh số các kỳ hạn",
    "omo_net": "omo_win_total − bill_issue_vol",
    "omo_net_outstanding": "omo_outstanding + bill_outstanding",
    "deposits_total": "tiền gửi dân cư + TCKT",
    "deposit_growth_ytd": "deposits_total so với tháng 12 năm trước",
    "m2_growth": "m2 so với tháng 12 năm trước",
    "credit_deposit_gap": "credit_growth_ytd − deposit_growth_ytd",
    "fx_import_cover": "fx_reserves ÷ imports",
    "car_banks_median": "median CAR hợp nhất từ CBTT TT41 của từng ngân hàng (cbtt_urls.csv)",
    "car_banks_min": "min CAR hợp nhất từ CBTT TT41 của từng ngân hàng",
    "car_banks_n": "số ngân hàng có CBTT CAR trong kỳ",
    "public_inv_ytd": "cộng dồn public_inv_month trong năm",
    "deposit_rate_avg_vcb": "lending_rate_avg − lending_deposit_spread (VCB chỉ công bố cho vay BQ và chênh lệch)",
    "lending_rate_big4": "trung bình đơn giản lend_avg VCB, BID, AGR theo tháng (≥2 ngân hàng)",
    "lending_rate_jsc": "trung bình đơn giản lend_avg các NH cổ phần có số trong tháng (≥2 ngân hàng)",
}


# chi tieu chua tu dong: ghi ro cho lay chu khong co trang de mo
MANUAL_NOTE = {
    "fdi_disbursed": "Cục Thống kê (thông cáo tháng)",
    "remittance": "NHNN chi nhánh TP.HCM",
    "kbnn_deposit": "Thuyết minh BCTC ngân hàng",
    "credit_outstanding": "FiinProX (chuỗi dừng 07/2025)",
    "ib_1y": "FiinProX (nguồn ngừng 2012)",
}


def source_of(series_id, source_col=""):
    """-> (ten nguon, url, cong thuc). url rong nghia la khong co trang de mo."""
    if series_id in FRED:
        return "FRED", "https://fred.stlouisfed.org/series/" + FRED[series_id], ""
    if series_id in DLKT_SLUG:
        return "dulieukinhte", DLKT + DLKT_SLUG[series_id], ""
    if series_id in DIRECT:
        n, u = DIRECT[series_id]
        return n, u, ""
    if series_id in DERIVED_FORMULA:
        return "Tính ra", "", DERIVED_FORMULA[series_id]
    if series_id in MANUAL_NOTE:
        return MANUAL_NOTE[series_id], "", ""
    return (source_col or "—"), "", ""


def table():
    """Bang phang cho Excel: series_id, nguon, url, cong thuc."""
    ids = set(FRED) | set(DLKT_SLUG) | set(DIRECT) | set(DERIVED_FORMULA) | set(MANUAL_NOTE)
    out = []
    for sid in sorted(ids):
        n, u, f = source_of(sid)
        out.append(dict(series_id=sid, nguon=n, url=u, cong_thuc=f))
    return out
