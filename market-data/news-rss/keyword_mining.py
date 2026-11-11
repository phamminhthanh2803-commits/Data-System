# -*- coding: utf-8 -*-
r"""keyword_mining.py - lap danh sach TU KHOA XUAT HIEN THUONG XUYEN & DANG CHU Y tu kho tin da keo (11/11/2026).

    python keyword_mining.py [--days 60] [--min-df 4]

Doc data\news_tagged.parquet + news_tags.parquet -> output\keyword_candidates.xlsx:
  Tan_suat        cum 2-4 am tiet hay gap nhat trong tieu de + tom tat (bo cum mo dau / ket thuc bang hu tu), cot 'da_co' = da trong tu dien
  Theo_nganh      cum DAC TRUNG cua tung nganh: lift = P(cum | bai thuoc nganh) / P(cum) tren bai GAN NGANH BANG MA CK (nhan doc lap voi
                  tu dien -> tim tu moi), top 40 / nganh, chua co trong tu dien
  Chua_phan_loai  cum hay gap trong bai CHUA gan nganh -> lo hong tu dien
  Tu_dien_dung    tu khoa trong tu dien da khop bao nhieu bai (0 = co the bo / sai chinh ta)
  Ma_CK           ma 3 ky tu viet hoa da nhan + 2 vi du ngu canh (soat ma trung viet tat -> them can_ngu_canh vao alias_ma.csv)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter, defaultdict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mdlib import log, setup_stdout  # noqa: E402

import newslib as nl  # noqa: E402

HU_TU = set(nl.norm("""của và các những cho với trong là có được đã đang này một từ về khi để sẽ không nhưng tại theo hơn đến ra
 năm ngày tháng người cũng như thì mà nên vì bị do còn rất lại sau trước trên dưới vào hay hoặc nếu đó đây nhiều ít mới
 vừa chỉ đều cùng gì nào ai sao thế bao giờ tới ở lên xuống qua nhất thêm mức gần hơn khoảng lần đầu cả chưa hết vẫn
 sắp tiếp thứ gồm bằng này kia ấy vậy thể""").lower().split())
TACH = re.compile(r"[^\w%/]+")


def ngrams(text: str, nmax=4):
    out = set()
    for cau in re.split(r"[.,;:!?\"“”'‘’()\[\]–\-|]+", text.lower()):
        toks = [t for t in TACH.split(cau) if t]
        for n in range(2, nmax + 1):
            for i in range(len(toks) - n + 1):
                g = toks[i:i + n]
                if g[0] in HU_TU or g[-1] in HU_TU or any(x.isdigit() for x in g):
                    continue
                out.add(" ".join(g))
    return out


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0, help="0 = toan bo kho")
    ap.add_argument("--min-df", type=int, default=4)
    a = ap.parse_args()
    t = pd.read_parquet(nl.TAGGED)
    g = pd.read_parquet(nl.TAGS)
    if a.days:
        t = t[t["ngay_gio"] >= t["ngay_gio"].max() - pd.Timedelta(days=a.days)]
    t = t.drop_duplicates("nhom_trung")                               # tin dang lai nhieu bao chi tinh 1
    log(f"Che do: {len(t)} bai (bo trung tieu de) · min_df {a.min_df}")
    docs = {r.id: ngrams(nl.norm(r.tieu_de) + " . " + nl.norm(r.tom_tat)) for r in t.itertuples(index=False)}
    df = Counter()
    for s in docs.values():
        df.update(s)
    # chi giu CUM TOI DAI: bo 'động sản' khi 'bất động sản' gan cung tan suat (>= 80%) - n-gram tieng Viet hay bi cat giua tu ghep
    dai = defaultdict(int)
    for k, v in df.items():
        p = k.split(" ")
        if len(p) >= 3:
            for con in (" ".join(p[1:]), " ".join(p[:-1])):
                dai[con] = max(dai[con], v)
    cut = {k for k, v in df.items() if dai.get(k, 0) >= 0.8 * v}
    for s in docs.values():
        s -= cut
    df = Counter({k: v for k, v in df.items() if k not in cut})
    kw = nl.read_cfg("keywords.csv")
    co = {nl.norm(k).lower() for k in kw["tu_khoa"]}
    ten = dict(zip(nl.danh_sach_nganh()["ma"], nl.danh_sach_nganh()["nganh"]))

    # (1) tan suat chung
    top = [(k, v) for k, v in df.most_common() if v >= a.min_df]
    # bo cum con nam tron trong cum dai hon cung tan suat (vd 'giá vàng hôm' khi da co 'giá vàng hôm nay')
    tan = pd.DataFrame(top, columns=["cum", "so_bai"])
    tan["so_am_tiet"] = tan["cum"].str.count(" ") + 1
    tan["da_co"] = tan["cum"].isin(co)
    tan["ty_le_%"] = (tan["so_bai"] / len(docs) * 100).round(2)

    # (2) dac trung theo nganh: nhan = nganh gan qua MA CK (doc lap voi tu dien)
    pl = nl.PhanLoai()
    nhan = defaultdict(set)
    for r in t.itertuples(index=False):
        for c in str(r.ma or "").split("|"):
            ng = "Vingroup" if c in nl.VIN else pl.ma_nganh.get(c)
            if isinstance(ng, str):
                nhan[ng].add(r.id)
    # bo sung nhan tu tu dien voi diem cao (>= 8) de nganh it ma (Vi mo, The gioi, TTCK) van co mau
    for r in g[g["diem"] >= 8].itertuples(index=False):
        nhan[r.nganh].add(r.id)
    N = len(docs)
    rows = []
    for ng, ids in nhan.items():
        if len(ids) < 5:
            continue
        c = Counter()
        for i in ids:
            c.update(docs.get(i, ()))
        for k, v in c.items():
            if v < 3 or df[k] < a.min_df - 1:
                continue
            lift = (v / len(ids)) / (df[k] / N)
            if lift >= 3:
                rows.append({"nganh": ng, "cum": k, "so_bai_nganh": v, "so_bai_tong": df[k], "lift": round(lift, 1),
                             "do_tap_trung_%": round(v / df[k] * 100, 1), "da_co": k in co})
    tn = pd.DataFrame(rows)
    if len(tn):
        tn = (tn[~tn["da_co"]].sort_values(["nganh", "so_bai_nganh", "lift"], ascending=[True, False, False])
              .groupby("nganh").head(40).reset_index(drop=True))

    # (3) lo hong: bai chua phan loai
    khac = t[t["nganh_chinh"] == nl.KHAC]
    ck = Counter()
    for i in khac["id"]:
        ck.update(docs.get(i, ()))
    cpl = pd.DataFrame([(k, v, df[k], k in co) for k, v in ck.most_common() if v >= 3],
                       columns=["cum", "so_bai_chua_pl", "so_bai_tong", "da_co"])

    # (4) tu dien dang dung
    full = (t["tieu_de"].map(nl.norm) + " . " + t["tom_tat"].map(nl.norm))
    low = full.str.lower()
    dung = []
    for r in kw.itertuples(index=False):
        k = nl.norm(r.tu_khoa)
        rg = re.compile(rf"(?<!\w){re.escape(k if r.hoa == '1' else k.lower())}(?!\w)")
        n = int((full if r.hoa == "1" else low).str.contains(rg).sum())
        dung.append({"nganh": ten.get(r.ma, r.ma), "chu_de": r.chu_de, "tu_khoa": r.tu_khoa, "trong_so": r.trong_so, "so_bai_khop": n})
    dung = pd.DataFrame(dung).sort_values(["nganh", "so_bai_khop"], ascending=[True, False])

    # (5) ma CK + ngu canh
    ex = defaultdict(list)
    cnt = Counter()
    for r in t.itertuples(index=False):
        s = nl.norm(r.tieu_de) + " . " + nl.norm(r.tom_tat)
        for c in str(r.ma or "").split("|"):
            if not c:
                continue
            cnt[c] += 1
            m = re.search(rf"(?<![\w]){c}(?![\w])", s)
            if m and len(ex[c]) < 2:
                ex[c].append(s[max(0, m.start() - 45):m.end() + 35])
            elif len(ex[c]) < 2:
                ex[c].append("(qua alias) " + s[:80])
    mck = pd.DataFrame([{"ma": c, "so_bai": v, "nganh_icb2": pl.ma_nganh.get(c, ""), "ten": pl.icb["ten"].get(c, "") if "ten" in pl.icb else "",
                         "vi_du_1": (ex[c] + ["", ""])[0], "vi_du_2": (ex[c] + ["", ""])[1]} for c, v in cnt.most_common()])

    os.makedirs(nl.OUT, exist_ok=True)
    out = os.path.join(nl.OUT, "keyword_candidates.xlsx")
    with pd.ExcelWriter(out) as w:
        tan.head(1500).to_excel(w, "Tan_suat", index=False)
        tn.to_excel(w, "Theo_nganh", index=False)
        cpl.head(800).to_excel(w, "Chua_phan_loai", index=False)
        dung.to_excel(w, "Tu_dien_dung", index=False)
        mck.to_excel(w, "Ma_CK", index=False)
    log(f"Da luu {out}: {len(tan)} cum tan suat · {len(tn)} cum dac trung nganh · {len(cpl)} cum o bai chua phan loai · "
        f"{int((dung['so_bai_khop'] == 0).sum())}/{len(dung)} tu khoa chua khop bai nao · {len(mck)} ma CK")


if __name__ == "__main__":
    main()
