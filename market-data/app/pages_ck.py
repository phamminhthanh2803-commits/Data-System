# -*- coding: utf-8 -*-
"""
pages_ck.py - Thi truong chung khoan › Chung khoan Viet Nam: Hieu suat · Dong tien · Dinh gia · Nha dau tu.
Moi muc (H2 chu hoa) gom cac the `ui.card(...)`; so lieu tu datalib (dl) + data_ext (dx).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import data_live as rt
import datalib as dl
import data_ext as dx
import ui_genea as ui

IDX = list(dx.VN_INDEX_TEN)            # VNINDEX, VN30, VNMIDCAP, VNSMALLCAP, HNXINDEX, UPCOM
TEN = dx.VN_INDEX_TEN
SAN = ["Toàn thị trường", "HOSE", "HNX", "UPCoM"]
PN_TOGGLE = {"Phân ngành": ["Cấp 2", "Cấp 1", "Cấp 3"]}


def _pn(c):
    cap = int(str(c.toggle.get("Phân ngành", "Cấp 2"))[-1])
    return (cap, True)


def _ma_chon(key, default="FPT", label="Mã cổ phiếu"):
    m = dl.meta()
    ds = sorted(m.index)
    k = f"ma_{key}"
    if k not in st.session_state:
        st.session_state[k] = default if default in ds else ds[0]
    c1, _ = st.columns([1.2, 4])
    return c1.selectbox(label, ds, key=k), m


# ================================================================ HIEU SUAT
def hieu_suat(ctx):
    LAST = ctx["last"]
    ui.h2("Chỉ số")
    # (1) nen + khoi luong
    with ui.card("Chỉ số", "", help="Nến/đường theo phiên, cột = khối lượng (xanh phiên tăng, đỏ phiên giảm). "
                 "Nguồn indices-master (VCI) và tv-history (VNMidcap/VNSmallcap).",
                 key="vni_nen", chips=IDX, chip_default="VNINDEX", chip_fmt=TEN.get, toggles={"Kiểu": ["Nến", "Đường"]},
                 default="1Y") as c:
        o = rt.with_live(dx.index_ohlc(c.chip), "index_ohlc", code=c.chip)
        oc = c.cut(o)
        last2 = o.close.dropna()
        sub = ui.delta_html(last2.iloc[-1], last2.iloc[-2] if len(last2) > 1 else None, 2, "điểm") if len(last2) else ""
        c.markdown(f'<div class="gn-title" style="margin-top:-6px">{sub}<span class="unit">· {last2.index[-1]:%d/%m/%Y}</span></div>')
        fig = ui.fig_candle(oc, mode=c.toggle["Kiểu"], name=TEN[c.chip])
        if fig is not None:
            ui.add_last_price(fig, oc.close)
        c.chart(fig, oc.rename(columns={"open": "Mở", "high": "Cao", "low": "Thấp", "close": "Đóng", "volume": "KL", "value": "GTGD (tỷ)"}),
                ten=f"{TEN[c.chip]} OHLCV")

    # (2) rebase 100
    with ui.card("Hiệu suất chỉ số", "rebase 100 đầu kỳ", help="Mỗi chỉ số quy về 100 tại phiên đầu khung thời gian.",
                 key="idx_rebase", chips=IDX, chip_default=["VNINDEX", "VN30", "VNMIDCAP", "VNSMALLCAP"], chip_multi=True,
                 chip_fmt=TEN.get, default="YTD") as c:
        px = c.cut(rt.with_live(dx.index_close(c.chip), "index_close", codes=c.chip))
        reb = rt.mark_live(ui.rebase100(px), px)
        fig = ui.fig_line(reb, "rebase 100", hover_nd=1)
        if fig is not None:
            ui.add_hline(fig, 100, color=ui.TOK["gray"])
        perf = (reb.ffill().iloc[-1] - 100).round(2) if len(reb) else pd.Series(dtype=float)
        c.chart(fig, reb, ten="Hieu suat chi so rebase 100",
                note_text=" · ".join(f"{k} {ui.fmt_vn(v, 1, dau=True)}%" for k, v in perf.items()) if len(perf) else None)

    # (3) do rong
    with ui.card("Độ rộng thị trường: cổ phiếu dưới đường MA", "% số mã (toàn TT) · số mã (theo sàn)",
                 help="Toàn thị trường: % cổ phiếu có giá dưới MA20/50/100/200. Theo sàn: số mã dưới MA50/200/300 "
                      "(giá điều chỉnh TradingView, tính trong datalib.breadth).",
                 key="breadth", chips=["Toàn thị trường", "HOSE", "HNX", "UPCOM"], chip_default="Toàn thị trường", default="1Y") as c:
        br = c.cut(rt.with_live(dl.breadth_df(), "breadth"))
        if c.chip == "Toàn thị trường":
            d = rt.mark_live(pd.DataFrame({f"% dưới MA{w}": 100 - br[f"% mã trên MA{w}"] for w in (20, 50, 100, 200)}), br)
            fig = ui.fig_line(d, "% số mã", zero=True, hover_nd=1)
            if fig is not None:
                ui.add_hline(fig, 50, color=ui.TOK["gray"])
        else:
            d = br[[f"Dưới MA{w} - {c.chip}" for w in (50, 200, 300)]]
            fig = ui.fig_line(d, "số mã", zero=True, hover_nd=0)
        c.chart(fig, d, ten=f"Do rong duoi MA {c.chip}")

    ui.h2("Ngành")
    # (4) hieu suat nganh rebase
    with ui.card("Hiệu suất ngành", "rebase 100 đầu kỳ, gia quyền vốn hoá HOSE",
                 help="Chỉ số ngành tự tính: tổng vốn hoá các mã HOSE trong ngành (ICB Vietcap), quy về 100 tại đầu kỳ; "
                      "rổ = mã có giá ở cả đầu và cuối kỳ.", key="sec_rebase", toggles=PN_TOGGLE, default="YTD") as c:
        pn = _pn(c)
        sec, _ = dl.sector_caps(dl._mtime(dl.REGISTRY["tv_history"][2]), c.d0.strftime("%Y-%m-%d"),
                                min(c.d1, LAST).strftime("%Y-%m-%d"), pn)
        sec = rt.with_live(sec, "sector_caps", pn=pn)
        ds = [x for x in sec.columns if x != "Toàn HOSE"]
        kk = f"sec_pick_{pn[0]}"
        mac = [x for x in ("Ngân hàng", "Bất động sản", "Dịch vụ tài chính", "Vingroup", "Tài nguyên cơ bản", "Thực phẩm & đồ uống",
                           "Tài chính", "Công nghiệp", "Hàng & dịch vụ công nghiệp") if x in ds][:6]
        chon = st.multiselect("Ngành", ds, default=mac or ds[:6], key=kk)
        d = sec[(chon or ds[:6]) + ["Toàn HOSE"]]
        fig = ui.fig_line(d, "rebase 100", hover_nd=1, colors={"Toàn HOSE": ui.TOK["ink"]}, dash={"Toàn HOSE": "dash"})
        if fig is not None:
            ui.add_hline(fig, 100, color=ui.TOK["gray"])
        c.chart(fig, d, ten="Hieu suat nganh rebase 100")

    # (5) thay doi von hoa theo nganh
    with ui.card("Thay đổi vốn hoá theo ngành", "%", help="Biến động gia quyền vốn hoá đầu kỳ của các mã HOSE trong ngành, "
                 "tính đến phiên gần nhất. 'Toàn thị trường' = toàn bộ HOSE.",
                 key="sec_chg", chips=dx.HORIZONS, chip_default="1M", toggles=PN_TOGGLE, controls=False) as c:
        pn = _pn(c)
        r_hist = dx.sector_returns(LAST, pn)
        r, live_ts = rt.sector_returns_live(pn, ("HOSE",))
        if r is None:
            r = r_hist
        if r.empty or c.chip not in r:
            c.empty()
        else:
            s = r[c.chip].dropna()
            tt = s.get("Toàn thị trường", np.nan)
            s = s.drop("Toàn thị trường", errors="ignore").sort_values(ascending=False)
            s.loc["Toàn thị trường"] = tt
            fig = ui.fig_hbar(s, "%", sign=True, highlight="Toàn thị trường", nd=1)
            if live_ts is not None:
                r.attrs["live"] = {"ts": live_ts, "hist_end": LAST}
            c.chart(fig, r.round(2), last=r.attrs.get("end"), ten=f"Thay doi von hoa nganh {c.chip}", df_export=r_hist.round(2))

    # (6) bang hieu suat co phieu trong nganh
    with ui.card("Hiệu suất cổ phiếu trong ngành", "%", help="Biến động giá điều chỉnh của từng mã đến phiên gần nhất; "
                 "sắp theo vốn hoá. '—' = chưa đủ lịch sử.", key="stock_tbl", toggles=PN_TOGGLE, controls=False) as c:
        pn = _pn(c)
        ds = dl.ds_nganh(pn)
        kk = f"nganh_tbl_{pn[0]}"
        if kk not in st.session_state:
            st.session_state[kk] = "Ngân hàng" if "Ngân hàng" in ds else ds[0]
        c1, c2 = st.columns([1.5, 4])
        ng = c1.selectbox("Ngành", ds, key=kk)
        t_hist = dx.stock_returns(ng, LAST, pn)
        t, live_ts = rt.stock_returns_live(ng, pn)
        if t is None:
            t = t_hist
        if t.empty:
            c.empty()
        else:
            n_hien = c2.slider("Số mã hiển thị", 10, max(10, len(t)), min(30, len(t)), key=f"n_{kk}")
            c.table(t.head(n_hien), ten=f"Hieu suat co phieu {ng}", html=True, pct_cols=dx.HORIZONS, name_col="Tên công ty",
                    df_export=t_hist, live_ts=live_ts)
            ui.note(f"{len(t)} mã trong ngành {ng} (ICB cấp {pn[0]}). " +
                    (f"Tính với giá live {live_ts:%H:%M:%S} (1D = so với đóng cửa phiên trước)." if live_ts is not None else f"Tính đến {LAST:%d/%m/%Y}."))

    ui.h2("Cổ phiếu")
    # (7) co phieu
    with ui.card("Giá cổ phiếu", "", help="Nến/đường + khối lượng từ tv-history (giá điều chỉnh).", key="stock_px",
                 toggles={"Kiểu": ["Nến", "Đường"]}, default="1Y") as c:
        ma, m = _ma_chon("px")
        o = rt.with_live(dx.stock_ohlc(ma), "stock_ohlc", code=ma)
        oc = c.cut(o)
        if o.empty:
            c.empty()
        else:
            l2 = o.close.dropna()
            info = m.loc[ma] if ma in m.index else None
            sub = ui.delta_html(l2.iloc[-1], l2.iloc[-2] if len(l2) > 1 else None, 0, "đ")
            extra = ""
            if info is not None:
                extra = (f'<span class="unit">· {info.exchange} · {info.nhom} · vốn hoá {ui.fmt_vn(info.market_cap_basic / 1e9, 0)} tỷ</span>'
                         if pd.notna(info.market_cap_basic) else f'<span class="unit">· {info.exchange} · {info.nhom}</span>')
            c.markdown(f'<div class="gn-title" style="margin-top:-6px"><h3>{ma}</h3>{sub}{extra}</div>')
            fig = ui.fig_candle(oc, mode=c.toggle["Kiểu"], name=ma, ma=[20, 50])
            if fig is not None:
                ui.add_last_price(fig, oc.close, 0)
            r = oc.iloc[-1] if len(oc) else None
            c.chart(fig, oc.rename(columns={"open": "Mở", "high": "Cao", "low": "Thấp", "close": "Đóng", "volume": "KL", "value_approx": "GTGD"}),
                    ten=f"{ma} OHLCV",
                    note_text=(f"Phiên {oc.index[-1]:%d/%m/%Y}: O {ui.fmt_vn(r.open, 0)} · H {ui.fmt_vn(r.high, 0)} · L {ui.fmt_vn(r.low, 0)} · "
                               f"C {ui.fmt_vn(r.close, 0)} · KL {ui.fmt_vn(r.volume, 0)}") if r is not None else None)


# ================================================================ DONG TIEN
def dong_tien(ctx):
    LAST = ctx["last"]
    ui.h2("Chỉ số")
    with ui.card("Giá trị giao dịch", "tỷ đồng", help="GTGD khớp lệnh + thoả thuận theo phiên (VCI accumulatedValue); phiên VCI chưa có "
                 "được ước tính bằng close×KL. Đường = MA20 / MA50.", key="gtgd", chips=SAN, chip_default="Toàn thị trường",
                 toggles={"Gộp": ["Phiên", "Tuần", "Tháng"]}, default="1Y") as c:
        to = rt.with_live(dl.turnover_df(), "turnover")
        col = c.chip
        d = to[[col]].copy()
        d["MA20"] = d[col].rolling(20).mean()
        d["MA50"] = d[col].rolling(50).mean()
        d = c.cut(d)
        if c.toggle["Gộp"] != "Phiên":
            d = rt.mark_live(dx.resample_flow(d[[col]], c.toggle["Gộp"]), d)
            fig = ui.fig_bars(d, col, "tỷ đồng", sign=False, hover_nd=0)
        else:
            fig = ui.fig_bars(d, col, "tỷ đồng", sign=False, lines=["MA20", "MA50"], hover_nd=0)
        c.chart(fig, d, ten=f"GTGD {col}")

    with ui.card("Giá trị giao dịch theo nhà đầu tư", "tỷ đồng", help="Khối ngoại và tự doanh = (mua + bán)/2 từ flows-master; "
                 "trong nước khác = GTGD toàn thị trường trừ hai nhóm trên.", key="gtgd_ndt",
                 toggles={"Gộp": ["Phiên", "Tuần", "Tháng"], "Hiển thị": ["Giá trị", "Tỷ trọng"]}, default="1Y") as c:
        fi = c.cut(rt.with_live(dx.flows_investor(), "flows_investor"))
        d = rt.mark_live(dx.resample_flow(fi, c.toggle["Gộp"]), fi)
        fig = ui.fig_stack(d, "tỷ đồng", normalize=c.toggle["Hiển thị"] == "Tỷ trọng",
                           colors={"Khối ngoại": ui.TOK["orange"], "Tự doanh": ui.TOK["brown"], "Trong nước khác": ui.TOK["gray_light"]})
        tt = d.sum()
        note = ("Cả kỳ: khối ngoại " + ui.fmt_vn(tt.get("Khối ngoại", 0) / tt.sum() * 100, 1) + "%, tự doanh " +
                ui.fmt_vn(tt.get("Tự doanh", 0) / tt.sum() * 100, 1) + "%") if len(d) and tt.sum() else None
        if "live" in d.attrs:
            note = (note or "") + " · hôm nay: tự doanh chưa có (không live)"
        c.chart(fig, d, ten="GTGD theo nha dau tu", note_text=note)

    with ui.card("Giá trị giao dịch bình quân theo tháng", "tỷ đồng / phiên", help="Bình quân GTGD toàn thị trường mỗi phiên trong tháng; "
                 "tháng chưa kết thúc tô nhạt.", key="gtgd_thang", periods=["1Y", "3Y", "5Y", "All"], default="3Y") as c:
        m = c.cut(dx.monthly_turnover())
        fig = ui.fig_bars(m, "GTGD bình quân phiên", "tỷ đồng", sign=False, faded_mask=m["Chưa kết thúc"], hover_nd=0)
        c.chart(fig, m, ten="GTGD binh quan thang")

    nf = rt.with_live(dx.net_flows(), "net_flows")
    for ten, col, key in (("Giao dịch ròng tự doanh", "Tự doanh ròng", "td_rong"), ("Giao dịch ròng khối ngoại", "Khối ngoại ròng", "kn_rong")):
        with ui.card(ten, "tỷ đồng", help="Mua ròng cam, bán ròng xám; đường nâu = luỹ kế trong kỳ (trục phải). Toàn 3 sàn."
                     + (" Hôm nay: khối ngoại live (Σ ròng theo mã từ bộ thu); tự doanh không live." if key == "kn_rong" else
                        " Tự doanh KHÔNG live (chỉ có sau phiên)."),
                     key=key, toggles={"Gộp": ["Phiên", "Tuần", "Tháng"]}, default="1Y") as c:
            d0 = c.cut(nf[[col]]).dropna()
            d = rt.mark_live(dx.resample_flow(d0, c.toggle["Gộp"]), d0)
            d["Luỹ kế"] = d[col].cumsum()
            fig = ui.fig_bars(d, col, "tỷ đồng", sign=True, cum="Luỹ kế", hover_nd=0)
            tong = d[col].sum() if len(d) else np.nan
            c.chart(fig, d, ten=ten, note_text=f"Cả kỳ: {ui.fmt_vn(tong, 0, dau=True)} tỷ" if pd.notna(tong) else None,
                    legend_html=ui.legend_html([("Mua ròng", ui.TOK["orange"]), ("Bán ròng", ui.TOK["gray"]), ("Luỹ kế", ui.TOK["brown"])]))

    for ten, kind, key in (("Bản đồ tự doanh theo mã", "td", "tm_td"), ("Bản đồ khối ngoại theo mã", "kn", "tm_kn")):
        with ui.card(ten, "ròng trong kỳ, tỷ đồng", help="Ô = |giá trị ròng| của mã trong kỳ, gom theo ngành ICB; xanh mua ròng, đỏ bán ròng. "
                     "Tối đa 250 mã lớn nhất.", key=key, toggles=PN_TOGGLE, default="1M") as c:
            d_hist = dx.treemap_flows(kind, c.d0, min(c.d1, LAST), _pn(c))
            d, live_ts = (rt.treemap_add_today(d_hist, _pn(c)) if kind == "kn" and c.d1 >= rt.today_ts() else (d_hist, None))
            fig = ui.fig_treemap(d)
            dd = d.set_index("Mã") if len(d) else d
            if live_ts is not None:
                dd.attrs["live"] = {"ts": live_ts, "hist_end": LAST, "src": rt.LIVE_1M}
            c.chart(fig, dd, last=min(c.d1, LAST) if live_ts is None else c.d1, ten=ten,
                    df_export=d_hist.set_index("Mã") if len(d_hist) else d_hist)

    ui.h2("Ngành")
    ui.card_empty("Dòng tiền chủ động theo ngành", "tỷ đồng", "Chưa có dữ liệu khớp lệnh chủ động (mua lên / bán xuống) theo mã trong hệ thống.",
                  key="chu_dong_nganh")
    with ui.card("Khối ngoại ròng theo ngành", "tỷ đồng", help="Tổng mua/bán ròng khối ngoại của các mã trong ngành (Vietcap theo mã, 3 sàn).",
                 key="kn_nganh", toggles={"Hiển thị": ["Cả kỳ", "Tuần", "Tháng"], **PN_TOGGLE}, default="3M") as c:
        pn = _pn(c)
        tan = {"Cả kỳ": "M", "Tuần": "W", "Tháng": "M"}[c.toggle["Hiển thị"]]
        piv, tong = dx.flows_sector(c.d0, min(c.d1, LAST), ("HOSE", "HNX", "UPCOM"), tan, "netVal", pn)
        if tong.empty:
            c.empty()
        elif c.toggle["Hiển thị"] == "Cả kỳ":
            tong_hist = tong
            tong, live_ts = (rt.sector_flows_add_today(tong, pn) if c.d1 >= rt.today_ts() else (tong, None))
            if live_ts is not None:
                tong.attrs["live"] = {"ts": live_ts, "hist_end": LAST, "src": rt.LIVE_1M}
            c.chart(ui.fig_hbar(tong["Ròng (tỷ)"], "tỷ đồng", nd=0), tong, last=c.d1 if live_ts is not None else min(c.d1, LAST),
                    ten="Khoi ngoai rong theo nganh", df_export=tong_hist)
        else:
            c.chart(ui.fig_stack(piv, "tỷ đồng"), piv, ten="Khoi ngoai rong theo nganh")
    with ui.card("Tự doanh ròng theo ngành", "tỷ đồng", help="Tổng tự doanh ròng của các mã trong ngành (VNDirect theo mã, từ 05/2022).",
                 key="td_nganh", toggles=PN_TOGGLE, default="3M") as c:
        s = dx.prop_sector(c.d0, min(c.d1, LAST), ("HOSE", "HNX", "UPCOM"), _pn(c))
        c.chart(ui.fig_hbar(s, "tỷ đồng", nd=0) if len(s) else None, s.to_frame("Ròng (tỷ)"), last=min(c.d1, LAST), ten="Tu doanh rong theo nganh")

    ui.h2("Cổ phiếu")
    with ui.card("Giao dịch khối ngoại & tự doanh theo mã", "tỷ đồng", help="Ròng theo phiên của 1 mã; đường = luỹ kế trong kỳ.",
                 key="ma_flow", chips=["Khối ngoại", "Tự doanh"], chip_default="Khối ngoại", toggles={"Gộp": ["Phiên", "Tuần", "Tháng"]},
                 default="6M") as c:
        ma, _ = _ma_chon("flow")
        f = rt.with_live(dx.stock_flows(ma), "stock_flows", code=ma)
        col = f"{c.chip} ròng"
        d0 = c.cut(f[[col]]).dropna()
        d = rt.mark_live(dx.resample_flow(d0, c.toggle["Gộp"]), d0)
        if d.empty:
            c.empty()
        else:
            d["Luỹ kế"] = d[col].cumsum()
            c.chart(ui.fig_bars(d, col, "tỷ đồng", sign=True, cum="Luỹ kế", hover_nd=1), d, ten=f"{ma} {col}")
    ui.card_empty("Giao dịch nội bộ (cổ đông lớn, người nội bộ)", "", "Chưa có nguồn công bố giao dịch nội bộ trong hệ thống.", key="noi_bo")

    ui.h2("Quỹ ETF")
    ui.card_empty("Dòng tiền ETF ròng", "tỷ đồng", "Chưa có dữ liệu NAV / chứng chỉ quỹ ETF (29 quỹ) trong hệ thống.", key="etf")


# ================================================================== DINH GIA
RO = {"VNINDEX": "VN-Index", "VN30": "VN30", "HNX": "HNX", "UPCOM": "UPCoM"}


def _val_card(ct, ten, key):
    vw = dl.load("valuation_wide")
    with ui.card(f"{ten} TTM", "lần", help=f"{ten} trailing 12 tháng theo rổ (VNDirect, valuation-wide). Nét đứt = bình quân trong kỳ.",
                 key=key, chips=list(RO), chip_default=["VNINDEX", "VN30"], chip_multi=True, chip_fmt=RO.get, default="3Y") as c:
        p = vw[vw.code.isin(c.chip)].pivot_table(index="date", columns="code", values=ct, aggfunc="last")
        p.columns = [RO.get(x, x) for x in p.columns]
        p.index.name = "Ngày"
        p = rt.with_live(p, "valuation", ratio_by_col={RO.get(k, k): rt.ratio_for_index(k) for k in c.chip})
        d = c.cut(p)
        fig = ui.fig_line(d, "lần", hover_nd=2)
        if fig is not None and len(d):
            first = d.columns[0]
            mu = d[first].mean()
            ui.add_hline(fig, mu, f"TB {first} {ui.fmt_vn(mu, 2)}", color=ui.TOK["gray"])
        cur = " · ".join(f"{k} {ui.fmt_vn(v, 2)}" for k, v in d.ffill().iloc[-1].items()) if len(d) else ""
        c.chart(fig, d, ten=f"{ten} theo ro", note_text=cur or None)


def dinh_gia(ctx):
    LAST = ctx["last"]
    ui.h2("Chỉ số")
    _val_card("pe", "P/E", "pe_ro")
    _val_card("pb", "P/B", "pb_ro")
    with ui.card("P/E & P/B toàn thị trường có / không Vingroup", "lần", help="valuation-adjusted: chỉ số gốc và sau khi loại VIC-VHM-VRE-VPL.",
                 key="val_vin", chips=["VNINDEX", "VN30"], chip_default="VNINDEX", chip_fmt=RO.get,
                 toggles={"Chỉ tiêu": ["P/E", "P/B", "ROE"]}, default="3Y") as c:
        va = dl.load("valuation_adjusted")
        ct = {"P/E": "pe", "P/B": "pb", "ROE": "roe"}[c.toggle["Chỉ tiêu"]]
        s = va[va["index"] == c.chip].set_index("date").sort_index()
        d = s[[ct, f"{ct}_adj"]].rename(columns={ct: "Toàn thị trường", f"{ct}_adj": "Loại nhóm Vingroup"})
        if ct == "roe":
            d = d * 100
        else:
            d = rt.with_live(d, "valuation", ratio_by_col={"Toàn thị trường": rt.ratio_for_index(c.chip),
                                                          "Loại nhóm Vingroup": rt.ratio_for_index(c.chip, exclude_vin=True)})
        d.index.name = "Ngày"
        d = c.cut(d)
        c.chart(ui.fig_line(d, "%" if ct == "roe" else "lần", hover_nd=2, colors={"Loại nhóm Vingroup": ui.TOK["brown"]}), d,
                ten=f"{c.toggle['Chỉ tiêu']} co khong Vin")

    for ct, ten, key in (("pe", "P/E", "q_pe"), ("pb", "P/B", "q_pb")):
        with ui.card(f"Ngũ phân vị {ten}", "% số ngành ICB cấp 3", help=f"Mỗi tháng: {ten} hiện tại của từng ngành ICB cấp 3 (36 ngành, VNDirect) xếp phân vị "
                     f"so với CHÍNH lịch sử 5 năm của ngành đó, rồi đếm % số ngành rơi vào từng ngũ phân vị. Nhiều ngành ở 0–20% = thị trường rẻ so với "
                     f"quá khứ của chính nó. (Theo từng mã chưa làm được: stocks-wide mới có 7 mã.)",
                     key=key, periods=["1Y", "3Y", "5Y", "All"], default="5Y") as c:
            q = c.cut(dx.quintiles(ct))
            cols = [x for x in q.columns if "%" in x]
            fig = ui.fig_stack(q[cols], "%", area=True,
                               colors=dict(zip(cols, [ui.TOK["up"], "#9fd6b9", ui.TOK["gray_light"], ui.TOK["orange_light"], ui.TOK["down"]])))
            c.chart(fig, q.round(1), ten=f"Ngu phan vi {ten}",
                    note_text=f"Số ngành có đủ lịch sử: {int(q['Số ngành'].iloc[-1])} · trung vị phân vị {ui.fmt_vn(q['Trung vị phân vị'].iloc[-1], 0)}%" if len(q) else None)

    ui.h2("Ngành")
    with ui.card("Định giá theo ngành ICB", "lần", help="P/E, P/B theo ngành ICB cấp 2 (VNDirect sectors-wide).", key="val_nganh",
                 toggles={"Chỉ tiêu": ["P/E", "P/B", "P/S"]}, default="3Y") as c:
        sw = dl.load("sectors_wide")
        ct = {"P/E": "pe", "P/B": "pb", "P/S": "ps"}[c.toggle["Chỉ tiêu"]]
        ds = sorted(sw[sw.cap_icb == 2].ten_nganh.dropna().unique())
        chon = st.multiselect("Ngành", ds, default=[x for x in ("Ngân hàng", "Bất động sản", "Dịch vụ tài chính", "Bán lẻ") if x in ds], key="val_ng_pick")
        p = sw[sw.ten_nganh.isin(chon or ds[:4])].pivot_table(index="date", columns="ten_nganh", values=ct, aggfunc="last")
        p.index.name = "Ngày"
        p = rt.with_live(p, "valuation", ratio_by_col={g: rt.ratio_for_sector(g) for g in p.columns})
        d = c.cut(p)
        c.chart(ui.fig_line(d, "lần", hover_nd=2), d, ten=f"{c.toggle['Chỉ tiêu']} theo nganh")

    ui.h2("Cổ phiếu")
    with ui.card("Định giá cổ phiếu", "lần", help="P/E, P/B, P/S theo ngày của 1 mã (stocks-wide; mã chưa có thì kéo VNDirect).", key="val_ma",
                 toggles={"Chỉ tiêu": ["P/E", "P/B", "P/S"]}, default="3Y") as c:
        ma, _ = _ma_chon("val")
        s = dl.stock_val(ma)
        ct = {"P/E": "pe", "P/B": "pb", "P/S": "ps"}[c.toggle["Chỉ tiêu"]]
        if s.empty or ct not in s:
            c.empty()
        else:
            col = f"{c.toggle['Chỉ tiêu']} {ma}"
            d = c.cut(rt.with_live(s[[ct]].rename(columns={ct: col}), "valuation", ratio_by_col={col: rt.ratio_for_stock(ma)}))
            d.index.name = "Ngày"
            fig = ui.fig_line(d, "lần", hover_nd=2)
            if fig is not None and len(d):
                mu = d.iloc[:, 0].mean()
                ui.add_hline(fig, mu, f"TB {ui.fmt_vn(mu, 2)}", color=ui.TOK["gray"])
            c.chart(fig, d, ten=f"{ma} {c.toggle['Chỉ tiêu']}")


# ================================================================ NHA DAU TU
def nha_dau_tu(ctx):
    ui.h2("Tài khoản giao dịch")
    v = dx.vsdc_new()
    with ui.card("Số tài khoản mở mới ròng theo tháng", "tài khoản", help="Chênh lệch số tài khoản giao dịch cuối tháng (VSDC) so với tháng trước.",
                 key="vsdc_moi", chips=list(v.columns), chip_default="Tổng", periods=["1Y", "3Y", "5Y", "All"], default="3Y") as c:
        d = c.cut(v[[c.chip]].diff().dropna())
        d.columns = ["Mở mới ròng"]
        c.chart(ui.fig_bars(d, "Mở mới ròng", "tài khoản", sign=True, hover_nd=0), d, ten=f"TK mo moi {c.chip}")
    with ui.card("Số tài khoản giao dịch", "tài khoản", help="Số dư tài khoản cuối tháng theo loại nhà đầu tư (VSDC).",
                 key="vsdc_sodu", periods=["1Y", "3Y", "5Y", "All"], default="All") as c:
        d = c.cut(v)
        c.chart(ui.fig_line(d[[x for x in d.columns if x != "Tổng"]], "tài khoản", hover_nd=0), d, ten="So TK giao dich")

    ui.h2("Dư nợ margin")
    ui.card_empty("Dư nợ margin toàn thị trường theo quý", "tỷ đồng", "Chưa có dữ liệu dư nợ cho vay ký quỹ từ BCTC CTCK trong hệ thống.", key="margin_tt")
    ui.card_empty("Dư địa cho vay margin", "tỷ đồng", "Cần vốn chủ sở hữu CTCK × 2 trừ dư nợ hiện tại — chưa có nguồn.", key="margin_du_dia")
    ui.card_empty("Công ty chứng khoán theo dư nợ margin", "tỷ đồng", "Chưa có bảng dư nợ margin từng CTCK.", key="margin_ctck")
