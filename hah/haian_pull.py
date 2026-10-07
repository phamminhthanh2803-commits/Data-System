# -*- coding: utf-8 -*-
"""haian_pull.py — ban Python cua haian-schedule-daily.ps1 (07/10/2026), de cung 1 code chay tren Windows lan Linux/cloud.

HAIAN Schedule: lich tau HAH tu API kethop.haiants.vn. ps1 goc giu nguyen; logic y het:
  - Tu lay ngay HOM NAY + cac moc ETD moi 7 ngay toi +120 ngay; goi GetAllVessel + ShipSchedule cho moi tau
  - MERGE vao haian-schedule-master.csv theo khoa VoyDetail|PolId|PodId (moi de len cu), sap Vessel, ETD_iso
  - Dung lai 2 file gop theo voyage: haian-portcalls.csv (1 dong/cang) + haian-voyages.csv (1 dong/voyage);
    gop theo Vessel+Voyage, tach cum khi 2 leg cach nhau > 60 ngay (ma voyId lap lai qua nam)
  - Data ghi NGAY CANH SCRIPT (nhu $PSScriptRoot): doi thu muc thoai mai
  - CSV: moi o deu trong ngoac kep, UTF-8 BOM, CRLF (nhu Export-Csv -Encoding UTF8 cua PS 5.1)
  - Log haian-daily.log: "[yyyy-mm-dd HH:MM:SS] msg"
Khac ps1: loi nghiem trong / khong lay duoc danh sach tau -> exit 1 (ps1 exit 0) de runner bao WARN.
    python haian_pull.py
"""
import csv
import datetime as dt
import os
import re
import sys
import time
import traceback

import requests

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
MASTER_CSV = os.path.join(OUT_DIR, "haian-schedule-master.csv")   # file tich luy (history)
PORTCALLS_CSV = os.path.join(OUT_DIR, "haian-portcalls.csv")      # 1 dong / cang
VOYAGES_CSV = os.path.join(OUT_DIR, "haian-voyages.csv")          # 1 dong / voyage
LOG_FILE = os.path.join(OUT_DIR, "haian-daily.log")

LOOKAHEAD_DAYS = 120    # quet ETD tu hom nay toi +120 ngay
STEP_DAYS = 7           # moi tuan
PAUSE_S = 0.12          # nghi giua 2 request (lich su voi server)
CLUSTER_GAP_DAYS = 60

HEADERS = {"Accept": "*/*", "Referer": "https://eservice.haiants.vn/", "Origin": "https://eservice.haiants.vn"}
API_VESSELS = "https://kethop.haiants.vn/Booking/GetAllVessel"
API_SCHEDULE = "https://kethop.haiants.vn/Booking/ShipSchedule"

COLS = ["Vessel", "Voyage", "Service", "POL", "POL Terminal", "ETD", "ETA", "POD", "POD Terminal",
        "Transit (days)", "ClosingTime", "ShipId", "VoyDetail", "PolId", "PodId", "ETD_iso", "ETA_iso"]
PORTCALL_COLS = ["Vessel", "Voyage", "Service", "Seq", "Port", "Terminal", "ETA", "ETD", "VoyDetail"]
VOYAGE_COLS = ["Vessel", "Voyage", "Service", "NumPorts", "FirstETD", "LastETA", "Rotation", "VoyDetail"]


def log(msg):
    line = f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:                                             # noqa: BLE001
        pass


def s(v) -> str:
    """null -> '' (nhu Export-Csv)."""
    return "" if v is None else str(v)


def parse_dt(v):
    """[datetime]$iso cua PowerShell; khong parse duoc -> None."""
    if v is None or v == "":
        return None
    t = str(v).strip()
    try:
        return dt.datetime.fromisoformat(t)
    except ValueError:
        pass
    m = re.match(r"(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d)(?::(\d\d))?(?:\.(\d+))?", t)
    if m:
        y, mo, d, h, mi, se, fr = m.groups()
        return dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(se or 0), int((fr or "0").ljust(6, "0")[:6]))
    return None


def fmt_dt(iso) -> str:
    """Format-DT: '' neu rong; dd/MM/yyyy HH:mm; khong parse duoc -> chuoi goc."""
    if not iso:
        return ""
    t = parse_dt(iso)
    return t.strftime("%d/%m/%Y %H:%M") if t else str(iso)


def transit_days(etd, eta):
    a, b = parse_dt(etd), parse_dt(eta)
    if a is None or b is None:
        return ""
    return int(round((b - a).total_seconds() / 86400))          # round() ban-chan nhu [math]::Round


def get_vessels(sess):
    try:
        r = sess.get(API_VESSELS, headers=HEADERS, timeout=60)
        r.raise_for_status()
        v = r.json()
        return v if isinstance(v, list) else []
    except Exception as e:                                        # noqa: BLE001
        log(f"  ! GetAllVessel loi: {e}")
        return []


def get_schedule(sess, ship_id, etd):
    try:
        r = sess.post(API_SCHEDULE, params={"ShipId": ship_id, "ETD": etd},
                      headers={**HEADERS, "Content-Type": "application/json"}, data="", timeout=60)
        r.raise_for_status()
        v = r.json() if r.text.strip() else []
        return v if isinstance(v, list) else []
    except Exception as e:                                        # noqa: BLE001
        log(f"  ! ShipSchedule loi (etd={etd}): {e}")
        return []


def write_csv(path, cols, rows):
    """Export-Csv -NoTypeInformation -Encoding UTF8 (PS 5.1): BOM, moi o co ngoac kep, CRLF."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\r\n")
        w.writerow(cols)
        for r in rows:
            w.writerow([s(r.get(c)) for c in cols])


def add_port(ports, pid, name, terminal, arr_iso, dep_iso):
    key = pid or name
    if not key:
        return
    if key not in ports:
        ports[key] = {"Name": name, "Terminal": terminal, "Arr": arr_iso, "Dep": dep_iso}
        return
    p = ports[key]
    if not p["Name"] and name:
        p["Name"] = name
    if not p["Terminal"] and terminal:
        p["Terminal"] = terminal
    if arr_iso and not p["Arr"]:
        p["Arr"] = arr_iso
    if dep_iso and not p["Dep"]:
        p["Dep"] = dep_iso


def sort_time(p):
    return parse_dt(p["Arr"] or p["Dep"]) or dt.datetime.min


def main() -> int:
    log("===== BAT DAU pipeline =====")
    # 1) Nap master cu vao dict theo khoa
    store = {}
    if os.path.exists(MASTER_CSV):
        with open(MASTER_CSV, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                store[f"{row.get('VoyDetail', '')}|{row.get('PolId', '')}|{row.get('PodId', '')}"] = row
    before = len(store)
    log(f"Master cu: {before} chang")

    # 2) Danh sach tau + danh sach ngay ETD (tu dong tu hom nay)
    sess = requests.Session()
    vessels = get_vessels(sess)
    if not vessels:
        log("Khong lay duoc tau. DUNG.")
        return 1
    log(f"So tau: {len(vessels)}")
    today = dt.date.today()
    etds = [(today + dt.timedelta(days=i)).strftime("%m/%d/%Y") for i in range(0, LOOKAHEAD_DAYS + 1, STEP_DAYS)]
    log(f"Quet ETD: {etds[0]} -> {etds[-1]} ({len(etds)} moc)")

    # 3) Goi API + merge
    calls = 0
    for ship in vessels:
        ship_id = ship.get("shipId") if isinstance(ship, dict) else None
        for etd in etds:
            legs = get_schedule(sess, ship_id, etd)
            calls += 1
            for leg in legs:
                if not isinstance(leg, dict):
                    continue
                rec = {
                    "Vessel": s(leg.get("vesselName")),
                    "Voyage": s(leg.get("voyId")).strip(),
                    "Service": s(leg.get("lineCode")),
                    "POL": s(leg.get("polloc")),
                    "POL Terminal": s(leg.get("pol")),
                    "ETD": fmt_dt(leg.get("etd")),
                    "ETA": fmt_dt(leg.get("eta")),
                    "POD": s(leg.get("podloc")),
                    "POD Terminal": s(leg.get("pod")),
                    "Transit (days)": transit_days(leg.get("etd"), leg.get("eta")),
                    "ClosingTime": fmt_dt(leg.get("closingTime")),
                    "ShipId": s(ship_id),
                    "VoyDetail": s(leg.get("voyDetail")),
                    "PolId": s(leg.get("polId")),
                    "PodId": s(leg.get("podId")),
                    "ETD_iso": s(leg.get("etd")),
                    "ETA_iso": s(leg.get("eta")),
                }
                store[f"{rec['VoyDetail']}|{rec['PolId']}|{rec['PodId']}"] = rec
            time.sleep(PAUSE_S)
    after = len(store)
    log(f"Da goi {calls} request. Master moi: {after} chang (+{after - before} moi/cap nhat)")

    # 4) Ghi master (dong nhat schema)
    records = sorted(store.values(), key=lambda r: (s(r.get("Vessel")), s(r.get("ETD_iso"))))
    write_csv(MASTER_CSV, COLS, records)
    log(f"Da ghi master: {MASTER_CSV}")

    # 5) Dung lai theo voyage — GOP theo Vessel+Voyage, tach cum khi cach nhau > CLUSTER_GAP_DAYS
    groups = {}
    for r in store.values():
        groups.setdefault((s(r.get("Vessel")), s(r.get("Voyage"))), []).append(r)
    portcall_rows, voyage_rows = [], []
    for (_, _), grp in groups.items():
        ordered = sorted(grp, key=lambda r: parse_dt(r.get("ETD_iso")) or dt.datetime.min)
        clusters, cur, prev = [], [], None
        for r in ordered:
            t = parse_dt(r.get("ETD_iso"))
            if cur and prev and t and (t - prev).total_seconds() / 86400 > CLUSTER_GAP_DAYS:
                clusters.append(cur)
                cur = []
            cur.append(r)
            if t:
                prev = t
        if cur:
            clusters.append(cur)
        for recs in clusters:
            ports = {}
            for r in recs:
                add_port(ports, r.get("PolId"), r.get("POL"), r.get("POL Terminal"), None, r.get("ETD_iso"))   # cang DI -> ETD
                add_port(ports, r.get("PodId"), r.get("POD"), r.get("POD Terminal"), r.get("ETA_iso"), None)   # cang DEN -> ETA
            port_list = sorted(ports.values(), key=sort_time)
            if not port_list:
                continue
            vd = ";".join(sorted({s(r.get("VoyDetail")) for r in recs}))
            svc = next((r.get("Service") for r in recs if r.get("Service")), "")
            vessel, voyage = s(recs[0].get("Vessel")), s(recs[0].get("Voyage"))
            for seq, p in enumerate(port_list, 1):
                portcall_rows.append({"Vessel": vessel, "Voyage": voyage, "Service": svc, "Seq": seq,
                                      "Port": p["Name"], "Terminal": p["Terminal"],
                                      "ETA": fmt_dt(p["Arr"]), "ETD": fmt_dt(p["Dep"]), "VoyDetail": vd})
            first, last = port_list[0], port_list[-1]
            first_t = first["Dep"] or first["Arr"]
            last_t = last["Arr"] or last["Dep"]
            rotation = " > ".join(s(p["Name"]) if p["Name"] else s(p["Terminal"]) for p in port_list)
            voyage_rows.append({"Vessel": vessel, "Voyage": voyage, "Service": svc, "NumPorts": len(port_list),
                                "FirstETD": fmt_dt(first_t), "LastETA": fmt_dt(last_t), "Rotation": rotation, "VoyDetail": vd})
    portcall_rows.sort(key=lambda r: (r["Vessel"], r["VoyDetail"], r["Seq"]))
    voyage_rows.sort(key=lambda r: (r["Vessel"], r["FirstETD"]))
    write_csv(PORTCALLS_CSV, PORTCALL_COLS, portcall_rows)
    write_csv(VOYAGES_CSV, VOYAGE_COLS, voyage_rows)
    log(f"Da ghi: {PORTCALLS_CSV} ({len(portcall_rows)} dong), {VOYAGES_CSV} ({len(voyage_rows)} voyage)")
    log("===== XONG =====")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception as e:                                        # noqa: BLE001
        log(f"LOI nghiem trong: {e}")
        log(traceback.format_exc())
        sys.exit(1)
