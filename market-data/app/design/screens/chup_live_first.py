# -*- coding: utf-8 -*-
"""Chup full-page cac trang app (server test 8772, MD_ROOT=D:\pipeline-data\market-data) sau khi co lop nguon live-first (09/10/2026)."""
import sys, time
from playwright.sync_api import sync_playwright

OUT = r"D:\market-data\app\design\screens"
PORT = 8772
PAGES = [
    ("13-live-first-tong-quan", "tong-quan/tong-quan&live=1&tan=60", 2400),
    ("13-live-first-hieu-suat", "ttck/vn/hieu-suat&live=1&tan=60", 4400),
    ("13-live-first-dong-tien", "ttck/vn/dong-tien&live=1&tan=60", 5400),
    ("13-live-first-dinh-gia", "ttck/vn/dinh-gia&live=1&tan=60", 3700),
    ("13-live-first-kho", "tong-quan/kho", 2400),
]
only = sys.argv[1:]
with sync_playwright() as p:
    try:
        b = p.chromium.launch(channel="chrome", headless=True)
    except Exception:
        b = p.chromium.launch(headless=True)
    for name, q, h in PAGES:
        if only and name not in only:
            continue
        ctx = b.new_context(viewport={"width": 1440, "height": h}, device_scale_factor=1, color_scheme="light")
        pg = ctx.new_page()
        t0 = time.time()
        pg.goto(f"http://localhost:{PORT}/?trang={q}", wait_until="load")
        ok = False
        while time.time() - t0 < 90:
            txt = pg.inner_text("body")
            if "Phiên gần nhất" in txt:
                ok = True
                break
            time.sleep(0.5)
        t_render = time.time() - t0
        time.sleep(3)
        txt = pg.inner_text("body")
        bad = [k for k in ("Traceback", "Error:", "KeyError", "ValueError", "TypeError", "AttributeError") if k in txt]
        path = OUT + "\\" + name + ".png"
        pg.screenshot(path=path, full_page=True)
        print(name, "ok" if ok else "TIMEOUT", f"{t_render:.1f}s", "LOI:" + ",".join(bad) if bad else "khong traceback", path, flush=True)
        pg.close()
        ctx.close()
    b.close()
