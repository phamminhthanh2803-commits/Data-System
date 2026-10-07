# -*- coding: utf-8 -*-
r"""update_nganh_daily.py - CAP NHAT HANG NGAY file nganh IB&Brokerage_Nganh.xlsx theo kieu CHI THEM (append-only), ~1 phut.

NGUYEN TAC (24/09/2026, yeu cau PV2): moi lan chay chi THEM du lieu moi vao dung file OneDrive dang giao;
KHONG dung lai file, KHONG chep file khac de len; giu nguyen moi sheet/dong/cot/o user tu them.
Ngoai le: so cua RECENT_Q quy gan nhat (quy moi nhat + quy lien truoc) DUOC GHI DE bang so moi (dieu chinh BCTC, gia chot phien,
VSDC sua so); quy cu hon dong bang. Ghi de chi o cot pipeline cua dong co khoa trung; dong/cot user them trong bang khong dung.

Phan thay doi moi ngay: gia co phieu (tv-history.csv, buoc tvhistory 18:30) -> dinh gia nganh/tung ma + LNST TTM;
moi thang: so TK giao dich VSDC (buoc vsdc-accounts thu Hai).

Cac buoc:
 1. build_valuation_ck.py  -> valuation_nganh_ck_daily.csv, valuation_ck_stocks_daily.csv, npat_nganh_ck_quarterly.csv
 2. Sao luu file OneDrive -> excel_feed\_backup\daily\ (giu 10 ban gan nhat).
 3. Mo TRUC TIEP file OneDrive excel_feed\IB&Brokerage_Nganh.xlsx (COM):
    - tbl_DinhGia / tbl_DinhGia_Ma / tbl_NPAT / tbl_TK: NOI THEM dong co khoa chua co (APPEND_KEYS); dong thuoc RECENT_Q quy
      gan nhat (theo PERIOD_COL) ma so khac -> ghi de dung o cot CSV; dong cu hon giu nguyen; khong xoa dong nao.
    - Table2 sheet 'So TK mo moi': noi thang moi + keo cong thuc dong cuoi; thang trong RECENT_Q quy gan nhat -> ghi de 5 cot so.
    - Drivers (GTGD dong 28-35, khoi 64-85): dien o trong; RECENT_Q cot ky cuoi cua dong so thi truong -> ghi de (o cong thuc/chu giu).
    -> luu tai cho. Ban lam viec excel_feed\logic\ duoc chep lai TU file OneDrive (chieu nguoc) de cac script khac dung.
    File OneDrive dang mo trong Excel -> KHONG dung vao, bao WARN (exit 3); lan chay sau them bu (khoa chua co van chua co).
Chay: python update_nganh_daily.py [--no-valuation] [--file <xlsx>]     (buoc 'nganh-ck' trong Market Data PM)
"""
import argparse, glob, os, shutil, subprocess, sys, time
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_presentation as P                                       # dung lai OUTX, FINAL, DATA_SHEETS, to_serial, com_retry

APPEND_KEYS = {"tbl_DinhGia": ["date"], "tbl_DinhGia_Ma": ["ticker", "date"], "tbl_NPAT": ["period"], "tbl_TK": ["date"]}
PERIOD_COL = {"tbl_DinhGia": "date", "tbl_DinhGia_Ma": "date", "tbl_NPAT": "qend", "tbl_TK": "date"}   # cot xac dinh quy cua dong
RECENT_Q = 2                                                        # so quy gan nhat duoc ghi de (quy moi nhat + quy lien truoc)
BACKUP_DIR = os.path.join(P.FEED, "_backup", "daily")
KEEP_BACKUPS = 10


def log(m):
    print(m, flush=True)


def find_table(wb, tbl):
    for i in range(1, wb.Worksheets.Count + 1):
        ws = wb.Worksheets(i)
        for j in range(1, ws.ListObjects.Count + 1):
            lo = ws.ListObjects(j)
            if lo.Name == tbl:
                return ws, lo
    return None, None


def _norm(v):
    """Khoa so sanh duoc giua gia tri Excel va CSV: so ngay serial -> int, chuoi -> strip."""
    if v is None:
        return None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if hasattr(v, "year") and hasattr(v, "toordinal"):              # pywintypes datetime
        return int((pd.Timestamp(v.year, v.month, v.day) - P.EPOCH).days)
    return str(v).strip() if isinstance(v, str) else v


def _rows(rng):
    v = rng.Value
    if v is None:
        return []
    return [list(r) for r in v] if isinstance(v, tuple) else [[v]]


def _same(a, b):
    a, b = _norm(a), _norm(b)
    if isinstance(a, float) and a != a:
        a = None
    if isinstance(b, float) and b != b:
        b = None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return a == b


def recent_quarters(dates, n=RECENT_Q):
    """Tap quy (pd.Period) cua n quy gan nhat tinh tu ngay lon nhat."""
    q = pd.to_datetime(dates, errors="coerce").dropna().dt.to_period("Q")
    if q.empty:
        return set()
    top = q.max()
    return {top - k for k in range(n)}


def merge_table(wb, tbl, csv_path, date_cols, keys, pcol):
    """Bang Excel tbl <- CSV: (1) noi dong co khoa chua co; (2) dong co khoa trung thuoc RECENT_Q quy gan nhat ma so khac
    -> ghi de dung cac o cot CSV. Dong cu hon, dong/cot user tu them: khong dung. Tra ve so dong them + so dong sua."""
    ws, lo = find_table(wb, tbl)
    if lo is None:
        log(f"  ! khong thay bang {tbl} trong file -> bo qua (khong tu tao sheet moi)"); return 0
    df = pd.read_csv(csv_path, encoding="utf-8-sig", dtype={"period": str})
    rq = recent_quarters(df[pcol]) if pcol in df.columns else set()
    in_recent = (pd.to_datetime(df[pcol], errors="coerce").dt.to_period("Q").isin(rq) if rq
                 else pd.Series(False, index=df.index)).tolist()
    for c in date_cols:
        if c in df.columns:
            df[c] = P.to_serial(df[c])
    hdr = [str(h) for h in lo.HeaderRowRange.Value[0]]
    miss = [k for k in keys if k not in hdr or k not in df.columns]
    if miss:
        log(f"  ! {tbl}: thieu cot khoa {miss} -> bo qua"); return 0
    extra = [c for c in df.columns if c not in hdr]
    if extra:
        log(f"  ! {tbl}: CSV co cot moi {extra} - khong them cot vao bang (giu cau truc file)")
    own = [c for c in df.columns if c in hdr]                         # cot pipeline; cot user them trong bang -> khong dung
    r0, c0 = lo.HeaderRowRange.Row, lo.Range.Column
    n_old = lo.DataBodyRange.Rows.Count if lo.DataBodyRange is not None else 0
    body = _rows(lo.DataBodyRange) if n_old else []
    kidx = [hdr.index(k) for k in keys]
    pos = {}
    for i, row in enumerate(body):
        pos.setdefault(tuple(_norm(row[j]) for j in kidx), i)
    recs = df.astype(object).where(pd.notna(df), None)
    add, upd = [], 0
    for rec, is_recent in zip(recs.itertuples(index=False), in_recent):
        d = dict(zip(df.columns, rec))
        k = tuple(_norm(d[x]) for x in keys)
        if any(x is None for x in k):
            continue
        if k not in pos:
            add.append([d.get(h) for h in hdr]); pos[k] = -1; continue
        i = pos[k]
        if i < 0 or not is_recent:
            continue
        cur = body[i]
        diff = [c for c in own if not _same(cur[hdr.index(c)], d[c])]
        if diff:
            for c in diff:                                             # tung o cot pipeline khac -> ghi de
                ws.Cells(r0 + 1 + i, c0 + hdr.index(c)).Value = d[c]
            upd += 1
    if add:
        top = r0 + 1 + n_old
        lo.Resize(ws.Range(ws.Cells(r0, c0), ws.Cells(top + len(add) - 1, c0 + len(hdr) - 1)))
        ws.Range(ws.Cells(top, c0), ws.Cells(top + len(add) - 1, c0 + len(hdr) - 1)).Value = add
        for c in date_cols:
            if c in hdr:
                j = hdr.index(c)
                ws.Range(ws.Cells(top, c0 + j), ws.Cells(top + len(add) - 1, c0 + j)).NumberFormat = "yyyy-mm-dd"
    rq_s = ",".join(str(q) for q in sorted(rq)) or "-"
    log(f"  {tbl}: {n_old:,} -> {n_old + len(add):,} dong (+{len(add):,} moi, sua {upd:,} dong quy {rq_s})")
    return len(add) + upd


def append_table2(wb):
    """Sheet 'So TK mo moi': noi cac thang VSDC moi hon thang cuoi cua Table2; cot tinh = keo cong thuc dong cuoi; refresh pivot."""
    if not os.path.exists(P.VSDC_T2):
        log("  ! khong co vsdc_tk_ndt_table2.csv -> giu Table2"); return 0
    ws = wb.Worksheets("Số TK mở mới")
    lo = ws.ListObjects("Table2")
    hr, c0, ncol = lo.HeaderRowRange.Row, lo.Range.Column, lo.Range.Columns.Count
    n_old = lo.DataBodyRange.Rows.Count
    last = _norm(ws.Cells(hr + n_old, c0).Value)                     # serial ngay thang cuoi
    t2 = pd.read_csv(P.VSDC_T2, encoding="utf-8-sig").sort_values("Date").reset_index(drop=True)
    t2["_s"] = P.to_serial(t2["Date"])
    rq = recent_quarters(t2["Date"])
    body_old = _rows(ws.Range(ws.Cells(hr + 1, c0), ws.Cells(hr + n_old, c0 + 5)))
    pos = {_norm(r[0]): i for i, r in enumerate(body_old)}
    upd = 0
    for _, r in t2[pd.to_datetime(t2.Date).dt.to_period("Q").isin(rq)].iterrows():   # thang thuoc RECENT_Q quy gan nhat -> ghi de so
        i = pos.get(_norm(float(r["_s"])))
        if i is None:
            continue
        vals = [float(v) for v in r.iloc[1:6]]
        if not all(_same(a, b) for a, b in zip(body_old[i][1:6], vals)):
            ws.Range(ws.Cells(hr + 1 + i, c0 + 1), ws.Cells(hr + 1 + i, c0 + 5)).Value = [vals]; upd += 1
    new = t2[t2["_s"] > (last or 0)]
    if new.empty:
        log(f"  Số TK mở mới: Table2 {n_old} thang, khong co thang moi, sua {upd} thang")
        if upd:
            ws.Calculate()
        return upd
    f_last = ws.Range(ws.Cells(hr + n_old, c0 + 6), ws.Cells(hr + n_old, c0 + ncol - 1)).FormulaR1C1[0]
    top, n = hr + n_old + 1, len(new)
    lo.Resize(ws.Range(ws.Cells(hr, c0), ws.Cells(top + n - 1, c0 + ncol - 1)))
    body = [[float(r["_s"])] + [float(v) for v in r.iloc[1:6]] for _, r in new.iterrows()]
    ws.Range(ws.Cells(top, c0), ws.Cells(top + n - 1, c0 + 5)).Value = body
    for j, f in enumerate(f_last):                                   # cong thuc R1C1 cua dong cuoi -> dong moi (chi o moi)
        if isinstance(f, str) and f.startswith("="):
            ws.Range(ws.Cells(top, c0 + 6 + j), ws.Cells(top + n - 1, c0 + 6 + j)).FormulaR1C1 = f
    ws.Range(ws.Cells(top, c0), ws.Cells(top + n - 1, c0)).NumberFormat = "dd/mm/yyyy"
    ws.Range(ws.Cells(top, c0 + 1), ws.Cells(top + n - 1, c0 + 7)).NumberFormat = "#,##0"
    ws.Calculate()
    for i in range(1, ws.PivotTables().Count + 1):                    # pivot tro dia chi co dinh -> mo rong ra bang moi
        try:
            pt = ws.PivotTables(i)
            pt.ChangePivotCache(wb.PivotCaches().Create(1, f"'{ws.Name}'!{lo.Range.Address}")); pt.RefreshTable()
        except Exception as e:                                       # noqa: BLE001
            log(f"  (pivot So TK #{i}) {e}")
    log(f"  Số TK mở mới: Table2 {n_old} -> {n_old + n} thang (+{n}, den {new.Date.iloc[-1]}), sua {upd} thang")
    return n + upd


def backup(path):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, time.strftime("IB&Brokerage_Nganh_%Y%m%d_%H%M%S.xlsx"))
    shutil.copy2(path, dst)
    for old in sorted(glob.glob(os.path.join(BACKUP_DIR, "IB&Brokerage_Nganh_*.xlsx")))[:-KEEP_BACKUPS]:
        try:
            os.remove(old)
        except OSError:
            pass
    return dst


def excel_app():
    import win32com.client as win32
    try:
        return win32.DispatchEx("Excel.Application")
    except AttributeError:                                           # cache gen_py hong (23/09/2026: 'no attribute CLSIDToClassMap') -> xoa, tao lai
        import win32com
        for d in glob.glob(os.path.join(win32com.__gen_path__, "00020813-0000-0000-C000-000000000046*")):
            shutil.rmtree(d, ignore_errors=True)
        log("  (xoa cache win32com gen_py Excel bi hong, thu lai)")
        return win32.DispatchEx("Excel.Application")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-valuation", action="store_true")
    ap.add_argument("--file", default=P.FINAL, help="file dich (mac dinh: file OneDrive dang giao)")
    a = ap.parse_args()
    t0 = time.time()
    target = os.path.abspath(a.file)
    if not os.path.exists(target):
        log(f"LOI: chua co {target}"); return 2
    if not a.no_valuation:
        log("build_valuation_ck.py ...")
        r = subprocess.run([sys.executable, os.path.join(HERE, "build_valuation_ck.py")], env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if r.returncode != 0:
            log(f"  ! build_valuation_ck exit {r.returncode} - van them tu so lieu hien co")
    try:
        with open(target, "r+b"):                                    # user dang mo file trong Excel -> khoa ghi
            pass
    except OSError:
        log(f"  ! {target} dang mo (bi khoa) -> KHONG cap nhat hom nay, lan sau them bu"); return 3
    log(f"  sao luu -> {backup(target)}")
    xl = excel_app(); xl.Visible = False; xl.DisplayAlerts = False; xl.ScreenUpdating = False
    added = 0
    try:
        wb = xl.Workbooks.Open(target, UpdateLinks=0)
        if wb.ReadOnly:
            wb.Close(False); log(f"  ! {target} mo o che do chi doc -> KHONG cap nhat"); return 3
        xl.Calculation = -4135; xl.EnableEvents = False
        for name, tbl, csvp, dcols in P.DATA_SHEETS:
            if tbl not in APPEND_KEYS:
                continue
            if not os.path.exists(csvp):
                log(f"  ! thieu {csvp}"); continue
            try:
                added += P.com_retry(lambda: merge_table(wb, tbl, csvp, dcols, APPEND_KEYS[tbl], PERIOD_COL[tbl]))
            except Exception as e:                                   # noqa: BLE001
                log(f"  ! {tbl}: {e}")
        try:
            added += P.com_retry(lambda: append_table2(wb))
        except Exception as e:                                       # noqa: BLE001
            log(f"  ! Table2 So TK: {e}")
        try:                                                         # Drivers: dien o trong + ghi de RECENT_Q cot ky cuoi
            import drivers_extra
            added += P.com_retry(lambda: drivers_extra.build(wb, append_only=True, recent=RECENT_Q)) or 0
        except Exception as e:                                       # noqa: BLE001
            log(f"  ! Drivers bổ sung: {e}")
        xl.Calculation = -4105
        if added:
            P.com_retry(lambda: xl.CalculateFull()); P.com_retry(lambda: wb.Save())
        P.com_retry(lambda: wb.Close(False))
        log(f"-> {target}: {added:,} dong/o them hoac sua{'' if added else ' (khong doi, khong luu)'} [{time.time() - t0:.0f}s]")
    finally:
        try:
            xl.Quit()
        except Exception:                                            # noqa: BLE001
            pass
    if added and os.path.normcase(target) == os.path.normcase(os.path.abspath(P.FINAL)):
        try:                                                         # ban lam viec logic\ = ban sao CUA file giao (chieu nguoc)
            shutil.copyfile(target, P.OUTX)
        except OSError as e:
            log(f"  (khong chep ve {P.OUTX}: {e})")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
