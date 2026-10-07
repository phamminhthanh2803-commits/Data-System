# -*- coding: utf-8 -*-
r"""
aggregate_industry.py
---------------------
Gộp nhiều công ty thành 1 BÁO CÁO TÀI CHÍNH TOÀN NGÀNH (phương pháp Σ - cộng dồn).

Với mỗi (tần suất, báo cáo, chỉ tiêu, kỳ) -> CỘNG giá trị của tất cả các mã, đồng
thời đếm số công ty có số liệu (độ phủ). Tất cả đều cùng đơn vị "Tỷ VND" nên cộng
trực tiếp được. Mã trùng không bị cộng đôi (mỗi mã 1 dòng/ô).

Đầu vào: file long từ unpivot_fiinprox.py (mặc định output\fiinprox_facts_all.csv).
Lọc tuỳ chọn theo ngành (--nganh) và/hoặc tần suất (--freq Q|Y).

Đầu ra (output\industry\):
    industry_fs_long.csv         long: freq, statement, metric, period, n_cong_ty, tong_gia_tri
    industry_FS_Q.xlsx / _Y.xlsx wide (chỉ tiêu × kỳ), mỗi báo cáo 1 sheet; kèm sheet *_SoCty

Dùng:
    python aggregate_industry.py
    python aggregate_industry.py --freq Q
    python aggregate_industry.py --nganh "Dịch vụ tài chính"
    python aggregate_industry.py --src "D:\\...\\Dịch_vụ_tài_chính.csv"
"""
import os
import csv
import argparse
from collections import defaultdict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SRC = os.path.join(HERE, "output", "fiinprox_facts_all.csv")
STMT_ORDER = ["BS", "IS", "CF", "NOTE", "CAR"]
csv.field_size_limit(10_000_000)


def aggregate_rows(rows_iter, nganh_filter="", freq_filter=""):
    """Cộng dồn theo (freq, statement, row_order, metric, period) từ iterable dict.

    Dùng được cho cả khi đọc file (DictReader) lẫn list facts trong RAM.
    """
    # key -> [tong, so_cty, row_order_min, level, statement_name, year, quarter]
    agg = {}
    n_rows = 0
    tickers = set()
    for row in rows_iter:
        if freq_filter and row["freq"] != freq_filter:
            continue
        if nganh_filter and row.get("nganh_L2", "") != nganh_filter:
            continue
        v = row.get("value")
        if v in ("", None):
            continue
        try:
            val = float(v)
        except (ValueError, TypeError):
            continue
        n_rows += 1
        tickers.add(row["ticker"])
        ro = row.get("row_order") or "0"
        try:
            ro = int(float(ro))
        except (ValueError, TypeError):
            ro = 0
        # Khoá gộp gồm row_order (vị trí dòng template, đồng nhất giữa các cty) +
        # metric, vì tên chỉ tiêu KHÔNG duy nhất trong 1 báo cáo (nhãn lặp).
        key = (row["freq"], row["statement_code"], ro, row["metric"], row["period"])
        rec = agg.get(key)
        if rec is None:
            agg[key] = [val, 1, ro, row.get("level", ""),
                        row.get("statement_name", ""), row.get("year", ""),
                        row.get("quarter", ""), row.get("parent", "")]
        else:
            rec[0] += val
            rec[1] += 1
    return agg, n_rows, len(tickers)


def aggregate(src, nganh_filter, freq_filter):
    """Stream file long rồi gộp (giữ tương thích chạy độc lập)."""
    with open(src, "r", encoding="utf-8-sig", newline="") as fh:
        return aggregate_rows(csv.DictReader(fh), nganh_filter, freq_filter)


def _int(x, d=0):
    try:
        return int(float(x))
    except (ValueError, TypeError):
        return d


def to_long_rows(agg):
    rows = []
    for (freq, sc, ro, metric, period), rec in agg.items():
        rows.append({
            "freq": freq, "statement_code": sc, "statement_name": rec[4],
            "row_order": rec[2], "parent": rec[7], "metric": metric,
            "period": period, "year": rec[5], "quarter": rec[6],
            "n_cong_ty": rec[1], "tong_gia_tri": round(rec[0], 6),
        })
    # Thứ tự giống báo cáo gốc: tần suất -> báo cáo (BS,IS,CF,NOTE) -> dòng chỉ tiêu
    # -> kỳ theo THỜI GIAN (năm, quý), không sort chuỗi (tránh Q3/2012 > Q1/2013).
    rows.sort(key=lambda d: (
        d["freq"],
        STMT_ORDER.index(d["statement_code"]) if d["statement_code"] in STMT_ORDER else 9,
        _int(d["row_order"]), d["metric"],
        _int(d["year"]), _int(d["quarter"]),
    ))
    return rows


def order_periods(cols):
    def key(c):
        c = str(c)
        if "/" in c and c[:1].upper() == "Q":
            q, y = c[1:].split("/")
            return (int(y), int(q))
        try:
            return (int(c), 0)
        except ValueError:
            return (9999, 0)
    return sorted(cols, key=key)


def _build_wide(rows, freq, value_field):
    """Bảng wide (chỉ tiêu × kỳ) gộp mọi báo cáo, giữ đúng thứ tự gốc.

    Cột: statement_code, row_order, parent, Chỉ tiêu, <các kỳ theo thời gian>.
    """
    df = pd.DataFrame([d for d in rows if d["freq"] == freq])
    if df.empty:
        return None
    df["row_order"] = pd.to_numeric(df["row_order"], errors="coerce")
    if "parent" not in df.columns:
        df["parent"] = ""
    df["parent"] = df["parent"].fillna("")
    pieces, all_periods = [], set()
    for sc in [s for s in STMT_ORDER if s in set(df["statement_code"])]:
        sub = df[df["statement_code"] == sc]
        cols = order_periods(sub["period"].unique())
        all_periods.update(cols)
        # (row_order, parent, metric) -> không gộp nhầm chỉ tiêu trùng tên
        p = (sub.pivot_table(index=["row_order", "parent", "metric"], columns="period",
                             values=value_field, aggfunc="sum")
                .reindex(columns=cols).sort_index(level="row_order").reset_index())
        p.insert(0, "statement_code", sc)
        pieces.append(p)
    out = pd.concat(pieces, ignore_index=True)
    period_order = order_periods(all_periods)
    out = out.reindex(columns=["statement_code", "row_order", "parent", "metric"] + period_order)
    return out.rename(columns={"metric": "Chỉ tiêu", "parent": "Chỉ tiêu cha"})


def write_wide_csv(rows, freq, outdir):
    """Xuất CSV wide: industry_FS_<freq>.csv (tổng) + industry_SoCty_<freq>.csv (số cty)."""
    made = []
    val = _build_wide(rows, freq, "tong_gia_tri")
    if val is None:
        return made
    suffix = freq or "QY"
    p1 = os.path.join(outdir, f"industry_FS_{suffix}.csv")
    val.to_csv(p1, index=False, encoding="utf-8-sig", na_rep="")
    made.append(p1)
    cnt = _build_wide(rows, freq, "n_cong_ty")
    p2 = os.path.join(outdir, f"industry_SoCty_{suffix}.csv")
    cnt.to_csv(p2, index=False, encoding="utf-8-sig", na_rep="")
    made.append(p2)
    return made


def main():
    ap = argparse.ArgumentParser(description="Gộp các công ty thành 1 FS toàn ngành (Σ).")
    ap.add_argument("--src", default=DEFAULT_SRC, help="File long nguồn")
    ap.add_argument("--nganh", default="", help="Lọc theo nganh_L2 (vd 'Dịch vụ tài chính')")
    ap.add_argument("--freq", default="", choices=["", "Q", "Y"], help="Lọc tần suất (mặc định cả hai)")
    ap.add_argument("--outdir", default=os.path.join(HERE, "output", "industry"))
    args = ap.parse_args()

    if not os.path.isfile(args.src):
        raise SystemExit("Không thấy file nguồn: " + args.src)
    os.makedirs(args.outdir, exist_ok=True)

    print("Đang gộp ...", flush=True)
    agg, n_rows, n_tickers = aggregate(args.src, args.nganh, args.freq)
    rows = to_long_rows(agg)

    long_path = os.path.join(args.outdir, "industry_fs_long.csv")
    with open(long_path, "w", encoding="utf-8-sig", newline="") as fh:
        cols = ["freq", "statement_code", "statement_name", "row_order", "parent", "metric",
                "period", "year", "quarter", "n_cong_ty", "tong_gia_tri"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    made = []
    for fq in (["Q", "Y"] if not args.freq else [args.freq]):
        made += write_wide_csv(rows, fq, args.outdir)

    cov = [d["n_cong_ty"] for d in rows]
    print(f"Gộp {n_tickers} mã, {n_rows:,} quan sát -> {len(rows):,} dòng ngành")
    if cov:
        print(f"  độ phủ/ô: tối đa {max(cov)} cty, trung bình {sum(cov)/len(cov):.1f}")
    print("  long :", long_path)
    for p in made:
        print("  wide :", p)


if __name__ == "__main__":
    main()
