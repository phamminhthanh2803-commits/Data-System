# -*- coding: utf-8 -*-
"""run_slot.py — RUNNER cho hub BẤT ĐỘNG SẢN (D:\\bat-dong-san), cùng lõi runlib.py với market-data / shipping (17/10/2026).

    python run_slot.py --slot AM                 # bds-projects: danh sách 6.000+ dự án + 300 chi tiết + 800 dự án tin rao (~45–60 phút)
    python run_slot.py --slot AM --only bds-projects
    set BDS_ARGS=--master --pages 2   (env, tuỳ chọn) -> truyền thêm tham số cho bds_scrape.py (cloud: input `args` của bds-am.yml, thử nhanh)
Chưa đăng ký Task Scheduler; lệnh mẫu (chạy 1 lần trong PowerShell):
    schtasks /create /tn "BDS AM" /sc daily /st 07:30 /tr "python D:\\bat-dong-san\\run_slot.py --slot AM" /f
Cloud (GitHub Actions, repo Data-System): thêm hub 'bat-dong-san' vào pack_code.py + data_manifest.py (store/ lên Drive) rồi gọi run_slot.py như shipping.
"""
import os
import shlex
import sys

HUB = os.path.dirname(os.path.abspath(__file__))
MD_ROOT = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))
sys.path.insert(0, MD_ROOT)
try:
    from runlib import Runner, Step, parse_args
except ImportError as e:
    sys.exit(f"Khong import duoc runlib.py tu {MD_ROOT} (dat env MD_ROOT tro toi thu muc market-data): {e}")

BDS_ARGS = tuple(shlex.split(os.environ.get("BDS_ARGS", "")))      # rỗng = mặc định hằng ngày của bds_scrape.py

STEPS = [
    Step("AM", "bds-projects", "batdongsan-projects/bds_scrape.py", when=True, retry=2, retry_wait=300, extra_args=BDS_ARGS),   # batdongsan.com.vn: danh sách + chi tiết + tin rao -> store/
]


def main(argv=None) -> int:
    a = parse_args("AM", argv)
    r = Runner(root=HUB, prefix="bds", title="Bat dong san", slot=a.slot,
               default_match="DONE|ERROR|LOI|master:|geo:|chi tiết:|tin rao:", with_stale=False, alert=False, clean_txt=False)
    r.run(STEPS, a.only, dry_run=a.dry_run, skip=a.skip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
