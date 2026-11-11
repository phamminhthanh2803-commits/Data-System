# -*- coding: utf-8 -*-
r"""fetch_rss.py - keo tin RSS bao kinh te VN -> news_master + phan loai theo nganh (11/11/2026).

    python fetch_rss.py                 keo tat ca feed bat=1 trong config\feeds.csv, gop vao data\news_master.parquet, phan loai bai moi
    python fetch_rss.py --no-fetch      chi phan loai lai (sau khi sua config\keywords.csv / alias_ma.csv -> tu phan loai lai toan bo)
    python fetch_rss.py --reclass       ep phan loai lai toan bo lich su
    python fetch_rss.py --only CafeF,Vietstock

Dau ra (data\):
    news_master.parquet   1 dong = 1 bai (id = sha1 url chuan): ngay_gio (gio VN), nguon, chuyen_muc, goi_y, tieu_de, tom_tat, url, lay_luc
    news_tagged.parquet   master + nganh_chinh, nganh (|), chu_de (|), ma (|), loai_tin (|), diem, diem_chu_y, tu_khoa, nhom_trung, so_nguon
    news_tags.parquet     long id x nganh (diem, chu_de, tu_khoa) -> app chon nganh la sap tin theo diem / ngay
    feed_status.csv       trang thai tung feed lan chay cuoi
RSS chi giu 20-100 bai moi nhat moi chuyen muc -> chay nhieu lan/ngay (buoc news AM/PM/EOD + workflow news.yml 2 gio/lan).
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import sys
import time
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # D:\market-data -> mdlib
from mdlib import log, new_session, setup_stdout  # noqa: E402

import newslib as nl  # noqa: E402

STATE = os.path.join(nl.DATA, "phan_loai_state.json")
MASTER_COLS = ["id", "ngay_gio", "nguon", "chuyen_muc", "goi_y", "tieu_de", "tom_tat", "url", "lay_luc"]


def fetch_one(row, now):
    t0 = time.time()
    st = {"nguon": row.nguon, "chuyen_muc": row.chuyen_muc, "url": row.url, "http": None, "so_tin": 0, "loi": "", "luc": now}
    for lan in range(2):
        try:
            s = new_session("browser")
            r = s.get(row.url, timeout=25)
            st["http"] = r.status_code
            if r.status_code != 200:
                st["loi"] = f"HTTP {r.status_code}"
                continue
            items = nl.parse_rss(r.content)
            out = []
            for it in items:
                url = (it["url"] or "").strip()
                td = nl.norm(it["tieu_de"])
                if not url or not td:
                    continue
                ngay = nl.parse_date(it["ngay"]) or now
                if ngay > now + pd.Timedelta(hours=2):                 # gio sai mui (vd GMT ghi nham) -> lay gio keo
                    ngay = now
                out.append({"id": nl.make_id(url), "ngay_gio": ngay, "nguon": row.nguon, "chuyen_muc": row.chuyen_muc,
                            "goi_y": row.goi_y, "tieu_de": td, "tom_tat": nl.norm(it["tom_tat"])[:1500], "url": nl.canon_url(url),
                            "lay_luc": now})
            st["so_tin"], st["loi"] = len(out), ("" if out else "0 bai")
            st["giay"] = round(time.time() - t0, 1)
            return out, st
        except Exception as e:  # noqa: BLE001
            st["loi"] = f"{type(e).__name__}: {str(e)[:80]}"
            time.sleep(2)
    st["giay"] = round(time.time() - t0, 1)
    return [], st


def _gop_chuoi(s: pd.Series) -> str:
    vals = []
    for x in s.dropna():
        for p in str(x).split("|"):
            if p and p not in vals:
                vals.append(p)
    return "|".join(vals)


def merge_master(new: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    old = pd.read_parquet(nl.MASTER) if os.path.exists(nl.MASTER) else pd.DataFrame(columns=MASTER_COLS)
    n0 = old["id"].nunique() if len(old) else 0
    if new.empty:
        return old, 0
    allx = pd.concat([old, new], ignore_index=True)
    # 1 bai xuat hien o nhieu chuyen muc / nhieu lan keo: giu ban dau tien (ngay_gio som nhat), gop chuyen_muc + goi_y
    agg = allx.groupby("id", sort=False).agg(chuyen_muc=("chuyen_muc", _gop_chuoi), goi_y=("goi_y", _gop_chuoi))
    first = allx.sort_values(["ngay_gio", "lay_luc"]).drop_duplicates("id", keep="first").set_index("id")
    first["chuyen_muc"], first["goi_y"] = agg["chuyen_muc"], agg["goi_y"]
    out = first.reset_index()[MASTER_COLS].sort_values("ngay_gio", ascending=False).reset_index(drop=True)
    return out, out["id"].nunique() - n0


CUA_SO_GIO, NGUONG_GIONG = 36, 86      # gop tin trung: tieu de giong >= 86% (rapidfuzz ratio) trong 36 gio
TINH_LAI_NGAY = 3                       # chi tinh lai nhom cho bai 3 ngay gan nhat (bai cu giu nhom cu); lan dau / doi tu dien: 30 ngay


def gom_trung(t: pd.DataFrame, co_dinh: dict) -> pd.Series:
    """Khoa nhom tin trung giua cac bao: tieu de chuan hoa giong nhau (exact) hoac gan giong (rapidfuzz) trong CUA_SO_GIO.
    VD 'Vinhomes và Mitsubishi Corporation hợp tác...' (Tuoi Tre) = 'Vinhomes và Mitsubishi hợp tác...' (Dan tri)."""
    exact = t["tieu_de"].map(nl.nhom_trung)
    try:
        from rapidfuzz import fuzz, process
    except ImportError:
        return exact
    out = pd.Series([co_dinh.get(i) for i in t["id"]], index=t.index, dtype=object)
    moc = t["ngay_gio"].max() - pd.Timedelta(days=TINH_LAI_NGAY if co_dinh else 30)
    lam = t["ngay_gio"] >= moc - pd.Timedelta(hours=CUA_SO_GIO)        # cua so truoc moc lam ung vien so khop
    s = t[lam].sort_values("ngay_gio")
    ten = s["tieu_de"].map(lambda x: nl.norm(x).lower())
    gan = []                                                          # (thoi gian, tieu de chuan, nhom)
    for idx, ts, tt in zip(s.index, s["ngay_gio"], ten):
        gan = [g for g in gan if ts - g[0] <= pd.Timedelta(hours=CUA_SO_GIO)]
        nhom = out.at[idx] if (out.at[idx] and ts < moc) else None
        if nhom is None:
            m = process.extractOne(tt, [g[1] for g in gan], scorer=fuzz.ratio, score_cutoff=NGUONG_GIONG) if gan else None
            nhom = gan[m[2]][2] if m else exact.at[idx]
            out.at[idx] = nhom
        gan.append((ts, tt, nhom))
    return out.fillna(exact)


def classify(master: pd.DataFrame, full: bool) -> tuple[pd.DataFrame, pd.DataFrame, int]:
    h = nl.cfg_hash()
    st = {}
    if os.path.exists(STATE):
        try:
            st = json.load(open(STATE, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            st = {}
    old_t = pd.read_parquet(nl.TAGGED) if (os.path.exists(nl.TAGGED) and not full and st.get("hash") == h) else None
    old_g = pd.read_parquet(nl.TAGS) if old_t is not None and os.path.exists(nl.TAGS) else None
    if old_t is None:
        todo = master
        log(f"Che do: phan loai TOAN BO {len(master)} bai (tu dien {h} {'doi' if st.get('hash') not in (None, h) else 'moi'})")
    else:
        todo = master[~master["id"].isin(set(old_t["id"]))]
        log(f"Che do: phan loai {len(todo)} bai moi (tu dien {h} khong doi)")
    pl = nl.PhanLoai()
    rows, tags = [], []
    for r in todo.itertuples(index=False):
        k = pl.phan_loai(r.tieu_de, r.tom_tat, r.goi_y)
        ng = sorted(k["nganh"].items(), key=lambda x: -x[1])
        chinh = ng[0][0] if ng else nl.KHAC
        rows.append({"id": r.id, "nganh_chinh": chinh, "nganh": "|".join(n for n, _ in ng),
                     "chu_de": "|".join(dict.fromkeys(c for n, _ in ng for c in k["chu_de"].get(n, []))),
                     "ma": "|".join(k["ma"]), "loai_tin": "|".join(k["loai_tin"]), "diem": ng[0][1] if ng else 0.0,
                     "diem_su_kien": k["diem_su_kien"],
                     "tu_khoa": " · ".join(dict.fromkeys(t for n, _ in ng for t in k["tu_khoa"].get(n, [])))})
        for n, d in ng:
            tags.append({"id": r.id, "nganh": n, "diem": d, "chinh": n == chinh, "chu_de": "|".join(k["chu_de"].get(n, [])),
                         "tu_khoa": " · ".join(k["tu_khoa"].get(n, []))})
    new_t = pd.DataFrame(rows)
    new_g = pd.DataFrame(tags, columns=["id", "nganh", "diem", "chinh", "chu_de", "tu_khoa"])
    cls = new_t if old_t is None else pd.concat([old_t[[c for c in new_t.columns if c in old_t.columns]], new_t], ignore_index=True)
    g = new_g if old_g is None else pd.concat([old_g, new_g], ignore_index=True)
    cls = cls.drop_duplicates("id", keep="last")
    # ghep lai master (cot master luon lay ban moi nhat: chuyen_muc gop them) + tin trung tieu de giua cac bao
    t = master.merge(cls, on="id", how="left")
    co_dinh = dict(zip(old_t["id"], old_t["nhom_trung"])) if (old_t is not None and "nhom_trung" in old_t) else {}
    t["nhom_trung"] = gom_trung(t, co_dinh)
    t["so_nguon"] = t.groupby("nhom_trung")["nguon"].transform("nunique")
    t["diem_chu_y"] = (t["diem_su_kien"].fillna(0) + t["ma"].fillna("").ne("").astype(float) * 1.0
                       + (t["so_nguon"] - 1).clip(0, 4) * 1.0).round(2)
    t = t.sort_values("ngay_gio", ascending=False).reset_index(drop=True)
    g = g[g["id"].isin(set(t["id"]))].reset_index(drop=True)
    os.makedirs(nl.DATA, exist_ok=True)
    json.dump({"hash": h, "luc": datetime.now().isoformat(timespec="seconds")}, open(STATE, "w", encoding="utf-8"))
    return t, g, len(todo)


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--reclass", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    os.makedirs(nl.DATA, exist_ok=True)
    now = datetime.now(nl.VN_TZ).replace(tzinfo=None, microsecond=0)
    if not a.no_fetch:
        feeds = nl.read_cfg("feeds.csv")
        feeds = feeds[feeds["bat"].str.strip() != "0"]
        if a.only:
            ok = {x.strip().lower() for x in a.only.split(",")}
            feeds = feeds[feeds["nguon"].str.lower().isin(ok)]
        log(f"Che do: keo {len(feeds)} feed RSS ({feeds['nguon'].nunique()} bao)")
        rows, sts = [], []
        with cf.ThreadPoolExecutor(a.workers) as ex:
            for out, st in ex.map(lambda r: fetch_one(r, now), feeds.itertuples(index=False)):
                rows += out
                sts.append(st)
                if st["loi"]:
                    log(f"  ! {st['nguon']} / {st['chuyen_muc']}: {st['loi']}")
        sts = pd.DataFrame(sts)
        sts.to_csv(nl.FEED_STATUS, index=False, encoding="utf-8-sig")
        new = pd.DataFrame(rows, columns=MASTER_COLS)
        master, n_moi = merge_master(new)
        master.to_parquet(nl.MASTER, index=False)
        loi = int((sts["loi"] != "").sum())
        log(f"-> {len(new)} bai doc duoc, {n_moi} bai MOI · master {len(master)} bai · feed loi {loi}/{len(sts)}")
        if len(sts) and loi == len(sts):
            log("X LOI: khong feed nao doc duoc")
            sys.exit(2)
    else:
        if not os.path.exists(nl.MASTER):
            log("X LOI: chua co news_master.parquet")
            sys.exit(2)
        master = pd.read_parquet(nl.MASTER)
    t, g, n = classify(master, a.reclass)
    # ban cho app: tom tat cat 400 ky tu (RAM Streamlit Cloud 1 GB; ban day du o news_master) + danh sach nganh (app cloud khong co config\)
    t.assign(tom_tat=t["tom_tat"].str.slice(0, 400)).to_parquet(nl.TAGGED, index=False)
    g.to_parquet(nl.TAGS, index=False)
    nl.danh_sach_nganh()[["ma", "nganh", "loai", "thu_tu", "mo_ta"]].to_csv(os.path.join(nl.DATA, "nganh.csv"), index=False,
                                                                            encoding="utf-8-sig")
    co = t["nganh_chinh"].ne(nl.KHAC)
    log(f"Da luu {nl.TAGGED}: {len(t)} bai, {co.mean() * 100:.1f}% co nganh · {len(g)} cap bai x nganh")
    d7 = t[t["ngay_gio"] >= pd.Timestamp(now) - pd.Timedelta(days=7)]
    if len(d7):
        top = (g[g["id"].isin(set(d7["id"]))].groupby("nganh").size().sort_values(ascending=False))
        log("Tong 7 ngay theo nganh: " + " · ".join(f"{k} {v}" for k, v in top.items()))


if __name__ == "__main__":
    main()
