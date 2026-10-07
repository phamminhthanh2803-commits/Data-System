"""Streamlit app: vessel route visualization.

Workflow:
  1. Upload CSV/Excel with columns: Month, Region, Source (Source optional).
  2. App resolves each region to a representative port (catalog) — user can
     override port choice or type custom lon/lat.
  3. Renders Pacific-centred map + timeline → 300 DPI PNG.
"""
from __future__ import annotations

import io
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from ports import PORTS, REGION_TO_PORTS_BY_VESSEL, VESSEL_TYPES, VESSEL_TYPE_LABELS, resolve_port
from route import Waypoint, render

st.set_page_config(page_title="Vessel Route Visualizer", layout="wide")

st.title("Vessel Route Visualizer")
st.caption("Upload bảng vùng biển theo tháng → app dựng tuyến hải trình thật + timeline → PNG 300 DPI.")

# ---------- sample data download ----------
SAMPLE = pd.DataFrame([
    {"Month": "Dec 2016", "Region": "Australia / New Guinea Pacific",  "Source": "MarineTraffic"},
    {"Month": "Jan 2017", "Region": "East Asia / SE Asia / Australia", "Source": "Both"},
    {"Month": "Feb 2017", "Region": "East Asia / SE Asia",             "Source": "Both"},
    {"Month": "Mar 2017", "Region": "East Asia / SE Asia",             "Source": "VesselTracker"},
    {"Month": "Apr 2017", "Region": "East Asia -> NA West Coast",      "Source": "MarineTraffic"},
    {"Month": "May 2017", "Region": "North America West Coast",        "Source": "Both"},
    {"Month": "Jun 2017", "Region": "North America West Coast",        "Source": "Both"},
    {"Month": "Jul 2017", "Region": "Gulf of Mexico / Middle America", "Source": "MarineTraffic"},
])

with st.sidebar:
    st.header("Loại tàu")
    vessel_type = st.selectbox(
        "Chọn loại tàu (quyết định catalog cảng đại diện)",
        options=VESSEL_TYPES,
        format_func=lambda v: VESSEL_TYPE_LABELS[v],
        index=0,
        key="vessel_type",
    )
    st.caption({
        "crude":     "Cảng dầu thô: Ras Tanura, Bonny, Houston/LOOP, Ningbo, Sikka…",
        "chemical":  "Hub hóa chất/sản phẩm: Antwerp, Map Ta Phut, Ulsan, Jubail, Houston…",
        "gas":       "Terminal LNG/LPG: Ras Laffan, Sabine Pass, Gladstone LNG, Sodegaura, Zeebrugge…",
        "container": "Mega-hub container: Shanghai, Singapore, Rotterdam, LA/LB, Jebel Ali, Algeciras…",
        "general":   "Dùng catalog crude làm fallback.",
    }[vessel_type])

    st.divider()
    st.header("Hướng dẫn")
    st.markdown(
        "**Format file:**\n"
        "- `Month` — vd `Dec 2016`\n"
        "- `Region` — chuỗi vùng biển (trùng key trong catalog càng tốt)\n"
        "- `Source` — *optional*, vd `MarineTraffic` / `VesselTracker` / `Both`\n\n"
        "Sau khi upload, bạn có thể override cảng đại diện cho từng tháng."
    )
    st.download_button(
        "Tải sample CSV",
        SAMPLE.to_csv(index=False).encode("utf-8"),
        file_name="vessel_sample.csv",
        mime="text/csv",
    )
    with st.expander("Catalog vùng cho loại tàu hiện tại"):
        st.write(sorted(REGION_TO_PORTS_BY_VESSEL[vessel_type].keys()))

# ---------- file upload ----------
uploaded = st.file_uploader("Upload CSV hoặc Excel", type=["csv", "xlsx", "xls"])

if uploaded is None:
    st.info("Tải file lên hoặc dùng sample CSV ở sidebar để bắt đầu.")
    if st.checkbox("Dùng tạm sample data"):
        df_raw = SAMPLE.copy()
    else:
        st.stop()
else:
    suffix = Path(uploaded.name).suffix.lower()
    if suffix == ".csv":
        df_raw = pd.read_csv(uploaded)
    else:
        df_raw = pd.read_excel(uploaded)

# ---------- normalize columns ----------
cols = {c.lower().strip(): c for c in df_raw.columns}
required = {"month", "region"}
missing = required - cols.keys()
if missing:
    st.error(f"Thiếu cột bắt buộc: {missing}. Cần ít nhất Month + Region.")
    st.stop()

df = pd.DataFrame({
    "Month": df_raw[cols["month"]].astype(str).str.strip(),
    "Region": df_raw[cols["region"]].astype(str).str.strip(),
    "Source": df_raw[cols["source"]].astype(str).str.strip() if "source" in cols else "",
})

# ---------- time-range filter ----------
def _parse_month(s: str):
    """Try a few formats: 'Dec 2016', 'December 2016', '12/2016', '2016-12', 'Dec-16'."""
    s = str(s).strip()
    for fmt in ("%b %Y", "%B %Y", "%m/%Y", "%Y-%m", "%Y/%m", "%b-%y", "%b %y", "%Y-%m-%d"):
        try:
            return pd.to_datetime(s, format=fmt)
        except (ValueError, TypeError):
            continue
    try:
        return pd.to_datetime(s)
    except (ValueError, TypeError):
        return pd.NaT

df["_date"] = df["Month"].apply(_parse_month)
parse_failures = df["_date"].isna().sum()

st.subheader("Giới hạn khung thời gian")
if parse_failures == len(df):
    st.warning("Không parse được cột Month sang ngày tháng → bỏ qua filter, dùng toàn bộ file.")
    df_filtered = df.drop(columns=["_date"]).reset_index(drop=True)
else:
    if parse_failures:
        st.caption(f"⚠️ {parse_failures}/{len(df)} dòng có Month không parse được — sẽ giữ nguyên, không bị filter.")

    valid_dates = df["_date"].dropna()
    min_d, max_d = valid_dates.min().to_pydatetime(), valid_dates.max().to_pydatetime()

    months_list = sorted(valid_dates.dt.to_period("M").unique())
    month_labels = [p.strftime("%b %Y") for p in months_list]

    if len(month_labels) == 1:
        st.caption(f"File chỉ có 1 tháng: {month_labels[0]} — không cần filter.")
        df_filtered = df.drop(columns=["_date"]).reset_index(drop=True)
    else:
        start_idx, end_idx = st.select_slider(
            f"Chọn khoảng tháng (full range: {month_labels[0]} → {month_labels[-1]}, {len(month_labels)} tháng)",
            options=list(range(len(month_labels))),
            value=(0, len(month_labels) - 1),
            format_func=lambda i: month_labels[i],
        )
        start_period = months_list[start_idx]
        end_period = months_list[end_idx]
        start_ts = start_period.to_timestamp()
        end_ts = (end_period + 1).to_timestamp() - pd.Timedelta(days=1)
        mask = (df["_date"].between(start_ts, end_ts)) | df["_date"].isna()
        df_filtered = df.loc[mask].drop(columns=["_date"]).reset_index(drop=True)
        st.caption(
            f"📊 Đang dùng **{len(df_filtered)}/{len(df)}** dòng "
            f"({month_labels[start_idx]} → {month_labels[end_idx]})."
        )

df = df_filtered
if len(df) == 0:
    st.error("Không còn dòng nào sau khi filter. Mở rộng khoảng tháng.")
    st.stop()

# ---------- resolve ports ----------
port_options = sorted(PORTS.keys()) + ["(Custom lon/lat)"]

resolved = []
unrecognized = []
for _, row in df.iterrows():
    hit = resolve_port(row["Region"], vessel_type=vessel_type)
    if hit:
        port, lon, lat = hit
    else:
        # unknown region — let user pick
        port, lon, lat = "(Custom lon/lat)", 0.0, 0.0
        unrecognized.append(row["Region"])
    resolved.append({"Month": row["Month"], "Region": row["Region"], "Source": row["Source"],
                     "Port": port, "Lon": lon, "Lat": lat})

df_resolved = pd.DataFrame(resolved)

st.subheader("Waypoints (chỉnh được)")
total_rows = len(df_resolved)
ok_rows = sum(1 for r in resolved if r["Port"] != "(Custom lon/lat)")
st.caption(
    f"📂 File có **{total_rows} dòng**. Đã nhận diện cảng cho **{ok_rows}/{total_rows}** dòng "
    f"(loại tàu: **{VESSEL_TYPE_LABELS[vessel_type]}**). "
    "Cảng đại diện do app đoán từ Region — override Port dropdown hoặc chọn `(Custom lon/lat)` rồi điền lon/lat tay."
)
if unrecognized:
    uniq = sorted(set(unrecognized))
    with st.expander(f"⚠️ {len(unrecognized)} dòng có Region không khớp catalog ({len(uniq)} giá trị khác nhau) — click để xem & xử lý", expanded=True):
        st.write("Các giá trị Region chưa nhận diện được (sẽ bị BỎ QUA khi vẽ nếu không điền lon/lat):")
        for v in uniq:
            st.code(v, language=None)
        st.markdown(
            "**Cách xử lý:**\n"
            "1. Trong bảng dưới, các dòng này có `Port = (Custom lon/lat)` và `Lon=0, Lat=0`.\n"
            "2. Click ô `Port` của dòng → chọn cảng phù hợp trong dropdown → app sẽ tự sync lon/lat từ catalog.\n"
            "3. Hoặc giữ `(Custom lon/lat)` và gõ tay lon/lat vào 2 cột bên phải.\n"
            "4. Nếu muốn app auto-resolve các Region này lần sau → mở `ports.py` thêm vào `REGION_TO_PORTS` hoặc `KEYWORD_FALLBACK`."
        )

edited = st.data_editor(
    df_resolved,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Port": st.column_config.SelectboxColumn(options=port_options, required=True),
        "Lon": st.column_config.NumberColumn(format="%.3f", min_value=-180.0, max_value=180.0),
        "Lat": st.column_config.NumberColumn(format="%.3f", min_value=-90.0, max_value=90.0),
    },
    hide_index=True,
    key="waypoints_editor",
)

# Sync Lon/Lat from catalog when user changed Port (but not custom).
# Refresh whenever current lon/lat doesn't match the catalog entry for the selected port
# AND the selected port differs from the originally-resolved one — this catches the
# "user changed Port dropdown but Lon/Lat stayed at the old catalog values" case
# without overwriting deliberate custom coordinates the user typed.
def _sync(idx_row):
    idx, row = idx_row
    if row["Port"] in PORTS:
        target_lon, target_lat = PORTS[row["Port"]]
        original_port = df_resolved.iloc[idx]["Port"] if idx < len(df_resolved) else None
        if row["Port"] != original_port:
            row["Lon"], row["Lat"] = target_lon, target_lat
        elif abs(row["Lon"]) < 0.01 and abs(row["Lat"]) < 0.01:
            row["Lon"], row["Lat"] = target_lon, target_lat
    return row

edited = pd.DataFrame([_sync((i, r)) for i, r in enumerate(edited.to_dict("records"))])

# ---------- render ----------
title = st.text_input("Tiêu đề map", "Hành trình tàu — Dec 2016 → Jul 2017")

col1, col2 = st.columns([1, 4])
go = col1.button("Vẽ tuyến", type="primary")

if go:
    try:
        wps = []
        dropped = []
        for r in edited.itertuples(index=False):
            is_custom_unset = str(r.Port) == "(Custom lon/lat)" and r.Lon == 0 and r.Lat == 0
            if is_custom_unset:
                dropped.append(f"{r.Month} / {r.Region}")
                continue
            wps.append(Waypoint(
                month=str(r.Month),
                region=str(r.Region),
                source=str(r.Source) if pd.notna(r.Source) else "",
                port=str(r.Port),
                lon=float(r.Lon),
                lat=float(r.Lat),
            ))

        if dropped:
            with st.expander(f"ℹ️ Đã bỏ qua {len(dropped)} dòng (Port=Custom nhưng Lon/Lat chưa điền)", expanded=False):
                for d in dropped:
                    st.text(f"  • {d}")

        st.info(f"Render với **{len(wps)}/{len(edited)}** waypoints.")

        if len(wps) < 2:
            st.error("Cần tối thiểu 2 waypoint hợp lệ. Mở expander ⚠️ ở trên để điền lon/lat cho các dòng chưa nhận diện được.")
            st.stop()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            out_path = tmp.name

        with st.spinner("Đang tính tuyến biển và vẽ map..."):
            meta = render(wps, out_path, title=title)

        st.success(f"Xong — tổng quãng đường ước tính: **{meta['total_nm']:.0f} hải lý**.")
        st.image(out_path, caption="Preview (downscaled). Tải PNG 300 DPI bên dưới.", use_container_width=True)
        with open(out_path, "rb") as f:
            st.download_button(
                "Tải PNG 300 DPI",
                f.read(),
                file_name="vessel_route.png",
                mime="image/png",
            )

        with st.expander("Chi tiết từng chặng"):
            st.dataframe(pd.DataFrame(meta["legs"]), hide_index=True, use_container_width=True)

    except Exception as exc:
        st.exception(exc)
