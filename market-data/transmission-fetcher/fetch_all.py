# -*- coding: utf-8 -*-
"""Orchestrator: keo tat ca nguon -> transmission-master.csv -> tinh chi tieu phai sinh
-> xuat ban do node (transmission-nodes.csv) va bang wide (transmission-wide.csv).

Cach dung:
    python fetch_all.py              # incremental (mac dinh): keo tu max_date - 10 ngay
    python fetch_all.py --full       # keo lai full lich su tu FULL_START
    python fetch_all.py --only sbv   # chi chay 1 nguon: sbv | us | fx | market | bctc | caps | local
    python fetch_all.py --build      # khong keo, chi tinh lai phai sinh + bao cao
"""
from __future__ import annotations

import argparse
import datetime as dt
import os

import pandas as pd

import src_bctc
import src_caps
import src_dlkt
import src_fx
import src_lending
import src_local
import src_market
import src_rates
import src_sbv
import src_us
from common import (COLS, MASTER, NODES_CSV, ROOT, log, merge_master, new_session,
                    row, safe_to_csv, setup_stdout)

FULL_START = "2018-01-01"          # VCB/khoi ngoai deu co tu ~2018
LOOKBACK_DAYS = 10                 # incremental: keo lui de va gap/so revise
BCTC_EVERY_DAYS = 7                # BCTC quy chi doi 4 lan/nam -> keo lai moi tuan
WIDE = os.path.join(ROOT, "transmission-wide.csv")
NODEVIEW = os.path.join(ROOT, "transmission-nodes.csv")

# chi tieu phai sinh: series_id -> (input chinh, input phu, ham, ten, don vi, node)
DERIVED = [
    ("fx_band_ceiling", "fx_central", None, lambda a, b: a * 1.05,
     "Tran bien do +5%", "VND/USD", "N04", "Ty gia USD/VND"),
    ("fx_band_floor", "fx_central", None, lambda a, b: a * 0.95,
     "San bien do -5%", "VND/USD", "N04", "Ty gia USD/VND"),
    ("fx_vcb_sell_vs_ceiling", "fx_vcb_sell", "fx_central",
     lambda a, b: (a / (b * 1.05) - 1) * 100,
     "VCB ban so voi tran bien do", "%", "N04", "Ty gia USD/VND"),
    ("swap_on", "ib_on", "us_sofr", lambda a, b: a - b,
     "Chenh lai suat qua dem VND-USD", "diem %", "N07", "Swap point"),
    ("swap_1m", "ib_1m", "us_tbill_4w", lambda a, b: a - b,
     "Chenh lai suat 1 thang VND-USD", "diem %", "N07", "Swap point"),
    ("swap_3m", "ib_3m", "us_tbill_3m", lambda a, b: a - b,
     "Chenh lai suat 3 thang VND-USD", "diem %", "N07", "Swap point"),
    ("ib_curve_1m_on", "ib_1m", "ib_on", lambda a, b: a - b,
     "Do doc TT2 1 thang - qua dem", "diem %", "N08", "Lai suat TT2"),
    ("ib_spread_policy", "ib_on", "policy_refinance", lambda a, b: a - b,
     "LNH qua dem - lai suat tai cap von", "diem %", "N08", "Lai suat TT2"),
    # VCB khong cong bo lai suat huy dong binh quan truc tiep, chi cong bo cho vay BQ va chenh lech
    # -> huy dong BQ = cho vay BQ - chenh lech (cung mot bang cong bo, cung ngay)
    ("deposit_rate_avg_vcb", "lending_rate_avg", "lending_deposit_spread", lambda a, b: a - b,
     "Lai suat huy dong binh quan VCB (= cho vay BQ - chenh lech)", "%/nam", "N11", "Lai suat TT1"),
]


def _pivot(df: pd.DataFrame) -> pd.DataFrame:
    w = df.pivot_table(index="date", columns="series_id", values="value", aggfunc="last")
    w.index = pd.to_datetime(w.index)
    return w.sort_index()


def build_derived(df: pd.DataFrame) -> list:
    """Tinh chi tieu phai sinh tren khung ngay da can chinh (ffill toi da 5 phien).

    Chi xuat gia tri o nhung ngay input CHINH thuc su co quan sat - tranh bia so
    cho ngay khong co du lieu goc.
    """
    w = _pivot(df)
    wf = w.ffill(limit=5)
    out = []

    for sid, a_col, b_col, fn, name, unit, node_id, node_name in DERIVED:
        if a_col not in w.columns:
            continue
        if b_col is not None and b_col not in wf.columns:
            continue
        mask = w[a_col].notna()
        a = wf.loc[mask, a_col]
        b = wf.loc[mask, b_col] if b_col else pd.Series(index=a.index, dtype=float)
        val = fn(a, b)
        for d, v in val.dropna().items():
            out.append(row(d.strftime("%Y-%m-%d"), sid, round(float(v), 6),
                           series_name=name, unit=unit, freq="D", source="derived",
                           node_id=node_id, node_name=node_name))

    # tong doanh so lien ngan hang cong bo
    vol_cols = [c for c in w.columns if c.startswith("ib_vol_") and c != "ib_vol_total"]
    if vol_cols:
        tot = w[vol_cols].sum(axis=1, min_count=1).dropna()
        for d, v in tot.items():
            out.append(row(d.strftime("%Y-%m-%d"), "ib_vol_total", float(v),
                           series_name="Tong doanh so LNH cong bo", unit="ty VND",
                           freq="D", source="derived", node_id="N09", node_name="Nguon TT2"))

    # bom rong = OMO trung thau - tin phieu phat hanh
    if "omo_win_total" in w.columns:
        bom = w["omo_win_total"]
        hut = w["bill_issue_vol"] if "bill_issue_vol" in w.columns else 0
        net = (bom - (hut if isinstance(hut, int) else hut.fillna(0))).dropna()
        for d, v in net.items():
            out.append(row(d.strftime("%Y-%m-%d"), "omo_net", float(v),
                           series_name="Bom rong OMO - tin phieu", unit="ty VND",
                           freq="D", source="derived", node_id="N05", node_name="NHNN hut bom"))

    # bom rong TICH LUY = reverse repo dang luu hanh + tin phieu luu hanh.
    # FiinProX ghi tin phieu luu hanh la SO AM (hut tien) -> day la phep CONG, khong phai tru.
    if "omo_outstanding" in w.columns:
        rp = w["omo_outstanding"]
        bl = (w["bill_outstanding"].reindex(rp.index).fillna(0)
              if "bill_outstanding" in w.columns else 0)
        for d, v in (rp + bl).dropna().items():
            out.append(row(d.strftime("%Y-%m-%d"), "omo_net_outstanding", round(float(v), 2),
                           series_name="Bom rong dang luu hanh (repo + tin phieu)", unit="ty VND",
                           freq="D", source="derived", node_id="N05", node_name="NHNN hut bom"))

    # giai ngan dau tu cong LUY KE tu dau nam = cong don so thang trong cung nam
    if "public_inv_month" in w.columns:
        s = w["public_inv_month"].dropna()
        acc, yr = 0.0, None
        for d, v in s.items():
            acc = float(v) if yr != d.year else acc + float(v)
            yr = d.year
            out.append(row(d.strftime("%Y-%m-%d"), "public_inv_ytd", round(acc, 2),
                           series_name="Giai ngan dau tu cong luy ke tu dau nam", unit="ty VND",
                           freq="M", source="derived", node_id="N09", node_name="Nguon TT2"))

    # tong huy dong = tien gui TCKT + cu dan
    if {"deposits_corporate", "deposits_household"} <= set(w.columns):
        tot = w[["deposits_corporate", "deposits_household"]].sum(axis=1, min_count=2).dropna()
        for d, v in tot.items():
            out.append(row(d.strftime("%Y-%m-%d"), "deposits_total", round(float(v), 2),
                           series_name="Tong tien gui TCKT + cu dan", unit="ty VND",
                           freq="M", source="derived", node_id="N10",
                           node_name="Room va chi phi von NH"))
        w = w.copy()
        w["deposits_total"] = tot

    # Tang truong luy ke tu dau nam va so cung ky.
    # BAY: chuoi thang cua FiinProX co thang bi thieu (vd khong co 12/2025). Neu lay
    # "quan sat cuoi cung cua nam truoc" lam goc thi khi thieu thang 12 se am tham do
    # voi thang 11 hoac thang 9 -> ra so YTD sai ma khong bao loi. Vi vay YTD chi tinh
    # khi goc THUC SU la thang 12; khong co thi de trong. YoY dung de bu cho khoang trong.
    growth = {}
    for src, sid, name, node_id, node_name in [
        ("m2", "m2_growth", "Tang truong M2 luy ke", "N12", "Tin dung giai ngan"),
        ("deposits_total", "deposit_growth_ytd", "Tang truong huy dong luy ke", "N10", "Room va chi phi von NH"),
    ]:
        if src not in w.columns:
            continue
        s = w[src].dropna()
        ytd, yoy = {}, {}
        for d, v in s.items():
            dec = s[(s.index.year == d.year - 1) & (s.index.month == 12)]
            if len(dec) and dec.iloc[-1]:
                ytd[d] = (v / dec.iloc[-1] - 1) * 100
            diffs = pd.Series(abs(s.index - (d - pd.Timedelta(days=365))), index=s.index)
            near = diffs[diffs <= pd.Timedelta(days=25)]
            if len(near):
                base = s.loc[near.idxmin()]
                if base:
                    yoy[d] = (v / base - 1) * 100
        growth[sid] = pd.Series(ytd)
        for d, v in ytd.items():
            out.append(row(d.strftime("%Y-%m-%d"), sid, round(float(v), 4), series_name=name,
                           unit="%", freq="M", source="derived",
                           node_id=node_id, node_name=node_name))
        for d, v in yoy.items():
            out.append(row(d.strftime("%Y-%m-%d"), sid.replace("_ytd", "").replace("_growth", "") + "_growth_yoy",
                           round(float(v), 4), series_name=name.replace("luy ke", "so cung ky"),
                           unit="%", freq="M", source="derived",
                           node_id=node_id, node_name=node_name))

    # du tru ngoai hoi quy ra SO THANG NHAP KHAU - thuoc do "du dia" khong can gia dinh
    # nao ve quy dinh, thong le quoc te coi duoi 3 thang la mong
    if {"fx_reserves", "imports"} <= set(w.columns):
        res = w["fx_reserves"].dropna()
        imp = wf["imports"].reindex(res.index)
        cov = (res / imp).dropna()
        for d, v in cov.items():
            out.append(row(d.strftime("%Y-%m-%d"), "fx_import_cover", round(float(v), 2),
                           series_name="Du tru ngoai hoi tinh theo thang nhap khau",
                           unit="thang", freq="M", source="derived",
                           node_id="N06", node_name="NHNN ban forward"))

    # chenh tang truong tin dung - huy dong: duong = phan thieu phai bu bang von TT2
    # credit_growth_ytd lay tu so cong bo cua NHNN (qua dulieukinhte), khong tu tinh
    if "credit_growth_ytd" in w.columns and growth.get("deposit_growth_ytd") is not None:
        cg = w["credit_growth_ytd"].dropna()
        gap = (cg - growth["deposit_growth_ytd"].reindex(cg.index)).dropna()
        for d, v in gap.items():
            out.append(row(d.strftime("%Y-%m-%d"), "credit_deposit_gap", round(float(v), 4),
                           series_name="Chenh tang truong tin dung - huy dong", unit="diem %",
                           freq="M", source="derived", node_id="N09", node_name="Nguon TT2"))

    return out


def rebuild_derived(df: pd.DataFrame) -> pd.DataFrame:
    """Xoa toan bo dong source='derived' roi tinh lai - tranh dong cu sot lai khi doi cong thuc."""
    keep = df[df["source"] != "derived"]
    safe_to_csv(keep[COLS], MASTER)
    return merge_master(build_derived(keep))


def build_reports(df: pd.DataFrame) -> None:
    """Xuat bang wide + ban do node (moi series 1 dong: gia tri moi nhat va bien dong)."""
    w = _pivot(df)
    safe_to_csv(w.reset_index().rename(columns={"index": "date"}), WIDE,
                float_format="%.6g")

    reg = pd.read_csv(NODES_CSV, encoding="utf-8-sig")
    recs = []
    for _, r in reg.iterrows():
        sid = r["series_id"]
        s = w[sid].dropna() if sid in w.columns else pd.Series(dtype=float)
        rec = {
            "node_id": r["node_id"], "node_name": r["node_name"],
            "series_id": sid, "series_name": r["series_name"],
            "unit": r["unit"], "freq": r["freq"], "source": r["source"],
            "status": r["status"], "n_obs": len(s),
            "last_date": s.index[-1].strftime("%Y-%m-%d") if len(s) else "",
            "last_value": round(float(s.iloc[-1]), 4) if len(s) else None,
            "chg_1": round(float(s.iloc[-1] - s.iloc[-2]), 4) if len(s) > 1 else None,
            "chg_5": round(float(s.iloc[-1] - s.iloc[-6]), 4) if len(s) > 5 else None,
            "chg_20": round(float(s.iloc[-1] - s.iloc[-21]), 4) if len(s) > 20 else None,
            "note": r.get("note", ""),
        }
        if len(s):
            age = (dt.date.today() - s.index[-1].date()).days
            rec["tre_ngay"] = age
            # note co chu "ngung" = nguon da dung cong bo chuoi nay -> khong canh bao cu
            ended = "ngung" in str(r.get("note", "")).lower()
            rec["canh_bao"] = "CU" if (r["freq"] == "D" and age > 7 and not ended) else ""
        else:
            rec["tre_ngay"] = None
            rec["canh_bao"] = "CHUA CO DU LIEU" if r["status"] in ("auto", "derived") else ""
        recs.append(rec)
    out = pd.DataFrame(recs)
    safe_to_csv(out, NODEVIEW)

    have = out[out["n_obs"] > 0]
    log("Bao cao: %d/%d series co du lieu, %d node duoc phu"
        % (len(have), len(out), have["node_id"].nunique()))
    bad = out[(out["canh_bao"] != "") & (out["status"].isin(["auto", "derived"]))]
    for _, r in bad.iterrows():
        log("  ! %-24s %s" % (r["series_id"], r["canh_bao"]))


def main() -> None:
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="keo lai full lich su")
    ap.add_argument("--only", default="", help="sbv | us | fx | market | bctc | rates | dlkt | local (cach nhau bang dau phay)")
    ap.add_argument("--build", action="store_true", help="chi tinh lai phai sinh + bao cao")
    args = ap.parse_args()

    if args.build:
        if not os.path.exists(MASTER):
            log("Chua co master, phai chay keo du lieu truoc.")
            return
        # tran quy dinh khong can mang -> luon lam moi trong --build de doi thong tu la
        # chi can sua SFL_STEPS/LDR_STEPS roi chay --build, khong phai keo lai ca pipeline
        df = merge_master(src_caps.fetch_all())
        df = merge_master(src_lending.aggregate([], df))
        build_reports(rebuild_derived(df))
        return

    # moc bat dau
    if args.full or not os.path.exists(MASTER):
        start = FULL_START
        log("Che do FULL: keo tu %s" % start)
    else:
        old = pd.read_csv(MASTER, dtype={"date": str}, encoding="utf-8-sig")
        last = old["date"].max()
        start = (dt.date.fromisoformat(last) - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
        log("Che do incremental: master toi %s -> keo tu %s" % (last, start))

    only = {x.strip() for x in args.only.split(",") if x.strip()}
    session = new_session("browser")
    rows = []

    if not only or "sbv" in only:
        log("[1/9] NHNN (lai suat, ty gia, OMO, tin phieu) - chi co so cua ngay hien tai")
        rows += src_sbv.fetch_all(session)
    if not only or "us" in only:
        log("[2/9] FRED (lai suat USD)")
        rows += src_us.fetch_all(new_session("plain"), start=FULL_START)
    if not only or "fx" in only:
        log("[3/9] Vietcombank (ty gia USD/VND theo ngay)")
        rows += src_fx.fetch_all(new_session("plain"), start=start)
    if not only or "market" in only:
        log("[4/9] Khoi ngoai mua rong")
        rows += src_market.fetch_all(new_session("api"), start=start)

    if not only or "bctc" in only:
        need = True
        if not only and os.path.exists(MASTER):
            m = pd.read_csv(MASTER, dtype={"date": str}, encoding="utf-8-sig")
            # moc so sanh la LAN KEO gan nhat, khong phai ngay cuoi quy - neu lay ngay
            # cuoi quy thi suot 3 thang nao cung "cu" va buoc nay chay lai moi ngay
            got = m.loc[m["series_id"] == "casa_ratio", "fetched_at"].max()
            if isinstance(got, str):
                # nguon la file local cua FS Extractor -> chi quet lai khi FILE MOI HON
                # lan quet truoc, chinh xac hon la dem so ngay co dinh
                src = src_bctc.F_BS
                fresh = (os.path.exists(src) and
                         dt.datetime.fromtimestamp(os.path.getmtime(src))
                         > dt.datetime.fromisoformat(got))
                need = fresh or (dt.datetime.now() - dt.datetime.fromisoformat(got)).days >= 30
        if need:
            log("[5/9] BCTC quy tu FS Extractor (LDR, CASA nhom NH niem yet)")
            rows += src_bctc.fetch_all()
        else:
            log("[5/9] BCTC quy: file FS Extractor chua doi -> bo qua")

    if not only or "rates" in only:
        log("[6/9] Lai suat huy dong TT1 (Nguoiquansat) - chi co so cua ngay hien tai")
        rows += src_rates.fetch_all(new_session("browser"))
    if not only or "dlkt" in only:
        log("[7/9] dulieukinhte.com (lai suat cho vay, tin dung, FDI, ty gia cho den)")
        rows += src_dlkt.fetch_all(new_session("browser"))
    if not only or "local" in only:
        log("[8/9] Gop tu tool khac tren may (macro-fetcher)")
        rows += src_local.fetch_all()
    if not only or "caps" in only:
        log("[9/10] Tran quy dinh theo thong tu (khong can mang)")
        rows += src_caps.fetch_all()
    if not only or "lending" in only:
        log("[10/10] Lai suat cho vay binh quan tung ngan hang (BIDV, Eximbank, Agribank, VIB)")
        rows += src_lending.fetch_all(new_session("browser"))

    log("Tong %d dong moi -> gop vao master" % len(rows))
    df = merge_master(rows)
    # tong hop Big4 / co phan tu cac lend_avg_<ma> da co trong master (ke ca VCB tu dulieukinhte)
    df = merge_master(src_lending.aggregate([], df))
    df = rebuild_derived(df)
    log("Master: %d dong, %d series, %s -> %s"
        % (len(df), df["series_id"].nunique(), df["date"].min(), df["date"].max()))
    build_reports(df)
    log("Xong. File: %s | %s | %s" % (os.path.basename(MASTER),
                                      os.path.basename(WIDE), os.path.basename(NODEVIEW)))


if __name__ == "__main__":
    main()
