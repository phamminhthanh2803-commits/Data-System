# -*- coding: utf-8 -*-
r"""
cafeland.py - LỚP ĐỐI CHIẾU từ cafeland.vn/du-an (17/10/2026), gọi qua bds_scrape.py --cf-list / --cf-details N / --cf-prices / --cf-match.
Khảo sát: D:\bat-dong-san\khao-sat-cafeland.md. Không Cloudflare; dùng chung Client của bds_scrape.py (1 request/giây).

Kho store/cafeland/:
  projects.parquet        1 dòng / dự án cafeland: cf_id, name, url, type (8 loại), status (Đang/Sắp mở bán từ thẻ danh sách), lat/lng (link map trong
                          thẻ), province (từ tiêu đề "… tại <tỉnh>"), first_seen/last_seen + cột chi tiết (detail_at, price_ref_text, price_ref_lo/hi
                          triệu/m², progress_text, progress_month, legal_json (số QĐ + ngày), legal_last_date, investor, scale_json (Tổng DT, Mật độ…),
                          area_m2, build_area_m2, units_text, product_json (loại căn + khoảng DT), comps_json (giá dự kiến thấp nhất dự án lân cận),
                          cf_price_min (giá dự kiến thấp nhất của chính dự án, triệu/m²), rating_json, updated_at ("Cập nhật" trên trang)
  project_changes.parquet thay đổi status / giá tham khảo / tiến độ giữa 2 lần quét
  price_table/<YYYY-MM>.parquet  "Bảng giá dự án" (/bang-gia-du-an/): record_id (tăng dần = mốc thời gian), cf_id, name, type_label, status,
                          area_lo/hi, price_lo/hi (triệu/m²), date (ngày quét). Mỗi ngày chỉ quét tới record_id đã có -> chuỗi lịch sử tích luỹ.
  match.csv               cf_id <-> project_id batdongsan (tên + tỉnh, điểm Jaccard), cột `ok` để PV2 sửa tay (1 = đúng, 0 = sai)
"""
from __future__ import annotations

import glob
import json
import os
import re
import unicodedata
from datetime import date

import pandas as pd
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('BDS_STORE') or os.path.join(HERE, 'store')
CF = os.path.join(STORE, 'cafeland')
BASE = 'https://cafeland.vn'
P_PROJ = os.path.join(CF, 'projects.parquet')
P_CHG = os.path.join(CF, 'project_changes.parquet')
D_PRICE = os.path.join(CF, 'price_table')
P_MATCH = os.path.join(CF, 'match.csv')
TYPES = {'can-ho-chung-cu': 'Căn hộ chung cư', 'nha-o-xa-hoi': 'Nhà ở xã hội', 'khu-do-thi': 'Khu đô thị', 'bat-dong-san-nghi-duong': 'BĐS nghỉ dưỡng',
         'dat-nen-du-an': 'Đất nền dự án', 'nha-pho-biet-thu': 'Nhà phố - biệt thự', 'khu-cong-nghiep': 'Khu công nghiệp', 'loai-hinh-khac': 'Loại hình khác'}
DETAIL_COLS = ['detail_at', 'updated_at', 'price_ref_text', 'price_ref_lo', 'price_ref_hi', 'progress_text', 'progress_month', 'legal_json', 'legal_last_date',
               'investor', 'scale_json', 'area_m2', 'build_area_m2', 'units_text', 'product_json', 'comps_json', 'cf_price_min', 'rating_json', 'd_lat', 'd_lng']
WATCH = ['status', 'price_ref_text', 'progress_text', 'name']


def log(m): print(m, flush=True)


def _txt(e): return re.sub(r'\s+', ' ', e.get_text(' ', strip=True)) if e is not None else None


def vn_num(s):
    if s is None: return None
    m = re.search(r'-?\d[\d\.]*(?:,\d+)?', str(s))
    if not m: return None
    t = m.group(0)
    if ',' in t: t = t.replace('.', '').replace(',', '.')
    elif t.count('.') > 1 or re.fullmatch(r'\d{1,3}(\.\d{3})+', t): t = t.replace('.', '')
    try: return float(t)
    except ValueError: return None


def nums(s):
    """mọi số trong chuỗi, kiểu VN"""
    return [v for v in (vn_num(x) for x in re.findall(r'\d[\d\.]*(?:,\d+)?', str(s or ''))) if v is not None]


def parse_area_m2(txt):
    """'8.338m2' -> 8338; '191,61ha' -> 1916100; '- Lô NOXH-01: 1.766,97m2 - Lô 02: …' -> 1766.97 (số dương đầu tiên có đơn vị)"""
    if not txt: return None
    t = str(txt).lower()
    m = re.search(r'(\d[\d\.,]*)\s*(ha|m2|m²|km2)', t)
    if m is None:
        ns = [n for n in nums(t) if n > 0]
        return ns[0] if ns else None
    v = vn_num(m.group(1))
    if v is None: return None
    return v * 10000 if m.group(2) == 'ha' else (v * 1e6 if m.group(2) == 'km2' else v)


def price_per_m2(txt):
    """'Từ 100 triệu đồng/m2' -> (100, 100); 'Dự kiến 22-27 triệu đồng/m2 (…)' -> (22, 27); '24.164.557 đồng/m2; giá thuê: …' -> (24.16, 24.16);
    '1,2 tỷ/m²' -> (1200, 1200); 'Đang cập nhật' -> (None, None). Đơn vị triệu đồng/m²; chỉ lấy phần trước 'giá thuê'/';'."""
    if not txt: return None, None
    t = re.split(r';|giá thuê|cho thuê', str(txt).lower())[0]
    m = re.search(r'(\d[\d\.,]*)\s*(?:-|–|đến|~)?\s*(\d[\d\.,]*)?\s*(triệu|tr(?![a-zđ])|tỷ|nghìn|ngàn|đồng)', t)
    if not m: return None, None
    unit = m.group(3); mult = {'tỷ': 1000, 'nghìn': 0.001, 'ngàn': 0.001, 'đồng': 1e-6}.get(unit, 1)
    lo = vn_num(m.group(1)); hi = vn_num(m.group(2)) if m.group(2) else lo
    if lo is None: return None, None
    if hi is not None and hi < lo and unit != 'đồng': hi = lo
    return round(lo * mult, 3), round((hi if hi is not None else lo) * mult, 3)


# ================================================================ danh sách
def parse_list(html, type_slug):
    """thẻ dự án = cha của .col-proj-right (cột phải: h3 tên, loại, chủ đầu tư, địa chỉ, hàng công cụ có link map lat/lng); nhãn trạng thái .duan-*"""
    s = BeautifulSoup(html, 'html.parser'); out = []
    for right in s.select('.col-proj-right'):
        card = right.parent if right.parent is not None else right
        h = right.find('h3'); a = h.find('a', href=re.compile(r'/du-an/[a-z0-9\-]+-\d+\.html$')) if h else None
        if a is None: continue
        m = re.search(r'-(\d+)\.html$', a['href'])
        mp = right.find('a', href=re.compile(r'map\.cafeland\.vn/tin-du-an/'))
        ll = re.search(r'tin-du-an/(-?\d+\.\d+)/(-?\d+\.\d+)/', mp['href']) if mp else None
        st = card.select_one('[class*="duan-"]')
        inv = right.find('a', href=re.compile(r'/danh-ba/dau-tu-du-an/'))
        addr = right.select_one('.titleProjectSeo'); addr_t = re.sub(r'^\s*Địa chỉ:\s*', '', _txt(addr) or '') or None
        full = (a.get('title') or _txt(a) or '').strip()
        d = {'cf_id': int(m.group(1)), 'url': a['href'], 'title': full, 'name': short_name(full), 'type_slug': type_slug,
             'type': _txt(right.select_one('.news-type-title')) or TYPES.get(type_slug), 'status': _txt(st),
             'lat': float(ll.group(1)) if ll else None, 'lng': float(ll.group(2)) if ll else None,
             'investor': re.sub(r'^Chủ đầu tư:\s*', '', (inv.get('title') or _txt(inv) or '')).strip() or None if inv else None,
             'address': addr_t, 'province': province_from_address(addr_t)}
        out.append(d)
    return out


def short_name(full):
    """'Happy Home Dĩ An: Dự án nhà ở xã hội tại TP.HCM' -> 'Happy Home Dĩ An'; 'Dự án nhà ở xã hội Tây Phù Vân tại Ninh Bình' -> 'nhà ở xã hội Tây Phù Vân'"""
    n = full.split(':', 1)[0].strip() if ':' in full else re.sub(r'\s+tại\s+.+$', '', full).strip()
    return re.sub(r'^(Dự án|Khu|Chung cư)\s+', '', n, flags=re.I).strip() or full


def province_from_address(addr):
    if not addr: return None
    p = addr.rsplit(',', 1)[-1].strip()
    return re.sub(r'^(TP\.?|Tỉnh|Thành phố)\s*', '', p).strip() or None


def scan_list(cl, types=None, max_pages=400):
    rows = []
    for ts in (types or list(TYPES)):
        p, empty = 1, 0
        while p <= max_pages:
            r = cl.get(f'{BASE}/du-an/{ts}/' + ('' if p == 1 else f'page-{p}/'))
            items = parse_list(r.text, ts) if r is not None and r.status_code == 200 else []
            if not items:
                empty += 1
                if empty >= 2: break
            else:
                empty = 0; rows.extend(items)
            p += 1
        log(f'  cafeland {ts}: {p - 1} trang, luỹ kế {len(rows)} dự án')
    df = pd.DataFrame(rows)
    return df.drop_duplicates('cf_id', keep='first').reset_index(drop=True) if len(df) else df


def load_projects():
    return pd.read_parquet(P_PROJ) if os.path.exists(P_PROJ) else pd.DataFrame()


def save_projects(df):
    os.makedirs(CF, exist_ok=True); df = df.copy()
    for c in DETAIL_COLS:
        if c not in df: df[c] = None
    for c in df.columns:
        if df[c].dtype == object: df[c] = df[c].where(df[c].notna(), None)
    tmp = P_PROJ + '.tmp'; df.to_parquet(tmp, index=False); os.replace(tmp, P_PROJ)


def merge_list(old, new, today):
    new = new.copy(); new['last_seen'] = today; new['seen_last_scan'] = True
    if old.empty:
        new['first_seen'] = today
        for c in DETAIL_COLS: new[c] = None
        return new, pd.DataFrame([{'date': today, 'cf_id': int(i), 'name': n, 'field': 'new', 'old': None, 'new': s} for i, n, s in zip(new['cf_id'], new['name'], new['status'])])
    old = old.set_index('cf_id'); new = new.set_index('cf_id'); chg = []; common = new.index.intersection(old.index)
    for c in ['status', 'name', 'investor', 'address']:
        a, b = old.loc[common, c], new.loc[common, c]; diff = ~((a == b) | (a.isna() & b.isna()))
        chg += [{'date': today, 'cf_id': int(i), 'name': new.at[i, 'name'], 'field': c, 'old': a[i], 'new': b[i]} for i in common[diff.values]]
    chg += [{'date': today, 'cf_id': int(i), 'name': new.at[i, 'name'], 'field': 'new', 'old': None, 'new': new.at[i, 'status']} for i in new.index.difference(old.index)]
    for c in ['first_seen'] + DETAIL_COLS: new[c] = old[c].reindex(new.index) if c in old else None
    new['first_seen'] = new['first_seen'].fillna(today)
    gone = old.loc[old.index.difference(new.index)].copy(); gone['seen_last_scan'] = False
    return pd.concat([new, gone]).reset_index(), pd.DataFrame(chg)


def append_changes(chg):
    if chg is None or chg.empty: return 0
    if os.path.exists(P_CHG): chg = pd.concat([pd.read_parquet(P_CHG), chg], ignore_index=True)
    chg = chg.drop_duplicates(['date', 'cf_id', 'field'], keep='last')
    for c in ['old', 'new', 'name']: chg[c] = chg[c].astype(object).where(chg[c].notna(), None)
    os.makedirs(CF, exist_ok=True); chg.to_parquet(P_CHG, index=False); return len(chg)


# ================================================================ chi tiết
_MONTHS = r'(?:tháng|T)\s*(\d{1,2})\s*/\s*(\d{4})'


def _section(soup, title_re):
    """nội dung (text các <p>) sau <h2> có tiêu đề khớp, tới <h2> kế tiếp"""
    for h in soup.find_all(['h2', 'h3']):
        if re.search(title_re, h.get_text(' ', strip=True), re.I):
            out = []
            for sib in h.find_next_siblings():
                if sib.name in ('h2', 'h3'): break
                t = sib.get_text(' ', strip=True) if hasattr(sib, 'get_text') else ''
                if t: out.append(re.sub(r'\s+', ' ', t))
            return out
    return []


def parse_detail(html):
    s = BeautifulSoup(html, 'html.parser'); d = {}
    m = re.search(r'Cập nhật:\s*(\d{1,2}/\d{1,2}/\d{4})', html)
    d['updated_at'] = pd.to_datetime(m.group(1), dayfirst=True).date().isoformat() if m else None
    ll = re.search(r'tin-du-an-xung-quanh/(-?\d+\.\d+)[/,](-?\d+\.\d+)', html)
    if ll: d['d_lat'], d['d_lng'] = float(ll.group(1)), float(ll.group(2))
    # quy mô: bảng 2 cột sau h2 "Quy mô"
    scale = {}
    for h in s.find_all('h2'):
        if re.search(r'quy mô', h.get_text(), re.I):
            tb = h.find_next('table')
            if tb is not None:
                for tr in tb.find_all('tr'):
                    td = tr.find_all('td')
                    if len(td) >= 2: scale[_txt(td[0]).rstrip(':')] = _txt(td[1])
            break
    d['scale_json'] = json.dumps(scale, ensure_ascii=False) if scale else None
    d['area_m2'] = parse_area_m2(next((v for k, v in scale.items() if re.search(r'tổng diện tích(?! sàn)', k, re.I)), None))
    d['build_area_m2'] = parse_area_m2(next((v for k, v in scale.items() if re.search(r'diện tích xây dựng', k, re.I)), None))
    d['units_text'] = next((v for k, v in scale.items() if re.search(r'sản phẩm|số lượng|số căn', k, re.I)), None)
    # sản phẩm: <p><strong>Loại</strong></p><p>Diện tích: a-b m²</p>
    prods = []
    for p in _section(s, r'^sản phẩm'):
        mm = re.match(r'(.+?)\s*Diện tích:?\s*(.+)$', p)
        if mm: prods.append({'loai': mm.group(1).strip(), 'dien_tich': mm.group(2).strip()})
        elif prods and re.match(r'diện tích', p, re.I): prods[-1]['dien_tich'] = p.split(':', 1)[-1].strip()
        elif not re.match(r'diện tích', p, re.I) and len(p) < 80: prods.append({'loai': p.strip(), 'dien_tich': None})
    d['product_json'] = json.dumps(prods, ensure_ascii=False) if prods else None
    # pháp lý: câu có số quyết định + ngày
    legal = []
    for p in _section(s, r'^pháp lý'):
        for mm in re.finditer(r'(?:Quyết định|Văn bản|Giấy phép|Công văn|Nghị quyết)[^\.]{0,200}?(\d{1,2}/\d{1,2}/\d{4})', p):
            legal.append({'text': mm.group(0)[:220], 'date': pd.to_datetime(mm.group(1), dayfirst=True, errors='coerce')})
    if not legal:
        for p in _section(s, r'^pháp lý'):
            for mm in re.finditer(r'(\d{1,2}/\d{1,2}/\d{4})', p):
                legal.append({'text': p[max(0, mm.start() - 120):mm.end()][-220:], 'date': pd.to_datetime(mm.group(1), dayfirst=True, errors='coerce')})
    legal = [x for x in legal if pd.notna(x['date'])]
    d['legal_json'] = json.dumps([{'text': x['text'], 'date': x['date'].date().isoformat()} for x in legal], ensure_ascii=False) if legal else None
    d['legal_last_date'] = max(x['date'] for x in legal).date().isoformat() if legal else None
    # tiến độ + giá tham khảo
    prog = _section(s, r'^tiến độ'); d['progress_text'] = ' | '.join(x for x in prog if not re.search(r'giá bán', x, re.I))[:600] or None
    mm = re.search(_MONTHS, d['progress_text'] or '', re.I) or re.search(r'\d{1,2}/(\d{1,2})/(\d{4})', d['progress_text'] or '')
    d['progress_month'] = f'{int(mm.group(2))}-{int(mm.group(1)):02d}' if mm else None
    gia = next((x for x in prog if re.search(r'giá bán', x, re.I)), None) or next((x for x in re.findall(r'Giá bán tham khảo[^<]{0,120}', html)), None)
    d['price_ref_text'] = gia.split(':', 1)[-1].strip() if gia else None
    d['price_ref_lo'], d['price_ref_hi'] = price_per_m2(d['price_ref_text'])
    # chủ đầu tư
    inv = _section(s, r'chủ đầu tư')
    mm = re.search(r'Chủ đầu tư(?: dự án)?(?: là)?\s*[:\-]?\s*(.+?)(?:\s+hoạt động|\s+thành lập|\s+được|\s+có\s|\s+là\s|,|\.|$)', inv[0]) if inv else None
    d['investor'] = mm.group(1).strip()[:150] if mm else None
    # biểu đồ giá dự án cùng khu vực (Highcharts): {name:"<a href=...-ID.html'>Tên</a>", y: 93}
    comps = [{'cf_id': int(i), 'name': n, 'price_min': float(y)} for i, n, y in re.findall(r"du-an/[a-z0-9\-]+-(\d+)\.html'>([^<]+)</a>\",\s*y:\s*([\d\.]+)", html)]
    d['comps_json'] = json.dumps(comps, ensure_ascii=False) if comps else None
    own = re.search(r'-(\d+)\.html', s.find('link', rel='canonical')['href']) if s.find('link', rel='canonical') else None
    own_id = int(own.group(1)) if own else None
    d['cf_price_min'] = next((c['price_min'] for c in comps if c['cf_id'] == own_id), None)
    mm = re.search(r'var dataSpider = \[([\d\.,\s]*)\]', html)
    if mm and mm.group(1).strip(', '):
        d['rating_json'] = json.dumps([float(x) for x in mm.group(1).replace(' ', '').strip(',').split(',') if x])
    return d


def enrich_details(cl, df, n, today):
    if df.empty or n <= 0: return df, 0, 0
    cand = df[df['seen_last_scan'].fillna(True).astype(bool)].copy()
    cand['_o'] = pd.to_datetime(cand['detail_at'], errors='coerce'); cand = cand.sort_values('_o', na_position='first').head(n)
    df = df.set_index('cf_id'); ok = bad = 0; chg = []
    for i, (cid, row) in enumerate(cand.set_index('cf_id').iterrows(), 1):
        r = cl.get(row['url'])
        if r is None or r.status_code != 200: bad += 1; continue
        try: d = parse_detail(r.text)
        except Exception as e:  # noqa: BLE001
            log(f'  LOI parse cafeland {cid}: {e}'); bad += 1; continue
        for c in ('price_ref_text', 'progress_text'):
            o = df.at[cid, c] if c in df else None
            if pd.notna(o) and o != d.get(c): chg.append({'date': today, 'cf_id': int(cid), 'name': row['name'], 'field': c, 'old': o, 'new': d.get(c)})
        d['detail_at'] = today
        for k, v in d.items(): df.at[cid, k] = v
        ok += 1
        if i % 50 == 0: log(f'  cafeland chi tiết {i}/{len(cand)} ({ok} ok, {bad} lỗi)'); save_projects(df.reset_index())
    append_changes(pd.DataFrame(chg))
    return df.reset_index(), ok, bad


# ================================================================ bảng giá dự án
def parse_price_page(html):
    s = BeautifulSoup(html, 'html.parser'); tb = s.find('table'); out = []
    if tb is None: return out
    for tr in tb.find_all('tr')[1:]:
        td = tr.find_all('td')
        if len(td) < 5: continue
        a = td[1].find('a'); m = re.search(r'-(\d+)\.html', a['href']) if a else None
        name = _txt(td[1]) or ''; typ, _, nm = name.partition(':')
        ar = nums(_txt(td[3])); pr = price_per_m2(_txt(td[4]))
        out.append({'record_id': int(vn_num(_txt(td[0])) or 0), 'cf_id': int(m.group(1)) if m else None, 'name': nm.strip() if nm else name.strip(),
                    'type_label': typ.strip() if nm else None, 'status': _txt(td[2]), 'area_lo': ar[0] if ar else None, 'area_hi': ar[-1] if ar else None,
                    'price_lo': pr[0], 'price_hi': pr[1], 'price_text': _txt(td[4])})
    return out


def load_price_table():
    fs = sorted(glob.glob(os.path.join(D_PRICE, '*.parquet')))
    return pd.concat([pd.read_parquet(f) for f in fs], ignore_index=True) if fs else pd.DataFrame()


def fetch_price_table(cl, today, max_pages=40):
    old = load_price_table(); seen = int(old['record_id'].max()) if len(old) else 0
    rows, p = [], 1
    while p <= max_pages:
        r = cl.get(f'{BASE}/bang-gia-du-an/' + ('' if p == 1 else f'page-{p}/'))
        items = parse_price_page(r.text) if r is not None and r.status_code == 200 else []
        if not items: break
        new = [x for x in items if x['record_id'] > seen]; rows += new
        if len(new) < len(items): break           # đã chạm bản ghi cũ -> dừng
        p += 1
    if not rows: log(f'  bảng giá cafeland: không có bản ghi mới (đã có tới #{seen})'); return 0
    df = pd.DataFrame(rows); df['date'] = today
    os.makedirs(D_PRICE, exist_ok=True); pth = os.path.join(D_PRICE, f'{today[:7]}.parquet')
    if os.path.exists(pth): df = pd.concat([pd.read_parquet(pth), df], ignore_index=True)
    df = df.drop_duplicates('record_id', keep='first').sort_values('record_id'); df.to_parquet(pth, index=False)
    log(f'  bảng giá cafeland: {len(rows)} bản ghi mới (#{seen + 1 if seen else rows[-1]["record_id"]} → #{rows[0]["record_id"]}), {p} trang')
    return len(rows)


# ================================================================ ghép với batdongsan
STOP = {'du', 'an', 'khu', 'can', 'ho', 'chung', 'cu', 'toa', 'tai', 'tp', 'thanh', 'pho', 'nha', 'o', 'xa', 'hoi', 'dan', 'do', 'thi',
        'biet', 'thu', 'lien', 'ke', 'moi', 'phuc', 'hop', 'to', 'cao', 'oc', 'van', 'phong', 'dat', 'nen', 'trung', 'tam', 'thuong', 'mai',
        'residence', 'residences', 'tower', 'towers', 'city', 'park', 'garden', 'home', 'homes', 'new', 'central', 'plaza', 'complex', 'view', 'apartment',
        'quan', 'huyen', 'phuong', 'thi', 'tran', 'da', 'nang', 'ha', 'noi', 'hcm', 'sai', 'gon'}


def _tok(s):
    s = unicodedata.normalize('NFD', str(s or '').lower()); s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').replace('đ', 'd')
    return [t for t in re.sub(r'[^a-z0-9 ]', ' ', s).split() if t not in STOP]


def _prov(s):
    t = ' '.join(_tok(s)); t = re.sub(r'^(ho chi minh|hcm|sai gon)$', 'ho chi minh', t); return t


def province_from_title(name_or_title):
    m = re.search(r'tại\s+(.+)$', str(name_or_title or ''))
    return m.group(1).strip().replace('TP.', '').replace('TP ', '').strip() if m else None


def match(df_cf: pd.DataFrame, df_bds: pd.DataFrame, geo: pd.DataFrame, min_score=0.6):
    """ghép theo token tên (Jaccard) trong cùng tỉnh (tỉnh cafeland lấy từ tiêu đề url / card, batdongsan từ geo); giữ cột ok đã sửa tay"""
    b = df_bds[['project_id', 'name']].merge(geo[['project_id', 'city']], on='project_id', how='left') if len(geo) else df_bds[['project_id', 'name']].assign(city=None)
    b['prov'] = b['city'].map(_prov); b['tok'] = [set(_tok(n)) - set(_tok(c)) for n, c in zip(b['name'], b['city'].fillna(''))]
    old = pd.read_csv(P_MATCH, dtype=str).fillna('') if os.path.exists(P_MATCH) else pd.DataFrame(columns=['cf_id', 'ok'])
    manual = {str(k): v for k, v in zip(old.get('cf_id', []), old.get('ok', [])) if v in ('0', '1')}
    out = []
    for _, r in df_cf.iterrows():
        prov = _prov(r.get('province') or '')
        pt = set(_tok(r.get('province') or '')); t = set(_tok(r['name'])) - pt; cand = b[b['prov'] == prov] if prov and (b['prov'] == prov).any() else b
        sc = cand['tok'].map(lambda x: len(x & t) / max(1, len(x | t)))
        j = sc.idxmax() if len(sc) and sc.max() > 0 else None
        score = round(float(sc.max()), 2) if j is not None else 0
        if j is not None and len(cand.at[j, 'tok'] & t) < 2 and score < 0.99: score = min(score, 0.59)   # chỉ trùng 1 từ -> không tự nhận
        out.append({'cf_id': int(r['cf_id']), 'cf_name': r['name'], 'cf_province': r.get('province'), 'project_id': int(b.at[j, 'project_id']) if j is not None and score >= min_score else None,
                    'bds_name': b.at[j, 'name'] if j is not None else None, 'bds_city': b.at[j, 'city'] if j is not None else None, 'score': score,
                    'ok': manual.get(str(int(r['cf_id'])), '')})
    m = pd.DataFrame(out).sort_values('score', ascending=False); os.makedirs(CF, exist_ok=True); m.to_csv(P_MATCH, index=False, encoding='utf-8-sig')
    n_ok = int((m['project_id'].notna() & (m['ok'] != '0')).sum())
    log(f'  ghép cafeland <-> batdongsan: {n_ok}/{len(m)} có gợi ý (điểm >= {min_score}; >= 0,8: {(m["score"] >= 0.8).sum()}); sửa cột ok trong {P_MATCH}')
    return m


def load_match():
    if not os.path.exists(P_MATCH): return pd.DataFrame()
    m = pd.read_csv(P_MATCH); m = m[m['project_id'].notna() & (m['ok'].astype(str) != '0')]
    return m[['cf_id', 'project_id', 'score']].astype({'cf_id': int, 'project_id': int})


# ================================================================ điểm vào từ bds_scrape.py
def run(cl, today, do_list=False, details=None, prices=False, do_match=False, types=None, bds_projects=None, geo=None):
    res = {}; df = load_projects()
    if len(df) and 'title' not in df:                      # kho quét trước 18/10: tên còn đuôi ": Dự án … tại Tỉnh"
        df['title'] = df['name']; df['name'] = df['title'].map(short_name); save_projects(df)
    if do_list:
        new = scan_list(cl, types=types)
        if new.empty: log('cafeland danh sách: LOI không quét được')
        else:
            df, chg = merge_list(df, new, today); append_changes(chg); save_projects(df)
            res['cf_list'] = len(new); res['cf_changes'] = 0 if chg.empty else len(chg)
            log(f'cafeland danh sách: {len(new)} dự án, kho {len(df)}, {res["cf_changes"]} thay đổi')
    if details:
        df, ok, bad = enrich_details(cl, df, details, today); save_projects(df); res['cf_details'] = ok; res['cf_details_err'] = bad
        log(f'cafeland chi tiết: {ok} dự án, {bad} lỗi; đã có {df["detail_at"].notna().sum()}/{len(df)}')
    if prices:
        res['cf_prices'] = fetch_price_table(cl, today)
    if do_match and len(df) and bds_projects is not None and len(bds_projects):
        m = match(df, bds_projects, geo if geo is not None else pd.DataFrame()); res['cf_match'] = int(m['project_id'].notna().sum())
    return res
