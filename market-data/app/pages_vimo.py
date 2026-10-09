# -*- coding: utf-8 -*-
"""
pages_vimo.py - Vi mo › Vi mo Viet Nam (9 navtab) + Vi mo the gioi (4 navtab).
So lieu: datalib.tm (SBV / FRED / CBTT qua transmission-wide), datalib.nm / cpi_nso / gdp_nso / trade_nso / fdi_nso
(Cuc Thong ke), datalib.mv (IMF), data_ext (TPCP, CAR, NSNN).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import datalib as dl
import data_ext as dx
import ui_genea as ui

PM = ui.PERIODS_MACRO
tm, nm = dl.tm, dl.nm


def _tm(ids):
    try:
        return tm(ids)
    except Exception:  # noqa: BLE001
        return pd.DataFrame()


# ===================================================================== VIET NAM
def viet_nam(ctx, nav):
    {"tang-truong": _tang_truong, "gia-ca": _gia_ca, "lai-suat": _lai_suat, "he-thong-tai-chinh": _he_thong,
     "tai-khoa": _tai_khoa, "ty-gia": _ty_gia, "du-tru": _du_tru, "thuong-mai": _thuong_mai, "fdi": _fdi}[nav](ctx)


def _tang_truong(ctx):
    ui.h2("Tăng trưởng")
    with ui.card("Tăng trưởng GDP", "% so cùng kỳ, giá so sánh", help="Cục Thống kê: tăng trưởng GDP thực (giá so sánh) theo quý (từ 2000) "
                 "hoặc theo năm; cột = tổng số, đường = 3 khu vực kinh tế.", key="gdp_yoy", toggles={"Tần suất": ["Quý", "Năm"]},
                 periods=PM, default="10Y") as c:
        g = dl.gdp_nso("YOY_Q") if c.toggle["Tần suất"] == "Quý" else dx.gdp_year()
        kv = [x for x in dl.GDP_NGANH if x in g.columns and x != "Thuế sản phẩm trừ trợ cấp sản phẩm"]
        d = c.cut(g[kv]) if kv else pd.DataFrame()
        if d.empty:
            c.empty()
        else:
            lines = [x for x in kv if x != "Tổng số"]
            fig = ui.fig_bars(d, "Tổng số", "%", sign=False, color=ui.TOK["orange_light"], lines=lines, hover_nd=2,
                              line_colors=dict(zip(lines, [ui.TOK["brown"], ui.TOK["gray"], ui.TOK["tan"]])))
            if fig is not None:
                fig.update_layout(showlegend=True)
            last = d["Tổng số"].dropna()
            c.chart(fig, d, ten="Tang truong GDP",
                    note_text=f"Kỳ gần nhất {last.index[-1]:%m/%Y}: {ui.fmt_vn(last.iloc[-1], 2)}% (số NSO giá so sánh; chưa có GDP danh nghĩa yoy)" if len(last) else None)
    with ui.card("Cơ cấu GDP theo khu vực sản xuất", "% GDP giá hiện hành, theo quý", help="Tỷ trọng 3 khu vực + thuế sản phẩm trong GDP giá hiện hành.",
                 key="gdp_cocau", periods=PM, default="5Y") as c:
        d = c.cut(dx.gdp_sector_share())
        c.chart(ui.fig_stack(d, "%", normalize=True), d.round(2), ten="Co cau GDP")
    ui.card_empty("GDP phía chi tiêu (tiêu dùng, đầu tư, xuất khẩu ròng)", "% GDP, năm", "Chưa có bảng GDP theo phương pháp sử dụng trong nso_monthly; "
                  "có thể thêm từ niên giám PX-Web (Tài khoản quốc gia).", key="gdp_chitieu")

    ui.h2("Sản xuất & tiêu dùng")
    with ui.card("Chỉ số sản xuất công nghiệp (IIP)", "%", help="Toàn ngành công nghiệp: so cùng kỳ (IMF đến 2022, NSO từ 2023) và so tháng trước.",
                 key="iip", toggles={"Chỉ tiêu": ["So cùng kỳ", "So tháng trước", "Theo ngành"]}, periods=PM, default="5Y") as c:
        if c.toggle["Chỉ tiêu"] == "Theo ngành":
            iip = nm("IIP", "YOY", pct=True)
            ng = [x for x in iip.columns if x != "Toàn ngành công nghiệp"]
            mac = [x for x in ("Công nghiệp chế biến, chế tạo", "Khai khoáng", "Sản xuất và phân phối điện") if x in ng]
            chon = st.multiselect("Ngành", ng, default=mac, key="iip_ng")
            d = c.cut(iip[chon or mac])
            c.chart(ui.fig_line(d, "%", zero=True, hover_nd=1), d, ten="IIP theo nganh")
        else:
            col = c.toggle["Chỉ tiêu"]
            d = c.cut(dl.iip_nso()[[col]])
            c.chart(ui.fig_bars(d, col, "%", sign=True, hover_nd=1), d, ten=f"IIP {col}")
    ui.card_empty("PMI sản xuất Việt Nam", "điểm", "Chưa có nguồn PMI (S&P Global) trong hệ thống.", key="pmi")
    with ui.card("Tổng mức bán lẻ hàng hoá & dịch vụ", "nghìn tỷ đồng / tháng", help="Cục Thống kê, theo nhóm ngành hoạt động (bán lẻ, lưu trú ăn uống, du lịch, dịch vụ khác).",
                 key="banle", toggles={"Hiển thị": ["Giá trị", "Tăng trưởng"]}, periods=PM, default="3Y") as c:
        if c.toggle["Hiển thị"] == "Giá trị":
            bl = nm("RETAIL", "LEVEL") / 1e3            # section chi gan den 2015 -> chon theo ten muc
            bl = bl[[x for x in ("Bán lẻ hàng hóa", "Dịch vụ lưu trú, ăn uống", "Du lịch lữ hành", "Dịch vụ khác") if x in bl.columns]]
            d = c.cut(bl)
            c.chart(ui.fig_stack(d, "nghìn tỷ"), d, ten="Ban le theo nhom")
        else:
            d = c.cut(nm("RETAIL", "YOY", pct=True))
            cols = [x for x in d.columns if x == "Tổng số"] + [x for x in d.columns if x != "Tổng số"][:4]
            c.chart(ui.fig_line(d[cols], "%", zero=True, hover_nd=1), d, ten="Ban le yoy")


def _gia_ca(ctx):
    ui.h2("Lạm phát")
    KIEU = {"So cùng kỳ": "YOY", "So tháng trước": "MOM", "So tháng 12": "VS_DEC"}
    with ui.card("CPI & lạm phát cơ bản", "%", help="Cục Thống kê (PX-Web 2010–2025 nối báo cáo tháng 2023–nay). Lạm phát cơ bản chỉ có từ 2023.",
                 key="cpi", toggles={"Kỳ so sánh": list(KIEU)}, periods=PM, default="5Y") as c:
        ca = dl.cpi_nso(KIEU[c.toggle["Kỳ so sánh"]])
        cot = [x for x in ("CPI chung", "Lạm phát cơ bản") if x in ca.columns]
        d = c.cut(ca[cot])
        fig = ui.fig_line(d, "%", zero=False, hover_nd=2, colors={"Lạm phát cơ bản": ui.TOK["brown"]})
        if fig is not None and KIEU[c.toggle["Kỳ so sánh"]] == "YOY":
            ui.add_hline(fig, 4, "mục tiêu 4%", color=ui.TOK["gray"])
        last = d["CPI chung"].dropna() if "CPI chung" in d else pd.Series(dtype=float)
        c.chart(fig, d, ten="CPI", note_text=f"{last.index[-1]:%m/%Y}: CPI {ui.fmt_vn(last.iloc[-1], 2)}%" if len(last) else None)
    ui.card_empty("Đóng góp của các nhóm hàng vào lạm phát", "điểm %", "Cần quyền số rổ CPI từng nhóm — chưa có trong hệ thống.", key="cpi_donggop")
    with ui.card("Lạm phát theo nhóm hàng, tháng gần nhất", "%", help="11 nhóm hàng cấp 1 (và nhóm con) theo kỳ so sánh đã chọn.",
                 key="cpi_nhom", toggles={"Kỳ so sánh": list(KIEU)}, controls=False) as c:
        ca = dl.cpi_nso(KIEU[c.toggle["Kỳ so sánh"]])
        bo = {"CPI chung", "Lạm phát cơ bản", "Chỉ số giá vàng", "Chỉ số giá đô la Mỹ"}
        nhom = [x for x in ca.columns if x not in bo]
        if not nhom:
            c.empty()
        else:
            s = ca[nhom].ffill().iloc[-1].dropna().sort_values(ascending=False)
            s.loc["CPI chung"] = ca["CPI chung"].ffill().iloc[-1] if "CPI chung" in ca else np.nan
            c.chart(ui.fig_hbar(s, "%", sign=True, highlight="CPI chung", nd=2), s.to_frame("%"), last=ca.index.max(), ten="CPI theo nhom")
    with ui.card("Chỉ số giá vàng & đô la Mỹ trong rổ CPI", "% so cùng kỳ", help="Cục Thống kê công bố cùng CPI (không phải giá SJC/thế giới).",
                 key="cpi_vang", periods=PM, default="5Y") as c:
        ca = dl.cpi_nso("YOY")
        cot = [x for x in ("Chỉ số giá vàng", "Chỉ số giá đô la Mỹ") if x in ca.columns]
        d = c.cut(ca[cot]) if cot else pd.DataFrame()
        c.chart(ui.fig_line(d, "%", zero=True, hover_nd=2), d, ten="CPI vang USD")

    ui.h2("Giá hàng hoá")
    ui.card_empty("Giá dầu Brent / WTI", "USD/thùng", "Chưa có nguồn giá hàng hoá (EIA/FRED) trong hệ thống.", key="dau")
    ui.card_empty("Giá vàng thế giới", "USD/oz", "Chưa có nguồn giá vàng thế giới trong hệ thống.", key="vang_tg")
    ui.card_empty("Giá vàng SJC mua / bán", "triệu đồng/lượng", "Chưa có nguồn giá vàng SJC trong hệ thống.", key="vang_sjc")


def _lai_suat(ctx):
    ui.h2("Lãi suất điều hành & liên ngân hàng")
    with ui.card("Lãi suất điều hành", "%/năm", help="Tái cấp vốn, tái chiết khấu (SBV) và lãi suất trúng thầu OMO 7 ngày.",
                 key="ls_dieu_hanh", periods=PM, default="5Y") as c:
        d = c.cut(_tm(["policy_refinance", "policy_rediscount", "omo_win_7d_rate"]))
        c.chart(ui.fig_line(d, "%/năm", hover_nd=2), d, ten="Lai suat dieu hanh")
    with ui.card("Lãi suất liên ngân hàng", "%/năm", help="Bình quân liên ngân hàng VND theo kỳ hạn (SBV).",
                 key="ls_lnh", chips=["ib_on", "ib_1w", "ib_2w", "ib_1m", "ib_3m", "ib_6m"], chip_default=["ib_on", "ib_1w", "ib_1m", "ib_3m"],
                 chip_multi=True, chip_fmt=lambda k: dl.TM_TEN.get(k, k).replace("LNH ", ""), periods=ui.PERIODS, default="1Y") as c:
        d = c.cut(_tm(list(c.chip)))
        c.chart(ui.fig_line(d, "%/năm", hover_nd=2), d, ten="Lai suat lien ngan hang")
    with ui.card("Lãi suất huy động theo kỳ hạn", "%/năm", help="Big4 (thấp nhất), cao nhất thị trường và bình quân (SBV / CBTT ngân hàng).",
                 key="ls_huy_dong", chips=["1m", "6m", "12m"], chip_default="12m", chip_fmt=lambda k: {"1m": "1 tháng", "6m": "6 tháng", "12m": "12 tháng"}[k],
                 periods=PM, default="3Y") as c:
        k = c.chip
        d = c.cut(_tm([f"deposit_{k}_big4", f"deposit_{k}_max", f"deposit_{k}_avg"]))
        lo, hi, mid = (dl.TM_TEN.get(f"deposit_{k}_big4", f"deposit_{k}_big4"), dl.TM_TEN.get(f"deposit_{k}_max", f"deposit_{k}_max"),
                       dl.TM_TEN.get(f"deposit_{k}_avg", f"deposit_{k}_avg"))
        fig = ui.fig_line(d, "%/năm", hover_nd=2, colors={lo: ui.TOK["gray"], hi: ui.TOK["orange_light"], mid: ui.TOK["orange"]}, markers=True)
        c.chart(fig, d, ten=f"Huy dong {k}")

    ui.h2("Thanh khoản (OMO)")
    with ui.card("Số dư OMO & tín phiếu", "tỷ đồng", help="Repo đang lưu hành (bơm), tín phiếu đang lưu hành (âm = hút) và ròng.",
                 key="omo_sodu", periods=ui.PERIODS, default="1Y") as c:
        d = c.cut(_tm(["omo_outstanding", "bill_outstanding", "omo_net_outstanding"]))
        c.chart(ui.fig_line(d, "tỷ đồng", zero=True, hover_nd=0, colors={"Bơm ròng đang lưu hành": ui.TOK["ink"]}), d, ten="So du OMO")
    with ui.card("Bơm / hút ròng theo phiên", "tỷ đồng", help="Ròng OMO trong ngày (dương = bơm); gộp tuần/tháng = cộng dồn.",
                 key="omo_rong", toggles={"Gộp": ["Phiên", "Tuần", "Tháng"]}, periods=ui.PERIODS, default="6M") as c:
        d = c.cut(_tm(["omo_net_daily"])).dropna()
        d = dx.resample_flow(d, c.toggle["Gộp"])
        c.chart(ui.fig_bars(d, d.columns[0] if len(d.columns) else None, "tỷ đồng", sign=True, hover_nd=0) if len(d) else None, d, ten="Bom hut rong")

    ui.h2("Trái phiếu Chính phủ")
    tp = dx.tpcp_series()
    with ui.card("Lợi suất TPCP", "%/năm", help="Spot rate từ đường cong HNX (bond-pivot/tpcp_curve) các kỳ hạn 1 / 2 / 5 / 10 năm.",
                 key="tpcp_ls", periods=ui.PERIODS, default="1Y") as c:
        d = c.cut(tp)
        c.chart(ui.fig_line(d, "%/năm", hover_nd=2), d, ten="Loi suat TPCP")
    with ui.card("Đường cong lợi suất TPCP theo kỳ hạn", "%/năm", help="Spot tại ngày gần nhất và 1 / 3 / 12 tháng trước.",
                 key="tpcp_curve", controls=False) as c:
        snap = dx.tpcp_snapshot(tp.index.max()) if len(tp) else pd.DataFrame()
        if snap.empty:
            c.empty()
        else:
            s = snap.copy()
            s.index = [f"{x:g}N" for x in s.index]
            fig = ui.fig_line(s, "%/năm", hover_nd=2, markers=True, colors=dict(zip(s.columns, [ui.TOK["orange"], ui.TOK["brown"], ui.TOK["gray"], ui.TOK["gray_light"]])))
            if fig is not None:
                fig.update_xaxes(type="category", title="Kỳ hạn")
            c.chart(fig, snap.round(3), last=tp.index.max(), ten="Duong cong TPCP")
    with ui.card("Độ dốc đường cong 10 năm − 1 năm", "điểm %", help="Chênh spot 10 năm trừ 1 năm; âm = đường cong đảo ngược.",
                 key="tpcp_slope", periods=ui.PERIODS, default="3Y") as c:
        if {"TPCP 10 năm", "TPCP 1 năm"} <= set(tp.columns):
            d = c.cut((tp["TPCP 10 năm"] - tp["TPCP 1 năm"]).to_frame("10Y − 1Y").dropna())
            c.chart(ui.fig_bars(d, "10Y − 1Y", "điểm %", sign=True, hover_nd=2), d, ten="Do doc TPCP")
        else:
            c.empty()


def _he_thong(ctx):
    ui.h2("An toàn hệ thống")
    with ui.card("LDR theo nhóm sở hữu", "%", help="Dư nợ cho vay / tổng tiền gửi (NHNN thống kê tháng); nét đứt = trần TT22.",
                 key="ldr", periods=PM, default="5Y") as c:
        d = _tm(["ldr_system", "ldr_soe", "ldr_jsc", "ldr_cap"])
        ren = {dl.TM_TEN.get("ldr_cap"): "Trần LDR"}
        d = c.cut(d.rename(columns=ren).rename(columns=lambda x: {"ldr_system": "Toàn hệ thống", "ldr_soe": "NHTM Nhà nước", "ldr_jsc": "NHTM cổ phần"}.get(x, x)))
        fig = ui.fig_line(d.ffill() if "Trần LDR" in d else d, "%", hover_nd=2, dash={"Trần LDR": "dash"}, colors={"Trần LDR": ui.TOK["down"]})
        c.chart(fig, d, ten="LDR")
    with ui.card("Vốn ngắn hạn cho vay trung dài hạn", "%", help="Tỷ lệ theo nhóm (NHNN); nét đứt = trần theo lộ trình.",
                 key="sfl", periods=PM, default="5Y") as c:
        d = c.cut(_tm(["sfl_system", "sfl_soe", "sfl_jsc", "sfl_cap"]))
        cap = dl.TM_TEN.get("sfl_cap")
        fig = ui.fig_line(d.ffill() if cap in d else d, "%", hover_nd=2, dash={cap: "dash"}, colors={cap: ui.TOK["down"]})
        c.chart(fig, d, ten="Von ngan han cho vay TDH")
    with ui.card("Tỷ lệ an toàn vốn (CAR)", "%", help="NHNN (TT36 2013–2019, nhóm TT41 từ 2024) và IMF FSI toàn bộ TCTD; nét đứt = tối thiểu 8%.",
                 key="car", periods=PM, default="10Y") as c:
        d = c.cut(dx.car_frame())
        fig = ui.fig_line(d, "%", hover_nd=2, markers=True)
        if fig is not None:
            ui.add_hline(fig, 8, "tối thiểu 8%")
        banks = dx.car_banks()
        c.chart(fig, d, ten="CAR", note_text=(f"CAR từng NH gần nhất: " + ", ".join(f"{k.split(' ')[0]} {ui.fmt_vn(v, 1)}%" for k, v in banks.tail(6).items()))
                if len(banks) else None)
    ui.h2("Quy mô")
    with ui.card("Quy mô tổ chức tín dụng", "triệu tỷ đồng", help="Tổng tài sản và vốn điều lệ toàn hệ thống TCTD (NHNN, tháng).",
                 key="quymo_tctd", toggles={"Hiển thị": ["Quy mô", "Tăng trưởng"]}, periods=PM, default="5Y") as c:
        d = _tm(["bank_total_assets", "bank_charter_capital"]) / 1e6
        d.columns = ["Tổng tài sản", "Vốn điều lệ"][:d.shape[1]]
        if c.toggle["Hiển thị"] == "Quy mô":
            d = c.cut(d)
            c.chart(ui.fig_line(d, "triệu tỷ", hover_nd=2), d, ten="Quy mo TCTD")
        else:
            g = pd.DataFrame({k: dl.yoy(d[k].dropna()) for k in d.columns})
            g = c.cut(g.dropna(how="all"))
            c.chart(ui.fig_line(g, "% so cùng kỳ", zero=True, hover_nd=1), g, ten="Tang truong TCTD")
    with ui.card("Nhóm ngân hàng niêm yết", "%", help="CASA, LDR theo TT22, tỷ trọng cho vay trung dài hạn (BCTC hợp nhất, quý).",
                 key="nh_niem_yet", periods=PM, default="5Y") as c:
        d = _tm(["casa_ratio", "ldr_tt22_listed", "mlt_loan_share"])
        d.columns = ["CASA", "LDR theo TT22", "Tỷ trọng cho vay trung dài hạn"][:d.shape[1]]
        d = c.cut(d)
        c.chart(ui.fig_line(d, "%", hover_nd=1, markers=True), d, ten="NH niem yet")


def _tai_khoa(ctx):
    ui.h2("Ngân sách nhà nước")
    with ui.card("Thu, chi và bội chi NSNN", "nghìn tỷ đồng, năm", help="Niên giám Cục Thống kê (PX-Web V03.13-14 thu, V03.16 chi). Bội chi = thu − chi (âm = bội chi).",
                 key="nsnn", periods=["5Y", "10Y", "All"], default="10Y") as c:
        d = dx.nsnn_annual()
        d = c.cut(d)
        if d.empty:
            c.empty()
        else:
            s = d.copy()
            s.index = s.index.year.astype(str)
            fig = ui.fig_group_bars(s, ["Tổng thu", "Tổng chi"], ["Bội chi (thu − chi)"], "nghìn tỷ", hover_nd=0,
                                    colors={"Tổng thu": ui.TOK["orange"], "Tổng chi": ui.TOK["gray"], "Bội chi (thu − chi)": ui.TOK["ink"]})
            c.chart(fig, d.round(1), ten="Thu chi NSNN")
    with ui.card("Giải ngân vốn đầu tư từ NSNN", "nghìn tỷ đồng, luỹ kế từ đầu năm", help="Báo cáo KT-XH tháng (Cục Thống kê): vốn đầu tư thực hiện từ NSNN.",
                 key="nsnn_dautu", periods=PM, default="3Y") as c:
        d = nm("NSNN", "LEVEL_YTD")
        d = c.cut(d[["Tổng số"]] / 1e3) if "Tổng số" in d else pd.DataFrame()
        c.chart(ui.fig_bars(d, "Tổng số", "nghìn tỷ", sign=False, hover_nd=1) if len(d) else None, d, ten="Giai ngan dau tu cong")
    ui.card_empty("Dự toán NSNN & tỷ lệ thực hiện", "% dự toán", "Chưa có số dự toán và thực hiện tháng của Bộ Tài chính trong hệ thống.", key="nsnn_du_toan")


def _ty_gia(ctx):
    ui.h2("Tỷ giá USD/VND")
    with ui.card("Tỷ giá USD/VND", "VND/USD", help="Trung tâm (SBV), VCB bán, chợ đen bán; nét đứt = trần/sàn biên độ ±5%.",
                 key="fx", periods=ui.PERIODS, default="1Y") as c:
        d = c.cut(_tm(["fx_central", "fx_vcb_sell", "fx_free_sell", "fx_band_ceiling", "fx_band_floor"]))
        tr, sa = dl.TM_TEN["fx_band_ceiling"], dl.TM_TEN["fx_band_floor"]
        fig = ui.fig_line(d, "VND/USD", hover_nd=0, dash={tr: "dash", sa: "dash"}, colors={tr: ui.TOK["gray_light"], sa: ui.TOK["gray_light"], dl.TM_TEN["fx_free_sell"]: ui.TOK["brown"]})
        c.chart(fig, d, ten="Ty gia USD VND")
    with ui.card("Chênh lệch so với tỷ giá trung tâm", "%", help="(VCB bán − trung tâm) / trung tâm và (chợ đen bán − trung tâm) / trung tâm.",
                 key="fx_chenh", periods=ui.PERIODS, default="1Y") as c:
        w = _tm(["fx_central", "fx_vcb_sell", "fx_free_sell"]).ffill()
        tt = dl.TM_TEN["fx_central"]
        d = pd.DataFrame({"VCB bán": (w[dl.TM_TEN["fx_vcb_sell"]] / w[tt] - 1) * 100,
                          "Chợ đen bán": (w[dl.TM_TEN["fx_free_sell"]] / w[tt] - 1) * 100}).dropna(how="all")
        d = c.cut(d)
        fig = ui.fig_line(d, "%", hover_nd=2, colors={"Chợ đen bán": ui.TOK["brown"]})
        if fig is not None:
            ui.add_hline(fig, 5, "trần +5%")
            ui.add_hline(fig, 0, color=ui.TOK["gray"])
        c.chart(fig, d, ten="Chenh lech ty gia")


def _du_tru(ctx):
    ui.h2("Dự trữ ngoại hối")
    with ui.card("Dự trữ ngoại hối (gồm vàng)", "tỷ USD", help="IMF / SBV qua chuỗi truyền dẫn, theo tháng.", key="dutru", periods=PM, default="10Y") as c:
        d = c.cut(_tm(["fx_reserves"]) / 1e3)
        c.chart(ui.fig_line(d, "tỷ USD", zero=True, hover_nd=1), d, ten="Du tru ngoai hoi")
    with ui.card("Dự trữ tính theo tháng nhập khẩu", "tháng", help="Dự trữ / nhập khẩu bình quân tháng; mốc an toàn thông lệ 3 tháng.",
                 key="dutru_thang", periods=PM, default="10Y") as c:
        d = c.cut(_tm(["fx_import_cover"]))
        fig = ui.fig_line(d, "tháng", zero=True, hover_nd=2)
        if fig is not None:
            ui.add_hline(fig, 3, "mốc 3 tháng")
        c.chart(fig, d, ten="Thang nhap khau")
    ui.h2("Cán cân")
    with ui.card("Xuất nhập khẩu & cán cân thương mại", "tỷ USD / tháng", help="IMF đến 2022, Cục Thống kê từ 2023.", key="xnk_cc", periods=PM, default="5Y") as c:
        d = c.cut(dl.trade_nso() / 1e3)
        fig = ui.fig_bars(d, "Cán cân thương mại", "tỷ USD", sign=True, lines=["Xuất khẩu", "Nhập khẩu"], hover_nd=2,
                          line_colors={"Xuất khẩu": ui.TOK["brown"], "Nhập khẩu": ui.TOK["gray"]})
        c.chart(fig, d, ten="XNK can can")
    with ui.card("Cán cân thanh toán theo quý", "triệu USD", help="NHNN: cán cân vãng lai, tài chính, tổng thể, lỗi và sai sót.",
                 key="bop", periods=PM, default="5Y") as c:
        d = c.cut(_tm(["current_account_bop", "financial_account_bop", "bop_overall", "bop_errors"]))
        c.chart(ui.fig_group_bars(d, list(d.columns), unit="triệu USD", hover_nd=0) if len(d) else None, d, ten="Can can thanh toan")


def _thuong_mai(ctx):
    ui.h2("Thương mại hàng hoá")
    with ui.card("Xuất nhập khẩu theo tháng", "tỷ USD", help="Từng tháng hoặc luỹ kế từ đầu năm (Cục Thống kê; IMF bù lịch sử).",
                 key="xnk_thang", toggles={"Hiển thị": ["Từng tháng", "Luỹ kế"]}, periods=PM, default="3Y") as c:
        x = dl.trade_nso() / 1e3
        if c.toggle["Hiển thị"] == "Luỹ kế":
            x = x.groupby(x.index.year).cumsum()
        d = c.cut(x)
        fig = ui.fig_bars(d, "Cán cân thương mại", "tỷ USD", sign=True, lines=["Xuất khẩu", "Nhập khẩu"], hover_nd=2,
                          line_colors={"Xuất khẩu": ui.TOK["brown"], "Nhập khẩu": ui.TOK["gray"]})
        c.chart(fig, d, ten="XNK theo thang")
    with ui.card("Xuất khẩu: khu vực FDI và trong nước", "triệu USD / tháng", help="Tỷ trọng khu vực có vốn ĐTNN trong tổng xuất khẩu (Cục Thống kê).",
                 key="xk_fdi", toggles={"Hiển thị": ["Giá trị", "Tỷ trọng"]}, periods=PM, default="3Y") as c:
        xk = nm("XK", "LEVEL")
        fdi = [x for x in xk.columns if dl.nso_key(x).startswith("khuvuccovondautu")]
        tn = [x for x in xk.columns if dl.nso_key(x).startswith("khuvuckinhtetrongnuoc")]
        if not fdi:
            c.empty()
        else:
            d = pd.DataFrame({"Khu vực FDI": xk[fdi].bfill(axis=1).iloc[:, 0]})
            if tn:
                d["Khu vực trong nước"] = xk[tn].bfill(axis=1).iloc[:, 0]
            elif "Tổng số" in xk:
                d["Khu vực trong nước"] = xk["Tổng số"] - d["Khu vực FDI"]
            d = c.cut(d.dropna(how="all"))
            c.chart(ui.fig_stack(d, "triệu USD", normalize=c.toggle["Hiển thị"] == "Tỷ trọng"), d, ten="XK khu vuc FDI")
    with ui.card("Xuất khẩu theo mặt hàng, tháng gần nhất", "triệu USD", help="12 mặt hàng lớn nhất (Cục Thống kê).", key="xk_mh", controls=False) as c:
        xk = nm("XK", "LEVEL", section="mặt hàng")
        xk = xk[[x for x in xk.columns if "(lượng)" not in x]]
        if xk.empty:
            c.empty()
        else:
            s = xk.ffill().iloc[-1].dropna().sort_values(ascending=False).head(12)
            c.chart(ui.fig_hbar(s, "triệu USD", sign=False, nd=0), s.to_frame("triệu USD"), last=xk.index.max(), ten="XK mat hang")
    ui.h2("Cán cân thanh toán")
    with ui.card("Cán cân thanh toán theo quý (NHNN)", "triệu USD", help="Vãng lai, tài chính, FDI ròng, đầu tư gián tiếp ròng, tổng thể.",
                 key="bop2", periods=PM, default="5Y") as c:
        d = c.cut(_tm(["current_account_bop", "financial_account_bop", "fdi_net_bop", "fii_net_bop", "bop_overall"]))
        c.chart(ui.fig_line(d, "triệu USD", zero=True, hover_nd=0, markers=True), d, ten="BoP quy")


def _fdi(ctx):
    ui.h2("Vốn FDI")
    with ui.card("FDI đăng ký (luỹ kế từ đầu năm) & thực hiện", "triệu USD", help="Cục Thống kê: cấp mới + điều chỉnh luỹ kế; NHNN/NSO: FDI thực hiện (nghìn tỷ VND, trục phải).",
                 key="fdi_dk", periods=PM, default="5Y") as c:
        f = dl.fdi_nso()
        cot = [x for x in f.columns if "Số dự án" not in x]
        d = f[cot].copy() if cot else pd.DataFrame()
        th = _tm(["fdi_realized_vnd"])
        if len(th):
            d["FDI thực hiện (nghìn tỷ VND)"] = th.iloc[:, 0]
        d = c.cut(d.dropna(how="all"))
        c.chart(ui.fig_line(d, "triệu USD", hover_nd=0, secondary=["FDI thực hiện (nghìn tỷ VND)"]), d, ten="FDI dang ky")
    with ui.card("Số dự án cấp mới", "dự án, luỹ kế từ đầu năm", help="Cục Thống kê, theo tháng báo cáo.", key="fdi_du_an", periods=PM, default="5Y") as c:
        f = dl.fdi_nso()
        d = c.cut(f[["Số dự án cấp mới (luỹ kế)"]]) if "Số dự án cấp mới (luỹ kế)" in f else pd.DataFrame()
        c.chart(ui.fig_bars(d, "Số dự án cấp mới (luỹ kế)", "dự án", sign=False, hover_nd=0) if len(d) else None, d, ten="So du an FDI")
    with ui.card("FDI đăng ký theo ngành, kỳ gần nhất", "triệu USD, luỹ kế từ đầu năm", help="Tổng vốn đăng ký (cấp mới + điều chỉnh + góp vốn) phân theo ngành kinh tế.",
                 key="fdi_nganh", controls=False) as c:
        d = nm("FDI", "REG_TOTAL_YTD", section="ngành")
        if d.empty:
            c.empty()
        else:
            s = d.ffill().iloc[-1].dropna()
            s = s[[x for x in s.index if not str(x).startswith("Phân theo")]].sort_values(ascending=False).head(10)
            c.chart(ui.fig_hbar(s, "triệu USD", sign=False, nd=0), s.to_frame("triệu USD"), last=d.index.max(), ten="FDI theo nganh")


# ===================================================================== THE GIOI
NUOC = {"CHN": "Trung Quốc", "HKG": "Hồng Kông", "IDN": "Indonesia", "IND": "Ấn Độ", "JPN": "Nhật Bản", "KOR": "Hàn Quốc",
        "MYS": "Malaysia", "PHL": "Philippines", "SGP": "Singapore", "THA": "Thái Lan", "TWN": "Đài Loan", "VNM": "Việt Nam"}


def the_gioi(ctx, nav):
    mr = dl.load("macro_region")
    nuoc = sorted(mr.country.dropna().unique())

    def piv(series_name, chon):
        s = mr[mr.series_name == series_name]
        p = s.pivot_table(index="date", columns="country", values="value", aggfunc="last")
        p = p[[x for x in chon if x in p.columns]]
        p.columns = [NUOC.get(x, x) for x in p.columns]
        p.index.name = "Ngày"
        return p

    def region_card(title, unit, series_name, key, default_c, rebase=False, zero=False, nd=2, help=""):
        with ui.card(title, unit, help=help, key=key, chips=nuoc, chip_default=[x for x in default_c if x in nuoc], chip_multi=True,
                     chip_fmt=NUOC.get, periods=PM, default="5Y") as c:
            d = c.cut(piv(series_name, c.chip))
            if rebase:
                d = ui.rebase100(d)
            c.chart(ui.fig_line(d, unit if not rebase else "rebase 100", zero=zero, hover_nd=nd), d, ten=title)

    if nav == "ty-gia":
        ui.h2("Đồng USD")
        with ui.card("Chỉ số USD (DXY broad)", "điểm", help="FRED: chỉ số USD rộng.", key="dxy", periods=ui.PERIODS, default="3Y") as c:
            d = c.cut(_tm(["us_dxy_broad"]))
            c.chart(ui.fig_line(d, "điểm", hover_nd=1), d, ten="DXY")
        region_card("Tỷ giá nội tệ/USD các nước châu Á", "rebase 100 đầu kỳ (tăng = nội tệ mất giá)", "Ty gia noi te/USD cuoi ky", "fx_region",
                    ["VNM", "CHN", "KOR", "THA", "IDN", "JPN"], rebase=True, nd=1, help="IMF: tỷ giá cuối kỳ theo tháng, 12 nước.")
    elif nav == "lai-suat":
        ui.h2("Lãi suất USD")
        with ui.card("Lãi suất Mỹ", "%/năm", help="FRED: Fed target (trần), EFFR, SOFR, T-bill 3 tháng, UST 2 năm, 10 năm.",
                     key="us_rates", periods=PM, default="5Y") as c:
            d = c.cut(_tm(["us_fed_target_upper", "us_effr", "us_sofr", "us_tbill_3m", "us_ust_2y", "us_ust_10y"]))
            c.chart(ui.fig_line(d, "%/năm", hover_nd=2), d, ten="Lai suat My")
        with ui.card("Chênh lệch UST 10 năm − 2 năm", "điểm %", help="Độ dốc đường cong Mỹ; âm = đảo ngược.", key="us_slope", periods=PM, default="5Y") as c:
            w = _tm(["us_ust_10y", "us_ust_2y"]).ffill()
            d = c.cut((w.iloc[:, 0] - w.iloc[:, 1]).to_frame("10Y − 2Y").dropna()) if w.shape[1] == 2 else pd.DataFrame()
            c.chart(ui.fig_bars(d, "10Y − 2Y", "điểm %", sign=True, hover_nd=2) if len(d) else None, d, ten="Do doc UST")
        ui.card_empty("Lãi suất điều hành các NHTW châu Á", "%/năm", "Chưa có nguồn lãi suất điều hành khu vực (BIS) trong hệ thống.", key="asia_policy")
    elif nav == "gia-ca":
        ui.h2("Lạm phát")
        region_card("CPI so cùng kỳ 12 nước châu Á", "%", "CPI tong (chi so, 2024=100) - YoY %", "cpi_region",
                    ["VNM", "CHN", "KOR", "THA", "IDN", "JPN"], help="IMF CPI (2024=100) → so cùng kỳ.")
        region_card("CPI so tháng trước", "%", "CPI tong (chi so, 2024=100) - MoM %", "cpi_region_mom", ["VNM", "CHN", "KOR"], help="IMF, 12 nước.")
    else:
        ui.h2("Sản xuất & thương mại")
        region_card("Sản xuất công nghiệp so cùng kỳ (IIP)", "%", "IIP tang truong YoY", "iip_region", ["VNM", "CHN", "KOR", "TWN", "THA", "JPN"],
                    zero=True, nd=1, help="IMF IIP YoY, 12 nước châu Á.")
        region_card("Xuất khẩu so cùng kỳ", "%", "Xuat khau hang hoa - YoY %", "xk_region", ["VNM", "CHN", "KOR", "TWN"], zero=True, nd=1,
                    help="IMF: xuất khẩu hàng hoá YoY.")
        ui.h2("Lao động")
        ui.card_empty("Tỷ lệ thất nghiệp các nước", "%", "Chưa có nguồn lao động quốc tế (ILO/IMF WEO) trong hệ thống.", key="unemp_region")
