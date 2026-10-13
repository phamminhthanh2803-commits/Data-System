# -*- coding: utf-8 -*-
"""Kiem chung "khong lam mo UI khi live rerun" (13/10/2026, PV2: "giao dien khi cap nhat moi lan cua live khong nen lam mo").
Streamlit 1.64: luc fragment rerun, moi [data-testid="stElementContainer"] cu duoc gan data-stale="true" + class emotion doi sang
`opacity: .33; transition: opacity 1s ease-in 0.5s` -> the/chart mo di ~0,5 s sau khi bat dau rerun. ui_genea CSS ghi de
[data-stale="true"] { opacity:1; transition:none } + an stStatusWidget.
Script: mo trang (live=1, tan=5), cho den khi co data-stale="true", doi 0,9 s roi chup + do opacity NHO NHAT cua cac container stale
trong 12 s (truoc CSS ~0,33; sau CSS = 1), do scrollY truoc/sau de chac khong nhay cuon.
  python chup_khong_mo.py <port> <ten-anh>      vd: chup_khong_mo.py 8777 19-khong-mo-truoc
"""
import sys
import time

from playwright.sync_api import sync_playwright

OUT = r"D:\market-data\app\design\screens"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8777
NAME = sys.argv[2] if len(sys.argv) > 2 else "19-khong-mo"
JS = """
() => new Promise(res => {
  const out = {minOpacity: 1, staleEvents: 0, samples: 0, scroll0: window.scrollY, scrollMax: 0, statusWidgetShown: 0};
  const tick = () => {
    const els = document.querySelectorAll('[data-stale="true"]');
    if (els.length) { out.staleEvents++; }
    for (const el of els) { const o = parseFloat(getComputedStyle(el).opacity); if (o < out.minOpacity) out.minOpacity = o; out.samples++; }
    const sw = document.querySelector('[data-testid="stStatusWidget"]');
    if (sw && getComputedStyle(sw).display !== 'none' && sw.offsetParent !== null) out.statusWidgetShown++;
    out.scrollMax = Math.max(out.scrollMax, Math.abs(window.scrollY - out.scroll0));
  };
  const id = setInterval(tick, 50);
  setTimeout(() => { clearInterval(id); res(out); }, 12000);
})
"""
with sync_playwright() as p:
    try:
        b = p.chromium.launch(channel="chrome", headless=True)
    except Exception:  # noqa: BLE001
        b = p.chromium.launch(headless=True)
    ctx = b.new_context(viewport={"width": 1440, "height": 1500}, device_scale_factor=1, color_scheme="light")
    pg = ctx.new_page()
    pg.goto(f"http://localhost:{PORT}/?trang=tong-quan/tong-quan&live=1&tan=5", wait_until="load")
    t0 = time.time()
    while time.time() - t0 < 90 and "Phiên gần nhất:" not in pg.inner_text("body"):
        time.sleep(0.5)
    pg.mouse.wheel(0, 700)                       # cuon xuong giua trang de thay chart + kiem tra khong nhay cuon
    time.sleep(1)
    shot = None
    try:
        pg.wait_for_selector('[data-stale="true"]', timeout=20000, state="attached")
        time.sleep(0.9)                          # qua delay 0.5 s cua transition -> luc mo nhat (neu con mo)
        shot = OUT + "\\" + NAME + ".png"
        pg.screenshot(path=shot, full_page=False)
    except Exception as e:  # noqa: BLE001
        print("khong bat duoc data-stale:", type(e).__name__)
    m = pg.evaluate(JS)
    txt = pg.inner_text("body")
    live = [ln for ln in txt.split("\n") if "● LIVE dữ liệu" in ln]
    print(f"{NAME}: minOpacity={m['minOpacity']} staleEvents={m['staleEvents']} samples={m['samples']} "
          f"scrollJump={m['scrollMax']}px statusWidgetShown={m['statusWidgetShown']} | anh: {shot} | {live[0][:160] if live else '-'}")
    b.close()
