# -*- coding: utf-8 -*-
r"""
pt_update.py - BƯỚC PIPELINE "port-tracker": ghép dữ liệu cảng vụ LIÊN TỤC cho Port & Vessel Tracker (09/10/2026).

Chạy không giao diện (GitHub Actions 9:00 + 22:00 cho 11 cảng vụ; laptop 8:30 + 18:40 cho TP.HCM vì cảng vụ HCM chặn IP nước ngoài):
    1. import_store : nạp các file store/ (parquet) mới/đổi vào sqlite cache/live.sqlite (cloud: chỉ vài tháng gần, sqlite tạo mới mỗi lần)
    2. ensure       : gọi trang nguồn các ngày thiếu / chưa chốt trong cửa sổ [hôm nay - days, ngày mai] (mỗi cảng vụ 1 luồng)
    3. export_store : xuất lại các cảng vụ-tháng vừa ghi ra store/events/<auth>/<YYYY-MM>.parquet + store/days/<auth>.csv -> rclone đẩy Drive
App chỉ còn nạp store/ về (livedata.import_store), không phải gọi nguồn khi mở.

    python pt_update.py                          # cảng vụ: env PT_AUTHS, hoặc tất cả (cloud CLOUD=1: tất cả trừ HCM)
    python pt_update.py --auths HCM --days 14    # laptop: chỉ TP.HCM
    python pt_update.py --export-all --no-pull   # seed lần đầu: xuất toàn bộ sqlite hiện có ra store/
Env: PORT_TRACKER_DB (sqlite), PORT_TRACKER_STORE (store/), PT_AUTHS, PT_DAYS, CLOUD=1.
"""
import argparse
import os
import sys
import time
from datetime import date, timedelta

import pandas as pd

APP = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, APP)
import livedata as ld  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--auths', default=os.environ.get('PT_AUTHS', ''), help='mã cảng vụ, cách nhau dấu phẩy (trống = mặc định)')
    ap.add_argument('--days', type=int, default=int(os.environ.get('PT_DAYS', '14')), help='cửa sổ kéo: hôm nay - days .. ngày mai')
    ap.add_argument('--ttl', type=int, default=0, help='phút; ngày chưa chốt cũ hơn TTL thì kéo lại (0 = luôn kéo lại)')
    ap.add_argument('--max-pages', type=int, default=60, help='tối đa số trang / cảng vụ / lần chạy')
    ap.add_argument('--months', type=int, default=None, help='số tháng store nạp vào sqlite (cloud mặc định 4, laptop: tất cả)')
    ap.add_argument('--export-all', action='store_true', help='xuất toàn bộ sqlite ra store/ (seed lần đầu)')
    ap.add_argument('--no-pull', action='store_true'); ap.add_argument('--no-export', action='store_true')
    a = ap.parse_args(argv)
    t0 = time.time(); cloud = os.environ.get('CLOUD') == '1'
    auths = [x.strip().upper() for x in a.auths.split(',') if x.strip()] or ([x for x in ld.AUTHS if x != 'HCM'] if cloud else list(ld.AUTHS))
    bad = [x for x in auths if x not in ld.AUTHS]
    if bad: sys.exit(f'ERROR cang vu khong hop le: {bad} (hop le: {ld.AUTHS})')
    months = a.months if a.months is not None else (4 if cloud else None)
    since = None if months is None else (pd.Timestamp.today().normalize().replace(day=1) - pd.DateOffset(months=months - 1)).strftime('%Y-%m')
    print(f'port-tracker: db={ld.DB} store={ld.STORE} cang vu={",".join(auths)} cua so={a.days} ngay nap tu={since or "dau"}', flush=True)

    # 1. store -> sqlite (chỉ file đổi)
    n_imp, n_days = ld.import_store(since=since, progress=lambda i, n, au, ym: print(f'  nap {i}/{n} {au} {ym}', flush=True) if i % 25 == 0 or i == n else None)
    print(f'nap store: {n_imp} file events, {n_days} cang vu days ({time.time() - t0:.0f}s)', flush=True)

    # 2. gọi nguồn
    n_pull = 0; errs = []
    if not a.no_pull:
        d1 = date.today() + timedelta(days=1); d0 = d1 - timedelta(days=a.days + 1)
        if since and d0 < date.fromisoformat(since + '-01'): d0 = date.fromisoformat(since + '-01')   # không ghi vào tháng chưa nạp
        todo = ld.plan(auths, d0, d1, ttl_min=a.ttl)
        print('can keo: ' + (', '.join(f'{k}:{len(v)}' for k, v in todo.items()) or 'khong co'), flush=True)
        state = {'t': time.time()}

        def cb(i, n, au, d):
            if i % 20 == 0 or i == n: print(f'  keo {i}/{n} {au} {d}', flush=True)
        n_pull, errs = ld.ensure(auths, d0, d1, ttl_min=a.ttl, max_pages=a.max_pages, progress=cb, todo=todo)
        for e in errs: print('  LOI ' + e, flush=True)
        print(f'keo nguon: {n_pull} trang, {len(errs)} loi ({time.time() - state["t"]:.0f}s)', flush=True)

    # 3. sqlite -> store (các cảng vụ-tháng vừa ghi; hoặc toàn bộ khi seed)
    n_exp = 0
    if not a.no_export:
        pairs = None if a.export_all else set(ld._dirty)
        n_exp = ld.export_store(pairs, auths=auths if a.export_all else None)
        print(f'xuat store: {n_exp} file parquet', flush=True)

    ok = a.no_pull or n_pull > 0 or not errs
    print(f'{"DONE" if ok else "ERROR"} port-tracker: nap {n_imp}, keo {n_pull} trang, loi {len(errs)}, xuat {n_exp} | {time.time() - t0:.0f}s', flush=True)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
