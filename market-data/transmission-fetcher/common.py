# -*- coding: utf-8 -*-
r"""Ha tang chung cho transmission-fetcher.

14/09/2026: phan dung chung (session gia Chrome, get co retry, vn_number, vn_date, safe_to_csv, log, setup_stdout)
da chuyen len D:\market-data\mdlib.py de dung chung cho ca cum; file nay chi con phan RIENG cua transmission:
ROOT/MASTER/NODES_CSV/COLS, row(), merge_master(). Cac module khac van `from common import ...` nhu cu.
"""
from __future__ import annotations

import os
import sys
import datetime as dt

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # D:\market-data
from mdlib import (HAS_CURL, IMPERSONATE, UA, BROWSER_PROFILES, BROWSER_HEADERS, API_HEADERS,  # noqa: E402,F401
                   log, setup_stdout, new_session, get, vn_number, vn_date, safe_to_csv)

ROOT = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(ROOT, "transmission-master.csv")
NODES_CSV = os.path.join(ROOT, "nodes.csv")

COLS = ["date", "node_id", "node_name", "series_id", "series_name",
        "freq", "unit", "value", "source", "fetched_at"]


def row(date, series_id, value, *, series_name, unit, freq, source, node_id, node_name):
    return {
        "date": date, "node_id": node_id, "node_name": node_name,
        "series_id": series_id, "series_name": series_name,
        "freq": freq, "unit": unit, "value": value, "source": source,
        "fetched_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def merge_master(new_rows, path: str = MASTER) -> pd.DataFrame:
    """Gop du lieu moi vao master, dedup (date, series_id) keep last."""
    new = pd.DataFrame(new_rows, columns=COLS) if not isinstance(new_rows, pd.DataFrame) else new_rows
    if len(new):
        new = new.dropna(subset=["date", "series_id", "value"])
    parts = []
    for p in (path, path + ".pending.csv"):        # nuot lai phan bi ket lan truoc
        if os.path.exists(p):
            old = pd.read_csv(p, dtype={"date": str}, encoding="utf-8-sig")
            for c in COLS:
                if c not in old.columns:
                    old[c] = pd.NA
            parts.append(old[COLS])
    parts.append(new[COLS])
    df = pd.concat(parts, ignore_index=True)
    df = df.dropna(subset=["date", "series_id"])
    df = df.drop_duplicates(subset=["date", "series_id"], keep="last")
    df = df.sort_values(["series_id", "date"]).reset_index(drop=True)
    if safe_to_csv(df, path) and os.path.exists(path + ".pending.csv"):
        os.remove(path + ".pending.csv")
    return df


