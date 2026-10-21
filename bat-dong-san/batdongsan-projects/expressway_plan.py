# -*- coding: utf-8 -*-
r"""
expressway_plan.py - SƠ ĐỒ mạng lưới cao tốc quy hoạch Việt Nam (18/10/2026) -> store/infra/expressway_plan.parquet.

Nguồn danh mục: QĐ 1454/QĐ-TTg 01/09/2021 (41 tuyến, 9.014 km) + QĐ 12/QĐ-TTg 03/01/2025 (thêm Cà Mau – Đất Mũi, Quảng Ngãi – Kon Tum)
+ QĐ 1088/QĐ-BXD 30/06/2026 (thêm 5 tuyến: Vành đai miền núi phía Bắc CT.12, Vành đai trung du phía Bắc CT.43, Hà Tĩnh – Cầu Treo CT.44,
Huế – A Lưới CT.45, Phan Thiết – Bảo Lộc – Gia Nghĩa – Bu Prăng CT.46; đổi phạm vi CT.26, CT.33…) -> 46 tuyến ~10.106 km.

Không có shapefile công khai của quy hoạch, nên mỗi đoạn tuyến = chuỗi waypoint địa danh (ROUTES) và được dựng hình theo 2 cách (20/10/2026,
yêu cầu PV2 "nối theo từng nút giao tuyến đi qua"):
  1. BÁM OSM: nếu store/infra/osm_infra.parquet có way (motorway / construction / proposed / trunk) mang ref = mã tuyến (hoặc tên tuyến trong
     OSM_NAMES / opts['names'], hoặc ref phụ opts['refs'] - vd đường Hồ Chí Minh 'HCM' cho CT.02), dựng đồ thị các way đó (nối khe hở < 500 m
     giữa các đầu way), snap từng waypoint vào nút gần nhất (< 20 km) và tìm đường ngắn nhất giữa 2 waypoint kế tiếp -> tuyến tự đi qua đúng
     các nút giao thực tế; làm thưa điểm (simplify ~30 m). Cặp waypoint không có đường OSM thì nối thẳng -> geom_src = osm | mixed | schematic.
  2. SƠ ĐỒ: đoạn chỉ có trên quy hoạch giữ đường nối địa danh; waypoint có thể là tuple ('Nút giao X', lat, lng) để nắn tuyến qua đúng vị trí
     nút giao (theo QĐ 1454 + điều chỉnh 2025–2026).
Mọi đoạn được CHÈN NÚT GIAO (cột `nodes`): điểm cắt giữa tuyến và quốc lộ (trunk) / cao tốc / đường đang xây-quy hoạch có ref trong OSM, và giữa
các tuyến sơ đồ khác mã với nhau; với đoạn bám OSM chỉ giữ giao cắt có nhánh nối (motorway_link/trunk_link) trong 600 m (= nút giao thật, bỏ
chỗ cầu vượt không nối). Tên nút = ref/tên đường bị cắt ("Nút giao QL.1", "Nút giao CT.40"); app vẽ chấm tại nút + hover "CT.xx × QL.yy".
Tình trạng từng đoạn (operating / construction / proposed) là tham khảo tại 10/2026 từ Wikipedia "Hệ thống đường cao tốc Việt Nam" + báo chí;
`horizon` = "2030" (đầu tư trước 2030) hoặc "2050" (sau 2030) theo phụ lục quy hoạch, "-" khi đã khai thác/đang xây.
Sửa toạ độ/tình trạng/nút giao: sửa ROUTES (hoặc W, OSM_NAMES) rồi chạy lại.

    python expressway_plan.py            # dựng parquet (bám OSM + chèn nút giao)
    python expressway_plan.py --refine   # thêm: thay toạ độ waypoint bằng điểm cùng tên trong store/infra/places.parquet (OSM) nếu có
    python expressway_plan.py --no-osm   # chỉ sơ đồ nối thẳng (cách cũ 18/10), vẫn chèn nút giao
    python expressway_plan.py --only CT.40 --verbose   # kiểm tra 1 tuyến (không ghi parquet)
"""
from __future__ import annotations

import argparse
import heapq
import json
import os
import re
import sys
import unicodedata
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get('BDS_STORE') or os.path.join(HERE, 'store')
P_OUT = os.path.join(STORE, 'infra', 'expressway_plan.parquet')
P_PLACES = os.path.join(STORE, 'infra', 'places.parquet')
P_OSM = os.path.join(STORE, 'infra', 'osm_infra.parquet')

# tên tuyến trong OSM (way không có ref hoặc ref khác) dùng thêm để gom way theo mã tuyến; so khớp không dấu, '–' = '-'
OSM_NAMES = {
    'CT.01': ['cao tốc Hữu Nghị - Chi Lăng', 'cao tốc Diễn Châu - Bãi Vọt', 'cao tốc Cần Thơ - Cà Mau'],
    'CT.02': ['cao tốc Gia Nghĩa - Chơn Thành', 'cao tốc Chơn Thành - Đức Hoà', 'cao tốc Pleiku - Buôn Ma Thuột', 'cao tốc Buôn Ma Thuột - Gia Nghĩa',
              'cao tốc Tuyên Quang - Phú Thọ'],
    'CT.03': ['cao tốc Hòa Bình - Mộc Châu'], 'CT.07': ['cao tốc Chợ Mới - Bắc Kạn', 'cao tốc Thái Nguyên - Chợ Mới'],
    'CT.08': ['cao tốc Ninh Bình - Hải Phòng'], 'CT.09': ['cao tốc Nội Bài - Bắc Ninh'], 'CT.10': ['cao tốc Đồng Đăng - Trà Lĩnh'],
    'CT.13': ['cao tốc Bảo Hà (Lào Cai) - Lai Châu'], 'CT.15': ['cao tốc Tuyên Quang - Hà Giang'], 'CT.24': ['cao tốc Khánh Hòa - Buôn Ma Thuột'],
    'CT.25': ['cao tốc Nha Trang - Đà Lạt'], 'CT.27': ['cao tốc Dầu Giây - Tân Phú', 'cao tốc Tân Phú - Bảo Lộc', 'cao tốc Bảo Lộc - Liên Khương'],
    'CT.28': ['cao tốc Biên Hòa - Vũng Tàu'], 'CT.30': ['cao tốc Thành phố Hồ Chí Minh - Thủ Dầu Một - Chơn Thành'], 'CT.32': ['cao tốc Gò Dầu - Xa Mát'],
    'CT.34': ['cao tốc Châu Đốc - Cần Thơ - Sóc Trăng'], 'CT.36': ['cao tốc Dinh Bà - Cao Lãnh', 'cao tốc Cao Lãnh - An Hữu'],
    'CT.38': ['cao tốc vành đai 4 vùng thủ đô Hà Nội'], 'CT.39': ['cao tốc vành đai 5 Hà Nội'], 'CT.40': ['vành đai 3 Thành phố Hồ Chí Minh'],
    'CT.41': ['Vành đai 4 Thành phố Hồ Chí Minh'],
}
LINK_KINDS = ('motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link')
SNAP_KM = 20.0         # waypoint cách nút đồ thị OSM xa hơn -> không bám OSM cho cặp đó
GAP_M = 500.0          # nối 2 đầu way cách nhau < GAP_M (dữ liệu OSM hở, đổi carriageway)
DETOUR = 2.2           # đường OSM dài hơn DETOUR × đường chim bay + 15 km -> coi là lạc (đi vòng tuyến khác), nối thẳng

# (tên địa danh, lat, lng) - toạ độ gần đúng (thị trấn / nút giao / cửa khẩu)
W = {
    'Hữu Nghị': (21.96, 106.72), 'Chi Lăng': (21.60, 106.58), 'Bắc Giang': (21.27, 106.19), 'Pháp Vân': (20.95, 105.85), 'Phủ Lý': (20.54, 105.91),
    'Ninh Bình': (20.25, 105.97), 'Thanh Hóa': (19.80, 105.78), 'Nghi Sơn': (19.37, 105.74), 'Diễn Châu': (18.97, 105.58), 'Bãi Vọt': (18.53, 105.69),
    'Vũng Áng': (18.08, 106.38), 'Đồng Hới': (17.47, 106.60), 'Đông Hà': (16.81, 107.10), 'Huế': (16.46, 107.59), 'Đà Nẵng': (16.05, 108.17),
    'Quảng Ngãi': (15.12, 108.80), 'Hoài Nhơn': (14.52, 109.05), 'Quy Nhơn': (13.78, 109.19), 'Tuy Hòa': (13.09, 109.30), 'Vân Phong': (12.60, 109.20),
    'Nha Trang': (12.24, 109.19), 'Cam Lâm': (12.05, 109.14), 'Phan Rang': (11.57, 108.99), 'Vĩnh Hảo': (11.30, 108.73), 'Phan Thiết': (10.93, 108.10),
    'Dầu Giây': (10.94, 107.15), 'Long Thành': (10.79, 106.95), 'Tân Hiệp': (10.78, 106.86), 'Bến Lức': (10.63, 106.49), 'Trung Lương': (10.42, 106.30),
    'Mỹ Thuận': (10.28, 105.92), 'Cần Thơ': (10.03, 105.77), 'Hậu Giang': (9.78, 105.62), 'Bạc Liêu': (9.29, 105.72), 'Cà Mau': (9.18, 105.15),
    'Đất Mũi': (8.62, 104.72), 'Tuyên Quang': (21.82, 105.21), 'Việt Trì': (21.32, 105.40), 'Phú Thọ': (21.40, 105.23), 'Ba Vì': (21.12, 105.42),
    'Hòa Bình': (20.82, 105.34), 'Chợ Bến': (20.62, 105.60), 'Thạch Quảng': (20.30, 105.45), 'Ngọc Lặc': (19.90, 105.37), 'Tân Kỳ': (19.05, 105.37),
    'Hương Khê': (18.17, 105.70), 'Khe Sanh': (16.62, 106.73), 'A Lưới': (16.28, 107.25), 'Thạnh Mỹ': (15.75, 107.83), 'Ngọc Hồi': (14.72, 107.68),
    'Kon Tum': (14.35, 108.01), 'Pleiku': (13.98, 108.00), 'Buôn Ma Thuột': (12.68, 108.05), 'Gia Nghĩa': (12.00, 107.69), 'Chơn Thành': (11.43, 106.63),
    'Đức Hòa': (10.88, 106.42), 'Mỹ An': (10.52, 105.84), 'Cao Lãnh': (10.46, 105.63), 'Lộ Tẻ': (10.17, 105.47), 'Rạch Giá': (10.01, 105.08),
    'Hòa Lạc': (21.00, 105.52), 'Mộc Châu': (20.85, 104.65), 'Sơn La': (21.33, 103.92), 'Tuần Giáo': (21.58, 103.42), 'Điện Biên': (21.39, 103.02),
    'Tây Trang': (21.27, 102.93), 'Hà Nội': (21.03, 105.85), 'Hưng Yên': (20.65, 106.05), 'Hải Dương': (20.93, 106.33), 'Đình Vũ': (20.84, 106.76),
    'Nội Bài': (21.22, 105.80), 'Yên Bái': (21.70, 104.87), 'Lào Cai': (22.48, 103.97), 'Hải Phòng': (20.85, 106.70), 'Hạ Long': (20.95, 107.08),
    'Vân Đồn': (21.05, 107.42), 'Tiên Yên': (21.33, 107.40), 'Móng Cái': (21.53, 107.97), 'Thái Nguyên': (21.59, 105.84), 'Chợ Mới': (21.90, 105.80),
    'Bắc Kạn': (22.15, 105.83), 'Cao Bằng': (22.67, 106.26), 'Nam Định': (20.43, 106.17), 'Thái Bình': (20.45, 106.34), 'Bắc Ninh': (21.18, 106.06),
    'Chí Linh': (21.12, 106.40), 'Uông Bí': (21.03, 106.77), 'Đình Lập': (21.54, 107.10), 'Lạng Sơn': (21.85, 106.76), 'Đồng Đăng': (21.95, 106.70),
    'Thất Khê': (22.26, 106.46), 'Đông Khê': (22.43, 106.43), 'Trà Lĩnh': (22.80, 106.33), 'Xuân Trường': (20.30, 106.35), 'Mậu A': (21.87, 104.72),
    'Việt Quang': (22.33, 104.85), 'Bảo Hà': (22.17, 104.35), 'Lai Châu': (22.40, 103.47), 'Ma Lù Thàng': (22.66, 103.42), 'Yên Mỹ': (20.90, 106.03),
    'Hà Giang': (22.83, 104.98), 'Thanh Thủy (Hà Giang)': (22.95, 104.85), 'Cửa Lò': (18.80, 105.72), 'Vinh': (18.68, 105.68), 'Thanh Thủy (Nghệ An)': (18.66, 105.11),
    'Ba Đồn': (17.75, 106.42), 'Cha Lo': (17.68, 105.76), 'Cam Lộ': (16.80, 107.00), 'Lao Bảo': (16.62, 106.60), 'Nhơn Hội': (13.85, 109.23),
    'An Khê': (13.95, 108.68), 'Lệ Thanh': (13.75, 107.60), 'Khâm Đức': (15.45, 107.80), 'Bờ Y': (14.70, 107.52), 'Tam Kỳ': (15.57, 108.48),
    'Chu Lai': (15.42, 108.72), 'Dung Quất': (15.38, 108.80), 'Bãi Gốc': (12.96, 109.40), 'Buôn Hồ': (12.92, 108.27), 'Đắk Ruê': (12.80, 107.55),
    'Ninh Hòa': (12.49, 109.13), "M'Drắk": (12.72, 108.78), 'Diên Khánh': (12.26, 109.10), 'Khánh Vĩnh': (12.28, 108.90), 'Đà Lạt': (11.94, 108.44),
    'Liên Khương': (11.75, 108.37), 'Đơn Dương': (11.80, 108.60), 'Lâm Hà': (11.87, 108.22), 'Đắk Glong': (12.10, 107.90), 'Tân Phú': (11.35, 107.42),
    'Bảo Lộc': (11.55, 107.81), 'Biên Hòa': (10.95, 106.85), 'Bà Rịa': (10.50, 107.17), 'An Phú (TP.HCM)': (10.79, 106.75), 'Thủ Dầu Một': (10.98, 106.65),
    'Bàu Bàng': (11.25, 106.63), 'Đồng Xoài': (11.53, 106.90), 'Hoa Lư': (11.98, 106.90), 'Củ Chi': (11.00, 106.49), 'Trảng Bàng': (11.03, 106.37),
    'Gò Dầu': (11.08, 106.27), 'Mộc Bài': (11.10, 106.18), 'Tây Ninh': (11.31, 106.10), 'Tân Biên': (11.55, 106.00), 'Xa Mát': (11.68, 105.95),
    'Nhà Bè': (10.65, 106.73), 'Cần Đước': (10.55, 106.60), 'Chợ Gạo': (10.37, 106.46), 'Bến Tre': (10.24, 106.38), 'Mỏ Cày': (10.08, 106.30),
    'Trà Ôn': (9.96, 105.92), 'Phụng Hiệp': (9.78, 105.78), 'Châu Đốc': (10.70, 105.11), 'Long Xuyên': (10.38, 105.43), 'Trần Đề': (9.52, 106.17),
    'Hà Tiên': (10.38, 104.49), 'Kiên Lương': (10.29, 104.64), 'Vị Thanh': (9.78, 105.47), 'Dinh Bà': (10.90, 105.30), 'Hồng Ngự': (10.80, 105.34),
    'Vĩnh Long': (10.25, 105.97), 'Trà Vinh': (9.93, 106.34), 'Định An': (9.65, 106.42), 'Sóc Trăng': (9.60, 105.97),
    'Sóc Sơn': (21.22, 105.75), 'Mê Linh': (21.17, 105.70), 'Đan Phượng': (21.08, 105.65), 'Hoài Đức': (21.03, 105.68), 'Hà Đông': (20.95, 105.72),
    'Thường Tín': (20.85, 105.85), 'Văn Giang': (20.93, 105.95), 'Thuận Thành': (21.05, 106.05), 'Sơn Tây': (21.14, 105.50), 'Vĩnh Yên': (21.31, 105.60),
    'Lương Sơn': (20.88, 105.52), 'Nhơn Trạch': (10.70, 106.90), 'Tân Vạn': (10.88, 106.80), 'Bình Chuẩn': (10.98, 106.72), 'Hóc Môn': (10.88, 106.60),
    'Phú Mỹ': (10.60, 107.05), 'Trảng Bom': (10.95, 107.00), 'Tân Uyên': (11.05, 106.80), 'Bến Cát': (11.15, 106.60), 'Hiệp Phước': (10.62, 106.75),
    'Sơn Hà': (15.05, 108.50), 'Tân Thanh': (21.99, 106.65), 'Văn Chấn': (21.55, 104.55), 'Phù Yên': (21.27, 104.65), 'Tà Lùng': (22.52, 106.57),
    'Bắc Sơn': (21.90, 106.32), 'Hàm Yên': (22.07, 105.03), 'Bảo Yên': (22.23, 104.47), 'Hà Tĩnh': (18.34, 105.90), 'Phố Châu': (18.52, 105.43),
    'Cầu Treo': (18.37, 105.15), 'Bu Prăng': (12.20, 107.42), 'Vành đai 3 HN (Mai Dịch)': (21.04, 105.78), 'Thanh Trì': (20.96, 105.87),
    'Cầu Giẽ': (20.65, 105.95), 'Nghệ An (Rộ)': (18.90, 105.30),
}

# ROUTES: (mã, tên, nhóm, [ (tên đoạn, trạng thái, horizon, làn, [waypoint...]) ])
ROUTES = [
    ('CT.01', 'Bắc – Nam phía Đông', 'Trục Bắc – Nam', [
        ('Hữu Nghị – Chi Lăng', 'construction', '-', '6', ['Hữu Nghị', 'Chi Lăng']),
        ('Chi Lăng – Hà Nội', 'operating', '-', '4-8', ['Chi Lăng', 'Bắc Giang', 'Pháp Vân']),
        ('Hà Nội – Ninh Bình – Thanh Hóa', 'operating', '-', '4-10', ['Pháp Vân', 'Cầu Giẽ', 'Phủ Lý', 'Ninh Bình', 'Thanh Hóa', 'Nghi Sơn']),
        ('Nghi Sơn – Vinh – Hà Tĩnh', 'operating', '-', '4', ['Nghi Sơn', 'Diễn Châu', 'Bãi Vọt', 'Vũng Áng']),
        ('Vũng Áng – Quảng Trị – Huế – Đà Nẵng', 'operating', '-', '4', ['Vũng Áng', 'Đồng Hới', 'Đông Hà', 'Huế', 'Đà Nẵng']),
        ('Đà Nẵng – Quảng Ngãi – Quy Nhơn', 'operating', '-', '4', ['Đà Nẵng', 'Quảng Ngãi', 'Hoài Nhơn', 'Quy Nhơn']),
        ('Quy Nhơn – Nha Trang – Phan Thiết – Dầu Giây', 'operating', '-', '4', ['Quy Nhơn', 'Tuy Hòa', 'Vân Phong', 'Nha Trang', 'Cam Lâm', 'Phan Rang', 'Vĩnh Hảo', 'Phan Thiết', 'Dầu Giây']),
        ('Dầu Giây – Long Thành – Bến Lức – Trung Lương – Mỹ Thuận – Cần Thơ', 'operating', '-', '4-10', ['Dầu Giây', 'Long Thành', 'Tân Hiệp', 'Bến Lức', 'Trung Lương', 'Mỹ Thuận', 'Cần Thơ']),
        ('Cần Thơ – Hậu Giang – Cà Mau', 'construction', '-', '4', ['Cần Thơ', 'Hậu Giang', 'Bạc Liêu', 'Cà Mau']),
        ('Cà Mau – Đất Mũi (bổ sung QĐ 12/2025)', 'proposed', '2030', '4', ['Cà Mau', 'Đất Mũi'])]),
    ('CT.02', 'Bắc – Nam phía Tây', 'Trục Bắc – Nam', [
        ('Tuyên Quang – Phú Thọ', 'operating', '-', '4', ['Tuyên Quang', 'Phú Thọ']),
        ('Phú Thọ – Ba Vì – Chợ Bến', 'proposed', '2030', '4-6', ['Phú Thọ', 'Ba Vì', 'Chợ Bến']),
        ('Chợ Bến – Thạch Quảng – Tân Kỳ – Rộ (đường Hồ Chí Minh, nâng cấp sau 2030)', 'proposed', '2050', '4', ['Chợ Bến', 'Thạch Quảng', 'Ngọc Lặc', 'Tân Kỳ', 'Nghệ An (Rộ)'], {'refs': ['HCM']}),
        ('Rộ – Hương Khê – Khe Sanh – A Lưới – Thạnh Mỹ – Ngọc Hồi (đường Hồ Chí Minh)', 'proposed', '2050', '4', ['Nghệ An (Rộ)', 'Hương Khê', 'Khe Sanh', 'A Lưới', 'Thạnh Mỹ', 'Khâm Đức', 'Ngọc Hồi'], {'refs': ['HCM']}),
        ('Ngọc Hồi – Kon Tum – Pleiku', 'proposed', '2050', '6', ['Ngọc Hồi', 'Kon Tum', 'Pleiku'], {'refs': ['HCM']}),
        ('Pleiku – Buôn Ma Thuột', 'proposed', '2030', '6', ['Pleiku', 'Buôn Ma Thuột']),
        ('Buôn Ma Thuột – Gia Nghĩa', 'proposed', '2030', '6', ['Buôn Ma Thuột', 'Gia Nghĩa']),
        ('Gia Nghĩa – Chơn Thành', 'construction', '-', '4-6', ['Gia Nghĩa', 'Đồng Xoài', 'Chơn Thành']),
        ('Chơn Thành – Đức Hòa', 'construction', '-', '4', ['Chơn Thành', 'Củ Chi', 'Đức Hòa']),
        ('Đức Hòa – Mỹ An', 'proposed', '2030', '4', ['Đức Hòa', 'Mỹ An']),
        ('Mỹ An – Cao Lãnh', 'construction', '-', '4', ['Mỹ An', 'Cao Lãnh']),
        ('Cao Lãnh – Lộ Tẻ – Rạch Sỏi', 'operating', '-', '4', ['Cao Lãnh', 'Lộ Tẻ', 'Rạch Giá'])]),
    ('CT.03', 'Hà Nội – Hòa Bình – Sơn La – Điện Biên', 'Phía Bắc', [
        ('Hà Nội – Hòa Lạc – Hòa Bình', 'operating', '-', '4-6', ['Hà Nội', 'Hòa Lạc', 'Hòa Bình']),
        ('Hòa Bình – Mộc Châu', 'construction', '-', '4', ['Hòa Bình', 'Mộc Châu']),
        ('Mộc Châu – Sơn La', 'proposed', '2030', '4', ['Mộc Châu', 'Sơn La']),
        ('Sơn La – Điện Biên – Tây Trang', 'proposed', '2050', '4', ['Sơn La', 'Tuần Giáo', 'Điện Biên', 'Tây Trang'])]),
    ('CT.04', 'Hà Nội – Hải Phòng', 'Phía Bắc', [('Hà Nội – Hải Phòng', 'operating', '-', '6', ['Hà Nội', 'Hưng Yên', 'Hải Dương', 'Đình Vũ'])]),
    ('CT.05', 'Hà Nội – Lào Cai', 'Phía Bắc', [('Nội Bài – Việt Trì – Yên Bái – Lào Cai', 'operating', '-', '4-6', ['Nội Bài', 'Việt Trì', 'Yên Bái', 'Lào Cai'])]),
    ('CT.06', 'Hải Phòng – Hạ Long – Vân Đồn – Móng Cái', 'Phía Bắc', [('Hải Phòng – Móng Cái', 'operating', '-', '4-6', ['Hải Phòng', 'Hạ Long', 'Vân Đồn', 'Tiên Yên', 'Móng Cái'])]),
    ('CT.07', 'Hà Nội – Thái Nguyên – Bắc Kạn – Cao Bằng', 'Phía Bắc', [
        ('Hà Nội – Thái Nguyên – Chợ Mới', 'operating', '-', '4', ['Hà Nội', 'Thái Nguyên', 'Chợ Mới']),
        ('Chợ Mới – Bắc Kạn', 'construction', '-', '4', ['Chợ Mới', 'Bắc Kạn']),
        ('Bắc Kạn – Cao Bằng', 'proposed', '2050', '4', ['Bắc Kạn', 'Cao Bằng'])]),
    ('CT.08', 'Ninh Bình – Hải Phòng', 'Phía Bắc', [('Ninh Bình – Nam Định – Thái Bình – Hải Phòng', 'construction', '-', '4', ['Ninh Bình', 'Nam Định', 'Thái Bình', 'Hải Phòng'])]),
    ('CT.09', 'Nội Bài – Bắc Ninh – Hạ Long', 'Phía Bắc', [
        ('Nội Bài – Bắc Ninh', 'proposed', '2030', '6', ['Nội Bài', 'Bắc Ninh']),
        ('Bắc Ninh – Chí Linh – Uông Bí – Hạ Long', 'proposed', '2030', '6', ['Bắc Ninh', 'Chí Linh', 'Uông Bí', 'Hạ Long'])]),
    ('CT.10', 'Tiên Yên – Lạng Sơn – Cao Bằng', 'Phía Bắc', [
        ('Tiên Yên – Đình Lập – Lạng Sơn', 'proposed', '2050', '4', ['Tiên Yên', 'Đình Lập', 'Lạng Sơn']),
        ('Đồng Đăng – Trà Lĩnh', 'construction', '-', '4', ['Lạng Sơn', 'Đồng Đăng', 'Thất Khê', 'Đông Khê', 'Cao Bằng', 'Trà Lĩnh'])]),
    ('CT.11', 'Phủ Lý – Nam Định', 'Phía Bắc', [('Phủ Lý – Nam Định – Xuân Trường', 'proposed', '2030', '4', ['Phủ Lý', 'Nam Định', 'Xuân Trường'])]),
    ('CT.12 (2021)', 'Nối Hà Nội – Lào Cai với Hà Giang', 'Phía Bắc', [('Mậu A – Việt Quang', 'proposed', '2050', '4', ['Mậu A', 'Việt Quang'])]),
    ('CT.13', 'Bảo Hà – Lai Châu', 'Phía Bắc', [('Bảo Hà – Lai Châu – Ma Lù Thàng', 'proposed', '2030', '4', ['Bảo Hà', 'Lai Châu', 'Ma Lù Thàng'])]),
    ('CT.14', 'Chợ Bến – Yên Mỹ', 'Phía Bắc', [('Chợ Bến – Yên Mỹ', 'proposed', '2050', '4', ['Chợ Bến', 'Yên Mỹ'])]),
    ('CT.15', 'Tuyên Quang – Hà Giang', 'Phía Bắc', [('Tuyên Quang – Hà Giang – Thanh Thủy', 'construction', '-', '4', ['Tuyên Quang', 'Hàm Yên', 'Hà Giang', 'Thanh Thủy (Hà Giang)'])]),
    ('CT.16', 'Hưng Yên – Thái Bình', 'Phía Bắc', [('Hưng Yên – Thái Bình', 'construction', '-', '4', ['Hưng Yên', 'Thái Bình'])]),
    ('CT.17', 'Vinh – Thanh Thủy', 'Miền Trung – Tây Nguyên', [('Cửa Lò – Vinh – Thanh Thủy', 'proposed', '2050', '6', ['Cửa Lò', 'Vinh', 'Thanh Thủy (Nghệ An)'])]),
    ('CT.18', 'Vũng Áng – Cha Lo', 'Miền Trung – Tây Nguyên', [('Vũng Áng – Ba Đồn – Cha Lo', 'proposed', '2050', '4', ['Vũng Áng', 'Ba Đồn', 'Cha Lo'])]),
    ('CT.19', 'Cam Lộ – Lao Bảo', 'Miền Trung – Tây Nguyên', [('Đông Hà – Cam Lộ – Khe Sanh – Lao Bảo', 'proposed', '2030', '4', ['Đông Hà', 'Cam Lộ', 'Khe Sanh', 'Lao Bảo'])]),
    ('CT.20', 'Quy Nhơn – Pleiku – Lệ Thanh', 'Miền Trung – Tây Nguyên', [
        ('Nhơn Hội – An Khê – Pleiku', 'construction', '-', '4', ['Nhơn Hội', 'Quy Nhơn', 'An Khê', 'Pleiku']),
        ('Pleiku – Lệ Thanh', 'proposed', '2050', '4', ['Pleiku', 'Lệ Thanh'])]),
    ('CT.21', 'Đà Nẵng – Thạnh Mỹ – Ngọc Hồi – Bờ Y', 'Miền Trung – Tây Nguyên', [('Đà Nẵng – Bờ Y', 'proposed', '2050', '4', ['Đà Nẵng', 'Thạnh Mỹ', 'Khâm Đức', 'Ngọc Hồi', 'Bờ Y'])]),
    ('CT.22', 'Quảng Nam – Quảng Ngãi', 'Miền Trung – Tây Nguyên', [('Tam Kỳ – Chu Lai – Dung Quất', 'proposed', '2050', '4', ['Tam Kỳ', 'Chu Lai', 'Dung Quất'])]),
    ('CT.23', 'Phú Yên – Đắk Lắk', 'Miền Trung – Tây Nguyên', [
        ('Bãi Gốc – Tuy Hòa – Buôn Hồ', 'proposed', '2030', '4', ['Bãi Gốc', 'Tuy Hòa', 'Buôn Hồ']),
        ('Buôn Hồ – Đắk Ruê', 'proposed', '2050', '4', ['Buôn Hồ', 'Đắk Ruê'])]),
    ('CT.24', 'Khánh Hòa – Buôn Ma Thuột', 'Miền Trung – Tây Nguyên', [('Vân Phong – Ninh Hòa – M’Drắk – Buôn Ma Thuột', 'construction', '-', '4', ['Vân Phong', 'Ninh Hòa', "M'Drắk", 'Buôn Ma Thuột'])]),
    ('CT.25', 'Nha Trang – Liên Khương', 'Miền Trung – Tây Nguyên', [('Diên Khánh – Khánh Vĩnh – Đà Lạt – Liên Khương', 'proposed', '2030', '4', ['Diên Khánh', 'Khánh Vĩnh', 'Đà Lạt', 'Liên Khương'])]),
    ('CT.26', 'Phan Rang – Liên Khương – Buôn Ma Thuột (phạm vi QĐ 1088/2026)', 'Miền Trung – Tây Nguyên', [
        ('Phan Rang – Đơn Dương – Liên Khương', 'proposed', '2050', '4', ['Phan Rang', 'Đơn Dương', 'Liên Khương']),
        ('Liên Khương – Lâm Hà – Buôn Ma Thuột', 'proposed', '2050', '4', ['Liên Khương', 'Lâm Hà', 'Đắk Glong', 'Buôn Ma Thuột'])]),
    ('CT.27', 'Dầu Giây – Liên Khương', 'Phía Nam', [('Dầu Giây – Tân Phú – Bảo Lộc – Liên Khương', 'construction', '-', '4', ['Dầu Giây', 'Tân Phú', 'Bảo Lộc', 'Liên Khương'])]),
    ('CT.28', 'Biên Hòa – Vũng Tàu', 'Phía Nam', [('Biên Hòa – Long Thành – Bà Rịa', 'construction', '-', '6-8', ['Biên Hòa', 'Long Thành', 'Phú Mỹ', 'Bà Rịa'])]),
    ('CT.29', 'TP.HCM – Long Thành – Dầu Giây', 'Phía Nam', [('TP.HCM – Long Thành – Dầu Giây', 'operating', '-', '6-10', ['An Phú (TP.HCM)', 'Long Thành', 'Dầu Giây'])]),
    ('CT.30', 'TP.HCM – Chơn Thành – Hoa Lư', 'Phía Nam', [
        ('TP.HCM – Thủ Dầu Một – Chơn Thành', 'construction', '-', '6', ['Thủ Dầu Một', 'Bàu Bàng', 'Chơn Thành']),
        ('Chơn Thành – Đồng Xoài – Hoa Lư', 'proposed', '2050', '6', ['Chơn Thành', 'Đồng Xoài', 'Hoa Lư'])]),
    ('CT.31', 'TP.HCM – Mộc Bài', 'Phía Nam', [('TP.HCM – Củ Chi – Gò Dầu – Mộc Bài', 'construction', '-', '6', ['Hóc Môn', 'Củ Chi', 'Trảng Bàng', 'Gò Dầu', 'Mộc Bài'])]),
    ('CT.32', 'Gò Dầu – Xa Mát', 'Phía Nam', [('Gò Dầu – Tây Ninh – Xa Mát', 'proposed', '2050', '4', ['Gò Dầu', 'Tây Ninh', 'Tân Biên', 'Xa Mát'])]),
    ('CT.33', 'TP.HCM – Vĩnh Long – Cần Thơ – Cà Mau (QĐ 1088/2026; trước là TP.HCM – Tiền Giang – Bến Tre – Trà Vinh – Sóc Trăng)', 'Phía Nam', [
        ('Nhà Bè – Cần Đước – Chợ Gạo – Bến Tre – Vĩnh Long', 'proposed', '2030', '4', ['Nhà Bè', 'Cần Đước', 'Chợ Gạo', 'Bến Tre', 'Mỏ Cày', 'Trà Ôn']),
        ('Vĩnh Long – Cần Thơ', 'proposed', '2030', '4', ['Trà Ôn', 'Cần Thơ']),
        ('Cần Thơ – Cà Mau', 'proposed', '2050', '4', ['Cần Thơ', 'Phụng Hiệp', 'Bạc Liêu', 'Cà Mau'])]),
    ('CT.34', 'Châu Đốc – Cần Thơ – Sóc Trăng', 'Phía Nam', [('Châu Đốc – Long Xuyên – Cần Thơ – Trần Đề', 'construction', '-', '4-6', ['Châu Đốc', 'Long Xuyên', 'Cần Thơ', 'Sóc Trăng', 'Trần Đề'])]),
    ('CT.35', 'Hà Tiên – Rạch Giá – Bạc Liêu', 'Phía Nam', [
        ('Hà Tiên – Kiên Lương – Rạch Giá', 'proposed', '2030', '4', ['Hà Tiên', 'Kiên Lương', 'Rạch Giá']),
        ('Rạch Giá – Vị Thanh – Bạc Liêu', 'proposed', '2050', '4', ['Rạch Giá', 'Vị Thanh', 'Bạc Liêu'])]),
    ('CT.36', 'Hồng Ngự – Trà Vinh', 'Phía Nam', [('Dinh Bà – Hồng Ngự – Cao Lãnh – Vĩnh Long – Trà Vinh – Định An', 'proposed', '2050', '4', ['Dinh Bà', 'Hồng Ngự', 'Cao Lãnh', 'Vĩnh Long', 'Trà Vinh', 'Định An'])]),
    ('CT.37', 'Vành đai 3 Hà Nội', 'Vành đai Hà Nội', [('Vành đai 3 (khép kín)', 'operating', '-', '6', ['Vành đai 3 HN (Mai Dịch)', 'Thanh Trì', 'Nội Bài', 'Vành đai 3 HN (Mai Dịch)'])]),
    ('CT.38', 'Vành đai 4 Hà Nội', 'Vành đai Hà Nội', [('Vành đai 4 (HN – Lào Cai → Nội Bài – Hạ Long)', 'construction', '-', '6', ['Sóc Sơn', 'Mê Linh', 'Đan Phượng', 'Hoài Đức', 'Hà Đông', 'Thường Tín', 'Văn Giang', 'Thuận Thành', 'Bắc Ninh'])]),
    ('CT.39', 'Vành đai 5 Hà Nội', 'Vành đai Hà Nội', [('Vành đai 5 (khép kín)', 'proposed', '2050', '6', ['Hòa Lạc', 'Sơn Tây', 'Vĩnh Yên', 'Thái Nguyên', 'Bắc Giang', 'Hải Dương', 'Thái Bình', 'Phủ Lý', 'Lương Sơn', 'Hòa Lạc'])]),
    ('CT.40', 'Vành đai 3 TP.HCM', 'Vành đai TP.HCM', [('Vành đai 3 (Nhơn Trạch → Bến Lức)', 'construction', '-', '8', ['Nhơn Trạch', 'Tân Vạn', 'Bình Chuẩn', 'Hóc Môn', 'Bến Lức'])]),
    ('CT.41', 'Vành đai 4 TP.HCM', 'Vành đai TP.HCM', [('Vành đai 4 (Phú Mỹ → Hiệp Phước)', 'proposed', '2030', '8', ['Phú Mỹ', 'Long Thành', 'Trảng Bom', 'Tân Uyên', 'Bến Cát', 'Củ Chi', 'Đức Hòa', 'Bến Lức', 'Hiệp Phước'])]),
    ('CT.42', 'Quảng Ngãi – Kon Tum (bổ sung QĐ 12/2025)', 'Miền Trung – Tây Nguyên', [('Quảng Ngãi – Sơn Hà – Kon Tum', 'proposed', '2050', '4', ['Quảng Ngãi', 'Sơn Hà', 'Kon Tum'])]),
    ('CT.12', 'Vành đai miền núi phía Bắc (bổ sung QĐ 1088/2026)', 'Phía Bắc', [
        ('Tà Lùng – Đông Khê – Thất Khê – Lạng Sơn', 'proposed', '2050', '4', ['Tà Lùng', 'Đông Khê', 'Thất Khê', 'Lạng Sơn']),
        ('Lạng Sơn – Bắc Sơn – Chợ Mới (Thái Nguyên)', 'proposed', '2050', '4', ['Lạng Sơn', 'Bắc Sơn', 'Chợ Mới']),
        ('Chợ Mới – Hàm Yên (Tuyên Quang) – Bảo Yên (Lào Cai)', 'proposed', '2050', '4', ['Chợ Mới', 'Hàm Yên', 'Bảo Yên']),
        ('Bảo Yên – Lai Châu – Tuần Giáo (Sơn La)', 'proposed', '2050', '4', ['Bảo Yên', 'Bảo Hà', 'Lai Châu', 'Tuần Giáo'])]),
    ('CT.43', 'Vành đai trung du phía Bắc (bổ sung QĐ 1088/2026)', 'Phía Bắc', [
        ('Tân Thanh – Lạng Sơn – Thái Nguyên', 'proposed', '2030', '4', ['Tân Thanh', 'Lạng Sơn', 'Bắc Sơn', 'Thái Nguyên']),
        ('Thái Nguyên – Tuyên Quang – Yên Bái (HN – Lào Cai)', 'proposed', '2050', '4', ['Thái Nguyên', 'Tuyên Quang', 'Yên Bái']),
        ('Yên Bái – Văn Chấn – Phù Yên – Sơn La', 'proposed', '2050', '4', ['Yên Bái', 'Văn Chấn', 'Phù Yên', 'Sơn La'])]),
    ('CT.44', 'Hà Tĩnh – Cầu Treo (bổ sung QĐ 1088/2026)', 'Miền Trung – Tây Nguyên', [('Hà Tĩnh – Phố Châu – Cầu Treo', 'proposed', '2030', '4-6', ['Hà Tĩnh', 'Phố Châu', 'Cầu Treo'])]),
    ('CT.45', 'Huế – A Lưới (bổ sung QĐ 1088/2026)', 'Miền Trung – Tây Nguyên', [('Huế – A Lưới', 'proposed', '2050', '4', ['Huế', 'A Lưới'])]),
    ('CT.46', 'Phan Thiết – Bảo Lộc – Gia Nghĩa – Bu Prăng (bổ sung QĐ 1088/2026)', 'Miền Trung – Tây Nguyên', [
        ('Phan Thiết – Bảo Lộc – Gia Nghĩa', 'proposed', '2030', '4', ['Phan Thiết', 'Bảo Lộc', 'Gia Nghĩa']),
        ('Gia Nghĩa – Bu Prăng', 'proposed', '2050', '4', ['Gia Nghĩa', 'Bu Prăng'])]),
]


def _norm(s):
    s = unicodedata.normalize('NFD', str(s).lower()); s = ''.join(c for c in s if unicodedata.category(c) != 'Mn').replace('đ', 'd')
    return re.sub(r'[^a-z0-9 ]', ' ', s).strip()


def refine_coords(places_path=P_PLACES):
    """thay toạ độ W bằng điểm cùng tên trong gazetteer OSM (place city/town) nếu cách < 25 km (tránh trùng tên tỉnh khác)"""
    if not os.path.exists(places_path): return 0
    pl = pd.read_parquet(places_path); pl = pl[pl['place'].isin(['city', 'town'])].copy(); pl['n'] = pl['name'].map(_norm); n = 0
    for k, (lat, lng) in list(W.items()):
        base = re.sub(r'\s*\(.*?\)', '', k)
        cand = pl[pl['n'] == _norm(base)]
        if cand.empty: continue
        cand = cand.assign(d=((cand['lat'] - lat) ** 2 + ((cand['lng'] - lng) * 0.95) ** 2) ** 0.5 * 111).sort_values('d')
        if cand['d'].iloc[0] < 25: W[k] = (float(cand['lat'].iloc[0]), float(cand['lng'].iloc[0])); n += 1
    return n


def _km(a, b):
    """khoảng cách km giữa 2 điểm (lng, lat), xấp xỉ phẳng"""
    return float(np.hypot((a[0] - b[0]) * 111.32 * np.cos(np.radians((a[1] + b[1]) / 2)), (a[1] - b[1]) * 111.32))


def _refs(s):
    return [x.strip() for x in str(s).split(';') if x.strip()] if isinstance(s, str) and s else []


def _norm_name(s):
    return _norm(str(s).replace('–', '-').replace('—', '-'))


def cross_label(ref, name, own_code):
    """tên đường bị cắt để đặt tên nút giao: ref ưu tiên (QL.1, CT.05, ĐT.830, HCM -> đường Hồ Chí Minh), không có thì tên way"""
    for r in _refs(ref):
        if r == own_code: continue
        if r == 'HCM': return 'đường Hồ Chí Minh'
        return re.sub(r'^(QL|CT|ĐT|TL)\.?\s*', lambda m: m.group(1) + '.', r)
    n = str(name) if isinstance(name, str) and name else ''
    return re.sub(r'^Đường\s+', '', n) if n else ''


def _is_ref(lab): return bool(re.match(r'^(QL|CT|ĐT|TL)\.|^đường Hồ Chí Minh$', lab))


# ---------------------------------------------------------------- 1) bám OSM: đồ thị các way mang mã tuyến + đường ngắn nhất giữa waypoint
class OsmRouter:
    def __init__(self, osm: pd.DataFrame, verbose=False):
        o = osm[osm['layer'].isin(['motorway', 'construction', 'proposed', 'trunk']) & ~osm['kind'].isin(LINK_KINDS + ('bridge',))].copy()
        o['_refs'] = o['ref'].map(_refs); o['_name'] = o['name'].fillna('').map(_norm_name)
        self.o = o; self.cache = {}; self.verbose = verbose

    def ways(self, code, refs=(), names=()):
        o = self.o; keys = {code, *refs}
        m = o['_refs'].map(lambda r: any(k in r for k in keys))
        nm = [_norm_name(x) for x in list(OSM_NAMES.get(code, [])) + list(names)]
        if nm: m |= o['_name'].map(lambda s: any(x in s for x in nm))
        return o[m]

    def graph(self, code, refs=(), names=()):
        key = (code, tuple(refs), tuple(names))
        if key in self.cache: return self.cache[key]
        w = self.ways(code, refs, names)
        idx = {}; xy = []; adj = []; ends = []
        def nid(p):
            k = (round(p[0], 5), round(p[1], 5))
            if k not in idx: idx[k] = len(xy); xy.append(k); adj.append([])
            return idx[k]
        for c in w['coords']:
            pts = json.loads(c)
            if len(pts) < 2: continue
            ids = [nid(p) for p in pts]
            for a, b in zip(ids[:-1], ids[1:]):
                if a == b: continue
                d = _km(xy[a], xy[b]) * 1000; adj[a].append((b, d)); adj[b].append((a, d))
            ends += [ids[0], ids[-1]]
        # nối khe hở giữa các đầu way (< GAP_M), phạt ×3 để không ưu tiên nhảy khe
        cell = {}; gm = GAP_M / 111320.0
        for e in set(ends): cell.setdefault((int(xy[e][0] / gm), int(xy[e][1] / gm)), []).append(e)
        n_gap = 0
        for e in set(ends):
            cx, cy = int(xy[e][0] / gm), int(xy[e][1] / gm)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for f in cell.get((cx + dx, cy + dy), []):
                        if f <= e: continue
                        d = _km(xy[e], xy[f]) * 1000
                        if 0 < d < GAP_M and f not in [x for x, _ in adj[e]]: adj[e].append((f, d * 3)); adj[f].append((e, d * 3)); n_gap += 1
        comp = np.full(len(xy), -1, dtype=int); nc = 0                 # thành phần liên thông (để snap lại waypoint vào đúng mảng nối được)
        for s in range(len(xy)):
            if comp[s] >= 0: continue
            stack = [s]; comp[s] = nc
            while stack:
                u = stack.pop()
                for v, _ in adj[u]:
                    if comp[v] < 0: comp[v] = nc; stack.append(v)
            nc += 1
        g = {'xy': np.array(xy, dtype=float) if xy else np.zeros((0, 2)), 'adj': adj, 'comp': comp, 'n_ways': len(w), 'n_gap': n_gap}
        if self.verbose: print(f'   đồ thị {code}: {len(w)} way, {len(xy)} nút, {n_gap} khe nối, {nc} mảng liên thông')
        self.cache[key] = g; return g

    @staticmethod
    def snap(g, p, comp=None):
        """nút đồ thị gần (lng, lat) nhất (chỉ trong mảng liên thông comp nếu cho) -> (id, km)"""
        xy = g['xy']
        if not len(xy): return None, 1e9
        d = np.hypot((xy[:, 0] - p[0]) * 111.32 * np.cos(np.radians(p[1])), (xy[:, 1] - p[1]) * 111.32)
        if comp is not None: d = np.where(g['comp'] == comp, d, 1e9)
        i = int(d.argmin())
        return i, float(d[i])

    @staticmethod
    def dijkstra(g, s, t):
        adj = g['adj']; dist = {s: 0.0}; prev = {}; pq = [(0.0, s)]; seen = set()
        while pq:
            d, u = heapq.heappop(pq)
            if u in seen: continue
            seen.add(u)
            if u == t: break
            for v, w in adj[u]:
                nd = d + w
                if nd < dist.get(v, 1e18): dist[v] = nd; prev[v] = u; heapq.heappush(pq, (nd, v))
        if t not in dist: return None, None
        path = [t]
        while path[-1] != s: path.append(prev[path[-1]])
        return path[::-1], dist[t]

    def route(self, code, pts, refs=(), names=()):
        """pts = [(label, lng, lat, manual)] -> (coords [[lng,lat]...], flags theo cặp (True = bám OSM), vị trí waypoint đã snap)"""
        g = self.graph(code, refs, names); coords = []; flags = []; snapped = []
        for lab, lng, lat, manual in pts:
            i, d = self.snap(g, (lng, lat))
            i = i if d < (3.0 if manual else SNAP_KM) else None          # nút chèn tay: snap chặt (3 km) để giữ đúng vị trí
            snapped.append((lab, float(g['xy'][i][0]) if i is not None else lng, float(g['xy'][i][1]) if i is not None else lat, i))
        # waypoint giữa tuyến không snap được (địa danh cách tuyến > SNAP_KM, vd Cần Thơ với CT.34) mà 2 bên đều snap -> bỏ qua, đi OSM thẳng 2 bên
        keep = [k for k in range(len(snapped)) if not (0 < k < len(snapped) - 1 and snapped[k][3] is None and not pts[k][3]
                                                        and snapped[k - 1][3] is not None and snapped[k + 1][3] is not None)]
        if self.verbose and len(keep) < len(snapped): print(f'   {code}: bỏ waypoint xa tuyến ' + ', '.join(snapped[k][0] for k in range(len(snapped)) if k not in keep))
        snapped = [snapped[k] for k in keep]; pts = [pts[k] for k in keep]
        for k, ((la, xa, ya, ia), (lb, xb, yb, ib)) in enumerate(zip(snapped[:-1], snapped[1:])):
            seg = None
            if ia is not None and ib is not None and ia != ib:
                if g['comp'][ia] != g['comp'][ib]:                      # 2 đầu rơi vào 2 mảng rời: snap lại đầu kia vào mảng của đầu này (trong SNAP_KM)
                    j, d = self.snap(g, (pts[k + 1][1], pts[k + 1][2]), int(g['comp'][ia]))
                    if d < SNAP_KM: ib, xb, yb = j, float(g['xy'][j][0]), float(g['xy'][j][1])
                    else:
                        j, d = self.snap(g, (pts[k][1], pts[k][2]), int(g['comp'][ib]))
                        if d < SNAP_KM: ia, xa, ya = j, float(g['xy'][j][0]), float(g['xy'][j][1])
                path, L = self.dijkstra(g, ia, ib)
                if path and L / 1000 <= DETOUR * _km((xa, ya), (xb, yb)) + 15: seg = [[float(x), float(y)] for x, y in g['xy'][path]]
                elif self.verbose: print(f'   {code} {la} → {lb}: ' + ('không có đường OSM nối' if not path else f'đường OSM {L/1000:.0f} km quá vòng'))
            elif self.verbose: print(f'   {code} {la} → {lb}: waypoint xa đồ thị OSM (snap {ia}, {ib})')
            flags.append(seg is not None)
            if seg is None: seg = [[xa, ya], [xb, yb]]                  # không có đường OSM -> nối thẳng (toạ độ đã snap nếu có)
            if coords and coords[-1] == seg[0]: seg = seg[1:]
            coords += seg
        return coords, flags, snapped


def simplify_coords(coords, tol_deg=0.0003):
    if len(coords) <= 3: return coords
    from shapely.geometry import LineString
    ls = LineString(coords).simplify(tol_deg, preserve_topology=False)
    return [[float(x), float(y)] for x, y in ls.coords]


# ---------------------------------------------------------------- 2) nút giao: điểm cắt tuyến × đường OSM có ref / tuyến sơ đồ khác
class NodeFinder:
    def __init__(self, osm: pd.DataFrame):
        from shapely.geometry import LineString
        from shapely.strtree import STRtree
        c = osm[osm['layer'].isin(['trunk', 'motorway', 'construction', 'proposed']) & ~osm['kind'].isin(LINK_KINDS + ('bridge',))]
        nm = c['name'].fillna('')
        # không có ref: chỉ nhận "Đường cao tốc X" / "Đường vành đai N" (bỏ đường song hành, đường nối, nhánh "Đi ...")
        c = c[c['ref'].notna() | (nm.str.match(r'^Đường (cao tốc|[Vv]ành đai)') & ~nm.str.contains('song hành|nối|mở rộng|giai đoạn', regex=True))]
        self.cross = c.reset_index(drop=True); self.cross_geom = [LineString(json.loads(x)) for x in self.cross['coords']]
        self.cross['_name'] = self.cross['name'].fillna('').map(_norm_name)
        self.tree = STRtree(self.cross_geom)
        lk = osm[osm['kind'].isin(LINK_KINDS)]
        self.link_tree = STRtree([LineString(json.loads(x)) for x in lk['coords']])

    def has_link(self, pt, deg=0.006):
        return len(self.link_tree.query(pt.buffer(deg))) > 0

    def nodes_for(self, code, line, osm_spans, refs=(), names=(), need_link=True):
        """nút giao của 1 đoạn (shapely LineString) với đường OSM: [(label, lng, lat, pos_km, on_osm)].
        osm_spans: [(km_từ, km_đến)] phần tuyến bám OSM; need_link: trên phần bám OSM cao tốc chỉ giữ giao cắt có nhánh nối (motorway_link…)
        trong 600 m, trừ khi đường bị cắt là CT khác."""
        out = []; own = [_norm_name(x) for x in list(OSM_NAMES.get(code, [])) + list(names)]; keys = {code, *refs}
        for j in self.tree.query(line, predicate='intersects'):
            r = self.cross.iloc[int(j)]
            if keys & set(_refs(r['ref'])) or (own and any(x in r['_name'] for x in own)): continue      # way của chính tuyến (carriageway kép)
            lab = cross_label(r['ref'], r['name'], code)
            if not lab: continue
            inter = line.intersection(self.cross_geom[int(j)])
            pts = [inter] if inter.geom_type == 'Point' else [g for g in getattr(inter, 'geoms', []) if g.geom_type == 'Point']
            is_ct = any(x.startswith('CT.') for x in _refs(r['ref']))
            for p in pts:
                pos = line.project(p) * 111.32; on_osm = any(a - 0.5 <= pos <= b + 0.5 for a, b in osm_spans)
                if on_osm and need_link and not is_ct and not self.has_link(p): continue      # cầu vượt không nhánh nối -> không phải nút giao
                out.append((lab, p.x, p.y, pos, on_osm))
        return out


def dedupe_nodes(nodes, same_km=3.0, any_km=0.4):
    """gộp nút trùng: cùng tên trong same_km (carriageway kép cắt 2 lần, QL song song cắt qua lại; sơ đồ nối thẳng dùng 8 km) hoặc bất kỳ tên trong any_km"""
    nodes = sorted(nodes, key=lambda n: n['pos_km']); out = []
    for n in nodes:
        hit = None
        for m in out:
            d = _km((n['lng'], n['lat']), (m['lng'], m['lat']))
            if (n['cross'] == m['cross'] and d < same_km) or d < any_km: hit = m; break
        if hit is None: out.append(n); continue
        if n['kind'] == 'manual': hit.update(name=n['name'], cross=n['cross'], kind='manual'); continue
        if hit['kind'] == 'manual' or n['cross'] in hit['cross'].split(' / '): continue
        if _is_ref(n['cross']) and not _is_ref(hit['cross']): hit['cross'] = n['cross']           # ref (QL.1) thay cho tên dài
        elif _is_ref(n['cross']) or not _is_ref(hit['cross']): hit['cross'] += ' / ' + n['cross']
        hit['name'] = 'Nút giao ' + hit['cross']
    return out


def build(refine=False, use_osm=True, only=None, verbose=False, write=True):
    if refine: print('refine:', refine_coords(), 'waypoint lấy toạ độ OSM')
    osm = pd.read_parquet(P_OSM) if os.path.exists(P_OSM) else None
    if osm is None: print('KHÔNG có osm_infra.parquet -> sơ đồ nối thẳng, không chèn nút giao'); use_osm = False
    router = OsmRouter(osm, verbose) if use_osm else None
    finder = NodeFinder(osm) if osm is not None else None
    from shapely.geometry import LineString, Point
    rows = []; today = date.today().isoformat(); missing = set()
    for code, name, group, segs in ROUTES:
        if only and code not in only: continue
        for i, seg in enumerate(segs, 1):
            segname, status, horizon, lanes, wps = seg[:5]; opts = seg[5] if len(seg) > 5 else {}
            pts = []           # (label, lng, lat, manual)
            for w in wps:
                if isinstance(w, tuple): pts.append((w[0], float(w[2]), float(w[1]), True))
                elif w in W: pts.append((w, W[w][1], W[w][0], False))
                else: missing.add(w)
            if len(pts) < 2: continue
            if router:
                coords, flags, snapped = router.route(code, pts, opts.get('refs', ()), opts.get('names', ()))
                src = 'osm' if all(flags) else ('mixed' if any(flags) else 'schematic'); coords = simplify_coords(coords)
            else:
                coords = [[p[1], p[2]] for p in pts]; flags = [False] * (len(pts) - 1); src = 'schematic'; snapped = [(p[0], p[1], p[2], None) for p in pts]
            line = LineString(coords)
            # phần tuyến bám OSM (km dọc tuyến giữa 2 waypoint đã snap) -> nút giao trên đó ghi kind='osm', phần nối thẳng ghi 'plan'
            bnd = [line.project(Point(x, y)) * 111.32 for _, x, y, _ in snapped]
            osm_spans = [(min(a, b), max(a, b)) for a, b, f in zip(bnd[:-1], bnd[1:], flags) if f]
            nodes = []
            if finder:
                # chỉ đoạn ĐANG KHAI THÁC bám cao tốc OSM mới đòi nhánh nối (đang xây: OSM chưa vẽ nhánh; bám quốc lộ hiện hữu (opts refs, đường HCM): giao bằng)
                for lab, x, y, pos, on_osm in finder.nodes_for(code, line, osm_spans, opts.get('refs', ()), opts.get('names', ()), need_link=(status == 'operating' and not opts.get('refs'))):
                    nodes.append({'name': f'Nút giao {lab}', 'cross': lab, 'lng': round(x, 6), 'lat': round(y, 6), 'pos_km': round(pos, 1), 'kind': 'osm' if on_osm else 'plan'})
            for lab, x, y, _ in snapped:                                   # nút chèn tay trong ROUTES: waypoint tuple tên bắt đầu "Nút giao"
                if lab.lower().startswith('nút giao'):
                    nodes.append({'name': lab, 'cross': lab[8:].strip(), 'lng': round(x, 6), 'lat': round(y, 6), 'pos_km': round(line.project(Point(x, y)) * 111.32, 1), 'kind': 'manual'})
            nodes = dedupe_nodes(nodes, same_km=3.0 if src == 'osm' else 8.0)
            lats = [p[1] for p in coords]; lngs = [p[0] for p in coords]
            length = sum(_km(a, b) for a, b in zip(coords[:-1], coords[1:]))
            if verbose: print(f'{code}-{i} {segname}: {src} ({sum(flags)}/{len(flags)} cặp bám OSM) · {len(coords)} điểm · {length:.0f} km · {len(nodes)} nút giao: '
                              + ', '.join(n['cross'] for n in nodes))
            rows.append({'osm_id': f'{code}-{i}', 'layer': 'exp_plan', 'kind': 'expressway_plan', 'status': status, 'horizon': horizon,
                         'name': f'{code} {name} · {segname}', 'ref': code, 'route': name, 'segment': segname, 'group': group, 'lanes': lanes,
                         'opening_date': None, 'operator': None, 'bridge': None, 'coords': json.dumps(coords),
                         'waypoints': ' → '.join(p[0] for p in pts), 'geom_src': src, 'osm_pairs': f'{sum(flags)}/{len(flags)}', 'length_km': round(length, 1),
                         'nodes': json.dumps(nodes, ensure_ascii=False), 'n_nodes': len(nodes),
                         'lat_min': min(lats), 'lat_max': max(lats), 'lng_min': min(lngs), 'lng_max': max(lngs), 'n_pts': len(coords), 'fetched': today})
    if missing: print('THIẾU toạ độ:', sorted(missing))
    df = pd.DataFrame(rows)
    # nút giao giữa các tuyến sơ đồ khác mã (CT.xx × CT.yy) - thêm vào cả 2 đoạn nếu chưa có nút cùng mã trong 2 km
    geoms = [LineString(json.loads(c)) for c in df['coords']]; all_nodes = [json.loads(x) for x in df['nodes']]
    for a in range(len(df)):
        for b in range(a + 1, len(df)):
            if df['ref'].iloc[a] == df['ref'].iloc[b]: continue
            if df['lat_min'].iloc[a] > df['lat_max'].iloc[b] or df['lat_max'].iloc[a] < df['lat_min'].iloc[b] or df['lng_min'].iloc[a] > df['lng_max'].iloc[b] or df['lng_max'].iloc[a] < df['lng_min'].iloc[b]: continue
            inter = geoms[a].intersection(geoms[b])
            pts = [inter] if inter.geom_type == 'Point' else [g for g in getattr(inter, 'geoms', []) if g.geom_type == 'Point']
            for p in pts:
                for me, other, g in ((a, b, geoms[a]), (b, a, geoms[b])):
                    oc = df['ref'].iloc[other]; ocode = oc.split(' ')[0]
                    if any(ocode in n['cross'] and _km((p.x, p.y), (n['lng'], n['lat'])) < 2 for n in all_nodes[me]): continue
                    all_nodes[me].append({'name': f'Nút giao {oc}', 'cross': oc, 'lng': round(p.x, 6), 'lat': round(p.y, 6), 'pos_km': round(g.project(p) * 111.32, 1), 'kind': 'plan'})
    df['nodes'] = [json.dumps(dedupe_nodes(n, same_km=3.0 if s == 'osm' else 8.0), ensure_ascii=False) for n, s in zip(all_nodes, df['geom_src'])]
    df['n_nodes'] = [len(json.loads(x)) for x in df['nodes']]
    if write:
        os.makedirs(os.path.dirname(P_OUT), exist_ok=True); df.to_parquet(P_OUT, index=False)
    print(f'DONE expressway_plan: {df["ref"].nunique()} tuyến, {len(df)} đoạn, {df["n_nodes"].sum()} nút giao, {df["n_pts"].sum()} điểm'
          + (f' -> {P_OUT}' if write else ' (không ghi)') + f' | {df["status"].value_counts().to_dict()} | hình học {df["geom_src"].value_counts().to_dict()}')
    return df


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--refine', action='store_true'); ap.add_argument('--no-osm', action='store_true')
    ap.add_argument('--only', nargs='*', help='chỉ dựng các mã tuyến này, không ghi parquet'); ap.add_argument('--verbose', action='store_true'); a = ap.parse_args()
    build(refine=a.refine, use_osm=not a.no_osm, only=a.only, verbose=a.verbose or bool(a.only), write=not a.only); sys.exit(0)
