# -*- coding: utf-8 -*-
"""Chan lai suat USD: keo tu FRED (St. Louis Fed) qua endpoint CSV cong khai.

`fredgraph.csv` KHONG can API key va nhan NHIEU ma trong 1 request (`?id=A,B,C`)
-> keo ca 8 chuoi trong 1 lan goi thay vi 8 lan (FRED phan hoi rat cham, 8 request
roi rac mat toi ~6 phut, gop lai con vai giay).

QUIRK: tu 4 ma tro len FRED tra ve file ZIP (chua 1 CSV cho moi TAN SUAT, vd
'daily.csv' + 'daily,_7-day.csv') thay vi CSV thuan -> phai do byte dau 'PK'.
Moi lan chay keo full lich su roi de merge_master dedup, vi FRED co revise so cu.
"""
from __future__ import annotations

import io
import zipfile

import pandas as pd

from common import get, log, row

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id="
NODE = ("N01", "Lai suat USD")

# series_id noi bo -> (ma FRED, ten, don vi, tan suat)
SERIES = {
    "us_sofr":             ("SOFR",      "SOFR qua dem",                 "%/nam", "D"),
    "us_effr":             ("EFFR",      "Fed funds hieu luc (EFFR)",    "%/nam", "D"),
    "us_fed_target_upper": ("DFEDTARU",  "Tran lai suat muc tieu Fed",   "%/nam", "D"),
    "us_tbill_4w":         ("DTB4WK",    "Tin phieu KB My 4 tuan",       "%/nam", "D"),
    "us_tbill_3m":         ("DTB3",      "Tin phieu KB My 3 thang",      "%/nam", "D"),
    "us_ust_2y":           ("DGS2",      "Trai phieu KB My 2 nam",       "%/nam", "D"),
    "us_ust_10y":          ("DGS10",     "Trai phieu KB My 10 nam",      "%/nam", "D"),
    "us_dxy_broad":        ("DTWEXBGS",  "Chi so USD (broad)",           "diem",  "W"),
}
BY_CODE = {code: (sid, name, unit, freq) for sid, (code, name, unit, freq) in SERIES.items()}


def _frames(body: bytes) -> list:
    """Tra ve danh sach DataFrame wide (cot 1 = ngay, cac cot sau = ma FRED)."""
    if body[:2] == b"PK":                                    # >=4 ma -> ZIP nhieu CSV
        z = zipfile.ZipFile(io.BytesIO(body))
        return [pd.read_csv(io.BytesIO(z.read(n)))
                for n in z.namelist() if n.lower().endswith(".csv")]
    return [pd.read_csv(io.StringIO(body.decode("utf-8", "replace")))]


def fetch_all(session, start: str = "2015-01-01") -> list:
    body = get(session, FRED + ",".join(c for c, *_ in SERIES.values()),
               tries=3, wait=6, timeout=90, binary=True)
    if not body:
        return []

    out = []
    for df in _frames(body):
        if df.shape[1] < 2:
            continue
        df = df.rename(columns={df.columns[0]: "date"})
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        df = df.dropna(subset=["date"])
        df = df[df["date"] >= start]
        for code in df.columns[1:]:
            meta = BY_CODE.get(code)
            if not meta:
                continue
            sid, name, unit, freq = meta
            # FRED danh dau ngay nghi bang "." -> to_numeric bien thanh NaN
            vals = pd.to_numeric(df[code], errors="coerce")
            ok = vals.notna()
            for d, v in zip(df.loc[ok, "date"], vals[ok]):
                out.append(row(d, sid, float(v), series_name=name, unit=unit, freq=freq,
                               source="FRED", node_id=NODE[0], node_name=NODE[1]))
            if ok.any():
                log("  %-10s %5d dong, moi nhat %s = %s"
                    % (code, int(ok.sum()), df.loc[ok, "date"].iloc[-1], vals[ok].iloc[-1]))
    missing = set(BY_CODE) - {c for df in _frames(body) for c in df.columns}
    if missing:
        log("  ! FRED thieu ma: %s" % ", ".join(sorted(missing)))
    return out
