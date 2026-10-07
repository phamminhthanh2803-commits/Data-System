# -*- coding: utf-8 -*-
"""Phan nganh TO CHUC PHAT HANH trai phieu — toan thi truong.

Truoc day nganh_nhom chi lay tu spv_parent_map.csv (62 SPV khai tay) -> 85% so lo
(52% gia tri la NGAN HANG) bo trong. Script nay gan nganh cho MOI to chuc phat hanh.

Thu tu uu tien (dung o buoc dau tien khop):
  1. override    config/nganh_overrides.csv  (tu khoa -> nganh, sua tay sau khi soat)
  2. dac_biet    cong ty tai chinh / quan ly no / cho thue tai chinh / chung khoan
                 (ten co chu "Ngan hang" nhung KHONG phai ngan hang: FE Credit, CTCK con cua NH)
  3. niem_yet    khop TEN CHUAN voi 1.526 cong ty niem yet (fs-extractor nganh_cache.csv,
                 ICB VietcapIQ) -> ma CK + nganh ICB -> quy ve 9 nhom VBMA
  4. ngan_hang   ten co "ngan hang"/"NH TMCP" nhung chua niem yet (Agribank, Shinhan, HSBC...)
  5. he_sinh_thai parent_group trong spv_parent_map.csv (SPV cua Vingroup, Masterise, VTP...)
  6. tu_khoa     luat tu khoa tren ten
  7. "Chưa phân loại" -> xem bao cao, bo sung override

9 nhom theo cach chia cua VBMA: Ngan hang, Bat dong san, Xay dung, Tai chinh, Chung khoan,
Tieu dung, Cong nghiep, Nang luong, Linh vuc khac.

Output: data/processed/issuer_industry.csv (1 dong / to chuc phat hanh)
Chay:   python scripts/classify_issuers.py        (build_timeline.py cung goi tu dong)
"""
import csv
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hnx_common import write_file_safe

MASTER = "data/processed/bond_master.csv"
SPV_MAP = "data/spv_parent_map.csv"
OVERRIDES = "config/nganh_overrides.csv"
LISTED = os.path.join(os.path.normpath(os.environ.get("BCTC_ROOT", "D:/bctc")), "fs-extractor", "nganh_cache.csv")
OUT = "data/processed/issuer_industry.csv"

NGANH = ["Ngân hàng", "Bất động sản", "Xây dựng", "Tài chính", "Chứng khoán",
         "Tiêu dùng", "Công nghiệp", "Năng lượng", "Lĩnh vực khác"]
CHUA = "Chưa phân loại"


def khong_dau(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.replace("đ", "d").replace("Đ", "D").lower()).strip()


# tu phap ly bo khi so ten (dai truoc ngan)
_PHAP_LY = sorted([
    "ngan hang thuong mai co phan", "ngan hang tmcp", "nh tmcp", "ngan hang tnhh mot thanh vien",
    "ngan hang tnhh mtv", "ngan hang", "tong cong ty", "tap doan", "cong ty co phan",
    "cong ty tnhh mot thanh vien", "cong ty tnhh mtv", "cong ty tnhh", "cong ty cp", "cong ty",
    "ctcp", "cty cp", "cty tnhh", "cty", "co phan", "tnhh", "mot thanh vien", "mtv", "jsc",
    "joint stock company", "company limited", "corporation", "corp", "group",
], key=len, reverse=True)


def ten_chuan(s):
    t = khong_dau(s)
    t = re.sub(r"\(.*?\)", " ", t)                 # bo "(ten cu: ...)", "(HDBANK)"
    t = re.sub(r"\(.*$", " ", t)                    # ngoac mo khong dong (ten bi cat)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    for w in _PHAP_LY:
        t = re.sub(r"\b" + w + r"\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def ten_cu(s):
    """Cac ten cu trong ngoac: '(ten cu: X)' / '(Tên cũ: X)'."""
    return [m for m in re.findall(r"t[eê]n c[uũ]\s*:\s*([^)]+)\)?", str(s), flags=re.I)]


def icb_ve_vbma(l1, l2, l4):
    l1, l2, l4 = str(l1), str(l2), str(l4)
    if l2 == "Ngân hàng":
        return "Ngân hàng"
    if l2 == "Bất động sản":
        return "Bất động sản"
    if l2 == "Dịch vụ tài chính":
        return "Chứng khoán" if "chứng khoán" in l4.lower() else "Tài chính"
    if l2 == "Bảo hiểm":
        return "Tài chính"
    if l2 == "Xây dựng và Vật liệu":
        return "Xây dựng" if l4 == "Xây dựng" else "Công nghiệp"
    if l1 in ("Dầu khí", "Tiện ích Cộng đồng"):
        return "Năng lượng"
    if l1 in ("Công nghiệp", "Nguyên vật liệu"):
        return "Công nghiệp"
    if l1 in ("Hàng Tiêu dùng", "Dịch vụ Tiêu dùng", "Dược phẩm và Y tế"):
        return "Tiêu dùng"
    return "Lĩnh vực khác"


def nhom_ve_vbma(s):
    """nganh ghi tay trong spv_parent_map.csv -> 9 nhom."""
    t = khong_dau(s)
    if t.startswith("ngan hang"):
        return "Ngân hàng"
    if t.startswith(("bds", "bat dong san", "ban le bds", "du lich", "ks")):
        return "Bất động sản"          # KS/du lich cua cac tap doan BDS nghi duong (Sun, Vinpearl)
    if t.startswith(("fmcg", "ban le", "thuc an", "thuc pham")):
        return "Tiêu dùng"
    if t.startswith("khoang san"):
        return "Công nghiệp"
    return ""


def _cum(*cum):
    """Moi cum tu phai khop TRON TU (\\b hai dau). Khong co \\b thi "co phan bong sen" chua
    "phan bon" -> Cong ty Bong Sen (khach san) bi xep nham vao Cong nghiep."""
    return r"\b(?:" + "|".join(cum) + r")\b"


DAC_BIET = [
    ("Chứng khoán", _cum("chung khoan", "securities")),
    ("Tài chính", _cum("cong ty tai chinh", "cho thue tai chinh", "quan ly no va khai thac tai san",
                       "amc", "quan ly quy", "bao hiem")),
]
TU_KHOA = [
    # cum tu BDS RO RANG dat truoc: "Tiep van va Bat dong san Tan Lien Phat Tan Cang" khong bi
    # "cang" keo sang Cong nghiep, "xay dung - dia oc Viet Han" khong bi keo sang Xay dung
    ("Bất động sản", _cum("bat dong san", "dia oc", "real estate", "bds")),
    ("Năng lượng", _cum("dien", "nang luong", "thuy dien", "nhiet dien", "dau khi", "xang dau",
                        "solar", "dien mat troi", "dien gio", "energy", "power")),
    ("Xây dựng", _cum("xay dung", "xay lap", "ha tang", "giao thong", "cau duong", "bot",
                      "thi cong", "construction", "cong trinh")),
    ("Công nghiệp", _cum("thep", "hoa chat", "xi mang", "cao su", "nhua", "phan bon", "van tai",
                         "logistics", "cang", "hang khong", "o to", "co khi", "khoang san",
                         "det may", "may mac", "che tao", "dong tau", "go", "giay", "bao bi",
                         "tiep van")),
    ("Tiêu dùng", _cum("thuc pham", "ban le", "sieu thi", "sua", "do uong", "bia", "nong nghiep",
                       "chan nuoi", "thuy san", "duoc pham", "benh vien", "y te", "giao duc",
                       "truong hoc", "dinh duong", "vang bac", "da quy", "noi that")),
    ("Bất động sản", _cum("nha o", "land", "homes?", "do thi", "khu do thi", "khu cong nghiep", "kcn",
                          "du lich", "khach san", "resort", "nghi duong", "realty", "propert\\w*",
                          "phat trien nha", "khu dan cu", "tower", "city", "residence", "garden",
                          "villas?", "riverside", "marina", "park\\w*")),
]


def doc_niem_yet():
    """ten chuan -> (ticker, ten, L1, L2, L4); rieng bang ngan hang de khop gan dung."""
    exact, banks = {}, []
    if not os.path.exists(LISTED):
        print("[!] khong thay %s -> bo buoc khop niem yet" % LISTED)
        return exact, banks
    for r in csv.DictReader(open(LISTED, encoding="utf-8-sig")):
        v = (r["ticker"], r["ten_cong_ty"], r["nganh_L1"], r["nganh_L2"], r["nganh_L4"])
        k = ten_chuan(r["ten_cong_ty"])
        if len(k) >= 4:
            exact.setdefault(k, v)
        if r["nganh_L2"] == "Ngân hàng":
            banks.append((k, v))
    return exact, banks


def doc_override():
    out = []
    if os.path.exists(OVERRIDES):
        for r in csv.DictReader(open(OVERRIDES, encoding="utf-8-sig")):
            if r.get("tu_khoa", "").strip():
                out.append((khong_dau(r["tu_khoa"]), r["nganh"].strip(), r.get("ma_ck", "").strip(),
                            r.get("ghi_chu", "").strip()))
    out.sort(key=lambda x: -len(x[0]))
    return out


def doc_nhom():
    """spv keyword chuan -> (parent_group, nganh 9 nhom)."""
    out = []
    if os.path.exists(SPV_MAP):
        for r in csv.DictReader(open(SPV_MAP, encoding="utf-8-sig")):
            n = nhom_ve_vbma(r["nganh"])
            if n:
                out.append((khong_dau(r["spv_name_keyword"]), r["parent_group"], n, r["nganh"]))
    out.sort(key=lambda x: -len(x[0]))
    return out


def phan_loai(ten, exact, banks, overrides, nhom):
    """-> dict(ma_ck, ten_niem_yet, nganh, nganh_chi_tiet, nguon)"""
    t = khong_dau(ten)
    kq = lambda n, nguon, ma="", ten_ny="", ct="": dict(  # noqa: E731
        ma_ck=ma, ten_niem_yet=ten_ny, nganh=n, nganh_chi_tiet=ct, nguon=nguon)

    for kw, n, ma, gc in overrides:
        if kw in t:
            return kq(n, "override", ma, "", gc)
    for n, pat in DAC_BIET:
        if re.search(pat, t):
            # CTCK/cty tai chinh niem yet van lay ma CK neu khop
            v = exact.get(ten_chuan(ten))
            return kq(n, "dac_biet", v[0] if v else "", v[1] if v else "", v[4] if v else "")

    la_ngan_hang = bool(re.search(r"ngan hang|\bnh tmcp\b|\bbank\b", t))
    if not la_ngan_hang:
        # ten NGAN HANG khong duoc khop cong ty niem yet thuong: "Ngan hang TMCP Bao Viet"
        # co ten chuan "bao viet" trung "Tap doan Bao Viet" (BVH, bao hiem)
        for cand in [ten] + ten_cu(ten):
            v = exact.get(ten_chuan(cand))
            if v and v[3] != "Ngân hàng":
                return kq(icb_ve_vbma(v[2], v[3], v[4]), "niem_yet", v[0], v[1],
                          "%s / %s" % (v[3], v[4]))

    if la_ngan_hang:
        k = ten_chuan(ten)
        for bk, v in banks:                      # khop gan dung ten ngan hang niem yet
            if bk and (bk == k or (len(bk) >= 6 and bk in k) or (len(k) >= 6 and k in bk)):
                return kq("Ngân hàng", "niem_yet", v[0], v[1], "Ngân hàng")
        for cand in ten_cu(ten):
            kc = ten_chuan(cand)
            for bk, v in banks:
                if bk == kc:
                    return kq("Ngân hàng", "niem_yet", v[0], v[1], "Ngân hàng (tên cũ)")
        return kq("Ngân hàng", "ngan_hang", ct="Ngân hàng chưa niêm yết")

    for kw, g, n, goc in nhom:
        if kw and kw in t:
            return kq(n, "he_sinh_thai", ct="%s — %s" % (g, goc))

    for n, pat in TU_KHOA:
        if re.search(pat, t):
            return kq(n, "tu_khoa")
    return kq(CHUA, "chua")


def build():
    exact, banks = doc_niem_yet()
    overrides, nhom = doc_override(), doc_nhom()
    agg = {}
    for m in csv.DictReader(open(MASTER, encoding="utf-8-sig")):
        ten = m["to_chuc_phat_hanh"]
        try:
            gt = float(re.sub(r"[^\d.]", "", m["menh_gia"]) or 0) * \
                 float(re.sub(r"[^\d.]", "", m["kl_phat_hanh"]) or 0) / 1e9
        except ValueError:
            gt = 0.0
        a = agg.setdefault(ten, {"so_lo": 0, "gia_tri_ty": 0.0})
        a["so_lo"] += 1
        a["gia_tri_ty"] += gt if m.get("tien_te", "VNĐ") != "USD" else 0.0

    rows = []
    for ten, a in agg.items():
        r = phan_loai(ten, exact, banks, overrides, nhom)
        r.update({"to_chuc_phat_hanh": ten, "so_lo": a["so_lo"], "gia_tri_ty": round(a["gia_tri_ty"], 1)})
        rows.append(r)
    rows.sort(key=lambda r: -r["gia_tri_ty"])

    cols = ["to_chuc_phat_hanh", "ma_ck", "ten_niem_yet", "nganh", "nganh_chi_tiet", "nguon",
            "so_lo", "gia_tri_ty"]

    def _w(f):
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    write_file_safe(OUT, _w)

    tong = sum(r["gia_tri_ty"] for r in rows) or 1
    lo = sum(r["so_lo"] for r in rows) or 1
    print("phan nganh: %d to chuc -> %s" % (len(rows), OUT))
    theo_nguon = {}
    for r in rows:
        x = theo_nguon.setdefault(r["nguon"], [0, 0, 0.0])
        x[0] += 1; x[1] += r["so_lo"]; x[2] += r["gia_tri_ty"]
    for k, (n, l, g) in sorted(theo_nguon.items(), key=lambda kv: -kv[1][2]):
        print("  %-13s %4d to chuc  %5.1f%% so lo  %5.1f%% gia tri" % (k, n, l / lo * 100, g / tong * 100))
    return {r["to_chuc_phat_hanh"]: r for r in rows}


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    build()
