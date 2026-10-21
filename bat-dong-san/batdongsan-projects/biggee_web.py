# -*- coding: utf-8 -*-
r"""
biggee_web.py - nạp dữ liệu Biggee lấy QUA TRÌNH DUYỆT (gói thành viên, không có API) vào store/biggee/ (20/10/2026).

Cách lấy (xem BIGGEE.md mục 5): trong khung trình duyệt của Claude đã đăng nhập Biggee, chạy script JS kéo
  (a) bảng giá căn hộ toàn quốc  /index.php/pages/get_apart_price_list (DataTables, server chỉ trả 10 dòng/lượt, ~1.660 dự án)
      -> mỗi dòng 1 chuỗi "tỉnh|quận|phường|tên|slug|giá thấp|giá cao|giá TB|biến động %|tỷ suất LN %"
  (b) lịch sử giá từng dự án: HTML trang /dinh-gia-can-ho/<slug> có <input id="outDatatrend" value='[{"period":"09/2021","UNTPRICE":375000000,"DIST_UNTPRICE":127123000},...]'>
      (đồng/m², theo tháng, dự án + quận huyện, tới ~5 năm) -> mỗi dự án 1 dòng JSON {"slug":..., "data":[...]}
Kết quả JS được chép ra file text rồi nạp bằng script này:
    python biggee_web.py --price-list  <file.txt>      -> store/biggee/apart_price_list.parquet   (cột date = ngày nạp; tích luỹ theo ngày)
    python biggee_web.py --history     <file.jsonl|.json> -> store/biggee/project_history.parquet (slug, month, untprice, dist_untprice); nhận JSONL hoặc JSON gọn {slug: [[MM/YYYY, giá, giá quận],..]}
    python biggee_web.py --match                        -> store/biggee/apart_match.csv (slug <-> project_id batdongsan theo tên + tỉnh)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import date

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('BDS_STORE') or os.path.join(HERE, 'store')
BG = os.path.join(STORE, 'biggee')
P_LIST = os.path.join(BG, 'apart_price_list.parquet')
P_HIST = os.path.join(BG, 'project_history.parquet')
P_MATCH = os.path.join(BG, 'apart_match.csv')


def _num(s):
    s = str(s).strip().replace(',', '.')
    try: return float(s)
    except ValueError: return None


def load_price_list_text(path, today=None):
    today = today or date.today().isoformat(); rows = []
    for line in open(path, encoding='utf-8'):
        p = line.rstrip('\n').split('|')
        if len(p) < 10: continue
        rows.append({'city': p[0], 'district': p[1], 'ward': p[2], 'name': p[3], 'slug': p[4], 'price_lo': _num(p[5]), 'price_hi': _num(p[6]),
                     'price_avg': _num(p[7]), 'change_pct': _num(p[8]), 'yield_pct': _num(p[9]) if p[9] not in ('N/A', '') else None, 'date': today})
    df = pd.DataFrame(rows).drop_duplicates('slug')
    os.makedirs(BG, exist_ok=True)
    if os.path.exists(P_LIST): df = pd.concat([pd.read_parquet(P_LIST), df], ignore_index=True).drop_duplicates(['date', 'slug'], keep='last')
    df.to_parquet(P_LIST, index=False)
    print(f'bảng giá: {len(rows)} dòng nạp, kho {len(df)} dòng ({df["date"].nunique()} ngày) -> {P_LIST}')
    return df


def _iter_history(path):
    """2 định dạng: JSONL mỗi dòng {"slug":..,"data":[{"period":"MM/YYYY","UNTPRICE":..,"DIST_UNTPRICE":..}]}
    hoặc 1 JSON gọn {slug: [[period, untprice, dist_untprice], ...]} (window.__hist chép từ trình duyệt, có thể nhiều file/chunk)"""
    txt = open(path, encoding='utf-8').read().strip()
    if txt.startswith('{'):
        for slug, data in json.loads(txt).items():
            yield slug, [{'period': d[0], 'UNTPRICE': d[1], 'DIST_UNTPRICE': d[2]} if isinstance(d, list) else d for d in data]
        return
    for line in txt.splitlines():
        line = line.strip()
        if not line: continue
        try: o = json.loads(line)
        except json.JSONDecodeError: continue
        if isinstance(o.get('data'), list): yield o['slug'], o['data']


def load_history_jsonl(path, today=None):
    today = today or date.today().isoformat(); rows = []; n_pj = 0
    for slug, data in _iter_history(path):
        n_pj += 1
        for d in data:
            m = re.match(r'^(\d{1,2})/(\d{4})$', str(d.get('period', '')))
            if not m: continue
            rows.append({'slug': slug, 'month': pd.Timestamp(int(m.group(2)), int(m.group(1)), 1) + pd.offsets.MonthEnd(0),
                         'untprice': d.get('UNTPRICE'), 'dist_untprice': d.get('DIST_UNTPRICE'), 'fetched': today})
    df = pd.DataFrame(rows)
    for c in ('untprice', 'dist_untprice'): df[c] = pd.to_numeric(df[c], errors='coerce')
    os.makedirs(BG, exist_ok=True)
    if os.path.exists(P_HIST): df = pd.concat([pd.read_parquet(P_HIST), df], ignore_index=True).drop_duplicates(['slug', 'month'], keep='last')
    df.to_parquet(P_HIST, index=False)
    print(f'lịch sử: {n_pj} dự án / {len(rows)} dòng nạp, kho {df["slug"].nunique()} dự án, {len(df)} dòng tháng, {df["month"].min():%m/%Y} → {df["month"].max():%m/%Y} -> {P_HIST}')
    return df


STOP = {'du', 'an', 'khu', 'can', 'ho', 'chung', 'cu', 'toa', 'tai', 'tp', 'thanh', 'pho', 'nha', 'o', 'xa', 'hoi', 'dan', 'do', 'thi', 'biet', 'thu', 'lien', 'ke',
        'residence', 'residences', 'tower', 'towers', 'city', 'park', 'garden', 'home', 'homes', 'new', 'central', 'plaza', 'complex', 'view', 'apartment', 'quan', 'huyen', 'phuong'}


def _tok(s):
    s = unicodedata.normalize('NFD', str(s or '').lower()); s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').replace('đ', 'd')
    return [t for t in re.sub(r'[^a-z0-9 ]', ' ', s).split() if t not in STOP]


P_CODES = os.path.join(BG, 'ma_du_an.csv')                     # bảng mã API (biggee_api.py --catalog): biggee_code = slug, ten, tinh, quan


def project_names():
    """1 dòng/slug: name, city, district — bảng giá web (mới nhất) + bảng mã API cho slug chưa có trong bảng giá (20/10 tối)"""
    lst = pd.read_parquet(P_LIST).sort_values('date').drop_duplicates('slug', keep='last')[['slug', 'name', 'city', 'district']] if os.path.exists(P_LIST) else pd.DataFrame(columns=['slug', 'name', 'city', 'district'])
    if os.path.exists(P_CODES):
        cd = pd.read_csv(P_CODES, dtype=str).fillna('').rename(columns={'biggee_code': 'slug', 'ten': 'name', 'tinh': 'city', 'quan': 'district'})
        cd = cd[(cd['slug'] != '') & ~cd['slug'].isin(lst['slug'])][['slug', 'name', 'city', 'district']]
        lst = pd.concat([lst, cd], ignore_index=True)
    return lst.drop_duplicates('slug').reset_index(drop=True)


def match(min_score=0.6):
    """slug Biggee <-> project_id batdongsan: Jaccard token tên trong cùng tỉnh (tỉnh batdongsan từ geo_projects); cột ok sửa tay (1/0) giữ qua các lần.
    Mã = bảng giá web ∪ bảng mã API (project_names())."""
    lst = project_names()
    pr = pd.read_parquet(os.path.join(STORE, 'projects.parquet'))[['project_id', 'name']]
    geo = pd.read_parquet(os.path.join(STORE, 'geo_projects.parquet'))[['project_id', 'city', 'district']]
    b = pr.merge(geo, on='project_id', how='left'); b['tok'] = [set(_tok(n)) - set(_tok(c)) for n, c in zip(b['name'], b['city'].fillna(''))]
    b['prov'] = b['city'].fillna('').map(lambda x: ' '.join(_tok(x)))
    old = pd.read_csv(P_MATCH, dtype=str).fillna('') if os.path.exists(P_MATCH) else pd.DataFrame(columns=['slug', 'ok'])
    manual = {k: v for k, v in zip(old.get('slug', []), old.get('ok', [])) if v in ('0', '1')}
    out = []
    for _, r in lst.iterrows():
        prov = ' '.join(_tok(r['city'])); t = set(_tok(r['name'])) - set(_tok(r['city']))
        cand = b[b['prov'] == prov] if prov and (b['prov'] == prov).any() else b
        sc = cand['tok'].map(lambda x: len(x & t) / max(1, len(x | t)))
        j = sc.idxmax() if len(sc) and sc.max() > 0 else None; score = round(float(sc.max()), 2) if j is not None else 0
        if j is not None and len(cand.at[j, 'tok'] & t) < 2 and score < 0.99: score = min(score, 0.59)
        out.append({'slug': r['slug'], 'bg_name': r['name'], 'bg_city': r['city'], 'bg_district': r['district'], 'project_id': int(b.at[j, 'project_id']) if j is not None and score >= min_score else None,
                    'bds_name': b.at[j, 'name'] if j is not None else None, 'bds_district': b.at[j, 'district'] if j is not None else None, 'score': score, 'ok': manual.get(r['slug'], '')})
    m = pd.DataFrame(out).sort_values('score', ascending=False); m.to_csv(P_MATCH, index=False, encoding='utf-8-sig')
    print(f'ghép Biggee <-> batdongsan: {int(m["project_id"].notna().sum())}/{len(m)} (điểm ≥ {min_score}; ≥ 0,8: {(m["score"] >= 0.8).sum()}) -> {P_MATCH}')
    return m


def load_match():
    if not os.path.exists(P_MATCH): return pd.DataFrame()
    m = pd.read_csv(P_MATCH); m = m[m['project_id'].notna() & (m['ok'].astype(str) != '0')]
    return m[['slug', 'project_id', 'score']].astype({'project_id': int})


def load_history():
    """cho app: lịch sử tháng (triệu/m²) kèm project_id batdongsan"""
    if not os.path.exists(P_HIST): return pd.DataFrame()
    h = pd.read_parquet(P_HIST); h['ppm2'] = h['untprice'] / 1e6; h['dist_ppm2'] = h['dist_untprice'] / 1e6
    m = load_match()
    if len(m): h = h.merge(m[['slug', 'project_id']], on='slug', how='left')
    h = h.merge(project_names(), on='slug', how='left')
    return h


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--price-list', metavar='FILE'); ap.add_argument('--history', metavar='FILE'); ap.add_argument('--match', action='store_true')
    a = ap.parse_args(argv)
    if a.price_list: load_price_list_text(a.price_list)
    if a.history: load_history_jsonl(a.history)
    if a.match: match()
    return 0


if __name__ == '__main__':
    sys.exit(main())
