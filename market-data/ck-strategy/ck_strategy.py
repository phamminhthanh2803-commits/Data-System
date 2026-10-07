# -*- coding: utf-8 -*-
r"""CHIẾN LƯỢC NGÀNH CHỨNG KHOÁN — tín hiệu + backtest + trạng thái hằng ngày.

QUY TẮC (chốt 23/09/2026)
  Danh mục   : N cổ phiếu CTCK vốn hoá lớn nhất tại ngày mua (mặc định 5), bỏ mã niêm yết dưới 1 năm, chia đều tiền.
  MUA (3 điều kiện cùng lúc)
    1. Định giá thị trường: z của P/E VN-Index LOẠI VIN ≤ −1,7σ → bậc 1 (50% vốn); ≤ −1,9σ → bậc 2 (50% còn lại).
       z tính theo cửa sổ trượt 3 năm HOẶC 5 năm (chạm ở cửa sổ nào cũng được) để không bỏ lỡ chu kỳ.
    2. Thanh khoản: GTGD 3 sàn quý gần nhất GIẢM so với quý trước (dòng tiền đã rút → vùng đầu hàng).
    3. Lợi nhuận ngành CK (ưu tiên QoQ):
         - LNST quý gần nhất TĂNG QoQ  → mở đủ 2 bậc.
         - Chỉ TĂNG YoY (QoQ giảm)     → chỉ mở bậc 1 (50% vốn); mua nốt khi QoQ chuyển tăng.
         - Cả hai giảm                 → không mua.
  BÁN (bán hết khi chạm bất kỳ điều kiện nào) — đổi 28/09/2026 từ định giá sang kết quả kinh doanh
    - LNST ngành CK "bắt đầu không tăng": BCTC quý công bố SAU ngày mua cho thấy LNST ngành GIẢM QoQ,
      với điều kiện trong lệnh đã có ≥ 3 quý LNST tăng QoQ liên tiếp (tránh bán ở quý giảm lặt vặt giữa chu kỳ).
    - Chốt chặn: giảm 30% so với đỉnh của lệnh; khi đỉnh lãi của lệnh đã ≥ +20% thì siết còn giảm 20% từ đỉnh (chốt lời).
    - Nắm quá 5 năm.
    (Luật cũ: P/B ngành cắt xuống +2,5σ — chạy bằng --ban dinhgia để so sánh.)
  VÀO LẠI  : sau chốt chặn −30% chờ 10 phiên; sau bán vì LNST chờ BCTC quý kế tiếp; rồi mua lại khi tín hiệu mua bật lại.
             Sau chốt lời: mua lại cùng rổ, 100% vốn, khi rổ vượt lại đỉnh cũ của lệnh (sóng còn tiếp) — huỷ nếu LNST ngành chững.
  Tiền chờ : gửi tiết kiệm 5%/năm.
  Tham số chọn theo CHU KỲ BÌNH THƯỜNG (bỏ 2020–2022 Covid/bong bóng/vỡ bong bóng) — xem README.

KẾT QUẢ BACKTEST 04/2012 → 09/2026 (top 5): NAV 53,7x, CAGR +31,8%, sụt tối đa −25%, 8 lệnh đã đóng.
             Rổ cố định SSI,VND,HCM,VCI,MBS: 50,1x, CAGR +31,2%, sụt −25%.
             Chu kỳ bình thường (bỏ 2020–22): +19,3%/năm (luật 28/09 sáng: lãi ≥20% → −10%, g2: +16,3%/năm).
             Theo giai đoạn: 2012–19 +191% | 2023–24 +89% | 2025–nay +37% | (BT: 2020–21 +400%, 2022 +41%).
             VN-Index cùng kỳ 3,9x (+9,9%/năm).
             (28/09/2026: giá mua dùng giá đóng cửa gần nhất khi mã không khớp lệnh ngày mua — trước đó mã đó bị bỏ khỏi bậc mua.)

CHẠY:  python ck_strategy.py                 -> trạng thái hôm nay + CSV tín hiệu
       python ck_strategy.py --backtest      -> thêm bảng lệnh + biểu đồ PNG
       python ck_strategy.py --top 3         -> đổi số mã trong danh mục
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))
CK = os.path.join(os.path.normpath(os.environ.get("BCTC_ROOT", "D:/bctc")), "nganh-chung-khoan")
TV = os.path.join(MD, "index-fetcher", "tv-history.csv")
META = os.path.join(MD, "index-fetcher", "raw", "vn_screener_meta.csv")
INDICES = os.path.join(MD, "index-fetcher", "indices-master.csv")
VIETCAP = os.path.join(MD, "market-valuation", "history", "vnindex_val_vietcap.csv")
ADJ = os.path.join(MD, "market-valuation", "valuation-adjusted.csv")
FACT = os.path.join(CK, "fact_items.csv")
DIMC = os.path.join(CK, "dim_company.csv")

W3, W5 = 750, 1250          # cửa sổ trượt 3 năm / 5 năm (phiên)
K1, K2 = 1.7, 1.9           # ngưỡng mua (σ dưới trung bình)
EXIT = "lnst"               # luật bán chính: "lnst" (LNST ngành chững) hoặc "dinhgia" (P/B ngành cắt xuống +2,5σ, luật cũ)
G_MIN = 3                   # luật LNST: trong lệnh phải có ≥ G_MIN quý LNST ngành tăng QoQ liên tiếp rồi mới xét bán
                            # (3 thay vì 2 từ 28/09: 2 quý làm bán sớm 11/2017 giữa chu kỳ bình thường 2016–18)
XSELL = 2.5                 # luật định giá (cũ): cắt xuống +2,5σ
DDMAX = 0.30                # chốt chặn: giảm 30% từ đỉnh lệnh
LAI_KICH = 0.20             # siết chốt chặn khi đỉnh lãi lệnh đạt +20% (None = tắt)
DD_CHAT = 0.20              # sau khi siết: cắt khi giảm 20% từ đỉnh lệnh (−10% quá chặt ở chu kỳ 2016–18)
MUA_LAI = True              # bị cắt lúc đang lãi → mua lại cùng rổ (100% vốn) khi rổ vượt lại đỉnh cũ của lệnh,
                            # miễn LNST ngành chưa chững (chưa có quý giảm QoQ sau ≥ G_MIN quý tăng)


def muc_cat(peak_lai):
    """Mức sụt từ đỉnh lệnh được phép, theo đỉnh lãi đã đạt (peak_lai = đỉnh PnL, vd 0.25 = +25%)."""
    return DD_CHAT if (LAI_KICH is not None and peak_lai >= LAI_KICH) else DDMAX
MAXH = 1250                 # nắm tối đa 5 năm
COOL = 10                   # số phiên nghỉ trước khi được mua lại sau chốt chặn
LAG = 45                    # BCTC quý có hiệu lực sau cuối quý + 45 ngày
DEP = 0.05 / 250            # lãi tiền gửi khi đứng ngoài
MINYR = 1.0                 # bỏ mã niêm yết dưới 1 năm
BAT_THUONG = ("2020-01-01", "2022-12-31")   # Covid → bong bóng → vỡ bong bóng: không dùng để chọn tham số
CHU_KY = {"2012–19": ("2012-01-01", "2019-12-31"), "2020–21 (BT)": ("2020-01-01", "2021-12-31"),
          "2022 (BT)": ("2022-01-01", "2022-12-31"), "2023–24": ("2023-01-01", "2024-12-31"), "2025–nay": ("2025-01-01", "2035-12-31")}


def log(m):
    print(m, flush=True)


def _z(s, win):
    r = s.rolling(win, min_periods=win)
    return (s - r.mean()) / r.std()


def load():
    """Trả về mọi chuỗi cần thiết, đã căn theo phiên giao dịch."""
    dc = pd.read_csv(DIMC)
    tick = [t for t in dc.ticker if isinstance(t, str) and len(t) == 3 and t.isupper() and t.isalnum()]
    tv = pd.read_csv(TV, usecols=["date", "symbol", "exchange", "close"], dtype={"date": str})
    tv = tv[tv.symbol.isin(tick) & tv.exchange.isin(["HOSE", "HNX", "UPCOM"]) & (tv.date >= "2008-01-01")]
    tv["date"] = pd.to_datetime(tv.date)
    px = tv.pivot_table(index="date", columns="symbol", values="close", aggfunc="last").sort_index()
    pxf = px.ffill()
    shm = pd.read_csv(META).drop_duplicates("name").set_index("name").total_shares_outstanding_fundamental

    # --- BCTC quý ngành CK (FiinProX): VCSH và LNST công ty mẹ
    fi = pd.read_csv(FACT, dtype={"period": str})
    q = fi[(fi.freq == "Q") & fi.metric.isin(["equity", "equity_parent", "npat", "npat_parent"])]
    w = q.pivot_table(index=["ticker", "period"], columns="metric", values="value", aggfunc="first").reset_index()
    w["eq"] = w["equity_parent"].fillna(w["equity"]) if "equity_parent" in w else w["equity"]
    w["np"] = w["npat_parent"].fillna(w["npat"]) if "npat_parent" in w else w["npat"]
    w["qend"] = [pd.Timestamp(int(p.split("/")[1]), int(p[1]) * 3, 1) + pd.offsets.MonthEnd(0) for p in w.period]
    w["avail"] = w.qend + pd.Timedelta(days=LAG)

    # --- P/B ngành CK theo ngày = Σ vốn hoá / Σ VCSH (mã có cả giá lẫn VCSH)
    sh = pd.Series({t: shm.get(t) for t in px.columns}).dropna()
    sh = sh[sh > 0]
    daily = px[sh.index].stack().rename("close").reset_index().rename(columns={"symbol": "ticker"}).sort_values("date")
    fund = w[["ticker", "avail", "eq"]].rename(columns={"avail": "date"}).dropna().sort_values("date")
    d = pd.merge_asof(daily, fund, on="date", by="ticker", direction="backward").dropna(subset=["eq"])
    d["mcap"] = d.close * d.ticker.map(sh) / 1e9
    g = d.groupby("date")
    pb_ck = (g.mcap.sum() / g.eq.sum()).rename("pb_ck")
    pb_ck = pb_ck[g.size() >= 5]

    # --- LNST ngành theo quý -> cờ QoQ / YoY
    sec = w.groupby("qend")["np"].sum().sort_index()
    av = sec.index + pd.Timedelta(days=LAG)
    qoq = pd.Series((sec > sec.shift(1)).to_numpy(), index=av)
    yoy = pd.Series((sec > sec.shift(4)).to_numpy(), index=av)

    # --- Định giá VN-Index loại Vin: Vietcap (2009+) × hệ số, nối VNDirect pe_adj từ 07/2019
    vc = pd.read_csv(VIETCAP, parse_dates=["date"]).set_index("date").sort_index()
    ad = pd.read_csv(ADJ, parse_dates=["date"])
    ad = ad[ad["index"] == "VNINDEX"].set_index("date").sort_index()
    ex = ad.pe_adj.dropna()
    ov = pd.concat([ex, ad.pe], axis=1).dropna().iloc[:60]
    k = (ov.iloc[:, 0] / ov.iloc[:, 1]).mean()
    pe_vni = pd.concat([vc.pe[vc.index < ex.index[0]] * k, ex]).rename("pe_vni_ex_vin")

    # --- Thanh khoản 3 sàn theo quý + VN-Index
    ix = pd.read_csv(INDICES, usecols=["date", "index_code", "close", "value"], parse_dates=["date"])
    vni = ix[ix.index_code == "VNINDEX"].set_index("date").close.sort_index()
    gt = (ix[ix.index_code.isin(["VNINDEX", "HNXINDEX", "UPCOM"])]
          .pivot_table(index="date", columns="index_code", values="value", aggfunc="last").sum(axis=1, min_count=1) / 1e3)
    gt = gt[gt > 0].sort_index()
    gq = gt.groupby([gt.index.year, gt.index.quarter]).sum()
    gqe = gt.groupby([gt.index.year, gt.index.quarter]).apply(lambda s: s.index.max())
    liq_down = pd.Series((gq < gq.shift(1)).to_numpy(), index=pd.DatetimeIndex(gqe.to_numpy())).sort_index()

    days = px.index[px.index >= pe_vni.dropna().index[W3 - 1]]
    S = pd.DataFrame(index=days)
    S["pe_vni"] = pe_vni.reindex(days, method="ffill")
    S["z_pe3"] = _z(pe_vni, W3).reindex(days, method="ffill")
    S["z_pe5"] = _z(pe_vni, W5).reindex(days, method="ffill")
    S["pb_ck"] = pb_ck.reindex(days, method="ffill")
    S["z_pb3"] = _z(pb_ck, W3).reindex(days, method="ffill")
    S["liq_down"] = liq_down.reindex(days, method="ffill").fillna(False).astype(bool)
    S["eps_qoq"] = qoq.reindex(days, method="ffill").fillna(False).astype(bool)
    S["eps_yoy"] = yoy.reindex(days, method="ffill").fillna(False).astype(bool)
    S["muc_cong"] = np.where(S.liq_down & S.eps_qoq, 2, np.where(S.liq_down & S.eps_yoy, 1, 0))
    S["mua_b1"] = ((S.z_pe3 <= -K1) | (S.z_pe5 <= -K1)) & (S.muc_cong >= 1)
    S["mua_b2"] = ((S.z_pe3 <= -K2) | (S.z_pe5 <= -K2)) & (S.muc_cong >= 2)
    # phiên có BCTC quý mới hiệu lực (cuối quý + LAG) và quý đó LNST ngành tăng QoQ hay không — dùng cho luật bán LNST
    S["bctc_moi"], S["bctc_tang"], S["bctc_ky"] = False, False, ""
    for qe, kk, v in zip(sec.index, days.searchsorted(av), (sec > sec.shift(1)).to_numpy()):
        if kk < len(days):
            S.iloc[kk, S.columns.get_loc("bctc_moi")] = True
            S.iloc[kk, S.columns.get_loc("bctc_tang")] = bool(v)
            S.iloc[kk, S.columns.get_loc("bctc_ky")] = f"Q{qe.quarter}/{qe.year}"
    return S, px, pxf, sh, shm, vni, gq, sec


FIXED = None          # rổ cố định (list mã) nếu đặt qua --fixed; None = chọn top N vốn hoá


def top_n(px, pxf, shm, t, n):
    if FIXED:                                        # rổ cố định: lấy các mã đã có giá tại t
        return [c for c in FIXED if c in px.columns and pd.notna(px.loc[t, c])]
    """n mã CTCK vốn hoá lớn nhất có giá tại t, bỏ mã niêm yết dưới MINYR năm."""
    p0 = px.loc[t].dropna()
    mc = (p0 * shm.reindex(p0.index)).dropna()
    ok = [c for c in mc.index if pxf.loc[:t, c].notna().sum() >= int(MINYR * 250)]
    return list(mc.reindex(ok).nlargest(n).index)


def backtest(S, px, pxf, shm, n):
    D = S.index
    cash, lots, cyc, armed, stop_k, cho_bctc, reb = 1.0, [], None, True, None, False, None
    nav, expo, ev, pl = [], [], [], []           # pl: PnL theo ngày của lệnh đang mở
    for k, t in enumerate(D):
        if k:
            cash *= 1 + DEP
        pos = sum(L["u"] * L["path"].asof(t) for L in lots)
        z = S.z_pb3.iloc[k]
        z = z if pd.notna(z) else -9
        moi = bool(S.bctc_moi.iloc[k])
        if cyc is None and not S.mua_b1.iloc[k]:
            armed = True
        if cyc:
            ret = pos / cyc["cost"]
            if ret > cyc["peak"]:
                cyc["peak"], cyc["t_peak"] = ret, t
            cyc["tren"] = cyc["tren"] or z > XSELL
            ban = ""
            if moi and k > cyc["k0"]:                         # BCTC quý mới công bố SAU ngày vào lệnh
                tang = bool(S.bctc_tang.iloc[k])
                if EXIT == "lnst" and not tang and cyc["max_chuoi"] >= G_MIN:
                    ban = f"LNST ngành {S.bctc_ky.iloc[k]} giảm QoQ sau {cyc['max_chuoi']} quý tăng"
                cyc["chuoi"] = cyc["chuoi"] + 1 if tang else 0
                cyc["max_chuoi"] = max(cyc["max_chuoi"], cyc["chuoi"])
                cyc["bctc"].append((S.bctc_ky.iloc[k], tang))
            if not ban and EXIT == "dinhgia" and cyc["tren"] and z <= XSELL:
                ban = f"định giá CK cắt xuống +{XSELL:g}σ"
            lim = muc_cat(cyc["peak"] - 1)
            if not ban and ret / cyc["peak"] - 1 <= -lim:
                ban = f"chốt chặn −{lim:.0%} từ đỉnh lệnh" + (" (đang lãi → chốt lời)" if lim < DDMAX else "")
            if not ban and k - cyc["k0"] >= MAXH:
                ban = "hết 5 năm"
            if ban:
                pl.append({"ngay": t, "vao": cyc["t0"], "lai": ret - 1, "dinh": cyc["peak"] - 1})
                ev.append({"ngay": t, "sk": "BÁN", "ly_do": ban, "lai": ret - 1, "dinh": cyc["peak"] - 1, "ma": ", ".join(cyc["sel"])})
                stop_k = k if ban.startswith(f"chốt chặn −{DDMAX:.0%}") else None
                cho_bctc = ban.startswith("LNST")              # bán vì LNST → chờ BCTC quý kế tiếp mới được mua lại
                # bị cắt lúc đang lãi → theo dõi để mua lại khi rổ vượt đỉnh cũ (mức = đỉnh / giá bán, tính trên rổ chia đều)
                reb = ({"sel": cyc["sel"], "t": t, "muc": float((pxf.loc[cyc["t_peak"], cyc["sel"]] / pxf.loc[t, cyc["sel"]]).mean()),
                        "chuoi": cyc["chuoi"], "max_chuoi": cyc["max_chuoi"], "bctc": list(cyc["bctc"])}
                       if (MUA_LAI and "chốt lời" in ban) else None)
                cash += pos
                lots, cyc, armed, pos = [], None, False, 0
        if cyc is None and stop_k is not None and k - stop_k >= COOL:
            armed = True
        if cyc is None and cho_bctc and moi and ev and t > ev[-1]["ngay"]:
            armed, cho_bctc = True, False
        if cyc is None and reb is not None and moi and t > reb["t"]:     # đứng ngoài vẫn theo dõi LNST ngành
            tang = bool(S.bctc_tang.iloc[k])
            reb["bctc"].append((S.bctc_ky.iloc[k], tang))
            if not tang and reb["max_chuoi"] >= G_MIN:
                reb = None                                                # LNST đã chững → hết sóng, thôi chờ mua lại
            else:
                reb["chuoi"] = reb["chuoi"] + 1 if tang else 0
                reb["max_chuoi"] = max(reb["max_chuoi"], reb["chuoi"])
        total = cash + pos
        if cyc is None and reb is not None:
            sl = reb["sel"]
            if (pxf.loc[t, sl] / pxf.loc[reb["t"], sl]).mean() >= reb["muc"]:
                pth = (pxf.loc[t:, sl] / pxf.loc[t, sl]).mean(axis=1)
                amt = cash
                lots.append({"u": amt / pth.iloc[0], "c": amt, "path": pth})
                cyc = {"k0": k, "t0": t, "t_peak": t, "tot0": total, "done": {0, 1}, "cost": amt, "sel": sl, "peak": 1.0,
                       "tren": False, "chuoi": reb["chuoi"], "max_chuoi": reb["max_chuoi"], "bctc": reb["bctc"]}
                cash -= amt; pos += amt
                ev.append({"ngay": t, "sk": "MUA lại (100%)", "ly_do": "rổ vượt lại đỉnh cũ của lệnh trước", "ma": ", ".join(sl), "von": amt})
                reb = None
        for i, col in enumerate(("mua_b1", "mua_b2")):
            if not S[col].iloc[k]:
                continue
            if i == 0:
                if cyc or not armed:
                    continue
                cyc = {"k0": k, "t0": t, "t_peak": t, "tot0": total, "done": set(), "cost": 0.0, "sel": top_n(px, pxf, shm, t, n),
                       "peak": 0.0, "tren": False, "chuoi": 0, "max_chuoi": 0, "bctc": []}
                stop_k, reb = None, None
            elif not cyc or i in cyc["done"]:
                continue
            sl = cyc["sel"]
            pth = (pxf.loc[t:, sl] / pxf.loc[t, sl]).mean(axis=1)    # mã không khớp lệnh hôm đó → giá đóng cửa gần nhất
            amt = min(cash, 0.5 * cyc["tot0"])
            lots.append({"u": amt / pth.iloc[0], "c": amt, "path": pth})
            cash -= amt; pos += amt; cyc["cost"] += amt; cyc["done"].add(i)
            ev.append({"ngay": t, "sk": f"MUA bậc {i + 1} (50%)", "ly_do": f"P/E VNI loại Vin {S.pe_vni.iloc[k]:.2f}"
                       f" | {'LNST QoQ tăng' if S.eps_qoq.iloc[k] else 'chỉ YoY tăng'}", "ma": ", ".join(sl), "von": amt})
        if cyc and cyc["cost"] > 0:
            r = pos / cyc["cost"]
            pl.append({"ngay": t, "vao": cyc["t0"], "lai": r - 1, "dinh": max(cyc["peak"], r) - 1})
        nav.append(cash + pos)
        expo.append(pos / (cash + pos))
    E = pd.DataFrame(ev)
    E.attrs["pnl"] = pd.DataFrame(pl).drop_duplicates(["ngay", "vao"], keep="first")
    E.attrs["lenh_mo"] = cyc                                  # trạng thái lệnh đang mở (chuỗi quý LNST tăng...) hoặc None
    E.attrs["cho_mua_lai"] = reb                              # đang chờ mua lại khi rổ vượt đỉnh cũ, hoặc None
    return pd.Series(nav, index=D), pd.Series(expo, index=D), E


def trang_thai(S, px, pxf, shm, n, NAV, E):
    """In trạng thái hôm nay + việc cần làm."""
    t = S.index[-1]
    r = S.iloc[-1]
    win3 = S.z_pe3.notna().iloc[-1]
    mua = E[E.sk.str.startswith("MUA")]
    ban = E[E.sk == "BÁN"]
    dang_giu = len(mua) and (not len(ban) or mua.ngay.iloc[-1] > ban.ngay.iloc[-1])
    log(f"\n{'=' * 100}\nTRẠNG THÁI NGÀY {t:%d/%m/%Y} — danh mục {("rổ cố định " + ", ".join(FIXED)) if FIXED else ("top %d CTCK vốn hoá lớn" % n)}\n{'=' * 100}")
    log(f"  ĐỊNH GIÁ THỊ TRƯỜNG  P/E VN-Index loại Vin {r.pe_vni:.2f} | z 3 năm {r.z_pe3:+.2f}σ, z 5 năm {r.z_pe5:+.2f}σ"
        f"  → bậc 1 cần ≤ −{K1}σ: {'ĐẠT' if (r.z_pe3 <= -K1 or r.z_pe5 <= -K1) else 'chưa'}"
        f" | bậc 2 cần ≤ −{K2}σ: {'ĐẠT' if (r.z_pe3 <= -K2 or r.z_pe5 <= -K2) else 'chưa'}")
    log(f"  THANH KHOẢN          GTGD 3 sàn quý gần nhất {'GIẢM' if r.liq_down else 'TĂNG'} so với quý trước"
        f"  → cổng {'MỞ' if r.liq_down else 'ĐÓNG'}")
    log(f"  LNST NGÀNH CK        QoQ {'tăng' if r.eps_qoq else 'giảm'}, YoY {'tăng' if r.eps_yoy else 'giảm'}"
        f"  → mức cổng {int(r.muc_cong)}/2 ({'đủ 2 bậc' if r.muc_cong == 2 else ('chỉ bậc 1' if r.muc_cong == 1 else 'đóng')})")
    log(f"  ĐỊNH GIÁ NGÀNH CK    P/B {r.pb_ck:.2f} | z 3 năm {r.z_pb3:+.2f}σ"
        + (f"  → bán khi đã vượt +{XSELL}σ rồi cắt xuống" if EXIT == "dinhgia" else "  (tham khảo, không dùng để bán)"))
    if dang_giu:
        c = E.attrs.get("lenh_mo")
        if EXIT == "lnst" and c:
            ds = ", ".join(f"{ky} {'tăng' if tg else 'GIẢM'}" for ky, tg in c["bctc"]) or "chưa có quý nào công bố sau ngày mua"
            du = c["max_chuoi"] >= G_MIN
            log(f"  LUẬT BÁN LNST        BCTC quý công bố sau ngày mua: {ds} | chuỗi tăng dài nhất {c['max_chuoi']} quý (cần ≥ {G_MIN})"
                + ("  → ĐÃ KÍCH HOẠT: quý tới LNST ngành giảm QoQ là BÁN" if du
                   else f"  → chưa kích hoạt: cần thêm {G_MIN - c['chuoi']} quý tăng liên tiếp"))
        mo = pnl_lenh_mo(E, px, pxf, S.index)
        mua_gan, t0 = mo["lots"], mo["t0"]
        lai, dinh = mo["ro"].iloc[-1], mo["dinh"].iloc[-1]
        cach = (1 + lai) / (1 + dinh) - 1
        lim = muc_cat(dinh)
        von = 100 if mua_gan.sk.str.contains("lại").any() else 50 * len(mua_gan)
        siet = (f" — đã siết vì đỉnh lãi ≥ +{LAI_KICH:.0%}" if lim < DDMAX
                else (f"; siết còn −{DD_CHAT:.0%} khi đỉnh lãi ≥ +{LAI_KICH:.0%}" if LAI_KICH is not None else ""))
        log(f"\n  ĐANG NẮM GIỮ: {', '.join(mo['sel'])} | mua từ {t0:%d/%m/%Y} ({len(mua_gan)} lần mua, {von}% vốn) | "
            f"PnL {lai:+.1%} (đỉnh {dinh:+.1%}, cách đỉnh {cach:.1%}; chốt chặn ở −{lim:.0%} từ đỉnh{siet})")
        log("  PnL từng mã: " + " | ".join(f"{c} {v:+.1%}" for c, v in mo["ma"].iloc[-1].sort_values(ascending=False).items()))
        if cach <= -0.8 * lim:
            log(f"  ⚠ CẢNH BÁO: rổ đã giảm {cach:.1%} từ đỉnh lệnh — gần mức chốt chặn −{lim:.0%}")
        if len(mua_gan) == 1 and S.mua_b2.iloc[-1]:
            log("  → ĐỦ ĐIỀU KIỆN MUA NỐT BẬC 2 (50% vốn còn lại)")
    else:
        log(f"\n  ĐANG ĐỨNG NGOÀI (tiền gửi). Cần đủ: định giá ≤ −{K1}σ + thanh khoản quý giảm + LNST ngành tăng (QoQ hoặc YoY).")
        rb = E.attrs.get("cho_mua_lai")
        if rb:
            now = float((pxf.loc[t, rb["sel"]] / pxf.loc[rb["t"], rb["sel"]]).mean())
            log(f"  CHỜ MUA LẠI: {', '.join(rb['sel'])} — mua 100% vốn khi rổ vượt đỉnh cũ, tức +{rb['muc'] - 1:.1%} so với giá bán "
                f"{rb['t']:%d/%m/%Y} (hiện {now - 1:+.1%}); huỷ nếu LNST ngành chững")
        if S.mua_b1.iloc[-1]:
            log(f"  → HÔM NAY ĐỦ ĐIỀU KIỆN MUA BẬC 1: {', '.join(top_n(px, pxf, shm, t, n))}")
    yrs = (S.index[-1] - S.index[0]).days / 365.25
    log(f"\n  Backtest {S.index[0]:%m/%Y}–{S.index[-1]:%m/%Y}: NAV {NAV.iloc[-1]:.2f}x, CAGR {NAV.iloc[-1] ** (1 / yrs) - 1:+.1%}, "
        f"sụt tối đa {(NAV / NAV.cummax() - 1).min():.0%}, {len(ban)} lệnh đã đóng")


def cac_lenh(E, D):
    """Danh sách lệnh: [{t0, t1 (None nếu đang mở), lots, ban (dòng BÁN hoặc None)}]."""
    out, cur = [], None
    for r in E.itertuples():
        if r.sk.startswith("MUA"):
            if cur is None:
                cur = {"t0": r.ngay, "idx": []}
            cur["idx"].append(r.Index)
        elif cur is not None:
            out.append({"t0": cur["t0"], "t1": r.ngay, "lots": E.loc[cur["idx"]], "ban": r})
            cur = None
    if cur is not None:
        out.append({"t0": cur["t0"], "t1": None, "lots": E.loc[cur["idx"]], "ban": None})
    return out


def pnl_lenh(L, px, pxf, D):
    """PnL theo ngày của 1 lệnh: cả rổ + từng mã (gộp các bậc theo số tiền đã giải ngân)."""
    t0, lots = L["t0"], L["lots"]
    sel = lots.ma.iloc[0].split(", ")
    t1 = L["t1"] if L["t1"] is not None else px[sel].dropna(how="all").index.max()   # ngày cuối rổ có giá thật
    val = pd.DataFrame(0.0, index=D[(D >= t0) & (D <= t1)], columns=sel)
    cost = pd.DataFrame(0.0, index=val.index, columns=sel)
    for r in lots.itertuples():
        p0 = pxf.loc[r.ngay, sel].where(px.loc[r.ngay, sel].isna(), px.loc[r.ngay, sel])
        w = r.von / len(sel)
        val.loc[r.ngay:] += w * pxf.loc[r.ngay:, sel].reindex(val.loc[r.ngay:].index) / p0
        cost.loc[r.ngay:] += w
    ma = val / cost - 1
    ro = val.sum(axis=1) / cost.sum(axis=1) - 1
    dinh = (1 + ro).cummax() - 1
    return {"t0": t0, "t1": L["t1"], "ban": L["ban"], "sel": sel, "lots": lots, "ma": ma, "ro": ro, "dinh": dinh,
            "cat": (1 + dinh) * (1 - dinh.map(muc_cat)) - 1}   # mức PnL mà tại đó chạm chốt chặn (siết khi đã lãi)


def pnl_lenh_mo(E, px, pxf, D):
    """PnL của lệnh đang mở; None nếu đang đứng ngoài."""
    ls = cac_lenh(E, D)
    return pnl_lenh(ls[-1], px, pxf, D) if ls and ls[-1]["t1"] is None else None


def _luoi_y(a, lo, hi, n_major=8):
    """Vạch % dày: bước chính tự chọn theo biên độ (~8 vạch), vạch phụ = 1/5 bước chính."""
    from matplotlib.ticker import MultipleLocator, PercentFormatter
    buoc = next((b for b in (1, 2, 5, 10, 20, 25, 50, 100, 200) if (hi - lo) / b <= n_major), 500)
    a.yaxis.set_major_locator(MultipleLocator(buoc))
    a.yaxis.set_minor_locator(MultipleLocator(buoc / 5))
    a.yaxis.set_major_formatter(PercentFormatter(decimals=0))
    a.grid(which="major", axis="y", alpha=0.35)
    a.grid(which="minor", axis="y", alpha=0.12)


def _luoi_ngay(a, t0, t1, rong=False):
    """Vạch ngày dày theo độ dài lệnh (rong = True cho ô rộng toàn trang → nhãn dày gấp đôi):
    ≤ 3 tháng: nhãn tuần + vạch ngày | ≤ 8 tháng: nhãn 2 tuần + vạch tuần | ≤ 15 tháng: nhãn tháng + vạch tuần
    | ≤ 30 tháng: nhãn 2 tháng + vạch tháng | dài hơn: nhãn quý + vạch tháng."""
    import matplotlib.dates as mdates
    ngay = (t1 - t0).days / (2 if rong else 1)
    if ngay <= 90:
        maj, mnr, fm = mdates.WeekdayLocator(mdates.MO), mdates.DayLocator(), "%d/%m"
    elif ngay <= 250:
        maj, mnr, fm = mdates.WeekdayLocator(mdates.MO, interval=2), mdates.WeekdayLocator(mdates.MO), "%d/%m"
    elif ngay <= 450:
        maj, mnr, fm = mdates.MonthLocator(), mdates.WeekdayLocator(mdates.MO), "%m/%y"
    elif ngay <= 900:
        maj, mnr, fm = mdates.MonthLocator(bymonth=range(1, 13, 2)), mdates.MonthLocator(), "%m/%y"
    else:
        maj, mnr, fm = mdates.MonthLocator(bymonth=(1, 4, 7, 10)), mdates.MonthLocator(), "%m/%y"
    a.xaxis.set_major_locator(maj)
    a.xaxis.set_minor_locator(mnr)
    a.xaxis.set_major_formatter(mdates.DateFormatter(fm))
    a.grid(which="major", axis="x", alpha=0.35)
    a.grid(which="minor", axis="x", alpha=0.12)


def ve_tung_lenh(E, px, pxf, D, ten, out_png):
    """Mỗi lệnh 1 ô, thang riêng, vạch chia dày: PnL rổ + từng mã, đỉnh lệnh, mức chốt chặn, điểm mua/bán."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    INK, OR, RED, GRN = "#262626", "#ED7D31", "#C00000", "#00B050"
    PAL = ["#4472C4", "#7030A0", "#00B0F0", "#BF9000", "#548235", "#C55A11", "#2F5597", "#FF66CC"]
    ls = [pnl_lenh(L, px, pxf, D) for L in cac_lenh(E, D)]
    nc = 2
    nr = -(-len(ls) // nc)
    fig, axs = plt.subplots(nr, nc, figsize=(16, 4.6 * nr), constrained_layout=True, squeeze=False)
    for k, (a, m) in enumerate(zip(axs.flat, ls)):
        ro, ma = m["ro"] * 100, m["ma"] * 100
        mo = m["t1"] is None
        for i, c in enumerate(m["sel"]):
            col = PAL[i % len(PAL)]
            a.plot(ma.index, ma[c], color=col, lw=0.9, alpha=0.7)
            a.annotate(f"{c} {ma[c].iloc[-1]:+.0f}%", (ma.index[-1], ma[c].iloc[-1]), xytext=(4, 0), textcoords="offset points",
                       va="center", fontsize=7.5, color=col)
        a.plot(ro.index, ro, color=OR, lw=2.6, label="Cả rổ")
        a.plot(m["dinh"].index, m["dinh"] * 100, color=GRN, lw=1, ls=":", label="Đỉnh PnL lệnh")
        a.plot(m["cat"].index, m["cat"] * 100, color=RED, lw=1.2, ls="--", label="Mức chốt chặn")
        a.axhline(0, color=INK, lw=0.9)
        nhom = []                                            # các lần mua cách nhau < 10 ngày → 1 nhãn
        for r in m["lots"].itertuples():
            bac = r.sk.split("bậc ")[1].split(" ")[0] if "bậc " in r.sk else "lại"
            a.scatter([r.ngay], [ro.asof(r.ngay)], marker="^", s=90, color=OR, edgecolor=INK, lw=0.6, zorder=6)
            if nhom and (r.ngay - nhom[-1]["ngay"]).days < 10:
                nhom[-1]["bac"].append(bac)
            else:
                nhom.append({"ngay": r.ngay, "bac": [bac]})
        for g in nhom:
            a.annotate(("Mua lại (vượt đỉnh)" if g["bac"] == ["lại"] else f"Mua bậc {'+'.join(g['bac'])}") + f"\n{g['ngay']:%d/%m/%y}", (g["ngay"], ro.asof(g["ngay"])), xytext=(4, -24),
                       textcoords="offset points", ha="left", fontsize=7.5, color="#843C0C")
        # đỉnh PnL của lệnh — nhãn lệch trái nếu đỉnh sát cuối lệnh để không đè nhãn bán
        td = ro.idxmax()
        cuoi = (td - m["t0"]) > 0.8 * (ro.index[-1] - m["t0"])
        a.scatter([td], [ro.max()], marker="o", s=40, color=GRN, zorder=6)
        a.annotate(f"đỉnh {ro.max():+.1f}% ({td:%d/%m/%y})", (td, ro.max()), xytext=(-8 if cuoi else 0, 7), textcoords="offset points",
                   ha="right" if cuoi else "center", fontsize=7.5, color=GRN, fontweight="bold")
        # điểm bán / hiện tại
        a.scatter([ro.index[-1]], [ro.iloc[-1]], marker="v" if not mo else "o", s=100 if not mo else 60,
                  color=(GRN if ro.iloc[-1] > 0 else RED) if not mo else OR, edgecolor=INK, lw=0.6, zorder=7)
        a.annotate(f"{'nay' if mo else 'Bán'} {ro.iloc[-1]:+.1f}%", (ro.index[-1], ro.iloc[-1]), xytext=(6, 12),
                   textcoords="offset points", fontsize=9, fontweight="bold", color=OR if mo else INK)
        lo = min(ro.min(), ma.min().min(), m["cat"].min() * 100)
        hi = max(ro.max(), ma.max().max())
        pad = (hi - lo) * 0.08
        a.set_ylim(lo - pad, hi + pad * 1.6)
        span = pd.Timedelta(days=max(10, (ro.index[-1] - m["t0"]).days // 9))
        a.set_xlim(m["t0"] - pd.Timedelta(days=max(3, (ro.index[-1] - m["t0"]).days // 40)), ro.index[-1] + span)
        _luoi_y(a, lo, hi)
        _luoi_ngay(a, m["t0"], ro.index[-1])
        a.tick_params(axis="x", labelsize=8)
        ly = "ĐANG MỞ" if mo else m["ban"].ly_do
        a.set_title(f"#{k + 1}  {m['t0']:%d/%m/%Y} → {'nay' if mo else format(m['t1'], '%d/%m/%Y')}  ({len(ro)} phiên) | "
                    f"{ro.iloc[-1]:+.1f}% | đỉnh {ro.max():+.1f}% | {ly}", loc="left", fontsize=9.5, fontweight="bold",
                    color=OR if mo else INK)
        if k == 0:
            a.legend(frameon=False, fontsize=8, loc="upper left")
    for a in list(axs.flat)[len(ls):]:
        a.set_visible(False)
    fig.suptitle(f"DIỄN BIẾN PnL TỪNG LỆNH — {ten} (thang riêng mỗi lệnh; PnL từng mã trên giá vốn bình quân các bậc)",
                 x=0.01, ha="left", fontweight="bold", fontsize=11.5)
    fig.savefig(out_png, dpi=130, bbox_inches="tight")
    plt.close(fig)
    log(f"  -> {out_png}")


def ve_pnl(S, NAV, E, px, pxf, n, out_png, out_csv):
    """Biểu đồ theo dõi PnL: lệnh đang mở (rổ + từng mã + mức chốt chặn), PnL mọi lệnh theo số phiên, kết quả từng lệnh, NAV."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.ticker import PercentFormatter
    plt.rcParams.update({"font.family": "Segoe UI", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    INK, OR, GR, RED, GRN = "#262626", "#ED7D31", "#A6A6A6", "#C00000", "#00B050"
    PAL = ["#4472C4", "#7030A0", "#00B0F0", "#BF9000", "#548235", "#C55A11", "#2F5597", "#FF66CC"]
    D = S.index
    PL = E.attrs["pnl"].copy()
    B, Sl = E[E.sk.str.startswith("MUA")], E[E.sk == "BÁN"]
    mo = pnl_lenh_mo(E, px, pxf, D)
    ten = ("rổ " + ", ".join(FIXED)) if FIXED else f"top {n} CTCK vốn hoá lớn"

    fig = plt.figure(figsize=(15, 14), constrained_layout=True)
    gs = fig.add_gridspec(3, 2, height_ratios=[2.2, 1.6, 1.3])

    # 1) Lệnh đang mở
    a = fig.add_subplot(gs[0, :])
    if mo:
        ro, ma = mo["ro"] * 100, mo["ma"] * 100
        for i, c in enumerate(mo["sel"]):
            col = PAL[i % len(PAL)]
            a.plot(ma.index, ma[c], color=col, lw=1.1, alpha=0.85)
            a.annotate(f"{c} {ma[c].iloc[-1]:+.1f}%", (ma.index[-1], ma[c].iloc[-1]), xytext=(6, 0), textcoords="offset points",
                       va="center", fontsize=8.5, color=col, fontweight="bold")
        a.plot(ro.index, ro, color=OR, lw=3, label="Cả rổ")
        a.plot(mo["dinh"].index, mo["dinh"] * 100, color=GRN, lw=1, ls=":", label="Đỉnh PnL của lệnh")
        a.plot(mo["cat"].index, mo["cat"] * 100, color=RED, lw=1.4, ls="--", label=f"Mức chốt chặn (−{DDMAX:.0%} từ đỉnh lệnh" + (f"; −{DD_CHAT:.0%} khi đỉnh lãi ≥ +{LAI_KICH:.0%})" if LAI_KICH is not None else ")"))
        a.axhline(0, color=INK, lw=0.8)
        for r in mo["lots"].itertuples():
            a.axvline(r.ngay, color=OR, lw=0.8, ls=":")
            a.annotate(f"{r.sk.split(' (')[0]}\n{r.ngay:%d/%m/%y}", (r.ngay, ro.max()), xytext=(3, 8),
                       textcoords="offset points", fontsize=8, color="#843C0C")
        a.annotate(f"Rổ {ro.iloc[-1]:+.1f}%", (ro.index[-1], ro.iloc[-1]), xytext=(6, 14), textcoords="offset points",
                   fontsize=10, fontweight="bold", color=OR)
        cach = (1 + mo["ro"].iloc[-1]) / (1 + mo["dinh"].iloc[-1]) - 1
        a.set_title(f"LỆNH ĐANG MỞ — {ten} | vào {mo['t0']:%d/%m/%Y}, {len(mo['lots'])} bậc | PnL {mo['ro'].iloc[-1]:+.1%}, "
                    f"đỉnh {mo['dinh'].iloc[-1]:+.1%}, đang cách đỉnh {cach:.1%} (chốt chặn ở −{DDMAX:.0%}) | giá đến {mo['ro'].index[-1]:%d/%m/%Y}",
                    loc="left", fontweight="bold", fontsize=10.5)
        a.text(0.995, 0.02, "PnL từng mã tính trên giá vốn bình quân của các bậc đã mua → đường nhảy tại ngày mua bậc 2",
               transform=a.transAxes, ha="right", fontsize=8, color="gray")
        tn = ro.index[-1]
        a.set_xlim(mo["t0"] - pd.Timedelta(days=3), tn + pd.Timedelta(days=max(12, (tn - mo["t0"]).days // 7)))
        _luoi_ngay(a, mo["t0"], tn, rong=True)
        lo = min(ro.min(), ma.min().min(), mo["cat"].min() * 100)
        hi = max(ro.max(), ma.max().max())
        _luoi_y(a, lo, hi, n_major=14)
    else:
        a.text(0.5, 0.5, f"ĐANG ĐỨNG NGOÀI (tiền gửi) — lệnh gần nhất đóng {Sl.ngay.max():%d/%m/%Y}: {Sl.lai.iloc[-1]:+.1%}",
               ha="center", va="center", fontsize=13, transform=a.transAxes)
        a.set_title(f"LỆNH ĐANG MỞ — {ten} | cập nhật {D[-1]:%d/%m/%Y}", loc="left", fontweight="bold", fontsize=10.5)
    a.legend(frameon=False, fontsize=8.5, loc="upper left")

    # 2a) PnL mọi lệnh theo số phiên kể từ ngày vào
    a = fig.add_subplot(gs[1, 0])
    ds = list(PL.vao.drop_duplicates())
    for j, v in enumerate(ds):
        g = PL[PL.vao == v]
        x = np.arange(len(g))
        cur = mo is not None and v == mo["t0"]
        col = OR if cur else PAL[j % len(PAL)]
        a.plot(x, g.lai * 100, color=col, lw=2.6 if cur else 1.1, alpha=1 if cur else 0.75)
        a.annotate(f"{v:%m/%y} {g.lai.iloc[-1]:+.0%}", (x[-1], g.lai.iloc[-1] * 100), xytext=(4, 0), textcoords="offset points",
                   fontsize=8, color=col, fontweight="bold" if cur else "normal", va="center")
    a.axhline(0, color=INK, lw=0.8)
    from matplotlib.ticker import MultipleLocator
    _luoi_y(a, PL.lai.min() * 100, PL.lai.max() * 100, n_major=9)
    a.xaxis.set_major_locator(MultipleLocator(50)); a.xaxis.set_minor_locator(MultipleLocator(10))
    a.grid(which="major", axis="x", alpha=0.35); a.grid(which="minor", axis="x", alpha=0.12)
    a.set_xlabel("số phiên kể từ ngày vào lệnh")
    a.set_title("PnL từng lệnh theo số phiên — lệnh đang mở tô đậm màu cam", loc="left", fontsize=9, fontweight="bold")

    # 2b) Kết quả từng lệnh + đỉnh PnL đạt được
    a = fig.add_subplot(gs[1, 1])
    rows = []
    for v in ds:
        g = PL[PL.vao == v]
        cur = mo is not None and v == mo["t0"]
        rows.append({"vao": v, "ra": None if cur else g.ngay.iloc[-1], "lai": g.lai.iloc[-1], "dinh": g.dinh.iloc[-1], "mo": cur})
    T = pd.DataFrame(rows)
    x = np.arange(len(T))
    a.bar(x, T.lai * 100, color=[OR if m else (GRN if l > 0 else RED) for m, l in zip(T.mo, T.lai)],
          hatch=["//" if m else "" for m in T.mo], edgecolor="white", width=0.65)
    a.scatter(x, T.dinh * 100, marker="_", s=380, color=INK, lw=1.8, zorder=5, label="Đỉnh PnL trong lệnh")
    for i, r in T.iterrows():
        a.annotate(f"{r.lai:+.0%}", (i, r.lai * 100), xytext=(0, 4 if r.lai >= 0 else -11), textcoords="offset points",
                   ha="center", fontsize=8.5, fontweight="bold")
    a.set_xticks(x, [f"{r.vao:%m/%y}\n→ {'nay' if r.mo else format(r.ra, '%m/%y')}" for r in T.itertuples()], fontsize=8)
    a.axhline(0, color=INK, lw=0.8)
    a.yaxis.set_major_formatter(PercentFormatter()); a.grid(alpha=0.2, axis="y"); a.legend(frameon=False, fontsize=8, loc="upper right")
    a.set_title(f"Kết quả từng lệnh — thắng {int((T[~T.mo].lai > 0).sum())}/{int((~T.mo).sum())} lệnh đã đóng, "
                f"lãi TB {T[~T.mo].lai.mean():+.0%}", loc="left", fontsize=9, fontweight="bold")

    # 3) NAV + sụt giảm
    a = fig.add_subplot(gs[2, :])
    yrs = (D[-1] - D[0]).days / 365.25
    a.plot(NAV.index, NAV, color=OR, lw=2, label=f"NAV chiến lược {NAV.iloc[-1]:.1f}x (CAGR {NAV.iloc[-1] ** (1 / yrs) - 1:+.1%})")
    a.set_yscale("log"); a.grid(alpha=0.2)
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    a.yaxis.set_major_locator(FixedLocator([v for v in (1, 2, 3, 5, 10, 20, 30, 50) if v <= NAV.max() * 1.2]))
    a.yaxis.set_minor_locator(NullLocator())
    a.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}x"))
    for t0, t1 in zip(T.vao, T.ra.fillna(D[-1])):
        a.axvspan(t0, t1, color=OR, alpha=0.08)
    b2 = a.twinx()
    dd = (NAV / NAV.cummax() - 1) * 100
    b2.fill_between(dd.index, dd, 0, color=RED, alpha=0.18, label=f"Sụt từ đỉnh NAV (tối đa {dd.min():.0f}%)")
    b2.set_ylim(dd.min() * 3, 0); b2.yaxis.set_major_formatter(PercentFormatter())
    h1, l1 = a.get_legend_handles_labels(); h2, l2 = b2.get_legend_handles_labels()
    a.legend(h1 + h2, l1 + l2, frameon=False, fontsize=8.5, loc="upper left")
    a.xaxis.set_major_locator(mdates.YearLocator()); a.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    a.set_title("NAV danh mục (thang log) — vùng cam là thời gian có hàng", loc="left", fontsize=9, fontweight="bold")
    fig.savefig(out_png, dpi=130, bbox_inches="tight")
    plt.close(fig)

    # CSV: PnL theo ngày mọi lệnh + từng mã của lệnh đang mở
    outp = PL.copy()
    if mo:
        w = mo["ma"].add_prefix("lai_")
        w["muc_cat"] = mo["cat"]
        w = w.rename_axis("ngay").reset_index()
        outp = outp.merge(w, on="ngay", how="left")
    outp.assign(ngay=outp.ngay.dt.strftime("%Y-%m-%d"), vao=outp.vao.dt.strftime("%Y-%m-%d")).round(4).to_csv(
        out_csv, index=False, encoding="utf-8-sig")
    log(f"  -> {out_png}\n  -> {out_csv}")
    return mo


def ve(S, NAV, EXPO, E, px, pxf, shm, vni, n, out, sec=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    plt.rcParams.update({"font.family": "Segoe UI", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    INK, OR, GR, RED, GRN, BLU = "#262626", "#ED7D31", "#A6A6A6", "#C00000", "#00B050", "#4472C4"
    D = S.index
    vn = vni.reindex(D, method="ffill")
    vn = vn / vn.iloc[0]
    sel0 = top_n(px, pxf, shm, D[0], n)
    bh = (pxf.loc[D[0]:, sel0] / px.loc[D[0], sel0]).mean(axis=1).reindex(D, method="ffill")
    B, Sl = E[E.sk.str.startswith("MUA")], E[E.sk == "BÁN"]
    yrs = (D[-1] - D[0]).days / 365.25
    cagr, dd = NAV.iloc[-1] ** (1 / yrs) - 1, (NAV / NAV.cummax() - 1).min()
    PU = "#7030A0"
    fig = plt.figure(figsize=(15, 21), constrained_layout=True)
    gs = fig.add_gridspec(7, 1, height_ratios=[3, 0.8, 1.35, 1.35, 0.9, 2, 1.7])
    ax = [fig.add_subplot(gs[0])]
    ax += [fig.add_subplot(gs[i], sharex=ax[0]) for i in range(1, 6)]
    for a in ax[:5]:
        plt.setp(a.get_xticklabels(), visible=False)

    def to_bat_thuong(a, nhan=False):
        a0, b0 = BAT_THUONG
        a.axvspan(pd.Timestamp(a0), pd.Timestamp(b0), color=GR, alpha=0.13, hatch="//", lw=0)
        if nhan:
            a.annotate("BẤT THƯỜNG 2020–22\n(không dùng chọn tham số)", (pd.Timestamp("2021-07-01"), 1), xycoords=("data", "axes fraction"),
                       xytext=(0, -6), textcoords="offset points", ha="center", va="top", fontsize=8, color="dimgray", fontweight="bold")

    a = ax[0]
    to_bat_thuong(a, True)
    a.plot(bh.index, bh, color=GR, lw=1.1, label=(f"Rổ cố định {', '.join(FIXED)} (mua-giữ, đầu kỳ = 1)" if FIXED else f"Top {n} CTCK vốn hoá lớn (mua-giữ, đầu kỳ = 1)"))
    a.plot(vn.index, vn, color=INK, lw=0.9, alpha=0.75, label="VN-Index")
    a.set_yscale("log")
    st = None
    for t, on in (EXPO > 0).items():
        if on and st is None:
            st = t
        elif not on and st is not None:
            a.axvspan(st, t, color=OR, alpha=0.13); st = None
    if st is not None:
        a.axvspan(st, D[-1], color=OR, alpha=0.13)
    Bs, Bl = B[~B.sk.str.contains("lại")], B[B.sk.str.contains("lại")]
    a.scatter(Bs.ngay, bh.reindex(Bs.ngay, method="ffill"), s=115, marker="^", color=OR, edgecolor=INK, lw=0.6, zorder=5, label="Mua theo tín hiệu (50% vốn/bậc)")
    a.scatter(Bl.ngay, bh.reindex(Bl.ngay, method="ffill"), s=115, marker="^", color=PU, edgecolor=INK, lw=0.6, zorder=5, label="Mua lại khi rổ vượt đỉnh cũ (100%)")
    a.scatter(Sl.ngay, bh.reindex(Sl.ngay, method="ffill"), s=135, marker="v", color=GRN, edgecolor=INK, lw=0.6, zorder=5, label="Bán hết")

    def ngan(ly):
        if ly.startswith("LNST"):
            return "LNST chững"
        if "chốt lời" in ly:
            return f"chốt lời −{DD_CHAT:.0%}"
        if ly.startswith("chốt chặn"):
            return f"cắt −{DDMAX:.0%}"
        return ly
    for j, r in enumerate(Sl.itertuples()):
        a.annotate(f"{r.lai:+.0%}\n{ngan(r.ly_do)}", (r.ngay, bh.asof(r.ngay)), xytext=(4, 14 if j % 2 == 0 else 34), textcoords="offset points",
                   fontsize=8, fontweight="bold", color=GRN if r.lai > 0 else RED)
    truoc = None
    for r in Bs[~Bs.ngay.duplicated()].itertuples():
        if truoc is not None and (r.ngay - truoc).days < 10:          # 2 bậc sát nhau → 1 nhãn
            continue
        truoc = r.ngay
        a.annotate(f"{r.ngay:%d/%m/%y}", (r.ngay, bh.asof(r.ngay)), xytext=(0, -18), textcoords="offset points",
                   ha="center", fontsize=7.5, color="#843C0C")
    from matplotlib.ticker import FixedLocator as _FL, FuncFormatter as _FF, NullLocator as _NL
    a.set_ylim(bh.min() * 0.85, max(bh.max(), vn.max()) * 1.9)
    a.yaxis.set_major_locator(_FL([0.5, 0.7, 1, 1.5, 2, 3, 5, 7, 10, 15, 20]))
    a.yaxis.set_minor_locator(_NL()); a.yaxis.set_major_formatter(_FF(lambda v, _: f"{v:g}x"))
    a.legend(frameon=False, fontsize=8, loc="upper left", ncol=3); a.grid(alpha=0.2)
    a.set_title(f"CHIẾN LƯỢC NGÀNH CHỨNG KHOÁN — {('rổ ' + ', '.join(FIXED)) if FIXED else ('top %d CTCK vốn hoá lớn' % n)}\n"
                "MUA: định giá VN-Index loại Vin ≤ TB −1,7σ / −1,9σ (cửa sổ 3 hoặc 5 năm) + thanh khoản quý giảm + LNST ngành tăng (ưu tiên QoQ)\n"
                + (f"BÁN: LNST ngành giảm QoQ sau ≥ {G_MIN} quý tăng" if EXIT == "lnst" else "BÁN: P/B ngành CK cắt xuống +2,5σ")
                + f" | cắt −{DDMAX:.0%} từ đỉnh lệnh" + (f", siết −{DD_CHAT:.0%} khi đỉnh lãi ≥ +{LAI_KICH:.0%}" if LAI_KICH is not None else "")
                + (" | MUA LẠI khi rổ vượt đỉnh cũ sau chốt lời" if MUA_LAI and LAI_KICH is not None else ""),
                loc="left", fontweight="bold", fontsize=10.5)

    a = ax[1]
    a.fill_between(EXPO.index, 0, EXPO * 100, step="post", color=OR, alpha=0.6)
    a.set_ylim(0, 105); a.set_ylabel("% vốn"); a.grid(alpha=0.2)
    a.set_title(f"Tỷ trọng cổ phiếu (còn lại gửi 5%/năm) — trung bình {EXPO.mean():.0%}", loc="left", fontsize=9, fontweight="bold")

    a = ax[2]
    a.plot(D, S.z_pe3, color=INK, lw=0.9, label="z P/E VN-Index loại Vin (3 năm)")
    a.plot(D, S.z_pe5, color=GR, lw=0.9, label="z (5 năm)")
    for kk, col in ((K1, OR), (K2, "#843C0C")):
        a.axhline(-kk, color=col, lw=1.1, ls="--", label=f"−{kk}σ → mua 50%")
    a.axhline(0, color=GR, lw=0.8, ls=":")
    a.scatter(B.ngay, [S.z_pe3.asof(d) for d in B.ngay], s=45, color=OR, zorder=5)
    a.legend(frameon=False, fontsize=8, ncol=4, loc="lower left"); a.grid(alpha=0.2); a.set_ylabel("σ")
    a.set_title("Điều kiện 1 — định giá thị trường", loc="left", fontsize=9, fontweight="bold")

    a = ax[3]
    if EXIT == "lnst" and sec is not None:
        q = sec[(sec.index + pd.Timedelta(days=LAG)) >= D[0]] / 1e3
        av = q.index + pd.Timedelta(days=LAG)
        up = (sec > sec.shift(1)).reindex(q.index)
        a.bar(av, q, width=60, color=[GRN if u else RED for u in up], alpha=0.75)
        for d0 in Sl[Sl.ly_do.str.startswith("LNST")].ngay:
            a.axvline(d0, color=INK, lw=1.2, ls="--")
            a.annotate(f"BÁN {d0:%m/%y}", (d0, q.max() * 0.9), xytext=(3, 0), textcoords="offset points", fontsize=8, fontweight="bold")
        a.set_ylabel("nghìn tỷ đ"); a.grid(alpha=0.2)
        a.set_title(f"Tín hiệu BÁN — LNST ngành CK theo quý (xanh = tăng QoQ, đỏ = giảm; đặt tại ngày có BCTC = cuối quý + {LAG} ngày). "
                    f"Bán khi quý GIẢM xuất hiện sau ≥ {G_MIN} quý tăng liên tiếp trong lệnh", loc="left", fontsize=9, fontweight="bold")
    else:
        a.plot(D, S.z_pb3, color=INK, lw=0.9, label="z P/B ngành CK (3 năm)")
        a.axhline(XSELL, color=GRN, lw=1.2, ls="--", label=f"+{XSELL}σ — bán khi cắt xuống")
        a.axhline(0, color=GR, lw=0.8, ls=":")
        a.fill_between(D, XSELL, S.z_pb3.where(S.z_pb3 > XSELL), color=GRN, alpha=0.15)
        a.scatter(Sl.ngay, [S.z_pb3.asof(d) for d in Sl.ngay], s=55, color=GRN, edgecolor=INK, zorder=5)
        a.legend(frameon=False, fontsize=8, ncol=2, loc="upper left"); a.grid(alpha=0.2); a.set_ylabel("σ")
        a.set_title("Tín hiệu BÁN — định giá ngành CK", loc="left", fontsize=9, fontweight="bold")

    a = ax[4]
    a.fill_between(D, 0, S.muc_cong, step="post", color=BLU, alpha=0.3)
    a.set_ylim(0, 2.2); a.set_yticks([0, 1, 2]); a.set_yticklabels(["đóng", "½ vốn", "đủ vốn"])
    for d0 in B.ngay:
        a.axvline(d0, color=OR, lw=0.8)
    a.set_title("Điều kiện 2 & 3 — cổng thanh khoản (GTGD quý giảm) và lợi nhuận ngành (QoQ ưu tiên, YoY chỉ nửa vốn)",
                loc="left", fontsize=9, fontweight="bold")
    a.grid(alpha=0.2)

    a = ax[5]
    to_bat_thuong(a)
    a.plot(NAV.index, NAV, color=OR, lw=2.2, label=f"Chiến lược: {NAV.iloc[-1]:.1f}x, CAGR {cagr:+.1%}, sụt tối đa {dd:.0%}")
    a.plot(bh.index, bh, color=GR, lw=1, label=(f"Mua-giữ rổ cố định: {bh.iloc[-1]:.1f}x" if FIXED else f"Mua-giữ top {n} CK: {bh.iloc[-1]:.1f}x"))
    a.plot(vn.index, vn, color=INK, lw=1, label=f"Mua-giữ VN-Index: {vn.iloc[-1]:.1f}x")
    a.set_yscale("log"); a.legend(frameon=False, fontsize=8, loc="upper left"); a.grid(alpha=0.2)
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    a.yaxis.set_major_locator(FixedLocator([v for v in (0.5, 1, 2, 3, 5, 10, 20, 30, 50, 100) if v <= max(NAV.max(), bh.max()) * 1.3]))
    a.yaxis.set_minor_locator(NullLocator()); a.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}x"))
    a.set_title("Giá trị danh mục (thang log) — vùng gạch xám = giai đoạn bất thường", loc="left", fontsize=9, fontweight="bold")
    a.xaxis.set_major_locator(mdates.YearLocator()); a.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # --- Hiệu suất theo chu kỳ: chiến lược vs mua-giữ rổ (cuối kỳ và cao nhất trong kỳ)
    a = fig.add_subplot(gs[6])
    rows = []
    for ten, (a0, b0) in CHU_KY.items():
        s = NAV.loc[a0:b0]
        if s.empty:
            continue
        prev = NAV.loc[:a0].iloc[:-1]
        base = prev.iloc[-1] if len(prev) else s.iloc[0]
        t0 = s.index[0]
        sel = top_n(px, pxf, shm, t0, n)
        h = (pxf.loc[t0:b0, sel] / pxf.loc[t0, sel]).mean(axis=1)
        rows.append((ten, s.iloc[-1] / base - 1, h.iloc[-1] - 1, h.max() - 1, "BT" in ten))
    x = np.arange(len(rows))
    w = 0.27
    a.bar(x - w, [r[1] * 100 for r in rows], w, color=[GR if r[4] else OR for r in rows], label="Chiến lược")
    a.bar(x, [r[2] * 100 for r in rows], w, color="#BFBFBF", edgecolor=INK, lw=0.4, label="Mua-giữ rổ (cuối kỳ)")
    a.scatter(x, [r[3] * 100 for r in rows], marker="_", s=500, color=INK, lw=2, zorder=5, label="Mua-giữ rổ: cao nhất trong kỳ")
    for i, r in enumerate(rows):
        a.annotate(f"{r[1]:+.0%}", (i - w, r[1] * 100), xytext=(0, 3 if r[1] >= 0 else -12), textcoords="offset points",
                   ha="center", fontsize=9, fontweight="bold", color=INK)
        a.annotate(f"{r[2]:+.0%}", (i, r[2] * 100), xytext=(0, 3 if r[2] >= 0 else -12), textcoords="offset points", ha="center", fontsize=8)
    bt = [r for r in rows if not r[4]]
    yrs_bt = sum((min(pd.Timestamp(CHU_KY[r[0]][1]), D[-1]) - max(pd.Timestamp(CHU_KY[r[0]][0]), D[0])).days for r in bt) / 365.25
    g = np.prod([1 + r[1] for r in bt])
    a.set_xticks(x, [r[0] for r in rows])
    a.axhline(0, color=INK, lw=0.8); a.grid(alpha=0.2, axis="y"); a.legend(frameon=False, fontsize=8, loc="upper left")
    a.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    a.set_title(f"Hiệu suất theo chu kỳ — các chu kỳ BÌNH THƯỜNG gộp lại: {g - 1:+.0%}, tức {g ** (1 / yrs_bt) - 1:+.1%}/năm "
                f"(cột xám = giai đoạn bất thường, chỉ để tham khảo)", loc="left", fontsize=9, fontweight="bold")
    fig.text(0.01, -0.01, "Định giá VN-Index: Vietcap IQ 2009–07/2019 (×hệ số loại Vin) + VNDirect loại VIC/VHM/VRE/VPL. "
             "Định giá & LNST ngành CK: VCSH và LNST quý FiinProX × giá TradingView. Thanh khoản: GTGD 3 sàn (index-fetcher). "
             "Rổ CK thiếu CTCK đã huỷ niêm yết; chưa tính phí, thuế, cổ tức.", fontsize=8, color="gray")
    fig.savefig(out, dpi=130, bbox_inches="tight")
    log(f"  -> {out}")


def main():
    global FIXED, EXIT
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5, help="số mã trong danh mục (mặc định 5)")
    ap.add_argument("--backtest", action="store_true", help="in bảng lệnh + vẽ biểu đồ")
    ap.add_argument("--fixed", default="", help="rổ cố định, vd SSI,VND,HCM,VCI,MBS (bỏ qua chọn theo vốn hoá)")
    ap.add_argument("--ban", choices=["lnst", "dinhgia"], default=EXIT, help="luật bán: lnst (mặc định) hoặc dinhgia (luật cũ)")
    a = ap.parse_args()
    EXIT = a.ban
    if a.fixed:
        FIXED = [x.strip().upper() for x in a.fixed.split(",") if x.strip()]
        a.top = len(FIXED)
        log(f"Rổ cố định: {', '.join(FIXED)}")
    log("Đang nạp dữ liệu ...")
    S, px, pxf, sh, shm, vni, gq, sec = load()
    NAV, EXPO, E = backtest(S, px, pxf, shm, a.top)
    tag = f"{'fixed' if FIXED else 'top'}{a.top}" + ("" if EXIT == "lnst" else "_dinhgia")
    S.round(4).to_csv(os.path.join(HERE, "ck_signals.csv"), encoding="utf-8-sig")
    E.assign(ngay=E.ngay.dt.strftime("%Y-%m-%d")).to_csv(os.path.join(HERE, f"ck_trades_{tag}.csv"), index=False, encoding="utf-8-sig")
    NAV.rename("nav").to_csv(os.path.join(HERE, f"ck_nav_{tag}.csv"), encoding="utf-8-sig")
    if a.backtest:
        log("\nNHẬT KÝ LỆNH")
        log(E.drop(columns=["von"], errors="ignore").assign(ngay=E.ngay.dt.strftime("%d/%m/%Y"),
                     lai=E.lai.map(lambda x: "" if pd.isna(x) else f"{x:+.0%}"),
                     dinh=E.dinh.map(lambda x: "" if pd.isna(x) else f"{x:+.0%}")).to_string(index=False))
        ve(S, NAV, EXPO, E, px, pxf, shm, vni, a.top, os.path.join(HERE, f"ck_strategy_{tag}.png"), sec)
    ve_pnl(S, NAV, E, px, pxf, a.top, os.path.join(HERE, f"ck_pnl_{tag}.png"), os.path.join(HERE, f"ck_pnl_{tag}.csv"))
    ve_tung_lenh(E, px, pxf, S.index, ("rổ " + ", ".join(FIXED)) if FIXED else f"top {a.top} CTCK vốn hoá lớn",
                 os.path.join(HERE, f"ck_pnl_lenh_{tag}.png"))
    trang_thai(S, px, pxf, shm, a.top, NAV, E)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    main()

