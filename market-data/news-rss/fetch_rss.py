# -*- coding: utf-8 -*-
r"""fetch_rss.py - keo tin RSS bao kinh te VN -> news_master + phan loai theo nganh (11/11/2026).

    python fetch_rss.py                 keo tat ca feed bat=1 trong config\feeds.csv, gop vao kho, phan loai bai moi
    python fetch_rss.py --no-fetch      chi phan loai lai (sau khi sua config\keywords.csv / alias_ma.csv -> tu phan loai lai toan bo)
    python fetch_rss.py --reclass       ep phan loai lai toan bo lich su
    python fetch_rss.py --only CafeF,Vietstock

Dau ra (kho = cache app <app>\cache\news-rss, doi bang --data / env NEWS_DATA):
    news_master.parquet   1 dong = 1 bai (id = sha1 url chuan): ngay_gio (gio VN), nguon, chuyen_muc, goi_y, tieu_de, tom_tat, url, lay_luc
    news_tagged.parquet   master + nganh_chinh, nganh (|), chu_de (|), ma (|), loai_tin (|), diem, diem_chu_y, tu_khoa, nhom_trung, so_nguon
    news_tags.parquet     long id x nganh (diem, chu_de, tu_khoa) -> app chon nganh la sap tin theo diem / ngay
    feed_status.csv       trang thai tung feed lan chay cuoi
11/11/2026 (PV2): KHONG con kho dung san / lich chay rieng - app goi run() khi mo trang Tin tuc › Tin theo nganh (kho trong cache app,
tu lam moi sau TTL, gop don bai moi, xoa bai qua keep_days ngay; doi tu dien -> phan loai lai). RSS chi giu 20-100 bai moi nhat
moi chuyen muc nen lich su = cac lan mo app; CLI van chay tay duoc tren cung kho.
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


def merge_master(new: pd.DataFrame, keep_days: int | None = None) -> tuple[pd.DataFrame, int]:
    old = pd.read_parquet(nl.MASTER) if os.path.exists(nl.MASTER) else pd.DataFrame(columns=MASTER_COLS)
    if new.empty:
        return old, 0
    allx = pd.concat([x for x in (old, new) if len(x)], ignore_index=True)
    if keep_days:                                                     # xoa bai cu (VietnamNet RSS tra ca bai tu 2022)
        allx = allx[allx["ngay_gio"] >= allx["lay_luc"].max() - pd.Timedelta(days=keep_days)]
    # 1 bai xuat hien o nhieu chuyen muc / nhieu lan keo: giu ban dau tien (ngay_gio som nhat), gop chuyen_muc + goi_y
    agg = allx.groupby("id", sort=False).agg(chuyen_muc=("chuyen_muc", _gop_chuoi), goi_y=("goi_y", _gop_chuoi))
    first = allx.sort_values(["ngay_gio", "lay_luc"]).drop_duplicates("id", keep="first").set_index("id")
    first["chuyen_muc"], first["goi_y"] = agg["chuyen_muc"], agg["goi_y"]
    out = first.reset_index()[MASTER_COLS].sort_values("ngay_gio", ascending=False).reset_index(drop=True)
    moi = len(set(out["id"]) - set(old["id"])) if len(old) else len(out)
    return out, moi


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
    if os.path.exists(nl.STATE):
        try:
            st = json.load(open(nl.STATE, encoding="utf-8"))
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
    json.dump({"hash": h, "luc": datetime.now().isoformat(timespec="seconds")}, open(nl.STATE, "w", encoding="utf-8"))
    return t, g, len(todo)


def run(fetch: bool = True, reclass: bool = False, only: str = "", workers: int = 12, keep_days: int | None = None) -> dict:
    """Keo RSS (fetch) -> gop kho -> phan loai bai moi (hoac toan bo neu doi tu dien / reclass) -> ghi parquet. Tra tom tat.
    Goi tu app (pages_tin) va CLI. Loi toan bo feed -> RuntimeError (kho cu giu nguyen)."""
    os.makedirs(nl.DATA, exist_ok=True)
    now = datetime.now(nl.VN_TZ).replace(tzinfo=None, microsecond=0)
    kq = {"luc": now, "doc": 0, "moi": 0, "feed_loi": 0, "so_feed": 0}
    if fetch:
        feeds = nl.read_cfg("feeds.csv")
        feeds = feeds[feeds["bat"].str.strip() != "0"]
        if only:
            ok = {x.strip().lower() for x in only.split(",")}
            feeds = feeds[feeds["nguon"].str.lower().isin(ok)]
        log(f"Che do: keo {len(feeds)} feed RSS ({feeds['nguon'].nunique()} bao)")
        rows, sts = [], []
        with cf.ThreadPoolExecutor(workers) as ex:
            for out, st in ex.map(lambda r: fetch_one(r, now), feeds.itertuples(index=False)):
                rows += out
                sts.append(st)
                if st["loi"]:
                    log(f"  ! {st['nguon']} / {st['chuyen_muc']}: {st['loi']}")
        sts = pd.DataFrame(sts)
        loi = int((sts["loi"] != "").sum()) if len(sts) else 0
        if len(sts) and loi == len(sts):
            raise RuntimeError("khong feed RSS nao doc duoc (mat mang?)")
        sts.to_csv(nl.FEED_STATUS, index=False, encoding="utf-8-sig")
        new = pd.DataFrame(rows, columns=MASTER_COLS)
        master, n_moi = merge_master(new, keep_days)
        master.to_parquet(nl.MASTER, index=False)
        kq.update(doc=len(new), moi=n_moi, feed_loi=loi, so_feed=len(sts))
        log(f"-> {len(new)} bai doc duoc, {n_moi} bai MOI · kho {len(master)} bai · feed loi {loi}/{len(sts)}")
    else:
        if not os.path.exists(nl.MASTER):
            raise RuntimeError("chua co news_master.parquet")
        master = pd.read_parquet(nl.MASTER)
    t, g, n = classify(master, reclass)
    # tom tat cat 400 ky tu cho app (ban day du o news_master) + danh sach nganh (thu tu hien thi)
    t.assign(tom_tat=t["tom_tat"].str.slice(0, 400)).to_parquet(nl.TAGGED, index=False)
    g.to_parquet(nl.TAGS, index=False)
    nl.danh_sach_nganh()[["ma", "nganh", "loai", "thu_tu", "mo_ta"]].to_csv(os.path.join(nl.DATA, "nganh.csv"), index=False,
                                                                            encoding="utf-8-sig")
    co = t["nganh_chinh"].ne(nl.KHAC)
    kq.update(tong=len(t), phan_loai=n, ty_le=float(co.mean()) if len(t) else 0.0)
    log(f"Da luu {nl.TAGGED}: {len(t)} bai, {kq['ty_le'] * 100:.1f}% co nganh · {len(g)} cap bai x nganh")
    return kq


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--reclass", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--keep-days", type=int, default=0, help="xoa bai cu hon N ngay (0 = giu het)")
    ap.add_argument("--data", default="", help=r"thu muc kho (mac dinh = kho cua app <app>\cache\news-rss, hoac env NEWS_DATA)")
    a = ap.parse_args()
    if a.data:
        nl.set_data_dir(a.data)
    try:
        run(not a.no_fetch, a.reclass, a.only, a.workers, a.keep_days or None)
    except RuntimeError as e:
        log(f"X LOI: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
