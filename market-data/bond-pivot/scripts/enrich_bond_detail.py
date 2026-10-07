# -*- coding: utf-8 -*-
"""Enrich tung bond tu endpoint chi tiet — cac truong KHONG co trong master:
hinh thuc dam bao, ma ISIN, trang thai/ngay/KL dang ky giao dich (san TPDN
rieng le), dai dien NSHTP hien tai, XHTN.

Usage: python scripts/enrich_bond_detail.py [--limit N]
Resumable: bo qua ma_tp da co trong data/processed/bond_detail.csv.
1 request/bond (~0.8s) -> full 6.7k bond ~ 2h; sau do moi tuan chi con bond moi.
"""
import argparse
import csv
import html as H
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hnx_common import BASE, make_session, polite_sleep, write_file_safe

OUT = "data/processed/bond_detail.csv"

# nhan -> ten cot (gia tri = dong ke tiep trong text da bo tag)
LABELS = {
    "Trái phiếu bảo đảm": "dam_bao",
    "Hình thức đảm bảo": "hinh_thuc_dam_bao",
    "Tổ chức đại diện người sở hữu TP": "dai_dien_nshtp",
    "Kết quả XHTN gần nhất": "xhtn_ket_qua",
    "Đơn vị XHTN gần nhất": "xhtn_don_vi",
    "Mã TP giao dịch": "ma_tp_giao_dich",
    "Mã ISIN": "ma_isin",
    "Trạng thái ĐKGD": "trang_thai_dkgd",
    "Ngày giao dịch đầu tiên": "ngay_gd_dau_tien",
    "Khối lượng ĐKGD": "kl_dkgd",
}
# gia tri bi coi la rong neu trung 1 nhan khac hoac cac heading nay
NOT_VALUE = set(LABELS) | {
    "Tình trạng trái phiếu", "Ngày hiệu lực", "Ngày giao dịch cuối cùng",
    "Thông tin giao dịch", "Thông tin công bố", "CBTT phát hành",
    "CBTT đăng ký giao dịch", "Xem chi tiết >>", "Đối tượng giao dịch trái phiếu",
    "Đối tượng chào bán", "Mua lại/ Hoán đổi", "Có", "Không",
}

FIELDS = ["ma_tp"] + list(LABELS.values())


def parse_detail(html_text):
    txt = re.sub(r"<[^>]+>", "\n", H.unescape(html_text))
    lines = [x.strip() for x in txt.split("\n") if x.strip()]
    rec = {}
    for i, l in enumerate(lines):
        if l in LABELS and i + 1 < len(lines):
            v = lines[i + 1]
            if l == "Trái phiếu bảo đảm":
                # theo sau la 2 dong "Có"/"Không" — dong nao duoc danh dau thi
                # khong phan biet duoc qua text -> doc tu the input checked
                continue
            rec[LABELS[l]] = "" if v in NOT_VALUE else v[:120]
    # dam bao: radio name="rdWarranted", value Y/N, cai nao co checked
    m = re.search(r'value="([YN])"[^>]*\bchecked\b[^>]*name="rdWarranted"', html_text)
    if not m:
        m = re.search(r'name="rdWarranted"[^>]*value="([YN])"[^>]*\bchecked\b', html_text) \
            or re.search(r'value="([YN])"[^>]*name="rdWarranted"[^>]*\bchecked\b', html_text) \
            or re.search(r'input value="([YN])" type="radio" checked name="rdWarranted"', html_text)
    if m:
        rec["dam_bao"] = "Có" if m.group(1) == "Y" else "Không"
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10000)
    args = ap.parse_args()

    master = list(csv.DictReader(open("data/processed/bond_master.csv", encoding="utf-8-sig")))
    rows, done = [], set()
    if os.path.exists(OUT):
        rows = list(csv.DictReader(open(OUT, encoding="utf-8-sig")))
        done = {r["ma_tp"] for r in rows}

    todo = [m for m in master if m["ma_tp"].strip().upper() not in done]
    # uu tien bond dang luu hanh (dang quan tam nhat)
    todo.sort(key=lambda m: 0 if "Lưu hành" in m["tinh_trang"] else 1)
    todo = todo[:args.limit]
    print("detail backlog: %d, xu ly %d" % (len(master) - len(done), len(todo)), flush=True)
    if not todo:
        return

    sess, token = make_session("/to-chuc-phat-hanh/danh-sach-trai-phieu")
    for i, m in enumerate(todo, 1):
        code = m["ma_tp"].strip().upper()
        try:
            r = sess.get(BASE + "/to-chuc-phat-hanh/thong-tin-chi-tiet-trai-phieu",
                         params={"bond_code": code}, headers={"CP-TOKEN": token},
                         timeout=30)
            rec = parse_detail(r.text)
        except Exception as e:
            print("  fail %s: %s" % (code, e), flush=True)
            rec = {}
        polite_sleep()
        row = dict.fromkeys(FIELDS, "")
        row["ma_tp"] = code
        row.update({k: v for k, v in rec.items() if k in row})
        rows.append(row)
        if i % 25 == 0 or i == len(todo):
            def _w(f):
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader(); w.writerows(rows)
            write_file_safe(OUT, _w)
            print("%d/%d (vd: %s dkgd=%s isin=%s)" % (
                i, len(todo), code, row["trang_thai_dkgd"][:20], row["ma_isin"]),
                flush=True)
    print("done: %d bond co detail" % len(rows))


if __name__ == "__main__":
    main()
