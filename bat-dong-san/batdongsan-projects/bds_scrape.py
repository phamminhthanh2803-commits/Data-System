# -*- coding: utf-8 -*-
r"""
bds_scrape.py - SCRAPER DỰ ÁN BẤT ĐỘNG SẢN từ batdongsan.com.vn (17/10/2026) -> kho store/ (parquet) cho app BĐS Tracker.

3 lớp dữ liệu, mỗi lớp 1 cờ, chạy nối tiếp trong 1 lệnh (bước pipeline "bds-projects"):
  --geo            bảng tỉnh/thành - quận/huyện - dự án (JSON GetDataForBoxSearch, 1 request)   -> store/geo.json + geo_projects.parquet
  --master         quét TOÀN BỘ trang danh sách /du-an-bat-dong-san/p1..pN (10 dự án/trang, ~610 trang, ~12 phút)
                   -> store/projects.parquet (1 dòng/dự án, giữ cột chi tiết cũ) + store/project_changes.parquet (đổi trạng thái/số căn/...)
  --details N      trang chi tiết N dự án (ưu tiên chưa có, rồi cũ nhất): thuộc tính, toạ độ, chủ đầu tư, giá, mô tả -> cập nhật projects.parquet
  --listings N     thống kê tin rao bán + cho thuê của N dự án (/nha-dat-ban-<slug>, /nha-dat-cho-thue-<slug>, trang 1 = 20 tin + tổng số):
                   số tin, trung vị giá, giá/m², diện tích, tin đăng 7/30 ngày -> store/listing_stats/<YYYY-MM>.parquet (1 dòng/ngày/dự án/loại)
                   ưu tiên dự án Đang mở bán / Sắp mở bán chưa lấy hôm nay, rồi dự án cũ nhất.

    python bds_scrape.py                       # = --geo --master --details 300 --listings 800 (chạy hằng ngày)
    python bds_scrape.py --master --pages 3    # thử
    python bds_scrape.py --details 7000        # seed chi tiết toàn bộ (~2 giờ)
    python bds_scrape.py --listings 400 --kinds ban
Env: BDS_STORE (thư mục store/), BDS_DELAY (giây nghỉ giữa 2 request, mặc định 1.0).
Nguồn chặn bot bằng Cloudflare -> dùng curl_cffi giả lập Chrome; 403/429 thì nghỉ 5/20/60 giây và đổi fingerprint.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import random
import re
import sys
import time
from datetime import date, datetime, timedelta

import pandas as pd
from bs4 import BeautifulSoup
from curl_cffi import requests as creq

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('BDS_STORE') or os.path.join(HERE, 'store')
BASE = 'https://batdongsan.com.vn'
DELAY = float(os.environ.get('BDS_DELAY', '1.0'))
IMPERSONATE = ['chrome124', 'chrome120', 'chrome116', 'safari17_0', 'edge101']
TYPES = {   # tiền tố URL /du-an-<loại>-<địa bàn>/ (dài -> ngắn để khớp đúng)
    'khu-nghi-duong-sinh-thai': 'Khu nghỉ dưỡng, sinh thái', 'trung-tam-thuong-mai': 'Trung tâm thương mại',
    'cao-oc-van-phong': 'Cao ốc văn phòng', 'can-ho-chung-cu': 'Căn hộ chung cư', 'biet-thu-lien-ke': 'Biệt thự, liền kề',
    'khu-cong-nghiep': 'Khu công nghiệp', 'khu-do-thi-moi': 'Khu đô thị mới', 'nha-o-xa-hoi': 'Nhà ở xã hội',
    'khu-phuc-hop': 'Khu phức hợp', 'nha-mat-pho': 'Nhà mặt phố', 'shophouse': 'Shophouse', 'khac': 'Dự án khác'}
STATUS_ACTIVE = ('Đang mở bán', 'Sắp mở bán')
P_PROJ = os.path.join(STORE, 'projects.parquet')
P_CHG = os.path.join(STORE, 'project_changes.parquet')
P_GEO = os.path.join(STORE, 'geo.json')
P_GEOP = os.path.join(STORE, 'geo_projects.parquet')
D_LST = os.path.join(STORE, 'listing_stats')
P_RUNS = os.path.join(STORE, 'runs.csv')
MASTER_COLS = ['project_id', 'slug', 'url', 'name', 'status', 'type_slug', 'type', 'address', 'area_text', 'area_m2', 'units', 'blocks',
               'summary', 'investor', 'n_images', 'page', 'pos']
DETAIL_COLS = ['detail_at', 'd_name', 'd_status', 'd_address', 'city', 'district', 'lat', 'lng', 'investor_name', 'investor_id', 'legal',
               'price_text', 'price_lo', 'price_hi', 'd_area_m2', 'd_units', 'd_blocks', 'build_area_m2', 'floors', 'density',
               'handover', 'attrs_json', 'sale_types', 'desc']


def log(msg): print(msg, flush=True)


# ================================================================ HTTP
class Client:
    def __init__(self, delay=DELAY):
        self.delay, self.i_imp, self.n_req, self.n_err, self.t_last = delay, 0, 0, 0, 0.0
        self._new()

    def _new(self):
        self.s = creq.Session(impersonate=IMPERSONATE[self.i_imp % len(IMPERSONATE)])

    def get(self, path, tries=4, **kw):
        url = path if path.startswith('http') else BASE + path
        for k in range(tries):
            wait = self.delay * random.uniform(0.75, 1.35) - (time.time() - self.t_last)
            if wait > 0: time.sleep(wait)
            try:
                r = self.s.get(url, timeout=40, **kw); self.t_last = time.time(); self.n_req += 1
                if r.status_code == 200 and len(r.text) > 5000: return r
                if r.status_code == 404: return r
                code = r.status_code
            except Exception as e:  # noqa: BLE001
                code = f'EXC {type(e).__name__}'; self.t_last = time.time()
            self.n_err += 1
            if k < tries - 1:
                pause = [5, 20, 60][min(k, 2)]
                log(f'  {code} {url} -> nghỉ {pause}s, đổi fingerprint')
                self.i_imp += 1; self._new(); time.sleep(pause)
        return None


# ================================================================ parse tiện ích
def vn_num(s):
    """'6.045,58' -> 6045.58 ; '1,04' -> 1.04 ; '772' -> 772 ; '9.017' -> 9017"""
    if s is None: return None
    m = re.search(r'-?\d[\d\.]*(?:,\d+)?', str(s))
    if not m: return None
    t = m.group(0)
    if ',' in t: t = t.replace('.', '').replace(',', '.')
    elif t.count('.') > 1 or re.fullmatch(r'\d{1,3}(\.\d{3})+', t): t = t.replace('.', '')
    try: return float(t)
    except ValueError: return None


def parse_area(txt):
    """'1,04 ha' -> 10400 m²; '6.045,58 m²' -> 6045.58; '71,3 ha' -> 713000"""
    if not txt: return None
    v = vn_num(txt)
    if v is None: return None
    t = txt.lower()
    if re.search(r'\bha\b', t): return round(v * 10000, 2)
    if 'km' in t: return v * 1e6
    return v


def parse_price(txt):
    """giá tin rao -> (giá trị, đơn vị): '3,7 tỷ' -> (3.7,'tỷ'); '850 triệu' -> (0.85,'tỷ'); '100 triệu/tháng' -> (100,'triệu/tháng');
    'Thỏa thuận' -> (None, None)"""
    if not txt: return None, None
    t = txt.lower().strip(); v = vn_num(t)
    if v is None: return None, None
    if '/tháng' in t:
        if 'tỷ' in t: v *= 1000
        elif 'nghìn' in t or 'ngàn' in t: v /= 1000
        return v, 'triệu/tháng'
    if 'tỷ' in t: return v, 'tỷ'
    if 'triệu' in t: return v / 1000, 'tỷ'
    if 'nghìn' in t: return v / 1e6, 'tỷ'
    return None, None


def parse_ppm2(txt):
    """'74 tr/m²' -> 74 (triệu/m²); '166,67 nghìn/m²' -> 0.16667; '1,2 tỷ/m²' -> 1200"""
    if not txt: return None
    t = txt.lower(); v = vn_num(t)
    if v is None: return None
    if 'tỷ' in t: return v * 1000
    if 'nghìn' in t or 'ngàn' in t: return v / 1000
    return v


def type_from_url(url):
    m = re.match(r'/du-an-([a-z0-9\-]+)/', url or '')
    if not m: return None
    seg = m.group(1)
    for k in sorted(TYPES, key=len, reverse=True):
        if seg == k or seg.startswith(k + '-'): return k
    return None


def _txt(e): return re.sub(r'\s+', ' ', e.get_text(' ', strip=True)) if e is not None else None


# ================================================================ lớp 0: geo
def fetch_geo(cl: Client):
    r = cl.get('/microservice-architecture-router/Systems/Home/GetDataForBoxSearch',
               headers={'Referer': BASE + '/du-an-bat-dong-san', 'Accept': 'application/json'})
    if r is None: return None
    try: d = r.json()
    except Exception: return None  # noqa: BLE001
    rows = []
    for c in d.get('cities', []):
        for dd in c.get('districts', []):
            for p in dd.get('projects') or []:
                rows.append({'project_id': int(p['id']), 'geo_name': p['name'], 'city_code': c['code'], 'city': c['name'].strip(),
                             'district_id': dd['id'], 'district': dd['name'].strip()})
    os.makedirs(STORE, exist_ok=True)
    json.dump(d, open(P_GEO, 'w', encoding='utf-8'), ensure_ascii=False)
    g = pd.DataFrame(rows).drop_duplicates('project_id')
    g.to_parquet(P_GEOP, index=False)
    return g


def load_geo():
    cols = ['project_id', 'geo_name', 'city_code', 'city', 'district_id', 'district']
    return pd.read_parquet(P_GEOP) if os.path.exists(P_GEOP) else pd.DataFrame(columns=cols)


# ================================================================ lớp 1: danh sách
def parse_list_page(html):
    s = BeautifulSoup(html, 'html.parser'); out = []
    for card in s.select('.js__card-project-web'):
        a = card.select_one('a[href*="-pj"]')
        if a is None: continue
        href = a.get('href', ''); m = re.search(r'-pj(\d+)$', href)
        if not m: continue
        tl = a.get('tracking-label', ''); mp = re.search(r'pgno=(\d+)', tl); mi = re.search(r'ipos=(\d+)', tl)
        d = {'project_id': int(m.group(1)), 'slug': href.rsplit('/', 1)[-1].rsplit('-pj', 1)[0], 'url': href,
             'name': _txt(card.select_one('.re__prj-card-title')) or a.get('title'),
             'status': _txt(card.select_one('.re__prj-tag-info label')),
             'type_slug': type_from_url(href), 'address': _txt(card.select_one('.re__prj-card-location')),
             'summary': _txt(card.select_one('.re__prj-card-summary')), 'investor': _txt(card.select_one('.re__prj-card-contact')) or None,
             'area_text': None, 'units': None, 'blocks': None,
             'n_images': vn_num(_txt(card.select_one('.re__prj-card-image-feature span'))),
             'page': int(mp.group(1)) if mp else None, 'pos': int(mi.group(1)) if mi else None}
        for sp in card.select('.re__prj-card-config-value'):
            lab = sp.get('aria-label') or ''; t = _txt(sp) or ''
            if re.search(r'căn', lab): d['units'] = vn_num(lab)
            elif re.search(r'tòa|toà', lab): d['blocks'] = vn_num(lab)
            elif re.search(r'(m²|m2|ha)\s*$', t): d['area_text'] = t
        d['area_m2'] = parse_area(d['area_text']); d['type'] = TYPES.get(d['type_slug'])
        out.append(d)
    return out


def scan_master(cl: Client, pages=None, stop_empty=2):
    rows, empty, p = [], 0, 1
    while True:
        if pages and p > pages: break
        r = cl.get('/du-an-bat-dong-san' + ('' if p == 1 else f'/p{p}'))
        items = parse_list_page(r.text) if r is not None else []
        if not items:
            empty += 1
            if r is None: log(f'  trang {p}: không tải được')
            if empty >= stop_empty: break
        else:
            empty = 0; rows.extend(items)
        if p % 25 == 0: log(f'  quét {p} trang, {len(rows)} dự án, {cl.n_req} request, {cl.n_err} lỗi')
        p += 1
    df = pd.DataFrame(rows)
    if df.empty: return df
    return df.drop_duplicates('project_id', keep='first').reset_index(drop=True)


def load_projects():
    if not os.path.exists(P_PROJ):
        return pd.DataFrame(columns=MASTER_COLS + ['first_seen', 'last_seen', 'seen_last_scan'] + DETAIL_COLS + ['listing_at'])
    return pd.read_parquet(P_PROJ)


def save_projects(df):
    os.makedirs(STORE, exist_ok=True)
    df = df.copy()
    for c in DETAIL_COLS + ['listing_at']:
        if c not in df: df[c] = None
    for c in ['detail_at', 'd_name', 'd_status', 'd_address', 'city', 'district', 'investor_name', 'legal', 'price_text', 'handover',
              'attrs_json', 'sale_types', 'desc', 'listing_at', 'investor', 'area_text', 'summary', 'address', 'status', 'name']:
        df[c] = df[c].astype('object').where(df[c].notna(), None)
    for c in ['lat', 'lng', 'price_lo', 'price_hi', 'd_area_m2', 'd_units', 'd_blocks', 'build_area_m2', 'floors', 'density',
              'investor_id', 'units', 'blocks', 'area_m2', 'n_images', 'page', 'pos']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    tmp = P_PROJ + '.tmp'; df.to_parquet(tmp, index=False); os.replace(tmp, P_PROJ)


def merge_master(old: pd.DataFrame, new: pd.DataFrame, today: str):
    """ghép lần quét mới vào master: giữ first_seen + mọi cột chi tiết cũ; ghi project_changes khi 7 cột theo dõi đổi"""
    WATCH = ['status', 'units', 'blocks', 'area_text', 'name', 'address', 'investor']
    new = new.copy(); new['last_seen'] = today; new['seen_last_scan'] = True
    if old.empty:
        new['first_seen'] = today
        for c in DETAIL_COLS + ['listing_at']: new[c] = None
        chg = pd.DataFrame([{'date': today, 'project_id': int(p), 'name': n, 'field': 'new', 'old': None, 'new': s}
                            for p, n, s in zip(new['project_id'], new['name'], new['status'])])
        return new, chg
    old = old.set_index('project_id'); new = new.set_index('project_id')
    chg = []
    common = new.index.intersection(old.index)
    for c in WATCH:
        a, b = old.loc[common, c], new.loc[common, c]
        diff = ~((a == b) | (a.isna() & b.isna()))
        for pid in common[diff.values]:
            chg.append({'date': today, 'project_id': int(pid), 'name': new.at[pid, 'name'], 'field': c,
                        'old': None if pd.isna(a[pid]) else str(a[pid]), 'new': None if pd.isna(b[pid]) else str(b[pid])})
    for pid in new.index.difference(old.index):
        chg.append({'date': today, 'project_id': int(pid), 'name': new.at[pid, 'name'], 'field': 'new', 'old': None, 'new': new.at[pid, 'status']})
    keep_cols = ['first_seen'] + DETAIL_COLS + ['listing_at']
    for c in keep_cols:
        new[c] = old[c].reindex(new.index) if c in old else None
    new['first_seen'] = new['first_seen'].fillna(today)
    gone = old.loc[old.index.difference(new.index)].copy()
    gone['seen_last_scan'] = False
    out = pd.concat([new, gone]).reset_index()
    return out, pd.DataFrame(chg)


def append_changes(chg: pd.DataFrame):
    if chg is None or chg.empty: return 0
    if os.path.exists(P_CHG): chg = pd.concat([pd.read_parquet(P_CHG), chg], ignore_index=True)
    chg = chg.drop_duplicates(['date', 'project_id', 'field'], keep='last')
    for c in ['old', 'new', 'name']: chg[c] = chg[c].astype('object').where(chg[c].notna(), None)
    chg.to_parquet(P_CHG, index=False); return len(chg)


def load_changes():
    return pd.read_parquet(P_CHG) if os.path.exists(P_CHG) else pd.DataFrame(columns=['date', 'project_id', 'name', 'field', 'old', 'new'])


# ================================================================ lớp 2: chi tiết
def parse_detail(html):
    s = BeautifulSoup(html, 'html.parser'); d = {}
    d['d_name'] = _txt(s.select_one('h1.re__project-name'))
    ad = s.select_one('.re__project-address')
    if ad is not None:
        for a in ad.select('a'): a.decompose()
        d['d_address'] = (_txt(ad) or '').rstrip('. ') or None
    main = s.select_one('.project-main-container') or s
    st = main.select_one('.re__prj-tag-info:not(.re__prj-tag-info-fix) label')
    d['d_status'] = _txt(st)
    attrs = {}
    box = s.select_one('.re__project-main-number .re__project-attr-box') or s.select_one('.re__project-attr-box')
    if box is not None:
        for tr in box.select('tr'):
            td = tr.find_all('td')
            if len(td) >= 2:
                attrs[_txt(td[0])] = _txt(td[1])
                a = td[1].find('a', href=re.compile(r'-ep\d+'))
                if a is not None and 'Chủ đầu tư' in _txt(td[0]):
                    d['investor_id'] = int(re.search(r'-ep(\d+)', a['href']).group(1))
    d['attrs_json'] = json.dumps(attrs, ensure_ascii=False) if attrs else None
    d['investor_name'] = attrs.get('Chủ đầu tư'); d['legal'] = attrs.get('Pháp lý'); d['price_text'] = attrs.get('Giá')
    d['d_area_m2'] = parse_area(attrs.get('Diện tích')); d['build_area_m2'] = parse_area(attrs.get('Diện tích xây dựng'))
    d['d_units'] = vn_num(attrs.get('Số căn hộ') or attrs.get('Số căn') or attrs.get('Số sản phẩm'))
    d['d_blocks'] = vn_num(attrs.get('Số tòa') or attrs.get('Số toà')); d['floors'] = vn_num(attrs.get('Số tầng'))
    d['density'] = vn_num(attrs.get('Mật độ xây dựng')); d['handover'] = attrs.get('Thời điểm bàn giao') or attrs.get('Bàn giao')
    if d['price_text']:
        nums = [vn_num(x) for x in re.findall(r'\d[\d\.,]*', d['price_text'])]
        nums = [x for x in nums if x is not None]
        mult = 1000 if 'tỷ' in d['price_text'].lower() else 1
        if nums: d['price_lo'], d['price_hi'] = nums[0] * mult, (nums[1] if len(nums) > 1 else nums[0]) * mult
    m = re.search(r'maps/embed/v1/place\?q=(-?\d+\.\d+),(-?\d+\.\d+)', html)
    if m: d['lat'], d['lng'] = float(m.group(1)), float(m.group(2))
    for sc in s.find_all('script', type='application/ld+json'):
        try: j = json.loads(sc.string or '')
        except Exception: continue  # noqa: BLE001
        if j.get('@type') == 'BreadcrumbList':
            it = j.get('itemListElement', [])
            if len(it) >= 4: d['city'] = it[2].get('name'); d['district'] = it[3].get('name')
        elif j.get('@type') == 'FAQPage':
            for q in j.get('mainEntity', []):
                t = re.sub(r'<[^>]+>', '', q.get('acceptedAnswer', {}).get('text', ''))
                mm = re.search(r'bao gồm các loại hình:\s*(.+?)\.?$', t)
                if mm: d['sale_types'] = mm.group(1).strip()
    dc = s.select_one('.re__detail-content')
    if dc is not None: d['desc'] = (_txt(dc) or '')[:2000]
    return d


def enrich_details(cl: Client, df: pd.DataFrame, n: int, today: str):
    if df.empty or n <= 0: return df, 0, 0
    cand = df[df['seen_last_scan'].fillna(True).astype(bool)].copy()
    cand['_o'] = pd.to_datetime(cand['detail_at'], errors='coerce')
    cand = cand.sort_values('_o', na_position='first').head(n)
    df = df.set_index('project_id'); ok = bad = 0
    for i, (pid, row) in enumerate(cand.set_index('project_id').iterrows(), 1):
        r = cl.get(row['url'])
        if r is None or r.status_code != 200:
            bad += 1; continue
        try: d = parse_detail(r.text)
        except Exception as e:  # noqa: BLE001
            log(f'  LOI parse chi tiết pj{pid}: {e}'); bad += 1; continue
        d['detail_at'] = today
        for k, v in d.items(): df.at[pid, k] = v
        ok += 1
        if i % 50 == 0:
            log(f'  chi tiết {i}/{len(cand)} ({ok} ok, {bad} lỗi, {cl.n_req} request)'); save_projects(df.reset_index())
    return df.reset_index(), ok, bad


# ================================================================ lớp 3: tin rao
def rel_date(txt, today):
    """'Đăng hôm nay' / 'hôm qua' / '3 ngày trước' / '2 tuần trước' / '1 tháng trước' -> ngày"""
    t = (txt or '').lower()
    if 'hôm nay' in t: return today
    if 'hôm qua' in t: return today - timedelta(days=1)
    m = re.search(r'(\d+)\s*(ngày|tuần|tháng|năm)', t)
    if not m: return None
    n, u = int(m.group(1)), m.group(2)
    return today - timedelta(days=n * {'ngày': 1, 'tuần': 7, 'tháng': 30, 'năm': 365}[u])


def parse_srp(html, kind, today=None):
    today = today or date.today()
    s = BeautifulSoup(html, 'html.parser')
    cnt = s.select_one('#count-number'); n_total = vn_num(_txt(cnt)) if cnt is not None else None
    rows = []
    for c in s.select('.js__card-listing[prjid]'):
        pr, unit = parse_price(_txt(c.select_one('.re__card-config-price')))
        pub = c.select_one('.re__card-published-info-published-at')
        pt = ' '.join(x for x in [pub.get('aria-label', ''), pub.get('title', ''), _txt(pub) or ''] if x) if pub is not None else ''
        md = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', pt)
        posted = date(int(md.group(3)), int(md.group(2)), int(md.group(1))) if md else rel_date(pt, today)
        bed = c.select_one('.re__card-config-bedroom')
        rows.append({'prid': c.get('prid'), 'price': pr, 'price_unit': unit, 'area': vn_num(_txt(c.select_one('.re__card-config-area'))),
                     'ppm2': parse_ppm2(_txt(c.select_one('.re__card-config-price_per_m2'))),
                     'bed': vn_num(bed.get('aria-label', '')) if bed is not None else None,
                     'posted': posted})
    return n_total, pd.DataFrame(rows)


def srp_stats(n_total, cards: pd.DataFrame, today: date):
    o = {'n_total': n_total, 'n_sample': len(cards)}
    if cards.empty: return o
    o['price_med'] = cards['price'].median(); o['price_p25'] = cards['price'].quantile(.25); o['price_p75'] = cards['price'].quantile(.75)
    o['ppm2_med'] = cards['ppm2'].median(); o['ppm2_p25'] = cards['ppm2'].quantile(.25); o['ppm2_p75'] = cards['ppm2'].quantile(.75)
    o['area_med'] = cards['area'].median(); o['n_price'] = int(cards['price'].notna().sum()); o['n_ppm2'] = int(cards['ppm2'].notna().sum())
    p = pd.to_datetime(cards['posted'], errors='coerce')
    o['n_7d'] = int((p >= pd.Timestamp(today) - pd.Timedelta(days=7)).sum()); o['n_30d'] = int((p >= pd.Timestamp(today) - pd.Timedelta(days=30)).sum())
    o['posted_max'] = None if p.isna().all() else p.max().date().isoformat()
    return o


def fetch_listings(cl: Client, df: pd.DataFrame, n: int, today: str, kinds=('ban', 'thue')):
    if df.empty or n <= 0: return df, 0, 0
    cand = df[df['seen_last_scan'].fillna(True).astype(bool)].copy()
    cand['_act'] = cand['status'].isin(STATUS_ACTIVE)
    cand['_o'] = pd.to_datetime(cand['listing_at'], errors='coerce')
    cand = cand[~(cand['_act'] & (cand['listing_at'] == today))]
    cand = pd.concat([cand[cand['_act']].sort_values('_o', na_position='first'),
                      cand[~cand['_act']].sort_values('_o', na_position='first')]).head(n)
    df = df.set_index('project_id'); out = []; ok = bad = 0; td = date.fromisoformat(today)
    for i, (pid, row) in enumerate(cand.set_index('project_id').iterrows(), 1):
        for kind in kinds:
            r = cl.get(('/nha-dat-ban-' if kind == 'ban' else '/nha-dat-cho-thue-') + row['slug'])
            if r is None or r.status_code != 200: bad += 1; continue
            try:
                n_total, cards = parse_srp(r.text, kind, td)
                if not cards.empty: cards = cards[cards['prid'].notna()]
            except Exception as e:  # noqa: BLE001
                log(f'  LOI parse tin rao pj{pid} {kind}: {e}'); bad += 1; continue
            o = srp_stats(n_total, cards, td); o.update({'date': today, 'project_id': int(pid), 'kind': kind}); out.append(o); ok += 1
        df.at[pid, 'listing_at'] = today
        if i % 50 == 0:
            log(f'  tin rao {i}/{len(cand)} dự án ({ok} trang ok, {bad} lỗi, {cl.n_req} request)'); save_listing_stats(out); out = []
    save_listing_stats(out)
    return df.reset_index(), ok, bad


def save_listing_stats(rows):
    if not rows: return
    os.makedirs(D_LST, exist_ok=True)
    new = pd.DataFrame(rows)
    for ym, g in new.groupby(new['date'].str[:7]):
        p = os.path.join(D_LST, f'{ym}.parquet')
        if os.path.exists(p): g = pd.concat([pd.read_parquet(p), g], ignore_index=True)
        g = g.drop_duplicates(['date', 'project_id', 'kind'], keep='last').sort_values(['date', 'project_id', 'kind'])
        if 'posted_max' in g: g['posted_max'] = g['posted_max'].astype('object').where(g['posted_max'].notna(), None)
        g.to_parquet(p, index=False)


def load_listing_stats():
    fs = sorted(glob.glob(os.path.join(D_LST, '*.parquet')))
    return pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True) if fs else pd.DataFrame()


# ================================================================ main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--geo', action='store_true'); ap.add_argument('--master', action='store_true')
    ap.add_argument('--pages', type=int, default=None, help='--master: chỉ quét N trang đầu (thử)')
    ap.add_argument('--details', type=int, default=None, metavar='N'); ap.add_argument('--listings', type=int, default=None, metavar='N')
    ap.add_argument('--kinds', default='ban,thue'); ap.add_argument('--delay', type=float, default=DELAY)
    a = ap.parse_args(argv)
    if not (a.geo or a.master or a.details is not None or a.listings is not None):
        a.geo = a.master = True; a.details = 300; a.listings = 800
    t0 = time.time(); today = date.today().isoformat(); cl = Client(delay=a.delay); res = {}
    os.makedirs(STORE, exist_ok=True)
    log(f'bds-projects: store={STORE} geo={a.geo} master={a.master} details={a.details} listings={a.listings} delay={a.delay}s')
    if a.geo:
        g = fetch_geo(cl); res['geo'] = 0 if g is None else len(g)
        log(f'geo: {res["geo"]} dự án có tỉnh/quận' if g is not None else 'geo: LOI không tải được')
    df = load_projects()
    if a.master:
        new = scan_master(cl, pages=a.pages)
        if new.empty: log('master: LOI không quét được trang nào')
        else:
            df, chg = merge_master(df, new, today); n_chg = append_changes(chg); save_projects(df)
            res['master'] = len(new); res['changes'] = 0 if chg.empty else len(chg)
            log(f'master: {len(new)} dự án quét được, kho {len(df)} dự án, {res["changes"]} thay đổi (kho thay đổi {n_chg} dòng)')
    if a.details:
        df, ok, bad = enrich_details(cl, df, a.details, today); save_projects(df); res['details'] = ok; res['details_err'] = bad
        log(f'chi tiết: {ok} dự án, {bad} lỗi; đã có chi tiết {df["detail_at"].notna().sum()}/{len(df)}')
    if a.listings:
        df, ok, bad = fetch_listings(cl, df, a.listings, today, kinds=tuple(k.strip() for k in a.kinds.split(',') if k.strip()))
        save_projects(df); res['listings'] = ok; res['listings_err'] = bad
        log(f'tin rao: {ok} trang, {bad} lỗi')
    row = {'run_at': datetime.now().strftime('%Y-%m-%d %H:%M'), 'secs': round(time.time() - t0), 'requests': cl.n_req, 'http_err': cl.n_err, **res}
    pd.DataFrame([row]).to_csv(P_RUNS, mode='a', header=not os.path.exists(P_RUNS), index=False)
    ok = cl.n_req > 0 and (cl.n_err < max(5, cl.n_req * 0.3))
    log(f'{"DONE" if ok else "ERROR"} bds-projects: {cl.n_req} request, {cl.n_err} lỗi HTTP, {row["secs"]}s | {res}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
