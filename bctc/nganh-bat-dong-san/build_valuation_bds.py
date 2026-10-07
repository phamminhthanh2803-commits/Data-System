# -*- coding: utf-8 -*-
r"""build_valuation_bds.py — BƯỚC 2: ĐỊNH GIÁ NGÀNH BĐS theo ngày + DRIVERS thị trường theo quý.

Định giá (giống build_valuation_ck.py của ngành CK):
  vốn hoá = giá đóng cửa TradingView (đã điều chỉnh) × số CP HIỆN HÀNH (screener meta; thiếu thì vốn góp quý gần nhất / 10.000đ)
  LNST CĐ mẹ TTM = 4 quý liên tiếp (VCI); VCSH CĐ mẹ = VCSH − lợi ích CĐ không kiểm soát
  BCTC quý có hiệu lực từ cuối quý + LAG_DAYS (hợp nhất nộp trong 45 ngày)
  P/E nhóm = Σ vốn hoá / Σ LNST TTM (gồm công ty lỗ, như VNDirect); P/E ex-loss chỉ công ty lãi; P/B = Σ vốn hoá / Σ VCSH CĐ mẹ
  Nhóm = như data_fs (nhom_bds.csv, bỏ mã cong_vao_nganh = 0: VIC, DXS)
Drivers theo quý (giá trị từ các pipeline market-data):
  VN-Index cuối quý; P/E, P/B, vốn hoá ngành cuối quý; TPDN BĐS phát hành / đến hạn (HNX CBIS, bond-pivot);
  lãi suất cho vay BQ, huy động 12T, LNH qua đêm & 3T, tái cấp vốn, tín dụng YTD, M2 YoY (transmission-fetcher);
  khối ngoại mua/bán ròng nhóm BĐS (Vietcap IQ theo mã).
Ra: valuation_bds_stocks_daily.csv, valuation_bds_nhom_daily.csv, drivers_bds.csv (long), bond_maturity_bds.csv (+ bảng SQLite).
"""
import os
import sqlite3
import warnings

import numpy as np
import pandas as pd

from common_bds import (BONDS, FOREIGN_VCI, HERE, INDICES, META, NHOM_TONG, SQLITE, TM_WIDE, TV, log, qidx, qname,
                        utf8_stdout)
from build_nganh_bds import members

warnings.filterwarnings("ignore")
LAG_DAYS = 45
START = "2018-01-01"


def _fs_item(di, raw_long, bc, key):
    r = di[(di.bc == bc) & (di.key_item == key)].row_order
    if r.empty:
        return pd.DataFrame(columns=["ticker", "period", key])
    x = raw_long[(raw_long.bc == bc) & (raw_long.row_order == int(r.iloc[0]))]
    return x[["ticker", "period", "value"]].rename(columns={"value": key})


def fundamentals():
    di = pd.read_csv(os.path.join(HERE, "dim_item.csv"))
    raw = []
    for bc, f in (("IS", "income_statement"), ("BS", "balance_sheet")):
        d = pd.read_parquet(os.path.join(HERE, "raw", f + ".parquet"), columns=["ticker", "period", "row_order", "value"])
        raw.append(d.assign(bc=bc))
    raw = pd.concat(raw)
    raw["value"] = raw.value / 1e9
    w = _fs_item(di, raw, "IS", "attributable_to_parent_company")
    for k in ("owners_equity", "minority_interests", "minority_interests_before_2015", "paid_in_capital"):
        w = w.merge(_fs_item(di, raw, "BS", k), on=["ticker", "period"], how="outer")
    w["eq_parent"] = w.owners_equity - w.minority_interests.fillna(0) - w.minority_interests_before_2015.fillna(0)
    w["t"] = w.period.map(qidx)
    w = w.sort_values(["ticker", "t"])
    g = w.groupby("ticker")
    ok4 = g.t.shift(3) == w.t - 3
    w["npat_ttm"] = np.where(ok4 & w.attributable_to_parent_company.notna(),
                             g.attributable_to_parent_company.transform(lambda s: s.rolling(4, min_periods=4).sum()), np.nan)
    w["qend"] = [pd.Timestamp(int(p[:4]), int(p[-1]) * 3, 1) + pd.offsets.MonthEnd(0) for p in w.period]
    w["avail"] = w.qend + pd.Timedelta(days=LAG_DAYS)
    return w


def valuation(nh, w):
    tickers = [t for t in nh.ticker if isinstance(t, str) and len(t) == 3]
    tv = pd.read_csv(TV, dtype={"date": str}, usecols=["date", "symbol", "exchange", "close"])
    tv = tv[tv.symbol.isin(tickers) & tv.exchange.isin(["HOSE", "HNX", "UPCOM"]) & (tv.date >= START)]
    tv["date"] = pd.to_datetime(tv.date)
    px = tv.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index().ffill(limit=20)
    have = set(px.columns)
    log(f"  giá TradingView: {len(have)}/{len(tickers)} mã; thiếu: {sorted(set(tickers) - have)}")
    meta = pd.read_csv(META).drop_duplicates("name").set_index("name").total_shares_outstanding_fundamental
    last_cap = w.dropna(subset=["paid_in_capital"]).groupby("ticker").paid_in_capital.last() * 1e9 / 1e4
    sh = pd.Series({t: meta.get(t) if pd.notna(meta.get(t)) and meta.get(t) > 0 else last_cap.get(t) for t in have})

    daily = px.stack().rename("close").reset_index().rename(columns={"symbol": "ticker"}).sort_values("date")
    fund = (w[["ticker", "avail", "period", "npat_ttm", "eq_parent"]].rename(columns={"avail": "date"})
            .dropna(subset=["eq_parent"]).sort_values("date"))
    d = pd.merge_asof(daily, fund, on="date", by="ticker", direction="backward")
    d["shares"] = d.ticker.map(sh)
    d = d.dropna(subset=["shares", "period"])
    d["mcap_ty"] = d.close * d.shares / 1e9
    d["pe"] = np.where(d.npat_ttm > 0, d.mcap_ty / d.npat_ttm, np.nan)
    d["pb"] = np.where(d.eq_parent > 0, d.mcap_ty / d.eq_parent, np.nan)
    d = d.rename(columns={"npat_ttm": "npat_ttm_ty", "eq_parent": "vcsh_me_ty", "period": "ky_bctc"})
    cols = ["ticker", "date", "close", "shares", "mcap_ty", "npat_ttm_ty", "vcsh_me_ty", "pe", "pb", "ky_bctc"]
    d[cols].round(4).to_csv(os.path.join(HERE, "valuation_bds_stocks_daily.csv"), index=False, encoding="utf-8-sig")

    out = []
    for code, ten, rule in NHOM_TONG:
        x = d[d.ticker.isin(members(nh, rule))]
        pe_set = x.dropna(subset=["npat_ttm_ty"])
        pos = pe_set[pe_set.npat_ttm_ty > 0]
        pb_set = x[x.vcsh_me_ty > 0]
        g = pd.DataFrame({
            "n_ma": x.groupby("date").size(),
            "mcap_ty": x.groupby("date").mcap_ty.sum(),
            "mcap_pe": pe_set.groupby("date").mcap_ty.sum(), "npat_ttm_ty": pe_set.groupby("date").npat_ttm_ty.sum(),
            "mcap_pos": pos.groupby("date").mcap_ty.sum(), "npat_pos": pos.groupby("date").npat_ttm_ty.sum(),
            "mcap_pb": pb_set.groupby("date").mcap_ty.sum(), "vcsh_me_ty": pb_set.groupby("date").vcsh_me_ty.sum()})
        g["pe"] = np.where(g.npat_ttm_ty > 0, g.mcap_pe / g.npat_ttm_ty, np.nan)
        g["pe_ex_loss"] = np.where(g.npat_pos > 0, g.mcap_pos / g.npat_pos, np.nan)
        g["pb"] = np.where(g.vcsh_me_ty > 0, g.mcap_pb / g.vcsh_me_ty, np.nan)
        g["pe_coverage"] = g.mcap_pe / g.mcap_ty
        g = g.reset_index().assign(nhom=code, ten_nhom=ten)
        g = g[g.n_ma >= (2 if code == "VIN" else 5)]
        out.append(g[["date", "nhom", "ten_nhom", "n_ma", "mcap_ty", "npat_ttm_ty", "vcsh_me_ty", "pe", "pe_ex_loss", "pb", "pe_coverage"]])
    ind = pd.concat(out)
    ind.round(4).to_csv(os.path.join(HERE, "valuation_bds_nhom_daily.csv"), index=False, encoding="utf-8-sig")
    last = ind[ind.date == ind.date.max()].set_index("nhom")
    log(f"  định giá ngày {ind.date.max().date()}: " + " | ".join(
        f"{c} P/E {last.pe.get(c, np.nan):.1f} P/B {last.pb.get(c, np.nan):.2f}" for c, _, _ in NHOM_TONG if c in last.index))
    return d, ind


def _q(s):
    return s.index.year.astype(str) + "-Q" + s.index.quarter.astype(str)


def drivers(nh, ind, periods_end):
    rows = []

    def add(ma, ten, don_vi, nguon, ser):
        ser = ser.dropna()
        rows.append(pd.DataFrame({"ma": ma, "chi_tieu": ten, "don_vi": don_vi, "nguon": nguon,
                                  "period": ser.index, "value": ser.to_numpy()}))

    # VN-Index cuối quý
    ix = pd.read_csv(INDICES, usecols=["date", "index_code", "close"], parse_dates=["date"])
    vni = ix[ix.index_code == "VNINDEX"].set_index("date").close.sort_index()
    q = vni.groupby(_q(vni)).last()
    add("vnindex", "VN-Index cuối quý", "điểm", "index-fetcher (VCI)", q)
    # Định giá ngành cuối quý
    for code in ("ALL", "EXVIN", "NHA", "KCN", "VIN"):
        s = ind[ind.nhom == code].set_index("date").sort_index()
        if s.empty:
            continue
        last = s.groupby(_q(s)).last()
        ten = dict((c, t) for c, t, _ in NHOM_TONG)[code]
        add(f"pb_{code}", f"P/B {ten} cuối quý", "lần", "tính từ giá TradingView + BCTC VCI", last.pb)
        add(f"pe_{code}", f"P/E {ten} cuối quý", "lần", "tính từ giá TradingView + BCTC VCI", last.pe)
        if code == "ALL":
            add("mcap_ALL", "Vốn hoá toàn ngành BĐS cuối quý", "nghìn tỷ", "tính", last.mcap_ty / 1e3)
    # TPDN BĐS (riêng lẻ, HNX CBIS)
    b = pd.read_csv(BONDS, usecols=["nganh", "ngay_phat_hanh", "ngay_dao_han", "gia_tri_ty", "gia_tri_luu_hanh_ty",
                                    "gt_mua_lai_luy_ke_ty", "lai_suat", "ma_tp"], parse_dates=["ngay_phat_hanh", "ngay_dao_han"])
    b = b[b.nganh == "Bất động sản"].dropna(subset=["ngay_phat_hanh"]).copy()
    b["p_ph"] = b.ngay_phat_hanh.dt.year.astype(str) + "-Q" + b.ngay_phat_hanh.dt.quarter.astype(str)
    b["p_dh"] = np.where(b.ngay_dao_han.notna(),
                         b.ngay_dao_han.dt.year.astype("Int64").astype(str) + "-Q" + b.ngay_dao_han.dt.quarter.astype("Int64").astype(str), "")
    ph = b.groupby("p_ph").agg(gia_tri=("gia_tri_ty", "sum"), so_lo=("ma_tp", "size"))
    add("tp_ph", "TPDN BĐS phát hành riêng lẻ trong quý", "tỷ đồng", "HNX CBIS (bond-pivot)", ph.gia_tri)
    add("tp_ph_n", "Số lô TPDN BĐS phát hành", "lô", "HNX CBIS (bond-pivot)", ph.so_lo)
    b["lsw"] = b.lai_suat * b.gia_tri_ty
    ls = b.dropna(subset=["lai_suat"]).groupby("p_ph").apply(lambda x: x.lsw.sum() / x.gia_tri_ty.sum())
    add("tp_ls", "Lãi suất phát hành BQ gia quyền TPDN BĐS", "%/năm", "HNX CBIS (bond-pivot)", ls)
    b["con_lai"] = (b.gia_tri_ty - b.gt_mua_lai_luy_ke_ty.fillna(0)).clip(lower=0)
    today = pd.Timestamp.today()
    now_q = f"{today.year}-Q{today.quarter}"                  # quý lịch đang chạy
    fut = b.p_dh >= now_q                                      # chưa tới hạn -> dùng giá trị đang lưu hành
    b.loc[fut, "con_lai"] = b.loc[fut, "gia_tri_luu_hanh_ty"].fillna(b.loc[fut, "con_lai"])
    dh = b[b.p_dh != ""].groupby("p_dh").con_lai.sum()
    add("tp_dh", "TPDN BĐS đến hạn trong quý (giá trị còn lại)", "tỷ đồng", "HNX CBIS (bond-pivot)", dh[dh.index <= now_q])
    mat = dh[dh.index >= now_q].head(12)
    pd.DataFrame({"period": mat.index, "tp_den_han_ty": mat.to_numpy()}).to_csv(
        os.path.join(HERE, "bond_maturity_bds.csv"), index=False, encoding="utf-8-sig")
    # Lãi suất / tiền tệ
    tm = pd.read_csv(TM_WIDE, parse_dates=["date"]).set_index("date").sort_index()
    spec = [("lending_rate_avg", "LS cho vay BQ (VCB công bố)", "last"), ("lending_rate_big4", "LS cho vay BQ nhóm Big4", "last"),
            ("deposit_12m_avg", "LS huy động 12T BQ 28 NH", "last"), ("ib_on", "LS liên ngân hàng qua đêm (BQ quý)", "mean"),
            ("ib_3m", "LS liên ngân hàng 3T (BQ quý)", "mean"), ("policy_refinance", "LS tái cấp vốn", "last"),
            ("credit_growth_ytd", "Tăng trưởng tín dụng YTD", "last"), ("m2_growth_yoy", "M2 YoY", "last")]
    for sid, ten, how in spec:
        if sid in tm.columns:
            s = tm[sid].dropna()
            s = s.groupby(_q(s)).agg(how)
            add(sid, ten, "%", "transmission-fetcher (NHNN, dulieukinhte, FiinProX)", s)
    # Khối ngoại nhóm BĐS
    fv = pd.read_parquet(FOREIGN_VCI, columns=["code", "date", "netVal"])
    fv = fv[fv.code.isin(nh.ticker)]
    fv["date"] = pd.to_datetime(fv.date)
    fv = fv.set_index("date")
    vin = {"VIC", "VHM", "VRE"}
    add("kn_ALL", "Khối ngoại mua/bán ròng cổ phiếu BĐS trong quý", "tỷ đồng", "Vietcap IQ theo mã",
        fv.netVal.groupby(_q(fv)).sum() / 1e9)
    x = fv[~fv.code.isin(vin)]
    add("kn_EXVIN", "  trong đó: ngoài nhóm Vingroup", "tỷ đồng", "Vietcap IQ theo mã", x.netVal.groupby(_q(x)).sum() / 1e9)
    dr = pd.concat(rows, ignore_index=True)
    dr = dr[dr.period.str.match(r"^\d{4}-Q\d$")]
    dr.to_csv(os.path.join(HERE, "drivers_bds.csv"), index=False, encoding="utf-8-sig")
    log(f"  drivers_bds.csv: {dr.ma.nunique()} chỉ tiêu; lịch đáo hạn TPDN BĐS {len(mat)} quý tới: "
        + ", ".join(f"{p} {v:,.0f}" for p, v in mat.head(4).items()))
    return dr, mat


def main():
    nh = pd.read_csv(os.path.join(HERE, "nhom_bds.csv"), dtype={"cong_vao_nganh": int}, keep_default_na=False)
    w = fundamentals()
    d, ind = valuation(nh, w)
    periods_end = w.period.max()
    dr, mat = drivers(nh, ind, periods_end)
    con = sqlite3.connect(SQLITE)
    ind.assign(date=ind.date.dt.strftime("%Y-%m-%d")).to_sql("valuation_nhom_daily", con, if_exists="replace", index=False)
    d.assign(date=d.date.dt.strftime("%Y-%m-%d")).to_sql("valuation_stocks_daily", con, if_exists="replace", index=False)
    dr.to_sql("drivers", con, if_exists="replace", index=False)
    con.commit(); con.close()
    return d, ind, dr, mat


if __name__ == "__main__":
    utf8_stdout()
    main()
