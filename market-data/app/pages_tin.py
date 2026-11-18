# -*- coding: utf-8 -*-
r"""
pages_tin.py - Tin tuc › TIN THEO NGANH (11/11/2026): tin RSS 11 bao kinh te (news-rss\fetch_rss.py) da phan loai theo
23 nganh (19 ICB Vietcap cap 2 nhu ca app + Vingroup + Vi mo / TTCK / The gioi). Chon nganh -> tin tu loc va SAP XEP
(moi nhat / lien quan nhat / dang chu y). Deep-link: ?trang=tin-tuc/tin-nganh&nganh=Ngân hàng
"""
from __future__ import annotations

import html
import os
import sys
import threading
import time

import pandas as pd
import streamlit as st

import datalib as dl
import ui_genea as ui

TAT_CA = "Tất cả ngành"
KHAC = "Chưa phân loại"
SAP = {"Mới nhất": "moi", "Liên quan nhất": "lienquan", "Đáng chú ý": "chuy"}
COLS = ["id", "ngay_gio", "nguon", "chuyen_muc", "tieu_de", "tom_tat", "url", "nganh_chinh", "nganh", "chu_de", "ma", "loai_tin",
        "diem", "diem_chu_y", "tu_khoa", "nhom_trung", "so_nguon"]
NGUON_MAU = {"CafeF": "#b3551c", "Vietstock": "#1f6fb2", "VnEconomy": "#0f7b6c", "VnExpress": "#9b1c31", "Dân trí": "#2e7d32",
             "VietnamNet": "#c62828", "Tuổi Trẻ": "#1565c0", "Thanh Niên": "#00695c", "VietnamBiz": "#6a1b9a",
             "Nhịp sống kinh doanh": "#ef6c00", "VietnamPlus": "#37474f"}


# 11/11/2026 (PV2): KHONG co kho dung san / lich chay rieng. Mo trang -> neu kho trong cache app cu hon TTL thi keo RSS ngay
# (57 feed song song ~2 s + phan loai bai moi ~1 s), gop don vao kho cache (lich su = cac lan mo app, xoa bai > KEEP_DAYS ngay);
# doi tu dien (config\keywords.csv...) -> fetch_rss tu phan loai lai toan bo; cache_resource theo mtime file -> tu nap lai.
NEWS_CODE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "news-rss")   # <market-data>/news-rss (code)
NEWS_DATA = os.path.join(dl.CACHE, "news-rss")
TTL_PHUT = 15
KEEP_DAYS = 90
_LOCK = threading.Lock()


def _paths():
    d = NEWS_DATA
    return (os.path.join(d, "news_tagged.parquet"), os.path.join(d, "news_tags.parquet"), os.path.join(d, "feed_status.csv"),
            os.path.join(d, "nganh.csv"))


def _fetcher():
    if NEWS_CODE not in sys.path:
        sys.path.insert(0, NEWS_CODE)
    import fetch_rss
    import newslib
    newslib.set_data_dir(NEWS_DATA)
    return fetch_rss


def _lam_moi(force: bool = False) -> str:
    """Keo RSS neu kho cu hon TTL (hoac force). Chi 1 phien keo 1 luc; phien khac dung kho hien co. Tra thong bao loi ('' = ok)."""
    p = _paths()[0]
    tuoi = (time.time() - os.path.getmtime(p)) / 60 if os.path.exists(p) else 1e9
    if not force and tuoi < TTL_PHUT:
        return ""
    if not _LOCK.acquire(blocking=not os.path.exists(p)):           # chua co kho -> doi phien dang keo; co kho -> dung tam kho cu
        return ""
    try:
        if not force and os.path.exists(p) and (time.time() - os.path.getmtime(p)) / 60 < TTL_PHUT:
            return ""                                                # phien khac vua keo xong
        with st.spinner("Đang kéo tin RSS mới (57 chuyên mục, 11 báo) ..."):
            _fetcher().run(fetch=True, keep_days=KEEP_DAYS)
        return ""
    except Exception as e:  # noqa: BLE001 - mat mang / nguon loi: dung kho cu
        return f"{type(e).__name__}: {str(e)[:160]}"
    finally:
        _LOCK.release()


@st.cache_resource(show_spinner="Đang nạp tin RSS ...", max_entries=1)
def _news(mt: float):
    """(tin, tag nganh dai, thu tu nganh). Chi 400 ngay gan nhat (RAM cloud); nguoi goi KHONG sua tai cho."""
    p, pt, _, pn = _paths()
    t = pd.read_parquet(p)
    t = t[[c for c in COLS if c in t.columns]]
    t = t[t["ngay_gio"] >= t["ngay_gio"].max() - pd.Timedelta(days=400)].reset_index(drop=True)
    for c in ("nguon", "chuyen_muc", "nganh_chinh"):
        t[c] = t[c].astype("category")
    for c in ("nganh", "chu_de", "ma", "loai_tin", "tu_khoa"):
        t[c] = t[c].fillna("")
    g = pd.read_parquet(pt) if os.path.exists(pt) else pd.DataFrame(columns=["id", "nganh", "diem", "chinh", "chu_de", "tu_khoa"])
    g = g[g["id"].isin(set(t["id"]))].reset_index(drop=True)
    g["nganh"] = g["nganh"].astype("category")
    g = g.merge(t[["id", "ngay_gio"]], on="id", how="left")
    order = []
    if os.path.exists(pn):
        n = pd.read_csv(pn, dtype=str)
        order = list(n.sort_values("thu_tu", key=lambda s: s.astype(int))["nganh"])
    order += sorted(set(g["nganh"].astype(str)) - set(order))
    return t, g, order


def _badge(nguon: str) -> str:
    c = NGUON_MAU.get(str(nguon), "#595959")
    return (f'<span style="display:inline-block;padding:1px 7px;border-radius:999px;font-size:11px;font-weight:600;'
            f'background:{c}14;color:{c};line-height:16px;white-space:nowrap">{html.escape(str(nguon))}</span>')


def _chip(x: str, strong=False) -> str:
    bg, fg = ("var(--accent-wash)", "var(--accent-text)") if strong else ("var(--surface-2)", "var(--ink-2)")
    return (f'<span style="display:inline-block;padding:0 6px;margin:1px 2px 1px 0;border-radius:4px;font-size:11px;'
            f'background:{bg};color:{fg};white-space:nowrap">{html.escape(x)}</span>')


def _ngay(ts: pd.Timestamp, today: pd.Timestamp) -> str:
    if ts >= today:
        return f'<b>{ts:%H:%M}</b><small>hôm nay</small>'
    if ts >= today - pd.Timedelta(days=1):
        return f'<b>{ts:%H:%M}</b><small>hôm qua</small>'
    return f'<b>{ts:%d/%m}</b><small>{ts:%H:%M} · {ts:%Y}</small>'


def _html(t: pd.DataFrame, nganh: str, limit: int = 300) -> str:
    today = pd.Timestamp.now().normalize()
    h = ['<div class="gn-tblwrap" style="max-height:720px;overflow:auto"><table class="gn-tbl"><thead><tr>'
         '<th>Giờ</th><th style="text-align:left">Tin</th><th style="text-align:left">Ngành · mã</th>'
         '<th title="điểm liên quan với ngành đang chọn (tiêu đề ×2, tóm tắt ×1, mã CK, chuyên mục RSS)">Điểm</th></tr></thead><tbody>']
    for r in t.head(limit).itertuples(index=False):
        td = html.escape(str(r.tieu_de))
        tt = html.escape(str(r.tom_tat)[:220]) + ("…" if len(str(r.tom_tat)) > 220 else "")
        kw = html.escape(str(getattr(r, "tu_khoa_ng", "") or r.tu_khoa))
        trung = f' <small style="display:inline;color:var(--ink-3)">· {int(r.so_nguon)} báo đưa tin</small>' if r.so_nguon > 1 else ""
        ngs = [x for x in str(r.nganh).split("|") if x]
        chips = "".join(_chip(x, strong=(x == nganh or (nganh == TAT_CA and x == r.nganh_chinh))) for x in ngs[:4]) or _chip(KHAC)
        ma = " ".join(f'<b style="font-size:11.5px">{m}</b>' for m in str(r.ma).split("|")[:6] if m)
        lt = "".join(_chip(x) for x in str(r.loai_tin).split("|")[:3] if x)
        diem = getattr(r, "diem_ng", r.diem)
        h.append(f'<tr><td style="vertical-align:top">{_ngay(r.ngay_gio, today)}</td>'
                 f'<td style="text-align:left;white-space:normal;min-width:340px;vertical-align:top">{_badge(r.nguon)} '
                 f'<a href="{html.escape(str(r.url))}" target="_blank" rel="noopener" style="color:var(--ink);font-weight:600;'
                 f'text-decoration:none">{td}</a>{trung}<small title="Từ khoá khớp: {kw}">{tt}</small>'
                 f'{("<div>" + lt + "</div>") if lt else ""}</td>'
                 f'<td style="text-align:left;white-space:normal;min-width:170px;vertical-align:top">{chips}<div>{ma}</div></td>'
                 f'<td style="vertical-align:top" title="{kw}">{ui.fmt_vn(diem, 1)}</td></tr>')
    h.append("</tbody></table></div>")
    if len(t) > limit:
        h.append(f'<div class="gn-note">Hiện {limit}/{len(t)} tin — tải Excel để lấy đủ.</div>')
    return "".join(h)


def _export(t: pd.DataFrame) -> pd.DataFrame:
    out = t.assign(diem_x=t.get("diem_ng", t["diem"]))[
        ["ngay_gio", "nguon", "chuyen_muc", "tieu_de", "url", "nganh_chinh", "nganh", "chu_de", "ma", "loai_tin", "diem_x", "diem_chu_y",
         "so_nguon", "tu_khoa", "tom_tat"]].copy()
    out.columns = ["Thời gian", "Báo", "Chuyên mục", "Tiêu đề", "Link", "Ngành chính", "Mọi ngành", "Chủ đề", "Mã CK", "Loại tin",
                   "Điểm liên quan", "Điểm chú ý", "Số báo đưa", "Từ khoá khớp", "Tóm tắt"]
    return out


def _split_count(s: pd.Series, sep="|") -> pd.Series:
    x = s[s.astype(str) != ""].astype(str).str.split(sep).explode().str.strip()
    return x[x != ""].value_counts()


def tin_nganh(ctx):
    h0, h1 = st.columns([5, 1])
    with h0:
        ui.h2("Tin tức theo ngành — RSS báo kinh tế")
    p, pt, pf, _ = _paths()
    loi = _lam_moi(force=h1.button("↻ Kéo tin mới", key="tn_lam_moi", help=f"Tự kéo lại khi mở trang nếu tin cũ hơn {TTL_PHUT} phút"))
    if not os.path.exists(p):
        ui.card_empty("Tin theo ngành", "", f"Chưa kéo được tin RSS ({loi or 'chưa có kho'}). Bấm <b>↻ Kéo tin mới</b> để thử lại.",
                      key="tin_rss_trong")
        return
    cap = pd.Timestamp(os.path.getmtime(p), unit="s", tz="UTC").tz_convert("Asia/Ho_Chi_Minh")
    ui.note(f"Kéo RSS lúc {cap:%H:%M %d/%m} · tự làm mới khi mở trang nếu cũ hơn {TTL_PHUT} phút · giữ tin {KEEP_DAYS} ngày trong cache app"
            + (f' · <span style="color:var(--down)">lần kéo vừa rồi lỗi, đang dùng tin cũ: {html.escape(loi)}</span>' if loi else ""))
    t, g, order = _news(max(dl._raw_mt(p), dl._raw_mt(pt)))
    if t.empty:
        ui.card_empty("Tin theo ngành", "", "File rỗng — chạy lại fetch_rss.py.", key="tin_rss_trong")
        return
    today = pd.Timestamp.now().normalize()
    last = t["ngay_gio"].max()

    # ---- KPI
    d1 = t[t["ngay_gio"] >= today]
    d7 = t[t["ngay_gio"] >= today - pd.Timedelta(days=7)]
    g1 = g[g["ngay_gio"] >= pd.Timestamp.now() - pd.Timedelta(hours=24)]
    top24 = g1["nganh"].astype(str).value_counts()
    top24 = top24[~top24.index.isin(["Vĩ mô & chính sách", "Thị trường chứng khoán", "Kinh tế thế giới"])]
    ui.kpi_strip([
        ("Tin hôm nay", f"{len(d1)}", f"{d1['nguon'].nunique()} báo · {d1['nhom_trung'].nunique()} tin khác nhau", 1 if len(d1) else 0),
        ("7 ngày", f"{len(d7):,}".replace(",", "."), f"{(d7['nganh_chinh'] != KHAC).mean() * 100:.0f}% đã gắn ngành" if len(d7) else "", 0),
        ("Ngành nóng 24h", top24.index[0] if len(top24) else "—", f"{int(top24.iloc[0])} tin" if len(top24) else "", 0),
        ("Tin mới nhất", f"{last:%H:%M}", f"{last:%d/%m/%Y}", 0),
    ])

    # ---- (a) TIN THEO NGANH
    cnt = g[g["ngay_gio"] >= today - pd.Timedelta(days=7)]["nganh"].astype(str).value_counts()
    opts = [TAT_CA] + order + [KHAC]
    if "tn_nganh" not in st.session_state:
        q = st.query_params.get("nganh")
        st.session_state["tn_nganh"] = q if q in opts else TAT_CA
    with ui.card("Tin theo ngành", "chọn ngành → tin tự lọc và sắp xếp",
                 help="Nguồn: 57 chuyên mục RSS của 11 báo (CafeF, Vietstock, VnEconomy, VnExpress, Dân trí, VietnamNet, Tuổi Trẻ, Thanh Niên, "
                      "VietnamBiz, Nhịp sống KD, VietnamPlus), kéo ngay khi mở trang (cache 15 phút, gộp dồn 90 ngày). Phân loại = từ điển ~1.100 từ khoá theo ngành "
                      "(news-rss\\config\\keywords.csv; tiêu đề ×2, tóm tắt ×1) + mã CK nhắc trong bài (mã 3 ký tự / tên DN → ngành ICB cấp 2 Vietcap "
                      "như trang Hiệu suất) + gợi ý chuyên mục RSS; gắn ngành khi điểm ≥ 3, 1 bài có thể thuộc nhiều ngành. "
                      "Sắp xếp: Mới nhất · Liên quan nhất (điểm với ngành đang chọn) · Đáng chú ý (loại tin KQKD/M&A/pháp lý/cổ tức… + có mã CK "
                      "+ nhiều báo cùng đưa). Số trong ngoặc = số tin 7 ngày.",
                 key="tin_nganh", periods=["1D", "3D", "1W", "1M", "3M", "All"], default="1W", end=today) as c:
        with c.body():
            f0, f1, f2, f3 = st.columns([1.7, 1.6, 1.3, 1.1])
            nganh = f0.selectbox("Ngành", opts, key="tn_nganh",
                                 format_func=lambda x: x if x == TAT_CA else f"{x} ({int(cnt.get(x, 0))})")
            gg = g[g["nganh"].astype(str) == nganh] if nganh not in (TAT_CA, KHAC) else None
            cd_opts = list(_split_count(gg["chu_de"]).index) if gg is not None else list(_split_count(t["chu_de"]).index[:40])
            chu_de = f1.multiselect("Chủ đề", cd_opts, default=[], key=f"tn_cd_{nganh}", placeholder="Tất cả chủ đề")
            loai = f2.multiselect("Loại tin", list(_split_count(t["loai_tin"]).index), default=[], key="tn_loai", placeholder="Tất cả")
            sap = f3.selectbox("Sắp xếp", list(SAP), key="tn_sap")
            e0, e1, e2, e3 = st.columns([1.7, 1.6, 1.3, 1.1])
            nguon = e0.multiselect("Báo", sorted(t["nguon"].astype(str).unique()), default=[], key="tn_nguon", placeholder="Tất cả báo")
            q = e1.text_input("Tìm trong tiêu đề / mã", "", key="tn_q", placeholder="vd: lãi suất, HPG, cao tốc").strip()
            chinh = e2.toggle("Chỉ khi là ngành chính", False, key="tn_chinh",
                              help="Bỏ tin ngành này chỉ được nhắc phụ (điểm thấp hơn ngành khác của bài)")
            gop = e3.toggle("Gộp tin trùng", True, key="tn_gop", help="Cùng tiêu đề ở nhiều báo → giữ 1 dòng (ghi 'n báo đưa tin')")
        st.query_params["nganh"] = nganh
        x = t[(t["ngay_gio"] >= pd.Timestamp(c.d0)) & (t["ngay_gio"] < pd.Timestamp(c.d1) + pd.Timedelta(days=1))]
        if nganh == KHAC:
            x = x[x["nganh_chinh"] == KHAC]
        elif gg is not None:
            gsel = gg[gg["chinh"]] if chinh else gg
            gsel = gsel[["id", "diem", "chu_de", "tu_khoa"]].rename(columns={"diem": "diem_ng", "chu_de": "chu_de_ng", "tu_khoa": "tu_khoa_ng"})
            x = x.merge(gsel, on="id", how="inner")
            if chu_de:
                x = x[x["chu_de_ng"].fillna("").str.split("|").map(lambda v: bool(set(v) & set(chu_de)))]
        elif chu_de:
            x = x[x["chu_de"].str.split("|").map(lambda v: bool(set(v) & set(chu_de)))]
        if loai:
            x = x[x["loai_tin"].str.split("|").map(lambda v: bool(set(v) & set(loai)))]
        if nguon:
            x = x[x["nguon"].astype(str).isin(nguon)]
        if q:
            ql = q.lower()
            x = x[x["tieu_de"].str.lower().str.contains(ql, regex=False) | x["ma"].str.contains(q.upper(), regex=False)
                  | x["tom_tat"].str.lower().str.contains(ql, regex=False)]
        k = SAP[sap]
        dcol = "diem_ng" if "diem_ng" in x else "diem"
        if k == "lienquan":
            x = x.sort_values([dcol, "ngay_gio"], ascending=False)
        elif k == "chuy":
            x = x.sort_values(["diem_chu_y", dcol, "ngay_gio"], ascending=False)
        else:
            x = x.sort_values("ngay_gio", ascending=False)
        if gop:
            x = x.drop_duplicates("nhom_trung", keep="first")
        if x.empty:
            c.empty("Không có tin trong khung / bộ lọc đã chọn")
        else:
            c.markdown(_html(x, nganh))
            c.export(_export(x), ten=f"Tin {nganh}")
            with c._foot:
                st.markdown(f'<div class="gn-note">{len(x)} tin · {x["nguon"].nunique()} báo · {c.d0:%d/%m/%Y} – {c.d1:%d/%m/%Y} · '
                            f'sắp: {sap.lower()} · tin mới nhất {last:%H:%M %d/%m}</div>', unsafe_allow_html=True)

    # ---- (b) NGANH DUOC NHAC NHIEU + (c) TU KHOA NOI BAT
    col1, col2 = st.columns(2)
    with col1:
        with ui.card("Ngành được nhắc nhiều", "số tin (bỏ trùng tiêu đề)",
                     help="Mỗi bài tính cho mọi ngành nó được gắn (điểm ≥ 3). Ngành đang chọn tô xám.",
                     key="tin_nganh_dem", periods=["1D", "3D", "1W", "1M"], default="1W", end=today, compact=True) as c2:
            gp = g[(g["ngay_gio"] >= pd.Timestamp(c2.d0)) & (g["ngay_gio"] < pd.Timestamp(c2.d1) + pd.Timedelta(days=1))]
            gp = gp.merge(t[["id", "nhom_trung"]], on="id").drop_duplicates(["nganh", "nhom_trung"])
            s = gp["nganh"].astype(str).value_counts().sort_values(ascending=False)
            if s.empty:
                c2.empty()
            else:
                c2.chart(ui.fig_hbar(s, "tin", sign=False, highlight=nganh, nd=0), s.rename("Số tin").to_frame(), ten="So tin theo nganh")
    with col2:
        sub = nganh if nganh not in (TAT_CA, KHAC) else None
        with ui.card("Từ khoá nổi bật" + (f" · {sub}" if sub else ""), "số tin có từ khoá / mã",
                     help="Từ khoá trong từ điển (và mã CK) khớp nhiều nhất ở các tin của ngành đang chọn trong khung thời gian. "
                          "Gợi ý từ khoá mới: chạy news-rss\\keyword_mining.py → output\\keyword_candidates.xlsx.",
                     key="tin_tu_khoa", periods=["1D", "3D", "1W", "1M"], default="1W", end=today, compact=True) as c3:
            gp = g[(g["ngay_gio"] >= pd.Timestamp(c3.d0)) & (g["ngay_gio"] < pd.Timestamp(c3.d1) + pd.Timedelta(days=1))]
            if sub:
                gp = gp[gp["nganh"].astype(str) == sub]
            s = _split_count(gp["tu_khoa"], sep="·").head(20)
            if s.empty:
                c3.empty()
            else:
                c3.chart(ui.fig_hbar(s, "tin", sign=False, nd=0), s.rename("Số tin").to_frame(), ten="Tu khoa noi bat")

    # ---- (d) TINH TRANG NGUON
    with ui.card("Nguồn RSS", "trạng thái lần kéo gần nhất", key="tin_nguon", controls=False) as c4:
        if os.path.exists(pf):
            fs = pd.read_csv(pf)
            per = t[t["ngay_gio"] >= today - pd.Timedelta(days=7)].groupby(["nguon", "chuyen_muc"], observed=True).size()
            fs["Tin 7 ngày"] = [int(per.get((a, b), 0)) for a, b in zip(fs["nguon"], fs["chuyen_muc"])]
            fs = fs.rename(columns={"nguon": "Báo", "chuyen_muc": "Chuyên mục", "so_tin": "Tin trong feed", "loi": "Lỗi", "luc": "Kéo lúc"})
            c4.table(fs[["Báo", "Chuyên mục", "Tin trong feed", "Tin 7 ngày", "Lỗi", "Kéo lúc"]].set_index("Báo"), ten="Nguon RSS")
        else:
            c4.empty()


# =====================================================================================================================
# 18/11/2026: Tin tuc › WATCHLIST - danh sach ma cho news-alert + tin khop + TOM TAT HOM NAY (Claude Sonnet).
# Canh bao chay ONLINE: GitHub Actions news-alert.yml 15 phut/lan gui email (+ email tom tat cuoi ngay); laptop them toast.
# watchlist.csv / config.json / lich su / tom tat dung chung qua Google Drive (gdrive:pipeline-data/market-data/news-alert):
# mo trang -> keo ve (60 s/lan), Luu -> day len. Chay duoc ca laptop lan Streamlit Cloud (rclone do cloud_boot cai).
# =====================================================================================================================
ALERT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "news-alert")   # <market-data>/news-alert
WL_SECRETS = ("ANTHROPIC_API_KEY", "NEWS_ALERT_SMTP_PASS")


def _alert():
    if ALERT_DIR not in sys.path:
        sys.path.insert(0, ALERT_DIR)
    for k in WL_SECRETS:                                   # Streamlit Cloud: secrets -> env (SDK Anthropic / SMTP doc env)
        if not os.environ.get(k):
            try:
                v = st.secrets.get(k)
                if v:
                    os.environ[k] = str(v)
            except Exception:  # noqa: BLE001 - khong co secrets.toml
                pass
    import importlib
    import news_alert
    import tom_tat
    # news-alert nam ngoai thu muc app -> Streamlit KHONG tu nap lai khi code doi (push len Cloud / sua o laptop) -> tu reload theo mtime
    for mod in (news_alert, tom_tat):
        mt = os.path.getmtime(mod.__file__)
        if getattr(mod, "_mt_nap", None) != mt:                 # chua co dau (ban nap truoc khi co co che nay) -> reload 1 lan
            mod = importlib.reload(mod)
        mod._mt_nap = mt
    return sys.modules["news_alert"]


def _keo_drive(na, force: bool = False) -> bool:
    """Keo watchlist/config/trang thai/tom tat tu Drive, toi da 1 lan / 60 s / phien (force = ngay)."""
    k = "wl_keo_luc"
    if not force and time.time() - st.session_state.get(k, 0) < 60:
        return st.session_state.get("wl_keo_ok", False)
    ok = na.keo_ve(trang_thai=True)
    st.session_state[k], st.session_state["wl_keo_ok"] = time.time(), ok
    return ok


def _now_vn() -> pd.Timestamp:
    """Gio VN (naive) - Streamlit Cloud chay UTC."""
    return pd.Timestamp.now(tz="Asia/Ho_Chi_Minh").tz_localize(None)


def _doc_json(p: str) -> dict:
    import json
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def watchlist(ctx):
    h0, h1 = st.columns([5, 1])
    with h0:
        ui.h2("Watchlist tin tức — cảnh báo theo mã")
    if not os.path.exists(os.path.join(ALERT_DIR, "news_alert.py")):
        ui.card_empty("Watchlist", "", "Thiếu thư mục news-alert trong bản code này.", key="wl_khong_co")
        return
    na = _alert()
    lam_moi = h1.button("↻ Kéo tin mới", key="wl_lam_moi", help=f"Kéo lại tin RSS + watchlist/lịch sử từ Drive")
    drive_ok = _keo_drive(na, force=lam_moi)
    cfg = na.doc_cfg()
    wl = na.doc_watchlist()
    tt = _doc_json(os.path.join(ALERT_DIR, "trang_thai_email.json"))

    # ---- KPI trang thai
    lich = pd.read_csv(na.LICH_SU, encoding="utf-8-sig", parse_dates=["bao_luc", "ngay_gio"]) if os.path.exists(na.LICH_SU) \
        else pd.DataFrame()
    n_hn = int((lich["bao_luc"] >= _now_vn().normalize()).sum()) if len(lich) else 0
    lan = pd.Timestamp(tt["luc"]) if tt.get("luc") else None
    tre = (_now_vn() - lan).total_seconds() / 60 if lan is not None else None
    ui.kpi_strip([
        ("Mã theo dõi", f"{len(wl)}", ", ".join(x["ma"] for x in wl[:8]) + (" …" if len(wl) > 8 else ""), 0),
        ("Email đã báo hôm nay", f"{n_hn}", f"tổng {len(lich)} tin đã báo qua email", 1 if n_hn else 0),
        ("Quét online lần cuối", f"{lan:%H:%M %d/%m}" if lan is not None else "chưa chạy",
         (f"{tt.get('khop', 0)} tin khớp · {tt.get('moi', 0)} tin mới" if tt else "GitHub Actions News Alert"),
         (-1 if tre is not None and tre > 60 and cfg.get("gio_bat_dau", 7) <= _now_vn().hour < cfg.get("gio_ket_thuc", 22)
          else 0)),
        ("Kênh", "Email" if cfg.get("email_bat") else "Email tắt",
         f"{cfg.get('gio_bat_dau', 7)}h–{cfg.get('gio_ket_thuc', 22)}h · 15 phút/lần · tóm tắt {cfg.get('tom_tat_email_gio', '—')}h", 0),
    ])
    if not drive_ok:
        ui.note('<span style="color:var(--down)">Không đồng bộ được với Google Drive — đang dùng bản local, '
                'sửa watchlist sẽ chưa tới bộ cảnh báo online.</span>')

    col1, col2 = st.columns([1.25, 1])
    # ---- (a) SUA WATCHLIST
    with col1:
        with ui.card("Danh sách theo dõi", "sửa xong bấm Lưu", key="wl_ds", controls=False,
                     help="Mã = mã CK (tự nhận cả tên DN theo news-rss\\config\\alias_ma.csv, VD 'Hòa Phát' → HPG). "
                          "Tên gọi thêm = tên khác tự khai, cách nhau dấu ; (khớp nguyên từ trong tiêu đề / tóm tắt). "
                          "Lưu → đẩy lên Google Drive; bộ cảnh báo online dùng ở lần quét 15 phút kế tiếp.") as c:
            with c.body():
                df = pd.DataFrame([{"ma": x["ma"], "ten_goi_them": "; ".join(x["ten"]), "ghi_chu": x["ghi_chu"]} for x in wl],
                                  columns=["ma", "ten_goi_them", "ghi_chu"])
                ed = st.data_editor(df, num_rows="dynamic", use_container_width=True, hide_index=True, key="wl_editor",
                                    column_config={"ma": st.column_config.TextColumn("Mã", max_chars=10),
                                                   "ten_goi_them": st.column_config.TextColumn("Tên gọi thêm (;)"),
                                                   "ghi_chu": st.column_config.TextColumn("Ghi chú")})
                b0, b1 = st.columns([1, 2.4])
                if b0.button("💾 Lưu watchlist", key="wl_luu", type="primary"):
                    moi, thay = [], set()
                    for r in ed.fillna("").itertuples(index=False):
                        m = str(r.ma).strip().upper()
                        if m and m not in thay:
                            thay.add(m)
                            moi.append({"ma": m, "ten": [x.strip() for x in str(r.ten_goi_them).split(";") if x.strip()],
                                        "ghi_chu": str(r.ghi_chu).strip()})
                    ok = na.ghi_watchlist(moi)
                    st.session_state.pop("wl_editor", None)
                    st.toast(f"Đã lưu {len(moi)} mã" + (" · đã đồng bộ online" if ok else " · CHƯA lên Drive"))
                    st.rerun()
                b1.markdown('<div class="gn-note">Thêm mã: bấm ＋ cuối bảng · xoá: tick ô đầu dòng rồi bấm 🗑</div>',
                            unsafe_allow_html=True)
    # ---- (b) KENH THONG BAO
    with col2:
        with ui.card("Email thông báo", "config.json trên Drive", key="wl_kenh", controls=False,
                     help="Bộ cảnh báo online (GitHub Actions) gửi email khi có tin mới + 1 email tóm tắt cuối ngày bằng Claude Sonnet. "
                          "Mật khẩu ứng dụng Gmail = secret NEWS_ALERT_SMTP_PASS (GitHub), không lưu ở đây. "
                          "Laptop (task News Alert) còn bật thông báo góc màn hình khi máy mở.") as c:
            with c.body():
                eb = st.toggle("Gửi email khi có tin mới", bool(cfg.get("email_bat")), key="wl_email")
                den = st.text_input("Email nhận (nhiều địa chỉ cách dấu phẩy)", cfg.get("email_gui_den", ""), key="wl_den")
                usr = st.text_input("Gmail gửi (tài khoản có mật khẩu ứng dụng)", cfg.get("smtp_user", ""), key="wl_user")
                g0, g1, g2 = st.columns(3)
                gbd = g0.number_input("Báo từ giờ", 0, 23, int(cfg.get("gio_bat_dau", 7)), key="wl_gbd")
                gkt = g1.number_input("Đến giờ", 1, 24, int(cfg.get("gio_ket_thuc", 22)), key="wl_gkt")
                gtt = g2.number_input("Email tóm tắt lúc", 0, 23, int(cfg.get("tom_tat_email_gio") or 17), key="wl_gtt",
                                      help="Giờ gửi email tóm tắt diễn biến trong ngày (Claude Sonnet), 1 lần/ngày")
                k0, k1 = st.columns(2)
                if k0.button("💾 Lưu", key="wl_luu_kenh"):
                    cfg.update(email_bat=eb, email_gui_den=den.strip(), smtp_user=usr.strip(), gio_bat_dau=int(gbd),
                               gio_ket_thuc=int(gkt), tom_tat_email_gio=int(gtt))
                    ok = na.ghi_cfg(cfg)
                    st.toast("Đã lưu" + (" · đã đồng bộ online" if ok else " · CHƯA lên Drive"))
                    st.rerun()
                thieu = na.thieu_email(cfg)
                if thieu:
                    st.markdown('<div class="gn-note" style="color:var(--down)">Chưa gửi được email — thiếu: '
                                + html.escape(", ".join(thieu)) + '. Điền 2 ô trên rồi bấm 💾 Lưu; mật khẩu ứng dụng Gmail đặt ở '
                                'GitHub secret (email tự động) và Streamlit secrets / biến môi trường laptop (nút Gửi thử).</div>',
                                unsafe_allow_html=True)
                if k1.button("🔔 Gửi thử", key="wl_thu", help="Gửi 2 tin mới nhất khớp watchlist (email; laptop thêm toast)"):
                    p_kho = _paths()[0]
                    with st.spinner("Đang gửi thử ..."):
                        try:
                            t_thu = pd.read_parquet(p_kho) if os.path.exists(p_kho) else pd.DataFrame()
                            kq = na.gui_thu(t_thu, kenh="ca-hai")
                            (st.success if ("đã gửi" in kq or "đã hiện" in kq) else st.error)(kq)
                        except Exception as e:  # noqa: BLE001
                            st.error(f"{type(e).__name__}: {e}")

    # ---- (c) TOM TAT HOM NAY - Claude Sonnet
    loi = _lam_moi(force=lam_moi)
    p, pt, _, _ = _paths()
    today = _now_vn().normalize()
    if ALERT_DIR not in sys.path:
        sys.path.insert(0, ALERT_DIR)
    import tom_tat as tt_mod
    with ui.card("Tóm tắt diễn biến trong ngày", f"Claude Sonnet · {tt_mod.MODEL}", key="wl_tomtat", controls=False,
                 help="Gom tin trong ngày khớp watchlist (gộp tin trùng) → Claude Sonnet tóm tắt theo từng mã: điểm chính, diễn biến "
                      "theo giờ, ý nghĩa với cổ phiếu, việc cần theo dõi. Chỉ dựa trên tiêu đề + tóm tắt RSS. Kết quả lưu "
                      "news-alert/tom_tat/<ngày>.md trên Drive (laptop + app online + email cuối ngày dùng chung). "
                      "Cần API key Anthropic: biến ANTHROPIC_API_KEY (laptop) / Streamlit secrets (online).") as c:
        with c.body():
            a0, a1, a2 = st.columns([1.2, 1, 3])
            ngay = a0.date_input("Ngày", today.date(), key="wl_tt_ngay", format="DD/MM/YYYY", label_visibility="collapsed")
            ngay_s = f"{ngay:%Y-%m-%d}"
            cu = tt_mod.doc_ban_cu(ngay_s)
            bam = a1.button("🤖 Tóm tắt lại" if cu else "🤖 Tóm tắt", key="wl_tt_chay", type="primary" if not cu else "secondary")
            if bam:
                if not os.environ.get("ANTHROPIC_API_KEY"):
                    st.error("Chưa có API key Anthropic: đặt ANTHROPIC_API_KEY (biến môi trường User trên laptop, hoặc Streamlit "
                             "secrets cho app online) rồi mở lại app.")
                else:
                    with st.spinner(f"Claude Sonnet đang đọc tin {ngay:%d/%m} ..."):
                        try:
                            cu = tt_mod.tom_tat(ngay_s, kho=[p])          # kho tin cua app (Streamlit Cloud: dl.CACHE rieng)
                        except RuntimeError as e:
                            st.error(str(e))
                        except Exception as e:  # noqa: BLE001
                            st.error(f"Lỗi tóm tắt: {type(e).__name__}: {e}")
            if cu:
                a2.markdown(f'<div class="gn-note">Tóm tắt lúc {cu["luc"][11:16]} {cu["luc"][8:10]}/{cu["luc"][5:7]} · '
                            f'{cu["so_tin"]} tin · {cu["model"]} · {cu["in_tok"]:,}+{cu["out_tok"]:,} token</div>'.replace(",", "."),
                            unsafe_allow_html=True)
                st.markdown(cu["text"])
                with st.expander(f"Nguồn ({cu['so_tin']} tin)"):
                    st.markdown(cu["nguon"])
            elif not bam:
                st.markdown('<div class="gn-note">Chưa có bản tóm tắt cho ngày này — bấm 🤖 Tóm tắt.</div>', unsafe_allow_html=True)

    # ---- (d) TIN KHOP WATCHLIST (kho tin cua app, 90 ngay)
    if not wl or not os.path.exists(p):
        ui.card_empty("Tin khớp watchlist", "", loi or "Watchlist rỗng / chưa có kho tin", key="wl_tin_trong")
        return
    t, _, _ = _news(max(dl._raw_mt(p), dl._raw_mt(pt)))
    m = na.khop(t, wl)
    sent = na.doc_sent("email")
    mas = [x["ma"] for x in wl]
    with ui.card("Tin khớp watchlist", "kho tin của app (giữ 90 ngày)",
                 help="Cùng luật lọc với bộ cảnh báo: mã do bộ phân loại news-rss gắn + tên gọi thêm. 🔔 = tin đã gửi email.",
                 key="wl_tin", periods=["1D", "3D", "1W", "1M", "3M", "All"], default="1W", end=today,
                 chips=mas, chip_multi=True, chip_default=mas, chip_label="Mã") as c:
        chon = set(c.chip or [])
        x = m[(m["ngay_gio"] >= pd.Timestamp(c.d0)) & (m["ngay_gio"] < pd.Timestamp(c.d1) + pd.Timedelta(days=1))]
        x = x[x["ma_wl"].str.split("|").map(lambda v: bool(set(v) & chon))] if chon else x
        x = x.sort_values("ngay_gio", ascending=False).drop_duplicates("nhom_trung", keep="first")
        if x.empty:
            c.empty("Không có tin về các mã đã chọn trong khung thời gian")
        else:
            x = x.assign(tieu_de=[("🔔 " if (i in sent or f"g:{g}" in sent) else "") + str(td)
                                  for i, g, td in zip(x["id"], x["nhom_trung"], x["tieu_de"])])
            c.markdown(_html(x, TAT_CA))
            c.export(_export(x).assign(**{"Mã watchlist": x["ma_wl"].str.replace("|", ", ").to_numpy()}), ten="Tin watchlist")
            with c._foot:
                st.markdown(f'<div class="gn-note">{len(x)} tin · {x["nguon"].nunique()} báo · {c.d0:%d/%m/%Y} – {c.d1:%d/%m/%Y}'
                            f'{" · lần kéo vừa rồi lỗi: " + html.escape(loi) if loi else ""}</div>', unsafe_allow_html=True)

    # ---- (e) LICH SU DA BAO
    with ui.card("Lịch sử email đã gửi", "lich_su.csv", key="wl_lich_su", controls=False) as c:
        if lich.empty:
            c.empty("Chưa gửi email tin nào")
        else:
            ls = lich.sort_values("bao_luc", ascending=False).head(200).rename(columns={
                "bao_luc": "Báo lúc", "ngay_gio": "Đăng lúc", "ma_wl": "Mã", "nguon": "Báo", "tieu_de": "Tiêu đề", "url": "Link"})
            ls["Mã"] = ls["Mã"].astype(str).str.replace("|", ", ")
            c.table(ls[["Báo lúc", "Mã", "Báo", "Tiêu đề", "Đăng lúc", "Link"]].set_index("Báo lúc"), ten="Lich su canh bao")
