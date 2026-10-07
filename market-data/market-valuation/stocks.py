# -*- coding: utf-8 -*-
r"""
STOCK VALUATION — Định giá TỪNG MÃ riêng lẻ do VNDirect tính sẵn (group STOCK)
6 chỉ tiêu theo NGÀY: P/E, P/B, P/S, Tỷ suất cổ tức, Vốn hóa (từ 12/2017)
+ BVPS (từ 12/2022). Suy ra: LN TTM, VCSH, doanh thu TTM, cổ tức TTM, EPS, giá.

Chạy:
    python stocks.py VNM FPT MWG HPG        # kéo các mã chỉ định (incremental)
    python stocks.py --file tickers.txt     # đọc danh sách mã từ file (mỗi dòng 1 mã)
    python stocks.py VNM --full             # kéo lại full lịch sử

Output:
    stocks-master.csv  long-format: code, date, ratio, value (cache incremental,
                       mã mới tự kéo full, mã cũ chỉ kéo ngày mới)
    stocks-wide.csv    wide theo (code, date) + các cột suy ra

Lưu ý: mã THUA LỖ TTM bị VNDirect ẩn P/E -> ln_ttm/eps trống ngày đó (P/B vẫn có).
"""
import argparse
import os
import sys
import time

import pandas as pd

from fetch_valuation import fetch_pair, BASE_DIR
from adjust import load_fs_fallback   # LNST TTM (VCI) cho ma lo, VNDirect an P/E

MASTER_CSV = os.path.join(BASE_DIR, "stocks-master.csv")
WIDE_CSV = os.path.join(BASE_DIR, "stocks-wide.csv")

RATIOS = {
    "PRICE_TO_EARNINGS": "pe",
    "PRICE_TO_BOOK": "pb",
    "PRICE_TO_SALES": "ps",
    "DIVIDEND_YIELD": "div_yield",
    "MARKETCAP": "marketcap",
    "BVPS_CR": "bvps",
}
CHUNK = 20  # so ma gop trong 1 request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="Cac ma can keo, vd: VNM FPT MWG")
    ap.add_argument("--file", help="File danh sach ma (moi dong 1 ma)")
    ap.add_argument("--full", action="store_true", help="Keo lai full lich su")
    args = ap.parse_args()

    tickers = [t.upper() for t in args.tickers]
    if args.file:
        with open(args.file, encoding="utf-8-sig") as f:
            tickers += [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]
    tickers = list(dict.fromkeys(tickers))
    if not tickers:
        sys.exit("Chua co ma nao — truyen ma hoac --file tickers.txt")

    old = pd.DataFrame(columns=["code", "date", "ratio", "value"])
    if os.path.exists(MASTER_CSV) and not args.full:
        old = pd.read_csv(MASTER_CSV)
        print(f"Master hien co {len(old)} dong, {old['code'].nunique()} ma")

    new_rows = []
    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i:i + CHUNK]
        for ratio_code in RATIOS:
            from_date = None
            if not old.empty:
                sub = old[(old["code"].isin(chunk)) & (old["ratio"] == ratio_code)]
                # chi incremental khi TAT CA ma trong chunk da co cache; co ma moi -> keo full
                if not sub.empty and sub["code"].nunique() == len(chunk):
                    from_date = sub.groupby("code")["date"].max().min()
            got = fetch_pair(",".join(chunk), ratio_code, from_date)
            print(f"  [{chunk[0]}..{chunk[-1]}] {ratio_code:20s} +{len(got)} dong "
                  f"(tu {from_date or 'dau lich su'})")
            new_rows.extend(got)
            time.sleep(0.6)

    frames = [df for df in (old, pd.DataFrame(new_rows)) if not df.empty]
    master = pd.concat(frames, ignore_index=True)
    master = master.drop_duplicates(subset=["code", "date", "ratio"], keep="last")
    master = master.sort_values(["code", "ratio", "date"])
    master.to_csv(MASTER_CSV, index=False, encoding="utf-8-sig")
    print(f"\n-> {MASTER_CSV}: {len(master)} dong, {master['code'].nunique()} ma")

    wide = master.pivot_table(index=["code", "date"], columns="ratio", values="value").reset_index()
    wide.columns.name = None
    wide = wide.rename(columns=RATIOS)
    for col in RATIOS.values():
        if col not in wide.columns:
            wide[col] = pd.NA
    wide["ln_ttm"] = wide["marketcap"] / wide["pe"]
    wide["vcsh"] = wide["marketcap"] / wide["pb"]
    wide["doanh_thu_ttm"] = wide["marketcap"] / wide["ps"]
    wide["co_tuc_ttm"] = wide["div_yield"] * wide["marketcap"]
    wide["roe_ttm"] = wide["pb"] / wide["pe"]    # ROE TTM ma = pb/pe (thap phan)
    wide["gia"] = wide["bvps"] * wide["pb"]      # gia dong cua suy nguoc (tu 12/2022)
    wide["eps"] = wide["gia"] / wide["pe"]       # EPS TTM (tu 12/2022)

    # FALLBACK cho ma LO TTM: VNDirect an P/E -> roe_ttm (=pb/pe) trong. Lay LNST TTM tu
    # FS Extractor (VCI) lam TU SO, VCSH = marketcap/pb cua VNDirect lam MAU SO (giu cung
    # co so VCSH voi ma co lai) -> roe_ttm AM dung ban chat. Chi lap duoc cho ma da co
    # trong FS Extractor (D:\bctc\fs-extractor\output_cap*). roe_src danh dau nguon.
    # (vcsh = marketcap/pb da tinh o tren)
    wide["roe_src"] = wide["roe_ttm"].notna().map({True: "vndirect", False: ""})
    fs = load_fs_fallback(list(wide["code"].unique()))
    if not fs.empty:
        wide = wide.merge(fs, on=["code", "date"], how="left")
        fill = wide["roe_ttm"].isna() & wide["vcsh"].notna() & wide["earn_vci"].notna()
        wide.loc[fill, "roe_ttm"] = wide.loc[fill, "earn_vci"] / wide.loc[fill, "vcsh"]
        wide.loc[fill, "roe_src"] = "fs_vci"
        wide = wide.drop(columns=["earn_vci"])
        n = int(fill.sum())
        if n:
            print(f"  [i] roe_ttm fallback FS/VCI cho {n} dong (ma lo, VNDirect thieu P/E)")
    wide = wide.sort_values(["code", "date"])
    wide.to_csv(WIDE_CSV, index=False, encoding="utf-8-sig")
    print(f"-> {WIDE_CSV}: {len(wide)} dong ({wide['date'].min()} den {wide['date'].max()})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
