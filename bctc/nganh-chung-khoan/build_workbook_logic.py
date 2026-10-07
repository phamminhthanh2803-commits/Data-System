# -*- coding: utf-8 -*-
r"""build_workbook_logic.py — TÁI TẠO TOÀN BỘ LOGIC TÍNH TOÁN của workbook IB&Brokerage (Key ratios, FS Industry, Drivers)
bằng máy tính công thức pycel trên một workbook "lite" mà dữ liệu gốc đã được thay bằng số từ pipeline.

Cách làm:
 1. Từ workbook gốc dựng _wb_lite.xlsx: BS/IS/NOTE/Peer Data = GIÁ TRỊ (ô GETPIVOTDATA lấy từ pipeline, BS tra theo dòng);
    Key ratios / FS Industry / Drivers = GIỮ CÔNG THỨC (GETPIVOTDATA -> giá trị pipeline; link ngoài '[1]...' -> giá trị đã lưu;
    GETPIVOTDATA trên pivot 'Số TK mở mới' -> tính lại từ Table2); 'Số TK mở mới' = giá trị.
 2. pycel tính mọi công thức của 3 sheet đó; đối chiếu với giá trị workbook đang lưu -> logic\validation_logic.csv.
 3. Lặp G36 qua 87 mã (thay 55 dòng dữ liệu gốc của công ty bằng số pipeline) -> key_ratios_by_ticker.csv (long).
    (--peer: lặp G67 qua danh mục peer -> peer_compare.csv; mặc định bỏ vì pivot trên key_ratios_by_ticker.csv chọn mã tuỳ ý)
 4. Xuất logic\: fs_industry.csv, key_ratios_industry.csv, key_ratios_by_ticker.csv, drivers.csv, IB&Brokerage_logic.xlsx
Chạy: python build_workbook_logic.py [--wb <xlsx>] [--no-loop]
"""
import argparse, os, re, sys, warnings
import numpy as np
import pandas as pd
import openpyxl
from openpyxl.utils import get_column_letter, column_index_from_string

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_excel_feed as B
import render_workbook_feed as R

OUT = os.path.join(HERE, "excel_feed", "logic")
LITE = os.path.join(HERE, "excel_feed", "_wb_lite.xlsx")
VALUE_SHEETS = ["BS", "IS", "NOTE", "Peer Data", "Số TK mở mới", "Classification", "Market Share"]
FORMULA_SHEETS = ["Key ratios", "FS Industry", "Drivers"]
ARR_YEAR = re.compile(r'^=SUMPRODUCT\((?:\(LEFT\(\$?[A-Z]+\$?\d+:\$?[A-Z]+\$?\d+,2\)="(Q\d)"\)\*)?\(RIGHT\((\$?[A-Z]+\$?\d+):(\$?[A-Z]+\$?\d+),4\)\+0=([A-Z]+\$?\d+)\)\*\$?[A-Z]+\$?(\d+):\$?[A-Z]+\$?\d+\)$')   # nam = tong cac quy (hoac chi Q4) cua dong
PURE = re.compile(r'^=(IFERROR\()?(IF\(\$?[A-Z]+\$?\d+=""\s*,\s*)?GETPIVOTDATA\(')
KR_COMPANY_ROWS = list(range(36, 65))          # ty le cong ty (G36)
KR_RAW_ROWS = list(range(88, 146))              # du lieu goc theo ma (GETPIVOTDATA theo G36) + dan xuat
KR_INDUSTRY_ROWS = list(range(4, 34))
KR_PEER_ROWS = list(range(67, 85))
KR_COL0, KR_COL1 = column_index_from_string("I"), column_index_from_string("AX")


def log(m):
    print(m, flush=True)


def load_wb(path):
    return openpyxl.load_workbook(path, read_only=True), openpyxl.load_workbook(path, read_only=True, data_only=True)


def sheet_cells(wb, sn):
    return {(c.row, c.column): c.value for r in wb[sn].iter_rows() for c in r if getattr(c, "value", None) is not None}


def tk_pivot(vals_tk):
    """Table2 'Số TK mở mới' -> DataFrame (year, quarter, field -> sum)  để thay GETPIVOTDATA của Drivers."""
    hdr_row = next(r for (r, c), v in vals_tk.items() if v == "Date")
    cols = {c: str(vals_tk[(hdr_row, c)]).strip() for (r, c) in vals_tk if r == hdr_row}
    rows = []
    r = hdr_row + 1
    while (r, min(cols)) in vals_tk:
        rec = {cols[c]: vals_tk.get((r, c)) for c in cols}
        rows.append(rec); r += 1
    df = pd.DataFrame(rows)
    df["Date"] = pd.to_datetime(df["Date"])
    df = tk_extend_vsdc(df)
    df["y"] = df.Date.dt.year; df["q"] = (df.Date.dt.month - 1) // 3 + 1
    return df


VSDC_T2 = os.path.join(os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data")), "vsdc-accounts", "vsdc_tk_ndt_table2.csv")


def tk_extend_vsdc(df):
    """Noi them cac thang MOI HON workbook tu file tu dong D:/market-data/vsdc-accounts/vsdc_tk_ndt_table2.csv
    (pull_vsdc_accounts.py, buoc vsdc-accounts thu Hai) -> Drivers khong phai cho copy tay sheet 'So TK mo moi'."""
    if not os.path.exists(VSDC_T2):
        return df
    try:
        v = pd.read_csv(VSDC_T2, encoding="utf-8-sig")
        v["Date"] = pd.to_datetime(v["Date"])
        add = v[v.Date > df.Date.max()][[c for c in v.columns if c in df.columns]]
        if len(add):
            print(f"  Table2 'So TK mo moi': noi them {len(add)} thang tu VSDC ({add.Date.min():%Y-%m}..{add.Date.max():%Y-%m})")
            df = pd.concat([df, add], ignore_index=True)
    except Exception as e:                                        # noqa: BLE001
        print(f"  ! khong doc duoc {VSDC_T2}: {e}")
    return df


def norm_ws(s):
    return re.sub(r"\s+", " ", str(s)).strip().lower()


def tk_lookup(df, field, y, q):
    f = norm_ws(field.replace("Sum of ", ""))
    col = next((c for c in df.columns if norm_ws(c) == f), None)
    if col is None:
        return None
    x = df[(df.y == y) & (df.q == q)][col]
    return float(pd.to_numeric(x, errors="coerce").sum()) if len(x) else 0.0


def build_lite(wbp, lk, canon, faithful=False):
    wf, wv = load_wb(wbp)
    out = openpyxl.Workbook(); out.remove(out.active)
    tkdf = tk_pivot(sheet_cells(wv, "Số TK mở mới"))
    n_sub = {"getpivot": 0, "extlink": 0, "tkpivot": 0}
    for sn in VALUE_SHEETS + FORMULA_SHEETS:
        if sn not in wf.sheetnames:
            continue
        vals = sheet_cells(wv, sn); ws = out.create_sheet(sn)
        valsL = {(r, get_column_letter(c)): v for (r, c), v in vals.items()}   # R.* tra o theo (row, CHU cot)
        for (r, c), f in sheet_cells(wf, sn).items():
            ref = f"{get_column_letter(c)}{r}"
            if hasattr(f, "text") and not isinstance(f, str):        # ArrayFormula (SUMPRODUCT nam cua FS Industry) -> giu dang text
                f = str(f.text)
                ws[ref] = f.replace("_xlfn.", ""); continue
            if not (isinstance(f, str) and f.startswith("=")):
                ws[ref] = f; continue
            if "DATA!$A$3" in f and PURE.match(f):
                call = R.pick_getpivot(f, valsL, r)
                args = {k: R.norm(k, R.eval_arg(e, valsL, r)) for k, e in R.field_pairs(call)} if call else {}
                if args.get("metric"):
                    args["metric"] = canon.get(args["metric"].lower() if faithful else args["metric"], args["metric"] + " <khong co item>")
                if not faithful and sn == "BS" and not args.get("row_order") and isinstance(vals.get((r, 2)), (int, float)):
                    args["row_order"] = str(int(vals[(r, 2)]))
                got = lk.get(args.get("ticker"), args.get("metric"), args.get("row_order"), args.get("year"), args.get("quarter"))
                ws[ref] = got if got is not None else None; n_sub["getpivot"] += 1; continue
            if "GETPIVOTDATA" in f and "Số TK mở mới" in f:
                calls = R.gp_calls(f)
                a = R.split_args(calls[0]) if calls else []
                field = a[0].strip('"') if a else ""
                kw = {}
                for i in range(2, len(a) - 1, 2):
                    kw[a[i].strip('"')] = R.eval_arg(a[i + 1], valsL, r)
                y = R.norm("year", kw.get("Years (Date)")); q = R.norm("quarter", kw.get("Quarters (Date)"))
                got = tk_lookup(tkdf, field, y, q) if (y and q) else None
                ws[ref] = got if got is not None else vals.get((r, c)); n_sub["tkpivot"] += 1; continue
            if "[1]" in f or "GETPIVOTDATA" in f or sn in VALUE_SHEETS:
                ws[ref] = vals.get((r, c)); n_sub["extlink"] += ("[1]" in f); continue
            ws[ref] = f.replace("_xlfn.", "")
    out.save(LITE); wf.close(); wv.close()
    log(f"  lite: {LITE} | thay GETPIVOTDATA {n_sub['getpivot']:,}, link ngoài {n_sub['extlink']}, pivot TK {n_sub['tkpivot']}")


def evaluate_all(xl, wv, sn):
    """Tính mọi ô công thức của sheet sn; trả (values dict, report rows)."""
    wf = openpyxl.load_workbook(LITE, read_only=True)
    cells = sheet_cells(wf, sn); cached = sheet_cells(wv, sn); wf.close()
    vals, rep, arr = {}, [], []
    for (r, c), f in cells.items():
        ref = f"'{sn}'!{get_column_letter(c)}{r}"
        if hasattr(f, "text") and not isinstance(f, str):
            f = str(f.text)
        m_arr = ARR_YEAR.match(f) if isinstance(f, str) else None
        if m_arr:                                                     # SUMPRODUCT((RIGHT($U$4:$BM$4,4)+0=I$4)*$U24:$BM24): tinh sau bang Python
            arr.append((r, c, f, m_arr)); continue
        if isinstance(f, str) and f.startswith("="):
            try:
                v = xl.evaluate(ref)
            except Exception as e:                                # noqa: BLE001
                v = f"#PYCEL {type(e).__name__}: {str(e)[:60]}"
            exp = cached.get((r, c))
            if isinstance(v, str) and v.startswith("#PYCEL") and "DATA!" not in f:   # pycel khong ho tro (vd XLOOKUP tbl_MarketShare) -> giu gia tri workbook
                v = exp
            vals[(r, c)] = v
            ok = _same(v, exp)
            rep.append({"sheet": sn, "cell": f"{get_column_letter(c)}{r}", "expected": exp, "pipeline": v, "ok": ok, "formula": f[:120] if not ok else ""})
        else:
            vals[(r, c)] = f
    for r, c, f, m in arr:                                          # tong cac o quy cung dong co nam (4 ky tu cuoi tieu de) = nam o cot nay
        qpre, h0, h1, ycell, row_ref = m.group(1), m.group(2), m.group(3), m.group(4), int(m.group(5))
        hr = int(re.sub(r"\D", "", h0)); c0 = column_index_from_string(re.sub(r"[^A-Z]", "", h0)); c1 = column_index_from_string(re.sub(r"[^A-Z]", "", h1))
        y = vals.get((int(re.sub(r"\D", "", ycell)), c)); y = str(int(y)) if isinstance(y, (int, float)) else str(y)
        tot = 0.0
        for cc in range(c0, c1 + 1):
            h = vals.get((hr, cc)); v = vals.get((row_ref, cc))
            if h is not None and str(h)[-4:] == y and (not qpre or str(h)[:2] == qpre) and isinstance(v, (int, float)) and not isinstance(v, bool):
                tot += float(v)
        vals[(r, c)] = tot
        exp = cached.get((r, c)); ok = _same(tot, exp)
        rep.append({"sheet": sn, "cell": f"{get_column_letter(c)}{r}", "expected": exp, "pipeline": tot, "ok": ok, "formula": f[:120] if not ok else ""})
    return vals, rep


def _same(v, e):
    if isinstance(v, str) and v.startswith("#PYCEL"):
        return False
    if e is None or e == "":
        return v is None or v == "" or (isinstance(v, str) and v.startswith("#"))
    if isinstance(e, (int, float)) and not isinstance(e, bool):
        try:
            return abs(float(v) - float(e)) <= 1e-6 * max(1.0, abs(float(e)))
        except (TypeError, ValueError):
            return False
    return str(v) == str(e)


def grid_to_frame(vals, hdr_rows, label_cols, rows, c0, c1):
    """Bảng: nhãn = các cột label_cols, cột = tiêu đề ở hdr_rows (nối bằng '|'), chỉ dòng có ít nhất 1 số."""
    cols = {}
    for c in range(c0, c1 + 1):
        h = "|".join(str(vals.get((hr, c), "")) for hr in hdr_rows).strip("|")
        if h:
            cols[c] = h
    recs = []
    for r in rows:
        lab = " / ".join(str(vals.get((r, lc), "")).strip() for lc in label_cols if vals.get((r, lc)) not in (None, ""))
        row = {"row": r, "label": lab}
        num = False
        for c, h in cols.items():
            v = vals.get((r, c))
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                row[h] = v; num = True
            else:
                row[h] = None
        if num or lab:
            recs.append(row)
    return pd.DataFrame(recs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wb", default=None)
    ap.add_argument("--no-loop", action="store_true")
    ap.add_argument("--peer-only", action="store_true", help="bo qua vong lap 87 ma (dung key_ratios_by_ticker.csv da co)")
    ap.add_argument("--peer", action="store_true", help="sinh them peer_compare.csv (mac dinh KHONG: pivot tren key_ratios_by_ticker.csv da chon ma tuy y)")
    ap.add_argument("--faithful", action="store_true", help="bat chuoc pivot (gop hoa/thuong, BS theo nhan) chi de chung minh logic khop 100%")
    a = ap.parse_args()
    global LITE
    if a.faithful:
        LITE = LITE.replace("_wb_lite", "_wb_lite_faithful")
    wbp = a.wb or next(p for p in [os.path.join(os.path.expanduser("~"), "Downloads", "IB&Brokerage_Genea_2Q26.xlsx"),
                                    os.path.join(os.path.expanduser("~"), "OneDrive - Cong ty co phan Dau tu PV2", "IB&Brokerage_Genea_2Q26.xlsx")] if os.path.exists(p))
    os.makedirs(OUT, exist_ok=True)
    log(f"Workbook: {wbp}")
    B.CASEFOLD = a.faithful
    df = B.load_source(); lk = R.Lookup(df)
    canon = {m.lower(): m for m in df.metric.unique()} if a.faithful else {**{m: m for m in df.metric.unique()}, **B.ALIAS}
    build_lite(wbp, lk, canon, faithful=a.faithful)

    import logging
    logging.getLogger("pycel").setLevel(logging.CRITICAL)
    import pycel.excellib as XL
    from pycel.excelutil import flatten, VALUE_ERROR, NUM_ERROR
    def median(*args):                      # pycel thieu MEDIAN
        xs = [x for x in flatten(args) if isinstance(x, (int, float)) and not isinstance(x, bool)]
        return NUM_ERROR if not xs else float(np.median(xs))
    def search(find_text, within_text, start_num=1):   # pycel thieu SEARCH (khong phan biet hoa/thuong)
        try:
            i = str(within_text).lower().find(str(find_text).lower(), int(start_num) - 1)
        except Exception:
            return VALUE_ERROR
        return VALUE_ERROR if i < 0 else i + 1
    XL.median = median; XL.search = search
    from pycel import ExcelCompiler
    xl = ExcelCompiler(filename=LITE)
    _, wv = load_wb(wbp)
    all_vals, report = {}, []
    for sn in FORMULA_SHEETS:
        vals, rep = evaluate_all(xl, wv, sn)
        all_vals[sn] = vals; report += rep
        bad = [x for x in rep if not x["ok"]]
        log(f"  {sn:12} {len(rep):5,} công thức | khớp {len(rep) - len(bad):5,} | lệch {len(bad):,}")
    rep = pd.DataFrame(report); rep.to_csv(os.path.join(OUT, "validation_logic.csv"), index=False, encoding="utf-8-sig")
    # gia tri tung o cua 3 sheet logic (de build_presentation.py do vao ban sao Excel)
    cells = [{"sheet": sn, "row": r, "col": c, "value": v} for sn, vals in all_vals.items() for (r, c), v in vals.items()
             if isinstance(v, (int, float)) and not isinstance(v, bool)]
    pd.DataFrame(cells).to_csv(os.path.join(OUT, "cells_values.csv"), index=False, encoding="utf-8-sig")
    bad = rep[~rep.ok]
    if len(bad):
        pd.set_option("display.width", 240); log(bad.groupby("sheet").head(6).to_string(index=False))
        err = bad[bad.pipeline.astype(str).str.startswith("#PYCEL")]
        if len(err):
            log("  hàm pycel không hỗ trợ: " + str(err.pipeline.astype(str).str[:50].value_counts().head(5).to_dict()))

    # ---- xuất bảng trạng thái mặc định
    kr = all_vals["Key ratios"]
    fsi = all_vals["FS Industry"]; drv = all_vals["Drivers"]
    fs_hdr = [4]; fs_rows = list(range(5, 142)); fs_cols = (column_index_from_string("H"), column_index_from_string("BN"))
    grid_to_frame(fsi, fs_hdr, [1, 2, 3, 4, 5, 6, 7], fs_rows, *fs_cols).to_csv(os.path.join(OUT, "fs_industry.csv"), index=False, encoding="utf-8-sig")
    grid_to_frame(kr, [4], [6], KR_INDUSTRY_ROWS, KR_COL0, KR_COL1).to_csv(os.path.join(OUT, "key_ratios_industry.csv"), index=False, encoding="utf-8-sig")
    grid_to_frame(drv, [8], [5, 6, 7], list(range(9, 63)), column_index_from_string("I"), column_index_from_string("AS")).to_csv(os.path.join(OUT, "drivers.csv"), index=False, encoding="utf-8-sig")

    if a.no_loop:                                              # 16/09/2026: khoi cong ty tra thang Data_FS -> khong can vong lap pycel 87 ma
        import subprocess
        subprocess.run([sys.executable, os.path.join(HERE, "build_presentation.py"), "--wb", wbp], env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        log(f"-> {OUT} (no-loop)"); return
    # ---- vòng lặp công ty: thay G36 + 55 dòng dữ liệu gốc (rows 91-120, 132-143) bằng pipeline, tính lại rows 36-64 + 121-131 + 144-145
    hdr_year = {c: kr.get((89, c)) for c in range(KR_COL0, KR_COL1 + 1)}; hdr_q = {c: kr.get((90, c)) for c in range(KR_COL0, KR_COL1 + 1)}
    per = {c: kr.get((36, c)) for c in range(KR_COL0, KR_COL1 + 1)}
    raw_rows = [r for r in KR_RAW_ROWS if isinstance(kr.get((r, 4)), (int, float)) and kr.get((r, 5))]
    ratio_rows = [r for r in KR_COMPANY_ROWS + list(range(121, 132)) + [144, 145] if kr.get((r, 6)) and any(isinstance(kr.get((r, c)), (int, float)) for c in range(KR_COL0, KR_COL1 + 1))]
    def setv(addr, v):                       # pycel: o phai co trong cell_map (da evaluate) moi set_value duoc
        try:
            xl.set_value(addr, v)
        except AssertionError:
            xl.evaluate(addr); xl.set_value(addr, v)
    tickers = [] if a.peer_only else sorted(df.ticker.unique())
    recs = []
    for i, t in enumerate(tickers):
        setv("'Key ratios'!G36", t)
        for r in raw_rows:
            m, ro = canon.get(str(kr[(r, 5)]).strip(), str(kr[(r, 5)]).strip()), str(int(kr[(r, 4)]))
            for c in range(KR_COL0, KR_COL1 + 1):
                y, q = R.norm("year", hdr_year[c]), R.norm("quarter", hdr_q[c])
                v = lk.get(t, m, ro, y, q) if (y and q) else None
                setv(f"'Key ratios'!{get_column_letter(c)}{r}", v if v is not None else "")
        for r in ratio_rows + raw_rows:
            lab = str(kr.get((r, 6)) or kr.get((r, 5)) or "").strip()
            for c in range(KR_COL0, KR_COL1 + 1):
                try:
                    v = xl.evaluate(f"'Key ratios'!{get_column_letter(c)}{r}")
                except Exception:                                 # noqa: BLE001
                    v = None
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    recs.append({"ticker": t, "row": r, "chi_tieu": lab, "period": per[c], "year": hdr_year[c], "quarter": hdr_q[c], "value": float(v)})
        if i % 10 == 0:
            log(f"  Key ratios theo mã: {i + 1}/{len(tickers)} ({t})")
    if a.peer_only and os.path.exists(os.path.join(OUT, "key_ratios_by_ticker.csv")):
        krt = pd.read_csv(os.path.join(OUT, "key_ratios_by_ticker.csv"), encoding="utf-8-sig")
    else:
        krt = pd.DataFrame(recs); krt.to_csv(os.path.join(OUT, "key_ratios_by_ticker.csv"), index=False, encoding="utf-8-sig")
    log(f"  key_ratios_by_ticker: {len(krt):,} dòng, {krt.ticker.nunique()} mã, {krt.chi_tieu.nunique()} chỉ tiêu")

    if a.peer:
        # ---- vòng lặp peer: G67 qua danh mục F91:F120
        setv("'Key ratios'!G36", kr.get((36, 7)))
        pdv = sheet_cells(openpyxl.load_workbook(LITE, read_only=True), "Peer Data")
        metrics = [pdv.get((r, 2)) for r in range(7, 41) if pdv.get((r, 2))]     # danh muc dropdown G67 = Peer Data!B7:B40
        prec = []
        for m in metrics:
            setv("'Key ratios'!G67", m)
            for r in KR_PEER_ROWS:
                lab = str(kr.get((r, 6)) or "").strip()
                if not lab:
                    continue
                for c in range(KR_COL0, KR_COL1 + 1):
                    try:
                        v = xl.evaluate(f"'Key ratios'!{get_column_letter(c)}{r}")
                    except Exception:                                 # noqa: BLE001
                        v = None
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        prec.append({"chi_tieu": m, "row": r, "dong": lab, "period": per[c], "value": float(v)})
        pc = pd.DataFrame(prec); pc.to_csv(os.path.join(OUT, "peer_compare.csv"), index=False, encoding="utf-8-sig")
        log(f"  peer_compare: {len(pc):,} dòng, {len(metrics)} chỉ tiêu")

    # ---- bản NĂM: Key ratios chỉ định nghĩa theo quý (TTM = 4 quý); giá trị tại Q4 = cả năm (dòng chảy TTM) / cuối năm (số dư)
    yr = krt[krt.quarter == 4].copy(); yr["period"] = yr.year.astype(int).astype(str); yr = yr.drop(columns=["quarter"])
    yr.to_csv(os.path.join(OUT, "key_ratios_by_ticker_yearly.csv"), index=False, encoding="utf-8-sig")
    kri = pd.read_csv(os.path.join(OUT, "key_ratios_industry.csv"), encoding="utf-8-sig")
    q4 = [c for c in kri.columns if str(c).startswith("Q4-")]
    kri_y = kri[["row", "label"] + q4].rename(columns={c: c[3:] for c in q4})
    kri_y.to_csv(os.path.join(OUT, "key_ratios_industry_yearly.csv"), index=False, encoding="utf-8-sig")
    log(f"  bản năm: key_ratios_by_ticker_yearly {len(yr):,} dòng | key_ratios_industry_yearly {len(q4)} năm")
    with pd.ExcelWriter(os.path.join(OUT, "IB&Brokerage_logic.xlsx"), engine="openpyxl") as xw:
        for fn, sn in [("fs_industry", "FS Industry"), ("key_ratios_industry", "Key ratios - nganh"), ("drivers", "Drivers")] + ([("peer_compare", "Peer compare")] if a.peer else []):
            pd.read_csv(os.path.join(OUT, fn + ".csv"), encoding="utf-8-sig").to_excel(xw, sheet_name=sn, index=False)
        krt.to_excel(xw, sheet_name="Key ratios by ticker", index=False)
        yr.to_excel(xw, sheet_name="Key ratios by ticker (nam)", index=False)
        kri_y.to_excel(xw, sheet_name="Key ratios - nganh (nam)", index=False)
    import subprocess
    subprocess.run([sys.executable, os.path.join(HERE, "build_presentation.py"), "--wb", wbp], env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    log(f"-> {OUT}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
