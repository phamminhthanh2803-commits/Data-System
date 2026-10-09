# -*- coding: utf-8 -*-
"""
pages_khac.py - Tong quan (KPI + 4 chart + tinh trang du lieu) · Kho du lieu · Xuat Excel · Chung khoan the gioi ·
Trai phieu (phat hanh, co cau & lai suat, gia & duong cong loi suat) · Tin tuc.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data_live as rt
import datalib as dl
import data_ext as dx
import ui_genea as ui


# ================================================================ TONG QUAN
def tong_quan(ctx):
    LAST = ctx["last"]
    try:                                   # 1 dong KPI live (neu hom nay co du lieu DNSE) -> link sang trang Live
        import pages_live
        pages_live.mini_strip()
    except Exception:  # noqa: BLE001
        pass
    to = rt.with_live(dl.turnover_df(), "turnover")
    br = rt.with_live(dl.breadth_df(), "breadth")
    fv = rt.with_live(dl.flows_vn(), "flows_vn")
    val = dl.load("valuation_wide")
    is_live = "live" in to.attrs
    live = to[(to["Phiên"] == "Đang giao dịch")]
    to_c = to[(to["Phiên"] == "Đã đóng cửa")]
    last = to_c.index.max()
    v = val[val.code == "VNINDEX"].sort_values("date")
    pe_last, pb_last = v.pe.dropna().iloc[-1], v.pb.dropna().iloc[-1]
    if is_live:                                   # KPI = hom nay (LIVE), so sanh voi phien dong cua truoc
        ts = to.attrs["live"]["ts"]
        vni = to["VN-Index"].dropna()
        g = to["Toàn thị trường"]
        f_last = fv["KN ròng toàn TT"].dropna()
        br_c = br
        ma20 = to["MA20 toàn TT"].dropna().iloc[-1] if to["MA20 toàn TT"].notna().any() else np.nan
        ratio = rt.ratio_for_index("VNINDEX")
        if pd.notna(ratio):
            pe_last, pb_last = pe_last * ratio, pb_last * ratio
        tag = f"LIVE {ts:%H:%M:%S}"
    else:
        vni = to_c["VN-Index"].dropna()
        g = to_c["Toàn thị trường"]
        f_last = fv.loc[fv.index <= last, "KN ròng toàn TT"].dropna()
        br_c = br[br.index <= last]
        ma20 = to_c["MA20 toàn TT"].iloc[-1]
        tag = f"phiên {last:%d/%m}"
    chg = (vni.iloc[-1] / vni.iloc[-2] - 1) * 100 if len(vni) > 1 else np.nan
    if is_live:                                   # ±% theo tham chieu cua feed (lich su co the thieu phien gan nhat)
        il = rt.index_today()
        if "VNINDEX" in il.index and pd.notna(il.loc["VNINDEX", "change_pct"]):
            chg = float(il.loc["VNINDEX", "change_pct"])
    gma = (g.iloc[-1] / ma20 - 1) * 100 if pd.notna(ma20) else np.nan
    ui.kpi_strip([
        ("VN-Index", ui.fmt_vn(vni.iloc[-1], 2), f"{ui.fmt_vn(chg, 2, dau=True)}% {tag}", np.sign(chg) if pd.notna(chg) else 0),
        ("GTGD (tỷ)" + (" hôm nay" if is_live else ""), ui.fmt_vn(g.iloc[-1], 0), f"{ui.fmt_vn(gma, 0, dau=True)}% so MA20", np.sign(gma) if pd.notna(gma) else 0),
        ("Khối ngoại ròng (tỷ)", ui.fmt_vn(f_last.iloc[-1], 0) if len(f_last) else "—",
         f"20 phiên: {ui.fmt_vn(f_last.tail(20).sum(), 0, dau=True)}" if len(f_last) else "", np.sign(f_last.iloc[-1]) if len(f_last) else 0),
        ("% mã trên MA200", ui.fmt_vn(br_c["% mã trên MA200"].iloc[-1], 1) + "%", f"MA50: {ui.fmt_vn(br_c['% mã trên MA50'].iloc[-1], 0)}%", 0),
        ("% mã tăng (phiên)", ui.fmt_vn(br_c["% mã tăng"].iloc[-1], 0) + "%", f"Tăng − giảm: {int(br_c['Tăng - Giảm'].iloc[-1]):+d}", np.sign(br_c["Tăng - Giảm"].iloc[-1])),
        ("P/E VN-Index" + (" (live)" if is_live else ""), ui.fmt_vn(pe_last, 2), f"P/B {ui.fmt_vn(pb_last, 2)}", 0),
    ])
    if not live.empty and not is_live:
        r = live.iloc[-1]
        ui.callout(f"Phiên {live.index[-1]:%d/%m} đang giao dịch — VN-Index {ui.fmt_vn(r['VN-Index'], 2)}, GTGD tạm tính "
                   f"{ui.fmt_vn(r['Toàn thị trường'], 0)} tỷ (chưa hết phiên).")
    to_v = to if is_live else to_c
    ui.h2("Thị trường")
    a, b = st.columns(2)
    with a:
        with ui.card("VN-Index", "điểm", key="tq_vni", default="1Y", compact=True) as c:
            d = c.cut(to_v[["VN-Index"]])
            c.chart(ui.fig_line(d, "điểm", hover_nd=2), d, ten="VN-Index", height=300)
        with ui.card("Độ rộng: % cổ phiếu trên MA", "% số mã", key="tq_breadth", default="1Y", compact=True) as c:
            d = c.cut(br[["% mã trên MA50", "% mã trên MA200"]])
            fig = ui.fig_line(d, "%", zero=True, hover_nd=1)
            if fig is not None:
                ui.add_hline(fig, 50, color=ui.TOK["gray"])
            c.chart(fig, d, ten="Do rong tren MA", height=300)
    with b:
        with ui.card("Giá trị giao dịch toàn thị trường", "tỷ đồng", key="tq_gtgd", default="1Y", compact=True) as c:
            d = c.cut(to_v[["Toàn thị trường", "MA20 toàn TT", "MA50 toàn TT"]])
            c.chart(ui.fig_bars(d, "Toàn thị trường", "tỷ đồng", sign=False, lines=["MA20 toàn TT", "MA50 toàn TT"], hover_nd=0), d, ten="GTGD", height=300)
        with ui.card("Khối ngoại mua/bán ròng", "tỷ đồng", key="tq_kn", default="1Y", compact=True) as c:
            d = c.cut(fv[["KN ròng toàn TT"]])
            c.chart(ui.fig_bars(d, "KN ròng toàn TT", "tỷ đồng", sign=True, hover_nd=0), d, ten="Khoi ngoai rong", height=300)
    ui.h2("Tình trạng dữ liệu")
    fr = ctx["fresh"]
    with ui.card("Độ tươi của các bộ dữ liệu", f"{len(fr)} bộ · REGISTRY trong datalib.py", key="tq_fresh", controls=False) as c:
        if fr is None or fr.empty:
            c.empty()
        else:
            t = fr.copy()
            t["Dữ liệu đến"] = pd.to_datetime(t["Dữ liệu đến"]).dt.strftime("%d/%m/%Y")
            t["Cập nhật lúc"] = pd.to_datetime(t["Cập nhật lúc"]).dt.strftime("%d/%m %H:%M")
            cols = ["Dataset", "Nhóm", "Nguồn", "Trạng thái", "Dữ liệu đến", "Trễ (ngày)", "Số dòng", "Cập nhật lúc", "Mô tả"]
            t = t[[x for x in cols if x in t.columns]].set_index("Dataset")
            c.table(t, ten="Tinh trang du lieu", height=min(620, 40 + 35 * len(t)))
    with st.expander("⚙️ Dữ liệu: xoá cache / chạy pipeline"):
        c1, c2 = st.columns([1, 3])
        if c1.button("🔄 Xoá cache, nạp lại file", width="stretch"):
            st.cache_data.clear()
            st.rerun()
        slot = c2.selectbox("Slot Run-Market.ps1", ["PM", "AM"], key="slot")
        if c2.button("▶️ Cập nhật dữ liệu (có mạng, vài phút)", width="stretch"):
            cmd = ["powershell", "-NoProfile", "-File", os.path.join(dl.BASE, "Run-Market.ps1"), "-Slot", slot]
            with st.spinner("Đang chạy Run-Market.ps1 ..."):
                r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
            st.code((r.stdout or "")[-3000:] or "(không có output)")
            st.cache_data.clear()


# ============================================================== KHO DU LIEU
def kho_du_lieu(ctx):
    ui.h2("Kho dữ liệu — xem & lọc bất kỳ bảng nào")
    keys = sorted(dl.REGISTRY, key=lambda k: (dl.KHOI_THU_TU.get(dl.REGISTRY[k][1].split(" · ")[0], 9), dl.REGISTRY[k][1], dl.REGISTRY[k][0]))
    key = st.selectbox("Dataset", keys, key="kho_ds", format_func=lambda k: f"{dl.REGISTRY[k][1]}  ·  {dl.REGISTRY[k][0]}")
    ten, nhom, path, dcol, ecol, mota = dl.REGISTRY[key]
    with ui.card(ten, nhom, help=mota, key=f"kho_{key}", default="1Y") as c:
        lf = dl.live_first(key)
        ui.note(f"{mota} · <code>{path}</code> · <b>Nguồn: {'live-first (' + dl.src.DATASETS[dl.SRC_KEYS[key]][1] + ')' if lf else 'pipeline'}</b>"
                + (" — hàng cùng ngày lấy từ nguồn live-first, lịch sử pipeline nối phía trước" if lf else ""))
        d = dl.tv() if key == "tv_history" else dl.load(key)
        if key == "nso_monthly":
            nhom_tx = st.selectbox("Nhóm chỉ tiêu", list(dl.NHOM_NSO_TX), key="kho_nso_nhom")
            d = d[d.group.isin(dl.NHOM_NSO_TX[nhom_tx])]
        if ecol and ecol in d:
            ents = sorted(d[ecol].dropna().unique().tolist())
            pick = st.multiselect(f"Lọc {ecol}", ents, default=ents[:5] if len(ents) > 5 else ents, key=f"kho_pick_{key}")
            if pick:
                d = d[d[ecol].isin(pick)]
        if dcol in d and key not in ("nso", "nso_monthly"):
            dd = pd.to_datetime(d[dcol], errors="coerce")
            d = d[(dd >= c.d0) & (dd <= c.d1)]
        st.write(f"**{len(d):,} dòng × {d.shape[1]} cột**".replace(",", "."))
        numc = [x for x in d.columns if pd.api.types.is_numeric_dtype(d[x])]
        if numc and ecol and ecol in d and dcol in d:
            vcol = st.selectbox("Vẽ cột", numc, key=f"kho_col_{key}")
            p = d.pivot_table(index=dcol, columns=ecol, values=vcol, aggfunc="last")
            p.index = pd.to_datetime(p.index, errors="coerce")
            p = p[p.index.notna()].sort_index()
            p.index.name = "Ngày"
            with c.body():
                fig = ui.fig_line(p, vcol)
                if fig is not None:
                    st.plotly_chart(fig, width="stretch", config=ui.PLOTLY_CONFIG)
        c.table(d.tail(500).iloc[::-1].set_index(d.columns[0]), ten=f"Data_{key}", height=420)


# ================================================================ XUAT EXCEL
def xuat_excel(ctx):
    ui.h2("Xuất Excel nhiều bảng")
    with ui.card("Chọn bảng → 1 file Excel nhiều sheet", "cột đầu là ngày; quét vùng rồi Insert > Chart", key="xl", default="1Y") as c:
        d0, d1 = c.d0, c.d1
        months = c.months

        def cut(df):
            return c.cut(df)
        CHON = {
            "Giá trị giao dịch VN (ngày)": lambda: cut(dl.turnover_df()),
            "Chỉ số VN (đóng cửa)": lambda: cut(dx.index_close(list(dx.VN_INDEX_TEN))),
            "Khối ngoại VN (ngày)": lambda: cut(dl.flows_vn()),
            "Khối ngoại châu Á (tháng, USD)": lambda: dl.flows_region_df(d0, d1),
            "Độ rộng thị trường": lambda: cut(dl.breadth_df()),
            "Dưới MA50/200/300": lambda: cut(dl.breadth_df())[[x for x in dl.breadth_df().columns if "MA50" in x or "MA200" in x or "MA300" in x]],
            "Vốn hoá nhóm quy mô": lambda: dl.sectors(since=d0.strftime("%Y-%m-%d"), end=d1.strftime("%Y-%m-%d"))[1],
            "Chỉ số ngành (rebase 100)": lambda: dl.sectors(since=d0.strftime("%Y-%m-%d"), end=d1.strftime("%Y-%m-%d"))[0],
            "Tổng kết ngành": lambda: dl.sector_summary(months=months, end=d1),
            "Hiệu suất ngành 1D…5Y": lambda: dx.sector_returns(ctx["last"]),
            "Tăng trưởng EPS toàn TT": lambda: cut(dl.eps_market_df().pivot_table(index="Ngày", columns="code", values="Tăng trưởng EPS (%)", aggfunc="last")),
            "Định giá thị trường VN (P/E)": lambda: cut(dl.load("valuation_wide").pivot_table(index="date", columns="code", values="pe", aggfunc="last")),
            "Thanh khoản khu vực (USD)": lambda: cut(dl.load("indices").pivot_table(index="date", columns="index_code", values="value_usd", aggfunc="last")),
            "Tài khoản NĐT (VSDC)": lambda: cut(dx.vsdc_new()),
            "CPI theo nhóm hàng (yoy)": lambda: cut(dl.cpi_nso("YOY")),
            "Tỷ giá & dự trữ": lambda: cut(dl.tm(["fx_central", "fx_vcb_sell", "fx_free_sell", "fx_reserves", "fx_import_cover"])),
            "Lãi suất & OMO": lambda: cut(dl.tm(["ib_on", "ib_1w", "ib_1m", "ib_3m", "policy_refinance", "omo_net_outstanding", "deposit_12m_avg"])),
            "Xuất nhập khẩu": lambda: cut(dl.trade_nso()),
        }
        pick = st.multiselect("Bảng", list(CHON), default=list(CHON)[:6], key="xl_pick")
        if st.button("📦 Tạo file Excel", type="primary"):
            with st.spinner("Đang dựng ..."):
                sheets = {}
                for i, k in enumerate(pick):
                    try:
                        sheets[f"{i + 1:02d}_{k[:26]}"] = CHON[k]()
                    except Exception as e:  # noqa: BLE001
                        st.warning(f"{k}: {e}")
                if sheets:
                    st.session_state["xlsx"] = dl.to_excel(sheets)
                    st.session_state["xlsx_n"] = len(sheets)
        if "xlsx" in st.session_state:
            st.success(f"Đã dựng {st.session_state['xlsx_n']} sheet.")
            st.download_button("⤓ Tải file Excel", st.session_state["xlsx"], file_name=f"MarketData_{date.today():%Y%m%d}.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")
    with ui.card("Chart Pack (file Excel có sẵn biểu đồ)", "", key="chartpack", controls=False) as c:
        cp = os.path.join(dl.BASE, "chart-pack", "Chart_Pack_TTCK.xlsx")
        if os.path.exists(cp):
            c1, c2 = st.columns([1, 2])
            if c1.button("🔁 Cập nhật sheet GTGD trong Chart Pack"):
                r = subprocess.run([sys.executable, os.path.join(dl.BASE, "chart-pack", "add_sheet.py")], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
                st.code((r.stdout or "") + (r.stderr or "")[-800:])
            ui.note(f"<code>{cp}</code> — cập nhật {pd.Timestamp(os.path.getmtime(cp), unit='s'):%d/%m %H:%M}")
            with open(cp, "rb") as f:
                c2.download_button("⤓ Tải Chart Pack", f.read(), file_name="Chart_Pack_TTCK.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        else:
            c.empty("Chưa có Chart_Pack_TTCK.xlsx", f"Chạy chart-pack để tạo file tại {cp}")


# ========================================================== CK THE GIOI
def ck_the_gioi(ctx, nav):
    idx = dl.load("indices")
    TEN = {"VNINDEX": "VN-Index", "KOSPI": "KOSPI", "TAIEX": "TAIEX", "SET": "SET", "JCI": "JCI", "SSEC": "Shanghai", "N225": "Nikkei 225",
           "SP500": "S&P 500", "NASDAQ": "Nasdaq", "DJI": "Dow Jones", "HSI": "Hang Seng", "CSI300": "CSI 300", "FBMKLCI": "KLCI", "KOSDAQ": "KOSDAQ"}
    codes_all = sorted(idx.index_code.unique())
    if nav == "chi-so":
        ui.h2("Chỉ số")
        with ui.card("Hiệu suất chỉ số thế giới", "rebase 100 đầu kỳ", help="indices-master: VN + châu Á + Mỹ.", key="tg_rebase",
                     chips=codes_all, chip_default=["VNINDEX", "KOSPI", "TAIEX", "SET", "JCI", "SSEC", "N225", "SP500"], chip_multi=True,
                     chip_fmt=lambda k: TEN.get(k, k), default="YTD") as c:
            p = idx[idx.index_code.isin(c.chip)].pivot_table(index="date", columns="index_code", values="close", aggfunc="last")
            p.columns = [TEN.get(x, x) for x in p.columns]
            p.index.name = "Ngày"
            p = c.cut(rt.with_live(p, "world_close"))
            d = rt.mark_live(ui.rebase100(p), p)
            fig = ui.fig_line(d, "rebase 100", hover_nd=1)
            if fig is not None:
                ui.add_hline(fig, 100, color=ui.TOK["gray"])
            c.chart(fig, d, ten="Chi so the gioi rebase 100")
        with ui.card("Hiệu suất chỉ số theo nhiều khung", "%", help="Biến động giá đóng cửa đến phiên gần nhất của mỗi chỉ số.", key="tg_perf", controls=False) as c:
            p = idx.pivot_table(index="date", columns="index_code", values="close", aggfunc="last").sort_index().ffill(limit=10)

            def _perf(p):
                END = p.index.max()
                out = pd.DataFrame(index=p.columns)
                for h in dx.HORIZONS:
                    p0 = dx._p_at(p, END, h)
                    out[h] = (p.loc[END] / p0 - 1) * 100 if p0 is not None else np.nan
                out.index = [TEN.get(x, x) for x in out.index]
                out.index.name = "Chỉ số"
                return out.round(2)
            out_hist = _perf(p)
            p2 = rt.with_live(p, "world_close")
            if "live" in p2.attrs:                 # chi VN-Index co hang hom nay; chi so khac giu gia cuoi (ffill)
                p2 = p2.ffill(limit=1)
                out = _perf(p2)
                c.table(out, ten="Hieu suat chi so the gioi", html=True, pct_cols=dx.HORIZONS, df_export=out_hist, live_ts=p2.attrs["live"]["ts"])
                ui.note("Hàng hôm nay chỉ có VN-Index live; các chỉ số khác dùng giá đóng cửa gần nhất.")
            else:
                c.table(out_hist, ten="Hieu suat chi so the gioi", html=True, pct_cols=dx.HORIZONS)
    elif nav == "thanh-khoan":
        ui.h2("Thanh khoản")
        with ui.card("Giá trị giao dịch quy USD", "triệu USD / phiên, bình quân 20 phiên", help="indices-master.value_usd.", key="tg_liq",
                     chips=sorted(idx[idx.value_usd.notna()].index_code.unique()), chip_default=["VNINDEX", "KOSPI", "TAIEX", "SET", "JCI", "FBMKLCI"],
                     chip_multi=True, chip_fmt=lambda k: TEN.get(k, k), default="1Y") as c:
            v = idx[idx.index_code.isin(c.chip)].pivot_table(index="date", columns="index_code", values="value_usd", aggfunc="last")
            v.columns = [TEN.get(x, x) for x in v.columns]
            v.index.name = "Ngày"
            d = c.cut(v.rolling(20).mean())
            c.chart(ui.fig_line(d, "triệu USD", zero=True, hover_nd=0), d, ten="Thanh khoan USD")
    elif nav == "khoi-ngoai":
        ui.h2("Khối ngoại")
        with ui.card("Khối ngoại mua/bán ròng theo tháng", "triệu USD", help="7 thị trường (VN, Hàn, Đài, Indo, Thái, Malaysia), quy USD.", key="tg_kn",
                     toggles={"Hiển thị": ["Theo tháng", "Luỹ kế"]}, default="1Y") as c:
            fr = dl.flows_region_df(c.d0, c.d1)
            fr.index = pd.to_datetime(fr.index, format="%m/%Y")
            fr.index.name = "Tháng"
            d = fr.cumsum() if c.toggle["Hiển thị"] == "Luỹ kế" else fr
            fig = ui.fig_line(d, "triệu USD", zero=True, hover_nd=0, colors={"Việt Nam (HOSE)": ui.TOK["orange"], "EM Châu Á (tổng)": ui.TOK["ink"]})
            c.chart(fig, d, ten="Khoi ngoai khu vuc")
    else:
        ui.h2("Định giá")
        vr = dl.load("valuation_region_wide")
        cds = sorted(vr.code.unique())
        with ui.card("Định giá thị trường khu vực", "lần", help="P/E, P/B 12 thị trường (TradingView, SET, SSE, JPX, MSCI).", key="tg_val",
                     chips=cds, chip_default=[x for x in ["TV_VN", "TV_KR", "TV_TW", "TV_TH", "TV_ID", "TV_CN"] if x in cds], chip_multi=True,
                     toggles={"Chỉ tiêu": ["P/E", "P/B", "ROE"]}, default="3Y") as c:
            ct = {"P/E": "pe", "P/B": "pb", "ROE": "roe_ttm"}[c.toggle["Chỉ tiêu"]]
            p = vr[vr.code.isin(c.chip)].pivot_table(index="date", columns="code", values=ct, aggfunc="last")
            p.index.name = "Ngày"
            d = c.cut(p * (100 if ct == "roe_ttm" else 1))
            c.chart(ui.fig_line(d, "%" if ct == "roe_ttm" else "lần", hover_nd=2), d, ten=f"{c.toggle['Chỉ tiêu']} khu vuc")
        with ui.card("Snapshot định giá mới nhất", "", key="tg_snap", controls=False) as c:
            snap = vr.sort_values("date").groupby("code").last()[["date", "pe", "pb", "roe_ttm", "div_yield", "marketcap"]]
            snap["date"] = pd.to_datetime(snap["date"]).dt.strftime("%d/%m/%Y")
            c.table(snap.sort_values("pe").round(2), ten="Snapshot dinh gia khu vuc")


# =============================================================== TRAI PHIEU
def _bond_filter(b0, key):
    nam_min, nam_max = int(b0.nam_ph.min()), int(b0.nam_ph.max())
    with st.expander("Bộ lọc (năm phát hành, loại, ngành, CTCK bảo lãnh) — mặc định toàn thị trường", expanded=False):
        f1, f2, f3 = st.columns([2, 1.3, 1.3])
        nam = f1.slider("Năm phát hành", nam_min, nam_max, (max(nam_min, 2017), nam_max), key=f"{key}_nam")
        loai = f2.multiselect("Loại", ["Riêng lẻ trong nước", "Quốc tế (USD)"], default=["Riêng lẻ trong nước", "Quốc tế (USD)"], key=f"{key}_loai")
        ng = f3.multiselect("Ngành", dl.NGANH_TP, default=[], key=f"{key}_ng")
        g1, g2 = st.columns(2)
        top_ctck = b0.groupby("ctck_bao_lanh").gia_tri_ty.sum().sort_values(ascending=False)
        ctck = g1.multiselect("CTCK bảo lãnh / thu xếp", list(top_ctck.index), default=[], key=f"{key}_ctck")
        tc = g2.multiselect("Độ tin cậy CTCK", ["cao", "kha", "thap", "proxy"], default=[], key=f"{key}_tc")
    b = b0[(b0.nam_ph >= nam[0]) & (b0.nam_ph <= nam[1]) & b0.loai.isin(loai or list(b0.loai.unique()))]
    if ng:
        b = b[b.nganh.isin(ng)]
    if ctck:
        b = b[b.ctck_bao_lanh.isin(ctck)]
    if tc:
        b = b[b.do_tin_cay.isin(tc)]
    return b if len(b) else b0


def trai_phieu(ctx, nav):
    LAST = ctx["last"]
    if nav == "gia-loi-suat":
        return _duong_cong(ctx)
    b0 = dl.bonds_df()
    b = _bond_filter(b0, nav)
    ls_all = dl.lai_suat_bq(b.assign(k=1), "k")
    ui.kpi_strip([
        ("Số lô TP", f"{len(b):,}".replace(",", "."), "", 0),
        ("Giá trị phát hành", f"{ui.fmt_vn(b.gia_tri_ty.sum() / 1e3, 0)} ngh.tỷ", "", 0),
        ("Đang lưu hành", f"{ui.fmt_vn(b.gia_tri_luu_hanh_ty.sum() / 1e3, 0)} ngh.tỷ", "", 0),
        ("Đã mua lại", f"{ui.fmt_vn(b.gt_mua_lai_luy_ke_ty.sum() / 1e3, 0)} ngh.tỷ", "", 0),
        ("Lãi suất BQ gia quyền", f"{ui.fmt_vn(ls_all.iloc[0], 2)}%" if len(ls_all) else "—", "", 0),
        ("Tổ chức phát hành", f"{b.to_chuc_phat_hanh.nunique():,}".replace(",", "."), "", 0),
    ])
    nam_max = int(b0.nam_ph.max())
    if nav == "phat-hanh":
        ui.h2("Quy mô phát hành")
        with ui.card("Giá trị phát hành theo năm: app so với VBMA", "tỷ đồng", help="HNX CBIS chỉ có phát hành riêng lẻ trong nước (+ TP USD quy đổi); "
                     "phần ra công chúng lấy từ báo cáo VBMA. ◆ = tổng trong nước theo VBMA.", key="tp_nam", controls=False) as c:
            full = b0[b0.nam_ph.between(2019, nam_max)]
            app_nam = full.pivot_table(index="nam_ph", columns="loai", values="gia_tri_ty", aggfunc="sum").reindex(columns=["Riêng lẻ trong nước", "Quốc tế (USD)"])
            vb = dl.VBMA_NAM.set_index("Năm")
            dd = pd.DataFrame({"Riêng lẻ trong nước (app)": app_nam["Riêng lẻ trong nước"], "Ra công chúng (VBMA)": vb["VBMA công chúng"],
                               "Trái phiếu USD (app, quy đổi)": app_nam["Quốc tế (USD)"]}).fillna(0)
            dd = dd[dd.index.notna()]
            dd.index = dd.index.astype(int).astype(str)
            dd.index.name = "Năm"
            fig = ui.fig_stack(dd, "tỷ đồng", colors={"Riêng lẻ trong nước (app)": ui.TOK["orange"], "Ra công chúng (VBMA)": ui.TOK["gray"],
                                                    "Trái phiếu USD (app, quy đổi)": ui.TOK["orange_light"]})
            vt = vb[["VBMA tổng trong nước"]].dropna()
            vt.index = vt.index.astype(int).astype(str)
            vt = vt[vt.index.isin(dd.index)]
            if fig is not None and len(vt):
                fig.add_trace(go.Scatter(x=vt.index, y=vt["VBMA tổng trong nước"], mode="markers", name="VBMA tổng trong nước",
                                         marker=dict(symbol="diamond", size=12, color=ui.TOK["ink"]), hovertemplate="%{y:,.0f}<extra>VBMA tổng</extra>"))
            bang = pd.DataFrame({"App riêng lẻ (tỷ)": app_nam["Riêng lẻ trong nước"], "VBMA riêng lẻ (tỷ)": vb["VBMA riêng lẻ"]})
            bang["Chênh app – VBMA (%)"] = (bang["App riêng lẻ (tỷ)"] / bang["VBMA riêng lẻ (tỷ)"] - 1) * 100
            bang["VBMA công chúng (tỷ)"] = vb["VBMA công chúng"]
            bang["VBMA tổng trong nước (tỷ)"] = vb["VBMA tổng trong nước"]
            bang = bang.loc[bang.index.isin(range(2021, nam_max + 1))].round(1)
            bang.index.name = "Năm"
            c.chart(fig, dd, last=b0.ngay_phat_hanh.max(), ten="Phat hanh theo nam")
            with c.body():
                st.dataframe(bang, width="stretch")
        with ui.card("Phát hành theo quý", "tỷ đồng", help="Theo bộ lọc hiện tại; chồng theo loại.", key="tp_quy", periods=["3Y", "5Y", "All"], default="5Y") as c:
            q = b.pivot_table(index="quy_ph", columns="loai", values="gia_tri_ty", aggfunc="sum").fillna(0)
            q.index = pd.PeriodIndex(q.index, freq="Q").to_timestamp()
            q.index.name = "Quý"
            d = c.cut(q)
            c.chart(ui.fig_stack(d, "tỷ đồng", colors={"Riêng lẻ trong nước": ui.TOK["orange"], "Quốc tế (USD)": ui.TOK["gray"]}), d, ten="Phat hanh theo quy")
        ui.h2("Đáo hạn & tổ chức")
        with ui.card("Áp lực đáo hạn phần đang lưu hành", "tỷ đồng", help="Giá trị còn lưu hành theo năm đáo hạn, 10 năm tới, chồng theo ngành.", key="tp_daohan", controls=False) as c:
            dhn = (b[(b.gia_tri_luu_hanh_ty > 0) & (b.nam_dh >= LAST.year) & (b.nam_dh <= LAST.year + 10)]
                   .pivot_table(index="nam_dh", columns="nganh", values="gia_tri_luu_hanh_ty", aggfunc="sum").reindex(columns=dl.NGANH_TP).fillna(0))
            dhn = dhn.loc[:, dhn.sum() > 0]
            dhn.index = dhn.index.astype(int).astype(str)
            dhn.index.name = "Năm"
            c.chart(ui.fig_stack(dhn, "tỷ đồng"), dhn, last=b0.ngay_phat_hanh.max(), ten="Dao han theo nganh")
        a1, a2 = st.columns(2)
        with a1:
            with ui.card("Top hệ sinh thái theo giá trị phát hành", "tỷ đồng", key="tp_hst", controls=False) as c:
                top = b.groupby("parent_group").gia_tri_ty.sum().sort_values(ascending=False).head(15)
                c.chart(ui.fig_hbar(top, "tỷ đồng", sign=False, nd=0), top.to_frame("tỷ"), last=b0.ngay_phat_hanh.max(), ten="Top he sinh thai")
        with a2:
            with ui.card("Top CTCK bảo lãnh / thu xếp", "tỷ đồng, độ tin cậy cao/khá", key="tp_ctck", controls=False) as c:
                tc_ok = b[b.do_tin_cay.isin(["cao", "kha"])]
                src = tc_ok if len(tc_ok) else b
                topc = src.groupby("ctck_bao_lanh").gia_tri_ty.sum().sort_values(ascending=False).head(15)
                c.chart(ui.fig_hbar(topc, "tỷ đồng", sign=False, color=ui.TOK["brown"], nd=0), topc.to_frame("tỷ"), last=b0.ngay_phat_hanh.max(), ten="Top CTCK")
        with ui.card("Chi tiết từng lô", "500 lô gần nhất theo bộ lọc", key="tp_chitiet", controls=False) as c:
            cot = ["ma_tp", "to_chuc_phat_hanh", "ma_ck", "parent_group", "nganh", "loai", "ngay_phat_hanh", "ngay_dao_han", "gia_tri_ty",
                   "gia_tri_luu_hanh_ty", "lai_suat", "ky_han", "tinh_trang", "ctck_bao_lanh", "do_tin_cay"]
            ct = b[[x for x in cot if x in b]].sort_values("ngay_phat_hanh", ascending=False)
            c.table(ct.head(500).set_index("ma_tp"), ten="Trai phieu chi tiet", height=420)
    else:
        ui.h2("Cơ cấu theo ngành")
        with ui.card("Cơ cấu phát hành theo ngành", "tỷ đồng", help="9 ngành kiểu VBMA do pipeline gán (classify_issuers.py).", key="tp_nganh",
                     toggles={"Hiển thị": ["Giá trị", "Tỷ trọng"]}, controls=False) as c:
            cn = b.pivot_table(index="nam_ph", columns="nganh", values="gia_tri_ty", aggfunc="sum").reindex(columns=dl.NGANH_TP).fillna(0)
            cn = cn.loc[:, cn.sum() > 0]
            cn.index = cn.index.astype(int).astype(str)
            cn.index.name = "Năm"
            c.chart(ui.fig_stack(cn, "tỷ đồng", normalize=c.toggle["Hiển thị"] == "Tỷ trọng"), cn, last=b0.ngay_phat_hanh.max(), ten="Co cau nganh")
            ty = (cn.div(cn.sum(axis=1), axis=0) * 100).round(1)
            rows = []
            for y, v in dl.VBMA_NGANH.items():
                if str(y) in ty.index:
                    for k, pct in v.items():
                        rows.append({"Năm": y, "Ngành": k, "App (%)": ty.loc[str(y), k] if k in ty else np.nan, "VBMA (%)": pct})
            if rows:
                ui.note("Đối chiếu VBMA (riêng lẻ): " + " · ".join(f"{r['Năm']} {r['Ngành']} app {ui.fmt_vn(r['App (%)'], 1)}% / VBMA {ui.fmt_vn(r['VBMA (%)'], 1)}%" for r in rows))
        ui.h2("Lãi suất phát hành")
        with ui.card("Lãi suất phát hành bình quân gia quyền", "%/năm", help="Gia quyền theo giá trị phát hành; ◆ = VBMA toàn thị trường (năm).", key="tp_ls",
                     chips=dl.NGANH_TP, chip_default=["Ngân hàng", "Bất động sản"], chip_multi=True, toggles={"Tần suất": ["Quý", "Năm"]}, controls=False) as c:
            cot_t = "quy_ph" if c.toggle["Tần suất"] == "Quý" else "nam_ph"
            parts = [dl.lai_suat_bq(b, cot_t).rename("Toàn thị trường")]
            for g in c.chip:
                parts.append(dl.lai_suat_bq(b[b.nganh == g], cot_t).rename(g))
            ls = pd.concat(parts, axis=1)
            ls.index = ls.index.astype(int).astype(str) if cot_t == "nam_ph" else ls.index.astype(str)
            ls.index.name = "Kỳ"
            fig = ui.fig_line(ls, "%/năm", hover_nd=2, markers=True, colors={"Toàn thị trường": ui.TOK["ink"]})
            if fig is not None:
                fig.update_xaxes(type="category")
                if cot_t == "nam_ph":
                    vbl = dl.VBMA_NAM[["Năm", "VBMA LS BQ (%)"]].dropna()
                    vbl["Kỳ"] = vbl["Năm"].astype(int).astype(str)
                    vbl = vbl[vbl["Kỳ"].isin(ls.index)]
                    fig.add_trace(go.Scatter(x=vbl["Kỳ"], y=vbl["VBMA LS BQ (%)"], mode="markers", name="VBMA toàn TT",
                                             marker=dict(symbol="diamond", size=12, color=ui.TOK["down"])))
            c.chart(fig, ls.round(2), last=b0.ngay_phat_hanh.max(), ten="Lai suat phat hanh BQ")
        with ui.card("Từng lô phát hành: lãi suất theo thời gian", "%/năm, bong bóng = giá trị", help="Tối đa 3.000 lô lớn nhất theo bộ lọc.",
                     key="tp_bubble", controls=False) as c:
            sc = b[b.lai_suat.notna() & (b.lai_suat > 0) & (b.gia_tri_ty > 0)].copy()
            if len(sc) > 3000:
                sc = sc.nlargest(3000, "gia_tri_ty")
            sc = sc.rename(columns={"ngay_phat_hanh": "Ngày phát hành", "lai_suat": "Lãi suất", "gia_tri_ty": "Giá trị (tỷ)", "nganh": "Ngành"})
            fig = ui.fig_bubble(sc, "Ngày phát hành", "Lãi suất", "Giá trị (tỷ)", "Ngành", text="to_chuc_phat_hanh", unit="%/năm", ylim=[0, 18])
            c.chart(fig, sc[["ma_tp", "to_chuc_phat_hanh", "Ngành", "Ngày phát hành", "Lãi suất", "Giá trị (tỷ)", "ky_han"]].set_index("ma_tp"),
                    last=b0.ngay_phat_hanh.max(), ten="Lai suat tung lo")
        with ui.card("Lãi suất BQ gia quyền theo năm × ngành", "%/năm", key="tp_ls_bang", controls=False) as c:
            bang_ls = b[b.lai_suat.notna() & (b.lai_suat > 0) & (b.gia_tri_ty > 0)]
            piv = bang_ls.groupby(["nam_ph", "nganh"]).apply(lambda x: np.average(x.lai_suat, weights=x.gia_tri_ty)).unstack().reindex(columns=dl.NGANH_TP)
            piv["Toàn thị trường"] = dl.lai_suat_bq(bang_ls, "nam_ph")
            piv.index = piv.index.astype(int)
            piv.index.name = "Năm"
            c.table(piv.round(2).iloc[::-1], ten="Lai suat nam x nganh")


@st.cache_data(show_spinner="Đang dựng đường cong lợi suất ...")
def _duong_cong_cache(as_of, window, tin_cay, min_bond, mt):
    return dl.duong_cong(pd.Timestamp(as_of).date(), window, tin_cay, min_bond)


def _duong_cong(ctx):
    ui.callout("Giá giao dịch <b>sàn TPDN riêng lẻ HNX</b> (từ 19/07/2023, giá gộp) → YTM từng giao dịch → đường cong theo ngành tại as-of và 1/3/6/12 tháng "
               "trước. YTM bucket = bình quân gia quyền theo giá trị lô, đã cắt điểm phân tán (1,5·IQR).")
    yall = dl.bond_yields_prepared("thap")
    if yall.empty:
        ui.card_empty("Đường cong lợi suất TPDN", "", "Chưa có bond_yields.csv — chạy pipeline bonds.", key="yc_none")
        return
    d_last = yall.d.max().date()
    k1, k2, k3, k4 = st.columns([1.2, 1, 1.4, 0.8])
    as_of = k1.date_input("As-of", value=d_last, min_value=yall.d.min().date(), max_value=d_last, format="DD/MM/YYYY", key="yc_asof")
    window = k2.selectbox("Cửa sổ (ngày GD trước mốc)", [20, 30, 45, 60, 90], index=1, key="yc_win")
    tin_cay = k3.selectbox("Độ tin cậy YTM tối thiểu", ["kha", "cao", "thap"], index=0, key="yc_tc",
                           format_func=lambda v: {"cao": "cao — chỉ lãi cố định", "kha": "cao + kha (mặc định)", "thap": "tất cả"}[v])
    min_bond = k4.number_input("Tối thiểu bond/bucket", 2, 10, 3, key="yc_minb")
    long, fit, charts, wide = _duong_cong_cache(str(as_of), int(window), tin_cay, int(min_bond), dl._mtime(dl.REGISTRY["bond_yields"][2]))
    if long.empty:
        ui.card_empty("Đường cong lợi suất TPDN", "", "Không đủ giao dịch trong cửa sổ đã chọn.", key="yc_none2")
        return
    yc = dl._yc()
    MOC_NHAN = {m: ("Hiện tại" if m == "0M" else m + " trước") + " (%s)" % pd.Timestamp(d).strftime("%d/%m/%y")
                for m, d in long.drop_duplicates("moc").set_index("moc").ngay_moc.items()}
    MAU = {"12M": "#f0c9a8", "6M": "#e9ad7c", "3M": "#ed7d31", "1M": "#b3551c", "0M": "#7a4a2a"}
    long["Mốc"] = long.moc.map(MOC_NHAN)

    def _curve_fig(nganh):
        sub = long[long.nganh == nganh].sort_values("ky_han_tb")
        if sub.empty:
            return None
        fig = go.Figure()
        for m, _ in yc.MOC:
            if m in charts.get(nganh, {}):
                g, tpc, d_moc = charts[nganh][m]
                fig.add_trace(go.Scatter(x=g.ttm_nam, y=g.ytm, mode="markers", name=MOC_NHAN[m], legendgroup=m, showlegend=False,
                                         marker=dict(color=MAU[m], opacity=0.3, size=np.clip(np.sqrt(g.w_lo.fillna(1)) * 1.2, 4, 22)),
                                         text=g.ma_gd + " — " + g.to_chuc_phat_hanh.astype(str).str[:40],
                                         hovertemplate="%{text}<br>Kỳ hạn %{x:.2f}N · YTM %{y:.2f}%<extra></extra>"))
        for m, _ in yc.MOC:
            s = sub[sub.moc == m]
            if len(s):
                fig.add_trace(go.Scatter(x=s.ky_han_tb, y=s.ytm, mode="lines+markers", name=MOC_NHAN[m], legendgroup=m,
                                         line=dict(color=MAU[m], width=2.2), marker=dict(size=7),
                                         customdata=np.stack([s.n_bond, s.spread_bps.fillna(0)], axis=1),
                                         hovertemplate="%{x:.2f}N · YTM %{y:.2f}% · %{customdata[0]} bond · spread %{customdata[1]:.0f} bps<extra>" + MOC_NHAN[m] + "</extra>"))
        m0 = charts.get(nganh, {}).get("0M")
        if m0 and m0[1]:
            tpc = pd.DataFrame({"x": m0[1][0], "y": m0[1][1]})
            tpc = tpc[(tpc.x >= 0.1) & (tpc.x <= 20)]
            fig.add_trace(go.Scatter(x=tpc.x, y=tpc.y, mode="lines", name="TPCP spot (as-of)", line=dict(color=ui.TOK["ink2"], width=1.5, dash="dash"),
                                     hovertemplate="%{x:.2f}N · %{y:.2f}%<extra>TPCP</extra>"))
        ylo = max(0.0, float(sub.ytm.min()) - 3)
        fig.update_layout(height=360, hovermode="closest", xaxis=dict(type="log", range=[np.log10(0.1), np.log10(20)], title="Kỳ hạn còn lại (năm)",
                                                                       tickvals=[0.25, 0.5, 1, 2, 3, 5, 7, 10, 15], ticktext=["0,25", "0,5", "1", "2", "3", "5", "7", "10", "15"]),
                          yaxis=dict(title="YTM (%/năm)", range=[ylo, float(sub.ytm.max()) + 3]))
        return fig

    ui.h2("Đường cong theo ngành")
    nganh_co = [n for n in [yc.TOAN_TT, yc.TRU_NH] + dl.NGANH_TP if n in set(long.nganh)]
    chon = st.multiselect("Ngành", nganh_co, default=nganh_co[:4], key="yc_nganh")
    ui.note("Chấm = từng bond trong cửa sổ (kích thước ~ giá trị lô); đường = YTM bình quân gia quyền theo bucket kỳ hạn; nét đứt = spot TPCP. Nhạt → đậm = 12M trước → hiện tại.")
    for i in range(0, len(chon), 2):
        cols = st.columns(2)
        for j, ng in enumerate(chon[i:i + 2]):
            with cols[j]:
                with ui.card(ng, "YTM %/năm", key=f"yc_{ui.slug(ng)}", controls=False) as c:
                    sub = long[long.nganh == ng]
                    c.chart(_curve_fig(ng), sub.set_index("ngay_moc")[["moc", "ky_han", "ky_han_tb", "n_bond", "ytm", "ytm_median", "spread_bps"]],
                            last=pd.Timestamp(as_of), ten=f"Duong cong {ng}")
    ui.h2("Bảng dịch chuyển")
    with ui.card("YTM bình quân gia quyền theo ngành × bucket kỳ hạn", "% và thay đổi (bps) so với các mốc", key="yc_wide", controls=False) as c:
        c.table(wide.set_index(["nganh", "ky_han"]), ten="Dich chuyen duong cong")
        if len(fit):
            fw = fit.pivot_table(index=["nganh", "ky_han_nam"], columns="moc", values="ytm_fit")
            fw = fw.reindex(columns=[m for m, _ in yc.MOC if m in fw.columns])
            with c.body():
                st.markdown("**Tại kỳ hạn chuẩn (nội suy giữa các bucket)**")
                st.dataframe(fw.round(2), width="stretch")
    ui.h2("Giá & YTM từng mã")
    gan = yall[yall.d >= pd.Timestamp(as_of) - pd.Timedelta(days=90)]
    top = gan.groupby("ma_gd").gt_ty.sum().sort_values(ascending=False)
    ten_ma = yall.drop_duplicates("ma_gd").set_index("ma_gd").to_chuc_phat_hanh
    ma = st.selectbox("Mã trái phiếu (sắp theo GTGD 90 ngày)", list(top.index), format_func=lambda m: "%s — %s" % (m, str(ten_ma.get(m, ""))[:60]), key="yc_ma")
    h = yall[yall.ma_gd == ma].sort_values("d").set_index("d")
    info = h.iloc[-1]
    ui.kpi_strip([("Ngành", str(info.nganh), "", 0), ("Lãi suất PH", f"{ui.fmt_vn(info.lai_suat, 2)}%", "", 0),
                  ("Đáo hạn", pd.Timestamp(info.ngay_dao_han).strftime("%d/%m/%Y") if pd.notna(info.ngay_dao_han) else "—", "", 0),
                  ("Giá BQ gần nhất", f"{ui.fmt_vn(info.gia_bq_pct, 1)}% MG", "", 0), ("YTM gần nhất", f"{ui.fmt_vn(info.ytm, 2)}%", "", 0),
                  ("Độ tin cậy", str(info.do_tin_cay_ytm), str(info.loai_lai_suat) if pd.notna(info.loai_lai_suat) else "", 0)])
    ser = h[["gia_bq_pct", "ytm", "spread_bps"]].rename(columns={"gia_bq_pct": "Giá BQ (% mệnh giá)", "ytm": "YTM (%)", "spread_bps": "Spread (bps)"})
    ser.index.name = "Ngày"
    a1, a2 = st.columns(2)
    with a1:
        with ui.card(f"{ma} — giá bình quân ngày", "% mệnh giá (giá gộp)", key="yc_gia", controls=False) as c:
            c.chart(ui.fig_line(ser[["Giá BQ (% mệnh giá)"]], "% MG", hover_nd=1, markers=True), ser, ten=f"{ma} gia", height=300)
    with a2:
        with ui.card(f"{ma} — YTM theo ngày", "%/năm", key="yc_ytm", controls=False) as c:
            c.chart(ui.fig_line(ser[["YTM (%)"]], "%/năm", hover_nd=2, markers=True), ser, ten=f"{ma} YTM", height=300)
    with ui.card(f"{ma} — giao dịch", "300 giao dịch gần nhất", key="yc_bang_ma", controls=False) as c:
        bang_ma = h[["ma_gd", "kl", "gt_ty", "gia_bq_pct", "gia_cuoi_pct", "ytm", "ytm_gia_cuoi", "tpcp_spot", "spread_bps", "ttm_nam", "mo_hinh_cf", "do_tin_cay_ytm"]].iloc[::-1]
        c.table(bang_ma.head(300), ten=f"{ma} giao dich", height=360)
    ui.h2("TPCP benchmark")
    tp = dl.load("tpcp_curve")
    with ui.card("Đường cong spot TPCP tại các mốc", "%/năm", key="yc_tpcp", controls=False) as c:
        if tp.empty:
            c.empty()
        else:
            moc_ngay = long.drop_duplicates("moc").set_index("moc").ngay_moc
            tps = tp.assign(ngay=tp.ngay.dt.strftime("%Y-%m-%d"))
            out = {}
            for m, _ in yc.MOC:
                if m in moc_ngay:
                    tpc = yc.tpcp_curve_on(tps, pd.Timestamp(moc_ngay[m]).date())
                    if tpc:
                        out[MOC_NHAN[m]] = pd.Series(tpc[1], index=[f"{x:g}N" for x in tpc[0]])
            d = pd.DataFrame(out)
            d.index.name = "Kỳ hạn"
            fig = ui.fig_line(d, "%/năm", hover_nd=2, markers=True, colors={MOC_NHAN[m]: MAU[m] for m in MAU if m in MOC_NHAN})
            if fig is not None:
                fig.update_xaxes(type="category")
            c.chart(fig, d.round(3), last=pd.Timestamp(as_of), ten="TPCP cac moc")
    with ui.card("Spot TPCP theo thời gian", "%/năm", key="yc_tpcp_ts", default="1Y") as c:
        ky = c.cut(dx.tpcp_series())
        c.chart(ui.fig_line(ky, "%/năm", hover_nd=2), ky, ten="TPCP spot chuoi", height=300)


# ================================================================== TIN TUC
def tin_tuc(ctx):
    ui.h2("Tin tức")
    ui.card_empty("Tin tức thị trường", "", "Chuyên mục đang được xây dựng — chưa có nguồn tin tức trong hệ thống.", key="tin_tuc")
    fr = ctx["fresh"]
    with ui.card("Dữ liệu vừa cập nhật", "bộ dữ liệu có số liệu mới trong 7 ngày", key="tin_data", controls=False) as c:
        if fr is None or fr.empty:
            c.empty()
        else:
            t = fr.copy()
            t["Cập nhật lúc"] = pd.to_datetime(t["Cập nhật lúc"])
            t = t[t["Cập nhật lúc"] >= pd.Timestamp.now() - pd.Timedelta(days=7)].sort_values("Cập nhật lúc", ascending=False)
            t["Cập nhật lúc"] = t["Cập nhật lúc"].dt.strftime("%d/%m %H:%M")
            t["Dữ liệu đến"] = pd.to_datetime(t["Dữ liệu đến"]).dt.strftime("%d/%m/%Y")
            c.table(t[["Dataset", "Dữ liệu đến", "Cập nhật lúc", "Trạng thái"]].set_index("Dataset"), ten="Du lieu vua cap nhat")
