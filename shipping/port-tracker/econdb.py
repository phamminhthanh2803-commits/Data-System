# -*- coding: utf-8 -*-
r"""
econdb.py - BƯỚC PIPELINE "econdb" + bộ đọc cho app Port & Vessel Tracker (14/10/2026).

Nguồn: EconDB API v1 (https://api.econdb.com/v1/, docs https://developers.econdb.com/docs/), PV2 subscribe 10/2026.
Key: biến môi trường ECONDB_TOKEN (laptop: setx User; cloud: GitHub secret ECONDB_TOKEN). Không có key -> bỏ qua, exit 0.

Kéo về kho chia sẻ store/econdb/ (cùng thư mục store/ của app -> đồng bộ Drive như phần cảng vụ):
    series.parquet   : chuỗi thời gian dạng long (scope, metric, series, date, value) - mỗi lần kéo thay nguyên khối (scope, metric)
        traffic        container full (TEU) Imports/Exports/Transshipment theo TUẦN (6 cảng VN + cảng khu vực so sánh)
        dwell          ngày container nằm bãi theo tháng
        cap_throughput sức chở tàu ghé (TEU) theo hãng, tháng | cap_import/cap_export/cap_transshipment: sản lượng theo hãng
        partner_export / partner_import  TEU theo khu vực đối tác, tháng
        p2p_export / p2p_import          scope 'VN': TEU VN <-> từng nước đối tác theo tuần
        global_trade / lane_capacity     scope 'WORLD'
        term_throughput / term_full      throughput / container full (TEU, tháng) TỪNG terminal (series = mã terminal) - trang web, xem TERMINAL_MAP
    terminals.parquet: mã, terminal_id, tên, nhà khai thác, chiều dài bến
    calls.parquet    : lượt tàu container ghé (API chỉ giữ ~4 tháng -> TÍCH LUỸ, khoá locode+ship_imo+start)
    schedule.parquet : lịch tàu ~3 tuần tới (ảnh chụp lần kéo gần nhất)
    ports.parquet    : danh mục top 400 cảng
    vessels.parquet  : (16/10/2026) ~7.600 tàu container EconDB: imo, mmsi, tên, chủ tàu (owner), HÃNG KHAI THÁC (operator_name), AIS mới nhất
    vessel_portcalls.parquet : lượt ghé TOÀN CẦU của các tàu từng ghé VN (/vessels/{mmsi}/portcalls/, cộng dồn, khoá ship_imo+locode+start)
                       -> vòng tuyến từng tàu + gom dịch vụ (services.py)

    python econdb.py                 # kéo tất cả
    python econdb.py --only traffic,calls
    python econdb.py --only vessels,portcalls --portcalls-max 300
Locode của EconDB CÓ DẤU CÁCH ('VN HPH').
"""
import argparse
import os
import sys
import time

import pandas as pd
import requests

APP = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('PORT_TRACKER_STORE') or os.path.join(APP, 'store')
DIR = os.path.join(STORE, 'econdb')
API = 'https://api.econdb.com/v1'

VN_PORTS = {'VN HPH': 'Hải Phòng', 'VN SGN': 'TP.HCM', 'VN VUT': 'Vũng Tàu – Cái Mép', 'VN DAD': 'Đà Nẵng',
            'VN DNA': 'Đồng Nai', 'VN UIH': 'Quy Nhơn'}
# cảng vụ của app -> locode EconDB (Quảng Ninh, Thái Bình... không có trong top 400 của EconDB)
AUTH_LOCODES = {'HP': ['VN HPH'], 'HCM': ['VN SGN', 'VN VUT'], 'DNG': ['VN DAD'], 'DNI': ['VN DNA']}
PEERS = {'SG SIN': 'Singapore', 'MY TPP': 'Tanjung Pelepas', 'MY PKG': 'Port Klang', 'TH LCH': 'Laem Chabang',
         'ID JKT': 'Jakarta', 'PH MNL': 'Manila', 'KH KOS': 'Sihanoukville', 'CN SHA': 'Thượng Hải', 'CN NGB': 'Ninh Ba',
         'CN NSA': 'Nam Sa (Quảng Châu)', 'HK HKG': 'Hồng Kông', 'KR PUS': 'Busan', 'TW KHH': 'Cao Hùng'}
PARTNERS = {'US': 'Mỹ', 'CN': 'Trung Quốc', 'JP': 'Nhật Bản', 'KR': 'Hàn Quốc', 'TW': 'Đài Loan', 'HK': 'Hồng Kông',
            'SG': 'Singapore', 'MY': 'Malaysia', 'TH': 'Thái Lan', 'ID': 'Indonesia', 'IN': 'Ấn Độ', 'DE': 'Đức',
            'NL': 'Hà Lan', 'BE': 'Bỉ', 'GB': 'Anh', 'AU': 'Úc', 'CA': 'Canada', 'MX': 'Mexico'}
# THEO TERMINAL: API v1 không có, lấy từ trang terminal công khai của econdb.com (không cần đăng nhập):
#   /maritime/ports/async/<locode>/              -> danh sách mã terminal (code)
#   /maritime/get_terminal_detail/<locode>/<code>/ -> terminal_id, tên, nhà khai thác, chiều dài bến
#   /widgets/port-time-series/data/?unit=throughput&by=teu_class&freq=month&terminal_id=  -> throughput (cộng các cỡ tàu) = term_throughput
#   /widgets/sea-trade-by-week/data/?freq=month&terminal_id=                               -> container full nhập/xuất/TS = term_full
#   /widgets/port-time-series/data/?unit=throughput&by=service&freq=month&terminal_id=    -> throughput theo TÊN TUYẾN DỊCH VỤ của hãng
#       (top 8 tuyến + Others mỗi bến, từ 02/2022) = term_services.parquet (26/10/2026)
# Mã terminal EconDB -> bến cảng vụ trong app (mã không có ở đây vẫn được kéo, chỉ không ghép được với bến):
TERMINAL_MAP = {
    'VN HPH': {'VNCHL': 'HICT', 'HTIT': 'HTIT', 'HHIT': 'HHIT', 'NDV': 'NAM DINH VU', 'TANVU': 'TAN VU', 'VGR': 'VIP GREEN PORT',
               'NHDV': 'NAM HAI DINH VU', 'DINHVU': 'DINH VU', 'HAIAN': 'HAI AN', 'GREEN': 'GREEN PORT', 'TC189': 'TAN CANG 189', 'CVP': 'CHUA VE',
               'VIMC': 'VIMC', 'NAMHAI': 'NAM HAI', 'PTSC': 'PTSC DINH VU', 'MPC': 'MPC PORT', 'NP128': 'CANG 128', 'DOANXA': 'DOAN XA'},
    'VN SGN': {'CATLAI': 'CAT LAI', 'VICT': 'VICT', 'TCHP': 'TAN CANG HIEP PHUOC', 'SPCT': 'SPCT', 'SPITC': 'SP-ITC'},
    'VN VUT': {'GML': 'GEMALINK', 'TCIT': 'TCIT', 'CMIT': 'CMIT', 'TCTT': 'TCTT', 'VNSST': 'SSIT', 'SITV': 'SITV'},
    'VN DAD': {'DNT': 'BẾN CẢNG TIÊN SA'},
}
WEB = 'https://www.econdb.com'
# cảng vụ nhiều cảng EconDB (HCM): bến -> cảng theo cột node của cangvu-hcm/areas.csv
PORT_NODES = {'VN SGN': ('HO CHI MINH',), 'VN VUT': ('CAI MEP', 'VUNG TAU', 'LONG SON (VUNG TAU)')}
AREAS_HCM = os.path.join(os.path.dirname(APP), 'cangvu-hcm', 'areas.csv')


def terminal_port(auth):
    """hàm bến (tên cảng vụ) -> locode EconDB. Cảng vụ 1 cảng: mọi bến về cảng đó; HCM: tra node trong areas.csv, không rõ -> None."""
    lcs = AUTH_LOCODES.get(auth, [])
    if len(lcs) <= 1: return lambda t: lcs[0] if lcs else None
    node_port = {n: lc for lc, nodes in PORT_NODES.items() for n in nodes}
    m = {}
    if os.path.exists(AREAS_HCM):
        a = pd.read_csv(AREAS_HCM, dtype=str).fillna('')
        m = {str(t).strip().upper(): node_port.get(str(n).strip().upper()) for t, n in zip(a['terminal'], a['node'])}
    return lambda t: m.get(str(t).strip().upper())
FLOW_METRIC = {'throughput': 'cap_throughput', 'import': 'cap_import', 'export': 'cap_export', 'transshipment': 'cap_transshipment'}
METRIC_LABEL = {'term_throughput': 'Throughput theo terminal (TEU)', 'term_full': 'Container full theo terminal (TEU)', 'traffic': 'Container full (TEU)', 'dwell': 'Ngày nằm bãi', 'cap_throughput': 'Sức chở tàu ghé (TEU)',
                'cap_import': 'TEU nhập theo hãng', 'cap_export': 'TEU xuất theo hãng', 'cap_transshipment': 'TEU trung chuyển theo hãng',
                'partner_export': 'TEU xuất theo khu vực', 'partner_import': 'TEU nhập theo khu vực',
                'p2p_export': 'TEU xuất VN theo nước', 'p2p_import': 'TEU nhập VN theo nước',
                'global_trade': 'TEU nhập khẩu toàn cầu', 'lane_capacity': 'Sức chở theo tuyến (TEU)'}
SERIES_VN = {'Imports': 'Nhập', 'Exports': 'Xuất', 'Transshipment': 'Trung chuyển', 'Transshipments': 'Trung chuyển'}


# ================================================================ client
def token():
    t = os.environ.get('ECONDB_TOKEN', '').strip()
    if not t and os.name == 'nt':           # phiên mở trước khi setx: đọc thẳng biến User trong registry
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as k:
                t = str(winreg.QueryValueEx(k, 'ECONDB_TOKEN')[0]).strip()
        except OSError:
            t = ''
    return t


class Client:
    def __init__(self, tok, pause=0.15):
        self.s = requests.Session(); self.s.headers.update({'Authorization': f'Token {tok}', 'Accept': 'application/json'})
        self.pause = pause; self.n = 0

    def get(self, path, **params):
        url = f"{API}/{path.strip('/')}/"
        for i in range(3):
            try:
                r = self.s.get(url, params={k: v for k, v in params.items() if v is not None}, timeout=90)
                self.n += 1; time.sleep(self.pause)
                if r.status_code == 429 or r.status_code >= 500:
                    if r.status_code >= 500 and i == 2: r.raise_for_status()
                    time.sleep(5 * (i + 1)); continue
                r.raise_for_status()
                return r.json()
            except requests.RequestException:
                if i == 2: raise
                time.sleep(3 * (i + 1))


def plot_long(j, scope, metric):
    """{type, series, data:[{Date|index, <code>: v}]} -> long. Tên hãng 'CMA CGM / Imports' -> 'CMA CGM'."""
    if not isinstance(j, dict) or not j.get('data'): return pd.DataFrame()
    d = pd.DataFrame(j['data'])
    dk = 'Date' if 'Date' in d else ('index' if 'index' in d else d.columns[0])
    d = d.rename(columns={dk: 'date'}).melt(id_vars='date', var_name='series', value_name='value')
    d['series'] = d['series'].astype(str).str.replace(r' / (Imports|Exports|Transshipment|Cargo)$', '', regex=True)
    d['date'] = pd.to_datetime(d['date'], errors='coerce'); d['value'] = pd.to_numeric(d['value'], errors='coerce')
    d = d.dropna(subset=['date', 'value'])
    d.insert(0, 'metric', metric); d.insert(0, 'scope', scope)
    return d


# ================================================================ kéo
def pull(only=None, log=print):
    tok = token()
    if not tok:
        log('econdb: thieu ECONDB_TOKEN -> bo qua (laptop: setx ECONDB_TOKEN; cloud: GitHub secret ECONDB_TOKEN)')
        return None
    os.makedirs(DIR, exist_ok=True)
    c = Client(tok); want = set(only or []) or None
    on = lambda k: want is None or k in want  # noqa: E731
    blocks, errs = [], []

    def grab(scope, metric, path, **kw):
        try:
            d = plot_long(c.get(path, **kw), scope, metric)
            if len(d): blocks.append(d)
            return len(d)
        except Exception as e:  # noqa: BLE001
            errs.append(f'{scope} {metric}: {type(e).__name__} {str(e)[:120]}'); return 0

    t0 = time.time()
    if on('ports'):
        try:
            p = pd.DataFrame(c.get('ports')); p.to_parquet(os.path.join(DIR, 'ports.parquet'), index=False)
            log(f'ports: {len(p)} cang')
        except Exception as e:  # noqa: BLE001
            errs.append(f'ports: {e}')
    for lc in VN_PORTS:
        p = f'ports/{lc}'
        if on('traffic'): grab(lc, 'traffic', f'{p}/container-traffic')
        if on('dwell'): grab(lc, 'dwell', f'{p}/dwell-times')
        if on('capacity'):
            for fl, m in FLOW_METRIC.items(): grab(lc, m, f'{p}/capacity-by-operator', flow=None if fl == 'throughput' else fl, top=0)
        if on('partner'):
            grab(lc, 'partner_export', f'{p}/trade-by-partner', is_export=1); grab(lc, 'partner_import', f'{p}/trade-by-partner', is_export=0)
    if on('terminals'):
        w = requests.Session(); w.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126'

        def wget(path, **params):
            c.n += 1; time.sleep(0.25)
            r = w.get(WEB + path, params=params or None, timeout=60); r.raise_for_status(); return r.json()
        meta, tsv = [], []
        for lc in VN_PORTS:
            try: codes = [t['code'] for t in (wget(f'/maritime/ports/async/{lc}/').get('terminals') or []) if t.get('code')]
            except Exception as e: errs.append(f'{lc} terminals: {str(e)[:100]}'); continue  # noqa: E701
            for code in codes:
                try:
                    dt = wget(f'/maritime/get_terminal_detail/{lc}/{code}/'); tid = dt.get('terminal_id')
                    meta.append({'locode': lc, 'code': code, **{k: dt.get(k) for k in ('terminal_id', 'name', 'operator', 'berth_length', 'yard_area', 'sts_count')}})
                    if not tid: continue
                    tp = wget('/widgets/port-time-series/data/', unit='throughput', locode=lc, by='teu_class', freq='month', terminal_id=tid)
                    d = plot_long((tp.get('plots') or [{}])[0], lc, 'term_throughput')
                    if len(d): blocks.append(d.groupby(['scope', 'metric', 'date'], as_index=False)['value'].sum().assign(series=code))
                    fu = wget('/widgets/sea-trade-by-week/data/', locode=lc, freq='month', terminal_id=tid)
                    d = plot_long((fu.get('plots') or [{}])[0], lc, 'term_full')
                    if len(d): blocks.append(d.groupby(['scope', 'metric', 'date'], as_index=False)['value'].sum().assign(series=code))
                    sv = wget('/widgets/port-time-series/data/', unit='throughput', locode=lc, by='service', freq='month', terminal_id=tid)
                    d = plot_long((sv.get('plots') or [{}])[0], lc, 'term_service')
                    if len(d): tsv.append(d.rename(columns={'series': 'service'}).assign(terminal=code))
                except Exception as e:  # noqa: BLE001
                    errs.append(f'{lc} {code}: {type(e).__name__} {str(e)[:100]}')
        if meta:
            pd.DataFrame(meta).to_parquet(os.path.join(DIR, 'terminals.parquet'), index=False); log(f'terminals: {len(meta)} terminal')
        if tsv:
            pd.concat(tsv, ignore_index=True).to_parquet(os.path.join(DIR, 'term_services.parquet'), index=False)
            log(f'tuyến dịch vụ theo bến: {sum(len(x) for x in tsv)} dòng')
    if on('peers'):
        for lc in PEERS: grab(lc, 'traffic', f'ports/{lc}/container-traffic')
    if on('p2p'):
        for iso in PARTNERS:
            for m, ex in (('p2p_export', 1), ('p2p_import', 0)):
                try:
                    d = plot_long(c.get('point2point/container-volume', reference='VN', partner=iso, is_export=ex), 'VN', m)
                    if len(d): d['series'] = iso; blocks.append(d)
                except Exception as e:  # noqa: BLE001
                    errs.append(f'p2p {iso} {m}: {str(e)[:100]}')
    if on('global'):
        grab('WORLD', 'global_trade', 'shipping-indicators/container-trade'); grab('WORLD', 'lane_capacity', 'shipping-indicators/lane-capacity')
    n_series = merge_series(blocks)
    log(f'series: {sum(len(b) for b in blocks)} dong moi / {n_series} dong trong kho ({c.n} request, {time.time() - t0:.0f}s)')

    if on('calls'):
        new = []
        for lc in VN_PORTS:
            try: new += c.get(f'ports/{lc}/vessel-calls') or []
            except Exception as e: errs.append(f'calls {lc}: {str(e)[:100]}')  # noqa: E701
        log(f'calls: {merge_calls(pd.DataFrame(new))}')
    if on('schedule'):
        rows = []
        for lc in VN_PORTS:
            try: rows += c.get(f'ports/{lc}/vessel-schedule') or []
            except Exception as e: errs.append(f'schedule {lc}: {str(e)[:100]}')  # noqa: E701
        if rows:
            s = pd.DataFrame(rows)
            for k in ('start_date', 'end_date'): s[k] = pd.to_datetime(s[k], errors='coerce', utc=True).dt.tz_convert('Asia/Ho_Chi_Minh').dt.tz_localize(None)
            s['fetched'] = pd.Timestamp.now().floor('min')
            s.to_parquet(os.path.join(DIR, 'schedule.parquet'), index=False); log(f'schedule: {len(s)} chuyen sap toi')
    if on('vessels') or on('portcalls'):
        try:
            v = pull_vessels(c, log) if on('vessels') else _read('vessels.parquet')
            if on('portcalls') and len(v):
                master = os.path.join(os.path.dirname(APP), 'cangvu-haiphong', 'data', 'vessel_master.csv')
                extra = []
                if os.path.exists(master):                     # thêm tàu container cảng vụ có IMO, ghé 12 tháng
                    mv = pd.read_csv(master, dtype=str, usecols=lambda x: x in ('imo', 'vessel_class', 'calls_12m'))
                    mv = mv[mv['vessel_class'].fillna('').str.startswith('container') & (pd.to_numeric(mv['calls_12m'], errors='coerce') > 0)]
                    extra = mv['imo'].dropna().tolist()
                n_err = pull_portcalls(c, v, max_n=PORTCALLS_MAX, extra_imos=extra, log=log)
                if n_err: errs.append(f'portcalls: {n_err} tàu lỗi')
        except Exception as e:  # noqa: BLE001
            errs.append(f'vessels/portcalls: {str(e)[:150]}')
    for e in errs: log('  LOI ' + e)
    return c.n, errs


PORTCALLS_MAX = 1500
PORTCALLS_DAYS = 365          # lần đầu kéo 12 tháng lượt ghé của mỗi tàu


def pull_vessels(c, log=print):
    """danh sách tàu container EconDB (1 request) -> vessels.parquet"""
    v = pd.DataFrame(c.get('vessels') or [])
    if v.empty: return v
    v['fetched'] = pd.Timestamp.now().floor('min')
    v.to_parquet(os.path.join(DIR, 'vessels.parquet'), index=False)
    log(f'vessels: {len(v)} tàu, {v["operator_name"].notna().sum()} có hãng khai thác')
    return v


def vn_vessel_mmsi(v, extra_imos=()):
    """mmsi các tàu từng ghé VN: lượt ghé EconDB tại cảng VN (calls.parquet) + lịch tàu + IMO thêm (vd vessel_master cảng vụ),
    sắp theo lượt VN gần nhất"""
    calls, sch = _read('calls.parquet'), _read('schedule.parquet')
    last = {}
    for d, col in ((calls, 'start'), (sch, 'start_date')):
        if len(d):
            for imo, t in d.groupby('ship_imo')[col].max().items():
                if pd.notna(imo): last[int(imo)] = max(last.get(int(imo), t), t)
    for imo in extra_imos:
        try: last.setdefault(int(float(imo)), pd.Timestamp('2000-01-01'))
        except (TypeError, ValueError): pass
    m = v.dropna(subset=['imo', 'mmsi']).assign(imo=lambda d: d['imo'].astype('int64')).drop_duplicates('imo').set_index('imo')['mmsi']
    out = [(last[i], int(m[i])) for i in last if i in m.index]
    return [mm for _, mm in sorted(out, reverse=True)]


def pull_portcalls(c, v, max_n=1500, extra_imos=(), log=print):
    """lượt ghé toàn cầu của các tàu ghé VN, cộng dồn: mỗi tàu kéo từ (lượt cuối đã có − 14 ngày) hoặc 12 tháng trước"""
    f = os.path.join(DIR, 'vessel_portcalls.parquet')
    old = pd.read_parquet(f) if os.path.exists(f) else pd.DataFrame()
    have = old.groupby('mmsi')['start'].max() if len(old) else pd.Series(dtype='datetime64[ns]')
    todo = vn_vessel_mmsi(v, extra_imos)[:max_n]; rows, errs = [], 0; t0 = time.time()
    for i, mm in enumerate(todo):
        d0 = (have[mm] - pd.Timedelta(days=14)) if mm in have.index else pd.Timestamp.now() - pd.Timedelta(days=PORTCALLS_DAYS)
        try:
            for r in c.get(f'vessels/{mm}/portcalls', date_from=d0.strftime('%Y-%m-%d')) or []:
                r['mmsi'] = mm; rows.append(r)
        except Exception:  # noqa: BLE001
            errs += 1
        if (i + 1) % 200 == 0: log(f'  portcalls {i + 1}/{len(todo)} tàu, {len(rows)} lượt, {time.time() - t0:.0f}s')
    new = pd.DataFrame(rows)
    if len(new):
        for k in ('start', 'end'): new[k] = pd.to_datetime(new[k], errors='coerce', utc=True).dt.tz_convert('Asia/Ho_Chi_Minh').dt.tz_localize(None)
        new = new[new['start'].notna() & (new['start'] <= pd.Timestamp.now() + pd.Timedelta(days=2))]
    out = pd.concat([old, new], ignore_index=True) if len(old) else new
    if len(out):
        out = out.drop_duplicates(['ship_imo', 'locode', 'start'], keep='last').sort_values(['mmsi', 'start'])
        out.to_parquet(f, index=False)
    log(f'portcalls: {len(todo)} tàu, {len(new)} lượt kéo về ({errs} lỗi), kho {len(out)} lượt / {out["mmsi"].nunique() if len(out) else 0} tàu')
    return errs


def merge_series(blocks):
    f = os.path.join(DIR, 'series.parquet')
    old = pd.read_parquet(f) if os.path.exists(f) else pd.DataFrame(columns=['scope', 'metric', 'series', 'date', 'value'])
    if not blocks: return len(old)
    new = pd.concat(blocks, ignore_index=True)
    keys = set(map(tuple, new[['scope', 'metric']].drop_duplicates().values))
    keep = old[[(a, b) not in keys for a, b in zip(old['scope'], old['metric'])]] if len(old) else old
    out = (pd.concat([keep, new], ignore_index=True) if len(keep) else new).sort_values(['scope', 'metric', 'series', 'date'])
    out.to_parquet(f, index=False)
    return len(out)


def merge_calls(new):
    f = os.path.join(DIR, 'calls.parquet')
    old = pd.read_parquet(f) if os.path.exists(f) else pd.DataFrame()
    if len(new):
        for k in ('start', 'end'): new[k] = pd.to_datetime(new[k], errors='coerce', utc=True).dt.tz_convert('Asia/Ho_Chi_Minh').dt.tz_localize(None)
        new = new[new['start'].notna() & (new['start'] <= pd.Timestamp.now() + pd.Timedelta(days=2))]   # API có vài bản ghi ngày 2027 -> lỗi
        new = new.assign(fetched=pd.Timestamp.now().floor('min'))
    out = pd.concat([old, new], ignore_index=True) if len(old) else new
    if out.empty: return '0 luot'
    out = out.drop_duplicates(['locode', 'ship_imo', 'start'], keep='last').sort_values(['locode', 'start'])
    out.to_parquet(f, index=False)
    return f'{len(new)} luot keo ve, kho {len(out)} luot ({out["start"].min():%d/%m/%Y} -> {out["start"].max():%d/%m/%Y})'


# ================================================================ đọc (app)
def _read(name):
    f = os.path.join(DIR, name)
    return pd.read_parquet(f) if os.path.exists(f) else pd.DataFrame()


def load():
    """dict các bảng + chữ ký mtime (để app làm khoá cache)."""
    return {k: _read(f'{k}.parquet') for k in ('series', 'calls', 'schedule', 'ports', 'vessels', 'vessel_portcalls', 'term_services', 'terminals')}


def stamp():
    return '|'.join(f'{n}:{os.path.getmtime(os.path.join(DIR, n)):.0f}' for n in sorted(os.listdir(DIR))) if os.path.isdir(DIR) else ''


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', default='', help='ports,traffic,dwell,capacity,partner,terminals,peers,p2p,global,calls,schedule,vessels,portcalls')
    ap.add_argument('--portcalls-max', type=int, default=None,
                    help='số tàu tối đa kéo lượt ghé (~0,8 s/tàu); mặc định 500 (ghé VN gần nhất trước), thứ Hai 2500')
    a = ap.parse_args(argv)
    global PORTCALLS_MAX
    PORTCALLS_MAX = a.portcalls_max or (2500 if time.localtime().tm_wday == 0 else 500)
    t0 = time.time()
    r = pull([x.strip() for x in a.only.split(',') if x.strip()])
    if r is None:
        print('DONE econdb: bo qua (khong co key)'); return 0
    n, errs = r
    ok = n > 0 and len(errs) < max(5, n // 4)
    print(f'{"DONE" if ok else "ERROR"} econdb: {n} request, {len(errs)} loi, kho {DIR} | {time.time() - t0:.0f}s')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
