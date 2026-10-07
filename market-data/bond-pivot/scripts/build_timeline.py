# -*- coding: utf-8 -*-
"""Fact table cap lo, long-format, TOAN THI TRUONG — san pham chinh cua tool.

1 dong = 1 lo trai phieu (tu bond_master), kem:
- doanh nghiep + he sinh thai: parent_group (spv_parent_map.csv) + nganh + confidence
- chieu thoi gian: nam/quy/thang phat hanh + nam/quy dao han (ISO, pivot-ready)
- gia tri: PHAT HANH (gia_tri_ty) va DANG LUU HANH (gia_tri_luu_hanh_ty)
- CTCK bao lanh hop nhat: ctck_bao_lanh + nguon_bao_lanh + do_tin_cay
    cao        = PDF ket qua chao ban ghi dich danh bao lanh/tu van
    kha        = PDF ghi dai ly phat hanh / dai dien NSHTP
    proxy      = suy tu to_chuc_luu_ky (CTCK lam luu ky ~ ben thu xep)
    khong_xd   = khong co dau vet
- cot pdf_* raw de audit

Output: data/processed/market_issuance_timeline.csv
        data/processed/market_issuance_by_group.csv (tong hop theo nhom)
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_firm import load_spv_rules, map_parent, num, WINDOWS
from extract_arrangers import canonicalize, BANKS
from hnx_common import write_file_safe
import classify_issuers

# canonical la NGAN HANG/VSDC -> khong coi la CTCK bao lanh khi suy tu luu ky
NON_CTCK = BANKS

MASTER = "data/processed/bond_master.csv"
ARRANGER_EV = "data/processed/arranger_evidence.csv"
SPV_MAP = "data/spv_parent_map.csv"
OUT_TIMELINE = "data/processed/market_issuance_timeline.csv"
OUT_GROUP = "data/processed/market_issuance_by_group.csv"

MUALAI = "data/processed/mua_lai.csv"
DETAIL = "data/processed/bond_detail.csv"
FEED_CSV = "data/processed/feed.csv"
CREDIT_OUT = "data/processed/credit_events.csv"
# bang tay: ma_tp (hoac prefix ma + "*"), ctck, nguon_url — tu bao chi
PRESS = "data/press_arranger.csv"

CREDIT_PATTERNS = [
    ("cham_thanh_toan", r"chậm (?:thanh toán|trả)|không thể thanh toán|chưa thanh toán"),
    ("gia_han_ky_han", r"gia hạn|kéo dài kỳ hạn|thay đổi kỳ hạn|hoán đổi"),
    ("vi_pham", r"vi phạm|sự kiện vi phạm"),
    ("hoi_nghi_trai_chu", r"hội nghị (?:người sở hữu|trái chủ)|lấy ý kiến người sở hữu"),
]

FIELDS = ["ma_tp", "to_chuc_phat_hanh", "parent_group", "nganh_nhom", "mapped",
          "ma_ck", "nganh", "nganh_chi_tiet", "nguon_nganh",
          "ngay_phat_hanh", "nam_ph", "quy_ph", "thang_ph",
          "ngay_dao_han", "nam_dh", "quy_dh",
          "gia_tri_ty", "gia_tri_luu_hanh_ty", "menh_gia", "kl_phat_hanh",
          "kl_con_luu_hanh", "lai_suat", "ky_han", "tinh_trang",
          "gt_mua_lai_luy_ke_ty", "so_dot_mua_lai", "ngay_mua_lai_gan_nhat",
          "su_kien_tin_dung", "issuer_su_kien_tin_dung",
          "dam_bao", "hinh_thuc_dam_bao", "ma_isin", "trang_thai_dkgd",
          "ngay_gd_dau_tien",
          "ctck_bao_lanh", "nguon_bao_lanh", "do_tin_cay",
          "dai_dien_nshtp_hien_tai", "to_chuc_luu_ky",
          "pdf_bao_lanh", "pdf_tu_van", "pdf_dai_ly_phat_hanh",
          "pdf_dai_dien_nshtp"]


def resolve_arranger(e, luu_ky, dai_dien_detail="", press_ctck="", issuer=""):
    """(evidence, to_chuc_luu_ky, dai_dien tu detail) -> (ctck, nguon, tin_cay).

    PDF evidence: nhan ca NGAN HANG (bank cung lam bao lanh/tu van, co tai lieu
    thi tin). Tier proxy luu ky: CHI nhan CTCK (bank lam luu ky != bank bao lanh).
    Khi trong: nguon_bao_lanh ghi ly do (luu_ky_vsdc / luu_ky_ngan_hang / khong_ro).
    """
    if e:
        for role, tin_cay in [("bao_lanh", "cao"), ("tu_van", "cao"),
                              ("dai_ly_phat_hanh", "kha"),
                              ("dai_dien_nshtp", "kha")]:
            v = e.get(role, "")
            if v and v != "VSDC":
                return v, "pdf_" + role, tin_cay
    if dai_dien_detail:
        canon, _ = canonicalize(dai_dien_detail)
        if canon and canon not in NON_CTCK:
            return canon, "dai_dien_nshtp_hien_tai", "kha"
    canon, _ = canonicalize(luu_ky)
    if canon and canon not in NON_CTCK:
        return canon, "luu_ky", "proxy"
    # tier bao chi (bang tay data/press_arranger.csv)
    if press_ctck:
        return press_ctck, "bao_chi", "kha"
    # khong tim duoc o dau -> coi nhu TO CHUC PHAT HANH tu thu xep/tu ban
    # (dung cho phan lon bond ngan hang tu phat hanh); tin_cay=thap de loc duoc
    ly_do = ("luu_ky_vsdc" if canon == "VSDC"
             else "luu_ky_ngan_hang" if canon in NON_CTCK else "khong_ro")
    canon_iss, _ = canonicalize(issuer, fuzzy=False)  # fuzzy de nham ten dai
    name = canon_iss or issuer
    return name, "tu_phat_hanh(%s)" % ly_do, "thap"


def build_credit_events():
    """Quet tieu de feed -> credit_events.csv; tra ve (by_bond, by_issuer)."""
    import re as _re
    import unicodedata

    def norm_name(s):
        s = s.replace("Đ", "D").replace("đ", "d")
        s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()
        return _re.sub(r"\s+", " ", s.lower()).strip()

    events, by_bond, by_issuer = [], {}, {}
    for r in csv.DictReader(open(FEED_CSV, encoding="utf-8-sig")):
        kinds = [k for k, p in CREDIT_PATTERNS if _re.search(p, r["tieu_de"], _re.I)]
        if not kinds:
            continue
        events.append({"ngay": r["ngay_dang"], "ten_doanh_nghiep": r["ten_doanh_nghiep"],
                       "ma_tp": r["ma_tp_lien_quan"].strip().upper(),
                       "loai_su_kien": ";".join(kinds), "tieu_de": r["tieu_de"][:250],
                       "article_id": r["article_id"]})
        code = r["ma_tp_lien_quan"].strip().upper()
        if code:
            by_bond.setdefault(code, set()).update(kinds)
        by_issuer.setdefault(norm_name(r["ten_doanh_nghiep"]), set()).update(kinds)

    def _w(f):
        w = csv.DictWriter(f, fieldnames=["ngay", "ten_doanh_nghiep", "ma_tp",
                                          "loai_su_kien", "tieu_de", "article_id"])
        w.writeheader(); w.writerows(events)
    write_file_safe(CREDIT_OUT, _w)
    print("credit events: %d tin -> %s" % (len(events), CREDIT_OUT))
    return by_bond, by_issuer, norm_name


def load_mualai():
    """ma_tp -> (tong gt mua lai ty, so dot, ngay gan nhat ISO)."""
    agg = {}
    if not os.path.exists(MUALAI):
        return agg
    for r in csv.DictReader(open(MUALAI, encoding="utf-8-sig")):
        code = r["ma_tp"].strip().upper()
        a = agg.setdefault(code, [0.0, 0, ""])
        a[0] += num(r["gt_mua_lai"]) / 1e9
        a[1] += 1
        d = r["ngay_mua_lai"]
        dd = "-".join(reversed(d.split("/"))) if d else ""
        if dd > a[2]:
            a[2] = dd
    return agg


def load_detail():
    d = {}
    if os.path.exists(DETAIL):
        for r in csv.DictReader(open(DETAIL, encoding="utf-8-sig")):
            d[r["ma_tp"].strip().upper()] = r
    return d


def load_press():
    """press_arranger.csv: exact (ma_tp) va prefix (ma_tp ket thuc '*')."""
    exact, prefix = {}, []
    if os.path.exists(PRESS):
        for r in csv.DictReader(open(PRESS, encoding="utf-8-sig")):
            code = r["ma_tp"].strip().upper()
            if code.endswith("*"):
                prefix.append((code[:-1], r["ctck"]))
            elif code:
                exact[code] = r["ctck"]
    prefix.sort(key=lambda x: -len(x[0]))
    return exact, prefix


def press_lookup(code, exact, prefix):
    if code in exact:
        return exact[code]
    for p, ctck in prefix:
        if code.startswith(p):
            return ctck
    return ""


def iso_parts(d_ddmmyyyy):
    """'25/03/2021' -> ('2021-03-25', 2021, '2021Q1', '2021-03') hoac rong."""
    p = d_ddmmyyyy.split("/")
    if len(p) != 3 or not all(x.isdigit() for x in p):
        return "", "", "", ""
    dd, mm, yyyy = p
    q = (int(mm) - 1) // 3 + 1
    return "%s-%s-%s" % (yyyy, mm.zfill(2), dd.zfill(2)), yyyy, "%sQ%d" % (yyyy, q), "%s-%s" % (yyyy, mm.zfill(2))


def load_nganh():
    """keyword-normed -> nganh (de gan nganh cho parent_group)."""
    m = {}
    for r in csv.DictReader(open(SPV_MAP, encoding="utf-8-sig")):
        m.setdefault(r["parent_group"], r["nganh"].split("(")[0].strip())
    return m


def main():
    rules = load_spv_rules()
    nganh_map = load_nganh()
    # nganh cho MOI to chuc phat hanh (nganh_nhom cu chi co ~15% lo, bo trong toan bo ngan hang)
    nganh_tc = classify_issuers.build()
    ev = {}
    if os.path.exists(ARRANGER_EV):
        for r in csv.DictReader(open(ARRANGER_EV, encoding="utf-8-sig")):
            ev[r["ma_tp"].strip().upper()] = r
    by_bond, by_issuer, norm_name = build_credit_events()
    mualai = load_mualai()
    detail = load_detail()
    press_exact, press_prefix = load_press()

    rows = []
    for m in csv.DictReader(open(MASTER, encoding="utf-8-sig")):
        code = m["ma_tp"].strip().upper()
        g = map_parent(m["to_chuc_phat_hanh"], rules)
        iso_ph, nam_ph, quy_ph, thang_ph = iso_parts(m["ngay_phat_hanh"])
        iso_dh, nam_dh, quy_dh, _ = iso_parts(m["ngay_dao_han"])
        e = ev.get(code)
        det = detail.get(code, {})
        ctck, nguon, tin_cay = resolve_arranger(
            e, m["to_chuc_luu_ky"], det.get("dai_dien_nshtp", ""),
            press_lookup(code, press_exact, press_prefix),
            m["to_chuc_phat_hanh"])
        ml = mualai.get(code, [0.0, 0, ""])
        rows.append({
            "ma_tp": code,
            "to_chuc_phat_hanh": m["to_chuc_phat_hanh"],
            "parent_group": g,
            "nganh_nhom": nganh_map.get(g, ""),
            "mapped": int(g != m["to_chuc_phat_hanh"]),
            "ma_ck": nganh_tc.get(m["to_chuc_phat_hanh"], {}).get("ma_ck", ""),
            "nganh": nganh_tc.get(m["to_chuc_phat_hanh"], {}).get("nganh", classify_issuers.CHUA),
            "nganh_chi_tiet": nganh_tc.get(m["to_chuc_phat_hanh"], {}).get("nganh_chi_tiet", ""),
            "nguon_nganh": nganh_tc.get(m["to_chuc_phat_hanh"], {}).get("nguon", ""),
            "ngay_phat_hanh": iso_ph, "nam_ph": nam_ph, "quy_ph": quy_ph,
            "thang_ph": thang_ph,
            "ngay_dao_han": iso_dh, "nam_dh": nam_dh, "quy_dh": quy_dh,
            "gia_tri_ty": round(num(m["menh_gia"]) * num(m["kl_phat_hanh"]) / 1e9, 2),
            "gia_tri_luu_hanh_ty": round(num(m["menh_gia"]) * num(m["kl_con_luu_hanh"]) / 1e9, 2),
            "menh_gia": m["menh_gia"], "kl_phat_hanh": m["kl_phat_hanh"],
            "kl_con_luu_hanh": m["kl_con_luu_hanh"],
            "lai_suat": m["lai_suat_phat_hanh"], "ky_han": m["ky_han"],
            "tinh_trang": m["tinh_trang"],
            "gt_mua_lai_luy_ke_ty": round(ml[0], 2),
            "so_dot_mua_lai": ml[1],
            "ngay_mua_lai_gan_nhat": ml[2],
            "su_kien_tin_dung": ";".join(sorted(by_bond.get(code, []))),
            "issuer_su_kien_tin_dung": ";".join(sorted(
                by_issuer.get(norm_name(m["to_chuc_phat_hanh"]), []))),
            "dam_bao": det.get("dam_bao", ""),
            "hinh_thuc_dam_bao": det.get("hinh_thuc_dam_bao", ""),
            "ma_isin": det.get("ma_isin", ""),
            "trang_thai_dkgd": det.get("trang_thai_dkgd", ""),
            "ngay_gd_dau_tien": det.get("ngay_gd_dau_tien", ""),
            "ctck_bao_lanh": ctck, "nguon_bao_lanh": nguon, "do_tin_cay": tin_cay,
            "dai_dien_nshtp_hien_tai": det.get("dai_dien_nshtp", ""),
            "to_chuc_luu_ky": m["to_chuc_luu_ky"],
            "pdf_bao_lanh": (e or {}).get("bao_lanh", ""),
            "pdf_tu_van": (e or {}).get("tu_van", ""),
            "pdf_dai_ly_phat_hanh": (e or {}).get("dai_ly_phat_hanh", ""),
            "pdf_dai_dien_nshtp": (e or {}).get("dai_dien_nshtp", ""),
        })

    def _write(f):
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(rows)
    write_file_safe(OUT_TIMELINE, _write)

    # tong hop theo nhom (giu cho ai chi can bang gon)
    agg = {}
    for r in rows:
        a = agg.setdefault(r["parent_group"], {"so_lo": 0, "ty": 0.0, "lh": 0.0,
                                               **{w: 0.0 for w, _, _ in WINDOWS}})
        a["so_lo"] += 1
        a["ty"] += r["gia_tri_ty"]
        a["lh"] += r["gia_tri_luu_hanh_ty"]
        y = int(r["nam_ph"]) if r["nam_ph"] else 0
        for w, y0, y1 in WINDOWS:
            if y0 <= y <= y1:
                a[w] += r["gia_tri_ty"]

    def _write_g(f):
        w = csv.writer(f)
        w.writerow(["parent_group", "so_lo", "tong_gia_tri_ty", "dang_luu_hanh_ty"]
                   + ["gia_tri_ty_" + w for w, _, _ in WINDOWS])
        for g, a in sorted(agg.items(), key=lambda x: -x[1]["ty"]):
            w.writerow([g, a["so_lo"], round(a["ty"], 1), round(a["lh"], 1)]
                       + [round(a[w], 1) for w, _, _ in WINDOWS])
    write_file_safe(OUT_GROUP, _write_g)
    print("timeline: %d lo -> %s | by-group -> %s" % (len(rows), OUT_TIMELINE, OUT_GROUP))


if __name__ == "__main__":
    main()
