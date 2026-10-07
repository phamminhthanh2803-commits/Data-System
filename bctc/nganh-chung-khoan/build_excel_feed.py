# -*- coding: utf-8 -*-
r"""build_excel_feed.py — sinh CSV DẠNG RỘNG cho workbook IB&Brokerage_Genea_2Q26.xlsx (thay PivotTable 4,67 triệu dòng + GETPIVOTDATA).

Nguồn: fiinprox-unpivot\output\by_nganh_L2\Dịch_vụ_tài_chính.csv (đúng query `Dịch_vụ_tài_chính` của workbook, 20 trường).
Ngữ nghĩa tái tạo đúng pivot: SUM value theo (ticker | metric | row_order | năm | quý); quý null -> Q0; FY = tổng mọi dòng cùng năm (Q1..Q4 + Q0).
Đầu ra (excel_feed\):
  fs_all_wide.csv     key = "ALL|metric|row_order" (row_order = "ALL" cho tầng metric)      ~2.000 dòng × kỳ
  fs_ticker_wide.csv  key = "ticker|metric|row_order", ticker theo TICKER_SCOPE (list = tickers.txt | all)
  market_cap_daily.csv (bỏ 5 cột text), industry_valuation.csv  (từ fs-extractor\output_cap)
  manifest.json, validation_report.csv (nếu có validation_samples.csv)
Chạy:  python build_excel_feed.py [--scope list|all] [--validate excel_feed\validation_samples.csv]
Quy ước CSV: UTF-8 BOM, dấu phẩy, thập phân '.', không phân cách nghìn, ô thiếu để trống, số ghi %.12g.
"""
import argparse, json, os, sys
import datetime as dt
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "fiinprox-unpivot", "output", "by_nganh_L2", "Dịch_vụ_tài_chính.csv")
CAP_DIR = os.path.join(HERE, "..", "fs-extractor", "output_cap")
OUT = os.path.join(HERE, "excel_feed")
FMT = "%.12g"
ALIAS = {}           # nhan bien the -> nhan chuan (cung bao cao + row_order), dien khi load_source()
CASEFOLD = False     # True = bat chuoc loi gop hoa/thuong cua pivot (chi de doi chieu)

# 15 dòng mẫu trong đặc tả (GETPIVOTDATA hiện tại) — dùng kiểm định khi chưa có validation_samples.csv
SPEC_SAMPLES = """sheet,cell,ticker,metric,row_order,year,quarter,expected
BS,C8,,TÀI SẢN NGẮN HẠN,,2009,4,23951.422523152
BS,AN103,,Vay ngắn hạn,,2013,3,1374.890819432
BS,BK224,,"Phải trả cổ tức, gốc và lãi trái phiếu",,2019,2,1400.40098336
IS,E8,,DOANH THU HOẠT ĐỘNG,1,2009,,15802.268597586
IS,CD39,,Chi phí hoạt động tự doanh,32,2023,3,-177.952412428
IS,CK96,,Lãi trên cổ phiếu pha loãng (VND),,2025,2,1231
NOTE,X8,,CHỨNG KHOÁN LƯU KÝ NIÊM YẾT,1,2009,1,0
NOTE,BZ313,,Phải thu tổ chức phát hành chứng khoán,306,2022,3,0
NOTE,BW649,,Chi phí khác bằng tiền,642,2021,4,326.124506583
Peer Data,I7,TCX,Các tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL),6,2016,1,766.748421223
Peer Data,Y474,SHS,Lãi từ các tài sản tài chính sẵn sàng để bán,8,2020,1,0
Peer Data,AM1023,LPS,Công cụ thị trường tiền tệ,151,2023,3,0
Key ratios,I91,VCBS,Các tài sản tài chính ghi nhận thông qua lãi lỗ (FVTPL),6,2016,1,990.618071594
Key ratios,AH95,VCBS,TỔNG CỘNG TÀI SẢN,92,2022,2,8420.296789081
Key ratios,V163,,Trái phiếu,150,2019,2,1344.236931359
"""


def log(m):
    print(m, flush=True)


def period_cols(cols):
    """Sắp cột kỳ: năm tăng dần; trong năm Q0<Q1<..<Q4<FY."""
    def k(c):
        y, s = int(c[:4]), c[4:]
        return (y, 9 if s == "FY" else int(s[1]))
    return sorted(cols, key=k)


def load_source():
    log(f"Đọc {os.path.abspath(SRC)} ...")
    df = pd.read_csv(SRC, usecols=["ticker", "statement_code", "metric", "row_order", "year", "quarter", "value"], encoding="utf-8-sig",
                     dtype={"ticker": str, "metric": str, "row_order": str, "statement_code": str})
    df["ticker"] = df.ticker.str.strip()
    df["metric"] = df.metric.str.strip()
    ro = pd.to_numeric(df.row_order, errors="coerce")
    df["row_order"] = np.where(ro.notna(), ro.fillna(0).astype(int).astype(str), df.row_order.fillna("").str.strip())
    df["year"] = pd.to_numeric(df.year, errors="coerce").astype("Int64")
    df["q"] = pd.to_numeric(df.quarter, errors="coerce").fillna(0).astype(int)          # quý null -> Q0
    df["value"] = pd.to_numeric(df.value, errors="coerce")
    df = df.dropna(subset=["year", "value"])
    df["year"] = df.year.astype(int)
    # LUU Y: pivot Excel gop nhan KHONG phan biet hoa/thuong ("Tiền và tương đương tiền" BS + "TIỀN VÀ TƯƠNG ĐƯƠNG TIỀN" tieu de
    # thuyet minh = 1 item) -> sai so lieu. KHONG tai tao loi nay (CASEFOLD=False); giu nhan phan biet hoa/thuong.
    if CASEFOLD:
        canon = df.groupby(df.metric.str.lower()).metric.agg(lambda x: x.value_counts().index[0])
        df["metric"] = df.metric.str.lower().map(canon)
    # CUNG (bao cao, row_order) nhung nhan khac nhau giua mau quy / mau nam (IS 48 "Cộng doanh thu hoạt động tài chính" vs
    # "Doanh thu hoạt động tài chính", IS 56, IS 79) -> quy ve 1 nhan pho bien nhat; ALIAS giu nhan bien the de tra cuu van khop.
    # Khong lam vay thi Finance income/expense trong workbook = 0 vi sheet IS ghi nhan mau nam con du lieu quy nam duoi nhan "Cộng ...".
    ALIAS.clear()
    lab = df.drop_duplicates(["statement_code", "row_order", "metric"]).groupby(["statement_code", "row_order"]).metric.apply(list)
    for (sc, ro), labs in lab[lab.str.len() > 1].items():
        cnt = df[(df.statement_code == sc) & (df.row_order == ro)].metric.value_counts()
        can = cnt.index[0]
        for v in labs:
            if v != can:
                ALIAS[v] = can
    if ALIAS:
        df["metric"] = df.metric.map(lambda m: ALIAS.get(m, m))
        log(f"  gop nhan quy/nam cung dong: {ALIAS}")
    df = df.drop(columns=["statement_code"])
    log(f"  nhan metric: {df.metric.nunique()}" + (" (da gop hoa/thuong)" if CASEFOLD else ""))
    log(f"  {len(df):,} dòng có giá trị | {df.ticker.nunique()} mã | năm {df.year.min()}–{df.year.max()}")
    return df


FILL = "zero"


def all_period_codes(df):
    q = (df.year.astype(str) + "Q" + df.q.astype(str)).unique().tolist()
    fy = (df.year.astype(str) + "FY").unique().tolist()
    return period_cols(sorted(set(q) | set(fy)))


def widen(df, keys, all_periods=None):
    """SUM theo keys + kỳ (Qn và FY) -> bảng rộng, đủ mọi cột kỳ có trong nguồn; FILL=zero -> 0, blank -> trống."""
    q = df.groupby(keys + ["year", "q"]).value.sum(min_count=1).reset_index()
    q["per"] = q.year.astype(str) + "Q" + q.q.astype(str)
    fy = df.groupby(keys + ["year"]).value.sum(min_count=1).reset_index()
    fy["per"] = fy.year.astype(str) + "FY"
    long = pd.concat([q[keys + ["per", "value"]], fy[keys + ["per", "value"]]], ignore_index=True)
    w = long.pivot_table(index=keys, columns="per", values="value", aggfunc="first")
    w = w.reindex(columns=period_cols(all_periods)) if all_periods else w[period_cols(list(w.columns))]
    if FILL == "zero":
        w = w.fillna(0.0)      # pivot: item dòng/cột tồn tại nhưng giao điểm trống -> GETPIVOTDATA trả 0 (mẫu NOTE!X8)
    return w.reset_index()


def write_csv(df, path):
    df.to_csv(path, index=False, encoding="utf-8-sig", float_format=FMT, lineterminator="\n")


def build(scope, tickers_file):
    os.makedirs(OUT, exist_ok=True)
    df = load_source()
    # ---- fs_all_wide: tầng metric (row_order=ALL) + tầng metric×row_order, ticker=ALL
    P = all_period_codes(df)
    a1 = widen(df, ["metric"], P); a1.insert(1, "row_order", "ALL")
    a2 = widen(df, ["metric", "row_order"], P)
    fs_all = pd.concat([a1, a2], ignore_index=True)
    if ALIAS:
        extra = fs_all[fs_all.metric.isin(ALIAS.values())].copy(); extra["metric"] = extra.metric.map({v: k for k, v in ALIAS.items()}); fs_all = pd.concat([fs_all, extra], ignore_index=True)
    fs_all.insert(0, "key", "ALL|" + fs_all.metric + "|" + fs_all.row_order)
    pcols = period_cols([c for c in fs_all.columns if c[:4].isdigit()])
    fs_all = fs_all[["key", "metric", "row_order"] + pcols].sort_values(["metric", "row_order"], key=lambda s: s.map(lambda x: (x == "ALL", x)) if s.name == "row_order" else s).reset_index(drop=True)
    # ---- fs_ticker_wide
    if scope == "list":
        tk = [t.strip() for t in open(tickers_file, encoding="utf-8-sig") if t.strip()]
        sub = df[df.ticker.str.upper().isin([t.upper() for t in tk])]
        missing = sorted(set(t.upper() for t in tk) - set(sub.ticker.str.upper()))
        if missing:
            log(f"  ! mã trong tickers.txt không có trong nguồn: {missing}")
    else:
        tk = sorted(df.ticker.unique()); sub = df
    ft = widen(sub, ["ticker", "metric", "row_order"], P)
    if ALIAS:
        extra = ft[ft.metric.isin(ALIAS.values())].copy(); extra["metric"] = extra.metric.map({v: k for k, v in ALIAS.items()}); ft = pd.concat([ft, extra], ignore_index=True)
    ft.insert(0, "key", ft.ticker + "|" + ft.metric + "|" + ft.row_order)
    tcols = period_cols([c for c in ft.columns if c[:4].isdigit()])
    ft = ft[["key", "ticker", "metric", "row_order"] + tcols].sort_values(["ticker", "metric", "row_order"]).reset_index(drop=True)
    write_csv(fs_all, os.path.join(OUT, "fs_all_wide.csv")); write_csv(ft, os.path.join(OUT, "fs_ticker_wide.csv"))
    log(f"  fs_all_wide: {len(fs_all):,} dòng × {len(pcols)} kỳ | fs_ticker_wide ({scope}): {len(ft):,} dòng × {len(tcols)} kỳ, {ft.ticker.nunique()} mã")
    # ---- market cap / valuation (bỏ 5 cột text)
    counts = {"fs_all": len(fs_all), "fs_ticker": len(ft)}
    mc = os.path.join(CAP_DIR, "market_cap_daily.csv")
    if os.path.exists(mc):
        m = pd.read_csv(mc, encoding="utf-8-sig").drop(columns=["ten_cong_ty", "nganh_L1", "nganh_L2", "nganh_L3", "nganh_L4"], errors="ignore")
        write_csv(m, os.path.join(OUT, "market_cap_daily.csv")); counts["market_cap_daily"] = len(m)
    iv = os.path.join(CAP_DIR, "industry_valuation.csv")
    if os.path.exists(iv):
        v = pd.read_csv(iv, encoding="utf-8-sig"); write_csv(v, os.path.join(OUT, "industry_valuation.csv")); counts["industry_valuation"] = len(v)
    man = {"run_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "source": os.path.abspath(SRC), "n_rows_source": int(len(df)),
           "ticker_scope": scope, "tickers": list(tk), "periods": pcols, "row_counts": counts}
    json.dump(man, open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return df, fs_all, ft


CANON = {}


def validate(df, samples_path):
    """So GETPIVOTDATA (expected) với pipeline; expected trống = tổ hợp không được tồn tại."""
    CANON.update({m.lower(): m for m in df.metric.unique()})
    s = pd.read_csv(samples_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    s.columns = [c.strip() for c in s.columns]
    # chỉ mục tra nhanh trên nguồn
    g_t = df.groupby(["ticker", "metric", "row_order", "year", "q"]).value.sum(min_count=1)
    g_tfy = df.groupby(["ticker", "metric", "row_order", "year"]).value.sum(min_count=1)
    g_r = df.groupby(["metric", "row_order", "year", "q"]).value.sum(min_count=1)
    g_rfy = df.groupby(["metric", "row_order", "year"]).value.sum(min_count=1)
    g_m = df.groupby(["metric", "year", "q"]).value.sum(min_count=1)
    g_mfy = df.groupby(["metric", "year"]).value.sum(min_count=1)
    rows, bad = [], 0
    for r in s.itertuples(index=False):
        t, m, ro, y, q, exp = r.ticker.strip(), r.metric.strip(), r.row_order.strip(), int(float(r.year)), r.quarter.strip(), r.expected.strip()
        m = CANON.get(m.lower(), m) if CASEFOLD else ALIAS.get(m, m)
        ro = str(int(float(ro))) if ro else ""
        try:
            if t and q: got = g_t.get((t, m, ro, y, int(float(q))), np.nan)
            elif t: got = g_tfy.get((t, m, ro, y), np.nan)
            elif ro and q: got = g_r.get((m, ro, y, int(float(q))), np.nan)
            elif ro: got = g_rfy.get((m, ro, y), np.nan)
            elif q: got = g_m.get((m, y, int(float(q))), np.nan)
            else: got = g_mfy.get((m, y), np.nan)
        except Exception:
            got = np.nan
        if FILL == "zero" and pd.isna(got):     # item tồn tại (đâu đó) + cột kỳ tồn tại -> pivot cho 0
            if t:
                item_ok = (t, m, ro) in set(zip(*[g_t.index.get_level_values(i) for i in range(3)]))
            elif ro:
                item_ok = (m, ro) in set(zip(g_r.index.get_level_values(0), g_r.index.get_level_values(1)))
            else:
                item_ok = m in set(g_m.index.get_level_values(0))
            col_ok = ((y, int(float(q))) in set(zip(g_m.index.get_level_values(1), g_m.index.get_level_values(2)))) if q else (y in set(g_mfy.index.get_level_values(1)))
            got = 0.0 if (item_ok and col_ok) else np.nan
        if exp == "":
            ok = pd.isna(got)
        else:
            e = float(exp); ok = (not pd.isna(got)) and abs(got - e) <= 1e-6 * max(1.0, abs(e))
        bad += (not ok)
        rows.append({**r._asdict(), "pipeline": "" if pd.isna(got) else FMT % got, "ok": ok})
    rep = pd.DataFrame(rows); rep.to_csv(os.path.join(OUT, "validation_report.csv"), index=False, encoding="utf-8-sig")
    log(f"  kiểm định {len(rep)} mẫu: {len(rep) - bad} khớp, {bad} lệch -> excel_feed\\validation_report.csv")
    if bad:
        pd.set_option("display.width", 220); log(rep[~rep.ok].head(20).to_string(index=False))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="list", choices=["list", "all"])
    ap.add_argument("--tickers", default=os.path.join(OUT, "tickers.txt"))
    ap.add_argument("--validate", default=None, help="validation_samples.csv (xuất từ sheet _Validation_Samples)")
    ap.add_argument("--casefold", action="store_true", help="bat chuoc pivot gop nhan hoa/thuong (chi de doi chieu, KHONG khuyen nghi)")
    ap.add_argument("--fill", default="zero", choices=["zero", "blank"], help="ô không có dòng nguồn: 0 (giống GETPIVOTDATA) hay trống")
    ap.add_argument("--copy-to", default="",
                    help="thư mục chép CSV (mặc định KHÔNG chép: file giao duy nhất là IB&Brokerage_Nganh.xlsx do build_presentation.py chép)")
    a = ap.parse_args()
    global FILL, CASEFOLD
    FILL = a.fill; CASEFOLD = a.casefold
    df, _, _ = build(a.scope, a.tickers)
    vp = a.validate or os.path.join(OUT, "validation_samples.csv")
    if not os.path.exists(vp):
        vp = os.path.join(OUT, "validation_samples_spec.csv"); open(vp, "w", encoding="utf-8-sig", newline="").write(SPEC_SAMPLES)
        log("  (chưa có validation_samples.csv từ workbook -> kiểm định 15 mẫu trong đặc tả)")
    validate(df, vp)
    if a.copy_to:
        import shutil
        os.makedirs(a.copy_to, exist_ok=True)
        for fn in ["fs_all_wide.csv", "fs_ticker_wide.csv", "market_cap_daily.csv", "industry_valuation.csv", "manifest.json"]:
            if os.path.exists(os.path.join(OUT, fn)):
                shutil.copy(os.path.join(OUT, fn), os.path.join(a.copy_to, fn))
        log(f"  đã chép CSV sang {a.copy_to}")
    log(f"-> {OUT}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
