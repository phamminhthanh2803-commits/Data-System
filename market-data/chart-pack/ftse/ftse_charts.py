# -*- coding: utf-8 -*-
"""Bieu do dong von FTSE du kien vao Viet Nam (so lieu tong hop 16/09/2026).
Bang mau bao cao: cam #ED7D31, cam nhat #F4B183, den #262626, xam #A6A6A6/#BFBFBF.
Chay: python ftse_charts.py -> 4 file PNG + FTSE_dong_von.xlsx trong cung thu muc.
"""
import os

import altair as alt
import pandas as pd
import vl_convert as vlc

OUT = os.path.dirname(os.path.abspath(__file__))
VI = {"decimal": ",", "thousands": ".", "grouping": [3]}
CAM, CAM2, DEN, XAM, XAM2 = "#ED7D31", "#F4B183", "#262626", "#A6A6A6", "#BFBFBF"
FX = 26_180                       # VND/USD (VCB ban 16/09/2026) de quy doi
GTGD_BQ = 17_984                  # ty VND, binh quan 20 phien (app / indices-master)
KN_BAN_12T = 142_252              # ty VND, khoi ngoai ban rong luy ke 12 thang


def luu(ch, ten, w=760, h=340):
    ch = (ch.properties(width=w, height=h, background="#ffffff")
            .configure_view(strokeWidth=0)
            .configure_axis(labelColor="#595959", titleColor="#595959", gridColor="#D9D9D9",
                            domainColor="#D9D9D9", tickColor="#D9D9D9", labelFontSize=12,
                            titleFontSize=12, titleFontWeight="normal")
            .configure_legend(labelColor="#595959", labelFontSize=12, orient="bottom",
                              symbolType="square")
            .configure_title(color=DEN, fontSize=15, anchor="start", subtitleColor="#7F7F7F",
                             subtitleFontSize=12))
    p = os.path.join(OUT, ten + ".png")
    open(p, "wb").write(vlc.vegalite_to_png(ch.to_dict(), scale=2, format_locale=VI))
    return p


# ------------------------------------------------ 1. LO TRINH 4 DOT (Vietcap)
TONG = 78_900
dot = pd.DataFrame({
    "Đợt": ["Đợt 1\n18/09/2026", "Đợt 2\n19/03/2027", "Đợt 3\n18/06/2027", "Đợt 4\n17/09/2027"],
    "Tỷ lệ": [0.10, 0.20, 0.35, 0.35]})
dot["Giải ngân (tỷ đồng)"] = dot["Tỷ lệ"] * TONG
dot["Luỹ kế (tỷ đồng)"] = dot["Giải ngân (tỷ đồng)"].cumsum()
dot["Nhãn"] = dot["Giải ngân (tỷ đồng)"].map(lambda v: f"{v:,.0f}".replace(",", "."))
dot["Nhãn LK"] = dot["Luỹ kế (tỷ đồng)"].map(lambda v: f"{v:,.0f}".replace(",", "."))
dot["Đợt1"] = dot["Đợt"].str.replace("\n", " · ")
x = alt.X("Đợt1:N", sort=None, title=None, axis=alt.Axis(labelAngle=0))
y = alt.Y("Giải ngân (tỷ đồng):Q", title="tỷ đồng", axis=alt.Axis(format=",.0f"),
          scale=alt.Scale(domain=[0, 85_000]))
cot = alt.Chart(dot).mark_bar(size=70, color=XAM2).encode(x=x, y=y)
nhan = alt.Chart(dot).mark_text(dy=-10, fontSize=13, color=DEN).encode(
    x=x, y="Giải ngân (tỷ đồng):Q", text="Nhãn")
dg = alt.Chart(dot).mark_line(color=CAM, strokeWidth=2.5, point=alt.OverlayMarkDef(
    color=CAM, size=70)).encode(x=x, y="Luỹ kế (tỷ đồng):Q")
nhan2 = alt.Chart(dot.iloc[1:]).mark_text(dy=-14, fontSize=13, color=CAM, fontWeight="bold").encode(
    x=x, y="Luỹ kế (tỷ đồng):Q", text="Nhãn LK")
p1 = luu(alt.layer(cot, nhan, dg, nhan2).properties(title=alt.TitleParams(
    "Lộ trình giải ngân vốn thụ động FTSE vào Việt Nam",
    subtitle="Cột xám: giải ngân từng đợt · đường cam: luỹ kế · tổng 78.900 tỷ đồng (Vietcap, 23/08/2026)")),
    "1_lo_trinh_4_dot")

# ------------------------------------------- 2. SO SANH DU BAO CAC CTCK (ty USD)
db = pd.DataFrame([
    ("MBS", 1.50, 1.50, "T8/2026"),
    ("BSC", 1.40, 2.00, "T8/2026"),
    ("ACBS", 1.71, 1.71, "T4/2026 · rổ cũ"),
    ("VDSC", 2.10, 2.10, "T8/2026 · một số ETF"),
    ("SSI", 2.21, 4.28, "T8/2026"),
    ("Vietcap", round(TONG * 1e9 / FX / 1e9, 2), round(TONG * 1e9 / FX / 1e9, 2), "23/08/2026"),
    ("Bloomberg", 3.00, 3.00, "24/08/2026"),
], columns=["Nguồn", "Cơ sở", "Lạc quan", "Thời điểm"])
db["Tên"] = db["Nguồn"] + " (" + db["Thời điểm"] + ")"
db["Nhãn"] = db.apply(lambda r: (f"{r['Cơ sở']:.2f}".replace(".", ",") if r["Cơ sở"] == r["Lạc quan"]
                                 else f"{r['Cơ sở']:.2f} – {r['Lạc quan']:.2f}".replace(".", ",")), axis=1)
thu_tu = list(db.sort_values("Cơ sở").Tên)
yy = alt.Y("Tên:N", sort=thu_tu[::-1], title=None)
nen = alt.Chart(db).mark_bar(color=CAM2, height=18).encode(
    y=yy, x=alt.X("Lạc quan:Q", title="tỷ USD (vốn thụ động, khi giải ngân đủ 100%)",
                  scale=alt.Scale(domain=[0, 4.8]),
                  axis=alt.Axis(format=",.1f", values=[0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5])))
coso = alt.Chart(db).mark_bar(color=CAM, height=18).encode(y=yy, x="Cơ sở:Q")
nh = alt.Chart(db).mark_text(align="left", dx=6, fontSize=12, color=DEN).encode(
    y=yy, x="Lạc quan:Q", text="Nhãn")
tb = db["Cơ sở"].median()
vach = alt.Chart(pd.DataFrame({"x": [tb]})).mark_rule(color=DEN, strokeDash=[4, 4]).encode(x="x:Q")
p2 = luu(alt.layer(nen, coso, nh, vach).properties(title=alt.TitleParams(
    "Dự báo dòng vốn thụ động FTSE vào Việt Nam theo từng nguồn",
    subtitle=f"Cam đậm: kịch bản cơ sở · cam nhạt: lạc quan · vạch đứt: trung vị {tb:.2f} tỷ USD · "
             f"MBS: gồm cả quỹ chủ động ~6 tỷ USD/1 năm".replace(".", ","))),
    "2_du_bao_cac_ctck", h=300)

# ------------------------------- 3. DAT CANH THANH KHOAN & KHOI NGOAI (ty dong)
ss = pd.DataFrame([
    ("GTGD bình quân 1 phiên", GTGD_BQ, "tham chiếu"),
    ("FTSE đợt 1 (10%)", TONG * 0.10, "ftse"),
    ("FTSE đủ 4 đợt (100%)", TONG, "ftse"),
    ("Khối ngoại bán ròng 12 tháng", KN_BAN_12T, "kn"),
], columns=["Mục", "Tỷ đồng", "Nhóm"])
ss["Nhãn"] = ss["Tỷ đồng"].map(lambda v: f"{v:,.0f}".replace(",", "."))
ss["Phiên"] = (ss["Tỷ đồng"] / GTGD_BQ).map(lambda v: f"≈ {v:.1f} phiên".replace(".", ","))
mau = alt.Scale(domain=["tham chiếu", "ftse", "kn"], range=[XAM, CAM, DEN])
xx = alt.X("Mục:N", sort=None, title=None, axis=alt.Axis(labelAngle=0, labelLimit=200))
c3 = alt.Chart(ss).mark_bar(size=80).encode(
    x=xx, y=alt.Y("Tỷ đồng:Q", title="tỷ đồng", axis=alt.Axis(format=",.0f")),
    color=alt.Color("Nhóm:N", scale=mau, legend=None))
t3 = alt.Chart(ss).mark_text(dy=-22, fontSize=13, color=DEN, fontWeight="bold").encode(
    x=xx, y="Tỷ đồng:Q", text="Nhãn")
t3b = alt.Chart(ss).mark_text(dy=-8, fontSize=11, color="#7F7F7F").encode(
    x=xx, y="Tỷ đồng:Q", text="Phiên")
p3 = luu(alt.layer(c3, t3, t3b).properties(title=alt.TitleParams(
    "Quy mô dòng vốn FTSE so với thanh khoản và lượng khối ngoại đã bán",
    subtitle="Nhãn xám: quy đổi ra số phiên giá trị giao dịch bình quân (17.984 tỷ/phiên, 20 phiên gần nhất)")),
    "3_so_voi_thanh_khoan")

# -------------------------- 4. DOT 1 THEO MA: gia tri & so phien thanh khoan
# gia tri dot 1 theo ACBS (USD trieu, ro thang 4) - chi giu ma CON trong ro chot 21/08
acbs = {"VIC": 56.2, "VHM": 20.4, "MSN": 10.4, "HPG": 9.0, "VNM": 8.2, "VCB": 7.5, "SSI": 7.3,
        "VIX": 5.9, "VJC": 3.5, "VRE": 3.5, "VCI": 3.4, "FPT": 3.2, "STB": 3.2, "SHB": 3.1,
        "VND": 2.8, "GEX": 2.3, "NVL": 2.2, "BID": 1.8}
# gia tri giao dich binh quan 20 phien (ty dong, close x KL tu tv-history.csv)
adv = {"BID": 132, "FPT": 540, "GEX": 308, "HPG": 441, "MSN": 306, "NVL": 166, "SHB": 624,
       "SSI": 471, "STB": 467, "VCB": 304, "VCI": 233, "VHM": 654, "VIC": 1421, "VIX": 666,
       "VJC": 287, "VND": 192, "VNM": 209, "VRE": 140}
mm = pd.DataFrame({"Mã": list(acbs), "Đợt 1 (triệu USD)": list(acbs.values())})
mm["Đợt 1 (tỷ đồng)"] = mm["Đợt 1 (triệu USD)"] * FX / 1000
mm["GTGD BQ 20 phiên (tỷ đồng)"] = mm["Mã"].map(adv)
mm["% GTGD 1 phiên"] = mm["Đợt 1 (tỷ đồng)"] / mm["GTGD BQ 20 phiên (tỷ đồng)"] * 100
mm["Nhãn"] = mm["Đợt 1 (tỷ đồng)"].map(lambda v: f"{v:,.0f}".replace(",", "."))
mm["Nhãn %"] = mm["% GTGD 1 phiên"].map(lambda v: f"{v:.0f}%")
yo = alt.Y("Mã:N", sort="-x", title=None)
c4 = alt.Chart(mm).mark_bar(color=CAM, height=14).encode(
    y=yo, x=alt.X("Đợt 1 (tỷ đồng):Q", title="tỷ đồng giải ngân đợt 1",
                  axis=alt.Axis(format=",.0f"), scale=alt.Scale(domain=[0, 1700])))
t4 = alt.Chart(mm).mark_text(align="left", dx=5, fontSize=11, color=DEN).encode(
    y=yo, x="Đợt 1 (tỷ đồng):Q", text="Nhãn")
trai = alt.Chart(mm).mark_bar(color=DEN, height=14).encode(
    y=alt.Y("Mã:N", sort=alt.EncodingSortField("Đợt 1 (tỷ đồng)", order="descending"), title=None,
            axis=None),
    x=alt.X("% GTGD 1 phiên:Q", title="% GTGD bình quân 1 phiên", scale=alt.Scale(domain=[0, 170]),
            axis=alt.Axis(format=",.0f")))
t4b = alt.Chart(mm).mark_text(align="left", dx=5, fontSize=11, color=DEN).encode(
    y=alt.Y("Mã:N", sort=alt.EncodingSortField("Đợt 1 (tỷ đồng)", order="descending"), axis=None),
    x="% GTGD 1 phiên:Q", text="Nhãn %")
# hconcat khong nhan width/height tong -> luu rieng
ch4 = (alt.hconcat(alt.layer(c4, t4).properties(width=400, height=420),
                   alt.layer(trai, t4b).properties(width=300, height=420))
       .properties(background="#ffffff", title=alt.TitleParams(
           "Đợt 1 theo mã: bao nhiêu tiền và bằng bao nhiêu phần thanh khoản 1 phiên",
           subtitle="Giá trị đợt 1 theo ACBS (rổ T4, chỉ giữ mã còn trong rổ chốt 21/08) · "
                    "GTGD = close×KL bình quân 20 phiên đến 15/09/2026"))
       .configure_view(strokeWidth=0)
       .configure_axis(labelColor="#595959", titleColor="#595959", gridColor="#D9D9D9",
                       domainColor="#D9D9D9", tickColor="#D9D9D9", labelFontSize=12,
                       titleFontSize=12, titleFontWeight="normal")
       .configure_title(color=DEN, fontSize=15, anchor="start", subtitleColor="#7F7F7F",
                        subtitleFontSize=12))
p4 = os.path.join(OUT, "4_dot1_theo_ma.png")
open(p4, "wb").write(vlc.vegalite_to_png(ch4.to_dict(), scale=2, format_locale=VI))

# --------------------------------------------------------------- DU LIEU
with pd.ExcelWriter(os.path.join(OUT, "FTSE_dong_von.xlsx"), engine="openpyxl") as xw:
    dot.drop(columns=["Nhãn", "Nhãn LK", "Đợt1"]).to_excel(xw, sheet_name="Lo_trinh_4_dot", index=False)
    db.drop(columns=["Tên", "Nhãn"]).to_excel(xw, sheet_name="Du_bao_CTCK", index=False)
    ss.drop(columns=["Nhãn", "Phiên"]).to_excel(xw, sheet_name="So_voi_thanh_khoan", index=False)
    mm.drop(columns=["Nhãn", "Nhãn %"]).round(1).sort_values("Đợt 1 (tỷ đồng)", ascending=False) \
      .to_excel(xw, sheet_name="Dot1_theo_ma", index=False)
print("XONG:", p1, p2, p3, p4)
print(mm.sort_values("Đợt 1 (tỷ đồng)", ascending=False).round(0).to_string(index=False))
