import os, json, time, numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "cache"); os.makedirs(os.path.join(CACHE, "d"), exist_ok=True); os.makedirs(os.path.join(CACHE, "i"), exist_ok=True)

def universe():
    """Coba daftar lengkap dari IDX; fallback universe.txt."""
    try:
        import requests
        r = requests.get("https://www.idx.co.id/primary/StockData/GetSecuritiesStock?start=0&length=9999&code=&sector=&board=&language=id-id",
                         headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.idx.co.id/"}, timeout=20)
        codes = sorted({x["Code"] for x in r.json()["data"]})
        if len(codes) > 500: return codes, "IDX"
    except Exception: pass
    txt = open(os.path.join(os.path.dirname(__file__), "universe.txt")).read()
    return sorted({w for line in txt.splitlines() if not line.startswith("#") for w in line.split()}), "universe.txt"

def _seed(path, rel):
    """Cache Actions hilang? Ambil salinan terakhir yang dipublikasikan di GitHub Pages (agar histori forward intraday tidak hilang)."""
    site = os.environ.get("SITE_URL", "").rstrip("/")
    if os.path.exists(path) or not site: return
    try:
        import requests; r = requests.get(f"{site}/{rel}", timeout=20)
        if r.ok and r.text.startswith(","): open(path, "w").write(r.text)
    except Exception: pass

def _merge(path, new):
    old = pd.read_csv(path, index_col=0, parse_dates=True) if os.path.exists(path) else None
    df = pd.concat([old, new]) if old is not None else new
    df = df[~df.index.duplicated(keep="last")].sort_index(); df.to_csv(path); return df

def daily(codes, years=3):
    import yfinance as yf
    out = {}; tick = [c + ".JK" for c in codes]
    have = all(os.path.exists(os.path.join(CACHE, "d", f"{c}.csv")) for c in codes)
    for k in range(0, len(tick), 100):
        chunk = tick[k:k + 100]
        raw = yf.download(chunk, period="10d" if have else f"{years}y", interval="1d", group_by="ticker", auto_adjust=False, progress=False, threads=True)
        for t in chunk:
            try: d = raw[t] if len(chunk) > 1 else raw
            except KeyError: continue
            d = d.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
            d = d[d.volume > 0]
            if d.empty: continue
            d.index = pd.to_datetime(d.index).tz_localize(None)
            out[t[:-3]] = _merge(os.path.join(CACHE, "d", f"{t[:-3]}.csv"), d)
        time.sleep(1)
    return out

def intraday(codes):
    import yfinance as yf
    out = {}
    raw = yf.download([c + ".JK" for c in codes], period="60d", interval="15m", group_by="ticker", auto_adjust=False, progress=False, threads=True)
    for c in codes:
        try: d = raw[c + ".JK"].rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna()
        except KeyError: continue
        idx = pd.to_datetime(d.index)
        d.index = (idx.tz_convert("Asia/Jakarta") if idx.tz is not None else idx).tz_localize(None)
        d = d[(d.index.hour * 60 + d.index.minute >= 540) & (d.index.hour * 60 + d.index.minute <= 945)]
        p = os.path.join(CACHE, "i", f"{c}.csv"); _seed(p, f"data/icache/{c}.csv")
        out[c] = _merge(p, d)   # cache tumbuh terus -> forward test intraday tidak hilang
    return out

def index_jkse():
    import yfinance as yf
    d = yf.download("^JKSE", period="2y", interval="1d", auto_adjust=False, progress=False)
    if isinstance(d.columns, pd.MultiIndex): d.columns = d.columns.get_level_values(0)
    d = d.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].dropna(); d.index = pd.to_datetime(d.index).tz_localize(None); return d

# ---------------- DEMO (sintetis, bukan data pasar) ----------------
def _walk(seed, n, p0, vol):
    r = np.random.default_rng(seed); reg = np.repeat(r.choice([-1, 0, 1], size=n // 60 + 1, p=[.3, .3, .4]), 60)[:n]
    ret = reg * 0.0012 + vol * r.standard_t(4, n) / np.sqrt(2); return p0 * np.exp(np.cumsum(ret)), r

def _ohlc(c, r, vol, base_vol):
    from engine import fl
    o = np.r_[c[0], c[:-1]] * (1 + r.normal(0, vol / 4, len(c)))
    h = np.maximum(o, c) * (1 + np.abs(r.normal(0, vol / 2, len(c)))); l = np.minimum(o, c) * (1 - np.abs(r.normal(0, vol / 2, len(c))))
    f = np.vectorize(lambda x: max(fl(x), 1))
    return pd.DataFrame(dict(open=f(o), high=f(h), low=f(l), close=f(c), volume=(base_vol * r.lognormal(0, .5, len(c))).round(-2)))

def demo_daily(codes, end="2026-10-06"):
    idx = pd.bdate_range(end=end, periods=760); out = {}
    for k, c in enumerate(codes):
        seed = sum((k + 1) * ord(x) for k, x in enumerate(c)); p0 = [150, 400, 1200, 3000, 7000][seed % 5] * (0.7 + (seed % 7) / 10)
        cl, r = _walk(seed, len(idx), p0, 0.022); d = _ohlc(cl, r, 0.022, 2e9 * (1 + seed % 60) / p0); d.index = idx
        d["high"] = d[["open", "high", "close"]].max(axis=1); d["low"] = d[["open", "low", "close"]].min(axis=1); out[c] = d
    return out

def demo_intraday(codes, end="2026-10-06", days=60):
    days_idx = pd.bdate_range(end=end, periods=days)
    slots = [pd.Timedelta(minutes=m) for m in list(range(540, 720, 15)) + list(range(810, 946, 15))]
    idx = pd.DatetimeIndex([d + s for d in days_idx for s in slots]); out = {}
    for c in codes:
        seed = sum((k + 1) * ord(x) for k, x in enumerate(c)) + 7; p0 = [400, 1200, 3000, 7000, 9000][seed % 5]
        cl, r = _walk(seed, len(idx), p0, 0.004); d = _ohlc(cl, r, 0.004, 1.5e9 * (1 + seed % 5) / p0); d.index = idx
        d["high"] = d[["open", "high", "close"]].max(axis=1); d["low"] = d[["open", "low", "close"]].min(axis=1); out[c] = d
    return out
