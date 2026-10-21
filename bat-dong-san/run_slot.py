# -*- coding: utf-8 -*-
"""run_slot.py — RUNNER cho hub BẤT ĐỘNG SẢN (D:\\bat-dong-san), cùng lõi runlib.py với market-data / shipping (17/10/2026).

    python run_slot.py --slot AM                 # bds-projects: danh sách 6.000+ dự án + 300 chi tiết + 800 dự án tin rao + PDF báo cáo mới + 400 trang lịch sử giá quận (~55–70 phút)
    python run_slot.py --slot AM --only bds-projects
    python run_slot.py --slot AM --only biggee      # 20/10/2026: bước Biggee API hằng tháng (ngày 1-7 hoặc còn store/biggee/backfill.flag), chạy tay bất kỳ ngày nào
    set BDS_ARGS=--master --pages 2   (env, tuỳ chọn) -> truyền thêm tham số cho bds_scrape.py (cloud: input `args` của bds-am.yml, thử nhanh)
Chưa đăng ký Task Scheduler; lệnh mẫu (chạy 1 lần trong PowerShell):
    schtasks /create /tn "BDS AM" /sc daily /st 07:30 /tr "python D:\\bat-dong-san\\run_slot.py --slot AM" /f
18/10/2026: hub chạy LOCAL (task laptop 'BDS AM' 07:30), KHÔNG đưa lên cloud (batdongsan.com.vn chặn IP runner GitHub, PV2 chốt giữ local).
"""
import os
import shlex
import sys
from datetime import date

HUB = os.path.dirname(os.path.abspath(__file__))
MD_ROOT = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))
sys.path.insert(0, MD_ROOT)
try:
    from runlib import Runner, Step, parse_args
except ImportError as e:
    sys.exit(f"Khong import duoc runlib.py tu {MD_ROOT} (dat env MD_ROOT tro toi thu muc market-data): {e}")

BDS_ARGS = tuple(shlex.split(os.environ.get("BDS_ARGS", "")))      # rỗng = mặc định hằng ngày của bds_scrape.py

TODAY = date.today()
BIGGEE_FLAG = os.path.join(HUB, "batdongsan-projects", "store", "biggee", "backfill.flag")   # còn việc dở (hết quota ngày) -> chạy tiếp cả ngoài ngày 1-7
BIGGEE_WHEN = TODAY.day <= 7 or os.path.exists(BIGGEE_FLAG)
BIGGEE_ARGS = ("--update", "--delay", "0.5", "--budget", "900") + (("--refresh-catalog",) if TODAY.month in (1, 4, 7, 10) and TODAY.day <= 7 else ())   # đầu quý: làm mới bảng mã + thử lại mã không có dữ liệu

STEPS = [
    Step("AM", "bds-projects", "batdongsan-projects/bds_scrape.py", when=True, retry=2, retry_wait=300, extra_args=BDS_ARGS),   # batdongsan.com.vn: danh sách + chi tiết + tin rao -> store/
    Step("AM", "price-index", "batdongsan-projects/price_index.py", when=True, retry=1, retry_wait=60),                            # 20/10/2026: chỉ số giá tự tính (P50/P25/P90 tin so sánh 120 ngày) từ store/listings
    # 20/10/2026 (tối): Biggee API (app.digihub.com.vn, key store/biggee/key.txt, quota 1.000 request/ngày) — HẰNG THÁNG ngày 1-7: bảng mã còn thiếu + lịch sử/định giá
    # mọi dự án chưa lấy trong tháng (1 request/dự án, 900/ngày -> vài ngày); chạm quota -> dừng êm (exit 0), ngày sau tiếp; xong hết -> tự xoá backfill.flag. KHÔNG cào web biggee.vn.
    Step("AM", "biggee", "batdongsan-projects/biggee_api.py", when=BIGGEE_WHEN, retry=1, retry_wait=60, extra_args=BIGGEE_ARGS,
         match="DONE|ERROR|LOI|QUOTA|bảng mã|dự án|tỉnh:|--update|còn việc|đã xoá|CHU Y"),
]


def main(argv=None) -> int:
    a = parse_args("AM", argv)
    r = Runner(root=HUB, prefix="bds", title="Bat dong san", slot=a.slot,
               default_match="DONE|ERROR|LOI|master:|geo:|chi tiết:|tin rao:|báo cáo:|lịch sử giá khu vực:", with_stale=False, alert=False, clean_txt=False)
    r.run(STEPS, a.only, dry_run=a.dry_run, skip=a.skip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
