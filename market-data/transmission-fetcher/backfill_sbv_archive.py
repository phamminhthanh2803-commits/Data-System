# -*- coding: utf-8 -*-
"""Backfill lich su tu ARCHIVE cua trang 'Thong ke mot so chi tieu co ban' (sbv.gov.vn).

Trang do la portlet Asset Publisher cua Liferay: ngoai ban moi nhat con giu lai TOAN BO
cac ban da cong bo, phan trang qua tham so _cur. Moi ban la mot bang rieng:

  chi_tieu : Tong tai san, Von dieu le, TY LE VON NGAN HAN CHO VAY TRUNG DAI HAN (SFL),
             LDR - theo tung nhom TCTD. Cong bo THEO THANG.
  car      : Von tu co va TY LE AN TOAN VON (CAR), tach theo nhom ap dung TT41/TT22/TT14/TT23.

*** WAF ***
sbv.gov.vn chan rat nhanh khi goi nhieu: 6 giay/request la da bi chan sau 3 trang.
Script nay chay CHAM (mac dinh 25 giay/request), moi request mot session moi, va LUU TIEN DO
sau tung muc vao sbv_archive_state.json -> bi chan giua chung thi chay lai la tiep tuc,
khong lam lai tu dau. Chay full lan dau mat khoang 1 tieng.

    python backfill_sbv_archive.py            # chay/tiep tuc
    python backfill_sbv_archive.py --pause 40 # cham hon neu van bi chan
    python backfill_sbv_archive.py --merge    # chi gop ket qua da co vao master

*** BAY DA XU LY ***
Trang chi tiet cua MOT ban van hien bang MOI NHAT o dau, roi moi den bang cua ban duoc
tro toi. Vi vay khong duoc lay bang dau tien - phai lay bang CUOI CUNG khop dung loai,
va lay NGAY tu tieu de muc trong danh sach chu khong doc ngay tren trang.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html as ihtml
import json
import os
import re
import time

from bs4 import BeautifulSoup

from common import MASTER, log, merge_master, new_session, row, setup_stdout, vn_number

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(ROOT, "sbv_archive_state.json")

PORTLET = "com_liferay_asset_publisher_web_portlet_AssetPublisherPortlet_INSTANCE_whgo"
LIST_URL = ("https://sbv.gov.vn/vi/thong-ke-mot-so-chi-tieu-co-ban"
            "?p_p_id={p}&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
            "&_{p}_cur={{cur}}&_{p}_delta=20").format(p=PORTLET)
MAX_PAGES = 25

N_ROOM = ("N10", "Room va chi phi von NH")
N_POLICY = ("N03", "Noi rang buoc va nguon")

_ACC = (("àáảãạăằắẳẵặâầấẩẫậ", "a"), ("èéẻẽẹêềếểễệ", "e"), ("ìíỉĩị", "i"),
        ("òóỏõọôồốổỗộơờớởỡợ", "o"), ("ùúủũụưừứửữự", "u"), ("ỳýỷỹỵ", "y"), ("đ", "d"))


def _norm(s) -> str:
    s = str(s or "").lower().strip()
    for src, dst in _ACC:
        for ch in src:
            s = s.replace(ch, dst)
    return re.sub(r"\s+", " ", s)


class Budget(Exception):
    """Het han muc request cua dot nay - thoat sach de dot sau chay tiep."""


class Blocked(Budget):
    """WAF vua chan - ket thuc dot NGAY, khong thu them (moi request bi tu choi van bi dem)."""


# WAF cua SBV cho qua khoang 13-15 request roi chan CA IP trong nhieu chuc phut, bat ke
# nghi bao lau giua cac request. Vi vay khong cai duoc bang cach cham hon - phai chay
# THANH TUNG DOT ngan roi nghi han. `_BUDGET` dem so request da tieu trong dot hien tai.
_BUDGET = {"left": None}
_EVENTS = []                      # [thoi diem, ok?] cua tung request - de hoc quota/cua so
CACHE = os.path.join(ROOT, "sbv_cache")


def _cache_path(url):
    return os.path.join(CACHE, hashlib.sha1(url.encode("utf-8")).hexdigest() + ".html")


def _cached(url):
    p = _cache_path(url)
    if os.path.exists(p):
        return open(p, encoding="utf-8").read()
    return None


def _store(url, html):
    os.makedirs(CACHE, exist_ok=True)
    open(_cache_path(url), "w", encoding="utf-8").write(html)


def _fetch(url, pause):
    """Moi request mot session moi - WAF cua SBV gioi han so request tren mot phien.

    MOI TRANG TAI VE DEU LUU vao sbv_cache/ - request la thu dat nhat o day, khong bao gio
    tra hai lan cho cung mot URL (doi parser, chay lai, deu doc tu dia).
    Vua bi chan la KET THUC DOT ngay: da chan roi thi moi request tiep theo deu hong ma
    van bi dem, chi lam lenh cam dai them. Dot sau nghi du lau roi chay tiep tu cho nay.
    """
    c = _cached(url)
    if c is not None:
        return c
    if _BUDGET["left"] is not None:
        if _BUDGET["left"] <= 0:
            raise Budget()
        _BUDGET["left"] -= 1
    html = get_page(url)
    _EVENTS.append([dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bool(html)])
    if html is None:
        raise Blocked()
    _store(url, html)
    time.sleep(pause)
    return html


def get_page(url):
    """MOT lan thu duy nhat.

    Thu lai ngay khi vua bi chan chi lam lenh cam dai them, vi WAF dem ca request bi tu
    choi. Da bi chan thi cach duy nhat la nghi - de vong lap dot ngoai kia lo viec do.
    """
    from common import get
    return get(new_session("browser"), url, tries=1,
               referer="https://sbv.gov.vn/", timeout=45)


def probe():
    """Trang danh sach nhe nhat - hoi 'het bi chan chua' truoc khi mo dot moi."""
    from common import get
    ok = bool(get(new_session("browser"), LIST_URL.format(cur=1), tries=1, timeout=40))
    _EVENTS.append([dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ok])
    return ok


# ------------------------------------------------------------- liet ke archive
def parse_date(title):
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", title)
    if m:
        return "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1)))
    return None


def classify(title):
    t = _norm(title)
    if "ty le an toan von" in t:
        return "car"
    if "chi tieu co ban" in t and "roa" not in t:
        return "chi_tieu"
    return None


def list_entries(html):
    out = []
    for m in re.finditer(r'<a[^>]+href="([^"]*asset_publisher[^"]*)"[^>]*>(.*?)</a>', html, re.S):
        title = re.sub(r"\s+", " ", ihtml.unescape(re.sub(r"<[^>]+>", "", m.group(2)))).strip()
        kind = classify(title) if len(title) > 12 else None
        if not kind:
            continue
        d = parse_date(title)
        if not d:
            continue
        url = ihtml.unescape(m.group(1))
        if url.startswith("/"):
            url = "https://sbv.gov.vn" + url
        out.append(dict(kind=kind, date=d, title=title, url=url))
    return out


# ------------------------------------------------------------------- bo doc bang
def tables(html):
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
    return out


HEAD_ROWS = 6          # ban 2024 co 3 dong tren cung (tieu de, ngay, "Don vi: ty dong")
                       # roi moi den dong ten cot -> quet 3 dong dau la truot het nam 2023-2024


def pick(tbls, needle):
    """Lay bang CUOI CUNG co tieu de khop - bang dau tien la ban moi nhat luon hien o dau.

    Dong ten cot khong nam co dinh o dau bang: ban 2025-2026 dat no trong 3 dong dau, ban
    2023-2024 day xuong dong thu 4 vi co them dong tieu de va dong don vi. Quet HEAD_ROWS
    dong dau de bat duoc ca hai kieu.
    """
    hits = [t for t in tbls
            if any(needle in _norm(" ".join(r)) for r in t[:HEAD_ROWS])]
    return hits[-1] if hits else None


GROUPS = {"toan he thong": "system", "nhtm nha nuoc": "soe", "nhtm co phan": "jsc"}

# ------------------------------------------------------- doc so theo dung quy uoc cua bang
# SBV KHONG nhat quan giua cac ban: ban 2022-2024 danh may kieu My ("2,140,824.1" - phay
# la hang nghin, cham la thap phan), ban 2019-2021 va 2025-2026 danh kieu Viet
# ("2.039.967,8"). Doc nham quy uoc thi LDR 83,16% thanh 8316 - sai ma van "co so", nen
# phai suy ra quy uoc TU CHINH BANG roi moi doc.
_NUM_TOKEN = re.compile(r"^-?\d[\d.,]*$")


def _decimal_char(tbl):
    """Suy ra dau thap phan cua ca bang tu nhung o KHONG the hieu nham.

    Mot o co ca '.' lan ',' thi dau DUNG SAU la thap phan. Mot o chi co mot loai dau ma
    theo sau khong phai 3 chu so thi dau do la thap phan. Khong doan duoc thi mac dinh
    kieu Viet, vi do la quy uoc cua phan lon cac ban.
    """
    votes = {",": 0, ".": 0}
    for r_ in tbl:
        for c in r_:
            s = str(c).strip()
            if not _NUM_TOKEN.match(s):
                continue
            if "." in s and "," in s:
                votes["." if s.rfind(".") > s.rfind(",") else ","] += 1
                continue
            for ch in (",", "."):
                if s.count(ch) == 1 and len(s.split(ch)[1]) != 3:
                    votes[ch] += 1
    return "." if votes["."] > votes[","] else ","


def _num(txt, dec):
    """Doi mot o sang float theo dau thap phan `dec` da suy ra cho bang."""
    s = str(txt or "").replace("%", "").replace("\xa0", " ").replace(" ", "").strip()
    s = re.sub(r"\(\*+\)", "", s)
    if not s or not _NUM_TOKEN.match(s):
        return None
    neg = s.startswith("-")
    s = s.lstrip("-")
    thou = "," if dec == "." else "."
    s = s.replace(thou, "")
    if dec in s:                       # chi giu dau thap phan CUOI (SBV co o "892,137,0")
        head, _, tail = s.rpartition(dec)
        s = (head.replace(dec, "") or "0") + "." + tail
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


# --------------------------------------------------- ban do cot theo TEN, khong theo so
# So cot doi giua cac vintage: ban tu 2020 co 7 cot (Loai hinh, Tong TS x2, Von DL x2, SFL,
# LDR), ban 2019 co 9 cot va KHONG co LDR (thay vao do la Von tu co x2 va CAR toi thieu).
# Doc theo so thu tu cot la sai lech ca bang khi gap vintage khac, nen phai doc theo ten.
RATIO_COLS = (
    ("ty le du no cho vay so voi", "ldr", "LDR", N_ROOM),
    ("ty le von ngan han cho vay", "sfl", "Ty le von ngan han cho vay trung dai han", N_POLICY),
    ("ty le an toan von", "car_min", "Ty le an toan von toi thieu", N_ROOM),
)
ABS_COLS = (
    ("tong tai san", "bank_total_assets", "Tong tai san he thong TCTD"),
    ("von dieu le", "bank_charter_capital", "Von dieu le he thong TCTD"),
    ("von tu co", "bank_own_capital", "Von tu co he thong TCTD"),
)


def _columns(tbl):
    """-> {chi so cot: (vai tro, nhan)}; vai tro la 'abs' | 'growth' | 'val'.

    Dong ten cot chia doi: nhung chi tieu co ca so tuyet doi lan toc do tang chiem HAI cot
    (dong duoi ghi "So tuyet doi" / "Toc do tang truong"), con ty le chi chiem MOT. Cu the
    la phai dan hai dong tieu de lai voi nhau moi biet cot nao la cot nao.
    """
    h0 = None
    for i, r_ in enumerate(tbl[:HEAD_ROWS]):
        if "loai hinh tctd" in _norm(" ".join(r_)):
            h0 = i
            break
    if h0 is None:
        return None
    labels = [_norm(x) for x in tbl[h0]]
    sub = [_norm(x) for x in tbl[h0 + 1]] if h0 + 1 < len(tbl) else []
    cols, idx, si = {}, 0, 0
    for k, lab in enumerate(labels):
        if k == 0:
            cols[idx] = ("group", lab)
            idx += 1
            continue
        if si < len(sub) and sub[si].startswith("so tuyet doi"):
            cols[idx] = ("abs", lab)
            cols[idx + 1] = ("growth", lab)
            idx += 2
            si += 2
        else:
            cols[idx] = ("val", lab)
            idx += 1
    return cols


def parse_chi_tieu(tbl, date):
    """Doc bang 'Thong ke mot so chi tieu co ban' cho MOI vintage, dua vao ten cot."""
    cols = _columns(tbl)
    if not cols:
        return []
    dec = _decimal_char(tbl)
    ncol = max(cols) + 1
    out = []
    for c in tbl:
        if len(c) < ncol:
            continue
        key = GROUPS.get(_norm(c[0]))
        if not key:
            continue
        for i, (role, lab) in cols.items():
            if role == "growth" or i >= len(c):
                continue
            if role == "val":
                for needle, pre, name, node in RATIO_COLS:
                    if needle in lab:
                        v = _num(c[i], dec)
                        if v:
                            out.append(row(
                                date, pre + ("_system" if key == "system" else "_" + key), v,
                                series_name=name + " " + c[0], unit="%", freq="M",
                                source="SBV", node_id=node[0], node_name=node[1]))
                        break
            elif role == "abs" and key == "system":
                for needle, sid, name in ABS_COLS:
                    if lab.startswith(needle):
                        v = _num(c[i], dec)
                        if v:
                            out.append(row(date, sid, v, series_name=name, unit="ty VND",
                                           freq="M", source="SBV",
                                           node_id=N_ROOM[0], node_name=N_ROOM[1]))
                        break
    return out


def parse_car(tbl, date):
    """[Loai hinh, Von tu co, %tang, CAR] - co dong tieu de nhom theo Thong tu ap dung.

    Chi lay nhom Thong tu 41 (chuan Basel II, phu phan lon NHTM) va hai nhom con cua no.
    NHNN KHONG cong bo mot con so CAR chung cho ca he thong.
    """
    out, grp = [], None
    dec = _decimal_char(tbl)
    for c in tbl:
        if not c:
            continue
        lab = _norm(c[0])
        if lab.startswith("nhom"):
            grp = "tt41" if "41" in lab else ("tt22" if "22" in lab else
                                              ("tt14" if "14" in lab else "khac"))
            if grp == "tt41" and len(c) >= 4:
                car, cap = _num(c[3], dec), _num(c[1], dec)
                if car:
                    out.append(row(date, "car_tt41", car,
                                   series_name="CAR nhom ngan hang ap dung Thong tu 41",
                                   unit="%", freq="M", source="SBV",
                                   node_id=N_ROOM[0], node_name=N_ROOM[1]))
                if cap:
                    out.append(row(date, "own_capital_tt41", cap,
                                   series_name="Von tu co nhom ap dung Thong tu 41",
                                   unit="ty VND", freq="M", source="SBV",
                                   node_id=N_ROOM[0], node_name=N_ROOM[1]))
            continue
        if grp != "tt41" or len(c) < 4:
            continue
        key = GROUPS.get(lab)
        if key in ("soe", "jsc"):
            car = _num(c[3], dec)
            if car:
                out.append(row(date, "car_tt41_" + key, car,
                               series_name="CAR " + c[0] + " (nhom Thong tu 41)",
                               unit="%", freq="M", source="SBV",
                               node_id=N_ROOM[0], node_name=N_ROOM[1]))
    return out


# Neo bang chi_tieu vao cot SFL chu khong phai cot LDR: ban 2019 khong co cot LDR.
# Cot SFL co o moi vintage va KHONG co trong bang CAR, nen khong bat nham bang.
PARSER = {"chi_tieu": (parse_chi_tieu, "ty le von ngan han cho vay"),
          "car": (parse_car, "ty le an toan von")}


def read_tables(tbls, kind, date):
    """Doc bang theo loai da khai, khong duoc thi thu loai con lai.

    Tieu de trong danh sach doi khi khong khop noi dung: ban 30/07/2024 mang ten "chi tieu
    co ban" nhung trang chi co bang CAR. Bo qua theo tieu de la mat luon bang do.
    """
    order = [kind] + [k for k in PARSER if k != kind]
    for k in order:
        fn, needle = PARSER[k]
        tbl = pick(tbls, needle)
        if tbl:
            rows = fn(tbl, date)
            if rows:
                return rows
    return []


# ------------------------------------------------------------------------ chay
def load_state():
    if os.path.exists(STATE):
        return json.load(open(STATE, encoding="utf-8"))
    return {"pages": [], "entries": {}, "rows": {}, "failed": []}


def save_state(st):
    if _EVENTS:                       # nhat ky request de lan sau hoc quota/cua so
        ev = st.setdefault("waf", {}).setdefault("events", [])
        ev.extend(_EVENTS)
        del ev[:-400]
        del _EVENTS[:]
    json.dump(st, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)


def main():
    setup_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--pause", type=float, default=25.0, help="giay giua cac request")
    ap.add_argument("--merge", action="store_true", help="chi gop ket qua da co vao master")
    ap.add_argument("--relist", action="store_true", help="quet lai danh sach tu dau")
    ap.add_argument("--max-req", type=int, default=0,
                    help="chay toi da bao nhieu request roi thoat (0 = khong gioi han)")
    ap.add_argument("--skip-list", action="store_true",
                    help="bo qua pha liet ke, doc luon cac ban da tim thay")
    ap.add_argument("--batch", type=int, default=10,
                    help="so request moi dot, nen duoi nguong 13-15 cua WAF")
    ap.add_argument("--rest", type=float, default=900.0, help="giay nghi giua hai dot")
    ap.add_argument("--rounds", type=int, default=0, help="so dot toi da (0 = den khi xong)")
    ap.add_argument("--test-list", action="store_true",
                    help="thu xem trang danh sach co chua TOAN VAN 20 ban khong; co thi gat het")
    args = ap.parse_args()

    st = load_state()
    if args.relist:
        st["pages"] = []

    if args.test_list:
        _BUDGET["left"] = args.batch
        try:
            harvest_list(st, args)
        except Blocked:
            log("Bi chan giua chung - cho het chan roi chay lai --test-list, trang da tai nam trong cache.")
        except Budget:
            log("Het han muc %d request - chay lai --test-list sau khi nghi de gat tiep." % args.batch)
    elif args.max_req:                    # chay tay mot dot duy nhat
        _BUDGET["left"] = args.max_req
        try:
            _run(st, args)
        except Budget:
            log("Het han muc %d request cua dot nay." % args.max_req)
    else:
        _rounds(st, args)

    # ---- pha 3: gop ----
    allrows = [r for rs in st["rows"].values() for r in rs]
    if not allrows:
        log("Chua co du lieu de gop.")
        return
    df = merge_master(allrows, MASTER)
    log("Da gop %d dong tu %d ban vao master (%d dong, %d series)"
        % (len(allrows), len(st["rows"]), len(df), df["series_id"].nunique()))
    con = _todo(st)
    if con:
        log("Con %d ban chua doc duoc - chay lai script de lay tiep." % len(con))


PASTE_STATE = os.path.join(ROOT, "sbv_paste_state.json")


def _pasted():
    """Cac ban da duoc dan tay qua paste_sbv.py -> khong can tai lai. Key 'kind|date'."""
    if not os.path.exists(PASTE_STATE):
        return set()
    return set(json.load(open(PASTE_STATE, encoding="utf-8")))


def _todo(st):
    """Entries chua doc va chua dan tay, moi nhat truoc."""
    pasted = _pasted()
    out = [e for u, e in st["entries"].items()
           if u not in st["rows"] and "%s|%s" % (e["kind"], e["date"]) not in pasted]
    # CAR truoc (chi 7 ban ma lap day 4 chuoi trong), roi moi nhat truoc
    out.sort(key=lambda e: (0 if e["kind"] == "car" else 1, -int(e["date"].replace("-", ""))))
    return out


def _remaining(st):
    return [e["url"] for e in _todo(st)]


def _rounds(st, args):
    """Chay thanh tung dot ngan, giua cac dot nghi han.

    WAF khong tinh theo toc do ma theo SO REQUEST tren mot IP trong mot cua so thoi gian:
    khoang 13-15 request la chan ca IP trong vai chuc phut. Cham hon khong cuu duoc, chi
    co chay it roi nghi moi qua. Moi dot deu hoi truoc mot cau (`probe`) de khong dot chay
    han muc vao luc dang bi chan.
    """
    if args.merge:
        return
    waf = st.setdefault("waf", {})
    batch = int(waf.get("batch") or args.batch)
    rnd = 0
    while True:
        rnd += 1
        if args.rounds and rnd > args.rounds:
            log("Da chay du %d dot." % args.rounds)
            return
        if not _todo(st):
            log("Da doc het %d ban." % len(st["rows"]))
            return
        log("--- dot %d: hoi thu WAF (batch %d, cua so uoc %.0f phut) ---"
            % (rnd, batch, (waf.get("window") or args.rest) / 60))
        if not probe():
            _wait_unblock(st, args)
        _BUDGET["left"] = batch
        n0 = len(st["rows"])
        blocked = False
        try:
            _run(st, args)
        except Blocked:
            blocked = True
        except Budget:
            pass
        got = len(st["rows"]) - n0
        if blocked:
            # bi chan sau `got` ban -> quota thuc te ~ got (+1 probe); lan sau dung som hon
            waf["quota"] = got + 1
            batch = max(4, got - 2)
            log("  bi chan sau %d ban -> hoc: quota ~%d, dot sau chi chay %d" % (got, got + 1, batch))
        elif got >= batch:
            # het han muc ma chua bi chan -> lan sau thu nhich them 2, den khi cham tran
            cap = int(waf.get("quota") or 30) - 1
            batch = min(batch + 2, max(cap, batch))
        waf["batch"] = batch
        save_state(st)
        left = _remaining(st)
        if not left:
            log("Da doc het %d ban." % len(st["rows"]))
            return
        rest = waf.get("window") or args.rest
        log("Dot %d xong: +%d ban, da doc %d/%d, con %d. Nghi %.0f phut roi chay tiep."
            % (rnd, got, len(st["rows"]), len(st["entries"]), len(left), rest / 60))
        time.sleep(rest)


def _wait_unblock(st, args):
    """Dang bi chan: nghi bang cua so da hoc (hoac --rest), roi hoi lai moi 5 phut.

    Moi lan het chan thi ghi lai 'mat bao lau' -> lan sau nghi vua du, khong thua khong thieu.
    Lan dau nghi hoi non (cua so - 5 phut) de co co hoi hoc duoc cua so NGAN hon.
    """
    waf = st.setdefault("waf", {})
    est = float(waf.get("window") or args.rest)
    t0 = time.time()
    first = max(300.0, est - 300.0)
    log("  dang bi chan, nghi %.0f phut roi hoi lai" % (first / 60))
    time.sleep(first)
    while not probe():
        log("  van chan sau %.0f phut, hoi lai sau 5 phut" % ((time.time() - t0) / 60))
        time.sleep(300)
    elapsed = time.time() - t0
    waf["window"] = elapsed + 120
    save_state(st)
    log("  het chan sau %.0f phut -> hoc: cua so %.0f phut" % (elapsed / 60, waf["window"] / 60))


def _run(st, args):
    if args.merge:
        return

    if not args.skip_list:
        # ---- pha 1: liet ke ----
        empty = 0
        for cur in range(1, MAX_PAGES + 1):
            if cur in st["pages"]:
                continue
            html = _fetch(LIST_URL.format(cur=cur), args.pause)
            if not html:
                log("  ! trang %d bi chan, se thu lai o lan chay sau" % cur)
                continue
            es = list_entries(html)
            new = 0
            for e in es:
                if e["url"] not in st["entries"]:
                    st["entries"][e["url"]] = e
                    new += 1
            st["pages"].append(cur)
            save_state(st)
            log("  trang %2d: %d muc, moi %d (tong %d)" % (cur, len(es), new, len(st["entries"])))
            empty = empty + 1 if new == 0 else 0
            if empty >= 2:
                log("  -> khong con muc moi, dung liet ke")
                break

    # ---- pha 2: doc tung ban ----
    # Uu tien ban MOI NHAT truoc: neu chi lay duoc mot phan thi phan lay duoc van la
    # phan dang dung nhat de theo doi.
    todo = _todo(st)
    log("Con %d ban can doc (da co %d, dan tay %d)" % (len(todo), len(st["rows"]), len(_pasted())))
    for i, e in enumerate(todo, 1):
        html = _fetch(e["url"], args.pause)
        if not html:
            if e["url"] not in st["failed"]:
                st["failed"].append(e["url"])
            save_state(st)
            continue
        rows = read_tables(tables(html), e["kind"], e["date"])
        if not rows:
            log("  ? %s %s: khong thay bang khop" % (e["kind"], e["date"]))
        st["rows"][e["url"]] = rows
        if e["url"] in st["failed"]:
            st["failed"].remove(e["url"])
        save_state(st)
        log("  [%3d/%3d] %-8s %s -> %d chi tieu" % (i, len(todo), e["kind"], e["date"], len(rows)))


def _articles(html):
    """Tach tung <article> tren trang danh sach: (kind, date, cac bang trong article do)."""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for art in soup.find_all("article"):
        head = art.find(["h1", "h2", "h3", "h4"]) or art.find("a", href=re.compile("asset_publisher"))
        title = head.get_text(" ", strip=True) if head else art.get_text(" ", strip=True)[:120]
        tbls = []
        for t in art.find_all("table"):
            rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                    for tr in t.find_all("tr")]
            rows = [r for r in rows if r]
            if rows:
                tbls.append(rows)
        out.append(dict(title=title, kind=classify(title), date=parse_date(title), tables=tbls))
    return out


def harvest_list(st, args):
    """Neu trang danh sach render TOAN VAN thi 9 trang = ca kho, thay vi 170 request.

    Trang 1 khong co bang -> ket luan la KHONG, dung ngay (ton dung 1 request).
    """
    for cur in range(1, MAX_PAGES + 1):
        html = _fetch(LIST_URL.format(cur=cur), args.pause)
        arts = _articles(html)
        n_tab = sum(len(a["tables"]) for a in arts)
        log("  trang %2d: %d article, %d bang" % (cur, len(arts), n_tab))
        if cur == 1 and n_tab < 5:
            log("  -> trang danh sach KHONG chua toan van. Van phai doc tung ban.")
            return False
        if not arts:
            break
        new = 0
        for a in arts:
            if not a["kind"] or not a["date"]:
                continue
            fn, needle = PARSER[a["kind"]]
            tbl = pick(a["tables"], needle)
            if not tbl:
                continue
            key = next((u for u, e in st["entries"].items()
                        if e["kind"] == a["kind"] and e["date"] == a["date"]),
                       "list://%s/%s" % (a["kind"], a["date"]))
            if key in st["rows"]:
                continue
            st["rows"][key] = fn(tbl, a["date"])
            new += 1
        save_state(st)
        log("  trang %2d: gat them %d ban (tong %d)" % (cur, new, len(st["rows"])))
        if not _todo(st):
            break
    return True


if __name__ == "__main__":
    main()
