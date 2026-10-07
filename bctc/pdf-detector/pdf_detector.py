# -*- coding: utf-8 -*-
"""
PDF Detector & Downloader
=========================
Quét một trang web có phân trang (?page=2, 3, 4 ...), phát hiện toàn bộ link PDF,
lọc theo tiêu chí bạn đặt (loại văn bản: báo cáo tài chính, công ty mẹ, hợp nhất...)
rồi tải về.

Cách dùng nhanh:
    python pdf_detector.py
  -> chạy theo CONFIG mặc định bên dưới, hỏi tiêu chí lọc qua bàn phím.

Hoặc truyền tham số dòng lệnh (bỏ qua phần hỏi):
    python pdf_detector.py --url "https://haiants.vn/bao-cao-tai-chinh-q8.html" --include "hợp nhất" --pages 1-14

Phân trang kiểu ĐƯỜNG DẪN (không phải ?page=N): nhét {page} vào URL, vd tcsc.vn:
    python pdf_detector.py --url "https://tcsc.vn/vi/download/Bao-cao-tai-chinh/page-{page}/" --include "kiểm toán"

Chỉ cần requests + beautifulsoup4.
"""

import argparse
import os
import re
import sys
import time
import unicodedata
from urllib.parse import (urljoin, urlparse, urlunparse, parse_qs, urlencode,
                          unquote as _unquote)

import requests
import urllib3
from bs4 import BeautifulSoup

# Ép stdout/stderr sang UTF-8 để in được tiếng Việt trên console Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ============================================================================
# CONFIG MẶC ĐỊNH  -- sửa ở đây nếu muốn khỏi gõ lại mỗi lần
# ============================================================================
CONFIG = {
    # URL gốc (không cần kèm ?page=). Tool sẽ tự gắn ?page=N vào.
    "base_url": "https://haiants.vn/bao-cao-tai-chinh-q8.html",

    # Khoảng trang quét: (trang_đầu, trang_cuối). Đặt trang_cuối = None để tự
    # dừng khi gặp trang không còn PDF mới.
    "page_start": 1,
    "page_end": None,          # None = quét tới khi hết

    # Tham số phân trang trên URL (mặc định "page"). Vài site dùng "p", "trang"...
    "page_param": "page",

    # ----- TIÊU CHÍ LỌC FILE -----
    # include: chỉ tải file có chứa MỘT TRONG các từ khoá này (bỏ dấu để dễ trùng).
    #          Để rỗng [] = tải tất cả PDF.
    "include_keywords": [],            # ví dụ: ["hợp nhất", "công ty mẹ"]
    # include_mode: "any" = khớp 1 từ khoá là đủ; "all" = phải khớp hết.
    "include_mode": "any",
    # exclude: bỏ qua file chứa bất kỳ từ khoá nào trong đây.
    "exclude_keywords": [],            # ví dụ: ["soát xét", "tiếng anh"]

    # Thư mục lưu file
    "out_dir": os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads"),

    # Nghỉ giữa các request (giây) cho lịch sự với server
    "delay": 0.5,

    # Ghi đè file đã tồn tại?
    "overwrite": False,

    # Chế độ: None = tự nhận diện (static / masvn). Ép bằng "static" hoặc "masvn".
    "mode": None,

    # Đổi tên file thống nhất "<LOẠI> - <TICKER> - <KỲ>": BẬT MẶC ĐỊNH, ticker
    # TỰ DETECT theo host (TICKER_BY_HOST). Host lạ -> giữ tên gốc. Tắt = --no-rename.
    "no_rename": False,
    "ticker": None,        # đè ticker tự detect (cho host lạ hoặc muốn ép)
    # Gom file vào thư mục con theo ticker (downloads/<TICKER>/). Tắt = --no-subfolder.
    "no_subfolder": False,
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "vi,en;q=0.8",
}

# Mã CK theo host (cho chế độ đổi tên thống nhất --rename). Có thể đè bằng --ticker.
TICKER_BY_HOST = {
    "ssi.com.vn": "SSI", "vixs.vn": "VIX", "tcsc.vn": "TCSC", "hsc.com.vn": "HCM",
    "vdsc.com.vn": "VDS", "shs.com.vn": "SHS", "mbs.com.vn": "MBS",
    "bsc.com.vn": "BSI", "bvsc.com.vn": "BVS", "pinetree.vn": "PINETREE",
    "masvn.com": "MAS", "kafi.vn": "KAFI", "haiants.vn": "HAH",
    "gelex-infra.vn": "GEL",
}

# Host có chuỗi chứng chỉ SSL lỗi (thiếu intermediate cert) -> phải tải với
# verify=False. http_get() tự phát hiện 1 lần rồi nhớ host vào đây cho lần sau.
_INSECURE_HOSTS = set()


def http_get(session: requests.Session, url: str, **kw):
    """session.get có FALLBACK SSL: nếu server lỗi chuỗi chứng chỉ (vd
    gelex-infra.vn thiếu intermediate cert -> 'unable to verify the first
    certificate'), tự thử lại với verify=False (và nhớ host để khỏi lỗi lại)."""
    host = urlparse(url).netloc.lower()
    if host in _INSECURE_HOSTS:
        kw.setdefault("verify", False)
    try:
        return session.get(url, **kw)
    except requests.exceptions.SSLError:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        _INSECURE_HOSTS.add(host)
        kw["verify"] = False
        return session.get(url, **kw)


# ============================================================================
# Tiện ích
# ============================================================================
def strip_accents(text: str) -> str:
    """Bỏ dấu tiếng Việt + lowercase + biến dấu phân tách thành khoảng trắng."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D").lower()
    # Biến mọi dấu phân tách (-, _, ., /, ...) thành khoảng trắng để
    # "hợp nhất" khớp được cả "hop-nhat" trong tên file URL.
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_url(u: str) -> str:
    """Sửa các URL dị dạng hay gặp trên web (gây rớt file im lặng).

    Ví dụ thật trên haiants.vn: 'http:/haiants.vn/...' (thiếu 1 dấu /).
    """
    u = u.strip()
    # http:/host -> http://host  (thiếu 1 gạch sau scheme)
    u = re.sub(r"^(https?):/(?!/)", r"\1://", u, flags=re.IGNORECASE)
    # //host (protocol-relative) -> https://host
    if u.startswith("//"):
        u = "https:" + u
    return u


def build_page_url(base_url: str, page_param: str, page_num: int) -> str:
    """Dựng URL trang N.

    - Nếu URL chứa placeholder ``{page}`` -> phân trang kiểu ĐƯỜNG DẪN
      (vd tcsc.vn/.../page-{page}/ ): thay {page} bằng số trang. Dùng cho site
      nhét số trang vào path chứ không phải query string.
    - Ngược lại: gắn/ghi đè ?page=N vào query, giữ nguyên các query khác.
    """
    if "{page}" in base_url:
        return base_url.replace("{page}", str(page_num))
    parts = urlparse(base_url)
    q = parse_qs(parts.query)
    q[page_param] = [str(page_num)]
    new_query = urlencode(q, doseq=True)
    return urlunparse(parts._replace(query=new_query))


def safe_filename(name: str) -> str:
    """Làm sạch tên file cho Windows."""
    name = name.strip()
    name = re.sub(r'[<>:"/\\|?*]+', "_", name)
    name = re.sub(r"\s+", " ", name)
    return name[:180]  # tránh path quá dài


# ============================================================================
# Lõi: tìm PDF trên 1 trang
# ============================================================================
def _clean_label_name(label: str) -> str:
    """Dọn nhãn để làm tên file: bỏ số đếm lượt tải ở cuối, gọn khoảng trắng."""
    label = re.sub(r"\s+\d{1,6}\s*$", "", label.strip())   # bỏ "... 452" (lượt tải)
    return re.sub(r"\s+", " ", label).strip()


def find_pdfs_on_page(html: str, page_url: str, extra_pdf_patterns=None):
    """
    Trả về list dict: {url, text, [dest]}
      url  = link tuyệt đối tới file PDF
      text = nhãn hiển thị / tên tài liệu kèm theo (dùng để lọc)
      dest = (chỉ với link tải KHÔNG đuôi .pdf) tên file gợi ý lấy từ nhãn

    extra_pdf_patterns: list regex (string) — link KHỚP cũng coi là PDF, dù URL
        không có đuôi .pdf. Dùng cho site tải qua endpoint id (vd VDSC:
        /data/api/app/file-storage/<uuid>?downloadFrom=...). Khi đó tên file
        không suy được từ URL nên lấy từ nhãn (dest).
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []
    seen = set()
    extra = [re.compile(p, re.IGNORECASE) for p in (extra_pdf_patterns or [])]

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        # Nhận diện PDF: đuôi .pdf (kể cả có ?query phía sau) HOẶC khớp pattern phụ.
        is_pdf = bool(re.search(r"\.pdf(\?.*)?$", href, re.IGNORECASE))
        is_extra = (not is_pdf) and any(rx.search(href) for rx in extra)
        if not (is_pdf or is_extra):
            continue

        abs_url = normalize_url(urljoin(page_url, href))
        if abs_url in seen:
            continue
        seen.add(abs_url)

        # Nhãn: ưu tiên text của link; nếu rỗng (link là icon tải) thì lấy
        # text của cả hàng <tr> chứa nó, rồi tới tên file.
        label = a.get_text(" ", strip=True)
        if not label or len(label) < 4:
            row = a.find_parent(["tr", "li"])
            if row:
                label = row.get_text(" ", strip=True)
        if not label:
            label = os.path.basename(urlparse(abs_url).path)

        item = {"url": abs_url, "text": label}
        if is_extra:
            # URL không có tên file -> đặt tên từ nhãn, kèm id cho chắc duy nhất.
            mid = re.search(r"[-/]([0-9]{2,})(?:[?&]|$)", href) or \
                  re.search(r"([0-9a-f]{6,})", href)
            suffix = f" [{mid.group(1)[:8]}]" if mid else ""
            item["dest"] = safe_filename(_clean_label_name(label) + suffix) + ".pdf"
        results.append(item)

    return results


def find_detail_links(html: str, page_url: str, detail_re):
    """Tìm link trang CHI TIẾT (site 2 tầng: list -> chi tiết -> PDF).

    Trả list {url, text}. detail_re = regex string khớp href trang chi tiết.
    """
    soup = BeautifulSoup(html, "html.parser")
    rx = re.compile(detail_re, re.IGNORECASE)
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not rx.search(href):
            continue
        abs_url = normalize_url(urljoin(page_url, href))
        if abs_url in seen:
            continue
        seen.add(abs_url)
        out.append({"url": abs_url, "text": a.get_text(" ", strip=True)})
    return out


# Từ đồng nghĩa cho các loại văn bản (đã chuẩn hoá: bỏ dấu, thường).
# Giúp khớp cả tên file viết tắt/liền: "công ty mẹ" -> "ctyme", "rieng"...
SYNONYMS = {
    "hop nhat": ["hop nhat", "hopnhat", "consolidated"],
    "cong ty me": ["cong ty me", "congtyme", "ctyme", "rieng", "me"],
    "rieng": ["rieng", "cong ty me", "ctyme", "congtyme"],
    "soat xet": ["soat xet", "soatxet", "reviewed"],
    "kiem toan": ["kiem toan", "kiemtoan", "audited", "da kiem toan"],
    "bao cao tai chinh": ["bao cao tai chinh", "baocaotaichinh", "bctc"],
}


def _variants(keyword_norm: str):
    """Trả về các biến thể (đã chuẩn hoá) của 1 từ khoá để so khớp rộng hơn."""
    base = SYNONYMS.get(keyword_norm, [keyword_norm])
    out = set()
    for v in base:
        out.add(v)                    # dạng có khoảng trắng
        out.add(v.replace(" ", ""))   # dạng liền (khớp HOPNHAT, CTYME...)
    return out


def _kw_in(keyword_norm: str, haystack: str, haystack_nospace: str) -> bool:
    """Một từ khoá khớp nếu BẤT KỲ biến thể nào xuất hiện (kể cả dạng liền)."""
    for v in _variants(keyword_norm):
        if " " in v:
            if v in haystack:
                return True
        else:
            if v in haystack or v in haystack_nospace:
                return True
    return False


def match_criteria(text: str, url: str, cfg: dict) -> bool:
    """Quyết định file có thoả tiêu chí lọc không."""
    haystack = strip_accents(text + " " + url)
    haystack_nospace = haystack.replace(" ", "")

    inc = [strip_accents(k) for k in cfg["include_keywords"] if k.strip()]
    exc = [strip_accents(k) for k in cfg["exclude_keywords"] if k.strip()]

    # exclude thắng tuyệt đối
    if any(_kw_in(k, haystack, haystack_nospace) for k in exc):
        return False

    if not inc:
        return True

    if cfg["include_mode"] == "all":
        return all(_kw_in(k, haystack, haystack_nospace) for k in inc)
    return any(_kw_in(k, haystack, haystack_nospace) for k in inc)


# ============================================================================
# Đặt tên thống nhất (chế độ --rename):  "<LOẠI> - <TICKER> - <KỲ>[ - HN/RIENG][ - KT][ - EN]"
#   LOẠI: BCTC (báo cáo tài chính) | BCTLATTC (tỷ lệ an toàn tài chính / vốn khả
#         dụng) | CBTT (công bố thông tin) | GiaiTrinh (giải trình lợi nhuận)
#   KỲ:   Q1.2026 / H1.2026 (bán niên) / 2026 (cả năm)
#   HN/RIENG: hợp nhất / riêng (công ty mẹ); KT: quý có kiểm toán/soát xét; EN: bản tiếng Anh
# Nếu KHÔNG nhận diện được loại hoặc kỳ -> trả None (giữ tên gốc, không mất file).
# ============================================================================
def _detect_period(hay: str):
    """hay = strip_accents(...) của nguồn nhận diện kỳ. Trả 'Q1.2026'/
    'H1.2026'/'2026' hoặc None."""
    quarter = qpat = None
    for n, pats in ((4, r"quy ?4|quy ?iv|q ?4"),
                    (3, r"quy ?3|quy ?iii|q ?3"),
                    (2, r"quy ?2|quy ?ii|q ?2"),
                    (1, r"quy ?1|quy ?i\b|q ?1")):
        if re.search(r"\b(?:%s)\b" % pats, hay):
            quarter, qpat = n, pats
            break
    half = bool(re.search(r"ban nien|bannien|6 thang|semi|\bh1\b|\b30 0?6\b", hay))
    # NĂM — chú ý nhãn hay mở đầu bằng NGÀY UPLOAD (vd "30 thang 1 2026 ... quy
    # iv 2025") nên KHÔNG lấy năm đầu tiên. Thứ tự ưu tiên:
    #   1) "nam YYYY"  2) năm ngay cạnh token quý  3) ngày cuối kỳ (31/12, 30/06)
    #   4) năm cạnh "bán niên"  5) năm XUẤT HIỆN CUỐI CÙNG (thường là năm kỳ b/c).
    y = re.search(r"nam (20\d\d)", hay)
    if not y and quarter:
        y = re.search(r"(?:%s)[ ./]*(20\d\d)" % qpat, hay)
    if not y:
        y = re.search(r"3[01] (?:12|0?6)[ ./]*(20\d\d)", hay)
    if not y and half:
        y = re.search(r"(?:ban nien|6 thang)[ ./]*(20\d\d)", hay)
    if not y:
        allyears = re.findall(r"20\d\d", hay)
        if allyears:
            return _mk_period(quarter, half, allyears[-1])
        return None
    return _mk_period(quarter, half, y.group(1))


def _mk_period(quarter, half, year):
    if quarter:
        return f"Q{quarter}.{year}"
    if half:
        return f"H1.{year}"
    return year


def _detect_type(fnh: str, titleh: str):
    """fnh/titleh = strip_accents của tên file / tiêu đề. Ưu tiên TÊN FILE (tiêu
    đề thường gộp cả 'công bố BCTC và tỷ lệ ATTC'). So khớp KHÔNG khoảng trắng để
    bắt cả tên viết liền (vd 'Congbothongtin', 'BSCBaocaotaichinh'). Trả LOẠI/None."""
    def cls(h):
        hns = h.replace(" ", "")            # dạng liền: "cong bo" -> "congbo"
        has_bctc = ("baocaotaichinh" in hns or "bctc" in hns or "financial" in hns)
        # GiaiTrinh = bản giải trình ĐỘC LẬP. Nhiều file (vd GEL) đính kèm BCTC +
        # "Van ban giai trinh" trong CÙNG 1 PDF ("BCTC ... va Van ban giai trinh")
        # -> nội dung chính là BCTC, KHÔNG phải giải trình. Chỉ nhận GiaiTrinh khi
        # KHÔNG kèm báo cáo tài chính.
        if ("giaitrinh" in hns or "explanation" in hns) and not has_bctc:
            return "GiaiTrinh"
        # BCTLATTC & BCTC kiểm tra TRƯỚC CBTT: nhiều site (vd SSI) thêm tiền tố
        # "CBTT_BCTC_" / "CBTT_..._ATTC_" vào MỌI file -> "cbtt" chỉ là nhãn công
        # bố, không phải loại. CBTT thật = bản công bố KHÔNG kèm từ khoá báo cáo.
        if ("antoantaichinh" in hns or "attc" in hns or "vonkhadung" in hns
                or "bctltc" in hns or "chitieuantoan" in hns):
            return "BCTLATTC"
        if has_bctc:
            return "BCTC"
        if "cbtt" in hns or "congbothongtin" in hns or "disclosure" in hns:
            return "CBTT"
        return None
    return cls(fnh) or cls(titleh)


def _filename_from_cd(cd: str):
    """Rút tên file từ header Content-Disposition (đáng tin hơn tên trong URL).
    Ưu tiên RFC5987 filename*=UTF-8''... (đã %-encode) rồi tới filename=..."""
    if not cd:
        return None
    m = re.search(r"filename\*\s*=\s*[^']*''([^;]+)", cd, re.I)
    if m:
        try:
            return _unquote(m.group(1)).strip().strip('"')
        except Exception:
            pass
    m = re.search(r'filename\s*=\s*"?([^";]+)"?', cd, re.I)
    if m:
        return m.group(1).strip()
    return None


def _pdf_first_text(path: str, maxchars: int = 1000) -> str:
    """Trích text vùng đầu trang 1 (để phân loại khi tên file/nhãn vô dụng, vd
    URL là uuid). Cần pdfplumber; lỗi -> ''. Chỉ lấy maxchars đầu (vùng tiêu đề)."""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                return ""
            return (pdf.pages[0].extract_text() or "")[:maxchars]
    except Exception:
        return ""


def unified_filename(title: str, url: str, ticker: str, header_name: str = None,
                     page_year: str = None):
    """Tạo tên file thống nhất; None nếu không phân loại được (giữ tên gốc).

    header_name: tên file lấy từ Content-Disposition (nếu có) -> ƯU TIÊN dùng để
    phân loại loại/kỳ vì tên trong URL hay bị loạn (uuid, %20, dính số...).
    page_year: năm của TRANG đang quét (vd GEL lọc theo năm qua nav-year). Dùng
    làm nguồn năm CUỐI khi tên file không chứa kỳ — đáng tin hơn nhãn web nhiễu."""
    fn = header_name or os.path.basename(urlparse(url).path)
    try:
        fn = _unquote(fn)
    except Exception:
        pass
    fn_clean = re.sub(r"^\d{6,8}[-_ ]", "", fn)   # bỏ ngày upload ở đầu tên file
    fnh = strip_accents(fn_clean)
    titleh = strip_accents(title or "")
    hay = (titleh + " " + fnh).strip()

    rtype = _detect_type(fnh, titleh)
    # Kỳ: ưu tiên TÊN FILE (nguồn tin cậy của chính tài liệu). Nhãn/tiêu đề lấy từ
    # web hay bị nhiễu — vd bảng GEL gộp nhiều cột quý vào 1 hàng -> nhãn dính
    # nhiều ngày/năm của báo cáo khác.
    period = _detect_period(fnh)
    used_pyear = False
    if not period:
        # Tên file không có kỳ: nếu biết NĂM TRANG (GEL) thì dùng năm đó (báo cáo
        # năm); nếu không, mới đành dùng nhãn (các site khác).
        if page_year and re.fullmatch(r"20\d\d", page_year):
            period, used_pyear = page_year, True
        else:
            period = _detect_period(hay)
    if not rtype or not period:
        return None

    name = f"{rtype} - {ticker} - {period}"
    if re.search(r"hop nhat|consolidated", hay):
        name += " - HN"
    elif re.search(r"\brieng\b|cong ty me|ctyme|separate", hay):
        name += " - RIENG"
    # KT (kiểm toán/soát xét): thêm cho QUÝ để khỏi trùng quý thường; HOẶC cho báo
    # cáo NĂM khi năm suy từ trang (GEL) mà file ghi "soát xét" — phân biệt bản
    # kiểm toán với bản công bố cùng năm (nếu không sẽ trùng tên, mất file).
    if (period.startswith("Q") or used_pyear) and \
            re.search(r"kiem toan|soat xet|audited|reviewed", hay):
        name += " - KT"
    # bản tiếng Anh -> thêm EN (tránh đè bản tiếng Việt cùng kỳ)
    if re.match(r"^en[ _]", fnh) or "english" in fnh or "financial statement" in fnh:
        name += " - EN"
    return name


# ============================================================================
# Tải file
# ============================================================================
def download(url: str, label: str, out_dir: str, session: requests.Session,
             overwrite: bool, dest_name: str = None, ticker: str = None,
             page_year: str = None) -> str:
    """Tải 1 PDF. Trả về trạng thái dạng chuỗi.

    dest_name: nếu truyền vào thì dùng làm tên file (đã đảm bảo duy nhất),
               bỏ qua logic suy tên từ nhãn/URL.
    ticker:    nếu có (chế độ --rename) -> thử đặt tên thống nhất theo
               unified_filename(); không phân loại được thì rơi về logic thường.
    """
    # Fetch TRƯỚC (stream, chưa tải body) để đọc tên file từ Content-Disposition
    # + content-type. Tên header đáng tin hơn URL (URL hay là uuid/%20/dính số).
    try:
        r = http_get(session, url, headers=HEADERS, stream=True, timeout=60)
        r.raise_for_status()
    except Exception as e:
        return f"  [LỖI] {url} -> {e}"
    try:
        ctype = r.headers.get("Content-Type", "")
        hdr_name = _filename_from_cd(r.headers.get("Content-Disposition", ""))

        # Đổi tên thống nhất: ưu tiên cao nhất; phân loại dựa tên HEADER trước.
        uni = None
        if ticker:
            uni = unified_filename(label, url, ticker, header_name=hdr_name,
                                   page_year=page_year)
            if uni:
                dest_name = uni

        # Tên lưu (khi không đổi tên thống nhất): header > nhãn (nếu không phải nút
        # chung chung) > tên trong URL.
        generic = {"tai ve", "tai xuong", "download", "xem", "chi tiet", "pdf"}
        url_name = os.path.basename(urlparse(url).path)
        try:                                   # giải mã %20... cho tên đỡ "loạn"
            url_name = _unquote(url_name)
        except Exception:
            pass
        if dest_name:
            base = dest_name
        elif hdr_name:
            base = hdr_name
        elif label and len(label) >= 8 and strip_accents(label) not in generic:
            base = label
        else:
            base = url_name
        base = safe_filename(base)
        if not base.lower().endswith(".pdf"):
            base += ".pdf"

        dest = os.path.join(out_dir, base)
        if os.path.exists(dest) and not overwrite:
            return f"  [bỏ qua] đã có: {base}"

        is_pdf = ("pdf" in ctype.lower() or url.lower().endswith(".pdf")
                  or (hdr_name or "").lower().endswith(".pdf"))
        if not is_pdf:
            return f"  [cảnh báo] không phải PDF ({ctype}): {url}"

        tmp = dest + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        os.replace(tmp, dest)

        # Fallback NỘI DUNG: bật đổi tên nhưng KHÔNG phân loại được từ tên/nhãn/
        # header (vd URL là uuid, nhãn chỉ là icon) -> đọc text trang 1 phân loại
        # rồi đổi tên file vừa lưu.
        if ticker and not uni:
            uni2 = unified_filename(_pdf_first_text(dest), url, ticker)
            if uni2:
                nb = safe_filename(uni2) + ".pdf"
                nd = os.path.join(out_dir, nb)
                if nd != dest:
                    if os.path.exists(nd) and not overwrite:
                        i, b = 2, safe_filename(uni2)
                        while os.path.exists(os.path.join(out_dir, f"{b} ({i}).pdf")):
                            i += 1
                        nb, nd = f"{b} ({i}).pdf", os.path.join(out_dir, f"{b} ({i}).pdf")
                    os.replace(dest, nd)
                    base = nb

        size = os.path.getsize(os.path.join(out_dir, base)) / 1024
        return f"  [TẢI] {base}  ({size:,.0f} KB)"
    except Exception as e:
        return f"  [LỖI] {url} -> {e}"
    finally:
        r.close()


# ============================================================================
# Adapter cho site SPA (JavaScript) — dùng API JSON thay vì cào HTML.
# Hiện hỗ trợ: masvn.com (Mirae Asset VN) — trang /cate/<slug>-<id>.
# ----------------------------------------------------------------------------
# masvn là Nuxt SPA: danh sách báo cáo KHÔNG nằm trong HTML mà nạp qua API
#   GET https://masvn.com/api/categories/fe/<id>/article?page=N&limit=20
# (không cần token). Mỗi item có title + file_path -> link PDF.
# ============================================================================
import json as _json
from urllib.parse import quote as _quote


def detect_mode(url: str) -> str:
    """Tự nhận diện loại site."""
    host = urlparse(url).netloc.lower()
    if "masvn.com" in host and "/cate/" in url:
        return "masvn"
    if "kafi.vn" in host and "/investors" in url:
        return "kafi"
    if "shs.com.vn" in host and "/bao-cao-dinh-ky/" in url:
        return "shs"
    if "vdsc.com.vn" in host:
        return "vdsc"
    if "mbs.com.vn" in host and "/bao-cao-" in url:
        return "mbs"
    if "bsc.com.vn" in host and re.search(r"/(bao-cao-tai-chinh|bao-cao-thuong-nien|bao-cao-quan-tri|bien-ban)", url):
        return "bsc"
    if "pinetree.vn" in host and "/post/category/" in url:
        return "pinetree"
    if "bvsc.com.vn" in host and "/danhmuc/" in url:
        return "bvsc"
    if "gelex-infra.vn" in host and "/doc-cat/" in url:
        return "gel"
    return "static"


def _masvn_title(raw):
    """title trên masvn dạng JSON {"vi": "...","en": "..."}; lấy tiếng Việt."""
    if not raw:
        return ""
    try:
        d = _json.loads(raw)
        return d.get("vi") or d.get("en") or next(iter(d.values()), "")
    except Exception:
        return str(raw)


def run_masvn(cfg: dict, session: requests.Session):
    """Tải báo cáo từ masvn.com qua API JSON (có phân trang thật)."""
    m = re.search(r"/cate/[^/?#]*?-(\d+)", cfg["base_url"])
    if not m:
        print("  [LỖI] Không tách được category id từ URL masvn.")
        return
    cate_id = m.group(1)
    api = f"https://masvn.com/api/categories/fe/{cate_id}/article"
    hdr = dict(HEADERS)
    hdr.update({"Accept": "application/json, text/plain, */*",
                "Referer": cfg["base_url"], "Origin": "https://masvn.com"})

    total_found = total_match = total_dl = 0
    failures = []
    page = cfg["page_start"]
    last_page = cfg["page_end"]   # None = chưa biết, lấy từ API

    while True:
        if cfg["page_end"] is not None and page > cfg["page_end"]:
            break
        params = {"paging": 1, "active": 1, "sort": "published_at",
                  "direction": "desc", "page": page, "limit": 20}
        if cfg["include_keywords"]:
            # gửi 1 từ khoá lên server cho nhẹ; phần lọc chính vẫn làm ở client
            pass
        print(f"\n--- Trang {page}: {api}?page={page}")
        try:
            r = session.get(api, params=params, headers=hdr, timeout=30)
            r.raise_for_status()
            d = r.json()
        except Exception as e:
            print(f"  [LỖI API] {e}")
            break

        items = d.get("data") or []
        if last_page is None:
            last_page = d.get("last_page") or 1
            print(f"  (tổng {d.get('total','?')} báo cáo, {last_page} trang)")
        if not items:
            print("  (trang rỗng) -> dừng.")
            break

        for it in items:
            fp = it.get("file_path") or ""
            if not fp:
                continue
            title = _masvn_title(it.get("title"))
            url = "https://masvn.com/api" + _quote(fp)
            total_found += 1
            # match trên title + tên file, NHƯNG bỏ tiền tố timestamp-ngày upload
            # (vd 1774950044539-20260331-) để năm upload không gây dương tính giả.
            name_clean = re.sub(r"^\d{6,}-(?:\d{6,}-)?", "",
                                os.path.basename(fp))
            # url để rỗng: tránh ngày upload trong URL gây dương tính giả theo năm
            if match_criteria(title + " " + name_clean, "", cfg):
                total_match += 1
                # tên file: title cho dễ đọc + id để chắc chắn không trùng
                raw_name = os.path.basename(fp)
                dest = safe_filename(f"{title} [{it.get('id')}]") + ".pdf" \
                    if title else safe_filename(raw_name)
                status = download(url, title, cfg["out_dir"], session,
                                  cfg["overwrite"], dest_name=dest,
                                  ticker=cfg.get("rename_ticker"))
                if "[TẢI]" in status:
                    total_dl += 1
                elif "[LỖI]" in status or "cảnh báo" in status:
                    failures.append((url, status.strip()))
                print(f"  • {title[:60]}")
                print(status)
                time.sleep(cfg["delay"])
            else:
                print(f"  - (bỏ, không khớp) {title[:60]}")

        if cfg["page_end"] is None and page >= last_page:
            break
        page += 1
        time.sleep(cfg["delay"])

    print("\n" + "=" * 70)
    print(f"XONG. Tìm thấy {total_found} báo cáo | khớp tiêu chí {total_match} | "
          f"tải thành công {total_dl} file.")
    skipped = total_match - total_dl - len(failures)
    if skipped > 0:
        print(f"  ({skipped} file đã có sẵn -> bỏ qua. Dùng --overwrite để tải lại.)")
    if failures:
        print(f"\n  !! {len(failures)} FILE TẢI LỖI:")
        for u, st in failures:
            print(f"     - {u}\n       {st}")
    print(f"\nThư mục: {cfg['out_dir']}")
    print("=" * 70)


# ============================================================================
# Adapter cho shs.com.vn (Nuxt SPA + API Strapi same-origin).
# ----------------------------------------------------------------------------
# URL người dùng dán: shs.com.vn/quan-he-co-dong/bao-cao-dinh-ky/<CODE>
#   <CODE> = mã category (TAICHINH, ANTOANTAICHINH, THUONGNIEN...).
# List nạp client-side -> SSR HTML chỉ có 10 báo cáo mới nhất. Lấy đủ qua API:
#   GET /api/shareholders/periodic-report?category=<CODE>&page=N&pageSize=100
#   -> {data:[{Title, Summary(HTML chứa link .pdf), PublishedDate, ...}],
#       meta:{pagination:{page,pageCount,total}}}
# PDF (bản VI + EN) nằm trong Summary, host s3-storage.shs.com.vn. Lọc bằng
# Title + tên file (đã có "tài chính/kiểm toán/quý" + VI_/EN_ phân biệt ngôn ngữ).
# ============================================================================
def run_shs(cfg: dict, session: requests.Session):
    """Tải báo cáo định kỳ SHS qua API JSON (phân trang thật)."""
    parts = urlparse(cfg["base_url"])
    code = parts.path.rstrip("/").split("/")[-1]    # mã category cuối URL
    api = f"{parts.scheme}://{parts.netloc}/api/shareholders/periodic-report"
    hdr = dict(HEADERS)
    hdr.update({"Accept": "application/json", "Referer": cfg["base_url"]})

    total_found = total_match = total_dl = 0
    failures = []
    seen = set()
    page = cfg["page_start"]
    page_count = cfg["page_end"]   # None = lấy từ API

    while True:
        if cfg["page_end"] is not None and page > cfg["page_end"]:
            break
        params = {"category": code, "page": page, "pageSize": 100}
        print(f"\n--- Trang {page}: {api}?category={code}&page={page}")
        try:
            r = session.get(api, params=params, headers=hdr, timeout=30)
            r.raise_for_status()
            d = r.json()
        except Exception as e:
            print(f"  [LỖI API] {e}")
            break

        items = d.get("data") or []
        if page_count is None:
            pag = (d.get("meta") or {}).get("pagination") or {}
            page_count = pag.get("pageCount") or 1
            print(f"  (tổng {pag.get('total','?')} báo cáo, {page_count} trang)")
        if not items:
            print("  (trang rỗng) -> dừng.")
            break

        for it in items:
            title = it.get("Title") or ""
            blob = _json.dumps(it, ensure_ascii=False)
            pdfs = list(dict.fromkeys(re.findall(r"https?://[^\"'<>\\ ]+\.pdf", blob, re.I)))
            for url in pdfs:
                if url in seen:
                    continue
                seen.add(url)
                fname = os.path.basename(urlparse(url).path)
                total_found += 1
                # lọc trên Title + tên file (cả 2 đều giàu từ khoá VI_/EN_/quý/năm)
                if match_criteria(title + " " + fname, "", cfg):
                    total_match += 1
                    status = download(url, title, cfg["out_dir"], session,
                                      cfg["overwrite"], dest_name=safe_filename(fname),
                                      ticker=cfg.get("rename_ticker"))
                    if "[TẢI]" in status:
                        total_dl += 1
                    elif "[LỖI]" in status or "cảnh báo" in status:
                        failures.append((url, status.strip()))
                    print(f"  • {fname[:60]}")
                    print(status)
                    time.sleep(cfg["delay"])
                else:
                    print(f"  - (bỏ, không khớp) {fname[:60]}")

        if cfg["page_end"] is None and page >= page_count:
            break
        page += 1
        time.sleep(cfg["delay"])

    print("\n" + "=" * 70)
    print(f"XONG. Tìm thấy {total_found} PDF | khớp tiêu chí {total_match} | "
          f"tải thành công {total_dl} file.")
    skipped = total_match - total_dl - len(failures)
    if skipped > 0:
        print(f"  ({skipped} file đã có sẵn -> bỏ qua. Dùng --overwrite để tải lại.)")
    if failures:
        print(f"\n  !! {len(failures)} FILE TẢI LỖI:")
        for u, st in failures:
            print(f"     - {u}\n       {st}")
    print(f"\nThư mục: {cfg['out_dir']}")
    print("=" * 70)


# ============================================================================
# Adapter cho bsc.com.vn (WordPress + widget modal qua admin-ajax).
# ----------------------------------------------------------------------------
# Trang list (vd /bao-cao-tai-chinh/) render SSR mỗi báo cáo là 1 div có
# data-id=<post id> + tiêu đề/ngày, KHÔNG có link PDF (modal nạp khi click).
# Click -> POST admin-ajax:
#   action=get_content_qhcd & id_post=<id> & newstype=0 & security=<nonce>
#   -> HTML modal chứa link PDF trên files.bsc.com.vn/news/...  (cần header
#      X-Requested-With + Referer, nếu thiếu trả rỗng). Cloudflare KHÔNG chặn.
# Phân trang query ?post_page=N (auto-dừng khi trang không còn data-id).
# ⚠️ Một số post BSC không đính kèm PDF công khai (modal chỉ ghi "xem tập tin
#    đính kèm" mà không có link, hoặc gated recaptcha) -> bỏ qua tự nhiên.
# ============================================================================
def run_bsc(cfg: dict, session: requests.Session):
    """Tải báo cáo BSC: list -> POST modal get_content_qhcd lấy PDF."""
    parts = urlparse(cfg["base_url"])
    list_base = f"{parts.scheme}://{parts.netloc}{parts.path}"
    ajax = f"{parts.scheme}://{parts.netloc}/wp-admin/admin-ajax.php"
    hdr = dict(HEADERS)
    hdr.update({"X-Requested-With": "XMLHttpRequest", "Referer": cfg["base_url"],
                "Origin": f"{parts.scheme}://{parts.netloc}"})

    total_found = total_match = total_dl = 0
    failures, seen_ids, seen_files = [], set(), set()
    page = cfg["page_start"]
    empty_streak = 0
    nonce = None

    while True:
        if cfg["page_end"] is not None and page > cfg["page_end"]:
            break
        url = f"{list_base}?post_page={page}"
        print(f"\n--- Trang {page}: {url}")
        try:
            r = session.get(url, headers=hdr, timeout=30)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
        except Exception as e:
            print(f"  [LỖI tải trang] {e}")
            break

        if nonce is None:
            m = re.search(r'security["\']?\s*[:=]\s*["\']([a-f0-9]{8,12})', r.text)
            nonce = m.group(1) if m else ""
            print(f"  (nonce={nonce or 'KHÔNG TÌM THẤY'})")

        soup = BeautifulSoup(r.text, "html.parser")
        rows = []
        for d in soup.select("[data-id]"):
            idp = (d.get("data-id") or "").strip()
            if not idp.isdigit() or idp in seen_ids:
                continue
            ps = [p.get_text(" ", strip=True) for p in d.find_all("p")]
            cand = [p for p in ps if "báo cáo" in p.lower() or "công bố" in p.lower()]
            title = max(cand or ps or [""], key=len)
            nt = d.get("data-newstype") or "0"
            rows.append((idp, title, nt))

        if not rows:
            empty_streak += 1
            print("  (không có báo cáo mới)")
            if cfg["page_end"] is None and empty_streak >= 2:
                print("  -> Hết trang. Dừng.")
                break
            page += 1
            time.sleep(cfg["delay"])
            continue
        empty_streak = 0

        for idp, title, nt in rows:
            seen_ids.add(idp)
            try:
                pr = session.post(ajax, headers=hdr, timeout=30, data={
                    "action": "get_content_qhcd", "id_post": idp,
                    "newstype": nt, "security": nonce})
                pr.raise_for_status()
            except Exception as e:
                print(f"  [LỖI modal id={idp}] {e}")
                continue
            pdfs = [u for u in dict.fromkeys(
                    re.findall(r"https?://[^\"'<> ]+\.pdf", pr.text, re.I))
                    if u not in seen_files]
            if not pdfs:
                print(f"  - (không có PDF) {title[:55]}")
            for u in pdfs:
                seen_files.add(u)
                fname = os.path.basename(urlparse(u).path)
                total_found += 1
                if match_criteria(title + " " + fname, "", cfg):
                    total_match += 1
                    status = download(u, title, cfg["out_dir"], session,
                                      cfg["overwrite"], dest_name=safe_filename(fname),
                                      ticker=cfg.get("rename_ticker"))
                    if "[TẢI]" in status:
                        total_dl += 1
                    elif "[LỖI]" in status or "cảnh báo" in status:
                        failures.append((u, status.strip()))
                    print(f"  • {title[:55]}")
                    print(status)
                else:
                    print(f"  - (bỏ, không khớp) {fname[:55]}")
            time.sleep(cfg["delay"])
        page += 1
        time.sleep(cfg["delay"])

    print("\n" + "=" * 70)
    print(f"XONG. Tìm thấy {total_found} PDF | khớp tiêu chí {total_match} | "
          f"tải thành công {total_dl} file.")
    skipped = total_match - total_dl - len(failures)
    if skipped > 0:
        print(f"  ({skipped} file đã có sẵn -> bỏ qua. Dùng --overwrite để tải lại.)")
    if failures:
        print(f"\n  !! {len(failures)} FILE TẢI LỖI:")
        for u, st in failures:
            print(f"     - {u}\n       {st}")
    print(f"\nThư mục: {cfg['out_dir']}")
    print("=" * 70)


# ============================================================================
# Adapter cho kafi.vn/investors (Phoenix LiveView SPA).
# ----------------------------------------------------------------------------
# Danh sách báo cáo nằm SẴN trong HTML tĩnh (SSR), mỗi tài liệu là 1 div có
#   phx-click navigate -> /investors-details?tab=tntttc&id=<GoogleDriveID>
# File PDF lưu trên Google Drive. Tab "Thông tin tài chính" (tntttc) lấy được
# qua HTML tĩnh; các tab khác dùng websocket (cần browser) -> chưa hỗ trợ.
# ============================================================================
import html as _html


def _clean_title(t: str) -> str:
    t = re.sub(r"<[^>]+>", "", t)          # bỏ tag (img icon)
    t = _html.unescape(t)
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^\d+\.\s*", "", t)        # bỏ "2. " đầu dòng
    return t


def drive_download(file_id: str, dest_path: str, session: requests.Session,
                   overwrite: bool) -> str:
    """Tải 1 file từ Google Drive theo id. Xử lý cả trang xác nhận file lớn."""
    if os.path.exists(dest_path) and not overwrite:
        return f"  [bỏ qua] đã có: {os.path.basename(dest_path)}"
    url = "https://drive.usercontent.google.com/download"
    params = {"id": file_id, "export": "download"}
    try:
        r = session.get(url, params=params, headers=HEADERS, stream=True, timeout=90)
        # File lớn -> Google trả trang HTML xác nhận; lấy token rồi tải lại.
        ctype = r.headers.get("Content-Type", "")
        if "text/html" in ctype.lower():
            page = r.text
            form = {m.group(1): m.group(2) for m in
                    re.finditer(r'name="([^"]+)"\s+value="([^"]*)"', page)}
            if form:
                r = session.get(url, params=form, headers=HEADERS,
                                stream=True, timeout=180)
            else:
                return f"  [LỖI] Drive cần xác nhận nhưng không lấy được token: {file_id}"
        r.raise_for_status()
        tmp = dest_path + ".part"
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        os.replace(tmp, dest_path)
        size = os.path.getsize(dest_path) / 1024
        return f"  [TẢI] {os.path.basename(dest_path)}  ({size:,.0f} KB)"
    except Exception as e:
        return f"  [LỖI] drive:{file_id} -> {e}"


def run_kafi(cfg: dict, session: requests.Session):
    """Tải báo cáo tài chính từ kafi.vn/investors (HTML tĩnh + Google Drive)."""
    try:
        r = session.get("https://kafi.vn/investors", headers=HEADERS, timeout=30)
        r.raise_for_status()
        raw = r.text
    except Exception as e:
        print(f"  [LỖI tải trang] {e}")
        return

    # Mỗi tài liệu: phx-click navigate id=<drive id> ... <p ...link>title</p> ... <p text-N-500>date</p>
    blocks = re.findall(
        r'navigate&quot;,\{&quot;href&quot;:&quot;/investors-details\?tab='
        r'([a-z]+)&amp;id=([A-Za-z0-9_\-]{20,})&quot;.*?'
        r'<p class="[^"]*link[^"]*">(.*?)</p>.*?'
        r'<p class="text-N-500[^"]*">(.*?)</p>',
        raw, re.S)

    total_found = total_match = total_dl = 0
    failures = []
    seen = set()
    for tab, fid, title_raw, date_raw in blocks:
        if fid in seen:
            continue
        seen.add(fid)
        title = _clean_title(title_raw)
        date = _clean_title(date_raw)              # vd 20/04/2026
        total_found += 1
        if match_criteria(title + " " + date, "", cfg):
            total_match += 1
            d = date.replace("/", "-")
            # đổi tên thống nhất nếu bật --rename và phân loại được; nếu không
            # giữ "{tiêu đề} ({ngày}).pdf". (date dạng DD-MM-YYYY có năm cho kỳ.)
            uni = (unified_filename(f"{title} {date}", "", cfg["rename_ticker"])
                   if cfg.get("rename_ticker") else None)
            base = (uni + ".pdf") if uni else (safe_filename(f"{title} ({d})") + ".pdf")
            dest = os.path.join(cfg["out_dir"], base)
            status = drive_download(fid, dest, session, cfg["overwrite"])
            if "[TẢI]" in status:
                total_dl += 1
            elif "[LỖI]" in status:
                failures.append((fid, status.strip()))
            print(f"  • {title[:55]}  ({date})")
            print(status)
            time.sleep(cfg["delay"])
        else:
            print(f"  - (bỏ, không khớp) {title[:55]}  ({date})")

    print("\n" + "=" * 70)
    print(f"XONG. Tìm thấy {total_found} tài liệu | khớp tiêu chí {total_match} | "
          f"tải thành công {total_dl} file.")
    skipped = total_match - total_dl - len(failures)
    if skipped > 0:
        print(f"  ({skipped} file đã có sẵn -> bỏ qua. Dùng --overwrite để tải lại.)")
    if failures:
        print(f"\n  !! {len(failures)} FILE TẢI LỖI:")
        for u, st in failures:
            print(f"     - {u}\n       {st}")
    print("\n  (Chỉ lấy tab 'Thông tin tài chính'. Các tab khác cần chế độ browser.)")
    print(f"\nThư mục: {cfg['out_dir']}")
    print("=" * 70)


# ============================================================================
# Chạy chính
# ============================================================================
def run_gel(cfg: dict, session: requests.Session):
    """gelex-infra.vn (WordPress). PDF nằm INLINE trong bảng báo cáo
    (wp-content/uploads/.../*.pdf). 'Phân trang' thực chất là BỘ LỌC NĂM:
    <ul class="nav-year"> ... <a href="/doc-cat/<cat>/?y=<term_id>">2026</a> ...
    Mỗi năm 1 term_id (không đoán được, phải đọc từ nav). Quét trang gốc để lấy
    danh sách năm rồi duyệt TỪNG NĂM -> full lịch sử. Cert chain lỗi: http_get tự
    fallback verify=False."""
    base = cfg["base_url"]
    try:
        r = http_get(session, base, headers=HEADERS, timeout=30)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
    except Exception as e:
        print(f"  [LỖI tải trang gốc] {e}")
        return
    soup = BeautifulSoup(r.text, "html.parser")

    # Danh sách năm từ nav-year (giữ thứ tự xuất hiện, khử trùng theo URL).
    year_urls, seen_y = [], set()
    for a in soup.select("ul.nav-year a[href]"):
        href = a["href"]
        if re.search(r"[?&]y=\d+", href):
            u = normalize_url(urljoin(base, href))
            if u not in seen_y:
                seen_y.add(u)
                year_urls.append((a.get_text(strip=True) or "?", u))
    if not year_urls:
        year_urls = [("(trang hiện tại)", base)]
    print(f"  [chế độ gel] {len(year_urls)} năm: "
          f"{', '.join(l for l, _ in year_urls)}")

    seen_files = set()
    total_found = total_match = total_dl = 0
    failures = []
    for lbl, yurl in year_urls:
        print(f"\n--- Năm {lbl}: {yurl}")
        if yurl == base:
            html = r.text                       # tái dùng trang gốc đã tải
        else:
            try:
                yr = http_get(session, yurl, headers=HEADERS, timeout=30)
                yr.raise_for_status()
                yr.encoding = yr.apparent_encoding or "utf-8"
                html = yr.text
            except Exception as e:
                print(f"  [LỖI tải năm {lbl}] {e}")
                continue
        new = [p for p in find_pdfs_on_page(html, yurl)
               if p["url"] not in seen_files]
        print(f"  ({len(new)} PDF)")
        for p in new:
            seen_files.add(p["url"])
            total_found += 1
            if match_criteria(p["text"], p["url"], cfg):
                total_match += 1
                pyear = lbl if re.fullmatch(r"20\d\d", lbl or "") else None
                status = download(p["url"], p["text"], cfg["out_dir"], session,
                                  cfg["overwrite"], dest_name=p.get("dest"),
                                  ticker=cfg.get("rename_ticker"),
                                  page_year=pyear)
                if "[TẢI]" in status:
                    total_dl += 1
                elif "[LỖI]" in status or "cảnh báo" in status:
                    failures.append((p["url"], status.strip()))
                print(f"  • {p['text'][:60]}")
                print(status)
                time.sleep(cfg["delay"])
            else:
                print(f"  - (bỏ, không khớp) {p['text'][:60]}")
        time.sleep(cfg["delay"])

    print("\n" + "=" * 70)
    print(f"XONG. Tìm thấy {total_found} PDF | khớp tiêu chí {total_match} | "
          f"tải thành công {total_dl} file.")
    skipped = total_match - total_dl - len(failures)
    if skipped > 0:
        print(f"  ({skipped} file đã có sẵn -> bỏ qua. Dùng --overwrite để tải lại.)")
    if failures:
        print(f"\n  !! {len(failures)} FILE TẢI LỖI (không có trên đĩa):")
        for u, st in failures:
            print(f"     - {u}\n       {st}")
    print(f"\nThư mục: {cfg['out_dir']}")
    print("=" * 70)


def run(cfg: dict):
    session = requests.Session()

    # TICKER TỰ DETECT theo host (dùng cho cả đổi tên & gom thư mục). --ticker đè.
    host = urlparse(cfg["base_url"]).netloc.lower().replace("www.", "")
    tk = cfg.get("ticker") or next(
        (v for h, v in TICKER_BY_HOST.items() if h in host), None)
    tk = tk.upper() if tk else None

    # (1) Đổi tên thống nhất: BẬT MẶC ĐỊNH (tắt bằng --no-rename).
    cfg["rename_ticker"] = None
    if not cfg.get("no_rename"):
        if tk:
            cfg["rename_ticker"] = tk
            print(f"  [đổi tên: TỰ ĐỘNG] BCTC/BCTLATTC/CBTT/GiaiTrinh - "
                  f"{tk} - <kỳ>   (tắt: --no-rename)")
        else:
            print("  [đổi tên] host lạ, không tự detect được mã CK -> giữ tên "
                  "gốc. (Thêm --ticker <MÃ> nếu muốn đổi tên.)")

    # (2) Gom file vào THƯ MỤC CON theo ticker (vd downloads/SSI/). BẬT MẶC ĐỊNH
    # khi detect được ticker; tắt bằng --no-subfolder.
    if tk and not cfg.get("no_subfolder"):
        cfg["out_dir"] = os.path.join(cfg["out_dir"], tk)
        print(f"  [thư mục] gom vào: {cfg['out_dir']}   (tắt: --no-subfolder)")

    os.makedirs(cfg["out_dir"], exist_ok=True)

    # Tự nhận diện site SPA (vd masvn.com) -> dùng API thay vì cào HTML.
    mode = cfg.get("mode") or detect_mode(cfg["base_url"])
    if mode == "masvn":
        print("=" * 70)
        print("PDF DETECTOR  [chế độ masvn / API JSON]")
        print(f"  URL gốc   : {cfg['base_url']}")
        print(f"  Trang     : {cfg['page_start']} -> "
              f"{cfg['page_end'] if cfg['page_end'] else 'hết'}")
        print(f"  Include   : {cfg['include_keywords'] or '(tất cả)'} "
              f"[{cfg['include_mode']}]")
        print(f"  Exclude   : {cfg['exclude_keywords'] or '(không)'}")
        print(f"  Lưu vào   : {cfg['out_dir']}")
        print("=" * 70)
        run_masvn(cfg, session)
        return

    if mode == "kafi":
        print("=" * 70)
        print("PDF DETECTOR  [chế độ kafi / HTML tĩnh + Google Drive]")
        print(f"  URL gốc   : {cfg['base_url']}")
        print(f"  Include   : {cfg['include_keywords'] or '(tất cả)'} "
              f"[{cfg['include_mode']}]")
        print(f"  Exclude   : {cfg['exclude_keywords'] or '(không)'}")
        print(f"  Lưu vào   : {cfg['out_dir']}")
        print("=" * 70)
        run_kafi(cfg, session)
        return

    if mode == "shs":
        print("=" * 70)
        print("PDF DETECTOR  [chế độ shs / API JSON]")
        print(f"  URL gốc   : {cfg['base_url']}")
        print(f"  Trang     : {cfg['page_start']} -> "
              f"{cfg['page_end'] if cfg['page_end'] else 'hết'}")
        print(f"  Include   : {cfg['include_keywords'] or '(tất cả)'} "
              f"[{cfg['include_mode']}]")
        print(f"  Exclude   : {cfg['exclude_keywords'] or '(không)'}")
        print(f"  Lưu vào   : {cfg['out_dir']}")
        print("=" * 70)
        run_shs(cfg, session)
        return

    if mode == "bsc":
        print("=" * 70)
        print("PDF DETECTOR  [chế độ bsc / list + modal admin-ajax]")
        print(f"  URL gốc   : {cfg['base_url']}")
        print(f"  Trang     : {cfg['page_start']} -> "
              f"{cfg['page_end'] if cfg['page_end'] else 'tự dừng'}")
        print(f"  Include   : {cfg['include_keywords'] or '(tất cả)'} "
              f"[{cfg['include_mode']}]")
        print(f"  Exclude   : {cfg['exclude_keywords'] or '(không)'}")
        print(f"  Lưu vào   : {cfg['out_dir']}")
        print("=" * 70)
        run_bsc(cfg, session)
        return

    if mode == "gel":
        print("=" * 70)
        print("PDF DETECTOR  [chế độ gel / WordPress, PDF inline, lọc theo NĂM]")
        print(f"  URL gốc   : {cfg['base_url']}")
        print(f"  Include   : {cfg['include_keywords'] or '(tất cả)'} "
              f"[{cfg['include_mode']}]")
        print(f"  Exclude   : {cfg['exclude_keywords'] or '(không)'}")
        print(f"  Lưu vào   : {cfg['out_dir']}")
        print("=" * 70)
        run_gel(cfg, session)
        return

    if mode == "vdsc":
        # VDSC = static HTML thường + phân trang ?page=N, NHƯNG link tải là
        # endpoint id (không đuôi .pdf) -> bật pattern nhận diện phụ.
        cfg["extra_pdf_patterns"] = [r"/file-storage/"]
        print("  [chế độ vdsc] bật nhận diện link /file-storage/ (không đuôi .pdf)")

    if mode == "mbs":
        # MBS (WordPress) = static 2 TẦNG: trang list (SSR) -> trang chi tiết -> PDF.
        # Phân trang kiểu path /<slug>/page/N/. List slug = đoạn cuối URL; trang
        # chi tiết có href /<slug>-<...>. (Cloudflare chỉ chặn POST admin-ajax,
        # KHÔNG chặn GET nên dùng requests bình thường, khỏi cần browser.)
        parts = urlparse(cfg["base_url"])
        slug = parts.path.strip("/").split("/")[-1]
        cfg["follow_detail_re"] = r"/" + re.escape(slug) + r"-[^/]+/?$"
        if "{page}" not in cfg["base_url"]:
            root = f"{parts.scheme}://{parts.netloc}/{slug}"
            cfg["base_url"] = root + "/page/{page}/"
        print(f"  [chế độ mbs] 2 tầng: list -> chi tiết. slug='{slug}', "
              f"phân trang /page/N/")

    if mode == "pinetree":
        # Pinetree (WordPress) = static 2 TẦNG giống mbs: list /post/category/.../
        # (SSR) -> bài chi tiết /post/<YYYYMMDD>/<slug>/ -> PDF wp-content/uploads.
        # Phân trang path /page/N/.
        cfg["follow_detail_re"] = r"/post/\d{8}/[a-z0-9\-]+/?$"
        if "{page}" not in cfg["base_url"]:
            cfg["base_url"] = cfg["base_url"].rstrip("/") + "/page/{page}/"
        print("  [chế độ pinetree] 2 tầng: list -> bài /post/<ngày>/<slug>/, "
              "phân trang /page/N/")

    if mode == "bvsc":
        # BVSC = static 2 TẦNG: TOÀN BỘ báo cáo nằm trong 1 trang list (mỗi cái
        # là div.news__nhadautu--detail ẩn theo quý) -> link bài chi tiết
        # /danhsachbaiviet/<slug>/ -> PDF trên /media/...pdf. List không phân
        # trang; ?page=N bị site bỏ qua -> trang 2 lặp lại -> 0 bài mới ->
        # auto-stop. Đặt page_end=1 cho gọn nếu người dùng không yêu cầu khác.
        cfg["follow_detail_re"] = r"/danhsachbaiviet/[a-z0-9\-]+/?$"
        if cfg["page_end"] is None and cfg["page_start"] == 1:
            cfg["page_end"] = 1
        print("  [chế độ bvsc] 2 tầng: list (1 trang) -> bài "
              "/danhsachbaiviet/<slug>/")

    print("=" * 70)
    print("PDF DETECTOR")
    print(f"  URL gốc   : {cfg['base_url']}")
    print(f"  Trang     : {cfg['page_start']} -> "
          f"{cfg['page_end'] if cfg['page_end'] else 'tự dừng'}")
    print(f"  Include   : {cfg['include_keywords'] or '(tất cả)'} "
          f"[{cfg['include_mode']}]")
    print(f"  Exclude   : {cfg['exclude_keywords'] or '(không)'}")
    print(f"  Lưu vào   : {cfg['out_dir']}")
    print("=" * 70)

    seen_files = set()      # tránh tải trùng giữa các trang
    seen_details = set()    # (site 2 tầng) trang chi tiết đã ghé
    total_found = 0
    total_match = 0
    total_dl = 0
    failures = []           # các file khớp tiêu chí nhưng tải KHÔNG thành công
    page = cfg["page_start"]
    empty_streak = 0

    while True:
        if cfg["page_end"] is not None and page > cfg["page_end"]:
            break

        url = build_page_url(cfg["base_url"], cfg["page_param"], page)
        print(f"\n--- Trang {page}: {url}")

        # Tải trang với thử lại 2 lần; lỗi 1 trang KHÔNG giết cả crawl.
        resp = None
        for attempt in range(3):
            try:
                resp = http_get(session, url, headers=HEADERS, timeout=30)
                resp.raise_for_status()
                resp.encoding = resp.apparent_encoding or "utf-8"
                break
            except Exception as e:
                print(f"  [LỖI tải trang lần {attempt+1}] {e}")
                resp = None
                time.sleep(cfg["delay"] + attempt)
        if resp is None:
            # Bỏ qua trang lỗi này, vẫn đi tiếp (trừ khi đang auto-dừng).
            if cfg["page_end"] is None:
                empty_streak += 1
                if empty_streak >= 2:
                    print("  -> 2 trang liên tiếp không lấy được. Dừng.")
                    break
            page += 1
            continue

        pdfs = find_pdfs_on_page(resp.text, url, cfg.get("extra_pdf_patterns"))

        # Site 2 TẦNG: ghé từng trang chi tiết để lấy PDF thật bên trong.
        if cfg.get("follow_detail_re"):
            details = find_detail_links(resp.text, url, cfg["follow_detail_re"])
            new_details = [d for d in details if d["url"] not in seen_details]
            print(f"  ({len(new_details)} trang chi tiết mới)")
            for d in new_details:
                seen_details.add(d["url"])
                try:
                    dr = http_get(session, d["url"], headers=HEADERS, timeout=30)
                    dr.raise_for_status()
                    dr.encoding = dr.apparent_encoding or "utf-8"
                except Exception as e:
                    print(f"  [LỖI trang chi tiết] {d['url']} -> {e}")
                    continue
                dpdfs = find_pdfs_on_page(dr.text, d["url"],
                                          cfg.get("extra_pdf_patterns"))
                # Tiêu đề: ưu tiên text của link list; nếu là nút chung chung
                # ("Xem báo cáo", "Tải PDF"...) hoặc quá ngắn -> lấy từ SLUG URL
                # bài chi tiết (vd .../pinetree-bao-cao-tai-chinh-quy-1-nam-2026/).
                _generic = {"xem bao cao", "xem", "tai pdf", "tai ve", "tai xuong",
                            "download", "chi tiet", "xem chi tiet", "pdf", "doc"}
                title = (d["text"] or "").strip()
                if len(title) < 8 or strip_accents(title) in _generic:
                    slug = urlparse(d["url"]).path.rstrip("/").split("/")[-1]
                    slug = re.sub(r"^pinetree[\-_ ]*", "", slug, flags=re.I)
                    title = slug.replace("-", " ").replace("_", " ").strip() or title
                for dp in dpdfs:
                    # nhãn lọc = tiêu đề (giàu từ khoá) + tên file gốc
                    base = _clean_label_name(os.path.basename(
                        urlparse(dp["url"]).path))
                    dp["text"] = f"{title} {dp['text']}".strip()
                    # tên lưu: tiêu đề + tên file gốc -> DUY NHẤT (tránh trùng khi
                    # nhiều báo cáo cùng có "Cong-bo-thong-tin.pdf" / "Xem báo cáo").
                    if not dp.get("dest") and title and len(title) >= 6:
                        bare = re.sub(r"\.pdf$", "", base, flags=re.I)
                        dp["dest"] = safe_filename(f"{title} - {bare}") + ".pdf"
                    pdfs.append(dp)
                time.sleep(cfg["delay"])

        # Chỉ tính PDF chưa gặp ở trang trước (phát hiện hết phân trang)
        new_pdfs = [p for p in pdfs if p["url"] not in seen_files]

        if not new_pdfs:
            empty_streak += 1
            print(f"  (không có PDF mới)")
            # Auto-dừng: cần 2 trang liên tiếp không có PDF mới mới chắc là hết.
            if cfg["page_end"] is None and empty_streak >= 2:
                print("  -> Hết trang. Dừng.")
                break
            page += 1
            time.sleep(cfg["delay"])
            continue

        empty_streak = 0
        for p in new_pdfs:
            seen_files.add(p["url"])
            total_found += 1
            if match_criteria(p["text"], p["url"], cfg):
                total_match += 1
                status = download(p["url"], p["text"], cfg["out_dir"],
                                  session, cfg["overwrite"],
                                  dest_name=p.get("dest"),
                                  ticker=cfg.get("rename_ticker"))
                if "[TẢI]" in status:
                    total_dl += 1
                elif "[LỖI]" in status or "cảnh báo" in status:
                    failures.append((p["url"], status.strip()))
                print(f"  • {p['text'][:60]}")
                print(status)
                time.sleep(cfg["delay"])
            else:
                print(f"  - (bỏ, không khớp) {p['text'][:60]}")

        page += 1
        time.sleep(cfg["delay"])

    print("\n" + "=" * 70)
    print(f"XONG. Tìm thấy {total_found} PDF | khớp tiêu chí {total_match} | "
          f"tải thành công {total_dl} file.")
    skipped_existing = total_match - total_dl - len(failures)
    if skipped_existing > 0:
        print(f"  ({skipped_existing} file đã có sẵn -> bỏ qua. Dùng --overwrite để tải lại.)")
    if failures:
        print(f"\n  !! {len(failures)} FILE TẢI LỖI (không có trên đĩa):")
        for u, st in failures:
            print(f"     - {u}")
            print(f"       {st}")
    print(f"\nThư mục: {cfg['out_dir']}")
    print("=" * 70)


# ============================================================================
# Đổi tên TẠI CHỖ các PDF đã tải sẵn trong 1 thư mục (không tải lại)
# ============================================================================
def rename_existing_dir(folder: str, ticker: str, overwrite: bool = False):
    """Đổi tên các file .pdf đã có trong <folder> sang dạng thống nhất.
    Phân loại/kỳ suy từ chính TÊN FILE hiện tại. File không phân loại được ->
    giữ nguyên (không đổi). Trùng đích -> thêm (2),(3)..."""
    ticker = ticker.upper()
    print("=" * 70)
    print(f"ĐỔI TÊN TẠI CHỖ  |  thư mục: {folder}  |  ticker: {ticker}")
    print("=" * 70)
    if not os.path.isdir(folder):
        print(f"  [LỖI] không thấy thư mục: {folder}")
        return
    files = sorted(f for f in os.listdir(folder) if f.lower().endswith(".pdf"))
    done = skip = 0
    for fn in files:
        # đã đúng chuẩn rồi -> KHÔNG đụng (tránh strip mất hậu tố HN/RIENG/EN khi
        # chạy lại, vì "HN" trong tên không khớp regex "hợp nhất").
        if re.match(r"^(BCTC|BCTLATTC|CBTT|GiaiTrinh) - ", fn):
            skip += 1
            continue
        stem = _unquote(re.sub(r"\.pdf$", "", fn, flags=re.IGNORECASE))
        new = unified_filename(stem, fn, ticker)
        if not new:
            # tên file vô dụng (vd uuid) -> đọc NỘI DUNG trang 1 phân loại lại.
            new = unified_filename(_pdf_first_text(os.path.join(folder, fn)),
                                   fn, ticker)
        if not new:
            print(f"  - (giữ nguyên, không phân loại được) {fn[:60]}")
            skip += 1
            continue
        target = safe_filename(new) + ".pdf"
        if target == fn:
            skip += 1
            continue
        # tránh đè file khác: nếu đích đã tồn tại (khác nguồn) -> thêm (n)
        dst = os.path.join(folder, target)
        if os.path.exists(dst) and os.path.abspath(dst) != os.path.join(folder, fn):
            if overwrite:
                os.remove(dst)
            else:
                i = 2
                base = safe_filename(new)
                while os.path.exists(os.path.join(folder, f"{base} ({i}).pdf")):
                    i += 1
                target = f"{base} ({i}).pdf"
                dst = os.path.join(folder, target)
        os.rename(os.path.join(folder, fn), dst)
        print(f"  [ĐỔI] {fn[:50]}\n     -> {target}")
        done += 1
    print("\n" + "=" * 70)
    print(f"XONG. Đổi tên {done} file | giữ nguyên {skip} file.")
    print("=" * 70)


# ============================================================================
# Hỏi tiêu chí qua bàn phím (khi không truyền --include)
# ============================================================================
def interactive_setup(cfg: dict):
    print("\n>> Thiết lập tiêu chí (Enter để bỏ qua / giữ mặc định)\n")

    u = input(f"URL gốc [{cfg['base_url']}]: ").strip()
    if u:
        # Nếu người dùng dán URL có sẵn ?page=, giữ nguyên (tool tự ghi đè page).
        cfg["base_url"] = u

    inc = input("Từ khoá CHỌN (cách nhau dấu phẩy, vd: hợp nhất, công ty mẹ): ").strip()
    if inc:
        cfg["include_keywords"] = [x.strip() for x in inc.split(",") if x.strip()]
        m = input("  Khớp [1] BẤT KỲ từ khoá  /  [2] TẤT CẢ  (mặc định 1): ").strip()
        cfg["include_mode"] = "all" if m == "2" else "any"

    exc = input("Từ khoá LOẠI BỎ (cách nhau dấu phẩy, vd: soát xét, tiếng anh): ").strip()
    if exc:
        cfg["exclude_keywords"] = [x.strip() for x in exc.split(",") if x.strip()]

    pr = input("Khoảng trang (vd 1-14, hoặc Enter để tự dừng): ").strip()
    if pr:
        if "-" in pr:
            a, b = pr.split("-", 1)
            cfg["page_start"] = int(a)
            cfg["page_end"] = int(b)
        else:
            cfg["page_start"] = 1
            cfg["page_end"] = int(pr)

    # (Đổi tên file BẬT MẶC ĐỊNH + ticker tự detect theo host -> không hỏi nữa.)
    return cfg


def parse_args(cfg: dict):
    ap = argparse.ArgumentParser(description="Detect & download PDFs across paginated pages.")
    ap.add_argument("--url", help="URL gốc (không cần ?page=). Nếu site phân "
                    "trang kiểu path, nhét {page} vào URL vd .../page-{page}/")
    ap.add_argument("--include", help="Từ khoá chọn, cách nhau dấu phẩy")
    ap.add_argument("--include-mode", choices=["any", "all"], help="any/all")
    ap.add_argument("--exclude", help="Từ khoá loại bỏ, cách nhau dấu phẩy")
    ap.add_argument("--pages", help="Khoảng trang vd 1-14 (mặc định tự dừng)")
    ap.add_argument("--page-param", help='Tên tham số phân trang (mặc định "page")')
    ap.add_argument("--mode", choices=["static", "masvn", "kafi", "shs", "vdsc", "mbs", "bsc", "pinetree", "bvsc", "gel"], help="Ép chế độ (mặc định tự nhận diện)")
    ap.add_argument("--out", help="Thư mục lưu")
    ap.add_argument("--overwrite", action="store_true", help="Ghi đè file đã có")
    ap.add_argument("--ticker", help="Mã CK để đổi tên file thống nhất "
                    '("BCTC - SSI - Q1.2026"). Không truyền thì tự tra theo host.')
    ap.add_argument("--no-rename", action="store_true", help="TẮT đổi tên thống "
                    "nhất (mặc định BẬT, ticker tự detect theo host)")
    ap.add_argument("--no-subfolder", action="store_true", help="KHÔNG gom vào "
                    "thư mục con theo ticker (mặc định BẬT: downloads/<TICKER>/)")
    ap.add_argument("--rename-dir", help="Đổi tên TẠI CHỖ các PDF đã tải trong "
                    "thư mục này (cần --ticker). Không tải gì thêm.")
    args = ap.parse_args()

    # Chế độ tiện ích: đổi tên file đã có rồi thoát.
    if args.rename_dir:
        if not args.ticker:
            print("  [LỖI] --rename-dir cần kèm --ticker <MÃ CK>.")
            sys.exit(1)
        rename_existing_dir(args.rename_dir, args.ticker, bool(args.overwrite))
        sys.exit(0)

    used = False
    if args.url:
        cfg["base_url"] = args.url; used = True
    if args.include is not None:
        cfg["include_keywords"] = [x.strip() for x in args.include.split(",") if x.strip()]; used = True
    if args.include_mode:
        cfg["include_mode"] = args.include_mode
    if args.exclude is not None:
        cfg["exclude_keywords"] = [x.strip() for x in args.exclude.split(",") if x.strip()]; used = True
    if args.pages:
        if "-" in args.pages:
            a, b = args.pages.split("-", 1)
            cfg["page_start"], cfg["page_end"] = int(a), int(b)
        else:
            cfg["page_start"], cfg["page_end"] = 1, int(args.pages)
        used = True
    if args.page_param:
        cfg["page_param"] = args.page_param
    if args.mode:
        cfg["mode"] = args.mode
    if args.out:
        cfg["out_dir"] = args.out
    if args.overwrite:
        cfg["overwrite"] = True
    # ticker/no-rename là tuỳ chọn bổ trợ -> KHÔNG tính "used" (để chạy không URL
    # vẫn vào hỏi tương tác, đổi tên vẫn tự động).
    if args.ticker:
        cfg["ticker"] = args.ticker
    if args.no_rename:
        cfg["no_rename"] = True
    if args.no_subfolder:
        cfg["no_subfolder"] = True

    return cfg, used


if __name__ == "__main__":
    cfg = dict(CONFIG)
    cfg, used_cli = parse_args(cfg)
    # Nếu không truyền tham số dòng lệnh -> hỏi tương tác
    if not used_cli:
        cfg = interactive_setup(cfg)
    try:
        run(cfg)
    except KeyboardInterrupt:
        print("\n[Đã dừng bởi người dùng]")
