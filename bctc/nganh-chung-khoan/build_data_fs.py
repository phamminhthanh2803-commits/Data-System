# -*- coding: utf-8 -*-
r"""build_data_fs.py - 2 file nguon cho 2 sheet DATA trung gian cua IB&Brokerage_Nganh.xlsx (16/09/2026).

  excel_feed\data_fs.csv    -> sheet Data_FS (bang tbl_FS): TOAN BO item 3 bao cao (BS / IS / CF / NOTE) cua 87 CTCK + dong ALL (tong nganh),
                               theo QUY tu --from-year (mac dinh 2012), dang RONG: key = ticker|stmt|row_order ; cot key, ticker, stmt, row_order,
                               label, Q1-2012 ... Q2-2026 (nhan ky nhu Key ratios). Bo dong toan 0/trong (giu ~38k / 80k dong). Ty VND.
  excel_feed\data_dm_ma.csv -> sheet Data_DM (bang tbl_Ma): ticker, ten, nhom quy mo, VCSH ky gan nhat -> dropdown ma.
Nguon: nganh_chung_khoan.sqlite (bang fact_fs do build_nganh_ck.py dung tu fiinprox_facts_all.csv).
Chay: python build_data_fs.py [--from-year 2012]      (run_pipeline.py goi truoc build_workbook_logic.py)
"""
import argparse, os, sqlite3, sys, time
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "nganh_chung_khoan.sqlite")
FEED = os.path.join(HERE, "excel_feed")
STMT_ORDER = {"BS": 0, "IS": 1, "CF": 2, "NOTE": 3, "DER": 4}


def log(m):
    print(m, flush=True)


def _interest_in_row30(q, isq, periods):
    """DER|2: phan LAI VAY nam trong IS 30 ("CP du phong TSTC ... va CP di vay") - 17/09/2026.
    IS 51 va IS 30 KHONG trung nhau (CF 9 'Chi phi lai vay' = IS 51 o nhom SSI, = IS 30 o nhom HCM/ACBS, ~ tong o DSE/KISVN) nhung IS 30 con chua
    du phong (VDS 294 ty ma tien lai tra 51; MASC 843 vs CF 606). Trong tai = CF: ty le lai vay trong IS 30 = (max(|CF9|,|CF54|) - |IS51|) / |IS30|
    tren 4 quy truot (kep [0,1]); khong co CF -> nguong lai suat: IS51 x4/no < 2% va IS30 x4/no trong [2%, 15%] -> ca dong 30 la lai vay."""
    import numpy as np
    cfq = q[q.stmt == "CF"].pivot_table(index=["ticker", "per"], columns="row_order", values="value", aggfunc="first")
    bsq = q[q.stmt == "BS"].pivot_table(index=["ticker", "per"], columns="row_order", values="value", aggfunc="first")
    col = lambda df, c: (df[c] if c in df.columns else df.iloc[:, 0] * 0).fillna(0)
    f = pd.DataFrame({"is51": -col(isq, 51), "is30": (-col(isq, 30)).clip(lower=0), "cf": np.maximum(col(cfq, 9).abs().reindex(isq.index).fillna(0), col(cfq, 54).abs().reindex(isq.index).fillna(0)),
                      "debt": sum(col(bsq, r) for r in (95, 99, 100, 122, 126, 127)).reindex(isq.index).fillna(0)})
    f = f.reset_index(); f["per"] = pd.Categorical(f.per, categories=periods, ordered=True); f = f.sort_values(["ticker", "per"])
    roll = f.groupby("ticker")[["is51", "is30", "cf"]].transform(lambda s: s.rolling(4, min_periods=2).sum())
    share = ((roll.cf - roll.is51) / roll.is30.replace(0, np.nan)).clip(0, 1)
    thr = ((4 * f.is51 / f.debt.replace(0, np.nan)) < 0.02) & ((4 * f.is30 / f.debt.replace(0, np.nan)).between(0.02, 0.15))
    share = share.where(roll.cf > 0, thr.astype(float)).fillna(0)
    out = pd.Series((-(f.is30 * share)).values, index=pd.MultiIndex.from_arrays([f.ticker.values, f.per.astype(str).values], names=["ticker", "per"]))
    return out.reindex(isq.index).fillna(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-year", type=int, default=2012)
    a = ap.parse_args()
    t0 = time.time()
    con = sqlite3.connect(DB)
    q = pd.read_sql("SELECT ticker, statement_code AS stmt, row_order, metric, year, quarter, value FROM fact_fs "
                    "WHERE freq='Q' AND year>=? AND quarter IS NOT NULL AND value IS NOT NULL", con, params=(a.from_year,))
    q["quarter"] = q.quarter.astype(int); q["row_order"] = q.row_order.astype(int)
    q["per"] = "Q" + q.quarter.astype(str) + "-" + q.year.astype(str)
    periods = [f"Q{qq}-{yy}" for yy, qq in sorted(set(zip(q.year, q.quarter)))]
    # ---- dong DAN XUAT (stmt = DER) cho CIR chuan bank (17/09/2026): DER|1 = tong chi phi nghiep vu IS 32-39 ;
    #      DER|2 = IS 30 (du phong & chi phi di vay) CHI KHI cong ty khong co IS 51 cung ky (= lai vay ghi o dong 30, vd HCM)
    isq = q[q.stmt == "IS"].pivot_table(index=["ticker", "per"], columns="row_order", values="value", aggfunc="first")
    svc = isq.reindex(columns=range(32, 40)).fillna(0).sum(axis=1)
    int30 = _interest_in_row30(q, isq, periods)
    der = []
    for ro, lab, ser in ((1, "Chi phí nghiệp vụ (Σ IS 32–39: tự doanh, môi giới, bảo lãnh, tư vấn, lưu ký, TVTC, khác)", svc),
                         (2, "Lãi vay ghi ở IS 30 (phần có CF 9 / CF 54 chứng minh, 4 quý trượt; không có CF: ngưỡng lãi suất)", int30)):
        s = ser[ser != 0].reset_index(); s.columns = ["ticker", "per", "value"]
        s["stmt"] = "DER"; s["row_order"] = ro; s["metric"] = lab
        s["year"] = s.per.str[-4:].astype(int); s["quarter"] = s.per.str[1].astype(int); der.append(s)
    q = pd.concat([q] + der, ignore_index=True)
    label = q.groupby(["stmt", "row_order"]).metric.agg(lambda s: s.value_counts().index[0])
    w = q.pivot_table(index=["ticker", "stmt", "row_order"], columns="per", values="value", aggfunc="first").reindex(columns=periods)
    allw = q.groupby(["stmt", "row_order", "per"]).value.sum(min_count=1).unstack("per").reindex(columns=periods)
    allw.index = pd.MultiIndex.from_tuples([("ALL", s, r) for s, r in allw.index], names=w.index.names)
    w = pd.concat([allw, w])
    n_all = len(w)
    w = w[(w.fillna(0) != 0).any(axis=1)].reset_index()
    w.insert(0, "key", w.ticker + "|" + w.stmt + "|" + w.row_order.astype(str))
    w.insert(4, "label", [label.get((s, r), "") for s, r in zip(w.stmt, w.row_order)])
    w["_t"] = (w.ticker != "ALL").astype(int); w["_s"] = w.stmt.map(STMT_ORDER)
    w = w.sort_values(["_t", "ticker", "_s", "row_order"]).drop(columns=["_t", "_s"])
    os.makedirs(FEED, exist_ok=True)
    w.to_csv(os.path.join(FEED, "data_fs.csv"), index=False, encoding="utf-8-sig", float_format="%.6f")
    log(f"  data_fs.csv: {len(w):,} dong (bo {n_all - len(w):,} dong toan 0) x {len(periods)} quy ({periods[0]} -> {periods[-1]}), "
        f"{w.ticker.nunique() - 1} ma + ALL [{time.time() - t0:.0f}s]")
    dm = pd.read_csv(os.path.join(HERE, "dim_company.csv"), encoding="utf-8-sig")
    dm = dm[["ticker", "ten_cong_ty", "nhom_quy_mo", "vcsh_ky_gan_nhat_ty", "ky_gan_nhat"]].sort_values("ticker")
    dm.to_csv(os.path.join(FEED, "data_dm_ma.csv"), index=False, encoding="utf-8-sig")
    log(f"  data_dm_ma.csv: {len(dm)} ma")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
