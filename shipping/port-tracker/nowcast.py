# -*- coding: utf-8 -*-
r"""
nowcast.py - NOWCAST sản lượng container theo tháng cho Port & Vessel Tracker (14/10/2026).

Tổng quát hoá hict_nowcast.py của PV2 cho mọi cảng/bến:
  - biến giải thích (từ lượt cập bến cảng vụ): số lượt (calls), sức chở TEU danh nghĩa (teu; tàu thiếu TEU ước = DWT / trung vị DWT/TEU),
    tổng giờ nằm bến chặn trên 80 giờ/lượt (hours)
  - mục tiêu (sản lượng thực tế, TEU/tháng) = EconDB:
      * cảng vụ: container full EconDB (traffic, cộng tuần -> tháng theo ngày) của các cảng EconDB thuộc cảng vụ
      * bến có số CÔNG BỐ trong nowcast_targets.csv (>= MIN_TRAIN_TERM + 3 tháng, nhập trong app): dùng số công bố - EconDB terminal
        chỉ đếm container có hàng và lệch dần (HICT: công bố/EconDB 1,43 -> 1,77 năm 2024 -> 2026, lẫn HTIT/HHIT cùng Lạch Huyện)
      * bến có mã terminal EconDB (econdb.TERMINAL_MAP, vd VNCHL = HICT, HTIT = HTIT): throughput từng terminal (trang terminal
        EconDB, từ 2022) -> hồi quy riêng cho bến như cảng vụ
      * bến không có mã / chưa đủ tháng (vd TCTT: cảng vụ HCM mới có Cái Mép từ 08/2025): container full cảng × tỷ trọng container
        xếp dỡ của bến, đo bằng lượt tàu EconDB (vessel-calls) ghép với bến cảng vụ theo tên tàu + giờ đến -> ước/dự báo =
        ước/dự báo cảng vụ × tỷ trọng TB 3 tháng
  - hồi quy tuyến tính KHÔNG hệ số chặn, 11 biến thể (giờ bến / sức chở / cả hai × cửa sổ toàn bộ, 12, 6, 3 tháng); backtest ngoài mẫu
    (mỗi tháng chỉ dùng dữ liệu trước nó), chọn mô hình theo điểm = TB(MAPE cả lịch sử, MAPE 6 tháng gần nhất) để bám khi năng suất đổi
  - cảng vụ nhiều cảng EconDB (HCM = VN SGN + VN VUT): hồi quy RIÊNG từng cảng (fit_ports: biến = bến thuộc cảng đó theo
    econdb.terminal_port, thực tế = container full của cảng đó) rồi cộng (combine) -> tránh gãy chuỗi khi cảng vụ thêm Cái Mép 2025
  - nowcast: tháng trọn có biến nhưng chưa có thực tế = mô hình; tháng đang chạy = w × (biến đã có quy ra cả tháng, bỏ 2 ngày cuối
    vì tàu chưa rời chưa có giờ bến) + (1 - w) × dự báo thuần, w = số ngày đã có / số ngày tháng (0 nếu < MIN_DAYS_PARTIAL ngày)
  - dự báo thuần (tháng tới): biến = TB 3 tháng trọn gần nhất × mùa vụ năm trước của chuỗi THỰC TẾ (tháng đích / TB 3 tháng nền, chặn 0,7–1,35)
  - khoảng = ± MAPE × (1,5 − 0,5 w): nowcast tháng trọn ±MAPE, dự báo thuần ±1,5×MAPE
"""


import os
import unicodedata

import numpy as np
import pandas as pd

HOURS_CAP = 80


def me(x):
    """Mốc CUỐI THÁNG (PV2 15/10/2026: toàn hệ thống dùng ngày cuối kỳ, không dùng 01 tháng để khỏi hiểu nhầm).
    Series / DatetimeIndex / Timestamp -> cùng loại; 01/09 -> 30/09, 30/09 giữ nguyên."""
    off = pd.offsets.MonthEnd(0)
    if isinstance(x, pd.Series): return pd.to_datetime(x, errors='coerce').dt.normalize() + off
    if isinstance(x, pd.DatetimeIndex): return (x.normalize() + off).rename(x.name)
    return (pd.Timestamp(x).normalize() + off) if pd.notna(x) else x


def ly(ts):
    """cùng tháng năm trước, mốc cuối tháng (28/02/2026 -> 28/02/2025; 29/02/2024 -> 28/02/2023)"""
    return me(pd.Timestamp(ts) - pd.DateOffset(years=1))
MIN_TRAIN = 12              # cảng: backtest từ tháng thứ 13
MIN_TRAIN_TERM = 6          # bến: chuỗi cảng vụ ngắn hơn (Cái Mép từ 08/2025) -> backtest từ tháng thứ 7, cần >= 9 tháng để tự hồi quy
MIN_DAYS_PARTIAL = 5        # tháng đang chạy: từ 5 ngày dữ liệu mới cho biến tham gia nowcast (trọng số = số ngày / số ngày tháng)
LAG_DAYS = 2                # bỏ 2 ngày cuối: tàu vào chưa rời nên chưa có giờ nằm bến
# tên: (biến, cửa sổ tháng; None = toàn bộ quá khứ)
MODELS = {
    'A: giờ + sức chở':          (['hours', 'teu'], None),
    'B: chỉ sức chở':            (['teu'], None),
    'C: chỉ giờ bến':            (['hours'], None),
    'D: chỉ giờ bến, 12 tháng':  (['hours'], 12),
    'E: giờ + sức chở, 12 tháng': (['hours', 'teu'], 12),
    'F: chỉ sức chở, 12 tháng':  (['teu'], 12),
    'G: chỉ giờ bến, 6 tháng':   (['hours'], 6),          # cửa sổ ngắn: bám khi năng suất TEU/giờ đổi (HICT 2026)
    'H: giờ + sức chở, 6 tháng': (['hours', 'teu'], 6),
    'I: chỉ sức chở, 6 tháng':   (['teu'], 6),
    'J: chỉ giờ bến, 3 tháng':   (['hours'], 3),
    'K: chỉ sức chở, 3 tháng':   (['teu'], 3),
}
NAIVE = 'Naive: tháng trước'
RECENT_BT = 6               # chọn mô hình theo điểm = TB(MAPE cả lịch sử, MAPE 6 tháng backtest gần nhất)
BAND_Q = 0.8                # khoảng ước/dự báo = ± sai số backtest phân vị 80%
TARGETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'nowcast_targets.csv')   # số CÔNG BỐ theo bến (auth, terminal, month, actual_teu)


# ================================================================ biến giải thích
def features(v, last_day):
    """lượt cập bến (đã lọc phạm vi) -> bảng tháng: calls, teu, hours, days_obs, days_month, partial. last_day = ngày dữ liệu cuối."""
    last_day = pd.Timestamp(last_day) - pd.Timedelta(days=LAG_DAYS)      # tàu vào mấy ngày cuối chưa rời -> thiếu giờ bến
    d = v[v['arr_day'].notna() & (v['arr_day'] <= last_day)].copy()
    if d.empty: return pd.DataFrame()
    for c in ('teu', 'dwt', 'hours_in_port'): d[c] = pd.to_numeric(d[c], errors='coerce').astype(float)
    both = (d['teu'] > 0) & (d['dwt'] > 0)
    ratio = (d.loc[both, 'dwt'] / d.loc[both, 'teu']).median() if both.any() else np.nan
    miss = d['teu'].isna() | (d['teu'] <= 0)
    if pd.notna(ratio): d.loc[miss, 'teu'] = d.loc[miss, 'dwt'] / ratio
    d['hours_c'] = d['hours_in_port'].clip(upper=HOURS_CAP)
    d['m'] = me(d['arr_day'])
    f = d.groupby('m').agg(calls=('arr_day', 'size'), teu=('teu', 'sum'), hours=('hours_c', 'sum'))
    f = f.reindex(pd.date_range(f.index.min(), f.index.max(), freq='ME'), fill_value=0)
    # tháng ĐẦU chuỗi thiếu (dữ liệu bắt đầu giữa tháng, vd Cái Mép trong cảng vụ HCM từ cuối 07/2025: 2 lượt -> 1.952 TEU/giờ
    # so ~150 các tháng khác) -> bỏ, không thì lệch hệ số hồi quy
    if len(f) > 1 and d['arr_day'].min().day > 5: f = f.iloc[1:]
    f['days_month'] = f.index.days_in_month
    f['days_obs'] = f['days_month']
    lm = me(last_day)
    if lm in f.index: f.loc[lm, 'days_obs'] = pd.Timestamp(last_day).day
    f['partial'] = f['days_obs'] < f['days_month']
    f.attrs['dwt_per_teu'] = ratio
    return f


def econdb_monthly(series, locodes):
    """container full EconDB (Nhập + Xuất + Trung chuyển, tuần) -> TEU/tháng dương lịch (chia mỗi tuần đều 7 ngày); bỏ tháng chưa trọn."""
    d = series[(series['metric'] == 'traffic') & series['scope'].isin(locodes)]
    if d.empty: return pd.Series(dtype=float)
    w = d.groupby('date')['value'].sum().sort_index()
    first, last = w.index.min(), w.index.max()
    dd = (w / 7).reindex(pd.date_range(first, last + pd.Timedelta(days=6), freq='D')).ffill(limit=6)
    m = dd.groupby(me(dd.index)).sum(min_count=1)
    if last + pd.Timedelta(days=6) < last + pd.offsets.MonthEnd(0): m = m.iloc[:-1]
    if first.day > 1: m = m.iloc[1:]
    return m.dropna()


# ================================================================ sản lượng thực tế THEO BẾN từ EconDB
def nfc(s): return unicodedata.normalize('NFC', str(s))      # tên bến cảng vụ ĐN lưu dạng NFD ('BẾN CẢNG TIÊN SA' 18 ký tự)


def _members(t): return tuple(nfc(x) for x in t) if isinstance(t, (tuple, list)) else (nfc(t),)


def terminal_series(series, locodes, term_map, terminal, today=None):
    """throughput theo terminal của EconDB (term_throughput, tháng) cho bến cảng vụ `terminal` qua term_map {locode: {mã: bến}}.
    Bỏ tháng đang chạy (EconDB tính cả tàu dự kiến đến) và các tháng 0 ở đầu chuỗi (terminal chưa được tách)."""
    codes = [(lc, k) for lc in locodes for k, t in term_map.get(lc, {}).items() if nfc(terminal) in _members(t)]
    d = series[(series['metric'] == 'term_throughput') & pd.Series(list(zip(series['scope'], series['series'])), index=series.index).isin(codes)]
    if d.empty: return pd.Series(dtype=float)
    s = d.groupby('date')['value'].sum().sort_index(); s.index = me(s.index)      # EconDB ghi 01 tháng -> cuối tháng
    cur = me(today or pd.Timestamp.today())
    s = s[s.index < cur]
    nz = s[s > 0]
    return s[s.index >= nz.index.min()] if len(nz) else pd.Series(dtype=float)


def _nm(s): return ''.join(ch for ch in str(s).upper() if ch.isalnum())


def match_calls(ec_calls, v, tol_days=2):
    """ghép lượt tàu EconDB (ship_name, start, import_count, export_count) với lượt cập bến cảng vụ cùng tên tàu,
    giờ đến lệch <= tol_days -> gán bến. Trả về DataFrame month, terminal, n (container xếp + dỡ). ~92% lượt ghép được (HP 10/2026)."""
    if ec_calls is None or ec_calls.empty or v.empty: return pd.DataFrame(columns=['month', 'terminal', 'n'])
    e = ec_calls.copy(); e['nm'] = e['ship_name'].map(_nm); e['n'] = e['import_count'].fillna(0) + e['export_count'].fillna(0)
    h = v[v['arrival'] >= e['start'].min() - pd.Timedelta(days=tol_days)][['ship', 'arrival', 'terminal']].copy(); h['nm'] = h['ship'].map(_nm)
    m = e.merge(h, on='nm', how='inner')
    m['dt'] = (m['arrival'] - m['start']).abs()
    m = m[m['dt'] <= pd.Timedelta(days=tol_days)].sort_values('dt').drop_duplicates(['locode', 'ship_imo', 'start'])
    m['month'] = me(m['start'])
    out = m.groupby(['month', 'terminal'], as_index=False)['n'].sum()
    out.attrs['match_rate'] = len(m) / max(len(e), 1)
    return out


def terminal_actual(port_monthly, matched, terminal, ec_calls):
    """thực tế bến = container full EconDB của cảng × tỷ trọng container xếp dỡ của bến (lượt EconDB ghép được) trong tháng.
    Chỉ các tháng lượt ghé EconDB phủ trọn tháng. Trả về (Series thực tế, Series tỷ trọng mọi tháng có lượt ghé)."""
    if matched.empty: return pd.Series(dtype=float), pd.Series(dtype=float)
    tot = matched.groupby('month')['n'].sum()
    sh = (matched[matched['terminal'] == terminal].groupby('month')['n'].sum().reindex(tot.index).fillna(0) / tot.replace(0, np.nan)).dropna()
    s0 = ec_calls['start'].min()
    first_full = me(s0) if s0.day <= 2 else me(s0 + pd.offsets.MonthBegin(1))
    act = (port_monthly.reindex(sh.index) * sh)[lambda x: x.index >= first_full].dropna()
    return act, sh


# ================================================================ mô hình
def _fit(X, y):
    coef, *_ = np.linalg.lstsq(np.asarray(X, float), np.asarray(y, float), rcond=None)
    return coef


def run(feat, actual, min_train=MIN_TRAIN, seasonal_ref=None, force=None):
    """feat: features(); actual: Series tháng -> TEU thực tế. Trả về dict hoặc None nếu không đủ dữ liệu.
    data: bảng tháng (actual, modeled, backtest, nowcast, forecast, lo, hi, kind) ; mape: {mô hình: %}; best, coef, cols."""
    if feat.empty or actual is None or actual.empty: return None
    full = feat[~feat['partial']]
    train = full.join(actual.rename('actual'), how='inner').dropna(subset=['actual'])
    train = train[(train['actual'] > 0) & (train['teu'] > 0)]
    if len(train) < min_train + 3: return None
    bt = pd.DataFrame({'actual': train['actual'].iloc[min_train:]})
    for name, (cols, window) in MODELS.items():
        preds = []
        for i in range(min_train, len(train)):
            lo = 0 if window is None else max(0, i - window)
            tr = train.iloc[lo:i]
            preds.append(float(train[cols].iloc[i].values @ _fit(tr[cols], tr['actual'])))
        bt[name] = preds
    bt[NAIVE] = train['actual'].shift(1).iloc[min_train:].values
    mape = {c: float(np.mean(np.abs(bt[c] / bt['actual'] - 1)) * 100) for c in list(MODELS) + [NAIVE]}
    rec = bt.tail(RECENT_BT)
    mape_recent = {c: float(np.mean(np.abs(rec[c] / rec['actual'] - 1)) * 100) for c in list(MODELS) + [NAIVE]}
    auto = min(MODELS, key=lambda c: 0.5 * mape[c] + 0.5 * mape_recent[c])
    best = force if force in MODELS else auto                      # force: PV2 chọn tay mô hình cho bến
    # fit TRONG MẪU của từng mô hình (hệ số cuối) trên mọi tháng có biến -> đối chiếu 'model fit' như biểu đồ PV2
    scale_all = (feat['days_month'] / feat['days_obs'].clip(lower=1)).where(feat['partial'], 1.0)
    fits = pd.DataFrame(index=feat.index)
    for name, (cols_m, win_m) in MODELS.items():
        rows_m = train if win_m is None else train.iloc[-win_m:]
        fits[name] = feat[cols_m].mul(scale_all, axis=0).values @ _fit(rows_m[cols_m], rows_m['actual'])
    fit_err = {c: float(np.mean(np.abs(fits.loc[train.index, c] / train['actual'] - 1)) * 100) for c in MODELS}
    cols, window = MODELS[best]
    rows = train if window is None else train.iloc[-window:]
    coef = _fit(rows[cols], rows['actual'])
    # khoảng = ± sai số PHÂN VỊ 80% của backtest (16/10/2026: ± MAPE chỉ trùm 33/68 tháng công bố mới = 49%)
    err = float(np.quantile(np.abs(bt[best] / bt['actual'] - 1), BAND_Q))

    data, seas = _assemble(feat, actual, cols, coef, err, seasonal_ref, bt[best])
    return {'data': data, 'mape': mape, 'mape_recent': mape_recent, 'fit_err': fit_err, 'fits': fits, 'auto': auto, 'best': best, 'cols': cols,
            'coef': dict(zip(cols, coef)), 'backtest': bt, 'n_bt': len(bt),
            'n_train': len(train), 'seasonal': seas, 'dwt_per_teu': feat.attrs.get('dwt_per_teu')}


# ================================================================ số CÔNG BỐ theo bến (ưu tiên hơn EconDB khi có)
def load_targets():
    if not os.path.exists(TARGETS): return pd.DataFrame(columns=['auth', 'terminal', 'month', 'actual_teu'])
    t = pd.read_csv(TARGETS, dtype={'auth': str, 'terminal': str, 'month': str})
    t['month'] = me(pd.to_datetime(t['month'].str[:7] + '-01', errors='coerce')); t['actual_teu'] = pd.to_numeric(t['actual_teu'], errors='coerce')
    return t.dropna(subset=['month', 'actual_teu'])


def own_min_train(feat, actual):
    """min_train cho bến TỰ hồi quy: đủ MIN_TRAIN_TERM+3 tháng trùng (biến × số công bố) -> MIN_TRAIN_TERM; 7–8 tháng (vd Cái Mép:
    cảng vụ HCM mới có từ 07/2025) -> trùng - 3 (backtest 3 điểm, kém chắc chắn); < 7 -> None (dùng hệ số nhóm)"""
    if feat is None or feat.empty or actual is None or actual.empty: return None
    n = len(feat[~feat['partial'] & (feat['teu'] > 0)].join(actual.rename('_y'), how='inner').dropna(subset=['_y']))
    if n >= MIN_TRAIN_TERM + 3: return MIN_TRAIN_TERM
    return n - 3 if n >= 7 else None


def target_group(t, auth, terminal):
    """tên nhóm trong file chứa bến này: 'CHUA VE+TAN VU' (số công bố gộp 2 bến) hoặc chính tên bến; None nếu không có"""
    for g in t.loc[t['auth'] == auth, 'terminal'].drop_duplicates():
        if nfc(terminal) in [nfc(x.strip()) for x in str(g).split('+')]: return str(g)
    return None


def target_series(t, auth, terminal):
    """chuỗi số công bố của bến (hoặc của nhóm chứa bến, vd Chùa Vẽ + Tân Vũ công bố chung)"""
    g = target_group(t, auth, terminal)
    if g is None: return pd.Series(dtype=float)
    s = t[(t['auth'] == auth) & (t['terminal'] == g)].set_index('month')['actual_teu'].sort_index()
    return s[~s.index.duplicated(keep='last')]


def save_targets(auth, terminal, rows):
    """thay toàn bộ số của (auth, terminal) bằng rows (cột month, actual_teu)"""
    old = load_targets(); old = old[~((old['auth'] == auth) & (old['terminal'].map(nfc) == nfc(terminal)))]
    new = rows.dropna(subset=['month', 'actual_teu']).assign(auth=auth, terminal=terminal); new['month'] = pd.to_datetime(new['month'])
    out = pd.concat([old, new[['auth', 'terminal', 'month', 'actual_teu']]], ignore_index=True).sort_values(['auth', 'terminal', 'month'])
    out['month'] = out['month'].dt.strftime('%Y-%m'); out.to_csv(TARGETS, index=False, encoding='utf-8')


def _assemble(feat, actual, cols, coef, err, seasonal_ref=None, bt_series=None):
    """dựng bảng tháng (thực tế / nowcast / dự báo / khoảng) từ hệ số đã có; dùng cho run() và hệ số chung"""
    data = feat.join(actual.rename('actual'), how='left')
    scale = (data['days_month'] / data['days_obs'].clip(lower=1)).where(data['partial'], 1.0)
    data['modeled'] = (data[cols].mul(scale, axis=0).values @ coef)        # tháng đang chạy: biến quy ra cả tháng
    data['backtest'] = (bt_series.reindex(data.index) if bt_series is not None else data['modeled'])   # không backtest (hệ số chung): vẽ đường mô hình
    data['kind'] = np.where(data['actual'].notna(), 'thực tế', ''); data['nowcast'] = np.nan; data['forecast'] = np.nan; data['w'] = np.nan
    last_act = actual.index.max() if len(actual) else feat.index.min() - pd.Timedelta(days=1)
    nc = data['actual'].isna() & ~data['partial'] & (data.index > last_act)      # tháng trọn SAU thực tế cuối, có biến chưa có thực tế
    data.loc[nc, 'nowcast'] = data.loc[nc, 'modeled']; data.loc[nc, 'kind'] = 'nowcast'; data.loc[nc, 'w'] = 1.0

    # dự báo thuần (không cần biến tháng đích): biến = TB 3 tháng trọn gần nhất (B) × mùa vụ; mùa vụ từ chuỗi THỰC TẾ năm trước
    # = thực tế(tháng đích - 1 năm) / TB thực tế(B - 1 năm), chặn 0,7–1,35 (không lấy từ biến vì có thể gãy do đổi phạm vi)
    full = feat[~feat['partial']]; B = full.index[-3:]; base = full.loc[B, cols].mean()

    sref = seasonal_ref if seasonal_ref is not None and len(seasonal_ref) else actual     # mùa vụ: chuỗi cảng mượt hơn chuỗi bến

    def forecast(tm):
        seas, ly_, lyb = 1.0, ly(tm), [ly(x) for x in B]
        if ly_ in sref.index and all(x in sref.index for x in lyb) and sref.loc[lyb].mean() > 0:
            seas = float(np.clip(sref.loc[ly_] / sref.loc[lyb].mean(), 0.7, 1.35))
        return float(base.values @ coef) * seas, seas

    # NOWCAST tháng đang chạy = w × (biến đã có quy ra cả tháng) + (1 - w) × dự báo thuần, w = số ngày đã có / số ngày tháng
    # (dưới MIN_DAYS_PARTIAL ngày thì w = 0: biến vài ngày đầu tháng quá nhiễu)
    cur = feat.index.max()
    if cur in data.index and data.loc[cur, 'partial'] and pd.isna(data.loc[cur, 'actual']):
        f, _ = forecast(cur); dobs, dmon = data.loc[cur, 'days_obs'], data.loc[cur, 'days_month']
        w = float(dobs / dmon) if dobs >= MIN_DAYS_PARTIAL else 0.0
        data.loc[cur, ['forecast', 'w', 'nowcast', 'kind']] = [f, w, w * data.loc[cur, 'modeled'] + (1 - w) * f, 'nowcast (tháng đang chạy)']
    data = data[data['kind'] != '']
    nxt = me(cur + pd.Timedelta(days=1)); f, seas = forecast(nxt)      # cuối tháng kế tiếp
    data = pd.concat([data, pd.DataFrame({'forecast': [f], 'actual': [np.nan], 'kind': ['dự báo tháng tới'], 'w': [0.0]}, index=[nxt])])
    data['est'] = data['nowcast'].fillna(data['forecast'])
    band = err * (1.5 - 0.5 * data['w'].fillna(0))                  # biến càng đủ (w -> 1) khoảng càng hẹp (±MAPE), dự báo thuần ±1,5×MAPE
    data['lo'] = data['est'] * (1 - band); data['hi'] = data['est'] * (1 + band)
    data.index.name = 'Tháng'
    return data, seas


# ================================================================ HỆ SỐ CHUNG: bến không có số công bố -> OLS gộp các bến đã có số công bố
POOL_WINDOW = 12


CLASS_RULES = {'nước sâu': 'tàu TB ≥ 4.000 TEU', 'sông lớn': 'tàu < 4.000 TEU, sức chở ≥ 50.000 TEU/tháng', 'sông nhỏ': 'còn lại'}


def terminal_class(feat, months=12):
    """nhóm bến theo chính dữ liệu bến: cỡ tàu bình quân (TEU/lượt) và quy mô (sức chở/tháng) 12 tháng trọn gần nhất"""
    f = feat[~feat['partial']].tail(months)
    if f.empty or f['calls'].sum() == 0: return 'sông nhỏ'
    ship = f['teu'].sum() / f['calls'].sum(); cap = f['teu'].mean()
    return 'nước sâu' if ship >= 4000 else ('sông lớn' if cap >= 50000 else 'sông nhỏ')


def pooled_coef(pairs, window=POOL_WINDOW, label='chung'):
    """pairs: [(features, actual công bố)] -> hệ số chung: OLS gộp không chặn, mỗi bến lấy `window` tháng cuối có số; thử 3 bộ biến
    (giờ + sức chở / giờ / sức chở), chỉ nhận hệ số >= 0, chọn MAPE trong mẫu thấp nhất. None nếu < 2 bến."""
    rows = []
    for f, a in pairs:
        t = f[~f['partial']].join(a.rename('actual'), how='inner'); t = t[(t['actual'] > 0) & (t['teu'] > 0)]
        if len(t) >= 3: rows.append(t.iloc[-window:])
    if len(rows) < 2: return None
    tr = pd.concat(rows); best = None
    for cols in (['hours', 'teu'], ['hours'], ['teu']):
        coef = _fit(tr[cols], tr['actual'])
        if (coef < 0).any(): continue
        err = float(np.mean(np.abs(tr[cols].values @ coef / tr['actual'] - 1)))
        if best is None or err < best['err']:
            best = {'coef': dict(zip(cols, coef)), 'cols': cols, 'err': err, 'n_terms': len(rows), 'n_months': len(tr), 'label': label}
    return best


def pooled_by_class(pairs, window=POOL_WINDOW):
    """{nhóm: hệ số chung của nhóm} từ các bến có số công bố (nhóm < 2 bến thì không có -> dùng 'chung' = mọi bến)"""
    out = {'chung': pooled_coef(pairs, window, 'chung')}
    by = {}
    for f, a in pairs: by.setdefault(terminal_class(f), []).append((f, a))
    for cls, pr in by.items():
        pc = pooled_coef(pr, window, cls)
        if pc: out[cls] = pc
    return out


def apply_pooled(feat, pooled, actual=None, seasonal_ref=None):
    """ước/dự báo 1 bến bằng hệ số chung; actual = số công bố ngắn của bến (nếu có) chỉ để vẽ"""
    if feat.empty or pooled is None or not (feat['teu'] > 0).any(): return None
    actual = actual if actual is not None else pd.Series(dtype=float)
    cols = pooled['cols']; coef = np.array([pooled['coef'][c] for c in cols]); err = pooled['err']
    data, seas = _assemble(feat, actual, cols, coef, err, seasonal_ref, None)
    label = f"hệ số {pooled.get('label', 'chung')} ({pooled['n_terms']} bến công bố)"
    return {'data': data, 'mape': {label: err * 100}, 'mape_recent': {label: err * 100}, 'best': label, 'cols': cols, 'coef': pooled['coef'],
            'backtest': None, 'n_bt': 0, 'n_train': pooled['n_months'], 'seasonal': seas, 'dwt_per_teu': feat.attrs.get('dwt_per_teu'), 'pooled': True}


# ================================================================ hồi quy RIÊNG từng cảng EconDB rồi cộng
def combine(parts, label=None):
    """cộng kết quả run() của nhiều cảng thành 1 kết quả cùng dạng: data = tổng theo tháng chung (chỉ tháng mọi cảng đều có),
    MAPE = sai số của TỔNG backtest so với TỔNG thực tế (và naive tháng trước của tổng). parts giữ kết quả từng cảng."""
    parts = {k: v for k, v in parts.items() if v}
    if not parts: return None
    if len(parts) == 1:
        r = dict(next(iter(parts.values()))); r['parts'] = parts; return r
    label = label or f'tổng {len(parts)} cảng'
    idx = None
    for p in parts.values(): idx = p['data'].index if idx is None else idx.intersection(p['data'].index)
    cols = ['actual', 'modeled', 'backtest', 'nowcast', 'forecast', 'est', 'lo', 'hi']
    data = pd.DataFrame({c: pd.concat([p['data'].loc[idx, c] for p in parts.values()], axis=1).sum(axis=1, min_count=len(parts)) for c in cols}, index=idx)
    first = next(iter(parts.values()))['data']
    data['kind'] = first.loc[idx, 'kind']; data['w'] = first.loc[idx, 'w']
    for c in ('calls', 'teu', 'hours', 'days_obs'):
        if all(c in p['data'] for p in parts.values()):
            data[c] = pd.concat([p['data'].loc[idx, c] for p in parts.values()], axis=1).sum(axis=1, min_count=1) if c != 'days_obs' else first.loc[idx, c]
    data.index.name = 'Tháng'
    m = data[['actual', 'backtest']].dropna()
    a = data['actual'].dropna(); naive = a.shift(1).reindex(m.index)
    mape = {label: float(np.mean(np.abs(m['backtest'] / m['actual'] - 1)) * 100) if len(m) else np.nan,
            NAIVE: float(np.mean(np.abs(naive / m['actual'] - 1)) * 100) if len(m) else np.nan}
    mr = m.tail(RECENT_BT); nr = naive.reindex(mr.index)
    mape_recent = {label: float(np.mean(np.abs(mr['backtest'] / mr['actual'] - 1)) * 100) if len(mr) else np.nan,
                   NAIVE: float(np.mean(np.abs(nr / mr['actual'] - 1)) * 100) if len(mr) else np.nan}
    return {'data': data, 'mape': mape, 'mape_recent': mape_recent, 'best': label, 'cols': [], 'coef': {}, 'backtest': None, 'n_bt': len(m),
            'n_train': min(p['n_train'] for p in parts.values()), 'seasonal': float(np.mean([p['seasonal'] for p in parts.values()])),
            'dwt_per_teu': np.nan, 'parts': parts}


def fit_ports(v, series, locodes, term_port, last_day):
    """v: lượt cập bến tàu container của cảng vụ; term_port(bến) -> locode EconDB. Chạy run() RIÊNG cho từng cảng EconDB
    (biến = bến thuộc cảng đó, thực tế = container full EconDB của cảng đó) rồi combine -> cảng vụ = tổng các cảng."""
    parts = {}
    for lc in locodes:
        vv = v if len(locodes) == 1 else v[v['terminal'].map(term_port) == lc]
        parts[lc] = run(features(vv, last_day), econdb_monthly(series, [lc]))
    return combine(parts)


def summary(res):
    """1 dòng tóm tắt cho bảng toàn quốc"""
    d = res['data']; a = d['actual'].dropna()
    nc = d[d['kind'].str.startswith('nowcast')]
    fc = d[d['kind'] == 'dự báo tháng tới']
    row = {'Thực tế cuối': f'{a.index[-1]:%m/%Y}' if len(a) else '', 'TEU thực tế cuối': a.iloc[-1] if len(a) else np.nan}
    if len(nc): row.update({'Ước tháng': f'{nc.index[-1]:%m/%Y}', 'Ước TEU': nc['est'].iloc[-1]})
    if len(fc): row.update({'Dự báo tháng': f'{fc.index[-1]:%m/%Y}', 'Dự báo TEU': fc['est'].iloc[-1]})
    yo = None
    if len(fc):
        ly_ = ly(fc.index[-1])
        if ly_ in d.index and pd.notna(d.loc[ly_, 'actual']): yo = fc['est'].iloc[-1] / d.loc[ly_, 'actual'] - 1
    row.update({'Dự báo so cùng kỳ (%)': None if yo is None else yo * 100, 'MAPE backtest (%)': res['mape'][res['best']],
                'MAPE naive (%)': res['mape'].get(NAIVE), 'Mô hình': res['best'], 'Số tháng huấn luyện': res['n_train']})
    return row
