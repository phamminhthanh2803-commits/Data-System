# -*- coding: utf-8 -*-
"""Boc bang "cac to chuc lien quan" tu PDF ket qua chao ban — TOAN THI TRUONG.

Voi moi dot phat hanh trong registry (ttph.csv): tai PDF, doc text (pdfplumber,
fallback OCR tesseract vie), tim tung nhan vai tro va bat TEN TO CHUC dung sau,
chuan hoa ve canonical (org_canon.py). Ket qua la bang arranger cap van ban goc
dung chung cho moi cong ty:

    data/processed/arranger_evidence.csv
    ma_tp, ten_dn, ngay_phat_hanh, method, doc_url,
    tu_van / bao_lanh / dai_ly_phat_hanh / dai_ly_dang_ky_luu_ky /
    dai_ly_thanh_toan / dai_dien_nshtp / quan_ly_tsbd   (canonical)
    + cot *_raw (chuoi goc tu PDF de audit)

Text da extract cache o data/raw/pdf_text/<ma_tp>.txt (doi regex khong can
OCR lai). Resumable: bo qua ma_tp da co trong output.

Usage: python scripts/extract_arrangers.py [--limit N]
Uu tien doc 2021-2023 truoc (mau ND153 co bang to chuc; mau 2024+ thuong khong).
"""
import argparse
import csv
import io
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("TESSDATA_PREFIX", os.path.join(_ROOT, "tessdata"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hnx_common import BASE, make_session, polite_sleep, write_file_safe

import unicodedata
from rapidfuzz import fuzz

# ---- chuan hoa ten to chuc ve canonical (chiu noise OCR) ----
# canonical -> alias (khong dau, lowercase); alias co "(" duoc coi la regex
ALIASES = {
    "TCBS": ["chung khoan ky thuong", "techcom securities", "tcbs"],
    "TVSI": ["chung khoan tan viet", "tvsi"],
    "VPS": ["chung khoan vps"],
    "MBS": ["chung khoan mb", "chung khoan mbs"],
    "SSI": ["chung khoan ssi"],
    "VNDIRECT": ["vndirect", "vn direct"],
    "HDBS": ["chung khoan hd"],
    "KBSV": ["chung khoan kb"],
    "SHS": ["chung khoan sai gon - ha noi", "chung khoan shs"],
    "BSC": ["chung khoan bidv", "chung khoan ngan hang dau tu va phat trien"],
    "VCBS": ["chung khoan ngan hang tmcp ngoai thuong", "chung khoan vietcombank", "vcbs"],
    "ACBS": ["chung khoan acb"],
    "VPBankS": ["chung khoan vpbank", "chung khoan ngan hang tmcp viet nam thinh vuong"],
    "PSI": ["chung khoan dau khi"],
    "CTS": ["chung khoan cong thuong", "chung khoan ngan hang cong thuong", "vietinbank securities"],
    "FPTS": ["chung khoan fpt"],
    "Vietcap": ["chung khoan vietcap", "chung khoan ban viet"],
    "HSC": ["chung khoan thanh pho ho chi minh", "chung khoan tp hcm", "chung khoan tp. ho chi minh"],
    "KIS": ["chung khoan kis"],
    "TPS": ["chung khoan tien phong", "orient"],
    "BVSC": ["chung khoan bao viet"],
    "Agriseco": ["chung khoan agribank", "agriseco", "chung khoan ngan hang nong nghiep"],
    "MiraeAsset": ["mirae asset"],
    "Everest": ["chung khoan everest"],
    "APG": ["chung khoan apg"],
    "SmartInvest": ["smart invest"],
    "DSC": ["chung khoan dsc"],
    "VIX": ["chung khoan vix"],
    "ThanhCong": ["chung khoan thanh cong"],
    "SmartMind": ["smartmind"],
    "DNSE": ["chung khoan dnse", "dai nam"],
    "VDSC": ["chung khoan rong viet"],
    "VFS": ["chung khoan nhat viet"],
    "PHS": ["chung khoan phu hung"],
    "Yuanta": ["chung khoan yuanta"],
    "Maybank": ["chung khoan maybank", "kim eng"],
    "APS": ["chung khoan chau a - thai binh duong", "chau a thai binh duong"],
    "TVB": ["chung khoan tri viet"],
    "ASEAN": ["chung khoan asean"],
    "VIS": ["chung khoan quoc te viet nam"],
    "SBSI": ["stanley brothers"],
    "BMSC": ["chung khoan bao minh"],
    "NSI": ["chung khoan quoc gia"],
    "PineTree": ["pinetree"],
    "GTJA": ["guotai junan"],
    "IVS": ["chung khoan dau tu viet nam"],
    "VBSC": ["chung khoan viet bac"],
    "CSI": ["chung khoan kien thiet"],
    "EuroCapital": ["chung khoan eurocapital"],
    "Techcombank": ["ngan hang tmcp ky thuong", "techcombank"],
    "MB Bank": ["ngan hang thuong mai co phan quan doi", "ngan hang tmcp quan doi"],
    "TPBank": ["ngan hang tmcp tien phong"],
    "BIDV": ["ngan hang tmcp dau tu va phat trien"],
    "MSB": ["ngan hang tmcp hang hai"],
    "SCB": ["ngan hang tmcp sai gon(?! thuong)", "ngan hang sai gon"],
    "VSDC": ["luu ky va bu tru chung khoan"],
    "ACB Bank": ["ngan hang tmcp a chau"],
    "VIB": ["ngan hang tmcp quoc te"],
    "OCB": ["ngan hang tmcp phuong dong"],
    "LPBank": ["ngan hang tmcp loc phat", "lien viet", "buu dien lien viet"],
    "BacABank": ["ngan hang tmcp bac a"],
    "NamABank": ["ngan hang tmcp nam a"],
    "ABBank": ["ngan hang tmcp an binh"],
    "Vietcombank": ["ngan hang tmcp ngoai thuong"],
    "VietinBank": ["ngan hang tmcp cong thuong"],
    "HDBank": ["ngan hang tmcp phat trien thanh pho ho chi minh", "hdbank"],
    "VPBank": ["ngan hang tmcp viet nam thinh vuong"],
    "SHB": ["ngan hang tmcp sai gon - ha noi"],
    "Sacombank": ["ngan hang tmcp sai gon thuong tin", "sai gon tai loc"],
    "SeABank": ["ngan hang tmcp dong nam a"],
    "Eximbank": ["ngan hang tmcp xuat nhap khau"],
    "VietABank": ["ngan hang tmcp viet a"],
    "NCB": ["ngan hang tmcp quoc dan"],
    "PVcomBank": ["dai chung viet nam"],
    "Shinhan": ["shinhan viet nam"],
}

# canonical KHONG phai CTCK (ngan hang/VSDC) — dung o build_timeline
BANKS = {"Techcombank", "MB Bank", "TPBank", "BIDV", "MSB", "SCB", "VSDC",
         "ACB Bank", "VIB", "OCB", "LPBank", "BacABank", "NamABank", "ABBank",
         "Vietcombank", "VietinBank", "HDBank", "VPBank", "SHB", "Sacombank",
         "SeABank", "Eximbank", "VietABank", "NCB", "PVcomBank", "Shinhan"}


def _strip_accents(s):
    s = s.replace("Đ", "D").replace("đ", "d")
    return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode()


def _norm(s):
    s = re.sub(r"\s+", " ", _strip_accents(s).lower()).strip()
    return s.replace("thuong mai co phan", "tmcp")


def canonicalize(raw, fuzzy=True):
    """raw org string tu PDF -> (canonical, score) hoac ("", 0)."""
    n = _norm(raw)
    if not n:
        return "", 0
    for canon, aliases in ALIASES.items():
        for a in aliases:
            if re.search(a, n) if ("(" in a) else (a in n):
                return canon, 100
    if not fuzzy:
        return "", 0
    best, best_score = "", 0
    for canon, aliases in ALIASES.items():
        for a in aliases:
            sc = fuzz.partial_ratio(re.sub(r"\(.*?\)", "", a), n)
            if sc > best_score:
                best, best_score = canon, sc
    return (best, best_score) if best_score >= 86 else ("", 0)

import fitz
import pdfplumber
import pytesseract
from PIL import Image

_TESS_WIN = os.path.normpath("C:/Program Files/Tesseract-OCR/tesseract.exe")
pytesseract.pytesseract.tesseract_cmd = os.environ.get("TESSERACT_CMD") or (_TESS_WIN if os.path.exists(_TESS_WIN) else "tesseract")

PDF_DIR = "data/raw/pdfs"
TXT_DIR = "data/raw/pdf_text"
OUT = "data/processed/arranger_evidence.csv"
MAX_OCR_PAGES = 10

ROLES = [
    ("tu_van", r"t[ổôo]\s*ch[ứu]c\s*t[ưu]\s*v[ấâa]n(?:\s*h[ồôo]\s*s[ơo])?(?:\s*(?:ph[áa]t\s*h[àa]nh|ch[àa]o\s*b[áa]n))?"),
    ("bao_lanh", r"(?:t[ổôo]\s*ch[ứu]c\s*)?b[ảa]o\s*l[ãa]nh\s*ph[áa]t\s*h[àa]nh"),
    ("dai_ly_phat_hanh", r"[đd][ạa]i\s*l[ýy]\s*ph[áa]t\s*h[àa]nh"),
    ("dai_ly_dang_ky_luu_ky", r"(?:[đd][ạa]i\s*l[ýy]|t[ổôo]\s*ch[ứu]c)\s*[đd][ăâa]ng\s*k[ýy](?:[,\s]*(?:t[ổôo]\s*ch[ứu]c\s*)?l[ưu]u\s*k[ýy])?|(?:v[àa]\s*)?[đd][ăâa]ng\s*k[ýy],?\s*l[ưu]u\s*k[ýy]\s*tr[áa]i\s*phi[ếêe]u"),
    ("dai_ly_thanh_toan", r"[đd][ạa]i\s*l[ýy]\s*thanh\s*to[áa]n"),
    ("dai_dien_nshtp", r"[đd][ạa]i\s*di[ệêe]n\s*ng[ưu][ờơo]i\s*s[ởơo]\s*h[ữưu]u"),
    ("quan_ly_tsbd", r"(?:[đd][ạa]i\s*l[ýy]\s*)?qu[ảa]n\s*l[ýy]\s*t[àa]i\s*s[ảa]n\s*b[ảa]o\s*[đd][ảa]m"),
]

ORG_START = r"(?:c[ôoóỏõọ]ng\s*ty|CTCP|ng[âaàáảãạ]n\s*h[àaáảãạ]ng|t[ổôo]ng\s*c[ôo]ng\s*ty)"
ORG_STOP = r"(?:[ĐD][ịi]a\s*ch[ỉi]|S[ốô]\s*(?:fax|[đd]i[ệe]n)|[ĐD]i[ệe]n\s*tho[ạa]i|MST|Gi[ấâa]y|Website|Email|T[ầâa]ng\s*\d|$)"

FIELDS = ["ma_tp", "ten_dn", "ngay_phat_hanh", "method", "doc_url"]
for r_, _ in ROLES:
    FIELDS += [r_, r_ + "_raw"]


def extract_text(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            txt = "\n".join((p.extract_text() or "") for p in pdf.pages)
        if len(txt.strip()) > 300:
            return txt, "text"
    except Exception as e:
        print("  pdfplumber fail:", e)
    try:
        doc = fitz.open(pdf_path)
        out = []
        for p in list(doc)[:MAX_OCR_PAGES]:
            pix = p.get_pixmap(dpi=200)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            out.append(pytesseract.image_to_string(img, lang="vie"))
        return "\n".join(out), "ocr"
    except Exception as e:
        print("  ocr fail:", e)
        return "", "fail"


def parse_orgs(txt):
    """Voi moi vai tro, bat ten to chuc dung sau nhan -> {role: (canon, raw)}."""
    found = {}
    for role, pat in ROLES:
        for m in re.finditer(pat, txt, re.I):
            window = txt[m.end():m.end() + 300]
            # ten to chuc co the bi OCR xuong dong giua chung -> vá newline don
            window = re.sub(r"\n(?!\n)", " ", window)
            mv = re.search(r"[:\-–]?\s*(" + ORG_START + r"[^\n]{5,140})", window, re.I)
            if not mv:
                continue
            raw = re.split(ORG_STOP, mv.group(1))[0]
            raw = re.sub(r"\s+", " ", raw).strip(" .,:;-")
            if len(raw) < 8:
                continue
            canon, score = canonicalize(raw)
            # giu ket qua tot nhat cho moi vai tro (uu tien co canonical)
            cur = found.get(role)
            if cur is None or (not cur[0] and canon):
                found[role] = (canon, raw)
            if canon:
                break
    return found


def load_evidence():
    rows, by_code = [], {}
    if os.path.exists(OUT):
        rows = list(csv.DictReader(open(OUT, encoding="utf-8-sig")))
        by_code = {r["ma_tp"]: r for r in rows}
    return rows, by_code


def save_evidence(rows):
    def _write(f):
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(rows)
    write_file_safe(OUT, _write)


def cmd_articles(limit):
    """Vet cac lo CHUA co vai tro nao: doc file dinh kem tin CBTT cua chinh lo
    do (thay doi dieu kien/dai dien... thuong neu ten CTCK). Merge vao OUT."""
    rows, by_code = load_evidence()
    resolved = {c for c, r in by_code.items()
                if any(r.get(role) for role, _ in ROLES)}
    feed = list(csv.DictReader(open("data/processed/feed.csv", encoding="utf-8-sig")))
    # nhom article theo ma TP chua resolved; uu tien tin de co ten to chuc
    PRIO = re.compile(r"đại diện|điều kiện|điều khoản|đại lý|trách nhiệm", re.I)
    by_bond = {}
    for r in feed:
        code = r["ma_tp_lien_quan"].strip().upper()
        if not code or code in resolved or not r["article_id"]:
            continue
        by_bond.setdefault(code, []).append(r)
    todo = []
    for code, arts in by_bond.items():
        arts.sort(key=lambda a: (0 if PRIO.search(a["tieu_de"]) else 1, a["ngay_dang"]))
        todo.append((code, arts[:2]))  # toi da 2 tin/lo
    # da xu ly article nao roi thi bo qua (txt cache theo article id)
    todo = [(c, a) for c, a in todo
            if any(not os.path.exists(os.path.join(TXT_DIR, "art_%s.txt" % x["article_id"])) for x in a)]
    todo.sort(key=lambda x: x[0])
    todo = todo[:limit]
    print("articles mode: %d lo chua resolved co tin, xu ly %d lo dot nay"
          % (len(by_bond), len(todo)), flush=True)
    if not todo:
        return

    sess, token = make_session("/to-chuc-phat-hanh/tin-cong-bo")
    n_filled = 0
    for i, (code, arts) in enumerate(todo, 1):
        found = {}
        for a in arts:
            aid = a["article_id"]
            txt_path = os.path.join(TXT_DIR, "art_%s.txt" % aid)
            if os.path.exists(txt_path):
                txt = open(txt_path, encoding="utf-8").read()
            else:
                txt = ""
                try:
                    r = sess.get(BASE + "/article/chi-tiet", params={"id": aid},
                                 headers={"CP-TOKEN": token}, timeout=30)
                    polite_sleep()
                    urls = re.findall(r'href="(https?://owa\.hnx\.vn/[^"]+)"', r.text)
                    if urls:
                        fn = os.path.join(PDF_DIR, "art_%s.pdf" % aid)
                        if not os.path.exists(fn):
                            pr = sess.get(urls[0], timeout=120)
                            open(fn, "wb").write(pr.content)
                            polite_sleep()
                        txt, _ = extract_text(fn)
                    open(txt_path, "w", encoding="utf-8").write(txt or "")
                except Exception as e:
                    print("  fail art %s: %s" % (aid, e), flush=True)
                    continue
            if txt:
                for role, (canon, raw) in parse_orgs(txt).items():
                    if role not in found and canon:
                        found[role] = (canon, raw)
        if found:
            rec = by_code.get(code)
            if rec is None:
                rec = dict.fromkeys(FIELDS, "")
                rec.update({"ma_tp": code, "ten_dn": arts[0]["ten_doanh_nghiep"],
                            "ngay_phat_hanh": ""})
                rows.append(rec)
                by_code[code] = rec
            for role, (canon, raw) in found.items():
                if not rec.get(role):
                    rec[role] = canon
                    rec[role + "_raw"] = ("[art] " + raw)[:140]
            rec["method"] = (rec.get("method") or "") + "+article"
            n_filled += 1
        print("%4d/%d %s %s" % (i, len(todo), code,
              {k: v[0] for k, v in found.items()} or "-"), flush=True)
        if i % 10 == 0 or i == len(todo):
            save_evidence(rows)
    print("articles done: fill duoc %d lo" % n_filled)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--articles", action="store_true",
                    help="doc file dinh kem tin CBTT cho cac lo chua co vai tro")
    args = ap.parse_args()

    os.makedirs(PDF_DIR, exist_ok=True)
    os.makedirs(TXT_DIR, exist_ok=True)

    if args.articles:
        cmd_articles(args.limit)
        return

    ttph = []
    seen_code = set()
    for r in csv.DictReader(open("data/processed/ttph.csv", encoding="utf-8-sig")):
        code = r["ma_tp"].strip().upper()
        if r["file"] and code and code not in seen_code:
            seen_code.add(code)
            ttph.append(r)

    rows, done = [], set()
    if os.path.exists(OUT):
        rows = list(csv.DictReader(open(OUT, encoding="utf-8-sig")))
        done = {r["ma_tp"] for r in rows}

    def year(r):
        try:
            return int(r["ngay_phat_hanh"].split("/")[-1])
        except (ValueError, IndexError):
            return 0

    todo = [r for r in ttph if r["ma_tp"].strip().upper() not in done]
    # uu tien: (1) PDF da cache (khong ton download), (2) mau ND153 2021-2023
    cached = {f.split("_")[0] for f in os.listdir(PDF_DIR)} if os.path.isdir(PDF_DIR) else set()
    todo.sort(key=lambda r: (0 if r["ma_tp"].strip().upper() in cached else 1,
                             0 if 2021 <= year(r) <= 2023 else 1, year(r) or 9999))
    todo = todo[:args.limit]
    print("arranger backlog: %d chua doc, xu ly %d dot nay" % (
        len(ttph) - len(done), len(todo)), flush=True)
    if not todo:
        return

    sess = token = None
    for i, r in enumerate(todo, 1):
        code = r["ma_tp"].strip().upper()
        txt_path = os.path.join(TXT_DIR, code + ".txt")
        rec = dict.fromkeys(FIELDS, "")
        rec.update({"ma_tp": code, "ten_dn": r["ten_dn"],
                    "ngay_phat_hanh": r["ngay_phat_hanh"]})
        txt, method, url = "", "", ""
        if os.path.exists(txt_path):
            txt, method = open(txt_path, encoding="utf-8").read(), "cache"
        else:
            if sess is None:
                sess, token = make_session("/to-chuc-phat-hanh/thong-tin-phat-hanh")
            ref, ttype = r["file"].split("|")
            vf = sess.get(BASE + "/view-file", params={"refId": ref, "tableType": ttype},
                          headers={"CP-TOKEN": token}, timeout=30)
            urls = re.findall(r'href="(https://owa\.hnx\.vn/ftp/[^"]+)"', vf.text)
            polite_sleep()
            if urls:
                url = urls[0]
                fn = os.path.join(PDF_DIR, code + "_" + os.path.basename(url).split("_")[0] + ".pdf")
                if not os.path.exists(fn):
                    try:
                        pr = sess.get(url, timeout=120)
                        open(fn, "wb").write(pr.content)
                    except Exception as e:
                        print("  download fail %s: %s" % (code, e))
                        fn = None
                    polite_sleep()
                if fn and os.path.exists(fn):
                    txt, method = extract_text(fn)
                    if txt:
                        open(txt_path, "w", encoding="utf-8").write(txt)
        rec["method"] = method
        rec["doc_url"] = url
        if txt:
            for role, (canon, raw) in parse_orgs(txt).items():
                rec[role] = canon
                rec[role + "_raw"] = raw[:140]
        rows.append(rec)
        hits = {k: v for k, v in rec.items()
                if k in dict(ROLES) and v}
        print("%4d/%d %s [%s] %s" % (i, len(todo), code, method, hits or "-"),
              flush=True)
        if i % 10 == 0 or i == len(todo):
            def _write(f):
                w = csv.DictWriter(f, fieldnames=FIELDS)
                w.writeheader(); w.writerows(rows)
            write_file_safe(OUT, _write)
    print("done: %d/%d dot da co evidence" % (len(rows), len(ttph)))


if __name__ == "__main__":
    main()
