# -*- coding: utf-8 -*-
"""
fetch_macro_region.py — keo vi mo THANG cho cac nuoc KHU VUC (cung "form" macro_vn_master) tu IMF SDMX,
ra 1 file long-format co them cot `country`: macro_region_master.csv.

Nuoc (ma ISO3 IMF): VNM THA IDN MYS PHL SGP KOR CHN HKG JPN IND (+TWN neu IMF co — thuong KHONG, Dai Loan
khong phai thanh vien IMF).
Series (giong VN): CPI tong + 12 nhom COICOP (+YoY/MoM), ty gia LCU/USD cuoi ky + binh quan, XK FOB / NK CIF
(+YoY, can can), du tru ngoai hoi, IIP (+YoY).

Chay:  python fetch_macro_region.py            # keo full moi lan (IMF revise so cu), merge/dedup theo (date,country,series_id)
Dung chung ham fetch_flow / period_to_date / add_derived cua fetch_macro.py.
"""
import csv
import sys
from datetime import datetime
from pathlib import Path

import fetch_macro as vn   # tai su dung helper + COICOP_VI

HERE = Path(__file__).resolve().parent
MASTER = HERE / "macro_region_master.csv"
LOG = HERE / "fetch_log_region.txt"

COUNTRIES = ["VNM", "THA", "IDN", "MYS", "PHL", "SGP", "KOR", "CHN", "HKG", "JPN", "IND", "TWN"]
FIELDS = ["date", "country", "series_id", "series_name", "group", "unit", "value", "source"]

CCY = {"VNM": "VND", "THA": "THB", "IDN": "IDR", "MYS": "MYR", "PHL": "PHP", "SGP": "SGD",
       "KOR": "KRW", "CHN": "CNY", "HKG": "HKD", "JPN": "JPY", "IND": "INR", "TWN": "TWD"}


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def build_jobs():
    """Moi flow 1 request cho TAT CA nuoc (key COUNTRY = A+B+C). mapping key co them country."""
    cs = "+".join(COUNTRIES)
    jobs = []
    # CPI
    cps = "+".join(vn.COICOP_VI.keys())
    m = {}
    for c in COUNTRIES:
        for cp, name in vn.COICOP_VI.items():
            sid = "CPI_ALL" if cp == "_T" else f"CPI_{cp}"
            m[(c, "CPI", cp, "IX", "M")] = (sid, name, "CPI", "index_2024=100")
    jobs.append(("CPI", f"{cs}.CPI.{cps}.IX.M", m))
    # ER
    m = {}
    for c in COUNTRIES:
        m[(c, "XDC_USD", "EOP_RT", "M")] = ("FX_USD_EOP", "Ty gia noi te/USD cuoi ky", "FX", f"{CCY[c]}/USD")
        m[(c, "XDC_USD", "PA_RT", "M")] = ("FX_USD_AVG", "Ty gia noi te/USD binh quan ky", "FX", f"{CCY[c]}/USD")
    jobs.append(("ER", f"{cs}.XDC_USD.EOP_RT+PA_RT.M", m))
    # ITG
    m = {}
    for c in COUNTRIES:
        m[(c, "XG", "FOB_USD", "M")] = ("EXPORT_USD", "Xuat khau hang hoa FOB", "TRADE", "USD")
        m[(c, "MG", "CIF_USD", "M")] = ("IMPORT_USD", "Nhap khau hang hoa CIF", "TRADE", "USD")
    jobs.append(("ITG", f"{cs}.XG+MG.FOB_USD+CIF_USD.M", m))
    # IL
    m = {c: None for c in COUNTRIES}
    m = {(c, "TRGNV_REVS", "USD", "M"): ("FX_RESERVES_USD", "Du tru ngoai hoi (gom vang)", "RESERVES", "USD")
         for c in COUNTRIES}
    jobs.append(("IL", f"{cs}.TRGNV_REVS.USD.M", m))
    # PI
    m = {}
    for c in COUNTRIES:
        m[(c, "IND", "IX", "M")] = ("IIP_IX", "Chi so san xuat cong nghiep", "IIP", "index")
        m[(c, "IND", "YOY_PCH_PT", "M")] = ("IIP_YOY", "IIP tang truong YoY", "IIP", "%")
    jobs.append(("PI", f"{cs}.IND.IX+YOY_PCH_PT.M", m))
    return jobs


def pull_all():
    """Tra data[country][sid] = {date: value}, meta[sid] = (name, group, unit) (unit FX theo nuoc)."""
    data = {c: {} for c in COUNTRIES}
    meta = {}
    for flow, key, mapping in build_jobs():
        root = vn.fetch_flow(flow, key)
        if root is None:
            log(f"  BO QUA {flow}: khong tai duoc")
            continue
        dims = vn.DIM_ORDER[flow]
        n = 0
        for s in root.iter():
            if vn.localname(s.tag) != "Series":
                continue
            skey = tuple(s.get(d) for d in dims)
            if skey not in mapping:
                continue
            country = skey[0]
            sid, name, group, unit = mapping[skey]
            meta[(country, sid)] = (name, group, unit)
            bucket = data[country].setdefault(sid, {})
            for o in s:
                if vn.localname(o.tag) != "Obs":
                    continue
                d = vn.period_to_date(o.get("TIME_PERIOD"))
                v = o.get("OBS_VALUE")
                if d and v not in (None, "", "NaN"):
                    try:
                        bucket[d] = float(v)
                    except ValueError:
                        pass
            n += 1
        got = {c: len(data[c]) for c in COUNTRIES if data[c]}
        log(f"  {flow}: {n} series | so series/nuoc: {got}")
    return data, meta


def load_master():
    rows = {}
    if MASTER.exists():
        with open(MASTER, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                rows[(r["date"], r["country"], r["series_id"])] = r
    return rows


def main():
    log("=== BAT DAU fetch macro KHU VUC (IMF SDMX) ===")
    data, meta = pull_all()
    if not any(data.values()):
        log("KHONG co du lieu — giu nguyen master.")
        sys.exit(1)
    old = load_master()
    n_old = len(old)
    for c in COUNTRIES:
        if not data[c]:
            continue
        # add_derived cua VN lam viec tren dict {sid: {date: v}} + meta {sid: (...)}
        m_c = {sid: meta[(c, sid)] for sid in data[c]}
        vn.add_derived(data[c], m_c)
        for sid, series in data[c].items():
            name, group, unit = m_c[sid]
            for d, v in series.items():
                old[(d, c, sid)] = {"date": d, "country": c, "series_id": sid, "series_name": name,
                                    "group": group, "unit": unit, "value": repr(v), "source": "IMF_SDMX"}
    rows = sorted(old.values(), key=lambda r: (r["country"], r["group"], r["series_id"], r["date"]))
    tmp = MASTER.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(MASTER)
    per_c = {}
    for r in rows:
        x = per_c.setdefault(r["country"], [0, ""])
        x[0] += 1
        x[1] = max(x[1], r["date"])
    log(f"Master: {len(rows)} dong (+{len(rows) - n_old}); theo nuoc: "
        + ", ".join(f"{c}={n}/{d}" for c, (n, d) in sorted(per_c.items())))
    log("=== XONG ===")


if __name__ == "__main__":
    main()
