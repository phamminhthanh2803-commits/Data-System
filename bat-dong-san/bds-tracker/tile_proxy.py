# -*- coding: utf-8 -*-
r"""
tile_proxy.py - PROXY TILE quy hoạch cho trang Bản đồ (18/10/2026).

Lý do: Plotly/MapLibre tải tile raster bằng fetch() nên cần header CORS; server tile Sở QHKT TP.HCM (sqhkt-qlqh.tphcm.gov.vn) và VietPalm
không trả Access-Control-Allow-Origin -> trình duyệt chặn. Proxy này chạy trong tiến trình Streamlit (luồng nền, cổng TILE_PROXY_PORT mặc định 8768):
  GET /t/<key>/<z>/<x>/<y>.png  -> tải tile gốc (kèm Referer phù hợp), cache ở store/infra/tile_cache/<key>/<z>/<x>/<y>.png, trả về với CORS *.
Chỉ phục vụ các key khai báo trong infra_layers.TILES (không phải proxy mở). Tile đã cache dùng lại vĩnh viễn (xoá thư mục cache nếu bản đồ đổi).
"""
from __future__ import annotations

import base64
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('BDS_STORE') or os.path.join(os.path.dirname(APP), 'batdongsan-projects', 'store')
CACHE = os.path.join(STORE, 'infra', 'tile_cache')
PORT = int(os.environ.get('TILE_PROXY_PORT', '8768'))
_STATE = {'server': None, 'port': None, 'err': None}
_SESSIONS = {}
REFERER = {'sqhkt-qlqh.tphcm.gov.vn': 'https://thongtinquyhoach.hochiminhcity.gov.vn/', 'land.vietpalm.group': 'https://quyhoach.hanoi.vn/',
           's3-ap-southeast-1.amazonaws.com': 'https://quyhoach.hanoi.vn/'}
# PNG 1×1 trong suốt (base64, hợp lệ) cho tile ngoài vùng / lỗi
BLANK_PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==')


def _upstream(key):
    import infra_layers as il
    return il.TILES[key][1] if key in il.TILES else None


def _session():
    from curl_cffi import requests as creq
    tid = threading.get_ident()
    if tid not in _SESSIONS: _SESSIONS[tid] = creq.Session(impersonate='chrome124')
    return _SESSIONS[tid]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype='image/png', cache=True):
        self.send_response(code)
        self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        if cache: self.send_header('Cache-Control', 'public, max-age=86400')
        self.end_headers(); self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204); self.send_header('Access-Control-Allow-Origin', '*'); self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS'); self.end_headers()

    def do_GET(self):
        m = re.match(r'^/t/([a-z0-9_]+)/(\d{1,2})/(\d+)/(\d+)\.png$', self.path)
        if not m: return self._send(404, b'not found', 'text/plain', cache=False)
        key, z, x, y = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
        tpl = _upstream(key)
        if tpl is None: return self._send(404, b'unknown layer', 'text/plain', cache=False)
        p = os.path.join(CACHE, key, str(z), str(x), f'{y}.png')
        if os.path.exists(p):
            return self._send(200, open(p, 'rb').read())
        url = tpl.format(z=z, x=x, y=y); host = re.sub(r'^https?://([^/]+).*$', r'\1', url)
        try:
            r = _session().get(url, timeout=25, headers={'Referer': REFERER.get(host, url)})
            if r.status_code == 200 and r.headers.get('content-type', '').startswith('image') and len(r.content) > 0:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                tmp = p + '.part'; open(tmp, 'wb').write(r.content); os.replace(tmp, p)
                return self._send(200, r.content)
            return self._send(200, BLANK_PNG, cache=False)        # 404 (ngoài vùng có tile) -> tile trong suốt, không cache
        except Exception:  # noqa: BLE001
            return self._send(200, BLANK_PNG, cache=False)


def start(port=PORT):
    """khởi động 1 lần trong tiến trình (gọi từ app.py qua st.cache_resource); trả về cổng hoặc None"""
    if _STATE['server'] is not None: return _STATE['port']
    for pt in (port, port + 1, port + 2):
        try:
            srv = ThreadingHTTPServer(('127.0.0.1', pt), Handler); srv.daemon_threads = True
            threading.Thread(target=srv.serve_forever, daemon=True, name='tile-proxy').start()
            _STATE.update(server=srv, port=pt); return pt
        except OSError as e:
            _STATE['err'] = str(e)
    return None


def base_url(host='localhost'):
    return f'http://{host}:{_STATE["port"]}' if _STATE['port'] else None
