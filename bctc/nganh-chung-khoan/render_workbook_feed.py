# -*- coding: utf-8 -*-
r"""render_workbook_feed.py — dựng file Excel CÙNG CẤU TRÚC với IB&Brokerage_Genea_2Q26.xlsx (các sheet BS, IS, NOTE, Peer Data,
Key ratios, Drivers): giữ nguyên toạ độ ô, nhãn, tiêu đề kỳ; MỌI ô GETPIVOTDATA được thay bằng GIÁ TRỊ tính từ pipeline
(cùng ngữ nghĩa pivot: SUM theo ticker/metric/row_order/năm/quý, FY = subtotal năm, giao điểm trống = 0).
Đồng thời đối chiếu từng ô với giá trị pivot đang lưu trong workbook -> validation_full.csv (đây là kiểm định đầy đủ nhất).

    python render_workbook_feed.py [--wb <đường dẫn xlsx>]     (mặc định: bản trong Downloads / OneDrive)
Ra: excel_feed\IB&Brokerage_values.xlsx, excel_feed\validation_full.csv, excel_feed\validation_samples.csv (từ sheet _Validation_Samples)
"""
import argparse, os, re, sys
import numpy as np
import pandas as pd
import openpyxl
from openpyxl.utils import get_column_letter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "excel_feed")
sys.path.insert(0, HERE)
import build_excel_feed as B

SHEETS = ["BS", "IS", "NOTE", "Peer Data", "Key ratios", "Drivers"]
def split_args(call):
    """Tách danh sách tham số theo dấu phẩy CẤP NGOÀI (bỏ qua phẩy trong ngoặc / chuỗi)."""
    out, cur, depth, instr = [], "", 0, False
    for ch in call:
        if ch == '"':
            instr = not instr
        if not instr:
            if ch == "(": depth += 1
            elif ch == ")": depth -= 1
            elif ch == "," and depth == 0:
                out.append(cur); cur = ""; continue
        cur += ch
    if cur.strip():
        out.append(cur)
    return [x.strip() for x in out]


def field_pairs(call):
    a = split_args(call)
    pairs = []
    for i in range(2, len(a) - 1, 2):
        f = a[i].strip().strip('"')
        if f in ("ticker", "metric", "row_order", "year", "quarter"):
            pairs.append((f, a[i + 1]))
    return pairs
REF = re.compile(r'^\$?([A-Z]{1,3})\$?(\d+)$')


class Lookup:
    def __init__(self, df):
        self.g = {
            "t_q": df.groupby(["ticker", "metric", "row_order", "year", "q"]).value.sum(),
            "t_y": df.groupby(["ticker", "metric", "row_order", "year"]).value.sum(),
            "r_q": df.groupby(["metric", "row_order", "year", "q"]).value.sum(),
            "r_y": df.groupby(["metric", "row_order", "year"]).value.sum(),
            "m_q": df.groupby(["metric", "year", "q"]).value.sum(),
            "m_y": df.groupby(["metric", "year"]).value.sum(),
        }
        self.items_t = set(zip(df.ticker, df.metric, df.row_order))
        self.items_r = set(zip(df.metric, df.row_order))
        self.items_m = set(df.metric)
        self.cols_q = set(zip(df.year, df.q)); self.cols_y = set(df.year)

    def get(self, t, m, ro, y, q):
        """Trả số (0 nếu item + cột tồn tại mà không có dòng) hoặc None (GETPIVOTDATA lỗi -> '')."""
        if m is None or y is None:
            return None
        if t:
            key = (t, m, ro, y, q) if q is not None else (t, m, ro, y); g = self.g["t_q" if q is not None else "t_y"]; item_ok = (t, m, ro) in self.items_t
        elif ro:
            key = (m, ro, y, q) if q is not None else (m, ro, y); g = self.g["r_q" if q is not None else "r_y"]; item_ok = (m, ro) in self.items_r
        else:
            key = (m, y, q) if q is not None else (m, y); g = self.g["m_q" if q is not None else "m_y"]; item_ok = m in self.items_m
        col_ok = ((y, q) in self.cols_q) if q is not None else (y in self.cols_y)
        if not (item_ok and col_ok):
            return None
        v = g.get(key)
        return 0.0 if v is None else float(v)


def cell_val(ws_vals, ref, row):
    m = REF.match(ref.replace("$", "").strip() if not ref.startswith("$") else ref)
    r2 = REF.match(ref.strip())
    if not r2:
        return None
    col, rr = r2.group(1), int(r2.group(2))
    return ws_vals.get((rr, col))


def eval_arg(expr, ws_vals, row):
    e = expr.strip()
    m = re.match(r'^TRIM\((.+)\)$', e)
    if m:   # TRIM cua Excel con GOP khoang trang ben trong -> nhan 2 khoang trang trong pivot se KHONG khop (tra "")
        v = cell_val(ws_vals, m.group(1), row); return None if v is None else re.sub(r" {2,}", " ", str(v).strip())
    m = re.match(r'^TEXT\(ROW\(\)\s*-\s*(\d+)\s*,\s*"0"\)$', e)
    if m:
        return str(row - int(m.group(1)))
    if REF.match(e):
        return cell_val(ws_vals, e, row)
    m = re.match(r'^"(.*)"$', e)
    if m:
        return m.group(1)
    try:
        return float(e)
    except ValueError:
        return None


def norm(field, v):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if field in ("year", "quarter"):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None
    if field == "row_order":
        try:
            return str(int(float(v)))
        except (TypeError, ValueError):
            return str(v).strip()
    return str(v).strip()


def gp_calls(formula):
    """Bóc mọi GETPIVOTDATA(...) với ngoặc cân bằng (TRIM(...), TEXT(...) lồng bên trong)."""
    out, i = [], 0
    while True:
        j = formula.find("GETPIVOTDATA(", i)
        if j < 0:
            return out
        k, depth = j + len("GETPIVOTDATA("), 1
        while k < len(formula) and depth:
            depth += {"(": 1, ")": -1}.get(formula[k], 0); k += 1
        out.append(formula[j + len("GETPIVOTDATA("):k - 1]); i = k


def pick_getpivot(formula, ws_vals, row):
    """Chọn GETPIVOTDATA(...) áp dụng (xử lý mẫu IFERROR(IF($C8="",A,B),""))."""
    calls = gp_calls(formula)
    if not calls:
        return None
    if len(calls) >= 2:
        m = re.search(r'IF\((\$?[A-Z]{1,3}\$?\d+)=""\s*,', formula)
        if m:
            v = cell_val(ws_vals, m.group(1), row)
            return calls[0] if (v is None or str(v).strip() == "") else calls[1]
    return calls[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wb", default=None)
    ap.add_argument("--mode", default="correct", choices=["correct", "faithful"],
                    help="correct: BS tra theo dong (cot B = row_order), nhan phan biet hoa/thuong | faithful: bat chuoc pivot (gop hoa/thuong) de doi chieu")
    a = ap.parse_args()
    wbp = a.wb or next(p for p in [os.path.join(os.path.expanduser("~"), "Downloads", "IB&Brokerage_Genea_2Q26.xlsx"),
                                    os.path.join(os.path.expanduser("~"), "OneDrive - Cong ty co phan Dau tu PV2", "IB&Brokerage_Genea_2Q26.xlsx")] if os.path.exists(p))
    B.log(f"Workbook: {wbp}")
    B.CASEFOLD = (a.mode == "faithful")
    df = B.load_source(); lk = Lookup(df); canon = {m.lower(): m for m in df.metric.unique()} if B.CASEFOLD else {**{m: m for m in df.metric.unique()}, **B.ALIAS}
    wf = openpyxl.load_workbook(wbp, read_only=True)                  # công thức
    wv = openpyxl.load_workbook(wbp, read_only=True, data_only=True)  # giá trị đã tính (pivot hiện tại)
    out = openpyxl.Workbook(); out.remove(out.active)
    report = []
    for sn in SHEETS:
        if sn not in wf.sheetnames:
            continue
        rows_f = list(wf[sn].iter_rows()); rows_v = list(wv[sn].iter_rows())
        vals = {}
        for r in rows_v:
            for c in r:
                if c.value is not None:
                    vals[(c.row, get_column_letter(c.column))] = c.value
        ws = out.create_sheet(sn)
        n_gp = n_ok = 0
        for r in rows_f:
            for c in r:
                if c.value is None:
                    continue
                key = (c.row, get_column_letter(c.column))
                f = c.value
                pure = isinstance(f, str) and "DATA!$A$3" in f and re.match(r'^=(IFERROR\()?(IF\(\$?[A-Z]+\$?\d+=""\s*,\s*)?GETPIVOTDATA\(', f) is not None
                if pure:      # chi thay o THUAN GETPIVOTDATA tren pivot DATA; cong thuc hon hop / pivot khac giu gia tri goc
                    call = pick_getpivot(f, vals, c.row)
                    args = {k: norm(k, eval_arg(e, vals, c.row)) for k, e in field_pairs(call)} if call else {}
                    if args.get("metric"):
                        args["metric"] = canon.get(args["metric"].lower() if B.CASEFOLD else args["metric"], args["metric"] + " <khong co item>")
                    if a.mode == "correct" and sn == "BS" and not args.get("row_order") and isinstance(vals.get((c.row, "B")), (int, float)):
                        args["row_order"] = str(int(vals[(c.row, "B")]))      # BS: tra dung dong bang can doi, khong cong nham thuyet minh/nhan trung; khong co item -> khong khop
                    got = lk.get(args.get("ticker"), args.get("metric"), args.get("row_order"), args.get("year"), args.get("quarter"))
                    cached = vals.get(key)
                    exp = None if (cached is None or cached == "" or isinstance(cached, str)) else float(cached)
                    ok = (got is None and exp is None) or (got is not None and exp is not None and abs(got - exp) <= 1e-6 * max(1.0, abs(exp)))
                    n_gp += 1; n_ok += ok
                    report.append({"sheet": sn, "cell": f"{key[1]}{key[0]}", **{k: args.get(k) for k in ("ticker", "metric", "row_order", "year", "quarter")},
                                   "expected": "" if exp is None else B.FMT % exp, "pipeline": "" if got is None else B.FMT % got, "ok": ok, "formula": "" if ok else f[:160]})
                    ws[f"{key[1]}{key[0]}"] = got if got is not None else None
                else:
                    ws[f"{key[1]}{key[0]}"] = vals.get(key, f if not (isinstance(f, str) and f.startswith("=")) else None)
        B.log(f"  {sn:10} GETPIVOTDATA {n_gp:6,} ô | khớp {n_ok:6,} | lệch {n_gp - n_ok:,}")
    # _Validation_Samples -> csv chuẩn cho build_excel_feed --validate
    if "_Validation_Samples" in wv.sheetnames:
        rows = [r for r in wv["_Validation_Samples"].iter_rows(values_only=True)]
        hdr = next((i for i, r in enumerate(rows) if r and r[0] == "sheet"), None)
        if hdr is not None:
            vs = pd.DataFrame([list(r[:8]) for r in rows[hdr + 1:] if r and any(x is not None for x in r[:8])], columns=list(rows[hdr][:8]))
            vs.to_csv(os.path.join(OUT, "validation_samples.csv"), index=False, encoding="utf-8-sig"); B.log(f"  _Validation_Samples -> validation_samples.csv ({len(vs)} dòng)")
    wf.close(); wv.close()
    rep = pd.DataFrame(report); rep.to_csv(os.path.join(OUT, "validation_full.csv"), index=False, encoding="utf-8-sig")
    bad = rep[~rep.ok]
    B.log(f"  TỔNG: {len(rep):,} ô GETPIVOTDATA, khác pivot workbook {len(bad):,}" + (" (mode correct: khac = o workbook dang SAI, xem bs_corrections.csv)" if a.mode == "correct" else ""))
    if a.mode == "correct" and len(bad):
        bad.assign(pivot_workbook=bad.expected, gia_tri_dung=bad.pipeline).drop(columns=["expected", "pipeline", "ok", "formula"]).to_csv(os.path.join(OUT, "bs_corrections.csv"), index=False, encoding="utf-8-sig")
    if len(bad):
        pd.set_option("display.width", 250); B.log(bad.groupby("sheet").head(4).to_string(index=False))
        B.log("  lệch theo sheet: " + str(bad.groupby("sheet").size().to_dict()))
    xp = os.path.join(OUT, "IB&Brokerage_values.xlsx"); out.save(xp); B.log(f"-> {xp}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
