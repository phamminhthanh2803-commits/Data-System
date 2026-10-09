# -*- coding: utf-8 -*-
"""
trackerlib.py - lớp dữ liệu cho PORT & VESSEL TRACKER. CHỈ ĐỌC các file do pipeline D:/shipping tạo ra:
  cangvu-haiphong/data : cvhp_calls.csv, cvhp_events.csv, vessel_master.csv   (+ terminals.csv)
  cangvu-hcm/data      : cvhcm_calls.csv, cvhcm_events.csv                     (+ berths.csv)
  vessel-itinerary/data: vessel_route_pattern.csv, lane_monthly.csv, itinerary_legs.csv
Lớp tàu / hãng / TEU luôn ghép trực tiếp từ vessel_master tại lúc nạp (không phụ thuộc bước --apply).
"""
import io, os, sys
from datetime import datetime

import numpy as np
import pandas as pd

HUB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HP = os.path.join(HUB, 'cangvu-haiphong'); HCM = os.path.join(HUB, 'cangvu-hcm'); ITI = os.path.join(HUB, 'vessel-itinerary')
FILES = {
    'hp_calls': os.path.join(HP, 'data', 'cvhp_calls.csv'), 'hcm_calls': os.path.join(HCM, 'data', 'cvhcm_calls.csv'),
    'hp_events': os.path.join(HP, 'data', 'cvhp_events.csv'), 'hcm_events': os.path.join(HCM, 'data', 'cvhcm_events.csv'),
    'master': os.path.join(HP, 'data', 'vessel_master.csv'),
    'hp_terminals': os.path.join(HP, 'terminals.csv'), 'hcm_terminals': os.path.join(HCM, 'terminals_hcm.csv'),
    'pattern': os.path.join(ITI, 'data', 'vessel_route_pattern.csv'), 'lanes': os.path.join(ITI, 'data', 'lane_monthly.csv'),
    'legs': os.path.join(ITI, 'data', 'itinerary_legs.csv'),
}
NAT = os.path.join(HUB, 'cangvu-toanquoc', 'data')
FILES.update({'nat_calls': os.path.join(NAT, 'national_calls.csv'), 'nat_terms': os.path.join(NAT, 'national_terminals.csv'),
              'nat_cov': os.path.join(NAT, 'coverage.csv')})
AUTH_LABEL = {'QN': 'Quảng Ninh', 'HP': 'Hải Phòng', 'TBH': 'Thái Bình', 'THA': 'Thanh Hoá', 'HTH': 'Hà Tĩnh', 'DNG': 'Đà Nẵng – Quảng Nam',
              'NTG': 'Nha Trang', 'BTN': 'Bình Thuận', 'DNI': 'Đồng Nai', 'HCM': 'TP.HCM – Cái Mép', 'CTO': 'Cần Thơ', 'KGG': 'Kiên Giang'}
AUTH_ORDER = list(AUTH_LABEL)                       # bắc -> nam
EVENT_DIRS = {'QNK': 'QN', 'TBH': 'TBH', 'THA': 'THA', 'HTH': 'HTH', 'DNG': 'DNG', 'NTG': 'NTG', 'BTN': 'BTN', 'DNI': 'DNI', 'CTO': 'CTO', 'KGG': 'KGG'}
CLASS_LABEL = {'container': 'Container', 'container?': 'Container (suy đoán)', 'general': 'Hàng tổng hợp', 'bulk': 'Hàng rời',
               'tanker': 'Dầu/hoá chất', 'gas': 'Khí hoá lỏng', 'roro': 'Ro-ro/ô tô', 'sb': 'Sông biển', 'unknown': 'Chưa rõ',
               'other': 'Khác', '': 'Chưa rõ'}


def mtime(key):
    p = FILES[key]
    return os.path.getmtime(p) if os.path.exists(p) else 0.0


def stamp(*keys):
    """khoá cache: đổi khi bất kỳ file nguồn nào đổi"""
    return tuple(round(mtime(k), 1) for k in keys)


def _read(key, **kw):
    p = FILES[key]
    if not os.path.exists(p): return pd.DataFrame()
    return pd.read_csv(p, encoding='utf-8-sig', dtype=str, keep_default_na=False, **kw)


def load_master():
    m = _read('master')
    if m.empty: return m
    for c in ('teu', 'dwt', 'gt', 'loa', 'calls_total', 'calls_12m'):
        if c in m: m[c] = pd.to_numeric(m[c], errors='coerce')
    m['vessel_class'] = m['vessel_class'].replace('', 'unknown')
    return m


def load_terminal_meta():
    hp = _read('hp_terminals'); hcm = _read('hcm_terminals')
    rows = []
    if not hp.empty:
        hp = hp.assign(auth='HP')[['auth', 'terminal', 'group', 'ticker', 'kind']]; rows.append(hp)
    if not hcm.empty:
        hcm = hcm.drop_duplicates('terminal').assign(auth='HCM')[['auth', 'terminal', 'group', 'ticker', 'kind']]; rows.append(hcm)
    nat = _read('nat_terms')
    if not nat.empty:
        rows.append(nat[~nat['auth'].isin(['HP', 'HCM'])][['auth', 'terminal', 'group', 'ticker', 'kind']])
    t = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=['auth', 'terminal', 'group', 'ticker', 'kind'])
    t['terminal'] = t['terminal'].str.upper().str.strip()
    return t.drop_duplicates(['auth', 'terminal'])


def load_calls():
    """Mọi chuyến của 2 cảng vụ + thông tin tàu. 1 dòng = 1 chuyến."""
    parts = []
    for auth, key in (('HP', 'hp_calls'), ('HCM', 'hcm_calls')):
        d = _read(key)
        if d.empty: continue
        d['auth'] = auth; parts.append(d)
    nat = _read('nat_calls')                                  # các cảng vụ khác (bộ toàn quốc); HP/HCM lấy từ file gốc cho mới nhất
    if not nat.empty:
        nat = nat[~nat['auth'].isin(['HP', 'HCM'])].rename(columns={'imo': 'imo_src'})
        parts.append(nat.drop(columns=[c for c in ('auth_name', 'source') if c in nat]))
    if not parts: return pd.DataFrame()
    c = pd.concat(parts, ignore_index=True)
    for col in ('origin', 'destination', 'berths', 'first_berth', 'agent', 'status', 'ship', 'ship_key'):
        c[col] = c[col].fillna('')
    c['arrival'] = pd.to_datetime(c['arrival'], errors='coerce'); c['departure'] = pd.to_datetime(c['departure'], errors='coerce')
    c['date'] = c['arrival'].fillna(c['departure']).dt.normalize()
    c['arr_day'] = c['arrival'].dt.normalize()
    for col in ('dwt', 'gt', 'loa', 'hours_in_port', 'n_shifts'):
        c[col] = pd.to_numeric(c[col], errors='coerce')
    m = load_master()
    if not m.empty:
        c = c.merge(m[['ship_key', 'imo', 'vessel_class', 'operator', 'teu', 'built', 'service']], on='ship_key', how='left')
    else:
        for col in ('imo', 'vessel_class', 'operator', 'teu', 'built', 'service'): c[col] = np.nan
    if 'imo_src' in c:
        c['imo'] = c['imo'].fillna('').where(c['imo'].fillna('') != '', c['imo_src'].fillna(''))
    c['vessel_class'] = c['vessel_class'].fillna('unknown').replace('', 'unknown')
    c['operator'] = c['operator'].fillna('').replace('', '(chưa rõ hãng)')
    c['is_container'] = c['vessel_class'].isin(['container', 'container?'])
    return c


def load_visits(calls, tmeta):
    """1 dòng = 1 lượt cập 1 bến của 1 chuyến (tách cột berths, bỏ khu neo/phao). Dùng cho thống kê theo bến."""
    v = calls[calls['arr_day'].notna()][['auth', 'call_id', 'ship', 'ship_key', 'arr_day', 'arrival', 'departure', 'berths', 'dwt',
                                           'teu', 'vessel_class', 'operator', 'is_container', 'hours_in_port', 'origin',
                                           'destination']].copy()
    v['terminal'] = v['berths'].str.split('|')
    v = v.explode('terminal'); v['terminal'] = v['terminal'].fillna('').str.strip()
    v = v[v['terminal'] != '']
    v = v.merge(tmeta, on=['auth', 'terminal'], how='left')
    for col in ('group', 'ticker', 'kind'): v[col] = v[col].fillna('')
    v = v[~v['kind'].isin(['anchorage'])]
    v['month'] = v['arr_day'].dt.to_period('M').dt.to_timestamp()
    return v.drop(columns=['berths'])


def load_events_recent(days_back=7):
    """Sự kiện kế hoạch gần đây (bảng điều độ): từ hôm nay-days_back trở đi."""
    lo = (pd.Timestamp.today().normalize() - pd.Timedelta(days=days_back)).strftime('%Y-%m-%d')
    parts = []
    for auth, key in (('HP', 'hp_events'), ('HCM', 'hcm_events')):
        p = FILES[key]
        if not os.path.exists(p): continue
        for chunk in pd.read_csv(p, encoding='utf-8-sig', dtype=str, keep_default_na=False, chunksize=100000):
            ch = chunk[chunk['plan_date'] >= lo]
            if len(ch): parts.append(ch.assign(auth=auth))
    for code, auth in EVENT_DIRS.items():
        p = os.path.join(NAT, code, 'events.csv')
        if not os.path.exists(p): continue
        for chunk in pd.read_csv(p, encoding='utf-8-sig', dtype=str, keep_default_na=False, chunksize=100000):
            ch = chunk[chunk['plan_date'] >= lo]
            if len(ch): parts.append(ch.assign(auth=auth))
    if not parts: return pd.DataFrame()
    e = pd.concat(parts, ignore_index=True)
    for col in ('from', 'to', 'agent', 'time'): e[col] = e[col].fillna('')
    if 'terminal_to' in e:
        e['terminal_to'] = e['terminal_to'].fillna(''); e['terminal_from'] = e['terminal_from'].fillna('')
        e['to'] = np.where(e['terminal_to'].fillna('') != '', e['terminal_to'], e['to'])
        e['from'] = np.where(e['terminal_from'].fillna('') != '', e['terminal_from'], e['from'])
    e['dwt'] = pd.to_numeric(e['dwt'], errors='coerce')
    m = load_master()
    if not m.empty:
        e = e.merge(m[['ship_key', 'vessel_class', 'operator', 'teu']], on='ship_key', how='left')
    return e


def load_pattern():
    d = _read('pattern')
    for c in ('teu', 'n_stops', 'n_legs', 'n_hp_calls', 'n_hcm_calls', 'total_nm'):
        if c in d: d[c] = pd.to_numeric(d[c], errors='coerce')
    return d


def load_lanes():
    d = _read('lanes')
    if d.empty: return d
    for c in ('legs', 'ships', 'teu_sum'): d[c] = pd.to_numeric(d[c], errors='coerce').fillna(0)
    d['month'] = pd.to_datetime(d['month'] + '-01', errors='coerce')
    d['lane'] = d['from'] + ' → ' + d['to']
    return d


# ---------------------------------------------------------------- tiện ích phân tích
def top_n_other(df, key, value, n=7, other='Khác', order=None):
    """Gộp đuôi vào 'Khác'. order = danh sách thực thể ưu tiên cố định (màu đi theo thực thể, không theo hạng trong kỳ lọc)."""
    if order is None:
        order = df.groupby(key)[value].sum().sort_values(ascending=False).index.tolist()
    keep = [k for k in order if k in set(df[key])][:n]
    out = df.copy(); out[key] = np.where(out[key].isin(keep), out[key], other)
    return out, keep + ([other] if (out[key] == other).any() else [])


def period_compare(df, date_col, value_col, end, days=30):
    """tổng value trong [end-days, end), kỳ liền trước, và cùng kỳ năm trước"""
    end = pd.Timestamp(end); a0 = end - pd.Timedelta(days=days); b0 = a0 - pd.Timedelta(days=days)
    y1 = end - pd.Timedelta(days=365); y0 = y1 - pd.Timedelta(days=days)
    s = lambda lo, hi: df.loc[(df[date_col] >= lo) & (df[date_col] < hi), value_col].sum()
    return s(a0, end), s(b0, a0), s(y0, y1)


def pct(a, b):
    return None if not b else (a - b) / b


def to_excel(sheets):
    """sheets: {tên sheet: DataFrame} -> bytes xlsx"""
    bio = io.BytesIO()
    with pd.ExcelWriter(bio, engine='openpyxl') as xw:
        for name, d in sheets.items():
            d2 = d.copy()
            for c in d2.columns:
                if pd.api.types.is_datetime64_any_dtype(d2[c]): d2[c] = d2[c].dt.tz_localize(None) if getattr(d2[c].dt, 'tz', None) else d2[c]
            d2.to_excel(xw, sheet_name=str(name)[:31], index=False)
    return bio.getvalue()


def freshness():
    rows = []
    for k, p in FILES.items():
        rows.append({'Bộ dữ liệu': k, 'File': p, 'Cập nhật': datetime.fromtimestamp(os.path.getmtime(p)).strftime('%d/%m/%Y %H:%M') if os.path.exists(p) else 'CHƯA CÓ',
                     'Dung lượng (MB)': round(os.path.getsize(p) / 1e6, 1) if os.path.exists(p) else None})
    return pd.DataFrame(rows)


def itinerary_module():
    sys.path.insert(0, ITI)
    import vessel_itinerary as vi
    return vi


# ================================================================ DỮ LIỆU TRỰC TIẾP (kho của app, do livedata kéo từ trang nguồn)
import livedata as ld   # noqa: E402


def master_live():
    """bảng tham chiếu tàu (vessel_master) + kết quả tra trực tuyến trong app (vessel_live ghi đè chỗ còn trống)"""
    m = load_master()
    v = ld.vessel_live()
    if v.empty: return m
    v = v.drop_duplicates('ship_key').set_index('ship_key')
    if m.empty:
        m = pd.DataFrame(columns=['ship_key', 'ship', 'imo', 'vessel_class', 'operator', 'teu', 'built', 'service', 'dwt'])
    m = m.set_index('ship_key')
    for k in v.index.difference(m.index): m.loc[k, 'ship'] = v.loc[k, 'ship']
    for col in ('imo', 'teu', 'vessel_class', 'built'):
        cur = m[col] if col in m else pd.Series(index=m.index, dtype=object)
        new = v[col].reindex(m.index)
        empty = cur.isna() | (cur.astype(str).isin(['', 'nan', 'unknown', 'container?']))
        m[col] = cur.where(~(empty & new.notna() & (new.astype(str) != '')), new)
    m['teu'] = pd.to_numeric(m['teu'], errors='coerce')
    m['vessel_class'] = m['vessel_class'].fillna('unknown').replace('', 'unknown')
    return m.reset_index()


def enrich_calls(c):
    if c.empty: return c
    c['date'] = c['arrival'].fillna(c['departure']).dt.normalize(); c['arr_day'] = c['arrival'].dt.normalize()
    m = master_live()
    c = c.rename(columns={'imo': 'imo_src'})
    if not m.empty:
        for col in ('imo', 'vessel_class', 'operator', 'teu', 'built', 'service'):
            if col not in m: m[col] = np.nan
        c = c.merge(m[['ship_key', 'imo', 'vessel_class', 'operator', 'teu', 'built', 'service']], on='ship_key', how='left')
    else:
        for col in ('imo', 'vessel_class', 'operator', 'teu', 'built', 'service'): c[col] = np.nan
    c['imo'] = c['imo'].fillna('').astype(str).where(c['imo'].fillna('').astype(str) != '', c['imo_src'].fillna(''))
    c['vessel_class'] = c['vessel_class'].fillna('unknown').replace('', 'unknown')
    c['operator'] = c['operator'].fillna('').replace('', '(chưa rõ hãng)')
    c['is_container'] = c['vessel_class'].isin(['container', 'container?'])
    return c


def calls_from_store(auths, lo, hi):
    return enrich_calls(ld.build_calls(ld.load_events(list(auths), lo, hi)))


def _cdate(c):
    return c['arrival'].fillna(c['departure'])


def calls_frozen(auths, lo, b):
    """phần LỊCH SỬ: chuyến có ngày < b. Dùng sự kiện tới b+30 ngày để chuyến vào trước b vẫn thấy lượt rời."""
    b = pd.Timestamp(b)
    c = ld.build_calls(ld.load_events(list(auths), lo, (b + pd.Timedelta(days=30)).date()))
    return c[_cdate(c) < b] if len(c) else c


def calls_tail(auths, b, hi):
    """phần ĐUÔI gần đây: chuyến có ngày >= b. Dùng sự kiện từ b-45 ngày để có ngữ cảnh lượt vào."""
    b = pd.Timestamp(b)
    c = ld.build_calls(ld.load_events(list(auths), (b - pd.Timedelta(days=45)).date(), hi))
    return c[_cdate(c) >= b] if len(c) else c


def ship_calls(ship_key):
    return enrich_calls(ld.build_calls(ld.load_ship_events(ship_key)))


def terminal_meta(calls):
    """HP, HCM: bảng gán tay (chủ bến, mã CK). Cảng vụ khác: lấy tên bến từ dữ liệu, loại bến suy bằng từ khoá."""
    rows = []
    hp = _read('hp_terminals'); hcm = _read('hcm_terminals')
    if not hp.empty: rows.append(hp.assign(auth='HP')[['auth', 'terminal', 'group', 'ticker', 'kind']])
    if not hcm.empty: rows.append(hcm.drop_duplicates('terminal').assign(auth='HCM')[['auth', 'terminal', 'group', 'ticker', 'kind']])
    oth = calls[~calls['auth'].isin(['HP', 'HCM'])][['auth', 'berths']].copy()
    if len(oth):
        oth['terminal'] = oth['berths'].str.split('|'); oth = oth.explode('terminal')
        oth = oth[oth['terminal'].fillna('') != ''].drop_duplicates(['auth', 'terminal'])
        oth['group'] = oth['terminal'].str.title(); oth['ticker'] = ''; oth['kind'] = oth['terminal'].map(ld.pkh.infer_kind)
        rows.append(oth[['auth', 'terminal', 'group', 'ticker', 'kind']])
    t = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=['auth', 'terminal', 'group', 'ticker', 'kind'])
    t['terminal'] = t['terminal'].str.upper().str.strip()
    return t.drop_duplicates(['auth', 'terminal'])


def events_day(auths, day):
    e = ld.load_events(list(auths), day, day).rename(columns={'b_from': 'from', 'b_to': 'to'})
    if e.empty: return e
    m = master_live()
    if not m.empty: e = e.drop(columns=['imo']).merge(m[['ship_key', 'imo', 'vessel_class', 'operator', 'teu']], on='ship_key', how='left')
    for col in ('from', 'to', 'agent', 'time'): e[col] = e[col].fillna('')
    return e


def build_lanes(calls, classes=('container', 'container?')):
    """Chặng + vòng tuyến tính TRONG APP từ chuyến vừa ghép (không đọc file itinerary)."""
    vi = itinerary_module(); geo = vi.Geo(); dist = vi.Dist()
    c = calls[calls['vessel_class'].isin(classes) & calls['date'].notna()].copy()
    if c.empty: return pd.DataFrame(), pd.DataFrame()
    c['arrival'] = c['arrival'].dt.strftime('%Y-%m-%d %H:%M').fillna(''); c['departure'] = c['departure'].dt.strftime('%Y-%m-%d %H:%M').fillna('')
    keep = ['auth', 'ship', 'ship_key', 'arrival', 'departure', 'origin', 'destination', 'berths', 'first_berth', 'status', 'operator', 'teu']
    legs = []; pats = []
    for key, g in c[keep].fillna('').groupby('ship_key', sort=False):
        recs = g.to_dict('records'); name = recs[0]['ship']
        hp_ = [r for r in recs if r['auth'] == 'HP']; hcm_ = [r for r in recs if r['auth'] == 'HCM']
        oth = [dict(r, ship=r['auth']) for r in recs if r['auth'] not in ('HP', 'HCM')]
        stops = vi.stops_for_ship(hp_, hcm_, geo, other_calls=oth or None)
        if len(stops) < 2: continue
        op = recs[0]['operator']; teu = pd.to_numeric(recs[0]['teu'], errors='coerce')
        for l in vi.legs_from_stops(stops, dist):
            legs.append((l['t'].strftime('%Y-%m'), l['from'], l['to'], op, key, 0 if pd.isna(teu) else float(teu)))
        pat, ports = vi.route_pattern(stops)
        pats.append({'ship_key': key, 'ship': name, 'operator': op, 'teu': teu, 'route_pattern': pat, 'ports_called': ports, 'n_stops': len(stops)})
    dist.save()
    L = pd.DataFrame(legs, columns=['month', 'from', 'to', 'operator', 'ship_key', 'teu'])
    if L.empty: return L, pd.DataFrame(pats), L
    return lanes_from_legs(L), pd.DataFrame(pats).sort_values('n_stops', ascending=False), L


def lanes_from_legs(L):
    """bảng chặng theo tàu (month, from, to, operator, ship_key, teu) -> chặng gộp theo tháng/hãng. App dùng để lọc tuyến theo cảng vụ / bến."""
    if L.empty: return pd.DataFrame(columns=['month', 'from', 'to', 'operator', 'legs', 'ships', 'teu_sum', 'lane'])
    lanes = (L.groupby(['month', 'from', 'to', 'operator'], as_index=False)
             .agg(legs=('ship_key', 'size'), ships=('ship_key', 'nunique'), teu_sum=('teu', 'sum')))
    lanes['month'] = pd.to_datetime(lanes['month'] + '-01'); lanes['lane'] = lanes['from'] + ' → ' + lanes['to']
    return lanes
