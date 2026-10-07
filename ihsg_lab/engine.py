import math, numpy as np, pandas as pd
from config import CAPITAL, FEE_BUY as FB, FEE_SELL as FS, SLIP_TICKS as SLIP, LOT

def tick(p): return 1 if p < 200 else 2 if p < 500 else 5 if p < 2000 else 10 if p < 5000 else 25
def fl(p): t = tick(p); return math.floor(p / t + 1e-9) * t
def ce(p): t = tick(p); return math.ceil(p / t - 1e-9) * t

def _ema(s, n): return s.ewm(span=n, adjust=False).mean()
def _wild(s, n): return s.ewm(alpha=1 / n, adjust=False).mean()
def _atr(d, n=14):
    pc = d.close.shift()
    tr = pd.concat([d.high - d.low, (d.high - pc).abs(), (d.low - pc).abs()], axis=1).max(axis=1)
    tr.iloc[0] = d.high.iloc[0] - d.low.iloc[0]
    return _wild(tr, n)
def _rsi(c, n):
    x = c.diff(); up = _wild(x.clip(lower=0), n); dn = _wild((-x).clip(lower=0), n)
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))

def features(d, v):
    """d: OHLCV (index = WIB timestamps). Return dict of arrays. Signal on bar i -> entry at open i+1."""
    d = d.copy(); c = d.close; f = {}
    f["atr"] = _atr(d); e20, e50, e200 = _ema(c, 20), _ema(c, 50), _ema(c, 200)
    f["value20"] = (c * d.volume).rolling(20).mean()
    liq = f["value20"] >= v["min_value"] if v["min_value"] else pd.Series(True, d.index)
    exit_sig = pd.Series(False, d.index); eod = pd.Series(False, d.index); score = f["value20"].fillna(0)
    L = v["logic"]
    if L == "pullback":
        sig = liq & (e50 > e200) & (c > e50) & (d.low <= e20) & (c > e20) & (c > d.open)
    elif L == "breakout":
        hh = d.high.rolling(20).max().shift(); va = d.volume.rolling(20).mean().shift()
        sig = liq & (c > hh) & (d.volume > 1.5 * va) & (c > e50) & (_rsi(c, 14) < 80)
        score = (d.volume / va).fillna(0)
    elif L == "rsi2":
        r2 = _rsi(c, 2); sig = liq & (c > e200) & (r2 < 10); exit_sig = c > c.rolling(5).mean(); score = (100 - r2).fillna(0)
    else:  # intraday
        day = pd.Series(d.index.date, d.index); new = day != day.shift()
        tod = pd.Series(d.index.hour * 60 + d.index.minute, d.index)
        n = d.groupby(day).cumcount() + 1
        nxt = day.shift(-1); eod = (tod >= 930) | ((nxt != day) & nxt.notna())
        late = tod <= 855
        if L == "orb":
            orh = d.high.where(n <= 2).groupby(day).cummax().groupby(day).ffill()
            va = d.volume.rolling(20).mean()
            sig = (n >= 3) & late & (c > orh) & (c.shift() <= orh) & (d.volume > va)
            score = (d.volume / va).fillna(0)
        else:
            tp = (d.high + d.low + c) / 3
            vwap = (tp * d.volume).groupby(day).cumsum() / d.volume.groupby(day).cumsum()
            f["vwap"] = vwap
            sig = (n >= 3) & late & (c > vwap) & (e20 > vwap) & (d.low <= vwap * 1.003) & (c > d.open)
    f["sig"] = sig.fillna(False).astype(int); f["exit"] = exit_sig.fillna(False); f["eod"] = eod; f["score"] = score
    out = {k: np.asarray(s, dtype=float if k not in ("sig", "exit", "eod") else None) for k, s in f.items()}
    for k in ("open", "high", "low", "close", "volume"): out[k] = d[k].to_numpy(float)
    out["t"] = d.index; out["pos"] = {t: i for i, t in enumerate(d.index)}
    return out

def run(v, feats, start=None, end=None, capital=CAPITAL):
    risk = v["risk_pct"] * CAPITAL
    times = sorted(set().union(*[set(F["t"]) for F in feats.values()])) if feats else []
    if start is not None: times = [t for t in times if t >= pd.Timestamp(start)]
    if end is not None: times = [t for t in times if t < pd.Timestamp(end)]
    cash, mtm, pos, trades, curve, daypnl = capital, capital, {}, [], [], {}
    for t in times:
        day = t.date()
        cands = []
        for tk, F in feats.items():
            i = F["pos"].get(t)
            if i is None or i == 0 or tk in pos or F["sig"][i - 1] != 1 or not F["atr"][i - 1] > 0: continue
            cands.append((-F["score"][i - 1], tk, i))
        for _, tk, i in sorted(cands):
            if len(pos) >= v["max_pos"] or (v["day_cap"] and daypnl.get(day, 0) <= -v["day_cap"]): break
            F = feats[tk]; o = F["open"][i]; E = o + SLIP * tick(o); sl = fl(E - v["sl_atr"] * F["atr"][i - 1])
            if sl <= 0 or E - sl <= 0: continue
            per = (E - sl) + SLIP * tick(sl) + E * FB + sl * FS
            lots = math.floor(risk / (per * LOT) + 1e-9)
            lots = min(lots, math.floor(min(cash, v["max_pos_pct"] * mtm) / (E * LOT * (1 + FB)) + 1e-9))
            if lots < 1: continue
            cost = lots * LOT * E * (1 + FB); cash -= cost
            pos[tk] = dict(E=E, sl=sl, sl0=sl, tp=ce(E + v["tp_r"] * (E - sl)) if v["tp_r"] else None, lots=lots, cost=cost, t=t, bars=0)
        for tk in list(pos):
            F = feats[tk]; i = F["pos"].get(t)
            if i is None: continue
            p = pos[tk]; p["bars"] += 1; o, h, l, c = F["open"][i], F["high"][i], F["low"][i], F["close"][i]; X = None
            if l <= p["sl"]:
                m = min(p["sl"], o); X = m - SLIP * tick(m); why = "TRAIL" if X > p["E"] else "SL"
            elif p["tp"] and h >= p["tp"]: X, why = p["tp"], "TP"
            elif F["exit"][i]: X, why = c, "EXIT"
            elif F["eod"][i]: X, why = c, "EOD"
            elif v["time_stop"] and p["bars"] >= v["time_stop"]: X, why = c, "TIME"
            if X is not None:
                proc = p["lots"] * LOT * X * (1 - FS); pnl = proc - p["cost"]; cash += proc
                daypnl[day] = daypnl.get(day, 0) + pnl
                trades.append(dict(variant=v["id"], ticker=tk, entry_time=p["t"], exit_time=t, entry=p["E"], exit=X, sl=p["sl0"], lots=p["lots"],
                                   pnl=pnl, R=pnl / risk, fees=p["lots"] * LOT * (p["E"] * FB + X * FS), reason=why, bars=p["bars"]))
                del pos[tk]
            elif v["trail_atr"]:
                p["sl"] = max(p["sl"], fl(c - v["trail_atr"] * F["atr"][i]))
        mtm = cash + sum(p["lots"] * LOT * feats[tk]["close"][feats[tk]["pos"][t]] if t in feats[tk]["pos"] else p["cost"] for tk, p in pos.items())
        curve.append((t, mtm))
    openp = [dict(ticker=tk, entry=p["E"], sl=p["sl"], tp=p["tp"], lots=p["lots"], since=str(p["t"]), last=float(feats[tk]["close"][-1])) for tk, p in pos.items()]
    cv = pd.Series(dict(curve), dtype=float); cv.index = pd.DatetimeIndex(cv.index)
    return pd.DataFrame(trades), cv, openp

def metrics(tr, cv, v, capital=CAPITAL):
    z = dict(trades=0, win_rate=0.0, pf=0.0, exp_r=0.0, net=0.0, ret_pct=0.0, max_dd_pct=0.0, fees=0.0, avg_bars=0.0, max_losing_streak=0)
    if len(cv): z["max_dd_pct"] = float(((cv.cummax() - cv) / cv.cummax()).max() * 100)
    if tr is None or tr.empty: return z
    w = tr.pnl[tr.pnl > 0].sum(); l = -tr.pnl[tr.pnl <= 0].sum(); s = m = 0
    for x in tr.pnl: s = s + 1 if x <= 0 else 0; m = max(m, s)
    z.update(trades=len(tr), win_rate=float((tr.pnl > 0).mean()), pf=float(min(99, w / l)) if l else (99.0 if w > 0 else 0.0), exp_r=float(tr.R.mean()),
             net=float(tr.pnl.sum()), ret_pct=float(tr.pnl.sum() / capital * 100), fees=float(tr.fees.sum()), avg_bars=float(tr.bars.mean()), max_losing_streak=m)
    return z

def gate(bt, oos, fwd, C):
    m, basis = (fwd, "FWD") if fwd and fwd["trades"] > 0 else (oos, "OOS")
    if m["trades"] < C["min_trades"]: return "COLLECTING", basis
    ok = m["pf"] >= C["min_pf"] and m["exp_r"] >= C["min_exp_r"] and m["max_dd_pct"] <= C["max_dd_pct"] and (bt["exp_r"] <= 0 or m["exp_r"] >= bt["exp_r"] * (1 - C["max_decay"]))
    return ("PASS" if ok else "FAIL"), basis
