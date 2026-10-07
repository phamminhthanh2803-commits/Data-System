# -*- coding: utf-8 -*-
r"""backfill_drivers.py - SO LIEU LICH SU CO DINH cho khoi Drivers bo sung (dong 64-85), cac ky pipeline khong co.
Chay 1 lan (lich su khong doi) -> excel_feed\drivers_backfill.csv (key, q, value, source). drivers_extra.market_series()
chi dung cac dong nay khi pipeline THIEU ky do (pipeline luon uu tien).

 foreign_net : mua/ban rong khoi ngoai HOSE theo quy (ty dong), Q1-2010..Q3-2018 - CafeF GDKhoiNgoai.ashx (VNINDEX, theo ngay).
               VNDirect v4/foreigns (nguon cua pipeline) chi co tu 30/08/2018. Doi chieu 31/08/2018: CafeF -27,03 ty = VNDirect -27,03 ty.
               BAY CafeF: ngay dang MM/DD/YYYY, PageSize bi ep 20, moi truy van chi tra ~1 quy -> goi tung quy + phan trang.
 mcap_hose   : von hoa HOSE cuoi quy (ty dong), Q4-2017..Q2-2019 - tong MARKETCAP tung ma HOSE (VNDirect v4/ratios, co tu 15/12/2017)
               x HE SO hieu chinh ve co so von hoa VN-Index: 4 ky trung 07-12/2019 tong tung ma cao hon deu +8,1%..+8,7%
               (ma ngoai ro chi so) -> chia 1,083. Truy van theo NGAY (q=reportDate:...) THIEU MA (lech -17%..+9%) -> phai theo tung ma.
Chay: python backfill_drivers.py
"""
import concurrent.futures as cf
import os
import sys
import time

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "excel_feed", "drivers_backfill.csv")
VALU = os.path.join(os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data")), "market-valuation", "valuation-master.csv")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36"}
VND = "https://api-finfo.vndirect.com.vn/v4"


def qkey(d):
    d = pd.to_datetime(d)
    return "Q" + d.dt.quarter.astype(str) + "-" + d.dt.year.astype(str)


def cafef_foreign(q_from="2010Q1", q_to="2018Q3"):
    url = "https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/GDKhoiNgoai.ashx"
    rows = []
    for p in pd.period_range(q_from, q_to, freq="Q"):
        s, e, page = p.start_time, p.end_time, 1
        while True:
            r = requests.get(url, params={"Symbol": "VNINDEX", "StartDate": f"{s:%m/%d/%Y}", "EndDate": f"{e:%m/%d/%Y}",
                                          "PageIndex": page, "PageSize": 20},
                             headers={**UA, "Referer": "https://cafef.vn/"}, timeout=40)
            d = r.json()["Data"]
            batch = d.get("Data") or []
            rows += batch
            if not batch or page * 20 >= (d.get("TotalCount") or 0) or page > 20:
                break
            page += 1
            time.sleep(0.3)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df.Ngay, format="%d/%m/%Y")
    df = df.drop_duplicates("date")
    df["q"] = qkey(df.date)
    g = df.groupby("q").agg(net=("GTDGRong", "sum"), days=("date", "count"))
    g = g[g.days >= 50]
    return pd.DataFrame({"key": "foreign_net", "q": g.index, "value": g.net.values / 1e9,
                         "source": "CafeF GDKhoiNgoai VNINDEX (tong ngay)"})


def vnd_mcap_hose(factor=None):
    st = requests.get(f"{VND}/stocks", params={"q": "type:STOCK~floor:HOSE", "size": 9999, "fields": "code"},
                      headers=UA, timeout=60).json()["data"]
    codes = sorted({s["code"] for s in st})

    def one(code):
        for _ in range(3):
            try:
                j = requests.get(f"{VND}/ratios", params={"q": f"code:{code}~ratioCode:MARKETCAP~reportDate:lte:2019-12-31",
                                                          "size": 1000, "sort": "reportDate:asc"}, headers=UA, timeout=60).json()
                return [(code, r["reportDate"], r["value"]) for r in j["data"]]
            except Exception:                                                    # noqa: BLE001
                time.sleep(2)
        raise RuntimeError(f"khong lay duoc {code}")

    rows = []
    with cf.ThreadPoolExecutor(6) as ex:
        for res in ex.map(one, codes):
            rows += res
    df = pd.DataFrame(rows, columns=["code", "date", "value"]).drop_duplicates(["code", "date"])
    df["date"] = pd.to_datetime(df.date)
    tot = df.pivot_table(index="date", columns="code", values="value").sort_index().ffill(limit=10).sum(axis=1) / 1e9
    v = pd.read_csv(VALU)
    v = v[(v.code == "VNINDEX") & (v.ratio == "MARKETCAP")]
    v = pd.Series(v.value.values / 1e9, index=pd.to_datetime(v.date)).sort_index()
    ov = [pd.Timestamp(x) for x in ("2019-07-19", "2019-08-30", "2019-09-30", "2019-12-31")]
    ratios = [tot[:d].iloc[-1] / v[:d].iloc[-1] for d in ov]
    factor = factor or sum(ratios) / len(ratios)
    print("  he so tong tung ma / von hoa VN-Index o ky trung:", [round(x, 4) for x in ratios], "-> chia", round(factor, 4))
    q = (tot / factor).resample("QE").last()
    q = q[q.index < pd.Timestamp("2019-07-01")]
    return pd.DataFrame({"key": "mcap_hose", "q": qkey(pd.Series(q.index)).values, "value": q.values,
                         "source": f"VNDirect MARKETCAP tung ma HOSE / {factor:.4f}"})


def main():
    parts = [cafef_foreign(), vnd_mcap_hose()]
    out = pd.concat(parts, ignore_index=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(out.groupby("key").q.agg(["count", "first", "last"]).to_string())
    print("->", OUT)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
