# -*- coding: utf-8 -*-
"""Sinh transmission-dashboard.html tu transmission-master.csv.

Bo cuc 5 khoi theo mach doc cua Phong Dau tu:
  B1 Ap luc ty gia -> B2 Tu ty gia len chi phi von -> B3 Can doi va cung tien
  -> B4 Rang buoc ty le noi sinh -> B5 Du dia tien te

Chay lai sau moi lan fetch_all.py de dashboard co so moi:
    python make_dashboard.py
roi publish lai file transmission-dashboard.html.
"""
import datetime as dt
import json
import os

import pandas as pd

import sources_map as SM

ROOT = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(ROOT, "transmission-master.csv")
NODES = os.path.join(ROOT, "transmission-nodes.csv")
TPL = os.path.join(ROOT, "dashboard.tpl.html")
OUT = os.path.join(ROOT, "transmission-dashboard.html")
DAILY_FROM = "2021-01-01"

# ---------------------------------------------------------------- bo cuc
S1, S2, S3 = "var(--s1)", "var(--s2)", "var(--s3)"

BLOCKS = [
    dict(id="b1", no="01", name="Áp lực tỷ giá",
         lead="Áp lực bắt đầu từ giá vốn USD và cán cân ngoại tệ, hiện ra ở khoảng cách giữa "
              "giá bán của ngân hàng và trần biên độ. Chạm trần là lúc NHNN buộc phải hành động.",
         tiles=["fx_central", "fx_band_ceiling", "fx_vcb_sell", "fx_vcb_sell_vs_ceiling",
                "fx_free_sell", "fx_free_vs_vcb", "fx_sbv_sell_ref", "fx_reserves",
                "fx_import_cover", "us_sofr", "us_dxy_broad", "trade_balance", "fii_net_val",
                "fdi_inflow_bop", "fdi_realized_vnd", "current_account_bop", "bop_errors", "bop_overall"],
         charts=[
             dict(title="Giá bán USD so với trần biên độ", sub="VND/USD", big=True, dec=0,
                  series=[("fx_vcb_sell", "Vietcombank bán", S1),
                          ("fx_free_sell", "Chợ đen bán", S2),
                          ("fx_band_ceiling", "Trần biên độ +5%", S3)]),
             dict(title="Khoảng cách còn lại tới trần", sub="âm = giá bán còn thấp hơn trần bấy nhiêu %",
                  dec=2, zero=True, area=True,
                  series=[("fx_vcb_sell_vs_ceiling", "VCB bán so với trần", S1)]),
             dict(title="Dự trữ ngoại hối quy ra tháng nhập khẩu", sub="thông lệ dưới 3 tháng là mỏng",
                  dec=2, full=True, area=True, thr=3.0, thrlab="ngưỡng 3 tháng",
                  series=[("fx_import_cover", "Số tháng nhập khẩu", S1)]),
             dict(title="Cán cân thanh toán theo quý", sub="triệu USD; lỗi và sai sót âm kéo dài là dòng vốn chảy ra không ghi nhận được",
                  dec=0, full=True, zero=True,
                  series=[("current_account_bop", "Cán cân vãng lai", S1),
                          ("fdi_net_bop", "FDI ròng", S3),
                          ("bop_errors", "Lỗi và sai sót", S2)]),
         ]),
    dict(id="b2", no="02", name="Từ tỷ giá lên chi phí vốn",
         lead="NHNN hút hoặc bơm VND để giữ tỷ giá; liên ngân hàng phản ứng trước, rồi mới đến "
              "lãi suất huy động và cho vay. Đây là đoạn truyền dẫn giá.",
         tiles=["omo_net_outstanding", "omo_outstanding", "bill_outstanding", "omo_win_7d_rate",
                "policy_refinance", "ib_on", "ib_1m", "ib_3m", "ib_spread_policy",
                "ib_curve_1m_on", "swap_on", "swap_1m", "swap_3m",
                "deposit_12m_big4", "deposit_12m_max", "lending_rate_avg",
                "lending_rate_big4", "lending_rate_jsc", "deposit_rate_avg_vcb", "lending_deposit_spread", "lending_spread_net_vcb"],
         charts=[
             dict(title="Bơm ròng của NHNN đang lưu hành", sub="reverse repo cộng tín phiếu, tỷ đồng",
                  big=True, dec=0, zero=True, area=True,
                  series=[("omo_net_outstanding", "Bơm ròng tồn dư", S1)]),
             dict(title="Đường cong lãi suất liên ngân hàng", sub="lãi suất bình quân theo kỳ hạn, %/năm",
                  dec=2,
                  series=[("ib_on", "Qua đêm", S1), ("ib_1m", "1 tháng", S2),
                          ("ib_3m", "3 tháng", S3)]),
             dict(title="Chênh lãi suất VND trừ USD", sub="âm là điều kiện cho dòng vốn ngoại rút ra",
                  dec=2, zero=True,
                  series=[("swap_on", "Qua đêm", S1), ("swap_1m", "1 tháng", S2),
                          ("swap_3m", "3 tháng", S3)]),
             dict(title="Lãi suất cho vay bình quân từng ngân hàng công bố", sub="%/năm; Big4 và cổ phần là trung bình đơn giản các ngân hàng đã có bộ đọc",
                  dec=2, full=True,
                  series=[("lending_rate_big4", "Nhóm Big4", S1),
                          ("lending_rate_jsc", "Nhóm cổ phần", S2),
                          ("lending_rate_avg", "Vietcombank cho vay", S3)]),
             dict(title="Vietcombank: giá vốn và biên", sub="%/năm; huy động bình quân suy ra từ cho vay trừ chênh lệch",
                  dec=2, full=True,
                  series=[("lending_rate_avg", "Cho vay bình quân", S1),
                          ("deposit_rate_avg_vcb", "Huy động bình quân", S2),
                          ("lending_spread_net_vcb", "Biên sau chi phí", S3)]),
         ]),
    dict(id="b3", no="03", name="Cân đối và cung tiền",
         lead="Tín dụng chạy nhanh hơn huy động thì phần thiếu phải bù bằng vốn liên ngân hàng. "
              "Đây là nguồn gốc cấu trúc của căng thanh khoản, khác với cú sốc nhất thời.",
         tiles=["credit_growth_ytd", "deposit_growth_ytd", "credit_deposit_gap", "m2",
                "m2_growth", "cash_ratio_m2", "deposits_total", "deposits_household",
                "deposits_corporate", "bank_loans", "bank_deposits", "public_inv_month", "public_inv_ytd"],
         charts=[
             dict(title="Tăng trưởng tín dụng và huy động", sub="luỹ kế từ đầu năm, %", dec=2, full=True,
                  series=[("credit_growth_ytd", "Tín dụng", S1),
                          ("deposit_growth_ytd", "Huy động", S2),
                          ("m2_growth", "Cung tiền M2", S3)]),
             dict(title="Chênh tăng trưởng tín dụng trừ huy động", sub="điểm %, dương là phần phải bù bằng vốn TT2",
                  dec=2, zero=True, area=True, full=True,
                  series=[("credit_deposit_gap", "Chênh tín dụng − huy động", S1)]),
         ]),
    dict(id="b4", no="04", name="Ràng buộc tỷ lệ nội sinh",
         lead="Bốn ràng buộc quyết định ngân hàng còn cho vay được bao nhiêu: LDR, tỷ lệ vốn ngắn "
              "hạn cho vay trung dài hạn, hệ số an toàn vốn, và cơ cấu giá vốn qua CASA.",
         tiles=["ldr_system", "ldr_soe", "ldr_jsc", "ldr_tt22_listed", "loan_deposit_listed",
                "sfl_system", "sfl_soe", "sfl_jsc", "car_tt41", "car_tt41_soe", "car_tt41_jsc",
                "car_banks_median", "car_banks_min", "car_banks_n",
                "casa_ratio", "mlt_loan_share", "bank_total_assets", "bank_charter_capital"],
         charts=[
             dict(title="LDR theo Thông tư 22: NHNN so với nhóm niêm yết", sub="%, trần 85%; nhóm niêm yết tính hợp nhất, chưa loại tiền gửi Kho bạc",
                  dec=2, full=True,
                  series=[("ldr_system", "Toàn hệ thống (NHNN)", S1),
                          ("ldr_tt22_listed", "27 NH niêm yết", S2)], thr=85.0, thrlab="trần 85%"),
             dict(title="Cơ cấu kỳ hạn và giá vốn", sub="%, nhóm ngân hàng niêm yết", dec=2, full=True,
                  series=[("mlt_loan_share", "Tỷ trọng cho vay trung dài hạn", S1),
                          ("casa_ratio", "CASA", S2)]),
         ]),
]

# khoi 5 la bang tong hop, khong phai bieu do
HEADROOM = [
    ("fx_vcb_sell_vs_ceiling", "Tỷ giá còn cách trần biên độ", "Trần = tỷ giá trung tâm × 1,05",
     "Về gần 0 là NHNN buộc hút VND hoặc bán ngoại tệ."),
    ("fx_import_cover", "Dự trữ ngoại hối quy ra tháng nhập khẩu", "Thông lệ quốc tế 3 tháng",
     "Càng mỏng thì càng ít đạn để can thiệp kéo dài."),
    ("ib_spread_policy", "Liên ngân hàng qua đêm trừ lãi suất tái cấp vốn", "Mốc 0",
     "Âm là dư thanh khoản ngắn hạn; dương là hệ thống phải gõ cửa NHNN."),
    ("omo_net_outstanding", "Bơm ròng của NHNN đang lưu hành", "Mốc 0",
     "Số dư càng lớn thì hệ thống càng đang sống bằng tiền NHNN."),
    ("ldr_system", "LDR toàn hệ thống", "Trần 85% từ 01/01/2020 (Thông tư 22/2019)",
     "Còn cách trần bao nhiêu là còn bấy nhiêu room cho vay."),
    ("ldr_tt22_listed", "LDR Thông tư 22 của 27 ngân hàng niêm yết", "Trần 85%, số hợp nhất chưa loại Kho bạc",
     "Cao hơn số NHNN vì không có quỹ tín dụng và ngân hàng nước ngoài kéo xuống; sát 85% là nhóm niêm yết hết room."),
    ("sfl_system", "Tỷ lệ vốn ngắn hạn cho vay trung dài hạn",
     "Trần 40% từ 01/07/2026, trước đó 30% (Thông tư 25/2026)",
     "Vừa được nới 10 điểm phần trăm nên dư địa cho vay dài hạn rộng hẳn ra."),
    ("car_banks_min", "CAR thấp nhất trong các ngân hàng có công bố", "Tối thiểu 8%",
     "Ngân hàng yếu nhất còn cách sàn bao nhiêu là toàn hệ thống còn bấy nhiêu chỗ để NHNN siết."),
    ("car_tt41", "Hệ số an toàn vốn nhóm Thông tư 41", "Tối thiểu 8%",
     "Phần vượt 8% là dư địa mở rộng tài sản rủi ro."),
    ("casa_ratio", "CASA nhóm ngân hàng niêm yết", "So với chính nó theo thời gian",
     "Giảm là giá vốn đắt lên ngay cả khi lãi suất niêm yết chưa đổi."),
]

HERO = [
    ("fx_vcb_sell_vs_ceiling", "Giá bán USD của Vietcombank so với trần biên độ"),
    ("ib_spread_policy", "Liên ngân hàng qua đêm trừ lãi suất tái cấp vốn"),
    ("omo_net_outstanding", "Bơm ròng của NHNN đang lưu hành"),
    ("fx_import_cover", "Dự trữ ngoại hối quy ra tháng nhập khẩu"),
]

# trang thai tung khoi: (series, nguong diu, nguong cang, nhan)
STATUS = [
    ("b1", "fx_vcb_sell_vs_ceiling", -2.0, -0.5, ("dịu", "đang căng"), "lt"),
    ("b2", "ib_spread_policy", -0.5, 0.5, ("dịu", "đang căng"), "gt"),
    ("b3", "credit_deposit_gap", 0.0, 3.0, ("cân đối", "lệch nguồn"), "gt"),
    ("b4", "ldr_tt22_listed", 80.0, 84.0, ("còn room", "sát trần"), "gt"),
]


def main():
    d = pd.read_csv(MASTER, dtype={"date": str}, encoding="utf-8-sig")
    nodes = pd.read_csv(NODES, encoding="utf-8-sig")
    meta = nodes.set_index("series_id").to_dict("index")

    wanted = set(HERO and [h[0] for h in HERO])
    for b in BLOCKS:
        wanted |= set(b["tiles"])
        for c in b["charts"]:
            wanted |= {s[0] for s in c["series"]}
            wanted |= {"__thr__"} if c.get("thr") else set()
    wanted |= {h[0] for h in HEADROOM}
    wanted.discard("__thr__")

    S = {}
    for sid in sorted(wanted):
        m = meta.get(sid, {})
        s = d[d.series_id == sid][["date", "value"]].dropna().sort_values("date")
        freq = m.get("freq", "D")
        if freq == "D":
            s = s[s.date >= DAILY_FROM]
        if not len(s):
            continue
        nm, url, formula = SM.source_of(sid, m.get("source", ""))
        S[sid] = dict(n=m.get("series_name", sid), u=m.get("unit", ""), f=freq,
                      src=nm, url=url, fx=formula, st=m.get("status", ""),
                      p=[[r.date, round(float(r.value), 4)] for r in s.itertuples()])

    payload = dict(
        asof=d.date.max(), built=dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        rows=int(len(d)), n_series=int(d.series_id.nunique()),
        with_data=int((nodes.n_obs > 0).sum()), declared=int(len(nodes)),
        manual=nodes[nodes.status == "manual"].series_id.tolist(),
        sources={k: int(v) for k, v in d.source.value_counts().items()},
        blocks=BLOCKS, headroom=HEADROOM, hero=HERO, status=STATUS, S=S,
    )
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    print("series nhung: %d / %d yeu cau | %.0f KB" % (len(S), len(wanted), len(blob) / 1024))
    missing = sorted(wanted - set(S))
    if missing:
        print("chua co du lieu:", ", ".join(missing))

    # bang nguon dung chung cho Excel
    pd.DataFrame([dict(series_id=r.series_id, **dict(zip(
        ("nguon", "url", "cong_thuc"), SM.source_of(r.series_id, r.source))))
        for r in nodes.itertuples()]).to_csv(
        os.path.join(ROOT, "nguon-chi-tieu.csv"), index=False, encoding="utf-8-sig")

    # bo cuc 5 khoi cho Excel doc lai - khai bao mot noi duy nhat o BLOCKS/HEADROOM
    lay = []
    for b in BLOCKS:
        for sid in b["tiles"]:
            lay.append(dict(khoi=b["no"] + " " + b["name"], series_id=sid,
                            nguong="", doc_the_nao=""))
    for sid, lab, ref, read in HEADROOM:
        lay.append(dict(khoi="05 Dư địa tiền tệ", series_id=sid,
                        nguong=ref, doc_the_nao=read))
    pd.DataFrame(lay).to_csv(os.path.join(ROOT, "dashboard-layout.csv"),
                             index=False, encoding="utf-8-sig")

    # Ban HTML da bo (10/09/2026, template chuyen vao _archive/): script nay gio chi xuat hai CSV
    # cho Excel. Muon dung lai HTML thi chep dashboard.tpl.html tu _archive/ ra la tu render.
    if os.path.exists(TPL):
        tpl = open(TPL, encoding="utf-8").read()
        open(OUT, "w", encoding="utf-8").write(
            tpl.replace("/*__DATA__*/", blob.replace("</", "<" + chr(92) + "/")))
        print("transmission-dashboard.html: %.0f KB" % (os.path.getsize(OUT) / 1024))
    else:
        print("nguon-chi-tieu.csv + dashboard-layout.csv xong (khong render HTML)")


if __name__ == "__main__":
    main()
