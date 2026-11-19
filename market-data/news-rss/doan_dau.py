# -*- coding: utf-8 -*-
r"""doan_dau.py - lay DOAN DAU bai bao (sapo day du + 1-2 doan than bai dau tien) de nhan DN duoc nhac toi (19/11/2026).

RSS chi cho sapo cat ~200 ky tu -> DN nhac o doan than bai dau tien bi bo sot. Moi lan keo RSS: bai moi (trong DD_NGAY ngay,
toi da DD_TOI_DA bai/lan, moi nhat truoc) -> tai trang bai -> cot `doan_dau` trong news_master ("" = da thu, khong lay duoc).
Bo phan loai (newslib.PhanLoai.phan_loai) quet ma CK / ten DN trong doan_dau -> cot `ma` (+ `ma_doan_dau` = ma CHI co o doan dau).

    python doan_dau.py <url> [<url> ...]     thu trich 1 bai
"""
from __future__ import annotations

import re
import sys

DD_NGAY = 3                 # chi lay doan dau cho bai trong 3 ngay gan nhat
DD_TOI_DA = 300             # toi da 300 trang / lan keo (con bi chan boi DD_GIAY)
DD_KY_TU = 1200             # cat doan dau 1200 ky tu
DD_TIMEOUT = 8
DD_GIAY = 25                # tong thoi gian toi da 1 lan keo (app cho spinner) - bai chua kip lay o lan sau

# vung than bai theo bao (CSS) - khong khop thi dung heuristic: khoi co nhieu chu trong <p> nhat
THAN_BAI = {
    "cafef.vn": [".detail-content", "#mainContent", ".contentdetail"],
    "vietstock.vn": ["#vst_detail", ".single_post_heading", "#content"],
    "vneconomy.vn": [".detail__content", ".news-content"],
    "dantri.com.vn": [".singular-content", ".dt-news__content"],
    "vnexpress.net": [".fck_detail", "article.fck_detail"],
    "nhipsongkinhdoanh.vn": [".detail-content", ".article-content", ".content-detail"],
    "vietnamnet.vn": [".maincontent", ".main-content", "#maincontent"],
    "tuoitre.vn": [".detail-content", "#main-detail-body"],
    "vietnamplus.vn": [".article__body", ".content", ".article-body"],
    "thanhnien.vn": [".detail-content", ".detail-cmain"],
    "vietnambiz.vn": [".vnbcbc-body", ".vnbcb-content", ".content-detail"],
}
SAPO = [".sapo", ".detail-sapo", ".detail__summary", ".singular-sapo", "p.description", ".article__sapo", ".detail__sapo",
        "h2.sapo", ".vnbcbc-sapo", ".des"]
_BO = re.compile(r"^(ảnh|ảnh minh hoạ|nguồn|video|xem thêm|đọc thêm|tin liên quan|>>|\(ảnh)", re.I)
_WS = re.compile(r"\s+")


def _txt(el) -> str:
    return _WS.sub(" ", el.get_text(" ", strip=True)).strip()


def _doan_than_bai(soup, host: str) -> list[str]:
    """Cac doan <p> cua than bai (theo thu tu)."""
    vung = None
    for css in THAN_BAI.get(host, []):
        vung = soup.select_one(css)
        if vung is not None and len(_txt(vung)) > 200:
            break
        vung = None
    if vung is None:                                       # heuristic: cha cua cac <p> dai co tong chu lon nhat
        diem = {}
        for p in soup.find_all("p"):
            t = _txt(p)
            if len(t) >= 60 and p.parent is not None:
                diem[id(p.parent)] = (diem.get(id(p.parent), (p.parent, 0))[0], diem.get(id(p.parent), (p.parent, 0))[1] + len(t))
        if not diem:
            return []
        vung = max(diem.values(), key=lambda x: x[1])[0]
    out = []
    for p in vung.find_all(["p", "h2"]):
        if p.find_parent(["figure", "figcaption", "table", "aside"]) is not None:
            continue
        t = _txt(p)
        if len(t) >= 50 and not _BO.match(t):
            out.append(t)
    return out


def trich(html_bytes: bytes, url: str) -> str:
    """HTML trang bai -> 'sapo day du + 1-2 doan than bai dau' (<= DD_KY_TU ky tu)."""
    from bs4 import BeautifulSoup
    host = re.sub(r"^www\.", "", re.sub(r"^https?://([^/]+).*$", r"\1", url).lower())
    soup = BeautifulSoup(html_bytes, "lxml")
    for x in soup(["script", "style", "noscript", "iframe"]):
        x.decompose()
    # sapo: og:description truoc (luon la sapo cua CHINH bai; .des/.sapo co the la bai khac o sidebar - VietnamBiz)
    m = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "description"})
    sapo = _WS.sub(" ", (m.get("content") or "")).strip() if m else ""
    if len(sapo) < 40:
        sapo = ""
        for css in SAPO:
            el = soup.select_one(css)
            if el is not None and len(_txt(el)) >= 40:
                sapo = _txt(el)
                break
    sapo = re.sub(r"^\((Dân trí|VNA|TTXVN|ĐTCK|VnEconomy)\)\s*[-–]\s*", "", sapo)
    doan, ky = [], 0
    for t in _doan_than_bai(soup, host):
        if sapo and (t[:80] in sapo or sapo[:80] in t):     # doan trung sapo
            continue
        doan.append(t)
        ky += len(t)
        if len(doan) >= 2 or ky >= 600:
            break
    return (sapo + (" \n " if sapo and doan else "") + " ".join(doan))[:DD_KY_TU].strip()


def lay(url: str, session=None) -> str:
    """Tai 1 trang bai -> doan dau ('' neu loi)."""
    try:
        if session is None:
            sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))
            from mdlib import new_session
            session = new_session("browser")
        r = session.get(url, timeout=DD_TIMEOUT)
        if r.status_code != 200 or not r.content:
            return ""
        return trich(r.content, url)
    except Exception:  # noqa: BLE001
        return ""


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    for u in sys.argv[1:]:
        print(u, "\n ->", lay(u), "\n")
