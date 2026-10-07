"""Scrape CHI SO GIA CUOC TAU BIEN tu stockq.org va merge vao <TICKER>.csv.

Pham vi (2026-09-08): CHI lay chi so gia cuoc van tai bien, liet ke trong tickers.csv
  Dry bulk : BDI, BCI (Capesize), BPI (Panamax), BSI (Supramax), BHI (Handysize)
  Tanker   : BCTI (Clean), BDTI (Dirty)
  Container: SCFI (Shanghai Containerized Freight Index, du lieu theo TUAN)
Danh sach 220 chi so cu (co phieu/tien te/trai phieu...) da luu o tickers-all.csv,
muon keo lai thi truyen thang ma: python scrape_bcti.py SPX VIX

Usage:
  python scrape_bcti.py             # mac dinh BCTI
  python scrape_bcti.py ALL         # tat ca ma trong tickers.csv (8 chi so gia cuoc)
  python scrape_bcti.py BDI SCFI    # chi dinh ma

Nguon (moi, tu 2026-08-12 stockq doi kien truc chart):
  Loader   : https://en.stockq.org/index/js/<TICKER>_sma.js  (chua bien dataFiles)
  Du lieu  : https://www.stockq.org/index/chart-data.php?id=<TICKER>&type=sma|dev&range=<1m..5y>
             -> BAT BUOC header Referer: https://en.stockq.org/index/<TICKER>.htm (thieu = HTTP 403)
  sma = Price + MA20/MA60/MA120 | dev = Price + Average/upper/lower bound
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen

# stockq doi kien truc chart tu 2026-08-12: <TICKER>_sma.js gio chi con la LOADER,
# du lieu that nam o chart-data.php (bat buoc co header Referer, thieu -> HTTP 403).
# Loader chua san bien dataFiles = {"1m": url, ..., "5y": url} -> doc tu do cho chac.
LOADER_URL = "https://en.stockq.org/index/js/{ticker}_{kind}.js"
REFERER = "https://en.stockq.org/index/{ticker}.htm"
BASE_URL = "https://en.stockq.org/index/js"  # giu lai cho format cu
SCRIPT_DIR = Path(__file__).parent
LOG_FILE = SCRIPT_DIR / "scrape.log"
TICKERS_CSV = SCRIPT_DIR / "tickers.csv"


def load_all_tickers() -> list[str]:
    """Read every ticker from tickers.csv (column 'ticker')."""
    if not TICKERS_CSV.exists():
        log(f"ERROR: {TICKERS_CSV} not found; cannot expand ALL")
        return []
    with TICKERS_CSV.open("r", newline="", encoding="utf-8") as f:
        return [row["ticker"].strip() for row in csv.DictReader(f) if row.get("ticker")]

HEADERS = {"User-Agent": "Mozilla/5.0 (BCTI-scraper)"}

ROW_RE = re.compile(
    r"\[new Date\('([^']+)'\)\s*,\s*"
    r"([0-9.]+|null)\s*,\s*"
    r"([0-9.]+|null)?\s*,?\s*"
    r"([0-9.]+|null)?\s*,?\s*"
    r"([0-9.]+|null)?\s*\]"
)

BLOCK_RE = re.compile(
    r"var\s+(data\w+)\s*=\s*google\.visualization\.arrayToDataTable\(\[(.*?)\]\s*\);",
    re.DOTALL,
)

DATAFILES_RE = re.compile(r"var\s+dataFiles\s*=\s*(\{.*?\})\s*;", re.DOTALL)

# Keo TAT CA range co san, NGAN -> DAI, va "range ngan thang" khi trung ngay:
# range 5y bi nguon cat bot cot MA120 (chi con Price/MA20/MA60), cac range ngan
# van du 4 cot -> lay ban ngan truoc thi giu duoc MA120 cho phan gan day,
# range dai chi de lap phan lich su cu. Moi ma co bo range rieng (SCFI khong co 5y).
RANGE_ORDER = ["1m", "3m", "6m", "1y", "2y", "5y"]


def fetch(url: str, referer: str | None = None) -> str:
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    req = Request(url, headers=headers)
    with urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_block(block_body: str) -> list[tuple[str, float | None, ...]]:
    rows: list[tuple] = []
    for m in ROW_RE.finditer(block_body):
        date_str, *vals = m.groups()
        try:
            d = datetime.strptime(date_str, "%b %d, %Y").date()
        except ValueError:
            continue
        nums = tuple(None if v in (None, "null") else float(v) for v in vals)
        rows.append((d.isoformat(), *nums))
    return rows


def parse_js(text: str) -> dict[str, list[tuple]]:
    out = {}
    for m in BLOCK_RE.finditer(text):
        name, body = m.group(1), m.group(2)
        out[name] = parse_block(body)
    return out


def parse_payload(text: str) -> list[tuple]:
    """Rows tu 1 phan hoi. Ho tro ca format CU (var dataXX = arrayToDataTable([...]))
    lan format MOI cua chart-data.php (window.stockQChartRangeData("sma","5y", ...))."""
    blocks = parse_js(text)
    if blocks:
        rows: dict[str, tuple] = {}
        for key in ("data5Y", "data2Y", "data1Y", "data6M", "data3M", "data1M"):
            for row in blocks.get(key, []):
                rows.setdefault(row[0], row)
        if not rows:  # ten bien khac -> gom het cac block
            for rs in blocks.values():
                for row in rs:
                    rows.setdefault(row[0], row)
        return list(rows.values())
    return parse_block(text)


def fetch_series(ticker: str, kind: str) -> tuple[list[tuple], str]:
    """Lay chuoi 'sma' hoac 'dev' cua 1 ma qua loader -> chart-data.php.

    Tra (rows, raw_text) — raw_text de scrape_ticker con phan biet 'nguon rong'
    voi 'parser hong'. Keo moi range co san theo thu tu NGAN -> DAI (xem RANGE_ORDER)."""
    referer = REFERER.format(ticker=ticker)
    loader = fetch(LOADER_URL.format(ticker=ticker, kind=kind), referer)
    rows: dict[str, tuple] = {}
    raw = loader
    m = DATAFILES_RE.search(loader)
    if m:
        try:
            files = json.loads(m.group(1))
        except json.JSONDecodeError:
            files = {}
        want = [r for r in RANGE_ORDER if r in files]
        for i, rg in enumerate(want):
            raw = fetch(files[rg], referer)
            for row in parse_payload(raw):
                rows.setdefault(row[0], row)
            if i < len(want) - 1:
                time.sleep(0.2)
    else:
        # Format cu: du lieu nam ngay trong file .js
        for row in parse_payload(loader):
            rows.setdefault(row[0], row)
    return list(rows.values()), raw


def merge_sma_dev(sma_rows: list[tuple], dev_rows: list[tuple]) -> dict[str, dict]:
    by_date: dict[str, dict] = {}
    for r in sma_rows:
        d, price, ma20, ma60, ma120 = (r + (None,) * 5)[:5]
        by_date[d] = {"date": d, "price": price, "ma20": ma20, "ma60": ma60, "ma120": ma120}
    for r in dev_rows:
        d, price, avg, upper, lower = (r + (None,) * 5)[:5]
        row = by_date.setdefault(d, {"date": d, "price": price})
        if row.get("price") is None:
            row["price"] = price
        row["avg"] = avg
        row["upper"] = upper
        row["lower"] = lower
    return by_date


def load_existing(out_csv: Path) -> dict[str, dict]:
    if not out_csv.exists():
        return {}
    with out_csv.open("r", newline="", encoding="utf-8") as f:
        return {row["date"]: row for row in csv.DictReader(f)}


def write_csv(out_csv: Path, rows: dict[str, dict]) -> None:
    fields = ["date", "price", "ma20", "ma60", "ma120", "avg", "upper", "lower"]
    ordered = [rows[d] for d in sorted(rows)]
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k, "") if r.get(k) is not None else "" for k in fields})


def log(msg: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')}  {msg}"
    print(line)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def norm(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if v in (None, ""):
            out[k] = ""
        elif isinstance(v, float):
            out[k] = f"{v:g}"
        else:
            try:
                out[k] = f"{float(v):g}"
            except (TypeError, ValueError):
                out[k] = str(v)
    return out


def scrape_ticker(ticker: str) -> int:
    ticker = ticker.upper()
    out_csv = SCRIPT_DIR / f"{ticker}.csv"
    try:
        sma_rows, sma_txt = fetch_series(ticker, "sma")
        dev_rows, dev_txt = fetch_series(ticker, "dev")
    except Exception as e:
        log(f"[{ticker}] FETCH ERROR: {e}")
        return 1

    new_rows = merge_sma_dev(sma_rows, dev_rows)
    if not new_rows:
        # Distinguish an empty source (stockq has no data for this index)
        # from a real parser breakage (data present but regex missed it).
        if "new Date(" not in sma_txt and "new Date(" not in dev_txt:
            log(f"[{ticker}] SKIP: source has no data")
            return 0
        log(f"[{ticker}] PARSE ERROR: no rows extracted")
        return 2

    existing = load_existing(out_csv)
    added = sum(1 for d in new_rows if d not in existing)
    updated = sum(
        1 for d, r in new_rows.items()
        if d in existing and norm(r) != norm({k: existing[d].get(k, "") for k in r})
    )

    merged = {**existing, **{d: {**existing.get(d, {}), **r} for d, r in new_rows.items()}}
    write_csv(out_csv, merged)

    latest = max(new_rows)
    log(f"[{ticker}] OK  rows={len(merged)} added={added} updated={updated} latest={latest}")
    return 0


def main(argv: list[str]) -> int:
    args = argv[1:] or ["BCTI"]
    # Expand the ALL keyword into every ticker from tickers.csv
    tickers: list[str] = []
    for a in args:
        if a.upper() == "ALL":
            tickers.extend(load_all_tickers())
        else:
            tickers.append(a)
    # De-dup while preserving order
    seen_t: set[str] = set()
    tickers = [t for t in tickers if not (t.upper() in seen_t or seen_t.add(t.upper()))]

    total = len(tickers)
    log(f"=== RUN START: {total} ticker(s) ===")
    ok = fail = 0
    for i, t in enumerate(tickers, 1):
        rc = scrape_ticker(t)
        if rc == 0:
            ok += 1
        else:
            fail += 1
        if i < total:
            time.sleep(0.4)
    log(f"=== RUN DONE: ok={ok} fail={fail} total={total} ===")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
