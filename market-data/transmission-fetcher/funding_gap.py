# -*- coding: utf-8 -*-
"""Chenh cho vay - tien gui cua 27 NH niem yet duoc BU BANG NGUON NAO (tu FS Extractor).

    python funding_gap.py                # in bang luy ke + theo nhom + theo NH
    python funding_gap.py --base 2023-Q4

Doc D:/bctc/fs-extractor/output/balance_sheet.csv (chi dong ngan hang, ~78k dong), cache o _bank_bs.csv.
Gap = d(cho vay KH) - d(tien gui KH). Nguon bu: vay rong lien NH (vay - gui), GTCG phat hanh,
no Chinh phu & NHNN, no khac, von chu so huu. Chung khoan dau tu la DUNG von, in de doi chieu.
BAY: VCI dung lai item_id cho dong tong va dong thuyet minh -> drop_duplicates keep first.
"""
from __future__ import annotations

import argparse
import os
import sys
import unicodedata

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.normpath(os.environ.get("BCTC_ROOT", "D:/bctc")), "fs-extractor", "output", "balance_sheet.csv")
CACHE = os.path.join(ROOT, "_bank_bs.csv")
ITEMS = {"loan": "loans_and_advances_to_customers", "sec": "investment_securities",
         "ib_a": "placements_with_and_loans_to_other_credit_institutions",
         "dep": "deposits_from_customers", "ib_l": "deposits_and_loans_from_other_credit_institutions",
         "gtcg": "convertible_bonds_cds_and_other_valuable_papers_issued",
         "gov": "due_to_gov_and_loans_from_sbv", "oth_l": "other_liabilities", "equity": "owners_equity"}
SRC_LAB = [("ib_net", "vay rong lien NH"), ("gtcg", "GTCG phat hanh"), ("gov", "no CP & NHNN"),
           ("oth_l", "no khac"), ("equity", "von chu so huu")]
SOE = {"VCB", "CTG", "BID"}


def _norm(s):
    s = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").replace("đ", "d").lower().strip()


def load() -> pd.DataFrame:
    if not os.path.exists(CACHE) or os.path.getmtime(CACHE) < os.path.getmtime(SRC):
        use = ["ticker", "nganh_L2", "item", "item_en", "item_id", "period", "value"]
        fr = [ch[ch["nganh_L2"].map(_norm) == "ngan hang"]
              for ch in pd.read_csv(SRC, usecols=use, chunksize=1_000_000)]
        pd.concat(fr).to_csv(CACHE, index=False)
    bs = pd.read_csv(CACHE).drop_duplicates(["ticker", "period", "item_id"], keep="first")
    p = bs[bs.item_id.isin(ITEMS.values())].pivot_table(index=["period", "ticker"], columns="item_id",
                                                        values="value", aggfunc="first")
    return p.rename(columns={v: k for k, v in ITEMS.items()}) / 1e12        # nghin ty


def report(p: pd.DataFrame, base: str, sel=None, title="27 NH niem yet"):
    q = p if sel is None else p[[sel(t) for t in p.index.get_level_values(1)]]
    a = q.groupby("period").sum()
    a["ib_net"] = a.ib_l - a.ib_a
    last = a.index[-1]
    c = a.loc[last] - a.loc[base]
    gap = c["loan"] - c["dep"]
    print(f"\n=== {title}: {base} -> {last} (nghin ty) | cho vay +{c['loan']:.0f}, tien gui +{c['dep']:.0f}, "
          f"GAP {gap:.0f} | LDR {a.loc[last, 'loan'] / a.loc[last, 'dep'] * 100:.0f}%")
    for k, lab in SRC_LAB:
        print(f"  {lab:18s} {c[k]:7.0f}  {c[k] / gap * 100:5.0f}% gap")
    print(f"  {'(CK dau tu, dung von)':18s} {c['sec']:7.0f}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pd.set_option("display.width", 250)
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="2024-Q4")
    args = ap.parse_args()
    p = load()
    report(p, args.base)
    report(p, args.base, lambda t: t in SOE, "Quoc doanh VCB CTG BID")
    report(p, args.base, lambda t: t not in SOE, "Co phan")
    last = p.index.get_level_values(0).max()
    x = p.xs(last, level=0).copy()
    x["src"] = x.dep + x.ib_l + x.gtcg + x.gov
    out = pd.DataFrame({"ldr": x.loan / x.dep * 100, "gtcg%": x.gtcg / x.src * 100,
                        "gov%": x.gov / x.src * 100, "ib_net%": (x.ib_l - x.ib_a) / x.src * 100})
    print(f"\n=== {last} theo NH: LDR va ty trong tren tong nguon (tien gui + lien NH + GTCG + NHNN) ===")
    print(out.round(0).sort_values("ldr", ascending=False).to_string())


if __name__ == "__main__":
    main()
