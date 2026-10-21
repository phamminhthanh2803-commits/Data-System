# -*- coding: utf-8 -*-
r"""
make_clipper.py - sinh biggee_clipper.user.js (20/10/2026): userscript Tampermonkey KÉO TAY lịch sử giá Biggee.
Không tự động mở trang, không né bot: PV2 tự mở từng trang /dinh-gia-can-ho/<slug> như xem bình thường,
script chỉ đọc ô #outDatatrend đang hiển thị, lưu vào localStorage, hiện bảng tiến độ + nút "Dự án kế tiếp" (1 click = 1 trang)
và nút "Xuất JSON" -> tải biggee_hist_<ngày>.json -> nạp: python biggee_web.py --history <file> --match
Danh sách dự án còn thiếu lấy từ kho (bảng giá trừ dự án đã có lịch sử) và nhúng vào script; chạy lại make_clipper.py sau mỗi lần nạp để cập nhật.
"""
import json
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('BDS_STORE') or os.path.join(HERE, 'store')
BG = os.path.join(STORE, 'biggee')

lst = pd.read_parquet(os.path.join(BG, 'apart_price_list.parquet')).sort_values('date').drop_duplicates('slug', keep='last')
done = set(pd.read_parquet(os.path.join(BG, 'project_history.parquet'))['slug']) if os.path.exists(os.path.join(BG, 'project_history.parquet')) else set()
todo = lst[~lst['slug'].isin(done)][['slug', 'name', 'city', 'district']]
items = [[r.slug, f'{r.name} · {r.district}, {r.city}'] for r in todo.itertuples()]
print(f'{len(lst)} dự án trong bảng giá, {len(done)} đã có lịch sử, {len(items)} còn thiếu')

JS = r'''// ==UserScript==
// @name         Biggee clipper - ghi tay lịch sử giá dự án
// @namespace    bds-tracker
// @version      1.0
// @description  Ghi ô #outDatatrend của trang dự án đang mở vào localStorage; nút Dự án kế tiếp (1 click = 1 trang), Xuất JSON để nạp biggee_web.py
// @match        https://biggee.vn/*
// @grant        none
// ==/UserScript==
(function () {
  'use strict';
  const TODO = __TODO__;   // [slug, nhãn] còn thiếu, sinh bởi make_clipper.py
  const KEY = 'bg_hist';
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { return {}; } };
  const save = h => localStorage.setItem(KEY, JSON.stringify(h));
  const parseTrend = v => { v = v.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&'); try { return JSON.parse(v); } catch (e) { return JSON.parse(v.replace(/'/g, '"').replace(/\bNone\b/g, 'null')); } };
  const slugOf = () => (location.pathname.match(/\/dinh-gia-can-ho\/([^\/?#]+)/) || [])[1];

  const hist = load(); const slug = slugOf(); let msg = '';
  if (slug) {
    const inp = document.querySelector('#outDatatrend');
    if (inp && inp.value && inp.value.length > 10) {
      try { hist[slug] = parseTrend(inp.value).map(d => [d.period, d.UNTPRICE, d.DIST_UNTPRICE]); save(hist); msg = 'đã lưu ' + hist[slug].length + ' tháng'; }
      catch (e) { msg = 'lỗi đọc: ' + e.message; }
    } else if (/Vui lòng đăng nhập/.test(document.body.innerText)) msg = 'CHƯA ĐĂNG NHẬP';
    else if (/bot\.php/.test(location.href) || /Xác thực người dùng/.test(document.title)) msg = 'captcha';
    else msg = 'trang này không có ô lịch sử';
  }
  const remain = TODO.filter(t => !(t[0] in hist));
  const next = remain[0];

  const box = document.createElement('div');
  box.style.cssText = 'position:fixed;top:8px;right:8px;z-index:999999;background:#111;color:#eee;font:13px/1.5 system-ui,sans-serif;padding:10px 12px;border-radius:8px;opacity:.95;max-width:360px;box-shadow:0 2px 10px #0008';
  box.innerHTML = '<b style="color:#8f8">Biggee clipper</b> · đã có <b>' + Object.keys(hist).length + '</b> · còn <b>' + remain.length + '</b>' +
    (slug ? '<div style="margin-top:4px">' + slug + ': <span style="color:#ff0">' + msg + '</span></div>' : '') +
    (next ? '<div style="margin-top:6px"><a id="bgc_next" href="/dinh-gia-can-ho/' + next[0] + '" style="display:inline-block;background:#2a7;color:#fff;padding:5px 10px;border-radius:6px;text-decoration:none">Dự án kế tiếp ›</a> <span style="opacity:.8">' + next[1] + '</span></div>' : '<div style="margin-top:6px;color:#8f8">Hết danh sách</div>') +
    '<div style="margin-top:8px"><button id="bgc_export" style="background:#36c;color:#fff;border:0;padding:5px 10px;border-radius:6px;cursor:pointer">Xuất JSON</button> ' +
    '<button id="bgc_clear" style="background:#633;color:#fff;border:0;padding:5px 10px;border-radius:6px;cursor:pointer">Xoá bộ nhớ</button> ' +
    '<span style="opacity:.7">nạp: biggee_web.py --history file.json --match</span></div>';
  document.body.appendChild(box);
  document.getElementById('bgc_export').onclick = () => {
    const blob = new Blob([JSON.stringify(load())], {type: 'application/json'}); const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = 'biggee_hist_' + new Date().toISOString().slice(0, 10) + '.json'; a.click();
  };
  document.getElementById('bgc_clear').onclick = () => { if (confirm('Xoá dữ liệu đã lưu trong trình duyệt? (chỉ xoá sau khi đã Xuất JSON và nạp kho)')) { localStorage.removeItem(KEY); location.reload(); } };
})();
'''
out = os.path.join(HERE, 'biggee_clipper.user.js')
open(out, 'w', encoding='utf-8').write(JS.replace('__TODO__', json.dumps(items, ensure_ascii=False)))
print('->', out, os.path.getsize(out), 'bytes')
