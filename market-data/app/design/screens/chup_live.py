# -*- coding: utf-8 -*-
"""Chup full-page cac trang app (server 8770) bang Playwright (Chrome he thong), cho toi khi chan trang render xong."""
import sys, time
from playwright.sync_api import sync_playwright

OUT = r"D:\market-data\app\design\screens"
PAGES = [
    ("11-live-toan-app-tong-quan", "tong-quan/tong-quan&live=1&tan=60", 2400),
    ("11-live-toan-app-hieu-suat", "ttck/vn/hieu-suat&live=1&tan=60", 4400),
    ("11-live-toan-app-dong-tien", "ttck/vn/dong-tien&live=1&tan=60", 5400),
    ("11-live-toan-app-dinh-gia", "ttck/vn/dinh-gia&live=1&tan=60", 3700),
    ("11-live-toan-app-live", "live&live=1&tan=60", 3300),
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
        pg.goto(f"http://localhost:8770/?trang={q}", wait_until="load")
        t0 = time.time()
        ok = False
        while time.time() - t0 < 60:
            txt = pg.inner_text("body")
            if "Phiên gần nhất" in txt and ("render lúc" in txt or "live" not in q or "trang=live" in q or name.endswith("live")):
                ok = True
                break
            time.sleep(0.5)
        time.sleep(3)      # cho Plotly ve xong
        path = f"{OUT}\\{name}.png"
        pg.screenshot(path=path, full_page=True)
        print(name, "ok" if ok else "TIMEOUT", f"{time.time()-t0:.1f}s", path)
        pg.close()
        ctx.close()
    b.close()
