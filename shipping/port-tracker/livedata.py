# -*- coding: utf-8 -*-
"""
livedata.py - LỚP DỮ LIỆU TRỰC TIẾP của Port & Vessel Tracker.
App KHÔNG đọc các file events/calls do pipeline parse sẵn nữa. Mỗi lần cần dữ liệu, app gọi thẳng trang nguồn của cảng vụ,
phân tích trong bộ nhớ, rồi lưu vào KHO RIÊNG của app (SQLite: cache/live.sqlite) để không kéo lại ngày đã chốt.

Nguồn gọi trực tiếp (dùng lại đúng hàm scrape của các tool, không qua file):
    HP   csdltau.cangvuhaiphong.gov.vn/pages/ship_plan.aspx?d=N
    HCM  cangvuhanghaitphcm.gov.vn  page=shipschedule (POST ngày) + bảng tra mã cầu chính thức
    QN   kht1.cangvuhanghaiquangninh.gov.vn (từ 2025) ; public-kh Quảng Ninh (trước 2025)
    TBH, THA, HTH, DNG, BTN, DNI, KGG   API public-kh của từng cảng vụ
    NTG  cangvuhanghainhatrang.gov.vn ;  CTO  cangvuhanghaicantho.gov.vn

Quy tắc làm mới:
    - Ngày đã qua > 2 ngày và đã kéo sau mốc đó  -> coi là CHỐT, không kéo lại.
    - Ngày gần đây (hôm nay-2 .. ngày mai)        -> kéo lại nếu bản trong kho cũ hơn TTL (mặc định 30 phút).
    - Ngày chưa có trong kho                       -> kéo từ nguồn (tự động tối đa `max_pages` trang / cảng vụ / lần mở).
Khởi tạo: lần đầu, kho được nạp 1 LẦN từ lịch sử đã có (seed_from_local) để khỏi kéo lại ~8 năm; sau đó mọi cập nhật là trực tiếp.

Kho chia sẻ store/ (09/10/2026, mô hình cloud): pipeline (bước port-tracker trong run_slot.py: GitHub Actions 9:00 + 22:00 cho 11 cảng vụ,
laptop 8:30 + 18:40 cho TP.HCM) gọi nguồn qua pt_update.py rồi XUẤT sqlite -> store/events/<cảng vụ>/<YYYY-MM>.parquet + store/days/<cảng vụ>.csv
(mỗi file 1 cảng vụ 1 tháng, ~0,5 MB) để rclone đồng bộ Google Drive. App khi mở chỉ NẠP các file đổi (import_store) vào sqlite của mình,
không cần gọi nguồn nữa (vẫn kéo được bằng tay).
"""
import os, re, sqlite3, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import pandas as pd
import requests

APP = os.path.dirname(os.path.abspath(__file__)); HUB = os.path.dirname(APP)
for p in ('cangvu-haiphong', 'cangvu-hcm', 'cangvu-toanquoc'):
    sys.path.insert(0, os.path.join(HUB, p))
import cvhp_scrape as hp            # noqa: E402
import cvhcm_scrape as hcm          # noqa: E402
import pkh_scrape as pkh            # noqa: E402
import aspx_scrape as asx           # noqa: E402

DB = os.environ.get('PORT_TRACKER_DB') or os.path.join(APP, 'cache', 'live.sqlite')
COLS = ['auth', 'src', 'plan_date', 'section', 'time', 'ship', 'ship_key', 'imo', 'callsign', 'flag', 'is_sb', 'draft', 'loa', 'dwt', 'gt',
        'cargo_type', 'cargo_qty', 'from_raw', 'to_raw', 'b_from', 'b_to', 'region', 'channel', 'agent', 'tugs', 'itinerary_no', 'rec_id',
        'fetched_at']
NUM = ('draft', 'loa', 'dwt', 'gt', 'cargo_qty')
PKH = {r['code']: r for r in hp.read_csv(os.path.join(HUB, 'cangvu-toanquoc', 'authorities.csv')) if r['platform'] == 'pkh'}
AUTHS = ['QN', 'HP', 'TBH', 'THA', 'HTH', 'DNG', 'NTG', 'BTN', 'DNI', 'HCM', 'CTO', 'KGG']           # bắc -> nam
START = {'HP': '2019-01-01', 'HCM': '2019-01-01', 'QN': '2020-01-01', 'NTG': '2019-01-01', 'CTO': '2021-01-01'}   # mặc định pkh: 2020-01-01
QN_CUT = date(2025, 4, 14)          # Quảng Ninh chuyển dần public-kh -> kht1 trong 04/2025; từ 14/04 kht1 nhiều bản ghi hơn
_lock = threading.Lock()
STORE = os.environ.get('PORT_TRACKER_STORE') or os.path.join(APP, 'store')      # kho chia sẻ (parquet) đồng bộ Drive
_dirty = set()                      # (auth, 'YYYY-MM') đã ghi vào sqlite trong tiến trình này -> export_store() xuất lại
FAILED = {}                         # cảng vụ vừa gọi lỗi -> thời điểm; tự kéo sẽ bỏ qua trong COOLDOWN phút
COOLDOWN = 5


def log(*a): print(datetime.now().strftime('%H:%M:%S'), '[live]', *a, flush=True)


# ================================================================ KHO
def conn():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    c = sqlite3.connect(DB, timeout=60, check_same_thread=False)
    c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA synchronous=NORMAL')
    c.execute(f'CREATE TABLE IF NOT EXISTS events ({", ".join(k + (" REAL" if k in NUM else " TEXT") for k in COLS)})')
    c.execute('CREATE INDEX IF NOT EXISTS ix_ev ON events(auth, plan_date)')
    c.execute('CREATE INDEX IF NOT EXISTS ix_ship ON events(ship_key)')
    c.execute('CREATE TABLE IF NOT EXISTS days (auth TEXT, plan_date TEXT, fetched_at TEXT, n INTEGER, src TEXT, PRIMARY KEY(auth, plan_date))')
    c.execute('CREATE TABLE IF NOT EXISTS details (auth TEXT, itinerary_no TEXT, last_port TEXT, next_port TEXT, previous_ports TEXT, '
              'cargo TEXT, ship_owner TEXT, fetched_at TEXT, PRIMARY KEY(auth, itinerary_no))')
    c.execute('CREATE TABLE IF NOT EXISTS vessel_live (ship_key TEXT PRIMARY KEY, ship TEXT, imo TEXT, mmsi TEXT, vessel_class TEXT, teu REAL, '
              'built TEXT, source TEXT, fetched_at TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)')
    return c


def version():
    """đổi mỗi khi kho có dữ liệu mới -> khoá cache của app"""
    with conn() as c:
        r = c.execute('SELECT COUNT(*), MAX(fetched_at) FROM days').fetchone()
        d = c.execute('SELECT COUNT(*) FROM details').fetchone()[0]
    return f'{r[0]}|{r[1]}|{d}'


def version_before(auths, day):
    """phiên bản của phần lịch sử (plan_date < day): chỉ đổi khi kéo bù / nạp lại lịch sử, không đổi khi làm mới ngày gần đây"""
    with conn() as c:
        r = c.execute(f'SELECT COUNT(*), MAX(fetched_at) FROM days WHERE plan_date<? AND auth IN ({",".join("?" * len(auths))})',
                      [str(day)[:10]] + list(auths)).fetchone()
        d = c.execute('SELECT COUNT(*) FROM details').fetchone()[0]
    return f'{r[0]}|{r[1]}|{d}'


def is_empty():
    with conn() as c: return c.execute('SELECT COUNT(*) FROM days').fetchone()[0] == 0


def put_day(auth, d, events, src):
    rows = [tuple(e.get(k) if e.get(k) != '' or k not in NUM else None for k in COLS) for e in events]
    with _lock, conn() as c:
        c.execute('DELETE FROM events WHERE auth=? AND plan_date=?', (auth, d))
        ids = [e['rec_id'] for e in events if e.get('rec_id')]
        for i in range(0, len(ids), 500):                                     # bản ghi public-kh bị dời ngày: xoá bản cũ theo id
            c.execute(f'DELETE FROM events WHERE auth=? AND rec_id IN ({",".join("?" * len(ids[i:i + 500]))})', [auth] + ids[i:i + 500])
        c.executemany(f'INSERT INTO events VALUES ({",".join("?" * len(COLS))})', rows)
        c.execute('INSERT OR REPLACE INTO days VALUES (?,?,?,?,?)', (auth, d, datetime.now().strftime('%Y-%m-%d %H:%M'), len(rows), src))
    _dirty.add((auth, d[:7]))


def coverage():
    with conn() as c:
        return pd.read_sql('SELECT auth, COUNT(*) AS so_ngay, MIN(plan_date) AS tu_ngay, MAX(plan_date) AS den_ngay, SUM(n) AS so_su_kien, '
                           'MAX(fetched_at) AS keo_gan_nhat FROM days GROUP BY auth', c)


def suspicious(dwt, gt, loa):
    """DWT không hợp lý so với kích thước tàu -> nguồn gõ nhầm (vd 125.221.252 DWT, hay 749.980 DWT cho tàu 3.384 GT).
    Ngưỡng: > 450.000 DWT; hoặc > 4 lần GT; hoặc (khi không có GT) > 0,03 x LOA^3."""
    dwt = pd.to_numeric(dwt, errors='coerce'); gt = pd.to_numeric(gt, errors='coerce'); loa = pd.to_numeric(loa, errors='coerce')
    ok_loa = loa.between(15, 460)
    return (dwt > 450000) | (gt.gt(50) & (dwt > 4 * gt + 500)) | (~gt.gt(50) & ok_loa & (dwt > 0.03 * loa ** 3))


_REF = {'t': None, 'ref': None}


def ship_ref(force=False):
    """DWT / LOA chuẩn của từng tàu = trung vị các bản ghi hợp lý trong toàn kho. Tính lại tối đa 6 giờ 1 lần."""
    if not force and _REF['ref'] is not None and (datetime.now() - _REF['t']) < timedelta(hours=6): return _REF['ref']
    with conn() as c:
        df = pd.read_sql('SELECT ship_key, dwt, gt, loa FROM events WHERE dwt IS NOT NULL', c)
    df = df[~suspicious(df['dwt'], df['gt'], df['loa'])]
    df.loc[~df['loa'].between(15, 460), 'loa'] = None
    _REF['ref'] = df.groupby('ship_key')[['dwt', 'loa']].median(); _REF['t'] = datetime.now()
    return _REF['ref']


def clean(ev):
    """thay DWT/LOA gõ nhầm bằng trị chuẩn của chính tàu đó (không có thì để trống); cột dwt_raw giữ số gốc"""
    if ev.empty: return ev
    ref = ship_ref(); ev = ev.copy(); ev['dwt_raw'] = ev['dwt']
    bad = suspicious(ev['dwt'], ev['gt'], ev['loa'])
    if bad.any(): ev.loc[bad, 'dwt'] = ev.loc[bad, 'ship_key'].map(ref['dwt'])
    bl = ev['loa'].notna() & ~ev['loa'].between(15, 460)
    if bl.any(): ev.loc[bl, 'loa'] = ev.loc[bl, 'ship_key'].map(ref['loa'])
    return ev


def load_events(auths, d0, d1, raw=False):
    q = f'SELECT * FROM events WHERE auth IN ({",".join("?" * len(auths))}) AND plan_date>=? AND plan_date<=?'
    with conn() as c:
        ev = pd.read_sql(q, c, params=list(auths) + [str(d0)[:10], str(d1)[:10]])
    return ev if raw else clean(ev)


def load_ship_events(ship_key):
    with conn() as c:
        return clean(pd.read_sql('SELECT * FROM events WHERE ship_key=?', c, params=[ship_key]))


# ================================================================ KHO CHIA SẺ store/ (parquet theo cảng vụ + tháng, đồng bộ Drive)
def _ev_path(auth, ym): return os.path.join(STORE, 'events', auth, f'{ym}.parquet')
def _days_path(auth): return os.path.join(STORE, 'days', f'{auth}.csv')


def _sig(path):
    st = os.stat(path); return f'{st.st_size}|{st.st_mtime_ns}'


def export_store(pairs=None, auths=None):
    """sqlite -> store/: events/<auth>/<YYYY-MM>.parquet (1 file = 1 cảng vụ, 1 tháng) + days/<auth>.csv (toàn bộ ngày của cảng vụ).
    pairs=None: xuất toàn bộ kho (seed lần đầu). Trả về số file parquet đã ghi."""
    with conn() as c:
        if pairs is None:
            pairs = {(a, ym) for a, ym in c.execute("SELECT DISTINCT auth, substr(plan_date, 1, 7) FROM events")}
        pairs = {(a, ym) for a, ym in pairs if not auths or a in auths}
        n = 0
        for a, ym in sorted(pairs):
            ev = pd.read_sql('SELECT * FROM events WHERE auth=? AND plan_date LIKE ?', c, params=[a, ym + '%'])
            p = _ev_path(a, ym); os.makedirs(os.path.dirname(p), exist_ok=True)
            if ev.empty:
                if os.path.exists(p): os.remove(p)
                c.execute("DELETE FROM meta WHERE k=?", (f'imp:{a}/{ym}',)); continue
            ev.to_parquet(p + '.tmp', index=False, compression='zstd'); os.replace(p + '.tmp', p)
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (f'imp:{a}/{ym}', _sig(p))); n += 1
        for a in sorted({a for a, _ in pairs}):
            d = pd.read_sql('SELECT auth, plan_date, fetched_at, n, src FROM days WHERE auth=? ORDER BY plan_date', c, params=[a])
            p = _days_path(a); os.makedirs(os.path.dirname(p), exist_ok=True)
            d.to_csv(p + '.tmp', index=False, encoding='utf-8'); os.replace(p + '.tmp', p)
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (f'impd:{a}', _sig(p)))
    _dirty.difference_update(pairs)
    return n


def store_files(auths=None, since=None):
    """[(auth, 'YYYY-MM', đường dẫn)] các file parquet có trong store/ (since='YYYY-MM': bỏ tháng cũ hơn)."""
    root = os.path.join(STORE, 'events'); out = []
    if not os.path.isdir(root): return out
    for a in sorted(os.listdir(root)):
        d = os.path.join(root, a)
        if (auths and a not in auths) or not os.path.isdir(d): continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith('.parquet') and (not since or fn[:7] >= since): out.append((a, fn[:-8], os.path.join(d, fn)))
    return out


def import_store(since=None, auths=None, progress=None):
    """store/ -> sqlite: nạp các file parquet MỚI/ĐỔI so với lần nạp trước (chữ ký size|mtime trong bảng meta) + days/<auth>.csv.
    Mỗi file thay trọn 1 cảng vụ-tháng trong sqlite. Trả về (số file events nạp, số cảng vụ nạp days)."""
    files = store_files(auths, since)
    if not files and not os.path.isdir(os.path.join(STORE, 'days')): return 0, 0
    with conn() as c:
        have = dict(c.execute("SELECT k, v FROM meta WHERE k LIKE 'imp%'").fetchall())
    todo = [(a, ym, p) for a, ym, p in files if have.get(f'imp:{a}/{ym}') != _sig(p)]
    n = 0; touched = set()
    for i, (a, ym, p) in enumerate(todo, 1):
        if progress: progress(i, len(todo), a, ym)
        try: ev = pd.read_parquet(p).reindex(columns=COLS)
        except Exception as e: log('store loi', p, e); continue
        with _lock, conn() as c:
            c.execute('DELETE FROM events WHERE auth=? AND plan_date LIKE ?', (a, ym + '%'))
            ev.to_sql('events', c, if_exists='append', index=False)
            c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (f'imp:{a}/{ym}', _sig(p)))
        n += 1; touched.add(a)
    nd = 0; droot = os.path.join(STORE, 'days')
    if os.path.isdir(droot):
        for fn in sorted(os.listdir(droot)):
            a = fn[:-4]
            if not fn.endswith('.csv') or (auths and a not in auths): continue
            p = os.path.join(droot, fn)
            if have.get(f'impd:{a}') == _sig(p) and a not in touched: continue
            d = pd.read_csv(p, dtype=str, keep_default_na=False)
            with _lock, conn() as c:
                c.executemany('INSERT OR REPLACE INTO days VALUES (?,?,?,?,?)',
                              [(a, r.plan_date, r.fetched_at, int(float(r.n or 0)), r.src) for r in d.itertuples()])
                c.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (f'impd:{a}', _sig(p)))
            nd += 1
    if n: _REF['ref'] = None                                   # DWT/LOA chuẩn tính lại
    return n, nd


def store_status():
    """{'files': số parquet, 'latest': fetched_at mới nhất trong days/*.csv, 'auths': số cảng vụ} - để app hiện tình trạng kho chia sẻ."""
    files = store_files(); latest = ''; droot = os.path.join(STORE, 'days'); na = 0
    if os.path.isdir(droot):
        for fn in os.listdir(droot):
            if not fn.endswith('.csv'): continue
            na += 1
            try: latest = max(latest, pd.read_csv(os.path.join(droot, fn), usecols=['fetched_at'], dtype=str)['fetched_at'].max() or '')
            except Exception: pass
    return {'files': len(files), 'latest': latest, 'auths': na}


# ================================================================ GỌI NGUỒN
def _std(e, auth, src, frm=None, to=None):
    o = {k: e.get(k, '') for k in COLS}
    o.update({'auth': auth, 'src': src, 'from_raw': e.get('from', ''), 'to_raw': e.get('to', ''),
              'b_from': e.get('from', '') if frm is None else frm, 'b_to': e.get('to', '') if to is None else to})
    for k in NUM:
        try: o[k] = float(o[k]) if o[k] not in ('', None) else None
        except (TypeError, ValueError): o[k] = None
    if o['dwt'] and o['dwt'] > 550000: o['dwt'] = None            # nguồn gõ nhầm (vd 2.440.521 cho tàu 24.405 DWT)
    o['is_sb'] = str(o.get('is_sb') or 0)
    return o


class Source:
    """1 đối tượng / cảng vụ / luồng: giữ session + trạng thái POST-back."""
    def __init__(self, auth):
        self.auth = auth; self.now = datetime.now().strftime('%Y-%m-%d %H:%M')
        if auth == 'HP': self.sess = hp.make_session()
        elif auth == 'HCM': self.f = hcm.Fetcher(); self.rules = hcm.load_berth_rules()
        elif auth == 'QN': self.kht = asx.QNK(); self.host = pkh.Host(PKH['QNH'])
        elif auth in ('NTG', 'CTO'): self.site = asx.SITES[auth]()
        else: self.host = pkh.Host(PKH[auth])

    def _pkh(self, host, d, auth):
        out = []
        for sec, fn in (('Vao', host.come), ('Roi', host.leave), ('DiChuyen', host.shifting)):
            rows = fn(d)
            if rows is None: raise RuntimeError(f'public-kh {sec} that bai')
            for r in rows:
                e = pkh.to_event(auth, sec, r, self.now)
                if e and e['plan_date'] == d.isoformat(): out.append(_std(e, auth, 'public-kh'))
        return out, 'public-kh'

    def fetch(self, d):
        a = self.auth
        if a == 'HP':
            html = hp.fetch_date(self.sess, d, date.today())
            if html is None: raise RuntimeError('khong lay duoc trang csdltau')
            return [_std(e, a, 'csdltau') for e in hp.parse_page(html, d, self.now)], 'csdltau'
        if a == 'HCM':
            html = self.f.fetch(d)
            if html is None: raise RuntimeError('khong lay duoc trang shipschedule')
            evs = hcm.parse_page(html, d, self.now, self.rules)
            return [_std(e, a, 'shipschedule', frm=e['terminal_from'] or e['from'], to=e['terminal_to'] or e['to']) for e in evs], 'shipschedule'
        if a == 'QN':
            if d >= QN_CUT: return [_std(e, a, 'kht1') for e in self.kht.fetch(d, self.now)], 'kht1'
            return self._pkh(self.host, d, a)
        if a in ('NTG', 'CTO'):
            return [_std(e, a, 'aspx') for e in self.site.fetch(d, self.now)], 'aspx'
        return self._pkh(self.host, d, a)


def start_of(auth): return date.fromisoformat(START.get(auth, '2020-01-01'))


def plan(auths, d0, d1, ttl_min=30):
    """{auth: [ngày cần kéo]} theo quy tắc chốt / TTL. Ngày mới nhất trước."""
    today = date.today(); now = datetime.now()
    d1 = min(pd.Timestamp(d1).date(), today + timedelta(days=1)); d0 = pd.Timestamp(d0).date()
    with conn() as c:
        have = {(a, d): f for a, d, f in c.execute('SELECT auth, plan_date, fetched_at FROM days')}
    out = {}
    for a in auths:
        need = []; d = d1; lo = max(d0, start_of(a))
        while d >= lo:
            f = have.get((a, d.isoformat()))
            if f is None: need.append(d)
            else:
                ft = datetime.strptime(f, '%Y-%m-%d %H:%M')
                final = ft.date() >= d + timedelta(days=2)
                if not final and (now - ft) > timedelta(minutes=ttl_min): need.append(d)
            d -= timedelta(days=1)
        if need: out[a] = need
    return out


def cooling(auth):
    t = FAILED.get(auth)
    return bool(t) and (datetime.now() - t) < timedelta(minutes=COOLDOWN)


def ensure(auths, d0, d1, ttl_min=30, max_pages=40, progress=None, todo=None, skip_cooling=False):
    """Kéo trực tiếp từ nguồn các ngày thiếu/cũ. Mỗi cảng vụ 1 luồng (máy chủ khác nhau). Trả về (số trang đã kéo, lỗi).
    skip_cooling=True (tự kéo khi mở app): bỏ qua cảng vụ vừa lỗi trong 5 phút gần đây để không treo giao diện vì nguồn đang sập."""
    todo = todo if todo is not None else plan(auths, d0, d1, ttl_min)
    if skip_cooling: todo = {a: ds for a, ds in todo.items() if not cooling(a)}
    todo = {a: ds[:max_pages] if max_pages else ds for a, ds in todo.items()}
    total = sum(len(v) for v in todo.values()); done = [0]; errors = []
    if not total: return 0, errors

    def work(a, ds):
        try: s = Source(a)
        except Exception as e:
            errors.append(f'{a}: khong khoi tao duoc nguon ({str(e)[:80]})'); FAILED[a] = datetime.now(); return
        bad = 0
        for d in ds:
            try:
                evs, src = s.fetch(d); put_day(a, d.isoformat(), evs, src); bad = 0
            except Exception as e:
                errors.append(f'{a} {d}: {str(e)[:90]}'); bad += 1; FAILED[a] = datetime.now()
                if bad >= 2: errors.append(f'{a}: dung sau 2 loi lien tiep, thu lai sau {COOLDOWN} phut'); break
            done[0] += 1
            if progress: progress(done[0], total, a, d)
            time.sleep(0.15)

    with ThreadPoolExecutor(max_workers=max(1, len(todo))) as ex:
        for f in as_completed([ex.submit(work, a, ds) for a, ds in todo.items()]): f.result()
    return done[0], errors


# ================================================================ KHỞI TẠO KHO TỪ LỊCH SỬ ĐÃ CÓ (1 lần)
def seed_from_local(progress=None, only=None):
    """Nạp lịch sử đã parse sẵn vào kho của app để khỏi kéo lại nhiều năm. Chỉ chạy khi người dùng bấm hoặc kho trống."""
    nat = os.path.join(HUB, 'cangvu-toanquoc', 'data')
    jobs = [('HP', 'csdltau', os.path.join(HUB, 'cangvu-haiphong', 'data', 'cvhp_events.csv')),
            ('HCM', 'shipschedule', os.path.join(HUB, 'cangvu-hcm', 'data', 'cvhcm_events.csv')),
            ('QN', 'public-kh', os.path.join(nat, 'QNH', 'events.csv')), ('QN', 'kht1', os.path.join(nat, 'QNK', 'events.csv'))]
    jobs += [(c, 'public-kh', os.path.join(nat, c, 'events.csv')) for c in ('TBH', 'THA', 'HTH', 'DNG', 'BTN', 'DNI', 'KGG')]
    jobs += [(c, 'aspx', os.path.join(nat, c, 'events.csv')) for c in ('NTG', 'CTO')]
    if only: jobs = [j for j in jobs if j[0] in only]
    n_all = 0; maxday = (date.today() + timedelta(days=1)).isoformat()
    for i, (auth, src, path) in enumerate(jobs, 1):
        if progress: progress(i, len(jobs), auth, src)
        if not os.path.exists(path): continue
        for ch in pd.read_csv(path, encoding='utf-8-sig', dtype=str, keep_default_na=False, chunksize=150000):
            ch = ch[(ch['plan_date'] >= '2015-01-01') & (ch['plan_date'] <= maxday)]
            if auth == 'QN': ch = ch[ch['plan_date'] < QN_CUT.isoformat()] if src == 'public-kh' else ch[ch['plan_date'] >= QN_CUT.isoformat()]
            if ch.empty: continue
            df = pd.DataFrame({k: ch[k] if k in ch else '' for k in COLS})
            df['auth'] = auth; df['src'] = src; df['from_raw'] = ch['from']; df['to_raw'] = ch['to']
            if 'terminal_from' in ch:
                df['b_from'] = ch['terminal_from'].where(ch['terminal_from'] != '', ch['from']); df['b_to'] = ch['terminal_to'].where(ch['terminal_to'] != '', ch['to'])
            else:
                df['b_from'] = ch['from']; df['b_to'] = ch['to']
            df['ship_key'] = df['ship'].map(hp.ship_key)
            for k in NUM: df[k] = pd.to_numeric(df[k], errors='coerce')
            days = ch.groupby('plan_date').agg(n=('ship', 'size'), f=('fetched_at', 'max')).reset_index()
            with _lock, conn() as c:
                c.executemany('DELETE FROM events WHERE auth=? AND plan_date=?', [(auth, d) for d in days['plan_date']])
                df[COLS].to_sql('events', c, if_exists='append', index=False)
                c.executemany('INSERT OR REPLACE INTO days VALUES (?,?,?,?,?)',
                              [(auth, r.plan_date, (r.f if re.match(r'\d{4}-\d\d-\d\d \d\d:\d\d', r.f or '') else '2026-09-29 00:00'), int(r.n), src)
                               for r in days.itertuples()])
            n_all += len(df)
        with _lock, conn() as c:                                    # ngày trống trong khoảng nguồn đã quét -> ghi nhận n=0
            r = c.execute('SELECT MIN(plan_date), MAX(plan_date) FROM days WHERE auth=? AND src=?', (auth, src)).fetchone()
            if r and r[0]:
                lo = max(date.fromisoformat(r[0]), start_of(auth)) if src != 'public-kh' else start_of(auth)
                if auth == 'QN' and src == 'kht1': lo = QN_CUT
                hi = date.fromisoformat(r[1])
                if auth == 'QN' and src == 'public-kh': hi = QN_CUT - timedelta(days=1)
                have = {x[0] for x in c.execute('SELECT plan_date FROM days WHERE auth=?', (auth,))}
                d = lo; add = []; run = []
                while d <= hi:
                    if d.isoformat() in have:
                        if src == 'public-kh' or len(run) <= 10: add.extend(run)      # nguồn HTML: khoảng trống > 10 ngày = chưa từng kéo
                        run = []
                    else: run.append((auth, d.isoformat(), '2026-09-29 00:00', 0, src))
                    d += timedelta(days=1)
                c.executemany('INSERT OR IGNORE INTO days VALUES (?,?,?,?,?)', add)
    with conn() as c: c.execute("INSERT OR REPLACE INTO meta VALUES ('seeded', ?)", (datetime.now().strftime('%Y-%m-%d %H:%M'),))
    return n_all


# ================================================================ GHÉP CHUYẾN TRONG BỘ NHỚ
def build_calls(ev):
    """events (DataFrame từ kho) -> DataFrame chuyến. public-kh ghép theo mã chuyến, nguồn khác ghép theo chuỗi tên tàu."""
    if ev.empty: return pd.DataFrame()
    out = []
    ev = ev.rename(columns={'b_from': 'from', 'b_to': 'to'}).fillna({'time': '', 'ship': '', 'ship_key': '', 'from': '', 'to': '', 'agent': '', 'itinerary_no': '',
                                                  'imo': '', 'callsign': '', 'flag': '', 'is_sb': '0'})
    for k in ('dwt', 'gt', 'loa'): ev[k] = ev[k].where(ev[k].notna(), '')
    det = details_map()
    for (auth, src), g in ev.groupby(['auth', 'src'], sort=False):
        recs = g.to_dict('records')
        if src == 'public-kh':
            calls = pkh.build_calls(recs, {k[1]: v for k, v in det.items() if k[0] == auth})
        else:
            calls = hp.build_calls([r for r in recs if r['section'] in hp.SEC_ORDER])
            for c in calls: c['imo'] = ''
        for c in calls: c['auth'] = auth; c['src'] = src
        out.extend(calls)
    df = pd.DataFrame(out)
    if df.empty: return df
    df['arrival'] = pd.to_datetime(df['arrival'], errors='coerce'); df['departure'] = pd.to_datetime(df['departure'], errors='coerce')
    for k in ('dwt', 'gt', 'loa', 'hours_in_port', 'n_shifts'): df[k] = pd.to_numeric(df[k], errors='coerce')
    for k in ('origin', 'destination', 'berths', 'first_berth', 'agent', 'status', 'imo'): df[k] = df[k].fillna('')
    return df


# ================================================================ CHI TIẾT CHUYẾN (cảng trước / cảng kế) - gọi trực tiếp khi cần
def details_map():
    with conn() as c:
        return {(a, i): {'last_port': lp, 'next_port': np_, 'cargo_remaining': cg}
                for a, i, lp, np_, cg in c.execute('SELECT auth, itinerary_no, last_port, next_port, cargo FROM details')}


def fetch_details(auth, itinerary_nos, limit=25):
    code = 'QNH' if auth == 'QN' else auth
    if code not in PKH: return 0
    with conn() as c:
        have = {r[0] for r in c.execute('SELECT itinerary_no FROM details WHERE auth=?', (auth,))}
    todo = [i for i in itinerary_nos if i and i not in have][:limit]
    if not todo: return 0
    host = pkh.Host(PKH[code]); now = datetime.now().strftime('%Y-%m-%d %H:%M'); n = 0
    for ino in todo:
        rows = host.detail(ino)
        if rows is None: continue
        a = next((r for r in rows if r.get('noticeShipType') == 1), {}); d = next((r for r in rows if r.get('noticeShipType') == 2), {})
        with _lock, conn() as c:
            c.execute('INSERT OR REPLACE INTO details VALUES (?,?,?,?,?,?,?,?)',
                      (auth, ino, pkh.clean(a.get('lastPortOfCallCode')), pkh.clean(d.get('portGoingToCode') or a.get('portGoingToCode')),
                       pkh.clean(a.get('previousPortsOfCall')), pkh.clean(a.get('remainingCargo')), pkh.clean(a.get('shipOwnersName')), now))
        n += 1; time.sleep(0.4)
    return n


# ================================================================ THÔNG SỐ TÀU - tra trực tuyến khi cần
def vessel_live():
    with conn() as c: return pd.read_sql('SELECT * FROM vessel_live', c)


def lookup_vessel(ship_key, name, dwt=None, gt=None, imo=''):
    """IMO (BalticShipping -> VesselFinder) + TEU/loại tàu (Flexport Atlas). Ghi vào kho vessel_live."""
    import vessel_enrich as ve
    s = requests.Session(); out = {'ship_key': ship_key, 'ship': name, 'imo': imo or '', 'mmsi': '', 'vessel_class': '', 'teu': None, 'built': '', 'source': ''}
    src = []
    if not out['imo']:
        try:
            c, how = ve.bs_match(ve.bs_search(s, name), name, dwt, gt)
            if c:
                out['imo'] = str(c.get('imo') or ''); out['mmsi'] = str(c.get('mmsi') or ''); src.append('balticshipping')
                out['vessel_class'] = ve.BS_TYPE.get(int(c['type']), '') if c.get('type') else ''
        except Exception as e: log('bs', e)
    if not out['imo']:
        try:
            v, how = ve.bs_match(ve.vf_search(s, name), name, dwt, gt)
            if v:
                out['imo'] = v['imo']; out['mmsi'] = v['mmsi']; out['built'] = v['built']; src.append('vesselfinder')
                out['vessel_class'] = ve.VF_TYPE.get((v['type'] or '').lower(), out['vessel_class'])
        except Exception as e: log('vf', e)
    if out['imo']:
        try:
            p = ve.flexport_props(s, out['imo'], out['mmsi'])
            if p.get('TEU Capacity'): out['teu'] = float(p['TEU Capacity']); src.append('flexport')
            if p.get('Ship Type') in ve.FLEXPORT_TYPE: out['vessel_class'] = ve.FLEXPORT_TYPE[p['Ship Type']]
            if p.get('Year Built'): out['built'] = str(p['Year Built'])
        except Exception as e: log('flexport', e)
    out['source'] = '+'.join(src); out['fetched_at'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    with _lock, conn() as c:
        c.execute('INSERT OR REPLACE INTO vessel_live VALUES (?,?,?,?,?,?,?,?,?)', tuple(out[k] for k in
                  ('ship_key', 'ship', 'imo', 'mmsi', 'vessel_class', 'teu', 'built', 'source', 'fetched_at')))
    return out
