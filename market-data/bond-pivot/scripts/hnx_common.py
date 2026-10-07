# -*- coding: utf-8 -*-
"""Shared utils: HNX session (verified TLS qua CA bundle tu ghep + CP-TOKEN),
ghi file an toan khi bi khoa, va config firm tu config/firms.json."""
import json
import re
import time
import requests

BASE = "https://cbonds.hnx.vn"
CA_BUNDLE = "data/raw/ca_bundle.pem"
DELAY = 0.6  # politeness delay between requests (seconds)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")


def make_session(token_page: str) -> tuple[requests.Session, str]:
    """Return (session, cp_token) primed from the given portal page path."""
    s = requests.Session()
    s.verify = CA_BUNDLE
    s.headers.update({"User-Agent": UA, "X-Requested-With": "XMLHttpRequest",
                      "Referer": BASE + token_page})
    r = s.get(BASE + token_page, timeout=30)
    r.raise_for_status()
    m = re.search(r'name="__RequestVerificationToken"\s+content="([^"]+)"', r.text)
    if not m:
        raise RuntimeError("__RequestVerificationToken not found on " + token_page)
    return s, m.group(1)


def polite_sleep():
    time.sleep(DELAY)


def write_file_safe(path, writer_fn, mode="w", newline="", encoding="utf-8-sig"):
    """Write via .tmp then os.replace, retrying when the target is locked
    (e.g. CSV open in Excel). Returns True on success; on failure keeps the
    previous version and returns False."""
    import os
    tmp = path + ".tmp"
    kwargs = {"encoding": encoding}
    if "b" not in mode:
        kwargs["newline"] = newline
    with open(tmp, mode, **kwargs) as f:
        writer_fn(f)
    for attempt in range(3):
        try:
            os.replace(tmp, path)
            return True
        except PermissionError:
            time.sleep(5)
    print("WARNING: %s dang bi khoa (Excel?) - giu ban cu, bo qua lan ghi nay" % path)
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False


# ---------------- firm config (config/firms.json) ----------------
FIRMS_CONFIG = "config/firms.json"


def firms_all():
    return json.load(open(FIRMS_CONFIG, encoding="utf-8"))


def firms_enabled():
    return [k for k, f in firms_all().items() if f.get("enabled")]


def firm_get(key):
    firms = firms_all()
    if key not in firms:
        raise KeyError("firm '%s' khong co trong %s (co: %s)"
                       % (key, FIRMS_CONFIG, ", ".join(firms)))
    return firms[key]


def firm_identity_re(cfg):
    return re.compile("|".join(cfg["patterns"]), re.I)


def firm_out_dir(key):
    return "output/%s" % key
