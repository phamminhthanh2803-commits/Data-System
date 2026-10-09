# -*- coding: utf-8 -*-
r"""
MARKET DATA APP - mot cho de xem TOAN BO du lieu thi truong trong D:\market-data
va xuat Excel nhanh.

Chay:   D:\market-data\app\Chay-app.bat
hoac:   streamlit run D:\market-data\app\app.py

Khong ket noi mang (tru khi bam nut "Cap nhat du lieu" - nut do goi Run-Market.ps1).
"""
import os
import subprocess
import sys
import re
from datetime import date, datetime

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import datalib as dl  # noqa: E402
import xuat_excel as xuat  # noqa: E402

st.set_page_config(page_title="Market Data", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")

PRESETS = {"1 tháng": 1, "3 tháng": 3, "6 tháng": 6, "YTD": None, "12 tháng": 12,
           "2 năm": 24, "3 năm": 36, "5 năm": 60, "10 năm": 120, "Tất cả": None,
           "Tuỳ chọn…": None}

# dinh dang so kieu Viet Nam cho truc/tooltip cua Vega (1.234,5)
LOCALE_VI = {"decimal": ",", "thousands": ".", "grouping": [3], "currency": ["", " ₫"]}
EMBED = {"embedOptions": {"formatLocale": LOCALE_VI,
                          "actions": {"export": True, "source": False,
                                      "compiled": False, "editor": False}}}

# ---------------------------------------------------------- BANG MAU BIEU DO
# "Bao cao" = dung bo mau cac bieu do bao cao dang dung: cam #ED7D31, cam nhat
# #F4B183, den #262626, xam #A6A6A6 / #BFBFBF, nen trang, luoi ngang xam nhat.
MAU_BAOCAO = {
    "bg": "#ffffff", "ink": "#262626", "ink2": "#595959", "grid": "#D9D9D9",
    "bar": "#BFBFBF", "pos": "#00B050", "neg": "#C00000", "nhan": "#ED7D31",
    "echarts": "",
    "range": ["#262626", "#ED7D31", "#A6A6A6", "#F4B183", "#C00000", "#00B050",
              "#4472C4", "#843C0C", "#7F7F7F", "#BF9000", "#2E75B6", "#D9D9D9"],
}
MAU_TOI = {
    "bg": "#0e1117", "ink": "#e6e9ef", "ink2": "#a9b1c2", "grid": "#2a2f3a",
    "bar": "#3b82c4", "pos": "#1baf7a", "neg": "#e34948", "nhan": "#eb6834",
    "echarts": "dark",
    "range": ["#e6e9ef", "#eb6834", "#7fb3ff", "#f5c451", "#e34948", "#1baf7a",
              "#a78bfa", "#4dd0e1", "#94a3b8", "#f472b6", "#84cc16", "#c2b280"],
}

# 07/10/2026: giao dien Bloomberg Terminal - nen den, chu amber (#ffa028) / trang, font monospace, o KPI vien mong,
# tab dang phim lenh, thanh trang thai tren cung. Bang mau bieu do di kem (MAU_BLOOMBERG). Theme Streamlit nen
# (.streamlit/config.toml) cung dat base=dark + amber de widget dong bo.
MAU_BLOOMBERG = {
    "bg": "#000000", "ink": "#f2f2f2", "ink2": "#b8b8b8", "grid": "#262626",
    "bar": "#ffa028", "pos": "#19c37d", "neg": "#ff4d4f", "nhan": "#ffa028",
    "echarts": "dark", "font": "IBM Plex Mono, Consolas, Courier New, monospace",
    "range": ["#ffa028", "#ffffff", "#3d8bff", "#19c37d", "#ff4d4f", "#ffe066",
              "#e879f9", "#4dd0e1", "#9a9a9a", "#ff8c00", "#84cc16", "#c2b280"],
}
CSS_CHUNG = """
<style>
  .block-container {padding-top: 1.2rem; padding-bottom: 1rem; max-width: 100%;}
  [data-testid="stMetricValue"] {font-size: 1.55rem;}
  [data-testid="stMetricLabel"] {opacity: .75;}
  h1 {font-size: 1.9rem; margin-bottom: .2rem;}
  h2, h3 {margin-top: .4rem;}
  .stTabs [data-baseweb="tab"] {padding: 6px 14px;}
</style>
"""
CSS_BLOOMBERG = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&display=swap');
  :root {--bb-amber:#ffa028; --bb-line:#262626; --bb-panel:#0b0b0b; --bb-txt:#e8e8e8; --bb-dim:#9a9a9a;}
  html, body, [data-testid="stAppViewContainer"], [data-testid="stHeader"], .main {
      background:#000 !important; color:var(--bb-txt);
      font-family:"IBM Plex Mono", Consolas, "Courier New", monospace !important;}
  [data-testid="stSidebar"] {background:#050505 !important; border-right:1px solid var(--bb-line);}
  [data-testid="stSidebar"] * {font-family:"IBM Plex Mono", Consolas, monospace;}
  [data-testid="stSidebar"] h1 {font-size:1rem;}
  h1, h2, h3 {font-family:inherit !important; text-transform:uppercase; letter-spacing:.07em; color:var(--bb-amber) !important;}
  h1 {font-size:1.15rem !important; border-bottom:1px solid #333; padding-bottom:.3rem; margin-bottom:.5rem !important;}
  h2 {font-size:.95rem !important;} h3 {font-size:.85rem !important;}
  [data-testid="stMetric"] {background:var(--bb-panel); border:1px solid var(--bb-line); border-top:2px solid var(--bb-amber);
      padding:6px 10px 4px 10px;}
  [data-testid="stMetricLabel"] {opacity:1 !important;}
  [data-testid="stMetricLabel"] p {color:var(--bb-amber); text-transform:uppercase; font-size:.66rem; letter-spacing:.08em;}
  [data-testid="stMetricValue"] {color:#fff; font-size:1.3rem; font-weight:600;}
  [data-testid="stMetricDelta"] {font-size:.72rem;}
  .stTabs [data-baseweb="tab-list"] {background:#000; border-bottom:1px solid #333; gap:0;}
  .stTabs [data-baseweb="tab"] {color:#c8c8c8; text-transform:uppercase; font-size:.7rem; letter-spacing:.06em;
      padding:5px 12px; border-right:1px solid #1f1f1f; border-radius:0;}
  .stTabs [aria-selected="true"] {background:var(--bb-amber) !important;}
  .stTabs [aria-selected="true"] p {color:#000 !important; font-weight:600;}
  .stTabs [data-baseweb="tab-highlight"] {background:var(--bb-amber);}
  .stTabs [data-baseweb="tab-border"] {background:#333;}
  .stMarkdown p > strong:only-child {color:var(--bb-amber); text-transform:uppercase; font-size:.7rem; letter-spacing:.07em;}
  [data-testid="stDataFrame"], [data-testid="stTable"] {border:1px solid var(--bb-line);}
  .stButton > button, .stDownloadButton > button {background:#000 !important; color:var(--bb-amber) !important;
      border:1px solid var(--bb-amber) !important; border-radius:0 !important; text-transform:uppercase; font-size:.7rem; letter-spacing:.05em;}
  .stButton > button:hover, .stDownloadButton > button:hover {background:var(--bb-amber) !important; color:#000 !important;}
  div[data-baseweb="select"] > div, .stTextInput input, .stNumberInput input, [data-baseweb="input"] {
      background:var(--bb-panel) !important; border-radius:0 !important; border-color:#333 !important; font-size:.8rem;}
  [data-baseweb="popover"] li, [data-baseweb="menu"] li {font-size:.78rem;}
  .stRadio label, .stCheckbox label, .stToggle label, .stSelectbox label, .stMultiSelect label, .stSlider label {
      font-size:.72rem !important; text-transform:uppercase; letter-spacing:.05em; color:var(--bb-dim);}
  [data-testid="stCaptionContainer"], .stCaption {color:var(--bb-dim) !important; font-size:.68rem !important;}
  hr {border-color:var(--bb-line) !important;}
  [data-testid="stExpander"] {border:1px solid var(--bb-line); border-radius:0; background:var(--bb-panel);}
  .bb-bar {display:flex; flex-wrap:wrap; gap:0 18px; background:var(--bb-panel); border:1px solid #333;
      border-left:4px solid var(--bb-amber); padding:4px 10px; font-size:.68rem; letter-spacing:.06em;
      text-transform:uppercase; margin:0 0 .6rem 0; color:#ddd;}
  .bb-bar b {color:var(--bb-amber); font-weight:600;} .bb-bar .ok {color:#19c37d;} .bb-bar .warn {color:#ff4d4f;}
  .vega-embed, .vega-embed canvas, .vega-embed svg {background:#000 !important;}
</style>
"""
st.markdown(CSS_CHUNG, unsafe_allow_html=True)


# --------------------------------------------------------------- tien ich UI
def _boc_streamlit():
    """Boc 1 lan / tien trinh: bang & tieu de ve ra deu duoc ghi lai cho nut Xuat Excel."""
    from streamlit.delta_generator import DeltaGenerator as DG
    if getattr(DG, "_xuat_boc", False):
        return
    goc_df, goc_sub, goc_md = DG.dataframe, DG.subheader, DG.markdown

    def dataframe(self, data=None, *a, **k):
        xuat.ghi_bang(data)
        return goc_df(self, data, *a, **k)

    def subheader(self, body, *a, **k):
        xuat.dat_tieu_de(body)
        return goc_sub(self, body, *a, **k)

    def markdown(self, body, *a, **k):
        if isinstance(body, str) and body.lstrip().startswith("**"):
            xuat.dat_tieu_de(body)
        return goc_md(self, body, *a, **k)
    DG.dataframe, DG.subheader, DG.markdown = dataframe, subheader, markdown
    DG._xuat_boc = True


_boc_streamlit()
# st.dataframe / st.subheader / st.markdown la ham gan san vao DeltaGenerator chinh luc import
# -> tro lai qua DG da boc
from streamlit.delta_generator import DeltaGenerator as _DG  # noqa: E402
st.dataframe = lambda *a, **k: _DG.dataframe(st._main, *a, **k)
st.subheader = lambda *a, **k: _DG.subheader(st._main, *a, **k)
st.markdown = lambda *a, **k: _DG.markdown(st._main, *a, **k)


def dl_button(df: pd.DataFrame, ten: str, label="⬇️ Tải Excel", key=None, sheets=None):
    """Nut tai Excel cho bang dang xem."""
    data = sheets if sheets else {ten[:31]: df}
    st.download_button(label, dl.to_excel(data),
                       file_name=f"{ten}_{date.today():%Y%m%d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       key=key or f"dl_{ten}", width="content")


def tan_suat_thap(df: pd.DataFrame) -> bool:
    """True khi MOI cot deu la chuoi thang/quy/nam (buoc thoi gian trung vi >= 20 ngay).
    Chi can 1 cot theo ngay la tinh la chuoi ngay (bang tron ngay + thang)."""
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return False
    buoc = []
    for c in df.columns:
        s = df[c].dropna()
        if len(s) >= 2:
            buoc.append(s.index.to_series().diff().dt.days.median())
    return bool(buoc) and min(buoc) >= 20


def cut(df: pd.DataFrame, _=None):
    """Cat theo khung thoi gian dang chon o thanh ben (D_FROM..D_TO).

    Chuoi thang/quy (tan_suat_thap) giu TOAN BO lich su den D_TO khi bat DAI_THAP -
    12 diem thang khong du de doc xu huong. Tham so thu 2 giu lai cho tuong thich nguoc."""
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return df
    if DAI_THAP and tan_suat_thap(df):
        return df[df.index <= D_TO]
    df = df[(df.index >= D_FROM) & (df.index <= D_TO)]
    if THEO_THANG and len(df) > 2 and not tan_suat_thap(df):
        df = thang(df)
    return df


_FLOW_RE = re.compile(r"ròng|mua/bán|gtgd|giá trị giao dịch|khối lượng|\bkl\b|bơm|hút|\bnet\b|flow|turnover|volume|"
                      r"phát hành|đáo hạn|mua lại|lượt|số lượng", re.I)      # KHONG dung "mua"/"bán" tran: "VCB bán" la ty gia
_LEVEL_RE = re.compile(r"lưu hành|số dư|dư nợ|tổng tài sản|vốn hoá|vốn hóa|outstanding|lãi suất|tỷ giá|p/e|p/b|"
                       r"chỉ số|index|giá|rate|yield|ytm|%", re.I)


def thang(df: pd.DataFrame) -> pd.DataFrame:
    """Chuoi ngay -> 1 diem / thang (moc = ngay dau thang, khop voi so lieu thang NSO/IMF).
    Cot dong tien (ten co 'ròng', 'GTGD', 'bơm/hút', 'khối lượng'...) = CONG DON thang; con lai = gia tri CUOI thang."""
    agg = {}
    for c in df.columns:
        n = str(c)
        if not pd.api.types.is_numeric_dtype(df[c]):
            agg[c] = "last"
        elif re.search(r"lưu hành|số dư|dư nợ|tổng tài sản|outstanding|luỹ kế|lũy kế", n, re.I):
            agg[c] = "last"                       # "Bom rong dang luu hanh" la so du, khong cong don
        elif _FLOW_RE.search(n):
            agg[c] = "sum"
        else:
            agg[c] = "last"
    out = df.groupby(df.index.to_period("M")).agg(agg)
    out.index = out.index.to_timestamp()
    out.index.name = df.index.name
    # cot cong don: thang khong co giao dich -> NaN thay vi 0
    for c, a in agg.items():
        if a == "sum":
            cnt = df[c].groupby(df.index.to_period("M")).count()
            cnt.index = cnt.index.to_timestamp()
            out.loc[cnt.reindex(out.index).fillna(0) == 0, c] = np.nan
    return out


def _xdom(df):
    """(moc dau truc X, so thang cua truc) - chuoi thang dai thi truc bat dau tu diem dau tien."""
    if DAI_THAP and tan_suat_thap(df):
        x0 = min(df.index.min(), D_FROM)
        return x0, max(1, round((D_TO - x0).days / 30.44))
    return D_FROM, MONTHS


def _title(t):
    """Tieu de ve bang markdown chu khong bang title cua Vega (bi cat khi chart hep)."""
    if t:
        xuat.dat_tieu_de(t)
        st.markdown(f"**{t}**")


def _xtip(xcol, is_t):
    """Tooltip cot X: chi truyen `format` khi la truc ngay (None lam Vega bao loi schema)."""
    return (alt.Tooltip(f"{xcol}:T", title="Ngày", format="%d/%m/%Y") if is_t
            else alt.Tooltip(f"{xcol}:N", title=xcol))


def _fmt(vals) -> str:
    """So chu so thap phan hop voi do lon cua day so."""
    v = pd.Series(vals).replace([np.inf, -np.inf], np.nan).dropna().abs()
    m = float(v.max()) if len(v) else 0.0
    return ",.2f" if m < 10 else (",.1f" if m < 1000 else ",.0f")


def ten_file_an_toan(ten: str) -> str:
    """Bo dau va ky tu cam trong ten file anh."""
    bo = str.maketrans("àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợ"
                       "ùúủũụưừứửữựỳýỷỹỵ",
                       "aaaaaaaaaaaaaaaaadeeeeeeeeeeeiiiiiooooooooooooooooo"
                       "uuuuuuuuuuuyyyyy")
    t = str(ten).lower().translate(bo)
    t = "".join(c if c.isalnum() else "-" for c in t)
    t = "-".join(x for x in t.split("-") if x)[:60] or "bieu-do"
    return f"{t}_{date.today():%Y%m%d}"


def _xaxis(is_t, months=None):
    """Truc ngay: dinh dang theo do dai khung dang xem."""
    if not is_t:
        return alt.Axis(labelAngle=0, labelOverlap="greedy")
    mo = months or MONTHS
    f = "%d/%m" if mo <= 3 else ("%m/%Y" if mo <= 36 else "%Y")
    return alt.Axis(format=f, tickCount=8, labelAngle=0, grid=False)


def _xfmt(is_t, months=None):
    """Dinh dang ngay cua truc X (giong _xaxis) - truyen sang file Excel."""
    if not is_t:
        return None
    mo = months or MONTHS
    return "%d/%m" if mo <= 3 else ("%m/%Y" if mo <= 36 else "%Y")


def _kieu(df_cols=None, is_t=True, mo=None, x0=None, **kw):
    """Thong so hien thi cua 1 bieu do de file Excel ve y het: mau tung series (domain Vega
    sap tang dan tren bang mau dang chon), dinh dang truc, khung ngay."""
    k = {"x_fmt": _xfmt(is_t, mo), "x0": (x0 or D_FROM) if is_t else None, "x1": D_TO if is_t else None}
    if df_cols is not None:
        k["mau"] = xuat.mau_series(list(df_cols), _mau())
    k.update(kw)
    return k


def _xscale(is_t, x0=None):
    """CO DINH khung hien thi = dung khoang thoi gian dang chon (khong tu gian/pan)."""
    if not is_t:
        return alt.Undefined
    return alt.Scale(domain=[(x0 or D_FROM).isoformat(), D_TO.isoformat()], clamp=True)


def _yaxis(y_title, fmt):
    return alt.Axis(title=y_title or None, format=fmt, titleFontWeight="normal",
                    labelFlush=False, tickCount=6)


def _mau(n=None):
    """Bang mau dang dung (theo lua chon o thanh ben)."""
    r = TH["range"]
    return r if n is None else r[:max(1, n)]


def nut_anh(ten="bieu-do", height=38):
    """Hang nut nho duoi bieu do: COPY anh vao clipboard (1 cu bam) + tai PNG.

    Lam HOAN TOAN o trinh duyet: Streamlit ve bieu do bang SVG, component nay
    (cung origin, srcdoc + allow-same-origin) doc lai the <svg> cua bieu do ngay
    PHIA TREN no trong DOM cha, ve vao canvas roi ghi vao clipboard. Khong goi
    server, khong rerun, khong can thu vien ngoai.
    """
    import json
    html = """
<style>
  body {margin:0; font-family: "Source Sans Pro", system-ui, sans-serif;}
  .r {display:flex; gap:6px; align-items:center;}
  button {border:1px solid __VIEN__; background:transparent; color:__CHU__;
          border-radius:6px; padding:2px 10px; font-size:12px; cursor:pointer;
          line-height:20px;}
  button:hover {border-color:__NHAN__; color:__NHAN__;}
  #msg {font-size:12px; color:__CHU__; opacity:.85;}
</style>
<div class="r">
  <button id="cp" title="Copy ảnh biểu đồ, Ctrl+V dán thẳng vào slide/Word">📋 Copy ảnh</button>
  <button id="dl" title="Tải ảnh PNG về máy">⬇ PNG</button>
  <span id="msg"></span>
</div>
<script>
const SCALE = __SCALE__, NEN = __NEN__, TEN = __TEN__;
const P = window.parent.document;

function timSvg() {                       // bieu do gan nhat PHIA TREN component nay
  let node = window.frameElement;
  while (node && node !== P.body) {
    let sib = node.previousElementSibling;
    while (sib) {
      const svg = sib.querySelector && sib.querySelector('[data-testid="stVegaLiteChart"] svg');
      if (svg) return svg;
      sib = sib.previousElementSibling;
    }
    node = node.parentElement;
  }
  return null;
}

// dung anh TRONG REALM CUA TRANG CHA de con ghi duoc vao clipboard cua trang cha
function veAnh() {
  return new Promise((ok, loi) => {
    const svg = timSvg();
    if (!svg) { loi(new Error('không thấy biểu đồ')); return; }
    const w = svg.width.baseVal.value || svg.clientWidth;
    const h = svg.height.baseVal.value || svg.clientHeight;
    const xml = new XMLSerializer().serializeToString(svg);
    const img = new (window.parent.Image)();
    img.onload = () => {
      const c = P.createElement('canvas');
      c.width = Math.round(w * SCALE); c.height = Math.round(h * SCALE);
      const ctx = c.getContext('2d');
      ctx.fillStyle = NEN; ctx.fillRect(0, 0, c.width, c.height);
      ctx.drawImage(img, 0, 0, c.width, c.height);
      c.toBlob(b => b ? ok(b) : loi(new Error('không dựng được ảnh')), 'image/png');
    };
    img.onerror = () => loi(new Error('không đọc được SVG'));
    img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(xml);
  });
}

// uu tien clipboard cua TRANG CHA (iframe component co the khong duoc cap quyen
// clipboard-write), roi moi den clipboard cua chinh iframe
async function chepAnh() {
  const W = window.parent, CI = W.ClipboardItem || window.ClipboardItem;
  try {
    await W.navigator.clipboard.write([new CI({'image/png': veAnh()})]);
    return;
  } catch (e) {
    const b = await veAnh();
    try { await W.navigator.clipboard.write([new CI({'image/png': b})]); }
    catch (e2) { await navigator.clipboard.write([new ClipboardItem({'image/png': b})]); }
  }
}

function bao(t, ms) { const m = document.getElementById('msg'); m.textContent = t;
                      setTimeout(() => { m.textContent = ''; }, ms || 3500); }

document.getElementById('cp').onclick = async () => {
  try { await chepAnh(); bao('✓ đã copy — Ctrl+V để dán'); }
  catch (e) { bao('✗ ' + (e.message || e.name) + ' — dùng nút ⬇ PNG', 6000); }
};

document.getElementById('dl').onclick = async () => {
  try {
    const b = await veAnh();
    const a = P.createElement('a');
    a.href = window.parent.URL.createObjectURL(b); a.download = TEN + '.png';
    P.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => window.parent.URL.revokeObjectURL(a.href), 5000);
    bao('✓ đã tải');
  } catch (e) { bao('✗ ' + e.message, 6000); }
};
</script>"""
    html = (html.replace("__SCALE__", str(ANH_SCALE))
                .replace("__NEN__", json.dumps(TH["bg"]))
                .replace("__TEN__", json.dumps(ten_file_an_toan(ten)))
                .replace("__VIEN__", TH["grid"])
                .replace("__CHU__", TH["ink2"])
                .replace("__NHAN__", TH["nhan"]))
    st.iframe(html, height=height)


def show(ch, ten="bieu-do", da_ghi=False):
    """Ap bang mau + ve bieu do + nut copy/tai anh. da_ghi=False: bieu do tu dung -> ghi data."""
    if not da_ghi:
        xuat.ghi_altair(ch, ten)
    font = TH.get("font") or alt.Undefined
    ch = (ch.properties(background=TH["bg"])
            .configure_view(strokeWidth=0, fill=TH["bg"])
            .configure_axis(labelColor=TH["ink2"], titleColor=TH["ink2"], gridColor=TH["grid"],
                            domainColor=TH["grid"], tickColor=TH["grid"],
                            labelFontSize=11, titleFontSize=11, gridWidth=0.8, labelFont=font, titleFont=font)
            .configure_legend(labelColor=TH["ink2"], titleColor=TH["ink2"], labelFontSize=11,
                              symbolStrokeWidth=3, symbolType="stroke", labelFont=font, titleFont=font)
            .configure_title(color=TH["ink"], font=font))
    st.altair_chart(ch, width="stretch")
    nut_anh(ten)


def line(df, title="", y_title="", height=340, zero=False, y_domain=None, ten=None):
    """Bieu do duong nhieu series tu DataFrame wide. Truc X co dinh theo khung dang chon."""
    _title(title)
    if df.empty:
        st.caption("Không có dữ liệu trong khung thời gian này.")
        return
    xcol = df.index.name or "index"
    d = df.reset_index().melt(id_vars=xcol, var_name="Series", value_name="Giá trị").dropna()
    is_t = isinstance(df.index, pd.DatetimeIndex)
    x0, mo = _xdom(df) if is_t else (None, None)
    fmt = _fmt(d["Giá trị"])
    ysc = alt.Scale(zero=zero, nice=True) if y_domain is None else alt.Scale(domain=list(y_domain))
    ch = (alt.Chart(d).mark_line(strokeWidth=1.9, clip=True)
          .encode(x=alt.X(f"{xcol}:T" if is_t else f"{xcol}:N", title=None,
                          axis=_xaxis(is_t, mo), scale=_xscale(is_t, x0)),
                  y=alt.Y("Giá trị:Q", axis=_yaxis(y_title, fmt), scale=ysc),
                  color=alt.Color("Series:N", title=None, scale=alt.Scale(range=_mau()),
                                  legend=alt.Legend(orient="bottom", columns=4, labelLimit=220)),
                  tooltip=[_xtip(xcol, is_t), "Series", alt.Tooltip("Giá trị:Q", format=fmt)])
          .properties(height=height, usermeta=EMBED))
    xuat.ghi("line", title, df, y_title,
             kieu=_kieu(df.columns, is_t, mo, x0, y_fmt=fmt, zero=zero, cao_px=height, lw=1.9))
    show(ch, ten or title or "bieu-do", da_ghi=True)


def bars(df, col, title="", y_title="", height=300, color_sign=True, ten=None):
    """Bieu do COT. color_sign=True -> duong/am doi mau."""
    _title(title or col)
    if df.empty or col not in df:
        st.caption("Không có dữ liệu trong khung thời gian này.")
        return
    xcol = df.index.name or "index"
    d = df.reset_index().dropna(subset=[col])
    is_t = isinstance(df.index, pd.DatetimeIndex)
    x0, mo = _xdom(df[[col]]) if is_t else (None, None)
    fmt = _fmt(d[col])
    color = (alt.condition(alt.datum[col] >= 0, alt.value(TH["pos"]), alt.value(TH["neg"]))
             if color_sign else alt.value(TH["bar"]))
    ch = (alt.Chart(d).mark_bar(clip=True)
          .encode(x=alt.X(f"{xcol}:T" if is_t else f"{xcol}:N", title=None,
                          axis=_xaxis(is_t, mo), scale=_xscale(is_t, x0)),
                  y=alt.Y(f"{col}:Q", axis=_yaxis(y_title, fmt), scale=alt.Scale(nice=True)),
                  color=color,
                  tooltip=[_xtip(xcol, is_t), alt.Tooltip(f"{col}:Q", format=fmt)])
          .properties(height=height, usermeta=EMBED))
    xuat.ghi("bar", title or col, df[[col]], y_title,
             kieu=_kieu(None, is_t, mo, x0, y_fmt=fmt, zero=True, cao_px=height, sign=color_sign,
                        mau_cot=None if color_sign else TH["bar"]))
    show(ch, ten or title or col, da_ghi=True)


def bars_stack(df, title="", y_title="", height=340, ten=None):
    """Cot CHONG theo series (vd ngay/tuan x nhom nganh), am/duong chong tach 2 phia truc 0."""
    _title(title)
    if df.empty:
        st.caption("Không có dữ liệu trong khung thời gian này.")
        return
    xcol = df.index.name or "index"
    d = df.reset_index().melt(id_vars=xcol, var_name="Series", value_name="Giá trị").dropna()
    is_t = isinstance(df.index, pd.DatetimeIndex)
    x0, mo = _xdom(df) if is_t else (None, None)
    fmt = _fmt(d["Giá trị"])
    ch = (alt.Chart(d).mark_bar(clip=True)
          .encode(x=alt.X(f"{xcol}:T" if is_t else f"{xcol}:N", title=None,
                          axis=_xaxis(is_t, mo), scale=_xscale(is_t, x0)),
                  y=alt.Y("Giá trị:Q", axis=_yaxis(y_title, fmt), stack="zero"),
                  color=alt.Color("Series:N", title=None, scale=alt.Scale(range=_mau()),
                                  legend=alt.Legend(orient="bottom", columns=4)),
                  tooltip=[_xtip(xcol, is_t), "Series:N", alt.Tooltip("Giá trị:Q", format=fmt)])
          .properties(height=height, usermeta=EMBED))
    xuat.ghi("stack", title, df, y_title,
             kieu=_kieu(df.columns, is_t, mo, x0, y_fmt=fmt, zero=True, cao_px=height))
    show(ch, ten or title or "cot-chong", da_ghi=True)


def bars_lines(df, bar_col, line_cols, title="", y_title="", height=340,
               bar_color=None, color_sign=False, ten=None):
    """Cot (vd GTGD) + duong (vd MA20/MA50) chung 1 truc."""
    _title(title)
    if df.empty or bar_col not in df:
        st.caption("Không có dữ liệu trong khung thời gian này.")
        return
    xcol = df.index.name or "index"
    cols = [bar_col] + [c for c in line_cols if c in df]
    d = df[cols].reset_index().dropna(subset=[bar_col])
    fmt = _fmt(d[bar_col])
    x0, mo = _xdom(df[[bar_col]])
    xenc = alt.X(f"{xcol}:T", title=None, axis=_xaxis(True, mo), scale=_xscale(True, x0))
    bar_enc = (alt.condition(alt.datum[bar_col] >= 0, alt.value(TH["pos"]), alt.value(TH["neg"]))
               if color_sign else alt.value(bar_color or TH["bar"]))
    bar = (alt.Chart(d).mark_bar(clip=True, opacity=.9)
           .encode(x=xenc, y=alt.Y(f"{bar_col}:Q", axis=_yaxis(y_title, fmt),
                                   scale=alt.Scale(nice=True)),
                   color=bar_enc,
                   tooltip=[alt.Tooltip(f"{xcol}:T", title="Ngày", format="%d/%m/%Y")]
                           + [alt.Tooltip(f"{c}:Q", format=fmt) for c in cols]))
    layers = [bar]
    if len(cols) > 1:
        ln = (alt.Chart(d).transform_fold(list(cols[1:]), as_=["Series", "val"])
              .mark_line(strokeWidth=2, clip=True)
              .encode(x=xenc, y=alt.Y("val:Q", axis=_yaxis(y_title, fmt)),
                      color=alt.Color("Series:N", title=None,
                                      scale=alt.Scale(range=[TH["ink"], TH["nhan"]]),
                                      legend=alt.Legend(orient="bottom"))))
        layers.append(ln)
    ch = (alt.layer(*layers).resolve_scale(y="shared", color="independent")
          .properties(height=height, usermeta=EMBED))
    xuat.ghi("bar_line", title, df[cols], y_title,
             kieu=_kieu(None, True, mo, x0, y_fmt=fmt, zero=True, cao_px=height, sign=color_sign,
                        mau_cot=None if color_sign else (bar_color or TH["bar"])))
    show(ch, ten or title or bar_col, da_ghi=True)


def hbars(s: pd.Series, title="", x_title="", height=None, color=None, fmt=None, ten=None,
          color_sign=False):
    """Cot ngang cho bang xep hang (top nganh, top he sinh thai...). color_sign: duong/am doi mau."""
    _title(title)
    if s.empty:
        st.caption("Không có dữ liệu.")
        return
    d = s.rename("Giá trị").reset_index()
    name = d.columns[0]
    f = fmt or _fmt(d["Giá trị"])
    mau = (alt.condition(alt.datum["Giá trị"] >= 0, alt.value(TH["pos"]), alt.value(TH["neg"]))
           if color_sign else alt.value(color or TH["nhan"]))
    ch = (alt.Chart(d).mark_bar()
          .encode(y=alt.Y(f"{name}:N", sort="-x", title=None),
                  x=alt.X("Giá trị:Q", axis=_yaxis(x_title, f)), color=mau,
                  tooltip=[name, alt.Tooltip("Giá trị:Q", format=f)])
          .properties(height=height or max(180, 24 * len(d)), usermeta=EMBED))
    xuat.ghi("hbar", title, s.rename(x_title or "Giá trị").to_frame(), x_title,
             kieu={"y_fmt": f, "zero": True, "cao_px": height or max(180, 24 * len(d)),
                   "sign": color_sign, "mau_cot": None if color_sign else (color or TH["nhan"])})
    show(ch, ten or title or "xep-hang", da_ghi=True)


def line_nguong(df, nguong: dict, title="", y_title="", height=300, ten=None, zero=False):
    """Duong thuc te (net lien) + duong NGUONG/TRAN (net dut, bac thang, mau do/cam).

    nguong = {ten: Series theo ngay | so co dinh}. Nhin vao la thay con bao xa den tran."""
    _title(title)
    if df.empty:
        st.caption("Không có dữ liệu trong khung thời gian này.")
        return
    x0, mo = _xdom(df)
    xcol = df.index.name or "index"
    d = df.reset_index().melt(id_vars=xcol, var_name="Series", value_name="Giá trị").dropna()
    ng = []
    for k, v in nguong.items():
        if isinstance(v, pd.Series):
            s = v.dropna()
            s = s[s.index <= D_TO]
            if s.empty:
                continue
            s = s[s.ne(s.shift())]           # chi giu diem doi muc (chuoi tran ghi hang ngay)
            # keo bac thang ra toi mep phai truc de khong bi hut o ky cuoi
            s = pd.concat([s, pd.Series([s.iloc[-1]], index=[D_TO])])
            s = s[~s.index.duplicated(keep="first")]
        else:
            s = pd.Series([float(v), float(v)], index=[x0, D_TO])
        ng.append(pd.DataFrame({xcol: s.index, "Series": k, "Giá trị": s.values}))
    dn = pd.concat(ng) if ng else pd.DataFrame(columns=[xcol, "Series", "Giá trị"])
    ten_tt, ten_ng = list(dict.fromkeys(d.Series)), list(dict.fromkeys(dn.Series))
    mau_ng = [TH["neg"], TH["nhan"], TH["ink2"]]
    mau = alt.Scale(domain=ten_tt + ten_ng,
                    range=_mau(len(ten_tt)) + [mau_ng[i % 3] for i in range(len(ten_ng))])
    fmt = _fmt(pd.concat([d["Giá trị"], dn["Giá trị"]]))
    xenc = alt.X(f"{xcol}:T", title=None, axis=_xaxis(True, mo), scale=_xscale(True, x0))
    yenc = alt.Y("Giá trị:Q", axis=_yaxis(y_title, fmt), scale=alt.Scale(zero=zero, nice=True))
    leg = alt.Legend(orient="bottom", columns=4, labelLimit=240)
    tip = [_xtip(xcol, True), "Series", alt.Tooltip("Giá trị:Q", format=fmt)]
    lop = [alt.Chart(d).mark_line(strokeWidth=2, clip=True, point=alt.OverlayMarkDef(size=14))
           .encode(x=xenc, y=yenc, color=alt.Color("Series:N", title=None, scale=mau, legend=leg),
                   tooltip=tip)]
    if not dn.empty:
        lop.append(alt.Chart(dn).mark_line(strokeWidth=1.6, strokeDash=[6, 4], clip=True,
                                           interpolate="step-after")
                   .encode(x=xenc, y=yenc, color=alt.Color("Series:N", title=None, scale=mau,
                                                           legend=leg), tooltip=tip))
    wide = df.copy()
    for k, v in nguong.items():      # nguong -> cot cung truc ngay (bac thang = ffill)
        wide[k] = (v.sort_index().reindex(wide.index.union(v.index)).ffill().reindex(wide.index)
                   if isinstance(v, pd.Series) else float(v))
    xuat.ghi("nguong", title, wide, y_title, n_thuc=len(df.columns),
             kieu=_kieu(None, True, mo, x0, y_fmt=fmt, zero=zero, cao_px=height, lw=2,
                        mau={str(n): m for n, m in zip(ten_tt + ten_ng, mau.range)},
                        net_dut=[str(n) for n in ten_ng]))
    show(alt.layer(*lop).properties(height=height, usermeta=EMBED), ten or title or "nguong", da_ghi=True)


def tv_widget(kind: str, cfg: dict, height=560):
    """Nhung widget TradingView (bieu do ben thu 3). Can Internet o may dang mo app."""
    import json
    html = f"""
    <div class="tradingview-widget-container" style="height:{height}px;width:100%">
      <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
      <script type="text/javascript"
              src="https://s3.tradingview.com/external-embedding/embed-widget-{kind}.js" async>
      {json.dumps(cfg)}
      </script>
    </div>"""
    st.iframe(html, height=height + 10)


def echarts_treemap(hm: pd.DataFrame, title="", height=620):
    xuat.ghi("treemap", title or "Bản đồ nhiệt", hm.set_index("Mã") if "Mã" in hm else hm)
    """Ban do nhiet dang treemap (ECharts qua CDN) dung DU LIEU CUA MINH.

    hm: cot Mã, Nhóm ngành, Vốn hoá (tỷ), Biến động (%)."""
    import json
    nodes = [{"name": g, "children": [
        {"name": r["Mã"], "value": float(r["Vốn hoá (tỷ)"]), "pct": float(r["Biến động (%)"])}
        for _, r in sub.iterrows()]}
        for g, sub in hm.groupby("Nhóm ngành")]
    nen = TH["bg"]
    opt = {
        "backgroundColor": nen,
        "tooltip": {},
        "series": [{
            "type": "treemap", "roam": False, "nodeClick": False, "breadcrumb": {"show": False},
            "width": "100%", "height": "100%", "top": 4, "left": 2, "right": 2, "bottom": 2,
            "data": nodes,
            "levels": [
                {"itemStyle": {"borderColor": nen, "borderWidth": 3, "gapWidth": 3},
                 "upperLabel": {"show": True, "height": 20, "color": TH["ink2"], "fontSize": 11}},
                {"itemStyle": {"borderColor": nen, "borderWidth": 1, "gapWidth": 1}},
            ],
            "label": {"show": True, "fontSize": 11, "color": "#fff"},
        }],
    }
    html = f"""
    <div id="tm" style="width:100%;height:{height}px;background:{nen};"></div>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js"></script>
    <script>
      const opt = {json.dumps(opt, ensure_ascii=False)};
      const NEN = {json.dumps([int(TH["bg"][i:i + 2], 16) for i in (1, 3, 5)])};
      function col(p) {{                     // do (giam) -> mau nen (0) -> xanh (tang)
        const x = Math.max(-1, Math.min(1, p / 6));
        const t = x >= 0 ? [20, 160, 90] : [192, 0, 0];
        const a = Math.abs(x);
        return 'rgb(' + Math.round(NEN[0] + (t[0] - NEN[0]) * a) + ','
                      + Math.round(NEN[1] + (t[1] - NEN[1]) * a) + ','
                      + Math.round(NEN[2] + (t[2] - NEN[2]) * a) + ')';
      }}
      opt.series[0].data.forEach(function (g) {{ g.children.forEach(function (c) {{
        c.itemStyle = {{color: col(c.pct)}};
        c.label = {{formatter: c.name + '\\n' + (c.pct >= 0 ? '+' : '')
                             + c.pct.toFixed(1).replace('.', ',') + '%',
                    color: Math.abs(c.pct) > 2 ? '#fff' : {json.dumps(TH["ink"])}}};
      }}); }});
      opt.tooltip.formatter = function (i) {{
        var p = i.data.pct;
        return i.name + '<br/>Vốn hoá: ' + Math.round(i.value).toLocaleString('vi-VN') + ' tỷ'
             + (p === undefined ? '' : '<br/>Biến động: ' + (p >= 0 ? '+' : '')
                + p.toFixed(2).replace('.', ',') + '%');
      }};
      var ch = echarts.init(document.getElementById('tm'), {json.dumps(THEME_ECHARTS or None)});
      ch.setOption(opt);
      window.addEventListener('resize', function () {{ ch.resize(); }});
    </script>"""
    _title(title)
    st.iframe(html, height=height + 12)


def kpi(col, label, value, delta=None, help=None):
    xuat.ghi_kpi(label, value, delta)
    col.metric(label, value, delta, help=help)


RATIO_UNIT = {"pe": "lần", "pb": "lần", "ps": "lần", "div_yield": "%", "roe_ttm": "%",
              "earnings_yield": "%", "marketcap": "tỷ VND", "ln_ttm": "tỷ VND",
              "marketcap_float": "tỷ VND", "doanh_thu_ttm": "tỷ VND", "close": "điểm"}


def don_vi(r):
    return RATIO_UNIT.get(r, r)


TEN_CT = {"pe": "P/E", "pb": "P/B", "ps": "P/S", "div_yield": "Tỷ suất cổ tức", "roe_ttm": "ROE TTM",
          "marketcap": "Vốn hoá", "ln_ttm": "LN TTM", "earnings_yield": "Earnings yield (E/P)"}


def chon_ct(label, opts, default=("pe", "pb"), key=None):
    """Multiselect chi tieu dinh gia (hien ten dep). Bo trong -> lay chi tieu dau tien."""
    chon = st.multiselect(label, opts, default=[x for x in default if x in opts],
                          format_func=lambda k: TEN_CT.get(k, k), key=key)
    return chon or [opts[0]]


def ten_sheet(tien_to, ct):
    return f"{tien_to}_{TEN_CT.get(ct, ct)}".replace("/", "").replace(" ", "")[:31]


def luoi_ct(cts, ve, ncol=2):
    """Moi chi tieu 1 bieu do, xep luoi ncol cot. ve(ct) tu goi line()."""
    for i in range(0, len(cts), ncol):
        cols = st.columns(ncol) if len(cts) > 1 else [st.container()]
        for col, ct in zip(cols, cts[i:i + ncol]):
            with col:
                ve(ct)


def num(v, nd=1):
    return "—" if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:,.{nd}f}"



# ------------------------------------------------- TAB & BO LOC DONG BO TOAN APP (07/10/2026)
def tabs_bb(names, key):
    """Tab dong bo: tab dang mo duoc NHO trong session (doi trang / rerun van giu), moi tab la 1 khung
    (container) - tab khong chon thi an bang CSS nen noi dung van duoc ve -> Xuat Excel toan app van du.
    Khi dang xuat Excel dung st.tabs goc cho chac."""
    if xuat.dang_xuat_all() or st.session_state.get(xuat.K_REQ):
        return xuat.tabs(names)
    k_mem = f"_tab_{key}"
    nho = st.session_state.get(k_mem)
    if nho not in names:
        nho = names[0]
    chon = st.segmented_control("Tab", names, default=nho, key=f"tabsel_{key}",
                                label_visibility="collapsed") or nho
    st.session_state[k_mem] = chon
    out, an = [], []
    for i, n in enumerate(names):
        ck = f"tab_{key}_{i}"
        out.append(xuat._Tab(st.container(key=ck), n))
        if n != chon:
            an.append(ck)
    if an:
        st.markdown("<style>" + "".join(f".st-key-{a}{{display:none;}}" for a in an) + "</style>",
                    unsafe_allow_html=True)
    return out


def filt(kieu, label, options, default=None, key=None, col=None, **kw):
    """Bo loc dong bo: lua chon duoc nho theo key trong session -> doi tab / doi trang / rerun van giu.
    kieu = multiselect | selectbox | radio. col = cot (st.columns) de dat widget."""
    key = key or re.sub(r"\W+", "_", str(label).lower())
    k_mem, w = f"_f_{key}", (col or st)
    opts = list(options)
    if kieu == "multiselect":
        nho = [x for x in st.session_state.get(k_mem, default if default is not None else []) if x in opts]
        val = w.multiselect(label, opts, default=nho, key=f"w_{key}", **kw)
    else:
        nho = st.session_state.get(k_mem, default)
        if nho not in opts:
            nho = default if default in opts else (opts[0] if opts else None)
        idx = opts.index(nho) if nho in opts else 0
        val = (w.radio if kieu == "radio" else w.selectbox)(label, opts, index=idx, key=f"w_{key}", **kw)
    st.session_state[k_mem] = val
    return val


# ------------------------------------------------------------------ SIDEBAR
st.sidebar.title("📊 Market Data")
TRANG = ["🏠 Tổng quan", "📈 Việt Nam", "🌏 Khu vực & thế giới", "🏦 Vĩ mô & tiền tệ",
         "🧾 Trái phiếu & nhà đầu tư", "📺 Biểu đồ nhúng", "🔎 Kho dữ liệu", "⬇️ Xuất Excel"]
# mo thang 1 trang bang URL: ...:8765/?trang=vimo (dung cho Chay-app-macro.bat)
TAT = {"tong-quan": 0, "vn": 1, "khu-vuc": 2, "vimo": 3, "trai-phieu": 4, "chart": 5,
       "kho": 6, "excel": 7}
_q = st.query_params.get("trang")
if _q in TAT and "trang_da_mo" not in st.session_state:
    st.session_state["trang_da_mo"] = True
    st.session_state["nav"] = TRANG[TAT[_q]]
PAGE = st.sidebar.radio("Trang", TRANG, key="nav", label_visibility="collapsed")
st.sidebar.divider()

try:
    LAST = dl.last_session()          # phien da dong cua gan nhat
except Exception:  # noqa: BLE001
    LAST = pd.Timestamp.now().normalize()
DATA_MIN = pd.Timestamp("2000-01-01")

ky = st.sidebar.selectbox("Khoảng thời gian", list(PRESETS), index=4)
if ky == "Tuỳ chọn…":
    if "kh_tuy_chon" not in st.session_state:   # dat value + key cung luc -> Streamlit canh bao
        st.session_state["kh_tuy_chon"] = ((LAST - pd.DateOffset(months=12)).date(), LAST.date())
    r = st.sidebar.date_input("Từ ngày → đến ngày",
                              min_value=DATA_MIN.date(), max_value=date.today(),
                              format="DD/MM/YYYY", key="kh_tuy_chon")
    if isinstance(r, (tuple, list)) and len(r) == 2:
        D_FROM, D_TO = pd.Timestamp(r[0]), pd.Timestamp(r[1])
    else:                              # dang chon do: moi bam 1 dau
        D_FROM = pd.Timestamp(r[0] if isinstance(r, (tuple, list)) else r)
        D_TO = LAST
    if D_FROM > D_TO:
        D_FROM, D_TO = D_TO, D_FROM
elif ky == "YTD":
    D_FROM, D_TO = pd.Timestamp(f"{LAST.year - 1}-12-31"), LAST
elif PRESETS[ky] is None:
    D_FROM, D_TO = DATA_MIN, LAST
else:
    D_FROM, D_TO = LAST - pd.DateOffset(months=PRESETS[ky]), LAST
MONTHS = max(1, round((D_TO - D_FROM).days / 30.44))
st.sidebar.caption(f"**{D_FROM:%d/%m/%Y} → {D_TO:%d/%m/%Y}**  ({MONTHS} tháng)")
DAI_THAP = st.sidebar.toggle("Chuỗi tháng/quý: toàn bộ lịch sử", value=True,
                             help="Bật: số liệu tháng/quý (CPI, tín dụng, M2, LDR, CAR, XNK...) "
                                  "luôn vẽ từ điểm đầu tiên đến ngày kết thúc, không bị cắt theo "
                                  "khoảng thời gian. Tắt: cắt giống số liệu ngày.")
# 07/10/2026: moi bieu do hien theo THANG (user yeu cau) - chuoi ngay gop ve 1 diem/thang ngay trong cut():
# gia/lai suat/ty gia/so du -> gia tri cuoi thang; dong tien (mua/ban rong, GTGD, bom/hut, khoi luong) -> cong don thang
THEO_THANG = st.sidebar.toggle("Hiển thị theo tháng", value=True,
                               help="Bật: chuỗi theo ngày gộp về 1 điểm mỗi tháng (giá, lãi suất, tỷ giá, số dư = "
                                    "cuối tháng; mua/bán ròng, GTGD, bơm/hút = cộng dồn tháng) để khớp với "
                                    "CPI, XNK, IIP... của Cục Thống kê. Tắt: vẽ theo ngày như cũ.")

_pn1, _pn2 = st.sidebar.columns([1, 1])
ICB_CAP = _pn1.selectbox("Phân ngành ICB", [1, 2, 3, 4], index=1, key="icb_cap",
                         format_func=lambda x: f"Cấp {x}",
                         help="Phân ngành ICB của Vietcap, áp cho TOÀN app (tab Ngành, bản đồ nhiệt, "
                              "khối ngoại / tự doanh theo ngành, tra cứu cổ phiếu). Cấp 1: ~10 ngành · "
                              "Cấp 2: ~19 · Cấp 3-4: chi tiết hơn")
ICB_VIN = _pn2.checkbox("Tách Vingroup", value=True, key="icb_vin",
                        help="VIC, VHM, VRE, VPL gom thành nhóm riêng thay vì nằm trong Bất động sản")
dl.set_pn((ICB_CAP, ICB_VIN))
bang_mau = st.sidebar.selectbox("Bảng màu biểu đồ", ["Bloomberg Terminal", "Báo cáo (nền trắng)", "Tối"], index=0,
                                help="Bloomberg: nền đen, chữ amber, font monospace (mặc định). Bảng màu Báo cáo dùng "
                                     "đúng bộ cam/đen/xám của các biểu đồ báo cáo, ảnh xuất ra dán thẳng vào slide là khớp.")
TH = (MAU_BLOOMBERG if bang_mau.startswith("Bloomberg") else
      MAU_BAOCAO if bang_mau.startswith("Báo cáo") else MAU_TOI)
if TH is MAU_BLOOMBERG:
    st.markdown(CSS_BLOOMBERG, unsafe_allow_html=True)
THEME_ECHARTS = TH["echarts"]
xuat.dat_giao_dien(TH)
ANH_SCALE = st.sidebar.select_slider("Độ nét ảnh copy", [1, 2, 3, 4], value=2,
                                     format_func=lambda x: f"{x}x",
                                     help="Ảnh copy/tải về được phóng gấp mấy lần kích thước "
                                          "biểu đồ trên màn hình")

TRANG_XUAT = TRANG[:5]          # 5 trang du lieu (bo Bieu do nhung / Kho / Xuat Excel)
with st.sidebar.expander("📥 Xuất Excel (data + chart)", expanded=xuat.dang_xuat_all()):
    st.caption("File Excel gồm **data + biểu đồ Excel** của mọi chart, bảng, chỉ số đang hiển thị — "
               "đúng khoảng thời gian, phân ngành, bộ lọc đang chọn. Mỗi tab 1 sheet, có Mục lục.")
    _x1, _x2 = st.columns(2)
    if _x1.button("Trang này", width="stretch", key="_xuat_btn_trang",
                  help="Mọi tab của trang đang xem"):
        st.session_state[xuat.K_REQ] = True
    if _x2.button("Toàn app", width="stretch", key="_xuat_btn_all",
                  help="5 trang dữ liệu: " + ", ".join(TRANG_XUAT) + ". Mất khoảng 1-3 phút."):
        xuat.bat_dau_xuat_all(PAGE, TRANG_XUAT, giu_khoa=("nav",))
    if xuat.dang_xuat_all():
        _con = st.session_state.get(xuat.K_Q, [])
        st.info(f"Đang xuất toàn app… còn {len(_con)} trang: {', '.join(_con)}")
        st.button("⏭️ Tiếp tục (nếu bị dừng)", key="_xuat_tiep", width="stretch")
    XUAT_NUT = st.empty()
PAGE = xuat.trang_luot_nay(PAGE)
xuat.bat_dau(PAGE)

with st.sidebar.expander("⚙️ Dữ liệu"):
    if st.button("🔄 Xoá cache, nạp lại file", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Chạy pipeline (có kết nối mạng, vài phút):")
    slot = st.selectbox("Slot", ["PM", "AM"], key="slot")
    steps = {"PM": ["transmission", "flows", "foreign-stocks", "foreign-vci", "prop-stocks", "icb-vci",
                    "indices-vn", "tvhistory", "valuation-region", "tradingview", "msci", "macro-region"],
             "AM": ["valuation-vn", "macro-vn", "bonds", "vsdc-accounts", "indices"]}[slot]
    chon = st.multiselect("Bước", steps, default=[])
    if st.button("▶️ Cập nhật dữ liệu", width="stretch"):
        cmd = ["powershell", "-NoProfile", "-File", os.path.join(dl.BASE, "Run-Market.ps1"), "-Slot", slot]
        if chon:
            cmd += ["-Only", ",".join(chon)]
        with st.spinner("Đang chạy Run-Market.ps1 ..."):
            r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        st.code((r.stdout or "")[-3000:] or "(không có output)")
        st.cache_data.clear()

st.sidebar.caption(f"Phiên gần nhất: {LAST:%d/%m/%Y}")
END = D_TO
# moc dau ky: chi so nganh / von hoa phai dung RO co phieu cua CHINH ky dang xem,
# neu co dinh ro tu 2016 thi cac ma len san sau (VHM, VPL...) bi loai khoi ca chuoi
SINCE = D_FROM.strftime("%Y-%m-%d")
SINCE_TO = D_TO.strftime("%Y-%m-%d")

# ================================================================ TONG QUAN
if TH is MAU_BLOOMBERG:
    # thanh trang thai kieu terminal: trang, khung thoi gian, tan suat, do tuoi du lieu
    try:
        _fr = dl.freshness_df()
        _cu = int((_fr["Trạng thái"] != "OK").sum())
        _tuoi = f"<span class='{'ok' if _cu == 0 else 'warn'}'>DATA {len(_fr) - _cu}/{len(_fr)} OK</span>"
    except Exception:  # noqa: BLE001
        _tuoi = ""
    st.markdown(f"<div class='bb-bar'><b>MARKET DATA</b><span>{PAGE[2:]}</span>"
                f"<span><b>KHUNG</b> {D_FROM:%d/%m/%Y} – {D_TO:%d/%m/%Y}</span>"
                f"<span><b>TẦN SUẤT</b> {'THÁNG' if THEO_THANG else 'NGÀY'}</span>"
                f"<span><b>ICB</b> CẤP {ICB_CAP}</span>{_tuoi}"
                f"<span><b>{datetime.now():%d %b %Y %H:%M}</b></span></div>", unsafe_allow_html=True)

if PAGE == "🏠 Tổng quan":
    if st.session_state.get("tape", True):
        tv_widget("ticker-tape", {
            "symbols": [{"proName": "HOSE:VNINDEX", "title": "VN-Index"},
                        {"proName": "HOSE:VN30", "title": "VN30"},
                        {"proName": "HOSE:VNMIDCAP", "title": "VNMidcap"},
                        {"proName": "HOSE:VNSMALLCAP", "title": "VNSmallcap"},
                        {"proName": "KRX:KOSPI", "title": "KOSPI"},
                        {"proName": "TWSE:TAIEX", "title": "TAIEX"},
                        {"proName": "SP:SPX", "title": "S&P 500"},
                        {"proName": "TVC:DXY", "title": "DXY"},
                        {"proName": "TVC:GOLD", "title": "Vàng"},
                        {"proName": "TVC:USOIL", "title": "Dầu WTI"}],
            "showSymbolLogo": True, "isTransparent": True, "displayMode": "adaptive",
            "colorTheme": "dark", "locale": "vi_VN",
        }, height=52)
    st.title("Tổng quan thị trường")
    fr = dl.freshness_df()
    to = dl.turnover_df()
    br = dl.breadth_df()
    fv = dl.flows_vn()
    val = dl.load("valuation_wide")

    live = to[(to["Phiên"] == "Đang giao dịch") & (to.index <= D_TO)]
    # KPI luôn dùng phiên ĐÃ ĐÓNG CỬA, và không vượt quá ngày cuối của khung đang chọn
    to = to[(to["Phiên"] == "Đã đóng cửa") & (to.index <= D_TO)]
    last = to.index.max()
    c = st.columns(6)
    vni = to["VN-Index"].dropna()
    kpi(c[0], "VN-Index", num(vni.iloc[-1], 2),
        f"{(vni.iloc[-1] / vni.iloc[-2] - 1) * 100:+.2f}%" if len(vni) > 1 else None)
    g = to["Toàn thị trường"]
    kpi(c[1], "GTGD (tỷ)", num(g.iloc[-1], 0),
        f"{(g.iloc[-1] / to['MA20 toàn TT'].iloc[-1] - 1) * 100:+.0f}% vs MA20")
    f_last = fv.loc[fv.index <= last, "KN ròng toàn TT"].dropna()
    kpi(c[2], "KN ròng (tỷ)", num(f_last.iloc[-1], 0),
        f"20 phiên: {f_last.tail(20).sum():+,.0f}")
    br_c = br[br.index <= last]
    kpi(c[3], "% trên MA200", num(br_c["% mã trên MA200"].iloc[-1], 1) + "%",
        f"MA50: {br_c['% mã trên MA50'].iloc[-1]:.0f}%")
    kpi(c[4], "% mã tăng", num(br_c["% mã tăng"].iloc[-1], 0) + "%")
    v = val[val.code == "VNINDEX"].sort_values("date")
    kpi(c[5], "P/E VN-Index", num(v.pe.dropna().iloc[-1], 2),
        f"P/B {v.pb.dropna().iloc[-1]:.2f}")
    st.caption(f"Số liệu phiên đã đóng cửa gần nhất: {last:%d/%m/%Y}. GTGD tính bằng tỷ VND.")
    if not live.empty:
        r = live.iloc[-1]
        st.info(f"Phiên {live.index[-1]:%d/%m} đang giao dịch — VN-Index {r['VN-Index']:,.2f}, "
                f"GTGD tạm tính {r['Toàn thị trường']:,.0f} tỷ (chưa hết phiên, không dùng để so sánh).")

    a, b = st.columns([3, 2])
    with a:
        line(cut(to[["VN-Index"]]), "VN-Index", "điểm", height=265)
        bars_lines(cut(to), "Toàn thị trường", ["MA20 toàn TT", "MA50 toàn TT"],
                   "Giá trị giao dịch toàn thị trường", "tỷ VND", height=265)
    with b:
        line(cut(br[["% mã trên MA50", "% mã trên MA200"]]),
             "Độ rộng: % cổ phiếu trên MA", "% số mã", height=265, zero=True)
        bars(cut(fv[["KN ròng toàn TT"]]), "KN ròng toàn TT",
             "Khối ngoại mua/bán ròng", "tỷ VND", height=265)

    st.subheader("Tình trạng dữ liệu")
    # KHONG dat ten bien "show": se de len ham ve bieu do show() cua ca app
    bang_tt = fr.copy()
    bang_tt["Dữ liệu đến"] = pd.to_datetime(bang_tt["Dữ liệu đến"]).dt.strftime("%d/%m/%Y")
    bang_tt["Cập nhật lúc"] = pd.to_datetime(bang_tt["Cập nhật lúc"]).dt.strftime("%d/%m %H:%M")
    st.dataframe(bang_tt[["Dataset", "Nhóm", "Trạng thái", "Dữ liệu đến", "Trễ (ngày)",
                       "Số dòng", "Cập nhật lúc", "Mô tả"]],
                 width="stretch", hide_index=True,
                 column_config={"Số dòng": st.column_config.NumberColumn(format="%d")})
    dl_button(fr.set_index("Dataset"), "TinhTrangDuLieu")

# ================================================================== VIET NAM
elif PAGE == "📈 Việt Nam":
    st.title("Thị trường Việt Nam")
    t = tabs_bb(["Chỉ số & GTGD", "Khối ngoại & tự doanh", "Độ rộng thị trường",
                 "Dưới MA50/200/300", "Vốn hoá nhóm", "Ngành", "Định giá",
                 "Tăng trưởng EPS", "Cổ phiếu"], "vn")

    with t[0]:
        to = cut(dl.turnover_df())
        st.subheader("Giá trị giao dịch")
        c1, c2 = st.columns([4, 1])
        kieu = c2.radio("Kiểu", ["Cột — toàn TT", "Cột — chồng 3 sàn", "Đường"], index=0)
        ma = c2.checkbox("Hiện MA20/MA50", value=True)
        mas = ["MA20 toàn TT", "MA50 toàn TT"] if ma else []
        with c1:
            if kieu == "Cột — toàn TT":
                bars_lines(to, "Toàn thị trường", mas, "", "tỷ VND", height=380)
            elif kieu == "Cột — chồng 3 sàn":
                d = to[["HOSE", "HNX", "UPCoM"]].reset_index().melt(
                    id_vars="Ngày", var_name="Sàn", value_name="GTGD").dropna()
                ch = (alt.Chart(d).mark_bar(clip=True)
                      .encode(x=alt.X("Ngày:T", title=None, axis=_xaxis(True), scale=_xscale(True)),
                              y=alt.Y("GTGD:Q", axis=_yaxis("tỷ VND", ",.0f"), stack="zero"),
                              color=alt.Color("Sàn:N", title=None,
                                              scale=alt.Scale(range=["#2a78d6", "#eb6834", "#1baf7a"]),
                                              legend=alt.Legend(orient="bottom")),
                              tooltip=[alt.Tooltip("Ngày:T", format="%d/%m/%Y"), "Sàn",
                                       alt.Tooltip("GTGD:Q", format=",.0f")])
                      .properties(height=380, usermeta=EMBED))
                st.altair_chart(ch, width="stretch")
            else:
                line(to[["HOSE", "HNX", "UPCoM", "Toàn thị trường"] + mas], "", "tỷ VND",
                     height=380, zero=True)
        m = to[["Toàn thị trường"]].copy()
        m["thang"] = m.index.to_period("M").astype(str)
        mth = m.groupby("thang")["Toàn thị trường"].mean().to_frame("GTGD bình quân phiên")
        mth.index.name = "Tháng"
        bars(mth, "GTGD bình quân phiên", "GTGD bình quân mỗi phiên theo tháng", "tỷ VND",
             height=260, color_sign=False)
        st.caption("Nguồn VCI (accumulatedValue). Phiên VCI chưa cập nhật được bù bằng close×KL "
                   "từ TradingView — xem cột Nguồn trong bảng.")
        idx = dl.load("indices")
        codes = st.multiselect("Chỉ số", sorted(idx.index_code.unique()),
                               default=["VNINDEX", "VN30", "HNXINDEX", "UPCOM"])
        px = idx[idx.index_code.isin(codes)].pivot_table(index="date", columns="index_code",
                                                         values="close", aggfunc="last")
        px = cut(px, MONTHS)
        reb = px / px.apply(lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan) * 100
        line(reb, "Diễn biến chỉ số (rebase 100 đầu kỳ)", "rebase 100")
        st.dataframe(to.tail(15).iloc[::-1], width="stretch")
        dl_button(to, "GTGD_ChiSo", sheets={"GTGD": to, "ChiSo": px, "Rebase100": reb})

    with t[1]:
        st.subheader("Khối ngoại & tự doanh (tỷ VND)")
        fv = cut(dl.flows_vn(), MONTHS)
        c1, c2 = st.columns([3, 2])
        with c1:
            bars(fv, "KN ròng toàn TT", "Mua/bán ròng khối ngoại theo phiên", "tỷ VND")
        with c2:
            line(fv[["Luỹ kế KN toàn TT"]], "Luỹ kế khối ngoại", "tỷ VND")
        cols = [c for c in fv.columns if c.startswith(("KN ròng H", "KN ròng U", "Tự doanh"))]
        line(fv[cols].rolling(20).sum(), "Tổng 20 phiên theo sàn & tự doanh", "tỷ VND")
        xl_kn = {"VN_theo_ngay": fv}

        st.subheader("Khối ngoại theo nhóm ngành (tỷ VND)")
        fs = dl.foreign_stocks()
        if fs.empty:
            st.caption("Chưa có dữ liệu theo mã — chạy bước foreign-stocks (index-fetcher\\fetch_foreign_stocks.py).")
        else:
            TEN_KN = {"netVal": "Mua/bán ròng", "netMatch": "Ròng khớp lệnh (bỏ thoả thuận)",
                      "buyVal": "Giá trị mua", "sellVal": "Giá trị bán"}
            c1, c2, c3 = st.columns([2, 1, 2])
            san = c1.multiselect("Sàn", ["HOSE", "HNX", "UPCOM"], default=["HOSE", "HNX", "UPCOM"],
                                 key="kn_san") or ["HOSE", "HNX", "UPCOM"]
            tan = c2.radio("Gộp theo", ["D", "W", "M"], index=1, horizontal=True, key="kn_tan",
                           format_func={"D": "Ngày", "W": "Tuần", "M": "Tháng"}.get)
            ct_kn = c3.multiselect("Chỉ tiêu", list(TEN_KN), default=["netVal"], key="kn_ct",
                                   format_func=TEN_KN.get) or ["netVal"]
            tu = max(D_FROM, fs.date.min())
            if D_FROM < fs.date.min():
                st.caption(f"Dữ liệu theo mã có từ {fs.date.min():%d/%m/%Y} — khung trước đó bị cắt.")
            cap, vin = ICB_CAP, ICB_VIN          # phan nganh chon o thanh ben (ICB Vietcap)
            pn = (cap, vin)
            nhom_all = dl.ds_nganh(pn)
            nhom = st.multiselect(f"Nhóm ngành ICB cấp {cap} (bỏ trống = tất cả; đổi cấp ở thanh bên)",
                                  nhom_all, default=[], key=f"kn_nhom_{cap}_{vin}")
            piv_kn, tong = {}, pd.DataFrame()
            for ct in ct_kn:
                piv_kn[ct], tong = dl.flows_sector(tu, D_TO, tuple(san), tan, ct, pn)
                if nhom and not piv_kn[ct].empty:
                    piv_kn[ct] = piv_kn[ct][[c for c in nhom if c in piv_kn[ct].columns]]
            if nhom and not tong.empty:
                tong = tong.loc[[c for c in tong.index if c in nhom]]

            a1, a2 = st.columns([2, 3])
            with a1:
                hbars(tong["Ròng (tỷ)"] if not tong.empty else pd.Series(dtype=float),
                      f"Ròng cả kỳ {tu:%d/%m/%Y} → {D_TO:%d/%m/%Y}", "tỷ VND", color_sign=True,
                      height=max(260, 30 * len(tong)))
            with a2:
                ct_lk = next((c for c in ("netVal", "netMatch") if c in piv_kn), None)
                if ct_lk:
                    line(piv_kn[ct_lk].cumsum(), f"Luỹ kế {TEN_KN[ct_lk].lower()} theo nhóm", "tỷ VND",
                         height=max(260, 30 * len(tong)))
            TEN_TAN = {"D": "phiên", "W": "tuần", "M": "tháng"}[tan]
            luoi_ct(ct_kn, lambda ct: bars_stack(piv_kn[ct], f"{TEN_KN[ct]} theo {TEN_TAN}, chồng theo nhóm",
                                                 "tỷ VND"), ncol=1)
            b1, b2 = st.columns([3, 2])
            with b1:
                st.markdown("**Tổng hợp theo nhóm**")
                st.dataframe(tong, width="stretch")
            with b2:
                st.markdown("**Top mã mua / bán ròng trong kỳ**" + (" (nhóm đã chọn)" if nhom else ""))
                top = dl.flows_top_ma(tu, D_TO, nhom or None, tuple(san), n=10,
                                      chi_tieu=ct_lk or "netVal", pn=pn)
                st.dataframe(top, width="stretch", height=390)
            st.caption(f"Phân ngành: ICB cấp {cap} của Vietcap"
                       + (", tách riêng nhóm Vingroup" if vin else "") + ". "
                       "Nguồn: Vietcap IQ theo từng mã (lịch sử từ 2000, tách khớp lệnh / thoả thuận); "
                       "VNDirect bù các phiên Vietcap chưa có. Chọn đủ 3 sàn = không lọc sàn. Mã đã huỷ "
                       "niêm yết không có trong nguồn nên số các năm cũ thấp hơn tổng cấp sàn.")
            xl_kn.update({f"Nganh_{TEN_KN[ct]}"[:31].replace("/", "-"): piv_kn[ct] for ct in ct_kn})
            xl_kn.update({"Nganh_TongKy": tong, "Top_ma": top})

            # ---------------------------- soi 1 nhom: ma nao duoc mua / bi ban (khoi ngoai & tu doanh)
            st.subheader("🔍 Soi dòng tiền trong nhóm ngành (khối ngoại & tự doanh)")
            TEN_NGUON = {"kn": "Khối ngoại", "td": "Tự doanh", "ca": "Khối ngoại + tự doanh"}
            d0, d1, d2, d3 = st.columns([2, 2, 2, 1])
            nguon = d0.radio("Dòng tiền", list(TEN_NGUON), horizontal=True, key="soi_nguon",
                             format_func=TEN_NGUON.get)
            td_sec = dl.prop_sector(tu, D_TO, tuple(san), pn)
            kn_sec = dl.flows_sector(tu, D_TO, tuple(san), "M", "netVal", pn)[1]
            kn_sec = kn_sec["Ròng (tỷ)"] if not kn_sec.empty else pd.Series(dtype=float)
            xep = {"kn": kn_sec, "td": td_sec, "ca": kn_sec.add(td_sec, fill_value=0)}[nguon]
            thu_tu = list(xep.abs().sort_values(ascending=False).index)
            thu_tu = [x for x in thu_tu if x in nhom_all] + [x for x in nhom_all if x not in thu_tu]
            ng_soi = d1.selectbox("Nhóm ngành", thu_tu, index=thu_tu.index(nhom[0]) if nhom else 0,
                                  key=f"kn_soi_nhom_{cap}_{vin}",
                                  help="Mặc định là nhóm có dòng tiền ròng (mua hoặc bán) lớn nhất trong kỳ "
                                       "theo dòng tiền đang chọn")
            ct_soi = d2.radio("Khối ngoại tính theo", ["netVal", "netMatch"], horizontal=True, key="kn_soi_ct",
                              format_func=TEN_KN.get, disabled=nguon == "td")
            n_soi = d3.number_input("Số mã mỗi phía", 3, 30, 10, key="kn_soi_n")

            fs_td = dl.prop_stocks()
            if nguon != "kn" and not fs_td.empty and tu < fs_td.date.min():
                st.caption(f"Tự doanh theo mã chỉ có từ {fs_td.date.min():%d/%m/%Y} (VNDirect) — "
                           "trước mốc này phần tự doanh bằng 0.")
            if nguon != "kn":
                so_sanh = pd.DataFrame({"Khối ngoại ròng (tỷ)": kn_sec, "Tự doanh ròng (tỷ)": td_sec}).fillna(0)
                so_sanh["Tổng (tỷ)"] = so_sanh.sum(axis=1)
                so_sanh = so_sanh.sort_values("Tổng (tỷ)", ascending=False).round(1)
                f1, f2 = st.columns([2, 3])
                with f1:
                    hbars(td_sec, f"Tự doanh ròng theo nhóm {tu:%d/%m/%Y} → {D_TO:%d/%m/%Y}", "tỷ VND",
                          color_sign=True, height=max(260, 30 * len(td_sec)))
                with f2:
                    st.markdown("**Khối ngoại vs tự doanh theo nhóm**")
                    st.dataframe(so_sanh, width="stretch")
                xl_kn["TD_vs_KN_theo_nhom"] = so_sanh

            if nguon == "kn":
                bm, ts_ma = dl.flows_nhom_ma(tu, D_TO, ng_soi, tuple(san), ct_soi, pn)
                cot_r = "Ròng (tỷ)" if ct_soi == "netVal" else "Ròng khớp lệnh (tỷ)"
                ten_lk = f"{TEN_KN[ct_soi].lower()} khối ngoại"
            elif nguon == "td":
                bm, ts_ma = dl.prop_nhom_ma(tu, D_TO, ng_soi, tuple(san), pn)
                cot_r, ten_lk = "Ròng (tỷ)", "mua/bán ròng tự doanh"
            else:
                bm, ts_ma = dl.dong_tien_nhom(tu, D_TO, ng_soi, tuple(san), ct_soi, pn)
                cot_r, ten_lk = "Tổng KN + TD (tỷ)", "ròng khối ngoại + tự doanh"
            if bm.empty:
                st.caption(f"Nhóm này không có giao dịch {TEN_NGUON[nguon].lower()} trong kỳ.")
            else:
                r = bm[cot_r].dropna()
                mua, ban = r[r > 0], r[r < 0]
                k = st.columns(4)
                kpi(k[0], f"Ròng cả nhóm ({len(bm)} mã)", f"{r.sum():,.0f} tỷ")
                kpi(k[1], "Số mã mua ròng / bán ròng", f"{len(mua)} / {len(ban)}")
                kpi(k[2], "Mua ròng nhiều nhất",
                    f"{mua.idxmax()} {mua.max():+,.0f} tỷ" if len(mua) else "—")
                kpi(k[3], "Bán ròng nhiều nhất",
                    f"{ban.idxmin()} {ban.min():+,.0f} tỷ" if len(ban) else "—")
                if nguon == "ca":
                    ch = bm["Chiều"].value_counts()
                    st.caption(f"Khối ngoại và tự doanh **cùng chiều** ở {ch.get('Cùng chiều', 0)} mã, "
                               f"**ngược chiều** ở {ch.get('Ngược chiều', 0)} mã, "
                               f"chỉ một bên giao dịch ở {ch.get('Một phía', 0)} mã.")

                e1, e2 = st.columns(2)
                nguoi = TEN_NGUON[nguon].lower()
                with e1:
                    hbars(mua.head(n_soi), f"Được {nguoi} mua ròng nhiều nhất — {ng_soi}", "tỷ VND",
                          color=TH["pos"], height=max(200, 26 * min(n_soi, len(mua))))
                with e2:
                    hbars(ban.sort_values().head(n_soi), f"Bị {nguoi} bán ròng nhiều nhất — {ng_soi}",
                          "tỷ VND", color=TH["neg"], height=max(200, 26 * min(n_soi, len(ban))))

                chon_ma = list(mua.head(5).index) + list(ban.sort_values().head(5).index)
                ma_ve = st.multiselect("Mã vẽ luỹ kế", list(bm.index), default=chon_ma,
                                       key=f"soi_ma_{nguon}_{ng_soi}")
                if ma_ve:
                    lk = ts_ma[[m for m in ma_ve if m in ts_ma.columns]].fillna(0).cumsum()
                    tan_lk = {"D": None, "W": "W-FRI", "M": "ME"}[tan]
                    if tan_lk:
                        lk = lk.resample(tan_lk).last()
                    line(lk, f"Luỹ kế {ten_lk} từng mã — {ng_soi}", "tỷ VND", height=360)

                st.markdown(f"**Toàn bộ {len(bm)} mã trong nhóm {ng_soi} — {TEN_NGUON[nguon]}** "
                            f"({tu:%d/%m/%Y} → {D_TO:%d/%m/%Y}, sắp theo {cot_r.lower()})")

                def _mau_so(v):
                    if pd.isna(v) or v == 0:
                        return ""
                    return f"color: {TH['pos'] if v > 0 else TH['neg']}; font-weight: 600"
                to_mau = [c for c in ["Ròng (tỷ)", "Ròng khớp lệnh (tỷ)", "Thay đổi sở hữu (điểm %)",
                                      "Khối ngoại ròng (tỷ)", "Tự doanh ròng (tỷ)", "Tổng KN + TD (tỷ)"]
                          if c in bm.columns]
                st.dataframe(bm.style.map(_mau_so, subset=to_mau).format(precision=2),
                             width="stretch", height=min(600, 38 + 35 * len(bm)))
                st.caption("KN / GTGD, TD / GTGD = (mua + bán) / 2 chia GTGD toàn phiên của mã (GTGD từ Vietcap). "
                           "Sở hữu NN theo room Vietcap công bố. Tự doanh: VNDirect, chỉ có từ 05/2022; "
                           "Chiều = khối ngoại và tự doanh cùng mua/cùng bán ròng hay ngược nhau.")
                tien_to = {"kn": "KN", "td": "TD", "ca": "KN_TD"}[nguon]
                xl_kn[f"Soi_{tien_to}_{ng_soi}"[:31].replace("/", "-")] = bm
                xl_kn[f"Soi_{tien_to}_{ng_soi}_ngay"[:31].replace("/", "-")] = ts_ma

        st.subheader("Khối ngoại châu Á theo tháng (triệu USD)")
        fr = dl.flows_region_df(D_FROM, D_TO)
        line(fr, "", "triệu USD")
        st.dataframe(fr.iloc[::-1], width="stretch")
        xl_kn["ChauA_theo_thang"] = fr
        dl_button(fv, "KhoiNgoai", sheets=xl_kn)

    with t[2]:
        st.subheader("Độ rộng thị trường")
        br = cut(dl.breadth_df(), MONTHS)
        line(br[["% mã trên MA20", "% mã trên MA50", "% mã trên MA100", "% mã trên MA200"]],
             "% cổ phiếu nằm trên đường trung bình", "%", zero=True)
        c1, c2 = st.columns(2)
        with c1:
            line(br[["A/D line (luỹ kế)"]], "A/D line (luỹ kế số mã tăng - giảm)", "số mã luỹ kế")
        with c2:
            line(br[["Số mã đỉnh 52 tuần", "Số mã đáy 52 tuần"]], "Đỉnh / đáy 52 tuần", "số mã", zero=True)
        bars(br, "Tăng - Giảm", "Chênh lệch số mã tăng - giảm theo phiên", "số mã")
        st.dataframe(br.tail(15).iloc[::-1], width="stretch")
        dl_button(br, "DoRongThiTruong")

    with t[3]:
        st.subheader("Số cổ phiếu nằm dưới MA50 / MA200 / MA300")
        br = cut(dl.breadth_df(), MONTHS)
        line(br[["% dưới MA50", "% dưới MA200", "% dưới MA300"]],
             "% cổ phiếu nằm dưới MA (toàn thị trường)", "%", zero=True)
        w = st.selectbox("Đường MA", [50, 200, 300])
        line(br[[f"Dưới MA{w} - HOSE", f"Dưới MA{w} - HNX", f"Dưới MA{w} - UPCOM",
                 f"Dưới MA{w} - Toàn TT"]], f"Số mã dưới MA{w} theo sàn", "số mã", zero=True)
        cols = [c for c in br.columns if "MA50" in c or "MA200" in c or "MA300" in c]
        st.dataframe(br[cols].tail(15).iloc[::-1], width="stretch")
        dl_button(br[cols], "DuoiMA")

    with t[4]:
        st.subheader("Vốn hoá theo nhóm quy mô")
        sec, caps = dl.sectors(since=SINCE, end=SINCE_TO)
        idx = dl.load("indices")
        tvh = dl.tv()
        lv = (tvh[tvh.tv_symbol.isin(["HOSE:VNINDEX", "HOSE:VN30", "HOSE:VNMIDCAP", "HOSE:VNSMALLCAP"])]
              .pivot_table(index="date", columns="tv_symbol", values="close", aggfunc="last")
              .rename(columns={"HOSE:VNINDEX": "VN-Index", "HOSE:VN30": "VN30",
                               "HOSE:VNMIDCAP": "VNMidcap", "HOSE:VNSMALLCAP": "VNSmallcap"}))
        lv = cut(lv, MONTHS)
        reb = lv / lv.iloc[0] * 100
        c1, c2 = st.columns(2)
        with c1:
            line(reb, "VN30 / Midcap / Smallcap vs VN-Index (rebase 100)", "rebase 100")
        with c2:
            line(caps, "Vốn hoá ước tính theo nhóm (nghìn tỷ VND)", "nghìn tỷ", zero=True)
        st.caption("Nhóm quy mô chia theo thứ hạng vốn hoá HOSE cuối kỳ (top 30 / 31-100 / còn lại), "
                   "vốn hoá = số CP lưu hành hiện tại × giá điều chỉnh. Rổ chính thức là 4 cột chỉ số bên trái.")
        dl_button(reb, "VonHoaNhom", sheets={"ChiSo": lv, "Rebase100": reb, "VonHoa": caps})
        _ = idx

    with t[5]:
        st.subheader("Diễn biến theo ngành (gia quyền vốn hoá, HOSE)")
        sec, _ = dl.sectors(since=SINCE, end=SINCE_TO)
        line(sec, "Chỉ số ngành rebase 100 đầu kỳ", "rebase 100", height=420)
        ss = dl.sector_summary(months=MONTHS, end=D_TO)
        st.dataframe(ss, width="stretch")
        dl_button(sec, "Nganh", sheets={"ChiSoNganh": sec, "TongKet": ss})

    with t[6]:
        st.subheader("Định giá thị trường")
        vw = dl.load("valuation_wide")
        c1, c2 = st.columns([1, 2])
        with c1:
            code = st.multiselect("Rổ", sorted(vw.code.unique()), default=["VNINDEX", "VN30"])
        with c2:
            cts = chon_ct("Chỉ tiêu hiển thị (áp cho mọi khung bên dưới)",
                          ["pe", "pb", "ps", "div_yield", "roe_ttm", "earnings_yield", "marketcap", "ln_ttm"],
                          key="ct_dinhgia")
        xl = {}

        st.markdown("**Theo rổ**")
        p_ro = {ct: vw[vw.code.isin(code)].pivot_table(index="date", columns="code", values=ct,
                                                         aggfunc="last") for ct in cts}
        luoi_ct(cts, lambda ct: line(cut(p_ro[ct]), f"{TEN_CT[ct]} theo rổ", don_vi(ct)))
        xl.update({ten_sheet("Ro", ct): p_ro[ct] for ct in cts})

        st.markdown("**Loại nhóm Vingroup**")
        va = dl.load("valuation_adjusted")
        CT_ADJ = {"pe": "pe", "pb": "pb", "roe_ttm": "roe"}   # chi tieu co ban loai nhom Vin
        ct_adj = [ct for ct in cts if ct in CT_ADJ]
        if va.empty:
            st.caption("Chưa có dữ liệu valuation-adjusted.csv.")
        elif not ct_adj:
            st.caption("Khung loại nhóm Vingroup chỉ có P/E, P/B, ROE TTM — chọn thêm 1 trong 3 ở trên.")
        else:
            vi = st.selectbox("Rổ (đã điều chỉnh)", sorted(va["index"].unique()))
            dva = va[va["index"] == vi].set_index("date").sort_index()

            def _adj(ct):
                c0 = CT_ADJ[ct]
                d = dva[[c0, f"{c0}_adj"]].rename(columns={c0: "Gốc", f"{c0}_adj": "Loại nhóm Vin"})
                if ct == "roe_ttm":
                    d = d * 100
                xl[ten_sheet("LoaiVin", ct)] = d
                line(cut(d), f"{vi} {TEN_CT[ct]}: trước / sau khi loại VIC-VHM-VRE-VPL",
                     "%" if ct == "roe_ttm" else "lần")
            luoi_ct(ct_adj, _adj)

        st.markdown("**Định giá theo ngành ICB**")
        sw = dl.load("sectors_wide")
        ng = st.multiselect("Ngành", sorted(sw.ten_nganh.dropna().unique()),
                            default=["Ngân hàng", "Bất động sản", "Dịch vụ tài chính"])
        ct_ng = [ct for ct in cts if ct in sw.columns]
        p_ng = {ct: sw[sw.ten_nganh.isin(ng)].pivot_table(index="date", columns="ten_nganh", values=ct,
                                                            aggfunc="last") for ct in ct_ng}
        luoi_ct(ct_ng, lambda ct: line(cut(p_ng[ct]), f"{TEN_CT[ct]} theo ngành ICB", don_vi(ct)))
        xl.update({ten_sheet("Nganh", ct): p_ng[ct] for ct in ct_ng})
        dl_button(p_ro[cts[0]], "DinhGia", sheets=xl)

    with t[7]:
        st.subheader("Tăng trưởng EPS & lợi nhuận toàn thị trường")
        e = dl.eps_market_df()
        TEN = {"VNINDEX": "VN-Index (toàn HOSE)", "VN30": "VN30", "HNX": "HNX", "UPCOM": "UPCoM"}
        ro = st.multiselect("Rổ", list(TEN), default=["VNINDEX", "VN30"],
                            format_func=lambda k: TEN[k])
        if not ro:
            ro = ["VNINDEX"]

        cur = e[(e.code == ro[0]) & (e["Ngày"] <= D_TO)].set_index("Ngày").sort_index()
        eps_c = cur["EPS TTM (điểm)"].dropna()
        g_c = cur["Tăng trưởng EPS (%)"].dropna()
        ln_c = cur["LN TTM (tỷ)"].dropna()
        gl_c = cur["Tăng trưởng LN TTM (%)"].dropna()
        c = st.columns(5)
        kpi(c[0], f"EPS TTM {TEN[ro[0]]}", num(eps_c.iloc[-1], 1) + " đ",
            f"{g_c.iloc[-1]:+.1f}% so cùng kỳ" if len(g_c) else None)
        kpi(c[1], "LN TTM", f"{ln_c.iloc[-1] / 1e3:,.0f} ngh.tỷ",
            f"{gl_c.iloc[-1]:+.1f}% so cùng kỳ" if len(gl_c) else None)
        kpi(c[2], "P/E", num(cur["P/E"].dropna().iloc[-1], 2),
            f"P/B {cur['P/B'].dropna().iloc[-1]:.2f}" if cur["P/B"].notna().any() else None)
        kpi(c[3], "ROE TTM", num(cur["ROE TTM (%)"].dropna().iloc[-1], 1) + "%")
        peg = (cur["P/E"].dropna().iloc[-1] / g_c.iloc[-1]) if len(g_c) and g_c.iloc[-1] > 0 else np.nan
        kpi(c[4], "PEG (P/E ÷ tăng trưởng)", num(peg, 2))
        st.caption(f"Số liệu đến {eps_c.index.max():%d/%m/%Y}. EPS quy về **điểm chỉ số** nên so sánh "
                   "được theo thời gian; LN TTM là tổng lợi nhuận sau thuế 12 tháng của rổ. "
                   "Nguồn: VNDirect (valuation-wide.csv).")

        piv_eps = e[e.code.isin(ro)].pivot_table(index="Ngày", columns="code",
                                                 values="EPS TTM (điểm)", aggfunc="last")
        piv_g = e[e.code.isin(ro)].pivot_table(index="Ngày", columns="code",
                                               values="Tăng trưởng EPS (%)", aggfunc="last")
        piv_ln = e[e.code.isin(ro)].pivot_table(index="Ngày", columns="code",
                                                values="LN TTM (tỷ)", aggfunc="last") / 1e3
        piv_eps.columns = [TEN.get(c, c) for c in piv_eps.columns]
        piv_g.columns = [TEN.get(c, c) for c in piv_g.columns]
        piv_ln.columns = [TEN.get(c, c) for c in piv_ln.columns]

        a1, a2 = st.columns(2)
        with a1:
            line(cut(piv_eps), "EPS TTM (điểm chỉ số)", "điểm", height=300)
        with a2:
            if len(ro) == 1:
                bars(cut(piv_g), piv_g.columns[0], "Tăng trưởng EPS so cùng kỳ", "%", height=300)
            else:
                line(cut(piv_g), "Tăng trưởng EPS so cùng kỳ", "%", height=300, zero=True)
        line(cut(piv_ln), "Lợi nhuận sau thuế TTM của rổ", "nghìn tỷ VND", height=280)

        st.markdown("**Tăng trưởng lợi nhuận theo ngành (ICB)**")
        cap = st.radio("Cấp ngành", [2, 3], horizontal=True,
                       format_func=lambda x: f"Cấp {x}")
        sec_e = dl.eps_sector_df(cap, SINCE_TO)
        b1, b2 = st.columns([3, 2])
        with b1:
            hbars(sec_e["Tăng trưởng LN TTM (%)"], "LN TTM so cùng kỳ theo ngành", "%",
                  color="#1baf7a")
        with b2:
            st.dataframe(sec_e, width="stretch")
        st.caption("Ngành có nền lợi nhuận rất thấp năm trước (Dầu khí, Truyền thông…) cho ra "
                   "% tăng/giảm rất lớn — đọc kèm cột LN TTM tuyệt đối.")

        q = cur[["EPS TTM (điểm)", "Tăng trưởng EPS (%)", "LN TTM (tỷ)",
                 "Tăng trưởng LN TTM (%)", "P/E", "P/B"]].resample("QE").last().round(2)
        q.index = [f"{d.year}Q{d.quarter}" for d in q.index]
        q.index.name = "Quý"
        st.dataframe(q.tail(16).iloc[::-1], width="stretch")
        dl_button(piv_eps, "TangTruongEPS",
                  sheets={"EPS_TTM": piv_eps, "Tang_truong_EPS": piv_g, "LN_TTM": piv_ln,
                          "Theo_quy": q, "Theo_nganh": sec_e})

    with t[8]:
        st.subheader("Tra cứu cổ phiếu")
        m = dl.meta()
        ma_cp = st.selectbox("Mã", sorted(m.index), index=int(np.where(np.array(sorted(m.index)) == "FPT")[0][0])
                             if "FPT" in m.index else 0)
        info = m.loc[ma_cp]
        c = st.columns(4)
        c[0].metric("Sàn", str(info.exchange))
        c[1].metric("Ngành (ICB Vietcap)", str(info.nhom))
        c[2].metric("Vốn hoá (nghìn tỷ)", num(info.market_cap_basic / 1e12, 1)
                    if pd.notna(info.market_cap_basic) else "—")
        c[3].metric("Số CP (triệu)", num(info.total_shares_outstanding_fundamental / 1e6, 0)
                    if pd.notna(info.total_shares_outstanding_fundamental) else "—")
        d = dl.tv()
        d = d[d.symbol == ma_cp].set_index("date").sort_index()
        d = cut(d, MONTHS)
        c1, c2 = st.columns([3, 2])
        with c1:
            line(d[["close"]].rename(columns={"close": ma_cp}), f"Giá điều chỉnh {ma_cp}", "VND")
        with c2:
            bars(d.assign(gtgd=d.value_approx / 1e9), "gtgd", "GTGD (tỷ VND)", "tỷ VND", color_sign=False)
        s = dl.stock_val(ma_cp)
        if s.empty:
            st.caption(f"VNDirect không có số liệu định giá cho {ma_cp}.")
        else:
            ct_cp = chon_ct("Chỉ tiêu định giá", ["pe", "pb", "ps", "roe_ttm", "div_yield"],
                            key="ct_cophieu")
            luoi_ct(ct_cp, lambda ct: line(cut(s[[ct]].rename(columns={ct: ma_cp}), MONTHS),
                                           f"{TEN_CT[ct]} của {ma_cp}", don_vi(ct)))
        out = d[["close", "volume", "value_approx"]]
        dl_button(out, f"CoPhieu_{ma_cp}", sheets={"Gia": out, "DinhGia": s})

# =========================================================== KHU VUC / THE GIOI
elif PAGE == "🌏 Khu vực & thế giới":
    st.title("Khu vực & thế giới")
    t = tabs_bb(["Chỉ số", "Thanh khoản", "Khối ngoại", "Định giá"], "kv")
    idx = dl.load("indices")

    with t[0]:
        codes = st.multiselect("Chỉ số", sorted(idx.index_code.unique()),
                               default=["VNINDEX", "KOSPI", "TAIEX", "SET", "JCI", "SSEC", "N225", "SP500"])
        p = idx[idx.index_code.isin(codes)].pivot_table(index="date", columns="index_code",
                                                        values="close", aggfunc="last")
        p = cut(p, MONTHS)
        reb = p / p.apply(lambda s: s.dropna().iloc[0] if s.notna().any() else np.nan) * 100
        line(reb, "Rebase 100 đầu kỳ", "rebase 100", height=420)
        perf = pd.DataFrame({"Hiệu suất kỳ (%)": (reb.iloc[-1] - 100).round(1)}).sort_values(
            "Hiệu suất kỳ (%)", ascending=False)
        st.dataframe(perf, width="stretch")
        dl_button(reb, "ChiSoKhuVuc", sheets={"Rebase100": reb, "Gia": p, "HieuSuat": perf})

    with t[1]:
        st.subheader("Giá trị giao dịch quy USD (triệu USD / phiên)")
        codes = st.multiselect("Thị trường", sorted(idx[idx.value_usd.notna()].index_code.unique()),
                               default=["VNINDEX", "KOSPI", "TAIEX", "SET", "JCI", "FBMKLCI"], key="liq")
        v = idx[idx.index_code.isin(codes)].pivot_table(index="date", columns="index_code",
                                                        values="value_usd", aggfunc="last")
        v = cut(v, MONTHS)
        line(v.rolling(20).mean(), "Bình quân 20 phiên", "triệu USD", zero=True)
        mm = v.copy()
        mm.index = mm.index.to_period("M")
        mm = mm.groupby(level=0).mean().round(0)
        mm.index = mm.index.astype(str)
        st.dataframe(mm.iloc[::-1], width="stretch")
        dl_button(v, "ThanhKhoanKhuVuc", sheets={"Ngay": v, "BinhQuanThang": mm})

    with t[2]:
        fr = dl.flows_region_df(D_FROM, D_TO)
        line(fr, "Khối ngoại mua/bán ròng theo tháng (triệu USD)", "triệu USD", height=380)
        line(fr.cumsum(), "Luỹ kế", "triệu USD", height=300)
        st.dataframe(fr.iloc[::-1], width="stretch")
        dl_button(fr, "KhoiNgoaiKhuVuc", sheets={"TheoThang": fr, "LuyKe": fr.cumsum()})

    with t[3]:
        vr = dl.load("valuation_region_wide")
        c1, c2 = st.columns(2)
        codes = c1.multiselect("Thị trường", sorted(vr.code.unique()),
                               default=[c for c in ["TV_VN", "TV_KR", "TV_TW", "TV_TH", "TV_ID", "TV_CN"]
                                        if c in set(vr.code)])
        with c2:
            rs = chon_ct("Chỉ tiêu", ["pe", "pb", "roe_ttm", "div_yield", "earnings_yield", "marketcap"],
                         key="ct_khuvuc")
        pv = {r: vr[vr.code.isin(codes)].pivot_table(index="date", columns="code", values=r, aggfunc="last")
              for r in rs}
        luoi_ct(rs, lambda r: line(cut(pv[r]), f"{TEN_CT[r]} theo thị trường", don_vi(r)))
        p = pv[rs[0]]
        snap = (vr.sort_values("date").groupby("code").last()[["date", "pe", "pb", "roe_ttm",
                                                               "div_yield", "marketcap"]])
        st.dataframe(snap.sort_values("pe"), width="stretch")
        dl_button(p, "DinhGiaKhuVuc", sheets={**{ten_sheet("KV", r): pv[r] for r in rs},
                                              "SnapshotMoiNhat": snap})

# =============================================================== VI MO & TIEN TE
elif PAGE == "🏦 Vĩ mô & tiền tệ":
    st.title("Vĩ mô & tiền tệ")
    tm, mv = dl.tm, dl.mv
    # 07/10/2026: tab nhom theo KHUNG PHAN TICH VI MO chuan (dl.KHUNG_VI_MO): moi khoi noi dung ben duoi
    # gan vao tab bang T["..."]; mot tab co the nhan nhieu khoi (theo thu tu code).
    TEN_TAB = list(dl.KHUNG_VI_MO)
    T = dict(zip(TEN_TAB, tabs_bb(TEN_TAB, "vimo")))

    # ------------------------------------------------------ 1. BANG DIEU KHIEN
    with T["Bảng điều khiển"]:
        # 07/10/2026: CPI, XNK, IIP, ban le, FDI lay tu Cuc Thong ke (nso-fetcher); IMF chi bu lich su truoc 2023
        cpi, d_cpi = dl.nm_last("CPI|YOY|CPI chung", pct=True)
        if pd.isna(cpi):
            cpi, d_cpi = dl.mv_last("CPI tong (chi so, 2024=100) - YoY %")
        fxc, d_fx = dl.tm_last("fx_central")
        vcb, _ = dl.tm_last("fx_vcb_sell")
        ion, d_ion = dl.tm_last("ib_on")
        omo, d_omo = dl.tm_last("omo_net_outstanding")
        tin, d_tin = dl.tm_last("credit_growth_ytd")
        m2g, d_m2 = dl.tm_last("m2_growth_yoy")
        res, d_res = dl.tm_last("fx_reserves")
        cov, _ = dl.tm_last("fx_import_cover")
        dep, _ = dl.tm_last("deposit_12m_avg")

        c = st.columns(4)
        kpi(c[0], "CPI so cùng kỳ", num(cpi, 2) + "%",
            f"đến {d_cpi:%m/%Y}" if d_cpi is not None else None)
        kpi(c[1], "Tỷ giá trung tâm", num(fxc, 0),
            f"VCB bán {vcb:,.0f}" if pd.notna(vcb) else None)
        kpi(c[2], "LNH qua đêm", num(ion, 2) + "%",
            f"HĐ 12T bình quân {dep:.2f}%" if pd.notna(dep) else None)
        kpi(c[3], "Bơm ròng đang lưu hành", f"{omo / 1e3:,.1f} ngh.tỷ" if pd.notna(omo) else "—",
            f"đến {d_omo:%d/%m/%Y}" if d_omo is not None else None)

        c = st.columns(4)
        kpi(c[0], "Tăng trưởng tín dụng YTD", num(tin, 2) + "%",
            f"đến {d_tin:%m/%Y}" if d_tin is not None else None)
        kpi(c[1], "M2 so cùng kỳ", num(m2g, 2) + "%",
            f"đến {d_m2:%m/%Y}" if d_m2 is not None else None)
        gdp_g, d_gdp, st_gdp = dl.gdp_last()
        kpi(c[2], f"GDP quý {(d_gdp.month - 1) // 3 + 1}/{d_gdp.year}" if d_gdp is not None else "GDP quý",
            num(gdp_g, 2) + "%", f"so cùng kỳ ({st_gdp.lower() or 'NSO'})" if pd.notna(gdp_g) else None,
            help=f"Dự trữ ngoại hối: {res / 1e3:,.1f} tỷ USD ({cov:.1f} tháng nhập khẩu) — xem tab Tỷ giá & dự trữ."
            if pd.notna(res) and pd.notna(cov) else None)
        xnk_m = dl.trade_nso()                              # trieu USD/thang, NSO tu 2023
        nam = xnk_m.index.max().year if len(xnk_m) else None
        xs = xnk_m[xnk_m.index.year == nam] if nam else xnk_m
        cc = (xs["Xuất khẩu"].sum() - xs["Nhập khẩu"].sum()) / 1e3 if nam else np.nan
        kpi(c[3], f"Cán cân TM {nam} (luỹ kế {xs.index.max():%m/%Y})" if nam else "Cán cân TM",
            f"{cc:+,.1f} tỷ USD" if pd.notna(cc) else "—",
            f"XK {xs['Xuất khẩu'].sum() / 1e3:,.0f} tỷ USD" if nam else None)

        a1, a2 = st.columns(2)
        with a1:
            cpi_y = dl.cpi_nso("YOY")
            cot = [c for c in ("CPI chung", "Lạm phát cơ bản") if c in cpi_y.columns]
            line(cut(cpi_y[cot]) if cot else cut(mv(contains="CPI tong").filter(like="YoY")),
                 "Lạm phát CPI so cùng kỳ (Cục Thống kê)", "%", height=280, zero=True)
            line(cut(tm(["ib_on", "ib_1w", "ib_3m", "policy_refinance"])),
                 "Lãi suất liên ngân hàng & lãi suất tái cấp vốn", "%/năm", height=280)
        with a2:
            line(cut(tm(["fx_central", "fx_band_ceiling", "fx_vcb_sell", "fx_free_sell"])),
                 "Tỷ giá USD/VND", "VND/USD", height=280)
            d = cut(tm(["omo_net_outstanding"]))
            if not d.empty:
                bars(d, d.columns[0], "NHNN bơm / hút ròng đang lưu hành", "tỷ VND", height=280)

    # ------------------------------------------------------------ 2. LAM PHAT
    with T["Giá cả"]:
        st.subheader("Lạm phát (Cục Thống kê)")
        KIEU = {"So cùng kỳ năm trước": "YOY", "So tháng trước": "MOM", "So tháng 12 năm trước": "VS_DEC",
                "Bình quân từ đầu năm so cùng kỳ": "AVG_YTD_YOY", "Chỉ số mức 2024=100 (IMF)": "IMF"}
        kieu = filt("radio", "Chỉ tiêu", list(KIEU), key="cpi_kieu", horizontal=True)
        if KIEU[kieu] == "IMF":
            cpi_all = mv(group="CPI")
            cot = [c for c in cpi_all.columns if not c.endswith("%")]
            d = cut(cpi_all[cot])
            d.columns = [c.replace("CPI ", "") for c in d.columns]
            line(d, "CPI theo nhóm COICOP — chỉ số 2024=100 (IMF SDMX)", "chỉ số", height=360)
            dl_button(d, "CPI_IMF")
        else:
            c_all = dl.cpi_nso(KIEU[kieu])
            chinh = [c for c in ("CPI chung", "Lạm phát cơ bản") if c in c_all.columns]
            vang = [c for c in ("Chỉ số giá vàng", "Chỉ số giá đô la Mỹ") if c in c_all.columns]
            nhom = [c for c in c_all.columns if c not in chinh + vang]
            line(cut(c_all[chinh]), f"CPI chung & lạm phát cơ bản — {kieu.lower()}", "%", height=300, zero=True)
            uu_tien = [c for c in ("Hàng ăn và dịch vụ ăn uống", "Nhà ở, điện, nước, chất đốt và vật liệu xây dựng",
                                   "Giao thông", "Giáo dục", "Thuốc và dịch vụ y tế") if c in nhom]
            chon = filt("multiselect", "Nhóm hàng", nhom, default=(uu_tien or nhom)[:4], key="cpi_nhom")
            if chon:
                line(cut(c_all[chon]), f"CPI theo nhóm hàng — {kieu.lower()}", "%", height=340, zero=True)
            c1, c2 = st.columns(2)
            with c1:
                if vang:
                    line(cut(c_all[vang]), f"Chỉ số giá vàng & đô la Mỹ — {kieu.lower()}", "%",
                         height=300, zero=True)
            with c2:
                if nhom:
                    bang = c_all[nhom].ffill().iloc[-1].dropna().rename_axis("Nhóm hàng")
                    hbars(bang.sort_values(ascending=False),
                          f"CPI theo nhóm, kỳ {c_all.index.max():%m/%Y} — {kieu.lower()}", "%",
                          color="#eb6834", height=300)
            dl_button(cut(c_all), "CPI_NSO")
        st.caption("Nguồn: Cục Thống kê (NSO) — PX-Web niên giám (CPI tháng theo nhóm hàng 2010–2025, số đã chốt) "
                   "nối với Biểu số liệu báo cáo KT-XH tháng (01/2023–nay; lạm phát cơ bản, dịch vụ y tế/giáo dục "
                   "chỉ có ở báo cáo tháng). Chỉ số mức 2024=100 giữ từ IMF. Cập nhật thứ Hai: bước `nso`, `nso-monthly`.")

    # ------------------------------------------------------ 3. TY GIA & DU TRU
    with T["Đối ngoại"]:
        st.subheader("Tỷ giá & dự trữ ngoại hối")
        line(cut(tm(["fx_central", "fx_band_ceiling", "fx_band_floor", "fx_vcb_sell",
                     "fx_vcb_transfer", "fx_free_sell", "fx_sbv_sell_ref"])),
             "Tỷ giá USD/VND: trung tâm, biên độ, ngân hàng, chợ đen", "VND/USD", height=360)
        c1, c2 = st.columns(2)
        with c1:
            line(cut(tm(["fx_vcb_sell_vs_ceiling"])),
                 "VCB bán so với trần biên độ (âm = còn dư địa)", "%", height=280)
        with c2:
            line(cut(tm(["swap_on", "swap_1m", "swap_3m"])),
                 "Chênh lãi suất VND - USD (swap point)", "điểm %", height=280, zero=True)
        c3, c4 = st.columns(2)
        with c3:
            d = tm(["fx_reserves"]) / 1e3
            if not d.empty:
                d.columns = ["Dự trữ ngoại hối"]
            line(cut(d), "Dự trữ ngoại hối (gồm vàng)", "tỷ USD", height=280)
        with c4:
            line(cut(tm(["fx_import_cover"])), "Dự trữ tính theo tháng nhập khẩu", "tháng",
                 height=280)
        dl_button(cut(tm(["fx_central", "fx_band_ceiling", "fx_band_floor", "fx_vcb_sell",
                          "fx_free_sell", "fx_reserves", "fx_import_cover"])), "TyGia_DuTru")

    # --------------------------------------------- 4. LAI SUAT & THANH KHOAN
    with T["Tiền tệ & thanh khoản"]:
        st.subheader("Lãi suất & thanh khoản hệ thống")
        line(cut(tm(["ib_on", "ib_1w", "ib_2w", "ib_1m", "ib_3m", "ib_6m"])),
             "Lãi suất liên ngân hàng theo kỳ hạn", "%/năm", height=320)
        c1, c2 = st.columns(2)
        with c1:
            line(cut(tm(["policy_refinance", "policy_rediscount", "omo_win_7d_rate", "ib_on"])),
                 "Lãi suất điều hành vs liên ngân hàng", "%/năm", height=280)
        with c2:
            line(cut(tm(["ib_spread_policy", "ib_curve_1m_on"])),
                 "Chênh lệch qua đêm - tái cấp vốn · độ dốc 1T - qua đêm", "điểm %",
                 height=280, zero=True)
        st.markdown("**NHNN bơm / hút**")
        line(cut(tm(["omo_outstanding", "bill_outstanding", "omo_net_outstanding"])),
             "Repo đang lưu hành (bơm) · tín phiếu (âm = hút) · ròng", "tỷ VND",
             height=300, zero=True)
        c3, c4 = st.columns(2)
        with c3:
            dn = cut(tm(["omo_net_daily"]))
            if not dn.empty:
                bars(dn, dn.columns[0], "Bơm / hút ròng trong ngày", "tỷ VND", height=260)
        with c4:
            line(cut(tm(["deposit_1m_avg", "deposit_6m_avg", "deposit_12m_avg",
                         "deposit_12m_big4", "deposit_12m_max"])),
                 "Lãi suất huy động", "%/năm", height=260)
        line(cut(tm(["lending_rate_avg", "deposit_rate_avg_vcb", "lending_deposit_spread"])),
             "Lãi suất cho vay bình quân & chênh lệch cho vay - huy động (VCB công bố)",
             "%/năm · điểm %", height=280)
        dl_button(cut(tm(["ib_on", "ib_1w", "ib_1m", "ib_3m", "policy_refinance",
                          "omo_net_outstanding", "deposit_12m_avg", "lending_rate_avg"])),
                  "LaiSuat_ThanhKhoan")

    # -------------------------------------------------- 5. TIN DUNG & TIEN TE
    with T["Tiền tệ & thanh khoản"]:
        st.subheader("Tín dụng & cung tiền")
        c1, c2 = st.columns(2)
        with c1:
            line(cut(tm(["credit_growth_ytd"])), "Tăng trưởng tín dụng luỹ kế từ đầu năm",
                 "%", height=280, zero=True)
        with c2:
            line(cut(tm(["m2_growth_yoy", "m2_growth", "deposit_growth_yoy"])),
                 "Tăng trưởng M2 & tiền gửi", "%", height=280, zero=True)
        c3, c4 = st.columns(2)
        with c3:
            d = tm(["credit_outstanding", "m2"]) / 1e6
            line(cut(d), "Quy mô tín dụng & M2", "triệu tỷ VND", height=280)
        with c4:
            line(cut(tm(["credit_deposit_gap", "cash_ratio_m2"])),
                 "Chênh tăng trưởng tín dụng - huy động · tỷ trọng tiền mặt trên M2",
                 "% · điểm %", height=280, zero=True)
        st.caption("LDR, tỷ lệ vốn ngắn hạn cho vay trung dài hạn, CAR và quy mô hệ thống: "
                   "xem tab **An toàn hệ thống NH**.")
        dl_button(cut(tm(["credit_growth_ytd", "credit_outstanding", "m2", "m2_growth_yoy",
                          "deposit_growth_yoy", "credit_deposit_gap"])), "TinDung_TienTe")

    # ------------------------------------------------ 6. AN TOAN HE THONG NH
    with T["Hệ thống ngân hàng"]:
        st.subheader("Chỉ tiêu an toàn hệ thống ngân hàng")
        st.caption("Nguồn: NHNN — *Thống kê một số chỉ tiêu cơ bản* (tháng, từ 04/2013) và *Tỷ lệ an "
                   "toàn vốn*; CBTT từng ngân hàng (CAR bán niên); BCTC nhóm NH niêm yết (quý). "
                   "Nét liền = thực tế, nét đứt = trần / mức tối thiểu theo quy định.")
        w_ = dl.tm_wide(dl._mtime(dl.TM_WIDE))

        def s_(sid):
            return w_[sid].dropna() if sid in w_.columns else pd.Series(dtype=float)

        def cuoi(sid):
            s = s_(sid)
            s = s[s.index <= D_TO]
            return (s.iloc[-1], s.index[-1]) if len(s) else (np.nan, None)

        def yoy_(s):
            s = s[s.index <= D_TO]
            if len(s) < 2:
                return np.nan
            moc = s.index[-1] - pd.DateOffset(years=1)
            truoc = s[(s.index >= moc - pd.Timedelta("20D")) & (s.index <= moc + pd.Timedelta("20D"))]
            # khong co dung ky cung ky (NHNN khuyet 12/2024-10/2025) -> khong tinh, tranh so 19 thang
            return (s.iloc[-1] / truoc.iloc[-1] - 1) * 100 if len(truoc) else np.nan

        # CAR noi 2 che do bao cao: toi thieu (TT36, 2013-2019) va nhom ap dung TT41 (2024-)
        car_ht = pd.DataFrame({
            "Toàn hệ thống": s_("car_min_system").combine_first(s_("car_tt41")),
            "NHTM Nhà nước": s_("car_min_soe").combine_first(s_("car_tt41_soe")),
            "NHTM cổ phần": s_("car_min_jsc").combine_first(s_("car_tt41_jsc")),
            # chuoi SONG SONG (quy, 2008-): pham vi toan bo to chuc nhan tien gui -> lap 2020-06/2024
            "Toàn bộ TCTD (IMF FSI)": s_("car_imf_system"),
        })
        car_ht.index.name = "Ngày"
        # 8% truoc TT13/2010 -> 9% (TT13/2010, TT36/2014) -> 8% (TT41/2016 ap dung tu 2020)
        car_toi_thieu = pd.Series([8.0, 9.0, 8.0], index=[pd.Timestamp("2008-01-01"),
                                                          pd.Timestamp("2010-10-01"),
                                                          pd.Timestamp("2020-01-01")])

        ldr, d_ldr = cuoi("ldr_system")
        ldr_tran, _ = cuoi("ldr_cap")
        sfl, d_sfl = cuoi("sfl_system")
        sfl_tran, _ = cuoi("sfl_cap")
        car_s = car_ht["Toàn hệ thống"].dropna()
        car_s = car_s[car_s.index <= D_TO]
        ts = s_("bank_total_assets")
        vdl = s_("bank_charter_capital")

        c = st.columns(5)
        kpi(c[0], "LDR toàn hệ thống", num(ldr, 2) + "%",
            f"cách trần {ldr_tran - ldr:.1f} điểm %" if pd.notna(ldr_tran) and pd.notna(ldr) else None,
            help=f"Kỳ {d_ldr:%m/%Y}. Trần {ldr_tran:.0f}% theo TT22/2019 (định nghĩa LDR của trần "
                 "có điều chỉnh, không trùng hoàn toàn số NHNN thống kê)." if d_ldr is not None else None)
        kpi(c[1], "Vốn NH cho vay trung dài hạn", num(sfl, 2) + "%",
            f"cách trần {sfl_tran - sfl:.1f} điểm %" if pd.notna(sfl_tran) and pd.notna(sfl) else None,
            help=f"Kỳ {d_sfl:%m/%Y}. Trần hiện hành {sfl_tran:.0f}%." if d_sfl is not None else None)
        kpi(c[2], "CAR toàn hệ thống",
            num(car_s.iloc[-1], 2) + "%" if len(car_s) else "—",
            f"trên mức tối thiểu 8%: {car_s.iloc[-1] - 8:+.1f} điểm %" if len(car_s) else None,
            help=f"Kỳ {car_s.index[-1]:%m/%Y}, nhóm ngân hàng áp dụng TT41." if len(car_s) else None)
        kpi(c[3], "Tổng tài sản TCTD",
            f"{ts[ts.index <= D_TO].iloc[-1] / 1e6:,.2f} triệu tỷ" if len(ts) else "—",
            f"{yoy_(ts):+.1f}% so cùng kỳ" if pd.notna(yoy_(ts)) else None)
        kpi(c[4], "Vốn điều lệ TCTD",
            f"{vdl[vdl.index <= D_TO].iloc[-1] / 1e6:,.2f} triệu tỷ" if len(vdl) else "—",
            f"{yoy_(vdl):+.1f}% so cùng kỳ" if pd.notna(yoy_(vdl)) else None)

        c1, c2 = st.columns(2)
        with c1:
            d = cut(tm(["ldr_system", "ldr_soe", "ldr_jsc"], ten_viet=False))
            d.columns = ["Toàn hệ thống", "NHTM Nhà nước", "NHTM cổ phần"][:d.shape[1]]
            line_nguong(d, {"Trần LDR (TT22)": s_("ldr_cap")},
                        "LDR — dư nợ cho vay / tổng tiền gửi", "%", height=300)
        with c2:
            d = cut(tm(["sfl_system", "sfl_soe", "sfl_jsc"], ten_viet=False))
            d.columns = ["Toàn hệ thống", "NHTM Nhà nước", "NHTM cổ phần"][:d.shape[1]]
            line_nguong(d, {"Trần theo lộ trình": s_("sfl_cap")},
                        "Tỷ lệ vốn ngắn hạn cho vay trung dài hạn", "%", height=300)

        # du dia den tran - ky moi nhat, theo nhom
        du = {}
        for nhom, sid_l, sid_s in [("Toàn hệ thống", "ldr_system", "sfl_system"),
                                  ("NHTM Nhà nước", "ldr_soe", "sfl_soe"),
                                  ("NHTM cổ phần", "ldr_jsc", "sfl_jsc")]:
            du[nhom] = {"LDR": ldr_tran - cuoi(sid_l)[0], "Vốn NH cho vay TDH": sfl_tran - cuoi(sid_s)[0]}
        du = pd.DataFrame(du).T
        c1, c2 = st.columns(2)
        with c1:
            hbars(du["LDR"].rename_axis("Nhóm"), "Dư địa LDR đến trần, kỳ mới nhất", "điểm %",
                  height=150, color=TH["ink"])
        with c2:
            hbars(du["Vốn NH cho vay TDH"].rename_axis("Nhóm"),
                  "Dư địa tỷ lệ vốn NH cho vay TDH đến trần, kỳ mới nhất", "điểm %",
                  height=150, color=TH["nhan"])

        line_nguong(cut(car_ht.dropna(how="all")),
                    {"Mức tối thiểu (8% → 9% → 8% TT41)": car_toi_thieu},
                    "Tỷ lệ an toàn vốn (CAR) — NHNN: 2013-2019 theo TT36, từ 07/2024 nhóm TT41 · "
                    "IMF FSI: toàn bộ tổ chức nhận tiền gửi, theo quý", "%", height=320)
        st.caption("Đường IMF FSI chạy song song với số NHNN, không nối vào nhau vì khác phạm vi "
                   "(IMF tính toàn bộ tổ chức nhận tiền gửi; NHNN từ 07/2024 chỉ nhóm áp dụng TT41). "
                   "Chênh lệch ở kỳ trùng ≤ 0,2 điểm %. IMF bán niên đến 2023, hằng quý từ Q2/2023, trễ 2-3 quý.")

        # CAR tung ngan hang (CBTT ban nien)
        car_nh = {}
        for col in w_.columns:
            if col.startswith("car_") and col[4:].isalpha() and len(col) == 7:
                s = w_[col].dropna()
                s = s[s.index <= D_TO]
                if len(s):
                    car_nh[f"{col[4:].upper()} ({s.index[-1]:%m/%y})"] = s.iloc[-1]
        c1, c2 = st.columns([1, 1])
        with c1:
            if car_nh:
                hbars(pd.Series(car_nh).rename_axis("Ngân hàng").sort_values(),
                      "CAR từng ngân hàng, kỳ CBTT gần nhất", "%", color=TH["nhan"])
        with c2:
            d = cut(tm(["car_banks_median", "car_banks_min"], ten_viet=False))
            d.columns = ["Trung vị các NH", "Thấp nhất"][:d.shape[1]]
            line_nguong(d, {"Tối thiểu 8%": 8.0}, "CAR hợp nhất các NH có CBTT", "%", height=300)

        st.markdown("#### Quy mô hệ thống")
        c1, c2 = st.columns(2)
        with c1:
            d = pd.DataFrame({"Tổng tài sản": ts, "Vốn điều lệ": vdl}) / 1e6
            d.index.name = "Ngày"
            qm = cut(d)
            if not qm.empty:
                bars(qm, "Tổng tài sản", "Tổng tài sản hệ thống TCTD", "triệu tỷ VND",
                     height=280, color_sign=False)
        with c2:
            def yoy_chuoi(s):
                # dung ngay cung ky (chuoi NHNN co thang bi khuyet -> khong dung pct_change(12))
                s = s[~s.index.duplicated(keep="last")].sort_index()
                truoc = s.reindex(s.index - pd.DateOffset(years=1), method="nearest",
                                  tolerance=pd.Timedelta("20D"))
                return pd.Series((s.values / truoc.values - 1) * 100, index=s.index)

            g = pd.DataFrame({"Tổng tài sản": yoy_chuoi(ts),
                              "Vốn điều lệ": yoy_chuoi(vdl)}).dropna(how="all")
            g.index.name = "Ngày"
            line(cut(g), "Tăng trưởng so cùng kỳ (12 kỳ tháng)", "%", height=280, zero=True)
        c1, c2 = st.columns(2)
        with c1:
            db = (ts / vdl).dropna().rename("Tổng tài sản / vốn điều lệ").to_frame()
            db.index.name = "Ngày"
            line(cut(db), "Đòn bẩy hệ thống", "lần", height=260)
        with c2:
            d = cut(tm(["casa_ratio", "ldr_tt22_listed", "mlt_loan_share"], ten_viet=False))
            d.columns = ["CASA", "LDR theo TT22", "Tỷ trọng cho vay trung dài hạn"][:d.shape[1]]
            line(d, "Nhóm NH niêm yết (quý, BCTC hợp nhất)", "%", height=260)

        # bang 13 ky thang gan nhat, to mau theo tung dong
        bang = pd.DataFrame({
            "LDR toàn hệ thống (%)": s_("ldr_system"),
            "LDR NHTM Nhà nước (%)": s_("ldr_soe"),
            "LDR NHTM cổ phần (%)": s_("ldr_jsc"),
            "Vốn NH cho vay TDH (%)": s_("sfl_system"),
            "CAR toàn hệ thống (%)": car_ht["Toàn hệ thống"],
            "Tổng tài sản (triệu tỷ)": ts / 1e6,
            "Vốn điều lệ (triệu tỷ)": vdl / 1e6,
        })
        bang = bang[bang.index <= D_TO].dropna(how="all")
        bang = bang[bang.index.day >= 28].tail(13)
        if not bang.empty:
            st.markdown("**13 kỳ tháng gần nhất** (màu đậm = cao trong dòng)")
            hien = bang.T
            hien.columns = [f"{x:%m/%Y}" for x in hien.columns]
            try:
                sty = hien.style.format("{:,.2f}", na_rep="—").background_gradient(
                    axis=1, cmap="Oranges")
                st.dataframe(sty, width="stretch")
            except Exception:  # noqa: BLE001  - thieu matplotlib thi hien bang tho
                st.dataframe(hien.round(2), width="stretch")
        dl_button(bang, "AnToanHeThongNH",
                  sheets={"TyLe_Thang": bang.rename_axis("Ngày").reset_index(),
                          "LDR_SFL": cut(tm(["ldr_system", "ldr_soe", "ldr_jsc", "ldr_cap",
                                             "sfl_system", "sfl_soe", "sfl_jsc", "sfl_cap"])),
                          "CAR_HeThong": cut(car_ht), "CAR_TungNH": pd.Series(car_nh, name="CAR %")
                          .rename_axis("Ngân hàng").reset_index(),
                          "QuyMo": cut(pd.DataFrame({"Tổng tài sản (tỷ)": ts,
                                                     "Vốn điều lệ (tỷ)": vdl}))})

    # ---------------------------------------------- 7. THUONG MAI, FDI & BOP
    with T["Đối ngoại"]:
        st.subheader("Thương mại hàng hoá (Cục Thống kê, IMF bù lịch sử)")
        xnk = dl.trade_nso()
        line(cut(xnk) / 1e3, "Xuất nhập khẩu hàng hoá theo tháng (IMF đến 2022, Cục Thống kê từ 2023)",
             "tỷ USD", height=300, zero=True)
        line(cut(dl.trade_nso_yoy()), "Tăng trưởng xuất / nhập khẩu so cùng kỳ", "%", height=260, zero=True)
        xk_it = dl.nm("XK", "LEVEL", section="mặt hàng")       # bo dong tong / khu vuc kinh te
        nk_it = dl.nm("NK", "LEVEL", section="mặt hàng")
        xk_it = xk_it[[c for c in xk_it.columns if "(lượng)" not in c]]
        nk_it = nk_it[[c for c in nk_it.columns if "(lượng)" not in c]]
        c1, c2 = st.columns(2)
        with c1:
            if not xk_it.empty:
                top_x = xk_it.ffill().iloc[-1].dropna().sort_values(ascending=False).head(12)
                hbars(top_x.rename_axis("Mặt hàng"), f"Xuất khẩu theo mặt hàng, tháng {xk_it.index.max():%m/%Y}",
                      "triệu USD", color=TH["ink"], height=330)
        with c2:
            if not nk_it.empty:
                top_n = nk_it.ffill().iloc[-1].dropna().sort_values(ascending=False).head(12)
                hbars(top_n.rename_axis("Mặt hàng"), f"Nhập khẩu theo mặt hàng, tháng {nk_it.index.max():%m/%Y}",
                      "triệu USD", color=TH["nhan"], height=330)
        c1, c2 = st.columns(2)
        with c1:
            chon = filt("multiselect", "Mặt hàng xuất khẩu (trị giá tháng)", list(xk_it.columns),
                        default=list(top_x.index[:4]) if not xk_it.empty else [], key="xk_mh")
            if chon:
                line(cut(xk_it[chon]), "Xuất khẩu theo mặt hàng", "triệu USD", height=300)
        with c2:
            chon = filt("multiselect", "Mặt hàng nhập khẩu (trị giá tháng)", list(nk_it.columns),
                        default=list(top_n.index[:4]) if not nk_it.empty else [], key="nk_mh")
            if chon:
                line(cut(nk_it[chon]), "Nhập khẩu theo mặt hàng", "triệu USD", height=300)

    with T["Tăng trưởng & đầu tư"]:
        st.markdown("**Sản xuất công nghiệp & bán lẻ**")
        c1, c2 = st.columns(2)
        with c1:
            line(cut(dl.iip_nso()), "Chỉ số sản xuất công nghiệp toàn ngành (IMF đến 2022, NSO từ 2023)",
                 "%", height=280, zero=True)
        with c2:
            line(cut(dl.nm("RETAIL", "YOY", pct=True)),
                 "Tổng mức bán lẻ hàng hoá & doanh thu DVTD so cùng kỳ", "%", height=280, zero=True)
        c1, c2 = st.columns(2)
        with c1:
            iip_n = dl.nm("IIP", "YOY", pct=True)
            nganh = [c for c in iip_n.columns if c != "Toàn ngành công nghiệp"]
            mac = [c for c in ("Công nghiệp chế biến, chế tạo", "Khai khoáng", "Sản xuất và phân phối điện",
                               "Sản xuất sản phẩm điện tử, máy vi tính và sản phẩm quang học") if c in nganh]
            chon = filt("multiselect", "Ngành công nghiệp (IIP so cùng kỳ)", nganh, default=mac, key="iip_nganh")
            if chon:
                line(cut(iip_n[chon]), "IIP theo ngành so cùng kỳ", "%", height=300, zero=True)
        with c2:
            bl = dl.nm("RETAIL", "LEVEL") / 1e3
            if not bl.empty:
                bl = bl[[c for c in bl.columns if c != "Tổng số"]]
                bars_stack(cut(bl), "Tổng mức bán lẻ theo nhóm (tháng)", "nghìn tỷ VND", height=300)

        st.markdown("**FDI & cán cân thanh toán**")
        c1, c2 = st.columns(2)
        with c1:
            fdi = dl.fdi_nso()
            cot = [c for c in fdi.columns if "Số dự án" not in c]
            if cot:
                line(cut(fdi[cot]), "FDI đăng ký luỹ kế từ đầu năm (Cục Thống kê, theo tháng báo cáo)",
                     "triệu USD", height=280)
        with c2:
            line(cut(tm(["current_account_bop", "financial_account_bop", "fdi_net_bop",
                         "fii_net_bop", "bop_overall", "bop_errors"])),
                 "Cán cân thanh toán theo quý", "triệu USD", height=280, zero=True)
        line(cut(tm(["fdi_registered", "fdi_realized_vnd"])),
             "FDI đăng ký (triệu USD, luỹ kế) & thực hiện (nghìn tỷ VND) — chuỗi truyền dẫn", "", height=260)
        st.caption("Nguồn: Cục Thống kê — Biểu số liệu báo cáo KT-XH tháng (XK/NK theo mặt hàng, IIP theo ngành, "
                   "bán lẻ, FDI đăng ký). Tháng gần nhất là số ước tính, tháng trước đó là sơ bộ (file tháng sau "
                   "ghi đè). IMF SDMX chỉ bù lịch sử trước 2023. Cán cân thanh toán: NHNN qua chuỗi truyền dẫn.")
        dl_button(cut(xnk), "ThuongMai_FDI",
                  sheets={"XNK": cut(xnk), "XNK_YoY": cut(dl.trade_nso_yoy()),
                          "XK_MatHang": cut(xk_it), "NK_MatHang": cut(nk_it),
                          "IIP": cut(iip_n), "BanLe": cut(dl.nm("RETAIL", "LEVEL")), "FDI": cut(fdi),
                          "BOP": cut(tm(["fdi_registered", "fdi_realized_vnd",
                                         "current_account_bop", "bop_overall"]))})

    # --------------------------------------------------------- 7. MY & KHU VUC
    with T["Thế giới"]:
        st.subheader("Lãi suất Mỹ & đồng USD")
        line(cut(tm(["us_fed_target_upper", "us_effr", "us_sofr", "us_tbill_3m",
                     "us_ust_2y", "us_ust_10y"])), "Lãi suất USD", "%/năm", height=300)
        line(cut(tm(["us_dxy_broad"])), "Chỉ số USD (broad)", "điểm", height=260)
        st.subheader("Vĩ mô 12 nước châu Á (IMF)")
        mr = dl.load("macro_region")
        c1, c2 = st.columns(2)
        g = c1.selectbox("Nhóm", sorted(mr.group.dropna().unique()), key="mrg")
        sub = mr[mr.group == g]
        sn = c2.selectbox("Chỉ tiêu", sorted(sub.series_name.dropna().unique()), key="mrs")
        sub = sub[sub.series_name == sn]
        nuoc = st.multiselect("Nước", sorted(sub.country.dropna().unique()),
                              default=sorted(sub.country.dropna().unique())[:6], key="mrn")
        p = sub[sub.country.isin(nuoc)].pivot_table(index="date", columns="country",
                                                    values="value", aggfunc="last")
        p.index.name = "Ngày"
        line(cut(p), sn, str(sub.unit.dropna().iloc[0]) if sub.unit.notna().any() else "",
             height=320)
        dl_button(cut(p), "ViMoKhuVuc")

    # ------------------------------------------------------- 8. TOAN BO CHUOI
    with T["Dữ liệu gốc"]:
        st.subheader("Toàn bộ chuỗi truyền dẫn")
        mt = dl.tm_meta(dl._mtime(dl.REGISTRY["transmission"][2])).reset_index()
        mt["tre"] = (pd.Timestamp.now().normalize() - mt["last"]).dt.days
        mt["ten"] = [dl.TM_TEN.get(i, t) for i, t in zip(mt.series_id, mt.ten)]
        mt["last"] = mt["last"].dt.strftime("%d/%m/%Y")
        bang_chuoi = mt.rename(columns={"series_id": "Mã chuỗi", "node_name": "Node", "ten": "Tên chuỗi",
                                  "unit": "Đơn vị", "freq": "Tần suất", "last": "Dữ liệu đến",
                                  "n": "Số điểm", "tre": "Trễ (ngày)"})
        st.dataframe(bang_chuoi[["Node", "Tên chuỗi", "Mã chuỗi", "Đơn vị", "Tần suất",
                           "Dữ liệu đến", "Trễ (ngày)", "Số điểm"]],
                     width="stretch", hide_index=True, height=260)
        nd = st.selectbox("Node", sorted(mt.node_name.unique()))
        ids = mt[mt.node_name == nd].set_index("series_id")
        chon = st.multiselect("Chuỗi", list(ids.index), default=list(ids.index)[:4],
                              format_func=lambda i: dl.TM_TEN.get(i, ids.ten.get(i, i)))
        if chon:
            line(cut(tm(chon)), nd,
                 " · ".join(sorted(set(ids.unit.reindex(chon).dropna()))[:2]), height=340)
            dl_button(cut(tm(chon)), "TruyenDan")
        st.caption("Nguồn: SBV (VNIBOR, OMO, tín phiếu, tỷ giá trung tâm), Cục Thống kê (CPI, XNK, IIP, bán lẻ, "
                   "FDI — bước `nso`, `nso-monthly`), IMF SDMX (dự trữ, chỉ số CPI mức, lịch sử trước 2023 — "
                   "bước `macro-vn`), FRED (lãi suất Mỹ), CBTT ngân hàng. Cập nhật bằng bước "
                   "`transmission` của Run-Market.ps1.")

    # ------------------------------------------------------- 9. NIEN GIAM NSO
    with T["Dữ liệu gốc"]:
        st.subheader("Niên giám thống kê — PX-Web Cục Thống kê (333 bảng)")
        cat = dl.nso_catalog()
        c1, c2 = st.columns([1, 2])
        db = filt("selectbox", "Lĩnh vực", list(dict.fromkeys(cat.db)), key="nso_db", col=c1)
        sub = cat[cat.db == db].set_index("table_id")
        tid = filt("selectbox", "Bảng", list(sub.index), key="nso_tb", col=c2,
                   format_func=lambda i: f"{i} · {sub.title[i][:95]}")
        freqs = [f for f in ("M", "Q", "A") if f in sub.freq[tid]]
        fq = freqs[0] if len(freqs) == 1 else st.radio("Tần suất", freqs, horizontal=True, key="nso_fq",
                                                       format_func=lambda f: {"A": "Năm", "M": "Tháng", "Q": "Quý"}[f])
        w = dl.nso_table(tid, fq)
        if w.empty:
            st.caption("Bảng không có chuỗi theo thời gian (xem Kho dữ liệu).")
        else:
            cols = list(w.columns)
            chon = filt("multiselect", "Chuỗi", cols, default=cols[:min(5, len(cols))], key=f"nso_s_{tid}")
            if chon:
                dv = sorted({w.attrs.get("unit", {}).get(c, "") for c in chon} - {""})
                line(cut(w[chon]), sub.title[tid], " · ".join(dv[:2]), height=360)
            hien = w.tail(30).copy()
            hien.index = [f"{x:%Y}" if fq == "A" else f"{x:%m/%Y}" for x in hien.index]
            st.dataframe(hien.T, width="stretch", height=min(420, 60 + 28 * len(cols)))
            dl_button(w, f"NSO_{tid}")
        st.caption(f"Kỳ gần nhất của bảng: {sub['last'][tid]} · cập nhật PX-Web: {sub.updated[tid] or 'không rõ'} · "
                   "giá trị 'Sơ bộ'/'Ước tính' xem cột status trong nso_master.csv. Toàn bộ bảng: "
                   "nso-fetcher\\nso_timeseries.xlsx.")

    # ------------------------------------------------------- 10. GDP & SO QUY
    with T["Tăng trưởng & đầu tư"]:
        st.subheader("GDP theo quý (Cục Thống kê, từ 2000)")
        gdp = dl.gdp_nso("YOY_Q")
        if gdp.empty:
            st.caption("Chưa có số quý — chạy `fetch_monthly_reports.py`.")
        else:
            khu_vuc = [c for c in dl.GDP_NGANH if c in gdp.columns]
            c1, c2 = st.columns([3, 2])
            with c1:
                line(cut(gdp[khu_vuc]), "Tăng trưởng GDP so cùng kỳ theo khu vực kinh tế (quý)", "%",
                     height=320, zero=True)
            with c2:
                cuoi = gdp.ffill().iloc[-1].dropna().drop([c for c in khu_vuc if c in gdp.columns], errors="ignore")
                hbars(cuoi.sort_values().rename_axis("Ngành"),
                      f"Tăng trưởng theo ngành, quý {(gdp.index.max().month - 1) // 3 + 1}/{gdp.index.max().year}",
                      "%", color=TH["ink"], height=320)
            nganh = [c for c in gdp.columns if c not in khu_vuc]
            chon = filt("multiselect", "Ngành cấp 1", nganh, default=[c for c in (
                "Công nghiệp chế biến, chế tạo", "Xây dựng", "Bán buôn và bán lẻ; sửa chữa ô tô, mô tô, xe máy và xe có động cơ khác",
                "Hoạt động kinh doanh bất động sản", "Hoạt động tài chính, ngân hàng và bảo hiểm") if c in nganh], key="gdp_nganh")
            if chon:
                line(cut(gdp[chon]), "Tăng trưởng GDP theo ngành so cùng kỳ", "%", height=300, zero=True)
            c1, c2 = st.columns(2)
            with c1:
                hh = dl.gdp_nso("LEVEL_HH_Q", pct=False)
                if "Tổng số" in hh:
                    d = (hh[[c for c in khu_vuc if c in hh.columns and c != "Tổng số"]] / 1e3)
                    bars_stack(cut(d), "GDP theo giá hiện hành theo khu vực (quý)", "nghìn tỷ VND", height=300)
            with c2:
                ss = dl.gdp_nso("LEVEL_SS_Q", pct=False)
                if "Tổng số" in ss:
                    d = pd.DataFrame({"GDP giá so sánh": ss["Tổng số"] / 1e3})
                    if "Tổng số" in hh:
                        d["GDP giá hiện hành"] = hh["Tổng số"] / 1e3
                    d.index.name = "Ngày"
                    line(cut(d), "Quy mô GDP theo quý", "nghìn tỷ VND", height=300)

    with T["Giá cả"]:
        st.markdown("**Giá sản xuất (PPI, quý)**")
        c1, c2 = st.columns(2)
        with c1:
            ppi = dl.nq("PPI", "YOY_Q", pct=True)
            mac = [c for c in ("Nông, lâm nghiệp và thủy sản", "Công nghiệp", "Công nghiệp chế biến, chế tạo",
                               "Dịch vụ", "Vận tải kho bãi") if c in ppi.columns]
            if mac:
                line(cut(ppi[mac]), "Chỉ số giá sản xuất (PPI) so cùng kỳ theo ngành (quý)", "%", height=300, zero=True)
        with c2:
            ppi_q = dl.nq("PPI", "QOQ", pct=True)
            mac = [c for c in ("Nông, lâm nghiệp và thủy sản", "Công nghiệp", "Dịch vụ") if c in ppi_q.columns]
            if mac:
                line(cut(ppi_q[mac]), "PPI so quý trước", "%", height=300, zero=True)
    with T["Đối ngoại"]:
        st.markdown("**Thương mại dịch vụ (quý)**")
        svc = dl.nq("SVC", "LEVEL_Q", items=["Xuất khẩu dịch vụ", "Nhập khẩu dịch vụ"]) / 1e3
        if not svc.empty:
            svc["Cán cân dịch vụ"] = svc.get("Xuất khẩu dịch vụ") - svc.get("Nhập khẩu dịch vụ")
            line(cut(svc), "Xuất nhập khẩu dịch vụ theo quý", "tỷ USD", height=300, zero=True)
    with T["Tăng trưởng & đầu tư"]:
        st.markdown("**Vốn đầu tư toàn xã hội (quý)**")
        inv = dl.nq("INVEST", "YOY_Q", pct=True)
        mac = [c for c in ("Tổng số", "Khu vực nhà nước", "Khu vực ngoài nhà nước", "Khu vực có vốn đầu tư nước ngoài")
               if c in inv.columns]
        if mac:
            line(cut(inv[mac]), "Vốn đầu tư thực hiện toàn xã hội so cùng kỳ (quý)", "%", height=300, zero=True)
    with T["Lao động"]:
        st.markdown("**Lao động**")
        c1, c2 = st.columns(2)
        with c1:
            un = dl.unemp_nso()
            if not un.empty:
                line(cut(un), "Tỷ lệ thất nghiệp & thiếu việc làm trong độ tuổi lao động (quý)", "%", height=300)
        with c2:
            lb = dl.nq("LABOR", "LEVEL_Q")
            mac = [c for c in ("Lực lượng lao động từ 15 tuổi trở lên", "Lao động có việc làm") if c in lb.columns]
            if mac:
                line(cut(lb[mac] / 1e3), "Lực lượng lao động & lao động có việc làm", "triệu người", height=300)
        st.caption("Nguồn: Biểu số liệu Báo cáo KT-XH quý của Cục Thống kê (GDP theo giá hiện hành / so sánh và tăng "
                   "trưởng theo ngành, PPI, XNK dịch vụ, vốn đầu tư toàn xã hội, lao động — việc làm). Quý gần nhất "
                   "là số ước tính, quý trước đó sơ bộ (báo cáo sau ghi đè). XK/NK hàng hoá, IIP, bán lẻ theo quý "
                   "có trong nso_monthly_master.csv (metric *_Q).")
    with T["Tăng trưởng & đầu tư"]:
        dl_button(cut(gdp) if not gdp.empty else pd.DataFrame(), "GDP_Quy",
                  sheets={"GDP_YoY": cut(gdp), "GDP_HienHanh": cut(dl.gdp_nso("LEVEL_HH_Q", pct=False)),
                          "GDP_SoSanh": cut(dl.gdp_nso("LEVEL_SS_Q", pct=False)),
                          "PPI_YoY": cut(dl.nq("PPI", "YOY_Q", pct=True)), "XNK_DichVu": cut(dl.nq("SVC", "LEVEL_Q")),
                          "VonDauTu_YoY": cut(dl.nq("INVEST", "YOY_Q", pct=True)), "ThatNghiep": cut(dl.unemp_nso()),
                          "LaoDong": cut(dl.nq("LABOR", "LEVEL_Q"))})

# ========================================================= TRAI PHIEU & NDT
elif PAGE == "🧾 Trái phiếu & nhà đầu tư":
    st.title("Trái phiếu doanh nghiệp & nhà đầu tư")
    t = tabs_bb(["Tài khoản NĐT (VSDC)", "Trái phiếu doanh nghiệp", "Giá & đường cong lợi suất"], "tp")

    with t[0]:
        v = dl.load("vsdc").set_index("date")
        cols = [c for c in ["ca_nhan", "to_chuc", "ca_nhan_nn", "to_chuc_nn", "tong"] if c in v]
        ten = {"ca_nhan": "Cá nhân trong nước", "to_chuc": "Tổ chức trong nước",
               "ca_nhan_nn": "Cá nhân nước ngoài", "to_chuc_nn": "Tổ chức nước ngoài", "tong": "Tổng"}
        d = v[cols].rename(columns=ten)
        line(cut(d, MONTHS), "Số tài khoản giao dịch", "tài khoản")
        moi = d.diff()
        bars(cut(moi, MONTHS), "Tổng", "Số tài khoản mở mới theo tháng", "tài khoản")
        st.dataframe(d.tail(18).iloc[::-1], width="stretch")
        dl_button(d, "TaiKhoanNDT", sheets={"SoDu": d, "MoMoi": moi})

    with t[1]:
        b0 = dl.bonds_df()
        st.caption("Toàn thị trường TPDN từ HNX CBIS (**phát hành riêng lẻ trong nước** + trái phiếu "
                   "USD). Mặc định hiển thị **tất cả**; bộ lọc ngành / CTCK bảo lãnh là tuỳ chọn.")
        nam_min, nam_max = int(b0.nam_ph.min()), int(b0.nam_ph.max())
        f1, f2, f3, f4 = st.columns([2, 1, 1.3, 1])
        nam = f1.slider("Năm phát hành", nam_min, nam_max, (max(nam_min, 2017), nam_max))
        tt = f2.multiselect("Tình trạng", sorted(b0.tinh_trang.dropna().unique()), default=[])
        ng = f3.multiselect("Ngành", dl.NGANH_TP, default=[])
        loai = f4.multiselect("Loại", ["Riêng lẻ trong nước", "Quốc tế (USD)"],
                              default=["Riêng lẻ trong nước", "Quốc tế (USD)"])

        b = b0[(b0.nam_ph >= nam[0]) & (b0.nam_ph <= nam[1]) & b0.loai.isin(loai or list(b0.loai.unique()))]
        if tt:
            b = b[b.tinh_trang.isin(tt)]
        if ng:
            b = b[b.nganh.isin(ng)]
        with st.expander("🏦 Lọc theo CTCK bảo lãnh / hệ sinh thái (tuỳ chọn)"):
            g1, g2, g3 = st.columns([2, 1, 2])
            top_ctck = b.groupby("ctck_bao_lanh").gia_tri_ty.sum().sort_values(ascending=False)
            ctck = g1.multiselect("CTCK bảo lãnh / thu xếp", list(top_ctck.index), default=[],
                                  help="Để trống = toàn thị trường")
            tc = g2.multiselect("Độ tin cậy", ["cao", "kha", "thap", "proxy"], default=[],
                                help="cao/kha lấy từ PDF công bố; proxy suy từ tổ chức lưu ký")
            hst = g3.multiselect("Hệ sinh thái / tổ chức phát hành",
                                 list(b.groupby("parent_group").gia_tri_ty.sum()
                                      .sort_values(ascending=False).index), default=[])
            if ctck:
                b = b[b.ctck_bao_lanh.isin(ctck)]
            if tc:
                b = b[b.do_tin_cay.isin(tc)]
            if hst:
                b = b[b.parent_group.isin(hst)]
        if b.empty:
            st.warning("Không có lô trái phiếu nào khớp bộ lọc.")
            if not xuat.dang_xuat_all():
                st.stop()
            b = b0                     # dang xuat toan app: bo bo loc de van co du lieu

        ls_all = dl.lai_suat_bq(b.assign(k=1), "k")
        c = st.columns(6)
        c[0].metric("Số lô TP", f"{len(b):,}".replace(",", "."))
        c[1].metric("Giá trị phát hành", f"{b.gia_tri_ty.sum() / 1e3:,.0f} ngh.tỷ")
        c[2].metric("Đang lưu hành", f"{b.gia_tri_luu_hanh_ty.sum() / 1e3:,.0f} ngh.tỷ")
        c[3].metric("Đã mua lại", f"{b.gt_mua_lai_luy_ke_ty.sum() / 1e3:,.0f} ngh.tỷ")
        c[4].metric("Lãi suất BQ (gia quyền)", f"{ls_all.iloc[0]:,.2f}%" if len(ls_all) else "—")
        c[5].metric("Tổ chức phát hành", f"{b.to_chuc_phat_hanh.nunique():,}".replace(",", "."))

        MAU_NG = alt.Scale(domain=dl.NGANH_TP, range=_mau(len(dl.NGANH_TP)))
        s = tabs_bb(["Quy mô & đối chiếu VBMA", "Cơ cấu theo ngành", "Lãi suất phát hành",
                     "Đáo hạn & tổ chức", "Chi tiết"], "tp_dn")

        # ------------------------------------------ QUY MO & DOI CHIEU VBMA
        with s[0]:
            st.markdown("**Giá trị phát hành theo năm: dữ liệu app so với VBMA**")
            full = b0[b0.nam_ph.between(2019, nam_max)]
            app_nam = full.pivot_table(index="nam_ph", columns="loai", values="gia_tri_ty",
                                       aggfunc="sum").reindex(columns=["Riêng lẻ trong nước",
                                                                        "Quốc tế (USD)"])
            app_usd = full[full.loai == "Quốc tế (USD)"].groupby("nam_ph").gia_tri_usd_tr.sum()
            vb = dl.VBMA_NAM.set_index("Năm")
            dd = pd.DataFrame({
                "Riêng lẻ trong nước (app)": app_nam["Riêng lẻ trong nước"],
                "Ra công chúng (VBMA)": vb["VBMA công chúng"],
                "Trái phiếu USD (app, quy đổi)": app_nam["Quốc tế (USD)"],
            }).fillna(0)
            dd.index.name = "Năm"
            dl_ = dd.reset_index().melt(id_vars="Năm", var_name="Nguồn", value_name="Tỷ đồng")
            dl_["Năm"] = dl_["Năm"].astype(int).astype(str)
            thu_tu = list(dd.columns)
            cot = (alt.Chart(dl_).mark_bar()
                   .encode(x=alt.X("Năm:O", title=None, axis=alt.Axis(labelAngle=0)),
                           y=alt.Y("Tỷ đồng:Q", stack="zero",
                                   axis=_yaxis("tỷ đồng", ",.0f")),
                           color=alt.Color("Nguồn:N", title=None, sort=thu_tu,
                                           scale=alt.Scale(domain=thu_tu,
                                                           range=[TH["nhan"], TH["bar"], "#F4B183"]),
                                           legend=alt.Legend(orient="bottom")),
                           order=alt.Order("thu_tu:Q"),
                           tooltip=["Năm", "Nguồn", alt.Tooltip("Tỷ đồng:Q", format=",.0f")])
                   .transform_calculate(thu_tu="indexof(" + str(thu_tu) + ", datum['Nguồn'])"))
            vt = vb[["VBMA tổng trong nước"]].dropna().reset_index()
            vt["Năm"] = vt["Năm"].astype(int).astype(str)
            vt = vt[vt["Năm"].isin(dl_["Năm"].unique())]
            diem = (alt.Chart(vt).mark_point(shape="diamond", size=110, filled=True, color=TH["ink"])
                    .encode(x="Năm:O", y="VBMA tổng trong nước:Q",
                            tooltip=["Năm", alt.Tooltip("VBMA tổng trong nước:Q", format=",.0f",
                                                        title="VBMA tổng (riêng lẻ + công chúng)")]))
            show(alt.layer(cot, diem).properties(height=340, usermeta=EMBED), "tpdn-quy-mo-vbma")
            st.caption("◆ đen = tổng phát hành trong nước theo VBMA (riêng lẻ + ra công chúng). "
                       "Năm 2026 của VBMA chỉ có 6 tháng.")

            bang = pd.DataFrame({
                "App riêng lẻ (tỷ)": app_nam["Riêng lẻ trong nước"],
                "VBMA riêng lẻ (tỷ)": vb["VBMA riêng lẻ"],
            })
            bang["Chênh app – VBMA (%)"] = (bang["App riêng lẻ (tỷ)"] / bang["VBMA riêng lẻ (tỷ)"] - 1) * 100
            bang["VBMA công chúng (tỷ)"] = vb["VBMA công chúng"]
            bang["VBMA tổng trong nước (tỷ)"] = vb["VBMA tổng trong nước"]
            bang["App thiếu so với VBMA tổng (%)"] = (1 - bang["App riêng lẻ (tỷ)"]
                                                      / bang["VBMA tổng trong nước (tỷ)"]) * 100
            bang["App TP USD (tr.USD)"] = app_usd
            bang["VBMA quốc tế (tr.USD)"] = vb["VBMA quốc tế (tr.USD)"]
            bang["Nguồn VBMA"] = vb["Nguồn VBMA"]
            bang = bang.loc[bang.index.isin(range(2021, nam_max + 1))]
            bang.index.name = "Năm"
            st.dataframe(bang.round(1), width="stretch")
            st.info("**Vì sao số app nhỏ hơn con số hay được nhắc:** dữ liệu HNX CBIS chỉ có "
                    "**phát hành riêng lẻ** — khớp VBMA gần như tuyệt đối (2024: 435.704 tỷ, 2025: "
                    "574.556 tỷ). Con số VBMA hay được trích (2024: 468.618 tỷ, 2025: 629.910 tỷ) là "
                    "**cộng thêm phát hành ra công chúng**, phần app không có từng lô — chiếm "
                    "khoảng 7–13% mỗi năm.")
            dl_button(bang, "TPDN_DoiChieu_VBMA", sheets={"Doi_chieu": bang, "Stack_nam": dd})

        # ----------------------------------------------------- CO CAU NGANH
        with s[1]:
            cn = b.pivot_table(index="nam_ph", columns="nganh", values="gia_tri_ty",
                               aggfunc="sum").reindex(columns=dl.NGANH_TP).fillna(0)
            cn.index.name = "Năm"
            dn = cn.reset_index().melt(id_vars="Năm", var_name="Ngành", value_name="Tỷ đồng")
            dn["Năm"] = dn["Năm"].astype(int).astype(str)
            kieu_cc = st.radio("Hiển thị", ["Giá trị (tỷ đồng)", "Tỷ trọng (%)"], horizontal=True)
            chuan = kieu_cc.startswith("Tỷ trọng")
            ch = (alt.Chart(dn).mark_bar()
                  .encode(x=alt.X("Năm:O", title=None, axis=alt.Axis(labelAngle=0)),
                          y=alt.Y("Tỷ đồng:Q", stack="normalize" if chuan else "zero",
                                  axis=_yaxis("% giá trị phát hành" if chuan else "tỷ đồng",
                                              ".0%" if chuan else ",.0f")),
                          color=alt.Color("Ngành:N", title=None, scale=MAU_NG,
                                          legend=alt.Legend(orient="bottom", columns=5)),
                          order=alt.Order("thu_tu:Q"),
                          tooltip=["Năm", "Ngành", alt.Tooltip("Tỷ đồng:Q", format=",.0f")])
                  .transform_calculate(thu_tu="indexof(" + str(dl.NGANH_TP) + ", datum['Ngành'])")
                  .properties(height=360, usermeta=EMBED))
            _title("Cơ cấu phát hành theo ngành")
            show(ch, "tpdn-co-cau-nganh")

            ty_trong = (cn.div(cn.sum(axis=1), axis=0) * 100).round(1)
            ty_trong.index = ty_trong.index.astype(int)
            k1, k2 = st.columns([3, 2])
            with k1:
                st.markdown("**Tỷ trọng theo năm (%)**")
                st.dataframe(ty_trong.iloc[::-1], width="stretch")
            with k2:
                st.markdown("**Đối chiếu VBMA (riêng lẻ)**")
                rows = []
                for y, v in dl.VBMA_NGANH.items():
                    if y in ty_trong.index:
                        for k, pct in v.items():
                            rows.append({"Năm": y, "Ngành": k, "App (%)": ty_trong.loc[y, k],
                                         "VBMA (%)": pct})
                if rows:
                    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                st.caption("Ngành do pipeline gán (bond-pivot `classify_issuers.py`): khớp tên với "
                           "1.526 công ty niêm yết (ICB) → ngân hàng → hệ sinh thái → từ khoá. Chỉ "
                           "khớp VBMA khi không bật bộ lọc khác.")
            ng_src = (b.groupby("nguon_nganh").agg(so_lo=("ma_tp", "size"), gia_tri=("gia_tri_ty", "sum")))
            ng_src["% giá trị"] = ng_src.gia_tri / max(b.gia_tri_ty.sum(), 1) * 100
            ng_src = ng_src.rename(index={"niem_yet": "Khớp công ty niêm yết", "tu_khoa": "Từ khoá tên",
                                          "he_sinh_thai": "Hệ sinh thái (SPV)", "override": "Sửa tay",
                                          "dac_biet": "CTCK / công ty tài chính",
                                          "ngan_hang": "Ngân hàng chưa niêm yết", "chua": "Chưa phân loại"})
            chua = (b[b.nganh == "Chưa phân loại"].groupby("to_chuc_phat_hanh")
                    .agg(so_lo=("ma_tp", "size"), gia_tri_ty=("gia_tri_ty", "sum"))
                    .sort_values("gia_tri_ty", ascending=False))
            with st.expander(f"Nguồn gán ngành · {len(chua)} tổ chức chưa phân loại "
                             f"({chua.gia_tri_ty.sum() / max(b.gia_tri_ty.sum(), 1) * 100:.1f}% giá trị)"):
                e1, e2 = st.columns([2, 3])
                e1.dataframe(ng_src.sort_values("gia_tri", ascending=False).round(1),
                             width="stretch")
                e2.dataframe(chua.head(40).round(0), width="stretch")
                st.caption(r"Bổ sung ngành: thêm dòng `từ khoá,ngành,mã CK,ghi chú` vào "
                           r"`D:\market-data\bond-pivot\config\nganh_overrides.csv` rồi chạy "
                           r"`python scripts\build_timeline.py` trong bond-pivot.")
            dl_button(cn, "TPDN_CoCauNganh", sheets={"Gia_tri": cn, "Ty_trong": ty_trong})

        # -------------------------------------------------- LAI SUAT PHAT HANH
        with s[2]:
            tan = st.radio("Tần suất", ["Quý", "Năm"], horizontal=True, key="ls_tan")
            cot_t = "quy_ph" if tan == "Quý" else "nam_ph"
            nganh_ls = st.multiselect("So sánh ngành", dl.NGANH_TP,
                                      default=["Ngân hàng", "Bất động sản"], key="ls_ng")
            tong = dl.lai_suat_bq(b, cot_t).rename("Toàn thị trường (lọc hiện tại)")
            parts = [tong]
            for g in nganh_ls:
                parts.append(dl.lai_suat_bq(b[b.nganh == g], cot_t).rename(g))
            ls = pd.concat(parts, axis=1)
            ls.index = ls.index.astype(str)
            ls.index.name = "Kỳ"
            dls = ls.reset_index().melt(id_vars="Kỳ", var_name="Series", value_name="%/năm").dropna()
            dom = ["Toàn thị trường (lọc hiện tại)"] + list(nganh_ls)
            mau_ls = ["#7F7F7F"] + [_mau()[dl.NGANH_TP.index(g)] for g in nganh_ls]
            duong = (alt.Chart(dls).mark_line(strokeWidth=2.2, point=alt.OverlayMarkDef(size=28))
                     .encode(x=alt.X("Kỳ:O", title=None, axis=alt.Axis(labelAngle=-45 if tan == "Quý" else 0,
                                                                        labelOverlap="greedy")),
                             y=alt.Y("%/năm:Q", axis=_yaxis("%/năm", ",.1f"),
                                     scale=alt.Scale(zero=False)),
                             color=alt.Color("Series:N", title=None,
                                             scale=alt.Scale(domain=dom, range=mau_ls),
                                             legend=alt.Legend(orient="bottom")),
                             tooltip=["Kỳ", "Series", alt.Tooltip("%/năm:Q", format=",.2f")]))
            lop = [duong]
            if tan == "Năm":
                vbl = dl.VBMA_NAM[["Năm", "VBMA LS BQ (%)"]].dropna()
                vbl["Kỳ"] = vbl["Năm"].astype(int).astype(str)
                vbl = vbl[vbl["Kỳ"].isin(ls.index)]
                lop.append(alt.Chart(vbl).mark_point(shape="diamond", size=120, filled=True,
                                                     color=TH["neg"])
                           .encode(x="Kỳ:O", y="VBMA LS BQ (%):Q",
                                   tooltip=["Kỳ", alt.Tooltip("VBMA LS BQ (%):Q", format=",.2f",
                                                              title="VBMA LS BQ toàn TT")]))
            _title("Lãi suất phát hành bình quân gia quyền theo giá trị")
            show(alt.layer(*lop).properties(height=340, usermeta=EMBED), "tpdn-lai-suat-bq")
            if tan == "Năm":
                st.caption("◆ đỏ = lãi suất bình quân toàn thị trường theo VBMA (gồm cả công chúng). "
                           "Riêng lẻ theo VBMA: 2024 7,2% · 2025 7,4% — app 7,24% · 7,40%.")

            sc = b[b.lai_suat.notna() & (b.lai_suat > 0) & (b.gia_tri_ty > 0)].copy()
            if len(sc) > 4000:
                sc = sc.nlargest(4000, "gia_tri_ty")
            diem_ls = (alt.Chart(sc).mark_circle(opacity=.55)
                       .encode(x=alt.X("ngay_phat_hanh:T", title=None,
                                       axis=alt.Axis(format="%Y", tickCount=10, grid=False)),
                               y=alt.Y("lai_suat:Q", axis=_yaxis("%/năm", ",.0f"),
                                       scale=alt.Scale(domain=[0, 18], clamp=True)),
                               size=alt.Size("gia_tri_ty:Q", title="Giá trị (tỷ)",
                                             scale=alt.Scale(range=[8, 500]), legend=None),
                               color=alt.Color("nganh:N", title=None, scale=MAU_NG,
                                               legend=alt.Legend(orient="bottom", columns=5)),
                               tooltip=["ma_tp", "to_chuc_phat_hanh", "nganh",
                                        alt.Tooltip("ngay_phat_hanh:T", format="%d/%m/%Y"),
                                        alt.Tooltip("lai_suat:Q", format=",.2f"),
                                        alt.Tooltip("gia_tri_ty:Q", format=",.0f", title="Giá trị (tỷ)"),
                                        "ky_han"])
                       .properties(height=380, usermeta=EMBED))
            _title("Từng lô phát hành: lãi suất theo thời gian (bong bóng = giá trị)")
            show(diem_ls, "tpdn-lai-suat-tung-lo")

            bang_ls = b[b.lai_suat.notna() & (b.lai_suat > 0) & (b.gia_tri_ty > 0)]
            piv = bang_ls.groupby(["nam_ph", "nganh"]).apply(
                lambda x: np.average(x.lai_suat, weights=x.gia_tri_ty)).unstack().reindex(columns=dl.NGANH_TP)
            piv["Toàn thị trường"] = dl.lai_suat_bq(bang_ls, "nam_ph")
            piv.index = piv.index.astype(int)
            piv.index.name = "Năm"
            st.markdown("**Lãi suất BQ gia quyền theo năm × ngành (%/năm)**")
            st.dataframe(piv.round(2).iloc[::-1], width="stretch")
            st.caption("Lãi suất là mức coupon khi phát hành; ~24–47% số đợt là lãi suất thả nổi "
                       "(theo VBMA) nên đây là lãi suất kỳ đầu.")
            dl_button(piv, "TPDN_LaiSuat", sheets={"Nam_x_nganh": piv, "Theo_ky": ls})

        # ---------------------------------------------- DAO HAN & TO CHUC
        with s[3]:
            n1, n2 = st.columns(2)
            with n1:
                dh = (b[b.gia_tri_luu_hanh_ty > 0].groupby("nam_dh").gia_tri_luu_hanh_ty.sum()
                      .to_frame("Giá trị đáo hạn"))
                dh.index.name = "Năm"
                dh = dh[(dh.index >= LAST.year) & (dh.index <= LAST.year + 10)]
                dh.index = dh.index.astype(int).astype(str)
                bars(dh, "Giá trị đáo hạn", "Áp lực đáo hạn phần đang lưu hành", "tỷ đồng",
                     height=300, color_sign=False)
            with n2:
                dhn = (b[(b.gia_tri_luu_hanh_ty > 0) & (b.nam_dh >= LAST.year) & (b.nam_dh <= LAST.year + 5)]
                       .pivot_table(index="nam_dh", columns="nganh", values="gia_tri_luu_hanh_ty",
                                    aggfunc="sum").reindex(columns=dl.NGANH_TP).fillna(0))
                dhn.index.name = "Năm"
                dm = dhn.reset_index().melt(id_vars="Năm", var_name="Ngành", value_name="Tỷ đồng")
                dm["Năm"] = dm["Năm"].astype(int).astype(str)
                _title("Đáo hạn 5 năm tới theo ngành")
                show(alt.Chart(dm).mark_bar()
                     .encode(x=alt.X("Năm:O", title=None, axis=alt.Axis(labelAngle=0)),
                             y=alt.Y("Tỷ đồng:Q", axis=_yaxis("tỷ đồng", ",.0f")),
                             color=alt.Color("Ngành:N", title=None, scale=MAU_NG,
                                             legend=alt.Legend(orient="bottom", columns=3)),
                             tooltip=["Năm", "Ngành", alt.Tooltip("Tỷ đồng:Q", format=",.0f")])
                     .properties(height=300, usermeta=EMBED), "tpdn-dao-han-nganh")
            n3, n4 = st.columns(2)
            with n3:
                top = b.groupby("parent_group").gia_tri_ty.sum().sort_values(ascending=False).head(15)
                hbars(top, "Top hệ sinh thái theo giá trị phát hành", "tỷ đồng")
            with n4:
                tc_ok = b[b.do_tin_cay.isin(["cao", "kha"])]
                src = tc_ok if len(tc_ok) else b
                topc = src.groupby("ctck_bao_lanh").gia_tri_ty.sum().sort_values(ascending=False).head(15)
                hbars(topc, "Top CTCK bảo lãnh / thu xếp" + (" (độ tin cậy cao/khá)" if len(tc_ok) else ""),
                      "tỷ đồng", color=TH["ink"])

        # ------------------------------------------------------------ CHI TIET
        with s[4]:
            cot = ["ma_tp", "to_chuc_phat_hanh", "ma_ck", "parent_group", "nganh", "nganh_chi_tiet",
                   "nguon_nganh", "loai", "ngay_phat_hanh",
                   "ngay_dao_han", "gia_tri_ty", "gia_tri_usd_tr", "gia_tri_luu_hanh_ty", "lai_suat",
                   "ky_han", "tinh_trang", "ctck_bao_lanh", "do_tin_cay", "dam_bao"]
            chi_tiet = b[[c for c in cot if c in b]].sort_values("ngay_phat_hanh", ascending=False)
            st.dataframe(chi_tiet.head(500), width="stretch", hide_index=True)
            dl_button(chi_tiet.set_index("ma_tp"), "TraiPhieu_ToanTT")

    # ------------------------------------------ GIA GD + DUONG CONG LOI SUAT
    with t[2]:
        st.caption("Giá giao dịch **sàn TPDN riêng lẻ HNX** (từ 19/07/2023, giá gộp đã gồm lãi dồn tích) "
                   "→ YTM từng giao dịch → đường cong theo ngành tại **as-of và 1/3/6/12 tháng trước**. "
                   "YTM bucket = **bình quân gia quyền theo giá trị lô đang lưu hành**, đã cắt điểm "
                   "phân tán (1,5·IQR). Bond thả nổi dùng lãi suất phát hành làm coupon (độ tin cậy *kha*).")
        yall = dl.bond_yields_prepared("thap")
        if yall.empty:
            st.warning("Chưa có bond_yields.csv — chạy pipeline bonds (pull_prices → bond_yields).")
            st.stop()
        d_last = yall.d.max().date()
        k1, k2, k3, k4 = st.columns([1.2, 1, 1.2, 0.8])
        as_of = k1.date_input("As-of", value=d_last, min_value=yall.d.min().date(), max_value=d_last,
                              format="DD/MM/YYYY", key="yc_asof")
        window = k2.selectbox("Cửa sổ (ngày GD trước mốc)", [20, 30, 45, 60, 90], index=1, key="yc_win")
        tin_cay = k3.selectbox("Độ tin cậy YTM tối thiểu", ["kha", "cao", "thap"], index=0, key="yc_tc",
                               format_func=lambda v: {"cao": "cao — chỉ lãi cố định",
                                                      "kha": "cao + kha (mặc định)",
                                                      "thap": "tất cả (kể cả trả lãi cuối kỳ)"}[v])
        min_bond = k4.number_input("Tối thiểu bond/bucket", 2, 10, 3, key="yc_minb")
        long, fit, charts, wide = dl.duong_cong(as_of, int(window), tin_cay, int(min_bond))
        if long.empty:
            st.warning("Không đủ giao dịch trong cửa sổ đã chọn.")
            st.stop()
        yc = dl._yc()
        MOC_NHAN = {m: ("Hiện tại" if m == "0M" else m + " trước") + " (%s)" % pd.Timestamp(d).strftime("%d/%m/%y")
                    for m, d in long.drop_duplicates("moc").set_index("moc").ngay_moc.items()}
        MOC_ORDER = [MOC_NHAN[m] for m, _ in yc.MOC if m in MOC_NHAN]
        MOC_MAU = [yc.RAMP[m] for m, _ in yc.MOC if m in MOC_NHAN]
        long["Mốc"] = long.moc.map(MOC_NHAN)

        u = tabs_bb(["Đường cong theo ngành", "Bảng dịch chuyển", "Giá & YTM từng mã", "TPCP benchmark"], "tp_yc")

        def _slug(ng):
            return "".join(ch for ch in ng if ch.isalnum()).lower()

        def _curve_chart(nganh):
            sub = long[long.nganh == nganh].sort_values("ky_han_tb")
            if sub.empty:
                return None
            xsc = alt.Scale(type="log", domain=[0.1, 20])
            xax = alt.Axis(values=[0.25, 0.5, 1, 2, 3, 5, 7, 10, 15], format="~g", labelAngle=0, grid=False,
                           title="Kỳ hạn còn lại (năm)")
            csc = alt.Scale(domain=MOC_ORDER, range=MOC_MAU)
            ysc = alt.Scale(domain=[max(0.0, float(sub.ytm.min()) - 3), float(sub.ytm.max()) + 3])  # cat cham phan tan
            lop, dots = [], []
            for m, _ in yc.MOC:
                if m in charts.get(nganh, {}):
                    g, tpc, d_moc = charts[nganh][m]
                    dots.append(g[["ma_gd", "to_chuc_phat_hanh", "ttm_nam", "ytm", "w_lo", "gia_bq_pct"]]
                                .assign(**{"Mốc": MOC_NHAN[m]}))
            if dots:
                dd = pd.concat(dots)
                lop.append(alt.Chart(dd).mark_circle(opacity=0.28, clip=True).encode(
                    x=alt.X("ttm_nam:Q", scale=xsc, axis=xax),
                    y=alt.Y("ytm:Q", title="YTM (%/năm)", scale=ysc),
                    color=alt.Color("Mốc:N", scale=csc, sort=MOC_ORDER,
                                    legend=alt.Legend(orient="bottom", columns=3)),
                    size=alt.Size("w_lo:Q", scale=alt.Scale(range=[15, 400]), legend=None),
                    tooltip=["ma_gd", "to_chuc_phat_hanh", "Mốc",
                             alt.Tooltip("ttm_nam:Q", format=".2f", title="Kỳ hạn còn lại"),
                             alt.Tooltip("ytm:Q", format=".2f", title="YTM %"),
                             alt.Tooltip("gia_bq_pct:Q", format=".1f", title="Giá % mệnh giá"),
                             alt.Tooltip("w_lo:Q", format=",.0f", title="Giá trị lô (tỷ)")]))
            lop.append(alt.Chart(sub).mark_line(point=True, strokeWidth=2.2, clip=True).encode(
                x=alt.X("ky_han_tb:Q", scale=xsc, axis=xax),
                y=alt.Y("ytm:Q", title="YTM (%/năm)", scale=ysc),
                color=alt.Color("Mốc:N", scale=csc, sort=MOC_ORDER),
                order="ky_han_tb:Q",
                tooltip=["Mốc", "ky_han", alt.Tooltip("ytm:Q", format=".2f", title="YTM BQ gia quyền %"),
                         alt.Tooltip("ytm_median:Q", format=".2f", title="Median %"),
                         alt.Tooltip("ytm_min:Q", format=".2f"), alt.Tooltip("ytm_max:Q", format=".2f"),
                         "n_bond", alt.Tooltip("gia_tri_lo_ty:Q", format=",.0f", title="Giá trị lô (tỷ)"),
                         alt.Tooltip("spread_bps:Q", format=",.0f", title="Spread vs TPCP (bps)")]))
            m0 = charts.get(nganh, {}).get("0M")
            if m0 and m0[1]:
                tpc = pd.DataFrame({"ky_han_nam": m0[1][0], "spot": m0[1][1]})
                tpc = tpc[(tpc.ky_han_nam >= 0.1) & (tpc.ky_han_nam <= 20)]
                lop.append(alt.Chart(tpc).mark_line(strokeDash=[5, 4], color=TH["ink2"], strokeWidth=1.5, clip=True).encode(
                    x=alt.X("ky_han_nam:Q", scale=xsc), y=alt.Y("spot:Q", scale=ysc),
                    tooltip=[alt.Tooltip("ky_han_nam:Q", title="Kỳ hạn"),
                             alt.Tooltip("spot:Q", format=".2f", title="TPCP spot %")]))
            return alt.layer(*lop).properties(height=360, usermeta=EMBED)

        with u[0]:
            nganh_co = [n for n in [yc.TOAN_TT, yc.TRU_NH] + dl.NGANH_TP if n in set(long.nganh)]
            chon = filt("multiselect", "Ngành", nganh_co, default=nganh_co[:4], key="yc_nganh")
            st.caption("Chấm = từng bond trong cửa sổ (kích thước ~ giá trị lô); đường = YTM bình quân gia quyền "
                       "theo bucket kỳ hạn; nét đứt = spot TPCP tại as-of. Nhạt → đậm = 12M trước → hiện tại.")
            for i in range(0, len(chon), 2):
                cols = st.columns(2)
                for j, ng in enumerate(chon[i:i + 2]):
                    with cols[j]:
                        _title(ng)
                        ch = _curve_chart(ng)
                        if ch is not None:
                            show(ch, "tpdn-duong-cong-" + _slug(ng))
            if xuat.dang_xuat_all():
                for ng in nganh_co:
                    if ng not in chon:
                        ch = _curve_chart(ng)
                        if ch is not None:
                            xuat.ghi_altair(ch, "tpdn-duong-cong-" + _slug(ng))

        with u[1]:
            st.markdown("**YTM bình quân gia quyền (%) theo ngành × bucket kỳ hạn — và thay đổi (bps) so với các mốc**")
            st.dataframe(wide.set_index(["nganh", "ky_han"]), width="stretch")
            if len(fit):
                st.markdown("**Tại kỳ hạn chuẩn (nội suy giữa các bucket, không ngoại suy)**")
                fw = fit.pivot_table(index=["nganh", "ky_han_nam"], columns="moc", values="ytm_fit")
                fw = fw.reindex(columns=[m for m, _ in yc.MOC if m in fw.columns])
                st.dataframe(fw.round(2), width="stretch")
            dl_button(wide.set_index(["nganh", "ky_han"]), "TPDN_DuongCong",
                      sheets={"Wide": wide.set_index(["nganh", "ky_han"]), "Long": long.set_index("ngay_moc"),
                              "KyHanChuan": fit.set_index("ngay_moc") if len(fit) else pd.DataFrame()})

        with u[2]:
            gan = yall[yall.d >= pd.Timestamp(as_of) - pd.Timedelta(days=90)]
            top = gan.groupby("ma_gd").gt_ty.sum().sort_values(ascending=False)
            ten_ma = yall.drop_duplicates("ma_gd").set_index("ma_gd").to_chuc_phat_hanh
            ma = st.selectbox("Mã trái phiếu (sắp theo GTGD 90 ngày)", list(top.index),
                              format_func=lambda m: "%s — %s" % (m, str(ten_ma.get(m, ""))[:60]), key="yc_ma")
            h = yall[yall.ma_gd == ma].sort_values("d").set_index("d")
            info = h.iloc[-1]
            c = st.columns(6)
            c[0].metric("Ngành", str(info.nganh))
            c[1].metric("Lãi suất PH", "%.2f%%" % info.lai_suat)
            c[2].metric("Đáo hạn", pd.Timestamp(info.ngay_dao_han).strftime("%d/%m/%Y") if pd.notna(info.ngay_dao_han) else "—")
            c[3].metric("Giá BQ gần nhất", "%.1f%% MG" % info.gia_bq_pct)
            c[4].metric("YTM gần nhất", "%.2f%%" % info.ytm)
            c[5].metric("Độ tin cậy", str(info.do_tin_cay_ytm) + (" · " + str(info.loai_lai_suat) if pd.notna(info.loai_lai_suat) else ""))
            ser = h[["gia_bq_pct", "ytm", "spread_bps"]].rename(
                columns={"gia_bq_pct": "Giá BQ (% mệnh giá)", "ytm": "YTM (%)", "spread_bps": "Spread (bps)"})
            ser.index.name = "date"
            line(ser[["Giá BQ (% mệnh giá)"]], "%s — giá bình quân ngày (giá gộp)" % ma, "% mệnh giá", height=260, ten="tpdn-gia-ma")
            line(ser[["YTM (%)"]], "%s — YTM theo ngày" % ma, "%/năm", height=260, ten="tpdn-ytm-ma")
            bang_ma = h[["ma_gd", "kl", "gt_ty", "gia_bq_pct", "gia_cuoi_pct", "ytm", "ytm_gia_cuoi", "tpcp_spot",
                         "spread_bps", "ttm_nam", "mo_hinh_cf", "do_tin_cay_ytm", "ghi_chu"]].iloc[::-1]
            st.dataframe(bang_ma.head(300), width="stretch")
            dl_button(bang_ma, "TPDN_%s" % ma)

        with u[3]:
            tp = dl.load("tpcp_curve")
            if tp.empty:
                st.info("Chưa có tpcp_curve.csv.")
            else:
                moc_ngay = long.drop_duplicates("moc").set_index("moc").ngay_moc
                tps = tp.assign(ngay=tp.ngay.dt.strftime("%Y-%m-%d"))
                lop = []
                for m, _ in yc.MOC:
                    if m not in moc_ngay:
                        continue
                    tpc = yc.tpcp_curve_on(tps, pd.Timestamp(moc_ngay[m]).date())
                    if tpc:
                        lop.append(pd.DataFrame({"Kỳ hạn (năm)": tpc[0], "Spot (%)": tpc[1], "Mốc": MOC_NHAN[m]}))
                if lop:
                    tt_ = pd.concat(lop)
                    _title("Đường cong spot TPCP tại các mốc")
                    ch = (alt.Chart(tt_).mark_line(point=True, strokeWidth=2).encode(
                        x=alt.X("Kỳ hạn (năm):Q", scale=alt.Scale(type="log"),
                                axis=alt.Axis(values=[0.25, 0.5, 1, 2, 3, 5, 7, 10, 15, 20], format="~g", labelAngle=0, grid=False)),
                        y=alt.Y("Spot (%):Q", scale=alt.Scale(zero=False)),
                        color=alt.Color("Mốc:N", scale=alt.Scale(domain=MOC_ORDER, range=MOC_MAU), sort=MOC_ORDER,
                                        legend=alt.Legend(orient="bottom", columns=3)),
                        tooltip=["Mốc", "Kỳ hạn (năm)", alt.Tooltip("Spot (%):Q", format=".2f")])
                          .properties(height=320, usermeta=EMBED))
                    show(ch, "tpcp-spot-cac-moc")
                ky = tp[tp.ky_han_nam.isin([1, 2, 5, 10])].pivot_table(index="ngay", columns="ky_han", values="spot_nam")
                ky.index.name = "date"
                ky = ky.rename(columns=lambda c: "TPCP " + c)
                line(cut(ky), "Spot TPCP theo thời gian (1 / 2 / 5 / 10 năm)", "%/năm", height=300, ten="tpcp-spot-chuoi")
                dl_button(ky, "TPCP_Spot", sheets={"Spot_1_2_5_10": ky,
                                                   "Cac_moc": pd.concat(lop) if lop else pd.DataFrame()})

# ============================================================== BIEU DO NHUNG
elif PAGE == "📺 Biểu đồ nhúng":
    st.title("Biểu đồ nhúng")
    st.caption("Biểu đồ từ dịch vụ bên thứ ba (cần Internet). Dữ liệu ở các trang khác "
               r"vẫn là dữ liệu offline trong `D:\market-data`.")
    t = tabs_bb(["Chart Việt Nam (VNDirect)", "Bản đồ nhiệt VN", "Chart quốc tế (TradingView)",
                 "So sánh nhiều mã (TradingView)"], "nhung")

    with t[0]:
        m = dl.meta()
        ds = ["VNINDEX", "VN30", "VNMIDCAP", "VNSMALLCAP", "HNXINDEX", "UPCOM"] + sorted(m.index)
        c1, c2 = st.columns([2, 1])
        sym = c1.selectbox("Mã / chỉ số", ds, index=0, accept_new_options=True)
        cao = c2.slider("Chiều cao (px)", 400, 1000, 640, step=40)
        url = f"https://dchart.vndirect.com.vn/?symbol={sym}&theme=dark"
        st.iframe(url, height=cao)
        st.markdown(f"[↗ Mở biểu đồ {sym} trong tab mới]({url}) "
                    "(dùng khi khung bên trên trống vì trình duyệt chặn nhúng)")
        st.caption("Nguồn: dchart.vndirect.com.vn — nền TradingView, dữ liệu Việt Nam, có đủ "
                   "chỉ số VN-Index/VN30 mà widget TradingView gốc không cho nhúng.")

    with t[1]:
        c1, c2, c3 = st.columns([1, 1, 2])
        HORIZON = {"1 phiên": 1, "1 tuần": 5, "1 tháng": 21, "3 tháng": 63, "12 tháng": 250}
        hz = c1.selectbox("Biến động", list(HORIZON), index=0)
        topn = c2.slider("Số mã", 100, 500, 300, step=50)
        san = c3.multiselect("Sàn", list(dl.VN_EX), default=["HOSE"])
        hm = dl.heatmap_df(HORIZON[hz], topn, tuple(san), D_TO.strftime("%Y-%m-%d"))
        if hm.empty:
            st.info("Không đủ dữ liệu.")
        else:
            echarts_treemap(hm, f"Vốn hoá & biến động {hz.lower()} — {len(hm)} mã, "
                                f"phiên {D_TO:%d/%m/%Y}", height=640)
            st.caption("Ô lớn = vốn hoá lớn; xanh = tăng, đỏ = giảm. Dữ liệu từ tv-history.csv "
                       "+ số CP screener TradingView (dữ liệu của mình, không phải bên thứ ba).")
            dl_button(hm.set_index("Mã"), "BanDoNhietVN")

    with t[2]:
        # widget mien phi cua TradingView chan phan lon CHI SO (SPX, DJI, N225...);
        # co phieu My, FX, hang hoa, crypto thi nhung binh thuong
        GOI_Y = ["NASDAQ:NVDA", "NASDAQ:AAPL", "NASDAQ:MSFT", "NASDAQ:TSLA", "NYSE:BRK.B",
                 "OANDA:XAUUSD", "TVC:USOIL", "FX:EURUSD", "FX:USDJPY", "BITSTAMP:BTCUSD",
                 "KRX:005930", "TWSE:2330", "HKEX:700"]
        c1, c2, c3 = st.columns([2, 1, 1])
        sym = c1.selectbox("Mã quốc tế", GOI_Y, index=0, accept_new_options=True,
                           help="Dạng SÀN:MÃ. Mã Việt Nam không nhúng được — dùng tab đầu tiên.")
        itv = c2.selectbox("Khung nến", ["D", "W", "M", "60"], index=0,
                           format_func=lambda x: {"D": "Ngày", "W": "Tuần", "M": "Tháng",
                                                  "60": "1 giờ"}[x])
        kieu = c3.selectbox("Kiểu", ["1", "3", "8"], index=0,
                            format_func=lambda x: {"1": "Nến", "3": "Đường", "8": "Heikin Ashi"}[x])
        tv_widget("advanced-chart", {
            "symbol": sym, "interval": itv, "style": kieu, "theme": "dark", "locale": "vi_VN",
            "timezone": "Asia/Ho_Chi_Minh", "width": "100%", "height": 600,
            "withdateranges": True, "hide_side_toolbar": False, "allow_symbol_change": True,
            "details": True, "support_host": "https://www.tradingview.com",
        }, height=620)

    with t[3]:
        chon = st.multiselect("Các mã cần so sánh",
                              ["NASDAQ:NVDA", "NASDAQ:AAPL", "OANDA:XAUUSD", "TVC:USOIL",
                               "FX:EURUSD", "KRX:005930", "TWSE:2330", "HKEX:700",
                               "BITSTAMP:BTCUSD"],
                              default=["NASDAQ:NVDA", "OANDA:XAUUSD", "BITSTAMP:BTCUSD"],
                              accept_new_options=True)
        if chon:
            tv_widget("symbol-overview", {
                "symbols": [[s, s + "|12M"] for s in chon],
                "chartOnly": False, "locale": "vi_VN", "colorTheme": "dark",
                "isTransparent": False, "width": "100%", "height": 520, "showVolume": False,
                "changeMode": "price-and-percent", "chartType": "line",
                "timezone": "Asia/Ho_Chi_Minh",
            }, height=560)

# ================================================================ KHO DU LIEU
elif PAGE == "🔎 Kho dữ liệu":
    st.title("Kho dữ liệu — xem & lọc bất kỳ bảng nào")
    fr = dl.freshness_df()
    # dataset xep theo KHUNG PHAN TICH (nhom trong REGISTRY), lua chon nho khi doi trang
    keys = sorted(dl.REGISTRY, key=lambda k: (dl.KHOI_THU_TU.get(dl.REGISTRY[k][1].split(" · ")[0], 9), dl.REGISTRY[k][1], dl.REGISTRY[k][0]))
    key = filt("selectbox", "Dataset", keys, key="kho_ds",
               format_func=lambda k: f"{dl.REGISTRY[k][1]}  ·  {dl.REGISTRY[k][0]}")
    ten, nhom, path, dcol, ecol, mota = dl.REGISTRY[key]
    st.caption(f"{mota}  \n`{path}`")
    d = dl.tv() if key == "tv_history" else dl.load(key)
    if key == "nso_monthly":                 # 5.600 series -> loc theo nhom chi tieu truoc
        nhom_tx = filt("selectbox", "Nhóm chỉ tiêu (khung phân tích)", list(dl.NHOM_NSO_TX), key="kho_nso_nhom")
        d = d[d.group.isin(dl.NHOM_NSO_TX[nhom_tx])]
    if ecol and ecol in d:
        ents = sorted(d[ecol].dropna().unique().tolist())
        pick = st.multiselect(f"Lọc {ecol}", ents, default=ents[:5] if len(ents) > 5 else ents)
        if pick:
            d = d[d[ecol].isin(pick)]
    if dcol in d and key not in ("nso", "nso_monthly"):      # so lieu nam/thang NSO: xem toan bo lich su
        dd = pd.to_datetime(d[dcol], errors="coerce")
        d = d[(dd >= D_FROM) & (dd <= D_TO)]
    st.write(f"**{len(d):,} dòng × {d.shape[1]} cột**")
    st.dataframe(d.tail(500).iloc[::-1], width="stretch", hide_index=True)
    numc = [c for c in d.columns if pd.api.types.is_numeric_dtype(d[c])]
    if numc and ecol and ecol in d and dcol in d:
        v = st.selectbox("Vẽ cột", numc)
        p = d.pivot_table(index=dcol, columns=ecol, values=v, aggfunc="last")
        line(p, f"{ten} — {v}", v)
    dl_button(d.set_index(d.columns[0]), f"Data_{key}")
    _ = fr

# ================================================================ XUAT EXCEL
elif PAGE == "⬇️ Xuất Excel":
    st.title("Xuất Excel")
    st.caption("Chọn các bảng cần dùng → tải về 1 file Excel nhiều sheet, cột đầu là ngày, "
               "quét vùng rồi Insert > Chart là ra biểu đồ.")
    st.info(f"Khung thời gian: **{D_FROM:%d/%m/%Y} → {D_TO:%d/%m/%Y}** "
            f"({MONTHS} tháng) — đổi ở thanh bên trái.")

    CHON = {
        "Giá trị giao dịch VN (ngày)": lambda: cut(dl.turnover_df()),
        "Chỉ số VN (giá, KL, GTGD)": lambda: cut(
            dl.load("indices").query("index_code in @dl.VN_IDX").pivot_table(
                index="date", columns="index_code", values="close", aggfunc="last")),
        "Khối ngoại VN (ngày)": lambda: cut(dl.flows_vn()),
        "Khối ngoại châu Á (tháng, USD)": lambda: dl.flows_region_df(D_FROM, D_TO),
        "Độ rộng thị trường": lambda: cut(dl.breadth_df()),
        "Dưới MA50/200/300": lambda: cut(dl.breadth_df())[
            [c for c in dl.breadth_df().columns
             if "MA50" in c or "MA200" in c or "MA300" in c]],
        "Vốn hoá nhóm quy mô": lambda: dl.sectors(since=SINCE, end=SINCE_TO)[1],
        "Chỉ số ngành (rebase 100)": lambda: dl.sectors(since=SINCE, end=SINCE_TO)[0],
        "Tổng kết ngành": lambda: dl.sector_summary(months=MONTHS, end=D_TO),
        "Tăng trưởng EPS toàn TT": lambda: cut(
            dl.eps_market_df().pivot_table(index="Ngày", columns="code",
                                           values="Tăng trưởng EPS (%)", aggfunc="last")),
        "EPS TTM theo rổ": lambda: cut(
            dl.eps_market_df().pivot_table(index="Ngày", columns="code",
                                           values="EPS TTM (điểm)", aggfunc="last")),
        "Tăng trưởng LN theo ngành": lambda: dl.eps_sector_df(2, SINCE_TO),
        "Định giá thị trường VN": lambda: cut(
            dl.load("valuation_wide").pivot_table(index="date", columns="code", values="pe",
                                                  aggfunc="last")),
        "Thanh khoản khu vực (USD)": lambda: cut(
            dl.load("indices").pivot_table(index="date", columns="index_code", values="value_usd",
                                           aggfunc="last")),
        "Tài khoản NĐT (VSDC)": lambda: cut(dl.load("vsdc").set_index("date")),
    }
    pick = st.multiselect("Bảng", list(CHON), default=list(CHON)[:6])
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
        st.download_button("⬇️ Tải file", st.session_state["xlsx"],
                           file_name=f"MarketData_{date.today():%Y%m%d}.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           type="primary")

    st.divider()
    st.subheader("Chart Pack (file có sẵn biểu đồ bạn đã dựng)")
    cp = os.path.join(dl.BASE, "chart-pack", "Chart_Pack_TTCK.xlsx")
    if os.path.exists(cp):
        c1, c2 = st.columns([1, 2])
        with c1:
            if st.button("🔁 Cập nhật sheet GTGD trong Chart Pack"):
                r = subprocess.run([sys.executable, os.path.join(dl.BASE, "chart-pack", "add_sheet.py")],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
                st.code((r.stdout or "") + (r.stderr or "")[-800:])
        with c2:
            st.caption(f"`{cp}` — cập nhật lần cuối "
                       f"{pd.Timestamp(os.path.getmtime(cp), unit='s', tz='Asia/Ho_Chi_Minh'):%d/%m %H:%M}")
            with open(cp, "rb") as f:
                st.download_button("⬇️ Tải Chart Pack", f.read(), file_name="Chart_Pack_TTCK.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ================================================================ XUAT EXCEL (cuoi script)
xuat.ket_thuc(PAGE, {
    "thu_tu_trang": TRANG_XUAT,
    "dong_mo_ta": (f"Khung thời gian {D_FROM:%d/%m/%Y} → {D_TO:%d/%m/%Y} · Phân ngành ICB cấp {ICB_CAP}"
                   f" (Vietcap){', tách Vingroup' if ICB_VIN else ''} · Chuỗi tháng/quý: "
                   f"{'toàn bộ lịch sử' if DAI_THAP else 'cắt theo khung'}"),
    "hien_thi": {"Khoảng thời gian": f"{ky}: {D_FROM:%d/%m/%Y} → {D_TO:%d/%m/%Y} ({MONTHS} tháng)",
                 "Phiên gần nhất": f"{LAST:%d/%m/%Y}",
                 "Phân ngành": f"ICB cấp {ICB_CAP} (Vietcap)" + (", tách Vingroup" if ICB_VIN else ""),
                 "Chuỗi tháng/quý": "toàn bộ lịch sử" if DAI_THAP else "cắt theo khung",
                 "Trang xuất": ", ".join(TRANG_XUAT) if xuat.K_ALL in st.session_state else PAGE},
}, XUAT_NUT)
