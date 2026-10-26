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

WINDOW_DAYS = 180          # 26/10/2026: 120 -> 180 ngày, vòng tuyến theo CHU KỲ của từng tàu (rotations)
MAX_CYCLE_DAYS = 150
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
    """lượt ghé toàn cầu -> 1 dòng/tàu (mmsi). 26/10/2026: vòng tuyến = các cảng ghé trong 1 CHU KỲ gần nhất của tàu; chu kỳ = trung vị
    khoảng ngày tàu quay lại cùng một cảng (>= 7 ngày; không quay lại -> 120 ngày; tối đa MAX_CYCLE_DAYS). Cách cũ (cảng ghé >= 2 lần trong
    120 ngày) bỏ sót cảng của tuyến vòng dài (Á-Âu, Á-Mỹ ~ 80–110 ngày) và gom tàu chạy rời vào cụm rác 1 cảng (Singapore: 53 tàu nhiều hãng)."""
    if pc is None or pc.empty: return pd.DataFrame()
    now = pd.Timestamp(now or pd.Timestamp.now())
    p = pc[pc['start'] >= now - pd.Timedelta(days=window_days)].sort_values(['mmsi', 'start'])
    rows = []
    for mm, g in p.groupby('mmsi'):
        g = g[g['locode'].ne(g['locode'].shift())]                                  # bỏ ghé lặp liền nhau (dời bến)
        seen, gaps = {}, []
        for x, ti in zip(g['locode'], g['start']):
            if x in seen and (ti - seen[x]).days >= 7: gaps.append((ti - seen[x]).days)
            seen[x] = ti
        cyc = float(pd.Series(gaps).median()) if gaps else None
        span = min(cyc * 1.05 if cyc else 120, MAX_CYCLE_DAYS)
        h = g[g['start'] >= g['start'].max() - pd.Timedelta(days=span)]
        reg = list(dict.fromkeys(h['locode']))
        name_of = dict(zip(g['locode'], g['port_name']))
        last = g.iloc[-1]
        rows.append({'mmsi': mm, 'imo': g['ship_imo'].dropna().iloc[-1] if g['ship_imo'].notna().any() else None, 'ship': last['ship_name'],
                     'ports': tuple(reg), 'route': ' – '.join(name_of.get(x, x) for x in reg),
                     'vn_ports': ', '.join(name_of.get(x, x) for x in reg if str(x).startswith('VN')),
                     'n_calls': len(g), 'last_call': last['start'], 'last_port': last['port_name'], 'cycle_days': cyc,
                     'teu_moves': float(g[['import_count', 'export_count']].fillna(0).sum().sum())})
    return pd.DataFrame(rows)


def cluster(rot, ops=None, jac=JACCARD, names=None):
    """gom tàu thành dịch vụ: tập cảng vòng tuyến giống nhau (Jaccard >= jac), tham lam theo cụm lớn trước.
    ops: dict imo -> hãng đã biết. names: dict mmsi -> TÊN tuyến dịch vụ EconDB (trang tàu, 26/10/2026): tàu có tên -> dịch vụ = tên đó;
    tàu chưa có tên -> theo cụm vòng cảng, cụm mà >= 1/2 tàu có tên cùng mang tên X thì gán X; còn lại giữ mã cụm Sxxx.
    -> (svc: 1 dòng/dịch vụ, rot có cột service_id, service_name)"""
    if rot is None or rot.empty: return pd.DataFrame(), rot
    ops = ops or {}
    rot = rot.copy()
    rot['operator_known'] = rot['imo'].map(lambda i: ops.get(int(i)) if pd.notna(i) and int(i) in ops else '')
    # vòng toàn cảng VN (nội địa): mỗi hãng chạy tuyến riêng, không chia tàu -> thêm hãng vào tập so khớp (tách cụm 'Hồ Chí Minh – Hải Phòng')
    rot['pset'] = [frozenset(p) | ({'OP:' + o} if o and all(str(x).startswith('VN') for x in p) else set())
                   for p, o in zip(rot['ports'], rot['operator_known'])]
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
    names = names or {}
    rot['service_name'] = rot['mmsi'].map(lambda m: names.get(int(m)) if pd.notna(m) else None)
    named = rot.dropna(subset=['service_name'])
    cl_name = {}
    for sid_, g in named.groupby('service_id'):
        top_, n_ = Counter(g['service_name']).most_common(1)[0]
        if n_ >= max(1, (rot['service_id'] == sid_).sum() / 2): cl_name[sid_] = top_
    rot['service_name'] = rot['service_name'].fillna(rot['service_id'].map(cl_name))
    rot['service_id'] = rot['service_name'].fillna(rot['service_id'])
    svc = []
    for sid, g in rot.groupby('service_id'):
        pos = Counter(); order = {}
        for ports in g['ports']:
            for k, x in enumerate(ports): pos[x] += 1; order.setdefault(x, []).append(k / max(len(ports) - 1, 1))
        core = [x for x, n in pos.items() if n >= max(1, len(g) / 2)] or list(pos)
        # thứ tự cảng theo hành trình THỰC của 1 tàu đại diện (tàu có vòng giống tập lõi nhất, nhiều lượt nhất); TB vị trí nhiều tàu bị xáo
        # vì mỗi tàu bắt đầu ở một điểm khác nhau của vòng. Cảng lõi tàu đại diện không ghé -> xếp theo TB vị trí, nối cuối.
        cs = set(core)
        rep_ = max(g.itertuples(), key=lambda r: (len(cs & set(r.ports)) / len(cs | set(r.ports)), r.n_calls))
        seq = [x for x in rep_.ports if x in cs]
        core = seq + sorted([x for x in core if x not in seq], key=lambda x: sum(order[x]) / len(order[x]))
        name_of = {}
        for r in g.itertuples():
            for x, nm in zip(r.ports, r.route.split(' – ')): name_of.setdefault(x, nm)
        known = Counter(o for o in g['operator_known'] if o)
        top, n_top = (known.most_common(1)[0] if known else ('', 0))
        svc.append({'service_id': sid, 'service_name': g['service_name'].dropna().iloc[0] if g['service_name'].notna().any() else '', 'route': ' – '.join(name_of.get(x, x) for x in core),
                    'vn_ports': ', '.join(name_of.get(x, x) for x in core if str(x).startswith('VN')),
                    'n_vessels': len(g), 'n_known': sum(known.values()), 'operator': top,
                    'operator_share': n_top / sum(known.values()) if known else None,
                    'operators': ', '.join(f'{o} ({n})' for o, n in known.most_common(4)),
                    'vessels': ', '.join(sorted(g['ship'].astype(str))[:12]), 'last_call': g['last_call'].max()})
    return pd.DataFrame(svc).sort_values('n_vessels', ascending=False), rot


def service_names(vs):
    """vessel_services.parquet (econdb.pull_vessel_services) -> dict mmsi -> tên tuyến dịch vụ"""
    if vs is None or len(vs) == 0 or 'service' not in vs: return {}
    v = vs.dropna(subset=['service'])
    return {int(m): str(n).strip() for m, n in zip(v['mmsi'], v['service']) if pd.notna(m) and str(n).strip()}


def names_for_rotations(rot, cs, ops=None):
    """lịch tàu công khai của hãng (carrier_services.csv: carrier, service_code, service_name, vessel, imo) -> dict mmsi -> nhãn tuyến
    'CODE (Hãng)'. Ghép theo IMO rồi tên tàu chuẩn hoá. Tàu có ở nhiều nguồn (thuê slot / chia tàu) -> ưu tiên nguồn của chính hãng khai
    thác tàu (ops: imo -> hãng), rồi nguồn khác Hải An, cuối cùng Hải An."""
    if cs is None or len(cs) == 0 or rot is None or rot.empty: return {}
    ops = ops or {}
    cs = cs.assign(k_imo=pd.to_numeric(cs.get('imo'), errors='coerce'), k_nm=cs['vessel'].map(norm_name))
    out = {}
    for r in rot.itertuples():
        imo = pd.to_numeric(pd.Series([r.imo]), errors='coerce').iloc[0]
        c = cs[(cs['k_imo'] == imo)] if pd.notna(imo) and imo > 0 else cs.iloc[0:0]
        if c.empty: c = cs[cs['k_nm'] == norm_name(r.ship)]
        if c.empty: continue
        op = (ops.get(int(imo)) if pd.notna(imo) and imo > 0 else '') or ''
        def rank(row):
            car = str(row['carrier']).lower()
            return (0 if op and (op.lower() in car or car.split(' (')[0] in op.lower()) else 1, 1 if 'hai an' in car else 0)
        best = min((row for _, row in c.iterrows()), key=rank)
        code = str(best['service_code']).strip()
        if code and code.lower() != 'nan': out[int(r.mmsi)] = f"{code} ({str(best['carrier']).split(' (')[0]})"
    return out


def infer_operator(svc, rot, share=INFER_SHARE, min_known=2):
    """imo -> (hãng suy theo dịch vụ, mã dịch vụ) cho tàu chưa rõ hãng"""
    if svc is None or svc.empty: return {}
    ok = svc[(svc['n_known'] >= min_known) & (svc['operator_share'].fillna(0) >= share)].set_index('service_id')
    out = {}
    for r in rot[(rot['operator_known'] == '') & rot['service_id'].isin(ok.index)].itertuples():
        if pd.notna(r.imo): out[int(r.imo)] = (ok.loc[r.service_id, 'operator'], r.service_id)
    return out
