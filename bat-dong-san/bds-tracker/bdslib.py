# -*- coding: utf-8 -*-
r"""
bdslib.py - lớp DỮ LIỆU của BĐS Tracker: đọc kho store/ của batdongsan-projects (parquet) và tính các bảng cho app.
Không gọi mạng. Kho: projects.parquet (1 dòng/dự án), geo_projects.parquet (tỉnh/quận theo danh bạ batdongsan),
project_changes.parquet (thay đổi theo ngày), listing_stats/<YYYY-MM>.parquet (thống kê tin rao theo ngày/dự án/loại).
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
BIG_CITIES = ['Hà Nội', 'Hồ Chí Minh', 'Bình Dương', 'Đồng Nai', 'Đà Nẵng', 'Hải Phòng', 'Khánh Hòa', 'Bà Rịa Vũng Tàu', 'Long An', 'Hưng Yên']


def stamp():
    """chữ ký kho (size|mtime các file) -> khoá cache của app"""
    fs = [os.path.join(STORE, f) for f in ('projects.parquet', 'geo_projects.parquet', 'project_changes.parquet', 'runs.csv')]
    fs += glob.glob(os.path.join(STORE, 'listing_stats', '*.parquet'))
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
            'units_f': 'Số căn', 'area_f': 'Diện tích (m²)', 'blocks': 'Số tòa', 'cdt': 'Chủ đầu tư', 'price_text': 'Giá niêm yết',
            'legal': 'Pháp lý', 'address': 'Địa chỉ', 'link': 'Link'}
    cols = {k: v for k, v in cols.items() if k in d}
    return d[list(cols)].rename(columns=cols)
