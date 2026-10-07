"""Download every Google Sheets CSV listed in sources.json into raw/YYYY-MM-DD/."""
from __future__ import annotations
import json, sys, time, hashlib, datetime as dt
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "sources.json"
RAW_DIR = ROOT / "raw"
LOG_PATH = ROOT / "fetch.log"

URL_TMPL = "https://docs.google.com/spreadsheets/d/e/{sid}/pub?gid={gid}&single=true&output=csv"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"


def log(msg: str) -> None:
    line = f"[{dt.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def http_get(url: str, retries: int = 3, backoff: float = 2.0) -> bytes:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers={"User-Agent": UA, "Accept": "text/csv,*/*"})
            with urlopen(req, timeout=30) as resp:
                return resp.read()
        except (URLError, HTTPError) as e:
            last_err = e
            log(f"  attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(backoff * attempt)
    raise RuntimeError(f"GET failed after {retries} attempts: {last_err}")


def latest_snapshot_for(label: str, exclude: Path | None = None) -> Path | None:
    """Most recent earlier snapshot of `label`, ignoring `exclude` (today's path)."""
    if not RAW_DIR.exists():
        return None
    candidates = sorted(
        (p for p in RAW_DIR.glob(f"*/{label}.csv") if p.is_file() and p != exclude),
        reverse=True,
    )
    return candidates[0] if candidates else None


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    today = dt.date.today().isoformat()
    out_dir = RAW_DIR / today
    out_dir.mkdir(parents=True, exist_ok=True)

    log(f"=== fetch start: {today} ===")
    ok, skipped, failed = 0, 0, 0

    for src in cfg["sources"]:
        label = src["label"]
        url = URL_TMPL.format(sid=src["sheet_id"], gid=src["gid"])
        out_path = out_dir / f"{label}.csv"
        log(f"-> {label} (gid={src['gid']})")
        try:
            data = http_get(url)
        except Exception as e:
            log(f"   FAILED: {e}")
            failed += 1
            continue

        # Dedupe vs previous snapshot (skip writing if identical content)
        prev = latest_snapshot_for(label, exclude=out_path)
        if prev and prev.read_bytes() == data:
            log(f"   unchanged vs {prev.parent.name} -> skip write")
            skipped += 1
            continue

        out_path.write_bytes(data)
        log(f"   wrote {out_path.relative_to(ROOT)} ({len(data)} bytes, sha256={sha256(data)[:12]})")
        ok += 1

    log(f"=== fetch done: wrote={ok} unchanged={skipped} failed={failed} ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
