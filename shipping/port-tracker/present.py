# -*- coding: utf-8 -*-
r"""
present.py - BƯỚC PIPELINE "pt-present": dựng sẵn dữ liệu TRÌNH BÀY cho app Port & Vessel Tracker (21/10/2026).

App online trước đây phải tự nạp ~1.000 file sự kiện vào SQLite (64 s, DB 364 MB) rồi ghép chuyến / lượt cập bến / chặng /
dịch vụ (~40 s, RAM ~700 MB) mỗi lần khởi động. Bước này làm hết trong pipeline (sau port-tracker, econdb, cvhp-vessels),
ghi ra store/present/ - app chỉ đọc parquet:

    calls_<YYYY>.parquet   chuyến tàu đã gắn hãng/TEU/lớp tàu (theo năm của ngày chuyến), cột chữ = category
    visits_<YYYY>.parquet  lượt cập bến từng bến (theo năm ngày cập bến)
    lanes / patterns / legs.parquet   chặng + vòng tuyến (khung mặc định 26 tháng của app)
    services / rotations.parquet      tuyến dịch vụ EconDB (gom vòng tuyến) + vòng tuyến từng tàu
    master.parquet         bảng tàu gọn (cột app dùng)
    events_recent.parquet  sự kiện điều động 21 ngày trước .. 7 ngày sau (trang Điều độ)
    meta.json              phiên bản kho, độ phủ từng cảng vụ, ngày dữ liệu cuối, danh sách năm

    python present.py                 # dựng toàn bộ (từ 2019)
    python present.py --since 2024    # chỉ dựng lại các năm >= 2024 (giữ file năm cũ)
Env: PORT_TRACKER_STORE, PORT_TRACKER_DB (giống pt_update).
"""
import argparse
import json
import os
import sys
import time

import pandas as pd

APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)
import livedata as ld        # noqa: E402
import trackerlib as tl      # noqa: E402

OUT = os.path.join(ld.STORE, 'present')
LANES_MONTHS = 26            # = mặc định "Dữ liệu nạp: 2 năm" của app
CAT_MAX = 0.5                # cột chữ có tỉ lệ giá trị riêng < 50% -> category (giảm RAM khi app đọc)
# cột chuyến app dùng (+ vài cột cho bảng tải về); bỏ imo_src, callsign, is_sb, arr_date, dep_date, n_shifts, shifts, n_revisions
CALL_COLS = ['call_id', 'auth', 'itinerary_no', 'ship', 'ship_key', 'flag', 'dwt', 'gt', 'loa', 'agent',
             'arrival', 'origin', 'first_berth', 'berths', 'last_berth', 'departure',
             'destination', 'hours_in_port', 'status', 'last_port', 'next_port', 'cargo', 'src', 'date', 'arr_day',
             'imo', 'vessel_class', 'operator', 'teu', 'built', 'service', 'is_container']
MASTER_COLS = ['ship_key', 'ship', 'imo', 'mmsi', 'vessel_class', 'class_src', 'built', 'flag', 'gt', 'dwt', 'loa', 'owner', 'manager',
               'operator', 'operator_src', 'teu', 'teu_src', 'service', 'service_src', 'calls_total', 'calls_12m', 'first_seen', 'last_seen',
               'top_berth', 'top_agent', 'top_cargo', 'is_sb', 'econdb_operator', 'econdb_owner', 'service_id', 'service_route']


def log(*a): print(time.strftime('%H:%M:%S'), *a, flush=True)


def slim(d):
    """category cho cột chữ lặp nhiều; số giữ nguyên"""
    d = d.copy()
    for c in d.columns:
        if d[c].dtype == object and len(d):
            try: ratio = d[c].nunique(dropna=False) / len(d)
            except TypeError: continue
            if ratio < CAT_MAX: d[c] = d[c].astype('category')
    return d


def write(df, name):
    p = os.path.join(OUT, name); tmp = p + '.tmp'
    slim(df).to_parquet(tmp, index=False, compression='zstd'); os.replace(tmp, p)
    return os.path.getsize(p) / 1e6


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--since', type=int, default=2019, help='năm đầu dựng lại (file năm cũ hơn giữ nguyên)')
    a = ap.parse_args(argv)
    t0 = time.time(); os.makedirs(OUT, exist_ok=True)
    n, nd = ld.import_store(progress=lambda i, k, au, ym: log(f'  nạp {i}/{k} {au} {ym}') if i % 200 == 0 or i == k else None)
    log(f'nạp store -> sqlite: {n} file events, {nd} cảng vụ days ({time.time() - t0:.0f}s)')
    today = pd.Timestamp.today().normalize()
    auths = list(ld.AUTHS)

    # 1. chuyến toàn lịch sử = phần lịch sử (< đầu tháng trước) + đuôi gần đây, gắn hãng/TEU
    b = str((today.replace(day=1) - pd.DateOffset(months=1)).date())
    lo = f'{min(a.since, 2019)}-01-01' if a.since <= 2019 else f'{a.since - 1}-11-15'      # dựng lại từ năm since: cần ngữ cảnh cuối năm trước
    fz = tl.calls_frozen(auths, lo, b); tail = tl.calls_tail(auths, b, (today + pd.Timedelta(days=1)).date())
    calls = tl.enrich_calls(pd.concat([x for x in (fz, tail) if len(x)], ignore_index=True))
    calls = calls[[c for c in CALL_COLS if c in calls.columns]]
    log(f'chuyến: {len(calls)} ({time.time() - t0:.0f}s)')
    visits = tl.load_visits(calls, tl.terminal_meta(calls))
    log(f'lượt cập bến: {len(visits)} ({time.time() - t0:.0f}s)')

    yr_c = calls['date'].dt.year; yr_v = visits['arr_day'].dt.year
    years = sorted(int(y) for y in yr_c.dropna().unique() if y >= a.since)
    size = 0.0
    for y in years:
        size += write(calls[yr_c == y], f'calls_{y}.parquet') + write(visits[yr_v == y], f'visits_{y}.parquet')
    all_years = sorted(int(f[6:10]) for f in os.listdir(OUT) if f.startswith('calls_') and f.endswith('.parquet'))
    log(f'ghi {len(years)} năm chuyến + lượt ({size:.1f} MB), có sẵn {all_years}')

    # 2. chặng + vòng tuyến (khung mặc định app)
    lo_l = today - pd.DateOffset(months=LANES_MONTHS) - pd.Timedelta(days=45)
    lanes, pats, legs = tl.build_lanes(calls[calls['date'] >= lo_l])
    for d, nm in ((lanes, 'lanes'), (pats, 'patterns'), (legs, 'legs')): size += write(d, f'{nm}.parquet')
    log(f'chặng: {len(lanes)} chặng-tháng, {len(pats)} tàu ({time.time() - t0:.0f}s)')

    # 3. tuyến dịch vụ EconDB + bảng tàu gọn
    master = tl.master_live()
    size += write(master[[c for c in MASTER_COLS if c in master.columns]], 'master.parquet')
    try:
        import econdb as ed, services as svm
        pc = ed.load().get('vessel_portcalls')
        if pc is not None and len(pc):
            ops = {}
            for imo, op in zip(master['imo'], master['operator']):
                try:
                    if op and str(op) != 'nan': ops[int(float(imo))] = op
                except (TypeError, ValueError): pass
            import carrier_services as cs_
            rot0 = svm.rotations(pc)
            nm = {**svm.service_names(ed.load().get('vessel_services')), **svm.names_for_rotations(rot0, cs_.load(), ops)}   # lịch tàu hãng ưu tiên
            svc, rot = svm.cluster(rot0, ops, names=nm)
            log(f'tên tuyến (lịch tàu hãng): {len(nm)} tàu')
            size += write(svc, 'services.parquet') + write(rot.drop(columns=['pset'], errors='ignore').assign(ports=rot['ports'].map(' '.join)), 'rotations.parquet')
            log(f'dịch vụ: {len(svc)}')
    except Exception as e:  # noqa: BLE001
        log(f'  ! dịch vụ EconDB lỗi: {str(e)[:150]}')

    # 4. sự kiện điều động gần đây (trang Điều độ)
    ev = []
    for d in pd.date_range(today - pd.Timedelta(days=21), today + pd.Timedelta(days=7)):
        e = tl.events_day(auths, d.strftime('%Y-%m-%d'))
        if len(e): ev.append(e.assign(plan_date=d.strftime('%Y-%m-%d')))
    if ev: size += write(pd.concat(ev, ignore_index=True), 'events_recent.parquet')

    # 4b. mùa vụ SỨC CHỞ nhiều năm theo cảng vụ (dự báo sản lượng, nowcast.cap_season): đọc lượt cập bến MỌI năm đã có trong present/
    try:
        import nowcast as nw
        fs = sorted(f for f in os.listdir(OUT) if f.startswith('visits_') and f.endswith('.parquet'))
        vv = pd.concat([pd.read_parquet(os.path.join(OUT, f)) for f in fs], ignore_index=True)
        for c in vv.columns:
            if isinstance(vv[c].dtype, pd.CategoricalDtype): vv[c] = vv[c].astype(object)
        vv = vv[vv['is_container'].astype(bool)]; lastv = vv['arr_day'].max(); rows = []
        for au in sorted(vv['auth'].dropna().unique().tolist()) + ['VN']:
            sub = vv if au == 'VN' else vv[vv['auth'] == au]
            si = nw.cap_season(nw.features(sub, lastv))
            if si is not None:
                rows += [{'auth': au, 'thang': int(m), 'si': float(x), 'tu': str(sub['arr_day'].min().date()), 'den': str(lastv.date())} for m, x in si.items()]
        if rows: size += write(pd.DataFrame(rows), 'season_cap.parquet')
        log(f'mùa vụ sức chở: {len(rows) // 12} phạm vi')
    except Exception as e:  # noqa: BLE001
        log(f'  ! mùa vụ sức chở lỗi: {str(e)[:150]}')

    # 5. meta
    cov = ld.coverage(); ss = ld.store_status()
    last = calls.loc[calls['arr_day'].notna(), 'arr_day'].max()
    meta = {'version': ld.version(), 'built_at': time.strftime('%Y-%m-%d %H:%M'), 'last_day': str(min(last, today).date()),
            'years': all_years, 'coverage': cov.to_dict('records'), 'store_status': ss, 'lanes_months': LANES_MONTHS}
    with open(os.path.join(OUT, 'meta.json'), 'w', encoding='utf-8') as f: json.dump(meta, f, ensure_ascii=False, default=str)
    log(f'DONE present: {size:.1f} MB -> {OUT} ({time.time() - t0:.0f}s)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
