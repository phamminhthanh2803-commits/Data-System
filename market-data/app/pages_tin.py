# -*- coding: utf-8 -*-
r"""
pages_tin.py - Tin tuc › TIN THEO NGANH (11/11/2026): tin RSS 11 bao kinh te (news-rss\fetch_rss.py) da phan loai theo
23 nganh (19 ICB Vietcap cap 2 nhu ca app + Vingroup + Vi mo / TTCK / The gioi). Chon nganh -> tin tu loc va SAP XEP
(moi nhat / lien quan nhat / dang chu y). Deep-link: ?trang=tin-tuc/tin-nganh&nganh=Ngân hàng
"""
from __future__ import annotations

import html
import os

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


def _paths():
    p = dl.reg_path("news_rss")
    d = os.path.dirname(p)
    return p, os.path.join(d, "news_tags.parquet"), os.path.join(d, "feed_status.csv"), os.path.join(d, "nganh.csv")


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


def _pull_cloud():
    try:
        import cloud_boot
        if cloud_boot.is_cloud():
            with st.spinner("Đang kéo tin RSS từ Drive ..."):
                cloud_boot.pull_folder("news-rss", ["/data/news_tagged.parquet", "/data/news_tags.parquet", "/data/feed_status.csv",
                                                    "/data/nganh.csv"])
    except Exception:  # noqa: BLE001
        pass


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
    ui.h2("Tin tức theo ngành — RSS báo kinh tế")
    p, pt, pf, _ = _paths()
    if not os.path.exists(p):
        _pull_cloud()
    if not os.path.exists(p):
        ui.card_empty("Tin theo ngành", "", f"Chưa có <code>{p}</code> — chạy <code>python D:\\market-data\\news-rss\\fetch_rss.py</code> "
                      "(bước <b>news</b> AM/PM/EOD) hoặc kéo dữ liệu cloud về.", key="tin_rss_trong")
        return
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
                      "VietnamBiz, Nhịp sống KD, VietnamPlus), kéo ở bước news (AM/PM/EOD). Phân loại = từ điển ~1.100 từ khoá theo ngành "
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
