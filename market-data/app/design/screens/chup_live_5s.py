# -*- coding: utf-8 -*-
"""Kiem chung + chup KENH 5 GIAY cua lop live (13/10/2026): bo thu test local `dnse_stream.py --no-dnse --serve-port 8787
--push-remote gdrive:pipeline-data/realtime-test` (HTTP + Cloudflare quick tunnel, tunnel.json len Drive test) + app cong 8777 voi
RT_ROOT = thu muc trong, RT_CLOUD=1, RT_REMOTE=gdrive:pipeline-data/realtime-test, MD_ROOT=D:\\pipeline-data\\market-data.
data_live doc tunnel.json -> GET parquet moi 5 s -> thanh LIVE phai ghi "live 5 s (cloud)" + "Cloudflare tunnel", chart co overlay,
Kho du lieu co dong "Nguon cloud ... tunnel ... tre x s". Anh: 18-live-5s.png (Tong quan) + 18-live-5s-kho.png.
Chay: python chup_live_5s.py [port]"""
import sys
import time

from playwright.sync_api import sync_playwright

OUT = r"D:\market-data\app\design\screens"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8777
PAGES = [("18-live-5s", "tong-quan/tong-quan", 2600), ("18-live-5s-kho", "tong-quan/kho", 2600)]
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
        while time.time() - t0 < 150:              # cho thread tunnel keo xong: thanh LIVE hien "live 5 s (cloud)"
            pg.goto(f"http://localhost:{PORT}/?trang={q}&live=1&tan=5", wait_until="load")
            t1 = time.time()
            while time.time() - t1 < 60:
                txt = pg.inner_text("body")
                if "Phiên gần nhất:" in txt:
                    break
                time.sleep(0.5)
            if "live 5 s (cloud)" in txt or q != "tong-quan/tong-quan":
                break
            time.sleep(10)
        time.sleep(6)                               # vai vong 5 s de so lieu doi
        txt = pg.inner_text("body")
        bad = [k for k in ("Traceback", "KeyError", "ValueError", "TypeError", "AttributeError", "NameError", "Lỗi khi dựng thẻ") if k in txt]
        live_bar = [ln for ln in txt.split("\n") if "● LIVE dữ liệu" in ln]
        kho = [ln for ln in txt.split("\n") if "Nguồn cloud" in ln]
        print(q, f"{time.time() - t0:.0f}s", "LOI:" + ",".join(bad) if bad else "khong traceback",
              "| 5s:", "live 5 s (cloud)" in txt, "| LIVE marker:", txt.count("● LIVE"),
              "| thanh LIVE:", (live_bar[0][:220] if live_bar else "-"), "| kho:", (kho[0][:300] if kho else "-"), flush=True)
        pg.screenshot(path=OUT + "\\" + name + ".png", full_page=True)
        pg.close()
        ctx.close()
    b.close()
