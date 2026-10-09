# -*- coding: utf-8 -*-
r"""
MARKET DATA APP - giao dien moi theo mau "Genea" (09/10/2026): nen be sang, dieu huong 3 cap tren dau
trang, the bieu do trang bo goc, mau cam #ed7d31. Khao sat + quy tac dung: design\genea-ui-spec.md.

Chay:   D:\market-data\app\Chay-app.bat      (hoac: python -m streamlit run app.py --server.port 8765)
Deep-link: ?trang=<section>/<sub>/<nav>, vd ?trang=ttck/vn/dong-tien, ?trang=vi-mo/viet-nam/gia-ca
(cac slug cu ?trang=vimo | vn | trai-phieu | kho | excel | khu-vuc van mo dung trang).

Cau truc: app.py (khung + dieu huong) · ui_genea.py (theme, the, chart Plotly) · data_ext.py (du lieu bo sung)
          pages_ck.py (TTCK Viet Nam) · pages_vimo.py (Vi mo VN + the gioi) · pages_khac.py (Tong quan, CK the gioi,
          Trai phieu, Tin tuc, Kho du lieu, Xuat Excel) · datalib.py (lop du lieu, giu nguyen) · app_legacy.py (giao dien cu).
"""
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalib as dl  # noqa: E402
import ui_genea as ui  # noqa: E402

st.set_page_config(page_title="Market Data", page_icon="◆", layout="wide", initial_sidebar_state="collapsed")
ui.inject_css()

# ------------------------------------------------------------ CAY DIEU HUONG
NAV = {
    "tong-quan": ("Tổng quan", {
        "tong-quan": ("Tổng quan", {}),
        "kho": ("Kho dữ liệu", {}),
        "excel": ("Xuất Excel", {}),
    }),
    "ttck": ("Thị trường chứng khoán", {
        "vn": ("Chứng khoán Việt Nam", {"hieu-suat": "Hiệu suất", "dong-tien": "Dòng tiền",
                                        "dinh-gia": "Định giá", "nha-dau-tu": "Nhà đầu tư"}),
        "the-gioi": ("Chứng khoán thế giới", {"chi-so": "Chỉ số", "thanh-khoan": "Thanh khoản",
                                               "khoi-ngoai": "Khối ngoại", "dinh-gia": "Định giá"}),
        "trai-phieu": ("Trái phiếu", {"phat-hanh": "Phát hành", "co-cau": "Cơ cấu & lãi suất",
                                      "gia-loi-suat": "Giá & đường cong lợi suất"}),
    }),
    "vi-mo": ("Vĩ mô", {
        "viet-nam": ("Vĩ mô Việt Nam", {
            "tang-truong": "Tăng trưởng & sản xuất", "gia-ca": "Giá cả", "lai-suat": "Lãi suất & tiền tệ",
            "he-thong-tai-chinh": "Hệ thống tài chính", "tai-khoa": "Tài khoá", "ty-gia": "Tỷ giá",
            "du-tru": "Dự trữ ngoại hối", "thuong-mai": "Thương mại & CCTT", "fdi": "Đầu tư nước ngoài"}),
        "the-gioi": ("Vĩ mô thế giới", {"ty-gia": "Tỷ giá", "lai-suat": "Lãi suất", "gia-ca": "Chỉ số giá",
                                         "tang-truong": "Tăng trưởng & lao động"}),
    }),
    "tin-tuc": ("Tin tức", {}),
}
# slug cu cua app_legacy -> duong dan moi
CU = {"vimo": "vi-mo/viet-nam/tang-truong", "vn": "ttck/vn/hieu-suat", "khu-vuc": "ttck/the-gioi/chi-so",
      "trai-phieu": "ttck/trai-phieu/phat-hanh", "kho": "tong-quan/kho", "excel": "tong-quan/excel",
      "chart": "ttck/vn/hieu-suat", "tong-quan": "tong-quan/tong-quan"}


def _doc_query():
    """Doc ?trang= 1 lan dau phien -> dat trang thai dieu huong."""
    if st.session_state.get("_nav_init"):
        return
    st.session_state["_nav_init"] = True
    q = st.query_params.get("trang") or ""
    q = CU.get(q, q)
    parts = [p for p in q.split("/") if p]
    if not parts or parts[0] not in NAV:
        return
    sec = parts[0]
    ui.set_nav("nav_sec", sec)
    subs = NAV[sec][1]
    if len(parts) > 1 and parts[1] in subs:
        ui.set_nav(f"nav_sub_{sec}", parts[1])
        navs = subs[parts[1]][1]
        if len(parts) > 2 and parts[2] in navs:
            ui.set_nav(f"nav_nav_{sec}_{parts[1]}", parts[2])


_doc_query()

# ------------------------------------------------------------ DU LIEU CHUNG
try:
    LAST = dl.last_session()
except Exception:  # noqa: BLE001
    LAST = pd.Timestamp.now().normalize()
ui.set_data_end(LAST)
try:
    FRESH = dl.freshness_df()
    _fr = FRESH.copy()
    _fr["Dữ liệu đến"] = pd.to_datetime(_fr["Dữ liệu đến"]).dt.strftime("%d/%m/%Y")
    NGUON = _fr[["Dataset", "Nhóm", "Trạng thái", "Dữ liệu đến", "Trễ (ngày)"]]
except Exception:  # noqa: BLE001
    FRESH, NGUON = pd.DataFrame(), None

# ------------------------------------------------------------------ HEADER
ui.header(NGUON, len(dl.REGISTRY))

# ----------------------------------------------------------- DIEU HUONG 3 CAP
SEC = ui.nav(list(NAV), "nav_sec", default="tong-quan", kind="pills", fmt=lambda k: NAV[k][0])
subs = NAV[SEC][1]
SUB = NAVK = None
with st.container(border=True, key="khung_noi_dung"):
    if subs:
        SUB = ui.nav(list(subs), f"nav_sub_{SEC}", kind="subtab", fmt=lambda k: subs[k][0])
        navs = subs[SUB][1]
        if navs:
            NAVK = ui.nav(list(navs), f"nav_nav_{SEC}_{SUB}", kind="segment", fmt=lambda k: navs[k])
    st.query_params["trang"] = "/".join(p for p in (SEC, SUB, NAVK) if p)

    ctx = {"last": LAST, "fresh": FRESH}
    if SEC == "tong-quan":
        import pages_khac as pk
        {"tong-quan": pk.tong_quan, "kho": pk.kho_du_lieu, "excel": pk.xuat_excel}[SUB](ctx)
    elif SEC == "ttck":
        if SUB == "vn":
            import pages_ck as pc
            {"hieu-suat": pc.hieu_suat, "dong-tien": pc.dong_tien, "dinh-gia": pc.dinh_gia,
             "nha-dau-tu": pc.nha_dau_tu}[NAVK](ctx)
        elif SUB == "the-gioi":
            import pages_khac as pk
            pk.ck_the_gioi(ctx, NAVK)
        else:
            import pages_khac as pk
            pk.trai_phieu(ctx, NAVK)
    elif SEC == "vi-mo":
        import pages_vimo as pv
        if SUB == "viet-nam":
            pv.viet_nam(ctx, NAVK)
        else:
            pv.the_gioi(ctx, NAVK)
    else:
        import pages_khac as pk
        pk.tin_tuc(ctx)

st.markdown(f'<div class="gn-note" style="margin-top:10px">Phiên gần nhất: {LAST:%d/%m/%Y} · '
            f'Dữ liệu đọc từ <code>{dl.BASE}</code> · Giao diện cũ: <code>app_legacy.py</code></div>',
            unsafe_allow_html=True)
