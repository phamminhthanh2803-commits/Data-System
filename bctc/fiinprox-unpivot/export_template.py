# -*- coding: utf-8 -*-
r"""
export_template.py
------------------
Tạo file MẪU để nhập tay (hoặc cho AI điền) số liệu, theo ĐÚNG bộ chỉ tiêu chuẩn
(statement_code + row_order + tên) — để khớp và gộp được với data FiinProX.

Khung chỉ tiêu lấy từ output\template_skeleton.csv (do run_pipeline.py tạo).

Tạo ra: manual_input\<Ngành>\<MÃ> [Q|Y].csv  (wide: cột chỉ tiêu + các kỳ trống để điền)
Tên file giữ NGUYÊN mã (cả mã có dấu cách như "Alpha Securities") để khớp master.

Dùng — 1 mã:
    python export_template.py --ticker VND --freq Q --nganh "Dịch vụ tài chính" --periods Q1/2026
Dùng — TẤT CẢ mã đang có trong master (đúng ngành của từng mã):
    python export_template.py --from-master --freq Q --periods Q1/2026
"""
import os
import csv
import argparse

HERE = os.path.dirname(os.path.abspath(__file__))
SKELETON = os.path.join(HERE, "output", "template_skeleton.csv")
MASTER = os.path.join(HERE, "output", "fiinprox_facts_all.csv")
MANUAL_DIR = os.path.join(HERE, "manual_input")
STMT_ORDER = ["BS", "IS", "CF", "NOTE", "CAR"]
csv.field_size_limit(10_000_000)


def fs_safe(s, fallback="X"):
    """Bỏ ký tự cấm Windows nhưng GIỮ dấu cách (khớp tên mã/ngành gốc)."""
    s = (s or "").strip() or fallback
    for ch in '\\/:*?"<>|':
        s = s.replace(ch, " ")
    return " ".join(s.split())


def load_skeleton():
    if not os.path.isfile(SKELETON):
        raise SystemExit("Chưa có template_skeleton.csv — chạy run_pipeline.py 1 lần trước.")
    with open(SKELETON, "r", encoding="utf-8-sig", newline="") as fh:
        skel = list(csv.DictReader(fh))
    skel.sort(key=lambda d: (STMT_ORDER.index(d["statement_code"])
                             if d["statement_code"] in STMT_ORDER else 9,
                             int(float(d["row_order"]))))
    return skel


def write_template(ticker, freq, nganh, periods, skel, overwrite=False):
    out_dir = os.path.join(MANUAL_DIR, fs_safe(nganh, "_KhongRoNganh"))
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{fs_safe(ticker)} [{freq}].csv")
    if os.path.isfile(out) and not overwrite:
        return out, False
    cols = ["statement_code", "row_order", "Chỉ tiêu"] + periods
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for d in skel:
            w.writerow([d["statement_code"], d["row_order"], d["metric"]] + [""] * len(periods))
    return out, True


def tickers_from_master(freq):
    """Tập (ticker, nganh_L2) đang có trong master với tần suất freq."""
    if not os.path.isfile(MASTER):
        raise SystemExit("Chưa có fiinprox_facts_all.csv — chạy run_pipeline.py trước.")
    seen = {}
    with open(MASTER, "r", encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["freq"] != freq:
                continue
            t = row["ticker"]
            if t not in seen:
                seen[t] = row.get("nganh_L2", "") or "_KhongRoNganh"
    return seen


def main():
    ap = argparse.ArgumentParser(description="Tạo mẫu nhập tay theo khung chỉ tiêu chuẩn.")
    ap.add_argument("--ticker", help="1 mã cụ thể")
    ap.add_argument("--from-master", action="store_true", help="Tạo cho TẤT CẢ mã trong master")
    ap.add_argument("--freq", required=True, choices=["Q", "Y"])
    ap.add_argument("--nganh", default="", help="Ngành (bắt buộc khi dùng --ticker)")
    ap.add_argument("--periods", required=True, help="Kỳ, phẩy ngăn (vd Q1/2026 hoặc 2024,2025)")
    ap.add_argument("--overwrite", action="store_true", help="Ghi đè file mẫu đã có")
    args = ap.parse_args()

    periods = [p.strip() for p in args.periods.split(",") if p.strip()]
    if not periods:
        raise SystemExit("Cần --periods (vd Q1/2026).")
    skel = load_skeleton()

    if args.from_master:
        tk = tickers_from_master(args.freq)
        made = skipped = 0
        locked = []
        for ticker, nganh in sorted(tk.items()):
            try:
                _, created = write_template(ticker, args.freq, nganh, periods, skel, args.overwrite)
                made += created
                skipped += (not created)
            except PermissionError:
                locked.append(ticker)
        print(f"Tạo {made} mẫu mới ({skipped} đã có, bỏ qua) | freq {args.freq} | kỳ {', '.join(periods)}")
        if locked:
            print(f"  ! {len(locked)} file đang MỞ (đóng Excel rồi chạy lại): {', '.join(locked)}")
        print(f"  -> {MANUAL_DIR}\\<Ngành>\\<MÃ> [{args.freq}].csv")
    else:
        if not args.ticker or not args.nganh:
            raise SystemExit("Dùng --ticker X --nganh '...'  hoặc  --from-master.")
        out, created = write_template(args.ticker, args.freq, args.nganh, periods, skel, args.overwrite)
        print(("Đã tạo: " if created else "Đã có (bỏ qua, dùng --overwrite để ghi đè): ") + out)
        print(f"  {len(skel)} chỉ tiêu | kỳ: {', '.join(periods)}")


if __name__ == "__main__":
    main()
