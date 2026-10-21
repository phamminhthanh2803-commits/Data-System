# -*- coding: utf-8 -*-
r"""
BĐS TRACKER - theo dõi dự án bất động sản từ batdongsan.com.vn (D:\bat-dong-san), dựng 17/10/2026 theo template Port & Vessel Tracker.
Chạy:  D:\bat-dong-san\bds-tracker\Chay-app.bat   (http://localhost:8767)

GIAO DIỆN: mẫu "Genea" dùng chung (ui_genea.py: nền be sáng, thẻ biểu đồ Plotly có kỳ + nút xuất, điều hướng trên đầu trang, không sidebar).
Cấp 1 = 6 trang: Tổng quan · Giá & tin rao · Chủ đầu tư · Bản đồ · Thay đổi · Dữ liệu.
Cấp 2 (trên MỌI trang) = phạm vi: Toàn quốc · Tỉnh/thành · Dự án. Bộ lọc chung (loại hình, trạng thái) ngay dưới header.
Deep-link: ?trang=<trang>/<pham-vi>&tinh=<tỉnh>&da=<project_id>  (vd ?trang=gia/tinh&tinh=Hà Nội).

DỮ LIỆU: kho store/ của batdongsan-projects (bds_scrape.py chạy hằng ngày: danh sách 6.000+ dự án, chi tiết, thống kê tin rao bán/thuê,
lịch sử giá khu vực cấp quận area_history/, PDF báo cáo thị trường reports/). App chỉ đọc parquet/csv (bdslib.py), không gọi mạng.
"""
import json
import os
import sys
import urllib.parse

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bdslib as bl   # noqa: E402
import infra_layers as il  # noqa: E402
import ui_genea as ui  # noqa: E402


def _fresh(mod):
    """server Streamlit đang chạy giữ module cũ trong bộ nhớ (chỉ app.py được nạp lại) -> nạp lại khi file module đổi (18/10/2026)"""
    import importlib
    t = os.path.getmtime(mod.__file__)
    if getattr(mod, '_LOADED_MTIME', None) != t:
        try: mod = importlib.reload(mod)
        except (KeyError, ImportError): mod = importlib.import_module(mod.__name__)
        mod._LOADED_MTIME = t
    return mod


bl = _fresh(bl); il = _fresh(il)
import tile_proxy as tp  # noqa: E402


@st.cache_resource(show_spinner=False)
def _tile_proxy():
    """proxy tile quy hoạch (CORS) chạy 1 lần trong tiến trình, cổng 8768; xem tile_proxy.py"""
    return tp.start()


_PROXY_PORT = _tile_proxy()
try:
    _host = (st.context.headers.get('host') or 'localhost').split(':')[0]
except Exception:  # noqa: BLE001
    _host = 'localhost'
il.PROXY['base'] = f'http://{_host}:{_PROXY_PORT}' if _PROXY_PORT else None

st.set_page_config(page_title='BĐS Tracker', page_icon='🏙️', layout='wide', initial_sidebar_state='collapsed')
ui.inject_css()
TOK = ui.TOK
PER = ['1M', '3M', '6M', '1Y', 'All']
TODAY = pd.Timestamp.today().normalize()


# ================================================================ dữ liệu (cache theo chữ ký kho)
@st.cache_data(show_spinner='Đang nạp kho dự án…', max_entries=3)
def load_all(stamp):
    return bl.load_projects(), bl.load_changes(), bl.load_listings(), bl.load_area_history(), bl.load_reports(), bl.load_biggee_list(), bl.load_biggee_history(), bl.load_price_index()


STAMP = bl.stamp()
P_ALL, CHG, LS, AH, REP, BGL, BGH, PIX = load_all(STAMP)
P_ALL = bl.add_price_ref(P_ALL, BGL, LS)      # 20/10: giá tham chiếu mọi dự án (riêng / tin rao / TB quận / TB tỉnh)
if P_ALL.empty:
    st.error('Kho chưa có dữ liệu. Chạy `python D:\\bat-dong-san\\batdongsan-projects\\bds_scrape.py` trước.'); st.stop()
LAST_SCAN = pd.to_datetime(P_ALL['last_seen'], errors='coerce').max()
LS_LAST = LS['date'].max() if not LS.empty else None
ui.set_data_end(max(x for x in [LAST_SCAN, LS_LAST] if x is not None)); ui.DATA_MIN = pd.Timestamp('2018-01-01').date()      # 21/10: mốc sớm nhất toàn app (Biggee từ 2018); trước để 01/10/2026 làm date_input lỗi khi chọn 1Y/3Y ở thẻ lịch sử

# ================================================================ điều hướng + deep-link
PAGES = {'tong-quan': 'Tổng quan', 'gia': 'Giá & tin rao', 'cdt': 'Chủ đầu tư', 'ban-do': 'Bản đồ', 'thay-doi': 'Thay đổi', 'du-lieu': 'Dữ liệu'}
LEVELS = {'toan-quoc': 'Toàn quốc', 'tinh': 'Tỉnh/thành', 'du-an': 'Dự án'}


def _doc_query():
    if st.session_state.get('_nav_init'): return
    st.session_state['_nav_init'] = True
    q = st.query_params.get('trang') or ''; parts = [p for p in q.split('/') if p]
    if parts and parts[0] in PAGES: ui.set_nav('nav_page', parts[0])
    if len(parts) > 1 and parts[1] in LEVELS: ui.set_nav('nav_lv', parts[1])
    if st.query_params.get('tinh'): st.session_state['sel_tinh'] = st.query_params.get('tinh')
    if st.query_params.get('da'):
        try: st.session_state['_da_q'] = int(st.query_params.get('da'))
        except ValueError: pass


_doc_query()

# ================================================================ header
h1, h2c = st.columns([5, 2])
with h1:
    st.markdown('<div class="gn-logo"><span class="dia"></span>BĐS Tracker</div>', unsafe_allow_html=True)
with h2c:
    _, p = st.columns([1, 3])
    with p:
        with st.popover(f'Kho dữ liệu: {len(P_ALL):,} dự án ▾'.replace(',', '.'), width='stretch'):
            r = bl.runs()
            n_det = int(P_ALL['detail_at'].notna().sum()); n_ls = int(P_ALL['listing_at'].notna().sum())
            ui.note(f'Nguồn: batdongsan.com.vn (mục Dự án). Quét danh sách gần nhất <b>{LAST_SCAN:%d/%m/%Y}</b> · '
                    f'có chi tiết {n_det:,}/{len(P_ALL):,} dự án · có tin rao {n_ls:,} dự án · thống kê tin rao mới nhất '
                    f'{LS_LAST:%d/%m/%Y}'.replace(',', '.') if LS_LAST is not None else 'chưa có tin rao')
            if len(r):
                st.dataframe(r.tail(12).iloc[::-1], width='stretch', hide_index=True, height=40 + 35 * min(12, len(r)))
            st.caption('Pipeline: `python D:\\bat-dong-san\\batdongsan-projects\\bds_scrape.py` (danh sách + 300 chi tiết + 800 dự án tin rao/ngày).')

# ---- bộ lọc chung
f1, f2, f3 = st.columns([3.2, 2.6, 2.2])
with f1:
    LOAI = st.multiselect('Loại hình', [t for t in bl.TYPE_ORDER if t in set(P_ALL['type'])], default=[], key='f_loai',
                          placeholder='Mọi loại hình')
with f2:
    TT = st.multiselect('Trạng thái', [s for s in bl.STATUS_ORDER if s in set(P_ALL['status'])], default=[], key='f_tt',
                        placeholder='Mọi trạng thái')
with f3:
    st.markdown(f'<div class="gn-note" style="margin-top:34px">Dữ liệu tới <b>{ui.DATA_END:%d/%m/%Y}</b> · số căn/diện tích theo trang dự án, '
                'không phải nguồn cung thực tế.</div>', unsafe_allow_html=True)
_m = pd.Series(True, index=P_ALL.index)
if LOAI: _m &= P_ALL['type'].isin(LOAI)
if TT: _m &= P_ALL['status'].isin(TT)
P_F = P_ALL[_m]
TINH_ORDER = P_F['tinh'].value_counts().index.tolist()


# ================================================================ phạm vi
def pick_scope(level):
    if level == 'toan-quoc': return None, None
    c1, c2, c3 = st.columns([1.6, 2.6, 3])
    tinhs = TINH_ORDER or ['(chưa rõ)']
    want = st.session_state.get('sel_tinh', 'Hà Nội')
    tinh = c1.selectbox('Tỉnh/thành', tinhs, index=tinhs.index(want) if want in tinhs else 0, key='w_tinh',
                        help='Thứ tự theo số dự án (sau bộ lọc)')
    st.session_state['sel_tinh'] = tinh; st.query_params['tinh'] = tinh
    if level == 'tinh': return tinh, None
    d = P_F[P_F['tinh'] == tinh].sort_values(['status', 'units_f'], ascending=[True, False])
    if d.empty:
        c2.info('Không có dự án theo bộ lọc.'); return tinh, None
    opts = d['project_id'].tolist(); names = dict(zip(d['project_id'], d['name'] + ' · ' + d['status'].str.lower() + ' · ' + d['quan'].fillna('')))
    want = st.session_state.pop('_da_q', None) or st.session_state.get(f'sel_da_{tinh}')
    pid = c2.selectbox('Dự án', opts, index=opts.index(want) if want in opts else 0, format_func=lambda x: names.get(x, str(x)), key=f'w_da_{tinh}')
    st.session_state[f'sel_da_{tinh}'] = pid; st.query_params['da'] = str(pid)
    r = P_ALL.set_index('project_id').loc[pid]
    with c3:
        st.markdown(f'<div class="gn-note" style="margin-top:28px">{r["type"]} · {r.get("cdt") or ""} · '
                    f'<a href="{r["link"]}" target="_blank">trang nguồn ↗</a></div>', unsafe_allow_html=True)
    return tinh, pid


def scoped(level, tinh, pid):
    if level == 'toan-quoc': return P_F
    if level == 'tinh': return P_F[P_F['tinh'] == tinh]
    return P_ALL[P_ALL['project_id'] == pid]


def scope_name(level, tinh, pid):
    if level == 'toan-quoc': return 'cả nước'
    if level == 'tinh': return tinh
    return P_ALL.set_index('project_id').at[pid, 'name']


def ls_scoped(level, tinh, pid, kind):
    """thống kê tin rao của các dự án trong phạm vi + cột tinh/type"""
    if LS.empty: return LS
    d = LS[LS['kind'] == kind].merge(P_ALL[['project_id', 'name', 'tinh', 'quan', 'type', 'status']], on='project_id', how='inner')
    ids = set(scoped(level, tinh, pid)['project_id'])
    return d[d['project_id'].isin(ids)]


def kpi_projects(d):
    n = len(d); vc = d['status'].value_counts()
    units = d.loc[d['status'].isin(['Đang mở bán', 'Sắp mở bán']), 'units_f'].sum()
    lb = bl.latest_listing(LS[LS['project_id'].isin(d['project_id'])], 'ban') if not LS.empty else pd.DataFrame()
    items = [('Dự án', bl.fmt_int(n), f'{len(d["cdt"].unique())} chủ đầu tư', 0),
             ('Đang mở bán', bl.fmt_int(vc.get('Đang mở bán', 0)), f'sắp mở bán {bl.fmt_int(vc.get("Sắp mở bán", 0))}', 1),
             ('Đã bàn giao', bl.fmt_int(vc.get('Đã bàn giao', 0)), f'đang cập nhật {bl.fmt_int(vc.get("Đang cập nhật", 0))}', 0),
             ('Số căn đang/sắp mở bán', bl.fmt_int(units), f'{bl.fmt_int(d.loc[d["status"].isin(["Đang mở bán", "Sắp mở bán"]), "units_f"].notna().sum())} dự án có số căn', 0)]
    if len(lb):
        items.append(('Tin rao bán', bl.fmt_int(lb['n_total'].sum()), f'{bl.fmt_int(lb["n_7d"].sum())} tin đăng 7 ngày · {len(lb)} dự án theo dõi', 0))
        items.append(('Giá rao/m² (trung vị)', bl.fmt_num(lb['ppm2_med'].median(), 1) + ' tr', 'trung vị của trung vị từng dự án', 0))
    ui.kpi_strip(items)


def hbar_count(s, unit, key, title, help_txt=None, n=20):
    with ui.card(title, unit=unit, key=key, controls=False, help=help_txt) as cd:
        s = s.head(n)
        cd.chart(ui.fig_hbar(s, unit=unit, sign=False, nd=0), s.to_frame(unit), ten=key)


def _rgba(hex_, a):
    h = hex_.lstrip('#'); return f'rgba({int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)},{a})'


def fig_mid_band(items, unit='tr/m²', hover_nd=1, height=None):
    """Đường trung bình + DẢI CAO-THẤP MỜ đi kèm (quy ước 20/10/2026: mọi biểu đồ trung bình đều có dải).
    items = [{'name', 'mid': Series(index thời gian), 'lo': Series|None, 'hi': Series|None, 'color': hex|None, 'dash': str|None, 'width': float|None, 'band_name': str|None}]"""
    fig = go.Figure(); any_ = False
    for i, it in enumerate(items):
        mid = it['mid'].dropna() if it.get('mid') is not None else pd.Series(dtype=float)
        col = it.get('color') or ui.PALETTE[i % len(ui.PALETTE)]
        lo, hi = it.get('lo'), it.get('hi')
        if lo is not None and hi is not None:
            b = pd.concat([lo.rename('lo'), hi.rename('hi')], axis=1).dropna()
            if len(b):
                bn = it.get('band_name') or f'Thấp–Cao {it["name"]}'
                fig.add_trace(go.Scatter(x=b.index, y=b['hi'], mode='lines', line=dict(width=0.5, color=_rgba(col, 0.35)), name=bn, legendgroup=bn, showlegend=True,
                                         hovertemplate='cao %{y:,.' + str(hover_nd) + 'f}<extra>' + bn + '</extra>'))
                fig.add_trace(go.Scatter(x=b.index, y=b['lo'], mode='lines', line=dict(width=0.5, color=_rgba(col, 0.35)), fill='tonexty', fillcolor=_rgba(col, 0.13),
                                         name=bn, legendgroup=bn, showlegend=False, hovertemplate='thấp %{y:,.' + str(hover_nd) + 'f}<extra>' + bn + '</extra>'))
                any_ = True
        if len(mid):
            fig.add_trace(go.Scatter(x=mid.index, y=mid.values, mode='lines+markers' if it.get('markers') else 'lines', name=it['name'],
                                     line=dict(width=it.get('width') or 2.2, color=col, dash=it.get('dash') or 'solid'),
                                     hovertemplate='%{y:,.' + str(hover_nd) + 'f}<extra>' + it['name'] + '</extra>'))
            any_ = True
    if not any_: return None
    fig.update_layout(height=height or ui.HEIGHT, yaxis=dict(title=unit or None), hovermode='x unified')
    fig.update_xaxes(tickformat='%m/%Y', nticks=8)
    return fig


def fig_range_dots(df, name_col, mid_col, lo_col, hi_col, src_col=None, unit='tr/m²'):
    """Mỗi dự án 1 dòng: thanh thấp–cao mờ + chấm trung bình (dùng cho trang Chủ đầu tư)."""
    d = df.dropna(subset=[mid_col]).sort_values(mid_col)
    if d.empty: return None
    y = d[name_col].astype(str).str.slice(0, 40); col = ui.PALETTE[0]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=y, x=(d[hi_col] - d[lo_col]).fillna(0), base=d[lo_col].fillna(d[mid_col]), orientation='h', marker=dict(color=_rgba(col, 0.18), line=dict(width=0)),
                         name='Thấp – Cao', hovertemplate='thấp %{base:,.1f} – cao %{x:,.1f}<extra></extra>', customdata=d[hi_col]))
    fig.data[-1].hovertemplate = 'thấp %{base:,.1f} – cao %{customdata:,.1f}<extra>Thấp – Cao</extra>'
    fig.add_trace(go.Scatter(y=y, x=d[mid_col], mode='markers', marker=dict(size=9, color=col), name='Trung bình',
                             customdata=d[src_col] if src_col else None, hovertemplate='%{x:,.1f} ' + unit + ('<br>%{customdata}' if src_col else '') + '<extra>%{y}</extra>'))
    fig.update_layout(height=max(300, 80 + 26 * len(d)), barmode='overlay', xaxis=dict(title=unit), yaxis=dict(automargin=True), margin=dict(l=10, r=10, t=10, b=30))
    return fig


def fig_cat_stack(piv, unit):
    fig = ui.fig_stack(piv, unit=unit)
    if fig is not None: fig.update_layout(hovermode='x unified')
    return fig


# ================================================================ TRANG 1: TỔNG QUAN
def page_overview(level, tinh, pid, K):
    d = scoped(level, tinh, pid)
    ui.h2(f'Tổng quan · {scope_name(level, tinh, pid)}')
    if level == 'du-an': page_project(pid, K); return
    kpi_projects(d)
    if level == 'toan-quoc':
        c1, c2 = st.columns(2)
        with c1: hbar_count(d['tinh'].value_counts(), 'dự án', f'{K}_tinh', 'Dự án theo tỉnh/thành', 'Tỉnh/thành theo danh bạ batdongsan (63 tỉnh cũ).')
        with c2:
            s = d[d['status'].isin(['Đang mở bán', 'Sắp mở bán'])].groupby('tinh')['units_f'].sum().sort_values(ascending=False)
            hbar_count(s, 'căn', f'{K}_units', 'Số căn đang / sắp mở bán theo tỉnh', 'Tổng số căn ghi trên trang dự án của các dự án Đang mở bán + Sắp mở bán (dự án không có số căn tính 0).')
    else:
        c1, c2 = st.columns(2)
        with c1: hbar_count(d['quan'].fillna('(chưa rõ)').value_counts(), 'dự án', f'{K}_quan_{tinh}', f'Dự án theo quận/huyện · {tinh}')
        with c2:
            s = d[d['status'].isin(['Đang mở bán', 'Sắp mở bán'])].groupby(d['quan'].fillna('(chưa rõ)'))['units_f'].sum().sort_values(ascending=False)
            hbar_count(s, 'căn', f'{K}_units_{tinh}', f'Số căn đang / sắp mở bán theo quận/huyện · {tinh}')
    with ui.card('Loại hình × trạng thái', unit='số dự án', key=f'{K}_type', controls=False, toggles={'Hiện': ['Số dự án', 'Tỷ trọng']}) as cd:
        piv = d.pivot_table(index='type', columns='status', values='project_id', aggfunc='count', fill_value=0)
        piv = piv.reindex(index=[t for t in bl.TYPE_ORDER if t in piv.index], columns=[s for s in bl.STATUS_ORDER if s in piv.columns])
        cd.chart(ui.fig_stack(piv, unit='dự án', normalize=cd.toggle.get('Hiện') == 'Tỷ trọng'), piv, ten='loai_hinh_trang_thai')
    with ui.card('Danh sách dự án', unit=f'{len(d):,} dự án theo bộ lọc'.replace(',', '.'), key=f'{K}_list', controls=False) as cd:
        q = st.text_input('Tìm theo tên / chủ đầu tư / địa chỉ', key=f'{K}_q', placeholder='vd Vinhomes, Nam Long, Thủ Đức…')
        dd = d
        if q:
            m = dd[['name', 'cdt', 'address']].fillna('').apply(lambda c: c.str.contains(q, case=False, regex=False)).any(axis=1); dd = dd[m]
        t = bl.project_table(dd.sort_values(['status', 'units_f'], ascending=[True, False]))
        cd.table(t, ten='danh_sach_du_an', height=min(560, 40 + 35 * len(t)))


# ================================================================ TRANG dự án (1 dự án)
def page_project(pid, K):
    r = P_ALL.set_index('project_id').loc[pid]
    lb = LS[(LS['project_id'] == pid)] if not LS.empty else pd.DataFrame()
    b = lb[lb['kind'] == 'ban'].sort_values('date') if len(lb) else pd.DataFrame(); t = lb[lb['kind'] == 'thue'].sort_values('date') if len(lb) else pd.DataFrame()
    items = [('Trạng thái', r['status'], r['type'], 0), ('Số căn', bl.fmt_int(r['units_f']), f'{bl.fmt_int(r["blocks"])} tòa' if pd.notna(r.get('blocks')) else '', 0),
             ('Diện tích đất', bl.fmt_num(r['area_f'] / 10000, 2) + ' ha' if pd.notna(r['area_f']) else '–', r.get('legal') or '', 0),
             ('Giá niêm yết', r.get('price_text') or '–', 'theo trang dự án', 0)]
    if len(b):
        x = b.iloc[-1]
        items.append(('Tin rao bán', bl.fmt_int(x['n_total']), f'trung vị {bl.fmt_num(x["ppm2_med"], 1)} tr/m² · {bl.fmt_int(x["n_7d"])} tin 7 ngày', 0))
    if len(t):
        x = t.iloc[-1]; items.append(('Tin cho thuê', bl.fmt_int(x['n_total']), f'trung vị {bl.fmt_num(x["price_med"], 1)} tr/tháng', 0))
    ui.kpi_strip(items)
    c1, c2 = st.columns([3, 2])
    with c1:
        with ui.card('Giá rao bán / m²', unit='triệu đồng/m², trung vị 20 tin mới nhất', key=f'{K}_ppm2_{pid}', periods=PER, default='3M',
                     help='Dải = phân vị 25–75 của 20 tin rao mới nhất trên trang dự án mỗi ngày.') as cd:
            if len(b):
                w = b.set_index('date')[['ppm2_p25', 'ppm2_p75', 'ppm2_med']]; w.index.name = 'Ngày'
                fig = ui.fig_band(cd.cut(w), 'ppm2_p25', 'ppm2_p75', mid='ppm2_med', unit='tr/m²', name_band='P25–P75')
                if fig is not None and len(w) < 3: fig.update_traces(mode='lines+markers', selector=dict(mode='lines'))
                cd.chart(fig, w.rename(columns={'ppm2_p25': 'P25', 'ppm2_p75': 'P75', 'ppm2_med': 'Trung vị'}), ten=f'gia_m2_pj{pid}')
            else: cd.empty('Chưa thống kê tin rao của dự án này')
    with c2:
        with ui.card('Số tin rao', unit='tin trên batdongsan', key=f'{K}_ntin_{pid}', periods=PER, default='3M', compact=True) as cd:
            if len(lb):
                w = lb.pivot_table(index='date', columns='kind', values='n_total').rename(columns={'ban': 'Bán', 'thue': 'Cho thuê'}); w.index.name = 'Ngày'
                cd.chart(ui.fig_line(cd.cut(w), unit='tin', zero=True, markers=True, hover_nd=0), w, ten=f'so_tin_pj{pid}')
            else: cd.empty()
    biggee_project_card(pid, K)
    with ui.card('Thông tin dự án', unit='theo trang batdongsan', key=f'{K}_info_{pid}', controls=False) as cd:
        info = {'Địa chỉ': r.get('d_address') or r.get('address'), 'Chủ đầu tư': r.get('cdt'), 'Pháp lý': r.get('legal'),
                'Bàn giao': r.get('handover'), 'Loại hình bán/thuê': r.get('sale_types'), 'Toạ độ': f'{r["lat"]:.5f}, {r["lng"]:.5f}' if pd.notna(r.get('lat')) else None,
                'Thuộc tính khác': r.get('attrs_json'), 'Cập nhật chi tiết': r.get('detail_at'), 'Lần đầu thấy': f'{r["first_seen"]:%d/%m/%Y}' if pd.notna(r['first_seen']) else None}
        cd.table(pd.DataFrame({'Mục': list(info), 'Giá trị': [str(v) if v is not None and v == v else '–' for v in info.values()]}), ten=f'thong_tin_pj{pid}')
        if r.get('desc'):
            with cd.body(): st.markdown(f'<div class="gn-note">{str(r["desc"])[:1500]}…</div>', unsafe_allow_html=True)
    ch = CHG[CHG['project_id'] == pid].sort_values('date', ascending=False)
    if len(ch):
        with ui.card('Lịch sử thay đổi', unit='trạng thái, số căn, tên…', key=f'{K}_chg_{pid}', controls=False) as cd:
            cd.table(ch[['date', 'field', 'old', 'new']].rename(columns={'date': 'Ngày', 'field': 'Trường', 'old': 'Cũ', 'new': 'Mới'}), ten=f'thay_doi_pj{pid}')
    if PG != 'ban-do': page_project_map(pid, f'{K}_pj')      # 20/10 PV2: tab Dự án cũng cần bản đồ (trang Bản đồ đã tự gọi, không vẽ 2 lần)


def biggee_project_card(pid, K):
    """thẻ 'Giá dự án theo tháng' (20/10/2026): Biggee (gói thành viên, tr/m²) + chỉ số TỰ TÍNH cùng phương pháp (price_index.py: P50, dải P25–P90)
    từ tin rao batdongsan ta crawl; lịch sử trước 10/2026 chỉ có Biggee, từ 10/2026 có cả hai để đối chiếu rồi thay dần."""
    h = BGH[BGH['project_id'] == pid].sort_values('month').assign(month=lambda d: d['month'].clip(upper=TODAY)) if not BGH.empty else pd.DataFrame()   # tháng hiện tại = tới hôm nay
    row = BGL[BGL['project_id'] == pid] if not BGL.empty else pd.DataFrame()
    px_ = PIX[PIX['project_id'] == pid].sort_values('month').assign(month=lambda d: d['month'].clip(upper=TODAY)) if not PIX.empty else pd.DataFrame()
    # 20/10 PV2: BẮT BUỘC luôn có lịch sử -> không có chuỗi riêng thì lấy chuỗi quận / tỉnh / toàn quốc từ Biggee
    pr_ = P_ALL.set_index('project_id').loc[pid]; area_w = area_lbl = None; area_n = 0
    if h.empty:
        for tinh_, quan_ in [(pr_.get('tinh'), pr_.get('quan')), (pr_.get('tinh'), None), (None, None)]:
            area_w, area_lbl, area_n = bl.area_history(BGH, BGL, tinh_, quan_)
            if area_w is not None and len(area_w) >= 3: break
    if h.empty and row.empty and px_.empty and area_w is None: return
    unit = 'triệu đồng/m², trung vị đơn giá rao của tin so sánh (Biggee · tự tính)'
    if h.empty and area_w is not None:
        y = area_w.iloc[-1]; unit += f' · dự án chưa có giá riêng → {area_lbl}: TB {bl.fmt_num(y["tb"], 0)} (thấp {bl.fmt_num(y["lo"], 0)} – cao {bl.fmt_num(y["hi"], 0)}), {area_n} DA'
    if len(row):
        x = row.iloc[0]
        unit += f' · Biggee hiện {bl.fmt_num(x["price_avg"], 0)} ({bl.fmt_num(x["price_lo"], 0)}–{bl.fmt_num(x["price_hi"], 0)}) · 1 năm {bl.fmt_num(x["change_pct"], 1)}%'
    if len(px_):
        y = px_.iloc[-1]; unit += f' · tự tính {bl.fmt_num(y["p50"], 0)} ({bl.fmt_num(y["p25"], 0)}–{bl.fmt_num(y["p90"], 0)}, n={int(y["n"])})'
    dm = ui.DATA_MIN; ui.DATA_MIN = pd.Timestamp('2018-01-01').date()      # kho batdongsan bắt đầu 10/2026 nhưng Biggee có từ 2018 -> mở khung ngày cho thẻ này
    with ui.card('Giá dự án theo tháng', unit=unit, key=f'{K}_bg_{pid}', periods=['1Y', '3Y', 'All'], default='All',
                 help='Cùng một phương pháp (đã kiểm chứng BIGGEE.md §7): trung vị (P50) đơn giá rao của các tin so sánh đăng trong ~4 tháng, thấp = P25, cao = P90; '
                      'không phải giá giao dịch. Biggee = chuỗi kéo từ biggee.vn (gói thành viên, từ 2018); Tự tính = price_index.py trên tin rao batdongsan ta crawl từ 10/2026. '
                      'Dải mờ = thấp–cao: của chuỗi tự tính (P25–P90) khi có, nếu không là P25–P90 các dự án trong quận/tỉnh theo tháng.') as cd:
        if h.empty and px_.empty and area_w is None: cd.empty('Chưa có lịch sử tháng cho dự án này')
        else:
            items = []; export = {}
            band_lo = band_hi = None; band_name = None
            if len(px_):
                band_lo, band_hi, band_name = px_.set_index('month')['p25'], px_.set_index('month')['p90'], 'Thấp–Cao tự tính (P25–P90)'
            else:
                aw_, al_, an_ = bl.area_history(BGH, BGL, pr_.get('tinh'), pr_.get('quan'))
                if aw_ is None or len(aw_) < 3: aw_, al_, an_ = bl.area_history(BGH, BGL, pr_.get('tinh'), None)
                if aw_ is not None:
                    aw_ = aw_.copy(); aw_.index = pd.DatetimeIndex(aw_.index.where(aw_.index <= TODAY, TODAY)); band_lo, band_hi, band_name = aw_['lo'], aw_['hi'], f'Thấp–Cao {al_} (P25–P90, {an_} DA)'
            if len(h):
                hm = h.set_index('month')
                items.append({'name': 'Biggee', 'mid': hm['ppm2'], 'lo': band_lo, 'hi': band_hi, 'band_name': band_name, 'color': ui.PALETTE[0]})
                items.append({'name': 'Biggee · TB quận', 'mid': hm['dist_ppm2'], 'dash': 'dash', 'width': 1.4, 'color': ui.PALETTE[1]})
                export.update({'Biggee': hm['ppm2'], 'Biggee · TB quận': hm['dist_ppm2']})
            elif area_w is not None:
                aw = area_w.copy(); aw.index = pd.DatetimeIndex(aw.index.where(aw.index <= TODAY, TODAY), name='Tháng')
                items.append({'name': f'TB {area_lbl}', 'mid': aw['tb'], 'lo': aw['lo'], 'hi': aw['hi'], 'band_name': f'Thấp–Cao {area_lbl} (P25–P90)', 'color': ui.PALETTE[0]})
                export.update({f'TB {area_lbl}': aw['tb'], f'Thấp {area_lbl}': aw['lo'], f'Cao {area_lbl}': aw['hi']})
            if len(px_):
                pm = px_.set_index('month')
                items.append({'name': 'Tự tính P50', 'mid': pm['p50'], 'lo': None if len(h) else pm['p25'], 'hi': None if len(h) else pm['p90'], 'band_name': 'Thấp–Cao tự tính (P25–P90)',
                              'color': ui.PALETTE[2] if len(h) else ui.PALETTE[0], 'markers': len(pm) < 4})
                export.update({'Tự tính P50': pm['p50'], 'Tự tính P25': pm['p25'], 'Tự tính P90': pm['p90']})
            if band_lo is not None and band_name and band_name not in export: export[band_name.replace('Thấp–Cao', 'Thấp')] = band_lo; export[band_name.replace('Thấp–Cao', 'Cao')] = band_hi
            w = pd.DataFrame(export).sort_index(); w.index.name = 'Tháng'
            cut_items = [{**it, 'mid': cd.cut(it['mid'].to_frame())[it['mid'].name or 0] if it.get('mid') is not None else None,
                          'lo': cd.cut(it['lo'].to_frame()).iloc[:, 0] if it.get('lo') is not None else None,
                          'hi': cd.cut(it['hi'].to_frame()).iloc[:, 0] if it.get('hi') is not None else None} for it in items]
            fig = fig_mid_band(cut_items, unit='tr/m²')
            note = ' · '.join(x for x in [f'Biggee: {str(h["slug"].iloc[0])} · {len(h)} tháng' if len(h) else (f'chưa có chuỗi riêng: dùng {area_lbl} ({area_n} dự án Biggee, {len(area_w)} tháng)' if area_w is not None else ''), f'tự tính: {len(px_)} tháng, n mới nhất {int(px_.iloc[-1]["n"])} tin' if len(px_) else '', f'dải: {band_name}' if band_name else ''] if x)
            cd.chart(fig, w, ten=f'gia_thang_pj{pid}', note_text=note)
    ui.DATA_MIN = dm


def biggee_list_card(level, tinh, K):
    """thẻ 'Bảng giá căn hộ Biggee': toàn quốc = theo quận/huyện hoặc dự án; tỉnh = từng dự án (giá TB, biến động 1 năm, tỷ suất)"""
    if BGL.empty: return
    d = BGL if level == 'toan-quoc' else BGL[BGL['tinh'] == tinh]
    if d.empty: return
    with ui.card('Bảng giá căn hộ Biggee', unit=f'{len(d):,} dự án · tr/m² · biến động % 1 năm · tỷ suất cho thuê %'.replace(',', '.'), key=f'{K}_bgl', controls=False,
                 toggles={'Xem': ['Quận/huyện', 'Dự án']} if level == 'toan-quoc' else None,
                 help='Bảng giá căn hộ toàn quốc của Biggee (ước tính mô hình theo tin rao), bản mới nhất đã nạp. Ghép với dự án batdongsan theo tên + tỉnh (apart_match.csv).') as cd:
        if level == 'toan-quoc' and cd.toggle.get('Xem', 'Quận/huyện') == 'Quận/huyện':
            g = d.groupby(['tinh', 'district']).agg(n=('slug', 'size'), gia_tb=('price_avg', 'median'), bien_dong=('change_pct', 'median'), ty_suat=('yield_pct', 'median')).reset_index()
            g = g.sort_values('n', ascending=False).rename(columns={'tinh': 'Tỉnh', 'district': 'Quận/huyện', 'n': 'Số dự án', 'gia_tb': 'Giá TB (trung vị)', 'bien_dong': 'Biến động 1N %', 'ty_suat': 'Tỷ suất %'})
            cd.table(g.round(1), ten='biggee_theo_quan', height=520)
        else:
            t = d.sort_values('price_avg', ascending=False)[['name', 'tinh', 'district', 'ward', 'price_lo', 'price_hi', 'price_avg', 'change_pct', 'yield_pct', 'project_id', 'date']]
            t = t.rename(columns={'name': 'Dự án', 'tinh': 'Tỉnh', 'district': 'Quận/huyện', 'ward': 'Phường', 'price_lo': 'Thấp', 'price_hi': 'Cao', 'price_avg': 'TB',
                                  'change_pct': 'Biến động 1N %', 'yield_pct': 'Tỷ suất %', 'project_id': 'ID batdongsan', 'date': 'Ngày'})
            cd.table(t.round(1), ten='biggee_bang_gia', height=520)


# ================================================================ TRANG 2: GIÁ & TIN RAO
def page_price(level, tinh, pid, K):
    ui.h2(f'Giá & tin rao · {scope_name(level, tinh, pid)}')
    if level == 'du-an':
        if LS.empty: ui.card_empty('Giá & tin rao', note_text='Chưa có thống kê tin rao. Chạy bds_scrape.py --listings.'); return
        page_project(pid, K); return
    if LS.empty: ui.card_empty('Giá & tin rao', note_text='Chưa có thống kê tin rao. Chạy bds_scrape.py --listings.')
    else: listing_cards(level, tinh, pid, K)
    area_card(level, tinh, K)
    biggee_list_card(level, tinh, K)


def area_card(level, tinh, K):
    """thẻ 'Lịch sử giá khu vực (batdongsan)': dòng tóm tắt widget Lịch sử giá cấp quận (% 1 năm, khoảng giá tham khảo, số tin).
    Toàn quốc = bảng quận × % 1 năm; Tỉnh = cột ngang theo quận + bảng."""
    title = 'Lịch sử giá khu vực (batdongsan)'
    if AH.empty: ui.card_empty(title, note_text='Chưa có dữ liệu. Chạy bds_scrape.py --area-history.'); return
    types = [t for t in bl.AREA_TYPE_ORDER if t in set(AH['type'])] or ['Căn hộ chung cư']
    with ui.card(title, unit='% thay đổi giá rao trong 1 năm qua theo quận/huyện · khoảng giá tham khảo · số tin', key=f'{K}_area', controls=False,
                 chips=types, chip_default='Căn hộ chung cư', toggles={'Loại tin': ['Bán', 'Cho thuê']},
                 help='Dòng tóm tắt "Giá bán đã tăng x% trong 1 năm qua" và bảng Thông tin (khoảng giá, diện tích phổ biến) trên trang tìm kiếm '
                      'cấp quận của batdongsan.com.vn: giá RAO, không phải giá giao dịch. Biểu đồ đầy đủ theo quý cần đăng nhập KYC nên không lấy. '
                      'Mỗi trang quận × loại × bán/thuê lấy lại ~2–3 tuần/lần (400 trang/ngày).') as cd:
        kind = 'ban' if cd.toggle.get('Loại tin', 'Bán') == 'Bán' else 'thue'
        d = bl.latest_area(AH, cd.chip, kind)
        if level == 'tinh' and len(d): d = d[d['city'] == tinh]
        if d.empty: cd.empty(note_text='Chưa lấy trang nào cho loại này (bán: 6 loại hình; cho thuê: không có đất nền / đất).'); return
        unit = d['price_unit'].dropna().mode(); unit = unit.iloc[0] if len(unit) else ('tr/m²' if kind == 'ban' else 'tr/tháng')
        t = d.sort_values('pct_1y', ascending=False)[['city', 'district', 'pct_1y', 'price_lo', 'price_hi', 'area_lo', 'area_hi', 'n_total', 'date', 'url']]
        t = t.rename(columns={'city': 'Tỉnh/thành', 'district': 'Quận/huyện', 'pct_1y': '% 1 năm', 'price_lo': f'Giá từ ({unit})', 'price_hi': f'Giá đến ({unit})',
                              'area_lo': 'DT từ (m²)', 'area_hi': 'DT đến (m²)', 'n_total': 'Số tin', 'date': 'Ngày lấy', 'url': 'Trang nguồn'})
        t['Ngày lấy'] = t['Ngày lấy'].dt.strftime('%d/%m/%Y')
        cfg = {'Trang nguồn': st.column_config.LinkColumn('Nguồn', display_text='mở ↗')}
        if level == 'tinh':
            s = d.set_index('district')['pct_1y'].dropna().sort_values(ascending=False)
            tt = t.drop(columns=['Tỉnh/thành'])
            cd.chart(ui.fig_hbar(s, unit='% 1 năm', sign=True, nd=1), tt, ten=f'lich_su_gia_{ui.slug(tinh)[:20]}',
                     note_text=f'{len(d)} quận/huyện · {int(d["n_total"].fillna(0).sum()):,} tin rao'.replace(',', '.'))
            with cd.body(): st.dataframe(tt.round(1), width='stretch', hide_index=True, height=min(420, 40 + 35 * len(tt)), column_config=cfg)
        else:
            with cd.body(): st.dataframe(t.round(1), width='stretch', hide_index=True, height=560, column_config=cfg)
            cd.export(t, ten='lich_su_gia_khu_vuc')
            ui.note(f'{len(d)} quận/huyện · {d["city"].nunique()} tỉnh · lấy từ {d["date"].min():%d/%m/%Y} đến {d["date"].max():%d/%m/%Y} · '
                    f'tăng {int((d["pct_1y"] > 0).sum())} · giảm {int((d["pct_1y"] < 0).sum())} quận')


def listing_cards(level, tinh, pid, K):
    kind_lab = {'ban': 'Bán', 'thue': 'Cho thuê'}
    with ui.card('Giá rao / m² trung vị theo ' + ('tỉnh/thành' if level == 'toan-quoc' else 'quận/huyện'),
                 unit='triệu đồng/m² (bán) · triệu đồng/m²/tháng (thuê)', key=f'{K}_ppm2_geo', controls=False, chips=list(kind_lab.values()),
                 help='Mỗi dự án = trung vị 20 tin mới nhất; cột = trung vị các dự án trong khu vực, lần thống kê gần nhất. Chỉ khu vực ≥ 3 dự án.') as cd:
        kind = 'ban' if cd.chip == 'Bán' else 'thue'
        d = bl.latest_listing(ls_scoped(level, tinh, pid, kind), kind)
        g = 'tinh' if level == 'toan-quoc' else 'quan'
        if len(d):
            gg = d.groupby(d[g].fillna('(chưa rõ)')).agg(med=('ppm2_med', 'median'), lo=('ppm2_p25', 'median'), hi=('ppm2_p75', 'median'), n=('project_id', 'count'))
            gg = gg[gg['n'] >= 3].sort_values('med', ascending=False).head(25).reset_index().rename(columns={g: 'khu_vuc'})
            gg['src'] = gg['n'].map(lambda n: f'{n} dự án · dải = trung vị P25–P75 của các dự án')
            fig = fig_range_dots(gg, 'khu_vuc', 'med', 'lo', 'hi', src_col='src', unit='tr/m²')      # 20/10: biểu đồ trung bình luôn kèm dải thấp–cao mờ
            cd.chart(fig, gg.rename(columns={'khu_vuc': 'Khu vực', 'med': 'Trung vị', 'lo': 'P25', 'hi': 'P75', 'n': 'Số dự án'}).drop(columns='src'), ten='gia_m2_khu_vuc', height=fig.layout.height if fig is not None else None)
        else: cd.empty()
    c1, c2 = st.columns(2)
    with c1:
        with ui.card('Giá rao bán / m² theo tuần', unit='triệu đồng/m², 6 khu vực nhiều dự án nhất', key=f'{K}_ppm2_w', periods=PER, default='3M', compact=True) as cd:
            d = ls_scoped(level, tinh, pid, 'ban'); g = 'tinh' if level == 'toan-quoc' else 'quan'
            if len(d):
                top = d.groupby('project_id')[g].first().value_counts().head(6).index.tolist()
                dt = d[d[g].isin(top)]
                w = bl.weekly(dt, [g]); w = w.reindex(columns=[t for t in top if t in w.columns])
                wl = bl.weekly(dt, [g], val='ppm2_p25'); wh = bl.weekly(dt, [g], val='ppm2_p75')      # dải mờ = trung vị P25 / P75 các dự án trong khu vực
                items = [{'name': str(c), 'mid': cd.cut(w[[c]]).iloc[:, 0], 'lo': cd.cut(wl[[c]]).iloc[:, 0] if c in wl else None, 'hi': cd.cut(wh[[c]]).iloc[:, 0] if c in wh else None,
                          'band_name': f'Thấp–Cao {c} (P25–P75)', 'markers': True, 'color': ui.PALETTE[i % len(ui.PALETTE)]} for i, c in enumerate(w.columns)]
                exp = pd.concat({'Trung vị': w, 'P25': wl.reindex(columns=w.columns), 'P75': wh.reindex(columns=w.columns)}, axis=1)
                cd.chart(fig_mid_band(items, unit='tr/m²'), exp, ten='gia_m2_tuan')
            else: cd.empty()
    with c2:
        with ui.card('Số tin rao bán theo tuần', unit='tổng tin của các dự án theo dõi', key=f'{K}_ntin_w', periods=PER, default='3M', compact=True) as cd:
            d = ls_scoped(level, tinh, pid, 'ban'); g = 'tinh' if level == 'toan-quoc' else 'quan'
            if len(d):
                top = d.groupby('project_id')[g].first().value_counts().head(6).index.tolist()
                w = bl.weekly(d[d[g].isin(top)], [g], val='n_total', how='sum'); w = w.reindex(columns=[t for t in top if t in w.columns])
                cd.chart(ui.fig_line(cd.cut(w), unit='tin', zero=True, markers=True, hover_nd=0), w, ten='so_tin_tuan')
            else: cd.empty()
    with ui.card('Dự án theo tin rao', unit='lần thống kê gần nhất của mỗi dự án', key=f'{K}_top', controls=False, chips=list(kind_lab.values()),
                 toggles={'Xếp theo': ['Số tin', 'Tin 7 ngày', 'Giá/m²']}) as cd:
        kind = 'ban' if cd.chip == 'Bán' else 'thue'
        d = bl.latest_listing(ls_scoped(level, tinh, pid, kind), kind)
        if len(d):
            col = {'Số tin': 'n_total', 'Tin 7 ngày': 'n_7d', 'Giá/m²': 'ppm2_med'}[cd.toggle.get('Xếp theo', 'Số tin')]
            t = d.sort_values(col, ascending=False)[['name', 'tinh', 'quan', 'type', 'status', 'n_total', 'n_7d', 'n_30d', 'ppm2_med', 'ppm2_p25', 'ppm2_p75', 'price_med', 'area_med', 'date', 'project_id']]
            t = t.rename(columns={'name': 'Dự án', 'tinh': 'Tỉnh', 'quan': 'Quận/huyện', 'type': 'Loại', 'status': 'Trạng thái', 'n_total': 'Số tin', 'n_7d': 'Tin 7 ngày',
                                  'n_30d': 'Tin 30 ngày', 'ppm2_med': 'Giá/m² TV', 'ppm2_p25': 'P25', 'ppm2_p75': 'P75', 'price_med': 'Giá TV (tỷ / tr/tháng)', 'area_med': 'DT TV', 'date': 'Ngày', 'project_id': 'ID'})
            cd.table(t.head(300).round(1), ten='du_an_theo_tin_rao', height=520)
        else: cd.empty()


# ================================================================ TRANG 3: CHỦ ĐẦU TƯ
def page_investors(level, tinh, pid, K):
    d = scoped(level, tinh, pid)
    ui.h2(f'Chủ đầu tư · {scope_name(level, tinh, pid)}')
    if level == 'du-an': page_project(pid, K); return
    dd = d[d['cdt'] != '(chưa rõ)']
    ui.note(f'{len(dd):,}/{len(d):,} dự án có tên chủ đầu tư (tên theo trang batdongsan, chưa chuẩn hoá – cùng tập đoàn có thể nhiều pháp nhân).'.replace(',', '.'))
    opts = dd['cdt'].value_counts().index.tolist()
    if not opts: ui.card_empty('Chủ đầu tư', note_text='Chưa có dự án nào có tên chủ đầu tư trong phạm vi này.'); return
    c = st.selectbox('Chọn chủ đầu tư', opts, key=f'{K}_cdt_sel', format_func=lambda x: f'{x} ({int((dd["cdt"] == x).sum())} dự án)')
    investor_cards(dd[dd['cdt'] == c].copy(), c, K)
    st.markdown('<div class="gn-h2" style="margin-top:18px">Tổng quan chủ đầu tư</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1: hbar_count(dd['cdt'].value_counts(), 'dự án', f'{K}_cdt_n', 'Chủ đầu tư nhiều dự án nhất')
    with c2:
        s_ = dd[dd['status'].isin(['Đang mở bán', 'Sắp mở bán'])].groupby('cdt')['units_f'].sum().sort_values(ascending=False)
        hbar_count(s_, 'căn', f'{K}_cdt_u', 'Chủ đầu tư theo số căn đang / sắp mở bán')
    with ui.card('Bảng chủ đầu tư', unit='số dự án theo trạng thái, số căn, giá tham chiếu trung vị và dải thấp–cao các dự án', key=f'{K}_cdt_tbl', controls=False) as cd:
        g = dd.groupby('cdt').agg(**{'Dự án': ('project_id', 'count'), 'Đang mở bán': ('status', lambda s: (s == 'Đang mở bán').sum()),
                                     'Sắp mở bán': ('status', lambda s: (s == 'Sắp mở bán').sum()), 'Đã bàn giao': ('status', lambda s: (s == 'Đã bàn giao').sum()),
                                     'Số căn (tổng)': ('units_f', 'sum'), 'Diện tích (ha)': ('area_f', lambda s: s.sum() / 10000),
                                     'Giá TC trung vị (tr/m²)': ('ref_ppm2', 'median'), 'Thấp nhất': ('ref_lo', 'min'), 'Cao nhất': ('ref_hi', 'max'),
                                     'Tỉnh': ('tinh', lambda s: ', '.join(s.value_counts().head(4).index))}).sort_values('Dự án', ascending=False)
        g.index.name = 'Chủ đầu tư'
        cd.table(g.round(1), ten='chu_dau_tu', height=520)


def investor_cards(sub: pd.DataFrame, c: str, K: str):
    """khối 1 chủ đầu tư (20/10/2026): KPI · giá từng dự án (chấm TB + thanh thấp–cao mờ) · lịch sử giá các dự án (đường từng dự án + trung vị CĐT với dải mờ) · bảng dự án"""
    kk = f'{K}_cdt_{abs(hash(c)) % 10**8}'
    n_open = int(sub['status'].isin(['Đang mở bán', 'Sắp mở bán']).sum()); own = int((sub['ref_src'] == 'Biggee dự án').sum() + (sub['ref_src'] == 'Tin rao batdongsan').sum())
    ui.kpi_strip([('Dự án', bl.fmt_int(len(sub)), f'{n_open} đang/sắp mở bán', 0), ('Số căn', bl.fmt_int(sub['units_f'].sum()), f'{bl.fmt_int(sub["units_f"].count())} dự án có số căn', 0),
                  ('Giá tham chiếu trung vị', bl.fmt_num(sub['ref_ppm2'].median(), 1) + ' tr/m²', f'thấp {bl.fmt_num(sub["ref_lo"].min(), 0)} – cao {bl.fmt_num(sub["ref_hi"].max(), 0)}', 0),
                  ('Có giá riêng', f'{own}/{len(sub)}', 'còn lại dùng TB quận/tỉnh', 0)])
    c1, c2 = st.columns([3, 2])
    with c1:
        with ui.card('Giá từng dự án của chủ đầu tư', unit='tr/m²: chấm = giá tham chiếu, thanh mờ = thấp – cao', key=f'{kk}_rng', controls=False,
                     help='Giá tham chiếu theo thứ tự ưu tiên: Biggee dự án (P50, dải P25–P90) → tin rao batdongsan (trung vị, P25–P75) → TB quận → TB tỉnh (cột Nguồn giá trong bảng).') as cd:
            fig = fig_range_dots(sub.assign(_lbl=sub['name'] + ' · ' + sub['quan'].fillna('')), '_lbl', 'ref_ppm2', 'ref_lo', 'ref_hi', src_col='ref_src')
            t = sub.sort_values('ref_ppm2', ascending=False)[['name', 'tinh', 'quan', 'status', 'ref_ppm2', 'ref_lo', 'ref_hi', 'ref_src']].rename(
                columns={'name': 'Dự án', 'tinh': 'Tỉnh', 'quan': 'Quận/huyện', 'status': 'Trạng thái', 'ref_ppm2': 'Giá TC', 'ref_lo': 'Thấp', 'ref_hi': 'Cao', 'ref_src': 'Nguồn giá'})
            if fig is not None: cd.chart(fig, t, ten=f'gia_du_an_cdt', height=fig.layout.height)
            else: cd.empty()
    with c2:
        with ui.card('Loại hình × trạng thái', unit='số dự án của chủ đầu tư', key=f'{kk}_mix', controls=False) as cd:
            piv = sub.pivot_table(index='type', columns='status', values='project_id', aggfunc='count', fill_value=0)
            if len(piv): cd.chart(fig_cat_stack(piv, 'dự án'), piv, ten='loai_hinh_cdt')
            else: cd.empty()
    # lịch sử giá các dự án của CĐT
    hh = BGH[BGH['project_id'].isin(sub['project_id'])].copy() if not BGH.empty else pd.DataFrame()
    dm = ui.DATA_MIN; ui.DATA_MIN = pd.Timestamp('2018-01-01').date()
    with ui.card('Lịch sử giá các dự án của chủ đầu tư', unit='tr/m² theo tháng (Biggee): đường mảnh = từng dự án, đường đậm = trung vị các dự án, dải mờ = thấp–cao (P25–P90) các dự án',
                 key=f'{kk}_hist', periods=['1Y', '3Y', 'All'], default='All',
                 help='Chuỗi tháng Biggee của từng dự án (trung vị giá rao tin so sánh). Dự án không có chuỗi riêng không vẽ; nếu không dự án nào có, dùng chuỗi tỉnh/quận nơi CĐT có nhiều dự án nhất.') as cd:
        items = []; export = {}
        if len(hh):
            hh = hh.merge(sub[['project_id', 'name', 'units_f']], on='project_id'); hh['month'] = hh['month'].clip(upper=TODAY)
            piv = hh.pivot_table(index='month', columns='name', values='ppm2', aggfunc='median').sort_index()
            agg = piv.agg(['median', lambda x: x.quantile(.25), lambda x: x.quantile(.9)], axis=1); agg.columns = ['med', 'lo', 'hi']
            top = hh.groupby('name')['units_f'].max().sort_values(ascending=False).head(8).index
            for i, nm in enumerate(top):
                items.append({'name': str(nm)[:36], 'mid': piv[nm], 'width': 1.1, 'color': ui.PALETTE[(i + 2) % len(ui.PALETTE)]}); export[str(nm)] = piv[nm]
            items.append({'name': f'Trung vị {len(piv.columns)} dự án', 'mid': agg['med'], 'lo': agg['lo'], 'hi': agg['hi'], 'band_name': 'Thấp–Cao các dự án (P25–P90)', 'color': ui.PALETTE[0], 'width': 2.6})
            export.update({'Trung vị': agg['med'], 'Thấp (P25)': agg['lo'], 'Cao (P90)': agg['hi']}); note = f'{len(piv.columns)}/{len(sub)} dự án có chuỗi Biggee; vẽ {len(top)} dự án nhiều căn nhất'
        else:
            t_ = sub['tinh'].value_counts().index[0] if len(sub) else None; q_ = sub[sub['tinh'] == t_]['quan'].value_counts().index[0] if t_ is not None and sub[sub['tinh'] == t_]['quan'].notna().any() else None
            aw, al, an = bl.area_history(BGH, BGL, t_, q_)
            if aw is None or len(aw) < 3: aw, al, an = bl.area_history(BGH, BGL, t_, None)
            if aw is not None:
                aw = aw.copy(); aw.index = pd.DatetimeIndex(aw.index.where(aw.index <= TODAY, TODAY), name='Tháng')
                items.append({'name': f'TB {al}', 'mid': aw['tb'], 'lo': aw['lo'], 'hi': aw['hi'], 'band_name': f'Thấp–Cao {al} (P25–P90)', 'color': ui.PALETTE[0]})
                export.update({f'TB {al}': aw['tb'], f'Thấp {al}': aw['lo'], f'Cao {al}': aw['hi']}); note = f'không dự án nào của CĐT có chuỗi riêng → chuỗi {al} ({an} dự án Biggee)'
            else: note = ''
        if items:
            w = pd.DataFrame(export).sort_index(); w.index.name = 'Tháng'
            cut_items = [{**it, 'mid': cd.cut(it['mid'].to_frame()).iloc[:, 0] if it.get('mid') is not None else None,
                          'lo': cd.cut(it['lo'].to_frame()).iloc[:, 0] if it.get('lo') is not None else None,
                          'hi': cd.cut(it['hi'].to_frame()).iloc[:, 0] if it.get('hi') is not None else None} for it in items]
            cd.chart(fig_mid_band(cut_items, unit='tr/m²'), w, ten='lich_su_gia_cdt', note_text=note)
        else: cd.empty('Chưa có lịch sử giá cho chủ đầu tư này')
    ui.DATA_MIN = dm
    with ui.card('Danh sách dự án của chủ đầu tư', unit=f'{len(sub)} dự án · giá tham chiếu, thấp – cao, nguồn giá', key=f'{kk}_tbl', controls=False) as cd:
        cd.table(bl.project_table(sub.sort_values(['status', 'ref_ppm2'], ascending=[True, False])), ten='du_an_cdt', height=min(560, 40 + 35 * len(sub)))


# ================================================================ TRANG 4: BẢN ĐỒ
def _bbox(mm, pad=0.02):
    """khung bao (nam, tây, bắc, đông) theo phân vị 1–99% để 1 toạ độ sai (vd dự án HCM ghi lat 21°) không kéo khung ra cả nước"""
    la, lo = mm['lat'], mm['lng']
    return (float(la.quantile(0.01)) - pad, float(lo.quantile(0.01)) - pad, float(la.quantile(0.99)) + pad, float(lo.quantile(0.99)) + pad)


def _layer_controls(K, bbox, default_osm=('exp_plan', 'metro', 'construction', 'proposed', 'motorway', 'airport')):
    """bộ chọn lớp chồng: tile quy hoạch (theo phạm vi), lớp OSM, trạng thái, ranh phân khu HN, độ mờ"""
    tl_opts = il.tiles_for_bbox(bbox)
    c0, c1, c2, c3 = st.columns([1.6, 2.2, 2.2, 1.3])
    with c0:
        base = st.selectbox('Nền bản đồ', list(il.BASEMAPS), index=list(il.BASEMAPS).index(st.session_state.get('basemap', il.BASEMAP_DEFAULT)), key=f'{K}_base',
                            format_func=lambda k: il.BASEMAPS[k][0], help='Voyager/Liberty/Bright/Esri: nền có đường, tên đường, địa danh kiểu Google Maps; Positron: nền nhạt để lớp hạ tầng nổi.')
        st.session_state['basemap'] = base
    with c1:
        tiles = st.multiselect('Lớp quy hoạch (tile)', tl_opts, default=[], key=f'{K}_tiles', format_func=lambda k: il.TILES[k][0],
                               placeholder='Chọn lớp quy hoạch chồng lên nền…' if tl_opts else 'Phạm vi này chưa có tile quy hoạch')
    with c2:
        osm = st.multiselect('Hạ tầng (OpenStreetMap)', list(il.OSM_LAYERS), default=[k for k in default_osm if k in il.OSM_LAYERS], key=f'{K}_osm',
                             format_func=lambda k: il.OSM_LAYERS[k])
    with c3:
        sts = st.multiselect('Trạng thái', ['operating', 'construction', 'proposed'], default=['operating', 'construction', 'proposed'], key=f'{K}_sts',
                             format_func=lambda k: il.STATUS_VI[k])
    c4, c5, c6 = st.columns([1.6, 1.6, 3])
    zones = c4.toggle('Ranh QH phân khu Hà Nội', value=False, key=f'{K}_zones')
    op = c5.slider('Độ mờ tile', 0.2, 1.0, 0.6, 0.1, key=f'{K}_op')
    with c6:
        st.markdown('<div class="gn-note" style="margin-top:30px">Không có chú giải: trỏ chuột vào đường để xem tên, loại, tình trạng. '
                    'Ký hiệu (tông tối): cao tốc = lòng nâu sẫm viền đen + vạch xám; quốc lộ = lòng xám xanh đậm; đường sắt/metro = nét đen – tà vẹt xám (metro xanh than, đang xây nâu); '
                    'đang xây = nét đứt nâu viền đen; quy hoạch = nét đứt tím than; nút giao = chấm đen. Tile TP.HCM: Sở QHKT; tile Hà Nội: VietPalm (nguồn thứ ba); hạ tầng: OSM.</div>', unsafe_allow_html=True)
    return tiles, osm, sts, zones, op


def _apply_layers(fig, tiles, osm, sts, zones, op, bbox, max_pts=60):
    OSM = get_osm(il.stamp()); n = 0
    scale = 10.0 if bbox is None else max(0.03, min(10.0, (bbox[3] - bbox[1]) / 1.0))      # bề rộng khung (độ) ~ 1° = cấp tỉnh
    if osm and not OSM.empty: n = il.add_osm_traces(fig, OSM, osm, bbox=bbox, statuses=tuple(sts), max_pts=max_pts, scale=scale)
    if zones: il.add_zone_traces(fig, get_zones(il.stamp()), bbox=bbox)
    if tiles: fig.update_layout(map_layers=il.raster_layers(tiles, bbox=bbox, opacity=op))
    return n


@st.cache_data(show_spinner=False, max_entries=2)
def get_osm(stamp): return il.load_osm()


@st.cache_data(show_spinner=False, max_entries=2)
def get_zones(stamp): return il.load_zones()


@st.cache_data(show_spinner=False, max_entries=2)
def get_hcm_lookup(stamp): return il.load_hcm_lookup()


def page_map(level, tinh, pid, K):
    d = scoped(level, tinh, pid)
    ui.h2(f'Bản đồ dự án · {scope_name(level, tinh, pid)}')
    if level == 'du-an': page_project_map(pid, K); return
    m = d[d['lat'].notna() & d['lng'].notna() & d['lat'].between(8, 24) & d['lng'].between(102, 110)]
    with ui.card('Vị trí dự án & hạ tầng', unit=f'{len(m):,}/{len(d):,} dự án có toạ độ'.replace(',', '.'), key=f'{K}_map', controls=False,
                 toggles={'Màu': ['Trạng thái', 'Loại hình'], 'Cỡ': ['Số căn', 'Đều'], 'Chấm': ['Thưa', 'Vừa', 'Đủ']},
                 help='Chấm = dự án batdongsan. Lớp chồng: tile quy hoạch chính thức (TP.HCM) / bản đồ công bố (Hà Nội) + hạ tầng OSM '
                      '(metro, cao tốc, đường đang xây, đường quy hoạch, sân bay). Ở cấp Toàn quốc chỉ vẽ hạ tầng, zoom vào tỉnh để bật tile.') as cd:
        if m.empty: cd.empty('Chưa có dự án nào có toạ độ trong phạm vi.'); return
        bbox = _bbox(m, pad=0.05)
        with cd.body(): tiles, osm, sts, zones, op = _layer_controls(K, bbox if level != 'toan-quoc' else None,
                                                                       default_osm=('exp_plan', 'metro', 'construction') if level == 'toan-quoc' else ('exp_plan', 'metro', 'construction', 'proposed', 'motorway', 'airport'))
        col = 'status' if cd.toggle.get('Màu') == 'Trạng thái' else 'type'
        # 20/10/2026: giãn chấm - gom theo ô lưới, mỗi ô giữ dự án nhiều căn nhất (Thưa ~70 ô ngang, Vừa ~140, Đủ = mọi chấm)
        dens = cd.toggle.get('Chấm', 'Thưa'); mm = m.copy(); mm['_khac'] = 0
        if dens != 'Đủ':
            ncell = 70 if dens == 'Thưa' else 140
            span = max(bbox[3] - bbox[1], bbox[2] - bbox[0], 0.01); cell = span / ncell
            mm['_gx'] = ((mm['lng'] - bbox[1]) / cell).round().astype(int); mm['_gy'] = ((mm['lat'] - bbox[0]) / cell).round().astype(int)
            mm = mm.sort_values('units_f', ascending=False, na_position='last')
            cnt = mm.groupby(['_gx', '_gy'])['project_id'].transform('size'); mm['_khac'] = cnt - 1
            mm = mm.drop_duplicates(['_gx', '_gy'], keep='first')
        mm['sz'] = np.sqrt(mm['units_f'].fillna(0).clip(0, 20000)) + 3 if cd.toggle.get('Cỡ') == 'Số căn' else 6      # 20/10 PV2: cỡ bubble theo số căn như cũ
        mm['Số căn'] = mm['units_f']; mm['Chủ đầu tư'] = mm['cdt']; mm['Dự án khác trong ô'] = mm['_khac']
        order = [s for s in (bl.STATUS_ORDER if col == 'status' else bl.TYPE_ORDER) if s in set(mm[col])]
        zoom = 5 if level == 'toan-quoc' else 9
        fig = px.scatter_map(mm, lat='lat', lon='lng', color=col, size='sz', size_max=18, hover_name='name', zoom=zoom,
                             hover_data={'lat': False, 'lng': False, 'sz': False, 'Số căn': ':.0f', 'quan': True, 'Chủ đầu tư': True, col: True,
                                         'Dự án khác trong ô': True},
                             color_discrete_sequence=ui.NGANH_PALETTE, category_orders={col: order}, map_style='carto-positron',
                             center={'lat': mm['lat'].median(), 'lon': mm['lng'].median()})
        # 17/10/2026: nền OpenStreetMap (tile.openstreetmap.org) không phân giải DNS được từ mạng VN -> CARTO Positron
        n_inf = _apply_layers(fig, tiles, osm, sts, zones, op, bbox if level != 'toan-quoc' else None, max_pts=25 if level == 'toan-quoc' else 60)
        fig.update_traces(marker=dict(opacity=0.85 if dens == 'Đủ' else 0.95))
        fig.update_layout(height=680, margin=dict(l=0, r=0, t=10, b=0), showlegend=False, hovermode='closest', map_style=il.BASEMAPS[st.session_state.get('basemap', il.BASEMAP_DEFAULT)][1])
        note = (f'hiện {len(mm):,}/{len(m):,} chấm (mỗi ô lưới giữ dự án nhiều căn nhất, hover thấy số dự án còn lại trong ô)'.replace(',', '.') if dens != 'Đủ' else f'{len(m):,} chấm'.replace(',', '.'))
        cd.chart(fig, bl.project_table(m).assign(lat=m['lat'].values, lng=m['lng'].values), ten='ban_do_du_an', height=680,
                 note_text=note + (f' · {n_inf:,} đoạn hạ tầng OSM trong khung'.replace(',', '.') if n_inf else ''))


def page_project_map(pid, K):
    """cấp Dự án: bản đồ 1 dự án zoom 13 + lớp chồng + tra cứu quy hoạch tại điểm (TP.HCM)"""
    r = P_ALL.set_index('project_id').loc[pid]
    if pd.isna(r.get('lat')) or pd.isna(r.get('lng')): ui.card_empty('Bản đồ', note_text='Dự án chưa có toạ độ.'); return
    lat, lng = float(r['lat']), float(r['lng']); bbox = (lat - 0.04, lng - 0.05, lat + 0.04, lng + 0.05)
    near = P_ALL[P_ALL['lat'].between(bbox[0], bbox[2]) & P_ALL['lng'].between(bbox[1], bbox[3])].copy()
    with ui.card('Vị trí dự án so với quy hoạch & hạ tầng', unit=f'{r["name"]} · bán kính ~4 km', key=f'{K}_pmap_{pid}', controls=False) as cd:
        with cd.body(): tiles, osm, sts, zones, op = _layer_controls(f'{K}_{pid}', bbox, default_osm=('exp_plan', 'metro', 'construction', 'proposed', 'motorway', 'trunk', 'airport', 'bridge'))
        near['Số căn'] = near['units_f']; near['Chủ đầu tư'] = near['cdt']; near['Dự án'] = np.where(near['project_id'] == pid, 'Dự án này', 'Dự án lân cận')
        near['sz'] = np.sqrt(near['units_f'].fillna(0).clip(0, 20000)) + 3      # 20/10 PV2: bubble theo số căn cả ở bản đồ dự án
        near.loc[near['project_id'] == pid, 'sz'] = near['sz'].max() * 1.15 + 4
        fig = px.scatter_map(near, lat='lat', lon='lng', color='Dự án', size='sz', size_max=22, hover_name='name', zoom=13, map_style='carto-positron',
                             hover_data={'lat': False, 'lng': False, 'sz': False, 'Số căn': ':.0f', 'status': True, 'Chủ đầu tư': True, 'Dự án': False},
                             color_discrete_map={'Dự án này': TOK['down'], 'Dự án lân cận': TOK['gray']}, center={'lat': lat, 'lon': lng})
        fig.update_traces(marker=dict(opacity=0.75)); fig.update_traces(marker=dict(opacity=1), selector=dict(name='Dự án này')); fig.update_traces(marker_sizemin=5)
        n_inf = _apply_layers(fig, tiles, osm, sts, zones, op, bbox)
        fig.update_layout(height=620, margin=dict(l=0, r=0, t=10, b=0), showlegend=False, hovermode='closest', map_style=il.BASEMAPS[st.session_state.get('basemap', il.BASEMAP_DEFAULT)][1])
        cd.chart(fig, near[['project_id', 'name', 'status', 'lat', 'lng']], ten=f'ban_do_pj{pid}', height=620,
                 note_text=f'{n_inf} đoạn hạ tầng OSM trong khung · {len(near) - 1} dự án lân cận')
    lk = get_hcm_lookup(il.stamp())
    with ui.card('Quy hoạch tại vị trí dự án (TP.HCM)', unit='tra cứu thửa đất tại toạ độ, Sở QHKT TP.HCM', key=f'{K}_qh_{pid}', controls=False,
                 help='Thửa đất chứa toạ độ dự án: đồ án QH phân khu 1/2000, chức năng sử dụng đất và tỷ lệ diện tích, lộ giới đường tiếp giáp, '
                      'điều chỉnh cục bộ. Chỉ có cho dự án TP.HCM đã tra (infra_fetch.py --hcm-lookup).') as cd:
        row = lk[lk['project_id'] == pid] if len(lk) else lk
        if row.empty: cd.empty('Chưa tra cứu điểm này (chỉ TP.HCM; chạy `python infra_fetch.py --hcm-lookup N`).'); return
        x = row.iloc[0]
        if x.get('empty'): cd.empty('Cổng quy hoạch không trả dữ liệu cho toạ độ này (ngoài vùng có bản đồ số hoặc thửa chưa số hoá).'); return
        items = [('Thửa đất', x.get('parcel_no') or '–', f"{x.get('ward') or ''}, {x.get('district') or ''}", 0),
                 ('Diện tích thửa', bl.fmt_num(x.get('parcel_area'), 0) + ' m²', '', 0),
                 ('Chức năng SDĐ chính', x.get('main_landuse') or '–', f"{bl.fmt_num(x.get('main_landuse_pct'), 1)}% diện tích thửa" if pd.notna(x.get('main_landuse_pct')) else '', 0),
                 ('Đồ án QH phân khu', bl.fmt_int(x.get('n_docs')), 'đồ án 1/2000 liên quan', 0)]
        ui.kpi_strip(items)

        def _tbl(js, cols):
            try: v = json.loads(js) if isinstance(js, str) else None
            except Exception: v = None  # noqa: BLE001
            return pd.DataFrame(v)[[c for c in cols if v and c in v[0]]].rename(columns=cols) if v else pd.DataFrame()
        with cd.body():
            c1, c2 = st.columns(2)
            t = _tbl(x.get('landuse'), {'chucnang': 'Chức năng sử dụng đất', 'ma': 'Mã', 'pct': '% thửa', 'dientich': 'm²'})
            if len(t): c1.dataframe(t.round(1), hide_index=True, width='stretch')
            t = _tbl(x.get('docs'), {'ten': 'Đồ án quy hoạch', 'soqd': 'Số QĐ', 'ngay': 'Ngày duyệt', 'coquan': 'Cơ quan'})
            if len(t): c2.dataframe(t, hide_index=True, width='stretch')
            t = _tbl(x.get('roads'), {'duong': 'Đường tiếp giáp', 'logioi': 'Lộ giới (m)', 'huong': 'Hướng'})
            if len(t): c1.dataframe(t, hide_index=True, width='stretch')
            t = _tbl(x.get('dccb'), {'ten': 'Điều chỉnh cục bộ', 'soqd': 'Số QĐ', 'ngay': 'Ngày duyệt'})
            if len(t): c2.dataframe(t, hide_index=True, width='stretch')
        ui.note(f'Tra cứu ngày {x.get("fetched")}. Nguồn: thongtinquyhoach.hochiminhcity.gov.vn (Sở Quy hoạch – Kiến trúc TP.HCM). Toạ độ dự án lấy từ batdongsan, '
                'có thể lệch vài chục mét so với ranh thửa thực tế.')


# ================================================================ TRANG 5: THAY ĐỔI
def page_changes(level, tinh, pid, K):
    ui.h2(f'Thay đổi · {scope_name(level, tinh, pid)}')
    ids = set(scoped(level, tinh, pid)['project_id'])
    ch = CHG[CHG['project_id'].isin(ids)].merge(P_ALL[['project_id', 'tinh', 'type']], on='project_id', how='left')
    seed = ch['date'].min() if len(ch) else None
    ui.note(f'So sánh mỗi lần quét danh sách với lần trước: dự án mới xuất hiện, đổi trạng thái (Sắp mở bán → Đang mở bán → Đã bàn giao), số căn, tên, địa chỉ, chủ đầu tư. '
            f'Ngày đầu tiên ({seed:%d/%m/%Y}) là lần nạp kho nên mọi dự án đều "new".' if seed is not None else 'Chưa có thay đổi nào.')
    if ch.empty: return
    FL = {'new': 'Dự án mới', 'status': 'Trạng thái', 'units': 'Số căn', 'blocks': 'Số tòa', 'area_text': 'Diện tích', 'name': 'Tên', 'address': 'Địa chỉ', 'investor': 'Chủ đầu tư'}
    ch['Loại thay đổi'] = ch['field'].map(FL).fillna(ch['field'])
    with ui.card('Số thay đổi theo ngày', unit='theo loại', key=f'{K}_chg_d', periods=PER, default='3M') as cd:
        w = ch[ch['date'] > seed].pivot_table(index='date', columns='Loại thay đổi', values='project_id', aggfunc='count', fill_value=0)
        w.index.name = 'Ngày'
        if len(w): cd.chart(ui.fig_stack(cd.cut(w), unit='thay đổi'), w, ten='thay_doi_theo_ngay')
        else: cd.empty('Mới có 1 lần quét – thay đổi sẽ xuất hiện từ lần quét thứ hai.')
    with ui.card('Đổi trạng thái', unit='dự án chuyển trạng thái, mới nhất trước', key=f'{K}_chg_st', controls=False) as cd:
        t = ch[ch['field'] == 'status'].sort_values('date', ascending=False)[['date', 'name', 'tinh', 'type', 'old', 'new', 'project_id']]
        if len(t): cd.table(t.rename(columns={'date': 'Ngày', 'name': 'Dự án', 'tinh': 'Tỉnh', 'type': 'Loại', 'old': 'Từ', 'new': 'Sang', 'project_id': 'ID'}), ten='doi_trang_thai')
        else: cd.empty('Chưa có dự án đổi trạng thái.')
    with ui.card('Dự án mới xuất hiện', unit='sau lần nạp kho đầu tiên', key=f'{K}_chg_new', controls=False) as cd:
        t = ch[(ch['field'] == 'new') & (ch['date'] > seed)].sort_values('date', ascending=False)[['date', 'name', 'tinh', 'type', 'new', 'project_id']]
        if len(t): cd.table(t.rename(columns={'date': 'Ngày', 'name': 'Dự án', 'tinh': 'Tỉnh', 'type': 'Loại', 'new': 'Trạng thái', 'project_id': 'ID'}), ten='du_an_moi')
        else: cd.empty('Chưa có dự án mới.')
    with ui.card('Mọi thay đổi', unit='toàn bộ nhật ký', key=f'{K}_chg_all', controls=False) as cd:
        t = ch.sort_values('date', ascending=False)[['date', 'name', 'tinh', 'Loại thay đổi', 'old', 'new', 'project_id']]
        cd.table(t.rename(columns={'date': 'Ngày', 'name': 'Dự án', 'tinh': 'Tỉnh', 'old': 'Cũ', 'new': 'Mới', 'project_id': 'ID'}).head(2000), ten='nhat_ky_thay_doi', height=480)


# ================================================================ TRANG 6: DỮ LIỆU
def page_data(level, tinh, pid, K):
    ui.h2('Dữ liệu')
    d = scoped(level, tinh, pid)
    n_det = d['detail_at'].notna().sum(); n_ls = d['listing_at'].notna().sum(); n_geo = d['lat'].notna().sum()
    ui.kpi_strip([('Dự án trong phạm vi', bl.fmt_int(len(d)), f'quét danh sách {LAST_SCAN:%d/%m/%Y}', 0),
                  ('Có chi tiết', bl.fmt_int(n_det), f'{n_det / max(len(d), 1):.0%} · có toạ độ {bl.fmt_int(n_geo)}', 0),
                  ('Có thống kê tin rao', bl.fmt_int(n_ls), f'{n_ls / max(len(d), 1):.0%}', 0),
                  ('Dòng tin rao', bl.fmt_int(len(LS)), f'từ {LS["date"].min():%d/%m/%Y}' if len(LS) else '', 0),
                  ('Lịch sử giá khu vực', bl.fmt_int(len(AH)), (f'{AH["district_id"].nunique()} quận · ' if len(AH) else '') + f'{len(REP)} PDF báo cáo', 0)])
    with ui.card('Độ phủ theo tỉnh/thành', unit='số dự án · có chi tiết · có tin rao', key=f'{K}_cov', controls=False) as cd:
        g = P_F.groupby('tinh').agg(**{'Dự án': ('project_id', 'count'), 'Có chi tiết': ('detail_at', lambda s: s.notna().sum()),
                                       'Có toạ độ': ('lat', lambda s: s.notna().sum()), 'Có tin rao': ('listing_at', lambda s: s.notna().sum()),
                                       'Đang mở bán': ('status', lambda s: (s == 'Đang mở bán').sum())}).sort_values('Dự án', ascending=False)
        cd.table(g, ten='do_phu', height=480)
    with ui.card('Báo cáo thị trường PDF', unit='research.batdongsan.com.vn · báo cáo tháng/quý 2018–2025, báo cáo tỉnh, phân tích VRES', key=f'{K}_rep',
                 controls=False, chips=['Tất cả'] + list(bl.REPORT_TYPE_LABEL.values()),
                 help='Tải bằng bds_scrape.py --reports về store/reports/<type>/. Biểu đồ chỉ số giá trong PDF phần lớn là ảnh; '
                      'extracted.csv chỉ gom các dòng text/bảng có số (%, tr/m²).') as cd:
        if REP.empty: cd.empty(note_text='Chưa tải. Chạy bds_scrape.py --reports.')
        else:
            r = REP if cd.chip == 'Tất cả' else REP[REP['type_label'] == cd.chip]
            t = r.sort_values('published', ascending=False)[['published', 'type_label', 'title', 'url', 'pages', 'n_hits', 'size_mb', 'file']]
            t = t.rename(columns={'published': 'Ngày đăng', 'type_label': 'Loại', 'title': 'Tiêu đề', 'url': 'PDF', 'pages': 'Trang', 'n_hits': 'Dòng số liệu',
                                  'size_mb': 'MB', 'file': 'File local'})
            with cd.body():
                st.dataframe(t, width='stretch', hide_index=True, height=min(560, 40 + 35 * len(t)),
                             column_config={'PDF': st.column_config.LinkColumn('PDF', display_text='Mở PDF ↗'),
                                            'Ngày đăng': st.column_config.DateColumn('Ngày đăng', format='DD/MM/YYYY'),
                                            'MB': st.column_config.NumberColumn('MB', format='%.1f')})
            cd.export(t, ten='bao_cao_thi_truong')
            ex = bl.reports_extracted()
            n_img = int((REP['text_chars'].fillna(0) < 200).sum()) if 'text_chars' in REP else 0
            ui.note(f'{len(REP)} PDF trong danh mục · {int(REP["file"].notna().sum())} đã tải về store/reports/ · {len(ex):,} dòng số liệu trích (extracted.csv) · '
                    f'{n_img} file gần như không có text (ảnh/scan).'.replace(',', '.'))
    with ui.card('Lịch sử chạy scraper', unit='runs.csv', key=f'{K}_runs', controls=False) as cd:
        r = bl.runs()
        if len(r): cd.table(r.iloc[::-1], ten='runs')
        else: cd.empty()
    with ui.card('Tải toàn bộ', unit='kho hiện tại', key=f'{K}_dl', controls=False) as cd:
        with cd.body():
            c1, c2, c3 = st.columns(3)
            c1.download_button('⤓ Dự án (CSV)', bl.project_table(P_ALL).to_csv(index=False).encode('utf-8-sig'), 'du_an_batdongsan.csv', width='stretch')
            if len(LS): c2.download_button('⤓ Thống kê tin rao (CSV)', LS.to_csv(index=False).encode('utf-8-sig'), 'tin_rao_thong_ke.csv', width='stretch')
            if len(CHG): c3.download_button('⤓ Thay đổi (CSV)', CHG.to_csv(index=False).encode('utf-8-sig'), 'thay_doi.csv', width='stretch')
            if len(AH): c1.download_button('⤓ Lịch sử giá khu vực (CSV)', AH.to_csv(index=False).encode('utf-8-sig'), 'lich_su_gia_khu_vuc.csv', width='stretch')
            if len(REP): c2.download_button('⤓ Danh mục báo cáo PDF (CSV)', REP.drop(columns=['local']).to_csv(index=False).encode('utf-8-sig'), 'bao_cao_index.csv', width='stretch')
        ui.note('Nguồn: batdongsan.com.vn, mục Dự án (danh sách, trang chi tiết, trang tin rao theo dự án). Số căn / diện tích / giá là số ghi trên trang, '
                'không kiểm chứng; giá/m² là giá RAO (tin đăng), không phải giá giao dịch.')


# ================================================================ chạy
PG = ui.nav(list(PAGES), 'nav_page', default='tong-quan', kind='pills', fmt=lambda k: PAGES[k])
with st.container(border=True):
    LV = ui.nav(list(LEVELS), 'nav_lv', default='toan-quoc', kind='subtab', fmt=lambda k: LEVELS[k])
    st.query_params['trang'] = f'{PG}/{LV}'
    TINH, PID = pick_scope(LV)
    if LV == 'du-an' and PID is None: st.stop()
    K = f'{PG}_{LV}' + (f'_{ui.slug(TINH)[:20]}' if TINH else '') + (f'_{PID}' if PID else '')
    {'tong-quan': page_overview, 'gia': page_price, 'cdt': page_investors, 'ban-do': page_map, 'thay-doi': page_changes, 'du-lieu': page_data}[PG](LV, TINH, PID, K)
