# -*- coding: utf-8 -*-
r"""
import_manual.py
----------------
Đọc các file nhập tay/AI trong manual_input\<Ngành>\<MÃ>_<Q|Y>.csv (wide: cột chỉ tiêu
+ các kỳ) -> trả về list facts dạng long, sẵn sàng gộp vào pipeline.

Quy ước:
  - Thư mục con = NGÀNH (dùng khi mã không tra được ICB).
  - Tên file = <MÃ>_<Q|Y> (vd VND_Q.csv). Phần Q/Y chỉ để gợi ý; tần suất thực lấy
    từ chính nhãn kỳ (Q1/2026 -> quý, 2025 -> năm).
  - 3 cột meta: statement_code, row_order, (Chỉ tiêu | metric). Các cột còn lại là kỳ.
  - Ô trống = bỏ qua. Số có thể chứa dấu phẩy ngăn nghìn.

Hàm chính: load_manual(icb_map) -> facts (đã gắn ngành).
"""
import os
import re
import csv
import glob

import unpivot_fiinprox as U

# tên file: "<MÃ> [Q].csv" / "<MÃ> [Y].csv"  (mã giữ nguyên dấu cách)
_FNAME = re.compile(r"^(?P<ticker>.+?)\s*\[(?P<freq>[QY])\]$")

HERE = os.path.dirname(os.path.abspath(__file__))
MANUAL_DIR = os.path.join(HERE, "manual_input")
META_KEYS = {"statement_code", "row_order", "chỉ tiêu", "metric", "level", "statement_name"}


def _norm(s):
    return ("" if s is None else str(s)).strip()


def _to_num(v):
    v = _norm(v).replace(" ", "")
    if v == "":
        return None
    neg = v.startswith("(") and v.endswith(")")
    if neg:
        v = v[1:-1]
    v = v.replace(",", "")
    try:
        n = float(v)
        return -n if neg else n
    except ValueError:
        return None


def _read_file(fp, nganh, icb_map):
    base = os.path.splitext(os.path.basename(fp))[0]
    m = _FNAME.match(base)
    ticker = m.group("ticker").strip() if m else base.strip()

    facts = []
    with open(fp, "r", encoding="utf-8-sig", newline="") as fh:
        rdr = csv.DictReader(fh)
        cols = rdr.fieldnames or []
        period_cols = [c for c in cols if U.parse_period(c)]  # cột nào là kỳ hợp lệ
        for row in rdr:
            sc = _norm(row.get("statement_code"))
            metric = _norm(row.get("Chỉ tiêu") or row.get("metric"))
            if not sc or not metric:
                continue
            ro = row.get("row_order") or "0"
            for pc in period_cols:
                val = _to_num(row.get(pc))
                if val is None:
                    continue
                fr, year, quarter = U.parse_period(pc)
                facts.append({
                    "ticker": ticker, "entity_type": "", "freq": fr,
                    "statement_code": sc, "statement_name": _norm(row.get("statement_name")),
                    "unit": "Tỷ VND", "currency": "VND",
                    "row_order": ro, "level": _norm(row.get("level")),
                    "parent": _norm(row.get("parent")),
                    "metric": metric, "period": pc, "year": year,
                    "quarter": "" if quarter is None else quarter, "value": val,
                })
    # gắn ngành: ưu tiên ICB theo mã, không có thì dùng tên thư mục con
    U.enrich_industry(facts, icb_map, default_nganh=nganh)
    return facts, ticker


def _load_skeleton():
    """Lookup từ template_skeleton.csv:
    (sc,metric)->row_order ; (sc,row_order)->(metric, parent)."""
    by_metric, by_ro = {}, {}
    sk = os.path.join(HERE, "output", "template_skeleton.csv")
    if os.path.isfile(sk):
        with open(sk, "r", encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                sc = _norm(r["statement_code"])
                ro = _norm(r["row_order"])
                me = _norm(r["metric"])
                parent = _norm(r.get("parent"))
                by_metric[(sc, me.lower())] = ro
                by_ro[(sc, ro)] = (me, parent)
    return by_metric, by_ro


def _set_nganh(fact, icb_map, row_nganh):
    """Gắn ngành cho 1 fact long: ICB theo mã -> cột nganh -> rỗng."""
    info = icb_map.get(str(fact["ticker"]).strip().upper())
    if info:
        for k in U.ICB_COLS:
            fact[k] = info.get(k, "")
    else:
        fact["ten_cong_ty"] = ""
        for k in ("nganh_L1", "nganh_L2", "nganh_L3", "nganh_L4"):
            fact[k] = row_nganh


def _read_long(fp, icb_map, sk_metric, sk_ro):
    """File long: mỗi dòng 1 số liệu. Cột: ticker, statement_code, period, value bắt buộc;
    metric HOẶC row_order; freq & nganh tuỳ chọn (freq suy từ period)."""
    facts = 0
    out = []
    with open(fp, "r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            ticker = _norm(row.get("ticker"))
            if not ticker or ticker.startswith("#"):
                continue  # bỏ dòng trống / dòng ví dụ (#)
            sc = _norm(row.get("statement_code")).upper()
            period = _norm(row.get("period"))
            pp = U.parse_period(period)
            val = _to_num(row.get("value"))
            if not sc or not pp or val is None:
                continue
            fr, year, quarter = pp
            metric = _norm(row.get("metric") or row.get("Chỉ tiêu"))
            ro = _norm(row.get("row_order"))
            # bù phần thiếu từ khung chuẩn
            if not ro and metric:
                ro = sk_metric.get((sc, metric.lower()), "0")
            sk_me, sk_parent = sk_ro.get((sc, ro), ("", ""))
            if not metric and ro:
                metric = sk_me
            if not metric:
                continue
            fact = {
                "ticker": ticker, "entity_type": "", "freq": _norm(row.get("freq")) or fr,
                "statement_code": sc, "statement_name": "",
                "unit": "Tỷ VND", "currency": "VND",
                "row_order": ro or "0", "level": "",
                "parent": _norm(row.get("parent")) or sk_parent, "metric": metric,
                "period": period, "year": year,
                "quarter": "" if quarter is None else quarter, "value": val,
            }
            _set_nganh(fact, icb_map, _norm(row.get("nganh_L2") or row.get("nganh")))
            out.append(fact)
            facts += 1
    return out, facts


def load_manual(icb_map):
    facts = []
    files = 0
    if not os.path.isdir(MANUAL_DIR):
        return facts, files

    # (1) file LONG đặt ngay ở gốc manual_input\*.csv (trừ file _...)
    sk_metric, sk_ro = _load_skeleton()
    for fp in sorted(glob.glob(os.path.join(MANUAL_DIR, "*.csv"))):
        if os.path.basename(fp).startswith("_"):
            continue
        f, n = _read_long(fp, icb_map, sk_metric, sk_ro)
        if f:
            facts.extend(f)
            files += 1
            print(f"    nhập tay (long): {os.path.basename(fp)} -> {n:,} dòng")

    # (2) file WIDE trong thư mục con manual_input\<Ngành>\<MÃ> [Q|Y].csv
    for sub in sorted(os.listdir(MANUAL_DIR)):
        subdir = os.path.join(MANUAL_DIR, sub)
        if not os.path.isdir(subdir) or sub.startswith("_") or sub.lower() == "template":
            continue
        nganh = sub  # tên thư mục con = ngành
        for fp in sorted(glob.glob(os.path.join(subdir, "*.csv"))):
            f, ticker = _read_file(fp, nganh, icb_map)
            if f:
                facts.extend(f)
                files += 1
                print(f"    nhập tay (wide): {os.path.relpath(fp, MANUAL_DIR)} -> {ticker}: {len(f):,} ô")
    return facts, files


if __name__ == "__main__":
    # chạy độc lập để kiểm tra
    import json
    icb = U.load_icb_map(os.path.join(HERE, "output"))
    fc, n = load_manual(icb)
    print(f"Tổng: {len(fc):,} facts từ {n} file nhập tay")
    if fc:
        print(json.dumps(fc[0], ensure_ascii=False, indent=2))
