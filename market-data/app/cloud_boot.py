# -*- coding: utf-8 -*-
r"""
cloud_boot.py - khoi dong app Market Data tren STREAMLIT COMMUNITY CLOUD (12/10/2026).

Tren cloud khong co o D:\ va khong co rclone san, du lieu pipeline nam tren Google Drive (gdrive:pipeline-data/market-data/...,
xem D:\cloud-deploy\data_manifest.py). Module nay chay DAU app.py (truoc khi import datalib):

  1. Nhan biet cloud: co st.secrets["RCLONE_CONF"] (base64 cua rclone.conf) hoac env STREAMLIT_CLOUD=1, VA thu muc du lieu local
     (MD_ROOT) chua co du lieu that. Khong phai cloud -> boot() tra False, app chay nhu tren laptop.
  2. rclone: Linux tai rclone-current-linux-amd64.zip ve ~/.local/bin (cache theo container); Windows dung ban winget (de test).
     rclone.conf ghi tu secret vao ~/.config/rclone/rclone.conf (chmod 600). rclone_cmd() dung chung cho data_live (realtime/<ngay>).
  3. Keo du lieu app can (APP_DATA, --include tung file) ve DATA_ROOT = MD_ROOT (mac dinh /tmp/pipeline-data/market-data),
     dat env MD_ROOT / SHIP_ROOT / BCTC_ROOT / RT_ROOT / APP_CACHE / SRC_CACHE; chep code phu (bond-pivot/scripts, market-valuation/*.py)
     tu repo vao DATA_ROOT vi datalib import tu do; dung san 2 parquet gia (tv-history 237 MB -> parquet) de trang dau mo nhanh.
     Lan dau hien st.status tien do; ghi marker .cloud_boot.json de rerun / phien khac khong keo lai.
  4. Thread nen moi 30 phut: rclone copy lai (chi file doi) + dung lai parquet neu tv-history.csv moi.

Chay tay (khong can streamlit):  STREAMLIT_CLOUD=1 RCLONE_CONF=<base64> MD_ROOT=<thu muc trong> python cloud_boot.py --pull
"""
from __future__ import annotations

import base64
import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_MD = os.path.dirname(APP_DIR)                     # <repo>/market-data: code cac buoc (bond-pivot/scripts, market-valuation, realtime-lab)
REMOTE = os.environ.get("RCLONE_REMOTE", "gdrive:pipeline-data")
HUB = "market-data"
RCLONE_URL = "https://downloads.rclone.org/rclone-current-linux-amd64.zip"
WINGET_RCLONE = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "WinGet", "Packages",
                             "Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe", "rclone-v1.75.1-windows-amd64", "rclone.exe")
HOME = os.path.expanduser("~")
BIN_DIR = os.path.join(HOME, ".local", "bin")
CONF_PATH = os.path.join(HOME, ".config", "rclone", "rclone.conf")
MARKER = ".cloud_boot.json"
REFRESH_SEC = int(os.environ.get("CLOUD_REFRESH_SEC", "1800"))
DEFAULT_ROOT = ("/tmp/pipeline-data/market-data" if os.name != "nt"
                else os.path.join(tempfile.gettempdir(), "pipeline-data", "market-data"))

# (thu muc tren Drive gdrive:pipeline-data/market-data/<thu muc>, cac file app doc - rclone --include, '/' = goc thu muc)
# Chi dung cac file datalib/data_ext/data_src doc; KHONG keo raw/vci_foreign (440 MB), reports/, monthly-reports/, history/...
APP_DATA = [
    ("index-fetcher", ["/indices-master.csv", "/flows-master.csv", "/fx-master.csv", "/tv-history.csv", "/indices.csv",
                       "/raw/vn_screener_meta.csv", "/raw/vn_icb_vci.csv", "/raw/vn_foreign_stocks_vci.parquet",
                       "/raw/vn_prop_stocks.csv", "/raw/vn_foreign_stocks_*.csv"]),
    ("market-valuation", ["/valuation-wide.csv", "/valuation-adjusted.csv", "/sectors-wide.csv", "/stocks-wide.csv",
                          "/shares-master.csv", "/valuation-region-wide.csv", "/market-eps.csv", "/nhom-loai.txt"]),
    ("transmission-fetcher", ["/transmission-master.csv", "/transmission-wide.csv"]),
    ("nso-fetcher", ["/nso_master.csv", "/nso_monthly_master.csv", "/nso_catalog.csv"]),
    ("macro-fetcher", ["/macro_vn_master.csv", "/macro_region_master.csv"]),
    ("vsdc-accounts", ["/vsdc_tk_ndt.csv"]),
    ("bond-pivot", ["/data/processed/**"]),
    # hub khac: "<hub>/<thu muc>" -> gdrive:pipeline-data/<hub>/<thu muc> -> <base>/<hub>/<thu muc> (BCTC_ROOT = <base>/bctc)
    ("bctc/bctc-scan", ["/data/bctc_congbo.csv"]),                         # 13/10/2026: BCTC moi cong bo -> tab Tin tuc
]
OTHER_HUBS = ("bctc", "shipping", "hah")
APP_CACHE_REMOTE = "app-cache/src"      # gdrive:pipeline-data/market-data/app-cache/src = cache\\src cua app laptop (stock_daily...)
# code trong repo ma datalib import theo duong dan DU LIEU (MD_ROOT/...): chep sang DATA_ROOT
CODE_DIRS = [("bond-pivot/scripts", "*.py"), ("market-valuation", "*.py")]
RCLONE_COMMON = ["--fast-list", "--transfers", "16", "--checkers", "32", "--retries", "3", "--low-level-retries", "10",
                 "--stats-one-line", "--stats", "30s", "-q"]

_LOCK = threading.RLock()        # 12/10/2026: RLock - boot() giu khoa roi goi rclone_path() cung xin khoa -> Lock thuong deadlock tren Linux
_STATE: dict = {"cloud": None, "booted": False, "thread": None, "last_pull": None, "pulls": 0, "error": None, "mb": 0.0}


def _log(msg: str) -> None:
    print(f"[cloud_boot] {time.strftime('%H:%M:%S')} {msg}", flush=True)


# ------------------------------------------------------------------------------------------------ nhan biet
def _secret(name: str) -> str | None:
    """st.secrets[name] (secrets.toml) -> env name -> None. Khong bao gio in gia tri."""
    try:
        import streamlit as st
        v = st.secrets.get(name)              # noqa: SIM105 - khong co file secrets -> exception
        if v:
            return str(v)
    except Exception:  # noqa: BLE001
        pass
    v = os.environ.get(name)
    return v or None


def data_root() -> str:
    return os.path.normpath(os.environ.get("MD_ROOT") or DEFAULT_ROOT)


def _has_local_data(root: str) -> bool:
    """Thu muc da co du lieu that (laptop) -> khong duoc keo de len; du lieu do chinh cloud_boot keo ve (co marker) thi khong tinh."""
    return (os.path.exists(os.path.join(root, "index-fetcher", "indices-master.csv"))
            and not os.path.exists(os.path.join(root, MARKER)))


def is_cloud() -> bool:
    """Cloud = (secret RCLONE_CONF hoac env STREAMLIT_CLOUD=1) va MD_ROOT chua co du lieu local. CLOUD_BOOT=0 tat han."""
    if _STATE["cloud"] is not None:
        return _STATE["cloud"]
    if os.environ.get("CLOUD_BOOT") == "0":
        _STATE["cloud"] = False
        return False
    flag = os.environ.get("STREAMLIT_CLOUD") == "1" or bool(_secret("RCLONE_CONF"))
    _STATE["cloud"] = bool(flag) and not _has_local_data(data_root())
    return _STATE["cloud"]


# ------------------------------------------------------------------------------------------------ rclone
def _install_rclone_linux() -> str:
    """Tai rclone-current-linux-amd64.zip -> ~/.local/bin/rclone (chmod 755). Tra duong dan."""
    import urllib.request
    os.makedirs(BIN_DIR, exist_ok=True)
    dst = os.path.join(BIN_DIR, "rclone")
    _log(f"tai rclone {RCLONE_URL}")
    hdr = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) cloud_boot/1.0"}   # 12/10/2026: khong co UA -> 403
    buf = None
    try:
        with urllib.request.urlopen(urllib.request.Request(RCLONE_URL, headers=hdr), timeout=120) as r:
            buf = io.BytesIO(r.read())
    except Exception as e:  # noqa: BLE001 - du phong: GitHub releases (asset linux-amd64.zip cua ban moi nhat)
        _log(f"downloads.rclone.org loi ({type(e).__name__}: {str(e)[:60]}) -> thu GitHub releases")
        api = "https://api.github.com/repos/rclone/rclone/releases/latest"
        with urllib.request.urlopen(urllib.request.Request(api, headers=hdr), timeout=60) as r:
            rel = json.load(r)
        url = next(a["browser_download_url"] for a in rel["assets"] if a["name"].endswith("linux-amd64.zip"))
        _log(f"tai {url}")
        with urllib.request.urlopen(urllib.request.Request(url, headers=hdr), timeout=180) as r:
            buf = io.BytesIO(r.read())
    with zipfile.ZipFile(buf) as z:
        name = next(n for n in z.namelist() if n.endswith("/rclone"))
        with z.open(name) as f, open(dst, "wb") as o:
            shutil.copyfileobj(f, o)
    os.chmod(dst, 0o755)
    return dst


def rclone_path() -> str:
    """Duong dan rclone dung duoc: env RCLONE > PATH > (Windows) ban winget > (Linux) ~/.local/bin/rclone, chua co thi tai."""
    for c in (os.environ.get("RCLONE"), shutil.which("rclone")):
        if c and os.path.exists(c):
            return c
    if os.name == "nt":
        if os.path.exists(WINGET_RCLONE):
            return WINGET_RCLONE
        raise FileNotFoundError("Khong thay rclone.exe (winget install Rclone.Rclone hoac dat env RCLONE)")
    dst = os.path.join(BIN_DIR, "rclone")
    if not os.path.exists(dst):
        with _LOCK:
            if not os.path.exists(dst):
                _install_rclone_linux()
    os.environ["RCLONE"] = dst                 # data_live / sync_data tim rclone qua env RCLONE truoc
    return dst


def rclone_config() -> str | None:
    """rclone.conf: tu secret RCLONE_CONF (base64) -> ~/.config/rclone/rclone.conf (0600); khong co secret -> env RCLONE_CONFIG
    hoac None (rclone tu tim conf mac dinh, vd %APPDATA%\\rclone\\rclone.conf tren laptop)."""
    b64 = _secret("RCLONE_CONF")
    if not b64:
        p = os.environ.get("RCLONE_CONFIG")
        return p if p and os.path.exists(p) else None
    raw = base64.b64decode("".join(b64.split()))
    os.makedirs(os.path.dirname(CONF_PATH), exist_ok=True)
    try:
        cur = open(CONF_PATH, "rb").read()
    except OSError:
        cur = None
    if cur != raw:
        with open(CONF_PATH, "wb") as f:
            f.write(raw)
    try:
        os.chmod(CONF_PATH, 0o600)
    except OSError:
        pass
    os.environ["RCLONE_CONFIG"] = CONF_PATH    # rclone (ke ca goi tu data_live) dung dung file conf nay
    return CONF_PATH


def rclone_cmd(*args: str) -> list[str]:
    """Lenh rclone day du (duong dan + --config) de module khac (data_live keo realtime/<ngay>) dung chung."""
    cmd = [rclone_path()]
    conf = rclone_config()
    if conf:
        cmd += ["--config", conf]
    return cmd + list(args)


def remote(sub: str = "") -> str:
    """gdrive:pipeline-data/market-data[/sub]."""
    return f"{REMOTE}/{HUB}/{sub}" if sub else f"{REMOTE}/{HUB}"


class DriveAuthError(RuntimeError):
    """Token Google Drive cua rclone bi thu hoi/het han (invalid_grant) - can lam moi token + cap nhat secret RCLONE_CONF."""


DRIVE_AUTH_HINT = ("Quyền Google Drive của rclone đã hết hạn (invalid_grant). Trên laptop chạy "
                   "D:\\cloud-deploy\\local\\Lam-moi-token-Drive.ps1, rồi dán chuỗi mới vào secret RCLONE_CONF "
                   "(GitHub Actions + Streamlit Cloud → Settings → Secrets) và Reboot app.")


def run_rclone(args: list[str], timeout: int = 900) -> tuple[int, str]:
    cmd = rclone_cmd(*args) + RCLONE_COMMON
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    out = (r.stdout + r.stderr).strip()
    if r.returncode != 0:
        _log(f"rclone exit {r.returncode}: {out[-400:]}")
        if "invalid_grant" in out or "couldn't fetch token" in out:   # 15/10/2026: OAuth Testing -> token chet sau 7 ngay
            raise DriveAuthError(DRIVE_AUTH_HINT)
    return r.returncode, out


def pull_folder(name: str, includes: list[str], root: str | None = None) -> float:
    """rclone copy 1 thu muc Drive -> DATA_ROOT/<name> chi cac file includes (file khong doi thi rclone tu bo qua). Tra so giay."""
    root = root or data_root()
    hub = name.split("/", 1)[0] if "/" in name else ""
    if hub in OTHER_HUBS:                                 # thu muc cua hub khac (bctc/...): canh MD_ROOT, cung cay <base>/<hub>/...
        dst = os.path.join(os.path.dirname(root), *name.split("/"))
        src = f"{REMOTE}/{name}"
    else:
        dst = os.path.join(root, name)
        src = remote(name)
    os.makedirs(dst, exist_ok=True)
    args = ["copy", src, dst]
    for p in includes:
        args += ["--include", p]
    t0 = time.time()
    rc, _ = run_rclone(args)
    if rc != 0:
        raise RuntimeError(f"rclone copy {name} loi (exit {rc})")
    return time.time() - t0


# ------------------------------------------------------------------------------------------------ du lieu
def _copy_code(root: str) -> None:
    """Chep *.py ma datalib import theo duong dan du lieu (bond-pivot/scripts/yield_curve.py, market-valuation/fetch_valuation.py)."""
    for rel, pat in CODE_DIRS:
        src_dir = os.path.join(REPO_MD, rel)
        if not os.path.isdir(src_dir):
            continue
        dst_dir = os.path.join(root, rel)
        os.makedirs(dst_dir, exist_ok=True)
        for f in glob.glob(os.path.join(src_dir, pat)):
            d = os.path.join(dst_dir, os.path.basename(f))
            if not os.path.exists(d) or os.path.getmtime(d) < os.path.getmtime(f):
                shutil.copy2(f, d)


_VER_RX = re.compile(r"^([A-Za-z_]\w*?)(\.\d{14}(_\d+)?)?\.parquet$")   # <name>.parquet | <name>.<YYYYmmddHHMMSS>[_k].parquet


def _read_status(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _write_status(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=str)
    for i in range(5):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 4:
                raise
            time.sleep(0.2)


def src_current_files(src_dir: str) -> dict:
    """{dataset: ten file parquet HIEN HANH} trong cache\\src (13/10/2026 cache theo phien ban - xem data_src.path): con tro
    status.json[name]['file'] -> `<name>.parquet` cu -> ban moi nhat theo mtime. Khong import data_src (dung duoc cho moi src_dir)."""
    st = _read_status(os.path.join(src_dir, "status.json"))
    names: dict[str, list[str]] = {}
    try:
        for f in os.listdir(src_dir):
            m = _VER_RX.match(f)
            if m:
                names.setdefault(m.group(1), []).append(f)
    except OSError:
        return {}
    for n in st:
        if not n.startswith("_") and n not in names:
            names[n] = []
    out = {}
    for n, fs in names.items():
        f = st.get(n, {}).get("file")
        if f and os.path.exists(os.path.join(src_dir, f)):
            out[n] = f
        elif fs:
            out[n] = max(fs, key=lambda x: (os.path.getmtime(os.path.join(src_dir, x)), x))
    return out


def push_src_cache(src_dir: str) -> float:
    """LAPTOP: day ban parquet HIEN HANH cua tung dataset + status.json len Drive (app-cache/src) de cloud seed (rclone copy, chi file
    doi), roi xoa ban cu tren Drive (13/10/2026: cache theo phien ban nen ten file doi moi lan ghi)."""
    if not os.path.isdir(src_dir):
        return 0.0
    t0 = time.time()
    cur = src_current_files(src_dir)
    if not cur:
        return 0.0
    inc = ["--include", "/status.json"]
    for f in cur.values():
        inc += ["--include", "/" + f]
    rc, _ = run_rclone(["copy", src_dir, remote(APP_CACHE_REMOTE)] + inc, timeout=600)
    if rc != 0:
        raise RuntimeError(f"rclone copy app-cache loi (exit {rc})")
    flt = []
    for f in cur.values():
        flt += ["--filter", "- /" + f]
    flt += ["--filter", "+ /*.parquet", "--filter", "- *", "--min-age", "2h"]   # 13/10: chi xoa ban cu >2h - laptop va job EOD khong xoa file cua nhau
    rc, out = run_rclone(["delete", remote(APP_CACHE_REMOTE)] + flt, timeout=300)   # ban cu tren Drive (khong loi neu khong co)
    if rc not in (0, 3):
        _log(f"xoa ban cu app-cache tren Drive loi (exit {rc}) - bo qua")
    return time.time() - t0


def pull_src_cache(src_dir: str, names: list[str] | None = None, newer_only: bool = False) -> list[str]:
    """CLOUD: keo app-cache/src tu Drive ve SRC_CACHE. Lan dau (names=None): status.json + ban hien hanh moi dataset (theo con tro
    `file` cua status tren Drive; Drive chua co status -> moi *.parquet). Thread nen (names=['stock_daily'], newer_only=True): chi keo
    dataset nang khi ban tren Drive co `last` MOI HON ban local, va chi cap nhat muc status cua dataset do (khong de len muc cua
    dataset cloud tu keo). Tra danh sach file da keo."""
    os.makedirs(src_dir, exist_ok=True)
    tmpd = tempfile.mkdtemp(prefix="srcstat_")
    rst_path = os.path.join(tmpd, "status.json")
    rc, _ = run_rclone(["copyto", remote(APP_CACHE_REMOTE) + "/status.json", rst_path], timeout=120)
    rst = _read_status(rst_path) if rc == 0 else {}
    shutil.rmtree(tmpd, ignore_errors=True)
    if not rst:
        if names is not None:
            return []
        rc, _ = run_rclone(["copy", remote(APP_CACHE_REMOTE), src_dir, "--include", "/*.parquet", "--include", "/status.json"])
        if rc != 0:
            _log("khong keo duoc app-cache/src (chua co tren Drive?) - data_src se keo nen tu nguon")
            return []
        return sorted(f for f in os.listdir(src_dir) if f.endswith(".parquet"))
    lst_path = os.path.join(src_dir, "status.json")
    lst = _read_status(lst_path)
    want = {}
    for n in (names or [k for k in rst if not k.startswith("_")]):
        d = rst.get(n) or {}
        f = d.get("file") or f"{n}.parquet"
        if newer_only:
            lo = (lst.get(n) or {}).get("last") or ""
            lf = (lst.get(n) or {}).get("file") or f"{n}.parquet"
            if os.path.exists(os.path.join(src_dir, lf)) and str(d.get("last") or "") <= str(lo):
                continue
        want[n] = f
    if not want:
        return []
    inc = []
    for f in want.values():
        inc += ["--include", "/" + f]
    rc, _ = run_rclone(["copy", remote(APP_CACHE_REMOTE), src_dir] + inc, timeout=900)
    if rc != 0:
        _log(f"keo app-cache/src loi (exit {rc})")
        return []
    got = [f for f in want.values() if os.path.exists(os.path.join(src_dir, f))]
    if names is None:                                    # lan dau: lay nguyen status Drive (con tro file + ngay cuoi + ghi chu)
        new = {k: v for k, v in rst.items() if not k.startswith("_")}
        new.update({k: v for k, v in lst.items() if k.startswith("_")})
    else:
        new = dict(lst)
        for n, f in want.items():
            if f in got:
                new[n] = dict(rst.get(n) or {})
    _write_status(lst_path, new)
    for n, f in want.items():                            # ban cu cua dataset vua keo (cloud, khong bi khoa) -> xoa
        if f not in got:
            continue
        for x in os.listdir(src_dir):
            m = _VER_RX.match(x)
            if m and m.group(1) == n and x != f:
                try:
                    os.remove(os.path.join(src_dir, x))
                except OSError:
                    pass
    return got


def _set_env(root: str) -> None:
    """Env cho datalib / data_src / data_live truoc khi import."""
    os.environ["MD_ROOT"] = root
    os.environ["SRC_CACHE_PUSH"] = "0"                   # cloud khong day cache nguon nguoc len Drive
    base = os.path.dirname(root)
    os.environ.setdefault("SHIP_ROOT", os.path.join(base, "shipping"))
    os.environ.setdefault("BCTC_ROOT", os.path.join(base, "bctc"))
    rt = os.path.join(REPO_MD, "realtime-lab")          # co symbols.txt (repo); data/<ngay> do data_live keo tu Drive
    os.environ.setdefault("RT_ROOT", rt if os.path.isdir(rt) else os.path.join(root, "realtime-lab"))
    cache = os.path.join(base, "app-cache")              # cache parquet cua app o /tmp (repo mount co the chi doc)
    os.environ.setdefault("APP_CACHE", cache)
    os.environ.setdefault("SRC_CACHE", os.path.join(cache, "src"))
    os.makedirs(os.environ["SRC_CACHE"], exist_ok=True)


def _prebuild_tv(root: str) -> list[str]:
    """Dung san cache/tv-history.parquet + tv-ohlc-vn.parquet tu tv-history.csv (chi khi CSV moi hon). Tra ten file da dung."""
    csv = os.path.join(root, "index-fetcher", "tv-history.csv")
    if not os.path.exists(csv):
        return []
    if APP_DIR not in sys.path:
        sys.path.insert(0, APP_DIR)
    import datalib as dl                                 # noqa: PLC0415 - sau khi env da dat
    import data_ext as dx                                # noqa: PLC0415
    mt = os.path.getmtime(csv)
    done = []
    pq = os.path.join(dl.CACHE, "tv-history.parquet")
    if not (os.path.exists(pq) and os.path.getmtime(pq) >= mt):
        dl.tv_csv_to_parquet(csv, pq)
        done.append("tv-history.parquet")
    pq2 = os.path.join(dl.CACHE, "tv-ohlc-vn.parquet")
    if not (os.path.exists(pq2) and os.path.getmtime(pq2) >= mt):
        dl.tv_csv_to_parquet(csv, pq2, dx.OHLC_COLS, only_vn=True)
        done.append("tv-ohlc-vn.parquet")
    try:                                                 # ban ghep live-first (tv-live.parquet): dung NGAY LUC NAY khi app con it
        stamp = os.path.join(dl.CACHE, "tv-live.stamp")  # du lieu thuong tru (dinh RAM ~+600 MB tam thoi), khong de len trang dau
        before = open(stamp).read() if os.path.exists(stamp) else ""
        dl.tv()
        after = open(stamp).read() if os.path.exists(stamp) else ""
        if after != before:
            done.append("tv-live.parquet")
    except Exception as e:  # noqa: BLE001
        _log(f"tv-live: {type(e).__name__}: {str(e)[:120]}")
    trim_memory()
    return done


def _size_mb(root: str) -> tuple[float, int]:
    tot = n = 0
    for dp, _, fs in os.walk(root):
        for f in fs:
            try:
                tot += os.path.getsize(os.path.join(dp, f))
                n += 1
            except OSError:
                pass
    return tot / 1e6, n


def _marker_path(root: str) -> str:
    return os.path.join(root, MARKER)


def _write_marker(root: str, **kw) -> None:
    kw["time"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(_marker_path(root), "w", encoding="utf-8") as f:
        json.dump(kw, f, ensure_ascii=False, indent=1)


def pull_all(root: str, progress=None, first: bool = False) -> dict:
    """Keo toan bo APP_DATA + chep code (+ lan dau: app-cache/src) + dung parquet. progress(msg) goi tung buoc. Tra thong ke."""
    t0 = time.time()
    rclone_path()
    rclone_config()
    steps = []
    for name, inc in APP_DATA:
        if progress:
            progress(f"Kéo {name} …")
        s = pull_folder(name, inc, root)
        steps.append((name, round(s, 1)))
        _log(f"keo {name}: {s:.1f} s")
    _copy_code(root)
    if first:
        if progress:
            progress("Kéo cache nguồn live-first (app-cache/src) …")
        t1 = time.time()
        got = pull_src_cache(os.environ.get("SRC_CACHE") or os.path.join(os.path.dirname(root), "app-cache", "src"))
        steps.append(("app-cache/src", round(time.time() - t1, 1)))
        _log(f"app-cache/src: {len(got)} file")
    if progress:
        progress("Dựng cache giá (parquet) …")
    built = _prebuild_tv(root)
    mb, n = _size_mb(root)
    info = {"seconds": round(time.time() - t0, 1), "mb": round(mb, 1), "files": n, "steps": steps, "built": built}
    _write_marker(root, **info)
    _STATE.update(last_pull=time.time(), pulls=_STATE["pulls"] + 1, error=None, mb=mb)
    _log(f"xong: {info['seconds']} s, {mb:.0f} MB, {n} file")
    return info


def _refresh_loop(root: str) -> None:
    while True:
        time.sleep(REFRESH_SEC)
        try:
            pull_all(root)
        except Exception as e:  # noqa: BLE001
            _STATE["error"] = f"{type(e).__name__}: {str(e)[:200]}"
            _log(f"lam moi loi: {_STATE['error']}")


def _start_refresh(root: str) -> None:
    t = _STATE.get("thread")
    if t is not None and t.is_alive():
        return
    th = threading.Thread(target=_refresh_loop, args=(root,), name="cloud_boot_refresh", daemon=True)
    th.start()
    _STATE["thread"] = th


def trim_memory() -> None:
    """Tra RAM da giai phong ve he dieu hanh (glibc malloc_trim tren Linux + pool pyarrow) - goi cuoi moi lan render tren cloud.
    pandas/numpy giai phong khoi lon nhung heap glibc hay giu lai -> RSS cao gia tao tren may 1 GB."""
    import gc
    gc.collect()
    try:
        import pyarrow as pa
        pa.default_memory_pool().release_unused()
    except Exception:  # noqa: BLE001
        pass
    if sys.platform.startswith("linux"):
        try:
            import ctypes
            ctypes.CDLL("libc.so.6").malloc_trim(0)
        except Exception:  # noqa: BLE001
            pass


def _tune_allocators() -> None:
    """Linux: jemalloc cua pyarrow tra RAM ngay (decay 0) thay vi giu lai."""
    try:
        import pyarrow as pa
        pa.jemalloc_set_decay_ms(0)
    except Exception:  # noqa: BLE001
        pass


def info() -> dict:
    """Trang thai de hien o chan trang / debug."""
    root = data_root()
    d = {"cloud": bool(_STATE["cloud"]), "root": root, "pulls": _STATE["pulls"], "error": _STATE["error"], "mb": round(_STATE["mb"])}
    try:
        with open(_marker_path(root), encoding="utf-8") as f:
            d["marker"] = json.load(f)
    except Exception:  # noqa: BLE001
        d["marker"] = None
    return d


def boot(ui: bool = True) -> bool:
    """Goi dau app.py (sau st.set_page_config, truoc import datalib). Tra True neu dang chay che do cloud."""
    if not is_cloud():
        return False
    root = data_root()
    os.makedirs(root, exist_ok=True)
    _set_env(root)
    _tune_allocators()
    with _LOCK:
        if _STATE["booted"] or os.path.exists(_marker_path(root)):
            _STATE["booted"] = True
            _start_refresh(root)
            return True
        st = None
        if ui:
            try:
                import streamlit as st_
                from streamlit.runtime.scriptrunner import get_script_run_ctx
                st = st_ if get_script_run_ctx() is not None else None
            except Exception:  # noqa: BLE001
                st = None
        if st is not None:
            with st.status("Lần đầu mở trên cloud: đang kéo dữ liệu từ Google Drive (≈ 1–2 phút) …", expanded=True) as box:
                lines = st.empty()
                log: list[str] = []

                def prog(msg):
                    log.append(f"• {msg}")
                    lines.markdown("\n".join(log[-8:]))

                try:
                    inf = pull_all(root, prog, first=True)
                    box.update(label=f"Đã kéo {inf['mb']:.0f} MB ({inf['files']} file) trong {inf['seconds']:.0f} s · "
                                     f"làm mới mỗi {REFRESH_SEC // 60} phút", state="complete", expanded=False)
                except Exception as e:  # noqa: BLE001
                    _STATE["error"] = f"{type(e).__name__}: {str(e)[:300]}"
                    box.update(label=f"Kéo dữ liệu lỗi: {_STATE['error']}", state="error")
                    raise
        else:
            pull_all(root, _log, first=True)
        _STATE["booted"] = True
        _start_refresh(root)
    return True


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Keo du lieu app tu Drive nhu tren Streamlit Cloud (khong can streamlit)")
    ap.add_argument("--pull", action="store_true", help="keo ve MD_ROOT (mac dinh /tmp/pipeline-data/market-data)")
    ap.add_argument("--info", action="store_true")
    a = ap.parse_args()
    if a.pull:
        os.environ.setdefault("STREAMLIT_CLOUD", "1")
        r = data_root()
        os.makedirs(r, exist_ok=True)
        _set_env(r)
        print(json.dumps(pull_all(r, _log, first=True), ensure_ascii=False, indent=1))
    else:
        print(json.dumps(info(), ensure_ascii=False, indent=1))
