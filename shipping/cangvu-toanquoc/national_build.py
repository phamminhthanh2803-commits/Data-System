# -*- coding: utf-8 -*-
"""
national_build.py - Gộp chuyến tàu của MỌI cảng vụ đã có dữ liệu thành bộ toàn quốc (chỉ đọc nguồn, ghi vào data/).
Nguồn:  HP  = D:/shipping/cangvu-haiphong/data/cvhp_calls.csv         (csdltau, từ 2019)
        HCM = D:/shipping/cangvu-hcm/data/cvhcm_calls.csv             (gồm Cái Mép - Vũng Tàu từ 08/2025)
        pkh = data/<CODE>/calls.csv   (QNH, TBH, THA, HTH, DNG, BTN, DNI, KGG; HPH chỉ dùng lấy IMO)
        aspx= data/<CODE>/calls.csv   (QNK, NTG, CTO)
Quảng Ninh: public-kh (QNH) dừng đầu 2025, kht1 (QNK) có từ 2025 -> nối 2 nguồn tại ngày đầu tiên QNK có dữ liệu, gộp thành mã QN.
Output (data/):
    national_calls.csv      1 dòng = 1 chuyến, cột chung + auth, auth_name, source
    national_terminals.csv  auth, terminal, group, ticker, kind
    national_monthly.csv    tháng x cảng vụ: số chuyến, số tàu, tổng DWT, tổng GT, số chuyến tàu >= 5.000 DWT
    coverage.csv            mỗi cảng vụ: nguồn, khoảng ngày, số chuyến, tỷ lệ có IMO / cảng trước-cảng kế
Chạy:  python national_build.py
"""
import csv, os, sys
from collections import Counter, defaultdict
from datetime import datetime

ROOT = os.path.dirname(os.path.abspath(__file__)); HUB = os.path.dirname(ROOT); DATA = os.path.join(ROOT, 'data')
sys.path.insert(0, os.path.join(HUB, 'cangvu-haiphong'))
from cvhp_scrape import read_csv, write_csv, ship_key   # noqa: E402

FIELDS = ['auth', 'auth_name', 'source', 'call_id', 'ship', 'ship_key', 'imo', 'is_sb', 'dwt', 'gt', 'loa', 'agent', 'arrival', 'arr_date',
          'origin', 'first_berth', 'berths', 'last_berth', 'n_shifts', 'shifts', 'departure', 'dep_date', 'destination', 'hours_in_port',
          'status', 'n_revisions', 'cargo']
NAMES = {'HP': 'Hải Phòng', 'HCM': 'TP.HCM – Cái Mép', 'QN': 'Quảng Ninh', 'TBH': 'Thái Bình', 'THA': 'Thanh Hoá', 'HTH': 'Hà Tĩnh',
         'DNG': 'Đà Nẵng – Quảng Nam', 'NTG': 'Nha Trang', 'BTN': 'Bình Thuận', 'DNI': 'Đồng Nai', 'CTO': 'Cần Thơ', 'KGG': 'Kiên Giang'}
ORDER = ['QN', 'HP', 'TBH', 'THA', 'HTH', 'DNG', 'NTG', 'BTN', 'DNI', 'HCM', 'CTO', 'KGG']       # bắc -> nam


def log(*a): print(datetime.now().strftime('%H:%M:%S'), *a, flush=True)


def valid_imo(x):
    """IMO 7 chữ số đúng số kiểm tra (loại số đăng ký nội địa, id tạm)"""
    x = (x or '').strip()
    if len(x) != 7 or not x.isdigit(): return ''
    return x if sum(int(x[i]) * (7 - i) for i in range(6)) % 10 == int(x[6]) else ''


MAXDAY = ''


def load(auth, source, path, tpath, lo='', hi='9999'):
    global MAXDAY
    if not MAXDAY:
        from datetime import date, timedelta
        MAXDAY = (date.today() + timedelta(days=3)).isoformat()
    rows = read_csv(path); out = []
    for c in rows:
        d = c.get('arr_date') or c.get('dep_date') or (c.get('shifts', '')[:10])
        if not d or not (lo <= d < hi) or not ('2015-01-01' <= d <= MAXDAY): continue
        r = {k: c.get(k, '') for k in FIELDS}
        r.update({'auth': auth, 'auth_name': NAMES[auth], 'source': source, 'ship_key': ship_key(c.get('ship', '')), 'imo': valid_imo(c.get('imo'))})
        out.append(r)
    terms = [{'auth': auth, 'terminal': t['terminal'].upper().strip(), 'group': t.get('group', ''), 'ticker': t.get('ticker', ''),
              'kind': t.get('kind', '')} for t in read_csv(tpath)]
    return out, terms


def main():
    calls, terms = [], []
    def add(auth, source, path, tpath, **kw):
        c, t = load(auth, source, path, tpath, **kw); calls.extend(c); terms.extend(t)
        log(f'{auth:4s} {source:22s} {len(c):7d} chuyen')
    add('HP', 'csdltau', os.path.join(HUB, 'cangvu-haiphong', 'data', 'cvhp_calls.csv'), os.path.join(HUB, 'cangvu-haiphong', 'terminals.csv'))
    add('HCM', 'aspx shipschedule', os.path.join(HUB, 'cangvu-hcm', 'data', 'cvhcm_calls.csv'), os.path.join(HUB, 'cangvu-hcm', 'terminals_hcm.csv'))
    qnk = read_csv(os.path.join(DATA, 'QNK', 'calls.csv'))
    cut = '2025-04-14' if qnk else '9999'          # Quảng Ninh chuyển dần sang kht1 trong 04/2025 (cùng mốc với app)
    add('QN', 'public-kh (den ' + cut + ')', os.path.join(DATA, 'QNH', 'calls.csv'), os.path.join(DATA, 'QNH', 'terminals.csv'), hi=cut)
    add('QN', 'kht1', os.path.join(DATA, 'QNK', 'calls.csv'), os.path.join(DATA, 'QNK', 'terminals.csv'), lo=cut)
    for code in ('TBH', 'THA', 'HTH', 'DNG', 'BTN', 'DNI', 'KGG'):
        add(code, 'public-kh', os.path.join(DATA, code, 'calls.csv'), os.path.join(DATA, code, 'terminals.csv'))
    for code in ('NTG', 'CTO'):
        add(code, 'aspx', os.path.join(DATA, code, 'calls.csv'), os.path.join(DATA, code, 'terminals.csv'))

    # IMO: điền từ imo_map cho chuyến của nguồn không có IMO (HP, HCM, aspx)
    imo = {r['ship_key']: valid_imo(r['imo']) for r in read_csv(os.path.join(DATA, 'imo_map.csv')) if valid_imo(r['imo'])}
    for c in calls:
        if not c['imo'] and c['ship_key'] in imo: c['imo'] = imo[c['ship_key']]
    # DWT gõ nhầm ở nguồn (> 450.000, hoặc > 4 x GT, hoặc > 0,03 x LOA^3 khi không có GT) -> thay bằng trung vị DWT hợp lý của chính tàu đó
    def f(x):
        try: return float(x)
        except (TypeError, ValueError): return 0.0
    def bad(c):
        d, g, l = f(c['dwt']), f(c['gt']), f(c['loa'])
        return d > 450000 or (g > 50 and d > 4 * g + 500) or (g <= 50 and 15 <= l <= 460 and d > 0.03 * l ** 3)
    good = defaultdict(list)
    for c in calls:
        if f(c['dwt']) > 0 and not bad(c): good[c['ship_key']].append(f(c['dwt']))
    n_fix = 0
    for c in calls:
        if f(c['dwt']) > 0 and bad(c):
            v = sorted(good.get(c['ship_key'], [])); c['dwt'] = v[len(v) // 2] if v else ''; n_fix += 1
    log(f'sua DWT go nham: {n_fix} chuyen')
    calls.sort(key=lambda r: (r['arrival'] or r['departure'] or '', r['auth'], r['ship']))
    write_csv(os.path.join(DATA, 'national_calls.csv'), calls, FIELDS)
    seen = set(); tt = []
    for t in terms:
        k = (t['auth'], t['terminal'])
        if t['terminal'] and k not in seen: seen.add(k); tt.append(t)
    write_csv(os.path.join(DATA, 'national_terminals.csv'), tt, ['auth', 'terminal', 'group', 'ticker', 'kind'])

    mon = defaultdict(lambda: {'calls': 0, 'ships': set(), 'dwt_sum': 0.0, 'gt_sum': 0.0, 'calls_5000dwt': 0})
    cov = defaultdict(lambda: {'n': 0, 'imo': 0, 'ports': 0, 'first': '9999', 'last': '', 'src': Counter()})
    for c in calls:
        v = cov[c['auth']]; v['n'] += 1; v['imo'] += bool(c['imo']); v['ports'] += bool(c['origin'] or c['destination']); v['src'][c['source']] += 1
        d = c['arr_date'] or c['dep_date']
        if d: v['first'] = min(v['first'], d); v['last'] = max(v['last'], d)
        if not c['arr_date']: continue
        m = mon[(c['arr_date'][:7], c['auth'])]
        dwt = float(c['dwt'] or 0); m['calls'] += 1; m['ships'].add(c['ship_key']); m['dwt_sum'] += dwt; m['gt_sum'] += float(c['gt'] or 0)
        m['calls_5000dwt'] += dwt >= 5000
    write_csv(os.path.join(DATA, 'national_monthly.csv'),
              [{'month': k[0], 'auth': k[1], 'auth_name': NAMES[k[1]], 'calls': v['calls'], 'ships': len(v['ships']), 'dwt_sum': round(v['dwt_sum']),
                'gt_sum': round(v['gt_sum']), 'calls_5000dwt': v['calls_5000dwt']} for k, v in sorted(mon.items())],
              ['month', 'auth', 'auth_name', 'calls', 'ships', 'dwt_sum', 'gt_sum', 'calls_5000dwt'])
    rows = [{'auth': a, 'auth_name': NAMES[a], 'sources': '; '.join(f'{s} ({n})' for s, n in cov[a]['src'].most_common()), 'first_date': cov[a]['first'],
             'last_date': cov[a]['last'], 'calls': cov[a]['n'], 'pct_imo': round(cov[a]['imo'] / cov[a]['n'], 3) if cov[a]['n'] else 0,
             'pct_origin_dest': round(cov[a]['ports'] / cov[a]['n'], 3) if cov[a]['n'] else 0} for a in ORDER if a in cov]
    write_csv(os.path.join(DATA, 'coverage.csv'), rows, ['auth', 'auth_name', 'sources', 'first_date', 'last_date', 'calls', 'pct_imo', 'pct_origin_dest'])
    log(f'DONE national: {len(calls)} chuyen, {len(cov)} cang vu, {len(tt)} ben -> {DATA}')
    for r in rows: log(f"   {r['auth']:4s} {r['auth_name']:22s} {r['first_date']} -> {r['last_date']}  {r['calls']:7d} chuyen  IMO {r['pct_imo']:.0%}  cang di/den {r['pct_origin_dest']:.0%}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
