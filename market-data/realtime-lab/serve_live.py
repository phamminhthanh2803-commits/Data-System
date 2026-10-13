# -*- coding: utf-8 -*-
r"""
serve_live.py — KENH 5 GIAY cho app (13/10/2026, PV2: "doi thanh live 5 s" cho ca app online lan laptop).

Bo thu dnse_stream.py tren GitHub Actions xuat 8 parquet moi 5 s vao data/<ngay>/ nhung chi day Drive moi 60 s (rclone) ->
app chi thay "live 1 phut (cloud)". Module nay mo 1 HTTP server nho (stdlib, khong them thu vien) ngay trong tien trinh bo thu
+ 1 Cloudflare QUICK TUNNEL (`cloudflared tunnel --url`, mien phi, khong can tai khoan, URL https://<ngau-nhien>.trycloudflare.com)
de app (laptop hoac Streamlit Cloud) GET truc tiep cac parquet moi 5 s. Drive 60 s (push_loop) VAN GIU lam du phong.

  GET /index.json[?k=token]            -> {"ts": epoch, "day": "YYYY-MM-DD", "token_required": bool,
                                           "files": {name: {"mtime": epoch, "size": bytes}}}   (chi file dang co)
  GET /<day>/<name>.parquet[?k=token]  -> noi dung file; chi <day> dang phuc vu + ten trong WHITELIST (8 parquet, khong duckdb)
  Cache-Control: no-store. File doc bang open() nguyen khoi — bo thu ghi .tmp roi os.replace nen khong bao gio doc file ghi do.
  env RT_TOKEN (secret GitHub tuy chon, PV2 tu dat chuoi bat ky) -> moi request phai co ?k=<token> (sai/thieu -> 403).

tunnel.json (ghi vao <out_root>/tunnel.json roi `rclone copyto` len <remote>/tunnel.json, lam moi moi 5 phut, cuoi job url=null):
  {"url": "https://xxx.trycloudflare.com" | null, "started": iso, "updated": iso, "run_id": ..., "day": ..., "token_required": bool}
  App (data_live.py) doc file nay tu Drive (cache 60 s) de biet URL; url null / GET /index.json loi -> ve Drive 60 s.

Dung tu dnse_stream.py: `--serve-port 8787` -> start_server(...) + start_tunnel(...). cloudflared tim theo env CLOUDFLARED -> PATH ->
C:\Program Files (x86)\cloudflared\cloudflared.exe. Khong co / loi -> log + bo qua (van con Drive 60 s).
Chay thu rieng:  python serve_live.py --dir data --port 8787 [--tunnel] [--remote gdrive:pipeline-data/realtime-test]
"""
from __future__ import annotations

import datetime as dt
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

VN_TZ = dt.timezone(dt.timedelta(hours=7))
WHITELIST = ["index_latest", "stocks_latest", "rt_latest", "influence_latest", "foreign_latest", "market_summary",
             "index_1m", "rt_bars_1m"]
TUNNEL_RX = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
TUNNEL_REFRESH = 300            # s, ghi lai tunnel.json + copyto Drive (app cache 60 s)
TUNNEL_URL_WAIT = 60            # s, cho cloudflared in URL
RCLONE_OPTS = ["--contimeout", "15s", "--timeout", "60s", "--retries", "2", "--low-level-retries", "5", "-q"]
STATE = {"day": None, "day_dir": None, "token": None, "n_req": 0, "n_bad": 0, "url": None, "proc": None}


def log(msg: str) -> None:
    print(f"[{dt.datetime.now(VN_TZ):%H:%M:%S}] [serve] {msg}", flush=True)


# ----------------------------------------------------------------------------- HTTP server
class _Handler(BaseHTTPRequestHandler):
    server_version = "serve_live/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: D102 - im lang (chi log loi o do_GET)
        return

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _auth_ok(self, query: str) -> bool:
        tok = STATE.get("token")
        if not tok:
            return True
        k = urllib.parse.parse_qs(query).get("k", [""])[0]
        return hmac.compare_digest(k, tok)

    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def do_GET(self):  # noqa: N802
        STATE["n_req"] += 1
        u = urllib.parse.urlsplit(self.path)
        if not self._auth_ok(u.query):
            STATE["n_bad"] += 1
            self._send(403, b'{"error":"token"}')
            return
        path = u.path
        day, day_dir = STATE.get("day"), STATE.get("day_dir")
        if path in ("/", "/index.json"):
            files = {}
            if day_dir and os.path.isdir(day_dir):
                for name in WHITELIST:
                    p = os.path.join(day_dir, name + ".parquet")
                    try:
                        s = os.stat(p)
                        files[name] = {"mtime": round(s.st_mtime, 3), "size": s.st_size}
                    except OSError:
                        continue
            body = json.dumps({"ts": round(time.time(), 3), "day": day, "token_required": bool(STATE.get("token")),
                               "files": files}).encode()
            self._send(200, body)
            return
        m = re.fullmatch(r"/(\d{4}-\d{2}-\d{2})/([a-z0-9_]+)\.parquet", path)
        if not m or m.group(2) not in WHITELIST or m.group(1) != day or not day_dir:
            self._send(404, b'{"error":"not found"}')
            return
        p = os.path.join(day_dir, m.group(2) + ".parquet")
        data = None
        for _i in range(3):                         # os.replace dang doi ten -> thu lai
            try:
                with open(p, "rb") as f:
                    data = f.read()
                break
            except OSError:
                time.sleep(0.1)
        if data is None:
            self._send(404, b'{"error":"no file"}')
            return
        self._send(200, data, "application/octet-stream")


def start_server(day_dir: str, day: str, port: int, token: str | None = None) -> ThreadingHTTPServer:
    """Mo HTTP server (thread nen daemon) phuc vu day_dir. Tra server (goi .shutdown() khi dung)."""
    STATE.update(day=day, day_dir=day_dir, token=(token or None))
    srv = ThreadingHTTPServer(("127.0.0.1", port), _Handler)       # chi loopback: ra ngoai qua cloudflared
    srv.daemon_threads = True
    th = threading.Thread(target=srv.serve_forever, name="serve-live", daemon=True)
    th.start()
    log(f"HTTP :{port} phuc vu {day_dir} (token {'BAT' if token else 'tat'})")
    return srv


# ----------------------------------------------------------------------------- cloudflared quick tunnel
def find_cloudflared() -> str | None:
    cands = [os.environ.get("CLOUDFLARED"), shutil.which("cloudflared"),
             r"C:\Program Files (x86)\cloudflared\cloudflared.exe", r"C:\Program Files\cloudflared\cloudflared.exe"]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def _write_tunnel_json(path: str, url: str | None, started: str | None, run_id: str, day: str, token_required: bool) -> None:
    doc = {"url": url, "started": started, "updated": dt.datetime.now(VN_TZ).isoformat(timespec="seconds"),
           "run_id": run_id, "day": day, "token_required": token_required, "refresh_sec": TUNNEL_REFRESH}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)
    os.replace(tmp, path)


def _push_tunnel_json(rc: str | None, path: str, remote: str | None) -> bool:
    if not rc or not remote:
        return False
    try:
        r = subprocess.run([rc, "copyto", path, f"{remote}/tunnel.json"] + RCLONE_OPTS, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            log(f"! rclone copyto tunnel.json exit {r.returncode}: {(r.stderr or r.stdout)[-200:].strip()}")
            return False
        return True
    except Exception as e:  # noqa: BLE001
        log(f"! copyto tunnel.json: {type(e).__name__}: {str(e)[:120]}")
        return False


def _probe(url: str, token: str | None, tries: int = 6) -> float | None:
    """GET <url>/index.json qua internet (kiem chung tunnel da dinh tuyen). Tra giay phan hoi hoac None."""
    q = f"?k={urllib.parse.quote(token)}" if token else ""
    for i in range(tries):
        t0 = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url + "/index.json" + q, headers={"User-Agent": "serve_live"}),
                                        timeout=5) as r:
                if r.status == 200:
                    json.load(r)
                    return time.time() - t0
        except Exception:  # noqa: BLE001
            time.sleep(3 + 2 * i)
    return None


def _spawn(cf: str, port: int):
    """Chay cloudflared, tra (proc, url|None). URL doc tu stderr (cloudflared in log ra stderr) toi da TUNNEL_URL_WAIT s."""
    cmd = [cf, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate", "--loglevel", "info"]
    kw = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if os.name == "nt" else {}
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **kw)
    found: list[str] = []

    def reader():
        try:
            for line in proc.stderr:
                if not found:
                    m = TUNNEL_RX.search(line)
                    if m:
                        found.append(m.group(0))
                if "error" in line.lower() and "429" in line:
                    log(f"cloudflared: {line.strip()[:200]}")
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=reader, name="cloudflared-log", daemon=True).start()
    t0 = time.time()
    while time.time() - t0 < TUNNEL_URL_WAIT and not found and proc.poll() is None:
        time.sleep(0.5)
    return proc, (found[0] if found else None)


def _tunnel_loop(port: int, out_root: str, remote: str | None, rc: str | None, day: str, token: str | None,
                 stop_evt: threading.Event) -> None:
    cf = find_cloudflared()
    path = os.path.join(out_root, "tunnel.json")
    run_id = os.environ.get("GITHUB_RUN_ID") or f"local-{os.getpid()}"
    if not cf:
        log("! khong tim thay cloudflared (env CLOUDFLARED / PATH) -> KHONG mo tunnel, app dung Drive 60 s")
        return
    started = None
    proc = None
    url = None
    n_restart = 0
    try:
        while not stop_evt.is_set():
            if proc is None or proc.poll() is not None:
                if proc is not None:
                    log(f"! cloudflared thoat ma {proc.returncode} -> mo lai (lan {n_restart + 1})")
                    n_restart += 1
                    if n_restart > 20:
                        log("! cloudflared loi qua 20 lan -> bo tunnel (van con Drive 60 s)")
                        break
                    stop_evt.wait(min(60, 5 * n_restart))
                    if stop_evt.is_set():
                        break
                proc, url = _spawn(cf, port)
                STATE["proc"] = proc
                if not url:
                    log(f"! cloudflared khong in URL trong {TUNNEL_URL_WAIT} s (ma {proc.poll()}) -> thu lai")
                    try:
                        proc.terminate()
                    except Exception:  # noqa: BLE001
                        pass
                    continue
                started = dt.datetime.now(VN_TZ).isoformat(timespec="seconds")
                STATE["url"] = url
                _write_tunnel_json(path, url, started, run_id, day, bool(token))      # day URL len Drive TRUOC, probe sau
                pushed = _push_tunnel_json(rc, path, remote)
                sec = _probe(url, token)
                log(f"tunnel {url} (run {run_id}) -> GET /index.json qua internet: "
                    + (f"OK {sec:.2f}s" if sec is not None else "CHUA phan hoi (app se tu thu lai)")
                    + (f" | tunnel.json -> {remote}/tunnel.json" if pushed else ""))
            # lam moi moi TUNNEL_REFRESH s (kiem tra tien trinh song moi 5 s)
            for _ in range(TUNNEL_REFRESH // 5):
                if stop_evt.wait(5) or proc.poll() is not None:
                    break
            if stop_evt.is_set() or proc.poll() is not None:
                continue
            _write_tunnel_json(path, url, started, run_id, day, bool(token))
            _push_tunnel_json(rc, path, remote)
    finally:
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except Exception:  # noqa: BLE001
                pass
        STATE["url"] = None
        try:
            _write_tunnel_json(path, None, started, run_id, day, bool(token))
            _push_tunnel_json(rc, path, remote)
        except Exception as e:  # noqa: BLE001
            log(f"! ghi tunnel.json cuoi: {type(e).__name__}: {str(e)[:120]}")
        log(f"tunnel dong (url=null da day Drive) | request: {STATE['n_req']} (403: {STATE['n_bad']})")


def start_tunnel(port: int, out_root: str, remote: str | None, rc: str | None, day: str, token: str | None,
                 stop_evt: threading.Event) -> threading.Thread:
    """Thread nen: cloudflared quick tunnel -> tunnel.json -> Drive; dung khi stop_evt set (ghi url=null). Tra thread (join <= 20 s)."""
    th = threading.Thread(target=_tunnel_loop, args=(port, out_root, remote, rc, day, token, stop_evt), name="cf-tunnel", daemon=True)
    th.start()
    return th


# ----------------------------------------------------------------------------- chay thu rieng
if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="HTTP + Cloudflare quick tunnel phuc vu parquet bo thu (thu rieng)")
    ap.add_argument("--dir", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"), help="thu muc goc data/")
    ap.add_argument("--day", default="", help="YYYY-MM-DD (mac dinh: thu muc ngay moi nhat)")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--tunnel", action="store_true")
    ap.add_argument("--remote", default="", help="rclone remote de day tunnel.json (vd gdrive:pipeline-data/realtime-test)")
    ap.add_argument("--duration", type=int, default=0)
    a = ap.parse_args()
    day = a.day or sorted(d for d in os.listdir(a.dir) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d))[-1]
    tok = os.environ.get("RT_TOKEN") or None
    srv = start_server(os.path.join(a.dir, day), day, a.port, tok)
    ev = threading.Event()
    th = None
    if a.tunnel:
        rc = shutil.which("rclone") or os.environ.get("RCLONE")
        th = start_tunnel(a.port, a.dir, a.remote or None, rc, day, tok, ev)
    try:
        t0 = time.time()
        while not a.duration or time.time() - t0 < a.duration:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    ev.set()
    if th:
        th.join(timeout=20)
    srv.shutdown()
    sys.exit(0)
