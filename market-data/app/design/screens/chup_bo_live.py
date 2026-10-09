# -*- coding: utf-8 -*-
"""Kiem chung + chup sau khi BO HAN trang Live (09/10/2026 toi, server test 8773, MD_ROOT=D:\\pipeline-data\\market-data):
khong traceback, khong con pill Live, ?trang=live -> Tong quan, overlay ● LIVE tren chart van chay, khoi Bo thu o Kho du lieu.
Anh: 14-bo-live-tong-quan.png, 14-bo-live-hieu-suat.png (+ kho)."""
import sys, time, re, json
from playwright.sync_api import sync_playwright

OUT = r"D:\market-data\app\design\screens"
PORT = 8773
PAGES = [
    ("14-bo-live-tong-quan", "tong-quan/tong-quan", 2600),
    ("14-bo-live-hieu-suat", "ttck/vn/hieu-suat", 4600),
    ("14-bo-live-kho", "tong-quan/kho", 2600),
    (None, "ttck/vn/dong-tien", 5400),
    (None, "ttck/vn/dinh-gia", 3700),
    (None, "vi-mo/viet-nam/gia-ca", 3000),
    (None, "live", 2400),                      # deep-link cu -> phai ve Tong quan
    (None, "live&lam-moi=5", 2400),
]
THE_LIVE = ["Diễn biến trong phiên", "Độ rộng trong phiên", "GTGD luỹ kế so với bình quân", "Khối ngoại trong phiên",
            "Toàn sàn trong phiên", "Ảnh hưởng lên chỉ số", "Bảng giá toàn sàn", "Nến 1 phút", "Mở trang Live"]
only = sys.argv[1:]
res = {}
with sync_playwright() as p:
    try:
        b = p.chromium.launch(channel="chrome", headless=True)
    except Exception:
        b = p.chromium.launch(headless=True)
    for name, q, h in PAGES:
        if only and (name or q) not in only:
            continue
        ctx = b.new_context(viewport={"width": 1440, "height": h}, device_scale_factor=1, color_scheme="light")
        pg = ctx.new_page()
        tt = []
        for lan in (1, 2):                                   # lan 2 = render am
            t0 = time.time()
            pg.goto(f"http://localhost:{PORT}/?trang={q}", wait_until="load")
            ok = False
            while time.time() - t0 < 120:
                txt = pg.inner_text("body")
                if "Phiên gần nhất:" in txt:
                    ok = True
                    break
                time.sleep(0.4)
            tt.append(time.time() - t0)
        time.sleep(3)
        txt = pg.inner_text("body")
        bad = [k for k in ("Traceback", "KeyError", "ValueError", "TypeError", "AttributeError", "NameError", "Lỗi khi dựng thẻ") if k in txt]
        pills = [x.strip() for x in txt.split("\n") if x.strip() in ("Tổng quan", "Live", "Thị trường chứng khoán", "Vĩ mô", "Tin tức")]
        rl = re.findall(r"render lúc (\d\d:\d\d:\d\d) \(([\d.,]+) s\)", txt)
        res[q] = {"ok": ok, "t_lan1": round(tt[0], 1), "t_lan2": round(tt[1], 1), "loi": bad, "pill_live": "Live" in pills,
                  "url": pg.url, "the_live_con": [t for t in THE_LIVE if t in txt], "overlay_LIVE": txt.count("● LIVE"),
                  "bo_thu": "Bộ thu real-time DNSE" in txt, "render_fragment": rl}
        if name:
            pg.screenshot(path=OUT + "\\" + name + ".png", full_page=True)
        print(q, "ok" if ok else "TIMEOUT", f"lan1 {tt[0]:.1f}s lan2 {tt[1]:.1f}s", "LOI:" + ",".join(bad) if bad else "khong traceback",
              "PILL LIVE CON!" if "Live" in pills else "khong pill Live", "| the live con:", res[q]["the_live_con"],
              "| overlay LIVE:", res[q]["overlay_LIVE"], "| bo thu:", res[q]["bo_thu"], "| fragment:", rl, "|", pg.url, flush=True)
        pg.close()
        ctx.close()
    b.close()
print(json.dumps(res, ensure_ascii=False, indent=1))
