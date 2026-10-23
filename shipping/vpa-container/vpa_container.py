# -*- coding: utf-8 -*-
r"""
vpa_container.py - gom báo cáo SẢN LƯỢNG CONTAINER hằng tháng của Hiệp hội Cảng biển VN (VPA) thành 1 bảng dài (16/10/2026).

Đầu vào: file Excel VPA, mỗi sheet "T<m>-<yyyy>" = 1 tháng, cột (từ cột A):
  KHU VỰC / Cảng | Năm <yyyy-1> | <m>T<yyyy-1> (lũy kế cùng kỳ) | <m>T-<yyyy> (lũy kế) | THÁNG <m>: CỘNG | Nhập ngoại | Xuất ngoại |
  Nhập nội | Xuất nội | Trung chuyển | 20' | Rỗng | Lạnh | GN qua sà lan | tỷ lệ
Đầu ra (data/):
  vpa_container_long.csv  : 1 dòng = cảng × tháng: region, port, month (cuối tháng), teu, nguon (thang | luy_ke_cung_ky | luy_ke),
                            nhap_ngoai, xuat_ngoai, nhap_noi, xuat_noi, trung_chuyen, teu20, rong, lanh, sa_lan, canh_bao
  vpa_container_wide.xlsx : cảng × tháng (TEU) + sheet Năm (cả năm năm trước theo báo cáo)
Tháng năm trước (vd T1–T7/2025) suy từ chênh lệch cột lũy kế cùng kỳ giữa 2 sheet liền nhau.
Tháng năm nay: cột CỘNG; nếu trống/0 mà lũy kế tăng thì lấy chênh lệch lũy kế (VPA đôi khi chỉ điền lũy kế, vd Nam Hải Đình Vũ T1/2026).
Cảng trùng tên trong 1 sheet (vd Nam Hải Đình Vũ 2 dòng) -> giữ dòng có số lớn nhất.

    python vpa_container.py <file.xlsx> [file2.xlsx ...]      # gộp nhiều file (tháng sau ghi đè tháng trước)
    python vpa_container.py --targets                          # + cập nhật D:\shipping\port-tracker\nowcast_targets.csv
"""
import argparse
import glob
import os
import re
import sys
import unicodedata

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'data')
TARGETS = os.path.join(os.path.dirname(HERE), 'port-tracker', 'nowcast_targets.csv')
# 21/10/2026: kho dữ liệu cục bộ D:\shipping\port-tracker\store đã xoá (bản online đọc Drive) -> chia khối theo EconDB / lịch tàu đọc kho laptop đồng bộ
_PD_STORE = r'D:\pipeline-data\shipping\port-tracker\store'
if os.path.isdir(_PD_STORE): os.environ.setdefault('PORT_TRACKER_STORE', _PD_STORE)
COLS = ['year_prev', 'cum_prev', 'cum_cur', 'teu', 'nhap_ngoai', 'xuat_ngoai', 'nhap_noi', 'xuat_noi', 'trung_chuyen', 'teu20', 'rong', 'lanh', 'sa_lan']
CANG_VU = '__CANG_VU__'           # dòng tổng cảng vụ trong nowcast_targets (cộng các cảng VPA của cảng vụ)
REGIONS = ('MIỀN BẮC', 'BẮC TRUNG BỘ', 'NAM TRUNG BỘ', 'ĐÔNG NAM BỘ', 'CÁI MÉP', 'ĐỒNG BẰNG', 'TỔNG CỘNG')

# tên cảng VPA (đã chuẩn hoá: bỏ dấu, (*), khoảng trắng) -> (cảng vụ, bến trong app Port Tracker)
PORT_MAP = {
    'HAI PHONG CHUA VE+TAN VU': ('HP', 'CHUA VE+TAN VU'), 'HTIT': ('HP', 'HTIT'), 'HICT LACH HUYEN, HP': ('HP', 'HICT'),
    'DOAN XA': ('HP', 'DOAN XA'), 'DINH VU': ('HP', 'DINH VU'), 'NAM HAI DINH VU': ('HP', 'NAM HAI DINH VU'), 'NAM DINH VU': ('HP', 'NAM DINH VU'),
    'TAN CANG 128 HAI PHONG': ('HP', 'CANG 128'), 'VIMC DINH VU': ('HP', 'VIMC'), 'VIP GREEN PORT': ('HP', 'VIP GREEN PORT'),
    'GREEN PORT': ('HP', 'GREEN PORT'), 'MIPEC': ('HP', 'MPC PORT'), 'HAI AN': ('HP', 'HAI AN'), 'TC 189 HAI PHONG': ('HP', 'TAN CANG 189'),
    'NAM HAI': ('HP', 'NAM HAI'), 'HHIT': ('HP', 'HHIT'), 'PTSC DINH VU': ('HP', 'PTSC DINH VU'),
    'DA NANG': ('DNG', 'BẾN CẢNG TIÊN SA'), 'PHUOC AN': ('DNI', 'BẾN CẢNG PHƯỚC AN'),
    'CANG SAI GON': ('HCM', 'SAI GON'), 'BEN NGHE': ('HCM', 'BEN NGHE'), 'TAN CANG - HIEP PHUOC': ('HCM', 'TAN CANG HIEP PHUOC'),
    'TAN CANG - CAT LAI': ('HCM', 'CAT LAI'), 'VICT': ('HCM', 'VICT'), 'SPCT': ('HCM', 'SPCT'), 'SP-ITC': ('HCM', 'SP-ITC'),
    'SP-PSA': ('HCM', 'SP-PSA'), 'TAN CANG - TCIT': ('HCM', 'TCIT'), 'TAN CANG - TCTT': ('HCM', 'TCTT'), 'CMIT': ('HCM', 'CMIT'),
    'SSIT': ('HCM', 'SSIT'), 'SITV': ('HCM', 'SITV'), 'GEMALINK': ('HCM', 'GEMALINK'),
}


def _norm(s):
    s = unicodedata.normalize('NFD', str(s)); s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').replace('đ', 'd').replace('Đ', 'D')
    s = re.sub(r'\(\*\)', '', s); s = s.replace('(', ' ').replace(')', ' ')
    return re.sub(r'\s+', ' ', s).strip().upper()


def _num(x):
    if x is None or (isinstance(x, str) and not re.search(r'\d', x)): return np.nan
    try: return float(str(x).replace(',', ''))
    except ValueError: return np.nan


def read_file(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    out = []
    for ws in wb.worksheets:
        m = re.match(r'T(\d{1,2})-(\d{4})', ws.title.strip())
        if not m: continue
        mon, yr = int(m.group(1)), int(m.group(2)); region = ''
        for row in ws.iter_rows(min_row=5, values_only=True):
            name = row[0]
            if name is None or not str(name).strip(): continue
            name = re.sub(r'\s+', ' ', str(name)).strip()
            up = _norm(name)
            if up.startswith('TONG CONG'):                     # dòng toàn quốc: lấy rồi dừng (dưới là ghi chú)
                vals = [_num(x) for x in row[1:14]]
                out.append({'sheet': ws.title, 'year': yr, 'mon': mon, 'region': 'TOÀN QUỐC', 'kind': 'total', 'port': 'TỔNG CỘNG', 'key': 'TONG CONG',
                            **dict(zip(COLS, vals))})
                break
            if any(up.startswith(_norm(r)) for r in REGIONS):
                region = name.split('(')[0].strip(); kind = 'region'
            else:
                kind = 'port'
            vals = [_num(x) for x in row[1:14]]
            if all(np.isnan(v) for v in vals[:4]): continue
            out.append({'sheet': ws.title, 'year': yr, 'mon': mon, 'region': region, 'kind': kind, 'port': name, 'key': up, **dict(zip(COLS, vals))})
    return pd.DataFrame(out)


def read_year_formulas(path):
    """cột "Năm <năm trước>" (cột B) của sheet tháng mới nhất: VPA gõ số cứng dạng =a+b+...+z. Số cuối = T12, ngược dần về trước;
    số đầu = cộng dồn các tháng còn lại (11 số: T1+T2 rồi T3..T12; 3 số: T1..T10, T11, T12). Ô không công thức = chỉ có số cả năm."""
    import openpyxl
    wf = openpyxl.load_workbook(path, data_only=False); wv = openpyxl.load_workbook(path, data_only=True)
    sh = []
    for ws in wf.worksheets:
        m = re.match(r'T(\d{1,2})-(\d{4})', ws.title.strip())
        if m: sh.append((int(m.group(2)), int(m.group(1)), ws.title))
    if not sh: return pd.DataFrame()
    yr, _, title = max(sh); ws, vs = wf[title], wv[title]; out = []
    for r in range(5, ws.max_row + 1):
        name = ws.cell(r, 1).value
        if name is None or not str(name).strip(): continue
        up = _norm(re.sub(r'\s+', ' ', str(name)).strip())
        if up.startswith('TONG CONG'):
            v = _num(vs.cell(r, 2).value)
            if pd.notna(v) and v > 0: out.append({'key': 'TONG CONG', 'year': yr - 1, 'terms': [v], 'annual': v})
            break
        if any(up.startswith(_norm(x)) for x in REGIONS): continue
        f, v = ws.cell(r, 2).value, _num(vs.cell(r, 2).value)
        terms = None
        if isinstance(f, str) and re.fullmatch(r'=[\d.+\s]+', f.strip()):
            terms = [float(x) for x in re.findall(r'\d+(?:\.\d+)?', f)]
        if terms is None and (pd.isna(v) or v <= 0): continue
        out.append({'key': up, 'year': yr - 1, 'terms': terms or [v], 'annual': sum(terms) if terms else v})
    return pd.DataFrame(out)


def _me(y, m): return pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)


class AllocWeights:
    """nhịp tháng để chia 1 khối (chỉ biết tổng) ra từng tháng (16/10/2026 PV2: mọi số theo VPA, không dùng số ảnh):
    (1) throughput terminal EconDB của bến (mọi tháng khối > 0); (2) lịch tàu container cảng vụ của chính bến
    (TB tỷ trọng giờ nằm bến và sức chở); (3) None -> nhịp chung"""
    def __init__(self):
        self.t = None; self.v = {}; self.e = None

    def _econdb(self, auth, term, ms):
        try:
            sys.path.insert(0, os.path.dirname(TARGETS))
            import econdb as ed, nowcast as nw
            if self.e is None: self.e = ed.load()['series']
            lcs = ed.AUTH_LOCODES.get(auth)
            if not lcs or self.e is None or not len(self.e): return None
            parts = [nw.terminal_series(self.e, lcs, ed.TERMINAL_MAP, x.strip()) for x in term.split('+')]
            if any(p_.empty for p_ in parts): return None
            s = pd.concat(parts, axis=1).sum(axis=1, min_count=len(parts))
            s = s.reindex(ms)
            return s if s.notna().all() and (s > 0).all() else None
        except Exception as e:  # noqa: BLE001
            print(f'  ! EconDB terminal {term}: {e}'); return None

    def _targets(self):
        if self.t is None:
            self.t = pd.read_csv(TARGETS, dtype={'month': str}) if os.path.exists(TARGETS) else pd.DataFrame(columns=['auth', 'terminal', 'month', 'actual_teu'])
        return self.t

    def _visits(self, auth, lo, hi):
        if auth not in self.v:
            try:
                sys.path.insert(0, os.path.dirname(TARGETS))
                import trackerlib as tl
                c = tl.calls_from_store([auth], str(lo.date()), str(hi.date()))
                v = tl.load_visits(c, tl.terminal_meta(c)); v = v[v['is_container']].copy()
                v['month'] = tl.me(v['arr_day']); v['teu'] = pd.to_numeric(v['teu'], errors='coerce')
                v['hours_in_port'] = pd.to_numeric(v['hours_in_port'], errors='coerce').clip(upper=80)
                self.v[auth] = v
            except Exception as e:  # noqa: BLE001
                print(f'  ! không đọc được lịch tàu cảng vụ {auth}: {e}'); self.v[auth] = None
        return self.v[auth]

    def __call__(self, key, months):
        m = PORT_MAP.get(key)
        if not m: return None, 'nhịp chung'
        auth, term = m; ms = pd.DatetimeIndex(months)
        e = self._econdb(auth, term, ms)
        if e is not None: return e / e.sum(), 'throughput terminal EconDB'
        v = self._visits(auth, ms.min() - pd.offsets.MonthBegin(1), ms.max() + pd.Timedelta(days=1))
        if v is not None and len(v):
            members = [x.strip() for x in term.split('+')]
            g = v[v['terminal'].isin(members)].groupby('month')[['hours_in_port', 'teu']].sum().reindex(ms).fillna(0)
            if (g > 0).all().all():
                w = 0.5 * g['hours_in_port'] / g['hours_in_port'].sum() + 0.5 * g['teu'] / g['teu'].sum()
                return w, 'lịch tàu cảng vụ của bến'
        return None, 'nhịp chung'


XAC_NHAN = os.path.join(HERE, 'input', 'so_xac_nhan.csv')


def apply_confirmed(long):
    """input/so_xac_nhan.csv (port, month YYYY-MM, teu): số PV2 xác nhận -> ưu tiên cao nhất (nguon xac_nhan). Dòng vùng + TỔNG CỘNG
    của tháng đó cộng thêm chênh lệch (số xác nhận − số VPA cũ) để tổng vẫn khớp. -> (long, bảng chênh)"""
    if not os.path.exists(XAC_NHAN): return long, pd.DataFrame()
    x = pd.read_csv(XAC_NHAN, dtype={'port': str, 'month': str})
    x['key'] = x['port'].map(_norm); x['month'] = pd.to_datetime(x['month'].str[:7] + '-01') + pd.offsets.MonthEnd(0)
    meta = long.drop_duplicates('key', keep='last').set_index('key')[['region', 'kind', 'port']]
    miss = sorted(set(x['key']) - set(meta.index))
    if miss: print('  ! số xác nhận: không thấy cảng', miss)
    x = x[x['key'].isin(meta.index)]
    old = long.set_index(['key', 'month'])['teu']
    x['cu'] = [old.get((k, m), np.nan) for k, m in zip(x['key'], x['month'])]
    rows = x[['key', 'month', 'teu']].assign(nguon='xac_nhan', canh_bao='').join(meta, on='key')
    long = _dedup(pd.concat([long, rows], ignore_index=True))
    d = x[x['cu'].notna() & ((x['teu'] - x['cu']).abs() > 0.5)].assign(chenh=lambda t: t['teu'] - t['cu'])
    for r in d.itertuples():                                       # vùng + toàn quốc của tháng đó (nếu là số VPA, không phải phân bổ)
        reg = meta.loc[r.key, 'region']
        for k in ('TONG CONG',) + tuple(long.loc[(long['kind'] == 'region') & (long['region'] == reg), 'key'].unique()):
            mk = (long['key'] == k) & (long['month'] == r.month) & (long['nguon'] != 'phan_bo_nam_truoc')
            long.loc[mk, 'teu'] += r.chenh
    return long, d


TRAILING_RATIO = (0.55, 1.4)   # TB tháng của phần còn lại / TB các số cuối phải nằm trong khoảng này mới tin cách đọc


def _trailing_ok(key, t, yr, have):
    """23/10/2026: kiểm chứng công thức ít số = 'lũy kế T1..Tk + các tháng cuối' bằng các tháng ĐÃ BIẾT (lũy kế cùng kỳ của sheet mới):
    số đầu − tháng đã biết trong T1..Tk chia cho số tháng còn thiếu (≤ 3) phải cỡ các số cuối (TRAILING_RATIO);
    không thiếu tháng nào thì số đầu phải khớp tổng đã biết ±2%."""
    n = len(t); fe = 13 - n
    span = [_me(yr, m) for m in range(1, fe + 1)]
    known = [have[(key, m)] for m in span if (key, m) in have.index]
    unk = len(span) - len(known)
    if unk > 3: return False
    rest = t[0] - sum(known)
    if unk == 0:
        ok = abs(rest) <= 0.02 * t[0]
    else:
        tail = float(np.mean(t[1:])) if t[1:] else 0
        ok = tail > 0 and TRAILING_RATIO[0] <= (rest / unk) / tail <= TRAILING_RATIO[1]
    if ok: print(f'  + {key}: xác nhận công thức "lũy kế T1..T{fe} + {n - 1} tháng cuối" (còn {unk} tháng: {rest:,.0f})')
    return ok


def year_months(form, long, weights=None, cum=None):
    """-> (rows, blocks) năm trước từ công thức cột Năm.
    rows: tháng tách được (nguon nam_truoc_cong_thuc) + tháng PHÂN BỔ từ khối (phan_bo_nam_truoc, chỉ để hiển thị/cộng tổng tham khảo).
    blocks: khối nhiều tháng chỉ biết TỔNG (số đầu của công thức hoặc số cả năm − các tháng đã biết trong khoảng đó):
    mô hình dùng làm 1 quan sát gộp, không làm số tháng."""
    if form.empty: return pd.DataFrame(), pd.DataFrame()
    meta = long.drop_duplicates('key', keep='last').set_index('key')[['region', 'kind', 'port']]
    have = long[long['nguon'] != 'phan_bo_nam_truoc'].set_index(['key', 'month'])['teu']
    rows, blocks = [], []
    for r in form.itertuples(index=False):
        if r.key not in meta.index: continue
        if r.key == 'TONG CONG': continue                                                         # tổng: khối riêng ở main()
        t, yr = r.terms, r.year
        if 1 < len(t) <= MIN_TERMS_MONTHLY - 1 and r.key not in TRAILING_OK and not _trailing_ok(r.key, t, yr, have):
            t = [sum(t)]     # 2–4 số chưa kiểm chứng được cách đọc 'lũy kế + tháng cuối' (HTIT 49.476 ≠ T12 ảnh 63.729) -> chỉ tổng năm
        n = len(t); fe = 13 - n if n > 1 else 12                                                    # số đầu = T1..T(fe)
        for i, v in enumerate(t[1:] if n > 1 else [], start=fe + 1):
            rows.append({'key': r.key, 'month': _me(yr, i), 'teu': v, 'nguon': 'nam_truoc_cong_thuc'})
        span = [_me(yr, m) for m in range(1, fe + 1)]
        known = {m: have[(r.key, m)] for m in span if (r.key, m) in have.index}
        unk = [m for m in span if m not in known]
        if not unk: continue
        tot = t[0] - sum(known.values())
        if len(unk) == 1 and tot >= 0:                                     # khối 1 tháng = số tháng chính xác (vd Gemalink T10 = 10T − T1..T9)
            rows.append({'key': r.key, 'month': unk[0], 'teu': tot, 'nguon': 'nam_truoc_cong_thuc'}); continue
        if tot < 0:
            print(f'  ! {meta.loc[r.key, "port"]}: số đầu {t[0]:,.0f} < các tháng đã biết {sum(known.values()):,.0f} -> bỏ khối'); continue
        # lũy kế cùng kỳ T1..TM năm trước (cột thứ 3 sheet tháng M mới nhất) tách khối thành phần <= M và phần > M;
        # phần <= M ≈ 0 -> các tháng đó = 0 thật (bến chưa chạy, vd HTIT T1–T4/2025). Cột lũy kế vô lý (âm / > khối) -> không tách
        if cum and r.key in cum:
            M, cv = cum[r.key]; a = [m for m in unk if m.month <= M]; b = [m for m in unk if m.month > M]
            sa = cv - sum(v for m, v in known.items() if m.month <= M)
            if a and b and -max(100, 0.005 * tot) <= sa <= tot:
                if sa <= max(100, 0.005 * tot):
                    rows += [{'key': r.key, 'month': m, 'teu': 0.0, 'nguon': 'nam_truoc_cong_thuc'} for m in a]
                    blocks.append({'key': r.key, 'months': b, 'teu': tot - max(sa, 0)}); continue
                blocks += [{'key': r.key, 'months': a, 'teu': sa}, {'key': r.key, 'months': b, 'teu': tot - sa}]; continue
        blocks.append({'key': r.key, 'months': unk, 'teu': tot})
    rows = pd.DataFrame(rows, columns=['key', 'month', 'teu', 'nguon'])
    # phân bổ khối theo nhịp tháng của các cảng biết đủ 12 tháng (chỉ để hiển thị / tổng tham khảo)
    allm = pd.concat([long[long['kind'] == 'port'][['key', 'month', 'teu']], rows[['key', 'month', 'teu']]])
    yr0 = form['year'].iloc[0]; full_keys = [k for k, g in allm[allm['month'].dt.year == yr0].groupby('key') if g['month'].nunique() == 12]
    prof = allm[allm['key'].isin(full_keys) & (allm['month'].dt.year == yr0)].groupby('month')['teu'].sum()
    extra = []
    for b in blocks:
        w, how = weights(b['key'], b['months']) if weights else (None, 'nhịp chung')
        if w is None:
            w = prof.reindex(b['months']).fillna(0)
            w = w / w.sum() if w.sum() > 0 else pd.Series(1 / len(w), index=w.index)
        b['cach_chia'] = how
        extra += [{'key': b['key'], 'month': m, 'teu': b['teu'] * x, 'nguon': 'phan_bo_nam_truoc'} for m, x in w.items()]
    rows = pd.concat([rows, pd.DataFrame(extra, columns=rows.columns)], ignore_index=True)
    rows = rows.join(meta, on='key'); rows['canh_bao'] = ''
    blocks = pd.DataFrame(blocks)
    if len(blocks): blocks = blocks.join(meta, on='key')
    return rows, blocks


def agg_blocks(long, blocks, group_cols):
    """khối cho dòng gộp (vùng / toàn quốc / cảng vụ): khoảng = hợp các tháng phân bổ của thành viên; tổng = cộng mọi tháng ĐÃ BIẾT
    của thành viên trong khoảng + tổng các khối thành viên (chính xác, không phân bổ)"""
    out = []
    p = long[long['kind'] == 'port']
    for gk, g in p.groupby(group_cols):
        ks = set(g['key']); bb = blocks[blocks['key'].isin(ks)] if len(blocks) else blocks
        if bb is None or not len(bb): continue
        months = sorted({m for ms in bb['months'] for m in ms})
        exact = g[g['month'].isin(months) & (g['nguon'] != 'phan_bo_nam_truoc')]['teu'].sum()
        out.append({**dict(zip(group_cols, gk if isinstance(gk, tuple) else (gk,))), 'months': months, 'teu': exact + bb['teu'].sum()})
    return pd.DataFrame(out)


def totals_from_ports(long, months):
    """dòng vùng + TỔNG CỘNG cho các tháng chỉ có số cảng (năm trước tách từ công thức): cộng các cảng"""
    p = long[(long['kind'] == 'port') & long['month'].isin(months)]
    if p.empty: return pd.DataFrame()
    def src(g): return 'phan_bo_nam_truoc' if (g == 'phan_bo_nam_truoc').any() else 'nam_truoc_cong_thuc'
    reg = p.groupby(['region', 'month'], as_index=False).agg(teu=('teu', 'sum'), nguon=('nguon', src))
    rk = long[long['kind'] == 'region'].drop_duplicates('region').set_index('region')
    reg['kind'] = 'region'; reg['port'] = reg['region'].map(rk['port']).fillna(reg['region'])
    reg['key'] = reg['region'].map(rk['key']).fillna(reg['region'].map(_norm))
    tot = p.groupby('month', as_index=False).agg(teu=('teu', 'sum'), nguon=('nguon', src))
    tot = tot.assign(region='TOÀN QUỐC', kind='total', port='TỔNG CỘNG', key='TONG CONG')
    return pd.concat([reg, tot], ignore_index=True).assign(canh_bao='')


# bến ít số mà PV2 đã xác nhận cách đọc "lũy kế + các tháng cuối" (16/10/2026 Gemalink: 7M 1.076.996 · 10M 1.585.050 · T11 175.956 · T12 170.041)
TRAILING_OK = {'GEMALINK'}                 # HTIT: PV2 gửi đủ số tháng -> input/so_xac_nhan.csv
MIN_TERMS_MONTHLY = 5      # công thức cột Năm >= 5 số mới tách tháng (11–12 số khớp 100% số tháng đã biết; 7 số An Giang khớp)


RANK = {'luy_ke_cung_ky': 0, 'phan_bo_nam_truoc': 1, 'nam_truoc_cong_thuc': 2, 'luy_ke': 3, 'thang': 4, 'xac_nhan': 5}   # trùng tháng: hạng cao thắng


def _dedup(long):
    return (long.assign(_r=long['nguon'].map(RANK)).sort_values(['key', 'month', '_r'])
            .drop_duplicates(['key', 'month'], keep='last').drop(columns='_r'))


def build(raw):
    raw = raw.copy()
    raw['score'] = raw[['teu', 'cum_cur']].fillna(0).max(axis=1)
    raw = raw.sort_values('score').drop_duplicates(['year', 'mon', 'key'], keep='last')         # cảng trùng tên trong sheet
    raw['port'] = raw['key'].map(raw.groupby('key')['port'].agg(lambda s: s.mode().iloc[0]))   # tên hiển thị = cách viết hay gặp nhất (VPA có 'Dình Vũ')
    rows = []
    for (key, yr), g in raw.groupby(['key', 'year']):
        g = g.set_index('mon').sort_index(); meta = g.iloc[-1]
        prev_cum = prev_cum_p = 0.0; prev_m = 0; prev_mc = prev_mp = 0          # tháng gần nhất CÓ ô lũy kế (năm nay / cùng kỳ)
        for mon, r in g.iterrows():
            gap = mon != prev_m + 1                                  # thiếu sheet tháng trước -> không suy được chênh lệch lũy kế
            # 16/10/2026: chỉ lấy chênh lệch khi THÁNG LIỀN TRƯỚC có ô lũy kế (Phước An T6/2026 trống lũy kế cùng kỳ -> T7/2025 cũ = T6+T7)
            d_cur = r['cum_cur'] - prev_cum if not gap and prev_mc == mon - 1 and pd.notna(r['cum_cur']) else np.nan
            d_prev = r['cum_prev'] - prev_cum_p if not gap and prev_mp == mon - 1 and pd.notna(r['cum_prev']) else np.nan
            teu, src, warn = r['teu'], 'thang', ''
            if (pd.isna(teu) or teu == 0) and pd.notna(d_cur) and d_cur > 0: teu, src = d_cur, 'luy_ke'
            elif pd.notna(d_cur) and pd.notna(teu) and teu > 0 and abs(teu - d_cur) > max(50, 0.02 * teu):
                warn = f'tháng {teu:,.0f} ≠ chênh lũy kế {d_cur:,.0f}'
            if pd.notna(teu) and teu > 0:
                rows.append({'region': meta['region'], 'kind': meta['kind'], 'port': meta['port'], 'key': key,
                             'month': pd.Timestamp(yr, mon, 1) + pd.offsets.MonthEnd(0), 'teu': teu, 'nguon': src, 'canh_bao': warn,
                             **{c: r[c] for c in COLS[4:]}})
            stale = pd.notna(d_prev) and d_prev == 0 and prev_cum_p > 0     # lũy kế đứng yên sau tháng có số = ô chép lại (Phước An T6/2026)
            if pd.notna(d_prev) and (d_prev > 0 or (d_prev == 0 and prev_cum_p == 0)):     # lũy kế vẫn 0 từ đầu năm = tháng 0 thật
                rows.append({'region': meta['region'], 'kind': meta['kind'], 'port': meta['port'], 'key': key,
                             'month': pd.Timestamp(yr - 1, mon, 1) + pd.offsets.MonthEnd(0), 'teu': d_prev, 'nguon': 'luy_ke_cung_ky', 'canh_bao': ''})
            if pd.notna(r['cum_cur']): prev_cum, prev_mc = r['cum_cur'], mon
            if pd.notna(r['cum_prev']) and not stale: prev_cum_p, prev_mp = r['cum_prev'], mon
            prev_m = mon
    long = _dedup(pd.DataFrame(rows))                                # 'thang' (sheet đúng tháng) ưu tiên hơn suy từ lũy kế
    year_prev = raw.sort_values(['year', 'mon']).groupby('key').agg(port=('port', 'last'), region=('region', 'last'), kind=('kind', 'last'),
                                                                    year=('year', 'last'), year_prev=('year_prev', 'last'))
    return long, year_prev


def _ym(ms): return ';'.join(pd.Timestamp(m).strftime('%Y-%m') for m in ms)


def to_targets(long, blocks):
    """-> (tháng, khối). tháng: các cảng trong PORT_MAP + toàn quốc (TỔNG CỘNG, auth 'VN') + cảng vụ (cộng cảng map, '__CANG_VU__');
    tháng có phần phân bổ thì KHÔNG ghi làm số tháng. khối: (auth, terminal, months 'YYYY-MM;...', total_teu) cho mô hình làm quan sát gộp."""
    p = long[long['kind'] == 'port'].copy(); p['map'] = p['key'].map(PORT_MAP)
    p = p[p['map'].notna()]
    t = pd.DataFrame({'auth': p['map'].str[0], 'terminal': p['map'].str[1], 'month': p['month'].dt.strftime('%Y-%m'), 'actual_teu': p['teu'].round(1),
                      'fill_only': ((p['nguon'] == 'luy_ke_cung_ky') | ((p['nguon'] == 'nam_truoc_cong_thuc') & (p['teu'] == 0))).values,
                      'phan_bo': (p['nguon'] == 'phan_bo_nam_truoc').values})
    tot = long[long['kind'] == 'total']
    vn = pd.DataFrame({'auth': 'VN', 'terminal': 'TOÀN QUỐC', 'month': tot['month'].dt.strftime('%Y-%m'), 'actual_teu': tot['teu'].round(1),
                       'fill_only': (tot['nguon'] == 'luy_ke_cung_ky').values, 'phan_bo': (tot['nguon'] == 'phan_bo_nam_truoc').values})
    cv = t.groupby(['auth', 'month'], as_index=False).agg(actual_teu=('actual_teu', 'sum'), fill_only=('fill_only', 'max'),
                                                          phan_bo=('phan_bo', 'max')).assign(terminal=CANG_VU)
    cv['fill_only'] = cv['fill_only'] & ~cv['phan_bo']; vn['fill_only'] = vn['fill_only'] & ~vn['phan_bo']
    # % phân bổ của dòng tổng: phần TEU từ cảng phân bổ / tổng tháng (cộng cảng)
    pa = long[(long['kind'] == 'port')].assign(pb=lambda d: d['teu'].where(d['nguon'] == 'phan_bo_nam_truoc', 0.0))
    pct_vn = (pa.groupby('month')['pb'].sum() / pa.groupby('month')['teu'].sum() * 100).rename(lambda m: m.strftime('%Y-%m'))
    pm = pa.assign(map=pa['key'].map(PORT_MAP)).dropna(subset=['map']); pm['auth'] = pm['map'].str[0]
    pct_cv = (pm.groupby(['auth', 'month'])['pb'].sum() / pm.groupby(['auth', 'month'])['teu'].sum() * 100)
    pct_cv.index = pct_cv.index.set_levels(pct_cv.index.levels[1].strftime('%Y-%m'), level=1)
    # 16/10/2026 PV2: số phân bổ coi như số thật -> bến cũng ghi số tháng (ghi_chu cho biết nguồn), không còn khối
    vn['ghi_chu'] = [f'gồm {pct_vn.get(m, 0):.0f}% phân bổ' if pb else '' for m, pb in zip(vn['month'], vn['phan_bo'])]
    cv['ghi_chu'] = [f'gồm {pct_cv.get((a, m), 0):.0f}% phân bổ' if pb else '' for a, m, pb in zip(cv['auth'], cv['month'], cv['phan_bo'])]
    t['ghi_chu'] = np.where(t['phan_bo'], 'phân bổ từ tổng VPA', '')
    months = pd.concat([t, vn, cv[t.columns]], ignore_index=True).drop(columns='phan_bo')
    bl = []
    if len(blocks):
        b = blocks[blocks['key'] != 'TONG CONG'].copy(); b['map'] = b['key'].map(PORT_MAP); b = b[b['map'].notna()]
        bl += []   # PV2 16/10: khối đã chia thành số tháng (coi như số thật) -> không ghi khối cho bến
        p2 = long.copy(); p2['map'] = p2['key'].map(PORT_MAP); p2 = p2[(p2['kind'] == 'port') & p2['map'].notna()]; p2['auth'] = p2['map'].str[0]
        bk = blocks.copy(); bk['map'] = bk['key'].map(PORT_MAP); bk = bk[bk['map'].notna()]
        # tổng cảng vụ / toàn quốc đã có số tháng (thật + phân bổ, ghi % trong ghi_chu) -> không cần khối
    return months, pd.DataFrame(bl, columns=['auth', 'terminal', 'months', 'total_teu'])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('files', nargs='*', help='file Excel VPA (mặc định: mọi VPA-container*.xlsx trong input/)')
    ap.add_argument('--targets', action='store_true', help='cập nhật nowcast_targets.csv của Port Tracker (VPA ghi đè trùng tháng)')
    a = ap.parse_args(argv)
    files = a.files or sorted(glob.glob(os.path.join(HERE, 'input', 'VPA-container*.xlsx')))
    if not files: sys.exit('ERROR khong co file VPA')
    raw = pd.concat([read_file(f) for f in files], ignore_index=True)
    long, yp = build(raw)
    long, xn = apply_confirmed(long)
    if len(xn): print(f'Số xác nhận (input/so_xac_nhan.csv): {len(xn)} ô khác VPA\n' + xn[['port', 'month', 'cu', 'teu']].to_string(index=False))
    # năm trước từ công thức cột "Năm" (số cứng cộng từng tháng) -> thêm T8–T12 + sửa tháng suy từ lũy kế sai
    form = pd.concat([read_year_formulas(f) for f in files], ignore_index=True)
    last = raw.sort_values(['year', 'mon']).groupby('key').tail(1)
    cum = {k: (int(m), float(c)) for k, m, c, y in zip(last['key'], last['mon'], last['cum_prev'], last['year'])
           if pd.notna(c) and y == form['year'].max() + 1} if len(form) else {}
    ym, blocks = year_months(form.drop_duplicates('key', keep='last'), long, AllocWeights(), cum) if len(form) else (pd.DataFrame(), pd.DataFrame())
    if len(ym):
        have = set(long.loc[long['kind'] == 'total', 'month'])
        tt = totals_from_ports(_dedup(pd.concat([long, ym], ignore_index=True)), sorted(set(ym['month']) - have))   # bỏ trùng TRƯỚC khi cộng (số xác nhận + công thức cùng tháng)
        fixed = ym.merge(long[long['nguon'] == 'luy_ke_cung_ky'][['key', 'month', 'teu']], on=['key', 'month'], suffixes=('', '_lk'))
        fixed = fixed[(fixed['teu'] - fixed['teu_lk']).abs() > 1]
        long = _dedup(pd.concat([long, ym, tt], ignore_index=True))
        print(f'Cột năm trước (công thức): {form["key"].nunique()} cảng -> {(ym["nguon"] == "nam_truoc_cong_thuc").sum()} tháng tách được, '
              f'{len(blocks)} khối chỉ biết tổng ({(ym["nguon"] == "phan_bo_nam_truoc").sum()} tháng phân bổ để xem); tổng/vùng thêm {tt["month"].nunique() if len(tt) else 0} tháng; '
              f'{len(fixed)} tháng sửa số suy từ lũy kế')
        if len(fixed): print(fixed[['port', 'month', 'teu_lk', 'teu']].to_string(index=False))
        tc = form[form['key'] == 'TONG CONG']
        if len(tc) and len(tt):                                      # tổng tháng (cộng cảng) co giãn để 5 tháng đúng bằng ô TỔNG CỘNG năm − T1..T7
            yr0 = int(tc['year'].iloc[0]); kn = long[(long['key'] == 'TONG CONG') & (long['month'].dt.year == yr0) & (long['nguon'] != 'phan_bo_nam_truoc')]
            target = float(tc['annual'].iloc[0]) - kn['teu'].sum()
            mk = (long['key'] == 'TONG CONG') & (long['nguon'] == 'phan_bo_nam_truoc')
            if mk.any() and long.loc[mk, 'teu'].sum() > 0:
                f = target / long.loc[mk, 'teu'].sum(); long.loc[mk, 'teu'] *= f
                print(f'Tổng toàn quốc T{long.loc[mk, "month"].dt.month.min()}–T{long.loc[mk, "month"].dt.month.max()}/{yr0}: cộng cảng × {f:.4f} '
                      f'= ô TỔNG CỘNG năm − tháng đã biết ({target:,.0f})')
        if len(tc):
            yr0 = int(tc['year'].iloc[0]); kn = long[(long['key'] == 'TONG CONG') & (long['month'].dt.year == yr0) & (long['nguon'] != 'phan_bo_nam_truoc')]
            unk = [_me(yr0, m) for m in range(1, 13) if _me(yr0, m) not in set(kn['month'])]
            if unk:
                blocks = pd.concat([blocks, pd.DataFrame([{'key': 'TONG CONG', 'months': unk, 'teu': float(tc['annual'].iloc[0]) - kn['teu'].sum(),
                                                           'region': 'TOÀN QUỐC', 'kind': 'total', 'port': 'TỔNG CỘNG'}])], ignore_index=True)
        if len(blocks):
            bo = blocks.assign(months=blocks['months'].map(_ym))
            if 'cach_chia' not in bo: bo['cach_chia'] = ''
            bo[['region', 'port', 'months', 'teu', 'cach_chia']].to_csv(os.path.join(DATA, 'vpa_container_blocks.csv'), index=False, encoding='utf-8-sig')
    os.makedirs(DATA, exist_ok=True)
    long.drop(columns=['key']).to_csv(os.path.join(DATA, 'vpa_container_long.csv'), index=False, encoding='utf-8-sig')
    w = long.pivot_table(index=['region', 'kind', 'port'], columns='month', values='teu', aggfunc='last')
    w.columns = [c.strftime('%m/%Y') for c in w.columns]
    with pd.ExcelWriter(os.path.join(DATA, 'vpa_container_wide.xlsx')) as xw:
        w.reset_index().to_excel(xw, sheet_name='TEU theo thang', index=False)
        yp.reset_index(drop=True).to_excel(xw, sheet_name='Ca nam truoc', index=False)
        long[long['canh_bao'] != ''][['port', 'month', 'teu', 'canh_bao']].to_excel(xw, sheet_name='Canh bao', index=False)
    n_warn = (long['canh_bao'] != '').sum()
    print(f'{len(files)} file, {raw["sheet"].nunique()} sheet -> {long["key"].nunique()} cảng/vùng, {len(long)} dòng '
          f'({long["month"].min():%m/%Y}–{long["month"].max():%m/%Y}), {n_warn} cảnh báo | {DATA}')
    unm = sorted(set(long.loc[(long['kind'] == 'port'), 'port'][~long.loc[long['kind'] == 'port', 'key'].isin(PORT_MAP)]))
    print('Cảng chưa map vào app:', ', '.join(unm))
    if a.targets:
        new, nb = to_targets(long, blocks)
        bpath = os.path.join(os.path.dirname(TARGETS), 'nowcast_blocks.csv')
        nb.to_csv(bpath, index=False, encoding='utf-8')
        print(f'nowcast_blocks: {len(nb)} khối (bến + cảng vụ + toàn quốc) -> {bpath}')
        old = pd.read_csv(TARGETS, dtype={'month': str}) if os.path.exists(TARGETS) else pd.DataFrame(columns=new.columns)
        old['month'] = old['month'].str[:7]
        # số THÁNG (sheet đúng tháng) ghi đè; số năm trước SUY TỪ LŨY KẾ cùng kỳ chỉ điền ô trống (cột lũy kế VPA đôi khi chép nhầm năm,
        # vd Chùa Vẽ+Tân Vũ 1T2025 = 108.077 = số T1/2024)
        both = old.merge(new, on=['auth', 'terminal', 'month'], suffixes=('_cu', '_vpa'))
        diff = both[(both['actual_teu_cu'] - both['actual_teu_vpa']).abs() > 1]
        # 16/10/2026 PV2: MỌI số lấy theo VPA (kể cả suy từ lũy kế) thay số ảnh; tháng VPA chỉ biết tổng khối -> bỏ số ảnh, bến dùng khối
        inblk = {(r.auth, r.terminal, m) for r in nb.itertuples() for m in str(r.months).split(';')}
        drop = [(a, t_, m) in inblk for a, t_, m in zip(old['auth'], old['terminal'], old['month'])]
        if any(drop): print(f'Bỏ {sum(drop)} số cũ (ảnh) nằm trong khối VPA:', sorted({t_ for (a, t_, m), d in zip(zip(old['auth'], old['terminal'], old['month']), drop) if d}))
        old = old[[not d for d in drop]]
        new = new.drop(columns='fill_only')
        out = pd.concat([old, new]).drop_duplicates(['auth', 'terminal', 'month'], keep='last').sort_values(['auth', 'terminal', 'month'])
        out.to_csv(TARGETS, index=False, encoding='utf-8')
        print(f'nowcast_targets: {len(old)} -> {len(out)} dòng ({out["terminal"].nunique()} bến), {len(diff)} ô khác số cũ (VPA ghi đè)')
        if len(diff): print(diff.to_string(index=False))
    print('DONE vpa-container')
    return 0


if __name__ == '__main__':
    sys.exit(main())
