# -*- coding: utf-8 -*-
"""Nap file Excel xuat tu FiinProX ("Bieu do phan tich tai chinh") vao master.

Dung de BACKFILL lich su cho nhung chi tieu ma NHNN chi dang so cua ngay hien tai
(lai suat lien ngan hang, doanh so, lai suat dieu hanh, ty gia trung tam...).

Cach dung:
    python import_fiinprox.py                 # quet *.xlsx trong thu muc tool + .\fiinprox\
    python import_fiinprox.py duong_dan.xlsx  # nap 1 file cu the

Cau truc file FiinProX (do thuc te tren ban xuat 08/09/2026):
    dong 5-6 : "Tinh nang" / "Ngay trich xuat"
    dong 8   : ten cot, cot 1 la "Ngay"
    dong 10  : don vi, dang "Don vi : %" hoac "Don vi : VND"
    tu dong 11: du lieu, ngay giam dan
Script khong hard-code so dong ma DO: tim dong co o dau la "Ngay", dong "Don vi"
la dong dau tien phia duoi co chua "Don vi".

Ten cot duoc so khop bang regex sau khi bo dau -> them chi tieu moi chi can them
1 dong vao REG.
"""
from __future__ import annotations

import datetime as dt
import glob
import os
import re
import sys

import openpyxl

from common import ROOT, log, merge_master, row, setup_stdout

# (regex tren ten cot da bo dau) -> (series_id, ten, don vi dich, tan suat, node_id, node_name)
# series_id va ten co the chua "{0}" - se duoc thay bang group 1 cua regex (vd so ngay ky han).
REG = [
    (r"lai suat tai cap von",          ("policy_refinance",  "Lai suat tai cap von",  "%/nam", "D", "N03", "Noi rang buoc va nguon")),
    (r"lai suat tai chiet khau",       ("policy_rediscount", "Lai suat tai chiet khau", "%/nam", "D", "N03", "Noi rang buoc va nguon")),
    (r"lai suat.*lien ngan hang.*qua dem", ("ib_on", "LNH binh quan qua dem", "%/nam", "D", "N08", "Lai suat TT2")),
    (r"lai suat.*lien ngan hang.*1 tuan",  ("ib_1w", "LNH binh quan 1 tuan",  "%/nam", "D", "N08", "Lai suat TT2")),
    (r"lai suat.*lien ngan hang.*2 tuan",  ("ib_2w", "LNH binh quan 2 tuan",  "%/nam", "D", "N08", "Lai suat TT2")),
    (r"lai suat.*lien ngan hang.*1 thang", ("ib_1m", "LNH binh quan 1 thang", "%/nam", "D", "N08", "Lai suat TT2")),
    (r"lai suat.*lien ngan hang.*3 thang", ("ib_3m", "LNH binh quan 3 thang", "%/nam", "D", "N08", "Lai suat TT2")),
    (r"lai suat.*lien ngan hang.*6 thang", ("ib_6m", "LNH binh quan 6 thang", "%/nam", "D", "N08", "Lai suat TT2")),
    (r"lai suat.*lien ngan hang.*9 thang", ("ib_9m", "LNH binh quan 9 thang", "%/nam", "D", "N08", "Lai suat TT2")),
    (r"lai suat.*lien ngan hang.*1 nam",   ("ib_1y", "LNH binh quan 1 nam",   "%/nam", "D", "N08", "Lai suat TT2")),

    # DOANH SO - phai neo dau dong (^). FiinProX dat ten cot ky han khac la
    # "Doanh so 1 tuan (Doanh so giao dich QUA DEM 1 tuan)" -> pattern "doanh so.*qua dem"
    # se nuot HET moi ky han vao ib_vol_on. Neo ^ de chi bat nhan ngay sau "doanh so".
    (r"^doanh so qua dem",  ("ib_vol_on", "Doanh so LNH qua dem", "ty VND", "D", "N09", "Nguon TT2")),
    (r"^doanh so 1 tuan",   ("ib_vol_1w", "Doanh so LNH 1 tuan",  "ty VND", "D", "N09", "Nguon TT2")),
    (r"^doanh so 2 tuan",   ("ib_vol_2w", "Doanh so LNH 2 tuan",  "ty VND", "D", "N09", "Nguon TT2")),
    (r"^doanh so 1 thang",  ("ib_vol_1m", "Doanh so LNH 1 thang", "ty VND", "D", "N09", "Nguon TT2")),
    (r"^doanh so 3 thang",  ("ib_vol_3m", "Doanh so LNH 3 thang", "ty VND", "D", "N09", "Nguon TT2")),
    (r"^doanh so 6 thang",  ("ib_vol_6m", "Doanh so LNH 6 thang", "ty VND", "D", "N09", "Nguon TT2")),
    (r"^doanh so 9 thang",  ("ib_vol_9m", "Doanh so LNH 9 thang", "ty VND", "D", "N09", "Nguon TT2")),
    (r"^doanh so 1 nam",    ("ib_vol_1y", "Doanh so LNH 1 nam",   "ty VND", "D", "N09", "Nguon TT2")),
    (r"ty gia trung tam",              ("fx_central", "Ty gia trung tam", "VND/USD", "D", "N04", "Ty gia USD/VND")),

    # --- nghiep vu thi truong mo (node N05) ---
    # LUU Y DAU: FiinProX ghi tin phieu luu hanh la SO AM (hut tien), reverse repo duong
    # (bom tien) -> bom rong = omo_outstanding + bill_outstanding, KHONG phai tru.
    (r"reverse repo\s*-\s*kl luu hanh",
     ("omo_outstanding", "Reverse repo dang luu hanh (bom)", "ty VND", "D", "N05", "NHNN hut bom")),
    (r"reverse repo.*lai suat trung thau.*ky han (\d+) ngay",
     ("omo_win_{0}d_rate", "Lai suat trung thau OMO ky han {0} ngay", "%/nam", "D", "N05", "NHNN hut bom")),
    (r"tin phieu\s*-\s*kl luu hanh",
     ("bill_outstanding", "Tin phieu NHNN luu hanh (am = hut)", "ty VND", "D", "N05", "NHNN hut bom")),
    (r"tin phieu.*lai suat trung thau.*ky han (\d+) ngay",
     ("bill_win_{0}d_rate", "Lai suat trung thau tin phieu ky han {0} ngay", "%/nam", "D", "N05", "NHNN hut bom")),

    # --- cung tien, tin dung, huy dong (theo thang) ---
    (r"tong phuong tien thanh toan",
     ("m2", "Tong phuong tien thanh toan (M2)", "ty VND", "M", "N12", "Tin dung giai ngan")),
    (r"tong du no tin dung",
     ("credit_outstanding", "Tong du no tin dung", "ty VND", "M", "N12", "Tin dung giai ngan")),
    (r"tien gui cua cac tckt",
     ("deposits_corporate", "Tien gui cua cac TCKT", "ty VND", "M", "N10", "Room va chi phi von NH")),
    (r"tien gui cua cu dan",
     ("deposits_household", "Tien gui cua cu dan", "ty VND", "M", "N10", "Room va chi phi von NH")),
]

_ACCENTS = (
    ("àáảãạăằắẳẵặâầấẩẫậ", "a"), ("èéẻẽẹêềếểễệ", "e"), ("ìíỉĩị", "i"),
    ("òóỏõọôồốổỗộơờớởỡợ", "o"), ("ùúủũụưừứửữự", "u"), ("ỳýỷỹỵ", "y"), ("đ", "d"),
)


def _norm(s) -> str:
    s = str(s or "").lower().strip()
    for src, dst in _ACCENTS:
        for ch in src:
            s = s.replace(ch, dst)
    return re.sub(r"\s+", " ", s)


def _factor(src_unit: str, dst_unit: str) -> float:
    """FiinProX luu % duoi dang thap phan (0.045 = 4,5%) va tien theo VND tuyet doi."""
    su, du = _norm(src_unit), _norm(dst_unit)
    if "%" in su and "%" in du:
        return 100.0
    if su.endswith("vnd") and du.startswith("ty"):        # VND -> ty VND
        return 1e-9
    if "ty" in su and du.startswith("ty"):
        return 1.0
    return 1.0


def _match(header: str):
    """Tra ve meta da dien group (vd ky han 7 ngay -> omo_win_7d_rate)."""
    h = _norm(header)
    for pat, meta in REG:
        m = re.search(pat, h)
        if not m:
            continue
        g = m.groups()
        if not g:
            return meta
        sid, name, unit, freq, node_id, node_name = meta
        return (sid.format(*g), name.format(*g), unit, freq, node_id, node_name)
    return None


def read_file(path: str) -> list:
    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.worksheets[0]
    grid = list(ws.iter_rows(values_only=True))

    hdr_i = next((i for i, r in enumerate(grid) if r and _norm(r[0]) == "ngay"), None)
    if hdr_i is None:
        log("  ! %s: khong tim thay dong tieu de co o dau la 'Ngay'" % os.path.basename(path))
        return []
    # CHU Y: o don vi ghi "Don vi : %" co dau -> phai _norm truoc khi do, khong so khop
    # chuoi tho (bug da dinh: khong nhan ra don vi -> he so quy doi = 1 -> 0,0462 thay vi 4,62)
    unit_i = next((i for i in range(hdr_i + 1, min(hdr_i + 5, len(grid)))
                   if grid[i] and any("don vi" in _norm(c) for c in grid[i])), None)
    header = grid[hdr_i]
    units = grid[unit_i] if unit_i is not None else [None] * len(header)

    cols = {}
    for j in range(1, len(header)):
        meta = _match(header[j])
        if not meta:
            if header[j]:
                log("  ? bo qua cot chua khai bao: %s" % str(header[j])[:60])
            continue
        src_unit = re.sub(r"^.*don vi\s*:\s*", "", _norm(units[j]))
        f = _factor(src_unit, meta[2])
        if unit_i is None or not src_unit:
            log("  ! khong doc duoc don vi cot '%s' -> giu nguyen so goc" % str(header[j])[:50])
        cols[j] = (meta, f)

    if not cols:
        log("  ! %s: khong co cot nao khop REG" % os.path.basename(path))
        return []

    out, stat = [], {}
    for r in grid[hdr_i + 1:]:
        if not r or not isinstance(r[0], (dt.datetime, dt.date)):
            continue
        d = (r[0].date() if isinstance(r[0], dt.datetime) else r[0]).isoformat()
        for j, ((sid, name, unit, freq, node_id, node_name), f) in cols.items():
            v = r[j] if j < len(r) else None
            if v is None or isinstance(v, str):
                continue
            out.append(row(d, sid, round(float(v) * f, 6), series_name=name, unit=unit,
                           freq=freq, source="FiinProX", node_id=node_id, node_name=node_name))
            s = stat.setdefault(sid, [0, d, d])
            s[0] += 1
            s[1], s[2] = min(s[1], d), max(s[2], d)

    log("  %s" % os.path.basename(path))
    for sid, (n, lo, hi) in sorted(stat.items()):
        log("    %-18s %5d dong  %s -> %s" % (sid, n, lo, hi))
    return out


def main() -> None:
    setup_stdout()
    if len(sys.argv) > 1:
        files = sys.argv[1:]
    else:
        files = sorted(glob.glob(os.path.join(ROOT, "FiinProX*.xls*")) +
                       glob.glob(os.path.join(ROOT, "fiinprox", "*.xls*")))
    if not files:
        log("Khong thay file FiinProX nao. Dat file .xlsx vao %s hoac thu muc fiinprox\\" % ROOT)
        return

    rows = []
    for f in files:
        rows += read_file(f)
    if not rows:
        log("Khong nap duoc dong nao.")
        return

    df = merge_master(rows)
    log("Master: %d dong, %d series, %s -> %s"
        % (len(df), df["series_id"].nunique(), df["date"].min(), df["date"].max()))
    log("Chay 'python fetch_all.py --build' de tinh lai chi tieu phai sinh + bao cao.")


if __name__ == "__main__":
    main()
