# -*- coding: utf-8 -*-
"""Lai suat huy dong TT1 (node N11) - cao tu bang tong hop cua Nguoiquansat.

https://dulieu.nguoiquansat.vn/lai-suat : bang HTML render san (khong can JS),
28 ngan hang x 3 ky han (1 thang / 6 thang / 12 thang), don vi %/nam.

CHI CO SO CUA NGAY HIEN TAI (giong 4 trang NHNN) -> chay hang ngay de boi chuoi.
Day la lai suat NIEM YET tren website ngan hang, khong phai lai suat thuc te
huy dong (ngan hang lon thuong thoa thuan them voi mon tien lon) - dung de theo
XU HUONG va CHENH LECH nhom, dung coi la gia von thuc.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata

from bs4 import BeautifulSoup

from common import get, log, row

URL = "https://dulieu.nguoiquansat.vn/lai-suat"
NODE = ("N11", "Lai suat TT1")

# nhom NHTM Nha nuoc (Big4) - Agribank + 3 ma niem yet
BIG4 = {"agribank", "bidv", "vietcombank", "vietinbank"}

TENORS = {1: ("deposit_1m", "1 thang"), 2: ("deposit_6m", "6 thang"), 3: ("deposit_12m", "12 thang")}


def _norm(s: str) -> str:
    """Bo dau roi bo ky tu khong phai chu/so.

    Phai BO DAU truoc: neu chi lam re.sub(r"[^a-z0-9]") thi "Ngan hang" co dau
    thanh "nnhng" (a-co-dau bi xoa han) va moi phep so khop deu truot.
    """
    s = unicodedata.normalize("NFD", str(s or "").lower()).replace("đ", "d")
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]", "", s)


def _num(txt):
    """Trang nay dung DAU CHAM lam thap phan ("3.60" = 3,6%) - KHAC kieu so cua NHNN,
    nen KHONG dung common.vn_number() (ham do coi dau cham la hang nghin -> 360)."""
    s = str(txt or "").strip().replace("%", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def fetch_all(session) -> list:
    html = get(session, URL, tries=3, wait=5)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")

    # dong tieu de co the la <td> chu khong phai <th> -> doc dong dau tien cua bang
    table = None
    for t in soup.find_all("table"):
        first = t.find("tr")
        if not first:
            continue
        head = _norm(" ".join(c.get_text(" ", strip=True) for c in first.find_all(["td", "th"])))
        if "nganhang" in head and "thang" in head:
            table = t
            break
    if table is None:
        log("  ! khong tim thay bang lai suat huy dong")
        return []

    banks = {}
    for tr in table.find_all("tr"):
        c = [x.get_text(" ", strip=True) for x in tr.find_all(["td", "th"])]
        if len(c) < 4 or _norm(c[0]) in ("nganhang", ""):
            continue
        banks[_norm(c[0])] = [_num(c[i]) for i in (1, 2, 3)]
    if not banks:
        log("  ! bang lai suat rong")
        return []

    date = dt.date.today().isoformat()
    out = []
    for idx, (prefix, label) in TENORS.items():
        vals = [v[idx - 1] for v in banks.values() if v[idx - 1] is not None]
        big = [v[idx - 1] for k, v in banks.items() if k in BIG4 and v[idx - 1] is not None]
        if vals:
            out.append(row(date, prefix + "_avg", round(sum(vals) / len(vals), 4),
                           series_name="Lai suat huy dong %s binh quan %d NH" % (label, len(vals)),
                           unit="%/nam", freq="D", source="Nguoiquansat",
                           node_id=NODE[0], node_name=NODE[1]))
        if len(big) >= 3:
            out.append(row(date, prefix + "_big4", round(sum(big) / len(big), 4),
                           series_name="Lai suat huy dong %s nhom Big4" % label,
                           unit="%/nam", freq="D", source="Nguoiquansat",
                           node_id=NODE[0], node_name=NODE[1]))
        if vals:
            out.append(row(date, prefix + "_max", max(vals),
                           series_name="Lai suat huy dong %s cao nhat thi truong" % label,
                           unit="%/nam", freq="D", source="Nguoiquansat",
                           node_id=NODE[0], node_name=NODE[1]))
    log("  lai suat huy dong %s: %d ngan hang, %d chi tieu" % (date, len(banks), len(out)))
    return out
