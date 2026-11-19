# -*- coding: utf-8 -*-
r"""tom_tat.py - Claude Sonnet tom tat tin theo KHUNG THOI GIAN: 2 hang muc VI MO + TIN DOANH NGHIEP (18-19/11/2026).

- Vi mo  = bai news-rss gan nganh "Vĩ mô & chính sách" / "Kinh tế thế giới" trong khung (gop trung, chon theo diem lien quan,
           moi chu de <= MAX_MOI_CHU_DE bai, gia vang/bac gom 1 nhom).
- Tin DN = bai khop watchlist (hoac cac ma / tu khoa trong THANH TIM KIEM `tim` - xem tin rieng tung ma), gom theo loai su kien,
           KHONG chia muc theo tung ma.
Khung: tu..den bat ky (app: Hom nay / 24 gio / 3 ngay / 1 tuan / tuy chon); khung dai -> nang tran so bai (_he_so).

Goi tu app (Tin tuc › Watchlist) hoac CLI:
    python tom_tat.py                          hom nay, watchlist + vi mo (email cuoi ngay dung dung ban nay)
    python tom_tat.py --ngay 2026-11-17
    python tom_tat.py --tu "2026-11-13" --den "2026-11-20" --tim HPG,"Hòa Phát" --chi dn

Ket qua luu tom_tat\<khoa>.md + .json (khoa = <ngay> cho ban mac dinh trong ngay) -> app hien lai khong goi API lan nua.
Can API key Anthropic: bien moi truong User ANTHROPIC_API_KEY (SDK tu doc). Chi phi ~ vai trang/lan (Sonnet 5.5: $2/$10 moi 1M token).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")   # Streamlit Cloud chay gio UTC -> moi moc thoi gian theo gio VN

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "tom_tat")
MODEL = "claude-sonnet-5-5"          # PV2 chon Sonnet
MAX_BAI = 150                         # tin DN cho khung 1 ngay; nhieu hon -> giu bai diem chu y cao
VIMO, TG = "Vĩ mô & chính sách", "Kinh tế thế giới"
MAX_VIMO, MAX_TG = 45, 15             # tin vi mo VN / the gioi cho khung 1 ngay (chon theo diem lien quan)
MAX_MOI_CHU_DE = 8                    # 1 chu de toi da 8 bai -> du phu cac chu de khac
MAX_VANG = 5                          # gia vang/bac: 20-30 bai/ngay cung 1 dien bien -> 5 bai diem cao nhat

SYSTEM = """Bạn là chuyên viên phân tích chứng khoán Việt Nam, viết bản tóm tắt tin cho nhà đầu tư trong một khung thời gian cho trước.
Đầu vào có thể gồm 2 khối: (A) tin doanh nghiệp (các mã theo dõi / mã được tìm), (B) tin vĩ mô trong nước và kinh tế thế giới.

Quy tắc chung:
- Chỉ dựa vào các tin được cung cấp (tiêu đề + tóm tắt RSS). Không thêm số liệu, sự kiện hay giá cổ phiếu không có trong tin.
- Tin trùng nhau giữa các báo chỉ kể một lần. Ghi số tin nguồn dạng [3] (số thứ tự chung của cả 2 khối).
- Khung nhiều ngày: nêu diễn biến theo thời gian (ghi ngày), ưu tiên thay đổi quan trọng nhất của cả khung.
- Viết tiếng Việt, Markdown gọn, tổng không quá ~1.000 từ (khung trên 3 ngày: ~1.400 từ).

Bố cục CHỈ GỒM 2 mục dưới đây, theo thứ tự (bỏ mục không có khối đầu vào tương ứng; không thêm mục khác):

## Vĩ mô
Gom khối (B) theo chủ đề, mỗi chủ đề một dòng "**<Chủ đề>:**" + 1-3 câu có số liệu chính trong tin (thứ tự ưu tiên:
Chính sách tiền tệ & lãi suất · Tỷ giá & ngoại hối · Tăng trưởng/sản xuất/XNK/FDI · Lạm phát & giá cả · Ngân sách, thuế,
đầu tư công · Chính sách & pháp luật · Vàng · Thế giới (Fed, Mỹ, Trung Quốc, giá hàng hoá)). Nhiều bài cùng một số liệu
(vd giá vàng cập nhật nhiều lần) → nêu diễn biến một lần. Kết mục bằng "**Tác động tới thị trường:**" (ngành/nhóm cổ phiếu
hưởng lợi hay chịu áp lực, lý do ngắn) và "**Cần theo dõi:**" (sự kiện vĩ mô sắp tới được nhắc trong tin).

## Tin doanh nghiệp
KHÔNG chia tiểu mục theo từng mã. Gom khối (A) theo loại sự kiện, mỗi loại một dòng "**<Loại>:**" rồi các gạch đầu dòng
(gợi ý loại: Kết quả kinh doanh · Cổ tức, phát hành & tăng vốn · Dự án, đầu tư & hợp đồng · M&A, cổ đông & giao dịch nội bộ ·
Pháp lý & quản trị · Nhận định, khuyến nghị · Khác). Mỗi gạch đầu dòng mở đầu bằng mã in đậm (vd **HPG**, nhiều mã cách dấu
phẩy) — gồm mã theo dõi và các "DN khác được nhắc" có vai trò thật trong sự kiện (đối tác, bên mua/bán, nhà thầu, chủ đầu tư),
không gắn DN chỉ được nhắc thoáng qua —, nêu sự kiện + số liệu chính + đánh giá ngắn (tích cực / tiêu cực / trung tính) và số tin nguồn. Tin chỉ nhắc mã thoáng
qua (bài tổng hợp thị trường) thì gộp 1 dòng ở "Khác" hoặc bỏ. Kết mục bằng "**Cần theo dõi:**" (sự kiện doanh nghiệp sắp tới)."""


def _he_so(tu, den) -> float:
    """Khung dai -> nhieu bai hon: <= 30 gio x1, <= 4 ngay x1.5, con lai x2."""
    gio = (den - tu).total_seconds() / 3600
    return 1.0 if gio <= 30 else 1.5 if gio <= 96 else 2.0


def _chon_vimo(t, bo_id: set, hs: float = 1.0) -> list[dict]:
    """Tin vi mo VN + the gioi trong bang tin `t` (da loc khung): bo bai da o khoi DN, gop trung, chon theo diem lien quan,
    moi chu de toi da MAX_MOI_CHU_DE bai (x he so khung). Tra list bai (cot `khoi` = 'VN' | 'TG') theo thu tu thoi gian."""
    import pandas as pd
    if t.empty:
        return []
    ng = t["nganh"].fillna("").astype(str)
    v = t[(ng.str.contains(VIMO, regex=False) | ng.str.contains(TG, regex=False)) & ~t["id"].isin(bo_id)].copy()
    if v.empty:
        return []
    ng = v["nganh"].fillna("").astype(str)
    # VN: nganh chinh Vi mo, hoac co nhan Vi mo ma nganh chinh khong phai The gioi; con lai -> TG
    vn = v["nganh_chinh"].eq(VIMO) | (ng.str.contains(VIMO, regex=False) & ~v["nganh_chinh"].eq(TG))
    v["khoi"] = vn.map({True: "VN", False: "TG"})
    v["chu_de_1"] = v["chu_de"].fillna("").astype(str).str.split("|").str[0].replace("", "Khác")
    # bai gia vang (nhieu bao cap nhat ca ngay, chu de dau hay la Fed/Ty gia) -> gom 1 nhom "Vàng"
    vang = v["chu_de_1"].eq("Vàng") | v["tieu_de"].fillna("").str.lower().str.contains(
        r"giá vàng|vàng thế giới|vàng sjc|vàng nhẫn|usd/ounce|giá bạc")
    v.loc[vang, "chu_de_1"] = "Vàng"
    v = v.sort_values(["diem", "so_nguon", "ngay_gio"], ascending=False)
    v = v[~(v["nhom_trung"].fillna("").ne("") & v["nhom_trung"].duplicated())]
    v = v.groupby(["khoi", "chu_de_1"], sort=False).head(int(MAX_MOI_CHU_DE * hs))
    v = v[(v["chu_de_1"] != "Vàng") | (v.groupby("chu_de_1").cumcount() < int(MAX_VANG * hs))]
    out = pd.concat([v[v["khoi"] == "VN"].head(int(MAX_VIMO * hs)), v[v["khoi"] == "TG"].head(int(MAX_TG * hs))])
    return out.sort_values("ngay_gio").to_dict("records")


def tach_tim(s: str | list | None) -> list[str]:
    """Chuoi thanh tim kiem 'HPG, VCB; Hòa Phát' -> ['HPG', 'VCB', 'Hòa Phát'] (bo trung, giu thu tu)."""
    if not s:
        return []
    ds = s if isinstance(s, list) else re.split(r"[,;\n]+", str(s))
    out = []
    for x in ds:
        x = str(x).strip()
        x = x.upper() if re.fullmatch(r"[A-Za-z0-9]{3}", x) else x
        if x and x not in out:
            out.append(x)
    return out


def _wl_tim(tim: list[str], wl: list[dict]) -> list[dict]:
    """Thanh tim kiem -> danh sach dang watchlist cho na.khop: ma 3 ky tu (lay ca ten goi them neu ma co trong watchlist),
    tu khoa khac (vd ten DN) -> khop nguyen tu trong tieu de / tom tat."""
    theo_ma = {x["ma"]: x for x in wl}
    out = []
    for x in tim:
        if re.fullmatch(r"[A-Z0-9]{3}", x):
            out.append(theo_ma.get(x) or {"ma": x, "ten": [], "ghi_chu": ""})
        else:
            out.append({"ma": x, "ten": [x], "ghi_chu": ""})
    return out


def _doc_kho(kho: list[str] | None):
    import pandas as pd
    # 18/11: app truyen kho cua chinh no (Streamlit Cloud: dl.CACHE khong nam o <market-data>/app/cache) + kho news-alert (Actions)
    kho = list(kho or []) + [os.path.join(os.path.dirname(BASE), "app", "cache", "news-rss", "news_tagged.parquet"),
                             os.path.join(BASE, "kho", "news_tagged.parquet")]
    co = [p for p in dict.fromkeys(os.path.normpath(x) for x in kho) if os.path.exists(p)]
    if not co:
        raise RuntimeError("Không tìm thấy kho tin RSS (news_tagged.parquet) — mở trang Tin theo ngành / bấm ↻ Kéo tin mới trước")
    return pd.concat([pd.read_parquet(p) for p in co], ignore_index=True).drop_duplicates("id")


def _bai_khung(tu, den, kho=None, tim=None, vimo=True, dn=True) -> tuple[list[dict], list[str], list[dict]]:
    """Tin trong khung [tu, den): (tin DN khop watchlist / thanh tim kiem, ds ma-tu khoa, tin vi mo)."""
    sys.path.insert(0, BASE)
    import news_alert as na
    wl = na.doc_watchlist()
    if tim:
        wl = _wl_tim(tim, wl)
    mas = [x["ma"] for x in wl]
    t = _doc_kho(kho)
    t = t[(t["ngay_gio"] >= tu) & (t["ngay_gio"] < den)]
    hs = _he_so(tu, den)
    m = na.khop(t, wl) if dn and len(t) and wl else t.iloc[0:0]
    if not m.empty:
        m = m.sort_values("ngay_gio").drop_duplicates("nhom_trung", keep="first")
        if len(m) > MAX_BAI * hs:
            m = m.sort_values(["diem_chu_y", "ngay_gio"], ascending=False).head(int(MAX_BAI * hs)).sort_values("ngay_gio")
    vm = _chon_vimo(t, set(m["id"]) if len(m) else set(), hs) if vimo else []
    return m.to_dict("records"), mas, vm


def _bai_hom_nay(ngay: str, kho: list[str] | None = None):
    """Tuong thich cu: tin ca ngay `ngay` (watchlist + vi mo)."""
    import pandas as pd
    d0 = pd.Timestamp(ngay)
    return _bai_khung(d0, d0 + pd.Timedelta(days=1), kho)


def khoa_mac_dinh(tu, den, tim=None, vimo=True, dn=True) -> str:
    """Ten file luu ban tom tat: '<ngay>' cho ban ca ngay watchlist + vi mo (email cuoi ngay); con lai tu-den + bo loc."""
    import pandas as pd
    ca_ngay = tu == tu.normalize() and den == tu + pd.Timedelta(days=1)
    k = f"{tu:%Y-%m-%d}" if ca_ngay else f"{tu:%Y%m%d-%H%M}_{den:%Y%m%d-%H%M}"
    if tim:
        import unicodedata
        s = unicodedata.normalize("NFKD", "-".join(tim).replace("đ", "d").replace("Đ", "D"))
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        k += "_" + re.sub(r"[^0-9A-Za-z]+", "-", s).strip("-")[:60]
    if not (vimo and dn):
        k += "_vimo" if vimo else "_dn"
    return k


def tom_tat(ngay: str | None = None, kho: list[str] | None = None, tu=None, den=None, tim=None,
            vimo: bool = True, dn: bool = True, khoa: str | None = None) -> dict:
    """Goi Sonnet tom tat tin khung [tu, den) (mac dinh: ca ngay `ngay`, hom nay). tim = thanh tim kiem (ma / tu khoa) thay
    watchlist cho muc Tin doanh nghiep; vimo / dn = chon hang muc. Tra dict {text, nguon, so_tin, model, luc, tu, den, ...};
    luu tom_tat\\<khoa>.md/.json + day len Drive. Loi -> RuntimeError voi thong bao tieng Viet."""
    import anthropic
    import pandas as pd
    if not (vimo or dn):
        raise RuntimeError("Chọn ít nhất 1 hạng mục: Vĩ mô hoặc Tin doanh nghiệp")
    if tu is None:
        tu = pd.Timestamp(ngay or datetime.now(VN).strftime("%Y-%m-%d"))
        den = tu + pd.Timedelta(days=1)
    tu, den = pd.Timestamp(tu), pd.Timestamp(den)
    tim = tach_tim(tim)
    khoa = khoa or khoa_mac_dinh(tu, den, tim, vimo, dn)
    bai_wl, mas, vm = _bai_khung(tu, den, kho, tim, vimo, dn)
    khung = f"{tu:%d/%m/%Y %H:%M} – {den:%d/%m/%Y %H:%M}"
    if not bai_wl and not vm:
        raise RuntimeError(f"Không có tin nào ({'vĩ mô / ' if vimo else ''}{'doanh nghiệp ' if dn else ''}) trong khung {khung}"
                           + (f" khớp: {', '.join(tim)}" if tim else ""))
    bai = bai_wl + vm                                          # so [n] chung: DN truoc, vi mo sau
    nhieu_ngay = (den - tu) > pd.Timedelta(hours=30)
    fmt = "%d/%m %H:%M" if nhieu_ngay else "%H:%M"

    def _dong(i: int, b: dict, nhan: str, doan_dau: bool = False) -> str:
        tt = str(b.get("tom_tat") or "").strip()
        dd = str(b.get("doan_dau") or "").strip() if doan_dau else ""
        sn = int(b.get("so_nguon") or 1)
        return (f"[{i}] {b['ngay_gio']:{fmt}} · {b['nguon']}{f' (+{sn - 1} báo khác)' if sn > 1 else ''} · {nhan}\n"
                f"Tiêu đề: {b['tieu_de']}\n" + (f"Đoạn đầu bài: {dd[:700]}" if len(dd) > len(tt) else f"Tóm tắt: {tt}"))

    def _nhan_dn(b: dict) -> str:
        # 19/11: DN duoc nhac (cot ma: tieu de + sapo + doan dau bai) -> Sonnet gan tag ma cho tung dong
        khac = [x for x in str(b.get("ma") or "").split("|") if x and x not in b["ma_wl"].split("|")]
        return ("mã: " + b["ma_wl"].replace("|", ", ") + (f" · DN khác được nhắc: {', '.join(khac[:8])}" if khac else "")
                + (f" · loại: {str(b['loai_tin']).replace('|', ', ')}" if b.get("loai_tin") else ""))
    khoi_a = [_dong(i, b, _nhan_dn(b), doan_dau=True) for i, b in enumerate(bai_wl, 1)]
    khoi_b = [_dong(i, b, ("Thế giới" if b["khoi"] == "TG" else "Trong nước") + " · chủ đề: "
                    + (str(b.get("chu_de") or "").replace("|", ", ") or "khác"))
              for i, b in enumerate(vm, len(bai_wl) + 1)]
    phan = [f"{'Mã / từ khoá được tìm' if tim else 'Danh sách theo dõi'}: {', '.join(mas) or '(trống)'}",
            f"Khung thời gian: {khung}", f"Hạng mục cần viết: {' + '.join(([] if not vimo else ['Vĩ mô']) + ([] if not dn else ['Tin doanh nghiệp']))}"]
    if dn:
        phan.append(f"(A) {len(bai_wl)} tin doanh nghiệp (đã gộp tin trùng):\n\n" + ("\n\n".join(khoi_a) or "(không có)"))
    if vimo:
        phan.append(f"(B) {len(vm)} tin vĩ mô & kinh tế thế giới (đã gộp tin trùng, chọn theo mức liên quan):\n\n"
                    + ("\n\n".join(khoi_b) or "(không có)"))
    user = "\n\n".join(phan)
    try:
        client = anthropic.Anthropic()
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=10000,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",                         # tu chuyen model khac neu bi tu choi nham
        )
    except anthropic.AuthenticationError:
        raise RuntimeError("API key Anthropic không hợp lệ (biến ANTHROPIC_API_KEY)") from None
    except anthropic.PermissionDeniedError as e:
        raise RuntimeError(f"API key không có quyền dùng {MODEL}: {e.message}") from None
    except anthropic.RateLimitError:
        raise RuntimeError("Đang bị giới hạn tần suất API — thử lại sau ít phút") from None
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Lỗi API {e.status_code}: {e.message}") from None
    except anthropic.APIConnectionError:
        raise RuntimeError("Không kết nối được API Anthropic (mạng?)") from None
    except TypeError as e:                               # chua co credential: SDK bao thieu api_key
        if "api_key" in str(e) or "auth" in str(e).lower():
            raise RuntimeError("Chưa có API key: đặt biến môi trường User ANTHROPIC_API_KEY rồi mở lại app") from None
        raise
    if resp.stop_reason == "refusal":
        raise RuntimeError("Model từ chối tóm tắt lượt này — thử lại")
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "max_tokens":
        text += "\n\n_(bị cắt do giới hạn độ dài)_"
    # chu thich nguon [n] -> link bai
    nguon = "\n".join(f"{i}. [{'Vĩ mô · ' if i > len(bai_wl) else ''}{b['nguon']} · {b['ngay_gio']:{fmt}}] [{b['tieu_de']}]({b['url']})"
                      for i, b in enumerate(bai, 1))
    kq = {"ngay": f"{tu:%Y-%m-%d}", "khoa": khoa, "tu": tu.isoformat(timespec="minutes"), "den": den.isoformat(timespec="minutes"),
          "khung": khung, "tim": tim, "vimo": vimo, "dn": dn,
          "luc": datetime.now(VN).replace(tzinfo=None).isoformat(timespec="seconds"), "so_tin": len(bai), "model": resp.model,
          "in_tok": resp.usage.input_tokens, "out_tok": resp.usage.output_tokens, "ma": mas,
          "so_tin_wl": len(bai_wl), "so_tin_vimo": len(vm), "text": text, "nguon": nguon}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"{khoa}.md"), "w", encoding="utf-8") as f:
        f.write(f"# Tóm tắt tin {khung}{' · ' + ', '.join(tim) if tim else ''} ({kq['luc'][11:16]})\n\n{text}\n\n---\n"
                f"**Nguồn**\n\n{nguon}\n")
    with open(os.path.join(OUT, f"{khoa}.json"), "w", encoding="utf-8") as f:
        json.dump(kq, f, ensure_ascii=False, indent=1)
    import news_alert as na                                   # len Drive -> app online / laptop doc chung
    na.day_len(os.path.join("tom_tat", f"{khoa}.md"), os.path.join("tom_tat", f"{khoa}.json"))
    return kq


def md_html(md: str) -> str:
    """Markdown gon cua Sonnet -> HTML cho email (###, -, **dam**, [chu](url), so thu tu)."""
    import html as h
    import re
    out, ds = [], None
    for dong in md.splitlines():
        s = dong.rstrip()
        x = h.escape(re.sub(r"^\s*(#{1,6}\s+|[-*]\s+|\d+\.\s+)", "", s).strip())
        x = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", x)
        x = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', x)
        m_ds = re.match(r"^\s*([-*]|\d+\.)\s", s)
        if ds and not m_ds:
            out.append(f"</{ds}>")
            ds = None
        if re.match(r"^#{1,6}\s", s):
            out.append(f'<h3 style="margin:14px 0 4px">{x}</h3>')
        elif m_ds:
            loai = "ol" if m_ds.group(1)[0].isdigit() else "ul"
            if ds != loai:
                if ds:
                    out.append(f"</{ds}>")
                out.append(f'<{loai} style="margin:2px 0 6px 18px;padding:0">')
                ds = loai
            out.append(f"<li>{x}</li>")
        elif x:
            out.append(f'<p style="margin:4px 0">{x}</p>')
    if ds:
        out.append(f"</{ds}>")
    return "\n".join(out)


def doc_ban_cu(khoa: str) -> dict | None:
    """Ban tom tat da luu theo khoa (<ngay> hoac khoa_mac_dinh / khoa app dat)."""
    p = os.path.join(OUT, f"{khoa}.json")
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--ngay", default=None, help="ca ngay YYYY-MM-DD (mac dinh hom nay)")
    ap.add_argument("--tu", default=None, help="dau khung, vd '2026-11-13' hoac '2026-11-19 08:00'")
    ap.add_argument("--den", default=None, help="cuoi khung (khong gom), mac dinh bay gio")
    ap.add_argument("--tim", default=None, help="ma / tu khoa thay watchlist cho Tin doanh nghiep, cach dau phay")
    ap.add_argument("--chi", choices=["vimo", "dn"], default=None, help="chi 1 hang muc")
    a = ap.parse_args()
    import pandas as pd
    tu = pd.Timestamp(a.tu) if a.tu else None
    den = pd.Timestamp(a.den) if a.den else (pd.Timestamp(datetime.now(VN).replace(tzinfo=None)) if tu is not None else None)
    try:
        kq = tom_tat(a.ngay, tu=tu, den=den, tim=a.tim, vimo=a.chi != "dn", dn=a.chi != "vimo")
    except RuntimeError as e:
        print(f"X {e}")
        sys.exit(2)
    print(kq["text"])
    print(f"\n({kq['khung']} · {kq['so_tin']} tin · {kq['model']} · {kq['in_tok']}+{kq['out_tok']} token)")


if __name__ == "__main__":
    main()
