# -*- coding: utf-8 -*-
"""
pkh_scrape.py - Kéo KẾ HOẠCH ĐIỀU ĐỘNG TÀU của các cảng vụ dùng nền tảng "public-kh"
(Hệ thống dịch vụ hành chính công trực tuyến - portlet TichHopGiaoThong, mỗi cảng vụ 1 máy chủ riêng).
Trang công khai:  <base>#/tra-cuu/ke_hoach/0/0/KeHoachDieuDongTau2
API (JSON, không cần đăng nhập) - chính là các request trang công khai gọi:
    getURLInit                         -> danh sách URL tài nguyên
    vma_itinerary_schedule_come        -> tàu đến   (timeOfArrival=dd/mm/yyyy ; BỎ tham số ngày = trả toàn bộ lịch sử)
    vma_itinerary_schedule_leave       -> tàu rời   (timeOfDeparture=...)
    vma_schedule_shifting              -> di chuyển (shiftingDate=...)
    findVmaItineraryScheduleByItineraryNo -> chi tiết 1 chuyến: cảng trước / cảng kế (UN/LOCODE), hàng, mục đích
Có sẵn IMO, hô hiệu, GT, DWT, NT, LOA, mã chuyến itineraryNo (nối chính xác lượt đến - di chuyển - rời).
CHỈ lấy trường vận hành của tàu/chuyến. KHÔNG lấy tên thuyền trưởng, thuyền viên, điện thoại/email đại lý.

Danh sách cảng vụ: authorities.csv (platform=pkh). Dữ liệu: data/<CODE>/events.csv, calls.csv, terminals.csv.

Chạy:
    python pkh_scrape.py                       # hằng ngày: kéo [hôm nay-3 .. +1] mọi cảng vụ, cập nhật theo id, rebuild
    python pkh_scrape.py --full                # lần đầu: kéo TOÀN BỘ lịch sử (3 request lớn / cảng vụ, ~1 phút mỗi request)
    python pkh_scrape.py --only DNG,HTH --full
    python pkh_scrape.py --details 400         # tra cảng trước/cảng kế cho 400 chuyến tàu lớn gần nhất chưa có (giãn 0,6s)
    python pkh_scrape.py --no-fetch            # chỉ rebuild calls + bảng tổng hợp toàn quốc
"""
import argparse, csv, json, os, re, sys, time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import requests
import urllib3

urllib3.disable_warnings()
ROOT = os.path.dirname(os.path.abspath(__file__)); HUB = os.path.dirname(ROOT)
DATA = os.path.join(ROOT, 'data')
sys.path.insert(0, os.path.join(HUB, 'cangvu-haiphong'))
from cvhp_scrape import norm_name, ship_key, read_csv, write_csv   # noqa: E402

H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 cangvu-toanquoc', 'Accept-Language': 'vi',
     'X-Requested-With': 'XMLHttpRequest'}
Q = ('?p_p_id={pid}&p_p_lifecycle=2&p_p_state=normal&p_p_mode=view&p_p_cacheability=cacheLevelPage'
     '&p_p_col_id=column-1&p_p_col_count=1&p_p_resource_id=getURLInit')
PIDS = ('kehoachaction_WAR_TichHopGiaoThongportlet', 'vma_WAR_TichHopGiaoThongportlet')
EVENT_FIELDS = ['auth', 'rec_id', 'itinerary_no', 'plan_date', 'section', 'time', 'ship', 'ship_key', 'imo', 'callsign', 'flag',
                'is_sb', 'loa', 'breadth', 'draft', 'dwt', 'gt', 'nt', 'region', 'from', 'to', 'berth', 'channel', 'agent',
                'tugs', 'reason', 'fetched_at']
CALL_FIELDS = ['call_id', 'auth', 'itinerary_no', 'ship', 'ship_key', 'imo', 'callsign', 'flag', 'is_sb', 'dwt', 'gt', 'loa', 'agent',
               'arrival', 'arr_date', 'origin', 'first_berth', 'berths', 'last_berth', 'n_shifts', 'shifts', 'departure', 'dep_date',
               'destination', 'hours_in_port', 'status', 'n_revisions', 'last_port', 'next_port', 'cargo']
DETAIL_FIELDS = ['auth', 'itinerary_no', 'last_port', 'next_port', 'next_port_state', 'previous_ports', 'subsequent_ports',
                 'cargo_type', 'cargo_remaining', 'cargo_quantity', 'purpose', 'ship_owner', 'fetched_at']
KIND_RULES = [
    ('anchorage', r'ĐÓN TRẢ HOA TIÊU|KIỂM DỊCH|KHU NEO|VÙNG NEO|\bNEO\b|P/S|TRÁNH BÃO|TRÚ BÃO'),
    ('offshore', r'NGOÀI KHƠI|\bMỎ\b|GIÀN|DẦU KHÍ NGOÀI'),
    ('shipyard', r'ĐÓNG TÀU|SỬA CHỮA TÀU|SHIPYARD|Ụ TÀU'),
    ('gas', r'\bGAS\b|\bLPG\b|KHÍ HOÁ LỎNG|KHÍ HÓA LỎNG'),
    ('petro', r'XĂNG DẦU|PETRO|PVOIL|KHO DẦU|LỌC DẦU|LỌC HÓA DẦU|LỌC HOÁ DẦU|HÓA DẦU|HOÁ DẦU|NHỰA ĐƯỜNG'),
    ('cement', r'XI MĂNG|CLINKER'),
    ('power', r'NHIỆT ĐIỆN|ĐIỆN LỰC'),
    ('passenger', r'TÀU KHÁCH|BẾN KHÁCH|HÀNH KHÁCH|DU LỊCH|PHÀ'),
    ('buoy', r'BẾN PHAO|\bPHAO\b|CHUYỂN TẢI'),
]


def log(*a): print(datetime.now().strftime('%H:%M:%S'), *a, flush=True)


def clean(s): return re.sub(r'\s+', ' ', re.sub(r'<br\s*/?>', ' ', str(s or ''))).strip(' ,')


def infer_kind(name):
    for k, rx in KIND_RULES:
        if re.search(rx, name, re.I): return k
    return 'general'


def split_place(s):
    """'KHU VỰC HH ĐÀ NẴNG, Bến cảng Tiên Sa, Cầu cảng số 3 (Tiên Sa 3)' -> (region, terminal, berth)"""
    parts = [p.strip() for p in clean(s).split(',') if p.strip()]
    if not parts: return '', '', ''
    if len(parts) >= 3: return parts[0].upper(), parts[1].upper(), ', '.join(parts[2:])
    if len(parts) == 2:
        if re.match(r'(KHU VỰC|KV)\b', parts[0], re.I): return parts[0].upper(), parts[1].upper(), ''
        return '', parts[0].upper(), parts[1]
    return '', parts[0].upper(), ''


def pdt(s):
    try: return datetime.strptime(s, '%d/%m/%Y %H:%M') if s else None
    except ValueError: return None


# ---------------------------------------------------------------- API
class Host:
    def __init__(self, row):
        self.code = row['code']; self.name = row['name']; self.base = row['base']; self.mc = row['maritime_code']
        self.use = row['use']; self.sess = requests.Session(); self.urls = None
        self.dir = os.path.join(DATA, self.code); os.makedirs(self.dir, exist_ok=True)

    def init(self):
        u = {}
        for pid in PIDS:
            r = self.sess.get(self.base + Q.format(pid=pid), headers=H, timeout=60, verify=False)
            u.update({k: v for k, v in r.json().items() if isinstance(v, str)})
        self.urls = u

    def get(self, key, timeout=600, **params):
        if self.urls is None: self.init()
        for i in range(3):
            try:
                r = self.sess.get(self.urls[key], params=params, headers=H, timeout=timeout, verify=False)
                r.raise_for_status(); j = r.json()
                return j.get('data', []) if isinstance(j, dict) else []
            except Exception as e:
                log(f'  [{self.code}] loi {key} ({str(e)[:80]}); thu lai {i + 1}/3'); time.sleep(5 * (i + 1)); self.urls = None
                try: self.init()
                except Exception: pass
        return None

    PAGE = 1500                                   # kéo toàn bộ theo trang: máy chủ lớn (HP, Quảng Ninh, Đồng Nai) bị 504 nếu lấy 1 lần

    def paged(self, key, p, d):
        if d is not None:
            p['start'] = p['end'] = -1
            return self.get(key, **p)
        out = []; i = 0
        while True:
            p['start'] = i; p['end'] = i + self.PAGE
            rows = self.get(key, timeout=300, **p)
            if rows is None: return out or None
            out.extend(rows)
            if len(rows) < self.PAGE: return out
            i += self.PAGE
            if i % (self.PAGE * 10) == 0: log(f'  [{self.code}] {key[:34]}: {i} ban ghi...')
            time.sleep(0.5)

    def come(self, d=None):
        p = dict(itineraryType='arrival', noticeShipType=1, maritimeCode=self.mc, markedAsArrival='3,4,5,7,8,9', shipBoat='SHIP')
        if d: p['timeOfArrival'] = d.strftime('%d/%m/%Y')
        return self.paged('getVmaItinerarySchedule_Come_URL', p, d)

    def leave(self, d=None):
        p = dict(itineraryType='departure', noticeShipType=2, maritimeCode=self.mc, markedAsDeparture='3,4,5,7,8,9', shipBoat='SHIP')
        if d: p['timeOfDeparture'] = d.strftime('%d/%m/%Y')
        return self.paged('getVmaItinerarySchedule_Leave_URL', p, d)

    def shifting(self, d=None):
        p = dict(maritimeCode=self.mc, requestState=4, noticeShipType=4)
        if d: p['shiftingDate'] = d.strftime('%d/%m/%Y')
        return self.paged('getVmaScheduleShiftingURL', p, d)

    def detail(self, itinerary_no):
        return self.get('findVmaItineraryScheduleByItineraryNoURL', timeout=90, itineraryNo=itinerary_no)


def to_event(auth, sec, r, fetched_at):
    if sec == 'DiChuyen':
        t = pdt(r.get('shiftingDate')); rid = f"S{r.get('vmaScheduleShiftingId')}"
        _, frm, fb = split_place(r.get('from')); reg, to, tb = split_place(r.get('to') or
                                                                         f"{r.get('shiftingPortHarbourName', '')}, {r.get('shiftingPortWharfName', '')}")
        berth = tb; agent = clean(r.get('shipAgencyName') or r.get('nameOfShipownersAgents'))
    else:
        t = pdt(r.get('timeOfArrival') if sec == 'Vao' else r.get('timeOfDeparture')); rid = f"I{r.get('vmaItineraryScheduleId')}"
        reg, term, berth = split_place(r.get('anchoringPortWharfName'))
        frm, to = ('', term) if sec == 'Vao' else (term, '')
        agent = clean(r.get('shipAgencyName'))
    if t is None or not (2015 <= t.year <= date.today().year + 1): return None       # bỏ bản ghi ngày lỗi (năm 0003, 3023...)
    name = norm_name(r.get('nameOfShip'))
    if not name: return None
    draft = max(float(r.get('shownDraftxA') or 0), float(r.get('shownDraftxF') or 0)) or ''
    return {'auth': auth, 'rec_id': rid, 'itinerary_no': r.get('itineraryNo', ''), 'plan_date': t.strftime('%Y-%m-%d'), 'section': sec,
            'time': t.strftime('%H:%M'), 'ship': name, 'ship_key': ship_key(name), 'imo': clean(r.get('imoNumber')),
            'callsign': clean(r.get('callSign')), 'flag': clean(r.get('flagStateOfShipName')),
            'is_sb': 1 if str(r.get('vrCode', '')).upper().startswith('VRSB') or re.search(r'\((VR-)?SB\)', name) else 0,
            'loa': r.get('loa') or '', 'breadth': r.get('breadth') or '', 'draft': draft, 'dwt': r.get('dwt') or '', 'gt': r.get('gt') or '',
            'nt': r.get('nt') or '', 'region': reg, 'from': frm, 'to': to, 'berth': berth, 'channel': clean(r.get('chanelName')),
            'agent': agent, 'tugs': clean(r.get('tugBoatNames') or r.get('tugboatList')), 'reason': clean(r.get('reasonToShift')),
            'fetched_at': fetched_at}


def fetch_host(h, full, days, fetched_at):
    p = os.path.join(h.dir, 'events.csv')
    ev = {(e['section'], e['rec_id']): e for e in read_csv(p)}
    n0 = len(ev); got = 0
    jobs = [(None,)] if full else [(d,) for d in days]
    for (d,) in jobs:
        for sec, fn in (('Vao', h.come), ('Roi', h.leave), ('DiChuyen', h.shifting)):
            rows = fn(d)
            if rows is None: log(f'  [{h.code}] {sec} {d or "toan bo"}: THAT BAI'); continue
            for r in rows:
                e = to_event(h.code, sec, r, fetched_at)
                if e: ev[(sec, e['rec_id'])] = e; got += 1
            if full: log(f'  [{h.code}] {sec} toan bo: {len(rows)} ban ghi')
            time.sleep(0.3)
    rows = sorted(ev.values(), key=lambda e: (e['plan_date'], e['time'], e['section']))
    write_csv(p, rows, EVENT_FIELDS)
    log(f'[{h.code}] {h.name}: nhan {got} ban ghi, events {n0} -> {len(rows)}')
    return rows


# ---------------------------------------------------------------- calls theo mã chuyến
def build_calls(events, details):
    by = defaultdict(list)
    for e in events:
        by[e['itinerary_no'] or f"{e['ship_key']}|{e['plan_date']}"].append(e)
    out = []
    for ino, evs in by.items():
        evs.sort(key=lambda e: (e['plan_date'], e['time'], {'Vao': 0, 'DiChuyen': 1, 'Roi': 2}[e['section']]))
        arr = [e for e in evs if e['section'] == 'Vao']; dep = [e for e in evs if e['section'] == 'Roi']
        sh = [e for e in evs if e['section'] == 'DiChuyen']; e0 = evs[-1]
        a = arr[-1] if arr else None; d = dep[-1] if dep else None                       # bản sau cùng = kế hoạch đã điều chỉnh
        berths = []
        for e in ([a] if a else []) + sh + ([d] if d else []):
            for t in ([e['to']] if e['section'] != 'Roi' else [e['from']]):
                if t and (not berths or berths[-1] != t): berths.append(t)
            if e['section'] == 'DiChuyen' and e['from'] and not berths[:-1]: berths.insert(0, e['from']) if e['from'] != berths[0] else None
        ta = datetime.strptime(a['plan_date'] + ' ' + a['time'], '%Y-%m-%d %H:%M') if a else None
        td = datetime.strptime(d['plan_date'] + ' ' + d['time'], '%Y-%m-%d %H:%M') if d else None
        if td and ta and td < ta: td = None
        st = 'complete' if (a and d and td) else 'no_departure' if a else 'no_arrival' if d else 'shift_only'
        det = details.get(ino, {})
        mx = lambda f: max([float(e[f]) for e in evs if e[f] not in ('', None)] or [0]) or ''
        out.append({'call_id': ino, 'auth': e0['auth'], 'itinerary_no': ino, 'ship': e0['ship'], 'ship_key': e0['ship_key'],
                    'imo': next((e['imo'] for e in evs if e['imo']), ''), 'callsign': next((e['callsign'] for e in evs if e['callsign']), ''),
                    'flag': e0['flag'], 'is_sb': e0['is_sb'], 'dwt': mx('dwt'), 'gt': mx('gt'), 'loa': mx('loa'), 'agent': e0['agent'],
                    'arrival': ta.strftime('%Y-%m-%d %H:%M') if ta else '', 'arr_date': a['plan_date'] if a else '',
                    'origin': det.get('last_port', ''), 'first_berth': berths[0] if berths else '', 'berths': '|'.join(berths),
                    'last_berth': berths[-1] if berths else '', 'n_shifts': len(sh),
                    'shifts': '|'.join(f"{e['plan_date']} {e['time']} {e['from']}>{e['to']}" for e in sh),
                    'departure': td.strftime('%Y-%m-%d %H:%M') if td else '', 'dep_date': d['plan_date'] if (d and td) else '',
                    'destination': det.get('next_port', ''), 'hours_in_port': round((td - ta).total_seconds() / 3600, 1) if (ta and td) else '',
                    'status': st, 'n_revisions': max(0, len(arr) - 1), 'last_port': det.get('last_port', ''),
                    'next_port': det.get('next_port', ''), 'cargo': det.get('cargo_remaining', '')})
    out.sort(key=lambda r: (r['arrival'] or r['departure'], r['ship']))
    return out


def build_terminals(events):
    c = Counter(); reg = {}
    for e in events:
        for t in (e['from'], e['to']):
            if t: c[t] += 1; reg.setdefault(t, e['region'])
    return [{'terminal': t, 'group': t.title(), 'ticker': '', 'kind': infer_kind(t), 'region': reg.get(t, ''), 'n_events': n}
            for t, n in c.most_common()]


# ---------------------------------------------------------------- chi tiết chuyến (cảng trước / cảng kế)
def run_details(h, limit, min_dwt, sleep):
    p = os.path.join(h.dir, 'details.csv')
    det = {r['itinerary_no']: r for r in read_csv(p)}
    calls = read_csv(os.path.join(h.dir, 'calls.csv'))
    todo = [c for c in calls if c['itinerary_no'] and c['itinerary_no'] not in det and float(c['dwt'] or 0) >= min_dwt and c['arrival']]
    todo.sort(key=lambda c: c['arrival'], reverse=True)
    now = datetime.now().strftime('%Y-%m-%d %H:%M'); n = 0
    for c in todo[:limit]:
        rows = h.detail(c['itinerary_no'])
        if rows is None: continue
        a = next((r for r in rows if r.get('noticeShipType') == 1), {}); d = next((r for r in rows if r.get('noticeShipType') == 2), {})
        det[c['itinerary_no']] = {
            'auth': h.code, 'itinerary_no': c['itinerary_no'], 'last_port': clean(a.get('lastPortOfCallCode')),
            'next_port': clean(d.get('portGoingToCode') or a.get('portGoingToCode')), 'next_port_state': clean(d.get('portGoingToStateName')),
            'previous_ports': clean(a.get('previousPortsOfCall')), 'subsequent_ports': clean(d.get('subsequentPortsOfCall')),
            'cargo_type': clean(a.get('cargoType')), 'cargo_remaining': clean(a.get('remainingCargo')),
            'cargo_quantity': clean(a.get('quantityOfCargo') or d.get('quantityOfCargo')), 'purpose': clean(a.get('purposeCode')),
            'ship_owner': clean(a.get('shipOwnersName')), 'fetched_at': now}
        n += 1
        if n % 50 == 0:
            write_csv(p, list(det.values()), DETAIL_FIELDS); log(f'  [{h.code}] chi tiet {n}/{min(limit, len(todo))}')
        time.sleep(sleep)
    write_csv(p, list(det.values()), DETAIL_FIELDS)
    log(f'[{h.code}] DONE details: +{n} (con {max(0, len(todo) - n)} chuyen >= {int(min_dwt)} DWT chua tra)')


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--full', action='store_true'); ap.add_argument('--only', default='')
    ap.add_argument('--no-fetch', action='store_true'); ap.add_argument('--details', type=int, default=0)
    ap.add_argument('--min-dwt', type=float, default=3000); ap.add_argument('--sleep', type=float, default=0.6)
    ap.add_argument('--days-back', type=int, default=3)
    a = ap.parse_args()
    auths = [r for r in read_csv(os.path.join(ROOT, 'authorities.csv')) if r['platform'] == 'pkh']
    if a.only: auths = [r for r in auths if r['code'] in a.only.split(',')]
    hosts = [Host(r) for r in auths]
    today = date.today(); days = [today + timedelta(days=i) for i in range(-a.days_back, 2)]
    fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M')

    def work(h):
        try:
            events = read_csv(os.path.join(h.dir, 'events.csv')) if a.no_fetch else fetch_host(h, a.full, days, fetched_at)
            if a.details and h.use == 'calls':
                write_csv(os.path.join(h.dir, 'calls.csv'), build_calls(events, {}), CALL_FIELDS) if not os.path.exists(os.path.join(h.dir, 'calls.csv')) else None
                run_details(h, a.details, a.min_dwt, a.sleep)
            det = {r['itinerary_no']: r for r in read_csv(os.path.join(h.dir, 'details.csv'))}
            calls = build_calls(events, det)
            write_csv(os.path.join(h.dir, 'calls.csv'), calls, CALL_FIELDS)
            write_csv(os.path.join(h.dir, 'terminals.csv'), build_terminals(events), ['terminal', 'group', 'ticker', 'kind', 'region', 'n_events'])
            st = Counter(c['status'] for c in calls)
            yrs = sorted({c['arr_date'][:4] for c in calls if c['arr_date']})
            log(f'[{h.code}] DONE calls: {len(calls)} chuyen {dict(st)} | nam {yrs[0] if yrs else "-"}..{yrs[-1] if yrs else "-"}')
            return h.code, len(events), len(calls)
        except Exception as e:
            log(f'[{h.code}] LOI: {e}'); return h.code, 0, 0

    with ThreadPoolExecutor(max_workers=len(hosts) or 1) as ex:                 # mỗi cảng vụ 1 luồng (máy chủ khác nhau)
        res = list(ex.map(work, hosts))

    # bảng IMO toàn quốc (mọi cảng vụ pkh, kể cả HPH) cho vessel_enrich
    imo = {}
    for h in hosts:
        for e in read_csv(os.path.join(h.dir, 'events.csv')):
            x = e['imo'] or ''
            if re.fullmatch(r'\d{7}', x) and sum(int(x[i]) * (7 - i) for i in range(6)) % 10 == int(x[6]):
                k = e['ship_key']; cur = imo.get(k)
                if cur is None or e['plan_date'] > cur['last_seen']:
                    imo[k] = {'ship_key': k, 'ship': e['ship'], 'imo': e['imo'], 'callsign': e['callsign'], 'flag': e['flag'],
                              'gt': e['gt'], 'dwt': e['dwt'], 'loa': e['loa'], 'last_seen': e['plan_date'], 'auth': e['auth']}
    if imo:
        write_csv(os.path.join(DATA, 'imo_map.csv'), sorted(imo.values(), key=lambda r: r['ship_key']),
                  ['ship_key', 'ship', 'imo', 'callsign', 'flag', 'gt', 'dwt', 'loa', 'last_seen', 'auth'])
    log(f'DONE pkh: {res} | imo_map {len(imo)} tau')
    return 0


if __name__ == '__main__':
    sys.exit(main())
