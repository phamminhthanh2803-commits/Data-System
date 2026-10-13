#!/usr/bin/env python3
"""probe_cloud.py - Do thu tu MAY CLOUD xem cac nguon du lieu cua 3 hub (market-data / shipping / bctc)
co bi chan theo dia ly (IP nuoc ngoai) hay WAF hay khong, TRUOC KHI quyet dinh don pipeline len cloud.

Chay:  python probe_cloud.py            (chi can `requests`; co `curl_cffi` thi test them che do gia Chrome)
       python probe_cloud.py --json out.json

Doc ket qua: OK = HTTP 2xx/3xx va co noi dung; BLOCK = 403/429/451 hoac trang chan (Cloudflare/Incapsula);
             TIMEOUT = khong tra loi trong 25s (gov.vn hay drop goi tu IP ngoai VN thay vi tra 403).
So sanh voi lan chay tren may local (tat ca OK ngay 07/10/2026) de biet nguon nao can proxy VN.
"""
import argparse, json, socket, sys, time, warnings
warnings.filterwarnings("ignore")

try:
    import requests
except ImportError:
    sys.exit("can `pip install requests`")
try:
    from curl_cffi import requests as curl_requests
except ImportError:
    curl_requests = None

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36")

# (nhom, buoc dung, URL thu). URL la trang nhe / endpoint cong khai - khong can dang nhap.
TARGETS = [
    # ---- market-data
    ("VN-gov",   "transmission (SBV)",     "https://sbv.gov.vn/"),
    ("VN-gov",   "nso / nso-monthly",      "https://pxweb.nso.gov.vn/"),
    ("VN-gov",   "nso-monthly",            "https://www.nso.gov.vn/"),
    ("VN-gov",   "bonds (HNX CBIS)",       "https://www.hnx.vn/ModuleReportBonds/Bond_YieldCurve/SearchAndNextPageYieldCurveData"),
    ("VN-gov",   "vsdc-accounts",          "https://vsdc.vn/"),
    ("VN-api",   "valuation-vn/flows",     "https://api-finfo.vndirect.com.vn/v4/stock_prices?q=code:VNM&size=1"),
    ("VN-api",   "foreign-vci/icb-vci",    "https://trading.vietcap.com.vn/"),
    ("VN-api",   "foreign-vci",            "https://iq.vietcap.com.vn/"),
    ("VN-web",   "transmission (bank rates)", "https://www.vietcombank.com.vn/"),
    ("VN-web",   "transmission (bank rates)", "https://bidv.com.vn/"),
    ("VN-web",   "transmission",           "https://dulieukinhte.com/"),
    ("VN-web",   "masvn",                  "https://masvn.com/"),
    ("VN-web",   "cafef",                  "https://cafef.vn/"),
    ("VN-api",   "bctc-scan (Vietstock)",  "https://finance.vietstock.vn/FPT/tai-lieu.htm"),
    ("VN-api",   "bctc-scan (HOSE api)",   "https://api.hsx.vn/n/api/v1/1/news/cate?pageIndex=1&pageSize=1&aliasCate=tin-tuc/tin-to-chuc-niem-yet"),
    ("Global",   "tradingview / tvhistory","https://scanner.tradingview.com/vietnam/scan"),
    ("Global",   "indices (yahoo)",        "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=1d&interval=1d"),
    ("Global",   "macro (IMF SDMX)",       "https://api.imf.org/external/sdmx/2.1/dataflow"),
    ("Global",   "transmission (FRED)",    "https://fred.stlouisfed.org/"),
    ("Region",   "valuation-region (SET, Incapsula)", "https://www.set.or.th/en/home"),
    ("Region",   "valuation-region (TWSE)","https://www.twse.com.tw/"),
    ("Region",   "valuation-region (IDX, Cloudflare)", "https://www.idx.co.id/"),
    ("Region",   "valuation-region (Bursa)","https://www.bursamalaysia.com/"),
    ("Region",   "valuation-region (JPX)", "https://www.jpx.co.jp/"),
    ("Region",   "valuation-region (Naver KR)", "https://finance.naver.com/"),
    # ---- shipping
    ("Ship",     "vhbs",                   "https://www.vhbs.de/"),
    ("Ship",     "haian",                  "https://kethop.haiants.vn/Booking/GetAllVessel"),
    ("Ship",     "bcti (stockq)",          "https://en.stockq.org/"),
    ("Ship",     "cvhp-vessels",           "https://www.balticshipping.com/"),
    ("Ship",     "vimawa",                 "https://vimawa.gov.vn/"),
    ("VN-gov",   "cvhp",                   "https://csdltau.cangvuhaiphong.gov.vn/"),
    ("VN-gov",   "cvhcm",                  "https://cangvuhanghaitphcm.gov.vn/"),
    ("VN-gov",   "cv-aspx (Quang Ninh)",   "https://kht1.cangvuhanghaiquangninh.gov.vn/"),
    ("VN-gov",   "cv-aspx (Nha Trang)",    "https://cangvuhanghainhatrang.gov.vn/"),
    ("VN-gov",   "cv-aspx (Can Tho)",      "https://cangvuhanghaicantho.gov.vn/"),
    ("VN-gov",   "cv-pkh (Da Nang)",       "http://tttb.cangvuhanghaidanang.gov.vn/public-kh"),
    # ---- nguon LIVE / live-first (them 12/10/2026 de kiem tra chay tu runner GitHub)
    ("Live",     "SSI iBoard snapshot toan san",   "https://iboard-query.ssi.com.vn/stock/exchange/hose"),
    ("Live",     "SSI iBoard chart 1 phut",        "https://iboard-api.ssi.com.vn/statistics/charts/history?resolution=1&symbol=VNINDEX&from=%d&to=%d"),
    ("Live",     "Entrade nen ngay (live-first)",  "https://services.entrade.com.vn/chart-api/v2/ohlcs/index?from=%d&to=%d&symbol=VNINDEX&resolution=1D"),
    ("Live",     "VNDirect dchart 1 phut",         "https://dchart-api.vndirect.com.vn/dchart/history?symbol=VNINDEX&resolution=1&from=%d&to=%d"),
    ("Live",     "Vietcap symbols getList",        "https://trading.vietcap.com.vn/api/price/symbols/getList"),
    ("Live",     "CafeF giao dich noi bo",         "https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/GDCoDong.ashx?Symbol=FPT&StartDate=&EndDate=&PageIndex=1&PageSize=5"),
    ("Live",     "DNSE Open API REST",             "https://openapi.dnse.com.vn/"),
    ("Live",     "DNSE WebSocket host",            "https://ws-openapi.dnse.com.vn/v1/stream"),
]

BLOCK_MARKERS = ("Incapsula", "_Incapsula_Resource", "cf-browser-verification", "Just a moment",
                 "Attention Required", "Access Denied", "Request unsuccessful", "captcha")


def classify(status, text, err):
    if err:
        return "TIMEOUT" if "timed out" in err.lower() or "timeout" in err.lower() else "ERR"
    if status in (403, 429, 451):
        return "BLOCK"
    if any(m.lower() in text[:4000].lower() for m in BLOCK_MARKERS):
        return "BLOCK"
    if 200 <= status < 400 or status in (400, 405):
        return "OK"
    return f"HTTP{status}"


def probe(url, mode):
    t0 = time.time()
    try:
        if mode == "curl_cffi":
            r = curl_requests.get(url, impersonate="chrome", timeout=25, allow_redirects=True)
        else:
            r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "vi,en;q=0.8"},
                             timeout=25, allow_redirects=True, verify=False)
        return classify(r.status_code, r.text or "", ""), r.status_code, round(time.time() - t0, 1)
    except Exception as e:  # noqa: BLE001
        return classify(0, "", str(e) or type(e).__name__), 0, round(time.time() - t0, 1)


NOW = int(time.time())
FROM = NOW - 2 * 86400


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="ghi ket qua ra file JSON")
    a = ap.parse_args()
    modes = ["requests"] + (["curl_cffi"] if curl_requests else [])
    try:
        ip = requests.get("https://api.ipify.org?format=json", timeout=10).json().get("ip")
    except Exception:  # noqa: BLE001
        ip = "?"
    print(f"May: {socket.gethostname()}  IP public: {ip}  che do: {', '.join(modes)}")
    print(f"{'Nhom':8} {'Buoc':36} " + " ".join(f"{m:>16}" for m in modes) + "  URL")
    rows, bad = [], []
    for grp, step, url in TARGETS:
        if "%d" in url:
            url = url % (FROM, NOW)
        res = {m: probe(url, m) for m in modes}
        cell = " ".join(f"{v[0]:>8}{v[1]:>4}{v[2]:>4}s" for v in res.values())
        print(f"{grp:8} {step:36} {cell}  {url}")
        rows.append({"group": grp, "step": step, "url": url, **{m: list(v) for m, v in res.items()}})
        if all(v[0] != "OK" for v in res.values()):
            bad.append(step)
    print()
    print(f"Tong {len(TARGETS)} nguon, KHONG vao duoc bang moi che do: {len(bad)}")
    for b in bad:
        print(f"  X {b}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"ip": ip, "rows": rows}, f, ensure_ascii=False, indent=1)
        print(f"Da ghi {a.json}")


if __name__ == "__main__":
    main()
