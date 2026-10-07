# -*- coding: utf-8 -*-
r"""drivers_extra.py - KHOI BO SUNG sheet Drivers tu dong 64 (17/09/2026, spec PV2):
 A. Dong tien khoi ngoai & tin dung CTCK: mua/ban rong khoi ngoai HOSE (quy, luy ke 4 quy), du no margin, Δ margin, tuong quan 8 quy.
 B. Lai suat: LS huy dong binh quan (VCB cong bo, co tu 2024) + LNH 3 thang, qua dem, tai cap von (thuoc do mat bang lai suat thuc) + CoF CTCK.
    Ghi chu PV2: LS tien gui giai doan 2026 KHONG phan anh dung mat bang lai suat -> doc cung LNH/CoF.
 C. Phia cung co phieu HOSE vs quy mo margin: von hoa HOSE cuoi quy, Margin / Von hoa, Von hoa / Margin.
 LICH SU DAI HON (17/09/2026): ky pipeline thieu lay tu excel_feed\drivers_backfill.csv (backfill_drivers.py): khoi ngoai
 Q1-2018..Q3-2018 (CafeF, pipeline VNDirect chi tu 30/08/2018), von hoa HOSE Q1-2018..Q2-2019 (tong tung ma VNDirect / 1,083).
 Von hoa: bo diem gai (VNINDEX MARKETCAP 29/03/2024 chi ~1/33 gia tri that -> Q1-2024 tung sai).
 Dung full (build_presentation): CHI xoa vung so (cot I..) cua khoi; nhan cot F chi ghi khi o trong.
 Hang ngay (update_nganh_daily, 24/09/2026): build(wb, append_only=True, recent=2) dien o trong + ghi de so 2 ky cuoi; o cong thuc/chu giu.
 (Khoi 2 dong 87-122 them chieu 17/09 da GO theo yeu cau user.)
Cot ky = Drivers I..AP (header dong 8 'Qn-yyyy'). So lieu thi truong = GIA TRI tinh tu CSV pipeline (tinh lai moi lan chay);
dong dan xuat = CONG THUC (tham chieu FS Industry / Key ratios / chinh cac dong nay).
Nguon: D:\market-data\index-fetcher\flows-master.csv (VNINDEX foreign, ngay), transmission-fetcher\transmission-master.csv
(deposit_rate_avg_vcb, ib_3m, ib_on, policy_refinance), market-valuation\valuation-master.csv (VNINDEX MARKETCAP).
Goi tu build_presentation.py (sau Drivers) va update_nganh_daily.py ; chay rieng: python drivers_extra.py [--file] [--no-copy]
"""
import argparse, os, sys, time
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_presentation import col_letter, com_retry, log, OUTX, copy_final   # noqa: E402

MD = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))   # MD_ROOT (pipeline-data cloud/laptop); mac dinh D:/market-data
FLOWS = os.path.join(MD, "index-fetcher", "flows-master.csv")
TRANS = os.path.join(MD, "transmission-fetcher", "transmission-master.csv")
VALU = os.path.join(MD, "market-valuation", "valuation-master.csv")
ROW0, C0, NMAX = 64, 9, 42                     # Drivers: bat dau dong 64, cot I, toi da 42 ky
PURPLE, WHITE = 0xA03070, 0xFFFFFF
FMT = {"ty": '_(* #,##0_);_(* (#,##0);_(* "-"??_);_(@_)', "pct": "0.00%", "pct1": "0.0%;(0.0%);-", "x": '0.0"x"', "r": "0.00"}


def _qkey(dates):
    d = pd.to_datetime(dates)
    return "Q" + d.dt.quarter.astype(str) + "-" + d.dt.year.astype(str)


INDICES = os.path.join(MD, "index-fetcher", "indices-master.csv")
GTGD_ROWS = {"VNINDEX": (28, 33), "HNXINDEX": (29, 34), "UPCOM": (30, 35)}     # Drivers: (GTGD quy, ADTV) - truoc day la gia tri link SharePoint


def gtgd_series():
    """{index_code: {'Qn-yyyy': (GTGD quy ty dong, ADTV ty dong, so phien)}} tu indices-master (value = trieu dong/phien, vnstock).
    Doi chieu 17/09/2026 voi so link SharePoint cu: lech 0% o ca 3 san, moi quy 2019-2026; lap them Q1-Q4/2018."""
    if not os.path.exists(INDICES):
        return {}
    m = pd.read_csv(INDICES, encoding="utf-8-sig", low_memory=False, usecols=["date", "index_code", "value"])
    m = m[m.index_code.isin(GTGD_ROWS)].dropna(subset=["value"])
    m = m[m.value > 0]
    m["q"] = _qkey(m.date)
    g = m.groupby(["index_code", "q"]).value.agg(["sum", "count"])
    out = {}
    for (code, q), r in g.iterrows():
        out.setdefault(code, {})[q] = (r["sum"] / 1e3, r["sum"] / 1e3 / r["count"], int(r["count"]))
    return out


def _fill_empty(ws, r, cols, vals=None, formulas=None, recent=0):
    """Hang ngay: ghi vao o dang TRONG; rieng `recent` cot ky cuoi cua dong GIA TRI -> ghi de neu so khac
    (o dang la cong thuc hoac chu - vd. user tu go - khong dung). Tra ve so o da ghi."""
    cur = ws.Range(ws.Cells(r, cols[0]), ws.Cells(r, cols[-1])).Formula
    cur = list(cur[0]) if isinstance(cur, tuple) else [cur]
    n = 0
    for k, c in enumerate(cols):
        if cur[k] not in (None, ""):
            if vals is None or k < len(cols) - recent or vals[k] is None or str(cur[k]).startswith("="):
                continue
            try:
                if abs(float(cur[k]) - vals[k]) <= 1e-9 * max(1.0, abs(vals[k])):
                    continue
            except (TypeError, ValueError):
                continue
            ws.Cells(r, c).Value = vals[k]; n += 1
            continue
        if formulas is not None:
            ws.Cells(r, c).Formula = formulas[k]; n += 1
        elif vals[k] is not None:
            ws.Cells(r, c).Value = vals[k]; n += 1
    return n


def write_gtgd(ws, periods, append_only=False, recent=0):
    data = gtgd_series(); n = 0
    cols = list(range(C0, C0 + len(periods)))
    for code, (rt, ra) in GTGD_ROWS.items():
        s = data.get(code, {})
        vt = [s[p][0] if p in s else None for p in periods]; va = [s[p][1] if p in s else None for p in periods]
        if append_only:
            n += _fill_empty(ws, rt, cols, vt, recent=recent) + _fill_empty(ws, ra, cols, va, recent=recent); continue
        ws.Range(ws.Cells(rt, C0), ws.Cells(rt, C0 + len(periods) - 1)).Value = [vt]
        ws.Range(ws.Cells(ra, C0), ws.Cells(ra, C0 + len(periods) - 1)).Value = [va]
        n += sum(p in s for p in periods)
    if append_only:
        return n
    ws.Cells(27, 7).Value = "nguồn: index-fetcher (vnstock), tổng phiên trong quý"; ws.Cells(32, 7).Value = "GTGD quý / số phiên"
    for a in ("G27", "G32"):
        ws.Range(a).Font.Italic = True; ws.Range(a).Font.Size = 8
    return n


def market_series():
    """{ten: {'Qn-yyyy': gia tri}} cho cac dong GIA TRI."""
    out = {}
    if os.path.exists(FLOWS):
        f = pd.read_csv(FLOWS, encoding="utf-8-sig")
        f = f[(f.index_code == "VNINDEX") & (f.flow_type == "foreign") & (f.freq == "D")].copy()
        f["q"] = _qkey(f.date)
        g = f.groupby("q").agg(net=("net_val", "sum"), days=("date", "count"))
        out["foreign_net"] = (g.net[g.days >= 50] / 1e9).to_dict()             # bo quy dau 2018 thieu ngay
    if os.path.exists(TRANS):
        t = pd.read_csv(TRANS, encoding="utf-8-sig", low_memory=False, usecols=["date", "series_id", "value", "source"])
        t = t[t.series_id.isin(["deposit_rate_avg_vcb", "ib_3m", "ib_on", "policy_refinance"])].copy()
        t["value"] = pd.to_numeric(t.value, errors="coerce"); t = t.dropna(subset=["value"])
        t = t.sort_values(["series_id", "date", "source"]).drop_duplicates(["series_id", "date"], keep="last")
        t["q"] = _qkey(t.date)
        for sid, how in (("deposit_rate_avg_vcb", "mean"), ("ib_3m", "mean"), ("ib_on", "mean"), ("policy_refinance", "last")):
            s = t[t.series_id == sid].sort_values("date").groupby("q").value
            val = (s.mean() if how == "mean" else s.last()) / 100
            if how == "last" and len(val):                              # LS dieu hanh: quy khong co quan sat = giu muc cu
                per = pd.PeriodIndex([f"{q[3:]}Q{q[1]}" for q in val.index], freq="Q")
                full = pd.period_range(per.min(), per.max(), freq="Q")
                val = pd.Series(val.values, index=per).sort_index().reindex(full).ffill()
                val.index = [f"Q{p.quarter}-{p.year}" for p in full]
            out[sid] = val.to_dict()
    if os.path.exists(VALU):
        v = pd.read_csv(VALU, encoding="utf-8-sig")
        v = v[v.code == "VNINDEX"].sort_values("date").copy()
        v["q"] = _qkey(v.date)
        mc = v[v.ratio == "MARKETCAP"].copy()
        med = mc.value.rolling(21, center=True, min_periods=5).median()
        mc = mc[(mc.value > 0.5 * med) & (mc.value < 2 * med)]             # diem gai (29/03/2024 ~1/33 gia tri) -> bo
        out["mcap_hose"] = (mc.groupby("q").value.last() / 1e9).to_dict()
    for k, s in backfill().items():                                    # ky pipeline thieu -> so lieu lich su co dinh
        cur = out.setdefault(k, {})
        for q, val in s.items():
            cur.setdefault(q, val)
    return out


BACKFILL = os.path.join(HERE, "excel_feed", "drivers_backfill.csv")


def backfill():
    """{key: {'Qn-yyyy': value}} tu drivers_backfill.csv (backfill_drivers.py)."""
    if not os.path.exists(BACKFILL):
        return {}
    b = pd.read_csv(BACKFILL, encoding="utf-8-sig")
    return {k: dict(zip(g.q, g.value)) for k, g in b.groupby("key")}


# (khoa, nhan, dinh dang, kieu, tham so)  kieu: sec | per | val (series) | f (ham tao cong thuc theo cot) | blank
def rows_spec():
    L = col_letter
    kr = lambda r: (lambda c, rm: f"=IFERROR(INDEX('Key ratios'!$I${r}:$AX${r},MATCH({L(c)}$8,'Key ratios'!$I$4:$AX$4,0))+0,\"\")")
    fs = lambda r: (lambda c, rm: f"=IFERROR(INDEX('FS Industry'!$U${r}:$BN${r},MATCH({L(c)}$8,'FS Industry'!$U$4:$BN$4,0))+0,\"\")")
    ref = lambda k, c, rm: f"{L(c)}{rm[k]}"
    return [
        ("hdr", "BỔ SUNG DRIVERS (17/09/2026): dòng tiền khối ngoại, lãi suất, phía cung cổ phiếu HOSE – số thị trường tính lại mỗi lần chạy pipeline", None, "sec", None),
        ("per", "Kỳ", None, "per", None),
        ("sA", "A. Khối ngoại & tín dụng margin", None, "bold", None),
        ("foreign_net", "Mua/bán ròng khối ngoại HOSE (quý, tỷ đồng)", "ty", "val", "foreign_net"),
        ("foreign_4q", "Mua/bán ròng khối ngoại lũy kế 4 quý", "ty", "f",
         lambda c, rm: '=""' if c < C0 + 3 else f'=IF(COUNT({L(c-3)}{rm["foreign_net"]}:{L(c)}{rm["foreign_net"]})<4,"",SUM({L(c-3)}{rm["foreign_net"]}:{L(c)}{rm["foreign_net"]}))'),
        ("margin", "Dư nợ margin toàn ngành (tỷ đồng)", "ty", "f", fs(43)),
        ("d_margin", "Δ dư nợ margin so với quý trước", "ty", "f",
         lambda c, rm: '=""' if c == C0 else f'=IF(OR({ref("margin", c-1, rm)}="",{ref("margin", c, rm)}=""),"",{ref("margin", c, rm)}-{ref("margin", c-1, rm)})'),
        ("correl", "Tương quan 8 quý: mua ròng khối ngoại vs Δ dư nợ margin", "r", "f",
         lambda c, rm: '=""' if c < C0 + 7 else f'=IFERROR(CORREL({L(c-7)}{rm["foreign_net"]}:{L(c)}{rm["foreign_net"]},{L(c-7)}{rm["d_margin"]}:{L(c)}{rm["d_margin"]}),"")'),
        ("b1", None, None, "blank", None),
        ("sB", "B. Lãi suất (LS tiền gửi 2026 không phản ánh đúng mặt bằng lãi suất → đọc cùng LNH và CoF CTCK)", None, "bold", None),
        ("dep", "LS huy động bình quân (VCB công bố, bình quân quý; có từ 2024)", "pct", "val", "deposit_rate_avg_vcb"),
        ("ib3m", "LS liên ngân hàng 3 tháng (bình quân quý)", "pct", "val", "ib_3m"),
        ("ibon", "LS liên ngân hàng qua đêm (bình quân quý)", "pct", "val", "ib_on"),
        ("refi", "LS tái cấp vốn (cuối quý)", "pct", "val", "policy_refinance"),
        ("cof", "CoF CTCK toàn ngành (Key ratios, quý quy năm)", "pct", "f", kr(26)),
        ("sp_ib_dep", "Chênh LNH 3 tháng − LS huy động", "pct", "f",
         lambda c, rm: f'=IF(OR({ref("ib3m", c, rm)}="",{ref("dep", c, rm)}=""),"",{ref("ib3m", c, rm)}-{ref("dep", c, rm)})'),
        ("sp_cof_ib", "Chênh CoF CTCK − LNH 3 tháng", "pct", "f",
         lambda c, rm: f'=IF(OR({ref("cof", c, rm)}="",{ref("ib3m", c, rm)}=""),"",{ref("cof", c, rm)}-{ref("ib3m", c, rm)})'),
        ("b2", None, None, "blank", None),
        ("sC", "C. Phía cung cổ phiếu HOSE vs quy mô margin", None, "bold", None),
        ("mcap", "Vốn hoá HOSE (VN-Index, cuối quý, tỷ đồng; Q1-2018–Q2-2019 ước tính từ vốn hoá từng mã)", "ty", "val", "mcap_hose"),
        ("margin_mcap", "Dư nợ margin / Vốn hoá HOSE", "pct", "f",
         lambda c, rm: f'=IF(OR({ref("margin", c, rm)}="",{ref("mcap", c, rm)}=""),"",{ref("margin", c, rm)}/{ref("mcap", c, rm)})'),
        ("mcap_margin", "Vốn hoá HOSE / Dư nợ margin", "x", "f",
         lambda c, rm: f'=IF(OR({ref("margin", c, rm)}="",{ref("mcap", c, rm)}=""),"",{ref("mcap", c, rm)}/{ref("margin", c, rm)})'),
    ]


def build(wb, append_only=False, recent=0):
    """append_only=True (update_nganh_daily): chi dien o TRONG trong cac dong GTGD + khoi 64-85, khong xoa/ghi de/doi dinh dang
    -> tra ve so o da them. False (build_presentation dung full): ghi lai ca khoi nhu cu -> tra ve rm."""
    ws = wb.Worksheets("Drivers")
    periods = []
    for c in range(C0, C0 + NMAX):
        v = ws.Cells(8, c).Value
        if not v:
            break
        periods.append(str(v))
    ncol = len(periods); cols = list(range(C0, C0 + ncol))
    spec = rows_spec(); rm = {k: ROW0 + i for i, (k, *_r) in enumerate(spec)}
    if append_only:
        n_g = write_gtgd(ws, periods, append_only=True, recent=recent)
        data = market_series(); n_v = n_f = 0
        for key, lab, fmt, kind, arg in spec:
            if kind == "val":
                s = data.get(arg, {})
                n_v += _fill_empty(ws, rm[key], cols, [float(s[p]) if p in s and pd.notna(s[p]) else None for p in periods], recent=recent)
            elif kind == "f":
                n_f += _fill_empty(ws, rm[key], cols, formulas=[arg(c, rm) for c in cols])
        log(f"  Drivers (điền ô trống + ghi đè {recent} kỳ cuối, {ncol} kỳ đến {periods[-1] if periods else '-'}): GTGD/ADTV +{n_g}, số thị trường +{n_v}, công thức +{n_f}")
        return n_g + n_v + n_f
    n_gtgd = write_gtgd(ws, periods)                                  # dong 28-30 / 33-35: GTGD & ADTV tu pipeline (thay link SharePoint)
    log(f"  Drivers GTGD/ADTV từ pipeline: {n_gtgd} ô-kỳ (3 sàn × {ncol} kỳ)")
    # CHI xoa vung so (cot ky) cua khoi - KHONG xoa cot nhan F (giu nhan user sua tay) va khong dung vung khac
    ws.Range(ws.Cells(ROW0, C0), ws.Cells(ROW0 + len(spec) - 1, C0 + NMAX)).Clear()
    data = market_series(); nval = nf = 0
    for key, lab, fmt, kind, arg in spec:
        r = rm[key]
        if lab and not ws.Cells(r, 6).Value:                              # nhan: chi ghi khi o trong (user sua tay thi giu)
            ws.Cells(r, 6).Value = lab
        rg = ws.Range(ws.Cells(r, 6), ws.Cells(r, C0 + ncol - 1))
        rg.Font.Name = "Aptos"; rg.Font.Size = 10
        if kind == "sec":
            ws.Range(ws.Cells(r, 6), ws.Cells(r, C0 + ncol - 1)).Interior.Color = PURPLE
            rg.Font.Color = WHITE; rg.Font.Bold = True; continue
        if kind == "bold":
            ws.Cells(r, 6).Font.Bold = True; continue
        if kind == "blank":
            continue
        if kind == "per":
            ws.Range(ws.Cells(r, C0), ws.Cells(r, C0 + ncol - 1)).Formula = [[f"={col_letter(c)}$8" for c in cols]]
            rg.Font.Bold = True; ws.Range(ws.Cells(r, C0), ws.Cells(r, C0 + ncol - 1)).HorizontalAlignment = -4152; continue
        body = ws.Range(ws.Cells(r, C0), ws.Cells(r, C0 + ncol - 1))
        if kind == "val":
            s = data.get(arg, {})
            vals = [float(s[p]) if p in s and pd.notna(s[p]) else None for p in periods]
            body.Value = [vals]; nval += sum(v is not None for v in vals)
        else:
            body.Formula = [[arg(c, rm) for c in cols]]; nf += ncol
        body.NumberFormat = FMT[fmt]
        ws.Cells(r, 6).IndentLevel = 1
    log(f"  Drivers bổ sung (dòng {ROW0}–{ROW0 + len(spec) - 1}): {nval} ô số thị trường, {nf} ô công thức, {ncol} kỳ")
    return rm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=OUTX); ap.add_argument("--no-copy", action="store_true")
    a = ap.parse_args()
    import win32com.client as win32
    t0 = time.time()
    xl = win32.DispatchEx("Excel.Application"); xl.Visible = False; xl.DisplayAlerts = False; xl.ScreenUpdating = False
    try:
        wb = xl.Workbooks.Open(os.path.abspath(a.file), UpdateLinks=0)
        xl.Calculation = -4135; xl.EnableEvents = False
        com_retry(lambda: build(wb))
        xl.Calculation = -4105; xl.CalculateFull()
        wb.Save(); wb.Close(False)
        log(f"-> {a.file} [{time.time() - t0:.0f}s]")
    finally:
        try:
            xl.Quit()
        except Exception:                                            # noqa: BLE001
            pass
    if not a.no_copy and os.path.abspath(a.file) == os.path.abspath(OUTX):
        copy_final(OUTX)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
