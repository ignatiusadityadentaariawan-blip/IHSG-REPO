"""Jalankan semua: unduh data -> backtest/OOS/forward 5 varian -> screener semua emiten -> sinyal -> tulis data/ untuk web & Excel.
   python ihsg_lab/build_site.py          (data asli Yahoo Finance, dipakai GitHub Actions)
   python ihsg_lab/build_site.py --demo   (data sintetis, untuk uji)"""
import os, sys, json, math, datetime as dt, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import *
from engine import features, run, metrics, gate, tick, fl, ce, _ema, _rsi, _atr
import data as D

DEMO = "--demo" in sys.argv
OUT = os.path.join(D.ROOT, "data"); os.makedirs(os.path.join(OUT, "ohlc"), exist_ok=True); os.makedirs(os.path.join(OUT, "intra"), exist_ok=True)
NOW = dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).replace(tzinfo=None)
XL0 = pd.Timestamp("1899-12-30")

def j(x):
    if isinstance(x, (np.floating, float)): return None if not np.isfinite(x) else round(float(x), 4)
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (pd.Timestamp, dt.datetime, dt.date)): return str(x)
    return x
def dump(name, obj): json.dump(obj, open(os.path.join(OUT, name), "w"), default=j, separators=(",", ":"))

def plan(v, F, tk, i):
    """Rencana order dari sinyal di bar i (estimasi entry = close i)."""
    E = F["close"][i] + SLIP_TICKS * tick(F["close"][i]); sl = fl(E - v["sl_atr"] * F["atr"][i]); risk = v["risk_pct"] * CAPITAL
    per = (E - sl) + SLIP_TICKS * tick(sl) + E * FEE_BUY + sl * FEE_SELL
    lots = max(0, min(math.floor(risk / (per * LOT)), math.floor(v["max_pos_pct"] * CAPITAL / (E * LOT * (1 + FEE_BUY)))))
    tp = ce(E + v["tp_r"] * (E - sl)) if v["tp_r"] else None
    return dict(variant=v["id"], ticker=tk, entry=E, sl=sl, tp=tp, trail=v["trail_atr"] or None, lots=lots, value=lots * LOT * E,
                risk_rp=lots * LOT * per, sl_pct=(E - sl) / E * 100, time=str(F["t"][i]))

def main():
    codes, src = D.universe()
    if DEMO:
        daily = D.demo_daily(codes); intra = D.demo_intraday(SCALP_UNIVERSE)
        jk = D.demo_daily(["JKSE"])["JKSE"] * 1.0; jk[["open", "high", "low", "close"]] *= 6000 / jk.close.iloc[-1]
    else:
        daily = D.daily(codes); intra = D.intraday(SCALP_UNIVERSE); jk = D.index_jkse()
    summary = dict(updated=NOW.strftime("%Y-%m-%d %H:%M"), demo=DEMO, universe_src=src, n_universe=len(codes), n_loaded=len(daily),
                   capital=CAPITAL, fee_buy=FEE_BUY, fee_sell=FEE_SELL, forward_start=FORWARD_START, criteria=CRITERIA, variants=[])
    eq, trades_out, signals = {}, [], []
    for v in VARIANTS:
        src_d = {k: d for k, d in (daily.items() if v["kind"] == "swing" else intra.items()) if len(d) > 60}
        F = {k: features(d, v) for k, d in src_d.items()}
        if v["kind"] == "swing":
            s0 = min(d.index[0] for d in src_d.values()) + pd.Timedelta(days=300); split = pd.Timestamp(SPLIT_DAILY)
        else:
            allt = sorted(set().union(*[set(d.index) for d in src_d.values()])); pre = [t for t in allt if t < pd.Timestamp(FORWARD_START)]
            s0 = pre[min(len(pre) - 1, 66)] if pre else allt[0]
            split = pre[int(len(pre) * INTRA_BT_SHARE)] if pre else allt[0]
        fw = pd.Timestamp(FORWARD_START)
        tb, cb, _ = run(v, F, s0, split); to, co, _ = run(v, F, split, fw); tf, cf, op = run(v, F, fw, None)
        mb, mo = metrics(tb, cb, v), metrics(to, co, v); mf = metrics(tf, cf, v) if len(cf) else None
        st, basis = gate(mb, mo, mf, CRITERIA)
        for p in op: p["upnl"] = p["lots"] * LOT * (p["last"] * (1 - FEE_SELL) - p["entry"] * (1 + FEE_BUY))
        summary["variants"].append(dict({k: v[k] for k in ("id", "name", "kind", "profile", "tf", "desc", "sl_atr", "tp_r", "trail_atr", "time_stop", "max_pos", "day_cap")},
                                        risk_rp=v["risk_pct"] * CAPITAL, bt=mb, oos=mo, fwd=mf, status=st, basis=basis, open=op,
                                        period=dict(bt=[str(s0)[:16], str(split)[:16]], oos=[str(split)[:16], FORWARD_START])))
        day = lambda c: [[str(t.date()), round(float(x))] for t, x in c.resample("1D").last().dropna().items()] if len(c) else []
        eq[v["id"]] = dict(bt=day(cb), oos=day(co), fwd=day(cf))
        for ph, t in (("BT", tb), ("OOS", to), ("FWD", tf)):
            if not t.empty: trades_out += [dict(r, phase=ph) for r in t.tail(150 if ph == "FWD" else 60).to_dict("records")]
        # sinyal aktif di bar terakhir
        for tk, f in F.items():
            i = len(f["close"]) - 1
            if f["sig"][i] == 1 and (v["kind"] == "swing" or f["t"][i].date() == max(ff["t"][-1] for ff in F.values()).date()):
                signals.append(dict(plan(v, f, tk, i), score=float(f["score"][i])))
        print(f'{v["id"]} BT n={mb["trades"]} PF={mb["pf"]:.2f} ExpR={mb["exp_r"]:+.2f} | OOS n={mo["trades"]} PF={mo["pf"]:.2f} | FWD n={(mf or {}).get("trades",0)} -> {st}')
    # ---------- screener ----------
    rows = []
    sw = {v["id"]: v for v in VARIANTS}
    for tk, d in daily.items():
        if len(d) < 60: continue
        c = d.close; i = len(d) - 1; e20, e50, e200 = _ema(c, 20), _ema(c, 50), _ema(c, 200); a = _atr(d); r14 = _rsi(c, 14)
        val20 = float((c * d.volume).rolling(20).mean().iloc[-1]); vr = float(d.volume.iloc[-1] / d.volume.rolling(20).mean().iloc[-2]) if len(d) > 21 else np.nan
        trend = int(c.iloc[-1] > e20.iloc[-1]) + int(e20.iloc[-1] > e50.iloc[-1]) + int(e50.iloc[-1] > e200.iloc[-1])
        hh20 = d.high.rolling(20).max().iloc[-1]; hi52, lo52 = d.high.tail(250).max(), d.low.tail(250).min()
        ch = lambda n: float(c.iloc[-1] / c.iloc[-1 - n] - 1) * 100 if len(c) > n else np.nan
        mom = np.nanmean([ch(20), ch(60) / 2]); liq = np.log10(max(val20, 1e6)) - 9
        score = round(trend * 15 + np.clip(mom, -20, 20) + np.clip(liq, 0, 3) * 10 + (10 if 45 <= r14.iloc[-1] <= 70 else 0), 1)
        sigs = [s for s in signals if s["ticker"] == tk and sw[s["variant"]]["kind"] == "swing"]
        action = "BUY SETUP" if sigs else ("AVOID" if trend == 0 or val20 < 1e9 else "WATCH" if trend >= 2 else "NEUTRAL")
        best = max(sigs, key=lambda s: {"S1": 3, "S2": 2, "S3": 1}[s["variant"]]) if sigs else {}
        rows.append(dict(code=tk, close=float(c.iloc[-1]), chg1=ch(1), chg5=ch(5), chg20=ch(20), value20_bn=val20 / 1e9, vol_ratio=vr, rsi14=float(r14.iloc[-1]),
                         atr_pct=float(a.iloc[-1] / c.iloc[-1] * 100), trend=trend, dist20h=float(c.iloc[-1] / hh20 - 1) * 100,
                         pos52=float((c.iloc[-1] - lo52) / (hi52 - lo52) * 100) if hi52 > lo52 else 50, score=score, action=action,
                         variants="/".join(s["variant"] for s in sigs), entry=best.get("entry"), sl=best.get("sl"), tp=best.get("tp"), lots=best.get("lots")))
        o = d.tail(500); pd.DataFrame(dict(xl=((o.index - XL0).days).astype(int), open=o.open, high=o.high, low=o.low, close=o.close, volume=o.volume.astype(np.int64),
                                           date=o.index.strftime("%Y-%m-%d"))).to_csv(os.path.join(OUT, "ohlc", f"{tk}.csv"), index=False, lineterminator="\n")
    for tk, d in intra.items():
        o = d.tail(450); xl = ((o.index - XL0) / pd.Timedelta(days=1)).round(6)
        pd.DataFrame(dict(xl=xl, open=o.open, high=o.high, low=o.low, close=o.close, volume=o.volume.astype(np.int64), time=o.index.strftime("%Y-%m-%d %H:%M"))
                     ).to_csv(os.path.join(OUT, "intra", f"{tk}.csv"), index=False, lineterminator="\n")
    scr = pd.DataFrame(rows).sort_values("score", ascending=False)
    dump("screener.json", scr.round(3).replace({np.nan: None}).to_dict("records"))
    cols = ["code", "close", "chg1", "chg5", "chg20", "value20_bn", "vol_ratio", "rsi14", "atr_pct", "trend", "dist20h", "pos52", "score", "action", "variants", "entry", "sl", "tp", "lots"]
    for k in range(5):
        part = scr.iloc[k * 200:(k + 1) * 200]
        part[cols].round(2).to_csv(os.path.join(OUT, f"screener_{k + 1}.csv"), index=False, header=False, lineterminator="\n")
    # ---------- index & market breadth ----------
    c = jk.close; e = lambda n: float(_ema(c, n).iloc[-1])
    summary["ihsg"] = dict(close=float(c.iloc[-1]), chg=float(c.iloc[-1] / c.iloc[-2] - 1) * 100, ema20=e(20), ema50=e(50), ema200=e(200), rsi14=float(_rsi(c, 14).iloc[-1]),
                           hi52=float(jk.high.tail(250).max()), lo52=float(jk.low.tail(250).min()), date=str(jk.index[-1].date()),
                           spark=[round(float(x), 1) for x in c.tail(60)])
    summary["breadth"] = dict(up=int((scr.chg1 > 0).sum()), down=int((scr.chg1 < 0).sum()), uptrend=int((scr.trend >= 2).sum()), buy_setups=int((scr.action == "BUY SETUP").sum()), total=len(scr))
    summary["n_pass"] = sum(1 for x in summary["variants"] if x["status"] == "PASS")
    dump("summary.json", summary); dump("equity.json", eq); dump("trades.json", trades_out)
    dump("signals.json", sorted(signals, key=lambda s: (s["variant"], -s["score"])))
    rc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "research.json")
    if os.path.exists(rc): dump("research.json", json.load(open(rc)))
    print("OK", summary["updated"], "| screener", len(scr), "| signals", len(signals))

if __name__ == "__main__": main()
