# -*- coding: utf-8 -*-
r"""
bds_scrape.py - SCRAPER DỰ ÁN BẤT ĐỘNG SẢN từ batdongsan.com.vn (17/10/2026) -> kho store/ (parquet) cho app BĐS Tracker.

5 lớp dữ liệu, mỗi lớp 1 cờ, chạy nối tiếp trong 1 lệnh (bước pipeline "bds-projects"):
  --geo            bảng tỉnh/thành - quận/huyện - dự án (JSON GetDataForBoxSearch, 1 request)   -> store/geo.json + geo_projects.parquet
  --master         quét TOÀN BỘ trang danh sách /du-an-bat-dong-san/p1..pN (10 dự án/trang, ~610 trang, ~12 phút)
                   -> store/projects.parquet (1 dòng/dự án, giữ cột chi tiết cũ) + store/project_changes.parquet (đổi trạng thái/số căn/...)
  --details N      trang chi tiết N dự án (ưu tiên chưa có, rồi cũ nhất): thuộc tính, toạ độ, chủ đầu tư, giá, mô tả -> cập nhật projects.parquet
  --listings N     thống kê tin rao bán + cho thuê của N dự án (/nha-dat-ban-<slug>, /nha-dat-cho-thue-<slug>, trang 1 = 20 tin + tổng số):
                   số tin, trung vị giá, giá/m², diện tích, tin đăng 7/30 ngày -> store/listing_stats/<YYYY-MM>.parquet (1 dòng/ngày/dự án/loại)
                   ưu tiên dự án Đang mở bán / Sắp mở bán chưa lấy hôm nay, rồi dự án cũ nhất.
  --reports        (lịch sử 2018-2024) tải toàn bộ PDF báo cáo thị trường ở research.batdongsan.com.vn (3 type, phân trang; chỉ tải file chưa có)
                   -> store/reports/<type>/<tên>.pdf + index.csv; rồi trích dòng text/bảng có số liệu (%, tr/m²) bằng pymupdf -> extracted.csv
  --area-history N (lịch sử 1 năm, cấp quận) N trang tìm kiếm quận × loại hình (6 bán / 4 thuê) × bán/thuê, mặc định 400/lần, quay vòng cũ nhất:
                   dòng tóm tắt "Giá bán đã tăng x% trong 1 năm qua" + bảng Thông tin (khoảng giá, diện tích phổ biến) + tổng số tin
                   -> store/area_history/<YYYY-MM>.parquet (1 dòng/ngày/quận/loại/bán-thuê). Danh bạ slug quận: store/area_slugs.csv (--area-slugs dựng lại)

    python bds_scrape.py                       # = --geo --master --details 300 --listings 800 --reports --area-history 400 (chạy hằng ngày)
    python bds_scrape.py --master --pages 3    # thử
    python bds_scrape.py --details 7000        # seed chi tiết toàn bộ (~2 giờ)
    python bds_scrape.py --listings 400 --kinds ban
    python bds_scrape.py --reports             # seed PDF báo cáo (~90 file) + trích số liệu
    python bds_scrape.py --area-history 400    # 400 trang quận/lần (~8 phút); --area-history 10000 = seed toàn bộ ~5.200 trang (~1,5 giờ)
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
import unicodedata
import urllib.parse
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
D_LRAW = os.path.join(STORE, 'listings')          # 20/10/2026: tin rao từng dòng (prid) cho price_index.py
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

    def get_file(self, url, path, tries=3):
        """tải file nhị phân (PDF) về path; trả số byte, 0 nếu 404, None nếu lỗi"""
        for k in range(tries):
            wait = self.delay * random.uniform(0.75, 1.35) - (time.time() - self.t_last)
            if wait > 0: time.sleep(wait)
            try:
                r = self.s.get(url, timeout=300); self.t_last = time.time(); self.n_req += 1
                if r.status_code == 200 and r.content[:5] == b'%PDF-':
                    tmp = path + '.part'
                    with open(tmp, 'wb') as f: f.write(r.content)
                    os.replace(tmp, path); return len(r.content)
                if r.status_code == 404: return 0
                code = f'{r.status_code} ({len(r.content)} byte, không phải PDF)' if r.status_code == 200 else r.status_code
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
    df = df.set_index('project_id'); out = []; raw = []; ok = bad = 0; td = date.fromisoformat(today)
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
            if not cards.empty:
                c2 = cards.copy(); c2['date'] = today; c2['project_id'] = int(pid); c2['kind'] = kind; raw.extend(c2.to_dict('records'))
        df.at[pid, 'listing_at'] = today
        if i % 50 == 0:
            log(f'  tin rao {i}/{len(cand)} dự án ({ok} trang ok, {bad} lỗi, {cl.n_req} request)'); save_listing_stats(out); out = []; save_listings_raw(raw); raw = []
    save_listing_stats(out); save_listings_raw(raw)
    return df.reset_index(), ok, bad


def save_listings_raw(rows):
    """tin rao từng dòng: 1 dòng / prid / kind, giữ first_seen (lần đầu thấy) + date (lần thấy gần nhất) + posted (ngày đăng theo trang),
    file theo tháng của first_seen -> store/listings/<YYYY-MM>.parquet. price_index.py đọc toàn bộ."""
    if not rows: return
    os.makedirs(D_LRAW, exist_ok=True)
    new = pd.DataFrame(rows); new['prid'] = new['prid'].astype(str); new['first_seen'] = new['date']
    new['posted'] = new['posted'].map(lambda x: x.isoformat() if hasattr(x, 'isoformat') else (None if x is None or x != x else str(x)))
    old = load_listings_raw()
    if not old.empty:
        fs = old.set_index(['prid', 'kind'])['first_seen']
        new['first_seen'] = [fs.get((a, b), c) for a, b, c in zip(new['prid'], new['kind'], new['first_seen'])]
    allr = pd.concat([old, new], ignore_index=True).drop_duplicates(['prid', 'kind'], keep='last')
    for ym, g in allr.groupby(allr['first_seen'].str[:7]):
        g = g.sort_values(['first_seen', 'project_id', 'kind', 'prid'])
        for c in ('posted', 'price_unit'): g[c] = g[c].astype('object').where(g[c].notna(), None)
        tmp = os.path.join(D_LRAW, f'{ym}.parquet.tmp'); g.to_parquet(tmp, index=False); os.replace(tmp, os.path.join(D_LRAW, f'{ym}.parquet'))


def load_listings_raw():
    fs = sorted(glob.glob(os.path.join(D_LRAW, '*.parquet')))
    return pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True) if fs else pd.DataFrame()


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


# ================================================================ lớp 4: báo cáo thị trường PDF (research.batdongsan.com.vn)
RESEARCH = 'https://research.batdongsan.com.vn'
REPORT_TYPES = {0: 'thi-truong', 1: 'tinh', 2: 'phan-tich'}      # type=0 báo cáo thị trường (tháng/quý), 1 báo cáo tỉnh, 2 phân tích chuyên sâu / VRES
D_REP = os.path.join(STORE, 'reports')
P_REP_IDX = os.path.join(D_REP, 'index.csv')
P_REP_EXT = os.path.join(D_REP, 'extracted.csv')
REP_IDX_COLS = ['type', 'type_name', 'title', 'published', 'url', 'file', 'size', 'downloaded_at', 'pages', 'text_chars', 'n_images', 'n_hits']
RX_NUM_HIT = re.compile(r'\d[\d\.,]*\s*(%|tr/m|triệu/m|tr\.?/m|triệu đồng/m|đ/m|tỷ/m|điểm)', re.I)


def parse_report_list(html):
    """trang ListingReport/Index -> ([{title, published, url}], số trang lớn nhất thấy trong phân trang)"""
    s = BeautifulSoup(html, 'html.parser'); out = []
    for c in s.select('.card-content'):
        a = c.select_one('a[href]')
        if a is None: continue
        href = a['href'].strip()
        if not re.search(r'\.pdf(\?|$)', href, re.I): continue
        t = _txt(c.select_one('.card-time')) or ''
        md = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', t)
        img = c.select_one('img')
        out.append({'title': _txt(c.select_one('.card-title')) or (img.get('title') if img is not None else None),
                    'published': f'{md.group(3)}-{int(md.group(2)):02d}-{int(md.group(1)):02d}' if md else None,
                    'url': href if href.startswith('http') else RESEARCH + href})
    pages = [int(x) for x in re.findall(r'currentPage=(\d+)', html)]
    return out, (max(pages) if pages else 1)


def list_reports(cl: Client):
    rows = []
    for t, tname in REPORT_TYPES.items():
        p, maxp = 1, 1
        while p <= maxp and p <= 30:
            r = cl.get(f'{RESEARCH}/ListingReport/Index?type={t}&currentPage={p}')
            if r is None: log(f'  báo cáo type={t} trang {p}: không tải được'); break
            items, mp = parse_report_list(r.text); maxp = max(maxp, mp)
            for it in items: rows.append({'type': t, 'type_name': tname, **it})
            if not items: break
            p += 1
    df = pd.DataFrame(rows, columns=['type', 'type_name', 'title', 'published', 'url'])
    return df.drop_duplicates('url').reset_index(drop=True)


def _pdf_name(url):
    name = os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(url).path))
    return re.sub(r'[^\w\.\-\[\]\(\) ]', '_', name)[:150]


def load_report_index():
    if not os.path.exists(P_REP_IDX): return pd.DataFrame(columns=REP_IDX_COLS)
    d = pd.read_csv(P_REP_IDX, dtype={'file': str, 'url': str, 'title': str, 'published': str, 'downloaded_at': str})
    for c in REP_IDX_COLS:
        if c not in d: d[c] = None
    return d


def save_report_index(df):
    os.makedirs(D_REP, exist_ok=True)
    df[REP_IDX_COLS].to_csv(P_REP_IDX, index=False, encoding='utf-8-sig')


def fetch_reports(cl: Client, today: str):
    """liệt kê 3 type -> tải PDF chưa có về store/reports/<type_name>/ -> index.csv; trả (index, số file mới, số lỗi)"""
    idx = load_report_index()
    lst = list_reports(cl)
    if lst.empty: log('  báo cáo: không liệt kê được trang nào'); return idx, 0, 1
    idx = idx.set_index('url'); new = bad = 0
    for r in lst.itertuples():
        if r.url not in idx.index:
            idx.loc[r.url, ['type', 'type_name', 'title', 'published']] = [r.type, r.type_name, r.title, r.published]
        row = idx.loc[r.url]
        rel = row['file'] if isinstance(row['file'], str) and row['file'] else os.path.join(r.type_name, _pdf_name(r.url))
        full = os.path.join(D_REP, rel)
        if os.path.exists(full) and os.path.getsize(full) > 1000:
            if not isinstance(row['file'], str) or not row['file']:
                idx.loc[r.url, ['file', 'size']] = [rel, os.path.getsize(full)]
            continue
        os.makedirs(os.path.dirname(full), exist_ok=True)
        n = cl.get_file(r.url, full)
        if n:
            idx.loc[r.url, ['file', 'size', 'downloaded_at']] = [rel, n, today]; new += 1
            log(f'  tải {rel} ({n / 1e6:.1f} MB)')
        else:
            bad += 1; idx.loc[r.url, 'size'] = 0 if n == 0 else None
    idx = idx.reset_index()
    save_report_index(idx)
    return idx, new, bad


def extract_pdf(path, rel):
    """pymupdf: dòng text có số liệu (% / tr/m² / điểm) + bảng (find_tables) có số -> (rows, pages, text_chars, n_images)"""
    try: import pymupdf
    except ImportError: import fitz as pymupdf  # noqa: N813
    doc = pymupdf.open(path); rows = []; chars = 0; n_img = 0; seen = set()
    for i, page in enumerate(doc, 1):
        txt = page.get_text('text') or ''; chars += len(txt.strip()); n_img += len(page.get_images(full=False))
        for b in page.get_text('blocks'):          # khối text (câu/đoạn/nhãn) giữ ngữ cảnh hơn tách dòng
            if len(b) < 5 or b[6] != 0: continue   # b[6]=1 là khối ảnh
            ln = re.sub(r'\s+', ' ', b[4]).strip()
            if len(ln) < 3 or len(ln) > 700 or not RX_NUM_HIT.search(ln): continue
            k = (i, 'text', ln)
            if k in seen: continue
            seen.add(k); rows.append({'file': rel, 'page': i, 'kind': 'text', 'text': ln})
        try:
            for tb in page.find_tables().tables:
                for row in tb.extract():
                    cells = [re.sub(r'\s+', ' ', c or '').strip() for c in row]
                    ln = ' | '.join(c for c in cells if c)
                    if not re.search(r'\d', ln) or len(ln) < 3: continue
                    k = (i, 'table', ln)
                    if k in seen: continue
                    seen.add(k); rows.append({'file': rel, 'page': i, 'kind': 'table', 'text': ln[:600]})
        except Exception:  # noqa: BLE001 - find_tables thiếu ở pymupdf cũ / trang lỗi
            pass
    n_pages = len(doc); doc.close()
    return rows, n_pages, chars, n_img


def extract_reports(idx: pd.DataFrame):
    """trích số liệu cho các PDF chưa trích (cột pages trống) -> extracted.csv; cập nhật pages/text_chars/n_images/n_hits trong index"""
    todo = idx[idx['file'].notna() & (idx['file'].astype(str) != '') & idx['pages'].isna()]
    if todo.empty: return idx, 0
    out = []; n_ok = 0
    for i, r in todo.iterrows():
        full = os.path.join(D_REP, str(r['file']))
        if not os.path.exists(full): continue
        try: rows, n_pages, chars, n_img = extract_pdf(full, str(r['file']))
        except Exception as e:  # noqa: BLE001
            log(f'  LOI trích {r["file"]}: {e}'); idx.loc[i, ['pages', 'text_chars', 'n_images', 'n_hits']] = [-1, 0, 0, 0]; continue
        idx.loc[i, ['pages', 'text_chars', 'n_images', 'n_hits']] = [n_pages, chars, n_img, len(rows)]
        out.extend(rows); n_ok += 1
    if out:
        new = pd.DataFrame(out)
        if os.path.exists(P_REP_EXT):
            old = pd.read_csv(P_REP_EXT); new = pd.concat([old[~old['file'].isin(new['file'])], new], ignore_index=True)
        new.to_csv(P_REP_EXT, index=False, encoding='utf-8-sig')
    save_report_index(idx)
    return idx, n_ok


# ================================================================ lớp 5: lịch sử giá khu vực (dòng tóm tắt widget "Lịch sử giá" trên trang tìm kiếm cấp quận)
AREA_TYPES = {'can-ho-chung-cu': 'Căn hộ chung cư', 'nha-rieng': 'Nhà riêng', 'nha-mat-pho': 'Nhà mặt phố',
              'nha-biet-thu-lien-ke': 'Biệt thự, liền kề', 'dat-nen-du-an': 'Đất nền dự án', 'dat': 'Đất'}
AREA_KIND_TYPES = {'ban': list(AREA_TYPES), 'thue': ['can-ho-chung-cu', 'nha-rieng', 'nha-mat-pho', 'nha-biet-thu-lien-ke']}  # không có cho thuê đất nền/đất
CITY_PRIORITY = ['Hà Nội', 'Hồ Chí Minh', 'Bình Dương', 'Đồng Nai', 'Đà Nẵng', 'Hải Phòng', 'Khánh Hòa', 'Bà Rịa Vũng Tàu', 'Long An', 'Hưng Yên',
                 'Quảng Ninh', 'Bắc Ninh', 'Bình Định', 'Thanh Hóa', 'Nghệ An', 'Thừa Thiên Huế', 'Cần Thơ', 'Lâm Đồng', 'Kiên Giang', 'Bình Thuận']
D_AREA = os.path.join(STORE, 'area_history')
P_SLUG = os.path.join(STORE, 'area_slugs.csv')
# text MẪU của widget bị khoá KYC (giống nhau ở mọi trang) -> không phải số liệu, chỉ ghi khi KHÁC
AREA_PLACEHOLDER = {'23% Giá thuê đã tăng trong 1 năm qua (Q2/2022 - Q2/2023)', '6% Giá hiện tại thấp hơn đỉnh 8,5 tr/tháng vào Q1/2022',
                    '0 tr/tháng Giá đang cập nhật'}
AREA_COLS = ['date', 'city', 'district', 'city_code', 'district_id', 'district_slug', 'type', 'type_slug', 'kind', 'n_total', 'pct_1y',
             'price_lo', 'price_hi', 'price_unit', 'area_lo', 'area_hi', 'n_info', 'last_posted', 'rent_pct', 'rent_period',
             'peak_pct', 'peak_price', 'peak_unit', 'peak_quarter', 'trend_text', 'raw_text', 'url', 'h1']


def _norm(s):
    """bỏ dấu, thường, đ->d, gọn khoảng trắng: 'Bà Rịa Vũng Tàu' -> 'ba ria vung tau'"""
    s = unicodedata.normalize('NFD', str(s or '')).replace('đ', 'd').replace('Đ', 'D')
    s = ''.join(ch for ch in s if unicodedata.category(ch) != 'Mn')
    return re.sub(r'\s+', ' ', s).strip().lower().replace(' - ', ' ').replace('-', ' ')


def _norm_dist(s):
    """tên quận không tiền tố: 'Quận 7' -> '7', 'Huyện Bình Chánh' -> 'binh chanh', 'Thành Phố Thủ Đức' -> 'thu duc'"""
    return re.sub(r'^(quan|huyen|thanh pho|thi xa|tp\.?|tx\.?|q\.?|h\.?)\s+', '', _norm(s))


def parse_sidebar(html, prefix):
    """link /<prefix>-<slug> trong hộp 'Mua bán nhà đất tại …' (.re__product-count-box) -> [{name, slug, count}]"""
    s = BeautifulSoup(html, 'html.parser'); out = []
    for a in s.select('.re__product-count-box a[href]'):
        href = a['href'].split('?')[0]
        if not href.startswith(f'/{prefix}-'): continue
        name = _txt(a) or ''; m = re.search(r'\(([\d\.]+)\)\s*$', name)
        out.append({'name': re.sub(r'\s*\([\d\.]+\)\s*$', '', name).strip(), 'slug': href[len(prefix) + 2:],
                    'count': vn_num(m.group(1)) if m else None})
    return out


def district_slug_from_url(url):
    """/du-an-can-ho-chung-cu-di-an-bd/xxx-pj1 -> 'di-an-bd' (slug địa bàn dùng chung với trang tìm kiếm)"""
    m = re.match(r'/du-an-([a-z0-9\-]+)/', url or '')
    if not m: return None
    seg = m.group(1); t = type_from_url(url)
    return seg[len(t) + 1:] if t and seg != t else None


def build_area_slugs(cl: Client):
    """danh bạ slug: tỉnh (sidebar trang toàn quốc /ban-dat, /ban-can-ho-chung-cu) -> quận (sidebar trang tỉnh), khớp tên với geo.json;
    quận không khớp thì lấy slug từ URL dự án (projects.parquet) -> store/area_slugs.csv"""
    if not os.path.exists(P_GEO): log('  area: chưa có geo.json (chạy --geo)'); return pd.DataFrame()
    geo = json.load(open(P_GEO, encoding='utf-8'))
    prov = {}
    for pre in ('ban-dat', 'ban-can-ho-chung-cu'):
        r = cl.get('/' + pre)
        if r is None: continue
        for it in parse_sidebar(r.text, pre): prov.setdefault(_norm(it['name']), it['slug'])
    prov.setdefault('ho chi minh', 'tp-hcm'); prov.setdefault('ha noi', 'ha-noi')
    rows = []
    for c in geo.get('cities', []):
        cname = c['name'].strip(); cslug = prov.get(_norm(cname))
        found, cnt = {}, {}
        if cslug:
            for pre in ('ban-dat', 'ban-can-ho-chung-cu'):
                r = cl.get(f'/{pre}-{cslug}')
                if r is None: continue
                for it in parse_sidebar(r.text, pre):
                    k = _norm_dist(it['name']); found.setdefault(k, it['slug']); cnt[k] = (cnt.get(k) or 0) + (it['count'] or 0)
        else:
            log(f'  area: không có slug tỉnh cho {cname}')
        for d in c.get('districts', []):
            k = _norm_dist(d['name'])
            rows.append({'city_code': c['code'], 'city': cname, 'district_id': d['id'], 'district': d['name'].strip(), 'city_slug': cslug,
                         'district_slug': found.get(k), 'n_sidebar': cnt.get(k), 'source': 'sidebar' if found.get(k) else None})
        log(f'  area slug: {cname} -> {cslug}, {sum(1 for d in c.get("districts", []) if _norm_dist(d["name"]) in found)}/{len(c.get("districts", []))} quận')
    df = pd.DataFrame(rows)
    proj, gp = load_projects(), load_geo()
    if len(proj) and len(gp):
        ps = proj[['project_id', 'url']].merge(gp[['project_id', 'district_id']], on='project_id')
        ps['ds'] = ps['url'].map(district_slug_from_url)
        fb = ps.dropna(subset=['ds']).groupby('district_id')['ds'].agg(lambda s: s.value_counts().index[0])
        miss = df['district_slug'].isna()
        df.loc[miss, 'district_slug'] = df.loc[miss, 'district_id'].map(fb)
        df.loc[miss & df['district_slug'].notna(), 'source'] = 'project_url'
    os.makedirs(STORE, exist_ok=True)
    df.to_csv(P_SLUG, index=False, encoding='utf-8-sig')
    log(f'  area slug: {df["district_slug"].notna().sum()}/{len(df)} quận có slug ({(df["source"] == "project_url").sum()} từ URL dự án)')
    return df


def load_area_slugs():
    return pd.read_csv(P_SLUG, dtype={'city_slug': str, 'district_slug': str, 'source': str}) if os.path.exists(P_SLUG) else pd.DataFrame()


def parse_range(val):
    """'29.4 - 151,9 tr/m²' -> (29.4, 151.9, 'tr/m²'); '8 - 60 tr/tháng' -> (8, 60, 'tr/tháng'); '40 - 152 m²' -> (40, 152, 'm²')"""
    if not val: return None, None, None
    parts = re.split(r'\s*[-–]\s*', val.strip(), maxsplit=1)
    lo = vn_num(parts[0]); hi = vn_num(parts[1]) if len(parts) > 1 else lo
    unit = re.sub(r'[\d\.,\s\-–]+', '', val).strip() or None
    return lo, hi, unit


def parse_area_page(html):
    """trang tìm kiếm cấp quận -> dict: tổng số tin, dòng tóm tắt '% 1 năm' (số thật, không cần đăng nhập), bảng Thông tin (khoảng giá,
    diện tích phổ biến, số lượng, cập nhật), và 2 dòng của widget chi tiết CHỈ KHI khác text mẫu (hiện luôn là mẫu -> None)"""
    s = BeautifulSoup(html, 'html.parser'); d = {}; raw = []
    cnt = s.select_one('#count-number'); d['n_total'] = vn_num(_txt(cnt)) if cnt is not None else None
    d['h1'] = _txt(s.select_one('h1'))
    e = s.select_one('.js__entry-chart')
    if e is not None:
        numtxt = _txt(e.select_one('.entry-number')); num = vn_num(numtxt); txt = _txt(e.select_one('.entry-text')) or ''
        cls = ' '.join(e.get('class', []))
        sign = -1 if ('down-trend' in cls or 'giảm' in txt) else (1 if ('up-trend' in cls or 'tăng' in txt) else None)
        if num is not None and sign is not None and '1 năm' in txt: d['pct_1y'] = sign * num
        d['trend_text'] = f'{numtxt or ""} {txt}'.strip() or None
        if d['trend_text']: raw.append(d['trend_text'])
    for tr in s.select('table.re__table-row tr'):
        td = tr.find_all('td')
        if len(td) < 2: continue
        lab0 = _txt(td[0]) or ''; lab = _norm(lab0); val = _txt(td[1]) or ''
        if lab.startswith('gia ') or 'khoang gia' in lab:
            d['price_lo'], d['price_hi'], d['price_unit'] = parse_range(val); raw.append(f'{lab0}: {val}')
        elif 'dien tich' in lab:
            d['area_lo'], d['area_hi'], _ = parse_range(val); raw.append(f'{lab0}: {val}')
        elif lab.startswith('so luong'):
            d['n_info'] = vn_num(val)
        elif 'cap nhat' in lab:
            md = re.search(r'(\d{2})-(\d{2})-(\d{4})', val)
            d['last_posted'] = f'{md.group(3)}-{md.group(2)}-{md.group(1)}' if md else None
    dc = s.select_one('.js__detail-chart')
    if dc is not None:
        t2 = _txt(dc.select_one('.js__pricing-history--top-col-2')) or ''
        t3 = _txt(dc.select_one('.js__pricing-history--top-col-3')) or ''
        if t2 and t2 not in AREA_PLACEHOLDER:
            m = re.search(r'([\d\.,]+)\s*%.*?(tăng|giảm).*?\((Q\d/\d{4}\s*-\s*Q\d/\d{4})\)', t2)
            if m: d['rent_pct'] = vn_num(m.group(1)) * (-1 if m.group(2) == 'giảm' else 1); d['rent_period'] = re.sub(r'\s+', '', m.group(3))
            raw.append(t2)
        if t3 and t3 not in AREA_PLACEHOLDER:
            m = re.search(r'([\d\.,]+)\s*%.*?đỉnh\s*([\d\.,]+)\s*(\S+)\s*vào\s*(Q\d/\d{4})', t3)
            if m: d['peak_pct'], d['peak_price'], d['peak_unit'], d['peak_quarter'] = vn_num(m.group(1)), vn_num(m.group(2)), m.group(3), m.group(4)
            raw.append(t3)
    d['raw_text'] = ' | '.join(raw) if raw else None
    return d


def load_area_history():
    fs = sorted(glob.glob(os.path.join(D_AREA, '*.parquet')))
    return pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True) if fs else pd.DataFrame(columns=AREA_COLS)


def save_area_history(rows):
    if not rows: return
    os.makedirs(D_AREA, exist_ok=True)
    new = pd.DataFrame(rows)
    for c in AREA_COLS:
        if c not in new: new[c] = None
    new = new[AREA_COLS]
    for ym, g in new.groupby(new['date'].str[:7]):
        p = os.path.join(D_AREA, f'{ym}.parquet')
        if os.path.exists(p): g = pd.concat([pd.read_parquet(p), g], ignore_index=True)
        g = g.drop_duplicates(['date', 'district_id', 'type_slug', 'kind'], keep='last').sort_values(['date', 'city', 'district', 'kind', 'type_slug'])
        for c in ['n_total', 'pct_1y', 'price_lo', 'price_hi', 'area_lo', 'area_hi', 'n_info', 'rent_pct', 'peak_pct', 'peak_price', 'district_id']:
            g[c] = pd.to_numeric(g[c], errors='coerce')
        for c in ['price_unit', 'last_posted', 'rent_period', 'peak_unit', 'peak_quarter', 'trend_text', 'raw_text', 'h1', 'url', 'district_slug']:
            g[c] = g[c].astype('object').where(g[c].notna(), None)
        tmp = p + '.tmp'; g.to_parquet(tmp, index=False); os.replace(tmp, p)


def area_queue(slugs: pd.DataFrame, hist: pd.DataFrame, n: int, today: str, kinds=('ban', 'thue')):
    """hàng đợi trang quận × loại × bán/thuê: chưa lấy bao giờ trước (tỉnh lớn trước), rồi lấy cũ nhất; bỏ trang đã lấy hôm nay"""
    sl = slugs.dropna(subset=['district_slug'])
    combos = [{'city_code': r.city_code, 'city': r.city, 'district_id': int(r.district_id), 'district': r.district, 'district_slug': r.district_slug,
               'type_slug': t, 'kind': k} for r in sl.itertuples() for k in kinds for t in AREA_KIND_TYPES[k]]
    q = pd.DataFrame(combos)
    if q.empty: return q
    if len(hist):
        last = hist.groupby(['district_id', 'type_slug', 'kind'])['date'].max().rename('last').reset_index()
        last['district_id'] = last['district_id'].astype(int)
        q = q.merge(last, on=['district_id', 'type_slug', 'kind'], how='left')
    else:
        q['last'] = None
    q = q[q['last'].astype(object) != today]
    pri = {c: i for i, c in enumerate(CITY_PRIORITY)}
    q['_p'] = q['city'].map(pri).fillna(99)
    q = q.sort_values(['last', '_p', 'city', 'district', 'kind', 'type_slug'], na_position='first')
    return q.head(n)


def fetch_area_history(cl: Client, n: int, today: str, kinds=('ban', 'thue'), rebuild_slugs=False):
    slugs = load_area_slugs()
    if rebuild_slugs or slugs.empty or 'district_slug' not in slugs:
        log('  area: dựng danh bạ slug tỉnh/quận…'); slugs = build_area_slugs(cl)
    if slugs.empty: return 0, 1
    hist = load_area_history()
    q = area_queue(slugs, hist, n, today, kinds)
    log(f'  area: {len(q)} trang trong hàng đợi ({(q["last"].isna()).sum() if len(q) else 0} chưa lấy bao giờ)')
    rows = []; ok = bad = 0
    for i, r in enumerate(q.itertuples(), 1):
        path = f"/{'ban' if r.kind == 'ban' else 'cho-thue'}-{r.type_slug}-{r.district_slug}"
        resp = cl.get(path)
        if resp is None or resp.status_code != 200: bad += 1; continue
        try: d = parse_area_page(resp.text)
        except Exception as e:  # noqa: BLE001
            log(f'  LOI parse {path}: {e}'); bad += 1; continue
        if d.get('n_total') is None and not d.get('trend_text'):   # trang chuyển hướng / không phải trang tìm kiếm
            bad += 1; continue
        d.update({'date': today, 'city': r.city, 'district': r.district, 'city_code': r.city_code, 'district_id': r.district_id,
                  'district_slug': r.district_slug, 'type': AREA_TYPES[r.type_slug], 'type_slug': r.type_slug, 'kind': r.kind, 'url': BASE + path})
        rows.append(d); ok += 1
        if i % 50 == 0:
            log(f'  lịch sử giá khu vực {i}/{len(q)} ({ok} ok, {bad} lỗi, {cl.n_req} request)'); save_area_history(rows); rows = []
    save_area_history(rows)
    return ok, bad


# ================================================================ main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--geo', action='store_true'); ap.add_argument('--master', action='store_true')
    ap.add_argument('--pages', type=int, default=None, help='--master: chỉ quét N trang đầu (thử)')
    ap.add_argument('--details', type=int, default=None, metavar='N'); ap.add_argument('--listings', type=int, default=None, metavar='N')
    ap.add_argument('--kinds', default='ban,thue'); ap.add_argument('--delay', type=float, default=DELAY)
    ap.add_argument('--reports', action='store_true', help='tải PDF báo cáo research.batdongsan.com.vn + trích số liệu')
    ap.add_argument('--no-extract', action='store_true', help='--reports: chỉ tải, không trích PDF')
    ap.add_argument('--area-history', type=int, nargs='?', const=400, default=None, metavar='N', help='N trang quận × loại × bán/thuê (mặc định 400)')
    ap.add_argument('--area-slugs', action='store_true', help='dựng lại danh bạ slug quận (store/area_slugs.csv) trước khi --area-history')
    ap.add_argument('--cf-list', action='store_true', help='cafeland: quét danh sách dự án 8 loại (~800 trang) -> store/cafeland/projects.parquet')
    ap.add_argument('--cf-types', default='', help='--cf-list: chỉ vài loại, vd can-ho-chung-cu,khu-do-thi')
    ap.add_argument('--cf-details', type=int, default=None, metavar='N', help='cafeland: N trang chi tiết (giá tham khảo, tiến độ, pháp lý, quy mô)')
    ap.add_argument('--cf-prices', action='store_true', help='cafeland: bảng giá dự án (bản ghi mới kể từ lần trước) -> store/cafeland/price_table/')
    ap.add_argument('--cf-match', action='store_true', help='cafeland: ghép cf_id <-> project_id batdongsan (tên + tỉnh) -> store/cafeland/match.csv')
    a = ap.parse_args(argv)
    any_cf = a.cf_list or a.cf_details is not None or a.cf_prices or a.cf_match
    if not (a.geo or a.master or a.details is not None or a.listings is not None or a.reports or a.area_history is not None or a.area_slugs or any_cf):
        a.geo = a.master = a.reports = True; a.details = 300; a.listings = 800; a.area_history = 400
        a.cf_list = a.cf_prices = a.cf_match = True; a.cf_details = 200
    t0 = time.time(); today = date.today().isoformat(); cl = Client(delay=a.delay); res = {}
    os.makedirs(STORE, exist_ok=True)
    log(f'bds-projects: store={STORE} geo={a.geo} master={a.master} details={a.details} listings={a.listings} reports={a.reports} '
        f'area_history={a.area_history} delay={a.delay}s')
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
    if a.reports:
        idx, new, bad = fetch_reports(cl, today); res['reports_new'] = new; res['reports_err'] = bad
        n_ext = 0
        if not a.no_extract:
            idx, n_ext = extract_reports(idx); res['reports_extracted'] = n_ext
        have = idx['file'].notna().sum() if len(idx) else 0
        log(f'báo cáo: {len(idx)} PDF trong danh mục, {have} đã có file, {new} mới tải, {bad} lỗi, {n_ext} trích mới')
    if a.area_history is not None or a.area_slugs:
        ok, bad = fetch_area_history(cl, a.area_history or 0, today, kinds=tuple(k.strip() for k in a.kinds.split(',') if k.strip()),
                                     rebuild_slugs=a.area_slugs)
        res['area'] = ok; res['area_err'] = bad
        log(f'lịch sử giá khu vực: {ok} trang, {bad} lỗi')
    if a.cf_list or a.cf_details is not None or a.cf_prices or a.cf_match:
        import cafeland as cf
        res.update(cf.run(cl, today, do_list=a.cf_list, details=a.cf_details, prices=a.cf_prices, do_match=a.cf_match,
                          types=[t.strip() for t in a.cf_types.split(',') if t.strip()] or None, bds_projects=load_projects(), geo=load_geo()))
    row = {'run_at': datetime.now().strftime('%Y-%m-%d %H:%M'), 'secs': round(time.time() - t0), 'requests': cl.n_req, 'http_err': cl.n_err, **res}
    runs = pd.concat([pd.read_csv(P_RUNS), pd.DataFrame([row])], ignore_index=True) if os.path.exists(P_RUNS) else pd.DataFrame([row])
    runs.to_csv(P_RUNS, index=False)      # ghép theo TÊN cột (mỗi lần chạy có bộ cột khác nhau)
    ok = cl.n_req > 0 and (cl.n_err < max(5, cl.n_req * 0.3))
    log(f'{"DONE" if ok else "ERROR"} bds-projects: {cl.n_req} request, {cl.n_err} lỗi HTTP, {row["secs"]}s | {res}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
