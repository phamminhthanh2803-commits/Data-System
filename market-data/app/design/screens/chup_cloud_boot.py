# -*- coding: utf-8 -*-
"""Kiem chung + chup CHE DO STREAMLIT CLOUD (cloud_boot, 12/10/2026): app chay voi STREAMLIT_CLOUD=1 + MD_ROOT = thu muc TRONG
+ .streamlit/secrets.toml (RCLONE_CONF) -> lan dau tu keo du lieu tu gdrive:pipeline-data/market-data ve MD_ROOT (st.status tien do),
cac trang chinh mo khong traceback, chan trang co "Cloud: du lieu keo tu Google Drive luc ...".
Anh: 17-cloud-boot.png (Tong quan, ngay sau khi keo xong) + 17-cloud-boot-dong-tien.png.  Chay: python chup_cloud_boot.py [port]"""
import sys
import time

from playwright.sync_api import sync_playwright

OUT = r"D:\market-data\app\design\screens"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8776
PAGES = [("17-cloud-boot", "tong-quan/tong-quan", 2600), (None, "ttck/vn/hieu-suat", 4200),
         ("17-cloud-boot-dong-tien", "ttck/vn/dong-tien", 5000), (None, "ttck/vn/dinh-gia", 3600), (None, "vi-mo/viet-nam/gia-ca", 3000),
         (None, "tong-quan/kho", 2600)]
with sync_playwright() as p:
    try:
        b = p.chromium.launch(channel="chrome", headless=True)
    except Exception:  # noqa: BLE001
        b = p.chromium.launch(headless=True)
    for i, (name, q, h) in enumerate(PAGES):
        ctx = b.new_context(viewport={"width": 1440, "height": h}, device_scale_factor=1, color_scheme="light")
        pg = ctx.new_page()
        t0 = time.time()
        pg.goto(f"http://localhost:{PORT}/?trang={q}&live=0", wait_until="load")
        txt = ""
        seen_status = ""
        while time.time() - t0 < 400:                       # lan dau: cho keo du lieu xong (muc tieu < 90 s)
            txt = pg.inner_text("body")
            if "Lần đầu mở trên cloud" in txt and not seen_status:
                seen_status = f"st.status hien sau {time.time() - t0:.0f}s"
            if "Phiên gần nhất:" in txt:
                break
            time.sleep(0.5)
        time.sleep(2)
        txt = pg.inner_text("body")
        bad = [k for k in ("Traceback", "KeyError", "ValueError", "TypeError", "AttributeError", "NameError", "Lỗi khi dựng thẻ",
                           "THIẾU FILE", "LỖI:") if k in txt]
        foot = [ln for ln in txt.split("\n") if "Phiên gần nhất:" in ln]
        status = [ln for ln in txt.split("\n") if "Đã kéo" in ln or "Kéo dữ liệu lỗi" in ln]
        print(f"{q:28} {time.time() - t0:5.0f}s", "LOI:" + ",".join(bad) if bad else "khong traceback", "|", seen_status,
              "|", (status[0][:120] if status else "-"), "|", (foot[0][:220] if foot else "-"), flush=True)
        if name:
            pg.screenshot(path=OUT + "\\" + name + ".png", full_page=True)
        pg.close()
        ctx.close()
    b.close()
