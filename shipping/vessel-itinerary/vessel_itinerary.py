# -*- coding: utf-8 -*-
"""
vessel_itinerary.py - Sinh LỘ TRÌNH DI CHUYỂN của từng tàu từ dữ liệu cảng vụ (không cần AIS).

Nguồn (chỉ đọc):
  - D:/shipping/cangvu-haiphong/data/cvhp_calls_enriched.csv : chuyến tại Hải Phòng, CÓ cảng đi (origin) + cảng đến kế (destination)
  - D:/shipping/cangvu-hcm/data/cvhcm_calls_enriched.csv     : chuyến tại TP.HCM / Cái Mép / Vũng Tàu (giờ vào-rời, bến)
Ghép theo ship_key thành chuỗi ĐIỂM DỪNG theo thời gian:
  ... -> [cảng đi] -> HAI PHONG (bến, giờ vào/rời) -> [cảng đến] -> ... -> HO CHI MINH / CAI MEP (giờ vào/rời) -> ...
  Điểm dừng suy ra từ cột origin/destination của HP đánh dấu inferred=1 (không có giờ); nếu trùng cảng với chuyến thật
  ở HCM liền kề thì gộp vào chuyến thật. Hai điểm dừng thật cùng cảng cách nhau <= 2 ngày cũng gộp.
Toạ độ: ports_geo.csv (regex -> cảng, lon, lat, precision = port | country | inland). Tên nước ngoài ở HP đa số chỉ ở
  mức QUỐC GIA (CHINA, KOREA...) -> đặt ở cảng đại diện, precision=country (đọc bản đồ phải hiểu là gần đúng).
Khoảng cách chặng: thư viện searoute (tuyến biển chuẩn, hải lý), cache data/port_pairs_nm.csv.
Vẽ bản đồ: dùng engine D:/shipping/vessel-route-app/route.py (PNG 300 DPI + timeline).

Chạy:
  python vessel_itinerary.py --ship "WAN HAI 105" --from 2026-07-01            # 1 tàu: CSV + PNG trong out/
  python vessel_itinerary.py --ship "HAIAN BELL,PACIFIC GRACE" --last 12      # nhiều tàu, 12 điểm dừng gần nhất
  python vessel_itinerary.py --all --since 2025-01-01                          # toàn bộ tàu container -> data/*.csv
  python vessel_itinerary.py --all --since 2025-01-01 --classes container,general,bulk
Output --all (data/):
  itinerary_stops.csv       : 1 dòng = 1 điểm dừng (ship, seq, port, terminal, arrive, depart, inferred, source...)
  itinerary_legs.csv        : 1 dòng = 1 chặng (from -> to, ngày rời/đến, số ngày, hải lý, operator, teu)
  vessel_route_pattern.csv  : 1 dòng/tàu: vòng tuyến hay chạy nhất (proxy tuyến dịch vụ), số chặng, các cảng ghé
  lane_monthly.csv          : tháng x chặng (from -> to) x hãng: số chuyến, tổng TEU danh nghĩa
"""
import argparse, csv, os, re, sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
HUB = os.path.dirname(ROOT)
DATA = os.path.join(ROOT, 'data'); OUT = os.path.join(ROOT, 'out')
HP_CALLS = os.path.join(HUB, 'cangvu-haiphong', 'data', 'cvhp_calls_enriched.csv')
HCM_CALLS = os.path.join(HUB, 'cangvu-hcm', 'data', 'cvhcm_calls_enriched.csv')
HP_CALLS_RAW = os.path.join(HUB, 'cangvu-haiphong', 'data', 'cvhp_calls.csv')
HCM_CALLS_RAW = os.path.join(HUB, 'cangvu-hcm', 'data', 'cvhcm_calls.csv')
GEO_CSV = os.path.join(ROOT, 'ports_geo.csv')
PAIRS_CSV = os.path.join(DATA, 'port_pairs_nm.csv')
ROUTE_APP = os.path.join(HUB, 'vessel-route-app')

# bến HCM -> nút cảng
HCM_NODE = {
    'CAI MEP': {'TCIT', 'TCTT', 'CMIT', 'SSIT', 'GEMALINK', 'THI VAI TONG HOP', 'SITV', 'SP-PSA', 'PHU MY', 'MY XUAN',
                'BARIA SERECE', 'PV GAS / HOA DAU'},
    'HO CHI MINH': {'CAT LAI', 'SP-ITC', 'VICT', 'SPCT', 'TAN CANG HIEP PHUOC', 'PHU HUU', 'BEN NGHE', 'SAI GON',
                    'SAI GON HIEP PHUOC', 'BONG SEN', 'PHAO GEMADEPT', 'PHAO NHA BE', 'SOAI RAP', 'XANG DAU', 'XI MANG',
                    'LONG AN', 'HA LOC', 'VAN AN', 'SOWATCO / THI VAI', 'DONG TAU', 'PHAO'},
    'LONG SON (VUNG TAU)': {'LONG SON'},
    'VUNG TAU': {'PTSC VUNG TAU', 'VIETSOVPETRO', 'NEO VUNG TAU'},
    'MO DAU KHI (ngoai khoi)': {'MO DAU KHI'},
    'CON DAO': {'CON DAO'},
    'CAN GIO': {'CAN GIO', 'NAO VET / BAI DO'},
}
NODE_OF = {t: n for n, ts in HCM_NODE.items() for t in ts}
HCM_TERMINALS = os.path.join(HUB, 'cangvu-hcm', 'terminals_hcm.csv')     # bảng bến chính thức (cột node = cụm địa lý) do cvhcm_scrape tạo
if os.path.exists(HCM_TERMINALS):
    with open(HCM_TERMINALS, encoding='utf-8-sig', newline='') as _f:
        for _r in csv.DictReader(_f):
            if _r.get('node'): NODE_OF[_r['terminal']] = _r['node']
NODE_GEO = {'HAI PHONG': (106.80, 20.80), 'HO CHI MINH': (106.78, 10.70), 'CAI MEP': (107.03, 10.53),
            'VUNG TAU': (107.08, 10.33), 'LONG SON (VUNG TAU)': (107.08, 10.43), 'MO DAU KHI (ngoai khoi)': (107.9, 9.8),
            'CON DAO': (106.60, 8.68), 'CAN GIO': (106.95, 10.40)}
MERGE_GAP = timedelta(days=2)
OTHER = {}
UNKNOWN = '(ngoai vung du lieu)'          # điểm giả: tàu rời cảng rồi quay lại đúng cảng đó, không rõ đã ghé đâu


def log(*a): print(datetime.now().strftime('%H:%M:%S'), *a, flush=True)


def read_csv(p):
    if not os.path.exists(p): return []
    with open(p, encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))


def write_csv(p, rows, fields):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p + '.tmp', 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    os.replace(p + '.tmp', p)


def pdt(s):
    try: return datetime.strptime(s, '%Y-%m-%d %H:%M') if s else None
    except ValueError: return None


def skey(name):
    import unicodedata
    name = ''.join(c for c in unicodedata.normalize('NFD', (name or '').replace('Đ', 'D').replace('đ', 'd')) if unicodedata.category(c) != 'Mn')
    k = re.sub(r'\((VR-)?SB\)|\(SI+\)', '', name.upper())
    return re.sub(r'[^A-Z0-9]+', ' ', k).strip()


# ---------------------------------------------------------------- gazetteer
class Geo:
    def __init__(self):
        self.rules = [(re.compile(r['pattern'], re.I), r) for r in read_csv(GEO_CSV)]
        self.cache = {}; self.unmapped = Counter()

    def resolve(self, raw):
        """tên thô -> (port, lon, lat, precision); không map được -> (raw, None, None, 'unmapped')"""
        raw = (raw or '').strip().upper()
        if raw in self.cache: return self.cache[raw]
        res = None
        for rx, r in self.rules:
            if rx.search(raw):
                res = (r['port'], float(r['lon']), float(r['lat']), r['precision']); break
        if res is None:
            res = (raw, None, None, 'unmapped'); self.unmapped[raw] += 1
        self.cache[raw] = res
        return res


# ---------------------------------------------------------------- build stops
MASTER_CSV = os.path.join(HUB, 'cangvu-haiphong', 'data', 'vessel_master.csv')
REGION = {'HO CHI MINH': 'HCM', 'CAI MEP': 'HCM', 'VUNG TAU': 'HCM', 'LONG SON (VUNG TAU)': 'HCM'}   # cùng vùng cảng


def load_calls():
    """Đọc file chuyến GỐC của 2 cảng vụ rồi tự ghép lớp tàu/hãng/TEU từ vessel_master (không phụ thuộc bước --apply)."""
    hp = read_csv(HP_CALLS_RAW); hcm = read_csv(HCM_CALLS_RAW)
    OTHER.clear()
    for c in read_csv(os.path.join(HUB, 'cangvu-toanquoc', 'data', 'national_calls.csv')):
        if c['auth'] not in ('HP', 'HCM'):
            c = dict(c); c['ship'] = c['auth']; OTHER.setdefault(c['ship_key'], []).append(c)
    master = {r['ship_key']: r for r in read_csv(MASTER_CSV)}
    for c in hp + hcm:
        m = master.get(c['ship_key'], {})
        c['vessel_class'] = m.get('vessel_class', ''); c['operator'] = m.get('operator', ''); c['teu'] = m.get('teu', '')
    log(f'calls: HP {len(hp)}, HCM {len(hcm)}, master {len(master)} tau')
    return hp, hcm


# cảng vụ khác (bộ toàn quốc) -> nút cảng; tên trùng với ports_geo để điểm suy ra từ HP gộp được với chuyến thật
AUTH_NODE = {'QN': ('QUANG NINH (CAI LAN)', 107.05, 20.95), 'TBH': ('DIEM DIEN (THAI BINH)', 106.57, 20.55), 'THA': ('NGHI SON', 105.83, 19.32),
             'HTH': ('VUNG ANG / SON DUONG', 106.43, 18.10), 'DNG': ('DA NANG', 108.22, 16.12), 'NTG': ('NHA TRANG', 109.20, 12.25),
             'BTN': ('VINH TAN', 108.80, 11.30), 'DNI': ('DONG NAI', 106.95, 10.65), 'CTO': ('CAN THO', 105.80, 10.03),
             'KGG': ('KIEN GIANG', 104.00, 10.20)}
SUB_NODE = [(r'CẨM PHẢ|CAM PHA|HN2|HÒN NÉT|HON NET', ('CAM PHA', 107.37, 21.02)), (r'KỲ HÀ|KY HA|CHU LAI|TAM HIỆP', ('CHU LAI', 108.68, 15.48)),
            (r'C\.RANH|CAM RANH|BA NGÒI|BA NGOI', ('CAM RANH', 109.20, 11.90)), (r'VÂN PHONG|VAN PHONG|H\.KHÓI|HÒN KHÓI', ('VAN PHONG', 109.40, 12.60))]


def other_stops(calls, geo):
    out = []
    for c in calls:
        auth = c['ship']                                   # bản ghi tạm: cột ship mang mã cảng vụ
        if auth not in AUTH_NODE: continue
        arr, dep = pdt(c['arrival']), pdt(c['departure']); t0 = arr or dep
        if t0 is None: continue
        node = AUTH_NODE[auth]
        for rx, nd in SUB_NODE:
            if re.search(rx, c['berths'], re.I): node = nd; break
        for side, raw, t in (('origin', c.get('origin', ''), arr), ('dest', c.get('destination', ''), dep)):
            if raw and t and not re.fullmatch(r'[A-Z]{5}', raw.strip()):          # mã UN/LOCODE chưa giải nghĩa thì bỏ qua
                p, lon, lat, prec = geo.resolve(raw)
                if p not in ('OPEN SEA', 'TO ORDER') and prec != 'unmapped':
                    out.append({'t': t + timedelta(minutes=-1 if side == 'origin' else 1), 'port': p, 'lon': lon, 'lat': lat, 'precision': prec,
                                'terminal': '', 'arrive': None, 'depart': None, 'inferred': 1, 'source': f'{auth}-{side}', 'raw_name': raw})
        out.append({'t': t0, 'port': node[0], 'lon': node[1], 'lat': node[2], 'precision': 'port', 'terminal': c['berths'], 'arrive': arr,
                    'depart': dep, 'inferred': 0, 'source': 'CV-' + auth, 'raw_name': c.get('first_berth', ''), 'status': c.get('status', '')})
    return out


def stops_for_ship(hp_calls, hcm_calls, geo, other_calls=None):
    """Trả về list điểm dừng đã sắp theo thời gian và gộp trùng."""
    raw = []
    for c in hp_calls:
        arr, dep = pdt(c['arrival']), pdt(c['departure'])
        t0 = arr or dep
        if t0 is None: continue
        if c.get('origin') and arr:
            p, lon, lat, prec = geo.resolve(c['origin'])
            if p not in ('OPEN SEA', 'TO ORDER'):
                raw.append({'t': arr - timedelta(minutes=1), 'port': p, 'lon': lon, 'lat': lat, 'precision': prec,
                            'terminal': '', 'arrive': None, 'depart': None, 'inferred': 1, 'source': 'CVHP-origin',
                            'raw_name': c['origin']})
        raw.append({'t': t0, 'port': 'HAI PHONG', 'lon': NODE_GEO['HAI PHONG'][0], 'lat': NODE_GEO['HAI PHONG'][1],
                    'precision': 'port', 'terminal': c['berths'], 'arrive': arr, 'depart': dep, 'inferred': 0,
                    'source': 'CVHP', 'raw_name': c['first_berth'], 'status': c['status']})
        if c.get('destination') and dep:
            p, lon, lat, prec = geo.resolve(c['destination'])
            if p not in ('OPEN SEA', 'TO ORDER'):
                raw.append({'t': dep + timedelta(minutes=1), 'port': p, 'lon': lon, 'lat': lat, 'precision': prec,
                            'terminal': '', 'arrive': None, 'depart': None, 'inferred': 1, 'source': 'CVHP-dest',
                            'raw_name': c['destination']})
    for c in hcm_calls:
        arr, dep = pdt(c['arrival']), pdt(c['departure'])
        t0 = arr or dep
        if t0 is None: continue
        berths = [b for b in c['berths'].split('|') if b]
        nodes = []
        for b in berths:
            n = NODE_OF.get(b, 'HO CHI MINH' if b else '')
            if n and (not nodes or nodes[-1][0] != n): nodes.append([n, [b]])
            elif n: nodes[-1][1].append(b)
        real = [x for x in nodes if x[0] != 'VUNG TAU'] or nodes        # neo Vũng Tàu chỉ là chờ, bỏ nếu có bến thật
        for i, (n, bs) in enumerate(real):
            lon, lat = NODE_GEO.get(n, (None, None))
            raw.append({'t': t0 + timedelta(minutes=i), 'port': n, 'lon': lon, 'lat': lat, 'precision': 'port',
                        'terminal': '|'.join(bs), 'arrive': arr if i == 0 else None,
                        'depart': dep if i == len(real) - 1 else None, 'inferred': 0, 'source': 'CVHCM',
                        'raw_name': bs[0], 'status': c['status']})
    if other_calls: raw.extend(other_stops(other_calls, geo))
    raw.sort(key=lambda s: s['t'])
    # điểm SUY RA (origin/destination của HP) nằm cùng vùng cảng với một chuyến THẬT liền kề (HCM/Cái Mép/Vũng Tàu)
    # -> bỏ điểm suy ra, giữ chuyến thật (vd HP ghi "đi HO CHI MINH" nhưng tàu thật ghé Cái Mép rồi mới vào Cát Lái)
    keep = []
    for i, s in enumerate(raw):
        if s['inferred'] and s['port'] in REGION:
            j = i + 1 if s['source'] == 'CVHP-dest' else i - 1
            nb = None
            rng = range(i + 1, min(i + 4, len(raw))) if s['source'] == 'CVHP-dest' else range(i - 1, max(i - 4, -1), -1)
            for j in rng:
                if raw[j]['port'] == 'HAI PHONG': break
                if not raw[j]['inferred'] and REGION.get(raw[j]['port']) == REGION[s['port']]:
                    nb = raw[j]; break
            if nb is not None and abs((nb['t'] - s['t']).days) <= 10:
                if s['source'] not in nb['source']: nb['source'] += '+' + s['source']
                continue
        keep.append(s)
    raw = keep
    out = []
    for s in raw:
        if out and out[-1]['port'] == s['port']:
            p = out[-1]
            gap_ok = True
            if not p['inferred'] and not s['inferred']:
                last = p['depart'] or p['arrive'] or p['t']; first = s['arrive'] or s['depart'] or s['t']
                gap_ok = (first - last) <= MERGE_GAP
            if gap_ok:
                if p['inferred'] and not s['inferred']:                      # thay điểm suy ra bằng chuyến thật
                    s2 = dict(s); s2['source'] = s['source'] + '+' + p['source']; out[-1] = s2
                elif not p['inferred'] and s['inferred']:
                    if s['source'] not in p['source']: p['source'] += '+' + s['source']
                elif not p['inferred'] and not s['inferred']:
                    p['depart'] = s['depart'] or p['depart']
                    if s['terminal'] and s['terminal'] not in p['terminal']: p['terminal'] += '|' + s['terminal']
                continue
            # 2 chuyến THẬT cùng cảng cách nhau > 2 ngày: tàu đã đi đâu đó ngoài vùng dữ liệu rồi quay lại
            out.append({'t': (p['depart'] or p['arrive'] or p['t']) + timedelta(minutes=1), 'port': UNKNOWN, 'lon': None,
                        'lat': None, 'precision': 'unknown', 'terminal': '', 'arrive': None, 'depart': None, 'inferred': 1,
                        'source': 'gap', 'raw_name': ''})
        out.append(dict(s))
    return out


# ---------------------------------------------------------------- distances
class Dist:
    def __init__(self):
        self.cache = {(r['from'], r['to']): (float(r['nm']) if r['nm'] else None) for r in read_csv(PAIRS_CSV)}
        self.dirty = False; self.sr = None

    def nm(self, a, b):
        if a['lon'] is None or b['lon'] is None: return None
        k = (a['port'], b['port'])
        if k in self.cache: return self.cache[k]
        if self.sr is None:
            import searoute as sr; self.sr = sr
        try:
            f = self.sr.searoute((a['lon'], a['lat']), (b['lon'], b['lat']), units='naut')
            v = round(float(f['properties'].get('length', 0.0)), 0)
        except Exception:
            v = None
        self.cache[k] = v; self.cache[(b['port'], a['port'])] = v; self.dirty = True
        return v

    def save(self):
        if self.dirty:
            write_csv(PAIRS_CSV, [{'from': k[0], 'to': k[1], 'nm': '' if v is None else v} for k, v in sorted(self.cache.items())],
                      ['from', 'to', 'nm'])


def legs_from_stops(stops, dist):
    legs = []
    for a, b in zip(stops[:-1], stops[1:]):
        dep = a['depart'] or (a['arrive'] if not a['inferred'] else None)
        arr = b['arrive'] or (b['depart'] if not b['inferred'] else None)
        days = round((arr - dep).total_seconds() / 86400, 1) if (dep and arr and arr >= dep) else ''
        legs.append({'from': a['port'], 'to': b['port'], 'depart': dep, 'arrive': arr, 'days': days,
                     'nm': dist.nm(a, b), 'inferred': 1 if (a['inferred'] or b['inferred']) else 0,
                     't': a['t']})
    return legs


def route_pattern(stops, max_len=7):
    """Vòng tuyến hay chạy nhất: đi theo chuyển tiếp phổ biến nhất bắt đầu từ cảng ghé nhiều nhất."""
    trans = defaultdict(Counter); cnt = Counter()
    for a, b in zip(stops[:-1], stops[1:]):
        trans[a['port']][b['port']] += 1
    for s in stops: cnt[s['port']] += 1
    if not cnt: return '', ''
    home = 'HAI PHONG' if cnt.get('HAI PHONG') else cnt.most_common(1)[0][0]
    path = [home]; cur = home
    for _ in range(max_len):
        nxts = [(p, n) for p, n in trans[cur].most_common() if p not in path[1:]]
        if not nxts: break
        nxt = nxts[0][0]; path.append(nxt); cur = nxt
        if nxt == home: break
    return ' > '.join(path), '; '.join(f'{p}({n})' for p, n in cnt.most_common(8))


def fmt(t): return t.strftime('%Y-%m-%d %H:%M') if t else ''


# ---------------------------------------------------------------- render 1 tàu
def render_png(ship, stops, out_png, title=None):
    sys.path.insert(0, ROUTE_APP)
    from route import Waypoint, render
    wps = []
    for s in stops:
        if s['lon'] is None: continue
        t = s['arrive'] or s['depart'] or s['t']
        label = t.strftime('%d/%m/%y') + ('~' if s['inferred'] else '')
        port = s['port'] if s['precision'] != 'country' else s['port'] + '*'
        wps.append(Waypoint(month=label, region=s['raw_name'], source=s['source'].split('+')[0].replace('CVHP-', 'HP '),
                            port=port, lon=s['lon'], lat=s['lat']))
    # bỏ điểm liên tiếp trùng cảng (sau khi lọc điểm không toạ độ)
    w2 = []
    for w in wps:
        if w2 and w2[-1].port == w.port: continue
        w2.append(w)
    if len(w2) < 2:
        log(f'  {ship}: khong du diem co toa do de ve'); return None
    meta = render(w2, out_png, title=title or f'Lộ trình tàu {ship}  ({w2[0].month} → {w2[-1].month})   * = vị trí mức quốc gia, ~ = suy từ cảng đi/đến')
    return meta


STOP_FIELDS = ['ship_key', 'ship', 'vessel_class', 'operator', 'teu', 'seq', 'port', 'precision', 'terminal', 'arrive', 'depart',
               'hours_in_port', 'inferred', 'source', 'raw_name', 'lon', 'lat']
LEG_FIELDS = ['ship_key', 'ship', 'vessel_class', 'operator', 'teu', 'seq', 'from', 'to', 'depart', 'arrive', 'days', 'nm',
              'inferred', 'month']


def stop_rows(meta, stops):
    rows = []
    for i, s in enumerate(stops, 1):
        hrs = round((s['depart'] - s['arrive']).total_seconds() / 3600, 1) if (s['arrive'] and s['depart']) else ''
        rows.append({**meta, 'seq': i, 'port': s['port'], 'precision': s['precision'], 'terminal': s['terminal'],
                     'arrive': fmt(s['arrive']), 'depart': fmt(s['depart']), 'hours_in_port': hrs, 'inferred': s['inferred'],
                     'source': s['source'], 'raw_name': s['raw_name'], 'lon': s['lon'] if s['lon'] is not None else '',
                     'lat': s['lat'] if s['lat'] is not None else ''})
    return rows


def leg_rows(meta, legs):
    rows = []
    for i, l in enumerate(legs, 1):
        rows.append({**meta, 'seq': i, 'from': l['from'], 'to': l['to'], 'depart': fmt(l['depart']), 'arrive': fmt(l['arrive']),
                     'days': l['days'], 'nm': '' if l['nm'] is None else int(l['nm']), 'inferred': l['inferred'],
                     'month': l['t'].strftime('%Y-%m')})
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ship', help='tên tàu (nhiều tàu cách nhau dấu phẩy)')
    ap.add_argument('--all', action='store_true', help='mọi tàu thuộc --classes')
    ap.add_argument('--classes', default='container,container?', help='lớp tàu cho --all')
    ap.add_argument('--from', dest='dfrom', help='YYYY-MM-DD'); ap.add_argument('--to', dest='dto')
    ap.add_argument('--since', help='như --from (cho --all)')
    ap.add_argument('--last', type=int, default=0, help='chỉ lấy N điểm dừng gần nhất (cho --ship)')
    ap.add_argument('--min-stops', type=int, default=3, help='--all: bỏ tàu có ít hơn N điểm dừng')
    ap.add_argument('--no-png', action='store_true')
    a = ap.parse_args()
    if not (a.ship or a.all): ap.error('can --ship hoac --all')
    dfrom = a.dfrom or a.since or '2019-01-01'; dto = a.dto or '2100-01-01'

    hp, hcm = load_calls()
    geo = Geo(); dist = Dist()
    by_hp = defaultdict(list); by_hcm = defaultdict(list); meta = {}
    def in_range(c):
        d = c['arr_date'] or c['dep_date']
        return bool(d) and dfrom <= d <= dto
    for c in hp:
        if in_range(c): by_hp[c['ship_key']].append(c)
        meta[c['ship_key']] = c
    for c in hcm:
        if in_range(c): by_hcm[c['ship_key']].append(c)
        meta.setdefault(c['ship_key'], c)

    if a.ship:
        keys = [skey(x) for x in a.ship.split(',') if x.strip()]
    else:
        cls = set(a.classes.split(','))
        keys = [k for k in set(by_hp) | set(by_hcm) if meta[k].get('vessel_class', '') in cls]
    log(f'so tau xu ly: {len(keys)} (tu {dfrom} den {dto})')

    all_stops, all_legs, patterns = [], [], []
    for n, k in enumerate(sorted(keys), 1):
        if k not in by_hp and k not in by_hcm:
            log(f'  khong co chuyen nao cho "{k}" trong khoang ngay'); continue
        m = meta[k]
        mrow = {'ship_key': k, 'ship': m['ship'], 'vessel_class': m.get('vessel_class', ''), 'operator': m.get('operator', ''),
                'teu': m.get('teu', '')}
        oth = [c for c in OTHER.get(k, []) if dfrom <= (c['arr_date'] or c['dep_date'] or '') <= dto]
        stops = stops_for_ship(by_hp.get(k, []), by_hcm.get(k, []), geo, other_calls=oth)
        if a.ship and a.last: stops = stops[-a.last:]
        if a.all and len(stops) < a.min_stops: continue
        legs = legs_from_stops(stops, dist)
        srows, lrows = stop_rows(mrow, stops), leg_rows(mrow, legs)
        pat, ports = route_pattern(stops)
        tot_nm = sum(l['nm'] or 0 for l in legs)
        patterns.append({**mrow, 'route_pattern': pat, 'ports_called': ports, 'n_stops': len(stops), 'n_legs': len(legs),
                         'n_hp_calls': sum(1 for s in stops if s['port'] == 'HAI PHONG'),
                         'n_hcm_calls': sum(1 for s in stops if s['port'] in ('HO CHI MINH', 'CAI MEP')),
                         'total_nm': int(tot_nm), 'first': fmt(stops[0]['t']) if stops else '', 'last': fmt(stops[-1]['t']) if stops else ''})
        if a.ship:
            safe = re.sub(r'[^A-Z0-9]+', '_', k)
            write_csv(os.path.join(OUT, f'{safe}_stops.csv'), srows, STOP_FIELDS)
            write_csv(os.path.join(OUT, f'{safe}_legs.csv'), lrows, LEG_FIELDS)
            log(f'{m["ship"]}: {len(stops)} diem dung, {len(legs)} chang, {int(tot_nm):,} hai ly | vong tuyen: {pat}')
            for s in srows[-25:]:
                log(f'   {s["seq"]:>3} {s["port"][:26].ljust(26)} {s["arrive"] or "     ~      ":16} -> {s["depart"] or "":16} {s["terminal"][:30]:30} {s["source"]}')
            if not a.no_png:
                png = os.path.join(OUT, f'{safe}_route.png')
                r = render_png(m['ship'], stops, png)
                if r: log(f'   PNG: {png}')
        else:
            all_stops.extend(srows); all_legs.extend(lrows)
            if n % 500 == 0: log(f'  ... {n}/{len(keys)} tau')
    dist.save()

    if a.all:
        write_csv(os.path.join(DATA, 'itinerary_stops.csv'), all_stops, STOP_FIELDS)
        write_csv(os.path.join(DATA, 'itinerary_legs.csv'), all_legs, LEG_FIELDS)
        write_csv(os.path.join(DATA, 'vessel_route_pattern.csv'), sorted(patterns, key=lambda r: -r['n_stops']),
                  ['ship_key', 'ship', 'vessel_class', 'operator', 'teu', 'route_pattern', 'ports_called', 'n_stops', 'n_legs',
                   'n_hp_calls', 'n_hcm_calls', 'total_nm', 'first', 'last'])
        lane = defaultdict(lambda: {'legs': 0, 'teu_sum': 0, 'ships': set()})
        for l in all_legs:
            x = lane[(l['month'], l['from'], l['to'], l['operator'] or '(chua ro)')]
            x['legs'] += 1; x['ships'].add(l['ship_key'])
            try: x['teu_sum'] += int(float(l['teu'])) if l['teu'] else 0
            except ValueError: pass
        write_csv(os.path.join(DATA, 'lane_monthly.csv'),
                  [{'month': k[0], 'from': k[1], 'to': k[2], 'operator': k[3], 'legs': v['legs'], 'ships': len(v['ships']),
                    'teu_sum': v['teu_sum']} for k, v in sorted(lane.items())],
                  ['month', 'from', 'to', 'operator', 'legs', 'ships', 'teu_sum'])
        log(f'DONE all: {len(patterns)} tau, {len(all_stops)} diem dung, {len(all_legs)} chang -> {DATA}')
    if geo.unmapped:
        log(f'ten cang chua co toa do: {len(geo.unmapped)} (top: ' + ', '.join(f'{k}' for k, _ in geo.unmapped.most_common(25)) + ')')
    return 0


if __name__ == '__main__':
    sys.exit(main())
