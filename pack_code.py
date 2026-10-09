# -*- coding: utf-8 -*-
"""pack_code.py — sao chep CODE (khong data) cua 3 hub + HAH vao repo cloud-deploy (07/10/2026).

    python pack_code.py            # D:\\market-data -> market-data/, D:\\shipping -> shipping/, D:\\bctc -> bctc/,
                                   # D:\\Database\\Logistics\\HAH\\haian_pull.py -> hah/, D:\\market-data\\cloud-probe -> cloud-probe/
    python pack_code.py --dry-run  # chi liet ke
    python pack_code.py --dest D:\\pipeline-data   # chep code vao cay du lieu local (Run-Local-*.ps1 dung)

Whitelist: .py .md .txt .json .yaml .yml .toml .ini .cfg .bat .ps1 .js .pem .crt .traineddata va .csv < 2 MB
(file cau hinh nho: carriers.csv, terminals.csv, nodes.csv, banks.txt, tv_symbols.txt, firms.json...).
Bo: data (CSV master lon, *-master/*-wide/fact_*/..., parquet, sqlite, xlsx, pdf, html), logs, cache, __pycache__,
_pip-backup, pdf-detector/downloads, fs-extractor/output, fiinprox-unpivot/output, bond-pivot/data+output, raw/, data/...
Nguon goc (D:\\...) KHONG bi sua. Chay lai bat ky luc nao de cap nhat code trong repo (chep de, xoa file code da mat o nguon).
Truoc khi chep: quet secret (token/api_key/password/cookie/Bearer gan cung) -> in canh bao, van chep (xem README).
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MD_SRC = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))
SHIP_SRC = os.path.normpath(os.environ.get("SHIP_ROOT", "D:/shipping"))
BCTC_SRC = os.path.normpath(os.environ.get("BCTC_ROOT", "D:/bctc"))
HAH_SRC = os.path.normpath(os.environ.get("HAH_DIR", "D:/Database/Logistics/HAH"))

# (nguon, dich tuong doi repo, loai tru rieng (thu muc tuong doi nguon, posix))
HUBS = [
    (MD_SRC, "market-data", ["cloud-probe", "_pip-backup", "bond-pivot/data", "bond-pivot/output", "bond-pivot/logs",
                             "transmission-fetcher/cbtt", "transmission-fetcher/sbv_cache", "transmission-fetcher/_archive",
                             "transmission-fetcher/paste", "transmission-fetcher/lending", "nso-fetcher/monthly-reports",
                             "app/cache", "chart-pack/out", "chart-pack/ftse/out", "index-fetcher/raw/vci_foreign"]),
    (SHIP_SRC, "shipping", ["port-tracker/cache", "cangvu-toanquoc/khao-sat", "vimawa-sanluong/downloads",
                            "vimawa-sanluong/raw"]),
    (BCTC_SRC, "bctc", ["pdf-detector/downloads", "pdf-detector/markitdown-tool/out", "fs-extractor/output",
                        "fiinprox-unpivot/output", "fiinprox-unpivot/input", "nganh-chung-khoan/excel_feed",
                        "nganh-bat-dong-san/output", "nganh-bat-dong-san/cbre-reports", "md2bctc/output", "md2bctc/input",
                        "tcbs-pbi/output", "pdf-detector/markitdown-tool/tessdata", "fs-extractor/output_cap",
                        "fs-extractor/output_cap_adjust", "fs-extractor/output_liq", "tcbs-pbi"]),
    (os.path.join(MD_SRC, "cloud-probe"), "cloud-probe", []),
]
HAH_FILES = ["haian_pull.py", "HUONG-DAN-SU-DUNG.md"]          # ps1/js goc giu o laptop, khong can tren cloud

CODE_EXT = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".bat", ".ps1", ".js", ".pem",
            ".crt", ".traineddata", ".gitignore"}
SMALL_EXT = {".csv": 2 * 1024 * 1024}                             # file cau hinh .csv < 2 MB
DIR_SKIP = {"__pycache__", ".git", ".venv", "venv", "node_modules", "logs", "cache", "raw", "data", "output", "out",
            "downloads", "history", "reports", "_backup", ".pytest_cache", ".ipynb_checkpoints"}
# ten file DATA du nho van bo (CSV master / ket qua pipeline trong thu muc goc)
DATA_NAME = ["*-master*.csv", "*_master*.csv", "*-wide*.csv", "*_wide*.csv", "fact_*.csv", "ratios_wide_*.csv",
             "valuation_*_daily.csv", "npat_*.csv", "industry_summary.csv", "vsdc_tk_ndt*.csv", "*_timeseries*.csv",
             "nso_catalog.csv", "monthly_reports_index.csv", "cbtt_urls.csv", "_bank_bs.csv", "transmission-nodes.csv",
             "berth_area_*.csv", "status*.txt", "status-*.txt", "*.log", "*_log.txt", "*_log_*.txt", "fetch_log*.txt",
             "market-eps.csv", "shares-master.csv", "vhbs_contex.csv", "haian-*.csv", "itinerary_*.csv", "*.bak",
             "*.tmp", "sbv_*_state.json", "tv-history*.csv", "indices.csv", "flows-*.csv", "fx-*.csv",
             "probe_local_baseline.json", "ck_*.csv", "valuation-*.csv", "stocks-*.csv", "sectors-*.csv", "tickers-master.csv",
             "nganh_cache.csv", "bond_maturity_bds.csv", "*.traineddata.bak"]
# file trong thu muc BCTI-scraper: 221 CSV chi so (data) -> chi lay code
BCTI_KEEP = {"scrape_bcti.py", "HUONG-DAN.txt"}

SECRET_RX = re.compile(r"""(?i)\b(api[_-]?key|apikey|secret|password|passwd|bot[_-]?token|access[_-]?token|auth[_-]?token|
                            cookie|authorization|bearer)\b\s*[:=]\s*['"][A-Za-z0-9_\-:./+=]{12,}['"]""", re.X)
SECRET_OK = re.compile(r"(?i)environ|getenv|os\.environ|\{token\}|\{tok\}|\$env|secrets\.|<meta|__VPToken|__RequestVerification")


def is_code(rel_posix: str, name: str, size: int) -> bool:
    low = name.lower()
    ext = os.path.splitext(low)[1]
    if any(fnmatch.fnmatch(low, p) for p in DATA_NAME):
        return False
    if rel_posix.startswith("shipping/BCTI-scraper/") or rel_posix.startswith("BCTI-scraper/"):
        return name in BCTI_KEEP
    if ext in CODE_EXT or low in CODE_EXT:
        return True
    if ext in SMALL_EXT and size < SMALL_EXT[ext]:
        return True
    return False


def walk_hub(src: str, excl: list) -> list:
    out = []
    excl = [e.rstrip("/").lower() for e in excl]
    for root, dirs, files in os.walk(src):
        rel = os.path.relpath(root, src).replace("\\", "/")
        rel = "" if rel == "." else rel
        keep = []
        for d in dirs:
            rd = (rel + "/" + d if rel else d).lower()
            if d in DIR_SKIP or rd in excl or (d.startswith(".") and d != ".streamlit"):   # .streamlit/config.toml = theme app
                continue
            keep.append(d)
        dirs[:] = keep
        for f in files:
            rp = rel + "/" + f if rel else f
            full = os.path.join(root, f)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            if is_code(rp, f, size):
                out.append((rp, full, size))
    return out


def scan_secrets(files: list) -> list:
    hits = []
    for rp, full, _ in files:
        if not full.lower().endswith((".py", ".ps1", ".bat", ".js", ".json", ".yaml", ".yml", ".cfg", ".ini", ".toml")):
            continue
        try:
            for i, line in enumerate(open(full, encoding="utf-8", errors="replace"), 1):
                if SECRET_RX.search(line) and not SECRET_OK.search(line):
                    hits.append(f"{rp}:{i}: {line.strip()[:120]}")
        except OSError:
            pass
    return hits


def copy_tree(items: list, dest_root: str, dry: bool) -> tuple[int, int]:
    n, total = 0, 0
    wanted = set()
    for rp, full, size in items:
        dst = os.path.join(dest_root, rp.replace("/", os.sep))
        wanted.add(os.path.normcase(dst))
        total += size
        n += 1
        if dry:
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst) or os.path.getsize(dst) != size or int(os.path.getmtime(dst)) < int(os.path.getmtime(full)):
            shutil.copy2(full, dst)
    # xoa file code trong repo da mat o nguon (chi file loai code, KHONG dong vao data dong bo tu Drive)
    if not dry and os.path.isdir(dest_root):
        for root, dirs, files in os.walk(dest_root):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
            for f in files:
                p = os.path.join(root, f)
                if os.path.normcase(p) in wanted:
                    continue
                ext = os.path.splitext(f.lower())[1]
                if ext in (".py", ".md", ".ps1", ".bat", ".js") and os.path.normcase(p) not in wanted:
                    try:
                        os.remove(p)
                        print(f"  - xoa {os.path.relpath(p, dest_root)} (khong con o nguon)")
                    except OSError:
                        pass
    return n, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", default=HERE, help="thu muc dich (mac dinh: thu muc repo nay)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--hub", default="", help="chi chep 1 hub: market-data|shipping|bctc|hah|cloud-probe")
    a = ap.parse_args()
    grand_n = grand_b = 0
    all_items = []
    for src, name, excl in HUBS:
        if a.hub and a.hub != name:
            continue
        if not os.path.isdir(src):
            print(f"! khong thay {src}, bo qua {name}")
            continue
        items = walk_hub(src, excl)
        n, b = copy_tree(items, os.path.join(a.dest, name), a.dry_run)
        print(f"{name:12} <- {src}: {n} file, {b / 1e6:.1f} MB")
        grand_n += n
        grand_b += b
        all_items += [(name + "/" + rp, full, s) for rp, full, s in items]
    if not a.hub or a.hub == "hah":
        items = [(f, os.path.join(HAH_SRC, f), os.path.getsize(os.path.join(HAH_SRC, f)))
                 for f in HAH_FILES if os.path.exists(os.path.join(HAH_SRC, f))]
        n, b = copy_tree(items, os.path.join(a.dest, "hah"), a.dry_run)
        print(f"{'hah':12} <- {HAH_SRC}: {n} file, {b / 1e6:.1f} MB")
        grand_n += n
        grand_b += b
        all_items += [("hah/" + rp, full, s) for rp, full, s in items]
    print(f"TONG: {grand_n} file, {grand_b / 1e6:.1f} MB{' (dry-run)' if a.dry_run else ''}")
    hits = scan_secrets(all_items)
    if hits:
        print(f"\n! QUET SECRET: {len(hits)} dong nghi ngo (chuyen sang env + GitHub Secrets truoc khi push):")
        for h in hits:
            print("  " + h)
    else:
        print("Quet secret: khong thay token/api_key/password/cookie gan cung trong code.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
