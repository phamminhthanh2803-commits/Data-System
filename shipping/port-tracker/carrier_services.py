# -*- coding: utf-8 -*-
"""
carrier_services.py - TÊN TUYẾN DỊCH VỤ của từng tàu theo LỊCH TÀU CÔNG KHAI của hãng (26/10/2026, PV2).

EconDB (API trả phí) không có tên tuyến; web EconDB chặn khi quét nhiều -> lấy thẳng từ hãng: mỗi nguồn trả bảng
    carrier, service_code, service_name, vessel, imo, source_url
gộp vào store/carrier_services.csv (giữ bản cũ của hãng khi lần kéo lỗi). services.cluster(names=...) gom tàu theo tên tuyến này.

Nguồn:
  hai_an    : lịch tàu Hải An (bước haian, HAH_DIR/haian-voyages.csv): mã tuyến (SCX, VSX, ECX, VIN, PHX, DOM...) chuyến gần nhất mỗi tàu
  yang_ming : API lịch dài hạn chính thức yangming.com/api/LongTerm (GetServiceList + GetServiceDetail), tuyến có cảng VN (~22 request)
  cosco     : API công khai elines.coscoshipping.com: tên tàu -> mã tàu COSCO -> lịch 8 tuần -> tuyến hiện tại (loopAbbrv);
              chỉ tàu hãng COSCO/OOCL đã ghé VN 12 tháng (master), ~2 request/tàu -> chạy THỨ HAI (WEEKLY)
  Đã dò và KHÔNG dùng (26/10/2026): MSC, CMA CGM, ZIM, KMTC, Wan Hai, OOCL (chặn bot), HMM (robots cấm), Maersk (robots cấm trang lịch),
  Evergreen ShipmentLink (robots cấm tác tử AI), ONE (robots cấm /api/), Flexport Atlas (điều khoản cấm truy cập tự động),
  vessel-schedule-service.com (chỉ cảng Nhật, bán gói API). API chính thức cần key miễn phí: Maersk, Hapag-Lloyd, CMA CGM, ONE, ZIM.

    python carrier_services.py                 # kéo mọi nguồn
    python carrier_services.py --only hai_an
"""
import argparse
import os
import sys
import time

import pandas as pd

APP = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('PORT_TRACKER_STORE') or os.path.join(APP, 'store')
OUT = os.path.join(STORE, 'carrier_services.csv')
HAH_DIR = os.environ.get('HAH_DIR') or ('D:/Database/Logistics/HAH' if os.name == 'nt' else os.path.join(os.path.dirname(os.path.dirname(APP)), 'hah'))
COLS = ['carrier', 'service_code', 'service_name', 'vessel', 'imo', 'source_url']
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
WEEKLY = {'cosco'}            # nguồn nhiều request: chỉ chạy thứ Hai (hoặc --only)


class Polite:
    """requests.Session giới hạn số request, nghỉ >= delay giây giữa 2 lần gọi; 403/429 -> dừng nguồn (không lách)"""
    def __init__(self, max_requests, delay=1.2, headers=None):
        import requests
        self.s = requests.Session(); self.s.headers.update({'User-Agent': UA, 'Accept': 'application/json, text/plain, */*', **(headers or {})})
        self.left, self.delay, self.t = max_requests, delay, 0.0

    def get(self, url, **kw):
        if self.left <= 0: raise RuntimeError('hết hạn mức request')
        w = self.delay - (time.time() - self.t)
        if w > 0: time.sleep(w)
        self.left -= 1; r = self.s.get(url, timeout=40, **kw); self.t = time.time()
        if r.status_code in (403, 429): raise RuntimeError(f'{r.status_code} - dừng nguồn')
        r.raise_for_status(); return r


def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)


def fetch_hai_an(max_requests=None):
    """mã tuyến của chuyến gần nhất (đã/ sắp chạy trong 120 ngày) mỗi tàu trong lịch Hải An; tàu thuê slot (YM, Wan Hai...) cũng có
    mã tuyến HAH -> chỉ dùng khi tàu không có nguồn từ chính hãng khai thác (ưu tiên ở names_for_rotations)"""
    f = os.path.join(HAH_DIR, 'haian-voyages.csv')
    if not os.path.exists(f): return pd.DataFrame(columns=COLS)
    d = pd.read_csv(f, encoding='utf-8-sig')
    d['t'] = pd.to_datetime(d['FirstETD'], dayfirst=True, errors='coerce')
    now = pd.Timestamp.now()
    d = d[(d['t'] >= now - pd.Timedelta(days=120)) & (d['t'] <= now + pd.Timedelta(days=60)) & d['Service'].notna()]
    d = d.sort_values('t').drop_duplicates('Vessel', keep='last')
    return pd.DataFrame({'carrier': 'Hai An (HAH)', 'service_code': d['Service'].astype(str).str.strip(), 'service_name': '',
                         'vessel': d['Vessel'].astype(str).str.strip(), 'imo': None, 'source_url': 'https://eservice.haiants.vn/'})


YM_API = 'https://www.yangming.com/api/'


def fetch_yang_ming(max_requests=60):
    """tuyến Yang Ming có cảng VN (mã cảng VNxxx) -> tàu + IMO theo vòng quay (lịch gồm ~7 tuần đã chạy)"""
    http = Polite(max_requests, headers={'Referer': 'https://www.yangming.com/en/esolution/schedule/long_term_schedule_download'})
    loops = []
    for x in http.get(YM_API + 'LongTerm/GetServiceList').json():
        if any(str(p.get('portCode', '')).startswith('VN') for p in (x.get('portList') or [])) and x['loop'] not in [l for l, _ in loops]:
            loops.append((x['loop'], x['directn']))
    rows = []
    for loop, bound in loops:
        url = f'{YM_API}LongTerm/GetServiceDetail?serviceCode={loop}&bound={bound}'
        d = http.get(url).json() or {}
        for ver in d.get('verList') or []:
            for r in ver.get('rotationList') or []:
                if r.get('vesselName'):
                    rows.append({'carrier': 'Yang Ming', 'service_code': loop, 'service_name': d.get('loopName') or '', 'vessel': r['vesselName'].strip(),
                                 'imo': r.get('imoNo') or None, 'source_url': url})
    return pd.DataFrame(rows, columns=COLS).drop_duplicates(['service_code', 'vessel'])


COSCO = 'https://elines.coscoshipping.com'


def _vn_fleet(operators):
    """tàu container của các hãng `operators` ghé VN 12 tháng (master dựng sẵn) -> [(tên, imo)]"""
    f = os.path.join(STORE, 'present', 'master.parquet')
    if not os.path.exists(f): return []
    m = pd.read_parquet(f, columns=['ship', 'imo', 'operator', 'vessel_class', 'calls_12m'])
    m = m[m['operator'].isin(operators) & m['vessel_class'].astype(str).str.startswith('container') & (pd.to_numeric(m['calls_12m'], errors='coerce') > 0)]
    return list(dict.fromkeys(zip(m['ship'].astype(str).str.strip().str.upper(), m['imo'])))


def fetch_cosco(max_requests=400):
    """tuyến HIỆN TẠI của tàu COSCO/OOCL đã ghé VN: findVesselByPrefix -> mã tàu -> purpoShipment/vesselCode (8 tuần);
    tuyến = loopAbbrv của chuyến có lượt ghé gần nhất đã qua (chưa có thì chuyến đầu)"""
    http = Polite(max_requests, headers={'language': 'en_US', 'Referer': COSCO + '/ebusiness/'})
    now = pd.Timestamp.now(); rows = []
    for name, imo in _vn_fleet(['COSCO', 'OOCL']):
        try:
            hits = http.get(f'{COSCO}/ebbase/public/general/findVesselByPrefix', params={'prefix': name}).json()['data']['content']
            code = next((h['code'] for h in hits if (h.get('description') or '').upper() == name), None)
            if not code: continue
            url = f'{COSCO}/ebschedule/public/purpoShipment/vesselCode?vesselCode={code}&period=8'
            d = http.get(url).json()['data']['content']['data'] or []
        except Exception as e:  # noqa: BLE001 - lỗi 1 tàu bỏ qua; hết hạn mức / 403 / 429 thì dừng nguồn
            if 'hạn mức' in str(e) or '403' in str(e) or '429' in str(e): break
            continue
        loop, cur, first = None, None, None
        for r in d:
            loop = r.get('loopAbbrv') or loop
            first = first or loop
            t = pd.to_datetime(r.get('arrDtlocAct') or r.get('arrDtlocCos'), errors='coerce')
            if loop and pd.notna(t) and t <= now: cur = loop
        svc = cur or first
        if svc: rows.append({'carrier': 'COSCO', 'service_code': svc, 'service_name': '', 'vessel': name, 'imo': imo, 'source_url': url})
    return pd.DataFrame(rows, columns=COLS)


FETCHERS = {'hai_an': fetch_hai_an, 'yang_ming': fetch_yang_ming, 'cosco': fetch_cosco}


def pull(only=None):
    old = pd.read_csv(OUT, dtype=str) if os.path.exists(OUT) else pd.DataFrame(columns=COLS + ['source', 'fetched'])
    parts, errs = [], []
    weekly_ok = time.localtime().tm_wday == 0 or not os.path.exists(OUT)
    for k, fn in FETCHERS.items():
        if only and k not in only: continue
        if not only and k in WEEKLY and not weekly_ok: continue
        try:
            d = fn()
            if d is None or d.empty: raise RuntimeError('0 dòng')
            d = d.assign(source=k, fetched=time.strftime('%Y-%m-%d %H:%M'))
            parts.append(d); log(f'{k}: {len(d)} tàu, {d["service_code"].nunique()} tuyến')
        except Exception as e:  # noqa: BLE001 - giữ bản cũ của nguồn lỗi
            errs.append(f'{k}: {str(e)[:150]}'); log(f'  LOI {k}: {str(e)[:150]}')
            if len(old): parts.append(old[old['source'] == k])
    done = {p['source'].iloc[0] for p in parts if len(p)}
    keep = old[~old['source'].isin(done)] if len(old) else old
    out = pd.concat([keep] + parts, ignore_index=True) if parts else old
    os.makedirs(STORE, exist_ok=True); out.to_csv(OUT, index=False, encoding='utf-8-sig')
    log(f'-> {OUT}: {len(out)} dòng')
    return errs


def load():
    return pd.read_csv(OUT, dtype=str) if os.path.exists(OUT) else pd.DataFrame(columns=COLS)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--only', default='')
    a = ap.parse_args(argv)
    errs = pull([x.strip() for x in a.only.split(',') if x.strip()] or None)
    return 1 if errs and len(errs) == len(FETCHERS) else 0


if __name__ == '__main__':
    sys.exit(main())
