# -*- coding: utf-8 -*-
"""Phan tich mot CTCK: flag bond -> map SPV -> aggregate -> report.

Usage: python scripts/analyze_firm.py <firm_key>     (vd: tcbs)

Input chung : data/processed/{bond_master,feed}.csv, data/spv_parent_map.csv
Output rieng: output/<firm>/{bonds_raw,feed_hits,issuer_frequency,
              issuer_frequency_raw}.csv + report.md

Signal A: bond_master.to_chuc_luu_ky khop regex cong ty (proxy manh).
Signal B: feed CBTT nhac ten cong ty kem vai tro.
"""
import csv
import os
import re
import sys
import unicodedata
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hnx_common import (write_file_safe, firm_get, firm_identity_re,
                        firm_out_dir)

MASTER = "data/processed/bond_master.csv"
FEED = "data/processed/feed.csv"
SPV_MAP = "data/spv_parent_map.csv"
ARRANGER_EV = "data/processed/arranger_evidence.csv"
EV_ROLES = ["tu_van", "bao_lanh", "dai_ly_phat_hanh", "dai_ly_dang_ky_luu_ky",
            "dai_ly_thanh_toan", "dai_dien_nshtp", "quan_ly_tsbd"]

ROLE_PATTERNS = [
    ("dai_dien_nshtp", r"[đd][ạa]i\s+di[ệe]n\s+(?:ng[ưu][ờo]i|NSH)"),
    ("dai_ly_dang_ky_luu_ky", r"[đd][ạa]i\s+l[ýy]\s+[đd][ăa]ng\s+k[ýy]"),
    ("dai_ly_thanh_toan", r"[đd][ạa]i\s+l[ýy]\s+thanh\s+to[áa]n"),
    ("dai_ly_phat_hanh", r"[đd][ạa]i\s+l[ýy]\s+ph[áa]t\s+h[àa]nh"),
    ("tu_van", r"t[ổo]\s+ch[ứu]c\s+t[ưu]\s+v[ấa]n|t[ưu]\s+v[ấa]n\s+(?:h[ồo]\s+s[ơo]\s+)?(?:ph[áa]t\s+h[àa]nh|ch[àa]o\s+b[áa]n)"),
    ("bao_lanh", r"b[ảa]o\s+l[ãa]nh\s+ph[áa]t\s+h[àa]nh"),
    ("to_chuc_luu_ky", r"t[ổo]\s+ch[ứu]c\s+l[ưu]u\s+k[ýy]"),
]

BOND_CODE_RE = re.compile(
    r"\b[A-Z][A-Z0-9]{1,5}[BH]\d{6,10}\b"
    r"|\b[A-Z0-9]{2,12}[._]BOND[._]?\d{4,10}\b"
    r"|\b[A-Z0-9]{3,6}CH\d{4,10}\b")

WINDOWS = [("2019_2021", 2019, 2021), ("2022_2023", 2022, 2023),
           ("2024_2026", 2024, 2026)]


# ---------- helpers ----------
def strip_accents(s):
    s = s.replace("Đ", "D").replace("đ", "d")
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()


def norm(s):
    return re.sub(r"\s+", " ", strip_accents(s).lower()).strip()


def num(s):
    return float(re.sub(r"[^\d.]", "", s) or 0) if s else 0.0


def fmt(v):
    return "{:,.0f}".format(v).replace(",", ".")


def detect_roles(text):
    return [n for n, p in ROLE_PATTERNS if re.search(p, text, re.I)]


def load_spv_rules():
    rules = []
    with open(SPV_MAP, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            rules.append((norm(row["spv_name_keyword"]), row["parent_group"]))
    rules.sort(key=lambda x: -len(x[0]))
    return rules


def map_parent(issuer, rules):
    n = norm(issuer)
    for kw, parent in rules:
        if kw and kw in n:
            return parent
    return issuer


def load_arranger_evidence():
    """ma_tp -> {role: canonical} tu bang evidence toan thi truong (neu co)."""
    ev = {}
    if os.path.exists(ARRANGER_EV):
        for r in csv.DictReader(open(ARRANGER_EV, encoding="utf-8-sig")):
            ev[r["ma_tp"].strip().upper()] = {k: r.get(k, "") for k in EV_ROLES}
    return ev


# ---------- level 1 ----------
def flag_bonds(firm_re):
    master = {}
    with open(MASTER, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            master[row["ma_tp"].strip().upper()] = row

    bonds, hits = {}, []
    # Signal A: firm la to chuc luu ky trong bond master
    for code, m in master.items():
        if firm_re.search(m["to_chuc_luu_ky"]):
            if firm_re.search(m["to_chuc_phat_hanh"]):
                continue  # bond do chinh cong ty phat hanh
            bonds[code] = {"roles": {"dai_ly_dang_ky_luu_ky"},
                           "signals": {"master_luu_ky"}, "n_articles": 0,
                           "sample_title": "", "issuer": m["to_chuc_phat_hanh"]}

    # Signal B: feed CBTT nhac ten cong ty
    with open(FEED, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            text = " | ".join([row["ten_doanh_nghiep"], row["tieu_de"], row["ghi_chu"]])
            if not firm_re.search(text):
                continue
            issuer_is_firm = bool(firm_re.search(row["ten_doanh_nghiep"]))
            roles = detect_roles(row["tieu_de"] + " | " + row["ghi_chu"])
            codes = set(c.upper() for c in BOND_CODE_RE.findall(
                row["ma_tp_lien_quan"] + " " + row["tieu_de"]))
            if row["ma_tp_lien_quan"].strip():
                codes.add(row["ma_tp_lien_quan"].strip().upper())
            hits.append({**row, "roles": ";".join(roles),
                         "issuer_is_firm": int(issuer_is_firm),
                         "bond_codes": ";".join(sorted(codes))})
            if issuer_is_firm:
                continue
            for code in codes:
                b = bonds.setdefault(code, {"roles": set(), "signals": set(),
                                            "n_articles": 0, "sample_title": "",
                                            "issuer": row["ten_doanh_nghiep"]})
                b["signals"].add("feed")
                b["roles"].update(roles or ["unspecified"])
                b["n_articles"] += 1
                if not b["sample_title"]:
                    b["sample_title"] = row["tieu_de"][:200]

    rows = []
    for code, b in sorted(bonds.items()):
        m = master.get(code, {})
        rows.append({
            "ma_tp": code,
            "to_chuc_phat_hanh": m.get("to_chuc_phat_hanh", b["issuer"]),
            "parent_group": "",  # dien o buoc map
            "mapped_by_keyword": 0,
            "ngay_phat_hanh": m.get("ngay_phat_hanh", ""),
            "ngay_dao_han": m.get("ngay_dao_han", ""),
            "menh_gia": m.get("menh_gia", ""),
            "kl_phat_hanh": m.get("kl_phat_hanh", ""),
            "gia_tri_phat_hanh_ty": round(num(m.get("menh_gia", "")) * num(m.get("kl_phat_hanh", "")) / 1e9, 2),
            "lai_suat_phat_hanh": m.get("lai_suat_phat_hanh", ""),
            "ky_han": m.get("ky_han", ""),
            "tinh_trang": m.get("tinh_trang", ""),
            "vai_tro": ";".join(sorted(b["roles"])),
            "nguon": "level1:" + "+".join(sorted(b["signals"])),
            "n_articles": b["n_articles"],
            "in_master": int(bool(m)),
            "sample_title": b["sample_title"],
        })
    return rows, hits


# ---------- aggregate ----------
def aggregate(rows, key):
    agg = {}
    for r in rows:
        k = r[key]
        a = agg.setdefault(k, {"so_lo": 0, "tong_gia_tri_ty": 0.0,
                               "first_date": "", "last_date": "",
                               **{f"so_lo_{w}": 0 for w, _, _ in WINDOWS},
                               **{f"gia_tri_ty_{w}": 0.0 for w, _, _ in WINDOWS},
                               "vai_tro": set(), "issuers": set()})
        a["so_lo"] += 1
        a["tong_gia_tri_ty"] += r["gia_tri_phat_hanh_ty"]
        a["vai_tro"].update(r["vai_tro"].split(";"))
        a["issuers"].add(r["to_chuc_phat_hanh"])
        d = r["ngay_phat_hanh"]
        dd = "-".join(reversed(d.split("/"))) if d else ""
        if dd:
            if not a["first_date"] or dd < a["first_date"]:
                a["first_date"] = dd
            if not a["last_date"] or dd > a["last_date"]:
                a["last_date"] = dd
        try:
            y = int(d.split("/")[-1])
        except (ValueError, IndexError):
            y = 0
        for w, y0, y1 in WINDOWS:
            if y0 <= y <= y1:
                a[f"so_lo_{w}"] += 1
                a[f"gia_tri_ty_{w}"] += r["gia_tri_phat_hanh_ty"]
    return agg


def write_agg_csv(path, agg, key, extra_issuer_count):
    cols = [key, "so_lo", "tong_gia_tri_ty", "first_date", "last_date"]
    cols += [f"so_lo_{w}" for w, _, _ in WINDOWS]
    cols += [f"gia_tri_ty_{w}" for w, _, _ in WINDOWS]
    cols += ["vai_tro"] + (["so_issuer_con"] if extra_issuer_count else [])

    def _write(f):
        w = csv.writer(f)
        w.writerow(cols)
        for k, a in sorted(agg.items(), key=lambda x: (-x[1]["tong_gia_tri_ty"], -x[1]["so_lo"])):
            row = [k, a["so_lo"], round(a["tong_gia_tri_ty"], 1),
                   a["first_date"], a["last_date"]]
            row += [a[f"so_lo_{w2}"] for w2, _, _ in WINDOWS]
            row += [round(a[f"gia_tri_ty_{w2}"], 1) for w2, _, _ in WINDOWS]
            row += [";".join(sorted(x for x in a["vai_tro"] if x))]
            if extra_issuer_count:
                row += [len(a["issuers"])]
            w.writerow(row)
    write_file_safe(path, _write)


# ---------- report ----------
def make_report(path, firm_key, cfg, freq_rows, bond_rows):
    internal = set(cfg.get("internal_groups", []))
    ext = [r for r in freq_rows if r[0] not in internal]
    tot_val = sum(r[2] for r in ext) or 1
    tot_lots = sum(r[1] for r in ext)
    top3 = sum(r[2] for r in ext[:3])
    top5 = sum(r[2] for r in ext[:5])
    int_val = sum(r[2] for r in freq_rows if r[0] in internal)

    L = []
    w = L.append
    w("# Khách hàng trái phiếu thường xuyên của %s — proxy từ HNX CBIS" % cfg["name"])
    w("")
    w("*Sinh tự động %s. Phương pháp & caveat: xem README.md (mục caveat áp dụng chung).*" % date.today().isoformat())
    w("")
    w("## Quy mô flag")
    w("")
    w("- **%d lô** / **%s tỷ VND** mệnh giá gắn dấu vết %s"
      % (tot_lots, fmt(tot_val), firm_key.upper()))
    if internal:
        w("  (đã tách nhóm nội bộ %s: %s tỷ)." % (", ".join(internal), fmt(int_val)))
    if cfg.get("anchor_note"):
        w("- %s" % cfg["anchor_note"])
    w("")
    w("## Top 15 khách hàng theo GIÁ TRỊ (parent group)")
    w("")
    w("| # | Nhóm | Số lô | Giá trị (tỷ) | First | Last | 2019-21 | 2022-23 | 2024-26 |")
    w("|---|------|------:|-------------:|-------|------|--------:|--------:|--------:|")
    for i, r in enumerate(ext[:15], 1):
        w("| %d | %s | %d | %s | %s | %s | %d | %d | %d |"
          % (i, r[0][:48], r[1], fmt(r[2]), r[3][:7], r[4][:7], r[5], r[6], r[7]))
    w("")
    by_lots = sorted(ext, key=lambda r: (-r[1], -r[2]))
    w("## Top 15 theo SỐ LÔ")
    w("")
    w("| # | Nhóm | Số lô | Giá trị (tỷ) |")
    w("|---|------|------:|-------------:|")
    for i, r in enumerate(by_lots[:15], 1):
        w("| %d | %s | %d | %s |" % (i, r[0][:48], r[1], fmt(r[2])))
    w("")
    w("## Mức tập trung")
    w("")
    w("- Top 3 = **%.0f%%** tổng giá trị flag; top 5 = **%.0f%%**." % (100 * top3 / tot_val, 100 * top5 / tot_val))
    w("")
    if bond_rows:
        cnt = {}
        for b in bond_rows:
            k = b["evidence_check"].split(":")[0]
            cnt[k] = cnt.get(k, 0) + 1
        confirmed = cnt.get("confirmed", 0)
        other = cnt.get("other_firm", 0)
        w("## Đối chiếu bằng chứng PDF kết quả chào bán (arranger_evidence)")
        w("")
        w("| Trạng thái | Số lô | Ý nghĩa |")
        w("|---|---:|---|")
        w("| confirmed | %d | PDF nêu đích danh công ty (kết luận được vai trò) |" % confirmed)
        w("| other_firm | %d | PDF nêu công ty KHÁC → proxy lưu ký sai, cần loại khi đếm origination |" % other)
        w("| doc_no_table | %d | có PDF nhưng là thông báo ngắn, không có bảng tổ chức |" % cnt.get("doc_no_table", 0))
        w("| no_doc | %d | chưa có/chưa đọc tài liệu |" % cnt.get("no_doc", 0))
        w("")
        others = sorted({b["evidence_check"].split(":", 1)[1]
                         for b in bond_rows if b["evidence_check"].startswith("other_firm")})
        if others:
            w("Các lô `other_firm` thuộc về: %s — xem cột `evidence_check` trong `bonds_raw.csv`." % ", ".join(others))
            w("")
    w("## Caveats")
    w("")
    w("1. Vai trò ≠ khách hàng origination — lọc bằng cột `vai_tro` + evidence Level 2.")
    w("2. Under-count: bond đã chuyển đăng ký về VSDC không còn hiện tên CTCK lưu ký cũ.")
    w("3. Mapping SPV→parent theo báo chí (xem confidence trong `data/spv_parent_map.csv`).")
    w("4. Dữ liệu CBIS dày từ 2023; đầy đủ hơn từ 2025 (TT 76/2024/TT-BTC).")
    write_file_safe(path, lambda f: f.write("\n".join(L)), encoding="utf-8")


def main():
    if len(sys.argv) < 2:
        print("usage: analyze_firm.py <firm_key>")
        sys.exit(1)
    key = sys.argv[1]
    cfg = firm_get(key)
    firm_re = firm_identity_re(cfg)
    out = firm_out_dir(key)
    os.makedirs(out, exist_ok=True)

    rows, hits = flag_bonds(firm_re)
    rules = load_spv_rules()

    # ---- Signal C + doi chieu: bang arranger evidence toan thi truong ----
    canon = cfg.get("canonical", key.upper())
    ev = load_arranger_evidence()
    flagged_codes = {r["ma_tp"] for r in rows}
    # C1: evidence neu dich danh cong ty o lo CHUA flag -> them vao
    master = {}
    with open(MASTER, encoding="utf-8-sig") as f:
        for m in csv.DictReader(f):
            master[m["ma_tp"].strip().upper()] = m
    for code, roles in ev.items():
        ev_roles_hit = sorted(k for k, v in roles.items() if v == canon)
        if not ev_roles_hit or code in flagged_codes:
            continue
        m = master.get(code, {})
        rows.append({
            "ma_tp": code,
            "to_chuc_phat_hanh": m.get("to_chuc_phat_hanh", ""),
            "parent_group": "", "mapped_by_keyword": 0,
            "ngay_phat_hanh": m.get("ngay_phat_hanh", ""),
            "ngay_dao_han": m.get("ngay_dao_han", ""),
            "menh_gia": m.get("menh_gia", ""),
            "kl_phat_hanh": m.get("kl_phat_hanh", ""),
            "gia_tri_phat_hanh_ty": round(num(m.get("menh_gia", "")) * num(m.get("kl_phat_hanh", "")) / 1e9, 2),
            "lai_suat_phat_hanh": m.get("lai_suat_phat_hanh", ""),
            "ky_han": m.get("ky_han", ""),
            "tinh_trang": m.get("tinh_trang", ""),
            "vai_tro": ";".join(ev_roles_hit),
            "nguon": "level2:pdf",
            "n_articles": 0,
            "in_master": int(bool(m)),
            "sample_title": "",
        })
    # C2: cot doi chieu per-lot cho MOI dong (ke ca flag boi proxy)
    for r in rows:
        e = ev.get(r["ma_tp"])
        if e is None:
            r["pdf_bao_lanh"] = r["pdf_tu_van"] = r["pdf_dai_dien_nshtp"] = ""
            r["evidence_check"] = "no_doc"
            continue
        r["pdf_bao_lanh"] = e.get("bao_lanh", "")
        r["pdf_tu_van"] = e.get("tu_van", "")
        r["pdf_dai_dien_nshtp"] = e.get("dai_dien_nshtp", "")
        named = {v for v in e.values() if v}
        if canon in named:
            r["evidence_check"] = "confirmed"
            r["vai_tro"] = ";".join(sorted(set(r["vai_tro"].split(";"))
                                           | {k for k, v in e.items() if v == canon}))
        elif named:
            r["evidence_check"] = "other_firm:" + ",".join(sorted(named))
        else:
            r["evidence_check"] = "doc_no_table"

    for r in rows:
        r["parent_group"] = map_parent(r["to_chuc_phat_hanh"], rules)
        r["mapped_by_keyword"] = int(r["parent_group"] != r["to_chuc_phat_hanh"])

    def _write_bonds(f):
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    if rows and not write_file_safe(os.path.join(out, "bonds_raw.csv"), _write_bonds):
        sys.exit(2)

    if hits:
        def _write_hits(f):
            w = csv.DictWriter(f, fieldnames=list(hits[0].keys()))
            w.writeheader(); w.writerows(hits)
        write_file_safe(os.path.join(out, "feed_hits.csv"), _write_hits)

    write_agg_csv(os.path.join(out, "issuer_frequency.csv"),
                  aggregate(rows, "parent_group"), "parent_group", True)
    write_agg_csv(os.path.join(out, "issuer_frequency_raw.csv"),
                  aggregate(rows, "to_chuc_phat_hanh"), "to_chuc_phat_hanh", False)

    # doc lai freq (dang list tuple) cho report
    freq_rows = []
    with open(os.path.join(out, "issuer_frequency.csv"), encoding="utf-8-sig") as f:
        rd = csv.reader(f)
        next(rd)
        for v in rd:
            freq_rows.append([v[0], int(v[1]), float(v[2]), v[3], v[4],
                              int(v[5]), int(v[6]), int(v[7])])
    make_report(os.path.join(out, "report.md"), key, cfg, freq_rows, rows)
    n_conf = sum(1 for r in rows if r["evidence_check"] == "confirmed")
    n_other = sum(1 for r in rows if r["evidence_check"].startswith("other_firm"))
    print("%s: %d bond flagged (confirmed=%d, other_firm=%d) -> %s/"
          % (key, len(rows), n_conf, n_other, out))


if __name__ == "__main__":
    main()
