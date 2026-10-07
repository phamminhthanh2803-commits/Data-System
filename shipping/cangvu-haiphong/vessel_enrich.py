# -*- coding: utf-8 -*-
"""
vessel_enrich.py - Bổ sung thông tin TÀU cho dữ liệu Cảng vụ HP: loại tàu, IMO, chủ tàu, HÃNG KHAI THÁC, TEU, TUYẾN DỊCH VỤ.

3 tầng:
  1. --particulars : tra BalticShipping (API JSON miễn phí, không cần key) theo tên tàu -> IMO, MMSI, loại tàu, năm đóng,
                     chủ tàu/quản lý, cờ. Khớp tên + DWT (±10%). Không có TEU.
  2. luật           : carriers.csv (tiền tố tên tàu / từ khoá chủ tàu / đại lý độc quyền) -> operator (hãng khai thác).
  3. agent          : --todo xuất data/vessel_todo.csv (tàu container còn thiếu TEU/operator/service, ưu tiên hay ghé 12 tháng
                     gần nhất). Agent Claude Code (skill /cvhp-vessels) tra web rồi ghi data/vessel_lookup.csv;
                     --merge nạp lại vào data/vessel_master.csv (ưu tiên lookup > luật > BalticShipping).
  --apply          : ghép vessel_master vào cvhp_calls -> cvhp_calls_enriched.csv + cvhp_monthly_operator.csv
                     + cvhp_monthly_terminal.csv (tháng x bến x loại tàu: lượt cập bến, tổng TEU, tổng DWT).

Chạy:
  python vessel_enrich.py                       # = --particulars --limit 300 rồi --apply (bước hằng ngày)
  python vessel_enrich.py --particulars --limit 2000 --since 2025-01-01
  python vessel_enrich.py --todo --limit 40      # xuất danh sách cho agent tra
  python vessel_enrich.py --merge                # nạp data/vessel_lookup.csv
  python vessel_enrich.py --apply
"""
import argparse, csv, os, re, sys, time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

import requests

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, 'data')
MASTER_CSV = os.path.join(DATA, 'vessel_master.csv')          # 1 master chung cho mọi cảng vụ
TODO_CSV = os.path.join(DATA, 'vessel_todo.csv')
LOOKUP_CSV = os.path.join(DATA, 'vessel_lookup.csv')
CARRIERS_CSV = os.path.join(ROOT, 'carriers.csv')
HCM_ROOT = os.path.join(os.path.dirname(ROOT), 'cangvu-hcm')
# mỗi cảng vụ: events/calls đầu vào, file bến (cột terminal/kind), output enriched + tổng hợp tháng
PORTS = {
    'hp': {'events': os.path.join(DATA, 'cvhp_events.csv'), 'calls': os.path.join(DATA, 'cvhp_calls.csv'),
           'terminals': os.path.join(ROOT, 'terminals.csv'), 'calls_enr': os.path.join(DATA, 'cvhp_calls_enriched.csv'),
           'mon_op': os.path.join(DATA, 'cvhp_monthly_operator.csv'), 'mon_term': os.path.join(DATA, 'cvhp_monthly_terminal.csv')},
    'hcm': {'events': os.path.join(HCM_ROOT, 'data', 'cvhcm_events.csv'), 'calls': os.path.join(HCM_ROOT, 'data', 'cvhcm_calls.csv'),
            'terminals': os.path.join(HCM_ROOT, 'terminals_hcm.csv'), 'calls_enr': os.path.join(HCM_ROOT, 'data', 'cvhcm_calls_enriched.csv'),
            'mon_op': os.path.join(HCM_ROOT, 'data', 'cvhcm_monthly_operator.csv'), 'mon_term': os.path.join(HCM_ROOT, 'data', 'cvhcm_monthly_terminal.csv')},
}

BS_URL = 'https://www.balticshipping.com/'
BS_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128',
              'X-Requested-With': 'XMLHttpRequest', 'Referer': 'https://www.balticshipping.com/vessels'}
# mã loại tàu BalticShipping (suy ra từ mẫu 09/2026): 12 container, 14 hàng tổng hợp, 9 hàng rời, 26 dầu thô,
# 29 dầu sản phẩm, 82 hoá chất/dầu SP, 32 LPG, 83 xe (ro-ro), 46 khác/nhỏ
BS_TYPE = {12: 'container', 14: 'general', 9: 'bulk', 26: 'tanker', 29: 'tanker', 82: 'tanker', 32: 'gas',
           83: 'roro', 46: 'other'}
CONTAINER_TERMINALS = {'HICT', 'HHIT', 'HTIT', 'LACH HUYEN 1', 'LACH HUYEN 2', 'TAN VU', 'CHUA VE', 'DINH VU',
                       'NAM DINH VU', 'NAM HAI DINH VU', 'NAM HAI', 'VIP GREEN PORT', 'GREEN PORT', 'HAI AN',
                       'PTSC DINH VU', 'TAN CANG 189', 'MPC PORT', 'VIMC', 'CANG 128', 'DOAN XA',
                       'CAT LAI', 'TCIT', 'TCTT', 'CMIT', 'SSIT', 'GEMALINK', 'SP-ITC', 'VICT', 'SPCT',
                       'TAN CANG HIEP PHUOC', 'PHU HUU', 'BEN NGHE', 'TCCT', 'PHAO GEMADEPT'}

MASTER_FIELDS = ['ship_key', 'ship', 'imo', 'mmsi', 'bs_type', 'vf_type', 'vessel_class', 'class_src', 'built', 'flag',
                 'gt', 'dwt', 'loa', 'owner', 'manager', 'operator', 'operator_src', 'teu', 'teu_src', 'teu_checked',
                 'service', 'service_src', 'lookup_as_of', 'lookup_note', 'bs_checked', 'calls_total', 'calls_12m',
                 'first_seen', 'last_seen', 'top_berth', 'top_agent', 'top_cargo', 'is_sb']
VF_TYPE = {'container ship': 'container', 'bulk carrier': 'bulk', 'general cargo ship': 'general', 'general cargo': 'general',
           'oil products tanker': 'tanker', 'crude oil tanker': 'tanker', 'chemical/oil products tanker': 'tanker',
           'oil/chemical tanker': 'tanker', 'lpg tanker': 'gas', 'lng tanker': 'gas', 'vehicles carrier': 'roro',
           'ro-ro cargo ship': 'roro', 'ro-ro/passenger ship': 'roro', 'cement carrier': 'bulk', 'heavy load carrier': 'general',
           'deck cargo ship': 'general', 'passenger ship': 'other', 'cargo ship': 'general'}
FLEXPORT_TYPE = {'Container Ship': 'container', 'Bulk Carrier': 'bulk', 'General Cargo Ship': 'general'}
LOOKUP_FIELDS = ['ship_key', 'ship', 'imo', 'operator', 'teu', 'service', 'vessel_class', 'source', 'as_of', 'note']


def log(*a): print(datetime.now().strftime('%H:%M:%S'), *a, flush=True)


def read_csv(p):
    if not os.path.exists(p): return []
    with open(p, encoding='utf-8-sig', newline='') as f: return list(csv.DictReader(f))


def write_csv(p, rows, fields):
    tmp = p + '.tmp'
    with open(tmp, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    os.replace(tmp, p)


def fnum(v):
    try: return float(v) if v not in ('', None) else None
    except ValueError: return None


# ---------------------------------------------------------------- index tàu từ events
def build_index(events):
    """Thống kê theo ship_key: số lượt Vào, DWT/GT/LOA, lần đầu/cuối, bến & đại lý hay gặp."""
    idx = {}
    cutoff = (date.today() - timedelta(days=365)).isoformat()
    for e in events:
        if e['section'] not in ('Vao', 'Roi'): continue
        k = e['ship_key']
        if not k: continue
        d = idx.setdefault(k, {'ship': e['ship'], 'dwt': None, 'gt': None, 'loa': None, 'calls_total': 0, 'calls_12m': 0,
                               'first_seen': e['plan_date'], 'last_seen': e['plan_date'], 'berths': Counter(),
                               'agents': Counter(), 'is_sb': e['is_sb'], 'cargo': Counter()})
        to = e.get('terminal_to') or e['to']; frm = e.get('terminal_from') or e['from']     # HCM: bến đã map thay mã cầu
        if e['section'] == 'Vao':
            d['calls_total'] += 1
            if e['plan_date'] >= cutoff: d['calls_12m'] += 1
            d['berths'][to] += 1
        else:
            d['berths'][frm] += 1
        if e.get('cargo_type'): d['cargo'][e['cargo_type']] += 1
        if e['agent']: d['agents'][e['agent']] += 1
        for f in ('dwt', 'gt', 'loa'):
            v = fnum(e[f])
            if v and (d[f] is None or v > d[f]): d[f] = v
        d['first_seen'] = min(d['first_seen'], e['plan_date']); d['last_seen'] = max(d['last_seen'], e['plan_date'])
        if e['plan_date'] >= d['last_seen']: d['ship'] = e['ship']
    return idx


def load_master():
    return {r['ship_key']: r for r in read_csv(MASTER_CSV)}


def sync_master(master, idx):
    """Thêm tàu mới / cập nhật thống kê từ events vào master."""
    for k, d in idx.items():
        m = master.setdefault(k, {f: '' for f in MASTER_FIELDS})
        m['ship_key'] = k; m['ship'] = d['ship']; m['is_sb'] = d['is_sb']
        m['calls_total'] = d['calls_total']; m['calls_12m'] = d['calls_12m']
        m['first_seen'] = d['first_seen']; m['last_seen'] = d['last_seen']
        m['top_berth'] = d['berths'].most_common(1)[0][0] if d['berths'] else ''
        m['top_agent'] = d['agents'].most_common(1)[0][0] if d['agents'] else ''
        m['top_cargo'] = d['cargo'].most_common(1)[0][0] if d['cargo'] else ''
        for f in ('dwt', 'gt', 'loa'):
            if d[f] and not m.get(f): m[f] = int(d[f]) if float(d[f]).is_integer() else d[f]
    return master


# ---------------------------------------------------------------- 1. BalticShipping
def bs_search(sess, name):
    data = {'request[0][module]': 'ships', 'request[0][action]': 'list', 'request[0][id]': '0',
            'request[0][data][0][name]': 'search_id', 'request[0][data][0][value]': '0',
            'request[0][data][1][name]': 'name', 'request[0][data][1][value]': name,
            'request[0][data][2][name]': 'imo', 'request[0][data][2][value]': '',
            'request[0][data][3][name]': 'page', 'request[0][data][3][value]': '0'}
    r = sess.post(BS_URL, data=data, headers=BS_HEADERS, timeout=40)
    r.raise_for_status()
    return [s['data'] for s in r.json()['data']['request'][0].get('ships', []) if s.get('data')]


def bs_match(cands, name, dwt, gt):
    """Chọn bản ghi khớp: tên đúng + DWT/GT trong ±10%; nếu chỉ 1 kết quả đúng tên và không có DWT để so -> chấp nhận."""
    name_u = name.upper().strip()
    exact = [c for c in cands if (c.get('name') or '').upper().strip() == name_u]
    def close(a, b): return a and b and abs(float(a) - float(b)) / max(float(b), 1) <= 0.10
    for c in exact:
        if close(c.get('dwt'), dwt) or close(c.get('gt'), gt): return c, 'name+size'
    if len(exact) == 1 and not (dwt or gt): return exact[0], 'name_only'
    if len(exact) == 1 and not (exact[0].get('dwt') or exact[0].get('gt')): return exact[0], 'name_only'
    return None, 'no_match' if exact else 'not_found'


VF_HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/128 Safari/537.36',
              'Accept-Language': 'en'}


def vf_search(sess, name):
    """VesselFinder tìm theo tên (HTML tĩnh): [{imo, mmsi, name, type, built, gt, dwt}] - dự phòng cho tàu BalticShipping chưa có."""
    import lxml.html as LH
    r = sess.get('https://www.vesselfinder.com/vessels', params={'name': name}, headers=VF_HEADERS, timeout=40)
    r.raise_for_status()
    out = []
    for tr in LH.fromstring(r.text).xpath('//table//tr[td]'):
        href = tr.xpath('.//a[contains(@href,"/vessels/details/")]/@href')
        if not href: continue
        tds = [re.sub(r'\s+', ' ', td.text_content()).strip() for td in tr.xpath('./td')]
        photo = ' '.join(tr.xpath('.//img/@data-src'))
        mm = re.search(r'/ship-photo/\d+-(\d{9})-', photo)
        nm = tr.xpath('.//div[@class="slna"]/text()'); ty = tr.xpath('.//div[@class="slty"]/text()')
        out.append({'imo': href[0].rsplit('/', 1)[-1], 'mmsi': mm.group(1) if mm else '',
                    'name': (nm[0] if nm else '').strip(), 'type': (ty[0] if ty else '').strip(),
                    'built': tds[1] if len(tds) > 1 else '', 'gt': fnum(tds[2]) if len(tds) > 2 else None,
                    'dwt': fnum(tds[3]) if len(tds) > 3 else None})
    return out


def run_particulars(master, limit, since, min_dwt, sleep):
    sess = requests.Session()
    today = date.today().isoformat(); recheck = (date.today() - timedelta(days=180)).isoformat()
    todo = [m for m in master.values()
            if (not m.get('bs_checked') or (not m.get('imo') and m['bs_checked'] < recheck))
            and m.get('last_seen', '') >= since and (fnum(m.get('dwt')) or 0) >= min_dwt and str(m.get('is_sb')) != '1']
    todo.sort(key=lambda m: (-int(m.get('calls_12m') or 0), -int(m.get('calls_total') or 0)))
    log(f'BalticShipping/VesselFinder: {len(todo)} tau can tra IMO (gioi han {limit})')
    n_ok = n_vf = 0
    for i, m in enumerate(todo[:limit]):
        try:
            cands = bs_search(sess, m['ship'])
        except Exception as e:
            log(f'  loi {m["ship"]}: {e}'); time.sleep(5); continue
        c, how = bs_match(cands, m['ship'], fnum(m.get('dwt')), fnum(m.get('gt')))
        m['bs_checked'] = today
        if c:
            m['imo'] = c.get('imo') or ''; m['mmsi'] = c.get('mmsi') or ''; m['bs_type'] = c.get('type') or ''
            yb = c.get('year_build')
            m['built'] = datetime.fromtimestamp(int(yb), timezone.utc).year if yb and str(yb).lstrip('-').isdigit() and int(yb) > 0 else (yb or '')
            m['owner'] = c.get('owner_name') or ''; m['manager'] = c.get('manager_name') or ''
            m['flag'] = c.get('flag_id') or ''
            if not m.get('gt') and c.get('gt'): m['gt'] = c['gt']
            if not m.get('dwt') and c.get('dwt'): m['dwt'] = c['dwt']
            m['lookup_note'] = f'bs:{how}'; n_ok += 1
        else:
            m['lookup_note'] = f'bs:{how}'
            try:                                                        # dự phòng VesselFinder (tàu mới 2022+ BalticShipping chưa có)
                time.sleep(sleep)
                v, how2 = bs_match(vf_search(sess, m['ship']), m['ship'], fnum(m.get('dwt')), fnum(m.get('gt')))
                if v:
                    m['imo'] = v['imo']; m['mmsi'] = v['mmsi'] or m.get('mmsi', ''); m['vf_type'] = v['type']
                    if v['built'] and not m.get('built'): m['built'] = v['built']
                    if not m.get('gt') and v['gt']: m['gt'] = v['gt']
                    m['lookup_note'] += f' vf:{how2}'; n_vf += 1
                else:
                    m['lookup_note'] += f' vf:{how2}'
            except Exception as e:
                log(f'  loi VF {m["ship"]}: {e}')
        if (i + 1) % 25 == 0:
            write_csv(MASTER_CSV, sorted(master.values(), key=lambda r: r['ship_key']), MASTER_FIELDS)
            log(f'  ... {i + 1}/{min(limit, len(todo))} (khop BS {n_ok}, VF {n_vf})')
        time.sleep(sleep)
    log(f'DONE particulars: tra {min(limit, len(todo))}, khop BalticShipping {n_ok}, VesselFinder {n_vf}')


# ---------------------------------------------------------------- 1b. TEU từ Flexport Atlas (JSON-LD, chỉ tàu container)
def flexport_props(sess, imo, mmsi=''):
    import json
    url = f'https://atlas.flexport.com/vessel/imo:{imo}' + (f'/mmsi:{mmsi}' if mmsi else '')
    r = sess.get(url, headers=VF_HEADERS, timeout=60)
    r.raise_for_status()
    props = {}
    for x in re.findall(r'<script type="application/ld\+json">(.*?)</script>', r.text, re.S):
        try:
            j = json.loads(x)
        except ValueError:
            continue
        for p in (j.get('additionalProperty') or []): props[p.get('name')] = p.get('value')
        if j.get('name') and 'additionalProperty' in j: props['_name'] = j['name']
    return props


def run_teu(master, limit, since, sleep):
    sess = requests.Session()
    today = date.today().isoformat()
    todo = [m for m in master.values()
            if m.get('imo') and not m.get('teu') and not m.get('teu_checked')
            and m.get('vessel_class') in ('container', 'container?', 'unknown', 'general', '')
            and m.get('last_seen', '') >= since]
    todo.sort(key=lambda m: (-int(m.get('calls_12m') or 0), -int(m.get('calls_total') or 0)))
    log(f'Flexport TEU: {len(todo)} tau co IMO can tra (gioi han {limit})')
    n_ok = n_none = 0
    for i, m in enumerate(todo[:limit]):
        try:
            p = flexport_props(sess, m['imo'], m.get('mmsi', ''))
            if not p and m.get('mmsi'): p = flexport_props(sess, m['imo'])
        except Exception as e:
            log(f'  loi Flexport {m["ship"]}: {e}'); time.sleep(5); continue
        m['teu_checked'] = today
        if p.get('TEU Capacity'):
            m['teu'] = int(p['TEU Capacity']); m['teu_src'] = 'flexport'; n_ok += 1
        if p.get('Ship Type'):
            m['vf_type'] = m.get('vf_type') or p['Ship Type']
            if p['Ship Type'] in FLEXPORT_TYPE and m.get('class_src') != 'lookup':
                m['vessel_class'] = FLEXPORT_TYPE[p['Ship Type']]; m['class_src'] = 'flexport'
        if p.get('Year Built') and not m.get('built'): m['built'] = p['Year Built']
        if p.get('Length Overall') and not m.get('loa'): m['loa'] = p['Length Overall']
        if not p: n_none += 1; m['teu_src'] = 'flexport:none'
        if (i + 1) % 25 == 0:
            write_csv(MASTER_CSV, sorted(master.values(), key=lambda r: r['ship_key']), MASTER_FIELDS)
            log(f'  ... {i + 1}/{min(limit, len(todo))} (co TEU {n_ok}, khong co trang {n_none})')
        time.sleep(sleep)
    log(f'DONE teu: tra {min(limit, len(todo))}, co TEU {n_ok}, Flexport khong co {n_none}')


# ---------------------------------------------------------------- 2. phân loại + hãng theo luật
def load_carriers():
    rules = {'name': [], 'owner': [], 'agent': []}
    for r in read_csv(CARRIERS_CSV):
        rules[r['kind']].append((re.compile(r['pattern'], re.I), r['operator']))
    return rules


def classify(m, rules):
    # loại tàu: lookup > flexport > balticshipping > vesselfinder > suy đoán
    if m.get('class_src') in ('lookup', 'flexport') and m.get('vessel_class'): pass
    else:
        t = m.get('bs_type'); vt = (m.get('vf_type') or '').lower()
        if t and int(float(t)) in BS_TYPE:
            m['vessel_class'] = BS_TYPE[int(float(t))]; m['class_src'] = 'balticshipping'
        elif vt in VF_TYPE:
            m['vessel_class'] = VF_TYPE[vt]; m['class_src'] = 'vesselfinder'
        elif vt and 'tanker' in vt:
            m['vessel_class'] = 'tanker'; m['class_src'] = 'vesselfinder'
        else:
            name = m.get('ship', ''); cargo = (m.get('top_cargo') or '').upper()
            if cargo.startswith('CONTAINER'): m['vessel_class'], m['class_src'] = 'container', 'cargo'   # loại hàng HCM
            elif re.search(r'\bGAS\b|LPG', name): m['vessel_class'], m['class_src'] = 'gas', 'name'
            elif m.get('top_berth') in CONTAINER_TERMINALS and (fnum(m.get('dwt')) or 0) >= 5000:
                m['vessel_class'], m['class_src'] = 'container?', 'berth'
            elif str(m.get('is_sb')) == '1': m['vessel_class'], m['class_src'] = 'sb', 'name'
            else: m['vessel_class'], m['class_src'] = m.get('vessel_class') or 'unknown', m.get('class_src') or ''
    # hãng khai thác (chỉ tàu container / chưa rõ / hàng tổng hợp; tàu dầu, gas, rời không gán hãng container)
    if m.get('operator_src') == 'lookup' and m.get('operator'): return
    if m.get('vessel_class') in ('tanker', 'gas', 'bulk', 'roro', 'sb', 'other'):
        m['operator'] = ''; m['operator_src'] = ''; return
    for kind, field in (('name', 'ship'), ('owner', 'owner'), ('owner', 'manager'), ('agent', 'top_agent')):
        v = m.get(field) or ''
        for rx, op in rules[kind]:
            if rx.search(v):
                m['operator'] = op; m['operator_src'] = f'rule:{kind}'; return
    if not m.get('operator_src', '').startswith('lookup'):
        m['operator'] = m.get('operator') if m.get('operator_src') == 'lookup' else ''
        m['operator_src'] = ''


# ---------------------------------------------------------------- 3. agent todo / merge
def write_todo(master, limit, classes):
    rows = [m for m in master.values()
            if m.get('vessel_class') in classes
            and (not m.get('teu') or not m.get('operator') or not m.get('service'))
            and (not m.get('lookup_as_of') or m['lookup_as_of'] < (date.today() - timedelta(days=365)).isoformat())]
    rows.sort(key=lambda m: (-int(m.get('calls_12m') or 0), -int(m.get('calls_total') or 0)))
    out = []
    for m in rows[:limit]:
        out.append({'ship_key': m['ship_key'], 'ship': m['ship'], 'imo': m.get('imo', ''), 'dwt': m.get('dwt', ''),
                    'gt': m.get('gt', ''), 'loa': m.get('loa', ''), 'built': m.get('built', ''), 'owner': m.get('owner', ''),
                    'top_agent': m.get('top_agent', ''), 'top_berth': m.get('top_berth', ''),
                    'calls_12m': m.get('calls_12m', ''), 'operator_now': m.get('operator', ''),
                    'missing': '|'.join(f for f in ('operator', 'teu', 'service') if not m.get(f))})
    write_csv(TODO_CSV, out, ['ship_key', 'ship', 'imo', 'dwt', 'gt', 'loa', 'built', 'owner', 'top_agent', 'top_berth',
                              'calls_12m', 'operator_now', 'missing'])
    log(f'DONE todo: {len(out)}/{len(rows)} tau can agent tra -> {TODO_CSV}')


def merge_lookup(master, path):
    rows = read_csv(path); n = 0
    for r in rows:
        k = r.get('ship_key') or ''
        m = master.get(k)
        if not m:
            log(f'  bo qua (khong co trong master): {k}'); continue
        if r.get('operator'): m['operator'] = r['operator']; m['operator_src'] = 'lookup'
        if r.get('teu'): m['teu'] = re.sub(r'[^\d]', '', str(r['teu']))
        if r.get('service'): m['service'] = r['service']; m['service_src'] = 'lookup'
        if r.get('vessel_class'): m['vessel_class'] = r['vessel_class']; m['class_src'] = 'lookup'
        if r.get('imo') and not m.get('imo'): m['imo'] = r['imo']
        m['lookup_as_of'] = r.get('as_of') or date.today().isoformat()
        m['lookup_note'] = (r.get('source') or '') + ((' | ' + r['note']) if r.get('note') else '')
        n += 1
    log(f'DONE merge: {n}/{len(rows)} dong tu {path}')


# ---------------------------------------------------------------- 4. apply vào calls + tổng hợp tháng
def apply_to_calls(master, port):
    P = PORTS[port]
    CALLS_CSV, CALLS_ENR_CSV, MON_OP_CSV, MON_TERM_CSV = P['calls'], P['calls_enr'], P['mon_op'], P['mon_term']
    calls = read_csv(CALLS_CSV)
    if not calls: log(f'[{port}] chua co calls'); return
    terms = {r['terminal']: r for r in read_csv(P['terminals'])}
    out = []
    for c in calls:
        m = master.get(c['ship_key'], {})
        c2 = dict(c)
        c2.update({'imo': m.get('imo', ''), 'vessel_class': m.get('vessel_class', ''), 'operator': m.get('operator', ''),
                   'teu': m.get('teu', ''), 'service': m.get('service', ''), 'built': m.get('built', '')})
        out.append(c2)
    fields = list(calls[0].keys()) + ['imo', 'vessel_class', 'operator', 'teu', 'service', 'built'] if calls else []
    write_csv(CALLS_ENR_CSV, out, fields)
    # tháng x hãng (chỉ chuyến có Vào)
    op = defaultdict(lambda: {'calls': 0, 'teu_sum': 0, 'dwt_sum': 0, 'teu_known': 0})
    tm = defaultdict(lambda: {'berth_visits': 0, 'teu_sum': 0, 'dwt_sum': 0, 'teu_known': 0})
    for c in out:
        if not c['arr_date']: continue
        mon = c['arr_date'][:7]; teu = fnum(c['teu']) or 0; dwt = fnum(c['dwt']) or 0
        a = op[(mon, c['operator'] or '(chua ro)', c['vessel_class'])]
        a['calls'] += 1; a['teu_sum'] += teu; a['dwt_sum'] += dwt; a['teu_known'] += 1 if teu else 0
        for b in c['berths'].split('|'):
            if not b or terms.get(b, {}).get('kind') == 'anchorage': continue
            t = tm[(mon, b, c['vessel_class'])]
            t['berth_visits'] += 1; t['teu_sum'] += teu; t['dwt_sum'] += dwt; t['teu_known'] += 1 if teu else 0
    rows = [{'month': k[0], 'operator': k[1], 'vessel_class': k[2], **{x: round(y) for x, y in v.items()}} for k, v in sorted(op.items())]
    write_csv(MON_OP_CSV, rows, ['month', 'operator', 'vessel_class', 'calls', 'teu_known', 'teu_sum', 'dwt_sum'])
    rows = [{'month': k[0], 'terminal': k[1], 'group': terms.get(k[1], {}).get('group', ''),
             'ticker': terms.get(k[1], {}).get('ticker', ''), 'vessel_class': k[2], **{x: round(y) for x, y in v.items()}}
            for k, v in sorted(tm.items())]
    write_csv(MON_TERM_CSV, rows, ['month', 'terminal', 'group', 'ticker', 'vessel_class', 'berth_visits', 'teu_known',
                                   'teu_sum', 'dwt_sum'])
    n_cont = sum(1 for c in out if c['vessel_class'].startswith('container'))
    n_teu = sum(1 for c in out if c['vessel_class'].startswith('container') and c['teu'])
    n_op = sum(1 for c in out if c['vessel_class'].startswith('container') and c['operator'])
    log(f'DONE apply [{port}]: {len(out)} chuyen; container {n_cont} (co TEU {n_teu}, co hang {n_op}) -> {CALLS_ENR_CSV}, {MON_OP_CSV}, {MON_TERM_CSV}')


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--particulars', action='store_true', help='tra IMO/loại/chủ tàu (BalticShipping, dự phòng VesselFinder)')
    ap.add_argument('--teu', action='store_true', help='tra TEU theo IMO (Flexport Atlas)')
    ap.add_argument('--todo', action='store_true'); ap.add_argument('--merge', nargs='?', const=LOOKUP_CSV)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--limit', type=int, default=300); ap.add_argument('--since', default='2019-01-01', help='chỉ tra tàu còn ghé từ ngày này')
    ap.add_argument('--min-dwt', type=float, default=3000); ap.add_argument('--sleep', type=float, default=0.8)
    ap.add_argument('--classes', default='container,container?', help='lớp tàu đưa vào todo')
    ap.add_argument('--port', default='all', help='hp | hcm | all: cảng vụ để đọc events và ghi bảng enriched')
    a = ap.parse_args()
    if not (a.particulars or a.teu or a.todo or a.merge or a.apply): a.particulars = a.teu = a.apply = True
    ports = list(PORTS) if a.port == 'all' else [a.port]

    events = []
    for p in ports:
        ev = read_csv(PORTS[p]['events']); log(f'[{p}] events: {len(ev)} dong'); events.extend(ev)
    nat = os.path.join(os.path.dirname(ROOT), 'cangvu-toanquoc', 'data')
    if a.port == 'all' and os.path.isdir(nat):                       # các cảng vụ khác (bộ toàn quốc); HPH trùng HP nên bỏ
        for code in sorted(os.listdir(nat)):
            f = os.path.join(nat, code, 'events.csv')
            if code not in ('HPH', 'QNH') and os.path.exists(f):
                ev = [e for e in read_csv(f) if e.get('plan_date', '') >= '2023-01-01']
                for e in ev: e.setdefault('gt', ''); e.setdefault('agent', '')
                log(f'[{code}] events tu 2023: {len(ev)} dong'); events.extend(ev)
    master = sync_master(load_master(), build_index(events))
    imo_map = {r['ship_key']: r for r in read_csv(os.path.join(nat, 'imo_map.csv'))}
    n_imo = 0
    for k, m in master.items():                                      # IMO chính thức từ hệ thống cảng vụ (public-kh)
        r = imo_map.get(k)
        if r and not m.get('imo'):
            m['imo'] = r['imo']; m['lookup_note'] = (m.get('lookup_note') or '') + ' imo:public-kh'; n_imo += 1
            if not m.get('gt') and r.get('gt'): m['gt'] = r['gt']
    if n_imo: log(f'dien IMO tu public-kh: {n_imo} tau')
    rules = load_carriers()
    log(f'master: {len(master)} tau ({sum(1 for m in master.values() if m.get("imo"))} co IMO, '
        f'{sum(1 for m in master.values() if m.get("teu"))} co TEU)')
    if a.particulars: run_particulars(master, a.limit, a.since, a.min_dwt, a.sleep)
    for m in master.values(): classify(m, rules)
    if a.teu: run_teu(master, a.limit, a.since, a.sleep)
    for m in master.values(): classify(m, rules)
    if a.merge: merge_lookup(master, a.merge)
    write_csv(MASTER_CSV, sorted(master.values(), key=lambda r: r['ship_key']), MASTER_FIELDS)
    cls = Counter(m['vessel_class'] for m in master.values())
    log(f'DONE master: {len(master)} tau -> {MASTER_CSV}; lop: {dict(cls.most_common())}')
    if a.todo: write_todo(master, a.limit, set(a.classes.split(',')))
    if a.apply:
        for p in ports: apply_to_calls(master, p)
    return 0


if __name__ == '__main__':
    sys.exit(main())
