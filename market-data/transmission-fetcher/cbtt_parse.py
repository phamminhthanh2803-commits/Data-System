# -*- coding: utf-8 -*-
"""Doc bang TY LE AN TOAN VON tu cac ban CBTT (Thong tu 41, Phu luc 05) cua tung ngan hang.

Dau vao : cbtt/<TICKER>/<TICKER>-CAR-<yyyy-mm-dd>.md  (pdf2md.py sinh ra tu PDF)
Dau ra  : cbtt/car_bank.csv  (long: ticker, date, scope, metric, value, conf, file)
          --merge -> transmission-master.csv, series car_<ticker> (hop nhat, thieu thi rieng le)

Moi ngan hang mot bo cuc, nhung deu xoay quanh 3 thu:
  * mot dong nhan "Ty le an toan von" (khong phai "cap 1") kem 2-4 so %
  * mot dong tieu de cot "Rieng le ... Hop nhat" o phia tren (thu tu + so cot)
  * mot dong ngay dd/mm/yyyy o phia tren (ky hien tai, ky truoc) - khong co thi lay tu ten file
Bo cuc dang KHOI (VIB): "Bao cao hop nhat" ... "Ty le an toan von 12.15% 11.97%" -> 2 so = ky nay, ky truoc.
Bo cuc dang CHENH (OCB): 3 so = ky nay, ky truoc, chenh -> bo so thu 3.

PDF scan (ACB, CTG, STB, NAB) OCR ra chu mat dau ("Ty le an toan von", "Tyl@antoanvén"): so khop
sau khi BO DAU va bo ky tu la; so % mat dau phay ("1182%") thi doan la 11.82 va danh dau conf=low.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
import unicodedata

import pandas as pd

from common import MASTER, log, merge_master, row, setup_stdout

ROOT = os.path.dirname(os.path.abspath(__file__))
CBTT = os.path.join(ROOT, "cbtt")
OUT = os.path.join(CBTT, "car_bank.csv")

N_ROOM = ("N10", "Room va chi phi von NH")


def _norm(s: str) -> str:
    """bo dau + thuong + gop khoang trang; giu chu so, %, dau cham/phay."""
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = s.replace("đ", "d").replace("Đ", "D").lower()
    return re.sub(r"\s+", " ", s).strip()


def _squash(s: str) -> str:
    """chi giu a-z de so khop nhan bi OCR pha ("tyl@antoanvén" -> "tylantoanvn")."""
    return re.sub(r"[^a-z]", "", _norm(s))


# --- nhan dang dong ----------------------------------------------------------------
PCT = re.compile(r"(\(?-?\d{1,3}[.,]\d{1,2}\)?\s*%)")                  # 12,46% | 12.46% | (0.02%)
PCT_OCR = re.compile(r"(?<![\d.,*])(\d{3,4})\s*%")                       # OCR mat dau phay: 1182%
DEC = re.compile(r"(?<![\d.,/*A-Za-z])(\d{1,2}[.,]\d{1,2})(?![\d%])")   # 13.09 trong bang markdown khong co %
DATE = re.compile(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})")
LABEL = re.compile(r"tyl?e?antoan[vy][a-z]{0,2}n|capitaladequacyratio|\bcar\b")   # VN, OCR pha, va ban tieng Anh
T1 = re.compile(r"c[aâ]?p1|cp1")


def _strip_formula(s: str) -> str:
    """bo cong thuc trong ngoac + '*100%' de khong nham la so lieu / dem chu."""
    s = re.sub(r"\{[^}]*\}|\[[^\]]*\]|\([A-Za-z][^)]*\)", " ", s)
    return re.sub(r"[x*]\s*100\s*%", " ", s)


def _pct_values(line: str):
    """-> [(value, conf)] cac so % tren dong theo thu tu (gom ca so OCR mat dau phay, giu dung vi tri)."""
    body = _strip_formula(line)
    found = [(m.start(), float(m.group(1).replace("%", "").replace("(", "-").replace(")", "").replace(",", ".")), "ok")
             for m in PCT.finditer(body)]
    found += [(m.start(), int(m.group(1)) / 100.0, "low")
              for m in PCT_OCR.finditer(body) if m.group(1) != "100"]
    out = [(v, c) for _, v, c in sorted(found)]
    if not out and ("|" in line or _is_car_label(line)):
        # bang markdown (TCB) hoac dong "Ty le an toan von: C3 = B2/A5 x 100%  14,26  14,38" (KLB): so khong co %.
        # Chi lay so SAU CHU CAI CUOI CUNG cua dong - bo "2.2." trong tieu de muc va "12,5" trong cong thuc.
        letters = [m.start() for m in re.finditer(r"[A-Za-zÀ-ỹ]", body)]
        tail = body[letters[-1] + 1:] if letters else body
        out = [(float(m.group(1).replace(",", ".")), "ok") for m in DEC.finditer(tail)]
    return out


def _pure_pct_line(line: str):
    """dong CHI co 2-4 so % (bo cuc 2 cot: nhan mot ben, so mot ben) -> [(v, conf)] hoac None."""
    s = line.strip()
    if not s or not re.fullmatch(r"(\(?-?\d{1,3}[.,]\d{1,2}\)?\s*%\s*){2,4}", s):
        return None
    return _pct_values(s)


PROSE = ("toi thieu", "quy dinh", "o muc", "dat muc", "duy tri", "cao hon", "thap hon", "giam so voi",
         "ke tu", "nam thu", "trung binh", "toan ngan hang", "lam tron", "tu ngay", "hieu luc")


def _is_car_label(line: str) -> str | None:
    """'car' | 'car_t1' | None. Chiu duoc OCR mat dau. Bo dong van xuoi noi ve CAR."""
    head = _strip_formula(line.split("%")[0][:110])
    sq = _squash(head)
    n = _norm(head)
    nd = re.sub(r"[^a-z0-9]", "", n)                       # giu chu so de bat "cap1"
    if not LABEL.search(sq) and not re.search(r"\bcar\b", n):
        if re.search(r"tyl?e?v[a-z]{0,2}ncap1", nd):
            return "car_t1"
        return None
    words = len(n.split())
    if "|" not in line and (DATE.search(line) or (any(p in n for p in PROSE) and words > 9) or words > 14):
        return None
    return "car_t1" if re.search(r"cap1|cp1|tier1", nd) else "car"


def _scope_header(line: str):
    """dong tieu de cot -> ['rl','hn',...] theo thu tu xuat hien; None neu khong phai."""
    n = _norm(line)
    pos = [(m.start(), "rl") for m in re.finditer(r"rieng le|separate|standalone|\bbank\b(?!.*consolidat)", n)]
    pos += [(m.start(), "hn") for m in re.finditer(r"hop nhat|consolidated", n)]
    if not pos:
        return None
    return [k for _, k in sorted(pos)]


def _dates(line: str):
    return ["%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
            for m in DATE.finditer(line) if 2000 <= int(m.group(3)) <= 2100]


def parse_file(path: str, ticker: str, file_date: str):
    lines = open(path, encoding="utf-8").read().splitlines()
    recs = []
    for i, line in enumerate(lines):
        metric = _is_car_label(line)
        if not metric:
            continue
        vals = _pct_values(line)
        # VIB: "Ty le an toan von cap 1 10.60% 10.45% Ty le an toan von 12.08% 11.93%" tren MOT dong
        n2 = _norm(line)
        if metric == "car_t1" and n2.count("ty le an toan von") >= 2 and len(vals) == 4:
            recs += _emit(lines, i, ticker, file_date, "car_t1", vals[:2])
            recs += _emit(lines, i, ticker, file_date, "car", vals[2:])
            continue
        if not vals:
            # nhan o dong nay, so o 1-2 dong duoi (bang markdown vo)
            for j in (1, 2):
                if i + j < len(lines) and not _is_car_label(lines[i + j]):
                    vals = _pct_values(lines[i + j])
                    if vals:
                        break
        if not vals and metric == "car" and not re.search(r"\d", re.sub(r"^\s*[\d.]+\s*", "", _strip_formula(line))):
            # Bo cuc SHB: tieu de "2. TY LE AN TOAN VON (CAR)" roi MOI SO MOT DONG, moi khoi 7 so tuyet doi
            # + 2 dong % (ty le cap 1, ty le an toan von); khoi 1 = rieng le, khoi 2 = hop nhat.
            singles = []
            for j in range(i + 1, min(len(lines), i + 45)):
                s = lines[j].strip()
                if re.fullmatch(r"\(?-?\d{1,3}[.,]\d{1,2}\)?\s*%", s):
                    singles.append(float(s.replace("%", "").replace(",", ".").strip("() ")))
                elif _is_car_label(lines[j]):
                    break
            if len(singles) in (2, 4):
                for b, scope in enumerate(("rl", "hn")[: len(singles) // 2]):
                    t1, car = singles[2 * b], singles[2 * b + 1]
                    for mt, v in (("car_t1", t1), ("car", car)):
                        recs.append(dict(ticker=ticker, date=file_date, scope=scope, metric=mt,
                                         value=v, conf="low", file="", line=i + 1))
                continue
        if not vals:
            # bo cuc 2 cot (ABB): cot nhan truoc, cot so sau. Dong "Ty le von cap 1" roi "Ty le an toan von"
            # lien nhau -> dong so % thu nhat / thu hai phia duoi tuong ung.
            order = 0
            k = i - 1
            while k >= 0 and _is_car_label(lines[k]) and not _pct_values(lines[k]):
                order += 1
                k -= 1
            pure = []
            for j in range(i + 1, min(len(lines), i + 60)):
                p = _pure_pct_line(lines[j])
                if p:
                    pure.append(p)
                if len(pure) > order:
                    break
            if len(pure) > order:
                vals = [(v, "low") for v, _ in pure[order]]
        if not vals:
            continue
        recs += _emit(lines, i, ticker, file_date, metric, vals)
    return recs


def _emit(lines, i, ticker, file_date, metric, vals):
    """ghep so voi cot (rl/hn) va ky (ngay) dua vao ngu canh phia tren."""
    scopes, dates, block = None, [], None
    for k in range(i - 1, max(-1, i - 60), -1):
        n = _norm(lines[k])
        sc = _scope_header(lines[k])
        # tieu de KHOI: "Bao cao hop nhat", "Bang 2.a ... rieng le", "Hop nhat:" - chi mot scope tren dong,
        # nam trong 30 dong phia tren -> moi so trong khoi la cua scope do
        if block is None and sc and len(sc) == 1 and i - k <= 30 and len(n.split()) <= 12:
            block = sc[0]
        # tieu de cot that phai co CA HAI "rieng le" va "hop nhat" (van xuoi hay lap "hop nhat" 2 lan)
        nw = len([w for w in n.split() if w not in ("|", "-", "---")])   # bang markdown: bo dau |
        if scopes is None and sc and len(sc) >= 2 and {"rl", "hn"} <= set(sc) and nw <= 14:
            scopes = sc
        if not dates:
            d = _dates(lines[k])
            if d:
                # GIU THU TU TREN TRANG: TCB/VIB ghi ky nay truoc, OCB ghi ky truoc truoc - deu dung
                # theo vi tri cot. BIDV ghi 4 ngay (moi scope 2 ky) -> ghep theo vi tri luon.
                dates = list(dict.fromkeys(d)) if len(d) != 4 else d
        if scopes and dates:
            break
    vals = [v for v in vals]
    # OCB kieu "ky nay, ky truoc, chenh": 3 so, 2 ngay -> bo so chenh
    if len(vals) == 3 and len(dates) >= 2:
        vals = vals[:2]
    out = []
    if len(vals) == 4 and scopes and len(scopes) >= 2:
        if len(dates) == 4 and len(scopes) == 2:
            # BIDV: "Rieng le | Hop nhat", moi scope 2 cot ngay -> scope-major, ngay theo vi tri
            sc, dts = [scopes[0]] * 2 + [scopes[1]] * 2, dates
        else:
            # TCB/VPB: (ky nay: rl, hn) (ky truoc: rl, hn) - date-major theo thu tu header
            sc = (scopes + scopes)[:4] if len(scopes) == 2 else scopes[:4]
            dts = [dates[0], dates[0], dates[1], dates[1]] if len(dates) >= 2 else [file_date] * 2 + [None] * 2
        for (v, conf), s, d in zip(vals, sc, dts):
            if d:
                out.append((d, s, v, conf))
    elif len(vals) == 2 and block:
        # khoi VIB: 2 so = ky nay, ky truoc cua CUNG scope
        dts = dates[:2] if len(dates) >= 2 else [file_date, None]
        for (v, conf), d in zip(vals, dts):
            if d:
                out.append((d, block, v, conf))
    elif len(vals) == 2 and scopes and len(scopes) >= 2:
        # 2 so = rl, hn cua ky nay
        for (v, conf), s in zip(vals, scopes[:2]):
            out.append((file_date, s, v, conf))
    elif len(vals) == 2:
        # 2 so, khong co tieu de cot doc duoc (OCR mat) -> mau Phu luc 05 TT41 la "Rieng le | Hop nhat"
        for (v, conf), s in zip(vals, ("rl", "hn")):
            out.append((file_date, s, v, "low"))
    elif len(vals) == 1 and len(_norm(lines[i]).split()) <= 9:
        # mot so tren dong ngan kieu bang (khong phai van xuoi ke chuyen)
        out.append((file_date, block or "hn", vals[0][0], "low"))
    return [dict(ticker=ticker, date=d, scope=s, metric=metric, value=v, conf=c,
                 file=os.path.basename(lines and "" or "") or "", line=i + 1)
            for d, s, v, c in out]


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--merge", action="store_true", help="gop car_<ticker> vao master")
    ap.add_argument("--only", default="", help="chi mot ticker")
    args = ap.parse_args()

    recs = []
    for path in sorted(glob.glob(os.path.join(CBTT, "*", "*.md"))):
        if os.path.basename(os.path.dirname(path)).startswith("_"):     # _ocr400 = thu nghiem
            continue
        base = os.path.basename(path)
        m = re.match(r"([A-Z0-9]+)-CAR-(\d{4}-\d{2}-\d{2})", base)
        if not m:
            continue
        ticker, fdate = m.group(1), m.group(2)
        if args.only and ticker != args.only.upper():
            continue
        rs = parse_file(path, ticker, fdate)
        # ban OCR lai (psm 4, 400 dpi) trong cbtt/_alt/<T>/ - lay ban nao doc ra NHIEU gia tri CAR hon
        alt = os.path.join(CBTT, "_alt", ticker, base)
        if os.path.exists(alt):
            rs2 = parse_file(alt, ticker, fdate)
            if sum(r["metric"] == "car" for r in rs2) > sum(r["metric"] == "car" for r in rs):
                rs = rs2
        for r in rs:
            r["file"] = base
        recs += rs
        got = sorted({(r["date"], r["scope"], r["metric"], r["value"]) for r in rs})
        log("%-4s %s -> %d gia tri: %s" % (ticker, fdate, len(rs),
            ", ".join("%s/%s %s=%g" % (d[2:7], s, mt, v) for d, s, mt, v in got[:8])))

    if not recs:
        log("Khong doc duoc gi.")
        return
    df = pd.DataFrame(recs)
    df = df[(df.value >= 4) & (df.value < 60)]
    df = df[~((df.value == 8.0) & (df.conf == "low"))]        # "toi thieu 8%" trong van xuoi
    # CAR duoi 8% la vi pham phap luat, khong ngan hang niem yet nao cong bo the -> chac chan la
    # ty le cap 1 bi gan nham nhan (CTG 7,2%). Ty le cap 1 thi duoc phep thap hon.
    df = df[~((df.metric == "car") & (df.value < 8.0))]
    # ngay phai nam trong [ky bao cao - 15 thang, ky bao cao]: loai cac moc 2019/2020 trong van xuoi
    fd = pd.to_datetime(df.file.str.extract(r"CAR-(\d{4}-\d{2}-\d{2})")[0], errors="coerce")
    dd = pd.to_datetime(df.date, format="%Y-%m-%d", errors="coerce")     # ngay OCR vo (31/06, 30/02) -> NaT -> loai
    df = df[dd.notna() & fd.notna() & (dd <= fd + pd.Timedelta(days=5)) & (dd >= fd - pd.Timedelta(days=460))]
    # cung (ticker, ky, scope, chi tieu): uu tien so doc chac (ok) truoc so doan (low), roi thu tu trong file
    df["_c"] = (df.conf != "ok").astype(int)
    df = df.sort_values(["ticker", "date", "scope", "metric", "_c", "line"])
    df = df.drop_duplicates(["ticker", "date", "scope", "metric"], keep="first").drop(columns="_c")
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    log("Ghi %s: %d dong, %d ngan hang" % (os.path.basename(OUT), len(df), df.ticker.nunique()))

    if args.merge:
        car = df[df.metric == "car"]
        rows, best = [], {}
        for (t, d), g in car.groupby(["ticker", "date"]):
            pick = g[g.scope == "hn"] if (g.scope == "hn").any() else g
            r0 = pick.iloc[0]
            best[(t, d)] = float(r0.value)
            rows.append(row(d, "car_" + t.lower(), float(r0.value),
                            series_name="CAR %s (%s, CBTT TT41)" % (t, "hop nhat" if r0.scope == "hn" else "rieng le"),
                            unit="%", freq="H", source="CBTT " + t,
                            node_id=N_ROOM[0], node_name=N_ROOM[1]))
        # Tong hop theo ky NUA NAM (30/06, 31/12) - chi ky co it nhat 3 ngan hang. Day la cai
        # dashboard doc: NHNN chi cong bo CAR gop theo nhom, con day la phan bo THAT giua cac NH.
        agg = pd.DataFrame([dict(t=t, d=d, v=v) for (t, d), v in best.items()])
        agg = agg[agg.d.str[5:] .isin(["06-30", "12-31"])]
        for d, g in agg.groupby("d"):
            if len(g) < 3:
                continue
            for sid, val, nm in (("car_banks_median", g.v.median(), "CAR hop nhat trung vi cac NH co CBTT"),
                                 ("car_banks_min", g.v.min(), "CAR hop nhat thap nhat trong cac NH co CBTT"),
                                 ("car_banks_n", float(len(g)), "So ngan hang co CBTT CAR trong ky")):
                rows.append(row(d, sid, round(float(val), 2), series_name=nm,
                                unit="%" if sid != "car_banks_n" else "ngan hang", freq="H",
                                source="CBTT ngan hang", node_id=N_ROOM[0], node_name=N_ROOM[1]))
        m = merge_master(rows, MASTER)
        log("Gop %d dong (car_<ticker> + tong hop) vao master (%d dong, %d series)"
            % (len(rows), len(m), m.series_id.nunique()))


if __name__ == "__main__":
    main()
