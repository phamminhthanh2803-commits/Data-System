# -*- coding: utf-8 -*-
r"""
biggee_api.py - nạp dữ liệu giá + LỊCH SỬ GIÁ từ Biggee API vào kho store/biggee/ (17/10/2026).

Nguồn tài liệu: https://biggee.vn/thong-tin-api ("Tài liệu mô tả" = Google Sheet) + docs.biggee.vn/open-api + mẫu hợp đồng.
  - Host API thật: https://app.digihub.com.vn/api/ (sheet mô tả); docs.biggee.vn ghi https://biggee.vn/api/ -> script thử cả hai.
  - Tham số GET query (partner_key, uri_req, lat, lng, radius); API danh sách nhận city/district/ward bằng POST form-data.
  - Hợp đồng mẫu: lịch sử giá qua API = 12 THÁNG gần nhất (website gói Xem giá ghi 5 năm) -> muốn dài hơn phải thương lượng khi ký.
  - Biggee cấp key qua email sau khi ký + tạm ứng 20% (7 ngày làm việc). Giá: để trống trong hợp đồng mẫu, hỏi 0889441000 / contact@biggee.vn.

API dùng:
  getCityList / getDistrictList / getWardList / getStreetList / getProjectList  -> bảng mã (URI_REQ) tỉnh, quận, phường, đường, DỰ ÁN (tự lấy, không cần Biggee gửi)
  dinhgiacanho (docs) | house_price_place (sheet)  -> giá theo mã: dinhgia (đơn giá TB thấp/cao/tham khảo, DT p50, giá bán p50, điểm mô hình),
                                                     sosanh (tin rao so sánh), lichsu (THÁNG: dongia_sosanh = giá chính vị trí, dongia_quanhuyen, ngay_xu_ly MM/YYYY)
  house_price_list                                 -> bảng giá khu vực (mặt tiền / hẻm 1-2-3 / đất sào thấp-cao-TB) theo phường hoặc quận
  gianhadat_by_radius / giacanho_by_radius         -> giá tuyến đường / dự án quanh toạ độ (< 1 km)
  fulltext_search (POST keyword)                   -> tìm mã địa chỉ

    python biggee_api.py --ping                                  # kiểm tra key: getCityList
    python biggee_api.py --catalog                               # tỉnh -> quận -> dự án -> store/biggee/ma_du_an.csv (+ ma_quan.csv, ma_tinh.csv)
    python biggee_api.py --catalog --cities "Hồ Chí Minh,Hà Nội"  # chỉ vài tỉnh
    python biggee_api.py --test                                  # gọi giá 1 mã dự án đầu tiên, in JSON thô (xem đơn vị thật)
    python biggee_api.py --projects [--limit 200] [--since 2026-10-01] [--codes a,b]   # giá + lịch sử tháng mọi dự án -> project_history/valuation/comps.parquet
    python biggee_api.py --streets store/biggee/ma_duong.csv     # giá nhà đất theo mã đường (cột URI_REQ)
    python biggee_api.py --around 10.724 106.740 --rad 800 [--kind canho|nhadat]
    python biggee_api.py --match                                 # gợi ý ghép mã Biggee <-> project_id batdongsan (tên + tỉnh) -> ma_du_an_goi_y.csv
    python biggee_api.py --update [--budget 900] [--refresh-catalog] [--delay 0.5]
        # 20/10 (tối): bước HẰNG THÁNG của run_slot (ngày 1-3): (1) bảng mã còn thiếu (quận chưa gọi getProjectList; --refresh-catalog = gọi lại
        # quận lấy trước đầu tháng), (2) lịch sử + định giá mọi mã (catalog ∪ bảng giá web ∪ kho lịch sử) chưa lấy trong tháng này.
        # Hết ngân sách request trong ngày -> dừng êm (exit 0), lần chạy sau (ngày mai) tiếp từ chỗ dừng. Xoá store/biggee/backfill.flag khi hết việc.
Key: env BIGGEE_KEY hoặc store/biggee/key.txt (1 dòng; KHÔNG commit, không lên Drive). JSON thô giữ ở store/biggee/raw/<api>/.
QUOTA: 1.000 request/ngày (30 ngày từ 20/10/2026). Mỗi request ghi vào store/biggee/quota.csv (date,n); --budget N (mặc định 950) = trần trong ngày,
chạm trần -> QuotaHet, mọi bước lưu dở dang rồi thoát. API chịu 3 request/giây (delay 0,3) không lỗi; hằng tháng dùng delay 0,5.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import date

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('BDS_STORE') or os.path.join(HERE, 'store')
BG = os.path.join(STORE, 'biggee')
HOSTS = ['https://app.digihub.com.vn/api/', 'https://biggee.vn/api/']
P_CODES = os.path.join(BG, 'ma_du_an.csv')
P_TINH = os.path.join(BG, 'ma_tinh.csv')
P_QUAN = os.path.join(BG, 'ma_quan.csv')                           # + cột list_fetched (ngày gọi getDistrictList), projects_fetched (ngày gọi getProjectList)
P_LIST = os.path.join(BG, 'apart_price_list.parquet')              # bảng giá web (biggee_web.py): slug = uri_req
P_QUOTA = os.path.join(BG, 'quota.csv')                            # date,n: số request đã gọi mỗi ngày (quota 1.000/ngày)
P_FLAG = os.path.join(BG, 'backfill.flag')                         # có file -> run_slot chạy bước biggee cả ngoài ngày 1-3 (còn việc dở); --update xoá khi xong
P_HIST = os.path.join(BG, 'project_history.parquet')
P_VAL = os.path.join(BG, 'project_valuation.parquet')
P_COMP = os.path.join(BG, 'project_comps.parquet')
P_STREET_HIST = os.path.join(BG, 'street_history.parquet')
P_STREET_VAL = os.path.join(BG, 'street_valuation.parquet')
PROJECT_PRICE_APIS = ['dinhgiacanho', 'house_price_place']       # docs.biggee.vn | sheet mô tả (thử lần lượt, nhớ cái chạy được)


def log(m): print(m, flush=True)


def get_key():
    k = os.environ.get('BIGGEE_KEY')
    if k: return k.strip()
    p = os.path.join(BG, 'key.txt')
    if os.path.exists(p): return open(p, encoding='utf-8').read().strip()
    sys.exit('Chưa có partner_key: đặt env BIGGEE_KEY (setx BIGGEE_KEY "...") hoặc ghi vào store/biggee/key.txt')


def num(v):
    """chuỗi số Biggee ('45.5', '45,5', '1.250,5', '') -> float"""
    if v is None: return None
    if isinstance(v, (int, float)): return float(v)
    s = str(v).strip().replace(' ', '')
    if not s or s.lower() in ('null', 'none', 'nan'): return None
    if ',' in s and '.' in s: s = s.replace('.', '').replace(',', '.')
    elif ',' in s: s = s.replace(',', '.')
    try: return float(s)
    except ValueError: return None


def month(v):
    """'11/2019' | '2019-11' | '2019-11-01' -> Timestamp cuối tháng"""
    if not v: return None
    s = str(v).strip()
    m = re.match(r'^(\d{1,2})/(\d{4})$', s)
    if m: return pd.Timestamp(int(m.group(2)), int(m.group(1)), 1) + pd.offsets.MonthEnd(0)
    try: return pd.Timestamp(s) + pd.offsets.MonthEnd(0)
    except Exception: return None  # noqa: BLE001


def lower_keys(d):
    return {str(k).lower(): v for k, v in d.items()} if isinstance(d, dict) else d


class QuotaHet(Exception):
    """chạm trần request trong ngày (--budget, quota Biggee 1.000/ngày) -> các bước lưu dở dang rồi dừng êm, ngày mai chạy tiếp"""


def quota_today():
    """số request đã gọi hôm nay theo store/biggee/quota.csv"""
    if not os.path.exists(P_QUOTA): return 0
    q = pd.read_csv(P_QUOTA, dtype=str).fillna(''); r = q[q['date'] == date.today().isoformat()]
    return int(float(r['n'].iloc[-1])) if len(r) else 0


def quota_save(n):
    t = date.today().isoformat()
    q = pd.read_csv(P_QUOTA, dtype=str).fillna('') if os.path.exists(P_QUOTA) else pd.DataFrame(columns=['date', 'n'])
    q = pd.concat([q[q['date'] != t], pd.DataFrame([{'date': t, 'n': int(n)}])], ignore_index=True)
    os.makedirs(BG, exist_ok=True); q.to_csv(P_QUOTA, index=False)


class Biggee:
    def __init__(self, key, delay=0.6, budget=950):
        from curl_cffi import requests as creq
        self.s = creq.Session(impersonate='chrome124'); self.key = key; self.delay = delay
        self.n = 0; self.err = 0; self.nodata = 0; self.host = None; self.project_api = None
        self.budget = budget; self.n_day = quota_today()               # đã gọi hôm nay (mọi lần chạy script trong ngày)

    def _tick(self):
        if self.n_day >= self.budget: raise QuotaHet(f'đã {self.n_day}/{self.budget} request hôm nay')
        self.n += 1; self.n_day += 1; quota_save(self.n_day)

    def _json(self, r):
        """JSON dict của API (status 200 HTTP + body dict) hoặc None; 'Vượt giới hạn gọi API' -> QuotaHet"""
        if r.status_code != 200: return None
        try: j = r.json()
        except Exception: return None  # noqa: BLE001
        if not isinstance(j, dict): return None
        if 'giới hạn' in str(j.get('status_message', '')).lower():       # {"status":500,"status_message":"Vượt giới hạn gọi API"} = hết quota ngày (thật)
            self.n_day = max(self.n_day, self.budget, 1000); quota_save(self.n_day)
            raise QuotaHet(f'API báo "{j.get("status_message")}" (quota ngày đã hết, bộ đếm quota.csv đặt {self.n_day})')
        return j

    @staticmethod
    def _status(j):
        st = j.get('status', 200)
        try: return int(st)
        except (TypeError, ValueError): return 200 if str(st).lower() in ('ok', 'success', 'true') else 0

    def call(self, api, form=None, **query):
        """GET query (partner_key + query); form = dict POST form-data (API danh sách). Thử lần lượt các host, nhớ host chạy được.
        Trả dict JSON khi API trả lời (kể cả status 404 'Not Found' = mã không có dữ liệu -> data None, KHÔNG thử host khác, không tính lỗi);
        None khi lỗi mạng/HTTP (tính vào self.err)."""
        q = {'partner_key': self.key, **query}; last = None
        for host in ([self.host] if self.host else HOSTS):
            self._tick(); time.sleep(self.delay)
            try:
                r = self.s.post(host + api, params=q, data=form, timeout=60) if form else self.s.get(host + api, params=q, timeout=60)
                j = self._json(r)
                if j is not None:
                    self.host = host
                    if self._status(j) != 200: self.nodata += 1; j['data'] = None
                    return j
                last = (host, r.status_code, r.text[:200].replace('\n', ' '))
            except QuotaHet: raise
            except Exception as e:  # noqa: BLE001
                last = (host, 'EXC', str(e)[:160])
        self.err += 1; log(f'  LOI {api} {query or form}: {last}'); return None

    def project_price(self, code):
        """dict JSON (data None = mã không có dữ liệu giá) hoặc None (lỗi mạng)"""
        apis = [self.project_api] if self.project_api else PROJECT_PRICE_APIS
        out = None
        for api in apis:
            j = self.call(api, uri_req=code)
            if j is None: continue
            out = j
            if j.get('data') is not None: self.project_api = api; return j
        return out


def save_raw(api, code, j):
    d = os.path.join(BG, 'raw', api); os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f'{re.sub(r"[^A-Za-z0-9_.-]", "_", str(code))[:120]}_{date.today():%Y%m%d}.json')
    json.dump(j, open(p, 'w', encoding='utf-8'), ensure_ascii=False); return p


def _append(path, new: pd.DataFrame, keys):
    if new is None or new.empty: return 0
    if os.path.exists(path): new = pd.concat([pd.read_parquet(path), new], ignore_index=True)
    new = new.drop_duplicates(keys, keep='last')
    os.makedirs(os.path.dirname(path), exist_ok=True); new.to_parquet(path, index=False); return len(new)


# ================================================================ bảng mã (catalog)
def _rows(j):
    d = j.get('data') if isinstance(j, dict) else None
    if d is None: d = j.get('ket_qua') if isinstance(j, dict) else None
    if isinstance(d, dict): d = [d]
    return [lower_keys(x) for x in (d or []) if isinstance(x, dict)]


QUAN_COLS = ['city', 'district', 'uri_req', 'lat', 'lng', 'list_fetched', 'projects_fetched']
CODE_COLS = ['biggee_code', 'ten', 'tinh', 'quan', 'lat', 'lng', 'project_id', 'fetched']


def _csv(path, cols):
    d = pd.read_csv(path, dtype=str).fillna('') if os.path.exists(path) else pd.DataFrame(columns=cols)
    for c in cols:
        if c not in d: d[c] = ''
    return d[cols]


def _cutoff(refresh):
    """mốc 'đã lấy' cho catalog: refresh -> đầu tháng này (quận lấy trước đó phải gọi lại), không -> '' (chỉ quận chưa gọi bao giờ)"""
    return date.today().replace(day=1).isoformat() if refresh else ''


def catalog_todo(refresh=False):
    """(số tỉnh chưa có danh sách quận, số quận chưa gọi getProjectList) theo ma_tinh/ma_quan.csv; chưa có ma_tinh -> (None, None)"""
    if not os.path.exists(P_TINH): return None, None
    cut = _cutoff(refresh); tinh = _csv(P_TINH, ['city', 'uri_req', 'lat', 'lng']); quan = _csv(P_QUAN, QUAN_COLS)
    listed = set(quan[quan['list_fetched'] > cut]['city'])
    n_city = int((~tinh['city'].isin(listed)).sum()); n_dist = int((quan['projects_fetched'] <= cut).sum())
    return n_city, n_dist


def run_catalog(api: Biggee, cities=None, refresh=False):
    """tỉnh -> quận -> dự án, GHI DẦN sau mỗi quận và CHẠY TIẾP được: ma_quan.csv giữ ngày đã gọi getDistrictList (list_fetched) /
    getProjectList (projects_fetched); chỉ gọi phần chưa có (refresh=True: cả phần lấy trước đầu tháng này). Chạm --budget -> QuotaHet
    (đã lưu dở dang) để lần sau tiếp. ma_du_an.csv: upsert theo biggee_code (= uri_req = slug web), giữ cột project_id ghép tay."""
    os.makedirs(BG, exist_ok=True); cut = _cutoff(refresh); today = date.today().isoformat()
    tinh = _csv(P_TINH, ['city', 'uri_req', 'lat', 'lng'])
    if tinh.empty or refresh:
        j = api.call('getCityList')
        if j is None: sys.exit('getCityList không trả dữ liệu -> kiểm tra key/host')
        tinh = pd.DataFrame(_rows(j)); tinh.to_csv(P_TINH, index=False, encoding='utf-8-sig')
    names = tinh['city'].tolist() if 'city' in tinh else []
    if cities: names = [c for c in names if any(nfc_str(c) == nfc_str(x) for x in cities)] or cities
    quan = _csv(P_QUAN, QUAN_COLS); codes = _csv(P_CODES, CODE_COLS)
    nc, nd = catalog_todo(refresh); log(f'tỉnh: {len(tinh)} (lấy {len(names)}); còn {nc} tỉnh chưa có quận, {nd} quận chưa có dự án; hôm nay đã {api.n_day}/{api.budget} request')
    n_new = 0
    try:
        for c in names:
            mine = quan[quan['city'] == c]
            if mine.empty or not (mine['list_fetched'] > cut).any():
                jd = api.call('getDistrictList', form={'city': c}); ds = _rows(jd) if jd else []
                if not ds: continue
                save_raw('getDistrictList', c, jd)
                new = pd.DataFrame(ds); new['city'] = c; new['list_fetched'] = today
                keep = dict(zip(mine['uri_req'], mine['projects_fetched']))           # giữ ngày đã lấy dự án của quận cũ
                new['projects_fetched'] = new['uri_req'].map(keep).fillna('')
                for col in QUAN_COLS:
                    if col not in new: new[col] = ''
                quan = pd.concat([quan[quan['city'] != c], new[QUAN_COLS]], ignore_index=True)
                quan.to_csv(P_QUAN, index=False, encoding='utf-8-sig')
            todo = quan[(quan['city'] == c) & (quan['projects_fetched'] <= cut)]
            for i, dd in todo.iterrows():
                dn = dd['district']; jp = api.call('getProjectList', form={'city': c, 'district': dn})
                if jp is None: continue                                                 # lỗi mạng/API: để lần sau gọi lại
                save_raw('getProjectList', f'{c}_{dn}', jp); ps = pd.DataFrame(_rows(jp))
                if len(ps) >= 100: log(f'  CHU Y {c}/{dn}: {len(ps)} dự án (đúng 100? có thể API cắt trang - xem raw/getProjectList)')
                if len(ps):
                    ps = ps.rename(columns={'uri_req': 'biggee_code', 'project_name': 'ten'})
                    ps['tinh'] = c; ps['quan'] = dn; ps['fetched'] = today
                    for col in CODE_COLS:
                        if col not in ps: ps[col] = ''
                    ps['biggee_code'] = ps['biggee_code'].astype(str).str.strip(); ps = ps[ps['biggee_code'] != '']
                    pid = dict(zip(codes['biggee_code'], codes['project_id']))
                    ps['project_id'] = ps['biggee_code'].map(pid).fillna('')
                    n_new += int((~ps['biggee_code'].isin(codes['biggee_code'])).sum())
                    codes = pd.concat([codes[~codes['biggee_code'].isin(ps['biggee_code'])], ps[CODE_COLS]], ignore_index=True)
                    codes.to_csv(P_CODES, index=False, encoding='utf-8-sig')
                quan.loc[i, 'projects_fetched'] = today; quan.to_csv(P_QUAN, index=False, encoding='utf-8-sig')
            log(f'  {c}: {int((quan["city"] == c).sum())} quận, luỹ kế {len(codes)} dự án (+{n_new} mới), {api.n} request')
    except QuotaHet as e:
        log(f'  HET QUOTA ngày ({e}) -> đã lưu dở dang, lần chạy sau tiếp'); raise
    finally:
        nc, nd = catalog_todo(refresh); web = set(pd.read_parquet(P_LIST)['slug']) if os.path.exists(P_LIST) else set()
        log(f'bảng mã dự án: {len(codes)} mã (+{n_new} mới) -> {P_CODES}; còn {nc} tỉnh / {nd} quận chưa lấy; '
            f'slug bảng giá web có trong bảng mã: {len(web & set(codes["biggee_code"]))}/{len(web)}')
    return len(codes)


# ================================================================ giá dự án
def parse_project(code, j, today):
    d = lower_keys(j.get('data') or j.get('ket_qua') or {})
    dg = d.get('dinhgia') or d.get('ket_qua') or {}
    if isinstance(dg, list): dg = dg[0] if dg else {}
    dg = lower_keys(dg)
    val = {'biggee_code': str(code), 'date': today, 'dongia_tb_thap': num(dg.get('dongia_tb_thap')), 'dongia_tb_cao': num(dg.get('dongia_tb_cao')),
           'dongia_thamkhao': num(dg.get('dongia_thamkhao')), 'dientich_p50': num(dg.get('dientich_p50')), 'giaban_p50': num(dg.get('giaban_p50')),
           'diem_mohinh': num(dg.get('diem_mohinh')), 'chudautu': dg.get('chudautu'), 'diachi_duan': dg.get('diachi_duan'), 'tongdientich': num(dg.get('tongdientich')),
           'api': j.get('_api')}
    hist = []
    for h in d.get('lichsu') or []:
        h = lower_keys(h); m = month(h.get('ngay_xu_ly'))
        if m is None: continue
        hist.append({'slug': str(code), 'month': m, 'untprice': num(h.get('dongia_sosanh')), 'dist_untprice': num(h.get('dongia_quanhuyen')), 'fetched': today})   # schema chung với biggee_web.py
    comps = []
    for c in d.get('sosanh') or []:
        c = lower_keys(c)
        comps.append({'biggee_code': str(code), 'date': today, 'ma_tt': str(c.get('ma_tt')), 'tinh_thanh': c.get('tinh_thanh'), 'quan_huyen': c.get('quan_huyen'),
                      'phuong_xa': c.get('phuong_xa'), 'duong_pho': c.get('duong_pho'), 'du_an': c.get('du_an'), 'giaban': num(c.get('giaban')),
                      'dientich': num(c.get('dientich')), 'sophong': num(c.get('sophong')), 'ngay_dang': c.get('ngay_dang'), 'duongdan': c.get('duongdan')})
    return pd.DataFrame(hist), pd.DataFrame([val]), pd.DataFrame(comps)


def _cat(frames):
    frames = [f for f in frames if f is not None and len(f)]
    return pd.concat(frames, ignore_index=True) if frames else None


def all_codes():
    """mọi mã dự án đã biết: bảng mã API (ma_du_an.csv) ∪ slug bảng giá web ∪ slug đã có lịch sử trong kho"""
    s = set(_csv(P_CODES, CODE_COLS)['biggee_code']) if os.path.exists(P_CODES) else set()
    if os.path.exists(P_LIST): s |= set(pd.read_parquet(P_LIST)['slug'].astype(str))
    if os.path.exists(P_HIST): s |= set(pd.read_parquet(P_HIST)['slug'].astype(str))
    return {c for c in s if c and c != 'nan'}


def run_projects(api: Biggee, limit=None, since=None, codes=None, from_list=False, update=False, missing=False, refresh=False):
    """update=True (hằng tháng): mọi mã all_codes() chưa có định giá lấy từ đầu tháng này, mã CHƯA THỬ bao giờ đi trước; mã đã thử mà API
    không có dữ liệu (dòng định giá api='nodata') chỉ thử lại khi refresh=True (quý). missing=True: chỉ mã chưa có lịch sử trong kho.
    Chạm --budget -> dừng êm, mã còn lại để lần sau."""
    hist = set(pd.read_parquet(P_HIST)['slug'].astype(str)) if os.path.exists(P_HIST) else set()
    if update or missing:
        allc = all_codes(); since = since or date.today().replace(day=1).isoformat()
        val = pd.read_parquet(P_VAL) if os.path.exists(P_VAL) else pd.DataFrame(columns=['biggee_code', 'date', 'api'])
        last = val.sort_values('date').drop_duplicates('biggee_code', keep='last'); tried = set(last['biggee_code'].astype(str))
        nodata = set(last[last['api'].astype(str) == 'nodata']['biggee_code'].astype(str))
        todo = pd.Series(sorted(allc, key=lambda c: (c in tried, c)))                        # chưa thử bao giờ đi trước
        if missing: todo = todo[~todo.isin(hist)]
        if not refresh: todo = todo[~todo.isin(nodata - hist)]
        log(f'--{"update" if update else "missing"}: {len(allc)} mã đã biết, {len(hist)} có lịch sử, {len(tried)} đã thử, {len(nodata)} API không có dữ liệu'
            f'{" (bỏ qua, thử lại khi --refresh-catalog)" if not refresh else " (thử lại)"}; mốc định giá từ {since}')
    elif from_list:                                              # 20/10: mã = slug web trong bảng giá (biggee_web.py) chưa có lịch sử trong kho
        lst = pd.read_parquet(P_LIST)['slug'].drop_duplicates()
        todo = lst[~lst.isin(hist)].reset_index(drop=True); log(f'--from-list: {len(lst)} slug bảng giá, {len(hist)} đã có lịch sử, còn {len(todo)}')
    else:
        if not os.path.exists(P_CODES): sys.exit(f'Thiếu {P_CODES}: chạy --catalog trước (hoặc dùng --from-list / --update)')
        cd = pd.read_csv(P_CODES, dtype=str).fillna('')
        todo = cd['biggee_code'].astype(str).str.strip(); todo = todo[todo != '']
    if codes: todo = todo[todo.isin(codes)]
    if since and os.path.exists(P_VAL):
        done = pd.read_parquet(P_VAL); done = done[done['date'] >= since]['biggee_code'].astype(str); todo = todo[~todo.isin(done)]
    if limit: todo = todo.head(limit)
    todo = todo.reset_index(drop=True); n_todo = len(todo)
    log(f'dự án cần lấy: {n_todo} mã; hôm nay đã {api.n_day}/{api.budget} request')
    today = date.today().isoformat(); H, V, C = [], [], []; ok = 0; i = 0; quota = False
    for i, code in enumerate(todo, 1):
        try: j = api.project_price(code)
        except QuotaHet as e:
            log(f'  HET QUOTA ngày ({e}) -> dừng, còn {n_todo - i + 1} mã để lần sau'); i -= 1; quota = True; break
        if j is None: continue                                                                  # lỗi mạng: lần sau thử lại
        if j.get('data') is None:                                                               # API: mã không có dữ liệu giá -> ghi dấu, không thử lại hằng tháng
            V.append(pd.DataFrame([{'biggee_code': str(code), 'date': today, 'api': 'nodata'}])); continue
        j['_api'] = api.project_api; save_raw(api.project_api, code, j)
        h, v, c = parse_project(code, j, today); H.append(h); V.append(v); C.append(c); ok += 1
        if i % 20 == 0 or i == n_todo: log(f'  {i}/{n_todo} mã, {ok} ok, {api.nodata} không có dữ liệu, {api.err} lỗi, {api.n} request')
        if i % 50 == 0:
            _append(P_HIST, _cat(H), ['slug', 'month']); _append(P_VAL, _cat(V), ['biggee_code', 'date'])
            _append(P_COMP, _cat(C), ['biggee_code', 'date', 'ma_tt']); H, V, C = [], [], []
    nh = _append(P_HIST, _cat(H), ['slug', 'month']); nv = _append(P_VAL, _cat(V), ['biggee_code', 'date']); nc = _append(P_COMP, _cat(C), ['biggee_code', 'date', 'ma_tt'])
    nproj = pd.read_parquet(P_HIST)['slug'].nunique() if os.path.exists(P_HIST) else 0
    log(f'dự án: {ok}/{i} mã ok, {api.nodata} không có dữ liệu (API {api.project_api}), còn {n_todo - i} mã chưa lấy{" (hết quota ngày)" if quota else ""}; '
        f'kho lịch sử {nproj} dự án / {nh or 0} dòng, định giá {nv or 0} dòng, tin so sánh {nc or 0} dòng')
    return ok, n_todo - i


# ================================================================ giá nhà đất theo mã đường
def run_streets(api: Biggee, path, limit=None):
    cd = pd.read_csv(path, dtype=str).fillna(''); cd.columns = [c.lower() for c in cd.columns]
    col = 'uri_req' if 'uri_req' in cd else cd.columns[0]
    todo = cd[col][cd[col] != '']
    if limit: todo = todo.head(limit)
    today = date.today().isoformat(); H, V = [], []; ok = 0
    for code in todo:
        j = api.call('house_price_place', uri_req=code) or api.call('dinhgianhadat', uri_req=code)
        if j is None: continue
        save_raw('house_price_place', code, j); d = lower_keys(j.get('data') or {}); dg = lower_keys(d.get('dinhgia') or d.get('ket_qua') or {})
        dc = d.get('diachi') or dg; dc = lower_keys(dc[0] if isinstance(dc, list) and dc else dc)
        V.append({'uri_req': code, 'date': today, 'dia_chi': dc.get('dia_chi_formatted'), 'tinh_thanh': dc.get('tinh_thanh'), 'quan_huyen': dc.get('quan_huyen'),
                  'phuong_xa': dc.get('phuong_xa'), 'duong_pho': dc.get('duong_pho'), 'lat': num(dc.get('lat')), 'lng': num(dc.get('lng')),
                  'dongia_tb_thap': num(dg.get('dongia_tb_thap') or dg.get('gia_mat_tien_thap')), 'dongia_tb_cao': num(dg.get('dongia_tb_cao') or dg.get('gia_mat_tien_cao')),
                  'dongia_thamkhao': num(dg.get('dongia_thamkhao') or dg.get('gia_mat_tien_tb')), 'dientich_p50': num(dg.get('dientich_p50')), 'giaban_p50': num(dg.get('giaban_p50')),
                  'diem_mohinh': num(dg.get('diem_mohinh')),
                  **{f'hem{k[-1]}_dongia': num(dg.get(k)) for k in dg if re.match(r'gia_hem_l\d_tb$', k)},
                  **{f'hem{lower_keys(h).get("loai_hem")}_dongia': num(lower_keys(h).get('don_gia')) for h in (d.get('dinhgiahem') or []) if lower_keys(h).get('loai_hem')}})
        for h in d.get('lichsu') or []:
            h = lower_keys(h); m = month(h.get('ngay_xu_ly'))
            if m is not None: H.append({'uri_req': code, 'month': m, 'dongia_sosanh': num(h.get('dongia_sosanh')), 'dongia_quanhuyen': num(h.get('dongia_quanhuyen')), 'fetched': today})
        ok += 1
    nh = _append(P_STREET_HIST, pd.DataFrame(H), ['uri_req', 'month']); nv = _append(P_STREET_VAL, pd.DataFrame(V), ['uri_req', 'date'])
    log(f'tuyến đường: {ok}/{len(todo)} ok; lịch sử {nh} dòng, định giá {nv} dòng'); return ok


# ================================================================ ghép mã với batdongsan
def nfc_tokens(s):
    s = unicodedata.normalize('NFD', str(s or '').lower()); s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    return re.sub(r'[^a-z0-9 ]', ' ', s.replace('đ', 'd')).split()


def nfc_str(s): return ' '.join(nfc_tokens(s))


def match_codes():
    """gợi ý ghép mã Biggee <-> project_id batdongsan theo tên (Jaccard token) trong cùng tỉnh -> ma_du_an_goi_y.csv để sửa tay"""
    cd = pd.read_csv(P_CODES, dtype=str).fillna('')
    p = pd.read_parquet(os.path.join(STORE, 'projects.parquet'))[['project_id', 'name', 'address']]
    g = os.path.join(STORE, 'geo_projects.parquet')
    p = p.merge(pd.read_parquet(g)[['project_id', 'city', 'district']], on='project_id', how='left') if os.path.exists(g) else p.assign(city=None, district=None)
    p['tok'] = p['name'].map(lambda x: set(nfc_tokens(x))); p['city_n'] = p['city'].fillna('').map(nfc_str); out = []
    for _, r in cd.iterrows():
        t = set(nfc_tokens(r.get('ten', ''))); cand = p
        if r.get('tinh'):
            m = p['city_n'] == nfc_str(r['tinh']).replace('tp ', '').replace('thanh pho ', '')
            if m.any(): cand = p[m]
        sc = cand['tok'].map(lambda x: len(x & t) / max(1, len(x | t)))
        best = sc.idxmax() if len(sc) and sc.max() > 0 else None
        out.append({**r.to_dict(), 'goi_y_project_id': int(p.at[best, 'project_id']) if best is not None else None,
                    'goi_y_ten': p.at[best, 'name'] if best is not None else None, 'goi_y_quan': p.at[best, 'district'] if best is not None else None,
                    'diem': round(float(sc.max()), 2) if best is not None else 0})
    o = pd.DataFrame(out).sort_values('diem', ascending=False); po = os.path.join(BG, 'ma_du_an_goi_y.csv'); o.to_csv(po, index=False, encoding='utf-8-sig')
    log(f'gợi ý ghép {len(o)} mã -> {po} (điểm >= 0,6 thường đúng; chép cột goi_y_project_id sang project_id trong ma_du_an.csv)')


def load_history():
    """cho app: dùng biggee_web.load_history() (schema chung slug/untprice/dist_untprice + ghép apart_match.csv)"""
    import biggee_web
    return biggee_web.load_history()


# ================================================================ main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--ping', action='store_true'); ap.add_argument('--catalog', action='store_true'); ap.add_argument('--cities', default='')
    ap.add_argument('--test', action='store_true'); ap.add_argument('--projects', action='store_true'); ap.add_argument('--codes', default='')
    ap.add_argument('--streets', default=None); ap.add_argument('--around', nargs=2, type=float, metavar=('LAT', 'LNG')); ap.add_argument('--rad', type=float, default=500)
    ap.add_argument('--kind', default='canho', choices=['canho', 'nhadat']); ap.add_argument('--match', action='store_true')
    ap.add_argument('--from-list', action='store_true', help='20/10: --projects với mã = slug trong store/biggee/apart_price_list.parquet chưa có lịch sử (không cần --catalog)')
    ap.add_argument('--update', action='store_true', help='20/10 tối: bước hằng tháng = bảng mã còn thiếu + lịch sử/định giá mọi mã chưa lấy trong tháng (dừng êm khi hết quota ngày)')
    ap.add_argument('--missing', action='store_true', help='--projects chỉ với mã chưa có lịch sử trong kho (bảng mã ∪ bảng giá web)')
    ap.add_argument('--refresh-catalog', action='store_true', help='--catalog/--update: gọi lại cả quận đã lấy trước đầu tháng này (làm mới bảng mã, ~770 request)')
    ap.add_argument('--budget', type=int, default=950, help='trần request trong NGÀY (quota Biggee 1.000; đếm ở store/biggee/quota.csv)')
    ap.add_argument('--limit', type=int, default=None); ap.add_argument('--since', default=None); ap.add_argument('--delay', type=float, default=0.6)
    ap.add_argument('--probe', metavar='SLUG', help='20/10: gọi thử dinhgiacanho với uri_req = slug web (vd grand-marina-quan-1-ho-chi-minh), in JSON thô + số tháng lịch sử')
    a = ap.parse_args(argv); os.makedirs(BG, exist_ok=True); t0 = time.time()
    if a.match: match_codes(); return 0
    api = Biggee(get_key(), delay=a.delay, budget=a.budget)
    if a.ping:
        j = api.call('getCityList'); print('OK host', api.host, '-', len(_rows(j)), 'tỉnh' if j else 'KHÔNG GỌI ĐƯỢC'); return 0 if j else 1
    if a.probe:
        j = api.project_price(a.probe)
        if j is None: print('KHÔNG GỌI ĐƯỢC (xem LOI ở trên: key sai, host, hoặc IP đang bị biggee.vn chặn 403)'); return 1
        save_raw(api.project_api, a.probe, j); d = j.get('data') or {}
        print('OK host', api.host, 'api', api.project_api, '| khoá data:', list(d.keys())[:20] if isinstance(d, dict) else type(d).__name__)
        for k, v in (d.items() if isinstance(d, dict) else []):
            if isinstance(v, list): print(f'  {k}: list {len(v)} phần tử, đầu: {json.dumps(v[0], ensure_ascii=False)[:300] if v else ""}')
            elif isinstance(v, dict): print(f'  {k}: dict {list(v.keys())[:15]}')
            else: print(f'  {k}: {str(v)[:120]}')
        return 0
    quota = False
    if a.catalog:
        try: run_catalog(api, cities=[c.strip() for c in a.cities.split(',') if c.strip()] or None, refresh=a.refresh_catalog)
        except QuotaHet: quota = True
    if a.test:
        if not os.path.exists(P_CODES): sys.exit('Cần ma_du_an.csv (chạy --catalog) để --test')
        cd = pd.read_csv(P_CODES, dtype=str).fillna(''); code = cd['biggee_code'].iloc[0]
        j = api.project_price(code)
        print(json.dumps(j, ensure_ascii=False, indent=1)[:5000] if j else 'KHÔNG GỌI ĐƯỢC (xem LOI ở trên: key / host / tên API)')
        return 0 if j else 1
    if a.around:
        j = api.call('giacanho_by_radius' if a.kind == 'canho' else 'gianhadat_by_radius', lat=a.around[0], lng=a.around[1], radius=a.rad)
        print(json.dumps(j, ensure_ascii=False, indent=1)[:6000] if j else 'KHÔNG GỌI ĐƯỢC'); return 0 if j else 1
    ok = 0; left = 0
    if a.update:                                                 # bước hằng tháng (run_slot): bảng mã còn thiếu -> dự án chưa lấy tháng này
        nc, nd = catalog_todo(a.refresh_catalog)
        if nc is None or nc or nd or a.refresh_catalog:
            if not quota:
                try: run_catalog(api, refresh=a.refresh_catalog)
                except QuotaHet: quota = True
        else: log('bảng mã: đủ (không còn tỉnh/quận chưa lấy)')
        if not quota:
            n, left = run_projects(api, limit=a.limit, since=a.since, update=True, refresh=a.refresh_catalog); ok += n
        nc, nd = catalog_todo(a.refresh_catalog)
        if left == 0 and not quota and not (nc or nd) and os.path.exists(P_FLAG): os.remove(P_FLAG); log(f'đã xoá {P_FLAG} (hết việc dở)')
        if (left or quota or nc or nd) and not os.path.exists(P_FLAG): open(P_FLAG, 'w').write(date.today().isoformat()); log(f'còn việc -> tạo {P_FLAG} để run_slot chạy tiếp ngày mai')
    elif a.projects:
        n, left = run_projects(api, limit=a.limit, since=a.since, codes=[c.strip() for c in a.codes.split(',') if c.strip()] or None, from_list=a.from_list, missing=a.missing); ok += n
    if a.streets: ok += run_streets(api, a.streets, limit=a.limit)
    if a.projects or a.streets or a.update or a.catalog:
        tail = f', còn {left} mã (hết quota ngày, mai chạy tiếp)' if (left or quota) else ''
        log(f'{"DONE" if (ok or a.catalog or a.update) and api.err < max(3, api.n * 0.3) else "ERROR"} biggee: {api.n} request ({api.n_day}/{api.budget} hôm nay), '
            f'{api.nodata} không có dữ liệu, {api.err} lỗi, {time.time() - t0:.0f}s{tail}')
        return 0 if (ok or a.catalog or a.update) and api.err < max(3, api.n * 0.3) else 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
