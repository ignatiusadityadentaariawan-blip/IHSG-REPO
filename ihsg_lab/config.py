"""IHSG Paper Lab – konfigurasi. Modal 100 jt, 5 varian (3 swing harian + 2 scalp 15 menit)."""
CAPITAL = 100_000_000          # Rp per varian (paper)
FEE_BUY = 0.001513             # Ajaib: termasuk broker, levy, PPN (limit order)
FEE_SELL = 0.002513            # Ajaib: + PPh final 0,1%
SLIP_TICKS = 1                 # slippage 1 tick saat entry & saat kena SL
LOT = 100
FORWARD_START = "2026-10-07"   # mulai paper forward test (WIB)
SPLIT_DAILY = "2025-10-01"     # backtest  < split <= OOS < forward
INTRA_BT_SHARE = 0.6           # data 15m Yahoo hanya ~60 hari: 60% BT, 40% OOS
CRITERIA = dict(min_trades=30, min_pf=1.20, min_exp_r=0.10, max_dd_pct=10.0, max_decay=0.50)

V = lambda **k: k
VARIANTS = [
 V(id="S1", name="Blue Chip Pullback", kind="swing", profile="Konservatif", tf="1d", logic="pullback",
   min_value=50e9, sl_atr=2.0, tp_r=2.0, trail_atr=0, time_stop=20, risk_pct=0.005, max_pos=5, max_pos_pct=0.25, day_cap=0,
   desc="Saham likuid (nilai transaksi ≥ Rp50 M/hari) dalam uptrend (EMA50>EMA200), beli saat pullback ke EMA20 dan candle hijau."),
 V(id="S2", name="Breakout Momentum", kind="swing", profile="Moderat", tf="1d", logic="breakout",
   min_value=20e9, sl_atr=1.5, tp_r=0, trail_atr=2.5, time_stop=30, risk_pct=0.0075, max_pos=6, max_pos_pct=0.20, day_cap=0,
   desc="Tembus high 20 hari dengan volume ≥1,5× rata-rata, di atas EMA50, RSI<80. Keluar dengan trailing stop 2,5 ATR."),
 V(id="S3", name="Oversold Rebound", kind="swing", profile="Moderat-agresif", tf="1d", logic="rsi2",
   min_value=10e9, sl_atr=2.5, tp_r=0, trail_atr=0, time_stop=7, risk_pct=0.01, max_pos=6, max_pos_pct=0.20, day_cap=0,
   desc="Saham uptrend (di atas EMA200) yang RSI(2)<10. Jual saat close > SMA5 (lelang penutupan) atau maks 7 hari."),
 V(id="C1", name="ORB 30 Menit", kind="scalp", profile="Agresif", tf="15m", logic="orb",
   min_value=0, sl_atr=1.0, tp_r=1.5, trail_atr=0, time_stop=0, risk_pct=0.0025, max_pos=3, max_pos_pct=0.30, day_cap=500_000,
   desc="Opening range 09:00–09:30. Beli saat close 15m menembus high OR dengan volume di atas rata-rata (≤14:15). Wajib flat sebelum tutup."),
 V(id="C2", name="VWAP Bounce", kind="scalp", profile="Sangat agresif", tf="15m", logic="vwap",
   min_value=0, sl_atr=1.0, tp_r=1.0, trail_atr=0, time_stop=0, risk_pct=0.005, max_pos=4, max_pos_pct=0.30, day_cap=1_500_000,
   desc="Harga & EMA20 di atas VWAP, pullback menyentuh VWAP lalu candle hijau (≤14:15). TP 1R, wajib flat sebelum tutup."),
]
SCALP_UNIVERSE = ["BBCA","BBRI","BMRI","BBNI","TLKM","ASII","GOTO","ANTM","ADRO","MDKA","BRIS","PTRO","CUAN","AMMN","UNTR"]
