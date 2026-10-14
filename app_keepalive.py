# -*- coding: utf-8 -*-
"""Giu app Streamlit Community Cloud luon thuc (14/10/2026 PV2: 'app on 24/24').

Streamlit Cloud cho app public NGU sau ~12 gio khong co ai MO (request HTTP thuong khong tinh - phai co phien trinh duyet
that). Script nay mo app bang Chromium headless (Playwright), neu gap trang "app is asleep" thi bam nut danh thuc,
doi toi khi app render xong (thay chu 'Market Data'), roi dong. Chay theo lich GitHub Actions (app-keepalive.yml, 4 gio/lan).

Dung: python app_keepalive.py <url> [--timeout 300]
Exit 0 = app thuc + render OK; 1 = khong render duoc trong thoi gian cho (log de xem).
"""
import argparse
import sys
import time


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--timeout", type=int, default=300, help="giay toi da doi app render")
    ap.add_argument("--text", default="Market Data", help="chu phai thay khi app da render")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    t0 = time.time()
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(viewport={"width": 1280, "height": 900})
        pg.goto(a.url, wait_until="domcontentloaded", timeout=120_000)
        woke = False
        state = "?"
        while time.time() - t0 < a.timeout:
            body = ""
            try:
                body = pg.inner_text("body")
            except Exception:  # noqa: BLE001 - trang dang chuyen
                pass
            # app render ben trong iframe cua Streamlit Cloud -> xem ca frame con
            for fr in pg.frames:
                try:
                    if a.text in fr.inner_text("body"):
                        state = "OK"
                        break
                except Exception:  # noqa: BLE001
                    continue
            if state == "OK":
                break
            low = body.lower()
            if ("asleep" in low or "get this app back up" in low) and not woke:
                for sel in ("text=Yes, get this app back up!", "button:has-text('get this app back up')", "button:has-text('Yes')"):
                    try:
                        pg.click(sel, timeout=5_000)
                        woke = True
                        print(f"[{time.time() - t0:5.0f}s] app dang NGU -> da bam danh thuc")
                        break
                    except Exception:  # noqa: BLE001
                        continue
            elif "oh no" in low or "error" in low[:400]:
                print(f"[{time.time() - t0:5.0f}s] trang bao loi: {body[:200]!r}")
            time.sleep(5)
        try:
            pg.screenshot(path="keepalive.png", full_page=False)
        except Exception:  # noqa: BLE001
            pass
        br.close()
    dt = time.time() - t0
    if state == "OK":
        print(f"OK: app thuc va da render ('{a.text}') sau {dt:.0f}s" + (" (vua danh thuc)" if woke else ""))
        return 0
    print(f"LOI: khong thay '{a.text}' sau {dt:.0f}s (danh thuc: {woke})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
