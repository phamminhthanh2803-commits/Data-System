# -*- coding: utf-8 -*-
"""Cac ty le cua he thong ngan hang NIEM YET, doc tu D:\\bctc\\fs-extractor (khong goi mang).

Truoc day module nay tu goi VCI qua vnstock cho MOT DANH SACH 18 MA go tay, phai gian
6 giay/ma vi rate limit -> mat ~10 phut va chi phu duoc 18/28 ngan hang. Nay FS Extractor
da keo full thi truong ve local nen:
  - Doc thang balance_sheet.csv va note.csv, quet theo chunk, moi file ~25 giay.
  - Nhan dien ngan hang bang nhan nganh (`nganh_L2` = "Ngan hang") -> tu dong du 28 ma,
    khong con danh sach go tay, ma moi len san la tu co.
  - Khong con phu thuoc rate limit cua vnstock.

Chi tieu -> node:
  ldr_broad_listed     cho vay KH / nguon von huy dong mo rong            N10
  loan_deposit_listed  cho vay KH / tien gui KH (KHONG phai LDR)          N10
  casa_ratio           tien gui khong ky han (nob66) / tien gui KH        N10
  bank_deposits        tien gui khach hang                                N10
  bank_loans           cho vay khach hang                                 N12

BAY DA XU LY: VCI dung LAI item_id cho ca dong tong tren bang can doi lan dong thuyet
minh ben duoi - vi du `deposits_and_loans_from_other_credit_institutions` co 2 dong
(VCB quy 2/2026: 405.184 va 389.128 ty) -> phai drop_duplicates keep="first" (dong tong
dung truoc trong file), neu khong tong nguon von bi cong doi va ty le sai xuong.
"""
from __future__ import annotations

import calendar
import datetime as dt
import os
import re

import pandas as pd

from common import log, row

FSX_DIR = os.environ.get("FSX_DIR") or os.path.join(os.path.normpath(os.environ.get("BCTC_ROOT", "D:/bctc")), "fs-extractor", "output")
F_BS = os.path.join(FSX_DIR, "balance_sheet.csv")
F_NOTE = os.path.join(FSX_DIR, "note.csv")
STALE_DAYS = 45                    # canh bao neu du lieu FS Extractor qua cu
MIN_BANKS = 15                     # duoi nguong nay coi nhu khong phai ban full thi truong

BANK_LABEL = "ngan hang"           # nhan nganh_L2 sau khi bo dau

ITEM_LOAN = "loans_and_advances_to_customers"
ITEM_DEP = "deposits_from_customers"
ITEM_INTERBANK = "deposits_and_loans_from_other_credit_institutions"
ITEM_PAPERS = "convertible_bonds_cds_and_other_valuable_papers_issued"
ITEM_GOV = "due_to_gov_and_loans_from_sbv"
ITEM_IB_LOAN = "loans_from_other_credit_institutions"   # phan VAY trong "tien gui va vay TCTD khac"
FUNDING = [ITEM_DEP, ITEM_INTERBANK, ITEM_PAPERS, ITEM_GOV, ITEM_IB_LOAN]
ITEM_DEMAND_DEP = "nob66"          # "Tien gui khong ky han" trong thuyet minh -> tu so CASA
# Cho vay phan theo THOI HAN trong thuyet minh (nob45 la dong tong):
ITEM_LOAN_ST = "nob46"             # cho vay ngan han
ITEM_LOAN_MT = "nob47"             # cho vay trung han
ITEM_LOAN_LT = "nob48"             # cho vay dai han
NOTE_ITEMS = {ITEM_DEMAND_DEP, ITEM_LOAN_MT, ITEM_LOAN_LT, ITEM_LOAN_ST}

N_ROOM = ("N10", "Room va chi phi von NH")
N_CREDIT = ("N12", "Tin dung giai ngan")

_ACC = (("àáảãạăằắẳẵặâầấẩẫậ", "a"), ("èéẻẽẹêềếểễệ", "e"), ("ìíỉĩị", "i"),
        ("òóỏõọôồốổỗộơờớởỡợ", "o"), ("ùúủũụưừứửữự", "u"), ("ỳýỷỹỵ", "y"), ("đ", "d"))


def _norm(s) -> str:
    s = str(s or "").lower().strip()
    for src, dst in _ACC:
        for ch in src:
            s = s.replace(ch, dst)
    return s


def _quarter_end(period: str):
    m = re.match(r"^(\d{4})-Q([1-4])$", str(period).strip())
    if not m:
        return None
    y, q = int(m.group(1)), int(m.group(2))
    mth = q * 3
    return dt.date(y, mth, calendar.monthrange(y, mth)[1]).isoformat()


def _scan(path: str, items: set, label: str) -> pd.DataFrame:
    """Quet file long-format cua FS Extractor, chi giu ngan hang + item can dung."""
    if not os.path.exists(path):
        log("  ! khong thay %s -> bo qua %s" % (path, label))
        return pd.DataFrame()
    age = (dt.datetime.now() - dt.datetime.fromtimestamp(os.path.getmtime(path))).days
    if age > STALE_DAYS:
        log("  ! %s da %d ngay chua cap nhat - chay lai FS Extractor de co quy moi"
            % (os.path.basename(path), age))
    use = ["ticker", "nganh_L2", "item_id", "period", "value"]
    frames = []
    for ch in pd.read_csv(path, usecols=lambda c: c in use, chunksize=1000000):
        ch = ch[ch["item_id"].isin(items)]
        if len(ch):
            frames.append(ch[ch["nganh_L2"].map(_norm) == BANK_LABEL])
    frames = [f for f in frames if len(f)]
    if not frames:
        log("  ! %s: khong khop dong nao" % label)
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    # xem chu thich dau file: item_id lap lai giua dong tong va dong thuyet minh
    df = df.drop_duplicates(subset=["ticker", "period", "item_id"], keep="first")
    n = df["ticker"].nunique()
    log("  %s: %d dong, %d ngan hang" % (label, len(df), n))
    # Truoc 08/09/2026 fsx GHI DE ca file moi lan chay: keo 1 ma thi file chi con 1 ma.
    # Nay fsx da gop nen kho xay ra, nhung van chan de khong bao gio tinh ty le cap
    # he thong tu vai ngan hang ma khong bao gi.
    if n < MIN_BANKS:
        log("  X chi thay %d ngan hang (nguong %d) - file khong phai ban full thi truong, "
            "chay lai FS Extractor cho toan bo tickers.txt roi lam lai" % (n, MIN_BANKS))
        return pd.DataFrame()
    return df


def _enough(cnt: pd.Series, period) -> bool:
    """Bo ky moi mo chi vai ngan hang kip ra bao cao."""
    return cnt.get(period, 0) >= max(3, int(0.6 * cnt.max()))


def fetch_all(_session=None) -> list:
    bs = _scan(F_BS, set([ITEM_LOAN] + FUNDING), "bang can doi")
    if not len(bs):
        return []

    piv = bs.pivot_table(index="period", columns="item_id", values="value", aggfunc="sum")
    cnt = bs.groupby("period")["ticker"].nunique()
    out = []
    for period, r in piv.iterrows():
        d = _quarter_end(period)
        loan, dep = r.get(ITEM_LOAN), r.get(ITEM_DEP)
        if not d or not loan or not dep or not _enough(cnt, period):
            continue
        out.append(row(d, "loan_deposit_listed", round(float(loan) / float(dep) * 100, 2),
                       series_name="Cho vay KH / Tien gui KH nhom NH niem yet", unit="%",
                       freq="Q", source="FS Extractor", node_id=N_ROOM[0], node_name=N_ROOM[1]))
        # LDR theo Dieu 20 Thong tu 22/2019: tong tien gui = tien gui KH + TIEN GUI cua TCTD khac
        # (khong gom phan VAY TCTD) + giay to co gia da phat hanh. KHONG cong vay NHNN/Chinh phu.
        # Hai gioi han: (1) so HOP NHAT, TT22 ap cho rieng le (VPB gom FE Credit nen bi thoi);
        # (2) chua loai tien gui Kho bac Nha nuoc (TT26/2022, TT08/2026) vi bang can doi khong tach.
        ib_dep = float(r.get(ITEM_INTERBANK) or 0) - float(r.get(ITEM_IB_LOAN) or 0)
        tg22 = float(dep) + max(ib_dep, 0.0) + float(r.get(ITEM_PAPERS) or 0)
        if tg22:
            out.append(row(d, "ldr_tt22_listed", round(float(loan) / tg22 * 100, 2),
                           series_name="LDR theo Dieu 20 TT22 (NH niem yet, hop nhat, chua loai KBNN)",
                           unit="%", freq="Q", source="FS Extractor",
                           node_id=N_ROOM[0], node_name=N_ROOM[1]))
        out.append(row(d, "bank_deposits", round(float(dep) / 1e9, 2),
                       series_name="Tien gui khach hang nhom NH niem yet", unit="ty VND",
                       freq="Q", source="FS Extractor", node_id=N_ROOM[0], node_name=N_ROOM[1]))
        out.append(row(d, "bank_loans", round(float(loan) / 1e9, 2),
                       series_name="Cho vay khach hang nhom NH niem yet", unit="ty VND",
                       freq="Q", source="FS Extractor", node_id=N_CREDIT[0], node_name=N_CREDIT[1]))

    # ---------------------------------------------------------------- CASA
    nt_all = _scan(F_NOTE, NOTE_ITEMS, "thuyet minh")
    nt = nt_all[nt_all.item_id == ITEM_DEMAND_DEP] if len(nt_all) else nt_all
    if len(nt):
        dem = nt.groupby("period")["value"].sum()
        ncnt = nt.groupby("period")["ticker"].nunique()
        # mau so phai cung bo ma voi tu so: ngan hang nao khong co dong "tien gui khong
        # ky han" trong thuyet minh thi cung khong duoc tinh vao tong tien gui
        dep_by = (bs[bs.item_id == ITEM_DEP]
                  .merge(nt[["ticker", "period"]].drop_duplicates(), on=["ticker", "period"])
                  .groupby("period")["value"].sum())
        for period, demand in dem.items():
            d = _quarter_end(period)
            dep = dep_by.get(period)
            if not d or not dep or not _enough(ncnt, period):
                continue
            out.append(row(d, "casa_ratio", round(float(demand) / float(dep) * 100, 2),
                           series_name="Ty le CASA nhom NH niem yet", unit="%",
                           freq="Q", source="FS Extractor",
                           node_id=N_ROOM[0], node_name=N_ROOM[1]))

    # ------------------------------------------- co cau ky han cho vay
    # KHONG phai SFL theo Thong tu 22: SFL can NGUON VON theo ky han con lai, ma thuyet
    # minh chi tach tien gui thanh "khong ky han / co ky han" chu khong theo ky han con
    # lai -> mau so cua SFL khong lay duoc. Day la TU SO cua SFL (phan du no trung dai
    # han), theo doi ap luc chuyen hoa ky han.
    if len(nt_all):
        lt = nt_all[nt_all.item_id.isin([ITEM_LOAN_ST, ITEM_LOAN_MT, ITEM_LOAN_LT])]
        if len(lt):
            piv2 = lt.pivot_table(index="period", columns="item_id", values="value", aggfunc="sum")
            lcnt = lt.groupby("period")["ticker"].nunique()
            for period, r2 in piv2.iterrows():
                d = _quarter_end(period)
                mlt = float(r2.get(ITEM_LOAN_MT) or 0) + float(r2.get(ITEM_LOAN_LT) or 0)
                tot = mlt + float(r2.get(ITEM_LOAN_ST) or 0)
                if not d or not tot or not _enough(lcnt, period):
                    continue
                out.append(row(d, "mlt_loan_share", round(mlt / tot * 100, 2),
                               series_name="Ty trong cho vay trung dai han (NH niem yet)",
                               unit="%", freq="Q", source="FS Extractor",
                               node_id=N_ROOM[0], node_name=N_ROOM[1]))
                out.append(row(d, "mlt_loans", round(mlt / 1e9, 2),
                               series_name="Du no cho vay trung dai han (NH niem yet)",
                               unit="ty VND", freq="Q", source="FS Extractor",
                               node_id=N_ROOM[0], node_name=N_ROOM[1]))

    log("  BCTC quy: %d dong" % len(out))
    return out
