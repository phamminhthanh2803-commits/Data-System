# news-rss — tin RSS báo kinh tế, phân loại theo ngành (11/11/2026)

Kéo **57 chuyên mục RSS của 11 báo** (CafeF, Vietstock, VnEconomy, VnExpress, Dân trí, VietnamNet, Tuổi Trẻ, Thanh Niên,
VietnamBiz, Nhịp sống kinh doanh, VietnamPlus), gộp vào kho lịch sử, **phân loại từng bài theo ngành**. App Market Data ›
**Tin tức › Tin theo ngành**: chọn ngành thì tin tự lọc và sắp xếp (mới nhất / liên quan nhất / đáng chú ý).

```
news-rss\
  newslib.py           chuẩn hoá tiếng Việt (hoá/hóa, thuỷ/thủy, HTML), đọc RSS, bộ phân loại PhanLoai
  fetch_rss.py         kéo feed → data\news_master.parquet → phân loại → news_tagged / news_tags (+ feed_status.csv, nganh.csv)
  keyword_mining.py    gợi ý từ khoá: output\keyword_candidates.xlsx (tần suất, đặc trưng theo ngành, lỗ hổng, mã CK + ngữ cảnh)
  danh_sach_nganh.py   output\danh_sach_nganh.xlsx: các danh sách ngành đang dùng trong hệ thống (ICB Vietcap, nhóm TradingView, ngành TPDN)
  config\
    nganh.csv          23 ngành phân loại: 19 ICB Vietcap cấp 2 (tên giữ nguyên như app) + Vingroup + Vĩ mô & chính sách
                       + Thị trường chứng khoán + Kinh tế thế giới; cột ma = khoá ngắn dùng ở keywords.csv / feeds.csv
    keywords.csv       ~1.100 từ khoá: ma ngành, chủ đề con, từ khoá, trọng số 1-3, hoa=1 (phân biệt hoa thường: AI, EVN, BOT…)
    loai_tin.csv       13 loại tin (KQKD, cổ tức, phát hành, M&A, GD nội bộ, pháp lý, chính sách, dự án, nhân sự, ĐHĐCĐ,
                       khuyến nghị, biến động giá) → điểm "đáng chú ý"
    alias_ma.csv       tên gọi → mã CK (Hòa Phát → HPG…), bo_alias (tên trùng địa danh), can_ngu_canh (mã trùng viết tắt: CPI, VND, SBV…)
    feeds.csv          danh sách feed + goi_y (chuyên mục RSS gợi ý 1 ngành, +1,5 điểm)
  data\                (Drive: gdrive:pipeline-data/market-data/news-rss/data)
  output\              file Excel soát từ khoá (chỉ ở laptop)
```

## Cách phân loại
Điểm một bài cho một ngành = Σ trọng số từ khoá khớp (**tiêu đề ×2, tóm tắt ×1**, mỗi từ tính 1 lần/trường)
+ **mã CK** nhắc trong bài (mã 3 ký tự viết hoa hoặc tên DN → ngành ICB cấp 2 của mã theo `index-fetcher\raw\vn_icb_vci.csv`;
tiêu đề 4, tóm tắt 3; bài nhắc > 5 mã ×0,5; mã Vingroup cộng cả Vingroup lẫn BĐS)
+ **gợi ý chuyên mục** RSS 1,5. Gắn ngành khi điểm **≥ 3**; một bài có thể nhiều ngành, ngành điểm cao nhất = ngành chính.
Khớp nguyên từ (không khớp giữa từ), cụm dài thắng cụm ngắn ("bảo hiểm xã hội" không tính cho ngành Bảo hiểm).
Điểm đáng chú ý = trọng số loại tin + 1 nếu có mã CK + số báo cùng đưa tin.

## Chạy
```
python fetch_rss.py                 # kéo + phân loại bài mới (~5 giây)
python fetch_rss.py --no-fetch      # chỉ phân loại lại (sửa config\*.csv → tự phân loại lại TOÀN BỘ vì đổi hash từ điển)
python keyword_mining.py            # soát / bổ sung từ khoá → output\keyword_candidates.xlsx
python danh_sach_nganh.py
```
**Lịch:** GitHub Actions `news.yml` (repo Data-System) **2 giờ/lần 06:15 → 22:15** — RSS chỉ giữ 20–100 bài mới nhất mỗi chuyên mục
(Vietstock 20) nên chạy 2 lần/ngày sẽ sót tin. Chỉ workflow này ghi `news-rss/data` trên Drive (không có bước news trong Market AM/PM).
App cloud kéo về mỗi 30 phút (cloud_boot APP_DATA); laptop: `sync_data.py app` (APP_FOLDERS).

## Bổ sung từ khoá
1. `python keyword_mining.py` → mở `output\keyword_candidates.xlsx`: sheet **Theo_nganh** (cụm đặc trưng ngành chưa có trong từ điển,
   lift ≥ 3 trên bài gắn ngành qua mã CK), **Chua_phan_loai** (cụm hay gặp ở bài chưa có ngành), **Ma_CK** (mã nhận được + ngữ cảnh
   → mã nhận nhầm thì thêm `can_ngu_canh` vào alias_ma.csv).
2. Thêm dòng vào `config\keywords.csv` → `python fetch_rss.py --no-fetch` (cloud: chạy tay news.yml với `reclass`).

Nguồn đã thử và loại: nld.com.vn (ngừng cập nhật 06/2026), laodong, baodautu, tinnhanhchungkhoan, znews, thoibaotaichinh, vir,
baochinhphu (404 hoặc rỗng).
