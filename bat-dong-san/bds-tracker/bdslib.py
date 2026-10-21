# -*- coding: utf-8 -*-
r"""
bdslib.py - lớp DỮ LIỆU của BĐS Tracker: đọc kho store/ của batdongsan-projects (parquet) và tính các bảng cho app.
Không gọi mạng. Kho: projects.parquet (1 dòng/dự án), geo_projects.parquet (tỉnh/quận theo danh bạ batdongsan),
project_changes.parquet (thay đổi theo ngày), listing_stats/<YYYY-MM>.parquet (thống kê tin rao theo ngày/dự án/loại),
area_history/<YYYY-MM>.parquet (dòng tóm tắt "Lịch sử giá" cấp quận × loại × bán/thuê), reports/index.csv (PDF báo cáo research.batdongsan).
"""
from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

APP = os.path.dirname(os.path.abspath(__file__))
HUB = os.path.dirname(APP)
STORE = os.environ.get('BDS_STORE') or os.path.join(HUB, 'batdongsan-projects', 'store')
STATUS_ORDER = ['Đang mở bán', 'Sắp mở bán', 'Đã bàn giao', 'Đang cập nhật']
TYPE_ORDER = ['Căn hộ chung cư', 'Khu đô thị mới', 'Biệt thự, liền kề', 'Nhà ở xã hội', 'Khu phức hợp', 'Shophouse', 'Nhà mặt phố',
              'Khu nghỉ dưỡng, sinh thái', 'Khu công nghiệp', 'Cao ốc văn phòng', 'Trung tâm thương mại', 'Dự án khác']
AREA_TYPE_ORDER = ['Căn hộ chung cư', 'Nhà riêng', 'Nhà mặt phố', 'Biệt thự, liền kề', 'Đất nền dự án', 'Đất']
REPORT_TYPE_LABEL = {'thi-truong': 'Thị trường', 'tinh': 'Tỉnh', 'phan-tich': 'Phân tích'}
BIG_CITIES = ['Hà Nội', 'Hồ Chí Minh', 'Bình Dương', 'Đồng Nai', 'Đà Nẵng', 'Hải Phòng', 'Khánh Hòa', 'Bà Rịa Vũng Tàu', 'Long An', 'Hưng Yên']


def stamp():
    """chữ ký kho (size|mtime các file) -> khoá cache của app"""
    fs = [os.path.join(STORE, f) for f in ('projects.parquet', 'geo_projects.parquet', 'project_changes.parquet', 'runs.csv')]
    fs += glob.glob(os.path.join(STORE, 'listing_stats', '*.parquet')) + glob.glob(os.path.join(STORE, 'area_history', '*.parquet'))
    fs += [os.path.join(STORE, 'reports', 'index.csv')] + glob.glob(os.path.join(STORE, 'biggee', '*.parquet')) + [os.path.join(STORE, 'biggee', 'apart_match.csv')] + [os.path.join(STORE, 'price_index.parquet'), os.path.join(STORE, 'price_index_district.parquet')]
    return '|'.join(f'{os.path.getsize(f)}:{int(os.path.getmtime(f))}' for f in fs if os.path.exists(f))


def load_projects() -> pd.DataFrame:
    p = os.path.join(STORE, 'projects.parquet')
    if not os.path.exists(p): return pd.DataFrame()
    d = pd.read_parquet(p)
    g = os.path.join(STORE, 'geo_projects.parquet')
    if os.path.exists(g):
        geo = pd.read_parquet(g)[['project_id', 'city', 'district']].rename(columns={'city': 'g_city', 'district': 'g_district'})
        d = d.merge(geo, on='project_id', how='left')
    else:
        d['g_city'] = None; d['g_district'] = None
    # tỉnh/quận: danh bạ batdongsan (63 tỉnh cũ, phủ gần đủ) -> breadcrumb trang chi tiết -> đoán từ địa chỉ
    d['tinh'] = d['g_city'].where(d['g_city'].notna(), d.get('city'))
    d['quan'] = d['g_district'].where(d['g_district'].notna(), d.get('district'))
    miss = d['tinh'].isna() & d['address'].notna()
    d.loc[miss, 'tinh'] = d.loc[miss, 'address'].str.rsplit(',', n=1).str[-1].str.strip()
    d['tinh'] = d['tinh'].fillna('(chưa rõ)').replace({'TP Hồ Chí Minh': 'Hồ Chí Minh', 'Tp Hồ Chí Minh': 'Hồ Chí Minh'})
    d['status'] = d['status'].fillna('Đang cập nhật'); d['type'] = d['type'].fillna('Dự án khác')
    d['units_f'] = pd.to_numeric(d['units'], errors='coerce').fillna(pd.to_numeric(d.get('d_units'), errors='coerce'))
    d['area_f'] = pd.to_numeric(d['area_m2'], errors='coerce').fillna(pd.to_numeric(d.get('d_area_m2'), errors='coerce'))
    d['cdt'] = d.get('investor_name').where(d.get('investor_name').notna(), d['investor']) if 'investor_name' in d else d['investor']
    d['cdt'] = d['cdt'].fillna('(chưa rõ)').str.strip()
    d['link'] = 'https://batdongsan.com.vn' + d['url'].astype(str)
    d['first_seen'] = pd.to_datetime(d['first_seen'], errors='coerce')
    return d


def load_changes() -> pd.DataFrame:
    p = os.path.join(STORE, 'project_changes.parquet')
    if not os.path.exists(p): return pd.DataFrame(columns=['date', 'project_id', 'name', 'field', 'old', 'new'])
    d = pd.read_parquet(p); d['date'] = pd.to_datetime(d['date']); return d


def load_listings() -> pd.DataFrame:
    fs = sorted(glob.glob(os.path.join(STORE, 'listing_stats', '*.parquet')))
    if not fs: return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d['date'] = pd.to_datetime(d['date'])
    for c in ['n_total', 'n_sample', 'price_med', 'ppm2_med', 'ppm2_p25', 'ppm2_p75', 'area_med', 'n_7d', 'n_30d']:
        if c in d: d[c] = pd.to_numeric(d[c], errors='coerce')
    return d


def load_area_history() -> pd.DataFrame:
    """lịch sử giá khu vực (batdongsan, cấp quận): 1 dòng/ngày/quận/loại hình/bán-thuê, pct_1y = % thay đổi giá rao 1 năm (âm = giảm)"""
    fs = sorted(glob.glob(os.path.join(STORE, 'area_history', '*.parquet')))
    if not fs: return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d['date'] = pd.to_datetime(d['date'])
    for c in ['n_total', 'pct_1y', 'price_lo', 'price_hi', 'area_lo', 'area_hi']:
        if c in d: d[c] = pd.to_numeric(d[c], errors='coerce')
    return d


def latest_area(ah: pd.DataFrame, type_name: str, kind: str) -> pd.DataFrame:
    """dòng mới nhất của mỗi quận cho 1 loại hình × bán/thuê"""
    if ah.empty: return ah
    d = ah[(ah['type'] == type_name) & (ah['kind'] == kind)].sort_values('date')
    return d.groupby('district_id').tail(1)


def load_reports() -> pd.DataFrame:
    """danh mục PDF báo cáo research.batdongsan.com.vn (reports/index.csv) + đường dẫn file local"""
    p = os.path.join(STORE, 'reports', 'index.csv')
    if not os.path.exists(p): return pd.DataFrame()
    d = pd.read_csv(p, dtype={'file': str, 'url': str, 'title': str})
    d['published'] = pd.to_datetime(d['published'], errors='coerce')
    d['type_label'] = d['type_name'].map(REPORT_TYPE_LABEL).fillna(d['type_name'])
    d['size_mb'] = pd.to_numeric(d.get('size'), errors='coerce') / 1e6
    d['local'] = d['file'].map(lambda f: os.path.join(STORE, 'reports', f) if isinstance(f, str) and f else None)
    return d


def reports_extracted() -> pd.DataFrame:
    p = os.path.join(STORE, 'reports', 'extracted.csv')
    return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame(columns=['file', 'page', 'kind', 'text'])


def runs() -> pd.DataFrame:
    p = os.path.join(STORE, 'runs.csv')
    return pd.read_csv(p) if os.path.exists(p) else pd.DataFrame()


def latest_listing(ls: pd.DataFrame, kind='ban') -> pd.DataFrame:
    """dòng mới nhất của mỗi dự án cho 1 loại tin (bán/thuê)"""
    if ls.empty: return ls
    d = ls[ls['kind'] == kind].sort_values('date')
    return d.groupby('project_id').tail(1)


def weekly(ls: pd.DataFrame, key_cols, val='ppm2_med', how='median') -> pd.DataFrame:
    """chuỗi theo TUẦN (Chủ nhật = cuối tuần) của 1 chỉ tiêu, gộp theo key_cols (vd tinh); mỗi dự án lấy giá trị cuối tuần"""
    if ls.empty: return pd.DataFrame()
    d = ls.copy(); d['ky'] = d['date'].dt.to_period('W-SUN').dt.end_time.dt.normalize()
    d = d.sort_values('date').groupby(['ky', 'project_id'] + key_cols, as_index=False).tail(1)
    out = d.groupby(['ky'] + key_cols)[val].agg(how).unstack(key_cols) if key_cols else d.groupby('ky')[val].agg(how).to_frame(val)
    out.index = pd.DatetimeIndex(out.index); out.index.name = 'Kỳ'
    return out


def top_n_other(s: pd.Series, n=7, other='Khác') -> pd.Series:
    s = s.sort_values(ascending=False)
    if len(s) <= n: return s
    return pd.concat([s.iloc[:n], pd.Series({other: s.iloc[n:].sum()})])


def fmt_int(v): return '–' if v is None or pd.isna(v) else f'{v:,.0f}'.replace(',', '.')
def fmt_num(v, nd=1): return '–' if v is None or pd.isna(v) else f'{v:,.{nd}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def to_excel(sheets: dict) -> bytes:
    import io
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=str(name)[:31], index=isinstance(df.index, pd.DatetimeIndex))
    return buf.getvalue()


def project_table(d: pd.DataFrame) -> pd.DataFrame:
    cols = {'project_id': 'ID', 'name': 'Dự án', 'status': 'Trạng thái', 'type': 'Loại hình', 'tinh': 'Tỉnh/thành', 'quan': 'Quận/huyện',
            'units_f': 'Số căn', 'area_f': 'Diện tích (m²)', 'blocks': 'Số tòa', 'cdt': 'Chủ đầu tư',
            'ref_ppm2': 'Giá tham chiếu (tr/m²)', 'ref_lo': 'Thấp', 'ref_hi': 'Cao', 'ref_src': 'Nguồn giá', 'price_text': 'Giá niêm yết',
            'legal': 'Pháp lý', 'address': 'Địa chỉ', 'link': 'Link'}
    cols = {k: v for k, v in cols.items() if k in d}
    return d[list(cols)].rename(columns=cols)

# ---------------------------------------------------------------- Biggee (gói thành viên, lấy qua trình duyệt - biggee_web.py, 20/10/2026)
def load_biggee_list() -> pd.DataFrame:
    """bảng giá căn hộ Biggee (tr/m² thấp/cao/TB, biến động % 1 năm, tỷ suất LN %) - bản mới nhất mỗi dự án + project_id batdongsan nếu ghép được"""
    p = os.path.join(STORE, 'biggee', 'apart_price_list.parquet')
    if not os.path.exists(p): return pd.DataFrame()
    d = pd.read_parquet(p).sort_values('date').drop_duplicates('slug', keep='last')
    d['date'] = pd.to_datetime(d['date'], errors='coerce'); d['tinh'] = d['city'].replace({'TP Hồ Chí Minh': 'Hồ Chí Minh'})
    m = _biggee_match()
    return d.merge(m, on='slug', how='left') if len(m) else d.assign(project_id=np.nan)


def _biggee_match() -> pd.DataFrame:
    p = os.path.join(STORE, 'biggee', 'apart_match.csv')
    if not os.path.exists(p): return pd.DataFrame()
    m = pd.read_csv(p); m = m[m['project_id'].notna() & (m['ok'].astype(str) != '0')]
    return m[['slug', 'project_id']].astype({'project_id': int})


def load_biggee_history() -> pd.DataFrame:
    """lịch sử giá tháng Biggee: slug, month (cuối tháng), ppm2 (tr/m² dự án), dist_ppm2 (quận), project_id (nếu ghép)"""
    p = os.path.join(STORE, 'biggee', 'project_history.parquet')
    if not os.path.exists(p): return pd.DataFrame()
    h = pd.read_parquet(p); h['month'] = pd.to_datetime(h['month']); h['ppm2'] = h['untprice'] / 1e6; h['dist_ppm2'] = h['dist_untprice'] / 1e6
    m = _biggee_match()
    return h.merge(m, on='slug', how='left') if len(m) else h.assign(project_id=np.nan)

def load_price_index() -> pd.DataFrame:
    """chỉ số giá dự án TỰ TÍNH (price_index.py, cùng phương pháp Biggee: P50/P25/P90 đơn giá rao của tin so sánh 120 ngày), tr/m²"""
    p = os.path.join(STORE, 'price_index.parquet')
    if not os.path.exists(p): return pd.DataFrame()
    d = pd.read_parquet(p); d['month'] = pd.to_datetime(d['month']); return d


def load_price_index_district() -> pd.DataFrame:
    p = os.path.join(STORE, 'price_index_district.parquet')
    if not os.path.exists(p): return pd.DataFrame()
    d = pd.read_parquet(p); d['month'] = pd.to_datetime(d['month']); return d

# ---------------------------------------------------------------- giá tham chiếu cho mọi dự án (20/10/2026)
def _norm_qh(x):
    """'Quận 2 ' | 'Huyện Nhà Bè' | 'TP Thủ Đức' -> 'quan 2' | 'nha be' | 'thu duc' (so khớp quận giữa batdongsan và Biggee)"""
    import unicodedata, re as _re
    t = unicodedata.normalize('NFD', str(x or '').lower()); t = ''.join(c for c in t if unicodedata.category(c) != 'Mn').replace('đ', 'd')
    t = _re.sub(r'^(thanh pho|tp\.?|thi xa|tx\.?|huyen|h\.)\s+', '', t.strip())
    t = _re.sub(r'^q\.?\s*(\d+)$', r'quan \1', t); t = _re.sub(r'\s+', ' ', t).strip()
    return t


def add_price_ref(d: pd.DataFrame, bgl: pd.DataFrame, ls: pd.DataFrame) -> pd.DataFrame:
    """thêm ref_ppm2 / ref_lo / ref_hi / ref_src (tr/m²) cho từng dự án, ưu tiên:
    1 Biggee dự án (TB, thấp=P25, cao=P90 của Biggee) · 2 tin rao batdongsan của ta (trung vị, P25, P75 20 tin mới nhất)
    · 3 TB quận = trung vị giá TB các dự án Biggee cùng tỉnh+quận, thấp/cao = P25/P90 các dự án đó · 4 TB tỉnh (cùng cách). Dự án không phải căn hộ vẫn hiện TB quận căn hộ (ghi rõ nguồn)."""
    d = d.copy(); d['ref_ppm2'] = np.nan; d['ref_lo'] = np.nan; d['ref_hi'] = np.nan; d['ref_src'] = None
    if bgl is not None and not bgl.empty:
        b = bgl.dropna(subset=['price_avg']).copy(); b['qh'] = b['district'].map(_norm_qh); b['tn'] = b['tinh'].map(_norm_qh)
        # 1. giá riêng Biggee
        bp = b.dropna(subset=['project_id']).drop_duplicates('project_id').set_index(b.dropna(subset=['project_id']).drop_duplicates('project_id')['project_id'].astype(int))
        m = d['project_id'].isin(bp.index)
        d.loc[m, 'ref_ppm2'] = d.loc[m, 'project_id'].map(bp['price_avg']); d.loc[m, 'ref_lo'] = d.loc[m, 'project_id'].map(bp['price_lo'])
        d.loc[m, 'ref_hi'] = d.loc[m, 'project_id'].map(bp['price_hi']); d.loc[m, 'ref_src'] = 'Biggee dự án'
    # 2. tin rao của ta
    if ls is not None and not ls.empty:
        l = ls[(ls['kind'] == 'ban') & ls['ppm2_med'].gt(0)].sort_values('date').drop_duplicates('project_id', keep='last').set_index('project_id')
        m = d['ref_ppm2'].isna() & d['project_id'].isin(l.index)
        d.loc[m, 'ref_ppm2'] = d.loc[m, 'project_id'].map(l['ppm2_med']); d.loc[m, 'ref_lo'] = d.loc[m, 'project_id'].map(l['ppm2_p25'])
        d.loc[m, 'ref_hi'] = d.loc[m, 'project_id'].map(l['ppm2_p75']); d.loc[m, 'ref_src'] = 'Tin rao batdongsan'
    # 3-4. TB quận / tỉnh từ bảng giá Biggee
    if bgl is not None and not bgl.empty:
        q = b.groupby(['tn', 'qh'])['price_avg'].agg(ref_ppm2='median', ref_lo=lambda x: x.quantile(.25), ref_hi=lambda x: x.quantile(.9), n='size')
        t = b.groupby('tn')['price_avg'].agg(ref_ppm2='median', ref_lo=lambda x: x.quantile(.25), ref_hi=lambda x: x.quantile(.9), n='size')
        key = list(zip(d['tinh'].map(_norm_qh), d['quan'].map(_norm_qh)))
        m = d['ref_ppm2'].isna() & pd.Series([k in q.index for k in key], index=d.index)
        if m.any():
            qq = q.loc[[k for k, ok in zip(key, m) if ok]]
            d.loc[m, 'ref_ppm2'] = qq['ref_ppm2'].values; d.loc[m, 'ref_lo'] = qq['ref_lo'].values; d.loc[m, 'ref_hi'] = qq['ref_hi'].values
            d.loc[m, 'ref_src'] = ['TB quận (căn hộ Biggee, %d DA)' % n for n in qq['n'].values]
        tn = d['tinh'].map(_norm_qh); m = d['ref_ppm2'].isna() & tn.isin(t.index)
        if m.any():
            tt = t.loc[tn[m]]
            d.loc[m, 'ref_ppm2'] = tt['ref_ppm2'].values; d.loc[m, 'ref_lo'] = tt['ref_lo'].values; d.loc[m, 'ref_hi'] = tt['ref_hi'].values
            d.loc[m, 'ref_src'] = ['TB tỉnh (căn hộ Biggee, %d DA)' % n for n in tt['n'].values]
        m = d['ref_ppm2'].isna()
        if m.any():                                                  # 5. toàn quốc - để không dự án nào trống (ghi rõ nguồn)
            x = b['price_avg']; d.loc[m, 'ref_ppm2'] = x.median(); d.loc[m, 'ref_lo'] = x.quantile(.25); d.loc[m, 'ref_hi'] = x.quantile(.9)
            d.loc[m, 'ref_src'] = 'TB toàn quốc (căn hộ Biggee, %d DA)' % len(x)
    for c in ('ref_ppm2', 'ref_lo', 'ref_hi'): d[c] = pd.to_numeric(d[c], errors='coerce').round(1)
    return d

def area_history(bgh: pd.DataFrame, bgl: pd.DataFrame, tinh=None, quan=None):
    """chuỗi tháng cấp QUẬN (hoặc tỉnh khi quan=None, toàn quốc khi cả hai None) từ lịch sử Biggee các dự án trong khu vực:
    'TB khu vực' = trung vị dist_untprice (chuỗi quận của chính Biggee) hoặc trung vị untprice các dự án; 'Thấp'/'Cao' = P25/P90 untprice các dự án theo tháng.
    Trả (DataFrame index tháng, nhãn khu vực, số dự án) hoặc (None, None, 0)."""
    if bgh is None or bgh.empty or bgl is None or bgl.empty: return None, None, 0
    g = bgh.merge(bgl[['slug', 'tinh', 'district']], on='slug', how='inner')
    if tinh is not None: g = g[g['tinh'].map(_norm_qh) == _norm_qh(tinh)]
    if quan is not None: g = g[g['district'].map(_norm_qh) == _norm_qh(quan)]
    if g['slug'].nunique() < 1: return None, None, 0
    w = g.groupby('month').agg(tb=('ppm2', 'median'), lo=('ppm2', lambda x: x.quantile(.25)), hi=('ppm2', lambda x: x.quantile(.9)), n=('slug', 'nunique'))
    if quan is not None and g['dist_ppm2'].notna().any(): w['tb'] = g.groupby('month')['dist_ppm2'].median()      # chuỗi quận của Biggee
    w = w[w['n'] >= 1]; w.index.name = 'Tháng'
    label = f'quận {quan}' if quan else (f'tỉnh {tinh}' if tinh else 'toàn quốc')
    return w, label, int(g['slug'].nunique())
