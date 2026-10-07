# -*- coding: utf-8 -*-
"""Lai suat cho vay BINH QUAN tung ngan hang cong bo hang thang -> nhom Big4 vs co phan.

Tu 2024 NHNN bat moi ngan hang dang "lai suat cho vay binh quan + chenh lech lai suat" tren
website hang thang. Khong co trang tong hop nao cua NHNN de cao, nen moi ngan hang mot bo doc:

  BID  trang thang, URL co mau .../bidv-cong-bo-lai-suat-cho-vay-binh-quan-ky-thang-MM-YYYY
       (co so tu 10/2025; trang cac thang truoc ton tai nhung rong)  -> lich su
  EIB  mot trang cho ca nam, moi thang mot bang                       -> lich su trong nam
  AGR  mot trang, chi thang hien tai                                  -> anh chup, boi dan
  VIB  mot trang, chi thang hien tai, tach KHCN / KHDN                -> anh chup, boi dan
  VCB  da co san qua dulieukinhte (lending_rate_avg)                  -> chi gan them ma

Series: lend_avg_<ma> (%/nam), lend_spread_<ma> (diem %), thang cuoi ky. Tong hop:
  lending_rate_big4 = trung binh don gian VCB, BID, AGR (CTG chua co bo doc)
  lending_rate_jsc  = trung binh don gian cac NH co phan co so trong thang
Trung binh DON GIAN, khong theo du no - ghi ro tren dashboard. Chi tinh thang co >= 2 NH.

Chua doc duoc: CTG (file dinh kem nap bang JS), ACB (link "tai day" tung thang), TCB (PDF KHCN,
ten file khong on dinh), MBB/VPB/STB/HDB/TPB (chua tim thay trang). Them dan vao ADAPTERS.
"""
from __future__ import annotations

import datetime as dt
import re

from bs4 import BeautifulSoup

from common import get, log, new_session, row

N_TT1 = ("N11", "Lai suat TT1")
BIG4 = {"vcb", "bid", "ctg", "agr"}

NUM = re.compile(r"(\d{1,2}[.,]\d{1,2})")
MONTH = re.compile(r"th[aáÁ]ng\s*(\d{1,2})\s*(?:[/\-]|n[aăĂ]m)?\s*(\d{4})", re.I)   # "tháng 7/2026", "THÁNG 01 NĂM 2026"


def _f(s):
    m = NUM.search(str(s))
    return float(m.group(1).replace(",", ".")) if m else None


def _month_end(y, m):
    y, m = int(y), int(m)
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return (dt.date(ny, nm, 1) - dt.timedelta(days=1)).isoformat()


def _rows(t, avg, spread, khcn=None, khdn=None, d=None, src=""):
    out = []
    if avg is not None:
        out.append(row(d, "lend_avg_" + t, avg, series_name="Lai suat cho vay binh quan " + t.upper(),
                       unit="%/nam", freq="M", source=src, node_id=N_TT1[0], node_name=N_TT1[1]))
    if spread is not None:
        out.append(row(d, "lend_spread_" + t, spread,
                       series_name="Chenh lech lai suat cho vay - huy dong binh quan " + t.upper(),
                       unit="diem %", freq="M", source=src, node_id=N_TT1[0], node_name=N_TT1[1]))
    for k, v in (("khcn", khcn), ("khdn", khdn)):
        if v is not None:
            out.append(row(d, "lend_avg_%s_%s" % (t, k), v,
                           series_name="Lai suat cho vay binh quan %s %s" % (t.upper(), k.upper()),
                           unit="%/nam", freq="M", source=src, node_id=N_TT1[0], node_name=N_TT1[1]))
    return out


def _text(html):
    return re.sub(r"\s+", " ", BeautifulSoup(html, "html.parser").get_text(" "))


# ------------------------------------------------------------------------------ BIDV
BID_URL = ("https://bidv.com.vn/bidv/tin-tuc/congbothongtinlaisuat_vi/congbolaisuatchovay_vi/"
           "bidv-cong-bo-lai-suat-cho-vay-binh-quan-ky-thang-{m:02d}-{y}")


def bid(session, months):
    out = []
    for y, m in months:
        html = get(session, BID_URL.format(y=y, m=m), tries=1, timeout=40)
        if not html:
            continue
        t = _text(html)
        avg = re.search(r"Lãi suất cho vay bình quân[^0-9]{0,40}(\d+[.,]\d+)", t)
        sp = re.search(r"Chênh lệch lãi suất \(cho vay bình quân[^0-9]{0,80}(\d+[.,]\d+)", t)
        if avg:
            out += _rows("bid", _f(avg.group(1)), _f(sp.group(1)) if sp else None,
                         d=_month_end(y, m), src="BIDV")
    return out


# ------------------------------------------------------------------------------ Eximbank
def eib(session, year):
    html = get(session, "https://eximbank.com.vn/tin-tuc/lai-suat-binh-quan-thang-trong-nam-%d" % year,
               tries=1, timeout=40)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tbl in soup.find_all("table"):
        # nhan thang nam o tieu de ngay truoc bang
        label, node = None, tbl
        for _ in range(8):
            node = node.find_previous(string=MONTH)
            if node is None:
                break
            label = MONTH.search(str(node))
            if label:
                break
        if not label:
            continue
        cells = {r.find_all(["td", "th"])[0].get_text(" ", strip=True).lower():
                 r.find_all(["td", "th"])[-1].get_text(" ", strip=True)
                 for r in tbl.find_all("tr") if len(r.find_all(["td", "th"])) >= 2}
        avg = sp = khcn = khdn = None
        for k, v in cells.items():
            if k.startswith("lãi suất cho vay bình quân") and "đối với" not in k:
                avg = _f(v)
            elif "khách hàng cá nhân" in k or "khcn" in k:
                khcn = _f(v)
            elif "doanh nghiệp" in k or "khdn" in k:
                khdn = _f(v)
            elif k.startswith("chênh lệch"):
                sp = _f(v)
        out += _rows("eib", avg, sp, khcn, khdn, d=_month_end(label.group(2), label.group(1)), src="Eximbank")
    return out


# ------------------------------------------------------------------------------ Agribank
def agr(session):
    html = get(session, "https://www.agribank.com.vn/vn/lai-suat-cho-vay-agribank", tries=1, timeout=40)
    if not html:
        return []
    t = _text(html)
    lab = MONTH.search(t)
    avg = re.search(r"Lãi suất cho vay bình quân\(?\*?\)?\s*(\d+[.,]\d+)", t)
    sp = re.search(r"III\. Chênh lệch\s*(\d+[.,]\d+)", t)
    if not (lab and avg):
        return []
    return _rows("agr", _f(avg.group(1)), _f(sp.group(1)) if sp else None,
                 d=_month_end(lab.group(2), lab.group(1)), src="Agribank")


# ------------------------------------------------------------------------------ VIB
def vib(session):
    html = get(session, "https://www.vib.com.vn/vn/lai-suat-vay-binh-quan/", tries=1, timeout=40)
    if not html:
        return []
    t = _text(html)
    lab = MONTH.search(t)
    khcn = re.search(r"(?:cá nhân|Individual)[^0-9]{0,60}(\d+[.,]\d+)", t, re.I)
    khdn = re.search(r"(?:doanh nghiệp|Enterprise)[^0-9]{0,60}(\d+[.,]\d+)", t, re.I)
    # "Chenh lech" xuat hien ca trong tieu de trang -> lay so dau tien SAU chu do ma < 5 (chenh lech,
    # khong phai lai suat cho vay 9%)
    sp = None
    for m in re.finditer(r"[Cc]hênh lệch[^0-9]{0,160}(\d+[.,]\d+)", t):
        if _f(m.group(1)) is not None and _f(m.group(1)) < 5:
            sp = m
            break
    if not lab or not (khcn or khdn):
        return []
    a, b = (_f(khcn.group(1)) if khcn else None), (_f(khdn.group(1)) if khdn else None)
    avg = round((a + b) / 2, 2) if a is not None and b is not None else (a if a is not None else b)
    return _rows("vib", avg, _f(sp.group(1)) if sp else None, a, b,
                 d=_month_end(lab.group(2), lab.group(1)), src="VIB")


# ------------------------------------------------------------------------------ tong hop
def aggregate(rows, master_df=None):
    """lending_rate_big4 / lending_rate_jsc theo thang tu cac lend_avg_<ma> (gom ca master cu)."""
    import pandas as pd
    parts = [pd.DataFrame(rows)] if rows else []
    if master_df is not None:
        m = master_df[master_df.series_id.str.match(r"^lend_avg_[a-z]{3}$|^lending_rate_avg$")]
        parts.append(m)
    if not parts:
        return []
    df = pd.concat(parts, ignore_index=True)
    df["t"] = df.series_id.str.replace("lending_rate_avg", "lend_avg_vcb").str[-3:]
    df = df[df.series_id.str.match(r"^lend_avg_[a-z]{3}$|^lending_rate_avg$")]
    df = df.sort_values("fetched_at").drop_duplicates(["date", "t"], keep="last")
    out = []
    for grp, sid, name in (("big4", "lending_rate_big4", "Lai suat cho vay binh quan nhom Big4 (TB don gian)"),
                           ("jsc", "lending_rate_jsc", "Lai suat cho vay binh quan nhom NHTM co phan (TB don gian)")):
        sub = df[df.t.isin(BIG4)] if grp == "big4" else df[~df.t.isin(BIG4)]
        for d, g in sub.groupby("date"):
            if len(g) >= 2:
                out.append(row(d, sid, round(float(g.value.mean()), 2), series_name=name + " · n=%d" % len(g),
                               unit="%/nam", freq="M", source="tong hop " + ",".join(sorted(g.t)),
                               node_id=N_TT1[0], node_name=N_TT1[1]))
    return out


def fetch_all(session=None, start_year=2025) -> list:
    session = session or new_session("browser")
    today = dt.date.today()
    months = [(y, m) for y in range(start_year, today.year + 1) for m in range(1, 13)
              if (y, m) <= (today.year, today.month)]
    out = []
    for name, fn in (("BIDV", lambda: bid(session, months)),
                     ("Eximbank", lambda: sum((eib(session, y) for y in range(start_year, today.year + 1)), [])),
                     ("Agribank", lambda: agr(session)),
                     ("VIB", lambda: vib(session))):
        try:
            r = fn()
        except Exception as e:                                             # noqa: BLE001
            log("  ! %s: %s" % (name, e))
            r = []
        n = len({x["date"] for x in r})
        log("  %-9s %d thang%s" % (name, n, "" if n else "  (khong doc duoc)"))
        out += r
    return out


if __name__ == "__main__":
    from common import setup_stdout
    setup_stdout()
    rs = fetch_all()
    import pandas as pd
    d = pd.DataFrame(rs)
    print(d.pivot_table(index="date", columns="series_id", values="value").round(2).tail(14).to_string())
