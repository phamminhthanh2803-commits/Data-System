# -*- coding: utf-8 -*-
"""Weekly pipeline runner (Task Scheduler goi qua run_daily.ps1).

Phan CHUNG (1 lan):
 1. bond master  — re-pull toan bo (truong luu ky/tinh trang thay doi)
 2. feed + ttph  — incremental (moi->cu, dung khi het tin moi)
Phan RIENG (lap qua cac firm enabled trong config/firms.json):
 3. analyze_firm — flag + map SPV + aggregate + report
 4. level2       — doc PDF backlog (cap trong level2_update.py)
 5. snapshot     — output/<firm>/history/ + logs/summary.csv
Them 10/2026 (sau timeline): bond_prices (gia GD hang ngay san TPDNRL) ->
 tpcp_curve (spot TPCP hnx.vn) -> bond_yields (YTM + spread) -> yield_curve
 (duong cong theo nganh, 5 moc 0/1/3/6/12M + PNG).

Log: logs/pipeline_YYYY-MM-DD.log
"""
import csv
import os
import shutil
import subprocess
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.join(ROOT, "scripts"))


def main():
    os.chdir(ROOT)
    import hnx_common as firms_cfg
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs("logs", exist_ok=True)
    log = open(os.path.join("logs", "pipeline_%s.log" % today), "a", encoding="utf-8")

    def say(msg):
        line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    def run_step(name, cmd, critical):
        say("step %s ..." % name)
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([PY] + cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env)
        log.write(r.stdout or "")
        if r.returncode == 2:
            say("step %s WARNING: file dich bi khoa (Excel?), giu ban cu" % name)
            return name + ":locked"
        if r.returncode != 0:
            log.write(r.stderr or "")
            say("step %s FAILED (rc=%d)" % (name, r.returncode))
            if critical:
                say("critical step failed — aborting")
                log.close()
                sys.exit(1)
            return name
        tail = (r.stdout or "").strip().splitlines()
        say("step %s ok (%s)" % (name, tail[-1][:100] if tail else ""))
        return None

    say("=== pipeline start ===")
    failed = []
    # ---- shared pulls ----
    for name, cmd, critical in [
            ("bond_master", ["scripts/pull_hnx.py", "master"], True),
            ("update_feeds", ["scripts/pull_hnx.py", "update"], True)]:
        f = run_step(name, cmd, critical)
        if f:
            failed.append(f)

    # ---- arranger evidence (toan thi truong, chip away backlog) ----
    f = run_step("arranger_evidence",
                 ["scripts/extract_arrangers.py", "--limit", "50"], False)
    if f:
        failed.append(f)

    # ---- enrich chi tiet bond moi (ISIN, dam bao, DKGD, dai dien NSHTP) ----
    f = run_step("bond_detail",
                 ["scripts/enrich_bond_detail.py", "--limit", "300"], False)
    if f:
        failed.append(f)

    # ---- fact table timeline toan thi truong (pivot theo quy) ----
    f = run_step("timeline", ["scripts/build_timeline.py"], False)
    if f:
        failed.append(f)

    # ---- gia giao dich + duong cong loi suat (them 10/2026) ----
    # prices/tpcp: incremental 20-30 ngay (lich su server day du nen chay tuan van kin)
    for name, cmd in [("bond_prices", ["scripts/pull_prices.py", "update"]),
                      ("tpcp_curve", ["scripts/pull_tpcp_curve.py", "update"]),
                      ("bond_yields", ["scripts/bond_yields.py"]),
                      ("yield_curve", ["scripts/yield_curve.py"])]:
        f = run_step(name, cmd, False)
        if f:
            failed.append(f)

    # ---- per-firm ----
    summary_rows = []
    for key in firms_cfg.firms_enabled():
        f = run_step("analyze:%s" % key, ["scripts/analyze_firm.py", key], True)
        if f:
            failed.append(f)
        # snapshot + so lieu tong
        out = firms_cfg.firm_out_dir(key)
        hist = os.path.join(out, "history")
        os.makedirs(hist, exist_ok=True)
        freq_path = os.path.join(out, "issuer_frequency.csv")
        if os.path.exists(freq_path):
            shutil.copy(freq_path, os.path.join(hist, "issuer_frequency_%s.csv" % today))
        internal = set(firms_cfg.firm_get(key).get("internal_groups", []))
        bonds = list(csv.DictReader(open(os.path.join(out, "bonds_raw.csv"), encoding="utf-8-sig")))
        ext = [b for b in bonds if b.get("parent_group") not in internal]
        tot = sum(float(b.get("gia_tri_phat_hanh_ty") or 0) for b in ext)
        summary_rows.append([today, key, len(ext), round(tot, 1),
                             ";".join(x for x in failed if x.endswith(key) or ":" not in x)])
        say("%s: %d bond khach hang ngoai, %.0f ty" % (key, len(ext), tot))

    summary = "logs/summary.csv"
    new_file = not os.path.exists(summary)
    with open(summary, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["date", "firm", "bonds_flagged_ext", "value_ty_ext", "failed_steps"])
        w.writerows(summary_rows)
    say("=== pipeline done ===")
    log.close()


if __name__ == "__main__":
    main()
