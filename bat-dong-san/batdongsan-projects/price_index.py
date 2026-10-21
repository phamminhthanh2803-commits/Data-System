# -*- coding: utf-8 -*-
r"""
price_index.py - CHỈ SỐ GIÁ DỰ ÁN TỰ TÍNH theo phương pháp đã kiểm chứng của Biggee (BIGGEE.md §7), 20/10/2026.

Nguồn: tin rao từng dòng do bds_scrape.py lưu (store/listings/<YYYY-MM>.parquet: prid, project_id, kind, price, price_unit, area, ppm2,
bed, posted, first_seen, date). Mỗi dự án × tháng:
  mẫu  = tin BÁN có đơn giá, đăng (posted; thiếu thì first_seen) trong cửa sổ WINDOW_DAYS trước cuối tháng, mỗi prid tính 1 lần
  lọc  = bỏ tin ngoài [LO_X, HI_X] × trung vị thô, rồi bỏ |x − trung vị| > MAD_K × MAD (mô phỏng "mẫu phù hợp" của Biggee)
  giá  = P50 (TB), P25 (thấp), P90 (cao) của đơn giá tr/m²; thêm P50 theo số phòng ngủ (1/2/3/4+), n, DT trung vị
Cấp quận: gộp tin của mọi dự án trong quận (geo_projects.district), cùng cách. Kết quả:
  store/price_index.parquet          (project_id, month, n, p25, p50, p90, mean, area_med, p50_b1..p50_b4)
  store/price_index_district.parquet (city, district, month, n, p25, p50, p90)
Chạy: python price_index.py [--window 120] [--compare-biggee]  (so với store/biggee/project_history.parquet các tháng trùng)
Chuỗi lịch sử trước khi có tin rao của ta (10/2026) vẫn lấy từ Biggee; app nối 2 chuỗi (bdslib.load_price_index).
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('BDS_STORE') or os.path.join(HERE, 'store')
P_OUT = os.path.join(STORE, 'price_index.parquet')
P_OUT_D = os.path.join(STORE, 'price_index_district.parquet')
WINDOW_DAYS = 120          # Biggee: mẫu so sánh trong ~4 tháng gần nhất
LO_X, HI_X = 0.5, 2.0      # bỏ tin lệch quá xa trung vị thô (nhập sai đơn vị, rao đất/nhà phố lẫn vào)
MAD_K = 3.5                # lọc robust lần 2
N_MIN = 5                  # dưới 5 mẫu không tính


def load_listings():
    fs = sorted(glob.glob(os.path.join(STORE, 'listings', '*.parquet')))
    if not fs: return pd.DataFrame()
    d = pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True)
    d = d[d['kind'] == 'ban'].copy()
    # đơn giá: ưu tiên ppm2 trang ghi; thiếu thì giá (tỷ) / DT
    calc = np.where((d['price_unit'] == 'tỷ') & d['area'].gt(0), d['price'] * 1000 / d['area'].replace(0, np.nan), np.nan)
    d['ppm2'] = pd.to_numeric(d['ppm2'], errors='coerce').fillna(pd.Series(calc, index=d.index))
    d['t'] = pd.to_datetime(d['posted'], errors='coerce').fillna(pd.to_datetime(d['first_seen'], errors='coerce'))
    d = d[d['ppm2'].gt(0) & d['t'].notna()]
    d['bed'] = pd.to_numeric(d['bed'], errors='coerce')
    return d


def _filter(x: pd.Series) -> pd.Series:
    med = x.median(); x = x[(x >= LO_X * med) & (x <= HI_X * med)]
    if len(x) >= 4:
        med = x.median(); mad = (x - med).abs().median() * 1.4826
        if mad > 0: x = x[(x - med).abs() <= MAD_K * mad]
    return x


def _stats(g: pd.DataFrame) -> dict | None:
    x = _filter(g['ppm2'])
    if len(x) < N_MIN: return None
    keep = g.loc[x.index]
    o = {'n': int(len(x)), 'p25': float(np.percentile(x, 25)), 'p50': float(np.percentile(x, 50)), 'p90': float(np.percentile(x, 90)),
         'mean': float(x.mean()), 'area_med': float(keep['area'].median()) if keep['area'].notna().any() else np.nan}
    b = keep['bed'].clip(upper=4)
    for k in (1, 2, 3, 4):
        xs = x[b == k]; o[f'p50_b{k}'] = float(xs.median()) if len(xs) >= 3 else np.nan
    return o


def build(window=WINDOW_DAYS):
    d = load_listings()
    if d.empty: print('chưa có store/listings/*.parquet (bds_scrape.py --listings lưu từ 20/10/2026)'); return pd.DataFrame(), pd.DataFrame()
    geo = pd.read_parquet(os.path.join(STORE, 'geo_projects.parquet'))[['project_id', 'city', 'district']]
    d = d.merge(geo, on='project_id', how='left')
    months = pd.period_range(d['t'].min().to_period('M'), pd.Timestamp.today().to_period('M'), freq='M')
    rows, rows_d = [], []
    for m in months:
        end = m.to_timestamp(how='end').normalize(); start = end - pd.Timedelta(days=window)
        w = d[(d['t'] > start) & (d['t'] <= end)].sort_values('date').drop_duplicates('prid', keep='last')
        if w.empty: continue
        for pid, g in w.groupby('project_id'):
            o = _stats(g)
            if o: rows.append({'project_id': int(pid), 'month': end, **o})
        for (c, q), g in w.dropna(subset=['district']).groupby(['city', 'district']):
            o = _stats(g)
            if o: rows_d.append({'city': c, 'district': q, 'month': end, **o})
    out = pd.DataFrame(rows); outd = pd.DataFrame(rows_d)
    out.to_parquet(P_OUT, index=False); outd.to_parquet(P_OUT_D, index=False)
    print(f'chỉ số giá: {out["project_id"].nunique() if len(out) else 0} dự án × {len(months)} tháng = {len(out)} dòng; quận {len(outd)} dòng; tin dùng {d["prid"].nunique():,} -> {P_OUT}'.replace(',', '.'))
    return out, outd


def compare_biggee(out: pd.DataFrame):
    pb = os.path.join(STORE, 'biggee', 'project_history.parquet'); pm = os.path.join(STORE, 'biggee', 'apart_match.csv')
    if out.empty or not os.path.exists(pb): print('chưa so được với Biggee'); return
    h = pd.read_parquet(pb); h['month'] = pd.to_datetime(h['month']); m = pd.read_csv(pm)
    m = m[m['project_id'].notna() & (m['ok'].astype(str) != '0')][['slug', 'project_id']].astype({'project_id': int})
    h = h.merge(m, on='slug'); h['bg'] = h['untprice'] / 1e6
    x = out.merge(h[['project_id', 'month', 'bg']], on=['project_id', 'month'])
    if x.empty: print('không có tháng trùng với Biggee'); return
    x['r'] = x['p50'] / x['bg']
    print(f'so Biggee: {len(x)} dự án-tháng trùng | tỷ lệ P50 ta / Biggee: trung vị {x["r"].median():.3f}, P25–P75 {x["r"].quantile(.25):.3f}–{x["r"].quantile(.75):.3f}, '
          f'trong ±10%: {((x["r"] - 1).abs() <= .1).mean():.0%} | corr log {np.corrcoef(np.log(x["p50"]), np.log(x["bg"]))[0, 1]:.3f}')
    x.sort_values('r').to_csv(os.path.join(STORE, 'biggee', 'doi_chieu_price_index.csv'), index=False, encoding='utf-8-sig')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--window', type=int, default=WINDOW_DAYS); ap.add_argument('--compare-biggee', action='store_true')
    a = ap.parse_args(argv)
    out, _ = build(a.window)
    if a.compare_biggee: compare_biggee(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
