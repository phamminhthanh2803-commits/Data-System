# -*- coding: utf-8 -*-
r"""
infra_fetch.py - kéo LỚP HẠ TẦNG từ OpenStreetMap (Overpass API) cho bản đồ dự án (18/10/2026) -> store/infra/osm_infra.parquet.

Lớp (toàn Việt Nam, 1 truy vấn ~1,5 phút):
  metro       railway=subway|light_rail (đang khai thác) + railway=construction (construction=subway|light_rail|rail) + railway=proposed
  rail        railway=rail đang khai thác (tuyến Bắc-Nam, …) - chỉ tuyến chính (usage=main)
  motorway    highway=motorway|motorway_link đang khai thác (cao tốc)
  trunk       highway=trunk (quốc lộ chính)
  construction highway=construction (đường đang xây: cao tốc, vành đai, cầu…) + construction=* ghi loại đường
  proposed    highway=proposed (đường quy hoạch) + proposed=* ghi loại đường
  airport     aeroway=aerodrome (sân bay, gồm đang xây/quy hoạch nếu có tag)
  bridge      man_made=bridge hoặc bridge=yes trên construction/proposed (có tên)
Mỗi way -> 1 dòng: osm_id, layer, kind (loại cụ thể), status (operating|construction|proposed), name, ref, opening_date, operator, coords (list [lng, lat]),
lat_min/max, lng_min/max (để lọc nhanh theo khung nhìn). Chạy tuần 1 lần là đủ (OSM đổi chậm).

    python infra_fetch.py                 # toàn VN
    python infra_fetch.py --bbox 20.5,105.3,21.4,106.2   # chỉ 1 khung (nam,tây,bắc,đông) để thử
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('BDS_STORE') or os.path.join(HERE, 'store')
D_INFRA = os.path.join(STORE, 'infra')
P_OSM = os.path.join(D_INFRA, 'osm_infra.parquet')
ENDPOINTS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter', 'https://overpass.private.coffee/api/interpreter']
UA = 'bds-tracker/0.1 (nghien cuu thi truong BDS; lien he investment.idea.9x@gmail.com)'


GROUPS = {
    'rail': '''way["railway"~"^(subway|light_rail|monorail|proposed|construction)$"]{A};
  way["railway"="rail"]["usage"="main"]{A};
  way["aeroway"="aerodrome"]{A};
  relation["aeroway"="aerodrome"]{A};
  way["man_made"="bridge"]["name"]{A};''',
    'road': '''way["highway"~"^(motorway|motorway_link|trunk|construction|proposed)$"]{A};''',
}
# Overpass 504 khi hỏi cả nước 1 lần (18/10/2026) -> chia dải vĩ độ × nhóm lớp, mỗi truy vấn ~10-40 s
BANDS = [(8.3, 11.0), (11.0, 13.5), (13.5, 16.0), (16.0, 18.5), (18.5, 20.5), (20.5, 21.6), (21.6, 23.5)]
LNG = (102.0, 110.0)


def query(group, bbox):
    s, w, n, e = bbox
    return f'''[out:json][timeout:300][maxsize:536870912];
(
  {GROUPS[group].replace('{A}', f'({s},{w},{n},{e})')}
);
out tags geom;'''


def classify(t):
    rw, hw = t.get('railway', ''), t.get('highway', '')
    if t.get('aeroway') == 'aerodrome':
        st = 'construction' if t.get('construction') or t.get('aerodrome') == 'construction' else ('proposed' if t.get('proposed') else 'operating')
        return 'airport', 'airport', st
    if t.get('man_made') == 'bridge': return 'bridge', 'bridge', 'operating'
    if rw in ('subway', 'light_rail', 'monorail'): return 'metro', rw, 'operating'
    if rw == 'construction':
        k = t.get('construction', 'rail'); return ('metro' if k in ('subway', 'light_rail', 'monorail') else 'rail'), k, 'construction'
    if rw == 'proposed':
        k = t.get('proposed', 'rail'); return ('metro' if k in ('subway', 'light_rail', 'monorail') else 'rail'), k, 'proposed'
    if rw == 'rail': return 'rail', 'rail', 'operating'
    if hw in ('motorway', 'motorway_link'): return 'motorway', hw, 'operating'
    if hw == 'trunk': return 'trunk', hw, 'operating'
    if hw == 'construction': return 'construction', t.get('construction', 'road'), 'construction'
    if hw == 'proposed': return 'proposed', t.get('proposed', 'road'), 'proposed'
    return 'other', hw or rw, 'operating'


def fetch(q, log=print):
    data = urllib.parse.urlencode({'data': q}).encode()
    for ep in ENDPOINTS:
        t0 = time.time()
        try:
            req = urllib.request.Request(ep, data=data, headers={'User-Agent': UA, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=900) as r: body = r.read()
            j = json.loads(body); log(f'  {ep}: {len(j.get("elements", []))} phần tử, {len(body) / 1e6:.1f} MB, {time.time() - t0:.0f}s'); return j
        except Exception as e:  # noqa: BLE001
            log(f'  {ep}: LOI {str(e)[:150]}')
    return None


def to_rows(j, today):
    rows = []
    for el in j.get('elements', []):
        t = el.get('tags', {}) or {}
        geoms = []
        if el['type'] == 'way': geoms = [el.get('geometry') or []]
        elif el['type'] == 'relation':
            geoms = [m.get('geometry') or [] for m in el.get('members', []) if m.get('type') == 'way' and m.get('geometry')]
        for g in geoms:
            if len(g) < 2: continue
            layer, kind, status = classify(t)
            lats = [p['lat'] for p in g]; lngs = [p['lon'] for p in g]
            rows.append({'osm_id': f"{el['type'][0]}{el['id']}", 'layer': layer, 'kind': kind, 'status': status, 'name': t.get('name') or t.get('name:vi'),
                         'ref': t.get('ref'), 'opening_date': t.get('opening_date'), 'operator': t.get('operator'), 'bridge': t.get('bridge'),
                         'lanes': t.get('lanes'), 'coords': json.dumps([[round(x, 6), round(y, 6)] for x, y in zip(lngs, lats)]),
                         'lat_min': min(lats), 'lat_max': max(lats), 'lng_min': min(lngs), 'lng_max': max(lngs), 'n_pts': len(g), 'fetched': today})
    return pd.DataFrame(rows)


def clip_vn(df):
    """bỏ đoạn ngoài biên giới VN (dải bbox 102–110 kinh độ phủ cả Nam Ninh TQ, Lào, Thái, Campuchia); ranh geoBoundaries ADM0 +0,02°"""
    p = os.path.join(D_INFRA, 'vn_boundary.geojson')
    if not os.path.exists(p) or df.empty: return df
    from shapely.geometry import shape, Point
    from shapely.prepared import prep
    pg = prep(shape(json.load(open(p, encoding='utf-8'))['features'][0]['geometry']).buffer(0.02))
    def inside(c):
        pts = json.loads(c); mid = pts[len(pts) // 2]
        return pg.contains(Point(mid[0], mid[1])) or pg.contains(Point(pts[0][0], pts[0][1]))
    return df[df['coords'].map(inside)]


def load():
    return pd.read_parquet(P_OSM) if os.path.exists(P_OSM) else pd.DataFrame()


# ================================================================ tra cứu quy hoạch tại điểm - TP.HCM (API a-z/all của Sở QHKT, cổng thongtinquyhoach.hochiminhcity.gov.vn)
P_HCM = os.path.join(D_INFRA, 'hcm_qh_lookup.parquet')
D_HCM_RAW = os.path.join(D_INFRA, 'hcm_raw')
AZ_URL = 'https://sqhkt-qlqh.tphcm.gov.vn/computing/930/api/v3.1/a-z/all'
HCM_BBOX = (10.35, 106.35, 11.16, 107.03)


def _j(v):
    if isinstance(v, str):
        try: return json.loads(v)
        except Exception: return v  # noqa: BLE001
    return v


def parse_az(j):
    """response a-z/all -> dict tóm tắt (thửa đất tại điểm: diện tích, số tờ/thửa, phường; đồ án QHPK; chức năng SDĐ + % diện tích; lộ giới; điều chỉnh cục bộ)"""
    ttc = _j(j.get('ThongTinChung')) or {}
    if not isinstance(ttc, dict): ttc = {}
    docs = [{'ten': d.get('tendoan'), 'soqd': d.get('soqd'), 'ngay': d.get('ngayduyet'), 'coquan': d.get('coquanpd')} for d in (ttc.get('dsttdoan') or [])]
    lu = []
    for f in _j(j.get('QHPK')) or []:
        p = f.get('properties') or {}
        try: pct = float(p.get('tldientich') or 0)
        except (TypeError, ValueError): pct = 0.0
        lu.append({'chucnang': p.get('chucnang'), 'ma': p.get('maquyuoc'), 'pct': round(pct, 1), 'dientich': p.get('dientich')})
    lu.sort(key=lambda x: -x['pct'])
    roads = [{'duong': (f.get('properties') or {}).get('tenduong'), 'logioi': (f.get('properties') or {}).get('logioi'), 'huong': (f.get('properties') or {}).get('huongtiepgiap')} for f in _j(j.get('LoGioi')) or []]
    dccb = [{'ten': (f.get('properties') or {}).get('tendccb'), 'soqd': (f.get('properties') or {}).get('soqd'), 'ngay': (f.get('properties') or {}).get('ngayduyet')} for f in _j(j.get('DCCB')) or []]
    def num(v):
        try: return float(v)
        except (TypeError, ValueError): return None
    return {'parcel_area': num(ttc.get('dientich')), 'parcel_no': f"tờ {ttc.get('soto')} thửa {ttc.get('sothua')}" if ttc.get('sothua') else None,
            'district': ttc.get('tenquanhuyen'), 'ward': ttc.get('tenphuongxa'), 'n_docs': len(docs), 'docs': json.dumps(docs, ensure_ascii=False) if docs else None,
            'main_landuse': lu[0]['chucnang'] if lu else None, 'main_landuse_pct': lu[0]['pct'] if lu else None,
            'landuse': json.dumps(lu, ensure_ascii=False) if lu else None, 'roads': json.dumps(roads, ensure_ascii=False) if roads else None,
            'dccb': json.dumps(dccb, ensure_ascii=False) if dccb else None, 'n_qhchitiet': len(_j(j.get('QHChiTiet')) or []), 'n_qhnganh': len(_j(j.get('QHNganh')) or []),
            'blocked': j.get('blocked')}


def hcm_lookup(n, delay=1.2):
    """n dự án batdongsan ở TP.HCM (geo city) có toạ độ, chưa tra -> POST Lat/Lon -> hcm_qh_lookup.parquet (+ JSON thô hcm_raw/<project_id>.json)"""
    from curl_cffi import requests as creq
    pr = pd.read_parquet(os.path.join(STORE, 'projects.parquet')); ge = pd.read_parquet(os.path.join(STORE, 'geo_projects.parquet'))
    pr = pr.merge(ge[['project_id', 'city']].rename(columns={'city': 'g_city'}), on='project_id', how='left')
    pr = pr[(pr['g_city'] == 'Hồ Chí Minh') & pr['lat'].between(HCM_BBOX[0], HCM_BBOX[2]) & pr['lng'].between(HCM_BBOX[1], HCM_BBOX[3])]
    old = pd.read_parquet(P_HCM) if os.path.exists(P_HCM) else pd.DataFrame()
    done = set(old['project_id']) if len(old) else set()
    todo = pr[~pr['project_id'].isin(done)].sort_values('status').head(n)
    print(f'hcm-lookup: {len(pr)} dự án HCM có toạ độ, đã tra {len(done)}, tra thêm {len(todo)}', flush=True)
    S = creq.Session(impersonate='chrome124'); H = {'Referer': 'https://thongtinquyhoach.hochiminhcity.gov.vn/', 'Origin': 'https://thongtinquyhoach.hochiminhcity.gov.vn'}
    os.makedirs(D_HCM_RAW, exist_ok=True); rows = []; err = 0; today = date.today().isoformat()
    for i, r in enumerate(todo.itertuples(), 1):
        try:
            resp = S.post(AZ_URL, data={'Lat': float(r.lat), 'Lon': float(r.lng)}, headers=H, timeout=40); time.sleep(delay)
            if resp.status_code != 200 or not resp.text.strip():
                rows.append({'project_id': int(r.project_id), 'lat': r.lat, 'lng': r.lng, 'fetched': today, 'status_http': resp.status_code, 'empty': True}); continue
            try: j = resp.json()
            except Exception:  # noqa: BLE001 - vài điểm server trả dict kiểu Python (nháy đơn) thay vì JSON
                import ast
                try: j = ast.literal_eval(resp.text)
                except Exception: j = None  # noqa: BLE001
            if not isinstance(j, dict):
                rows.append({'project_id': int(r.project_id), 'lat': r.lat, 'lng': r.lng, 'fetched': today, 'status_http': 200, 'empty': True}); continue
            json.dump(j, open(os.path.join(D_HCM_RAW, f'{int(r.project_id)}.json'), 'w', encoding='utf-8'), ensure_ascii=False)
            rows.append({'project_id': int(r.project_id), 'lat': r.lat, 'lng': r.lng, 'fetched': today, 'status_http': 200, 'empty': False, **parse_az(j)})
        except Exception as e:  # noqa: BLE001
            err += 1; print(f'  LOI pj{r.project_id}: {str(e)[:120]}', flush=True); time.sleep(5)
        if i % 25 == 0: print(f'  {i}/{len(todo)} ({err} lỗi)', flush=True)
    if rows:
        new = pd.DataFrame(rows); allr = pd.concat([old, new], ignore_index=True).drop_duplicates('project_id', keep='last')
        for c in allr.columns:
            if allr[c].dtype == object: allr[c] = allr[c].where(allr[c].notna(), None)
        allr.to_parquet(P_HCM, index=False)
    have = sum(1 for x in rows if not x.get('empty'))
    print(f'DONE hcm-lookup: {len(rows)} dự án tra, {have} có dữ liệu, {err} lỗi; kho {len(done) + len(rows)}', flush=True)
    return len(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--bbox', default=None, help='nam,tây,bắc,đông (mặc định: cả Việt Nam)')
    ap.add_argument('--hcm-lookup', type=int, default=None, metavar='N', help='tra quy hoạch tại điểm cho N dự án TP.HCM (không kéo OSM)')
    a = ap.parse_args(argv); t0 = time.time(); today = date.today().isoformat()
    if a.hcm_lookup is not None:
        return 0 if hcm_lookup(a.hcm_lookup) else 1
    if a.bbox:
        s_, w_, n_, e_ = [float(x) for x in a.bbox.split(',')]; boxes = [(s_, w_, n_, e_)]
    else:
        boxes = [(s_, LNG[0], n_, LNG[1]) for s_, n_ in BANDS]
    parts = []
    for bb in boxes:
        for grp in GROUPS:
            print(f'infra: {grp} {bb} …', flush=True)
            j = fetch(query(grp, bb), log=lambda m: print(m, flush=True))
            if j is None: print(f'  bỏ qua {grp} {bb}', flush=True); continue
            parts.append(to_rows(j, today)); time.sleep(3)
    df = pd.concat([x for x in parts if len(x)], ignore_index=True) if parts else pd.DataFrame()
    if len(df): df = clip_vn(df.drop_duplicates('osm_id'))
    if df.empty: print('ERROR infra: 0 dòng', flush=True); return 1
    os.makedirs(D_INFRA, exist_ok=True)
    if a.bbox and os.path.exists(P_OSM):
        old = load(); df = pd.concat([old[~old['osm_id'].isin(df['osm_id'])], df], ignore_index=True)
    df.to_parquet(P_OSM, index=False)
    summ = df.groupby(['layer', 'status']).size().to_dict()
    print(f'DONE infra: {len(df)} đoạn -> {P_OSM} | {summ} | {time.time() - t0:.0f}s', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
