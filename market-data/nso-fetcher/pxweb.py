# -*- coding: utf-8 -*-
"""pxweb.py - thu vien noi PX-Web cua Cuc Thong ke (NSO): https://pxweb.nso.gov.vn/pxweb/vi/

Tinh trang nguon (khao sat 07/10/2026):
  * API REST /api/v1/vi/ chi mo 4 CSDL (Cong nghiep, Doanh nghiep, Dan so..., config cu) va POST bi IIS 404
    -> KHONG dung API. Dung giao dien ASP.NET WebForms: GET trang chon bien -> POST form voi toan bo gia tri
       + OutputFormat=FileTypeJsonStat -> tra file JSON-stat (co 1 byte NUL o cuoi).
  * Cay: /pxweb/vi/<db>/<folder>/<table>.px/  (folder trung ten db). Danh sach bang chi hien khi ?tablelist=true.
  * Bang la so lieu NIEN GIAM (nam) + CPI theo thang (V11.01-V11.07). Gia tri nam co tien to "So bo", "Uoc tinh".
  * Gioi han 100.000 o/lan (SelectionLimitation) - bang theo dia phuong van duoi muc nay.
"""
from __future__ import annotations

import html as H
import itertools
import json
import os
import re
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))   # D:\market-data
from mdlib import log, new_session                                                 # noqa: E402

UI = "https://pxweb.nso.gov.vn/pxweb/vi/"
SOURCE = "NSO_PXWEB"

# CSDL kinh te (mac dinh keo). Cac CSDL khac (Y te, Giao duc, Don vi hanh chinh, Thong ke nuoc ngoai) va
# nhom PLV* (phan theo vung/tinh) keo bang --db <ten> hoac --db all.
ECON_DBS = [
    "Tài khoản quốc gia",
    "Chỉ số giá",
    "Xuất nhập khẩu",
    "Thương mại",
    "Công nghiệp",
    "Đầu tư và xây dựng",
    "Doanh nghiệp",
    "Du lịch",
    "Vận tải và Bưu chính viễn thông",
    "Nông nghiệp, lâm nghiệp và thủy sản",
    "Dân số và lao động",
]

YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
PURE_YEAR_RE = re.compile(r"^\s*[^\d]*(?:19|20)\d{2}\s*$")           # "2024", "So bo 2025", "Uoc tinh 2025"
MONTH_RE = re.compile(r"^\s*(?:th[aá]ng)?\s*0?([1-9]|1[0-2])\s*$", re.I)
QUARTER_RE = re.compile(r"^\s*qu[yý]\s*(IV|I{1,3}|[1-4])\s*$", re.I)
ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4}


def session():
    return new_session("browser")


def _get(s, url: str, tries: int = 3):
    for i in range(1, tries + 1):
        try:
            r = s.get(url, timeout=90)
            if r.status_code == 200:
                return r.text
            reason = f"HTTP {r.status_code}"
        except Exception as e:                                    # noqa: BLE001
            reason = f"{type(e).__name__}: {e}"
        if i < tries:
            log(f"  ! {reason} -> thu lai {i}/{tries - 1}: {url[-70:]}")
            time.sleep(5 * i)
    log(f"  X khong lay duoc: {url[-90:]}")
    return None


def _links(html: str):
    """[(href da giai ma, text)] tu HTML PX-Web (href vua URL-encode vua HTML-escape)."""
    out = []
    for h, t in re.findall(r'href="([^"]*)"[^>]*>(.*?)</a>', html, re.S):
        h = H.unescape(urllib.parse.unquote(h))
        t = re.sub(r"<[^>]+>", "", H.unescape(t)).strip()
        out.append((h, t))
    return out


def list_databases(s) -> list[str]:
    html = _get(s, UI)
    if not html:
        return []
    seen = []
    for h, _ in _links(html):
        m = re.match(r"^/pxweb/vi/([^/?]+)/\?", h)
        if m and m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def list_tables(s, db: str) -> list[dict]:
    """Tat ca bang .px trong CSDL (duyet moi folder con 1 cap, nhu PX-Web NSO dang to chuc)."""
    html = _get(s, UI + urllib.parse.quote(f"{db}/"))
    if not html:
        return []
    folders = []
    for h, _ in _links(html):
        m = re.match(rf"^/pxweb/vi/{re.escape(db)}/([^/?]+)/", h)
        if m and not m.group(1).endswith(".px") and m.group(1) not in folders:
            folders.append(m.group(1))
    if not folders:
        folders = [db]
    tables = []
    for folder in folders:
        html = _get(s, UI + urllib.parse.quote(f"{db}/{folder}/") + "?tablelist=true")
        if not html:
            continue
        seen = set()
        for h, t in _links(html):
            path = h.split("?")[0]
            if not path.endswith(".px/"):
                continue
            tid = path.rstrip("/").rsplit("/", 1)[1]
            if tid in seen:
                continue
            seen.add(tid)
            tables.append({"db": db, "folder": folder, "table_id": tid, "title": t})
    return tables


def fetch_table(s, db: str, folder: str, table_id: str, fmt: str = "FileTypeJsonStat"):
    """GET trang chon bien -> POST chon TAT CA gia tri moi bien + dinh dang JSON-stat. Tra dict JSON-stat hoac None."""
    url = UI + urllib.parse.quote(f"{db}/{folder}/{table_id}/")
    html = _get(s, url)
    if not html:
        return None
    form = []
    for m in re.finditer(r'<input[^>]*type="hidden"[^>]*>', html):
        tag = m.group(0)
        n = re.search(r'name="([^"]*)"', tag)
        v = re.search(r'value="([^"]*)"', tag)
        if n:
            form.append((H.unescape(n.group(1)), H.unescape(v.group(1)) if v else ""))
    n_box = 0
    for lb in re.finditer(r'<select[^>]*name="([^"]*ValuesListBox)"[^>]*>(.*?)</select>', html, re.S):
        n_box += 1
        name = H.unescape(lb.group(1))
        for val in re.findall(r'<option[^>]*value="([^"]*)"', lb.group(2)):
            form.append((name, val))
    fmt_sel = re.search(r'<select[^>]*name="([^"]*OutputFormatDropDownList)"', html)
    btn = re.search(r'<input[^>]*name="([^"]*ButtonViewTable)"', html)
    if not (n_box and fmt_sel and btn):
        log(f"  X {table_id}: trang chon bien khong dung cau truc (listbox={n_box})")
        return None
    form.append((H.unescape(fmt_sel.group(1)), fmt))
    form.append((H.unescape(btn.group(1)), "Tiếp tục"))
    for i in range(1, 4):
        try:
            r = s.post(url, data=form, headers={"Referer": url}, timeout=180)
        except Exception as e:                                    # noqa: BLE001
            log(f"  ! {table_id}: POST {type(e).__name__} -> thu lai {i}/2")
            time.sleep(5 * i)
            continue
        ctype = r.headers.get("content-type", "")
        if r.status_code == 200 and "json" in ctype:
            raw = r.content.replace(b"\x00", b"").decode("utf-8-sig", errors="replace")
            try:
                return json.loads(raw)
            except json.JSONDecodeError as e:
                log(f"  X {table_id}: JSON hong ({e})")
                return None
        if r.status_code == 200:
            msg = re.search(r'class="[^"]*error[^"]*"[^>]*>(.*?)<', r.text, re.S | re.I)
            why = msg.group(1).strip() if msg else "co the vuot gioi han o"
            log(f"  X {table_id}: server tra HTML thay vi JSON ({why[:80]})")
            return None
        log(f"  ! {table_id}: HTTP {r.status_code} -> thu lai {i}/2")
        time.sleep(5 * i)
    return None


# ------------------------------------------------------------------ JSON-stat -> long rows
COLS = ["date", "freq", "table_id", "series_id", "pos", "dim1", "dim2", "dim3", "unit", "status", "value", "updated", "source"]
# pos = thu tu xuat hien cua series trong bang NSO (giu thu tu goc: Tong so truoc, nhom con sau) - dung khi dung sheet rong


def _cats(dim: dict):
    cat = dim["category"]
    idx = cat["index"]
    lab = cat.get("label", {})
    order = idx if isinstance(idx, list) else sorted(idx, key=lambda k: idx[k])
    return [(code, str(lab.get(code, code))) for code in order]


def _classify(labels: list[str], cats: list[list]):
    """Tim dim nam / thang / quy. Uu tien nhan 'Nam'; neu khong co thi dim ma >=60% gia tri la nam thuan."""
    year_i = month_i = quarter_i = None
    for i, lab in enumerate(labels):
        if lab.strip().lower() in ("năm", "nam"):
            year_i = i
            break
    if year_i is None:
        for i, vals in enumerate(cats):
            texts = [t for _, t in vals]
            if texts and sum(1 for t in texts if PURE_YEAR_RE.match(t)) >= max(1, 0.6 * len(texts)):
                year_i = i
                break
    for i, (lab, vals) in enumerate(zip(labels, cats)):
        if i == year_i:
            continue
        texts = [t for _, t in vals]
        low = lab.strip().lower()
        n_m = sum(1 for t in texts if MONTH_RE.match(t))
        n_q = sum(1 for t in texts if QUARTER_RE.match(t))
        if month_i is None and (low.startswith("tháng") or low.startswith("các tháng") or n_m >= max(1, 0.6 * len(texts))):
            month_i = i
        elif quarter_i is None and (low.startswith("quý") or n_q >= max(1, 0.6 * len(texts))):
            quarter_i = i
    return year_i, month_i, quarter_i


UNIT_WORDS = re.compile(r"%|tỷ|triệu|nghìn|đồng|usd|đô la|tấn|người|km|\bha\b|m3|m2|cái|chiếc|kwh|lượt|giờ|ngày|"
                        r"=\s*100|giá (?:hiện hành|so sánh)|đơn vị|tuổi|con|quả|lít|tháng", re.I)


def _unit(series_dims: list[str], title: str) -> str:
    """Don vi tach tu cuoi nhan series: "(Ty dong)" hoac "Chi tieu - Ty dong". Dau gach ngang chi nhan khi doan sau
    trong giong don vi (tranh "Ba Ria - Vung Tau", "Thua Thien - Hue" thanh don vi)."""
    for t in reversed(series_dims):
        m = re.search(r"\(([^()]{1,45})\)\s*$", t)
        if m and m.group(1).strip("* ").strip():
            return m.group(1).strip()
        m = re.search(r"\s[-–]\s([^-–]{1,35})$", t)
        if m and UNIT_WORDS.search(m.group(1)):
            return m.group(1).strip()
    m = re.search(r"\(([^()]{1,45})\)\s*$", title)
    return m.group(1).strip() if m and m.group(1).strip("* ") else ""


def parse_table(d: dict, table_id: str, title: str = ""):
    """JSON-stat (PX-Web 2017: {"dataset": {...}}) -> (rows theo COLS, info)."""
    ds = d.get("dataset", d)
    dim = ds["dimension"]
    ids = dim.get("id") or [k for k in dim if isinstance(dim[k], dict) and "category" in dim[k]]
    sizes = dim.get("size") or [len(dim[k]["category"]["index"]) for k in ids]
    labels = [str(dim[k].get("label", k)) for k in ids]
    cats = [_cats(dim[k]) for k in ids]
    values = ds.get("value", [])
    if isinstance(values, dict):
        getv = lambda i: values.get(str(i))                        # noqa: E731
    else:
        getv = lambda i: values[i] if i < len(values) else None    # noqa: E731
    updated = str(ds.get("updated", ""))[:10]
    if updated.startswith("9999"):
        updated = ""
    year_i, month_i, quarter_i = _classify(labels, cats)
    title_year = YEAR_RE.search(title or "")
    rows = []
    freqs = set()
    pos = {}
    for flat, combo in enumerate(itertools.product(*[range(n) for n in sizes])):
        v = getv(flat)
        if v is None or v == "":
            continue
        try:
            v = float(v)
        except (TypeError, ValueError):
            continue
        texts = [cats[i][combo[i]][1] for i in range(len(ids))]
        status = ""
        if year_i is not None:
            yt = texts[year_i]
            m = YEAR_RE.search(yt)
            if m:
                year = m.group(1)
                date, freq = year, "A"
                status = re.sub(r"[\d\s\-–/()*.]+", " ", yt.replace(year, "")).strip()
            else:
                date, freq = yt.strip(), "X"                        # "Tong so", "1988-1990"...
        elif title_year:
            date, freq, status = title_year.group(1), "A", "theo tieu de"
        else:
            date, freq = "", "X"
        series_dims = []
        for i, t in enumerate(texts):
            if i == year_i:
                continue
            if i == month_i and freq == "A":
                mm = MONTH_RE.match(t)
                if mm:
                    date, freq = f"{date}-{int(mm.group(1)):02d}", "M"
                    continue
            if i == quarter_i and freq == "A":
                mq = QUARTER_RE.match(t)
                if mq:
                    q = mq.group(1).upper()
                    date, freq = f"{date}-Q{ROMAN.get(q, q)}", "Q"
                    continue
            series_dims.append(re.sub(r"\s+", " ", t).strip())
        sid = table_id + "|" + "|".join(series_dims)
        pos.setdefault(sid, len(pos))
        d1, d2, d3 = (series_dims + ["", "", ""])[:3]
        if len(series_dims) > 3:
            d3 = " | ".join(series_dims[2:])
        rows.append((date, freq, table_id, sid, pos[sid], d1, d2, d3, _unit(series_dims, title), status, v, updated, SOURCE))
        freqs.add(freq)
    info = {
        "dims": " | ".join(f"{lab} [{n}]" for lab, n in zip(labels, sizes)),
        "time_dim": "/".join(x for x in [labels[year_i] if year_i is not None else "",
                                          labels[month_i] if month_i is not None else "",
                                          labels[quarter_i] if quarter_i is not None else ""] if x),
        "freq": "".join(sorted(freqs)),
        "n_rows": len(rows),
        "n_series": len({r[3] for r in rows}),
        "first": min((r[0] for r in rows if r[1] != "X"), default=""),
        "last": max((r[0] for r in rows if r[1] != "X"), default=""),
        "updated": updated,
        "label": str(ds.get("label", ""))[:200],
    }
    return rows, info
