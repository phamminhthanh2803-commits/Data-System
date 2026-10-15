# -*- coding: utf-8 -*-
"""pack_port_tracker_public.py — chép CODE app Port Tracker (không dữ liệu, không key) vào repo PUBLIC D:\\port-tracker-public (15/10/2026).

Repo public chỉ dùng để Streamlit Community Cloud chạy app (gói miễn phí: app public không giới hạn). Dữ liệu app tự kéo từ Google Drive
lúc chạy (shipping/port-tracker/cloud_boot_pt.py, secret RCLONE_CONF đặt trên Streamlit, KHÔNG nằm trong repo).

    python pack_port_tracker_public.py              # chép + quét secret
    python pack_port_tracker_public.py --dry-run

Cây repo: shipping/<thư mục> giống D:\\shipping (app.py tìm code cảng vụ ở thư mục cha). Main file trên Streamlit:
shipping/port-tracker/app.py ; requirements.txt ở gốc repo.
"""
import argparse
import fnmatch
import os
import re
import shutil
import sys

SRC = os.path.normpath(os.environ.get('SHIP_ROOT', 'D:/shipping'))
DST = os.path.normpath(os.environ.get('PT_PUBLIC', 'D:/port-tracker-public'))
# thư mục -> mẫu file được chép (đường dẫn tương đối, posix); không chép data/, store/, cache/, logs/
TAKE = {
    'port-tracker': ['*.py', 'README.md', '.streamlit/config.toml'],
    'cangvu-haiphong': ['*.py', '*.csv'],
    'cangvu-hcm': ['*.py', '*.csv'],
    'cangvu-toanquoc': ['*.py', '*.csv'],
    'vessel-itinerary': ['*.py', '*.csv'],
}
SKIP_DIRS = {'data', 'store', 'cache', 'logs', '__pycache__', 'khao-sat', 'raw', 'downloads', 'out', 'png', 'maps'}
SKIP_FILES = {'nowcast_targets.csv'}            # số công bố nội bộ PV2 -> kéo từ Drive lúc chạy, không public
MAX_CSV = 2_000_000
REQ = """# Port & Vessel Tracker (Streamlit Community Cloud) - 15/10/2026
streamlit==1.57.0
pandas==2.3.3
numpy==2.2.6
pyarrow==24.0.0
plotly==7.1.0
requests==2.34.2
urllib3==2.7.0
lxml==6.1.3
openpyxl==3.1.5
"""
README = """# Port & Vessel Tracker (bản online)

Mã nguồn app Streamlit theo dõi cảng biển Việt Nam (12 cảng vụ) + sản lượng container (EconDB) + ước/dự báo hồi quy.
Repo chỉ có **code**; dữ liệu app tự kéo từ Google Drive lúc chạy (secret `RCLONE_CONF` trên Streamlit Cloud).

- Main file: `shipping/port-tracker/app.py`
- Secrets (Streamlit → Settings → Secrets):
  - `RCLONE_CONF = "<base64 của rclone.conf>"` (bắt buộc)
  - `APP_PASSWORD = "<mật khẩu xem app>"` (khuyên dùng: dữ liệu EconDB là gói trả phí)

Mã gốc nằm ở repo private Data-System; repo này được sinh tự động bởi `pack_port_tracker_public.py`, đừng sửa tay.
"""
SECRET_RE = re.compile(r'(?i)(api[_-]?key|token|password|secret|bearer)\s*[=:]\s*["\'][A-Za-z0-9_\-]{16,}["\']')


def wanted(rel, pats):
    parts = rel.split('/')
    if any(p in SKIP_DIRS for p in parts[:-1]) or parts[-1] in SKIP_FILES: return False
    return any(fnmatch.fnmatch(rel, p) or (('/' not in p) and fnmatch.fnmatch(parts[-1], p) and len(parts) == 1) for p in pats)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--dry-run', action='store_true'); a = ap.parse_args()
    files = []
    for d, pats in TAKE.items():
        root = os.path.join(SRC, d)
        for r, dirs, fs in os.walk(root):
            dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
            for f in fs:
                rel = os.path.relpath(os.path.join(r, f), root).replace('\\', '/')
                if not wanted(rel, pats): continue
                p = os.path.join(r, f)
                if f.endswith('.csv') and os.path.getsize(p) > MAX_CSV: continue
                files.append((p, os.path.join(DST, 'shipping', d, rel)))
    hits = []
    for p, _ in files:
        if p.endswith(('.py', '.csv', '.toml', '.md')):
            for i, line in enumerate(open(p, encoding='utf-8', errors='ignore'), 1):
                if SECRET_RE.search(line): hits.append(f'{p}:{i}: {line.strip()[:100]}')
    print(f'{len(files)} file, {sum(os.path.getsize(p) for p, _ in files) / 1e6:.1f} MB -> {DST}')
    if hits:
        print('NGHI CO SECRET, DUNG LAI:'); print('\n'.join(hits)); return 1
    if a.dry_run:
        for p, q in files: print(' ', os.path.relpath(q, DST))
        return 0
    old = os.path.join(DST, 'shipping')
    if os.path.isdir(old): shutil.rmtree(old)                 # chép đè sạch (xoá file đã mất ở nguồn)
    for p, q in files:
        os.makedirs(os.path.dirname(q), exist_ok=True); shutil.copy2(p, q)
    os.makedirs(os.path.join(DST, '.streamlit'), exist_ok=True)            # Streamlit Cloud đọc config ở gốc repo
    shutil.copy2(os.path.join(SRC, 'port-tracker', '.streamlit', 'config.toml'), os.path.join(DST, '.streamlit', 'config.toml'))
    open(os.path.join(DST, 'requirements.txt'), 'w', encoding='utf-8').write(REQ)
    open(os.path.join(DST, 'README.md'), 'w', encoding='utf-8').write(README)
    open(os.path.join(DST, '.gitignore'), 'w', encoding='utf-8').write(
        '__pycache__/\n*.pyc\nshipping/port-tracker/store/\nshipping/port-tracker/cache/\nshipping/port-tracker/.cloud_boot.json\n'
        'shipping/port-tracker/nowcast_targets.csv\nshipping/*/data/\n.streamlit/secrets.toml\n')
    print('Quet secret: khong thay. Xong.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
