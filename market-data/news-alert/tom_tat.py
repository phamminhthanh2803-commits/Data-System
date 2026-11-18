# -*- coding: utf-8 -*-
r"""tom_tat.py - Claude Sonnet tom tat DIEN BIEN HOM NAY cua tin watchlist (18/11/2026).

Goi tu app (Tin tuc › Watchlist, nut "Tom tat hom nay") hoac CLI:
    python tom_tat.py                  tom tat tin hom nay khop watchlist (kho tin cua app, fallback kho news-alert)
    python tom_tat.py --ngay 2026-11-17

Ket qua luu tom_tat\<ngay>.md + .json (thoi diem, so tin, model, token) -> app hien lai khong goi API lan nua.
Can API key Anthropic: bien moi truong User ANTHROPIC_API_KEY (SDK tu doc). Chi phi ~ vai trang/lan (Sonnet 5.5: $2/$10 moi 1M token).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")   # Streamlit Cloud chay gio UTC -> moi moc thoi gian theo gio VN

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "tom_tat")
MODEL = "claude-sonnet-5-5"          # PV2 chon Sonnet
MAX_BAI = 150                         # du cho 1 ngay watchlist; nhieu hon -> giu bai diem chu y cao

SYSTEM = """Bạn là chuyên viên phân tích chứng khoán Việt Nam, viết bản tóm tắt tin trong ngày cho nhà đầu tư theo dõi một danh sách mã.

Quy tắc:
- Chỉ dựa vào các tin được cung cấp (tiêu đề + tóm tắt RSS). Không thêm số liệu, sự kiện hay giá cổ phiếu không có trong tin.
- Gom theo từng mã (theo thứ tự danh sách theo dõi), bỏ qua mã không có tin. Tin trùng nhau giữa các báo chỉ kể một lần.
- Mỗi mã: 1 dòng "Điểm chính" rồi 2-5 gạch đầu dòng diễn biến theo thứ tự thời gian, ghi giờ và số tin nguồn dạng [3].
  Cuối mỗi mã 1 dòng "Ý nghĩa:" nêu tác động có thể tới doanh nghiệp/cổ phiếu (tích cực / tiêu cực / trung tính) và lý do ngắn.
  Nếu tin chỉ nhắc mã thoáng qua (bài tổng hợp thị trường) thì nói rõ là nhắc phụ, không suy diễn.
- Mở đầu bằng 2-3 câu "Toàn cảnh hôm nay" nối các mã nếu có chủ đề chung; kết bằng mục "Cần theo dõi" (sự kiện sắp tới được nhắc trong tin).
- Viết tiếng Việt, Markdown gọn (### cho từng mã), không quá ~600 từ."""


def _bai_hom_nay(ngay: str, kho: list[str] | None = None) -> tuple[list[dict], list[str]]:
    """Tin khop watchlist trong ngay `ngay` (YYYY-MM-DD): kho app (90 ngay, du nhat) + kho news-alert, bo trung."""
    import pandas as pd
    sys.path.insert(0, BASE)
    import news_alert as na
    wl = na.doc_watchlist()
    mas = [x["ma"] for x in wl]
    # 18/11: app truyen kho cua chinh no (Streamlit Cloud: dl.CACHE khong nam o <market-data>/app/cache) + kho news-alert (Actions)
    kho = list(kho or []) + [os.path.join(os.path.dirname(BASE), "app", "cache", "news-rss", "news_tagged.parquet"),
                             os.path.join(BASE, "kho", "news_tagged.parquet")]
    co = [p for p in dict.fromkeys(os.path.normpath(x) for x in kho) if os.path.exists(p)]
    if not co:
        raise RuntimeError("Không tìm thấy kho tin RSS (news_tagged.parquet) — mở trang Tin theo ngành / bấm ↻ Kéo tin mới trước")
    t = pd.concat([pd.read_parquet(p) for p in co], ignore_index=True)
    t = t.drop_duplicates("id")
    d0 = pd.Timestamp(ngay)
    t = t[(t["ngay_gio"] >= d0) & (t["ngay_gio"] < d0 + pd.Timedelta(days=1))]
    m = na.khop(t, wl) if len(t) else t
    if m.empty:
        return [], mas
    m = m.sort_values("ngay_gio").drop_duplicates("nhom_trung", keep="first")
    if len(m) > MAX_BAI:
        m = m.sort_values(["diem_chu_y", "ngay_gio"], ascending=False).head(MAX_BAI).sort_values("ngay_gio")
    return m.to_dict("records"), mas


def tom_tat(ngay: str | None = None, kho: list[str] | None = None) -> dict:
    """Goi Sonnet tom tat tin watchlist ngay `ngay`. Tra dict {text, so_tin, model, luc, in_tok, out_tok}; luu tom_tat\\<ngay>.md/.json.
    Loi -> RuntimeError voi thong bao tieng Viet."""
    import anthropic
    ngay = ngay or datetime.now(VN).strftime("%Y-%m-%d")
    bai, mas = _bai_hom_nay(ngay, kho)
    if not bai:
        raise RuntimeError(f"Không có tin nào khớp watchlist ngày {ngay}")
    dong = []
    for i, b in enumerate(bai, 1):
        tt = str(b.get("tom_tat") or "").strip()
        sn = int(b.get("so_nguon") or 1)
        dong.append(f"[{i}] {b['ngay_gio']:%H:%M} · {b['nguon']}{f' (+{sn - 1} báo khác)' if sn > 1 else ''} · mã: "
                    f"{b['ma_wl'].replace('|', ', ')}\nTiêu đề: {b['tieu_de']}\nTóm tắt: {tt}")
    user = (f"Danh sách theo dõi: {', '.join(mas)}\nNgày: {ngay}\n\n{len(bai)} tin (đã gộp tin trùng):\n\n" + "\n\n".join(dong))
    try:
        client = anthropic.Anthropic()
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=8000,
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
    nguon = "\n".join(f"{i}. [{b['nguon']} · {b['ngay_gio']:%H:%M}] [{b['tieu_de']}]({b['url']})" for i, b in enumerate(bai, 1))
    kq = {"ngay": ngay, "luc": datetime.now(VN).replace(tzinfo=None).isoformat(timespec="seconds"), "so_tin": len(bai), "model": resp.model,
          "in_tok": resp.usage.input_tokens, "out_tok": resp.usage.output_tokens, "ma": mas,
          "text": text, "nguon": nguon}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"{ngay}.md"), "w", encoding="utf-8") as f:
        f.write(f"# Tóm tắt tin watchlist {ngay} ({kq['luc'][11:16]})\n\n{text}\n\n---\n**Nguồn**\n\n{nguon}\n")
    with open(os.path.join(OUT, f"{ngay}.json"), "w", encoding="utf-8") as f:
        json.dump(kq, f, ensure_ascii=False, indent=1)
    import news_alert as na                                   # len Drive -> app online / laptop doc chung
    na.day_len(os.path.join("tom_tat", f"{ngay}.md"), os.path.join("tom_tat", f"{ngay}.json"))
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


def doc_ban_cu(ngay: str) -> dict | None:
    p = os.path.join(OUT, f"{ngay}.json")
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
    ap.add_argument("--ngay", default=None)
    a = ap.parse_args()
    try:
        kq = tom_tat(a.ngay)
    except RuntimeError as e:
        print(f"X {e}")
        sys.exit(2)
    print(kq["text"])
    print(f"\n({kq['so_tin']} tin · {kq['model']} · {kq['in_tok']}+{kq['out_tok']} token)")


if __name__ == "__main__":
    main()
