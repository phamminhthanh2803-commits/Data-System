# -*- coding: utf-8 -*-
"""
pages_live.py - trang LIVE (?trang=live): du lieu real-time DNSE tu realtime-lab (parquet xuat moi 5 s), the kieu Genea,
tu lam moi bang st.fragment(run_every=...) voi bo chon tan suat 5 s / 15 s / 60 s / Tat.
Ngoai gio giao dich: hien phien gan nhat co trong data\\ + ghi ro 'bo thu khong chay'.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import data_live as rt
import ui_genea as ui

FREQ = {"5 s": 5, "15 s": 15, "60 s": 60, "Tắt": None}
LUNCH = [dict(bounds=[11.5, 13], pattern="hour")]        # bo khoang nghi trua tren truc gio (CHI cho nen 1 phut:
# chuoi 5 s theo ts_recv van co diem trong gio nghi trua vi DNSE tiep tuc phat market_index -> khong cat)
H = 340


# ------------------------------------------------------------------ TIEN ICH
def _show(c, fig, df=None, ten=None, note=None, height=None, lunch=False):
    """Ve Plotly trong the Genea nhung GIU dinh dang truc gio (Card.chart ep tickformat theo ngay). lunch=True: cat 11:30-13:00."""
    if fig is None:
        c.empty()
        return
    if height:
        fig.update_layout(height=height)
    fig.update_xaxes(tickformat="%H:%M", hoverformat="%H:%M:%S", rangebreaks=LUNCH if lunch else None)
    with c.body():
        st.plotly_chart(fig, width="stretch", config=ui.PLOTLY_CONFIG, key=f"fig_live_{c.key}")
    c.export(df, ten, fig)
    if note:
        with c._foot:  # noqa: SLF001
            st.markdown(f'<div class="gn-note">{note}</div>', unsafe_allow_html=True)


def _delta(ch, pct, nd=2):
    if ch is None or pd.isna(ch):
        return "", 0
    s = f"{ui.fmt_vn(ch, nd, dau=True)}"
    if pct is not None and pd.notna(pct):
        s += f" ({ui.fmt_vn(pct, 2, dau=True)}%)"
    return s, int(np.sign(ch))


def _kpi_html(items):
    """items: (label, value, delta, cls) cls: up/down/warn/''."""
    h = ['<div class="gn-kpis" style="grid-template-columns:repeat(auto-fit,minmax(138px,1fr))">']
    for label, value, delta, cls in items:
        style = ' style="color:#ed7d31;font-weight:600"' if cls == "warn" else ""
        h.append(f'<div class="gn-kpi"><div class="l">{label}</div><div class="v">{value}</div>'
                 f'<div class="d {cls if cls in ("up", "down") else ""}"{style}>{delta or "&nbsp;"}</div></div>')
    h.append("</div>")
    return "".join(h)


C_TRAN, C_SAN = "#b23bc9", "#1a9ab8"          # mau gia tran / san (quy uoc bang gia VN)


def _html_board(t: pd.DataFrame, max_h: int | None = None) -> str:
    """Bang gia HTML: ±% va KN rong xanh/do, gia tran tim / san xanh ngoc, so kieu VN; cot chuoi (Nguồn, Giờ, Sàn GD) in nguyen;
    cot '_ex' (san) hien nho duoi ma."""
    cols = [c for c in t.columns if c != "_ex"]
    has_ex = "_ex" in t.columns
    wrap = f'<div class="gn-tblwrap" style="max-height:{max_h}px">' if max_h else '<div class="gn-tblwrap">'
    h = [wrap + '<table class="gn-tbl"><thead><tr><th>' + str(t.index.name or "Mã") + "</th>"]
    h += [f"<th>{c}</th>" for c in cols]
    h.append("</tr></thead><tbody>")
    for sym, r in t.iterrows():
        pct = r.get("±%")
        kcls = "up" if pd.notna(pct) and pct > 0 else ("down" if pd.notna(pct) and pct < 0 else "")
        gia, tran, san = r.get("Giá"), r.get("Trần"), r.get("Sàn")
        gstyle = ""
        if pd.notna(gia) and pd.notna(tran) and gia >= tran - 1e-9:
            gstyle = f' style="color:{C_TRAN};font-weight:600"'
        elif pd.notna(gia) and pd.notna(san) and gia <= san + 1e-9:
            gstyle = f' style="color:{C_SAN};font-weight:600"'
        ex = f'<small>{r["_ex"]}</small>' if has_ex and pd.notna(r.get("_ex")) else ""
        h.append(f'<tr><td><b class="{kcls}"{gstyle}>{sym}</b>{ex}</td>')
        for c in cols:
            v = r[c]
            if v is None or (not isinstance(v, str) and pd.isna(v)):
                h.append('<td class="na">—</td>')
                continue
            if isinstance(v, str):
                h.append(f'<td style="color:var(--ink-2)">{v}</td>')
            elif c == "±%":
                h.append(f'<td class="{kcls}"{gstyle}>{ui.fmt_vn(v, 2, dau=True)}%</td>')
            elif c in ("KN ròng (tỷ)", "KN mua ròng (tỷ)"):
                h.append(f'<td class="{"up" if v > 0 else ("down" if v < 0 else "")}">{ui.fmt_vn(v, 1, dau=True)}</td>')
            elif c == "Giá":
                h.append(f'<td class="{kcls}"{gstyle}>{ui.fmt_vn(v, 2)}</td>')
            elif c == "Trần":
                h.append(f'<td style="color:{C_TRAN}">{ui.fmt_vn(v, 2)}</td>')
            elif c == "Sàn":
                h.append(f'<td style="color:{C_SAN}">{ui.fmt_vn(v, 2)}</td>')
            elif c in ("Bid1", "Ask1", "Cao", "Thấp", "Tham chiếu", "TC"):
                h.append(f"<td>{ui.fmt_vn(v, 2)}</td>")
            elif c in ("KL khớp cuối", "KL tổng", "KL", "Tăng", "Giảm", "Đứng", "Kịch trần", "Kịch sàn", "Có giá", "Niêm yết"):
                h.append(f"<td>{ui.fmt_vn(v, 0)}</td>")
            else:
                h.append(f"<td>{ui.fmt_vn(v, 1)}</td>")
        h.append("</tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


def _html_top(x: pd.DataFrame, title: str, color: str) -> str:
    """Bang nho top 10: Ma (san) · Gia (nghin) · ±% · GTGD (ty)."""
    h = [f'<div class="gn-note" style="font-weight:600;color:{color};margin-bottom:4px">{title}</div>',
         '<table class="gn-tbl"><thead><tr><th>Mã</th><th>Giá</th><th>±%</th><th>GTGD (tỷ)</th></tr></thead><tbody>']
    for sym, r in x.iterrows():
        p = r.get("change_pct")
        k = "up" if pd.notna(p) and p > 0 else ("down" if pd.notna(p) and p < 0 else "")
        h.append(f'<tr><td><b class="{k}">{sym}</b><small>{r.get("exchange", "")}</small></td><td class="{k}">{ui.fmt_vn(r.get("price") / 1000.0 if pd.notna(r.get("price")) else None, 2)}</td>'
                 f'<td class="{k}">{ui.fmt_vn(p, 2, dau=True)}%</td><td>{ui.fmt_vn(r.get("total_val"), 1)}</td></tr>')
    h.append("</tbody></table>")
    return "".join(h)


# ------------------------------------------------------------------ KPI STRIP
def kpi_strip(k: dict, now, day: str, live: bool):
    items = []
    for code in ("VNINDEX", "VN30", "HNX", "UPCOM"):
        r = k["idx"].get(code)
        if r is None:
            items.append((rt.TEN_IDX[code], "—", "", ""))
            continue
        d, sg = _delta(r["change"], r["pct"])
        items.append((rt.TEN_IDX[code], ui.fmt_vn(r["value"], 2), d, "up" if sg > 0 else ("down" if sg < 0 else "")))
    if k["f1m"] is not None:
        b = k["basis"]
        bs = f"basis {ui.fmt_vn(b, 2, dau=True)}" if b is not None and pd.notna(b) else "basis —"
        items.append(("VN30F1M", ui.fmt_vn(k["f1m"], 1), bs, "up" if (b or 0) > 0 else ("down" if (b or 0) < 0 else "")))
    else:
        items.append(("VN30F1M", "—", "chưa có tick", ""))
    vni = k["idx"].get("VNINDEX") or {}
    items.append(("GTGD toàn TT (tỷ)", ui.fmt_vn(k["gtgd"], 0), f"HOSE {ui.fmt_vn(vni.get('total_val'), 0)} tỷ", ""))
    items.append(("Tăng / giảm / đứng", f'<span style="color:#12965a">{k["adv"]}</span> / <span style="color:#e23b3b">{k["dec"]}</span> / {k["unch"]}',
                  f"trần {k['ceil']} · sàn {k['floor']}", ""))
    ts = k["ts"]
    if ts is not None:
        lag = (now - ts.to_pydatetime()).total_seconds()
        if live:
            items.append(("Cập nhật", f"{ts:%H:%M:%S}", f"trễ {lag:,.0f} s" if lag < 3600 else f"trễ {lag / 60:,.0f} phút",
                          "warn" if lag > 30 else ""))
        else:
            items.append(("Phiên gần nhất", f"{pd.Timestamp(day):%d/%m}", f"lúc {ts:%H:%M:%S} · bộ thu không chạy", "warn"))
    st.markdown(_kpi_html(items), unsafe_allow_html=True)


# ------------------------------------------------------------------ TRANG
def live(ctx):
    now = rt.now_vn()
    day = rt.latest_day()
    c1, c2, c3 = st.columns([1.6, 3.2, 2.2])
    with c1:
        if "live_freq" not in st.session_state:          # ?lam-moi=5|15|60|tat dat tan suat ban dau
            q = str(st.query_params.get("lam-moi") or "").lower().strip()
            st.session_state["live_freq"] = {"5": "5 s", "15": "15 s", "60": "60 s", "tat": "Tắt", "0": "Tắt"}.get(q, "5 s")
        f = st.segmented_control("Làm mới", list(FREQ), key="live_freq", label_visibility="collapsed")
        f = f if f in FREQ else "5 s"
    with c2:
        tt = rt.trang_thai_phien(now)
        running = rt.collector_running()
        dot = "#12965a" if running else "#e23b3b"
        st.markdown(f'<div class="gn-note" style="margin-top:8px"><span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
                    f'background:{dot};margin-right:6px"></span>{tt} · bộ thu DNSE {"đang chạy" if running else "không chạy"} · '
                    f'làm mới mỗi {f if FREQ[f] else "— (tắt)"}</div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="gn-note" style="text-align:right;margin-top:8px">Giờ VN {now:%H:%M:%S} · dữ liệu <code>{rt.DATA}</code></div>',
                    unsafe_allow_html=True)
    if day is None:
        ui.card_empty("Live", "", "Chưa có thư mục dữ liệu real-time nào trong realtime-lab\\data\\ — bật bộ thu DNSE (cuối trang).", key="live_none")
        _collector_card()
        return

    @st.fragment(run_every=FREQ[f])
    def _body():
        _render(day)

    _body()


def _render(day: str):
    now = rt.now_vn()
    d = rt.load_day(day)
    k = rt.kpi(d)
    live_now = (day == now.strftime("%Y-%m-%d")) and rt.in_session(now)
    if st.session_state.pop("_live_err", None):
        pass                                   # loi doc 1 file -> da dung ban cu, khong lam on trang
    if not live_now:
        ui.callout(f"Phiên gần nhất <b>{pd.Timestamp(day):%d/%m/%Y}</b>, bộ thu không chạy (ngoài giờ 08:45–15:10 T2–T6 "
                   f"hoặc chưa bật). Số liệu dưới đây là trạng thái cuối cùng đã ghi.")
    if not k["idx"]:
        ui.card_empty("Chỉ số", "", f"Thư mục {day} chưa có index_latest.parquet có dữ liệu.", key="live_kpi_none")
    else:
        kpi_strip(k, now, day, live_now)

    ui.h2("Chỉ số")
    # ---- Dien bien trong phien
    idx_opts = [i for i in ("VNINDEX", "VN30", "HNX", "UPCOM", "HNX30", "VN100") if i in k["idx"]] or ["VNINDEX"]
    with ui.card("Diễn biến trong phiên", "điểm · GTGD luỹ kế (tỷ) trục phải", key="live_dien_bien", controls=False,
                 help="Đường: giá trị chỉ số mỗi 5 giây (market_summary). Nến: nến 1 phút (index_1m). Nét đứt = tham chiếu (prior).",
                 chips=idx_opts, chip_default="VNINDEX", chip_fmt=rt.TEN_IDX.get, toggles={"Kiểu": ["Đường", "Nến"]}) as c:
        idx = c.chip
        r = k["idx"].get(idx, {})
        sub = ui.delta_html(r.get("value"), r.get("prior"), 2, "điểm") if r else ""
        if sub:
            c.markdown(f'<div class="gn-title" style="margin-top:-6px">{sub}<span class="unit">· cao {ui.fmt_vn(r.get("high"), 2)} · '
                       f'thấp {ui.fmt_vn(r.get("low"), 2)}</span></div>')
        if c.toggle["Kiểu"] == "Nến":
            o = rt.bars(d, idx, "index_1m")
            fig = ui.fig_candle(o, mode="Nến", name=rt.TEN_IDX.get(idx, idx))
            if fig is not None:
                if r.get("prior") is not None and pd.notna(r.get("prior")):
                    ui.add_hline(fig, float(r["prior"]), color=ui.TOK["gray"])
            _show(c, fig, o.rename(columns={"open": "Mở", "high": "Cao", "low": "Thấp", "close": "Đóng", "volume": "KL"}),
                  ten=f"{idx} nen 1 phut", height=H + 40, lunch=True, note="Nến 1 phút từ DNSE (ohlc), có backfill REST đầu phiên.")
        else:
            s = rt.series_5s(d, idx)
            if s.empty:
                c.empty("Chưa có lịch sử 5 s cho chỉ số này")
            else:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=s.index, y=s["value"], name=rt.TEN_IDX.get(idx, idx), mode="lines",
                                         line=dict(color=ui.TOK["orange"], width=2), hovertemplate="%{y:,.2f}<extra>điểm</extra>"))
                if "total_val" in s:
                    fig.add_trace(go.Scatter(x=s.index, y=s["total_val"], name="GTGD luỹ kế", mode="lines", yaxis="y2",
                                             line=dict(color=ui.TOK["tan"], width=1.3), fill="tozeroy", fillcolor="rgba(201,149,106,0.12)",
                                             hovertemplate="%{y:,.0f} tỷ<extra>GTGD</extra>"))
                if r.get("prior") is not None and pd.notna(r.get("prior")):
                    ui.add_hline(fig, float(r["prior"]), text=f"TC {ui.fmt_vn(r['prior'], 2)}", color=ui.TOK["gray"])
                ui.add_last_price(fig, s["value"], 2)
                fig.update_layout(height=H + 40, yaxis=dict(title=None),
                                  yaxis2=dict(overlaying="y", side="right", showgrid=False, rangemode="tozero",
                                              tickfont=dict(size=11, color=ui.TOK["ink3"])))
                _show(c, fig, s.rename(columns={"value": "Điểm", "total_val": "GTGD luỹ kế (tỷ)"}), ten=f"{idx} 5 giay",
                      note=f"{len(s):,} điểm 5 giây · từ {s.index.min():%H:%M:%S} đến {s.index.max():%H:%M:%S}".replace(",", "."))

    # ---- Do rong trong phien
    with ui.card("Độ rộng trong phiên", "số mã tăng / giảm / đứng giá · % tăng trục phải", key="live_do_rong", controls=False,
                 help="Số mã tăng/giảm/đứng của rổ chỉ số theo thời gian (5 s). Đường = % mã tăng trên tổng.",
                 chips=idx_opts, chip_default="VNINDEX", chip_fmt=rt.TEN_IDX.get) as c:
        b = rt.breadth_5s(d, c.chip)
        if b.empty:
            c.empty()
        else:
            fig = ui.fig_stack(b[["Tăng", "Giảm", "Đứng giá"]], "số mã", area=True, height=H,
                               colors={"Tăng": ui.TOK["up_soft"], "Giảm": ui.TOK["down_soft"], "Đứng giá": "#e6e2de"})
            fig.add_trace(go.Scatter(x=b.index, y=b["% tăng"], name="% tăng", mode="lines", yaxis="y2",
                                     line=dict(color=ui.TOK["brown"], width=1.8), hovertemplate="%{y:,.1f}%<extra>% tăng</extra>"))
            fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, range=[0, 100], ticksuffix="%",
                                          tickfont=dict(size=11, color=ui.TOK["ink3"])))
            last = b.iloc[-1]
            _show(c, fig, b, ten=f"Do rong {c.chip}",
                  note=f"Hiện tại: tăng {int(last['Tăng'])} · giảm {int(last['Giảm'])} · đứng {int(last['Đứng giá'])} · % tăng {ui.fmt_vn(last['% tăng'], 1)}%")

    # ---- GTGD luy ke so voi binh quan
    with ui.card("GTGD luỹ kế so với bình quân", "tỷ đồng · toàn thị trường (HOSE + HNX + UPCoM)", key="live_gtgd", controls=False,
                 help="GTGD luỹ kế hôm nay theo thời gian so với đường bình quân tối đa 20 phiên trước tại cùng mốc giờ "
                      "(chỉ các phiên có market_summary trong data\\<ngày>\\).") as c:
        g = rt.gtgd_toan_tt_5s(d)
        if g.empty:
            c.empty()
        else:
            prev = tuple(x for x in rt.days() if x < day)
            avg = rt.avg_curve(prev)
            df = g.to_frame()
            note = f"GTGD luỹ kế {ui.fmt_vn(float(g.iloc[-1]), 0)} tỷ lúc {g.index[-1]:%H:%M:%S}"
            if not avg.empty:
                a = avg.copy()
                a.index = pd.Timestamp(day) + a.index
                df = df.join(a, how="outer")
                at = a.reindex([g.index[-1].floor("1min")]).dropna()
                if len(at):
                    note += f" · {avg.name} cùng giờ {ui.fmt_vn(float(at.iloc[0]), 0)} tỷ ({ui.fmt_vn((float(g.iloc[-1]) / float(at.iloc[0]) - 1) * 100, 0, dau=True)}%)"
            else:
                note += " · chưa có phiên trước nào để tính bình quân (bộ thu mới chạy)"
            fig = ui.fig_line(df, "tỷ đồng", zero=True, hover_nd=0, height=H,
                              colors={g.name: ui.TOK["orange"], **({avg.name: ui.TOK["gray"]} if not avg.empty else {})},
                              dash={avg.name: "dash"} if not avg.empty else None)
            _show(c, fig, df, ten="GTGD luy ke", note=note)

    ui.h2("Dòng tiền & cổ phiếu")
    # ---- Toan san trong phien (stocks_latest)
    with ui.card("Toàn sàn trong phiên", "số mã · top 10 tăng/giảm % (GTGD ≥ 0,5 tỷ) · top 10 GTGD", key="live_toan_san", controls=False,
                 help="stocks_latest (~1.500 mã, 5 s): số mã tăng/giảm/đứng so tham chiếu và số mã kịch trần/sàn theo sàn, "
                      "đối chiếu với advances/declines/ceiling/floor của market_index (cột 'Chỉ số'). Giá nghìn đồng.") as c:
        sc = rt.market_scan(d)
        if not sc:
            c.empty("Chưa có stocks_latest.parquet")
        else:
            c.markdown(_html_board(sc["summary"]))
            a, b2, c3 = st.columns(3)
            with a:
                st.markdown(_html_top(sc["top_up"], "Top tăng %", "#12965a"), unsafe_allow_html=True)
            with b2:
                st.markdown(_html_top(sc["top_dn"], "Top giảm %", "#e23b3b"), unsafe_allow_html=True)
            with c3:
                st.markdown(_html_top(sc["top_val"], "Top GTGD", ui.TOK["brown"]), unsafe_allow_html=True)
            c.export(sc["summary"], "Toan san trong phien")
            with c._foot:  # noqa: SLF001
                ts = sc["ts"]
                st.markdown(f'<div class="gn-note">{sc["n_price"]} mã có giá khớp · {sc["n_dnse"]} mã tick DNSE 5 s, còn lại snapshot SSI 60 s'
                            f'{f" · cập nhật {ts:%H:%M:%S}" if pd.notna(ts) else ""} · "Có giá" đếm mã đã khớp nên có thể lệch "Chỉ số" '
                            f'(rổ chỉ số không gồm mã mới niêm yết/ETF, còn chỉ số đếm cả mã chưa khớp là đứng giá)</div>', unsafe_allow_html=True)

    # ---- Khoi ngoai trong phien (toan san)
    with ui.card("Khối ngoại trong phiên", "tỷ đồng · toàn sàn (stocks_latest)", key="live_kn", controls=False,
                 help="Ròng = Σ(mua − bán) khối ngoại theo mã từ stocks_latest: VN30 theo kênh foreign DNSE (5 s), mã khác theo "
                      "snapshot SSI iBoard (60 s). Đường ròng chỉ tích luỹ từ lúc mở trang (file không lưu lịch sử khối ngoại).") as c:
        fa = rt.foreign_all(d)
        if fa is None:
            fr = rt.foreign_table(d)
            if fr.empty:
                c.empty("Chưa có dữ liệu khối ngoại")
                fa = None
            else:                                   # fallback: chi VN30 (rt_latest + foreign_latest)
                net_s = fr["Ròng (tỷ)"]
                fa = {"net": float(net_s.sum()), "mua": float(fr["Mua (tỷ)"].sum()), "ban": float(fr["Bán (tỷ)"].sum()), "n": len(fr),
                      "by_ex": pd.DataFrame(), "top_mua": net_s[net_s > 0].head(10), "top_ban": net_s[net_s < 0].tail(10),
                      "table": fr.rename(columns={"Ròng (tỷ)": "KN ròng (tỷ)"}), "ts": None, "n_dnse": len(fr)}
        if fa:
            net, mua, ban = fa["net"], fa["mua"], fa["ban"]
            hist = st.session_state.setdefault("_live_fr_hist", [])
            ts = rt.ts_max(d) or pd.Timestamp(now)
            if not hist or hist[-1][0] != ts:
                hist.append((ts, net))
                del hist[:-2000]
            ex_txt = " · ".join(f'{rt.EXCH_TEN.get(ex, ex)} <span class="{"delta-up" if v >= 0 else "delta-down"}">{ui.fmt_vn(v, 0, dau=True)}</span>'
                                for ex, v in fa["by_ex"]["rong"].items()) if len(fa["by_ex"]) else ""
            c.markdown(f'<div class="gn-title" style="margin-top:-6px"><span class="unit">Ròng toàn TT</span>'
                       f'<span class="{"delta-up" if net >= 0 else "delta-down"}">{ui.fmt_vn(net, 1, dau=True)} tỷ</span>'
                       f'<span class="unit">· mua {ui.fmt_vn(mua, 0)} · bán {ui.fmt_vn(ban, 0)} · {fa["n"]} mã có GD khối ngoại'
                       f'{" · " + ex_txt if ex_txt else ""}</span></div>')
            a, b2 = st.columns([1.3, 1])
            top = pd.concat([fa["top_mua"], fa["top_ban"]]).sort_values(ascending=False)
            with a:
                fig = ui.fig_hbar(top, "tỷ đồng", sign=True, nd=1, height=max(260, 24 * len(top) + 50))
                if fig is not None:
                    st.plotly_chart(fig, width="stretch", config=ui.PLOTLY_CONFIG, key="fig_live_kn_top")
            with b2:
                if len(hist) > 1:
                    hs = pd.Series({t: v for t, v in hist}).sort_index()
                    fl = ui.fig_line(hs.to_frame("Ròng luỹ kế"), "tỷ đồng", hover_nd=1, height=max(260, 24 * len(top) + 50),
                                     colors={"Ròng luỹ kế": ui.TOK["brown"]})
                    fl.update_xaxes(tickformat="%H:%M", hoverformat="%H:%M:%S")
                    st.plotly_chart(fl, width="stretch", config=ui.PLOTLY_CONFIG, key="fig_live_kn_line")
                else:
                    st.markdown('<div class="gn-empty" style="height:260px">Đường ròng luỹ kế sẽ hiện sau vài lần làm mới</div>',
                                unsafe_allow_html=True)
            with st.expander(f"Bảng khối ngoại theo mã ({fa['n']} mã)"):
                st.markdown(_html_board(fa["table"]), unsafe_allow_html=True)
            c.export(fa["table"], "Khoi ngoai theo ma")
            with c._foot:  # noqa: SLF001
                st.markdown(f'<div class="gn-note">{fa["n_dnse"]} mã khối ngoại DNSE 5 s, còn lại SSI 60 s · tự doanh không live</div>',
                            unsafe_allow_html=True)

    # ---- Anh huong len chi so
    inf_idx = rt.influence_indices(d)
    with ui.card("Ảnh hưởng lên chỉ số", "điểm · top 10 kéo lên / kéo xuống", key="live_inf", controls=False,
                 help="influence (điểm đóng góp vào thay đổi chỉ số) từ kênh market_index_influence của DNSE.",
                 chips=inf_idx, chip_default="VNINDEX", chip_fmt=rt.TEN_IDX.get) as c:
        up, dn, ts = rt.influence(d, c.chip)
        if up.empty and dn.empty:
            c.empty()
        else:
            a, b2 = st.columns(2)
            with a:
                st.markdown('<div class="gn-note" style="font-weight:600;color:#12965a">Kéo lên</div>', unsafe_allow_html=True)
                fu = ui.fig_hbar(up, "điểm", sign=True, nd=2, height=300)
                if fu is not None:
                    st.plotly_chart(fu, width="stretch", config=ui.PLOTLY_CONFIG, key="fig_live_inf_up")
                else:
                    st.markdown('<div class="gn-empty" style="height:300px">Không có mã kéo lên</div>', unsafe_allow_html=True)
            with b2:
                st.markdown('<div class="gn-note" style="font-weight:600;color:#e23b3b">Kéo xuống</div>', unsafe_allow_html=True)
                fd = ui.fig_hbar(dn.sort_values(), "điểm", sign=True, nd=2, height=300)
                if fd is not None:
                    st.plotly_chart(fd, width="stretch", config=ui.PLOTLY_CONFIG, key="fig_live_inf_dn")
                else:
                    st.markdown('<div class="gn-empty" style="height:300px">Không có mã kéo xuống</div>', unsafe_allow_html=True)
            both = pd.concat([up, dn]).rename("Ảnh hưởng (điểm)").to_frame()
            both.index.name = "Mã"
            c.export(both, f"Anh huong {c.chip}")
            if ts is not None:
                with c._foot:  # noqa: SLF001
                    st.markdown(f'<div class="gn-note">Cập nhật influence lúc {ts:%H:%M:%S} · tổng kéo lên '
                                f'{ui.fmt_vn(float(up.sum()), 2, dau=True)} · kéo xuống {ui.fmt_vn(float(dn.sum()), 2, dau=True)}</div>',
                                unsafe_allow_html=True)

    # ---- Bang gia toan san (stocks_latest)
    BASKETS = ["VN30", "HOSE", "HNX", "UPCOM", "Tất cả"]
    with ui.card("Bảng giá toàn sàn", "giá nghìn đồng · KL cổ phiếu · GTGD / KN ròng tỷ", key="live_bang", controls=False,
                 help="stocks_latest (~1.500 mã, 5 s): giá khớp, ±% so tham chiếu, trần/sàn/TC, KL & GTGD luỹ kế, khối ngoại mua ròng. "
                      "Nguồn ● 5 s = tick DNSE, ○ 1 phút = snapshot SSI iBoard. Bid/Ask 1 chỉ có cho mã theo dõi (VN30, rt_latest). "
                      "Giá tím = kịch trần, xanh ngọc = kịch sàn.",
                 chips=BASKETS, chip_default="VN30", chip_label="Rổ", toggles={"Sắp theo": ["±%", "GTGD", "KL"]}) as c:
        k1, k2 = st.columns([1.4, 4])
        q = k1.text_input("Tìm mã", key="live_bang_q", placeholder="Tìm mã…", label_visibility="collapsed")
        t = rt.board_all(d, c.chip, q, c.toggle["Sắp theo"])
        if t.empty:
            msg = "Chưa có stocks_latest.parquet (bộ thu chưa chạy bản toàn sàn)" if rt._stocks_day(d).empty else f"Không có mã nào khớp '{q}' trong rổ {c.chip}"
            c.empty(msg)
        else:
            n_gia, n_dnse = int(t["Giá"].notna().sum()), int((t["Nguồn"] == "● 5 s").sum())
            with k2:
                st.markdown(f'<div class="gn-note" style="margin-top:8px">{len(t)} mã · {n_gia} mã có giá · {n_dnse} mã tick DNSE 5 s · '
                            f'sắp theo {c.toggle["Sắp theo"]} giảm dần</div>', unsafe_allow_html=True)
            c.markdown(_html_board(t, max_h=640))
            exp = t.drop(columns=["_ex"]).assign(**{"Sàn GD": t["_ex"]})
            c.export(exp, f"Bang gia {c.chip}")
            with c._foot:  # noqa: SLF001
                st.markdown('<div class="gn-note">KL = số cổ phiếu (DNSE phát /10, bộ thu đã nhân 10 lúc parse từ 09/10/2026) · '
                            'GTGD tỷ đồng · KN ròng = mua − bán khối ngoại (VN30 DNSE 5 s, mã khác SSI 60 s) · phái sinh xem KPI + nến 1 phút</div>',
                            unsafe_allow_html=True)

    # ---- Nen 1 phut tung ma
    syms = rt.bar_symbols(d, "rt_bars_1m")
    futs = [s for s in rt.bar_symbols(d, "index_1m") if s.startswith("VN30F")]
    with ui.card("Nến 1 phút từng mã", "giá nghìn đồng · KL cổ phiếu · chỉ VN30 + phái sinh", key="live_nen_ma", controls=False,
                 help="rt_bars_1m (kênh ohlc.1 DNSE, chỉ các mã theo dõi trong dnse_symbols.txt = VN30) + index_1m (VN30F1M/F2M). "
                      "Mã ngoài VN30 không có nến 1 phút (chỉ tick_extra).") as c:
        allsym = syms + futs
        if not allsym:
            c.empty()
        else:
            k1, _ = st.columns([1.2, 4])
            if "live_ma" not in st.session_state or st.session_state["live_ma"] not in allsym:
                st.session_state["live_ma"] = "FPT" if "FPT" in allsym else allsym[0]
            sym = k1.selectbox("Mã", allsym, key="live_ma")
            o = rt.bars(d, sym, "index_1m" if sym.startswith("VN30F") else "rt_bars_1m")
            fig = ui.fig_candle(o, mode="Nến", name=sym)
            if fig is not None and len(o):
                ui.add_last_price(fig, o.close, 2)
            _show(c, fig, o.rename(columns={"open": "Mở", "high": "Cao", "low": "Thấp", "close": "Đóng", "volume": "KL"}),
                  ten=f"{sym} nen 1 phut", height=H + 40, lunch=True,
                  note=(f"{len(o)} nến · đóng {ui.fmt_vn(float(o.close.iloc[-1]), 2)} · KL {ui.fmt_vn(float(o.volume.sum()), 0)} · chỉ VN30 + phái sinh" if len(o) else None))

    ui.h2("Bộ thu")
    _collector_card()


def _collector_card():
    with ui.card("Trạng thái bộ thu DNSE", "realtime-lab\\dnse_stream.py · task 'Realtime DNSE' 08:45–15:10 T2–T6", key="live_collector",
                 controls=False) as c:
        pids = rt.collector_pids()
        p, lines = rt.log_tail(5)
        a, b = st.columns([1, 3])
        with a:
            dot = "#12965a" if pids else "#e23b3b"
            st.markdown(f'<div class="gn-kpi"><div class="l">Tiến trình</div><div class="v" style="font-size:16px">'
                        f'<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:{dot};margin-right:6px"></span>'
                        f'{"Đang chạy" if pids else "Không chạy"}</div><div class="d">{"PID " + ", ".join(map(str, pids)) if pids else "—"}</div></div>',
                        unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            if c1.button("▶ Bật bộ thu", key="live_start", width="stretch", disabled=bool(pids)):
                st.session_state["_live_msg"] = rt.start_collector()
            if c2.button("■ Tắt", key="live_stop", width="stretch", disabled=not pids):
                st.session_state["_live_msg"] = rt.stop_collector()
            msg = st.session_state.pop("_live_msg", None)
            if msg:
                st.caption(msg)
        with b:
            if p:
                st.markdown(f'<div class="gn-note">Log mới nhất: <code>{p}</code></div>', unsafe_allow_html=True)
                st.code("\n".join(lines) if lines else "(log trống)", language=None)
            else:
                st.markdown('<div class="gn-note">Chưa có file log trong realtime-lab\\logs\\.</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------ DONG KPI NHO CHO TONG QUAN
def mini_strip():
    """1 dong KPI live (neu co du lieu hom nay) + link sang trang Live. Goi o dau Tong quan."""
    try:
        k = rt.snapshot_today()
    except Exception:  # noqa: BLE001
        return
    if not k:
        return
    now = rt.now_vn()
    live_now = rt.in_session(now) and rt.collector_running()
    parts = []
    for code in ("VNINDEX", "VN30", "HNX", "UPCOM"):
        r = k["idx"].get(code)
        if not r or pd.isna(r.get("value")):
            continue
        ch = r.get("change") or 0
        cls = "up" if ch > 0 else ("down" if ch < 0 else "")
        parts.append(f'<b>{rt.TEN_IDX[code]}</b> {ui.fmt_vn(r["value"], 2)} <span class="{cls}">{ui.fmt_vn(r.get("pct"), 2, dau=True)}%</span>')
    parts.append(f'GTGD {ui.fmt_vn(k["gtgd"], 0)} tỷ')
    parts.append(f'<span class="up">{k["adv"]}</span>/<span class="down">{k["dec"]}</span>/{k["unch"]}')
    if k["f1m"] is not None:
        parts.append(f'F1M {ui.fmt_vn(k["f1m"], 1)}' + (f' (basis {ui.fmt_vn(k["basis"], 1, dau=True)})' if k["basis"] is not None else ""))
    ts = k["ts"]
    tag = (f'<span style="color:#12965a;font-weight:600">● LIVE</span>' if live_now
           else f'<span style="color:#8c8c8c;font-weight:600">○ Phiên {pd.Timestamp(k["day"]):%d/%m}</span>')
    lag = k.get("lag")
    lag_txt = f' · trễ {lag:,.0f} s' if live_now and lag is not None else ""
    st.markdown(
        '<div class="gn-callout" style="display:flex;gap:14px;flex-wrap:wrap;align-items:center;font-size:13px">'
        f'{tag}<span>{" · ".join(parts)}</span>'
        f'<span style="color:#8c8c8c">{ts:%H:%M:%S}{lag_txt}</span>'
        '<a href="?trang=live" target="_self" style="margin-left:auto;color:#b3551c;font-weight:600;text-decoration:none">Mở trang Live →</a>'
        '</div>'.replace("<span class=\"up\">", '<span style="color:#12965a;font-weight:600">').replace("<span class=\"down\">", '<span style="color:#e23b3b;font-weight:600">'),
        unsafe_allow_html=True)
