# -*- coding: utf-8 -*-
r"""
infra_layers.py - LỚP HẠ TẦNG & QUY HOẠCH cho trang Bản đồ của BĐS Tracker (18/10/2026).

Nguồn (xem D:\bat-dong-san\README.md mục 7):
  - OSM Overpass (batdongsan-projects/infra_fetch.py) -> store/infra/osm_infra.parquet: metro / đường sắt / cao tốc / quốc lộ / đường đang xây /
    đường quy hoạch / sân bay / cầu, mỗi đoạn 1 dòng với toạ độ JSON.
  - Ranh quy hoạch Hà Nội (GeoJSON của quyhoach.hanoi.vn) -> store/infra/hn_zones.parquet: 45 phân khu, QH chung, 15 đô thị vệ tinh (WKT).
  - Tile raster quy hoạch (chồng lên nền): TP.HCM Sở QHKT (bản đồ số QH sử dụng đất, ranh QH phân khu), Hà Nội (QH phân khu / QH chung / KHSDĐ /
    đô thị vệ tinh, tile do VietPalm dựng từ bản đồ công bố - nguồn thứ ba).
  - Tra cứu quy hoạch tại điểm (TP.HCM, API a-z/all của Sở QHKT) -> store/infra/hcm_qh_lookup.parquet (infra_fetch.py --hcm-lookup).
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import plotly.graph_objects as go

APP = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('BDS_STORE') or os.path.join(os.path.dirname(APP), 'batdongsan-projects', 'store')
D_INFRA = os.path.join(STORE, 'infra')

# ---- tile raster quy hoạch: key -> (nhãn, url template, opacity, nguồn, bbox (nam, tây, bắc, đông) để chỉ hiện khi phạm vi phù hợp)
TILES = {
    'hcm_sdd': ('QH sử dụng đất TP.HCM (Sở QHKT)', 'https://sqhkt-qlqh.tphcm.gov.vn/api/tiles/bandoso/{z}/{x}/{y}.png', 0.65, 'sqhkt-qlqh.tphcm.gov.vn', (10.3, 106.3, 11.2, 107.1)),
    'hcm_ranh': ('Ranh QH phân khu TP.HCM', 'https://sqhkt-qlqh.tphcm.gov.vn/api/tiles/ranh_qhpk_tphcm_v2/{z}/{x}/{y}.png', 0.9, 'sqhkt-qlqh.tphcm.gov.vn', (10.3, 106.3, 11.2, 107.1)),
    'hn_qhpk': ('QH phân khu Hà Nội', 'https://land.vietpalm.group/data/qhpk/{z}/{x}/{y}.png', 0.6, 'quyhoach.hanoi.vn / VietPalm', (20.5, 105.3, 21.4, 106.1)),
    'hn_qhc': ('QH chung Hà Nội 2030', 'https://s3-ap-southeast-1.amazonaws.com/vietpalm/maps/qhc/{z}/{x}/{y}.png', 0.6, 'quyhoach.hanoi.vn / VietPalm', (20.5, 105.3, 21.4, 106.1)),
    'hn_khsdd': ('Kế hoạch SDĐ Hà Nội', 'https://land.vietpalm.group/data/khsdd/{z}/{x}/{y}.png', 0.6, 'quyhoach.hanoi.vn / VietPalm', (20.5, 105.3, 21.4, 106.1)),
    'hn_dtvt': ('Đô thị vệ tinh Hà Nội', 'https://land.vietpalm.group/data/dtvt/{z}/{x}/{y}.png', 0.7, 'quyhoach.hanoi.vn / VietPalm', (20.5, 105.3, 21.4, 106.1)),
}
# ---- lớp vector OSM: layer -> (nhãn, màu theo trạng thái)
OSM_LAYERS = {
    'exp_plan': 'Cao tốc quy hoạch (sơ đồ QĐ 1454/1088)', 'metro': 'Metro / đường sắt đô thị', 'rail': 'Đường sắt', 'motorway': 'Cao tốc', 'trunk': 'Quốc lộ chính',
    'construction': 'Đường đang xây', 'proposed': 'Đường quy hoạch', 'airport': 'Sân bay', 'bridge': 'Cầu lớn',
}
COLOR = {('metro', 'operating'): '#7a1fa2', ('metro', 'construction'): '#c2185b', ('metro', 'proposed'): '#e591c4',
         ('rail', 'operating'): '#5d4037', ('rail', 'construction'): '#c2185b', ('rail', 'proposed'): '#e591c4',
         ('motorway', 'operating'): '#1565c0', ('trunk', 'operating'): '#64b5f6',
         ('construction', 'construction'): '#e65100', ('proposed', 'proposed'): '#ffb74d',
         ('airport', 'operating'): '#2e7d32', ('airport', 'construction'): '#e65100', ('airport', 'proposed'): '#ffb74d', ('bridge', 'operating'): '#455a64',
         ('exp_plan', 'operating'): '#90a4ae', ('exp_plan', 'construction'): '#ef6c00', ('exp_plan', 'proposed'): '#d81b60'}
STATUS_VI = {'operating': 'đang khai thác', 'construction': 'đang xây', 'proposed': 'quy hoạch'}
WIDTH = {'metro': 3, 'rail': 2, 'motorway': 3, 'trunk': 1.5, 'construction': 3, 'proposed': 2.5, 'airport': 2, 'bridge': 3, 'exp_plan': 2.5}


def stamp():
    fs = [os.path.join(D_INFRA, f) for f in ('osm_infra.parquet', 'hn_zones.parquet', 'hcm_qh_lookup.parquet', 'expressway_plan.parquet')]
    return '|'.join(f'{os.path.getsize(f)}:{int(os.path.getmtime(f))}' for f in fs if os.path.exists(f))


def load_osm():
    """OSM + sơ đồ cao tốc quy hoạch (expressway_plan.py, layer 'exp_plan') trong 1 bảng"""
    parts = [pd.read_parquet(os.path.join(D_INFRA, f)) for f in ('osm_infra.parquet', 'expressway_plan.parquet') if os.path.exists(os.path.join(D_INFRA, f))]
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def load_zones():
    p = os.path.join(D_INFRA, 'hn_zones.parquet')
    return pd.read_parquet(p) if os.path.exists(p) else pd.DataFrame()


def load_hcm_lookup():
    p = os.path.join(D_INFRA, 'hcm_qh_lookup.parquet')
    return pd.read_parquet(p) if os.path.exists(p) else pd.DataFrame()


def in_bbox(df, bbox, margin=0.0):
    """giữ các đoạn có khung bao giao với bbox (nam, tây, bắc, đông)"""
    if df.empty or bbox is None: return df
    s, w, n, e = bbox
    return df[(df['lat_max'] >= s - margin) & (df['lat_min'] <= n + margin) & (df['lng_max'] >= w - margin) & (df['lng_min'] <= e + margin)]


def _thin(coords, max_pts=60):
    if len(coords) <= max_pts: return coords
    step = int(np.ceil(len(coords) / max_pts)); out = coords[::step]
    return out if out[-1] == coords[-1] else out + [coords[-1]]


# ---------------------------------------------------------------- "texture" đường: nhiều lớp vẽ chồng (18/10/2026)
# Scattermap chỉ có width + màu, không có nét đứt -> vạch kẻ / nét đứt / tà vẹt được sinh thành các đoạn ngắn theo khoảng cách mét.
# style = danh sách lớp vẽ từ dưới lên: (độ rộng px, màu, kiểu) kiểu = 'solid' | ('dash', on_m, off_m) tính theo tỉ lệ `scale`
# (scale = 1 ~ phạm vi tỉnh ~100 km; cấp dự án 0,05; toàn quốc 10).
def _dash(on, off): return ('dash', on, off)


STYLES = {
    # 20/10/2026: TÔNG TỐI toàn bộ (PV2) - vẫn giữ texture: (viền, lòng, vạch) / nét đứt / tà vẹt
    # cao tốc đang khai thác: viền đen, lòng nâu sẫm, vạch xám sáng giữa
    ('motorway', 'operating'): [(7, '#111111', 'solid'), (5, '#3e2723', 'solid'), (1.2, '#bdbdbd', _dash(500, 400))],
    ('exp_plan', 'operating'): [(7, '#111111', 'solid'), (5, '#3e2723', 'solid'), (1.2, '#bdbdbd', _dash(500, 400))],
    # quốc lộ: viền than, lòng xám xanh đậm, vạch xám
    ('trunk', 'operating'): [(5, '#1c262b', 'solid'), (3.2, '#455a64', 'solid'), (0.9, '#90a4ae', _dash(400, 400))],
    # đường đang xây: nét đứt dài, viền đen lòng nâu
    ('construction', 'construction'): [(6, '#212121', _dash(900, 300)), (3.5, '#6d4c41', _dash(900, 300))],
    ('exp_plan', 'construction'): [(7, '#212121', _dash(900, 300)), (4.5, '#795548', _dash(900, 300))],
    # quy hoạch: nét đứt tím than trên nền mờ
    ('proposed', 'proposed'): [(5, 'rgba(33,33,33,0.15)', 'solid'), (2.5, '#4a148c', _dash(600, 500))],
    ('exp_plan', 'proposed'): [(6, 'rgba(33,33,33,0.15)', 'solid'), (3, '#311b92', _dash(700, 500))],
    # metro / đường sắt: nền đen/xanh than + tà vẹt xám sáng xen kẽ
    ('metro', 'operating'): [(6, '#0d1b2a', 'solid'), (3.5, '#b0bec5', _dash(250, 250))],
    ('metro', 'construction'): [(6, '#3e2723', 'solid'), (3.5, '#bcaaa4', _dash(250, 250))],
    ('metro', 'proposed'): [(5, 'rgba(49,27,146,0.3)', 'solid'), (3, '#311b92', _dash(400, 400))],
    ('rail', 'operating'): [(4.5, '#000000', 'solid'), (2.5, '#9e9e9e', _dash(300, 300))],
    ('rail', 'construction'): [(4.5, '#3e2723', 'solid'), (2.5, '#bcaaa4', _dash(300, 300))],
    ('rail', 'proposed'): [(3.5, 'rgba(62,39,35,0.3)', 'solid'), (2, '#3e2723', _dash(400, 400))],
    # sân bay, cầu
    ('airport', 'operating'): [(3, '#1b3a1e', 'solid'), (1.5, '#4a6b4d', _dash(300, 200))],
    ('airport', 'construction'): [(3, '#4e342e', _dash(400, 200))],
    ('airport', 'proposed'): [(2.5, '#5d4037', _dash(400, 300))],
    ('bridge', 'operating'): [(6, '#000000', 'solid'), (3, '#546e7a', 'solid')],
}
DEFAULT_STYLE = [(3, '#424242', 'solid')]


def _dash_segments(coords, on_m, off_m):
    """cắt polyline [[lng,lat],...] thành các đoạn 'on' dài on_m, cách nhau off_m (mét, xấp xỉ phẳng)"""
    segs, cur, on = [], [], True; remain = on_m
    for (x0, y0), (x1, y1) in zip(coords[:-1], coords[1:]):
        k = 111320.0 * np.cos(np.radians((y0 + y1) / 2)); dx = (x1 - x0) * k; dy = (y1 - y0) * 111320.0
        L = float(np.hypot(dx, dy)); pos = 0.0
        if L == 0: continue
        if on and not cur: cur = [[x0, y0]]
        while L - pos > remain:
            pos += remain; t = pos / L; px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            if on: cur.append([px, py]); segs.append(cur); cur = []
            else: cur = [[px, py]]
            on = not on; remain = on_m if on else off_m
        remain -= (L - pos)
        if on: cur.append([x1, y1])
    if on and len(cur) > 1: segs.append(cur)
    return segs


def _trace(fig, segs, width, color, name, texts=None, hover=False):
    lats, lngs, tx = [], [], []
    for i, c in enumerate(segs):
        lngs += [p[0] for p in c] + [None]; lats += [p[1] for p in c] + [None]
        if texts is not None: tx += [texts[i]] * len(c) + [None]
    if not lats: return
    fig.add_trace(go.Scattermap(lat=lats, lon=lngs, mode='lines', name=name, line=dict(width=width, color=color), showlegend=False,
                                hoverinfo='text' if hover else 'skip', text=tx if hover else None))


def add_osm_traces(fig, osm: pd.DataFrame, layers, bbox=None, statuses=('operating', 'construction', 'proposed'), max_pts=60, scale=1.0):
    """vẽ hạ tầng có texture: mỗi (layer, status) = vài lớp Scattermap chồng nhau; không legend, chỉ hover (lớp lòng đường).
    scale: tỉ lệ độ dài vạch (1 = phạm vi tỉnh; cấp dự án ~0,05; toàn quốc ~10)."""
    if osm is None or osm.empty: return 0
    d = in_bbox(osm, bbox, margin=0.05) if bbox else osm
    d = d[d['layer'].isin(layers) & d['status'].isin(statuses)]
    n = 0
    order = ['trunk', 'motorway', 'rail', 'bridge', 'airport', 'construction', 'proposed', 'exp_plan', 'metro']   # vẽ sau = nổi trên
    for layer in order:
        for status in ('operating', 'construction', 'proposed'):
            g = d[(d['layer'] == layer) & (d['status'] == status)]
            if g.empty: continue
            lines, texts = [], []
            for _, r in g.iterrows():
                # 20/10/2026: đoạn cao tốc bám hình OSM có nhiều điểm (đi qua từng nút giao) -> làm thưa nhẹ hơn lớp OSM thường
                c = _thin(json.loads(r['coords']), max_pts * 12 if layer == 'exp_plan' else max_pts)
                if len(c) < 2: continue
                lines.append(c)
                if layer == 'exp_plan':
                    hz = {'2030': 'đầu tư trước 2030', '2050': 'đầu tư sau 2030'}.get(str(r.get('horizon')), '')
                    src = str(r.get('geom_src') or 'schematic')
                    how = {'osm': f"hướng tuyến theo OSM (bám đường thật, qua từng nút giao)", 'mixed': f"một phần theo OSM ({r.get('osm_pairs')} chặng), phần còn lại SƠ ĐỒ nối địa danh"}.get(
                        src, 'SƠ ĐỒ (nối địa danh, nắn qua nút giao chèn tại giao cắt với đường OSM; không phải hướng tuyến)')
                    nodes = json.loads(r['nodes']) if isinstance(r.get('nodes'), str) and r.get('nodes') else []
                    nd = ' · '.join(n['cross'] for n in nodes[:10]) + (f' · … (+{len(nodes) - 10})' if len(nodes) > 10 else '')
                    texts.append(f"<b>{r['name']}</b><br>{how}<br>{STATUS_VI.get(status, status)}" + (f" · {hz}" if hz else '') + f" · {r.get('lanes')} làn"
                                 + (f" · {r.get('length_km')} km" if r.get('length_km') else '') + f"<br>{r.get('waypoints')}" + (f"<br>Nút giao ({len(nodes)}): {nd}" if nodes else ''))
                else:
                    texts.append(f"<b>{r['name'] or r['ref'] or OSM_LAYERS.get(layer, layer)}</b><br>{OSM_LAYERS.get(layer, layer)} · {STATUS_VI.get(status, status)}"
                                 + (f"<br>dự kiến {r['opening_date']}" if r.get('opening_date') else ''))
            if not lines: continue
            style = STYLES.get((layer, status), DEFAULT_STYLE); nm = f"{OSM_LAYERS.get(layer, layer)} ({STATUS_VI.get(status, status)})"
            for k, (w, col, pat) in enumerate(style):
                hover = (k == min(1, len(style) - 1))                       # lớp lòng đường (lớp thứ 2) nhận hover; viền/vạch bỏ qua
                if pat == 'solid':
                    _trace(fig, lines, w, col, nm, texts, hover)
                else:
                    _, on, off = pat; on *= scale; off *= scale
                    segs, tx = [], []
                    for c, t in zip(lines, texts):
                        ds = _dash_segments(c, on, off); segs += ds; tx += [t] * len(ds)
                    _trace(fig, segs, w, col, nm, tx, hover)
            n += len(lines)
    if 'exp_plan' in layers: add_node_traces(fig, d[d['layer'] == 'exp_plan'], bbox)
    return n


def add_node_traces(fig, ex: pd.DataFrame, bbox=None):
    """20/10/2026: chấm NÚT GIAO của sơ đồ cao tốc (cột `nodes` JSON: name, cross, lat, lng, kind) - 2 lớp: viền trắng + chấm đậm (có hover).
    Nút trùng vị trí giữa 2 tuyến (CT.01 × CT.40 có ở cả 2 đoạn) gộp 1 chấm, hover ghi cả 2 tuyến."""
    if ex is None or ex.empty or 'nodes' not in ex.columns: return 0
    pts = {}
    for _, r in ex.iterrows():
        if not isinstance(r['nodes'], str) or not r['nodes']: continue
        for nd in json.loads(r['nodes']):
            if bbox is not None and not (bbox[0] - 0.05 <= nd['lat'] <= bbox[2] + 0.05 and bbox[1] - 0.05 <= nd['lng'] <= bbox[3] + 0.05): continue
            k = (round(nd['lat'], 3), round(nd['lng'], 3))
            how = {'osm': 'vị trí theo OSM', 'manual': 'nhập tay theo QĐ', 'plan': 'sơ đồ: giao cắt với đường OSM'}.get(nd.get('kind'), '')
            line = f"{r['ref']} × {nd['cross']}" + (f" · {how}" if how else '')
            if k in pts: pts[k][1].append(line)
            else: pts[k] = (nd['name'], [line], nd['lat'], nd['lng'])
    if not pts: return 0
    lats = [v[2] for v in pts.values()]; lngs = [v[3] for v in pts.values()]
    texts = [f"<b>{v[0]}</b><br>" + '<br>'.join(dict.fromkeys(v[1])) for v in pts.values()]
    fig.add_trace(go.Scattermap(lat=lats, lon=lngs, mode='markers', name='Nút giao', marker=dict(size=9, color='#cfd8dc', opacity=0.9), hoverinfo='skip', showlegend=False))
    fig.add_trace(go.Scattermap(lat=lats, lon=lngs, mode='markers', name='Nút giao', marker=dict(size=5, color='#111111', opacity=1), hoverinfo='text', text=texts, showlegend=False))
    return len(pts)


def add_zone_traces(fig, zones: pd.DataFrame, layers=('Quy hoạch phân khu',), bbox=None):
    """ranh quy hoạch Hà Nội (WKT polygon) -> đường viền + tên"""
    if zones is None or zones.empty: return 0
    from shapely import wkt
    z = zones[zones['layer'].isin(layers)]
    if bbox: z = in_bbox(z, bbox, margin=0.05)
    lats, lngs, texts, cx, cy, names = [], [], [], [], [], []
    for _, r in z.iterrows():
        g = wkt.loads(r['wkt']); polys = list(g.geoms) if g.geom_type == 'MultiPolygon' else [g]
        for p in polys:
            xs, ys = p.exterior.coords.xy; c = _thin(list(zip(xs, ys)), 120)
            lngs += [q[0] for q in c] + [None]; lats += [q[1] for q in c] + [None]
            texts += [f"{r['name']}<br>{r['layer']} · {r['area_ha']} ha · dân số {r['population']}<br>{r['note']}"] * len(c) + [None]
        ctr = g.representative_point(); cx.append(ctr.x); cy.append(ctr.y); names.append(str(r['name']).replace('PHÂN KHU ', ''))
    if not lats: return 0
    fig.add_trace(go.Scattermap(lat=lats, lon=lngs, mode='lines', name='Ranh QH phân khu HN', line=dict(width=1.5, color='#6d4c41'), hoverinfo='text', text=texts))
    fig.add_trace(go.Scattermap(lat=cy, lon=cx, mode='text', text=names, textfont=dict(size=10, color='#4e342e'), name='Tên phân khu', hoverinfo='skip', showlegend=False))
    return len(z)


PROXY = {'base': None}     # app.py đặt = tile_proxy.base_url(host): tile gốc không có CORS -> đi qua proxy localhost:8768


def raster_layers(keys, bbox=None, opacity=None):
    """map_layers Plotly cho các tile chọn; bbox để chỉ bật tile phù hợp phạm vi (tránh tải tile vô ích)"""
    out = []
    for k in keys:
        if k not in TILES: continue
        lab, url, op, src, tb = TILES[k]
        if bbox is not None:
            s, w, n, e = bbox; ts, tw, tn, te = tb
            if n < ts or s > tn or e < tw or w > te: continue
        if PROXY['base']: url = f"{PROXY['base']}/t/{k}/{{z}}/{{x}}/{{y}}.png"
        out.append({'below': 'traces', 'sourcetype': 'raster', 'source': [url], 'opacity': opacity if opacity is not None else op,
                    'sourceattribution': f'{lab} © {src}', 'minzoom': 8, 'maxzoom': 19})
    return out


def tiles_for_bbox(bbox):
    if bbox is None: return list(TILES)
    s, w, n, e = bbox
    return [k for k, (_, _, _, _, tb) in TILES.items() if not (n < tb[0] or s > tb[2] or e < tb[1] or w > tb[3])]


def hcm_lookup_summary(row) -> dict:
    """1 dòng hcm_qh_lookup -> các mục hiển thị"""
    out = {}
    for k in ['parcel_area', 'parcel_no', 'docs', 'landuse', 'roads', 'dccb', 'fetched']:
        if k in row and pd.notna(row[k]) and row[k] not in ('', '[]'): out[k] = row[k]
    return out
