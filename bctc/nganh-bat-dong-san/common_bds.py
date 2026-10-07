# -*- coding: utf-8 -*-
"""Hằng số + tiện ích dùng chung cho pipeline NGÀNH BẤT ĐỘNG SẢN (D:\\bctc\\nganh-bat-dong-san)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FSX_DIR = r"D:\bctc\fs-extractor"
FSX_OUT = os.path.join(FSX_DIR, "output")                  # dump BCTC VCI toàn sàn (fsx.py bctc)
MD = r"D:\market-data"
TV = os.path.join(MD, "index-fetcher", "tv-history.csv")
META = os.path.join(MD, "index-fetcher", "raw", "vn_screener_meta.csv")
INDICES = os.path.join(MD, "index-fetcher", "indices-master.csv")
FOREIGN_VCI = os.path.join(MD, "index-fetcher", "raw", "vn_foreign_stocks_vci.parquet")
BONDS = os.path.join(MD, "bond-pivot", "data", "processed", "market_issuance_timeline.csv")
TM_WIDE = os.path.join(MD, "transmission-fetcher", "transmission-wide.csv")

RAW = os.path.join(HERE, "raw")
OUT_XLSX = os.path.join(HERE, "Nganh_BDS.xlsx")
SQLITE = os.path.join(HERE, "nganh_bat_dong_san.sqlite")
NHOM_CSV = os.path.join(HERE, "nhom_bds.csv")              # user sửa được: nhóm + có cộng vào ngành hay không

NGANH_L2 = "Bất động sản"                                   # ICB cấp 2 trong dump VCI
STMTS = {"IS": "income_statement", "BS": "balance_sheet", "CF": "cash_flow", "NOTE": "note"}
DON_VI = 1e9                                                # VND -> tỷ đồng
FIRST_Q = "2018-Q1"                                         # VCI chỉ có từ 2018

# Nhóm tổng hợp (mã nhóm, tên hiển thị, hàm chọn thành viên theo cột nhom của nhom_bds.csv)
NHOM_TONG = [
    ("ALL", "Toàn ngành", None),
    ("EXVIN", "Toàn ngành (trừ Vingroup)", "!Vingroup"),
    ("NHA", "Phát triển nhà ở & khác", "Phát triển nhà ở & khác"),
    ("KCN", "Khu công nghiệp", "Khu công nghiệp"),
    ("VIN", "Vingroup (VHM, VRE)", "Vingroup"),
    ("DV", "Dịch vụ BĐS", "Dịch vụ BĐS"),
]

# Phân nhóm tự động lần đầu (user sửa trong nhom_bds.csv, lần sau KHÔNG ghi đè)
VIN = {"VIC", "VHM", "VRE"}
KCN = {"BCM", "D2D", "HPI", "IDC", "IDV", "ITA", "KBC", "LHG", "MH3", "NTC", "PXL", "SIP", "SZB", "SZC",
       "SZG", "SZL", "TIP", "VRG", "TID"}
# Không cộng vào tổng ngành để khỏi đếm đôi: công ty mẹ đã hợp nhất công ty con cùng ngành
KHONG_CONG = {"VIC": "Hợp nhất VHM, VRE và mảng ngoài BĐS (VinFast...) - chỉ xem riêng",
              "DXS": "Công ty con của DXG (đã hợp nhất vào DXG)"}


def log(m):
    print(m, flush=True)


def utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass


def qlabel(p):
    """'2026-Q2' -> 'Q2-2026' (nhãn cột giống file ngành CK)."""
    y, q = p.split("-Q")
    return f"Q{q}-{y}"


def qidx(p):
    y, q = p.split("-Q")
    return int(y) * 4 + int(q) - 1


def qname(i):
    return f"{i // 4}-Q{i % 4 + 1}"


def qend(p):
    import pandas as pd
    y, q = p.split("-Q")
    return pd.Timestamp(int(y), int(q) * 3, 1) + pd.offsets.MonthEnd(0)
