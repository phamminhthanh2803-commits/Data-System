# -*- coding: utf-8 -*-
"""
cvhcm_berthmap.py - Dựng bảng tra CHÍNH THỨC mã cầu/phao -> khu vực cảng của Cảng vụ TP.HCM.
Nguồn: trang "Vị trí tàu tại cảng" (page=shipinport&cat=3095) có 2 cột "Khu vực cảng" và "Cầu/Phao" cho mọi tàu đang ở cảng.
Kéo ảnh chụp của nhiều ngày (mặc định ngày 1 và 15 mỗi tháng trong 30 tháng + 7 ngày gần nhất), đếm cặp (mã cầu, khu vực),
ghi berth_area_map.csv (code, area, n, share). Mỗi mã lấy khu vực xuất hiện nhiều nhất.
cvhcm_scrape.py dùng bảng này trước, regex trong berths.csv chỉ là dự phòng cho mã chưa từng thấy.

Chạy:  python cvhcm_berthmap.py            (cộng dồn vào bảng cũ)      python cvhcm_berthmap.py --months 60
"""
import argparse, csv, os, re, sys, time
from collections import Counter, defaultdict
from datetime import date, timedelta

import requests
import lxml.html as LH

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(ROOT, 'berth_area_map.csv'); RAWCNT = os.path.join(ROOT, 'berth_area_counts.csv')
URL = 'https://cangvuhanghaitphcm.gov.vn/index.aspx?page=shipinport&cat=3095'
H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/128 cvhcm-berthmap', 'Accept-Language': 'vi'}


def norm(s): return re.sub(r'\s+', ' ', (s or '')).strip().upper()


def hidden(t): return dict(re.findall(r'<input type="hidden" name="([^"]+)"[^>]*value="([^"]*)"', t))


def snapshot(sess, state, d):
    ds = d.strftime('%d/%m/%Y'); iso = d.isoformat()
    data = dict(state)
    data.update({'ctl22$txtDate': ds, 'ctl22$txtDate$dateInput': ds,
                 'ctl22_txtDate_dateInput_ClientState': '{"enabled":true,"emptyMessage":"","validationText":"%s-00-00-00","valueAsString":"%s-00-00-00",'
                                                        '"minDateStr":"1980-01-01-00-00-00","maxDateStr":"2099-12-30-00-00-00","lastSetTextBoxValue":"%s"}' % (iso, iso, ds),
                 'ctl22$btnSearch': 'Tìm kiếm', 'ctl43$txtSearch': 'Từ khóa cần tìm'})
    r = sess.post(URL, data=data, headers=H, timeout=120); r.raise_for_status(); r.encoding = 'utf-8'
    doc = LH.fromstring(r.text)
    tb = max(doc.xpath('//table'), key=lambda x: len(x.xpath('.//tr')))
    pairs = []
    for tr in tb.xpath('.//tr'):
        if not re.search(r'\brg(Alt)?Row\b', tr.get('class', '')): continue
        c = [re.sub(r'\s+', ' ', x.text_content()).strip() for x in tr.xpath('./td')]
        if len(c) >= 7 and c[3] and c[4]: pairs.append((norm(c[4]), norm(c[3])))
    return pairs, hidden(r.text)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--months', type=int, default=30); ap.add_argument('--sleep', type=float, default=0.6)
    a = ap.parse_args()
    today = date.today()
    days = {today - timedelta(days=i) for i in range(7)}
    y, m = today.year, today.month
    for _ in range(a.months):
        for dd in (1, 15):
            d = date(y, m, dd)
            if d <= today: days.add(d)
        m -= 1
        if m == 0: y, m = y - 1, 12
    cnt = defaultdict(Counter)
    if os.path.exists(RAWCNT):
        for r in csv.DictReader(open(RAWCNT, encoding='utf-8-sig')): cnt[r['code']][r['area']] += int(r['n'])
    sess = requests.Session()
    r0 = sess.get(URL, headers=H, timeout=90); r0.encoding = 'utf-8'; state = hidden(r0.text)
    for i, d in enumerate(sorted(days), 1):
        try:
            pairs, state = snapshot(sess, state, d)
        except Exception as e:
            print(f'loi {d}: {e}', flush=True); time.sleep(5)
            r0 = sess.get(URL, headers=H, timeout=90); r0.encoding = 'utf-8'; state = hidden(r0.text); continue
        for code, area in pairs: cnt[code][area] += 1
        print(f'{i}/{len(days)} {d}: {len(pairs)} tau, tong {len(cnt)} ma cau', flush=True)
        time.sleep(a.sleep)
    with open(RAWCNT, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f); w.writerow(['code', 'area', 'n'])
        for code in sorted(cnt):
            for area, n in cnt[code].most_common(): w.writerow([code, area, n])
    with open(OUT, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f); w.writerow(['code', 'area', 'n', 'share'])
        for code in sorted(cnt):
            area, n = cnt[code].most_common(1)[0]
            w.writerow([code, area, n, round(n / sum(cnt[code].values()), 2)])
    areas = Counter()
    for code in cnt: areas[cnt[code].most_common(1)[0][0]] += sum(cnt[code].values())
    print(f'DONE berth map: {len(cnt)} ma cau, {len(areas)} khu vuc -> {OUT}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
