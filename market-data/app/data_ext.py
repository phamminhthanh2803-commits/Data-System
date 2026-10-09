# -*- coding: utf-8 -*-
"""
data_ext.py - cac ham DU LIEU bo sung cho giao dien moi (Genea), xay tren datalib.py.

Chi them nhung gi datalib chua co: OHLC chi so / co phieu (nen), hieu suat nganh & co phieu theo
nhieu khung (1D...5Y), GTGD theo nha dau tu, treemap khoi ngoai / tu doanh, ngu phan vi P/E-P/B,
spot TPCP theo ky han, CAR he thong, NSNN nien giam. Khong sua datalib (lop du lieu giu nguyen).
"""
from __future__ import annotations

import os

import numpy as np
import pandas as pd
import streamlit as st

import datalib as dl

VN_INDEX_TEN = {"VNINDEX": "VN-Index", "VN30": "VN30", "VNMIDCAP": "VNMidcap", "VNSMALLCAP": "VNSmallcap",
                "HNXINDEX": "HNX-Index", "UPCOM": "UPCoM"}
HORIZONS = ["1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y"]


# ------------------------------------------------------------------ OHLC
@st.cache_data(show_spinner="Đang dựng cache OHLC (lần đầu ~30 giây) ...")
def _ohlc_vn(mt: float) -> pd.DataFrame:
    """tv-history.csv -> parquet OHLCV cua toan bo ma + chi so Viet Nam (HOSE/HNX/UPCOM)."""
    pq = os.path.join(dl.CACHE, "tv-ohlc-vn.parquet")
    if os.path.exists(pq) and os.path.getmtime(pq) >= mt:
        return pd.read_parquet(pq)
    d = pd.read_csv(dl.REGISTRY["tv_history"][2],
                    usecols=["date", "tv_symbol", "exchange", "symbol", "open", "high", "low", "close", "volume", "value_approx"],
                    dtype={"date": str})
    d = d[d.exchange.isin(dl.VN_EX)].copy()
    d["date"] = pd.to_datetime(d.date)
    for c in ("tv_symbol", "exchange", "symbol"):
        d[c] = d[c].astype("category")
    d.to_parquet(pq, index=False)
    return d


def ohlc_vn() -> pd.DataFrame:
    return _ohlc_vn(dl._raw_mt(dl.REGISTRY["tv_history"][2]))      # mtime THAT cua CSV (dl._mtime da gom cache nguon live-first)


def stock_ohlc(code: str) -> pd.DataFrame:
    """OHLCV 1 ma: tv-history (gia dieu chinh) + duoi live-first (Entrade/VNDirect x he so dieu chinh) sau ngay cuoi tv-history."""
    d = ohlc_vn()
    d = d[d.symbol == code].set_index("date").sort_index()[["open", "high", "low", "close", "volume", "value_approx"]]
    d = d[~d.index.duplicated(keep="last")]
    return _stock_ohlc_tail(code, d, dl._src_mt("tv_history"))


@st.cache_data(show_spinner=False)
def _stock_ohlc_tail(code: str, d: pd.DataFrame, mt_src: float) -> pd.DataFrame:
    s = dl.stock_src_ohlc(code, mt_src)
    if s.empty:
        return d
    tv_close = d[["close"]].reset_index().assign(symbol=code)[["symbol", "date", "close"]]
    if len(tv_close):
        tv_close = tv_close[tv_close.date < tv_close.date.max()]
    exch = dl.exchange_map()
    m = dl.adjust_stock_src(s, tv_close, exch).set_index("date")
    start = tv_close.date.max() + pd.Timedelta(days=1) if len(tv_close) else pd.Timestamp("1900-01-01")
    m = m[m.index >= start]
    if m.empty:
        return d
    tail = pd.DataFrame({c: m[c] * m.adj for c in ("open", "high", "low", "close")})
    tail["volume"] = m.volume
    tail["value_approx"] = m.value
    out = pd.concat([d[d.index < start], tail]).sort_index()
    out.index.name = "date"
    return out


def index_ohlc(code: str) -> pd.DataFrame:
    """OHLCV + GTGD (ty) cua 1 chi so VN. VNINDEX/VN30/HNXINDEX/UPCOM: indices-master (co value);
    VNMIDCAP/VNSMALLCAP: tv-history."""
    if code in ("VNMIDCAP", "VNSMALLCAP"):
        d = ohlc_vn()
        d = d[d.tv_symbol == f"HOSE:{code}"].set_index("date").sort_index()
        d = d[["open", "high", "low", "close", "volume"]].copy()
        d["value"] = np.nan
    else:
        i = dl.load("indices")
        d = i[i.index_code == code].set_index("date").sort_index()[["open", "high", "low", "close", "volume", "value"]].copy()
        d["value"] = d["value"] / 1e3          # trieu -> ty
    return d[~d.index.duplicated(keep="last")]


def index_close(codes) -> pd.DataFrame:
    out = {}
    for c in codes:
        try:
            s = index_ohlc(c)["close"].dropna()
            if len(s):
                out[VN_INDEX_TEN.get(c, c)] = s
        except Exception:  # noqa: BLE001
            pass
    d = pd.DataFrame(out)
    d.index.name = "Ngày"
    return d.sort_index()


# ---------------------------------------------------- HIEU SUAT NGANH / MA
def _p_at(px: pd.DataFrame, end: pd.Timestamp, h: str):
    """Gia tai moc lui `h` tu `end` (phien gan nhat <= moc)."""
    if h == "1D":
        ix = px.index[px.index < end]
        return px.loc[ix[-1]] if len(ix) else None
    if h == "YTD":
        moc = pd.Timestamp(year=end.year - 1, month=12, day=31)
    else:
        n = int(h[:-1])
        moc = end - (pd.Timedelta(days=7 * n) if h.endswith("W") else pd.DateOffset(months=n if h.endswith("M") else 12 * n))
    ix = px.index[px.index <= moc]
    return px.loc[ix[-1]] if len(ix) else None


def sector_returns_from(px: pd.DataFrame, end, pn: tuple, san: tuple) -> pd.DataFrame:
    """Hieu suat nganh 1D...5Y gia quyen von hoa dau ky tu ma tran gia `px` (co the da ghep hang hom nay - live)."""
    m = dl.meta(pn)
    sh = m.total_shares_outstanding_fundamental
    exch = m.exchange.reindex(px.columns)
    cols = [c for c in px.columns if exch.get(c) in san and pd.notna(sh.get(c))]
    px = px.loc[:pd.Timestamp(end), cols]
    END = px.index.max()
    p1 = px.loc[END]
    nhom = m.nhom.reindex(cols)
    rows = {}
    for h in HORIZONS:
        p0 = _p_at(px, END, h)
        if p0 is None:
            continue
        ok = p0.notna() & p1.notna() & (p0 > 0)
        w = (p0 * sh.reindex(cols))[ok]
        r = (p1[ok] / p0[ok] - 1) * 100
        g = pd.DataFrame({"r": r, "w": w, "nhom": nhom[ok]})
        by = g.groupby("nhom").apply(lambda x: np.average(x.r, weights=x.w) if x.w.sum() else np.nan)
        by["Toàn thị trường"] = np.average(g.r, weights=g.w) if g.w.sum() else np.nan
        rows[h] = by
    out = pd.DataFrame(rows)
    out.index.name = "Ngành"
    out.attrs["end"] = END
    return out


@st.cache_data(show_spinner=False)
def _sector_returns(mt: float, end: str, pn: tuple, san: tuple) -> pd.DataFrame:
    _, px, _ = dl.prices(since="2016-01-01")
    return sector_returns_from(px, end, pn, san)


def sector_returns(end, pn=None, san=("HOSE",)) -> pd.DataFrame:
    return _sector_returns(dl._mtime(dl.REGISTRY["tv_history"][2]), str(pd.Timestamp(end).date()), tuple(pn or dl.PN), tuple(san))


def stock_returns_from(px: pd.DataFrame, nhom: str, end, pn: tuple) -> pd.DataFrame:
    """Bang hieu suat co phieu trong nganh tu ma tran gia `px` (co the da ghep hang hom nay - live)."""
    m = dl.meta(pn)
    cols = [c for c in px.columns if m.nhom.get(c) == nhom]
    if not cols:
        return pd.DataFrame()
    px = px.loc[:pd.Timestamp(end), cols]
    END = px.index.max()
    p1 = px.loc[END]
    out = pd.DataFrame(index=cols)
    for h in HORIZONS:
        p0 = _p_at(px, END, h)
        out[h] = (p1 / p0 - 1) * 100 if p0 is not None else np.nan
    ten = dl.icb().get("ten", pd.Series(dtype=str))
    out.insert(0, "Tên công ty", out.index.map(lambda c: str(ten.get(c, "")) if pd.notna(ten.get(c, np.nan)) else ""))
    out.insert(1, "Sàn", out.index.map(lambda c: str(m.exchange.get(c, ""))))
    mc = (p1 * m.total_shares_outstanding_fundamental.reindex(cols)) / 1e9
    out.insert(2, "Vốn hoá (tỷ)", mc.values)
    out.index.name = "Mã"
    out = out[p1.reindex(out.index).notna()]
    return out.sort_values("Vốn hoá (tỷ)", ascending=False)


@st.cache_data(show_spinner=False)
def _stock_returns(mt: float, nhom: str, end: str, pn: tuple) -> pd.DataFrame:
    _, px, _ = dl.prices(since="2016-01-01")
    return stock_returns_from(px, nhom, end, pn)


def stock_returns(nhom, end, pn=None) -> pd.DataFrame:
    return _stock_returns(dl._mtime(dl.REGISTRY["tv_history"][2]), nhom, str(pd.Timestamp(end).date()), tuple(pn or dl.PN))


# ------------------------------------------------------------- DONG TIEN
def flows_investor() -> pd.DataFrame:
    """GTGD theo nha dau tu (ty VND/ngay): Khoi ngoai = (mua+ban)/2, Tu doanh = (mua+ban)/2, Trong nuoc khac = con lai."""
    fl = dl.load("flows")
    d = fl[fl.index_code.isin(["VNINDEX", "HNXINDEX", "UPCOM"])].copy()
    d["gd"] = (d.buy_val.fillna(0) + d.sell_val.fillna(0)) / 2 / 1e9
    g = d.pivot_table(index="date", columns="flow_type", values="gd", aggfunc="sum")
    to = dl.turnover_df()
    out = pd.DataFrame({"Khối ngoại": g.get("foreign"), "Tự doanh": g.get("prop")})
    out["Trong nước khác"] = to["Toàn thị trường"].reindex(out.index) - out.fillna(0).sum(axis=1)
    out = out[out["Trong nước khác"].notna() & (out["Trong nước khác"] > 0)]
    out.index.name = "Ngày"
    return out


def net_flows() -> pd.DataFrame:
    """Mua/ban rong khoi ngoai va tu doanh toan thi truong theo ngay (ty) + luy ke."""
    fv = dl.flows_vn()
    out = pd.DataFrame({"Khối ngoại ròng": fv["KN ròng toàn TT"]})
    td = [c for c in fv.columns if c.startswith("Tự doanh")]
    out["Tự doanh ròng"] = fv[td].sum(axis=1, min_count=1) if td else np.nan
    out.index.name = "Ngày"
    return out


def resample_flow(df: pd.DataFrame, freq: str) -> pd.DataFrame:
    rule = {"Phiên": None, "Tuần": "W-FRI", "Tháng": "ME"}[freq]
    return df if rule is None else df.resample(rule).sum(min_count=1).dropna(how="all")


def _flows_mt() -> float:
    return dl._mtime(dl.REGISTRY["flows"][2]) + dl._mtime(getattr(dl, "FS_VCI", "")) + dl._mtime(getattr(dl, "FS_VND", ""))


def treemap_flows(kind: str, d0, d1, pn=None, san=("HOSE", "HNX", "UPCOM"), topn=250) -> pd.DataFrame:
    """Rong theo ma trong ky, kem nhom nganh (kind: 'kn' | 'td'). Cache theo (ky, pn) de fragment LIVE chay lai nhanh."""
    return _treemap_flows(_flows_mt(), kind, pd.Timestamp(d0), pd.Timestamp(d1), tuple(pn or dl.PN), tuple(san), topn)


@st.cache_data(show_spinner=False)
def flows_sector_c(mt: float, d0, d1, san: tuple, tan: str, chi_tieu: str, pn: tuple):
    return dl.flows_sector(d0, d1, san, tan, chi_tieu, pn)


@st.cache_data(show_spinner=False)
def prop_sector_c(mt: float, d0, d1, san: tuple, pn: tuple):
    return dl.prop_sector(d0, d1, san, pn)


def flows_sector(d0, d1, san, tan, chi_tieu, pn):
    return flows_sector_c(_flows_mt(), pd.Timestamp(d0), pd.Timestamp(d1), tuple(san), tan, chi_tieu, tuple(pn or dl.PN))


def prop_sector(d0, d1, san, pn):
    return prop_sector_c(_flows_mt(), pd.Timestamp(d0), pd.Timestamp(d1), tuple(san), tuple(pn or dl.PN))


@st.cache_data(show_spinner=False)
def _treemap_flows(mt: float, kind: str, d0, d1, pn: tuple, san: tuple, topn: int) -> pd.DataFrame:
    d = dl._loc_fs(d0, d1, san, pn) if kind == "kn" else dl._loc_prop(d0, d1, san, pn)
    if d.empty:
        return pd.DataFrame()
    g = d.groupby(["code", "nhom"], observed=True).netVal.sum().reset_index()
    g["Ròng (tỷ)"] = g.netVal / 1e9
    g = g.rename(columns={"code": "Mã", "nhom": "Nhóm ngành"})[["Mã", "Nhóm ngành", "Ròng (tỷ)"]]
    g = g[g["Ròng (tỷ)"].abs() > 0.05]
    return g.reindex(g["Ròng (tỷ)"].abs().sort_values(ascending=False).index).head(topn).reset_index(drop=True)


def stock_flows(code: str) -> pd.DataFrame:
    fs = dl.foreign_stocks()
    pr = dl.prop_stocks()
    kn = fs[fs.code == code].set_index("date").sort_index()
    td = pr[pr.code == code].set_index("date").sort_index()
    out = pd.DataFrame({"Khối ngoại ròng": kn.netVal / 1e9 if len(kn) else pd.Series(dtype=float),
                        "Khối ngoại mua": kn.buyVal / 1e9 if len(kn) else pd.Series(dtype=float),
                        "Khối ngoại bán": kn.sellVal / 1e9 if len(kn) else pd.Series(dtype=float),
                        "Tự doanh ròng": td.netVal / 1e9 if len(td) else pd.Series(dtype=float),
                        "GTGD (tỷ)": kn.totalValue / 1e9 if len(kn) else pd.Series(dtype=float)})
    out.index.name = "Ngày"
    return out.sort_index()


def monthly_turnover() -> pd.DataFrame:
    to = dl.turnover_df()
    t = to[to["Phiên"] == "Đã đóng cửa"]["Toàn thị trường"]
    m = t.groupby(t.index.to_period("M")).agg(["mean", "count"])
    m.columns = ["GTGD bình quân phiên", "Số phiên"]
    m.index = m.index.to_timestamp()
    m.index.name = "Tháng"
    last = t.index.max()
    m["Chưa kết thúc"] = (m.index.to_period("M") == last.to_period("M")) & (last.day < 28)
    return m


# ------------------------------------------------------------- DINH GIA
@st.cache_data(show_spinner="Đang tính ngũ phân vị định giá ...")
def _quintiles(mt: float, ratio: str, years: int) -> pd.DataFrame:
    """% so co phieu theo ngu phan vi cua CHINH lich su ma do (cua so `years` nam), moi thang 1 diem."""
    # stocks-wide chi co 7 ma -> dung sectors-wide ICB cap 3 (36 nganh), moi nganh so voi chinh lich su cua no
    sw = dl.load("sectors_wide")
    sw = sw[sw.cap_icb == 3]
    p = sw.pivot_table(index="date", columns="ten_nganh", values=ratio, aggfunc="last").sort_index()
    p = p.where((p > 0) & (p < (500 if ratio == "pe" else 50)))
    m = p.resample("ME").last()
    m = m.loc[:, m.notna().sum() >= 24]
    vals = m.values
    n = len(m)
    win = years * 12
    rows = []
    for t in range(24, n):
        hist = vals[max(0, t - win):t]
        cur = vals[t]
        ok = ~np.isnan(cur)
        h_ok = ~np.isnan(hist)
        cnt = h_ok.sum(axis=0)
        ok &= cnt >= 12
        if not ok.any():
            continue
        below = (np.where(h_ok, hist, np.inf) <= cur).sum(axis=0)
        pct = below[ok] / cnt[ok] * 100
        q = np.digitize(pct, [20, 40, 60, 80])
        rows.append({"Ngày": m.index[t], "0–20% (rẻ nhất)": (q == 0).mean() * 100, "20–40%": (q == 1).mean() * 100,
                     "40–60%": (q == 2).mean() * 100, "60–80%": (q == 3).mean() * 100, "80–100% (đắt nhất)": (q == 4).mean() * 100,
                     "Số ngành": int(ok.sum()), "Trung vị phân vị": float(np.median(pct))})
    return pd.DataFrame(rows).set_index("Ngày")


def quintiles(ratio="pe", years=5) -> pd.DataFrame:
    return _quintiles(dl._mtime(dl.REGISTRY["sectors_wide"][2]), ratio, years)


# ------------------------------------------------------------------ TPCP
def tpcp_series(tenors=(1, 2, 5, 10)) -> pd.DataFrame:
    tp = dl.load("tpcp_curve")
    if tp.empty:
        return pd.DataFrame()
    k = tp[tp.ky_han_nam.isin(tenors)].pivot_table(index="ngay", columns="ky_han_nam", values="spot_nam")
    k.columns = [f"TPCP {int(c) if float(c).is_integer() else c} năm" for c in k.columns]
    k.index.name = "Ngày"
    return k.sort_index()


def tpcp_snapshot(as_of, backs=(0, 1, 3, 12)) -> pd.DataFrame:
    """Duong cong spot tai as-of va cac moc lui (thang). Cot = moc, index = ky han (nam)."""
    tp = dl.load("tpcp_curve")
    if tp.empty:
        return pd.DataFrame()
    out = {}
    for b in backs:
        moc = pd.Timestamp(as_of) - pd.DateOffset(months=b)
        ngay = tp.ngay[tp.ngay <= moc].max()
        if pd.isna(ngay):
            continue
        s = tp[tp.ngay == ngay].set_index("ky_han_nam").spot_nam.sort_index()
        out[("Hiện tại" if b == 0 else f"{b}M trước") + f" ({ngay:%d/%m/%y})"] = s
    d = pd.DataFrame(out)
    d.index.name = "Kỳ hạn (năm)"
    return d


# ------------------------------------------------------- HE THONG NGAN HANG
def car_frame() -> pd.DataFrame:
    """CAR he thong noi 2 che do (TT36 -> TT41) + IMF FSI (nhu app cu)."""
    w = dl.tm_wide(dl._mtime(dl.TM_WIDE))

    def s_(sid):
        return w[sid].dropna() if sid in w.columns else pd.Series(dtype=float)
    car = pd.DataFrame({
        "Toàn hệ thống": s_("car_min_system").combine_first(s_("car_tt41")),
        "NHTM Nhà nước": s_("car_min_soe").combine_first(s_("car_tt41_soe")),
        "NHTM cổ phần": s_("car_min_jsc").combine_first(s_("car_tt41_jsc")),
        "Toàn bộ TCTD (IMF FSI)": s_("car_imf_system"),
    })
    car.index.name = "Ngày"
    return car.dropna(how="all")


def car_banks() -> pd.Series:
    w = dl.tm_wide(dl._mtime(dl.TM_WIDE))
    out = {}
    for col in w.columns:
        if col.startswith("car_") and col[4:].isalpha() and len(col) == 7:
            s = w[col].dropna()
            if len(s):
                out[f"{col[4:].upper()} ({s.index[-1]:%m/%y})"] = s.iloc[-1]
    return pd.Series(out, dtype=float).sort_values()


# ------------------------------------------------------------------- NSNN
def nsnn_annual() -> pd.DataFrame:
    """Thu / chi / boi chi NSNN theo nam (nien giam PX-Web V03.13-14, V03.16), nghin ty."""
    try:
        thu = dl.nso_table("V03.13-14", "A")
        chi = dl.nso_table("V03.16", "A")
    except Exception:  # noqa: BLE001
        return pd.DataFrame()
    if thu.empty or chi.empty:
        return pd.DataFrame()

    def tong(d):
        c = [c for c in d.columns if str(c).strip().lower().startswith(("tổng", "chung"))]
        return d[c[0]] if c else d.iloc[:, 0]
    out = pd.DataFrame({"Tổng thu": tong(thu) / 1e3, "Tổng chi": tong(chi) / 1e3})
    out["Bội chi (thu − chi)"] = out["Tổng thu"] - out["Tổng chi"]
    out.index.name = "Năm"
    out.attrs["thu_cols"] = list(thu.columns)
    out.attrs["chi_cols"] = list(chi.columns)
    return out.dropna(how="all")


# -------------------------------------------------------------------- VSDC
def vsdc_new() -> pd.DataFrame:
    v = dl.load("vsdc").set_index("date").sort_index()
    cols = [c for c in ["ca_nhan", "to_chuc", "ca_nhan_nn", "to_chuc_nn", "tong"] if c in v]
    ten = {"ca_nhan": "Cá nhân trong nước", "to_chuc": "Tổ chức trong nước", "ca_nhan_nn": "Cá nhân nước ngoài",
           "to_chuc_nn": "Tổ chức nước ngoài", "tong": "Tổng"}
    d = v[cols].rename(columns=ten)
    d.index.name = "Ngày"
    return d


# ---------------------------------------------------------------- GDP NAM
def gdp_year() -> pd.DataFrame:
    d = dl.nm("GDP", "YOY_YEAR", pct=True)
    if d.empty:
        return d
    ten = {dl.nso_key(x): x for x in dl.GDP_NGANH}
    d.columns = [ten.get(dl.nso_key(c), c) for c in d.columns]
    d = d.loc[:, ~d.columns.duplicated()]
    return d


def gdp_sector_share() -> pd.DataFrame:
    """Co cau GDP theo khu vuc (gia hien hanh, quy) -> %."""
    hh = dl.gdp_nso("LEVEL_HH_Q", pct=False)
    kv = [c for c in dl.GDP_NGANH if c in hh.columns and c != "Tổng số"]
    if not kv:
        return pd.DataFrame()
    d = hh[kv]
    return d.div(d.sum(axis=1), axis=0) * 100
