# -*- coding: utf-8 -*-
r"""
recv_server.py - máy nhận file từ trình duyệt (20/10/2026): script JS chạy trong tab Biggee đã đăng nhập POST dữ liệu thu được về đây,
không phải chép tay qua chat. Chỉ lắng nghe 127.0.0.1:8769, chỉ nhận POST /save/<tên file> (ký tự an toàn), ghi vào store/biggee/inbox/<tên>.
CORS * để trang https://biggee.vn gọi được (Chrome cho phép https -> http://localhost). Chạy: python recv_server.py  (Ctrl+C để dừng)
"""
import os
import re
import sys
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
INBOX = os.path.join(os.environ.get('BDS_STORE') or os.path.join(HERE, 'store'), 'biggee', 'inbox')
PORT = int(os.environ.get('RECV_PORT', '8769'))


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*'); self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Append')
        self.send_header('Access-Control-Allow-Private-Network', 'true')      # Chrome PNA: trang https public -> 127.0.0.1 cần header này ở preflight

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_GET(self):
        body = b'recv ok'; self.send_response(200); self._cors(); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        m = re.match(r'^/save/([A-Za-z0-9_.\-]{1,80})$', self.path)
        if not m: self.send_response(404); self._cors(); self.end_headers(); return
        n = int(self.headers.get('Content-Length', '0')); data = self.rfile.read(n)
        os.makedirs(INBOX, exist_ok=True); p = os.path.join(INBOX, m.group(1))
        mode = 'ab' if self.headers.get('X-Append') == '1' else 'wb'
        with open(p, mode) as f: f.write(data)
        print(f'[{datetime.now():%H:%M:%S}] {m.group(1)} {"+" if mode == "ab" else ""}{n} bytes', flush=True)
        body = f'saved {n}'.encode(); self.send_response(200); self._cors(); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)


if __name__ == '__main__':
    print(f'recv_server: http://127.0.0.1:{PORT}/save/<file> -> {INBOX}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
