# -*- coding: utf-8 -*-
"""Keo du lieu tien te tu cong thong tin NHNN (sbv.gov.vn).

4 trang deu la HTML render san (khong can JS), NHUNG dung WAF Incapsula:
- chan User-Agent kieu curl/python tran -> phai gia lap header Chrome day du (common.py)
- khi bi chan van tra ve HTTP 200 kem trang "Request Rejected" ~246 byte
- goi qua nhanh/nhieu se bi chan tam thoi -> co delay giua cac trang + retry backoff

CAC TRANG CHI CONG BO SO CUA NGAY HIEN TAI (khong co lich su) -> pipeline chay
hang ngay de boi dan chuoi thoi gian vao transmission-master.csv.
"""
from __future__ import annotations

import re
import time

from bs4 import BeautifulSoup

from common import get, log, new_session, row, vn_date, vn_number

BASE = "https://sbv.gov.vn"
URL_RATES = BASE + "/l%C3%A3i-su%E1%BA%A5t1"                                    # /lai-suat1
URL_FX = BASE + "/t%E1%BB%B7-gi%C3%A1"                                          # /ty-gia
URL_OMO = BASE + "/vi/nghi%E1%BB%87p-v%E1%BB%A5-th%E1%BB%8B-tr%C6%B0%E1%BB%9Dng-m%E1%BB%9F"
URL_BILL = BASE + "/vi/thong-tin-chao-ban-tin-phieu-nhnn"

N_POLICY = ("N03", "Noi rang buoc va nguon")
N_FX = ("N04", "Ty gia USD/VND")
N_OMO = ("N05", "NHNN hut bom")
N_FWD = ("N06", "NHNN ban forward")
N_IB = ("N08", "Lai suat TT2")
N_IBVOL = ("N09", "Nguon TT2")

# nhan ky han tren bang lai suat lien ngan hang -> hau to series_id
TENORS = {
    "qua dem": "on", "1 tuan": "1w", "2 tuan": "2w", "1 thang": "1m",
    "3 thang": "3m", "6 thang": "6m", "9 thang": "9m", "12 thang": "12m",
}
# NHNN dang doanh so DU CA 7 ky han -> lay het, khoi phai backfill tu FiinProX
IB_VOL_KEEP = set(TENORS.values())

_ACCENTS = (
    ("àáảãạăằắẳẵặâầấẩẫậ", "a"),
    ("èéẻẽẹêềếểễệ", "e"),
    ("ìíỉĩị", "i"),
    ("òóỏõọôồốổỗộơờớởỡợ", "o"),
    ("ùúủũụưừứửữự", "u"),
    ("ỳýỷỹỵ", "y"),
    ("đ", "d"),
)


def _norm(s: str) -> str:
    """Bo dau tieng Viet + ha chu thuong de so khop nhan."""
    s = (s or "").lower().strip()
    for src, dst in _ACCENTS:
        for ch in src:
            s = s.replace(ch, dst)
    return re.sub(r"\s+", " ", s)


def _tables(html: str):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for t in soup.find_all("table"):
        rows = []
        for tr in t.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if rows:
            out.append(rows)
    return out, soup.get_text("\n", strip=True)


# ---------------------------------------------------------------- lai suat
def fetch_rates(session) -> list:
    """Trang Lai suat: lai suat dieu hanh + lai suat BQ lien ngan hang + doanh so."""
    html = get(session, URL_RATES, referer=BASE + "/", wait=15)
    if not html:
        return []
    tables, text = _tables(html)
    out = []

    # ngay ap dung cua bang lien ngan hang: "Ngay ap dung: 04/09/2026"
    ntext = _norm(text)
    m = re.search(r"ngay ap dung[:\s]*(\d{1,2}/\d{1,2}/\d{4})", ntext)
    date = vn_date(m.group(1)) if m else None
    if not date:
        log("  ! Khong doc duoc 'Ngay ap dung' tren trang lai suat -> bo qua")
        return []

    for rows in tables:
        for cells in rows:
            if len(cells) < 2:
                continue
            label = _norm(cells[0])

            # 1) lai suat dieu hanh
            if "tai chiet khau" in label:
                v = vn_number(cells[1])
                if v is not None:
                    out.append(row(date, "policy_rediscount", v,
                                   series_name="Lai suat tai chiet khau",
                                   unit="%/nam", freq="D", source="SBV",
                                   node_id=N_POLICY[0], node_name=N_POLICY[1]))
                continue
            if "tai cap von" in label:
                v = vn_number(cells[1])
                if v is not None:
                    out.append(row(date, "policy_refinance", v,
                                   series_name="Lai suat tai cap von",
                                   unit="%/nam", freq="D", source="SBV",
                                   node_id=N_POLICY[0], node_name=N_POLICY[1]))
                continue

            # 2) bang lien ngan hang: [ky han, lai suat BQ, doanh so]
            key = TENORS.get(label)
            if not key or len(cells) < 3:
                continue
            rate = vn_number(cells[1])
            vol = vn_number(cells[2])
            if rate is not None:
                out.append(row(date, "ib_" + key, rate,
                               series_name="LNH binh quan " + cells[0],
                               unit="%/nam", freq="D", source="SBV",
                               node_id=N_IB[0], node_name=N_IB[1]))
            if vol is not None and key in IB_VOL_KEEP:
                out.append(row(date, "ib_vol_" + key, vol,
                               series_name="Doanh so LNH " + cells[0],
                               unit="ty VND", freq="D", source="SBV",
                               node_id=N_IBVOL[0], node_name=N_IBVOL[1]))
    log("  lai suat / lien ngan hang %s: %d chi tieu" % (date, len(out)))
    return out


# ------------------------------------------------------------------ ty gia
def fetch_fx(session) -> list:
    """Trang Ty gia: ty gia trung tam + gia mua/ban tham chieu cua So GD NHNN."""
    html = get(session, URL_FX, referer=BASE + "/", wait=15)
    if not html:
        return []
    tables, text = _tables(html)
    out = []

    ntext = _norm(text)
    m = re.search(r"ap dung cho ngay\s*(\d{1,2}/\d{1,2}/\d{4})", ntext)
    date = vn_date(m.group(1)) if m else None
    if not date:
        log("  ! Khong doc duoc ngay ap dung tren trang ty gia -> bo qua")
        return []

    for rows in tables:
        for cells in rows:
            if not cells:
                continue
            label = _norm(cells[0])

            # "1 Do la My =" | "25.603 VND"
            if "do la my" in label and "=" in cells[0] and len(cells) >= 2:
                v = vn_number(cells[1].replace("VND", ""))
                if v:
                    out.append(row(date, "fx_central", v, series_name="Ty gia trung tam",
                                   unit="VND/USD", freq="D", source="SBV",
                                   node_id=N_FX[0], node_name=N_FX[1]))

            # bang tham chieu Cuc QLNH: [STT, USD, Do la My, Mua, Ban]
            if len(cells) >= 5 and _norm(cells[1]) == "usd":
                buy, sell = vn_number(cells[3]), vn_number(cells[4])
                if buy:
                    out.append(row(date, "fx_sbv_buy_ref", buy,
                                   series_name="Gia mua USD tham chieu So GD NHNN",
                                   unit="VND/USD", freq="D", source="SBV",
                                   node_id=N_FWD[0], node_name=N_FWD[1]))
                if sell:
                    out.append(row(date, "fx_sbv_sell_ref", sell,
                                   series_name="Gia ban USD tham chieu So GD NHNN",
                                   unit="VND/USD", freq="D", source="SBV",
                                   node_id=N_FWD[0], node_name=N_FWD[1]))
    log("  ty gia %s: %d chi tieu" % (date, len(out)))
    return out


# --------------------------------------------------------------------- OMO
def fetch_omo(session) -> list:
    """Trang Nghiep vu thi truong mo: ket qua dau thau trong ngay."""
    html = get(session, URL_OMO, referer=BASE + "/", wait=15)
    if not html:
        return []
    tables, text = _tables(html)
    out = []

    ntext = _norm(text)
    m = re.search(r"ngay\s*(\d{1,2})\s*thang\s*(\d{1,2})\s*nam\s*(\d{4})", ntext)
    date = vn_date("%s/%s/%s" % m.groups()) if m else vn_date(ntext)
    if not date:
        log("  ! Khong doc duoc ngay tren trang OMO -> bo qua")
        return []

    side = "mua"          # "mua ky han" = bom tien ; "ban" / "tin phieu" = hut tien
    for rows in tables:
        for cells in rows:
            if not cells:
                continue
            label = _norm(cells[0])
            if label.startswith("mua"):
                side = "mua"
            elif label.startswith("ban") or "tin phieu" in label:
                side = "ban"

            if label.startswith("tong cong"):
                v = vn_number(cells[-2] if len(cells) >= 3 else cells[-1])
                if v is not None and side == "mua":
                    out.append(row(date, "omo_win_total", v,
                                   series_name="Khoi luong trung thau OMO",
                                   unit="ty VND", freq="D", source="SBV",
                                   node_id=N_OMO[0], node_name=N_OMO[1]))
                continue

            km = re.search(r"ky han\s*(\d+)\s*ngay", label)
            if not km or len(cells) < 4:
                continue
            days = km.group(1)
            vol, rate = vn_number(cells[2]), vn_number(cells[3])
            pre = "omo_win" if side == "mua" else "bill_win"
            kind = "OMO mua" if side == "mua" else "Tin phieu ban"
            if vol is not None:
                out.append(row(date, "%s_%sd_vol" % (pre, days), vol,
                               series_name="%s ky han %s ngay" % (kind, days),
                               unit="ty VND", freq="D", source="SBV",
                               node_id=N_OMO[0], node_name=N_OMO[1]))
            if rate:
                out.append(row(date, "%s_%sd_rate" % (pre, days), rate,
                               series_name="Lai suat trung thau ky han %s ngay" % days,
                               unit="%/nam", freq="D", source="SBV",
                               node_id=N_OMO[0], node_name=N_OMO[1]))
    log("  OMO %s: %d chi tieu" % (date, len(out)))
    return out


# --------------------------------------------------------------- tin phieu
def fetch_bill(session) -> list:
    """Trang chao ban tin phieu NHNN (chi co so lieu khi NHNN mo dot hut tien)."""
    html = get(session, URL_BILL, referer=BASE + "/", tries=2, wait=15)
    if not html:
        return []
    tables, _ = _tables(html)
    date = None
    vol = None
    for rows in tables:
        for cells in rows:
            if len(cells) < 2:
                continue
            label = _norm(cells[0])
            if "ngay dau thau" in label:
                date = vn_date(cells[1])
            if "khoi luong tin phieu" in label:
                vol = vn_number(cells[1])
    if not date or not vol:
        log("  tin phieu: khong co dot chao ban kem so lieu (binh thuong)")
        return []
    ty = vol / 1e9 if vol > 1e6 else vol      # trang ghi theo VND menh gia
    log("  tin phieu %s: %s ty VND" % (date, format(ty, ",.0f")))
    return [row(date, "bill_issue_vol", ty, series_name="Tin phieu NHNN phat hanh",
                unit="ty VND", freq="D", source="SBV",
                node_id=N_OMO[0], node_name=N_OMO[1])]


# ------------------------------------------------- thong ke he thong TCTD
URL_BANKSTAT = BASE + "/vi/thong-ke-mot-so-chi-tieu-co-ban"

N_ROOM = ("N10", "Room va chi phi von NH")

# nhan dong -> hau to series_id (chi lay 3 nhom can cho so do)
BANK_GROUPS = {"toan he thong": "system", "nhtm nha nuoc": "soe", "nhtm co phan": "jsc"}


def fetch_bank_stats(session) -> list:
    """Bang "Thong ke mot so chi tieu co ban" - LDR va ty le von ngan han cho vay
    trung dai han (SFL) toan he thong, cap nhat theo quy.

    Cot: [Loai hinh TCTD, Tong tai san, %tang, Von dieu le, %tang, SFL, LDR]
    """
    html = get(session, URL_BANKSTAT, referer=BASE + "/", wait=15)
    if not html:
        return []
    tables, text = _tables(html)
    ntext = _norm(text)
    m = re.search(r"den thoi diem\s*(\d{1,2}/\d{1,2}/\d{4})", ntext)
    date = vn_date(m.group(1)) if m else None
    if not date:
        log("  ! khong doc duoc moc thoi gian tren trang thong ke TCTD -> bo qua")
        return []

    out = []
    for rows in tables:
        for cells in rows:
            if len(cells) < 7:
                continue
            key = BANK_GROUPS.get(_norm(cells[0]))
            if not key:
                continue
            sfl, ldr = vn_number(cells[5]), vn_number(cells[6])
            if ldr:
                out.append(row(date, "ldr_system" if key == "system" else "ldr_" + key, ldr,
                               series_name="LDR " + cells[0], unit="%", freq="Q", source="SBV",
                               node_id=N_ROOM[0], node_name=N_ROOM[1]))
            if sfl and key == "system":
                out.append(row(date, "sfl_system", sfl,
                               series_name="Ty le von ngan han cho vay trung dai han",
                               unit="%", freq="Q", source="SBV",
                               node_id=N_POLICY[0], node_name=N_POLICY[1]))
            if key == "system":
                for idx, sid, name in ((1, "bank_total_assets", "Tong tai san he thong TCTD"),
                                       (3, "bank_charter_capital", "Von dieu le he thong TCTD")):
                    v = vn_number(cells[idx])
                    if v:
                        out.append(row(date, sid, v, series_name=name, unit="ty VND",
                                       freq="Q", source="SBV",
                                       node_id=N_ROOM[0], node_name=N_ROOM[1]))
    log("  thong ke TCTD %s: %d chi tieu" % (date, len(out)))
    return out


def fetch_all(_session=None) -> list:
    """MOI TRANG MOT SESSION MOI.

    WAF cua SBV gioi han so request tren mot phien: 4 trang dau qua duoc, den trang
    thu 5 (thong ke TCTD) thi bi chan du da gian 10s va retry 15/30/45s - nhung goi
    lai bang session moi thi thanh cong ngay. Vi vay khong dung chung session.
    """
    out = []
    for fn in (fetch_rates, fetch_fx, fetch_omo, fetch_bill, fetch_bank_stats):
        try:
            out += fn(new_session("browser"))
        except Exception as e:                                    # noqa: BLE001
            log("  X loi %s: %s" % (fn.__name__, e))
        time.sleep(8)
    return out
