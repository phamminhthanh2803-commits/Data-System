# -*- coding: utf-8 -*-
"""sync_data.py — dong bo DATA giua Google Drive (rclone) va cay thu muc chay pipeline, theo data_manifest.py.

Chon thu muc theo DUNG cac buoc se chay hom nay (runlib.select_steps: slot, --only, CLOUD_SKIP, windows_only) nen
--only a,b khi chay tay cung chi keo thu muc buoc do can.

    python sync_data.py down --hub market-data --slot PM [--only a,b] [--job cloud|laptop]   # Drive -> local (rclone copy, khong xoa)
    python sync_data.py up   --hub market-data --slot PM [--only a,b] [--job cloud|laptop]   # local -> Drive
         chu thu muc (owner == job): rclone sync (xoa file da mat, --max-delete 50); ben kia: rclone copy chi file *_up_include
         + copyto status-<slot>.txt len gdrive:pipeline-data/<hub>/
    python sync_data.py app                       # Drive -> local toan bo thu muc app Streamlit doc (APP_FOLDERS)
    python sync_data.py seed [--skip-bond]        # lan dau: D:\\ (HUB_SRC) -> Drive (rclone copy)
    them --dry-run de xem lenh rclone; --remote gdrive:pipeline-data (hoac env RCLONE_REMOTE)
Thu muc local = env MD_ROOT/SHIP_ROOT/HAH_DIR (cloud: $GITHUB_WORKSPACE/<hub>; laptop: D:\\pipeline-data\\<hub>).
rclone: env RCLONE (duong dan) > PATH > ban winget (xem find_rclone).
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "market-data"))          # runlib.select_steps (cung luat chon buoc voi runner)
import data_manifest as dm  # noqa: E402
from runlib import select_steps  # noqa: E402

WINGET_RCLONE = os.path.join(os.path.expanduser("~"), "AppData", "Local", "Microsoft", "WinGet", "Packages",
                             "Rclone.Rclone_Microsoft.Winget.Source_8wekyb3d8bbwe", "rclone-v1.75.1-windows-amd64", "rclone.exe")
COMMON = ["-L", "--fast-list", "--transfers", "16", "--checkers", "32", "--stats-one-line", "--stats", "60s",
          "--retries", "5", "--low-level-retries", "20", "--drive-chunk-size", "64M"]


def find_rclone() -> str:
    for c in (os.environ.get("RCLONE"), shutil.which("rclone"), WINGET_RCLONE):
        if c and os.path.exists(c):
            return c
    if shutil.which("rclone"):
        return "rclone"
    sys.exit("Khong tim thay rclone (cai: winget install Rclone.Rclone, hoac dat env RCLONE=duong dan rclone.exe)")


def load_steps(hub: str) -> list:
    """Doc STEPS tu <repo>/<hub>/run_slot.py (import runlib tu <repo>/market-data)."""
    if hub not in ("market-data", "shipping"):
        return []
    path = os.path.join(HERE, hub, "run_slot.py")
    spec = importlib.util.spec_from_file_location(f"run_slot_{hub.replace('-', '_')}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.STEPS


def selected_step_names(hub: str, slot: str, only: list, job: str) -> list:
    steps = load_steps(hub)
    # cloud: tren Linux windows_only bi bo; laptop: giu luat Windows
    chosen = select_steps(steps, slot, only, None, is_win=(job == "laptop"))
    return [s.name for s in chosen]


def plan(hub: str, slot: str, only: list, job: str) -> tuple[dict, dict, list]:
    """-> (down: key -> include|None, up_full: key -> Folder, up_partial: [(Folder, include)])"""
    names = selected_step_names(hub, slot, only, job)
    down: dict = {}
    writes: set = set()
    for n in names:
        for key, mode, inc in dm.STEP_FOLDERS.get(n, []):
            f = dm.FOLDERS[key]
            if not f.drive:
                continue
            if key in down and (down[key] is None or inc is None):
                down[key] = None
            elif key in down:
                down[key] = sorted(set(down[key]) | set(inc))
            else:
                down[key] = None if inc is None else list(inc)
            if mode == "rw":
                writes.add(key)
    up_full, up_part = {}, []
    for key in sorted(writes):
        f = dm.FOLDERS[key]
        if f.owner == job:
            up_full[key] = f
        else:
            inc = f.cloud_up_include if job == "cloud" else f.laptop_up_include
            if inc:
                up_part.append((f, inc))
    return names, down, up_full, up_part


def write_filter(f: dm.Folder, include=None, extra_exclude=()) -> str:
    """File filter rclone: '-' exclude (code + rieng + extra) roi '+' include (neu co) va '- **'."""
    inc = include if include is not None else f.include
    lines = []
    for p in dm.CODE_EXCLUDE + f.exclude + list(extra_exclude):
        lines.append(f"- {p}")
    if inc is not None:
        for p in inc:
            lines.append(f"+ /{p}")
        lines.append("- **")
    fd, path = tempfile.mkstemp(prefix="rclone_filter_", suffix=".txt", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path


def rclone(rc: str, args: list, dry: bool) -> int:
    cmd = [rc] + args + COMMON
    print("  $ " + " ".join(a if " " not in a else f'"{a}"' for a in cmd), flush=True)
    if dry:
        return 0
    r = subprocess.call(cmd)
    if r != 0:
        print(f"  ! rclone exit {r}", flush=True)
    return r


def do_down(rc, remote, folders: dict, dry) -> int:
    bad = 0
    for key, inc in folders.items():
        f = dm.FOLDERS[key]
        local = f.local_root()
        os.makedirs(local, exist_ok=True)
        flt = write_filter(f, inc)
        print(f"-- keo ve {key}{' (1 phan)' if inc else ''} -> {local}")
        bad += rclone(rc, ["copy", f.remote(remote), local, "--filter-from", flt], dry) != 0
    return bad


def do_up(rc, remote, hub, slot, up_full: dict, up_part: list, dry, job="cloud") -> int:
    bad = 0
    for key, f in up_full.items():
        local = f.local_root()
        if not os.path.isdir(local):
            print(f"-- {key}: khong co thu muc local, bo qua")
            continue
        # laptop la chu (cangvu-hcm): KHONG dong vao file cloud ghi (3 file enriched) -> loai khoi sync
        extra = [f"/{p}" for p in f.cloud_up_include] if job == "laptop" else []
        flt = write_filter(f, extra_exclude=extra)
        print(f"-- day len (sync, chu={f.owner}) {key}")
        bad += rclone(rc, ["sync", local, f.remote(remote), "--filter-from", flt, "--max-delete", "50"], dry) != 0
    for f, inc in up_part:
        local = f.local_root()
        flt = write_filter(f, inc)
        print(f"-- day len 1 phan (copy) {f.key}: {', '.join(inc)}")
        bad += rclone(rc, ["copy", local, f.remote(remote), "--filter-from", flt], dry) != 0
    if hub in dm.HUB_ENV and slot and job == "cloud":          # status-<slot>.txt tren Drive = cua cloud (laptop doi file nay)
        base = os.environ.get(dm.HUB_ENV[hub]) or dm.HUB_SRC[hub]
        st = os.path.join(base, f"status-{slot}.txt")
        if os.path.exists(st):
            bad += rclone(rc, ["copyto", st, f"{remote}/{hub}/status-{slot}.txt"], dry) != 0
    return bad


def do_app(rc, remote, dry) -> int:
    bad = 0
    for key, inc in dm.APP_FOLDERS:
        f = dm.FOLDERS[key]
        local = f.local_root()
        os.makedirs(local, exist_ok=True)
        flt = write_filter(f, inc)
        print(f"-- app: keo ve {key} -> {local}")
        bad += rclone(rc, ["copy", f.remote(remote), local, "--filter-from", flt], dry) != 0
    return bad


def do_seed(rc, remote, skip_bond: bool, dry) -> int:
    bad = 0
    for f in dm.FOLDERS.values():
        if not f.drive or (skip_bond and f.path == "bond-pivot"):
            continue
        src = f.src_root()
        if not os.path.isdir(src):
            print(f"-- {f.key}: khong thay {src}, bo qua")
            continue
        flt = write_filter(f)
        print(f"-- seed {f.key}: {src} -> {f.remote(remote)}")
        bad += rclone(rc, ["copy", src, f.remote(remote), "--filter-from", flt], dry) != 0
    for hub in ("market-data", "shipping"):
        for slot in ("AM", "PM"):
            st = os.path.join(dm.HUB_SRC[hub], f"status-{slot}.txt")
            if os.path.exists(st):
                bad += rclone(rc, ["copyto", st, f"{remote}/{hub}/status-{slot}.txt"], dry) != 0
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("action", choices=["down", "up", "app", "seed", "plan"])
    ap.add_argument("--hub", default="market-data", choices=["market-data", "shipping"])
    ap.add_argument("--slot", default="", choices=["", "AM", "PM"])
    ap.add_argument("--only", default="")
    ap.add_argument("--job", default="cloud" if os.environ.get("CLOUD") == "1" or os.name != "nt" else "laptop",
                    choices=["cloud", "laptop"])
    ap.add_argument("--remote", default=os.environ.get("RCLONE_REMOTE", "gdrive:pipeline-data"))
    ap.add_argument("--skip-bond", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    only = [x.strip() for x in a.only.split(",") if x.strip()]
    rc = "rclone" if a.dry_run and not shutil.which("rclone") and not os.path.exists(WINGET_RCLONE) else find_rclone()

    if a.action == "app":
        return 1 if do_app(rc, a.remote, a.dry_run) else 0
    if a.action == "seed":
        return 1 if do_seed(rc, a.remote, a.skip_bond, a.dry_run) else 0
    if not a.slot:
        sys.exit("can --slot AM|PM")
    names, down, up_full, up_part = plan(a.hub, a.slot, only, a.job)
    print(f"[{a.action}] hub={a.hub} slot={a.slot} job={a.job} buoc: {', '.join(names) or '(khong co)'}")
    # hub 'hah' dung chung voi shipping: dong bo khi buoc haian chay
    if a.action == "plan":
        print("  keo ve :", {k: (v or 'toan bo') for k, v in down.items()})
        print("  day len:", list(up_full), "+ 1 phan:", [(f.key, inc) for f, inc in up_part])
        return 0
    if a.action == "down":
        return 1 if do_down(rc, a.remote, down, a.dry_run) else 0
    # up: buoc dung chung hub 'hah' (haian) di cung shipping
    return 1 if do_up(rc, a.remote, a.hub, a.slot, up_full, up_part, a.dry_run, a.job) else 0


if __name__ == "__main__":
    sys.exit(main())
