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

st.set_page_config(page_title='Port & Vessel Tracker', page_icon='⚓', layout='wide', initial_sidebar_state='collapsed')
ui.inject_css()
ui.PERIOD_MONTHS['2Y'] = 24
PER = ['3M', '6M', '1Y', '2Y', '3Y', 'All']
MEASURES = {'Lượt tàu': 'calls', 'TEU danh nghĩa': 'teu', 'DWT': 'dwt'}
TOK = ui.TOK


# ================================================================ dữ liệu: ghép từ kho (khoá cache = phiên bản kho)
@st.cache_data(show_spinner='Đang ghép chuyến phần lịch sử (mỗi tháng chỉ tính 1 lần)…', max_entries=6, persist='disk')
def get_frozen(auths, lo, b, fver, cv=2):
    return tl.calls_frozen(auths, lo, b)


@st.cache_data(show_spinner='Đang ghép chuyến từ dữ liệu vừa kéo…', max_entries=6)
def get_tail(auths, b, hi, ver, cv=2):
    return tl.calls_tail(auths, b, hi)


@st.cache_data(show_spinner=False, max_entries=6)
def get_calls(auths, lo, hi, ver, mstamp):
    b = str((TODAY.replace(day=1) - pd.DateOffset(months=1)).date())
    t0 = time.time(); fz = get_frozen(auths, lo, b, ld.version_before(auths, pd.Timestamp(b) + pd.Timedelta(days=30)))
    t1 = time.time(); tail = get_tail(auths, b, hi, ver)
    if os.environ.get('PT_PROFILE'): print(f'[profile]   frozen {t1 - t0:.1f}s, tail {time.time() - t1:.1f}s', flush=True)
    parts = [x for x in (fz, tail) if len(x)]
    return tl.enrich_calls(pd.concat(parts, ignore_index=True)) if parts else pd.DataFrame()


@st.cache_data(show_spinner='Đang tách lượt cập bến…', max_entries=6)
def get_visits(auths, lo, hi, ver, mstamp):
    c = get_calls(auths, lo, hi, ver, mstamp)
    return tl.load_visits(c, tl.terminal_meta(c))


def get_lanes(auths, lo, hi, ver, mstamp):
    key = (auths, lo, hi, str(TODAY.date()), ld.version_before(auths, TODAY - pd.Timedelta(days=30)), mstamp)
    cache = st.session_state.setdefault('_lanes', {})
    if key not in cache:
        with st.spinner('Đang tính chặng và vòng tuyến…'):
            cache.clear(); cache[key] = tl.build_lanes(get_calls(auths, lo, hi, ver, mstamp))
    return cache[key]


@st.cache_data(max_entries=2)
def get_master(ver, mstamp): return tl.master_live()


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
    return s.dt.to_period('W-SUN').dt.start_time if freq == 'Tuần' else s.dt.to_period('M').dt.to_timestamp()


def by_period(df, lo=None, hi=None):
    """lọc khung ngày [lo, hi] (mặc định của thẻ) rồi gán kỳ; bỏ kỳ cuối chưa trọn để đường không gãy giả"""
    d = df[(df['arr_day'] >= pd.Timestamp(lo if lo is not None else LO)) & (df['arr_day'] <= pd.Timestamp(hi if hi is not None else LAST))].copy()
    if d.empty: return d
    d['ky'] = bucket(d['arr_day'], FREQ)
    cur = bucket(pd.Series([LAST]), FREQ).iloc[0]
    end = (cur + pd.offsets.MonthEnd(0)) if FREQ == 'Tháng' else cur + pd.Timedelta(days=6)
    if LAST < end: d = d[d['ky'] < cur]
    first = d['ky'].min() if len(d) else None
    if first is not None and d.loc[d['ky'] == first, 'arr_day'].min() > first + pd.Timedelta(days=2 if FREQ == 'Tuần' else 5):
        d = d[d['ky'] > first]
    return d


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
PAGES = {'tong-quan': 'Tổng quan', 'hang-tau': 'Hãng tàu & tàu', 'dieu-do': 'Điều độ & cảnh báo', 'tuyen': 'Tuyến', 'du-lieu': 'Dữ liệu'}
LEVELS = {'toan-quoc': 'Toàn quốc', 'cang-vu': 'Từng cảng vụ', 'cang': 'Từng cảng'}
CU = {'ben-cang': 'tong-quan', 'tau': 'hang-tau', 'canh-bao': 'dieu-do'}            # slug trang cũ
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
cov = ld.coverage()
with h2c:
    _, p = st.columns([1, 3])
    with p:
        with st.popover(f'Kho dữ liệu: {len(cov)} cảng vụ ▾', width='stretch'):
            ss = ld.store_status()
            ui.note(f'Pipeline ghép liên tục: cloud 9:00 + 22:00 (11 cảng vụ), laptop 8:30 + 18:40 (TP.HCM) → kho chia sẻ store/ '
                    f'({ss["files"]} tệp parquet, cập nhật gần nhất {ss["latest"] or "–"}). Ngày đã qua hơn 2 ngày coi là chốt.')
            if len(cov):
                cv2 = cov.copy(); cv2['Cảng vụ'] = cv2['auth'].map(tl.AUTH_LABEL); cv2['o'] = cv2['auth'].map({a: i for i, a in enumerate(tl.AUTH_ORDER)})
                st.dataframe(cv2.sort_values('o')[['Cảng vụ', 'tu_ngay', 'den_ngay', 'so_ngay', 'so_su_kien', 'keo_gan_nhat']]
                             .rename(columns={'tu_ngay': 'Từ', 'den_ngay': 'Đến', 'so_ngay': 'Số ngày', 'so_su_kien': 'Sự kiện', 'keo_gan_nhat': 'Kéo gần nhất'}),
                             width='stretch', hide_index=True, height=40 + 35 * len(cv2))
            LIVE = st.toggle('Kéo thêm từ trang nguồn khi mở', value=False, key='live_on',
                             help='Kho đã được pipeline cập nhật 2 lần/ngày. Bật khi cần số liệu trong ngày (gọi thẳng 12 trang cảng vụ, 10–60 giây).')
            TTL = st.select_slider('Làm mới ngày gần đây sau (phút)', [5, 10, 30, 60, 180], value=30, key='ttl')
            FORCE = st.button('🔄 Kéo lại từ nguồn ngay', key='force_pull', width='stretch')

# ---- bộ lọc chung (thay sidebar cũ)
f1, f2, f3, f4, f5 = st.columns([1.3, 1.9, 1.2, 1.7, 3])
with f1: TAU = st.segmented_control('Loại tàu', ['Container', 'Mọi loại'], default='Container', key='f_tau') or 'Container'
with f2: MEAS_LABEL = st.segmented_control('Đo lường', list(MEASURES), default='TEU danh nghĩa', key='f_meas') or 'TEU danh nghĩa'
with f3: FREQ = st.segmented_control('Độ phân giải', ['Tháng', 'Tuần'], default='Tháng', key='f_freq') or 'Tháng'
with f4: NAP = st.segmented_control('Dữ liệu nạp', ['2 năm', '3 năm', 'Từ 2019'], default='2 năm', key='f_nap') or '2 năm'
ONLY_CONT = TAU == 'Container'; MEAS = MEASURES[MEAS_LABEL]
MONTHS = {'2 năm': 26, '3 năm': 38, 'Từ 2019': 400}[NAP]
tick('header')

# ================================================================ nạp kho + ghép chuyến
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
VER = ld.version(); MST = tl.stamp('master', 'hp_terminals', 'hcm_terminals')
KEY = (tuple(AUTHS), str(LOAD_LO.date()), str(LOAD_HI.date()), VER, MST)
with st.spinner('Đang ghép chuyến tàu từ kho (lần đầu trong tháng có thể mất 1–2 phút)…'):
    calls = get_calls(*KEY)
if calls.empty:
    st.error('Kho chưa có dữ liệu. Kiểm tra mạng hoặc vào trang "Dữ liệu" để kéo từ nguồn.'); st.stop()
visits = get_visits(*KEY)
tick('get_calls+visits')
LAST = min(calls.loc[calls['arr_day'].notna(), 'arr_day'].max(), TODAY)
LO = LOAD_LO
ui.set_data_end(LAST); ui.DATA_MIN = LOAD_LO.date()
_upd = (VER.split('|')[1] or '')[:16]
with f5:
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
                     help='Mỗi đường = 1 cảng vụ (7 lớn nhất + Khác). Kỳ cuối chưa trọn bị bỏ.') as cd:
            w = wide(by_period(c, cd.d0, cd.d1), 'Cảng vụ', order)
            cd.chart(ui.fig_line(w, unit=MEAS_LABEL, zero=True, hover_nd=0), w, last=LAST, ten='theo_cang_vu',
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
            cd.chart(ui.fig_stack(w, unit=MEAS_LABEL), w, last=LAST, ten=f'{auth}_theo_{dim}')
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
                cd.chart(ui.fig_bars(w, unit=MEAS_LABEL, sign=False, hover_nd=0), w, last=LAST, ten=f'{term}_theo_ky')
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
        stops = vi.stops_for_ship(rec(w[w['auth'] == 'HP']), rec(w[w['auth'] == 'HCM']), vi.Geo(), other_calls=rec(oth.assign(ship=oth['auth'])) if len(oth) else None)
        st.markdown('**Lộ trình trong khung ngày trên**')
        if not stops: ui.note('Không có điểm dừng trong khoảng ngày này.')
        else:
            dist = vi.Dist(); legs = vi.legs_from_stops(stops, dist); dist.save()
            nm = sum(l['nm'] or 0 for l in legs)
            ui.note(f'{len(stops)} điểm dừng, {len(legs)} chặng, khoảng {fmt_int(nm)} hải lý. Dấu ~ là điểm suy từ cảng đi/đến ghi ở Hải Phòng; '
                    'cảng nước ngoài đa số chỉ ở mức quốc gia nên vị trí và hải lý là gần đúng.')
            srows = pd.DataFrame(vi.stop_rows({'ship_key': key, 'ship': name}, stops))[
                ['seq', 'port', 'precision', 'terminal', 'arrive', 'depart', 'hours_in_port', 'inferred', 'source', 'raw_name']]
            srows['hours_in_port'] = pd.to_numeric(srows['hours_in_port'], errors='coerce')
            a, b = st.columns([3, 2])
            with a:
                st.dataframe(srows, width='stretch', hide_index=True, height=340); dl_row(srows, f'lo_trinh_{ui.slug(key)}', f'{K}_stops')
            with b:
                if st.button('🗺️ Vẽ bản đồ lộ trình', key=f'{K}_map', width='stretch'):
                    png = os.path.join(tempfile.gettempdir(), f'tracker_{key.replace(" ", "_")}.png')
                    with st.spinner('Đang tính tuyến biển và vẽ…'): ok = vi.render_png(name, stops[-40:], png)
                    if ok:
                        st.image(png)
                        with open(png, 'rb') as f: st.download_button('⤓ Tải PNG', f.read(), file_name=os.path.basename(png), key=f'{K}_png')
                    else: st.warning('Không đủ điểm có toạ độ để vẽ.')
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
                cd.chart(ui.fig_stack(w, unit=MEAS_LABEL), w, last=LAST, ten=f'{term}_hang_theo_ky')

    order_op = entity_order(known, 'operator', MEAS)
    if order_op:
        with ui.card('Chi tiết một hãng', unit='phân bổ + đội tàu đang khai thác', key=f'{K}_opdetail', periods=PER, default='2Y', end=LAST) as cd:
            op = st.selectbox('Hãng', order_op, key=f'{K}_op_sel')
            allo = known[known['operator'] == op].copy()
            allo['ben'] = allo['Cảng vụ'] if level == 'toan-quoc' else (allo['terminal'] if level == 'cang-vu' else term)
            w = wide(by_period(allo, cd.d0, cd.d1), 'ben', entity_order(allo, 'ben', MEAS))
            cd.chart(ui.fig_stack(w, unit=MEAS_LABEL), w, last=LAST, ten=f'{ui.slug(op)}_theo_ben')
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
def page_lanes(level, auth, term, K):
    lanes, patterns, legs = get_lanes(*KEY)
    ui.h2(f'Luồng tuyến · {scope_name(level, auth, term)}')
    if level != 'toan-quoc':
        ships = set(scoped(level, auth, term)[1]['ship_key'])
        legs = legs[legs['ship_key'].isin(ships)] if len(legs) else legs
        lanes = tl.lanes_from_legs(legs); patterns = patterns[patterns['ship_key'].isin(ships)] if len(patterns) else patterns
        ui.note(f'Chặng của các tàu container đã ghé {scope_name(level, auth, term)} trong dữ liệu đã nạp (mọi chặng của các tàu đó, kể cả chặng không qua cảng này).')
    else:
        ui.note('Chặng ghép trong app từ lịch 12 cảng vụ, chỉ gồm tàu container. Cảng nước ngoài đa số ở mức quốc gia. Không gồm chặng đi/đến "ngoài vùng dữ liệu".')
    if lanes.empty: ui.card_empty('Chặng', note_text='Chưa đủ dữ liệu để ghép chặng cho phạm vi này.'); return
    L = lanes[(~lanes['lane'].str.contains('ngoai vung du lieu')) & (lanes['from'] != lanes['to'])]
    mcol = 'teu_sum' if MEAS == 'teu' else 'legs'; mlab = 'TEU danh nghĩa' if MEAS == 'teu' else 'Số chặng'
    a, b = st.columns([2, 3])
    with a:
        with ui.card('Chặng lớn nhất', unit=mlab, key=f'{K}_top', periods=PER, default='1Y', end=LAST, compact=True) as cd:
            Lw = L[(L['month'] >= pd.Timestamp(cd.d0)) & (L['month'] <= pd.Timestamp(cd.d1))]
            top = Lw.groupby('lane')[mcol].sum().sort_values(ascending=False)
            cd.chart(ui.fig_hbar(top.head(15), unit=mlab, sign=False, nd=0), top.rename(mlab).to_frame(), last=LAST, ten='chang_lon_nhat')
    order = L.groupby('lane')[mcol].sum().sort_values(ascending=False).index.tolist()
    with b:
        with ui.card('Chặng theo tháng', unit=mlab, key=f'{K}_series', periods=PER, default='2Y', end=LAST, compact=True) as cd:
            pick = st.multiselect('Chặng theo dõi (tối đa 6)', order, default=order[:4], max_selections=6, key=f'{K}_pick')
            g = L[L['lane'].isin(pick) & (L['month'] >= pd.Timestamp(cd.d0)) & (L['month'] <= pd.Timestamp(cd.d1)) & (L['month'] < LAST.to_period('M').to_timestamp())]
            w = g.groupby(['month', 'lane'])[mcol].sum().unstack('lane').reindex(columns=[k for k in order if k in pick]).fillna(0)
            w.index = pd.DatetimeIndex(w.index); w.index.name = 'Tháng'
            cd.chart(ui.fig_line(w, unit=mlab, zero=True, hover_nd=0), w, last=LAST, ten='chang_theo_thang')
    with ui.card('Hãng khai thác trên một chặng', unit=mlab, key=f'{K}_ops', periods=PER, default='1Y', end=LAST) as cd:
        one = st.selectbox('Chặng', order, key=f'{K}_lane')
        o = L[(L['lane'] == one) & (L['month'] >= pd.Timestamp(cd.d0)) & (L['month'] <= pd.Timestamp(cd.d1))].groupby('operator')[[mcol, 'ships']].sum().sort_values(mcol, ascending=False)
        cd.chart(ui.fig_hbar(o[mcol].head(12), unit=mlab, sign=False, nd=0), o.rename(columns={mcol: mlab, 'ships': 'Số tàu'}), last=LAST, ten=f'hang_tren_chang')
    with ui.card('Vòng tuyến hay chạy của từng tàu', unit=f'{len(patterns)} tàu', key=f'{K}_pat', controls=False) as cd:
        cd.table(patterns.drop(columns=['ship_key']).reset_index(drop=True), ten='vong_tuyen_tau', height=400)


# ================================================================ TRANG 5: DỮ LIỆU
def pull_block(auths_default, K):
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
        {'tong-quan': page_overview, 'hang-tau': page_operators, 'dieu-do': page_ops, 'tuyen': page_lanes, 'du-lieu': page_data}[PG](LV, AUTH, TERM, K)
tick('render')
st.markdown(f'<div class="gn-note" style="margin-top:10px">Dữ liệu đến {LAST:%d/%m/%Y} · 12 cảng vụ · kho <code>{ld.STORE}</code> · '
            'Giao diện theo mẫu Market Data App (ui_genea.py)</div>', unsafe_allow_html=True)
