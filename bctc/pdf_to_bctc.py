# -*- coding: utf-8 -*-
r"""pdf_to_bctc.py — CHUOI 1 LENH: tai PDF BCTC tu web -> OCR sang Markdown -> boc thanh CSV long (cum D:\bctc).

Truoc day phai chay tay 3 tool: pdf-detector\pdf_detector.py -> pdf-detector\markitdown-tool\pdf2md.py -> md2bctc\md2bctc.py.

    python pdf_to_bctc.py --ticker SSI --url "https://www.ssi.com.vn/..." --include "hợp nhất" [--pages 1-14] [--mode ...]
    python pdf_to_bctc.py --ticker SSI --skip-download            # da co PDF trong pdf-detector\downloads\SSI, chi OCR + boc
    python pdf_to_bctc.py --ticker SSI --skip-download --skip-ocr # da co .md, chi boc CSV
Tham so them cho pdf_detector dat sau "--": python pdf_to_bctc.py --ticker X --url U -- --exclude "mẹ" --overwrite
Ket qua: md2bctc\bctc_master.csv + bctc_notes.csv (gop, dedup theo md2bctc), .md nam canh PDF.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PDFDET = os.path.join(HERE, "pdf-detector", "pdf_detector.py")
PDF2MD = os.path.join(HERE, "pdf-detector", "markitdown-tool", "pdf2md.py")
MD2BCTC = os.path.join(HERE, "md2bctc", "md2bctc.py")
DOWNLOADS = os.path.join(HERE, "pdf-detector", "downloads")


def run(name, cmd, cwd):
    print(f"\n===== {name}: {' '.join(cmd[1:])}", flush=True)
    r = subprocess.run([sys.executable] + cmd, cwd=cwd, env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"})
    if r.returncode != 0:
        print(f"!! {name} exit {r.returncode} -> dung", flush=True)
        sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser(description="PDF BCTC -> Markdown -> CSV")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--url", help="Trang danh sach BCTC (bo qua neu --skip-download)")
    ap.add_argument("--include", help="Tu khoa loc, cach nhau dau phay (vd 'hợp nhất,kiểm toán')")
    ap.add_argument("--pages", help="vd 1-14")
    ap.add_argument("--mode", help="ep che do pdf_detector (masvn/shs/vdsc/...)")
    ap.add_argument("--dir", help="Thu muc PDF (mac dinh pdf-detector\\downloads\\<ticker>)")
    ap.add_argument("--skip-download", action="store_true")
    ap.add_argument("--skip-ocr", action="store_true")
    ap.add_argument("--dpi", default="300")
    ap.add_argument("--year", default="", help="Nam BCTC (neu md2bctc khong tu nhan ra)")
    ap.add_argument("extra", nargs="*", help="tham so them cho pdf_detector (sau --)")
    a = ap.parse_args()
    tk = a.ticker.upper()
    pdf_dir = a.dir or os.path.join(DOWNLOADS, tk)

    if not a.skip_download:
        if not a.url:
            sys.exit("Can --url (hoac --skip-download)")
        cmd = [PDFDET, "--url", a.url, "--ticker", tk, "--out", DOWNLOADS]
        if a.include:
            cmd += ["--include", a.include]
        if a.pages:
            cmd += ["--pages", a.pages]
        if a.mode:
            cmd += ["--mode", a.mode]
        run("1/3 TAI PDF", cmd + a.extra, os.path.dirname(PDFDET))
    if not os.path.isdir(pdf_dir):
        sys.exit(f"Khong thay thu muc PDF: {pdf_dir}")
    if not a.skip_ocr:
        run("2/3 PDF -> MARKDOWN (OCR)", [PDF2MD, pdf_dir, "-r", "--dpi", a.dpi], os.path.dirname(PDF2MD))
    cmd = [MD2BCTC, pdf_dir, "-r", "--ticker", tk]
    if a.year:
        cmd += ["--year", a.year]
    run("3/3 MARKDOWN -> CSV", cmd, os.path.dirname(MD2BCTC))
    print(f"\nXONG {tk}. Master: {os.path.join(os.path.dirname(MD2BCTC), 'bctc_master.csv')}", flush=True)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # --help co tieng Viet, console cp1252 se loi
    except Exception:
        pass
    main()
