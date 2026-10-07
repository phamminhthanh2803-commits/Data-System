# -*- coding: utf-8 -*-
"""Dung DUONG CONG LOI SUAT TPDN theo NGANH tai nhieu moc thoi gian de xem dich
chuyen: as-of (ngay GD cuoi), 1 thang, 3 thang, 6 thang, 12 thang truoc.

Input : data/processed/bond_yields.csv (bond_yields.py), tpcp_curve.csv
Output: data/processed/yield_curve.csv        long, pivot-ready
            as_of, moc (0M/1M/3M/6M/12M), ngay_moc, nganh, ky_han (bucket), ky_han_tb,
            n_bond, n_bond_truoc_cat, n_gd, gt_ty, gia_tri_lo_ty,
            ytm = BQ GIA QUYEN theo GIA TRI LO dang luu hanh, sau khi cat diem phan tan (IQR),
            ytm_wavg_raw (chua cat), ytm_wavg_gtgd (trong so GTGD), ytm_median, ytm_min/max,
            spread_bps (gia quyen), tpcp_spot
        data/processed/yield_curve_wide.csv   nganh x bucket, cot = moc (ytm) + thay doi bps
        data/processed/yield_curve_fit.csv    noi suy (log ky han) giua cac bucket tai ky han
            chuan 0.5/1/2/3/5/7/10 nam — chi trong khoang ky han co quan sat
        output/yield_curves/<as_of>_<nganh>.png + _tat_ca.png (small multiples)

Cach dung: moi moc lay cac giao dich trong WINDOW ngay truoc moc (mac dinh 30),
moi bond giu giao dich GAN NHAT, trong so = GIA TRI LO dang luu hanh (fallback gia
tri phat hanh, roi GTGD). Trong moi bucket cat diem ngoai [Q1-1.5IQR, Q3+1.5IQR]
(khi >= 5 bond) de giam nhieu phan tan truoc khi tinh binh quan. Loai outlier,
ttm < 0.1 nam, va (mac dinh) chi dung do_tin_cay cao + kha (--tin-cay cao de
chi lay bond lai suat co dinh).

Ham compute_curves() dung chung cho app Streamlit (D:/market-data/app/datalib.py).

Usage: python scripts/yield_curve.py [--as-of YYYY-MM-DD] [--window 30]
                                     [--tin-cay cao|kha|thap] [--min-bond 3] [--no-chart]
"""
import argparse
import calendar
import os
import sys
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

YIELDS = "data/processed/bond_yields.csv"
TPCP = "data/processed/tpcp_curve.csv"
OUT_LONG = "data/processed/yield_curve.csv"
OUT_WIDE = "data/processed/yield_curve_wide.csv"
OUT_FIT = "data/processed/yield_curve_fit.csv"
CHART_DIR = "output/yield_curves"

MOC = [("0M", 0), ("1M", 1), ("3M", 3), ("6M", 6), ("12M", 12)]
BUCKETS = [(0.1, 0.5, "0.1-0.5N"), (0.5, 1, "0.5-1N"), (1, 2, "1-2N"), (2, 3, "2-3N"),
           (3, 5, "3-5N"), (5, 7, "5-7N"), (7, 10, "7-10N"), (10, 99, ">10N")]
BUCKET_ORDER = [lab for _, _, lab in BUCKETS]
FIT_TENORS = [0.5, 1, 2, 3, 5, 7, 10]
TIN_CAY_RANK = {"cao": 0, "kha": 1, "thap": 2}
TOAN_TT = "Toàn thị trường"
TRU_NH = "Toàn TT trừ Ngân hàng"
# ramp 1 mau (ordinal: cu -> moi = nhat -> dam), theo dataviz palette
RAMP = {"12M": "#86b6ef", "6M": "#5598e7", "3M": "#2a78d6", "1M": "#1c5cab", "0M": "#0d366b"}


def months_back(d, k):
    m = d.month - 1 - k
    y = d.year + m // 12
    m = m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


def bucket_of(ttm):
    for lo, hi, lab in BUCKETS:
        if lo <= ttm < hi:
            return lab
    return ""


def trim_iqr(b, k=1.5, min_n=5):
    """Cat diem ngoai [Q1 - k*IQR, Q3 + k*IQR] trong bucket (chi khi >= min_n bond)."""
    if len(b) < min_n:
        return b
    q1, q3 = b.ytm.quantile(0.25), b.ytm.quantile(0.75)
    iqr = q3 - q1
    t = b[(b.ytm >= q1 - k * iqr) & (b.ytm <= q3 + k * iqr)]
    return t if len(t) >= 2 else b


def tpcp_curve_on(tp, d):
    """(ky_han_nam[], spot[], ngay) cua duong cong TPCP tai ngay d hoac ngay gan nhat truoc."""
    if tp is None or tp.empty:
        return None
    days = sorted(x for x in tp.ngay.unique() if x <= d.isoformat())
    if not days:
        return None
    g = tp[tp.ngay == days[-1]].sort_values("ky_han_nam")
    return g.ky_han_nam.values.astype(float), g.spot_nam.values.astype(float), days[-1]


def prepare_yields(y, tin_cay="kha"):
    """Loc bond_yields: co YTM, khong outlier, du tin cay, ttm >= 0.1; them cot d, w_lo."""
    y = y[y.ytm.notna() & ~y.ghi_chu.fillna("").astype(str).str.contains("outlier")]
    y = y[y.do_tin_cay_ytm.map(TIN_CAY_RANK).fillna(9) <= TIN_CAY_RANK[tin_cay]]
    y = y[y.ttm_nam >= 0.1].copy()
    y["d"] = pd.to_datetime(y.ngay)
    y["nganh"] = y.nganh.fillna("Chưa phân loại")
    y["w_lo"] = pd.to_numeric(y.get("gia_tri_luu_hanh_ty"), errors="coerce")
    y["w_lo"] = y.w_lo.where(y.w_lo > 0, pd.to_numeric(y.get("gia_tri_ph_ty"), errors="coerce"))
    y["w_lo"] = y.w_lo.where(y.w_lo > 0, y.gt_ty).fillna(y.gt_ty).clip(lower=1e-3)
    return y


def compute_curves(y, as_of, window=30, min_bond=3, tp=None, moc=MOC):
    """y: bond_yields da qua prepare_yields(). Tra ve (long_df, fit_df, charts)
    charts[nganh][moc] = (bond_df trong cua so, tpcp tuple, ngay_moc)."""
    rows, fits, charts = [], [], {}
    for lab, k in moc:
        d_moc = months_back(as_of, k)
        d0 = d_moc - timedelta(days=window)
        w = y[(y.d > pd.Timestamp(d0)) & (y.d <= pd.Timestamp(d_moc))]
        n_gd = w.groupby("ma_gd").size()
        w = w.sort_values("d").groupby("ma_gd").tail(1).copy()
        w["n_gd"] = w.ma_gd.map(n_gd)
        w["bucket"] = w.ttm_nam.map(bucket_of)
        w = w[w.bucket != ""]
        if w.empty:
            continue
        tpc = tpcp_curve_on(tp, d_moc)
        groups = [(TOAN_TT, w), (TRU_NH, w[w.nganh != "Ngân hàng"])] + \
                 [(n, g) for n, g in w.groupby("nganh")]
        for nganh, g in groups:
            if g.ma_gd.nunique() < min_bond:
                continue
            pts = []
            for lo, hi, blab in BUCKETS:
                b = g[g.bucket == blab]
                if len(b) < min_bond:
                    continue
                bt = trim_iqr(b)
                ttm_tb = float(np.average(bt.ttm_nam, weights=bt.w_lo))
                sp = bt[bt.spread_bps.notna()]
                ytm = float(np.average(bt.ytm, weights=bt.w_lo))
                rows.append({
                    "as_of": as_of.isoformat(), "moc": lab, "ngay_moc": d_moc.isoformat(),
                    "nganh": nganh, "ky_han": blab, "ky_han_tb": round(ttm_tb, 2),
                    "n_bond": int(bt.ma_gd.nunique()), "n_bond_truoc_cat": int(b.ma_gd.nunique()),
                    "n_gd": int(bt.n_gd.sum()),
                    "gt_ty": round(float(bt.gt_ty.sum()), 1), "gia_tri_lo_ty": round(float(bt.w_lo.sum()), 1),
                    "ytm": round(ytm, 3),
                    "ytm_wavg_raw": round(float(np.average(b.ytm, weights=b.w_lo)), 3),
                    "ytm_wavg_gtgd": round(float(np.average(bt.ytm, weights=bt.gt_ty)), 3),
                    "ytm_median": round(float(bt.ytm.median()), 3),
                    "ytm_min": round(float(bt.ytm.min()), 3), "ytm_max": round(float(bt.ytm.max()), 3),
                    "spread_bps": round(float(np.average(sp.spread_bps, weights=sp.w_lo)), 0) if len(sp) else np.nan,
                    "tpcp_spot": round(float(np.interp(ttm_tb, tpc[0], tpc[1])), 3) if tpc else np.nan,
                })
                pts.append((ttm_tb, ytm))
            # ky han chuan = noi suy (log ky han) giua cac bucket — khong ngoai suy
            if len(pts) >= 2:
                pts.sort()
                xs, ys = np.log([p[0] for p in pts]), [p[1] for p in pts]
                for t in FIT_TENORS:
                    if pts[0][0] <= t <= pts[-1][0]:
                        fits.append({"as_of": as_of.isoformat(), "moc": lab, "ngay_moc": d_moc.isoformat(),
                                     "nganh": nganh, "ky_han_nam": t,
                                     "ytm_fit": round(float(np.interp(np.log(t), xs, ys)), 3),
                                     "tpcp_spot": round(float(np.interp(t, tpc[0], tpc[1])), 3) if tpc else np.nan,
                                     "n_bond": int(g.ma_gd.nunique())})
            charts.setdefault(nganh, {})[lab] = (g, tpc, d_moc)
    return pd.DataFrame(rows), pd.DataFrame(fits), charts


def wide_table(long, moc=MOC):
    wide = long.pivot_table(index=["nganh", "ky_han"], columns="moc", values="ytm", aggfunc="first")
    cols = [m for m, _ in moc]
    wide = wide.reindex(columns=cols)
    base = cols[0]
    for m in cols[1:]:
        wide["thay_doi_%s_bps" % m] = ((wide[base] - wide[m]) * 100).round(0)
    nb = long[long.moc == base].set_index(["nganh", "ky_han"]).n_bond
    wide["n_bond_%s" % base] = nb
    wide = wide.reset_index()
    wide["_o"] = wide.ky_han.map({l: i for i, l in enumerate(BUCKET_ORDER)})
    wide["_n"] = wide.nganh.map(lambda n: 0 if n == TOAN_TT else 1 if n == TRU_NH else 2)
    return wide.sort_values(["_n", "nganh", "_o"]).drop(columns=["_o", "_n"])


def load_tpcp(path=TPCP):
    if not os.path.exists(path):
        return None
    c = pd.read_csv(path)
    return c[c.spot_nam.notna()]


def main():
    from hnx_common import write_file_safe
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", dest="as_of")
    ap.add_argument("--window", type=int, default=30)
    ap.add_argument("--tin-cay", default="kha", choices=list(TIN_CAY_RANK))
    ap.add_argument("--min-bond", type=int, default=3)
    ap.add_argument("--no-chart", action="store_true")
    a = ap.parse_args()

    y = prepare_yields(pd.read_csv(YIELDS, low_memory=False), a.tin_cay)
    tp = load_tpcp()
    last = y.d.max().date()
    as_of = datetime.strptime(a.as_of, "%Y-%m-%d").date() if a.as_of else last
    long, fits, charts = compute_curves(y, as_of, a.window, a.min_bond, tp)
    if long.empty:
        print("khong du du lieu")
        sys.exit(1)
    for lab, _ in MOC:
        sub = long[long.moc == lab]
        if len(sub):
            print("moc %s (%s): %d nganh" % (lab, sub.ngay_moc.iloc[0], sub.nganh.nunique()))
    write_file_safe(OUT_LONG, lambda f: long.to_csv(f, index=False))
    wide = wide_table(long)
    write_file_safe(OUT_WIDE, lambda f: wide.to_csv(f, index=False))
    if len(fits):
        write_file_safe(OUT_FIT, lambda f: fits.to_csv(f, index=False))
    print("yield_curve: %d dong long, %d dong wide, %d diem fit -> %s" % (len(long), len(wide), len(fits), OUT_LONG))
    if not a.no_chart:
        draw(charts, as_of, long)


def draw(charts, as_of, long):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(CHART_DIR, exist_ok=True)
    order = [TOAN_TT, TRU_NH] + sorted(n for n in charts if n not in (TOAN_TT, TRU_NH))
    xt = [0.25, 0.5, 1, 2, 3, 5, 7, 10, 15]

    def one(ax, nganh):
        tpc_drawn = False
        for moc, _ in MOC:
            if moc not in charts[nganh]:
                continue
            g, tpc, d_moc = charts[nganh][moc]
            sub = long[(long.nganh == nganh) & (long.moc == moc)].sort_values("ky_han_tb")
            ax.scatter(g.ttm_nam, g.ytm, s=np.clip(g.w_lo / 50, 2, 60) + 8, color=RAMP[moc], alpha=0.25, lw=0)
            if len(sub):
                ax.plot(sub.ky_han_tb, sub.ytm, "-o", color=RAMP[moc], lw=2, ms=4,
                        label="%s (%s, %d bond)" % (moc if moc != "0M" else "Hiện tại", d_moc.strftime("%d/%m/%y"), g.ma_gd.nunique()))
            if moc == "0M" and tpc and not tpc_drawn:
                ax.plot(tpc[0], tpc[1], "--", color="#8a8984", lw=1.5, label="TPCP spot (%s)" % tpc[2][5:])
                tpc_drawn = True
        ax.set_xscale("log")
        ax.set_xticks(xt); ax.set_xticklabels([("%g" % x) for x in xt])
        ax.set_xlim(0.1, 20)
        ys = long[long.nganh == nganh].ytm
        if len(ys):
            ax.set_ylim(max(0, ys.min() - 3), ys.max() + 3)   # cat outlier de doc duoc duong cong
        ax.set_xlabel("Kỳ hạn còn lại (năm)"); ax.set_ylabel("YTM (%/năm)")
        ax.grid(True, color="#e8e8e8", lw=0.6); ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.set_title(nganh, loc="left", fontsize=11, fontweight="bold")

    for nganh in order:
        fig, ax = plt.subplots(figsize=(9, 5.5))
        one(ax, nganh)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=8, frameon=False)
        fig.suptitle("Đường cong lợi suất TPDN riêng lẻ — %s (as-of %s; chấm = bond, kích thước ~ giá trị lô; "
                     "đường = BQ gia quyền giá trị lô theo bucket, đã cắt IQR)"
                     % (nganh, as_of.strftime("%d/%m/%Y")), fontsize=9, x=0.01, ha="left")
        fig.tight_layout()
        fn = os.path.join(CHART_DIR, "%s_%s.png" % (as_of.isoformat(), "".join(c for c in nganh if c.isalnum())))
        fig.savefig(fn, dpi=130); plt.close(fig)
    n = len(order)
    cols = 3
    rws = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rws, cols, figsize=(6 * cols, 4 * rws), squeeze=False)
    for i, nganh in enumerate(order):
        one(axes[i // cols][i % cols], nganh)
    for j in range(n, rws * cols):
        axes[j // cols][j % cols].axis("off")
    h, l = axes[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower right", fontsize=9, frameon=False, ncol=3)
    fig.suptitle("Đường cong lợi suất TPDN riêng lẻ theo ngành — as-of %s (nhạt → đậm = 12M → hiện tại)" % as_of.strftime("%d/%m/%Y"),
                 fontsize=13, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.03, 1, 0.97))
    fig.savefig(os.path.join(CHART_DIR, "%s_tat_ca.png" % as_of.isoformat()), dpi=110)
    plt.close(fig)
    print("charts -> %s" % CHART_DIR)


if __name__ == "__main__":
    main()
