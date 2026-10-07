# -*- coding: utf-8 -*-
r"""
MARKET VALUATION FETCHER
Kéo chỉ số định giá TOÀN THỊ TRƯỜNG đã được VNDirect tính sẵn (API finfo v4/ratios):
    P/E, P/B, P/S, Tỷ suất cổ tức, Vốn hóa — theo NGÀY, cho VNINDEX / HNX / UPCOM / VN30.
Không cần tự gộp từng mã. Không cần API key.

Output:
    valuation-master.csv  long-format (code, date, ratio, value) — nguồn gốc, merge/dedup incremental
    valuation-wide.csv    wide theo (code, date): pe, pb, ps, div_yield, marketcap
                          + cấu phần suy ra: ln_ttm (LN toàn TT), gtss (BV toàn TT),
                            doanh_thu_ttm, co_tuc_ttm, earnings_yield
                          + nếu có D:\market-data\index-fetcher\indices-master.csv: close, eps_index, bvps_index
Chạy:
    python fetch_valuation.py            # incremental (kéo tiếp từ ngày cuối trong master)
    python fetch_valuation.py --full     # kéo lại toàn bộ lịch sử (từ 2017-12-15)
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MASTER_CSV = os.path.join(BASE_DIR, "valuation-master.csv")
WIDE_CSV = os.path.join(BASE_DIR, "valuation-wide.csv")
INDEX_MASTER = os.path.join(os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data")), "index-fetcher", "indices-master.csv")

API = "https://api-finfo.vndirect.com.vn/v4/ratios"
PAGE_SIZE = 1000
SLEEP = 0.6  # nghỉ giữa các request, tránh làm phiền server

CODES = ["VNINDEX", "HNX", "UPCOM", "VN30"]
RATIOS = {
    "PRICE_TO_EARNINGS": "pe",
    "PRICE_TO_BOOK": "pb",
    "PRICE_TO_SALES": "ps",
    "DIVIDEND_YIELD": "div_yield",
    "MARKETCAP": "marketcap",
}
# map code VNDirect -> index_code trong indices-master.csv (index-fetcher)
INDEX_CODE_MAP = {"VNINDEX": "VNINDEX", "HNX": "HNXINDEX", "UPCOM": "UPCOM", "VN30": "VN30"}


def fetch_pair(code, ratio_code, from_date=None):
    """Kéo toàn bộ lịch sử 1 cặp (code, ratioCode), phân trang, trả list dict."""
    q = f"code:{code}~ratioCode:{ratio_code}"
    if from_date:
        q += f"~reportDate:gte:{from_date}"
    rows, page = [], 1
    while True:
        params = urllib.parse.urlencode(
            {"q": q, "size": PAGE_SIZE, "page": page, "sort": "reportDate:asc"}
        )
        url = f"{API}?{params}"
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.load(resp)
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"  [retry] {code}/{ratio_code} p{page}: {e}")
                time.sleep(3 * (attempt + 1))
        batch = data.get("data", [])
        rows.extend(
            {"code": r.get("code", code), "date": r["reportDate"], "ratio": ratio_code, "value": r["value"]}
            for r in batch
        )
        if len(batch) < PAGE_SIZE:
            break
        page += 1
        time.sleep(SLEEP)
    return rows


def build_wide(master):
    wide = master.pivot_table(index=["code", "date"], columns="ratio", values="value").reset_index()
    wide.columns.name = None
    wide = wide.rename(columns=RATIOS)
    for col in RATIOS.values():
        if col not in wide.columns:
            wide[col] = pd.NA

    # Cấu phần định giá suy ngược từ số VNDirect đã tính (đơn vị VND, TTM):
    wide["ln_ttm"] = wide["marketcap"] / wide["pe"]          # tổng LNST TTM toàn thị trường
    wide["gtss"] = wide["marketcap"] / wide["pb"]            # tổng giá trị sổ sách (VCSH)
    wide["doanh_thu_ttm"] = wide["marketcap"] / wide["ps"]   # tổng doanh thu TTM
    wide["co_tuc_ttm"] = wide["div_yield"] * wide["marketcap"]  # tổng cổ tức tiền TTM
    wide["earnings_yield"] = 1 / wide["pe"]
    # ROE TTM toàn thị trường = LN_TTM / VCSH = (mcap/pe)/(mcap/pb) = pb/pe = EPS/BVPS.
    # Dùng pb/pe (không dùng ln_ttm/gtss) để có lịch sử từ 2017 (marketcap chỉ có từ 2019).
    # Đơn vị: phần thập phân (0.15 = 15%). Nhân 100 ra %.
    wide["roe_ttm"] = wide["pb"] / wide["pe"]

    # EPS/BVPS theo "điểm chỉ số" = close / PE, close / PB (cần giá đóng cửa từ index-fetcher)
    if os.path.exists(INDEX_MASTER):
        idx = pd.read_csv(INDEX_MASTER, usecols=["date", "index_code", "close"])
        idx["code"] = idx["index_code"].map({v: k for k, v in INDEX_CODE_MAP.items()})
        idx = idx.dropna(subset=["code"])[["date", "code", "close"]]
        wide = wide.merge(idx, on=["code", "date"], how="left")
        wide["eps_index"] = wide["close"] / wide["pe"]
        wide["bvps_index"] = wide["close"] / wide["pb"]
    else:
        print(f"[!] Khong thay {INDEX_MASTER} -> bo qua eps_index/bvps_index")

    return wide.sort_values(["code", "date"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="Keo lai toan bo lich su")
    args = ap.parse_args()

    old = pd.DataFrame(columns=["code", "date", "ratio", "value"])
    if os.path.exists(MASTER_CSV) and not args.full:
        old = pd.read_csv(MASTER_CSV)
        print(f"Master hien co {len(old)} dong, den {old['date'].max()}")

    new_rows = []
    for code in CODES:
        for ratio_code in RATIOS:
            from_date = None
            if not old.empty:
                sub = old[(old["code"] == code) & (old["ratio"] == ratio_code)]
                if not sub.empty:
                    from_date = sub["date"].max()  # keo lai tu ngay cuoi, dedup sau
            got = fetch_pair(code, ratio_code, from_date)
            print(f"  {code:8s} {ratio_code:20s} +{len(got)} dong (tu {from_date or 'dau lich su'})")
            new_rows.extend(got)
            time.sleep(SLEEP)

    frames = [df for df in (old, pd.DataFrame(new_rows)) if not df.empty]
    master = pd.concat(frames, ignore_index=True)
    master = master.drop_duplicates(subset=["code", "date", "ratio"], keep="last")
    master = master.sort_values(["code", "ratio", "date"])
    master.to_csv(MASTER_CSV, index=False, encoding="utf-8-sig")
    print(f"\n-> {MASTER_CSV}: {len(master)} dong")

    wide = build_wide(master)
    wide.to_csv(WIDE_CSV, index=False, encoding="utf-8-sig")
    print(f"-> {WIDE_CSV}: {len(wide)} dong ({wide['date'].min()} den {wide['date'].max()})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
