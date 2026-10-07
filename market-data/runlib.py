# -*- coding: utf-8 -*-
"""runlib.py — LOI RUNNER DUNG CHUNG cho run_slot.py cua 3 hub (D:\\market-data, D:\\shipping), viet 07/10/2026.

Tai hien dung logic cua Run-Market.ps1 / Run-Shipping.ps1 bang Python de cung 1 code chay duoc tren Windows
(Task Scheduler) lan Linux (cron tren Oracle ARM). 2 file .ps1 goc GIU NGUYEN, 4 task Task Scheduler van goi ps1
cho toi khi chuyen sang cloud; run_slot.py chi la ban thay the tuong duong.

Cach dung (xem run_slot.py cua tung hub):
    from runlib import Step, Runner, MD_ROOT, SHIP_ROOT, BCTC_ROOT, IS_WIN
    steps = [Step(slot="AM", name="valuation-vn", script="market-valuation/run_daily.py", when=True, critical=True), ...]
    Runner(root=HUB, prefix="market", title="Market Data", default_match=..., with_stale=True, alert=True).run(steps, slot, only)

Gi giu y het ps1:
  - Thu tu buoc, dieu kien When (thu Hai / thu Bay / ngay <= 7), --only bo qua When, buoc loi KHONG chan buoc sau
  - Retry / RetryWait, Critical -> trang thai FAIL, Stale -> goi stale_check.py, loc dong output theo regex Match
    (PowerShell -match khong phan biet hoa/thuong -> re.IGNORECASE)
  - status-<Slot>.txt + logs/<prefix>_<Slot>_<stamp>.log cung dinh dang (UTF-8 BOM, [time] [LEVEL] msg)
  - don log giu 60 file; market: xoa *_*.txt trong logs/ cu hon 2 ngay
Khac ps1:
  - Canh bao: notify() gui Telegram neu co env TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID; khong co env va dang o Windows
    -> popup MessageBox nhu cu (tien trinh rieng, khong chan runner); Linux khong env -> chi ghi log WARN.
  - Step(windows_only=True) (nganh-ck: Excel COM) -> tren Linux bo qua + ghi log, khong tinh la loi.
  - Step(kind="ps1") (alibra run.ps1): Windows goi powershell.exe; Linux goi pwsh neu co, khong thi chay fallback_py.
  - --skip a,b / env CLOUD_SKIP (cloud-deploy 07/10/2026): bo qua buoc chay o may khac (cloud bo cvhcm, cvhcm-berthmap,
    nganh-ck, bonds; laptop chay chung). select_steps() = cung luat chon buoc, dung cho cloud-deploy/sync_data.py.
Bien moi truong: MD_ROOT (D:\\market-data), SHIP_ROOT (D:\\shipping), BCTC_ROOT (D:\\bctc), HAH_DIR (D:\\Database\\Logistics\\HAH).
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

IS_WIN = os.name == "nt"
MD_ROOT = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))
SHIP_ROOT = os.path.normpath(os.environ.get("SHIP_ROOT", "D:/shipping"))
BCTC_ROOT = os.path.normpath(os.environ.get("BCTC_ROOT", "D:/bctc"))
HAH_DIR = os.path.normpath(os.environ.get("HAH_DIR", "D:/Database/Logistics/HAH"))
PYTHON = sys.executable or "python"

# env cho tien trinh con (giong $env:... trong ps1)
CHILD_ENV = dict(os.environ)
CHILD_ENV.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
                  "VNSTOCK_DISABLE_AGENT_SETUP": "1",   # vnai >= 2.6 tu ghi ~/.claude/CLAUDE.md + AGENTS.md khi import vnstock -> tat
                  "MD_ROOT": MD_ROOT, "SHIP_ROOT": SHIP_ROOT, "BCTC_ROOT": BCTC_ROOT, "HAH_DIR": HAH_DIR})


@dataclass
class Step:
    slot: str                       # 'AM' | 'PM'
    name: str
    script: str                     # duong dan .py (tuong doi root cua hub hoac tuyet doi)
    workdir: str = ""               # tuong doi root hoac tuyet doi; "" -> thu muc chua script
    when: bool = True               # dieu kien lich (thu Hai/thu Bay/...); --only bo qua
    retry: int = 1
    retry_wait: int = 60            # giay
    critical: bool = False          # loi -> trang thai FAIL + canh bao
    stale: dict | None = None       # {"file": ..., "days": N, "groups": [...]} -> stale_check.py
    match: str | None = None        # regex loc dong stdout ghi vao log (None -> default_match cua Runner)
    extra_args: tuple = ()
    kind: str = "py"                # 'py' | 'ps1'
    windows_only: bool = False      # Excel COM...: Linux bo qua + log
    fallback_py: tuple = ()         # kind='ps1' tren Linux khong co pwsh: chay lan luot cac .py nay (tuong doi root)
    note: str = ""


def notify(title: str, body: str, logger=None) -> str:
    """Canh bao: Telegram (env TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) > popup Windows > chi log. Tra ve kenh da dung."""
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if tok and chat:
        try:
            data = urllib.parse.urlencode({"chat_id": chat, "text": f"{title}\n{body}"}).encode()
            with urllib.request.urlopen(f"https://api.telegram.org/bot{tok}/sendMessage", data=data, timeout=20) as r:
                ok = json.loads(r.read().decode("utf-8", "replace")).get("ok")
            if ok:
                return "telegram"
            if logger:
                logger("Telegram tra ve ok=false", "WARN")
        except Exception as e:                                    # noqa: BLE001
            if logger:
                logger(f"Telegram loi: {e}", "WARN")
    if IS_WIN:
        try:
            code = "import ctypes, sys; ctypes.windll.user32.MessageBoxW(0, sys.argv[2], sys.argv[1], 0x10)"
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            subprocess.Popen([PYTHON, "-c", code, title, body], creationflags=flags,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "popup"
        except Exception as e:                                    # noqa: BLE001
            if logger:
                logger(f"popup loi: {e}", "WARN")
    if logger:
        logger(f"CANH BAO (khong co kenh gui): {title} | {body.replace(chr(10), ' / ')}", "WARN")
    return "log"


class Runner:
    def __init__(self, root: str, prefix: str, title: str, slot: str, default_match: str,
                 with_stale: bool = False, alert: bool = False, clean_txt: bool = False,
                 stale_script: str | None = None):
        self.root = os.path.normpath(root)
        self.prefix, self.title, self.slot = prefix, title, slot
        self.default_match = default_match
        self.with_stale, self.alert, self.clean_txt = with_stale, alert, clean_txt
        self.stale_script = stale_script or os.path.join(MD_ROOT, "stale_check.py")
        self.log_dir = os.path.join(self.root, "logs")
        self.stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(self.log_dir, f"{prefix}_{slot}_{self.stamp}.log")
        self.status_file = os.path.join(self.root, f"status-{slot}.txt")
        self.today = dt.datetime.now()
        self.dry_run = False
        os.makedirs(self.log_dir, exist_ok=True)

    # ------------------------------------------------------------------ log
    def log(self, msg: str, level: str = "INFO") -> None:
        line = f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] [{level}] {msg}"
        print(line, flush=True)
        if self.dry_run:
            return
        try:
            new = not os.path.exists(self.log_file)
            with open(self.log_file, "a", encoding="utf-8-sig" if new else "utf-8") as f:   # BOM nhu Add-Content -Encoding utf8
                f.write(line + "\n")
        except Exception:                                         # noqa: BLE001
            pass

    # ------------------------------------------------------------------ duong dan
    def abspath(self, p: str) -> str:
        return os.path.normpath(p if os.path.isabs(p) else os.path.join(self.root, p))

    # ------------------------------------------------------------------ chay 1 lenh, bat output ra file (nhu Start-Process -Redirect*)
    def _run_capture(self, name: str, cmd: list, workdir: str, match: str) -> int:
        so = os.path.join(self.log_dir, f"out_{self.stamp}_{name}.txt")
        se = os.path.join(self.log_dir, f"err_{self.stamp}_{name}.txt")
        try:
            with open(so, "wb") as fo, open(se, "wb") as fe:
                code = subprocess.call(cmd, cwd=workdir, stdout=fo, stderr=fe, stdin=subprocess.DEVNULL, env=CHILD_ENV)
            rx = re.compile(match, re.IGNORECASE)
            if os.path.exists(so):
                for t in open(so, encoding="utf-8-sig", errors="replace").read().splitlines():
                    if rx.search(t):
                        self.log(f"  {t}")
            if code != 0 and os.path.exists(se):
                for t in open(se, encoding="utf-8-sig", errors="replace").read().splitlines()[-8:]:
                    if t.strip():
                        self.log(f"  {t}", "WARN")
            return code
        except Exception as e:                                    # noqa: BLE001
            self.log(f"{name} ngoai le: {e}", "ERROR")
            return 999
        finally:
            for p in (so, se):
                try:
                    os.remove(p)
                except OSError:
                    pass

    def _cmd_for(self, s: Step) -> list | None:
        script = self.abspath(s.script)
        if s.kind == "ps1":
            if IS_WIN:
                return ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, *s.extra_args]
            if shutil.which("pwsh"):
                return ["pwsh", "-NoProfile", "-File", script, *s.extra_args]
            return None
        return [PYTHON, script, *s.extra_args]

    def run_step(self, s: Step) -> bool:
        self.log(f"----- {s.name} -----")
        match = s.match or self.default_match
        work = self.abspath(s.workdir) if s.workdir else os.path.dirname(self.abspath(s.script))
        t0 = time.time()
        code = 999
        for i in range(1, max(1, s.retry) + 1):
            cmd = self._cmd_for(s)
            if cmd is None:                                       # ps1 tren Linux khong co pwsh
                if s.fallback_py:
                    code = 0
                    for fp in s.fallback_py:
                        self.log(f"  (Linux, khong co pwsh) chay {fp}")
                        code = self._run_capture(s.name, [PYTHON, self.abspath(fp)], os.path.dirname(self.abspath(fp)), match)
                        if code != 0:
                            break
                else:
                    self.log(f"{s.name}: bo qua (script .ps1, khong co pwsh tren may nay)", "WARN")
                    code = 0
            else:
                code = self._run_capture(s.name, cmd, work, match)
            if code == 0:
                break
            self.log(f"{s.name} exit {code} (lan {i}/{s.retry})", "WARN")
            if i < s.retry:
                time.sleep(s.retry_wait)
        res = "OK" if code == 0 else f"FAIL exit {code}"
        self.log(f"{s.name} : {res} [{time.time() - t0:,.0f}s]")
        return code == 0

    def check_stale(self, s: Step) -> str:
        st = s.stale or {}
        file = self.abspath(st.get("file", ""))
        if not os.path.exists(file):
            return f"STALE|khong thay {st.get('file')}"
        cmd = [PYTHON, self.stale_script, file, str(st.get("days", 7)), *[str(g) for g in st.get("groups", [])]]
        try:
            p = subprocess.run(cmd, capture_output=True, env=CHILD_ENV, timeout=600)
            lines = [t for t in p.stdout.decode("utf-8", "replace").splitlines() if t.strip()]
            out = lines[-1].strip() if lines else ""
        except Exception:                                         # noqa: BLE001
            out = ""
        return out or "STALE|probe khong chay duoc"

    # ------------------------------------------------------------------ vong chinh (y het ps1)
    def run(self, steps: list, only: list | None = None, dry_run: bool = False, skip: list | None = None) -> str:
        only = [o for o in (only or []) if o]
        skip = skip_set(skip)
        self.dry_run = dry_run
        self.log(f"===== BAT DAU {self.title} [{self.slot}] =====")
        if skip:
            self.log(f"bo qua theo --skip/CLOUD_SKIP: {','.join(sorted(skip))}")
        fails, stales, crit_fail = [], [], False
        for s in steps:
            if s.slot != self.slot:
                continue
            if only and s.name not in only:
                continue
            if not s.when and not only:
                self.log(f"{s.name}: bo qua (khong dung lich)")
                continue
            if s.windows_only and not IS_WIN:
                self.log(f"{s.name}: bo qua (chi chay tren Windows - Excel COM){' - ' + s.note if s.note else ''}")
                continue
            if s.name in skip:
                self.log(f"{s.name}: bo qua (--skip/CLOUD_SKIP - buoc nay chay o may khac)")
                continue
            if dry_run:
                self.log(f"{s.name}: SE CHAY {self.abspath(s.script)} {' '.join(s.extra_args)}".rstrip())
                continue
            ok = self.run_step(s)
            if not ok:
                fails.append(s.name)
                if s.critical:
                    crit_fail = True
            if s.stale:
                probe = self.check_stale(s)
                self.log(f"  do tuoi: {probe}")
                if probe.startswith("STALE|"):
                    stales.append(f"{s.name}: {probe.split('|')[1]}")
        if crit_fail:
            state = "FAIL"
        elif stales:
            state = "STALE"
        elif fails:
            state = "WARN"
        else:
            state = "OK"
        now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        if self.with_stale:
            status = f"{state} | {now} | loi: {','.join(fails)} | cu: {'; '.join(stales)}"
            end = f"{state} | loi: {','.join(fails)} | cu: {'; '.join(stales)}"
        else:
            status = f"{state} | {now} | loi: {','.join(fails)}"
            end = f"{state} {','.join(fails)}"
        if not dry_run:
            with open(self.status_file, "wb") as f:                # Set-Content -Encoding utf8: BOM + CRLF
                f.write((status + "\r\n").encode("utf-8-sig"))
        self.log(f"===== KET THUC [{self.slot}]: {end} =====")
        if self.alert and (crit_fail or stales) and not dry_run:
            ch = notify(f"{self.title} {self.slot} - {state}",
                        f"Loi: {', '.join(fails)}\nDu lieu cu: {'; '.join(stales)}\n\nLog: {self.log_file}", self.log)
            self.log(f"canh bao qua: {ch}")
        self.cleanup()
        return state

    def cleanup(self) -> None:
        """Giu 60 log moi nhat; market: xoa *_*.txt (out_/err_/probe_ sot lai) cu hon 2 ngay."""
        logs = sorted(glob.glob(os.path.join(self.log_dir, f"{self.prefix}_*.log")), key=os.path.getmtime, reverse=True)
        for p in logs[60:]:
            try:
                os.remove(p)
            except OSError:
                pass
        if self.clean_txt:
            cutoff = time.time() - 2 * 86400
            for p in glob.glob(os.path.join(self.log_dir, "*_*.txt")):
                try:
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
                except OSError:
                    pass


def skip_set(skip=None) -> set:
    """Tap buoc bi bo qua = --skip a,b + env CLOUD_SKIP (cloud-deploy: cvhcm,cvhcm-berthmap,nganh-ck,bonds chay o laptop)."""
    out = set()
    for src in (skip or [], os.environ.get("CLOUD_SKIP", "").split(",")):
        out.update(x.strip() for x in src if x and x.strip())
    return out


def select_steps(steps: list, slot: str, only=None, skip=None, is_win: bool | None = None) -> list:
    """Danh sach Step SE CHAY hom nay theo dung luat cua Runner.run (slot, --only bo qua When, windows_only, skip).
    Dung chung cho runner va cloud-deploy/sync_data.py (chon thu muc du lieu can dong bo)."""
    only = [o for o in (only or []) if o]
    skip = skip_set(skip)
    win = IS_WIN if is_win is None else is_win
    out = []
    for s in steps:
        if s.slot != slot or (only and s.name not in only) or (not s.when and not only):
            continue
        if (s.windows_only and not win) or s.name in skip:
            continue
        out.append(s)
    return out


def parse_args(default_slot: str, argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Runner Python thay Run-*.ps1 (cung bang buoc).")
    ap.add_argument("--slot", choices=["AM", "PM"], default=default_slot)
    ap.add_argument("--only", default="", help="chi chay cac buoc nay, cach nhau boi dau phay (bo qua dieu kien lich)")
    ap.add_argument("--skip", default="", help="bo qua cac buoc nay (cong them env CLOUD_SKIP), vd cvhcm,nganh-ck")
    ap.add_argument("--dry-run", action="store_true", help="chi liet ke buoc se chay, khong chay")
    a = ap.parse_args(argv)
    a.only = [x.strip() for x in a.only.split(",") if x.strip()]
    a.skip = [x.strip() for x in a.skip.split(",") if x.strip()]
    return a
