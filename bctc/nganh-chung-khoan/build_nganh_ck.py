# -*- coding: utf-8 -*-
r"""build_nganh_ck.py — FOLDER NGÀNH CHỨNG KHOÁN: chỉ tiêu chuẩn + tỷ lệ tính sẵn, xếp theo metadata cho SQL / PivotTable.

Đầu vào : D:\bctc\fiinprox-unpivot\output\fiinprox_facts_all.csv (long, Tỷ VND; ngành "Dịch vụ tài chính" = CTCK)
Ánh xạ  : metric_map.csv (key ↔ statement_code + row_order; tạo mẫu lần đầu, sửa được) — NOTE có nhãn lặp nên khoá là row_order.
Đầu ra  (cùng thư mục):
  dim_company.csv      ticker, tên, ngành ICB, nhóm quy mô (theo VCSH kỳ gần nhất: Lớn/Vừa/Nhỏ), kỳ đầu/cuối
  dim_period.csv       period, freq, year, quarter, ngày cuối kỳ
  dim_metric.csv       metric, tên Việt, nhóm, đơn vị, công thức
  fact_items.csv       long: ticker | freq | period | metric(key gốc) | value (Tỷ VND) — chỉ tiêu đã ánh xạ
  fact_ratios.csv      long: ticker | freq | period | year | quarter | metric | value — items + dẫn xuất + TTM + tỷ lệ + tăng trưởng
  ratios_wide_Q.csv / ratios_wide_Y.csv   1 dòng = ticker×kỳ, cột = metric (xem nhanh)
  industry_summary.csv theo kỳ: tổng quy mô ngành + trung vị tỷ lệ + số công ty
  nganh_chung_khoan.sqlite  bảng dim_*, fact_items, fact_ratios, fact_fs (toàn bộ facts ngành, có index) + view v_ratios
  nganh_chung_khoan_pivot.xlsx  sheet fact_ratios (long, cho PivotTable) + dim_company + dim_metric
Chạy: python build_nganh_ck.py   (run_pipeline.py của fiinprox-unpivot gọi tự động ở cuối)
"""
import os, sqlite3, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "fiinprox-unpivot", "output", "fiinprox_facts_all.csv")
NGANH = "Dịch vụ tài chính"
MAP_CSV = os.path.join(HERE, "metric_map.csv")

# key, statement, row_order, nhãn kiểm tra (một phần), tên Việt, nhóm
MAP = [
    ("cash", "BS", 3, "Tiền và tương đương tiền", "Tiền và tương đương tiền", "Quy mô"),
    ("fvtpl", "BS", 6, "FVTPL", "Tài sản tài chính FVTPL", "Quy mô"),
    ("htm_st", "BS", 7, "HTM", "Đầu tư nắm giữ đến đáo hạn (ngắn hạn)", "Quy mô"),
    ("loans", "BS", 8, "Các khoản cho vay", "Các khoản cho vay (margin + ứng trước)", "Quy mô"),
    ("afs_st", "BS", 9, "AFS", "Tài sản tài chính AFS (ngắn hạn)", "Quy mô"),
    ("fa_provision", "BS", 10, "Dự phòng suy giảm", "Dự phòng suy giảm tài sản tài chính", "Quy mô"),
    ("receivables", "BS", 11, "Tổng các khoản phải thu", "Tổng các khoản phải thu", "Quy mô"),
    ("lt_invest", "BS", 54, "Đầu tư dài hạn", "Đầu tư dài hạn", "Quy mô"),
    ("total_assets", "BS", 92, "TỔNG CỘNG TÀI SẢN", "Tổng tài sản", "Quy mô"),
    ("liabilities", "BS", 93, "NỢ PHẢI TRẢ", "Nợ phải trả", "Quy mô"),
    ("st_borrow", "BS", 95, "Vay và nợ thuê", "Vay và nợ thuê tài chính ngắn hạn", "Quy mô"),
    ("st_bonds", "BS", 100, "Trái phiếu phát hành ngắn hạn", "Trái phiếu phát hành ngắn hạn", "Quy mô"),
    ("lt_borrow", "BS", 122, "Vay và nợ thuê", "Vay và nợ thuê tài chính dài hạn", "Quy mô"),
    ("lt_bonds", "BS", 127, "Trái phiếu phát hành dài hạn", "Trái phiếu phát hành dài hạn", "Quy mô"),
    ("equity", "BS", 142, "VỐN CHỦ SỞ HỮU", "Vốn chủ sở hữu (gồm CĐ thiểu số)", "Quy mô"),
    ("equity_parent", "BS", 143, "Vốn chủ sở hữu", "Vốn chủ sở hữu công ty mẹ", "Quy mô"),
    ("charter_capital", "BS", 145, "Vốn góp", "Vốn góp của chủ sở hữu", "Quy mô"),
    ("retained", "BS", 158, "Lợi nhuận chưa phân phối", "Lợi nhuận chưa phân phối", "Quy mô"),
    ("afs_reval_reserve", "BS", 152, "đánh giá lại tài sản", "Chênh lệch đánh giá lại TS theo giá trị hợp lý (VCSH) = lãi/lỗ AFS chưa thực hiện luỹ kế", "Quy mô"),
    ("investor_deposits", "BS", 202, "Tiền gửi của khách hàng", "Tiền gửi của khách hàng (ngoài bảng)", "Quy mô"),
    ("op_revenue", "IS", 1, "DOANH THU HOẠT ĐỘNG", "Doanh thu hoạt động", "Kết quả"),
    ("fvtpl_gain", "IS", 2, "FVTPL", "Lãi từ tài sản FVTPL", "Kết quả"),
    ("htm_income", "IS", 6, "đáo hạn", "Lãi từ HTM", "Kết quả"),
    ("loan_income", "IS", 7, "cho vay và phải thu", "Lãi từ cho vay và phải thu (margin)", "Kết quả"),
    ("afs_income", "IS", 8, "sẵn sàng để bán", "Lãi từ AFS", "Kết quả"),
    ("brokerage_rev", "IS", 10, "môi giới", "Doanh thu môi giới", "Kết quả"),
    ("underwriting_rev", "IS", 11, "bảo lãnh", "Doanh thu bảo lãnh phát hành", "Kết quả"),
    ("advisory_rev", "IS", 13, "tư vấn đầu tư", "Doanh thu tư vấn đầu tư", "Kết quả"),
    ("custody_rev", "IS", 15, "lưu ký", "Doanh thu lưu ký", "Kết quả"),
    ("fin_advisory_rev", "IS", 18, "tư vấn tài chính", "Doanh thu tư vấn tài chính", "Kết quả"),
    ("other_rev", "IS", 19, "Doanh thu khác", "Doanh thu khác", "Kết quả"),
    ("fvtpl_loss", "IS", 23, "FVTPL", "Lỗ từ tài sản FVTPL", "Kết quả"),
    ("provision_borrow_cost", "IS", 30, "CP đi vay", "CP dự phòng TSTC + chi phí đi vay (một số CTCK ghi lãi vay ở đây)", "Kết quả"),
    ("prop_cost", "IS", 32, "tự doanh", "Chi phí hoạt động tự doanh", "Kết quả"),
    ("brokerage_cost", "IS", 33, "môi giới", "Chi phí môi giới", "Kết quả"),
    ("op_cost", "IS", 41, "Chi phí hoạt động kinh doanh", "Chi phí hoạt động kinh doanh", "Kết quả"),
    ("gross_profit", "IS", 42, "LỢI NHUẬN GỘP", "Lợi nhuận gộp", "Kết quả"),
    ("fin_income", "IS", 48, "doanh thu hoạt động tài chính", "Doanh thu hoạt động tài chính", "Kết quả"),
    ("interest_expense", "IS", 51, "Chi phí lãi vay", "Chi phí lãi vay", "Kết quả"),
    ("fin_cost", "IS", 56, "chi phí tài chính", "Chi phí tài chính", "Kết quả"),
    ("selling_exp", "IS", 57, "CHI PHÍ BÁN HÀNG", "Chi phí bán hàng", "Kết quả"),
    ("ga_exp", "IS", 58, "QUẢN LÝ", "Chi phí quản lý", "Kết quả"),
    ("op_result", "IS", 59, "KẾT QUẢ HOẠT ĐỘNG", "Kết quả hoạt động", "Kết quả"),
    ("pbt", "IS", 65, "TRƯỚC THUẾ", "Lợi nhuận trước thuế", "Kết quả"),
    ("tax", "IS", 68, "THUẾ", "Chi phí thuế TNDN", "Kết quả"),
    ("npat", "IS", 71, "SAU THUẾ", "Lợi nhuận sau thuế", "Kết quả"),
    ("npat_parent", "IS", 72, "chủ sở hữu", "LNST cổ đông công ty mẹ", "Kết quả"),
    ("oci", "IS", 75, "TOÀN DIỆN KHÁC", "Thu nhập (lỗ) toàn diện khác sau thuế (OCI)", "Kết quả"),
    ("oci_afs", "IS", 77, "sẵn sàng để bán", "OCI: lãi/(lỗ) đánh giá lại AFS trong kỳ", "Kết quả"),
    ("total_comprehensive", "IS", 84, "Tổng thu nhập toàn diện", "Tổng thu nhập toàn diện (LNST + OCI)", "Kết quả"),
    ("eps_reported", "IS", 88, "Lãi cơ bản", "EPS cơ bản báo cáo (VND)", "Kết quả"),
    ("margin_loans", "NOTE", 159, "ký quỹ", "Cho vay ký quỹ (margin) — thuyết minh", "Quy mô"),
    ("advance_loans", "NOTE", 160, "ứng trước", "Cho vay ứng trước tiền bán", "Quy mô"),
    ("trading_value_investors", "NOTE", 109, "Giá trị Cổ phiếu", "GTGD cổ phiếu của NĐT thực hiện qua CTCK trong kỳ", "Hoạt động"),
    ("trading_value_prop", "NOTE", 101, "Giá trị Cổ phiếu", "GTGD cổ phiếu tự doanh trong kỳ", "Hoạt động"),
    ("fvtpl_fv", "NOTE", 185, "FVTPL", "Giá trị hợp lý FVTPL — thuyết minh", "Quy mô"),
    ("fvtpl_fv_listed", "NOTE", 187, "Cổ phiếu niêm yết", "FVTPL: cổ phiếu niêm yết (giá hợp lý)", "Quy mô"),
    ("fvtpl_fv_bonds", "NOTE", 190, "Trái phiếu", "FVTPL: trái phiếu (giá hợp lý)", "Quy mô"),
    ("staff_cost_ga", "NOTE", 575, "nhân viên", "Chi phí nhân viên (trong chi phí quản lý)", "Kết quả"),
]
FLOW_KEYS = {k for k, sc, *_ in MAP if sc == "IS"} | {"trading_value_investors", "trading_value_prop", "staff_cost_ga"}
FLOW_KEYS -= {"eps_reported"}

DERIVED = [   # (metric, tên Việt, nhóm, đơn vị, công thức)
    ("net_fvtpl", "Lãi ròng FVTPL", "Kết quả", "Tỷ VND", "fvtpl_gain - fvtpl_loss"),
    ("interest_cost", "Chi phí lãi vay (IS 51, thiếu thì IS 30)", "Kết quả", "Tỷ VND", "interest_expense if > 0 else provision_borrow_cost"),
    ("borrowings", "Tổng vay + trái phiếu", "Quy mô", "Tỷ VND", "st_borrow + st_bonds + lt_borrow + lt_bonds"),
    ("margin_book", "Dư nợ margin (thuyết minh, thiếu thì lấy BS cho vay)", "Quy mô", "Tỷ VND", "margin_loans else loans"),
    ("invest_book", "Danh mục đầu tư (FVTPL+AFS+HTM ngắn hạn)", "Quy mô", "Tỷ VND", "fvtpl + afs_st + htm_st"),
    ("shares_mn", "Số cổ phiếu (triệu, = vốn góp / 10.000đ)", "Quy mô", "triệu CP", "charter_capital*1e9/1e4/1e6"),
    ("bvps", "Giá trị sổ sách / CP", "Định giá", "VND", "equity_parent / shares"),
    ("opex", "Chi phí vận hành (bán hàng + quản lý)", "Kết quả", "Tỷ VND", "selling_exp + ga_exp"),
    ("net_brokerage", "Môi giới ròng (DT − CP môi giới)", "Kết quả", "Tỷ VND", "brokerage_rev - brokerage_cost"),
    ("total_income", "Tổng thu nhập (DT hoạt động + DT tài chính)", "Kết quả", "Tỷ VND", "op_revenue + fin_income"),
    ("npat_incl_oci", "LNST + OCI AFS (lợi nhuận kinh tế gồm lãi/lỗ AFS chưa thực hiện)", "Kết quả", "Tỷ VND", "npat + oci_afs"),
]
RATIOS = [   # tỷ lệ theo kỳ (Q dùng TTM cho dòng chảy; Y dùng số năm)
    ("roe", "ROE (TTM / VCSH bình quân)", "Sinh lời", "%", "npat_ttm / avg(equity_t, equity_t-4)"),
    ("roa", "ROA (TTM / TTS bình quân)", "Sinh lời", "%", "npat_ttm / avg(total_assets)"),
    ("net_margin", "Biên LNST / DT hoạt động (TTM)", "Sinh lời", "%", "npat_ttm / op_revenue_ttm"),
    ("pbt_margin", "Biên LNTT / DT hoạt động (TTM)", "Sinh lời", "%", "pbt_ttm / op_revenue_ttm"),
    ("eps_ttm", "EPS TTM (VND)", "Định giá", "VND", "npat_parent_ttm*1e9 / shares"),
    ("leverage", "Đòn bẩy TTS / VCSH", "Đòn bẩy", "x", "total_assets / equity"),
    ("debt_to_equity", "Vay + TP / VCSH", "Đòn bẩy", "x", "borrowings / equity"),
    ("margin_to_equity", "Dư nợ margin / VCSH (trần 2x)", "Đòn bẩy", "%", "margin_book / equity"),
    ("margin_to_assets", "Dư nợ margin / TTS", "Cơ cấu tài sản", "%", "margin_book / total_assets"),
    ("invest_to_assets", "Danh mục đầu tư / TTS", "Cơ cấu tài sản", "%", "invest_book / total_assets"),
    ("cash_to_assets", "Tiền / TTS", "Cơ cấu tài sản", "%", "cash / total_assets"),
    ("loan_yield", "Lợi suất cho vay (TTM / dư nợ BQ)", "Hiệu quả", "%", "loan_income_ttm / avg(loans)"),
    ("cost_of_funds", "Chi phí vốn vay (lãi vay TTM / vay BQ)", "Hiệu quả", "%", "interest_cost_ttm / avg(borrowings)"),
    ("lending_spread", "Chênh lệch lợi suất cho vay − chi phí vốn", "Hiệu quả", "đ%", "loan_yield - cost_of_funds"),
    ("brokerage_margin", "Biên môi giới (DT − CP) / DT môi giới (TTM)", "Hiệu quả", "%", "net_brokerage_ttm / brokerage_rev_ttm"),
    ("cir", "CIR: (CP hoạt động + CP vận hành) / tổng thu nhập (TTM)", "Hiệu quả", "%", "(op_cost_ttm + opex_ttm) / total_income_ttm"),
    ("opex_to_income", "CP vận hành / tổng thu nhập (TTM)", "Hiệu quả", "%", "opex_ttm / total_income_ttm"),
    ("brokerage_fee_rate", "Phí môi giới hiệu dụng (DT môi giới / GTGD NĐT)", "Hiệu quả", "%", "brokerage_rev / trading_value_investors (cùng kỳ)"),
    ("mix_brokerage", "Tỷ trọng DT môi giới / DT hoạt động (TTM)", "Cơ cấu doanh thu", "%", "brokerage_rev_ttm / op_revenue_ttm"),
    ("mix_lending", "Tỷ trọng lãi cho vay / DT hoạt động (TTM)", "Cơ cấu doanh thu", "%", "loan_income_ttm / op_revenue_ttm"),
    ("mix_fvtpl", "Tỷ trọng lãi FVTPL (gộp) / DT hoạt động (TTM)", "Cơ cấu doanh thu", "%", "fvtpl_gain_ttm / op_revenue_ttm"),
    ("mix_ib", "Tỷ trọng bảo lãnh + tư vấn / DT hoạt động (TTM)", "Cơ cấu doanh thu", "%", "(underwriting_rev+advisory_rev+fin_advisory_rev)_ttm / op_revenue_ttm"),
    ("g_npat_yoy", "Tăng trưởng LNST YoY (kỳ)", "Tăng trưởng", "%", "npat / npat_t-4 - 1"),
    ("g_revenue_yoy", "Tăng trưởng DT hoạt động YoY (kỳ)", "Tăng trưởng", "%", "op_revenue / op_revenue_t-4 - 1"),
    ("g_margin_yoy", "Tăng trưởng dư nợ margin YoY", "Tăng trưởng", "%", "margin_book / margin_book_t-4 - 1"),
    ("g_margin_qoq", "Tăng trưởng dư nợ margin QoQ", "Tăng trưởng", "%", "margin_book / margin_book_t-1 - 1"),
    ("g_equity_yoy", "Tăng trưởng VCSH YoY", "Tăng trưởng", "%", "equity / equity_t-4 - 1"),
]


def log(m):
    print(m, flush=True)


def ensure_map():
    cols = ["metric", "statement_code", "row_order", "label_check", "ten_viet", "nhom"]
    base = pd.DataFrame(MAP, columns=cols)
    if not os.path.exists(MAP_CSV):
        base.to_csv(MAP_CSV, index=False, encoding="utf-8-sig")
        log(f"  tạo mẫu {os.path.basename(MAP_CSV)}")
    mp = pd.read_csv(MAP_CSV, encoding="utf-8-sig")
    new = base[~base.metric.isin(mp.metric)]                      # metric moi them vao MAP trong code -> tu bo sung vao CSV (giu sua tay cua user)
    if len(new):
        mp = pd.concat([mp, new], ignore_index=True); mp.to_csv(MAP_CSV, index=False, encoding="utf-8-sig")
        log(f"  + metric_map.csv: thêm {len(new)} metric mới: {', '.join(new.metric)}")
    return mp


def pkey(freq, year, q):
    return f"Q{int(q)}/{int(year)}" if freq == "Q" else f"{int(year)}"


def main():
    mp = ensure_map()
    log(f"Đọc {SRC} ...")
    use = ["ticker", "ten_cong_ty", "nganh_L1", "nganh_L2", "nganh_L3", "nganh_L4", "freq", "statement_code", "row_order",
           "metric", "period", "year", "quarter", "value", "unit"]
    df = pd.read_csv(SRC, usecols=use, encoding="utf-8-sig", dtype={"period": str})
    df = df[df.nganh_L2 == NGANH]
    df["row_order"] = pd.to_numeric(df.row_order, errors="coerce").astype("Int64")
    df["value"] = pd.to_numeric(df.value, errors="coerce")
    log(f"  {len(df):,} facts, {df.ticker.nunique()} công ty")

    # ---- dim_company: nhóm quy mô theo VCSH kỳ Q gần nhất
    eq = df[(df.statement_code == "BS") & (df.row_order == 142) & (df.freq == "Q")].dropna(subset=["value"])
    eq = eq.sort_values(["ticker", "year", "quarter"]).groupby("ticker").tail(1).set_index("ticker")
    q_eq = eq.value.quantile([0.33, 0.66])
    comp = df.groupby("ticker").agg(ten_cong_ty=("ten_cong_ty", "first"), nganh_L1=("nganh_L1", "first"), nganh_L2=("nganh_L2", "first"),
                                    nganh_L3=("nganh_L3", "first"), nganh_L4=("nganh_L4", "first"), year_min=("year", "min"), year_max=("year", "max"))
    comp["vcsh_ky_gan_nhat_ty"] = eq.value.round(1)
    comp["ky_gan_nhat"] = eq.period
    comp["nhom_quy_mo"] = pd.cut(comp.vcsh_ky_gan_nhat_ty, [-np.inf, q_eq.iloc[0], q_eq.iloc[1], np.inf], labels=["Nhỏ", "Vừa", "Lớn"]).astype(str)
    comp = comp.reset_index()

    # ---- fact_items: ánh xạ (statement, row_order) -> key, kiểm tra nhãn
    key = {(r.statement_code, int(r.row_order)): r.metric for r in mp.itertuples()}
    df["key"] = [key.get((s, int(r))) if pd.notna(r) else None for s, r in zip(df.statement_code, df.row_order)]
    items = df.dropna(subset=["key"]).copy()
    chk = items.groupby("key").metric.agg(lambda s: s.value_counts().index[0])
    for r in mp.itertuples():
        lab = chk.get(r.metric, "")
        if str(r.label_check).lower() not in str(lab).lower():
            log(f"  ! nhãn khác kỳ vọng: {r.metric} -> '{lab}' (mong '{r.label_check}')")
    items = items.dropna(subset=["value"])
    items["quarter"] = pd.to_numeric(items.quarter, errors="coerce").fillna(0).astype(int)   # ky nam: quarter NaN -> 0 (pivot_table bo NaN trong index -> mat het freq Y)
    items = items.groupby(["ticker", "freq", "period", "year", "quarter", "key"], dropna=False).value.sum(min_count=1).reset_index()
    wide = items.pivot_table(index=["ticker", "freq", "period", "year", "quarter"], columns="key", values="value", aggfunc="first")
    for k, *_ in MAP:
        if k not in wide.columns:
            wide[k] = np.nan
    wide = wide.reset_index()
    wide["quarter"] = pd.to_numeric(wide.quarter, errors="coerce").fillna(0).astype(int)
    wide["year"] = pd.to_numeric(wide.year, errors="coerce").astype(int)
    wide["t"] = np.where(wide.freq == "Q", wide.year * 4 + wide.quarter - 1, wide.year)   # chỉ số thời gian liên tục
    wide = wide.sort_values(["ticker", "freq", "t"]).reset_index(drop=True)

    # ---- dẫn xuất (FiinProX ghi CHI PHÍ/THUẾ bằng số ÂM -> đổi về dương để tính tỷ lệ)
    w = wide
    COST_KEYS = ["fvtpl_loss", "provision_borrow_cost", "prop_cost", "brokerage_cost", "op_cost", "interest_expense", "fin_cost", "selling_exp", "ga_exp", "tax", "staff_cost_ga"]
    for c in COST_KEYS:
        w[c] = w[c].abs()
    w["interest_cost"] = w.interest_expense.where(w.interest_expense > 0, w.provision_borrow_cost)   # HCM: lãi vay nằm ở IS dòng 30
    w["net_fvtpl"] = w.fvtpl_gain.fillna(0) - w.fvtpl_loss.fillna(0)
    w["borrowings"] = w[["st_borrow", "st_bonds", "lt_borrow", "lt_bonds"]].sum(axis=1, min_count=1)
    w["margin_book"] = w.margin_loans.where(w.margin_loans.notna() & (w.margin_loans > 0), w.loans)
    w["invest_book"] = w[["fvtpl", "afs_st", "htm_st"]].sum(axis=1, min_count=1)
    w["shares_mn"] = w.charter_capital * 1e9 / 1e4 / 1e6
    w["bvps"] = w.equity_parent * 1e9 / (w.shares_mn * 1e6)
    w["opex"] = w[["selling_exp", "ga_exp"]].sum(axis=1, min_count=1)
    w["net_brokerage"] = w.brokerage_rev.fillna(0) - w.brokerage_cost.fillna(0)
    w["total_income"] = w[["op_revenue", "fin_income"]].sum(axis=1, min_count=1)
    w["ib_rev"] = w[["underwriting_rev", "advisory_rev", "fin_advisory_rev"]].sum(axis=1, min_count=1)
    w["npat_incl_oci"] = w.npat + w.oci_afs.fillna(0)        # LNST + lai/lo AFS chua thuc hien trong ky (OCI) - quan trong voi CTCK giu AFS lon (TCX, VCI, SHS)

    # ---- TTM (Q: tổng 4 quý liên tiếp; Y: chính nó) và giá trị 4 kỳ trước / 1 kỳ trước
    flows = sorted(FLOW_KEYS | {"net_fvtpl", "opex", "net_brokerage", "total_income", "ib_rev", "interest_cost", "npat_incl_oci"})
    g = w.groupby(["ticker", "freq"], sort=False)
    consec4 = (g.t.shift(3) == w.t - 3)          # 4 kỳ liên tiếp không thiếu
    for k in flows:
        ttm = g[k].transform(lambda s: s.rolling(4, min_periods=4).sum())
        w[k + "_ttm"] = np.where(w.freq == "Q", np.where(consec4, ttm, np.nan), w[k])
    def lag(col, n):
        prev = g[col].shift(n); ok = g.t.shift(n) == w.t - n
        return prev.where(ok)
    def avg(col):   # bình quân đầu-cuối kỳ TTM (Q: t và t-4; Y: t và t-1)
        n = np.where(w.freq == "Q", 4, 1)
        prev = pd.Series([lag(col, 4)[i] if w.freq[i] == "Q" else lag(col, 1)[i] for i in range(len(w))], index=w.index)
        return w[col].where(prev.isna(), (w[col] + prev) / 2)
    # tối ưu: tính lag 4 và lag 1 một lần
    lag4 = {c: lag(c, 4) for c in ["equity", "total_assets", "loans", "borrowings", "npat", "op_revenue", "margin_book"]}
    lag1 = {c: lag(c, 1) for c in ["equity", "total_assets", "loans", "borrowings", "margin_book"]}
    def avg2(col):
        prev = np.where(w.freq == "Q", lag4[col], lag1[col])
        prev = pd.Series(prev, index=w.index)
        return (w[col] + prev.fillna(w[col])) / 2
    pct = lambda a, b: np.where((b.abs() > 0), a / b * 100, np.nan)
    w["roe"] = pct(w.npat_ttm, avg2("equity"))
    w["roa"] = pct(w.npat_ttm, avg2("total_assets"))
    w["net_margin"] = pct(w.npat_ttm, w.op_revenue_ttm)
    w["pbt_margin"] = pct(w.pbt_ttm, w.op_revenue_ttm)
    w["eps_ttm"] = w.npat_parent_ttm * 1e9 / (w.shares_mn * 1e6)
    w["leverage"] = w.total_assets / w.equity
    w["debt_to_equity"] = w.borrowings / w.equity
    w["margin_to_equity"] = pct(w.margin_book, w.equity)
    w["margin_to_assets"] = pct(w.margin_book, w.total_assets)
    w["invest_to_assets"] = pct(w.invest_book, w.total_assets)
    w["cash_to_assets"] = pct(w.cash, w.total_assets)
    w["loan_yield"] = pct(w.loan_income_ttm, avg2("loans"))
    w["cost_of_funds"] = pct(w.interest_cost_ttm, avg2("borrowings"))
    w["lending_spread"] = w.loan_yield - w.cost_of_funds
    w["brokerage_margin"] = pct(w.net_brokerage_ttm, w.brokerage_rev_ttm)
    w["cir"] = pct(w.op_cost_ttm.fillna(0) + w.opex_ttm.fillna(0), w.total_income_ttm)
    w["opex_to_income"] = pct(w.opex_ttm, w.total_income_ttm)
    w["brokerage_fee_rate"] = pct(w.brokerage_rev, w.trading_value_investors)
    w["mix_brokerage"] = pct(w.brokerage_rev_ttm, w.op_revenue_ttm)
    w["mix_lending"] = pct(w.loan_income_ttm, w.op_revenue_ttm)
    w["mix_fvtpl"] = pct(w.fvtpl_gain_ttm, w.op_revenue_ttm)
    w["mix_ib"] = pct(w.ib_rev_ttm, w.op_revenue_ttm)
    lagY = {c: pd.Series(np.where(w.freq == "Q", lag4[c], lag(c, 1)), index=w.index) for c in ["npat", "op_revenue", "margin_book", "equity"]}   # YoY: Q lui 4 ky, NAM lui 1 ky (truoc 16/09/2026 nam lui 4 nam - sai)
    w["g_npat_yoy"] = pct(w.npat - lagY["npat"], lagY["npat"].abs())
    w["g_revenue_yoy"] = pct(w.op_revenue - lagY["op_revenue"], lagY["op_revenue"].abs())
    w["g_margin_yoy"] = pct(w.margin_book - lagY["margin_book"], lagY["margin_book"])
    w["g_margin_qoq"] = pct(w.margin_book - lag1["margin_book"], lag1["margin_book"])
    w["g_equity_yoy"] = pct(w.equity - lagY["equity"], lagY["equity"])
    for c in ["leverage", "debt_to_equity"]:
        w.loc[(w.equity <= 0), c] = np.nan
    w = w.drop(columns=["t"])

    # ---- dim_metric
    dm = [(r.metric, r.ten_viet, r.nhom, "VND" if r.metric == "eps_reported" else "Tỷ VND", f"{r.statement_code} dòng {r.row_order}") for r in mp.itertuples()]
    dm += [(k, v, g_, u, f) for k, v, g_, u, f in DERIVED]
    dm += [(k + "_ttm", f"{dict((m[0], m[4]) for m in MAP).get(k, k)} — TTM 4 quý (năm: bằng số năm)", "TTM", "Tỷ VND", f"tổng 4 quý liên tiếp của {k}") for k in flows]
    dm += [(k, v, g_, u, f) for k, v, g_, u, f in RATIOS]
    dim_metric = pd.DataFrame(dm, columns=["metric", "ten_viet", "nhom", "don_vi", "cong_thuc"]).drop_duplicates("metric")
    order = list(dim_metric.metric)

    # ---- xuất
    dims = ["ticker", "freq", "period", "year", "quarter"]
    long = w.melt(id_vars=dims, value_vars=[c for c in order if c in w.columns], var_name="metric", value_name="value").dropna(subset=["value"])
    long = long.merge(dim_metric[["metric", "nhom", "don_vi"]], on="metric", how="left")
    long["value"] = long.value.astype(float).round(4)
    dim_period = w[dims].drop_duplicates().copy()
    dim_period["ngay_cuoi_ky"] = [pd.Timestamp(int(y), 12, 31) if f == "Y" else (pd.Timestamp(int(y), int(q) * 3, 1) + pd.offsets.MonthEnd(0)) for f, y, q in zip(dim_period.freq, dim_period.year, dim_period.quarter)]
    dim_period = dim_period.drop(columns="ticker").drop_duplicates().sort_values(["freq", "ngay_cuoi_ky"])
    items_out = items.rename(columns={"key": "metric"})

    comp.to_csv(os.path.join(HERE, "dim_company.csv"), index=False, encoding="utf-8-sig")
    dim_period.to_csv(os.path.join(HERE, "dim_period.csv"), index=False, encoding="utf-8-sig")
    dim_metric.to_csv(os.path.join(HERE, "dim_metric.csv"), index=False, encoding="utf-8-sig")
    items_out.to_csv(os.path.join(HERE, "fact_items.csv"), index=False, encoding="utf-8-sig")
    long.to_csv(os.path.join(HERE, "fact_ratios.csv"), index=False, encoding="utf-8-sig")
    for fq in ("Q", "Y"):
        w[w.freq == fq].drop(columns=["freq"]).to_csv(os.path.join(HERE, f"ratios_wide_{fq}.csv"), index=False, encoding="utf-8-sig", float_format="%.4f")

    # ---- industry summary: tổng quy mô + trung vị tỷ lệ
    size_cols = ["total_assets", "equity", "loans", "margin_book", "fvtpl", "borrowings", "op_revenue", "npat", "npat_ttm", "op_revenue_ttm", "brokerage_rev", "loan_income"]
    ratio_cols = [r[0] for r in RATIOS]
    agg = w.groupby(["freq", "period", "year", "quarter"]).agg(**{f"sum_{c}": (c, "sum") for c in size_cols}, **{f"med_{c}": (c, "median") for c in ratio_cols}, n_cong_ty=("ticker", "nunique")).reset_index()
    agg["ind_roe_ttm"] = pct(agg.sum_npat_ttm, agg.sum_equity)
    agg["ind_margin_to_equity"] = pct(agg.sum_margin_book, agg.sum_equity)
    agg["ind_net_margin_ttm"] = pct(agg.sum_npat_ttm, agg.sum_op_revenue_ttm)
    agg = agg.merge(dim_period, on=["freq", "period", "year", "quarter"], how="left").sort_values(["freq", "ngay_cuoi_ky"])
    agg.to_csv(os.path.join(HERE, "industry_summary.csv"), index=False, encoding="utf-8-sig", float_format="%.4f")

    # ---- SQLite
    dbp = os.path.join(HERE, "nganh_chung_khoan.sqlite")
    if os.path.exists(dbp):
        os.remove(dbp)
    con = sqlite3.connect(dbp)
    comp.to_sql("dim_company", con, index=False); dim_period.assign(ngay_cuoi_ky=dim_period.ngay_cuoi_ky.dt.strftime("%Y-%m-%d")).to_sql("dim_period", con, index=False)
    dim_metric.to_sql("dim_metric", con, index=False); items_out.to_sql("fact_items", con, index=False); long.to_sql("fact_ratios", con, index=False)
    fs = df[["ticker", "freq", "statement_code", "row_order", "metric", "period", "year", "quarter", "value"]].dropna(subset=["value"])
    fs.to_sql("fact_fs", con, index=False, chunksize=200000)
    agg.assign(ngay_cuoi_ky=agg.ngay_cuoi_ky.dt.strftime("%Y-%m-%d")).to_sql("industry_summary", con, index=False)
    cur = con.cursor()
    cur.executescript("""
        CREATE INDEX ix_fs ON fact_fs(ticker, freq, statement_code, row_order, period);
        CREATE INDEX ix_fs_metric ON fact_fs(statement_code, row_order, period);
        CREATE INDEX ix_items ON fact_items(ticker, freq, metric, period);
        CREATE INDEX ix_ratios ON fact_ratios(metric, freq, period);
        CREATE INDEX ix_ratios_t ON fact_ratios(ticker, freq, period);
        CREATE VIEW v_ratios AS
          SELECT r.ticker, c.ten_cong_ty, c.nhom_quy_mo, r.freq, r.period, r.year, r.quarter, r.metric, m.ten_viet, m.nhom, m.don_vi, r.value
          FROM fact_ratios r JOIN dim_company c ON c.ticker = r.ticker JOIN dim_metric m ON m.metric = r.metric;
        CREATE VIEW v_latest_q AS
          SELECT * FROM v_ratios WHERE freq = 'Q' AND (year*4+quarter) = (
            SELECT MAX(year*4+quarter) FROM (
              SELECT year, quarter, COUNT(*) n FROM fact_ratios WHERE freq='Q' AND metric='total_assets' GROUP BY year, quarter
            ) WHERE n >= 0.7 * (SELECT MAX(n) FROM (SELECT COUNT(*) n FROM fact_ratios WHERE freq='Q' AND metric='total_assets' GROUP BY year, quarter)));
    """)
    con.commit(); con.close()

    # ---- Excel cho PivotTable (long + dims)
    xp = os.path.join(HERE, "nganh_chung_khoan_pivot.xlsx")
    piv = long.merge(comp[["ticker", "ten_cong_ty", "nhom_quy_mo"]], on="ticker", how="left").merge(dim_metric[["metric", "ten_viet"]], on="metric", how="left")
    piv = piv[["ticker", "ten_cong_ty", "nhom_quy_mo", "freq", "period", "year", "quarter", "nhom", "metric", "ten_viet", "don_vi", "value"]]
    if len(piv) > 1_040_000:
        piv = piv[piv.year >= 2015]
    with pd.ExcelWriter(xp, engine="openpyxl") as xw:
        piv.to_excel(xw, sheet_name="fact_ratios", index=False)
        comp.to_excel(xw, sheet_name="dim_company", index=False)
        dim_metric.to_excel(xw, sheet_name="dim_metric", index=False)
        agg.to_excel(xw, sheet_name="industry_summary", index=False)
    log(f"-> {len(comp)} công ty | fact_items {len(items_out):,} | fact_ratios {len(long):,} | fact_fs {len(fs):,} | pivot xlsx {len(piv):,} dòng")
    latest = w[w.freq == "Q"].sort_values(["year", "quarter"]).groupby("ticker").tail(1)
    show = latest[latest.ticker.isin(["SSI", "VND", "HCM", "VCI", "VCBS", "MBS", "TCBS", "VIX", "SHS"])][["ticker", "period", "total_assets", "equity", "margin_book", "roe", "leverage", "margin_to_equity", "net_margin", "loan_yield", "cost_of_funds", "mix_lending", "g_npat_yoy"]]
    pd.set_option("display.width", 220); log(show.round(1).to_string(index=False))


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
