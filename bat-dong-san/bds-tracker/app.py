# -*- coding: utf-8 -*-
r"""
BĐS TRACKER - theo dõi dự án bất động sản từ batdongsan.com.vn (D:\bat-dong-san), dựng 17/10/2026 theo template Port & Vessel Tracker.
Chạy:  D:\bat-dong-san\bds-tracker\Chay-app.bat   (http://localhost:8767)

GIAO DIỆN: mẫu "Genea" dùng chung (ui_genea.py: nền be sáng, thẻ biểu đồ Plotly có kỳ + nút xuất, điều hướng trên đầu trang, không sidebar).
Cấp 1 = 6 trang: Tổng quan · Giá & tin rao · Chủ đầu tư · Bản đồ · Thay đổi · Dữ liệu.
Cấp 2 (trên MỌI trang) = phạm vi: Toàn quốc · Tỉnh/thành · Dự án. Bộ lọc chung (loại hình, trạng thái) ngay dưới header.
Deep-link: ?trang=<trang>/<pham-vi>&tinh=<tỉnh>&da=<project_id>  (vd ?trang=gia/tinh&tinh=Hà Nội).

DỮ LIỆU: kho store/ của batdongsan-projects (bds_scrape.py chạy hằng ngày: danh sách 6.000+ dự án, chi tiết, thống kê tin rao bán/thuê).
App chỉ đọc parquet (bdslib.py), không gọi mạng.
"""
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
import ui_genea as ui  # noqa: E402

st.set_page_config(page_title='BĐS Tracker', page_icon='🏙️', layout='wide', initial_sidebar_state='collapsed')
ui.inject_css()
TOK = ui.TOK
PER = ['1M', '3M', '6M', '1Y', 'All']
TODAY = pd.Timestamp.today().normalize()


# ================================================================ dữ liệu (cache theo chữ ký kho)
@st.cache_data(show_spinner='Đang nạp kho dự án…', max_entries=3)
def load_all(stamp):
    return bl.load_projects(), bl.load_changes(), bl.load_listings()


STAMP = bl.stamp()
P_ALL, CHG, LS = load_all(STAMP)
if P_ALL.empty:
    st.error('Kho chưa có dữ liệu. Chạy `python D:\\bat-dong-san\\batdongsan-projects\\bds_scrape.py` trước.'); st.stop()
LAST_SCAN = pd.to_datetime(P_ALL['last_seen'], errors='coerce').max()
LS_LAST = LS['date'].max() if not LS.empty else None
ui.set_data_end(max(x for x in [LAST_SCAN, LS_LAST] if x is not None)); ui.DATA_MIN = pd.Timestamp('2026-10-01').date()

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


# ================================================================ TRANG 2: GIÁ & TIN RAO
def page_price(level, tinh, pid, K):
    ui.h2(f'Giá & tin rao · {scope_name(level, tinh, pid)}')
    if LS.empty: ui.card_empty('Giá & tin rao', note_text='Chưa có thống kê tin rao. Chạy bds_scrape.py --listings.'); return
    if level == 'du-an': page_project(pid, K); return
    kind_lab = {'ban': 'Bán', 'thue': 'Cho thuê'}
    with ui.card('Giá rao / m² trung vị theo ' + ('tỉnh/thành' if level == 'toan-quoc' else 'quận/huyện'),
                 unit='triệu đồng/m² (bán) · triệu đồng/m²/tháng (thuê)', key=f'{K}_ppm2_geo', controls=False, chips=list(kind_lab.values()),
                 help='Mỗi dự án = trung vị 20 tin mới nhất; cột = trung vị các dự án trong khu vực, lần thống kê gần nhất. Chỉ khu vực ≥ 3 dự án.') as cd:
        kind = 'ban' if cd.chip == 'Bán' else 'thue'
        d = bl.latest_listing(ls_scoped(level, tinh, pid, kind), kind)
        g = 'tinh' if level == 'toan-quoc' else 'quan'
        if len(d):
            s = d.groupby(d[g].fillna('(chưa rõ)'))['ppm2_med'].agg(['median', 'count']); s = s[s['count'] >= 3]['median'].sort_values(ascending=False).head(25)
            cd.chart(ui.fig_hbar(s, unit='tr/m²', sign=False, nd=1), s.to_frame('Trung vị'), ten='gia_m2_khu_vuc')
        else: cd.empty()
    c1, c2 = st.columns(2)
    with c1:
        with ui.card('Giá rao bán / m² theo tuần', unit='triệu đồng/m², 6 khu vực nhiều dự án nhất', key=f'{K}_ppm2_w', periods=PER, default='3M', compact=True) as cd:
            d = ls_scoped(level, tinh, pid, 'ban'); g = 'tinh' if level == 'toan-quoc' else 'quan'
            if len(d):
                top = d.groupby('project_id')[g].first().value_counts().head(6).index.tolist()
                w = bl.weekly(d[d[g].isin(top)], [g]); w = w.reindex(columns=[t for t in top if t in w.columns])
                cd.chart(ui.fig_line(cd.cut(w), unit='tr/m²', markers=True, hover_nd=1), w, ten='gia_m2_tuan')
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
    c1, c2 = st.columns(2)
    with c1: hbar_count(dd['cdt'].value_counts(), 'dự án', f'{K}_cdt_n', 'Chủ đầu tư nhiều dự án nhất')
    with c2:
        s = dd[dd['status'].isin(['Đang mở bán', 'Sắp mở bán'])].groupby('cdt')['units_f'].sum().sort_values(ascending=False)
        hbar_count(s, 'căn', f'{K}_cdt_u', 'Chủ đầu tư theo số căn đang / sắp mở bán')
    with ui.card('Bảng chủ đầu tư', unit='số dự án theo trạng thái, số căn, tỉnh hoạt động', key=f'{K}_cdt_tbl', controls=False) as cd:
        g = dd.groupby('cdt').agg(**{'Dự án': ('project_id', 'count'), 'Đang mở bán': ('status', lambda s: (s == 'Đang mở bán').sum()),
                                     'Sắp mở bán': ('status', lambda s: (s == 'Sắp mở bán').sum()), 'Đã bàn giao': ('status', lambda s: (s == 'Đã bàn giao').sum()),
                                     'Số căn (tổng)': ('units_f', 'sum'), 'Diện tích (ha)': ('area_f', lambda s: s.sum() / 10000),
                                     'Tỉnh': ('tinh', lambda s: ', '.join(s.value_counts().head(4).index))}).sort_values('Dự án', ascending=False)
        g.index.name = 'Chủ đầu tư'
        cd.table(g.round(1), ten='chu_dau_tu', height=520)
    with ui.card('Dự án của một chủ đầu tư', unit='chọn chủ đầu tư', key=f'{K}_cdt_one', controls=False) as cd:
        opts = dd['cdt'].value_counts().index.tolist()
        with cd.body(): c = st.selectbox('Chủ đầu tư', opts, key=f'{K}_cdt_sel', label_visibility='collapsed')
        cd.table(bl.project_table(dd[dd['cdt'] == c].sort_values('status')), ten='du_an_cdt')


# ================================================================ TRANG 4: BẢN ĐỒ
def page_map(level, tinh, pid, K):
    d = scoped(level, tinh, pid)
    ui.h2(f'Bản đồ dự án · {scope_name(level, tinh, pid)}')
    m = d[d['lat'].notna() & d['lng'].notna() & d['lat'].between(8, 24) & d['lng'].between(102, 110)]
    with ui.card('Vị trí dự án', unit=f'{len(m):,}/{len(d):,} dự án có toạ độ (từ trang chi tiết)'.replace(',', '.'), key=f'{K}_map', controls=False,
                 toggles={'Màu': ['Trạng thái', 'Loại hình'], 'Cỡ': ['Số căn', 'Đều']}) as cd:
        if m.empty: cd.empty('Chưa có dự án nào có toạ độ trong phạm vi (chi tiết được kéo dần 300 dự án/ngày).'); return
        col = 'status' if cd.toggle.get('Màu') == 'Trạng thái' else 'type'
        mm = m.copy(); mm['sz'] = np.sqrt(mm['units_f'].fillna(0).clip(0, 20000)) + 3 if cd.toggle.get('Cỡ') == 'Số căn' else 6
        mm['Số căn'] = mm['units_f']; mm['Chủ đầu tư'] = mm['cdt']
        order = [s for s in (bl.STATUS_ORDER if col == 'status' else bl.TYPE_ORDER) if s in set(mm[col])]
        zoom = 5 if level == 'toan-quoc' else (9 if level == 'tinh' else 13)
        fig = px.scatter_map(mm, lat='lat', lon='lng', color=col, size='sz', size_max=18, hover_name='name', zoom=zoom,
                             hover_data={'lat': False, 'lng': False, 'sz': False, 'Số căn': ':.0f', 'quan': True, 'Chủ đầu tư': True, col: True},
                             color_discrete_sequence=ui.NGANH_PALETTE, category_orders={col: order}, map_style='open-street-map',
                             center={'lat': mm['lat'].median(), 'lon': mm['lng'].median()})
        fig.update_layout(height=640, margin=dict(l=0, r=0, t=30, b=0), legend=dict(orientation='h', y=1.02, x=0), hovermode='closest')
        cd.chart(fig, bl.project_table(mm).assign(lat=mm['lat'].values, lng=mm['lng'].values), ten='ban_do_du_an', height=640)


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
        cd.table(t.rename(columns={'date': 'Ngày', 'name': 'Dự án', 'tinh': 'Tỉnh', 'type': 'Loại', 'old': 'Từ', 'new': 'Sang', 'project_id': 'ID'}), ten='doi_trang_thai') if len(t) else cd.empty('Chưa có dự án đổi trạng thái.')
    with ui.card('Dự án mới xuất hiện', unit='sau lần nạp kho đầu tiên', key=f'{K}_chg_new', controls=False) as cd:
        t = ch[(ch['field'] == 'new') & (ch['date'] > seed)].sort_values('date', ascending=False)[['date', 'name', 'tinh', 'type', 'new', 'project_id']]
        cd.table(t.rename(columns={'date': 'Ngày', 'name': 'Dự án', 'tinh': 'Tỉnh', 'type': 'Loại', 'new': 'Trạng thái', 'project_id': 'ID'}), ten='du_an_moi') if len(t) else cd.empty('Chưa có dự án mới.')
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
                  ('Dòng tin rao', bl.fmt_int(len(LS)), f'từ {LS["date"].min():%d/%m/%Y}' if len(LS) else '', 0)])
    with ui.card('Độ phủ theo tỉnh/thành', unit='số dự án · có chi tiết · có tin rao', key=f'{K}_cov', controls=False) as cd:
        g = P_F.groupby('tinh').agg(**{'Dự án': ('project_id', 'count'), 'Có chi tiết': ('detail_at', lambda s: s.notna().sum()),
                                       'Có toạ độ': ('lat', lambda s: s.notna().sum()), 'Có tin rao': ('listing_at', lambda s: s.notna().sum()),
                                       'Đang mở bán': ('status', lambda s: (s == 'Đang mở bán').sum())}).sort_values('Dự án', ascending=False)
        cd.table(g, ten='do_phu', height=480)
    with ui.card('Lịch sử chạy scraper', unit='runs.csv', key=f'{K}_runs', controls=False) as cd:
        r = bl.runs(); cd.table(r.iloc[::-1], ten='runs') if len(r) else cd.empty()
    with ui.card('Tải toàn bộ', unit='kho hiện tại', key=f'{K}_dl', controls=False) as cd:
        with cd.body():
            c1, c2, c3 = st.columns(3)
            c1.download_button('⤓ Dự án (CSV)', bl.project_table(P_ALL).to_csv(index=False).encode('utf-8-sig'), 'du_an_batdongsan.csv', width='stretch')
            if len(LS): c2.download_button('⤓ Thống kê tin rao (CSV)', LS.to_csv(index=False).encode('utf-8-sig'), 'tin_rao_thong_ke.csv', width='stretch')
            if len(CHG): c3.download_button('⤓ Thay đổi (CSV)', CHG.to_csv(index=False).encode('utf-8-sig'), 'thay_doi.csv', width='stretch')
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
