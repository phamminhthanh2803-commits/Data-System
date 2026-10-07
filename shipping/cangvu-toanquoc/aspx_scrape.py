# -*- coding: utf-8 -*-
"""
aspx_scrape.py - Kéo kế hoạch điều động tàu của 3 cảng vụ có trang ASP.NET riêng (không có public-kh hiện hành):
    QNK  Quảng Ninh  https://kht1.cangvuhanghaiquangninh.gov.vn/   POST-back ngày (rdptime); 3 bảng theo khu vực
         Cẩm Phả / Hòn Gai / Quảng Yên; 1 bảng gộp vào-rời-di chuyển (phân loại theo cột Từ/Đến = P/S). Chỉ có từ 2025.
    NTG  Nha Trang   index.aspx?page=shipschedule&cat=2015          cùng nền tảng TP.HCM (ctl22$txtDate + btnSearch); có từ 2019
    CTO  Cần Thơ     Index.aspx?page=khddt&kv=<ct|hg|st|tv>&d=<offset>   tham số d như Hải Phòng; 4 khu vực; có từ ~2021
Schema events giống Hải Phòng (+ cột auth, region); chuyến ghép theo chuỗi tên tàu bằng build_calls của cvhp_scrape.

Chạy:
    python aspx_scrape.py                          # hằng ngày: [hôm nay-3 .. +1] cả 3 cảng vụ
    python aspx_scrape.py --from 2019-01-01        # backfill (bỏ qua ngày đã có; --force kéo lại)
    python aspx_scrape.py --only NTG --from 2024-01-01
    python aspx_scrape.py --no-fetch
"""
import argparse, json, os, re, sys, time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

import requests
import urllib3
import lxml.html as LH

urllib3.disable_warnings()
ROOT = os.path.dirname(os.path.abspath(__file__)); HUB = os.path.dirname(ROOT); DATA = os.path.join(ROOT, 'data')
sys.path.insert(0, os.path.join(HUB, 'cangvu-haiphong')); sys.path.insert(0, ROOT)
from cvhp_scrape import norm_name, ship_key, read_csv, write_csv, vn_num, build_calls, CALL_FIELDS, SEC_ORDER, num   # noqa: E402
from pkh_scrape import infer_kind                                                                                       # noqa: E402

H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 cangvu-toanquoc', 'Accept-Language': 'vi'}
EVENT_FIELDS = ['auth', 'plan_date', 'section', 'stt', 'time', 'ship', 'ship_key', 'is_sb', 'flag', 'draft', 'loa', 'dwt', 'gt', 'tugs',
                'channel', 'region', 'from', 'to', 'agent', 'pilot', 'fetched_at']
PS = re.compile(r'^(P/?S|P0\b|PS\b|HOA TIÊU|TRẠM HOA TIÊU|PHAO SỐ 0|PHAO 0)', re.I)


def log(*a): print(datetime.now().strftime('%H:%M:%S'), *a, flush=True)


def txt(el): return re.sub(r'\s+', ' ', el.text_content()).strip()


def fnum(s):
    """số kiểu '1772.9' hoặc '180.188,8' hoặc '2,4'"""
    s = (s or '').strip().replace(' ', '')
    if not s: return None
    if ',' in s: return vn_num(s)
    if re.fullmatch(r'\d{1,3}(\.\d{3})+', s): return vn_num(s)             # 94.027 = chín mươi tư nghìn
    try: return float(s)
    except ValueError: return None


def hidden(t):
    d = {}
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', t):
        n = re.search(r'name="([^"]+)"', m.group(0)); v = re.search(r'value="([^"]*)"', m.group(0))
        if n: d[n.group(1)] = v.group(1) if v else ''
    return d


def client_state(d):
    iso = d.isoformat(); ds = d.strftime('%d/%m/%Y')
    return json.dumps({"enabled": True, "emptyMessage": "", "validationText": iso + "-00-00-00", "valueAsString": iso + "-00-00-00",
                       "minDateStr": "1980-01-01-00-00-00", "maxDateStr": "2099-12-31-00-00-00", "lastSetTextBoxValue": ds})


def ev(auth, d, sec, stt, tm, ship, draft, loa, dwt, gt, tugs, channel, region, frm, to, agent, pilot, flag, now):
    name = norm_name(ship)
    if not name: return None
    return {'auth': auth, 'plan_date': d.isoformat(), 'section': sec, 'stt': stt, 'time': tm, 'ship': name, 'ship_key': ship_key(name),
            'is_sb': 1 if re.search(r'\((VR-)?SB\)', name) else 0, 'flag': flag, 'draft': fnum(draft), 'loa': fnum(loa), 'dwt': fnum(dwt),
            'gt': fnum(gt), 'tugs': tugs, 'channel': channel, 'region': region, 'from': norm_name(frm), 'to': norm_name(to),
            'agent': agent, 'pilot': pilot, 'fetched_at': now}


def hhmm(s):
    m = re.search(r'(\d{1,2}):(\d{1,2})', s or '')
    return f'{int(m.group(1)):02d}:{int(m.group(2)):02d}' if m else ''


# ---------------------------------------------------------------- Quảng Ninh kht1
class QNK:
    code = 'QNK'; name = 'Quảng Ninh (kht1)'; url = 'https://kht1.cangvuhanghaiquangninh.gov.vn/'; start = date(2025, 3, 25)
    GRIDS = {'GridView_CamPha': 'CAM PHA', 'GridView_HonGai': 'HON GAI', 'GridView_QuangYen': 'QUANG YEN'}

    def __init__(self): self.s = requests.Session(); self.state = None

    def fetch(self, d, now):
        if self.state is None:
            r = self.s.get(self.url, headers=H, timeout=90, verify=False); r.encoding = 'utf-8'; self.state = hidden(r.text)
        data = dict(self.state)
        data.update({'__EVENTTARGET': 'rdptime', '__EVENTARGUMENT': '', 'rdptime': d.isoformat(), 'rdptime$dateInput': d.strftime('%d/%m/%Y'),
                     'rdptime_dateInput_ClientState': client_state(d)})
        r = self.s.post(self.url, data=data, headers=H, timeout=120, verify=False); r.raise_for_status(); r.encoding = 'utf-8'
        self.state = hidden(r.text)
        doc = LH.fromstring(r.text); out = []
        for gid, region in self.GRIDS.items():
            tb = doc.xpath(f'//*[@id="{gid}"]')
            for i, tr in enumerate(tb[0].xpath('.//tr')[1:] if tb else [], 1):
                c = [txt(x) for x in tr.xpath('./td')]
                if len(c) < 12: continue
                m = re.search(r'(\d{2})/(\d{2})/(\d{4})', c[0])
                if m and date(int(m.group(3)), int(m.group(2)), int(m.group(1))) != d: continue        # dòng của ngày khác
                frm, to = c[9], c[10]
                sec = 'Vao' if PS.search(frm) else 'Roi' if PS.search(to) else 'DiChuyen'
                e = ev(self.code, d, sec, i, hhmm(c[0]), c[1], c[2], c[3], c[4], c[5], c[7], c[8], region,
                       '' if sec == 'Vao' else frm, '' if sec == 'Roi' else to, c[11], c[6], '', now)
                if e: out.append(e)
        return out


# ---------------------------------------------------------------- Nha Trang (nền tảng TP.HCM)
class NTG:
    code = 'NTG'; name = 'Nha Trang'; url = 'https://cangvuhanghainhatrang.gov.vn/index.aspx?page=shipschedule&cat=2015'; start = date(2019, 1, 1)
    GRIDS = {'ctl22_GridView_TauVao': 'Vao', 'ctl22_GridView_TauRoi': 'Roi', 'ctl22_GridView_DiChuyen': 'DiChuyen'}

    def __init__(self): self.s = requests.Session(); self.state = None

    def fetch(self, d, now):
        if self.state is None:
            r = self.s.get(self.url, headers=H, timeout=90, verify=False); r.encoding = 'utf-8'; self.state = hidden(r.text)
        ds = d.strftime('%d/%m/%Y'); data = dict(self.state)
        data.update({'ctl22$txtDate': ds, 'ctl22$txtDate$dateInput': ds, 'ctl22_txtDate_dateInput_ClientState': client_state(d),
                     'ctl22$btnSearch': 'Tìm kiếm'})
        r = self.s.post(self.url, data=data, headers=H, timeout=120, verify=False); r.raise_for_status(); r.encoding = 'utf-8'
        got = re.search(r'id="ctl22_txtDate_dateInput"[^>]*value="([^"]*)"', r.text)
        if not got or got.group(1) != ds: raise RuntimeError(f'trang tra ve ngay {got.group(1) if got else None}')
        self.state = hidden(r.text)
        doc = LH.fromstring(r.text); out = []
        for gid, sec in self.GRIDS.items():
            tb = doc.xpath(f'//*[@id="{gid}"]')
            for i, tr in enumerate(tb[0].xpath('.//tr')[1:] if tb else [], 1):
                c = [txt(x) for x in tr.xpath('./td')]
                if len(c) < 9: continue
                e = ev(self.code, d, sec, i, hhmm(c[0]), c[1], c[2], c[3], c[4], '', c[5], '', '', c[6], c[7], c[8], '', '', now)
                if e: out.append(e)
        return out


# ---------------------------------------------------------------- Cần Thơ (tham số d, 4 khu vực)
class CTO:
    code = 'CTO'; name = 'Cần Thơ'; url = 'https://cangvuhanghaicantho.gov.vn/Index.aspx?page=khddt&kv={kv}&d={d}'; start = date(2021, 1, 1)
    KV = {'ct': 'CAN THO', 'hg': 'HAU GIANG', 'st': 'SOC TRANG', 'tv': 'TRA VINH'}
    GRIDS = {'ctl01_rgTauDen_ctl00': 'Vao', 'ctl01_rgTauDi_ctl00': 'Roi', 'ctl01_rgTauDoi_ctl00': 'DiChuyen'}

    def __init__(self): self.s = requests.Session()

    def fetch(self, d, now):
        out = []; off = (d - date.today()).days
        for kv, region in self.KV.items():
            r = self.s.get(self.url.format(kv=kv, d=off), headers=H, timeout=90, verify=False); r.raise_for_status(); r.encoding = 'utf-8'
            doc = LH.fromstring(r.text)
            for gid, sec in self.GRIDS.items():
                for tr in doc.xpath(f'//*[@id="{gid}"]//tr[contains(@class,"rgRow") or contains(@class,"rgAltRow")]'):
                    c = [txt(x) for x in tr.xpath('./td')]
                    if len(c) < 13: continue
                    e = ev(self.code, d, sec, c[0], hhmm(c[1]), c[2], c[4], c[5], c[6], '', c[7], c[8], region,
                           '' if sec == 'Vao' and PS.search(c[9]) else c[9], '' if sec == 'Roi' and PS.search(c[10]) else c[10], c[12], c[11], c[3], now)
                    if e: out.append(e)
            time.sleep(0.15)
        return out


SITES = {'QNK': QNK, 'NTG': NTG, 'CTO': CTO}


def run_site(cls, dfrom, dto, force, no_fetch, sleep):
    site = cls(); ddir = os.path.join(DATA, site.code); os.makedirs(ddir, exist_ok=True)
    p = os.path.join(ddir, 'events.csv'); events = read_csv(p); have = {e['plan_date'] for e in events}
    today = date.today(); now = datetime.now().strftime('%Y-%m-%d %H:%M')
    if not no_fetch:
        d0 = max(dfrom, site.start); new = {}; n = 0
        for i in range((dto - d0).days + 1):
            d = d0 + timedelta(days=i); ds = d.isoformat()
            recent = today - timedelta(days=3) <= d <= today + timedelta(days=1)
            if ds in have and not (force or recent): continue
            for k in range(3):
                try:
                    new[ds] = site.fetch(d, now); n += 1; break
                except Exception as e:
                    log(f'  [{site.code}] loi {ds}: {str(e)[:90]} (thu lai {k + 1}/3)'); time.sleep(4 * (k + 1))
                    if hasattr(site, 'state'): site.state = None
            if n and n % 100 == 0:
                log(f'  [{site.code}] ... {ds} ({n} ngay), ghi tam')
                write_csv(p, [e for e in events if e['plan_date'] not in new] + [x for v in new.values() for x in v], EVENT_FIELDS)
            time.sleep(sleep)
        if new:
            events = [e for e in events if e['plan_date'] not in new] + [x for v in new.values() for x in v]
            events.sort(key=lambda e: (e['plan_date'], SEC_ORDER.get(e['section'], 3), e['time']))
            write_csv(p, events, EVENT_FIELDS)
        log(f'[{site.code}] {site.name}: keo {len(new)} ngay, events {len(events)} dong, {len({e["plan_date"] for e in events})} ngay')
    for e in events: e['ship_key'] = ship_key(e['ship'])
    calls = build_calls(events)
    for c in calls: c['auth'] = site.code
    write_csv(os.path.join(ddir, 'calls.csv'), calls, ['auth'] + CALL_FIELDS)
    cnt = Counter()
    for e in events:
        for t in (e['from'] if e['section'] != 'Vao' else '', e['to'] if e['section'] != 'Roi' else ''):
            if t: cnt[t] += 1
    write_csv(os.path.join(ddir, 'terminals.csv'),
              [{'terminal': t, 'group': t.title(), 'ticker': '', 'kind': infer_kind(t), 'region': '', 'n_events': n} for t, n in cnt.most_common()],
              ['terminal', 'group', 'ticker', 'kind', 'region', 'n_events'])
    log(f'[{site.code}] DONE calls: {len(calls)} chuyen {dict(Counter(c["status"] for c in calls))}')
    return site.code, len(events), len(calls)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--from', dest='dfrom'); ap.add_argument('--to', dest='dto'); ap.add_argument('--only', default='')
    ap.add_argument('--force', action='store_true'); ap.add_argument('--no-fetch', action='store_true'); ap.add_argument('--sleep', type=float, default=0.3)
    a = ap.parse_args()
    today = date.today()
    dfrom = date.fromisoformat(a.dfrom) if a.dfrom else today - timedelta(days=3)
    dto = date.fromisoformat(a.dto) if a.dto else today + timedelta(days=1)
    codes = a.only.split(',') if a.only else list(SITES)
    with ThreadPoolExecutor(max_workers=len(codes)) as ex:
        res = list(ex.map(lambda c: run_site(SITES[c], dfrom, dto, a.force, a.no_fetch, a.sleep), codes))
    log(f'DONE aspx: {res}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
