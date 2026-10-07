"""Combine the latest raw/ snapshot AND the union of every snapshot ever pulled.

Outputs in output/:
    master_long.csv          long format of LATEST snapshot only (matches the web)
    master_long_history.csv  append-only, every snapshot we have ever pulled
    master_wide.xlsx         wide format of LATEST snapshot (one sheet per label)
    master_archive_long.csv  union of every (label, row_key, column) ever seen,
                             keeping the value from the most recent snapshot that
                             contained it, plus last_seen_snapshot stamp
    master_archive_wide.xlsx wide archive — one sheet per label with the full
                             historical row_key index (rows the web has since
                             dropped are retained)
"""
from __future__ import annotations
import json, sys, datetime as dt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "sources.json"
RAW_DIR = ROOT / "raw"
OUT_DIR = ROOT / "output"
LOG_PATH = ROOT / "combine.log"


def log(msg: str) -> None:
    line = f"[{dt.datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def safe_write_csv(df: pd.DataFrame, path: Path) -> bool:
    try:
        df.to_csv(path, index=False, encoding="utf-8")
        return True
    except PermissionError:
        log(f"  SKIP {path.name}: file is open (close it in Excel and re-run)")
        return False


def safe_write_xlsx(write_fn, path: Path) -> bool:
    try:
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            write_fn(xw)
        return True
    except PermissionError:
        log(f"  SKIP {path.name}: file is open (close it in Excel and re-run)")
        return False


def latest_snapshot_dir() -> Path:
    dirs = sorted((p for p in RAW_DIR.iterdir() if p.is_dir()), reverse=True)
    if not dirs:
        raise SystemExit("No raw snapshots — run fetch.py first.")
    return dirs[0]


def to_long(df: pd.DataFrame, label: str, category: str, snapshot: str) -> pd.DataFrame:
    """Melt any wide CSV into long format.

    The first column is treated as the row key (typically Date or Size). Every
    remaining column becomes a (column, value) pair.
    """
    if df.empty:
        return pd.DataFrame(columns=["snapshot_date", "category", "label", "row_key", "column", "value"])
    key_col = df.columns[0]
    long = df.melt(id_vars=[key_col], var_name="column", value_name="value")
    long = long.rename(columns={key_col: "row_key"})
    long.insert(0, "label", label)
    long.insert(0, "category", category)
    long.insert(0, "snapshot_date", snapshot)
    return long[["snapshot_date", "category", "label", "row_key", "column", "value"]]


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    snap_dir = latest_snapshot_dir()
    snapshot = snap_dir.name
    log(f"combining snapshot {snapshot}")

    long_frames: list[pd.DataFrame] = []
    wide_frames: dict[str, pd.DataFrame] = {}

    for src in cfg["sources"]:
        label, category = src["label"], src["category"]
        csv_path = snap_dir / f"{label}.csv"
        if not csv_path.exists():
            # Fall back to the most recent earlier snapshot if today's fetch skipped
            # an unchanged file.
            prev = sorted(RAW_DIR.glob(f"*/{label}.csv"), reverse=True)
            if not prev:
                log(f"  {label}: no snapshot found, skipping")
                continue
            csv_path = prev[0]
            log(f"  {label}: using earlier snapshot {csv_path.parent.name}")
        df = pd.read_csv(csv_path)
        df.columns = [str(c).strip() for c in df.columns]
        wide_frames[label] = df
        long_frames.append(to_long(df, label, category, snapshot))
        log(f"  {label}: {len(df)} rows x {len(df.columns)} cols")

    if not long_frames:
        log("nothing to combine")
        return 1

    master_long = pd.concat(long_frames, ignore_index=True)
    long_path = OUT_DIR / "master_long.csv"
    if safe_write_csv(master_long, long_path):
        log(f"wrote {long_path.relative_to(ROOT)} ({len(master_long)} rows)")

    # Append-only historical long file: keeps every snapshot we've ever pulled.
    hist_path = OUT_DIR / "master_long_history.csv"
    if hist_path.exists():
        hist = pd.read_csv(hist_path)
        # Replace any rows from same snapshot to keep idempotent
        hist = hist[hist["snapshot_date"] != snapshot]
        hist = pd.concat([hist, master_long], ignore_index=True)
    else:
        hist = master_long
    if safe_write_csv(hist, hist_path):
        log(f"wrote {hist_path.relative_to(ROOT)} ({len(hist)} rows total)")

    wide_path = OUT_DIR / "master_wide.xlsx"
    def _write_wide(xw):
        meta = pd.DataFrame(
            [
                {
                    "label": s["label"],
                    "category": s["category"],
                    "sheet_id": s["sheet_id"],
                    "gid": s["gid"],
                    "rows": len(wide_frames.get(s["label"], [])),
                    "note": s.get("note", ""),
                }
                for s in cfg["sources"]
            ]
        )
        meta.to_excel(xw, sheet_name="_meta", index=False)
        for label, df in wide_frames.items():
            df.to_excel(xw, sheet_name=label[:31], index=False)
    if safe_write_xlsx(_write_wide, wide_path):
        log(f"wrote {wide_path.relative_to(ROOT)}")

    # ---- Archive: union across every snapshot ever pulled ----
    write_archive(cfg)
    return 0


def write_archive(cfg: dict) -> None:
    """Build archive_long + archive_wide that retain row_keys the web has dropped.

    For each (label, row_key, column), keep the value from the most recent
    snapshot whose CSV contained that cell. Cells the web has since rolled out
    of view stay in the archive with their last-seen value.
    """
    category_by_label = {s["label"]: s["category"] for s in cfg["sources"]}
    labels = [s["label"] for s in cfg["sources"]]

    archive_rows: list[pd.DataFrame] = []
    wide_archives: dict[str, pd.DataFrame] = {}

    for label in labels:
        snapshots = sorted(RAW_DIR.glob(f"*/{label}.csv"))
        if not snapshots:
            continue
        # Build long frame across every snapshot for this label
        per_label_long: list[pd.DataFrame] = []
        for snap_csv in snapshots:
            snap_name = snap_csv.parent.name
            df = pd.read_csv(snap_csv)
            df.columns = [str(c).strip() for c in df.columns]
            if df.empty or len(df.columns) < 2:
                continue
            key_col = df.columns[0]
            # If row_key duplicates exist within a single snapshot, keep the
            # LAST occurrence — assume later row = corrected/updated value.
            df = df.drop_duplicates(subset=[key_col], keep="last")
            long = df.melt(id_vars=[key_col], var_name="column", value_name="value")
            long = long.rename(columns={key_col: "row_key"})
            long["snapshot_date"] = snap_name
            per_label_long.append(long)
        if not per_label_long:
            continue
        combined = pd.concat(per_label_long, ignore_index=True)
        # Drop nulls so a cell that was empty in a newer snapshot does not erase
        # a real value from an older snapshot.
        combined = combined.dropna(subset=["value"])
        # Sort so the latest snapshot wins on drop_duplicates(keep="last")
        combined = combined.sort_values(["row_key", "column", "snapshot_date"])
        latest = combined.drop_duplicates(subset=["row_key", "column"], keep="last")
        latest = latest.rename(columns={"snapshot_date": "last_seen_snapshot"})
        latest.insert(0, "label", label)
        latest.insert(0, "category", category_by_label[label])
        archive_rows.append(latest[["category", "label", "row_key", "column", "value", "last_seen_snapshot"]])

        # Wide archive sheet: row_key index × column, preserving the original
        # column order from the most recent snapshot
        latest_csv = snapshots[-1]
        latest_df = pd.read_csv(latest_csv)
        latest_df.columns = [str(c).strip() for c in latest_df.columns]
        col_order = list(latest_df.columns[1:])
        # Append any columns seen in older snapshots but not in the latest
        extra_cols = [c for c in latest["column"].unique() if c not in col_order]
        col_order = col_order + extra_cols
        # row_key order: preserve order from the most recent snapshot, append
        # any older row_keys after, in the order they first appeared
        latest_keys = latest_df.iloc[:, 0].astype(str).tolist()
        all_keys = latest["row_key"].astype(str).tolist()
        appended: list[str] = []
        seen = set(latest_keys)
        for k in all_keys:
            if k not in seen:
                appended.append(k); seen.add(k)
        row_order = latest_keys + appended
        wide = latest.pivot_table(
            index="row_key", columns="column", values="value",
            aggfunc="last",
        )
        wide = wide.reindex(index=row_order, columns=col_order)
        wide_archives[label] = wide

    if not archive_rows:
        log("archive: nothing to write")
        return

    arc_long = pd.concat(archive_rows, ignore_index=True)
    arc_long_path = OUT_DIR / "master_archive_long.csv"
    if safe_write_csv(arc_long, arc_long_path):
        log(f"wrote {arc_long_path.relative_to(ROOT)} ({len(arc_long)} rows, "
            f"covers {arc_long['last_seen_snapshot'].nunique()} snapshots)")

    arc_wide_path = OUT_DIR / "master_archive_wide.xlsx"
    def _write_arc(xw):
        for label, wide in wide_archives.items():
            wide.to_excel(xw, sheet_name=label[:31])
    if safe_write_xlsx(_write_arc, arc_wide_path):
        log(f"wrote {arc_wide_path.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
