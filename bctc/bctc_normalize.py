# -*- coding: utf-8 -*-
r"""bctc_normalize.py — DUA 4 NGUON BCTC VE MOT SCHEMA (cum D:\bctc, gop 14/09/2026).

4 tool trong D:\bctc tao facts long-format nhung moi tool mot bo cot / don vi / cach ghi ky:
  fs-extractor\output\*.csv          vnstock/VCI    : ticker,item,item_id,period(2018-Q1),value (VND)          -> 3.5 GB
  fiinprox-unpivot\output\fiinprox_facts_all.csv    : ticker,entity_type,freq,statement_code,metric,period(Q2/2015),value (Ty VND)
  md2bctc\bctc_master.csv            OCR CTCK       : ticker,fiscal_year,period_label,consolidated,statement,ma_so,chi_tieu,period(current/prior),value (VND),quality
  tcbs-pbi\PL_Cheatsheet.csv, BS_Cheatsheet.csv     : Year,Quarter(2020Q1),Measure (VND),Type

Schema chung (COLS):
  ticker | source (fs|fiinprox|md|tcbs) | entity (HN=hop nhat, RL=rieng le, ?=khong ro) | statement (BS|IS|CF|NOTE|RATIO|OTHER)
  | item_id | item | period (YYYY-Qn hoac YYYY-FY) | value (VND, ratio giu nguyen) | quality (clean|dirty|na)

Dung:
  python bctc_normalize.py HAH GMD --out bctc_HAH_GMD.csv          # loc theo ma, gop 4 nguon
  python bctc_normalize.py SSI --source md,fiinprox                 # chi 1-2 nguon
  from bctc_normalize import load_all; df = load_all(["HAH"])       # trong Python
Luu y: md2bctc chi lay cot 'current' (cot 'prior' cua BCTC quy khong xac dinh la ky truoc hay dau nam);
       fs-extractor doc theo chunk 1 trieu dong vi file lon; tcbs chi co 1 cong ty (TCBS), khong loc theo ma.
"""
import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FS_DIR = os.path.join(HERE, "fs-extractor", "output")
FIIN = os.path.join(HERE, "fiinprox-unpivot", "output", "fiinprox_facts_all.csv")
MD = os.path.join(HERE, "md2bctc", "bctc_master.csv")
TCBS_DIR = os.path.join(HERE, "tcbs-pbi")
COLS = ["ticker", "source", "entity", "statement", "item_id", "item", "period", "value", "quality"]
FS_STMT = {"balance_sheet": "BS", "income_statement": "IS", "cash_flow": "CF", "note": "NOTE", "ratio": "RATIO"}
MD_STMT = {"balance_sheet": "BS", "income_statement": "IS", "cash_flow": "CF", "cash_flow_indirect": "CF",
           "cash_flow_direct": "CF"}
FIIN_STMT = {"BS": "BS", "IS": "IS", "CF": "CF", "CFI": "CF", "CFD": "CF", "NOTE": "NOTE"}


def _finish(df):
    df = df.reindex(columns=COLS)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"]).reset_index(drop=True)


def load_fs(tickers=None, statements=None, chunksize=1_000_000):
    """fs-extractor: 5 file lon -> doc chunk, loc ma. statements: list trong FS_STMT (mac dinh tat ca)."""
    out = []
    tk = set(t.upper() for t in tickers) if tickers else None
    for name, code in FS_STMT.items():
        if statements and code not in statements:
            continue
        path = os.path.join(FS_DIR, name + ".csv")
        if not os.path.exists(path):
            continue
        for ch in pd.read_csv(path, usecols=["ticker", "item", "item_id", "period", "value"], chunksize=chunksize,
                              encoding="utf-8-sig", dtype={"period": str}):
            if tk is not None:
                ch = ch[ch["ticker"].isin(tk)]
            if ch.empty:
                continue
            ch = ch.assign(source="fs", entity="HN", statement=code, quality="na")
            out.append(ch)
    if not out:
        return pd.DataFrame(columns=COLS)
    return _finish(pd.concat(out, ignore_index=True))


def load_fiinprox(tickers=None):
    if not os.path.exists(FIIN):
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(FIIN, encoding="utf-8-sig", dtype={"period": str},
                     usecols=["ticker", "entity_type", "freq", "statement_code", "metric", "row_order", "year",
                              "quarter", "value", "unit"])
    if tickers:
        df = df[df["ticker"].isin([t.upper() for t in tickers])]
    df = df.copy()
    mult = df["unit"].astype(str).str.contains("Tỷ|Ty", regex=True).map({True: 1e9, False: 1.0})
    df["value"] = pd.to_numeric(df["value"], errors="coerce") * mult
    q = pd.to_numeric(df["quarter"], errors="coerce")
    df["period"] = df["year"].astype("Int64").astype(str) + "-" + \
        q.apply(lambda x: f"Q{int(x)}" if pd.notna(x) and x > 0 else "FY")
    df["entity"] = df["entity_type"].astype(str).map(lambda s: "HN" if "Hợp nhất" in s or "Hop nhat" in s
                                                    else ("RL" if "Riêng" in s or "Rieng" in s else "?"))
    df["statement"] = df["statement_code"].map(FIIN_STMT).fillna("OTHER")
    df["item_id"] = df["statement_code"].astype(str) + "_" + df["row_order"].astype(str)
    df = df.rename(columns={"metric": "item"}).assign(source="fiinprox", quality="na")
    return _finish(df)


def load_md(tickers=None):
    """md2bctc: chi cot 'current'. period = fiscal_year + period_label (Q1..Q4/FY)."""
    if not os.path.exists(MD):
        return pd.DataFrame(columns=COLS)
    df = pd.read_csv(MD, encoding="utf-8-sig", dtype=str,
                     usecols=["ticker", "fiscal_year", "period_label", "consolidated", "statement", "ma_so", "chi_tieu",
                              "period", "value", "quality"])
    if tickers:
        df = df[df["ticker"].isin([t.upper() for t in tickers])]
    df = df[df["period"] == "current"].copy()
    lab = df["period_label"].astype(str).str.upper().str.replace("QUY", "Q", regex=False)
    df["period"] = df["fiscal_year"].astype(str) + "-" + lab.where(lab.str.match(r"^Q[1-4]$"), "FY")
    df["entity"] = df["consolidated"].map({"Y": "HN", "N": "RL"}).fillna("?")
    df["statement"] = df["statement"].map(MD_STMT).fillna("OTHER")
    df = df.rename(columns={"ma_so": "item_id", "chi_tieu": "item"}).assign(source="md")
    df["quality"] = df["quality"].fillna("na")
    return _finish(df)


def load_tcbs():
    """TCBS (Power BI): PL_Cheatsheet + BS_Cheatsheet quy, Measure = VND."""
    out = []
    for fn, code in (("PL_Cheatsheet.csv", "IS"), ("BS_Cheatsheet.csv", "BS")):
        path = os.path.join(TCBS_DIR, fn)
        if not os.path.exists(path):
            continue
        df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
        q = df["Quarter"].astype(str).str.extract(r"(\d{4})Q([1-4])")
        df["period"] = q[0] + "-Q" + q[1]
        df["item"] = df["Type_vie2"].fillna(df["Type"]).astype(str).str.strip()
        out.append(df.assign(ticker="TCBS", source="tcbs", entity="RL", statement=code, quality="na",
                             item_id=df["Type"], value=pd.to_numeric(df["Measure"], errors="coerce")))
    if not out:
        return pd.DataFrame(columns=COLS)
    return _finish(pd.concat(out, ignore_index=True))


def load_all(tickers=None, sources=("fs", "fiinprox", "md", "tcbs")):
    parts = []
    if "fs" in sources:
        parts.append(load_fs(tickers))
    if "fiinprox" in sources:
        parts.append(load_fiinprox(tickers))
    if "md" in sources:
        parts.append(load_md(tickers))
    if "tcbs" in sources and (not tickers or "TCBS" in [t.upper() for t in tickers]):
        parts.append(load_tcbs())
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame(columns=COLS)
    return pd.concat(parts, ignore_index=True).sort_values(["ticker", "source", "statement", "period", "item_id"]).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser(description="Gop BCTC 4 nguon ve 1 schema")
    ap.add_argument("tickers", nargs="*", help="Ma CK (trong = tat ca; CAN THAN: fs-extractor 3.5 GB)")
    ap.add_argument("--source", default="fs,fiinprox,md,tcbs", help="fs,fiinprox,md,tcbs")
    ap.add_argument("--out", default=None, help="CSV ra (mac dinh bctc_<ma>.csv canh script)")
    a = ap.parse_args()
    srcs = tuple(s.strip() for s in a.source.split(","))
    df = load_all(a.tickers or None, srcs)
    out = a.out or os.path.join(HERE, "bctc_" + ("_".join(t.upper() for t in a.tickers) if a.tickers else "all") + ".csv")
    df.to_csv(out, index=False, encoding="utf-8-sig")
    print(f"-> {out}: {len(df)} dong | nguon: {df['source'].value_counts().to_dict() if len(df) else {}}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
