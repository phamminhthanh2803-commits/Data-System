# -*- coding: utf-8 -*-
r"""
PORT & VESSEL TRACKER - theo dõi cảng và tàu của 12 cảng vụ hàng hải (D:\shipping).
Chạy:  D:\shipping\port-tracker\Chay-app.bat   (http://localhost:8766)

GIAO DIỆN (09/10/2026): theo mẫu "Genea" dùng chung với Market Data App (ui_genea.py: nền be sáng, thẻ biểu đồ Plotly có kỳ + nút xuất,
điều hướng 3 cấp trên đầu trang, không sidebar). Cấp 1 = 5 trang: Tổng quan · Hãng tàu & tàu · Điều độ & cảnh báo · Tuyến · Dữ liệu.
Cấp 2 (trên MỌI trang) = phạm vi: Toàn quốc · Từng cảng vụ · Từng cảng (bến). Bộ lọc chung (loại tàu, đo lường, độ phân giải, dữ liệu nạp)
nằm ngay dưới header. Deep-link: ?trang=<trang>/<pham-vi>&cv=HP&ben=HICT  (vd ?trang=dieu-do/cang-vu&cv=HCM).

DỮ LIỆU: pipeline ghép liên tục (bước port-tracker: cloud 9:00 + 22:00 cho 11 cảng vụ, laptop 8:30 + 18:40 cho TP.HCM, xem pt_update.py)
vào kho chia sẻ store/ (parquet, đồng bộ Google Drive). Khi mở, app chỉ nạp các file store mới vào sqlite riêng cache\\live.sqlite rồi
phân tích trong bộ nhớ (livedata.py + trackerlib.py). Vẫn gọi thẳng được trang nguồn qua chip "Kho dữ liệu" ở header.
"""
import os, sys, tempfile, threading, time
from datetime import date

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trackerlib as tl  # noqa: E402
import livedata as ld   # noqa: E402
import ui_genea as ui   # noqa: E402
import econdb as ed     # noqa: E402
import nowcast as nw    # noqa: E402
import services as svm   # noqa: E402


# ---------------------------------------------------------------- BỘ NHỚ ĐỆM THEO PHIÊN BẢN + VAN AN TOÀN RAM (21/10/2026)
# Lỗi "Error running app" trên Streamlit Cloud: st.cache_data khoá theo mtime/phiên bản KHÔNG giới hạn -> mỗi lần cloud kéo dữ liệu mới
# từ Drive thêm 1 bản (vd giá cổ phiếu ~400 MB), bản cũ ở lại -> RAM tăng dần tới > 1 GB -> Cloud tắt app.
import functools as _ft
import gc as _gc
import inspect as _insp


def _is_ver(name):
    return name.startswith("mt") or name.endswith("stamp") or name in ("ver", "fver")


def vcache(*dargs, **kw):
    """st.cache_data chỉ giữ PHIÊN BẢN dữ liệu mới nhất: tham số tên mt*/…stamp/ver/fver là phiên bản; cùng các tham số còn lại mà
    phiên bản đổi -> xoá cache của hàm này (bản cũ không nằm lại trong RAM)."""
    def deco(f):
        kw.setdefault("max_entries", 32)
        cf = st.cache_data(**kw)(f)
        names = list(_insp.signature(f).parameters)
        vnames = [n for n in names if _is_ver(n)]
        seen = {}

        @_ft.wraps(f)
        def w(*a, **k):
            args = dict(zip(names, a)); args.update(k)
            ver = tuple(args.get(n) for n in vnames)
            try:
                other = hash(tuple((n, args[n]) for n in names if n in args and n not in vnames and not n.startswith("_")))
            except TypeError:
                other = None
            if vnames and other is not None:
                if other in seen and seen[other] != ver:
                    cf.clear(); seen.clear()
                seen[other] = ver
            return cf(*a, **k)
        w.clear = cf.clear
        return w
    if dargs and callable(dargs[0]):
        return deco(dargs[0])
    return deco


def mem_guard(limit_mb=None):
    """RAM tiến trình vượt ngưỡng (env MEM_GUARD_MB, mặc định 850) -> xoá cache dữ liệu + trả RAM về hệ điều hành.
    Trang sau chậm hơn một chút nhưng app không bị Cloud tắt. Trả về True nếu đã dọn."""
    try:
        import psutil
        lim = float(limit_mb or os.environ.get("MEM_GUARD_MB", "850"))
        if psutil.Process().memory_info().rss / 1e6 < lim:
            return False
        st.cache_data.clear(); _gc.collect()
        try:
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:  # noqa: BLE001
            pass
        return True
    except Exception:  # noqa: BLE001
        return False


def _fresh(mod):
    """server Streamlit đang chạy giữ module cũ trong bộ nhớ (chỉ app.py được nạp lại) -> nạp lại khi file module đổi"""
    import importlib
    t = os.path.getmtime(mod.__file__)
    if getattr(mod, '_LOADED_MTIME', None) != t:
        try: mod = importlib.reload(mod)
        except (KeyError, ImportError):            # Streamlit vừa gỡ module khỏi sys.modules lúc cập nhật code (bản online) -> nạp mới
            mod = importlib.import_module(mod.__name__)
        mod._LOADED_MTIME = t
    return mod


ed = _fresh(ed); nw = _fresh(nw)

st.set_page_config(page_title='Port & Vessel Tracker', page_icon='⚓', layout='wide', initial_sidebar_state='collapsed')
ui.inject_css()


def _gate():
    """bản online public: nếu secret APP_PASSWORD có thì phải nhập mật khẩu (dữ liệu EconDB là gói trả phí, không phát tán)"""
    try: pw = st.secrets.get('APP_PASSWORD')
    except Exception: pw = None  # noqa: E701,BLE001
    if not pw or st.session_state.get('_auth_ok'): return
    _, mid, _ = st.columns([2, 3, 2])
    with mid:
        st.markdown('<div class="gn-logo" style="margin-top:12vh"><span class="dia"></span>Port &amp; Vessel Tracker</div>', unsafe_allow_html=True)
        v = st.text_input('Mật khẩu', type='password', key='_pw')
        if v and v == str(pw): st.session_state['_auth_ok'] = True; st.rerun()
        if v: st.error('Sai mật khẩu')
    st.stop()


import cloud_boot_pt as cb   # noqa: E402
try:
    CLOUD = cb.boot()            # 17/10/2026: kéo dữ liệu + bật luồng làm mới TRƯỚC màn hình mật khẩu -> lượt keepalive giữ dữ liệu luôn sẵn
except cb.DriveAuthError as _e:
    st.error(str(_e)); st.stop()
_gate()
ui.PERIOD_MONTHS['2Y'] = 24
# 21/10/2026: dữ liệu TRÌNH BÀY dựng sẵn bởi bước pipeline pt-present (present.py) -> app chỉ đọc parquet, không SQLite / ghép chuyến
PRESENT_DIR = os.path.join(ld.STORE, 'present')


def _present_meta():
    f = os.path.join(PRESENT_DIR, 'meta.json')
    if not os.path.exists(f): return None
    try:
        import json
        with open(f, encoding='utf-8') as fh: return json.load(fh)
    except Exception: return None  # noqa: E701,BLE001


PMETA = _present_meta()
PRESENT = PMETA is not None
PER = ['3M', '6M', '1Y', '2Y', '3Y', 'All']
MEASURES = {'Lượt tàu': 'calls', 'TEU danh nghĩa': 'teu', 'DWT': 'dwt'}
TOK = ui.TOK


# ================================================================ dữ liệu: đọc bản dựng sẵn (present) hoặc ghép từ kho
def _p_read(name):
    f = os.path.join(PRESENT_DIR, name)
    if not os.path.exists(f): return pd.DataFrame()
    d = pd.read_parquet(f)
    for c in d.columns:                                   # category -> chữ thường: giữ nguyên hành vi groupby/pivot (RAM còn thấp hơn nhờ gộp chuỗi)
        if isinstance(d[c].dtype, pd.CategoricalDtype): d[c] = d[c].astype(object)
    return d


def _p_years(lo):
    """các năm cần đọc từ mốc lo; bản online thiếu năm cũ thì kéo thêm từ Drive (chỉ khi chọn '3 năm' / 'Từ 2019')"""
    ys = [y for y in (PMETA or {}).get('years', []) if y >= pd.Timestamp(lo).year]
    miss = [y for y in ys if not os.path.exists(os.path.join(PRESENT_DIR, f'calls_{y}.parquet'))]
    if miss and CLOUD:
        with st.spinner(f'Đang kéo thêm dữ liệu các năm {", ".join(map(str, miss))}…'):
            cb.pull_items([('port-tracker', [f'/store/present/{k}_{y}.parquet' for y in miss for k in ('calls', 'visits')])])
    return [y for y in ys if os.path.exists(os.path.join(PRESENT_DIR, f'calls_{y}.parquet'))]


def p_table(kind, lo, ver):                               # không cache riêng: get_calls / get_visits đã cache (tránh 2 bản trong RAM)
    """chuyến / lượt cập bến dựng sẵn từ mốc lo"""
    ys = _p_years(lo)
    d = pd.concat([_p_read(f'{kind}_{y}.parquet') for y in ys], ignore_index=True) if ys else pd.DataFrame()
    col = 'date' if kind == 'calls' else 'arr_day'
    return d[d[col] >= pd.Timestamp(lo)].reset_index(drop=True) if len(d) else d


# ================================================================ dữ liệu: ghép từ kho (khoá cache = phiên bản kho)
@vcache(show_spinner='Đang ghép chuyến phần lịch sử (mỗi tháng chỉ tính 1 lần)…', max_entries=6, persist='disk')
def get_frozen(auths, lo, b, fver, cv=2):
    return tl.calls_frozen(auths, lo, b)


@vcache(show_spinner='Đang ghép chuyến từ dữ liệu vừa kéo…', max_entries=6)
def get_tail(auths, b, hi, ver, cv=2):
    return tl.calls_tail(auths, b, hi)


@vcache(show_spinner=False, max_entries=6)
def get_calls(auths, lo, hi, ver, mstamp):
    if PRESENT: return p_table('calls', lo, ver)
    b = str((TODAY.replace(day=1) - pd.DateOffset(months=1)).date())
    t0 = time.time(); fz = get_frozen(auths, lo, b, ld.version_before(auths, pd.Timestamp(b) + pd.Timedelta(days=30)))
    t1 = time.time(); tail = get_tail(auths, b, hi, ver)
    if os.environ.get('PT_PROFILE'): print(f'[profile]   frozen {t1 - t0:.1f}s, tail {time.time() - t1:.1f}s', flush=True)
    parts = [x for x in (fz, tail) if len(x)]
    return tl.enrich_calls(pd.concat(parts, ignore_index=True)) if parts else pd.DataFrame()


@vcache(show_spinner='Đang tách lượt cập bến…', max_entries=6)
def get_visits(auths, lo, hi, ver, mstamp):
    if PRESENT: return p_table('visits', lo, ver)
    c = get_calls(auths, lo, hi, ver, mstamp)
    return tl.load_visits(c, tl.terminal_meta(c))


def get_lanes(auths, lo, hi, ver, mstamp):
    if PRESENT and MONTHS == PMETA.get('lanes_months', 26):     # khung mặc định: chặng dựng sẵn
        return _p_cached('lanes', ver), _p_cached('patterns', ver), _p_cached('legs', ver)
    key = (auths, lo, hi, str(TODAY.date()), (ver if PRESENT else ld.version_before(auths, TODAY - pd.Timedelta(days=30))), mstamp)
    cache = st.session_state.setdefault('_lanes', {})
    if key not in cache:
        with st.spinner('Đang tính chặng và vòng tuyến…'):
            cache.clear(); cache[key] = tl.build_lanes(get_calls(auths, lo, hi, ver, mstamp))
    return cache[key]


@vcache(show_spinner=False, max_entries=12)
def _p_cached(name, ver): return _p_read(f'{name}.parquet')


@vcache(max_entries=2)
def get_master(ver, mstamp):
    if PRESENT:
        m = _p_cached('master', ver)
        for c in ('teu', 'dwt', 'gt', 'loa', 'calls_total', 'calls_12m'):
            if c in m: m[c] = pd.to_numeric(m[c], errors='coerce')
        return m
    return tl.master_live()


@vcache(show_spinner=False, max_entries=2)
def get_services(estamp, mstamp):
    """vòng tuyến + dịch vụ từ lượt ghé toàn cầu EconDB (store/econdb/vessel_portcalls.parquet); hãng đã biết lấy từ vessel_master"""
    if PRESENT:                                          # dựng sẵn: dịch vụ + vòng tuyến; danh sách tàu EconDB đọc kho nhỏ
        rot = _p_cached('rotations', VER)
        if len(rot): rot['ports'] = rot['ports'].fillna('').str.split(' ').map(tuple)
        return _p_cached('services', VER), rot, ed.load().get('vessels', pd.DataFrame())
    E = ed.load(('vessel_portcalls', 'vessel_services', 'vessels')); pc = E.get('vessel_portcalls')
    if pc is None or pc.empty: return pd.DataFrame(), pd.DataFrame(), E.get('vessels', pd.DataFrame())
    m = tl.load_master()
    ops = {}
    for imo, op in zip(m.get('imo', pd.Series(dtype=str)), m.get('operator', pd.Series(dtype=str))):
        try:
            if op and str(op) != 'nan': ops[int(float(imo))] = op
        except (TypeError, ValueError): pass
    import carrier_services as cs_
    rot0 = svm.rotations(pc)
    svc, rot = svm.cluster(rot0, ops, names={**svm.service_names(E.get('vessel_services')), **svm.names_for_rotations(rot0, cs_.load(), ops)})
    return svc, rot, E.get('vessels', pd.DataFrame())


def live_pull(auths, d0, d1, ttl, max_pages, label, auto=False):
    """Gọi trang nguồn cho các ngày thiếu/cũ, có thanh tiến độ. Trả về (số trang đã kéo, số trang còn thiếu, lỗi)."""
    todo = ld.plan(auths, d0, d1, ttl_min=ttl)
    need = sum(len(v) for v in todo.values())
    if auto:
        todo = {a: ds for a, ds in todo.items() if not ld.cooling(a)}
        recent = (TODAY - pd.Timedelta(days=3)).date()
        todo = {a: (ds if len(ds) <= 12 else [d for d in ds if d >= recent]) for a, ds in todo.items()}
        todo = {a: ds for a, ds in todo.items() if ds}
    if not todo: return 0, need, []
    take = sum(min(len(v), max_pages) if max_pages else len(v) for v in todo.values())
    state = {'i': 0, 'a': '', 'd': ''}; res = {}
    def cb(i, n, a, d): state.update(i=i, a=a, d=str(d))
    def run(): res['out'] = ld.ensure(auths, d0, d1, ttl_min=ttl, max_pages=max_pages, progress=cb, todo=todo)
    t = threading.Thread(target=run, daemon=True); t.start()
    bar = st.progress(0.0, text=f'{label}: 0/{take} trang')
    while t.is_alive():
        bar.progress(min(1.0, state['i'] / max(take, 1)), text=f"{label}: {state['i']}/{take} trang · {tl.AUTH_LABEL.get(state['a'], state['a'])} {state['d']}")
        time.sleep(0.25)
    bar.empty()
    n, errs = res.get('out', (0, ['khong chay duoc']))
    return n, need - take, errs


TODAY = pd.Timestamp.today().normalize()
_T0 = [time.time()]


def tick(label):
    if os.environ.get('PT_PROFILE'): print(f'[profile] {label}: {time.time() - _T0[0]:.1f}s', flush=True)
    _T0[0] = time.time()


# ================================================================ tiện ích
def fmt_int(v): return '–' if v is None or pd.isna(v) else f'{v:,.0f}'.replace(',', '.')
def fmt_pct(v): return None if v is None or pd.isna(v) else f'{v * 100:+.1f}%'.replace('.', ',')
def fmt_h(v): return '–' if v is None or pd.isna(v) else f'{v:.1f}'.replace('.', ',')


def add_measure(df):
    d = df.copy(); d['calls'] = 1
    d['teu'] = pd.to_numeric(d['teu'], errors='coerce').fillna(0); d['dwt'] = d['dwt'].fillna(0)
    return d


def bucket(s, freq):
    """kỳ = mốc CUỐI kỳ: tuần -> Chủ nhật, tháng -> ngày cuối tháng (chuẩn chung 15/10/2026)"""
    return s.dt.to_period('W-SUN').dt.end_time.dt.normalize() if freq == 'Tuần' else s.dt.to_period('M').dt.to_timestamp('M')


def by_period(df, lo=None, hi=None):
    """lọc khung ngày [lo, hi] (mặc định của thẻ) rồi gán kỳ. 21/10/2026: GIỮ kỳ cuối chưa trọn (= lũy kế tới ngày dữ liệu cuối);
    biểu đồ tự vẽ kỳ đó mờ / nét đứt (ui.PARTIAL)"""
    d = df[(df['arr_day'] >= pd.Timestamp(lo if lo is not None else LO)) & (df['arr_day'] <= pd.Timestamp(hi if hi is not None else LAST))].copy()
    if d.empty: return d
    d['ky'] = bucket(d['arr_day'], FREQ)
    first = d['ky'].min() if len(d) else None
    if first is not None:
        p0 = first - pd.Timedelta(days=6) if FREQ == 'Tuần' else first.replace(day=1)     # ngày đầu kỳ đầu tiên
        if d.loc[d['ky'] == first, 'arr_day'].min() > p0 + pd.Timedelta(days=2 if FREQ == 'Tuần' else 5): d = d[d['ky'] > first]
    return d


def yoy_total(df, idx):
    """% tổng (đo lường đang chọn) so CÙNG KỲ năm trước tại các kỳ idx. Kỳ đang chạy so cùng SỐ NGÀY năm trước."""
    if df is None or df.empty or idx is None or not len(idx): return pd.Series(dtype=float)
    d = df[['arr_day', MEAS]].copy(); d['ky'] = bucket(d['arr_day'], FREQ)
    tot = d.groupby('ky')[MEAS].sum()
    out = {}
    for k in pd.DatetimeIndex(idx):
        prev = (k - pd.DateOffset(years=1)) if FREQ == 'Tháng' else (k - pd.Timedelta(weeks=52))
        if FREQ == 'Tháng': prev = prev + pd.offsets.MonthEnd(0)
        cur_v = tot.get(k, np.nan)
        if LAST < k:                                              # kỳ đang chạy: lũy kế tới LAST so cùng số ngày năm trước
            p0 = (k.replace(day=1) if FREQ == 'Tháng' else k - pd.Timedelta(days=6)) - (pd.DateOffset(years=1) if FREQ == 'Tháng' else pd.Timedelta(weeks=52))
            p1 = LAST - (pd.DateOffset(years=1) if FREQ == 'Tháng' else pd.Timedelta(weeks=52))
            base = d.loc[(d['arr_day'] >= p0) & (d['arr_day'] <= p1), MEAS].sum()
        else:
            base = tot.get(prev, np.nan)
        out[k] = (cur_v / base - 1) * 100 if base and base == base and base > 0 else np.nan
    y = pd.Series(out, name='YoY tổng (%)')
    # lịch cảng vụ chỉ có Cái Mép từ 08/2025 -> phạm vi có Cái Mép: YoY chỉ so được từ 08/2026 (hai kỳ cùng phạm vi)
    hcm = (df['auth'] == 'HCM') if 'auth' in df else pd.Series(False, index=df.index)
    has_cm = (hcm & (df['terminal'].map(_tp_hcm) == CM_PORT)).any() if 'terminal' in df else hcm.any()   # bảng chuyến (không có bến): có HCM là tính
    if has_cm: y[y.index < YOY_CM_FROM] = np.nan
    return y


_tp_hcm = ed.terminal_port('HCM')
YOY_CM_FROM = pd.Timestamp('2026-08-31')


def with_yoy(fig, df, w):
    """công tắc YoY bật: thêm đường YoY của TỔNG biểu đồ (trục phải)"""
    if not YOY or fig is None or w is None or w.empty: return fig
    y = yoy_total(df, w.index).dropna()
    if y.empty and len(w) and 'auth' in df and (df['auth'] == 'HCM').any():
        fig.add_annotation(x=1, y=1, xref='paper', yref='paper', xanchor='right', yanchor='bottom', showarrow=False,
                           text='YoY từ 08/2026 (dữ liệu Cái Mép có từ 08/2025)', font=dict(size=10, color=TOK['down']))
    if y.empty: return fig
    fig.add_trace(go.Scatter(x=y.index, y=y.values, name='YoY tổng (%)', mode='lines+markers', yaxis='y2',
                             line=dict(color=TOK['down'], width=1.8, dash='dash'), marker=dict(size=4),
                             hovertemplate='%{y:+.1f}%<extra>YoY tổng</extra>'))
    fig.update_layout(yaxis2=dict(overlaying='y', side='right', showgrid=False, ticksuffix='%', zeroline=True, zerolinecolor=TOK['ink3'],
                                  tickfont=dict(size=11, color=TOK['down'])), showlegend=True)
    return fig


def entity_order(df, key, value):
    """thứ tự thực thể CỐ ĐỊNH theo tổng 24 tháng gần nhất -> màu đi theo thực thể, không đổi khi lọc kỳ"""
    d = df[df['arr_day'] >= LAST - pd.DateOffset(months=24)]
    return d.groupby(key)[value].sum().sort_values(ascending=False).index.tolist()


def wide(d, dim, order, n=7, share_of=None):
    """bảng rộng kỳ × thực thể (top n + Khác). share_of: DataFrame cùng kỳ để tính thị phần (%)"""
    if d.empty: return pd.DataFrame()
    d2, keep = tl.top_n_other(d, dim, MEAS, n=n, order=order)
    w = d2.groupby(['ky', dim])[MEAS].sum().unstack(dim).reindex(columns=keep).fillna(0)
    w.index = pd.DatetimeIndex(w.index); w.index.name = 'Kỳ'
    if share_of is not None:
        tot = share_of.groupby('ky')[MEAS].sum().reindex(w.index).replace(0, np.nan)
        w = w.div(tot, axis=0) * 100
        if 'Khác' in w: w = w.drop(columns=['Khác'])
    return w


def kpi_30(d, unit):
    """4 KPI 30 ngày (so 30 ngày trước); giờ nằm cảng = trung vị"""
    base = d[d['arr_day'] >= LAST - pd.Timedelta(days=800)]; end = LAST + pd.Timedelta(days=1)
    items = []
    for lab, m in [(f'{unit}, 30 ngày', 'calls'), ('TEU danh nghĩa, 30 ngày', 'teu'), ('DWT, 30 ngày', 'dwt')]:
        a, b, y = tl.period_compare(base, 'arr_day', m, end, 30)
        p = tl.pct(a, b); py = tl.pct(a, y)
        items.append((lab, fmt_int(a), f'{fmt_pct(p) or "–"} so 30 ngày trước · {fmt_pct(py) or "–"} cùng kỳ năm trước',
                      0 if p is None or pd.isna(p) else (1 if p >= 0 else -1)))
    cur = base[(base['arr_day'] >= end - pd.Timedelta(days=30)) & (base['arr_day'] < end)]
    prv = base[(base['arr_day'] >= end - pd.Timedelta(days=60)) & (base['arr_day'] < end - pd.Timedelta(days=30))]
    h1, h0 = cur['hours_in_port'].median(), prv['hours_in_port'].median()
    dh = None if pd.isna(h0) or pd.isna(h1) else h1 - h0
    items.append(('Giờ nằm cảng (trung vị)', fmt_h(h1), ('–' if dh is None else f'{dh:+.1f} giờ'.replace('.', ',')) + f' · {cur["ship_key"].nunique()} tàu khác nhau',
                  0 if dh is None else (-1 if dh > 0 else 1)))
    ui.kpi_strip(items)


def fig_heat(hm, xs, ys, xlab):
    z = hm.pivot(index='operator', columns='ben', values=MEAS).reindex(index=ys, columns=xs)
    fig = go.Figure(go.Heatmap(z=z.values, x=xs, y=ys, colorscale=[[0, '#fdf3ec'], [0.5, TOK['orange_light']], [1, TOK['orange']]],
                               hovertemplate='%{y}<br>%{x}: %{z:,.0f}<extra></extra>', showscale=False, xgap=2, ygap=2))
    fig.update_layout(height=max(260, 28 * len(ys) + 120), hovermode='closest', margin=dict(l=6, r=6, t=10, b=6),
                      xaxis=dict(tickangle=-35, title=xlab, tickfont=dict(size=11)), yaxis=dict(autorange='reversed', tickfont=dict(size=12, color=TOK['ink'])))
    return fig


@vcache(show_spinner=False, max_entries=1)
def get_term_services(estamp):
    f = os.path.join(ld.STORE, 'econdb', 'term_services.parquet')
    return pd.read_parquet(f) if os.path.exists(f) else pd.DataFrame()


@st.cache_resource(show_spinner=False, max_entries=1)
def iti_econ(estamp):
    """lượt ghé toàn cầu EconDB theo tàu (vessel_itinerary.Econ) - 1 bản dùng chung mọi phiên"""
    return tl.itinerary_module().Econ(os.path.join(ld.STORE, 'econdb'))


@st.cache_resource(show_spinner=False, max_entries=1)
def iti_dist(mt):
    """hải lý + đường đi trên biển giữa 2 cảng (cache port_pairs_nm.csv do bước itinerary tính sẵn)"""
    return tl.itinerary_module().Dist()


def _pairs_mt():
    f = tl.itinerary_module().PAIRS_CSV
    return os.path.getmtime(f) if os.path.exists(f) else 0


def fig_route_map(stops, dist, loop=False, height=520):
    """bản đồ lộ trình: đường đi trên biển giữa các điểm dừng liên tiếp (cache searoute; thiếu thì đường thẳng) + điểm dừng
    (cảng VN cam, cảng ngoài xám; cỡ theo số lượt ghé). loop=True: nối điểm cuối về điểm đầu (vòng tuyến dịch vụ)."""
    pts = [x for x in stops if x.get('lon') is not None and x.get('lat') is not None]
    if len(pts) < 2: return None
    seq = pts + ([pts[0]] if loop else [])
    lon, lat, miss = [], [], 0
    for a, b in zip(seq[:-1], seq[1:]):
        if a['port'] == b['port']: continue
        pth = dist.path(a, b, straight=False)             # chưa có đường biển tính sẵn -> không vẽ (tránh đường thẳng cắt qua lục địa)
        if not pth: miss += 1; continue
        for (x0, y0), (x1, y1) in zip(pth[:-1], pth[1:]):    # chèn điểm mỗi ~1,5 độ: Plotly nối 2 điểm bằng cung trắc địa, đoạn dài
            n_ = max(1, int(max(abs(x1 - x0), abs(y1 - y0)) / 1.5))   # sẽ cong khỏi đường biển của searoute (cắt qua đất liền)
            for j in range(n_): lon.append(x0 + (x1 - x0) * j / n_); lat.append(y0 + (y1 - y0) * j / n_)
        lon.append(pth[-1][0]); lat.append(pth[-1][1])
        lon.append(None); lat.append(None)
    fig = go.Figure(go.Scattergeo(lon=lon, lat=lat, mode='lines', line=dict(width=1.6, color=TOK['brown']), hoverinfo='skip', showlegend=False))
    agg = {}
    for x in pts:
        k = x['port']; a = agg.setdefault(k, {'lon': x['lon'], 'lat': x['lat'], 'n': 0, 'last': '', 'term': set(), 'moves': 0})
        a['n'] += 1; t = x.get('arrive') or x.get('t')
        if t: a['last'] = max(a['last'], t.strftime('%Y-%m-%d'))
        if x.get('terminal'): a['term'].update(t_ for t_ in str(x['terminal']).split('|') if t_)
        try: a['moves'] += int(float(x.get('moves') or 0))
        except (TypeError, ValueError): pass
    names = list(agg)
    vn = [n for n in names if agg[n]['lon'] and 102 <= agg[n]['lon'] <= 110 and 8 <= agg[n]['lat'] <= 23.5]
    for grp, col in ((vn, TOK['orange']), ([n for n in names if n not in vn], TOK['gray'])):
        if not grp: continue
        fig.add_trace(go.Scattergeo(
            lon=[agg[n]['lon'] for n in grp], lat=[agg[n]['lat'] for n in grp], mode='markers+text', text=grp, textposition='top center',
            textfont=dict(size=10, color=TOK['ink2']), showlegend=False,
            marker=dict(size=[min(7 + 2.5 * agg[n]['n'], 22) for n in grp], color=col, line=dict(width=0.6, color='white')),
            customdata=[[agg[n]['n'], agg[n]['last'], ', '.join(sorted(agg[n]['term']))[:60], agg[n]['moves']] for n in grp],
            hovertemplate='<b>%{text}</b><br>%{customdata[0]} lượt · ghé cuối %{customdata[1]}<br>%{customdata[2]}'
                          '<br>TEU xếp dỡ (EconDB) %{customdata[3]:,.0f}<extra></extra>'))
    lo_ = [agg[n]['lon'] for n in names]; la_ = [agg[n]['lat'] for n in names]
    seg = [(x1, x2) for x1, x2 in zip(lon[:-1], lon[1:]) if x1 is not None and x2 is not None]
    if any(abs(x2 - x1) > 180 for x1, x2 in seg) or any(abs(x) > 180 for x in lon if x is not None):   # đường vắt qua kinh tuyến 180 (searoute ghi kinh độ > 180)
        lo_ = [x + 360 if x < 0 else x for x in lo_]
    c_lon = (max(lo_) + min(lo_)) / 2; c_lon = c_lon - 360 if c_lon > 180 else c_lon
    span = max(max(lo_) - min(lo_), (max(la_) - min(la_)) * 1.6, 8)
    fig.update_geos(projection_type='natural earth', showcountries=True, countrycolor='#d9d4cc', showland=True, landcolor='#f3efe8',
                    showocean=True, oceancolor='#eaf1f5', lakecolor='#eaf1f5', coastlinecolor='#c9c2b8', projection_rotation=dict(lon=c_lon),
                    center=dict(lon=c_lon, lat=(max(la_) + min(la_)) / 2), projection_scale=max(1.0, min(8.0, 300 / span)))
    fig.update_layout(height=height, margin=dict(l=0, r=0, t=0, b=0), meta='no_labels no_partial')
    if miss: fig.add_annotation(text=f'{miss} chặng chưa có đường biển tính sẵn (không vẽ)', x=0.01, y=0.01, xref='paper', yref='paper',
                                showarrow=False, font=dict(size=11, color=TOK['ink2']), xanchor='left', yanchor='bottom')
    return fig


def fig_gantt(g):
    g = g.copy(); g['Cảng vụ'] = g['auth'].map(tl.AUTH_LABEL); g['ben'] = g['first_berth'].replace('', '(chưa rõ bến)')
    fig = px.timeline(g, x_start='arrival', x_end='departure', y='ben', color='Cảng vụ', color_discrete_sequence=ui.PALETTE,
                      hover_data={'arrival': '|%d/%m/%Y %H:%M', 'departure': '|%d/%m/%Y %H:%M', 'hours_in_port': ':.1f', 'origin': True, 'destination': True, 'ben': False})
    fig.update_yaxes(autorange='reversed', title=None); fig.update_xaxes(title=None, tickformat='%d/%m')
    fig.update_layout(height=max(160, 30 * g['ben'].nunique() + 80), hovermode='closest', bargap=0.35, margin=dict(l=6, r=6, t=30, b=6))
    return fig


def to_xlsx_sheets(sheets): return tl.to_excel(sheets)


def dl_row(df, name, key):
    """2 nút tải nhỏ (CSV / Excel) cho bảng không nằm trong thẻ"""
    c1, c2, _ = st.columns([1, 1, 6])
    c1.download_button('⤓ CSV', df.to_csv(index=False).encode('utf-8-sig'), file_name=f'{name}.csv', key=f'c_{key}', width='stretch')
    c2.download_button('⤓ Excel', to_xlsx_sheets({name[:31]: df}) if len(df) <= 200000 else b'', file_name=f'{name}.xlsx', key=f'x_{key}', width='stretch', disabled=len(df) > 200000)


# ================================================================ điều hướng + deep-link
PAGES = {'tong-quan': 'Tổng quan', 'hang-tau': 'Hãng tàu & tàu', 'dieu-do': 'Điều độ & cảnh báo', 'tuyen': 'Tuyến dịch vụ',
         'san-luong': 'Sản lượng', 'du-lieu': 'Dữ liệu'}
LEVELS = {'toan-quoc': 'Toàn quốc', 'cang-vu': 'Từng cảng vụ', 'cang': 'Từng cảng'}
CU = {'ben-cang': 'tong-quan', 'tau': 'hang-tau', 'canh-bao': 'dieu-do', 'econdb': 'san-luong', 'du-bao': 'san-luong'}            # slug trang cũ
ALL_AUTHS = list(ld.AUTHS)


def _doc_query():
    if st.session_state.get('_nav_init'): return
    st.session_state['_nav_init'] = True
    q = st.query_params.get('trang') or ''; parts = [p for p in q.split('/') if p]
    if parts:
        pg = CU.get(parts[0], parts[0])
        if pg in PAGES: ui.set_nav('nav_page', pg)
        if len(parts) > 1 and parts[1] in LEVELS: ui.set_nav('nav_lv', parts[1])
    cv = (st.query_params.get('cv') or '').upper()
    if cv in ALL_AUTHS: st.session_state['sel_auth'] = cv
    if st.query_params.get('ben'): st.session_state['_ben_q'] = st.query_params.get('ben').upper()


_doc_query()

# ================================================================ header: logo + chip kho dữ liệu (độ phủ, kéo từ nguồn)
h1, h2c = st.columns([5, 2])
with h1:
    st.markdown('<div class="gn-logo"><span class="dia"></span>Port &amp; Vessel Tracker</div>', unsafe_allow_html=True)
cov = pd.DataFrame(PMETA['coverage']) if PRESENT else ld.coverage()
with h2c:
    _, p = st.columns([1, 3])
    with p:
        with st.popover(f'Kho dữ liệu: {len(cov)} cảng vụ ▾', width='stretch'):
            ss = PMETA['store_status'] if PRESENT else ld.store_status()
            if PRESENT: ui.note(f'Bản trình bày dựng sẵn bởi pipeline lúc {PMETA["built_at"]} (bước pt-present) - app chỉ đọc, không ghép lại.')
            ui.note(f'Pipeline ghép liên tục: cloud 9:00 + 22:00 (11 cảng vụ), laptop 8:30 + 18:40 (TP.HCM) → kho chia sẻ store/ '
                    f'({ss["files"]} tệp parquet, cập nhật gần nhất {ss["latest"] or "–"}). Ngày đã qua hơn 2 ngày coi là chốt.')
            if len(cov):
                cv2 = cov.copy(); cv2['Cảng vụ'] = cv2['auth'].map(tl.AUTH_LABEL); cv2['o'] = cv2['auth'].map({a: i for i, a in enumerate(tl.AUTH_ORDER)})
                st.dataframe(cv2.sort_values('o')[['Cảng vụ', 'tu_ngay', 'den_ngay', 'so_ngay', 'so_su_kien', 'keo_gan_nhat']]
                             .rename(columns={'tu_ngay': 'Từ', 'den_ngay': 'Đến', 'so_ngay': 'Số ngày', 'so_su_kien': 'Sự kiện', 'keo_gan_nhat': 'Kéo gần nhất'}),
                             width='stretch', hide_index=True, height=40 + 35 * len(cv2))
            if PRESENT: LIVE, TTL, FORCE = False, 30, False         # bản dựng sẵn: không gọi nguồn từ app
            else:
                LIVE = st.toggle('Kéo thêm từ trang nguồn khi mở', value=False, key='live_on',
                                 help='Kho đã được pipeline cập nhật 2 lần/ngày. Bật khi cần số liệu trong ngày (gọi thẳng 12 trang cảng vụ, 10–60 giây).')
                TTL = st.select_slider('Làm mới ngày gần đây sau (phút)', [5, 10, 30, 60, 180], value=30, key='ttl')
                FORCE = st.button('🔄 Kéo lại từ nguồn ngay', key='force_pull', width='stretch')

# ---- bộ lọc chung (thay sidebar cũ)
f1, f2, f3, f4, f5 = st.columns([1.3, 1.9, 1.2, 1.7, 3])
_t1, _t2, _t3 = f5.columns([0.9, 1.3, 2.6])
with _t1: YOY = st.toggle('YoY', value=False, key='f_yoy', help='Thêm đường % so cùng kỳ năm trước (trục phải) cho biểu đồ theo kỳ')
with _t2: ui.LABELS['on'] = st.toggle('Nhãn số liệu', value=False, key='f_lbl', help='Hiện số trên biểu đồ, cách quãng (~12 nhãn) cho đỡ chồng')
with f1: TAU = st.segmented_control('Loại tàu', ['Container', 'Mọi loại'], default='Container', key='f_tau') or 'Container'
with f2: MEAS_LABEL = st.segmented_control('Đo lường', list(MEASURES), default='TEU danh nghĩa', key='f_meas') or 'TEU danh nghĩa'
with f3: FREQ = st.segmented_control('Độ phân giải', ['Tháng', 'Tuần'], default='Tháng', key='f_freq') or 'Tháng'
with f4: NAP = st.segmented_control('Dữ liệu nạp', ['2 năm', '3 năm', 'Từ 2019'], default='2 năm', key='f_nap') or '2 năm'
ONLY_CONT = TAU == 'Container'; MEAS = MEASURES[MEAS_LABEL]
MONTHS = {'2 năm': 26, '3 năm': 38, 'Từ 2019': 400}[NAP]
tick('header')

# ================================================================ nạp kho + ghép chuyến
if not PRESENT:
    with st.spinner('Đang nạp dữ liệu mới từ kho chia sẻ store/ (lần đầu khoảng 1–2 phút)…'):
        N_IMP, _ = ld.import_store()
    if N_IMP: st.toast(f'Đã nạp {N_IMP} tệp mới từ kho chia sẻ')
    if ld.is_empty():
        with st.spinner('Khởi tạo kho dữ liệu của app từ lịch sử đã có (chỉ 1 lần, khoảng 1–2 phút)…'):
            ld.seed_from_local()
AUTHS = ALL_AUTHS
LOAD_LO = max(pd.Timestamp('2019-01-01'), TODAY - pd.DateOffset(months=MONTHS) - pd.Timedelta(days=45))
LOAD_HI = TODAY + pd.Timedelta(days=1)
if LIVE or FORCE:
    n_pull, n_left, errs = live_pull(AUTHS, LOAD_LO, LOAD_HI, 0 if FORCE else TTL, 40, 'Đang gọi trang nguồn các cảng vụ', auto=True)
    if n_pull: st.toast(f'Đã kéo trực tiếp {n_pull} trang từ nguồn')
    if n_left: ui.note(f'Còn {n_left} ngày-cảng vụ chưa có trong kho cho khoảng thời gian này. Vào trang "Dữ liệu" để kéo bù từ nguồn.')
    if errs:
        with st.expander(f'{len(errs)} lỗi khi gọi nguồn'): st.write(errs[:40])
tick('goi nguon')
VER = (PMETA['version'] + '|' + PMETA['built_at']) if PRESENT else ld.version()
MST = PMETA['built_at'] if PRESENT else tl.stamp('master', 'hp_terminals', 'hcm_terminals')
KEY = (tuple(AUTHS), str(LOAD_LO.date()), str(LOAD_HI.date()), VER, MST)
if st.session_state.get('_ver_key') != (VER, MST):        # phiên bản dữ liệu đổi -> bỏ kết quả mô hình / chặng của bản cũ trong phiên
    for _k in ('_nc', '_lanes'): st.session_state.pop(_k, None)
    st.session_state['_ver_key'] = (VER, MST)
with st.spinner('Đang ghép chuyến tàu từ kho (lần đầu trong tháng có thể mất 1–2 phút)…'):
    calls = get_calls(*KEY)
if calls.empty:
    st.error('Kho chưa có dữ liệu. Kiểm tra mạng hoặc vào trang "Dữ liệu" để kéo từ nguồn.'); st.stop()
visits = get_visits(*KEY)
if CLOUD and not PRESENT: cb.trim_memory()         # bản online: trả RAM tạm sau ghép chuyến (máy ~1 GB)
tick('get_calls+visits')
LAST = min(calls.loc[calls['arr_day'].notna(), 'arr_day'].max(), TODAY)
LO = LOAD_LO
ui.set_data_end(LAST); ui.DATA_MIN = LOAD_LO.date()
_cur = bucket(pd.Series([LAST]), FREQ).iloc[0]                    # mốc cuối kỳ đang chạy (tháng / tuần)
ui.PARTIAL.update(x=_cur if LAST < _cur else None, last=LAST, label=f'lũy kế đến {LAST:%d/%m}', freq=FREQ)
_upd = (VER.split('|')[1] or '')[:16]
with _t3:
    st.markdown(f'<div class="gn-note" style="margin-top:28px">Dữ liệu đến <b>{LAST:%d/%m/%Y}</b> · kho cập nhật {_upd} · '
                'TEU là sức chở danh nghĩa của tàu, không phải sản lượng xếp dỡ.</div>', unsafe_allow_html=True)

# khung chung: mọi lượt cập bến / chuyến theo bộ lọc loại tàu, mọi thời gian đã nạp
V_ALL = add_measure(visits[visits['is_container'] | (not ONLY_CONT)]); V_ALL['Cảng vụ'] = V_ALL['auth'].map(tl.AUTH_LABEL)
C_ALL = add_measure(calls[calls['arr_day'].notna() & (calls['is_container'] | (not ONLY_CONT))]); C_ALL['Cảng vụ'] = C_ALL['auth'].map(tl.AUTH_LABEL)


# ================================================================ phạm vi 3 cấp (cấp 2 của điều hướng, trên mọi trang)
def terminals_of(auth):
    return entity_order(V_ALL[V_ALL['auth'] == auth], 'terminal', MEAS)


def pick_scope(level):
    """cấp 'cang-vu': chọn cảng vụ; cấp 'cang': cảng vụ + bến. Lựa chọn nhớ qua các trang (key cố định)."""
    if level == 'toan-quoc': return None, None
    c1, c2, c3 = st.columns([1.3, 1.8, 4])
    auth = c1.selectbox('Cảng vụ', ALL_AUTHS, index=ALL_AUTHS.index(st.session_state.get('sel_auth', 'HP')),
                        format_func=lambda a: tl.AUTH_LABEL.get(a, a), key='w_auth')
    st.session_state['sel_auth'] = auth; st.query_params['cv'] = auth
    if level == 'cang-vu': return auth, None
    opts = terminals_of(auth)
    if not opts:
        c2.info('Cảng vụ này chưa có lượt cập bến theo bộ lọc.'); return auth, None
    want = st.session_state.pop('_ben_q', None) or st.session_state.get(f'sel_term_{auth}')
    term = c2.selectbox('Cảng / bến', opts, index=opts.index(want) if want in opts else 0, key=f'w_term_{auth}',
                        help='Thứ tự theo tổng 24 tháng gần nhất của đo lường đang chọn')
    st.session_state[f'sel_term_{auth}'] = term; st.query_params['ben'] = term
    with c3:
        m = V_ALL[(V_ALL['auth'] == auth) & (V_ALL['terminal'] == term)].drop_duplicates('terminal')
        if len(m):
            r = m.iloc[0]; extra = ' · '.join(x for x in (r.get('group', ''), f"mã CK {r['ticker']}" if r.get('ticker') else '', tl.CLASS_LABEL.get(r.get('kind', ''), r.get('kind', ''))) if x)
            st.markdown(f'<div class="gn-note" style="margin-top:28px">{extra}</div>', unsafe_allow_html=True)
    return auth, term


def scoped(level, auth=None, term=None):
    """(chuyến, lượt cập bến) trong phạm vi; cấp cảng: chuyến = chuyến có ghé bến đó"""
    if level == 'toan-quoc': return C_ALL, V_ALL
    if level == 'cang-vu': return C_ALL[C_ALL['auth'] == auth], V_ALL[V_ALL['auth'] == auth]
    v = V_ALL[(V_ALL['auth'] == auth) & (V_ALL['terminal'] == term)]
    return C_ALL[(C_ALL['auth'] == auth) & C_ALL['call_id'].isin(v['call_id'])], v


def scope_name(level, auth, term):
    return f'cả nước ({len(ALL_AUTHS)} cảng vụ)' if level == 'toan-quoc' else (tl.AUTH_LABEL[auth] if level == 'cang-vu' else f'{tl.AUTH_LABEL[auth]} · {term}')


def unit_txt(level): return 'Lượt cập bến' if level == 'cang' else 'Lượt tàu vào'


# ================================================================ TRANG 1: TỔNG QUAN
def page_overview(level, auth, term, K):
    c, v = scoped(level, auth, term)
    if (v if level == 'cang' else c).empty: ui.card_empty('Tổng quan', note_text='Không có dữ liệu trong phạm vi này.'); return
    ui.h2(f'Tổng quan · {scope_name(level, auth, term)}')
    kpi_30(v if level == 'cang' else c, unit_txt(level))

    if level == 'toan-quoc':
        order = entity_order(c, 'Cảng vụ', MEAS)
        with ui.card(f'{MEAS_LABEL} theo {FREQ.lower()}', unit='theo cảng vụ', key=f'{K}_series', periods=PER, default='2Y', end=LAST,
                     help='Mỗi đường = 1 cảng vụ (7 lớn nhất + Khác). Kỳ đang chạy = lũy kế tới ngày dữ liệu cuối (nét đứt).') as cd:
            w = wide(by_period(c, cd.d0, cd.d1), 'Cảng vụ', order)
            cd.chart(with_yoy(ui.fig_line(w, unit=MEAS_LABEL, zero=True, hover_nd=0), c, w), w, last=LAST, ten='theo_cang_vu',
                     note_text='Các bến Cái Mép – Thị Vải chỉ có trong dữ liệu TP.HCM từ 07–08/2025 nên chuỗi TP.HCM tăng bậc ở mốc này.')
        with ui.card('Tỷ trọng từng cảng vụ', unit='% cả nước', key=f'{K}_share', periods=PER, default='2Y', end=LAST) as cd:
            d = by_period(c, cd.d0, cd.d1); w = wide(d, 'Cảng vụ', order, share_of=d)
            cd.chart(ui.fig_stack(w.fillna(0), unit='%', area=True), w.round(1), last=LAST, ten='ty_trong_cang_vu', height=340)
        with ui.card('Bảng số liệu theo cảng vụ', unit=MEAS_LABEL, key=f'{K}_tbl', periods=PER, default='1Y', end=LAST) as cd:
            d = by_period(c, cd.d0, cd.d1)
            piv = d.pivot_table(index='Cảng vụ', columns='ky', values=MEAS, aggfunc='sum', fill_value=0)
            piv.columns = [k.strftime('%m/%Y' if FREQ == 'Tháng' else '%d/%m/%y') for k in piv.columns]
            cd.table(piv.loc[[o for o in order if o in piv.index]], ten='bang_cang_vu', height=min(460, 40 + 36 * len(piv)))

    elif level == 'cang-vu':
        with ui.card(f'{MEAS_LABEL} theo {FREQ.lower()}', unit=f'theo bến · {tl.AUTH_LABEL[auth]}', key=f'{K}_series_{auth}', periods=PER, default='2Y', end=LAST,
                     chips=['Bến', 'Nhóm chủ bến', 'Mã CK'], chip_default='Bến', chip_label='Gộp theo',
                     help='Cột chồng = 7 mục lớn nhất + Khác. Không tính khu neo, bến phao neo chờ.') as cd:
            dim = {'Bến': 'terminal', 'Nhóm chủ bến': 'group', 'Mã CK': 'ticker'}[cd.chip]
            va = v[v[dim] != '']; order = entity_order(va, dim, MEAS)
            w = wide(by_period(va, cd.d0, cd.d1), dim, order)
            cd.chart(with_yoy(ui.fig_stack(w, unit=MEAS_LABEL), va, w), w, last=LAST, ten=f'{auth}_theo_{dim}')
        with ui.card(f'Thị phần trong tổng {tl.AUTH_LABEL[auth]}', unit='%', key=f'{K}_share_{auth}', periods=PER, default='2Y', end=LAST,
                     chips=['Bến', 'Nhóm chủ bến', 'Mã CK'], chip_default='Bến', chip_label='Gộp theo') as cd:
            dim = {'Bến': 'terminal', 'Nhóm chủ bến': 'group', 'Mã CK': 'ticker'}[cd.chip]
            va = v[v[dim] != '']; order = entity_order(va, dim, MEAS)
            d = by_period(va, cd.d0, cd.d1); w = wide(d, dim, order, n=8, share_of=by_period(v, cd.d0, cd.d1))
            cd.chart(ui.fig_line(w, unit='%', zero=True, hover_nd=1), w.round(1), last=LAST, ten=f'{auth}_thi_phan_{dim}',
                     note_text='Mẫu số là tổng lượt cập bến của cùng cảng vụ và cùng bộ lọc loại tàu.')
        with ui.card('Bảng số liệu theo bến', unit=MEAS_LABEL, key=f'{K}_tbl_{auth}', periods=PER, default='1Y', end=LAST) as cd:
            d = by_period(v, cd.d0, cd.d1)
            piv = d.pivot_table(index='terminal', columns='ky', values=MEAS, aggfunc='sum', fill_value=0)
            piv.columns = [k.strftime('%m/%Y' if FREQ == 'Tháng' else '%d/%m/%y') for k in piv.columns]
            order = entity_order(v, 'terminal', MEAS)
            cd.table(piv.loc[[o for o in order if o in piv.index]], ten=f'{auth}_bang_ben', height=min(460, 40 + 36 * len(piv)))

    else:
        va = V_ALL[V_ALL['auth'] == auth]
        with ui.card(f'{MEAS_LABEL} theo {FREQ.lower()}', unit=f'{term} · {tl.AUTH_LABEL[auth]}', key=f'{K}_series_{auth}_{term}', periods=PER, default='2Y', end=LAST,
                     toggles={'Xem': ['Giá trị', 'Thị phần']}) as cd:
            d = by_period(v, cd.d0, cd.d1).assign(Bến=term)
            if cd.toggle.get('Xem') == 'Thị phần':
                w = wide(d, 'Bến', [term], share_of=by_period(va, cd.d0, cd.d1))
                cd.chart(ui.fig_line(w, unit='% cảng vụ', zero=True, hover_nd=1), w.round(1), last=LAST, ten=f'{term}_thi_phan',
                         note_text=f'Thị phần của {term} trong tổng lượt cập bến {tl.AUTH_LABEL[auth]} (cùng bộ lọc loại tàu).')
            else:
                w = wide(d, 'Bến', [term])
                cd.chart(with_yoy(ui.fig_bars(w, unit=MEAS_LABEL, sign=False, hover_nd=0), v, w), w, last=LAST, ten=f'{term}_theo_ky')
        a, b = st.columns(2)
        last12 = v[(v['arr_day'] > LAST - pd.DateOffset(months=12)) & (v['arr_day'] <= LAST)]
        with a:
            with ui.card('Hãng tàu ghé nhiều nhất', unit='12 tháng gần nhất', key=f'{K}_ops_{auth}_{term}', controls=False) as cd:
                top = last12.groupby('operator')[MEAS].sum().sort_values(ascending=False).head(12)
                cd.chart(ui.fig_hbar(top, unit=MEAS_LABEL, sign=False, nd=0), top.rename(MEAS_LABEL).to_frame(), last=LAST, ten=f'{term}_hang')
        with b:
            with ui.card('Cỡ tàu bình quân', unit='TEU/lượt', key=f'{K}_size_{auth}_{term}', periods=PER, default='2Y', end=LAST, compact=True) as cd:
                d = by_period(v[v['teu'] > 0], cd.d0, cd.d1)
                sz = d.groupby('ky')['teu'].mean().to_frame('TEU/lượt'); sz.index = pd.DatetimeIndex(sz.index)
                cd.chart(ui.fig_line(sz, unit='TEU/lượt', hover_nd=0), sz.round(0), last=LAST, ten=f'{term}_co_tau')
        with ui.card('Lượt cập bến', unit=f'{term}', key=f'{K}_list_{auth}_{term}', periods=PER, default='6M', end=LAST) as cd:
            d = v[(v['arr_day'] >= pd.Timestamp(cd.d0)) & (v['arr_day'] <= pd.Timestamp(cd.d1))]
            cols = ['arr_day', 'ship', 'operator', 'teu', 'dwt', 'origin', 'destination', 'hours_in_port', 'vessel_class']
            cd.table(d.sort_values('arr_day', ascending=False)[cols].assign(arr_day=lambda x: x['arr_day'].dt.strftime('%Y-%m-%d')).reset_index(drop=True),
                     ten=f'luot_cap_ben_{term}', height=380)


# ================================================================ TRANG 2: HÃNG TÀU & TÀU
def ship_detail(key, name, K):
    master = get_master(VER, MST)
    if PRESENT:                                          # mọi chuyến của tàu trong các năm đã có (đủ lịch sử khi đã nạp 'Từ 2019')
        sc = calls[calls['ship_key'] == key]
    else:
        sc = tl.ship_calls(key)
    sc = sc.sort_values('date') if len(sc) else calls[calls['ship_key'] == key].sort_values('date')
    m = master[master['ship_key'] == key].iloc[0].to_dict() if (not master.empty and (master['ship_key'] == key).any()) else {}
    if not m.get('imo') and len(sc): m['imo'] = next((x for x in sc['imo'] if x), '')
    if not m.get('dwt') and len(sc): m['dwt'] = sc['dwt'].max()
    pat = get_lanes(*KEY)[1]; prow = pat[pat['ship_key'] == key] if len(pat) else pat
    ui.kpi_strip([('IMO', m.get('imo') or '–', '', 0), ('Loại tàu', tl.CLASS_LABEL.get(m.get('vessel_class', ''), m.get('vessel_class', '–')), '', 0),
                  ('Hãng khai thác', (m.get('operator') or '–')[:22], '', 0), ('TEU', fmt_int(m.get('teu')), '', 0),
                  ('DWT', fmt_int(m.get('dwt')), '', 0), ('Năm đóng', str(m.get('built') or '–')[:4], '', 0)])
    if len(prow): ui.note(f"Vòng tuyến hay chạy: <b>{prow.iloc[0]['route_pattern']}</b> · cảng ghé: {prow.iloc[0]['ports_called']}")
    if m.get('service'): ui.note(f"Tuyến dịch vụ (tra cứu): {m['service']}")
    svc, rot, ves = get_services(ed.stamp(), MST)
    ev, _ = svm.match_vessel(svm.vessel_index(ves), m.get('imo'), m.get('mmsi'), name, m.get('dwt')) if len(ves) else (None, None)
    if ev is not None:
        bits = [f"hãng khai thác <b>{svm.op_canon(ev.get('operator_name'))[0] or '–'}</b>", f"chủ tàu {ev.get('owner') or '–'}"]
        if len(rot) and pd.notna(ev.get('mmsi')) and (rot['mmsi'] == ev['mmsi']).any():
            rr = rot[rot['mmsi'] == ev['mmsi']].iloc[0]; sv_ = svc[svc['service_id'] == rr['service_id']]
            bits.append(f"dịch vụ <b>{rr['service_id']}</b>: {sv_['route'].iloc[0] if len(sv_) else rr['route']}"
                        + (f" ({int(sv_['n_vessels'].iloc[0])} tàu; {sv_['operators'].iloc[0]})" if len(sv_) and sv_['operators'].iloc[0] else ''))
        if ev.get('last_signal'):
            bits.append(f"AIS {str(ev.get('last_signal'))[:16]}: {ev.get('last_speed') or 0:.1f} hl/h → {ev.get('destination') or '–'}"
                        + (f", ETA {str(ev.get('last_eta'))[:10]}" if ev.get('last_eta') else ''))
        ui.note('EconDB: ' + ' · '.join(bits))
    b1, b2, _ = st.columns([1.3, 1.6, 4])
    if b1.button('🔎 Tra thông số tàu trực tuyến', key=f'{K}_lookup', help='IMO từ BalticShipping / VesselFinder, TEU và loại tàu từ Flexport Atlas'):
        with st.spinner('Đang tra…'):
            r = ld.lookup_vessel(key, name, dwt=m.get('dwt') if pd.notna(m.get('dwt')) else None, imo=str(m.get('imo') or ''))
        st.success(f"IMO {r['imo'] or '–'} · TEU {fmt_int(r['teu'])} · loại {r['vessel_class'] or '–'} · nguồn {r['source'] or 'không tìm thấy'}")
        st.cache_data.clear(); st.rerun()
    pk = sc[(sc['src'] == 'public-kh') & (sc['origin'] == '')] if len(sc) else sc
    if len(pk) and b2.button(f'🧭 Tra cảng trước / cảng kế ({min(len(pk), 25)} chuyến)', key=f'{K}_details', help='Gọi trang chi tiết chuyến của cảng vụ (public-kh)'):
        with st.spinner('Đang gọi trang chi tiết chuyến…'):
            n = sum(ld.fetch_details(a, g.sort_values('date', ascending=False)['call_id'].tolist(), 25) for a, g in pk.groupby('auth'))
        st.success(f'Đã tra {n} chuyến'); st.cache_data.clear(); st.rerun()

    with ui.card('Thời gian nằm cảng', unit='từng chuyến, theo bến', key=f'{K}_gantt', periods=['1M', '3M', '6M', '1Y', 'All'], default='3M', end=LAST) as cd:
        w = sc[(sc['date'] >= pd.Timestamp(cd.d0)) & (sc['date'] <= pd.Timestamp(cd.d1) + pd.Timedelta(days=2))]
        g = w.dropna(subset=['arrival', 'departure'])
        if g.empty: cd.empty('Không có chuyến trọn vẹn (có cả giờ vào và giờ rời) trong khoảng ngày này.')
        else:
            exp = g[['auth', 'first_berth', 'arrival', 'departure', 'hours_in_port', 'origin', 'destination']].reset_index(drop=True)
            cd.chart(fig_gantt(g), exp, ten=f'nam_cang_{key}', last=g['departure'].max())
        # lộ trình trong cùng khung ngày
        vi = tl.itinerary_module()
        rec = lambda d: d.assign(arrival=d['arrival'].dt.strftime('%Y-%m-%d %H:%M').fillna(''), departure=d['departure'].dt.strftime('%Y-%m-%d %H:%M').fillna(''))[
            ['ship', 'ship_key', 'arrival', 'departure', 'origin', 'destination', 'berths', 'first_berth', 'status']].fillna('').to_dict('records')
        oth = w[~w['auth'].isin(['HP', 'HCM'])]
        try:                                              # 29/10/2026: + lượt ghé toàn cầu EconDB (đúng cảng ngoài, giờ, TEU xếp dỡ)
            econ = iti_econ(ed.stamp()).stops(m.get('mmsi'), m.get('imo'), pd.Timestamp(cd.d0).to_pydatetime(),
                                              (pd.Timestamp(cd.d1) + pd.Timedelta(days=2)).to_pydatetime())
        except Exception:  # noqa: BLE001
            econ = []
        stops = vi.stops_for_ship(rec(w[w['auth'] == 'HP']), rec(w[w['auth'] == 'HCM']), vi.Geo(),
                                  other_calls=rec(oth.assign(ship=oth['auth'])) if len(oth) else None, econ=econ)
        st.markdown('**Lộ trình trong khung ngày trên**')
        if not stops: ui.note('Không có điểm dừng trong khoảng ngày này.')
        else:
            dist = iti_dist(_pairs_mt()); legs = vi.legs_from_stops(stops, dist)
            nm = sum(l['nm'] or 0 for l in legs); n_e = sum(1 for x in stops if 'EconDB' in x['source'])
            ui.note(f'{len(stops)} điểm dừng ({n_e} có lượt ghé toàn cầu EconDB: đúng cảng, giờ đến/rời, TEU xếp dỡ), {len(legs)} chặng, '
                    f'khoảng {fmt_int(nm)} hải lý. Điểm có dấu ~ suy từ cảng đi/đến ghi ở Hải Phòng (mức quốc gia, gần đúng) - chỉ còn ở '
                    'khoảng thời gian EconDB chưa phủ.')
            srows = pd.DataFrame(vi.stop_rows({'ship_key': key, 'ship': name}, stops))[
                ['seq', 'port', 'precision', 'terminal', 'arrive', 'depart', 'hours_in_port', 'moves', 'inferred', 'source', 'raw_name']]
            for c_ in ('hours_in_port', 'moves'): srows[c_] = pd.to_numeric(srows[c_], errors='coerce')
            fig = fig_route_map(stops[-60:], dist)
            if fig is not None: st.plotly_chart(fig, width='stretch', config={'displayModeBar': False}, key=f'{K}_map')
            st.dataframe(srows, width='stretch', hide_index=True, height=300); dl_row(srows, f'lo_trinh_{ui.slug(key)}', f'{K}_stops')
    with ui.card('Toàn bộ chuyến của tàu', unit='mọi cảng vụ, mọi thời gian', key=f'{K}_allcalls', controls=False) as cd:
        cols = ['auth', 'arrival', 'departure', 'origin', 'first_berth', 'berths', 'destination', 'hours_in_port', 'status', 'agent']
        cd.table(sc.sort_values('date', ascending=False)[cols].reset_index(drop=True), ten=f'chuyen_{key}', height=380)


def page_operators(level, auth, term, K):
    c, v = scoped(level, auth, term)
    if v.empty: ui.card_empty('Hãng tàu', note_text='Không có dữ liệu trong phạm vi này.'); return
    ui.h2(f'Hãng tàu · {scope_name(level, auth, term)}')
    known = v[v['operator'] != '(chưa rõ hãng)']
    l12 = known[(known['arr_day'] > LAST - pd.DateOffset(months=12)) & (known['arr_day'] <= LAST)].copy()
    covr = 1 - (v.loc[v['arr_day'] > LAST - pd.DateOffset(months=12), 'operator'] == '(chưa rõ hãng)').mean() if len(v) else 0
    ui.note(f'Độ phủ: {covr:.0%} lượt cập bến 12 tháng gần nhất đã xác định được hãng khai thác. Phần còn lại tra bằng skill /cvhp-vessels.')
    col = {'toan-quoc': 'Cảng vụ', 'cang-vu': 'terminal', 'cang': None}[level]
    if col:
        with ui.card(f'Hãng × {"cảng vụ" if level == "toan-quoc" else "bến"}', unit=f'12 tháng gần nhất · {MEAS_LABEL}', key=f'{K}_heat', controls=False) as cd:
            l12['ben'] = l12[col]
            ops = l12.groupby('operator')[MEAS].sum().sort_values(ascending=False).head(15).index.tolist()
            bens = l12[l12['operator'].isin(ops)].groupby('ben')[MEAS].sum().sort_values(ascending=False).head(14).index.tolist()
            hm = l12[l12['operator'].isin(ops) & l12['ben'].isin(bens)].groupby(['operator', 'ben'], as_index=False)[MEAS].sum()
            if hm.empty: cd.empty()
            else:
                piv = hm.pivot(index='operator', columns='ben', values=MEAS).reindex(index=ops, columns=bens).fillna(0)
                cd.chart(fig_heat(hm, bens, ops, 'cảng vụ' if level == 'toan-quoc' else 'bến'), piv, last=LAST, ten='hang_x_ben')
    else:
        a, b = st.columns(2)
        with a:
            with ui.card('Hãng ghé nhiều nhất', unit='12 tháng gần nhất', key=f'{K}_top', controls=False) as cd:
                top = l12.groupby('operator')[MEAS].sum().sort_values(ascending=False).head(12)
                cd.chart(ui.fig_hbar(top, unit=MEAS_LABEL, sign=False, nd=0), top.rename(MEAS_LABEL).to_frame(), last=LAST, ten=f'{term}_top_hang')
        with b:
            with ui.card('Hãng theo kỳ', unit=f'{MEAS_LABEL} · 6 hãng lớn nhất + Khác', key=f'{K}_opseries', periods=PER, default='2Y', end=LAST, compact=True) as cd:
                order = entity_order(known, 'operator', MEAS); w = wide(by_period(known, cd.d0, cd.d1), 'operator', order, n=6)
                cd.chart(with_yoy(ui.fig_stack(w, unit=MEAS_LABEL), known, w), w, last=LAST, ten=f'{term}_hang_theo_ky')

    order_op = entity_order(known, 'operator', MEAS)
    if order_op:
        with ui.card('Chi tiết một hãng', unit='phân bổ + đội tàu đang khai thác', key=f'{K}_opdetail', periods=PER, default='2Y', end=LAST) as cd:
            op = st.selectbox('Hãng', order_op, key=f'{K}_op_sel')
            allo = known[known['operator'] == op].copy()
            allo['ben'] = allo['Cảng vụ'] if level == 'toan-quoc' else (allo['terminal'] if level == 'cang-vu' else term)
            w = wide(by_period(allo, cd.d0, cd.d1), 'ben', entity_order(allo, 'ben', MEAS))
            cd.chart(with_yoy(ui.fig_stack(w, unit=MEAS_LABEL), allo, w), w, last=LAST, ten=f'{ui.slug(op)}_theo_ben')
            f12 = allo[(allo['arr_day'] > LAST - pd.DateOffset(months=12)) & (allo['arr_day'] <= LAST)]
            pat = get_lanes(*KEY)[1]
            fl = (f12.groupby(['ship_key', 'ship'], as_index=False)
                  .agg(luot=('calls', 'sum'), teu=('teu', 'max'), dwt=('dwt', 'max'), ben_chinh=('ben', lambda s: s.value_counts().index[0]), lan_cuoi=('arr_day', 'max'))
                  .sort_values('luot', ascending=False))
            if not pat.empty: fl = fl.merge(pat[['ship_key', 'route_pattern']], on='ship_key', how='left')
            fl['lan_cuoi'] = fl['lan_cuoi'].dt.strftime('%Y-%m-%d')
            st.markdown(f'**Đội tàu {op} ghé {scope_name(level, auth, term)}, 12 tháng gần nhất** ({len(fl)} tàu)')
            fl = fl.drop(columns=['ship_key']).rename(columns={'ship': 'Tàu', 'luot': 'Lượt cập bến', 'teu': 'TEU', 'dwt': 'DWT', 'ben_chinh': 'Bến chính',
                                                               'lan_cuoi': 'Lần ghé cuối', 'route_pattern': 'Vòng tuyến hay chạy'})
            st.dataframe(fl, width='stretch', hide_index=True, height=min(400, 40 + 36 * len(fl))); dl_row(fl, f'doi_tau_{ui.slug(op)}', f'{K}_fleet')

    ui.h2(f'Tàu · {scope_name(level, auth, term)}')
    recent = c[c['date'] >= LAST - pd.DateOffset(months=36)].copy()
    recent['n12'] = (recent['date'] >= LAST - pd.DateOffset(months=12)).astype(int)
    cnt = (recent.groupby(['ship_key', 'ship']).agg(n=('n12', 'sum'), cont=('is_container', 'max')).reset_index()
           .sort_values(['cont', 'n'], ascending=[False, False]).drop_duplicates('ship_key'))
    names = dict(zip(cnt['ship_key'], cnt['ship'])); n12 = dict(zip(cnt['ship_key'], cnt['n']))
    key = st.selectbox(f'Chọn tàu đã ghé {scope_name(level, auth, term)} trong 36 tháng ({len(cnt)} tàu; gõ để tìm)', cnt['ship_key'].tolist(),
                       index=None, placeholder='— chọn tàu —', format_func=lambda k: f'{names.get(k, k)} ({n12.get(k, 0)} chuyến 12 tháng)', key=f'{K}_ship')
    if key: ship_detail(key, names.get(key, key), f'{K}_{ui.slug(key)[:20]}')


# ================================================================ TRANG 3: ĐIỀU ĐỘ & CẢNH BÁO
def page_ops(level, auth, term, K):
    c, v = scoped(level, auth, term)
    ui.h2(f'Bảng điều độ · {scope_name(level, auth, term)}')
    days = [(TODAY + pd.Timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, -8, -1)]
    c1, c2 = st.columns([1, 4])
    day = c1.selectbox('Ngày kế hoạch', days, index=1, key='dd_day', format_func=lambda d: pd.Timestamp(d).strftime('%d/%m/%Y') + (' (hôm nay)' if d == TODAY.strftime('%Y-%m-%d') else ''))
    auths_pull = ALL_AUTHS if level == 'toan-quoc' else [auth]
    if LIVE: live_pull(auths_pull, day, day, min(TTL, 10), 0, f'Đang gọi kế hoạch ngày {day}')
    if PRESENT:
        er = _p_cached('events_recent', VER)
        e = er[(er['plan_date'] == str(day)[:10]) & er['auth'].isin(auths_pull)].drop(columns=['plan_date']) if len(er) else er
    else:
        e = tl.events_day(auths_pull, day)
    if ONLY_CONT and len(e): e = e[e['vessel_class'].isin(['container', 'container?'])]
    if level == 'cang' and len(e):
        t = term.upper(); e = e[(e['from'].str.upper().str.strip() == t) | (e['to'].str.upper().str.strip() == t)]
    if e.empty:
        ui.card_empty('Kế hoạch điều động', note_text='Các cảng vụ chưa công bố kế hoạch cho ngày này trong phạm vi đang xem.' +
                      ('' if LIVE else ' Bật "Kéo thêm từ trang nguồn" ở chip Kho dữ liệu để gọi thẳng cảng vụ.'))
    else:
        e['teu'] = pd.to_numeric(e['teu'], errors='coerce')
        c2.markdown(f'<div class="gn-note" style="margin-top:28px">Kéo lúc {str(pd.to_datetime(e["fetched_at"]).max())[:16]} · kế hoạch do cảng vụ công bố và bổ sung dần trong ngày.</div>', unsafe_allow_html=True)
        items = []
        for lab, sec in [('Tàu vào', 'Vao'), ('Tàu rời', 'Roi'), ('Di chuyển', 'DiChuyen')]:
            s = e[e['section'] == sec]; items.append((lab, fmt_int(len(s)), f'TEU {fmt_int(s["teu"].sum())} · DWT {fmt_int(s["dwt"].sum())}', 0))
        items.append(('TEU danh nghĩa vào', fmt_int(e.loc[e['section'] == 'Vao', 'teu'].sum()), f'{e["auth"].nunique()} cảng vụ có kế hoạch', 0))
        ui.kpi_strip(items)
        with ui.card('Kế hoạch điều động', unit=pd.Timestamp(day).strftime('%d/%m/%Y'), key=f'{K}_plan', controls=False) as cd:
            show = ['auth', 'time', 'ship', 'operator', 'teu', 'dwt', 'from', 'to', 'vessel_class', 'agent']
            tabs = st.tabs(['Tàu vào', 'Tàu rời', 'Di chuyển'])
            for tab, sec in zip(tabs, ['Vao', 'Roi', 'DiChuyen']):
                with tab:
                    d = e[e['section'] == sec].sort_values(['auth', 'time'])[[x for x in show if x in e]].reset_index(drop=True)
                    st.dataframe(d, width='stretch', hide_index=True, height=min(420, 40 + 36 * max(len(d), 1)))
            cd.export(e[[x for x in show + ['section'] if x in e]].reset_index(drop=True), ten=f'dieu_do_{day}')
    with ui.card('Tàu đang ở cảng', unit='đã vào trong 10 ngày, chưa thấy kế hoạch rời', key=f'{K}_inport', controls=False,
                 help='Tàu vừa rời nhưng trang cảng vụ chưa cập nhật vẫn có thể nằm trong danh sách.') as cd:
        ip = c[(c['status'] == 'no_departure') & (c['arrival'] >= TODAY - pd.Timedelta(days=10)) & (c['arrival'] <= TODAY + pd.Timedelta(days=1))]
        ip = ip.assign(ngay_o_cang=((pd.Timestamp.now() - ip['arrival']).dt.total_seconds() / 86400).round(1))
        cd.table(ip.sort_values('arrival', ascending=False)[['auth', 'ship', 'operator', 'teu', 'dwt', 'arrival', 'origin', 'berths', 'ngay_o_cang', 'agent']].reset_index(drop=True),
                 ten='tau_dang_o_cang', height=min(400, 40 + 36 * max(len(ip), 1)))

    ui.h2(f'Cảnh báo thay đổi · {scope_name(level, auth, term)}')
    win = int((st.segmented_control('Cửa sổ so sánh', ['14 ngày', '30 ngày', '60 ngày', '90 ngày'], default='30 ngày', key='cb_win') or '30 ngày').split()[0])
    va = v[v['arr_day'] <= LAST].copy(); va['ben'] = va['auth'] + ' · ' + va['terminal']
    v_auth = V_ALL[(V_ALL['auth'] == auth) & (V_ALL['arr_day'] <= LAST)].copy() if level == 'cang' else va
    end = LAST + pd.Timedelta(days=1); a0 = end - pd.Timedelta(days=win); b0 = a0 - pd.Timedelta(days=win)
    y1 = end - pd.Timedelta(days=365); y0 = y1 - pd.Timedelta(days=win)
    cur = va[(va['arr_day'] >= a0) & (va['arr_day'] < end)]

    with ui.card('1. Biến động theo bến', unit=f'{win} ngày gần nhất so với kỳ trước và cùng kỳ năm trước', key=f'{K}_cb1', controls=False) as cd:
        def agg(lo, hi, name): return va[(va['arr_day'] >= lo) & (va['arr_day'] < hi)].groupby('ben')[['calls', 'teu']].sum().add_suffix(name)
        mm = pd.concat([agg(a0, end, '_ky_nay'), agg(b0, a0, '_ky_truoc'), agg(y0, y1, '_nam_truoc')], axis=1).fillna(0)
        if level != 'cang': mm = mm[(mm['calls_ky_nay'] + mm['calls_ky_truoc']) >= 6]
        mm['teu_so_ky_truoc'] = (mm['teu_ky_nay'] / mm['teu_ky_truoc'].replace(0, np.nan) - 1) * 100
        mm['teu_so_nam_truoc'] = (mm['teu_ky_nay'] / mm['teu_nam_truoc'].replace(0, np.nan) - 1) * 100
        mm = mm.sort_values('teu_so_ky_truoc', key=lambda s: s.abs(), ascending=False)
        if mm.empty: cd.empty()
        else:
            show = mm[['calls_ky_nay', 'calls_ky_truoc', 'teu_ky_nay', 'teu_ky_truoc', 'teu_nam_truoc', 'teu_so_ky_truoc', 'teu_so_nam_truoc']].rename(columns={
                'calls_ky_nay': 'Lượt kỳ này', 'calls_ky_truoc': 'Lượt kỳ trước', 'teu_ky_nay': 'TEU kỳ này', 'teu_ky_truoc': 'TEU kỳ trước',
                'teu_nam_truoc': 'TEU năm trước', 'teu_so_ky_truoc': '% so kỳ trước', 'teu_so_nam_truoc': '% so năm trước'})
            show.index.name = 'Bến'
            cd.table(ui.style_pct(show, cols=['% so kỳ trước', '% so năm trước'], nd=1), ten='bien_dong_ben', height=min(420, 40 + 36 * len(show)), df_export=show.round(1))
    with ui.card('2. Tàu mới xuất hiện', unit=f'{win} ngày qua · chưa từng ghé phạm vi này (tính từ 2019)', key=f'{K}_cb2', controls=False,
                 help='Thường là dấu hiệu tuyến dịch vụ mới hoặc hãng thay tàu cỡ khác.') as cd:
        first = va.groupby('ship_key')['arr_day'].min()
        new = cur[cur['ship_key'].map(first) >= a0]
        nv = (new.groupby(['ship_key', 'ship', 'operator'], as_index=False)
              .agg(teu=('teu', 'max'), luot=('calls', 'sum'), ben=('ben', lambda s: ', '.join(s.value_counts().index[:3])), lan_dau=('arr_day', 'min')).sort_values('teu', ascending=False))
        nv['lan_dau'] = nv['lan_dau'].dt.strftime('%Y-%m-%d')
        cd.table(nv.drop(columns=['ship_key']).rename(columns={'ship': 'Tàu', 'operator': 'Hãng', 'teu': 'TEU', 'luot': 'Lượt', 'ben': 'Bến', 'lan_dau': 'Lần đầu'}).reset_index(drop=True),
                 ten='tau_moi', height=min(360, 40 + 36 * max(len(nv), 1)))
    with ui.card('3. Tàu ngừng ghé', unit=f'đều đặn 90 ngày trước đó (≥ 6 lượt), vắng trong {win} ngày qua', key=f'{K}_cb3', controls=False) as cd:
        prev = va[(va['arr_day'] >= a0 - pd.Timedelta(days=90)) & (va['arr_day'] < a0)]
        pv = prev.groupby(['ship_key', 'ship', 'operator'], as_index=False).agg(luot_90=('calls', 'sum'), teu=('teu', 'max'), ben=('ben', lambda s: s.value_counts().index[0]), lan_cuoi=('arr_day', 'max'))
        gone = pv[(pv['luot_90'] >= (3 if level == 'cang' else 6)) & (~pv['ship_key'].isin(cur['ship_key']))].sort_values('luot_90', ascending=False)
        gone['lan_cuoi'] = gone['lan_cuoi'].dt.strftime('%Y-%m-%d')
        cd.table(gone.drop(columns=['ship_key']).rename(columns={'ship': 'Tàu', 'operator': 'Hãng', 'luot_90': 'Lượt 90 ngày trước', 'teu': 'TEU', 'ben': 'Bến', 'lan_cuoi': 'Lần cuối'}).reset_index(drop=True),
                 ten='tau_ngung_ghe', height=min(360, 40 + 36 * max(len(gone), 1)))
    with ui.card('4. Tàu đổi bến chính', unit='bến container ghé nhiều nhất 60 ngày gần đây khác 180 ngày trước đó (tối thiểu 3 và 4 lượt)', key=f'{K}_cb4', controls=False) as cd:
        def main_berth(d):
            g = d.groupby(['auth', 'ship_key', 'terminal']).size().reset_index(name='n').sort_values('n', ascending=False)
            return g.drop_duplicates(['auth', 'ship_key']).set_index(['auth', 'ship_key'])
        nowb = main_berth(v_auth[(v_auth['arr_day'] >= end - pd.Timedelta(days=60)) & (v_auth['kind'] == 'container')])
        oldb = main_berth(v_auth[(v_auth['arr_day'] >= end - pd.Timedelta(days=240)) & (v_auth['arr_day'] < end - pd.Timedelta(days=60)) & (v_auth['kind'] == 'container')])
        sw = nowb.join(oldb, lsuffix='_moi', rsuffix='_cu', how='inner')
        sw = sw[(sw['terminal_moi'] != sw['terminal_cu']) & (sw['n_moi'] >= 3) & (sw['n_cu'] >= 4)].reset_index()
        if level == 'cang': sw = sw[(sw['terminal_moi'] == term) | (sw['terminal_cu'] == term)]
        info = v_auth.drop_duplicates('ship_key').set_index('ship_key')[['ship', 'operator', 'teu']]
        sw = sw.join(info, on='ship_key').sort_values('teu', ascending=False)
        cd.table(sw[['auth', 'ship', 'operator', 'teu', 'terminal_cu', 'n_cu', 'terminal_moi', 'n_moi']].rename(columns={
            'auth': 'Cảng vụ', 'ship': 'Tàu', 'operator': 'Hãng', 'teu': 'TEU', 'terminal_cu': 'Bến cũ', 'n_cu': 'Lượt cũ', 'terminal_moi': 'Bến mới', 'n_moi': 'Lượt mới'}).reset_index(drop=True),
                 ten='tau_doi_ben', height=min(360, 40 + 36 * max(len(sw), 1)))


# ================================================================ TRANG 4: TUYẾN
def svc_label(svc):
    """service_id -> nhãn ngắn 'S036 · KMTC · Ho Chi Minh – Hong Kong – … (+3)'"""
    out = {}
    for r in svc.itertuples():
        ports = [x for x in str(r.route).split(' – ') if x]
        rt = ' – '.join(ports[:4]) + (f' … (+{len(ports) - 4})' if len(ports) > 4 else '')
        nm = getattr(r, 'service_name', '') or ''
        out[r.service_id] = (f'{nm} · {r.operator or "chưa rõ hãng"} · {rt}' if nm else f'{r.service_id} (chưa có tên) · {r.operator or "chưa rõ hãng"} · {rt}')
    return out


def ship_service(mst, rot):
    """ship_key -> service_id qua IMO (rồi MMSI) với bảng vòng tuyến dựng CÙNG lượt với services.parquet (mã dịch vụ trong master do
    bước ghép tàu buổi sáng tính ở lượt khác, có thể lệch)"""
    if rot is None or rot.empty: return pd.Series(dtype=object)
    by_imo = rot.assign(k=pd.to_numeric(rot['imo'], errors='coerce')).query('k > 0').drop_duplicates('k').set_index('k')['service_id']
    by_mmsi = rot.assign(k=pd.to_numeric(rot['mmsi'], errors='coerce')).dropna(subset=['k']).drop_duplicates('k').set_index('k')['service_id']
    m = mst.drop_duplicates('ship_key').set_index('ship_key')
    s_ = pd.to_numeric(m['imo'], errors='coerce').map(by_imo)
    return s_.fillna(pd.to_numeric(m['mmsi'], errors='coerce').map(by_mmsi)).dropna()


def term_codes(level, auth, term):
    """mã bến EconDB (locode, mã) thuộc phạm vi đang xem"""
    out = []
    for a, lcs in ed.AUTH_LOCODES.items():
        if level != 'toan-quoc' and a != auth: continue
        for lc in lcs:
            for code, t in ed.TERMINAL_MAP.get(lc, {}).items():
                if level == 'cang' and nw.nfc(term) not in nw._members(t): continue
                out.append((lc, code))
    return out


def page_lanes(level, auth, term, K):
    """TUYẾN DỊCH VỤ (26/10/2026, PV2: thay luồng chặng): (1) lượt cập bến cảng vụ của tàu container gắn DỊCH VỤ của tàu (gom từ lượt ghé
    toàn cầu EconDB -> master.service_id), (2) truy ngược từ tàu, (3) tuyến dịch vụ CÓ TÊN của hãng theo bến (EconDB, top 8/bến + Others)."""
    ui.h2(f'Tuyến dịch vụ · {scope_name(level, auth, term)}')
    svc, rot, _ = get_services(ed.stamp(), MST)
    mst = get_master(VER, MST)
    v = scoped(level, auth, term)[1]; v = v[v['is_container'].astype(bool)]
    if svc.empty or v.empty:
        ui.card_empty('Tuyến dịch vụ', note_text='Chưa có dữ liệu dịch vụ (EconDB) hoặc lượt cập bến cho phạm vi này.'); return
    sid = ship_service(mst, rot)
    v = v.assign(service_id=v['ship_key'].map(sid), teu=pd.to_numeric(v['teu'], errors='coerce'))
    lab = svc_label(svc); si = svc.set_index('service_id')
    mcol = 'teu' if MEAS == 'teu' else 'calls'; mlab = 'TEU danh nghĩa ghé' if MEAS == 'teu' else 'Lượt cập bến'
    has = v['service_id'].notna()
    ui.note(f'Dịch vụ = nhóm tàu chạy cùng vòng cảng (vòng = các cảng tàu ghé trong 1 chu kỳ gần nhất, theo lượt ghé toàn cầu EconDB). Lượt cập bến cảng vụ của tàu tính cho dịch vụ hiện tại '
            f'của tàu. Đã ghép dịch vụ: {has.mean() * 100:.0f}% lượt, {v.loc[has, "teu"].sum() / max(v["teu"].sum(), 1) * 100:.0f}% TEU danh nghĩa '
            f'(còn lại chủ yếu tàu nội địa nhỏ/sà lan chưa có trong EconDB).')
    vs = v[has]

    def per(d0, d1): return vs[(vs['arr_day'] >= pd.Timestamp(d0)) & (vs['arr_day'] <= pd.Timestamp(d1))]

    def by_svc(d):
        return d.groupby('service_id').agg(calls=('call_id', 'size'), teu=('teu', 'sum'), ships=('ship_key', 'nunique'),
                                           last=('arr_day', 'max')).sort_values(mcol, ascending=False)

    def monthly(d, col):
        k = d['arr_day'].dt.to_period('M').dt.to_timestamp('M')
        g = d.groupby([k, col])['call_id'].size() if mcol == 'calls' else d.groupby([k, col])['teu'].sum()
        w = g.unstack(col).fillna(0); w.index = pd.DatetimeIndex(w.index); w.index.name = 'Tháng'
        return w

    order = by_svc(per(LAST - pd.DateOffset(years=1), LAST)).index.tolist() or by_svc(vs).index.tolist()
    a, b = st.columns([2, 3])
    with a:
        with ui.card('Dịch vụ ghé nhiều nhất', unit=mlab, key=f'{K}_svtop', periods=PER, default='1Y', end=LAST, compact=True) as cd:
            g = by_svc(per(cd.d0, cd.d1))[mcol].head(15)
            g.index = [lab.get(x, x) for x in g.index]
            cd.chart(ui.fig_hbar(g, unit=mlab, sign=False, nd=0), g.rename(mlab).to_frame(), last=LAST, ten='dich_vu_lon_nhat')
    with b:
        with ui.card('Dịch vụ theo tháng', unit=mlab, key=f'{K}_svser', periods=PER, default='2Y', end=LAST, compact=True) as cd:
            pick = st.multiselect('Dịch vụ theo dõi (tối đa 6)', order, default=order[:4], max_selections=6, key=f'{K}_svpick',
                                  format_func=lambda x: lab.get(x, x))
            d = per(cd.d0, cd.d1); d = d[d['service_id'].isin(pick)]
            if d.empty: cd.empty('Chưa chọn dịch vụ hoặc không có lượt ghé trong khoảng ngày này.')
            else:
                w = monthly(d, 'service_id'); w = w.reindex(columns=[x for x in pick if x in w.columns]); w.columns = [lab.get(x, x) for x in w.columns]
                cd.chart(ui.fig_line(w, unit=mlab, zero=True, hover_nd=0), w, last=LAST, ten='dich_vu_theo_thang')

    with ui.card(f'Các dịch vụ ghé {scope_name(level, auth, term)}', unit='trong khoảng ngày', key=f'{K}_svlist', periods=PER, default='1Y', end=LAST) as cd:
        d = per(cd.d0, cd.d1); g = by_svc(d)
        tb = d.groupby(['service_id', 'terminal']).size().reset_index(name='n').sort_values('n', ascending=False)
        terms = {k_: ', '.join(f'{t} ({n})' for t, n in zip(x['terminal'].head(4), x['n'].head(4))) for k_, x in tb.groupby('service_id')}
        t = g.join(si[[c for c in ('service_name', 'operator', 'operators', 'route', 'vn_ports', 'n_vessels') if c in si]], how='left')
        t['ben'] = t.index.map(terms)
        t = t.reset_index().rename(columns={'service_id': 'Mã', 'operator': 'Hãng chính', 'operators': 'Các hãng (số tàu)', 'route': 'Vòng cảng',
                                            'vn_ports': 'Cảng VN trên vòng', 'ben': 'Bến ghé (lượt)', 'n_vessels': 'Tàu trong dịch vụ',
                                            'ships': 'Tàu đã ghé', 'calls': 'Lượt cập bến', 'teu': 'TEU danh nghĩa', 'last': 'Lượt cuối'})
        t['Lượt cuối'] = pd.to_datetime(t['Lượt cuối']).dt.strftime('%d/%m/%Y')
        t['Tuyến dịch vụ'] = [n if isinstance(n, str) and n else f'{m} (chưa có tên)' for n, m in zip(t.get('service_name', pd.Series('', index=t.index)), t['Mã'])]
        cols = ['Tuyến dịch vụ', 'Hãng chính', 'Vòng cảng', 'Bến ghé (lượt)', 'Lượt cập bến', 'TEU danh nghĩa', 'Tàu đã ghé', 'Tàu trong dịch vụ',
                'Các hãng (số tàu)', 'Cảng VN trên vòng', 'Lượt cuối']
        cd.table(t[cols].round(0), ten='dich_vu_ghe', height=420)

    with ui.card('Chi tiết một dịch vụ', unit='vòng cảng · tàu · lượt ghé theo bến', key=f'{K}_svone', periods=PER, default='1Y', end=LAST) as cd:
        one = st.selectbox('Dịch vụ', order, key=f'{K}_svsel', format_func=lambda x: lab.get(x, x)) if order else None
        if one in si.index:
            r = si.loc[one]
            ui.note(f"<b>{lab.get(one, one).split(' · ')[0]}</b> · hãng chính <b>{r['operator'] or 'chưa rõ'}</b>" + (f" ({r['operators']})" if r['operators'] else '')
                    + f" · {int(r['n_vessels'])} tàu · vòng cảng: {r['route']}")
            rv = rot[rot['service_id'] == one].copy(); rv['imo_n'] = pd.to_numeric(rv['imo'], errors='coerce')
            mm = mst.assign(imo_n=pd.to_numeric(mst['imo'], errors='coerce')).dropna(subset=['imo_n'])
            mm = mm[mm['imo_n'] > 0].drop_duplicates('imo_n').set_index('imo_n')
            rv['ship_key'] = rv['imo_n'].map(mm['ship_key']); rv['Hãng'] = rv['imo_n'].map(mm['operator']); rv['TEU'] = rv['imo_n'].map(mm['teu'])
            vl = V_ALL[V_ALL['ship_key'].isin(rv['ship_key'].dropna())].sort_values('arr_day').groupby('ship_key').tail(1).set_index('ship_key')
            rv = rv.join(vl[['arr_day', 'auth', 'terminal']], on='ship_key')
            show = rv[['ship', 'Hãng', 'TEU', 'last_port', 'last_call', 'arr_day', 'auth', 'terminal']].rename(columns={
                'ship': 'Tàu', 'last_port': 'Cảng ghé cuối (toàn cầu)', 'last_call': 'Ngày', 'arr_day': 'Cập bến VN cuối', 'auth': 'Cảng vụ', 'terminal': 'Bến'})
            for c in ('Ngày', 'Cập bến VN cuối'): show[c] = pd.to_datetime(show[c]).dt.strftime('%d/%m/%Y')
            codes = [c_ for c_ in str(r.get('route_codes', '') or '').split(' ') if c_]
            if len(codes) >= 2:
                ec = iti_econ(ed.stamp()); names = str(r['route']).split(' – ')
                pts = []
                for i_, c_ in enumerate(codes):
                    p_, lo_, la_ = ec.port(c_.replace('_', ' '), names[i_] if i_ < len(names) else c_)
                    pts.append({'port': p_, 'lon': lo_, 'lat': la_})
                fig = fig_route_map(pts, iti_dist(_pairs_mt()), loop=True, height=440)
                if fig is not None: st.plotly_chart(fig, width='stretch', config={'displayModeBar': False}, key=f'{K}_svmap')
            cd.table(show.sort_values('Tàu').reset_index(drop=True), ten=f'tau_dich_vu_{one}', height=min(420, 60 + 36 * len(show)))
            d = per(cd.d0, cd.d1); d = d[d['service_id'] == one]
            if len(d):
                w = monthly(d, 'terminal')
                cd.chart(ui.fig_stack(w, unit=mlab), w, last=LAST, ten=f'dich_vu_{one}_theo_ben',
                         note_text='Lượt ghé của các tàu thuộc dịch vụ tại các bến trong phạm vi, theo tháng.')

    with ui.card('Truy theo tàu', unit='tàu → dịch vụ → lượt ghé toàn cầu và Việt Nam', key=f'{K}_svship', controls=False) as cd:
        cnt = v.groupby(['ship_key', 'ship']).size().sort_values(ascending=False).reset_index()
        nm = dict(zip(cnt['ship_key'], cnt['ship']))
        k = st.selectbox('Tàu (đã ghé phạm vi này, nhiều lượt trước)', cnt['ship_key'].tolist(), key=f'{K}_svshipsel', format_func=lambda x: nm.get(x, x))
        if k:
            m = mst[mst['ship_key'] == k].iloc[0].to_dict() if (mst['ship_key'] == k).any() else {}
            sv_ = sid.get(k, '') if isinstance(sid.get(k, ''), str) else ''
            ui.note(f"<b>{nm.get(k, k)}</b> · IMO {m.get('imo') or '–'} · hãng {m.get('operator') or '–'} · {fmt_int(m.get('teu'))} TEU · "
                    + (f"dịch vụ <b>{lab.get(sv_, sv_)}</b> — vòng cảng {si.loc[sv_, 'route']}" if sv_ in si.index
                       else 'chưa ghép được dịch vụ (tàu chưa có lượt ghé toàn cầu trong EconDB)'))
            pc = iti_econ(ed.stamp()).pc                       # bản dùng chung (cache_resource), không sao chép
            mm_ = pd.to_numeric(pd.Series([m.get('mmsi')]), errors='coerce').iloc[0]
            im_ = pd.to_numeric(pd.Series([m.get('imo')]), errors='coerce').iloc[0]
            g = pd.DataFrame()
            if len(pc) and (pd.notna(mm_) or (pd.notna(im_) and im_ > 0)):
                g = pc[(pc['mmsi'] == mm_) | ((pc['ship_imo'] == im_) if pd.notna(im_) and im_ > 0 else False)]
            c1, c2 = st.columns(2)
            with c1:
                st.markdown('**Lượt ghé toàn cầu (EconDB, 120 ngày)**')
                g = g[g['start'] >= LAST - pd.Timedelta(days=120)].sort_values('start', ascending=False) if len(g) else g
                if len(g):
                    st.dataframe(pd.DataFrame({'Đến': g['start'].dt.strftime('%d/%m/%Y'), 'Cảng': g['port_name'], 'Mã': g['locode'],
                                               'Dỡ (TEU)': g['import_count'], 'Xếp (TEU)': g['export_count']}), hide_index=True, height=360)
                else: st.caption('Không có lượt ghé toàn cầu của tàu này trong EconDB.')
            with c2:
                st.markdown('**Lượt cập bến tại Việt Nam (cảng vụ)**')
                h = V_ALL[V_ALL['ship_key'] == k].sort_values('arr_day', ascending=False).head(60)
                st.dataframe(pd.DataFrame({'Đến': h['arr_day'].dt.strftime('%d/%m/%Y'), 'Cảng vụ': h['auth'].map(lambda x: tl.AUTH_LABEL.get(x, x)),
                                           'Bến': h['terminal'], 'Giờ nằm bến': pd.to_numeric(h['hours_in_port'], errors='coerce').round(0)}),
                             hide_index=True, height=360)

    ts = get_term_services(ed.stamp())
    codes = term_codes(level, auth, term)
    if len(ts) and codes:
        x = ts[[(s_, c_) in set(codes) for s_, c_ in zip(ts['scope'], ts['terminal'])]]
        tname = {(lc, c): t for lc, mp in ed.TERMINAL_MAP.items() for c, t in mp.items()}
        with ui.card('Tuyến dịch vụ có tên của hãng (EconDB, theo bến)', unit='TEU thông qua', key=f'{K}_svnamed', periods=PER, default='1Y', end=LAST,
                     help='EconDB công bố sản lượng theo TÊN tuyến dịch vụ của hãng cho từng bến: chỉ 8 tuyến lớn nhất mỗi bến, phần còn lại gộp "Others".') as cd:
            y = x[(x['date'] >= pd.Timestamp(cd.d0)) & (x['date'] <= pd.Timestamp(cd.d1))]
            if y.empty: cd.empty('Chưa có số liệu tuyến dịch vụ theo bến trong khoảng ngày này.')
            else:
                y = y.assign(ben=[tname.get((s_, c_), c_) for s_, c_ in zip(y['scope'], y['terminal'])])
                named = y[y['service'] != 'Others']; tot = max(y['value'].sum(), 1)
                top = named.groupby('service')['value'].sum().sort_values(ascending=False)
                tab = named.pivot_table(index='service', columns='ben', values='value', aggfunc='sum').fillna(0)
                tab['Tổng'] = tab.sum(axis=1)
                cd.chart(ui.fig_hbar(top.head(15), unit='TEU', sign=False, nd=0), tab.sort_values('Tổng', ascending=False).round(0), last=LAST,
                         ten='tuyen_dich_vu_co_ten',
                         note_text=f'Tuyến có tên chiếm {named["value"].sum() / tot * 100:.0f}% sản lượng các bến trong phạm vi; "Others" (tuyến nhỏ hơn top 8 '
                                   f'mỗi bến) {(tot - named["value"].sum()) / tot * 100:.0f}%. Bảng tải về: tuyến × bến.')


# ================================================================ TRANG 5: DỮ LIỆU
def pull_block(auths_default, K):
    if PRESENT:                                          # bản dựng sẵn: pipeline kéo nguồn 2 lần/ngày, app không ghi kho
        ui.note(f'Dữ liệu do pipeline kéo từ trang cảng vụ 2 lần/ngày rồi dựng sẵn (lần gần nhất {PMETA["built_at"]}); app online không kéo nguồn.')
        return
    with ui.card('Kéo bù / kéo lại từ trang nguồn', unit='gọi thẳng trang cảng vụ theo khoảng ngày', key=f'{K}_pull', controls=False) as cd:
        f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
        ba = f1.multiselect('Cảng vụ', ALL_AUTHS, default=auths_default, format_func=lambda a: tl.AUTH_LABEL.get(a, a), key=f'{K}_pull_auths')
        bd0 = f2.date_input('Từ ngày', (TODAY - pd.Timedelta(days=30)).date(), key=f'{K}_bf0', format='DD/MM/YYYY')
        bd1 = f3.date_input('Đến ngày', TODAY.date(), key=f'{K}_bf1', format='DD/MM/YYYY')
        again = f4.checkbox('Kéo lại cả ngày đã có', value=False, key=f'{K}_again')
        miss = ld.plan(ba, bd0, bd1, ttl_min=0 if again else 10 ** 7) if ba else {}
        n_miss = sum(len(v) for v in miss.values())
        ui.note(f'{n_miss} trang cần gọi' + (' (khoảng ' + fmt_int(n_miss * 0.6 / max(len(miss), 1) / 60) + ' phút)' if n_miss > 100 else ''))
        if st.button('⬇️ Kéo từ nguồn', disabled=not n_miss, key=f'{K}_pull_btn', type='primary'):
            n, _, errs = live_pull(ba, bd0, bd1, 0 if again else 10 ** 7, 0, 'Đang kéo bù từ trang nguồn')
            st.success(f'Đã kéo {n} trang' + (f', {len(errs)} lỗi' if errs else ''))
            if errs: st.write(errs[:40])
            st.cache_data.clear(); st.rerun()


def page_data(level, auth, term, K):
    c, v = scoped(level, auth, term)
    ui.h2(f'Dữ liệu · {scope_name(level, auth, term)}')
    if level == 'toan-quoc':
        with ui.card('Kho của app theo cảng vụ', unit='ngày có trong kho, lần kéo gần nhất', key=f'{K}_cov', controls=False) as cd:
            cv2 = cov.copy(); cv2['Cảng vụ'] = cv2['auth'].map(tl.AUTH_LABEL); cv2['o'] = cv2['auth'].map({a: i for i, a in enumerate(tl.AUTH_ORDER)})
            cd.table(cv2.sort_values('o')[['Cảng vụ', 'tu_ngay', 'den_ngay', 'so_ngay', 'so_su_kien', 'keo_gan_nhat']].rename(columns={
                'tu_ngay': 'Từ ngày', 'den_ngay': 'Đến ngày', 'so_ngay': 'Số ngày', 'so_su_kien': 'Số sự kiện', 'keo_gan_nhat': 'Kéo gần nhất'}).reset_index(drop=True),
                ten='kho_theo_cang_vu', height=40 + 36 * len(cv2))
        pull_block(['HP'], K)
        master = get_master(VER, MST)
        cc = c[(c['arr_day'] > LAST - pd.DateOffset(months=12)) & c['is_container']]
        ui.kpi_strip([('Tàu trong bảng tham chiếu', fmt_int(len(master)), '', 0), ('Có IMO', fmt_int((master['imo'].fillna('').astype(str) != '').sum()), '', 0),
                      ('Chuyến container 12 tháng có TEU', f"{(pd.to_numeric(cc['teu'], errors='coerce') > 0).mean():.0%}" if len(cc) else '–', '', 0),
                      ('Chuyến container 12 tháng có hãng', f"{(cc['operator'] != '(chưa rõ hãng)').mean():.0%}" if len(cc) else '–', '', 0)])
        if not PRESENT:
            with st.expander('Khởi tạo lại kho từ lịch sử đã parse sẵn (chỉ dùng khi kho hỏng)'):
                if st.button('Nạp lịch sử có sẵn vào kho', key='seed_btn'):
                    with st.spinner('Đang nạp…'): n = ld.seed_from_local()
                    st.success(f'Đã nạp {fmt_int(n)} sự kiện'); st.cache_data.clear(); st.rerun()
    elif level == 'cang-vu':
        r = cov[cov['auth'] == auth]
        if len(r):
            r = r.iloc[0]
            ui.kpi_strip([('Từ ngày', str(r['tu_ngay']), '', 0), ('Đến ngày', str(r['den_ngay']), '', 0), ('Số ngày trong kho', fmt_int(r['so_ngay']), '', 0),
                          ('Số sự kiện', fmt_int(r['so_su_kien']), f'kéo gần nhất {r["keo_gan_nhat"]}', 0)])
        pull_block([auth], K)
    with ui.card('Tải dữ liệu', unit=('lượt cập bến' if level == 'cang' else 'chuyến tàu') + ' theo bộ lọc', key=f'{K}_dl', periods=PER, default='1Y', end=LAST) as cd:
        d = (v if level == 'cang' else c)
        d = d[(d['arr_day'] >= pd.Timestamp(cd.d0)) & (d['arr_day'] <= pd.Timestamp(cd.d1))].drop(columns=['is_container', 'calls'], errors='ignore')
        ui.note(f'{len(d):,} dòng'.replace(',', '.') + ' · bảng hiện 5.000 dòng mới nhất, nút tải lấy toàn bộ')
        cd.table(d.sort_values('arr_day', ascending=False).head(5000).reset_index(drop=True), ten='du_lieu_theo_bo_loc', height=420, df_export=d)


# ================================================================ TRANG 6: SẢN LƯỢNG - thực tế EconDB (container full / throughput terminal) + ước/dự báo hồi quy
@vcache(show_spinner=False, max_entries=2)
def get_econdb(stamp): return ed.load()


ED_PER = ['6M', '1Y', '2Y', '3Y', 'All']
ED_REGION = {'China': 'Trung Quốc', 'Korea & Japan': 'Hàn Quốc & Nhật Bản', 'North America East': 'Bờ Đông Bắc Mỹ', 'North America West': 'Bờ Tây Bắc Mỹ',
             'US GOM': 'Vịnh Mexico (Mỹ)', 'North West Europe': 'Tây Bắc Âu', 'West Mediterranean': 'Tây Địa Trung Hải', 'South east Asia': 'Đông Nam Á',
             'Southeast Asia': 'Đông Nam Á', 'Central America': 'Trung Mỹ', 'East South America': 'Đông Nam Mỹ', 'West Africa': 'Tây Phi', 'India': 'Ấn Độ',
             'Africa': 'Châu Phi', 'East Asia': 'Đông Á', 'Europe': 'Châu Âu', 'Latin America': 'Mỹ Latinh', 'Middle East': 'Trung Đông',
             'North America': 'Bắc Mỹ', 'South Asia': 'Nam Á'}
ED_NAME = {**ed.VN_PORTS, **ed.PEERS, **ed.PARTNERS, **ed.SERIES_VN, **ED_REGION, 'Unknown': 'Chưa rõ', 'Others': 'Khác'}


def ed_wide(s, metric, scopes=None, by='series', flow=True):
    """chuỗi EconDB -> bảng rộng kỳ × (series|scope). Chuỗi tuần: Độ phân giải 'Tháng' cộng tuần thành tháng (bỏ tháng đầu/cuối chưa trọn).
    flow=False (ngày nằm bãi): gộp nhiều cảng bằng bình quân."""
    d = s[s['metric'] == metric]
    if scopes is not None: d = d[d['scope'].isin(scopes)]
    d = d[d['date'] <= TODAY]                                   # sức chở theo tuyến có lịch tương lai
    if d.empty: return pd.DataFrame()
    w = d.pivot_table(index='date', columns=by, values='value', aggfunc='sum' if flow else 'mean').sort_index()
    weekly = len(w) > 2 and w.index.to_series().diff().median() <= pd.Timedelta(days=8)
    if weekly and FREQ == 'Tháng' and flow:
        # chia đều mỗi tuần cho 7 ngày rồi cộng theo tháng dương lịch (cộng theo thứ Hai thì tháng có 5 tuần nhảy vọt)
        first, last = w.index.min(), w.index.max()
        dd = (w / 7).reindex(pd.date_range(first, last + pd.Timedelta(days=6), freq='D')).ffill(limit=6)
        w = dd.groupby(tl.me(dd.index)).sum(min_count=1)
        if last + pd.Timedelta(days=6) < last + pd.offsets.MonthEnd(0): w = w.iloc[:-1]
        if first.day > 1: w = w.iloc[1:]
    elif weekly:
        w.index = w.index + pd.Timedelta(days=6)                 # EconDB ghi thứ Hai đầu tuần -> Chủ nhật cuối tuần
    else:
        w.index = tl.me(w.index)                                 # EconDB ghi 01 tháng -> cuối tháng
    w = w.rename(columns=lambda c: ED_NAME.get(c, c))
    w = w.T.groupby(level=0).sum(min_count=1).T if flow else w.T.groupby(level=0).mean().T   # gộp tên trùng (Transshipment/s)
    w.index = pd.DatetimeIndex(w.index); w.index.name = 'Kỳ'
    return w


def ed_top(w, n=7):
    """giữ n cột lớn nhất (theo 24 tháng gần nhất, thứ tự cố định để màu không đổi khi đổi kỳ) + Khác; 'Chưa rõ' để riêng ở cuối"""
    if w.empty: return w
    rec = w[w.index >= w.index.max() - pd.DateOffset(months=24)]
    order = [c for c in rec.sum().sort_values(ascending=False).index if c not in ('Khác', 'Chưa rõ')]
    keep = order[:n]; rest = [c for c in w.columns if c not in keep and c != 'Chưa rõ']
    out = w[keep].copy()
    if rest: out['Khác'] = w[rest].sum(axis=1, min_count=1)
    if 'Chưa rõ' in w: out['Chưa rõ'] = w['Chưa rõ']
    return out


def _norm(x): return ''.join(ch for ch in str(x).upper() if ch.isalnum())


# ---- mô hình ước/dự báo (nowcast.py)
def nc_capsi(auth):
    """mùa vụ SỨC CHỞ nhiều năm của cảng vụ (present/season_cap.parquet, pipeline dựng từ lịch tàu 2019+); chưa có file -> tính từ lượt đã nạp"""
    f = os.path.join(PRESENT_DIR, 'season_cap.parquet'); key = (auth, os.path.getmtime(f) if os.path.exists(f) else 0, LAST)
    cache = st.session_state.setdefault('_capsi', {})
    if key in cache: return cache[key]
    si = None
    if os.path.exists(f):
        d = pd.read_parquet(f); d = d[d['auth'] == auth]
        if len(d) == 12: si = d.set_index('thang')['si'].astype(float)
    if si is None:
        v = nc_visits(); si = nw.cap_season(nw.features(v if auth == 'VN' else v[v['auth'] == auth], LAST))
    cache[key] = si
    return si


def nc_visits():
    """luôn dùng lượt cập bến tàu container, không theo bộ lọc Loại tàu"""
    return visits[visits['is_container']]


def nc_auth(auth, E):
    """cấp cảng vụ = hồi quy RIÊNG từng cảng EconDB thuộc cảng vụ (biến = bến thuộc cảng, thực tế = container full cảng) rồi cộng"""
    lcs = ed.AUTH_LOCODES.get(auth)
    if not lcs or E['series'].empty: return None
    key = ('nc_auth', auth, KEY, ed.stamp())
    cache = st.session_state.setdefault('_nc', {})
    if key not in cache:
        v = nc_visits(); cache[key] = nw.fit_ports(v[v['auth'] == auth], E['series'], lcs, ed.terminal_port(auth), LAST)
    return cache[key]


def nc_matched(auth, E):
    """lượt tàu EconDB của các cảng thuộc cảng vụ, ghép với bến cảng vụ (tên tàu + giờ đến)"""
    lcs = ed.AUTH_LOCODES.get(auth); cl = E['calls']
    if not lcs or cl.empty: return None, None
    key = ('nc_match', auth, KEY, ed.stamp())
    cache = st.session_state.setdefault('_nc', {})
    if key not in cache:
        c = cl[cl['locode'].isin(lcs)]; v = nc_visits()
        cache[key] = (nw.match_calls(c, v[v['auth'] == auth]), c)
    return cache[key]


def nc_pooled(auth, E):
    """hệ số chung THEO NHÓM bến (nước sâu / sông lớn / sông nhỏ, nowcast.terminal_class) từ các bến có số công bố của cảng vụ;
    cảng vụ không có bến công bố thì gộp toàn quốc. Trả về ({nhóm: hệ số}, phạm vi)"""
    T = nw.load_targets()
    key = ('nc_pooled', auth, KEY, os.path.getmtime(nw.TARGETS) if os.path.exists(nw.TARGETS) else 0)
    cache = st.session_state.setdefault('_nc', {})
    if key in cache: return cache[key]
    v = nc_visits()

    def pairs(auths):
        out = []
        for a in auths:
            va = v[v['auth'] == a]
            for g in T.loc[T['auth'] == a, 'terminal'].drop_duplicates():
                members = [nw.nfc(x.strip()) for x in str(g).split('+')]
                f = nw.features(va[va['terminal'].map(nw.nfc).isin(members)], LAST)
                if len(f): out.append((f, nw.target_series(T, a, members[0])))
        return out
    pools = nw.pooled_by_class(pairs([auth])); scope = tl.AUTH_LABEL.get(auth, auth)
    if not pools.get('chung'):
        pools = nw.pooled_by_class(pairs(sorted(T['auth'].unique()))); scope = 'toàn quốc'
    cache[key] = (pools, scope)
    return cache[key]


def nc_term(auth, term, E, ra):
    """bến: thực tế = container full EconDB cảng × tỷ trọng bến (lượt EconDB ghép được). Đủ tháng -> hồi quy riêng (res);
    chưa đủ -> bảng phân bổ (view) = ước/dự báo cảng vụ × tỷ trọng TB 3 tháng gần nhất."""
    lcs = ed.AUTH_LOCODES.get(auth)
    if not lcs: return None
    force = st.session_state.get(f'nc_force_{auth}_{nw.nfc(term)}')          # PV2 chọn tay mô hình cho bến (chip "So sánh mô hình")
    force = force if force in nw.MODELS else None
    key = ('nc_term', auth, term, KEY, ed.stamp(), nw.MIN_TRAIN_TERM, os.path.getmtime(nw.TARGETS) if os.path.exists(nw.TARGETS) else 0, force,
           os.path.getmtime(nw.BLOCKS) if os.path.exists(nw.BLOCKS) else 0)
    cache = st.session_state.setdefault('_nc', {})
    if key in cache: return cache[key]
    v = nc_visits(); va = v[v['auth'] == auth]; ft = nw.features(va[va['terminal'].map(nw.nfc) == nw.nfc(term)], LAST)
    port = nw.econdb_monthly(E['series'], lcs)                    # mùa vụ cho dự báo bến lấy từ chuỗi cảng (mượt hơn)
    ts = nw.terminal_series(E['series'], lcs, ed.TERMINAL_MAP, term, TODAY)
    # 0) bến có số CÔNG BỐ (nowcast_targets.csv) -> ưu tiên: EconDB terminal chỉ đếm container có hàng, lệch dần so công bố
    T = nw.load_targets(); pub = nw.target_series(T, auth, term); grp = nw.target_group(T, auth, term)
    pools, pscope = nc_pooled(auth, E); cls = nw.terminal_class(ft)
    prior = (pools.get(cls) or pools.get('chung') or {}).get('coef')        # điểm tựa: hệ số nhóm cùng loại bến (cả 2 biến > 0)
    if len(pub) >= 7:
        members = [x.strip() for x in grp.split('+')]
        fg = ft if len(members) == 1 else nw.features(va[va['terminal'].map(nw.nfc).isin([nw.nfc(x) for x in members])], LAST)   # nhóm: biến gộp các bến
        mt = nw.own_min_train(fg, pub)                            # 7–8 tháng trùng (Cái Mép) vẫn tự hồi quy, backtest ít điểm
        res = nw.run(fg, pub, min_train=mt, seasonal_ref=nw.season_ref(T, auth), force=force, prior=prior, capsi=nc_capsi(auth),
                     blocks=nw.block_list(nw.load_blocks(), auth, grp, pub)) if mt else None
        if res is not None:
            if len(members) > 1 and len(ts): ts = nw.terminal_series(E['series'], lcs, ed.TERMINAL_MAP, members[0], TODAY)
            for x in members[1:]: ts = ts.add(nw.terminal_series(E['series'], lcs, ed.TERMINAL_MAP, x, TODAY), fill_value=0) if len(members) > 1 else ts
            cache[key] = {'res': res, 'group': grp if len(members) > 1 else None, 'econ': ts,
                          'src': f'số công bố {"gộp " + " + ".join(members) + " " if len(members) > 1 else ""}({pub.index.min():%m/%Y}–{pub.index.max():%m/%Y}); '
                                 f'ước/dự báo: hồi quy riêng của bến, 2 biến ({res["n_train"]} tháng trùng dữ liệu cảng vụ; TEU = '
                                 + ' + '.join(f'{v:,.2f} × {"giờ bến" if c == "hours" else "sức chở"}' for c, v in res['coef'].items())
                                 + (f'; kéo về hệ số nhóm {cls} {nw.PRIOR_K:.0f} tháng tương đương)' if prior else ')')}
            return cache[key]
    # 0b) bến KHÔNG có / thiếu số công bố -> HỆ SỐ CHUNG rút từ các bến đã có số công bố (cùng cảng vụ, không đủ thì toàn quốc)
    pooled = pools.get(cls) or pools.get('chung')
    if pooled is not None:
        res = nw.apply_pooled(ft, pooled, pub if len(pub) else None, port, capsi=nc_capsi(auth))
        if res is not None:
            cache[key] = {'res': res, 'econ': ts, 'cls': cls,
                          'src': (f'số công bố ({pub.index.min():%m/%Y}–{pub.index.max():%m/%Y}); ' if len(pub) else 'chưa có số công bố; ')
                          + f'ước/dự báo: hệ số nhóm "{pooled["label"]}" ({pooled["n_terms"]} bến công bố {pscope}; bến này xếp nhóm {cls}: {nw.CLASS_RULES[cls]}; '
                          + ' · '.join(f'{c} × {v:.2f}' for c, v in pooled['coef'].items()) + ')'}
            return cache[key]
    # 1) bến có mã terminal EconDB (TERMINAL_MAP) -> throughput từng terminal từ 2022 -> TỰ hồi quy cho chính nó
    if len(ts):
        res = nw.run(ft, ts, min_train=nw.MIN_TRAIN_TERM, seasonal_ref=port, force=force, prior=None, capsi=nc_capsi(auth))
        if res is not None:
            codes = ', '.join(k for lc in lcs for k, t in ed.TERMINAL_MAP.get(lc, {}).items() if nw.nfc(term) in nw._members(t))
            cache[key] = {'res': res, 'src': f'throughput terminal EconDB ({codes})'}
            return cache[key]
    # 2) bến không có mã terminal EconDB (hoặc chưa đủ tháng): tỷ trọng từ lượt tàu EconDB ghép được với bến
    matched, c = nc_matched(auth, E)
    if matched is None or matched.empty: return None
    port = nw.econdb_monthly(E['series'], lcs)
    act, sh = nw.terminal_actual(port, matched, term, c)
    res = nw.run(ft, act, min_train=nw.MIN_TRAIN_TERM, seasonal_ref=port, force=force, capsi=nc_capsi(auth)) if len(act) >= nw.MIN_TRAIN_TERM + 3 else None
    view = None
    if res is None and ra is not None:
        d = ra['data']; full_sh = sh[sh.index.isin(act.index)]
        sh_avg = full_sh.iloc[-3:].mean() if len(full_sh) else np.nan
        est_rows = d[d['actual'].isna()]
        view = pd.concat([
            pd.DataFrame({'actual': act, 'kind': 'thực tế', 'port': port.reindex(act.index), 'share': full_sh}),
            pd.DataFrame({'actual': np.nan, 'kind': est_rows['kind'], 'port': est_rows['est'], 'share': sh_avg,
                          'est': est_rows['est'] * sh_avg, 'lo': est_rows['lo'] * sh_avg, 'hi': est_rows['hi'] * sh_avg}, index=est_rows.index)])
        view['backtest'] = np.nan; view.index.name = 'Tháng'
    out = {'res': res, 'view': view, 'act': act, 'share': sh, 'match_rate': matched.attrs.get('match_rate', np.nan),
           'src': 'container full EconDB cảng × tỷ trọng container xếp dỡ của bến (lượt tàu EconDB)'}
    cache[key] = out
    return out


def fig_nowcast(d, bt_name, blocks=None):
    """PV2 16/10/2026: chart chỉ gồm số thực, nowcast, dự phóng (có khoảng) và mô hình fit - không đánh dấu riêng phân bổ / khối / backtest"""
    fig = go.Figure()
    a = d['actual']; W = 22 * 86400000                  # độ rộng cột cố định (ms): trace 1 điểm thì Plotly vẽ cột mảnh gần như vô hình
    fig.add_trace(go.Bar(x=d.index, y=a, name='Thực tế', marker_color=TOK['gray'], width=W, hovertemplate='%{y:,.0f}<extra>Thực tế</extra>'))
    for kind, lab, col in [('nowcast', 'Nowcast', TOK['orange']), ('nowcast (tháng đang chạy)', 'Nowcast (tháng đang chạy)', TOK['orange_light']),
                           ('dự báo tháng tới', 'Dự phóng', TOK['tan']), ('dự báo', 'Dự phóng', TOK['tan'])]:
        x = d[d['kind'] == kind]
        if x.empty: continue
        fig.add_trace(go.Bar(x=x.index, y=x['est'], name=lab, legendgroup=lab, showlegend=kind != 'dự báo' or not (d['kind'] == 'dự báo tháng tới').any(),
                             marker_color=col, width=W,
                             error_y=dict(type='data', symmetric=False, array=(x['hi'] - x['est']).values, arrayminus=(x['est'] - x['lo']).values,
                                          color=TOK['ink3'], thickness=1.2, width=4),
                             hovertemplate='%{y:,.0f}<extra>' + lab + '</extra>'))
    if 'modeled' in d:                                     # model fit (hệ số cuối) suốt lịch sử, như biểu đồ "Model Fit" của PV2
        f = d.loc[d['kind'] != 'nowcast (tháng đang chạy)', 'modeled'].dropna()      # tháng đang chạy mới vài ngày -> fit quy đổi nhiễu, không vẽ
        fig.add_trace(go.Scatter(x=f.index, y=f.values, name=f'Mô hình fit ({bt_name.split(":")[0]})' if bt_name else 'Mô hình fit', mode='lines+markers',
                                 line=dict(color=TOK['down'], width=2, dash='dash'), marker=dict(size=5), hovertemplate='%{y:,.0f}<extra>Mô hình fit</extra>'))
    fig.update_layout(height=380, barmode='overlay', bargap=0.25, yaxis=dict(title='TEU / tháng', rangemode='tozero'), meta='no_partial')
    return fig


def vn_total(E):
    """tổng các cảng vụ có EconDB = combine() các mô hình cảng vụ (thực tế + ước/dự báo cộng theo tháng)"""
    parts = {tl.AUTH_LABEL[a]: nc_auth(a, E) for a in ed.AUTH_LOCODES}
    return nw.combine(parts, f'tổng {sum(1 for p in parts.values() if p)} cảng vụ')


def terminal_rows(auth, E, ra):
    """1 dòng/bến có mã terminal EconDB thuộc cảng vụ, mỗi bến tự hồi quy (nc_term); sắp theo thực tế giảm dần"""
    s = E['series']; rows = []; seen = set()
    tser = s[(s['metric'] == 'term_throughput') & s['scope'].isin(ed.AUTH_LOCODES.get(auth, []))][['scope', 'series']].drop_duplicates()
    for lc, k in tser.itertuples(index=False):
        t = ed.TERMINAL_MAP.get(lc, {}).get(k)
        tt = nc_term(auth, nw._members(t)[0], E, ra) if t else None
        if not tt or tt.get('res') is None: continue
        label = tt.get('group') or nw._members(t)[0]          # bến công bố gộp (Chùa Vẽ + Tân Vũ) chỉ 1 dòng
        if label in seen: continue
        seen.add(label); rows.append({'Phạm vi': label.replace('+', ' + '), **nw.summary(tt['res'])})
    return sorted(rows, key=lambda r: -(r.get('TEU thực tế cuối') or 0))


def parts_note(res):
    """1 dòng mô tả các mô hình thành phần (từng cảng / cảng vụ)"""
    ps = res.get('parts') or {}
    if len(ps) <= 1: return ''
    return 'Hồi quy riêng: ' + '; '.join(f'{ed.VN_PORTS.get(k, k)} ({p["best"].split(":")[0]}, MAPE ' + f'{p["mape"][p["best"]]:.1f}%'.replace('.', ',') + ')'
                                          for k, p in ps.items()) + ' → cộng lại.'


# cảng vụ HCM chỉ có Cái Mép từ 08/2025 (số VPA trước đó đã gồm Cái Mép) -> tổng HCM và toàn quốc chỉ học từ 08/2025
PUB_COVER_FROM = {'VN': '2025-08-31', 'HCM': '2025-08-31'}


def nc_published_total(auth, name):
    """tổng có SỐ CÔNG BỐ (VPA): auth 'VN'/'TOÀN QUỐC' = cả nước, auth X/'__CANG_VU__' = cảng vụ X. Biến = mọi lượt tàu container
    của phạm vi (12 cảng vụ / cảng vụ X); hồi quy 2 biến kéo về điểm tựa của chính chuỗi (self_prior). None nếu < 7 tháng trùng."""
    T = nw.load_targets(); pub = nw.target_series(T, auth, name)
    if pub.empty: return None                                      # file số công bố chưa có dòng tổng (vd bản online chưa kéo file mới)
    pub_all = pub                                                  # cả T1–T7/2025 suy từ lũy kế cùng kỳ: làm mùa vụ + hiện như thực tế
    cut = PUB_COVER_FROM.get(auth)                                 # chỉ học từ tháng dữ liệu cảng vụ đã phủ đủ phạm vi VPA
    if cut: pub = pub[pd.DatetimeIndex(pub.index) >= pd.Timestamp(cut)]
    if len(pub) < 7: return None
    key = ('nc_pub', auth, name, KEY, os.path.getmtime(nw.TARGETS) if os.path.exists(nw.TARGETS) else 0,
           os.path.getmtime(nw.BLOCKS) if os.path.exists(nw.BLOCKS) else 0)
    cache = st.session_state.setdefault('_nc', {})
    if key not in cache:
        v = nc_visits(); v = v if auth == 'VN' else v[v['auth'] == auth]
        r = nc_split_cm(v, pub_all, cut, auth, name) if cut else None          # tách Cái Mép: phần còn lại học + fit được cả trước mốc cắt
        if r is None:
            f = nw.features(v, LAST); mt = nw.own_min_train(f, pub)
            r = nw.run(f, pub, min_train=mt, seasonal_ref=nw.season_ref(T, auth), prior=nw.self_prior(f, pub), capsi=nc_capsi(auth),
                       blocks=nw.block_list(nw.load_blocks(), auth, name, pub_all)) if mt else None
        cache[key] = None if r is None else {
            'd': r['data'], 'res': r,
            'src': ('VPA TỔNG CỘNG (mọi cảng container cả nước, gồm rỗng)' if auth == 'VN' else 'VPA, cộng các cảng thuộc cảng vụ')
                   + f' {pub_all.index.min():%m/%Y}–{pub_all.index.max():%m/%Y}',
            'note': r.get('split_note') or (f'Ước/dự báo: hồi quy 2 biến trên mọi lượt tàu container {"12 cảng vụ" if auth == "VN" else "của cảng vụ"} '
                    f'(TEU = ' + ' + '.join(f'{x:,.2f} × {"giờ bến" if c == "hours" else "sức chở"}' for c, x in r['coef'].items()) + ').')}
    return cache[key]


VIMAWA = os.path.join(tl.HUB, 'vimawa-sanluong', 'data', 'vimawa_sanluong.csv')


def vimawa_stamp(): return os.path.getmtime(VIMAWA) if os.path.exists(VIMAWA) else 0


@vcache(show_spinner=False, max_entries=2)
def vimawa_teu(stamp):
    """container toàn quốc (1000 TEU -> TEU) theo tháng từ biểu 28-T Cục Hàng hải: thuc_te (suy từ lũy kế) + uoc (cột tháng báo cáo)"""
    if not stamp: return pd.DataFrame()
    d = pd.read_csv(VIMAWA, usecols=['period', 'ky_loai', 'nhom', 'chieu', 'don_vi', 'thang_bao_cao', 'thang_thuc_te'])
    d = d[(d['ky_loai'] == 'thang') & (d['nhom'] == 'container') & (d['chieu'] == 'tong') & (d['don_vi'] == '1000 TEU')]
    d.index = pd.DatetimeIndex(tl.me(pd.to_datetime(d['period'] + '-01')))
    return pd.DataFrame({'thuc_te': d['thang_thuc_te'] * 1000, 'uoc': d['thang_bao_cao'] * 1000}).sort_index()


def vimawa_compare(d, vm, n=6):
    """bảng tháng: VPA thực tế + app (dự báo quá khứ = backtest ngoài mẫu, ước/dự báo hiện tại) + Cục HH (thực tế, ước lập ngày 15
    của MỌI kỳ, quy về phạm vi VPA). -> (bảng, tỷ lệ VPA/Cục HH, sai số từng nguồn trên tháng trùng)"""
    vpa = d['actual']; cuc = vm['thuc_te']; uoc = vm['uoc']
    both = pd.concat([vpa, cuc], axis=1, keys=['v', 'c']).dropna()
    both = both[both.index >= pd.Timestamp('2025-04-30')]           # Cục HH đổi phạm vi từ T4/2025
    ratio = float((both['v'] / both['c']).tail(n).median()) if len(both) else None
    bt = d['backtest'] if 'backtest' in d else pd.Series(dtype=float)
    est = d['est'].where(d['actual'].isna()) if 'est' in d else pd.Series(dtype=float)
    w = pd.DataFrame({'VPA thực tế → nowcast/dự báo app': vpa.combine_first(est),    # PV2 17/10: 1 đường liền
                      'App: dự báo quá khứ (backtest)': bt,
                      'Cục HH thực tế': cuc, 'Cục HH ước (lập ngày 15)': uoc})            # PV2 17/10: bỏ đường quy về phạm vi VPA
    w = w[w.index >= pd.Timestamp('2024-01-31')].dropna(how='all'); w.index.name = 'Tháng'

    def mape(a, b, since='2025-04-30'):
        x = pd.concat([a, b], axis=1, keys=['a', 'b']).dropna(); x = x[x.index >= pd.Timestamp(since)]
        return (float((x['b'] / x['a'] - 1).abs().mean() * 100), len(x)) if len(x) else (None, 0)
    err = {'cuc_uoc': mape(cuc, uoc), 'app_bt': mape(vpa, bt, '2000-01-01'),
           'cuc_uoc_vpa': mape(vpa, uoc * ratio) if ratio else (None, 0)}
    return w, ratio, err


CM_PORT = 'VN VUT'                                                 # Cái Mép - Thị Vải: lịch cảng vụ chỉ có từ 08/2025


def _coef_txt(r):
    return ' + '.join(f'{x:,.2f} × {"giờ bến" if c == "hours" else "sức chở"}' for c, x in r['coef'].items())


def _window_sum(T, B, auth, terms, W):
    """tổng chính xác của các bến 'terms' trên các tháng W (số tháng + khối nằm gọn trong W); None nếu có tháng không phủ"""
    tot = 0.0; W = pd.DatetimeIndex(W)
    for t in terms:
        s = nw.target_series(T, auth, t); cov = set(s.index.intersection(W)); tot += float(s.reindex(sorted(cov)).sum())
        for ms, x in nw.block_list(B, auth, t, s):
            if pd.DatetimeIndex(ms).isin(W).all() and not cov & set(ms): tot += x; cov |= set(ms)
        if cov != set(W): return None
    return tot


def nc_split_cm(v, pub, cut, auth=None, name=None):
    """tổng có số công bố (toàn quốc / TP.HCM) = mô hình NGOÀI Cái Mép (lịch cảng vụ đủ từ đầu -> học + fit cả 2025)
    + mô hình Cái Mép (học từ mốc cắt). Trước mốc cắt phần Cái Mép = số VPA thực tế (đã biết) để có đường fit tổng;
    MAPE tổng chỉ tính trên tháng cả 2 phần đều có backtest thật. None nếu không tách được."""
    T = nw.load_targets(); tp = ed.terminal_port('HCM')
    cm_terms = sorted({t for t in T.loc[T['auth'] == 'HCM', 'terminal'] if t != '__CANG_VU__' and tp(t) == CM_PORT})
    if not cm_terms: return None
    B = nw.load_blocks(); ser = {}
    for t in cm_terms:                                  # bến Cái Mép chỉ có TỔNG nhiều tháng (Gemalink T8–T12/2025) -> chia theo lịch tàu của chính bến
        s_t = nw.target_series(T, 'HCM', t)
        ft = nw.features(v[(v['auth'] == 'HCM') & (v['terminal'].map(nw.nfc) == nw.nfc(t))], LAST)
        for W, tot in nw.block_list(B, 'HCM', t, s_t):
            W = pd.DatetimeIndex(W); g = ft.reindex(W)[['hours', 'teu']]
            e = nw.terminal_series(get_econdb(ed.stamp())['series'], ed.AUTH_LOCODES['HCM'], ed.TERMINAL_MAP, t, TODAY).reindex(W)
            if e.notna().all() and (e > 0).all():                  # PV2 16/10: chia theo tỷ lệ throughput terminal EconDB
                s_t = s_t.combine_first(tot * e / e.sum())
            elif g.notna().all().all() and (g > 0).all().all():    # không có EconDB -> lịch tàu cảng vụ của bến
                w = 0.5 * g['hours'] / g['hours'].sum() + 0.5 * g['teu'] / g['teu'].sum()
                s_t = s_t.combine_first(tot * w)
        ser[t] = s_t
    cm_act = pd.concat(list(ser.values()), axis=1).sum(axis=1, min_count=len(cm_terms)).dropna()
    rest_act = (pub - cm_act.reindex(pub.index)).dropna()
    is_cm = (v['auth'] == 'HCM') & (v['terminal'].map(tp) == CM_PORT)
    f_rest, f_cm = nw.features(v[~is_cm], LAST), nw.features(v[is_cm], LAST)
    cm_fit = cm_act[cm_act.index >= pd.Timestamp(cut)]
    mt_r, mt_c = nw.own_min_train(f_rest, rest_act), nw.own_min_train(f_cm, cm_fit)
    if not (mt_r and mt_c): return None
    b_rest, b_cm = [], []
    wins = [W for t in cm_terms for W, _ in nw.block_list(B, 'HCM', t, ser[t])]          # khối Cái Mép chưa chia được (thiếu lịch tàu)
    for W in wins:                                                  # tổng có số tháng trên khoảng khối Cái Mép -> phần còn lại = tổng − Cái Mép
        W = pd.DatetimeIndex(W)
        if not W.isin(pub.index).all() or not (W >= pd.Timestamp(cut)).all(): continue
        cm_w = _window_sum(T, B, 'HCM', cm_terms, W); tot = float(pub.reindex(W).sum())
        if cm_w is not None and 0 < cm_w < tot: b_cm.append((W, cm_w)); b_rest.append((W, tot - cm_w))
    for W, tot in (nw.block_list(B, auth, name, pub) if auth else []):           # khối tổng (vd T8–T12/2025) -> chia 2 phần chính xác
        cm_w = _window_sum(T, B, 'HCM', cm_terms, W)
        if cm_w is not None and 0 < cm_w < tot: b_cm.append((W, cm_w)); b_rest.append((W, tot - cm_w))
    sref = nw.season_ref(T, 'HCM')                                  # mùa vụ: chuỗi VPA cảng vụ (không lấy chuỗi riêng từng phần)
    csi = nc_capsi('HCM')
    r_rest = nw.run(f_rest, rest_act, min_train=mt_r, seasonal_ref=sref, prior=nw.self_prior(f_rest, rest_act), blocks=b_rest, capsi=csi)
    r_cm = nw.run(f_cm, cm_fit, min_train=mt_c, seasonal_ref=sref, prior=nw.self_prior(f_cm, cm_fit), blocks=b_cm, capsi=csi)
    if r_rest is None or r_cm is None: return None
    # phần Cái Mép trước mốc cắt: thực tế VPA làm cả fit/backtest (chỉ để cộng ra đường tổng, không tính sai số)
    pre = [m for m in r_rest['data'].index if m not in r_cm['data'].index and m in cm_act.index]
    d_cm = r_cm['data']
    if pre:
        x = pd.DataFrame({c: cm_act.reindex(pre).values for c in ('actual', 'modeled', 'backtest')}, index=pd.DatetimeIndex(pre))
        x['kind'] = 'thực tế'; x['w'] = np.nan
        d_cm = pd.concat([x, d_cm]).sort_index()
    r = nw.combine({'Ngoài Cái Mép': r_rest, 'Cái Mép': {**r_cm, 'data': d_cm}}, 'tổng 2 mô hình')
    r['blocks'] = [{'months': W, 'total': tot, 'modeled': sum(b['modeled'] for rr in (r_rest, r_cm) for b in rr.get('blocks', [])
                                                               if set(b['months']) == set(W))} for W, tot in (nw.block_list(B, auth, name, pub) if auth else [])]
    d = r['data']; ok = (d.index >= pd.Timestamp(cut)) & d['actual'].notna() & d['backtest'].notna()
    m = d.loc[ok, ['actual', 'backtest']]; a = d['actual'].dropna(); naive = a.shift(1).reindex(m.index)
    mm = lambda y, yh: float(np.mean(np.abs(yh / y - 1)) * 100) if len(y) else np.nan  # noqa: E731
    r['mape'] = {r['best']: mm(m['actual'], m['backtest']), nw.NAIVE: mm(m['actual'], naive)}
    mr = m.tail(nw.RECENT_BT); r['mape_recent'] = {r['best']: mm(mr['actual'], mr['backtest']), nw.NAIVE: mm(mr['actual'], naive.reindex(mr.index))}
    r['n_bt'] = len(m)
    r['split_note'] = (f'Ước/dự báo = 2 mô hình hồi quy 2 biến cộng lại: ngoài Cái Mép (TEU = {_coef_txt(r_rest)}, học từ {rest_act.index.min():%m/%Y}, '
                       f'MAPE {r_rest["mape"][r_rest["best"]]:.1f}%) + Cái Mép (TEU = {_coef_txt(r_cm)}, học từ {cm_fit.index.min():%m/%Y} vì lịch cảng vụ '
                       f'Cái Mép bắt đầu 08/2025). Trước đó đường fit tổng = fit ngoài Cái Mép + Cái Mép thực tế VPA; MAPE tổng chỉ tính từ {pd.Timestamp(cut):%m/%Y}.'
                       + (f' Khối chỉ biết tổng ({len(b_rest)}) học làm quan sát gộp.' if b_rest else ''))
    return r


def alloc_block(auth, term, W, tot):
    """chia 1 khối VPA (chỉ biết tổng) của bến ra từng tháng: tỷ lệ throughput terminal EconDB, không có thì lịch tàu cảng vụ của bến"""
    W = pd.DatetimeIndex(W)
    lcs = ed.AUTH_LOCODES.get(auth)
    if lcs:
        parts = [nw.terminal_series(get_econdb(ed.stamp())['series'], lcs, ed.TERMINAL_MAP, x.strip(), TODAY) for x in term.split('+')]
        if all(len(p_) for p_ in parts):
            e = pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts)).reindex(W)
            if e.notna().all() and (e > 0).all(): return tot * e / e.sum(), 'throughput terminal EconDB'
    v = nc_visits(); members = [nw.nfc(x.strip()) for x in term.split('+')]
    g = nw.features(v[(v['auth'] == auth) & v['terminal'].map(nw.nfc).isin(members)], LAST).reindex(W)[['hours', 'teu']]
    if g.notna().all().all() and (g > 0).all().all():
        return tot * (0.5 * g['hours'] / g['hours'].sum() + 0.5 * g['teu'] / g['teu'].sum()), 'lịch tàu cảng vụ'
    return None, None


def add_term_alloc(m, auth, term, grp=None):
    """bến có khối VPA: thêm cột ước từng tháng (phân bổ từ tổng VPA) vào bảng mô hình - chỉ hiển thị, hồi quy vẫn học khối"""
    if not m or m.get('d') is None or m.get('res') is None: return m
    name = grp or term; T = nw.load_targets(); pub = nw.target_series(T, auth, name)
    d = m['d'].copy(); fits = m['res'].get('fits'); best = m['res'].get('best'); how_all = set(); rng = []
    fit = fits[best] if isinstance(fits, pd.DataFrame) and best in fits else None
    for W, tot in nw.block_list(nw.load_blocks(), auth, name, pub):
        a, how = alloc_block(auth, name, W, tot)
        if a is None: continue
        for mth, x in a.items():
            row = {'actual': x, 'kind': 'thực tế (phân bổ từ tổng VPA)'}
            if fit is not None and mth in fit.index: row['modeled'] = float(fit.loc[mth])
            if mth in d.index:
                for k_, v_ in row.items(): d.loc[mth, k_] = v_
            else: d = pd.concat([d, pd.DataFrame([row], index=pd.DatetimeIndex([mth]))])
        how_all.add(how); rng.append(f'{pd.DatetimeIndex(W).min():%m/%Y}–{pd.DatetimeIndex(W).max():%m/%Y} (tổng {tot:,.0f})')
    if not rng: return m
    d = d.sort_index(); d.index.name = 'Tháng'
    m = dict(m); m['d'] = d
    m['note'] = (m.get('note') or '') + (f' Tháng {", ".join(rng)}: VPA chỉ công bố tổng các tháng này, chia theo {" / ".join(sorted(how_all))}; '
                                         'mô hình học khối (tổng), không học từng tháng phân bổ.')
    return m


def mark_alloc(m, auth, name):
    """tháng số công bố có phần PHÂN BỔ (dòng tổng: bến chỉ có tổng năm chia theo lịch tàu) -> kind 'thực tế (gồm X% phân bổ)' + ghi chú"""
    if not m or m.get('d') is None: return m
    T = nw.load_targets()
    if 'ghi_chu' not in T: return m
    g = T[(T['auth'] == auth) & (T['terminal'] == name) & T['ghi_chu'].fillna('').astype(str).str.len().gt(0)].set_index('month')['ghi_chu']
    g = g[g.index.isin(m['d'].index)]
    if g.empty: return m
    d = m['d'].copy(); d.loc[g.index, 'kind'] = 'thực tế (' + g.astype(str) + ')'
    pct = g.astype(str).str.extract(r'(\d+)%')[0].astype(float)
    m = dict(m); m['d'] = d
    if pct.isna().all():                                           # bến: cả tháng là số phân bổ từ tổng VPA
        m['note'] = (m.get('note') or '') + (f' Tháng {", ".join(f"{x:%m/%Y}" for x in g.index)}: VPA chỉ công bố tổng nhiều tháng, '
                                             'chia theo throughput terminal EconDB (không có thì lịch tàu cảng vụ); mô hình dùng như số thật.')
        return m
    m['note'] = (m.get('note') or '') + (f' Tháng {g.index.min():%m/%Y}–{g.index.max():%m/%Y} : tổng tháng gồm {pct.min():.0f}–{pct.max():.0f}% '
                                         'phân bổ — bến VPA chỉ có tổng nhiều tháng được chia theo throughput terminal EconDB (không có thì lịch tàu cảng vụ); cộng các tháng vẫn đúng tổng VPA.')
    return m


VN_PARTS = ['HP', 'HCM', 'DNG', 'DNI']                            # cảng vụ có số VPA (cộng các cảng thành viên VPA thuộc cảng vụ)


def nc_vn_bottom_up():
    """TOÀN QUỐC = cộng mô hình từng cảng vụ có số VPA (HP, TP.HCM [ngoài Cái Mép + Cái Mép], Đà Nẵng, Đồng Nai)
    + 'cảng VPA khác' (TỔNG CỘNG − 4 cảng vụ: Bình Dương, Đồng Nai ICD, Quy Nhơn, Nghệ Tĩnh, miền Tây...) ước theo tỷ lệ so với tổng
    4 cảng vụ (TB 3 tháng có số trước đó -> backtest vẫn ngoài mẫu). Fit / nowcast / dự báo / backtest đều cộng từ thành phần."""
    T = nw.load_targets(); vn = nw.target_series(T, 'VN', 'TOÀN QUỐC')
    if vn.empty: return None
    parts = {a: nc_published_total(a, '__CANG_VU__') for a in VN_PARTS}
    parts = {a: p_ for a, p_ in parts.items() if p_ and p_.get('res') is not None}
    if len(parts) < 2: return None
    idx = None
    for p_ in parts.values(): idx = p_['res']['data'].index if idx is None else idx.intersection(p_['res']['data'].index)
    cols = ['actual', 'modeled', 'backtest', 'est', 'lo', 'hi']
    S = pd.DataFrame({c: pd.concat([p_['res']['data'].reindex(idx)[c] for p_ in parts.values()], axis=1).sum(axis=1, min_count=len(parts))
                      for c in cols}, index=idx)
    first = parts.get('HCM', next(iter(parts.values())))['res']['data'].reindex(idx)
    vn_ = vn.reindex(idx)
    r = ((vn_ - S['actual']) / S['actual']).where(S['actual'] > 0)          # tỷ lệ cảng VPA khác / tổng 4 cảng vụ
    r_prior = r.shift(1).rolling(3, min_periods=1).mean()                   # chỉ dùng các tháng TRƯỚC
    r_last = float(r.dropna().tail(3).mean()) if r.notna().any() else 0.0
    r_all = float(r.dropna().mean()) if r.notna().any() else 0.0
    d = pd.DataFrame(index=idx)
    d['actual'] = vn_
    d['modeled'] = S['modeled'] * (1 + r_all)
    d['backtest'] = S['backtest'] * (1 + r_prior)
    for c in ('est', 'lo', 'hi'): d[c] = S[c] * (1 + r_last)
    d['kind'] = first['kind']; d['w'] = first['w'] if 'w' in first else np.nan
    d.loc[d['actual'].notna(), 'kind'] = 'thực tế'
    d = d[d['actual'].notna() | d['est'].notna()]; d.index.name = 'Tháng'
    m = d[['actual', 'backtest']].dropna(); a = d['actual'].dropna(); naive = a.shift(1).reindex(m.index)
    mm = lambda y, yh: float(np.mean(np.abs(yh / y - 1)) * 100) if len(y) else np.nan  # noqa: E731
    lab = 'tổng các cảng vụ'
    mr = m.tail(nw.RECENT_BT)
    res = {'data': d, 'best': lab, 'mape': {lab: mm(m['actual'], m['backtest']), nw.NAIVE: mm(m['actual'], naive)},
           'mape_recent': {lab: mm(mr['actual'], mr['backtest']), nw.NAIVE: mm(mr['actual'], naive.reindex(mr.index))},
           'n_bt': len(m), 'n_train': min(p_['res'].get('n_train', 0) for p_ in parts.values()), 'cols': [], 'coef': {},
           'seasonal': float(np.mean([p_['res'].get('seasonal', 1.0) for p_ in parts.values()])),
           'parts': {tl.AUTH_LABEL.get(a, a): p_['res'] for a, p_ in parts.items()}}
    vn1 = lambda x: f'{x:.1f}'.replace('.', ',')  # noqa: E731
    pn = ', '.join(f"{tl.AUTH_LABEL.get(a, a)} (MAPE {vn1(p_['res']['mape'][p_['res']['best']])}%)" for a, p_ in parts.items())
    return {'d': d, 'res': res,
            'src': f'VPA TỔNG CỘNG (mọi cảng container cả nước, gồm rỗng) {vn.index.min():%m/%Y}–{vn.index.max():%m/%Y}',
            'note': f'Ước/dự báo = CỘNG mô hình từng cảng vụ (số VPA của các cảng thành viên): {pn} + cảng VPA khác '
                    f'(Bình Dương, Quy Nhơn, Nghệ Tĩnh, miền Tây...: {vn1(r_last * 100)}% tổng 4 cảng vụ, TB 3 tháng gần nhất).'}


def with_pub_history(m, auth, name):
    """thêm các tháng SỐ CÔNG BỐ chưa có trong bảng mô hình (vd T1–T7/2025 VPA suy từ lũy kế cùng kỳ, trước khi cảng vụ phủ Cái Mép)
    thành dòng thực tế: hiện trên biểu đồ/bảng, không đưa vào hồi quy"""
    if not m or m.get('d') is None or not len(m['d']): return m
    pub = nw.target_series(nw.load_targets(), auth, name)
    d = m['d']; la = d['actual'].last_valid_index()
    add = pub[~pd.DatetimeIndex(pub.index).isin(d.index)]
    if la is not None: add = add[add.index <= la]
    if add.empty: return m
    extra = pd.DataFrame({'actual': add.astype(float).values, 'kind': 'thực tế'}, index=pd.DatetimeIndex(add.index))
    d2 = pd.concat([extra, d]).sort_index(); d2.index.name = d.index.name
    m = dict(m); m['d'] = d2
    m['note'] = (m.get('note') or '') + (f' Tháng {add.index.min():%m/%Y}–{add.index.max():%m/%Y}: chỉ số công bố, '
                                         'không đưa vào hồi quy (lịch cảng vụ đã nạp chưa có hoặc chưa phủ đủ phạm vi).')
    return m


def vol_model(level, auth, term, E):
    """dict(d = bảng tháng actual/est/lo/hi/kind/backtest, res = kết quả hồi quy hoặc None, src, note)"""
    if level == 'toan-quoc':
        rv = nc_vn_bottom_up() or nc_published_total('VN', 'TOÀN QUỐC')   # 17/10 PV2: cộng mô hình các cảng vụ (thành viên VPA)
        if rv: return mark_alloc(with_pub_history(rv, 'VN', 'TOÀN QUỐC'), 'VN', 'TOÀN QUỐC')
        r = vn_total(E)
        if r is None: return None
        return {'d': r['data'], 'res': r, 'src': 'tổng container full EconDB của ' + ', '.join(tl.AUTH_LABEL[a] for a in ed.AUTH_LOCODES),
                'note': parts_note(r)}
    if level == 'cang-vu':
        rv = nc_published_total(auth, '__CANG_VU__')               # cộng các cảng VPA thuộc cảng vụ
        if rv: return mark_alloc(with_pub_history(rv, auth, '__CANG_VU__'), auth, '__CANG_VU__')
    ra = nc_auth(auth, E)
    if level == 'cang-vu':
        if ra is None: return None
        return {'d': ra['data'], 'res': ra, 'src': 'container full EconDB (' + ' + '.join(ed.VN_PORTS[x] for x in ed.AUTH_LOCODES[auth]) + ')',
                'note': parts_note(ra)}
    tt = nc_term(auth, term, E, ra)
    if not tt: return None
    if tt.get('res') is not None:
        m = {'d': tt['res']['data'], 'res': tt['res'], 'src': tt['src'], 'econ': tt.get('econ')}
        return mark_alloc(add_term_alloc(with_pub_history(m, auth, term), auth, term, tt.get('group')), auth, tt.get('group') or term)             if str(tt['src']).startswith('số công bố') else m
    if tt.get('view') is None or tt['act'].empty: return None
    return {'d': tt['view'], 'res': None, 'src': tt['src'], 'share': tt['share'],
            'note': f'Bến chưa có chuỗi terminal EconDB đủ dài → ước/dự báo = ước/dự báo cảng vụ × tỷ trọng TB 3 tháng '
                    f'(ghép được {tt["match_rate"] * 100:.0f}% lượt tàu EconDB).'}


def quarter_table(d):
    """bảng tháng -> quý: thực tế + ước/dự báo cho tháng chưa có thực tế; chỉ giữ quý đủ 3 tháng (thực tế hoặc ước)"""
    x = d[~d.index.duplicated(keep='last')].copy()
    x['uoc'] = x['est'].where(x['actual'].isna()); x['lo_u'] = x['lo'].where(x['actual'].isna()); x['hi_u'] = x['hi'].where(x['actual'].isna())
    x = x[x['actual'].notna() | x['uoc'].notna()]
    if x.empty: return pd.DataFrame()
    x['q'] = pd.DatetimeIndex(x.index).to_period('Q')
    q = x.groupby('q').agg(thuc_te=('actual', 'sum'), uoc=('uoc', 'sum'), lo_u=('lo_u', 'sum'), hi_u=('hi_u', 'sum'),
                           n_tt=('actual', 'count'), n_uoc=('uoc', 'count'),
                           pb=('kind', lambda k: int(k.astype(str).str.contains('phân bổ').sum())))
    q = q[(q['n_tt'] + q['n_uoc']) == 3]
    q['tong'] = q['thuc_te'] + q['uoc']; q['thap'] = q['thuc_te'] + q['lo_u']; q['cao'] = q['thuc_te'] + q['hi_u']
    q['tinh_trang'] = [('đủ 3 tháng thực tế' if u == 0 else f'{t} tháng thực tế + {u} ước/dự báo') + (f' ({p_} tháng gồm phân bổ)' if p_ else '')
                       for t, u, p_ in zip(q['n_tt'], q['n_uoc'], q['pb'])]
    prev = q['tong'].copy(); prev.index = prev.index + 4
    q['yoy'] = (q['tong'] / prev.reindex(q.index) - 1) * 100
    q.index = [f'Q{p_.quarter}/{p_.year}' for p_ in q.index]
    return q


def fig_quarter(q):
    fig = go.Figure()
    fig.add_trace(go.Bar(x=q.index, y=q['thuc_te'], name='Thực tế', marker_color=TOK['gray'], hovertemplate='%{y:,.0f}<extra>Thực tế</extra>'))
    u = q['uoc'].where(q['uoc'] > 0)
    fig.add_trace(go.Bar(x=q.index, y=u, name='Ước / dự báo', marker_color=TOK['orange'], customdata=q['tinh_trang'],
                         error_y=dict(type='data', symmetric=False, array=(q['cao'] - q['tong']).where(q['uoc'] > 0).values,
                                      arrayminus=(q['tong'] - q['thap']).where(q['uoc'] > 0).values, color=TOK['ink3'], thickness=1.2, width=5),
                         hovertemplate='%{y:,.0f}<br>%{customdata}<extra>Ước / dự báo</extra>'))
    fig.add_trace(go.Scatter(x=q.index, y=q['tong'], mode='text', text=[f'{v / 1e6:,.2f}tr' if v >= 1e6 else f'{v / 1e3:,.0f}k' for v in q['tong']],
                             textposition='top center', showlegend=False, hoverinfo='skip'))
    fig.update_layout(height=380, barmode='stack', bargap=0.35, yaxis=dict(title='TEU / quý', rangemode='tozero'), meta='no_partial')
    return fig


def vol_kpis(m, s, scopes):
    d = m['d']; res = m['res']; a = d['actual'].dropna()
    rng = lambda r: f"{fmt_int(r['lo'])} – {fmt_int(r['hi'])}"  # noqa: E731

    def yoy(k, v):
        ly = nw.ly(k)
        return v / d.loc[ly, 'actual'] - 1 if ly in d.index and pd.notna(d.loc[ly, 'actual']) and d.loc[ly, 'actual'] else None
    items = []
    if len(a):
        y = yoy(a.index[-1], a.iloc[-1])
        items.append((f'Thực tế T{a.index[-1]:%m/%Y}', fmt_int(a.iloc[-1]), f'{fmt_pct(y) or "–"} cùng kỳ', 0 if y is None else (1 if y >= 0 else -1)))
    pick = d[d['kind'].isin(['nowcast (tháng đang chạy)'])]
    if pick.empty: pick = d[d['actual'].isna()].iloc[:1]
    for k, r in pick.iterrows():
        y = yoy(k, r['est'])
        items.append((f'{"Dự báo" if r["kind"] == "dự báo tháng tới" else "Ước"} T{k:%m/%Y}', fmt_int(r['est']),
                      rng(r) + (f' · {fmt_pct(y)} cùng kỳ' if y is not None else ''), 0 if y is None else (1 if y >= 0 else -1)))
    qt = quarter_table(d)
    if len(qt):
        for qi, r in qt[qt['n_uoc'] > 0].tail(2).iterrows():          # quý chưa chốt (tối đa 2: quý trước còn ước + quý đang mở có dự báo)
            yq = r['yoy']; lab = 'Ước' if r['n_tt'] > 0 or qi != qt.index[-1] else 'Dự báo'
            items.append((f'{lab} {qi} (cả quý)', fmt_int(r['tong']),
                          f"{int(r['n_tt'])}T thực tế + {int(r['n_uoc'])}T ước/dự báo" + (f' · {fmt_pct(yq / 100)} cùng kỳ' if pd.notna(yq) else ''),
                          0 if pd.isna(yq) else (1 if yq >= 0 else -1)))
    if res:
        mm = res['mape']; b = res['best']
        mr = res.get('mape_recent') or {}; nv = mm.get(nw.NAIVE)
        if res.get('pooled'):
            items.append(('Sai số hệ số chung', f'{mm[b]:.1f}%'.replace('.', ','), 'trong mẫu gộp các bến công bố · chưa backtest riêng', 0))
        else:
            items.append(('Sai số mô hình (MAPE)', f'{mm[b]:.1f}%'.replace('.', ','),
                          (f'{b.split(":")[0]}' + (f' · 6 tháng gần {mr[b]:.1f}%' if b in mr else '') + (f' · naive {nv:.1f}%' if nv is not None else '')).replace('.', ','),
                          0 if nv is None else (1 if mm[b] < nv else -1)))
    dw = s[(s['metric'] == 'dwell') & s['scope'].isin(scopes) & (s['series'] == 'Imports')].groupby('date')['value'].mean().sort_index()
    if len(dw) >= 2 and len(items) < 5:
        dd = dw.iloc[-1] - dw.iloc[-2]
        items.append((f'Nằm bãi hàng nhập T{dw.index[-1]:%m}', f'{fmt_h(dw.iloc[-1])} ngày', f'{dd:+.1f} ngày so tháng trước'.replace('.', ','),
                      -1 if dd > 0 else 1))
    ui.kpi_strip(items)


VOL_CHIPS = {'toan-quoc': ['Thực tế & dự báo', 'Theo quý', 'Theo chiều', 'Theo cảng', 'XK theo nước', 'NK theo nước', 'So khu vực'],
             'cang-vu': ['Thực tế & dự báo', 'Theo quý', 'Theo chiều', 'Theo terminal', 'Theo hãng', 'XK theo đối tác', 'NK theo đối tác'],
             'cang': ['Thực tế & dự báo', 'Theo quý', 'Tỷ trọng trong cảng vụ']}
# chip -> (chỉ tiêu EconDB, cột tách, giữ top n, kỳ gần nhất thấp giả)
VOL_SPLIT = {'Theo chiều': ('traffic', 'series', None, False), 'Theo cảng': ('traffic', 'scope', None, False),
             'Theo terminal': ('term_throughput', 'series', 8, False), 'Theo hãng': ('cap_throughput', 'series', 7, False),
             'XK theo nước': ('p2p_export', 'series', 7, True), 'NK theo nước': ('p2p_import', 'series', 7, True),
             'XK theo đối tác': ('partner_export', 'series', None, True), 'NK theo đối tác': ('partner_import', 'series', None, True)}


def page_volume(level, auth, term, K):
    """TRANG SẢN LƯỢNG: thực tế EconDB + ước/dự báo hồi quy (nowcast.py) trong cùng 1 thẻ, tách theo chiều/cảng/terminal/hãng/đối tác,
    1 thẻ chi tiết (bảng tháng, so sánh mô hình, nằm bãi, lịch tàu, lượt ghé)"""
    E = get_econdb(ed.stamp()); s = E['series']
    if s.empty:
        ui.card_empty('Sản lượng', note_text='Chưa có dữ liệu EconDB (store/econdb/). Chạy bước pipeline "econdb" (cần biến môi trường ECONDB_TOKEN).'); return
    ui.DATA_MIN = date(2022, 1, 1)
    scopes = list(ed.VN_PORTS) if level == 'toan-quoc' else ed.AUTH_LOCODES.get(auth, [])
    if not scopes:
        ui.card_empty('Sản lượng', note_text=f'EconDB không theo dõi cảng thuộc {tl.AUTH_LABEL[auth]} (chỉ Hải Phòng, TP.HCM – Cái Mép, Đà Nẵng, Đồng Nai).'); return
    name = 'Việt Nam' if level == 'toan-quoc' else (tl.AUTH_LABEL[auth] if level == 'cang-vu' else f'{term} ({tl.AUTH_LABEL[auth]})')
    m = vol_model(level, auth, term, E)
    ui.h2(f'Sản lượng container · {name}')
    if m: vol_kpis(m, s, scopes)
    unit = 'TEU / ' + FREQ.lower()
    chips = VOL_CHIPS[level] if m else ([c for c in VOL_CHIPS[level] if c in VOL_SPLIT or c == 'So khu vực'] or ['Theo chiều'])

    # ---- thẻ chính
    with ui.card('Sản lượng container', unit='TEU có hàng xếp dỡ (EconDB)', key=f'{K}_vol', periods=ED_PER, default='2Y', end=TODAY,
                 chips=chips, chip_default=chips[0], chip_label='Xem',
                 help='Thực tế = EconDB (container full của cảng / throughput từng terminal). Ước/dự báo = hồi quy không hệ số chặn trên biến cảng vụ '
                      '(giờ nằm bến, sức chở TEU, số lượt), chọn mô hình theo sai số backtest ngoài mẫu; gạch = khoảng ± MAPE; đường nâu = backtest.') as cd:
        ch = cd.chip if cd.chip in chips else chips[0]
        if ch == 'Thực tế & dự báo':
            dd = m['d'][m['d'].index >= cd.d0]
            note = f'Thực tế: {m["src"]}. ' + (m.get('note') or '')
            r = m['res']
            if r and nw.NAIVE in r['mape'] and r['mape'][r['best']] >= r['mape'][nw.NAIVE] and r.get('n_bt', 99) >= 6:
                note += ' ⚠ Mô hình chưa tốt hơn "lấy tháng trước" → dùng số dự báo thận trọng.'
            elif r and not r.get('pooled') and r.get('n_bt', 99) < 6:
                note += f' Chỉ {r["n_bt"]} tháng backtest chung → sai số chưa đáng tin.'
            if r:                                        # 23/10/2026: hệ số hiệu chỉnh sai số 3 tháng có số gần nhất
                adjs = [r['adj']] if r.get('adj') else [p_.get('adj') for p_ in (r.get('parts') or {}).values() if p_ and p_.get('adj')]
                if adjs:
                    note += (' Ước/dự báo đã nhân hệ số hiệu chỉnh theo sai số 3 tháng có số gần nhất ('
                             + ', '.join(f'×{x:.2f}'.replace('.', ',') for x in adjs[:5]) + ') - độ đầy hàng của tàu thay đổi theo thời gian.'
                             + ' Mùa vụ tháng dự báo = TB của VPA cấp cảng vụ năm trước và mùa vụ sức chở tàu ghé cảng vụ nhiều năm (lịch tàu từ 2019).')
                if r.get('best') == nw.ENS or any(p_ and p_.get('best') == nw.ENS for p_ in (r.get('parts') or {}).values()):
                    note += (' Số ước = TB 3 cách: hồi quy lịch tàu, TB thực tế 3 tháng gần nhất × mùa vụ, hiệu suất khai thác (TEU / sức chở)'
                             ' 3 tháng × mùa vụ hiệu suất × sức chở tháng đích'
                             ' (backtest: sai số thấp hơn từng cách riêng, nhất là bến nhỏ/sà lan).')
            fig = fig_nowcast(dd, m['res']['best'] if m['res'] else '', blocks=(m['res'] or {}).get('blocks'))
            econ = m.get('econ')
            if econ is not None and len(econ):            # EconDB (full) chỉ để trong bảng tải về, không vẽ (PV2 16/10)
                dd = dd.join(econ[econ.index >= cd.d0].rename('econdb_full'))
            cd.chart(fig, dd[[c for c in ['actual', 'backtest', 'est', 'lo', 'hi', 'kind', 'econdb_full'] if c in dd]].round(0),
                     ten=f'san_luong_{_norm(name)}', note_text=note, last=LAST)
        elif ch == 'Theo quý':
            q = quarter_table(m['d'])
            q = q[[pd.Period(f"{i.split('/')[1]}Q{i[1]}").end_time >= pd.Timestamp(cd.d0) for i in q.index]] if len(q) else q
            if q.empty: cd.empty('Chưa đủ tháng để gom quý')
            else:
                t = q[['tong', 'thuc_te', 'uoc', 'thap', 'cao', 'yoy', 'tinh_trang']].rename(columns={
                    'tong': 'Tổng quý', 'thuc_te': 'Thực tế', 'uoc': 'Ước/dự báo', 'thap': 'Thấp', 'cao': 'Cao', 'yoy': 'So cùng kỳ (%)', 'tinh_trang': 'Tình trạng'})
                t.index.name = 'Quý'
                cd.chart(fig_quarter(q), t.iloc[::-1].round(1), ten=f'san_luong_quy_{_norm(name)}', last=LAST,
                         note_text='Quý = 3 tháng. Tháng chưa có thực tế lấy ước (nowcast) / dự báo của mô hình; dự báo luôn kéo tới hết quý đang mở. '
                                   'Khoảng thấp–cao chỉ cộng sai số của các tháng ước/dự báo. Quý thiếu tháng (không thực tế, không ước) không hiện.')
        elif ch == 'Tỷ trọng trong cảng vụ':
            v = nc_visits(); va = v[v['auth'] == auth]
            ft = nw.features(va[va['terminal'].map(nw.nfc) == nw.nfc(term)], LAST); fa = nw.features(va, LAST)
            w = pd.DataFrame({'Theo giờ nằm bến (cảng vụ)': ft['hours'] / fa['hours'].replace(0, np.nan) * 100})
            ts = nw.terminal_series(s, scopes, ed.TERMINAL_MAP, term, TODAY)
            if len(ts): w = w.join((ts / nw.econdb_monthly(s, scopes).reindex(ts.index) * 100).rename('Theo throughput EconDB'), how='outer')
            if m and m.get('share') is not None: w = w.join((m['share'] * 100).rename('Theo container xếp dỡ (EconDB)'), how='outer')
            w = cd.cut(w[w.index < tl.me(TODAY)]); w.index.name = 'Tháng'
            cd.chart(ui.fig_line(w, unit='% cảng vụ', zero=True, hover_nd=1), w.round(1), ten=f'ty_trong_{_norm(term)}')
        elif ch == 'So khu vực':
            vn = ed_wide(s, 'traffic', scopes).sum(axis=1, min_count=1).rename('Việt Nam')
            pw = ed_wide(s, 'traffic', list(ed.PEERS), by='scope')
            w = cd.cut(pd.concat([vn, pw], axis=1))
            show = w[['Việt Nam'] + [c for c in ['Singapore', 'Tanjung Pelepas', 'Port Klang', 'Laem Chabang'] if c in w]]
            cd.chart(ui.fig_line(show, unit=unit, zero=True, hover_nd=0), w, ten='so_khu_vuc', note_text='Container full EconDB; tệp tải về có đủ 13 cảng khu vực.')
        else:
            metric, by, top, lag = VOL_SPLIT[ch]
            w = ed_wide(s, metric, ['VN'] if metric.startswith('p2p') else scopes, by=by)
            if metric == 'term_throughput':
                tmap = {k: nw._members(t)[0] for lc in scopes for k, t in ed.TERMINAL_MAP.get(lc, {}).items()}
                w = w.rename(columns=lambda c: tmap.get(c, c)); w = w[w.index < tl.me(TODAY)]
            if top: w = ed_top(w, n=top)
            w = cd.cut(w)
            cd.chart(ui.fig_stack(w, unit=unit), w, ten=f'{metric}_{_norm(name)}',
                     note_text='Kỳ gần nhất thường thấp giả: EconDB bổ sung cảng đích/hãng dần sau khi tàu rời.' if lag else None)

    # ---- tham chiếu Cục Hàng hải (vimawa, biểu 28-T): số toàn quốc, phạm vi rộng hơn VPA nhưng ra sớm hơn 1 tháng
    if level == 'toan-quoc' and m is not None:
        vm = vimawa_teu(vimawa_stamp())
        if len(vm):
            with ui.card('Tham chiếu Cục Hàng hải (vimawa)', unit='TEU / tháng', key=f'{K}_vimawa', periods=ED_PER, default='2Y', end=LAST,
                         help='Biểu 28-T sản lượng container qua cảng biển của Cục Hàng hải & Đường thủy VN (vimawa.gov.vn/vi/thong-ke). '
                              'Phạm vi rộng hơn VPA (từ T4/2025 gộp cả cảng thủy nội địa) nên số cao hơn VPA.') as cd:
                w, ratio, err = vimawa_compare(m['d'], vm)
                w = cd.cut(w)
                fe = lambda k, lab: f'{lab} {err[k][0]:.1f}% ({err[k][1]} tháng)'.replace('.', ',') if err[k][0] is not None else ''  # noqa: E731
                fv = ui.fig_line(w, unit='TEU', zero=False, hover_nd=0, markers=True,
                                 dash={'App: dự báo quá khứ (backtest)': 'dot', 'Cục HH ước (lập ngày 15)': 'dot'})
                if fv is not None: fv.update_layout(meta='no_partial')             # tháng đang chạy = nowcast cả tháng
                cd.chart(fv,
                         w.iloc[::-1].round(0), ten='tham_chieu_cuc_hang_hai', last=LAST,
                         note_text=(f'Tỷ lệ VPA / Cục HH 6 tháng gần nhất = {ratio:.1%}. '.replace('.', ',', 1) if ratio else '')
                                   + 'Sai số trung bình (MAPE): ' + ' · '.join(x for x in (
                                       fe('app_bt', 'app dự báo quá khứ so VPA'), fe('cuc_uoc', 'Cục HH ước so Cục HH thực tế')) if x) + '. '
                                   + 'App dự báo quá khứ = backtest ngoài mẫu (mỗi tháng chỉ học từ các tháng trước). '
                                   'Cục HH thực tế tháng m = lũy kế tháng trước của báo cáo tháng m+1 − của báo cáo tháng m; số ước lập ngày 15 của tháng.')
    # ---- thẻ chi tiết
    if level == 'toan-quoc':
        rows = []
        for a in ed.AUTH_LOCODES:
            r = nc_auth(a, E)
            if not r: continue
            rows.append({'Phạm vi': tl.AUTH_LABEL[a], **nw.summary(r)})
            if len(r.get('parts') or {}) > 1:
                for lc, p in r['parts'].items(): rows.append({'Phạm vi': f'   ○ {ed.VN_PORTS.get(lc, lc)}', **nw.summary(p)})
            rows += [{**row, 'Phạm vi': '   └ ' + row['Phạm vi']} for row in terminal_rows(a, E, r)]
        with ui.card('Ước và dự báo theo cảng vụ, bến', unit='TEU / tháng', key=f'{K}_vol_tbl', controls=False,
                     help='Mỗi dòng = 1 mô hình riêng; thực tế cảng vụ = container full EconDB, bến = throughput terminal EconDB.') as cd:
            if rows: cd.table(pd.DataFrame(rows).drop(columns=['Số tháng huấn luyện'], errors='ignore').round(1), ten='du_bao_cang_vu_ben',
                              height=min(560, 60 + 36 * len(rows)))
            else: cd.empty('Chưa đủ dữ liệu')
        return
    tabs = (['Bảng tháng', 'So sánh mô hình'] if m and m['res'] else ['Bảng tháng'] if m else []) + \
           (['Theo bến'] if level == 'cang-vu' else ['Số công bố']) + ['Nằm bãi', 'Lịch tàu', 'Lượt ghé']
    with ui.card('Chi tiết', key=f'{K}_vol_det', controls=False, chips=tabs, chip_default=tabs[0], chip_label='Chi tiết') as cd:
        ch = cd.chip if cd.chip in tabs else tabs[0]
        if ch == 'Bảng tháng':
            cols = [c for c in ['kind', 'actual', 'backtest', 'est', 'lo', 'hi', 'calls', 'teu', 'hours', 'days_obs', 'share'] if c in m['d']]
            t = m['d'][cols].iloc[::-1].copy(); t.index = t.index.strftime('%m/%Y')
            cd.table(t.rename(columns={'kind': 'Loại', 'actual': 'Thực tế', 'backtest': 'Backtest', 'est': 'Ước/dự báo', 'lo': 'Thấp', 'hi': 'Cao',
                                       'calls': 'Lượt (cảng vụ)', 'teu': 'Sức chở TEU', 'hours': 'Giờ bến', 'days_obs': 'Số ngày dữ liệu',
                                       'share': 'Tỷ trọng'}).round(3), ten=f'bang_thang_{_norm(name)}', height=380)
        elif ch == 'So sánh mô hình':
            ps = m['res'].get('parts') or {}
            if len(ps) > 1:          # cảng vụ nhiều cảng: bảng mô hình từng cảng
                t = pd.DataFrame([{'Cảng': ed.VN_PORTS.get(k, k), 'Mô hình': p['best'], 'MAPE (%)': p['mape'][p['best']], 'Naive (%)': p['mape'][nw.NAIVE],
                                   'Tháng huấn luyện': p['n_train'], 'Hệ số': ' · '.join(f'{c} × {v:.2f}' for c, v in p['coef'].items()),
                                   'Mùa vụ tháng tới': p['seasonal']} for k, p in ps.items()])
                cd.table(t.round(2), ten=f'mo_hinh_tung_cang_{_norm(name)}', height=60 + 36 * len(t))
                ui.note('Mỗi cảng EconDB một mô hình riêng (biến = các bến thuộc cảng đó); cảng vụ = tổng. MAPE của tổng tính trên các tháng mọi cảng đều có backtest.')
            elif m['res'].get('pooled'):
                ui.note(f'Bến chưa có số công bố → dùng hệ số chung: {m["src"]}. Sai số {m["res"]["mape"][m["res"]["best"]]:.1f}% là sai số TRONG MẪU gộp của các bến công bố, '
                        'không phải backtest riêng của bến này. Nhập số công bố ở chip "Số công bố" để có mô hình riêng.')
            else:
                r = m['res']; d = r['data']
                if level == 'cang' and r.get('fits') is not None:
                    # chọn tay mô hình cho bến (mặc định: tự động theo điểm backtest)
                    opts = ['Tự động'] + list(nw.MODELS)
                    st.selectbox('Mô hình dùng cho bến này', opts, key=f'nc_force_{auth}_{nw.nfc(term)}',
                                 format_func=lambda x: f'Tự động (tổ hợp, hồi quy {r["auto"].split(":")[0]})' if x == 'Tự động' else x)
                rows = []
                for k in nw.MODELS:
                    rows.append({'Mô hình': k, 'Đang dùng': '✔' if k == r['best'] else ('tự động' if k == r.get('auto') else ''),
                                 'MAPE backtest (%)': r['mape'].get(k), '6 tháng gần (%)': (r.get('mape_recent') or {}).get(k),
                                 'Fit trong mẫu (%)': (r.get('fit_err') or {}).get(k)})
                if nw.UTIL in r['mape']:
                    rows.append({'Mô hình': nw.UTIL, 'Đang dùng': 'trong tổ hợp' if r['best'] == nw.ENS else '', 'MAPE backtest (%)': r['mape'][nw.UTIL],
                                 '6 tháng gần (%)': (r.get('mape_recent') or {}).get(nw.UTIL)})
                if nw.ENS in r['mape']:
                    rows.append({'Mô hình': nw.ENS, 'Đang dùng': '✔' if r['best'] == nw.ENS else '', 'MAPE backtest (%)': r['mape'][nw.ENS],
                                 '6 tháng gần (%)': (r.get('mape_recent') or {}).get(nw.ENS)})
                rows.append({'Mô hình': nw.NAIVE, 'Đang dùng': '', 'MAPE backtest (%)': r['mape'].get(nw.NAIVE), '6 tháng gần (%)': (r.get('mape_recent') or {}).get(nw.NAIVE)})
                t = pd.DataFrame(rows).sort_values('MAPE backtest (%)')
                cd.table(t.round(1).reset_index(drop=True), ten=f'so_sanh_mo_hinh_{_norm(name)}', height=60 + 36 * len(t))
                if r.get('fits') is not None:
                    # đối chiếu fit: thực tế (cột) + fit của mô hình đang dùng và 2 mô hình tốt kế tiếp
                    score = {k: 0.5 * r['mape'][k] + 0.5 * r['mape_recent'][k] for k in nw.MODELS}
                    rg = r.get('reg', r['best'])                 # tổ hợp: fit vẽ theo mô hình hồi quy thành phần
                    show = [rg] + [k for k in sorted(score, key=score.get) if k != rg][:2]
                    fits = r['fits'][show]; fits = fits[fits.index >= d.index.min()]
                    fig = go.Figure(go.Bar(x=d.index, y=d['actual'], name='Thực tế', marker_color=TOK['gray'], width=22 * 86400000, hovertemplate='%{y:,.0f}<extra>Thực tế</extra>'))
                    for i, k in enumerate(show):
                        fig.add_trace(go.Scatter(x=fits.index, y=fits[k].values, name=k, mode='lines+markers', marker=dict(size=4),
                                                 line=dict(width=2.2 if i == 0 else 1.4, dash='dash' if i == 0 else 'dot', color=[TOK['down'], TOK['brown'], TOK['tan']][i]),
                                                 hovertemplate='%{y:,.0f}<extra>' + k + '</extra>'))
                    fig.update_layout(height=340, yaxis=dict(title='TEU / tháng', rangemode='tozero'), bargap=0.25)
                    cd.chart(fig, fits.join(d['actual']).round(0), ten=f'fit_mo_hinh_{_norm(name)}', height=340,
                             note_text=f'Fit trong mẫu (hệ số cuối) của mô hình hồi quy đang dùng ({rg.split(":")[0]}) và 2 mô hình tốt kế tiếp theo điểm backtest. '
                                       f'{r["n_train"]} tháng huấn luyện; hệ số ' + ' · '.join(f'{k} × {v:.2f}' for k, v in r['coef'].items()) + f'; mùa vụ tháng tới {r["seasonal"]:.2f}.')
        elif ch == 'Theo bến':
            rows = terminal_rows(auth, E, m['res'] if m else None)
            if not rows: cd.empty('Chưa có bến nào đủ dữ liệu')
            else:
                t = pd.DataFrame(rows)
                tot = {'Phạm vi': 'Tổng các bến có mô hình', 'TEU thực tế cuối': t['TEU thực tế cuối'].sum(), 'Ước TEU': t['Ước TEU'].sum(), 'Dự báo TEU': t['Dự báo TEU'].sum()}
                if m and m['res']: tot_port = {'Phạm vi': f'Mô hình cảng vụ ({tl.AUTH_LABEL[auth]})', **nw.summary(m['res'])}; t = pd.concat([t, pd.DataFrame([tot, tot_port])], ignore_index=True)
                cd.table(t.drop(columns=['Số tháng huấn luyện'], errors='ignore').round(1), ten=f'du_bao_theo_ben_{_norm(name)}', height=min(560, 60 + 36 * len(t)))
                ui.note(f'Mỗi bến TỰ hồi quy trên lượt cập bến của chính nó, thực tế = số công bố nếu đã nhập (vd HICT), không thì throughput terminal EconDB; backtest từ tháng thứ {nw.MIN_TRAIN_TERM + 1}. '
                        'Tổng các bến có thể lệch mô hình cảng vụ vì EconDB không tách hết mọi bến (phần "Others"). Bấm "Từng cảng" để xem chi tiết từng bến.')
        elif ch == 'Số công bố':
            T = nw.load_targets(); cur = nw.target_series(T, auth, term)
            econ = nw.terminal_series(s, scopes, ed.TERMINAL_MAP, term, TODAY)
            ui.note(f'Sản lượng {term} do doanh nghiệp/cảng công bố (TEU/tháng, gồm cả container rỗng). Có ≥ {nw.MIN_TRAIN_TERM + 3} tháng thì mô hình dùng số này '
                    'thay cho EconDB (EconDB chỉ đếm container có hàng). Sửa trực tiếp trong bảng rồi bấm Lưu.')
            base = pd.DataFrame({'month': cur.index, 'actual_teu': cur.values}) if len(cur) else pd.DataFrame({'month': pd.Series(dtype='datetime64[ns]'), 'actual_teu': pd.Series(dtype=float)})
            if len(econ): base = base.merge(pd.DataFrame({'month': econ.index, 'EconDB (full)': econ.values}), on='month', how='outer').sort_values('month')
            edt = st.data_editor(base, num_rows='dynamic', key=f'{K}_tg_edit_{_norm(term)}', width='stretch', height=380,
                                 column_config={'month': st.column_config.DateColumn('Tháng', format='MM/YYYY'),
                                                'actual_teu': st.column_config.NumberColumn('Công bố (TEU)', format='%d'),
                                                'EconDB (full)': st.column_config.NumberColumn('EconDB (TEU full)', format='%d', disabled=True)})
            if st.button('💾 Lưu số công bố', key=f'{K}_tg_save_{_norm(term)}'):
                rows = edt[['month', 'actual_teu']].copy(); rows['month'] = tl.me(pd.to_datetime(rows['month']))
                nw.save_targets(auth, term, rows); st.session_state.pop('_nc', None); st.rerun()
        elif ch == 'Nằm bãi':
            w = ed_wide(s, 'dwell', scopes, flow=False)
            cd.chart(ui.fig_line(w, unit='ngày', hover_nd=1), w.round(2), ten=f'nam_bai_{_norm(name)}', height=300,
                     note_text='Ngày container nằm bãi bình quân tháng của cảng (EconDB, không tách theo bến).')
        elif ch == 'Lịch tàu':
            sc = E['schedule']; sc = sc[sc['locode'].isin(scopes)] if len(sc) else sc
            if level == 'cang' and len(sc):
                codes = [k for lc in scopes for k, t in ed.TERMINAL_MAP.get(lc, {}).items() if nw.nfc(term) in nw._members(t)]
                sc = sc[sc['terminal_code'].isin(codes)] if codes else sc.iloc[0:0]
            if sc.empty: cd.empty('Chưa có lịch tàu')
            else:
                cols = [c for c in ['start_date', 'end_date', 'port_name', 'terminal_code', 'ship_name', 'ship_imo', 'ship_teu', 'voyage_code'] if c in sc]
                t = sc.sort_values('start_date')[cols].fillna({'terminal_code': '', 'voyage_code': ''}).rename(columns={
                    'start_date': 'Đến', 'end_date': 'Rời', 'port_name': 'Cảng', 'terminal_code': 'Terminal', 'ship_name': 'Tàu', 'ship_imo': 'IMO',
                    'ship_teu': 'TEU', 'voyage_code': 'Chuyến'})
                cd.table(t.reset_index(drop=True), ten=f'lich_tau_{_norm(name)}', height=380)
        else:
            cl = E['calls']; cl = cl[cl['locode'].isin(scopes)].sort_values('start', ascending=False) if len(cl) else cl
            if cl.empty: cd.empty('Chưa có lượt ghé')
            else:
                cols = ['start', 'end', 'port_name', 'ship_name', 'ship_imo', 'import_count', 'export_count']
                cd.table(cl[cols].rename(columns={'start': 'Đến', 'end': 'Rời', 'port_name': 'Cảng', 'ship_name': 'Tàu', 'ship_imo': 'IMO',
                                                  'import_count': 'Dỡ', 'export_count': 'Xếp'}).reset_index(drop=True), ten=f'luot_ghe_{_norm(name)}', height=380)
                ui.note('Lượt tàu container EconDB của cả cảng (không tách bến), số container xếp/dỡ theo tàu; tích luỹ từ 16/06/2026.')


# ================================================================ khung nội dung: cấp 1 (trang) + cấp 2 (phạm vi) + trang
PG = ui.nav(list(PAGES), 'nav_page', default='tong-quan', kind='pills', fmt=lambda k: PAGES[k])
with st.container(border=True, key='khung_noi_dung'):
    LV = ui.nav(list(LEVELS), 'nav_lv', default='toan-quoc', kind='subtab', fmt=lambda k: LEVELS[k])
    st.query_params['trang'] = f'{PG}/{LV}'
    AUTH, TERM = pick_scope(LV)
    ok = LV == 'toan-quoc' or (LV == 'cang-vu' and AUTH) or (LV == 'cang' and TERM)
    if not ok:
        st.info('Chọn cảng vụ / bến để xem.')
    else:
        K = f'{PG}_{LV}'
        {'tong-quan': page_overview, 'hang-tau': page_operators, 'dieu-do': page_ops, 'tuyen': page_lanes, 'san-luong': page_volume,
         'du-lieu': page_data}[PG](LV, AUTH, TERM, K)
tick('render')
# 26/10/2026: GIẢI PHÓNG bảng lớn của lượt chạy. Streamlit giữ namespace lượt chạy cuối của TỪNG phiên (tab đang mở) tới lượt chạy sau;
# st.cache_data trả BẢN SAO -> mỗi tab giữ ~150 MB chuyến/lượt cập bến (đo: 1 tab 544 MB, 4 tab 1.127 MB, không tự giảm) -> vài người mở
# là vượt ~1 GB của Streamlit Cloud ("Error running app"); mem_guard xoá cache không gỡ được các bản này. Lượt chạy sau dựng lại từ cache.
for _n, _v in list(globals().items()):
    if not _n.startswith('_') and isinstance(_v, (pd.DataFrame, pd.Series)) and np.sum(_v.memory_usage(deep=False)) > 1e6:
        globals().pop(_n, None)
_gc.collect()
if CLOUD: mem_guard()                                # 21/10/2026: RAM > MEM_GUARD_MB (850) -> xoá cache, tránh Cloud tắt app
st.markdown(f'<div class="gn-note" style="margin-top:10px">Dữ liệu đến {LAST:%d/%m/%Y} · 12 cảng vụ · kho <code>{ld.STORE}</code> · '
            'Giao diện theo mẫu Market Data App (ui_genea.py)</div>', unsafe_allow_html=True)
