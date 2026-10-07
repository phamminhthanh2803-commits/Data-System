# -*- coding: utf-8 -*-
"""Ty gia USD/VND cua ngan hang thuong mai (Vietcombank) - dai dien gia thi truong.

Endpoint cong khai co tham so ngay:
    https://www.vietcombank.com.vn/api/exchangerates?date=YYYY-MM-DD
-> lay duoc LICH SU (khac trang ty gia NHNN chi co ngay hien tai).
Ngay nghi VCB tra ve muc ty gia dang hieu luc -> chi keo ngay lam viec (T2-T6).
"""
from __future__ import annotations

import datetime as dt
import json
import time

from common import get, log, row

URL = "https://www.vietcombank.com.vn/api/exchangerates?date=%s"
NODE = ("N04", "Ty gia USD/VND")
EARLIEST = "2020-02-03"      # do thuc te: truoc ngay nay API tra rong -> khoi goi phi

FIELDS = {
    "cash":     ("fx_vcb_buy_cash", "VCB mua tien mat"),
    "transfer": ("fx_vcb_transfer", "VCB mua chuyen khoan"),
    "sell":     ("fx_vcb_sell",     "VCB ban"),
}


def _one_day(session, day: dt.date) -> list:
    txt = get(session, URL % day.isoformat(), tries=2, wait=4, timeout=25)
    if not txt:
        return []
    try:
        j = json.loads(txt)
    except Exception:                                             # noqa: BLE001
        return []
    usd = next((x for x in j.get("Data") or [] if x.get("currencyCode") == "USD"), None)
    if not usd:
        return []                                                 # ngay chua co bang ty gia
    d = (j.get("Date") or "")[:10] or day.isoformat()
    out = []
    for key, (sid, name) in FIELDS.items():
        try:
            v = float(usd[key])
        except (KeyError, TypeError, ValueError):
            continue
        out.append(row(d, sid, v, series_name=name, unit="VND/USD", freq="D",
                       source="Vietcombank", node_id=NODE[0], node_name=NODE[1]))
    return out


def fetch_all(session, start: str, end: str | None = None, pause: float = 0.25) -> list:
    """Keo tung ngay lam viec trong khoang [start, end]."""
    d0 = dt.date.fromisoformat(max(start, EARLIEST))
    d1 = dt.date.fromisoformat(end) if end else dt.date.today()
    out, day = [], d0
    while day <= d1:
        if day.weekday() < 5:                                     # bo T7/CN
            out += _one_day(session, day)
            time.sleep(pause)
        day += dt.timedelta(days=1)
    log("  VCB USD/VND: %d dong tu %s den %s" % (len(out), d0, d1))
    return out
