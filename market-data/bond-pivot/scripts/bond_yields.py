# -*- coding: utf-8 -*-
"""Tinh LOI SUAT DAO HAN (YTM) cho tung giao dich trai phieu rieng le + spread so
voi TPCP, ghep nganh/he sinh thai tu fact table.

Input : data/processed/bond_prices.csv      (pull_prices.py)
        data/processed/bond_detail.csv      (ma_gd <-> ma_tp)
        data/processed/bond_master.csv      (menh gia, coupon, ky tra lai, dao han)
        data/processed/ttph.csv             (loai lai suat: co dinh / tha noi / ket hop)
        data/processed/market_issuance_timeline.csv (nganh, parent_group)
        data/processed/tpcp_curve.csv       (benchmark, pull_tpcp_curve.py)
Output: data/processed/bond_yields.csv      (1 dong = 1 ma x 1 ngay co giao dich)

Mo hinh dong tien (gia tren san = GIA THANH TOAN = gia gop/dirty):
  * dinh ky (Dinh ky - Cuoi ky / Dau ky / Khac co ky tra lai): coupon = menh_gia x
    lai_suat x (thang_ky/12) tai cac moc lui tu ngay dao han; goc tra cuoi.
  * mot lan khi den han / ky tra lai >= ky han: 1 dong tien = menh_gia x
    (1 + lai_suat x so_nam_tu_phat_hanh)  (lai don, khong nhap goc).
  * zero coupon (lai_suat = 0): 1 dong tien = menh_gia.
  YTM = lai suat hieu dung nam (annual effective, ACT/365) giai bang bisection.
  Bond tha noi / ket hop: HNX chi cong bo lai suat PHAT HANH (ky dau) -> coupon
  proxy -> do_tin_cay_ytm = kha. Mot lan khi den han / Khac -> thap.
  Outlier (ytm < 0 hoac > 40%, gia < 50% hoac > 250% menh gia) giu lai nhung
  ghi_chu = outlier -> yield_curve.py loai khi dung duong cong.
"""
import csv
import os
import re
import sys
from datetime import date, datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hnx_common import write_file_safe

PRICES = "data/processed/bond_prices.csv"
DETAIL = "data/processed/bond_detail.csv"
MASTER = "data/processed/bond_master.csv"
TTPH = "data/processed/ttph.csv"
TIMELINE = "data/processed/market_issuance_timeline.csv"
TPCP = "data/processed/tpcp_curve.csv"
OUT = "data/processed/bond_yields.csv"

FIELDS = ["ngay", "ma_gd", "ma_tp", "to_chuc_phat_hanh", "parent_group", "nganh",
          "nganh_chi_tiet", "ma_ck", "gia_tri_luu_hanh_ty", "gia_tri_ph_ty",
          "loai_lai_suat", "phuong_thuc_tra_lai",
          "ky_tra_lai_thang", "lai_suat", "ngay_phat_hanh", "ngay_dao_han", "ttm_nam",
          "menh_gia", "kl", "gt_ty", "gia_bq_pct", "gia_cuoi_pct", "ytm", "ytm_gia_cuoi",
          "tpcp_spot", "spread_bps", "mo_hinh_cf", "do_tin_cay_ytm", "ghi_chu"]

YTM_LO, YTM_HI = -0.5, 2.0          # khoang tim nghiem (-50% .. +200%)
OUT_YTM_LO, OUT_YTM_HI = 0.0, 40.0  # ngoai khoang -> outlier
OUT_P_LO, OUT_P_HI = 50.0, 250.0


def parse_months(s):
    """'3 Tháng' -> 3, '1 Năm' -> 12, '' -> None."""
    if not isinstance(s, str):
        return None
    m = re.match(r"\s*(\d+)\s*(Th[áa]ng|N[ăa]m|Ng[àa]y)", s, re.I)
    if not m:
        return None
    n, u = int(m.group(1)), m.group(2).lower()
    if u.startswith("ng"):
        return max(1, round(n / 30))
    return n if u.startswith("th") else n * 12


def to_date(s):
    if not isinstance(s, str) or not s:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            pass
    return None


def add_months(d, k):
    """d + k thang (giu ngay, lui ve cuoi thang neu can)."""
    m = d.month - 1 + k
    y = d.year + m // 12
    m = m % 12 + 1
    import calendar
    day = min(d.day, calendar.monthrange(y, m)[1])
    return date(y, m, day)


def schedule(issue, maturity, months):
    """Cac moc tra lai lui tu dao han ve sau ngay phat hanh (tang dan)."""
    out, k = [], 0
    while True:
        d = add_months(maturity, -k * months)
        if issue and d <= issue:
            break
        out.append(d)
        k += 1
        if k > 600:
            break
    return sorted(out)


def build_cf(issue, maturity, par, coupon, months, pttl):
    """-> (dates list, amounts ndarray, mo_hinh, tin_cay_base)."""
    yrs_total = (maturity - issue).days / 365.0 if issue else None
    single = (pttl or "").startswith("Một lần") or months is None or \
        (yrs_total and months >= yrs_total * 12 - 0.5)
    if coupon <= 0:
        return [maturity], np.array([par], float), "zero_coupon", "cao"
    if single:
        if not yrs_total:
            return [maturity], np.array([par], float), "khong_xd", "thap"
        return [maturity], np.array([par * (1 + coupon / 100 * yrs_total)], float), "lai_don_den_han", "thap"
    ds = schedule(issue, maturity, months)
    cf = np.full(len(ds), par * coupon / 100 * months / 12.0)
    cf[-1] += par
    return ds, cf, "dinh_ky_%dm" % months, "cao"


def solve_ytm(price, t_years, cf):
    """price = sum cf/(1+y)^t  -> y (annual effective) bang bisection."""
    def f(y):
        return float(np.sum(cf / np.power(1.0 + y, t_years))) - price
    lo, hi = YTM_LO, YTM_HI
    flo, fhi = f(lo), f(hi)
    if np.isnan(flo) or np.isnan(fhi) or flo * fhi > 0:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2
        fm = f(mid)
        if flo * fm <= 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def load_tpcp():
    if not os.path.exists(TPCP):
        return None
    c = pd.read_csv(TPCP)
    c = c[c.spot_nam.notna()]
    curves = {}
    for d, g in c.groupby("ngay"):
        g = g.sort_values("ky_han_nam")
        curves[d] = (g.ky_han_nam.values.astype(float), g.spot_nam.values.astype(float))
    return curves


def tpcp_at(curves, ngay, ttm, _cache={}):
    """Spot TPCP tai ngay (hoac ngay gan nhat truoc do), noi suy theo ttm."""
    if not curves:
        return None
    if ngay not in _cache:
        keys = sorted(curves)
        import bisect
        i = bisect.bisect_right(keys, ngay) - 1
        _cache[ngay] = keys[i] if i >= 0 else None
    k = _cache[ngay]
    if k is None:
        return None
    x, y = curves[k]
    return float(np.interp(ttm, x, y))


def main():
    if not os.path.exists(PRICES):
        print("chua co", PRICES)
        sys.exit(1)
    px = pd.read_csv(PRICES, dtype={"ma_gd": str})
    det = pd.read_csv(DETAIL, dtype=str).fillna("")
    det = det[det.ma_tp_giao_dich != ""]
    gd2tp = dict(zip(det.ma_tp_giao_dich.str.upper(), det.ma_tp.str.upper()))
    master = pd.read_csv(MASTER, dtype=str).fillna("")
    master["ma_tp"] = master.ma_tp.str.upper()
    mset = set(master.ma_tp)
    m_by = master.set_index("ma_tp").to_dict("index")
    tt = pd.read_csv(TTPH, dtype=str).fillna("").drop_duplicates("ma_tp")
    lls = dict(zip(tt.ma_tp.str.upper(), tt.loai_lai_suat))
    tl = pd.read_csv(TIMELINE, dtype=str).fillna("").drop_duplicates("ma_tp")
    tl_by = tl.set_index(tl.ma_tp.str.upper())[["parent_group", "nganh", "nganh_chi_tiet", "ma_ck",
                                                 "gia_tri_luu_hanh_ty", "gia_tri_ty"]].to_dict("index")
    curves = load_tpcp()

    rows, stats = [], {"khong_noi": 0, "bo_qua": 0}
    cf_cache = {}
    for r in px.itertuples(index=False):
        gd = r.ma_gd.upper()
        tp = gd2tp.get(gd) or (gd if gd in mset else None)
        t = to_date(r.ngay)
        base = {"ngay": r.ngay, "ma_gd": gd, "ma_tp": tp or "", "kl": r.kl,
                "gt_ty": round(r.gt / 1e9, 3)}
        if not tp:
            stats["khong_noi"] += 1
            rows.append({**base, "nganh": "Chưa nối mã", "ghi_chu": "khong_noi_ma_tp", "do_tin_cay_ytm": ""})
            continue
        m = m_by[tp]
        info = tl_by.get(tp, {})
        par = float(m["menh_gia"].replace(",", "") or 0)
        coupon = float(m["lai_suat_phat_hanh"].replace(",", "") or 0)
        issue, mat = to_date(m["ngay_phat_hanh"]), to_date(m["ngay_dao_han"])
        months = parse_months(m["ky_han_tra_lai"])
        pttl = m["phuong_thuc_tra_lai"]
        loai_ls = lls.get(tp, "")
        base.update({"to_chuc_phat_hanh": m["to_chuc_phat_hanh"],
                     "parent_group": info.get("parent_group", ""),
                     "nganh": info.get("nganh", "Chưa phân loại"),
                     "nganh_chi_tiet": info.get("nganh_chi_tiet", ""), "ma_ck": info.get("ma_ck", ""),
                     "gia_tri_luu_hanh_ty": info.get("gia_tri_luu_hanh_ty", ""),
                     "gia_tri_ph_ty": info.get("gia_tri_ty", ""),
                     "loai_lai_suat": loai_ls, "phuong_thuc_tra_lai": pttl,
                     "ky_tra_lai_thang": months or "", "lai_suat": coupon,
                     "ngay_phat_hanh": issue.isoformat() if issue else "",
                     "ngay_dao_han": mat.isoformat() if mat else "", "menh_gia": int(par)})
        if not mat or not t or par <= 0 or m["tien_te"] not in ("", "VND", "VNĐ"):
            stats["bo_qua"] += 1
            rows.append({**base, "ghi_chu": "thieu_dao_han_hoac_ngoai_te", "do_tin_cay_ytm": ""})
            continue
        ttm = (mat - t).days / 365.0
        base["ttm_nam"] = round(ttm, 3)
        p_bq, p_cuoi = r.gia_bq / par * 100, r.gia_cuoi / par * 100
        base.update({"gia_bq_pct": round(p_bq, 3), "gia_cuoi_pct": round(p_cuoi, 3)})
        if ttm <= 0:
            rows.append({**base, "ghi_chu": "da_dao_han", "do_tin_cay_ytm": ""})
            continue
        if tp not in cf_cache:
            cf_cache[tp] = build_cf(issue, mat, 100.0, coupon, months, pttl)
        ds, cf, model, tin_cay = cf_cache[tp]
        keep = [i for i, d in enumerate(ds) if d > t]
        if not keep:
            rows.append({**base, "mo_hinh_cf": model, "ghi_chu": "het_dong_tien", "do_tin_cay_ytm": ""})
            continue
        tv = np.array([(ds[i] - t).days / 365.0 for i in keep])
        cfv = cf[keep]
        y = solve_ytm(p_bq, tv, cfv)
        y2 = solve_ytm(p_cuoi, tv, cfv) if abs(p_cuoi - p_bq) > 1e-9 else y
        if tin_cay == "cao" and (loai_ls in ("Thả nổi", "Kết hợp") or pttl.startswith("Định kỳ - Đầu")):
            tin_cay = "kha"
        if pttl == "Khác" and tin_cay == "cao":
            tin_cay = "kha"
        notes = []
        if y is None:
            notes.append("khong_giai_duoc")
        else:
            if not (OUT_YTM_LO <= y * 100 <= OUT_YTM_HI) or not (OUT_P_LO <= p_bq <= OUT_P_HI):
                notes.append("outlier")
        if loai_ls in ("Thả nổi", "Kết hợp"):
            notes.append("coupon_proxy_ky_dau")
        tp_spot = tpcp_at(curves, r.ngay, ttm)
        rows.append({**base, "ytm": round(y * 100, 4) if y is not None else "",
                     "ytm_gia_cuoi": round(y2 * 100, 4) if y2 is not None else "",
                     "tpcp_spot": round(tp_spot, 4) if tp_spot is not None else "",
                     "spread_bps": round((y * 100 - tp_spot) * 100, 1) if (y is not None and tp_spot is not None) else "",
                     "mo_hinh_cf": model, "do_tin_cay_ytm": tin_cay, "ghi_chu": ";".join(notes)})

    def _w(f):
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    if not write_file_safe(OUT, _w):
        sys.exit(2)
    ok = [r for r in rows if r.get("ytm") not in ("", None) and "outlier" not in r.get("ghi_chu", "")]
    tc = pd.Series([r["do_tin_cay_ytm"] for r in ok]).value_counts().to_dict()
    print("bond_yields: %d giao dich, %d co YTM dung duoc (%s), khong noi ma %d, bo qua %d -> %s" % (
        len(rows), len(ok), tc, stats["khong_noi"], stats["bo_qua"], OUT))


if __name__ == "__main__":
    main()
