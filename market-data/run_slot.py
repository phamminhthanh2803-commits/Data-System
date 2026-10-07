# -*- coding: utf-8 -*-
"""run_slot.py — RUNNER Python cho cum DU LIEU THI TRUONG & VI MO (D:\\market-data), ban tuong duong Run-Market.ps1 (07/10/2026).

Cung bang buoc, cung logic (When theo thu, Retry, Critical, Stale, Match, status-<Slot>.txt, logs/market_<Slot>_*.log).
Muc dich: 1 code chay duoc ca Windows (Task Scheduler hien tai van goi Run-Market.ps1) lan Linux/cloud (cron).
    python run_slot.py --slot AM
    python run_slot.py --slot PM --only flows,tradingview
    python run_slot.py --slot PM --dry-run
    python run_slot.py --slot PM --skip nganh-ck,bonds     # hoac env CLOUD_SKIP=... (cloud-deploy)
Canh bao: Telegram (env TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) hoac popup Windows (xem runlib.notify).
Buoc nganh-ck (Excel COM, ghi file OneDrive) windows_only: tren Linux bo qua + ghi log.
"""
import datetime as dt
import os
import sys

HUB = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HUB)
from runlib import BCTC_ROOT, Runner, Step, parse_args  # noqa: E402

today = dt.date.today()
is_mon, is_sat, is_early = today.weekday() == 0, today.weekday() == 5, today.day <= 7
NGANH_CK = os.path.join(BCTC_ROOT, "nganh-chung-khoan")

STEPS = [
    # ---- AM 10:30
    Step("AM", "valuation-vn", "market-valuation/run_daily.py", "market-valuation", when=True, critical=True,
         note="P/E, P/B, EPS thi truong VN (VNDirect) + nganh + tung ma + dieu chinh"),
    Step("AM", "macro-vn", "macro-fetcher/fetch_macro.py", "macro-fetcher", when=is_mon, match="."),
    # 07/10/2026: PX-Web NSO song lai o pxweb.nso.gov.vn (form ASP.NET -> JSON-stat): nien giam (nam) + CPI thang;
    # keo lai het moi tuan vi NSO sua so cu (So bo -> chinh thuc). nso-monthly chi tai Excel "Bieu so lieu" bao cao KT-XH thang.
    Step("AM", "nso", "nso-fetcher/fetch_nso.py", "nso-fetcher", when=is_mon, match="Da luu|Tong|LOI|XONG|X ",
         note="NSO PX-Web 11 CSDL kinh te -> nso_master.csv + nso_catalog.csv + nso_timeseries.xlsx"),
    Step("AM", "nso-monthly", "nso-fetcher/fetch_monthly_reports.py", "nso-fetcher", when=is_mon, match="Da luu|Tong|LOI|X "),
    Step("AM", "bonds", "bond-pivot/scripts/run_pipeline.py", "bond-pivot", when=is_mon, match=r"\] "),
    Step("AM", "vsdc-accounts", "vsdc-accounts/pull_vsdc_accounts.py", "vsdc-accounts", when=is_mon, match="Da luu|LOI|! |X "),
    Step("AM", "indices", "index-fetcher/fetch_indices.py", "index-fetcher", when=is_sat, retry=3, critical=True,
         stale={"file": "index-fetcher/indices-master.csv", "days": 6,
                "groups": ["VN=source:vnstock", "Global=source:yahoo", "KhuVuc=source:!vnstock,yahoo"]}),
    # ---- PM 18:30 (sau khi TQ/HK/Han/Dai/Thai/Indo/Malaysia/Nhat dong cua; SBV da dang so trong ngay)
    Step("PM", "transmission", "transmission-fetcher/fetch_all.py", "transmission-fetcher", when=True, retry=3, retry_wait=90,
         critical=True, match="Che do|Master:|Bao cao|Tong|X |! ",
         stale={"file": "transmission-fetcher/transmission-master.csv", "days": 4, "groups": []}),
    Step("PM", "flows", "index-fetcher/fetch_flows.py", "index-fetcher", when=True),
    Step("PM", "foreign-stocks", "index-fetcher/fetch_foreign_stocks.py", "index-fetcher", when=True, match="Che do|-> |Da luu|Khong",
         note="khoi ngoai mua/ban theo tung ma (VNDirect, du phong) -> app tab Khoi ngoai chia theo nhom nganh"),
    # 18/09/2026: nguon CHINH khoi ngoai theo ma = Vietcap IQ (lich su tu 2000, tach thoa thuan);
    # hang ngay chi keo 10 phien gan nhat moi ma (~1600 request, 8 luong). Backfill: --full.
    Step("PM", "foreign-vci", "index-fetcher/fetch_foreign_vci.py", "index-fetcher", when=True,
         extra_args=("--recent", "10"), match="Che do|Da luu|-> |! "),
    Step("PM", "prop-stocks", "index-fetcher/fetch_prop_stocks.py", "index-fetcher", when=True, match="Che do|-> |Da luu|Khong",
         note="tu doanh CTCK theo tung ma (VNDirect, tu 05/2022) -> app Soi dong tien"),
    Step("PM", "icb-vci", "index-fetcher/fetch_icb_vci.py", "index-fetcher", when=True, match="Che do|-> |Da luu|LOI",
         note="phan nganh ICB 4 cap (Vietcap, 1 request) -> app chia dong tien KN/TD theo nganh"),
    # 17/09/2026: GTGD chinh thuc (VCI) cua 4 chi so VN phai cap nhat MOI NGAY sau dong cua (buoc 'indices' chi chay T7).
    Step("PM", "indices-vn", "index-fetcher/fetch_indices.py", "index-fetcher", when=True,
         extra_args=("--only", "VNINDEX,VN30,HNXINDEX,UPCOM"), match="Che do|Tong|Da luu|LOI"),
    Step("PM", "tvhistory", "index-fetcher/tv_history.py", "index-fetcher", when=True, match="-> |da luu|KHONG"),
    Step("PM", "valuation-region", "market-valuation/region.py", "market-valuation", when=True),
    Step("PM", "tradingview", "market-valuation/tv_region.py", "market-valuation", when=True, match="TV_|LOI|->"),
    Step("PM", "nganh-ck", os.path.join(NGANH_CK, "update_nganh_daily.py"), NGANH_CK, when=True, match="-> |! |LOI|tbl_|Table2",
         windows_only=True,
         note="file nganh CK IB&Brokerage_Nganh.xlsx: dinh gia + LNST TTM tu gia TradingView, so TK VSDC (sau tvhistory)"),
    Step("PM", "msci", "market-valuation/msci_region.py", "market-valuation", when=is_early),
    Step("PM", "macro-region", "macro-fetcher/fetch_macro_region.py", "macro-fetcher", when=is_mon, match="."),
]


def main(argv=None) -> int:
    a = parse_args("PM", argv)
    r = Runner(root=HUB, prefix="market", title="Market Data", slot=a.slot,
               default_match="Che do|LOI|Tong|Da luu|->|Master|XONG|Bao cao|! |X ",
               with_stale=True, alert=True, clean_txt=True)
    r.run(STEPS, a.only, dry_run=a.dry_run, skip=a.skip)
    return 0          # nhu ps1: luon exit 0 (trang thai o status-<Slot>.txt)


if __name__ == "__main__":
    sys.exit(main())
