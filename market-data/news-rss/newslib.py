# -*- coding: utf-8 -*-
r"""newslib.py - thu vien chung cua news-rss (11/11/2026): chuan hoa van ban tieng Viet, doc RSS, bo phan loai tin theo nganh.

Phan loai = tu dien tu khoa (config\keywords.csv) + nhan dien ma CK (ma 3 ky tu viet hoa + ten ngan DN tu ICB Vietcap
index-fetcher\raw\vn_icb_vci.csv + config\alias_ma.csv) + goi y chuyen muc RSS (config\feeds.csv). Diem 1 nganh =
tong trong_so tu khoa (tieu de x2, tom tat x1) + ma CK (tieu de 4, tom tat 2) + goi y chuyen muc 1,5. Gan nganh khi diem >= NGUONG.
"""
from __future__ import annotations

import email.utils
import hashlib
import html
import os
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
HUB = os.path.dirname(ROOT)                                          # code: D:\market-data (cloud: <repo>/market-data)
CFG = os.path.join(ROOT, "config")
OUT = os.path.join(ROOT, "output")
# du lieu ICB nam o cay DU LIEU (MD_ROOT: laptop D:\pipeline-data\market-data / cloud /tmp/...), khong phai cay code
ICB_CSV = os.path.join(os.environ.get("MD_ROOT") or HUB, "index-fetcher", "raw", "vn_icb_vci.csv")
if not os.path.exists(ICB_CSV):
    ICB_CSV = os.path.join(HUB, "index-fetcher", "raw", "vn_icb_vci.csv")
VN_TZ = timezone(timedelta(hours=7))


def set_data_dir(d: str) -> None:
    """Thu muc kho tin. 11/11/2026: app keo RSS khi mo trang va giu kho trong CACHE cua app (APP_CACHE/news-rss);
    chay tay CLI mac dinh news-rss\\data (hoac env NEWS_DATA)."""
    global DATA, MASTER, TAGGED, TAGS, FEED_STATUS, STATE
    DATA = os.path.normpath(d)
    MASTER = os.path.join(DATA, "news_master.parquet")               # 1 dong = 1 bai (id = sha1 url)
    TAGGED = os.path.join(DATA, "news_tagged.parquet")               # master + cot phan loai (app doc)
    TAGS = os.path.join(DATA, "news_tags.parquet")                   # long: id x nganh (diem, chu de, tu khoa) -> loc/sap theo nganh
    FEED_STATUS = os.path.join(DATA, "feed_status.csv")
    STATE = os.path.join(DATA, "phan_loai_state.json")              # hash tu dien lan phan loai truoc


# kho mac dinh = cache cua app Market Data (app ghi khi mo trang; CLI / keyword_mining dung chung kho do)
set_data_dir(os.environ.get("NEWS_DATA") or os.path.join(os.environ.get("APP_CACHE") or os.path.join(HUB, "app", "cache"), "news-rss"))

NGUONG = 3.0             # diem toi thieu de gan 1 nganh
W_TIEU_DE, W_TOM_TAT = 2.0, 1.0
W_MA_TD, W_MA_TT = 4.0, 3.0           # ma CK o tieu de / tom tat (bai nhac >5 ma: x0,5)
W_GOI_Y = 1.5
VIN = ("VIC", "VHM", "VRE", "VPL")
KHAC = "Chưa phân loại"

# ------------------------------------------------------------------ chuan hoa van ban
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_TONE = "\u0300\u0301\u0303\u0309\u0323"                              # huyen sac nga hoi nang (NFD)
_OLD_NEW = re.compile(f"([oO])([{_TONE}])([aAeE])|([uU])([{_TONE}])([yY])")


def _dau_moi(m):
    return (m.group(1) + m.group(3) + m.group(2)) if m.group(1) else (m.group(4) + m.group(6) + m.group(5))


def norm(s) -> str:
    """NFC + bo the HTML + thong nhat kieu bo dau: 'hóa'/'hoá', 'thủy'/'thuỷ', 'Ủy'/'Uỷ' -> 1 dang (dau tren nguyen am sau).
    Ap dung GIONG NHAU cho van ban va tu khoa nen chi can nhat quan, khong can dung chinh ta."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return ""
    s = str(s)
    for _ in range(2):                                               # mot so bao ma hoa 2 lan (&amp;aacute;)
        s = html.unescape(s)
    s = _TAG.sub(" ", s)
    s = unicodedata.normalize("NFD", s)
    s = _OLD_NEW.sub(_dau_moi, s)
    s = unicodedata.normalize("NFC", s).replace("\u00a0", " ")
    return _WS.sub(" ", s).strip()


def canon_url(u: str) -> str:
    u = str(u or "").strip()
    u = re.sub(r"[?#].*$", "", u)
    return re.sub(r"^http://", "https://", u).rstrip("/")


def make_id(url: str) -> str:
    return hashlib.sha1(canon_url(url).encode("utf-8")).hexdigest()[:16]


def nhom_trung(title: str) -> str:
    """Khoa gom tin trung tieu de giua cac bao (cung 1 tin dang lai)."""
    t = re.sub(r"[^\w]+", " ", norm(title).lower()).strip()
    return hashlib.sha1(t[:90].encode("utf-8")).hexdigest()[:10]


# ------------------------------------------------------------------ doc RSS
_TZFIX = [(re.compile(r"GMT\+0?7(:?00)?$"), "+0700"), (re.compile(r"([+-]\d\d):(\d\d)$"), r"\1\2"),
          (re.compile(r"([+-]\d\d)$"), r"\g<1>00")]


def parse_date(s: str):
    """pubDate cac kieu: RFC822 (nam 2 hoac 4 so, GMT+7, +07:00, +07), '11/11/2026 9:12:00 AM' (Tuoi Tre, M/D/Y) -> gio VN naive."""
    s = (s or "").strip()
    if not s:
        return None
    x = s
    for rg, rep in _TZFIX:
        x = rg.sub(rep, x)
    try:
        d = email.utils.parsedate_to_datetime(x)
        if d.tzinfo is None:
            d = d.replace(tzinfo=VN_TZ)
        return d.astimezone(VN_TZ).replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        pass
    for f in ("%m/%d/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            d = datetime.strptime(s, f)
            if d.tzinfo is not None:
                d = d.astimezone(VN_TZ).replace(tzinfo=None)
            return d
        except ValueError:
            continue
    return None


def parse_rss(content: bytes) -> list[dict]:
    try:
        from lxml import etree
        root = etree.fromstring(content, etree.XMLParser(recover=True, huge_tree=True))
    except ImportError:                                               # du phong: thu vien chuan (XML hong -> bo feed)
        import xml.etree.ElementTree as etree
        try:
            root = etree.fromstring(content)
        except etree.ParseError:
            return []
    if root is None:
        return []
    out = []
    items = root.findall(".//item")
    if not items:                                                    # Atom
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for e in root.findall(".//a:entry", ns):
            link = e.find("a:link", ns)
            out.append({"tieu_de": e.findtext("a:title", "", ns), "url": link.get("href") if link is not None else "",
                        "tom_tat": e.findtext("a:summary", "", ns), "ngay": e.findtext("a:updated", "", ns)})
        return out
    for it in items:
        link = (it.findtext("link") or "").strip() or (it.findtext("guid") or "").strip()
        out.append({"tieu_de": it.findtext("title") or "", "url": link, "tom_tat": it.findtext("description") or "",
                    "ngay": it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date") or ""})
    return out


# ------------------------------------------------------------------ cau hinh
def read_cfg(name: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(CFG, name), dtype=str, comment="#", skipinitialspace=True).fillna("")


def cfg_hash() -> str:
    """Doi tu dien / alias / nganh / file ICB -> phan loai lai toan bo lich su."""
    h = hashlib.sha1()
    for f in sorted(os.listdir(CFG)):
        with open(os.path.join(CFG, f), "rb") as fh:
            h.update(f.encode() + fh.read())
    with open(__file__, "rb") as fh:
        h.update(fh.read())
    if os.path.exists(ICB_CSV):
        h.update(str(os.path.getsize(ICB_CSV)).encode())
    return h.hexdigest()[:12]


def danh_sach_nganh() -> pd.DataFrame:
    return read_cfg("nganh.csv")


# ten ngan DN tu ICB: bo tien to chung, chi giu ten du dac trung (tranh 'Xay dung', 'Dien luc' khop moi bai)
_PREFIX = re.compile(r"^(Tập đoàn|Tổng Công ty|Tổng công ty|TCT|Công ty|CTCP|Tập Đoàn)\s+", re.I)
_CHUNG = set(norm("""đầu tư phát triển xây dựng thương mại dịch vụ sản xuất công nghiệp việt nam vn cổ phần điện lực vận tải cảng
 hàng không xuất nhập khẩu kinh doanh nhà đô thị khu công nghệ kỹ thuật cơ khí điện nước môi trường cấp thoát hạ tầng giao thông
 tổng hợp thực phẩm nông nghiệp lâm thủy hải sản dược phẩm y tế vật tư thiết bị vật liệu khoáng sản bất động sản tài chính
 chứng khoán ngân hàng bảo hiểm quỹ du lịch khách sạn thép nhựa giấy in phát hành sách giáo dục thiết bị
 miền bắc nam trung tây đông quốc tế toàn cầu châu á thái bình dương sài gòn hà nội tp hcm và & - group holdings corp jsc""").lower().split())


def _alias_tu_ten(ten: str) -> str | None:
    t = _PREFIX.sub("", norm(ten)).strip(" -.")
    t = _PREFIX.sub("", t).strip(" -.")
    if len(t) < 4:
        return None
    toks = [w for w in re.split(r"[\s\-&.,()]+", t.lower()) if w]
    if not toks or all(w in _CHUNG or w.isdigit() for w in toks):
        return None
    if len(toks) == 1 and not re.search(r"[A-Z]{2,}|[a-z][A-Z]", t) and len(t) < 6:
        return None                                                  # 1 tu ngan thuong (de trung)
    return t


def load_ma() -> tuple[pd.DataFrame, dict, set]:
    """(bang ICB theo ma, alias->ma, tap ma can ngu canh)."""
    icb = pd.read_csv(ICB_CSV, dtype=str).drop_duplicates("code").set_index("code") if os.path.exists(ICB_CSV) else pd.DataFrame()
    icb = icb[icb.index.str.fullmatch(r"[A-Z][A-Z0-9]{2}", na=False)]
    if "icb4" in icb:
        icb = icb[icb["icb4"].fillna("") != "Quỹ đầu tư"]
    alias = {}
    for ma, r in icb.iterrows():
        a = _alias_tu_ten(r.get("ten", ""))
        if a:
            alias.setdefault(a, ma)
    am = read_cfg("alias_ma.csv")
    bo = set()
    for r in am.itertuples(index=False):
        ma, a, kieu = r.ma.strip().upper(), norm(r.alias), r.kieu.strip()
        if kieu == "bo_alias":
            bo.add(a)
        elif kieu == "alias" and a:
            alias[a] = ma
    for a in bo:
        alias.pop(a, None)
    mo_ho = {r.ma.strip().upper() for r in am.itertuples(index=False) if r.kieu.strip() == "can_ngu_canh"}
    return icb, alias, mo_ho


# ------------------------------------------------------------------ bo phan loai
class PhanLoai:
    def __init__(self):
        kw = read_cfg("keywords.csv")
        self.nganh = danh_sach_nganh()
        self.ten = dict(zip(self.nganh["ma"], self.nganh["nganh"]))           # ma nganh -> ten (= icb2 cua Vietcap)
        bad = sorted(set(kw["ma"]) - set(self.ten))
        if bad:
            raise ValueError(f"keywords.csv co ma nganh khong co trong nganh.csv: {bad}")
        self.kw_lo, self.kw_hoa = defaultdict(list), defaultdict(list)
        for r in kw.itertuples(index=False):
            k = norm(r.tu_khoa)
            if not k:
                continue
            w = float(r.trong_so or 1)
            if str(r.hoa).strip() == "1":
                self.kw_hoa[k].append((self.ten[r.ma], r.chu_de, w))
            else:
                self.kw_lo[k.lower()].append((self.ten[r.ma], r.chu_de, w))
        lt = read_cfg("loai_tin.csv")
        self.lt_lo, self.lt_hoa = defaultdict(list), defaultdict(list)
        for r in lt.itertuples(index=False):
            k = norm(r.tu_khoa)
            (self.lt_hoa[k] if str(r.hoa).strip() == "1" else self.lt_lo[k.lower()]).append((r.loai_tin, float(r.trong_so or 1)))
        self.re_lo = self._rx(self.kw_lo)
        self.re_hoa = self._rx(self.kw_hoa)
        self.re_lt_lo = self._rx(self.lt_lo)
        self.re_lt_hoa = self._rx(self.lt_hoa)
        self.icb, self.alias, self.mo_ho = load_ma()
        self.ma_set = set(self.icb.index)
        self.ma_nganh = self.icb["icb2"].to_dict() if "icb2" in self.icb else {}
        lech = sorted({v for v in self.ma_nganh.values() if isinstance(v, str)} - set(self.ten.values()))
        if lech:
            print(f"! icb2 trong vn_icb_vci.csv khong co trong nganh.csv (ma CK nganh nay khong duoc gan): {lech}")
        self.re_alias = self._rx(self.alias)
        self.re_ma = re.compile(r"(?<![\w\-./&])([A-Z][A-Z0-9]{2})(?![\w\-&])")
        self.re_ctx = re.compile(r"(mã|cổ phiếu|cp|HOSE|HNX|UPCoM|UPCOM|HSX)[\s:]*$", re.I)

    @staticmethod
    def _rx(d):
        if not d:
            return None
        alt = "|".join(re.escape(k) for k in sorted(d, key=len, reverse=True))
        return re.compile(rf"(?<!\w)({alt})(?!\w)")

    def _ma_trong(self, s: str) -> set:
        out = set()
        for m in self.re_ma.finditer(s):
            c = m.group(1)
            if c not in self.ma_set:
                continue
            if c in self.mo_ho:                                      # (CPI), (FDI) la dinh nghia viet tat -> chi nhan 'ma CEO', 'HNX: CEO'
                if not self.re_ctx.search(s[max(0, m.start() - 14):m.start()]):
                    continue
            out.add(c)
        if self.re_alias is not None:
            for m in self.re_alias.finditer(s):
                out.add(self.alias[m.group(1)])
        return out

    def phan_loai(self, tieu_de: str, tom_tat: str, goi_y: str = "") -> dict:
        td, tt = norm(tieu_de), norm(tom_tat)
        if tt.startswith(td) and td:
            tt = tt[len(td):]
        diem = defaultdict(float)
        chu_de = defaultdict(set)
        tukhoa = defaultdict(list)
        for txt, w in ((td, W_TIEU_DE), (tt, W_TOM_TAT)):
            seen = set()
            for rg, d, lower in ((self.re_lo, self.kw_lo, True), (self.re_hoa, self.kw_hoa, False)):
                if rg is None:
                    continue
                for m in rg.finditer(txt.lower() if lower else txt):
                    k = m.group(1)
                    if k in seen:
                        continue
                    seen.add(k)
                    for ng, cd, ws in d[k]:
                        diem[ng] += ws * w
                        if cd:
                            chu_de[ng].add(cd)
                        tukhoa[ng].append(k)
        ma_td, ma_tt = self._ma_trong(td), self._ma_trong(tt)
        ma_tt -= ma_td
        nhieu = len(ma_td | ma_tt) > 5                                 # bai liet ke nhieu ma (diem tin, top CP) -> giam trong so ma
        for ds, w in ((ma_td, W_MA_TD), (ma_tt, W_MA_TT)):
            for c in ds:
                ng = "Vingroup" if c in VIN else self.ma_nganh.get(c)
                if not ng or (isinstance(ng, float)):
                    continue
                diem[ng] += w * (0.5 if nhieu else 1)
                tukhoa[ng].append(c)
                if c in VIN:                                         # Vingroup: cong ca nganh ICB2 cua ma (VHM -> BDS)
                    ng2 = self.ma_nganh.get(c)
                    if isinstance(ng2, str):
                        diem[ng2] += w * 0.75 * (0.5 if nhieu else 1)
                        tukhoa[ng2].append(c)
        for g in {x for x in str(goi_y).split("|") if x in self.ten}:   # goi y chuyen muc RSS (ma nganh)
            diem[self.ten[g]] += W_GOI_Y
        nganh = {ng: round(v, 2) for ng, v in diem.items() if v >= NGUONG}
        loai, d_lt = [], 0.0
        for txt, w in ((td, W_TIEU_DE), (tt, W_TOM_TAT)):
            for rg, d, lower in ((self.re_lt_lo, self.lt_lo, True), (self.re_lt_hoa, self.lt_hoa, False)):
                if rg is None:
                    continue
                for m in rg.finditer(txt.lower() if lower else txt):
                    for lt, ws in d[m.group(1)]:
                        if lt not in loai:
                            loai.append(lt)
                            d_lt += ws * w
        return {"nganh": nganh, "chu_de": {k: sorted(v) for k, v in chu_de.items() if k in nganh},
                "tu_khoa": {k: list(dict.fromkeys(v)) for k, v in tukhoa.items() if k in nganh},
                "ma": sorted(ma_td) + sorted(ma_tt), "loai_tin": loai, "diem_su_kien": d_lt}
