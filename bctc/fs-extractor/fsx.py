# -*- coding: utf-8 -*-
"""
fsx.py — Bộ kéo data tài chính VN (vnstock/VCI), 1 entry point cho 3 pipeline.

    python fsx.py bctc HAH GMD --from 2020-Q1            # báo cáo tài chính
    python fsx.py cap  --file tickers.txt --from 2020-01-01   # vốn hóa + P/E + P/B
    python fsx.py liq  --from 2020-01-01                 # thanh khoản index

Chọn mã theo NGÀNH (khỏi nhập tay từng mã):
    python fsx.py nganh                                  # xem danh sách ngành ICB
    python fsx.py nganh "ngan hang"                      # tra ngành + xem mã
    python fsx.py bctc --nganh "Ngân hàng" --from 2020-Q1
    python fsx.py cap  --nganh "Cảng biển,Vận tải biển" --san HOSE,HNX

Phần dùng chung (phân ngành, pacer, vòng lặp mã, nạp mã...) ở common.py.
Chi tiết phương pháp + giới hạn: xem NHAT-KY-LAM-VIEC.md.
"""
import argparse
import os

import pandas as pd

import common as C
from common import suppress, QEND


def _gather_tickers(args, req_weight, workers=1):
    """Gom mã từ 3 nguồn: dòng lệnh + --file + --nganh (khử trùng lặp, giữ thứ tự).

    Trả (tickers, listing) — listing khác None khi có dùng --nganh (tái sử dụng
    làm bảng phân ngành, khỏi gọi API thêm).
    """
    tickers = C.load_tickers(args.tickers, args.file)
    listing = None
    if getattr(args, "nganh", None):
        listing = C.get_listing(refresh=getattr(args, "refresh_nganh", False))
        tk, names = C.resolve_nganh(args.nganh, listing, args.san)
        if not tk:
            raise SystemExit(f"Khong co nganh nao khop '{', '.join(args.nganh)}'. "
                             f"Chay: python fsx.py nganh  de xem danh sach ten nganh.")
        print(f"Nganh khop: {', '.join(names)}")
        preview = " ".join(tk[:25]) + (" ..." if len(tk) > 25 else "")
        print(f"  -> {len(tk)} ma ({args.san or 'HOSE,HNX,UPCOM'}): {preview}")
        tickers += tk
    seen = set()
    tickers = [t for t in tickers if not (t in seen or seen.add(t))]
    if len(tickers) > 10:
        if workers > 1:      # song song: tran la do tre server (~20 ma/phut o 6 luong)
            est = max(1, -(-len(tickers) // (3 * workers)))
            print(f"Tong {len(tickers)} ma — uoc luong ~{est} phut "
                  f"(song song {workers} luong).", flush=True)
        else:
            est = -(-len(tickers) * req_weight // C.SAFE_PER_MIN)  # ceil, phút
            print(f"Tong {len(tickers)} ma — uoc luong ~{est} phut (rate-limit "
                  f"{C.SAFE_PER_MIN} req/phut).", flush=True)
    return tickers, listing


# ══════════════════════════ PIPELINE 1: BCTC ══════════════════════════
REPORTS = {"income_statement": "income_statement",
           "balance_sheet": "balance_sheet",
           "cash_flow": "cash_flow"}
BCTC_REQ = 7  # income+balance+cashflow+ratio+note(2)+handshake
BCTC_WORKERS = 6      # so luong mac dinh cho bctc (do thuc te: 4 luong 17,6 ma/phut, 8 luong 23,6)


def _make_finance(symbol, period):
    with suppress():
        from vnstock.explorer.vci.financial import Finance
        return Finance(symbol=symbol, period=period, show_log=False)


def _pull_report(fin, report_type, period, limit):
    """Gọi hàm nội bộ _get_report để vượt giới hạn 4 kỳ của bản community."""
    with suppress():
        return fin._get_report(report_type=report_type, period=period, lang="vi", limit=limit)


def _pull_note_long(fin, ticker, period, limit):
    """Thuyết minh BCTC — section NOTE (vnstock không expose). Trả long-format."""
    from vnstock.core.utils import client
    url = f"{fin.base_url}/v1/company/{fin.symbol}/financial-statement"
    with suppress():
        resp = client.send_request(url=url, headers=fin.headers, method="GET",
                                   params={"section": "NOTE"}, payload=None, show_log=False)
    data = resp.get("data") or {}
    rows = data.get("years" if period == "year" else "quarters", [])[:limit]
    if not rows:
        return pd.DataFrame()
    with suppress():
        mapping = fin._get_ratio_dict(format="dataframe")
    mapping = mapping.drop_duplicates(subset="field_name")
    vi_name = mapping.set_index("field_name")["name"].to_dict()
    en_name = mapping.set_index("field_name")["en_name"].to_dict()
    meta = {"organCode", "ticker", "createDate", "updateDate",
            "yearReport", "lengthReport", "publicDate"}
    recs = []
    for row in rows:
        year, length = row.get("yearReport"), row.get("lengthReport")
        if year is None:
            continue
        p = str(year) if period == "year" else f"{year}-Q{length}"
        for field, val in row.items():
            if val is not None and field not in meta and field in vi_name:
                recs.append({"ticker": ticker, "item": vi_name.get(field, field),
                             "item_en": en_name.get(field, field), "item_id": field,
                             "period": p, "value": val})
    return pd.DataFrame(recs)


def _to_long(df, ticker):
    """Wide (cột = kỳ) -> long: ticker | item | item_en | item_id | period | value."""
    if df is None or df.empty:
        return pd.DataFrame()
    id_cols = [c for c in ("item", "item_en", "item_id") if c in df.columns]
    period_cols = [c for c in df.columns if c not in id_cols and c != "report_period"]
    long_df = df.melt(id_vars=id_cols, value_vars=period_cols,
                      var_name="period", value_name="value")
    long_df.insert(0, "ticker", ticker)
    return long_df.dropna(subset=["value"])


def _bctc_one(tk, period, limit):
    """Kéo toàn bộ 5 báo cáo của 1 mã, trả {bucket: long_df}."""
    fin = _make_finance(tk, period)
    out = {name: _to_long(_pull_report(fin, rtype, period, limit), tk)
           for name, rtype in REPORTS.items()}
    out["ratio"] = _to_long(_pull_report(fin, "ratio", period, limit), tk)
    out["note"] = _pull_note_long(fin, tk, period, limit)
    return out


def cmd_bctc(args):
    for label, val in (("--from", args.p_from), ("--to", args.p_to)):
        if val:
            try:
                C.period_key(val)
            except (ValueError, IndexError):
                raise SystemExit(f"{label} không hợp lệ: '{val}'. Dùng 2020-Q1 hoặc 2020.")
    tickers, listing = _gather_tickers(args, BCTC_REQ,
                                       args.workers if args.workers else BCTC_WORKERS)
    if not tickers:
        raise SystemExit("Chưa có mã nào. Truyền trực tiếp, qua --file hoặc --nganh.")
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    industry = C.load_industry(listing)

    # BCTC đi qua Finance._get_report / _get_ratio_dict — hàm NỘI BỘ, KHÔNG dính
    # decorator @optimize_execution của vnai nên không bị đếm quota 20 req/phút.
    # => chạy song song được, nhanh gấp ~8-10 lần (xem C.process_tickers).
    workers = args.workers if args.workers else BCTC_WORKERS
    results, failed = C.process_tickers(
        tickers, lambda tk: _bctc_one(tk, args.period, args.limit), BCTC_REQ,
        args.sleep, workers=workers)

    buckets = {name: [] for name in list(REPORTS) + ["ratio", "note"]}
    for _, res in results:
        for name, df in res.items():
            buckets[name].append(df)

    for name, frames in buckets.items():
        frames = [f for f in frames if f is not None and not f.empty]
        if not frames:
            print(f"  {name}: khong co du lieu")
            continue
        combined = pd.concat(frames, ignore_index=True)
        # Ratio VCI trộn kỳ năm + quý -> giữ đúng loại kỳ đã chọn
        is_q = combined["period"].astype(str).str.contains("-Q")
        combined = combined[is_q if args.period == "quarter" else ~is_q]
        if args.p_from or args.p_to:
            combined = combined[combined["period"].map(
                lambda p: C.in_range(p, args.p_from, args.p_to))]
        combined = C.merge_industry(combined, industry)
        C.write_csv(combined, out_dir, f"{name}.csv", key=("ticker", "period"),
                    merge=not args.overwrite)
        print(f"  {name}.csv: moi keo {len(combined):,} dong | {combined['ticker'].nunique()} ma "
              f"| {combined['period'].nunique()} ky")
    _finish(out_dir, failed)


# ══════════════════════════ PIPELINE 2: VỐN HÓA + P/E + P/B ══════════════════════════
CAP_REQ = 5  # ratio_summary + overview + history + income + balance


def _first_scalar(df, col):
    """Lấy giá trị đầu tiên KHÔNG rỗng của cột `col` ở dòng đầu.

    VCI có lúc trả overview() với CỘT TRÙNG TÊN (2026-09: 'issue_share' xuất hiện
    4 lần, 2 ô có số 2 ô None) -> df[col] khi đó là DataFrame chứ không phải
    Series, .iloc[0] ra Series và mọi phép `if x` sau đó nổ
    "truth value of a Series is ambiguous". Hàm này gỡ về đúng 1 số.
    """
    if df is None or col not in df.columns:
        return None
    obj = df[col]
    if isinstance(obj, pd.DataFrame):
        vals = [v for v in obj.iloc[0].tolist() if pd.notna(v)]
        return vals[0] if vals else None
    v = obj.iloc[0]
    return None if pd.isna(v) else v


def _daily_market_cap(symbol, start, end):
    """Trả (df_daily, dict_snapshot) cho 1 mã. Xem NHAT-KY-LAM-VIEC.md mục 3."""
    with suppress():
        from vnstock.explorer.vci.company import Company
        from vnstock.explorer.vci.quote import Quote
        from vnstock.explorer.vci.financial import Finance
        comp = Company(symbol=symbol)
        # Gọi bản KHÔNG bọc decorator vnai (xem C.unwrap) -> không tốn quota 20/phút.
        # Company() không gọi API lúc khởi tạo nên sau bước này cap sạch quota.
        rs = C.unwrap(Company.ratio_summary)(comp)
        ov = C.unwrap(Company.overview)(comp)
        q = Quote(symbol=symbol)
        px = C.unwrap(Quote.history)(q, start=start, end=end, interval="1D")
        _fin = Finance(symbol=symbol, period="quarter", show_log=False)
        inc = _fin._get_report(report_type="income_statement", period="quarter", lang="vi", limit=500)
        bs = _fin._get_report(report_type="balance_sheet", period="quarter", lang="vi", limit=500)

    # 1) Số CP hiện tại (cố định) — xem mục 6 NHAT-KY về lý do dùng CP hiện tại
    cur_shares = _first_scalar(ov, "issue_share")
    # số CP lịch sử (fallback nếu thiếu issue_share)
    shares = rs[rs["quarter"].between(1, 4)][["year", "quarter", "number_of_shares_mkt_cap"]].copy()
    shares = shares.dropna(subset=["number_of_shares_mkt_cap"])
    shares["eff_date"] = pd.to_datetime(shares["year"].astype(str) + shares["quarter"].map(QEND))
    shares = shares[["eff_date", "number_of_shares_mkt_cap"]].sort_values("eff_date")

    # 2) LNST công ty mẹ TTM (4 quý LIỀN KỀ; thiếu quý -> NaN; quý âm vẫn cộng)
    qcols = [c for c in inc.columns if str(c)[:4].isdigit() and "-Q" in str(c)]
    prow = inc[inc["item_id"] == "attributable_to_parent_company"]
    lnst = pd.DataFrame()
    if not prow.empty and qcols:
        d = pd.DataFrame({"period": qcols, "v": [prow.iloc[0][c] for c in qcols]})
        d["qidx"] = d["period"].str[:4].astype(int) * 4 + (d["period"].str[-1].astype(int) - 1)
        d = d.sort_values("qidx").set_index("qidx")
        d = d.reindex(range(int(d.index.min()), int(d.index.max()) + 1))
        d["lnst_ttm"] = d["v"].rolling(4).sum()
        yr = (d.index // 4).astype(int)
        q = (d.index % 4 + 1).astype(int)
        d["eff_date"] = pd.to_datetime([f"{y}{QEND[qq]}" for y, qq in zip(yr, q)])
        lnst = d.dropna(subset=["lnst_ttm"])[["eff_date", "lnst_ttm"]].sort_values("eff_date")

    # 3) VCSH công ty mẹ = Vốn chủ sở hữu − lợi ích cổ đông thiểu số
    bqcols = [c for c in bs.columns if str(c)[:4].isdigit() and "-Q" in str(c)]

    def _line(item_id):
        r = bs[bs["item_id"] == item_id]
        return r.iloc[0] if not r.empty else None

    oe, mi, mi0 = _line("owners_equity"), _line("minority_interests"), \
        _line("minority_interests_before_2015")
    equity = pd.DataFrame()
    if oe is not None and bqcols:
        recs = []
        for c in bqcols:
            et = oe[c]
            if pd.isna(et):
                continue
            m_ = (mi[c] if mi is not None and pd.notna(mi[c]) else 0) + \
                 (mi0[c] if mi0 is not None and pd.notna(mi0[c]) else 0)
            recs.append({"eff_date": pd.Timestamp(f"{c[:4]}{QEND[int(c[-1])]}"),
                         "equity_parent": et - m_})
        equity = pd.DataFrame(recs).sort_values("eff_date")

    # 3b) pe/pb VietcapIQ công bố (theo quý) -> để đối chiếu
    vci_r = rs[rs["quarter"].between(1, 4)][["year", "quarter", "pe", "pb"]].copy()
    vci_r["eff_date"] = pd.to_datetime(vci_r["year"].astype(str) + vci_r["quarter"].map(QEND))
    vci_r = vci_r[["eff_date", "pe", "pb"]].rename(
        columns={"pe": "pe_vci", "pb": "pb_vci"}).sort_values("eff_date")

    # 4) Giá ngày (đã điều chỉnh) + vốn hóa = giá đc × SỐ CP HIỆN TẠI (mục 3 NHAT-KY)
    px["date"] = pd.to_datetime(px["time"])
    px = px.sort_values("date")
    if cur_shares and not pd.isna(cur_shares):
        m = px.copy()
        m["shares_outstanding"] = cur_shares
    else:  # fallback số CP lịch sử
        m = pd.merge_asof(px, shares, left_on="date", right_on="eff_date", direction="backward")
        m["shares_outstanding"] = m["number_of_shares_mkt_cap"]
    mcap_vnd = m["close"] * 1000 * m["shares_outstanding"]
    m["market_cap_ty"] = (mcap_vnd / 1e9).round(2)

    # 5) P/E = vốn hóa / NPATMI (LNST<=0 -> trống); P/B = vốn hóa / VCSH (<=0 -> trống)
    if not lnst.empty:
        m = pd.merge_asof(m, lnst, left_on="date", right_on="eff_date",
                          direction="backward", suffixes=("", "_l"))
        m["pe_daily"] = (mcap_vnd / m["lnst_ttm"]).round(2)
        m.loc[m["lnst_ttm"] <= 0, "pe_daily"] = pd.NA
    else:
        m["lnst_ttm"] = pd.NA
        m["pe_daily"] = pd.NA
    if not equity.empty:
        m = pd.merge_asof(m, equity, left_on="date", right_on="eff_date",
                          direction="backward", suffixes=("", "_e"))
        m["pb_daily"] = (mcap_vnd / m["equity_parent"]).round(2)
        m.loc[m["equity_parent"] <= 0, "pb_daily"] = pd.NA
    else:
        m["equity_parent"] = pd.NA
        m["pb_daily"] = pd.NA
    m["lnst_ttm_ty"] = (m["lnst_ttm"] / 1e9).round(2)
    m["equity_ty"] = (m["equity_parent"] / 1e9).round(2)
    m = pd.merge_asof(m, vci_r, left_on="date", right_on="eff_date",
                      direction="backward", suffixes=("", "_v"))
    m["pe_vci"] = m["pe_vci"].round(2)
    m["pb_vci"] = m["pb_vci"].round(2)
    m["date"] = m["date"].dt.strftime("%Y-%m-%d")
    m = m[(m["date"] >= start) & (m["date"] <= end)]
    daily = m[["date", "close", "shares_outstanding", "market_cap_ty", "lnst_ttm_ty",
               "equity_ty", "pe_daily", "pe_vci", "pb_daily", "pb_vci"]].dropna(
        subset=["shares_outstanding"])
    daily.insert(0, "ticker", symbol)

    # snapshot hiện tại
    snap = {"ticker": symbol}
    for src, key in [("current_price", "gia_hien_tai"), ("market_cap", "von_hoa_vnd"),
                     ("issue_share", "so_cp_luu_hanh"), ("foreigner_percentage", "room_ngoai_pct"),
                     ("state_percentage", "nha_nuoc_pct")]:
        if src in ov.columns:
            snap[key] = ov[src].iloc[0]
    last = rs.sort_values(["year", "quarter"]).iloc[-1]
    for src, key in [("pe", "pe"), ("pb", "pb"), ("roe", "roe")]:
        if src in rs.columns:
            snap[key] = round(last[src], 3) if pd.notna(last[src]) else None
    return daily, snap


def _industry_valuation(dd):
    """P/E, P/B CẢ NGÀNH bằng phương pháp GỘP (Σ tử / Σ mẫu cùng tập mã), 4 cấp ICB."""
    rows = []
    for lv in ("nganh_L1", "nganh_L2", "nganh_L3", "nganh_L4"):
        base = dd.dropna(subset=[lv])
        allg = base.groupby([lv, "date"]).agg(
            so_ma=("ticker", "nunique"), mcap_ty=("market_cap_ty", "sum")).reset_index()
        peg = base.dropna(subset=["lnst_ttm_ty"]).groupby([lv, "date"]).agg(
            so_ma_pe=("ticker", "nunique"), mcap_pe=("market_cap_ty", "sum"),
            lnst_ttm_ty=("lnst_ttm_ty", "sum")).reset_index()
        pbg = base.dropna(subset=["equity_ty"]).groupby([lv, "date"]).agg(
            so_ma_pb=("ticker", "nunique"), mcap_pb=("market_cap_ty", "sum"),
            equity_ty=("equity_ty", "sum")).reset_index()
        g = allg.merge(peg, on=[lv, "date"], how="left").merge(pbg, on=[lv, "date"], how="left")
        g = g.rename(columns={lv: "nganh"})
        g.insert(0, "cap", lv.replace("nganh_", ""))
        rows.append(g)
    ind = pd.concat(rows, ignore_index=True)
    ind["pe_nganh"] = (ind["mcap_pe"] / ind["lnst_ttm_ty"]).round(2)
    ind.loc[ind["lnst_ttm_ty"] <= 0, "pe_nganh"] = pd.NA
    ind["pb_nganh"] = (ind["mcap_pb"] / ind["equity_ty"]).round(2)
    ind.loc[ind["equity_ty"] <= 0, "pb_nganh"] = pd.NA
    for c in ("mcap_ty", "lnst_ttm_ty", "equity_ty"):
        ind[c] = ind[c].round(1)
    return ind[["cap", "nganh", "date", "so_ma", "mcap_ty", "so_ma_pe", "lnst_ttm_ty",
                "pe_nganh", "so_ma_pb", "equity_ty", "pb_nganh"]]


def cmd_cap(args):
    tickers, listing = _gather_tickers(args, CAP_REQ)
    if not tickers:
        raise SystemExit("Chưa có mã nào. Truyền trực tiếp, qua --file hoặc --nganh.")
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    industry = C.load_industry(listing)

    # cap gọi ratio_summary/overview/history qua C.unwrap nên KHÔNG còn bị vnai
    # đếm quota -> chạy song song được như bctc.
    results, failed = C.process_tickers(
        tickers, lambda tk: _daily_market_cap(tk, args.d_from, args.d_to), CAP_REQ,
        args.sleep, workers=args.workers if args.workers else BCTC_WORKERS)
    daily_frames = [res[0] for _, res in results]
    snaps = [res[1] for _, res in results]

    if daily_frames:
        dd = C.merge_industry(pd.concat(daily_frames, ignore_index=True), industry)
        C.write_csv(dd, out_dir, "market_cap_daily.csv", key=("ticker", "date"),
                    merge=not args.overwrite)
        print(f"  market_cap_daily.csv: moi keo {len(dd):,} dong | {dd['ticker'].nunique()} ma "
              f"| {dd['date'].min()} -> {dd['date'].max()}")
        if industry is not None:
            ind = _industry_valuation(dd)
            C.write_csv(ind, out_dir, "industry_valuation.csv")
            n_l3 = ind[ind["cap"] == "L3"]["nganh"].nunique()
            print(f"  industry_valuation.csv: {len(ind):,} dong | {n_l3} nganh L3 | gop 4 cap ICB")

    if snaps:
        sd = pd.DataFrame(snaps)
        if industry is not None:
            sd = sd.merge(industry[["ticker", "ten_cong_ty", "nganh_L3", "nganh_L4"]],
                          on="ticker", how="left")
            front = ["ticker", "ten_cong_ty", "nganh_L3", "nganh_L4"]
            sd = sd[front + [c for c in sd.columns if c not in front]]
        C.write_csv(sd, out_dir, "snapshot.csv", key=("ticker",), merge=not args.overwrite)
        print(f"  snapshot.csv: {len(sd)} ma")
    _finish(out_dir, failed)


# ══════════════════════════ PIPELINE 3: THANH KHOẢN INDEX ══════════════════════════
INDICES = ["VNINDEX", "VN30", "VNMID", "VNSML", "HNXINDEX", "HNX30", "UPCOMINDEX"]


def _pull_history(symbol, start, end):
    with suppress():
        from vnstock.explorer.vci.quote import Quote
        q = Quote(symbol=symbol)
        return C.unwrap(Quote.history)(q, start=start, end=end, interval="1D")


def cmd_liq(args):
    tickers, listing = _gather_tickers(args, 1)
    if not tickers and args.no_index:
        raise SystemExit("Chưa có mã nào và lại --no-index — không có gì để kéo.")
    if not tickers:
        print("Khong co ma nao -> chi keo INDEX.", flush=True)
    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    industry = C.load_industry(listing) if tickers else None

    if tickers:
        results, failed = C.process_tickers(
            tickers, lambda tk: _pull_history(tk, args.d_from, args.d_to), 1,
            args.sleep, workers=args.workers if args.workers else BCTC_WORKERS)
        frames = []
        for tk, df in results:
            df = df.copy()
            df.insert(0, "ticker", tk)
            frames.append(df)
        if frames:
            liq = pd.concat(frames, ignore_index=True)
            liq["date"] = pd.to_datetime(liq["time"]).dt.strftime("%Y-%m-%d")
            liq = liq[(liq["date"] >= args.d_from) & (liq["date"] <= args.d_to)]
            liq["gtgd_ty"] = (liq["close"] * liq["volume"] / 1e6).round(3)
            liq = liq[["ticker", "date", "open", "high", "low", "close", "volume", "gtgd_ty"]]
            liq = C.merge_industry(liq, industry)
            C.write_csv(liq, out_dir, "liquidity.csv", key=("ticker", "date"),
                        merge=not args.overwrite)
            print(f"  liquidity.csv: moi keo {len(liq):,} dong | {liq['ticker'].nunique()} ma "
                  f"| {liq['date'].min()} -> {liq['date'].max()}")
    else:
        failed = []

    if not args.no_index:
        pacer = C.Pacer()
        idx_frames = []
        for idx in INDICES:
            pacer.wait(1)
            try:
                df = C.call_with_retry(_pull_history, idx, args.d_from, args.d_to)
                df.insert(0, "index", idx)
                idx_frames.append(df)
            except Exception as e:
                print(f"    LOI {idx}: {e}", flush=True)
        if idx_frames:
            di = pd.concat(idx_frames, ignore_index=True)
            di["date"] = pd.to_datetime(di["time"]).dt.strftime("%Y-%m-%d")
            di = di[(di["date"] >= args.d_from) & (di["date"] <= args.d_to)]
            di = di[["index", "date", "open", "high", "low", "close", "volume"]]
            C.write_csv(di, out_dir, "indices.csv")
            print(f"  indices.csv: {len(di):,} dong | {di['index'].nunique()} chi so")
    _finish(out_dir, failed)


# ══════════════════════════ PIPELINE 4: TRA CỨU NGÀNH ══════════════════════════
def cmd_nganh(args):
    """Liệt kê ngành ICB (4 cấp) + số mã; có từ khóa thì kèm luôn danh sách mã."""
    listing = C.get_listing(refresh=args.refresh_nganh)
    df = listing
    if args.san:
        wanted = [s.strip().upper().replace("HSX", "HOSE") for s in args.san.split(",")]
        df = df[df["san"].isin(wanted)]
    kw = [C.strip_accents(k) for a in args.keyword for k in a.split(",") if k.strip()]

    print(f"\nDanh sach nganh ICB ({args.san or 'HOSE,HNX,UPCOM'}) — nguon VCI, "
          f"cache {C.NGANH_CACHE_DAYS} ngay:\n")
    for lv in ("nganh_L1", "nganh_L2", "nganh_L3", "nganh_L4"):
        grp = df.groupby(lv)["ticker"].nunique().sort_values(ascending=False)
        if kw:
            grp = grp[grp.index.map(lambda n: any(k in C.strip_accents(n) for k in kw))]
        if grp.empty:
            continue
        print(f"── Cap {lv.replace('nganh_', '')} " + "─" * 50)
        for name, n in grp.items():
            print(f"   {name:<55} {n:>4} ma")
    if kw:
        tk, names = C.resolve_nganh(args.keyword, listing, args.san)
        if tk:
            print(f"\nTong hop khop '{', '.join(args.keyword)}': {len(tk)} ma")
            for i in range(0, len(tk), 15):
                print("   " + " ".join(tk[i:i + 15]))
            print(f"\nKeo data: python fsx.py cap --nganh \"{args.keyword[0]}\""
                  + (f" --san {args.san}" if args.san else ""))
        else:
            print(f"\nKhong nganh nao khop '{', '.join(args.keyword)}'.")


# ══════════════════════════ CLI ══════════════════════════
def _finish(out_dir, failed):
    if failed:
        print(f"\nMa loi: {', '.join(failed)}")
    print(f"\nXong. CSV tai: {out_dir}")


def _add_common(p, default_out):
    p.add_argument("tickers", nargs="*", help="Danh sách mã, vd: HAH GMD VSC")
    p.add_argument("--file", help="File .txt chứa mã, mỗi dòng 1 mã")
    p.add_argument("--nganh", action="append", default=[],
                   help="Tên/từ khóa ngành ICB (lặp lại được, hoặc cách nhau dấu phẩy), "
                        "vd --nganh \"Ngân hàng\" — không cần gõ dấu")
    p.add_argument("--san", default="", help="Lọc sàn khi dùng --nganh, vd HOSE,HNX "
                                             "(mặc định cả HOSE,HNX,UPCOM)")
    p.add_argument("--refresh-nganh", action="store_true",
                   help="Kéo lại danh sách mã + ngành (bỏ qua cache 7 ngày)")
    p.add_argument("--out", default=default_out, help="Thư mục xuất CSV")
    p.add_argument("--sleep", type=float, default=1.0, help="Nghỉ giữa các mã (giây)")
    p.add_argument("--workers", type=int, default=0,
                   help="Số luồng song song, 0 = mặc định 6. Đặt 1 để quay lại "
                        "chế độ tuần tự có pacer (chậm ~4-8 lần).")
    p.add_argument("--overwrite", action="store_true",
                   help="Ghi đè file cũ thay vì GỘP thêm vào. Mặc định là gộp: kéo bổ "
                        "sung vài mã sẽ không làm mất các mã đã kéo trước đó. "
                        "Bản trước khi ghi vẫn được lưu trong <out>/_archive/.")


def main():
    ap = argparse.ArgumentParser(description="FS Extractor — kéo data tài chính VN (vnstock/VCI)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    today = pd.Timestamp.today().strftime("%Y-%m-%d")

    pb = sub.add_parser("bctc", help="Báo cáo tài chính (5 báo cáo long-format)")
    _add_common(pb, "output")
    pb.add_argument("--period", choices=["quarter", "year"], default="quarter")
    pb.add_argument("--limit", type=int, default=500, help="Số kỳ tối đa (mặc định 500=full)")
    pb.add_argument("--from", dest="p_from", default="", help="Kỳ đầu, vd 2020-Q1 hoặc 2020")
    pb.add_argument("--to", dest="p_to", default="", help="Kỳ cuối, vd 2024-Q4 hoặc 2024")
    pb.set_defaults(func=cmd_bctc)

    pc = sub.add_parser("cap", help="Vốn hóa + P/E + P/B theo ngày + định giá ngành")
    _add_common(pc, "output_cap")
    pc.add_argument("--from", dest="d_from", default="2015-01-01", help="Ngày đầu YYYY-MM-DD")
    pc.add_argument("--to", dest="d_to", default=today, help="Ngày cuối YYYY-MM-DD")
    pc.set_defaults(func=cmd_cap)

    pl = sub.add_parser("liq", help="Thanh khoản 7 index theo ngày")
    _add_common(pl, "output_liq")
    pl.add_argument("--from", dest="d_from", default="2015-01-01", help="Ngày đầu YYYY-MM-DD")
    pl.add_argument("--to", dest="d_to", default=today, help="Ngày cuối YYYY-MM-DD")
    pl.add_argument("--no-index", action="store_true", help="Bỏ qua index")
    pl.set_defaults(func=cmd_liq)

    pn = sub.add_parser("nganh", help="Tra cứu ngành ICB: tên ngành + số mã + danh sách mã")
    pn.add_argument("keyword", nargs="*", help="Từ khóa lọc ngành (không cần dấu), vd: ngan hang")
    pn.add_argument("--san", default="", help="Lọc sàn, vd HOSE,HNX")
    pn.add_argument("--refresh-nganh", "--refresh", dest="refresh_nganh", action="store_true",
                    help="Kéo lại danh sách (bỏ qua cache)")
    pn.set_defaults(func=cmd_nganh)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
