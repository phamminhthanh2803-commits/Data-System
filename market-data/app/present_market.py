# -*- coding: utf-8 -*-
r"""
present_market.py - DUNG SAN du lieu trinh bay cho app Market Data (21/10/2026, chong "Error running app" het RAM ~1 GB tren
Streamlit Community Cloud). Giong port-tracker\present.py: pipeline tinh nang 1 lan, app chi doc parquet nho.

Buoc md-present (run_slot.py, cuoi Market AM / PM / EOD) ghi <MD_ROOT>\present\ (Drive: gdrive:pipeline-data/market-data/present):
  px.parquet            ma tran gia dieu chinh (ffill 20 phien) toan bo co phieu VN tu 2015 (ngay x ma, ~27 MB RAM)
                        -> hieu suat nganh/ma, chi so nganh, von hoa nhom, heatmap, phien gan nhat (app tinh tu ma tran nay)
  breadth.parquet       do rong thi truong (datalib.breadth, tu 2015)
  turnover_est.parquet  GTGD uoc tinh close x KL theo san (bu phien VCI chua co trong datalib.turnover)
  tv-live.parquet       bang gia ghep tv-history + stock_daily live-first (= datalib.tv(); trang Kho du lieu doc theo ma)
  tv-ohlc-vn.parquet    OHLCV VN tu tv-history.csv (nen 1 ma / VNMidcap / VNSmallcap, doc bang bo loc pyarrow)
  fs.parquet            khoi ngoai theo ma (Vietcap + VNDirect bu, cot san), SAP THEO NGAY, row group 100k dong
                        -> app doc dung ky can (bo loc pyarrow) thay vi giu 5 trieu dong (~360 MB) thuong tru
  fs_san_vnd.parquet    san theo VNDirect (gan san cho phan live-first sau pipeline)
  meta.json             gio dung + chu ky file goc tung phan (app tren may co file goc: chu ky khac -> tinh nhu cu)

App: datalib.present_on('px'|'fs') -> doc ban dung san; khong co / khong hop le -> tinh tu file goc nhu truoc.

    python present_market.py                       # dung ca 2 phan vao <MD_ROOT>\present
    python present_market.py --only fs --out D:\tmp\present
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time

APP_DIR = os.path.dirname(os.path.abspath(__file__))


def _env() -> str:
    """Env truoc khi import datalib: tat ban dung san (dung tu file goc), tat thread nen, cache nguon live-first + cache build rieng."""
    os.environ["MD_PRESENT_OFF"] = "1"
    os.environ["APP_NO_BG"] = "1"
    os.environ.setdefault("VNSTOCK_DISABLE_AGENT_SETUP", "1")
    md = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))
    if not os.environ.get("SRC_CACHE"):                # runner AM/PM: sync_data keo app-cache/src ve <MD_ROOT>/app-cache/src
        cand = os.path.join(md, "app-cache", "src")
        if os.path.isdir(cand):
            os.environ["SRC_CACHE"] = cand
    build = tempfile.mkdtemp(prefix="md_present_build_")   # parquet trung gian (tv-live...) - khong dung cache cua app dang chay
    os.environ["APP_CACHE"] = build
    return build


def _w_parquet(df, path: str, **kw) -> int:
    df.to_parquet(path, compression="snappy", **kw)
    return os.path.getsize(path)


def build_px(dl, dx, tmp: str) -> dict:
    """Phan gia: ma tran px, do rong, GTGD uoc, tv-live, OHLC VN."""
    t0 = time.time()
    sig = dl.present_sig("px")
    csv = dl.REGISTRY["tv_history"][2]
    if not os.path.exists(csv):
        raise FileNotFoundError(f"thieu {csv}")
    mt = dl._mtime(csv)
    t = dl.tv()                                         # live-first: dung CACHE/tv-live.parquet; khong: CACHE/tv-history.parquet
    tv_last, tv_rows = str(t.date.max().date()), int(len(t))
    del t
    live = os.path.join(dl.CACHE, "tv-live.parquet")
    srcp = live if dl.live_first("tv_history") and os.path.exists(live) else os.path.join(dl.CACHE, "tv-history.parquet")
    shutil.copyfile(srcp, os.path.join(tmp, "tv-live.parquet"))
    px_raw, px, val = dl._price_matrix_full(mt)
    pxw = px.set_axis(px.columns.astype(str), axis=1)    # cot CategoricalIndex khong ghi duoc vao parquet -> chuoi (app dung lai)
    sizes = {"px.parquet": _w_parquet(pxw, os.path.join(tmp, "px.parquet"))}
    del pxw
    br = dl.breadth(mt, "2015-01-01")
    sizes["breadth.parquet"] = _w_parquet(br, os.path.join(tmp, "breadth.parquet"))
    est = dl.turnover_est()
    sizes["turnover_est.parquet"] = _w_parquet(est, os.path.join(tmp, "turnover_est.parquet"))
    dl.tv_csv_to_parquet(csv, os.path.join(tmp, "tv-ohlc-vn.parquet"), dx.OHLC_COLS, only_vn=True)
    for f in ("tv-live.parquet", "tv-ohlc-vn.parquet"):
        sizes[f] = os.path.getsize(os.path.join(tmp, f))
    print(f"-> px {px.shape[0]} phien x {px.shape[1]} ma ({px.index.min():%d/%m/%Y} - {px.index.max():%d/%m/%Y}) · "
          f"breadth {len(br)} · GTGD uoc {len(est)} · tv {tv_rows:,} dong den {tv_last} · {time.time() - t0:.0f} s", flush=True)
    return {"sig": sig, "tv_last": tv_last, "tv_rows": tv_rows, "px_shape": list(px.shape),
            "px_end": str(px.index.max().date()), "live_first": bool(dl.live_first("tv_history")), "sizes": sizes}


def build_fs(dl, tmp: str) -> dict:
    """Phan khoi ngoai theo ma: fs.parquet (sap theo ngay) + san VNDirect + ngay cuoi pipeline."""
    import pyarrow as pa
    import pyarrow.parquet as ppq
    import pandas as pd
    t0 = time.time()
    sig = dl.present_sig("fs")
    tables, end, san_vnd = dl.fs_pipeline_tables()
    if not tables:
        raise FileNotFoundError(f"thieu khoi ngoai theo ma ({dl.FS_VCI})")
    d = dl.fs_to_pandas(tables, san_vnd)
    d = d.sort_values(["date", "code"], kind="stable").reset_index(drop=True)
    schema = pa.schema([("code", pa.string()), ("date", pa.timestamp("ns"))] + [(c, pa.float32()) for c in dl.FS_VALS]
                       + [("floor", pa.dictionary(pa.int8(), pa.string()))])
    tb = pa.Table.from_pandas(d, schema=schema, preserve_index=False)
    p = os.path.join(tmp, "fs.parquet")
    ppq.write_table(tb, p, compression="snappy", row_group_size=100_000)
    rows, d0, d1 = len(d), d.date.min(), d.date.max()
    del d, tb
    sv = pd.DataFrame({"code": san_vnd.index.astype(str), "floor": san_vnd.astype(str).values})
    _w_parquet(sv, os.path.join(tmp, "fs_san_vnd.parquet"), index=False)
    sizes = {f: os.path.getsize(os.path.join(tmp, f)) for f in ("fs.parquet", "fs_san_vnd.parquet")}
    print(f"-> fs {rows:,} dong ({d0:%d/%m/%Y} - {d1:%d/%m/%Y}), pipeline den {end:%d/%m/%Y} · {len(sv)} ma san VND · "
          f"{sizes['fs.parquet'] / 1e6:.0f} MB · {time.time() - t0:.0f} s", flush=True)
    return {"sig": sig, "pipe_end": str(end.date()), "rows": rows, "sizes": sizes}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dung san du lieu trinh bay cho app Market Data -> <MD_ROOT>/present")
    ap.add_argument("--out", default="", help="thu muc ra (mac dinh env MD_PRESENT hoac <MD_ROOT>/present)")
    ap.add_argument("--only", default="px,fs", help="px,fs")
    a = ap.parse_args(argv)
    build = _env()
    sys.path.insert(0, APP_DIR)
    import warnings
    warnings.filterwarnings("ignore")
    import logging
    logging.getLogger("streamlit").setLevel(logging.ERROR)
    import datalib as dl  # noqa: E402
    import data_ext as dx  # noqa: E402
    out = os.path.normpath(a.out or dl.PRESENT)
    os.makedirs(out, exist_ok=True)
    tmp = os.path.join(out, ".tmp-build")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp)
    parts = [x.strip() for x in a.only.split(",") if x.strip()]
    print(f"Che do: dung san {', '.join(parts)} -> {out} (MD_ROOT {dl.BASE}, SRC_CACHE {os.environ.get('SRC_CACHE', '(app)')})",
          flush=True)
    old = {}
    try:
        with open(os.path.join(out, "meta.json"), encoding="utf-8") as f:
            old = json.load(f)
    except Exception:  # noqa: BLE001
        pass
    meta = {"built": time.time(), "built_at": time.strftime("%Y-%m-%d %H:%M:%S"), "parts": dict(old.get("parts") or {})}
    bad = 0
    for p in parts:
        try:
            meta["parts"][p] = build_px(dl, dx, tmp) if p == "px" else build_fs(dl, tmp)
        except Exception as e:  # noqa: BLE001 - 1 phan loi thi giu ban cu cua phan do
            bad += 1
            print(f"! LOI {p}: {type(e).__name__}: {str(e)[:300]}", flush=True)
            continue
        for f in dl.PRESENT_FILES[p]:                  # thay tung file (meta.json ghi SAU CUNG -> app khong thay ban nua voi)
            os.replace(os.path.join(tmp, f), os.path.join(out, f))
    if bad == len(parts):
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(build, ignore_errors=True)
        return 1
    with open(os.path.join(tmp, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    os.replace(os.path.join(tmp, "meta.json"), os.path.join(out, "meta.json"))
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.rmtree(build, ignore_errors=True)
    tot = sum(os.path.getsize(os.path.join(out, f)) for f in os.listdir(out) if os.path.isfile(os.path.join(out, f)))
    print(f"Da luu {out}: {tot / 1e6:.0f} MB · {meta['built_at']}" + (f" · {bad} phan LOI" if bad else ""), flush=True)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
