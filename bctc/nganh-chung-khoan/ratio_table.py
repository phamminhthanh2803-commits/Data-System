# -*- coding: utf-8 -*-
r"""ratio_table.py - sheet Data_TyLe / Data_TyLe_Nam trong IB&Brokerage_Nganh.xlsx: CHI TIEU GOC = gia tri, TY LE = CONG THUC EXCEL.

Yeu cau (16/09/2026): "su dung cong thuc de tinh cac ratios, thay vi set up chi so san tu buoc dung file ben ngoai"
-> nguoi dung sua/soat logic ngay trong Excel. Cong thuc giu O(1)/o (chi tham chieu 1-4 dong lien truoc cung ma), khong SUMIFS/OFFSET.

Bo cuc bang (moi dong = 1 ma x 1 ky, sap xep ticker, t):
   ticker | period | year | quarter | t (chi so ky lien tuc)     : gia tri
   <chi tieu goc theo metric_map.csv: cash, fvtpl, ..., npat, oci_afs, ...>   : gia tri (ty VND; chi phi da doi ve duong nhu build_nganh_ck)
   ok_ttm, ok_lag4, ok_lag1                                                  : =AND(cung ma, du ky lien tiep)
   dan xuat (net_fvtpl, interest_cost, borrowings, margin_book, invest_book, shares_mn, bvps, opex, net_brokerage, total_income, ib_rev, npat_incl_oci)
   *_ttm cho cac dong chay dung trong ty le (Q: SUM 4 dong lien tiep; nam: chinh no)
   ty le (roe, roa, ..., g_equity_yoy)  = cong thuc, don vi nhu ratios_wide_*.csv (% x100)
Cong thuc mau (dong r):  ok_ttm = AND($A{r-3}=$A{r}, $E{r}-$E{r-3}=3);  npat_ttm = IF(ok_ttm, SUM(npat{r-3}:npat{r}), "")
   roe = IFERROR(npat_ttm / IF(ok_lag4,(equity+equity{r-4})/2, equity) * 100, "")
"""
import os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))

ID = ["ticker", "period", "year", "quarter", "t"]
HELP = ["ok_ttm", "ok_lag4", "ok_lag1"]
DERIVED = [   # (cot, cong thuc; {x} = o cung dong cua cot x)
    ("net_fvtpl", "={fvtpl_gain}-{fvtpl_loss}"),
    ("interest_cost", "=IF({interest_expense}>0,{interest_expense},{provision_borrow_cost})"),
    ("borrowings", "={st_borrow}+{st_bonds}+{lt_borrow}+{lt_bonds}"),
    ("margin_book", "=IF({margin_loans}>0,{margin_loans},{loans})"),
    ("invest_book", "={fvtpl}+{afs_st}+{htm_st}"),
    ("shares_mn", "={charter_capital}/10"),                        # ty VND * 1e9 / 10.000 d / 1e6 = /10 (trieu CP)
    ("bvps", "=IFERROR({equity_parent}*1000/{shares_mn},\"\")"),
    ("opex", "={selling_exp}+{ga_exp}"),
    ("net_brokerage", "={brokerage_rev}-{brokerage_cost}"),
    ("total_income", "={op_revenue}+{fin_income}"),
    ("ib_rev", "={underwriting_rev}+{advisory_rev}+{fin_advisory_rev}"),
    ("npat_incl_oci", "={npat}+{oci_afs}"),
]
TTM = ["npat", "npat_parent", "pbt", "op_revenue", "loan_income", "interest_cost", "net_brokerage", "brokerage_rev",
       "op_cost", "opex", "total_income", "fvtpl_gain", "ib_rev", "npat_incl_oci", "oci_afs", "fin_income", "afs_income", "htm_income"]
# ty le: {avg:x} = binh quan dau-cuoi (Q: t va t-4, nam: t va t-1); {lagN:x} = gia tri N ky truoc (N = 4 quy / 1 nam); {lag1:x} = 1 ky truoc
RATIOS = [
    ("roe", "=IFERROR({npat_ttm}/{avg:equity}*100,\"\")"),
    ("roa", "=IFERROR({npat_ttm}/{avg:total_assets}*100,\"\")"),
    ("net_margin", "=IFERROR({npat_ttm}/{op_revenue_ttm}*100,\"\")"),
    ("pbt_margin", "=IFERROR({pbt_ttm}/{op_revenue_ttm}*100,\"\")"),
    ("eps_ttm", "=IFERROR({npat_parent_ttm}*1000/{shares_mn},\"\")"),
    ("leverage", "=IF({equity}>0,{total_assets}/{equity},\"\")"),
    ("debt_to_equity", "=IF({equity}>0,{borrowings}/{equity},\"\")"),
    ("margin_to_equity", "=IFERROR({margin_book}/{equity}*100,\"\")"),
    ("margin_to_assets", "=IFERROR({margin_book}/{total_assets}*100,\"\")"),
    ("invest_to_assets", "=IFERROR({invest_book}/{total_assets}*100,\"\")"),
    ("cash_to_assets", "=IFERROR({cash}/{total_assets}*100,\"\")"),
    ("loan_yield", "=IFERROR({loan_income_ttm}/{avg:loans}*100,\"\")"),
    ("cost_of_funds", "=IFERROR({interest_cost_ttm}/{avg:borrowings}*100,\"\")"),
    ("lending_spread", "=IFERROR({loan_yield}-{cost_of_funds},\"\")"),
    ("brokerage_margin", "=IFERROR({net_brokerage_ttm}/{brokerage_rev_ttm}*100,\"\")"),
    ("cir", "=IFERROR(({op_cost_ttm}+{opex_ttm})/{total_income_ttm}*100,\"\")"),
    ("opex_to_income", "=IFERROR({opex_ttm}/{total_income_ttm}*100,\"\")"),
    ("brokerage_fee_rate", "=IFERROR({brokerage_rev}/{trading_value_investors}*100,\"\")"),
    ("mix_brokerage", "=IFERROR({brokerage_rev_ttm}/{op_revenue_ttm}*100,\"\")"),
    ("mix_lending", "=IFERROR({loan_income_ttm}/{op_revenue_ttm}*100,\"\")"),
    ("mix_fvtpl", "=IFERROR({fvtpl_gain_ttm}/{op_revenue_ttm}*100,\"\")"),
    ("mix_ib", "=IFERROR({ib_rev_ttm}/{op_revenue_ttm}*100,\"\")"),
    ("oci_to_npat", "=IFERROR({oci_afs_ttm}/ABS({npat_ttm})*100,\"\")"),
    ("g_npat_yoy", "=IF({okN},IFERROR(({npat}-{lagN:npat})/ABS({lagN:npat})*100,\"\"),\"\")"),
    ("g_revenue_yoy", "=IF({okN},IFERROR(({op_revenue}-{lagN:op_revenue})/ABS({lagN:op_revenue})*100,\"\"),\"\")"),
    ("g_margin_yoy", "=IF({okN},IFERROR(({margin_book}-{lagN:margin_book})/{lagN:margin_book}*100,\"\"),\"\")"),
    ("g_margin_qoq", "=IF({ok1},IFERROR(({margin_book}-{lag1:margin_book})/{lag1:margin_book}*100,\"\"),\"\")"),
    ("g_equity_yoy", "=IF({okN},IFERROR(({equity}-{lagN:equity})/{lagN:equity}*100,\"\"),\"\")"),
]


def col_letter(c):
    s = ""
    while c:
        c, r = divmod(c - 1, 26); s = chr(65 + r) + s
    return s


def item_columns():
    mp = pd.read_csv(os.path.join(HERE, "metric_map.csv"), encoding="utf-8-sig")
    return list(mp.metric)


def load_items(csv_path, freq):
    """ratios_wide_{Q|Y}.csv -> chi ID + chi tieu goc, sap xep ticker, t."""
    df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype={"period": str})
    items = [c for c in item_columns() if c in df.columns]
    df["t"] = (df.year * 4 + df.quarter - 1) if freq == "Q" else df.year
    df = df.sort_values(["ticker", "t"]).reset_index(drop=True)
    return df[ID + items], items


def build_rows(df, items, freq):
    """Tra (headers, rows): moi row = list gia tri / chuoi cong thuc theo dong Excel (dong 2 = du lieu dau)."""
    headers = ID + items + HELP + [k for k, _ in DERIVED] + [k + "_ttm" for k in TTM] + [k for k, _ in RATIOS]
    col = {h: col_letter(i + 1) for i, h in enumerate(headers)}
    N = 4 if freq == "Q" else 1                                       # lag YoY: 4 quy / 1 nam
    okN = "ok_lag4" if freq == "Q" else "ok_lag1"
    vals = df.astype(object).where(pd.notna(df), None).values.tolist()
    rows = []
    for i, v in enumerate(vals):
        r = i + 2
        ref = {h: f"{col[h]}{r}" for h in headers}
        def lagref(x, n):
            return f"{col[x]}{r - n}"
        f = {}
        f["ok_ttm"] = (f"=AND($A{r-3}=$A{r},$E{r}-$E{r-3}=3)" if (freq == "Q" and r >= 5) else ("=TRUE" if freq == "Y" else "=FALSE"))
        f["ok_lag4"] = f"=AND($A{r-4}=$A{r},$E{r}-$E{r-4}=4)" if r >= 6 else "=FALSE"
        f["ok_lag1"] = f"=AND($A{r-1}=$A{r},$E{r}-$E{r-1}=1)" if r >= 3 else "=FALSE"
        for k, tpl in DERIVED:
            f[k] = tpl.format(**ref)
        for k in TTM:
            f[k + "_ttm"] = (f"=IF({ref['ok_ttm']},SUM({col[k]}{r-3}:{col[k]}{r}),\"\")" if (freq == "Q" and r >= 5)
                             else (f"={ref[k]}" if freq == "Y" else "=\"\""))
        ctx = dict(ref); ctx["okN"] = ref[okN]; ctx["ok1"] = ref["ok_lag1"]
        for k, tpl in RATIOS:
            s = tpl
            for x in ["equity", "total_assets", "loans", "borrowings"]:
                if "{avg:" + x + "}" in s:
                    avg = (f"IF(AND({ref[okN]},{lagref(x, N)}<>\"\"),({ref[x]}+{lagref(x, N)})/2,{ref[x]})" if r - N >= 2 else ref[x])   # ky truoc trong -> dung so cuoi ky (nhu Python)
                    s = s.replace("{avg:" + x + "}", avg)
            for x in ["npat", "op_revenue", "margin_book", "equity"]:
                s = s.replace("{lagN:" + x + "}", lagref(x, N) if r - N >= 2 else ref[x])
                s = s.replace("{lag1:" + x + "}", lagref(x, 1) if r - 1 >= 2 else ref[x])
            f[k] = s.format(**ctx)
        rows.append(v + [f[h] for h in headers[len(ID) + len(items):]])
    return headers, rows


def write(ws, lo, headers, rows, tbl_name, chunk=5000):
    """Ghi header + rows (gia tri/cong thuc) vao sheet; tao hoac resize bang Excel tbl_name. lo=None -> tao moi."""
    n, ncol = len(rows), len(headers)
    if lo is not None:                                                # bang cu: BO bang (Unlist) truoc khi ghi - ghi cong thuc vao bang dang ton tai
        lo.Unlist()                                                   # -> Excel tu "calculated column": lay cong thuc dong dau (=FALSE) trai ca cot
    ws.Cells.ClearContents()
    ws.Range(ws.Cells(1, 1), ws.Cells(1, ncol)).Value = [headers]
    for i in range(0, n, chunk):
        part = [["" if x is None else x for x in row] for row in rows[i:i + chunk]]   # .Formula khong nhan None
        ws.Range(ws.Cells(2 + i, 1), ws.Cells(1 + i + len(part), ncol)).Formula = part
    lo = ws.ListObjects.Add(1, ws.Range(ws.Cells(1, 1), ws.Cells(n + 1, ncol)), None, 1)   # tao lai bang cung ten -> pivot cua nguoi dung van tro dung
    lo.Name = tbl_name; lo.TableStyle = "TableStyleLight1"
    n_items = len([h for h in headers if h not in HELP and not h.endswith("_ttm") and h not in dict(DERIVED) and h not in dict(RATIOS)])
    return n, ncol, ncol - n_items


def fill(ws, lo, csv_path, freq, tbl_name):
    df, items = load_items(csv_path, freq)
    headers, rows = build_rows(df, items, freq)
    return write(ws, lo, headers, rows, tbl_name)
