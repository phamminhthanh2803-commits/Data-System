# -*- coding: utf-8 -*-
r"""
PORT & VESSEL TRACKER - theo dõi cảng và tàu trên bộ dữ liệu cảng vụ Hải Phòng + TP.HCM (D:\shipping).
Chạy:  D:\shipping\port-tracker\Chay-app.bat   (http://localhost:8766)
App GỌI THẲNG trang nguồn của từng cảng vụ (livedata.py), phân tích trong bộ nhớ và lưu vào kho riêng cache\\live.sqlite.
Không đọc các file events/calls do pipeline parse sẵn.
"""
import os, sys, tempfile
from datetime import date

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trackerlib as tl  # noqa: E402
import livedata as ld   # noqa: E402
import threading, time  # noqa: E402

st.set_page_config(page_title='Port & Vessel Tracker', page_icon='⚓', layout='wide', initial_sidebar_state='expanded')

# ---------------------------------------------------------------- bảng màu (bộ tham chiếu đã kiểm định mù màu, thứ tự CỐ ĐỊNH)
try:
    DARK = (st.context.theme.type == 'dark')
except Exception:
    DARK = False
CAT = (['#3987e5', '#d95926', '#199e70', '#c98500', '#d55181', '#008300', '#9085e9', '#e66767'] if DARK else
       ['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#4a3aa7', '#e34948'])
OTHER = '#6f6e69' if DARK else '#b4b2a9'
INK2 = '#c3c2b7' if DARK else '#52514e'
GRID = '#383835' if DARK else '#e4e2dc'
SURF = '#0e1117' if DARK else '#ffffff'
SEQ = ['#184f95', '#3987e5', '#9ec5f4'] if DARK else ['#cde2fb', '#3987e5', '#0d366b']
LOCALE_VI = {'decimal': ',', 'thousands': '.', 'grouping': [3], 'currency': ['', ' ₫']}
EMBED = {'embedOptions': {'formatLocale': LOCALE_VI, 'actions': {'export': True, 'source': False, 'compiled': False, 'editor': False}}}

st.markdown("""<style>
  .block-container {padding-top: 2.0rem; padding-bottom: 1rem; max-width: 100%;}
  [data-testid="stMetricValue"] {font-size: 1.5rem;}
  [data-testid="stMetricLabel"] {opacity: .75;}
</style>""", unsafe_allow_html=True)

MEASURES = {'Lượt tàu': 'calls', 'TEU danh nghĩa (sức chở tàu)': 'teu', 'DWT': 'dwt'}


# ---------------------------------------------------------------- dữ liệu: ghép từ kho trực tiếp (khoá cache = phiên bản kho)
@st.cache_data(show_spinner='Đang ghép chuyến phần lịch sử (mỗi tháng chỉ tính 1 lần)…', max_entries=6, persist='disk')
def get_frozen(auths, lo, b, fver, cv=2):                 # cv: tăng khi đổi cách làm sạch/ghép để bỏ cache đĩa cũ
    return tl.calls_frozen(auths, lo, b)


@st.cache_data(show_spinner='Đang ghép chuyến từ dữ liệu vừa kéo…', max_entries=6)
def get_tail(auths, b, hi, ver, cv=2):
    return tl.calls_tail(auths, b, hi)


@st.cache_data(show_spinner=False, max_entries=6)
def get_calls(auths, lo, hi, ver, mstamp):
    b = str((TODAY.replace(day=1) - pd.DateOffset(months=1)).date())            # mốc tách: đầu tháng trước
    t0 = time.time(); fz = get_frozen(auths, lo, b, ld.version_before(auths, pd.Timestamp(b) + pd.Timedelta(days=30)))
    t1 = time.time(); tail = get_tail(auths, b, hi, ver)
    if os.environ.get('PT_PROFILE'): print(f'[profile]   frozen {t1 - t0:.1f}s, tail {time.time() - t1:.1f}s', flush=True)
    parts = [fz, tail]
    parts = [x for x in parts if len(x)]
    return tl.enrich_calls(pd.concat(parts, ignore_index=True)) if parts else pd.DataFrame()


@st.cache_data(show_spinner='Đang tách lượt cập bến…', max_entries=6)
def get_visits(auths, lo, hi, ver, mstamp):
    c = get_calls(auths, lo, hi, ver, mstamp)
    return tl.load_visits(c, tl.terminal_meta(c))


def get_lanes(auths, lo, hi, ver, mstamp):
    return _lanes_day(auths, lo, hi, mstamp, ver)


def _lanes_day(auths, lo, hi, mstamp, ver):
    key = (auths, lo, hi, str(TODAY.date()), ld.version_before(auths, TODAY - pd.Timedelta(days=30)), mstamp)
    cache = st.session_state.setdefault('_lanes', {})
    if key not in cache:
        with st.spinner('Đang tính chặng và vòng tuyến…'):
            cache.clear(); cache[key] = tl.build_lanes(get_calls(auths, lo, hi, ver, mstamp))
    return cache[key]


@st.cache_data(max_entries=2)
def get_master(ver, mstamp): return tl.master_live()


def live_pull(auths, d0, d1, ttl, max_pages, label, auto=False):
    """Gọi trang nguồn cho các ngày thiếu/cũ, có thanh tiến độ. Trả về (số trang đã kéo, số trang còn thiếu, lỗi).
    auto=True (khi mở app): chỉ làm mới ngày gần đây + lấp khoảng trống nhỏ (<= 12 ngày/cảng vụ); khoảng trống lớn để người dùng
    chủ động kéo ở trang Dữ liệu, tránh chặn giao diện mỗi lần đổi trang."""
    todo = ld.plan(auths, d0, d1, ttl_min=ttl)
    need = sum(len(v) for v in todo.values())
    if auto:
        todo = {a: ds for a, ds in todo.items() if not ld.cooling(a)}           # nguồn vừa lỗi: chờ 5 phút rồi mới thử lại
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
    """đo thời gian từng bước khi đặt biến môi trường PT_PROFILE=1 (in ra log máy chủ)"""
    if os.environ.get('PT_PROFILE'):
        print(f'[profile] {label}: {time.time() - _T0[0]:.1f}s', flush=True)
    _T0[0] = time.time()


# ---------------------------------------------------------------- tiện ích
def add_measure(df):
    d = df.copy(); d['calls'] = 1
    d['teu'] = pd.to_numeric(d['teu'], errors='coerce').fillna(0); d['dwt'] = d['dwt'].fillna(0)
    return d


def bucket(s, freq):
    return s.dt.to_period('W-SUN').dt.start_time if freq == 'Tuần' else s.dt.to_period('M').dt.to_timestamp()


def drop_partial(df, col, freq):
    """bỏ kỳ cuối chưa trọn (tháng/tuần đang chạy) để đường không gãy giả"""
    if df.empty: return df
    first = bucket(pd.Series([df[col].min()]), freq).iloc[0]
    src = df['arr_day'] if 'arr_day' in df else None
    if src is not None and src[df[col] == first].min() > first + pd.Timedelta(days=2 if freq == 'Tuần' else 5):
        df = df[df[col] > first]                                       # kỳ đầu bị cắt bởi mốc lọc -> bỏ
    cur = bucket(pd.Series([LAST]), freq).iloc[0]
    end = (cur + pd.offsets.MonthEnd(0)) if freq == 'Tháng' else cur + pd.Timedelta(days=6)
    return df if LAST >= end else df[df[col] < cur]


def color_scale(order):
    rng = []; i = 0
    for k in order:
        if k == 'Khác': rng.append(OTHER)
        else: rng.append(CAT[i % len(CAT)]); i += 1
    return alt.Scale(domain=list(order), range=rng)


def base_cfg(ch, height=300):
    return (ch.properties(height=height, usermeta=EMBED)
            .configure(locale=alt.Locale(number=alt.NumberLocale(decimal=',', thousands='.', grouping=[3], currency=['', ' ₫'])))
            .configure_view(strokeWidth=0)
            .configure_axis(gridColor=GRID, domainColor=GRID, tickColor=GRID, labelColor=INK2, titleColor=INK2, labelFontSize=11,
                            titleFontSize=11, titleFontWeight='normal')
            .configure_legend(labelColor=INK2, titleColor=INK2, orient='top', title=None, labelLimit=220, symbolStrokeWidth=3))


def line_chart(df, x, y, color, order, ytitle, yfmt=',.0f', height=300):
    if df.empty: st.info('Không có dữ liệu cho lựa chọn này.'); return
    hover = alt.selection_point(fields=[x], nearest=True, on='pointerover', empty=False, clear='pointerout')
    enc = alt.Chart(df).encode(x=alt.X(f'{x}:T', title=None, axis=alt.Axis(grid=False, format='%m/%y')),
                               y=alt.Y(f'{y}:Q', title=ytitle, axis=alt.Axis(format=yfmt)),
                               color=alt.Color(f'{color}:N', scale=color_scale(order), sort=list(order)))
    tips = [alt.Tooltip(f'{x}:T', title='Kỳ', format='%d/%m/%Y'), alt.Tooltip(f'{color}:N', title='Nhóm'),
            alt.Tooltip(f'{y}:Q', title=ytitle, format=yfmt)]
    ch = alt.layer(enc.mark_line(strokeWidth=2),
                   enc.mark_point(size=70, filled=True, stroke=SURF, strokeWidth=2)
                      .encode(opacity=alt.condition(hover, alt.value(1), alt.value(0)), tooltip=tips).add_params(hover),
                   alt.Chart(df).mark_rule(color=INK2, strokeWidth=1).encode(x=f'{x}:T', opacity=alt.condition(hover, alt.value(.45), alt.value(0))))
    st.altair_chart(base_cfg(ch, height), width='stretch')


def stack_chart(df, x, y, color, order, ytitle, yfmt=',.0f', height=300, freq='Tháng'):
    if df.empty: st.info('Không có dữ liệu cho lựa chọn này.'); return
    rank = {k: i for i, k in enumerate(order)}
    d = df.copy(); d['_o'] = d[color].map(rank)
    ch = alt.Chart(d).mark_bar(stroke=SURF, strokeWidth=1).encode(
        x=alt.X(f'{x}:T', title=None, timeUnit='yearmonth' if freq == 'Tháng' else 'yearweek', axis=alt.Axis(grid=False, format='%m/%y')),
        y=alt.Y(f'{y}:Q', title=ytitle, stack='zero', axis=alt.Axis(format=yfmt)),
        color=alt.Color(f'{color}:N', scale=color_scale(order), sort=list(order)),
        order=alt.Order('_o:Q'),
        tooltip=[alt.Tooltip(f'{x}:T', title='Kỳ', format='%m/%Y'), alt.Tooltip(f'{color}:N', title='Nhóm'),
                 alt.Tooltip(f'{y}:Q', title=ytitle, format=yfmt)])
    st.altair_chart(base_cfg(ch, height), width='stretch')


def hbar(df, cat, val, vtitle, height=None, fmt=',.0f'):
    if df.empty: st.info('Không có dữ liệu.'); return
    ch = alt.Chart(df).mark_bar(color=CAT[0], cornerRadiusEnd=3, height={'band': .65}).encode(
        y=alt.Y(f'{cat}:N', sort='-x', title=None, axis=alt.Axis(labelLimit=260)),
        x=alt.X(f'{val}:Q', title=vtitle, axis=alt.Axis(format=fmt)),
        tooltip=[alt.Tooltip(f'{cat}:N', title=''), alt.Tooltip(f'{val}:Q', title=vtitle, format=fmt)])
    st.altair_chart(base_cfg(ch, height or max(160, 26 * len(df) + 40)), width='stretch')


def fmt_int(v): return '–' if v is None or pd.isna(v) else f'{v:,.0f}'.replace(',', '.')


def fmt_pct(v): return None if v is None or pd.isna(v) else f'{v * 100:+.1f}%'.replace('.', ',')


def table(df, key, height=380, name=None):
    st.dataframe(df, width='stretch', hide_index=True, height=height)
    c1, c2, _ = st.columns([1, 1, 6])
    c1.download_button('⬇️ Excel', tl.to_excel({(name or key)[:31]: df}) if len(df) <= 200000 else b'', file_name=f'{name or key}.xlsx',
                       key=f'x_{key}', disabled=len(df) > 200000)
    c2.download_button('⬇️ CSV', df.to_csv(index=False).encode('utf-8-sig'), file_name=f'{name or key}.csv', key=f'c_{key}')


def entity_order(df, key, value, lo):
    """thứ tự thực thể CỐ ĐỊNH theo tổng 24 tháng gần nhất -> màu đi theo thực thể, không đổi khi lọc kỳ"""
    d = df[df['arr_day'] >= LAST - pd.DateOffset(months=24)]
    return d.groupby(key)[value].sum().sort_values(ascending=False).index.tolist()


# ---------------------------------------------------------------- sidebar
st.sidebar.title('⚓ Port & Vessel Tracker')
PAGES = ['Tổng quan', 'Bến cảng', 'Hãng tàu', 'Tàu', 'Bảng điều độ', 'Cảnh báo', 'Tuyến', 'Dữ liệu']
SLUG = dict(zip(['tong-quan', 'ben-cang', 'hang-tau', 'tau', 'dieu-do', 'canh-bao', 'tuyen', 'du-lieu'], PAGES))
_qp = SLUG.get(st.query_params.get('trang', ''), PAGES[0])          # mở thẳng 1 trang: http://localhost:8766/?trang=canh-bao
PAGE = st.sidebar.radio('Trang', PAGES, index=PAGES.index(_qp), label_visibility='collapsed')
st.sidebar.divider()
ALL_AUTHS = list(ld.AUTHS)
AUTHS = st.sidebar.multiselect('Cảng vụ (trống = cả nước)', ALL_AUTHS, default=[], format_func=lambda a: tl.AUTH_LABEL.get(a, a)) or ALL_AUTHS
ONLY_CONT = st.sidebar.toggle('Chỉ tàu container', value=True)
PRESET = st.sidebar.selectbox('Khoảng thời gian', ['6 tháng', '12 tháng', '24 tháng', '36 tháng', 'Từ 2019'], index=2)
FREQ = st.sidebar.radio('Độ phân giải', ['Tháng', 'Tuần'], horizontal=True)
MEAS_LABEL = st.sidebar.selectbox('Đo lường', list(MEASURES), index=1 if ONLY_CONT else 0)
MEAS = MEASURES[MEAS_LABEL]
MONTHS = {'6 tháng': 6, '12 tháng': 12, '24 tháng': 24, '36 tháng': 36, 'Từ 2019': 400}[PRESET]
st.sidebar.divider()
LIVE = st.sidebar.toggle('Tự kéo từ trang nguồn khi mở', value=True, help='Tắt: chỉ dùng dữ liệu đã có trong kho của app.')
TTL = st.sidebar.select_slider('Làm mới ngày gần đây sau (phút)', [5, 10, 30, 60, 180], value=30)
FORCE = st.sidebar.button('🔄 Kéo lại từ nguồn ngay', width='stretch')

# ---- kho của app: lần đầu nạp lịch sử đã có (1 lần), sau đó mọi cập nhật đi thẳng từ trang nguồn
tick('sidebar')
if ld.is_empty():
    with st.spinner('Khởi tạo kho dữ liệu của app từ lịch sử đã có (chỉ 1 lần, khoảng 1–2 phút)…'):
        ld.seed_from_local()
LOAD_LO = max(pd.Timestamp('2019-01-01'), TODAY - pd.DateOffset(months=max(MONTHS, 26)) - pd.Timedelta(days=45))
LOAD_HI = TODAY + pd.Timedelta(days=1)
if LIVE or FORCE:
    n_pull, n_left, errs = live_pull(AUTHS, LOAD_LO, LOAD_HI, 0 if FORCE else TTL, 40, 'Đang gọi trang nguồn các cảng vụ', auto=True)
    if n_pull: st.toast(f'Đã kéo trực tiếp {n_pull} trang từ nguồn')
    if n_left: st.warning(f'Còn {n_left} ngày-cảng vụ chưa có trong kho cho khoảng thời gian này. Vào trang "Dữ liệu" để kéo bù từ nguồn.')
    if errs:
        with st.expander(f'{len(errs)} lỗi khi gọi nguồn'): st.write(errs[:40])

tick('goi nguon')
VER = ld.version(); MST = tl.stamp('master', 'hp_terminals', 'hcm_terminals')
KEY = (tuple(AUTHS), str(LOAD_LO.date()), str(LOAD_HI.date()), VER, MST)
calls = get_calls(*KEY)
if calls.empty:
    st.error('Kho chưa có dữ liệu cho lựa chọn này và không kéo được từ nguồn. Kiểm tra mạng hoặc vào trang "Dữ liệu".'); st.stop()
tick('get_calls')
visits = get_visits(*KEY)
tick('get_visits')
LAST = min(calls.loc[calls['arr_day'].notna(), 'arr_day'].max(), TODAY)
LO = max((LAST - pd.DateOffset(months=MONTHS)).normalize(), LOAD_LO)
st.sidebar.caption(f'Dữ liệu đến {LAST:%d/%m/%Y}, kéo trực tiếp từ trang cảng vụ. TEU là sức chở danh nghĩa của tàu, không phải sản lượng xếp dỡ.')


def scope(df, date_col='arr_day', lo=None):
    d = df[df['auth'].isin(AUTHS) & df[date_col].notna()]
    if ONLY_CONT: d = d[d['is_container']]
    return d[(d[date_col] >= (lo if lo is not None else LO)) & (d[date_col] <= LAST)]


# ================================================================ TỔNG QUAN
if PAGE == 'Tổng quan':
    st.title('Tổng quan cảng và tàu')
    st.caption(('Tàu container' if ONLY_CONT else 'Mọi loại tàu') + ' · ' + (f'cả nước ({len(AUTHS)} cảng vụ)' if len(AUTHS) == len(ALL_AUTHS) else ', '.join(tl.AUTH_LABEL[a] for a in AUTHS)) +
               f' · so sánh 30 ngày đến {LAST:%d/%m/%Y}')
    base = add_measure(scope(calls, lo=LAST - pd.Timedelta(days=800)))
    end = LAST + pd.Timedelta(days=1)
    cols = st.columns(4)
    for col, (lab, m) in zip(cols, [('Lượt tàu vào, 30 ngày', 'calls'), ('TEU danh nghĩa, 30 ngày', 'teu'), ('DWT, 30 ngày', 'dwt')]):
        a, b, y = tl.period_compare(base, 'arr_day', m, end, 30)
        col.metric(lab, fmt_int(a), fmt_pct(tl.pct(a, b)), help=f'30 ngày trước: {fmt_int(b)} · cùng kỳ năm trước: {fmt_int(y)} ({fmt_pct(tl.pct(a, y)) or "–"})')
    cur = base[(base['arr_day'] >= end - pd.Timedelta(days=30)) & (base['arr_day'] < end)]
    prv = base[(base['arr_day'] >= end - pd.Timedelta(days=60)) & (base['arr_day'] < end - pd.Timedelta(days=30))]
    h1, h0 = cur['hours_in_port'].median(), prv['hours_in_port'].median()
    cols[3].metric('Giờ nằm cảng (trung vị)', '–' if pd.isna(h1) else f'{h1:.1f}'.replace('.', ','),
                   None if pd.isna(h0) or pd.isna(h1) else f'{h1 - h0:+.1f} giờ'.replace('.', ','), delta_color='inverse',
                   help=f'Số tàu khác nhau trong 30 ngày: {cur["ship_key"].nunique()}')

    d = add_measure(scope(calls)); d['ky'] = bucket(d['arr_day'], FREQ); d = drop_partial(d, 'ky', FREQ)
    d['Cảng vụ'] = d['auth'].map(tl.AUTH_LABEL)
    st.subheader(f'{MEAS_LABEL} theo {FREQ.lower()}')
    allc = add_measure(calls[calls['arr_day'].notna() & (calls['is_container'] | (not ONLY_CONT))]); allc['Cảng vụ'] = allc['auth'].map(tl.AUTH_LABEL)
    d2, keep = tl.top_n_other(d, 'Cảng vụ', MEAS, n=7, order=entity_order(allc, 'Cảng vụ', MEAS, LO))
    g = d2.groupby(['ky', 'Cảng vụ'], as_index=False)[MEAS].sum()
    line_chart(g, 'ky', MEAS, 'Cảng vụ', keep, MEAS_LABEL)
    if 'HCM' in AUTHS:
        st.caption('Lưu ý: các bến Cái Mép – Thị Vải chỉ có trong dữ liệu TP.HCM từ 07–08/2025, nên chuỗi TP.HCM tăng bậc ở mốc này do mở rộng phạm vi.')

    v = add_measure(scope(visits)); v['ky'] = bucket(v['arr_day'], FREQ); v = drop_partial(v, 'ky', FREQ)
    two = st.multiselect('Xem theo bến của cảng vụ (tối đa 2)', AUTHS, default=[a for a in ('HP', 'HCM') if a in AUTHS][:2] or AUTHS[:1],
                         max_selections=2, format_func=lambda a: tl.AUTH_LABEL.get(a, a)) or AUTHS[:1]
    cs = st.columns(len(two))
    for c, a in zip(cs, two):
        with c:
            st.subheader(f'{tl.AUTH_LABEL[a]}: {MEAS_LABEL.split(" (")[0]} theo bến')
            va = v[v['auth'] == a]
            order = entity_order(add_measure(visits[(visits['auth'] == a) & (visits['is_container'] | (not ONLY_CONT))]), 'terminal', MEAS, LO)
            va2, keep = tl.top_n_other(va, 'terminal', MEAS, n=7, order=order)
            stack_chart(va2.groupby(['ky', 'terminal'], as_index=False)[MEAS].sum(), 'ky', MEAS, 'terminal', keep, MEAS_LABEL, freq=FREQ)
    with st.expander('Bảng số liệu theo bến'):
        piv = v.groupby(['auth', 'terminal', 'ky'])[MEAS].sum().reset_index()
        piv['ky'] = piv['ky'].dt.strftime('%Y-%m-%d')
        table(piv.pivot_table(index=['auth', 'terminal'], columns='ky', values=MEAS, aggfunc='sum', fill_value=0).reset_index(), 'tq_ben', name='tong_quan_theo_ben')

# ================================================================ BẾN CẢNG
elif PAGE == 'Bến cảng':
    st.title('Theo dõi bến cảng')
    c1, c2 = st.columns([1, 3])
    auth = c1.selectbox('Cảng vụ', AUTHS, index=AUTHS.index('HP') if 'HP' in AUTHS else 0, format_func=lambda a: tl.AUTH_LABEL.get(a, a))
    dim_label = c1.radio('Gộp theo', ['Bến', 'Nhóm chủ bến', 'Mã CK'], horizontal=False)
    dim = {'Bến': 'terminal', 'Nhóm chủ bến': 'group', 'Mã CK': 'ticker'}[dim_label]
    va = add_measure(visits[(visits['auth'] == auth) & (visits['is_container'] | (not ONLY_CONT))])
    va = va[va[dim] != '']
    order = entity_order(va, dim, MEAS, LO)
    pick = c2.multiselect(f'Chọn {dim_label.lower()} (tối đa 8)', order, default=order[:5], max_selections=8)
    if not pick: st.info('Chọn ít nhất một mục.'); st.stop()
    v = va[(va['arr_day'] >= LO) & (va['arr_day'] <= LAST)].copy(); v['ky'] = bucket(v['arr_day'], FREQ); v = drop_partial(v, 'ky', FREQ)
    sel = v[v[dim].isin(pick)]
    order_pick = [k for k in order if k in pick]
    st.subheader(f'{MEAS_LABEL} theo {FREQ.lower()}')
    g = sel.groupby(['ky', dim], as_index=False)[MEAS].sum()
    line_chart(g, 'ky', MEAS, dim, order_pick, MEAS_LABEL)
    st.subheader(f'Thị phần trong tổng {tl.AUTH_LABEL[auth]} (%)')
    tot = v.groupby('ky')[MEAS].sum().rename('tot')
    sh = g.merge(tot, on='ky'); sh['share'] = sh[MEAS] / sh['tot']
    line_chart(sh, 'ky', 'share', dim, order_pick, 'Thị phần', yfmt='.0%')
    st.caption('Mẫu số là tổng các lượt cập bến (không tính khu neo, bến phao neo chờ) của cùng cảng vụ và cùng bộ lọc loại tàu.')

    st.divider()
    one = st.selectbox(f'Chi tiết một {dim_label.lower()}', order_pick)
    d1 = v[v[dim] == one]; last12 = va[(va[dim] == one) & (va['arr_day'] > LAST - pd.DateOffset(months=12)) & (va['arr_day'] <= LAST)]
    k = st.columns(4)
    k[0].metric('Lượt cập bến, 12 tháng', fmt_int(len(last12)))
    k[1].metric('TEU danh nghĩa, 12 tháng', fmt_int(last12['teu'].sum()))
    k[2].metric('Cỡ tàu bình quân (TEU/lượt)', fmt_int(last12.loc[last12['teu'] > 0, 'teu'].mean()))
    k[3].metric('Giờ nằm cảng (trung vị)', '–' if last12['hours_in_port'].dropna().empty else f"{last12['hours_in_port'].median():.1f}".replace('.', ','))
    a, b = st.columns(2)
    with a:
        st.markdown('**Hãng tàu ghé nhiều nhất, 12 tháng**')
        top = last12.groupby('operator', as_index=False)[MEAS].sum().sort_values(MEAS, ascending=False).head(12)
        hbar(top, 'operator', MEAS, MEAS_LABEL)
    with b:
        st.markdown('**Cỡ tàu bình quân theo kỳ (TEU/lượt)**')
        sz = d1[d1['teu'] > 0].groupby('ky', as_index=False)['teu'].mean(); sz['Bến'] = one
        line_chart(sz, 'ky', 'teu', 'Bến', [one], 'TEU/lượt', height=320)
    with st.expander('Danh sách lượt cập bến (theo bộ lọc thời gian)'):
        cols = ['arr_day', 'ship', 'operator', 'teu', 'dwt', 'terminal', 'origin', 'destination', 'hours_in_port', 'vessel_class']
        table(d1.sort_values('arr_day', ascending=False)[cols].assign(arr_day=lambda x: x['arr_day'].dt.strftime('%Y-%m-%d')), 'ben_ct', name=f'luot_cap_ben_{one}')

# ================================================================ HÃNG TÀU
elif PAGE == 'Hãng tàu':
    st.title('Theo dõi hãng tàu')
    va = add_measure(visits[visits['auth'].isin(AUTHS) & (visits['is_container'] | (not ONLY_CONT))])
    known = va[va['operator'] != '(chưa rõ hãng)']
    order_op = entity_order(known, 'operator', MEAS, LO)
    cov = 1 - (va.loc[va['arr_day'] > LAST - pd.DateOffset(months=12), 'operator'] == '(chưa rõ hãng)').mean()
    st.caption(f'Độ phủ: {cov:.0%} lượt cập bến 12 tháng gần nhất đã xác định được hãng khai thác. Phần còn lại cần tra bằng skill /cvhp-vessels.')
    v = va[(va['arr_day'] >= LO) & (va['arr_day'] <= LAST)].copy(); v['ky'] = bucket(v['arr_day'], FREQ); v = drop_partial(v, 'ky', FREQ)

    st.subheader(f'Hãng × bến, 12 tháng gần nhất ({MEAS_LABEL})')
    l12 = known[(known['arr_day'] > LAST - pd.DateOffset(months=12)) & (known['arr_day'] <= LAST)].copy()
    l12['ben'] = l12['auth'] + ' · ' + l12['terminal']
    ops = l12.groupby('operator')[MEAS].sum().sort_values(ascending=False).head(15).index.tolist()
    bens = l12[l12['operator'].isin(ops)].groupby('ben')[MEAS].sum().sort_values(ascending=False).head(14).index.tolist()
    hm = l12[l12['operator'].isin(ops) & l12['ben'].isin(bens)].groupby(['operator', 'ben'], as_index=False)[MEAS].sum()
    if not hm.empty:
        ch = alt.Chart(hm).mark_rect(stroke=SURF, strokeWidth=2).encode(
            x=alt.X('ben:N', sort=bens, title=None, axis=alt.Axis(labelAngle=-35, labelLimit=160)),
            y=alt.Y('operator:N', sort=ops, title=None, axis=alt.Axis(labelLimit=200)),
            color=alt.Color(f'{MEAS}:Q', scale=alt.Scale(range=SEQ), legend=alt.Legend(title=MEAS_LABEL, orient='right', format=',.0f')),
            tooltip=[alt.Tooltip('operator:N', title='Hãng'), alt.Tooltip('ben:N', title='Bến'), alt.Tooltip(f'{MEAS}:Q', title=MEAS_LABEL, format=',.0f')])
        st.altair_chart(base_cfg(ch, 30 * len(ops) + 90).configure_legend(orient='right', labelColor=INK2, titleColor=INK2), width='stretch')

    st.divider()
    op = st.selectbox('Chi tiết một hãng', order_op)
    vo = v[v['operator'] == op].copy(); vo['ben'] = vo['auth'] + ' · ' + vo['terminal']
    allo = va[va['operator'] == op].copy(); allo['ben'] = allo['auth'] + ' · ' + allo['terminal']
    vo2, keep = tl.top_n_other(vo, 'ben', MEAS, n=7, order=entity_order(allo, 'ben', MEAS, LO))
    st.subheader(f'{op}: {MEAS_LABEL} theo bến')
    stack_chart(vo2.groupby(['ky', 'ben'], as_index=False)[MEAS].sum(), 'ky', MEAS, 'ben', keep, MEAS_LABEL, freq=FREQ)
    st.markdown('**Đội tàu đang khai thác (12 tháng gần nhất)**')
    f12 = allo[(allo['arr_day'] > LAST - pd.DateOffset(months=12)) & (allo['arr_day'] <= LAST)]
    pat = get_lanes(*KEY)[1]
    fl = (f12.groupby(['ship_key', 'ship'], as_index=False)
          .agg(luot=('calls', 'sum'), teu=('teu', 'max'), dwt=('dwt', 'max'), ben_chinh=('ben', lambda s: s.value_counts().index[0]),
               lan_cuoi=('arr_day', 'max')).sort_values('luot', ascending=False))
    if not pat.empty: fl = fl.merge(pat[['ship_key', 'route_pattern']], on='ship_key', how='left')
    fl['lan_cuoi'] = fl['lan_cuoi'].dt.strftime('%Y-%m-%d')
    table(fl.drop(columns=['ship_key']).rename(columns={'ship': 'Tàu', 'luot': 'Lượt cập bến', 'teu': 'TEU', 'dwt': 'DWT', 'ben_chinh': 'Bến chính',
                                                         'lan_cuoi': 'Lần ghé cuối', 'route_pattern': 'Vòng tuyến hay chạy'}), 'hang_doitau', name=f'doi_tau_{op}')

# ================================================================ TÀU
elif PAGE == 'Tàu':
    st.title('Theo dõi tàu')
    master = get_master(VER, MST)
    recent = calls[calls['date'] >= LAST - pd.DateOffset(months=36)].copy()
    recent['n12'] = (recent['date'] >= LAST - pd.DateOffset(months=12)).astype(int)
    cnt = (recent.groupby(['ship_key', 'ship']).agg(n=('n12', 'sum'), cont=('is_container', 'max')).reset_index()
           .sort_values(['cont', 'n'], ascending=[False, False]).drop_duplicates('ship_key'))      # tàu container ghé nhiều 12 tháng lên đầu
    names = dict(zip(cnt['ship_key'], cnt['ship']))
    key = st.selectbox('Chọn tàu (gõ để tìm)', cnt['ship_key'].tolist(), format_func=lambda k: names.get(k, k))
    sc = tl.ship_calls(key)                                       # mọi chuyến của tàu ở mọi cảng vụ, mọi thời gian (từ kho)
    sc = sc.sort_values('date') if len(sc) else calls[calls['ship_key'] == key].sort_values('date')
    m = master[master['ship_key'] == key].iloc[0].to_dict() if (not master.empty and (master['ship_key'] == key).any()) else {}
    if not m.get('imo') and len(sc): m['imo'] = next((x for x in sc['imo'] if x), '')
    if not m.get('dwt') and len(sc): m['dwt'] = sc['dwt'].max()
    pat = get_lanes(*KEY)[1]; prow = pat[pat['ship_key'] == key] if len(pat) else pat
    k = st.columns(6)
    k[0].metric('IMO', m.get('imo') or '–'); k[1].metric('Loại tàu', tl.CLASS_LABEL.get(m.get('vessel_class', ''), m.get('vessel_class', '–')))
    k[2].metric('Hãng khai thác', (m.get('operator') or '–')[:22]); k[3].metric('TEU', fmt_int(m.get('teu')))
    k[4].metric('DWT', fmt_int(m.get('dwt'))); k[5].metric('Năm đóng', str(m.get('built') or '–')[:4])
    if len(prow): st.caption(f"Vòng tuyến hay chạy: **{prow.iloc[0]['route_pattern']}** · cảng ghé: {prow.iloc[0]['ports_called']}")
    if m.get('service'): st.caption(f"Tuyến dịch vụ (tra cứu): {m['service']}")
    b1, b2, _ = st.columns([1.3, 1.6, 4])
    if b1.button('🔎 Tra thông số tàu trực tuyến', help='IMO từ BalticShipping / VesselFinder, TEU và loại tàu từ Flexport Atlas'):
        with st.spinner('Đang tra…'):
            r = ld.lookup_vessel(key, names.get(key, key), dwt=m.get('dwt') if pd.notna(m.get('dwt')) else None, imo=str(m.get('imo') or ''))
        st.success(f"IMO {r['imo'] or '–'} · TEU {fmt_int(r['teu'])} · loại {r['vessel_class'] or '–'} · nguồn {r['source'] or 'không tìm thấy'}")
        st.cache_data.clear(); st.rerun()
    pk = sc[(sc['src'] == 'public-kh') & (sc['origin'] == '')] if len(sc) else sc
    if len(pk) and b2.button(f'🧭 Tra cảng trước / cảng kế ({min(len(pk), 25)} chuyến)', help='Gọi trang chi tiết chuyến của cảng vụ (public-kh)'):
        with st.spinner('Đang gọi trang chi tiết chuyến…'):
            n = sum(ld.fetch_details(a, g.sort_values('date', ascending=False)['call_id'].tolist(), 25) for a, g in pk.groupby('auth'))
        st.success(f'Đã tra {n} chuyến'); st.cache_data.clear(); st.rerun()

    c1, c2 = st.columns(2)
    d0 = c1.date_input('Từ ngày', (LAST - pd.DateOffset(months=3)).date()); d1 = c2.date_input('Đến ngày', (LAST + pd.Timedelta(days=2)).date())
    w = sc[(sc['date'] >= pd.Timestamp(d0)) & (sc['date'] <= pd.Timestamp(d1))]
    st.subheader('Thời gian nằm cảng')
    g = w.dropna(subset=['arrival', 'departure']).copy()
    if g.empty: st.info('Không có chuyến trọn vẹn (có cả giờ vào và giờ rời) trong khoảng ngày này.')
    else:
        g['Cảng vụ'] = g['auth'].map(tl.AUTH_LABEL); g['ben'] = g['first_berth']
        ch = alt.Chart(g).mark_bar(height=14, cornerRadius=3).encode(
            x=alt.X('arrival:T', title=None, axis=alt.Axis(format='%d/%m', grid=True)), x2='departure:T',
            y=alt.Y('ben:N', title=None, sort=alt.SortField('arrival'), axis=alt.Axis(labelLimit=200)),
            color=alt.Color('Cảng vụ:N', scale=color_scale([tl.AUTH_LABEL[a] for a in tl.AUTH_ORDER if a in set(g['auth'])][:8])),
            tooltip=[alt.Tooltip('ben:N', title='Bến'), alt.Tooltip('arrival:T', title='Vào', format='%d/%m/%Y %H:%M'),
                     alt.Tooltip('departure:T', title='Rời', format='%d/%m/%Y %H:%M'), alt.Tooltip('hours_in_port:Q', title='Giờ nằm cảng'),
                     alt.Tooltip('origin:N', title='Từ'), alt.Tooltip('destination:N', title='Đi')])
        st.altair_chart(base_cfg(ch, max(140, 30 * g['ben'].nunique() + 60)), width='stretch')

    st.subheader('Lộ trình')
    vi = tl.itinerary_module()
    rec = lambda d: d.assign(arrival=d['arrival'].dt.strftime('%Y-%m-%d %H:%M').fillna(''), departure=d['departure'].dt.strftime('%Y-%m-%d %H:%M').fillna(''))[
        ['ship', 'ship_key', 'arrival', 'departure', 'origin', 'destination', 'berths', 'first_berth', 'status']].fillna('').to_dict('records')
    oth = w[~w['auth'].isin(['HP', 'HCM'])]
    stops = vi.stops_for_ship(rec(w[w['auth'] == 'HP']), rec(w[w['auth'] == 'HCM']), vi.Geo(),
                              other_calls=rec(oth.assign(ship=oth['auth'])) if len(oth) else None)      # cột ship tạm mang mã cảng vụ
    if not stops: st.info('Không có điểm dừng trong khoảng ngày này.')
    else:
        dist = vi.Dist(); legs = vi.legs_from_stops(stops, dist); dist.save()
        nm = sum(l['nm'] or 0 for l in legs)
        st.caption(f'{len(stops)} điểm dừng, {len(legs)} chặng, khoảng {fmt_int(nm)} hải lý. Dấu ~ là điểm suy từ cảng đi/đến ghi ở Hải Phòng; '
                   'cảng nước ngoài đa số chỉ ở mức quốc gia nên vị trí và hải lý là gần đúng.')
        srows = pd.DataFrame(vi.stop_rows({'ship_key': key, 'ship': names.get(key, key)}, stops))[
            ['seq', 'port', 'precision', 'terminal', 'arrive', 'depart', 'hours_in_port', 'inferred', 'source', 'raw_name']]
        srows['hours_in_port'] = pd.to_numeric(srows['hours_in_port'], errors='coerce')      # cột lẫn số và rỗng -> Arrow báo lỗi kiểu
        a, b = st.columns([3, 2])
        with a: table(srows, 'tau_stops', height=360, name=f'lo_trinh_{key}')
        with b:
            if st.button('🗺️ Vẽ bản đồ lộ trình', width='stretch'):
                png = os.path.join(tempfile.gettempdir(), f'tracker_{key.replace(" ", "_")}.png')
                with st.spinner('Đang tính tuyến biển và vẽ…'):
                    ok = vi.render_png(names.get(key, key), stops[-40:], png)
                if ok:
                    st.image(png)
                    with open(png, 'rb') as f: st.download_button('⬇️ Tải PNG', f.read(), file_name=os.path.basename(png), key='png_dl')
                else: st.warning('Không đủ điểm có toạ độ để vẽ.')
    with st.expander('Toàn bộ chuyến của tàu (mọi thời gian)'):
        cols = ['auth', 'arrival', 'departure', 'origin', 'first_berth', 'berths', 'destination', 'hours_in_port', 'status', 'agent']
        table(sc.sort_values('date', ascending=False)[cols], 'tau_calls', name=f'chuyen_{key}')

# ================================================================ BẢNG ĐIỀU ĐỘ
elif PAGE == 'Bảng điều độ':
    st.title('Bảng điều độ')
    days = [(TODAY + pd.Timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, -8, -1)]
    tday = TODAY.strftime('%Y-%m-%d')
    c1, c2 = st.columns([1, 3])
    day = c1.selectbox('Ngày kế hoạch', days, index=days.index(tday))
    n_pull, _, errs = live_pull(AUTHS, day, day, min(TTL, 10), 0, f'Đang gọi kế hoạch ngày {day}')      # ngày đang xem: làm mới nhanh hơn
    e = tl.events_day(AUTHS, day)
    if e.empty: st.info('Các cảng vụ chưa công bố kế hoạch cho ngày này.'); st.stop()
    got = ld.coverage();
    c1.caption('Kéo lúc ' + str(pd.to_datetime(e['fetched_at']).max())[:16])
    if ONLY_CONT: e = e[e['vessel_class'].isin(['container', 'container?'])]
    e['teu'] = pd.to_numeric(e['teu'], errors='coerce')
    k = st.columns(4)
    for col, (lab, sec) in zip(k, [('Tàu vào', 'Vao'), ('Tàu rời', 'Roi'), ('Di chuyển', 'DiChuyen')]):
        s = e[e['section'] == sec]; col.metric(lab, fmt_int(len(s)), help=f'TEU danh nghĩa: {fmt_int(s["teu"].sum())} · DWT: {fmt_int(s["dwt"].sum())}')
    k[3].metric('TEU danh nghĩa vào', fmt_int(e.loc[e['section'] == 'Vao', 'teu'].sum()))
    c2.caption('Kế hoạch do cảng vụ công bố và bổ sung dần trong ngày. Ngày mai thường mới có vài dòng. Bảng này gọi thẳng trang cảng vụ mỗi khi mở.')
    show = ['auth', 'time', 'ship', 'operator', 'teu', 'dwt', 'from', 'to', 'vessel_class', 'agent']
    tabs = st.tabs(['Tàu vào', 'Tàu rời', 'Di chuyển', 'Đang ở cảng'])
    for tab, sec in zip(tabs[:3], ['Vao', 'Roi', 'DiChuyen']):
        with tab: table(e[e['section'] == sec].sort_values(['auth', 'time'])[[c for c in show if c in e]], f'dd_{sec}', name=f'dieu_do_{sec}_{day}')
    with tabs[3]:
        ip = calls[calls['auth'].isin(AUTHS) & (calls['status'] == 'no_departure') & (calls['arrival'] >= TODAY - pd.Timedelta(days=10)) & (calls['arrival'] <= TODAY + pd.Timedelta(days=1))]
        if ONLY_CONT: ip = ip[ip['is_container']]
        ip = ip.assign(ngay_o_cang=((pd.Timestamp.now() - ip['arrival']).dt.total_seconds() / 86400).round(1))
        st.caption('Tàu đã vào trong 10 ngày qua và chưa thấy kế hoạch rời. Tàu vừa rời nhưng trang cảng vụ chưa cập nhật vẫn có thể nằm trong danh sách.')
        table(ip.sort_values('arrival', ascending=False)[['auth', 'ship', 'operator', 'teu', 'dwt', 'arrival', 'origin', 'berths', 'ngay_o_cang', 'agent']], 'dd_inport', name='tau_dang_o_cang')

# ================================================================ CẢNH BÁO
elif PAGE == 'Cảnh báo':
    st.title('Cảnh báo thay đổi')
    win = st.slider('Cửa sổ so sánh (ngày)', 14, 90, 30, step=1)
    va = add_measure(visits[visits['auth'].isin(AUTHS) & (visits['is_container'] | (not ONLY_CONT)) & (visits['arr_day'] <= LAST)])
    va['ben'] = va['auth'] + ' · ' + va['terminal']
    end = LAST + pd.Timedelta(days=1); a0 = end - pd.Timedelta(days=win); b0 = a0 - pd.Timedelta(days=win)
    y1 = end - pd.Timedelta(days=365); y0 = y1 - pd.Timedelta(days=win)
    cur = va[(va['arr_day'] >= a0) & (va['arr_day'] < end)]

    st.subheader(f'1. Biến động theo bến: {win} ngày gần nhất so với kỳ trước và cùng kỳ năm trước')
    def agg(lo, hi, name): return va[(va['arr_day'] >= lo) & (va['arr_day'] < hi)].groupby('ben')[['calls', 'teu']].sum().add_suffix(name)
    mm = pd.concat([agg(a0, end, '_ky_nay'), agg(b0, a0, '_ky_truoc'), agg(y0, y1, '_nam_truoc')], axis=1).fillna(0)
    mm = mm[(mm['calls_ky_nay'] + mm['calls_ky_truoc']) >= 6]
    mm['teu_so_ky_truoc'] = (mm['teu_ky_nay'] / mm['teu_ky_truoc'].replace(0, np.nan) - 1).round(3)
    mm['teu_so_nam_truoc'] = (mm['teu_ky_nay'] / mm['teu_nam_truoc'].replace(0, np.nan) - 1).round(3)
    mm = mm.reset_index().sort_values('teu_so_ky_truoc', key=lambda s: s.abs(), ascending=False)
    table(mm[['ben', 'calls_ky_nay', 'calls_ky_truoc', 'teu_ky_nay', 'teu_ky_truoc', 'teu_so_ky_truoc', 'teu_nam_truoc', 'teu_so_nam_truoc']], 'cb_ben', height=320, name='bien_dong_ben')

    first = va.groupby('ship_key')['arr_day'].min()
    st.subheader(f'2. Tàu mới xuất hiện trong {win} ngày qua')
    new = cur[cur['ship_key'].map(first) >= a0]
    nv = (new.groupby(['ship_key', 'ship', 'operator'], as_index=False)
          .agg(teu=('teu', 'max'), luot=('calls', 'sum'), ben=('ben', lambda s: ', '.join(s.value_counts().index[:3])), lan_dau=('arr_day', 'min'))
          .sort_values('teu', ascending=False))
    nv['lan_dau'] = nv['lan_dau'].dt.strftime('%Y-%m-%d')
    st.caption('Tàu chưa từng ghé (tính từ 2019) thường là dấu hiệu tuyến dịch vụ mới hoặc hãng thay tàu cỡ khác.')
    table(nv.drop(columns=['ship_key']), 'cb_new', height=300, name='tau_moi')

    st.subheader(f'3. Tàu ngừng ghé: đều đặn trước đó, vắng trong {win} ngày qua')
    prev = va[(va['arr_day'] >= a0 - pd.Timedelta(days=90)) & (va['arr_day'] < a0)]
    pv = prev.groupby(['ship_key', 'ship', 'operator'], as_index=False).agg(luot_90_ngay_truoc=('calls', 'sum'), teu=('teu', 'max'),
                                                                           ben=('ben', lambda s: s.value_counts().index[0]), lan_cuoi=('arr_day', 'max'))
    gone = pv[(pv['luot_90_ngay_truoc'] >= 6) & (~pv['ship_key'].isin(cur['ship_key']))].sort_values('luot_90_ngay_truoc', ascending=False)
    gone['lan_cuoi'] = gone['lan_cuoi'].dt.strftime('%Y-%m-%d')
    table(gone.drop(columns=['ship_key']), 'cb_gone', height=300, name='tau_ngung_ghe')

    st.subheader('4. Tàu đổi bến chính')
    def main_berth(d):
        g = d.groupby(['auth', 'ship_key', 'terminal']).size().reset_index(name='n').sort_values('n', ascending=False)
        return g.drop_duplicates(['auth', 'ship_key']).set_index(['auth', 'ship_key'])
    nowb = main_berth(va[(va['arr_day'] >= end - pd.Timedelta(days=60)) & (va['kind'] == 'container')])
    oldb = main_berth(va[(va['arr_day'] >= end - pd.Timedelta(days=240)) & (va['arr_day'] < end - pd.Timedelta(days=60)) & (va['kind'] == 'container')])
    sw = nowb.join(oldb, lsuffix='_moi', rsuffix='_cu', how='inner')
    sw = sw[(sw['terminal_moi'] != sw['terminal_cu']) & (sw['n_moi'] >= 3) & (sw['n_cu'] >= 4)].reset_index()
    info = va.drop_duplicates('ship_key').set_index('ship_key')[['ship', 'operator', 'teu']]
    sw = sw.join(info, on='ship_key').sort_values('teu', ascending=False)
    st.caption('Bến container ghé nhiều nhất trong 60 ngày gần đây khác với 180 ngày trước đó (tối thiểu 3 và 4 lượt). Dấu hiệu hãng chuyển bến.')
    table(sw[['auth', 'ship', 'operator', 'teu', 'terminal_cu', 'n_cu', 'terminal_moi', 'n_moi']], 'cb_switch', height=300, name='tau_doi_ben')

# ================================================================ TUYẾN
elif PAGE == 'Tuyến':
    st.title('Luồng tuyến')
    lanes, patterns = get_lanes(*KEY)
    if lanes.empty: st.info('Chưa đủ dữ liệu để ghép chặng cho lựa chọn này.'); st.stop()
    st.caption('Chặng ghép trong app từ lịch các cảng vụ vừa kéo, chỉ gồm tàu container. Cảng nước ngoài đa số ở mức quốc gia. Không gồm các chặng đi/đến "ngoài vùng dữ liệu".')
    L = lanes[(lanes['month'] >= LO) & (~lanes['lane'].str.contains('ngoai vung du lieu')) & (lanes['from'] != lanes['to'])]
    mcol = 'teu_sum' if MEAS == 'teu' else 'legs'; mlab = 'TEU danh nghĩa' if MEAS == 'teu' else 'Số chặng'
    top = L.groupby('lane', as_index=False)[mcol].sum().sort_values(mcol, ascending=False)
    a, b = st.columns([2, 3])
    with a:
        st.subheader(f'Chặng lớn nhất ({mlab})'); hbar(top.head(15), 'lane', mcol, mlab)
    with b:
        order = top['lane'].tolist()
        pick = st.multiselect('Chặng theo dõi (tối đa 6)', order, default=order[:4], max_selections=6)
        g = L[L['lane'].isin(pick)].groupby(['month', 'lane'], as_index=False)[mcol].sum()
        g = g[g['month'] < LAST.to_period('M').to_timestamp()]
        st.subheader(f'{mlab} theo tháng'); line_chart(g, 'month', mcol, 'lane', [k for k in order if k in pick], mlab, height=360)
    one = st.selectbox('Hãng khai thác trên một chặng', order)
    o = L[L['lane'] == one].groupby('operator', as_index=False)[[mcol, 'ships']].sum().sort_values(mcol, ascending=False)
    hbar(o.head(12), 'operator', mcol, mlab)
    with st.expander('Vòng tuyến hay chạy của từng tàu'):
        table(patterns, 'tuyen_pattern', name='vong_tuyen_tau')

# ================================================================ DỮ LIỆU
else:
    st.title('Dữ liệu nguồn')
    st.caption('App gọi thẳng trang nguồn của từng cảng vụ và lưu vào kho riêng (cache\\live.sqlite). Ngày đã qua hơn 2 ngày coi là chốt, không kéo lại.')
    cov = ld.coverage()
    cov['Cảng vụ'] = cov['auth'].map(tl.AUTH_LABEL); cov['order'] = cov['auth'].map({a: i for i, a in enumerate(tl.AUTH_ORDER)})
    st.dataframe(cov.sort_values('order')[['Cảng vụ', 'tu_ngay', 'den_ngay', 'so_ngay', 'so_su_kien', 'keo_gan_nhat']]
                 .rename(columns={'tu_ngay': 'Từ ngày', 'den_ngay': 'Đến ngày', 'so_ngay': 'Số ngày có trong kho', 'so_su_kien': 'Số sự kiện',
                                  'keo_gan_nhat': 'Kéo từ nguồn gần nhất'}), width='stretch', hide_index=True)
    st.subheader('Kéo bù / kéo lại từ trang nguồn')
    f1, f2, f3, f4 = st.columns([2, 1, 1, 1])
    ba = f1.multiselect('Cảng vụ', ALL_AUTHS, default=AUTHS if len(AUTHS) < len(ALL_AUTHS) else ['HP'], format_func=lambda a: tl.AUTH_LABEL.get(a, a))
    bd0 = f2.date_input('Từ ngày', (TODAY - pd.Timedelta(days=30)).date(), key='bf0'); bd1 = f3.date_input('Đến ngày', TODAY.date(), key='bf1')
    again = f4.checkbox('Kéo lại cả ngày đã có', value=False)
    miss = ld.plan(ba, bd0, bd1, ttl_min=0 if again else 10 ** 7) if ba else {}
    n_miss = sum(len(v) for v in miss.values())
    st.caption(f'{n_miss} trang cần gọi' + (' (khoảng ' + fmt_int(n_miss * 0.6 / max(len(miss), 1) / 60) + ' phút)' if n_miss > 100 else ''))
    if st.button('⬇️ Kéo từ nguồn', disabled=not n_miss):
        n, _, errs = live_pull(ba, bd0, bd1, 0 if again else 10 ** 7, 0, 'Đang kéo bù từ trang nguồn')
        st.success(f'Đã kéo {n} trang' + (f', {len(errs)} lỗi' if errs else ''))
        if errs: st.write(errs[:40])
        st.cache_data.clear(); st.rerun()
    with st.expander('Khởi tạo lại kho từ lịch sử đã parse sẵn (chỉ dùng khi kho hỏng hoặc muốn nạp nhanh nhiều năm)'):
        if st.button('Nạp lịch sử có sẵn vào kho'):
            with st.spinner('Đang nạp…'): n = ld.seed_from_local()
            st.success(f'Đã nạp {fmt_int(n)} sự kiện'); st.cache_data.clear(); st.rerun()
    master = get_master(VER, MST)
    c = calls[calls['arr_day'] > LAST - pd.DateOffset(months=12)]
    cc = c[c['is_container']]
    k = st.columns(4)
    k[0].metric('Tàu trong bảng tham chiếu', fmt_int(len(master))); k[1].metric('Có IMO', fmt_int((master['imo'].fillna('').astype(str) != '').sum()))
    k[2].metric('Chuyến container 12 tháng có TEU', f"{(pd.to_numeric(cc['teu'], errors='coerce') > 0).mean():.0%}" if len(cc) else '–')
    k[3].metric('Chuyến container 12 tháng có hãng', f"{(cc['operator'] != '(chưa rõ hãng)').mean():.0%}" if len(cc) else '–')
    st.subheader('Tải dữ liệu theo bộ lọc hiện tại')
    d = scope(calls).drop(columns=['is_container'])
    st.caption(f'{len(d):,} chuyến'.replace(',', '.'))
    table(d.sort_values('arrival', ascending=False).head(5000), 'dl_calls', name='chuyen_tau_theo_bo_loc')
    st.download_button('⬇️ CSV đầy đủ', d.to_csv(index=False).encode('utf-8-sig'), file_name='chuyen_tau_day_du.csv', key='full_csv')
