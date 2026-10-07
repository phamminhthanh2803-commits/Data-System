# -*- coding: utf-8 -*-
"""
macro-fetcher: keo du lieu vi mo Viet Nam theo thang tu IMF SDMX API
ve 1 file CSV long-format (macro_vn_master.csv), merge/dedup incremental.

Nguon: https://api.imf.org/external/sdmx/2.1 (khong can API key)
Cac flow su dung:
  IMF.STA,CPI  - CPI tong (_T) + 12 nhom COICOP CP01..CP12 (index, 2024=100)
  IMF.STA,ER   - Ty gia VND/USD (cuoi ky + binh quan ky)
  IMF.STA,ITG  - Xuat khau FOB / Nhap khau CIF (USD)
  IMF.STA,IL   - Du tru ngoai hoi (tong, gom vang, USD)
  IMF.STA,PI   - Chi so san xuat cong nghiep (IIP)

Output: macro_vn_master.csv
  cot: date,series_id,series_name,group,unit,value,source
  date dang YYYY-MM. Series dan xuat (YoY/MoM %, can can thuong mai)
  duoc tinh lai tu index/level moi lan chay.
"""

import csv
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

BASE = "https://api.imf.org/external/sdmx/2.1/data"
START = "1995-01"
HERE = Path(__file__).resolve().parent
MASTER = HERE / "macro_vn_master.csv"
LOG = HERE / "fetch_log.txt"

FIELDS = ["date", "series_id", "series_name", "group", "unit", "value", "source"]

# (flow, key, dict series_key_trong_flow -> (series_id, series_name, group, unit))
COICOP_VI = {
    "_T":   "CPI tong (chi so, 2024=100)",
    "CP01": "CPI 01 Luong thuc, thuc pham & do uong khong con",
    "CP02": "CPI 02 Do uong co con & thuoc la",
    "CP03": "CPI 03 May mac, giay dep",
    "CP04": "CPI 04 Nha o, dien, nuoc, chat dot",
    "CP05": "CPI 05 Thiet bi & do dung gia dinh",
    "CP06": "CPI 06 Y te",
    "CP07": "CPI 07 Giao thong",
    "CP08": "CPI 08 Buu chinh vien thong",
    "CP09": "CPI 09 Van hoa, giai tri",
    "CP10": "CPI 10 Giao duc",
    "CP11": "CPI 11 Nha hang & khach san",
    "CP12": "CPI 12 Hang hoa & dich vu khac",
}

JOBS = []
# CPI: key = COUNTRY.INDEX_TYPE.COICOP.TYPE.FREQ
for cp, name in COICOP_VI.items():
    sid = "CPI_ALL" if cp == "_T" else f"CPI_{cp}"
    JOBS.append(("CPI", f"VNM.CPI.{cp}.IX.M",
                 {("VNM", "CPI", cp, "IX", "M"): (sid, name, "CPI", "index_2024=100")}))

# ER: key = COUNTRY.INDICATOR.TYPE.FREQ  (XDC_USD = VND per USD)
JOBS.append(("ER", "VNM.XDC_USD.EOP_RT+PA_RT.M", {
    ("VNM", "XDC_USD", "EOP_RT", "M"): ("VND_USD_EOP", "Ty gia VND/USD cuoi ky", "FX", "VND/USD"),
    ("VNM", "XDC_USD", "PA_RT", "M"):  ("VND_USD_AVG", "Ty gia VND/USD binh quan ky", "FX", "VND/USD"),
}))

# ITG: key = COUNTRY.INDICATOR.TYPE.FREQ
JOBS.append(("ITG", "VNM.XG+MG.FOB_USD+CIF_USD.M", {
    ("VNM", "XG", "FOB_USD", "M"): ("EXPORT_USD", "Xuat khau hang hoa FOB", "TRADE", "USD"),
    ("VNM", "MG", "CIF_USD", "M"): ("IMPORT_USD", "Nhap khau hang hoa CIF", "TRADE", "USD"),
}))

# IL: key = COUNTRY.INDICATOR.UNIT.FREQ (TRGNV_REVS = total reserves incl gold, national valuation)
JOBS.append(("IL", "VNM.TRGNV_REVS.USD.M", {
    ("VNM", "TRGNV_REVS", "USD", "M"): ("FX_RESERVES_USD", "Du tru ngoai hoi (gom vang)", "RESERVES", "USD"),
}))

# PI: key = COUNTRY.PRODUCTION_INDEX.TYPE.FREQ
JOBS.append(("PI", "VNM.IND.IX+YOY_PCH_PT.M", {
    ("VNM", "IND", "IX", "M"):         ("IIP_IX", "Chi so san xuat cong nghiep (2010=100)", "IIP", "index_2010=100"),
    ("VNM", "IND", "YOY_PCH_PT", "M"): ("IIP_YOY", "IIP tang truong YoY", "IIP", "%"),
}))

# FSIC: key = COUNTRY.SECTOR.INDICATOR.FREQUENCY. FSI688_CFSI_PT = von tu co / tai san co rui ro
# (CAR) cua TOAN BO to chuc nhan tien gui - chay song song CAR NHNN (TT36 den 2019, nhom TT41 tu
# 07/2024) de lap khoang 2020-06/2024. Quy (ban nien den 2023Q1) tu 2014Q2 + nam tu 2008 (gan thang 12;
# nam trung ky Q4 thi Q4 ghi de, gia tri bang nhau).
JOBS.append(("FSIC", "VNM.S12CFSI.FSI688_CFSI_PT.A+Q", {
    ("VNM", "S12CFSI", "FSI688_CFSI_PT", "A"): ("CAR_IMF", "CAR to chuc nhan tien gui (IMF FSI)", "BANK", "%"),
    ("VNM", "S12CFSI", "FSI688_CFSI_PT", "Q"): ("CAR_IMF", "CAR to chuc nhan tien gui (IMF FSI)", "BANK", "%"),
}))

# thu tu dimension trong XML attrib cua tung flow
DIM_ORDER = {
    "FSIC": ["COUNTRY", "SECTOR", "INDICATOR", "FREQUENCY"],
    "CPI": ["COUNTRY", "INDEX_TYPE", "COICOP_1999", "TYPE_OF_TRANSFORMATION", "FREQUENCY"],
    "ER":  ["COUNTRY", "INDICATOR", "TYPE_OF_TRANSFORMATION", "FREQUENCY"],
    "ITG": ["COUNTRY", "INDICATOR", "TYPE_OF_TRANSFORMATION", "FREQUENCY"],
    "IL":  ["COUNTRY", "INDICATOR", "UNIT", "FREQUENCY"],
    "PI":  ["COUNTRY", "PRODUCTION_INDEX", "TYPE_OF_TRANSFORMATION", "FREQUENCY"],
}


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def localname(tag):
    return tag.split("}")[-1]


def fetch_flow(flow, key, retries=3):
    url = f"{BASE}/IMF.STA,{flow}/{key}?startPeriod={START}"
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "macro-fetcher/1.0"})
            xml = urllib.request.urlopen(req, timeout=180).read()
            return ET.fromstring(xml)
        except Exception as e:
            log(f"  loi lan {i+1} ({flow}): {e}")
            time.sleep(5 * (i + 1))
    return None


def period_to_date(p):
    # '2026-M06' -> '2026-06' ; '2025-Q2' -> '2025-06' ; '2008' -> '2008-12'
    if not p:
        return None
    if "-Q" in p:
        y, q = p.split("-Q")
        return f"{y}-{int(q) * 3:02d}"
    if len(p) == 4 and p.isdigit():
        return f"{p}-12"
    return p.replace("-M", "-")


def pull_all():
    """Tra ve dict {(series_id): {date: value}} + metadata."""
    data = {}   # sid -> {date: float}
    meta = {}   # sid -> (name, group, unit)
    for flow, key, mapping in JOBS:
        root = fetch_flow(flow, key)
        if root is None:
            log(f"  BO QUA {flow}/{key}: khong tai duoc")
            continue
        dims = DIM_ORDER[flow]
        n_series = 0
        for s in root.iter():
            if localname(s.tag) != "Series":
                continue
            skey = tuple(s.get(d) for d in dims)
            if skey not in mapping:
                continue
            sid, name, group, unit = mapping[skey]
            meta[sid] = (name, group, unit)
            bucket = data.setdefault(sid, {})
            for o in s:
                if localname(o.tag) != "Obs":
                    continue
                d = period_to_date(o.get("TIME_PERIOD"))
                v = o.get("OBS_VALUE")
                if d and v not in (None, "", "NaN"):
                    try:
                        bucket[d] = float(v)
                    except ValueError:
                        pass
            n_series += 1
        log(f"  {flow}/{key}: {n_series} series, "
            + ", ".join(f"{mapping[k][0]}={len(data.get(mapping[k][0], {}))} obs"
                        for k in mapping if mapping[k][0] in data))
    return data, meta


def prev_month(d):
    y, m = int(d[:4]), int(d[5:7])
    m -= 1
    if m == 0:
        y, m = y - 1, 12
    return f"{y:04d}-{m:02d}"


def prev_year(d):
    return f"{int(d[:4])-1:04d}-{d[5:7]}"


def add_derived(data, meta):
    """Tinh YoY/MoM cho CPI & IIP index, YoY cho XNK, can can thuong mai."""
    derived = {}
    for sid in list(data):
        if not sid.startswith("CPI"):
            continue
        base_name = meta[sid][0]
        for suffix, fn, label in (("_YOY", prev_year, "YoY %"), ("_MOM", prev_month, "MoM %")):
            out = {}
            for d, v in data[sid].items():
                pv = data[sid].get(fn(d))
                if pv:
                    out[d] = round((v / pv - 1) * 100, 4)
            if out:
                derived[sid + suffix] = out
                meta[sid + suffix] = (f"{base_name} - {label}", "CPI", "%")
    for sid, label in (("EXPORT_USD", "Xuat khau"), ("IMPORT_USD", "Nhap khau")):
        if sid in data:
            out = {}
            for d, v in data[sid].items():
                pv = data[sid].get(prev_year(d))
                if pv:
                    out[d] = round((v / pv - 1) * 100, 4)
            if out:
                derived[sid.replace("_USD", "_YOY")] = out
                meta[sid.replace("_USD", "_YOY")] = (f"{label} hang hoa - YoY %", "TRADE", "%")
    if "EXPORT_USD" in data and "IMPORT_USD" in data:
        out = {}
        for d, x in data["EXPORT_USD"].items():
            m = data["IMPORT_USD"].get(d)
            if m is not None:
                out[d] = x - m
        derived["TRADE_BAL_USD"] = out
        meta["TRADE_BAL_USD"] = ("Can can thuong mai hang hoa (X-M)", "TRADE", "USD")
    data.update(derived)


def load_master():
    rows = {}
    if MASTER.exists():
        with open(MASTER, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                rows[(r["date"], r["series_id"])] = r
    return rows


def main():
    log("=== BAT DAU fetch macro VN (IMF SDMX) ===")
    data, meta = pull_all()
    if not data:
        log("KHONG co du lieu moi nao — giu nguyen master. KET THUC.")
        sys.exit(1)
    add_derived(data, meta)

    old = load_master()
    n_old = len(old)
    for sid, series in data.items():
        name, group, unit = meta[sid]
        for d, v in series.items():
            old[(d, sid)] = {
                "date": d, "series_id": sid, "series_name": name,
                "group": group, "unit": unit, "value": repr(v),
                "source": "IMF_SDMX",
            }
    rows = sorted(old.values(), key=lambda r: (r["date"], r["group"], r["series_id"]))

    tmp = MASTER.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(MASTER)

    latest = max(r["date"] for r in rows)
    n_series = len({r["series_id"] for r in rows})
    log(f"Master: {len(rows)} dong (+{len(rows)-n_old} moi), {n_series} series, moi nhat {latest}")
    log("=== XONG ===")


if __name__ == "__main__":
    main()
