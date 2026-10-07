# -*- coding: utf-8 -*-
"""
cvhcm_scrape.py - Kéo KẾ HOẠCH ĐIỀU ĐỘNG TÀU THUYỀN hằng ngày của Cảng vụ Hàng hải TP.HCM
                  (bao gồm cả khu Cái Mép - Thị Vải - Vũng Tàu sau sáp nhập BR-VT vào TP.HCM 07/2025).
    https://cangvuhanghaitphcm.gov.vn/index.aspx?page=shipschedule&cat=3107
    ASP.NET WebForms: chọn ngày bằng POST-back (ctl22$txtDate + ctl22$btnSearch, kèm __VIEWSTATE/__EVENTVALIDATION
    lấy từ trang trước). Lịch sử lùi được tới 2019. 3 bảng: Tàu đến (GridView_TauDen) / Tàu rời (GridView_TauRoi)
    / Tàu di chuyển (GridView_TauDiChuyen). Trang của một ngày bổ sung dần -> luôn kéo lại [hôm nay-3 .. ngày mai].
    (Trang "Vị trí tàu tại cảng" page=shipinport là ảnh chụp tàu ĐANG ở cảng, không có DWT -> không dùng.)

Khác Hải Phòng: không có GT, không có cảng đi/đến ngoài HCM; có thêm Quốc tịch, Hô hiệu, LOẠI HÀNG + khối lượng
(ví dụ "CONTAINER 1883", "LPG 46822", "NIL" = không hàng), tuyến luồng (Sài Gòn - Vũng Tàu / Soài Rạp / Vũng Tàu - Thị Vải...).
Tên tàu có dấu "* " đầu (giữ vào cột mark).

Kết quả data/: cvhcm_events.csv, cvhcm_calls.csv, cvhcm_terminal_daily.csv, cvhcm_daily.csv (cùng cấu trúc cụm HP,
thuật toán ghép chuyến + tổng hợp import từ D:/shipping/cangvu-haiphong/cvhp_scrape.py). raw/YYYY-MM-DD.html cache.
Bến (Vị trí neo đậu) là MÃ CẦU (C.LAI 5, SP-ITC01, CẦU CẢNG SỐ 1 - SSIT, NEO VT...) -> berths.csv map regex -> terminal.

Chạy:
    python cvhcm_scrape.py                      # kéo [hôm nay-3 .. +1], rebuild
    python cvhcm_scrape.py --from 2019-01-01    # backfill (bỏ qua ngày đã có; --force kéo lại)
    python cvhcm_scrape.py --no-fetch           # chỉ rebuild từ events (hoặc raw cache nếu events trống)
"""
import argparse, csv, os, re, sys, time
from collections import defaultdict
from datetime import date, datetime, timedelta

import requests
import lxml.html as LH

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), 'cangvu-haiphong'))
from cvhp_scrape import (build_calls, build_daily, build_terminal_daily, CALL_FIELDS, TERM_FIELDS, DAILY_FIELDS,   # noqa: E402
                         read_csv, write_csv, vn_num, norm_name, ship_key, SEC_ORDER, num, log)

DATA = os.path.join(ROOT, 'data'); RAW = os.path.join(ROOT, 'raw')
EVENTS_CSV = os.path.join(DATA, 'cvhcm_events.csv'); CALLS_CSV = os.path.join(DATA, 'cvhcm_calls.csv')
TERM_DAILY_CSV = os.path.join(DATA, 'cvhcm_terminal_daily.csv'); DAILY_CSV = os.path.join(DATA, 'cvhcm_daily.csv')
BERTHS_CSV = os.path.join(ROOT, 'berths.csv')
URL = 'https://cangvuhanghaitphcm.gov.vn/index.aspx?page=shipschedule&cat=3107'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 cvhcm-scraper', 'Accept-Language': 'vi'}

GRIDS = {'ctl22_GridView_TauDen': 'Vao', 'ctl22_GridView_TauRoi': 'Roi', 'ctl22_GridView_TauDiChuyen': 'DiChuyen'}
COLS = {
    'Vao': ['stt', 'ship', 'flag', 'callsign', 'dwt', 'loa', 'draft', 'cargo', 'to', 'time', 'time2', 'tugs', 'agent', 'channel'],
    'Roi': ['stt', 'ship', 'flag', 'callsign', 'dwt', 'loa', 'draft', 'cargo', 'from', 'time', 'tugs', 'agent', 'channel'],
    'DiChuyen': ['stt', 'ship', 'flag', 'callsign', 'dwt', 'loa', 'draft', 'cargo', 'from', 'to', 'time', 'tugs', 'agent', 'channel'],
}
EVENT_FIELDS = ['plan_date', 'section', 'stt', 'time', 'time2', 'ship', 'ship_key', 'mark', 'is_sb', 'flag', 'callsign', 'draft',
                'loa', 'dwt', 'gt', 'cargo_type', 'cargo_qty', 'tugs', 'channel', 'from', 'to', 'terminal_from', 'terminal_to',
                'agent', 'fetched_at']


# ---------------------------------------------------------------- mã cầu -> khu vực chính thức -> bến
# Chuỗi tra:  mã cầu --(berth_area_map.csv, bảng CHÍNH THỨC từ trang "Vị trí tàu tại cảng")--> khu vực cảng
#             khu vực --(areas.csv, gán tay)--> bến ngắn gọn + chủ bến + mã CK + loại + cụm địa lý (node)
#             chưa có trong areas.csv -> regex berths.csv trên tên khu vực; mã chưa từng thấy -> regex trên mã.
AREA_MAP_CSV = os.path.join(ROOT, 'berth_area_map.csv'); AREAS_CSV = os.path.join(ROOT, 'areas.csv')
TERMINALS_CSV = os.path.join(ROOT, 'terminals_hcm.csv')
KIND_RULES = [
    ('anchorage', r'KHU NEO|NGOAI PHAO|^PHAO \d|KHU VUC PHAO|SỰ CỐ|VÙNG CSB|HOA TIÊU|^NEO'),
    ('offshore', r'^MỎ |^MO |NGOÀI KHƠI|DKNK'),
    ('offshore-base', r'PTSC|VIETSOVPETRO|ĐÔNG XUYÊN|PVC-MS|NASOS|DVDK'),
    ('shipyard', r'ĐÓNG TÀU|BA SON|SHIPYARD|VARD|SỬA TÀU|TÀU THỦY|DÀN KHOAN|Ụ TÀU'),
    ('gas', r'GAS|HYOSUNG'),
    ('petro', r'XĂNG DẦU|XANG DAU|PETRO|PVOIL|PETEC|K2|CALOFIC|VẠN AN|HÀ LỘC|HYDROCARBON|HOA DAU|HÓA DẦU|L\.T\.C|TÀU DẦU'),
    ('cement', r'XI MĂNG|CLINKER|XM|FICO|SCC-VN'),
    ('other', r'NẠO VÉT|BAI DO|BÃI ĐỔ|CẦN GIỜ|QUAN KHU|HẢI ĐOÀN|CÔNG VỤ|CÁP TREO|THI CÔNG|TÀU KHÁCH|CÔN ĐẢO|BẾN ĐẦM|HÀNG GIANG|^KV '),
    ('buoy', r'PHAO|KHU VỰC \d+|HƯNG THÁI|HAI VAN|NHA RONG|LONG THUẬN|BẢO VIỆT PHÁT|HOÀNG HẢI ĐĂNG|HOÀNG MINH|FALCON|SSV|TRƯỜNG AN|HẢI LONG|LONG BEACH'),
]
NODE_RULES = [
    ('MO DAU KHI (ngoai khoi)', r'^MỎ |^MO |NGOÀI KHƠI|DKNK'),
    ('CON DAO', r'CÔN ĐẢO|BẾN ĐẦM|BEN DAM'),
    ('CAN GIO', r'CẦN GIỜ|BÌNH KHÁNH|NẠO VÉT|TIEN GIANG|TIỀN GIANG|MỸ THO'),
    ('LONG SON (VUNG TAU)', r'LONG SƠN|LONG SON'),
    ('CAI MEP', r'CÁI MÉP|CAI MEP|THỊ VẢI|THI VAI|PHÚ MỸ|PHU MY|MỸ XUÂN|MY XUAN|POSCO|INTERFLOUR|SCC-VN|PHƯỚC AN|PHUOC AN|HYOSUNG|VT-TV|VUNG TAU-THI VAI'),
    ('VUNG TAU', r'VŨNG TÀU|VUNG TAU|VTAU|VT|PTSC|VIETSOVPETRO|SAO MAI|ĐÔNG XUYÊN|VARD|PVC-MS|NASOS|HẢI ĐOÀN 129|CLT|CÙ LAO TÀO|K2|GAS ELF|NGOAI PHAO|^PHAO \d|CSB3'),
]


def infer(rules, name, default):
    for val, rx in rules:
        if re.search(rx, name, re.I): return val
    return default


class BerthMap:
    def __init__(self):
        self.code_area = {r['code']: r['area'] for r in read_csv(AREA_MAP_CSV)}
        self.areas = {r['area']: r for r in read_csv(AREAS_CSV)}
        self.rx = [(re.compile(r['pattern'], re.I), r) for r in read_csv(BERTHS_CSV)]
        self.meta = {}                                                  # terminal -> {group, ticker, kind, node, area}

    def _regex(self, name):
        for rx, r in self.rx:
            if rx.search(name): return r
        return None

    def terminal(self, code):
        if not code: return ''
        area = self.code_area.get(code)
        if area:
            r = self.areas.get(area)
            if r: m = {'terminal': r['terminal'], 'group': r['group'], 'ticker': r['ticker'], 'kind': r['kind'], 'node': r['node'], 'area': area}
            else:
                name = re.sub(r'^(BẾN CẢNG|BEN CANG|CẦU CẢNG|CAU CANG) ', '', area)
                m = {'terminal': name, 'group': name.title()[:40], 'ticker': '', 'kind': infer(KIND_RULES, area, 'general'),
                     'node': infer(NODE_RULES, area, 'HO CHI MINH'), 'area': area}
        else:
            r = self._regex(code)
            if r is None: return ''
            m = {'terminal': r['terminal'], 'group': r['group'], 'ticker': r['ticker'], 'kind': r['kind'],
                 'node': infer(NODE_RULES, r['terminal'] + ' ' + code, 'HO CHI MINH'), 'area': '(regex)'}
        self.meta.setdefault(m['terminal'], m)
        return m['terminal']

    def save_meta(self):
        rows = sorted(self.meta.values(), key=lambda r: r['terminal'])
        write_csv(TERMINALS_CSV, rows, ['terminal', 'group', 'ticker', 'kind', 'node', 'area'])
        return {r['terminal']: r for r in rows}


def load_berth_rules():
    return BerthMap()


def berth_terminal(code, rules):
    return rules.terminal(code)


# ---------------------------------------------------------------- fetch
def hidden_fields(html):
    return dict(re.findall(r'<input type="hidden" name="([^"]+)"[^>]*value="([^"]*)"', html))


class Fetcher:
    def __init__(self):
        self.sess = requests.Session(); self.state = None

    def _get_base(self):
        r = self.sess.get(URL, headers=HEADERS, timeout=90); r.raise_for_status(); r.encoding = 'utf-8'
        self.state = hidden_fields(r.text); return r.text

    def fetch(self, d, retries=3):
        ds = d.strftime('%d/%m/%Y'); iso = d.isoformat()
        for i in range(retries):
            try:
                if self.state is None: self._get_base()
                data = dict(self.state)
                data.update({'ctl22$txtDate': ds, 'ctl22$txtDate$dateInput': ds,
                             'ctl22_txtDate_dateInput_ClientState':
                                 '{"enabled":true,"emptyMessage":"","validationText":"%s-00-00-00","valueAsString":"%s-00-00-00",'
                                 '"minDateStr":"1980-01-01-00-00-00","maxDateStr":"2099-12-30-00-00-00","lastSetTextBoxValue":"%s"}' % (iso, iso, ds),
                             'ctl22$btnSearch': 'Tìm kiếm', 'ctl43$txtSearch': 'Từ khóa cần tìm'})
                r = self.sess.post(URL, data=data, headers=HEADERS, timeout=120); r.raise_for_status(); r.encoding = 'utf-8'
                got = re.search(r'id="ctl22_txtDate_dateInput"[^>]*value="([^"]*)"', r.text)
                if not got or got.group(1) != ds:
                    raise RuntimeError(f'trang tra ve ngay {got.group(1) if got else None} thay vi {ds}')
                self.state = hidden_fields(r.text)
                return r.text
            except Exception as e:
                log(f'  loi {ds} ({e}); thu lai {i + 1}/{retries}'); self.state = None; time.sleep(3 * (i + 1))
        return None


# ---------------------------------------------------------------- parse
def split_cargo(s):
    s = (s or '').strip()
    if not s or s.upper() == 'NIL': return '', None
    m = re.match(r'^(.*?)[\s]*([\d.,]+)\s*$', s)
    if m and m.group(1).strip(): return m.group(1).strip().upper(), vn_num(m.group(2).replace('.', '').replace(',', '.') if ',' in m.group(2) and '.' in m.group(2) else m.group(2).replace(',', ''))
    return s.upper(), None


def parse_page(html, plan_date, fetched_at, rules):
    doc = LH.fromstring(html); out = []
    for gid, sec in GRIDS.items():
        tbl = doc.get_element_by_id(gid, None)
        if tbl is None: continue
        cols = COLS[sec]
        for tr in tbl.xpath('.//tr')[1:]:
            cells = [re.sub(r'\s+', ' ', td.text_content()).strip() for td in tr.xpath('./td')]
            if len(cells) != len(cols):
                if cells and cells[0]: log(f'  {plan_date} {sec}: dong {len(cells)} cot la: {cells[:3]}')
                continue
            rec = dict(zip(cols, cells))
            raw = rec['ship']; mark = 1 if raw.startswith('*') else 0
            name = norm_name(raw.lstrip('* ').split('/')[0])            # "PACIFIC GRACE/3FQJ7" -> bỏ hô hiệu
            ctype, cqty = split_cargo(rec['cargo'])
            frm = norm_name(rec.get('from', '')); to = norm_name(rec.get('to', ''))
            out.append({
                'plan_date': plan_date.isoformat(), 'section': sec, 'stt': vn_num(rec['stt']), 'time': rec['time'],
                'time2': rec.get('time2', ''), 'ship': name, 'ship_key': ship_key(name), 'mark': mark,
                'is_sb': 1 if re.search(r'\((VR-)?SB\)', name) else 0, 'flag': rec['flag'], 'callsign': rec['callsign'],
                'draft': vn_num(rec['draft'].replace(',', '.')), 'loa': vn_num(rec['loa'].replace(',', '.')),
                'dwt': vn_num(rec['dwt'].replace(',', '')), 'gt': None, 'cargo_type': ctype, 'cargo_qty': cqty,
                'tugs': rec['tugs'], 'channel': rec['channel'], 'from': frm, 'to': to,
                'terminal_from': berth_terminal(frm, rules) if frm else '', 'terminal_to': berth_terminal(to, rules) if to else '',
                'agent': rec['agent'], 'fetched_at': fetched_at,
            })
    return out


# ---------------------------------------------------------------- summaries (theo terminal đã map, fallback mã cầu)
def with_terminal(events):
    """Bản sao events với from/to thay bằng terminal (để dùng lại build_calls/build_terminal_daily của HP)."""
    out = []
    for e in events:
        e2 = dict(e)
        e2['from'] = e['terminal_from'] or e['from']; e2['to'] = e['terminal_to'] or e['to']
        out.append(e2)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--from', dest='dfrom'); ap.add_argument('--to', dest='dto')
    ap.add_argument('--force', action='store_true'); ap.add_argument('--no-fetch', action='store_true')
    ap.add_argument('--sleep', type=float, default=0.5)
    a = ap.parse_args()
    today = date.today()
    dfrom = date.fromisoformat(a.dfrom) if a.dfrom else today - timedelta(days=3)
    dto = date.fromisoformat(a.dto) if a.dto else today + timedelta(days=1)
    if dto < dfrom: dfrom, dto = dto, dfrom
    os.makedirs(DATA, exist_ok=True); os.makedirs(RAW, exist_ok=True)
    rules = load_berth_rules()

    events = read_csv(EVENTS_CSV); have = {e['plan_date'] for e in events}
    log(f'events hien co: {len(events)} dong, {len(have)} ngay')
    if not a.no_fetch:
        f = Fetcher(); fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M'); recent_lo = today - timedelta(days=3)
        new_by_date = {}; n_days = (dto - dfrom).days + 1; n_new = 0
        for i in range(n_days):
            d = dfrom + timedelta(days=i); ds = d.isoformat()
            always = recent_lo <= d <= today + timedelta(days=1)
            if ds in have and not (a.force or always): continue
            html = f.fetch(d)
            if html is None: continue
            with open(os.path.join(RAW, ds + '.html'), 'w', encoding='utf-8') as fh: fh.write(html)
            evs = parse_page(html, d, fetched_at, rules); new_by_date[ds] = evs; n_new += 1
            log(f'{ds}: {len(evs)} su kien (Vao {sum(1 for e in evs if e["section"] == "Vao")}, Roi {sum(1 for e in evs if e["section"] == "Roi")})')
            if n_new % 50 == 0:
                log(f'  ... {i + 1}/{n_days} ngay, ghi tam events')
                write_csv(EVENTS_CSV, [e for e in events if e['plan_date'] not in new_by_date] + [x for v in new_by_date.values() for x in v], EVENT_FIELDS)
            time.sleep(a.sleep)
        if new_by_date:
            events = [e for e in events if e['plan_date'] not in new_by_date]
            for ds in new_by_date: events.extend(new_by_date[ds])
            events.sort(key=lambda e: (e['plan_date'], SEC_ORDER.get(e['section'], 3), num(e['stt'])))
            write_csv(EVENTS_CSV, events, EVENT_FIELDS)
            log(f'DONE events: +{sum(len(v) for v in new_by_date.values())} dong ({len(new_by_date)} ngay) -> {len(events)} dong, {EVENTS_CSV}')
        else:
            log('khong co ngay nao can keo')
    elif not events:
        for fn in sorted(os.listdir(RAW)):
            if fn.endswith('.html'):
                with open(os.path.join(RAW, fn), encoding='utf-8') as fh:
                    events.extend(parse_page(fh.read(), date.fromisoformat(fn[:-5]), 'cache', rules))
        write_csv(EVENTS_CSV, events, EVENT_FIELDS); log(f'parse lai tu raw: {len(events)} dong')
    else:                                                            # map lại terminal theo berths.csv mới
        for e in events:
            e['terminal_from'] = berth_terminal(e['from'], rules) if e['from'] else ''
            e['terminal_to'] = berth_terminal(e['to'], rules) if e['to'] else ''
        write_csv(EVENTS_CSV, events, EVENT_FIELDS)

    for e in events: e['ship_key'] = ship_key(e['ship'])          # tính lại khoá (bỏ dấu) cho dữ liệu cũ
    evt = with_terminal(events)
    calls = build_calls(evt); write_csv(CALLS_CSV, calls, CALL_FIELDS)
    st = defaultdict(int)
    for c in calls: st[c['status']] += 1
    log(f'DONE calls: {len(calls)} chuyen {dict(st)} -> {CALLS_CSV}')
    terminals = rules.save_meta()                                   # terminals_hcm.csv: bến -> chủ bến, mã CK, loại, cụm địa lý
    td = build_terminal_daily(evt, terminals); write_csv(TERM_DAILY_CSV, td, TERM_FIELDS)
    unmapped = defaultdict(int)
    for e in events:
        if e['from'] and not e['terminal_from']: unmapped[e['from']] += 1
        if e['to'] and not e['terminal_to']: unmapped[e['to']] += 1
    top = sorted(unmapped.items(), key=lambda x: -x[1])[:30]
    log(f'DONE terminal_daily: {len(td)} dong -> {TERM_DAILY_CSV}; ma cau chua map: {len(unmapped)} (top: {", ".join(f"{k}({v})" for k, v in top)})')
    dl = build_daily(evt); write_csv(DAILY_CSV, dl, DAILY_FIELDS); log(f'DONE daily: {len(dl)} ngay -> {DAILY_CSV}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
