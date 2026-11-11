# -*- coding: utf-8 -*-
r"""danh_sach_nganh.py - liet ke CAC DANH SACH NGANH dang dung trong he thong Market Data -> output\danh_sach_nganh.xlsx (11/11/2026).

Sheet:
  Nganh_phan_loai_tin  23 nganh dung de phan loai tin (config\nganh.csv) + so ma CK, so tu khoa, so tin 7/30 ngay
  ICB_Vietcap          cay ICB 4 cap (index-fetcher\raw\vn_icb_vci.csv): cap1 > cap2 > cap3 > cap4, so ma, ma vi du
  Nhom_TradingView     nhom nganh kieu chart-pack / three_month (datalib.nhom_nganh, theo sector/industry TradingView)
  Nganh_TPDN           9 nganh trai phieu kieu VBMA (bond-pivot classify_issuers.py, datalib.NGANH_TP)
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdlib import log, setup_stdout  # noqa: E402

import newslib as nl  # noqa: E402

NHOM_TV = ["Vingroup", "Ngân hàng", "Chứng khoán", "BĐS (ngoài Vin)", "Thép", "Tài chính khác", "Tiêu dùng, bán lẻ", "Điện, dầu khí",
           "Công nghệ, viễn thông", "Công nghiệp, vật liệu", "Vận tải, cảng, HK", "Khác"]
NGANH_TP = ["Ngân hàng", "Bất động sản", "Xây dựng", "Tài chính", "Chứng khoán", "Tiêu dùng", "Công nghiệp", "Năng lượng",
            "Lĩnh vực khác", "Chưa phân loại"]


def main():
    setup_stdout()
    icb = pd.read_csv(nl.ICB_CSV, dtype=str)
    ng = nl.danh_sach_nganh()
    kw = nl.read_cfg("keywords.csv")
    so_kw = kw.groupby("ma").size()
    so_ma = icb.groupby("icb2")["code"].nunique()
    ng["so_ma_CK"] = ng["nganh"].map(so_ma).fillna(0).astype(int)
    ng.loc[ng["ma"] == "VIN", "so_ma_CK"] = len(nl.VIN)
    ng["so_tu_khoa"] = ng["ma"].map(so_kw).fillna(0).astype(int)
    ng["chu_de_con"] = ng["ma"].map(kw.groupby("ma")["chu_de"].apply(lambda s: " · ".join(dict.fromkeys(s))))
    if os.path.exists(nl.TAGS):
        t = pd.read_parquet(nl.TAGGED, columns=["id", "ngay_gio"])
        g = pd.read_parquet(nl.TAGS).merge(t, on="id")
        end = t["ngay_gio"].max()
        for d in (7, 30):
            ng[f"so_tin_{d}_ngay"] = ng["nganh"].map(g[g["ngay_gio"] >= end - pd.Timedelta(days=d)].groupby("nganh").size()).fillna(0).astype(int)
    tree = (icb.groupby(["icb1", "icb2", "icb3", "icb4"])["code"]
            .agg(so_ma="nunique", ma_vi_du=lambda s: ", ".join(sorted(s)[:12])).reset_index())
    out = os.path.join(nl.OUT, "danh_sach_nganh.xlsx")
    os.makedirs(nl.OUT, exist_ok=True)
    with pd.ExcelWriter(out) as w:
        ng.to_excel(w, "Nganh_phan_loai_tin", index=False)
        tree.to_excel(w, "ICB_Vietcap", index=False)
        pd.DataFrame({"nhom": NHOM_TV, "nguon": "datalib.nhom_nganh (TradingView sector/industry)"}).to_excel(w, "Nhom_TradingView", index=False)
        pd.DataFrame({"nganh": NGANH_TP, "nguon": "bond-pivot classify_issuers.py (VBMA)"}).to_excel(w, "Nganh_TPDN", index=False)
    log(f"Da luu {out}: {len(ng)} nganh phan loai tin · ICB {icb['icb1'].nunique()}/{icb['icb2'].nunique()}/{icb['icb3'].nunique()}/"
        f"{icb['icb4'].nunique()} nhom cap 1/2/3/4 · {icb['code'].nunique()} ma")


if __name__ == "__main__":
    main()
