# -*- coding: utf-8 -*-
"""
cvhp_scrape.py - Kéo KẾ HOẠCH ĐIỀU ĐỘNG TÀU hằng ngày của Cảng vụ Hàng hải Hải Phòng
                 https://csdltau.cangvuhaiphong.gov.vn/pages/ship_plan.aspx?d=<offset>
    d = số ngày lệch so với HÔM NAY (server): 0 = hôm nay, -1 = hôm qua, 1 = ngày mai. Lùi được nhiều năm (d=-1000 vẫn có).
    Mỗi ngày có 4 bảng: Rời cảng (Roi) / Di chuyển (DiChuyen) / Vào cảng (Vao) / Qua luồng (QuaLuong).
    Trang của một ngày được bổ sung dần trong ngày -> mặc định luôn kéo lại [hôm nay-3 .. ngày mai] và THAY toàn bộ dòng của ngày đó.

Kết quả (data/):
    cvhp_events.csv          : master long, 1 dòng = 1 sự kiện (plan_date, section, time, ship, dwt, gt, from, to, ...)
    cvhp_calls.csv           : 1 dòng = 1 CHUYẾN TÀU cập cảng (ghép Vào -> Di chuyển* -> Rời cùng tên tàu, khử trùng lặp
                               do tàu vắt sang nhiều ngày). DWT/GT đếm 1 lần/chuyến, các bến đã làm hàng, giờ nằm cảng.
    cvhp_terminal_daily.csv  : theo ngày x bến: số tàu vào bến (Vào + Di chuyển đến), số tàu rời bến, DWT/GT tương ứng.
    cvhp_daily.csv           : tổng theo ngày (số tàu + DWT vào/rời cảng HP, số tàu di chuyển, qua luồng).
    raw/YYYY-MM-DD.html      : cache HTML gốc (parse lại không cần mạng: --no-fetch khi events trống).

Chạy:
    python cvhp_scrape.py                       # kéo [hôm nay-3 .. +1], rebuild bảng dẫn xuất
    python cvhp_scrape.py --from 2024-01-01     # backfill lịch sử (bỏ qua ngày đã có, --force để kéo lại)
    python cvhp_scrape.py --from 2026-09-01 --to 2026-09-15 --force
    python cvhp_scrape.py --no-fetch            # chỉ rebuild calls/summary từ events (hoặc từ raw cache nếu events trống)
"""
import argparse, csv, html as H, os, re, sys, time
from collections import defaultdict
from datetime import date, datetime, timedelta

import requests
import lxml.html as LH

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'data'); RAW = os.path.join(ROOT, 'raw')
EVENTS_CSV = os.path.join(DATA, 'cvhp_events.csv')
CALLS_CSV = os.path.join(DATA, 'cvhp_calls.csv')
TERM_DAILY_CSV = os.path.join(DATA, 'cvhp_terminal_daily.csv')
DAILY_CSV = os.path.join(DATA, 'cvhp_daily.csv')
TERMINALS_CSV = os.path.join(ROOT, 'terminals.csv')
URL = 'https://csdltau.cangvuhaiphong.gov.vn/pages/ship_plan.aspx?d={d}'

SECTION_OF = {'TD_ShowShipPlan_Roi': 'Roi', 'TD_ShowShipPlan_DiChuyen': 'DiChuyen',
              'TD_ShowShipPlan_Vao': 'Vao', 'TD_ShowShipPlan_QuaLuong': 'QuaLuong'}
COLS_13 = ['stt', 'time', 'ship', 'draft', 'loa', 'dwt', 'gt', 'tugs', 'channel', 'from', 'to', 'agent', 'pilot']
COLS_10 = ['stt', 'time', 'ship', 'draft', 'loa', 'dwt', 'channel', 'from', 'to', 'pilot']   # Qua luồng: không GT/tàu lai/đại lý
EVENT_FIELDS = ['plan_date', 'section', 'stt', 'time', 'ship', 'ship_key', 'is_sb', 'draft', 'loa', 'dwt', 'gt',
                'tugs', 'channel', 'from', 'to', 'agent', 'pilot', 'fetched_at']
REVISION_DAYS = 3        # 2 lần "Vào" cùng tàu, cùng from/to trong <=3 ngày mà chưa "Rời" -> lịch bị dời, giữ bản sau
MAX_CALL_DAYS = 45       # Vào mà quá 45 ngày không thấy Rời -> coi như thiếu dữ liệu rời, sự kiện sau là chuyến mới
SEC_ORDER = {'Vao': 0, 'DiChuyen': 1, 'Roi': 2}


def log(*a):
    print(datetime.now().strftime('%H:%M:%S'), *a, flush=True)


def vn_num(s):
    """'18.360' -> 18360 ; '8,6' -> 8.6 ; '' -> None"""
    s = (s or '').strip().replace(' ', '')
    if not s: return None
    s = s.replace('.', '').replace(',', '.')
    try:
        v = float(s)
        return int(v) if v.is_integer() else v
    except ValueError:
        return None


def norm_name(s):
    return re.sub(r'\s+', ' ', H.unescape(s or '')).strip().upper()


def strip_accents(s):
    import unicodedata
    s = (s or '').replace('Đ', 'D').replace('đ', 'd')
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def ship_key(name):
    """khoá nhận diện tàu: bỏ dấu tiếng Việt (VIỄN ĐÔNG 68 = VIEN DONG 68), hậu tố (SB)/(VR-SB), ký tự lạ, khoảng trắng thừa"""
    k = re.sub(r'\((VR-)?SB\)|\(SI+\)', '', strip_accents(norm_name(name)))
    return re.sub(r'[^A-Z0-9]+', ' ', k).strip()


# ---------------------------------------------------------------- fetch + parse
def make_session():
    s = requests.Session()
    s.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) cvhp-scraper',
                      'Accept-Language': 'vi,en;q=0.8'})
    return s


def fetch_offset(sess, d, retries=3):
    for i in range(retries):
        try:
            r = sess.get(URL.format(d=d), timeout=90)
            r.raise_for_status()
            r.encoding = 'utf-8'
            return r.text
        except Exception as e:
            log(f'  loi mang d={d} ({e}); thu lai {i + 1}/{retries}'); time.sleep(3 * (i + 1))
    return None


def page_date(html):
    m = re.search(r'ĐIỀU ĐỘNG TÀU NGÀY\s*(\d{2})/(\d{2})/(\d{4})', html)
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def fetch_date(sess, target, local_today):
    """Kéo trang của đúng ngày target. d tính theo ngày máy; nếu ngày server lệch (qua nửa đêm) thì chỉnh lại 1 lần."""
    d = (target - local_today).days
    html = fetch_offset(sess, d)
    if html is None: return None
    got = page_date(html)
    if got is None:
        log(f'  khong doc duoc ngay trong trang d={d}'); return None
    if got != target:
        d2 = d + (target - got).days
        log(f'  server lech ngay: d={d} -> {got}, chinh d={d2}')
        html = fetch_offset(sess, d2)
        if html is None or page_date(html) != target:
            log(f'  van khong khop ngay {target}, bo qua'); return None
    return html


def parse_page(html, plan_date, fetched_at):
    """HTML lỗi thẻ (</td> thừa sau cột Đại lý) nhưng lxml xử lý ổn. Trả về list dict sự kiện."""
    doc = LH.fromstring(html)
    out = []
    for tbl in doc.xpath("//table[@class='cssTD']"):
        sec = SECTION_OF.get(tbl.getparent().get('id'))
        if not sec: continue
        for tr in tbl.xpath('./tr')[1:]:
            cells = [re.sub(r'\s+', ' ', td.text_content()).strip() for td in tr.xpath('./td')]
            if len(cells) == 13: cols = COLS_13
            elif len(cells) == 10: cols = COLS_10
            else:
                log(f'  {plan_date} {sec}: dong {len(cells)} cot la, bo qua: {cells[:3]}'); continue
            rec = dict(zip(cols, cells))
            name = norm_name(rec['ship'])
            out.append({
                'plan_date': plan_date.isoformat(), 'section': sec, 'stt': vn_num(rec['stt']),
                'time': rec['time'], 'ship': name, 'ship_key': ship_key(name),
                'is_sb': 1 if re.search(r'\((VR-)?SB\)', name) else 0,
                'draft': vn_num(rec['draft']), 'loa': vn_num(rec['loa']), 'dwt': vn_num(rec['dwt']),
                'gt': vn_num(rec.get('gt')), 'tugs': rec.get('tugs', ''), 'channel': rec['channel'],
                'from': norm_name(rec['from']), 'to': norm_name(rec['to']),
                'agent': rec.get('agent', ''), 'pilot': rec.get('pilot', ''), 'fetched_at': fetched_at,
            })
    return out


# ---------------------------------------------------------------- csv io
def read_csv(path):
    if not os.path.exists(path): return []
    with open(path, encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, fields):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        w.writeheader(); w.writerows(rows)
    os.replace(tmp, path)


def load_terminals():
    return {norm_name(r['terminal']): r for r in read_csv(TERMINALS_CSV)}


def num(v):
    try: return float(v) if v not in ('', None) else 0.0
    except ValueError: return 0.0


# ---------------------------------------------------------------- calls (ghép chuyến tàu)
def ev_dt(e):
    t = e['time'] if re.match(r'^\d{1,2}:\d{2}$', e['time'] or '') else '00:00'
    return datetime.strptime(e['plan_date'] + ' ' + t, '%Y-%m-%d %H:%M')


def new_call(e):
    return {'ship': e['ship'], 'ship_key': e['ship_key'], 'is_sb': e['is_sb'], 'dwt': e['dwt'], 'gt': e['gt'],
            'loa': e['loa'], 'agent': e['agent'], 'arrival': None, 'arr_date': '', 'origin': '', 'first_berth': '',
            'berths': [], 'shifts': [], 'departure': None, 'dep_date': '', 'destination': '',
            'status': 'open', 'n_revisions': 0}


def build_calls(events):
    """Ghép chuỗi Vào -> Di chuyển* -> Rời của cùng ship_key thành 1 chuyến (bỏ bảng Qua luồng).
    status: complete | no_arrival (Rời/Di chuyển mà không thấy Vào trước đó) | no_departure (Vào mà không thấy Rời)
            | shift_only (chỉ có Di chuyển)."""
    by_ship = defaultdict(list)
    for e in events:
        if e['section'] in SEC_ORDER: by_ship[e['ship_key']].append(e)
    calls = []
    for key, evs in by_ship.items():
        evs.sort(key=lambda e: (ev_dt(e), SEC_ORDER[e['section']]))
        seen = set(); uniq = []                     # khử trùng lặp tuyệt đối (phòng khi kéo lại chồng)
        for e in evs:
            k = (e['plan_date'], e['section'], e['time'], e['from'], e['to'])
            if k in seen: continue
            seen.add(k); uniq.append(e)
        cur = None
        for e in uniq:
            sec = e['section']; dt = ev_dt(e)
            expired = cur is not None and cur['arrival'] is not None and (dt - cur['arrival']).days > MAX_CALL_DAYS
            if sec == 'Vao':
                if cur is not None:
                    same = (cur['origin'] == e['from'] and cur['first_berth'] == e['to'] and not cur['shifts'])
                    if same and cur['arrival'] and (dt - cur['arrival']).days <= REVISION_DAYS:
                        cur['arrival'] = dt; cur['arr_date'] = e['plan_date']; cur['n_revisions'] += 1
                        continue                                  # lịch vào bị dời ngày -> giữ bản sau
                    cur['status'] = 'no_departure'; calls.append(cur)
                cur = new_call(e); cur['arrival'] = dt; cur['arr_date'] = e['plan_date']
                cur['origin'] = e['from']; cur['first_berth'] = e['to']; cur['berths'] = [e['to']]
            elif sec == 'DiChuyen':
                if cur is None or expired:
                    if cur is not None: cur['status'] = 'no_departure'; calls.append(cur)
                    cur = new_call(e); cur['status'] = 'no_arrival'; cur['first_berth'] = e['from']; cur['berths'] = [e['from']]
                cur['shifts'].append(f"{e['plan_date']} {e['time']} {e['from']}>{e['to']}")
                if e['to'] not in cur['berths']: cur['berths'].append(e['to'])
            else:  # Roi
                if cur is None or expired:
                    if cur is not None: cur['status'] = 'no_departure'; calls.append(cur)
                    cur = new_call(e); cur['status'] = 'no_arrival'; cur['first_berth'] = e['from']; cur['berths'] = [e['from']]
                elif cur['status'] == 'open':
                    cur['status'] = 'complete'
                if e['from'] not in cur['berths']: cur['berths'].append(e['from'])
                cur['departure'] = dt; cur['dep_date'] = e['plan_date']; cur['destination'] = e['to']
                calls.append(cur); cur = None
        if cur is not None:
            if cur['status'] == 'open': cur['status'] = 'no_departure'
            elif cur['status'] == 'no_arrival': cur['status'] = 'shift_only'
            calls.append(cur)
    rows = []
    for c in calls:
        arr, dep = c['arrival'], c['departure']
        rows.append({
            'call_id': f"{c['ship_key'].replace(' ', '_')}_{c['arr_date'] or c['dep_date'] or (c['shifts'][0][:10] if c['shifts'] else '')}",
            'ship': c['ship'], 'ship_key': c['ship_key'], 'is_sb': c['is_sb'],
            'dwt': c['dwt'], 'gt': c['gt'], 'loa': c['loa'], 'agent': c['agent'],
            'arrival': arr.strftime('%Y-%m-%d %H:%M') if arr else '', 'arr_date': c['arr_date'],
            'origin': c['origin'], 'first_berth': c['first_berth'],
            'berths': '|'.join(c['berths']), 'last_berth': c['berths'][-1] if c['berths'] else '',
            'n_shifts': len(c['shifts']), 'shifts': '|'.join(c['shifts']),
            'departure': dep.strftime('%Y-%m-%d %H:%M') if dep else '', 'dep_date': c['dep_date'],
            'destination': c['destination'],
            'hours_in_port': round((dep - arr).total_seconds() / 3600, 1) if (arr and dep) else '',
            'status': c['status'], 'n_revisions': c['n_revisions'],
        })
    rows.sort(key=lambda r: (r['arrival'] or r['departure'], r['ship']))
    return rows


CALL_FIELDS = ['call_id', 'ship', 'ship_key', 'is_sb', 'dwt', 'gt', 'loa', 'agent', 'arrival', 'arr_date', 'origin',
               'first_berth', 'berths', 'last_berth', 'n_shifts', 'shifts', 'departure', 'dep_date', 'destination',
               'hours_in_port', 'status', 'n_revisions']


# ---------------------------------------------------------------- summaries
def build_terminal_daily(events, terminals):
    agg = defaultdict(lambda: {'n_arrive': 0, 'dwt_arrive': 0.0, 'gt_arrive': 0.0, 'n_shift_in': 0, 'dwt_shift_in': 0.0,
                               'n_depart': 0, 'dwt_depart': 0.0, 'gt_depart': 0.0, 'n_shift_out': 0, 'dwt_shift_out': 0.0})
    for e in events:
        sec = e['section']; dwt = num(e['dwt']); gt = num(e['gt'])
        if sec == 'Vao':
            a = agg[(e['plan_date'], e['to'])]; a['n_arrive'] += 1; a['dwt_arrive'] += dwt; a['gt_arrive'] += gt
        elif sec == 'Roi':
            a = agg[(e['plan_date'], e['from'])]; a['n_depart'] += 1; a['dwt_depart'] += dwt; a['gt_depart'] += gt
        elif sec == 'DiChuyen':
            a = agg[(e['plan_date'], e['to'])]; a['n_shift_in'] += 1; a['dwt_shift_in'] += dwt
            b = agg[(e['plan_date'], e['from'])]; b['n_shift_out'] += 1; b['dwt_shift_out'] += dwt
    rows = []
    for (d, term), a in sorted(agg.items()):
        t = terminals.get(term, {})
        r = {'plan_date': d, 'terminal': term, 'group': t.get('group', ''), 'ticker': t.get('ticker', ''),
             'kind': t.get('kind', '')}
        r.update({k: (round(v) if isinstance(v, float) else v) for k, v in a.items()})
        r['n_berth_in'] = a['n_arrive'] + a['n_shift_in']; r['dwt_berth_in'] = round(a['dwt_arrive'] + a['dwt_shift_in'])
        rows.append(r)
    return rows


TERM_FIELDS = ['plan_date', 'terminal', 'group', 'ticker', 'kind', 'n_arrive', 'dwt_arrive', 'gt_arrive', 'n_shift_in',
               'dwt_shift_in', 'n_berth_in', 'dwt_berth_in', 'n_depart', 'dwt_depart', 'gt_depart', 'n_shift_out',
               'dwt_shift_out']


def build_daily(events):
    agg = defaultdict(lambda: defaultdict(float))
    for e in events:
        a = agg[e['plan_date']]; sec = e['section']
        a[f'n_{sec}'] += 1; a[f'dwt_{sec}'] += num(e['dwt'])
        if sec in ('Vao', 'Roi'): a[f'gt_{sec}'] += num(e['gt'])
        if sec == 'Vao' and str(e['is_sb']) == '1': a['n_Vao_sb'] += 1
    rows = []
    for d in sorted(agg):
        a = agg[d]
        rows.append({'plan_date': d, 'n_vao': int(a['n_Vao']), 'dwt_vao': round(a['dwt_Vao']), 'gt_vao': round(a['gt_Vao']),
                     'n_vao_sb': int(a['n_Vao_sb']), 'n_roi': int(a['n_Roi']), 'dwt_roi': round(a['dwt_Roi']),
                     'gt_roi': round(a['gt_Roi']), 'n_dichuyen': int(a['n_DiChuyen']), 'n_qualuong': int(a['n_QuaLuong']),
                     'dwt_qualuong': round(a['dwt_QuaLuong'])})
    return rows


DAILY_FIELDS = ['plan_date', 'n_vao', 'dwt_vao', 'gt_vao', 'n_vao_sb', 'n_roi', 'dwt_roi', 'gt_roi', 'n_dichuyen',
                'n_qualuong', 'dwt_qualuong']


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--from', dest='dfrom', help='YYYY-MM-DD, mặc định hôm nay-3')
    ap.add_argument('--to', dest='dto', help='YYYY-MM-DD, mặc định ngày mai')
    ap.add_argument('--force', action='store_true', help='kéo lại cả ngày đã có trong events')
    ap.add_argument('--no-fetch', action='store_true', help='không kéo mạng, chỉ rebuild bảng dẫn xuất')
    ap.add_argument('--sleep', type=float, default=0.4, help='giây nghỉ giữa 2 request')
    args = ap.parse_args()

    today = date.today()
    dfrom = date.fromisoformat(args.dfrom) if args.dfrom else today - timedelta(days=3)
    dto = date.fromisoformat(args.dto) if args.dto else today + timedelta(days=1)
    if dto < dfrom: dfrom, dto = dto, dfrom
    os.makedirs(DATA, exist_ok=True); os.makedirs(RAW, exist_ok=True)

    events = read_csv(EVENTS_CSV)
    have = {e['plan_date'] for e in events}
    log(f'events hien co: {len(events)} dong, {len(have)} ngay')

    if not args.no_fetch:
        sess = make_session(); fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M')
        recent_lo = today - timedelta(days=3)
        new_by_date = {}; n_days = (dto - dfrom).days + 1; n_new = 0
        for i in range(n_days):
            d = dfrom + timedelta(days=i); ds = d.isoformat()
            always = recent_lo <= d <= today + timedelta(days=1)         # cửa sổ gần: luôn kéo lại (trang bổ sung dần)
            if ds in have and not (args.force or always): continue
            html = fetch_date(sess, d, today)
            if html is None: continue
            with open(os.path.join(RAW, ds + '.html'), 'w', encoding='utf-8') as f: f.write(html)
            evs = parse_page(html, d, fetched_at)
            new_by_date[ds] = evs; n_new += 1
            log(f'{ds}: {len(evs)} su kien (Vao {sum(1 for e in evs if e["section"] == "Vao")}, '
                f'Roi {sum(1 for e in evs if e["section"] == "Roi")})')
            if n_new % 50 == 0:
                log(f'  ... {i + 1}/{n_days} ngay, ghi tam events')
                write_csv(EVENTS_CSV, [e for e in events if e['plan_date'] not in new_by_date]
                          + [x for v in new_by_date.values() for x in v], EVENT_FIELDS)
            time.sleep(args.sleep)
        if new_by_date:
            events = [e for e in events if e['plan_date'] not in new_by_date]          # thay toàn bộ ngày kéo lại
            for ds in new_by_date: events.extend(new_by_date[ds])
            events.sort(key=lambda e: (e['plan_date'], SEC_ORDER.get(e['section'], 3), num(e['stt'])))
            write_csv(EVENTS_CSV, events, EVENT_FIELDS)
            log(f'DONE events: +{sum(len(v) for v in new_by_date.values())} dong ({len(new_by_date)} ngay) '
                f'-> {len(events)} dong, {EVENTS_CSV}')
        else:
            log('khong co ngay nao can keo')
    elif not events:
        for fn in sorted(os.listdir(RAW)):
            if fn.endswith('.html'):
                with open(os.path.join(RAW, fn), encoding='utf-8') as f:
                    events.extend(parse_page(f.read(), date.fromisoformat(fn[:-5]), 'cache'))
        write_csv(EVENTS_CSV, events, EVENT_FIELDS); log(f'parse lai tu raw: {len(events)} dong')

    for e in events: e['ship_key'] = ship_key(e['ship'])          # tính lại khoá (bỏ dấu) cho dữ liệu cũ
    terminals = load_terminals()
    calls = build_calls(events)
    write_csv(CALLS_CSV, calls, CALL_FIELDS)
    st = defaultdict(int)
    for c in calls: st[c['status']] += 1
    log(f'DONE calls: {len(calls)} chuyen {dict(st)} -> {CALLS_CSV}')
    td = build_terminal_daily(events, terminals); write_csv(TERM_DAILY_CSV, td, TERM_FIELDS)
    unknown = sorted({r['terminal'] for r in td if not r['group']})
    log(f'DONE terminal_daily: {len(td)} dong -> {TERM_DAILY_CSV}; ben chua map trong terminals.csv: {len(unknown)}')
    if unknown: log('  ' + ', '.join(unknown[:40]) + (' ...' if len(unknown) > 40 else ''))
    dl = build_daily(events); write_csv(DAILY_CSV, dl, DAILY_FIELDS)
    log(f'DONE daily: {len(dl)} ngay -> {DAILY_CSV}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
