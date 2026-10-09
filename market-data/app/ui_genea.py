# -*- coding: utf-8 -*-
"""
ui_genea.py - lop GIAO DIEN cua Market Data App theo mau "Genea" (design/genea-ui-spec.md).

Gom: design tokens + CSS, header, dieu huong 3 cap (pills / subtab / segment), the bieu do
`card(...)` (tieu de + don vi + chip doi tuong + period + 2 o ngay + toggle + nut xuat),
template Plotly (nen trong suot, luoi #ece8e4, chu truc 11px #8c8c8c, bang mau cam/nau/xam),
cac ham ve chart dung chung (line / bars / bars_lines / stack / hbar / candle / treemap),
dinh dang so kieu Viet Nam (1.234,5) va bang % to mau xanh/do.

KHONG chua logic so lieu - so lieu lay tu datalib.py / data_ext.py.
"""
from __future__ import annotations

import io
import re
import unicodedata
from contextlib import contextmanager
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ------------------------------------------------------------------ TOKENS
TOK = {
    "bg": "#faf8f6", "surface": "#ffffff", "surface2": "#f5f2ef",
    "ink": "#262626", "ink2": "#595959", "ink3": "#8c8c8c",
    "rule": "#d9d9d9", "rule_soft": "#ece8e4",
    "orange": "#ed7d31", "orange_light": "#f4b183", "accent_text": "#b3551c",
    "accent_strong": "#c75f1e", "wash": "#fdf3ec",
    "up": "#12965a", "down": "#e23b3b", "up_soft": "#b7e4cd", "down_soft": "#f4c4c4",
    "gray": "#a6a6a6", "gray_light": "#bfbfbf",
    "brown": "#7a4a2a", "brown2": "#8b5a3c", "tan": "#c9956a",
    "danger": "#b42318", "warn": "#9c4a15",
}
# bang mau chuoi tren chart (quan sat tu trang mau): cam, nau dam, xam, cam nhat, nau nhat, nau, xam dam...
PALETTE = ["#ed7d31", "#7a4a2a", "#a6a6a6", "#f4b183", "#c9956a", "#8b5a3c", "#595959",
           "#d9d9d9", "#b3551c", "#bfbfbf", "#262626", "#f0c9a8"]
NGANH_PALETTE = PALETTE + ["#e0a37a", "#9c7b63", "#cfcfcf", "#6b3f22"]

PERIODS = ["1M", "3M", "6M", "YTD", "1Y", "3Y", "5Y", "All"]
PERIODS_MACRO = ["1Y", "3Y", "5Y", "10Y", "All"]
PERIOD_MONTHS = {"1M": 1, "3M": 3, "6M": 6, "1Y": 12, "3Y": 36, "5Y": 60, "10Y": 120}
DATA_MIN = date(2000, 1, 1)
DATA_END = date.today()          # app dat lai = phien gan nhat (set_data_end)
FONT = "Inter, system-ui, Avenir, Arial, sans-serif"
HEIGHT = 380
HAS_KALEIDO = False
try:                                  # ⧉ Anh chi khi co kaleido
    import kaleido  # noqa: F401
    HAS_KALEIDO = True
except Exception:  # noqa: BLE001
    HAS_KALEIDO = False


def set_data_end(d):
    global DATA_END
    DATA_END = pd.Timestamp(d).date()


# ---- LIVE toan app (09/10/2026): app.py dat moi lan chay; Card dung de ve dau LIVE, cat ky toi hom nay, xuat lich su
LIVE = {"active": False, "ts": None, "hist_end": None}


def set_live(active: bool, ts=None, hist_end=None):
    LIVE["active"], LIVE["ts"], LIVE["hist_end"] = bool(active), ts, hist_end


def _today():
    return pd.Timestamp(date.today())


def live_bar(state: dict, freq_key="live_freq_all", on_key="live_on", freqs=("5 s", "15 s", "60 s")):
    """Hang dieu khien LIVE duoi header: cong tac ● LIVE + tan suat + trang thai. Tra (on, freq_label)."""
    c1, c2, c3 = st.columns([1.1, 1.6, 5])
    with c1:
        on = st.toggle("● LIVE", key=on_key, help="Bật: mọi biểu đồ có điểm hôm nay cập nhật liên tục trong phiên "
                       "(mặc định bật 08:45–15:10 T2–T6). Nút tải CSV/Excel luôn chỉ xuất dữ liệu lịch sử.")
    with c2:
        f = st.segmented_control("Tần suất", list(freqs), key=freq_key, label_visibility="collapsed", disabled=not on)
    with c3:
        if on and state.get("active"):
            ts = state.get("ts")
            lag = state.get("lag")
            txt = (f'<span style="color:{TOK["up"]};font-weight:600">● LIVE</span> dữ liệu {ts:%H:%M:%S}'
                   + (f' · trễ {lag:,.0f} s' if lag is not None else "") + f' · làm mới mỗi {f or "15 s"}'
                   " · chỉ số + giá HOSE/HNX 5 s (DNSE) · UPCOM + khối ngoại theo mã 1 phút (SSI) · ○ = điểm hôm nay · tải về = lịch sử")
        elif on:
            txt = f'<span style="color:{TOK["ink3"]};font-weight:600">○ LIVE</span> chờ dữ liệu ({state.get("reason") or "—"})'
        else:
            txt = f'<span style="color:{TOK["ink3"]}">○ Live tắt</span> · dữ liệu lịch sử tới phiên gần nhất'
        st.markdown(f'<div class="gn-note" style="margin-top:9px">{txt}</div>', unsafe_allow_html=True)
    return on, f


# ---------------------------------------------------------------------- CSS
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root {
  --bg:#faf8f6; --surface:#fff; --surface-2:#f5f2ef; --ink:#262626; --ink-2:#595959; --ink-3:#8c8c8c;
  --rule:#d9d9d9; --rule-soft:#ece8e4; --accent:#ed7d31; --accent-text:#b3551c; --accent-strong:#c75f1e;
  --accent-wash:#fdf3ec; --up:#12965a; --down:#e23b3b;
  --shadow-sm:0 1px 2px #2626260f; --shadow-md:0 1px 2px #2626261a; --shadow-lg:0 6px 20px #26262629;
}
html, body, [data-testid="stAppViewContainer"], .main, [data-testid="stHeader"] {
  background: var(--bg) !important; color: var(--ink); font-family: Inter, system-ui, Avenir, Arial, sans-serif !important; }
[data-testid="stAppViewContainer"] *, [data-testid="stMarkdownContainer"] * { font-family: Inter, system-ui, Avenir, Arial, sans-serif; }
[data-testid="stSidebar"], [data-testid="collapsedControl"], [data-testid="stSidebarCollapsedControl"] { display: none !important; }
[data-testid="stHeader"] { display: none !important; }
[data-testid="stToolbar"], [data-testid="stDecoration"], #MainMenu, footer { display: none !important; }
.block-container { max-width: 1440px; padding: 14px 22px 40px 22px !important; }
h1, h2, h3, h4 { font-family: Inter, system-ui, sans-serif !important; color: var(--ink) !important; }

/* ---------- header */
.gn-head { display:flex; align-items:center; justify-content:space-between; margin: 2px 0 10px 0; }
.gn-logo { display:flex; align-items:center; gap:10px; font-size:22px; font-weight:700; color:var(--ink); }
.gn-logo .dia { width:16px; height:16px; background:var(--accent); transform:rotate(45deg); border-radius:2px; display:inline-block; }
.gn-src { font-size:13px; color:var(--ink-3); border:0.8px solid var(--rule); border-radius:999px; padding:6px 12px; background:#fff; }

/* ---------- dieu huong cap 1: vien thuoc (st.pills: button[data-variant=pills], active = aria-checked) */
[class*="st-key-nav1_"] button[data-variant="pills"] {
  border-radius: 999px !important; padding: 8px 16px !important; font-size: 13px !important; font-weight: 600 !important;
  border: 0.8px solid var(--rule) !important; background: #fff !important; color: var(--ink) !important; min-height: 0 !important; box-shadow: none !important; }
[class*="st-key-nav1_"] button[data-variant="pills"] p { font-size: 13px !important; font-weight: 600 !important; }
[class*="st-key-nav1_"] button[data-variant="pills"][aria-checked="true"] {
  background: var(--accent) !important; color: #fff !important; border-color: var(--accent) !important; }
[class*="st-key-nav1_"] button[data-variant="pills"][aria-checked="true"] p, [class*="st-key-nav1_"] button[data-variant="pills"][aria-checked="true"] * { color: #fff !important; }
[class*="st-key-nav1_"] button[data-variant="pills"]:hover { border-color: var(--accent-strong) !important; }
[class*="st-key-nav1_"] [role="radiogroup"] { gap: 8px !important; }

/* ---------- dieu huong cap 2: tab gach chan */
[class*="st-key-nav2_"] button[data-variant="pills"] {
  border: none !important; border-bottom: 2px solid transparent !important; border-radius: 0 !important;
  background: transparent !important; padding: 8px 4px !important; margin-right: 16px !important;
  font-size: 14px !important; font-weight: 600 !important; color: var(--ink) !important; box-shadow: none !important; min-height: 0 !important; }
[class*="st-key-nav2_"] button[data-variant="pills"] p { font-size: 14px !important; font-weight: 600 !important; }
[class*="st-key-nav2_"] button[data-variant="pills"][aria-checked="true"] { color: var(--accent-text) !important; border-bottom-color: var(--accent) !important; }
[class*="st-key-nav2_"] button[data-variant="pills"][aria-checked="true"] p { color: var(--accent-text) !important; }
[class*="st-key-nav2_"] { border-bottom: 0.8px solid var(--rule-soft); margin-bottom: 6px; }
[class*="st-key-nav2_"] [role="radiogroup"] { gap: 0 !important; }

/* ---------- segment (cap 3, period, toggle): st.segmented_control -> button[data-variant=segmented_control] trong khay */
[data-testid="stButtonGroup"]:has(button[data-variant="segmented_control"]) [role="radiogroup"] {
  background: var(--surface-2) !important; border-radius: 9px !important; padding: 3px !important; gap: 2px !important; border: none !important; flex-wrap: nowrap !important; }
button[data-variant="segmented_control"] {
  border: none !important; border-radius: 7px !important; padding: 5px 10px !important; font-size: 13px !important; font-weight: 600 !important;
  background: transparent !important; color: var(--ink-2) !important; box-shadow: none !important; min-height: 0 !important; margin: 0 !important; }
button[data-variant="segmented_control"] p { font-size: 13px !important; font-weight: 600 !important; }
button[data-variant="segmented_control"][aria-checked="true"] { background: #fff !important; color: var(--accent-text) !important; box-shadow: var(--shadow-md) !important; }
button[data-variant="segmented_control"][aria-checked="true"] p { color: var(--accent-text) !important; }
[class*="st-key-nav3_"] button[data-variant="segmented_control"] { padding: 7px 14px !important; }

/* ---------- chip doi tuong trong the (pills goc phai) */
[class*="st-key-chips_"] button[data-variant="pills"] {
  border-radius: 8px !important; border: 0.8px solid var(--rule) !important; background: #fff !important; color: var(--ink) !important;
  font-size: 13px !important; font-weight: 600 !important; padding: 5px 12px !important; min-height: 0 !important; box-shadow: none !important; }
[class*="st-key-chips_"] button[data-variant="pills"] p { font-size: 13px !important; font-weight: 600 !important; }
[class*="st-key-chips_"] button[data-variant="pills"][aria-checked="true"], [class*="st-key-chips_"] button[data-variant="pills"][data-selected="true"] { background: var(--accent) !important; color: #fff !important; border-color: var(--accent) !important; }
[class*="st-key-chips_"] button[data-variant="pills"][aria-checked="true"] p, [class*="st-key-chips_"] button[data-variant="pills"][data-selected="true"] p { color: #fff !important; }
[class*="st-key-chips_"] [data-testid="stButtonGroup"] { display: flex; justify-content: flex-end; }
[class*="st-key-chips_"] [role="radiogroup"] { justify-content: flex-end; gap: 6px !important; }
[class*="st-key-chips_"] [data-testid="stElementContainer"] { width: 100% !important; }
[data-testid="stButtonGroup"] { margin: 0 !important; }

/* ---------- the (card) */
[data-testid="stVerticalBlockBorderWrapper"] { background: #fff; border: 0.8px solid var(--rule-soft) !important; border-radius: 12px !important; padding: 12px 16px 14px 16px !important; }
.gn-card [data-testid="stVerticalBlockBorderWrapper"] { padding: 10px 12px !important; }
.gn-title { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; margin: 2px 0 2px 0; }
.gn-title h3 { font-size:16px !important; font-weight:700 !important; margin:0 !important; padding:0 !important; line-height:1.3; }
.gn-title .unit { font-size:13px; color:var(--ink-3); }
.gn-title .delta-up { color: var(--up); font-weight:600; } .gn-title .delta-down { color: var(--down); font-weight:600; }
.gn-title .q { display:inline-flex; width:16px; height:16px; border-radius:50%; border:1px solid var(--rule); color:var(--ink-3); font-size:11px;
  align-items:center; justify-content:center; cursor:help; }
.gn-h2 { font-size:18px; font-weight:700; text-transform:uppercase; letter-spacing:.02em; color:var(--ink); margin: 18px 0 8px 0; }
.gn-note { font-size:12.5px; color:var(--ink-3); margin: 2px 0 4px 0; }
.gn-callout { border-left: 3px solid var(--accent); padding: 4px 10px; font-size: 13px; color: var(--ink-2); background: var(--accent-wash); border-radius: 0 6px 6px 0; margin: 4px 0 8px 0; }
.gn-empty { height: 180px; display:flex; align-items:center; justify-content:center; color: var(--ink-3); font-size: 14px;
  border: 1px dashed var(--rule-soft); border-radius: 10px; background: #fcfbfa; opacity: .85; }
.gn-legend { font-size:12px; color:var(--ink-2); display:flex; gap:14px; flex-wrap:wrap; margin:2px 0 4px 0; }
.gn-legend i { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; vertical-align:-1px; }

/* o ngay, select, input */
[data-testid="stDateInput"] input, [data-testid="stSelectbox"] > div > div, [data-testid="stMultiSelect"] > div > div, [data-testid="stTextInput"] input, [data-testid="stNumberInput"] input {
  border-radius: 8px !important; font-size: 13px !important; border-color: var(--rule-soft) !important; background: #fff !important; min-height: 34px !important; }
[data-testid="stDateInput"] > div > div, [data-testid="stSelectbox"] > div, [data-testid="stMultiSelect"] > div { border-radius: 8px !important; }
[data-testid="stDateInput"] label, [data-testid="stSelectbox"] label, [data-testid="stMultiSelect"] label, [data-testid="stTextInput"] label, [data-testid="stNumberInput"] label,
[data-testid="stSegmentedControl"] label, [data-testid="stPills"] label, [data-testid="stSlider"] label, [data-testid="stRadio"] label { font-size: 12px !important; color: var(--ink-3) !important; }
/* nut xuat */
.stDownloadButton > button, .stButton > button { border: 0.8px solid var(--rule) !important; border-radius: 8px !important; background: #fff !important;
  color: var(--ink) !important; font-size: 12.5px !important; font-weight: 600 !important; padding: 4px 10px !important; min-height: 0 !important; line-height: 1.5 !important; }
.stDownloadButton > button:hover, .stButton > button:hover { border-color: var(--accent-strong) !important; color: var(--accent-strong) !important; }
.stButton > button[kind="primary"] { background: var(--accent) !important; color:#fff !important; border-color: var(--accent) !important; }
.gn-export [data-testid="stHorizontalBlock"] { justify-content: flex-end; gap: 6px; }
/* KPI */
.gn-kpis { display:grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 6px 0 14px 0; }
.gn-kpi { background:#fff; border:0.8px solid var(--rule-soft); border-radius:12px; padding:12px 14px; }
.gn-kpi .l { font-size:12px; color:var(--ink-3); font-weight:600; text-transform:uppercase; letter-spacing:.03em; }
.gn-kpi .v { font-size:22px; font-weight:700; color:var(--ink); margin-top:2px; }
.gn-kpi .d { font-size:12.5px; color:var(--ink-2); margin-top:2px; } .gn-kpi .d.up{color:var(--up)} .gn-kpi .d.down{color:var(--down)}
/* bang % */
table.gn-tbl { width:100%; border-collapse:collapse; font-size:13px; }
table.gn-tbl th { text-align:right; font-weight:600; color:var(--ink-3); font-size:12px; padding:6px 8px; border-bottom:0.8px solid var(--rule-soft); white-space:nowrap; }
table.gn-tbl th:first-child { text-align:left; }
table.gn-tbl td { text-align:right; padding:6px 8px; border-bottom:0.8px solid var(--rule-soft); font-variant-numeric: tabular-nums; white-space:nowrap; }
table.gn-tbl td:first-child { text-align:left; }
table.gn-tbl td b { font-weight:700; } table.gn-tbl td small { color:var(--ink-2); font-size:11.5px; display:block; font-weight:400; }
table.gn-tbl .up { color: var(--up); } table.gn-tbl .down { color: var(--down); } table.gn-tbl .na { color: var(--ink-3); }
table.gn-tbl tr.total td { font-weight:700; background: var(--surface-2); }
.gn-tblwrap { max-height: 520px; overflow:auto; border:0.8px solid var(--rule-soft); border-radius: 10px; }
[data-testid="stDataFrame"] { border-radius: 10px; }
[data-testid="stExpander"] { border: 0.8px solid var(--rule-soft) !important; border-radius: 10px !important; background:#fff; }
hr { border-color: var(--rule-soft) !important; }
[data-testid="stCaptionContainer"] { color: var(--ink-3) !important; }
.stAlert { border-radius: 10px; }
[data-testid="stPopover"] button, [data-testid="stPopoverButton"] { border-radius: 999px !important; font-size: 13px !important; color: var(--ink-3) !important; }
[data-testid="stPopover"] button [data-testid="stIconMaterial"], [data-testid="stExpander"] summary [data-testid="stIconMaterial"] { display: none !important; }
[data-testid="stExpander"] summary { font-size: 13px !important; color: var(--ink-2) !important; }
[data-testid="stExpander"] summary::before { content: "▸ "; color: var(--ink-3); }
</style>
"""


def inject_css():
    st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------- DINH DANG SO VN
def fmt_vn(v, nd=1, dau=False) -> str:
    """1234.5 -> '1.234,5' (kieu Viet Nam). dau=True them dau +."""
    if v is None or (isinstance(v, float) and (np.isnan(v) or np.isinf(v))) or (pd.isna(v) if not isinstance(v, str) else False):
        return "—"
    s = f"{v:+,.{nd}f}" if dau else f"{v:,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_auto(v):
    """So chu so thap phan theo do lon."""
    if v is None or pd.isna(v):
        return "—"
    a = abs(v)
    return fmt_vn(v, 2 if a < 10 else (1 if a < 1000 else 0))


def nd_cua(vals) -> int:
    v = pd.Series(vals, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna().abs()
    m = float(v.max()) if len(v) else 0.0
    return 2 if m < 10 else (1 if m < 1000 else 0)


def slug(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").replace("đ", "d").replace("Đ", "D").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "x"


def ten_file(ten: str) -> str:
    return f"{slug(ten)[:60]}_{date.today():%Y%m%d}"


# ------------------------------------------------------------------ HEADER
def header(nguon_df: pd.DataFrame | None, n_bo: int, extra: str = "", src_df: pd.DataFrame | None = None):
    """Dong 1: logo ◆ Market Data (trai) + chip 'Nguon du lieu: N bo' (phai, popover liet ke REGISTRY + do tuoi + cot Nguon
    live-first/pipeline; `extra` = dong trang thai lop nguon live-first; `src_df` = bang data_src.source_status())."""
    c1, c2 = st.columns([5, 2])
    with c1:
        st.markdown('<div class="gn-logo"><span class="dia"></span>Market Data</div>', unsafe_allow_html=True)
    with c2:
        _, p = st.columns([1, 3])
        with p:
            with st.popover(f"Nguồn dữ liệu: {n_bo} bộ ▾", width="stretch"):
                if extra:
                    st.markdown(f'<div class="gn-note">● Live-first: {extra}</div>', unsafe_allow_html=True)
                if nguon_df is not None and len(nguon_df):
                    d = nguon_df.copy()
                    st.dataframe(d, width="stretch", hide_index=True, height=min(520, 40 + 35 * len(d)))
                else:
                    st.caption("Chưa đọc được bảng tình trạng dữ liệu.")
                if src_df is not None and len(src_df):
                    st.caption("Lớp nguồn live-first (Entrade / VNDirect / EOD bộ thu) — cache `cache\\src`, cập nhật tăng dần nền")
                    st.dataframe(src_df, width="stretch", hide_index=True, height=40 + 35 * len(src_df))


# ----------------------------------------------------------- DIEU HUONG
def nav(options, key, default=None, kind="pills", fmt=None):
    """1 cap dieu huong, nho trong session_state[key]. kind: pills (cap 1), subtab (cap 2), segment (cap 3).
    Tra ve lua chon (khong bao gio None)."""
    opts = list(options)
    cur = st.session_state.get(key)
    if cur not in opts:
        cur = default if default in opts else opts[0]
        st.session_state[key] = cur
    wk = f"_w_{key}"
    if st.session_state.get(wk) not in opts:
        st.session_state[wk] = cur
    ck = {"pills": "nav1", "subtab": "nav2", "segment": "nav3"}[kind]
    with st.container(key=f"{ck}_{key}"):
        st.markdown(f"<style>.st-key-{ck}_{key} {{}}</style>", unsafe_allow_html=True)
        widget = st.segmented_control if kind == "segment" else st.pills
        val = widget("nav", opts, key=wk, label_visibility="collapsed", format_func=fmt or (lambda x: x))
    if val is None:            # bam lai nut dang chon -> Streamlit tra None: giu lua chon cu
        val = cur
        st.session_state[wk] = val
    st.session_state[key] = val
    return val


def set_nav(key, value):
    st.session_state[key] = value
    st.session_state[f"_w_{key}"] = value


def h2(text):
    st.markdown(f'<div class="gn-h2">{text}</div>', unsafe_allow_html=True)


def note(text):
    st.markdown(f'<div class="gn-note">{text}</div>', unsafe_allow_html=True)


def callout(text):
    st.markdown(f'<div class="gn-callout">{text}</div>', unsafe_allow_html=True)


def kpi_strip(items):
    """items: [(label, value_str, delta_str, sign)] sign: +1/-1/0."""
    h = ['<div class="gn-kpis">']
    for label, value, delta, sign in items:
        cls = "up" if sign and sign > 0 else ("down" if sign and sign < 0 else "")
        h.append(f'<div class="gn-kpi"><div class="l">{label}</div><div class="v">{value}</div>'
                 f'<div class="d {cls}">{delta or "&nbsp;"}</div></div>')
    h.append("</div>")
    st.markdown("".join(h), unsafe_allow_html=True)


# ----------------------------------------------------------- KY (PERIOD)
def period_dates(per: str, end=None):
    end = pd.Timestamp(end or DATA_END).date()
    if per == "YTD":
        return date(end.year - 1, 12, 31), end
    if per in ("All", None):
        return DATA_MIN, end
    m = PERIOD_MONTHS.get(per, 12)
    return (pd.Timestamp(end) - pd.DateOffset(months=m)).date(), end


def _on_per(key, end):
    per = st.session_state.get(f"per_{key}")
    if per:
        d0, d1 = period_dates(per, end)
        st.session_state[f"d0_{key}"] = d0
        st.session_state[f"d1_{key}"] = d1


def _on_date(key):
    st.session_state[f"per_{key}"] = None


class Card:
    """Doi tuong tra ve trong `with card(...) as c:` - chua lua chon (chip, ky, toggle) va ham ve."""

    def __init__(self, key, title, chip, d0, d1, toggles, slot, foot, body):
        self.key, self.title, self.chip = key, title, chip
        self.d0, self.d1 = pd.Timestamp(d0), pd.Timestamp(d1)
        self.toggle = toggles
        self._slot, self._foot, self._body = slot, foot, body
        self.months = max(1, round((self.d1 - self.d0).days / 30.44))

    # ---- cat khung thoi gian
    def cut(self, df: pd.DataFrame, keep_history=False):
        if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
            return df
        d1 = self.d1
        if LIVE["active"] and "live" in getattr(df, "attrs", {}):      # hang LIVE hom nay luon nam trong khung
            d1 = max(d1, _today())
        out = df[df.index <= d1] if keep_history else df[(df.index >= self.d0) & (df.index <= d1)]
        out.attrs = dict(df.attrs)
        return out

    # ---- ve
    def chart(self, fig, df=None, last=None, ten=None, note_text=None, height=None, legend_html=None, df_export=None):
        """Ve Plotly trong than the; nut xuat CSV/Excel (va Anh neu co kaleido) o hang dieu khien; dong 'Cap nhat lan cuoi'.
        df_export: bang de tai ve (mac dinh = df bo hang live hom nay)."""
        if fig is None:
            self.empty()
            return
        if height:
            fig.update_layout(height=height)
        _xaxis_fmt(fig, self.months)
        apply_rangebreaks(fig)
        live = (df.attrs.get("live") if df is not None and hasattr(df, "attrs") else None) if LIVE["active"] else None
        if live and isinstance(df, pd.DataFrame) and isinstance(df.index, pd.DatetimeIndex) and \
                (df.empty or pd.Timestamp(df.index.max()).normalize() != _today()):
            live = None                                      # hang hom nay da bi loai (dropna...) -> coi nhu lich su
        if live:
            add_live_marker(fig, df, live.get("ts"), live.get("src"))
        with self._body:
            if legend_html:
                st.markdown(legend_html, unsafe_allow_html=True)
            st.plotly_chart(fig, width="stretch", config=PLOTLY_CONFIG, key=f"fig_{self.key}_{abs(hash(ten or '')) % 9973}")
        self.export(df_export if df_export is not None else df, ten, fig)
        if last is None and df is not None and len(df) and isinstance(df.index, pd.DatetimeIndex):
            last = df.index.max()
        txt = []
        if live:
            hist_end = live.get("hist_end")
            ts = live.get("ts")
            src = f' ({live["src"]})' if live.get("src") else ""
            txt.append(f'<span style="color:{TOK["up"]};font-weight:600">● LIVE {ts:%H:%M:%S}{src}</span>' if ts is not None else "● LIVE")
            if hist_end is not None and pd.notna(hist_end):
                txt.append(f"lịch sử tới {pd.Timestamp(hist_end):%d/%m/%Y} · tải về không gồm live")
        elif last is not None and pd.notna(last):
            txt.append((f"Lịch sử tới {pd.Timestamp(last):%d/%m/%Y}" if LIVE["active"] else
                        f"Cập nhật lần cuối: {pd.Timestamp(last):%d/%m/%Y}"))
        if note_text:
            txt.append(note_text)
        if txt:
            with self._foot:
                st.markdown(f'<div class="gn-note">{" · ".join(txt)}</div>', unsafe_allow_html=True)

    def export(self, df, ten=None, fig=None):
        if df is None or (hasattr(df, "empty") and df.empty):
            return
        ten = ten or self.title
        help_txt = None
        live = df.attrs.get("live") if hasattr(df, "attrs") else None
        if live and isinstance(df, pd.DataFrame) and isinstance(df.index, pd.DatetimeIndex):
            df = df[df.index < _today()]                     # tai ve: CHI lich su, khong gom hang live hom nay
            he = live.get("hist_end")
            help_txt = f"Dữ liệu lịch sử tới {pd.Timestamp(he):%d/%m/%Y}, không gồm live" if he is not None and pd.notna(he) else "Không gồm live"
            if df.empty:
                return
        with self._slot:
            n = 3 if (HAS_KALEIDO and fig is not None) else 2
            cols = st.columns(n)
            csv = df.to_csv(encoding="utf-8-sig").encode("utf-8-sig") if isinstance(df, pd.DataFrame) else str(df).encode("utf-8")
            cols[0].download_button("⤓ CSV", csv, file_name=f"{ten_file(ten)}.csv", mime="text/csv",
                                    key=f"csv_{self.key}_{slug(ten)[:20]}", width="stretch", help=help_txt)
            cols[1].download_button("⤓ Excel", _xlsx(df, ten), file_name=f"{ten_file(ten)}.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    key=f"xls_{self.key}_{slug(ten)[:20]}", width="stretch", help=help_txt)
            if n == 3:
                try:
                    png = fig.to_image(format="png", scale=2)
                    cols[2].download_button("⧉ Ảnh", png, file_name=f"{ten_file(ten)}.png", mime="image/png",
                                            key=f"png_{self.key}_{slug(ten)[:20]}", width="stretch")
                except Exception:  # noqa: BLE001
                    pass

    def table(self, df, ten=None, height=None, pct_cols=None, name_col=None, html=False, total_row=None, df_export=None, live_ts=None):
        """Bang trong the: html=True ve bang % kieu Genea (Ma dam + ten nho, % xanh/do). df_export: bang tai ve (lich su);
        live_ts: bang da tinh voi gia hom nay -> ghi 'LIVE hh:mm:ss'."""
        with self._body:
            if df is None or df.empty:
                st.markdown('<div class="gn-empty">Chưa có dữ liệu</div>', unsafe_allow_html=True)
                return
            if html:
                st.markdown(html_pct_table(df, pct_cols=pct_cols, name_col=name_col, total_row=total_row),
                            unsafe_allow_html=True)
            else:
                st.dataframe(df, width="stretch", **({"height": height} if height else {}))
        self.export(df_export if df_export is not None else df, ten)
        if live_ts is not None and LIVE["active"]:
            with self._foot:
                st.markdown(f'<div class="gn-note"><span style="color:{TOK["up"]};font-weight:600">● LIVE {live_ts:%H:%M:%S}</span>'
                            ' · tính với giá hôm nay · tải về = lịch sử</div>', unsafe_allow_html=True)

    def empty(self, msg="Chưa có dữ liệu", note_text=None):
        with self._body:
            st.markdown(f'<div class="gn-empty">{msg}</div>', unsafe_allow_html=True)
        if note_text:
            with self._foot:
                st.markdown(f'<div class="gn-note">{note_text}</div>', unsafe_allow_html=True)

    def write(self, *a, **k):
        with self._body:
            st.write(*a, **k)

    def markdown(self, s):
        with self._body:
            st.markdown(s, unsafe_allow_html=True)

    def body(self):
        return self._body


def _xlsx(df, ten) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl", datetime_format="dd/mm/yyyy") as xw:
        (df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)).to_excel(xw, sheet_name=re.sub(r"[\\/*?:\[\]]", "-", str(ten))[:31] or "Sheet")
    return buf.getvalue()


@contextmanager
def card(title, unit="", help=None, key=None, chips=None, chip_default=None, chip_multi=False,
         periods=PERIODS, default="1Y", toggles=None, end=None, controls=True, subtitle_html=None,
         chip_fmt=None, chip_label="Đối tượng", compact=False):
    """The bieu do theo giai phau Genea.

    Hang 1: tieu de (H3) + don vi (nhat) + '?' (help) | chip doi tuong (pills, goc phai).
    Hang 2: period (segment) + 2 o ngay | toggle kieu chart + nut xuat (dien sau khi c.chart(...)).
    Than: `with card(...) as c:` -> c.chip, c.d0/c.d1, c.toggle[ten], c.chart(fig, df), c.table(df), c.empty().
    """
    key = key or slug(title)[:40]
    with st.container(border=True, key=f"card_{key}"):
        st.markdown(f'<style>.st-key-card_{key}{{}}</style>', unsafe_allow_html=True)
        chip = None
        if chips:
            hc1, hc2 = st.columns([2.2, 3])
        else:
            hc1, hc2 = st.container(), None
        with hc1:
            q = f'<span class="q" title="{help}">?</span>' if help else ""
            u = f'<span class="unit">{unit}</span>' if unit else ""
            st.markdown(f'<div class="gn-title"><h3>{title}</h3>{u}{subtitle_html or ""}{q}</div>', unsafe_allow_html=True)
        if chips:
            with hc2:
                with st.container(key=f"chips_{key}"):
                    wk = f"chip_{key}"
                    opts = list(chips)
                    if wk not in st.session_state:
                        st.session_state[wk] = (list(chip_default) if chip_multi and chip_default else
                                                (chip_default if chip_default in opts else (opts[:1] if chip_multi else opts[0])))
                    chip = st.pills(chip_label, opts, key=wk, selection_mode="multi" if chip_multi else "single",
                                    label_visibility="collapsed", format_func=chip_fmt or (lambda x: x))
                    if chip is None or (chip_multi and not chip):
                        chip = (list(chip_default) if chip_multi and chip_default else (chip_default or opts[0])) if not chip_multi else [opts[0]]
                        if not chip_multi:
                            chip = chip if chip in opts else opts[0]
        toggles_val, slot, foot = {}, None, None
        d0, d1 = period_dates(default, end)
        if controls:
            if f"d0_{key}" not in st.session_state:
                st.session_state[f"d0_{key}"], st.session_state[f"d1_{key}"] = d0, d1
            if f"per_{key}" not in st.session_state:
                st.session_state[f"per_{key}"] = default
            n_tog = len(toggles or {})
            w_tog = [0.55 + 0.085 * sum(len(str(o)) for o in opts) for opts in (toggles or {}).values()]
            if compact:            # the nua trang: period 1 hang, ngay + toggle + xuat hang duoi
                r1 = st.container()
                r2, r3, r4 = st.columns([1.0, 1.0, 1.4 + sum(w_tog)])
            else:
                r1, r2, r3, r4 = st.columns([3.3, 1.0, 1.0, 1.9 + sum(w_tog)])
            with r1:
                st.segmented_control("Kỳ", list(periods), key=f"per_{key}", label_visibility="collapsed",
                                     on_change=_on_per, args=(key, end))
            with r2:
                st.date_input("Từ ngày", key=f"d0_{key}", min_value=DATA_MIN, max_value=date.today(),
                              format="DD/MM/YYYY", label_visibility="collapsed", on_change=_on_date, args=(key,))
            with r3:
                st.date_input("Đến ngày", key=f"d1_{key}", min_value=DATA_MIN, max_value=date.today(),
                              format="DD/MM/YYYY", label_visibility="collapsed", on_change=_on_date, args=(key,))
            with r4:
                if toggles:
                    tcols = st.columns(w_tog + [1.5])
                    for (tname, topts), tc in zip(toggles.items(), tcols[:-1]):
                        with tc:
                            tk = f"tog_{key}_{slug(tname)}"
                            if tk not in st.session_state:
                                st.session_state[tk] = topts[0]
                            v = st.segmented_control(tname, list(topts), key=tk, label_visibility="collapsed")
                            toggles_val[tname] = v if v is not None else topts[0]
                    slot = tcols[-1].container(key=f"exp_{key}")
                else:
                    slot = st.container(key=f"exp_{key}")
            d0, d1 = st.session_state[f"d0_{key}"], st.session_state[f"d1_{key}"]
            if d0 > d1:
                d0, d1 = d1, d0
        else:
            if toggles:
                w_tog = [0.55 + 0.085 * sum(len(str(o)) for o in opts) for opts in toggles.values()]
                _, r4 = st.columns([max(0.5, 4.5 - sum(w_tog)), sum(w_tog) + 1.3])
                tcols = r4.columns(w_tog + [1.3])
                for (tname, topts), tc in zip(toggles.items(), tcols[:-1]):
                    with tc:
                        tk = f"tog_{key}_{slug(tname)}"
                        if tk not in st.session_state:
                            st.session_state[tk] = topts[0]
                        v = st.segmented_control(tname, list(topts), key=tk, label_visibility="collapsed")
                        toggles_val[tname] = v if v is not None else topts[0]
                slot = tcols[-1].container(key=f"exp_{key}")
            else:
                _, sc = st.columns([3, 1.2])
                slot = sc.container(key=f"exp_{key}")
        with slot:
            st.markdown('<div class="gn-export"></div>', unsafe_allow_html=True)
        body = st.container()
        foot = st.container()
        c = Card(key, title, chip, d0, d1, toggles_val, slot, foot, body)
        with body:
            try:
                yield c
            except Exception as e:  # noqa: BLE001 - 1 the loi khong lam chet ca trang
                st.markdown(f'<div class="gn-empty">Lỗi khi dựng thẻ: {type(e).__name__}: {str(e)[:220]}</div>',
                            unsafe_allow_html=True)


def card_empty(title, unit="", note_text="Chưa có nguồn dữ liệu trong hệ thống", key=None):
    """The 'Chua co du lieu' nhat: giu dung khung, khong bo trong."""
    with card(title, unit, key=key, controls=False) as c:
        c.empty(note_text=note_text)


# ------------------------------------------------------------ PLOTLY
def _template():
    t = go.layout.Template()
    t.layout = go.Layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=12, color=TOK["ink2"]),
        colorway=PALETTE,
        margin=dict(l=6, r=6, t=30, b=6),
        height=HEIGHT,
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#fff", bordercolor=TOK["rule"], font=dict(family=FONT, size=12, color=TOK["ink"])),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(size=12, color=TOK["ink2"]),
                    bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, zeroline=False, showline=False, tickfont=dict(size=11, color=TOK["ink3"]),
                   ticks="", linecolor=TOK["rule_soft"], automargin=True),
        yaxis=dict(showgrid=True, gridcolor=TOK["rule_soft"], gridwidth=1, zeroline=False, showline=False,
                   tickfont=dict(size=11, color=TOK["ink3"]), ticks="", automargin=True,
                   title=dict(font=dict(size=11, color=TOK["ink3"]))),
        separators=",.",
    )
    return t


pio.templates["genea"] = _template()
pio.templates.default = "genea"
PLOTLY_CONFIG = {"displaylogo": False, "responsive": True,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "zoomIn2d", "zoomOut2d"],
                 "toImageButtonOptions": {"format": "png", "scale": 2}}


def _xaxis_fmt(fig, months):
    f = "%d/%m" if months <= 3 else ("%m/%Y" if months <= 36 else "%Y")
    fig.update_xaxes(tickformat=f, hoverformat="%d/%m/%Y")
    if months > 36:
        fig.update_xaxes(dtick="M12" if months <= 180 else "M24")


def apply_rangebreaks(fig):
    """Truc ngay: an cuoi tuan + ngay le/ngay khong co du lieu (09/10/2026 PV2: bieu do dut quang vi ve ca ngay nghi).
    Chi ap cho chuoi theo NGAY (buoc giua cac moc <= 3 ngay); chuoi trong phien (<2 ngay) va chuoi thang/quy giu nguyen."""
    xs = []
    for tr in fig.data:
        x = getattr(tr, "x", None)
        if x is None or len(x) == 0:
            continue
        try:
            xi = pd.DatetimeIndex(pd.to_datetime(pd.Index(list(x)), errors="coerce")).dropna()
        except Exception:  # noqa: BLE001
            return
        if len(xi):
            xs.append(xi)
    if not xs:
        return
    allx = xs[0]
    for o in xs[1:]:
        allx = allx.append(o)
    if allx.max() - allx.min() < pd.Timedelta(days=2):
        return                                                   # trong phien: khong dung
    days = pd.DatetimeIndex(allx.normalize().unique()).sort_values()
    if len(days) < 3:
        return
    step = pd.Series(days[1:] - days[:-1]).median()
    if step > pd.Timedelta(days=3):
        return                                                   # tuan/thang/quy: khong phai ngay nghi
    full = pd.date_range(days.min(), days.max(), freq="D")
    missing = full.difference(days)
    rb = [dict(bounds=["sat", "mon"])]
    hol = [d.strftime("%Y-%m-%d") for d in missing if d.weekday() < 5]
    if hol:
        rb.append(dict(values=hol))
    fig.update_xaxes(rangebreaks=rb)


def _is_time(df):
    return isinstance(df.index, pd.DatetimeIndex)


def _x(df):
    return df.index if _is_time(df) else df.index.astype(str)


def fig_line(df: pd.DataFrame, unit="", zero=False, colors=None, dash=None, secondary=None, fill=None,
             height=HEIGHT, markers=False, hover_nd=None, width=2):
    """Duong: moi cot 1 chuoi. secondary = [cot ve truc phai]. dash = {cot: 'dash'}."""
    fig = go.Figure()
    if df is None or df.empty:
        return None
    nd = hover_nd if hover_nd is not None else nd_cua(df.values.ravel())
    colors = colors or {}
    sec = set(secondary or [])
    for i, c in enumerate(df.columns):
        s = df[c].dropna()
        if s.empty:
            continue
        fig.add_trace(go.Scatter(
            x=_x(s), y=s.values, name=str(c), mode="lines+markers" if markers else "lines",
            line=dict(width=width, color=colors.get(c, PALETTE[i % len(PALETTE)]), dash=(dash or {}).get(c, "solid")),
            fill=fill if fill else None, yaxis="y2" if c in sec else "y",
            hovertemplate="%{y:,." + str(nd) + "f}<extra>" + str(c) + "</extra>"))
    fig.update_layout(height=height, yaxis=dict(title=unit or None, rangemode="tozero" if zero else "normal"))
    if sec:
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, tickfont=dict(size=11, color=TOK["ink3"])))
    return fig


def fig_bars(df: pd.DataFrame, col=None, unit="", sign=True, color=None, height=HEIGHT, lines=None,
             line_colors=None, cum=None, hover_nd=None, faded_mask=None, opacity=1.0):
    """Cot: col duong/am to cam/xam (sign=True) hoac 1 mau. lines = [cot ve duong de len] (MA...),
    cum = cot ve LUY KE o truc phai. faded_mask = Series bool -> cot to nhat (thang chua ket thuc)."""
    if df is None or df.empty:
        return None
    col = col or df.columns[0]
    s = df[col]
    nd = hover_nd if hover_nd is not None else nd_cua(s.values)
    if sign:
        cols = np.where(s.values >= 0, TOK["orange"], TOK["gray"])
    else:
        cols = np.array([color or TOK["orange"]] * len(s), dtype=object)
    if faded_mask is not None:
        m = np.asarray(faded_mask.reindex(df.index).fillna(False).values, dtype=bool)
        cols = np.where(m, TOK["orange_light"] if not sign else np.where(s.values >= 0, TOK["orange_light"], TOK["gray_light"]), cols)
    fig = go.Figure(go.Bar(x=_x(df), y=s.values, name=str(col), marker_color=list(cols), opacity=opacity,
                           hovertemplate="%{y:,." + str(nd) + "f}<extra>" + str(col) + "</extra>"))
    for i, lc in enumerate(lines or []):
        if lc in df:
            fig.add_trace(go.Scatter(x=_x(df), y=df[lc].values, name=str(lc), mode="lines",
                                     line=dict(width=1.8, color=(line_colors or {}).get(lc, [TOK["brown"], TOK["tan"], TOK["ink2"]][i % 3])),
                                     hovertemplate="%{y:,." + str(nd) + "f}<extra>" + str(lc) + "</extra>"))
    if cum is not None and cum in df:
        fig.add_trace(go.Scatter(x=_x(df), y=df[cum].values, name=str(cum), mode="lines", yaxis="y2",
                                 line=dict(width=2, color=TOK["brown"]),
                                 hovertemplate="%{y:,.0f}<extra>" + str(cum) + "</extra>"))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, tickfont=dict(size=11, color=TOK["ink3"]),
                                      title=dict(text="luỹ kế", font=dict(size=11, color=TOK["ink3"]))))
    fig.update_layout(height=height, yaxis=dict(title=unit or None), bargap=0.25, showlegend=bool(lines or cum))
    if not _is_time(df):
        fig.update_xaxes(type="category")
    return fig


def fig_stack(df: pd.DataFrame, unit="", normalize=False, height=HEIGHT, colors=None, area=False):
    """Cot chong (hoac vung chong) theo cot; normalize = 100%."""
    if df is None or df.empty:
        return None
    d = df.copy()
    if normalize:
        tot = d.abs().sum(axis=1).replace(0, np.nan)
        d = d.div(tot, axis=0) * 100
    fig = go.Figure()
    for i, c in enumerate(d.columns):
        col = (colors or {}).get(c, NGANH_PALETTE[i % len(NGANH_PALETTE)])
        if area:
            fig.add_trace(go.Scatter(x=_x(d), y=d[c].values, name=str(c), stackgroup="one", mode="lines",
                                     line=dict(width=0.5, color=col), fillcolor=col,
                                     hovertemplate="%{y:,.1f}<extra>" + str(c) + "</extra>"))
        else:
            fig.add_trace(go.Bar(x=_x(d), y=d[c].values, name=str(c), marker_color=col,
                                 hovertemplate="%{y:,.1f}<extra>" + str(c) + "</extra>"))
    fig.update_layout(barmode="relative", height=height, yaxis=dict(title=("%" if normalize else unit) or None), bargap=0.2)
    if not _is_time(d):
        fig.update_xaxes(type="category")
    return fig


def fig_hbar(s: pd.Series, unit="", sign=True, color=None, height=None, highlight=None, nd=None):
    """Cot ngang xep hang (gia tri lon o tren). highlight = nhan to mau khac (vd 'Toan thi truong')."""
    if s is None or s.empty:
        return None
    s = s.dropna()
    nd = nd if nd is not None else nd_cua(s.values)
    if sign:
        cols = [TOK["up"] if v >= 0 else TOK["down"] for v in s.values]
    else:
        cols = [color or TOK["orange"]] * len(s)
    if highlight is not None:
        cols = [TOK["ink2"] if str(k) == str(highlight) else c for k, c in zip(s.index, cols)]
    lab = [str(i) if len(str(i)) <= 34 else str(i)[:32] + "…" for i in s.index]
    fig = go.Figure(go.Bar(x=s.values, y=lab, orientation="h", marker_color=cols,
                           text=[fmt_vn(v, nd) for v in s.values], textposition="outside", textfont=dict(size=11, color=TOK["ink2"]),
                           hovertemplate="%{x:,." + str(nd) + "f}<extra>%{y}</extra>"))
    h = height or max(220, 26 * len(s) + 60)
    fig.update_layout(height=h, xaxis=dict(title=unit or None, showgrid=True, gridcolor=TOK["rule_soft"], zeroline=True, zerolinecolor=TOK["rule"], tickangle=0, nticks=6),
                      yaxis=dict(showgrid=False, autorange="reversed", tickfont=dict(size=12, color=TOK["ink"])),
                      margin=dict(l=6, r=40, t=10, b=6), showlegend=False, hovermode="closest", bargap=0.3)
    return fig


def fig_candle(o: pd.DataFrame, mode="Nến", volume=True, height=HEIGHT, name="", ma=None):
    """o: index ngay, cot open/high/low/close(/volume). mode 'Nến' | 'Đường'. ma = [20, 50] duong MA."""
    if o is None or o.empty:
        return None
    o = o.dropna(subset=["close"])
    fig = go.Figure()
    if mode == "Nến" and {"open", "high", "low"} <= set(o.columns) and o[["open", "high", "low"]].notna().any().any():
        fig.add_trace(go.Candlestick(x=o.index, open=o.open, high=o.high, low=o.low, close=o.close, name=name or "Giá",
                                     increasing=dict(line=dict(color=TOK["up"], width=1), fillcolor=TOK["up"]),
                                     decreasing=dict(line=dict(color=TOK["down"], width=1), fillcolor=TOK["down"]),
                                     whiskerwidth=0.4))
        fig.update_layout(hovermode="x")
    else:
        fig.add_trace(go.Scatter(x=o.index, y=o.close, mode="lines", name=name or "Giá", line=dict(color=TOK["orange"], width=2),
                                 hovertemplate="%{y:,.2f}<extra>" + (name or "Giá") + "</extra>"))
    for i, w in enumerate(ma or []):
        m = o.close.rolling(w).mean()
        fig.add_trace(go.Scatter(x=o.index, y=m, mode="lines", name=f"MA{w}", line=dict(width=1.3, color=[TOK["brown"], TOK["tan"], TOK["gray"]][i % 3]),
                                 hovertemplate="%{y:,.2f}<extra>MA" + str(w) + "</extra>"))
    if volume and "volume" in o and o.volume.notna().any():
        up = o.close >= o.close.shift()
        fig.add_trace(go.Bar(x=o.index, y=o.volume, name="KL", yaxis="y2", opacity=0.9,
                             marker_color=np.where(up, TOK["up_soft"], TOK["down_soft"]),
                             hovertemplate="%{y:,.0f}<extra>KL</extra>"))
        fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, range=[0, float(o.volume.max()) * 4],
                                      tickfont=dict(size=10, color=TOK["ink3"]), showticklabels=False))
    fig.update_layout(height=height, xaxis=dict(rangeslider=dict(visible=False)), yaxis=dict(title=None, side="left"),
                      showlegend=bool(ma))
    apply_rangebreaks(fig)                                     # an cuoi tuan + ngay le
    return fig


def fig_treemap(d: pd.DataFrame, path=("Nhóm ngành", "Mã"), value="abs", color="Ròng (tỷ)", height=560):
    """Treemap: o = |gia tri|, mau = dau (mua rong xanh, ban rong do)."""
    if d is None or d.empty:
        return None
    import plotly.express as px
    d = d.copy()
    d["abs"] = d[color].abs()
    d = d[d["abs"] > 0]
    if d.empty:
        return None
    vmax = float(d[color].abs().quantile(0.95)) or 1.0
    fig = px.treemap(d, path=[px.Constant("Toàn thị trường")] + list(path), values=value, color=color,
                     color_continuous_scale=[TOK["down"], "#f6d9d9", "#f4f1ee", "#cfeadb", TOK["up"]],
                     range_color=[-vmax, vmax], custom_data=[color])
    fig.update_traces(hovertemplate="%{label}<br>Ròng: %{customdata[0]:,.1f} tỷ<extra></extra>",
                      texttemplate="%{label}<br>%{customdata[0]:,.0f}", textfont=dict(family=FONT, size=12),
                      marker=dict(line=dict(width=1, color="#fff")), root_color="#fff")
    fig.update_layout(height=height, margin=dict(l=2, r=2, t=24, b=2), coloraxis_showscale=False)
    return fig


def add_hline(fig, y, text=None, color=None, dash="dash"):
    kw = dict(annotation_text=text, annotation_position="top right",
              annotation_font=dict(size=11, color=color or TOK["down"])) if text else {}
    fig.add_hline(y=y, line=dict(color=color or TOK["down"], width=1.2, dash=dash), **kw)
    return fig


def _marker(fig, x, y, col, yaxis="y", size=10):
    fig.add_trace(go.Scatter(x=[x], y=[y], mode="markers", showlegend=False, hoverinfo="skip", yaxis=yaxis or "y",
                             marker=dict(symbol="circle-open", size=size, color=col, line=dict(width=2, color=col))))


def add_live_marker(fig, df: pd.DataFrame, ts=None, src=None):
    """Diem cuoi (hom nay) = dau tron RONG tren moi duong/cot/nen + nhan 'LIVE hh:mm:ss' (goc tren phai)."""
    if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return fig
    x_last = df.index.max()
    for tr in list(fig.data):
        try:
            if tr.x is None or len(tr.x) == 0:
                continue
            xs = pd.to_datetime(pd.Index(tr.x))
            if xs[-1] != x_last:
                continue
            if tr.type == "scatter" and tr.y is not None:
                y = tr.y[-1]
                if y is None or (isinstance(y, float) and np.isnan(y)):
                    continue
                col = (tr.line.color if tr.line is not None and tr.line.color else None) or TOK["orange"]
                _marker(fig, x_last, y, col, getattr(tr, "yaxis", "y"))
            elif tr.type == "bar" and tr.y is not None:
                y = tr.y[-1]
                if y is None or (isinstance(y, float) and np.isnan(y)):
                    continue
                _marker(fig, x_last, y, TOK["ink"], getattr(tr, "yaxis", "y"), 9)
            elif tr.type == "candlestick" and tr.close is not None:
                _marker(fig, x_last, tr.close[-1], TOK["ink"])
        except Exception:  # noqa: BLE001
            continue
    label = (f"LIVE {ts:%H:%M:%S}" if ts is not None else "LIVE") + (f" · {src}" if src else "")
    fig.add_annotation(x=1, y=1, xref="paper", yref="paper", xanchor="right", yanchor="bottom", text=label, showarrow=False,
                       font=dict(size=11, color="#fff"), bgcolor=TOK["up"], borderpad=3, yshift=2)
    return fig


def add_last_price(fig, s: pd.Series, nd=2):
    """Net dut do + nhan gia hien tai (nhu trang mau)."""
    s = s.dropna()
    if s.empty:
        return fig
    v = float(s.iloc[-1])
    fig.add_hline(y=v, line=dict(color=TOK["down"], width=1, dash="dot"))
    fig.add_annotation(x=1, xref="paper", y=v, text=fmt_vn(v, nd), showarrow=False, xanchor="left",
                       font=dict(size=11, color="#fff"), bgcolor=TOK["down"], borderpad=3)
    return fig


def legend_html(items):
    """items: [(ten, mau)] -> dong chu thich cham mau."""
    return '<div class="gn-legend">' + "".join(f'<span><i style="background:{m}"></i>{t}</span>' for t, m in items) + "</div>"


# ------------------------------------------------------------- BANG %
def html_pct_table(df: pd.DataFrame, pct_cols=None, name_col=None, total_row=None, nd=1):
    """Bang kieu Genea: cot dau = index (dam) + name_col (nho), cac cot % canh phai xanh/do, '—' khi thieu."""
    pct_cols = list(pct_cols) if pct_cols else [c for c in df.columns if c != name_col]
    h = ['<div class="gn-tblwrap"><table class="gn-tbl"><thead><tr><th>' + (str(df.index.name or "Mã")) + "</th>"]
    for c in pct_cols:
        h.append(f"<th>{c}</th>")
    h.append("</tr></thead><tbody>")
    for idx, row in df.iterrows():
        cls = ' class="total"' if total_row is not None and str(idx) == str(total_row) else ""
        name = f"<small>{row[name_col]}</small>" if name_col and name_col in df.columns and pd.notna(row[name_col]) else ""
        h.append(f"<tr{cls}><td><b>{idx}</b>{name}</td>")
        for c in pct_cols:
            v = row[c]
            if v is None or pd.isna(v):
                h.append('<td class="na">—</td>')
            else:
                k = "up" if v > 0 else ("down" if v < 0 else "")
                h.append(f'<td class="{k}">{fmt_vn(v, nd, dau=True)}%</td>')
        h.append("</tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


def style_pct(df: pd.DataFrame, cols=None, nd=2):
    """pandas Styler: so % duong xanh / am do, dinh dang."""
    cols = cols or [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    def _c(v):
        if pd.isna(v) or v == 0:
            return ""
        return f"color: {TOK['up'] if v > 0 else TOK['down']}; font-weight: 600"
    return df.style.map(_c, subset=cols).format(precision=nd, thousands=".", decimal=",", na_rep="—")


def rebase100(px: pd.DataFrame) -> pd.DataFrame:
    base = px.apply(lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan)
    return px / base * 100


def delta_html(v_now, v_prev, nd=2, unit=""):
    """'1.730,02 điểm −8,95 (−0,51%)' voi mau tang/giam."""
    if v_now is None or pd.isna(v_now):
        return ""
    s = f'<span class="unit">{fmt_vn(v_now, nd)} {unit}</span>'
    if v_prev is not None and pd.notna(v_prev) and v_prev:
        d = v_now - v_prev
        k = "delta-up" if d >= 0 else "delta-down"
        s += f' <span class="{k}">{fmt_vn(d, nd, dau=True)} ({fmt_vn(d / v_prev * 100, 2, dau=True)}%)</span>'
    return s


def fig_group_bars(df: pd.DataFrame, bars, lines=None, unit="", height=HEIGHT, colors=None, hover_nd=None):
    """Cot nhom (nhieu cot canh nhau) + duong de len (vd thu / chi + boi chi)."""
    if df is None or df.empty:
        return None
    nd = hover_nd if hover_nd is not None else nd_cua(df[bars].values.ravel())
    fig = go.Figure()
    for i, b in enumerate(bars):
        fig.add_trace(go.Bar(x=_x(df), y=df[b].values, name=str(b), marker_color=(colors or {}).get(b, PALETTE[i % len(PALETTE)]),
                             hovertemplate="%{y:,." + str(nd) + "f}<extra>" + str(b) + "</extra>"))
    for j, ln in enumerate(lines or []):
        fig.add_trace(go.Scatter(x=_x(df), y=df[ln].values, name=str(ln), mode="lines+markers",
                                 line=dict(width=2, color=(colors or {}).get(ln, [TOK["ink"], TOK["brown"]][j % 2])),
                                 hovertemplate="%{y:,." + str(nd) + "f}<extra>" + str(ln) + "</extra>"))
    fig.update_layout(barmode="group", height=height, yaxis=dict(title=unit or None), bargap=0.25)
    if not _is_time(df):
        fig.update_xaxes(type="category")
    return fig


def fig_band(df: pd.DataFrame, lo, hi, mid=None, unit="", height=HEIGHT, name_band="Dải cao – thấp"):
    """Dai cao-thap (to mo) + duong giua (vd lai suat huy dong: Big4 thap - cao nhat - binh quan)."""
    if df is None or df.empty or lo not in df or hi not in df:
        return None
    d = df.dropna(subset=[lo, hi], how="all")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d.index, y=d[hi], name=str(hi), mode="lines", line=dict(width=1, color=TOK["orange_light"]),
                             hovertemplate="%{y:,.2f}<extra>" + str(hi) + "</extra>"))
    fig.add_trace(go.Scatter(x=d.index, y=d[lo], name=str(lo), mode="lines", line=dict(width=1, color=TOK["orange_light"]),
                             fill="tonexty", fillcolor="rgba(244,177,131,0.35)", hovertemplate="%{y:,.2f}<extra>" + str(lo) + "</extra>"))
    if mid and mid in d:
        fig.add_trace(go.Scatter(x=d.index, y=d[mid], name=str(mid), mode="lines", line=dict(width=2.2, color=TOK["orange"]),
                                 hovertemplate="%{y:,.2f}<extra>" + str(mid) + "</extra>"))
    fig.update_layout(height=height, yaxis=dict(title=unit or None))
    return fig


def fig_bubble(d: pd.DataFrame, x, y, size, color, text=None, unit="", height=HEIGHT, xtitle=None, ylim=None, log_x=False):
    """Bong bong: moi diem 1 lo (vd lai suat phat hanh theo thoi gian, kich thuoc = gia tri)."""
    if d is None or d.empty:
        return None
    import plotly.express as px
    fig = px.scatter(d, x=x, y=y, size=size, color=color, hover_name=text, size_max=28, opacity=0.55,
                     color_discrete_sequence=NGANH_PALETTE, log_x=log_x)
    fig.update_traces(marker=dict(line=dict(width=0.5, color="#fff")))
    fig.update_layout(height=height, yaxis=dict(title=unit or None, range=ylim), xaxis=dict(title=xtitle), hovermode="closest",
                      legend=dict(orientation="h", y=-0.18, x=0))
    return fig
