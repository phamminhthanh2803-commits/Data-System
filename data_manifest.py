# -*- coding: utf-8 -*-
"""data_manifest.py — BAN DO DU LIEU cua pipeline: thu muc nao moi buoc doc/ghi, ai la chu (cloud hay laptop),
thu muc nao len Google Drive (07/10/2026).

Quy uoc Drive:  gdrive:pipeline-data/<hub>/<thu-muc>  lap y cau truc D:\\  (hub = market-data | shipping | hah).
  - Code (.py/.md/.ps1/.bat/logs) KHONG len Drive (o repo GitHub); Drive chi giu data (CSV/parquet/json/xlsx/pdf...).
  - Moi thu muc co 1 CHU duy nhat duoc ghi toan bo: cloud (GitHub Actions) hoac laptop. Ben kia chi doc, hoac chi ghi
    vai file liet ke ro (cloud_up_include / laptop_up_include) de 2 ben khong ghi de nhau.
  - bond-pivot (3,5 GB) KHONG len Drive (Drive chi con 6,8 GB): buoc bonds chay o laptop (Run-Local-Mini thu Hai) tren
    D:\\market-data\\bond-pivot (junction D:\\pipeline-data\\market-data\\bond-pivot -> D:\\market-data\\bond-pivot de app doc).
  - cangvu-hcm: laptop la chu (Cang vu TP.HCM chan IP nuoc ngoai); cloud chi ghi 3 file enriched (vessel_enrich.py).
  - market-valuation: cloud la chu; laptop chi ghi valuation-region-master/wide.csv (IDX + Bursa bi Cloudflare chan IP My).

    python data_manifest.py            # in bang thu muc + buoc
    python data_manifest.py --size     # uoc dung luong tung thu muc se len Drive (doc tu D:\\), canh bao neu > 4 GB
"""
from __future__ import annotations

import fnmatch
import os
import sys
from dataclasses import dataclass, field

HUB_ENV = {"market-data": "MD_ROOT", "shipping": "SHIP_ROOT", "bctc": "BCTC_ROOT", "hah": "HAH_DIR"}
LAPTOP_DATA = {"market-data": "D:/pipeline-data/market-data", "shipping": "D:/pipeline-data/shipping", "bctc": "D:/bctc",
               "hah": "D:/pipeline-data/hah"}   # cay du lieu laptop (mo hinh cloud); bctc van la goc (nganh-ck Excel)
HUB_SRC = {"market-data": "D:/market-data", "shipping": "D:/shipping", "bctc": "D:/bctc",
           "hah": "D:/Database/Logistics/HAH"}                      # nguon goc tren laptop (seed lan dau)
DRIVE_LIMIT_MB = 4000

# loai tru CHUNG moi thu muc (code + log + tam): rclone filter, ap dung ca 2 chieu
CODE_EXCLUDE = ["*.py", "*.pyc", "__pycache__/**", "*.md", "*.ps1", "*.bat", "*.js", ".gitignore", "logs/**", "*.log",
                "*.tmp", "*.bak", "*.err", "desktop.ini", "Thumbs.db"]


@dataclass
class Folder:
    hub: str
    path: str                              # tuong doi hub ("" = chinh hub, vd hah)
    owner: str = "cloud"                   # 'cloud' | 'laptop': ben duoc rclone sync toan bo thu muc len Drive
    drive: bool = True                     # False: khong len Drive (bond-pivot)
    exclude: list = field(default_factory=list)      # them vao CODE_EXCLUDE (rclone pattern, tuong doi thu muc)
    include: list | None = None            # chi dong bo cac file nay (hah)
    cloud_up_include: list = field(default_factory=list)    # owner=laptop: file cloud van duoc ghi (rclone copy)
    laptop_up_include: list = field(default_factory=list)   # owner=cloud: file laptop van duoc ghi (rclone copy)
    note: str = ""

    @property
    def key(self) -> str:
        return f"{self.hub}/{self.path}" if self.path else self.hub

    def local_root(self) -> str:
        # Laptop (Windows, khong CLOUD=1) ma chua dat env -> D:\pipeline-data\<hub>, KHONG BAO GIO la cay goc D:\<hub>
        # (07/10/2026: chay `sync_data.py app` tay khong env da copy Drive de len D:\shipping goc - vo hai nhung sai y).
        base = os.environ.get(HUB_ENV[self.hub])
        if not base:
            base = HUB_SRC[self.hub] if (os.environ.get("CLOUD") == "1" or os.name != "nt") else LAPTOP_DATA[self.hub]
        return os.path.normpath(os.path.join(base, self.path)) if self.path else os.path.normpath(base)

    def src_root(self) -> str:
        return os.path.normpath(os.path.join(HUB_SRC[self.hub], self.path)) if self.path else os.path.normpath(HUB_SRC[self.hub])

    def remote(self, base: str) -> str:
        return f"{base}/{self.hub}/{self.path}" if self.path else f"{base}/{self.hub}"


FOLDERS: dict[str, Folder] = {f.key: f for f in [
    # ---------------- market-data (cloud la chu)
    Folder("market-data", "market-valuation", laptop_up_include=["valuation-region-master.csv", "valuation-region-wide.csv"],
           note="P/E P/B VN + khu vuc; laptop chi ghi 2 file region (IDX/Bursa)"),
    Folder("market-data", "index-fetcher", note="chi so, khoi ngoai, tu doanh, ICB, tv-history (229 MB), raw/vci_foreign ~440 MB"),
    Folder("market-data", "transmission-fetcher", exclude=["cbtt/**", "sbv_cache/**", "_archive/**", "transmission.xlsx"],
           note="ty gia -> lai suat -> thanh khoan; bo cbtt (811 MB PDF, cong cu rieng) + sbv_cache (backfill)"),
    Folder("market-data", "nso-fetcher", note="NSO PX-Web + Bieu so lieu thang (monthly-reports 134 MB, parse lai moi tuan)"),
    Folder("market-data", "macro-fetcher"),
    Folder("market-data", "vsdc-accounts"),
    Folder("market-data", "bond-pivot", owner="laptop", exclude=["data/raw/**", "logs/**", "tessdata/**", "output/**"],
           note="laptop chay buoc bonds thu Hai; len Drive CHI data/processed + config (~45 MB), bo data/raw 3,5 GB PDF"),
    # ---------------- shipping
    Folder("shipping", "VHBS-ConTex"),
    Folder("hah", "", include=["haian-schedule-master.csv", "haian-portcalls.csv", "haian-voyages.csv", "haian-schedule.csv"],
           note="lich tau HAH (D:/Database/Logistics/HAH): chi 4 CSV, bo xlsx/pdf/ps1/js"),
    Folder("shipping", "cangvu-haiphong", exclude=["raw/**"], note="raw/ (392 MB HTML cache) o lai laptop; data/ 81 MB"),
    Folder("shipping", "cangvu-hcm", owner="laptop", exclude=["raw/**"],
           cloud_up_include=["data/cvhcm_calls_enriched.csv", "data/cvhcm_monthly_operator.csv", "data/cvhcm_monthly_terminal.csv"],
           note="laptop cao (IP VN); cloud chi ghi 3 file enriched tu vessel_enrich.py"),
    Folder("shipping", "cangvu-toanquoc", exclude=["khao-sat/**"]),
    Folder("shipping", "vessel-itinerary"),
    Folder("shipping", "Alibra-scraper"),
    Folder("shipping", "BCTI-scraper"),
]}

# file index-fetcher ma cac buoc KHAC (valuation, nganh-ck) can doc - khong keo raw/vci_foreign 1.600 file
IDX_SMALL = ["indices-master.csv", "flows-master.csv", "fx-master.csv", "tv-history.csv", "raw/vn_screener_meta.csv",
             "raw/vn_icb_vci.csv"]

# buoc -> [(thu muc, 'r'|'rw', include hoac None)]  (ten buoc = Step.name trong run_slot.py cua tung hub)
STEP_FOLDERS: dict[str, list] = {
    # market-data AM
    "valuation-vn":     [("market-data/market-valuation", "rw", None), ("market-data/index-fetcher", "r", IDX_SMALL)],
    "macro-vn":         [("market-data/macro-fetcher", "rw", None)],
    "nso":              [("market-data/nso-fetcher", "rw", None)],
    "nso-monthly":      [("market-data/nso-fetcher", "rw", None)],
    "bonds":            [("market-data/bond-pivot", "rw", None)],
    "vsdc-accounts":    [("market-data/vsdc-accounts", "rw", None)],
    "indices":          [("market-data/index-fetcher", "rw", None)],
    # market-data PM
    "transmission":     [("market-data/transmission-fetcher", "rw", None), ("market-data/macro-fetcher", "r", None),
                         ("market-data/index-fetcher", "r", IDX_SMALL)],
    "flows":            [("market-data/index-fetcher", "rw", None)],
    "foreign-stocks":   [("market-data/index-fetcher", "rw", None)],
    "foreign-vci":      [("market-data/index-fetcher", "rw", None)],
    "prop-stocks":      [("market-data/index-fetcher", "rw", None)],
    "icb-vci":          [("market-data/index-fetcher", "rw", None)],
    "indices-vn":       [("market-data/index-fetcher", "rw", None)],
    "tvhistory":        [("market-data/index-fetcher", "rw", None)],
    "valuation-region": [("market-data/market-valuation", "rw", None), ("market-data/index-fetcher", "r", IDX_SMALL)],
    "tradingview":      [("market-data/market-valuation", "rw", None), ("market-data/index-fetcher", "r", IDX_SMALL)],
    "nganh-ck":         [("market-data/index-fetcher", "r", IDX_SMALL), ("market-data/vsdc-accounts", "r", None),
                         ("market-data/market-valuation", "r", None), ("market-data/transmission-fetcher", "r", None)],
    "msci":             [("market-data/market-valuation", "rw", None)],
    "macro-region":     [("market-data/macro-fetcher", "rw", None)],
    # shipping AM
    "vhbs":             [("shipping/VHBS-ConTex", "rw", None)],
    "haian":            [("hah", "rw", None)],
    "cvhp":             [("shipping/cangvu-haiphong", "rw", None)],
    "cvhcm-berthmap":   [("shipping/cangvu-hcm", "rw", None)],
    "cvhcm":            [("shipping/cangvu-hcm", "rw", None)],
    "cv-pkh":           [("shipping/cangvu-toanquoc", "rw", None), ("shipping/cangvu-haiphong", "r", None)],
    "cv-aspx":          [("shipping/cangvu-toanquoc", "rw", None)],
    "cv-national":      [("shipping/cangvu-toanquoc", "rw", None), ("shipping/cangvu-haiphong", "r", None),
                         ("shipping/cangvu-hcm", "r", None)],
    "cvhp-vessels":     [("shipping/cangvu-haiphong", "rw", None), ("shipping/cangvu-hcm", "rw", None),
                         ("shipping/cangvu-toanquoc", "r", None)],
    "itinerary":        [("shipping/vessel-itinerary", "rw", None), ("shipping/cangvu-haiphong", "r", None),
                         ("shipping/cangvu-hcm", "r", None), ("shipping/cangvu-toanquoc", "r", None)],
    "alibra":           [("shipping/Alibra-scraper", "rw", None)],
    # shipping PM
    "bcti":             [("shipping/BCTI-scraper", "rw", None)],
}

# thu muc app local doc (Run-Local-Mini keo ve D:\pipeline-data moi toi de app Streamlit + port-tracker dung)
APP_FOLDERS = [("market-data/market-valuation", None), ("market-data/index-fetcher", IDX_SMALL + ["raw/vn_foreign_stocks_vci.parquet",
               "raw/vn_prop_stocks.csv", "raw/vn_foreign_stocks_*.csv", "reports/**"]),
               ("market-data/transmission-fetcher", None), ("market-data/nso-fetcher", ["nso_master.csv", "nso_monthly_master.csv",
               "nso_catalog.csv", "nso_timeseries.xlsx", "monthly_reports_index.csv"]), ("market-data/macro-fetcher", None),
               ("market-data/vsdc-accounts", None), ("shipping/VHBS-ConTex", None), ("hah", None),
               ("shipping/cangvu-haiphong", None), ("shipping/cangvu-hcm", None), ("shipping/cangvu-toanquoc", None),
               ("shipping/vessel-itinerary", None), ("shipping/Alibra-scraper", None), ("shipping/BCTI-scraper", None)]


# ---------------------------------------------------------------------------------------------- tien ich
def _match(rel: str, pat: str) -> bool:
    """So khop gan dung rclone: 'x/**' = thu muc x bat ky cap (hoac goc neu co '/'), '*.py' = ten file."""
    rel = rel.replace("\\", "/")
    p = pat.lstrip("/")
    anchored = pat.startswith("/")
    if p.endswith("/**"):
        d = p[:-3]
        return rel.startswith(d + "/") if anchored else (rel.startswith(d + "/") or ("/" + d + "/") in ("/" + rel))
    if "/" in p:
        return fnmatch.fnmatch(rel, p) if anchored else (fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(rel, "*/" + p))
    return fnmatch.fnmatch(os.path.basename(rel), p)


def folder_size(f: Folder, root: str | None = None) -> tuple[int, int]:
    """(bytes, so file) se len Drive tu thu muc nguon, ap dung include/exclude."""
    root = root or f.src_root()
    if not os.path.isdir(root):
        return 0, 0
    ex = CODE_EXCLUDE + f.exclude
    tot = n = 0
    for dp, dirs, files in os.walk(root):
        rel_dir = os.path.relpath(dp, root).replace("\\", "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        dirs[:] = [d for d in dirs if not any(_match((rel_dir + "/" + d if rel_dir else d) + "/x", p) for p in ex if p.endswith("/**"))]
        for fn in files:
            rel = rel_dir + "/" + fn if rel_dir else fn
            if f.include is not None and not any(_match(rel, p) for p in f.include):
                continue
            if any(_match(rel, p) for p in ex):
                continue
            try:
                tot += os.path.getsize(os.path.join(dp, fn))
                n += 1
            except OSError:
                pass
    return tot, n


def main() -> int:
    size = "--size" in sys.argv
    print(f"{'thu muc':34} {'chu':7} {'Drive':5} {'MB':>8} {'file':>7}  ghi chu")
    total = 0
    for f in FOLDERS.values():
        mb = nf = 0
        if size and f.drive:
            b, nf = folder_size(f)
            mb = b / 1e6
            total += mb
        print(f"{f.key:34} {f.owner:7} {'co' if f.drive else 'KHONG':5} {mb:8.0f} {nf:7}  {f.note}")
    if size:
        print(f"\nTONG len Drive: {total:,.0f} MB (gioi han {DRIVE_LIMIT_MB} MB){'  !!! VUOT' if total > DRIVE_LIMIT_MB else '  OK'}")
    print("\nBuoc -> thu muc:")
    for s, lst in STEP_FOLDERS.items():
        print(f"  {s:17} " + "; ".join(f"{k} [{m}{' 1 phan' if inc else ''}]" for k, m, inc in lst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
