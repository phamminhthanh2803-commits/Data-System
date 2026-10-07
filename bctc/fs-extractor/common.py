# -*- coding: utf-8 -*-
"""
common.py — Phần DÙNG CHUNG cho cả 3 pipeline (bctc / cap / liq) của fsx.py.

Gom hết những thứ trước đây lặp lại ở fs_pull/liq_pull/cap_pull:
  - thiết lập encoding + tắt warning + nuốt banner vnstock
  - điều tiết rate-limit (Pacer + call_with_retry)
  - tải bảng phân ngành ICB, nạp danh sách mã, merge ngành
  - vòng lặp xử lý từng mã (pacer + retry + progress)
  - tiện ích so khoảng kỳ (period_key / in_range) cho BCTC
"""
import io
import sys
import datetime
import os
import shutil
import time
import warnings
from contextlib import redirect_stdout

import pandas as pd

warnings.filterwarnings("ignore")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

QEND = {1: "-03-31", 2: "-06-30", 3: "-09-30", 4: "-12-31"}
FRONT = ["ticker", "ten_cong_ty", "nganh_L1", "nganh_L2", "nganh_L3", "nganh_L4"]
SAFE_PER_MIN = 18  # chừa biên so với trần 20/phút của vnstock community

TOOL_DIR = os.path.dirname(os.path.abspath(__file__))
NGANH_CACHE = os.path.join(TOOL_DIR, "nganh_cache.csv")
NGANH_CACHE_DAYS = 7  # cache danh sách mã + ngành, quá hạn tự kéo lại
ARCHIVE_KEEP = 1        # so ban cu giu trong _archive/ (dat 0 de tat)
ARCHIVE_FREE_MIN = 15 * 1024**3   # con duoi 15 GB trong thi bo qua archive


def suppress():
    """Context nuốt stdout (né banner quảng cáo của vnstock)."""
    return redirect_stdout(io.StringIO())


# ─────────────────────────── Rate limit ───────────────────────────
class Pacer:
    """Giữ nhịp < SAFE_PER_MIN request/phút (rolling 60s) để né rate-limit."""

    def __init__(self, max_per_min: int = SAFE_PER_MIN):
        self.max = max_per_min
        self.stamps = []

    def wait(self, weight: int = 1):
        weight = min(weight, self.max)
        while True:
            now = time.time()
            self.stamps = [t for t in self.stamps if now - t < 60]
            if len(self.stamps) + weight <= self.max:
                break
            sleep_for = 60 - (now - self.stamps[0]) + 0.5
            print(f"    [pacer] giu nhip API, cho {sleep_for:.0f}s ...", flush=True)
            time.sleep(max(sleep_for, 1))
        self.stamps.extend([time.time()] * weight)


def unwrap(func):
    """Bỏ lớp decorator @optimize_execution của vnai để KHÔNG bị đếm quota 20 req/phút.

    vnai dùng functools.wraps nên hàm gốc còn nguyên ở __wrapped__; gọi thẳng hàm
    gốc = vẫn đúng code vnstock, chỉ mất phần đếm quota phía client (server VCI
    không giới hạn). Hàm nào không bị bọc thì trả lại chính nó.
    Dùng cho Company.ratio_summary / Company.overview / Quote.history — 3 chỗ duy
    nhất khiến pipeline cap/liq phải bò theo pacer.
    """
    return getattr(func, "__wrapped__", func)


def call_with_retry(fn, *args, retries: int = 4, backoff: int = 62, **kwargs):
    """Gọi fn; nếu dính rate-limit (SystemExit / Exception) thì chờ rồi thử lại."""
    for attempt in range(retries + 1):
        try:
            return fn(*args, **kwargs)
        except SystemExit as e:
            if "rate limit" not in str(e).lower() or attempt == retries:
                raise
            print(f"    [retry] dinh rate-limit, cho {backoff}s ({attempt + 1}/{retries}) ...", flush=True)
            time.sleep(backoff)
        except Exception as e:
            if "rate limit" not in str(e).lower() or attempt == retries:
                raise
            print(f"    [retry] {type(e).__name__}, cho {backoff}s ({attempt + 1}/{retries}) ...", flush=True)
            time.sleep(backoff)


# ─────────────────────────── Phân ngành & mã ───────────────────────────
def get_industry_map() -> pd.DataFrame:
    """Bảng phân ngành ICB 4 cấp + tên công ty cho toàn bộ mã (nguồn VCI)."""
    with suppress():
        from vnstock.explorer.vci.listing import Listing
        df = Listing().symbols_by_industries()
    pivot = df.pivot_table(index=["symbol", "organ_name"], columns="icb_level",
                           values="icb_name", aggfunc="first").reset_index()
    pivot.columns = ["ticker", "ten_cong_ty", "nganh_L1", "nganh_L2", "nganh_L3", "nganh_L4"]
    return pivot


def load_industry(listing=None):
    """Tải bảng ngành, in tiến trình; trả None nếu lỗi (pipeline vẫn chạy được).

    Nếu đã có sẵn bảng listing (từ get_listing khi dùng --nganh) thì tái sử dụng,
    khỏi gọi API thêm lần nữa.
    """
    if listing is not None:
        return listing[FRONT].drop_duplicates("ticker")
    print("Tai bang phan nganh ICB ...", flush=True)
    try:
        return get_industry_map()
    except Exception as e:
        print(f"  Khong tai duoc phan nganh ({e})", flush=True)
        return None


# ─────────────────────────── Chọn mã theo NGÀNH ───────────────────────────
def get_listing(refresh: bool = False) -> pd.DataFrame:
    """Bảng mã STOCK đang niêm yết: ticker|ten_cong_ty|san|nganh_L1..L4.

    Cache ra nganh_cache.csv (NGANH_CACHE_DAYS ngày) — chọn ngành không tốn API.
    """
    if not refresh and os.path.exists(NGANH_CACHE):
        if time.time() - os.path.getmtime(NGANH_CACHE) < NGANH_CACHE_DAYS * 86400:
            return pd.read_csv(NGANH_CACHE)
    print("Tai danh sach ma + phan nganh tu VCI (cache 7 ngay) ...", flush=True)
    ind = get_industry_map()
    with suppress():
        from vnstock.explorer.vci.listing import Listing
        ex = Listing().symbols_by_exchange()
    ex = ex[(ex["type"] == "STOCK") & (ex["exchange"].isin(["HSX", "HNX", "UPCOM"]))]
    ex = ex[["symbol", "exchange"]].rename(columns={"symbol": "ticker", "exchange": "san"})
    ex["san"] = ex["san"].replace({"HSX": "HOSE"})
    df = ex.merge(ind, on="ticker", how="left")
    df = df[["ticker", "ten_cong_ty", "san",
             "nganh_L1", "nganh_L2", "nganh_L3", "nganh_L4"]].sort_values("ticker")
    df.to_csv(NGANH_CACHE, index=False, encoding="utf-8-sig")
    return df


def strip_accents(s) -> str:
    """Bỏ dấu + thường hóa để so khớp: 'Ngân hàng' -> 'ngan hang'."""
    import unicodedata
    s = str(s).replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def resolve_nganh(patterns, listing: pd.DataFrame, san: str = ""):
    """Tìm mã theo tên/từ khóa ngành ICB (khớp cả 4 cấp, không phân biệt hoa thường/dấu).

    patterns: list từ khóa (mỗi phần tử có thể chứa nhiều ngành cách nhau dấu phẩy).
    san: lọc sàn, vd "HOSE,HNX" (rỗng = cả 3 sàn).
    Trả (tickers đã sort, tên ngành khớp được) — tickers rỗng nếu không khớp gì.
    """
    pats = [strip_accents(p) for a in patterns for p in str(a).split(",") if p.strip()]
    df = listing
    if san:
        wanted = [s.strip().upper().replace("HSX", "HOSE") for s in san.split(",") if s.strip()]
        df = df[df["san"].isin(wanted)]
    lv_cols = ["nganh_L1", "nganh_L2", "nganh_L3", "nganh_L4"]
    norm = {c: df[c].fillna("").map(strip_accents) for c in lv_cols}
    mask = pd.Series(False, index=df.index)
    matched = set()
    for p in pats:
        for c in lv_cols:
            hit = norm[c].str.contains(p, regex=False)
            matched |= set(df.loc[hit, c].dropna())
            mask |= hit
    sel = df[mask]
    return sorted(sel["ticker"].unique()), sorted(matched)


def load_tickers(tickers_arg, file):
    """Gộp mã từ dòng lệnh + file .txt (mỗi dòng 1 mã), viết hoa."""
    tickers = [t.upper() for t in tickers_arg]
    if file:
        with open(file, encoding="utf-8") as fh:
            tickers += [line.strip().upper() for line in fh if line.strip()]
    return tickers


def merge_industry(df, industry_map, front=None):
    """Merge cột ngành vào df theo ticker, đưa các cột ngành lên đầu."""
    if industry_map is None or df is None or df.empty:
        return df
    front = front or FRONT
    df = df.merge(industry_map, on="ticker", how="left")
    return df[front + [c for c in df.columns if c not in front]]


def process_tickers(tickers, fn, req_weight, sleep=1.0, workers=1):
    """Chạy fn(ticker) cho từng mã, trả (results, failed).

    workers=1  -> tuần tự, có Pacer giữ nhịp <18 req/phút (BẮT BUỘC cho pipeline
                  nào gọi API CÔNG KHAI của vnstock: Company.ratio_summary,
                  Company.overview, Quote.history, Listing.* — các hàm này bị
                  decorator @optimize_execution của vnai đếm quota 20 req/phút,
                  chạm trần là sys.exit() giết cả batch).
    workers>1  -> song song, KHÔNG pacer. Chỉ dùng cho đường đi KHÔNG bị vnai
                  đếm — cụ thể là BCTC (Finance._get_report / _get_ratio_dict là
                  hàm NỘI BỘ, không có decorator). Đo thực tế 2026-09-08:
                  tuần tự có pacer 2,2 mã/phút -> 4 luồng 17,6 -> 8 luồng 23,6.
                  Trần thật là ĐỘ TRỄ server (~2,5s/request), không phải quota.
    """
    if workers and workers > 1:
        return _process_parallel(tickers, fn, workers)

    pacer = Pacer()
    results, failed = [], []
    for i, tk in enumerate(tickers, 1):
        print(f"[{i}/{len(tickers)}] {tk} ...", flush=True)
        pacer.wait(req_weight)
        try:
            results.append((tk, call_with_retry(fn, tk)))
        except Exception as e:
            print(f"    LOI {tk}: {e}", flush=True)
            failed.append(tk)
        time.sleep(sleep)
    return results, failed


def _process_parallel(tickers, fn, workers):
    """Chạy fn(ticker) song song bằng thread (I/O-bound nên GIL không cản).

    Giữ nguyên thứ tự mã trong kết quả để output y hệt chế độ tuần tự.
    stdout bị nuốt cho CẢ đoạn song song (suppress() dùng redirect_stdout —
    KHÔNG an toàn khi nhiều luồng vào/ra đan xen), tiến trình in ra stdout thật.
    """
    from concurrent.futures import ThreadPoolExecutor

    workers = max(1, min(int(workers), 12))
    print(f"  (song song {workers} luong, khong dung pacer)", flush=True)
    real_stdout = sys.stdout
    done = [0]

    def task(tk):
        try:
            val = call_with_retry(fn, tk)
            err = None
        except BaseException as e:          # vnai raise SystemExit khi chạm quota
            val, err = None, e
        done[0] += 1
        tag = "OK " if err is None else "LOI"
        print(f"[{done[0]}/{len(tickers)}] {tk} {tag}"
              + (f": {err}" if err is not None else ""),
              file=real_stdout, flush=True)
        return tk, val, err

    try:
        sys.stdout = io.StringIO()          # nuốt banner quảng cáo của vnstock
        with ThreadPoolExecutor(max_workers=workers) as ex:
            rows = list(ex.map(task, tickers))
    finally:
        sys.stdout = real_stdout            # tự lành kể cả khi luồng làm lệch stdout

    results = [(tk, val) for tk, val, err in rows if err is None]
    failed = [tk for tk, _, err in rows if err is not None]
    return results, failed


def _archive(path):
    """Day ban hien tai vao _archive/ truoc khi thay the. Giu ARCHIVE_KEEP ban gan nhat."""
    if not os.path.exists(path) or ARCHIVE_KEEP <= 0:
        return
    out_dir = os.path.dirname(path)
    name = os.path.basename(path)
    adir = os.path.join(out_dir, "_archive")
    try:
        free = shutil.disk_usage(out_dir).free
    except OSError:
        free = 0
    if free < os.path.getsize(path) + ARCHIVE_FREE_MIN:
        print(f"  ! con it dia trong -> bo qua archive cho {name}")
        return
    os.makedirs(adir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        shutil.copy2(path, os.path.join(adir, f"{name}.{stamp}"))
    except OSError as e:
        print(f"  ! khong archive duoc {name}: {e}")
        return
    olds = sorted(f for f in os.listdir(adir) if f.startswith(name + "."))
    for f in olds[:-ARCHIVE_KEEP]:
        try:
            os.remove(os.path.join(adir, f))
        except OSError:
            pass


def _merge_into(df, path, key):
    """Gop df vao file san co: bo dong cu co cung khoa, giu phan con lai, noi df vao.

    Doc theo chunk de khong nap ca file 1 GB vao RAM. Khoa nen la ('ticker','period')
    hoac ('ticker','date') - MOT LAN KEO thay the tron ven cac ky/ngay no lay ve, va
    giu nguyen nhung ky cu ma lan nay khong keo.
    """
    head = pd.read_csv(path, nrows=0, encoding="utf-8-sig")
    cols = list(head.columns)
    if not set(key).issubset(cols) or not set(key).issubset(df.columns):
        raise ValueError("thieu cot khoa trong file cu hoac du lieu moi")
    newkeys = set(df[list(key)].astype(str).agg("|".join, axis=1))
    tmp = path + ".tmp"
    kept = 0
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:
        first = True
        for ch in pd.read_csv(path, chunksize=400000, dtype=str, encoding="utf-8-sig"):
            k = ch[list(key)].astype(str).agg("|".join, axis=1)
            sub = ch[~k.isin(newkeys)]
            if len(sub):
                sub.to_csv(f, index=False, header=first)
                first = False
                kept += len(sub)
        df.reindex(columns=cols).to_csv(f, index=False, header=first)
    _archive(path)
    os.replace(tmp, path)
    return kept


def write_csv(df, out_dir, name, key=None, merge=True):
    """Ghi CSV utf-8-sig (Excel doc duoc tieng Viet).

    key != None va merge=True  -> GOP vao file cu (mac dinh, an toan)
    key None hoac merge=False  -> ghi de, nhung van archive ban cu truoc
    """
    path = os.path.join(out_dir, name)
    if key and merge and os.path.exists(path) and os.path.getsize(path) > 0:
        try:
            kept = _merge_into(df, path, key)
            print(f"  {name}: giu {kept:,} dong cu + {len(df):,} dong moi")
            return path
        except Exception as e:                                    # noqa: BLE001
            print(f"  ! gop that bai ({e}) -> ghi de, ban cu nam trong _archive/")
    _archive(path)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


# ─────────────────────────── So khoảng kỳ (BCTC) ───────────────────────────
def period_key(p: str):
    """'2020-Q3' -> (2020, 3); '2020' -> (2020, 0)."""
    p = str(p).strip().upper().replace("Q", "-Q").replace("--", "-")
    parts = p.split("-Q")
    year = int(parts[0])
    quarter = int(parts[1]) if len(parts) > 1 and parts[1] else 0
    return (year, quarter)


def in_range(p: str, p_from: str, p_to: str) -> bool:
    try:
        k = period_key(p)
    except (ValueError, IndexError):
        return True
    if p_from and k < period_key(p_from):
        return False
    if p_to:
        k_to = period_key(p_to)
        if k_to[1] == 0 and k[1] > 0:  # '--to 2024' với data quý -> trọn 4 quý
            k_to = (k_to[0], 4)
        if k > k_to:
            return False
    return True
