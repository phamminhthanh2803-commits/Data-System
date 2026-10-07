# -*- coding: utf-8 -*-
"""run_slot.py — RUNNER Python cho cum VAN TAI BIEN (D:\\shipping), ban tuong duong Run-Shipping.ps1 (07/10/2026).

Cung bang buoc, cung logic (When thu Hai, Match, status-<Slot>.txt, logs/shipping_<Slot>_*.log, giu 60 log).
Dung chung loi runner D:\\market-data\\runlib.py (MD_ROOT).
    python run_slot.py --slot AM
    python run_slot.py --slot AM --only vhbs,cvhp
Khac Run-Shipping.ps1:
  - vhbs : VHBS-ConTex/vhbs_pull.py (ban Python cua Update-VhbsContex.ps1; ps1 goc giu nguyen)
  - haian: <HAH_DIR>/haian_pull.py (ban Python cua haian-schedule-daily.ps1; HAH_DIR mac dinh D:\\Database\\Logistics\\HAH)
  - alibra: van la run.ps1 (Windows); Linux khong co pwsh -> chay fetch.py roi combine.py
"""
import datetime as dt
import os
import sys

HUB = os.path.dirname(os.path.abspath(__file__))
MD_ROOT = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))
sys.path.insert(0, MD_ROOT)
try:
    from runlib import HAH_DIR, Runner, Step, parse_args
except ImportError as e:
    sys.exit(f"Khong import duoc runlib.py tu {MD_ROOT} (dat env MD_ROOT tro toi thu muc market-data): {e}")

today = dt.date.today()
is_mon = today.weekday() == 0

STEPS = [
    Step("AM", "vhbs", "VHBS-ConTex/vhbs_pull.py", when=True),                                         # gia thue tau container (ConTex)
    Step("AM", "haian", os.path.join(HAH_DIR, "haian_pull.py"), when=True),                            # lich tau HAH (data ghi canh script)
    Step("AM", "cvhp", "cangvu-haiphong/cvhp_scrape.py", when=True),                                   # lich dieu dong tau Cang vu HP (keo lai hom nay-3..+1)
    Step("AM", "cvhcm-berthmap", "cangvu-hcm/cvhcm_berthmap.py", extra_args=("--months", "2"), when=is_mon),   # thu Hai: bang tra ma cau -> khu vuc cang
    Step("AM", "cvhcm", "cangvu-hcm/cvhcm_scrape.py", when=True),                                      # ke hoach dieu dong tau Cang vu TP.HCM (gom Cai Mep - Vung Tau)
    Step("AM", "cv-pkh", "cangvu-toanquoc/pkh_scrape.py", extra_args=("--details", "150"), when=True),  # 9 cang vu nen tang public-kh
    Step("AM", "cv-aspx", "cangvu-toanquoc/aspx_scrape.py", when=True),                                # Quang Ninh kht1, Nha Trang, Can Tho
    Step("AM", "cv-national", "cangvu-toanquoc/national_build.py", when=True),                         # gop chuyen tau toan quoc
    Step("AM", "cvhp-vessels", "cangvu-haiphong/vessel_enrich.py", when=True),                         # tra IMO/loai tau/TEU/hang (toi da 300 tau/ngay) + ghep vao calls
    Step("AM", "itinerary", "vessel-itinerary/vessel_itinerary.py",
         extra_args=("--all", "--since", "2025-01-01", "--no-png"), when=True),                        # lo trinh tung tau + chang + vong tuyen
    Step("AM", "alibra", "alibra-scraper/run.ps1", kind="ps1", when=is_mon,
         fallback_py=("alibra-scraper/fetch.py", "alibra-scraper/combine.py")),
    Step("PM", "bcti", "BCTI-scraper/scrape_bcti.py", extra_args=("ALL",), when=True),                 # BDI/BCI/BPI/BSI/BHI/BCTI/BDTI/SCFI (stockq.org)
]


def main(argv=None) -> int:
    a = parse_args("AM", argv)
    r = Runner(root=HUB, prefix="shipping", title="Shipping", slot=a.slot,
               default_match="DONE|ERROR|LOI|XONG|Master|Da ghi|done|failed|saved|rows",
               with_stale=False, alert=False, clean_txt=False)
    r.run(STEPS, a.only, dry_run=a.dry_run, skip=a.skip)
    return 0


if __name__ == "__main__":
    sys.exit(main())
