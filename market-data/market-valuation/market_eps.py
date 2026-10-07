# -*- coding: utf-8 -*-
r"""
MARKET EPS TUYỆT ĐỐI — NPATMI toàn thị trường / Σ số CP lưu hành (VND/CP)

Phương pháp:
  - Số CP lưu hành từng mã = vốn hóa (VNDirect ratios) / giá đóng cửa CHƯA điều
    chỉnh (v4/stock_prices, cột close — đã kiểm chứng: VNM ra đúng 2,09 tỷ CP)
  - Σ theo ngày trên các mã HOSE (khớp rổ VNINDEX; cột floor lấy theo từng ngày
    lịch sử nên mã chuyển sàn/hủy niêm yết tự đúng — không bị survivorship bias)
  - EPS tuyệt đối = ln_ttm (NPATMI TTM, từ valuation-wide) / Σ số CP
  - BVPS tuyệt đối = gtss / Σ số CP
  Lưu ý: P/E VNDirect tính trên LN cổ đông công ty mẹ (quy ước "công ty mẹ" như
  DIVIDEND_YIELD) -> ln_ttm = mcap/pe chính là NPATMI TTM.

Lịch sử từ 2019-07-19 (mốc có vốn hóa cấp chỉ số -> có ln_ttm). Full lần đầu
~3.500 request (~45 phút, nên chạy nền); incremental hằng ngày chỉ vài request.

Chạy:
    python market_eps.py           # incremental
    python market_eps.py --full    # tính lại từ 2019-07-19

QUAN TRỌNG - phương pháp panel + forward-fill: VNDirect KHÔNG công bố MARKETCAP
đủ mọi mã mỗi ngày (ngày thiếu nhóm này, ngày thiếu nhóm kia, có hôm lệch cả
nghìn tỷ). Vì số CP lưu hành đổi rất hiếm (chỉ khi phát hành/mua quỹ), tool xây
panel (ngày x mã) rồi ffill số CP tối đa 15 phiên -> tổng theo ngày ổn định.

Output:
    shares-master.csv  panel gốc (code, date, so_cp, mcap) - cache incremental
    market-eps.csv     date, so_ma, tong_cp_luu_hanh, tong_mcap_hose,
                       eps_abs, bvps_abs, qc_mcap (~1.0 la khop chi so)
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

import pandas as pd

from fetch_valuation import BASE_DIR, WIDE_CSV

OUT_CSV = os.path.join(BASE_DIR, "market-eps.csv")
SHARES_CSV = os.path.join(BASE_DIR, "shares-master.csv")
FFILL_LIMIT = 15   # so phien toi da keo so CP cu sang ngay thieu data
OVERLAP_DAYS = 30  # incremental lui lai N ngay de ffill/dedup an toan
API = "https://api-finfo.vndirect.com.vn/v4"
START = "2019-07-19"
PAGE_SIZE = 1000
SLEEP = 0.5


def fetch_paged(endpoint, q, fields=None, sort="date:asc", label=""):
    rows, page = [], 1
    while True:
        params = {"q": q, "size": PAGE_SIZE, "page": page, "sort": sort}
        if fields:
            params["fields"] = fields
        url = f"{API}/{endpoint}?{urllib.parse.urlencode(params)}"
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=40) as resp:
                    data = json.load(resp)
                break
            except Exception as e:
                if attempt == 2:
                    raise
                print(f"  [retry] {label} p{page}: {e}")
                time.sleep(3 * (attempt + 1))
        batch = data.get("data", [])
        rows.extend(batch)
        if page % 50 == 0:
            print(f"  ... {label} trang {page} ({len(rows):,} dong)")
        if len(batch) < PAGE_SIZE:
            break
        page += 1
        time.sleep(SLEEP)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()

    old = pd.DataFrame()
    from_date = START
    if os.path.exists(SHARES_CSV) and not args.full:
        old = pd.read_csv(SHARES_CSV)
        last = old["date"].max()
        from_date = (pd.Timestamp(last) - pd.Timedelta(days=OVERLAP_DAYS)).date().isoformat()
        print(f"Panel hien co den {last}, keo lai tu {from_date} (overlap ffill)")

    print(f"[1/3] Gia dong cua chua dieu chinh (HOSE) tu {from_date} ...")
    px = fetch_paged("stock_prices", f"date:gte:{from_date}~floor:HOSE~type:STOCK",
                     fields="code,date,close", label="gia")
    px = pd.DataFrame(px)
    print(f"      {len(px):,} dong gia")

    print(f"[2/3] Von hoa tung ma tu {from_date} ...")
    mc = fetch_paged("ratios", f"ratioCode:MARKETCAP~group:STOCK~reportDate:gte:{from_date}",
                     sort="reportDate:asc", label="mcap")
    mc = pd.DataFrame([{"code": r["code"], "date": r["reportDate"], "mcap": r["value"]}
                       for r in mc])
    print(f"      {len(mc):,} dong von hoa")

    print("[3/3] Panel + ffill so CP, tinh EPS tuyet doi ...")
    m = px.merge(mc, on=["code", "date"], how="inner")
    m = m[(m["close"] > 0) & (m["mcap"] > 0)]
    m["so_cp"] = m["mcap"] / (m["close"] * 1000)  # close don vi nghin VND
    m = m[["code", "date", "so_cp", "mcap"]]

    frames = [df for df in (old, m) if not df.empty]
    master = pd.concat(frames, ignore_index=True)
    master = master.drop_duplicates(subset=["code", "date"], keep="last")
    master = master.sort_values(["code", "date"])
    master.to_csv(SHARES_CSV, index=False, encoding="utf-8-sig")
    print(f"      {SHARES_CSV}: {len(master):,} dong, {master['code'].nunique()} ma")

    # panel ngay x ma, ffill so CP (va mcap cho QC) toi da FFILL_LIMIT phien
    cp = master.pivot_table(index="date", columns="code", values="so_cp").ffill(limit=FFILL_LIMIT)
    mcap_p = master.pivot_table(index="date", columns="code", values="mcap").ffill(limit=FFILL_LIMIT)
    daily = pd.DataFrame({
        "so_ma": cp.notna().sum(axis=1),
        "tong_cp_luu_hanh": cp.sum(axis=1),
        "tong_mcap_hose": mcap_p.sum(axis=1),
    }).reset_index()

    w = pd.read_csv(WIDE_CSV)
    w = w[w["code"] == "VNINDEX"][["date", "marketcap", "ln_ttm", "gtss"]]
    daily = daily.merge(w, on="date", how="left")
    daily["eps_abs"] = daily["ln_ttm"] / daily["tong_cp_luu_hanh"]
    daily["bvps_abs"] = daily["gtss"] / daily["tong_cp_luu_hanh"]
    daily["qc_mcap"] = daily["tong_mcap_hose"] / daily["marketcap"]
    daily = daily.drop(columns=["marketcap", "ln_ttm", "gtss"])

    daily.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    last = daily.dropna(subset=["eps_abs"]).iloc[-1]
    print(f"\n-> {OUT_CSV}: {len(daily)} ngay ({daily['date'].min()} den {daily['date'].max()})")
    print(f"   Moi nhat {last['date']}: {last['so_ma']:.0f} ma | "
          f"{last['tong_cp_luu_hanh']/1e9:,.1f} ty CP | "
          f"EPS {last['eps_abs']:,.0f} d/CP | BVPS {last['bvps_abs']:,.0f} d/CP | "
          f"QC mcap {last['qc_mcap']:.3f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
