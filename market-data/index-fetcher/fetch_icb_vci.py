# -*- coding: utf-8 -*-
"""Phan nganh ICB 4 cap (ten tieng Viet) cua moi ma tu Vietcap IQ -> raw/vn_icb_vci.csv.

1 request (search-bar tra ~2.100 ma ca da huy niem yet / OTC). App dung de chia dong tien
khoi ngoai / tu doanh theo nganh (thay phan loai TradingView trong vn_screener_meta.csv).

Chay:  python fetch_icb_vci.py"""
import os

import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "raw", "vn_icb_vci.csv")
URL = "https://iq.vietcap.com.vn/api/iq-insight-service/v2/company/search-bar?language=1"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/128.0.0.0 Safari/537.36",
       "Referer": "https://trading.vietcap.com.vn/", "Origin": "https://trading.vietcap.com.vn"}


def main():
    print("Che do: full (1 request search-bar)")
    d = requests.get(URL, headers=HDR, timeout=60).json()["data"]
    rows = []
    for c in d:
        r = {"code": c.get("code"), "floor": c.get("floor"), "ten": c.get("shortName") or c.get("name"),
             "loai_dn": c.get("comTypeCode")}
        for lv in (1, 2, 3, 4):
            icb = c.get(f"icbLv{lv}") or {}
            r[f"icb{lv}_code"] = icb.get("code")
            r[f"icb{lv}"] = icb.get("name")
        rows.append(r)
    df = pd.DataFrame(rows).dropna(subset=["code"]).drop_duplicates("code").sort_values("code")
    if len(df) < 1500:   # API tra thieu -> giu file cu
        print(f"LOI: chi {len(df)} ma, khong ghi de")
        raise SystemExit(1)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"-> {os.path.basename(OUT)}: {len(df)} ma, co ICB cap 2: {df.icb2.notna().sum()}")
    print(f"Da luu {len(df)} ma")


if __name__ == "__main__":
    main()
