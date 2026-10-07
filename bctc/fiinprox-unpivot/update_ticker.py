# -*- coding: utf-8 -*-
r"""
update_ticker.py
----------------
Cập nhật lại số liệu cho ĐÚNG 1 ticker sau khi sửa file gốc FiinProX, KHÔNG chạy lại
cả pipeline (không đọc lại 173 mã kia).

Làm gì:
  1) Đọc lại file FiinProX của ticker (Quarterly + Yearly) -> facts mới, gắn ngành.
  2) Vá master fiinprox_facts_all.csv: thay khối dòng của ticker (stream 1 lượt).
  3) Vá by_nganh_L2\<Ngành>.csv tương tự.
  4) Vá GỘP NGÀNH industry\<Ngành>\: cộng/trừ phần đóng góp của ticker (incremental),
     ghi lại industry_fs_long.csv + industry_FS_*.csv + industry_SoCty_*.csv.
  5) Cập nhật cache cho file đã sửa.

Dùng:
    python update_ticker.py "HD Securities"
    python update_ticker.py VND
"""
import os
import csv
import sys
import glob

import unpivot_fiinprox as U
import aggregate_industry as A
import run_pipeline as R

csv.field_size_limit(10_000_000)
HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "output")
MASTER = os.path.join(OUTDIR, "fiinprox_facts_all.csv")


def find_sources(ticker):
    """Tìm file FiinProX khớp ticker — chỉ bản MỚI NHẤT mỗi (tần suất, mã)."""
    out = []
    for folder, default_nganh in R.read_config():
        files, _ = R.latest_files(folder)
        for fp in files:
            if U.ticker_from_filename(fp).strip().lower() == ticker.strip().lower():
                out.append((fp, default_nganh))
    return out


def stream_replace(path, ticker, new_rows):
    """Thay khối dòng của 1 ticker trong CSV (master/by_nganh). Trả về list dòng CŨ."""
    if not os.path.isfile(path):
        return []
    tmp = path + ".tmp"
    old = []
    tl = ticker.strip().lower()
    state = 0  # 0 trước khối, 1 trong khối, 2 đã chèn xong
    with open(path, "r", encoding="utf-8-sig", newline="") as fin, \
         open(tmp, "w", encoding="utf-8-sig", newline="") as fout:
        rdr = csv.DictReader(fin)
        w = csv.DictWriter(fout, fieldnames=U.FACT_COLS, extrasaction="ignore")
        w.writeheader()
        for row in rdr:
            if row["ticker"].strip().lower() == tl:
                old.append(row)
                state = 1
                continue
            if state == 1:                     # khối ticker vừa kết thúc -> chèn dòng mới
                w.writerows(new_rows)
                state = 2
            w.writerow(row)
        if state == 1:                          # khối ticker nằm ở cuối file
            w.writerows(new_rows)
        elif state == 0:                        # ticker chưa có -> thêm vào cuối
            w.writerows(new_rows)
    os.replace(tmp, path)
    return old


def patch_industry(nganh, old_rows, new_rows):
    """Cộng/trừ phần đóng góp ticker vào gộp ngành (incremental)."""
    ind_dir = os.path.join(OUTDIR, "industry", U.safe_name(nganh))
    long_path = os.path.join(ind_dir, "industry_fs_long.csv")
    if not os.path.isfile(long_path):
        print("  ! chưa có industry cho ngành này, bỏ qua vá gộp:", nganh)
        return
    # nạp gộp hiện tại
    agg = {}
    with open(long_path, "r", encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            key = (r["freq"], r["statement_code"], U._int(r["row_order"]),
                   r["metric"], r["period"])
            agg[key] = {
                "freq": r["freq"], "statement_code": r["statement_code"],
                "statement_name": r["statement_name"], "row_order": U._int(r["row_order"]),
                "parent": r.get("parent", ""), "metric": r["metric"], "period": r["period"],
                "year": r["year"], "quarter": r["quarter"],
                "n_cong_ty": int(float(r["n_cong_ty"])), "tong_gia_tri": float(r["tong_gia_tri"]),
            }

    def key_of(f):
        return (f["freq"], f["statement_code"], U._int(f["row_order"]), f["metric"], f["period"])

    # trừ đóng góp CŨ
    for f in old_rows:
        k = key_of(f)
        if k in agg:
            agg[k]["tong_gia_tri"] -= float(f["value"])
            agg[k]["n_cong_ty"] -= 1
    # cộng đóng góp MỚI
    for f in new_rows:
        k = key_of(f)
        if k in agg:
            agg[k]["tong_gia_tri"] += float(f["value"])
            agg[k]["n_cong_ty"] += 1
        else:
            agg[k] = {
                "freq": f["freq"], "statement_code": f["statement_code"],
                "statement_name": f.get("statement_name", ""), "row_order": U._int(f["row_order"]),
                "parent": f.get("parent", ""), "metric": f["metric"], "period": f["period"],
                "year": f.get("year", ""), "quarter": f.get("quarter", ""),
                "n_cong_ty": 1, "tong_gia_tri": float(f["value"]),
            }
    # bỏ ô không còn công ty nào
    rows = [v for v in agg.values() if v["n_cong_ty"] > 0]
    for v in rows:
        v["tong_gia_tri"] = round(v["tong_gia_tri"], 6)
    rows.sort(key=lambda d: (d["freq"],
                             A.STMT_ORDER.index(d["statement_code"]) if d["statement_code"] in A.STMT_ORDER else 9,
                             U._int(d["row_order"]), d["metric"], U._int(d["year"]), U._int(d["quarter"])))

    with open(long_path, "w", encoding="utf-8-sig", newline="") as fh:
        cols = ["freq", "statement_code", "statement_name", "row_order", "parent", "metric",
                "period", "year", "quarter", "n_cong_ty", "tong_gia_tri"]
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    for fq in ("Q", "Y"):
        A.write_wide_csv(rows, fq, ind_dir)
    print(f"  vá gộp ngành: {len(rows):,} dòng -> {ind_dir}")


def main():
    if len(sys.argv) < 2:
        raise SystemExit('Dùng: python update_ticker.py "HD Securities"')
    ticker = sys.argv[1]

    srcs = find_sources(ticker)
    if not srcs:
        raise SystemExit(f"Không tìm thấy file FiinProX cho ticker: {ticker}")
    print(f"Cập nhật ticker: {ticker}  ({len(srcs)} file nguồn)")

    icb_map = U.load_icb_map(OUTDIR)
    new_facts, nganh = [], None
    for fp, default_nganh in srcs:
        facts, hit = R.load_or_parse(fp, use_cache=True)  # đọc lại (cache miss vì đã sửa) + cập nhật cache
        U.enrich_industry(facts, icb_map, default_nganh=default_nganh)
        new_facts.extend(facts)
        print(f"  đọc lại: {os.path.basename(fp)} -> {len(facts):,} facts ({'cache' if hit else 'parse mới'})")
    if new_facts:
        nganh = new_facts[0].get("nganh_L2") or U.UNCLASSIFIED
    R.apply_fixes(new_facts)  # áp bảng sửa lỗi nguồn fixes.csv
    U.sort_facts(new_facts)

    # 1) master
    old_master = stream_replace(MASTER, ticker, new_facts)
    print(f"  master: thay {len(old_master):,} dòng cũ bằng {len(new_facts):,} dòng mới")
    # 2) by_nganh
    by_path = os.path.join(OUTDIR, "by_nganh_L2", U.safe_name(nganh) + ".csv")
    stream_replace(by_path, ticker, new_facts)
    # 3) industry (dùng dòng cũ lấy được từ master để trừ chính xác)
    patch_industry(nganh, old_master, new_facts)

    print("Xong. Đã cập nhật riêng ticker, không đụng các mã khác.")


if __name__ == "__main__":
    main()
