# -*- coding: utf-8 -*-
r"""build_nganh_bds.py — BƯỚC 1: BCTC NGÀNH BẤT ĐỘNG SẢN từ dump VCI toàn sàn (fs-extractor).

Nguồn : D:\bctc\fs-extractor\output\{income_statement,balance_sheet,cash_flow,note}.csv (VCI, từ 2018-Q1, số RIÊNG từng quý, VND)
        lọc ICB cấp 2 = "Bất động sản" + mọi mã có trong nhom_bds.csv (thêm mã ngoài ICB bằng cách thêm dòng vào file này).
Khoá  : (mã, báo cáo, row_order). VCI trả CÙNG MỘT thứ tự dòng cho mọi mã/kỳ (đã kiểm: 1 chuỗi item duy nhất mỗi báo cáo)
        -> row_order = vị trí dòng trong (mã, kỳ); item_id VCI có trùng (cost, accumulated_depreciation, held_to_maturity...)
        nên không dùng item_id làm khoá. Script tự kiểm lại mỗi lần chạy.
Nhóm  : nhom_bds.csv (tạo tự động lần đầu, sau đó user sửa; lần sau chỉ THÊM mã mới). cong_vao_nganh = 0 -> không cộng vào tổng
        (VIC đã hợp nhất VHM/VRE; DXS là con của DXG) để khỏi đếm đôi.
Ra    : raw\*.parquet (cache trích từ dump), data_fs.csv (wide: key ticker|bc|row_order hoặc G:<nhóm>|bc|row_order, cột quý + năm),
        dim_item.csv, dim_company.csv, nganh_bat_dong_san.sqlite (fact_fs long, dim_company, dim_item).
Năm   : dòng chảy (IS, CF, thuyết minh doanh thu/chi phí) = tổng 4 quý (thiếu quý -> trống); số dư (BS, thuyết minh còn lại) = Q4.
"""
import argparse
import os
import sqlite3

import duckdb
import numpy as np
import pandas as pd

from common_bds import (FIRST_Q, FSX_OUT, HERE, KCN, KHONG_CONG, NGANH_L2, NHOM_CSV, NHOM_TONG, RAW, SQLITE,
                        STMTS, VIN, DON_VI, log, qidx, qlabel, qname, utf8_stdout)

NOTE_FLOW = set(range(102, 147)) | {155}          # noc102..noc146 (doanh thu/giá vốn/tài chính/chi phí theo yếu tố), noc155


def extract(force=False):
    """Trích BĐS từ dump VCI (~3 GB) -> raw\\<bc>.parquet; chỉ trích lại khi CSV nguồn mới hơn."""
    os.makedirs(RAW, exist_ok=True)
    extra = []
    if os.path.exists(NHOM_CSV):
        extra = pd.read_csv(NHOM_CSV, dtype=str).ticker.dropna().tolist()
    con = duckdb.connect()
    out = {}
    for bc, f in STMTS.items():
        src = os.path.join(FSX_OUT, f + ".csv")
        pq = os.path.join(RAW, f + ".parquet")
        if not force and os.path.exists(pq) and os.path.getmtime(pq) >= os.path.getmtime(src):
            out[bc] = pd.read_parquet(pq)
            continue
        log(f"  trích {f}.csv ({os.path.getsize(src) / 1e6:,.0f} MB) ...")
        lst = ",".join("'" + t.replace("'", "") + "'" for t in extra) or "''"
        d = con.execute(f"""
            WITH s AS (SELECT *, row_number() OVER () rn
                       FROM read_csv_auto('{src.replace(os.sep, '/')}', all_varchar=true)
                       WHERE nganh_L2 = '{NGANH_L2}' OR ticker IN ({lst}))
            SELECT ticker, ten_cong_ty, nganh_L4, item_id, item, period,
                   try_cast(value AS DOUBLE) AS value,
                   row_number() OVER (PARTITION BY ticker, period ORDER BY rn) AS row_order
            FROM s WHERE period LIKE '____-Q_'""").df()
        d.to_parquet(pq, index=False)
        out[bc] = d
    return out


def check_layout(raw):
    """Mọi (mã, kỳ) phải cùng chuỗi item_id -> row_order là khoá chung."""
    bad = {}
    for bc, d in raw.items():
        seq = d.sort_values(["ticker", "period", "row_order"]).groupby(["ticker", "period"]).item_id.agg("|".join)
        n = seq.nunique()
        if n > 1:
            top = seq.value_counts().index[0]
            bad[bc] = sorted({t for (t, p), s in seq.items() if s != top})
    if bad:
        log(f"  CẢNH BÁO: bố cục dòng khác chuẩn ở {bad} -> các mã này có thể lệch dòng, kiểm tra lại")
    return bad


def dim_item(raw):
    rows = []
    for bc, d in raw.items():
        ref = d.drop_duplicates(["row_order"]).sort_values("row_order")[["row_order", "item_id", "item"]].copy()
        ref["k"] = ref.groupby("item_id").cumcount() + 1
        ref["bc"] = bc
        rows.append(ref)
    di = pd.concat(rows)[["bc", "row_order", "item_id", "k", "item"]]
    di["key_item"] = np.where(di.groupby(["bc", "item_id"]).k.transform("max") > 1,
                              di.item_id + "#" + di.k.astype(str), di.item_id)
    num = pd.to_numeric(di.item_id.str.extract(r"^noc(\d+)$")[0], errors="coerce")
    di["dong_chay"] = (di.bc.isin(["IS", "CF"]) | ((di.bc == "NOTE") & num.isin(NOTE_FLOW))).astype(int)
    di["don_vi"] = np.where(di.item_id.str.startswith("eps"), "VND", "tỷ đồng")
    return di.reset_index(drop=True)


def load_nhom(raw):
    """nhom_bds.csv: tạo lần đầu theo luật, lần sau giữ nguyên dòng cũ (user đã sửa) + thêm mã mới."""
    allc = pd.concat([d[["ticker", "ten_cong_ty", "nganh_L4", "period"]] for d in raw.values()])   # TBR, DCH thiếu IS
    cty = (allc.sort_values("period").groupby("ticker")
           .agg(ten_cong_ty=("ten_cong_ty", "last"), nganh_L4=("nganh_L4", "last")).reset_index())

    def auto(r):
        t = r.ticker
        if t in VIN:
            return "Vingroup"
        if t in KCN or "khu công nghiệp" in str(r.ten_cong_ty).lower():
            return "Khu công nghiệp"
        if "Tư Vấn" in str(r.nganh_L4) or "Môi giới" in str(r.nganh_L4):
            return "Dịch vụ BĐS"
        return "Phát triển nhà ở & khác"

    cty["nhom"] = cty.apply(auto, axis=1)
    cty["cong_vao_nganh"] = [0 if t in KHONG_CONG else 1 for t in cty.ticker]
    cty["ghi_chu"] = [KHONG_CONG.get(t, "") for t in cty.ticker]
    if os.path.exists(NHOM_CSV):
        old = pd.read_csv(NHOM_CSV, dtype={"cong_vao_nganh": int}, keep_default_na=False)
        new = cty[~cty.ticker.isin(old.ticker)]
        if len(new):
            log(f"  nhom_bds.csv: thêm {len(new)} mã mới {new.ticker.tolist()}")
        nh = pd.concat([old, new], ignore_index=True)
        nh = nh.drop(columns=["ten_cong_ty", "nganh_L4"]).merge(cty[["ticker", "ten_cong_ty", "nganh_L4"]], on="ticker", how="left")
    else:
        nh = cty
        log(f"  tạo nhom_bds.csv ({len(nh)} mã) - sửa cột nhom / cong_vao_nganh rồi chạy lại nếu cần")
    nh = nh[["ticker", "ten_cong_ty", "nganh_L4", "nhom", "cong_vao_nganh", "ghi_chu"]].sort_values(["nhom", "ticker"])
    nh.to_csv(NHOM_CSV, index=False, encoding="utf-8-sig")
    return nh


def members(nh, rule):
    ok = nh[nh.cong_vao_nganh.astype(int) == 1]
    if rule is None:
        return set(ok.ticker)
    if rule.startswith("!"):
        return set(ok[ok.nhom != rule[1:]].ticker)
    return set(ok[ok.nhom == rule].ticker)


def build(force=False):
    raw = extract(force)
    check_layout(raw)
    di = dim_item(raw)
    nh = load_nhom(raw)

    long = pd.concat([d.assign(bc=bc)[["ticker", "bc", "row_order", "period", "value"]] for bc, d in raw.items()])
    long = long[long.period >= FIRST_Q].dropna(subset=["value"])
    long = long.merge(di[["bc", "row_order", "don_vi", "dong_chay"]], on=["bc", "row_order"], how="left")
    long["value"] = np.where(long.don_vi == "VND", long.value, long.value / DON_VI)
    periods = sorted(long.period.unique(), key=qidx)
    periods = [qname(i) for i in range(qidx(periods[0]), qidx(periods[-1]) + 1)]
    log(f"  {long.ticker.nunique()} mã, {len(long):,} số liệu, kỳ {periods[0]} .. {periods[-1]}")

    # ---- dòng nhóm (tổng các mã thành viên có số)
    grp = []
    no_eps = long[long.don_vi != "VND"]
    for code, _ten, rule in NHOM_TONG:
        mem = members(nh, rule)
        s = no_eps[no_eps.ticker.isin(mem)].groupby(["bc", "row_order", "period"]).value.sum(min_count=1).reset_index()
        grp.append(s.assign(ticker="G:" + code))
        n = long[(long.bc == "IS") & long.ticker.isin(mem)].groupby("period").ticker.nunique().reset_index(name="value")
        grp.append(n.assign(ticker="G:" + code, bc="CNT", row_order=0))
    allrows = pd.concat([long[["ticker", "bc", "row_order", "period", "value"]]] + grp, ignore_index=True)

    # ---- wide quý
    w = allrows.pivot_table(index=["ticker", "bc", "row_order"], columns="period", values="value", aggfunc="first")
    w = w.reindex(columns=periods)
    nz = w.fillna(0).abs().sum(axis=1) > 0
    w = w[nz]
    # ---- năm: dòng chảy = tổng 4 quý đủ; số dư = Q4
    years = sorted({int(p[:4]) for p in periods if f"{p[:4]}-Q4" in periods and f"{p[:4]}-Q1" in periods})
    flow = w.index.to_frame(index=False).merge(di[["bc", "row_order", "dong_chay"]], on=["bc", "row_order"], how="left")
    is_flow = (flow.dong_chay.fillna(0).to_numpy() == 1)
    ycols = {}
    for y in years:
        qs = [f"{y}-Q{i}" for i in range(1, 5)]
        s4 = w[qs].sum(axis=1, min_count=4)
        ycols[str(y)] = np.where(is_flow, s4, w[f"{y}-Q4"])
    wy = pd.DataFrame(ycols, index=w.index)
    # CNT năm = số công ty ở Q4
    cnt = w.index.get_level_values("bc") == "CNT"
    for y in years:
        wy.loc[cnt, str(y)] = w.loc[cnt, f"{y}-Q4"]

    idx = w.index.to_frame(index=False)
    lab = idx.merge(di[["bc", "row_order", "key_item", "item", "don_vi"]], on=["bc", "row_order"], how="left")
    lab.loc[lab.bc == "CNT", ["key_item", "item", "don_vi"]] = ["n_cong_ty", "Số công ty có BCTC", "công ty"]
    out = pd.DataFrame({
        "key": (idx.ticker + "|" + idx.bc + "|" + idx.row_order.astype(int).astype(str)).to_numpy(),
        "ma": idx.ticker.to_numpy(), "bc": idx.bc.to_numpy(), "dong": idx.row_order.astype(int).to_numpy(),
        "item_id": lab.key_item.to_numpy(), "chi_tieu": lab.item.to_numpy(), "don_vi": lab.don_vi.to_numpy()})
    q = w.reset_index(drop=True); q.columns = [qlabel(c) for c in q.columns]
    yv = wy.reset_index(drop=True)
    data_fs = pd.concat([out, q, yv], axis=1)
    order_bc = {"CNT": 0, "IS": 1, "BS": 2, "CF": 3, "NOTE": 4}
    data_fs["_g"] = data_fs.ma.str.startswith("G:").map({True: 0, False: 1})
    data_fs = data_fs.sort_values(["_g", "ma", "bc", "dong"], key=lambda s: s.map(order_bc) if s.name == "bc" else s).drop(columns="_g")
    data_fs.to_csv(os.path.join(HERE, "data_fs.csv"), index=False, encoding="utf-8-sig")
    di.to_csv(os.path.join(HERE, "dim_item.csv"), index=False, encoding="utf-8-sig")

    # ---- dim_company: nhóm + kỳ BCTC gần nhất + VCSH CĐ mẹ gần nhất
    bs = long[long.bc == "BS"].merge(di[["bc", "row_order", "key_item"]], on=["bc", "row_order"])
    eq = bs[bs.key_item.isin(["owners_equity", "minority_interests"])].pivot_table(
        index=["ticker", "period"], columns="key_item", values="value", aggfunc="first").reset_index()
    eq["vcsh_me"] = eq.owners_equity - eq.get("minority_interests", 0).fillna(0)
    last = eq.sort_values("period").groupby("ticker").tail(1)[["ticker", "period", "vcsh_me"]]
    dc = nh.merge(last.rename(columns={"period": "ky_gan_nhat"}), on="ticker", how="left")
    dc.to_csv(os.path.join(HERE, "dim_company.csv"), index=False, encoding="utf-8-sig")

    con = sqlite3.connect(SQLITE)
    fl = allrows.merge(di[["bc", "row_order", "key_item", "item", "don_vi"]], on=["bc", "row_order"], how="left")
    fl.to_sql("fact_fs", con, if_exists="replace", index=False)
    con.execute("CREATE INDEX IF NOT EXISTS ix_fs ON fact_fs(ticker, bc, row_order, period)")
    dc.to_sql("dim_company", con, if_exists="replace", index=False)
    di.to_sql("dim_item", con, if_exists="replace", index=False)
    con.commit(); con.close()
    log(f"  data_fs.csv: {len(data_fs):,} dòng x {len(periods)} quý + {len(years)} năm | nhóm: "
        + ", ".join(f"{c} {len(members(nh, r))}" for c, _, r in NHOM_TONG))
    return data_fs, di, nh, periods, years


if __name__ == "__main__":
    utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="trích lại từ dump VCI dù cache còn mới")
    build(ap.parse_args().force)
