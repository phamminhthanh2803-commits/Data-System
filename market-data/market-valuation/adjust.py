# -*- coding: utf-8 -*-
r"""
ADJUSTED VALUATION — P/E, P/B thị trường LOẠI TRỪ một nhóm mã
    P/E đieu chinh = (Σvon hoa − von hoa nhom loai) / (ΣLN TTM − LN TTM nhom loai)
    P/B đieu chinh = (Σvon hoa − von hoa nhom loai) / (ΣVCSH  − VCSH nhom loai)

Nguon so lieu tung ma: cung API VNDirect (v4/ratios, group STOCK) de nhat quan voi
so toan thi truong. LN ma = marketcap/PE; VCSH ma = marketcap/PB.
KHI MA THUA LO: VNDirect ngung cong bo PE -> fallback sang LNST TTM cua FS Extractor
(D:\bctc\fs-extractor\output_cap\market_cap_daily.csv, cot lnst_ttm_ty x 1e9) neu co.

Chay:
    python adjust.py VIC VHM VRE                 # loai nhom Vin khoi VNINDEX
    python adjust.py VCB BID CTG --index VNINDEX # loai nhom bank
    python adjust.py VIC VHM --full              # keo lai full lich su cac ma

Yeu cau: da chay fetch_valuation.py truoc (can valuation-wide.csv).
Output: valuation-adjusted.csv + cache tickers-master.csv (incremental).
"""
import argparse
import os
import sys
import time

import pandas as pd

from fetch_valuation import fetch_pair, BASE_DIR, WIDE_CSV, SLEEP, INDEX_MASTER

TICKERS_CSV = os.path.join(BASE_DIR, "tickers-master.csv")
ADJ_CSV = os.path.join(BASE_DIR, "valuation-adjusted.csv")

# Schema indices-master.csv (index-fetcher) — de ghi chi so phai sinh vao chung
IDX_COLS = ["date", "index_code", "index_name", "source", "open", "high",
            "low", "close", "adj_close", "volume", "value"]

VCI_CHART = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
VCI_HDR = {"User-Agent": "Mozilla/5.0", "Content-Type": "application/json",
           "Accept": "application/json", "Referer": "https://trading.vietcap.com.vn/"}


MD_ROOT = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))
BCTC_ROOT = os.path.normpath(os.environ.get("BCTC_ROOT", "D:/bctc"))
TV_HISTORY = os.path.join(MD_ROOT, "index-fetcher", "tv-history.csv")   # index-fetcher/tv_history.py (TradingView, toan bo ma VN, tu 2000)


def fetch_prices(tickers, count_back=3000):
    """Gia dong cua DAILY tung ma (dung cho return nhom loai), long-format code,date,price.
    Tu 14/09/2026: UU TIEN doc tv-history.csv (TradingView, gia da dieu chinh, lich su tu khi niem yet);
    ma nao khong co trong file (hoac file cu >7 ngay) thi fallback VCI gap-chart nhu truoc."""
    import requests
    frames = []
    missing = list(tickers)
    if os.path.exists(TV_HISTORY):
        tv = pd.read_csv(TV_HISTORY, usecols=["date", "symbol", "exchange", "close"], dtype={"date": str})
        tv = tv[tv["exchange"].isin(["HOSE", "HNX", "UPCOM"])]
        fresh = (pd.Timestamp.now() - pd.to_datetime(tv["date"].max())).days <= 7
        if fresh:
            for sym in tickers:
                s = tv[tv["symbol"] == sym]
                if len(s):
                    frames.append(pd.DataFrame({"code": sym, "date": s["date"].values, "price": s["close"].values}))
                    missing.remove(sym)
            print(f"  Gia tu TradingView (tv-history.csv): {len(tickers) - len(missing)}/{len(tickers)} ma"
                  + (f", VCI cho {missing}" if missing else ""))
        else:
            print(f"  [!] tv-history.csv cu (moi nhat {tv['date'].max()}) -> dung VCI")
    for sym in missing:
        payload = {"timeFrame": "ONE_DAY", "symbols": [sym],
                   "to": int(time.time()), "countBack": count_back}
        try:
            r = requests.post(VCI_CHART, json=payload, headers=VCI_HDR, timeout=30)
            r.raise_for_status()
            d = r.json()
            sd = d[0] if isinstance(d, list) and d else {}
            if not sd or not sd.get("c"):
                print(f"  [!] {sym}: khong co gia")
                continue
            dates = pd.to_datetime(pd.to_numeric(sd["t"]), unit="s", utc=True) \
                      .tz_convert("Asia/Ho_Chi_Minh").strftime("%Y-%m-%d")
            frames.append(pd.DataFrame({"code": sym, "date": dates, "price": sd["c"]}))
        except Exception as e:
            print(f"  [!] Loi keo gia {sym}: {repr(e)[:80]}")
        time.sleep(0.4)
    if not frames:
        return pd.DataFrame(columns=["code", "date", "price"])
    return pd.concat(frames, ignore_index=True)


def write_to_index_master(adj, code, label):
    """Ghi chuoi diem_adj (chi so DA LOAI nhom) vao indices-master.csv nhu 1 index phai sinh.
    Dedup theo (date, index_code) -> chi thay ban cu cua CHINH code nay, khong dung index that.
    index-fetcher khi chay lai se giu nguyen cac dong nay (khong fetch nen khong xoa)."""
    if not os.path.exists(INDEX_MASTER):
        print(f"  [!] Khong thay {INDEX_MASTER} -> bo qua ghi index phai sinh")
        return
    sub = adj.dropna(subset=["diem_adj"])
    out = pd.DataFrame({
        "date": sub["date"], "index_code": code, "index_name": label,
        "source": "derived-mktval", "open": pd.NA, "high": pd.NA, "low": pd.NA,
        "close": sub["diem_adj"], "adj_close": sub["diem_adj"],
        "volume": pd.NA, "value": pd.NA,
    })[IDX_COLS]
    im = pd.read_csv(INDEX_MASTER, dtype={"date": str})
    for c in IDX_COLS:
        if c not in im.columns:
            im[c] = pd.NA
    # GIU nguyen moi cot khac cua master (index-fetcher da them currency, value_usd... tu 09/2026),
    # chi bo sung cot con thieu cho dong phai sinh -> khong lam mat cot khi ghi lai.
    all_cols = list(im.columns) + [c for c in IDX_COLS if c not in im.columns]
    for c in all_cols:
        if c not in out.columns:
            out[c] = "VND" if c == "currency" else pd.NA
    im = im[im["index_code"] != code]                    # bo ban cu cua chi so phai sinh
    combined = pd.concat([im[all_cols], out[all_cols]], ignore_index=True)
    combined = combined.drop_duplicates(subset=["date", "index_code"], keep="last")
    combined = combined.sort_values(["index_code", "date"])
    combined.to_csv(INDEX_MASTER, index=False, encoding="utf-8-sig")
    print(f"-> Ghi {len(out)} dong '{code}' vao {INDEX_MASTER}")
FS_CAP_CSVS = [
    os.path.join(BCTC_ROOT, "fs-extractor", "output_cap", "market_cap_daily.csv"),
    os.path.join(BCTC_ROOT, "fs-extractor", "output_cap_adjust", "market_cap_daily.csv"),
]

RATIOS = ["MARKETCAP", "PRICE_TO_EARNINGS", "PRICE_TO_BOOK"]


def load_fs_fallback(tickers):
    """LNST TTM (VND) theo (ticker, date) tu FS Extractor — dung khi VNDirect thieu PE (ma lo)."""
    frames = []
    for path in FS_CAP_CSVS:
        if os.path.exists(path):
            fs = pd.read_csv(path, usecols=["ticker", "date", "lnst_ttm_ty"])
            frames.append(fs[fs["ticker"].isin(tickers)])
    if not frames:
        return pd.DataFrame(columns=["code", "date", "earn_vci"])
    fs = pd.concat(frames, ignore_index=True)
    fs = fs.drop_duplicates(subset=["ticker", "date"], keep="last")
    fs = fs.rename(columns={"ticker": "code"})
    fs["earn_vci"] = fs["lnst_ttm_ty"] * 1e9
    return fs[["code", "date", "earn_vci"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="+", help="Cac ma loai tru, vd: VIC VHM VRE")
    ap.add_argument("--index", default="VNINDEX", choices=["VNINDEX", "HNX", "UPCOM", "VN30"])
    ap.add_argument("--full", action="store_true", help="Keo lai full lich su cac ma")
    args = ap.parse_args()
    tickers = [t.upper() for t in args.tickers]

    if not os.path.exists(WIDE_CSV):
        sys.exit("Chua co valuation-wide.csv — chay fetch_valuation.py truoc.")

    # 1. Keo/cap nhat cache tung ma (incremental nhu master chinh)
    old = pd.DataFrame(columns=["code", "date", "ratio", "value"])
    if os.path.exists(TICKERS_CSV) and not args.full:
        old = pd.read_csv(TICKERS_CSV)
    new_rows = []
    for code in tickers:
        for ratio_code in RATIOS:
            from_date = None
            if not old.empty:
                sub = old[(old["code"] == code) & (old["ratio"] == ratio_code)]
                if not sub.empty:
                    from_date = sub["date"].max()
            got = fetch_pair(code, ratio_code, from_date)
            print(f"  {code:8s} {ratio_code:20s} +{len(got)} dong (tu {from_date or 'dau lich su'})")
            if ratio_code == "MARKETCAP" and not got and from_date is None:
                print(f"  [!] {code}: khong co du lieu — kiem tra lai ma")
            new_rows.extend(got)
            time.sleep(SLEEP)
    frames = [df for df in (old, pd.DataFrame(new_rows)) if not df.empty]
    cache = pd.concat(frames, ignore_index=True)
    cache = cache.drop_duplicates(subset=["code", "date", "ratio"], keep="last")
    cache = cache.sort_values(["code", "ratio", "date"])
    cache.to_csv(TICKERS_CSV, index=False, encoding="utf-8-sig")

    # 2. Wide tung ma -> LN, VCSH tung ma theo ngay
    tk = cache[cache["code"].isin(tickers)]
    tk = tk.pivot_table(index=["code", "date"], columns="ratio", values="value").reset_index()
    tk.columns.name = None
    tk = tk.rename(columns={"MARKETCAP": "mcap", "PRICE_TO_EARNINGS": "pe", "PRICE_TO_BOOK": "pb"})
    for col in ("pe", "pb"):
        if col not in tk.columns:
            tk[col] = pd.NA
    tk["earn"] = tk["mcap"] / tk["pe"]
    tk["book"] = tk["mcap"] / tk["pb"]

    # fallback LN tu FS Extractor cho ngay ma lo (VNDirect khong cong bo PE)
    fs = load_fs_fallback(tickers)
    if not fs.empty:
        tk = tk.merge(fs, on=["code", "date"], how="left")
        n_fb = (tk["earn"].isna() & tk["earn_vci"].notna()).sum()
        tk["earn"] = tk["earn"].fillna(tk["earn_vci"])
        tk = tk.drop(columns=["earn_vci"])
        if n_fb:
            print(f"  [i] Dung fallback LNST VCI cho {n_fb} dong (ma lo, VNDirect thieu PE)")

    # 3. Gop nhom loai tru theo ngay
    #    - Moi ma chi tinh tu ngay co P/B dau tien (proxy ngay niem yet):
    #      VNDirect co snapshot MARKETCAP cuoi quy TRUOC ca ngay niem yet (data rac, vd VPL)
    #    - Ngay ma chua niem yet: chua nam trong ro -> tru 0, KHONG huy ca ngay
    first_live = tk[tk["pb"].notna()].groupby("code")["date"].min()
    for code in tickers:
        if code in first_live.index:
            print(f"  {code}: tinh tu {first_live[code]} (ngay co P/B dau tien)")
        else:
            print(f"  [!] {code}: khong co P/B ngay nao -> bi loai khoi phep tinh")
    tk = tk[tk["date"] >= tk["code"].map(first_live)]
    tk["thieu_ln"] = tk["mcap"].notna() & tk["earn"].isna()
    tk["thieu_bv"] = tk["mcap"].notna() & tk["book"].isna()
    grp = tk.groupby("date").agg(
        mcap_ex=("mcap", "sum"),
        earn_ex=("earn", "sum"),
        book_ex=("book", "sum"),
        n_ma=("mcap", "count"),
        n_thieu_ln=("thieu_ln", "sum"),
        n_thieu_bv=("thieu_bv", "sum"),
    ).reset_index()
    grp.loc[grp["n_thieu_ln"] > 0, "earn_ex"] = pd.NA
    grp.loc[grp["n_thieu_bv"] > 0, "book_ex"] = pd.NA

    # 4. Join voi so toan thi truong, tinh chi so dieu chinh
    w = pd.read_csv(WIDE_CSV)
    w = w[w["code"] == args.index][["date", "pe", "pb", "marketcap", "ln_ttm", "gtss", "close"]]
    adj = w.merge(grp, on="date", how="left").sort_values("date")
    chua_ny = adj["mcap_ex"].isna()  # ngay chua co ma nao trong nhom niem yet
    adj.loc[chua_ny, ["mcap_ex", "earn_ex", "book_ex", "n_ma", "n_thieu_ln", "n_thieu_bv"]] = 0
    adj["index"] = args.index
    adj["nhom_loai"] = "+".join(tickers)
    adj["mcap_adj"] = adj["marketcap"] - adj["mcap_ex"]
    adj["pe_adj"] = adj["mcap_adj"] / (adj["ln_ttm"] - adj["earn_ex"])
    adj["pb_adj"] = adj["mcap_adj"] / (adj["gtss"] - adj["book_ex"])
    # ROE = LN/VCSH = pb/pe. Ban goc va ban DA LOAI nhom ma (mcap tu triet tieu):
    adj["roe"] = adj["pb"] / adj["pe"]                                          # ROE ro goc
    adj["roe_adj"] = (adj["ln_ttm"] - adj["earn_ex"]) / (adj["gtss"] - adj["book_ex"])  # ROE da loai
    adj["ty_trong_mcap"] = adj["mcap_ex"] / adj["marketcap"]

    # "Diem" chi so DIEU CHINH loai nhom (phuong phap RETURN-DECOMPOSITION):
    #   R_exVin_t = (R_index_t - w_Vin_(t-1) * r_Vin_t) / (1 - w_Vin_(t-1))
    #   diem_adj noi chuoi tu R_exVin, neo bang chinh chi so tai ngay goc.
    # Uu diem: xay tu return CUA CHINH VN-Index (da dieu chinh divisor) -> KHONG bi nhieu
    #   boi ma moi niem yet ngoai nhom (khac han mcap-ratio).
    # CANH BAO con lai: w_Vin dung mcap DAY DU cua VNDirect (khong free-float) -> trong so
    #   nhom hoi cao hon thuc te trong VN-Index; gia VCI dieu chinh ca co tuc nen r_Vin hoi
    #   cao hon 'price return' thuan (chenh nho ~ loi tuc co tuc).
    adj["diem"] = adj["close"]                       # diem chi so goc (VN-Index...)
    prices = fetch_prices(tickers)
    if prices.empty:
        print("  [!] Khong keo duoc gia nhom loai -> diem_adj de trong")
        adj["diem_adj"] = pd.NA
    else:
        # r_Vin = return gia nhom, trong so theo mcap tung ma (VNDirect), dung mcap ngay t-1
        vin = tk[["code", "date", "mcap"]].merge(prices, on=["code", "date"], how="inner")
        vin = vin.sort_values(["code", "date"])
        vin["ret"] = vin.groupby("code")["price"].pct_change()
        vin["mcap_prev"] = vin.groupby("code")["mcap"].shift(1)
        vin = vin.dropna(subset=["ret", "mcap_prev"])
        vin = vin[vin["mcap_prev"] > 0]
        vin["contrib"] = vin["mcap_prev"] * vin["ret"]
        g = vin.groupby("date").agg(num=("contrib", "sum"), den=("mcap_prev", "sum")).reset_index()
        g["r_vin"] = g["num"] / g["den"]
        rvin = g[["date", "r_vin"]]

        # Chuoi ngay giao dich (co close), noi chuoi ex-Vin
        s = adj[adj["close"].notna()].sort_values("date").copy()
        s["R_index"] = s["close"].pct_change()
        s["w_prev"] = s["ty_trong_mcap"].shift(1)
        s = s.merge(rvin, on="date", how="left")
        s["R_exvin"] = (s["R_index"] - s["w_prev"] * s["r_vin"]) / (1 - s["w_prev"])
        # ngay hiem thieu r_vin -> gia dinh ex-Vin di theo index (khong lam gay chuoi)
        miss = s["r_vin"].isna() & s["R_index"].notna()
        s.loc[miss, "R_exvin"] = s.loc[miss, "R_index"]
        base_close = s["close"].iloc[0]
        growth = (1 + s["R_exvin"]).fillna(1.0)
        growth.iloc[0] = 1.0                          # ngay goc = neo
        s["diem_adj"] = base_close * growth.cumprod()
        adj = adj.merge(s[["date", "diem_adj"]], on="date", how="left")
        print(f"  [i] diem_adj (return-decomp) neo tai {s['date'].iloc[0]} = {base_close:.2f} diem"
              f" | r_vin {len(rvin)} ngay, thieu {int(miss.sum())} ngay")

    cols = ["date", "index", "nhom_loai", "pe", "pe_adj", "pb", "pb_adj",
            "roe", "roe_adj", "diem", "diem_adj", "ty_trong_mcap", "marketcap",
            "mcap_ex", "ln_ttm", "earn_ex", "gtss", "book_ex", "n_thieu_ln"]
    adj[cols].to_csv(ADJ_CSV, index=False, encoding="utf-8-sig")

    # Ghi chuoi diem_adj vao indices-master.csv nhu 1 chi so phai sinh (dung canh VNINDEX...)
    write_to_index_master(adj, f"{args.index}ADJ", f"{args.index} loai {'+'.join(tickers)}")

    ok = adj["pe_adj"].notna().sum()
    print(f"\n-> {ADJ_CSV}: {len(adj)} dong ({adj['date'].min()} den {adj['date'].max()})")
    print(f"   pe_adj tinh duoc {ok}/{len(adj)} ngay"
          + ("" if ok == len(adj) else " — ngay thieu do ma lo khong co LN (xem n_thieu_ln)"))
    last = adj.dropna(subset=["pe_adj"]).iloc[-1]
    print(f"   Moi nhat {last['date']}: PE {last['pe']:.2f} -> {last['pe_adj']:.2f} | "
          f"PB {last['pb']:.2f} -> {last['pb_adj']:.2f} | "
          f"ROE {last['roe']*100:.2f}% -> {last['roe_adj']*100:.2f}% | "
          f"Diem {last['diem']:.1f} -> {last['diem_adj']:.1f} | "
          f"nhom loai chiem {last['ty_trong_mcap']*100:.1f}% von hoa")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
