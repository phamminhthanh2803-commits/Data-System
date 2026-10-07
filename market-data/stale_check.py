# -*- coding: utf-8 -*-
"""stale_check.py — kiem tra do tuoi master CSV cho Run-Market.ps1.

    python stale_check.py <csv> <max_days> [Ten=col:v1,v2 | Ten=col:!v1,v2 ...]
Khong co nhom -> kiem tra max(date) toan file. In 1 dong:  OK|rows=N|... hoac STALE|<mo ta>|rows=N
"""
import sys
from datetime import datetime

import pandas as pd


def main():
    path, max_days = sys.argv[1], int(sys.argv[2])
    df = pd.read_csv(path, dtype={"date": str}, usecols=lambda c: c in ("date", "source", "series_id", "index_code"))
    groups = sys.argv[3:] or ["ALL="]
    stale, info = [], []
    for g in groups:
        name, _, spec = g.partition("=")
        sub = df
        if spec:
            col, _, vals = spec.partition(":")
            neg = vals.startswith("!")
            vs = [v for v in vals.lstrip("!").split(",") if v]
            m = sub[col].astype(str).isin(vs)
            sub = sub[~m] if neg else sub[m]
        d = sub["date"].dropna().max() if len(sub) else None
        if not d:
            stale.append(f"{name}: khong co du lieu")
            continue
        age = (datetime.now() - datetime.strptime(str(d)[:10], "%Y-%m-%d")).days
        info.append(f"{name}={d}")
        if age > max_days:
            stale.append(f"{name} cu {age} ngay (moi nhat {d})")
    if stale:
        print(f"STALE|{'; '.join(stale)}|rows={len(df)}")
    else:
        print(f"OK|rows={len(df)}|{' '.join(info)}")


if __name__ == "__main__":
    main()
