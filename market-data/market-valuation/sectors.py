# -*- coding: utf-8 -*-
r"""
SECTOR VALUATION — Định giá THEO NGÀNH (ICB) do VNDirect tính sẵn
55 mã ngành ICB (trộn cấp 2 & cấp 3) x 5 chỉ tiêu: P/E, P/B, P/S, Tỷ suất cổ tức,
Vốn hóa — theo NGÀY, lịch sử từ 12/2017 (vốn hóa từ ~07/2019).

Kéo batch tất cả ngành trong 1 request/ratio (code:0500,0530,... , phân trang 1000).
Full lần đầu ~550k dòng; các lần sau incremental chỉ ~5 request.

Chạy:
    python sectors.py           # incremental
    python sectors.py --full    # kéo lại toàn bộ lịch sử

Output:
    sectors-master.csv  long-format: code, date, ratio, value
    sectors-wide.csv    wide theo (code, date) + ten_nganh, cap_icb + cấu phần suy ra
                        (ln_ttm, gtss, doanh_thu_ttm, co_tuc_ttm nhu valuation-wide)
Lưu ý: ngành chỉ có 1 nhánh con thì số cấp 2 = cấp 3 (vd 8300 = 8350 Ngân hàng).
"""
import argparse
import os
import sys
import time

import pandas as pd

from fetch_valuation import fetch_pair, BASE_DIR, RATIOS

MASTER_CSV = os.path.join(BASE_DIR, "sectors-master.csv")
WIDE_CSV = os.path.join(BASE_DIR, "sectors-wide.csv")

# ICB chuẩn (VNDirect group INDUSTRY). Cấp 2 = mã đuôi 00, còn lại cấp 3.
NGANH = {
    "0500": "Dầu khí", "0530": "Sản xuất Dầu khí", "0570": "Thiết bị, Dịch vụ & Phân phối Dầu khí",
    "1300": "Hóa chất", "1350": "Hóa chất",
    "1700": "Tài nguyên Cơ bản", "1730": "Lâm nghiệp & Giấy", "1750": "Kim loại công nghiệp", "1770": "Khai khoáng",
    "2300": "Xây dựng & Vật liệu", "2350": "Xây dựng & Vật liệu",
    "2700": "Hàng & Dịch vụ Công nghiệp", "2720": "Hàng công nghiệp tổng hợp",
    "2730": "Điện tử & Thiết bị điện", "2750": "Chế tạo máy công nghiệp",
    "2770": "Vận tải", "2790": "Dịch vụ hỗ trợ",
    "3300": "Ô tô & Phụ tùng", "3350": "Ô tô & Phụ tùng",
    "3500": "Thực phẩm & Đồ uống", "3530": "Đồ uống", "3570": "Sản xuất thực phẩm",
    "3700": "Hàng cá nhân & Gia dụng", "3720": "Đồ gia dụng & Xây dựng nhà",
    "3740": "Hàng giải trí", "3760": "Hàng cá nhân", "3780": "Thuốc lá",
    "4500": "Y tế", "4530": "Thiết bị & Dịch vụ Y tế", "4570": "Dược phẩm & Công nghệ sinh học",
    "5300": "Bán lẻ", "5330": "Bán lẻ Thực phẩm & Thuốc", "5370": "Bán lẻ tổng hợp",
    "5500": "Truyền thông", "5550": "Truyền thông",
    "5700": "Du lịch & Giải trí", "5750": "Du lịch & Giải trí",
    "6500": "Viễn thông", "6530": "Viễn thông cố định", "6570": "Viễn thông di động",
    "7500": "Tiện ích (Điện, Nước, Khí đốt)", "7530": "Điện", "7570": "Nước & Khí đốt",
    "8300": "Ngân hàng", "8350": "Ngân hàng",
    "8500": "Bảo hiểm", "8530": "Bảo hiểm phi nhân thọ",
    "8600": "Bất động sản", "8630": "Đầu tư & Dịch vụ Bất động sản", "8670": "Quỹ đầu tư BĐS (REITs)",
    "8700": "Dịch vụ tài chính", "8770": "Dịch vụ tài chính",
    "9500": "Công nghệ", "9530": "Phần mềm & Dịch vụ máy tính", "9570": "Thiết bị & Phần cứng công nghệ",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="Keo lai toan bo lich su")
    args = ap.parse_args()

    old = pd.DataFrame(columns=["code", "date", "ratio", "value"])
    if os.path.exists(MASTER_CSV) and not args.full:
        old = pd.read_csv(MASTER_CSV, dtype={"code": str})
        print(f"Master hien co {len(old)} dong, den {old['date'].max()}")

    batch_code = ",".join(NGANH)  # tat ca nganh trong 1 request
    new_rows = []
    for ratio_code in RATIOS:
        from_date = None
        if not old.empty:
            sub = old[old["ratio"] == ratio_code]
            if not sub.empty:
                from_date = sub.groupby("code")["date"].max().min()
        got = fetch_pair(batch_code, ratio_code, from_date)
        print(f"  {ratio_code:20s} +{len(got)} dong (tu {from_date or 'dau lich su'})")
        new_rows.extend(got)
        time.sleep(0.6)

    frames = [df for df in (old, pd.DataFrame(new_rows)) if not df.empty]
    master = pd.concat(frames, ignore_index=True)
    master["code"] = master["code"].astype(str)
    master = master.drop_duplicates(subset=["code", "date", "ratio"], keep="last")
    master = master.sort_values(["code", "ratio", "date"])
    master.to_csv(MASTER_CSV, index=False, encoding="utf-8-sig")
    print(f"\n-> {MASTER_CSV}: {len(master)} dong")

    wide = master.pivot_table(index=["code", "date"], columns="ratio", values="value").reset_index()
    wide.columns.name = None
    wide = wide.rename(columns=RATIOS)
    for col in RATIOS.values():
        if col not in wide.columns:
            wide[col] = pd.NA
    wide.insert(1, "ten_nganh", wide["code"].map(NGANH))
    wide.insert(2, "cap_icb", wide["code"].str[-2:].eq("00").map({True: 2, False: 3}))
    wide["ln_ttm"] = wide["marketcap"] / wide["pe"]
    wide["gtss"] = wide["marketcap"] / wide["pb"]
    wide["doanh_thu_ttm"] = wide["marketcap"] / wide["ps"]
    wide["co_tuc_ttm"] = wide["div_yield"] * wide["marketcap"]
    wide["roe_ttm"] = wide["pb"] / wide["pe"]   # ROE TTM nganh = pb/pe (thap phan, 0.15=15%)
    wide = wide.sort_values(["code", "date"])
    wide.to_csv(WIDE_CSV, index=False, encoding="utf-8-sig")
    print(f"-> {WIDE_CSV}: {len(wide)} dong, {wide['code'].nunique()} nganh "
          f"({wide['date'].min()} den {wide['date'].max()})")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
