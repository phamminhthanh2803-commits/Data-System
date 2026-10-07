# -*- coding: utf-8 -*-
"""Dong von ngoai sinh: khoi ngoai mua rong toan thi truong (node N02).

Nguon: API VNDirect finfo `v4/foreigns` (cong khai, tu 08/2018), don vi VND.

PHAM VI DA THU HEP (08/09/2026): truoc day module nay con keo thanh khoan 3 san
(turnover_*) va tach rieng mua/ban cua khoi ngoai cho node N13-N16. User theo doi
thanh khoan thi truong bang file rieng nen ca khoi N13-N16 da bi bo khoi tool.
Chi giu lai mua rong o node N02 vi day la INPUT cua so do truyen dan (dong von
ngoai sinh), khong phai ket qua o cuoi chuoi.
"""
from __future__ import annotations

import json

from common import get, log, row

VND_FOREIGN = ("https://api-finfo.vndirect.com.vn/v4/foreigns"
               "?q=code:VNINDEX~tradingDate:gte:{start}&size=9990&sort=tradingDate")
NODE = ("N02", "Dong von ngoai sinh")


def fetch_all(session, start: str) -> list:
    txt = get(session, VND_FOREIGN.format(start=start), tries=3)
    if not txt:
        return []
    try:
        data = json.loads(txt).get("data") or []
    except Exception as e:                                        # noqa: BLE001
        log("  X khoi ngoai: JSON loi (%s)" % e)
        return []
    out = []
    for it in data:
        d, net = it.get("tradingDate"), it.get("netVal")
        if not d or net is None:
            continue
        out.append(row(d, "fii_net_val", float(net) / 1e9,
                       series_name="Khoi ngoai mua rong toan TT", unit="ty VND",
                       freq="D", source="VNDirect",
                       node_id=NODE[0], node_name=NODE[1]))
    log("  khoi ngoai: %d dong, moi nhat %s"
        % (len(out), max(x["date"] for x in out) if out else "-"))
    return out
