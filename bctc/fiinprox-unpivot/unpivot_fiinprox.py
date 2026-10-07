# -*- coding: utf-8 -*-
"""
unpivot_fiinprox.py
-------------------
Unpivot (wide -> long) FiinProX financial-statement Excel exports into tidy CSVs
ready for SQL / metadata lookups.

Each FiinProX export workbook has one sheet per statement:
    Bảng cân đối kế toán   -> BS   (Balance sheet)
    Kết quả kinh doanh     -> IS   (Income statement)
    Lưu chuyển tiền tệ     -> CF   (Cash flow)
    Thuyết minh            -> NOTE (Notes)
    Báo cáo an toàn vốn    -> CAR  (Capital adequacy - usually no period grid, skipped)

Sheet layout (auto-detected, not hard-coded by row number):
    rows 1-10 : metadata block (Mã CK / Loại / Xem theo=tần suất / Tiền tệ / đơn vị)
    header    : first col-A cell starting with "Chỉ tiêu"; period labels in B.. (Q3/2012 | 2008)
    +1..+3    : Trạng thái kiểm toán | Công ty kiểm toán | Loại ý kiến kiểm toán  (per period)
    rest      : line items; leading spaces in col A encode the indent / hierarchy level

Outputs (per input file, into --outdir):
    <stem>_facts.csv    long fact table  (one row per metric x period observation)
    <stem>_periods.csv  per-period audit metadata

And combined across all inputs:
    fiinprox_facts_all.csv
    fiinprox_periods_all.csv

Usage:
    python unpivot_fiinprox.py file1.xlsx [file2.xlsx ...] [--outdir DIR]
    python unpivot_fiinprox.py --indir D:\\Database          # all FiinProX_*.xlsx in a folder
"""
import sys
import os
import re
import csv
import glob
import argparse
import datetime as dt

import openpyxl

SHEET_CODE = {
    "Bảng cân đối kế toán": "BS",
    "Kết quả kinh doanh": "IS",
    "Lưu chuyển tiền tệ": "CF",
    "Thuyết minh": "NOTE",
    "Báo cáo an toàn vốn": "CAR",
}

AUDIT_LABELS = {
    "Trạng thái kiểm toán": "audit_status",
    "Công ty kiểm toán": "audit_firm",
    "Loại ý kiến kiểm toán": "audit_opinion",
}

ICB_COLS = ["ten_cong_ty", "nganh_L1", "nganh_L2", "nganh_L3", "nganh_L4"]

FACT_COLS = [
    "ticker", "ten_cong_ty", "nganh_L1", "nganh_L2", "nganh_L3", "nganh_L4",
    "entity_type", "freq", "statement_code", "statement_name",
    "unit", "currency", "row_order", "level", "parent", "metric",
    "period", "year", "quarter", "value",
]
PERIOD_COLS = [
    "ticker", "freq", "statement_code", "statement_name",
    "period", "year", "quarter", "audit_status", "audit_firm", "audit_opinion",
]

# Thư mục tool fs-extractor (nguồn bảng phân ngành ICB từ vnstock/VCI)
FS_EXTRACTOR_DIR = r"D:\bctc\fs-extractor"
UNCLASSIFIED = "_KhongRoNganh"


def _txt(v):
    return "" if v is None else str(v).strip()


def parse_period(label):
    """'Q3/2012' -> ('Q', 2012, 3); '2008' -> ('Y', 2008, None). Returns (freq, year, quarter)."""
    s = _txt(label)
    if not s:
        return None
    if s.upper().startswith("Q") and "/" in s:
        q, y = s[1:].split("/", 1)
        try:
            return ("Q", int(y), int(q))
        except ValueError:
            return None
    if s.isdigit() and len(s) == 4:
        return ("Y", int(s), None)
    return None


def to_number(v):
    """Coerce a cell to float. Returns (value_or_None, ok)."""
    if v is None or v == "":
        return None, True
    if isinstance(v, (int, float)):
        return float(v), True
    s = str(v).strip().replace(" ", "")
    if s == "":
        return None, True
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    s = s.replace(",", "")
    try:
        n = float(s)
        return (-n if neg else n), True
    except ValueError:
        return None, False


def indent_level(name):
    raw = "" if name is None else str(name)
    stripped = raw.lstrip(" ")
    spaces = len(raw) - len(stripped)
    return spaces // 5, stripped.strip()


def find_meta(rows):
    """Scan the top block for ticker / entity / freq / currency / unit."""
    meta = {"ticker": "", "entity_type": "", "freq_label": "", "currency": "", "unit": ""}
    for r in rows[:10]:
        cells = [_txt(c) for c in r]
        for i, c in enumerate(cells):
            nxt = cells[i + 1] if i + 1 < len(cells) else ""
            if c == "Mã CK":
                meta["ticker"] = nxt
            elif c == "Loại":
                meta["entity_type"] = nxt
            elif c == "Xem theo":
                meta["freq_label"] = nxt
            elif c == "Tiền tệ":
                meta["currency"] = nxt
                # unit usually sits two cells further on the same row (e.g. 'Tỷ VND')
                if i + 2 < len(cells) and cells[i + 2]:
                    meta["unit"] = cells[i + 2]
    return meta


def process_sheet(ws, meta_fallback):
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return [], []

    meta = find_meta(rows)
    for k, v in meta_fallback.items():
        if not meta.get(k):
            meta[k] = v

    # locate header row: first col-A cell starting with "Chỉ tiêu"
    hdr_idx = None
    for i, r in enumerate(rows):
        if _txt(r[0]).startswith("Chỉ tiêu"):
            hdr_idx = i
            break
    if hdr_idx is None:
        return [], []

    header = rows[hdr_idx]
    # period columns: index -> (label, freq, year, quarter)
    periods = {}
    for ci in range(1, len(header)):
        p = parse_period(header[ci])
        if p:
            periods[ci] = (_txt(header[ci]), *p)
    if not periods:
        return [], []  # e.g. Báo cáo an toàn vốn

    freq = next(iter(periods.values()))[1]  # 'Q' or 'Y'
    scode = SHEET_CODE.get(ws.title, ws.title[:6].upper())

    # audit metadata rows (immediately after header, matched by label)
    audit = {ci: {"audit_status": "", "audit_firm": "", "audit_opinion": ""} for ci in periods}
    data_start = hdr_idx + 1
    for ri in range(hdr_idx + 1, min(hdr_idx + 6, len(rows))):
        key = AUDIT_LABELS.get(_txt(rows[ri][0]))
        if key:
            for ci in periods:
                if ci < len(rows[ri]):
                    audit[ci][key] = _txt(rows[ri][ci])
            data_start = ri + 1

    facts = []
    order = 0
    stack = []  # ngăn xếp (level, tên) để lần ra chỉ tiêu cha gần nhất
    for ri in range(data_start, len(rows)):
        name_raw = rows[ri][0]
        if _txt(name_raw) == "":
            continue
        level, metric = indent_level(name_raw)
        if metric == "":
            continue
        order += 1
        # cha = chỉ tiêu gần nhất có cấp thụt nhỏ hơn (để phân biệt tên trùng)
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else ""
        stack.append((level, metric))
        for ci, (plabel, pfreq, year, quarter) in periods.items():
            cell = rows[ri][ci] if ci < len(rows[ri]) else None
            val, ok = to_number(cell)
            if val is None:
                continue  # not reported / blank -> skip (keeps the long table sparse-clean)
            facts.append({
                "ticker": meta["ticker"], "entity_type": meta["entity_type"],
                "freq": pfreq, "statement_code": scode, "statement_name": ws.title,
                "unit": meta["unit"], "currency": meta["currency"],
                "row_order": order, "level": level, "parent": parent, "metric": metric,
                "period": plabel, "year": year,
                "quarter": "" if quarter is None else quarter,
                "value": val,
            })

    period_rows = []
    for ci, (plabel, pfreq, year, quarter) in periods.items():
        a = audit[ci]
        period_rows.append({
            "ticker": meta["ticker"], "freq": pfreq,
            "statement_code": scode, "statement_name": ws.title,
            "period": plabel, "year": year,
            "quarter": "" if quarter is None else quarter,
            "audit_status": a["audit_status"], "audit_firm": a["audit_firm"],
            "audit_opinion": a["audit_opinion"],
        })
    return facts, period_rows


def ticker_from_filename(path):
    """Lấy mã/tên từ tên file: ...Hop_nhat_<TOKEN>_<YYYYMMDD>.xlsx -> TOKEN."""
    base = os.path.splitext(os.path.basename(path))[0]
    m = re.search(r"Hop_nhat_(.+?)_\d{6,8}$", base)
    return (m.group(1).strip() if m else base)


STMT_RANK = {"BS": 0, "IS": 1, "CF": 2, "NOTE": 3, "CAR": 4}


def _int(x, d=0):
    try:
        return int(float(x))
    except (ValueError, TypeError):
        return d


def sort_facts(facts):
    """Sắp giống báo cáo gốc: mã -> tần suất -> báo cáo (BS,IS,CF,NOTE) -> dòng
    chỉ tiêu (row_order) -> kỳ theo THỜI GIAN (năm, quý)."""
    facts.sort(key=lambda f: (
        str(f.get("ticker", "")), f.get("freq", ""),
        STMT_RANK.get(f.get("statement_code", ""), 9),
        _int(f.get("row_order")), _int(f.get("year")), _int(f.get("quarter")),
    ))
    return facts


def process_file(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    # global metadata fallback from the first sheet
    first = wb.worksheets[0]
    gmeta = find_meta(list(first.iter_rows(min_row=1, max_row=10, values_only=True)))
    # nhiều CTCK chưa niêm yết để trống ô "Mã CK" -> lấy mã/tên từ tên file
    if not gmeta.get("ticker"):
        gmeta["ticker"] = ticker_from_filename(path)
    facts, periods = [], []
    for ws in wb.worksheets:
        f, p = process_sheet(ws, gmeta)
        facts.extend(f)
        periods.extend(p)
    wb.close()
    return facts, periods


def load_icb_map(outdir, refresh=False):
    """ticker -> {ten_cong_ty, nganh_L1..L4}. Cache vào icb_map.csv (cạnh script).

    Nguồn: fs-extractor/common.get_industry_map() (vnstock/VCI, ICB 4 cấp).
    Lần đầu (hoặc --refresh-icb) gọi mạng; sau đó đọc cache để chạy offline.
    """
    cache = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icb_map.csv")
    rows = None
    if not refresh and os.path.isfile(cache):
        with open(cache, "r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.DictReader(fh))
        print(f"  ICB: dùng cache {os.path.basename(cache)} ({len(rows)} mã)")
    else:
        try:
            if FS_EXTRACTOR_DIR not in sys.path:
                sys.path.insert(0, FS_EXTRACTOR_DIR)
            import common as C  # type: ignore
            df = C.get_industry_map()
            rows = df.to_dict("records")
            with open(cache, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=["ticker"] + ICB_COLS)
                w.writeheader()
                w.writerows(rows)
            print(f"  ICB: kéo từ vnstock/VCI, lưu cache ({len(rows)} mã)")
        except Exception as e:  # noqa: BLE001
            print(f"  ! ICB: không tải được bảng ngành ({e}). Output sẽ không phân ngành.")
            return {}
    out = {}
    for r in rows:
        t = str(r.get("ticker", "")).strip().upper()
        if t:
            out[t] = {k: ("" if r.get(k) in (None, "nan") else str(r.get(k, "")).strip())
                      for k in ICB_COLS}
    return out


def enrich_industry(facts, icb_map, default_nganh=""):
    """Gắn cột ngành vào mỗi fact theo ticker.

    Mã không có trong ICB (CTCK chưa niêm yết...) -> dùng default_nganh (nếu có)
    điền cho cả nganh_L1..L4 để gom về 1 file ngành thay vì _KhongRoNganh.
    """
    blank = {k: "" for k in ICB_COLS}
    fb = dict(blank)
    if default_nganh:
        for k in ("nganh_L1", "nganh_L2", "nganh_L3", "nganh_L4"):
            fb[k] = default_nganh
    for f in facts:
        info = icb_map.get(str(f["ticker"]).strip().upper())
        if info is None:
            info = fb
        for k in ICB_COLS:
            f[k] = info.get(k, "")
    return facts


def safe_name(s):
    """Tên ngành -> tên file an toàn (giữ tiếng Việt, bỏ ký tự cấm Windows)."""
    s = (s or "").strip() or UNCLASSIFIED
    for ch in '\\/:*?"<>|':
        s = s.replace(ch, " ")
    return "_".join(s.split())


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description="Unpivot FiinProX statement workbooks to tidy CSV.")
    ap.add_argument("files", nargs="*", help="One or more FiinProX .xlsx files")
    ap.add_argument("--indir", help="Folder: process all FiinProX_*.xlsx inside")
    ap.add_argument("--outdir", default=None, help="Output folder (default: <script>/output)")
    ap.add_argument("--level", default="L2", choices=["L1", "L2", "L3", "L4"],
                    help="Cấp ICB để tách file theo ngành (default L2)")
    ap.add_argument("--refresh-icb", action="store_true", help="Kéo lại bảng ngành từ vnstock (bỏ cache)")
    ap.add_argument("--no-split", action="store_true", help="Chỉ xuất 1 file gộp, không tách theo ngành")
    ap.add_argument("--default-nganh", default="",
                    help="Ngành mặc định cho mã không tra được ICB (vd 'Dịch vụ tài chính')")
    args = ap.parse_args()

    files = list(args.files)
    if args.indir:
        files += sorted(glob.glob(os.path.join(args.indir, "FiinProX_*.xlsx")))
    files = [f for f in files if not os.path.basename(f).startswith("~$")]
    if not files:
        print("No input files. Drag .xlsx onto the .bat, or pass paths / --indir.")
        sys.exit(1)

    outdir = args.outdir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
    os.makedirs(outdir, exist_ok=True)

    icb_map = load_icb_map(outdir, refresh=args.refresh_icb)

    all_facts = []
    for path in files:
        if not os.path.isfile(path):
            print("  ! missing:", path)
            continue
        facts, _periods = process_file(path)
        all_facts.extend(facts)
        print(f"  + {os.path.basename(path)}: {len(facts):,} facts")

    enrich_industry(all_facts, icb_map, default_nganh=args.default_nganh)
    sort_facts(all_facts)  # thứ tự giống báo cáo gốc

    # File gộp toàn bộ
    out_path = os.path.join(outdir, "fiinprox_facts_all.csv")
    write_csv(out_path, FACT_COLS, all_facts)

    print(f"\nDone @ {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  total: {len(all_facts):,} facts -> fiinprox_facts_all.csv")

    if not args.no_split:
        col = "nganh_" + args.level
        sect_dir = os.path.join(outdir, "by_nganh_" + args.level)
        os.makedirs(sect_dir, exist_ok=True)
        # gom theo ngành
        groups = {}
        for f in all_facts:
            key = f.get(col) or UNCLASSIFIED
            groups.setdefault(key, []).append(f)
        for name, rows in sorted(groups.items()):
            write_csv(os.path.join(sect_dir, safe_name(name) + ".csv"), FACT_COLS, rows)
        print(f"  phân ngành ({args.level}): {len(groups)} file -> {sect_dir}")
        for name, rows in sorted(groups.items()):
            print(f"      - {safe_name(name)}.csv : {len(rows):,}")
    print(f"  out  : {outdir}")


if __name__ == "__main__":
    main()
