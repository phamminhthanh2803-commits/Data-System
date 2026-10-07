# -*- coding: utf-8 -*-
"""Gop du lieu tu cac tool khac dang co san tren may (khong goi mang).

Hien lay tu D:\\market-data\\macro-fetcher (IMF SDMX, thang):
    TRADE_BAL_USD   -> trade_balance   (node N02 - nhap sieu)
    EXPORT_USD      -> exports         (node N02)
    IMPORT_USD      -> imports         (node N02)
    FX_RESERVES_USD -> fx_reserves     (node N06 - NHNN ban can thiep thi du tru giam)
    VND_USD_EOP     -> fx_imf_eop      (node N04 - doi chieu voi VCB/NHNN)

Duong dan doc tu bien moi truong MACRO_MASTER neu co, khong thi mac dinh
D:\\market-data\\macro-fetcher\\macro_vn_master.csv. Thieu file thi bo qua (khong lam hong pipeline).
"""
from __future__ import annotations

import os

import pandas as pd

from common import log, row

MACRO_MASTER = os.environ.get("MACRO_MASTER") or os.path.join(
    os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data")), "macro-fetcher", "macro_vn_master.csv")

# series_id nguon -> (series_id dich, ten, don vi dich, he so, node_id, node_name)
MAP = {
    "TRADE_BAL_USD":   ("trade_balance", "Can can thuong mai hang hoa", "trieu USD", 1e-6,
                        "N02", "Dong von ngoai sinh"),
    "EXPORT_USD":      ("exports", "Xuat khau hang hoa FOB", "trieu USD", 1e-6,
                        "N02", "Dong von ngoai sinh"),
    "IMPORT_USD":      ("imports", "Nhap khau hang hoa CIF", "trieu USD", 1e-6,
                        "N02", "Dong von ngoai sinh"),
    "FX_RESERVES_USD": ("fx_reserves", "Du tru ngoai hoi (gom vang)", "trieu USD", 1e-6,
                        "N06", "NHNN ban forward"),
    "VND_USD_EOP":     ("fx_imf_eop", "Ty gia VND/USD cuoi ky (IMF)", "VND/USD", 1.0,
                        "N04", "Ty gia USD/VND"),
    # song song car_min_system (TT36) / car_tt41 (NHNN): pham vi TOAN BO to chuc nhan tien gui
    "CAR_IMF":         ("car_imf_system", "CAR to chuc nhan tien gui (IMF FSI)", "%", 1.0,
                        "N10", "Room va chi phi von NH"),
}
FREQ = {"CAR_IMF": "Q"}


def _month_end(ym: str) -> str | None:
    """'2026-06' -> '2026-06-30' de cung truc thoi gian voi cac chuoi khac."""
    try:
        return (pd.Period(ym, freq="M").end_time).strftime("%Y-%m-%d")
    except Exception:                                             # noqa: BLE001
        return None


def fetch_all(_session=None) -> list:
    if not os.path.exists(MACRO_MASTER):
        log("  ! khong thay %s -> bo qua nguon local" % MACRO_MASTER)
        return []
    df = pd.read_csv(MACRO_MASTER, dtype={"date": str}, encoding="utf-8-sig")
    df = df[df["series_id"].isin(MAP)]
    out = []
    for _, r in df.iterrows():
        sid, name, unit, factor, node_id, node_name = MAP[r["series_id"]]
        d = _month_end(r["date"])
        if not d or pd.isna(r["value"]):
            continue
        out.append(row(d, sid, round(float(r["value"]) * factor, 4), series_name=name,
                       unit=unit, freq=FREQ.get(r["series_id"], "M"), source="IMF/macro-fetcher",
                       node_id=node_id, node_name=node_name))
    n = df.groupby("series_id").size().to_dict()
    log("  macro-fetcher: %d dong (%s)" % (len(out), ", ".join("%s=%d" % kv for kv in sorted(n.items()))))
    return out
