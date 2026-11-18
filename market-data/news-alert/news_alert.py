# -*- coding: utf-8 -*-
r"""news_alert.py - canh bao TIN TUC theo watchlist co phieu (18/11/2026).

Moi lan chay: keo RSS 57 feed (news-rss\fetch_rss.run, kho rieng .\kho) -> loc bai co ma trong watchlist.csv (cot `ma` do bo
phan loai gan: ma 3 ky tu / ten DN trong alias_ma.csv, hoac `ten_goi_them` tu khai) -> bai CHUA bao (gop tin trung nhieu bao)
-> gui theo KENH:
    email  ONLINE 24/7: GitHub Actions news-alert.yml 15 phut/lan (Gmail SMTP, mat khau = secret NEWS_ALERT_SMTP_PASS)
           + email TOM TAT CUOI NGAY bang Claude Sonnet (tom_tat.py, secret ANTHROPIC_API_KEY) luc config.tom_tat_email_gio
    toast  laptop (task Windows "News Alert", chi khi may bat) - thong bao goc man hinh, bam = mo bai

watchlist.csv + config.json DUNG CHUNG qua Google Drive (gdrive:pipeline-data/market-data/news-alert): moi lan chay keo ve,
sua (app / CLI them-xoa) thi day len. Trang thai rieng tung kenh: email = da_gui.json + lich_su.csv (Actions dong bo Drive),
toast = da_gui_may.json + lich_su_may.csv (chi o laptop).

    python news_alert.py --kenh toast    1 lan (task laptop)      |  python news_alert.py --kenh email   (Actions)
    python news_alert.py ds              xem watchlist            |  python news_alert.py them HPG VCB / xoa HPG
    python news_alert.py --thu           gui thu 2 bai moi nhat khop watchlist (khong ghi trang thai)
    python news_alert.py --khong-keo     dung kho hien co, khong keo RSS
Env: NEWS_ALERT_REMOTE (rong = khong dung Drive), RCLONE, RCLONE_CONFIG.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import shutil
import smtplib
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from email.mime.text import MIMEText

BASE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.dirname(BASE)                                   # D:\market-data
for p in (MD, os.path.join(MD, "news-rss"), BASE):
    if p not in sys.path:
        sys.path.insert(0, p)

WATCHLIST = os.path.join(BASE, "watchlist.csv")
CONFIG = os.path.join(BASE, "config.json")
SENT = os.path.join(BASE, "da_gui.json")                     # kenh email (online) - dong bo Drive
LICH_SU = os.path.join(BASE, "lich_su.csv")
KHO = os.path.join(BASE, "kho")
LOGS = os.path.join(BASE, "logs")
TOM_TAT = os.path.join(BASE, "tom_tat")
TOAST_PS1 = os.path.join(BASE, "toast.ps1")
GIU_NGAY = 14                                                # nho bai da bao trong 14 ngay
NO_WINDOW = 0x08000000
REMOTE = os.environ.get("NEWS_ALERT_REMOTE", "gdrive:pipeline-data/market-data/news-alert")
CHUNG = ["watchlist.csv", "config.json"]                     # file dung chung laptop / Actions / app online
TRANG_THAI = ["da_gui.json", "lich_su.csv", "trang_thai_email.json"]   # trang thai kenh email (Actions ghi, app doc)
CFG_MAC_DINH = {"toast_bat": True, "email_bat": False, "email_gui_den": "", "smtp_user": "", "smtp_host": "smtp.gmail.com",
                "smtp_port": 465, "gio_bat_dau": 7, "gio_ket_thuc": 22, "chi_bao_tin_moi_trong_gio": 12,
                "toi_da_toast_le": 4, "tom_tat_email_gio": 17}


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def _ghi_log_file():
    """pythonw (Task Scheduler, khong cua so) khong co stdout -> ghi vao logs\\alert.log (cat bot khi > 1 MB)."""
    os.makedirs(LOGS, exist_ok=True)
    p = os.path.join(LOGS, "alert.log")
    if os.path.exists(p) and os.path.getsize(p) > 1_000_000:
        with open(p, encoding="utf-8", errors="replace") as f:
            duoi = f.read()[-200_000:]
        with open(p, "w", encoding="utf-8") as f:
            f.write(duoi)
    f = open(p, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = f


def doc_cfg() -> dict:
    cfg = dict(CFG_MAC_DINH)
    try:
        cfg.update(json.load(open(CONFIG, encoding="utf-8")))
    except Exception:  # noqa: BLE001
        pass
    return cfg


def ghi_cfg(cfg: dict) -> bool:
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return day_len("config.json")


# ---------------- Google Drive (rclone) ----------------
def _rclone() -> list[str] | None:
    if not REMOTE:
        return None
    exe = os.environ.get("RCLONE") or shutil.which("rclone")
    if not exe and os.name == "nt":
        import glob
        g = glob.glob(os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "WinGet", "Packages",
                                   "Rclone.Rclone*", "rclone-*", "rclone.exe"))
        exe = g[0] if g else None
    if not exe:
        return None
    cmd = [exe]
    conf = os.environ.get("RCLONE_CONFIG")
    if not conf:                                             # laptop: rclone.conf that (khong phai ban ao MSIX trong %APPDATA%)
        c = os.path.join(os.path.expanduser("~"), ".config", "rclone", "rclone.conf")
        conf = c if os.path.exists(c) else None
    if conf:
        cmd += ["--config", conf]
    return cmd


def _chay_rclone(args: list[str], timeout: int = 60) -> bool:
    rc = _rclone()
    if not rc:
        return False
    try:
        r = subprocess.run(rc + args, capture_output=True, text=True, timeout=timeout,
                           creationflags=NO_WINDOW if os.name == "nt" else 0)
        if r.returncode != 0:
            log(f"  ! rclone {args[0]}: {(r.stderr or '').strip()[-200:]}")
        return r.returncode == 0
    except Exception as e:  # noqa: BLE001
        log(f"  ! rclone {args[0]}: {type(e).__name__}: {e}")
        return False


def keo_ve(trang_thai: bool = False) -> bool:
    """Drive -> BASE: watchlist.csv + config.json (+ da_gui.json, lich_su.csv, tom_tat/ khi trang_thai=True - cho app)."""
    inc = [f"/{x}" for x in CHUNG] + ([f"/{x}" for x in TRANG_THAI] + ["/tom_tat/**"] if trang_thai else [])
    args = ["copy", REMOTE, BASE]
    for i in inc:
        args += ["--include", i]
    return _chay_rclone(args)


def day_len(*ten: str) -> bool:
    """BASE/<ten> -> Drive (file hoac tom_tat/<ngay>.md ...)."""
    ok = True
    for t in ten:
        if os.path.exists(os.path.join(BASE, t)):
            ok &= _chay_rclone(["copyto", os.path.join(BASE, t), f"{REMOTE}/{t.replace(os.sep, '/')}"])
    return ok if _rclone() else False


# ---------------- watchlist ----------------
def doc_watchlist() -> list[dict]:
    if not os.path.exists(WATCHLIST):
        return []
    out = []
    with open(WATCHLIST, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            ma = (r.get("ma") or "").strip().upper()
            if not ma or ma.startswith("#"):
                continue
            ten = [x.strip() for x in (r.get("ten_goi_them") or "").split(";") if x.strip()]
            out.append({"ma": ma, "ten": ten, "ghi_chu": (r.get("ghi_chu") or "").strip()})
    return out


def ghi_watchlist(wl: list[dict]) -> bool:
    """Ghi watchlist.csv + day len Drive (tra True neu da len Drive)."""
    with open(WATCHLIST, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ma", "ten_goi_them", "ghi_chu"])
        for x in wl:
            w.writerow([x["ma"], ";".join(x["ten"]), x["ghi_chu"]])
    return day_len("watchlist.csv")


def lenh_watchlist(cmd: str, mas: list[str]) -> None:
    keo_ve()
    wl = doc_watchlist()
    co = {x["ma"] for x in wl}
    if cmd == "them":
        for m in mas:
            m = m.strip().upper()
            if m and m not in co:
                wl.append({"ma": m, "ten": [], "ghi_chu": ""})
                co.add(m)
    elif cmd == "xoa":
        bo = {m.strip().upper() for m in mas}
        wl = [x for x in wl if x["ma"] not in bo]
    if cmd in ("them", "xoa"):
        print("Da day len Drive" if ghi_watchlist(wl) else "CHI luu local (khong day duoc len Drive)")
    print(f"Watchlist ({len(wl)} ma): " + ", ".join(x["ma"] + (f" [{'; '.join(x['ten'])}]" if x["ten"] else "") for x in wl))


# ---------------- loc tin ----------------
def khop(t, wl: list[dict]):
    """Them cot ma_wl = cac ma watchlist trong bai (cot `ma` cua bo phan loai + ten_goi_them khop nguyen tu trong tieu de/tom tat)."""
    ma_bai = t["ma"].fillna("").map(lambda s: set(str(s).split("|")) - {""})
    text = (t["tieu_de"].fillna("").astype(str) + " \n " + t["tom_tat"].fillna("").astype(str))
    res = [[] for _ in range(len(t))]
    for x in wl:
        hit = ma_bai.map(lambda s, m=x["ma"]: m in s).to_numpy()
        if x["ten"]:
            pat = re.compile(r"(?<!\w)(" + "|".join(re.escape(n) for n in x["ten"]) + r")(?!\w)", re.IGNORECASE)
            hit = hit | text.map(lambda s: bool(pat.search(s))).to_numpy()
        for i in hit.nonzero()[0]:
            res[i].append(x["ma"])
    t = t.copy()
    t["ma_wl"] = ["|".join(r) for r in res]
    return t[t["ma_wl"] != ""]


def _file_kenh(kenh: str) -> tuple[str, str]:
    return (SENT, LICH_SU) if kenh == "email" else (os.path.join(BASE, "da_gui_may.json"), os.path.join(BASE, "lich_su_may.csv"))


def doc_sent(kenh: str = "email") -> dict:
    try:
        return json.load(open(_file_kenh(kenh)[0], encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def ghi_sent(sent: dict, kenh: str) -> None:
    moc = (datetime.now() - timedelta(days=GIU_NGAY)).isoformat()
    sent = {k: v for k, v in sent.items() if v >= moc}
    json.dump(sent, open(_file_kenh(kenh)[0], "w", encoding="utf-8"), ensure_ascii=False, indent=0)


# ---------------- gui ----------------
def gui_toast(tieu_de: str, noi_dung: str, url: str = "", nguon: str = "") -> bool:
    if os.name != "nt":
        return False
    e = lambda s: html.escape(str(s or ""), quote=True)  # noqa: E731
    mo = f' activationType="protocol" launch="{e(url)}"' if url else ""
    nut = (f'<actions><action content="Mở bài" activationType="protocol" arguments="{e(url)}"/></actions>' if url else "")
    xml = (f'<toast{mo}><visual><binding template="ToastGeneric"><text>{e(tieu_de)}</text><text>{e(noi_dung)}</text>'
           f'<text placement="attribution">{e(nguon)}</text></binding></visual>{nut}</toast>')
    fd, p = tempfile.mkstemp(suffix=".xml", prefix="newsalert_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(xml)
    try:
        r = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                            "-File", TOAST_PS1, "-XmlPath", p], capture_output=True, text=True, timeout=30,
                           creationflags=NO_WINDOW)
        if r.returncode != 0:
            log(f"  ! toast loi: {(r.stderr or r.stdout).strip()[:200]}")
        return r.returncode == 0
    finally:
        try:
            os.remove(p)
        except OSError:
            pass


def thieu_email(cfg: dict) -> list[str]:
    """Nhung muc con thieu de gui email (rong = du)."""
    out = []
    if not cfg.get("smtp_user"):
        out.append("Gmail gửi (smtp_user)")
    if not cfg.get("email_gui_den"):
        out.append("Email nhận (email_gui_den)")
    if not os.environ.get("NEWS_ALERT_SMTP_PASS"):
        out.append("mật khẩu ứng dụng Gmail (NEWS_ALERT_SMTP_PASS)")
    return out


LOI_MAIL = ""                                                # loi SMTP gan nhat (app hien cho nguoi dung)


def gui_mail(cfg: dict, tieu: str, body_html: str) -> bool:
    global LOI_MAIL
    mk = os.environ.get("NEWS_ALERT_SMTP_PASS", "")
    user, den = cfg.get("smtp_user", ""), cfg.get("email_gui_den", "")
    thieu = thieu_email(cfg)
    if thieu:
        LOI_MAIL = "Thiếu " + ", ".join(thieu)
        log(f"  ! email: {LOI_MAIL} -> bo qua")
        return False
    mk = "".join(mk.split())                                 # Gmail hien mat khau ung dung dang "abcd efgh ijkl mnop"
    msg = MIMEText(body_html, "html", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = tieu, user, den
    host = cfg.get("smtp_host", "smtp.gmail.com")
    p0 = int(cfg.get("smtp_port", 465))
    loi_ket_noi = []
    # 18/11: Streamlit Cloud cat ket noi SMTP (SMTPServerDisconnected) -> thu 465 SSL roi 587 STARTTLS
    for port in dict.fromkeys([p0, 587 if p0 == 465 else 465]):
        try:
            if port == 465:
                s = smtplib.SMTP_SSL(host, port, timeout=30)
            else:
                s = smtplib.SMTP(host, port, timeout=30)
                s.ehlo()
                s.starttls()
                s.ehlo()
            with s:
                s.login(user, mk)
                s.sendmail(user, [x.strip() for x in den.split(",") if x.strip()], msg.as_string())
            log(f"  email -> {den} (cong {port}): {tieu}")
            LOI_MAIL = ""
            return True
        except smtplib.SMTPAuthenticationError:
            LOI_MAIL = ("Gmail từ chối đăng nhập: sai Gmail gửi hoặc mật khẩu ứng dụng (cần mật khẩu ứng dụng 16 ký tự của "
                        "đúng tài khoản Gmail gửi, không phải mật khẩu Gmail; tài khoản phải bật xác minh 2 bước)")
            log(f"  ! email loi: {LOI_MAIL}")
            return False
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, OSError) as ex:   # mang / cong bi chan -> thu cong kia
            loi_ket_noi.append(f"cổng {port}: {type(ex).__name__} {str(ex)[:80]}".strip())
        except Exception as ex:  # noqa: BLE001
            LOI_MAIL = f"{type(ex).__name__}: {str(ex)[:200]}"
            log(f"  ! email loi: {LOI_MAIL}")
            return False
    LOI_MAIL = ("Máy chủ này không kết nối được Gmail SMTP (" + "; ".join(loi_ket_noi) + "). Streamlit Cloud thường chặn "
                "cổng gửi mail — email tự động do GitHub Actions gửi; thử bằng GitHub → Actions → News Alert → Run workflow "
                "(tick thu), hoặc bấm Gửi thử trên app chạy ở laptop.")
    log(f"  ! email loi: {LOI_MAIL}")
    return False


def gui_thu(t, kenh: str = "ca-hai") -> str:
    """Gui thu 2 tin moi nhat khop watchlist tu bang tin `t` (kho cua app) - KHONG ghi trang thai. Tra thong bao ket qua."""
    cfg = doc_cfg()
    wl = doc_watchlist()
    m = khop(t, wl).sort_values("ngay_gio", ascending=False) if len(t) and wl else t.iloc[0:0]
    if m.empty:
        return "Chưa có tin nào khớp watchlist trong kho tin để gửi thử"
    bai = m.head(2).to_dict("records")
    kq = []
    if kenh in ("toast", "ca-hai") and os.name == "nt" and cfg.get("toast_bat", True):
        kq.append("toast: " + ("đã hiện" if gui_toast(f"📰 {bai[0]['ma_wl'].replace('|', ', ')} (thử)", bai[0]["tieu_de"],
                                                      bai[0]["url"], str(bai[0]["nguon"])) else "lỗi"))
    if kenh in ("email", "ca-hai"):
        kq.append("email: " + ("đã gửi tới " + cfg.get("email_gui_den", "") if gui_email_tin(cfg, bai, thu=True) else LOI_MAIL))
    return " · ".join(kq) or "Không có kênh nào để thử"


def _the_bai(b: dict) -> str:
    tt = html.escape(str(b.get("tom_tat") or "")[:300])
    loai = html.escape(str(b.get("loai_tin") or "").replace("|", ", "))
    sn = int(b.get("so_nguon") or 1)
    return (f'<tr><td style="padding:8px 10px;border-bottom:1px solid #eee;vertical-align:top;white-space:nowrap">'
            f'<b>{html.escape(b["ma_wl"].replace("|", ", "))}</b><br><span style="color:#888;font-size:12px">'
            f'{b["ngay_gio"]:%d/%m %H:%M}</span></td>'
            f'<td style="padding:8px 10px;border-bottom:1px solid #eee"><a href="{html.escape(b["url"])}" '
            f'style="font-weight:600;color:#1a56db;text-decoration:none">{html.escape(b["tieu_de"])}</a><br>'
            f'<span style="color:#666;font-size:12px">{html.escape(str(b["nguon"]))}{f" · {sn} báo" if sn > 1 else ""}'
            f'{" · " + loai if loai else ""}</span><div style="color:#333;font-size:13px;margin-top:4px">{tt}</div></td></tr>')


def gui_email_tin(cfg: dict, bai: list[dict], thu: bool = False) -> bool:
    ma = sorted({m for b in bai for m in b["ma_wl"].split("|")})
    tieu = f"[Tin watchlist] {', '.join(ma)} - {len(bai)} tin" + (" (THU)" if thu else "")
    body = (f'<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px"><p>{len(bai)} tin mới về watchlist '
            f'({", ".join(ma)}):</p><table style="border-collapse:collapse;width:100%">{"".join(_the_bai(b) for b in bai)}</table>'
            f'<p style="color:#999;font-size:11px">news-alert · sửa watchlist: app Market Data › Tin tức › Watchlist</p></div>')
    return gui_mail(cfg, tieu, body)


def bao(cfg: dict, bai: list[dict], kenh: str, thu: bool = False) -> bool:
    ok = False
    if kenh in ("toast", "ca-hai") and cfg.get("toast_bat", True):
        n_le = int(cfg.get("toi_da_toast_le", 4))
        if len(bai) <= n_le:
            for b in bai:
                sn = int(b.get("so_nguon") or 1)
                ok |= gui_toast(f"📰 {b['ma_wl'].replace('|', ', ')} · {b['ngay_gio']:%H:%M}", b["tieu_de"], b["url"],
                                str(b["nguon"]) + (f" · {sn} báo" if sn > 1 else ""))
        else:
            ma = sorted({m for b in bai for m in b["ma_wl"].split("|")})
            ok |= gui_toast(f"📰 {len(bai)} tin mới: {', '.join(ma)}", " · ".join(b["tieu_de"][:70] for b in bai[:3]) + " …",
                            bai[0]["url"], "Xem đủ trong app › Tin tức › Watchlist")
    if kenh in ("email", "ca-hai") and cfg.get("email_bat", False):
        ok |= gui_email_tin(cfg, bai, thu)
    return ok


def _email_tom_tat(cfg: dict, now: datetime) -> None:
    """Kenh email: sau gio cfg.tom_tat_email_gio, moi ngay 1 lan -> Sonnet tom tat tin watchlist hom nay + gui email."""
    gio = cfg.get("tom_tat_email_gio")
    if gio in (None, "", False) or not cfg.get("email_bat") or now.hour < int(gio):
        return
    ngay = now.strftime("%Y-%m-%d")
    co = os.path.join(TOM_TAT, f"{ngay}.emailed")
    if os.path.exists(co):
        return
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log("Tom tat cuoi ngay: chua co ANTHROPIC_API_KEY -> bo qua")
        return
    import tom_tat as tt
    try:
        kq = tt.tom_tat(ngay)
    except RuntimeError as e:
        log(f"Tom tat cuoi ngay: {e}")
        if "Không có tin" in str(e):                          # ngay khong co tin: danh dau, khong goi lai
            os.makedirs(TOM_TAT, exist_ok=True)
            open(co, "w").close()
            day_len(os.path.join("tom_tat", f"{ngay}.emailed"))
        return
    body = (f'<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;max-width:760px">'
            f'{tt.md_html(kq["text"])}<hr><p style="font-size:12px;color:#666"><b>Nguồn ({kq["so_tin"]} tin)</b><br>'
            f'{tt.md_html(kq["nguon"])}</p><p style="color:#999;font-size:11px">{kq["model"]} · {kq["luc"][11:16]}</p></div>')
    if gui_mail(cfg, f"[Tóm tắt watchlist {now:%d/%m}] {', '.join(kq['ma'])}", body):
        open(co, "w").close()
        day_len(os.path.join("tom_tat", f"{ngay}.emailed"))


# ---------------- chay ----------------
def chay(keo: bool = True, thu: bool = False, kenh: str = "ca-hai") -> int:
    import pandas as pd
    import newslib as nl
    keo_ve()
    cfg = doc_cfg()
    wl = doc_watchlist()
    if not wl:
        log("Watchlist rong -> them ma o app (Tin tuc › Watchlist) hoac: python news_alert.py them HPG")
        return 0
    nl.set_data_dir(KHO)
    if keo:
        import fetch_rss
        try:
            kq = fetch_rss.run(keep_days=GIU_NGAY)
            log(f"Keo RSS: {kq.get('moi', 0)} bai moi · feed loi {kq.get('feed_loi', 0)}/{kq.get('so_feed', 0)}")
        except RuntimeError as ex:
            log(f"X keo RSS loi: {ex}")
            return 2
    if not os.path.exists(nl.TAGGED):
        log("Chua co kho tin")
        return 2
    t = pd.read_parquet(nl.TAGGED)
    m = khop(t, wl).sort_values("ngay_gio", ascending=False)
    if thu:
        if m.empty:
            log("--thu: chua co bai nao khop watchlist trong kho")
            gui_toast("📰 News Alert (thử)", "Thông báo đang hoạt động. Chưa có tin khớp watchlist.", "", "news-alert")
            return 0
        b = m.head(2).to_dict("records")
        log(f"--thu: gui {len(b)} bai moi nhat khop watchlist qua kenh {kenh}")
        bao(cfg, b, kenh, thu=True)
        return 0
    now = datetime.now(nl.VN_TZ).replace(tzinfo=None)
    if not (int(cfg.get("gio_bat_dau", 7)) <= now.hour < int(cfg.get("gio_ket_thuc", 22))):
        log(f"Gio im lang ({now:%H:%M}) -> giu tin, bao vao gio sau")
        return 0
    m = m[m["ngay_gio"] >= now - timedelta(hours=float(cfg.get("chi_bao_tin_moi_trong_gio", 12)))]
    sent = doc_sent(kenh)
    moi = m[~m["id"].isin(set(sent)) & ~m["nhom_trung"].fillna("").map(lambda k: bool(k) and ("g:" + k) in sent)]
    moi = moi.drop_duplicates("nhom_trung", keep="last")                     # tin trung nhieu bao: 1 lan
    log(f"[{kenh}] Watchlist {len(wl)} ma · {len(m)} bai khop trong cua so · {len(moi)} bai CHUA bao")
    with open(os.path.join(BASE, f"trang_thai_{kenh}.json"), "w", encoding="utf-8") as f:
        json.dump({"luc": datetime.now().isoformat(timespec="seconds"), "so_ma": len(wl), "khop": int(len(m)),
                   "moi": int(len(moi)), "so_bai_kho": int(len(t))}, f, ensure_ascii=False)
    if len(moi):
        bai = moi.sort_values("ngay_gio").to_dict("records")
        if bao(cfg, bai, kenh):
            luc = datetime.now().isoformat(timespec="seconds")
            for b in bai:
                sent[b["id"]] = luc
                if b.get("nhom_trung"):
                    sent["g:" + b["nhom_trung"]] = luc
            ghi_sent(sent, kenh)
            ls = pd.DataFrame(bai)[["ngay_gio", "ma_wl", "nguon", "tieu_de", "url", "loai_tin", "so_nguon"]].assign(bao_luc=luc)
            p_ls = _file_kenh(kenh)[1]
            ls.to_csv(p_ls, mode="a", header=not os.path.exists(p_ls), index=False, encoding="utf-8-sig")
            for b in bai:
                log(f"  -> [{b['ma_wl']}] {b['nguon']}: {b['tieu_de'][:90]}")
        else:
            log("X khong kenh nao gui duoc -> de lan sau bao lai")
    if kenh in ("email", "ca-hai"):
        _email_tom_tat(cfg, now)
    return 0


def main():
    if sys.stdout is None or "--log" in sys.argv:
        _ghi_log_file()
    else:
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("lenh", nargs="?", choices=["chay", "ds", "them", "xoa"], default="chay")
    ap.add_argument("ma", nargs="*")
    ap.add_argument("--kenh", choices=["toast", "email", "ca-hai"], default="ca-hai")
    ap.add_argument("--thu", action="store_true")
    ap.add_argument("--khong-keo", action="store_true")
    ap.add_argument("--log", action="store_true")
    a = ap.parse_args()
    if a.lenh in ("ds", "them", "xoa"):
        lenh_watchlist(a.lenh, a.ma)
        return
    try:
        sys.exit(chay(not a.khong_keo, a.thu, a.kenh))
    except Exception as ex:  # noqa: BLE001
        import traceback
        log(f"X LOI: {type(ex).__name__}: {ex}\n{traceback.format_exc()}")
        sys.exit(1)


if __name__ == "__main__":
    main()
