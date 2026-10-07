# -*- coding: utf-8 -*-
"""Cao du lieu HNX cbonds — gop toan bo cac lenh pull vao 1 file.

Usage:
  python scripts/pull_hnx.py master      # re-pull FULL bond master (68 trang)
  python scripts/pull_hnx.py update      # incremental feed CBTT + registry TTPH
  python scripts/pull_hnx.py feed-full   # rebuild FULL feed (chi khi can)
  python scripts/pull_hnx.py ttph-full   # rebuild FULL registry (chi khi can)

Khong cache HTML tho — parse thang vao CSV o data/processed/.
"""
import csv
import html as H
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hnx_common import BASE, make_session, polite_sleep, write_file_safe

MASTER_CSV = "data/processed/bond_master.csv"
FEED_CSV = "data/processed/feed.csv"
TTPH_CSV = "data/processed/ttph.csv"
PAGE_SIZE = 100
STOP_AFTER = 2    # incremental: dung sau N trang lien tiep khong co tin moi
MAX_PAGES = 200

MASTER_COLS = ["stt", "ma_tp", "tien_te", "to_chuc_phat_hanh", "menh_gia",
               "ky_han", "ky_han_con_lai_ngay", "ngay_phat_hanh", "ngay_dao_han",
               "phuong_thuc_tra_lai", "ky_han_tra_lai", "kl_phat_hanh",
               "kl_con_luu_hanh", "to_chuc_luu_ky", "lai_suat_phat_hanh",
               "doi_tuong_chao_ban", "don_vi_xhtn", "ket_qua_xhtn",
               "ngay_hieu_luc", "tai_lieu", "tieu_chuan_ben_vung",
               "don_vi_danh_gia", "tinh_trang"]

FEED_COLS = ["tab", "stt", "ngay_dang", "ten_doanh_nghiep", "ma_tp_lien_quan",
             "tieu_de", "ghi_chu", "tinh_trang", "article_id", "n_files"]
FEED_TABS = {1: "dinh_ky", 2: "bat_thuong", 3: "khac", 4: "tu_so"}

TTPH_COLS = ["stt", "ngay_dang_tin", "ten_dn", "ma_tp", "tien_te", "ky_han",
             "ngay_phat_hanh", "ngay_dao_han", "ky_han_con_lai", "khoi_luong",
             "menh_gia", "loai_hinh_tra_lai", "loai_lai_suat", "pt_thanh_toan_lai",
             "mua_lai_hoan_doi", "thi_truong", "lai_suat", "tinh_trang", "file"]

MUALAI_CSV = "data/processed/mua_lai.csv"
MUALAI_COLS = ["stt", "ngay_dang_tin", "ten_dn", "ma_tp", "menh_gia", "ky_han",
               "ngay_phat_hanh", "ngay_dao_han", "gt_phat_hanh",
               "gt_dang_luu_hanh", "gt_mua_lai", "sl_mua_lai", "gt_con_lai",
               "sl_con_lai", "ngay_mua_lai", "tinh_trang", "ghi_chu", "file"]


def clean(c):
    return H.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c))).strip()


def total_of(frag):
    m = re.search(r"Tổng số\s*<b>([\d,\.]+)</b>", frag)
    return int(re.sub(r"[^\d]", "", m.group(1))) if m else 0


def check_api(text, what):
    if text.lstrip().startswith("{"):
        raise RuntimeError("API error (%s): %s" % (what, text[:200]))
    return text


# ---------------- bond master ----------------
def fetch_master_page(sess, token, page):
    payload = {"SearchKeys": ["", "", "", "", "", "", "", ""],
               "CurrentPage": page, "NumberRecordOnPage": PAGE_SIZE}
    r = sess.post(BASE + "/to-chuc-phat-hanh/danh-sach-trai-phieu",
                  data=json.dumps(payload),
                  headers={"Content-Type": "application/json;charset=utf-8",
                           "CP-TOKEN": token}, timeout=60)
    r.raise_for_status()
    return check_api(r.text, "master p%d" % page)


def parse_master(frag):
    rows = []
    body = re.search(r"<tbody[^>]*>(.*?)</tbody>", frag, re.S)
    if body:
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.S):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(cells) >= len(MASTER_COLS):
                rows.append([clean(c) for c in cells[:len(MASTER_COLS)]])
    return rows, total_of(frag)


def cmd_master():
    sess, token = make_session("/to-chuc-phat-hanh/danh-sach-trai-phieu")
    all_rows, page, total = [], 1, None
    while True:
        rows, tot = parse_master(fetch_master_page(sess, token, page))
        polite_sleep()
        if total is None and tot:
            total = tot
            print("bond master total:", total, flush=True)
        all_rows.extend(rows)
        if not rows or (total and len(all_rows) >= total):
            break
        page += 1
    def _w(f):
        w = csv.writer(f)
        w.writerow(MASTER_COLS)
        w.writerows(all_rows)
    if not write_file_safe(MASTER_CSV, _w):
        sys.exit(2)
    print("saved %d rows -> %s" % (len(all_rows), MASTER_CSV))


# ---------------- feed CBTT ----------------
def fetch_feed_page(sess, token, page):
    data = [("keysSearch[]", v) for v in [""] * 7]
    data += [("currentPages[]", str(page))] * 4
    data += [("numberRecord[]", str(PAGE_SIZE))] * 4
    r = sess.post(BASE + "/to-chuc-phat-hanh/tin-cong-bo-x", data=data,
                  headers={"CP-TOKEN": token}, timeout=60)
    r.raise_for_status()
    return check_api(r.text, "feed p%d" % page)


def parse_feed(frag):
    out, totals = [], {}
    tables = re.findall(r"<table.*?</table>", frag, re.S)
    tails = re.split(r"</table>", frag)[1:]
    for i, tbl in enumerate(tables):
        tail = tails[i] if i < len(tails) else ""
        mtab = re.search(r"changePage(\d)\(", tail)
        tab = int(mtab.group(1)) if mtab else i + 1
        mtot = re.search(r"Tổng số\s*<b>([\d,\.]+)</b>", tail)
        if mtot:
            totals[tab] = int(re.sub(r"[^\d]", "", mtot.group(1)))
        ths = [clean(t) for t in re.findall(r"<th[^>]*>(.*?)</th>", tbl, re.S)]
        has_note, has_bond = "Ghi chú" in ths, "Mã TP liên quan" in ths
        body = re.search(r"<tbody[^>]*>(.*?)</tbody>", tbl, re.S)
        if not body:
            continue
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.S):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(cells) < 5:
                continue
            vals = [clean(c) for c in cells]
            art = re.search(r"showArticle\('(\d+)'\)", tr)
            files = re.findall(r"view-file", tr)
            k = 0
            row = {"tab": FEED_TABS.get(tab, str(tab)), "stt": vals[k],
                   "ngay_dang": vals[k + 1], "ten_doanh_nghiep": vals[k + 2]}
            k += 3
            row["ma_tp_lien_quan"] = vals[k] if has_bond else ""
            k += 1 if has_bond else 0
            row["tieu_de"] = vals[k]; k += 1
            row["ghi_chu"] = vals[k] if has_note else ""
            k += 1 if has_note else 0
            row["tinh_trang"] = vals[k] if k < len(vals) else ""
            row["article_id"] = art.group(1) if art else ""
            row["n_files"] = len(files)
            out.append(row)
    return out, totals


def feed_key(r):
    return (r["tab"], r["article_id"], r["ngay_dang"], r["tieu_de"][:80])


def cmd_feed_full():
    sess, token = make_session("/to-chuc-phat-hanh/tin-cong-bo")
    rows, seen, page, max_pages = [], set(), 1, None
    while True:
        prows, totals = parse_feed(fetch_feed_page(sess, token, page))
        polite_sleep()
        if max_pages is None and totals:
            max_pages = max(math.ceil(t / PAGE_SIZE) for t in totals.values())
            print("feed totals:", totals, "->", max_pages, "pages", flush=True)
        fresh = 0
        for r in prows:
            if feed_key(r) in seen:
                continue
            seen.add(feed_key(r)); rows.append(r); fresh += 1
        print("feed page %d -> %d fresh" % (page, fresh), flush=True)
        if (max_pages and page >= max_pages) or (fresh == 0 and page > 1):
            break
        page += 1
    _save_feed(rows)


def _save_feed(rows):
    def _w(f):
        w = csv.DictWriter(f, fieldnames=FEED_COLS)
        w.writeheader(); w.writerows(rows)
    write_file_safe(FEED_CSV, _w)
    print("feed saved: %d rows" % len(rows))


# ---------------- registry TTPH ----------------
def fetch_ttph_page(sess, token, page):
    data = [("searchKeys[]", v) for v in [""] * 4]
    data += [("arrCurrentPage[]", str(page))] * 12
    data += [("arrNumberRecord[]", str(PAGE_SIZE))] * 12
    r = sess.post(BASE + "/to-chuc-phat-hanh/thong-tin-phat-hanh/tim-kiem",
                  data=data, headers={"CP-TOKEN": token}, timeout=90)
    r.raise_for_status()
    return check_api(r.text, "ttph p%d" % page)


def parse_ttph(frag):
    t0 = re.findall(r"<table.*?</table>", frag, re.S)[0]
    body = re.search(r"<tbody[^>]*>(.*?)</tbody>", t0, re.S)
    rows = []
    if body:
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.S):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(cells) < 18:
                continue
            vals = [clean(c) for c in cells[:18]]
            m = re.search(r"ViewFileTTPH\(([\d.]+)\s*,\s*(\d+)\)", tr)
            vals.append(("%s|%s" % (m.group(1).split(".")[0], m.group(2))) if m else "")
            rows.append(vals)
    return rows, total_of(frag)


def ttph_key(v):
    return (v[3], v[1], v[6], v[18])


def parse_mualai(frag):
    """Bang 1 cua response TTPH = cac dot MUA LAI trai phieu."""
    tables = re.findall(r"<table.*?</table>", frag, re.S)
    if len(tables) < 2:
        return [], 0
    t1 = tables[1]
    body = re.search(r"<tbody[^>]*>(.*?)</tbody>", t1, re.S)
    rows = []
    if body:
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body.group(1), re.S):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(cells) < 17:
                continue
            vals = [clean(c) for c in cells[:17]]
            m = re.search(r"ViewFileTTPH\(([\d.]+)\s*,\s*(\d+)\)", tr)
            vals.append(("%s|%s" % (m.group(1).split(".")[0], m.group(2))) if m else "")
            rows.append(vals)
    # pager cua bang 1 nam SAU the </table> thu 2 (tails[1] la pager bang 0)
    tails = re.split(r"</table>", frag)
    total = total_of(tails[2]) if len(tails) > 2 else 0
    return rows, total


def mualai_key(v):
    return (v[3], v[14], v[10], v[1])  # ma_tp, ngay_mua_lai, gt_mua_lai, ngay_dang


def _save_mualai(rows):
    def _w(f):
        w = csv.writer(f)
        w.writerow(MUALAI_COLS)
        w.writerows(rows)
    write_file_safe(MUALAI_CSV, _w)
    print("mua_lai saved: %d rows" % len(rows))


def cmd_mualai_full():
    sess, token = make_session("/to-chuc-phat-hanh/thong-tin-phat-hanh")
    rows, seen, page, total = [], set(), 1, None
    while True:
        frag = fetch_ttph_page(sess, token, page)
        polite_sleep()
        prows, tot = parse_mualai(frag)
        if total is None and tot:
            total = tot
            print("mua_lai total:", total, flush=True)
        fresh = 0
        for v in prows:
            if mualai_key(v) in seen:
                continue
            seen.add(mualai_key(v)); rows.append(v); fresh += 1
        print("mua_lai page %d -> %d fresh (cum %d)" % (page, fresh, len(rows)), flush=True)
        if (total and len(rows) >= total) or fresh == 0:
            break
        page += 1
    _save_mualai(rows)


def cmd_ttph_full():
    sess, token = make_session("/to-chuc-phat-hanh/thong-tin-phat-hanh")
    rows, seen, page, total = [], set(), 1, None
    while True:
        prows, tot = parse_ttph(fetch_ttph_page(sess, token, page))
        polite_sleep()
        if total is None and tot:
            total = tot
            print("ttph total:", total, flush=True)
        fresh = 0
        for v in prows:
            if ttph_key(v) in seen:
                continue
            seen.add(ttph_key(v)); rows.append(v); fresh += 1
        print("ttph page %d -> %d fresh" % (page, fresh), flush=True)
        if (total and len(rows) >= total) or fresh == 0:
            break
        page += 1
    _save_ttph(rows)


def _save_ttph(rows):
    def _w(f):
        w = csv.writer(f)
        w.writerow(TTPH_COLS)
        w.writerows(rows)
    write_file_safe(TTPH_CSV, _w)
    print("ttph saved: %d rows" % len(rows))


# ---------------- incremental update (hang tuan) ----------------
def cmd_update():
    # feed
    existing = list(csv.DictReader(open(FEED_CSV, encoding="utf-8-sig")))
    seen = {feed_key(r) for r in existing}
    sess, token = make_session("/to-chuc-phat-hanh/tin-cong-bo")
    new_rows, page, quiet = [], 1, 0
    while page <= MAX_PAGES and quiet < STOP_AFTER:
        prows, _ = parse_feed(fetch_feed_page(sess, token, page))
        polite_sleep()
        fresh = 0
        for r in prows:
            if feed_key(r) in seen:
                continue
            seen.add(feed_key(r)); new_rows.append(r); fresh += 1
        quiet = quiet + 1 if fresh == 0 else 0
        print("feed page %d -> %d new" % (page, fresh), flush=True)
        page += 1
    if new_rows:
        _save_feed(new_rows + existing)
    print("feed: +%d rows (total %d)" % (len(new_rows), len(existing) + len(new_rows)))

    # ttph + mua_lai (cung 1 response, 2 bang)
    raw = list(csv.reader(open(TTPH_CSV, encoding="utf-8-sig")))
    header, existing = raw[0], raw[1:]
    seen = {ttph_key(v) for v in existing}
    ml_existing = []
    if os.path.exists(MUALAI_CSV):
        ml_existing = list(csv.reader(open(MUALAI_CSV, encoding="utf-8-sig")))[1:]
    ml_seen = {mualai_key(v) for v in ml_existing}
    sess, token = make_session("/to-chuc-phat-hanh/thong-tin-phat-hanh")
    new_rows, ml_new, page, quiet = [], [], 1, 0
    while page <= MAX_PAGES and quiet < STOP_AFTER:
        frag = fetch_ttph_page(sess, token, page)
        polite_sleep()
        prows, _ = parse_ttph(frag)
        ml_rows, _ = parse_mualai(frag)
        fresh = 0
        for v in prows:
            if ttph_key(v) in seen:
                continue
            seen.add(ttph_key(v)); new_rows.append(v); fresh += 1
        for v in ml_rows:
            if mualai_key(v) in ml_seen:
                continue
            ml_seen.add(mualai_key(v)); ml_new.append(v); fresh += 1
        quiet = quiet + 1 if fresh == 0 else 0
        print("ttph page %d -> %d new (ca 2 bang)" % (page, fresh), flush=True)
        page += 1
    if new_rows:
        _save_ttph(new_rows + existing)
    if ml_new:
        _save_mualai(ml_new + ml_existing)
    print("ttph: +%d | mua_lai: +%d rows" % (len(new_rows), len(ml_new)))


if __name__ == "__main__":
    cmds = {"master": cmd_master, "update": cmd_update,
            "feed-full": cmd_feed_full, "ttph-full": cmd_ttph_full,
            "mualai-full": cmd_mualai_full}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds:
        print(__doc__)
        sys.exit(1)
    cmds[sys.argv[1]]()
