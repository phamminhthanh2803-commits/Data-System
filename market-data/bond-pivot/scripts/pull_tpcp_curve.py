# -*- coding: utf-8 -*-
"""Keo DUONG CONG LOI SUAT TPCP (spot rate) theo ngay tu hnx.vn — lam benchmark
phi rui ro de tinh SPREAD cho trai phieu doanh nghiep.

Nguon: POST https://www.hnx.vn/ModuleReportBonds/Bond_YieldCurve/SearchAndNextPageYieldCurveData
       form pDate=dd/mm/yyyy -> bang 11 ky han (3 thang .. 20 nam):
       spot lien tuc, par yield, spot theo nam. Co lich su (thu 02/01/2024 van tra).
TLS: www.hnx.vn thieu intermediate GlobalSign -> tu ghep CA bundle tu AIA
     (data/raw/ca_bundle_hnx.pem), KHONG tat verify.

Usage:
  python scripts/pull_tpcp_curve.py update              # 30 ngay gan nhat
  python scripts/pull_tpcp_curve.py backfill [--from 2023-07-19]
Output: data/processed/tpcp_curve.csv (long: ngay, ky_han, ky_han_nam, spot_lien_tuc,
        par_yield, spot_nam) — chi ghi ngay co du lieu (ngay nghi tra bang rong).
"""
import argparse
import csv
import html as H
import os
import re
import sys
from datetime import date, datetime, timedelta

import certifi
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hnx_common import UA, write_file_safe

HNX = "https://www.hnx.vn"
PAGE = "/vi-vn/trai-phieu/duong-cong-loi-suat.html"
EP = "/ModuleReportBonds/Bond_YieldCurve/SearchAndNextPageYieldCurveData"
CA = "data/raw/ca_bundle_hnx.pem"
OUT = "data/processed/tpcp_curve.csv"
FIELDS = ["ngay", "ky_han", "ky_han_nam", "spot_lien_tuc", "par_yield", "spot_nam"]
TENOR_YEARS = {"3 tháng": 0.25, "6 tháng": 0.5, "9 tháng": 0.75, "1 năm": 1, "2 năm": 2,
               "3 năm": 3, "5 năm": 5, "7 năm": 7, "10 năm": 10, "15 năm": 15, "20 năm": 20,
               "30 năm": 30}


def ensure_ca():
    """Ghep certifi + intermediate tai tu AIA cua cert www.hnx.vn."""
    if os.path.exists(CA):
        return CA
    import socket
    import ssl
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    ctx = ssl.create_default_context()
    ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    with socket.create_connection(("www.hnx.vn", 443), timeout=20) as sock:
        with ctx.wrap_socket(sock, server_hostname="www.hnx.vn") as ss:
            cert = x509.load_der_x509_certificate(ss.getpeercert(binary_form=True))
    aia = cert.extensions.get_extension_for_oid(x509.ExtensionOID.AUTHORITY_INFORMATION_ACCESS).value
    pems = []
    for a in aia:
        if a.access_method == x509.AuthorityInformationAccessOID.CA_ISSUERS:
            d = requests.get(a.access_location.value, timeout=30).content
            try:
                c = x509.load_der_x509_certificate(d)
            except Exception:
                c = x509.load_pem_x509_certificate(d)
            pems.append(c.public_bytes(serialization.Encoding.PEM).decode())
    with open(CA, "w") as f:
        f.write(open(certifi.where()).read() + "\n" + "\n".join(pems))
    return CA


def make_session():
    s = requests.Session()
    s.verify = ensure_ca()
    s.headers.update({"User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
                      "Referer": HNX + PAGE})
    s.get(HNX + PAGE, timeout=40)
    return s


def clean(c):
    return H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()


def fnum(s):
    s = s.strip().replace(",", ".")
    try:
        return round(float(s), 6)
    except ValueError:
        return ""


def fetch_day(sess, d):
    r = sess.post(HNX + EP, data={"pDate": d.strftime("%d/%m/%Y")}, timeout=60)
    r.raise_for_status()
    tables = re.findall(r"<table.*?</table>", r.text, re.S)
    if not tables:
        return []
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tables[0], re.S):
        cells = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 4 or cells[0] not in TENOR_YEARS:
            continue
        rows.append({"ngay": d.isoformat(), "ky_han": cells[0],
                     "ky_han_nam": TENOR_YEARS[cells[0]],
                     "spot_lien_tuc": fnum(cells[1]), "par_yield": fnum(cells[2]),
                     "spot_nam": fnum(cells[3])})
    return rows


def load_existing():
    if not os.path.exists(OUT):
        return []
    return list(csv.DictReader(open(OUT, encoding="utf-8-sig")))


def save(rows):
    rows.sort(key=lambda r: (r["ngay"], float(r["ky_han_nam"])))

    def _w(f):
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    if not write_file_safe(OUT, _w):
        sys.exit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["update", "backfill"])
    ap.add_argument("--from", dest="d_from", default="2023-07-19")
    ap.add_argument("--to", dest="d_to", default=date.today().isoformat())
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    existing = load_existing()
    have = {r["ngay"] for r in existing}
    d1 = datetime.strptime(a.d_to, "%Y-%m-%d").date()
    d0 = d1 - timedelta(days=a.days) if a.cmd == "update" else datetime.strptime(a.d_from, "%Y-%m-%d").date()
    sess = make_session()
    new, d, n_req = [], d0, 0
    while d <= d1:
        if d.weekday() < 5 and d.isoformat() not in have:
            try:
                rows = fetch_day(sess, d)
            except Exception as e:
                print("  LOI %s: %s" % (d, e), flush=True)
                rows = []
            n_req += 1
            if rows:
                new.extend(rows)
            if n_req % 50 == 0:
                print("  ... %s: %d ngay co du lieu" % (d, len({r['ngay'] for r in new})), flush=True)
                save(existing + new)
        d += timedelta(days=1)
    rows = existing + new
    save(rows)
    days = sorted({r["ngay"] for r in rows})
    print("tpcp_curve: +%d ngay moi (tong %d ngay, %s..%s)" % (
        len({r['ngay'] for r in new}), len(days), days[0] if days else "", days[-1] if days else ""))


if __name__ == "__main__":
    main()
