# -*- coding: utf-8 -*-
"""Bộ chỉ tiêu của KHỐI (nhóm ngành / công ty) trong file ngành BĐS + bộ dịch sang công thức Excel.

Một khối = danh sách dòng. Dòng 'raw' tra Data_FS theo khoá <tiền tố>|<báo cáo>|<row_order>; dòng 'f' là CÔNG THỨC Excel
viết bằng token tham chiếu dòng khác trong cùng khối:
  {x}        ô dòng x cùng cột
  {x@ttm}    quý: tổng 4 quý (đủ 4 quý mới tính) | năm: chính ô đó
  {x@ttm0}   quý: tổng 4 quý, ô trống coi = 0 (chi phí có thể không phát sinh) | năm: N(ô)
  {x@avg}    quý: bình quân (t, t−4) | năm: bình quân (t, t−1)
  {x@lag}    quý: t−4 (cùng kỳ) | năm: t−1
Token không đủ cột (đầu chuỗi) -> ô để trống. Mọi dòng 'f' bọc IFERROR(...,"").
Định nghĩa thống nhất với file ngành CK: ROE/ROA = TTM / bình quân (t, t−4 quý | t, t−1 năm).
"""
import re

# (key, nhãn, loại, báo cáo, item VCI (key_item trong dim_item) hoặc biểu thức, định dạng)
BLOCK = [
    ("n", "Số công ty có BCTC (chỉ khối nhóm)", "raw", "CNT", "n_cong_ty", "n"),
    ("_h1", "KẾT QUẢ KINH DOANH (tỷ đồng)", "hdr", None, None, None),
    ("rev", "Doanh thu thuần", "raw", "IS", "net_sales", "ty"),
    ("cogs", "Giá vốn hàng bán", "raw", "IS", "cost_of_sales", "ty"),
    ("gp", "Lợi nhuận gộp", "raw", "IS", "gross_profit", "ty"),
    ("fin_inc", "Doanh thu tài chính", "raw", "IS", "financial_income", "ty"),
    ("fin_exp", "Chi phí tài chính", "raw", "IS", "financial_expenses", "ty"),
    ("int_exp", "   trong đó: chi phí lãi vay", "raw", "IS", "interest_expenses", "ty"),
    ("jv", "Lãi/(lỗ) công ty liên doanh, liên kết", "raw", "IS", "gain_loss_from_joint_ventures_from_2015", "ty"),
    ("sell", "Chi phí bán hàng", "raw", "IS", "selling_expenses", "ty"),
    ("ga", "Chi phí quản lý doanh nghiệp", "raw", "IS", "general_and_admin_expenses", "ty"),
    ("other", "Thu nhập khác, ròng", "raw", "IS", "net_other_income_expenses", "ty"),
    ("pbt", "Lợi nhuận trước thuế", "raw", "IS", "net_accounting_profit_loss_before_tax", "ty"),
    ("npat", "Lợi nhuận sau thuế", "raw", "IS", "net_profit_loss_after_tax", "ty"),
    ("npatmi", "LNST của cổ đông công ty mẹ", "raw", "IS", "attributable_to_parent_company", "ty"),
    ("_h2", "BẢNG CÂN ĐỐI (tỷ đồng)", "hdr", None, None, None),
    ("ta", "Tổng tài sản", "raw", "BS", "total_assets", "ty"),
    ("cash", "Tiền và tương đương tiền", "raw", "BS", "cash_and_cash_equivalents", "ty"),
    ("st_inv", "Đầu tư tài chính ngắn hạn", "raw", "BS", "short_term_investments#1", "ty"),
    ("ar", "Phải thu ngắn hạn", "raw", "BS", "accounts_receivable", "ty"),
    ("ar_lt", "Phải thu dài hạn", "raw", "BS", "long_term_trade_receivables", "ty"),
    ("inv", "Hàng tồn kho (giá gốc)", "raw", "BS", "inventories", "ty"),
    ("wip", "   trong đó: chi phí SXKD dở dang (BĐS dở dang)", "raw", "NOTE", "noc19", "ty"),
    ("re_goods", "   trong đó: hàng hoá bất động sản", "raw", "NOTE", "noc24", "ty"),
    ("wip_lt", "Chi phí SXKD dở dang dài hạn", "raw", "BS", "long_term_cost_of_work_in_progress", "ty"),
    ("cip", "Xây dựng cơ bản dở dang", "raw", "BS", "construction_in_progress", "ty"),
    ("ip", "Bất động sản đầu tư (giá trị còn lại)", "raw", "BS", "investment_properties", "ty"),
    ("assoc", "Đầu tư vào công ty liên doanh, liên kết", "raw", "BS", "investments_in_associates", "ty"),
    ("liab", "Nợ phải trả", "raw", "BS", "liabilities", "ty"),
    ("adv", "Người mua trả tiền trước ngắn hạn", "raw", "BS", "advances_from_customers", "ty"),
    ("adv_lt", "Người mua trả tiền trước dài hạn", "raw", "BS", "long_term_advances_from_customers", "ty"),
    ("unrev", "Doanh thu chưa thực hiện ngắn hạn", "raw", "BS", "short_term_unrealized_revenue", "ty"),
    ("unrev_lt", "Doanh thu chưa thực hiện dài hạn", "raw", "BS", "deferred_revenue", "ty"),
    ("st_debt", "Vay và nợ thuê tài chính ngắn hạn", "raw", "BS", "short_term_borrowings", "ty"),
    ("lt_debt", "Vay và nợ thuê tài chính dài hạn", "raw", "BS", "long_term_borrowings", "ty"),
    ("bonds", "   trong đó: trái phiếu phát hành (thuyết minh vay dài hạn)", "raw", "NOTE", "noc96", "ty"),
    ("equity", "Vốn chủ sở hữu", "raw", "BS", "owners_equity", "ty"),
    ("mi", "Lợi ích cổ đông không kiểm soát", "raw", "BS", "minority_interests", "ty"),
    ("debt", "Tổng nợ vay", "f", None, 'IF(AND({st_debt}="",{lt_debt}=""),"",N({st_debt})+N({lt_debt}))', "ty"),
    ("net_debt", "Nợ vay ròng (nợ vay − tiền − ĐTNH)", "f", None, "{debt}-N({cash})-N({st_inv})", "ty"),
    ("eq_me", "VCSH của cổ đông công ty mẹ", "f", None, "{equity}-N({mi})", "ty"),
    ("adv_all", "Người mua trả tiền trước (ngắn + dài hạn)", "f", None,
     'IF(AND({adv}="",{adv_lt}=""),"",N({adv})+N({adv_lt}))', "ty"),
    ("_h3", "LƯU CHUYỂN TIỀN TỆ (tỷ đồng)", "hdr", None, None, None),
    ("cfo", "Lưu chuyển tiền thuần từ HĐKD (CFO)", "raw", "CF", "net_cash_inflows_outflows_from_operating_activities", "ty"),
    ("d_inv", "   (Tăng)/giảm hàng tồn kho", "raw", "CF", "increase_decrease_in_inventories", "ty"),
    ("int_paid", "   Tiền lãi vay đã trả", "raw", "CF", "interest_paid", "ty"),
    ("capex", "Tiền chi mua sắm, xây dựng TSCĐ và TS dài hạn", "raw", "CF", "purchases_of_fixed_assets_and_other_long_term_assets", "ty"),
    ("cfi", "Lưu chuyển tiền thuần từ HĐ đầu tư (CFI)", "raw", "CF", "net_cash_inflows_outflows_from_investing_activities", "ty"),
    ("borrow", "Tiền thu từ đi vay", "raw", "CF", "proceeds_from_loans", "ty"),
    ("repay", "Tiền trả nợ gốc vay", "raw", "CF", "repayment_of_loans", "ty"),
    ("issue", "Tiền thu từ phát hành cổ phiếu", "raw", "CF", "proceeds_from_issue_of_shares", "ty"),
    ("div", "Cổ tức đã trả", "raw", "CF", "dividends_paid", "ty"),
    ("cff", "Lưu chuyển tiền thuần từ HĐ tài chính (CFF)", "raw", "CF", "net_cash_inflows_outflows_from_financing_activities", "ty"),
    ("_h4", "CHỈ SỐ", "hdr", None, None, None),
    ("rev_ttm", "Doanh thu thuần TTM", "f", None, "{rev@ttm}", "ty"),
    ("npatmi_ttm", "LNST CĐ mẹ TTM", "f", None, "{npatmi@ttm}", "ty"),
    ("rev_yoy", "Tăng trưởng doanh thu (so cùng kỳ)", "f", None, 'IF({rev@lag}<=0,"",{rev}/{rev@lag}-1)', "pct"),
    ("npat_yoy", "Tăng trưởng LNST CĐ mẹ TTM (so cùng kỳ)", "f", None,
     'IF({npatmi_ttm@lag}<=0,"",{npatmi_ttm}/{npatmi_ttm@lag}-1)', "pct"),
    ("gm", "Biên lợi nhuận gộp (trong kỳ)", "f", None, "{gp}/{rev}", "pct"),
    ("gm_ttm", "Biên lợi nhuận gộp TTM", "f", None, "{gp@ttm}/{rev@ttm}", "pct"),
    ("nm_ttm", "Biên LNST CĐ mẹ TTM", "f", None, "{npatmi@ttm}/{rev@ttm}", "pct"),
    ("sga", "(CP bán hàng + CP QLDN) / Doanh thu TTM", "f", None, "-({sell@ttm0}+{ga@ttm0})/{rev@ttm}", "pct"),
    ("roe", "ROE TTM (VCSH CĐ mẹ bình quân)", "f", None, "{npatmi@ttm}/{eq_me@avg}", "pct"),
    ("roa", "ROA TTM (tổng tài sản bình quân)", "f", None, "{npat@ttm}/{ta@avg}", "pct"),
    ("de", "Nợ vay / VCSH", "f", None, "{debt}/{equity}", "x"),
    ("nde", "Nợ vay ròng / VCSH", "f", None, "{net_debt}/{equity}", "x"),
    ("bond_debt", "Trái phiếu / Tổng nợ vay", "f", None, "{bonds}/{debt}", "pct"),
    ("cod", "Chi phí vốn vay TTM (lãi vay / nợ vay bình quân)", "f", None, "-{int_exp@ttm0}/{debt@avg}", "pct"),
    ("icr", "EBIT / Chi phí lãi vay TTM (lần)", "f", None,
     'IF({int_exp@ttm0}=0,"",({pbt@ttm}-{int_exp@ttm0})/-{int_exp@ttm0})', "x"),
    ("inv_ta", "Tồn kho / Tổng tài sản", "f", None, "{inv}/{ta}", "pct"),
    ("adv_inv", "Người mua trả tiền trước / Tồn kho", "f", None, "{adv_all}/{inv}", "pct"),
    ("adv_rev", "Người mua trả tiền trước / DT TTM (lần)", "f", None, "{adv_all}/{rev@ttm}", "x"),
    ("inv_turn", "Vòng quay tồn kho TTM (lần)", "f", None, "-{cogs@ttm}/{inv@avg}", "x"),
    ("liq", "(Tiền + ĐTNH) / Vay ngắn hạn (lần)", "f", None, "(N({cash})+N({st_inv}))/{st_debt}", "x"),
    ("cfo_ttm", "CFO TTM", "f", None, "{cfo@ttm}", "ty"),
    ("cfo_np", "CFO TTM / LNST CĐ mẹ TTM (lần)", "f", None, "{cfo@ttm}/{npatmi@ttm}", "x"),
]
KEYS = [b[0] for b in BLOCK]
ROW_OF = {k: i + 1 for i, k in enumerate(KEYS)}          # dòng i của khối = top + ROW_OF[key]
NROW = len(BLOCK)
FMT = {"ty": '#,##0;-#,##0', "pct": "0.0%", "x": '0.00"x"', "n": "0"}
TOK = re.compile(r"\{(\w+)(?:@(\w+))?\}")


def _col(i):
    from openpyxl.utils import get_column_letter
    return get_column_letter(i)


def expand(expr, key_row, c, c0, mode):
    """Dịch biểu thức token -> công thức Excel tại cột số c; c0 = cột kỳ đầu tiên; mode 'Q'|'Y'.
    key_row[k] = số dòng (cùng sheet) hoặc (tiền tố sheet "'FS Industry'!", số dòng) khi dòng nằm ở sheet khác.
    Trả None nếu token cần kỳ trước cột đầu (để ô trống)."""
    lag = 4 if mode == "Q" else 1
    bad = False

    def ref(k):
        v = key_row[k]
        return v if isinstance(v, tuple) else ("", v)

    def cell(k, cc):
        sh, r = ref(k)
        return f"{sh}{_col(cc)}{r}"

    def rng_(k, a, b):
        sh, r = ref(k)
        return f"{sh}{_col(a)}{r}:{_col(b)}{r}"

    def rep(m):
        nonlocal bad
        k, op = m.group(1), m.group(2)
        if op is None:
            return cell(k, c)
        if op in ("ttm", "ttm0"):
            if mode == "Y":
                return cell(k, c) if op == "ttm" else f"N({cell(k, c)})"
            if c - 3 < c0:
                bad = True
                return "0"
            rng = rng_(k, c - 3, c)
            return f'IF(COUNT({rng})=4,SUM({rng}),"")' if op == "ttm" else f"SUM({rng})"
        if op == "avg":
            if c - lag < c0:
                bad = True
                return "0"
            return f"(({cell(k, c)}+{cell(k, c - lag)})/2)"
        if op == "lag":
            if c - lag < c0:
                bad = True
                return "0"
            return cell(k, c - lag)
        raise ValueError(op)

    out = TOK.sub(rep, expr)
    return None if bad else f'=IFERROR({out},"")'
