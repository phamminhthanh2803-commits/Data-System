# -*- coding: utf-8 -*-
"""Tran quy dinh (ldr_cap, sfl_cap) - dung tu VAN BAN PHAP LUAT, khong phai tu API.

Hai chi tieu nay khong co nguon may doc duoc: chung la con so trong thong tu, chi doi
khi NHNN ban hanh van ban moi. Nhung KHONG phai "nhap tay" tung dong - chung la ham
BAC THANG theo thoi gian, khai bao mot lan o day roi sinh ra chuoi theo thang.

Muon cap nhat khi co thong tu moi: them mot dong vao SFL_STEPS / LDR_STEPS, chay lai
`python fetch_all.py --only caps`. Khong can sua cho nao khac.

*** CAN THAN ***
- Truoc 2020 KHONG co mot tran LDR chung cho ca he thong: Thong tu 36/2014 cho NHTM
  Nha nuoc 90%, NHTM co phan 80%. Vi vay ldr_cap chi bat dau tu 01/01/2020 (TT 22/2019
  gop ve mot muc 85%). Dung so sanh ldr_system truoc 2020 voi chuoi nay.
- Lo trinh SFL bi GIAN hai lan (TT 08/2020 vi Covid) roi bi DAO CHIEU mot lan
  (TT 25/2026 nang tu 30% len 40%). Cac moc duoi day la lo trinh THUC TE da ap dung,
  khong phai lo trinh du kien trong van ban goc.
"""
from __future__ import annotations

import datetime as dt

from common import log, row

N_POLICY = ("N03", "Noi rang buoc va nguon")

# (ngay hieu luc, tran %, van ban) - moc ap dung cho ngan hang va chi nhanh NH nuoc ngoai
SFL_STEPS = [
    ("2016-07-01", 60.0, "TT 06/2016 sua TT 36/2014"),
    ("2017-01-01", 50.0, "TT 06/2016 sua TT 36/2014"),
    ("2018-01-01", 45.0, "TT 19/2017 sua TT 36/2014"),
    ("2019-01-01", 40.0, "TT 19/2017; TT 22/2019 giu nguyen"),
    ("2021-10-01", 37.0, "TT 08/2020 sua TT 22/2019"),
    ("2022-10-01", 34.0, "TT 08/2020 sua TT 22/2019"),
    ("2023-10-01", 30.0, "TT 08/2020 sua TT 22/2019"),
    ("2026-07-01", 40.0, "TT 25/2026 sua TT 22/2019"),
]

LDR_STEPS = [
    ("2020-01-01", 85.0, "TT 22/2019 - mot muc chung cho moi loai hinh"),
]

SPEC = {
    "sfl_cap": (SFL_STEPS, "Tran ty le von ngan han cho vay trung dai han"),
    "ldr_cap": (LDR_STEPS, "Tran ty le du no cho vay so voi tong tien gui"),
}


def _month_ends(start: str, end: dt.date):
    """Sinh ngay cuoi thang tu thang chua `start` den thang chua `end`."""
    y, m = int(start[:4]), int(start[5:7])
    while (y, m) <= (end.year, end.month):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        last = dt.date(ny, nm, 1) - dt.timedelta(days=1)
        yield min(last, end)
        y, m = ny, nm


def _value_at(steps, day: str):
    """Tran co hieu luc tai ngay `day` - buoc cuoi cung co ngay hieu luc <= day."""
    hit = None
    for eff, val, doc in steps:
        if eff <= day:
            hit = (val, doc)
    return hit


def fetch_all(_session=None) -> list:
    today = dt.date.today()
    out = []
    for sid, (steps, name) in SPEC.items():
        for d in _month_ends(steps[0][0], today):
            day = d.isoformat()
            hit = _value_at(steps, day)
            if not hit:
                continue
            val, doc = hit
            out.append(row(day, sid, val, series_name=name, unit="%", freq="E",
                           source="TT-NHNN · " + doc,
                           node_id=N_POLICY[0], node_name=N_POLICY[1]))
    log("  tran quy dinh: %d dong (%s)"
        % (len(out), ", ".join("%s=%g%%" % (s, _value_at(SPEC[s][0], today.isoformat())[0])
                               for s in SPEC)))
    return out


if __name__ == "__main__":
    from common import setup_stdout
    setup_stdout()
    for r in fetch_all()[-6:]:
        print(r["date"], r["series_id"], r["value"], r["source"])
