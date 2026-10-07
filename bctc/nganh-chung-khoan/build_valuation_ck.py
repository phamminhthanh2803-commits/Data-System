# -*- coding: utf-8 -*-
r"""build_valuation_ck.py — ĐỊNH GIÁ TOÀN NGÀNH CHỨNG KHOÁN theo ngày + LNST TOÀN NGÀNH theo quý/TTM (gọi cuối run_pipeline.py sau build_nganh_ck).

Nguồn:  giá đóng cửa từng mã: D:\market-data\index-fetcher\tv-history.csv (TradingView, cập nhật hằng ngày)
        LNST, VCSH theo quý: fact_items.csv (FiinProX); số CP = số CP HIỆN HÀNH (TradingView) vì giá TradingView đã điều chỉnh (như VCI)
        LNST toàn ngành (cả công ty chưa niêm yết): industry_summary.csv
Quy ước: BCTC quý q coi là "có" từ ngày cuối quý + LAG_DAYS; tại mỗi ngày dùng quý gần nhất đã có.
         P/E ngành = Σ vốn hoá / Σ LNST TTM (gồm cả công ty lỗ, như VNDirect); P/E ex-loss chỉ tính công ty lãi; P/B = Σ vốn hoá / Σ VCSH.
Ra (cùng thư mục):
  valuation_nganh_ck_daily.csv   date | n_ma | mcap_ty | npat_ttm_ty | equity_ty | pe | pe_ex_loss | pb | pe_coverage
  valuation_ck_stocks_daily.csv  ticker | date | close | shares | mcap_ty | npat_ttm_ty | equity_ty | pe | pb | period_bctc   (cho PivotTable)
  npat_nganh_ck_quarterly.csv    period | npat_all_ty (87 cty) | npat_listed_ty | npat_ttm_all | npat_ttm_listed | yoy...
  dinh-gia-nganh-ck.png ; bảng valuation_daily / npat_quarterly trong nganh_chung_khoan.sqlite
"""
import os, sqlite3, sys, warnings
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
MD_ROOT = os.path.normpath(os.environ.get("MD_ROOT", "D:/market-data"))
TV = os.path.join(MD_ROOT, "index-fetcher", "tv-history.csv")
META = os.path.join(MD_ROOT, "index-fetcher", "raw", "vn_screener_meta.csv")
START = "2015-01-01"
LAG_DAYS = 30


def log(m):
    print(m, flush=True)


def qend(period):
    q, y = period.split("/"); q = int(q[1]); y = int(y)
    return pd.Timestamp(y, q * 3, 1) + pd.offsets.MonthEnd(0)


def main():
    dc = pd.read_csv(os.path.join(HERE, "dim_company.csv"))
    listed = [t for t in dc.ticker if isinstance(t, str) and t.isupper() and t.isalnum() and len(t) == 3]
    tv = pd.read_csv(TV, dtype={"date": str}, usecols=["date", "symbol", "close"])
    tv = tv[tv.symbol.isin(listed) & (tv.date >= START)].copy(); tv["date"] = pd.to_datetime(tv.date)
    have = sorted(tv.symbol.unique())
    log(f"  gia TradingView: {len(have)} ma niem yet / {len(listed)} ma 3 ky tu; thieu gia: {sorted(set(listed) - set(have))}")
    px = tv.pivot_table(index="date", columns="symbol", values="close").sort_index().ffill()

    fi = pd.read_csv(os.path.join(HERE, "fact_items.csv"), dtype={"period": str})
    q = fi[(fi.freq == "Q") & fi.ticker.isin(have) & fi.metric.isin(["npat", "equity", "charter_capital"])]
    w = q.pivot_table(index=["ticker", "period"], columns="metric", values="value", aggfunc="first").reset_index()
    w["qend"] = w.period.map(qend); w["avail"] = w.qend + pd.Timedelta(days=LAG_DAYS)
    w = w.sort_values(["ticker", "qend"])
    w["t"] = w.qend.dt.year * 4 + (w.qend.dt.month - 1) // 3
    g = w.groupby("ticker")
    ok4 = g.t.shift(3) == w.t - 3
    w["npat_ttm"] = np.where(ok4, g.npat.transform(lambda s: s.rolling(4, min_periods=4).sum()), np.nan)
    # SO CO PHIEU: gia TradingView DA DIEU CHINH chia tach/quyen -> phai nhan voi so CP HIEN HANH cho ca lich su (cung cach VCI/fs-extractor);
    # nhan voi von gop tung quy se bi chiet khau 2 lan (2019 SSI: 3.117 ty thay vi ~15.000). Thieu so CP hien hanh thi lay von gop quy moi nhat /10.000d.
    meta = pd.read_csv(META).set_index("name").total_shares_outstanding_fundamental
    last_charter = w.sort_values("qend").groupby("ticker").charter_capital.last() * 1e9 / 1e4
    w["shares"] = w.ticker.map(meta).where(w.ticker.map(meta) > 0, w.ticker.map(last_charter))

    # ---- panel ngày: quý gần nhất đã công bố tại mỗi ngày (merge_asof theo ticker)
    daily = px.stack().rename("close").reset_index().rename(columns={"symbol": "ticker"}).sort_values("date")
    fund = w[["ticker", "avail", "period", "shares", "npat_ttm", "equity"]].rename(columns={"avail": "date"}).sort_values("date")
    d = pd.merge_asof(daily, fund, on="date", by="ticker", direction="backward")
    d = d.dropna(subset=["shares"])
    d["mcap_ty"] = d.close * d.shares / 1e9
    d["pe"] = np.where(d.npat_ttm > 0, d.mcap_ty / d.npat_ttm, np.nan)
    d["pb"] = np.where(d.equity > 0, d.mcap_ty / d.equity, np.nan)
    d = d.rename(columns={"npat_ttm": "npat_ttm_ty", "equity": "equity_ty", "period": "period_bctc"})
    d[["ticker", "date", "close", "shares", "mcap_ty", "npat_ttm_ty", "equity_ty", "pe", "pb", "period_bctc"]].round(4).to_csv(
        os.path.join(HERE, "valuation_ck_stocks_daily.csv"), index=False, encoding="utf-8-sig")

    # ---- toàn ngành theo ngày
    def agg(x):
        pe_set = x.dropna(subset=["npat_ttm_ty"]); pos = pe_set[pe_set.npat_ttm_ty > 0]; pb_set = x[x.equity_ty > 0]
        return pd.Series({"n_ma": len(x), "mcap_ty": x.mcap_ty.sum(),
                          "npat_ttm_ty": pe_set.npat_ttm_ty.sum(), "equity_ty": pb_set.equity_ty.sum(),
                          "pe": pe_set.mcap_ty.sum() / pe_set.npat_ttm_ty.sum() if pe_set.npat_ttm_ty.sum() > 0 else np.nan,
                          "pe_ex_loss": pos.mcap_ty.sum() / pos.npat_ttm_ty.sum() if pos.npat_ttm_ty.sum() > 0 else np.nan,
                          "pb": pb_set.mcap_ty.sum() / pb_set.equity_ty.sum() if pb_set.equity_ty.sum() > 0 else np.nan,
                          "pe_coverage": pe_set.mcap_ty.sum() / x.mcap_ty.sum() if x.mcap_ty.sum() > 0 else np.nan})
    ind = d.groupby("date").apply(agg).reset_index()
    ind = ind[ind.n_ma >= 15]          # thanh phan doi theo thoi gian (so ma niem yet tang), giu tu khi co >= 15 ma
    ind.round(4).to_csv(os.path.join(HERE, "valuation_nganh_ck_daily.csv"), index=False, encoding="utf-8-sig")

    # ---- LNST toàn ngành theo quý: 87 cty (industry_summary) + nhóm niêm yết
    isum = pd.read_csv(os.path.join(HERE, "industry_summary.csv"), dtype={"period": str})
    isum = isum[isum.freq == "Q"][["period", "year", "quarter", "sum_npat", "sum_npat_ttm", "n_cong_ty"]].rename(
        columns={"sum_npat": "npat_all_ty", "sum_npat_ttm": "npat_ttm_all_ty", "n_cong_ty": "n_all"})
    ql = w.groupby("period").agg(npat_listed_ty=("npat", "sum"), npat_ttm_listed_ty=("npat_ttm", "sum"), n_listed=("ticker", "size")).reset_index()
    npq = isum.merge(ql, on="period", how="left"); npq["qend"] = npq.period.map(qend); npq = npq.sort_values("qend")
    for c in ("npat_all_ty", "npat_listed_ty", "npat_ttm_all_ty", "npat_ttm_listed_ty"):
        npq[c + "_yoy"] = npq[c] / npq[c].shift(4) - 1
    npq.round(4).to_csv(os.path.join(HERE, "npat_nganh_ck_quarterly.csv"), index=False, encoding="utf-8-sig")

    con = sqlite3.connect(os.path.join(HERE, "nganh_chung_khoan.sqlite"))
    ind.assign(date=ind.date.dt.strftime("%Y-%m-%d")).to_sql("valuation_daily", con, if_exists="replace", index=False)
    d.assign(date=d.date.dt.strftime("%Y-%m-%d"))[["ticker", "date", "close", "shares", "mcap_ty", "npat_ttm_ty", "equity_ty", "pe", "pb", "period_bctc"]].to_sql("valuation_stocks_daily", con, if_exists="replace", index=False)
    npq.assign(qend=npq.qend.dt.strftime("%Y-%m-%d")).to_sql("npat_quarterly", con, if_exists="replace", index=False)
    con.commit(); con.close()

    # ---- biểu đồ
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt, matplotlib.dates as mdates
    plt.rcParams.update({"font.family": "Segoe UI", "font.size": 9, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(2, 2, figsize=(16, 10), constrained_layout=True)
    s = ind.set_index("date")
    ax[0, 0].plot(s.pe, color="#d62728", lw=1.4, label=f"P/E (gồm lỗ) nay {s.pe.iloc[-1]:.1f}"); ax[0, 0].plot(s.pe_ex_loss, color="#ff7f0e", lw=1, ls="--", label=f"P/E ex-loss {s.pe_ex_loss.iloc[-1]:.1f}")
    ax[0, 0].axhline(s.pe.median(), color="gray", lw=0.8, ls=":", label=f"trung vị {s.pe.median():.1f}"); ax[0, 0].set_ylim(0, min(60, s.pe.quantile(0.99) * 1.2)); ax[0, 0].legend(fontsize=8, frameon=False); ax[0, 0].grid(alpha=0.25)
    ax[0, 0].set_title("1. P/E ngành chứng khoán (Σ vốn hoá / Σ LNST TTM)", fontsize=10, fontweight="bold", loc="left")
    ax[0, 1].plot(s.pb, color="#1f77b4", lw=1.4, label=f"P/B nay {s.pb.iloc[-1]:.2f}"); ax[0, 1].axhline(s.pb.median(), color="gray", lw=0.8, ls=":", label=f"trung vị {s.pb.median():.2f}"); ax[0, 1].legend(fontsize=8, frameon=False); ax[0, 1].grid(alpha=0.25)
    ax[0, 1].set_title("2. P/B ngành (Σ vốn hoá / Σ VCSH)", fontsize=10, fontweight="bold", loc="left")
    ax[1, 0].plot(s.mcap_ty / 1e3, color="black", lw=1.4, label=f"Vốn hoá {len(have)} mã niêm yết (nghìn tỷ) nay {s.mcap_ty.iloc[-1]/1e3:.0f}"); ax[1, 0].legend(fontsize=8, frameon=False); ax[1, 0].grid(alpha=0.25)
    ax[1, 0].set_title("3. Vốn hoá ngành", fontsize=10, fontweight="bold", loc="left")
    nq = npq.set_index("qend")
    ax[1, 1].bar(nq.index, nq.npat_all_ty / 1e3, width=60, color="#9ecae1", label="LNST quý, 87 công ty (nghìn tỷ)")
    ax2 = ax[1, 1].twinx(); ax2.plot(nq.npat_ttm_all_ty / 1e3, color="#d62728", lw=1.6, label=f"LNST TTM 87 cty nay {nq.npat_ttm_all_ty.iloc[-1]/1e3:.1f} nghìn tỷ"); ax2.plot(nq.npat_ttm_listed_ty / 1e3, color="#2ca02c", lw=1.2, ls="--", label="LNST TTM niêm yết")
    h1, l1 = ax[1, 1].get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels(); ax[1, 1].legend(h1 + h2, l1 + l2, fontsize=8, frameon=False, loc="upper left"); ax[1, 1].grid(alpha=0.25); ax2.spines["top"].set_visible(False)
    ax[1, 1].set_title("4. Lợi nhuận sau thuế toàn ngành", fontsize=10, fontweight="bold", loc="left")
    for a in ax.flat:
        a.xaxis.set_major_locator(mdates.YearLocator()); a.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.suptitle("Ngành chứng khoán: định giá theo ngày và LNST toàn ngành (pipeline FiinProX + TradingView)", fontsize=13, fontweight="bold")
    fig.text(0.01, -0.015, f"Vốn hoá = giá điều chỉnh × số CP hiện hành (như VCI); BCTC quý có hiệu lực sau cuối quý + {LAG_DAYS} ngày; P/E gồm cả công ty lỗ; ngành 87 công ty gồm cả chưa niêm yết.", fontsize=8, color="gray")
    fig.savefig(os.path.join(HERE, "dinh-gia-nganh-ck.png"), dpi=130, bbox_inches="tight")
    last = ind.iloc[-1]
    log(f"  valuation_nganh_ck_daily: {len(ind):,} ngày {ind.date.min().date()}..{ind.date.max().date()} | nay: {int(last.n_ma)} mã, mcap {last.mcap_ty/1e3:.0f} nghìn tỷ, P/E {last.pe:.1f} (ex-loss {last.pe_ex_loss:.1f}), P/B {last.pb:.2f}, coverage {last.pe_coverage:.0%}")
    log(f"  npat_nganh_ck_quarterly: {len(npq)} quý; {npq.period.iloc[-1]}: LNST quý 87 cty {npq.npat_all_ty.iloc[-1]:,.0f} tỷ, TTM {npq.npat_ttm_all_ty.iloc[-1]:,.0f} tỷ ({npq.npat_ttm_all_ty_yoy.iloc[-1]:+.0%} YoY); niêm yết TTM {npq.npat_ttm_listed_ty.iloc[-1]:,.0f} tỷ")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    main()
