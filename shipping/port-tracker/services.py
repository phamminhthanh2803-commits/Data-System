# -*- coding: utf-8 -*-
"""
services.py - vòng tuyến từng tàu + gom TUYẾN DỊCH VỤ từ lượt ghé toàn cầu EconDB (store/econdb/vessel_portcalls.parquet, 16/10/2026).

  rotations(pc)            : 1 dòng/tàu: các cảng ghé LẶP LẠI trong cửa sổ (mặc định 120 ngày) theo thứ tự ghé = vòng tuyến,
                             cảng VN trên vòng, lượt ghé cuối, cảng cuối
  cluster(rot, ops)        : gom tàu có tập cảng vòng tuyến giống nhau (Jaccard >= 0,6) thành 1 DỊCH VỤ; hãng của dịch vụ = đa số
                             hãng đã biết của các tàu trong dịch vụ (ops: imo -> hãng)
  infer_operator(svc, ...) : tàu chưa rõ hãng thuộc dịch vụ có 1 hãng chiếm >= 60% (>= 2 tàu đã biết) -> gán hãng đó

Hãng EconDB (vessels.parquet: operator_name) đổi về tên hãng của app bằng OP_ALIAS.
"""
import re
import unicodedata
from collections import Counter

import pandas as pd

WINDOW_DAYS = 120
JACCARD = 0.6
INFER_SHARE = 0.6

# tên hãng EconDB -> tên hãng trong app (carriers.csv)
OP_ALIAS = {
    'Mediterranean Shipping': 'MSC', 'Cosco': 'COSCO', 'Ocean Network Express': 'ONE', 'Wan Hai': 'Wan Hai Lines',
    'Pacific International': 'PIL', 'T.S. Lines': 'TS Lines', 'Korea Marine Transport': 'KMTC', 'Emirates Shipping Line': 'Emirates Shipping',
    'Interasia Lines': 'Interasia', 'China United': 'CUL', 'Heung-A Shipping': 'Heung-A', 'Hai An Transport and Stevedoring JSC': 'Hai An (HAH)',
    'Shanghai Jinjiang Shipping': 'Jinjiang Shipping', 'Ningbo Ocean Shipping': 'Ningbo Ocean Shipping (NBOSCO)',
    'Global Feeder Shipping': 'Global Feeder Shipping (GFS)', 'Sinokor': 'Sinokor', 'Namsung': 'Namsung',
}
# chủ tàu EconDB (khi EconDB không ghi hãng) -> hãng: chỉ chủ tàu TỰ KHAI THÁC (không phải chủ cho thuê như Zodiac, Costamare, Seaspan)
OWNER_OPERATOR = [
    (r'THILOGI|TRUONG HAI', 'THILOGI (THACO)'), (r'VIETNAM MARITIME|VIMC', 'VIMC Lines (Bien Dong)'), (r'GLS SHIPPING|GEMADEPT', 'GLS'),
    (r'HAI AN TRANSPORT', 'Hai An (HAH)'), (r'VINAFCO', 'Vinafco'), (r'VIETSUN', 'Vietsun'), (r'TAN CANG', 'Tan Cang Shipping (SNP)'),
    (r'VIETNAM OCEAN SHIPPING|VOSCO', 'VOSCO'), (r'VSICO', 'VSICO'), (r'SALAM PACIFIC', 'SPIL (Salam Pacific)'), (r'PAN OCEAN', 'Pan Ocean'),
    (r'ASEAN SEAS LINE', 'ASEAN Seas Line'), (r'TRANSFAR', 'Transfar Shipping'), (r'JINJIANG', 'Jinjiang Shipping'), (r'SINOKOR', 'Sinokor'),
    (r'KOREA MARINE TRANSPORT|\bKMTC\b', 'KMTC'), (r'NAMSUNG', 'Namsung'), (r'HEUNG.?A', 'Heung-A'), (r'DONGJIN', 'Dongjin'),
    (r'PAN CONTINENTAL|PANCON', 'Pancon'), (r'SITC', 'SITC'), (r'WAN HAI', 'Wan Hai Lines'), (r'EVERGREEN', 'Evergreen'),
    (r'YANG MING', 'Yang Ming'), (r'CMA CGM|\bAPL\b|CNC', 'CMA CGM'), (r'MAERSK', 'Maersk'), (r'MEDITERRANEAN SHIPPING|\bMSC\b', 'MSC'),
    (r'COSCO|CHINA SHIPPING|ORIENT OVERSEAS', 'COSCO'), (r'OCEAN NETWORK EXPRESS', 'ONE'), (r'HAPAG', 'Hapag-Lloyd'),
    (r'PACIFIC INTERNATIONAL LINES', 'PIL'), (r'HMM|HYUNDAI MERCHANT', 'HMM'), (r'\bZIM\b', 'ZIM'), (r'REGIONAL CONTAINER', 'RCL'),
    (r'SAMUDERA', 'Samudera'), (r'X-PRESS', 'X-Press Feeders'), (r'TS LINES', 'TS Lines'), (r'INTERASIA', 'Interasia'),
    (r'CHINA UNITED', 'CUL'), (r'SINOTRANS', 'Sinotrans'), (r'KANWAY', 'Kanway Line'), (r'MERATUS', 'Meratus'), (r'TANTO', 'Tanto Intim Line'),
]


def norm_name(s):
    s = unicodedata.normalize('NFD', str(s or '')); s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn').replace('Đ', 'D').replace('đ', 'd')
    s = re.sub(r'\(SB\)', ' ', s.upper())
    return re.sub(r'[^A-Z0-9]+', ' ', s).strip()


def op_canon(econdb_operator=None, econdb_owner=None):
    """-> (hãng, nguồn) từ bản ghi EconDB: operator_name (đổi tên) > chủ tàu tự khai thác"""
    op = (econdb_operator or '').strip()
    if op and op.lower() not in ('nan', 'none'): return OP_ALIAS.get(op, op), 'econdb'
    ow = (econdb_owner or '').upper()
    for rx, o in OWNER_OPERATOR:
        if re.search(rx, ow): return o, 'econdb:owner'
    return '', ''


def vessel_index(v):
    """vessels.parquet -> (theo imo, theo mmsi, theo tên chuẩn hoá DUY NHẤT)"""
    if v is None or v.empty: return {}, {}, {}
    v = v.copy(); v['imo'] = pd.to_numeric(v['imo'], errors='coerce'); v['k'] = v['name'].map(norm_name)
    by_imo = {int(r['imo']): r for r in v.dropna(subset=['imo']).drop_duplicates('imo').to_dict('records')}
    by_mmsi = {int(r['mmsi']): r for r in v.dropna(subset=['mmsi']).drop_duplicates('mmsi').to_dict('records')}
    uniq = v[~v['k'].duplicated(keep=False)]
    by_name = {r['k']: r for r in uniq.to_dict('records')}
    return by_imo, by_mmsi, by_name


def match_vessel(idx, imo=None, mmsi=None, name=None, dwt=None):
    """bản ghi EconDB của 1 tàu: IMO > MMSI > tên duy nhất (DWT lệch <= 20% nếu có cả hai)"""
    by_imo, by_mmsi, by_name = idx
    for key, d in ((imo, by_imo), (mmsi, by_mmsi)):
        try:
            k = int(float(key))
            if k in d: return d[k], 'imo' if d is by_imo else 'mmsi'
        except (TypeError, ValueError):
            pass
    r = by_name.get(norm_name(name)) if name else None
    if r is not None:
        try:
            a, b = float(dwt), float(r.get('deadweight'))
            if a > 0 and b > 0 and abs(a / b - 1) > 0.2: return None, None
        except (TypeError, ValueError):
            pass
        return r, 'ten'
    return None, None


def rotations(pc, window_days=WINDOW_DAYS, now=None):
    """lượt ghé toàn cầu -> 1 dòng/tàu (mmsi): vòng tuyến = cảng ghé >= 2 lần trong cửa sổ (ít lượt thì mọi cảng), theo thứ tự ghé"""
    if pc is None or pc.empty: return pd.DataFrame()
    now = pd.Timestamp(now or pd.Timestamp.now())
    p = pc[pc['start'] >= now - pd.Timedelta(days=window_days)].sort_values(['mmsi', 'start'])
    rows = []
    for mm, g in p.groupby('mmsi'):
        seq = g['locode'].tolist()
        seq = [x for i, x in enumerate(seq) if i == 0 or x != seq[i - 1]]               # bỏ ghé lặp liền nhau (dời bến)
        cnt = Counter(seq)
        reg = [x for x in dict.fromkeys(seq) if cnt[x] >= 2] if len(seq) >= 6 else list(dict.fromkeys(seq))
        if not reg: reg = list(dict.fromkeys(seq))
        name_of = dict(zip(g['locode'], g['port_name']))
        last = g.iloc[-1]
        rows.append({'mmsi': mm, 'imo': g['ship_imo'].dropna().iloc[-1] if g['ship_imo'].notna().any() else None, 'ship': last['ship_name'],
                     'ports': tuple(reg), 'route': ' – '.join(name_of.get(x, x) for x in reg),
                     'vn_ports': ', '.join(name_of.get(x, x) for x in reg if str(x).startswith('VN')),
                     'n_calls': len(g), 'last_call': last['start'], 'last_port': last['port_name'],
                     'teu_moves': float(g[['import_count', 'export_count']].fillna(0).sum().sum())})
    return pd.DataFrame(rows)


def cluster(rot, ops=None, jac=JACCARD):
    """gom tàu thành dịch vụ: tập cảng vòng tuyến giống nhau (Jaccard >= jac), tham lam theo cụm lớn trước.
    ops: dict imo -> hãng đã biết. -> (svc: 1 dòng/dịch vụ, rot có cột service_id)"""
    if rot is None or rot.empty: return pd.DataFrame(), rot
    ops = ops or {}
    rot = rot.copy(); rot['pset'] = rot['ports'].map(frozenset)
    groups = rot.groupby('pset').size().sort_values(ascending=False)
    centers, assign = [], {}
    for ps in groups.index:
        best, bj = None, 0.0
        for i, c in enumerate(centers):
            j = len(ps & c) / len(ps | c) if ps | c else 0
            if j > bj: best, bj = i, j
        if best is not None and bj >= jac: assign[ps] = best
        else: assign[ps] = len(centers); centers.append(ps)
    rot['service_id'] = rot['pset'].map(lambda s: f'S{assign[s] + 1:03d}')
    rot['operator_known'] = rot['imo'].map(lambda i: ops.get(int(i)) if pd.notna(i) and int(i) in ops else '')
    svc = []
    for sid, g in rot.groupby('service_id'):
        pos = Counter(); order = {}
        for ports in g['ports']:
            for k, x in enumerate(ports): pos[x] += 1; order.setdefault(x, []).append(k / max(len(ports) - 1, 1))
        core = [x for x, n in pos.items() if n >= max(1, len(g) / 2)] or list(pos)
        core.sort(key=lambda x: sum(order[x]) / len(order[x]))
        name_of = {}
        for r in g.itertuples():
            for x, nm in zip(r.ports, r.route.split(' – ')): name_of.setdefault(x, nm)
        known = Counter(o for o in g['operator_known'] if o)
        top, n_top = (known.most_common(1)[0] if known else ('', 0))
        svc.append({'service_id': sid, 'route': ' – '.join(name_of.get(x, x) for x in core),
                    'vn_ports': ', '.join(name_of.get(x, x) for x in core if str(x).startswith('VN')),
                    'n_vessels': len(g), 'n_known': sum(known.values()), 'operator': top,
                    'operator_share': n_top / sum(known.values()) if known else None,
                    'operators': ', '.join(f'{o} ({n})' for o, n in known.most_common(4)),
                    'vessels': ', '.join(sorted(g['ship'].astype(str))[:12]), 'last_call': g['last_call'].max()})
    return pd.DataFrame(svc).sort_values('n_vessels', ascending=False), rot


def infer_operator(svc, rot, share=INFER_SHARE, min_known=2):
    """imo -> (hãng suy theo dịch vụ, mã dịch vụ) cho tàu chưa rõ hãng"""
    if svc is None or svc.empty: return {}
    ok = svc[(svc['n_known'] >= min_known) & (svc['operator_share'].fillna(0) >= share)].set_index('service_id')
    out = {}
    for r in rot[(rot['operator_known'] == '') & rot['service_id'].isin(ok.index)].itertuples():
        if pd.notna(r.imo): out[int(r.imo)] = (ok.loc[r.service_id, 'operator'], r.service_id)
    return out
