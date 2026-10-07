# -*- coding: utf-8 -*-
"""
md2bctc — Chuyển BCTC dạng Markdown (OCR) của Công ty Chứng khoán (mẫu B0x-CTCK)
          thành CSV long-format + metadata để tra cứu / SQL / lookup.

Usage:
    python md2bctc.py <input.md> [--ticker SSI] [--year 2016] [--outdir D:\\bctc\\md2bctc\\output]

Output (trong outdir):
    <ticker>_<year>_bctc_long.csv   -> 1 dòng / (báo cáo, mã số, kỳ)  [chính, dùng cho SQL]
    <ticker>_<year>_bctc_wide.csv   -> dạng bảng dễ đọc (mã số + 2 cột kỳ)
    <ticker>_<year>_bctc_meta.csv   -> metadata 1 dòng (công ty, năm, đơn vị...)

Thiết kế cho mẫu CTCK (B01/B02/B03/B04). Parse thuần regex, không cần API.
"""

import sys
import os
import glob
import re
import csv
import argparse
import unicodedata
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ----------------------------------------------------------------------------
# 1. Regex nền
# ----------------------------------------------------------------------------

# Một số tiền VN: 1-3 chữ số rồi >=1 nhóm 3 chữ số (ngăn bằng '.', ',' hoặc space do OCR),
# có thể bọc trong ngoặc (số âm). Trong 3 BC chính giá trị luôn là số nguyên VND nên
# dấu ',' được coi là dấu ngăn nghìn (lỗi OCR thay cho '.'), KHÔNG phải thập phân.
# Yêu cầu >=1 nhóm 3 -> luôn >=4 chữ số -> loại được mã số & số thuyết minh.
# Dấu ngăn nhóm 3 chữ số: '.' / ',' (OCR) / '..' / '. ' / ' .' / 1 space đơn.
# QUAN TRỌNG: KHÔNG cho 2 space liền làm sep -> tránh nối nhầm 2 cột sát nhau
# (vd '...818  214.303...' là 2 số ở 2 cột, không phải 1 số).
_SEP = r"(?:\.\.|[.,]\s?|\s[.,]|\s(?!\s))"
AMOUNT_RE = re.compile(r"\(?\s*-?\d{1,3}(?:" + _SEP + r"\d{3})+\s*\)?")

# Mã số ở đầu dòng (sau '|' và khoảng trắng): 1-4 số (4 số = OCR của 'ddd.d'),
# tùy chọn '.xxx' và hậu tố chữ.
CODE_RE = re.compile(r"^\s*\|?\s*(\d{1,4}(?:\.\d{1,3})?[a-zA-Z]?)(?=[\s|]|$)")

# Mã số kiểu outline cho B04 (biến động vốn): '1.', '1.1.', '6.1.' ...
B04_CODE_RE = re.compile(r"^\s*\|?\s*(\d{1,2}(?:\.\d{1,2})?)\.?\s+(?=[A-Za-zÀ-ỹ])")

# Dòng tổng không có mã số (TỔNG CỘNG TÀI SẢN / NGUỒN VỐN ...).
TOTAL_RE = re.compile(r"T[OỔ]NG\s*C[OỘ]NG", re.IGNORECASE)

# Số thuyết minh: 1-2 số, tùy chọn '.1' / '.11' (KHÔNG phải nhóm 3 chữ số).
NOTE_RE = re.compile(r"\d{1,2}(?:\.\d{1,2})?$")

# Mã form trong header trang.
FORM_RE = re.compile(r"B0(\d)([a-z]?)\s*-?\s*CTCK", re.IGNORECASE)

# Dòng header/footer/chữ ký cần bỏ qua khi đọc bảng.
# Lưu ý: các pattern phải đủ chặt để KHÔNG nuốt nhầm tên chỉ tiêu
# (vd "công ty con", "lợi nhuận kế toán trước thuế").
HEADER_RE = re.compile(
    r"(VND"
    r"|CH[IÍỈ]\s*TI[EÊ]U"
    r"|Thuy[eêé]?t\s*minh"
    r"|^\s*minh\b"
    r"|^\s*M[ãa]\s*s[oố6]?\s*\|"
    r"|B0\d[a-z]?\s*-?\s*CTCK"
    r"|C[oôéổ]ng\s*ty\s*C[oôổ]\s*ph[aâầ]n\s*Ch[uứ]ng"   # 'Công ty Cổ phần Chứng' (header cty)
    r"|B[AÁ]O\s+C[AÁ]O\s+(TINH|T[IÌ]NH|KET|K[EẾ]T|L[UƯ]U)"  # tiêu đề báo cáo
    r"|THUY[EẾ]T\s*MINH\s*B[AÁ]O"
    r"|\(ti[eéê]p\s*theo\)"
    r"|N[aă]m\s*tr[uươ][oớ]c"
    r"|N[aă]m\s*nay\b"
    r"|S[oôố6]\s*(cu[oôố]i|[dđ][aâ]u)\b"               # 'Số cuối/đầu (năm)' header cột
    r"|^\s*Kh[oôố]i\s*l[uươ][oợ]ng"                     # header 'Khối lượng'
    r"|tr[iì]nh\s*b[aà]y\s*l[aạ]i"
    r"|cho\s*n[aă]m\s*t[aà]i\s*ch"
    r"|t[aạ]i\s*ng[aà]y\s*31"
    r"|K[eế]\s*to[aá]n\s*Tr[uư][oơ]?[nờ]?ng"             # 'Kế toán Trưởng' (chữ ký)
    r"|Gi[aá]m\s*[dđ][oốé]c\s*T[aà]i\s*ch"               # 'Giám đốc Tài chính'
    r"|T[oổ]ng\s*Gi[aá]m\s*[dđ]"                          # 'Tổng Giám đốc'
    r"|Th[aà]nh\s*ph[oốé]\s*H[oồ]\s*Ch[ií]\s*Minh"
    r"|Ng[aà]y\s*\d+\s*th[aá]ng\s*\d+\s*n[aă]m"
    r")",
    re.IGNORECASE,
)

# Mốc bắt đầu phần lưu chuyển tiền của khách hàng (trong B03) — so khớp sau khi bỏ dấu.
CLIENT_CF_RE = re.compile(r"PHAN\s+LUU\s+CHUYEN.*M[O0]I\s*GI[O0]I", re.IGNORECASE)

# Tiêu đề mục thuyết minh: '<số>.  <Tiêu đề>' (vd '5.  TIỀN...', '7.1', '281'→28.1).
# Cho phép mã 1-3 chữ số (OCR hay gộp '7.1'->'71', '28.1'->'281') và tới 3 cấp ('3.4.1').
NOTE_HEADING_RE = re.compile(r"^\s+(\d{1,3}(?:\.\d{1,3}){0,2})\.?\s{2,}([A-Za-zÀ-ỹ].{2,})$")

# Từ khoá nhận diện DÒNG TIÊU ĐỀ CỘT trong note (để bỏ, không lẫn vào nhãn).
NOTE_HDR_WORDS = ["gia goc", "ghi so", "hop ly", "gia mua", "gia ban", "so luong",
                  "khoi luong", "don vi", "chenh lech", "so du", "tang trong",
                  "giam trong", "so phat sinh", "so trich", "so hoan", "muc dich",
                  "dien giai", "ty le", "lai suat", "nam nay", "nam truoc",
                  "so cuoi", "so dau", "trinh bay", "binh quan", "thoi gian"]

# Dòng chú thích/footnote cần bỏ khỏi bảng số.
FOOTNOTE_RE = re.compile(r"^\s*[\(\[][\*\d]+[\)\]]")

FORM_NAME = {
    "B01": ("balance_sheet", "Bao cao tinh hinh tai chinh"),
    "B02": ("income_statement", "Bao cao ket qua hoat dong"),
    "B03": ("cash_flow", "Bao cao luu chuyen tien te"),
    "B04": ("equity_changes", "Bao cao bien dong von chu so huu"),
}

# Cặp nhãn kỳ (current_left, prior_right) theo từng báo cáo.
PERIOD_DESC = {
    "balance_sheet": ("So cuoi nam", "So dau nam"),
    "income_statement": ("Nam nay", "Nam truoc"),
    "cash_flow": ("Nam nay", "Nam truoc"),
    "cash_flow_client": ("Nam nay", "Nam truoc"),
    "equity_changes": ("", ""),
}


# ----------------------------------------------------------------------------
# 2. Tách trang & xác định báo cáo
# ----------------------------------------------------------------------------

def strip_accents(s):
    s = s.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def split_pages(text):
    """Trả về list (page_no, [lines]) từ các block ```text``` theo marker trang."""
    pages = []
    cur_no = None
    in_block = False
    buf = []
    page_marker = re.compile(r"<!--\s*trang\s*(\d+)", re.IGNORECASE)
    for line in text.splitlines():
        m = page_marker.search(line)
        if m:
            cur_no = int(m.group(1))
            continue
        s = line.strip()
        if s.startswith("```"):
            if in_block:
                pages.append((cur_no, buf))
                buf = []
                in_block = False
            else:
                in_block = True
                buf = []
            continue
        if in_block:
            buf.append(line)
    if in_block and buf:
        pages.append((cur_no, buf))
    return pages


# Nhận diện loại báo cáo (format mới) theo TIÊU ĐỀ trong trang — đáng tin hơn mã
# form ở góc (OCR hay ghi sai, vd trang bảng CĐKT lại in 'B02').
# OCR hay sai 'ĐỘNG'->'BONG' nên dùng pattern lỏng, chịu lỗi.
# B01 XÉT CUỐI: 'TÌNH HÌNH TÀI CHÍNH' hay là running-header trên mọi trang
# (báo cáo 'riêng giữa niên độ'); tiêu đề KQKD/LCTT/VCSH cụ thể hơn nên ưu tiên.
NEW_TITLE_PATTERNS = [
    ("B04", re.compile(r"BIEN\s*[DB]ONG\s*VON")),
    ("B01", re.compile(r"TINH\s*HINH\s*TAI\s*CHINH")),
    ("B02", re.compile(r"BAO\s*CAO\s*KET\s*QUA")),
    ("B03", re.compile(r"LUU\s*CHUYEN\s*TIEN")),
]


def detect_new_stmt(lines):
    """Mã báo cáo (B01..B04) suy từ tiêu đề trong ~10 dòng đầu trang; None nếu không có."""
    head = re.sub(r"\s+", " ", strip_accents(" ".join(lines[:10])).upper())
    for code, pat in NEW_TITLE_PATTERNS:
        if pat.search(head):
            return code
    return None


def page_form(lines):
    """Trả về mã form (B01..B04) nếu trang thuộc 1 trong 4 báo cáo, else None."""
    head = "\n".join(lines[:8])
    m = FORM_RE.search(head)
    if not m:
        return None
    code = "B0" + m.group(1)
    return code if code in FORM_NAME else None


def group_new_pages(pages):
    """
    Gom trang format mới theo TIÊU ĐỀ báo cáo (carry-forward cho trang tiếp theo
    không có tiêu đề). Bỏ qua mã form ở góc vì OCR hay sai.
    """
    groups, cur = [], None
    for pn, lines in pages:
        if is_note_page(lines):
            cur = None  # tới phần thuyết minh -> ngừng gom vào 4 BC
            continue
        st = detect_new_stmt(lines)
        if st is None:
            if cur is not None:
                cur[1].append((pn, lines))
            continue
        if cur and cur[0] == st:
            cur[1].append((pn, lines))
        else:
            cur = (st, [(pn, lines)])
            groups.append(cur)
    return groups


def doc_code_at_start(groups):
    """
    True nếu báo cáo có MÃ SỐ ở ĐẦU dòng (TT334/2016) -> dùng extract_statement.
    False nếu mã số nằm GIỮA dòng (TT210/2014 quý, dòng bắt đầu 'A.'/'I.'/'1.')
    -> dùng parser position-based. Xét theo phần Bảng CĐKT (mã 3 chữ số 100-499).
    """
    for form, pgs in groups:
        if form != "B01":
            continue
        big = tot = 0
        for _pn, lines in pgs:
            for ln in lines:
                if is_header(ln) or not AMOUNT_RE.search(ln):
                    continue
                tot += 1
                mm = CODE_RE.match(ln)
                if mm:
                    c = mm.group(1).split(".")[0]
                    if c.isdigit() and 100 <= int(c) <= 999:
                        big += 1
        return tot == 0 or big >= tot * 0.4
    return True  # không có B01 -> mặc định mã-đầu-dòng


def is_note_page(lines):
    """Trang thuyết minh: mã form B05/B06 ở góc, HOẶC tiêu đề 'THUYẾT MINH BÁO CÁO'."""
    head = "\n".join(lines[:8])
    m = FORM_RE.search(head)
    if m and m.group(1) in ("5", "6"):
        return True
    h = re.sub(r"\s+", " ", strip_accents(head).upper())
    return bool(re.search(r"THUYET MINH BAO CAO TAI CHINH", h))


# ----------------------------------------------------------------------------
# 3. Parse số
# ----------------------------------------------------------------------------

def clean_amount(tok):
    """'(2.492. 782.800)' -> -2492782800 ; '11.884,989.070.539' -> 11884989070539"""
    t = tok.strip()
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").strip()
    # bỏ mọi dấu ngăn nghìn (space, '.', ',') -> số nguyên
    digits = re.sub(r"[^\d]", "", t)
    val = int(digits) if digits else 0
    return -val if neg else val


DASH_CHARS = "-=–—~"


def parse_record(text):
    """
    Tách 1 record -> (name, note, [amounts]).
    Lấy TẤT CẢ số (theo thứ tự); cột giá trị lấy CẶP ĐẦU (số nằm trên dòng có mã),
    tránh lấy nhầm số của các dòng con/bullet phía dưới.
    Số thuyết minh = token ngắn ngay trước số đầu tiên.
    """
    matches = list(AMOUNT_RE.finditer(text))
    if not matches:
        return text.strip(), "", []

    amounts = [clean_amount(m.group()) for m in matches]
    first_amt_pos = matches[0].start()
    pre = text[:first_amt_pos]

    # Thuyết minh = token số ngắn cuối cùng trong phần 'pre' (bỏ qua dấu '-', '.', '|' cuối)
    note = ""
    pre_strip = pre.rstrip(" .|" + DASH_CHARS)
    nm = NOTE_RE.search(pre_strip)
    name_part = pre
    if nm:
        before = pre_strip[: nm.start()]
        if before == "" or before[-1] in (" |." + DASH_CHARS):
            note = nm.group()
            name_part = before

    name = re.sub(r"\s+", " ", name_part).strip(" .|:" + DASH_CHARS)
    return name, note, amounts


def assign_columns(amounts, raw_lines):
    """
    Gán (current, prior) từ danh sách số.
    - >=2 số: lấy cặp đầu (current=amounts[0], prior=amounts[1]).
    - 1 số: cột còn lại là '-' (rỗng). Xác định số thuộc cột nào theo vị trí
            dấu '-' trên dòng chứa số: dấu '-' nằm BÊN TRÁI số -> số là cột đầu kỳ (prior).
    """
    if len(amounts) >= 2:
        return amounts[0], amounts[1]
    if len(amounts) == 1:
        val = amounts[0]
        line = ""
        for ln in raw_lines:
            if AMOUNT_RE.search(ln):
                line = ln
                break
        if line:
            m = AMOUNT_RE.search(line)
            before = line[: m.start()].rstrip()
            # dấu '-' đứng riêng ngay trước số (cách bằng khoảng trắng) -> cột current rỗng
            if before and before[-1] in DASH_CHARS and (len(before) < 2 or before[-2] == " "):
                return None, val
        return val, None
    return None, None


def is_header(line):
    return bool(HEADER_RE.search(line))


def normalize_code(code):
    """OCR code 4 chữ số liền -> 'ddd.d' (vd '1111' -> '111.1')."""
    if re.fullmatch(r"\d{4}", code):
        return code[:3] + "." + code[3:]
    return code


# ----------------------------------------------------------------------------
# 4. Bóc record theo block báo cáo
# ----------------------------------------------------------------------------

def extract_statement(form, pages_of_form):
    """
    pages_of_form: list các (page_no, lines) đã gom theo 1 form code.
    Trả về list dict record.
    B04 (bảng rộng) xử lý best-effort: lấy tất cả số, gán col1..colN.
    """
    records = []

    # Gom toàn bộ dòng nội dung, đánh dấu mốc client-cashflow cho B03.
    flat = []
    client_mode = False
    for page_no, lines in pages_of_form:
        for ln in lines:
            if not ln.strip():
                continue
            if CLIENT_CF_RE.search(strip_accents(ln)):
                client_mode = True
            flat.append((ln, client_mode))

    code_re = B04_CODE_RE if form == "B04" else CODE_RE

    # Gom block theo mã số.
    blocks = []  # (code, text, client_flag, raw_lines)
    cur = None
    for ln, cflag in flat:
        if is_header(ln):
            continue
        m = code_re.match(ln)
        if m:
            code = normalize_code(m.group(1))
            rest = ln[m.end():]
            if cur:
                blocks.append(cur)
            cur = [code, rest, cflag, [ln]]
        elif TOTAL_RE.search(ln):
            # Dòng tổng không có mã số (TỔNG CỘNG TÀI SẢN / NGUỒN VỐN);
            # số có thể nằm ở dòng kế tiếp -> tự gom qua continuation.
            if cur:
                blocks.append(cur)
            cur = ["", ln, cflag, [ln]]
        else:
            if cur:
                cur[1] += " " + ln
                cur[3].append(ln)
    if cur:
        blocks.append(cur)

    base_stmt, _ = FORM_NAME[form]

    for code, text, cflag, raw in blocks:
        stmt = "cash_flow_client" if (form == "B03" and cflag) else base_stmt

        name, note, amounts = parse_record(text)

        if form == "B04":
            if not amounts:
                continue
            for i, v in enumerate(amounts, 1):
                records.append({
                    "statement": stmt, "ma_so": code, "chi_tieu": name,
                    "thuyet_minh": note, "period": "col%d" % i,
                    "period_desc": "", "value": v,
                    "flag": "wide_check", "raw": " ".join(raw[:2]).strip(),
                })
            continue

        if not amounts:
            continue  # bỏ dòng footer/rác (không có số)

        cur_desc, prev_desc = PERIOD_DESC.get(stmt, ("", ""))
        cur_val, prev_val = assign_columns(amounts, raw)
        flag = "" if len(amounts) == 2 else "check_n_amount=%d" % len(amounts)

        rawtxt = " ".join(raw[:2]).strip()
        if cur_val is not None:
            records.append({
                "statement": stmt, "ma_so": code, "chi_tieu": name,
                "thuyet_minh": note, "period": "current", "period_desc": cur_desc,
                "value": cur_val, "flag": flag,
                "raw": "" if not flag else rawtxt,
            })
        if prev_val is not None:
            records.append({
                "statement": stmt, "ma_so": code, "chi_tieu": name,
                "thuyet_minh": note, "period": "prior", "period_desc": prev_desc,
                "value": prev_val, "flag": flag,
                "raw": "" if not flag else rawtxt,
            })
    return records


def normalize_line_ocr(ln):
    """Sửa vài ký tự OCR trong số: '§'->'5'."""
    return ln.replace("§", "5")


def find_amounts_pos(s):
    """Trả về [(value, end_position)] cho mọi số tiền trong chuỗi."""
    return [(clean_amount(m.group()), m.end()) for m in AMOUNT_RE.finditer(s)]


# Mục thuyết minh tối đa ~45 -> số > ngưỡng này (hoặc 3 chữ số) chắc chắn là mã GỘP.
MAX_TOP_NOTE = 50


def normalize_note_no(raw):
    """
    Suy số mục đúng từ OCR, KHÔNG cần ngữ cảnh (mục TM chỉ tới ~45):
    - đã có '.' -> giữ.
    - 3 chữ số ('281','441','301') -> 'dd.d' (28.1 / 44.1 / 30.1).
    - 2 chữ số > 50 ('71','73','75') -> 'd.d' (7.1 / 7.3 / 7.5).
    - còn lại (<=50, 1-2 chữ số) -> mục top-level, giữ nguyên.
      (OCR sai kiểu 40=10, 47=17, 41=11 không thể tự sửa -> dựa note_title.)
    """
    if "." in raw:
        return raw
    if len(raw) == 3:
        return raw[:2] + "." + raw[2:]
    if len(raw) == 2 and int(raw) > MAX_TOP_NOTE:
        return raw[0] + "." + raw[1]
    return raw


def _note_skip(ln):
    """Dòng cần bỏ trong note (không phải dữ liệu, không nên gộp vào nhãn)."""
    if AMOUNT_RE.search(ln):
        return False
    if is_header(ln):
        return True
    s = strip_accents(ln).lower()
    if not s.strip(" |.-_"):
        return True
    return sum(1 for w in NOTE_HDR_WORDS if w in s) >= 2  # dòng tiêu đề nhiều cột


def _clean_label(s):
    return re.sub(r"\s+", " ", s).strip(" .|:-—–»")


def extract_notes(note_pages):
    """
    Trích số liệu Thuyết minh (B05/B06) — thuật toán gán cột theo TỌA ĐỘ.

    1) Cắt thành các mục (note) theo dòng tiêu đề; suy note_no đúng.
    2) Mỗi mục: gom dòng dữ liệu (có số) + nhãn xuống dòng; bỏ dòng tiêu đề cột.
    3) Xác định số cột N (mode) và mốc cột (vị trí ký tự trung bình của dòng đầy đủ).
    4) Gán từng số vào cột theo vị trí (đơn điệu trái->phải) -> ô trống giữ đúng chỗ.
    """
    # --- 1) cắt mục ---
    blocks, cur = [], None
    for _pn, lines in note_pages:
        for ln in lines:
            ln = normalize_line_ocr(ln)
            s = ln.strip()
            if not s or s.lstrip("|").strip().isdigit():
                continue
            has_amt = bool(AMOUNT_RE.search(ln))
            hm = NOTE_HEADING_RE.match(ln)
            if hm and not has_amt:
                title = re.sub(r"\s+", " ", hm.group(2)).strip(" .:-—")
                title = re.sub(r"\(ti[eéê]p\s*theo\)\s*$", "", title, flags=re.I).strip(" .:-—")
                no = normalize_note_no(hm.group(1))
                # Gộp phần '(tiếp theo)': cùng note_no + title với block ngay trước
                # -> nối tiếp (bảng trải nhiều trang) thay vì tách mảnh.
                if blocks and blocks[-1]["no"] == no and blocks[-1]["title"] == title:
                    cur = blocks[-1]
                else:
                    cur = {"no": no, "raw": hm.group(1), "title": title, "lines": []}
                    blocks.append(cur)
                continue
            if cur is not None:
                cur["lines"].append(ln)

    # --- 2-4) parse từng mục ---
    records = []
    for b in blocks:
        records.extend(_parse_note_block(b))
    return records


def _parse_note_block(b):
    rows, buf = [], []
    for ln in b["lines"]:
        # Gặp footnote (1)/(*)/[1] -> phần còn lại của mục là chú thích, bỏ hết.
        if FOOTNOTE_RE.match(ln.strip()):
            break
        if _note_skip(ln):
            buf = []
            continue
        amts = find_amounts_pos(ln)
        if amts:
            first = AMOUNT_RE.search(ln)
            label = _clean_label(" ".join(buf + [ln[: first.start()]]))
            rows.append({"label": label, "cells": amts, "raw": ln.strip()})
            buf = []
        else:
            t = ln.strip()
            if FOOTNOTE_RE.match(t) or len(t) > 70:
                buf = []
            else:
                buf = (buf + [ln])[-3:]

    if not rows:
        return []

    # số cột N: giá trị xuất hiện >=2 lần, ưu tiên rộng nhất; nếu không có thì max.
    counts = [len(r["cells"]) for r in rows]
    cc = Counter(counts)
    N = max((v for v, f in cc.items() if f >= 2), default=max(counts))

    full = [r for r in rows if len(r["cells"]) == N]
    if not full:
        full = [max(rows, key=lambda r: len(r["cells"]))]
    anchors = [sum(r["cells"][i][1] for r in full) / len(full) for i in range(N)]

    out = []
    for r in rows:
        vals, overflow = _assign_cols(r["cells"], anchors)
        nonnull = [(i, v) for i, v in enumerate(vals) if v is not None]
        if not nonnull:
            continue
        flag = "wide_check" if N > 2 else ""
        if overflow:
            flag = (flag + ";overflow").strip(";")
        raw = r["raw"] if flag else ""
        for i, v in nonnull:
            if N <= 2:
                period = "current" if i == 0 else "prior"
            else:
                period = "col%d" % (i + 1)
            out.append({"note_no": b["no"], "note_no_raw": b["raw"],
                        "note_title": b["title"], "chi_tieu": r["label"],
                        "period": period, "value": v, "flag": flag, "raw": raw})
    return out


def _assign_cols(cells, anchors):
    """
    Gán mỗi số vào 1 cột theo vị trí, ĐƠN ĐIỆU trái->phải (giữ thứ tự, cho phép
    bỏ cột trống). Trả về (list giá trị theo cột, overflow?).
    """
    n = len(anchors)
    vals = [None] * n
    j = 0
    overflow = False
    for _v, e in cells:
        best_k, best_d = None, None
        for k in range(j, n):
            d = abs(e - anchors[k])
            if best_d is None or d < best_d:
                best_d, best_k = d, k
        if best_k is None:
            overflow = True
            break
        vals[best_k] = _v
        j = best_k + 1
    return vals, overflow


# ----------------------------------------------------------------------------
# 4c. Format CŨ (TT96/2008) — nhận diện theo TIÊU ĐỀ, không có mã B0x
# ----------------------------------------------------------------------------

OLD_STMT_PATTERNS = [
    ("balance_sheet",    re.compile(r"CAN\s*DOI\s*KE\s*TOAN")),
    ("income_statement", re.compile(r"KET\s*QUA.{0,18}KINH\s*DOANH")),
    ("cash_flow",        re.compile(r"LUU\s*CHUYEN\s*TIEN")),
    ("equity_changes",   re.compile(r"(BIEN\s*DONG|THAY\s*DOI).{0,12}VON\s*CHU")),
]
OLD_NOTES_RE = re.compile(r"THUYET\s*MINH")

# Header/footer/chữ ký format cũ cần bỏ (so khớp trên chuỗi đã bỏ dấu, hoa).
OLD_SKIP_RE = re.compile(
    r"CONG\s*TY\s*CO\s*PHAN|DIA\s*CHI|BIA\s*CHI|DIEN\s*THOAI|EVEN\s*THOAI|MST"
    r"|BAN\s*HANH\s*THEO|SUA\s*DOI\s*THEO|BO\s*TAI\s*CHINH"
    r"|BAO\s*CAO\s*TAI\s*CHINH|TAI\s*NGAY\s*\d|QUY\s*\d\s*NAM"
    r"|DON\s*VI\s*TINH|VI\s*TINH|THEO\s*PHUONG\s*PHAP|TIEP\s*THEO"
    r"|CHI\s*TIEU|MA\s*SO|SO\s*CUOI|SO\s*DAU|NAM\s*NAY|NAM\s*TRUOC"
    r"|LUY\s*KE|DEN\s*CUOI\s*QUY|NGUOI\s*LAP|KE\s*TOAN\s*TRUONG"
    r"|TONG\s*GIAM\s*DOC|GIAM\s*DOC|TRANG\s*\d|BO\s*PHAN\s*HOP\s*THANH"
    r"|DOC\s*CUNG\s*VOI|THUYET\s*MINH")


# Từ khoá header/đơn vị format cũ (đếm >=2 trên dòng không số -> bỏ; chịu OCR nát).
OLD_HDR_WORDS = ["chi tieu", "thuyet", "minh", "cuoi ky", "cudi", "so cuoi",
                 "so dau", "dau nam", "dau ky", "nam nay", "nam truoc", "luy ke",
                 "cuoi quy", "don vi", "phuong phap", "tai san", "nguon von"]


def _old_skip(line):
    if AMOUNT_RE.search(line):
        return False
    s = re.sub(r"\s+", " ", strip_accents(line).upper()).strip()
    if not s.strip(" |.-_=~"):
        return True
    if OLD_SKIP_RE.search(s):
        return True
    low = s.lower()
    return sum(1 for w in OLD_HDR_WORDS if w in low) >= 2


def _detect_old_stmt(line):
    """Trả về key statement nếu line là TIÊU ĐỀ báo cáo; 'NOTES' nếu bắt đầu thuyết minh."""
    s = re.sub(r"\s+", " ", strip_accents(line).upper()).strip()
    if re.search(r"THUYET\s*MINH\s*(BAO\s*CAO|BCTC|$)", s) and len(s) < 70:
        return "NOTES"
    for key, pat in OLD_STMT_PATTERNS:
        if pat.search(s):
            return key
    return None


def _parse_old_label(pre):
    """Tách (label, ma_so) từ text trước số. ma_so = code 2-4 số sát cột giá trị."""
    toks = pre.split()
    ma = ""
    for i in range(len(toks) - 1, -1, -1):
        t = toks[i].replace("O", "0").replace("o", "0").strip(".,)|:")
        if re.fullmatch(r"\d{2,4}", t):
            ma = t
            del toks[i]
            break
    label = re.sub(r"^\s*\d{1,2}[\s.|]+", "", " ".join(toks))  # bỏ STT đầu dòng
    return _clean_label(label), ma


def extract_old_format(pages):
    """
    Parse BCTC format CŨ (TT96/2008): cắt section theo tiêu đề, gán cột position-based
    (chịu số cột thay đổi: CĐKT/LCTT 2 cột, KQKD quý 4 cột). Bỏ phần thuyết minh cũ.
    """
    sections, cur = [], None
    for _pn, lines in pages:
        for ln in lines:
            ln = normalize_line_ocr(ln)
            st = _detect_old_stmt(ln)
            if st is not None:
                if st == "NOTES":
                    cur = None
                elif sections and sections[-1][0] == st:
                    cur = sections[-1]
                else:
                    cur = (st, [])
                    sections.append(cur)
                continue
            if cur is not None:
                cur[1].append(ln)

    records = []
    for st, lines in sections:
        records.extend(_parse_old_section(st, lines))
    return records


def _parse_old_section(statement, lines):
    rows, buf = [], []
    for ln in lines:
        if _old_skip(ln):
            buf = []
            continue
        amts = find_amounts_pos(ln)
        if amts:
            first = AMOUNT_RE.search(ln)
            label, ma = _parse_old_label(" ".join(buf + [ln[: first.start()]]))
            rows.append({"label": label, "ma": ma, "cells": amts, "raw": ln.strip()})
            buf = []
        else:
            t = ln.strip()
            if FOOTNOTE_RE.match(t) or len(t) > 80:
                buf = []
            else:
                buf = (buf + [ln])[-2:]

    if not rows:
        return []
    counts = [len(r["cells"]) for r in rows]
    # N = số cột phổ biến nhất (mode) -> chống vài dòng OCR rác làm phình số cột.
    N = Counter(counts).most_common(1)[0][0]
    full = [r for r in rows if len(r["cells"]) == N]
    if not full:
        full = [max(rows, key=lambda r: len(r["cells"]))]
    anchors = [sum(r["cells"][i][1] for r in full) / len(full) for i in range(N)]

    out = []
    for r in rows:
        vals, overflow = _assign_cols(r["cells"], anchors)
        nonnull = [(i, v) for i, v in enumerate(vals) if v is not None]
        if not nonnull:
            continue
        flag = "wide_check" if N > 2 else ""
        if overflow:
            flag = (flag + ";overflow").strip(";")
        raw = r["raw"] if flag else ""
        # KQKD báo cáo quý có 4 cột: Quý (năm nay/trước) + Lũy kế (năm nay/trước).
        quarterly_is = statement == "income_statement" and N == 4
        for i, v in nonnull:
            if N <= 2:
                period = "current" if i == 0 else "prior"
            elif quarterly_is:
                period = ["quy_current", "quy_prior", "ytd_current", "ytd_prior"][i]
            else:
                period = "col%d" % (i + 1)
            out.append({"statement": statement, "ma_so": r["ma"], "chi_tieu": r["label"],
                        "thuyet_minh": "", "period": period, "period_desc": "",
                        "value": v, "flag": flag, "raw": raw})
    return out


# ----------------------------------------------------------------------------
# 4d. Báo cáo TỶ LỆ AN TOÀN TÀI CHÍNH (TT226/2010) — không phải BCTC
# ----------------------------------------------------------------------------

def _norm(line):
    return re.sub(r"\s+", " ", strip_accents(line).upper()).strip()


def _car_main_title(s):
    """s đã chuẩn hoá. True nếu là dòng TIÊU ĐỀ bảng chính (không phải mục lục/prose)."""
    m = re.match(r"BAO CAO TY LE AN TOAN TAI CHINH(.*)$", s)
    return bool(m and not re.search(r"\d", m.group(1)))  # mục lục có '6-7' -> loại


def is_car_doc(pages):
    """Doc là Báo cáo tỷ lệ an toàn tài chính nếu có dòng tiêu đề bảng chính."""
    for _pn, lines in pages:
        for ln in lines:
            if _car_main_title(_norm(ln)):
                return True
    return False


def _car_note_pages(pages):
    """Các trang Thuyết minh BC tỷ lệ ATTC (header có 'THUYET MINH ... TY LE AN TOAN')."""
    out = []
    for pn, lines in pages:
        head = _norm(" ".join(lines[:6]))
        if re.search(r"THUYET MINH.*TY LE AN TOAN", head):
            out.append((pn, lines))
    return out


def extract_car_main(pages):
    """
    Trích BẢNG CHÍNH 'Báo cáo tỷ lệ an toàn tài chính' (statement='safety_ratio').
    Cấu trúc: STT | Chỉ tiêu | Thuyết minh | 1 cột giá trị (VND). 1 kỳ -> period=current.
    (Dòng 'Tỷ lệ an toàn ... %' không bắt được vì là %, có thể tự tính = VKD/tổng rủi ro.)
    """
    records, capture, done, buf = [], False, False, []
    for _pn, lines in pages:
        for ln in lines:
            ln = normalize_line_ocr(ln)
            s = _norm(ln)
            if not done and _car_main_title(s):
                capture = True
                buf = []
                continue
            if not capture:
                continue
            if "THUYET MINH" in s or re.search(r"KE TOAN TRUONG|TONG GIAM DOC", s):
                capture = False
                if records:  # đã bắt được bảng chính -> khoá, không bắt lại từ prose
                    done = True
                continue
            amts = find_amounts_pos(ln)
            if not amts:
                t = ln.strip()
                if len(t) <= 70 and not _old_skip(ln):
                    buf = (buf + [ln])[-2:]
                else:
                    buf = []
                continue
            pre = " ".join(buf + [ln[: AMOUNT_RE.search(ln).start()]])
            buf = []
            pre = re.sub(r"\s+", " ", pre).strip(" .|:-—")
            stt = ""
            m = re.match(r"(\d{1,2})\s+(.*)$", pre)
            if m:
                stt, pre = m.group(1), m.group(2)
            note = ""
            mn = re.search(r"^(.*\S)\s+(\d{1,2})$", pre.strip())
            if mn:
                pre, note = mn.group(1), mn.group(2)
            records.append({"statement": "safety_ratio", "ma_so": stt,
                            "chi_tieu": _clean_label(pre), "thuyet_minh": note,
                            "period": "current", "period_desc": "",
                            "value": amts[0][0], "flag": "", "raw": ""})
    return records


# ----------------------------------------------------------------------------
# 4b. Đánh giá chất lượng dòng: clean / dirty
# ----------------------------------------------------------------------------

# Ký tự rác OCR thường gặp trong nhãn (placeholder ô trống, nhiễu).
_QUAL_NOISE = re.compile(r"[§=~¬ñ•@#\^_\\|]|—")
# Đuôi nhãn toàn chữ cái đơn lẻ (vd '... quỹ Ề z z') => rác cột tràn vào nhãn.
_QUAL_TRAILSINGLE = re.compile(r"(?:\s[A-Za-zÀ-ỹ](?=\s|$)){2,}\s*$")
# Số tiền VND hợp lý hiếm khi >= 10^15 (1 triệu tỷ); lớn hơn => nghi dính cột.
_QUAL_MAXVAL = 10 ** 15


def row_quality(value, label, flag, statement=""):
    """
    Trả về ('clean'|'dirty', flag_đã_bổ_sung_lý_do).
    dirty = có dấu hiệu lỗi cần soi/sửa; clean = đáng tin.
    (Lưu ý: 'wide_check' đơn thuần — bảng nhiều cột parse đúng — KHÔNG bị coi là dirty.)
    """
    f = flag or ""
    extra = []
    if isinstance(value, int) and abs(value) >= _QUAL_MAXVAL:
        extra.append("huge_value")
    lab = (label or "").strip()
    if not lab:
        extra.append("no_label")
    elif _QUAL_NOISE.search(lab) or _QUAL_TRAILSINGLE.search(lab):
        extra.append("garbage_label")
    if statement == "equity_changes":
        extra.append("b04_besteffort")
    dirty = (bool(extra) or "overflow" in f or "check_n_amount" in f
             or "formula_mismatch" in f)
    parts = [p for p in f.split(";") if p] + extra
    return ("dirty" if dirty else "clean"), ";".join(parts)


# ----------------------------------------------------------------------------
# 5. Ghi file tổng (master) + wide
# ----------------------------------------------------------------------------

MASTER_COLS = ["ticker", "fiscal_year", "period_label", "consolidated", "currency",
               "statement", "ma_so", "chi_tieu", "thuyet_minh",
               "period", "period_desc", "value", "flag", "quality", "raw", "source_file"]

NOTE_COLS = ["ticker", "fiscal_year", "period_label", "consolidated", "currency",
             "note_no", "note_no_raw", "note_title", "chi_tieu",
             "period", "value", "flag", "quality", "raw", "source_file"]


def upsert_master(master_path, new_rows, src, cols=MASTER_COLS):
    """
    Cộng dồn vào file tổng, dedup theo SOURCE_FILE (mỗi file .md = 1 báo cáo).
    Chạy lại cùng file -> thay thế dòng cũ của chính nó (idempotent); các file khác
    (kể cả cùng ticker/năm: annual vs quý, riêng lẻ vs hợp nhất) được GIỮ NGUYÊN
    -> không đè mất nhau. Trả về (so_dong_giu_lai, so_dong_bi_thay_the).
    """
    kept = []
    replaced = 0
    if os.path.exists(master_path):
        with open(master_path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row.get("source_file") == src:
                    replaced += 1
                else:
                    kept.append(row)

    os.makedirs(os.path.dirname(os.path.abspath(master_path)), exist_ok=True)
    with open(master_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for row in kept:
            w.writerow({k: row.get(k, "") for k in cols})
        for row in new_rows:
            w.writerow({k: row.get(k, "") for k in cols})
    return len(kept), replaced


def balance_check(records):
    """
    Kiểm tra Tổng tài sản = Nợ phải trả + Vốn CSH cho từng kỳ.
    Tổng TS: dòng mã '270' (TT210/cũ) hoặc dòng không-mã 'TỔNG CỘNG TÀI SẢN' (TT334).
    Trả về list (nhãn_kỳ, tong_ts, no_cong_vcsh, ok?).
    """
    def find(per, pred):
        for r in records:
            if (r.get("statement") == "balance_sheet" and r.get("period") == per
                    and r.get("value") is not None and pred(r)):
                return r["value"]
        return None

    def total_assets(per):
        v = find(per, lambda r: r["ma_so"] in ("270", "290"))
        if v is None:
            v = find(per, lambda r: not r["ma_so"]
                     and re.search(r"(T[OỔ]NG|C[OỘ]NG)\s*(C[OỘ]NG\s*)?T[AÀ]I\s*S[AẢ]N",
                                   strip_accents(r["chi_tieu"]).upper()))
        return v

    def total_le(per):
        no = find(per, lambda r: r["ma_so"] == "300")
        vc = find(per, lambda r: r["ma_so"] == "400")
        if no is not None and vc is not None:
            return no + vc
        return find(per, lambda r: r["ma_so"] == "440")  # TỔNG NGUỒN VỐN

    out = []
    for per, lbl in (("current", "Cuoi ky"), ("prior", "Dau ky")):
        ta, le = total_assets(per), total_le(per)
        if ta is not None and le is not None:
            out.append((lbl, ta, le, ta == le))
    return out


# Công thức kiểm tra nhúng trong nhãn: '(100 = 110 + 130)', '(270=100+200)', ...
FORMULA_RE = re.compile(r"\(\s*(\d{2,4}(?:\.\d{1,3})?)\s*=\s*([0-9.+\-\s]+?)\s*\)")


def verify_formulas(records, tag=True):
    """
    Đối chiếu chéo bằng công thức nhúng trong chi_tieu (vd '100 = 110 + 130'):
    kiểm tra value(LHS) == Σ value(các mã RHS) cùng statement+kỳ.
    Nếu lệch và tag=True -> gắn cờ 'formula_mismatch' vào dòng LHS (→ quality=dirty),
    pinpoint đúng ô tổng đáng ngờ (thường do OCR sai 1 chữ số).
    Trả về {ok, fail, fails:[(stmt,period,ma,trich,congthuc)]}.
    """
    idx = {}
    for r in records:
        if r.get("ma_so") and r.get("value") is not None:
            idx[(r["statement"], r["ma_so"], r["period"])] = r
    ok = fail = 0
    fails = []
    for r in records:
        ma = r.get("ma_so")
        if not ma or r.get("value") is None:
            continue
        fm = FORMULA_RE.search(r.get("chi_tieu", ""))
        if not fm or fm.group(1) != ma:
            continue
        st, per = r["statement"], r["period"]
        total, missing = 0, False
        for sign, code in re.findall(r"([+\-]?)\s*(\d{2,4}(?:\.\d{1,3})?)", fm.group(2)):
            rr = idx.get((st, code, per))
            if rr is None:
                missing = True
                break
            total += (-1 if sign == "-" else 1) * rr["value"]
        if missing:
            continue
        if total == r["value"]:
            ok += 1
        else:
            fail += 1
            fails.append((st, per, ma, r["value"], total))
            if tag:
                r["flag"] = (r.get("flag", "") + ";formula_mismatch").strip(";")
    return {"ok": ok, "fail": fail, "fails": fails}


def write_wide(path, records):
    wide, order = {}, []
    for r in records:
        key = (r["statement"], r["ma_so"], r["chi_tieu"],
               r["period"] if r["period"].startswith("col") else "")
        if key not in wide:
            wide[key] = {"statement": r["statement"], "ma_so": r["ma_so"],
                         "chi_tieu": r["chi_tieu"], "thuyet_minh": r["thuyet_minh"],
                         "current": "", "prior": "", "flag": r["flag"]}
            order.append(key)
        wide[key][r["period"]] = r["value"]
    wcols = ["statement", "ma_so", "chi_tieu", "thuyet_minh", "current", "prior", "flag"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(wcols)
        for key in order:
            w.writerow([wide[key].get(c, "") for c in wcols])


# ----------------------------------------------------------------------------
# 6. Metadata
# ----------------------------------------------------------------------------

def detect_meta(text, ticker, year):
    company = ""
    m = re.search(r"C[oôéổ]ng\s*ty\s*C[oổ]\s*ph[aâầ]n\s*Ch[uứ]ng\s*kho[aá]n\s*[A-Za-zÀ-ỹ ]+", text)
    if m:
        company = re.sub(r"\s+", " ", m.group()).strip()
    if not year:
        # Ưu tiên ngày BÁO CÁO ("tại ngày DD tháng MM năm 20xx") -> tránh vớ nhầm
        # ngày của Thông tư (vd '226/2010 ngày 31 tháng 12 năm 2010'). Rồi tới
        # "31 tháng 12" (BCTC năm), cuối cùng là ngày kết kỳ bất kỳ (BCTC quý).
        ym = (re.search(r"t[aạ]i\s*ng[aà]y\s*\d{1,2}\s*th[aá]ng\s*\d{1,2}\s*n[aă]m\s*(20\d\d)", text)
              or re.search(r"31\s*th[aá]ng\s*12\s*n[aă]m\s*(20\d\d)", text)
              or re.search(r"th[aá]ng\s*\d{1,2}\s*n[aă]m\s*(20\d\d)", text))
        year = ym.group(1) if ym else ""
    # Riêng/Hợp nhất: lấy HẬU TỐ ngay sau tiêu đề báo cáo ('...HỢP NHẤT' / '...RIÊNG').
    # Không thể chỉ dựa 'HỢP NHẤT' xuất hiện đâu đó (BC riêng/hợp nhất đều nhắc cả hai).
    _T = re.sub(r"\s+", " ", strip_accents(text).upper())
    mt = re.search(r"(?:TINH HINH TAI CHINH|CAN DOI KE TOAN|KET QUA HOAT [DB]ONG"
                   r"|LUU CHUYEN TIEN TE)\s+(HOP NHAT|RIENG)", _T)
    if mt:
        consolidated = (mt.group(1) == "HOP NHAT")
    else:
        consolidated = "HOP NHAT" in _T
    # Kỳ báo cáo: 'Qx' nếu là báo cáo quý ('Quý N năm 20xx'), ngược lại 'FY' (năm).
    period_label = "FY"
    qm = re.search(r"Qu[yýiÝ]\s*(I{1,3}|IV|[1-4])\s*n[aă]m\s*20\d\d", text, re.IGNORECASE)
    if qm:
        roman = {"I": "1", "II": "2", "III": "3", "IV": "4"}
        period_label = "Q" + roman.get(qm.group(1).upper(), qm.group(1))
    return {
        "ticker": ticker, "company": company, "fiscal_year": year,
        "period_label": period_label,
        "currency": "VND", "consolidated": "Y" if consolidated else "N",
    }


# ----------------------------------------------------------------------------
# 6. Main
# ----------------------------------------------------------------------------

def process_file(text, ticker, year="", do_notes=True):
    """
    Xử lý 1 nội dung .md -> (meta, fmt, all_records, note_records).
    Dùng chung cho main() và test_all.py (1 nguồn sự thật, không lệch logic).
    """
    meta = detect_meta(text, ticker, year)
    pages = split_pages(text)

    # Phân biệt FORMAT theo TIÊU ĐỀ (không theo mã B0x — vì BCTC cũ cũng có mã B0x):
    #  - 'BÁO CÁO TÌNH HÌNH TÀI CHÍNH' -> TT210/2016 (new); mã có thể ở đầu/giữa dòng.
    #  - 'BẢNG CÂN ĐỐI KẾ TOÁN'        -> TT95/96/2008 + DN thường (TT200, B09-DN).
    #  - 'BÁO CÁO TỶ LỆ AN TOÀN'       -> CAR (TT226).
    T = re.sub(r"\s+", " ", strip_accents(text).upper())
    car_doc = is_car_doc(pages)
    new_format = (not car_doc) and ("BAO CAO TINH HINH TAI CHINH" in T)
    fmt = ("BC-ATTC (TT226)" if car_doc
           else "TT210/2016" if new_format else "TT95-96/2008")

    if car_doc:
        all_records = extract_car_main(pages)
        note_records = extract_notes(_car_note_pages(pages)) if do_notes else []
    elif new_format:
        groups = group_new_pages(pages)
        all_records = []
        if doc_code_at_start(groups):
            for form, pgs in groups:          # TT334: mã số ở đầu dòng
                all_records.extend(extract_statement(form, pgs))
        else:
            for form, pgs in groups:          # mã số giữa dòng -> position-based
                stmt = FORM_NAME[form][0]
                seclines = [ln for _pn, ls in pgs for ln in ls]
                all_records.extend(_parse_old_section(stmt, seclines))
        note_pages = [(pn, ls) for pn, ls in pages if is_note_page(ls)]
        note_records = extract_notes(note_pages) if do_notes else []
    else:
        all_records = extract_old_format(pages)
        # Thuyết minh (DN: 'MẪU SỐ B09-DN'; CTCK cũ): nhận trang theo tiêu đề
        # 'THUYẾT MINH BÁO CÁO TÀI CHÍNH' (is_note_page đã hỗ trợ).
        note_pages = [(pn, ls) for pn, ls in pages if is_note_page(ls)]
        note_records = extract_notes(note_pages) if do_notes else []
    # Đối chiếu chéo công thức nhúng (gắn cờ ô tổng sai) -> tăng độ chính xác
    meta["formula"] = verify_formulas(all_records, tag=True)
    return meta, fmt, all_records, note_records


def _collect_md(inputs, recursive):
    """Mở rộng danh sách input (file .md hoặc thư mục) -> list file .md."""
    files = []
    for raw in inputs:
        p = raw.strip().strip('"')
        if os.path.isdir(p):
            pat = os.path.join(p, "**", "*.md") if recursive else os.path.join(p, "*.md")
            files.extend(sorted(glob.glob(pat, recursive=recursive)))
        elif os.path.isfile(p) and p.lower().endswith(".md"):
            files.append(p)
        else:
            print("  ! Bo qua (khong phai .md / khong ton tai):", p)
    # khử trùng giữ thứ tự
    seen, out = set(), []
    for f in files:
        a = os.path.abspath(f)
        if a not in seen:
            seen.add(a)
            out.append(f)
    return out


def main():
    ap = argparse.ArgumentParser(description="BCTC Markdown (CTCK) -> CSV long-format")
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("input", nargs="+", help="1+ file .md HOAC thu muc chua .md")
    ap.add_argument("--ticker", default="")
    ap.add_argument("--year", default="")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="quet .md trong thu muc con (khi input la thu muc)")
    ap.add_argument("--master", default=os.path.join(here, "bctc_master.csv"),
                    help="file CSV tong 4 BC chinh. Mac dinh bctc_master.csv")
    ap.add_argument("--notes", default=os.path.join(here, "bctc_notes.csv"),
                    help="file CSV tong Thuyet minh. Mac dinh bctc_notes.csv")
    ap.add_argument("--outdir", default=os.path.join(here, "output"),
                    help="thu muc cho file _wide.csv (chi khi dung --wide)")
    ap.add_argument("--wide", action="store_true",
                    help="xuat them file <TICKER>_<YEAR>_wide.csv de doc nhanh")
    ap.add_argument("--no-notes", dest="do_notes", action="store_false",
                    help="bo qua trich Thuyet minh")
    args = ap.parse_args()

    files = _collect_md(args.input, args.recursive)
    if not files:
        print("Khong tim thay file .md nao.")
        return
    print("Tim thay %d file .md. Bat dau xu ly..." % len(files))
    nok = nerr = 0
    for i, path in enumerate(files, 1):
        print("\n[%d/%d] %s" % (i, len(files), os.path.basename(path)))
        try:
            run_one(path, args)
            nok += 1
        except Exception as e:
            nerr += 1
            print("  ! LOI:", e)
    print("\n", "#" * 60)
    print("# HOAN TAT: %d file OK, %d loi. Master: %s | Notes: %s"
          % (nok, nerr, args.master, args.notes if args.do_notes else "(bo qua)"))


def run_one(input_path, args):
    with open(input_path, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()

    ticker = args.ticker or _guess_ticker(input_path)
    meta, fmt, all_records, note_records = process_file(text, ticker, args.year, args.do_notes)
    year = meta["fiscal_year"] or "NA"

    base = "%s_%s_bctc" % (ticker or "UNK", year)
    src = os.path.basename(input_path)

    # --- Ghi/cộng dồn vào FILE TỔNG (upsert theo ticker+năm+hợp nhất) ---
    new_rows = []
    for r in all_records:
        q, fl = row_quality(r.get("value"), r.get("chi_tieu", ""),
                            r.get("flag", ""), r.get("statement", ""))
        row = {k: r.get(k, "") for k in MASTER_COLS}
        row["flag"], row["quality"] = fl, q
        row.update(ticker=meta["ticker"], fiscal_year=meta["fiscal_year"],
                   period_label=meta["period_label"], consolidated=meta["consolidated"],
                   currency=meta["currency"], source_file=src)
        new_rows.append(row)
    n_kept, n_replaced = upsert_master(args.master, new_rows, src)

    # --- Thuyết minh -> file notes riêng (cùng cơ chế upsert) ---
    nn_kept = nn_repl = 0
    if args.do_notes:
        note_rows = []
        for r in note_records:
            q, fl = row_quality(r.get("value"), r.get("chi_tieu", ""), r.get("flag", ""))
            row = {k: r.get(k, "") for k in NOTE_COLS}
            row["flag"], row["quality"] = fl, q
            row.update(ticker=meta["ticker"], fiscal_year=meta["fiscal_year"],
                       period_label=meta["period_label"], consolidated=meta["consolidated"],
                       currency=meta["currency"], source_file=src)
            note_rows.append(row)
        nn_kept, nn_repl = upsert_master(args.notes, note_rows, src, cols=NOTE_COLS)

    # --- (tùy chọn) file wide per-file để đọc nhanh ---
    wide_path = None
    if args.wide:
        os.makedirs(args.outdir, exist_ok=True)
        wide_path = os.path.join(args.outdir, base + "_wide.csv")
        write_wide(wide_path, all_records)

    # Tóm tắt ra console
    from collections import Counter
    c = Counter(r["statement"] for r in all_records)
    flagged = sum(1 for r in all_records if r["flag"])
    print("=" * 60)
    print("Company :", meta["company"])
    print("Ticker  :", meta["ticker"], "| Year:", meta["fiscal_year"],
          "| Ky:", meta["period_label"], "| Consolidated:", meta["consolidated"],
          "| Format:", fmt)
    print("-" * 60)
    for k in ["balance_sheet", "income_statement", "cash_flow",
              "cash_flow_client", "equity_changes", "safety_ratio"]:
        if c.get(k):
            print("  %-18s %4d dong" % (k, c[k]))
    if note_records:
        nf = sum(1 for r in note_records if r["flag"])
        print("  %-18s %4d dong (flag %d)" % ("note (thuyet minh)", len(note_records), nf))
    print("-" * 60)
    print("  Tong 4BC:", len(all_records), "dong | Can kiem tra (flag):", flagged)

    # Kiểm tra đẳng thức kế toán: Tổng tài sản = Nợ phải trả + Vốn CSH
    print("-" * 60)
    for lbl, ta, le, ok in balance_check(all_records):
        print("  Can doi (%s): TongTS=%s vs No+VCSH=%s -> %s"
              % (lbl, "{:,}".format(ta), "{:,}".format(le),
                 "OK" if ok else "LECH (kiem tra OCR!)"))
    fv = meta.get("formula", {})
    if fv.get("ok", 0) or fv.get("fail", 0):
        print("  Cong thuc nhung: khop %d, LECH %d%s"
              % (fv["ok"], fv["fail"],
                 " (xem flag 'formula_mismatch')" if fv["fail"] else ""))
    print("=" * 60)
    print("File tong:", args.master)
    print("  + Them %d dong moi (%s %s, %s)"
          % (len(new_rows), ticker or "UNK", year,
             "hop nhat" if meta["consolidated"] == "Y" else "rieng le"))
    if n_replaced:
        print("  ~ Thay the %d dong cu cung ticker/nam (chay lai)" % n_replaced)
    print("  = Tong file hien co: %d dong" % (n_kept + len(new_rows)))
    mdq = Counter(r["quality"] for r in new_rows)
    print("  quality: clean=%d | dirty=%d" % (mdq.get("clean", 0), mdq.get("dirty", 0)))
    if args.do_notes:
        print("File notes:", args.notes)
        print("  + Them %d dong note%s | = Tong: %d dong"
              % (len(note_records),
                 (" (thay the %d)" % nn_repl) if nn_repl else "",
                 nn_kept + len(note_records)))
        ndq = Counter(r["quality"] for r in note_rows)
        print("  quality: clean=%d | dirty=%d" % (ndq.get("clean", 0), ndq.get("dirty", 0)))
    if wide_path:
        print("File wide:", wide_path)


def _guess_ticker(path):
    # Đoán ticker từ tên thư mục cha (vd .../downloads/SSI/xxx.md -> SSI)
    parent = os.path.basename(os.path.dirname(os.path.abspath(path)))
    if re.fullmatch(r"[A-Z]{3,4}", parent):
        return parent
    return ""


if __name__ == "__main__":
    main()
