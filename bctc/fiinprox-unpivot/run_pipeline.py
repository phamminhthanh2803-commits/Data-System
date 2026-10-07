# -*- coding: utf-8 -*-
r"""
run_pipeline.py
---------------
PIPELINE 1-PHÁT cho FiinProX: quét thư mục -> unpivot -> phân ngành -> gộp BCTC ngành.
Tự động khi thêm/đổi file: chỉ parse file MỚI hoặc ĐÃ SỬA (cache theo mtime+size),
file cũ đọc lại từ cache nên rất nhanh.

Cấu hình bằng config.csv (cạnh script), mỗi dòng 1 thư mục ngành:
    folder,default_nganh
    D:\Database\Chứng khoán,Dịch vụ tài chính
    D:\Database\Ngân hàng,Ngân hàng
(default_nganh = ngành gán cho mã KHÔNG tra được trong bảng ICB niêm yết.)

Chạy:
    python run_pipeline.py                 # rebuild theo config.csv
    python run_pipeline.py --refresh-icb   # kéo lại bảng ngành ICB mới
    python run_pipeline.py --no-cache      # parse lại toàn bộ (bỏ cache)

Đầu ra output\:
    fiinprox_facts_all.csv                 master long (mọi ngành)
    by_nganh_L2\<Ngành>.csv                tách theo ngành
    industry\<Ngành>\industry_FS_Q.xlsx    BCTC gộp toàn ngành (+ _Y.xlsx, _long.csv)
"""
import os
import re
import csv
import glob
import hashlib
import argparse
import datetime as dt

import unpivot_fiinprox as U
import aggregate_industry as A
import import_manual as M

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "output")
CACHE_DIR = os.path.join(OUTDIR, ".cache")
CONFIG = os.path.join(HERE, "config.csv")
RAW_COLS = [c for c in U.FACT_COLS if c not in U.ICB_COLS]  # facts trước khi gắn ngành
csv.field_size_limit(10_000_000)


def ensure_config():
    if not os.path.isfile(CONFIG):
        with open(CONFIG, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["folder", "default_nganh"])
            w.writerow([r"D:\Database\Chứng khoán", "Dịch vụ tài chính"])
        print(f"  (tạo mẫu {os.path.basename(CONFIG)} — sửa lại đường dẫn/ngành nếu cần)")


def read_config():
    rows = []
    with open(CONFIG, "r", encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            folder = (r.get("folder") or "").strip()
            if folder:
                rows.append((folder, (r.get("default_nganh") or "").strip()))
    return rows


def _fid(xlsx):
    """Hash ỔN ĐỊNH theo đường dẫn (hash() của Python bị salt mỗi tiến trình)."""
    return hashlib.md5(os.path.abspath(xlsx).lower().encode("utf-8")).hexdigest()[:12]


def cache_path(xlsx):
    st = os.stat(xlsx)
    tag = f"{_fid(xlsx)}_{int(st.st_mtime)}_{st.st_size}"
    return os.path.join(CACHE_DIR, tag + ".csv")


_FPAT = re.compile(r"(Quarterly|Yearly).*?Hop_nhat_(.+?)_(\d{6,8})\.xlsx$", re.IGNORECASE)


def latest_files(folder):
    """Danh sách file FiinProX trong folder, CHỈ GIỮ BẢN MỚI NHẤT cho mỗi (tần suất, mã).

    FiinProX xuất bản mới (dấu ngày mới) chứa TRỌN lịch sử -> bản cũ bị thay thế
    hoàn toàn, nếu đọc cả hai thì mã đó bị đếm ĐÔI. Trả về (files, superseded).
    """
    all_files = [f for f in sorted(glob.glob(os.path.join(folder, "FiinProX_*.xlsx")))
                 if not os.path.basename(f).startswith("~$")]
    best, extra = {}, []
    for f in all_files:
        m = _FPAT.search(os.path.basename(f))
        if not m:
            extra.append(f)  # không parse được tên -> cứ lấy
            continue
        key = (m.group(1).lower(), m.group(2).strip().lower())
        date = m.group(3)
        cur = best.get(key)
        if cur is None or date > cur[0]:
            best[key] = (date, f)
    files = sorted([f for _, f in best.values()] + extra)
    superseded = len(all_files) - len(files)
    return files, superseded


def prune_superseded(folder):
    """XOÁ hẳn các bản cũ bị thay thế (file + cache). Trả về danh sách đã xoá."""
    keep, _ = latest_files(folder)
    keepset = {os.path.abspath(f) for f in keep}
    removed = []
    for f in sorted(glob.glob(os.path.join(folder, "FiinProX_*.xlsx"))):
        if os.path.basename(f).startswith("~$") or os.path.abspath(f) in keepset:
            continue
        try:
            cp = cache_path(f)
            if os.path.isfile(cp):
                os.remove(cp)
            os.remove(f)
            removed.append(os.path.basename(f))
        except PermissionError:
            print("  ! file đang mở, chưa xoá được:", os.path.basename(f))
    return removed


def apply_fixes(all_facts):
    """Áp bảng sửa lỗi nguồn fixes.csv (ticker,freq,sc,row_order,period -> giá trị đúng).

    Chỉ sửa khi giá trị hiện tại KHỚP gia_tri_sai (an toàn nếu FiinProX tự sửa nguồn);
    gia_tri_sai trống = luôn ép. Trả về số ô đã sửa."""
    fp = os.path.join(HERE, "fixes.csv")
    if not os.path.isfile(fp):
        return 0
    idx = {}
    with open(fp, "r", encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            t = (r.get("ticker") or "").strip()
            if not t or t.startswith("#"):
                continue
            key = (t, r["freq"].strip(), r["statement_code"].strip(),
                   str(U._int(r["row_order"])), r["period"].strip())
            idx[key] = r
    if not idx:
        return 0
    n = 0
    for f in all_facts:
        key = (f["ticker"], f["freq"], f["statement_code"],
               str(U._int(f["row_order"])), f["period"])
        fx = idx.get(key)
        if not fx:
            continue
        try:
            cur = float(f["value"])
            dung = float(fx["gia_tri_dung"])
        except (ValueError, TypeError):
            continue
        sai_raw = (fx.get("gia_tri_sai") or "").strip()
        if sai_raw:
            try:
                sai = float(sai_raw)
            except ValueError:
                continue
            if abs(cur - sai) > max(abs(sai) * 1e-6, 1e-9):
                continue  # giá trị hiện tại không phải số sai đã biết -> không đụng
        if cur != dung:
            f["value"] = dung
            n += 1
            print(f"    fix: {f['ticker']} {f['statement_code']} ro{f['row_order']} "
                  f"{f['period']}: {cur:,.2f} -> {dung:,.2f}")
    return n


def detect_renames(all_facts, ticker_date):
    """Phát hiện mã ĐỔI TÊN: 2 ticker có chuỗi DT hoạt động (IS ro1, quý) TRÙNG HỆT
    trên các kỳ chung -> cùng 1 công ty. Giữ tên có file MỚI hơn (nhiều kỳ hơn nếu hoà).

    Trả về list (ten_cu, ten_moi)."""
    sigs = {}
    for f in all_facts:
        if f["freq"] == "Q" and f["statement_code"] == "IS" and str(f["row_order"]) == "1":
            try:
                sigs.setdefault(f["ticker"], {})[f["period"]] = float(f["value"])
            except (ValueError, TypeError):
                pass
    tickers = sorted(sigs)
    renames = []
    for i, a in enumerate(tickers):
        for b in tickers[i + 1:]:
            common = set(sigs[a]) & set(sigs[b])
            if len(common) < 8:
                continue
            if not all(abs(sigs[a][p] - sigs[b][p]) < 0.01 for p in common):
                continue
            if not any(abs(sigs[a][p]) > 0.01 for p in common):
                continue  # toàn 0 thì không đủ bằng chứng
            da, db = ticker_date.get(a, ""), ticker_date.get(b, "")
            old, new = (a, b) if (db, len(sigs[b])) > (da, len(sigs[a])) else (b, a)
            renames.append((old, new))
    return renames


def _pkey(p):
    """'Q2/2026' -> (2026, 2) để so thứ tự kỳ."""
    m = re.match(r"Q([1-4])/(\d{4})", p or "")
    return (int(m.group(2)), int(m.group(1))) if m else (0, 0)


def detect_unit_errors(all_facts, out_csv, lo=500.0, hi=5000.0, flag=30.0, min_abs=100.0):
    r"""LỖI ĐƠN VỊ NGUỒN FiinProX (thêm 15/09/2026, vụ JB Securities Q1/2025: trái phiếu FVTPL 429.780 tỷ thay vì 429,78).

    Với mỗi (ticker, freq, statement, row_order) xét từng kỳ có ĐỦ 2 kỳ liền kề (trước và sau): r = |v| / trung vị(|trước|, |sau|).
    - lo <= r <= hi và |v| >= min_abs  -> coi là nhân nhầm 1.000 -> TỰ SỬA v/1000 (ghi action=auto_/1000)
      (dải 500..5000; hoặc >=100 lần kèm giá trị tuyệt đối phi lý — xem chú thích trong hàm; 100..500 lần với giá trị bình thường chỉ review)
    - r >= flag (không thuộc dải trên)  -> chỉ CẢNH BÁO (action=review), không sửa
    Ghi output\_loi_don_vi.csv để soát; các ô tự sửa được áp trực tiếp vào all_facts (mỗi lần chạy đều lặp lại, không cần fixes.csv)."""
    import statistics
    by = {}
    for i, f in enumerate(all_facts):
        try:
            v = float(f["value"])
        except (TypeError, ValueError):
            continue
        y = U._int(f.get("year")); q = U._int(f.get("quarter"))
        t = y * 4 + q if f["freq"] == "Q" else y
        by.setdefault((f["ticker"], f["freq"], f["statement_code"], str(U._int(f["row_order"]))), []).append((t, v, i))
    rows, n_fix = [], 0
    for key, lst in by.items():
        lst.sort()
        tt = {t: (v, i) for t, v, i in lst}
        for t, v, i in lst:
            if abs(v) < min_abs or (t - 1) not in tt or (t + 1) not in tt:
                continue
            nb = statistics.median([abs(tt[t - 1][0]), abs(tt[t + 1][0])])
            if nb <= 0:
                continue
            r = abs(v) / nb
            if r < flag:
                continue
            f = all_facts[i]
            # Tu sua chi khi gan nhu chac chan nhan nham 1.000:
            #  (a) ty le 500..5000 (x1000 voi lan can dao dong x2 len / x5 xuong), hoac
            #  (b) ty le >= 100 va gia tri tuyet doi phi ly: >= 100.000 ty voi dong so du/luong thong thuong (khong CTCK nao co),
            #      >= 5.000.000 ty voi dong GTGD/KLGD trong ky (NOTE 96-111; ca thi truong 1 quy chi ~2-3 trieu ty).
            #  Con lai (30..500 lan, gia tri binh thuong) -> review: co the la vi the that (vd SHS lo FVTPL -740 ty Q4/2025 khi lai 1.230).
            trading = key[2] == "NOTE" and 96 <= U._int(key[3]) <= 111
            big = abs(v) >= (5_000_000 if trading else 100_000)
            act = "auto_/1000" if ((lo <= r <= hi) or (r >= 100 and big)) else "review"
            rows.append({"ticker": f["ticker"], "freq": f["freq"], "statement_code": f["statement_code"], "row_order": f["row_order"],
                         "metric": f["metric"], "period": f["period"], "gia_tri": v, "lan_can": round(nb, 4), "ty_le": round(r, 1),
                         "action": act, "gia_tri_moi": v / 1000 if act == "auto_/1000" else ""})
            if act == "auto_/1000":
                f["value"] = v / 1000; n_fix += 1
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "freq", "statement_code", "row_order", "metric", "period", "gia_tri", "lan_can", "ty_le", "action", "gia_tri_moi"])
        w.writeheader(); w.writerows(sorted(rows, key=lambda r: (-abs(r["gia_tri"]))))
    return rows, n_fix


def check_completeness(all_facts, ticker_date, ticker_files, min_ratio=0.9, grace_days=60):
    """KIỂM TRA KỲ MỚI NHẤT CÓ ĐỦ KHÔNG (thêm 14/09/2026, sau vụ VCBS).

    Nguyên nhân gốc: file FiinProX xuất tay ngay sau mùa BCTC (vd 21/07 cho quý 2) thì BS/IS/CF
    đã có nhưng THUYẾT MINH và phần ngoài bảng CĐKT chưa được FiinProX nạp -> kỳ mới nhất
    vào master với NOTE = 0 dòng, BS thiếu ~45 dòng, mà không ai biết. Hàm này so số chỉ tiêu
    có giá trị ở kỳ quý mới nhất với kỳ ngay trước của CÙNG công ty; thiếu > (1-min_ratio)
    hoặc NOTE trống trong khi BS có số -> ghi vào output\\_can_xuat_lai.csv để xuất lại file.
    Ngoài ra cảnh báo 'xuất sớm' khi ngày xuất < cuối quý + grace_days (chưa chắc đã đủ).
    Trả về list dict (mỗi dòng 1 công ty cần xuất lại)."""
    cnt = {}   # (ticker, stmt, period) -> số ô có giá trị (chỉ freq Q)
    for f in all_facts:
        if f.get("freq") != "Q":
            continue
        v = f.get("value")
        if v in ("", None):
            continue
        k = (f["ticker"], f["statement_code"], f["period"])
        cnt[k] = cnt.get(k, 0) + 1
    by_t = {}
    for (t, sc, p), n in cnt.items():
        by_t.setdefault(t, {}).setdefault(p, {})[sc] = n
    out = []
    for t, per in by_t.items():
        pers = sorted(per, key=_pkey)
        if len(pers) < 2:
            continue
        last, prev = pers[-1], pers[-2]
        probs = []
        for sc in ("BS", "IS", "CF", "NOTE"):
            a, b = per[last].get(sc, 0), per[prev].get(sc, 0)
            if b and a < min_ratio * b:
                probs.append(f"{sc} {a}/{b}")
        y, q = _pkey(last)
        qend = dt.date(y, 12, 31) if q == 4 else dt.date(y, 3 * q + 1, 1) - dt.timedelta(days=1)
        d = ticker_date.get(t, "")
        try:
            dexp = dt.datetime.strptime(d, "%Y%m%d").date()
        except ValueError:
            dexp = None
        early = dexp is not None and (dexp - qend).days < grace_days
        if probs or (early and "NOTE" not in per[last]):
            files = [os.path.basename(x) for x in ticker_files.get(t, []) if "Quarterly" in x] or \
                    [os.path.basename(x) for x in ticker_files.get(t, [])]
            out.append({"ticker": t, "ky_moi_nhat": last, "ky_truoc": prev,
                        "thieu": "; ".join(probs) or "NOTE chưa có",
                        "ngay_xuat": d, "xuat_som": "x" if early else "",
                        "file": files[0] if files else ""})
    return sorted(out, key=lambda r: r["ticker"])


def load_or_parse(xlsx, use_cache):
    """Trả về list facts THÔ (chưa gắn ngành). Dùng cache nếu file không đổi."""
    cp = cache_path(xlsx)
    if use_cache and os.path.isfile(cp):
        with open(cp, "r", encoding="utf-8-sig", newline="") as fh:
            return list(csv.DictReader(fh)), True
    facts, _ = U.process_file(xlsx)
    # dọn cache cũ của chính file này (mtime/size khác) rồi ghi mới
    if use_cache:
        os.makedirs(CACHE_DIR, exist_ok=True)
        base = f"{_fid(xlsx)}_"
        for old in glob.glob(os.path.join(CACHE_DIR, base + "*.csv")):
            try:
                os.remove(old)
            except OSError:
                pass
        with open(cp, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=RAW_COLS)
            w.writeheader()
            w.writerows(facts)
    return facts, False


def main():
    ap = argparse.ArgumentParser(description="Pipeline 1-phát FiinProX.")
    ap.add_argument("--refresh-icb", action="store_true")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--level", default="L2", choices=["L1", "L2", "L3", "L4"])
    args = ap.parse_args()

    ensure_config()
    cfg = read_config()
    if not cfg:
        raise SystemExit("config.csv rỗng. Thêm dòng: folder,default_nganh")
    os.makedirs(OUTDIR, exist_ok=True)

    icb_map = U.load_icb_map(OUTDIR, refresh=args.refresh_icb)
    use_cache = not args.no_cache

    all_facts = []
    n_parsed = n_cached = 0
    ticker_date, ticker_files = {}, {}
    for folder, default_nganh in cfg:
        removed = prune_superseded(folder)  # xoá hẳn bản cũ bị thay thế (file + cache)
        files, _ = latest_files(folder)
        note = f" | đã xoá {len(removed)} bản cũ thừa" if removed else ""
        print(f"[{os.path.basename(folder)}] {len(files)} file{note} | ngành mặc định: {default_nganh or '(không)'}")
        for name in removed:
            print("    - xoá:", name)
        for f in files:
            facts, hit = load_or_parse(f, use_cache)
            # ép kiểu lại các cột số khi đọc từ cache (csv -> str)
            U.enrich_industry(facts, icb_map, default_nganh=default_nganh)
            all_facts.extend(facts)
            n_cached += hit
            n_parsed += (not hit)
            if facts:
                t = facts[0]["ticker"]
                m = _FPAT.search(os.path.basename(f))
                d = m.group(3) if m else "0"
                ticker_date[t] = max(ticker_date.get(t, ""), d)
                ticker_files.setdefault(t, []).append(f)
    print(f"  -> {len(all_facts):,} facts ({n_parsed} parse mới, {n_cached} từ cache)")

    # phát hiện mã ĐỔI TÊN (2 ticker trùng hệt data kỳ chung) -> bỏ tên cũ, xoá file cũ
    renames = detect_renames(all_facts, ticker_date)
    for old, new in renames:
        print(f"  ! ĐỔI TÊN phát hiện: '{old}' -> '{new}' (data trùng hệt) — loại bỏ '{old}'")
        all_facts = [f for f in all_facts if f["ticker"] != old]
        for fp in ticker_files.get(old, []):
            try:
                cp = cache_path(fp)
                if os.path.isfile(cp):
                    os.remove(cp)
                os.remove(fp)
                print("    - xoá file:", os.path.basename(fp))
            except (PermissionError, FileNotFoundError):
                print("    ! chưa xoá được (đang mở?):", os.path.basename(fp))

    # áp bảng sửa lỗi nguồn (fixes.csv) — file mới xuất lại mang số sai vẫn bị đè về số đúng
    n_fix = apply_fixes(all_facts)
    if n_fix:
        print(f"  + fixes.csv: đã sửa {n_fix} ô lỗi nguồn")

    # lỗi đơn vị nguồn (nhân nhầm 1.000): tự sửa các ô rõ ràng, còn lại liệt kê để soát
    ue_rows, ue_fix = detect_unit_errors(all_facts, os.path.join(OUTDIR, "_loi_don_vi.csv"))
    n_rev = sum(1 for r in ue_rows if r["action"] == "review")
    print(f"  ! lỗi đơn vị nguồn: tự sửa /1000 {ue_fix} ô, cần soát {n_rev} ô -> output\\_loi_don_vi.csv")

    # kiểm tra kỳ quý mới nhất có đủ không (thuyết minh/ngoài bảng vào FiinProX muộn hơn BS/IS/CF)
    incomplete = check_completeness(all_facts, ticker_date, ticker_files)
    chk_path = os.path.join(OUTDIR, "_can_xuat_lai.csv")
    with open(chk_path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["ticker", "ky_moi_nhat", "ky_truoc", "thieu", "ngay_xuat", "xuat_som", "file"])
        w.writeheader()
        w.writerows(incomplete)
    if incomplete:
        print(f"\n  !!! {len(incomplete)} công ty có KỲ MỚI NHẤT CHƯA ĐỦ (file FiinProX xuất sớm) -> xuất lại rồi chạy lại:")
        for r in incomplete:
            print(f"      {r['ticker']:18} {r['ky_moi_nhat']}: {r['thieu']}  (xuất {r['ngay_xuat']})")
        print(f"      danh sách: {chk_path}\n")
    else:
        print("  ✓ kỳ mới nhất của mọi công ty đủ so với kỳ trước")

    # khung chỉ tiêu chuẩn (cho nhập tay) — (statement_code,row_order) -> (cha, tên)
    skel = {}
    for f in all_facts:
        k = (f["statement_code"], U._int(f["row_order"]))
        skel.setdefault(k, (f.get("parent", ""), f["metric"]))
    with open(os.path.join(OUTDIR, "template_skeleton.csv"), "w",
              encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["statement_code", "row_order", "parent", "metric"])
        for (sc, ro), (parent, metric) in sorted(
                skel.items(), key=lambda kv: (U.STMT_RANK.get(kv[0][0], 9), kv[0][1])):
            w.writerow([sc, ro, parent, metric])

    # nạp dữ liệu nhập tay/AI; manual GHI ĐÈ khi trùng (ticker,freq,statement,row_order,period)
    manual, n_manual = M.load_manual(icb_map)
    if manual:
        def k5(f):
            return (f["ticker"], f["freq"], f["statement_code"],
                    str(U._int(f["row_order"])), f["period"])
        mkeys = {k5(f) for f in manual}
        all_facts = [f for f in all_facts if k5(f) not in mkeys] + manual
        print(f"  + nhập tay: {len(manual):,} facts từ {n_manual} file (ghi đè khi trùng)")

    # sắp xếp giống báo cáo gốc (mã -> tần suất -> báo cáo -> dòng -> kỳ theo thời gian)
    U.sort_facts(all_facts)

    # master + tách ngành
    U.write_csv(os.path.join(OUTDIR, "fiinprox_facts_all.csv"), U.FACT_COLS, all_facts)
    col = "nganh_" + args.level
    sect_dir = os.path.join(OUTDIR, "by_nganh_" + args.level)
    os.makedirs(sect_dir, exist_ok=True)
    groups = {}
    for fct in all_facts:
        groups.setdefault(fct.get(col) or U.UNCLASSIFIED, []).append(fct)
    for name, rows in groups.items():
        U.write_csv(os.path.join(sect_dir, U.safe_name(name) + ".csv"), U.FACT_COLS, rows)
    print(f"  phân ngành ({args.level}): {len(groups)} ngành")

    # gộp BCTC từng ngành — gộp THẲNG từ RAM (không đọc lại master 1GB)
    for name in sorted(groups):
        if name == U.UNCLASSIFIED:
            continue  # không gộp nhóm chưa rõ ngành
        agg, n_rows, n_tickers = A.aggregate_rows(groups[name])
        rows = A.to_long_rows(agg)
        ind_dir = os.path.join(OUTDIR, "industry", U.safe_name(name))
        os.makedirs(ind_dir, exist_ok=True)
        with open(os.path.join(ind_dir, "industry_fs_long.csv"), "w",
                  encoding="utf-8-sig", newline="") as fh:
            cols = ["freq", "statement_code", "statement_name", "row_order", "parent", "metric",
                    "period", "year", "quarter", "n_cong_ty", "tong_gia_tri"]
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        for fq in ("Q", "Y"):
            A.write_wide_csv(rows, fq, ind_dir)
        print(f"    + {name}: {n_tickers} mã -> industry\\{U.safe_name(name)}\\")

    # folder NGÀNH CHỨNG KHOÁN: chỉ tiêu chuẩn + tỷ lệ + SQLite + pivot (thêm 14/09/2026)
    ck = os.path.join(os.path.dirname(HERE), "nganh-chung-khoan", "build_nganh_ck.py")
    if os.path.exists(ck):
        import subprocess
        import sys as _sys
        print("\n[nganh-chung-khoan] build_nganh_ck.py ...")
        r = subprocess.run([_sys.executable, ck], env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        print("  ->", "OK" if r.returncode == 0 else f"LOI exit {r.returncode}")
        # feed CSV cho workbook IB&Brokerage (nhanh, ~1 phút); rồi build_workbook_logic.py dựng lại file ngành (BCTC_NO_WORKBOOK=1 để bỏ qua)
        val = os.path.join(os.path.dirname(ck), "build_valuation_ck.py")      # dinh gia nganh theo ngay + LNST nganh theo quy
        if os.path.exists(val):
            print("[nganh-chung-khoan] build_valuation_ck.py ...")
            r = subprocess.run([_sys.executable, val], env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            print("  ->", "OK" if r.returncode == 0 else f"LOI exit {r.returncode}")
        feed = os.path.join(os.path.dirname(ck), "build_excel_feed.py")
        if os.path.exists(feed):
            print("[nganh-chung-khoan] build_excel_feed.py --scope list ...")
            r = subprocess.run([_sys.executable, feed, "--scope", "list"], env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            print("  ->", "OK" if r.returncode == 0 else f"LOI exit {r.returncode}")
        dfs = os.path.join(os.path.dirname(ck), "build_data_fs.py")           # 2 sheet DATA trung gian (toan bo item 3FS 87 ma + danh muc ma)
        if os.path.exists(dfs):
            print("[nganh-chung-khoan] build_data_fs.py ...")
            r = subprocess.run([_sys.executable, dfs], env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            print("  ->", "OK" if r.returncode == 0 else f"LOI exit {r.returncode}")
        logic = os.path.join(os.path.dirname(ck), "build_workbook_logic.py")   # dung lai FULL file nganh IB&Brokerage_Nganh.xlsx (~6 phut, can workbook goc + Excel)
        if os.path.exists(logic) and not os.environ.get("BCTC_NO_WORKBOOK"):
            print("[nganh-chung-khoan] build_workbook_logic.py --no-loop -> build_presentation.py (file nganh) ...")
            r = subprocess.run([_sys.executable, logic, "--no-loop"], env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            print("  ->", "OK" if r.returncode == 0 else f"LOI exit {r.returncode}")

    print(f"\nXong @ {dt.datetime.now():%Y-%m-%d %H:%M:%S}  | out: {OUTDIR}")


if __name__ == "__main__":
    main()
