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


def year_months(form, long):
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
        if len(t) <= MIN_TERMS_MONTHLY - 1: t = [sum(t)]     # 2–4 số: không rõ mỗi số là tháng nào (HTIT 49.476 ≠ T12 ảnh 63.729) -> chỉ tổng năm
        n = len(t); fe = 13 - n if n > 1 else 12                                                    # số đầu = T1..T(fe)
        for i, v in enumerate(t[1:] if n > 1 else [], start=fe + 1):
            rows.append({'key': r.key, 'month': _me(yr, i), 'teu': v, 'nguon': 'nam_truoc_cong_thuc'})
        span = [_me(yr, m) for m in range(1, fe + 1)]
        known = {m: have[(r.key, m)] for m in span if (r.key, m) in have.index}
        unk = [m for m in span if m not in known]
        if not unk: continue
        tot = t[0] - sum(known.values())
        if tot < 0:
            print(f'  ! {meta.loc[r.key, "port"]}: số đầu {t[0]:,.0f} < các tháng đã biết {sum(known.values()):,.0f} -> bỏ khối'); continue
        blocks.append({'key': r.key, 'months': unk, 'teu': tot})
    rows = pd.DataFrame(rows, columns=['key', 'month', 'teu', 'nguon'])
    # phân bổ khối theo nhịp tháng của các cảng biết đủ 12 tháng (chỉ để hiển thị / tổng tham khảo)
    allm = pd.concat([long[long['kind'] == 'port'][['key', 'month', 'teu']], rows[['key', 'month', 'teu']]])
    yr0 = form['year'].iloc[0]; full_keys = [k for k, g in allm[allm['month'].dt.year == yr0].groupby('key') if g['month'].nunique() == 12]
    prof = allm[allm['key'].isin(full_keys) & (allm['month'].dt.year == yr0)].groupby('month')['teu'].sum()
    extra = []
    for b in blocks:
        w = prof.reindex(b['months']).fillna(0)
        w = w / w.sum() if w.sum() > 0 else pd.Series(1 / len(w), index=w.index)
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


MIN_TERMS_MONTHLY = 5      # công thức cột Năm >= 5 số mới tách tháng (11–12 số khớp 100% số tháng đã biết; 7 số An Giang khớp)


RANK = {'luy_ke_cung_ky': 0, 'phan_bo_nam_truoc': 1, 'nam_truoc_cong_thuc': 2, 'luy_ke': 3, 'thang': 4}   # trùng tháng: hạng cao thắng


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
        prev_cum = prev_cum_p = 0.0; prev_m = 0
        for mon, r in g.iterrows():
            gap = mon != prev_m + 1                                  # thiếu sheet tháng trước -> không suy được chênh lệch lũy kế
            d_cur = r['cum_cur'] - prev_cum if not gap and pd.notna(r['cum_cur']) else np.nan
            d_prev = r['cum_prev'] - prev_cum_p if not gap and pd.notna(r['cum_prev']) else np.nan
            teu, src, warn = r['teu'], 'thang', ''
            if (pd.isna(teu) or teu == 0) and pd.notna(d_cur) and d_cur > 0: teu, src = d_cur, 'luy_ke'
            elif pd.notna(d_cur) and pd.notna(teu) and teu > 0 and abs(teu - d_cur) > max(50, 0.02 * teu):
                warn = f'tháng {teu:,.0f} ≠ chênh lũy kế {d_cur:,.0f}'
            if pd.notna(teu) and teu > 0:
                rows.append({'region': meta['region'], 'kind': meta['kind'], 'port': meta['port'], 'key': key,
                             'month': pd.Timestamp(yr, mon, 1) + pd.offsets.MonthEnd(0), 'teu': teu, 'nguon': src, 'canh_bao': warn,
                             **{c: r[c] for c in COLS[4:]}})
            if pd.notna(d_prev) and d_prev > 0:
                rows.append({'region': meta['region'], 'kind': meta['kind'], 'port': meta['port'], 'key': key,
                             'month': pd.Timestamp(yr - 1, mon, 1) + pd.offsets.MonthEnd(0), 'teu': d_prev, 'nguon': 'luy_ke_cung_ky', 'canh_bao': ''})
            prev_cum = r['cum_cur'] if pd.notna(r['cum_cur']) else prev_cum
            prev_cum_p = r['cum_prev'] if pd.notna(r['cum_prev']) else prev_cum_p; prev_m = mon
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
                      'fill_only': (p['nguon'] == 'luy_ke_cung_ky').values, 'phan_bo': (p['nguon'] == 'phan_bo_nam_truoc').values})
    tot = long[long['kind'] == 'total']
    vn = pd.DataFrame({'auth': 'VN', 'terminal': 'TOÀN QUỐC', 'month': tot['month'].dt.strftime('%Y-%m'), 'actual_teu': tot['teu'].round(1),
                       'fill_only': (tot['nguon'] == 'luy_ke_cung_ky').values, 'phan_bo': (tot['nguon'] == 'phan_bo_nam_truoc').values})
    cv = t.groupby(['auth', 'month'], as_index=False).agg(actual_teu=('actual_teu', 'sum'), fill_only=('fill_only', 'max'),
                                                          phan_bo=('phan_bo', 'max')).assign(terminal=CANG_VU)
    months = pd.concat([t, vn, cv[t.columns]], ignore_index=True)
    months = months[~months['phan_bo']].drop(columns='phan_bo')
    bl = []
    if len(blocks):
        b = blocks[blocks['key'] != 'TONG CONG'].copy(); b['map'] = b['key'].map(PORT_MAP); b = b[b['map'].notna()]
        bl += [{'auth': m[0], 'terminal': m[1], 'months': _ym(ms), 'total_teu': round(v, 1)} for m, ms, v in zip(b['map'], b['months'], b['teu'])]
        p2 = long.copy(); p2['map'] = p2['key'].map(PORT_MAP); p2 = p2[(p2['kind'] == 'port') & p2['map'].notna()]; p2['auth'] = p2['map'].str[0]
        bk = blocks.copy(); bk['map'] = bk['key'].map(PORT_MAP); bk = bk[bk['map'].notna()]
        cvb = agg_blocks(p2, bk, ['auth'])
        bl += [{'auth': r.auth, 'terminal': CANG_VU, 'months': _ym(r.months), 'total_teu': round(r.teu, 1)} for r in cvb.itertuples()]
        vb = blocks[blocks['key'] == 'TONG CONG']
        bl += [{'auth': 'VN', 'terminal': 'TOÀN QUỐC', 'months': _ym(r.months), 'total_teu': round(r.teu, 1)} for r in vb.itertuples()]
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
    # năm trước từ công thức cột "Năm" (số cứng cộng từng tháng) -> thêm T8–T12 + sửa tháng suy từ lũy kế sai
    form = pd.concat([read_year_formulas(f) for f in files], ignore_index=True)
    ym, blocks = year_months(form.drop_duplicates('key', keep='last'), long) if len(form) else (pd.DataFrame(), pd.DataFrame())
    if len(ym):
        have = set(long.loc[long['kind'] == 'total', 'month'])
        tt = totals_from_ports(pd.concat([long, ym], ignore_index=True), sorted(set(ym['month']) - have))
        fixed = ym.merge(long[long['nguon'] == 'luy_ke_cung_ky'][['key', 'month', 'teu']], on=['key', 'month'], suffixes=('', '_lk'))
        fixed = fixed[(fixed['teu'] - fixed['teu_lk']).abs() > 1]
        long = _dedup(pd.concat([long, ym, tt], ignore_index=True))
        print(f'Cột năm trước (công thức): {form["key"].nunique()} cảng -> {(ym["nguon"] == "nam_truoc_cong_thuc").sum()} tháng tách được, '
              f'{len(blocks)} khối chỉ biết tổng ({(ym["nguon"] == "phan_bo_nam_truoc").sum()} tháng phân bổ để xem); tổng/vùng thêm {tt["month"].nunique() if len(tt) else 0} tháng; '
              f'{len(fixed)} tháng sửa số suy từ lũy kế')
        if len(fixed): print(fixed[['port', 'month', 'teu_lk', 'teu']].to_string(index=False))
        tc = form[form['key'] == 'TONG CONG']
        if len(tc):
            yr0 = int(tc['year'].iloc[0]); kn = long[(long['key'] == 'TONG CONG') & (long['month'].dt.year == yr0) & (long['nguon'] != 'phan_bo_nam_truoc')]
            unk = [_me(yr0, m) for m in range(1, 13) if _me(yr0, m) not in set(kn['month'])]
            if unk:
                blocks = pd.concat([blocks, pd.DataFrame([{'key': 'TONG CONG', 'months': unk, 'teu': float(tc['annual'].iloc[0]) - kn['teu'].sum(),
                                                           'region': 'TOÀN QUỐC', 'kind': 'total', 'port': 'TỔNG CỘNG'}])], ignore_index=True)
        if len(blocks):
            bo = blocks.assign(months=blocks['months'].map(_ym))
            bo[['region', 'port', 'months', 'teu']].to_csv(os.path.join(DATA, 'vpa_container_blocks.csv'), index=False, encoding='utf-8-sig')
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
        keys = set(zip(old['auth'], old['terminal'], old['month']))
        new = new[~(new['fill_only'] & [k in keys for k in zip(new['auth'], new['terminal'], new['month'])])].drop(columns='fill_only')
        out = pd.concat([old, new]).drop_duplicates(['auth', 'terminal', 'month'], keep='last').sort_values(['auth', 'terminal', 'month'])
        out.to_csv(TARGETS, index=False, encoding='utf-8')
        print(f'nowcast_targets: {len(old)} -> {len(out)} dòng ({out["terminal"].nunique()} bến), {len(diff)} ô khác số cũ '
              f'(số tháng ghi đè, số suy từ lũy kế cùng kỳ giữ số cũ)')
        if len(diff): print(diff.to_string(index=False))
    print('DONE vpa-container')
    return 0


if __name__ == '__main__':
    sys.exit(main())
