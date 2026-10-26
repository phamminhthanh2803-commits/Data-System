# -*- coding: utf-8 -*-
r"""
cloud_boot_pt.py - khởi động app Port Tracker trên STREAMLIT COMMUNITY CLOUD (15/10/2026, repo public port-tracker).

Repo public chỉ có CODE (shipping/port-tracker + code cảng vụ HP/HCM/toàn quốc + vessel-itinerary). Dữ liệu nằm trên Google Drive
(gdrive:pipeline-data/shipping/..., GitHub Actions repo Data-System đẩy lên hằng ngày). Module này chạy ĐẦU app.py:

  1. Nhận biết cloud: có st.secrets["RCLONE_CONF"] (base64 của rclone.conf) và chưa có kho store/ local. Laptop -> boot() trả False.
  2. Tải rclone (linux zip) về ~/.local/bin, ghi rclone.conf từ secret (chmod 600).
  3. Kéo PULL (~58 MB) về đúng chỗ app đọc trong cây repo (HUB = thư mục shipping/), ghi marker để rerun không kéo lại.
  4. Thread nền mỗi 30 phút rclone copy lại (chỉ file đổi) -> app tự nạp store mới (livedata.import_store so chữ ký file).
"""
from __future__ import annotations

import base64
import io
import json
import os
import subprocess
import threading
import time
import zipfile

APP = os.path.dirname(os.path.abspath(__file__)); HUB = os.path.dirname(APP)
REMOTE = os.environ.get('RCLONE_REMOTE', 'gdrive:pipeline-data') + '/shipping'
RCLONE_URL = 'https://downloads.rclone.org/rclone-current-linux-amd64.zip'
BIN = os.path.join(os.path.expanduser('~'), '.local', 'bin', 'rclone')
CONF = os.path.join(os.path.expanduser('~'), '.config', 'rclone', 'rclone.conf')
MARKER = os.path.join(APP, '.cloud_boot.json')
REFRESH_SEC = int(os.environ.get('CLOUD_REFRESH_SEC', '1800'))
# (thư mục trên Drive dưới shipping/, include) -> kéo về HUB/<thư mục>
def _present_inc(years_back=2):
    """bản dựng sẵn (present.py): file chung + chuyến/lượt cập bến của NĂM HIỆN TẠI và years_back năm trước; năm cũ hơn app kéo khi cần"""
    y = time.localtime().tm_year
    yrs = [f'/store/present/{k}_{x}.parquet' for x in range(y - years_back, y + 1) for k in ('calls', 'visits')]
    return ['/store/present/meta.json'] + [f'/store/present/{n}.parquet' for n in
            ('lanes', 'patterns', 'legs', 'services', 'rotations', 'master', 'events_recent', 'season_cap')] + yrs


# (thư mục trên Drive dưới shipping/, include) -> kéo về HUB/<thư mục>
# 21/10/2026: KHÔNG kéo store/** thô nữa (app không còn nạp SQLite / ghép chuyến) - chỉ bản dựng sẵn + EconDB nhỏ + số công bố
PULL = [('port-tracker', _present_inc() + ['/store/econdb/series.parquet', '/store/econdb/calls.parquet', '/store/econdb/schedule.parquet',
                                           '/store/econdb/ports.parquet', '/store/econdb/vessels.parquet', '/store/econdb/terminals.parquet',
                                           '/store/econdb/vessel_portcalls.parquet', '/store/econdb/term_services.parquet',   # trang Tuyến dịch vụ (26/10)
                                           '/nowcast_targets.csv', '/nowcast_blocks.csv']),
        ('vessel-itinerary', ['/data/port_pairs_nm.csv']),                      # cache hải lý (bản đồ lộ trình 1 tàu)
        ('vimawa-sanluong', ['/data/vimawa_sanluong.csv'])]                     # biểu 28-T Cục Hàng hải: tham chiếu trang Sản lượng
# file đổi thường xuyên (bản dựng sẵn mỗi lượt pipeline, số công bố PV2 sửa tay, Cục HH) -> kéo ngay khi app chạy code mới + mỗi FAST_SEC;
# rclone chỉ chép file đổi
FAST = [('port-tracker', ['/nowcast_targets.csv', '/nowcast_blocks.csv'] + _present_inc()), ('vimawa-sanluong', ['/data/vimawa_sanluong.csv'])]
FAST_SEC = int(os.environ.get('CLOUD_FAST_SEC', '300'))
STATE = {'error': None, 'last': None, 'mb': None}


class DriveAuthError(RuntimeError):
    pass


def _secret(name):
    try:
        import streamlit as st
        v = st.secrets.get(name)
        if v: return str(v)
    except Exception:  # noqa: BLE001
        pass
    return os.environ.get(name)


def _have_present():
    """đủ bản dựng sẵn (meta + các file chung + năm hiện tại) trên máy chưa"""
    return all(os.path.exists(os.path.join(APP, x.lstrip('/'))) for x in _present_inc(0))


def is_cloud():
    return bool(_secret('RCLONE_CONF')) and not os.path.isdir(os.path.join(APP, 'store', 'events'))


def _rclone():
    if os.path.exists(BIN): return BIN
    import requests
    os.makedirs(os.path.dirname(BIN), exist_ok=True)
    z = zipfile.ZipFile(io.BytesIO(requests.get(RCLONE_URL, timeout=180).content))
    name = next(n for n in z.namelist() if n.endswith('/rclone'))
    with open(BIN, 'wb') as f: f.write(z.read(name))
    os.chmod(BIN, 0o755)
    return BIN


def _conf():
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    with open(CONF, 'wb') as f: f.write(base64.b64decode(_secret('RCLONE_CONF')))
    os.chmod(CONF, 0o600)


def pull_items(items):
    """kéo nhanh vài file (không ghi marker)"""
    exe = _rclone()
    for folder, inc in items:
        subprocess.run([exe, 'copy', f'{REMOTE}/{folder}', os.path.join(HUB, folder), '--retries', '2']
                       + sum([['--include', x] for x in inc], []), capture_output=True, text=True, timeout=300)
    STATE['fast'] = time.strftime('%d/%m/%Y %H:%M')


def pull(progress=None):
    exe = _rclone(); t0 = time.time()
    for i, (folder, inc) in enumerate(PULL):
        if progress: progress(i, len(PULL), folder)
        args = [exe, 'copy', f'{REMOTE}/{folder}', os.path.join(HUB, folder), '--fast-list', '--transfers', '16', '--checkers', '32',
                '--retries', '3', '--low-level-retries', '10'] + sum([['--include', x] for x in inc], [])
        p = subprocess.run(args, capture_output=True, text=True, timeout=900)
        if p.returncode != 0:
            err = (p.stderr or '')[-400:]
            if 'invalid_grant' in err or 'token' in err.lower() and 'expired' in err.lower():
                raise DriveAuthError('Token Google Drive trong secret RCLONE_CONF đã hết hạn: trên laptop chạy `rclone config reconnect gdrive:` '
                                     'rồi tạo lại secret RCLONE_CONF (Settings → Secrets) và Reboot app.')
            raise RuntimeError(f'rclone copy {folder} lỗi: {err}')
    mb = sum(os.path.getsize(os.path.join(r, f)) for folder, _ in PULL for r, _, fs in os.walk(os.path.join(HUB, folder))
             for f in fs if '/data' in r.replace('\\', '/') or '/store' in r.replace('\\', '/')) / 1e6
    STATE.update(last=time.strftime('%d/%m/%Y %H:%M'), mb=round(mb, 1), error=None, secs=round(time.time() - t0))
    with open(MARKER, 'w') as f: json.dump(STATE, f)
    return STATE


def _loop():
    """16/10/2026: luồng v2 (tên mới -> chạy code mới cả khi luồng cũ còn sống sau khi cập nhật code): file nhỏ ngay + mỗi FAST_SEC,
    toàn bộ PULL mỗi REFRESH_SEC"""
    last_full = time.time()
    while True:
        try: pull_items(FAST)
        except Exception as e: STATE['error'] = str(e)[:300]  # noqa: E701,BLE001
        if time.time() - last_full >= REFRESH_SEC:
            try: pull(); last_full = time.time()
            except Exception as e: STATE['error'] = str(e)[:300]  # noqa: E701,BLE001
        time.sleep(FAST_SEC)


def trim_memory():
    """trả RAM tạm (sau khi ghép chuyến) về hệ điều hành - máy Streamlit Cloud ~1 GB; Linux glibc malloc_trim, nơi khác chỉ gc"""
    import gc
    gc.collect()
    try:
        import ctypes
        ctypes.CDLL('libc.so.6').malloc_trim(0)
    except Exception:  # noqa: BLE001
        pass


def boot():
    """True nếu đang chạy cloud (đã kéo dữ liệu). Gọi 1 lần đầu app.py."""
    if not _secret('RCLONE_CONF'): return False
    if os.path.exists(MARKER) and _have_present():          # 21/10/2026: đủ bản dựng sẵn (store/present) thì không kéo lại
        try: STATE.update(json.load(open(MARKER)))
        except Exception: pass  # noqa: E701,BLE001
    else:
        import streamlit as st
        _conf()
        with st.status('Đang kéo dữ liệu dựng sẵn từ Google Drive (≈ 20 giây)…', expanded=True) as s:
            pull(lambda i, n, f: s.write(f'{i + 1}/{n} · {f}'))
            s.update(label=f'Đã kéo {STATE["mb"]} MB trong {STATE.get("secs")} s', state='complete', expanded=False)
    if not any(t.name == 'pt_refresh_v3' for t in threading.enumerate()):     # v3 (21/10): danh sách kéo mới (bản dựng sẵn)
        threading.Thread(target=_loop, name='pt_refresh_v3', daemon=True).start()
    return True
