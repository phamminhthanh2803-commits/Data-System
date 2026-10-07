# -*- coding: utf-8 -*-
"""dulieukinhte.com - 96 bang so lieu vi mo VN, mien phi, HTML render san.

Moi trang la 1 bang WIDE: dong = chi tieu, cot = ky (8 ky gan nhat hien tren HTML).
Chay hang ngay thi 8 cot la du de va moi khoang trong.

*** KIEM TRA NGAY BAT BUOC ***
Mot so bang cua site nay dat NHAM nhan ngay cho cot: gia tri dung nhung nhan la ngay
cong bo chu khong phai ngay quan sat. Vi du bang "Lai suat dieu hanh + lien ngan hang"
(slug 391) gan nhan 08-09-2026 cho so thuc te cua 28-08-2026 (lech 11 ngay) - doi chieu
voi NHNN va FiinProX thi day du 7 ky han deu khop nhung LECH NGAY.
May man la JSON-LD trong trang co truong `temporalCoverage` ghi DUNG moc cuoi that su.
=> `_check_dates()` so cot moi nhat voi temporalCoverage; lech thi BO QUA ca bang.
Nho guard nay ma bang 391 (lien ngan hang) va 417 (duong cong loi suat TPCP) bi loai
tu dong thay vi lam hong chuoi thoi gian.
"""
from __future__ import annotations

import calendar
import datetime as dt
import re
import time

from bs4 import BeautifulSoup

from common import get, log, row, vn_number

BASE = "https://dulieukinhte.com/du-lieu/"

# slug -> danh sach (regex nhan dong, series_id, ten, don vi, tan suat, node_id, node_name[, he so])
# He so dung khi quy uoc dau khac nhau: FiinProX ghi tin phieu luu hanh la SO AM, trang nay
# ghi so duong -> phai nhan -1 cho dong bo, neu khong cung mot series se co 2 quy uoc dau.
TABLES = {
    "sbv-bomhut-tien-334": [
        (r"^tong omo dang luu hanh", "omo_outstanding",
         "Reverse repo dang luu hanh (bom)", "ty VND", "D", "N05", "NHNN hut bom"),
        (r"^tong tin phieu dang luu hanh", "bill_outstanding",
         "Tin phieu NHNN luu hanh (am = hut)", "ty VND", "D", "N05", "NHNN hut bom", -1),
        (r"^tong trung thau . mua", "omo_win_total",
         "Khoi luong trung thau OMO", "ty VND", "D", "N05", "NHNN hut bom"),
        (r"^tong dao han \(mua\)", "omo_maturity_total",
         "Khoi luong OMO dao han", "ty VND", "D", "N05", "NHNN hut bom"),
        (r"^- bom/hut rong cua nhnn", "omo_net_daily",
         "Bom/hut rong trong ngay", "ty VND", "D", "N05", "NHNN hut bom"),
    ],
    "cung-tien-m2-huy-dong-385": [
        (r"^tong phuong tien thanh toan", "m2",
         "Tong phuong tien thanh toan (M2)", "ty VND", "M", "N12", "Tin dung giai ngan"),
        (r"^tien gui cua (dan cu|cu dan)", "deposits_household",
         "Tien gui cua cu dan", "ty VND", "M", "N10", "Room va chi phi von NH"),
        (r"^tien gui cua cac tckt", "deposits_corporate",
         "Tien gui cua cac TCKT", "ty VND", "M", "N10", "Room va chi phi von NH"),
        (r"^ty trong tien mat", "cash_ratio_m2",
         "Ty trong tien mat tren M2", "%", "M", "N12", "Tin dung giai ngan"),
    ],
    "lai-suat-cho-vay-binh-quan-ngan-hang-700": [
        (r"^lai suat cho vay binh quan$", "lending_rate_avg",
         "Lai suat cho vay binh quan (VCB cong bo)", "%/nam", "M", "N11", "Lai suat TT1"),
        (r"^chenh lech lai suat tien gui va cho vay", "lending_deposit_spread",
         "Chenh lech lai suat cho vay - tien gui", "diem %", "M", "N11", "Lai suat TT1"),
        (r"^chenh lech lai suat sau khi tru chi phi", "lending_spread_net_vcb",
         "Chenh lech lai suat sau chi phi huy dong va su dung von (VCB)", "diem %", "M", "N11", "Lai suat TT1"),
    ],
    # Can can thanh toan theo QUY (NHNN cong bo, tre ~1 quy) - dong von vao/ra THAT, trieu USD.
    # "Tien va tien gui" xuat hien 2 lan (tai san co / tai san no) nen khong lay.
    "can-can-thanh-toan-361": [
        (r"^a\. can can vang lai", "current_account_bop",
         "Can can vang lai (BOP)", "trieu USD", "Q", "N02", "Dong von ngoai sinh"),
        (r"^dau tu truc tiep vao viet nam", "fdi_inflow_bop",
         "FDI vao Viet Nam (BOP, tai san no)", "trieu USD", "Q", "N02", "Dong von ngoai sinh"),
        (r"^dau tu truc tiep \(rong\)", "fdi_net_bop",
         "Dau tu truc tiep rong (BOP)", "trieu USD", "Q", "N02", "Dong von ngoai sinh"),
        (r"^dau tu gian tiep \(rong\)", "fii_net_bop",
         "Dau tu gian tiep rong (BOP)", "trieu USD", "Q", "N02", "Dong von ngoai sinh"),
        (r"^dau tu khac \(rong\)", "other_inv_net_bop",
         "Dau tu khac rong (BOP: tien gui, vay no)", "trieu USD", "Q", "N02", "Dong von ngoai sinh"),
        (r"^c\. can can tai chinh", "financial_account_bop",
         "Can can tai chinh (BOP)", "trieu USD", "Q", "N02", "Dong von ngoai sinh"),
        (r"^d\. loi va sai sot", "bop_errors",
         "Loi va sai sot (BOP) - dong von khong ghi nhan duoc", "trieu USD", "Q", "N02", "Dong von ngoai sinh"),
        (r"^e\. can can tong the", "bop_overall",
         "Can can tong the (BOP) = thay doi du tru", "trieu USD", "Q", "N02", "Dong von ngoai sinh"),
    ],
    # Von dau tu toan xa hoi theo quy (Cuc Thong ke): phan FDI = von FDI THUC HIEN quy ra VND
    "von-dau-tu-phat-trien-xa-hoi-275": [
        (r"^von fdi$", "fdi_realized_vnd",
         "Von FDI thuc hien (VDT toan xa hoi)", "nghin ty VND", "Q", "N02", "Dong von ngoai sinh"),
    ],
    # Von dau tu tu NSNN thuc hien (giai ngan dau tu cong) - so TRONG THANG, ty VND (thang 1/2026 =
    # 44.636, thang 2 = 39.841 thap hon -> khong phai luy ke). Tien ngoai sinh vao he thong qua Kho bac.
    # BAY: 10/2025 lap lai dung so cua 09/2025 (86.622) - site chua cap nhat thang do.
    "von-dau-tu-tu-nsnn-317": [
        (r"^tong$", "public_inv_month",
         "Giai ngan dau tu cong trong thang (von NSNN thuc hien)", "ty VND", "M", "N09", "Nguon TT2"),
    ],
    "tang-truong-tin-dung-toc-do-353": [
        (r"^tong cong", "credit_growth_ytd",
         "Tang truong tin dung luy ke (NHNN cong bo)", "%", "M", "N12", "Tin dung giai ngan"),
    ],
    "kieu-hoi-tp-ho-chi-minh-426": [
        (r"^tong kieu hoi", "remittance",
         "Kieu hoi ve TP.HCM", "trieu USD", "Q", "N02", "Dong von ngoai sinh"),
    ],
    "von-fdi-dang-ky-cap-moi-405": [
        (r"^von dang ky cap moi", "fdi_registered",
         "Von FDI dang ky cap moi (luy ke)", "trieu USD", "M", "N02", "Dong von ngoai sinh"),
    ],
    "ty-gia-cho-den-719": [
        (r"^mua vao$", "fx_free_buy", "Ty gia cho den - mua vao", "VND/USD", "D", "N04", "Ty gia USD/VND"),
        (r"^ban ra$", "fx_free_sell", "Ty gia cho den - ban ra", "VND/USD", "D", "N04", "Ty gia USD/VND"),
        (r"^chenh lech voi gia ban", "fx_free_vs_vcb",
         "Chenh ty gia cho den so voi VCB ban", "VND", "D", "N04", "Ty gia USD/VND"),
    ],
}

_ACC = (("àáảãạăằắẳẵặâầấẩẫậ", "a"), ("èéẻẽẹêềếểễệ", "e"), ("ìíỉĩị", "i"),
        ("òóỏõọôồốổỗộơờớởỡợ", "o"), ("ùúủũụưừứửữự", "u"), ("ỳýỷỹỵ", "y"), ("đ", "d"))


def _norm(s) -> str:
    s = str(s or "").lower().strip()
    for src, dst in _ACC:
        for ch in src:
            s = s.replace(ch, dst)
    s = re.sub(r"\s*\d+\s*$", "", s)          # bo so dem cuoi nhan (vd "TONG CONG 4")
    return re.sub(r"\s+", " ", s).strip()


def _eom(y: int, m: int) -> str:
    return dt.date(y, m, calendar.monthrange(y, m)[1]).isoformat()


def _col_date(label: str) -> str | None:
    """'07-09-2026' -> 2026-09-07 | '06-2026' -> 2026-06-30 | 'Q2-2026' -> 2026-06-30."""
    s = str(label or "").strip()
    m = re.match(r"^(\d{1,2})-(\d{1,2})-(\d{4})$", s)
    if m:
        d, mth, y = (int(x) for x in m.groups())
        try:
            return dt.date(y, mth, d).isoformat()
        except ValueError:
            return None
    m = re.match(r"^(\d{1,2})-(\d{4})$", s)
    if m:
        return _eom(int(m.group(2)), int(m.group(1)))
    m = re.match(r"^Q([1-4])-(\d{4})$", s, re.I)
    if m:
        return _eom(int(m.group(2)), int(m.group(1)) * 3)
    return None


def _check_dates(html: str, newest_col: str, slug: str) -> bool:
    """Cot moi nhat phai trung moc cuoi trong temporalCoverage cua JSON-LD."""
    m = re.search(r'"temporalCoverage":"([^"]+)"', html)
    if not m:
        log("  ? %s: khong co temporalCoverage de doi chieu -> van nap" % slug)
        return True
    cov_end = m.group(1).split("/")[-1].strip()
    col = _col_date(newest_col)
    if not col:
        return False
    ref = cov_end if len(cov_end) == 10 else _eom(*(int(x) for x in cov_end.split("-")[:2]))
    if col == ref:
        return True
    # bang QUY: temporalCoverage ghi thang DAU quy (Q1-2026 -> "2026-01") -> chap nhan neu ref nam trong quy
    if re.match(r"^Q[1-4]-\d{4}$", str(newest_col), re.I) and ref[:7] in {
            col[:5] + "%02d" % m for m in range(int(col[5:7]) - 2, int(col[5:7]) + 1)}:
        return True
    log("  X %s: cot moi nhat ghi %s nhung temporalCoverage ket thuc %s -> BO QUA CA BANG "
        "(site dat nham nhan ngay)" % (slug, newest_col, cov_end))
    return False


def fetch_table(session, slug: str, spec: list) -> list:
    html = get(session, BASE + slug, tries=3, wait=5)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if not table:
        log("  ! %s: khong co bang" % slug)
        return []
    rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            for tr in table.find_all("tr")]
    rows = [r for r in rows if r]
    if not rows:
        return []

    header = rows[0]
    dates = [(i, _col_date(h)) for i, h in enumerate(header) if _col_date(h)]
    if not dates:
        log("  ! %s: khong doc duoc nhan ngay o dong tieu de" % slug)
        return []
    if not _check_dates(html, header[dates[0][0]], slug):
        return []

    out = []
    for r in rows[1:]:
        if len(r) < 2:
            continue
        label = _norm(r[1] if not r[0] else r[0])
        for sp in spec:
            pat, sid, name, unit, freq, node_id, node_name = sp[:7]
            factor = sp[7] if len(sp) > 7 else 1
            if not re.search(pat, label):
                continue
            for i, d in dates:
                v = vn_number(r[i]) if i < len(r) else None
                if v is None:
                    continue
                out.append(row(d, sid, v * factor, series_name=name, unit=unit, freq=freq,
                               source="dulieukinhte", node_id=node_id, node_name=node_name))
            break
    if out:
        log("  %-44s %d dong (%d chi tieu)" % (slug, len(out), len({r["series_id"] for r in out})))
    return out


def fetch_all(session) -> list:
    out = []
    for slug, spec in TABLES.items():
        try:
            out += fetch_table(session, slug, spec)
        except Exception as e:                                    # noqa: BLE001
            log("  X %s: %s" % (slug, str(e)[:70]))
        time.sleep(2)
    return out
