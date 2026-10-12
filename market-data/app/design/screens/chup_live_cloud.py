# -*- coding: utf-8 -*-
"""Kiem chung + chup CHE DO CLOUD cua lop live (12/10/2026): app chay voi RT_ROOT = thu muc trong + RT_CLOUD=1 (ep cloud vi bo thu
laptop van dang chay) + MD_ROOT=D:\\pipeline-data\\market-data, server test 8775. data_live tu keo gdrive:pipeline-data/realtime/<hom nay>/
ve moi 60 s -> thanh LIVE phai ghi "live 1 phut (cloud)", chart co overlay, Kho du lieu co dong "Nguon cloud".
Anh: 16-live-cloud.png (Tong quan) + 16-live-cloud-kho.png.  Chay: python chup_live_cloud.py [port]"""
import re
import sys
import time

from playwright.sync_api import sync_playwright

OUT = r"D:\market-data\app\design\screens"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8775
PAGES = [("16-live-cloud", "tong-quan/tong-quan", 2600), ("16-live-cloud-kho", "tong-quan/kho", 2600),
         (None, "ttck/vn/dong-tien", 5000)]
with sync_playwright() as p:
    try:
        b = p.chromium.launch(channel="chrome", headless=True)
    except Exception:  # noqa: BLE001
        b = p.chromium.launch(headless=True)
    for name, q, h in PAGES:
        ctx = b.new_context(viewport={"width": 1440, "height": h}, device_scale_factor=1, color_scheme="light")
        pg = ctx.new_page()
        t0 = time.time()
        txt = ""
        # cho toi khi thread cloud keo xong (toi da 150 s): thanh LIVE hien "(cloud)"
        while time.time() - t0 < 150:
            pg.goto(f"http://localhost:{PORT}/?trang={q}&live=1", wait_until="load")
            t1 = time.time()
            while time.time() - t1 < 60:
                txt = pg.inner_text("body")
                if "Phiên gần nhất:" in txt:
                    break
                time.sleep(0.5)
            if "(cloud)" in txt or q != "tong-quan/tong-quan":
                break
            time.sleep(10)
        time.sleep(3)
        txt = pg.inner_text("body")
        bad = [k for k in ("Traceback", "KeyError", "ValueError", "TypeError", "AttributeError", "NameError", "Lỗi khi dựng thẻ") if k in txt]
        live_bar = [ln for ln in txt.split("\n") if "● LIVE" in ln and ("dữ liệu" in ln or "nguồn" in ln)]
        print(q, f"{time.time() - t0:.0f}s", "LOI:" + ",".join(bad) if bad else "khong traceback",
              "| cloud:", "(cloud)" in txt, "| LIVE marker:", txt.count("● LIVE"), "| nguon cloud (kho):", "Nguồn cloud" in txt,
              "| thanh LIVE:", (live_bar[0][:200] if live_bar else "-"), flush=True)
        if name:
            pg.screenshot(path=OUT + "\\" + name + ".png", full_page=True)
        pg.close()
        ctx.close()
    b.close()
