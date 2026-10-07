# -*- coding: utf-8 -*-
"""Tai PDF cong bo ty le an toan von (CBTT TT41) cua tung ngan hang -> OCR -> doc CAR -> master.

    python cbtt_fetch.py             # tai cac URL trong cbtt_urls.csv chua co file, OCR, parse, gop
    python cbtt_fetch.py --no-merge  # chi tai + OCR + parse (xem cbtt/car_bank.csv)
    python cbtt_fetch.py --only VPB  # mot ngan hang

Dau vao la cbtt_urls.csv (ticker, date, url, note). URL do tim bang tay/tim kiem web - moi ngan
hang mot kieu website nen khong co crawler chung; them dong moi vao CSV la lan chay sau tu tai.
File luu cbtt/<TICKER>/<TICKER>-CAR-<date>.pdf, .md nam canh (pdf2md.py cua D:/bctc/pdf-detector).

PDF scan (ACB, CTG, NAB, STB): OCR mac dinh (psm 6, 300 dpi) doc hong bang -> cot `note` ghi
"psm 4" thi OCR lai voi --psm 4 --dpi 400 --layout off (da thu: CTG qua duoc, STB van hong).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

import pandas as pd

from common import log, setup_stdout

ROOT = os.path.dirname(os.path.abspath(__file__))
CBTT = os.path.join(ROOT, "cbtt")
URLS = os.path.join(ROOT, "cbtt_urls.csv")
PDF2MD = os.path.join(os.path.normpath(os.environ.get("BCTC_ROOT", "D:/bctc")), "pdf-detector", "markitdown-tool", "pdf2md.py")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"


def _download(url: str, dest: str) -> bool:
    import requests
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "application/pdf,*/*"}, timeout=90)
    except Exception as e:                                             # noqa: BLE001
        log("  ! loi tai: %s" % e)
        return False
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        # cong Liferay/WebSphere (/wps/wcm/connect/...) can ?MOD=AJPERES moi tra file
        if "wps/wcm/connect" in url and "MOD=AJPERES" not in url:
            return _download(url + ("&" if "?" in url else "?") + "MOD=AJPERES", dest)
        log("  ! khong phai PDF (HTTP %s, %d byte): %s" % (r.status_code, len(r.content), url[:90]))
        return False
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    open(dest, "wb").write(r.content)
    return True


def _ocr(pdf: str, note: str) -> None:
    args = [sys.executable, PDF2MD, pdf, "--ocr", "auto"]
    if "psm 4" in (note or ""):
        args += ["--ocr", "force", "--psm", "4", "--dpi", "400", "--layout", "off", "-f"]
    subprocess.run(args, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--no-merge", action="store_true")
    ap.add_argument("--force", action="store_true", help="tai lai ca file da co")
    args = ap.parse_args()

    df = pd.read_csv(URLS, dtype=str).fillna("")
    if args.only:
        df = df[df.ticker.str.upper() == args.only.upper()]
    n_new = 0
    for r in df.itertuples():
        t, d = r.ticker.upper(), r.date
        pdf = os.path.join(CBTT, t, "%s-CAR-%s.pdf" % (t, d))
        md = pdf[:-4] + ".md"
        if os.path.exists(pdf) and not args.force:
            if not os.path.exists(md):
                log("%s %s: co PDF, chua co .md -> OCR" % (t, d))
                _ocr(pdf, r.note)
            continue
        log("%s %s: tai %s" % (t, d, r.url[:80]))
        if _download(r.url, pdf):
            n_new += 1
            _ocr(pdf, r.note)
            log("  -> %s (%s)" % (os.path.basename(md), "ok" if os.path.exists(md) else "OCR LOI"))
    log("Tai moi %d file." % n_new)

    cmd = [sys.executable, os.path.join(ROOT, "cbtt_parse.py")]
    if not args.no_merge:
        cmd.append("--merge")
    if args.only:
        cmd += ["--only", args.only]
    subprocess.run(cmd, check=False)


if __name__ == "__main__":
    main()
